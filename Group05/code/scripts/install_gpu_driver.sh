#!/usr/bin/env bash
# 安装 NVIDIA 专有驱动 (Ubuntu 24.04 裸机, RTX 4050 Max-Q)
# 用法:
#   sudo bash scripts/install_gpu_driver.sh
#   sudo reboot
#   bash scripts/install_cuda_torch.sh

set -e

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: 需要 root. 请用: sudo bash $0"
    exit 1
fi

echo "[gpu] (1/4) apt update"
apt-get update

echo "[gpu] (2/4) 安装 ubuntu-drivers + 编译依赖"
apt-get install -y ubuntu-drivers-common build-essential dkms

echo "[gpu] (3/4) 检测可用驱动"
ubuntu-drivers devices || true

echo "[gpu] (4/4) 自动安装推荐驱动"
ubuntu-drivers autoinstall

cat <<EOF

============================================================
NVIDIA 驱动安装完成.

下一步:
  1) sudo reboot
  2) 重启后验证:    nvidia-smi
  3) 安装 GPU Torch: bash scripts/install_cuda_torch.sh
============================================================
EOF
