#!/usr/bin/env bash
# targetctl.sh — start/stop/status/logs a single target server by name.
# Backs the root Makefile. Port + server location come from the target itself:
#   targets/<name>/manifest.json  ->  "port"
#   targets/<name>/server.py      ->  the app (reads its own .env; cwd-independent)
#
#   scripts/targetctl.sh start|stop|status|logs <name>
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$here/.." && pwd)"
PY="${PYTHON:-python3}"
RUN="$ROOT/.run"

action="${1:-}"
name="${2:-}"
[ -n "$action" ] && [ -n "$name" ] || { echo "  usage: targetctl.sh <start|stop|status|logs> <name>"; exit 2; }

dir="$ROOT/targets/$name"
[ -f "$dir/server.py" ] || { echo "  unknown target: $name (no targets/$name/server.py)"; exit 2; }
port="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['port'])" "$dir/manifest.json" 2>/dev/null)"
[ -n "$port" ] || { echo "  $name: could not read port from manifest.json"; exit 1; }
mkdir -p "$RUN"

listening() { lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; }

case "$action" in
  start)
    if listening; then echo "  $name: already listening on :$port"; exit 0; fi
    nohup "$PY" -u "$dir/server.py" >"$RUN/$name.log" 2>&1 &
    echo $! >"$RUN/$name.pid"
    for _ in $(seq 1 20); do
      curl -sf "http://localhost:$port/health" >/dev/null 2>&1 && break
      sleep 0.5
    done
    if listening; then
      echo "  $name: up on :$port  (pid $(cat "$RUN/$name.pid"), log .run/$name.log)"
    else
      echo "  $name: FAILED to start — last log lines:"; tail -n 5 "$RUN/$name.log" | sed 's/^/      /'
      exit 1
    fi
    ;;
  stop)
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      echo "$pids" | xargs kill 2>/dev/null || true
      echo "  $name: stopped (:$port)"
    else
      echo "  $name: not running"
    fi
    rm -f "$RUN/$name.pid"
    ;;
  status)
    if listening; then
      echo "  $name  :$port  UP"
    else
      echo "  $name  :$port  down"
    fi
    ;;
  logs)
    [ -f "$RUN/$name.log" ] || { echo "  $name: no log yet (.run/$name.log). Start it first."; exit 1; }
    tail -n 40 -f "$RUN/$name.log"
    ;;
  *)
    echo "  unknown action: $action"; exit 2
    ;;
esac
