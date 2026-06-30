#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
NAME="${NAME:-image23d-blender-web}"
HOST_PORT_HTTPS="${HOST_PORT_HTTPS:-8301}"
HOST_PORT_HTTP="${HOST_PORT_HTTP:-8300}"
IMAGE="${IMAGE:-lscr.io/linuxserver/blender:latest}"
CONFIG_DIR="${CONFIG_DIR:-$ROOT/run_logs/blender_web_config}"

mkdir -p "$CONFIG_DIR"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but not usable by this user."
  echo "Current user: $(id -un)"
  echo "Groups: $(groups)"
  echo "Docker socket: $(ls -l /var/run/docker.sock 2>/dev/null || true)"
  echo
  echo "Ask an admin to add this user to the docker group or start the container once with sufficient privileges."
  echo "After permission is fixed, re-run: $0"
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker start "$NAME" >/dev/null
else
  docker run -d \
    --name "$NAME" \
    --security-opt seccomp=unconfined \
    -e PUID="$(id -u)" \
    -e PGID="$(id -g)" \
    -e TZ=Asia/Shanghai \
    -p "${HOST_PORT_HTTP}:3000" \
    -p "${HOST_PORT_HTTPS}:3001" \
    -v "${CONFIG_DIR}:/config" \
    -v "${ROOT}:${ROOT}" \
    "$IMAGE" >/dev/null
fi

echo "Blender web container running: $NAME"
echo "HTTPS URL: https://10.2.16.106:${HOST_PORT_HTTPS}/"
echo "HTTP URL:  http://10.2.16.106:${HOST_PORT_HTTP}/"
echo "Mounted workspace: $ROOT"
