# attacker-agent (Python)

An adaptive red-team agent for the **Chungus Assistant ("Chip")**, ported from the Week-3 attacker lab.
It runs an autonomous campaign against a *local* target, judges each attempt with deterministic canaries,
remembers what works, then verifies and promotes confirmed findings into a promptfoo regression suite.

Everything targets **your own localhost only.** See [rules-of-engagement.md](rules-of-engagement.md).

## Loop

```
Wake → Orient → Plan → Attack → Judge → Reinforce        (attacker.py, one lap = one episode)
Reproduce 3× → Gate → Verdict → Promote                  (verify.py)
```

- **Planner** (`lib/planner.py`) — UCB1 picks which attack *family* to spend the next attempt on. Code, not vibes.
- **Strategies** (`lib/strategies.py`, `lib/profiles/`) — per-family opening message, escalation ladder, and goal.
- **Attacker brain** (`lib/llm.py`, optional) — writes the next message itself when the canned framing is refused.
- **Judge** (`lib/judge.py`, `lib/profiles/`) — deterministic canaries + tool-action flags decide a hit.
- **Memory** (`lib/memory.py`) — `campaign/` holds the register, journal, decision trace, findings, regressions.

## Setup

Requires **Python 3.10+**. No third-party packages (standard library only).

```bash
cp .env.example .env      # already set to the Chungus profile on :8090
# optionally add an ATTACKER_LLM_* model to make the agent adaptive (see .env.example)
```

## Run

Start the target first (in `../chungus-assistant`): `python3 server.py` (listens on :8090).

Then use the `./attack` launcher:

```bash
./attack start       # Day 5 — run the campaign, write candidate findings  (= python3 attacker.py)
./attack verify      # Day 6 — reproduce 3×, gate, and promote confirmed findings  (= python3 verify.py)
./attack health      # check the target is up
./attack clean       # delete the campaign/ workspace
```

The plain scripts still work (`python3 attacker.py`, `python3 verify.py`) if you prefer.

Tuning knobs (`EPISODES`, `MAX_TURNS`, `ATTACK_DELAY_MS`, `REPRO_RUNS`, …) are env vars — pass them through
the launcher, e.g. `EPISODES=3 ./attack start`. See `.env.example`.

## Targets

`TARGET_PROFILE=chungus` (the default in `.env.example`) attacks Chip on :8090 with the Chungus playbook and
canaries. With `TARGET_PROFILE` unset, the agent falls back to a Week-2 MerciBank target on :8080.

## What is NOT auto-graded

Chip's "no offensive content" guardrail needs an llm-rubric, not a string match, so it is intentionally left
out of the deterministic canary pack. The campaign is decided by canaries; the rubric is only a second opinion.
