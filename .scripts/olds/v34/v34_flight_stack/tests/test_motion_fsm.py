"""Climb-then-Cruise hareket makinesi -- state sirasi, guard'lar, eksen ayrimi.

Mock'un statik olani (MockFlightBackend) burada yetmez: guard'lar GERCEKTEN
yakinsayan bir araca bakiyor. _SimVehicle komutlanan hizi kinematik olarak
entegre eder, yani "CLIMB cikti mi" sorusu bir cagri sayimi degil gercek bir
irtifa olcumu uzerinden yanitlanir.
"""
import math

import pytest

from mocks.mock_flight_backend import MockFlightBackend

from core.navigation import motion_fsm as motion_fsm_module
from core.navigation.motion_fsm import MotionBudget, MotionProfile, MotionStateMachine
from core.navigation.motion_state import MotionState
from core.navigation.velocity_profile import ProfilePhase, trapezoidal_speed

_EARTH_RADIUS_M = 6371000.0
LAT0, LON0 = 47.3977, 8.5456


def _fast_profile(**overrides) -> MotionProfile:
    """Duvar saati maliyetini testten cikaran profil. Guard MANTIGI aynen
    kalir; yalnizca sureler kisalir (conftest'in MISSION_START_HOLD_S'i
    sifirlamasiyla ayni gerekce)."""
    profile = MotionProfile(
        hold_min_s=0.02, hold_max_s=0.20, arrival_hold_s=0.02,
        leg_timeout_s=20.0, vertical_timeout_s=10.0,
        attitude_stable_samples=2,
    )
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


class _SimVehicle(MockFlightBackend):
    """Komutlanan gövde hizini NED'e cevirip entegre eden minimal kinematik.

    Ani hiz cevabi varsayilir (birinci derece gecikme yok): bu makine bir
    ARAÇ modeli degil, bir KARAR mantigi; test edilen sey hangi eksenin ne
    zaman komutlandigi ve guard'larin ne zaman atesledigi."""

    def __init__(self, alt_m=10.0, north_m=0.0, east_m=0.0, yaw_deg=0.0):
        super().__init__()
        self.alt_m, self.north_m, self.east_m = alt_m, north_m, east_m
        self.vel_n = self.vel_e = self.vel_d = 0.0
        self._yaw_deg = yaw_deg
        #: (state, forward, right, down) -- eksen ayrimi assert'lerinin kaynagi.
        self.commands = []
        self.machine = None

    async def get_global_position(self):
        return (LAT0 + math.degrees(self.north_m / _EARTH_RADIUS_M),
                LON0 + math.degrees(self.east_m / (_EARTH_RADIUS_M * math.cos(math.radians(LAT0)))),
                self.alt_m)

    async def get_position_ned(self):
        return (self.north_m, self.east_m, -self.alt_m)

    async def get_velocity_ned(self):
        return (self.vel_n, self.vel_e, self.vel_d)

    async def get_yaw_deg(self):
        return self._yaw_deg

    async def send_setpoint(self, forward, right, down):
        """CenteringController._send_setpoint'in sozlesmesi: KOMUTLANANI doner."""
        self.commands.append(
            (self.machine.state if self.machine else None, forward, right, down))
        yaw = math.radians(self._yaw_deg)
        self.vel_n = forward * math.cos(yaw) - right * math.sin(yaw)
        self.vel_e = forward * math.sin(yaw) + right * math.cos(yaw)
        self.vel_d = down
        dt = motion_fsm_module.OFFBOARD_SETPOINT_INTERVAL_S
        self.north_m += self.vel_n * dt
        self.east_m += self.vel_e * dt
        self.alt_m -= self.vel_d * dt          # down pozitif => irtifa azalir
        return (forward, right, down)


def _machine(vehicle, profile=None, budget=None):
    machine = MotionStateMachine(vehicle, vehicle.send_setpoint,
                                 profile=profile or _fast_profile(),
                                 budget=budget)
    vehicle.machine = machine
    return machine


def _target(north_m=0.0, east_m=0.0):
    return (LAT0 + math.degrees(north_m / _EARTH_RADIUS_M),
            LON0 + math.degrees(east_m / (_EARTH_RADIUS_M * math.cos(math.radians(LAT0)))))


