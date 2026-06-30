#!/usr/bin/env bash
# 一键安装 QGroundControl (官方 AppImage) on Ubuntu 22.04 / 24.04.
# 步骤完全按 https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html#ubuntu
#
# 用法:
#   bash scripts/install_qgc.sh
#
# 安装后:
#   ~/QGroundControl/QGroundControl.AppImage
# 启动:
#   ~/QGroundControl/QGroundControl.AppImage

set -e

INSTALL_DIR="$HOME/QGroundControl"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# ---- 1) 串口权限 ------------------------------------------------------------
echo "[install_qgc] (1/5) 把当前用户加到 dialout 组"
sudo usermod -aG dialout "$(id -un)" || true

# ---- 2) 屏蔽 ModemManager (避免占用串口) -------------------------------------
echo "[install_qgc] (2/5) 屏蔽 ModemManager 服务"
sudo systemctl mask --now ModemManager.service 2>/dev/null || true

# ---- 3) 安装依赖 ------------------------------------------------------------
echo "[install_qgc] (3/5) 安装 GStreamer / Qt / libfuse2 等运行时依赖"
sudo apt-get update
sudo apt-get install -y \
    gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl \
    python3-gi python3-gst-1.0 \
    libfuse2 \
    libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor-dev

# ---- 4) 下载 AppImage --------------------------------------------------------
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  APPIMG="QGroundControl-x86_64.AppImage" ;;
    aarch64) APPIMG="QGroundControl-aarch64.AppImage" ;;
    *)       echo "ERROR: 不支持的架构: $ARCH"; exit 1 ;;
esac

# 尝试多个镜像源 (CloudFront 偶尔 403, GitHub Releases 通常稳)
URLS=(
    "https://github.com/mavlink/qgroundcontrol/releases/latest/download/$APPIMG"
    "https://d176tv9ibo4jno.cloudfront.net/latest/$APPIMG"
)

if [[ ! -f "$APPIMG" || $(stat -c %s "$APPIMG" 2>/dev/null || echo 0) -lt 50000000 ]]; then
    for url in "${URLS[@]}"; do
        echo "[install_qgc] (4/5) 尝试下载: $url"
        if curl -L --connect-timeout 15 --retry 3 -o "$APPIMG.part" "$url"; then
            sz=$(stat -c %s "$APPIMG.part" 2>/dev/null || echo 0)
            if [[ "$sz" -gt 50000000 ]]; then
                mv "$APPIMG.part" "$APPIMG"
                echo "[install_qgc]    下载完成: $(du -h "$APPIMG" | cut -f1)"
                break
            else
                echo "[install_qgc]    文件太小 ($sz B), 换源重试"
                rm -f "$APPIMG.part"
            fi
        fi
    done
fi

if [[ ! -f "$APPIMG" ]]; then
    echo "ERROR: 所有下载源都失败. 请手动从 https://github.com/mavlink/qgroundcontrol/releases 下载并放到 $INSTALL_DIR/"
    exit 1
fi

chmod +x "$APPIMG"

# ---- 5) 创建桌面快捷方式 -----------------------------------------------------
DESKTOP="$HOME/.local/share/applications/qgroundcontrol.desktop"
mkdir -p "$(dirname "$DESKTOP")"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=QGroundControl
Exec=$INSTALL_DIR/$APPIMG
Icon=qgroundcontrol
Terminal=false
Categories=Development;
EOF
echo "[install_qgc] (5/5) 桌面入口已写到 $DESKTOP"

cat <<EOF

============================================================
QGC 安装完成

启动方式:
  $INSTALL_DIR/$APPIMG
或在应用菜单搜索 "QGroundControl"

注意:
  * 你刚被加进 dialout 组, 需要 注销并重新登录 Ubuntu 一次,
    新组才会生效 (虚拟机里 reboot 也行).
  * 启动 PX4 SITL 后, QGC 会自动通过 UDP:14550 连接.
    PX4 启动日志里看到 "Ready for takeoff" 即可在 QGC 里
    点 "Takeoff" 起飞.

接下来 (建议):
  1. 重新登录使 dialout 生效
  2. bash scripts/launch_all.sh    # 启 PX4 + ROS2 感知
  3. 启动 QGC, 自动连接, 在地图上点航点 / 起飞
============================================================
EOF
