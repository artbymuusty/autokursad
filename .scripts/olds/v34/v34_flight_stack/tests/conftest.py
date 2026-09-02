"""Shared test configuration.

ADR-007 introduced MISSION_START_HOLD_S: a real-flight settling delay between
reaching mission altitude and issuing the mission start. It is a wall-clock
sleep inside Gorev2Orchestrator.run(), so at its production value (3.0s) it
would be paid by EVERY test that drives the orchestrator -- and it silently
broke the time-bounded lifecycle tests, whose _run_bounded() helper marks the
mission finished after 0.4s: the route "completed" during the hold, before the
search phase ever began.

Zeroed here so tests measure mission BEHAVIOUR rather than startup timing.
The hold's own behaviour stays covered by
test_gorev2_route_confirmation.py::test_adr007_start_sequence_holds_before_starting,
which sets it explicitly and asserts the sequence.
"""
import pytest

from core.config import parameters


@pytest.fixture(autouse=True)
def _no_mission_start_hold(monkeypatch):
    monkeypatch.setattr(parameters, "MISSION_START_HOLD_S", 0.0)


@pytest.fixture(autouse=True)
def _no_mission_resume_spacing(monkeypatch):
    """ADR-009 PX4-STABILITY added MISSION_RESUME_MIN_INTERVAL_S (15s) and a
    MISSION-mode confirmation to _resume_mission_route(). Both are
    real-flight protections measured against PX4 SITL, and both are pure
    wall-clock cost in a test -- 15s per resume dominates every
    time-bounded lifecycle test exactly the way MISSION_START_HOLD_S did.

    Patched on the ORCHESTRATOR module, not on `parameters`: the values are
    imported by value there. Tests that assert the spacing/confirm
    behaviour set their own values (see
    test_adr009_stale_health_backoff_speed.py)."""
    import core.mission.gorev2_orchestrator as gorev2_orchestrator
    monkeypatch.setattr(gorev2_orchestrator, "MISSION_RESUME_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(gorev2_orchestrator, "MISSION_MODE_CONFIRM_TIMEOUT_S", 1.0)


@pytest.fixture(autouse=True)
def _fast_motion_profile(monkeypatch):
    """Climb-then-Cruise'un DUVAR-SAATI maliyetlerini testten çıkarır.

    Üretim profili her bacağa gerçek zaman ekler: hold_min 0.3 s +
    arrival_hold 1.0 s, ve yakınsamayan bir bacak leg_timeout_s = 60 s
    bekler. MockFlightBackend statiktir (komut verilince hareket etmez), yani
    CRUISE onunla hiçbir zaman yakınsayamaz -- ölçüldü: bu fixture olmadan
    test_mission_lifecycle_spec.py tek başına dakikalara çıkıyor.

    Bu, MISSION_START_HOLD_S ve MISSION_RESUME_MIN_INTERVAL_S için yukarıda
    yapılanın aynısı ve aynı gerekçeyle: testler zamanlamayı değil DAVRANIŞI
    ölçmeli.

    Guard MANTIĞI dokunulmadan kalır -- yalnızca süreler kısalır.
    test_motion_fsm.py bu değerlere hiç güvenmez, kendi profilini açıkça
    kurar ve eşikleri orada zorlar.

    parameters ÜZERİNDE patch'leniyor (orchestrator modülü üzerinde değil):
    MotionProfile alanları default_factory ile bu modülü ÖRNEKLEME anında
    okur, tam da bunun mümkün olması için."""
    monkeypatch.setattr(parameters, "MOTION_HOLD_MIN_S", 0.0)
    monkeypatch.setattr(parameters, "MOTION_HOLD_MAX_S", 0.05)
    monkeypatch.setattr(parameters, "MOTION_ARRIVAL_HOLD_S", 0.0)
    monkeypatch.setattr(parameters, "MOTION_LEG_TIMEOUT_S", 1.0)
    monkeypatch.setattr(parameters, "MOTION_VERTICAL_TIMEOUT_S", 0.5)
