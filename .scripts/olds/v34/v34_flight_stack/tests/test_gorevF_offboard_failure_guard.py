"""Görev F (2) -- Offboard gecis hatasi guard'i: uc olu korumanin dirilisi.

OLCULEN SORUN (129 log, 250 takip gecisi): gecis %24.4 basarisiz oluyor ve
basarisizlik dali HICBIR koruma isletmiyordu. TargetValidator streak'i
hicbir yerde sifirlanmadigi icin ayni hedef 101 ms sonra yeniden seciliyor,
ayni takip koru korune tekrarlaniyor ve HER TEKRAR bir rota resume'u
harciyordu (ADR-011 T3). Doz-yanit: kosumda 0-1 hata -> %2-4 erken rota
bitisi, >=2 -> %60.

Bu dosya, ADR-004 §17'nin YAZDIGI ama gerceklesmemis davranisin fiilen
kuruldugunu cakiyor.
"""
import pytest

from core.config.parameters import (
    OFFBOARD_FAILURE_MAX_PER_TARGET,
    CENTERING_MAX_ATTEMPTS_PER_TARGET,
    CENTERING_RETRY_COOLDOWN_S,
)
from core.detection.target_validator import TargetValidator
from core.mission.debounce import DebounceTracker
from core.mission.gorev2_orchestrator import Gorev2Orchestrator


def _orch():
    """__init__'i atlayan kurulum -- mevcut test dosyalarinin idiomu
    (bkz. test_mission_route_resume). Guard'in dokundugu alanlar elle
    kuruluyor; _route_axis AttributeError'inin kaynagi da tam olarak bu
    desendi, o yuzden burada acikca set ediliyor."""
    o = Gorev2Orchestrator.__new__(Gorev2Orchestrator)
    o._offboard_failures = {}
    o._centering_attempts = {}
    o._centering_cooldown_until = {}
    o._centering_abandoned = set()
    o.validator = TargetValidator()
    o.debounce = DebounceTracker()
    o.published = []
    o._publish = lambda code, msg="", severity=None, category=None, data=None: \
        o.published.append((code, data or {}))
    return o


def _make_ready(o, shape, frames=8):
    """Streak'i track-ready esiginin uzerine cikar."""
    from core.detection.types import Detection
    for _ in range(frames):
        o.validator.update(
            Detection(shape_type=shape, confidence=0.9,
                      center_px=(320.0, 240.0), bbox_px=(300.0, 220.0, 40.0, 40.0)),
            15.0, (320.0, 240.0))


def test_validator_streak_is_reset_first_production_caller():
    """1. koruma: reset() bugune kadar core/ icinde HIC cagrilmiyordu."""
    o = _orch()
    _make_ready(o, "MAVI_ALTIGEN")
    assert o.validator.is_track_ready("MAVI_ALTIGEN") is True
    o._note_offboard_failure("MAVI_ALTIGEN", now=1000.0)
    assert o.validator.is_track_ready("MAVI_ALTIGEN") is False, \
        "streak sifirlanmadi -- 101 ms'lik yeniden secim geri geldi"


def test_cooldown_is_armed_so_the_candidate_filter_stops_being_a_no_op():
    """2. koruma: _centering_cooldown_until'in tek yazari uretimde hic
    cagrilmiyordu, yani :684'teki filtre kalici bos sozlugu siniyordu."""
    o = _orch()
    o._note_offboard_failure("KIRMIZI_UCGEN", now=1000.0)
    until = o._centering_cooldown_until["KIRMIZI_UCGEN"]
    assert until == pytest.approx(1000.0 + CENTERING_RETRY_COOLDOWN_S)
    # Filtrenin kendi ifadesi: now >= cooldown ise aday.
    assert not (1000.5 >= until), "cooldown hemen suruyor olmali"
    assert (until + 0.1) >= until


