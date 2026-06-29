#!/usr/bin/env bash
# Create the Linux venv used to RUN YOLOv8 inference inside the ROS 2
# `yolo_detector` node on Ubuntu.
#
# Training stays on Windows (see vision/setup_train_env.ps1) because the
# current Linux install runs inside a VirtualBox VM where the discrete GPU
# is NOT visible (no PCIe passthrough), making CUDA training impossible.
# This script therefore installs CPU-only PyTorch by default — fast enough
# for inference, but not for fine-tuning.
#
# Usage:
#     bash vision/setup_infer_env.sh             # CPU-only torch (default)
#     CUDA=cu121 bash vision/setup_infer_env.sh  # NVIDIA CUDA 12.1 wheels (bare-metal Linux)
#     CUDA=cu118 bash vision/setup_infer_env.sh  # NVIDIA CUDA 11.8 wheels (bare-metal Linux)
#     RECREATE=1 bash vision/setup_infer_env.sh  # nuke the venv and rebuild
#
# Notes:
# - The venv lives at vision/.venv-train (name kept for compatibility with
#   the Windows training side; both sides share the same folder name but
#   never coexist on the same machine).
# - numpy is pinned <2 to keep cv_bridge / rclpy ABI-compatible on Jazzy.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv-train"

if [[ "${RECREATE:-0}" == "1" && -d "$venv" ]]; then
    echo "Removing existing venv: $venv"
    rm -rf "$venv"
fi

if [[ ! -d "$venv" ]]; then
    base_python="${PYTHON:-python3}"
    if ! command -v "$base_python" >/dev/null 2>&1; then
        echo "ERROR: $base_python not found on PATH. Install python3 or set PYTHON=..." >&2
        exit 1
    fi
    if ! "$base_python" -c 'import venv' >/dev/null 2>&1; then
        echo "ERROR: python3-venv module missing. Run: sudo apt install python3-venv python3-pip" >&2
        exit 1
    fi
    echo "Creating venv at $venv (base: $base_python)"
    "$base_python" -m venv "$venv"
fi

# shellcheck disable=SC1091
source "$venv/bin/activate"

python -m pip install --upgrade pip wheel

cuda="${CUDA:-cpu}"
case "$cuda" in
    cpu)
        echo "Installing PyTorch CPU wheels"
        pip install --index-url https://download.pytorch.org/whl/cpu \
            "torch==2.3.1" "torchvision==0.18.1"
        ;;
    cu121)
        echo "Installing PyTorch CUDA 12.1 wheels"
        pip install --index-url https://download.pytorch.org/whl/cu121 \
            "torch==2.3.1" "torchvision==0.18.1"
        ;;
    cu118)
        echo "Installing PyTorch CUDA 11.8 wheels"
        pip install --index-url https://download.pytorch.org/whl/cu118 \
            "torch==2.3.1" "torchvision==0.18.1"
        ;;
    *)
        echo "Unknown CUDA=$cuda (expected cpu | cu121 | cu118)" >&2
        exit 1
        ;;
esac

echo "Installing remaining requirements"
pip install -r "$here/requirements-train.txt"

echo "Verifying torch / CUDA visibility"
python - <<'PY'
import torch
print(f"torch: {torch.__version__}")
print(f"cuda available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"device: {torch.cuda.get_device_name(0)}")
    print(f"capability: {torch.cuda.get_device_capability(0)}")
else:
    print("INFO: CUDA not visible — training will run on CPU (slower).")
PY

cat <<EOF

Done. Activate the env in any new shell:
    source $venv/bin/activate

This venv is for ROS 2 inference (yolo_detector node).
Training is done on Windows — see vision/setup_train_env.ps1.
After training, copy the resulting best.pt into ros2_ws/ and launch:
    ros2 launch low_altitude_bringup perception_yolo.launch.py \\
        model_path:=/home/libo/2026CV/ros2_ws/yolov8s-sim-v1.pt
EOF
