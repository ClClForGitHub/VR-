#!/usr/bin/env bash
set -euo pipefail

ROOT="${IMAGE23D_ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
GPU="${IMAGE23D_GPU:-0}"
WORLDMIRROR_PORT="${WORLDMIRROR_PORT:-8081}"
HUNYUAN3D_PORT="${HUNYUAN3D_PORT:-8091}"
LOG_DIR="${ROOT}/run_logs"

stop_from_pidfile() {
  local label="$1"
  local pidfile="$2"
  if [[ ! -f "${pidfile}" ]]; then
    echo "${label}: no pidfile at ${pidfile}"
    return 0
  fi

  local pid
  pid="$(cat "${pidfile}")"
  if [[ -z "${pid}" ]] || ! ps -p "${pid}" >/dev/null 2>&1; then
    echo "${label}: stale pidfile ${pidfile}"
    rm -f "${pidfile}"
    return 0
  fi

  local pgid
  pgid="$(ps -o pgid= -p "${pid}" | tr -d ' ')"
  if [[ -z "${pgid}" ]]; then
    echo "${label}: could not resolve process group for pid ${pid}" >&2
    return 1
  fi

  echo "${label}: stopping process group ${pgid}"
  kill -TERM -- "-${pgid}" || true
  rm -f "${pidfile}"
}

stop_from_pidfile "WorldMirror" "${LOG_DIR}/worldmirror_gpu${GPU}_${WORLDMIRROR_PORT}.pid"
stop_from_pidfile "Hunyuan3D-2.1 FastAPI service" "${LOG_DIR}/hunyuan3d21_api_gpu${GPU}_${HUNYUAN3D_PORT}.pid"
stop_from_pidfile "Hunyuan3D-2.1 legacy Gradio service" "${LOG_DIR}/hunyuan3d21_tex_gpu${GPU}_${HUNYUAN3D_PORT}.pid"

echo "Remaining matching ports, if any:"
ss -ltnp | grep -E ":(${WORLDMIRROR_PORT}|${HUNYUAN3D_PORT}) " || true
