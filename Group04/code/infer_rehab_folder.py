import argparse
import csv
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from ultralytics import YOLO

from train_stgat_uiprmd import (
    Graph,
    MultiStreamSTGCNClassifier,
    compute_bone_stream,
    compute_motion_stream,
    normalize_global_positions,
    resample_sequence,
)
from ul_red_parser_0 import EXERCISE_ANGLE_MAP, generate_all_templates, load_templates


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
VIDEO_ACTION_RE = re.compile(r"(?:^|[_-])(?:m|a)(?P<action>\d{2})(?:[_-]|\.|$)", re.IGNORECASE)
TEMPLATE_NAME_RE = re.compile(r"^(?P<exercise>[A-Za-z]+)R\d+S\d+$")

UI_PRMD_ACTION_NAMES = {idx: f"ui_action_{idx:02d}" for idx in range(1, 11)}


NOSE = 0
L_SHOULDER = 5
R_SHOULDER = 6
L_ELBOW = 7
R_ELBOW = 8
L_WRIST = 9
R_WRIST = 10
L_HIP = 11
R_HIP = 12
L_KNEE = 13
R_KNEE = 14
L_ANKLE = 15
R_ANKLE = 16


COCO_TO_TEMPLATE_ANGLES = {
    "right_elbow": (R_SHOULDER, R_ELBOW, R_WRIST),
    "left_elbow": (L_SHOULDER, L_ELBOW, L_WRIST),
    "right_shoulder": (R_ELBOW, R_SHOULDER, R_HIP),
    "left_shoulder": (L_ELBOW, L_SHOULDER, L_HIP),
    "right_knee": (R_HIP, R_KNEE, R_ANKLE),
    "left_knee": (L_HIP, L_KNEE, L_ANKLE),
    "right_hip": (R_SHOULDER, R_HIP, R_KNEE),
    "left_hip": (L_SHOULDER, L_HIP, L_KNEE),
}


@dataclass
class PoseSequence:
    coords: np.ndarray
    confs: np.ndarray
    fps: float
    frame_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch inference for rehabilitation videos. "
            "Supports DTW with UL-RED templates and ST-GCN with UI-PRMD checkpoints."
        )
    )
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("results"))
    parser.add_argument("--method", choices=["dtw", "stgcn", "both"], default="both")

    parser.add_argument("--yolo-model", type=str, default="yolo11n-pose.pt")
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--det-conf", type=float, default=0.35)
    parser.add_argument("--kp-conf", type=float, default=0.35)
    parser.add_argument("--sequence-length", type=int, default=96)

    parser.add_argument(
        "--stgcn-checkpoint",
        type=Path,
        default=Path("results/uiprmd_stgcn_kinect_multistream_loso_20260615_090311"),
        help="A single best_model.pth or a LOSO run directory that contains multiple fold checkpoints.",
    )
    parser.add_argument("--stgcn-threshold", type=float, default=0.5)
    parser.add_argument("--action-id", type=int, default=None, help="UI-PRMD action id in [1, 10].")

    parser.add_argument("--dtw-template-json", type=Path, default=Path("data/templates/ul_red_templates.json"))
    parser.add_argument("--ulred-root", type=Path, default=Path("data/ul-red"))
    parser.add_argument(
        "--exercise-name",
        type=str,
        default=None,
        help="UL-RED exercise name for DTW, for example ArmRaise or MiniSquat.",
    )
    parser.add_argument(
        "--dtw-threshold-scale",
        type=float,
        default=1.0,
        help="Multiply the template-derived DTW threshold by this value.",
    )
    parser.add_argument("--save-pose-npy", action="store_true")
    return parser.parse_args()


def find_video_files(video_dir: Path) -> list[Path]:
    if not video_dir.exists():
        raise FileNotFoundError(f"Video directory not found: {video_dir}")
    return sorted(path for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS)


