"""gz_system/camera_service.py -- topic kesfi ve kare-aclik testleri.

KOK NEDEN (2026-08-25): resolve_camera_topic() TEK ATISLIK bir `gz topic -l`
calistiriyordu. Kamera sensoru topic'i sim ayaga kalktiktan ~6-9 s SONRA
advertise ediliyor (olculdu, 3/3 kosu); o pencerede cagrilirsa fonksiyon
yapilandirilmis topic'e geri duser ve BIR DAHA denemezdi. gz-transport var
olmayan bir topic'e abone olmaya IZIN VERDIGI icin subscribe() True doner,
servis "Service is running." yazar ve sonsuza kadar sifir kare uretir --
Gorev2Orchestrator.vision 0.3 s icinde DOWN'a duser.

Bu testler duzeltmenin uc ayagini da sabitler:
  1. kesif BEKLER (tek atis degil)
  2. abone olup kare gelmemesi FARK EDILIR (CameraStarvationError)
  3. watchdog topic'i YENIDEN cozer (dongu icinde)

gz Python binding'leri venv'de yok (sistem Gazebo kurulumuna bagli;
camera_service_manager.py PYTHONPATH'i sadece alt surec icin enjekte eder),
bu yuzden modul stub'lanarak yukleniyor.
"""
import importlib.util
import os
import sys
import types

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(os.path.dirname(_HERE), "camera_service.py")


