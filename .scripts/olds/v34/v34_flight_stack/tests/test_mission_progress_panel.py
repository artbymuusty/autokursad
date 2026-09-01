"""The right-hand MISSION PROGRESS panel.

It exists because the pre-existing EVENT TIMELINE could not answer "where is
the mission now": snap.recent_events is a bounded ring (RECENT_EVENTS_MAX=80)
dominated by VEHICLE_TELEMETRY and WATCHDOG_UPDATED. Measured on a real 600 s
run, 4274 events contained only 79 MISSION_PHASE_CHANGED, and the last-80
window spanned 46.8 s with a single phase change in it. Phase transitions were
evicted within seconds of happening.

The panel therefore reads a SEPARATE, unbounded-in-practice phase_history that
the aggregator fills from MISSION_PHASE_CHANGED only, so telemetry noise can
never evict mission progress.
"""
import time

import numpy as np
import pytest

from core.telemetry.aggregator import RuntimeStateAggregator
from core.telemetry.dashboard import (
    MissionOpsDashboard, PROGRESS_COLUMN_WIDTH, collapse_phase_history,
)
from core.telemetry.events import Category, Event, Severity
from core.telemetry.snapshot import MissionSnapshot, PhaseTransition


def _phase_event(frm, to, reason, dur=1.0):
    return Event(code="MISSION_PHASE_CHANGED", subsystem="MissionContext",
                 category=Category.LIFECYCLE, severity=Severity.INFO,
                 message=f"{frm} -> {to} ({reason})",
                 data={"from_phase": frm, "to_phase": to, "reason": reason,
                       "previous_phase_duration_s": dur})


def _noise(n):
    return [Event(code="VEHICLE_TELEMETRY", subsystem="t", category=Category.TELEMETRY,
                  severity=Severity.INFO, message="", data={}) for _ in range(n)]


def _transitions(spec, t0=1000.0, step=5.0):
    return [PhaseTransition(from_phase=a, to_phase=b, reason=r,
                            ts=t0 + i * step, duration_s=step)
            for i, (a, b, r) in enumerate(spec)]


def _panel():
    d = MissionOpsDashboard.__new__(MissionOpsDashboard)
    d.progress_col_width = PROGRESS_COLUMN_WIDTH
    return d


# ------------------------------------------------------------ aggregation --

def test_phase_transitions_are_recorded_in_order_with_their_fields():
    agg = RuntimeStateAggregator()
    for frm, to, reason in (("IDLE", "ARMED", "start"),
                            ("ARMED", "TAKEOFF", "climb"),
                            ("TAKEOFF", "SEARCHING", "route")):
        agg.on_event(_phase_event(frm, to, reason))
    hist = agg.snapshot().phase_history
    assert [h.to_phase for h in hist] == ["ARMED", "TAKEOFF", "SEARCHING"]
    assert [h.from_phase for h in hist] == ["IDLE", "ARMED", "TAKEOFF"]
    assert [h.reason for h in hist] == ["start", "climb", "route"]
    assert all(h.ts > 0 for h in hist)
    # strictly non-decreasing in time -- the panel renders in this order
    assert hist == sorted(hist, key=lambda h: h.ts)


def test_telemetry_noise_cannot_evict_mission_progress():
    """THE regression this panel exists for. recent_events holds 80; a real
    run puts thousands of telemetry events between two phase changes."""
    agg = RuntimeStateAggregator()
    agg.on_event(_phase_event("IDLE", "ARMED", "start"))
    for e in _noise(200):
        agg.on_event(e)
    agg.on_event(_phase_event("ARMED", "TAKEOFF", "climb"))

    snap = agg.snapshot()
    assert [h.to_phase for h in snap.phase_history] == ["ARMED", "TAKEOFF"]
    # Prove the ring really did overflow, so the test is meaningful: the
    # FIRST transition happened 200 events ago and is gone from recent_events,
    # yet phase_history still has it. (The second one is the newest event of
    # all, so it is naturally still in the ring -- that is not the case under
    # test.)
    assert len(snap.recent_events) <= 80
    ring_msgs = [e.message for e in snap.recent_events]
    assert not any("IDLE -> ARMED" in m for m in ring_msgs), \
        "the first transition should have been evicted from recent_events"
    assert snap.phase_history[0].to_phase == "ARMED", \
        "but it must survive in phase_history"


