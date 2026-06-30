#!/usr/bin/env bash
# 2026CV one-shot demo launcher.
# Run inside Ubuntu 24.04. Requires PX4 SITL already running in another terminal:
#   cd ~/PX4/PX4-Autopilot && PX4_GZ_WORLD=baylands make px4_sitl gz_x500_gimbal
set -e

WS_ROOT="${WS_ROOT:-/home/libo/2026CV/ros2_ws}"

if [ ! -f "$WS_ROOT/install/setup.bash" ]; then
  echo "[run_demo] colcon install not found at $WS_ROOT/install. Building first..."
  (cd "$WS_ROOT" && source /opt/ros/jazzy/setup.bash && \
   colcon build --packages-select low_altitude_bringup --symlink-install)
fi

source /opt/ros/jazzy/setup.bash
source "$WS_ROOT/install/setup.bash"

cat <<EOF
[run_demo] Launching: perception_yolo.launch.py
  - parameter_bridge   -> /clock
  - gz_camera_bridge   -> /camera/image_raw
  - yolo_detector      -> /detections/yolo + /camera/annotated (with HUD + rich dashboard)

View the annotated stream in another terminal:
  source /opt/ros/jazzy/setup.bash
  ros2 run rqt_image_view rqt_image_view /camera/annotated

Make sure PX4 SITL is already running:
  cd ~/PX4/PX4-Autopilot && PX4_GZ_WORLD=baylands make px4_sitl gz_x500_gimbal

Press Ctrl+C to stop.
EOF

ros2 launch low_altitude_bringup perception_yolo.launch.py "$@"
