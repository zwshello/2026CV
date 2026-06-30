# 低空目标识别 — 代码运行说明

**课程**：2026CV 计算机视觉  
**组号**：Group 05  
**成员**：李彦博（1231002006）  
**选题**：低空目标识别（任务8）

---

## 一、项目概述

本项目面向低空经济场景下的无人机视觉感知任务，目标是在无人机低空飞行视角中，对远距离、小目标、快速运动目标进行检测与识别。系统基于 **PX4 SITL + Gazebo Harmonic + ROS 2 Jazzy + YOLOv8** 技术栈，构建了完整的"仿真平台 → 数据采集 → 模型训练 → 实时推理"端到端流水线。

### 系统架构

```text
Gazebo Harmonic 仿真环境 (baylands_2026cv 自定义场景)
    ↓
x500 无人机模型 + 机载相机传感器
    ↓
PX4 SITL 飞控仿真
    ↓
QGroundControl 地面站通信 (MAVLink)
    ↓
ROS 2 ros_gz_bridge (相机图像桥接)
    ↓
YOLOv8 目标检测节点 (yolo_detector)
    ↓
实时 HUD 标注显示 + 检测结果 JSON 存档
```

---

## 二、目录结构

```text
Group05/code/
├── vision/                  # 视觉检测与训练模块
│   ├── train_sim.py         # YOLOv8 仿真数据集微调脚本
│   ├── run_detection.py     # 离线/在线推理入口
│   ├── summarize_results.py # JSONL → Markdown 实验报告生成
│   ├── requirements.txt     # 推理依赖
│   ├── requirements-train.txt # 训练依赖
│   ├── setup_train_env.ps1  # Windows 训练环境配置
│   ├── setup_infer_env.sh   # Linux 推理环境配置
│   └── Dockerfile           # Docker 部署配置
├── sim/                     # 仿真场景与目标管理
│   ├── configs/
│   │   └── target_models.yaml    # 目标类别/模型/区域配置
│   ├── launch/
│   │   └── spawn_targets.py      # 在仿真场景中随机放置目标
│   ├── missions/
│   │   └── random_waypoints.py   # 无人机随机巡飞航点生成
│   └── runtime/                  # 运行时 spawn 清单
├── ros2_ws/                 # ROS 2 工作空间
│   ├── src/low_altitude_bringup/ # ROS 2 感知启动包
│   │   ├── launch/               # launch 文件
│   │   ├── config/               # 桥接配置
│   │   └── low_altitude_bringup/ # 核心节点
│   └── yolov8n.pt               # 预训练模型权重
├── scripts/                 # 环境配置与运维脚本
│   ├── activate_env.sh      # 环境激活
│   ├── launch_all.sh        # 一键启动全链路
│   ├── run_demo.sh          # 启动实时检测演示
│   └── quick_health_check.sh # 健康检查
├── demo/                    # 演示资源
│   ├── test_images/         # 测试图片
│   ├── ros2_outputs/        # ROS 2 检测输出
│   └── demo_video/          # 演示视频
├── docs/                    # 技术文档
│   ├── ROS2_RUNBOOK.md      # ROS 2 运行手册
│   ├── SIM_TRAINING_PIPELINE.md # 仿真训练端到端流程
│   └── SYSTEM_FREEZE_*.md   # 系统冻结问题分析与解决
├── PROJECT_PROGRESS.md      # 项目总体进展
├── REPORT_2026_0518.md      # 第三次汇报（算法模块）
└── README.md                # 本文件
```

---

## 三、环境要求

### 硬件要求
- **训练**：NVIDIA GPU（≥6 GB VRAM，推荐 RTX 3060+），Windows 宿主机
- **推理/仿真**：Ubuntu 24.04（原生安装或 VirtualBox），≥16 GB RAM，≥50 GB 磁盘

### 软件依赖

| 组件 | 版本 | 用途 |
|------|------|------|
| Ubuntu | 24.04 LTS | 仿真/推理操作系统 |
| PX4-Autopilot | v1.16.0 | 飞控仿真固件 |
| Gazebo | Harmonic | 3D 仿真引擎 |
| ROS 2 | Jazzy | 机器人中间件 |
| QGroundControl | 最新稳定版 | 地面站 |
| Python | 3.10+ | 训练/推理脚本 |
| PyTorch | 2.x (CUDA 12.1) | 深度学习框架 |
| Ultralytics | ≥8.2 | YOLOv8 |
| OpenCV | ≥4.5 | 图像处理 |

