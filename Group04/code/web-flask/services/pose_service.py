"""YOLO 姿态检测服务 — 7 种健身动作的关键点提取与角度计算"""

import numpy as np
import torch

# COCO 17 keypoint 索引
(NOSE, L_EYE, R_EYE, L_EAR, R_EAR,
 L_SHOULDER, R_SHOULDER,
 L_ELBOW, R_ELBOW,
 L_WRIST, R_WRIST,
 L_HIP, R_HIP,
 L_KNEE, R_KNEE,
 L_ANKLE, R_ANKLE) = range(17)

# ── 动作定义 (每种动作检测的关键角度) ──
EXERCISE_CONFIG = {
    "squat": {
        "name": "深蹲", "name_en": "Squat",
        "angles": ["knee", "hip"],
        "up_threshold": 160, "down_threshold": 100,
        "primary_joints": [(R_HIP, R_KNEE, R_ANKLE), (L_HIP, L_KNEE, L_ANKLE)],
        "description": "双脚与肩同宽，保持背部挺直，下蹲至大腿与地面平行"
    },
    "pushup": {
        "name": "俯卧撑", "name_en": "Push-up",
        "angles": ["elbow", "shoulder"],
        "up_threshold": 160, "down_threshold": 90,
        "primary_joints": [(R_SHOULDER, R_ELBOW, R_WRIST), (L_SHOULDER, L_ELBOW, L_WRIST)],
        "description": "双手略宽于肩，身体保持直线，下降至胸部接近地面"
    },
    "pullup": {
        "name": "引体向上", "name_en": "Pull-up",
        "angles": ["elbow"],
        "up_threshold": 140, "down_threshold": 80,
        "primary_joints": [(R_SHOULDER, R_ELBOW, R_WRIST), (L_SHOULDER, L_ELBOW, L_WRIST)],
        "description": "正握横杆，上拉至下巴过杠，缓慢下放"
    },
    "situp": {
        "name": "仰卧起坐", "name_en": "Sit-up",
        "angles": ["hip", "torso"],
        "up_threshold": 80, "down_threshold": 160,
        "primary_joints": [(R_HIP, R_SHOULDER, R_KNEE)],
        "description": "屈膝仰卧，收腹使上背部离开地面"
    },
    "bicep_curl": {
        "name": "哑铃弯举", "name_en": "Bicep Curl",
        "angles": ["elbow"],
        "up_threshold": 45, "down_threshold": 170,
        "primary_joints": [(R_SHOULDER, R_ELBOW, R_WRIST), (L_SHOULDER, L_ELBOW, L_WRIST)],
        "description": "上臂固定，屈肘举起哑铃，缓慢下放"
    },
    "shoulder_press": {
        "name": "肩部推举", "name_en": "Shoulder Press",
        "angles": ["elbow", "shoulder"],
        "up_threshold": 170, "down_threshold": 70,
        "primary_joints": [(R_ELBOW, R_SHOULDER, R_HIP), (L_ELBOW, L_SHOULDER, L_HIP)],
        "description": "坐姿或站姿，将哑铃从肩部向上推举至手臂伸直"
    },
    "dumbbell_fly": {
        "name": "哑铃飞鸟", "name_en": "Dumbbell Fly",
        "angles": ["elbow", "shoulder"],
        "up_threshold": 50, "down_threshold": 150,
        "primary_joints": [(R_WRIST, R_SHOULDER, NOSE), (L_WRIST, L_SHOULDER, NOSE)],
        "description": "仰卧于凳上，双臂微弯展开至水平，再夹胸收回"
    },
}


def calculate_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """三点夹角 ∠abc，b 为顶点"""
    ba = a - b
    bc = c - b
    dot = np.dot(ba, bc)
    norm = np.linalg.norm(ba) * np.linalg.norm(bc)
    if norm < 1e-9:
        return None
    return float(np.degrees(np.arccos(np.clip(dot / norm, -1.0, 1.0))))


