"""GOREV K / C + D: manyetik cekim menzili ve servo2/servo3 ayrimi.

OPERATOR KARARI (2026-09-04, "secenek 2"): 5 cm, cekimin BASLADIGI mesafe.
Kilitlenme kapilari (17.5 mm yanal / 5 mm eksenel / 8 deg egim / 0.05 m/s /
0.60 s dwell) AYNEN KALIYOR -- cekim onlari gevsetmez.

Bu testler tam olarak o ayrimi koruyor: menzil genis, kapi dar.
"""
import math
import os

import pytest

from core.mission.hook_seating import (
    MAGNET_ATTRACT_RANGE_M,
    MAGNET_CAPTURE_RADIUS_M,
    SeatState,
    SeatingGeometry,
    compute_seating_geometry,
)

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), *([os.pardir] * 5)))


def geom(lateral_m=0.0, insertion_m=0.0, tilt_rad=0.0, rel_speed_mps=0.0,
         pose_age_s=0.0, perp_n=0.0, perp_e=0.0):
    return SeatingGeometry(lateral_m=lateral_m, insertion_m=insertion_m,
                           tilt_rad=tilt_rad, rel_speed_mps=rel_speed_mps,
                           pose_age_s=pose_age_s, perp_n=perp_n, perp_e=perp_e)


def test_menzil_5_cm_ve_kapidan_genis():
    """Menzil kapinin ta kendisi olsaydi cekimin hicbir islevi olmazdi."""
    assert MAGNET_ATTRACT_RANGE_M == pytest.approx(0.05)
    assert MAGNET_ATTRACT_RANGE_M > MAGNET_CAPTURE_RADIUS_M


def test_J_demosundaki_41_72_mm_bandi_menzile_giriyor():
    """Olculen ariza bandi: yanal 41-72 mm. Cekim 41-50'yi yakalamali,
    50 mm'nin otesi menzil disinda kalmali -- 5 cm sinirinin anlami bu."""
    assert geom(lateral_m=0.041).attraction_active() is True
    assert geom(lateral_m=0.050).attraction_active() is True
    assert geom(lateral_m=0.060).attraction_active() is False
    assert geom(lateral_m=0.072).attraction_active() is False


def test_mesafe_yanal_ve_eksenel_bosluktan_birlikte_hesaplanir():
    """Delik YUZEYINE uzaklik: yandan ve yukaridan yaklasma ayni sayida."""
    g = geom(lateral_m=0.03, insertion_m=-0.04)     # 4 cm yukarida, 3 cm yanda
    assert g.magnet_distance_m() == pytest.approx(0.05, abs=1e-9)
    assert g.attraction_active() is True
    # Burun guverte duzleminin ALTINDAYSA eksenel bosluk yoktur.
    assert geom(lateral_m=0.03, insertion_m=+0.02).magnet_distance_m() == pytest.approx(0.03)


def test_cekim_menzili_KAPIYI_GEVSETMEZ():
    """Kritik guvence: menzilde olmak oturmak degildir."""
    g = geom(lateral_m=0.041)
    assert g.attraction_active() is True
    assert g.is_seatable() is False
    assert any(f.startswith("lateral") for f in g.failures())


def test_kapi_gecen_geometri_hala_geciyor():
    g = geom(lateral_m=0.010, insertion_m=0.001)
    assert g.is_seatable() is True
    assert g.attraction_active() is True     # kapi geciyorsa menzilde de olmali


def test_perp_yonu_NED_olarak_donuyor():
    """Cekimi uygulayan taraf YONU bilmeli; buyukluk tek basina yetmez.

    Gazebo dunyasi ENU (x=Dogu, y=Kuzey), gorev katmani NED konusuyor.
    Kanca yuvanin 3 cm KUZEYINDE ve 4 cm DOGUSUNDA duruyor.
    """
    payload_pos = (0.0, 0.0, 0.0)
    ident = (0.0, 0.0, 0.0, 1.0)
    # deck = payload + 0.035 * z ; kancanin burnu deck'in yaninda olsun
    hook_pos = (0.04, 0.03, 0.035 + 0.06465)   # x=Dogu, y=Kuzey
    g = compute_seating_geometry(hook_pos, ident, payload_pos, ident,
                                 rel_speed_mps=0.0, pose_age_s=0.0)
    assert g.perp_n == pytest.approx(0.03, abs=1e-6)
    assert g.perp_e == pytest.approx(0.04, abs=1e-6)
    assert g.lateral_m == pytest.approx(0.05, abs=1e-6)


def test_ATTRACTING_durumu_var():
    assert SeatState.ATTRACTING.value == "ATTRACTING"


def test_servo2_ve_servo3_kanallari_yamlda_ayri():
    """GOREV K / C: tek 'pickup_channel' ikiye bolundu, eskiler kalmali."""
    import yaml
    yol = os.path.join(REPO_ROOT, ".scripts", "olds", "v34", "v34_flight_stack",
                       "real_system", "config", "real_system.yaml")
    with open(yol, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    act = cfg["actuator"]
    assert "winch_channel" in act, "servo2 (vinc) kanali yok"
    assert "grip_channel" in act, "servo3 (kavrama) kanali yok"
    # Eski anahtarlar silinmedi -- bolme hicbir seyi kirmadi.
    assert "pickup_channel" in act and "drop_channel" in act
