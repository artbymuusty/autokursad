"""Placing a CARRIED payload on a visually-detected destination.

WHY THIS EXISTS
---------------
Görev 3's redrop already centres on the destination with vision -- but it
centres the VEHICLE. The load does not hang under the vehicle origin: it is
locked to the hook, which sits at body (-0.090, 0) plus whatever the rope is
doing. So a perfectly centred aircraft still drops the payload about 9 cm
off, plus swing. That is the same class of error the pickup work removed, and
it is removed the same way here: align the thing that is actually being
placed, not the airframe.

WHERE THE TWO NUMBERS COME FROM, and the distinction that matters:

    destination  <- from the CAMERA (the mission's own shape detections)
    carried load <- from the hook pose

The load is welded to the hook by the lock, so the hook's position IS the
load's position; there is no separate measurement to make. The hook pose is
the same simulated mechanical sensor the seating gate already trusts, and
using it here is deliberate rather than a shortcut -- see the fallback note
on carried_payload_ned_offset().

WHY NOT DETECT THE CARRIED LOAD IN THE IMAGE. It is a red rectangle, and in
Görev 3 it is being placed on a RED triangle, so the two are the same hue and
separable only by size and shape. Worse, at the 0.30 m release altitude the
load hangs close to the camera and is the nearest object in frame, so it
partially occludes the very target it is being aligned to. The hook pose is
both more accurate and unambiguous. If a future build needs a vision-only
answer -- a real aircraft with no hook encoder -- the load is detectable at
higher altitudes where it does not overlap the target, and that is the
documented fallback rather than something pretended here.
"""
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.config.parameters import CAMERA_LEVER_ARM_BODY_M
from core.detection.camera_intrinsics import default_camera_intrinsics
from core.mission.visual_alignment import (
    CAMERA_Z_ABOVE_MODEL_ORIGIN_M, body_to_ned,
)

logger = logging.getLogger(__name__)

# The arena markers are painted ON the ground, not on a raised deck: the
# hexagon and triangle models sit at world z = 0.003. So the depth to them is
# the camera's own height, unlike the receiver which is 0.070 m up.
MARKER_HEIGHT_M: float = 0.003

# Accept a placement at 5 cm. The measured drop scatter of the uncorrected
# system was 13-34 cm, dominated by the mount arm; 5 cm is well inside that
# and is about the payload's own short side (0.052 m), i.e. tightening
# further would be asserting precision the release itself does not have --
# the payload still falls, tumbles slightly and settles.
PLACE_TOLERANCE_M: float = 0.05
PLACE_KP: float = 0.6
PLACE_MAX_STEP_M: float = 0.10
PLACE_DEADBAND_M: float = 0.02
PLACE_MIN_STREAK: int = 3
PLACE_MAX_CORRECTIONS: int = 6
PLACE_SETTLE_S: float = 2.0
# The load swings on the same 0.831 s pendulum the hook does. Measuring while
# it is moving is measuring the motion, not the error.
PLACE_MAX_SPEED_MPS: float = 0.05
PLACE_TIMEOUT_S: float = 25.0
# A marker whose bounding box touches the image edge is CLIPPED, and the
# centroid of a clipped shape is not the centroid of the shape. This is not a
# hypothetical: the Kirmizi Ucgen is 1 m on a side and the frame at the 0.30 m
# release altitude is only 0.83 m wide -- 121% of it -- so the "detection"
# there is a fragment. Measured on the 2026-08-27 mission: the aligner
# reported 44.4 mm against that fragment and the payload landed 89.7 cm from
# the true centre. Reject it instead.
PLACE_BORDER_MARGIN_PX: float = 4.0


@dataclass
class PlacementResult:
    aligned: bool
    reason: str
    final_error_m: Optional[float]
    corrections: int
    detections: int
    samples: List[dict] = field(default_factory=list)
    # ABSOLUTE destination position in NED, from the last good VISION sample.
    # The marker does not move, so once measured where the camera can see it
    # properly this can be acted on lower down, where it cannot. See
    # settle_onto_ned().
    target_ned: Optional[Tuple[float, float]] = None


