"""Vendored copy of ``vision.dataset.projection``.

Kept inside the ROS package so the dataset collector works in both the
source-tree and ``colcon install`` layouts without depending on
``vision/`` being on PYTHONPATH. If you fix a bug here, also update the
canonical copy at ``vision/dataset/projection.py`` (and re-run
``vision/dataset/test_projection.py``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_ROS_TO_OPTICAL = np.array(
    [
        [0.0, -1.0, 0.0],
        [0.0, 0.0, -1.0],
        [1.0, 0.0, 0.0],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @classmethod
    def from_camera_info_k(cls, k: list[float], width: int, height: int) -> "CameraIntrinsics":
        return cls(fx=k[0], fy=k[4], cx=k[2], cy=k[5], width=int(width), height=int(height))


@dataclass(frozen=True)
class Pose:
    xyz: tuple[float, float, float]
    quat_xyzw: tuple[float, float, float, float]

    def rotation_matrix(self) -> np.ndarray:
        x, y, z, w = self.quat_xyzw
        n = x * x + y * y + z * z + w * w
        if n < 1e-12:
            return np.eye(3, dtype=np.float64)
        s = 2.0 / n
        return np.array(
            [
                [1.0 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
                [s * (x * y + z * w), 1.0 - s * (x * x + z * z), s * (y * z - x * w)],
                [s * (x * z - y * w), s * (y * z + x * w), 1.0 - s * (x * x + y * y)],
            ],
            dtype=np.float64,
        )

    def translation(self) -> np.ndarray:
        return np.asarray(self.xyz, dtype=np.float64)


@dataclass(frozen=True)
class VisibilityFilter:
    min_visible_fraction: float = 0.5
    min_pixel_size: int = 6
    max_distance_m: float = 150.0


def _world_to_optical(world_xyz: np.ndarray, cam_pose: Pose) -> np.ndarray:
    rwc = cam_pose.rotation_matrix()
    twc = cam_pose.translation()
    cam_frame = (world_xyz - twc) @ rwc
    return cam_frame @ _ROS_TO_OPTICAL.T


def _aabb_corners(center: np.ndarray, yaw: float, size: tuple[float, float, float]) -> np.ndarray:
    sx, sy, sz = size
    half = np.array([sx, sy, sz], dtype=np.float64) * 0.5
    signs = np.array(
        [
            [-1, -1, -1], [-1, -1, 1], [-1, 1, -1], [-1, 1, 1],
            [1, -1, -1], [1, -1, 1], [1, 1, -1], [1, 1, 1],
        ],
        dtype=np.float64,
    )
    local = signs * half
    cy_, sy_ = float(np.cos(yaw)), float(np.sin(yaw))
    rot = np.array(
        [
            [cy_, -sy_, 0.0],
            [sy_, cy_, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    return (local @ rot.T) + center


def project_aabb(
    *,
    center_xyz: tuple[float, float, float],
    yaw: float,
    size: tuple[float, float, float],
    cam_pose: Pose,
    intrinsics: CameraIntrinsics,
    vis: VisibilityFilter = VisibilityFilter(),
) -> tuple[float, float, float, float] | None:
    center = np.asarray(center_xyz, dtype=np.float64)
    distance = float(np.linalg.norm(center - cam_pose.translation()))
    if distance > vis.max_distance_m:
        return None
    corners_world = _aabb_corners(center, yaw, size)
    corners_cam = _world_to_optical(corners_world, cam_pose)
    if np.min(corners_cam[:, 2]) <= 0.05:
        return None
    z = corners_cam[:, 2]
    u = intrinsics.fx * corners_cam[:, 0] / z + intrinsics.cx
    v = intrinsics.fy * corners_cam[:, 1] / z + intrinsics.cy
    x_min_full = float(np.min(u))
    y_min_full = float(np.min(v))
    x_max_full = float(np.max(u))
    y_max_full = float(np.max(v))
    full_w = max(x_max_full - x_min_full, 1e-3)
    full_h = max(y_max_full - y_min_full, 1e-3)
    full_area = full_w * full_h
    x_min = max(x_min_full, 0.0)
    y_min = max(y_min_full, 0.0)
    x_max = min(x_max_full, float(intrinsics.width - 1))
    y_max = min(y_max_full, float(intrinsics.height - 1))
    if x_max - x_min < vis.min_pixel_size or y_max - y_min < vis.min_pixel_size:
        return None
    visible_area = (x_max - x_min) * (y_max - y_min)
    if visible_area / full_area < vis.min_visible_fraction:
        return None
    return (x_min, y_min, x_max, y_max)


def to_yolo_line(
    class_id: int,
    bbox_xyxy: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> str:
    x_min, y_min, x_max, y_max = bbox_xyxy
    cx = ((x_min + x_max) * 0.5) / image_width
    cy = ((y_min + y_max) * 0.5) / image_height
    w = (x_max - x_min) / image_width
    h = (y_max - y_min) / image_height
    return f"{int(class_id)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
