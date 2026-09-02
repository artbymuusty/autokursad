"""Uc composition root (main_gz / main_real / main_dual) ayni parcalari kuruyor mu.

Denetim (docs/v34-sistem-denetimi.md) su hatalarin hepsinin ayni sinifta
oldugunu gosterdi: bir mimari degisiklik main_gz.py'ye uygulandi, digerlerine
uygulanmadi ve fark SIMULASYONDA GORUNMEDIGI icin aylarca fark edilmedi.

  B1  VisionRuntime yalnizca main_gz'de kuruluyordu -> gercek/dual vision KOR
  B4  sinyal isleyicileri yalnizca main_gz'de -> gercek ucusta arac havada kalabilir
  B5  Gorev3PickupPhase'e publisher yalnizca main_gz'de geciliyordu
  B6  Gorev3PickupPhase'e FeedDetector yerine ham detector geciliyordu

Bu testler o SINIFI kapatiyor: davranisi degil, KOMPOZISYONU pinliyorlar.
Bir entrypoint ilerde bir parcayi unutursa burada duser -- arac ucurmaya
gerek kalmadan.

AST uzerinden calisiyor (metin eslestirme degil), yani bicimlendirme
degisiklikleri testi kirmaz.
"""
import ast
import os

import pytest

_STACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENTRYPOINTS = {
    "main_gz": os.path.join(_STACK, "gz_system", "main_gz.py"),
    "main_real": os.path.join(_STACK, "real_system", "main_real.py"),
    "main_dual": os.path.join(_STACK, "dual_system", "main_dual.py"),
}


def _tree(path):
    with open(path, "r", encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=path)


def _called_names(tree):
    """Cagrilan her seyin adi: `Foo(...)` -> "Foo", `a.b(...)` -> "b"."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
    return names


def _calls_to(tree, name):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == name) or \
               (isinstance(func, ast.Attribute) and func.attr == name):
                out.append(node)
    return out


@pytest.fixture(scope="module", params=sorted(ENTRYPOINTS), ids=lambda k: k)
def entry(request):
    name = request.param
    return name, _tree(ENTRYPOINTS[name])


def test_constructs_vision_runtime(entry):
    """B1: VisionRuntime uretimde DetectionFeed'in TEK ureticisi
    (DetectionFeed.publish yalnizca vision_runtime.py'den cagriliyor).
    Kurulmazsa besleme hic dolmaz ve gorev kor ucar."""
    name, tree = entry
    assert "VisionRuntime" in _called_names(tree), \
        f"{name}: VisionRuntime kurulmuyor -- detection_feed hic dolmaz (denetim B1)"


def test_starts_the_vision_runtime(entry):
    """Kurmak yetmez: ADR-010 P3 vision'i TUM gorev boyunca yasatiyor."""
    name, tree = entry
    assert "start" in _called_names(tree), f"{name}: vision.start() cagrilmiyor"


def test_constructs_feed_detector(entry):
    """B6: IDetector arayuzu isteyen bilesenler ham detector degil
    FeedDetector almali -- aksi halde HSVContourDetector'in streak durumuna
    IKINCI bir detect() cagirani girer (ADR-008 B1)."""
    name, tree = entry
    assert "FeedDetector" in _called_names(tree), \
        f"{name}: FeedDetector kurulmuyor (denetim B6)"


def test_pickup_phase_gets_feed_detector_not_raw_detector(entry):
    """Gorev3PickupPhase'in ucuncu konumsal argumani feed_detector olmali."""
    name, tree = entry
    calls = _calls_to(tree, "Gorev3PickupPhase")
    assert calls, f"{name}: Gorev3PickupPhase hic kurulmuyor"
    for call in calls:
        assert len(call.args) >= 3, f"{name}: Gorev3PickupPhase cagrisi beklenenden kisa"
        third = call.args[2]
        assert isinstance(third, ast.Name) and third.id == "feed_detector", \
            (f"{name}: Gorev3PickupPhase ham detector aliyor "
             f"({ast.dump(third)[:60]}) -- FeedDetector olmali (denetim B6)")


def test_pickup_phase_gets_a_publisher(entry):
    """B5: publisher gecilmezse bu fazin olaylari telemetriye/dashboard'a
    hic dusmez -- gorev sessizce gozlemlenemez hale gelir."""
    name, tree = entry
    for call in _calls_to(tree, "Gorev3PickupPhase"):
        kwargs = {kw.arg for kw in call.keywords}
        assert "publisher" in kwargs, \
            f"{name}: Gorev3PickupPhase publisher almiyor (denetim B5)"


def test_installs_signal_handlers(entry):
    """B4 / ADR-010 R4: arka planda baslatilan surec SIGINT = SIG_IGN miras
    alir; ezilmezse `kill -INT` yutulur ve arac HAVADA kalir.

    Iki mesru bicim var, ikisi de ayni ortak fonksiyona varir:
      * dogrudan install_signal_handlers(...) cagirmak (main_real/main_dual'in
        Linux dali, _run_with_shutdown icinde), ya da
      * run_with_main_thread_gui(...) cagirmak -- o pompa isleyicileri KENDISI
        kurar (core/runtime/main_thread_gui.py).
    main_gz 2026-09-02'de pompayi ortak module devrettigi icin ikinci bicimi
    kullaniyor."""
    name, tree = entry
    called = _called_names(tree)
    assert ("install_signal_handlers" in called
            or "run_with_main_thread_gui" in called), \
        f"{name}: sinyal isleyicisi kuran hicbir yol cagrilmiyor (denetim B4)"


def test_injects_the_motion_profile(entry):
    """Climb-then-Cruise esikleri (kalibrasyon kapisi dahil) her entrypoint'te
    config'ten enjekte edilmeli -- biri unutursa o yol parameters.py
    varsayilanlariyla, yani kapi ACIK halde ucar."""
    name, tree = entry
    assert "from_config" in _called_names(tree), \
        f"{name}: MotionProfile.from_config cagrilmiyor"


def test_has_a_macos_main_thread_paint_pump(entry):
    """B3 / ADR-006: macOS'ta dashboard cv2.imshow yerine MAIN_THREAD_PAINT'e
    yayin yapar (dashboard.py:287). Kopruyu ANA THREAD'de bosaltan bir pompa
    yoksa kareler yazilir, kimse okumaz ve hicbir pencere acilmaz -- gercek
    ucusta operatorun tek ekrani odur.

    Iki mesru bicim var: main_gz kendi _run_with_main_thread_gui'sini tasiyor
    (kopruyu dogrudan bosaltir), main_real/main_dual ortak
    core/runtime/main_thread_gui.run_with_main_thread_gui'yi cagirir."""
    name, tree = entry
    called = _called_names(tree)
    drains_bridge = "take" in called                       # MAIN_THREAD_PAINT.take()
    uses_shared_pump = "run_with_main_thread_gui" in called
    assert drains_bridge or uses_shared_pump, \
        f"{name}: macOS ana-thread boyama pompasi yok (denetim B3)"


def test_branches_on_darwin(entry):
    """Pompa YALNIZCA macOS'ta gerekli; Linux/Windows'ta dashboard kendi
    thread'inde boyar. Platform dali yoksa ya pompa hic calismaz ya da
    Linux'ta gereksiz yere thread'e tasinir."""
    name, tree = entry
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "darwin" in literals, f"{name}: platform dali yok (ADR-006)"
