#!/usr/bin/env bash
# 2026CV 一键启动全流程 (精简版)
#
# 必须在 Ubuntu 系统终端 (Ctrl+Alt+T) 中运行, 不要在 VS Code Snap 终端运行.
#
# 用法:
#   bash scripts/launch_all.sh                 # 默认 world=baylands_2026cv (自定义场景)
#   WORLD=baylands bash scripts/launch_all.sh  # 显式切换官方 baylands 世界
#   WITH_MISSION=1 bash scripts/launch_all.sh  # 额外开窗口跑随机航点任务
#   EXTRA_GUI=1 bash scripts/launch_all.sh     # 在 PX4 自带 GUI 之外再开一个 gz sim -g
#   CONF=0.25 bash scripts/launch_all.sh       # 自定义 YOLO 置信度阈值 (默认 0.15)
#   IMGSZ=320 bash scripts/launch_all.sh       # 推理分辨率 (320/416/480/640, 默认 480, 越小越快)
#   SKIP=2 bash scripts/launch_all.sh          # 每 N 帧推理一次 (默认 1=每帧推理)
#   DEVICE=0 bash scripts/launch_all.sh        # 强制使用 GPU 0 (默认空=ultralytics 自动选)
#   DEVICE=cpu bash scripts/launch_all.sh      # 强制使用 CPU
#   LOG_TO_DISK=0 bash scripts/launch_all.sh   # 禁止写盘日志 (默认)
#   LOG_TO_DISK=1 LOG_DIR=/tmp/launch_logs bash scripts/launch_all.sh  # 写到临时盘
#
# 中间缓冲区 (image_throttle, 默认开启, 抑制 RAM 增长):
#   THROTTLE_HZ=5             # 节点重发频率 (默认 5Hz, 调高到 30 等于不限流)
#   THROTTLE_W=320 THROTTLE_H=240   # 重发前缩放到小分辨率 (默认 0,0 = 不缩放)
#
# 自定义 Gazebo 资源覆盖层 (默认开启, 不改官方文件):
#   USE_CUSTOM_GZ=1 bash scripts/launch_all.sh
#   CUSTOM_GZ_ROOT=/home/libo/2026CV/sim/custom_gz bash scripts/launch_all.sh
#
# 三/四个独立终端窗口:
#   1_px4_sitl         — PX4 + Gazebo server (含自带 GUI)
#   2_gz_gui_extra     — (可选, EXTRA_GUI=1) 第二个 gz sim -g 客户端
#   3_ros2_perception  — ros_gz_bridge (clock+image) + yolo_detector
#   4_mission          — (可选, WITH_MISSION=1) MAVSDK 随机航点任务
#
# 看注释后图像:  bash scripts/view_annotated.sh
# 一键停止:      bash scripts/stop_all.sh

set -e

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-$HOME/PX4/PX4-Autopilot}"
USE_CUSTOM_GZ="${USE_CUSTOM_GZ:-1}"
CUSTOM_GZ_ROOT="${CUSTOM_GZ_ROOT:-$PROJ_ROOT/sim/custom_gz}"
WORLD="${WORLD:-}"
WITH_MISSION="${WITH_MISSION:-0}"
EXTRA_GUI="${EXTRA_GUI:-0}"
CONF="${CONF:-0.15}"
IMGSZ="${IMGSZ:-480}"
SKIP="${SKIP:-1}"
DEVICE="${DEVICE:-}"
LOG_TO_DISK="${LOG_TO_DISK:-}"
LOG_DIR="${LOG_DIR:-}"

# image_throttle (中间缓冲区) 参数
THROTTLE_HZ="${THROTTLE_HZ:-5.0}"
THROTTLE_W="${THROTTLE_W:-0}"
THROTTLE_H="${THROTTLE_H:-0}"

CUSTOM_GZ_MODELS="$CUSTOM_GZ_ROOT/models"
CUSTOM_GZ_WORLDS="$CUSTOM_GZ_ROOT/worlds"

