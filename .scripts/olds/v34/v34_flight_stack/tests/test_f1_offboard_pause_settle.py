"""
GOREV F1-KOK / K6 -- pause_mission() ile offboard.start() ARASINDAKI BEKLEME.

KOK NEDEN (docs/gorevF1-offboard-start-kok-neden.md): MAVSDK v3.17.2'de
CommandIdentification, DO_SET_MODE (176) icin komut parametrelerini
icermiyor. pause_mission() ve offboard.start() ayni {0,0,176,1,1} kimligiyle
gidiyor; pause'un ACK'i hala yoldayken start() kuyruga girerse ACK yanlis
kaleme atfediliyor ve OFFBOARD komutu HIC GONDERILMEDEN start() Success
donuyor. Olculen sessiz basarisizlik %20-24 (tools/offboard_gap_sweep.py,
0 ms -> 5/25); >=20 ms bekleme ile 0/150.

BU DOSYA nesnel olarak SIRALAMAYI ve MESAFEYI korur. Ne PX4'u ne MAVSDK'yi
kosturur -- korumasi gereken sey yalnizca su: iki DO_SET_MODE komutu
arasinda OFFBOARD_PAUSE_SETTLE_S kadar bosluk kalsin ve bu bosluk
mode/pause ile start ARASINDA olsun, oncesinde ya da sonrasinda degil.
"""
import asyncio
import pytest

from mocks.mock_flight_backend import MockFlightBackend
from core.navigation.centering_controller import CenteringController
from core.config.parameters import OFFBOARD_PAUSE_SETTLE_S


class _TimedFlight(MockFlightBackend):
    """Iki DO_SET_MODE cagrisinin event-loop zamanlarini kaydeder."""
    def __init__(self):
        super().__init__()
        self.marks = []

    def _mark(self, name):
        self.marks.append((name, asyncio.get_event_loop().time()))

    async def switch_to_offboard_from_mission(self) -> None:
        self._mark("pause")
        await super().switch_to_offboard_from_mission()

    async def start_offboard(self) -> None:
        self._mark("start")
        await super().start_offboard()


def test_parametre_makul_araliktadir():
    """50 ms: olculen round-trip'in (~11-14 ms) ~4 kati, gozlenen en yuksek
    start() suresinin (25.4 ms) 2 kati. Sifir olmasi kok nedeni geri getirir;
    asiri buyuk olmasi her hedefte bosa sure yakar."""
    assert 0.020 <= OFFBOARD_PAUSE_SETTLE_S <= 0.200


@pytest.mark.asyncio
async def test_bekleme_iki_komut_ARASINDA_gerceklesir():
    """Taramanin gosterdigi sey tam olarak bu mesafeydi: bekleme pause'dan
    ONCE ya da start'tan SONRA olsaydi cakisma penceresi acik kalirdi."""
    flight = _TimedFlight()
    controller = CenteringController(flight, detection_feed=None, camera=None)

    ok = await controller.switch_to_offboard()
    assert ok is True

    names = [n for n, _ in flight.marks]
    assert names == ["pause", "start"], f"beklenmeyen komut sirasi: {names}"

    gap = flight.marks[1][1] - flight.marks[0][1]
    # 0.9 kat pay: event-loop uyanma granularitesi asagi yonde birkac yuz
    # mikrosaniye oynatabilir, yukari yonde degil.
    assert gap >= OFFBOARD_PAUSE_SETTLE_S * 0.9, (
        f"iki DO_SET_MODE arasi yalnizca {gap*1000:.1f} ms -- "
        f"en az {OFFBOARD_PAUSE_SETTLE_S*1000:.0f} ms olmali")


@pytest.mark.asyncio
async def test_bekleme_start_basarisiz_olsa_da_uygulanir():
    """start() reddedilse bile bekleme onceden yapilmis olmali: aksi halde
    'basarisizlik' aslinda hic gonderilmemis bir komut olabilir ve F1
    guard'i (N=3) yanlis sebeple sayar."""
    class _Rejecting(_TimedFlight):
        async def start_offboard(self) -> None:
            self._mark("start")
            raise RuntimeError("COMMAND_DENIED")

    flight = _Rejecting()
    controller = CenteringController(flight, detection_feed=None, camera=None)
    ok = await controller.switch_to_offboard()
    assert ok is False
    assert [n for n, _ in flight.marks] == ["pause", "start"]
    gap = flight.marks[1][1] - flight.marks[0][1]
    assert gap >= OFFBOARD_PAUSE_SETTLE_S * 0.9
