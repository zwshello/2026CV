"""API 路由 — 健身分析（图片/视频/摄像头）"""

import os
import uuid
import time
import json
import cv2
import numpy as np
from datetime import datetime
from flask import Blueprint, request, jsonify, g, current_app
from models import db, ImageRecord, VideoRecord, ActionAnalysis, CameraSessionRecord, CameraSnapshot
from auth import login_required
from services.pose_service import PoseDetector, ActionCounter, EXERCISE_CONFIG
from services.ai_service import analyze_fitness_image
from services.video_service import analyze_video, analyze_image_frame, get_available_exercises
from services.camera_state import session_counters

fitness_bp = Blueprint("fitness", __name__)


def _save_upload(file, subfolder: str) -> str:
    """保存上传文件，返回存储路径"""
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file.save(path)
    return path


def _yolo_path():
    from config import YOLO_MODEL_PATH
    # 尝试多个可能路径
    candidates = [
        YOLO_MODEL_PATH,
        os.path.join(current_app.root_path, "..", "..", "rehab_coach", "yolo11n-pose.pt"),
        os.path.join(current_app.root_path, "yolo11n-pose.pt"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return YOLO_MODEL_PATH


# ── 获取支持的动作列表 ──
@fitness_bp.route("/api/exercises", methods=["GET"])
def list_exercises():
    return jsonify({"code": 200, "data": get_available_exercises()})


# ── 图片分析 ──
@fitness_bp.route("/api/fitness/image", methods=["POST"])
@login_required
def analyze_image():
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "请上传图片"}), 400
    file = request.files["file"]
    exercise_type = request.form.get("exercise_type", "squat")

    image_path = _save_upload(file, "images")

    # YOLO 姿态检测
    pose_result = analyze_image_frame(image_path, exercise_type, _yolo_path())

    # Qwen-VL AI 分析
    ai_result = analyze_fitness_image(image_path, exercise_type, pose_result)

    # 保存记录
    record = ImageRecord(
        user_id=g.user_id,
        image_path=image_path,
        exercise_type=exercise_type,
        pose_keypoints=json.dumps(pose_result.get("keypoints")) if pose_result.get("keypoints") else None,
        ai_analysis=ai_result.get("analysis_text"),
        score=ai_result.get("score", 75),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({"code": 200, "data": {
        "record_id": record.id,
        "pose": pose_result,
        "ai": ai_result,
    }})


# ── 视频分析 ──
@fitness_bp.route("/api/fitness/video", methods=["POST"])
@login_required
def analyze_video_endpoint():
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "请上传视频"}), 400
    file = request.files["file"]
    exercise_type = request.form.get("exercise_type", "squat")

    video_path = _save_upload(file, "videos")

    result = analyze_video(video_path, exercise_type, _yolo_path(), sample_interval=3)
    if "error" in result:
        return jsonify({"code": 400, "message": result["error"]}), 400

    # 保存记录
    record = VideoRecord(
        user_id=g.user_id,
        video_path=video_path,
        exercise_type=exercise_type,
        total_reps=result["total_reps"],
        correct_reps=result.get("correct_reps", result["total_reps"]),
        duration_seconds=result.get("duration_seconds"),
        avg_score=result.get("avg_score"),
    )
    db.session.add(record)
    db.session.flush()

    # 保存逐帧分析
    for fd in result.get("frames_detail", [])[:200]:
        aa = ActionAnalysis(
            video_record_id=record.id,
            frame_index=fd["frame"],
            rep_number=fd.get("rep_number"),
            action_phase=fd.get("phase"),
            is_correct=fd.get("is_correct", True),
            score=fd.get("score"),
        )
        db.session.add(aa)

    db.session.commit()

    return jsonify({"code": 200, "data": {
        "record_id": record.id,
        "total_reps": result["total_reps"],
        "correct_reps": result.get("correct_reps", result["total_reps"]),
        "duration_seconds": result.get("duration_seconds"),
        "avg_score": result.get("avg_score"),
        "frames_detail": result.get("frames_detail", []),
    }})


# ── 摄像头会话 — 创建 ──
@fitness_bp.route("/api/camera/start", methods=["POST"])
@login_required
def camera_start():
    data = request.json or {}
    exercise_type = data.get("exercise_type", "squat")

    session = CameraSessionRecord(
        user_id=g.user_id,
        exercise_type=exercise_type,
        session_start=datetime.utcnow(),
        status="active",
    )
    db.session.add(session)
    db.session.commit()

    session_counters[session.id] = ActionCounter(exercise_type)

    return jsonify({"code": 200, "data": {
        "session_id": session.id,
        "exercise_type": exercise_type,
        "exercise_name": EXERCISE_CONFIG.get(exercise_type, {}).get("name", exercise_type),
        "status": "active",
    }})


