"""
Pull TM-level performance data from 4 NEE franchise sheets, pick the 5 worst-performing
teammates per franchise, write coaching narratives, and inject the result into
index.html's TEAMMATES JS array.

Auth: reads service account JSON from env GOOGLE_SERVICE_ACCOUNT_JSON
      (or falls back to ./service_account.json for local testing).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

# Allow importing sibling modules whether the script is run from repo root or scripts/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from training_kb import QUOTES, METRIC_ANCHORS, quote_for, all_quotes_for, scenario_label  # noqa: E402

# Optional LLM-driven coaching: enabled only if ANTHROPIC_API_KEY is set.
try:
    import anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ---------- config ----------

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"
ROSTER_JSON = REPO_ROOT / "roster.json"

SHEET_IDS = {
    "bno": "1wNbp3pshBKqh3T5J2yLAM_5ukWo_MGjXRAarYoGz7tY",
    "bso": "1fvN6C7yd8YKBtQ4HnrodF_hBaa_v_fegKb9JszHmZkA",
    "cp":  "1cyTKzfEtnp4lcMLDyT7_g8L7dW75dgWdXJE6wrI-em4",
    "ct":  "13hqFm7cMX_pwxmLQgZSYEJ5KC-T64k5LmKHEYuVjSeU",
}

FRANCHISE_NAMES = {
    "bno": "Boston North",
    "bso": "Boston South",
    "cp":  "Coastal Ports",
    "ct":  "Connecticut",
}

# Standards per franchise: AJS $, 1/6 max%, Truck+ min%, complaint max%, NPS min%, GR min%
# NPS goal 90%, Google Reviews capture goal 25%.
STANDARDS = {
    "bno": {"ajs": 725, "loss": 33.0, "truck": 10.0, "complaint": 1.50, "nps": 90.0, "gr": 25.0},
    "bso": {"ajs": 725, "loss": 33.0, "truck": 10.0, "complaint": 1.50, "nps": 90.0, "gr": 25.0},
    "cp":  {"ajs": 619, "loss": 30.0, "truck": 12.5, "complaint": 1.50, "nps": 90.0, "gr": 25.0},
    "ct":  {"ajs": 619, "loss": 35.0, "truck": 10.0, "complaint": 1.30, "nps": 90.0, "gr": 25.0},
}

# Weights per leadership spec: AJS 50%, Complaints 20%, NPS 15%, Reviews 15% (sum = 100).
# Sub-scoring is BINARY: full weight if at/above standard, 0 if below.
_RAW_WEIGHTS = {"ajs": 50.0, "complaint": 20.0, "nps": 15.0, "gr": 15.0}
_W_TOTAL = sum(_RAW_WEIGHTS.values())  # 100
WEIGHTS = {k: v / _W_TOTAL for k, v in _RAW_WEIGHTS.items()}

# Coach mapping intentionally removed. Coaching language is now leader-agnostic
# so any team leader can pick up the dashboard and act on it without context.

# Min residential jobs for a TM to be eligible for coaching priority
# (small samples are noisy and not actionable)
MIN_RESI_JOBS = 10


# ---------- data shape ----------

@dataclass
class TM:
    franchise_code: str
    name: str          # display "First Last"
    role: str          # "CSL" / "CEL" / "SSL"
    resi_jobs: int
    resi_ajs: Optional[float]
    nps: Optional[float]
    loss_pct: Optional[float]   # 1/6 or less %
    truck_pct: Optional[float]
    cancel_conv_pct: Optional[float]
    complaint_pct: Optional[float]
    gr_pct: Optional[float] = None     # Google Reviews capture %
    weighted_score: float = 100.0      # 100 = at standard across the board, lower = worse
    sub_scores: dict = field(default_factory=dict)  # per-metric 0-100 scores
    severity: str = "medium"
    primary_issue: str = ""             # which metric is the dominant problem
    reasons: list[str] = field(default_factory=list)


# ---------- parsing helpers ----------

def parse_money(s: str) -> Optional[float]:
    if s is None:
        return None
    s = str(s).strip().replace("$", "").replace(",", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_pct(s: str) -> Optional[float]:
    """Parse '37.96%' -> 37.96, or '0.3796' -> 37.96."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s == "-":
        return None
    has_pct = s.endswith("%")
    s = s.rstrip("%").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if not has_pct and abs(v) <= 1.5:
        v *= 100  # 0.xxx -> percent
    return v


def parse_int(s: str) -> Optional[int]:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def display_name(raw: str) -> str:
    """Convert 'Last, First' -> 'First Last'. Pass through if already 'First Last'."""
    raw = raw.strip()
    if "," in raw:
        last, _, first = raw.partition(",")
        return f"{first.strip()} {last.strip()}"
    return raw


# ---------- sheet reading ----------

def auth_gspread() -> gspread.Client:
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ],
        )
    else:
        path = REPO_ROOT / "service_account.json"
        if not path.exists():
            raise RuntimeError(
                "No GOOGLE_SERVICE_ACCOUNT_JSON env var and no service_account.json file."
            )
        creds = Credentials.from_service_account_file(
            str(path),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ],
        )
    return gspread.authorize(creds)


def _looks_like_label(raw_name: str) -> bool:
    """Detect rows that are headers / standards / labels, not actual TM names."""
    upper = raw_name.upper().strip()
    if upper in {"CEL", "CSL", "SSL", "STANDARDS", "TEAMMATE", "NAME"}:
        return True
    if upper.startswith("OUR ") or "STANDARD" in upper:
        return True
    if upper.startswith("ANNUAL PLAN") or upper.startswith("MONTHLY"):
        return True
    if upper.startswith("ZZZZZ"):
        return True
    if upper.startswith("DIVERTED") or upper.startswith("RECYCL") or upper.startswith("DONAT"):
        return True
    if upper.startswith("TOTAL") or upper.startswith("AVERAGE") or upper.startswith("AVG"):
        return True
    # Rows that are clearly framework / headline text, not names
    if upper.startswith("WE ") or upper.startswith("THIS ") or upper.startswith("THE "):
        return True
    return False


def read_section(rows: list[list[str]], name_col_idx: int, role: str, code: str) -> list[TM]:
    """
    Parse a vertical TM block. Layout (offset from name_col_idx):
      +0  name
      +5  RESI JOBS (count)
      +6  RESI AJS ($)
      +8  1/6 OR LESS (%)
      +10 RESI TRUCK+ (%)
      +14 GOOGLE REVIEWS (%)
      +18 NPS (%)
      +20 TTM CANCEL CONVERSION (%)
      +22 TTM COMPLAINTS (%)

    Digital Whiteboard often has multiple data sections (sorted view + alphabetical
    view + historical) all in the same column. We scan the ENTIRE sheet, parse every
    row that looks like a TM, and de-duplicate by name. When a teammate appears
    multiple times we keep the row with the most RESI JOBS (most complete data).
    """
    tms_by_name: dict[str, TM] = {}
    for r in rows:
        def cell(off: int) -> str:
            return r[name_col_idx + off] if name_col_idx + off < len(r) else ""

        raw_name = cell(0).strip()
        if not raw_name:
            continue
        if _looks_like_label(raw_name):
            continue
        # A real teammate name is two words minimum (Last, First or First Last)
        if len(raw_name) < 3:
            continue

        resi_ajs = parse_money(cell(6))
        resi_jobs = parse_int(cell(5))
        # Skip rows that have no real performance data (avoids picking up the
        # alphabetical employee list at column A which has term flags but no metrics).
        if resi_ajs is None and resi_jobs in (None, 0):
            continue

        tm = TM(
            franchise_code=code,
            name=display_name(raw_name),
            role=role,
            resi_jobs=resi_jobs or 0,
            resi_ajs=resi_ajs,
            nps=parse_pct(cell(18)),
            loss_pct=parse_pct(cell(8)),
            truck_pct=parse_pct(cell(10)),
            cancel_conv_pct=parse_pct(cell(20)),
            complaint_pct=parse_pct(cell(22)),
            gr_pct=parse_pct(cell(14)),
        )

        existing = tms_by_name.get(tm.name)
        if existing is None or (tm.resi_jobs > existing.resi_jobs):
            tms_by_name[tm.name] = tm
    return list(tms_by_name.values())


