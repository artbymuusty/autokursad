"""tools/calibrate_real_servos.py testleri.

Bu script GERÇEK DONANIMA komut gönderiyor, yani testin işi "çalışıyor mu"
değil, **ne YAPMADIĞINI** kanıtlamak:

  1. --dry-run gerçekten kuru: MAVSDK'ya hiç dokunulmaz (bağlantı kurma
     yolu çağrılırsa test patlar) ve hiçbir actuator komutu gitmez.
  2. Güvenlik kapısı komuttan ÖNCE çalışır -- RealPayloadBackend'in
     CALIBRATION GUARD testiyle aynı mantık: sıra yanlışsa donanım
     operatör hazır olmadan hareket eder.
  3. Script hiçbir FLEX'i YAZMAZ. payload_config bu testlerin başında ve
     sonunda birebir aynı kalır.
  4. Ham veri formatı doğru: her satır CSV şemasına uyar, verdict'ler
     operatörün gerçekten verdiği cevabı taşır, uydurma yok.

Operatör simülasyonu için GERÇEK OperatorConsole kullanılır (girdi bir
StringIO'dur) -- sahte bir console, konsolun kendi doğrulama mantığını
(geçersiz cevabı yeniden sorma, EOF'u iptal sayma) test dışında bırakırdı.
"""
import csv
import importlib.util
import io
import os

import pytest

from payload import payload_config
from payload.backends.real_payload_backend import REQUIRED_FLEX_NAMES

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "calibrate_real_servos.py")


