"""Gazebo payload actuator: detach topics, and CONFIRMED release (F2).

Rewritten for ADR-011 (release detaches a world-loaded body instead of
spawning one) and F2 (a release is not believed until the body is seen to
leave the vehicle). The failure these pin down is concrete: on the first
ADR-011 flight the servo fired, the log said RELEASED, and the payload was
still bolted on -- it let go seconds later during the climb-out and landed
4.9 m past the target.
"""
import inspect
import os

import pytest
from unittest.mock import AsyncMock, patch

from core.config.parameters import PAYLOAD_EXPECTED_REST_Z_M
from gz_system import gz_payload_actuator
from gz_system.gz_payload_actuator import (
    GzPayloadActuator,
    PAYLOAD_DETACH_TOPIC,
    VEHICLE_MODEL_NAME,
    read_target_centers,
    shape_inradius_m,
)


def _mock_proc(returncode: int, stderr: bytes = b""):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate.return_value = (b"", stderr)
    return proc


class _FakeMonitor:
    """Scripted pose source. `drop_after` is how many payload reads stay
    attached before the body starts falling; read 1 is the pre-publish
    baseline, so 1 means "separates on the first poll after the servo" and
    None means it never separates at all."""

    def __init__(self, drop_after=1, known=True):
        self.drop_after = drop_after
        self.known = known
        self.reads = 0

    def get(self, name):
        if not self.known:
            return None
        if name == VEHICLE_MODEL_NAME:
            return (0.0, 0.0, 0.65)
        self.reads += 1
        attached_z = 0.47  # 0.18 m below the vehicle
        if self.drop_after is not None and self.reads > self.drop_after:
            return (0.0, 0.0, 0.03)
        return (0.0, 0.0, attached_z)

    def get_quat(self, name):
        return (0.0, 0.0, 0.0, 1.0)


def _actuator(monitor):
    return GzPayloadActuator("dummy_service", pose_monitor=monitor)


@pytest.mark.asyncio
async def test_release_at_mavi_altigen_detaches_the_red_payload():
    """The servo->colour mapping is a deliberate team assignment (RED
    payload on the MAVI hexagon) and must not drift."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)) as exec_mock:
        assert await actuator.release_payload_at_mavi_altigen() is True
    topics = [c.args for c in exec_mock.call_args_list]
    assert all(PAYLOAD_DETACH_TOPIC % "red" in args for args in topics)
    assert all("gz.msgs.Empty" in args for args in topics)


@pytest.mark.asyncio
async def test_release_at_kirmizi_ucgen_detaches_the_blue_payload():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)) as exec_mock:
        assert await actuator.release_payload_at_kirmizi_ucgen() is True
    assert all(PAYLOAD_DETACH_TOPIC % "blue" in c.args for c in exec_mock.call_args_list)


@pytest.mark.asyncio
async def test_detach_is_published_more_than_once():
    """gz-transport is a slow joiner: a one-shot publisher can advertise and
    send before the plugin has finished subscribing, and the message is
    simply lost. A single publish is what made the first flight's detach
    arrive seconds late."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)) as exec_mock:
        await actuator.release_payload_at_mavi_altigen()
    assert exec_mock.call_count > 1


@pytest.mark.asyncio
async def test_release_reports_failure_when_the_payload_never_separates():
    """THE regression. The payload is visible and demonstrably still hanging
    off the vehicle, so the release must come back False -- the caller uses
    that to hold position instead of climbing away."""
    actuator = _actuator(_FakeMonitor(drop_after=None))
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.release_payload_at_mavi_altigen() is False
    assert actuator.detach_latency("MAVI_ALTIGEN") is None


@pytest.mark.asyncio
async def test_confirmed_release_records_its_latency():
    actuator = _actuator(_FakeMonitor(drop_after=1))
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.release_payload_at_kirmizi_ucgen() is True
    latency = actuator.detach_latency("KIRMIZI_UCGEN")
    assert latency is not None and latency >= 0.0


