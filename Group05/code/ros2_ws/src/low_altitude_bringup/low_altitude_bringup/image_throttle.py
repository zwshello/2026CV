"""Latest-only image relay node (a.k.a. 中间缓冲区).

The Gazebo -> ros_gz_bridge image stream can far exceed downstream YOLO
inference throughput, which causes the unprocessed frames to accumulate in
host RAM (gz transport queues, DDS sub queues, Python references...).  This
node terminates that pipeline by holding *exactly one* frame in memory:

* incoming frame -> overwrite ``self._latest`` (no list, no append)
* timer at ``republish_hz`` -> publish whatever ``self._latest`` currently is

Thus RAM usage is mathematically O(1) regardless of source rate.

Optionally resize the frame to ``resize_width`` x ``resize_height`` before
republishing to also cut downstream byte-rate.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy, QoSDurabilityPolicy
from sensor_msgs.msg import Image


def _sensor_qos(depth: int = 1) -> QoSProfile:
    """best_effort + keep_last + depth=1 (drop-old single-slot)."""
    return QoSProfile(
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=depth,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


def _reliable_qos(depth: int = 1) -> QoSProfile:
    """reliable + keep_last + depth=1.

    Used for the *input* subscription: ros_gz_bridge publishes images with
    reliable QoS by default, and a strict-matching DDS pair (best_effort sub
    against reliable pub) can silently fail to connect in some ROS 2 builds.
    We therefore subscribe reliable here while still keeping memory bounded
    via depth=1 (drop-old at queue level).
    """
    return QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=depth,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


class ImageThrottle(Node):
    def __init__(self) -> None:
        super().__init__("image_throttle")

        self.declare_parameter("input_topic", "/camera/image_raw")
        self.declare_parameter("output_topic", "/camera/image_throttled")
        self.declare_parameter("republish_hz", 5.0)
        # 0 means "do not resize, pass-through original dims".
        self.declare_parameter("resize_width", 0)
        self.declare_parameter("resize_height", 0)
        self.declare_parameter("log_every_n_publish", 50)

        self._input_topic = self.get_parameter("input_topic").get_parameter_value().string_value
        self._output_topic = self.get_parameter("output_topic").get_parameter_value().string_value
        self._republish_hz = float(self.get_parameter("republish_hz").value)
        self._resize_w = int(self.get_parameter("resize_width").value)
        self._resize_h = int(self.get_parameter("resize_height").value)
        self._log_every = max(1, int(self.get_parameter("log_every_n_publish").value))

        if self._republish_hz <= 0:
            self._republish_hz = 5.0

        self._latest: Optional[Image] = None
        self._rx_count = 0
        self._tx_count = 0
        self._drop_count = 0  # frames overwritten before being republished

        self._sub = self.create_subscription(
            Image, self._input_topic, self._on_image, _reliable_qos(depth=1)
        )
        self._pub = self.create_publisher(Image, self._output_topic, _sensor_qos(depth=1))
        self._timer = self.create_timer(1.0 / self._republish_hz, self._on_timer)

        # cv2 only required when resizing.
        self._cv2 = None
        if self._resize_w > 0 and self._resize_h > 0:
            try:
                import cv2  # type: ignore
                self._cv2 = cv2
            except Exception as exc:  # pragma: no cover
                self.get_logger().warn(
                    f"resize requested ({self._resize_w}x{self._resize_h}) but cv2 unavailable: {exc}; passthrough"
                )
                self._resize_w = 0
                self._resize_h = 0

        self.get_logger().info(
            f"image_throttle: {self._input_topic} -> {self._output_topic} "
            f"@ {self._republish_hz:.2f} Hz, resize={self._resize_w}x{self._resize_h} "
            f"(0=passthrough)"
        )

    # ------------------------------------------------------------------
    def _on_image(self, msg: Image) -> None:
        if self._rx_count == 0:
            self.get_logger().info(
                f"image_throttle: got FIRST frame {msg.width}x{msg.height} {msg.encoding}"
            )
        if self._latest is not None:
            # Old frame got overwritten without being republished -> dropped.
            self._drop_count += 1
        self._latest = msg
        self._rx_count += 1

    def _on_timer(self) -> None:
        msg = self._latest
        if msg is None:
            return

        if self._resize_w > 0 and self._resize_h > 0 and self._cv2 is not None:
            msg = self._resize_message(msg)
            if msg is None:
                return

        self._pub.publish(msg)
        self._tx_count += 1

        if self._tx_count % self._log_every == 0:
            self.get_logger().info(
                f"throttle stats: rx={self._rx_count} tx={self._tx_count} "
                f"dropped={self._drop_count} "
                f"(latest {msg.width}x{msg.height} {msg.encoding})"
            )

    # ------------------------------------------------------------------
    def _resize_message(self, msg: Image) -> Optional[Image]:
        cv2 = self._cv2
        enc = (msg.encoding or "").lower()
        # Only handle the common cases used by gz_camera_bridge.
        if enc in ("rgb8", "bgr8"):
            channels = 3
            dtype = np.uint8
        elif enc == "mono8":
            channels = 1
            dtype = np.uint8
        else:
            # Unknown encoding -> bail out, publish original.
            return msg

        try:
            buf = np.frombuffer(msg.data, dtype=dtype)
            if channels == 1:
                frame = buf.reshape(msg.height, msg.width)
            else:
                frame = buf.reshape(msg.height, msg.width, channels)
            resized = cv2.resize(
                frame, (self._resize_w, self._resize_h), interpolation=cv2.INTER_AREA
            )
        except Exception as exc:  # pragma: no cover
            self.get_logger().warn_once(f"resize failed, passing through: {exc}")
            return msg

        out = Image()
        out.header = msg.header
        out.height = self._resize_h
        out.width = self._resize_w
        out.encoding = msg.encoding
        out.is_bigendian = msg.is_bigendian
        out.step = self._resize_w * channels
        out.data = resized.tobytes()
        return out


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ImageThrottle()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
