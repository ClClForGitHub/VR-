#!/usr/bin/env bash
set -euo pipefail

ROOT="${IMAGE23D_ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
GPU="${IMAGE23D_GPU:-0}"
CONDA_ENV="${IMAGE23D_CONDA_ENV:-hunyuan3d21}"
HOST="${IMAGE23D_HOST:-0.0.0.0}"
WORLDMIRROR_PORT="${WORLDMIRROR_PORT:-8081}"
HUNYUAN3D_PORT="${HUNYUAN3D_PORT:-8091}"
LOG_DIR="${ROOT}/run_logs"
mkdir -p "${LOG_DIR}"

ensure_port_free() {
  local port="$1"
  if ss -ltnp | grep -q ":${port} "; then
    echo "Port ${port} is already in use. Stop the existing service first." >&2
    ss -ltnp | grep ":${port} " >&2 || true
    exit 1
  fi
}

start_worldmirror() {
  local log="${LOG_DIR}/worldmirror_gpu${GPU}_${WORLDMIRROR_PORT}.log"
  local pidfile="${LOG_DIR}/worldmirror_gpu${GPU}_${WORLDMIRROR_PORT}.pid"
  ensure_port_free "${WORLDMIRROR_PORT}"
  setsid bash -lc "
    cd '${ROOT}/HY-World-2.0'
    CUDA_VISIBLE_DEVICES='${GPU}' \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    conda run --no-capture-output -n '${CONDA_ENV}' \
      python -m hyworld2.worldrecon.gradio_app \
        --pretrained_model_name_or_path '${ROOT}/models/tencent/HY-World-2.0' \
        --enable_bf16 \
        --host '${HOST}' \
        --port '${WORLDMIRROR_PORT}'
  " >"${log}" 2>&1 < /dev/null &
  echo "$!" > "${pidfile}"
  echo "WorldMirror starting on GPU ${GPU}, port ${WORLDMIRROR_PORT}; log: ${log}"
}

start_hunyuan3d() {
  local log="${LOG_DIR}/hunyuan3d21_api_gpu${GPU}_${HUNYUAN3D_PORT}.log"
  local pidfile="${LOG_DIR}/hunyuan3d21_api_gpu${GPU}_${HUNYUAN3D_PORT}.pid"
  ensure_port_free "${HUNYUAN3D_PORT}"
  setsid bash -lc "
    cd '${ROOT}/Hunyuan3D-2.1'
    CUDA_VISIBLE_DEVICES='${GPU}' \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    conda run --no-capture-output -n '${CONDA_ENV}' \
      python api_server.py \
        --model_path '${ROOT}/models/tencent/Hunyuan3D-2.1' \
        --subfolder hunyuan3d-dit-v2-1 \
        --texgen_model_path '${ROOT}/models/tencent/Hunyuan3D-2.1' \
        --dino_ckpt_path '${ROOT}/models/facebook/dinov2-giant' \
        --texture-resolution 768 \
        --max-num-view 8 \
        --low_vram_mode \
        --host '${HOST}' \
        --port '${HUNYUAN3D_PORT}' \
        --cache-path '${ROOT}/Hunyuan3D-2.1/api_cache_gpu${GPU}_tex'
  " >"${log}" 2>&1 < /dev/null &
  echo "$!" > "${pidfile}"
  echo "Hunyuan3D-2.1 FastAPI texture service starting on GPU ${GPU}, port ${HUNYUAN3D_PORT}; log: ${log}"
}

start_worldmirror
start_hunyuan3d

echo "Use scripts/status_a40_services.sh to verify readiness."
