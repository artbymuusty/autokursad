"""Entegrasyon testleri icin ust conftest'in hizlandirmalarini GERI ALIR.

tests/conftest.py'deki autouse fixture'lar tum alt dizinlere de uygulanir --
tests/integration/ dahil. Bu, birim testleri icin dogru (duvar saati
maliyetini cikarip DAVRANISI olcuyorlar) ama canli SITL testi icin YANLIS:

  _fast_motion_profile MOTION_LEG_TIMEOUT_S'i 1.0 s'ye cekiyor. Gercek bir
  arac 25 m'lik bir bacagi 1 saniyede ucamaz. Olculdu 2026-09-02: test
  "bacak yakinsamadi" ile dustu, uctugu sure toplam 14.57 s idi -- hata
  makinede degil, testin butcesindeydi.

Entegrasyon testinin butun amaci URETIM esikleriyle gercek arac altinda ne
oldugunu gormek, o yuzden burada varsayilanlar PARAMETERS.PY'DEN gelmeli.
Ayni adla yeniden tanimlamak pytest'te ust conftest'teki fixture'i golgeler.
"""
import pytest


@pytest.fixture(autouse=True)
def _fast_motion_profile():
    """No-op: uretim MOTION_* degerleri aynen kalsin."""
    yield


@pytest.fixture(autouse=True)
def _no_mission_start_hold():
    """No-op: ADR-007'nin gercek-ucus oturma gecikmesi canli testte GECERLI."""
    yield


@pytest.fixture(autouse=True)
def _no_mission_resume_spacing():
    """No-op: ADR-009'un resume araligi canli testte GECERLI."""
    yield
