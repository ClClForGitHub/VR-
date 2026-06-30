#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"

echo "== GLB viewer =="
"$ROOT/scripts/status_glb_viewer.sh" || true

echo
echo "== Runtime console =="
"$ROOT/scripts/status_runtime_console.sh" || true

echo
echo "== Blender MCP config =="
codex mcp list || true

echo
echo "== Blender 5.1 Lab MCP bridge =="
"$ROOT/scripts/status_blender51_lab_mcp_bridge.sh" || true

echo
echo "== Blender GUI/runtime =="
printf 'DISPLAY=%s\nWAYLAND_DISPLAY=%s\nXDG_SESSION_TYPE=%s\n' "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}" "${XDG_SESSION_TYPE:-}"

echo
echo "== Docker =="
docker info >/dev/null 2>&1 && echo "docker usable" || {
  echo "docker not usable by current user"
  groups
  ls -l /var/run/docker.sock 2>/dev/null || true
}
