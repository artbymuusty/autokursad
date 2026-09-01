"""Visual receiver detection, and the side-wall correction it depends on.

Benchmarked against 66 Gazebo frames whose labels were PROJECTED from
simulator ground-truth poses, never from a detector. Three approaches were
implemented independently and measured on the same frames:

    variant                       det%   mean px   mean cm   ms/frame
    top-face de-shadow (shipped) 100.0      0.63     0.086       7.5
    grey target disc              97.0      0.87     0.131      15.9
    hybrid of the two            100.0      0.97     0.152      29.6
    naive silhouette centre         --     11.59        --        --

With the confidence gate applied: 65/66 trusted, 0.49 px mean, 1.38 px max,
and at pickup altitude 0.068 cm mean / 0.134 cm p95 against the seating
gate's 2.325 cm lateral budget -- about 17x margin.
"""
import math

import cv2
import numpy as np
import pytest

from core.detection.receiver_detector import (
    BANDS, DECK_HEIGHT_M, EXPECTED_ASPECT, MIN_TRUSTED_CONFIDENCE,
    PAYLOAD_LONG_M, RECEIVER_MOUTH_R_M, ReceiverDetection, detect,
)

RED_BGR = (36, 28, 191)
BLUE_BGR = (191, 26, 13)
GREY_BGR = (150, 145, 140)
FOCAL = 539.94
PP = (640.0, 480.0)


def synth_payload(u=640.0, v=480.0, cam_h=0.60, angle=0.0, color=RED_BGR,
                  disc=True, size=(960, 1280)):
    """A payload rendered the way a NADIR pinhole camera actually sees it.

    Both the deck top and the ground footprint are horizontal, so each is the
    same rectangle scaled about the principal point. The footprint scale
    s = d/(d+deck) < 1, so the walls spill INWARD -- reproducing here the very
    bias the detector exists to remove.
    """
    img = np.full((size[0], size[1], 3), 200, np.uint8)
    d = cam_h - DECK_HEIGHT_M
    long_px = PAYLOAD_LONG_M * FOCAL / d
    short_px = long_px / EXPECTED_ASPECT
    s = d / (d + DECK_HEIGHT_M)
    top = cv2.boxPoints(((u, v), (long_px, short_px), angle))
    foot = np.array([[PP[0] + s * (x - PP[0]), PP[1] + s * (y - PP[1])] for x, y in top])
    hull = cv2.convexHull(np.vstack([top, foot]).astype(np.float32)).astype(np.int32)
    cv2.fillPoly(img, [hull], color)                       # silhouette incl. walls
    cv2.fillPoly(img, [top.astype(np.int32)], color)       # deck top
    if disc:
        r = max(2, int(0.006 * FOCAL / (d + 0.027)))
        cv2.circle(img, (int(u), int(v)), r, GREY_BGR, -1)
    return img, long_px


# ------------------------------------------------------------- basic find --

def test_finds_the_payload_and_returns_the_documented_interface():
    img, _ = synth_payload(u=700, v=400)
    d = detect(img, "red")
    assert isinstance(d, ReceiverDetection)
    assert d.center == (d.u, d.v)
    assert 0.0 <= d.confidence <= 1.0
    assert isinstance(d.trusted, bool)


def test_locates_the_top_face_centre_not_the_silhouette_centre():
    """THE regression this detector exists for. The silhouette of a 70 mm tall
    box includes its inward-spilling walls, so the silhouette centre sits
    between the true centre and the principal point. Off-axis, the naive
    estimate was measured at 11.6 px mean / 34 px worst -- larger than the
    23.25 mm mouth it must land inside."""
    u0, v0 = 980.0, 700.0                       # well off the principal point
    img, _ = synth_payload(u=u0, v=v0, cam_h=0.55)
    d = detect(img, "red")
    assert d is not None and d.trusted
    err = math.hypot(d.u - u0, d.v - v0)
    assert err < 4.0, f"{err:.1f} px from truth"

    # and prove the naive estimate really is worse on this same frame
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, np.array((0, 40, 40)), np.array((15, 255, 255))),
        cv2.inRange(hsv, np.array((165, 40, 40)), np.array((180, 255, 255))))
    c = max(cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0],
            key=cv2.contourArea)
    (nx, ny), _, _ = cv2.minAreaRect(c)
    naive = math.hypot(nx - u0, ny - v0)
    assert naive > err, f"naive {naive:.1f} px should be worse than {err:.1f} px"
    # the naive bias points TOWARD the principal point, never away
    assert math.hypot(nx - PP[0], ny - PP[1]) < math.hypot(u0 - PP[0], v0 - PP[1])


