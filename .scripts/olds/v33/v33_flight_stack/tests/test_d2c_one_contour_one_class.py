"""D2c: one contour must not commit as two classes.

Measured over 1741 live frames on 2026-08-17: 122 of them emitted
KIRMIZI_DIKDORTGEN *and* KIRMIZI_UCGEN together, from the SAME single red
blob -- identical area distributions (median 512 px2 in both sets), 3
vertices at eps 0.03, and not one touching the frame edge. No frame in the
entire flight contained more than one red or more than one blue blob, so
the payload contributed nothing: the arena triangle was committing as a
rectangle as well as a triangle, and Görev 3's pickup target IS a rectangle.

The cause is two shape gates sweeping different eps ranges over one
contour: 3 vertices over the triangle's 0.03-0.09, 4 over the rectangle's
tighter 0.02-0.06 where a rounded corner splits in two.
"""
import cv2
import numpy as np
import pytest

from core.detection.hsv_contour_detector import HSVContourDetector
from core.detection.types import Detection


def _triangle_frame(side_px=120, centre=(640, 480), colour=(0, 0, 220)):
    """A solid red triangle on grey, big enough to clear every area gate."""
    frame = np.full((960, 1280, 3), 120, dtype=np.uint8)
    cx, cy = centre
    h = int(side_px * 0.866)
    pts = np.array([[cx, cy - 2 * h // 3],
                    [cx - side_px // 2, cy + h // 3],
                    [cx + side_px // 2, cy + h // 3]], dtype=np.int32)
    cv2.fillPoly(frame, [pts], colour)
    return frame


def _det(shape_type, centre, bbox):
    return Detection(shape_type=shape_type, confidence=0.9,
                     center_px=centre, bbox_px=bbox)


def test_rectangle_on_top_of_a_committed_triangle_is_suppressed():
    """THE regression: a rectangle whose centre sits inside an already
    committed triangle is that same triangle, not a second object."""
    tri = _det("KIRMIZI_UCGEN", (640.0, 480.0), (580.0, 420.0, 700.0, 540.0))
    rect = _det("KIRMIZI_DIKDORTGEN", (641.0, 483.0), (581.0, 421.0, 699.0, 539.0))
    assert HSVContourDetector._overlaps_committed(rect, [tri]) is True


def test_a_genuinely_separate_rectangle_still_commits():
    """The suppression must not blind Görev 3: a rectangle somewhere else
    in the frame is a real second object and has to survive."""
    tri = _det("KIRMIZI_UCGEN", (300.0, 300.0), (240.0, 240.0, 360.0, 360.0))
    rect = _det("KIRMIZI_DIKDORTGEN", (900.0, 700.0), (840.0, 640.0, 960.0, 760.0))
    assert HSVContourDetector._overlaps_committed(rect, [tri]) is False


def test_no_committed_shapes_means_nothing_to_suppress():
    rect = _det("KIRMIZI_DIKDORTGEN", (640.0, 480.0), (580.0, 420.0, 700.0, 540.0))
    assert HSVContourDetector._overlaps_committed(rect, []) is False


@pytest.mark.asyncio
async def test_a_lone_triangle_never_also_commits_as_a_rectangle():
    """End to end through the real detector, on a synthetic frame holding
    exactly one red triangle. Whatever else it reports, it must not report
    a rectangle in the same place -- that is what sent the vehicle after the
    wrong class."""
    det = HSVContourDetector()
    frame = _triangle_frame()
    classes = []
    # Streak gates need consecutive frames before anything commits.
    for _ in range(6):
        classes = [d.shape_type for d in await det.detect(frame)]

    assert "KIRMIZI_DIKDORTGEN" not in classes, classes
    assert "MAVI_DIKDORTGEN" not in classes, classes


# --- F3 fix (2026-08-20): colour-aware suppression -----------------------
#
# Root-caused via live SITL + a passive Gazebo pose trace: Görev 3's own
# dropped payload is a real, differently-coloured rectangle that ADR-011
# deliberately places on top of the arena target it was aimed at (RED
# payload on the BLUE hexagon, BLUE payload on the RED triangle -- "never
# lies on a same-colour target"). The colour-blind version of
# _overlaps_committed suppressed KIRMIZI_DIKDORTGEN every time it sat on
# MAVI_ALTIGEN, which is exactly when Görev 3 needs to see it. These four
# cases match the A/B/C/D verification matrix for the fix.

def test_a_same_colour_triangle_rectangle_overlap_still_suppressed():
    """A: same physical object / same colour (KIRMIZI_UCGEN + KIRMIZI_DIKDORTGEN)
    -- the original D2c regression, duplicate suppression must continue."""
    tri = _det("KIRMIZI_UCGEN", (640.0, 480.0), (580.0, 420.0, 700.0, 540.0))
    rect = _det("KIRMIZI_DIKDORTGEN", (641.0, 483.0), (581.0, 421.0, 699.0, 539.0))
    assert HSVContourDetector._overlaps_committed(rect, [tri]) is True


def test_b_different_colour_hexagon_rectangle_overlap_not_suppressed():
    """B: two real, differently-coloured targets in the same region
    (MAVI_ALTIGEN + KIRMIZI_DIKDORTGEN) -- the actual Görev 3 scenario.
    THE fix: both must be preserved, not just one."""
    hexagon = _det("MAVI_ALTIGEN", (640.0, 480.0), (580.0, 420.0, 700.0, 540.0))
    payload = _det("KIRMIZI_DIKDORTGEN", (641.0, 483.0), (581.0, 421.0, 699.0, 539.0))
    assert HSVContourDetector._overlaps_committed(payload, [hexagon]) is False


def test_c_same_colour_hexagon_rectangle_overlap_still_suppressed():
    """C: same physical object / same colour, blue side
    (MAVI_ALTIGEN + MAVI_DIKDORTGEN) -- symmetric to A, must behave the same."""
    hexagon = _det("MAVI_ALTIGEN", (640.0, 480.0), (580.0, 420.0, 700.0, 540.0))
    rect = _det("MAVI_DIKDORTGEN", (641.0, 483.0), (581.0, 421.0, 699.0, 539.0))
    assert HSVContourDetector._overlaps_committed(rect, [hexagon]) is True


def test_d_same_colour_triangle_rectangle_overlap_still_suppressed():
    """D: same physical object / same colour, explicit KIRMIZI_UCGEN +
    KIRMIZI_DIKDORTGEN case named per the verification matrix (duplicate of
    test A's assertion, kept as its own test for direct traceability to the
    matrix this fix was verified against)."""
    tri = _det("KIRMIZI_UCGEN", (300.0, 300.0), (240.0, 240.0, 360.0, 360.0))
    rect = _det("KIRMIZI_DIKDORTGEN", (305.0, 305.0), (245.0, 245.0, 365.0, 365.0))
    assert HSVContourDetector._overlaps_committed(rect, [tri]) is True


def _hexagon_points(center=(640, 480), radius=90):
    return np.array(
        [(int(center[0] + radius * np.cos(np.pi / 3 * i)),
          int(center[1] + radius * np.sin(np.pi / 3 * i))) for i in range(6)],
        dtype=np.int32,
    )


@pytest.mark.asyncio
async def test_dropped_payload_on_arena_target_both_detected_end_to_end():
    """End to end through the real detector: a blue hexagon (arena target)
    with a red rectangle (dropped payload) sitting on top of it, exactly as
    Görev 3 finds it after Payload Mission 1. BEFORE this fix: only
    MAVI_ALTIGEN committed, KIRMIZI_DIKDORTGEN was suppressed every frame
    (reproduced live in SITL). AFTER: both must commit."""
    det = HSVContourDetector()
    frame = np.full((960, 1280, 3), 120, dtype=np.uint8)
    cv2.fillPoly(frame, [_hexagon_points()], (255, 0, 0))  # blue hexagon (arena)
    # Red payload rectangle, smaller, centred on the same spot -- same
    # relative placement as a payload released "HEDEFTE" (on target).
    rect_pts = cv2.boxPoints(((640, 480), (70, 50), 10.0)).astype(np.int32)
    cv2.fillPoly(frame, [rect_pts], (0, 0, 220))  # red

    classes = []
    for _ in range(6):
        classes = [d.shape_type for d in await det.detect(frame)]

    assert "MAVI_ALTIGEN" in classes, classes
    assert "KIRMIZI_DIKDORTGEN" in classes, classes
