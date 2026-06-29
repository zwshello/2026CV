# 系统卡死排障结论（2026-05-10）

## 一句话结论

是，核心问题是内存配置不足（在当前 VirtualBox 环境下），导致频繁 swap 抖动，最终表现为“系统接近卡死”。

## 背景与现象

在完整链路运行（PX4 + Gazebo + ROS2 感知 + QGC）一段时间后，系统明显变慢；执行 `bash scripts/stop_all.sh` 后恢复。

典型现象：

1. 不需要手动起飞，静置也会逐渐变卡。
2. 外置盘温度升高明显。
3. 停止链路后卡顿缓解。

## 关键证据（来自 quick_health_check 输出）

1. 内存与交换区压力极高：
   - 内存 14Gi 中已用约 13Gi，可用约 1.0Gi。
   - 交换区 3.8Gi 中已用约 2.6Gi。
2. 负载升高：
   - `load average: 10.00, 4.44, 2.67`。
3. 进程内存大户：
   - `gz sim --verbose ...` 占用约 69.4% 内存。
4. I/O 呈现 swap 特征：
   - `sda` 持续读写（读 136/s，写 422/s 量级），与内存不足导致的换页行为一致。
5. 内核严重错误特征缺失：
   - 未见 OOM kill / hung_task / I/O error / USB reset 等硬错误关键词。

## 为什么 stop_all 后会恢复

`stop_all.sh` 会终止 PX4、Gazebo、ROS2 感知等核心高负载进程，系统内存与 swap 压力快速下降，因此交互恢复流畅。

## 关于“硬盘很烫”

当前更像是 swap 持续读写导致的热量上升，而不是单纯日志写盘造成。即使已将 `launch_all.sh` 默认改为不写盘日志，若总内存不足，仍会发生高强度换页。

## 是否还有其他可能

有，但优先级低于“内存不足”：

1. Gazebo GUI 与 QGC 同时运行造成额外显存/内存占用。
2. rqt 图像查看器额外占用资源（若同时开启）。
3. VM 图形与虚拟硬件配置不合理（CPU/内存/3D 设置）。

## 推荐修复顺序

1. 提高虚拟机内存配额（优先）：建议至少 24Gi，理想 32Gi。
2. 先关闭可选 GUI：
   - 不开 `view_annotated.sh`。
   - 非必要时不同时开 QGC。
3. 保持默认不写盘日志：
   - 当前 `launch_all.sh` 默认 `LOG_TO_DISK=0`。
4. 若需要日志，优先写到临时目录：
   - `LOG_TO_DISK=1 LOG_DIR=/tmp/launch_logs bash scripts/launch_all.sh`

## 标准验证流程

1. 开取证：

```bash
sudo bash scripts/freeze_probe.sh start
```

2. 启动链路（默认不写盘日志）：

```bash
bash scripts/launch_all.sh
```

3. 发生卡顿时采样：

```bash
bash scripts/quick_health_check.sh
```

4. 停止链路与取证：

```bash
bash scripts/stop_all.sh
sudo bash scripts/freeze_probe.sh stop
```

5. 查看关键日志末尾：

```bash
tail -n 120 /tmp/freeze_probe/io.log
tail -n 120 /tmp/freeze_probe/kern.log
tail -n 120 /tmp/freeze_probe/sys.log
```

## 常见路径错误说明

如果当前目录在项目根目录 `~/2026CV`，应使用：

```bash
sudo bash scripts/freeze_probe.sh start
```

不要在项目根目录直接执行 `sudo bash freeze_probe.sh start`，否则会提示“没有那个文件或目录”。

## 最终判断

当前阶段可以把“内存配置不足导致 swap 抖动”视为第一根因。后续若在提升 VM 内存后仍复现，再进入第二阶段（逐项隔离 QGC、rqt、ROS2 感知链路）。
