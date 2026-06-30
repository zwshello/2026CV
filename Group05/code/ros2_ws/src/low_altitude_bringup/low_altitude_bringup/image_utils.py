from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sensor_msgs.msg import Image


@dataclass(frozen=True)
class ImageFrame:
    width: int
    height: int
    encoding: str
    rgb: np.ndarray


def image_message_to_rgb(msg: Image) -> ImageFrame:
    width = int(msg.width)
    height = int(msg.height)
    step = int(msg.step)
    encoding = (msg.encoding or "").lower()
    raw = np.frombuffer(msg.data, dtype=np.uint8)

    if width <= 0 or height <= 0 or step <= 0:
        raise ValueError("invalid image shape")

    expected = height * step
    if raw.size < expected:
        raise ValueError("image buffer is smaller than expected")

    raw = raw[:expected]

    if encoding in ("rgb8", "bgr8"):
        frame = raw.reshape((height, width, 3))
        rgb = frame if encoding == "rgb8" else frame[:, :, ::-1]
    elif encoding in ("rgba8", "bgra8"):
        frame = raw.reshape((height, width, 4))
        rgb = frame[:, :, :3] if encoding == "rgba8" else frame[:, :, [2, 1, 0]]
    elif encoding == "mono8":
        frame = raw.reshape((height, width))
        rgb = np.repeat(frame[:, :, None], 3, axis=2)
    else:
        raise ValueError(f"unsupported image encoding: {msg.encoding!r}")

    return ImageFrame(width=width, height=height, encoding=encoding, rgb=rgb.copy())


def image_frame_to_ppm(frame: ImageFrame) -> bytes:
    header = f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii")
    return header + frame.rgb.tobytes()


def rgb_to_image_message(
    rgb: np.ndarray,
    *,
    frame_id: str = "camera_link",
    stamp: object | None = None,
) -> Image:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb array must have shape (height, width, 3)")

    height, width, _ = rgb.shape
    msg = Image()
    if stamp is not None:
        msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = int(height)
    msg.width = int(width)
    msg.encoding = "rgb8"
    msg.is_bigendian = False
    msg.step = int(width * 3)
    msg.data = rgb.astype(np.uint8, copy=False).tobytes()
    return msg
