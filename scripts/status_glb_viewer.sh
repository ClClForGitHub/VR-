#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
PORT="${PORT:-8092}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/glb_viewer_${PORT}.pid}"
LOGFILE="${LOGFILE:-$ROOT/run_logs/glb_viewer_${PORT}.log}"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "GLB viewer running: pid=$(cat "$PIDFILE")"
  echo "URL: http://10.2.16.106:${PORT}/"
else
  echo "GLB viewer not running"
fi

ss -ltnp | rg ":${PORT}\\b" || true
if [[ -f "$LOGFILE" ]]; then
  echo "Recent log:"
  tail -40 "$LOGFILE"
fi
