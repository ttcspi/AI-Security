# attacker-agent (Python)

An adaptive red-team agent for the local **Chungus** targets. It runs an autonomous campaign against a
*local* target, judges each attempt with deterministic canaries + tool-action flags, remembers what works,
then verifies and promotes confirmed findings into a promptfoo regression suite.

It is **target-agnostic**: it reads a `targets.json` registry, picks a target by name, and loads that
target's `manifest.json` (ground truth) plus a per-target strategy pack. Adding a target needs no code here.

Everything targets **your own localhost only.** See [rules-of-engagement.md](rules-of-engagement.md).

## Loop

```
Wake → Orient → Plan → Attack → Judge → Reinforce        (attacker.py, one lap = one episode)
Reproduce 3× → Gate → Verdict → Promote                  (verify.py)
```

- **Registry** (`targets.json`) — maps a target NAME → its manifest + strategy module.
- **Target adapter** (`lib/target.py`) — resolves the active target (env `TARGET`, default in the registry).
- **Planner** (`lib/planner.py`) — UCB1 picks which attack *family* to spend the next attempt on.
- **Strategies** (`lib/profiles/<target>_strategies.py`) — per-family opening message, escalation ladder, goal.
- **Attacker brain** (`lib/llm.py`, optional) — writes the next message itself when a canned framing is refused.
- **Judge** (`lib/judge.py`) — deterministic; canaries + flags come from the target's `manifest.json`.
- **Memory** (`lib/memory.py`) — `campaign/` holds the register, journal, decision trace, findings, regressions.

## Setup

Requires **Python 3.10+**. No third-party packages (standard library only).

```bash
cp .env.example .env      # select the target with TARGET=<name> (default: chungus-hr)
# optionally add an ATTACKER_LLM_* model to make the agent adaptive (see .env.example)
```

## Run

Start the target(s) first (see `../../targets/`), then use the `./attack` launcher:

```bash
./attack list                  # registered targets (from targets.json)
./attack start [<target>]      # run a campaign (default target, or a named one)
./attack start --all           # run against EVERY registered target
./attack verify [<target>]     # reproduce 3×, gate, and promote confirmed findings
./attack health [<target>]     # check a target is up ( --all for every target )
./attack clean [<target>]      # delete the campaign workspace
```

`<target>` is a name from `targets.json` (`chungus-hr`, `chungus-bank`); omit it to use the default or the
`TARGET` in `.env`. `--all` writes each campaign to its own `campaign-<target>/` dir.

The plain scripts still work (`TARGET=chungus-bank python3 attacker.py`). Tuning knobs (`EPISODES`,
`MAX_TURNS`, `ATTACK_DELAY_MS`, `REPRO_RUNS`, …) are env vars, e.g. `EPISODES=3 ./attack start chungus-bank`.

## Targets

| Target         | Port | Strategy pack                         |
|----------------|------|---------------------------------------|
| `chungus-hr`   | 8090 | `lib/profiles/chungus_hr_strategies`  |
| `chungus-bank` | 8080 | `lib/profiles/chungus_bank_strategies`|

## What is NOT auto-graded

The "no offensive content" guardrail needs an llm-rubric, not a string match, so it is intentionally left
out of the deterministic canary pack. The campaign is decided by canaries/flags; the rubric is a second opinion.