def fetch_franchise(gc: gspread.Client, code: str) -> list[TM]:
    sh = gc.open_by_key(SHEET_IDS[code])
    ws = sh.worksheet("Digital Whiteboard")
    # Scan the entire used range so we catch teammates regardless of how far down
    # the sheet they appear. Sheets typically max at ~228 rows; pull the lot.
    last_row = max(250, ws.row_count)
    grid = ws.get_values(f"A1:AY{last_row}")

    # Skip the top rows that are headers (rows 1-4)
    body = grid[4:]
    cels = read_section(body, name_col_idx=4, role="CEL", code=code)   # column E
    csls = read_section(body, name_col_idx=28, role="CSL", code=code)  # column AC
    return cels + csls


# ---------- weighted scoring ----------

def _sub_score_higher_better(value: Optional[float], standard: float) -> Optional[float]:
    """
    Binary scoring (higher = better). At-or-above standard = 100. Below = 0.
    No partial credit for being below the line.
    """
    if value is None or standard <= 0:
        return None
    return 100.0 if value >= standard else 0.0


def _sub_score_lower_better(value: Optional[float], standard: float) -> Optional[float]:
    """
    Binary scoring (lower = better, e.g. Complaints). At-or-below = 100. Above = 0.
    """
    if value is None or standard <= 0:
        return None
    return 100.0 if value <= standard else 0.0


def score_tm(tm: TM) -> None:
    std = STANDARDS[tm.franchise_code]

    sub = {
        "ajs":        _sub_score_higher_better(tm.resi_ajs, std["ajs"]),
        "complaint":  _sub_score_lower_better(tm.complaint_pct, std["complaint"]),
        "nps":        _sub_score_higher_better(tm.nps, std["nps"]),
        "gr":         _sub_score_higher_better(tm.gr_pct, std["gr"]),
    }
    tm.sub_scores = {k: v for k, v in sub.items() if v is not None}

    # Reweight available metrics so missing data doesn't deflate the composite artificially
    weight_present = sum(WEIGHTS[k] for k, v in sub.items() if v is not None)
    if weight_present == 0:
        tm.weighted_score = 100.0
    else:
        tm.weighted_score = sum(
            sub[k] * WEIGHTS[k] / weight_present for k in sub if sub[k] is not None
        )
    # Hard cap at 100 (no over-100 scores)
    tm.weighted_score = min(100.0, tm.weighted_score)

    # Identify the dominant problem area (lowest sub-score below 100)
    below = {k: v for k, v in tm.sub_scores.items() if v < 100}
    tm.primary_issue = min(below, key=below.get) if below else ""

    # Severity bucket - calibrated to the binary score grid (0, 15, 20, 30, 35,
    # 50, 65, 70, 80, 85, 100). Hits-out-of-4 maps cleanly:
    #   100        = elite (4/4 standards met)
    #   80-85      = solid (3/4 met)
    #   65-70      = watch (2/4 met, including AJS)
    #   below 65   = urgent (missing AJS or 2+ standards)
    if tm.weighted_score < 65:
        tm.severity = "urgent"
    elif tm.weighted_score < 80:
        tm.severity = "high"
    else:
        tm.severity = "medium"


def pick_worst_5(tms: list[TM]) -> list[TM]:
    eligible = [t for t in tms if t.resi_jobs >= MIN_RESI_JOBS]
    for t in eligible:
        score_tm(t)
    # Primary sort: composite score ascending (worst first)
    # Tiebreaker: count of metrics below standard, then raw AJS gap (deeper gap = worse)
    def _rank_key(t: TM) -> tuple:
        below_count = sum(1 for v in t.sub_scores.values() if v < 100)
        ajs_gap = (STANDARDS[t.franchise_code]["ajs"] - (t.resi_ajs or 0))
        return (t.weighted_score, -below_count, -ajs_gap)
    eligible.sort(key=_rank_key)
    return eligible[:5]


def pick_top_5(tms: list[TM]) -> list[TM]:
    """Top 5 performers per franchise by composite score (descending).
    Tiebreaker: raw AJS dollars (higher = better)."""
    eligible = [t for t in tms if t.resi_jobs >= MIN_RESI_JOBS]
    for t in eligible:
        if not t.sub_scores:  # may not have been scored yet
            score_tm(t)
    eligible.sort(key=lambda t: (-t.weighted_score, -(t.resi_ajs or 0)))
    return eligible[:5]


def render_roster_entry(tm: TM) -> dict:
    """Lightweight roster record for the full-team view. No LLM-generated text."""
    if not tm.sub_scores:
        score_tm(tm)
    std = STANDARDS[tm.franchise_code]
    metrics: list[dict] = []
    metrics.append({"l": "Score", "v": f"{int(round(tm.weighted_score))}/100"})
    if tm.resi_ajs is not None:
        cls = "bad" if tm.resi_ajs < std["ajs"] else "good"
        metrics.append({"l": "Adj AJS", "v": f"${tm.resi_ajs:,.0f}", "c": cls})
    if tm.complaint_pct is not None:
        cls = "bad" if tm.complaint_pct > std["complaint"] else "good"
        metrics.append({"l": "Complaints", "v": f"{tm.complaint_pct:.2f}%", "c": cls})
    if tm.nps is not None:
        cls = "bad" if tm.nps < std["nps"] else "good"
        metrics.append({"l": "NPS", "v": f"{tm.nps:.0f}%", "c": cls})
    if tm.gr_pct is not None:
        cls = "bad" if tm.gr_pct < std["gr"] else "good"
        metrics.append({"l": "Reviews", "v": f"{tm.gr_pct:.1f}%", "c": cls})

    # Tier classification (binary scoring grid: only 100 hits all standards)
    if tm.weighted_score >= 100:
        tier = "elite"
    elif tm.weighted_score >= 80:
        tier = "solid"
    elif tm.weighted_score >= 65:
        tier = "watch"
    else:
        tier = "urgent"

    return {
        "id": f"roster-{tm.franchise_code}-{tm.name.replace(' ', '-').replace(',', '')}",
        "franchiseCode": tm.franchise_code,
        "name": tm.name,
        "role": tm.role,
        "score": int(round(tm.weighted_score)),
        "tier": tier,
        "resiJobs": tm.resi_jobs,
        "metrics": metrics,
    }


