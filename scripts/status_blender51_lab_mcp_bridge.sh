#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
BLENDER_BIN="${BLENDER_BIN:-/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
PORT="${PORT:-9876}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/blender51_lab_mcp_bridge_${PORT}.pid}"
LOGFILE="${LOGFILE:-$ROOT/run_logs/blender51_lab_mcp_bridge_${PORT}.log}"

if [[ -x "$BLENDER_BIN" ]]; then
  "$BLENDER_BIN" --version | sed -n '1,4p'
else
  echo "Blender binary not executable: $BLENDER_BIN"
fi

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Blender 5.1 Lab MCP bridge running: pid=$(cat "$PIDFILE")"
else
  echo "Blender 5.1 Lab MCP bridge not running"
fi

python - "$BIND_HOST" "$PORT" <<'PY' || true
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=0.4):
        print(f"Blender Lab MCP bridge socket: open on {host}:{port}")
except Exception as exc:
    print(f"Blender Lab MCP bridge socket: closed ({type(exc).__name__})")
PY

ss -ltnp | rg ":${PORT}\\b" || true

if [[ -f "$LOGFILE" ]]; then
  echo "Recent log:"
  tail -60 "$LOGFILE"
fi
