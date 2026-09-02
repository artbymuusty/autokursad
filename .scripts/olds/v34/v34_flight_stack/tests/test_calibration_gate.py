"""Kalibrasyon kapisi: Climb-then-Cruise gercek donanimda ancak esikler
OLCULDUKTEN sonra acilabilir.

Neden bir test: real_system.yaml'daki vz_settle_m_s ve
attitude_rate_limit_deg_s dogrudan SENSOR GURULTU TABANINA oturuyor ve su an
TAHMIN (TODO isaretli). Kalibre edilmeden acilirsa state makinesi ILERLEMEZ --
CLIMB vertical_timeout_s'te duser, HOLD her bacakta tavani yer ve 600 s'lik
ZORUNLU gorev butcesi erir. Bayragi elle acmak tek satirlik bir degisiklik
oldugu icin, o satirin yanina bir kapi konuldu.

Kapi SU SEKILDE calisir: enabled True yapilabilir, ama ancak ilgili TODO
isaretleri kaldirilmissa -- yani degerler gercekten olculup yazilmissa.
Protokol: docs/climb-then-cruise-hw-checklist.md 1. bolum.
"""
import os

import pytest
import yaml

_STACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_YAML = os.path.join(_STACK, "real_system", "config", "real_system.yaml")
GZ_YAML = os.path.join(_STACK, "gz_system", "config", "gz_system.yaml")

#: Kalibre edilmeden acilmasi TEHLIKELI olan alanlar.
CALIBRATION_REQUIRED = ("vz_settle_m_s", "attitude_rate_limit_deg_s")


def _raw(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _motion(path):
    return yaml.safe_load(_raw(path))["motion_profile"]


def _todo_lines(path, keys):
    """Icinde TODO gecen ve verilen anahtarlardan birine ait olan satirlar."""
    out = []
    for line in _raw(path).splitlines():
        stripped = line.strip()
        if "TODO" in stripped and any(stripped.startswith(k + ":") for k in keys):
            out.append(stripped)
    return out


def test_real_profile_gate_is_consistent_with_calibration_state():
    """Kapi ile kalibrasyon durumu AYNI yonde olmali.

    enabled: false  + TODO'lar duruyor  -> tutarli (bugunku durum)
    enabled: true   + TODO'lar YOK      -> tutarli (kalibrasyon bitmis)
    enabled: true   + TODO'lar DURUYOR  -> TUTARSIZ, bu test duser
    """
    motion = _motion(REAL_YAML)
    pending = _todo_lines(REAL_YAML, CALIBRATION_REQUIRED)
    if motion["enabled"]:
        assert not pending, (
            "real_system.yaml'da motion_profile.enabled TRUE ama su esikler hala "
            f"TODO: {pending}. Once hover olcum protokolunu calistir "
            "(docs/climb-then-cruise-hw-checklist.md 1. bolum), degerleri olculen "
            "p95'in ~3 katina cek, TODO'lari olcum tarihi + log referansiyla kapat."
        )
    else:
        assert pending, (
            "enabled FALSE ama kalibrasyon TODO'lari da yok. Ikisinden biri "
            "yanlis: ya esikler olculdu ve kapi acilmali, ya da TODO isaretleri "
            "yanlislikla silindi."
        )


def test_sitl_profile_is_unaffected_by_the_gate():
    """Kapi YALNIZCA gercek donanim icin. SITL'de Climb-then-Cruise acik
    kalmali, aksi halde canli entegrasyon testi hicbir sey dogrulamaz."""
    assert _motion(GZ_YAML)["enabled"] is True, \
        "SITL profilinde Climb-then-Cruise kapali -- entegrasyon testi anlamsizlasir"


@pytest.mark.parametrize("field", CALIBRATION_REQUIRED)
def test_calibration_fields_exist_in_both_profiles(field):
    """Alanlar silinirse kapi sessizce anlamini yitirir."""
    assert field in _motion(REAL_YAML), f"real profilinde {field} yok"
    assert field in _motion(GZ_YAML), f"SITL profilinde {field} yok"


def test_disabled_profile_falls_back_to_the_legacy_path():
    """enabled False iken goto_waypoint eski goto_global_position_and_wait'e
    dusmeli -- yani kapi kapaliyken gercek ucus BILINEN bir zeminde yapilir."""
    import inspect
    from core.navigation.centering_controller import CenteringController
    src = inspect.getsource(CenteringController.goto_waypoint)
    assert "if not self.motion_profile.enabled:" in src
    gate = src.split("if not self.motion_profile.enabled:")[1]
    assert "goto_global_position_and_wait" in gate.split("machine")[0], \
        "kapi kapaliyken eski yola dusulmuyor"