if [[ -z "$WORLD" ]]; then
    if [[ "$USE_CUSTOM_GZ" == "1" ]]; then
        WORLD="baylands_2026cv"
    else
        WORLD="default"
    fi
fi

if [[ -z "$LOG_TO_DISK" ]]; then
    LOG_TO_DISK="0"
fi

if [[ -z "$LOG_DIR" ]]; then
    if [[ "$LOG_TO_DISK" == "1" ]]; then
        LOG_DIR="$PROJ_ROOT/demo/ros2_outputs/launch_logs"
    else
        LOG_DIR="/tmp/2026cv_launch_logs"
    fi
fi

mkdir -p "$LOG_DIR"

# 默认始终开启 HUD/仪表盘/结果记录，便于实时观察状态。
ENABLE_HUD="true"
ENABLE_DASHBOARD="true"
USE_RICH="true"
RECORD_RESULTS="true"

# ---- 选择终端模拟器 ----------------------------------------------------------
TERM_CMD=""
if command -v gnome-terminal >/dev/null 2>&1; then
    TERM_CMD="gnome-terminal"
elif command -v xterm >/dev/null 2>&1; then
    TERM_CMD="xterm"
fi

spawn() {
    local title="$1"; shift
    local logfile="$LOG_DIR/${title}.log"
    local cmd="$*"
    local wrapped
    if [[ "$LOG_TO_DISK" == "1" ]]; then
        # 调试模式写盘日志; 性能模式可关闭以避免外置盘持续高温写入。
        wrapped="echo '== $title =='; { $cmd; } 2>&1 | tee '$logfile'; rc=\${PIPESTATUS[0]}; echo; echo \"[exit] $title rc=\$rc, 日志: $logfile\"; echo '按回车关闭窗口'; read"
        echo "[launch_all] -> $title  (log: $logfile)"
    else
        wrapped="echo '== $title =='; { $cmd; }; rc=\$?; echo; echo \"[exit] $title rc=\$rc\"; echo '按回车关闭窗口'; read"
        echo "[launch_all] -> $title  (disk log: off)"
    fi
    case "$TERM_CMD" in
        gnome-terminal)
            gnome-terminal --title="$title" -- bash -lc "$wrapped" >/dev/null 2>&1 &
            ;;
        xterm)
            xterm -T "$title" -e bash -lc "$wrapped" &
            ;;
        *)
            echo "[launch_all]   (无终端模拟器, 后台运行)"
            if [[ "$LOG_TO_DISK" == "1" ]]; then
                nohup bash -lc "$cmd" > "$logfile" 2>&1 &
            else
                nohup bash -lc "$cmd" > /dev/null 2>&1 &
            fi
            ;;
    esac
}

# ---- 前置检查 ---------------------------------------------------------------
[[ -d "$PX4_DIR" ]] || { echo "ERROR: PX4 目录不存在: $PX4_DIR"; exit 1; }

if [[ "$USE_CUSTOM_GZ" == "1" ]]; then
    [[ -d "$CUSTOM_GZ_MODELS" ]] || { echo "ERROR: 自定义模型目录不存在: $CUSTOM_GZ_MODELS"; exit 1; }
    [[ -d "$CUSTOM_GZ_WORLDS" ]] || { echo "ERROR: 自定义场景目录不存在: $CUSTOM_GZ_WORLDS"; exit 1; }
fi