def render_top_performer(tm: TM) -> dict:
    """Lightweight record for the Top Performers display (no LLM call)."""
    std = STANDARDS[tm.franchise_code]
    highlights: list[str] = []
    if tm.resi_ajs is not None and tm.resi_ajs >= std["ajs"]:
        highlights.append(f"AJS {fmt_money(tm.resi_ajs)}")
    if tm.complaint_pct is not None and tm.complaint_pct <= std["complaint"]:
        highlights.append(f"Complaints {fmt_pct(tm.complaint_pct, 2)}")
    if tm.nps is not None and tm.nps >= std["nps"]:
        highlights.append(f"NPS {fmt_pct(tm.nps, 0)}")
    if tm.gr_pct is not None and tm.gr_pct >= std["gr"]:
        highlights.append(f"Reviews {fmt_pct(tm.gr_pct, 1)}")
    return {
        "id": f"top-{tm.franchise_code}-{tm.name.replace(' ', '-')}",
        "franchiseCode": tm.franchise_code,
        "name": tm.name,
        "role": tm.role,
        "score": int(round(tm.weighted_score)),
        "resiJobs": tm.resi_jobs,
        "highlights": highlights[:3],
    }


# ---------- narrative generation ----------

def fmt_money(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else "n/a"


def fmt_pct(v: Optional[float], digits: int = 1) -> str:
    return f"{v:.{digits}f}%" if v is not None else "n/a"


def _today_salt() -> int:
    """Date-based salt so narratives rotate daily (keeps the dashboard feeling fresh)."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return sum(ord(c) * (i + 1) for i, c in enumerate(today))


def _stable_pick(seq: list[str], tm: TM) -> str:
    """
    Per-TM choice from a list of phrasings. Rotates daily so the same TM doesn't
    see the same wording every morning. Deterministic within a day so re-runs
    on the same date produce identical output.
    """
    h = sum(ord(c) for c in tm.name) + _today_salt()
    return seq[h % len(seq)]


def make_why(tm: TM) -> str:
    """
    Build a why narrative anchored on the dominant problem.
    Voice: warm, observational, coaching-style. Frames data as patterns
    worth understanding, not verdicts. No em dashes.
    """
    std = STANDARDS[tm.franchise_code]
    score = tm.weighted_score
    parts: list[str] = []

    # Lead with composite framing (multiple variants per band so daily rotation feels fresh)
    if score < 60:
        openers = [
            f"Composite at {score:.0f}/100. There's more than one thing going on here, worth taking time to see the whole picture before picking a single focus.",
            f"Score {score:.0f}/100. A few signals are pointing the same direction, which usually means one underlying habit is driving it rather than three separate issues.",
            f"At {score:.0f}/100, the picture is layered. The temptation is to coach all of it at once, which rarely works. Better to find the root and pull on that thread.",
            f"Composite {score:.0f}. Multi-front, but not random. Patterns this consistent usually trace back to a single behavior at the close or in the customer interaction.",
            f"Score lands at {score:.0f}/100. Worth slowing down before reacting. The numbers tell us where, but the conversation tells us why.",
        ]
        parts.append(_stable_pick(openers, tm))
    elif score < 80:
        openers = [
            f"Composite {score:.0f}/100. One area is doing most of the work pulling the score down. Zeroing in there is more productive than broadening.",
            f"At {score:.0f}/100, the headline number isn't a crisis, but the pattern is consistent enough to be worth a conversation.",
            f"Score {score:.0f}/100. Close enough to the line that one focused habit shift could move it meaningfully in two weeks.",
            f"Composite at {score:.0f}. Not a fire, more like a small leak. Worth catching now before it widens.",
            f"At {score:.0f}/100. He's not far off, which is the trickiest place to coach because the natural pull is to leave it alone.",
        ]
        parts.append(_stable_pick(openers, tm))
    else:
        openers = [
            f"Composite {score:.0f}/100. Close to the line on most things, slightly under on one. A small course-correction kind of week.",
            f"At {score:.0f}/100, this is light-touch maintenance coaching. One area to nudge, nothing to redesign.",
            f"Score {score:.0f}/100. Worth a brief check-in rather than a sit-down. Confidence reps, not crisis intervention.",
        ]
        parts.append(_stable_pick(openers, tm))

    # Anchor on the dominant issue with a coaching framing
    primary = tm.primary_issue
    if primary == "ajs" and tm.resi_ajs is not None:
        gap = std["ajs"] - tm.resi_ajs
        if gap > 150:
            ajs_lines = [
                f"Adjusted Resi AJS is sitting at {fmt_money(tm.resi_ajs)}, which is roughly ${gap:.0f} under our {fmt_money(std['ajs'])} mark. When AJS slides this far, it's almost always something in the close softening, not effort. Worth listening for whether the assumptive ask is still happening.",
                f"AJS at {fmt_money(tm.resi_ajs)}. The gap to {fmt_money(std['ajs'])} is real and it's been growing. Usually the answer lives in one of two places: he's hesitating on the assumptive ask, or Priority Items is getting skipped under pressure.",
            ]
            parts.append(_stable_pick(ajs_lines, tm))
        else:
            ajs_lines = [
                f"AJS at {fmt_money(tm.resi_ajs)}, about ${gap:.0f} short of {fmt_money(std['ajs'])}. He's right at the line, which is the trickiest place to coach because the natural pull is to leave it alone. Worth a small conversation before it widens.",
                f"Adj Resi AJS {fmt_money(tm.resi_ajs)}. The gap is closeable in a single shift if it's a confidence dip. Worth asking what's been on his mind.",
            ]
            parts.append(_stable_pick(ajs_lines, tm))
    elif primary == "complaint" and tm.complaint_pct is not None:
        ratio = tm.complaint_pct / std["complaint"]
        if ratio >= 3:
            comp_lines = [
                f"Complaint rate at {tm.complaint_pct:.2f}%, which is {ratio:.1f}x our {std['complaint']:.2f}% line. At his volume that's not noise, it's a pattern. Customers are walking away unhappy more often than the rest of the team and it's worth understanding what they're telling us specifically.",
                f"Complaints at {tm.complaint_pct:.2f}%, well past the {std['complaint']:.2f}% mark. The number is loud enough that the answer is probably in the actual feedback, not in another sales conversation. Worth pulling the recent ones and reading them together.",
            ]
            parts.append(_stable_pick(comp_lines, tm))
        else:
            comp_lines = [
                f"Complaint rate sitting at {tm.complaint_pct:.2f}%, about {ratio:.1f}x our {std['complaint']:.2f}% standard. Not alarm-level yet, but the trend is the part to pay attention to. Sometimes it's pace, sometimes tone, sometimes the close that lands wrong.",
                f"Complaints at {tm.complaint_pct:.2f}% (standard {std['complaint']:.2f}%). At this volume, even a couple of negative experiences can move the number. Worth checking whether they cluster around a time of day or job type.",
            ]
            parts.append(_stable_pick(comp_lines, tm))
    elif primary == "nps" and tm.nps is not None:
        nps_lines = [
            f"NPS at {tm.nps:.0f}% (goal {std['nps']:.0f}%). Customers are responding but not enthusiastically. That gap usually points to one of three things: pace felt rushed, communication broke somewhere, or the close came across as salesy.",
            f"NPS sitting at {tm.nps:.0f}%, under our {std['nps']:.0f}% goal. Worth listening to a couple of recent calls before deciding what to coach. The story tends to be in the customer's words, not the number.",
        ]
        parts.append(_stable_pick(nps_lines, tm))
    elif primary == "gr" and tm.gr_pct is not None:
        gr_lines = [
            f"Google Reviews capture at {tm.gr_pct:.1f}% (goal {std['gr']:.0f}%). When the capture rate is the lagging metric, it's almost always the same root cause: the ask isn't happening on the truck, or it's happening so quietly the customer doesn't notice it.",
            f"Reviews capture at {tm.gr_pct:.1f}%, well under our {std['gr']:.0f}% mark. Most people don't drop the ask because they don't want to. They drop it because they don't have a script that feels natural in their own voice.",
        ]
        parts.append(_stable_pick(gr_lines, tm))

    # 1-2 supporting observations, framed as context not verdicts
    secondary: list[str] = []
    if primary != "ajs" and tm.resi_ajs is not None and tm.resi_ajs < std["ajs"]:
        gap = std["ajs"] - tm.resi_ajs
        secondary.append(f"Worth noting AJS is also under, at {fmt_money(tm.resi_ajs)} (${gap:.0f} below {fmt_money(std['ajs'])}).")
    if primary != "complaint" and tm.complaint_pct is not None and tm.complaint_pct > std["complaint"]:
        secondary.append(f"Complaints sit at {tm.complaint_pct:.2f}% (vs {std['complaint']:.2f}% goal), which compounds the picture.")
    if primary != "nps" and tm.nps is not None and tm.nps < std["nps"]:
        secondary.append(f"NPS at {tm.nps:.0f}% adds to the customer-side signal.")
    if primary != "gr" and tm.gr_pct is not None and tm.gr_pct < std["gr"]:
        secondary.append(f"Reviews capture {tm.gr_pct:.1f}% trails the goal too.")

    # Mention extreme save/cancel situations explicitly
    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        secondary.append("Worth flagging: cancel conversion at 100%, meaning the SC Save isn't being attempted.")
    if tm.truck_pct is not None and tm.truck_pct < std["truck"]:
        secondary.append(f"Truck+ at {tm.truck_pct:.1f}% (vs {std['truck']:.1f}% std) is another thread worth pulling.")

    parts.extend(secondary[:2])

    # Volume context (last beat) - establishes the signal is real
    if tm.resi_jobs > 0:
        vol_lines = [
            f"Signal sits on {tm.resi_jobs} resi jobs, so it's a real read.",
            f"This is across {tm.resi_jobs} resi jobs, not a small-sample story.",
            f"{tm.resi_jobs} resi jobs of data behind it.",
        ]
        parts.append(_stable_pick(vol_lines, tm))

    return " ".join(parts)


def make_play(tm: TM, slot_idx: int = 0) -> str:
    """
    Build a play action in leader-agnostic coaching voice. Direct, action-first.
    slot_idx kept for signature compatibility but unused now that coach names are gone.
    """
    std = STANDARDS[tm.franchise_code]
    primary = tm.primary_issue

    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        actions = [
            "<strong>Pull 15 minutes for a Scenario 3.3 walkthrough.</strong> Take one real cancel from this week and run through it line by line. Have him script the SC Save in his own words before next shift so it lands naturally instead of memorized.",
            "<strong>Pair him with a strong closer for two shifts.</strong> Watching a save attempt happen up close shifts the mindset faster than another conversation. Goal: one documented attempt per cancel, even if it doesn't land.",
        ]
        return _stable_pick(actions, tm)

    if primary == "complaint":
        actions = [
            "<strong>Sit down with him before next shift.</strong> Pull the recent detractors together. Read them with curiosity, not accountability. The pattern usually surfaces on its own. Pick one thing to focus on for the week, not three.",
            "<strong>Ride along this week, focused on the late-afternoon hours.</strong> Fatigue is when service starts costing. Watch Punctual, Etiquette, Memorable in real time. Debrief same-day so the signal stays fresh.",
            "<strong>Open with what he's hearing from customers.</strong> The gap between intent and impact is invisible from inside the truck. The ask: what would he change if he could rerun the last shift?",
        ]
        return _stable_pick(actions, tm)

    if primary == "nps":
        actions = [
            "<strong>Listen to 2-3 recent calls with him this week.</strong> Not for blame, just to hear what the customer heard. CUSTOMER lens: Memorable, WOW Factor, Positive Ending. Commit to one per shift.",
            "<strong>Block 30 minutes for a service review.</strong> Replay the worst couple of NPS responses together. Where did the experience break? One concrete change per job, not a list of five.",
        ]
        return _stable_pick(actions, tm)

    if primary == "gr":
        actions = [
            "<strong>Run a 15-minute huddle on the review ask.</strong> Practice the words out loud, in his voice. Most people drop the ask because the script feels stiff, not because they don't want to. Track on paper for one week.",
            "<strong>Ride along and focus on the closeout moment.</strong> Listen for whether the ask happens, and how it's framed. Coach the words in the moment, not after the shift.",
        ]
        return _stable_pick(actions, tm)

    # AJS-led (or fallback)
    if tm.resi_ajs is not None and (std["ajs"] - tm.resi_ajs) > 100:
        actions = [
            f"<strong>Carve out a 1:1 today.</strong> Walk through 3 recent shifts together. Less PIP framing, more 'help me understand where this slipped.' If it's confidence, pair shadow with a top closer for two shifts. If it's process, run Scenario 3.1 verbally. 15-day target back to {fmt_money(std['ajs'])}.",
            "<strong>Pre-shift today, then a shadow tomorrow.</strong> Listen specifically for whether the assumptive ask is still landing. AJS dips at this scale almost always live in the close, not in effort or knowledge.",
        ]
        return _stable_pick(actions, tm)

    actions = [
        "<strong>Catch him in the morning huddle.</strong> Set an explicit AJS goal for the day, written down. Have him track each job's upsell attempt on paper. Review at EOD as a 'what did we learn' conversation, not a scorecard.",
        "<strong>Do a mid-shift check-in.</strong> Pull one job apart together: was Priority Items delivered? Was Truck+ pitched? Adjust on the next call. In-the-moment coaching compounds faster than end-of-week reviews.",
        "<strong>Run a 20-minute Scenario 3.1 refresher.</strong> Priority Items step specifically. The ask: one Truck+ pitch per job tomorrow, with him keeping his own count.",
    ]
    return _stable_pick(actions, tm)


def _resolve_anchor_key(tm: TM) -> str:
    """Map this TM's situation to the right anchor key in training_kb.METRIC_ANCHORS."""
    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        return "cancel_save"
    primary = tm.primary_issue or "ajs"
    # Truck+ is its own anchor when it's the dominant secondary signal
    std = STANDARDS[tm.franchise_code]
    if (primary == "ajs" and tm.truck_pct is not None and tm.truck_pct < std["truck"] / 2):
        return "truck_plus"
    return primary


def make_anchor(tm: TM) -> dict:
    """
    Returns the primary coaching anchor for this TM as a structured object:
      {
        "ref":   "Scenario 1, Step 4 - Estimate & Price",
        "name":  "Estimate & Price - Rules of the Range",
        "quote": "Confidence is EVERYTHING. Memorize the price list...",
        "rationale": "AJS dips at this scale usually live in the close..."
      }
    Used by the dashboard's Coaching Anchor block.
    """
    key = _resolve_anchor_key(tm)
    primary_quote = quote_for(key, secondary=False)
    secondary_quote = quote_for(key, secondary=True)

    rationale_map = {
        "ajs":         "AJS dips at this scale almost always live in the close, not in effort or knowledge. The fix is in the words, not the work.",
        "complaint":   "Complaint patterns usually trace back to either the agenda not landing or the experience feeling rushed.",
        "nps":         "Customers leaving lukewarm usually mean the experience peaked too early or the rapport stayed surface-level.",
        "gr":          "Reviews are won at the closeout. The 5 Star Service Agenda promises it; the closeout has to ask for it.",
        "cancel_save": "A 100% conversion-to-cancel almost always means the save isn't being attempted, not that it's being attempted badly.",
        "truck_plus":  "Truck+ rate is the canary on AJS health. If the seed isn't being planted on the Call Ahead, the load won't grow on site.",
    }

    return {
        "ref":          scenario_label(primary_quote),
        "name":         primary_quote["name"],
        "quote":        primary_quote["text"],
        "secondaryRef": scenario_label(secondary_quote) if secondary_quote != primary_quote else "",
        "secondaryName": secondary_quote["name"] if secondary_quote != primary_quote else "",
        "secondaryQuote": secondary_quote["text"] if secondary_quote != primary_quote else "",
        "rationale":    rationale_map.get(key, rationale_map["ajs"]),
    }


def make_framework(tm: TM) -> str:
    """Backwards-compatible single-line framework string. Kept for the dashboard's
    legacy framework field; the richer block is delivered via make_anchor()."""
    a = make_anchor(tm)
    return f"{a['ref']}. {a['rationale']}"


# ---------- AI coaching (optional, requires Anthropic API key) ----------

# Cache the client across calls
_AI_CLIENT = None
_AI_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def _ai_client():
    global _AI_CLIENT
    if _AI_CLIENT is None and _ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
        _AI_CLIENT = anthropic.Anthropic()
    return _AI_CLIENT


_AI_SYSTEM = """You are COACH RICK, the in-house master sales coach for the New England Elite \
1-800-GOT-JUNK? region. You've coached hundreds of CSLs, CELs and SSLs through the CSL \
Scenario playbook (Scenarios 1, 2, 3.1, 3.2, 3.3). You speak with the calm authority of \
someone who has seen every pattern before. You write daily coaching guidance that ANY \
team leader on the NEE leadership team can pick up cold and act on in a 1:1 or huddle.

YOUR JOB:
Translate raw performance numbers into a clear hypothesis about the underlying behavior, \
then give the leader a tight, specific play that maps to a real CSL Scenario step.

VOICE RULES (strict, non-negotiable):
- Warm but direct. Confident, action-first. Like a senior coach giving a peer the read.
- NEVER name a specific coach, manager, GM, or person other than the teammate. \
Frame actions as imperatives: "Pull 15 minutes with him...", "Run a Scenario 3.1 drill...", \
"Block 20 minutes pre-shift...". NEVER write "Tyler should..." or "Have the GM pull...". \
Any leader on the team must be able to act on this without context.
- No em dashes. Use periods or commas.
- Specific to this teammate's ACTUAL numbers, not generic. Cite the dollar figure, \
the percent gap, the metric name. If complaint rate is 4.2% vs 1.5% standard, say that.
- Reference the actual training material when relevant. Use real scenario names and step \
numbers from the context provided ("Scenario 3.3 Step 4 - Negotiation Protocol").
- Build a HYPOTHESIS that connects multiple metrics into a single underlying behavior. \
That's the coach's value-add. Don't just describe; diagnose.
- 3-5 sentences per section. Tight. No filler. No throat-clearing.

You will be given:
- The teammate's performance vs their franchise standards
- The dominant problem area
- Excerpts from the actual CSL Scenario training material that maps to that problem

Return JSON with exactly these keys:
{
  "why":   "3-5 sentences. What the data shows and the most likely underlying \
behavior. Anchor on the dominant problem. Add 1-2 supporting observations connecting \
metrics into a single hypothesis.",
  "play":  "3-5 sentences. A specific coaching action for this week. Concrete: time \
block, what to look at, what to practice. Reference the relevant training step. \
Use imperative voice ('Pull...', 'Block 20 minutes...', 'Run a Scenario X.X drill...'), \
NOT 'Coach should...' or any named person other than the teammate.",
  "rationale": "2-3 sentences. Why this specific training step is the right anchor \
for this teammate's pattern.",
  "deepDive": [
    {"category": "🎯 Today's Conversation", "q": "Give me a 60-second 1:1 opener I can use today.", "a": "..."},
    {"category": "🎯 Today's Conversation", "q": "Write a verbatim opening line for the conversation.", "a": "..."},
    {"category": "🎯 Today's Conversation", "q": "What posture should I bring? Curious, firm, or supportive?", "a": "..."},
    {"category": "📊 Diagnose the Pattern", "q": "What's the single biggest leverage point right now?", "a": "..."},
    {"category": "📊 Diagnose the Pattern", "q": "Three questions to surface what's behind the numbers.", "a": "..."},
    {"category": "📊 Diagnose the Pattern", "q": "What would I expect to see if my hypothesis is correct?", "a": "..."},
    {"category": "🚀 Path Forward", "q": "Build me a 7-day improvement plan.", "a": "..."},
    {"category": "🚀 Path Forward", "q": "What does success look like in two weeks?", "a": "..."},
    {"category": "🚀 Path Forward", "q": "What's the warning sign that this isn't working?", "a": "..."},
    {"category": "🚀 Path Forward", "q": "If I only have 5 minutes today, what's the one thing?", "a": "..."}
  ]
}

The ten deepDive questions above are FIXED - keep them verbatim, including the category \
prefix. Write each "a" in 2-5 sentences, same voice rules. Each answer must be specific \
to this teammate's actual numbers and reference real scenario steps where relevant. \
Vary your phrasing across the answers so the leader doesn't see the same construction \
repeated. The "verbatim opening line" answer should be a direct quote the leader can \
literally say.

Return ONLY valid JSON. No prose outside the object."""


def _ai_prompt(tm: TM) -> str:
    std = STANDARDS[tm.franchise_code]
    franchise_name = FRANCHISE_NAMES[tm.franchise_code]

    quotes = all_quotes_for(_resolve_anchor_key(tm))
    training_block = "\n\n".join(
        f"--- {scenario_label(q)} ---\n{q['text']}" for q in quotes[:3]
    )

    metrics_block = (
        f"  Adjusted Resi AJS: {fmt_money(tm.resi_ajs)} (standard {fmt_money(std['ajs'])})\n"
        f"  Complaint rate:    {fmt_pct(tm.complaint_pct, 2)} (max {std['complaint']:.2f}%)\n"
        f"  NPS:               {fmt_pct(tm.nps, 0)} (min {std['nps']:.0f}%)\n"
        f"  Reviews capture:   {fmt_pct(tm.gr_pct, 1)} (min {std['gr']:.0f}%)\n"
        f"  TTM cancel conv:   {fmt_pct(tm.cancel_conv_pct, 1) if tm.cancel_conv_pct is not None else 'n/a'}\n"
        f"  Truck+ rate:       {fmt_pct(tm.truck_pct, 1) if tm.truck_pct is not None else 'n/a'}\n"
        f"  Resi jobs:         {tm.resi_jobs}\n"
        f"  Composite score:   {tm.weighted_score:.0f}/100\n"
        f"  Severity:          {tm.severity}"
    )

    return f"""TEAMMATE
  Name:      {tm.name}
  Role:      {tm.role}
  Franchise: {franchise_name}

PERFORMANCE THIS PERIOD
{metrics_block}

DOMINANT PROBLEM
  {tm.primary_issue or 'mixed'}

RELEVANT TRAINING MATERIAL (use scenario names verbatim in your output)
{training_block}

Today's date: {datetime.now(timezone.utc).strftime('%A, %B %d')}. Vary phrasing day-to-day so this teammate doesn't see identical wording every morning.

Generate the JSON object."""


_COACH_PICK_SYSTEM = """You are COACH RICK, master sales coach for the New England Elite \
1-800-GOT-JUNK? region. You have just reviewed today's coaching list (the worst-scoring \
5 teammates from each of 4 franchises = 20 total).

Pick the SINGLE TEAMMATE who is the highest-leverage coaching conversation today. \
"Highest-leverage" means: where one focused conversation could move the most \
performance, OR where waiting another day is the most expensive.

Your output is a short brief that any leader on the team can read in 15 seconds and \
know exactly who to talk to first this morning.

VOICE:
- You're a senior coach giving the team's leadership a tip. Direct, confident, warm.
- NEVER name a coach, manager, or person other than the chosen teammate.
- No em dashes. No filler. No throat-clearing.
- Cite the specific number that drove your pick.

Return JSON exactly:
{
  "tmId": "<the id of the chosen teammate>",
  "headline": "One short sentence framing the pick (under 90 chars).",
  "rationale": "2-3 sentences. Why THIS person, today. What's the leverage. Reference \
the metric pattern and which CSL Scenario step would unlock it."
}

Return ONLY valid JSON."""


_HUDDLE_SYSTEM = """You are COACH RICK, master sales coach for the New England Elite \
1-800-GOT-JUNK? region. You have just reviewed today's coaching list (5 worst per franchise) \
plus today's top performers (5 best per franchise). Write a SHORT MORNING HUDDLE BRIEF \
that any leader can read aloud at the start of their daily team huddle.

VOICE:
- Energetic, real, specific. Like a coach hyping the team before practice.
- NEVER name a coach, manager, or person other than the teammates you mention.
- Use real names from the data when shouting people out or flagging concerns.
- No em dashes. No filler.
- 90-120 seconds when read aloud (about 180-220 words total).

STRUCTURE (use these section headings exactly):
- "What's working" — 2-3 sentences celebrating something real from today's top performers.
- "Where the focus needs to be" — 2-3 sentences naming the team-wide pattern from the worst-5 list (without piling on individuals).
- "Today's challenge" — One specific behavioral challenge for the whole region, tied to a CSL Scenario step. Make it concrete (e.g., 'Every CSL gives the assumptive ask within 3 seconds of the bid').

Return JSON exactly:
{
  "headline": "One short rallying line (under 80 chars).",
  "whatsWorking": "2-3 sentences.",
  "whereFocus": "2-3 sentences.",
  "todaysChallenge": "1-2 sentences. Concrete, behavioral, tied to a Scenario step."
}

Return ONLY valid JSON."""


def generate_huddle_brief(coaching_records: list[dict], top_records: list[dict]) -> Optional[dict]:
    """Generate today's morning huddle brief based on the full team picture."""
    client = _ai_client()
    if client is None:
        return None
    try:
        worst_lines = []
        for r in coaching_records:
            metrics = {m["l"]: m["v"] for m in r.get("metrics", [])}
            worst_lines.append(
                f"{r['name']} ({r['role']}, {FRANCHISE_NAMES.get(r['franchiseCode'], r['franchiseCode'])}) "
                f"score {metrics.get('Score', '?')} severity {r['severity']}"
            )
        top_lines = []
        for r in top_records:
            top_lines.append(
                f"{r['name']} ({r['role']}, {FRANCHISE_NAMES.get(r['franchiseCode'], r['franchiseCode'])}) "
                f"score {r['score']}/100, {r['resiJobs']} jobs, highlights: {', '.join(r['highlights']) if r['highlights'] else 'n/a'}"
            )
        prompt = (
            f"Today's date: {datetime.now(timezone.utc).strftime('%A, %B %d')}.\n\n"
            "TODAY'S COACHING LIST (worst per franchise):\n"
            + "\n".join(worst_lines)
            + "\n\nTODAY'S TOP PERFORMERS (best per franchise):\n"
            + "\n".join(top_lines)
            + "\n\nWrite today's morning huddle brief."
        )
        resp = client.messages.create(
            model=_AI_MODEL,
            max_tokens=700,
            system=_HUDDLE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        if not all(k in data for k in ("headline", "whatsWorking", "whereFocus", "todaysChallenge")):
            return None
        return data
    except Exception as e:
        print(f"::warning::Huddle brief generation failed: {e}", file=sys.stderr)
        return None


_MOTIVATIONAL_SYSTEM = """You are COACH RICK. Write today's motivational message for the New \
England Elite leadership team. They lead a junk-removal franchise, not a Silicon Valley startup.

VOICE:
- Plain. Honest. Like a coach getting his guys ready before the shift.
- Short. 2-4 sentences. Under 60 words total.
- No corporate cheerleader energy. No "synergy" or "let's crush it" garbage.
- Use real words: trucks, jobs, the close, the shift, the team, the work.
- Reference today's reality lightly if it sharpens the message - the urgent count, the top \
scores, the day of the week. Don't force it.
- No em dashes.

What you're going for: the leader reads this and feels ready. Not pumped-up fake. Ready. The way \
a real coach makes you feel before you go do hard work.

NEVER use these words: framework, paradigm, intentionality, bandwidth, holistically, optimize, \
leverage (verb), strategically, granular, ecosystem, alignment (noun), cadence, north star, \
unpack, lean in, surface, calibrate, synergy, crush it.

Return JSON exactly:
{
  "headline": "One punchy line (under 70 chars). The hook.",
  "body": "2-3 short sentences. The substance."
}

Return ONLY valid JSON."""


def generate_motivational_message(coaching_records: list[dict], top_records: list[dict]) -> Optional[dict]:
    """Generate today's motivational message from Coach Rick."""
    client = _ai_client()
    if client is None:
        return None
    try:
        urgent = sum(1 for r in coaching_records if r.get("severity") == "urgent")
        high = sum(1 for r in coaching_records if r.get("severity") == "high")
        top_count = len(top_records)
        day_of_week = datetime.now(timezone.utc).strftime("%A")
        prompt = (
            f"Today is {day_of_week}.\n"
            f"Across the region: {urgent} urgent teammates, {high} high-priority teammates "
            f"on today's coaching list. {top_count} teammates standing out as top performers.\n\n"
            "Write today's motivational message."
        )
        resp = client.messages.create(
            model=_AI_MODEL,
            max_tokens=300,
            system=_MOTIVATIONAL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        if not all(k in data for k in ("headline", "body")):
            return None
        return data
    except Exception as e:
        print(f"::warning::Motivational message generation failed: {e}", file=sys.stderr)
        return None


def pick_top_5_regional(roster_records: list[dict]) -> list[dict]:
    """Top 5 across the entire region. Tiebreaker: AJS (higher wins)."""
    def _ajs_value(r: dict) -> float:
        for m in r.get("metrics") or []:
            if m.get("l") == "Adj AJS":
                v = str(m.get("v", "")).replace("$", "").replace(",", "")
                try:
                    return float(v)
                except ValueError:
                    return 0.0
        return 0.0

    sorted_roster = sorted(
        roster_records,
        key=lambda r: (-r.get("score", 0), -_ajs_value(r)),
    )
    out: list[dict] = []
    for r in sorted_roster[:5]:
        out.append({
            "name": r["name"],
            "role": r["role"],
            "franchiseCode": r["franchiseCode"],
            "score": r["score"],
            "ajs": _ajs_value(r),
            "tier": r.get("tier", ""),
            "resiJobs": r.get("resiJobs", 0),
        })
    return out


def generate_coach_pick(records: list[dict]) -> Optional[dict]:
    """Pick today's highest-leverage coaching conversation across the whole region."""
    client = _ai_client()
    if client is None or not records:
        return None
    try:
        # Compact summary - id, name, franchise, score, severity, primary problem signal
        lines = []
        for r in records:
            metrics_dict = {m["l"]: m["v"] for m in r.get("metrics", [])}
            lines.append(
                f"{r['id']} | {r['name']} ({r['role']}, {FRANCHISE_NAMES.get(r['franchiseCode'], r['franchiseCode'])}) "
                f"| score {metrics_dict.get('Score', '?')} | severity {r['severity']} "
                f"| AJS {metrics_dict.get('Adj AJS', '?')} | Complaints {metrics_dict.get('Complaints', '?')} "
                f"| NPS {metrics_dict.get('NPS', '?')} | Reviews {metrics_dict.get('Reviews', '?')}"
            )
        summary = "\n".join(lines)
        prompt = (
            "TODAY'S COACHING LIST (5 worst per franchise, 20 total):\n\n"
            + summary
            + "\n\nPick the single highest-leverage coaching conversation for today."
        )
        resp = client.messages.create(
            model=_AI_MODEL,
            max_tokens=400,
            system=_COACH_PICK_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        if not all(k in data for k in ("tmId", "headline", "rationale")):
            return None
        # Validate the picked id exists
        if not any(r["id"] == data["tmId"] for r in records):
            return None
        return data
    except Exception as e:
        print(f"::warning::Coach Rick pick generation failed: {e}", file=sys.stderr)
        return None


def generate_ai_coaching(tm: TM, slot_idx: int = 0) -> Optional[dict]:
    """
    Use Claude to generate why / play / rationale for this teammate.
    Returns None if the API isn't available or the call fails.
    slot_idx kept for signature compatibility but unused.
    """
    client = _ai_client()
    if client is None:
        return None

    try:
        resp = client.messages.create(
            model=_AI_MODEL,
            max_tokens=3500,
            system=_AI_SYSTEM,
            messages=[{"role": "user", "content": _ai_prompt(tm)}],
        )
        raw = resp.content[0].text.strip()
        # Strip code fences if present
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        if not all(k in data for k in ("why", "play", "rationale")):
            return None
        return data
    except Exception as e:
        print(f"::warning::AI coaching generation failed for {tm.name}: {e}", file=sys.stderr)
        return None


def make_score_breakdown(tm: TM) -> str:
    """
    Plain-text breakdown for the score badge tooltip. Shows each sub-score,
    its weight, and the contribution.
    """
    rows: list[str] = []
    label_map = {
        "ajs": "Adj AJS",
        "complaint": "Complaints",
        "nps": "NPS",
        "gr": "Reviews",
    }
    weight_present = sum(WEIGHTS[k] for k in tm.sub_scores)
    for k in ("ajs", "complaint", "nps", "gr"):
        if k not in tm.sub_scores:
            rows.append(f"{label_map[k]}: no data")
            continue
        sub = tm.sub_scores[k]
        eff_w = WEIGHTS[k] / weight_present if weight_present else 0
        contrib = sub * eff_w
        rows.append(f"{label_map[k]}: {sub:.0f}/100 × {eff_w*100:.0f}% = {contrib:.1f}")
    rows.append(f"Composite: {tm.weighted_score:.0f}/100")
    return "\n".join(rows)


def make_metrics(tm: TM) -> list[dict]:
    """
    Show the 4 weighted metrics first (AJS, Complaint, NPS, GR), color-coded vs standard,
    plus the composite score. Drops in 1-2 contextual metrics if AJS/Complaint/NPS/GR alone
    don't tell the story.
    """
    std = STANDARDS[tm.franchise_code]
    out: list[dict] = []

    # Composite score badge (always first), with breakdown tooltip
    score_cls = "bad" if tm.weighted_score < 75 else ("good" if tm.weighted_score >= 95 else None)
    score_entry = {
        "l": "Score",
        "v": f"{tm.weighted_score:.0f}/100",
        "tip": make_score_breakdown(tm),
    }
    if score_cls:
        score_entry["c"] = score_cls
    out.append(score_entry)

    if tm.resi_ajs is not None:
        cls = "bad" if tm.resi_ajs < std["ajs"] else "good"
        out.append({"l": "Adj AJS", "v": fmt_money(tm.resi_ajs), "c": cls})

    if tm.complaint_pct is not None:
        cls = "bad" if tm.complaint_pct > std["complaint"] else "good"
        out.append({"l": "Complaints", "v": fmt_pct(tm.complaint_pct, 2), "c": cls})

    if tm.nps is not None:
        cls = "bad" if tm.nps < std["nps"] else "good"
        out.append({"l": "NPS", "v": fmt_pct(tm.nps, 0), "c": cls})

    if tm.gr_pct is not None:
        cls = "bad" if tm.gr_pct < std["gr"] else "good"
        out.append({"l": "Reviews", "v": fmt_pct(tm.gr_pct, 1), "c": cls})

    # Contextual extras only if there's a clear secondary signal
    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        out.append({"l": "Cancel Conv", "v": fmt_pct(tm.cancel_conv_pct, 0), "c": "bad"})

    return out


# ---------- HTML injection ----------

def render_teammates(records: list[dict]) -> str:
    """Build the JS array body (without the surrounding 'const TEAMMATES = [' and '];')."""
    chunks: list[str] = []
    by_fr: dict[str, list[dict]] = {}
    for r in records:
        by_fr.setdefault(r["franchiseCode"], []).append(r)

    label = {"bno": "BOSTON NORTH", "bso": "BOSTON SOUTH", "cp": "COASTAL PORTS", "ct": "CONNECTICUT"}
    order = ["bno", "bso", "cp", "ct"]

    for code in order:
        if code not in by_fr:
            continue
        chunks.append(f"\n    // {label[code]}")
        for tm in by_fr[code]:
            def _metric_js(m: dict) -> str:
                pairs = ["l: " + json.dumps(m["l"]), "v: " + json.dumps(m["v"])]
                if "c" in m:
                    pairs.append("c: " + json.dumps(m["c"]))
                if "tip" in m:
                    pairs.append("tip: " + json.dumps(m["tip"]))
                return "{ " + ", ".join(pairs) + " }"
            metrics_js = ", ".join(_metric_js(m) for m in tm["metrics"])
            anchor_js = json.dumps(tm.get("anchor", {}), ensure_ascii=False)
            source_js = json.dumps(tm.get("anchorSource", "template"))
            deep_dive_js = json.dumps(tm.get("deepDive", []), ensure_ascii=False)
            chunks.append(
                "    {\n"
                f"      id: {json.dumps(tm['id'])}, priority: {tm['priority']}, "
                f"franchiseCode: {json.dumps(tm['franchiseCode'])}, "
                f"name: {json.dumps(tm['name'])}, role: {json.dumps(tm['role'])}, "
                f"severity: {json.dumps(tm['severity'])},\n"
                f"      why: {json.dumps(tm['why'])},\n"
                f"      play: {json.dumps(tm['play'])},\n"
                f"      framework: {json.dumps(tm['framework'])},\n"
                f"      anchor: {anchor_js},\n"
                f"      anchorSource: {source_js},\n"
                f"      deepDive: {deep_dive_js},\n"
                f"      metrics: [{metrics_js}]\n"
                "    },"
            )
    # Trim trailing comma off the last element
    out = "\n".join(chunks)
    out = re.sub(r",\s*$", "", out)
    return out + "\n  "


def update_index_html(
    records: list[dict],
    updated_iso: str,
    coach_pick: Optional[dict] = None,
    top_performers: Optional[list[dict]] = None,
    motivational_message: Optional[dict] = None,
    huddle_brief: Optional[dict] = None,
    top_5_regional: Optional[list[dict]] = None,
) -> None:
    src = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Replace TEAMMATES array body
    pattern = re.compile(r"(const TEAMMATES = \[)(.*?)(\];)", re.DOTALL)
    if not pattern.search(src):
        raise RuntimeError("Could not find `const TEAMMATES = [...];` block in index.html")
    new_body = render_teammates(records)
    src = pattern.sub(lambda m: m.group(1) + new_body + m.group(3), src)

    # Helper: replace a single-line `const NAME = <value>;` declaration safely.
    # Critical: anchor `;` to end-of-line so a `;` inside a string value can't
    # accidentally terminate the match and leave stale content behind.
    def replace_const(html: str, name: str, value_js: str) -> str:
        # ^(prefix)(any chars, lazily)(;)([trailing whitespace + optional comment])$
        pat = re.compile(
            rf"^([ \t]*const {re.escape(name)} = ).+?;([ \t]*(?://[^\n]*)?)$",
            re.MULTILINE,
        )
        if pat.search(html):
            return pat.sub(lambda m: m.group(1) + value_js + ";" + m.group(2), html)
        return html

    src = replace_const(src, "COACH_PICK",          json.dumps(coach_pick or None, ensure_ascii=False))
    src = replace_const(src, "TOP_PERFORMERS",      json.dumps(top_performers or [], ensure_ascii=False))
    src = replace_const(src, "MOTIVATIONAL_MESSAGE", json.dumps(motivational_message or None, ensure_ascii=False))
    src = replace_const(src, "MVP_PICK",            "null")  # deprecated, force-null
    src = replace_const(src, "HUDDLE_BRIEF",        json.dumps(huddle_brief or None, ensure_ascii=False))
    src = replace_const(src, "TOP_5_REGIONAL",      json.dumps(top_5_regional or [], ensure_ascii=False))

    # 5. Update / insert LAST_UPDATED HTML comment near the top
    last_updated_marker = re.compile(r"<!--\s*LAST_UPDATED:.*?-->", re.IGNORECASE)
    new_comment = f"<!-- LAST_UPDATED: {updated_iso} -->"
    if last_updated_marker.search(src):
        src = last_updated_marker.sub(new_comment, src)
    else:
        src = src.replace("<!DOCTYPE html>", "<!DOCTYPE html>\n" + new_comment, 1)

    INDEX_HTML.write_text(src, encoding="utf-8")


# ---------- main ----------

def main() -> int:
    try:
        gc = auth_gspread()
    except Exception as e:
        print(f"::error::Could not authenticate to Google Sheets: {e}", file=sys.stderr)
        return 2

    all_records: list[dict] = []
    top_records: list[dict] = []
    roster_records: list[dict] = []
    for code in ("bno", "bso", "cp", "ct"):
        try:
            tms = fetch_franchise(gc, code)
        except Exception as e:
            print(f"::error::Failed to read {code.upper()} sheet: {e}", file=sys.stderr)
            return 3

        # Full roster (every eligible TM with sub-scores) for the chat sidebar
        eligible = [t for t in tms if t.resi_jobs >= MIN_RESI_JOBS]
        for t in eligible:
            score_tm(t)
            roster_records.append(render_roster_entry(t))

        worst = pick_worst_5(tms)
        for i, tm in enumerate(worst, start=1):
            anchor = make_anchor(tm)

            ai = generate_ai_coaching(tm, slot_idx=i - 1)
            deep_dive: list[dict] = []
            if ai:
                why = ai["why"]
                play = ai["play"]
                anchor["rationale"] = ai["rationale"]
                anchor_source = "ai"
                deep_dive = ai.get("deepDive") or []
            else:
                why = make_why(tm)
                play = make_play(tm, slot_idx=i - 1)
                anchor_source = "template"

            all_records.append({
                "id": f"tm-{code}-{i}",
                "priority": i,
                "franchiseCode": code,
                "name": tm.name,
                "role": tm.role,
                "severity": tm.severity,
                "why": why,
                "play": play,
                "framework": make_framework(tm),
                "anchor": anchor,
                "anchorSource": anchor_source,
                "deepDive": deep_dive,
                "metrics": make_metrics(tm),
            })
        # Top performers per franchise (no LLM needed, fast pure ranking)
        top = pick_top_5(tms)
        for tp in top:
            top_records.append(render_top_performer(tp))

        print(f"  {code.upper()}: {len(tms)} TMs read, picked {len(worst)} for coaching "
              f"(scores: {', '.join(f'{t.weighted_score:.0f}' for t in worst)}); "
              f"top {len(top)} (scores: {', '.join(f'{t.weighted_score:.0f}' for t in top)})",
              file=sys.stderr)

    if not all_records:
        print("::error::No teammates picked. Refusing to overwrite index.html.", file=sys.stderr)
        return 4

    # Coach Rick writes today's motivational message.
    motivational = generate_motivational_message(all_records, top_records)
    # Coach Rick writes the morning huddle brief based on the full team picture.
    huddle = generate_huddle_brief(all_records, top_records)
    # Top 5 regional performers (across all franchises). AJS is the tiebreaker.
    top_5_regional = pick_top_5_regional(roster_records)

    updated_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    update_index_html(
        all_records, updated_iso,
        top_performers=top_records,
        motivational_message=motivational,
        huddle_brief=huddle,
        top_5_regional=top_5_regional,
    )
    # Write the full roster as a separate JSON the chat view loads at runtime.
    # Sorted worst-first so leaders see who needs help when scrolling the sidebar.
    roster_records.sort(key=lambda r: r["score"])
    ROSTER_JSON.write_text(json.dumps({
        "updated": updated_iso,
        "teammates": roster_records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"index.html updated. LAST_UPDATED={updated_iso}, {len(all_records)} TMs written, "
          f"{len(top_records)} top performers.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
