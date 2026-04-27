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


# ---------- config ----------

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"

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
STANDARDS = {
    "bno": {"ajs": 725, "loss": 33.0, "truck": 10.0, "complaint": 1.50, "nps": 90.0, "gr": 25.0},
    "bso": {"ajs": 725, "loss": 33.0, "truck": 10.0, "complaint": 1.50, "nps": 90.0, "gr": 25.0},
    "cp":  {"ajs": 619, "loss": 30.0, "truck": 12.5, "complaint": 1.50, "nps": 90.0, "gr": 25.0},
    "ct":  {"ajs": 619, "loss": 35.0, "truck": 10.0, "complaint": 1.30, "nps": 90.0, "gr": 25.0},
}

# Weighted score weights (must sum to 1.0). Lower weighted score = worse performer.
WEIGHTS = {"ajs": 0.50, "complaint": 0.20, "nps": 0.15, "gr": 0.15}

COACHES = {
    "bno": ["Richard", "Tyler"],
    "bso": ["Tommy", "Kendall"],
    "cp":  ["Pat"],
    "ct":  ["Larry", "Jakarie", "Tim"],
}

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


def read_section(rows: list[list[str]], name_col_idx: int, role: str, code: str) -> list[TM]:
    """
    Parse a left-to-right TM block. Layout (offset from name_col_idx):
      +0 name
      +6 RESI AJS ($)
      +5 RESI JOBS (count)
      +8 1/6 OR LESS (%)
      +10 RESI TRUCK+ (%)
      +18 NPS (%)
      +20 TTM CANCEL CONVERSION (%)
      +22 TTM COMPLAINTS (%)

    Digital Whiteboard repeats the data in a second section further down (alphabetical
    list, possibly different time window). We only want the first section, so we stop
    when we hit any signal of the standards block or a re-heading.
    """
    tms: list[TM] = []
    consecutive_blank = 0
    for r in rows:
        def cell(off: int) -> str:
            return r[name_col_idx + off] if name_col_idx + off < len(r) else ""

        raw_name = cell(0).strip()
        if not raw_name:
            consecutive_blank += 1
            # Many blank rows in a row = end of this section
            if consecutive_blank >= 4:
                break
            continue
        consecutive_blank = 0

        # Stop on re-heading or standards block
        upper = raw_name.upper()
        if upper in {"CEL", "CSL", "SSL", "STANDARDS", "TEAMMATE"}:
            break
        if upper.startswith("OUR ") or "STANDARD" in upper or upper.startswith("ANNUAL PLAN"):
            break
        # ZZZZZ is just an in-section divider — keep reading
        if upper.startswith("ZZZZZ"):
            continue

        resi_ajs = parse_money(cell(6))
        resi_jobs = parse_int(cell(5))
        if resi_ajs is None and resi_jobs in (None, 0):
            continue

        tms.append(TM(
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
        ))
    return tms


def fetch_franchise(gc: gspread.Client, code: str) -> list[TM]:
    sh = gc.open_by_key(SHEET_IDS[code])
    ws = sh.worksheet("Digital Whiteboard")
    # Pull a generous range; rows beyond data are skipped naturally
    grid = ws.get_values("A1:AY120")

    # Section starts at row 5 (1-indexed) = index 4
    body = grid[4:]
    cels = read_section(body, name_col_idx=4, role="CEL", code=code)   # E
    csls = read_section(body, name_col_idx=28, role="CSL", code=code)  # AC
    return cels + csls


# ---------- weighted scoring ----------

def _sub_score_higher_better(value: Optional[float], standard: float) -> Optional[float]:
    """Score where higher value = better. 100 = at standard. Capped 0-130."""
    if value is None or standard <= 0:
        return None
    return max(0.0, min(130.0, (value / standard) * 100.0))


def _sub_score_lower_better(value: Optional[float], standard: float) -> Optional[float]:
    """Score where lower value = better (e.g., complaints). 100 = at standard."""
    if value is None or standard <= 0:
        return None
    if value <= 0:
        return 130.0  # better than perfect
    return max(0.0, min(130.0, (standard / value) * 100.0))


def score_tm(tm: TM) -> None:
    std = STANDARDS[tm.franchise_code]

    sub = {
        "ajs":        _sub_score_higher_better(tm.resi_ajs, std["ajs"]),
        "complaint":  _sub_score_lower_better(tm.complaint_pct, std["complaint"]),
        "nps":        _sub_score_higher_better(tm.nps, std["nps"]),
        "gr":         _sub_score_higher_better(tm.gr_pct, std["gr"]),
    }
    tm.sub_scores = {k: v for k, v in sub.items() if v is not None}

    # Reweight available metrics so missing data doesn't deflate score artificially
    weight_present = sum(WEIGHTS[k] for k, v in sub.items() if v is not None)
    if weight_present == 0:
        tm.weighted_score = 100.0
    else:
        tm.weighted_score = sum(
            (sub[k] * WEIGHTS[k] / weight_present) for k in sub if sub[k] is not None
        )

    # Identify the dominant problem area (lowest sub-score)
    below = {k: v for k, v in tm.sub_scores.items() if v < 100}
    if below:
        tm.primary_issue = min(below, key=below.get)
    else:
        tm.primary_issue = ""

    # Map score to severity bucket
    if tm.weighted_score < 60:
        tm.severity = "urgent"
    elif tm.weighted_score < 80:
        tm.severity = "high"
    else:
        tm.severity = "medium"


