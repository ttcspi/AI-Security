# target.py — the adapter that talks to the agent under test.
# This is the ONLY place that knows the target's HTTP envelope. Everything else calls Conversation.say().
#
# It mirrors the Week-2 shape: POST /v1/chat/completions, a bearer token, a JSON body, and a non-OpenAI
# reply at reply.text. Multi-turn works by passing the SAME session_id back.
#
# Rules of engagement: the target URL must point at YOUR OWN local agent (localhost only).
# Nothing else. See rules-of-engagement.md.
import json
import os
import re
import time
import urllib.error
import urllib.request

# TARGET_PROFILE=chungus points the adapter at the local Chungus Assistant (same envelope).
# The default profile is the Week-2 Chungus Bank target. Chungus is the one this project iterates on.
CHUNGUS = os.environ.get("TARGET_PROFILE") == "chungus"
if CHUNGUS:
    TARGET_URL = os.environ.get("CHUNGUS_TARGET_URL", "http://localhost:8090/v1/chat/completions")
    TARGET_KEY = os.environ.get("CHUNGUS_TARGET_KEY", "chungus-lab-key")
    TARGET_MODEL = "chungus-assistant"
else:
    TARGET_URL = os.environ.get("CHUNGUS_BANK_TARGET_URL", "http://localhost:8080/v1/chat/completions")
    TARGET_KEY = os.environ.get("CHUNGUS_BANK_TARGET_KEY", "chungus-bank-lab-key")
    TARGET_MODEL = "chungus-bank-assistant"

if not re.match(r"^https?://(localhost|127\.0\.0\.1)(:|/)", TARGET_URL):
    print(f'\n  REFUSING: target URL is "{TARGET_URL}".')
    print("  This lab attacks your OWN local agent only (localhost). See rules-of-engagement.md.\n")
    raise SystemExit(1)


def sleep(ms: float) -> None:
    time.sleep(ms / 1000)


def _post(messages, session_id):
    """One HTTP call to the target. Retries politely on the target's 429 rate limit (Retry-After)."""
    for _ in range(6):
        body = json.dumps({"model": TARGET_MODEL, "messages": messages, "session_id": session_id}).encode()
        req = urllib.request.Request(
            TARGET_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {TARGET_KEY}"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                text = resp.read().decode()
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
            if status == 429:
                wait = float(e.headers.get("retry-after") or 2)
                sleep((wait + 0.2) * 1000)
                continue
            text = e.read().decode(errors="replace")
            try:
                err = json.loads(text).get("error", {}).get("message")
            except json.JSONDecodeError:
                err = text[:200]
            raise RuntimeError(f"target {status}: {err or text[:200]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"target returned non-JSON ({status}): {text[:200]}")
    raise RuntimeError("target stayed rate-limited after several retries — slow down (raise ATTACK_DELAY_MS)")


class Conversation:
    """A conversation you can carry across turns. Each Conversation keeps one session_id, so the target
    remembers earlier turns — that is what makes multi-turn (crescendo-style) attacks possible."""

    def __init__(self):
        self.session_id = None
        self.turns = []

    def say(self, user_text):
        # The target derives context from its own server-side session history, so we send only the new turn.
        data = _post([{"role": "user", "content": user_text}], self.session_id)
        self.session_id = data.get("session_id") or self.session_id
        reply = (data.get("reply") or {}).get("text", "")
        turn = {
            "user": user_text,
            "reply": reply,
            "toolCalls": data.get("tool_calls") or [],
            "retrieved": data.get("retrieved") or [],
            "findingsHint": data.get("findings_hint") or {},
            "traceId": data.get("trace_id"),
            "sessionId": self.session_id,
        }
        self.turns.append(turn)
        return turn


def health():
    """A one-shot health check so a run fails fast with a clear message instead of a wall of errors."""
    base = re.sub(r"/v1/.*$", "", TARGET_URL)
    with urllib.request.urlopen(f"{base}/health") as resp:
        if resp.status != 200:
            raise RuntimeError(f"health {resp.status}")
        return json.loads(resp.read().decode())  # { ok, model, hasKey }


# Display names + startup hints for the selected target, so logs and the attacker prompt name the right bot.
if CHUNGUS:
    target_info = {
        "url": TARGET_URL,
        "name": "Chungus Assistant",
        "bot": "Chip",
        "startHint": "Start it in the chungus-assistant folder with `python3 server.py`.",
        "keyHint": "put CHUNGUS_LLM_API_KEY in chungus-assistant/.env.",
    }
else:
    target_info = {
        "url": TARGET_URL,
        "name": "Chungus Bank",
        "bot": "Chungus Bank",
        "startHint": "Start it in ../week2-chungus-bank with `npm start`.",
        "keyHint": "put CHUNGUS_BANK_LLM_API_KEY in ../week2-chungus-bank/.env.",
    }
