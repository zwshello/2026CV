"""ROS 2 YOLO detector node.

Focuses on ROS plumbing and inference; rolling stats, HUD overlay, dashboard
rendering and result archival are delegated to dedicated modules under this
package.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
    qos_profile_sensor_data,
)
from sensor_msgs.msg import Image
from std_msgs.msg import String

from low_altitude_bringup import dashboard
from low_altitude_bringup.hud import load_default_font, render_annotated_rgb
from low_altitude_bringup.image_utils import image_message_to_rgb, rgb_to_image_message
from low_altitude_bringup.metrics import PerceptionMetrics
from low_altitude_bringup.results_recorder import ResultsRecorder

try:
    from PIL import Image as PilImage
except Exception:  # pragma: no cover
    PilImage = None

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover
    YOLO = None


def _normalize_model_path(raw_path: str) -> str:
    if len(raw_path) >= 3 and raw_path[1] == ":" and raw_path[2] in ("\\", "/"):
        drive = raw_path[0].lower()
        tail = raw_path[3:].replace("\\", "/")
        return f"/mnt/{drive}/{tail}"
    return raw_path


def _resolve_model_path(configured_path: str) -> str:
    normalized = _normalize_model_path(configured_path.strip())
    configured = pathlib.Path(normalized).expanduser()

    candidates: list[pathlib.Path] = []
    if configured.is_absolute():
        candidates.append(configured)
    else:
        candidates.append(pathlib.Path.cwd() / configured)
        file_path = pathlib.Path(__file__).resolve()
        ros2_ws_root = next(
            (parent for parent in file_path.parents if parent.name == "ros2_ws"),
            None,
        )
        if ros2_ws_root is not None:
            candidates.append(ros2_ws_root / configured)
            candidates.append(ros2_ws_root.parent / configured)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return normalized


class YoloDetector(Node):
    """ROS 2 image detector backed by YOLOv8 when runtime dependencies exist."""

    def __init__(self) -> None:
        super().__init__("yolo_detector")
        self._declare_parameters()
        self._read_parameters()

        self._metrics = PerceptionMetrics(window_size=self._window_size)
        self._model: Any | None = None
        self._model_ready = False
        self._model_error: str | None = None
        self._resolved_model_path: str | None = None
        self._status_publish_count = 0
        self._font = load_default_font()

        self._console = dashboard.make_console() if self._use_rich else None
        self._live: Any | None = None

        self._results = ResultsRecorder(
            output_dir=self._results_dir,
            summary_interval_sec=self._summary_interval_sec,
            enabled=self._record_results,
        )

        self._publisher = self.create_publisher(String, self._detection_topic, 10)
        self._annotated_publisher = self.create_publisher(
            Image, self._annotated_image_topic, qos_profile_sensor_data
        )
        # Image input: best_effort + depth=1 so DDS itself drops old frames if
        # we are slower than the publisher (works in concert with the upstream
        # image_throttle relay node).
        image_sub_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self.create_subscription(
            Image, self._image_topic, self._image_callback, image_sub_qos
        )

        self._load_model()

        if self._heartbeat_interval_sec > 0.0:
            self.create_timer(self._heartbeat_interval_sec, self._heartbeat_callback)
        if self._enable_dashboard:
            if self._use_rich and dashboard.rich_available():
                self._live = dashboard.make_live(
                    self._console,
                    self._dashboard_refresh_hz,
                    dashboard.render_panel(self._metrics, model_ready=self._model_ready),
                )
                if self._live is not None:
                    self._live.start()
            self.create_timer(1.0 / self._dashboard_refresh_hz, self._dashboard_tick)

        self.get_logger().info(
            "YOLO detector listening to "
            f"{self._image_topic}, publishing detections to {self._detection_topic}, "
            f"and annotated frames to {self._annotated_image_topic}"
        )
        if self._results.enabled:
            self.get_logger().info(
                f"Recording detections to {self._results.jsonl_path} "
                f"and summary to {self._results.summary_path}"
            )

        if self._publish_startup_status:
            self._publish_status(
                {
                    "event": "startup",
                    "status": "ready" if self._model_ready else "model_unavailable",
                    "model_configured": self._model_path,
                    "model_resolved": self._resolved_model_path,
                    "heartbeat_interval_sec": self._heartbeat_interval_sec,
                    "report_every_n_frames": self._report_every_n_frames,
                }
            )

    # ------------------------------------------------------------------ params
    def _declare_parameters(self) -> None:
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("detection_topic", "/detections/yolo")
        self.declare_parameter("annotated_image_topic", "/camera/annotated")
        self.declare_parameter("model_path", "yolov8n.pt")
        self.declare_parameter("confidence", 0.25)
        self.declare_parameter("device", "")
        self.declare_parameter("report_every_n_frames", 1)
        self.declare_parameter("imgsz", 480)
        self.declare_parameter("publish_annotated", True)
        self.declare_parameter("save_annotated", False)
        self.declare_parameter("save_every_n_frames", 30)
        self.declare_parameter("annotated_dir", "/home/libo/2026CV/demo/ros2_outputs")
        self.declare_parameter("publish_startup_status", True)
        self.declare_parameter("heartbeat_interval_sec", 5.0)
        self.declare_parameter("log_every_n_status", 1)
        self.declare_parameter("enable_hud", True)
        self.declare_parameter("enable_dashboard", True)
        self.declare_parameter("use_rich", True)
        self.declare_parameter("dashboard_refresh_hz", 2.0)
        self.declare_parameter("window_size", 30)
        self.declare_parameter("record_results", True)
        self.declare_parameter("results_dir", "/home/libo/2026CV/demo/ros2_outputs")
        self.declare_parameter("summary_interval_sec", 5.0)

    def _read_parameters(self) -> None:
        gp = self.get_parameter
        self._image_topic = str(gp("image_topic").value)
        self._detection_topic = str(gp("detection_topic").value)
        self._annotated_image_topic = str(gp("annotated_image_topic").value)
        self._model_path = str(gp("model_path").value)
        self._confidence = float(gp("confidence").value)
        self._device = str(gp("device").value)
        self._report_every_n_frames = max(1, int(gp("report_every_n_frames").value))
        self._imgsz = max(160, int(gp("imgsz").value))
        self._publish_annotated = bool(gp("publish_annotated").value)
        self._save_annotated = bool(gp("save_annotated").value)
        self._save_every_n_frames = max(1, int(gp("save_every_n_frames").value))
        self._publish_startup_status = bool(gp("publish_startup_status").value)
        self._heartbeat_interval_sec = max(0.0, float(gp("heartbeat_interval_sec").value))
        self._log_every_n_status = max(1, int(gp("log_every_n_status").value))
        self._enable_hud = bool(gp("enable_hud").value)
        self._enable_dashboard = bool(gp("enable_dashboard").value)
        self._use_rich = bool(gp("use_rich").value) and dashboard.rich_available()
        self._dashboard_refresh_hz = max(0.5, float(gp("dashboard_refresh_hz").value))
        self._window_size = max(5, int(gp("window_size").value))
        self._record_results = bool(gp("record_results").value)
        self._results_dir = pathlib.Path(str(gp("results_dir").value))
        self._summary_interval_sec = max(1.0, float(gp("summary_interval_sec").value))

        self._annotated_dir = pathlib.Path(str(gp("annotated_dir").value))
        if self._save_annotated:
            try:
                self._annotated_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                self.get_logger().warning(
                    "Failed to create annotated_dir, disabling save_annotated: "
                    f"{self._annotated_dir} ({exc})"
                )
                self._save_annotated = False

    # ------------------------------------------------------------------- model
    def _load_model(self) -> None:
        if YOLO is None:
            self._model_error = (
                "ultralytics is not installed in WSL. Install runtime dependencies "
                "before using yolo_detector."
            )
            self.get_logger().warning(self._model_error)
            return
        resolved = _resolve_model_path(self._model_path)
        self._resolved_model_path = resolved
        try:
            self._model = YOLO(resolved)
            self._model_ready = True
            self.get_logger().info(
                f"Loaded YOLO model: configured={self._model_path} resolved={resolved}"
            )
        except Exception as exc:  # pragma: no cover
            self._model_error = (
                f"failed to load YOLO model configured={self._model_path} "
                f"resolved={resolved}: {exc}"
            )
            self.get_logger().error(self._model_error)

    # ------------------------------------------------------------- main path
    def _image_callback(self, msg: Image) -> None:
        self._metrics.mark_input()
        if self._metrics.frame_count % self._report_every_n_frames != 0:
            return

        try:
            frame = image_message_to_rgb(msg)
        except ValueError as exc:
            self.get_logger().warning(str(exc))
            return

        if not self._model_ready or self._model is None:
            self._metrics.mark_model_unavailable()
            if self._publish_annotated:
                annotated = render_annotated_rgb(
                    frame.rgb,
                    [],
                    metrics=self._metrics,
                    model_ready=False,
                    font=self._font,
                    enable_hud=self._enable_hud,
                )
                self._publish_annotated_image(annotated, msg)
            self._publish_status(
                {
                    "frame": self._metrics.frame_count,
                    "status": "model_unavailable",
                    "reason": self._model_error or "unknown",
                    "width": frame.width,
                    "height": frame.height,
                    "encoding": frame.encoding,
                }
            )
            return

        started = time.time()
        try:
            result = self._model.predict(
                source=frame.rgb,
                conf=self._confidence,
                device=self._device or None,
                imgsz=self._imgsz,
                verbose=False,
            )[0]
        except Exception as exc:  # pragma: no cover
            self._metrics.mark_failure()
            self.get_logger().error(f"YOLO inference failed: {exc}")
            self._publish_status(
                {
                    "frame": self._metrics.frame_count,
                    "status": "inference_failed",
                    "reason": str(exc),
                }
            )
            return

        detections = self._extract_detections(result)
        latency_ms = round((time.time() - started) * 1000.0, 2)
        self._metrics.mark_inference(latency_ms, detections)

        summary = {
            "frame": self._metrics.frame_count,
            "status": "ok",
            "width": frame.width,
            "height": frame.height,
            "encoding": frame.encoding,
            "latency_ms": latency_ms,
            "detections": detections,
        }
        self._publish_status(summary)
        self._results.append_frame(summary)
        self._results.maybe_write_summary(
            self._metrics,
            model_ready=self._model_ready,
            model_path=self._resolved_model_path,
        )

        annotated = render_annotated_rgb(
            frame.rgb,
            detections,
            metrics=self._metrics,
            model_ready=True,
            font=self._font,
            enable_hud=self._enable_hud,
        )
        if self._publish_annotated:
            self._publish_annotated_image(annotated, msg)
        if self._save_annotated and self._metrics.frame_count % self._save_every_n_frames == 0:
            self._save_annotated_image(annotated)

    @staticmethod
    def _extract_detections(result: Any) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return detections
        names = getattr(result, "names", {})
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item()) if box.cls is not None else -1
            conf = float(box.conf[0].item()) if box.conf is not None else 0.0
            detections.append(
                {
                    "class_id": cls_id,
                    "label": names.get(cls_id, str(cls_id)),
                    "confidence": round(conf, 4),
                    "bbox_xyxy": [round(v, 2) for v in xyxy],
                }
            )
        return detections

    # ---------------------------------------------------------------- timers
    def _heartbeat_callback(self) -> None:
        last_age = self._metrics.last_image_age()
        last_age_rounded = None if last_age is None else round(last_age, 3)
        self._publish_status(
            {
                "event": "heartbeat",
                "status": "ready" if self._model_ready else "model_unavailable",
                "frame_count": self._metrics.frame_count,
                "inference_failures": self._metrics.inference_failures,
                "model_configured": self._model_path,
                "model_resolved": self._resolved_model_path,
                "last_image_age_sec": last_age_rounded,
                "reason": self._model_error,
            }
        )
        self._results.maybe_write_summary(
            self._metrics,
            model_ready=self._model_ready,
            model_path=self._resolved_model_path,
            force=True,
        )

    def _dashboard_tick(self) -> None:
        if self._use_rich and self._live is not None:
            try:
                self._live.update(
                    dashboard.render_panel(self._metrics, model_ready=self._model_ready)
                )
            except Exception:
                pass
        else:
            self.get_logger().info(
                dashboard.plain_summary_line(self._metrics, model_ready=self._model_ready)
            )

    # ----------------------------------------------------------- publishing
    def _publish_status(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self._publisher.publish(msg)
        self._status_publish_count += 1
        status = str(payload.get("status", ""))
        event = str(payload.get("event", ""))
        should_log = (
            status != "ok"
            or event in ("startup", "heartbeat")
            or self._status_publish_count % self._log_every_n_status == 0
        )
        if should_log:
            self.get_logger().info(msg.data)

    def _publish_annotated_image(self, annotated: Any, source_msg: Image) -> None:
        try:
            rgb_array = (
                annotated
                if isinstance(annotated, np.ndarray)
                else np.array(annotated, dtype=np.uint8)
            )
            msg = rgb_to_image_message(
                rgb_array,
                frame_id=source_msg.header.frame_id or "camera_link",
                stamp=source_msg.header.stamp,
            )
            self._annotated_publisher.publish(msg)
        except Exception as exc:  # pragma: no cover
            self.get_logger().warning(f"Failed to publish annotated image: {exc}")

    def _save_annotated_image(self, annotated: Any) -> None:
        if PilImage is None:
            self.get_logger().warning(
                "Pillow is unavailable, skipping annotated image export."
            )
            return
        image = (
            annotated
            if not isinstance(annotated, np.ndarray)
            else PilImage.fromarray(annotated, mode="RGB")
        )
        path = self._annotated_dir / f"annotated_{self._metrics.frame_count:06d}.jpg"
        image.save(path, format="JPEG", quality=90)
        self.get_logger().info(f"Saved annotated frame to {path}")

    # ---------------------------------------------------------------- shutdown
    def shutdown(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
        self._results.maybe_write_summary(
            self._metrics,
            model_ready=self._model_ready,
            model_path=self._resolved_model_path,
            force=True,
        )


def main() -> None:
    rclpy.init()
    node = YoloDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()