def marker_offset_body_m(center_px, alt_m: float, res_w: int, res_h: int):
    """Ground marker position relative to the VEHICLE origin, in body axes.

    Same pixel-to-body convention as the rest of the stack (image +y is body
    AFT, image +x is body RIGHT), and the same camera lever-arm correction --
    the offset is measured from the CAMERA, which is not at the body origin.
    """
    intr = default_camera_intrinsics()
    if intr is None or alt_m is None or alt_m <= 0.0:
        return None
    focal = intr.scaled_to(res_w, res_h).focal_px
    if not focal:
        return None
    depth = alt_m + CAMERA_Z_ABOVE_MODEL_ORIGIN_M - MARKER_HEIGHT_M
    if depth <= 0.0:
        return None
    dx_px = center_px[0] - res_w / 2.0
    dy_px = center_px[1] - res_h / 2.0
    m_per_px = depth / focal
    lever_forward, lever_right = CAMERA_LEVER_ARM_BODY_M
    return (-dy_px * m_per_px + lever_forward, dx_px * m_per_px + lever_right)


def carried_payload_ned_offset(actuator):
    """Where the CARRIED load is, relative to the vehicle origin, as (n, e).

    The lock welds the payload to the hook, so the hook's own pose is the
    load's pose -- no second estimate is needed and none would be better.
    Returns None when the hook pose is unreadable, and the caller must then
    refuse to correct rather than guess: dropping on a guess is exactly the
    behaviour this replaces.
    """
    getter = getattr(actuator, "hook_nose_ned_offset_m", None)
    if getter is None:
        return None
    try:
        return getter()
    except Exception:  # noqa: BLE001
        return None


class VisualPlacementAligner:
    """Nudge the aircraft until the CARRIED load sits over the destination."""

    def __init__(self, get_detection, get_alt_m, get_yaw_deg, get_position_ned,
                 get_carried_offset, goto_ned_and_hold, get_rel_speed=None,
                 resolution=(1280, 960)):
        self.get_detection = get_detection
        self.get_alt_m = get_alt_m
        self.get_yaw_deg = get_yaw_deg
        self.get_position_ned = get_position_ned
        self.get_carried_offset = get_carried_offset
        self.goto_ned_and_hold = goto_ned_and_hold
        self.get_rel_speed = get_rel_speed
        self.resolution = resolution

    @staticmethod
    def _is_clipped(det, res_w: int, res_h: int) -> bool:
        """True when the detection touches the frame edge, i.e. is cut off."""
        bbox = getattr(det, "bbox_px", None)
        if not bbox:
            return False
        x1, y1, x2, y2 = bbox
        m = PLACE_BORDER_MARGIN_PX
        return (x1 <= m or y1 <= m or x2 >= res_w - m or y2 >= res_h - m)

    async def _measure(self):
        det = self.get_detection()
        if det is None:
            return None, None
        if self._is_clipped(det, *self.resolution):
            # A clipped marker's centroid is not its centre. Refusing costs a
            # retry; trusting it steers the aircraft to the wrong place.
            logger.debug("[GORSEL_YERLESTIRME] hedef kadraj kenarinda kirpik "
                         "-- merkez guvenilmez, olcum reddedildi")
            return None, det
        alt = await self.get_alt_m()
        if alt is None:
            return None, det
        w, h = self.resolution
        body = marker_offset_body_m(det.center_px, alt, w, h)
        if body is None:
            return None, det
        yaw = await self.get_yaw_deg()
        dest_n, dest_e = body_to_ned(body[0], body[1], yaw)
        carried = self.get_carried_offset()
        if carried is None:
            logger.debug("[GORSEL_YERLESTIRME] tasinan yuk pozu yok")
            return None, det
        return (dest_n - carried[0], dest_e - carried[1]), det

    async def align(self, altitude_m: float, yaw_deg: float,
                    tolerance_m: float = PLACE_TOLERANCE_M,
                    timeout_s: float = PLACE_TIMEOUT_S) -> PlacementResult:
        deadline = time.monotonic() + timeout_s
        corrections = dets = streak = 0
        last = None
        last_target_ned = None
        samples: List[dict] = []

        while time.monotonic() < deadline and corrections < PLACE_MAX_CORRECTIONS:
            err, det = await self._measure()
            if err is None:
                streak = 0
                await asyncio.sleep(0.2)
                continue
            dets += 1
            streak += 1
            n_now, e_now, _ = await self.get_position_ned()
            carried_now = self.get_carried_offset() or (0.0, 0.0)
            last_target_ned = (n_now + carried_now[0] + err[0],
                               e_now + carried_now[1] + err[1])
            mag = math.hypot(err[0], err[1])
            last = mag
            samples.append({"err_m": round(mag, 4),
                            "conf": round(det.confidence, 3) if det else None})
            if streak < PLACE_MIN_STREAK:
                await asyncio.sleep(0.15)
                continue
            if mag <= tolerance_m:
                logger.info("[GORSEL_YERLESTIRME] hizalandi: %.1f mm, %d duzeltme, "
                            "%d tespit", mag * 1000, corrections, dets)
                return PlacementResult(True, "aligned", mag, corrections, dets,
                                       samples, last_target_ned)
            if mag <= PLACE_DEADBAND_M:
                await asyncio.sleep(0.15)
                continue

            step_n, step_e = err[0] * PLACE_KP, err[1] * PLACE_KP
            step = math.hypot(step_n, step_e)
            if step > PLACE_MAX_STEP_M:
                k = PLACE_MAX_STEP_M / step
                step_n, step_e = step_n * k, step_e * k
            n0, e0, _ = await self.get_position_ned()
            logger.info("[GORSEL_YERLESTIRME] %d/%d yuk-hedef %.1f mm -> "
                        "(kuzey %+.3f, dogu %+.3f)", corrections + 1,
                        PLACE_MAX_CORRECTIONS, mag * 1000, step_n, step_e)
            await self.goto_ned_and_hold(n0 + step_n, e0 + step_e, altitude_m, yaw_deg)
            corrections += 1
            await self._wait_until_still()

        reason = "correction_budget" if corrections >= PLACE_MAX_CORRECTIONS else "timeout"
        if dets == 0:
            reason = "destination_not_seen"
        logger.warning("[GORSEL_YERLESTIRME] hizalanamadi (%s); son hata %s",
                       reason, f"{last * 1000:.1f} mm" if last is not None else "olculemedi")
        return PlacementResult(False, reason, last, corrections, dets, samples,
                               last_target_ned)

    async def _wait_until_still(self):
        if self.get_rel_speed is None:
            await asyncio.sleep(PLACE_SETTLE_S)
            return
        for _ in range(12):
            v = self.get_rel_speed()
            if v is None or v <= PLACE_MAX_SPEED_MPS:
                return
            await asyncio.sleep(0.25)