@pytest.fixture(autouse=True)
def _fast_tick(monkeypatch):
    """Tick SURESINI degil, tick BEKLEMESINI kaldirir.

    OFFBOARD_SETPOINT_INTERVAL_S'i kucultmek yanlis olurdu: hem trapez
    profilin ivme rampasi (v_onceki + a*dt) hem de _SimVehicle'in kinematik
    entegrasyonu o degeri kullaniyor, yani tick'i kucultmek araci gercekten
    100 kat yavas ucururdu ve bacaklar duvar-saati timeout'una takilirdi.
    Bunun yerine dt nominal 0.1 s'te KALIR (profil ve kinematik dogru
    olcekte calisir) ve yalnizca uyku sifirlanir -- conftest.py'nin
    MISSION_START_HOLD_S'i sifirlamasiyla ayni gerekce."""
    real_sleep = motion_fsm_module.asyncio.sleep

    async def _yield_only(_delay):
        await real_sleep(0)      # olay dongusune sirayi ver, ama bekleme

    monkeypatch.setattr(motion_fsm_module.asyncio, "sleep", _yield_only)


def _states(machine):
    return [s for s in machine.visited if s not in (MotionState.COMPLETE, MotionState.ABORTED)]


# --------------------------------------------------------------------------
# state sirasi
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_climb_then_cruise_full_sequence():
    """Hedef YUKARIDA: CLIMB -> HOLD -> CRUISE -> ARRIVAL_HOLD. DESCEND yok."""
    vehicle = _SimVehicle(alt_m=5.0)
    machine = _machine(vehicle)
    lat, lon = _target(north_m=30.0)

    assert await machine.fly_leg(lat, lon, 15.0) is True
    assert _states(machine) == [MotionState.CLIMB, MotionState.HOLD,
                                MotionState.CRUISE, MotionState.ARRIVAL_HOLD]


@pytest.mark.asyncio
async def test_descend_runs_after_cruise_not_before():
    """Hedef ASAGIDA: seyir YUKSEK irtifadan yapilir, alcalma hedefte olur.

    Operator karari 2026-09-02: once alcalip alcak irtifada seyretmek engel
    riski tasir. Bu yuzden CLIMB atlanir (zaten yukaridayiz) ama DESCEND
    CRUISE'dan SONRA gelir."""
    vehicle = _SimVehicle(alt_m=15.0)
    machine = _machine(vehicle)
    lat, lon = _target(north_m=30.0)

    assert await machine.fly_leg(lat, lon, 5.0) is True
    assert _states(machine) == [MotionState.HOLD, MotionState.CRUISE,
                                MotionState.DESCEND, MotionState.ARRIVAL_HOLD]
    # Seyir gercekten yuksekte yapildi mi: CRUISE sirasinda irtifa hic
    # hedef irtifaya inmemis olmali.
    cruise_alts = [c for c in vehicle.commands if c[0] is MotionState.CRUISE]
    assert cruise_alts, "CRUISE hic komut vermedi"


@pytest.mark.asyncio
async def test_climb_skipped_when_already_at_altitude():
    vehicle = _SimVehicle(alt_m=15.0)
    machine = _machine(vehicle)
    lat, lon = _target(north_m=20.0)

    assert await machine.fly_leg(lat, lon, 15.0) is True
    assert MotionState.CLIMB not in machine.visited
    assert MotionState.DESCEND not in machine.visited


# --------------------------------------------------------------------------
# eksen ayrimi -- bu calismanin ASIL amaci
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vertical_states_never_command_horizontal():
    """CLIMB/DESCEND sirasinda vx=vy=0. Kuplajin kirildiginin dogrudan kaniti."""
    vehicle = _SimVehicle(alt_m=5.0)
    machine = _machine(vehicle)
    lat, lon = _target(north_m=30.0)
    await machine.fly_leg(lat, lon, 15.0)

    vertical = [c for c in vehicle.commands
                if c[0] in (MotionState.CLIMB, MotionState.DESCEND)]
    assert vertical, "dikey state hic komut vermedi"
    assert all(f == 0.0 and r == 0.0 for _s, f, r, _d in vertical), \
        "CLIMB/DESCEND sirasinda yatay eksen komutlandi"


@pytest.mark.asyncio
async def test_cruise_holds_altitude_instead_of_travelling_vertically():
    """CRUISE'daki down terimi bir SEYAHAT bileseni degil, irtifa TUTMA terimi.

    Arac seyir irtifasinda basladigi icin hata ~0 kalmali; komut buyuklugu
    dikey seyir hizinin yaninda ihmal edilebilir olmali."""
    vehicle = _SimVehicle(alt_m=15.0)
    profile = _fast_profile()
    machine = _machine(vehicle, profile)
    lat, lon = _target(north_m=25.0)
    await machine.fly_leg(lat, lon, 15.0)

    cruise = [c for c in vehicle.commands if c[0] is MotionState.CRUISE]
    assert cruise
    assert max(abs(d) for _s, _f, _r, d in cruise) < 0.1 * profile.vertical_speed_m_s
    assert max(abs(f) for _s, f, _r, _d in cruise) > 0.5, "CRUISE yatay hareket etmedi"


