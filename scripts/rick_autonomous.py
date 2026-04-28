"""
Coach Rick - Autonomous Improvement Mode.

Once a day, Rick reads:
  - Accumulated leader feedback (👍/👎) from Cloudflare KV
  - Recent leader notes from KV
  - Recent error reports from his own commit history
  - The current state of the whitelisted files
  - His own past improvement log (what he tried, what worked, what was reverted)

Then he proposes 0-3 small improvements as a strict JSON edit list. Every edit goes
through a validation gauntlet before commit. If anything fails, the run aborts cleanly.
After deploy, a smoke test pings the live page; if it's broken, Rick auto-reverts.

KILL SWITCH:
  Repository variable `COACH_RICK_AUTONOMY` must equal "on" or this script exits 0
  immediately. Default off. Flip via GitHub UI or `gh variable set`.

WHITELIST: only these files can be modified.
DENYLIST: substring patterns that must never appear in new content (API keys, tokens, etc).
PROTECTED REGIONS: line patterns that must remain unchanged within a file.

Run from repo root:
  COACH_RICK_AUTONOMY=on python3 scripts/rick_autonomous.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "scripts" / "rick_improvement_log.json"

# ============================================================
# GUARDS
# ============================================================

# Files Rick is allowed to touch. Anything outside this list is rejected.
WHITELIST = {
    "index.html",                              # UI / copy / chips / styles
    "scripts/training_kb.py",                  # CSL Scenario quotes + metric anchors
    "scripts/refresh_dashboard.py",            # narrative templates + scoring tweaks
    "functions/api/chat.js",                   # Coach Rick prompt + leadership library
    "scripts/standard_for_every_job.md",       # service playbook (rare; allowed)
}

# Substrings that must NEVER appear in any new content. Hard-stop if found.
DENYLIST_NEW_CONTENT = [
    "sk-ant-api",                              # Anthropic API key prefix
    "cfut_",                                   # Cloudflare API token prefix
    "BEGIN RSA PRIVATE KEY",
    "BEGIN PRIVATE KEY",
    "-----BEGIN OPENSSH PRIVATE KEY",
    "ANTHROPIC_API_KEY",                       # never hardcode the var name to a value
    "CLOUDFLARE_API_TOKEN",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "@gmail.com",                              # rough PII guard (no real emails)
]

# Regex patterns whose presence in a file must be preserved exactly.
# (We compute the count before/after and require it to be unchanged.)
PROTECTED_PATTERNS = {
    "index.html": [
        r"<!DOCTYPE html>",                    # must remain a valid html doc
        r"<script>",                           # the inline script block
        r"</script>",
        r"const TEAMMATES = \[",               # critical data anchors
        r"const FRANCHISES = \[",
        r"id=\"dashboard\"",
    ],
    "scripts/refresh_dashboard.py": [
        r"def main\(\)",                       # entry point must remain
        r"def update_index_html\(",            # the html updater
        r"if __name__ == \"__main__\"",
    ],
    "functions/api/chat.js": [
        r"export async function onRequest",    # public function signature
        r"https://api\.anthropic\.com/v1/messages",  # the upstream URL
        r"x-api-key",                          # the auth header
    ],
}

# Maximum total characters of diff Rick can produce in one run.
DIFF_CHAR_BUDGET = 8000

# Maximum number of edits per run.
MAX_EDITS_PER_RUN = 3

# Log size cap so it doesn't grow forever.
LOG_ENTRIES_KEEP = 200


# ============================================================
# CONTEXT GATHERING
# ============================================================

def kill_switch_off() -> bool:
    return (os.environ.get("COACH_RICK_AUTONOMY", "").strip().lower() not in ("on", "true", "1", "yes"))


def is_dry_run() -> bool:
    """In dry-run mode, all reads + LLM call + validators run, but no commit/push/deploy."""
    return os.environ.get("RICK_DRY_RUN", "").strip().lower() in ("on", "true", "1", "yes")


def get_kv_feedback_summary() -> dict:
    """Fetch a summary of recent feedback from Cloudflare KV (across all leaders).
    Returns {ups: int, downs: int, recent_downs: [strings]}.
    KV doesn't list keys cheaply, so we read a known summary key the workflow maintains.
    For v1, we just summarize from a known-key list pattern."""
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    namespace = os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID", "156baaf858c7465d9e427e2cd7c32707")
    if not token or not account:
        return {"ups": 0, "downs": 0, "recent_downs": [], "note": "no CF credentials"}

    import urllib.request
    import urllib.error

    try:
        # List keys with prefix "leader:" — KV API: GET /accounts/{acc}/storage/kv/namespaces/{ns}/keys
        url = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
               f"/storage/kv/namespaces/{namespace}/keys?prefix=leader:")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        keys = [k["name"] for k in data.get("result", []) if k["name"].endswith(":feedback")]
    except Exception as e:
        return {"ups": 0, "downs": 0, "recent_downs": [], "note": f"key list failed: {e}"}

    ups, downs, recent_downs = 0, 0, []
    for key in keys[:20]:  # cap to first 20 leaders
        try:
            url = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
                   f"/storage/kv/namespaces/{namespace}/values/{key}")
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                arr = json.loads(resp.read())
            for entry in arr[-50:]:
                if entry.get("rating") == "up":
                    ups += 1
                elif entry.get("rating") == "down":
                    downs += 1
                    if entry.get("comment"):
                        recent_downs.append({
                            "comment": entry["comment"][:300],
                            "question": entry.get("question", "")[:200],
                        })
        except Exception:
            continue

    return {"ups": ups, "downs": downs, "recent_downs": recent_downs[-10:]}


def get_kv_notes_themes() -> list[dict]:
    """Pull recent leader notes (across leaders, anonymized) to surface team patterns."""
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    namespace = os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID", "156baaf858c7465d9e427e2cd7c32707")
    if not token or not account:
        return []

    import urllib.request

    try:
        url = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
               f"/storage/kv/namespaces/{namespace}/keys?prefix=leader:")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        note_keys = [k["name"] for k in data.get("result", []) if ":notes:" in k["name"]]
    except Exception:
        return []

    notes = []
    for key in note_keys[:50]:
        try:
            url = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
                   f"/storage/kv/namespaces/{namespace}/values/{key}")
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                arr = json.loads(resp.read())
            for n in arr[-5:]:
                notes.append({
                    "text": (n.get("text") or "")[:300],
                    "tmName": n.get("tmName") or "",
                })
        except Exception:
            continue
    return notes[-20:]  # cap


def read_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text())
    except Exception:
        return []


def append_log(entry: dict) -> None:
    log = read_log()
    log.append(entry)
    if len(log) > LOG_ENTRIES_KEEP:
        log = log[-LOG_ENTRIES_KEEP:]
    LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def file_excerpt(path: str, max_chars: int = 12000) -> str:
    """Return a file's content, truncated for prompt budget."""
    p = REPO_ROOT / path
    if not p.exists():
        return f"(file not found: {path})"
    text = p.read_text()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... (truncated; full file is {len(text)} chars)"