def _load_camera_service():
    """gz binding'lerini stub'layarak camera_service.py'yi yukler."""
    if "gz" not in sys.modules:
        gz = types.ModuleType("gz")
        transport = types.ModuleType("gz.transport13")
        transport.Node = lambda *a, **k: types.SimpleNamespace(
            subscribe=lambda *a, **k: True)
        msgs = types.ModuleType("gz.msgs10")
        image_pb2 = types.ModuleType("gz.msgs10.image_pb2")
        image_pb2.Image = type("Image", (), {})
        sys.modules.update({"gz": gz, "gz.transport13": transport,
                            "gz.msgs10": msgs, "gz.msgs10.image_pb2": image_pb2})
    spec = importlib.util.spec_from_file_location("camera_service_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_camera_service()

LIVE = "/world/default/model/x500_mono_cam_down_0/link/camera_link/sensor/camera/image"
OTHER = "/world/default/model/x500_other_0/link/camera_link/sensor/camera/image"
NOISE = ["/clock", "/stats", "/world/default/clock"]


class _FakeClock:
    """Gercek zaman beklemeden deadline mantigini surer."""
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


def _stub_listing(monkeypatch, sequence):
    """`gz topic -l` sonuclarini sirayla doner; son eleman tekrarlanir."""
    calls = {"n": 0}

    def fake(env, timeout_s):
        i = min(calls["n"], len(sequence) - 1)
        calls["n"] += 1
        return sequence[i]
    monkeypatch.setattr(mod, "_list_topics_once", fake)
    return calls


# =============================================================================
# KOK NEDEN: kesif BEKLEMELI
# =============================================================================

def test_topic_gec_yayina_girerse_BEKLENIR(monkeypatch):
    """ASIL DUZELTME: topic ilk yoklamada yoksa vazgecilmez."""
    clock = _FakeClock()
    calls = _stub_listing(monkeypatch, [NOISE, NOISE, NOISE, NOISE + [LIVE]])
    got = mod.resolve_camera_topic(LIVE, discovery_limit_s=30.0,
                                   sleep=clock.sleep, clock=clock.monotonic)
    assert got == LIVE
    assert calls["n"] == 4, "topic gorunene kadar yoklamali"


def test_topic_zaten_yayindaysa_BEKLEMEZ(monkeypatch):
    clock = _FakeClock()
    calls = _stub_listing(monkeypatch, [NOISE + [LIVE]])
    got = mod.resolve_camera_topic(LIVE, discovery_limit_s=30.0,
                                   sleep=clock.sleep, clock=clock.monotonic)
    assert got == LIVE
    assert calls["n"] == 1
    assert clock.t == 0.0, "canli topic icin hic beklenmemeli"


def test_sure_dolunca_geri_duser_ama_SONSUZA_KADAR_BEKLEMEZ(monkeypatch):
    clock = _FakeClock()
    _stub_listing(monkeypatch, [NOISE])
    got = mod.resolve_camera_topic(LIVE, discovery_limit_s=5.0,
                                   sleep=clock.sleep, clock=clock.monotonic)
    assert got == LIVE                     # eski davranis: yapilandirilmisa duser
    assert clock.t >= 5.0                  # ama once gercekten bekledi
    assert clock.t < 6.0                   # ve siniri asmadi


def test_gz_cli_bozuksa_yoklamaz(monkeypatch):
    """`gz topic -l` calismiyorsa yoklamanin anlami yok -- hemen don."""
    clock = _FakeClock()
    monkeypatch.setattr(mod, "_list_topics_once", lambda env, t: None)
    got = mod.resolve_camera_topic(LIVE, discovery_limit_s=30.0,
                                   sleep=clock.sleep, clock=clock.monotonic)
    assert got == LIVE
    assert clock.t == 0.0


def test_bos_liste_ile_cli_hatasi_AYRI_ele_alinir(monkeypatch):
    """Bos liste 'henuz advertise etmedi' demek -- yoklamaya devam."""
    clock = _FakeClock()
    calls = _stub_listing(monkeypatch, [[], [], NOISE + [LIVE]])
    got = mod.resolve_camera_topic(LIVE, discovery_limit_s=30.0,
                                   sleep=clock.sleep, clock=clock.monotonic)
    assert got == LIVE
    assert calls["n"] == 3


# =============================================================================
# Son-ek eslesmesi (model varyanti dayanikliligi)
# =============================================================================

def test_farkli_model_varyanti_son_ekle_bulunur():
    assert mod._match_camera_topic(LIVE, NOISE + [OTHER]) == OTHER


def test_birden_fazla_aday_varsa_ilki_secilir():
    assert mod._match_camera_topic("/yok", NOISE + [LIVE, OTHER]) == LIVE


def test_aday_yoksa_None():
    assert mod._match_camera_topic(LIVE, NOISE) is None


def test_tam_eslesme_son_ek_taramasindan_once_gelir():
    assert mod._match_camera_topic(LIVE, [OTHER, LIVE]) == LIVE


# =============================================================================
# "Abone oldum" != "kare akiyor"
# =============================================================================

class _FakeSocket:
    """ZMQ PUB yerine gecer. send_after kadar kare gonderince dongu durur."""
    def __init__(self, service=None, stop_after=None):
        self.sent = 0
        self.closed = False
        self._service = service
        self._stop_after = stop_after

    def bind(self, addr):
        pass

    def send(self, data):
        self.sent += 1
        if self._stop_after is not None and self.sent >= self._stop_after:
            self._service.running = False

    def close(self):
        self.closed = True


class _FakeCtx:
    def term(self):
        pass


def _service(monkeypatch, starvation_s):
    monkeypatch.setattr(mod, "_FRAME_STARVATION_LIMIT_S", starvation_s)
    svc = mod.CameraService(LIVE, "tcp://127.0.0.1:65001")
    svc.node = types.SimpleNamespace(subscribe=lambda *a, **k: True)
    svc.context = _FakeCtx()
    return svc


def test_kare_gelmezse_ACLIK_hatasi(monkeypatch):
    """ASIL SESSIZ ARIZA: subscribe() True dondu ama kare yok."""
    svc = _service(monkeypatch, 0.05)
    svc.socket = _FakeSocket()
    with pytest.raises(mod.CameraStarvationError) as ei:
        svc.start()
    assert "never started" in str(ei.value)
    assert LIVE in str(ei.value)


def test_aclik_hatasi_RuntimeError_TUREVI():
    """Watchdog `except RuntimeError` yakaliyor -- turemezse retry olmaz."""
    assert issubclass(mod.CameraStarvationError, RuntimeError)


def test_kare_akarken_ACLIK_HATASI_YOK(monkeypatch):
    svc = _service(monkeypatch, 5.0)
    svc.socket = _FakeSocket(service=svc, stop_after=3)
    import numpy as np
    svc.latest_frame = np.zeros((4, 4, 3), dtype=np.uint8)

    real_send = svc.socket.send

    def send_and_refeed(data):
        real_send(data)
        svc.latest_frame = np.zeros((4, 4, 3), dtype=np.uint8)  # akis devam ediyor
    svc.socket.send = send_and_refeed

    svc.start()                      # hata YOK
    assert svc.socket.sent >= 3


def test_subscribe_basarisizsa_RuntimeError(monkeypatch):
    """Mevcut davranis korunmali: subscribe False -> watchdog retry."""
    svc = _service(monkeypatch, 5.0)
    svc.socket = _FakeSocket()
    svc.node = types.SimpleNamespace(subscribe=lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        svc.start()


# =============================================================================
# Watchdog YAPISI: topic dongunun ICINDE cozulmeli
# =============================================================================

def test_watchdog_topici_YENIDEN_cozer():
    """Yapisal regresyon kalkani (AST, metin eslesmesi degil).

    Eski kod `resolved_topic = resolve_camera_topic(...)` cagrisini
    `while True:` dongusunun DISINDA yapiyordu; bu yuzden yanlis cozulmus
    bir topic'ten donus YOKTU. Cagri dongunun icinde kalmali.
    """
    import ast
    tree = ast.parse(open(_SCRIPT, encoding="utf-8").read())

    def walk_whiles(node):
        for child in ast.walk(node):
            if isinstance(child, ast.While):
                yield child

    resolves_in_loop = False
    for loop in walk_whiles(tree):
        for c in ast.walk(loop):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == "resolve_camera_topic"):
                resolves_in_loop = True
    assert resolves_in_loop, "resolve_camera_topic watchdog dongusunun ICINDE olmali"
