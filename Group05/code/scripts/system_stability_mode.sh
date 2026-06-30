#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
GPU_FLAG="${2:-}"

SYSCTL_CONF="/etc/sysctl.d/99-2026cv-stability.conf"
JOURNALD_DIR="/etc/systemd/journald.conf.d"
JOURNALD_CONF="$JOURNALD_DIR/99-2026cv-low-io.conf"

APT_TIMERS=(
    apt-daily.timer
    apt-daily-upgrade.timer
)

APT_SERVICES=(
    apt-daily.service
    apt-daily-upgrade.service
    packagekit.service
    packagekit-offline-update.service
)

usage() {
    cat <<EOF
用法:
  sudo bash scripts/system_stability_mode.sh apply [--disable-gsp]
  sudo bash scripts/system_stability_mode.sh revert
  sudo bash scripts/system_stability_mode.sh status

说明:
  apply  : 应用系统稳定化配置（低写盘 + 低 swap 抖动 + 限制后台更新）
  revert : 回退 system_stability_mode 的改动
  status : 查看当前关键状态

可选参数:
  --disable-gsp   传给 scripts/apply_gpu_stability_mode.sh
EOF
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        echo "ERROR: 需要 root, 请用 sudo 运行。"
        exit 1
    fi
}

apply_sysctl() {
    cat > "$SYSCTL_CONF" <<'EOF'
vm.swappiness=10
vm.vfs_cache_pressure=50
vm.dirty_background_ratio=3
vm.dirty_ratio=10
EOF
    sysctl --system >/dev/null
}

revert_sysctl() {
    rm -f "$SYSCTL_CONF"
    sysctl --system >/dev/null
}

apply_journald() {
    mkdir -p "$JOURNALD_DIR"
    cat > "$JOURNALD_CONF" <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=200M
SystemMaxUse=100M
EOF
    systemctl restart systemd-journald
}

revert_journald() {
    rm -f "$JOURNALD_CONF"
    systemctl restart systemd-journald
}

stop_background_updates() {
    systemctl stop "${APT_SERVICES[@]}" 2>/dev/null || true
    systemctl disable "${APT_TIMERS[@]}" 2>/dev/null || true
}

restore_background_updates() {
    systemctl enable "${APT_TIMERS[@]}" 2>/dev/null || true
}

set_power_profile() {
    if command -v powerprofilesctl >/dev/null 2>&1; then
        powerprofilesctl set balanced || true
    fi
}

apply_gpu_stability() {
    local script="/home/libo/2026CV/scripts/apply_gpu_stability_mode.sh"
    if [[ -x "$script" || -f "$script" ]]; then
        if [[ "$GPU_FLAG" == "--disable-gsp" ]]; then
            bash "$script" --disable-gsp
        else
            bash "$script"
        fi
    else
        echo "WARN: 未找到 $script, 跳过 GPU 稳定化。"
    fi
}

revert_gpu_stability() {
    local script="/home/libo/2026CV/scripts/revert_gpu_stability_mode.sh"
    if [[ -x "$script" || -f "$script" ]]; then
        bash "$script"
    else
        echo "WARN: 未找到 $script, 跳过 GPU 回退。"
    fi
}

unit_state() {
    local unit="$1"
    local state
    state="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    if [[ -z "$state" ]]; then
        state="unknown"
    fi
    echo "$state"
}

status_report() {
    echo "=== system_stability_mode 状态 ==="
    echo "[1] sysctl 配置文件"
    if [[ -f "$SYSCTL_CONF" ]]; then
        echo "  - 存在: $SYSCTL_CONF"
        cat "$SYSCTL_CONF"
    else
        echo "  - 未启用"
    fi

    echo "[2] journald 配置"
    if [[ -f "$JOURNALD_CONF" ]]; then
        echo "  - 存在: $JOURNALD_CONF"
        cat "$JOURNALD_CONF"
    else
        echo "  - 未启用"
    fi

    echo "[3] apt 定时器"
    for t in "${APT_TIMERS[@]}"; do
        echo "  - $t: $(unit_state "$t")"
    done

    echo "[4] 关键内核参数"
    sysctl vm.swappiness vm.vfs_cache_pressure vm.dirty_background_ratio vm.dirty_ratio 2>/dev/null || true

    echo "[5] GPU 状态"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu=name,driver_version,persistence_mode --format=csv,noheader 2>/dev/null || true
    else
        echo "  - nvidia-smi 不可用"
    fi

    echo "[6] 运行健康快照"
    free -h | sed -n '1,2p'
    if command -v uptime >/dev/null 2>&1; then
        echo "  - load: $(uptime | awk -F'load average: ' '{print $2}')"
    fi
}

apply_mode() {
    require_root
    echo "[apply] 写入 sysctl 稳定参数"
    apply_sysctl

    echo "[apply] 降低 journald 持久写盘"
    apply_journald

    echo "[apply] 停止并禁用后台更新定时器"
    stop_background_updates

    echo "[apply] 设置电源策略为 balanced"
    set_power_profile

    echo "[apply] 应用 GPU 稳定化"
    apply_gpu_stability

    cat <<EOF

============================================================
系统稳定化模式已应用。

建议下一步:
  1) reboot
  2) 开机后执行状态检查:
     sudo bash scripts/system_stability_mode.sh status
============================================================
EOF
}

revert_mode() {
    require_root
    echo "[revert] 回退 sysctl 配置"
    revert_sysctl

    echo "[revert] 回退 journald 配置"
    revert_journald

    echo "[revert] 恢复后台更新定时器"
    restore_background_updates

    echo "[revert] 回退 GPU 稳定化"
    revert_gpu_stability

    cat <<EOF

============================================================
system_stability_mode 已回退。
如你之前启用了 --disable-gsp, 建议 reboot 后再验证。
============================================================
EOF
}

case "$MODE" in
    apply)
        apply_mode
        ;;
    revert)
        revert_mode
        ;;
    status)
        status_report
        ;;
    *)
        usage
        exit 1
        ;;
esac