class PoseDetector:
    """YOLO 姿态检测器（单例）"""

    _instance = None

    def __new__(cls, model_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
            cls._instance._model_path = None
        return cls._instance

    def load_model(self, model_path: str):
        if self._model is not None and self._model_path == model_path:
            return
        from ultralytics import YOLO
        self._model = YOLO(model_path)
        self._model_path = model_path
        device = 0 if torch.cuda.is_available() else "cpu"
        if device == 0:
            self._model.to("cuda")

    def detect(self, image: np.ndarray, conf: float = 0.5):
        """对图像进行姿态估计，返回 (keypoints_xy, keypoints_conf) 或 (None, None)"""
        if self._model is None:
            raise RuntimeError("YOLO model not loaded — call load_model() first")
        results = self._model(image, conf=conf, verbose=False)
        kp = results[0].keypoints
        if kp is None or len(kp) == 0 or kp.data.shape[0] == 0:
            return None, None
        d = kp.data[0].cpu().numpy()
        return d[:, :2], d[:, 2]


class ActionCounter:
    """通用健身动作计数器"""

    def __init__(self, exercise_type: str):
        cfg = EXERCISE_CONFIG.get(exercise_type)
        if cfg is None:
            raise ValueError(f"未知动作类型: {exercise_type}")
        self.cfg = cfg
        self.exercise_type = exercise_type
        self.state = 0  # 0=starting, 1=moving, 2=peak, 3=returning
        self.count = 0
        self.correct_count = 0
        self.debounce_counter = 0
        self.current_angle = None
        self.current_phase = "standby"
        self.phase_names = {0: "准备", 1: "运动", 2: "顶峰", 3: "回收"}

    def get_primary_angle(self, keypoints_xy, keypoints_conf) -> float:
        """计算主要关节角度"""
        if keypoints_xy is None or keypoints_conf is None:
            return None
        for joints in self.cfg["primary_joints"]:
            i, j, k = joints
            if (keypoints_conf[i] >= 0.4 and
                keypoints_conf[j] >= 0.4 and
                keypoints_conf[k] >= 0.4):
                return calculate_angle(keypoints_xy[i], keypoints_xy[j], keypoints_xy[k])
        return None

    def update(self, keypoints_xy, keypoints_conf) -> dict:
        """返回 {action_completed, rep_count, angle, state, phase}"""
        angle = self.get_primary_angle(keypoints_xy, keypoints_conf)
        self.current_angle = angle

        if angle is None:
            return {"action_completed": False, "rep_count": self.count,
                    "angle": None, "state": self.state, "phase": self.current_phase}

        up_th = self.cfg["up_threshold"]
        down_th = self.cfg["down_threshold"]
        completed = False

        # 深蹲类：角度小 = 蹲下, 角度大 = 站直
        # 哑铃弯举类：角度小 = 弯举到头, 角度大 = 伸展
        if self.state == 0:
            if angle < down_th:
                self._confirm(1)
        elif self.state == 1:
            if angle < down_th * 0.8:
                self._confirm(2)
            elif angle > up_th:
                self.state = 0
        elif self.state == 2:
            if angle > down_th * 0.9:
                self._confirm(3)
        elif self.state == 3:
            if angle > up_th:
                self._confirm(0)
                self.count += 1
                completed = True
            elif angle < down_th:
                self.state = 1

        self.current_phase = self.phase_names.get(self.state, "?")
        return {
            "action_completed": completed,
            "rep_count": self.count,
            "angle": round(angle, 1),
            "state": self.state,
            "phase": self.current_phase,
        }

    def _confirm(self, new_state: int, debounce: int = 2):
        self.debounce_counter += 1
        if self.debounce_counter >= debounce:
            self.state = new_state
            self.debounce_counter = 0

    def reset(self):
        self.state = 0
        self.count = 0
        self.correct_count = 0
        self.debounce_counter = 0
        self.current_angle = None
        self.current_phase = "standby"

    def get_status(self) -> dict:
        return {
            "exercise": self.cfg["name"],
            "exercise_type": self.exercise_type,
            "rep_count": self.count,
            "angle": self.current_angle,
            "state": self.state,
            "phase": self.current_phase,
            "description": self.cfg["description"],
        }
