# Targets

Each subdirectory is a **self-contained, deliberately-vulnerable LLM app** used as a test subject. They are
independent apps that happen to speak the same HTTP contract, so one attacker can hit any of them.

| Target         | Port | What it is                                  |
|----------------|------|---------------------------------------------|
| `chungus-hr`   | 8090 | Chungus HR Assistant ("Chip")               |
| `chungus-bank` | 8080 | Chungus Bank retail-banking assistant       |

Run one with: `cd <target> && python3 server.py` (copy `.env.example` → `.env` and set a model key first).

## The contract every target honors

An attacker (or promptfoo) talks to a target through this envelope. Honor it and your target is attackable
with **zero** attacker changes.

- `GET /health` → `{ "ok": true, "model": "...", "hasKey": true|false }`
- `POST /v1/chat/completions`
  - Auth: `Authorization: Bearer <target key>`
  - Body: `{ "model": "...", "messages": [{ "role": "user", "content": "..." }], "session_id": "<optional>" }`
  - Reply (note: **not** OpenAI-shaped):
    ```json
    {
      "session_id": "sess_...",        // echo back to continue a multi-turn conversation
      "trace_id": "trc_...",
      "reply": { "text": "assistant text" },
      "tool_calls": [{ "name": "...", "args": {} }],
      "findings_hint": { "<flagKey>": <value> },   // server-reported forbidden actions
      "retrieved": ["doc-id", ...]
    }
    ```
- Rate limit: respond `429` with `Retry-After` when over budget.

## The manifest

Each target also ships a `manifest.json` — its **ground truth** for the attacker's deterministic judge:
connection (url/port/model/key env + default) plus `canaries` (strings that must never appear in a reply),
`flags` (which `findings_hint` keys map to which goal), and `impacts` (severity per goal). The target owns
this file because the target is what plants the data. The attacker reads it via its `targets.json` registry.

## Adding a target

1. New folder here with a `server.py` honoring the contract above, its data, and `.env.example`.
2. A `manifest.json` declaring its connection + canaries/flags/impacts.
3. In `attackers/attacker-agent/`: a strategy module `lib/profiles/<name>_strategies.py` and one entry in
   `targets.json` tying the name to the manifest + strategy module.

No attacker code changes — just data.
