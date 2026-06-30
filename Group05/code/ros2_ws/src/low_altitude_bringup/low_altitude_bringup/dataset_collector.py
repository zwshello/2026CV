"""ROS 2 node that records (image, YOLO label) pairs from a running sim.

The node subscribes to the camera image and ``CameraInfo`` topics, then uses
Gazebo Transport to read the live pose of every spawned target listed in the
manifest written by ``sim/launch/spawn_targets.py``. For each captured frame
it projects every target's 3D AABB into the image plane and writes a YOLO
label file alongside the image.

This file is part of the ``low_altitude_bringup`` ROS 2 package and is
registered as a console entry point so it can be launched via
``ros2 run low_altitude_bringup dataset_collector``.

Run example::

    ros2 run low_altitude_bringup dataset_collector \\
        --ros-args \\
        -p manifest_path:=/home/libo/2026CV/sim/runtime/spawned_latest.json \\
        -p output_dir:=/home/libo/2026CV/dataset/sim_v1 \\
        -p capture_hz:=2.0 \\
        -p target_total_frames:=5000

The collector exits cleanly once ``target_total_frames`` is reached.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image

# Local geometry helpers — vendored copy lives in this package so the
# collector works without ``vision/`` on PYTHONPATH (e.g. after a normal
# colcon install).
from .projection import (
    CameraIntrinsics,
    Pose,
    VisibilityFilter,
    project_aabb,
    to_yolo_line,
)

# Gazebo Transport for camera + per-model poses (sensor pose is best read
# straight from gz_transport rather than relying on a TF tree that we have
# not configured).
from gz.msgs10.pose_v_pb2 import Pose_V as GzPoseV  # type: ignore
from gz.transport13 import Node as GzNode  # type: ignore


@dataclass
class _TargetSpec:
    name: str
    class_id: int
    aabb_size: tuple[float, float, float]


@dataclass
class _LiveTarget:
    spec: _TargetSpec
    pose: Pose | None = None


class DatasetCollector(Node):
    """Record (image, label) pairs using ground-truth poses for auto-labelling."""

    def __init__(self) -> None:
        super().__init__("dataset_collector")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("camera_info_topic", "/camera/camera_info")
        self.declare_parameter("manifest_path", "")
        self.declare_parameter(
            "world", "baylands",
            descriptor=None,
        )
        self.declare_parameter(
            "camera_pose_gz_topic",
            "/world/baylands/pose/info",
            descriptor=None,
        )
        self.declare_parameter(
            "camera_link_name",
            "x500_gimbal_0::camera_link",
            descriptor=None,
        )
        self.declare_parameter("output_dir", "")
        self.declare_parameter("capture_hz", 2.0)
        self.declare_parameter("target_total_frames", 5000)
        self.declare_parameter("min_visible_fraction", 0.5)
        self.declare_parameter("min_pixel_size", 6)
        self.declare_parameter("max_distance_m", 150.0)
        self.declare_parameter("jpeg_quality", 90)

        self._image_topic = str(self.get_parameter("image_topic").value)
        self._camera_info_topic = str(self.get_parameter("camera_info_topic").value)
        self._manifest_path = str(self.get_parameter("manifest_path").value)
        self._world = str(self.get_parameter("world").value)
        self._camera_pose_topic = str(self.get_parameter("camera_pose_gz_topic").value)
        self._camera_link_name = str(self.get_parameter("camera_link_name").value)
        self._output_dir = str(self.get_parameter("output_dir").value)
        self._capture_hz = float(self.get_parameter("capture_hz").value)
        self._target_total_frames = int(self.get_parameter("target_total_frames").value)
        self._jpeg_quality = int(self.get_parameter("jpeg_quality").value)

        if not self._manifest_path or not Path(self._manifest_path).is_file():
            raise RuntimeError(f"manifest_path missing or not a file: {self._manifest_path}")
        if not self._output_dir:
            raise RuntimeError("output_dir must be provided")

        self._vis = VisibilityFilter(
            min_visible_fraction=float(self.get_parameter("min_visible_fraction").value),
            min_pixel_size=int(self.get_parameter("min_pixel_size").value),
            max_distance_m=float(self.get_parameter("max_distance_m").value),
        )

        # Output layout: train/val split happens later in build_yolo_dataset.py.
        self._images_dir = Path(self._output_dir) / "images" / "raw"
        self._labels_dir = Path(self._output_dir) / "labels" / "raw"
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._labels_dir.mkdir(parents=True, exist_ok=True)

        self._intrinsics: CameraIntrinsics | None = None
        self._cam_pose: Pose | None = None
        self._targets: dict[str, _LiveTarget] = {}
        self._latest_image: Image | None = None
        self._latest_image_lock = threading.Lock()
        self._frame_count = 0
        self._min_capture_period = 1.0 / max(self._capture_hz, 0.05)
        self._last_capture_t = 0.0

        self._load_manifest()
        self._setup_subscriptions()

        self.get_logger().info(
            f"Dataset collector ready — output: {self._output_dir}, target frames: "
            f"{self._target_total_frames}, capture_hz: {self._capture_hz}"
        )

    # ------------------------------------------------------------------ setup

    def _load_manifest(self) -> None:
        with open(self._manifest_path, "r", encoding="utf-8") as fh:
            payload: dict[str, Any] = json.load(fh)
        for entry in payload.get("targets", []):
            spec = _TargetSpec(
                name=str(entry["name"]),
                class_id=int(entry["class_id"]),
                aabb_size=tuple(entry["aabb_size"]),
            )
            self._targets[spec.name] = _LiveTarget(spec=spec)
        self.get_logger().info(f"Loaded {len(self._targets)} targets from manifest")

    def _setup_subscriptions(self) -> None:
        image_qos = QoSProfile(depth=5)
        image_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(Image, self._image_topic, self._on_image, image_qos)
        self.create_subscription(
            CameraInfo, self._camera_info_topic, self._on_camera_info, 5
        )

        self._gz_node = GzNode()
        # Single global pose stream contains every model — much cheaper than
        # one subscription per model.
        if not self._gz_node.subscribe(GzPoseV, self._camera_pose_topic, self._on_gz_poses):
            raise RuntimeError(
                f"Failed to subscribe to Gazebo pose topic: {self._camera_pose_topic}"
            )

    # --------------------------------------------------------------- callbacks

    def _on_camera_info(self, msg: CameraInfo) -> None:
        if self._intrinsics is not None:
            return
        if not msg.k or len(msg.k) < 9 or msg.width == 0 or msg.height == 0:
            return
        self._intrinsics = CameraIntrinsics.from_camera_info_k(
            list(msg.k), msg.width, msg.height
        )
        self.get_logger().info(
            f"Camera intrinsics locked: fx={self._intrinsics.fx:.1f} "
            f"fy={self._intrinsics.fy:.1f} cx={self._intrinsics.cx:.1f} "
            f"cy={self._intrinsics.cy:.1f} ({self._intrinsics.width}x{self._intrinsics.height})"
        )

    def _on_image(self, msg: Image) -> None:
        with self._latest_image_lock:
            self._latest_image = msg
        self._maybe_capture()

    def _on_gz_poses(self, msg: GzPoseV) -> None:
        for pose_msg in msg.pose:
            name = pose_msg.name
            xyz = (
                float(pose_msg.position.x),
                float(pose_msg.position.y),
                float(pose_msg.position.z),
            )
            quat = (
                float(pose_msg.orientation.x),
                float(pose_msg.orientation.y),
                float(pose_msg.orientation.z),
                float(pose_msg.orientation.w),
            )
            pose = Pose(xyz=xyz, quat_xyzw=quat)
            if name == self._camera_link_name:
                self._cam_pose = pose
                continue
            target = self._targets.get(name)
            if target is not None:
                target.pose = pose

    # ---------------------------------------------------------------- capture

    def _maybe_capture(self) -> None:
        now = time.monotonic()
        if now - self._last_capture_t < self._min_capture_period:
            return
        if self._intrinsics is None or self._cam_pose is None:
            return
        with self._latest_image_lock:
            image = self._latest_image
        if image is None:
            return
        rgb = self._image_to_rgb(image)
        if rgb is None:
            return
        labels = self._build_labels()
        if not self._write_pair(rgb, labels):
            return
        self._last_capture_t = now
        self._frame_count += 1
        if self._frame_count % 50 == 0 or self._frame_count == 1:
            self.get_logger().info(
                f"Captured {self._frame_count}/{self._target_total_frames} frames "
                f"(latest had {len(labels)} labels)"
            )
        if self._frame_count >= self._target_total_frames:
            self.get_logger().info("Target frame count reached — shutting down.")
            rclpy.shutdown()

    def _image_to_rgb(self, msg: Image) -> np.ndarray | None:
        h, w = int(msg.height), int(msg.width)
        if h <= 0 or w <= 0:
            return None
        enc = msg.encoding
        buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        if enc in ("rgb8", "bgr8"):
            arr = buf.reshape((h, w, 3))
            if enc == "bgr8":
                arr = arr[:, :, ::-1]
            return np.ascontiguousarray(arr)
        if enc == "rgba8":
            return np.ascontiguousarray(buf.reshape((h, w, 4))[:, :, :3])
        if enc == "mono8":
            gray = buf.reshape((h, w))
            return np.repeat(gray[:, :, None], 3, axis=2)
        self.get_logger().warning(f"Unsupported image encoding: {enc!r}")
        return None

    def _build_labels(self) -> list[str]:
        assert self._intrinsics is not None
        assert self._cam_pose is not None
        labels: list[str] = []
        for target in self._targets.values():
            if target.pose is None:
                continue
            bbox = project_aabb(
                center_xyz=target.pose.xyz,
                yaw=self._yaw_from_quat(target.pose.quat_xyzw),
                size=target.spec.aabb_size,
                cam_pose=self._cam_pose,
                intrinsics=self._intrinsics,
                vis=self._vis,
            )
            if bbox is None:
                continue
            labels.append(
                to_yolo_line(
                    target.spec.class_id, bbox, self._intrinsics.width, self._intrinsics.height
                )
            )
        return labels

    @staticmethod
    def _yaw_from_quat(q: tuple[float, float, float, float]) -> float:
        x, y, z, w = q
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return float(np.arctan2(siny_cosp, cosy_cosp))

    def _write_pair(self, rgb: np.ndarray, labels: list[str]) -> bool:
        from PIL import Image as PILImage  # imported lazily so unit tests don't need PIL

        stamp = f"{self._frame_count:06d}_{int(time.time() * 1000) % 1_000_000_000:09d}"
        img_path = self._images_dir / f"{stamp}.jpg"
        lbl_path = self._labels_dir / f"{stamp}.txt"
        try:
            PILImage.fromarray(rgb).save(img_path, "JPEG", quality=self._jpeg_quality)
        except OSError as exc:
            self.get_logger().error(f"Failed to write image {img_path}: {exc}")
            return False
        # Empty label file is valid (background frame); keep it so the dataset
        # builder can include negative samples.
        lbl_path.write_text("\n".join(labels), encoding="utf-8")
        return True


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: DatasetCollector | None = None
    try:
        node = DatasetCollector()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # pragma: no cover - top-level guard
        if node is not None:
            node.get_logger().error(f"dataset_collector fatal error: {exc}")
        else:
            print(f"dataset_collector fatal error: {exc}", file=sys.stderr)
        raise
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