# ============================================================
# LLM CALL
# ============================================================

SYSTEM = """You are COACH RICK, operating in AUTONOMOUS IMPROVEMENT MODE.

THE MISSION
Build the best AI leadership coaching tool the world has ever seen. Not the best for
junk-removal regions. Not the best for franchise leadership. The best, period.
Wooden, Lombardi, Campbell, Brown — the leaders this tool draws from set a bar.
Your job is to clear it, then keep raising it.

The leader who built this handed you direct commit access because he believes you
can be trusted with the keys. Repay that trust two ways: never break the site, and
never settle for a dashboard that's merely "fine." Every day you should be looking
for the smallest change that moves this tool measurably closer to that bar.

YOUR DAILY LOOP
Read the inputs (recent feedback, leader notes, your past improvement log, and the
current state of the whitelisted files). Pick 0 to 3 SMALL changes that, taken
together, make this tool sharper than it was yesterday. Output a JSON object with
the edits, or an empty edits list if today's signal genuinely doesn't justify one.

A "no change" answer is honest when there's no signal. It is cowardly when there
is signal and you didn't act on it. Pattern-match honestly: a thumbs-down, a
recurring leader question, a stale piece of copy, a prompt that drifts off voice,
a missing scenario quote — those are signals. Act on them.

WHAT GOOD AUTONOMOUS CHANGES LOOK LIKE
- Tightening Rick's voice in chat.js when feedback shows he sounds textbook
- Adding a suggested-prompt chip for a question pattern leaders keep asking
- Sharpening the motivational message prompt so it lands harder
- Adding a missing CSL Scenario quote to the training KB
- Making a leadership-library entry more specific to NEE's reality
- Replacing dead copy on the dashboard with copy that actually helps
- Tuning a coaching narrative template in refresh_dashboard.py for clarity

WHAT YOU MUST NEVER DO (these are non-negotiable safety rails)
- Add new dependencies, new endpoints, new env vars, or new build steps
- Touch authentication, secrets, or API key handling
- Restructure data shapes or contracts (TEAMMATES array, FRANCHISES array, KV schema)
- Modify GitHub Actions workflows
- Change function entry points (onRequest signature, main() signature)
- Add or change any URL/origin
- Make a change you can't justify with a specific feedback signal or principle
- Make stylistic changes for their own sake
- Bundle multiple ideas into one edit; one edit = one focused change

EDITING PROTOCOL
Each edit specifies one file in the whitelist plus an exact string replacement:
{
  "file": "<whitelisted relative path>",
  "find": "<EXACT existing substring; must appear in the file exactly once>",
  "replace": "<new substring; same general role; no protected strings>",
  "why": "<one sentence tying this to a feedback signal or principle>"
}

The 'find' string MUST be unique in the file. If you're not sure it's unique,
include enough surrounding context to make it unique. The system will reject any
edit whose 'find' isn't found exactly once.

RESPECT THE BUDGET
- Maximum 3 edits per run.
- Total combined size of all 'replace' fields must stay under 8000 characters.
- Small, focused, daily compounding > big risky overhauls. The bar gets cleared
  one inch at a time.

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "summary": "<one short line a leader will read in the dashboard log>",
  "edits": [ {file, find, replace, why}, ... ],
  "rationale": "<2-3 sentences naming the feedback signal or pattern that drove today's call>"
}

If you skip today, output: {"summary": "Nothing to change today.", "edits": [], "rationale": "..."}

Now go build the best leadership coaching tool the world has ever seen. One careful
change at a time. Every day.
"""


