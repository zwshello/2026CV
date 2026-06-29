import cv2
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import scrolledtext
from PIL import Image, ImageTk
import threading
import numpy as np
from ultralytics import YOLO
from datetime import datetime
import os
from collections import deque
import time
import json
import warnings

warnings.filterwarnings('ignore')


# ==================== 配置类 ====================
class Config:
    def __init__(self):
        self.model_small = 'yolov8n.pt'
        self.model_medium = 'yolov8s.pt'
        self.conf_threshold = 0.5
        self.iou_threshold = 0.5
        self.imgsz = 640
        self.drone_conf_threshold = 0.35
        self.drone_iou_threshold = 0.4
        self.drone_imgsz = 1280
        self.frame_skip = 1
        self.smooth_window = 5
        self.track_max_age = 30
        self.min_person_size = 20
        self.alert_threshold = 50


# ==================== 热力图累计器 ====================
class HeatmapAccumulator:
    def __init__(self, decay=0.95):
        self.heatmap = None
        self.decay = decay

    def init(self, shape):
        """初始化热力图尺寸"""
        self.heatmap = np.zeros(shape[:2], dtype=np.float32)

    def update(self, boxes, frame_shape):
        """更新热力图"""
        if self.heatmap is None:
            self.init(frame_shape)

        # 确保热力图尺寸匹配
        if self.heatmap.shape[0] != frame_shape[0] or self.heatmap.shape[1] != frame_shape[1]:
            self.init(frame_shape)

        self.heatmap *= self.decay

        for box in boxes:
            x1, y1, x2, y2 = map(int, box[:4])
            center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
            if 0 <= center_x < frame_shape[1] and 0 <= center_y < frame_shape[0]:
                cv2.circle(self.heatmap, (center_x, center_y), 50, 1, -1)

        self.heatmap = cv2.GaussianBlur(self.heatmap, (0, 0), 30)

        if self.heatmap.max() > 0:
            heatmap_norm = np.uint8(255 * self.heatmap / self.heatmap.max())
        else:
            heatmap_norm = np.uint8(self.heatmap)

        # 确保输出是3通道
        heatmap_color = cv2.applyColorMap(heatmap_norm, cv2.COLORMAP_JET)
        return heatmap_color

    def reset(self):
        if self.heatmap is not None:
            self.heatmap.fill(0)