def test_on_axis_there_is_no_wall_bias_to_remove():
    """Directly under the camera the walls are hidden, so both estimates agree.
    This is the sanity check on the correction's sign."""
    img, _ = synth_payload(u=PP[0], v=PP[1], cam_h=0.55)
    d = detect(img, "red")
    assert math.hypot(d.u - PP[0], d.v - PP[1]) < 3.0


def test_radius_tracks_apparent_scale_so_callers_can_sanity_check_altitude():
    for cam_h in (0.45, 0.75, 1.20):
        img, long_px = synth_payload(cam_h=cam_h)
        d = detect(img, "red")
        assert d is not None, cam_h
        expected = long_px * (RECEIVER_MOUTH_R_M / PAYLOAD_LONG_M)
        assert d.radius_px == pytest.approx(expected, rel=0.20), cam_h


def test_handles_arbitrary_payload_yaw():
    """The mission never controls payload yaw."""
    for angle in (0, 25, 60, -40, 88):
        img, _ = synth_payload(u=740, v=520, angle=angle)
        d = detect(img, "red")
        assert d is not None, angle
        assert math.hypot(d.u - 740, d.v - 520) < 6.0, angle


# ------------------------------------------------------------ safe refusal --

def test_returns_none_on_an_empty_scene():
    assert detect(np.full((480, 640, 3), 200, np.uint8), "red") is None


def test_returns_none_rather_than_a_guess_on_a_tiny_blob():
    """A wrong centre would steer the aircraft; None only costs a retry."""
    img = np.full((960, 1280, 3), 200, np.uint8)
    cv2.circle(img, (640, 480), 5, RED_BGR, -1)
    assert detect(img, "red") is None


def test_none_input_does_not_raise():
    assert detect(None, "red") is None


def test_unknown_colour_is_a_programming_error_not_a_silent_miss():
    img, _ = synth_payload()
    with pytest.raises(ValueError):
        detect(img, "chartreuse")


def test_red_and_blue_are_selected_independently():
    red_img, _ = synth_payload(color=RED_BGR, disc=False)
    assert detect(red_img, "red") is not None
    assert detect(red_img, "blue") is None
    blue_img, _ = synth_payload(color=BLUE_BGR, disc=False)
    assert detect(blue_img, "blue") is not None


def test_two_payloads_in_frame_do_not_merge_across_colours():
    """Görev 2 flies with both payloads aboard and both may be in view."""
    img, _ = synth_payload(u=420, v=480, color=RED_BGR, disc=False)
    blue, _ = synth_payload(u=900, v=480, color=BLUE_BGR, disc=False)
    img[np.any(blue != 200, axis=2)] = blue[np.any(blue != 200, axis=2)]
    r = detect(img, "red")
    b = detect(img, "blue")
    assert r is not None and b is not None
    assert abs(r.u - 420) < 8 and abs(b.u - 900) < 8


# ------------------------------------------------------------- confidence --

def test_confidence_gate_is_exposed_and_ordered():
    assert 0.0 < MIN_TRUSTED_CONFIDENCE < 1.0
    img, _ = synth_payload()
    d = detect(img, "red")
    assert d.trusted == (d.confidence >= MIN_TRUSTED_CONFIDENCE)


def test_a_payload_truncated_by_the_image_border_is_distrusted():
    """The single worst frame in the 66-frame benchmark (9.91 px) was a payload
    running off the image edge. It scored 0.46 while every good frame scored
    >= 0.75, so the gate -- not the centre -- is what keeps it out of the loop."""
    img, _ = synth_payload(u=1240, v=930, cam_h=0.45)
    d = detect(img, "red")
    if d is not None:
        assert not d.trusted, f"border-truncated payload trusted at {d.confidence:.2f}"


def test_geometry_constants_match_the_cad():
    assert PAYLOAD_LONG_M == pytest.approx(0.142)
    assert RECEIVER_MOUTH_R_M == pytest.approx(0.02325)
    assert DECK_HEIGHT_M == pytest.approx(0.070)
    assert EXPECTED_ASPECT == pytest.approx(0.142 / 0.052)
    assert set(BANDS) == {"red", "blue"}
