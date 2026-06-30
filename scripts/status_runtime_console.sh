#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
PORT="${PORT:-8093}"
PUBLIC_HOST="${PUBLIC_HOST:-10.2.16.106}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/runtime_console_${PORT}.pid}"
LOGFILE="${LOGFILE:-$ROOT/run_logs/runtime_console_${PORT}.log}"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Runtime console running: pid=$(cat "$PIDFILE")"
  echo "URL: http://${PUBLIC_HOST}:${PORT}/"
else
  echo "Runtime console not running"
fi

ss -ltnp | rg ":${PORT}\\b" || true
if [[ -f "$LOGFILE" ]]; then
  echo "Recent log:"
  tail -40 "$LOGFILE"
fi
