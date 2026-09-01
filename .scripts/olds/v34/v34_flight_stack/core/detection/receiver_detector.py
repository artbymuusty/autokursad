"""Visual detection of a payload's hook receiver, for closed-loop alignment.

WHAT IS BEING DETECTED, AND WHY IT IS NOT THE HOLE
--------------------------------------------------
"Find the dark circular funnel opening" does not work here, and the reason is
geometric rather than a tuning failure. The bore is cut into the payload's OWN
mesh and carries the SAME material, so it is red-on-red / blue-on-blue: a value
difference with no hue or saturation edge. Verified on real Gazebo frames.

The reliable signal is a fact about the CAD instead:

    The receiver bore axis passes through the payload's own centroid.

Both are centred on the payload link origin (radius-vs-z profile measured off
payload_body.stl, see core/mission/hook_seating.py). So the centre of the
payload's TOP FACE is the receiver axis.

THE CORRECTION THAT MAKES IT ACCURATE
-------------------------------------
Taking the centre of the red silhouette is NOT the top-face centre, and the
error is larger than the mouth itself. The payload is 70 mm tall, so the camera
sees its side walls too. Because this camera is nadir, the deck plane and the
ground footprint are both HORIZONTAL, i.e. parallel to the sensor: each
projects to a similar copy of the same rectangle, scaled about the principal
point. The footprint scale is

    s = d / (d + 0.070)   < 1

so the footprint lies CLOSER to the principal point than the top face, and the
visible walls always spill INWARD. The silhouette is conv(Q, sQ), whose centre
is pulled toward the image centre -- measured 11.6 px mean, 34 px worst, larger
than the 23.25 mm mouth radius it is supposed to land inside.

The top face is recovered exactly by a radial erosion:

    D(s) = { x in X : pp + s*(x - pp) in X }

For x in the top face the contracted point lands in sQ and is kept; for x in
the wall spill it lands outside and is dropped. s depends on the unknown camera
height, so it is solved as a fixed point by bisection on the implied long side.

MEASURED, on 66 Gazebo frames labelled by projecting simulator ground-truth
poses (never by a detector), against two alternatives implemented and
benchmarked independently:

    variant                       det%   mean px   mean cm   ms/frame
    top-face de-shadow (this)    100.0      0.63     0.086       7.5
    grey target disc              97.0      0.87     0.131      15.9
    hybrid of the two            100.0      0.97     0.152      29.6

    ...and the naive silhouette centre this replaces:  11.59 px mean, 34 px max.

At pickup altitude (0.30-0.60 m) this detector measures 0.130 cm mean /
0.397 cm p95, against the seating gate's 2.325 cm lateral budget -- roughly
18x margin. A learned detector is not warranted: a YOLO box centre would be
~2-3 px at best, several times worse than a geometric fit, and no weights for
this target exist in the repo.

WHAT THIS IS NOT
----------------
This is a MEASUREMENT, not an authority. It says where the receiver is in the
image. It does not decide that a pickup may proceed -- that stays with
core/mission/hook_seating.py, which validates real physical geometry. Vision
sits above the seating gate, never in place of it.
"""
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

# Gate downstream consumers on this. The one frame in 66 that the detector got
# wrong (9.91 px, a payload truncated by the image border) flagged itself at
# confidence 0.46; every good frame scored >= 0.75.
MIN_TRUSTED_CONFIDENCE: float = 0.70


@dataclass(frozen=True)
class ReceiverDetection:
    """Where the receiver axis is, in pixels, plus how much to trust it."""
    u: float
    v: float
    radius_px: float          # expected mouth radius at this apparent scale
    angle_deg: float          # payload long-axis orientation in the image
    confidence: float         # 0..1, see MIN_TRUSTED_CONFIDENCE
    method: str
    blob_area_px: float = 0.0

    @property
    def center(self) -> Tuple[float, float]:
        return (self.u, self.v)

    @property
    def trusted(self) -> bool:
        return self.confidence >= MIN_TRUSTED_CONFIDENCE


# ---------------------------------------------------------------- camera ----
FOCAL_PX = 539.94          # 1280 px / (2*tan(1.74/2))
PP = (640.0, 480.0)        # ideal pinhole, no distortion

# ------------------------------------------------------------- geometry -----
PAYLOAD_LONG = 0.142       # m, deck long side
PAYLOAD_SHORT = 0.052      # m, deck short side
DECK_H = 0.070             # m, deck top above ground  -> the side-wall spill
MOUTH_DIA = 0.0465         # m, receiver mouth diameter
MOUTH_R_OVER_LONG = (0.5 * MOUTH_DIA) / PAYLOAD_LONG   # 0.16373
EXPECTED_ASPECT = PAYLOAD_LONG / PAYLOAD_SHORT          # 2.7308

