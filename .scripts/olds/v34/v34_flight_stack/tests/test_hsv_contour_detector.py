import numpy as np
import cv2
import pytest

from core.detection.hsv_contour_detector import HSVContourDetector
from core.config.parameters import HSV_STREAK_FRAMES


def _frame_with_shapes() -> np.ndarray:
    frame = np.zeros((400, 400, 3), dtype=np.uint8)

    # Pure red (BGR) equilateral-ish triangle, top-left quadrant.
    tri_pts = np.array([[60, 40], [20, 120], [100, 120]], dtype=np.int32)
    cv2.fillPoly(frame, [tri_pts], (0, 0, 255))

    # Pure blue (BGR) regular hexagon, bottom-right quadrant.
    center = (280, 280)
    radius = 70
    hex_pts = np.array(
        [
            (
                int(center[0] + radius * np.cos(np.pi / 3 * i)),
                int(center[1] + radius * np.sin(np.pi / 3 * i)),
            )
            for i in range(6)
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(frame, [hex_pts], (255, 0, 0))

    return frame


@pytest.mark.asyncio
async def test_detects_both_shapes_after_streak_confirmation():
    detector = HSVContourDetector()
    frame = _frame_with_shapes()

    detections = []
    for _ in range(HSV_STREAK_FRAMES):
        detections = await detector.detect(frame)

    shape_types = {d.shape_type for d in detections}
    assert "KIRMIZI_UCGEN" in shape_types
    assert "MAVI_ALTIGEN" in shape_types
    for d in detections:
        assert d.confidence >= 0.7


@pytest.mark.asyncio
async def test_single_frame_not_committed_before_streak():
    detector = HSVContourDetector()
    frame = _frame_with_shapes()

    detections = await detector.detect(frame)

    assert detections == [] or HSV_STREAK_FRAMES <= 1


@pytest.mark.asyncio
async def test_empty_frame_yields_no_detections():
    detector = HSVContourDetector()
    frame = np.zeros((400, 400, 3), dtype=np.uint8)

    detections = []
    for _ in range(HSV_STREAK_FRAMES):
        detections = await detector.detect(frame)

    assert detections == []


def _rotated_rect_points(center, size, angle_deg):
    rect = (center, size, angle_deg)
    return cv2.boxPoints(rect).astype(np.int32)


@pytest.mark.asyncio
async def test_detects_rotated_rectangle_with_orientation():
    """Görev 3 (operatör revizyonu, 2026-08-13): KIRMIZI_DIKDORTGEN tespiti
    rotation_deg doldurmalı, ve bu değer aynı çokgen üzerinde bağımsızca
    çalıştırılan cv2.minAreaRect ile tutarlı olmalı (OpenCV sürüm-özel açı
    kuralına bağlı kalmadan, kendi içinde tutarlılık doğrulaması)."""
    frame = np.zeros((400, 400, 3), dtype=np.uint8)
    center = (200.0, 200.0)
    size = (140.0, 60.0)  # w > h -- long edge is the "width" side
    angle_deg = 25.0
    pts = _rotated_rect_points(center, size, angle_deg)
    cv2.fillPoly(frame, [pts], (0, 0, 255))  # pure red (BGR)

    detector = HSVContourDetector()
    detections = []
    for _ in range(HSV_STREAK_FRAMES):
        detections = await detector.detect(frame)

    rect_dets = [d for d in detections if d.shape_type == "KIRMIZI_DIKDORTGEN"]
    assert len(rect_dets) == 1
    det = rect_dets[0]
    assert det.rotation_deg is not None

    # Ground truth: re-run minAreaRect independently on the same drawn
    # contour, using the exact same w>=h branch logic as _detect_rectangle.
    contour = pts.reshape(-1, 1, 2)
    (_, _), (rw, rh), gt_angle = cv2.minAreaRect(contour)
    expected = float(gt_angle) if rw >= rh else float(gt_angle) + 90.0

    assert abs(det.rotation_deg - expected) < 1.0


@pytest.mark.asyncio
async def test_triangle_and_hexagon_detections_have_no_rotation():
    """rotation_deg is only meaningful for rectangle detections."""
    detector = HSVContourDetector()
    frame = _frame_with_shapes()

    detections = []
    for _ in range(HSV_STREAK_FRAMES):
        detections = await detector.detect(frame)

    for d in detections:
        assert d.shape_type in ("KIRMIZI_UCGEN", "MAVI_ALTIGEN")
        assert d.rotation_deg is None


def _run(coro):
    """detect() is async; these cases need no event loop of their own."""
    import asyncio
    return asyncio.run(coro)


# ------------------------------------------------- clipped-shape rejection --

def test_a_frame_filling_marker_is_not_reported_as_a_rectangle():
    """THE regression, measured by hovering over the arena hexagon.

    The markers are metres across: at the 1.5 m Görev 3 transit altitude the
    5 m blue hexagon covers the whole 3.67 x 2.76 m frame, and a frame-filling
    blob approximates to exactly four corners -- the frame's own. Measured:
    1.5 m reported MAVI_DIKDORTGEN on 8/8 frames while 2.0 m and 2.5 m
    correctly reported MAVI_ALTIGEN on every frame. That false rectangle
    crowds out the small payload the phase is hunting, and Görev 3 Faz 1 then
    fails with "Kırmızı Dikdörtgen bulunamadı" while sitting on top of it.
    """
    import cv2
    import numpy as np

    from core.detection.hsv_contour_detector import HSVContourDetector

    det = HSVContourDetector()
    # A blue field covering the entire frame, as the hexagon does from 1.5 m.
    img = np.zeros((960, 1280, 3), np.uint8)
    img[:, :] = (191, 26, 13)          # BGR, the payload/marker blue
    found = {d.shape_type for d in _run(det.detect(img))}
    assert "MAVI_DIKDORTGEN" not in found, found


def test_a_payload_sized_rectangle_well_inside_the_frame_is_still_found():
    """The rejection must not cost a real detection. A payload is 111 px long
    at 0.90 m and 170 px at the 0.45 m release altitude -- it never reaches
    the border at any altitude the mission uses."""
    import cv2
    import numpy as np

    from core.detection.hsv_contour_detector import HSVContourDetector

    det = HSVContourDetector()
    img = np.full((960, 1280, 3), 200, np.uint8)
    cv2.rectangle(img, (560, 440), (720, 500), (191, 26, 13), -1)
    found = {}
    for _ in range(4):                 # the detector requires a streak
        for d in _run(det.detect(img)):
            found[d.shape_type] = found.get(d.shape_type, 0) + 1
    assert "MAVI_DIKDORTGEN" in found, found


def test_border_predicate_is_exact_about_what_counts_as_clipped():
    import numpy as np

    from core.detection.hsv_contour_detector import HSVContourDetector

    full = np.array([[[0, 0]], [[1279, 0]], [[1279, 959]], [[0, 959]]], np.int32)
    inner = np.array([[[400, 400]], [[700, 400]], [[700, 520]], [[400, 520]]], np.int32)
    assert HSVContourDetector._touches_border(full, (960, 1280))
    assert not HSVContourDetector._touches_border(inner, (960, 1280))
