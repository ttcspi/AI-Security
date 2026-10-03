#!/usr/bin/env python3
# attacker.py — DAY 5: the attacker agent. It runs a campaign against the live target agent:
#
#   Wake -> Orient -> Plan -> Attack -> Judge -> Reinforce   (one lap = one "episode")
#
# The planner (UCB, code) picks which attack family to try; the agent opens with a canned message and, if
# the target refuses, ESCALATES — writing its own next message if you gave it an attacker model (lib/llm.py),
# otherwise walking a static ladder. The judge (deterministic canaries, code) says whether it worked, and
# the result is written to memory so the next lap is smarter. Candidates land in campaign/findings/ for
# Day 6 to verify.
#
#   Terminal 1:  (the target)   python3 server.py   (in ../chungus-assistant)
#   Terminal 2:  (here)          python3 attacker.py
#
# Everything targets YOUR localhost agent only. See rules-of-engagement.md.
import os
import sys
from datetime import datetime, timezone

import lib.env  # noqa: F401 — side-effect import loads .env FIRST
import lib.llm as llm
import lib.memory as mem
from lib.judge import impact_of, judge
from lib.planner import pick_family, record, summarize
from lib.strategies import FAMILIES, STRATEGIES, by_family
from lib.target import Conversation, TransportError, health, sleep, target_info

EPISODES = int(os.environ.get("EPISODES", 9))
MAX_TURNS = int(os.environ.get("MAX_TURNS", 4))
DELAY = float(os.environ.get("ATTACK_DELAY_MS", 600))
MAX_TRANSPORT_FAILS = int(os.environ.get("MAX_TRANSPORT_FAILS", 3))  # consecutive before we stop


class _C:
    def g(self, s): return f"\x1b[32m{s}\x1b[0m"
    def r(self, s): return f"\x1b[31m{s}\x1b[0m"
    def y(self, s): return f"\x1b[33m{s}\x1b[0m"
    def b(self, s): return f"\x1b[36m{s}\x1b[0m"
    def dim(self, s): return f"\x1b[2m{s}\x1b[0m"
    def bold(self, s): return f"\x1b[1m{s}\x1b[0m"


c = _C()


def line():
    print(c.dim("─" * 78))


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def attack(strategy, ep):
    """Attack ONE strategy in one episode: open, judge, escalate up to MAX_TURNS, judge again."""
    convo = Conversation()
    turns_sent = 0

    for t in range(MAX_TURNS):
        # Decide the next message: scripted strategies follow their sequence; others escalate (LLM or ladder).
        if t == 0:
            nxt, source = strategy["opening"], "opening"
        elif strategy.get("scripted"):
            followups = strategy.get("followups", [])
            nxt = followups[t - 1] if t - 1 < len(followups) else None
            source = "scripted"
        else:
            written = llm.mutate(strategy, convo)
            followups = strategy.get("followups", [])
            ladder = followups[t - 1] if t - 1 < len(followups) else None
            nxt = written or ladder
            source = "attacker-llm" if written else ("ladder (llm failed)" if llm.available() else "ladder")

        if nxt is None:
            mem.trace({"ep": ep, "step": "stop", "strategy": strategy["id"], "reason": "out of escalations"})
            break

        sys.stdout.write(c.dim("    → you: ") + nxt[:96] + ("…" if len(nxt) > 96 else "") + "\n")
        try:
            turn = convo.say(nxt)
        except TransportError as e:
            # We could not reach the target. That is not a miss — it is no result at all.
            mem.trace({"ep": ep, "step": "transport", "strategy": strategy["id"], "turn": t + 1, "reason": str(e)})
            return {"hit": False, "transport": True, "reason": str(e), "convo": convo, "turnsSent": turns_sent}
        turns_sent += 1
        sys.stdout.write(c.dim(f"    ← {target_info['bot'].lower()}: ") + " ".join(str(turn["reply"]).split())[:96] + "…\n")
        sleep(DELAY)

        verdict = judge(convo, strategy["goal"])
        mem.trace(
            {
                "ep": ep, "step": "turn", "strategy": strategy["id"], "turn": t + 1, "source": source, "sent": nxt,
                "reply": str(turn["reply"])[:300], "tools": [x.get("name") for x in (turn.get("toolCalls") or [])],
                "verdict": f"{verdict['kind']}: {verdict['evidence']}" if verdict["hit"] else "no leak yet",
            }
        )
        if verdict["hit"]:
            return {"hit": True, "verdict": verdict, "convo": convo, "turnsSent": turns_sent}
        # scripted sequences send every turn; free escalation stops when the ladder/LLM is exhausted
        if strategy.get("scripted") and t >= len(strategy.get("followups", [])):
            break
    return {"hit": False, "convo": convo, "turnsSent": turns_sent}