@pytest.mark.asyncio
async def test_missing_pose_data_is_unknown_not_failure():
    """A dead observer must not ground a flight. With no pose at all we
    cannot distinguish attached from separated, so we claim neither and let
    the mission proceed -- loudly unconfirmed, not falsely failed."""
    actuator = _actuator(_FakeMonitor(known=False))
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.release_payload_at_mavi_altigen() is True
    assert actuator.detach_latency("MAVI_ALTIGEN") is None


@pytest.mark.asyncio
async def test_release_returns_false_when_gz_cli_missing():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
        assert await actuator.release_payload_at_kirmizi_ucgen() is False


@pytest.mark.asyncio
async def test_release_returns_false_when_every_publish_fails():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec",
               return_value=_mock_proc(1, b"gz: command not found")):
        assert await actuator.release_payload_at_mavi_altigen() is False


_WORLD_FIXTURE = """<sdf version='1.9'><world name='default'>
  <include><uri>model://ground_plane</uri><name>ground_plane</name>
    <pose>0 0 0 0 0 0</pose></include>
  <!-- KURSAD_COMPETITION_AREA_START -->
  <include><uri>model://blue_hexagon</uri><name>blue_hexagon</name>
    <pose>-6.649 86.259 0.003 0 0 0</pose></include>
  <include><uri>model://red_triangle</uri><name>red_triangle</name>
    <pose>8.642 14.533 0.003 0 0 0</pose></include>
  <!-- KURSAD_COMPETITION_AREA_END -->
  <include><uri>model://blue_square</uri><name>blue_square</name>
    <pose>999 999 0 0 0 0</pose></include>
</world></sdf>"""


def _world_file(tmp_path, text=_WORLD_FIXTURE):
    path = tmp_path / "world.sdf"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_landing_reference_reads_the_centre_from_the_world_the_sim_loaded(tmp_path, monkeypatch):
    """E1 (2026-09-03): the centres used to be the literal (0,15)/(0,40).
    safe_sitl_launcher.sh step 4a regenerates default.sdf with RANDOM shape
    positions every launch, so those literals scored every drop against
    coordinates no shape had occupied in months -- a payload 15.3 cm from
    the triangle was reported 3373.0 cm off. Read the world, not a memory."""
    monkeypatch.setenv("KURSAD_WORLD_SDF", _world_file(tmp_path))
    actuator = _actuator(_FakeMonitor())
    assert actuator.landing_reference("MAVI_ALTIGEN")[:2] == (-6.649, 86.259)
    assert actuator.landing_reference("KIRMIZI_UCGEN")[:2] == (8.642, 14.533)
    # Rest height still comes from the parameter, not the world.
    assert actuator.landing_reference("MAVI_ALTIGEN")[2] == PAYLOAD_EXPECTED_REST_Z_M


def test_only_shapes_inside_the_generated_block_are_targets(tmp_path, monkeypatch):
    """generate_competition_area.py rewrites exactly the marker span, so a
    model outside it (ground_plane, or a stray blue_square) must never be
    mistaken for a drop target."""
    monkeypatch.setenv("KURSAD_WORLD_SDF", _world_file(tmp_path))
    centres = read_target_centers()
    assert set(centres) == {"MAVI_ALTIGEN", "KIRMIZI_UCGEN"}
    assert "MAVI_DIKDORTGEN" not in centres      # sits outside the markers


def test_unreadable_world_scores_nothing_rather_than_scoring_wrongly(tmp_path, monkeypatch):
    """A missing score is honest; a stale score is not. core then degrades
    to the documented above-ground check."""
    monkeypatch.setenv("KURSAD_WORLD_SDF", str(tmp_path / "yok.sdf"))
    actuator = _actuator(_FakeMonitor())
    assert actuator.landing_reference("MAVI_ALTIGEN") is None
    assert read_target_centers() == {}