async def settle_onto_ned(target_ned, get_position_ned, get_carried_offset,
                          goto_ned_and_hold, alt_m: float, yaw_deg: float,
                          get_rel_speed=None,
                          tolerance_m: float = PLACE_TOLERANCE_M,
                          max_corrections: int = PLACE_MAX_CORRECTIONS,
                          gain: float = 0.5):
    """Put the carried load on a position measured EARLIER, at an altitude
    where the camera can no longer see it.

    The same shape as the pickup's low-altitude settle, and for the same
    reason: the marker is measured where vision is trustworthy, and the last
    few centimetres are closed against the stored answer using the load's own
    position -- which, while it is locked to the hook, IS the hook's position.

    Gain is below 1 on purpose. A dead-beat step onto a hanging load converts
    position error into swing; halving it lets the pendulum catch up.

    Returns the final error in metres, or None if the load's pose is unknown.
    """
    last = None
    for i in range(1, max_corrections + 1):
        carried = get_carried_offset()
        if carried is None:
            logger.warning("[YERLESTIRME_DUZELTME] tasinan yuk pozu yok")
            return None
        n0, e0, _ = await get_position_ned()
        err_n = target_ned[0] - (n0 + carried[0])
        err_e = target_ned[1] - (e0 + carried[1])
        last = math.hypot(err_n, err_e)
        if last <= tolerance_m:
            logger.info("[YERLESTIRME_DUZELTME] %d/%d yuk-hedef %.1f mm -- hedefin icinde.",
                        i, max_corrections, last * 1000)
            return last
        logger.info("[YERLESTIRME_DUZELTME] %d/%d yuk-hedef %.1f mm -> (kuzey %+.3f, dogu %+.3f)",
                    i, max_corrections, last * 1000, err_n * gain, err_e * gain)
        await goto_ned_and_hold(n0 + err_n * gain, e0 + err_e * gain, alt_m, yaw_deg)
        if get_rel_speed is not None:
            for _ in range(12):
                v = get_rel_speed()
                if v is None or v <= PLACE_MAX_SPEED_MPS:
                    break
                await asyncio.sleep(0.25)
        else:
            await asyncio.sleep(PLACE_SETTLE_S)
    logger.warning("[YERLESTIRME_DUZELTME] butce doldu; son %s",
                   f"{last * 1000:.1f} mm" if last is not None else "olculemedi")
    return last