def slugify_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def get_template_exercise_name(template_name: str) -> str:
    match = TEMPLATE_NAME_RE.match(template_name)
    if match:
        return match.group("exercise")
    return template_name


def safe_float(value: float | int | np.floating | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return float(value)


def select_primary_person(result) -> tuple[np.ndarray | None, np.ndarray | None]:
    keypoints = getattr(result, "keypoints", None)
    boxes = getattr(result, "boxes", None)
    if keypoints is None or len(keypoints) == 0:
        return None, None

    person_index = 0
    if boxes is not None and len(boxes) > 0:
        xyxy = boxes.xyxy.cpu().numpy()
        areas = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
        person_index = int(np.argmax(areas))

    xy = keypoints.xy[person_index].cpu().numpy().astype(np.float32)
    conf = keypoints.conf[person_index].cpu().numpy().astype(np.float32)
    return xy, conf


def fill_nan_series(series: np.ndarray, fill_value: float = 0.0) -> np.ndarray:
    arr = np.asarray(series, dtype=np.float32).copy()
    if arr.ndim != 1:
        raise ValueError("fill_nan_series expects a 1D array.")
    mask = np.isfinite(arr)
    if mask.all():
        return arr
    if not mask.any():
        arr[:] = fill_value
        return arr
    indices = np.arange(len(arr), dtype=np.float32)
    arr[~mask] = np.interp(indices[~mask], indices[mask], arr[mask])
    return arr


def fill_nan_pose_sequence(coords: np.ndarray) -> np.ndarray:
    filled = np.asarray(coords, dtype=np.float32).copy()
    for joint_idx in range(filled.shape[1]):
        for dim_idx in range(filled.shape[2]):
            filled[:, joint_idx, dim_idx] = fill_nan_series(filled[:, joint_idx, dim_idx], fill_value=0.0)
    return filled


def smooth_pose_sequence(coords: np.ndarray, window_size: int = 5) -> np.ndarray:
    if window_size <= 1 or len(coords) < window_size:
        return coords
    kernel = np.ones(window_size, dtype=np.float32) / float(window_size)
    smoothed = coords.copy()
    for joint_idx in range(coords.shape[1]):
        for dim_idx in range(coords.shape[2]):
            padded = np.pad(coords[:, joint_idx, dim_idx], (window_size // 2,), mode="edge")
            smoothed[:, joint_idx, dim_idx] = np.convolve(padded, kernel, mode="valid")
    return smoothed


def extract_pose_sequence(
    video_path: Path,
    model: YOLO,
    device: str,
    det_conf: float,
) -> PoseSequence:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps) or fps <= 0:
        fps = 30.0

    coords: list[np.ndarray] = []
    confs: list[np.ndarray] = []

    while True:
        ok, frame = capture.read()
        if not ok:
            break

        result = model(frame, conf=det_conf, verbose=False, device=device)[0]
        xy, conf = select_primary_person(result)
        if xy is None or conf is None:
            coords.append(np.full((17, 2), np.nan, dtype=np.float32))
            confs.append(np.zeros(17, dtype=np.float32))
        else:
            coords.append(xy.astype(np.float32))
            confs.append(conf.astype(np.float32))

    capture.release()

    if not coords:
        raise RuntimeError(f"No frames were decoded from: {video_path}")

    coord_array = np.stack(coords, axis=0)
    conf_array = np.stack(confs, axis=0)
    return PoseSequence(coords=coord_array, confs=conf_array, fps=float(fps), frame_count=len(coords))


def calculate_angle_2d(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    v1 = p1 - p2
    v2 = p3 - p2
    denom = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom < 1e-6:
        return float("nan")
    cosine = np.clip(np.dot(v1, v2) / denom, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def resample_1d(sequence: list[float] | np.ndarray, target_len: int = 100) -> np.ndarray:
    arr = np.asarray(sequence, dtype=np.float32)
    if arr.size == 0:
        return np.zeros(target_len, dtype=np.float32)
    if arr.size == 1:
        return np.full(target_len, arr[0], dtype=np.float32)
    source_x = np.linspace(0.0, 1.0, num=arr.size, dtype=np.float32)
    target_x = np.linspace(0.0, 1.0, num=target_len, dtype=np.float32)
    return np.interp(target_x, source_x, arr).astype(np.float32)


def build_angle_sequences(coords: np.ndarray, confs: np.ndarray, kp_conf: float) -> dict[str, np.ndarray]:
    angles: dict[str, list[float]] = defaultdict(list)
    for frame_idx in range(coords.shape[0]):
        for angle_name, (i1, i2, i3) in COCO_TO_TEMPLATE_ANGLES.items():
            if (
                confs[frame_idx, i1] < kp_conf
                or confs[frame_idx, i2] < kp_conf
                or confs[frame_idx, i3] < kp_conf
            ):
                angles[angle_name].append(float("nan"))
                continue
            value = calculate_angle_2d(coords[frame_idx, i1], coords[frame_idx, i2], coords[frame_idx, i3])
            angles[angle_name].append(value)

    normalized: dict[str, np.ndarray] = {}
    for angle_name, sequence in angles.items():
        filled = fill_nan_series(np.asarray(sequence, dtype=np.float32), fill_value=0.0)
        normalized[angle_name] = resample_1d(filled, target_len=100)
    return normalized


def dtw_distance_1d(seq_a: np.ndarray, seq_b: np.ndarray) -> float:
    a = np.asarray(seq_a, dtype=np.float32)
    b = np.asarray(seq_b, dtype=np.float32)
    cost = np.full((len(a) + 1, len(b) + 1), np.inf, dtype=np.float32)
    cost[0, 0] = 0.0

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            dist = abs(a[i - 1] - b[j - 1])
            cost[i, j] = dist + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])

    normalizer = max(len(a) + len(b), 1)
    return float(cost[len(a), len(b)] / normalizer)


def average_dtw_distance(seq_dict_a: dict[str, np.ndarray], seq_dict_b: dict[str, np.ndarray]) -> float:
    shared = sorted(set(seq_dict_a) & set(seq_dict_b))
    if not shared:
        return float("inf")
    distances = [dtw_distance_1d(seq_dict_a[name], seq_dict_b[name]) for name in shared]
    return float(np.mean(distances))


def resolve_template_json(template_json: Path, ulred_root: Path) -> Path:
    if template_json.exists():
        return template_json
    if not ulred_root.exists():
        raise FileNotFoundError(
            f"Template json not found at {template_json}, and UL-RED root does not exist: {ulred_root}"
        )
    template_json.parent.mkdir(parents=True, exist_ok=True)
    generate_all_templates(str(ulred_root), str(template_json.parent))
    if not template_json.exists():
        raise FileNotFoundError(f"Template generation finished but json still missing: {template_json}")
    return template_json


def build_dtw_profiles(template_json: Path, ulred_root: Path, threshold_scale: float) -> dict[str, dict]:
    resolved_json = resolve_template_json(template_json, ulred_root)
    templates = load_templates(str(resolved_json))
    grouped: dict[str, list] = defaultdict(list)
    for template in templates.values():
        grouped[get_template_exercise_name(template.name)].append(template)

    profiles: dict[str, dict] = {}
    for exercise_name, items in grouped.items():
        if exercise_name not in EXERCISE_ANGLE_MAP:
            continue
        if not EXERCISE_ANGLE_MAP[exercise_name]:
            continue

        items = [item for item in items if item.angle_sequences]
        if not items:
            continue

        distances_by_idx = []
        for idx, candidate in enumerate(items):
            candidate_distances = []
            for jdx, other in enumerate(items):
                if idx == jdx:
                    continue
                candidate_distances.append(average_dtw_distance(candidate.angle_sequences, other.angle_sequences))
            mean_distance = float(np.mean(candidate_distances)) if candidate_distances else 0.0
            distances_by_idx.append((mean_distance, idx))

        _, medoid_idx = min(distances_by_idx, key=lambda item: item[0])
        medoid = items[medoid_idx]
        medoid_distances = [
            average_dtw_distance(medoid.angle_sequences, other.angle_sequences)
            for other in items
            if other is not medoid
        ]
        base_threshold = float(np.percentile(medoid_distances, 95)) if medoid_distances else 15.0
        threshold = max(base_threshold * threshold_scale, 5.0)
        profiles[exercise_name] = {
            "exercise_name": exercise_name,
            "exercise_slug": slugify_name(exercise_name),
            "template_name": medoid.name,
            "template_subject": medoid.subject_id,
            "template_angles": sorted(medoid.angle_sequences.keys()),
            "threshold": threshold,
            "intra_class_distances": medoid_distances,
            "medoid_template": medoid,
        }
    return profiles


def resolve_requested_exercise(exercise_name: str | None, profiles: dict[str, dict]) -> str | None:
    if exercise_name is None:
        return None
    if exercise_name in profiles:
        return exercise_name

    requested_slug = slugify_name(exercise_name)
    for key, profile in profiles.items():
        if requested_slug in {slugify_name(key), profile["exercise_slug"]}:
            return key
    raise KeyError(f"Unknown DTW exercise name: {exercise_name}")


def infer_with_dtw(
    angle_sequences: dict[str, np.ndarray],
    profiles: dict[str, dict],
    exercise_name: str | None,
) -> dict:
    requested_exercise = resolve_requested_exercise(exercise_name, profiles)
    candidate_names = [requested_exercise] if requested_exercise is not None else sorted(profiles)

    candidates = []
    for candidate_name in candidate_names:
        profile = profiles[candidate_name]
        distance = average_dtw_distance(angle_sequences, profile["medoid_template"].angle_sequences)
        threshold = profile["threshold"]
        score = distance / threshold if threshold > 0 else float("inf")
        candidates.append(
            {
                "exercise_name": candidate_name,
                "template_name": profile["template_name"],
                "template_subject": profile["template_subject"],
                "distance": distance,
                "threshold": threshold,
                "distance_ratio": score,
                "used_angles": profile["template_angles"],
            }
        )

    best = min(candidates, key=lambda item: item["distance_ratio"])
    return {
        "predicted_exercise": best["exercise_name"],
        "predicted_correct": bool(best["distance"] <= best["threshold"]),
        "distance": best["distance"],
        "threshold": best["threshold"],
        "distance_ratio": best["distance_ratio"],
        "template_name": best["template_name"],
        "template_subject": best["template_subject"],
        "used_angles": best["used_angles"],
        "all_candidates": candidates,
    }


def midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) * 0.5


def pose17_to_uiprmd22(coords: np.ndarray) -> np.ndarray:
    sequence = np.asarray(coords, dtype=np.float32)
    output = np.zeros((sequence.shape[0], 22, 3), dtype=np.float32)

    mid_hip = midpoint(sequence[:, L_HIP], sequence[:, R_HIP])
    mid_shoulder = midpoint(sequence[:, L_SHOULDER], sequence[:, R_SHOULDER])
    neck = mid_shoulder * 0.75 + sequence[:, NOSE] * 0.25
    head_tip = sequence[:, NOSE] + 0.35 * (sequence[:, NOSE] - mid_shoulder)

    output[:, 0, :2] = mid_hip
    output[:, 1, :2] = midpoint(mid_hip, mid_shoulder)
    output[:, 2, :2] = mid_shoulder
    output[:, 3, :2] = neck
    output[:, 4, :2] = sequence[:, NOSE]
    output[:, 5, :2] = head_tip

    output[:, 6, :2] = midpoint(neck, sequence[:, L_SHOULDER])
    output[:, 7, :2] = sequence[:, L_SHOULDER]
    output[:, 8, :2] = sequence[:, L_ELBOW]
    output[:, 9, :2] = sequence[:, L_WRIST]

    output[:, 10, :2] = midpoint(neck, sequence[:, R_SHOULDER])
    output[:, 11, :2] = sequence[:, R_SHOULDER]
    output[:, 12, :2] = sequence[:, R_ELBOW]
    output[:, 13, :2] = sequence[:, R_WRIST]

    output[:, 14, :2] = sequence[:, L_HIP]
    output[:, 15, :2] = sequence[:, L_KNEE]
    output[:, 16, :2] = sequence[:, L_ANKLE]
    output[:, 17, :2] = sequence[:, L_ANKLE] + 0.15 * (sequence[:, L_ANKLE] - sequence[:, L_KNEE])

    output[:, 18, :2] = sequence[:, R_HIP]
    output[:, 19, :2] = sequence[:, R_KNEE]
    output[:, 20, :2] = sequence[:, R_ANKLE]
    output[:, 21, :2] = sequence[:, R_ANKLE] + 0.15 * (sequence[:, R_ANKLE] - sequence[:, R_KNEE])

    return output


def build_stgcn_streams_from_pose(coords: np.ndarray, sequence_length: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    global_positions = pose17_to_uiprmd22(coords)
    global_positions = resample_sequence(global_positions, sequence_length)
    global_positions = normalize_global_positions(global_positions)

    joint_stream = global_positions.transpose(2, 0, 1).astype(np.float32)
    bone_stream = compute_bone_stream(global_positions).transpose(2, 0, 1).astype(np.float32)
    motion_stream = compute_motion_stream(global_positions).transpose(2, 0, 1).astype(np.float32)

    return (
        torch.from_numpy(joint_stream).unsqueeze(0),
        torch.from_numpy(bone_stream).unsqueeze(0),
        torch.from_numpy(motion_stream).unsqueeze(0),
    )


def resolve_stgcn_action_id(video_path: Path, action_id: int | None) -> int | None:
    if action_id is not None:
        return action_id - 1
    match = VIDEO_ACTION_RE.search(video_path.stem)
    if match:
        return int(match.group("action")) - 1
    return None


def collect_checkpoint_files(checkpoint_path: Path) -> list[Path]:
    if checkpoint_path.is_file():
        return [checkpoint_path]
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint path not found: {checkpoint_path}")

    fold_best = sorted(checkpoint_path.glob("fold_*/best_model.pth"))
    if fold_best:
        return fold_best

    recursive_best = sorted(checkpoint_path.rglob("best_model.pth"))
    if recursive_best:
        return recursive_best

    raise FileNotFoundError(f"No best_model.pth found under: {checkpoint_path}")


def load_stgcn_ensemble(checkpoint_path: Path, device: torch.device) -> tuple[list[dict], int]:
    checkpoint_files = collect_checkpoint_files(checkpoint_path)
    graph = Graph()
    ensemble: list[dict] = []
    num_actions = 10

    for ckpt_path in checkpoint_files:
        checkpoint = torch.load(ckpt_path, map_location=device, weights_only=False)
        meta = checkpoint.get("meta", {})
        args = checkpoint.get("args", {})
        num_actions = int(meta.get("num_actions", num_actions))
        dropout = float(args.get("dropout", 0.35))
        projection_dim = int(args.get("projection_dim", 128))

        model = MultiStreamSTGCNClassifier(
            graph.A,
            num_actions=num_actions,
            dropout=dropout,
            projection_dim=projection_dim,
        )
        state_dict = checkpoint.get("model_state_dict", checkpoint)
        model.load_state_dict(state_dict, strict=True)
        model.to(device)
        model.eval()
        prototypes_raw = checkpoint.get("prototypes", {})
        thresholds_raw = checkpoint.get("thresholds", {})
        prototypes = {
            int(action_id) - 1: np.asarray(vector, dtype=np.float32)
            for action_id, vector in prototypes_raw.items()
        }
        thresholds = {
            int(action_id) - 1: float(value)
            for action_id, value in thresholds_raw.items()
        }
        ensemble.append(
            {
                "model": model,
                "checkpoint_path": str(ckpt_path),
                "prototypes": prototypes,
                "thresholds": thresholds,
            }
        )

    if not ensemble:
        raise RuntimeError("No ST-GCN checkpoints were loaded.")
    return ensemble, num_actions


@torch.no_grad()
def infer_with_stgcn(
    ensemble: list[dict],
    num_actions: int,
    joint_stream: torch.Tensor,
    bone_stream: torch.Tensor,
    motion_stream: torch.Tensor,
    device: torch.device,
    stgcn_threshold: float,
    action_id: int | None,
) -> dict:
    joint_stream = joint_stream.to(device)
    bone_stream = bone_stream.to(device)
    motion_stream = motion_stream.to(device)

    candidate_ids = [action_id] if action_id is not None else list(range(num_actions))
    candidate_scores = []

    for candidate_id in candidate_ids:
        similarities = []
        thresholds = []

        for item in ensemble:
            model = item["model"]
            embedding = model(joint_stream, bone_stream, motion_stream, None)
            embedding_np = embedding[0].detach().cpu().numpy().astype(np.float32)
            prototype = item["prototypes"].get(candidate_id)
            if prototype is None:
                continue
            denom = np.linalg.norm(embedding_np) * np.linalg.norm(prototype)
            if denom <= 1e-12:
                continue
            similarities.append(float(np.dot(embedding_np, prototype) / denom))
            thresholds.append(float(item["thresholds"].get(candidate_id, stgcn_threshold)))

        if not similarities:
            continue

        mean_similarity = float(np.mean(similarities))
        mean_threshold = float(np.mean(thresholds)) if thresholds else stgcn_threshold
        mean_margin = mean_similarity - mean_threshold
        candidate_scores.append(
            {
                "action_id": candidate_id + 1,
                "action_name": UI_PRMD_ACTION_NAMES.get(candidate_id + 1, f"ui_action_{candidate_id + 1:02d}"),
                "similarity": mean_similarity,
                "threshold": mean_threshold,
                "margin": mean_margin,
            }
        )

    if not candidate_scores:
        raise RuntimeError("No ST-GCN prototype matched the requested action candidates.")

    best = max(candidate_scores, key=lambda item: item["margin"])
    return {
        "predicted_correct": bool(best["similarity"] >= best["threshold"]),
        "similarity": best["similarity"],
        "threshold": best["threshold"],
        "margin": best["margin"],
        "predicted_action_id": best["action_id"],
        "predicted_action_name": best["action_name"],
        "all_action_scores": candidate_scores,
    }


def save_results(output_dir: Path, rows: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "results.json"
    csv_path = output_dir / "results.csv"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(rows, file, indent=2, ensure_ascii=False)

    fieldnames = [
        "video",
        "fps",
        "frame_count",
        "dtw_predicted_correct",
        "dtw_predicted_exercise",
        "dtw_distance",
        "dtw_threshold",
        "dtw_distance_ratio",
        "stgcn_predicted_correct",
        "stgcn_similarity",
        "stgcn_threshold",
        "stgcn_margin",
        "stgcn_predicted_action_id",
        "stgcn_predicted_action_name",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def main() -> None:
    args = parse_args()
    videos = find_video_files(args.video_dir)
    if not videos:
        raise RuntimeError(f"No videos found in {args.video_dir}")

    output_dir = args.output_root / f"rehab_infer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.yolo_model)
    device = torch.device(args.device)

    dtw_profiles = None
    if args.method in {"dtw", "both"}:
        dtw_profiles = build_dtw_profiles(args.dtw_template_json, args.ulred_root, args.dtw_threshold_scale)
        summary = {
            key: {
                "template_name": value["template_name"],
                "template_subject": value["template_subject"],
                "threshold": value["threshold"],
                "template_angles": value["template_angles"],
            }
            for key, value in dtw_profiles.items()
        }
        with open(output_dir / "dtw_profiles.json", "w", encoding="utf-8") as file:
            json.dump(summary, file, indent=2, ensure_ascii=False)

    stgcn_models = []
    stgcn_num_actions = 10
    if args.method in {"stgcn", "both"}:
        stgcn_models, stgcn_num_actions = load_stgcn_ensemble(args.stgcn_checkpoint, device)

    all_results: list[dict] = []

    for video_path in videos:
        pose = extract_pose_sequence(video_path, model, args.device, args.det_conf)
        filled_coords = fill_nan_pose_sequence(pose.coords)
        filled_coords = smooth_pose_sequence(filled_coords, window_size=5)

        if args.save_pose_npy:
            np.save(output_dir / f"{video_path.stem}_pose.npy", filled_coords)

        result_row = {
            "video": video_path.name,
            "fps": safe_float(pose.fps),
            "frame_count": pose.frame_count,
        }

        if args.method in {"dtw", "both"}:
            angle_sequences = build_angle_sequences(filled_coords, pose.confs, args.kp_conf)
            dtw_result = infer_with_dtw(angle_sequences, dtw_profiles, args.exercise_name)
            result_row.update(
                {
                    "dtw_predicted_correct": dtw_result["predicted_correct"],
                    "dtw_predicted_exercise": dtw_result["predicted_exercise"],
                    "dtw_distance": safe_float(dtw_result["distance"]),
                    "dtw_threshold": safe_float(dtw_result["threshold"]),
                    "dtw_distance_ratio": safe_float(dtw_result["distance_ratio"]),
                    "dtw_template_name": dtw_result["template_name"],
                    "dtw_template_subject": dtw_result["template_subject"],
                    "dtw_all_candidates": dtw_result["all_candidates"],
                }
            )

        if args.method in {"stgcn", "both"}:
            joint_stream, bone_stream, motion_stream = build_stgcn_streams_from_pose(
                filled_coords, args.sequence_length
            )
            resolved_action_id = resolve_stgcn_action_id(video_path, args.action_id)
            stgcn_result = infer_with_stgcn(
                stgcn_models,
                stgcn_num_actions,
                joint_stream,
                bone_stream,
                motion_stream,
                device,
                args.stgcn_threshold,
                resolved_action_id,
            )
            result_row.update(
                {
                    "stgcn_predicted_correct": stgcn_result["predicted_correct"],
                    "stgcn_similarity": safe_float(stgcn_result["similarity"]),
                    "stgcn_threshold": safe_float(stgcn_result["threshold"]),
                    "stgcn_margin": safe_float(stgcn_result["margin"]),
                    "stgcn_predicted_action_id": stgcn_result["predicted_action_id"],
                    "stgcn_predicted_action_name": stgcn_result["predicted_action_name"],
                    "stgcn_all_action_scores": stgcn_result["all_action_scores"],
                }
            )

        all_results.append(result_row)
        print(json.dumps(result_row, ensure_ascii=False))

    save_results(output_dir, all_results)

    run_config = {
        "video_dir": str(args.video_dir),
        "method": args.method,
        "yolo_model": args.yolo_model,
        "device": args.device,
        "det_conf": args.det_conf,
        "kp_conf": args.kp_conf,
        "sequence_length": args.sequence_length,
        "stgcn_checkpoint": str(args.stgcn_checkpoint),
        "stgcn_threshold": args.stgcn_threshold,
        "action_id": args.action_id,
        "dtw_template_json": str(args.dtw_template_json),
        "ulred_root": str(args.ulred_root),
        "exercise_name": args.exercise_name,
        "dtw_threshold_scale": args.dtw_threshold_scale,
        "video_count": len(videos),
    }
    with open(output_dir / "run_config.json", "w", encoding="utf-8") as file:
        json.dump(run_config, file, indent=2, ensure_ascii=False)

    print(f"[INFO] Saved inference results to: {output_dir}")


if __name__ == "__main__":
    main()
