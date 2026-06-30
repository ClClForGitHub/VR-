#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
PORT="${PORT:-8093}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/runtime_console_${PORT}.pid}"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No pidfile: $PIDFILE"
  exit 0
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped runtime console pid=$PID"
else
  echo "Runtime console pid not running: $PID"
fi
rm -f "$PIDFILE"