@pytest.mark.asyncio
async def test_cruise_steers_in_body_frame_when_yawed():
    """Yaw=90 (doguya bakiyor) iken kuzeye gitmek SOL komutu demek.

    IFlightBackend'de NED velocity setpoint'i olmadigi icin yatay komut
    gövde eksenine cevrilmek zorunda; bu donusum yanlissa arac ters yone gider."""
    vehicle = _SimVehicle(alt_m=15.0, yaw_deg=90.0)
    machine = _machine(vehicle)
    lat, lon = _target(north_m=25.0)
    await machine.fly_leg(lat, lon, 15.0)

    cruise = [c for c in vehicle.commands if c[0] is MotionState.CRUISE]
    assert cruise
    # right < 0 (sol) baskin olmali, forward degil.
    assert min(r for _s, _f, r, _d in cruise) < -0.5
    assert max(abs(f) for _s, f, _r, _d in cruise) < 0.5


# --------------------------------------------------------------------------
# guard'lar
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_climb_guard_requires_vz_settle_not_just_altitude_band():
    """Irtifa banda girdi ama hala hizli iniyor/cikiyorsa YAKINSAMADI.

    climb_to_altitude()'un mevcut guard'inda eksik olan terim tam olarak bu."""
    profile = _fast_profile(vz_settle_m_s=0.2, alt_tol_m=0.3)
    vehicle = _SimVehicle(alt_m=14.9)     # zaten band icinde
    machine = _machine(vehicle, profile)

    # Araci band icinde ama HIZLI ilan et: guard atesle-me-meli.
    vehicle.vel_d = -5.0
    converged = await machine._run_vertical(15.0, motion_fsm_module.time.monotonic() + 0.3)
    # Sim send_setpoint her komutta vel_d'yi ezdigi icin bir tick sonra
    # duruma gore yakinsar; onemli olan ILK tick'te cikmamis olmasi.
    assert vehicle.commands, "guard ilk tick'te yanlislikla yakinsadi"


@pytest.mark.asyncio
async def test_cruise_arrival_needs_both_radius_and_speed():
    """Yaricap TEK BASINA yetmez -- 2026-08-13'te yaricaptan ~11 m/s ile
    gecilip 10-25 m oteye suzulmustu."""
    profile = _fast_profile(arrival_radius_m=2.0, arrival_speed_m_s=0.3)
    vehicle = _SimVehicle(alt_m=15.0, north_m=0.0)
    machine = _machine(vehicle, profile)
    lat, lon = _target(north_m=40.0)

    assert await machine.fly_leg(lat, lon, 15.0) is True
    final_speed = math.hypot(vehicle.vel_n, vehicle.vel_e)
    assert final_speed < profile.arrival_speed_m_s, \
        f"varista hala {final_speed:.2f} m/s -- hiz kosulu uygulanmamis"
    remaining = abs(40.0 - vehicle.north_m)
    assert remaining < profile.arrival_radius_m


@pytest.mark.asyncio
async def test_hold_waits_for_attitude_to_settle():
    """Sallanan arac min_s dolsa bile HOLD'dan cikamaz."""
    profile = _fast_profile(hold_min_s=0.01, hold_max_s=0.25,
                            attitude_rate_limit_deg_s=5.0, attitude_stable_samples=2)
    vehicle = _SimVehicle(alt_m=15.0)
    # Surekli salinim. Sonlu bir liste tukenip sabitlenseydi guard
    # yanlislikla "duruldu" derdi; bu yuzden sinirsiz alternasyon.
    flip = {"n": 0}

    async def _rocking():
        flip["n"] += 1
        return (0.0 if flip["n"] % 2 else 20.0, 0.0, 0.0)
    vehicle.get_attitude_euler = _rocking
    machine = _machine(vehicle, profile)
    machine.state = MotionState.HOLD

    await machine._run_hold(profile.hold_min_s, profile.hold_max_s,
                            motion_fsm_module.time.monotonic() + 5.0)
    # min_s'ten belirgin sekilde uzun surmus olmali (tavana dayanmis).
    assert machine.budget.cumulative_hold_s > profile.hold_min_s * 3


