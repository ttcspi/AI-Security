# memory.py — the engagement's memory, as plain files (auditable, diffable, cheap). Same idea as the AI
# Audit Service's per-engagement workspace: a strategy register (what pays off), a journal (what happened),
# a findings folder (candidates + confirmed/rejected), and a lessons log (dead ends, so we don't re-walk them).
#
#   campaign/
#     strategy-register.json   win/loss per family (the planner's brain)
#     session-journal.md       human-readable timeline of the campaign
#     lessons.jsonl            one line per dead end: "this framing didn't work"
#     decision-trace.jsonl     one line per decision (plan / turn / outcome) — watch a run live
#     findings/<ID>.json       a candidate finding (Day 5) -> CONFIRMED/REJECTED (Day 6)
#     findings/rejected/<ID>.json
#     regression/<ID>.gen.yaml a promptfoo regression case (Day 6 promote)
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
DIR = Path(os.environ.get("CAMPAIGN_DIR") or (LAB / "campaign"))
FINDINGS = DIR / "findings"
REJECTED = FINDINGS / "rejected"
REGRESSION = DIR / "regression"


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure():
    for d in (DIR, FINDINGS, REJECTED, REGRESSION):
        d.mkdir(parents=True, exist_ok=True)


def _reg_path():
    return DIR / "strategy-register.json"


def load_register():
    _ensure()
    try:
        return json.loads(_reg_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {"families": {}, "createdAt": _now()}


def save_register(reg):
    _ensure()
    _reg_path().write_text(json.dumps(reg, indent=2))


def journal(line):
    _ensure()
    with (DIR / "session-journal.md").open("a") as f:
        f.write(f"- {_now()} — {line}\n")


def lesson(obj):
    _ensure()
    with (DIR / "lessons.jsonl").open("a") as f:
        f.write(json.dumps({"at": _now(), **obj}) + "\n")


def trace(obj):
    """One line per decision the agent makes (plan / turn / outcome) — for watching a run live."""
    _ensure()
    with (DIR / "decision-trace.jsonl").open("a") as f:
        f.write(json.dumps({"at": _now(), **obj}) + "\n")


def save_finding(finding):
    _ensure()
    target_dir = REJECTED if finding.get("status") == "REJECTED" else FINDINGS
    (target_dir / f"{finding['id']}.json").write_text(json.dumps(finding, indent=2))


def load_candidates():
    _ensure()
    out = []
    for p in sorted(FINDINGS.glob("*.json")):
        out.append(json.loads(p.read_text()))
    return out


def save_regression(finding_id, yaml_text):
    _ensure()
    p = REGRESSION / f"{finding_id}.gen.yaml"
    p.write_text(yaml_text)
    return p


paths = {"DIR": DIR, "FINDINGS": FINDINGS, "REJECTED": REJECTED, "REGRESSION": REGRESSION}
