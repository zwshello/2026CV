"""Thin wrapper around ``ultralytics.YOLO.train`` for the sim dataset.

Defaults match the design we agreed on for an RTX 4050 Laptop (6 GB VRAM):

* model:   yolov8s.pt  (good speed/accuracy trade-off at 640)
* imgsz:   640
* batch:   16  (AMP on; fits in ~5 GB)
* epochs:  50
* mosaic:  1.0, mixup: 0.1  (helps simulated → real generalisation)

The script is intentionally minimal — Ultralytics already provides logging,
checkpointing, and validation. We just lock the defaults so re-running gives
reproducible artifacts under ``runs/sim/<run_name>``.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, help="Path to dataset.yaml")
    p.add_argument("--model", default="yolov8s.pt")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--device", default="0", help="CUDA device id, or 'cpu'.")
    p.add_argument("--project", default=str(Path("runs") / "sim"))
    p.add_argument("--name", default="v1")
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--mosaic", type=float, default=1.0)
    p.add_argument("--mixup", type=float, default=0.1)
    p.add_argument("--lr0", type=float, default=0.001)
    p.add_argument("--no-amp", action="store_true")
    args = p.parse_args()

    # Imported lazily so that --help works even before the heavy deps
    # are installed.
    from ultralytics import YOLO  # type: ignore

    model = YOLO(args.model)
    model.train(
        data=args.data,
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        patience=args.patience,
        mosaic=args.mosaic,
        mixup=args.mixup,
        lr0=args.lr0,
        amp=not args.no_amp,
        optimizer="AdamW",
        verbose=True,
    )

    weights = Path(args.project) / args.name / "weights" / "best.pt"
    print(f"Training finished. Best weights: {weights}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