# --------------------------------------------------------- colour bands -----
# tuned HSV bands from the repo (absolute; the sim has no auto-exposure)
BANDS = {
    "red":  [((0, 40, 40), (15, 255, 255)), ((165, 40, 40), (180, 255, 255))],
    "blue": [((90, 80, 40), (140, 255, 255))],
}

MIN_AREA = 250          # px^2, below this the payload is not usable anyway

# OpenCV contour vertices are pixel *indices*; the ground truth is a continuous
# projection u = cx + f*X/Z in which pixel i covers [i, i+1).  The two differ by
# half a pixel.  Measured signed bias over the 66 valid frames: (-0.53, -0.43).
PIXEL_CENTRE_OFFSET = 0.5
# the HSV threshold + 3x3 close grow the blob by roughly half a pixel per edge
EDGE_DILATION_PX = 1.0
MIN_S, MAX_S = 0.78, 0.9995


# ----------------------------------------------------------------------------
def _colour_mask(bgr, color):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = None
    for lo, hi in BANDS[color]:
        b = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        m = b if m is None else cv2.bitwise_or(m, b)
    # kill single-pixel speckle, close the 1-2 px seam the grey target disc and
    # the raised bore collar cut into the deck
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k3)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k3)
    return m


def _payload_hull(mask):
    """Convex hull of the payload blobs.

    The silhouette of a convex box under a pinhole is convex, so hulling is
    exact for a clean view and is a repair for occlusion (drone leg, winch
    cable, the other payload cutting across).  Small satellite blobs are only
    merged when they are close enough to plausibly be the same box.
    """
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n < 2:
        return None, 0.0
    areas = st[1:, cv2.CC_STAT_AREA]
    k = 1 + int(np.argmax(areas))
    main_area = float(areas[k - 1])
    if main_area < MIN_AREA:
        return None, 0.0

    keep = [k]
    x0, y0 = st[k, cv2.CC_STAT_LEFT], st[k, cv2.CC_STAT_TOP]
    x1 = x0 + st[k, cv2.CC_STAT_WIDTH]
    y1 = y0 + st[k, cv2.CC_STAT_HEIGHT]
    reach = 0.6 * max(st[k, cv2.CC_STAT_WIDTH], st[k, cv2.CC_STAT_HEIGHT])
    for j in range(1, n):
        if j == k or areas[j - 1] < 0.04 * main_area:
            continue
        bx0, by0 = st[j, cv2.CC_STAT_LEFT], st[j, cv2.CC_STAT_TOP]
        bx1 = bx0 + st[j, cv2.CC_STAT_WIDTH]
        by1 = by0 + st[j, cv2.CC_STAT_HEIGHT]
        gap = math.hypot(max(0, max(x0 - bx1, bx0 - x1)),
                         max(0, max(y0 - by1, by0 - y1)))
        if gap <= reach:
            keep.append(j)

    pts = []
    sel = np.isin(lab, keep).astype(np.uint8)
    cnts, _ = cv2.findContours(sel, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        pts.append(c.reshape(-1, 2))
    if not pts:
        return None, 0.0
    hull = cv2.convexHull(np.vstack(pts).astype(np.int32))
    kept_area = float(sum(areas[j - 1] for j in keep))
    return hull, kept_area


def _deshadow(roi, s, ox, oy):
    """Keep x in roi whose radial contraction by s about pp is also in roi.

    Sampling outside the ROI returns 0, which is correct: the ROI is the bbox
    of the payload silhouette, so any red point is inside it by construction.
    """
    px, py = PP[0] - ox, PP[1] - oy
    A = np.array([[s, 0.0, (1.0 - s) * px],
                  [0.0, s, (1.0 - s) * py]], np.float32)
    w = cv2.warpAffine(roi, A, (roi.shape[1], roi.shape[0]),
                       flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                       borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return cv2.bitwise_and(roi, w)


def _top_face_rect(roi, s, ox, oy):
    d = _deshadow(roi, s, ox, oy)
    n, lab, st, _ = cv2.connectedComponentsWithStats(d, 8)
    if n < 2:
        return None, None
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    comp = (lab == k).astype(np.uint8)
    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < MIN_AREA:
        return None, None
    return cv2.minAreaRect(c), c


def _s_from_long_side(L):
    """L (px) of the top face -> depth d -> radial shrink factor of the base."""
    if L <= 1.0:
        return MAX_S
    d = PAYLOAD_LONG * FOCAL_PX / L
    return d / (d + DECK_H)


# ----------------------------------------------------------------------------
def _detect_raw(bgr, color="red"):
    """bgr: HxWx3 uint8 BGR. color: "red" or "blue".
    Returns dict(u=float, v=float, radius_px=float, confidence=float, method=str)
    or None when nothing is found."""
    if bgr is None or bgr.ndim != 3:
        return None
    color = str(color).lower()
    if color not in BANDS:
        return None

    mask = _colour_mask(bgr, color)
    hull, blob_area = _payload_hull(mask)
    if hull is None:
        return None

    H, W = mask.shape[:2]
    x, y, w, h = cv2.boundingRect(hull)
    pad = 2
    ox, oy = max(0, x - pad), max(0, y - pad)
    ex, ey = min(W, x + w + pad), min(H, y + h + pad)
    roi = np.zeros((ey - oy, ex - ox), np.uint8)
    cv2.drawContours(roi, [hull - np.array([[ox, oy]])], -1, 255, cv2.FILLED)

    raw_rect = cv2.minAreaRect(hull)
    raw_long = max(raw_rect[1])

    # ---- solve the fixed point  s == s_implied(long side of D(s))  ----------
    lo, hi = MIN_S, MAX_S
    best = None
    for _ in range(16):
        mid = 0.5 * (lo + hi)
        rect, cnt = _top_face_rect(roi, mid, ox, oy)
        if rect is None:
            lo = mid                      # over-eroded: s must be larger
            continue
        best = (mid, rect, cnt)
        r = _s_from_long_side(max(rect[1])) - mid
        if r > 0:
            lo = mid                      # de-shadowed box still too small
        else:
            hi = mid
    if best is None:
        # de-shadow never produced anything; fall back to the raw silhouette
        rect, cnt = raw_rect, hull
        s_used = 1.0
        cu, cv_ = rect[0]            # hull/raw_rect are already in image coords
        method = "payload-rect-raw"
    else:
        s_used, rect, cnt = best
        cu, cv_ = rect[0][0] + ox, rect[0][1] + oy   # ROI -> image coords
        method = "payload-topface-deshadow"

    (rw, rh) = rect[1]
    long_side, short_side = max(rw, rh), min(rw, rh)
    if long_side < 4.0:
        return None

    # mouth radius scaled off the deck long side (both live on the same plane,
    # which is parallel to the sensor -> a single similarity factor)
    radius_px = MOUTH_R_OVER_LONG * max(long_side - EDGE_DILATION_PX, 1.0)

    # ------------------------------- confidence -----------------------------
    rect_area = max(long_side * short_side, 1.0)
    fill = float(cv2.contourArea(cnt)) / rect_area          # ~0.95 ideal
    f_fill = max(0.0, min(1.0, (fill - 0.55) / 0.35))

    aspect = long_side / max(short_side, 1e-6)
    f_aspect = math.exp(-((aspect - EXPECTED_ASPECT) ** 2) / (2 * 0.55 ** 2))

    # how much of the silhouette survived: an occluded / clipped box loses more
    # than the geometry predicts
    shrink = (long_side / raw_long) if raw_long > 1 else 1.0
    f_shrink = max(0.0, min(1.0, (shrink - 0.35) / 0.35))

    conf = float(max(0.0, min(1.0, 0.45 * f_fill + 0.40 * f_aspect + 0.15 * f_shrink)))

    # touching the image border means the rect (hence the centre) is unreliable
    bx, by, bw, bh = cv2.boundingRect(hull)
    if bx <= 1 or by <= 1 or bx + bw >= W - 1 or by + bh >= H - 1:
        conf *= 0.5

    return dict(u=float(cu) + PIXEL_CENTRE_OFFSET,
                v=float(cv_) + PIXEL_CENTRE_OFFSET, radius_px=float(radius_px),
                confidence=conf, method=method)

# Aliases kept so callers read in the repo's vocabulary.
PAYLOAD_LONG_M = PAYLOAD_LONG
PAYLOAD_SHORT_M = PAYLOAD_SHORT
PAYLOAD_ASPECT = EXPECTED_ASPECT
RECEIVER_MOUTH_R_M = 0.5 * MOUTH_DIA
DECK_HEIGHT_M = DECK_H


def detect(bgr, color: str = "red", deck_depth_m: Optional[float] = None,
           principal_point: Optional[Tuple[float, float]] = None,
           ) -> Optional[ReceiverDetection]:
    """Locate the receiver axis, or None if it is not found.

    deck_depth_m / principal_point are accepted for interface compatibility
    with callers that know the camera height. They are NOT needed here: the
    scale is solved from the image itself by the bisection in
    _s_from_long_side, which is what makes this detector independent of
    altitude telemetry.

    Returning None is always preferable to returning a wrong centre: this
    feeds a position controller, so a confident wrong answer would fly the
    aircraft somewhere nothing asked for.
    """
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return None
    if color not in BANDS:
        raise ValueError(f"unknown payload colour {color!r}")
    raw = _detect_raw(bgr, color)
    if raw is None:
        return None
    return ReceiverDetection(
        u=float(raw["u"]), v=float(raw["v"]),
        radius_px=float(raw["radius_px"]),
        angle_deg=float(raw.get("angle_deg", 0.0)),
        confidence=float(raw["confidence"]),
        method=str(raw.get("method", "top_face_deshadow")),
        blob_area_px=float(raw.get("blob_area_px", 0.0)))