# ── 摄像头 — 上传帧并分析 ──
@fitness_bp.route("/api/camera/frame", methods=["POST"])
@login_required
def camera_frame():
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "请上传帧"}), 400

    session_id = request.form.get("session_id", type=int)
    if not session_id or session_id not in session_counters:
        return jsonify({"code": 400, "message": "无效的会话 ID"}), 400

    file = request.files["file"]
    image_path = _save_upload(file, "camera")

    counter: ActionCounter = session_counters[session_id]

    detector = PoseDetector()
    detector.load_model(_yolo_path())

    image = cv2.imread(image_path)
    kp_xy, kp_conf = detector.detect(image)
    result = counter.update(kp_xy, kp_conf) if kp_xy is not None else {
        "action_completed": False, "rep_count": counter.count,
        "angle": None, "phase": "no_person",
    }

    return jsonify({"code": 200, "data": {
        "session_id": session_id,
        "rep_count": counter.count,
        "angle": result.get("angle"),
        "phase": result.get("phase", "no_person"),
        "action_completed": result.get("action_completed", False),
    }})


# ── 摄像头 — 截图 + AI 分析 ──
@fitness_bp.route("/api/camera/snapshot", methods=["POST"])
@login_required
def camera_snapshot():
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "请上传截图"}), 400

    session_id = request.form.get("session_id", type=int)
    session = db.session.get(CameraSessionRecord, session_id)
    if not session or session.user_id != g.user_id:
        return jsonify({"code": 404, "message": "会话不存在"}), 404

    file = request.files["file"]
    image_path = _save_upload(file, "camera")

    exercise_type = session.exercise_type or "squat"
    pose_result = analyze_image_frame(image_path, exercise_type, _yolo_path())
    ai_result = analyze_fitness_image(image_path, exercise_type, pose_result)

    counter = session_counters.get(session_id)

    snapshot = CameraSnapshot(
        session_id=session_id,
        image_path=image_path,
        exercise_type=exercise_type,
        rep_number=counter.count if counter else None,
        pose_keypoints=json.dumps(pose_result.get("keypoints")) if pose_result.get("keypoints") else None,
        ai_analysis=ai_result.get("analysis_text"),
        score=ai_result.get("score"),
    )
    db.session.add(snapshot)
    db.session.commit()

    return jsonify({"code": 200, "data": {
        "snapshot_id": snapshot.id,
        "pose": pose_result,
        "ai": ai_result,
    }})


# ── 摄像头 — 结束会话 ──
@fitness_bp.route("/api/camera/stop", methods=["POST"])
@login_required
def camera_stop():
    data = request.json or {}
    session_id = data.get("session_id")

    session = db.session.get(CameraSessionRecord, session_id)
    if not session or session.user_id != g.user_id:
        return jsonify({"code": 404, "message": "会话不存在"}), 404

    counter = session_counters.pop(session_id, None)
    session.session_end = datetime.utcnow()
    session.status = "completed"
    if session.session_start:
        session.duration_seconds = (session.session_end - session.session_start).total_seconds()
    if counter:
        session.total_reps = counter.count
    db.session.commit()

    return jsonify({"code": 200, "data": {
        "session_id": session.id,
        "total_reps": session.total_reps,
        "duration_seconds": session.duration_seconds,
        "status": "completed",
    }})


# ── 历史记录 ──
@fitness_bp.route("/api/records/images", methods=["GET"])
@login_required
def get_image_records():
    page = request.args.get("page", 1, type=int)
    records = (ImageRecord.query
               .filter_by(user_id=g.user_id)
               .order_by(ImageRecord.created_at.desc())
               .paginate(page=page, per_page=20, error_out=False))
    return jsonify({"code": 200, "data": {
        "items": [r.to_dict() for r in records.items],
        "total": records.total, "page": page,
        "pages": records.pages,
    }})


@fitness_bp.route("/api/records/videos", methods=["GET"])
@login_required
def get_video_records():
    page = request.args.get("page", 1, type=int)
    records = (VideoRecord.query
               .filter_by(user_id=g.user_id)
               .order_by(VideoRecord.created_at.desc())
               .paginate(page=page, per_page=20, error_out=False))
    return jsonify({"code": 200, "data": {
        "items": [r.to_dict() for r in records.items],
        "total": records.total, "page": page,
        "pages": records.pages,
    }})


@fitness_bp.route("/api/records/videos/<int:record_id>/details", methods=["GET"])
@login_required
def get_video_details(record_id):
    record = db.session.get(VideoRecord, record_id)
    if not record or record.user_id != g.user_id:
        return jsonify({"code": 404, "message": "记录不存在"}), 404
    analyses = (ActionAnalysis.query
                .filter_by(video_record_id=record_id)
                .order_by(ActionAnalysis.frame_index.asc())
                .all())
    return jsonify({"code": 200, "data": {
        "record": record.to_dict(),
        "analyses": [a.to_dict() for a in analyses],
    }})


@fitness_bp.route("/api/records/camera", methods=["GET"])
@login_required
def get_camera_records():
    page = request.args.get("page", 1, type=int)
    records = (CameraSessionRecord.query
               .filter_by(user_id=g.user_id)
               .order_by(CameraSessionRecord.session_start.desc())
               .paginate(page=page, per_page=20, error_out=False))
    return jsonify({"code": 200, "data": {
        "items": [r.to_dict() for r in records.items],
        "total": records.total, "page": page,
        "pages": records.pages,
    }})
