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

# Standards per franchise: AJS $, 1/6 max%, Truck+ min%, complaint max%, NPS min%
STANDARDS = {
    "bno": {"ajs": 725, "loss": 33.0, "truck": 10.0, "complaint": 1.50, "nps": 90.0},
    "bso": {"ajs": 725, "loss": 33.0, "truck": 10.0, "complaint": 1.50, "nps": 90.0},
    "cp":  {"ajs": 619, "loss": 30.0, "truck": 12.5, "complaint": 1.50, "nps": 90.0},
    "ct":  {"ajs": 619, "loss": 35.0, "truck": 10.0, "complaint": 1.30, "nps": 90.0},
}

COACHES = {
    "bno": ["Richard", "Tyler"],
    "bso": ["Tommy", "Kendall"],
    "cp":  ["Pat"],
    "ct":  ["Larry", "Jakarie", "Tim"],
}

# Min residential jobs for a TM to be eligible for coaching priority
# (small samples are noisy and not actionable)
MIN_RESI_JOBS = 8


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
    tier: int = 0      # 1=urgent, 2=high, 3=medium, 0=ok
    score: float = 0.0
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


# ---------- scoring ----------

def score_tm(tm: TM) -> None:
    std = STANDARDS[tm.franchise_code]
    reds: list[str] = []
    urgent = False

    if tm.resi_ajs is not None and tm.resi_ajs < std["ajs"] - 100:
        urgent = True
        reds.append(f"Adj AJS ${tm.resi_ajs:.0f}, ${std['ajs'] - tm.resi_ajs:.0f} below ${std['ajs']} standard")
    if tm.complaint_pct is not None and tm.complaint_pct > 2 * std["complaint"]:
        urgent = True
        reds.append(f"Complaint {tm.complaint_pct:.2f}%, {tm.complaint_pct/std['complaint']:.1f}x the {std['complaint']:.2f}% standard")
    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        urgent = True
        reds.append("Cancel conversion 100%. Every cancel he touched stayed cancelled")

    secondary_reds: list[str] = []
    if tm.resi_ajs is not None and tm.resi_ajs < std["ajs"]:
        gap = std["ajs"] - tm.resi_ajs
        if gap <= 100:
            secondary_reds.append(f"Adj AJS ${tm.resi_ajs:.0f}, ${gap:.0f} below ${std['ajs']} standard")
    if tm.loss_pct is not None and tm.loss_pct > std["loss"]:
        secondary_reds.append(f"1/6-or-less {tm.loss_pct:.1f}% (vs {std['loss']:.0f}% std)")
    if tm.truck_pct is not None and tm.truck_pct < std["truck"]:
        secondary_reds.append(f"Truck+ {tm.truck_pct:.1f}% (vs {std['truck']:.1f}% std)")
    if tm.complaint_pct is not None and std["complaint"] < tm.complaint_pct <= 2 * std["complaint"]:
        secondary_reds.append(f"Complaint {tm.complaint_pct:.2f}% (vs {std['complaint']:.2f}% std)")
    nps_low = tm.nps is not None and tm.nps < std["nps"]
    nps_severe = tm.nps is not None and tm.nps < 80.0

    if urgent:
        tm.tier = 1
        tm.reasons = reds + secondary_reds
    elif nps_severe:
        tm.tier = 2
        tm.reasons = [f"NPS {tm.nps:.1f}%, {std['nps'] - tm.nps:.0f}pts below the {std['nps']:.0f}% standard"] + secondary_reds
    elif (tm.resi_ajs is not None and tm.resi_ajs < std["ajs"]) and len(secondary_reds) >= 2:
        tm.tier = 2
        tm.reasons = secondary_reds
    elif secondary_reds or nps_low:
        tm.tier = 3
        tm.reasons = secondary_reds[:1] or [f"NPS {tm.nps:.1f}% below {std['nps']:.0f}% standard"]
    else:
        tm.tier = 0

    # Score for ranking inside a tier (lower = worse)
    parts: list[float] = []
    if tm.resi_ajs is not None:
        parts.append((tm.resi_ajs - std["ajs"]) / std["ajs"])
    if tm.complaint_pct is not None:
        parts.append(-(tm.complaint_pct - std["complaint"]) / max(std["complaint"], 0.5))
    if tm.cancel_conv_pct is not None:
        parts.append(-(tm.cancel_conv_pct) / 100.0)
    if tm.nps is not None:
        parts.append((tm.nps - std["nps"]) / std["nps"])
    if tm.truck_pct is not None:
        parts.append((tm.truck_pct - std["truck"]) / max(std["truck"], 1.0))
    tm.score = sum(parts) / len(parts) if parts else 0.0


