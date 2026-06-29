#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "ERROR: 请用 sudo 运行: sudo bash $0 [--disable-gsp]"
    exit 1
fi

DISABLE_GSP=0
if [[ "${1:-}" == "--disable-gsp" ]]; then
    DISABLE_GSP=1
elif [[ -n "${1:-}" ]]; then
    echo "用法: sudo bash $0 [--disable-gsp]"
    exit 1
fi

GPU_BDF="$(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader | head -n 1 | sed 's/^00000000:/0000:/')"
if [[ -z "$GPU_BDF" ]]; then
    echo "ERROR: 未检测到 NVIDIA GPU."
    exit 1
fi

SERVICE_PATH="/etc/systemd/system/2026cv-gpu-stability.service"
MODPROBE_PATH="/etc/modprobe.d/2026cv-nvidia-stability.conf"

echo "[gpu-stability] GPU BDF: $GPU_BDF"

echo "[gpu-stability] 启用 persistence mode"
nvidia-smi -pm 1 >/dev/null

echo "[gpu-stability] 关闭 NVIDIA runtime suspend"
if [[ -w "/sys/bus/pci/devices/$GPU_BDF/power/control" ]]; then
    echo on > "/sys/bus/pci/devices/$GPU_BDF/power/control"
fi

echo "[gpu-stability] 暂停 apt/packagekit 后台任务"
systemctl stop apt-daily.service apt-daily-upgrade.service packagekit.service packagekit-offline-update.service 2>/dev/null || true

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=2026CV NVIDIA Stability Settings
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/bash -lc 'if [[ -w /sys/bus/pci/devices/$GPU_BDF/power/control ]]; then echo on > /sys/bus/pci/devices/$GPU_BDF/power/control; fi'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now 2026cv-gpu-stability.service >/dev/null

if [[ "$DISABLE_GSP" == "1" ]]; then
    echo "[gpu-stability] 写入禁用 GSP 的 modprobe 配置 (需重启生效)"
    cat > "$MODPROBE_PATH" <<'EOF'
options nvidia NVreg_EnableGpuFirmware=0 NVreg_PreserveVideoMemoryAllocations=1
options nvidia_drm modeset=1 fbdev=1
EOF
    UPDATE_INITRAMFS=1
    if command -v update-initramfs >/dev/null 2>&1; then
        update-initramfs -u
    fi
else
    UPDATE_INITRAMFS=0
fi

cat <<EOF

============================================================
GPU 稳定性模式已应用

已生效:
  - nvidia-smi persistence mode = ON
  - /sys/bus/pci/devices/$GPU_BDF/power/control = on
  - apt/packagekit 后台任务已停止
  - 已安装 systemd 服务: 2026cv-gpu-stability.service

EOF

if [[ "$UPDATE_INITRAMFS" == "1" ]]; then
    cat <<EOF
额外已启用:
  - 禁用 GSP firmware
  - nvidia_drm modeset=1

下一步:
  1) reboot
  2) 登录后重试 GPU 任务
EOF
else
    cat <<EOF
建议先直接测试:
  WORLD=baylands DEVICE=0 IMGSZ=480 PERF=1 SKIP=1 bash scripts/launch_all.sh

如果仍然整机卡死，再执行:
  sudo bash scripts/apply_gpu_stability_mode.sh --disable-gsp
  sudo reboot
EOF
fi
