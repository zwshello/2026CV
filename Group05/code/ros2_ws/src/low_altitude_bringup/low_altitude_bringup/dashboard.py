"""Terminal dashboard rendering (rich-based with plain-text fallback)."""

from __future__ import annotations

from typing import Any

from low_altitude_bringup.metrics import PerceptionMetrics

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except Exception:  # pragma: no cover
    Console = None  # type: ignore[assignment]
    Live = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]


_BADGE_COLORS = {"READY": "green", "WAIT": "yellow", "STALE": "yellow", "FAIL": "red"}


def rich_available() -> bool:
    return Live is not None


def make_console() -> Any:
    return Console() if Console is not None else None


def make_live(console: Any, refresh_hz: float, renderable: Any) -> Any:
    if Live is None:
        return None
    return Live(
        renderable,
        console=console,
        refresh_per_second=max(0.5, float(refresh_hz)),
        screen=False,
        transient=False,
    )


def render_panel(metrics: PerceptionMetrics, *, model_ready: bool) -> Any:
    badge_text, _ = metrics.badge(model_ready)
    color = _BADGE_COLORS.get(badge_text, "white")
    last_age = metrics.last_image_age()

    header = Table.grid(expand=True)
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        Text("2026CV — Real-time Detection", style="bold cyan"),
        Text(f"[{badge_text}]", style=f"bold {color}"),
    )

    metrics_tbl = Table(expand=True, show_header=True, header_style="bold magenta")
    metrics_tbl.add_column("Metric")
    metrics_tbl.add_column("Value", justify="right")
    metrics_tbl.add_row("Input FPS", f"{metrics.input_fps():.2f}")
    metrics_tbl.add_row("Detection FPS", f"{metrics.detection_fps():.2f}")
    metrics_tbl.add_row("Latency avg (ms)", f"{metrics.latency_avg_ms():.1f}")
    metrics_tbl.add_row("Latency p95 (ms)", f"{metrics.latency_p95_ms():.1f}")
    metrics_tbl.add_row("Frames", str(metrics.frame_count))
    metrics_tbl.add_row("Inference failures", str(metrics.inference_failures))
    metrics_tbl.add_row(
        "Last image age (s)", "—" if last_age is None else f"{last_age:.2f}"
    )

    latest = Table(expand=True, show_header=True, header_style="bold magenta")
    latest.add_column("Label")
    latest.add_column("Conf", justify="right")
    if not metrics.last_detections:
        latest.add_row("(none)", "—")
    else:
        for d in metrics.last_detections[:6]:
            latest.add_row(
                str(d.get("label", "?")),
                f"{float(d.get('confidence', 0.0)):.2f}",
            )

    totals = Table(expand=True, show_header=True, header_style="bold magenta")
    totals.add_column("Top class")
    totals.add_column("Count", justify="right")
    if not metrics.class_totals:
        totals.add_row("(none)", "—")
    else:
        for label, count in metrics.class_totals.most_common(5):
            totals.add_row(label, str(count))

    body = Table.grid(expand=True)
    body.add_column(ratio=2)
    body.add_column(ratio=1)
    body.add_column(ratio=1)
    body.add_row(metrics_tbl, latest, totals)

    outer = Table.grid(expand=True)
    outer.add_column()
    outer.add_row(header)
    outer.add_row(body)
    return Panel(outer, border_style=color, title="2026CV Perception")


def plain_summary_line(metrics: PerceptionMetrics, *, model_ready: bool) -> str:
    badge_text, _ = metrics.badge(model_ready)
    last_age = metrics.last_image_age()
    age_text = "-" if last_age is None else f"{last_age:.2f}"
    return (
        f"[{badge_text}] in_fps={metrics.input_fps():.2f} "
        f"det_fps={metrics.detection_fps():.2f} "
        f"lat={metrics.latency_avg_ms():.1f}ms "
        f"frames={metrics.frame_count} "
        f"fails={metrics.inference_failures} img_age={age_text}"
    )