def test_world_without_the_markers_scores_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("KURSAD_WORLD_SDF",
                       _world_file(tmp_path, "<sdf><world name='x'></world></sdf>"))
    assert read_target_centers() == {}


def test_centres_are_read_once_and_remembered(tmp_path, monkeypatch):
    """The world cannot change mid-run, and re-reading it on every drop
    would put a file read in the release path."""
    path = _world_file(tmp_path)
    monkeypatch.setenv("KURSAD_WORLD_SDF", path)
    actuator = _actuator(_FakeMonitor())
    assert actuator.landing_reference("KIRMIZI_UCGEN")[:2] == (8.642, 14.533)
    os.remove(path)
    assert actuator.landing_reference("KIRMIZI_UCGEN")[:2] == (8.642, 14.533)


def test_no_hard_coded_target_centres_survive_anywhere():
    """Regression guard for the actual E1 defect: the module must not carry
    a literal centre dictionary again."""
    src = inspect.getsource(gz_payload_actuator)
    assert "TARGET_CENTERS = {" not in src
    assert not hasattr(gz_payload_actuator, "TARGET_CENTERS")


def test_tilt_is_reported_so_edge_landings_are_visible():
    actuator = _actuator(_FakeMonitor())
    assert actuator.get_released_payload_tilt_deg("MAVI_ALTIGEN") == 0.0


def _fast_capture(timeout_s=0.9):
    """Testlerde oturma penceresini kisalt: gercek deger 12 s x 3 deneme,
    yani tek bir basarisizlik senaryosu 36 saniye surerdi.

    Varsayilan 0.9 s: SEAT_DWELL_S (0.30 s) artik GERCEK bir sart oldugu
    icin pencere ondan belirgin olarak uzun olmali, yoksa gecerli geometri
    bile dwell'i tamamlayamadan zaman asimina ugrar."""
    import gz_system.gz_payload_actuator as act
    act.HOOK_CONTACT_TIMEOUT_S = timeout_s


def _seated(**over):
    """Gecerli bir oturma geometrisi ureten sahte olcum."""
    from core.mission.hook_seating import SeatingGeometry
    vals = dict(lateral_m=0.003, insertion_m=0.001, tilt_rad=0.0,
                rel_speed_mps=0.0, pose_age_s=0.0)
    vals.update(over)
    return SeatingGeometry(**vals)

