#!/usr/bin/env bash
# 2026CV 环境激活辅助脚本
#
# 用法: 在任何新 bash 会话里 `source scripts/activate_env.sh`
# 它会按顺序挂载:
#   1. ROS 2 Jazzy
#   2. ros2_ws 工作区 (若已 colcon build)
#   3. vision/.venv-train Python venv
# 并把 ROS python site-packages 暴露给 venv（让 yolo_detector 同时
# 看到 rclpy / cv_bridge 与 torch / ultralytics）。
#
# 必须用 source 而不是 bash 执行，否则环境变量不会留在当前 shell。

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: 必须用 'source $(basename "${BASH_SOURCE[0]}")' 来激活" >&2
    exit 1
fi

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. ROS 2 Jazzy
if [[ -f /opt/ros/jazzy/setup.bash ]]; then
    # shellcheck disable=SC1091
    source /opt/ros/jazzy/setup.bash
else
    echo "[activate_env] WARN: /opt/ros/jazzy 未找到，跳过 ROS"
fi

# 2. ros2_ws overlay
if [[ -f "$PROJ_ROOT/ros2_ws/install/setup.bash" ]]; then
    # shellcheck disable=SC1091
    source "$PROJ_ROOT/ros2_ws/install/setup.bash"
else
    echo "[activate_env] INFO: ros2_ws 尚未构建，运行 'cd ros2_ws && colcon build --symlink-install'"
fi

# 3. Python venv
if [[ -f "$PROJ_ROOT/vision/.venv-train/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$PROJ_ROOT/vision/.venv-train/bin/activate"
    # 让 venv python 也能 import rclpy / cv_bridge
    if [[ -d /opt/ros/jazzy/lib/python3.12/site-packages ]]; then
        export PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH:-}"
    fi
else
    echo "[activate_env] INFO: venv 尚未创建，运行 'bash vision/setup_train_env.sh'"
fi

# 4. Gazebo 命令发现修复
# 某些 ROS Jazzy 环境会把 GZ_CONFIG_PATH 覆盖为 vendor 路径，导致 `gz sim`
# 子命令不可见。把 /usr/share/gz 放在最前，保证 PX4/Gazebo world 可启动。
if [[ -d /usr/share/gz ]]; then
    case ":${GZ_CONFIG_PATH:-}:" in
        *":/usr/share/gz:"*)
            ;;
        *)
            export GZ_CONFIG_PATH="/usr/share/gz${GZ_CONFIG_PATH:+:$GZ_CONFIG_PATH}"
            ;;
    esac
fi

echo "[activate_env] PROJ_ROOT=$PROJ_ROOT"
echo "[activate_env] ROS_DISTRO=${ROS_DISTRO:-unset}  python=$(command -v python || echo none)"
echo "[activate_env] GZ_CONFIG_PATH=${GZ_CONFIG_PATH:-unset}"
