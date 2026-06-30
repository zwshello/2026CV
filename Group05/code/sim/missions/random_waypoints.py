"""Random-waypoint mission for PX4 SITL via MAVSDK-Python.

This script makes the drone arm, take off, then visit a sequence of random
waypoints inside a configurable bounding box for a fixed duration. Its job
is to provide enough viewpoint diversity so the dataset collector can
record varied training frames.

Why MAVSDK rather than ``commander`` shell commands?
* MAVSDK is async-friendly, lets us check vehicle state, and gives a clean
  shutdown when the mission ends.
* No ROS dependency — this script can run from any Python env that has
  ``mavsdk`` installed (``pip install mavsdk``).

Usage (in a separate terminal once PX4 SITL is up)::

    python3 sim/missions/random_waypoints.py \\
        --duration 2400 --min-alt 30 --max-alt 80 \\
        --x-range -100 100 --y-range -100 100 --seed 7

The default duration of 40 minutes is chosen to roughly match the goal of
collecting 5000 frames at 2 Hz with ample margin for transitions.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import time
from dataclasses import dataclass

try:
    from mavsdk import System
    from mavsdk.offboard import OffboardError, PositionNedYaw
except ImportError as exc:  # pragma: no cover - mavsdk optional at lint time
    raise SystemExit(
        "mavsdk is required to run this mission. Install it inside your sim env: "
        "pip install mavsdk"
    ) from exc


@dataclass
class _Waypoint:
    north: float
    east: float
    down: float
    yaw_deg: float


def _sample_waypoint(rng: random.Random, args: argparse.Namespace) -> _Waypoint:
    north = rng.uniform(args.x_range[0], args.x_range[1])
    east = rng.uniform(args.y_range[0], args.y_range[1])
    altitude = rng.uniform(args.min_alt, args.max_alt)
    yaw = rng.uniform(0.0, 360.0)
    # PX4 NED: down is positive towards ground.
    return _Waypoint(north=north, east=east, down=-altitude, yaw_deg=yaw)


async def _run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    drone = System()
    print(f"Connecting to {args.connection} ...")
    await drone.connect(system_address=args.connection)

    print("Waiting for vehicle ...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("  connected")
            break

    print("Waiting for global position estimate ...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break

    print("Arming ...")
    await drone.action.set_takeoff_altitude(max(args.min_alt, 5.0))
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(8.0)

    print("Switching to offboard ...")
    await drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, -args.min_alt, 0.0))
    try:
        await drone.offboard.start()
    except OffboardError as err:
        print(f"Offboard start failed: {err}; aborting")
        await drone.action.land()
        return

    deadline = time.monotonic() + args.duration
    visited = 0
    try:
        while time.monotonic() < deadline:
            wp = _sample_waypoint(rng, args)
            await drone.offboard.set_position_ned(
                PositionNedYaw(wp.north, wp.east, wp.down, wp.yaw_deg)
            )
            visited += 1
            print(
                f"  WP {visited}: N={wp.north:+.1f} E={wp.east:+.1f} "
                f"alt={-wp.down:.1f} yaw={wp.yaw_deg:.0f}"
            )
            # Dwell time scales with horizontal distance so we usually arrive
            # before the next waypoint is commanded.
            distance_guess = math.hypot(wp.north, wp.east) * 0.05 + 4.0
            await asyncio.sleep(min(distance_guess, args.max_dwell))
    finally:
        print("Mission done — landing")
        try:
            await drone.offboard.stop()
        except OffboardError:
            pass
        await drone.action.land()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--connection", default="udp://:14540")
    p.add_argument("--duration", type=float, default=2400.0, help="Total mission seconds.")
    p.add_argument("--min-alt", type=float, default=30.0)
    p.add_argument("--max-alt", type=float, default=80.0)
    p.add_argument("--x-range", type=float, nargs=2, default=[-100.0, 100.0])
    p.add_argument("--y-range", type=float, nargs=2, default=[-100.0, 100.0])
    p.add_argument(
        "--max-dwell",
        type=float,
        default=12.0,
        help="Cap per-waypoint hold time (seconds).",
    )
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