@pytest.mark.asyncio
async def test_gorev3_pickup_drives_the_real_hook_not_a_placeholder():
    """Bu test eskiden "hala simule placeholder" oldugunu dogruluyordu.
    2026-08-21'de mekanizma SDF'ye eklenip baglandi
    (x500_mono_cam_down/model.sdf: hook_winch_link + hook_rope_link +
    HookAttachSystem), dolayisiyla artik tersini dogruluyor: alma gercekten
    vinci salmali, temas beklemeli ve /hook/attach yayinlamali.

    Publish/echo cagrilari taklit edilir -- burada test edilen sira ve
    mesaj tipleridir, Gazebo'nun kendisi degil. Mesaj tipleri onemli:
    /hook/detach eklentide gz.msgs.Boolean bekliyor, Empty degil; yanlis
    tiple yayinlanan mesaji gz-transport sessizce dusurur."""
    actuator = _actuator(_FakeMonitor())
    _fast_capture()
    published, waited = [], []

    async def fake_pub(topic, msgtype, payload):
        published.append((topic, msgtype, payload))
        return True

    async def fake_wait(topic, timeout_s, needle="", after_start=None):
        waited.append(topic)
        # Gercek _gz_wait_for tetikleyiciyi ABONE OLDUKTAN SONRA calistirir;
        # sahte de ayni sirayi taklit etmeli, yoksa test /hook/attach'in hic
        # yayinlanmadigini gorur.
        if after_start is not None:
            await after_start()
        return True          # temas ve kilit onayi geldi varsay

    actuator._gz_pub = fake_pub
    actuator._gz_wait_for = fake_wait
    # OTURMA sarti artik ZORUNLU (bkz. _await_seating): kanca yuvanin
    # icinde, deck duzleminin 1 mm altinda ve duruyor varsayiliyor.
    # Not: bu ARTIK yatay mesafe degil -- gercek kanca pozundan hesaplanan
    # yuva-cerceveli geometridir.
    actuator.seating_geometry = lambda color: _seated()

    assert await actuator.activate_pickup_mechanism() is True
    topics = [t for t, _m, _p in published]
    assert "/hook/winch/cmd" in topics, topics
    assert "/hook/attach" in topics, topics
    # /hook/contact ARTIK HIC KULLANILMIYOR: kanca ucunun herhangi bir seye
    # (zemin dahil) degmesiyle tetiklendigi icin geometrik karari
    # dogrulayamaz. Zorunlu olan, kilidin /hook/state ile DOGRULANMASI.
    assert "/hook/state" in waited, waited
    assert "/hook/contact" not in waited, waited
    # SIRA: attach YALNIZCA oturma dogrulandiktan sonra yayinlanir.
    assert topics.index("/hook/winch/cmd") < topics.index("/hook/attach"), topics
    # Vinc salinmali ve KILITTEN SONRA ACIK KALMALI: toplamak, kilitli yuku
    # kancanin cekili konumuna kadar cekip govde/iniş takimi hacmine
    # sokuyordu (mission12'de yuk hedefin 7 m gerisine dustu). Toplama artik
    # yalnizca birakma sirasinda olur.
    winch = [p for t, _m, p in published if t == "/hook/winch/cmd"]
    assert winch, published
    assert "0.0" not in winch[-1], f"alma sonunda vinc toplanmamali: {winch}"
    attach = [p for t, _m, p in published if t == "/hook/attach"][0]
    assert "payload_red" in attach, attach

    published.clear()
    assert await actuator.activate_drop_mechanism() is True
    drop_topics = [t for t, _m, _p in published]
    assert drop_topics[0] == "/hook/detach", published
    assert published[0][1] == "gz.msgs.Boolean", published
    # Birakmadan SONRA vinc toplanmali, yoksa arac inerken kanca yere iniş
    # takimindan once deger.
    assert "/hook/winch/cmd" in drop_topics, published
    assert "0.0" in [p for t, _m, p in published if t == "/hook/winch/cmd"][-1], published


@pytest.mark.asyncio
async def test_gorev3_pickup_fails_loudly_when_the_hook_never_touches():
    """Temas gelmezse alma BASARISIZ donmeli -- sessizce True donmek,
    Gorev 3'un 2026-08-21 oncesi hali gibi, hic yuk tasinmadan "basarili"
    raporlamak demekti."""
    actuator = _actuator(_FakeMonitor())
    _fast_capture()

    async def fake_pub(topic, msgtype, payload):
        return True

    async def fake_wait(topic, timeout_s, needle="", after_start=None):
        if after_start is not None:
            await after_start()
        return False         # temas hic gelmiyor

    actuator._gz_pub = fake_pub
    actuator._gz_wait_for = fake_wait
    # Yuk cok uzakta: yanal 0.90 m, oturma yok.
    actuator.seating_geometry = lambda color: _seated(lateral_m=0.90)

    assert await actuator.activate_pickup_mechanism() is False


