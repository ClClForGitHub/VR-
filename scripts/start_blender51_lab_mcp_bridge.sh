#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
BLENDER_BIN="${BLENDER_BIN:-/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
PORT="${PORT:-9876}"
ADDON="${ADDON:-bl_ext.user_default.mcp}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/blender51_lab_mcp_bridge_${PORT}.pid}"
LOGFILE="${LOGFILE:-$ROOT/run_logs/blender51_lab_mcp_bridge_${PORT}.log}"

mkdir -p "$ROOT/run_logs"

if [[ ! -x "$BLENDER_BIN" ]]; then
  echo "Blender binary not executable: $BLENDER_BIN"
  exit 1
fi

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Blender 5.1 Lab MCP bridge already running: pid=$(cat "$PIDFILE")"
  echo "Socket: ${BIND_HOST}:${PORT}"
  exit 0
fi

if ss -ltnp | rg -q ":${PORT}\\b"; then
  echo "Port ${PORT} is already occupied:"
  ss -ltnp | rg ":${PORT}\\b" || true
  exit 1
fi

cd "$ROOT"
setsid bash -lc "exec '$BLENDER_BIN' --background --online-mode --addons '$ADDON' --command blender_mcp --host '$BIND_HOST' --port '$PORT'" >"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"

for _ in $(seq 1 15); do
  if python - "$BIND_HOST" "$PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.create_connection((host, port), timeout=0.4):
    pass
PY
  then
    echo "Blender 5.1 Lab MCP bridge started: pid=$(cat "$PIDFILE")"
    echo "Socket: ${BIND_HOST}:${PORT}"
    echo "Log: $LOGFILE"
    exit 0
  fi

  if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Blender 5.1 Lab MCP bridge exited during startup. Log:"
    tail -100 "$LOGFILE" || true
    rm -f "$PIDFILE"
    exit 1
  fi
  sleep 1
done

echo "Blender 5.1 Lab MCP bridge process started but socket did not open in time."
echo "pid=$(cat "$PIDFILE")"
echo "Recent log:"
tail -100 "$LOGFILE" || true
exit 1
