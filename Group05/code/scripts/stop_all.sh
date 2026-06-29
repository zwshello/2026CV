#!/usr/bin/env bash
# 2026CV 一键停止: 关掉 PX4 / Gazebo / ROS2 感知 / 任务进程
set +e

echo "[stop_all] 终止 PX4 / gz sim / ruby (gz wrapper) ..."
pkill -INT -f "px4|gz sim|ruby" 2>/dev/null
sleep 1
pkill -9   -f "px4|gz sim|ruby" 2>/dev/null

echo "[stop_all] 终止 ROS2 launch / yolo_detector / parameter_bridge ..."
pkill -INT -f "ros2 launch low_altitude_bringup|yolo_detector|parameter_bridge|gz_camera_bridge" 2>/dev/null
sleep 1
pkill -9   -f "ros2 launch low_altitude_bringup|yolo_detector|parameter_bridge|gz_camera_bridge" 2>/dev/null

echo "[stop_all] 终止 random_waypoints 任务 (若有) ..."
pkill -9 -f "random_waypoints.py" 2>/dev/null

echo "[stop_all] 清理完成. 残留进程检查:"
pgrep -af "px4|gz sim|ros2 launch low_altitude|yolo_detector|random_waypoints" || echo "  (无残留)"
