"""Climb-then-Cruise hareket makinesi.

NE COZUYOR: goto_global_position_and_wait() hedefe MUTLAK 3B pozisyon
setpoint'i gonderiyordu -- goto_position_ned(target_n, target_e,
-target_alt_m, yaw) -- yani X, Y ve Z ayni anda hareket ediyordu. Bu makine
onu bes state'e ayirir:

    CLIMB -> HOLD -> CRUISE -> DESCEND -> ARRIVAL_HOLD

CLIMB ve DESCEND kosulludur (irtifa farki tolerans altindaysa atlanir).
HOLD her zaman calisir: bacak, az once merkezleme yapmis ve hala sallanan bir
araclda baslayabilir; min 0.3 s ucuz, guard zaten durgunsa hemen cikar.

NE YAPMAZ:
  * go_to_and_center()'a DOKUNMAZ. Onun uc eksenli kuplaji kasitli ve
    ADR-009/ADR-010'da olculmus (kademeli inis alcalirken merkezler).
    ARRIVAL_HOLD bittikten sonra kontrol cagirana geri doner, merkezleme
    onun isidir.
  * Yeni bir setpoint yolu ACMAZ. Her komut cagirandan gelen `send_setpoint`
    uzerinden gider; CenteringController bunu kendi _send_setpoint'ine
    baglar, yani ADR-010 P4'un SetpointLimiter'i atlanmaz.
  * goto_global_position_and_wait()'i DEGISTIRMEZ ya da silmez. O metot
    oldugu gibi duruyor ve MOTION_FSM_ENABLED=False iken geri donus yolu.

SETPOINT BOSLUGU: PX4 ~500 ms setpoint'siz kalirsa Offboard'dan duser (bu kod
tabaninda en az dort ayri BUG FIX bunun kaydidir). State GECISLERI bu yuzden
akisi kesmez: her state kendi dongusunde OFFBOARD_SETPOINT_INTERVAL_S'te
komut yayinlar ve bir sonraki state ayni cagri zincirinde hemen devralir --
aralarinda await sleep YOKTUR.
"""
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.config.parameters import (
    GOREV2_MAX_FLIGHT_DURATION_S,
    MOTION_ACCEL_M_S2,
    MOTION_ALT_TOL_M,
    MOTION_ARRIVAL_HOLD_S,
    MOTION_ARRIVAL_RADIUS_M,
    MOTION_ARRIVAL_SPEED_M_S,
    MOTION_ATTITUDE_RATE_LIMIT_DEG_S,
    MOTION_ATTITUDE_STABLE_SAMPLES,
    MOTION_CRUISE_SPEED_M_S,
    MOTION_FSM_ENABLED,
    MOTION_HOLD_MAX_S,
    MOTION_HOLD_MIN_S,
    MOTION_LEG_TIMEOUT_S,
    MOTION_VERTICAL_SPEED_M_S,
    MOTION_VERTICAL_TIMEOUT_S,
    MOTION_VZ_SETTLE_M_S,
    OFFBOARD_SETPOINT_INTERVAL_S,
)
from core.interfaces.i_flight_backend import IFlightBackend, TelemetryStale
from core.navigation.geo import gps_to_ned_delta, haversine_distance_m
from core.navigation.motion_state import MotionState
from core.navigation.velocity_profile import (
    ned_to_body,
    split_horizontal,
    trapezoidal_speed,
)
from core.telemetry.event_bus import NULL_PUBLISHER, EventPublisher
from core.telemetry.events import Category, Event, Severity

logger = logging.getLogger(__name__)


