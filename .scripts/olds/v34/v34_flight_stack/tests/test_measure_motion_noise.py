"""Hover gurultu olcum aracinin MATEMATIGI.

Bu testler ucus GEREKTIRMEZ ve kasitli olarak boyle: kalibrasyon esikleri
bu hesaptan turetiliyor, yani p95 yanlissa gercek ucusta yanlis bir esik
kullanilir. Hesabin dogrulugu bir SITL kosumunun "calisti gibi gorundu"
izlenimine birakilamaz.
"""
import math

import pytest

from tools.measure_motion_noise import (
    RECOMMENDATION_MARGIN,
    attitude_rates,
    percentile,
    summarise,
)


# --------------------------------------------------------------------------
# percentile -- numpy'nin varsayilan 'linear' yontemiyle ayni olmali
# --------------------------------------------------------------------------

def test_percentile_matches_linear_interpolation_reference():
    data = list(range(1, 11))              # 1..10
    # rank = 0.95 * (10-1) = 8.55 -> 9 + 0.55*(10-9) = 9.55
    assert percentile(data, 95) == pytest.approx(9.55)
    # rank = 0.50 * 9 = 4.5 -> 5 + 0.5*(6-5) = 5.5
    assert percentile(data, 50) == pytest.approx(5.5)
    assert percentile(data, 0) == pytest.approx(1.0)
    assert percentile(data, 100) == pytest.approx(10.0)


def test_percentile_is_order_independent():
    shuffled = [7, 2, 9, 1, 5, 10, 3, 8, 4, 6]
    assert percentile(shuffled, 95) == pytest.approx(9.55)


def test_percentile_edge_cases():
    assert percentile([], 95) is None
    assert percentile([4.2], 95) == pytest.approx(4.2)


# --------------------------------------------------------------------------
# attitude_rates
# --------------------------------------------------------------------------

def _sample(t, roll, pitch, **kw):
    return {"t": t, "roll_deg": roll, "pitch_deg": pitch, "yaw_deg": 0.0, "vz": 0.0, **kw}


def test_rate_uses_real_dt_not_nominal_period():
    """Bir link tikanmasi 0.1 s yerine 0.4 s birakirsa sabit dt kullanmak
    sahte bir 4x rate uretirdi."""
    samples = [_sample(0.0, 0.0, 0.0), _sample(0.4, 2.0, 0.0)]
    rates = attitude_rates(samples)
    assert len(rates) == 1
    assert rates[0]["roll_rate"] == pytest.approx(5.0)     # 2 deg / 0.4 s
    assert rates[0]["dt"] == pytest.approx(0.4)


def test_rate_takes_the_larger_of_roll_and_pitch():
    samples = [_sample(0.0, 0.0, 0.0), _sample(0.1, 0.5, 3.0)]
    rates = attitude_rates(samples)
    assert rates[0]["pitch_rate"] == pytest.approx(30.0)
    assert rates[0]["max_rate"] == pytest.approx(30.0)


def test_rate_chain_breaks_across_a_stale_gap():
    """Bayat bir ornegin USTUNDEN turev alinmamali: iki taze ornek arasinda
    bilinmeyen bir bosluk varsa aradaki fark bir HIZ degildir."""
    samples = [
        _sample(0.0, 0.0, 0.0),
        {"t": 0.1, "stale": True, "reason": "link"},
        _sample(0.2, 30.0, 0.0),
        _sample(0.3, 30.5, 0.0),
    ]
    rates = attitude_rates(samples)
    # 0.0->0.2 arasi (30 deg atlama) SAYILMAMALI; yalnizca 0.2->0.3 kalir.
    assert len(rates) == 1
    assert rates[0]["roll_rate"] == pytest.approx(5.0)     # 0.5 deg / 0.1 s


def test_rate_handles_angle_wrap():
    """+179 -> -179 gercekte 2 derecelik bir harekettir, 358 degil.
    Sarma dogru islenmezse guard sabit duran bir araci 'sallaniyor' sanar."""
    samples = [_sample(0.0, 179.0, 0.0), _sample(0.1, -179.0, 0.0)]
    rates = attitude_rates(samples)
    assert rates[0]["roll_rate"] == pytest.approx(20.0)    # 2 deg / 0.1 s


# --------------------------------------------------------------------------
# summarise
# --------------------------------------------------------------------------

def test_summary_recommends_p95_times_margin():
    samples = [_sample(i * 0.1, 0.0, 0.0, vz=0.01 * i) for i in range(101)]
    summary = summarise(samples)
    vz_p95 = summary["vz_abs_m_s"]["p95"]
    assert summary["recommended"]["vz_settle_m_s"] == pytest.approx(
        round(vz_p95 * RECOMMENDATION_MARGIN, 3))
    assert summary["recommendation_margin"] == RECOMMENDATION_MARGIN


def test_summary_excludes_stale_samples_from_statistics():
    samples = [
        _sample(0.0, 0.0, 0.0, vz=0.1),
        {"t": 0.1, "stale": True, "reason": "link"},
        _sample(0.2, 0.0, 0.0, vz=0.3),
    ]
    summary = summarise(samples)
    assert summary["sample_count"] == 3
    assert summary["stale_count"] == 1
    assert summary["vz_abs_m_s"]["n"] == 2         # bayat olan sayilmadi


def test_summary_uses_absolute_vz():
    """Asagi ve yukari gurultu ayni tabana aittir; isaret tasimak p95'i
    yapay olarak kucultur."""
    samples = [_sample(i * 0.1, 0.0, 0.0, vz=(-1) ** i * 0.2) for i in range(20)]
    summary = summarise(samples)
    assert summary["vz_abs_m_s"]["p50"] == pytest.approx(0.2)


def test_summary_survives_a_recording_with_no_usable_samples():
    samples = [{"t": 0.0, "stale": True}, {"t": 0.1, "stale": True}]
    summary = summarise(samples)
    assert summary["vz_abs_m_s"] is None
    assert summary["recommended"]["vz_settle_m_s"] is None
