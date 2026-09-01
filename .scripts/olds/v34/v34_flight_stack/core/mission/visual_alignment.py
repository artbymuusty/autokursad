"""Closed-loop visual alignment of the hook onto a payload receiver.

WHERE THIS SITS IN THE STACK -- read this before changing anything.

    VISION  (this module)        measures where the receiver is
      |                          and asks the aircraft to move
      v
    PHYSICAL POSITION
      |
      v
    SEATING GATE  (core/mission/hook_seating.py)   decides if it may lock
      |
      v
    LOCK

Vision REQUESTS alignment. It never authorises a lock. The seating gate stays
the sole authority on whether the hook is physically in the receiver, and it
validates against real geometry, not against anything measured here. A vision
failure must therefore be able to cost a retry and nothing worse.

WHY THE ERROR IS NOT MEASURED IN THE IMAGE
------------------------------------------
The obvious formulation -- "drive the hook's pixel onto the receiver's pixel"
-- is wrong here, and not by a little. The hook hangs BELOW the camera and the
receiver sits ON THE GROUND, so the two are at very different depths; image
coincidence happens only at the instant of contact. Measured from the CAD
geometry, servoing in image space carries a bias of

    0.175 m * (hook height above the deck) / (hook distance below the camera)

which is 0.337 mm per mm of hover height, i.e. up to ~206 mm at a 1.2 m hover
-- an order of magnitude outside the seating gate's 23.25 mm lateral budget.
Worse, the hook's Ø45 shell OCCLUDES the receiver mouth from about 0.65 m
camera height downward, exactly during final approach.

So both sides are converted to METRES first and differenced there:

    receiver  <- from the IMAGE (this is the camera measurement)
    hook      <- from the real hook pose (a simulated mechanical sensor,
                 the same source the seating gate uses)
    error     =  receiver_ned - hook_ned

That is a genuine "centre the hook on the receiver", done in the frame where
it is actually true.

WHY THE MEASUREMENT OUTLIVES THE LOOP
-------------------------------------
The camera cannot see the receiver at the altitude where the hook actually
reaches it. With the hook over the receiver the CAMERA is 0.26 m ahead of it
(0.175 m hook offset + 0.085 m lever arm), and at the 0.30 m pickup altitude
that projects 501 px below centre -- past the 480 px half-frame. Measured: the
mission got 7 detections in 30 iterations there and correctly refused.

So alignment runs where the camera CAN see (0.55 m, receiver at 55% of the
half-frame), and its durable output is `receiver_ned` -- the receiver's
absolute position, which does not move. The final low-altitude correction is
then made against that stored measurement rather than against a live image,
with the hook's real pose closing the loop. The camera is still what found the
receiver; only the last few centimetres are dead-reckoned from its answer, and
the seating gate validates the result regardless.

SIGN CONVENTION
---------------
Taken verbatim from CenteringController._freeze_target_estimate, which is the
one place in this codebase where it has been validated in flight:

    m_per_px  = depth / focal
    forward_m = -dy_px * m_per_px + lever_forward
    right_m   =  dx_px * m_per_px + lever_right
    north_m   = forward*cos(yaw) - right*sin(yaw)
    east_m    = forward*sin(yaw) + right*cos(yaw)

Image +y is body AFT and image +x is body RIGHT. Getting this wrong makes the
loop diverge instead of converge, so it is not re-derived here.
"""
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from core.config.parameters import CAMERA_LEVER_ARM_BODY_M
from core.detection.camera_intrinsics import default_camera_intrinsics
from core.detection.receiver_detector import (
    MOUTH_R_OVER_LONG, PAYLOAD_LONG_M, RECEIVER_MOUTH_R_M, ReceiverDetection,
    detect,
)

logger = logging.getLogger(__name__)

# --- camera mount -------------------------------------------------------
# camera_link sits at model-frame z = +0.050 (measured live off
# /world/<w>/dynamic_pose/info), i.e. 0.19 m BELOW base_link, not above it.
# PX4's reported relative altitude tracks the model origin, so
#     camera height above ground = reported_alt + 0.050
CAMERA_Z_ABOVE_MODEL_ORIGIN_M: float = 0.050
# Payload deck top above ground, with the payload resting (link z 0.035 plus
# the 0.035 half-height). The receiver mouth opens here.
DECK_HEIGHT_M: float = 0.070