def pick_worst_5(tms: list[TM]) -> list[TM]:
    eligible = [t for t in tms if t.resi_jobs >= MIN_RESI_JOBS]
    for t in eligible:
        score_tm(t)
    flagged = [t for t in eligible if t.tier > 0]
    flagged.sort(key=lambda t: (t.tier, t.score))  # tier 1 first, then worst score
    if len(flagged) < 5:
        # Backfill with next-worst by score even if not flagged
        rest = [t for t in eligible if t.tier == 0]
        for t in rest:
            score_tm(t)
        rest.sort(key=lambda t: t.score)
        flagged += rest[: 5 - len(flagged)]
    return flagged[:5]


# ---------- narrative generation ----------

def severity_label(tier: int) -> str:
    return {1: "urgent", 2: "high", 3: "medium"}.get(tier, "medium")


def fmt_money(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else "n/a"


def fmt_pct(v: Optional[float], digits: int = 1) -> str:
    return f"{v:.{digits}f}%" if v is not None else "n/a"


def coach_line(code: str, action: str) -> str:
    coaches = COACHES[code]
    name = coaches[0]  # default lead coach
    return f"<strong>{name} {action}</strong>"


def make_why(tm: TM) -> str:
    std = STANDARDS[tm.franchise_code]
    parts: list[str] = []

    if tm.resi_ajs is not None and tm.resi_ajs < std["ajs"]:
        gap = std["ajs"] - tm.resi_ajs
        parts.append(f"Adj Resi AJS {fmt_money(tm.resi_ajs)}, ${gap:.0f} below the {fmt_money(std['ajs'])} standard.")

    if tm.complaint_pct is not None and tm.complaint_pct > std["complaint"]:
        ratio = tm.complaint_pct / std["complaint"]
        parts.append(f"Complaint rate {tm.complaint_pct:.2f}%, {ratio:.1f}x the {std['complaint']:.2f}% standard.")

    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        parts.append("Cancel conversion 100%. Every cancel he touched stayed cancelled. SC Save mechanics are missing.")

    if tm.nps is not None and tm.nps < std["nps"]:
        gap = std["nps"] - tm.nps
        if tm.nps < 80:
            parts.append(f"NPS {tm.nps:.1f}%, {gap:.0f} points below standard. Service quality is the bigger fire.")
        else:
            parts.append(f"NPS {tm.nps:.1f}% borderline.")

    if tm.truck_pct is not None and tm.truck_pct < std["truck"]:
        parts.append(f"Truck+ {tm.truck_pct:.1f}% (vs {std['truck']:.1f}% std). Closing small loads, not pitching the upsell.")

    if tm.loss_pct is not None and tm.loss_pct > std["loss"] and not any("AJS" in p for p in parts):
        parts.append(f"1/6-or-less rate {tm.loss_pct:.1f}% (vs {std['loss']:.0f}% std). Tiny-load problem.")

    if not parts:
        parts.append(f"Adj AJS {fmt_money(tm.resi_ajs)} below {fmt_money(std['ajs'])}. Single-metric watch list.")

    return " ".join(parts)


def make_play(tm: TM) -> str:
    std = STANDARDS[tm.franchise_code]
    if tm.tier == 1 and tm.resi_ajs is not None and tm.resi_ajs < std["ajs"] - 100:
        return f"{coach_line(tm.franchise_code, '1:1 today.')} Frame as Level 1 PIP. Walk 3 recent shifts together. Pair shadow with a top performer next 2 shifts. 15-day target back to {fmt_money(std['ajs'])}."
    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        return f"{coach_line(tm.franchise_code, 'runs a 15-min Scenario 3.3 verbal practice.')} Pull 1 actual cancel from this week and replay it together. Have him commit to 1 SC Save attempt per cancellation tomorrow."
    if tm.complaint_pct is not None and tm.complaint_pct > 2 * std["complaint"]:
        return f"{coach_line(tm.franchise_code, 'pre-shift sit-down.')} Pull last 3 NPS detractors. Walk through what was missed. Have him personally call back 2 of those customers."
    if tm.nps is not None and tm.nps < 80:
        return f"{coach_line(tm.franchise_code, 'runs a service-focused review.')} Listen to 3 detractor calls together. CUSTOMER framework: Memorable, WOW Factor, Etiquette. Commit to 2 picture-perfect moments per shift."
    if tm.truck_pct is not None and tm.truck_pct < std["truck"]:
        return f"{coach_line(tm.franchise_code, '30-min Scenario 3.1 refresher.')} Specifically the Priority Items step. Commit to 1 Truck+ pitch per job tomorrow."
    return f"{coach_line(tm.franchise_code, 'morning huddle.')} Set explicit AJS goal for the day. Have him write down each job's upsell attempts. Review at EOD."


def make_framework(tm: TM) -> str:
    std = STANDARDS[tm.franchise_code]
    if tm.tier == 1 and tm.resi_ajs is not None and tm.resi_ajs < std["ajs"] - 100:
        return "CSL Performance Accountability: Level 1 PIP. Below 66% Resi AJS for one month triggers documented plan with 30-day target."
    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        return "CSL Scenario 3.3: REEAP Negotiation Protocol. 100% conversion-to-cancel is a coaching emergency disguised as a metric."
    if tm.complaint_pct is not None and tm.complaint_pct > 2 * std["complaint"]:
        return "CEL CUSTOMER + CSL Scenario 1. The 5-Star Service Agenda either isn't being delivered or isn't landing."
    if tm.nps is not None and tm.nps < 80:
        return "CEL CUSTOMER framework: Memorable, Creating Lifelong Customers, Positive Ending. Low NPS at this scale is a service problem."
    if tm.truck_pct is not None and tm.truck_pct < std["truck"]:
        return "CSL Scenario 3.1: Priority Items + Estimate & Price. Truck+ rate is the canary on AJS health."
    return "CSL Scenario 3.2: Estimate & Price + Assumptive Ask. Maintenance coaching focused on the close."


def make_metrics(tm: TM) -> list[dict]:
    std = STANDARDS[tm.franchise_code]
    out: list[dict] = []

    if tm.resi_ajs is not None:
        cls = "bad" if tm.resi_ajs < std["ajs"] else "good"
        out.append({"l": "Adj AJS", "v": fmt_money(tm.resi_ajs), "c": cls})

    if tm.nps is not None:
        cls = "bad" if tm.nps < std["nps"] else "good"
        out.append({"l": "NPS", "v": fmt_pct(tm.nps, 1), "c": cls})

    if tm.truck_pct is not None:
        cls = "bad" if tm.truck_pct < std["truck"] else "good"
        out.append({"l": "Truck+", "v": fmt_pct(tm.truck_pct, 1), "c": cls})

    if tm.loss_pct is not None:
        cls = "bad" if tm.loss_pct > std["loss"] else "good"
        out.append({"l": "1/6 or Less", "v": fmt_pct(tm.loss_pct, 1), "c": cls})

    if tm.complaint_pct is not None and (tm.complaint_pct > std["complaint"] or len(out) < 4):
        cls = "bad" if tm.complaint_pct > std["complaint"] else "good"
        out.append({"l": "Complaint", "v": fmt_pct(tm.complaint_pct, 2), "c": cls})

    if tm.cancel_conv_pct is not None and tm.cancel_conv_pct >= 99.5:
        out.append({"l": "Cancel Conv", "v": fmt_pct(tm.cancel_conv_pct, 0), "c": "bad"})

    return out[:4]


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
                "severity": severity_label(tm.tier or 3),
                "why": make_why(tm),
                "play": make_play(tm),
                "framework": make_framework(tm),
                "metrics": make_metrics(tm),
            })
        print(f"  {code.upper()}: {len(tms)} TMs read, picked {len(worst)} for coaching", file=sys.stderr)

    if not all_records:
        print("::error::No teammates picked. Refusing to overwrite index.html.", file=sys.stderr)
        return 4

    updated_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    update_index_html(all_records, updated_iso)
    print(f"index.html updated. LAST_UPDATED={updated_iso}, {len(all_records)} TMs written.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
