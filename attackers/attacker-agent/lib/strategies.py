# strategies.py — loads the attacker playbook for the ACTIVE target. The registry (targets.json) names a
# strategy module per target; target.py resolves it to STRATEGY_MODULE and this file imports its STRATEGIES.
#
# Each strategy is ONE attack family: an opening message, follow-ups to ESCALATE with if the opener is
# refused, and the GOAL (which canary/flag in the target's manifest proves it worked). The escalation
# ladder is what makes this an *agent*; with an attacker model (llm.py) it writes its own follow-ups.
#
# families group strategies for the UCB planner (planner.py) — explore/exploit is chosen per family.
import importlib

from .target import STRATEGY_MODULE

_mod = importlib.import_module(f"lib.profiles.{STRATEGY_MODULE}")
STRATEGIES = _mod.STRATEGIES

# Preserve first-seen order while de-duplicating families.
FAMILIES = list(dict.fromkeys(s["family"] for s in STRATEGIES))


def by_family(family):
    return [s for s in STRATEGIES if s["family"] == family]


def by_id(strategy_id):
    return next((s for s in STRATEGIES if s["id"] == strategy_id), None)