@pytest.mark.asyncio
async def test_touching_the_ground_far_from_the_payload_is_not_a_capture():
    """THE regression (operator-reported, 2026-08-23): "kanca uzaktayken
    yuku alabildi".

    Temas sensoru kanca ucunun HERHANGI bir seye degmesinde tetikleniyor.
    Olculdu -- kanca yere degdiginde mesajin karsi tarafi:
        collision2 { name: "ground_plane::link::collision" }
    Eski surum temas topic'ini kosulsuz kabul ettigi icin bunu "yakalandi"
    sayiyor ve yuku metrelerce oteden kilitliyordu.

    GUNCELLEME (2026-08-26): /hook/contact artik KARARDAN TAMAMEN CIKARILDI.
    Bu testin sarti bu yuzden guclendi: temas HER SEYE "evet" dese bile,
    oturma geometrisi gecersizken alma reddedilmeli."""
    actuator = _actuator(_FakeMonitor())
    _fast_capture()

    async def fake_pub(topic, msgtype, payload):
        published.append(topic)
        return True

    published = []

    async def fake_wait(topic, timeout_s, needle="", after_start=None):
        if after_start is not None:
            await after_start()
        return True          # temas da, kilit onayi da "var" desin

    actuator._gz_pub = fake_pub
    actuator._gz_wait_for = fake_wait
    # Kanca zemine degiyor ama yuvadan 39 cm uzakta (olculen iskalama).
    actuator.seating_geometry = lambda color: _seated(lateral_m=0.39)

    assert await actuator.activate_pickup_mechanism() is False
    import gz_system.gz_payload_actuator as act
    assert act.HOOK_ATTACH_TOPIC not in published, published


@pytest.mark.asyncio
async def test_horizontal_alignment_alone_never_seats_the_hook():
    """ACCEPTANCE CASE 7 REGRESSION, at the actuator level.

    Replaces the old "5 cm rule" test. That rule was XY-only, and the
    2026-08-26 acceptance run drove it into a false capture: the hook was
    2.42 cm from the receiver horizontally -- comfortably inside 5 cm -- but
    1.97 m ABOVE it. The old gate welded the payload to the hook while the
    payload was still resting on the ground and hoisted it.

    Good horizontal alignment must therefore NOT be sufficient on its own:
    the axial term has to reject it, and no /hook/attach may be published."""
    actuator = _actuator(_FakeMonitor())
    _fast_capture()
    published = []

    async def fake_pub(topic, msgtype, payload):
        published.append(topic)
        return True

    async def fake_wait(topic, timeout_s, needle="", after_start=None):
        if after_start is not None:
            await after_start()
        return True

    actuator._gz_pub = fake_pub
    actuator._gz_wait_for = fake_wait
    # Case 7 geometrisi: yanal mukemmel, eksenel 1.97 m yukarida.
    actuator.seating_geometry = lambda color: _seated(lateral_m=0.0242,
                                                      insertion_m=-1.970)

    assert await actuator.activate_pickup_mechanism() is False
    import gz_system.gz_payload_actuator as act
    assert act.HOOK_ATTACH_TOPIC not in published, published
    assert actuator.is_hook_attached() is False


@pytest.mark.asyncio
async def test_momentary_valid_geometry_does_not_satisfy_the_dwell():
    """Ipte sallanan kanca yakalama zarfindan GECERKEN bir an gecerli
    gorunur. Olculen sarkac periyodu 0.831 s; 5 cm genlikli bir salinim
    zarfin icinde yalnizca ~0.128 s kalir. Tek bir iyi ornek kilit
    uretmemeli."""
    actuator = _actuator(_FakeMonitor())
    _fast_capture()
    published = []

    async def fake_pub(topic, msgtype, payload):
        published.append(topic)
        return True

    async def fake_wait(topic, timeout_s, needle="", after_start=None):
        if after_start is not None:
            await after_start()
        return True

    actuator._gz_pub = fake_pub
    actuator._gz_wait_for = fake_wait

    seq = {"n": 0}

    def swinging(color):
        # bir gecerli ornek, ardindan hep gecersiz -- dwell asla dolmaz
        seq["n"] += 1
        return _seated() if seq["n"] % 8 == 0 else _seated(lateral_m=0.30)

    actuator.seating_geometry = swinging

    assert await actuator.activate_pickup_mechanism() is False
    import gz_system.gz_payload_actuator as act
    assert act.HOOK_ATTACH_TOPIC not in published, published