# --- control ------------------------------------------------------------
# Proportional gain on a POSITION step, not a velocity: each iteration
# commands a hold at (current + gain*error), so <1 is a damping factor and
# 1.0 would be a dead-beat step onto a noisy measurement.
ALIGN_KP: float = 0.6
# Never ask for more than this in one step. A larger jump would out-run the
# rope: the hook is a pendulum with a measured 0.831 s period, and yanking the
# airframe simply converts position error into swing.
ALIGN_MAX_STEP_M: float = 0.08
# Below this the measurement noise exceeds the correction, so stop nudging.
# The detector's measured centre error at pickup altitude is ~5 mm mean.
ALIGN_DEADBAND_M: float = 0.006
# Accept convergence at half the seating gate's 23.25 mm lateral limit, so the
# gate is entered with margin rather than on its edge.
ALIGN_TOLERANCE_M: float = 0.010
# Exponential smoothing on the measured error. The detector occasionally falls
# back to the biased rect centre; unfiltered that would produce a visible jump.
ALIGN_FILTER_ALPHA: float = 0.6
# Consecutive good detections required before the first move. A single frame
# is not a measurement.
ALIGN_MIN_STREAK: int = 3
# Reject detections the detector itself is unsure of.
ALIGN_MIN_CONFIDENCE: float = 0.45
# Give up rather than hunt forever; the mission retries.
ALIGN_TIMEOUT_S: float = 25.0
# Total commanded travel budget. If alignment has moved this far it is not
# converging, it is chasing a mis-detection.
ALIGN_MAX_TRAVEL_M: float = 0.60
# How long the error must stay inside tolerance before declaring success.
ALIGN_DWELL_S: float = 0.4
# Frames without a detection before the loop stops commanding and reports lost.
ALIGN_MAX_LOST_FRAMES: int = 12


@dataclass
class AlignResult:
    converged: bool
    reason: str
    final_error_m: Optional[float]
    iterations: int
    travel_m: float
    detections: int
    lost_frames: int
    samples: List[dict] = field(default_factory=list)
    # ABSOLUTE receiver position in NED, from the last good VISION sample.
    # This is the durable product of the alignment: the receiver does not
    # move, so once it has been measured well it can be acted on later, at an
    # altitude where the camera can no longer see it. See the note on
    # receiver_ned in the module docstring.
    receiver_ned: Optional[Tuple[float, float]] = None


def camera_deck_depth_m(reported_alt_m: float) -> float:
    """Camera-to-deck distance from ALTITUDE TELEMETRY. Fallback only.

    Prefer depth_from_detection(): PX4's reported altitude and the true camera
    height differ by a few centimetres of hover error, and that error scales
    the whole metric conversion. Measured live: a vision estimate of 52.3 mm
    against a true 22.6 mm, i.e. ~30 mm of error on a 0.26 m offset -- almost
    exactly the ~10% depth error the hover offset produces.
    """
    return reported_alt_m + CAMERA_Z_ABOVE_MODEL_ORIGIN_M - DECK_HEIGHT_M


def depth_from_detection(det: ReceiverDetection, focal_px: float):
    """Camera-to-deck distance solved FROM THE IMAGE, with no telemetry.

    The detector reports the mouth radius it measured, and the mouth's true
    size is known from the CAD, so

        depth = focal * mouth_radius / radius_px

    This is self-consistent with the same pixels the centre came from, so it
    cannot drift against altitude error, mount-offset assumptions, or hover
    error. The detector's radius error was measured at 0.12 px mean over 66
    frames, which at pickup scale is well under a millimetre of depth.

    Returns None when the radius is implausible, so the caller can fall back.
    """
    if det is None or det.radius_px <= 1.0 or not focal_px:
        return None
    depth = focal_px * RECEIVER_MOUTH_R_M / det.radius_px
    # Sanity band: this camera cannot be 5 cm or 10 m from a payload deck.
    return depth if 0.05 < depth < 10.0 else None


def receiver_offset_body_m(det: ReceiverDetection, deck_depth_m: float,
                           res_w: int, res_h: int) -> Optional[Tuple[float, float]]:
    """Receiver position relative to the VEHICLE origin, in body axes.

    Returns (forward_m, right_m), or None if the intrinsics are unavailable.
    The camera lever arm is added because the pixel offset is measured from
    the CAMERA, which is not at the body origin the position controller uses.
    """
    intr = default_camera_intrinsics()
    if intr is None or deck_depth_m is None or deck_depth_m <= 0.0:
        return None
    focal = intr.scaled_to(res_w, res_h).focal_px
    if not focal:
        return None
    dx_px = det.u - res_w / 2.0
    dy_px = det.v - res_h / 2.0
    m_per_px = deck_depth_m / focal
    lever_forward, lever_right = CAMERA_LEVER_ARM_BODY_M
    return (-dy_px * m_per_px + lever_forward, dx_px * m_per_px + lever_right)