def call_rick(context_prompt: str) -> dict | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("::error::ANTHROPIC_API_KEY missing", file=sys.stderr)
        return None
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": context_prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        return json.loads(raw)
    except Exception as e:
        print(f"::warning::Rick autonomous call failed: {e}", file=sys.stderr)
        return None


# ============================================================
# VALIDATION GAUNTLET
# ============================================================

def validate_edit(edit: dict, current_files: dict[str, str]) -> tuple[bool, str]:
    """Pre-check an edit before we apply it. Returns (ok, error_msg)."""
    f = edit.get("file")
    find = edit.get("find")
    replace = edit.get("replace")
    why = edit.get("why")

    if not all(isinstance(x, str) and x for x in (f, find, replace, why)):
        return False, "missing or non-string fields"
    if f not in WHITELIST:
        return False, f"file not in whitelist: {f}"

    text = current_files.get(f)
    if text is None:
        return False, f"file not loaded: {f}"

    occurrences = text.count(find)
    if occurrences == 0:
        return False, f"'find' not present in {f}"
    if occurrences > 1:
        return False, f"'find' is ambiguous in {f} ({occurrences} occurrences); needs more context"

    # Denylist check on the replacement
    for bad in DENYLIST_NEW_CONTENT:
        if bad in replace:
            return False, f"replace contains forbidden token: {bad}"

    # Protected patterns must remain after replace
    new_text = text.replace(find, replace, 1)
    for pat in PROTECTED_PATTERNS.get(f, []):
        before = len(re.findall(pat, text))
        after = len(re.findall(pat, new_text))
        if after != before:
            return False, f"protected pattern count changed for {f}: /{pat}/ ({before} -> {after})"

    return True, ""


