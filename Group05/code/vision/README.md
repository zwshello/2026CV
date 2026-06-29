# 视觉模块说明

## 目标

`vision/` 目录放置目标检测与后续跟踪相关代码与训练脚本。

当前计划：

1. 从仿真环境中获取图像（通过 ROS 2 桥接 Gazebo 相机话题）
2. 使用 `YOLOv8` 做目标检测
3. 使用 `OpenCV` 显示与保存检测结果
4. 后续可扩展 `ByteTrack`

## 目录结构

```text
vision/
├─ requirements.txt              # 推理 / 通用依赖
├─ requirements-train.txt        # 训练 venv 依赖（Windows 侧）
├─ setup_train_env.ps1           # Windows：创建训练 venv（PyTorch CUDA 12.1）
├─ setup_infer_env.sh            # Linux：创建推理 venv（CPU 默认 / CUDA 可选）
├─ train_sim.py                  # YOLOv8 微调入口（在 Windows 跑）
├─ summarize_results.py          # JSONL → Markdown 报告（Linux 推理后跑）
├─ run_detection.py              # 离线/在线推理脚本
└─ Dockerfile
```

## venv 分工：Windows 训练 / Linux 推理

当前 Linux 系统跑在 VirtualBox 里，VBox 不支持 NVIDIA GPU 透传，VM 内
`nvidia-smi` 不可用、`torch.cuda.is_available()` 一直为 False。CPU 训
练 yolov8s 太慢，所以训练保留在 Windows 宿主机（RTX 4050），Linux 这边
只装 CPU 版 torch 给 ROS 2 `yolo_detector` 节点加载 `best.pt` 用。

两侧都在 `vision/.venv-train/` 这个目录名下创建 venv，**不会同时存在于
同一台机器**。

### Linux 推理 venv
```bash
cd /home/libo/2026CV
bash vision/setup_infer_env.sh                  # CPU 默认
# 裸机 Linux + NVIDIA 驱动可选：CUDA=cu121 bash vision/setup_infer_env.sh
source /home/libo/2026CV/vision/.venv-train/bin/activate
```
激活后可跑 `summarize_results.py`，并被 `yolo_detector` ROS 2 节点引用。
numpy 锁在 `<2`，避免和 ROS 2 cv_bridge 的 ABI 冲突。

### Windows 训练 venv
```powershell
# Windows PowerShell
pwsh -File vision\setup_train_env.ps1
.\vision\.venv-train\Scripts\Activate.ps1
python vision\train_sim.py --data D:\2026CV\dataset\sim_v1\dataset.yaml
```
训练得到 `runs/sim/v1/weights/best.pt` 后，拷回 Linux 侧
`ros2_ws/yolov8s-sim-v1.pt`，由 `perception_yolo.launch.py` 加载。

## 当前推荐链路（ROS 2 一体化）

```text
PX4 SITL + Gazebo
    ↓ ros_gz_image / ros_gz_bridge
ROS 2 话题 /camera/image_raw
    ↓ low_altitude_bringup yolo_detector
/detections/yolo + /camera/annotated + detections.jsonl
```

具体启动命令见 [docs/ROS2_RUNBOOK.md](../docs/ROS2_RUNBOOK.md) 与
[docs/SIM_TRAINING_PIPELINE.md](../docs/SIM_TRAINING_PIPELINE.md)。

## 历史链路（共享文件）

早期（项目还在 Windows + WSL 阶段）曾使用独立脚本把 Gazebo 帧写到共
享目录、再在 Windows 端 OpenCV 显示。迁移到原生 Ubuntu 后该链路不再
需要，相关脚本（`save_gz_camera_frame.py` / `view_gz_camera.py` /
`view_shared_camera_windows.py`）已从仓库删除，改用 ROS 2 +
`rqt_image_view /camera/annotated` 查看。
