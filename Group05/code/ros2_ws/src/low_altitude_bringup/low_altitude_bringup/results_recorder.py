"""Persist detection results as JSONL + periodic summary JSON.

This produces presentable "experiment artifact" files for the project report.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from low_altitude_bringup.metrics import PerceptionMetrics


class ResultsRecorder:
    """Append per-frame detection JSONL records and a rolling summary file."""

    def __init__(
        self,
        output_dir: pathlib.Path,
        *,
        jsonl_name: str = "detections.jsonl",
        summary_name: str = "summary.json",
        summary_interval_sec: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._output_dir = pathlib.Path(output_dir)
        self._summary_interval_sec = max(1.0, float(summary_interval_sec))
        self._jsonl_path = self._output_dir / jsonl_name
        self._summary_path = self._output_dir / summary_name
        self._last_summary_wall = 0.0

        if not self._enabled:
            return

        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            # Truncate previous run so each invocation has its own log.
            self._jsonl_path.write_text("", encoding="utf-8")
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def jsonl_path(self) -> pathlib.Path:
        return self._jsonl_path

    @property
    def summary_path(self) -> pathlib.Path:
        return self._summary_path

    def append_frame(self, record: dict[str, Any]) -> None:
        if not self._enabled:
            return
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=True))
                fh.write("\n")
        except Exception:
            # Disable on first failure to avoid noisy callbacks.
            self._enabled = False

    def maybe_write_summary(
        self,
        metrics: PerceptionMetrics,
        *,
        model_ready: bool,
        model_path: str | None,
        force: bool = False,
    ) -> bool:
        if not self._enabled:
            return False
        now = time.time()
        if not force and (now - self._last_summary_wall) < self._summary_interval_sec:
            return False
        self._last_summary_wall = now

        last_age = metrics.last_image_age(now)
        badge_text, _ = metrics.badge(model_ready)
        payload = {
            "updated_at": round(now, 3),
            "uptime_sec": round(now - metrics.started_wall, 3),
            "status": badge_text,
            "model_path": model_path,
            "model_ready": model_ready,
            "frames": metrics.frame_count,
            "inference_failures": metrics.inference_failures,
            "input_fps": round(metrics.input_fps(), 3),
            "detection_fps": round(metrics.detection_fps(), 3),
            "latency_avg_ms": round(metrics.latency_avg_ms(), 3),
            "latency_p95_ms": round(metrics.latency_p95_ms(), 3),
            "last_image_age_sec": None if last_age is None else round(last_age, 3),
            "class_totals": dict(metrics.class_totals.most_common()),
        }
        try:
            tmp_path = self._summary_path.with_suffix(self._summary_path.suffix + ".tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
            )
            tmp_path.replace(self._summary_path)
        except Exception:
            self._enabled = False
            return False
        return True
