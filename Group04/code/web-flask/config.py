"""Flask 全局配置文件"""

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 数据库
DATABASE_PATH = os.path.join(BASE_DIR, "database", "fitness.db")
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

# JWT
SECRET_KEY = os.environ.get("SECRET_KEY", "group04-fitness-rehab-2026-secret-key")
JWT_EXPIRATION_HOURS = 24
JWT_ALGORITHM = "HS256"

# YOLO
YOLO_MODEL_PATH = os.path.join(BASE_DIR, "..", "..", "rehab_coach", "yolo11n-pose.pt")
YOLO_CONFIDENCE = 0.5

# 阿里云百炼 Qwen-VL-Plus
QWEN_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "your-api-key-here")
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen-vl-plus"

# 文件上传
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# 分页
DEFAULT_PAGE_SIZE = 20
