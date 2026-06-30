from __future__ import annotations

import pathlib
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from low_altitude_bringup.image_utils import image_frame_to_ppm, image_message_to_rgb


class ImageSnapshot(Node):
    """Persist periodic ROS 2 camera frames for quick debugging."""

    def __init__(self) -> None:
        super().__init__("image_snapshot")
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("output_dir", "/tmp/ros2_camera_snapshots")
        self.declare_parameter("save_interval_sec", 1.0)
        self.declare_parameter("max_files", 20)

        image_topic = self.get_parameter("image_topic").value
        self._output_dir = pathlib.Path(self.get_parameter("output_dir").value)
        self._save_interval_sec = float(
            self.get_parameter("save_interval_sec").value
        )
        self._max_files = max(1, int(self.get_parameter("max_files").value))
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._last_save_time = 0.0
        self._save_index = 0

        self.create_subscription(
            Image,
            image_topic,
            self._image_callback,
            qos_profile_sensor_data,
        )
        self.get_logger().info(
            f"Saving periodic snapshots from {image_topic} into {self._output_dir}"
        )

    def _image_callback(self, msg: Image) -> None:
        now = time.time()
        if now - self._last_save_time < self._save_interval_sec:
            return

        try:
            frame = image_message_to_rgb(msg)
            snapshot = image_frame_to_ppm(frame)
        except ValueError as exc:
            self.get_logger().warning(str(exc))
            return

        slot = self._save_index % self._max_files
        path = self._output_dir / f"snapshot_{slot:02d}.ppm"
        path.write_bytes(snapshot)
        latest_path = self._output_dir / "latest_snapshot.txt"
        latest_path.write_text(path.name, encoding="ascii")

        self._last_save_time = now
        self._save_index += 1
        self.get_logger().info(
            f"Saved snapshot {path.name} ({frame.width}x{frame.height}, {frame.encoding})"
        )


def main() -> None:
    rclpy.init()
    node = ImageSnapshot()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
