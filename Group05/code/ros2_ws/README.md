# ROS 2 工作空间

本工作空间将仓库升级为更完整的
`PX4 + Gazebo + ROS 2 + 视觉` 学习项目。

## 包含内容

1. `low_altitude_bringup` ROS 2 包骨架
2. `/clock` 的 `ros_gz_bridge` 配置
3. Gazebo 相机话题的 `ros_gz_image` 集成
4. `image_snapshot`：将周期性的 ROS 2 图像帧保存到磁盘
5. `yolo_detector`：运行时配置后的 ROS 2 检测入口节点
6. HUD 叠加 + 富信息仪表盘合并到 `yolo_detector` 中
7. 模块化辅助工具：`metrics.py`、`hud.py`、`dashboard.py`、`results_recorder.py`
8. JSONL 检测日志 + 滚动 `summary.json` 产物，用于离线报告

## 推荐工作流

1. 启动 PX4 和 Gazebo
2. 将 Gazebo 相机话题桥接到 ROS 2
3. 需要快速截图到磁盘时，使用 `image_snapshot` 保存样本帧
4. 安装 YOLO 运行时依赖后，切换到 `yolo_detector`
5. 使用内置的 HUD 叠加和仪表盘验证吞吐量和延迟
6. 开始闭环工作时，添加 `px4_msgs` 和 `Micro XRCE-DDS Agent`

## 目录结构

```text
ros2_ws/
|-- src/
|   `-- low_altitude_bringup/
`-- README.md
```

## 构建

```bash
source /opt/ros/jazzy/setup.bash
cd /home/libo/2026CV/ros2_ws
colcon build
source install/setup.bash
```

## 启动选项

仅桥接：

```bash
ros2 launch low_altitude_bringup sim_bridge.launch.py \
  gz_image_topic:=/world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image
```

桥接 + 调试感知节点：

```bash
ros2 launch low_altitude_bringup perception_yolo.launch.py \
  gz_image_topic:=/world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image \
  enable_hud:=true \
  enable_dashboard:=true
```

桥接 + YOLO 检测器：

```bash
ros2 launch low_altitude_bringup perception_yolo.launch.py \
  gz_image_topic:=/world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image \
  model_path:=yolov8n.pt \
  enable_hud:=true \
  enable_dashboard:=true
```

检测器将快照写入：

```text
/home/libo/2026CV/demo/ros2_outputs
```

## 注意事项

1. 当前启动默认值假定使用 `baylands` 世界和 `x500_gimbal_0` 模型。
2. 如果切换世界或模型，请在启动时更新 `gz_image_topic`。
3. `gz_bridge_clock.yaml` 仅处理 `/clock`；图像传输由 `ros_gz_image` 处理。
4. 感知流水线已简化为 3 进程启动：bridge、camera bridge 和 `yolo_detector`。