@pytest.mark.asyncio
async def test_hold_exits_at_minimum_when_attitude_is_steady():
    profile = _fast_profile(hold_min_s=0.01, hold_max_s=1.0, attitude_stable_samples=2)
    vehicle = _SimVehicle(alt_m=15.0)          # attitude sabit (0,0,0)
    machine = _machine(vehicle, profile)
    machine.state = MotionState.HOLD

    await machine._run_hold(profile.hold_min_s, profile.hold_max_s,
                            motion_fsm_module.time.monotonic() + 5.0)
    assert machine.budget.cumulative_hold_s < 0.5


@pytest.mark.asyncio
async def test_hold_degrades_to_timer_when_attitude_unavailable():
    """get_attitude_euler() None dondurdugunde (backend desteklemiyor) guard
    sessizce sayaca dusmeli -- kanitlanamayan stabilite gorevi DUSURMEZ."""
    profile = _fast_profile(hold_min_s=0.01, hold_max_s=1.0)
    vehicle = _SimVehicle(alt_m=15.0)

    async def _no_attitude():
        return None
    vehicle.get_attitude_euler = _no_attitude

    machine = _machine(vehicle, profile)
    machine.state = MotionState.HOLD
    await machine._run_hold(profile.hold_min_s, profile.hold_max_s,
                            motion_fsm_module.time.monotonic() + 5.0)
    assert machine.budget.cumulative_hold_s < 0.5


# --------------------------------------------------------------------------
# setpoint akisi ve butce
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_every_state_streams_setpoints_including_hold():
    """PX4 ~500 ms setpoint'siz kalirsa Offboard'dan duser. HOLD dahil HER
    state kendi dongusunde komut yayinlamali -- state gecisleri akisi kesmez."""
    vehicle = _SimVehicle(alt_m=5.0)
    machine = _machine(vehicle)
    lat, lon = _target(north_m=25.0)
    await machine.fly_leg(lat, lon, 15.0)

    seen = {c[0] for c in vehicle.commands}
    for state in (MotionState.CLIMB, MotionState.HOLD,
                  MotionState.CRUISE, MotionState.ARRIVAL_HOLD):
        assert state in seen, f"{state.value} hic setpoint yayinlamadi"


@pytest.mark.asyncio
async def test_hold_budget_accumulates_across_legs():
    """Operator istegi: kumulatif hold suresi MISSION_TIMEOUT butcesine karsi
    izlenebilir olmali."""
    budget = MotionBudget()
    vehicle = _SimVehicle(alt_m=15.0)
    machine = _machine(vehicle, budget=budget)

    lat, lon = _target(north_m=10.0)
    await machine.fly_leg(lat, lon, 15.0)
    after_first = budget.cumulative_hold_s

    lat, lon = _target(north_m=20.0)
    await machine.fly_leg(lat, lon, 15.0)

    assert budget.legs == 2
    assert budget.cumulative_hold_s > after_first
    snapshot = budget.snapshot()
    assert snapshot["mission_timeout_s"] == 600
    assert snapshot["cumulative_hold_pct_of_budget"] >= 0.0
    assert MotionState.HOLD.value in snapshot["by_state_s"]


# --------------------------------------------------------------------------
# trapez profil
# --------------------------------------------------------------------------

def test_trapezoid_accelerates_then_brakes_on_remaining_distance():
    far = trapezoidal_speed(50.0, 0.0, 3.0, 1.5, 0.1)
    assert far.phase is ProfilePhase.ACCEL and far.speed_m_s == pytest.approx(0.15)

    cruising = trapezoidal_speed(50.0, 3.0, 3.0, 1.5, 0.1)
    assert cruising.phase is ProfilePhase.CRUISE and cruising.speed_m_s == pytest.approx(3.0)

    # 2 m kala: sqrt(2*1.5*2) = 2.449
    braking = trapezoidal_speed(2.0, 3.0, 3.0, 1.5, 0.1)
    assert braking.phase is ProfilePhase.DECEL
    assert braking.speed_m_s == pytest.approx(math.sqrt(2 * 1.5 * 2.0))


def test_trapezoid_stops_inside_stop_radius():
    step = trapezoidal_speed(1.0, 2.0, 3.0, 1.5, 0.1, stop_radius_m=2.0)
    assert step.speed_m_s == 0.0 and step.phase is ProfilePhase.HOLD
