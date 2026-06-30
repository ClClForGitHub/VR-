#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
PORT="${PORT:-9876}"
PIDFILE="${PIDFILE:-$ROOT/run_logs/blender51_lab_mcp_bridge_${PORT}.pid}"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No pidfile: $PIDFILE"
  exit 0
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped Blender 5.1 Lab MCP bridge pid=$PID"
else
  echo "Blender 5.1 Lab MCP bridge pid not running: $PID"
fi
rm -f "$PIDFILE"
