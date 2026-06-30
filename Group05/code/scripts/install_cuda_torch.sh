#!/usr/bin/env bash
# 在 vision/.venv-train 里安装 CUDA 版 PyTorch 并跑一次 YOLO GPU 基准.
# 运行前提: 已装好 NVIDIA 驱动并重启, nvidia-smi 可用.
#
# 用法: bash scripts/install_cuda_torch.sh

set -e

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJ_ROOT/vision/.venv-train"

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "ERROR: 找不到 nvidia-smi. 请先:"
    echo "       sudo bash scripts/install_gpu_driver.sh && sudo reboot"
    exit 1
fi

echo "[cuda] nvidia-smi:"
nvidia-smi | head -20

if [[ ! -d "$VENV" ]]; then
    echo "ERROR: venv 不存在: $VENV"
    echo "       请先: bash vision/setup_train_env.sh"
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "[cuda] 卸载旧的 CPU torch (若存在)"
pip uninstall -y torch torchvision || true

echo "[cuda] 安装 torch 2.3.1 + cu121"
pip install --index-url https://download.pytorch.org/whl/cu121 \
    "torch==2.3.1" "torchvision==0.18.1"

echo "[cuda] 验证 torch 是否看到 CUDA"
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
else:
    raise SystemExit("CUDA 不可见. 检查 nvidia-smi 与驱动版本.")
PY

echo "[cuda] YOLO GPU 基准 (yolov8n.pt @ imgsz=480)"
python - <<'PY'
from ultralytics import YOLO
import numpy as np, time
m = YOLO("/home/libo/2026CV/ros2_ws/yolov8n.pt")
img = (np.random.rand(720, 1280, 3) * 255).astype("uint8")
m.predict(img, device=0, imgsz=480, verbose=False)  # warmup
t0 = time.time()
N = 30
for _ in range(N):
    m.predict(img, device=0, imgsz=480, verbose=False)
dt = (time.time() - t0) / N * 1000
print(f"GPU avg latency: {dt:.1f} ms  (~{1000/dt:.1f} FPS)")
PY

cat <<EOF

============================================================
GPU Torch 就绪.

GPU 启动 (推荐):
  DEVICE=0 IMGSZ=480 PERF=1 bash scripts/launch_all.sh

强制 CPU (回退):
  DEVICE=cpu bash scripts/launch_all.sh
============================================================
EOF