def _load_module():
    """Script'i dosyadan yukler. tools/ bir paket DEGIL ve oyle olmasi da
    gerekmiyor -- bench araclari tek dosya olarak calistirilir; bu yukleme
    bicimi tam olarak o kullanimi sinar."""
    spec = importlib.util.spec_from_file_location("calibrate_real_servos", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _console(answers):
    """Operatorun sirayla verecegi cevaplarla bir OperatorConsole kurar.
    Cikti yutulur; testler ciktiyi ayrica inceleyebilsin diye dondurulur."""
    out = io.StringIO()
    return mod.OperatorConsole(io.StringIO("".join(f"{a}\n" for a in answers)), out), out


class _SpyAction:
    """set_actuator cagrilarini SIRAYLA kaydeder. raise_on: bu index'te
    ActionError benzeri bir hata firlatir (RPC reddi yolu)."""

    def __init__(self, raise_on=None):
        self.calls = []
        self._raise_on = raise_on

    async def set_actuator(self, index, value):
        self.calls.append((index, value))
        if self._raise_on is not None and index == self._raise_on:
            raise RuntimeError("COMMAND_DENIED")


@pytest.fixture(autouse=True)
def _flex_must_stay_untouched():
    """Her testten SONRA FLEX-14..19'un hala TBD oldugunu dogrular.
    Script'in 'config'e yazma' kabiliyeti hic olmamali; bu fixture o
    sozlesmeyi TUM testlere otomatik uygular."""
    before = {name: getattr(payload_config, name) for name in REQUIRED_FLEX_NAMES}
    yield
    after = {name: getattr(payload_config, name) for name in REQUIRED_FLEX_NAMES}
    assert after == before, (
        f"Script payload_config'i DEGISTIRDI: {before} -> {after}. Bu script "
        f"HAM VERI uretir, kalibrasyon karari operatorundur.")


# --- 1. --dry-run gercekten kuru mu ----------------------------------------

def test_dry_run_never_touches_mavsdk(tmp_path, monkeypatch):
    """--dry-run MAVSDK baglantisini KURMAMALI. connect_real_action
    cagrilirsa test patlar -- bayrak kontrolune degil, cagri grafigine
    bakiyoruz."""
    def _explode(*args, **kwargs):
        raise AssertionError("--dry-run modunda MAVSDK baglantisi KURULDU!")

    monkeypatch.setattr(mod, "connect_real_action", _explode)
    monkeypatch.setattr("sys.stdin", io.StringIO("\nn\n\nn\n"))

    out = tmp_path / "kuru.csv"
    assert mod.main(["--dry-run", "--out", str(out),
                     "index", "--servo", "Servo2", "--indices", "1", "2",
                     "--probe-value", "0.3"]) == 0
    assert out.exists()


@pytest.mark.asyncio
async def test_dry_run_action_records_but_sends_nothing():
    """DryRunAction ne gonderecegini yazar, gercek bir RPC yapmaz.
    Kaydettigi komutlar prosedurun dogru surdugunun kanitidir."""
    console, out = _console(["", "n", "", "y"])
    action = mod.DryRunAction(console)
    session = mod.CalibrationSession(action, console, dry_run=True)

    await session.run_index_sweep("Servo3", [3, 4], probe_value=0.2)

    assert action.calls == [(3, 0.2), (4, 0.2)]
    assert "GONDERILMEDI" in out.getvalue()
    assert session.candidates() == {"FLEX_15_SERVO3_ACTUATOR_INDEX": [4]}


# --- 2. Guvenlik kapisi komuttan ONCE ---------------------------------------

@pytest.mark.asyncio
async def test_safety_gate_runs_before_every_actuator_command():
    """Her komut, kendi ENTER onayindan SONRA gitmeli. Sira tersine
    donerse operator hazir olmadan servo hareket eder."""
    events = []

    class _RecordingConsole(mod.OperatorConsole):
        def confirm_ready(self, what):
            events.append(("gate", what))
            return super().confirm_ready(what)

    class _RecordingAction(_SpyAction):
        async def set_actuator(self, index, value):
            events.append(("cmd", index, value))
            await super().set_actuator(index, value)

    console = _RecordingConsole(io.StringIO("\nn\n\nn\n"), io.StringIO())
    session = mod.CalibrationSession(_RecordingAction(), console, dry_run=False)
    await session.run_index_sweep("Servo2", [7, 8], probe_value=0.1)

    kinds = [e[0] for e in events]
    assert kinds == ["gate", "cmd", "gate", "cmd"], (
        f"Guvenlik kapisi her komuttan ONCE calismali, gorulen sira: {kinds}")


@pytest.mark.asyncio
async def test_abort_at_safety_gate_sends_no_command():
    """Operator kapida 's' derse o komut HIC gitmez ve satir ABORTED olur."""
    console, _ = _console(["s"])
    action = _SpyAction()
    session = mod.CalibrationSession(action, console, dry_run=False)

    with pytest.raises(mod.OperatorAbort):
        await session.run_index_sweep("Servo2", [1, 2, 3], probe_value=0.5)

    assert action.calls == [], "Iptal edilen turda donanima komut GITMEMELI"
    assert [r["verdict"] for r in session.rows] == [mod.ABORTED]


# --- 3. Deger taramasinin fiziksel kurallari --------------------------------

@pytest.mark.asyncio
async def test_value_sweep_stops_at_target_and_reports_first_value():
    """Hedefe ulasan ILK deger aday olur; sonrasinda komut GONDERILMEZ."""
    console, _ = _console(["", "n", "", "n", "", "y"])
    action = _SpyAction()
    session = mod.CalibrationSession(action, console, dry_run=False)

    await session.run_value_sweep("FLEX_16_SERVO2_DOWN_VALUE", index=5, direction=1)

    assert action.calls == [(5, 0.0), (5, 0.05), (5, 0.1)]
    assert session.candidates() == {"FLEX_16_SERVO2_DOWN_VALUE": [0.1]}


@pytest.mark.asyncio
async def test_mechanical_limit_stops_sweep_and_is_not_a_candidate():
    """FLEX-16 HOW TO CALIBRATE: 'sinira dayanan degerleri ALMA'.
    Satir ham veriye girer ama ADAY OLMAZ, ve tarama devam ETMEZ."""
    console, _ = _console(["", "n", "", "l", "", "y"])
    action = _SpyAction()
    session = mod.CalibrationSession(action, console, dry_run=False)

    await session.run_value_sweep("FLEX_18_SERVO2_REVERSE_VALUE", index=5, direction=-1)

    assert action.calls == [(5, 0.0), (5, -0.05)], "Sinirdan sonra komut GITMEMELI"
    assert session.rows[-1]["verdict"] == mod.MECHANICAL_LIMIT
    assert session.candidates() == {}, "Mekanik sinir degeri ADAY OLAMAZ"


@pytest.mark.asyncio
async def test_value_sweep_never_exceeds_mavsdk_limit():
    """MAVSDK sozlesmesi: deger [-1..1]. Operator hep 'n' dese bile tarama
    bu sinirin disina komut GONDERMEZ."""
    # ENTER/cevap ciftleri alternatifli: her tur once kapiyi, sonra sorulari yer.
    console, _ = _console([x for _ in range(200) for x in ("", "n")])
    action = _SpyAction()
    session = mod.CalibrationSession(action, console, dry_run=False)

    await session.run_value_sweep("FLEX_17_SERVO3_GRAPPLE_VALUE", index=2, direction=1)

    assert action.calls, "Hic komut gonderilmedi -- tarama hic calismamis"
    assert all(abs(v) <= mod.ACTUATOR_VALUE_ABS_LIMIT for _, v in action.calls)
    assert max(v for _, v in action.calls) == pytest.approx(1.0)


# --- 4. RPC reddi bir "hareketsizlik bulgusu" DEGILDIR ----------------------

@pytest.mark.asyncio
async def test_rejected_rpc_is_not_recorded_as_no_move():
    """Komut kabul edilmediyse servo hic surulmemistir; operatore sormak
    yaniltici bir NO_MOVE satiri uretirdi. Bu tur RPC_REJECTED olur ve
    operatore HIC sorulmaz."""
    # Cevap akisi SADECE iki tur icin yeter (index 1 reddedilecek, sorulmayacak).
    console, _ = _console(["", "", "n"])
    action = _SpyAction(raise_on=1)
    session = mod.CalibrationSession(action, console, dry_run=False)

    await session.run_index_sweep("Servo2", [1, 2], probe_value=0.3)

    verdicts = [r["verdict"] for r in session.rows]
    assert verdicts == [mod.RPC_REJECTED, mod.NO_MOVE]
    assert session.rows[0]["operator_answer"] is None
    assert session.rows[0]["rpc_accepted"] is False


# --- 5. Operator konsolu ----------------------------------------------------

def test_invalid_answer_is_re_asked_not_silently_interpreted():
    """Gecersiz cevap sessizce 'hayir' sayilirsa ham veri kirlenir."""
    console, out = _console(["belki", "evet", "y"])
    assert console.ask("soru?", {"y": "evet", "n": "hayir"}) == "y"
    assert out.getvalue().count("gecersiz cevap") == 2


def test_exhausted_stdin_aborts_instead_of_guessing():
    """stdin biterse cevap YOK demektir -- sessizce bir varsayilan
    uydurulmaz, OperatorAbort atilir."""
    console, _ = _console([])
    with pytest.raises(mod.OperatorAbort):
        console.ask("soru?", {"y": "evet"})


@pytest.mark.asyncio
async def test_abort_mid_sweep_keeps_partial_rows():
    """Operator ortada durdurursa o ana kadarki ham veri KAYBOLMAZ."""
    console, _ = _console(["", "n", "", "s"])
    session = mod.CalibrationSession(_SpyAction(), console, dry_run=False)

    with pytest.raises(mod.OperatorAbort):
        await session.run_index_sweep("Servo2", [1, 2, 3], probe_value=0.3)

    assert [r["verdict"] for r in session.rows] == [mod.NO_MOVE, mod.ABORTED]


# --- 6. Ham veri formati ----------------------------------------------------

def test_csv_written_with_full_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "connect_real_action", lambda *a, **k: pytest.fail("baglanti!"))
    monkeypatch.setattr("sys.stdin", io.StringIO("\nn\n\ny\n"))

    out = tmp_path / "ham.csv"
    assert mod.main(["--dry-run", "--out", str(out),
                     "index", "--servo", "Servo3", "--indices", "4", "5",
                     "--probe-value", "-0.25"]) == 0

    with open(out, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["verdict"] for r in rows] == [mod.NO_MOVE, mod.MOVED]
    assert all(set(r) == set(mod.CSV_COLUMNS) for r in rows)
    assert all(r["dry_run"] == "True" for r in rows)
    assert rows[1]["target_flex"] == "FLEX_15_SERVO3_ACTUATOR_INDEX"
    assert rows[1]["actuator_index"] == "5"
    assert float(rows[1]["commanded_value"]) == pytest.approx(-0.25)