def syntax_check_python(path: Path) -> tuple[bool, str]:
    try:
        subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                       check=True, capture_output=True, timeout=15)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode("utf-8", "replace")[:500]
    except Exception as e:
        return False, str(e)[:500]


def syntax_check_js(path: Path) -> tuple[bool, str]:
    try:
        out = subprocess.run(["node", "--check", str(path)],
                             check=True, capture_output=True, timeout=15)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode("utf-8", "replace")[:500]
    except FileNotFoundError:
        # Node not available - skip the check rather than fail
        print("::warning::node not available; skipping JS syntax check", file=sys.stderr)
        return True, ""
    except Exception as e:
        return False, str(e)[:500]


def syntax_check_inline_js(html_path: Path) -> tuple[bool, str]:
    """Extract the LAST <script>...</script> block from index.html and run node --check on it.
    Mirrors the live-page syntax check we used when a regression slipped in."""
    text = html_path.read_text()
    scripts = re.findall(r"<script>([\s\S]*?)</script>", text)
    if not scripts:
        return True, ""
    main_script = scripts[-1]
    tmp = REPO_ROOT / ".rick_inline_check.js"
    try:
        # Wrap in a function so top-level await / module-level returns don't break the check
        tmp.write_text("(function(){\n" + main_script + "\n})();\n")
        return syntax_check_js(tmp)
    finally:
        try: tmp.unlink()
        except Exception: pass


def run_validators(changed_files: list[str]) -> tuple[bool, str]:
    for f in changed_files:
        path = REPO_ROOT / f
        if f.endswith(".py"):
            ok, err = syntax_check_python(path)
            if not ok: return False, f"{f}: python syntax: {err}"
        elif f.endswith(".js"):
            ok, err = syntax_check_js(path)
            if not ok: return False, f"{f}: js syntax: {err}"
        elif f.endswith(".html"):
            ok, err = syntax_check_inline_js(path)
            if not ok: return False, f"{f}: inline js syntax: {err}"
    return True, ""


# ============================================================
# SMOKE TEST AFTER DEPLOY
# ============================================================

