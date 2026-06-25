"""视频分析服务 — 逐帧处理视频，进行动作识别与计数"""

import os
import cv2
import json
import numpy as np
from services.pose_service import PoseDetector, ActionCounter, EXERCISE_CONFIG


def analyze_video(video_path: str, exercise_type: str, yolo_model_path: str,
                  sample_interval: int = 3) -> dict:
    """
    分析视频中的健身动作
    sample_interval: 每隔 N 帧采样一次
    返回 { total_reps, correct_reps, frames_detail, duration_seconds, avg_score }
    """
    if not os.path.exists(video_path):
        return {"error": f"视频文件不存在: {video_path}"}

    detector = PoseDetector()
    detector.load_model(yolo_model_path)

    counter = ActionCounter(exercise_type)
    frames_detail = []
    frame_idx = 0
    total_reps = 0

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if frame_idx % sample_interval != 0:
            continue

        kp_xy, kp_conf = detector.detect(frame)
        if kp_xy is None:
            frames_detail.append({
                "frame": frame_idx, "rep_number": None,
                "angle": None, "phase": "no_person",
                "is_correct": True, "score": None
            })
            continue

        result = counter.update(kp_xy, kp_conf)
        if result["action_completed"]:
            total_reps = result["rep_count"]

        frames_detail.append({
            "frame": frame_idx,
            "rep_number": result["rep_count"],
            "angle": result["angle"],
            "phase": result["phase"],
            "is_correct": True,
            "score": min(100, max(0, 100 - abs(result["angle"] - 120) * 0.5 if result["angle"] else 80))
        })

    cap.release()

    duration = total_frames / max(fps, 1)
    scores = [f["score"] for f in frames_detail if f["score"] is not None]
    avg_score = round(np.mean(scores), 1) if scores else 75.0

    return {
        "total_reps": total_reps,
        "correct_reps": total_reps,
        "duration_seconds": round(duration, 1),
        "avg_score": avg_score,
        "frames_detail": frames_detail,
        "exercise_type": exercise_type,
        "exercise_name": EXERCISE_CONFIG[exercise_type]["name"] if exercise_type in EXERCISE_CONFIG else exercise_type,
    }


def analyze_image_frame(image_path: str, exercise_type: str, yolo_model_path: str) -> dict:
    """分析单张图片中的健身动作"""
    if not os.path.exists(image_path):
        return {"error": f"图片不存在: {image_path}"}

    detector = PoseDetector()
    detector.load_model(yolo_model_path)

    image = cv2.imread(image_path)
    if image is None:
        return {"error": "无法读取图片"}

    kp_xy, kp_conf = detector.detect(image)

    if kp_xy is None:
        return {
            "exercise_type": exercise_type,
            "person_detected": False,
            "keypoints": None,
            "angle": None,
            "message": "未检测到人体",
        }

    counter = ActionCounter(exercise_type)
    result = counter.update(kp_xy, kp_conf)

    return {
        "exercise_type": exercise_type,
        "person_detected": True,
        "keypoints": kp_xy.tolist() if kp_xy is not None else None,
        "angle": result["angle"],
        "phase": result["phase"],
        "state": result["state"],
        "message": f"检测到 {EXERCISE_CONFIG[exercise_type]['name'] if exercise_type in EXERCISE_CONFIG else exercise_type} 动作",
    }


def get_available_exercises() -> list:
    """获取支持的健身动作列表"""
    return [
        {
            "key": key,
            "name": cfg["name"],
            "name_en": cfg["name_en"],
            "description": cfg["description"],
            "angles": cfg["angles"],
        }
        for key, cfg in EXERCISE_CONFIG.items()
    ]
