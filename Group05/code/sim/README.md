# sim/ — 训练目标与航迹生成

`sim/` 收集与仿真世界相关的脚本与配置。当前重点是为 YOLO 微调流程提供
**目标 spawn** 与 **数据采集飞行任务**。

## 目录速览

```text
sim/
├─ configs/
│  └─ target_models.yaml      # 类别 + Fuel 模型 + AABB 大小 + 采样区域
├─ launch/
│  └─ spawn_targets.py        # 调用 gz service 在 baylands 随机放目标
├─ missions/
│  └─ random_waypoints.py     # 通过 MAVSDK 让无人机随机巡飞
└─ runtime/                   # 运行时生成的 spawn manifest（gitignore）
```

## 典型工作流

```bash
# 1. 启动 PX4 SITL（Gazebo baylands）
cd ~/PX4/PX4-Autopilot
GZ_CONFIG_PATH=/usr/share/gz PX4_GZ_WORLD=baylands make px4_sitl gz_x500_gimbal

# 2. 在 Gazebo 已运行的世界里 spawn 目标
python3 sim/launch/spawn_targets.py --world baylands --seed 42

# 3. 启动数据采集
ros2 launch low_altitude_bringup dataset_collect.launch.py \
    output_dir:=/home/libo/2026CV/dataset/sim_v1 target_total_frames:=5000

# 4. 让无人机随机巡飞 ~40 分钟
python3 sim/missions/random_waypoints.py --duration 2400 --seed 7
```

如果看到 `The 'gz' command provides...` 且一直 `Waiting for Gazebo world`，通常是
`gz sim` 子命令没有被发现。先检查：

```bash
GZ_CONFIG_PATH=/usr/share/gz gz --commands | grep -E '^  sim:'
```

若有输出，再启动 PX4。没有输出时请先 `source scripts/activate_env.sh`，它会自动修复
`GZ_CONFIG_PATH` 的优先级。

完整流程见 [docs/SIM_TRAINING_PIPELINE.md](../docs/SIM_TRAINING_PIPELINE.md)。

## 修改类别 / 模型 / 区域

`configs/target_models.yaml` 是 spawner 与 collector 的唯一真相来源。
- 加类别：在 `classes:` 下追加条目，`id` 必须从 0 起连号。
- 改 AABB：`aabb_size: [length, width, height]`（米），偏大没关系，偏小标签会扣不住目标。
- 改区域：`spawn_area.{x_range, y_range}`；`boat` 使用 `water_z`。

改完 yaml，spawn_targets / dataset_collector / build_yolo_dataset 都会自动跟进。
