"""Lightweight runtime-metric helpers for the perception node.

Keeps fps/latency/percentile bookkeeping out of the main ROS node so the
detector file can stay focused on ROS plumbing and inference.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque


def fps_from_window(window: Deque[float]) -> float:
    if len(window) < 2:
        return 0.0
    span = window[-1] - window[0]
    if span <= 0.0:
        return 0.0
    return (len(window) - 1) / span


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return ordered[idx]


@dataclass
class PerceptionMetrics:
    """Rolling window stats for the perception pipeline."""

    window_size: int = 30
    input_times: Deque[float] = field(init=False)
    inference_times: Deque[float] = field(init=False)
    latencies_ms: Deque[float] = field(init=False)
    class_totals: Counter[str] = field(default_factory=Counter)
    last_detections: list[dict] = field(default_factory=list)
    last_image_wall_time: float | None = None
    last_status: str = "waiting"
    inference_failures: int = 0
    frame_count: int = 0
    started_wall: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        size = max(5, int(self.window_size))
        self.input_times = deque(maxlen=size)
        self.inference_times = deque(maxlen=size)
        self.latencies_ms = deque(maxlen=size)

    def mark_input(self, now: float | None = None) -> float:
        ts = now if now is not None else time.time()
        self.last_image_wall_time = ts
        self.input_times.append(ts)
        self.frame_count += 1
        return ts

    def mark_inference(self, latency_ms: float, detections: list[dict]) -> None:
        self.last_status = "ok"
        self.inference_times.append(time.time())
        self.latencies_ms.append(float(latency_ms))
        self.last_detections = detections
        for d in detections:
            self.class_totals[str(d.get("label", "?"))] += 1

    def mark_failure(self) -> None:
        self.last_status = "inference_failed"
        self.inference_failures += 1

    def mark_model_unavailable(self) -> None:
        self.last_status = "model_unavailable"

    def input_fps(self) -> float:
        return fps_from_window(self.input_times)

    def detection_fps(self) -> float:
        return fps_from_window(self.inference_times)

    def latency_avg_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    def latency_p95_ms(self) -> float:
        return percentile(list(self.latencies_ms), 95.0)

    def last_image_age(self, now: float | None = None) -> float | None:
        if self.last_image_wall_time is None:
            return None
        ts = now if now is not None else time.time()
        return max(0.0, ts - self.last_image_wall_time)

    def badge(self, model_ready: bool) -> tuple[str, tuple[int, int, int]]:
        last_age = self.last_image_age()
        if not model_ready:
            return ("FAIL", (220, 60, 60))
        if last_age is None or last_age > 3.0:
            return ("STALE", (230, 200, 60))
        if self.last_status == "ok":
            return ("READY", (60, 200, 90))
        if self.last_status == "inference_failed":
            return ("FAIL", (220, 60, 60))
        return ("WAIT", (230, 200, 60))
