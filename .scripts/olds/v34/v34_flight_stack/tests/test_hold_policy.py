"""HOLD politikasi: "EN AZ 2 s VE STABIL" -- saf sleep DEGIL.

Operator talebi (2026-09-02, Blok 6) "sabit ~2 s hold yeterli" idi. Uygulama
bunu bir TABAN olarak aldi: min sure DOLDU **VE** attitude durgun. Bu dosya o
ayrimi pinliyor -- birisi ilerde guard'i kaldirip `asyncio.sleep(2)` yazarsa
burada duser.

parameters.py degerleri conftest.py tarafindan testler icin sifirlaniyor
(duvar saati maliyeti cikarilsin diye), bu yuzden sayisal esikler YAML
profillerinden okunuyor: onlar operasyonel gercek ve monkeypatch'ten
etkilenmiyorlar.
"""
import inspect
import os

import pytest
import yaml

from core.navigation import motion_fsm

_STACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = {
    "SITL": os.path.join(_STACK, "gz_system", "config", "gz_system.yaml"),
    "GERCEK": os.path.join(_STACK, "real_system", "config", "real_system.yaml"),
}


def _motion(profile_path):
    with open(profile_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["motion_profile"]


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_hold_floor_is_two_seconds(name):
    """Her iki ortam da AYRI AYRI config edilebilir olmali ve tabani 2 s."""
    assert _motion(PROFILES[name])["hold_min_s"] == 2.0, \
        f"{name}: hold_min_s 2.0 olmali (Blok 6)"


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_ceiling_leaves_room_for_the_guard(name):
    """Tavan tabana esit/yakin olursa guard fiilen devre disi kalir: her
    sallanan arac aninda tavana carpar ve stabilite hic beklenmemis olur.
    En az 2 s'lik gercek bir durulma penceresi olmali."""
    m = _motion(PROFILES[name])
    headroom = m["hold_max_s"] - m["hold_min_s"]
    assert headroom >= 2.0, \
        f"{name}: guard'a yalnizca {headroom}s kaliyor -- tavani yukselt"


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_attitude_guard_is_still_configured(name):
    """Guard'in parametreleri hala profilde -- silinmemis."""
    m = _motion(PROFILES[name])
    assert m["attitude_rate_limit_deg_s"] > 0
    assert m["attitude_stable_samples"] >= 1


def test_hold_is_not_a_plain_sleep():
    """YAPISAL: _run_hold hala attitude okuyup stabilite sayiyor olmali.

    Bu testin varlik sebebi, talebin "2 s yeterli" diye okunup guard'in
    silinmesi riski. Silinirse asagidaki isaretler kaybolur."""
    src = inspect.getsource(motion_fsm.MotionStateMachine._run_hold)
    assert "get_attitude_euler" in src, "HOLD artik attitude okumuyor -- guard kaldirilmis"
    assert "attitude_stable_samples" in src, "ardisik-stabil ornek sayaci kaldirilmis"
    assert "attitude_rate_limit_deg_s" in src, "rate esigi kaldirilmis"
    assert "hold_max" in src or "max_s" in src, "emniyet tavani kaldirilmis"


def test_hold_still_requires_both_conditions():
    """Cikis kosulu 'min sure DOLDU **VE** (degraded ya da stabil)' olmali."""
    src = inspect.getsource(motion_fsm.MotionStateMachine._run_hold)
    assert "elapsed >= min_s" in src, "minimum sure kosulu yok"
    assert "stable_run >=" in src, "stabilite kosulu yok"
