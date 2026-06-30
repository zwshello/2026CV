from __future__ import annotations

from typing import Final

import rclpy
from gz.msgs10.image_pb2 import Image as GzImage
from gz.transport13 import Node as GzNode
from rclpy.node import Node
from sensor_msgs.msg import Image


class GzCameraBridge(Node):
    """Bridge a Gazebo Transport camera topic into a ROS 2 Image topic."""

    _RGB_CHANNELS: Final[int] = 3
    _RGBA_CHANNELS: Final[int] = 4
    _GRAY_CHANNELS: Final[int] = 1

    def __init__(self) -> None:
        super().__init__("gz_camera_bridge")
        self.declare_parameter(
            "gz_image_topic",
            "/world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image",
        )
        self.declare_parameter("image_topic", "/camera/image_raw")

        self._gz_image_topic = str(self.get_parameter("gz_image_topic").value)
        image_topic = str(self.get_parameter("image_topic").value)
        self._publisher = self.create_publisher(Image, image_topic, 10)
        self._frame_count = 0

        self._gz_node = GzNode()
        if not self._gz_node.subscribe(
            GzImage, self._gz_image_topic, self._handle_gz_image
        ):
            raise RuntimeError(
                f"Failed to subscribe to Gazebo image topic: {self._gz_image_topic}"
            )

        self.get_logger().info(
            f"Bridging Gazebo image {self._gz_image_topic} to ROS 2 topic {image_topic}"
        )

    def _handle_gz_image(self, msg: GzImage) -> None:
        width = int(msg.width)
        height = int(msg.height)
        step = int(msg.step)
        if width <= 0 or height <= 0 or step <= 0:
            return

        channels = step // width
        encoding = self._encoding_from_channels(channels)
        if encoding is None:
            if self._frame_count == 0:
                self.get_logger().warning(
                    f"Unsupported channel count from Gazebo image: channels={channels}"
                )
            return

        expected_size = height * step
        if len(msg.data) < expected_size:
            if self._frame_count == 0:
                self.get_logger().warning(
                    "Gazebo image buffer smaller than expected, skipping frame."
                )
            return

        ros_msg = Image()
        ros_msg.header.stamp = self.get_clock().now().to_msg()
        ros_msg.header.frame_id = "camera_link"
        ros_msg.height = height
        ros_msg.width = width
        ros_msg.encoding = encoding
        ros_msg.is_bigendian = False
        ros_msg.step = step
        ros_msg.data = bytes(msg.data[:expected_size])
        self._publisher.publish(ros_msg)

        self._frame_count += 1
        if self._frame_count == 1:
            self.get_logger().info(
                f"Published first ROS image frame: {width}x{height} encoding={encoding}"
            )

    def _encoding_from_channels(self, channels: int) -> str | None:
        if channels == self._RGB_CHANNELS:
            return "rgb8"
        if channels == self._RGBA_CHANNELS:
            return "rgba8"
        if channels == self._GRAY_CHANNELS:
            return "mono8"
        return None


def main() -> None:
    rclpy.init()
    node = GzCameraBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