@dataclass
class MotionProfile:
    """Bir bacagin tum esikleri. Tamami YAML'dan ezilebilir (control_gains
    ile ayni desen); buradaki varsayilanlar parameters.py'den gelir."""
    enabled: bool = MOTION_FSM_ENABLED
    alt_tol_m: float = MOTION_ALT_TOL_M
    vz_settle_m_s: float = MOTION_VZ_SETTLE_M_S
    hold_min_s: float = MOTION_HOLD_MIN_S
    hold_max_s: float = MOTION_HOLD_MAX_S
    attitude_rate_limit_deg_s: float = MOTION_ATTITUDE_RATE_LIMIT_DEG_S
    attitude_stable_samples: int = MOTION_ATTITUDE_STABLE_SAMPLES
    arrival_radius_m: float = MOTION_ARRIVAL_RADIUS_M
    arrival_speed_m_s: float = MOTION_ARRIVAL_SPEED_M_S
    cruise_speed_m_s: float = MOTION_CRUISE_SPEED_M_S
    accel_m_s2: float = MOTION_ACCEL_M_S2
    vertical_speed_m_s: float = MOTION_VERTICAL_SPEED_M_S
    leg_timeout_s: float = MOTION_LEG_TIMEOUT_S
    vertical_timeout_s: float = MOTION_VERTICAL_TIMEOUT_S
    arrival_hold_s: float = MOTION_ARRIVAL_HOLD_S

    @classmethod
    def from_config(cls, config: Optional[dict]) -> "MotionProfile":
        """YAML'daki `motion_profile` blogundan uretir. Blok yoksa ya da bir
        anahtar eksikse o alan parameters.py varsayilaninda kalir -- config
        dosyasi eksik diye ucus mantigi degismez."""
        profile = cls()
        if not config:
            return profile
        for key, value in config.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
            else:
                logger.warning("motion_profile: bilinmeyen anahtar yoksayildi: %s", key)
        return profile


@dataclass
class MotionBudget:
    """Kumulatif HOLD muhasebesi.

    Operator istegi (2026-09-02): HOLD sabit bekleme degil guard'li oldugu
    icin bacak basina degisken sure yiyor; bunun MISSION_TIMEOUT (Sartname
    Bolum 5.6, ZORUNLU 600 s) butcesine karsi izlenebilir olmasi gerekiyor.
    Gorev boyunca TEK bir ornek yasar (CenteringController tutar), her HOLD
    ve ARRIVAL_HOLD buraya yazar."""
    mission_timeout_s: float = GOREV2_MAX_FLIGHT_DURATION_S
    cumulative_hold_s: float = 0.0
    legs: int = 0
    _by_state: dict = field(default_factory=dict)

    def add(self, state: MotionState, seconds: float) -> None:
        self.cumulative_hold_s += seconds
        self._by_state[state.value] = self._by_state.get(state.value, 0.0) + seconds

    def snapshot(self) -> dict:
        return {
            "cumulative_hold_s": round(self.cumulative_hold_s, 3),
            "mission_timeout_s": self.mission_timeout_s,
            "cumulative_hold_pct_of_budget": round(
                100.0 * self.cumulative_hold_s / self.mission_timeout_s, 2)
            if self.mission_timeout_s else None,
            "legs": self.legs,
            "by_state_s": {k: round(v, 3) for k, v in self._by_state.items()},
        }


