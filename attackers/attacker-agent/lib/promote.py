# promote.py — turn a CONFIRMED finding into a promptfoo regression case ("report it to promptfoo").
# The last step of the audit loop: a verified vulnerability becomes a reusable, deterministic test that
# FAILS if the bug ever comes back. The provider returns the WHOLE response envelope (not just reply.text)
# so a test can also catch tool-action findings (e.g. a transfer that fired) via findings_hint.
#
# Connection + assertions are derived from the ACTIVE target's manifest (via target.py), so this works for
# any registered target with no edits.
import json

from .judge import CANARIES
from .target import ACTIVE, MANIFEST, TARGET_MODEL, TARGET_URL

_KEY_VAR = MANIFEST["key_env"]
_KEY_DEFAULT = MANIFEST["key_default"]
_LABEL = f"{ACTIVE}-http"
# Map each action-goal to the findings_hint flag key(s) that prove it, for goals with no text canary.
_FLAG_STRINGS_BY_GOAL = {}
for _key, _meta in MANIFEST.get("flags", {}).items():
    _FLAG_STRINGS_BY_GOAL.setdefault(_meta["goal"], []).append(_key)


def _assertions_for(goal):
    """Which strings prove each goal — what the regression must assert never appears in the envelope."""
    strings = (CANARIES.get(goal) or {}).get("strings")
    if strings:
        return [json.dumps(s) for s in strings]
    # Action-only goal (e.g. EXCESSIVE_AGENCY): assert the forbidden flag key never appears.
    return [json.dumps(k) for k in _FLAG_STRINGS_BY_GOAL.get(goal, [])]


def to_regression_yaml(finding):
    asserts_values = _assertions_for(finding["goal"])
    transcript = finding.get("transcript") or []
    prompt = "\n".join(t["user"] for t in transcript)  # collapsed replay
    asserts = "\n".join(f"      - {{ type: not-contains, value: {v} }}" for v in asserts_values)
    bot = MANIFEST["bot"].upper()
    transcript_comment = "\n".join(
        f"#   {i + 1}. YOU:   {t['user']}\n#      {bot}: {' '.join(str(t['reply']).split())[:100]}"
        for i, t in enumerate(transcript)
    )
    owasp_asi = finding.get("owaspASI")
    asi_suffix = f" · {owasp_asi}" if owasp_asi and owasp_asi != "—" else ""
    multi = "multi-turn " if len(transcript) > 1 else ""
    verified = finding.get("verification", {}).get("reproduced", "?")
    when = finding.get("verifiedAt") or finding.get("foundAt")

    return f"""# AUTO-GENERATED regression case — {finding['id']} ({finding['category']})
# {finding['owaspLLM']}{asi_suffix}
# Confirmed {verified} on {when}. AIVSS hint: {finding.get('aivssHint', 'n/a')}
#
# Original {multi}transcript that proved it:
{transcript_comment}
#
# NOTE: multi-turn findings are collapsed into one prompt here for a portable single-turn regression.
# For a faithful multi-turn replay, use a session-aware provider.
#
#   export {_KEY_VAR}={_KEY_DEFAULT}
#   npx -y promptfoo@latest eval -c {finding['id']}.gen.yaml --no-cache && npx -y promptfoo@latest view

description: "{finding['id']} — {finding['title']} (regression)"

providers:
  - id: https
    label: {_LABEL}
    config:
      url: {TARGET_URL}
      method: POST
      headers:
        Content-Type: application/json
        Authorization: 'Bearer {{{{env.{_KEY_VAR}}}}}'
      body:
        model: {TARGET_MODEL}
        messages: [{{ role: user, content: '{{{{prompt}}}}' }}]
      # Return the WHOLE envelope so assertions can see reply text AND tool-action flags.
      transformResponse: 'JSON.stringify(json)'
      maxRetries: 2

prompts:
  - '{{{{prompt}}}}'

tests:
  - description: "regression — {finding['id']} must not leak/act (a FAIL here = the bug is back)"
    vars: {{ prompt: {json.dumps(prompt)} }}
    assert:
{asserts}
    metadata: {{ id: {finding['id']}, goal: {finding['goal']}, owasp: "{finding['owaspLLM']}" }}
"""
