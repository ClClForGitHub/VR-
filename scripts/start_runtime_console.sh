#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
BIND_HOST="${BIND_HOST:-0.0.0.0}"
PORT="${PORT:-8093}"
PUBLIC_HOST="${PUBLIC_HOST:-10.2.16.106}"
GLB_VIEWER_URL="${GLB_VIEWER_URL:-http://10.2.16.106:8092}"
BLENDER_WEB_HTTP_URL="${BLENDER_WEB_HTTP_URL:-http://10.2.16.106:8300}"
BLENDER_WEB_HTTPS_URL="${BLENDER_WEB_HTTPS_URL:-https://10.2.16.106:8301}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/runtime_console_${PORT}.pid}"
LOGFILE="${LOGFILE:-$ROOT/run_logs/runtime_console_${PORT}.log}"

mkdir -p "$ROOT/run_logs"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Runtime console already running: pid=$(cat "$PIDFILE")"
  echo "URL: http://${PUBLIC_HOST}:${PORT}/"
  exit 0
fi

cd "$ROOT"
setsid bash -lc "cd '$ROOT' && exec python tools/runtime_console_server.py --host '$BIND_HOST' --port '$PORT' --root '$ROOT' --public-glb-viewer-base-url '$GLB_VIEWER_URL' --public-blender-web-http-url '$BLENDER_WEB_HTTP_URL' --public-blender-web-https-url '$BLENDER_WEB_HTTPS_URL'" >"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"
sleep 1

if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Runtime console failed to start. Log:"
  tail -80 "$LOGFILE" || true
  exit 1
fi

echo "Runtime console started: pid=$(cat "$PIDFILE")"
echo "URL: http://${PUBLIC_HOST}:${PORT}/"
echo "Log: $LOGFILE"
