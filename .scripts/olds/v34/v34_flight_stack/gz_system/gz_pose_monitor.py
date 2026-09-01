"""Live Gazebo pose cache for the gz backend.

WHY THIS EXISTS (F2, 2026-08-17). Release used to be fire-and-forget: the
actuator published a detach message and immediately reported success. The
ADR-011 acceptance flight showed what that hides -- payload 2 was still
attached 2 s after the servo (z=0.523, exactly base_link minus the 0.18 m
mount offset) and only separated during the climb-out, landing 4.9 m past
the triangle. Nothing in the log said so, because nothing was watching.

Confirming a release needs the payload's pose at ~20 Hz. Sampling it with
one `gz topic -e -n 1` per poll costs ~2 s of gz-transport discovery EACH
(measured), which is two orders of magnitude too slow. So one subscriber is
started once, early, and streams into a cache that any number of callers
read for free. Paying discovery once, at mission start, is also what makes
the detach publish itself prompt.

Read-only and best-effort by construction: every failure path leaves the
cache empty and callers get None. A pose observation must never be able to
break a flight.
"""
import asyncio
import logging
import os
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

Pose = Tuple[float, float, float]
Quat = Tuple[float, float, float, float]


def _rotate(q: Quat, v: Pose) -> Pose:
    """Rotate vector v by quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def _quat_mul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


class GzPoseMonitor:
    """Streams /world/<world>/dynamic_pose/info into an in-memory cache.

    NOTE ON COVERAGE: dynamic_pose/info only carries entities whose pose
    CHANGED this step. A body that has come to rest stops being published,
    so `get()` returns the last pose seen, not a live one -- which is
    exactly right for "where did the payload settle", and is why `age_s`
    is exposed rather than hidden.
    """

    def __init__(self, world_name: str = None):
        """world_name defaults to the world PX4 actually launched.

        WHY NOT THE LITERAL "default" (2026-08-27): PX4 selects the world via
        PX4_GZ_WORLD (ROMFS 4001_gz_x500 defaults it; px4-rc.gzsim uses it as
        BOTH the SDF filename stem and the gz-transport world name). With the
        literal, launching any other world -- the competition_day /
        competition_overcast variants, say -- left this subscribed to
        /world/default/dynamic_pose/info, which nobody publishes. Every
        payload and hook pose would silently go missing and the seating gate
        could never validate, with no error anywhere.
        """
        self.world_name = world_name or os.environ.get("PX4_GZ_WORLD", "default")
        self._poses: Dict[str, Pose] = {}
        self._quats: Dict[str, Quat] = {}
        self._stamps: Dict[str, float] = {}
        self._proc = None
        self._task = None

    async def start(self) -> bool:
        if self._proc is not None:
            return True
        topic = f"/world/{self.world_name}/dynamic_pose/info"
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "gz", "topic", "-e", "-t", topic,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            logger.warning("Gazebo poz izleyicisi baslatilamadi: %s", e)
            self._proc = None
            return False
        self._task = asyncio.create_task(self._read_loop())
        logger.info("Gazebo poz izleyicisi basladi: %s", topic)
        return True

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
            self._proc = None

    async def _read_loop(self) -> None:
        """Parses the protobuf text stream a line at a time.

        Pose_V nests exactly two message blocks inside each `pose`
        (position and orientation), so tracking which of the two is open is
        enough -- no general brace-depth parser is needed."""
        assert self._proc is not None and self._proc.stdout is not None
        name = None
        section = None
        pos: Dict[str, float] = {}
        ori: Dict[str, float] = {}
        while True:
            try:
                raw = await self._proc.stdout.readline()
            except Exception:  # noqa: BLE001
                return
            if not raw:
                return
            line = raw.decode(errors="replace").strip()
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
                pos, ori, section = {}, {}, None
            elif line.startswith("position"):
                section = "pos"
            elif line.startswith("orientation"):
                section = "ori"
            elif line == "}":
                section = None
            elif section and ":" in line:
                key, _, value = line.partition(":")
                try:
                    val = float(value)
                except ValueError:
                    continue
                (pos if section == "pos" else ori)[key.strip()] = val
                # A quaternion's w is the last field of the last block, so
                # its arrival is the reliable "this entry is complete" mark.
                if section == "ori" and key.strip() == "w" and name and len(pos) == 3:
                    self._poses[name] = (pos["x"], pos["y"], pos["z"])
                    self._quats[name] = (ori.get("x", 0.0), ori.get("y", 0.0),
                                         ori.get("z", 0.0), ori["w"])
                    self._stamps[name] = time.time()
                    name = None

    def link_world_pose(self, model_name: str, link_name: str):
        """WORLD pose of a LINK, composed from its model's world pose.

        WHY THIS EXISTS: /world/<w>/dynamic_pose/info reports MODEL poses in
        the world frame but LINK poses relative to their model. The hook
        hangs on a four-segment rope, so hook_body_link's model-frame pose
        moves continuously -- which is exactly the information the pickup
        gate needs and exactly what a "vehicle pose + fixed body offset"
        estimate throws away (measured error up to 19.86 cm in transport).

        Returns (position, quaternion, age_s) or None when either half of
        the pair is missing. `age_s` is the age of the STALER of the two
        samples, so a caller that gates on freshness cannot be fooled by a
        fresh model pose paired with a frozen link pose.
        """
        mp = self._poses.get(model_name)
        mq = self._quats.get(model_name)
        lp = self._poses.get(link_name)
        lq = self._quats.get(link_name)
        if mp is None or mq is None or lp is None or lq is None:
            return None

        wp = _rotate(mq, lp)
        pos = (mp[0] + wp[0], mp[1] + wp[1], mp[2] + wp[2])
        quat = _quat_mul(mq, lq)

        now = time.time()
        age = max(now - self._stamps.get(model_name, now),
                  now - self._stamps.get(link_name, now))
        return pos, quat, age

    def get(self, name: str) -> Optional[Pose]:
        return self._poses.get(name)

    def get_quat(self, name: str) -> Optional[Quat]:
        return self._quats.get(name)

    def age_s(self, name: str) -> Optional[float]:
        stamp = self._stamps.get(name)
        return None if stamp is None else time.time() - stamp

    def seen(self, name: str) -> bool:
        return name in self._poses
