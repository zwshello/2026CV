# 系统卡死问题端到端复盘（从首次卡死到当前方案）

更新时间：2026-05-11

## 1. 问题起点

项目在完整链路运行时（PX4 + Gazebo + ROS2 感知 + 可视化）会逐步变卡，最终接近卡死。

最早观察到的现象：

1. 不起飞也会随时间变慢。
2. 停止流程后系统明显恢复。
3. 外设温度升高，交互延迟明显。

## 2. 诊断过程与关键转折

### 2.1 第一阶段：确认是内存压力，不是单点崩溃

通过脚本取证与系统采样，确认不是内核硬错误主导，而是内存与 swap 压力持续累积。

关键工具：

1. scripts/freeze_probe.sh（内核、系统、I/O 持续采样）
2. scripts/quick_health_check.sh（负载、内存、I/O、关键进程快照）

### 2.2 第二阶段：修复仿真启动链稳定性

中途出现过 Gazebo 启动异常与版本冲突，先完成了基础稳定性修复：

1. 清理冲突版本（保留可用版本链路）
2. 修复 GZ 配置路径覆盖问题
3. 验证 PX4 + Gazebo 能稳定拉起

这一阶段解决了“起不来/崩”的问题，但没有解决“运行久了 RAM 持续增长”的问题。

### 2.3 第三阶段：确认 GPU 已启用但不能根治 RAM 增长

确认 Gazebo 已在 NVIDIA GPU 上运行，但 RAM 仍持续增加。

结论：

1. GPU 主要加速渲染，不会自动消除主机内存中的传输与缓冲积压。
2. 问题核心不在“是否启用 GPU”，而在“相机数据流在链路中的累计方式”。

### 2.4 第四阶段：定位到主增长进程

通过连续采样关键进程 RSS，观察到主要增长发生在 Gazebo server 所在进程（显示为 ruby 进程入口）。

同时观察到：

1. parameter_bridge 与 image_throttle 占用相对稳定。
2. yolo 侧并非主内存增长源。

结论：

主增长发生在更前段（Gazebo 相机与传输链），不是仅靠后段推理节流就能彻底解决。

## 3. 根因结论（当前版本）

这是一个“前段高吞吐 + 中间缓冲累积”的系统性问题。

具体是：

1. 相机源头输出分辨率和帧率较高。
2. Gazebo 内部与桥接链路存在缓存积压空间。
3. 后段消费速率无法长期匹配前段生产速率时，RAM 会线性增长。

因此，单纯提升后段处理能力不够；必须同时做源头降流和链路有界化。

## 4. 已落地的解决措施

### 4.1 链路有界化：中间缓冲区（latest-only relay）

在 ROS2 链路加入 image_throttle 节点，策略为“只保留最新帧，丢弃旧帧”，并可按频率重发。

关联文件：

1. ros2_ws/src/low_altitude_bringup/low_altitude_bringup/image_throttle.py
2. ros2_ws/src/low_altitude_bringup/launch/perception_yolo.launch.py
3. ros2_ws/src/low_altitude_bringup/setup.py
4. ros2_ws/src/low_altitude_bringup/low_altitude_bringup/yolo_detector.py

效果：

1. 后段内存由无界趋势变为有界。
2. 检测链路可持续运行，实时性更稳定。

### 4.2 源头降流：自定义相机模型

为避免修改官方文件，建立自定义 Gazebo 资源层，在用户目录复制并调整相机参数。

当前自定义相机参数已调至更清晰且相对稳态的挡位：

1. 640x360
2. 10Hz

关联路径：

1. sim/custom_gz/models/gimbal/model.sdf
2. sim/custom_gz/models/x500_gimbal/model.sdf
3. sim/custom_gz/models/x500_gimbal/model.config

### 4.3 自定义场景：以 baylands 为蓝本

建立自定义世界文件，不改官方场景文件。

关联路径：

1. sim/custom_gz/worlds/baylands_2026cv.sdf
2. sim/custom_gz/worlds/default_2026cv.sdf

### 4.4 启动链路改造：默认走自定义资源

启动脚本支持并默认启用自定义 Gazebo 资源层，同时处理 PX4 对 world 路径的硬编码约束（通过新增 symlink 的方式注入自定义 world 文件，不覆盖官方原文件）。

关联文件：

1. scripts/launch_all.sh

### 4.5 运行保护：可视化脚本内存阈值守护

图像查看脚本增加内存阈值监控，当可用内存低于阈值时可告警、退出或触发 stop_all。

关联文件：

1. scripts/view_annotated.sh

## 5. 当前推荐运行方式

1. 使用默认启动（已启用自定义场景与自定义模型）：
   bash scripts/launch_all.sh
2. 需要进一步压内存时，降低 throttle 参数或降低相机更新率。
3. 使用图像查看时启用内存守护动作：
   MEM_AVAIL_MIN_MB=2048 MEM_GUARD_ACTION=stop_all bash scripts/view_annotated.sh

## 6. 验证方法（每次调参后执行）

1. 检查相机输入实际帧率：
   timeout 5 ros2 topic hz /camera/image_raw
2. 检查相机分辨率：
   ros2 topic echo /camera/image_raw --once
3. 连续观测关键进程 RSS：
   ps -o pid,rss,comm -C ruby,parameter_bridge,image_throttle,yolo_detector
4. 结合系统内存快照：
   free -h

判定原则：

1. 若 ruby 进程 RSS 不再快速线性上升，说明源头与链路控制有效。
2. 若画面质量不足，优先上调分辨率，再评估内存斜率。
3. 若内存再次逼近阈值，优先降帧率而非仅调后段。

## 7. 本次问题的最终结论

从“系统卡死”走到“可长期运行”的关键不是单点优化，而是分层治理：

1. 先保启动稳定。
2. 再做链路有界化。
3. 最后做源头降流并使用自定义资源层隔离官方文件。

当前方案已经把问题从“必然卡死”降到“可控调参下稳定运行”，并保留了画质与稳定性的可调空间。