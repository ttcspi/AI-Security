# AI-Security

A small lab for red-teaming LLM-based apps: a set of deliberately-vulnerable **targets** and the
**attackers** that probe them. Everything runs locally; see each attacker's rules-of-engagement.

```
AI-Security/
├── targets/                 # the apps under attack (self-contained, one port each)
│   ├── chungus-hr/          #   Chungus HR Assistant "Chip"      :8090
│   ├── chungus-bank/        #   Chungus Bank assistant           :8080
│   └── README.md            #   the HTTP contract every target honors + how to add one
└── attackers/
    └── attacker-agent/      # adaptive campaign agent (planner + judge + verify/promote)
```

## Design

- **Targets are self-contained apps** that speak one shared HTTP contract (`targets/README.md`). Each ships
  a `manifest.json` — its ground truth (canaries, forbidden-action flags, impact tiers) — because the
  target is what plants the data.
- **The attacker is generic.** It reads a `targets.json` registry to pick a target by name and loads that
  target's manifest + a per-target strategy pack. Adding a target is data, not attacker code.

## Quick start

```bash
# 1) start one or more targets (set a model key in each target's .env first)
cd targets/chungus-hr   && cp .env.example .env && python3 server.py   # :8090
cd targets/chungus-bank && cp .env.example .env && python3 server.py   # :8080

# 2) attack them
cd attackers/attacker-agent
./attack list                     # registered targets
./attack start chungus-hr         # one target
./attack start --all              # every registered target
./attack verify chungus-hr        # reproduce + promote findings
```
