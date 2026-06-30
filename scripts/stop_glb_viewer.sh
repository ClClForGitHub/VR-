#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
PORT="${PORT:-8092}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/glb_viewer_${PORT}.pid}"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No pidfile: $PIDFILE"
  exit 0
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped GLB viewer pid=$PID"
else
  echo "GLB viewer pid not running: $PID"
fi
rm -f "$PIDFILE"