def body_to_ned(forward_m: float, right_m: float, yaw_deg: float) -> Tuple[float, float]:
    y = math.radians(yaw_deg or 0.0)
    return (forward_m * math.cos(y) - right_m * math.sin(y),
            forward_m * math.sin(y) + right_m * math.cos(y))


class VisualHookAligner:
    """Drives the aircraft so the REAL hook lands on the SEEN receiver.

    Deliberately constructed from callables rather than from the mission
    objects, so the whole control law is testable without a simulator.
    """

    def __init__(self, get_frame, get_alt_m, get_yaw_deg, get_position_ned,
                 get_hook_ned_offset, goto_ned_and_hold, color: str = "red",
                 detector: Callable = detect, get_truth_lateral_m=None):
        self.get_frame = get_frame
        self.get_alt_m = get_alt_m
        self.get_yaw_deg = get_yaw_deg
        self.get_position_ned = get_position_ned
        self.get_hook_ned_offset = get_hook_ned_offset
        self.goto_ned_and_hold = goto_ned_and_hold
        # SALT OLCUM (mekanizma 2c): verilirse her iterasyonda gorus
        # tahmininin yanina o anki GERCEK yanal hata da yazilir. None ise
        # davranis hic degismez.
        self.get_truth_lateral_m = get_truth_lateral_m
        # Son olcumun ara terimleri (salt tani). _measure'in DONUS
        # ARITESI bilerek degistirilmedi: testler ve diger cagiranlar
        # 2'li donusu bekliyor.
        self._last_diag = {}
        self.color = color
        self.detector = detector

    async def _measure(self, res_w: int, res_h: int):
        """One vision measurement of the hook->receiver error, in NED metres.

        Ara terimler SALT TANI olarak self._last_diag'a yazilir (mekanizma
        2c, 2026-08-31), boylece gorus tahmininin hangi terimle birlikte
        gercekten ayristigi olculebilir. Karar akisina girmez ve DONUS
        ARITESI degismez -- testler ve diger cagiranlar 2'li donusu bekliyor.
        """
        self._last_diag = {}
        frame = await self.get_frame()
        if frame is None:
            logger.debug("[GORSEL_HIZA] kare yok")
            return None, None
        alt = await self.get_alt_m()
        if alt is None:
            logger.debug("[GORSEL_HIZA] irtifa yok")
            return None, None
        depth_tel = camera_deck_depth_m(alt)
        det = self.detector(frame, self.color, deck_depth_m=depth_tel)
        if det is None:
            logger.debug("[GORSEL_HIZA] alici goruntude yok (irtifa %.2f m)", alt)
            return None, None
        if det.confidence < ALIGN_MIN_CONFIDENCE:
            logger.debug("[GORSEL_HIZA] guven dusuk %.2f < %.2f",
                         det.confidence, ALIGN_MIN_CONFIDENCE)
            return None, det
        h, w = frame.shape[0], frame.shape[1]
        intr = default_camera_intrinsics()
        focal = intr.scaled_to(w, h).focal_px if intr else None
        # Image-solved depth is authoritative; telemetry is the fallback.
        depth_img = depth_from_detection(det, focal)
        depth = depth_img or depth_tel
        body = receiver_offset_body_m(det, depth, w, h)
        if body is None:
            return None, det
        yaw = await self.get_yaw_deg()
        recv_n, recv_e = body_to_ned(body[0], body[1], yaw)
        hook = self.get_hook_ned_offset()
        if hook is None:
            logger.debug("[GORSEL_HIZA] kanca pozu yok -- oturma dogrulanamaz")
            return None, det
        truth = None
        if self.get_truth_lateral_m is not None:
            try:
                truth = self.get_truth_lateral_m()
            except Exception:  # noqa: BLE001 -- salt olcum, hizalamayi dusuremez
                truth = None
        self._last_diag = {
            "alt_m": round(alt, 4), "focal_px": round(focal, 2),
            "depth_img_m": (round(depth_img, 4) if depth_img else None),
            "depth_tel_m": round(depth_tel, 4),
            "depth_used_m": round(depth, 4),
            "depth_src": "image" if depth_img else "telemetry",
            "u": round(det.u, 2), "v": round(det.v, 2),
            "radius_px": round(det.radius_px, 2),
            "long_px": round(det.radius_px / MOUTH_R_OVER_LONG + 1.0, 2),
            "conf": round(det.confidence, 3), "method": det.method,
            "yaw_deg": (round(yaw, 2) if yaw is not None else None),
            "body_fwd_m": round(body[0], 4), "body_right_m": round(body[1], 4),
            "hook_off_n": round(hook[0], 4), "hook_off_e": round(hook[1], 4),
            "err_raw_m": round(math.hypot(recv_n - hook[0], recv_e - hook[1]), 4),
            "truth_lateral_m": (round(truth, 4) if truth is not None else None),
        }
        return (recv_n - hook[0], recv_e - hook[1]), det

    async def align(self, altitude_m: float, yaw_deg: float,
                    timeout_s: float = ALIGN_TIMEOUT_S,
                    tolerance_m: float = ALIGN_TOLERANCE_M) -> AlignResult:
        """tolerance_m is deliberately a parameter.

        The AIRBORNE stage does not need millimetre precision: its job is to
        measure the receiver well and get roughly over it. The fine work is
        done afterwards at pickup altitude, where the winch is out and each
        nudge DRAGS the resting hook across the deck instead of swinging it.
        Demanding 10 mm in the air just spends the deadline fighting the
        pendulum -- measured: 23 good detections, still timing out at 31 mm.
        """
        deadline = time.monotonic() + timeout_s
        filt = None
        travel = 0.0
        iters = dets = lost = 0
        inside_since = None
        samples: List[dict] = []
        last_err = None
        last_recv_ned = None

        while time.monotonic() < deadline:
            iters += 1
            err, det = await self._measure(1280, 960)
            diag = getattr(self, "_last_diag", None)
            if diag:
                logger.info("[GORSEL_HIZA_TANI] it=%d %s", iters,
                            " ".join(f"{k}={v}" for k, v in diag.items()))
            if err is None:
                lost += 1
                if lost >= ALIGN_MAX_LOST_FRAMES:
                    return AlignResult(False, "receiver_lost", last_err, iters,
                                       travel, dets, lost, samples, last_recv_ned)
                # DO NOT command anything while blind. Holding still is the
                # only safe action when the measurement is gone.
                await asyncio.sleep(0.15)
                continue

            lost = 0
            dets += 1
            n_now, e_now, _ = await self.get_position_ned()
            hook_now = self.get_hook_ned_offset() or (0.0, 0.0)
            # receiver_abs = vehicle + hook_offset + (receiver - hook)
            last_recv_ned = (n_now + hook_now[0] + err[0],
                             e_now + hook_now[1] + err[1])
            filt = err if filt is None else (
                ALIGN_FILTER_ALPHA * err[0] + (1 - ALIGN_FILTER_ALPHA) * filt[0],
                ALIGN_FILTER_ALPHA * err[1] + (1 - ALIGN_FILTER_ALPHA) * filt[1])
            mag = math.hypot(filt[0], filt[1])
            last_err = mag
            samples.append({"t": round(time.monotonic(), 3),
                            "err_m": round(mag, 4),
                            "conf": round(det.confidence, 3) if det else None,
                            "method": det.method if det else None})

            logger.debug("[GORSEL_HIZA] it=%d hata=(%.3f,%.3f) |%.3f| m conf=%.2f",
                         iters, filt[0], filt[1], mag, det.confidence if det else -1)
            if dets < ALIGN_MIN_STREAK:
                await asyncio.sleep(0.12)
                continue

            if mag <= tolerance_m:
                inside_since = inside_since or time.monotonic()
                if time.monotonic() - inside_since >= ALIGN_DWELL_S:
                    logger.info("[GORSEL_HIZA] yakinsadi: %.1f mm, %d iterasyon, "
                                "%d tespit, %.3f m hareket", mag * 1000, iters, dets, travel)
                    return AlignResult(True, "converged", mag, iters, travel,
                                       dets, lost, samples, last_recv_ned)
            else:
                inside_since = None

            if mag <= ALIGN_DEADBAND_M:
                await asyncio.sleep(0.12)
                continue

            step_n, step_e = filt[0] * ALIGN_KP, filt[1] * ALIGN_KP
            step = math.hypot(step_n, step_e)
            if step > ALIGN_MAX_STEP_M:
                k = ALIGN_MAX_STEP_M / step
                step_n, step_e = step_n * k, step_e * k
                step = ALIGN_MAX_STEP_M
            if travel + step > ALIGN_MAX_TRAVEL_M:
                return AlignResult(False, "travel_budget_exhausted", mag, iters,
                                   travel, dets, lost, samples, last_recv_ned)

            n0, e0, _ = await self.get_position_ned()
            await self.goto_ned_and_hold(n0 + step_n, e0 + step_e, altitude_m, yaw_deg)
            travel += step

        return AlignResult(False, "timeout", last_err, iters, travel, dets, lost, samples,
                           last_recv_ned)
