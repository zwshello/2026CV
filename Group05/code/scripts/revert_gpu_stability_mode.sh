#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "ERROR: 请用 sudo 运行: sudo bash $0"
    exit 1
fi

GPU_BDF="$(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader | head -n 1 | sed 's/^00000000:/0000:/')"
SERVICE_PATH="/etc/systemd/system/2026cv-gpu-stability.service"
MODPROBE_PATH="/etc/modprobe.d/2026cv-nvidia-stability.conf"

systemctl disable --now 2026cv-gpu-stability.service 2>/dev/null || true
rm -f "$SERVICE_PATH"

if [[ -n "$GPU_BDF" && -w "/sys/bus/pci/devices/$GPU_BDF/power/control" ]]; then
    echo auto > "/sys/bus/pci/devices/$GPU_BDF/power/control" || true
fi

nvidia-smi -pm 0 >/dev/null 2>&1 || true

if [[ -f "$MODPROBE_PATH" ]]; then
    rm -f "$MODPROBE_PATH"
    if command -v update-initramfs >/dev/null 2>&1; then
        update-initramfs -u
    fi
fi

systemctl daemon-reload

cat <<EOF

============================================================
GPU 稳定性模式已回退

已回退:
  - persistence mode -> OFF
  - power/control -> auto
  - 移除 systemd 服务: 2026cv-gpu-stability.service
  - 若之前启用过 --disable-gsp, modprobe 配置已删除

如回退了 GSP 配置, 请 reboot 生效。
EOF