def test_phase_history_is_not_the_recent_events_ring():
    agg = RuntimeStateAggregator()
    for i in range(120):
        agg.on_event(_phase_event(f"P{i}", f"P{i+1}", "step"))
    snap = agg.snapshot()
    assert len(snap.phase_history) == 120, "phase history must outlive the 80-event ring"


# -------------------------------------------------------------- collapsing --

def test_repeated_identical_transitions_are_run_length_collapsed():
    """A centering retry loop legitimately repeats. 13 identical lines would
    push everything else off a ~60-row panel, so they collapse to one row
    carrying a count -- collapsed, never hidden."""
    hist = _transitions([("A", "SEARCHING", "centering_timed_out")] * 13)
    rows = collapse_phase_history(hist)
    assert len(rows) == 1
    assert rows[0].to_phase == "SEARCHING"
    assert rows[0].count == 13
    assert rows[0].first_ts < rows[0].last_ts


def test_same_phase_with_a_different_reason_is_not_collapsed():
    """transition_to() does not guard phase == previous: Görev 3 fires three
    consecutive GOREV3_RUNNING transitions distinguished only by `reason`.
    Collapsing on phase alone would erase the whole of Görev 3."""
    hist = _transitions([("X", "GOREV3_RUNNING", "pickup"),
                         ("X", "GOREV3_RUNNING", "transport"),
                         ("X", "GOREV3_RUNNING", "redrop")])
    rows = collapse_phase_history(hist)
    assert len(rows) == 3
    assert [r.reason for r in rows] == ["pickup", "transport", "redrop"]
    assert all(r.count == 1 for r in rows)


def test_collapsing_preserves_chronological_order():
    hist = _transitions([("A", "SEARCHING", "r1"), ("A", "SEARCHING", "r1"),
                         ("A", "TRACKING", "r2"), ("A", "SEARCHING", "r1")])
    rows = collapse_phase_history(hist)
    assert [(r.to_phase, r.count) for r in rows] == [
        ("SEARCHING", 2), ("TRACKING", 1), ("SEARCHING", 1)]


def test_empty_history_collapses_to_nothing():
    assert collapse_phase_history([]) == []


# ----------------------------------------------------------------- render --

def test_panel_has_the_declared_width_and_matches_the_camera_height():
    snap = MissionSnapshot()
    snap.phase_history = _transitions([("IDLE", "ARMED", "start")])
    for height in (480, 960):
        img = _panel()._build_progress_column(snap, height=height)
        assert img.shape == (height, PROGRESS_COLUMN_WIDTH, 3), img.shape
        assert img.dtype == np.uint8


def test_panel_renders_before_any_transition_has_happened():
    """The dashboard opens before the mission arms; an empty history must not
    raise, because _render has no fallback that would keep the window alive."""
    img = _panel()._build_progress_column(MissionSnapshot(), height=960)
    assert img.shape == (960, PROGRESS_COLUMN_WIDTH, 3)


def test_panel_is_not_blank_once_there_is_progress():
    snap = MissionSnapshot()
    snap.phase_history = _transitions(
        [("IDLE", "ARMED", "start"), ("ARMED", "TAKEOFF", "climb")])
    snap.elapsed_s = 42.0
    img = _panel()._build_progress_column(snap, height=960)
    assert len(np.unique(img.reshape(-1, 3), axis=0)) > 3, "panel drew nothing"


def test_panel_survives_far_more_transitions_than_it_can_show():
    """A 600 s run produced 79 transitions against roughly 60 renderable rows.
    The panel must clip, not crash, and must keep the NEWEST rows."""
    snap = MissionSnapshot()
    snap.phase_history = _transitions(
        [(f"P{i}", f"P{i+1}", f"r{i}") for i in range(300)])
    img = _panel()._build_progress_column(snap, height=960)
    assert img.shape == (960, PROGRESS_COLUMN_WIDTH, 3)


def test_glyphs_are_ascii_so_hershey_fonts_can_render_them():
    """cv2.putText uses Hershey fonts, which have no Unicode coverage: a check
    mark or arrow renders as '?'. Everything the panel draws must be ASCII."""
    import inspect
    from core.telemetry import dashboard as dash
    src = inspect.getsource(dash._build_progress_column) \
        if hasattr(dash, "_build_progress_column") \
        else inspect.getsource(dash.MissionOpsDashboard._build_progress_column)
    assert src.isascii(), "non-ASCII glyph in the progress panel renderer"
