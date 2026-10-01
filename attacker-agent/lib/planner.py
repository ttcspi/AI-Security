# planner.py — the explore/exploit brain, as DETERMINISTIC CODE. The attacker LLM proposes wording;
# the PLANNER decides which family to spend the next attempt on. This is the "scripts own the math, the
# model proposes" rule from the AI Audit Service — so the agent's choices are auditable, not vibes.
#
# Algorithm: UCB1 (Upper Confidence Bound). For each attack family we track pulls (tries) and wins.
#   score(family) = winRate + C * sqrt( ln(totalPulls) / pulls )
# Untried families score Infinity, so we EXPLORE everything once, then EXPLOIT what pays off while still
# occasionally revisiting the rest. C (default sqrt(2)) is the explore/exploit knob.
import math
import os
from datetime import datetime, timezone

C = float(os.environ.get("UCB_C", math.sqrt(2)))


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pick_family(register, families):
    stats = register.get("families") or {}
    total = sum((stats.get(f) or {}).get("pulls", 0) for f in families)
    best, best_score = None, -math.inf
    scores = {}
    for f in families:
        pulls = (stats.get(f) or {}).get("pulls", 0)
        wins = (stats.get(f) or {}).get("wins", 0)
        score = math.inf if pulls == 0 else (wins / pulls) + C * math.sqrt(math.log(total or 1) / pulls)
        scores[f] = {"pulls": pulls, "wins": wins, "score": score}
        if score > best_score:
            best_score, best = score, f
    return {"family": best, "score": best_score, "scores": scores}


def record(register, family, won):
    """After an attempt, fold the result back in. Returns the updated register (caller persists it)."""
    register.setdefault("families", {})
    s = register["families"].setdefault(family, {"pulls": 0, "wins": 0})
    s["pulls"] += 1
    if won:
        s["wins"] += 1
    register["updatedAt"] = _now()
    return register


def summarize(register, families):
    """A small human-readable table of what the planner has learned so far."""
    stats = register.get("families") or {}
    rows = [
        {"family": f, "pulls": (stats.get(f) or {}).get("pulls", 0), "wins": (stats.get(f) or {}).get("wins", 0)}
        for f in families
    ]
    rows.sort(key=lambda r: (r["wins"], r["pulls"]), reverse=True)
    return rows