def pick_worst_5(tms: list[TM]) -> list[TM]:
    eligible = [t for t in tms if t.resi_jobs >= MIN_RESI_JOBS]
    for t in eligible:
        score_tm(t)
    eligible.sort(key=lambda t: t.weighted_score)  # ascending = worst first
    return eligible[:5]


# ---------- narrative generation ----------

def fmt_money(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else "n/a"


def fmt_pct(v: Optional[float], digits: int = 1) -> str:
    return f"{v:.{digits}f}%" if v is not None else "n/a"


def pick_coach(code: str, idx: int) -> str:
    """Rotate through coaches by priority slot so the same coach isn't named 5 times."""
    coaches = COACHES[code]
    return coaches[idx % len(coaches)]


def _stable_pick(seq: list[str], tm: TM) -> str:
    """Stable per-TM choice from a list of phrasings (deterministic, varies by name)."""
    h = sum(ord(c) for c in tm.name)
    return seq[h % len(seq)]


def make_why(tm: TM) -> str:
    """
    Build a why narrative anchored on the dominant problem, with secondary observations.
    Voice: short, punchy, warm but direct. No em dashes.
    """
    std = STANDARDS[tm.franchise_code]
    score = tm.weighted_score
    parts: list[str] = []

    # Lead with score context for severity
    if score < 50:
        opener_pool = [
            f"Composite {score:.0f}/100. Multi-front problem.",
            f"Score {score:.0f}/100. He's bleeding on more than one axis.",
            f"Composite {score:.0f}. Whole picture is red.",
        ]
        parts.append(_stable_pick(opener_pool, tm))
    elif score < 75:
        opener_pool = [
            f"Score {score:.0f}/100. One real problem, a few smaller leaks.",
            f"Composite {score:.0f}. Not a crisis yet, but trending wrong.",
        ]
        parts.append(_stable_pick(opener_pool, tm))

    # Anchor on dominant issue
    primary = tm.primary_issue
    if primary == "ajs" and tm.resi_ajs is not None:
        gap = std["ajs"] - tm.resi_ajs
        if gap > 100:
            parts.append(f"Adj Resi AJS {fmt_money(tm.resi_ajs)}. That's ${gap:.0f} under {fmt_money(std['ajs'])}. The close isn't landing.")
        else:
            parts.append(f"Adj Resi AJS {fmt_money(tm.resi_ajs)}, ${gap:.0f} short of {fmt_money(std['ajs'])}. Hovering at the line.")
    elif primary == "complaint" and tm.complaint_pct is not None:
        ratio = tm.complaint_pct / std["complaint"]
        if ratio >= 3:
            parts.append(f"Complaints at {tm.complaint_pct:.2f}%. That's {ratio:.1f}x the {std['complaint']:.2f}% line. Customers are leaving angry.")
        else:
            parts.append(f"Complaint rate {tm.complaint_pct:.2f}%, {ratio:.1f}x our {std['complaint']:.2f}% mark. Quality is slipping.")
    elif primary == "nps" and tm.nps is not None:
        gap = std["nps"] - tm.nps
        if tm.nps < 70:
            parts.append(f"NPS {tm.nps:.0f}%. {gap:.0f} points below standard. Customers aren't recommending him.")
        elif tm.nps < 80:
            parts.append(f"NPS at {tm.nps:.0f}%, {gap:.0f} points off. Service execution is breaking.")
        else:
            parts.append(f"NPS {tm.nps:.0f}%. Right at the line, not under it yet.")
    elif primary == "gr" and tm.gr_pct is not None:
        parts.append(f"Google Reviews capture at {tm.gr_pct:.1f}% (standard {std['gr']:.0f}%). The ask isn't happening on the truck.")

    # Add 1-2 secondary observations (skip the primary, dedupe)
    secondary_pool: list[str] = []

    if primary != "ajs" and tm.resi_ajs is not None and tm.resi_ajs < std["ajs"]:
        gap = std["ajs"] - tm.resi_ajs
        secondary_pool.append(f"AJS {fmt_money(tm.resi_ajs)} (${gap:.0f} under).")
    if primary != "complaint" and tm.complaint_pct is not None and tm.complaint_pct > std["complaint"]:
        secondary_pool.append(f"Complaints {tm.complaint_pct:.2f}% (vs {std['complaint']:.2f}% std).")
    if primary != "nps" and tm.nps is not None and tm.nps < std["nps"]:
        secondary_pool.append(f"NPS {tm.nps:.0f}% (under {std['nps']:.0f}%).")
    if primary != "gr" and tm.gr_pct is not None and tm.gr_pct < std["gr"]:
        secondary_pool.append(f"Reviews capture {tm.gr_pct:.1f}% (vs {std['gr']:.0f}%).")

    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        secondary_pool.append("Cancel conversion 100%. Every save attempt failed.")
    if tm.truck_pct is not None and tm.truck_pct < std["truck"]:
        secondary_pool.append(f"Truck+ {tm.truck_pct:.1f}% (vs {std['truck']:.1f}% std).")

    parts.extend(secondary_pool[:2])

    # Volume context (last beat)
    if tm.resi_jobs > 0:
        parts.append(f"Sample: {tm.resi_jobs} resi jobs.")

    return " ".join(parts)


def make_play(tm: TM, slot_idx: int) -> str:
    """
    Build a play action. Coach rotates per slot. Voice: short, action-first.
    """
    std = STANDARDS[tm.franchise_code]
    coach = pick_coach(tm.franchise_code, slot_idx)
    primary = tm.primary_issue

    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        actions = [
            f"<strong>{coach} runs Scenario 3.3 verbal practice today.</strong> Pull one actual cancel from this week. Replay it line by line. Have him script the SC Save out loud before next shift.",
            f"<strong>{coach} pairs him with a strong closer for two shifts.</strong> Goal: one documented save attempt per cancel. Track it on paper.",
        ]
        return _stable_pick(actions, tm)

    if primary == "complaint":
        actions = [
            f"<strong>{coach} pre-shift sit-down.</strong> Pull the 3 most recent detractors. Walk through what got missed. Have him personally call 2 customers back tomorrow.",
            f"<strong>{coach} runs a service ride-along this week.</strong> Watch the 4-6pm hour. Score Punctual + Etiquette + Memorable. Debrief same day.",
            f"<strong>{coach} pulls the complaint logs together with him.</strong> Identify the pattern: pace, language, or close? One focus, one shift.",
        ]
        return _stable_pick(actions, tm)

    if primary == "nps":
        actions = [
            f"<strong>{coach} listens to 3 detractor calls with him this week.</strong> CUSTOMER framework: Memorable, WOW Factor, Positive Ending. Commit to 2 picture-perfect moments per shift.",
            f"<strong>{coach} blocks 30 minutes for a service review.</strong> Replay the worst 2 NPS responses. Where did the experience break? Concrete fix per job tomorrow.",
        ]
        return _stable_pick(actions, tm)

    if primary == "gr":
        actions = [
            f"<strong>{coach} 15-min huddle on the review ask.</strong> Practice the script out loud. Goal: every job tomorrow gets the ask, no exceptions. Track on paper.",
            f"<strong>{coach} ride-along, focus on the closeout moment.</strong> Listen for whether the review request happens. Coach the words in the moment, not after.",
        ]
        return _stable_pick(actions, tm)

    # AJS-led (or fallback)
    if tm.resi_ajs is not None and (std["ajs"] - tm.resi_ajs) > 100:
        actions = [
            f"<strong>{coach} 1:1 today.</strong> Frame as Level 1 PIP. Walk 3 recent shifts together. Pair shadow with a top closer next 2 shifts. 15-day target back to {fmt_money(std['ajs'])}.",
            f"<strong>{coach} pre-shift today, then shadow tomorrow.</strong> Verbal Scenario 3.1 walk-through. Identify whether it's Priority Items or the Assumptive Ask that's leaking.",
        ]
        return _stable_pick(actions, tm)

    actions = [
        f"<strong>{coach} morning huddle.</strong> Explicit AJS goal for the day. Track each job's upsell attempt on paper. Review at EOD.",
        f"<strong>{coach} mid-shift check-in.</strong> One job pulled apart together: was Priority Items delivered? Was Truck+ pitched? Adjust on the next call.",
        f"<strong>{coach} 20-min Scenario 3.1 refresher.</strong> Priority Items step specifically. One Truck+ pitch per job tomorrow, no exceptions.",
    ]
    return _stable_pick(actions, tm)


def make_framework(tm: TM) -> str:
    primary = tm.primary_issue

    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        return "CSL Scenario 3.3: REEAP Negotiation. 100% conversion-to-cancel means he's not even attempting the save."
    if primary == "complaint":
        return "CEL CUSTOMER + CSL Scenario 1. The 5-Star Service Agenda is either not being delivered or not landing."
    if primary == "nps":
        if tm.nps is not None and tm.nps < 70:
            return "CEL CUSTOMER framework: Memorable, Creating Lifelong Customers, Positive Ending. NPS this low is a service-quality fire, not a sales one."
        return "CEL CUSTOMER framework: back half (Memorable, Genuine, Positive Ending). Customers are leaving lukewarm."
    if primary == "gr":
        return "CSL Scenario 3.2 close + CEL CUSTOMER (Ask). Reviews don't happen by accident. The ask is the lever."
    if primary == "ajs":
        std = STANDARDS[tm.franchise_code]
        if tm.resi_ajs is not None and tm.resi_ajs < std["ajs"] - 100:
            return "CSL Performance Accountability: Level 1 PIP. Below 66% Resi AJS one month triggers a documented 30-day plan."
        return "CSL Scenario 3.1: Priority Items + Estimate & Price. AJS dips usually live in the close, not the truck."
    return "CSL Scenario 3.2: Estimate & Price + Assumptive Ask. Maintenance coaching focused on consistency."


def make_metrics(tm: TM) -> list[dict]:
    """
    Show the 4 weighted metrics first (AJS, Complaint, NPS, GR), color-coded vs standard,
    plus the composite score. Drops in 1-2 contextual metrics if AJS/Complaint/NPS/GR alone
    don't tell the story.
    """
    std = STANDARDS[tm.franchise_code]
    out: list[dict] = []

    # Composite score badge (always first)
    score_cls = "bad" if tm.weighted_score < 75 else ("good" if tm.weighted_score >= 95 else None)
    score_entry = {"l": "Score", "v": f"{tm.weighted_score:.0f}/100"}
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
            metrics_js = ", ".join(
                "{ l: " + json.dumps(m["l"]) + ", v: " + json.dumps(m["v"]) +
                (", c: " + json.dumps(m["c"]) if "c" in m else "") + " }"
                for m in tm["metrics"]
            )
            chunks.append(
                "    {\n"
                f"      id: {json.dumps(tm['id'])}, priority: {tm['priority']}, "
                f"franchiseCode: {json.dumps(tm['franchiseCode'])}, "
                f"name: {json.dumps(tm['name'])}, role: {json.dumps(tm['role'])}, "
                f"severity: {json.dumps(tm['severity'])},\n"
                f"      why: {json.dumps(tm['why'])},\n"
                f"      play: {json.dumps(tm['play'])},\n"
                f"      framework: {json.dumps(tm['framework'])},\n"
                f"      metrics: [{metrics_js}]\n"
                "    },"
            )
    # Trim trailing comma off the last element
    out = "\n".join(chunks)
    out = re.sub(r",\s*$", "", out)
    return out + "\n  "


def update_index_html(records: list[dict], updated_iso: str) -> None:
    src = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Replace TEAMMATES array body
    pattern = re.compile(r"(const TEAMMATES = \[)(.*?)(\];)", re.DOTALL)
    if not pattern.search(src):
        raise RuntimeError("Could not find `const TEAMMATES = [...];` block in index.html")
    new_body = render_teammates(records)
    src = pattern.sub(lambda m: m.group(1) + new_body + m.group(3), src)

    # 2. Update / insert LAST_UPDATED HTML comment near the top
    last_updated_marker = re.compile(r"<!--\s*LAST_UPDATED:.*?-->", re.IGNORECASE)
    new_comment = f"<!-- LAST_UPDATED: {updated_iso} -->"
    if last_updated_marker.search(src):
        src = last_updated_marker.sub(new_comment, src)
    else:
        # Insert right after <!DOCTYPE html> on its own line
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
    for code in ("bno", "bso", "cp", "ct"):
        try:
            tms = fetch_franchise(gc, code)
        except Exception as e:
            print(f"::error::Failed to read {code.upper()} sheet: {e}", file=sys.stderr)
            return 3

        worst = pick_worst_5(tms)
        for i, tm in enumerate(worst, start=1):
            all_records.append({
                "id": f"tm-{code}-{i}",
                "priority": i,
                "franchiseCode": code,
                "name": tm.name,
                "role": tm.role,
                "severity": tm.severity,
                "why": make_why(tm),
                "play": make_play(tm, slot_idx=i - 1),
                "framework": make_framework(tm),
                "metrics": make_metrics(tm),
            })
        print(f"  {code.upper()}: {len(tms)} TMs read, picked {len(worst)} for coaching "
              f"(scores: {', '.join(f'{t.weighted_score:.0f}' for t in worst)})", file=sys.stderr)

    if not all_records:
        print("::error::No teammates picked. Refusing to overwrite index.html.", file=sys.stderr)
        return 4

    updated_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    update_index_html(all_records, updated_iso)
    print(f"index.html updated. LAST_UPDATED={updated_iso}, {len(all_records)} TMs written.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
