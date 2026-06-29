# 终端 B
source /opt/ros/jazzy/setup.bash
gz topic -l | grep camera
gz topic -e -t /world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image -n 1 | head -5# 终端 B
source /opt/ros/jazzy/setup.bash
gz topic -l | grep camera
gz topic -e -t /world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image -n 1 | head -5#!/usr/bin/env python3
"""Randomly spawn perception targets into a running Gazebo Harmonic world.

Usage (from a sourced ROS 2 + Gazebo environment):

    python3 sim/launch/spawn_targets.py \
        --world baylands \
        --config sim/configs/target_models.yaml \
        --seed 42

The script reads ``target_models.yaml``, draws a random population, and uses
the Gazebo Transport service ``/world/<world>/create`` (via the ``gz``
command-line tool) to spawn each model. A JSON manifest is written to
``sim/runtime/spawned_<timestamp>.json`` so the dataset collector knows the
ground-truth class of every spawned entity.

Design notes
------------
* No SDF file is modified; everything happens at runtime, so re-running the
  script produces a fresh randomisation without polluting world files.
* We rely on the ``gz`` CLI rather than ``ros_gz_sim create`` because Fuel
  URIs are resolved natively by Gazebo and we avoid an extra ROS dependency
  for what is effectively a sim-tooling script.
* Spawned model names follow ``<class>_<index>``; that name is the key the
  collector node uses to subscribe to ``/world/<world>/model/<name>/pose``.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SpawnedTarget:
    """Manifest record describing a single spawned model."""

    name: str
    class_id: int
    class_name: str
    fuel_uri: str
    pose_xyz: tuple[float, float, float]
    yaw: float
    aabb_size: tuple[float, float, float]


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _pick_population(rng: random.Random, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    pop = cfg["population"]
    total = rng.randint(int(pop["min_total"]), int(pop["max_total"]))
    weights = pop["class_weights"]
    classes_by_name = {c["name"]: c for c in cfg["classes"]}
    weighted_names = list(weights.keys())
    weighted_values = [float(weights[n]) for n in weighted_names]

    chosen: list[dict[str, Any]] = []
    for _ in range(total):
        name = rng.choices(weighted_names, weights=weighted_values, k=1)[0]
        chosen.append(classes_by_name[name])
    return chosen


def _sample_pose(
    rng: random.Random, klass: dict[str, Any], area: dict[str, Any]
) -> tuple[tuple[float, float, float], float]:
    x = rng.uniform(*area["x_range"])
    y = rng.uniform(*area["y_range"])
    base_z = float(area["water_z"] if klass["name"] == "boat" else area["ground_z"])
    z = base_z + float(klass.get("z_offset", 0.0))
    yaw = rng.uniform(0.0, 6.28318530718)
    return (x, y, z), yaw


def _build_create_request(
    world: str, name: str, fuel_uri: str, xyz: tuple[float, float, float], yaw: float
) -> str:
    """Build the textual ``ignition.msgs.EntityFactory`` request for ``gz service``."""

    x, y, z = xyz
    # Yaw-only rotation as a unit quaternion: q = (0, 0, sin(yaw/2), cos(yaw/2)).
    import math

    qz = math.sin(yaw / 2.0)
    qw = math.cos(yaw / 2.0)
    return (
        f'sdf_filename: "{fuel_uri}", '
        f'name: "{name}", '
        f"pose: {{ "
        f"position: {{ x: {x:.3f}, y: {y:.3f}, z: {z:.3f} }}, "
        f"orientation: {{ x: 0, y: 0, "
        f"z: {qz:.6f}, w: {qw:.6f} }}"
        f" }}"
    )


def _spawn_one(world: str, target: SpawnedTarget, dry_run: bool) -> bool:
    request = _build_create_request(
        world=world,
        name=target.name,
        fuel_uri=target.fuel_uri,
        xyz=target.pose_xyz,
        yaw=target.yaw,
    )
    cmd = [
        "gz",
        "service",
        "-s",
        f"/world/{world}/create",
        "--reqtype",
        "gz.msgs.EntityFactory",
        "--reptype",
        "gz.msgs.Boolean",
        "--timeout",
        "3000",
        "--req",
        request,
    ]
    if dry_run:
        print("[dry-run]", " ".join(cmd))
        return True

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        print("error: 'gz' CLI not found in PATH; source the Gazebo environment.")
        return False
    except subprocess.TimeoutExpired:
        print(f"warning: spawn of {target.name} timed out")
        return False

    ok = "data: true" in (result.stdout or "")
    if not ok:
        print(f"warning: spawn of {target.name} failed: {result.stdout!r} {result.stderr!r}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", default="baylands_2026cv")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "configs" / "target_models.yaml"),
    )
    parser.add_argument(
        "--manifest-dir",
        default=str(Path(__file__).resolve().parents[1] / "runtime"),
        help="Directory to write the spawned manifest JSON.",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--inter-spawn-delay",
        type=float,
        default=0.15,
        help="Seconds to wait between successive spawns to avoid overloading the service.",
    )
    args = parser.parse_args(argv)

    cfg_path = Path(args.config).resolve()
    if not cfg_path.is_file():
        print(f"error: config not found: {cfg_path}", file=sys.stderr)
        return 2
    cfg = _load_config(cfg_path)

    rng = random.Random(args.seed)
    population = _pick_population(rng, cfg)
    area = cfg["spawn_area"]

    spawned: list[SpawnedTarget] = []
    counts: dict[str, int] = {}
    for klass in population:
        idx = counts.get(klass["name"], 0)
        counts[klass["name"]] = idx + 1
        name = f"{klass['name']}_{idx}"
        fuel_uri = rng.choice(klass["fuel_uris"])
        xyz, yaw = _sample_pose(rng, klass, area)
        target = SpawnedTarget(
            name=name,
            class_id=int(klass["id"]),
            class_name=klass["name"],
            fuel_uri=fuel_uri,
            pose_xyz=xyz,
            yaw=yaw,
            aabb_size=tuple(klass["aabb_size"]),
        )
        if _spawn_one(args.world, target, dry_run=args.dry_run):
            spawned.append(target)
        time.sleep(args.inter_spawn_delay)

    manifest_dir = Path(args.manifest_dir).resolve()
    manifest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    manifest_path = manifest_dir / f"spawned_{stamp}.json"
    payload = {
        "world": args.world,
        "seed": args.seed,
        "config": str(cfg_path),
        "targets": [
            {
                "name": t.name,
                "class_id": t.class_id,
                "class_name": t.class_name,
                "fuel_uri": t.fuel_uri,
                "pose_xyz": list(t.pose_xyz),
                "yaw": t.yaw,
                "aabb_size": list(t.aabb_size),
            }
            for t in spawned
        ],
    }
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    # Convenience symlink/copy so collector_node can find the latest run.
    latest = manifest_dir / "spawned_latest.json"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        if os.name == "nt":
            shutil.copyfile(manifest_path, latest)
        else:
            os.symlink(manifest_path.name, latest)
    except OSError:
        shutil.copyfile(manifest_path, latest)

    print(f"spawned {len(spawned)}/{len(population)} targets")
    print(f"manifest: {manifest_path}")
    return 0 if spawned else 1


if __name__ == "__main__":
    raise SystemExit(main())