# ==================== 检测系统核心 ====================
class CrowdDetectionCore:
    def __init__(self, config):
        self.config = config

        # 模型
        self.model = None
        self.use_drone_mode = False

        # 检测参数
        self.conf_threshold = config.conf_threshold
        self.iou_threshold = config.iou_threshold
        self.imgsz = config.imgsz

        # 功能开关
        self.show_density = True
        self.show_trajectory = True
        self.show_accumulated = False

        # 统计数据
        self.frame_count = 0
        self.peak_count = 0
        self.current_count = 0
        self.current_fps = 0
        self.count_history = deque(maxlen=100)
        self.count_smooth = deque(maxlen=config.smooth_window)
        self.fps_history = deque(maxlen=30)
        self.prev_time = time.time()

        # 追踪
        self.tracks = {}
        self.next_track_id = 0
        self.track_max_age = config.track_max_age

        # 区域
        self.counting_zone = None
        self.counting_zones = []
        self.zone_names = []

        # 热力图
        self.heatmap_accumulator = HeatmapAccumulator()

        # 运行控制
        self.is_running = False
        self.cap = None

        # 当前帧缓存
        self.last_frame = None

    def load_model(self, use_drone_mode=False):
        """加载模型"""
        self.use_drone_mode = use_drone_mode
        if use_drone_mode:
            self.imgsz = self.config.drone_imgsz
            self.conf_threshold = self.config.drone_conf_threshold
            self.iou_threshold = self.config.drone_iou_threshold
            self.model = YOLO(self.config.model_medium)
            return "航拍模式已启动"
        else:
            self.imgsz = self.config.imgsz
            self.conf_threshold = self.config.conf_threshold
            self.iou_threshold = self.config.iou_threshold
            self.model = YOLO(self.config.model_small)
            return "普通模式已启动"

    def get_smooth_count(self, raw_count=None):
        """获取平滑计数"""
        if raw_count is not None:
            self.count_smooth.append(raw_count)
        if self.count_smooth:
            return int(np.mean(self.count_smooth))
        return 0

    def filter_small_targets(self, boxes):
        """过滤小目标"""
        valid_boxes = []
        for box in boxes:
            x1, y1, x2, y2 = map(int, box[:4])
            w = x2 - x1
            h = y2 - y1
            if w > self.config.min_person_size and h > self.config.min_person_size:
                valid_boxes.append(box)
        return valid_boxes

    def count_in_zone(self, boxes):
        """区域内计数"""
        if self.counting_zone is None and not self.counting_zones:
            return len(boxes)

        if self.counting_zones:
            counts = []
            for zone in self.counting_zones:
                count = 0
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box[:4])
                    bottom_center = ((x1 + x2) // 2, y2)
                    if cv2.pointPolygonTest(zone, bottom_center, False) >= 0:
                        count += 1
                counts.append(count)
            return counts
        else:
            count = 0
            for box in boxes:
                x1, y1, x2, y2 = map(int, box[:4])
                bottom_center = ((x1 + x2) // 2, y2)
                if cv2.pointPolygonTest(self.counting_zone, bottom_center, False) >= 0:
                    count += 1
            return count

    def process_frame(self, frame):
        """处理单帧"""
        if self.model is None:
            return frame, 0, 0

        self.frame_count += 1

        # 推理
        results = self.model(
            frame,
            imgsz=self.imgsz,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=[0],
            verbose=False
        )

        if results[0].boxes is not None:
            boxes = results[0].boxes.data.cpu().numpy()
            boxes = self.filter_small_targets(boxes)
            raw_count = len(boxes)
        else:
            boxes = []
            raw_count = 0

        self.current_count = self.get_smooth_count(raw_count)
        self.count_history.append(self.current_count)
        self.peak_count = max(self.peak_count, self.current_count)

        # 区域内计数
        zone_counts = self.count_in_zone(boxes)

        # 绘制检测框
        annotated_frame = results[0].plot()

        # 确保尺寸一致（重要：修复尺寸不匹配问题）
        if annotated_frame.shape[:2] != frame.shape[:2]:
            annotated_frame = cv2.resize(annotated_frame, (frame.shape[1], frame.shape[0]))

        # 绘制区域
        if self.counting_zone is not None:
            cv2.polylines(annotated_frame, [self.counting_zone], True, (255, 0, 0), 2)
        for i, zone in enumerate(self.counting_zones):
            color = [(255, 0, 0), (0, 255, 255), (255, 0, 255)][i % 3]
            cv2.polylines(annotated_frame, [zone], True, color, 2)
            center = np.mean(zone, axis=0).astype(int)
            name = self.zone_names[i] if i < len(self.zone_names) else f"Z{i + 1}"
            cv2.putText(annotated_frame, name, (center[0] - 20, center[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # 热力图（修复尺寸问题）
        if self.show_density and len(boxes) > 0:
            try:
                if self.show_accumulated:
                    heatmap = self.heatmap_accumulator.update(boxes, annotated_frame.shape)
                else:
                    # 临时热力图
                    heatmap = np.zeros((annotated_frame.shape[0], annotated_frame.shape[1]), dtype=np.float32)
                    for box in boxes:
                        x1, y1, x2, y2 = map(int, box[:4])
                        center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
                        if 0 <= center_x < annotated_frame.shape[1] and 0 <= center_y < annotated_frame.shape[0]:
                            cv2.circle(heatmap, (center_x, center_y), 50, 1, -1)
                    heatmap = cv2.GaussianBlur(heatmap, (0, 0), 30)
                    if heatmap.max() > 0:
                        heatmap = np.uint8(255 * heatmap / heatmap.max())
                    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

                # 确保热力图尺寸匹配
                if heatmap.shape[:2] != annotated_frame.shape[:2]:
                    heatmap = cv2.resize(heatmap, (annotated_frame.shape[1], annotated_frame.shape[0]))

                alpha = 0.4
                annotated_frame = cv2.addWeighted(annotated_frame, 1 - alpha, heatmap, alpha, 0)
            except Exception as e:
                print(f"热力图绘制错误: {e}")

        # 计算FPS
        current_time = time.time()
        fps = 1 / (current_time - self.prev_time + 1e-6)
        self.prev_time = current_time
        self.fps_history.append(fps)
        self.current_fps = np.mean(self.fps_history) if self.fps_history else fps

        # 在画面上绘制信息
        info_y = 30
        cv2.putText(annotated_frame, f"Count: {self.current_count}", (10, info_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"Peak: {self.peak_count}", (10, info_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
        cv2.putText(annotated_frame, f"FPS: {self.current_fps:.1f}", (10, info_y + 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # 显示区域计数
        if isinstance(zone_counts, list):
            for i, zc in enumerate(zone_counts):
                name = self.zone_names[i] if i < len(self.zone_names) else f"Zone{i + 1}"
                cv2.putText(annotated_frame, f"{name}: {zc}", (10, info_y + 90 + i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 1)
        elif zone_counts != len(boxes) and self.counting_zone is not None:
            cv2.putText(annotated_frame, f"In Zone: {zone_counts}", (10, info_y + 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 1)

        # 告警
        if self.current_count > self.config.alert_threshold:
            cv2.putText(annotated_frame, "ALERT: HIGH DENSITY!",
                        (annotated_frame.shape[1] // 2 - 150, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        self.last_frame = annotated_frame
        return annotated_frame, self.current_count, self.current_fps

    def start_camera(self):
        """启动摄像头"""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            return False
        self.is_running = True
        self.reset_stats()
        return True

    def start_video(self, path):
        """启动视频"""
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            return False
        self.is_running = True
        self.reset_stats()
        return True

    def start_image(self, path):
        """处理图片"""
        frame = cv2.imread(path)
        if frame is None:
            return False, None
        result, count, fps = self.process_frame(frame)
        self.is_running = False
        return True, result

    def get_frame(self):
        """获取一帧"""
        if self.cap is None or not self.is_running:
            return None, None

        ret, frame = self.cap.read()
        if not ret:
            return None, None

        result, count, fps = self.process_frame(frame)
        return result, count

    def stop(self):
        """停止"""
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None

    def reset_stats(self):
        """重置统计"""
        self.peak_count = 0
        self.current_count = 0
        self.count_history.clear()
        self.count_smooth.clear()
        self.frame_count = 0
        self.fps_history.clear()
        self.heatmap_accumulator.reset()
        self.tracks.clear()
        self.next_track_id = 0


# ==================== UI主窗口 ====================
class CrowdDetectionUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("人群检测系统 - 智能人流分析")
        self.root.geometry("1400x800")
        self.root.configure(bg='#2c3e50')

        # 配置
        self.config = Config()

        # 检测核心
        self.core = CrowdDetectionCore(self.config)

        # UI变量
        self.is_playing = False
        self.video_thread = None

        # 创建界面
        self.create_widgets()

        # 设置协议
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """创建界面组件"""
        # 主框架
        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：视频显示区域
        left_frame = tk.Frame(main_frame, bg='#34495e', relief=tk.RAISED, bd=2)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 视频标签
        self.video_label = tk.Label(left_frame, bg='#1a252f', text="等待启动...",
                                    font=("微软雅黑", 16), fg='white')
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 右侧：控制面板
        right_frame = tk.Frame(main_frame, bg='#34495e', width=350, relief=tk.RAISED, bd=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_frame.pack_propagate(False)

        # 标题
        title_label = tk.Label(right_frame, text="人群检测控制系统",
                               font=("微软雅黑", 18, "bold"),
                               bg='#34495e', fg='white')
        title_label.pack(pady=15)

        # ===== 输入源区域 =====
        source_frame = tk.LabelFrame(right_frame, text="输入源",
                                     font=("微软雅黑", 12, "bold"),
                                     bg='#34495e', fg='white', padx=10, pady=5)
        source_frame.pack(fill=tk.X, padx=10, pady=5)

        # 模式选择
        mode_frame = tk.Frame(source_frame, bg='#34495e')
        mode_frame.pack(fill=tk.X, pady=5)
        tk.Label(mode_frame, text="检测模式:", bg='#34495e', fg='white',
                 font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value="normal")
        normal_rb = tk.Radiobutton(mode_frame, text="普通模式", variable=self.mode_var,
                                   value="normal", bg='#34495e', fg='white', selectcolor='#34495e')
        normal_rb.pack(side=tk.LEFT, padx=10)
        drone_rb = tk.Radiobutton(mode_frame, text="航拍模式", variable=self.mode_var,
                                  value="drone", bg='#34495e', fg='white', selectcolor='#34495e')
        drone_rb.pack(side=tk.LEFT)

        # 按钮行
        btn_frame = tk.Frame(source_frame, bg='#34495e')
        btn_frame.pack(fill=tk.X, pady=5)

        self.cam_btn = tk.Button(btn_frame, text="📷 摄像头", command=self.start_camera,
                                 bg='#27ae60', fg='white', font=("微软雅黑", 10),
                                 width=10, height=1)
        self.cam_btn.pack(side=tk.LEFT, padx=2)

        self.img_btn = tk.Button(btn_frame, text="🖼️ 图片", command=self.select_image,
                                 bg='#3498db', fg='white', font=("微软雅黑", 10),
                                 width=10, height=1)
        self.img_btn.pack(side=tk.LEFT, padx=2)

        self.video_btn = tk.Button(btn_frame, text="🎬 视频", command=self.select_video,
                                   bg='#3498db', fg='white', font=("微软雅黑", 10),
                                   width=10, height=1)
        self.video_btn.pack(side=tk.LEFT, padx=2)

        # ===== 检测控制区域 =====
        detect_frame = tk.LabelFrame(right_frame, text="检测控制",
                                     font=("微软雅黑", 12, "bold"),
                                     bg='#34495e', fg='white', padx=10, pady=5)
        detect_frame.pack(fill=tk.X, padx=10, pady=5)

        # 置信度滑块
        conf_frame = tk.Frame(detect_frame, bg='#34495e')
        conf_frame.pack(fill=tk.X, pady=5)
        tk.Label(conf_frame, text="置信度阈值:", bg='#34495e', fg='white',
                 font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.conf_slider = tk.Scale(conf_frame, from_=0.1, to=0.95, resolution=0.05,
                                    orient=tk.HORIZONTAL, bg='#34495e', fg='white',
                                    length=150, command=self.on_conf_change)
        self.conf_slider.set(0.5)
        self.conf_slider.pack(side=tk.RIGHT)

        # 功能开关
        self.density_var = tk.BooleanVar(value=True)
        self.accumulated_var = tk.BooleanVar(value=False)

        tk.Checkbutton(detect_frame, text="密度热力图", variable=self.density_var,
                       command=self.toggle_density, bg='#34495e', fg='white',
                       selectcolor='#34495e').pack(anchor=tk.W, pady=2)
        tk.Checkbutton(detect_frame, text="累计热力图", variable=self.accumulated_var,
                       command=self.toggle_accumulated, bg='#34495e', fg='white',
                       selectcolor='#34495e').pack(anchor=tk.W, pady=2)

        # ===== 区域定义区域 =====
        zone_frame = tk.LabelFrame(right_frame, text="检测区域",
                                   font=("微软雅黑", 12, "bold"),
                                   bg='#34495e', fg='white', padx=10, pady=5)
        zone_frame.pack(fill=tk.X, padx=10, pady=5)

        self.zone_btn = tk.Button(zone_frame, text="✏️ 定义单区域", command=self.define_single_zone,
                                  bg='#e67e22', fg='white', font=("微软雅黑", 10))
        self.zone_btn.pack(fill=tk.X, pady=2)

        self.clear_zone_btn = tk.Button(zone_frame, text="🗑️ 清除区域", command=self.clear_zones,
                                        bg='#e74c3c', fg='white', font=("微软雅黑", 10))
        self.clear_zone_btn.pack(fill=tk.X, pady=2)

        # ===== 统计信息区域 =====
        stats_frame = tk.LabelFrame(right_frame, text="实时统计",
                                    font=("微软雅黑", 12, "bold"),
                                    bg='#34495e', fg='white', padx=10, pady=5)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        self.count_label = tk.Label(stats_frame, text="当前人数: 0",
                                    font=("微软雅黑", 14, "bold"),
                                    bg='#34495e', fg='#2ecc71')
        self.count_label.pack(anchor=tk.W, pady=2)

        self.peak_label = tk.Label(stats_frame, text="峰值人数: 0",
                                   font=("微软雅黑", 12),
                                   bg='#34495e', fg='#f1c40f')
        self.peak_label.pack(anchor=tk.W, pady=2)

        self.fps_label = tk.Label(stats_frame, text="FPS: 0",
                                  font=("微软雅黑", 12),
                                  bg='#34495e', fg='#3498db')
        self.fps_label.pack(anchor=tk.W, pady=2)

        # ===== 操作按钮区域 =====
        action_frame = tk.Frame(right_frame, bg='#34495e')
        action_frame.pack(fill=tk.X, padx=10, pady=10)

        self.stop_btn = tk.Button(action_frame, text="⏹️ 停止", command=self.stop_detection,
                                  bg='#e74c3c', fg='white', font=("微软雅黑", 12),
                                  width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.screenshot_btn = tk.Button(action_frame, text="📸 截图", command=self.take_screenshot,
                                        bg='#1abc9c', fg='white', font=("微软雅黑", 12),
                                        width=15, state=tk.DISABLED)
        self.screenshot_btn.pack(side=tk.RIGHT, padx=5)

        # 导出按钮
        export_btn = tk.Button(right_frame, text="📊 导出统计报表", command=self.export_report,
                               bg='#9b59b6', fg='white', font=("微软雅黑", 12))
        export_btn.pack(fill=tk.X, padx=10, pady=5)

        # 重置按钮
        reset_btn = tk.Button(right_frame, text="🔄 重置统计", command=self.reset_stats,
                              bg='#95a5a6', fg='white', font=("微软雅黑", 12))
        reset_btn.pack(fill=tk.X, padx=10, pady=5)

        # 状态栏
        self.status_bar = tk.Label(self.root, text="就绪",
                                   font=("微软雅黑", 9),
                                   bg='#1a252f', fg='white', anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def on_conf_change(self, val):
        """置信度变化"""
        self.core.conf_threshold = float(val)
        self.status_bar.config(text=f"置信度阈值: {val}")

    def toggle_density(self):
        """切换密度图"""
        self.core.show_density = self.density_var.get()

    def toggle_accumulated(self):
        """切换累计热力图"""
        self.core.show_accumulated = self.accumulated_var.get()

    def load_model(self):
        """加载模型"""
        use_drone = (self.mode_var.get() == "drone")
        msg = self.core.load_model(use_drone)
        self.status_bar.config(text=msg)

    def start_camera(self):
        """启动摄像头"""
        self.load_model()
        if self.core.start_camera():
            self.is_playing = True
            self.cam_btn.config(state=tk.DISABLED)
            self.img_btn.config(state=tk.DISABLED)
            self.video_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.screenshot_btn.config(state=tk.NORMAL)
            self.start_video_loop()
            self.status_bar.config(text="摄像头已启动")
        else:
            messagebox.showerror("错误", "无法打开摄像头")

    def select_image(self):
        """选择图片"""
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp")]
        )
        if path:
            self.load_model()
            success, result = self.core.start_image(path)
            if success:
                self.display_image(result)
                self.update_stats_display()
                self.status_bar.config(text=f"图片已加载: {os.path.basename(path)}")
            else:
                messagebox.showerror("错误", "无法读取图片")

    def select_video(self):
        """选择视频"""
        path = filedialog.askopenfilename(
            title="选择视频",
            filetypes=[("视频文件", "*.mp4 *.avi *.mov *.mkv")]
        )
        if path:
            self.load_model()
            if self.core.start_video(path):
                self.is_playing = True
                self.cam_btn.config(state=tk.DISABLED)
                self.img_btn.config(state=tk.DISABLED)
                self.video_btn.config(state=tk.DISABLED)
                self.stop_btn.config(state=tk.NORMAL)
                self.screenshot_btn.config(state=tk.NORMAL)
                self.start_video_loop()
                self.status_bar.config(text=f"视频已加载: {os.path.basename(path)}")
            else:
                messagebox.showerror("错误", "无法读取视频")

    def start_video_loop(self):
        """视频循环"""
        if self.is_playing and self.core.is_running:
            frame, count = self.core.get_frame()
            if frame is not None:
                self.display_image(frame)
                self.update_stats_display()
                self.root.after(30, self.start_video_loop)
            else:
                self.stop_detection()

    def display_image(self, cv_image):
        """显示图片"""
        if cv_image is None:
            return

        # 调整大小适应窗口
        h, w = cv_image.shape[:2]
        max_h, max_w = 540, 800
        if h > max_h or w > max_w:
            scale = min(max_h / h, max_w / w)
            new_w, new_h = int(w * scale), int(h * scale)
            cv_image = cv2.resize(cv_image, (new_w, new_h))

        # 转换颜色
        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(cv_image)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.config(image=imgtk, text="")
        self.video_label.image = imgtk

    def update_stats_display(self):
        """更新统计显示"""
        self.count_label.config(text=f"当前人数: {self.core.current_count}")
        self.peak_label.config(text=f"峰值人数: {self.core.peak_count}")
        self.fps_label.config(text=f"FPS: {self.core.current_fps:.1f}")

    def define_single_zone(self):
        """定义单区域"""
        if self.core.last_frame is None:
            messagebox.showinfo("提示", "请先启动摄像头或加载图片/视频")
            return

        messagebox.showinfo("区域定义",
                            "请在弹出窗口中用鼠标左键点击画区域（至少3个点）\n"
                            "完成后按Enter键，按ESC取消")

        # 在新窗口中进行区域定义
        frame_copy = self.core.last_frame.copy()
        points = []

        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                points.append((x, y))
                cv2.circle(frame_copy, (x, y), 5, (0, 255, 0), -1)
                if len(points) > 1:
                    cv2.line(frame_copy, points[-2], points[-1], (0, 255, 0), 2)
                cv2.imshow("Define Zone", frame_copy)

        cv2.namedWindow("Define Zone", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Define Zone", mouse_callback)
        cv2.imshow("Define Zone", frame_copy)

        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # Enter
                if len(points) >= 3:
                    self.core.counting_zone = np.array(points)
                    self.core.counting_zones = []
                    self.status_bar.config(text=f"已定义区域，顶点数: {len(points)}")
                break
            elif key == 27:  # ESC
                break

        cv2.destroyWindow("Define Zone")

    def clear_zones(self):
        """清除区域"""
        self.core.counting_zone = None
        self.core.counting_zones = []
        self.core.zone_names = []
        self.status_bar.config(text="已清除所有检测区域")

    def stop_detection(self):
        """停止检测"""
        self.is_playing = False
        self.core.stop()
        self.cam_btn.config(state=tk.NORMAL)
        self.img_btn.config(state=tk.NORMAL)
        self.video_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.screenshot_btn.config(state=tk.DISABLED)
        self.status_bar.config(text="检测已停止")

        # 清空显示
        self.video_label.config(image="", text="等待启动...")

    def take_screenshot(self):
        """截图"""
        if self.core.last_frame is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.jpg"
            cv2.imwrite(filename, self.core.last_frame)
            self.status_bar.config(text=f"截图已保存: {filename}")
            messagebox.showinfo("截图成功", f"已保存为: {filename}")

    def export_report(self):
        """导出报表"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.csv"

        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['时间', '当前人数', '峰值人数', '平均FPS', '处理帧数'])
                writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                 self.core.current_count,
                                 self.core.peak_count,
                                 f"{self.core.current_fps:.1f}",
                                 self.core.frame_count])
            self.status_bar.config(text=f"报表已导出: {filename}")
            messagebox.showinfo("导出成功", f"报表已保存为: {filename}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def reset_stats(self):
        """重置统计"""
        self.core.reset_stats()
        self.status_bar.config(text="统计已重置")
        self.update_stats_display()

    def on_closing(self):
        """关闭窗口"""
        self.is_playing = False
        self.core.stop()
        self.root.destroy()

    def run(self):
        """运行UI"""
        self.root.mainloop()


# ==================== 主程序 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("🎯 人群检测系统 - 图形界面版")
    print("=" * 60)
    print("\n首次运行需要下载YOLO模型，请稍等...")
    print("模型下载完成后会自动打开图形界面\n")

    # 预下载模型
    from ultralytics import YOLO

    try:
        YOLO('yolov8n.pt')
        print("✅ 模型加载成功")
    except Exception as e:
        print(f"⚠️ 模型下载中: {e}")

    # 启动UI
    app = CrowdDetectionUI()
    app.run()