def smoke_test_live(url: str = "https://nee-coaching.pages.dev/") -> tuple[bool, str]:
    """Pings the deployed page and verifies the inline JS still parses."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
        if r.status != 200:
            return False, f"HTTP {r.status}"
    except Exception as e:
        return False, f"fetch failed: {e}"

    # Inline JS must parse
    scripts = re.findall(r"<script>([\s\S]*?)</script>", body)
    if not scripts:
        return False, "no inline script in deployed page"
    tmp = REPO_ROOT / ".rick_smoke_check.js"
    try:
        tmp.write_text("(function(){\n" + scripts[-1] + "\n})();\n")
        ok, err = syntax_check_js(tmp)
    finally:
        try: tmp.unlink()
        except Exception: pass
    if not ok:
        return False, f"inline js parse failed: {err}"

    # Critical anchors must be present
    for must_have in [
        "id=\"dashboard\"",
        "const TEAMMATES = [",
        "const FRANCHISES = [",
    ]:
        if must_have not in body:
            return False, f"missing required anchor: {must_have}"

    return True, ""


# ============================================================
# MAIN FLOW
# ============================================================

def main() -> int:
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if kill_switch_off():
        print("Kill switch off. Set COACH_RICK_AUTONOMY=on to enable. Exiting.", file=sys.stderr)
        return 0

    # 1. Gather context
    feedback = get_kv_feedback_summary()
    notes = get_kv_notes_themes()
    log = read_log()

    current_files = {f: (REPO_ROOT / f).read_text() for f in WHITELIST if (REPO_ROOT / f).exists()}
    file_excerpts = {f: file_excerpt(f, 9000) for f in current_files.keys()}

    # 2. Build context prompt for Rick
    log_summary = log[-15:] if log else []
    ctx = "INPUTS\n" + "=" * 60 + "\n\n"
    ctx += f"FEEDBACK SUMMARY (across all leaders, last 50 each):\n{json.dumps(feedback, indent=2)}\n\n"
    ctx += f"RECENT LEADER NOTES (anonymized, recent):\n{json.dumps(notes, indent=2, ensure_ascii=False)}\n\n"
    ctx += f"YOUR PAST IMPROVEMENT LOG (most recent {len(log_summary)} runs):\n"
    ctx += json.dumps(log_summary, indent=2, ensure_ascii=False) + "\n\n"
    ctx += "WHITELISTED FILES (current state, full or truncated):\n\n"
    for f, t in file_excerpts.items():
        ctx += f"---- FILE: {f} ----\n{t}\n---- END {f} ----\n\n"
    ctx += "Now produce your improvement JSON for today. Empty edit list is a valid answer."

    # 3. Call Rick
    proposal = call_rick(ctx)
    if not proposal:
        append_log({"started": started, "status": "no_proposal", "summary": "Rick call failed"})
        return 1

    edits = proposal.get("edits") or []
    summary = proposal.get("summary", "(no summary)")
    rationale = proposal.get("rationale", "")
    if len(edits) == 0:
        print(f"Rick chose to make no changes today. Summary: {summary}")
        append_log({
            "started": started, "status": "no_changes",
            "summary": summary, "rationale": rationale,
        })
        commit_log("Rick autonomous: no changes today")
        return 0

    if len(edits) > MAX_EDITS_PER_RUN:
        print(f"::warning::Rick proposed {len(edits)} edits; capping at {MAX_EDITS_PER_RUN}", file=sys.stderr)
        edits = edits[:MAX_EDITS_PER_RUN]

    # Budget guard
    total_replace = sum(len(e.get("replace", "")) for e in edits)
    if total_replace > DIFF_CHAR_BUDGET:
        print(f"::error::diff budget exceeded ({total_replace} > {DIFF_CHAR_BUDGET})", file=sys.stderr)
        append_log({"started": started, "status": "rejected_budget", "summary": summary,
                    "edits_attempted": edits, "rationale": rationale})
        commit_log("Rick autonomous: rejected (budget)")
        return 0

    # 4. Validate each edit
    accepted = []
    rejected = []
    for e in edits:
        ok, err = validate_edit(e, current_files)
        if ok:
            # Apply in-memory so subsequent edits to the same file see the result
            current_files[e["file"]] = current_files[e["file"]].replace(e["find"], e["replace"], 1)
            accepted.append(e)
        else:
            rejected.append({"edit": e, "error": err})
            print(f"::warning::edit rejected: {err}", file=sys.stderr)

    if not accepted:
        append_log({"started": started, "status": "all_rejected", "summary": summary,
                    "rejected": rejected, "rationale": rationale})
        commit_log("Rick autonomous: all edits rejected pre-apply")
        return 0

    # 5. Apply to disk
    for f, content in current_files.items():
        (REPO_ROOT / f).write_text(content)

    # 6. Run validators on every changed file
    changed_files = sorted({e["file"] for e in accepted})
    ok, err = run_validators(changed_files)
    if not ok:
        # Roll back via git
        print(f"::error::validator failed: {err}", file=sys.stderr)
        subprocess.run(["git", "checkout", "--"] + changed_files, cwd=REPO_ROOT, check=False)
        append_log({"started": started, "status": "validator_failed", "summary": summary,
                    "edits": accepted, "validator_error": err, "rationale": rationale})
        if not is_dry_run():
            commit_log("Rick autonomous: validator caught a regression, reverted")
        return 1

    # Dry-run: stop here, revert disk changes, show what would have happened.
    if is_dry_run():
        print("\n=== RICK_DRY_RUN: no commit, no push, no deploy ===")
        print(f"Summary: {summary}")
        print(f"Rationale: {rationale}")
        print(f"Accepted edits ({len(accepted)}):")
        for e in accepted:
            print(f"  - {e['file']}: {e['why']}")
            print(f"      find:    {e['find'][:80]!r}")
            print(f"      replace: {e['replace'][:80]!r}")
        if rejected:
            print(f"Rejected edits ({len(rejected)}):")
            for r in rejected:
                print(f"  - {r['edit'].get('file')}: {r['error']}")
        # Restore the working tree
        subprocess.run(["git", "checkout", "--"] + changed_files, cwd=REPO_ROOT, check=False)
        return 0

    # 7. Commit + push
    commit_msg = f"Coach Rick (autonomous): {summary[:100]}"
    subprocess.run(["git", "config", "user.name", "coach-rick-bot"], cwd=REPO_ROOT, check=False)
    subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], cwd=REPO_ROOT, check=False)
    subprocess.run(["git", "add"] + changed_files, cwd=REPO_ROOT, check=False)
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_ROOT, check=False)

    # Append log entry, commit it too
    append_log({
        "started": started,
        "status": "applied",
        "summary": summary,
        "rationale": rationale,
        "edits": [{"file": e["file"], "why": e["why"]} for e in accepted],
        "rejected": rejected,
    })
    commit_log("Rick autonomous: log update")

    # Push with retry-on-conflict
    pushed = False
    for attempt in range(1, 6):
        if subprocess.run(["git", "push"], cwd=REPO_ROOT).returncode == 0:
            pushed = True
            break
        print(f"push attempt {attempt} failed; rebasing", file=sys.stderr)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=REPO_ROOT, check=False)
        time.sleep(2)
    if not pushed:
        print("::error::push failed after 5 attempts", file=sys.stderr)
        return 1

    # 8. Smoke test the deployed page (give Cloudflare a moment to propagate)
    time.sleep(20)
    ok, err = smoke_test_live()
    if not ok:
        print(f"::error::smoke test failed: {err}. Reverting.", file=sys.stderr)
        # Auto-revert the change commit (HEAD is now the log commit; HEAD~1 is the change)
        subprocess.run(["git", "revert", "--no-edit", "HEAD~1"], cwd=REPO_ROOT, check=False)
        for attempt in range(1, 6):
            if subprocess.run(["git", "push"], cwd=REPO_ROOT).returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=REPO_ROOT, check=False)
            time.sleep(2)
        append_log({"started": started, "status": "auto_reverted", "summary": summary,
                    "smoke_error": err})
        commit_log("Rick autonomous: smoke test failed, auto-reverted")
        return 1

    print(f"Rick autonomous: applied {len(accepted)} edits. Summary: {summary}")
    return 0


def commit_log(msg: str) -> None:
    """Stage and commit the improvement log if it changed. No-op if clean.
    In dry-run mode, never commits — preserves zero-side-effect contract."""
    if is_dry_run():
        return
    subprocess.run(["git", "add", str(LOG_PATH.relative_to(REPO_ROOT))], cwd=REPO_ROOT, check=False)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
    if diff.returncode != 0:
        subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT, check=False)


if __name__ == "__main__":
    sys.exit(main())
