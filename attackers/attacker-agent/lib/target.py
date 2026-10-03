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
import socket
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


# --- Transport: network trouble is NOT a test result ----------------------------------
# A canary that never leaks is a finding about the target. A target we could not reach, a
# timeout, a rate limit, or a 5xx is a finding about the *network* — it says nothing about
# whether the agent is vulnerable. We raise TransportError for those so the campaign and the
# verifier can keep the behavior OPEN instead of scoring it as a miss / rejection.
TIMEOUT_S = float(os.environ.get("TARGET_TIMEOUT_S", 90))  # one tool-calling LLM turn can be slow
MAX_RETRIES = int(os.environ.get("TARGET_RETRIES", 5))
_BACKOFF_S = [0.2, 0.4, 0.8, 1.6, 3.2]
_RETRYABLE_STATUS = {502, 503, 504}


class TransportError(RuntimeError):
    """The target could not be reached or did not answer cleanly. Not a verdict on the agent."""

    def __init__(self, message, retryable=False, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after  # seconds the server asked us to wait (429), else None


def _request_once(url, body, method):
    """One HTTP round-trip. Returns (status, text) on a clean response, else raises TransportError."""
    headers = {"Authorization": f"Bearer {TARGET_KEY}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read().decode(errors="replace")
        if status == 429:
            wait = float(e.headers.get("retry-after") or 2) + 0.2
            raise TransportError("target rate-limited (HTTP 429)", retryable=True, retry_after=wait)
        if status in _RETRYABLE_STATUS:
            raise TransportError(f"target HTTP {status} (transient)", retryable=True)
        # Any other HTTP status is a server/protocol failure, not a leak verdict — do not retry.
        try:
            err = json.loads(text).get("error", {}).get("message")
        except (json.JSONDecodeError, AttributeError):
            err = None
        raise TransportError(f"target HTTP {status}: {err or text[:200]}")
    except (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout) as e:
        # Connection refused, DNS failure, read timeout, reset mid-flight — all retryable.
        reason = getattr(e, "reason", e)
        raise TransportError(f"target unreachable: {reason}", retryable=True)


def _send(url, body, method="POST"):
    """Retry a request on transport trouble with backoff, then return parsed JSON or raise TransportError."""
    last = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            status, text = _request_once(url, body, method)
        except TransportError as e:
            last = e
            if not e.retryable or attempt == MAX_RETRIES:
                raise
            wait = e.retry_after if e.retry_after is not None else _BACKOFF_S[min(attempt, len(_BACKOFF_S) - 1)]
            time.sleep(wait)
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # A 200 with a broken body is a protocol failure, not a result — surface it, do not retry.
            raise TransportError(f"target returned non-JSON ({status}): {text[:200]}")
    raise last or TransportError("transport failure")


def _post(messages, session_id):
    """One chat call to the target. Transport trouble raises TransportError (see above)."""
    body = json.dumps({"model": TARGET_MODEL, "messages": messages, "session_id": session_id}).encode()
    return _send(TARGET_URL, body, "POST")


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
    return _send(f"{base}/health", None, "GET")  # { ok, model, hasKey }; raises TransportError if down


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
