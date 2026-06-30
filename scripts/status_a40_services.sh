#!/usr/bin/env bash
set -euo pipefail

ROOT="${IMAGE23D_ROOT:-/home/team/zouzhiyuan/image23D_Agent}"
GPU="${IMAGE23D_GPU:-0}"
WORLDMIRROR_PORT="${WORLDMIRROR_PORT:-8081}"
HUNYUAN3D_PORT="${HUNYUAN3D_PORT:-8091}"
LOG_DIR="${ROOT}/run_logs"

echo "CUDA_VISIBLE_DEVICES=${GPU}:"
CUDA_VISIBLE_DEVICES="${GPU}" conda run --no-capture-output -n hunyuan3d21 \
  python -c "import torch; print('available', torch.cuda.is_available()); print('count', torch.cuda.device_count()); print('device0', torch.cuda.get_device_name(0) if torch.cuda.device_count() else None); print('free_total_gb', tuple(round(x/1024**3, 2) for x in torch.cuda.mem_get_info(0)) if torch.cuda.device_count() else None)" \
  2>&1 || true

echo
echo "nvidia-smi physical index ${GPU}, if available:"
nvidia-smi -i "${GPU}" --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>&1 || true

echo
echo "Ports:"
ss -ltnp | grep -E ":(${WORLDMIRROR_PORT}|${HUNYUAN3D_PORT}) " || true

echo
echo "Tracked processes:"
for pidfile in \
  "${LOG_DIR}/worldmirror_gpu${GPU}_${WORLDMIRROR_PORT}.pid" \
  "${LOG_DIR}/hunyuan3d21_api_gpu${GPU}_${HUNYUAN3D_PORT}.pid" \
  "${LOG_DIR}/hunyuan3d21_tex_gpu${GPU}_${HUNYUAN3D_PORT}.pid"
do
  if [[ -f "${pidfile}" ]]; then
    pid="$(cat "${pidfile}")"
    echo "${pidfile}: ${pid}"
    ps -o user,pid,ppid,pgid,stat,etime,pcpu,pmem,rss,cmd -p "${pid}" || true
  else
    echo "${pidfile}: missing"
  fi
done

echo
echo "Recent logs:"
for log in \
  "${LOG_DIR}/worldmirror_gpu${GPU}_${WORLDMIRROR_PORT}.log" \
  "${LOG_DIR}/hunyuan3d21_api_gpu${GPU}_${HUNYUAN3D_PORT}.log" \
  "${LOG_DIR}/hunyuan3d21_tex_gpu${GPU}_${HUNYUAN3D_PORT}.log"
do
  echo "== ${log} =="
  tail -n 20 "${log}" 2>/dev/null || true
done
