# Rules of Engagement — attacker-agent

The rule that separates a security engineer from an attacker: **no written authorization, no test.**
This document is your authorization for this project, and it is narrow on purpose.

## Authorization
You are authorized to run this attacker agent against **the Chungus Assistant lab target you run on your own
machine**, for the purpose of learning and practicing agentic red-teaming.

## In scope
- **Only** your own local Chungus Assistant at `http://localhost:8090` (the `../chungus-assistant` target).
- The attacker agent (`attacker.py`, `verify.py`) and its `campaign/` workspace on your machine.

## Out of scope (never)
- Any other host, port, or network — the target adapter (`lib/target.py`) refuses any non-localhost URL.
- Anyone else's machine, any shared infra, or any real service.
- Pointing the **attacker model** (`ATTACKER_LLM_*`) at anything other than your own model endpoint, and
  pointing it or the target at any real system.

## Limits
- All data is fictional. There is nothing real to exfiltrate — you are proving *capability*, not stealing.
- Keep under the target's rate limit (raise `ATTACK_DELAY_MS` if you see HTTP 429).
- Attack traffic against a **commercial** model key can get it flagged — this is why the attacker model can
  be a **local** open model (Ollama / LM Studio) or a red-team-tuned model. Keep it local when in doubt.

## Kill switch
- Stop the attacker: `Ctrl-C`.
- Stop the target: `Ctrl-C` in the Chungus Assistant terminal.

## Evidence handling
- Findings, transcripts, and canary values live in `campaign/` on your machine. Do not paste canary values
  or transcripts outside your own notes. Screenshots for your write-up are fine.
