# target.py — the adapter that talks to the agent under test, and the single place that resolves WHICH
# target is active. Selection is data-driven:
#
#   targets.json (attacker-side registry)  ->  name -> {manifest path, strategy module}
#   <target>/manifest.json (target-side)   ->  connection (url/model/key) + canaries/flags/impacts
#
# Pick a target with the TARGET env var (default: the registry's "default"), e.g.  TARGET=chungus-bank.
# Everything else (strategies.py, judge.py, promote.py) reads what this module resolves, so adding a target
# never touches code — just a folder, a manifest, a strategy module, and one registry line.
#
# Rules of engagement: the resolved URL must be localhost. Nothing else. See rules-of-engagement.md.
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the attacker-agent dir
REGISTRY = json.loads((ROOT / "targets.json").read_text())

ACTIVE = os.environ.get("TARGET") or REGISTRY.get("default")
_targets = REGISTRY.get("targets", {})
if ACTIVE not in _targets:
    raise SystemExit(
        f"\n  Unknown TARGET={ACTIVE!r}. Known targets: {', '.join(_targets)}.\n"
        f"  Set TARGET=<name> or edit targets.json.\n"
    )

_entry = _targets[ACTIVE]
MANIFEST = json.loads((ROOT / _entry["manifest"]).resolve().read_text())
STRATEGY_MODULE = _entry["strategies"]  # read by strategies.py

TARGET_URL = os.environ.get(MANIFEST.get("url_env", ""), MANIFEST["url"])
TARGET_KEY = os.environ.get(MANIFEST["key_env"], MANIFEST["key_default"])
TARGET_MODEL = MANIFEST["model"]

if not re.match(r"^https?://(localhost|127\.0\.0\.1)(:|/)", TARGET_URL):
    print(f'\n  REFUSING: target URL for "{ACTIVE}" is "{TARGET_URL}".')
    print("  This lab attacks your OWN local agents only (localhost). See rules-of-engagement.md.\n")
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


# Display names + startup hints for the active target, so logs and the attacker prompt name the right bot.
target_info = {
    "target": ACTIVE,
    "url": TARGET_URL,
    "name": MANIFEST["name"],
    "bot": MANIFEST["bot"],
    "startHint": MANIFEST.get("start_hint", ""),
    "keyHint": MANIFEST.get("key_hint", ""),
}


def all_targets():
    """Every registered target name (used by the `attack` launcher for --all)."""
    return list(_targets)