@pytest.mark.asyncio
async def test_drop_reports_failure_when_the_payload_never_leaves_the_hook():
    """THE regression (2026-08-23 kosusu): birakma komutu KABUL EDILDI ama
    yuk kancada kaldi ve faz yine de "Basarili" dedi.

    Onceki surum yalnizca _gz_pub'in donusune bakiyordu -- o ise "gz komutu
    hatasiz calisti" demek, "joint kaldirildi" demek degil. Olculdu: yuk
    donus ucusu boyunca aracin 13 cm yaninda, 7 cm altinda kaldi ve
    x 19.5 -> 24.3 aracla birlikte ilerledi.

    /hook/state ile onaylamak burada ise yaramaz: eklenti set_data(false)
    yayinliyor, protobuf varsayilani atliyor, mesaj bos govdeyle gidiyor.
    Bu yuzden Gorev 2'nin kanitlanmis yontemi kullaniliyor: yuk aractan
    FIZIKSEL olarak ayrildi mi."""
    import gz_system.gz_payload_actuator as act
    actuator = _actuator(_FakeMonitor())
    act.HOOK_DETACH_CONFIRM_S = 0.2
    act.HOOK_DETACH_ATTEMPTS = 2

    async def fake_pub(topic, msgtype, payload):
        return True                      # komut hep "basarili"

    actuator._gz_pub = fake_pub
    # Yuk hic ayrilmiyor: goreli konum sabit, dinlenme yuksekligine inmiyor.
    actuator._relative_drop = lambda color: 0.50
    actuator._at_rest_height = lambda color: False

    assert await actuator.activate_drop_mechanism() is False


# --- E3 takibi: sekil basina "hedefte" yaricapi ------------------------------

def test_on_target_radius_is_derived_per_shape_from_sdf_geometry():
    """Tek bir 0.5 m esigi iki sekle birden uyamiyordu: ucgenin ic tegeti
    0.289 m, yani 0.5 m'de yuk ucgenin DISINDA sayilmasi gerekirken
    "hedefte" yaziliyordu; altigenin ic tegeti ise 0.866 m, yani 0.5 m
    gereksiz dardi."""
    actuator = _actuator(_FakeMonitor())
    hexagon = actuator.on_target_radius_m("MAVI_ALTIGEN")
    triangle = actuator.on_target_radius_m("KIRMIZI_UCGEN")
    assert hexagon == pytest.approx(0.866 - 0.15, abs=1e-3)
    assert triangle == pytest.approx(0.866 / 3.0 - 0.15, abs=1e-3)
    assert triangle < 0.5 < hexagon      # tek sabit ikisine de yanlisti


def test_inradius_follows_the_collision_box_not_the_visual_mesh():
    """ADR-011 oncesi gorsel ile carpisma ayrisip yukun %96 ihtimalle
    sekilden gectigi olculmustu; "uzerine dustu mu" sorusunun muhatabi
    carpisma geometrisidir."""
    assert shape_inradius_m("MAVI_ALTIGEN") == pytest.approx(1.732 / 2.0, abs=1e-3)
    # Eskenar ucgende agirlik merkezinden ic teget = yukseklik / 3.
    assert shape_inradius_m("KIRMIZI_UCGEN") == pytest.approx(0.866 / 3.0, abs=1e-3)


def test_missing_geometry_falls_back_to_the_flat_constant(monkeypatch, tmp_path):
    """Gercek donanimda SDF yoktur; orada davranis degismemeli."""
    monkeypatch.setenv("KURSAD_MODELS_ROOT", str(tmp_path))
    actuator = _actuator(_FakeMonitor())
    assert actuator.on_target_radius_m("MAVI_ALTIGEN") is None


def test_radius_is_read_once_per_shape():
    actuator = _actuator(_FakeMonitor())
    first = actuator.on_target_radius_m("KIRMIZI_UCGEN")
    assert actuator._on_target_radius["KIRMIZI_UCGEN"] == first
    assert actuator.on_target_radius_m("KIRMIZI_UCGEN") == first
