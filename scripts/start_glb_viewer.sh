#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
BIND_HOST="${BIND_HOST:-0.0.0.0}"
PORT="${PORT:-8092}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/glb_viewer_${PORT}.pid}"
LOGFILE="${LOGFILE:-$ROOT/run_logs/glb_viewer_${PORT}.log}"

mkdir -p "$ROOT/run_logs"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "GLB viewer already running: pid=$(cat "$PIDFILE")"
  echo "URL: http://10.2.16.106:${PORT}/"
  exit 0
fi

cd "$ROOT"
setsid bash -lc "cd '$ROOT' && exec python tools/glb_viewer_server.py --host '$BIND_HOST' --port '$PORT' --root '$ROOT'" >"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"
sleep 1

if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "GLB viewer failed to start. Log:"
  tail -80 "$LOGFILE" || true
  exit 1
fi

echo "GLB viewer started: pid=$(cat "$PIDFILE")"
echo "URL: http://10.2.16.106:${PORT}/"
echo "Log: $LOGFILE"
