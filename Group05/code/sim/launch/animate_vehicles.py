#!/usr/bin/env python3
"""Animate vehicles along road patrol routes in Gazebo Harmonic.

Vehicles follow linear back-and-forth routes on two intersecting roads:
  - East-West road  at y ≈ ±1.5 m  (two lanes)
  - North-South road at x ≈ ±1.5 m  (two lanes)

Usage:
    python3 sim/launch/animate_vehicles.py --world baylands_2026cv --duration 600
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LinearRoute:
    """A straight road segment; vehicles patrol back-and-forth."""

    x1: float
    y1: float
    x2: float
    y2: float
    speed_ms: float  # cruise speed (m/s)
    t0: float = 0.0  # initial position along route [0, 1]

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def base_yaw(self) -> float:
        return math.atan2(self.y2 - self.y1, self.x2 - self.x1)


def _set_pose(world: str, name: str, x: float, y: float, z: float, yaw: float) -> bool:
    qz = math.sin(yaw / 2.0)
    qw = math.cos(yaw / 2.0)
    req = (
        f'name: "{name}", '
        f"position: {{ x: {x:.3f}, y: {y:.3f}, z: {z:.3f} }}, "
        f"orientation: {{ x: 0, y: 0, z: {qz:.6f}, w: {qw:.6f} }}"
    )
    cmd = [
        "gz", "service",
        "-s", f"/world/{world}/set_pose",
        "--reqtype", "gz.msgs.Pose",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "1000",
        "--req", req,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return "data: true" in (r.stdout or "")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", default="baylands_2026cv")
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--dt", type=float, default=0.5, help="Update interval (s)")
    args = parser.parse_args(argv)

    # Only animate car_3, car_5 — others stay put.
    # Route direction derived from SDF initial yaw (read from pose/info topic):
    #   car_3 at (2.82, -6.28)  yaw=2.007 rad (~114°) → patrol ±35 m along road
    #   car_5 at (-12.09, 24.62) yaw=1.993 rad (~114°) → patrol ±30 m along road
    # Endpoints computed as: p = center ± dist × (cos(yaw), sin(yaw))
    routes: dict[str, LinearRoute] = {
        "car_3": LinearRoute(x1=18.0, y1=-37.8, x2=-12.4, y2=25.2,  speed_ms=7, t0=0.6),
        "car_5": LinearRoute(x1=0.4,  y1=-2.7,  x2=-24.5, y2=51.9,  speed_ms=6, t0=0.4),
    }

    # Mutable per-vehicle state
    t_pos = {name: r.t0 for name, r in routes.items()}
    fwd   = {name: True for name in routes}

    print(f"[animate_vehicles] {len(routes)} vehicles on road grid, world={args.world}")

    start = time.time()
    first_fail_warned = False

    try:
        while True:
            elapsed = time.time() - start
            if args.duration > 0 and elapsed > args.duration:
                print(f"[animate_vehicles] Done after {elapsed:.0f}s.")
                break

            for name, route in routes.items():
                dt_t = route.speed_ms * args.dt / route.length

                if fwd[name]:
                    t_pos[name] = min(1.0, t_pos[name] + dt_t)
                    if t_pos[name] >= 1.0:
                        fwd[name] = False
                else:
                    t_pos[name] = max(0.0, t_pos[name] - dt_t)
                    if t_pos[name] <= 0.0:
                        fwd[name] = True

                t = t_pos[name]
                x = route.x1 + t * (route.x2 - route.x1)
                y = route.y1 + t * (route.y2 - route.y1)
                yaw = route.base_yaw if fwd[name] else route.base_yaw + math.pi

                ok = _set_pose(args.world, name, x, y, 0.05, yaw)
                if not ok and elapsed > 3 and not first_fail_warned:
                    print(f"[animate_vehicles] WARN: set_pose failed for {name}")
                    first_fail_warned = True

            time.sleep(args.dt)

    except KeyboardInterrupt:
        print("\n[animate_vehicles] Stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