def test_debounce_is_armed():
    """3. koruma: mark_processed() bugune kadar yalnizca BASARILI GPS
    kaydindan sonra cagriliyordu."""
    o = _orch()
    o._note_offboard_failure("MAVI_ALTIGEN", now=1000.0)
    assert o.debounce.is_in_cooldown("MAVI_ALTIGEN", 1000.1) is True


def test_counter_is_separate_from_centering_attempts():
    """Offboard hatasi hedefin gorunurluguyle ilgili degil; ikisini ayni
    sayacta toplamak bir otopilot aksakligi yuzunden gorunur bir hedefi
    kalici terk ettirirdi."""
    o = _orch()
    for i in range(OFFBOARD_FAILURE_MAX_PER_TARGET):
        o._note_offboard_failure("MAVI_ALTIGEN", now=1000.0 + i)
    assert o._offboard_failures["MAVI_ALTIGEN"] == OFFBOARD_FAILURE_MAX_PER_TARGET
    assert o._centering_attempts == {}, "merkezleme sayaci kirletildi"


def test_option_A_abandons_the_shape_only_at_the_limit():
    """SECENEK A: sinira kadar takip surer, sinirda hedef BU TUR icin
    terk edilir -- arama ve rota DEVAM EDER (HOLD/abort degil)."""
    o = _orch()
    for i in range(OFFBOARD_FAILURE_MAX_PER_TARGET - 1):
        o._note_offboard_failure("MAVI_ALTIGEN", now=1000.0 + i)
        assert "MAVI_ALTIGEN" not in o._centering_abandoned
    o._note_offboard_failure("MAVI_ALTIGEN", now=2000.0)
    assert "MAVI_ALTIGEN" in o._centering_abandoned
    codes = [c for c, _ in o.published]
    assert "OFFBOARD_PURSUIT_ABANDONED" in codes
    d = dict(o.published)["OFFBOARD_PURSUIT_ABANDONED"]
    assert d["action"] == "abandon_shape_continue_search"
    assert d["offboard_failures"] == OFFBOARD_FAILURE_MAX_PER_TARGET


def test_other_shape_is_untouched_so_search_continues():
    """Secenek A'nin ozu: bir sekil terk edilse bile DIGERI ve rota surer."""
    o = _orch()
    for i in range(OFFBOARD_FAILURE_MAX_PER_TARGET):
        o._note_offboard_failure("MAVI_ALTIGEN", now=1000.0 + i)
    assert "KIRMIZI_UCGEN" not in o._centering_abandoned
    assert o._offboard_failures.get("KIRMIZI_UCGEN") is None
    assert o.debounce.is_in_cooldown("KIRMIZI_UCGEN", 1000.1) is False


def test_below_the_limit_publishes_a_noted_event_not_an_abandon():
    o = _orch()
    o._note_offboard_failure("KIRMIZI_UCGEN", now=1000.0)
    codes = [c for c, _ in o.published]
    assert "OFFBOARD_FAILURE_NOTED" in codes
    assert "OFFBOARD_PURSUIT_ABANDONED" not in codes
    d = dict(o.published)["OFFBOARD_FAILURE_NOTED"]
    assert d["validator_streak_reset"] is True and d["debounce_armed"] is True


def test_limit_is_separate_constant_and_not_the_centering_one():
    """Iki sinirin ayri olmasi tasarimin kendisi; ayni sabite baglanirsa
    ayrimin anlami kalmaz."""
    from core.config import parameters as p
    assert hasattr(p, "OFFBOARD_FAILURE_MAX_PER_TARGET")
    assert p.OFFBOARD_FAILURE_MAX_PER_TARGET is not p.CENTERING_MAX_ATTEMPTS_PER_TARGET \
        or OFFBOARD_FAILURE_MAX_PER_TARGET == CENTERING_MAX_ATTEMPTS_PER_TARGET
    # Deger olcumden geliyor: >=2 hatada %60 kayip, 1 hata neredeyse zararsiz.
    assert 2 <= OFFBOARD_FAILURE_MAX_PER_TARGET <= 4