---

## 四、快速开始

### 4.1 Linux 侧：仿真 + ROS 2 推理

```bash
# 1. 激活环境
cd /home/libo/2026CV
source scripts/activate_env.sh

# 2. 安装推理 venv
bash vision/setup_infer_env.sh
source vision/.venv-train/bin/activate

# 3. 构建 ROS 2 工作空间
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash

# 4. 启动 PX4 SITL + Gazebo（终端 A）
cd ~/PX4/PX4-Autopilot
PX4_GZ_WORLD=baylands make px4_sitl gz_x500_gimbal

# 5. Spawn 训练目标（终端 B）
cd /home/libo/2026CV
python3 sim/launch/spawn_targets.py --world baylands --seed 42

# 6. 启动 ROS 2 检测流水线（终端 B）
ros2 launch low_altitude_bringup perception_yolo.launch.py

# 7. 查看检测结果
ros2 run rqt_image_view rqt_image_view /camera/annotated
```

### 4.2 Windows 侧：YOLOv8 模型训练

```powershell
# 1. 创建训练 venv
pwsh -File vision\setup_train_env.ps1

# 2. 激活环境
.\vision\.venv-train\Scripts\Activate.ps1

# 3. 开始训练
python vision\train_sim.py --data D:\2026CV\dataset\sim_v1\dataset.yaml

# 4. 训练完成后，将 best.pt 拷贝到 Linux 侧
# scp runs/sim/v1/weights/best.pt libo@<vm-ip>:/home/libo/2026CV/ros2_ws/yolov8s-sim-v1.pt
```

### 4.3 数据分析与报告

```bash
# 生成检测实验报告
python vision/summarize_results.py \
  --jsonl demo/ros2_outputs/detections.jsonl \
  --output demo/ros2_outputs/report.md
```

---

## 五、核心模块说明

### 5.1 目标检测（YOLOv8）

- **模型**：`yolov8n.pt`（推理）/ `yolov8s.pt`（微调训练）
- **推理流程**：相机话题 → 节流(5Hz) → RGB 转换 → YOLO.predict() → 标注渲染 → HUD 叠加
- **性能指标**：滚动窗口 FPS、推理延迟 P50/P95、各类别累计检测计数

### 5.2 仿真场景

- **世界**：`baylands_2026cv`（基于 baylands 自定义）
- **动态目标**：6 辆巡逻车 + 8 名行人
- **车辆巡逻**：3 辆车沿预设路段自动来回行驶（`animate_vehicles.py`）
- **目标放置**：支持随机 spawn 5 类目标（car/truck/person/cone/boat）

### 5.3 ROS 2 感知流水线

- `parameter_bridge`：Gazebo `/clock` 桥接
- `gazebo_camera_bridge`：相机图像桥接至 `/camera/image_raw`
- `yolo_detector`：YOLOv8 推理 + HUD 叠加 + 性能仪表盘（三合一节点）

---

## 六、常见问题

| 问题 | 原因 | 解决方法 |
|------|------|----------|
| Gazebo 相机话题无图像 | 相机传感器未正确挂载 | 检查 `gz topic -l \| grep camera` |
| `set_pose` 无响应 | 模型设为 static | 去掉 `<static>true</static>` |
| 坐标偏差大 | baylands 中心不在原点 | 实测坐标系确认路段位置 |
| CPU 负载过高 | 物理更新率过高 | 降至 100 Hz |
| `gz` 命令找不到 | GZ_CONFIG_PATH 未设置 | `source scripts/activate_env.sh` |

---

## 七、参考文献

- YOLOv8: https://github.com/ultralytics/ultralytics
- PX4 Autopilot: https://github.com/PX4/PX4-Autopilot
- Gazebo: https://gazebosim.org
- ROS 2: https://docs.ros.org/en/jazzy/
- ByteTrack: https://github.com/ifzhang/ByteTrack
- Yolov7-tracker: https://github.com/JackWoo0831/Yolov7-tracker