def test_ambiguous_result_is_flagged_not_resolved(capsys):
    """Birden fazla index hareket ettiyse script SECMEZ, belirsizligi
    isaretler -- karar operatorundur."""
    console, out = _console([])
    session = mod.CalibrationSession(mod.DryRunAction(console), console, dry_run=True)
    session._record("index", "FLEX_14_SERVO2_ACTUATOR_INDEX", "Servo2", 5, 0.3,
                    True, "y", mod.MOVED)
    session._record("index", "FLEX_14_SERVO2_ACTUATOR_INDEX", "Servo2", 6, 0.3,
                    True, "y", mod.MOVED)

    mod.print_flex_reminder(console, session)
    text = out.getvalue()
    assert "BIRDEN FAZLA ADAY, BELIRSIZ" in text
    assert "[5, 6]" in text
    assert "SECMEZ" in text


# --- 7. Fiziksel sozlesme dogrulamalari (komut GONDERILMEDEN once) ----------

@pytest.mark.parametrize("argv, expected", [
    (["index", "--servo", "Servo2", "--indices", "0", "1", "--probe-value", "0.3"],
     "index 1'den baslar"),
    (["index", "--servo", "Servo2", "--indices", "1", "--probe-value", "1.5"],
     "MAVSDK sinirinin disinda"),
    (["value", "--flex", "FLEX_16_SERVO2_DOWN_VALUE", "--index", "0", "--direction", "+"],
     "index 1'den baslar"),
    (["value", "--flex", "FLEX_16_SERVO2_DOWN_VALUE", "--index", "5", "--direction", "+",
      "--step", "0"], "--step pozitif olmali"),
])
def test_contract_violations_rejected_before_any_command(argv, expected):
    args = mod.build_parser().parse_args(argv)
    with pytest.raises(SystemExit) as exc:
        mod.validate_args(args)
    assert expected in str(exc.value)


def test_required_arguments_have_no_defaults():
    """--indices ve --probe-value KASITLI olarak zorunludur (bkz. modul
    docstring'i). Bir gun varsayilan eklenirse bu test uyarir."""
    parser = mod.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["index", "--servo", "Servo2"])
    with pytest.raises(SystemExit):
        parser.parse_args(["index", "--servo", "Servo2", "--indices", "1"])
