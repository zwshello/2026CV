"""Render a human-readable Markdown report from the ROS 2 detection log.

Reads the JSONL written by ``yolo_detector`` and produces a concise summary
suitable for inclusion in the project report or presentation.

Usage::

    python vision/summarize_results.py \\
        --jsonl demo/ros2_outputs/detections.jsonl \\
        --output demo/ros2_outputs/report.md
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from collections import Counter
from typing import Iterable


def _iter_records(path: pathlib.Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return ordered[idx]


def _bar(value: float, max_value: float, width: int = 24) -> str:
    if max_value <= 0:
        return ""
    units = int(round(width * value / max_value))
    return "█" * units + "·" * (width - units)


def build_report(records: list[dict]) -> str:
    if not records:
        return "# 2026CV Detection Report\n\nNo records found.\n"

    frames = len(records)
    latencies = [float(r.get("latency_ms", 0.0)) for r in records if r.get("status") == "ok"]
    class_counts: Counter[str] = Counter()
    confidences: dict[str, list[float]] = {}
    detections_per_frame: list[int] = []
    for r in records:
        dets = r.get("detections", []) or []
        detections_per_frame.append(len(dets))
        for d in dets:
            label = str(d.get("label", "?"))
            class_counts[label] += 1
            confidences.setdefault(label, []).append(float(d.get("confidence", 0.0)))

    total_dets = sum(class_counts.values())
    avg_dets_per_frame = (sum(detections_per_frame) / frames) if frames else 0.0
    lat_avg = sum(latencies) / len(latencies) if latencies else 0.0
    lat_p95 = _percentile(latencies, 95.0)
    lat_p99 = _percentile(latencies, 99.0)
    lat_max = max(latencies) if latencies else 0.0

    out: list[str] = []
    out.append("# 2026CV Detection Report")
    out.append("")
    out.append("## Overview")
    out.append("")
    out.append(f"- Frames recorded: **{frames}**")
    out.append(f"- Total detections: **{total_dets}**")
    out.append(f"- Avg detections / frame: **{avg_dets_per_frame:.2f}**")
    out.append(f"- Inference latency (ms): avg **{lat_avg:.1f}**, p95 **{lat_p95:.1f}**, "
               f"p99 **{lat_p99:.1f}**, max **{lat_max:.1f}**")
    out.append("")

    out.append("## Class distribution")
    out.append("")
    if not class_counts:
        out.append("_No detections._")
    else:
        out.append("| Class | Count | Share | Avg conf | Bar |")
        out.append("|---|---:|---:|---:|---|")
        max_count = max(class_counts.values())
        for label, count in class_counts.most_common():
            confs = confidences.get(label, [])
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            share = (count / total_dets * 100.0) if total_dets else 0.0
            out.append(
                f"| {label} | {count} | {share:5.1f}% | {avg_conf:.2f} | `{_bar(count, max_count)}` |"
            )
    out.append("")

    out.append("## Latency histogram (ms)")
    out.append("")
    if not latencies:
        out.append("_No successful inferences._")
    else:
        bin_count = 10
        lo = min(latencies)
        hi = max(latencies)
        if math.isclose(lo, hi):
            hi = lo + 1.0
        step = (hi - lo) / bin_count
        bins = [0] * bin_count
        for v in latencies:
            idx = min(bin_count - 1, int((v - lo) / step))
            bins[idx] += 1
        max_bin = max(bins)
        out.append("| Range (ms) | Count | Bar |")
        out.append("|---|---:|---|")
        for i, c in enumerate(bins):
            edge_lo = lo + i * step
            edge_hi = lo + (i + 1) * step
            out.append(f"| {edge_lo:6.1f} – {edge_hi:6.1f} | {c} | `{_bar(c, max_bin)}` |")
    out.append("")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jsonl",
        default="demo/ros2_outputs/detections.jsonl",
        help="Path to the per-frame detection JSONL log.",
    )
    parser.add_argument(
        "--output",
        default="demo/ros2_outputs/report.md",
        help="Where to write the Markdown report.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    jsonl_path = pathlib.Path(args.jsonl)
    if not jsonl_path.exists():
        raise SystemExit(f"JSONL log not found: {jsonl_path}")
    records = list(_iter_records(jsonl_path))
    report = build_report(records)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote {output_path} ({len(records)} records)")


if __name__ == "__main__":
    main()
