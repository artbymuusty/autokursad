"""Climb-then-Cruise -- CANLI Gazebo SITL entegrasyon testi.

Bu, bu kod tabanindaki ILK canli-simulator testidir; bugune kadarki tum
testler mock tabanliydi (bkz. docs/flight-control-analysis.md 2.5). Amaci
bir birim testinin yapamadigi tek seyi kanitlamak: state sirasinin ve eksen
ayriminin GERCEK PX4 + gercek EKF + gercek Gazebo fizigi altinda da tuttugu.

KAPSAM (operator karari 2026-09-02): yalnizca GOREV 2 bacagi. Gorev 3 Faz 1
ayri bir is kalemi ve bu PR'in disinda. Test kamera/vision'a HIC dokunmaz --
tek bir seyahat bacagi ucar, boylece kirilganlik yuzeyi navigasyonla sinirli.

NASIL CALISTIRILIR (varsayilan pytest kosumunda ATLANIR):

    tests/integration/run_sitl_integration.sh

ya da simulator zaten ayaktaysa:

    KURSAD_SITL=1 PYTHONPATH=$PWD python -m pytest tests/integration -q -s

KURSAD_SITL ayarli degilse modul tamamen atlanir -- `pytest tests` hermetik
kalir ve CI'da simulator gerektirmez.
"""
import asyncio
import math
import os

import pytest

if not os.environ.get("KURSAD_SITL"):
    pytest.skip("Canli SITL gerekiyor: KURSAD_SITL=1 ile calistirin "
                "(bkz. tests/integration/run_sitl_integration.sh)",
                allow_module_level=True)

from core.detection.detection_feed import DetectionFeed          # noqa: E402
from core.navigation.centering_controller import CenteringController  # noqa: E402
from core.navigation.geo import haversine_distance_m             # noqa: E402
from core.navigation.motion_fsm import MotionProfile             # noqa: E402
from core.navigation.motion_state import MotionState             # noqa: E402
from core.telemetry.events import Event                          # noqa: E402
from gz_system.gz_flight_backend import GzFlightBackend          # noqa: E402

CONNECTION = os.environ.get("KURSAD_SITL_CONNECTION", "udp://:14540")
TAKEOFF_ALT_M = 8.0
#: Bacak hedefi: kalkis noktasindan 25 m kuzey, 15 m irtifa.
#: Kalkis 8 m'de yapildigi icin bacak CLIMB gerektirir (8 -> 15) ve
#: DESCEND gerektirmez -- bu testin dogruladigi sira budur.
LEG_NORTH_M = 25.0
LEG_ALT_M = 15.0
_EARTH_RADIUS_M = 6371000.0


class _RecordingPublisher:
    def __init__(self):
        self.events = []

    def publish(self, event: Event) -> None:
        self.events.append(event)

    def codes(self, code):
        return [e for e in self.events if e.code == code]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_gorev2_leg_runs_climb_hold_cruise_arrival_on_real_sitl():
    publisher = _RecordingPublisher()
    flight = GzFlightBackend(CONNECTION, publisher=publisher)

    await asyncio.wait_for(flight.connect(), timeout=60)

    centering = CenteringController(flight, DetectionFeed(), camera=None,
                                    publisher=publisher)
    centering.motion_profile = MotionProfile()      # parameters.py varsayilanlari

    # Komutlanan her setpoint'i O ANKI state ile birlikte kaydet: eksen
    # ayrimi iddiasi loglardan degil, gercekten gonderilen komutlardan
    # dogrulanacak.
    commands = []
    real_send = centering._send_setpoint

    async def _recording_send(forward, right, down, immediate_stop=True):
        machine = getattr(centering, "_last_motion_machine", None)
        result = await real_send(forward, right, down, immediate_stop=immediate_stop)
        commands.append((machine.state if machine else None, *result))
        return result

    centering._send_setpoint = _recording_send

    try:
        await flight.arm()
        await flight.takeoff(TAKEOFF_ALT_M)
        # PX4'un kendi TAKEOFF'u bitene kadar bekle; Offboard'a ancak
        # ondan sonra gecilir.
        for _ in range(120):
            _lat, _lon, alt = await flight.get_global_position()
            if alt >= TAKEOFF_ALT_M - 1.0:
                break
            await asyncio.sleep(0.5)
        else:
            pytest.fail(f"Kalkis {TAKEOFF_ALT_M} m'ye ulasmadi")

        start_lat, start_lon, start_alt = await flight.get_global_position()
        target_lat = start_lat + math.degrees(LEG_NORTH_M / _EARTH_RADIUS_M)
        target_lon = start_lon

        assert await centering.switch_to_offboard(), "PX4 OFFBOARD'a gecmedi"

        converged = await centering.goto_waypoint(target_lat, target_lon, LEG_ALT_M)
        assert converged, "bacak yakinsamadi"

        # --- 1) State sirasi -------------------------------------------------
        changes = publisher.codes("MOTION_STATE_CHANGED")
        sequence = [e.data["to_state"] for e in changes]
        expected = [MotionState.CLIMB.value, MotionState.HOLD.value,
                    MotionState.CRUISE.value, MotionState.ARRIVAL_HOLD.value,
                    MotionState.COMPLETE.value]
        assert sequence == expected, f"beklenen {expected}, gelen {sequence}"

        # --- 2) Eksen ayrimi -------------------------------------------------
        vertical = [c for c in commands
                    if c[0] in (MotionState.CLIMB, MotionState.DESCEND)]
        assert vertical, "CLIMB hic setpoint yayinlamadi"
        assert all(f == 0.0 and r == 0.0 for _s, f, r, _d in vertical), \
            "CLIMB/DESCEND sirasinda yatay eksen komutlandi"

        cruise = [c for c in commands if c[0] is MotionState.CRUISE]
        assert cruise, "CRUISE hic setpoint yayinlamadi"
        assert max(abs(f) for _s, f, _r, _d in cruise) > 0.5, "CRUISE yatay hareket etmedi"
        assert max(abs(d) for _s, _f, _r, d in cruise) < 0.5, \
            "CRUISE sirasinda dikey SEYAHAT komutu cikti (yalnizca irtifa tutma olmali)"

        # --- 3) Her state setpoint yayinladi (Offboard bosluk yok) -----------
        for state in (MotionState.CLIMB, MotionState.HOLD,
                      MotionState.CRUISE, MotionState.ARRIVAL_HOLD):
            assert any(c[0] is state for c in commands), \
                f"{state.value} hic setpoint yayinlamadi -- Offboard boslugu riski"

        # --- 4) Gercekten hedefe varildi -------------------------------------
        final_lat, final_lon, final_alt = await flight.get_global_position()
        remaining_m = haversine_distance_m(final_lat, final_lon, target_lat, target_lon)
        assert remaining_m < centering.motion_profile.arrival_radius_m * 1.5, \
            f"hedefe {remaining_m:.1f} m kala durdu"
        assert abs(final_alt - LEG_ALT_M) < 1.0, f"irtifa {final_alt:.1f} m"

        # --- 5) Kumulatif hold butcesi loglandi ------------------------------
        holds = publisher.codes("MOTION_HOLD_SETTLED")
        assert holds, "MOTION_HOLD_SETTLED yayinlanmadi"
        assert holds[-1].data["cumulative_hold_s"] > 0.0
        assert holds[-1].data["mission_timeout_s"] == 600
    finally:
        try:
            await flight.stop_offboard()
        except Exception:  # noqa: BLE001 -- teardown asla testi maskelemesin
            pass
        try:
            await flight.land()
        except Exception:  # noqa: BLE001
            pass
