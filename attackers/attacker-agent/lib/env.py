# env.py — a tiny zero-dependency .env loader (import this FIRST so the other libs see your keys).
# A value already set in your shell wins over .env, so you can override one setting for a single run:
#   EPISODES=3 python attacker.py
import os
import re
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def load(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ without overwriting existing vars."""
    env_path = path or (LAB / ".env")
    try:
        raw = env_path.read_text(encoding="utf-8")
    except OSError:
        return  # no .env — fine, defaults + shell env apply
    for line in raw.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        quoted = len(val) > 1 and (
            (val[0] == '"' and val.endswith('"')) or (val[0] == "'" and val.endswith("'"))
        )
        if quoted:
            val = val[1:-1]
        else:
            val = re.sub(r"\s+#.*$", "", val).strip()
        os.environ.setdefault(key, val)


# Load on import, mirroring the JS `import './lib/env.mjs'` side effect.
load()