def main():
    print(c.bold(f"\n  {target_info['name']} attacker agent — Day 5 campaign"))
    attacker_model = c.g(llm.info()["model"]) if llm.available() else c.y("none (static ladders)")
    print(c.dim(f"  target: {target_info['url']}   attacker-model: {attacker_model}"))

    # WAKE — fail fast if the target isn't up, and load memory.
    try:
        h = health()
    except Exception:  # noqa: BLE001
        print(c.r(f"\n  {target_info['name']} is not answering on /health. {target_info['startHint']}\n"))
        raise SystemExit(1)
    if not h.get("hasKey"):
        print(c.r(f"\n  {target_info['name']} is up but has no model key — {target_info['keyHint']}\n"))
        raise SystemExit(1)
    print(c.dim(f"  woke up · {target_info['name']} model = {h.get('model')}\n"))

    register = mem.load_register()
    done = set()  # strategies fully attempted (found or exhausted)
    found = []
    consecutive_transport = 0  # network blips in a row; stop the run if the target drops out
    mem.journal(
        f"campaign start · target model {h.get('model')} · attacker "
        f"{llm.info()['model'] if llm.available() else 'static'}"
    )

    for ep in range(1, EPISODES + 1):
        # ORIENT
        remaining = [s for s in STRATEGIES if s["id"] not in done]
        if not remaining:
            print(c.dim("  (every strategy attempted — stopping early)"))
            break

        # PLAN — UCB picks a family; take its first not-yet-done strategy (fall back across families).
        live_families = [f for f in FAMILIES if any(s["id"] not in done for s in by_family(f))]
        picked = pick_family(register, live_families)
        family = picked["family"]
        strategy = next((s for s in by_family(family) if s["id"] not in done), remaining[0])
        mem.trace(
            {"ep": ep, "step": "plan", "picked": family, "strategy": strategy["id"], "goal": strategy["goal"],
             "scores": picked["scores"]}
        )

        line()
        print(f"  {c.bold('episode ' + str(ep))}  {c.dim('plan→')} family {c.b(strategy['family'])}  "
              f"{c.dim('strategy→')} {c.bold(strategy['id'])}")
        print(c.dim(f"  {strategy['title']}  [{strategy['owaspLLM']}]"))

        # ATTACK + JUDGE
        try:
            result = attack(strategy, ep)
        except Exception as e:  # noqa: BLE001
            print(c.r(f"  attack error: {e}"))
            done.add(strategy["id"])
            continue

        # TRANSPORT — the target was unreachable. Leave the strategy OPEN and teach the planner
        # nothing: a network failure is not evidence either way. Stop if it keeps happening.
        if result.get("transport"):
            consecutive_transport += 1
            print(c.y(f"  … transport error — {result['reason']}") +
                  c.dim(f"  (left {strategy['id']} open, not scored)"))
            mem.journal(f"TRANSPORT {strategy['id']} ({strategy['goal']}) — {result['reason']}")
            if consecutive_transport >= MAX_TRANSPORT_FAILS:
                print(c.r(f"\n  {MAX_TRANSPORT_FAILS} transport failures in a row — is {target_info['name']} "
                          f"still up? Stopping so nothing is wrongly scored as a miss.\n"))
                break
            sleep(DELAY)
            continue
        consecutive_transport = 0

        # REINFORCE — update the planner, memory, and (on a hit) write a candidate finding.
        record(register, strategy["family"], result["hit"])
        mem.save_register(register)
        mem.trace(
            {"ep": ep, "step": "outcome", "strategy": strategy["id"], "family": strategy["family"],
             "hit": result["hit"], "turns": result["turnsSent"], "familyNow": register["families"][strategy["family"]]}
        )
        done.add(strategy["id"])

        if result["hit"]:
            v = result["verdict"]
            print(c.g(f"  ✓ HIT — {v['label']}") + c.dim(f"  ({v['kind']}: {v['evidence']})"))
            finding = {
                "id": strategy["id"], "status": "CANDIDATE", "title": strategy["title"], "category": strategy["family"],
                "goal": strategy["goal"], "owaspLLM": strategy["owaspLLM"], "owaspASI": strategy.get("owaspASI"),
                "aivssHint": strategy.get("aivssHint"), "impact": impact_of(strategy["goal"]),
                "evidence": v["evidence"], "evidenceKind": v["kind"], "foundAt": _now(),
                "turnsToHit": result["turnsSent"],
                "transcript": [
                    {"user": t["user"], "reply": t["reply"], "toolCalls": t["toolCalls"], "findingsHint": t["findingsHint"]}
                    for t in result["convo"].turns
                ],
                "evidence_ladder": "claimed",
            }
            mem.save_finding(finding)
            mem.journal(f"HIT {strategy['id']} ({strategy['goal']}) in {result['turnsSent']} turns — candidate saved")
            found.append(strategy["id"])
        else:
            print(c.y(f"  ✗ held — {target_info['name']} did not leak {strategy['goal']} in {result['turnsSent']} turns"))
            mem.lesson({"strategy": strategy["id"], "goal": strategy["goal"], "note": f"held after {result['turnsSent']} turns"})
            mem.journal(f"MISS {strategy['id']} ({strategy['goal']}) after {result['turnsSent']} turns")
        sleep(DELAY)

    # Summary — what the planner learned, and what to verify tomorrow.
    line()
    print(c.bold("\n  campaign summary"))
    for row in summarize(register, FAMILIES):
        wins = c.g(row["wins"]) if row["wins"] else row["wins"]
        print(f"   {row['family']:<18} {c.dim('tries')} {row['pulls']}  {c.dim('wins')} {wins}")
    print(f"\n  {c.bold('candidates found:')} {c.g(', '.join(found)) if found else c.y('none this run')}")
    print(c.dim(f"  written to {mem.paths['FINDINGS']}/"))
    print(c.dim("  next: python3 verify.py   → reproduce 3× in parallel, gate, and promote to promptfoo\n"))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(c.r(f"fatal: {e}"))
        raise SystemExit(1)
