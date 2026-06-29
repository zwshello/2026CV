#!/usr/bin/env bash
# 用系统 python 启动 rqt_image_view, 订阅 /camera/annotated.
# 注意: rqt 依赖 python3-pyqt5, 必须用系统 python 而不是 vision/.venv-train.
#
# 用法:
#   bash scripts/view_annotated.sh                       # 查看 /camera/annotated
#   bash scripts/view_annotated.sh /camera/image_raw     # 查看其它话题
#
# 内存阈值守护 (默认开启):
#   MEM_GUARD_ENABLE=1           # 1=开启, 0=关闭
#   MEM_AVAIL_MIN_MB=1536        # MemAvailable 最低阈值(MB)
#   MEM_GUARD_ACTION=warn        # warn | exit | stop_all
#   MEM_GUARD_INTERVAL=5         # 轮询间隔(秒)
#
# 示例:
#   MEM_AVAIL_MIN_MB=1800 MEM_GUARD_ACTION=stop_all bash scripts/view_annotated.sh
set -e

TOPIC="${1:-/camera/annotated}"
PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

MEM_GUARD_ENABLE="${MEM_GUARD_ENABLE:-1}"
MEM_AVAIL_MIN_MB="${MEM_AVAIL_MIN_MB:-1536}"
MEM_GUARD_ACTION="${MEM_GUARD_ACTION:-warn}"
MEM_GUARD_INTERVAL="${MEM_GUARD_INTERVAL:-5}"

mem_available_mb() {
    awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo
}

on_low_memory() {
    local avail_mb="$1"
    echo "[view_annotated] WARN: MemAvailable=${avail_mb}MB < 阈值 ${MEM_AVAIL_MIN_MB}MB"
    case "$MEM_GUARD_ACTION" in
        warn)
            ;;
        exit)
            echo "[view_annotated] 触发动作: exit (关闭 rqt 预览)"
            kill "$RQT_PID" 2>/dev/null || true
            ;;
        stop_all)
            echo "[view_annotated] 触发动作: stop_all (停止仿真全流程)"
            bash "$PROJ_ROOT/scripts/stop_all.sh" || true
            kill "$RQT_PID" 2>/dev/null || true
            ;;
        *)
            echo "[view_annotated] WARN: 未知 MEM_GUARD_ACTION='$MEM_GUARD_ACTION', 按 warn 处理"
            ;;
    esac
}

# 检查 PyQt5 是否安装
if ! /usr/bin/python3 -c "import PyQt5" 2>/dev/null; then
    echo "[view_annotated] 缺少 python3-pyqt5, 现在安装 (需要 sudo)..."
    sudo apt-get install -y python3-pyqt5 python3-pyqt5.qtsvg
fi

echo "[view_annotated] topic=$TOPIC"
echo "[view_annotated] clean launch: standalone rqt_image_view + clear-config"
echo "[view_annotated] mem_guard: enable=$MEM_GUARD_ENABLE min=${MEM_AVAIL_MIN_MB}MB action=$MEM_GUARD_ACTION interval=${MEM_GUARD_INTERVAL}s"

env \
    -u VIRTUAL_ENV \
    -u PYTHONHOME \
    -u PYTHONPATH \
    -u LD_LIBRARY_PATH \
    -u GTK_PATH \
    -u GIO_EXTRA_MODULES \
    -u QT_PLUGIN_PATH \
    -u QT_QPA_PLATFORMTHEME \
    -u SNAP \
    -u SNAP_NAME \
    -u SNAP_REVISION \
    -u SNAP_ARCH \
    -u SNAP_LIBRARY_PATH \
    -u SNAP_INSTANCE_NAME \
    HOME="$HOME" \
    USER="${USER:-$(id -un)}" \
    LOGNAME="${LOGNAME:-${USER:-$(id -un)}}" \
    DISPLAY="${DISPLAY:-}" \
    XAUTHORITY="${XAUTHORITY:-}" \
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
    WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
    PATH="$SYSTEM_PATH" \
    bash --noprofile --norc -lc '
        set -e
        source /opt/ros/jazzy/setup.bash
        if [[ -f "$1/ros2_ws/install/setup.bash" ]]; then
            source "$1/ros2_ws/install/setup.bash"
        fi
        exec ros2 run rqt_gui rqt_gui \
            --standalone rqt_image_view \
            --clear-config \
            --force-discover \
            --args "$2"
    ' bash "$PROJ_ROOT" "$TOPIC" &

RQT_PID=$!

cleanup() {
    kill "$RQT_PID" 2>/dev/null || true
}
trap cleanup INT TERM

if [[ "$MEM_GUARD_ENABLE" != "1" ]]; then
    wait "$RQT_PID"
    exit $?
fi

while kill -0 "$RQT_PID" 2>/dev/null; do
    avail_mb="$(mem_available_mb)"
    if [[ -n "$avail_mb" ]] && [[ "$avail_mb" -lt "$MEM_AVAIL_MIN_MB" ]]; then
        on_low_memory "$avail_mb"
        if [[ "$MEM_GUARD_ACTION" == "exit" || "$MEM_GUARD_ACTION" == "stop_all" ]]; then
            break
        fi
    fi
    sleep "$MEM_GUARD_INTERVAL"
done

wait "$RQT_PID" || true
