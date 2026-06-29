#!/usr/bin/env bash
# Quick runtime health snapshot for PX4/Gazebo/ROS2 chain.
set -euo pipefail

echo "=== quick_health_check ==="
date --iso-8601=seconds

echo
if command -v uptime >/dev/null 2>&1; then
    echo "[load]"
    uptime
fi

echo
if command -v free >/dev/null 2>&1; then
    echo "[memory]"
    free -h
fi

echo
if command -v iostat >/dev/null 2>&1; then
    echo "[iostat]"
    iostat -xz 1 1 || true
else
    echo "[iostat] not available (install sysstat for better IO metrics)"
fi

echo
echo "[top cpu: px4/gz/ros2/python]"
ps -eo pid,comm,state,%cpu,%mem,etime,args --sort=-%cpu \
  | grep -E "px4|gz sim|ros2|python3|yolo_detector|parameter_bridge|mavsdk" \
  | grep -v grep \
  | head -n 30 || true

echo
echo "[top io write: pidstat if available]"
if command -v pidstat >/dev/null 2>&1; then
    pidstat -d 1 1 | sed -n '1,40p' || true
else
    echo "pidstat not available (install sysstat)"
fi

echo
echo "[disk temp: nvme/sda via smartctl if available]"
if command -v smartctl >/dev/null 2>&1; then
    smartctl -A /dev/sda 2>/dev/null | grep -Ei "temp|temperature" || true
    smartctl -A /dev/nvme0 2>/dev/null | grep -Ei "temp|temperature" || true
else
    echo "smartctl not available (install smartmontools)"
fi

echo
echo "=== end ==="
