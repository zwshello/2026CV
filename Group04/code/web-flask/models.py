"""数据库模型 — 共 11 张表"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ── 1. 用户表 ──
class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    nickname = db.Column(db.String(80), nullable=True)
    role = db.Column(db.String(20), default="user")  # user | admin
    avatar = db.Column(db.String(512), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(10), nullable=True)  # male | female
    height = db.Column(db.Float, nullable=True)  # cm
    weight = db.Column(db.Float, nullable=True)  # kg
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    fitness_plans = db.relationship("FitnessPlan", backref="user", lazy="dynamic")
    diet_plans = db.relationship("DietPlan", backref="user", lazy="dynamic")
    exercise_plans = db.relationship("ExercisePlan", backref="user", lazy="dynamic")
    weight_records = db.relationship("WeightRecord", backref="user", lazy="dynamic")
    food_analyses = db.relationship("FoodAnalysis", backref="user", lazy="dynamic")
    image_records = db.relationship("ImageRecord", backref="user", lazy="dynamic")
    video_records = db.relationship("VideoRecord", backref="user", lazy="dynamic")
    camera_sessions = db.relationship("CameraSessionRecord", backref="user", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "username": self.username, "nickname": self.nickname,
            "role": self.role, "avatar": self.avatar, "email": self.email,
            "phone": self.phone, "age": self.age, "gender": self.gender,
            "height": self.height, "weight": self.weight,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 2. 健身计划表 ──
class FitnessPlan(db.Model):
    __tablename__ = "fitness_plan"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    plan_name = db.Column(db.String(120), nullable=False)
    goal = db.Column(db.String(256), nullable=True)  # 健身目标
    target_weight = db.Column(db.Float, nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    weekly_frequency = db.Column(db.Integer, default=3)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="active")  # active | completed | paused
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exercise_plans = db.relationship("ExercisePlan", backref="fitness_plan", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "plan_name": self.plan_name,
            "goal": self.goal, "target_weight": self.target_weight,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "weekly_frequency": self.weekly_frequency, "notes": self.notes,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 3. 饮食计划表 ──
class DietPlan(db.Model):
    __tablename__ = "diet_plan"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    plan_name = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=True)  # 饮食计划内容 / 建议
    daily_calorie_target = db.Column(db.Integer, nullable=True)
    protein_target = db.Column(db.Float, nullable=True)  # g
    carbs_target = db.Column(db.Float, nullable=True)
    fat_target = db.Column(db.Float, nullable=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "plan_name": self.plan_name,
            "content": self.content, "daily_calorie_target": self.daily_calorie_target,
            "protein_target": self.protein_target,
            "carbs_target": self.carbs_target, "fat_target": self.fat_target,
            "date": self.date.isoformat() if self.date else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 4. 锻炼计划表 ──
class ExercisePlan(db.Model):
    __tablename__ = "exercise_plan"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    fitness_plan_id = db.Column(db.Integer, db.ForeignKey("fitness_plan.id"), nullable=True)
    exercise_name = db.Column(db.String(80), nullable=False)  # squat, pushup, etc.
    sets = db.Column(db.Integer, default=3)
    reps = db.Column(db.Integer, default=12)
    duration_minutes = db.Column(db.Integer, nullable=True)
    rest_seconds = db.Column(db.Integer, default=60)
    day_of_week = db.Column(db.Integer, nullable=True)  # 1=Mon .. 7=Sun
    content = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "fitness_plan_id": self.fitness_plan_id,
            "exercise_name": self.exercise_name, "sets": self.sets, "reps": self.reps,
            "duration_minutes": self.duration_minutes, "rest_seconds": self.rest_seconds,
            "day_of_week": self.day_of_week, "content": self.content, "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 5. 体重记录表 ──
class WeightRecord(db.Model):
    __tablename__ = "weight_record"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    weight = db.Column(db.Float, nullable=False)  # kg
    body_fat_pct = db.Column(db.Float, nullable=True)
    record_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "weight": self.weight,
            "body_fat_pct": self.body_fat_pct,
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 6. 食物分析表 ──
class FoodAnalysis(db.Model):
    __tablename__ = "food_analysis"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    image_path = db.Column(db.String(512), nullable=False)
    food_name = db.Column(db.String(200), nullable=True)
    calories = db.Column(db.Float, nullable=True)  # kcal
    protein = db.Column(db.Float, nullable=True)  # g
    carbs = db.Column(db.Float, nullable=True)  # g
    fat = db.Column(db.Float, nullable=True)  # g
    fiber = db.Column(db.Float, nullable=True)
    analysis_text = db.Column(db.Text, nullable=True)  # AI 分析原文
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "image_path": self.image_path,
            "food_name": self.food_name, "calories": self.calories,
            "protein": self.protein, "carbs": self.carbs, "fat": self.fat,
            "fiber": self.fiber, "analysis_text": self.analysis_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 7. 图片分析记录表 ──
class ImageRecord(db.Model):
    __tablename__ = "image_record"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    image_path = db.Column(db.String(512), nullable=False)
    exercise_type = db.Column(db.String(80), nullable=True)
    pose_keypoints = db.Column(db.Text, nullable=True)  # JSON of keypoints
    ai_analysis = db.Column(db.Text, nullable=True)  # Qwen-VL 分析结果
    score = db.Column(db.Float, nullable=True)  # 动作评分 0-100
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "image_path": self.image_path,
            "exercise_type": self.exercise_type, "pose_keypoints": self.pose_keypoints,
            "ai_analysis": self.ai_analysis, "score": self.score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 8. 视频分析记录表 ──
class VideoRecord(db.Model):
    __tablename__ = "video_record"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    video_path = db.Column(db.String(512), nullable=False)
    exercise_type = db.Column(db.String(80), nullable=True)
    total_reps = db.Column(db.Integer, default=0)
    correct_reps = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Float, nullable=True)
    avg_score = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    action_analyses = db.relationship("ActionAnalysis", backref="video_record", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "video_path": self.video_path,
            "exercise_type": self.exercise_type, "total_reps": self.total_reps,
            "correct_reps": self.correct_reps, "duration_seconds": self.duration_seconds,
            "avg_score": self.avg_score, "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 9. 动作分析表 ──
class ActionAnalysis(db.Model):
    __tablename__ = "action_analysis"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    video_record_id = db.Column(db.Integer, db.ForeignKey("video_record.id"), nullable=False)
    frame_index = db.Column(db.Integer, nullable=False)
    rep_number = db.Column(db.Integer, nullable=True)
    action_phase = db.Column(db.String(40), nullable=True)  # up / down / hold / transition
    knee_angle = db.Column(db.Float, nullable=True)
    hip_angle = db.Column(db.Float, nullable=True)
    shoulder_angle = db.Column(db.Float, nullable=True)
    elbow_angle = db.Column(db.Float, nullable=True)
    is_correct = db.Column(db.Boolean, default=True)
    error_type = db.Column(db.String(80), nullable=True)
    score = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "video_record_id": self.video_record_id,
            "frame_index": self.frame_index, "rep_number": self.rep_number,
            "action_phase": self.action_phase,
            "knee_angle": self.knee_angle, "hip_angle": self.hip_angle,
            "shoulder_angle": self.shoulder_angle, "elbow_angle": self.elbow_angle,
            "is_correct": self.is_correct, "error_type": self.error_type,
            "score": self.score, "notes": self.notes,
        }


# ── 10. 摄像头会话记录表 ──
class CameraSessionRecord(db.Model):
    __tablename__ = "camera_session_record"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exercise_type = db.Column(db.String(80), nullable=True)
    session_start = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    session_end = db.Column(db.DateTime, nullable=True)
    total_reps = db.Column(db.Integer, default=0)
    correct_reps = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Float, nullable=True)
    avg_score = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default="active")  # active | completed
    notes = db.Column(db.Text, nullable=True)

    snapshots = db.relationship("CameraSnapshot", backref="session", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "exercise_type": self.exercise_type,
            "session_start": self.session_start.isoformat() if self.session_start else None,
            "session_end": self.session_end.isoformat() if self.session_end else None,
            "total_reps": self.total_reps, "correct_reps": self.correct_reps,
            "duration_seconds": self.duration_seconds, "avg_score": self.avg_score,
            "status": self.status, "notes": self.notes,
        }


# ── 11. 摄像头快照表 ──
class CameraSnapshot(db.Model):
    __tablename__ = "camera_snapshot"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("camera_session_record.id"), nullable=False)
    image_path = db.Column(db.String(512), nullable=False)
    exercise_type = db.Column(db.String(80), nullable=True)
    rep_number = db.Column(db.Integer, nullable=True)
    pose_keypoints = db.Column(db.Text, nullable=True)
    ai_analysis = db.Column(db.Text, nullable=True)
    score = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "session_id": self.session_id,
            "image_path": self.image_path, "exercise_type": self.exercise_type,
            "rep_number": self.rep_number, "pose_keypoints": self.pose_keypoints,
            "ai_analysis": self.ai_analysis, "score": self.score,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