# ---- 自定义资源注入 PX4 目录 (symlink 方式, 不修改任何官方文件) ----------------
# 原因: PX4 在 etc/init.d-posix/rcS 里把世界路径硬编码到
#   $PX4_DIR/Tools/simulation/gz/worlds/<WORLD>.sdf
# 而模型则按 GZ_SIM_RESOURCE_PATH 顺序检索. 为了让 PX4 找到我们的自定义
# baylands_2026cv 世界, 同时让 x500_gimbal/gimbal 用我们自己的 320x240@10Hz
# 副本, 在启动前为每个自定义资产在 PX4 目录里建立 symlink. symlink 是新建文件,
# 不会覆盖官方 default.sdf / baylands.sdf 等原版.
inject_symlink() {
    local src="$1"
    local dst="$2"
    if [[ ! -e "$src" ]]; then
        return 0
    fi
    if [[ -L "$dst" ]]; then
        ln -sfn "$src" "$dst"
    elif [[ -e "$dst" ]]; then
        echo "[launch_all] WARN: $dst 是官方真实文件, 跳过 symlink (避免覆盖). 改名你的自定义资产即可绕过."
    else
        ln -s "$src" "$dst"
    fi
}

if [[ "$USE_CUSTOM_GZ" == "1" ]]; then
    PX4_WORLDS_DIR="$PX4_DIR/Tools/simulation/gz/worlds"
    mkdir -p "$PX4_WORLDS_DIR"

    # 只为 worlds 建 symlink (PX4 启动脚本硬编码这个目录).
    # 模型通过 GZ_SIM_RESOURCE_PATH 前置就能命中我们的副本, 无需动 PX4 模型目录.
    for w in "$CUSTOM_GZ_WORLDS"/*.sdf; do
        [[ -e "$w" ]] || continue
        inject_symlink "$w" "$PX4_WORLDS_DIR/$(basename "$w")"
    done
    echo "[launch_all] 自定义世界 symlink 注入完成: $PX4_WORLDS_DIR/"
    echo "[launch_all] 自定义模型走 GZ_SIM_RESOURCE_PATH 前置, 不触碰 PX4 模型目录."
fi

if [[ ! -f "$PROJ_ROOT/ros2_ws/install/setup.bash" ]]; then
    echo "[launch_all] ros2_ws 未构建, 现在构建..."
    (cd "$PROJ_ROOT/ros2_ws" && source /opt/ros/jazzy/setup.bash && \
     colcon build --packages-select low_altitude_bringup --symlink-install)
fi

if env | grep -qE '^SNAP(_|=)'; then
    echo "[launch_all] WARN: 当前 shell 检测到 SNAP 环境变量, Gazebo GUI 可能崩溃."
    echo "             请用系统终端 (Ctrl+Alt+T), 不要在 VS Code Snap 终端运行此脚本."
fi

# 修正 ament_python 入口脚本 shebang -> venv python (含 ultralytics+torch)
VENV_PY="$PROJ_ROOT/vision/.venv-train/bin/python"
if [[ -x "$VENV_PY" ]]; then
    for f in "$PROJ_ROOT/ros2_ws/install/low_altitude_bringup/lib/low_altitude_bringup"/*; do
        [[ -f "$f" ]] || continue
        if head -c 200 "$f" 2>/dev/null | head -1 | grep -qE '^#!.*python'; then
            sed -i "1c #!$VENV_PY" "$f"
        fi
    done
fi

# 根据 world 拼出 gz 相机话题
GZ_IMG="/world/${WORLD}/model/x500_gimbal_0/link/camera_link/sensor/camera/image"

if [[ "$USE_CUSTOM_GZ" == "1" ]]; then
    if [[ -n "${GZ_SIM_RESOURCE_PATH:-}" ]]; then
        GZ_SIM_RESOURCE_PATH_EFFECTIVE="$CUSTOM_GZ_MODELS:$CUSTOM_GZ_WORLDS:$GZ_SIM_RESOURCE_PATH"
    else
        GZ_SIM_RESOURCE_PATH_EFFECTIVE="$CUSTOM_GZ_MODELS:$CUSTOM_GZ_WORLDS"
    fi
else
    GZ_SIM_RESOURCE_PATH_EFFECTIVE="${GZ_SIM_RESOURCE_PATH:-}"
fi

cat <<EOF
============================================================
2026CV 一键启动
  PX4_DIR     = $PX4_DIR
  WORLD       = $WORLD
  GZ_IMG      = $GZ_IMG
  CONFIDENCE  = $CONF
  IMGSZ       = $IMGSZ
    SKIP        = $SKIP
    DEVICE      = ${DEVICE:-auto}
  WITH_MISSION= $WITH_MISSION
  EXTRA_GUI   = $EXTRA_GUI
    LOG_TO_DISK = $LOG_TO_DISK
  日志目录    = $LOG_DIR
  终端        = ${TERM_CMD:-后台 (无窗口)}
  THROTTLE    = ${THROTTLE_HZ} Hz, resize=${THROTTLE_W}x${THROTTLE_H} (0=passthrough)
    USE_CUSTOM_GZ = $USE_CUSTOM_GZ
    CUSTOM_GZ_ROOT= $CUSTOM_GZ_ROOT
============================================================
EOF

# ---- 1) PX4 SITL + Gazebo server (含自带 GUI) -------------------------------
spawn "1_px4_sitl" "cd '$PX4_DIR' && export GZ_CONFIG_PATH=/usr/share/gz && export GZ_SIM_RESOURCE_PATH='$GZ_SIM_RESOURCE_PATH_EFFECTIVE' && PX4_GZ_WORLD='$WORLD' make px4_sitl gz_x500_gimbal"

# ---- 2) (可选) 额外 Gazebo GUI 客户端 ---------------------------------------
if [[ "$EXTRA_GUI" == "1" ]]; then
    sleep 8
    spawn "2_gz_gui_extra" "export GZ_CONFIG_PATH=/usr/share/gz; export QT_QPA_PLATFORM=xcb; gz sim -g"
fi

# ---- 3) ROS2 感知 (ros_gz_bridge + yolo_detector) --------------------------
PERCEPTION_WAIT="${PERCEPTION_WAIT:-15}"
echo "[launch_all] 等待 ${PERCEPTION_WAIT} 秒让 PX4/Gazebo 启动并发布相机话题..."
sleep "$PERCEPTION_WAIT"
DEVICE_ARG=""
if [[ -n "$DEVICE" ]]; then
    DEVICE_ARG=" device:='$DEVICE'"
fi
ROS_CMD="source '$PROJ_ROOT/scripts/activate_env.sh' && cd '$PROJ_ROOT' && \
ros2 launch low_altitude_bringup perception_yolo.launch.py \
    gz_image_topic:='$GZ_IMG' confidence:='$CONF' imgsz:='$IMGSZ' report_every_n_frames:='$SKIP'${DEVICE_ARG} \
    throttle_hz:='$THROTTLE_HZ' throttle_width:='$THROTTLE_W' throttle_height:='$THROTTLE_H' \
    enable_hud:='$ENABLE_HUD' enable_dashboard:='$ENABLE_DASHBOARD' use_rich:='$USE_RICH' \
    record_results:='$RECORD_RESULTS'"
spawn "3_ros2_perception" "$ROS_CMD"

# ---- 4) 随机航点任务 (可选) -------------------------------------------------
if [[ "$WITH_MISSION" == "1" ]]; then
    sleep 10
    MISSION_CMD="source '$PROJ_ROOT/scripts/activate_env.sh' && \
python3 '$PROJ_ROOT/sim/missions/random_waypoints.py' --duration 600 \
  --min-alt 30 --max-alt 80 --x-range -100 100 --y-range -100 100"
    spawn "4_mission" "$MISSION_CMD"
fi

cat <<EOF

[launch_all] 派发完毕. 后续:
  * 看注释后图像:    bash scripts/view_annotated.sh
  * 检测话题:        ros2 topic echo /detections/yolo --once
  * 帧率检查:        ros2 topic hz /camera/image_raw
  * 一键停止:        bash scripts/stop_all.sh

EOF