class MotionStateMachine:
    """Tek bir seyahat bacagini bes state uzerinden ucurur.

    send_setpoint: async (forward, right, down) -> (forward, right, down)
        GERCEKTEN komutlanani dondurmeli. CenteringController._send_setpoint
        tam olarak bunu yapar (rate limit sonrasi degeri doner) ve trapez
        profil bir sonraki tick'in rampasini o degerden devam ettirir --
        aksi halde profil ile limiter birbirini kovalar.
    """

    def __init__(self, flight: IFlightBackend,
                 send_setpoint: Callable,
                 profile: Optional[MotionProfile] = None,
                 budget: Optional[MotionBudget] = None,
                 kp_altitude: float = 0.5,
                 publisher: EventPublisher = NULL_PUBLISHER,
                 subsystem: str = "MotionStateMachine"):
        self.flight = flight
        self.send_setpoint = send_setpoint
        self.profile = profile or MotionProfile()
        self.budget = budget or MotionBudget()
        self.kp_altitude = kp_altitude
        self.publisher = publisher
        self.subsystem = subsystem
        self.state = MotionState.IDLE
        self._state_entered_at = time.monotonic()
        #: Bacak boyunca gecilen state'ler -- entegrasyon testi sirayi
        #: buradan da dogrulayabilir, yalnizca loglardan degil.
        self.visited: list = []

    # ---------------- olay/gecis ----------------

    def _publish(self, code, message="", severity=Severity.INFO, data=None):
        self.publisher.publish(Event(
            code=code, subsystem=self.subsystem, category=Category.NAVIGATION,
            severity=severity, message=message, data=data or {},
        ))

    def _transition(self, new_state: MotionState, reason: str = "") -> None:
        """MissionContext.transition_to() ile AYNI sozlesme: onceki state,
        yeni state, oncekinde gecen sure ve sebep -- operator istegi
        ('Her state gecisini logla')."""
        now = time.monotonic()
        previous, duration = self.state, now - self._state_entered_at
        self.state, self._state_entered_at = new_state, now
        self.visited.append(new_state)
        logger.info("[MOTION] %s -> %s (%.2fs%s)", previous.value, new_state.value,
                    duration, f", {reason}" if reason else "")
        self._publish("MOTION_STATE_CHANGED", f"{previous.value} -> {new_state.value}",
                      data={"from_state": previous.value, "to_state": new_state.value,
                            "previous_state_duration_s": round(duration, 3),
                            "reason": reason})

    def _abort_on_stale(self, state: MotionState, error: Exception) -> bool:
        """ADR-009 D1: telemetri olduyse komut vermeyi derhal birak."""
        logger.error("[MOTION] %s: telemetri bayat -- bacak iptal: %s", state.value, error)
        self._publish("MOTION_TELEMETRY_STALE_ABORT", str(error),
                      severity=Severity.CRITICAL, data={"state": state.value})
        self._transition(MotionState.ABORTED, reason="telemetry_stale")
        return False

    # ---------------- bacak ----------------

    async def fly_leg(self, target_lat: float, target_lon: float,
                      target_alt_m: float) -> bool:
        """CLIMB -> HOLD -> CRUISE -> DESCEND -> ARRIVAL_HOLD.

        Doner: hedefe yakinsandi mi. False, bacagin zaman asimina ugradigini
        ya da telemetrinin oldugunu gosterir -- cagiran taraf bunu
        goto_global_position_and_wait()'in donusuyle ayni sekilde yorumlar."""
        self.visited = []
        self.state = MotionState.IDLE
        self._state_entered_at = time.monotonic()
        self.budget.legs += 1
        leg_deadline = time.monotonic() + self.profile.leg_timeout_s

        try:
            start_lat, start_lon, start_alt = await self.flight.get_global_position()
            start_n, start_e, _ = await self.flight.get_position_ned()
        except TelemetryStale as e:
            return self._abort_on_stale(MotionState.IDLE, e)

        # Hedefin MUTLAK yerel-NED konumu BIR KEZ hesaplanir. Bu,
        # goto_global_position_and_wait()'in 2026-08-13 BUG FIX'inin ayni
        # ilkesi: hareketli bir goreli delta'yi mutlak bir API'ye beslemek
        # her iterasyonda baska bir noktayi kovalamak demekti.
        delta_n, delta_e = gps_to_ned_delta(start_lat, start_lon, target_lat, target_lon)
        target_n, target_e = start_n + delta_n, start_e + delta_e

        # Seyir irtifasi iki ucun YUKSEK olani: hedef asagidaysa once alcalip
        # alcak irtifada seyretmek engel riski tasir (operator karari).
        cruise_alt_m = max(start_alt, target_alt_m)
        distance_m = haversine_distance_m(start_lat, start_lon, target_lat, target_lon)

        needs_climb = (cruise_alt_m - start_alt) > self.profile.alt_tol_m
        needs_descend = (cruise_alt_m - target_alt_m) > self.profile.alt_tol_m

        logger.info("[MOTION] bacak: %.1f m yatay, %.1f m -> seyir %.1f m -> hedef %.1f m "
                    "(climb=%s descend=%s)", distance_m, start_alt, cruise_alt_m,
                    target_alt_m, needs_climb, needs_descend)
        self._publish("MOTION_LEG_STARTED",
                      f"dist={distance_m:.1f}m alt {start_alt:.1f}->{target_alt_m:.1f}m",
                      data={"target_lat": target_lat, "target_lon": target_lon,
                            "target_alt_m": target_alt_m, "cruise_alt_m": cruise_alt_m,
                            "start_alt_m": start_alt, "horizontal_distance_m": round(distance_m, 2),
                            "plan": [s for s, on in (("CLIMB", needs_climb), ("HOLD", True),
                                                     ("CRUISE", True), ("DESCEND", needs_descend),
                                                     ("ARRIVAL_HOLD", True)) if on]})

        if needs_climb:
            self._transition(MotionState.CLIMB, reason=f"target_alt={cruise_alt_m:.1f}m")
            if not await self._run_vertical(cruise_alt_m, leg_deadline):
                return self._finish(False, "climb_failed")

        self._transition(MotionState.HOLD, reason="settle_before_cruise")
        await self._run_hold(self.profile.hold_min_s, self.profile.hold_max_s, leg_deadline)

        self._transition(MotionState.CRUISE, reason=f"dist={distance_m:.1f}m")
        if not await self._run_cruise(target_n, target_e, cruise_alt_m, leg_deadline):
            return self._finish(False, "cruise_failed")

        if needs_descend:
            self._transition(MotionState.DESCEND, reason=f"target_alt={target_alt_m:.1f}m")
            if not await self._run_vertical(target_alt_m, leg_deadline):
                return self._finish(False, "descend_failed")

        self._transition(MotionState.ARRIVAL_HOLD, reason="settle_before_handover")
        await self._run_hold(self.profile.arrival_hold_s, self.profile.arrival_hold_s, leg_deadline)

        return self._finish(True, "converged")

    def _finish(self, converged: bool, reason: str) -> bool:
        if self.state is not MotionState.ABORTED:
            self._transition(MotionState.COMPLETE if converged else MotionState.ABORTED,
                             reason=reason)
        self._publish("MOTION_LEG_COMPLETE" if converged else "MOTION_LEG_FAILED", reason,
                      severity=Severity.INFO if converged else Severity.WARN,
                      data={"converged": converged, "reason": reason,
                            "states_visited": [s.value for s in self.visited],
                            **self.budget.snapshot()})
        return converged

    # ---------------- state'ler ----------------

    async def _run_vertical(self, target_alt_m: float, leg_deadline: float) -> bool:
        """CLIMB ve DESCEND -- ayni yasa, ayni guard, yalnizca isaret farkli.

        Guard climb_to_altitude()'unkinden bir terim FAZLA tasir:
        |alt_error| < alt_tol'un YANI SIRA |vz| < vz_settle. Tek basina
        pozisyon kosulu, banda hizla girip asmayi 'yakinsadi' sayiyordu."""
        dt = OFFBOARD_SETPOINT_INTERVAL_S
        deadline = min(leg_deadline, time.monotonic() + self.profile.vertical_timeout_s)
        commanded_speed = 0.0

        while time.monotonic() < deadline:
            try:
                _, _, current_alt = await self.flight.get_global_position()
                _, _, vel_down = await self.flight.get_velocity_ned()
            except TelemetryStale as e:
                return self._abort_on_stale(self.state, e)

            alt_error = current_alt - target_alt_m          # >0 ise fazla yuksek
            if abs(alt_error) < self.profile.alt_tol_m and abs(vel_down) < self.profile.vz_settle_m_s:
                await self.send_setpoint(0.0, 0.0, 0.0)
                self._publish("MOTION_VERTICAL_CONVERGED",
                              data={"state": self.state.value, "target_alt_m": target_alt_m,
                                    "alt_error_m": round(alt_error, 3),
                                    "vz_m_s": round(vel_down, 3)})
                return True

            step = trapezoidal_speed(abs(alt_error), abs(commanded_speed),
                                     self.profile.vertical_speed_m_s,
                                     self.profile.accel_m_s2, dt)
            # NED'de down POZITIF asagidir; alt_error>0 (fazla yuksek) ise
            # asagi inmek icin down_m_s pozitif olmali -- isaret dogrudan
            # alt_error'dan gelir.
            down_m_s = math.copysign(step.speed_m_s, alt_error)
            _f, _r, commanded_down = await self.send_setpoint(0.0, 0.0, down_m_s)
            commanded_speed = abs(commanded_down)
            await asyncio.sleep(dt)

        await self.send_setpoint(0.0, 0.0, 0.0)
        self._publish("MOTION_VERTICAL_TIMED_OUT", severity=Severity.WARN,
                      data={"state": self.state.value, "target_alt_m": target_alt_m})
        return False

    async def _run_hold(self, min_s: float, max_s: float, leg_deadline: float) -> None:
        """Pozisyon kilidi + attitude durgunluk guard'i.

        Sabit bir bekleme DEGIL (operator karari): min_s dolduktan sonra
        cikis, roll/pitch turevinin esik altinda MOTION_ATTITUDE_STABLE_
        SAMPLES ardisik ornek kalmasina baglidir. Attitude okunamiyorsa
        (get_attitude_euler() None doner -- ornegin backend desteklemiyor)
        guard sessizce sayaca duser; kanitlanamayan stabilite gorevi
        DUSURMEZ.

        max_s bir emniyet tavanidir: ruzgarda hic durulmayan bir arac
        yuzunden bacak sonsuza kadar beklemesin. Asildiginda WARN loglanir
        ve CRUISE'a devam edilir."""
        dt = OFFBOARD_SETPOINT_INTERVAL_S
        started = time.monotonic()
        deadline = min(leg_deadline, started + max(max_s, min_s))
        stable_run, samples, worst_rate = 0, 0, 0.0
        previous_att, previous_t = None, None
        degraded = False

        while True:
            # Sifir hiz: HOLD sirasinda da setpoint akisi SURMELI.
            await self.send_setpoint(0.0, 0.0, 0.0)

            attitude = await self.flight.get_attitude_euler()
            now = time.monotonic()
            if attitude is None:
                degraded = True
            elif previous_att is not None and previous_t is not None and now > previous_t:
                span = now - previous_t
                roll_rate = abs(_angle_delta_deg(attitude[0], previous_att[0])) / span
                pitch_rate = abs(_angle_delta_deg(attitude[1], previous_att[1])) / span
                rate = max(roll_rate, pitch_rate)
                worst_rate = max(worst_rate, rate)
                samples += 1
                stable_run = stable_run + 1 if rate < self.profile.attitude_rate_limit_deg_s else 0
            if attitude is not None:
                previous_att, previous_t = attitude, now

            elapsed = now - started
            if elapsed >= min_s:
                if degraded or stable_run >= self.profile.attitude_stable_samples:
                    break
            if now >= deadline:
                logger.warning("[MOTION] HOLD tavani doldu (%.2fs) -- attitude durulmadi "
                               "(en kotu %.1f deg/s, esik %.1f). Devam ediliyor.",
                               elapsed, worst_rate, self.profile.attitude_rate_limit_deg_s)
                self._publish("MOTION_HOLD_UNSETTLED", severity=Severity.WARN,
                              data={"state": self.state.value, "elapsed_s": round(elapsed, 3),
                                    "worst_attitude_rate_deg_s": round(worst_rate, 2),
                                    "limit_deg_s": self.profile.attitude_rate_limit_deg_s})
                break
            await asyncio.sleep(dt)

        held_s = time.monotonic() - started
        self.budget.add(self.state, held_s)
        self._publish("MOTION_HOLD_SETTLED",
                      f"{held_s:.2f}s (kumulatif {self.budget.cumulative_hold_s:.1f}s)",
                      data={"state": self.state.value, "held_s": round(held_s, 3),
                            "min_s": min_s, "attitude_samples": samples,
                            "attitude_guard_degraded": degraded,
                            "worst_attitude_rate_deg_s": round(worst_rate, 2),
                            **self.budget.snapshot()})

    async def _run_cruise(self, target_n: float, target_e: float,
                          cruise_alt_m: float, leg_deadline: float) -> bool:
        """Yatay seyir. Z burada SEYAHAT etmez, yalnizca TUTULUR.

        down_m_s bir irtifa-tutma terimidir (kp_altitude * hata), bir yorunge
        bileseni degil -- state'i 'yatay' yapan sey budur. cruise_alt_m
        CLIMB'in birakip gittigi irtifadir, yani normalde hata ~0 ve bu terim
        yalnizca surunmeyi (drift) toplar."""
        dt = OFFBOARD_SETPOINT_INTERVAL_S
        commanded_speed = 0.0

        while time.monotonic() < leg_deadline:
            try:
                current_n, current_e, _ = await self.flight.get_position_ned()
                _, _, current_alt = await self.flight.get_global_position()
                vel_n, vel_e, _ = await self.flight.get_velocity_ned()
                yaw_deg = await self.flight.get_yaw_deg()
            except TelemetryStale as e:
                return self._abort_on_stale(MotionState.CRUISE, e)

            error_n, error_e = target_n - current_n, target_e - current_e
            distance_m = math.hypot(error_n, error_e)
            horizontal_speed = math.hypot(vel_n, vel_e)

            # Guard'in IKI yarisi: yaricap TEK BASINA yetmez (2026-08-13
            # olcumu: yaricaptan ~11 m/s ile gecip 10-25 m otesine suzulme).
            if (distance_m < self.profile.arrival_radius_m
                    and horizontal_speed < self.profile.arrival_speed_m_s):
                await self.send_setpoint(0.0, 0.0, 0.0)
                self._publish("MOTION_CRUISE_ARRIVED",
                              data={"distance_m": round(distance_m, 2),
                                    "horizontal_speed_m_s": round(horizontal_speed, 2),
                                    "arrival_radius_m": self.profile.arrival_radius_m})
                return True

            step = trapezoidal_speed(distance_m, commanded_speed,
                                     self.profile.cruise_speed_m_s,
                                     self.profile.accel_m_s2, dt)
            north_m_s, east_m_s = split_horizontal(step.speed_m_s, error_n, error_e)
            forward_m_s, right_m_s = ned_to_body(north_m_s, east_m_s, yaw_deg)

            alt_error = current_alt - cruise_alt_m
            down_m_s = _clamp(alt_error * self.kp_altitude, self.profile.vertical_speed_m_s)

            f, r, _d = await self.send_setpoint(forward_m_s, right_m_s, down_m_s)
            commanded_speed = math.hypot(f, r)
            await asyncio.sleep(dt)

        await self.send_setpoint(0.0, 0.0, 0.0)
        self._publish("MOTION_CRUISE_TIMED_OUT", severity=Severity.WARN,
                      data={"target_n": target_n, "target_e": target_e})
        return False


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _angle_delta_deg(a: float, b: float) -> float:
    """(-180, 180] araligina sarilmis fark. Roll/pitch normalde sarmaz ama
    yaw'a yakin bir eksende +179 -> -179 sicramasi 358 deg/s'lik sahte bir
    rate uretirdi; guard'in bunu 'sallaniyor' diye okumamasi gerekiyor."""
    return (a - b + 180.0) % 360.0 - 180.0
