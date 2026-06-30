"""HUD overlay drawing for the annotated camera stream."""

from __future__ import annotations

from typing import Any

from low_altitude_bringup.metrics import PerceptionMetrics

try:
    from PIL import Image as PilImage
    from PIL import ImageDraw, ImageFont
except Exception:  # pragma: no cover
    PilImage = None
    ImageDraw = None
    ImageFont = None


def load_default_font() -> Any:
    if ImageFont is None:
        return None
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def render_annotated_rgb(
    rgb: Any,
    detections: list[dict[str, Any]],
    *,
    metrics: PerceptionMetrics,
    model_ready: bool,
    font: Any = None,
    enable_hud: bool = True,
) -> Any:
    """Return a PIL image with detection boxes and (optionally) a HUD overlay.

    Falls back to the raw RGB array when Pillow is not available.
    """
    if PilImage is None or ImageDraw is None:
        return rgb

    image = PilImage.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox_xyxy"]
        label = f"{detection['label']} {detection['confidence']:.2f}"
        draw.rectangle((x1, y1, x2, y2), outline=(255, 0, 0), width=3)
        draw.text((x1 + 4, max(y1 - 20, 4)), label, fill=(255, 255, 0), font=font)

    if enable_hud:
        _draw_hud(image, draw, detections, metrics=metrics, model_ready=model_ready, font=font)

    return image


def _draw_hud(
    image: Any,
    draw: Any,
    detections: list[dict[str, Any]],
    *,
    metrics: PerceptionMetrics,
    model_ready: bool,
    font: Any,
) -> None:
    badge_text, badge_color = metrics.badge(model_ready)

    lines = [
        f"FPS in:  {metrics.input_fps():5.2f}",
        f"FPS det: {metrics.detection_fps():5.2f}",
        f"lat avg: {metrics.latency_avg_ms():5.1f} ms",
        f"frames:  {metrics.frame_count}",
        f"dets:    {len(detections)}",
    ]
    line_h = 14
    block_w = 170
    block_h = line_h * len(lines) + 8
    draw.rectangle((6, 6, 6 + block_w, 6 + block_h), fill=(0, 0, 0, 140))
    for i, line in enumerate(lines):
        draw.text((12, 10 + i * line_h), line, fill=(240, 240, 240), font=font)

    badge_w, badge_h = 80, 26
    bx0 = image.width - badge_w - 6
    by0 = 6
    draw.rectangle(
        (bx0, by0, bx0 + badge_w, by0 + badge_h),
        fill=(*badge_color, 200),
        outline=(255, 255, 255, 220),
    )
    draw.text((bx0 + 8, by0 + 6), badge_text, fill=(0, 0, 0), font=font)

    if detections:
        top3 = sorted(
            detections,
            key=lambda d: float(d.get("confidence", 0.0)),
            reverse=True,
        )[:3]
        text = "  ".join(
            f"{d.get('label','?')} {float(d.get('confidence',0.0)):.2f}" for d in top3
        )
        tw = min(image.width - 12, max(block_w, 8 + len(text) * 7))
        ty = image.height - 28
        draw.rectangle((6, ty, 6 + tw, ty + 22), fill=(0, 0, 0, 140))
        draw.text((12, ty + 4), text, fill=(240, 240, 240), font=font)
