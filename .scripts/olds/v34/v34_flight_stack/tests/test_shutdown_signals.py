"""ADR-010 R4 korumasi -- core/runtime/shutdown.py.

Bu testlerin varligi denetim bulgusu B4'ten geliyor: koruma yalnizca
main_gz.py'de vardi, yani gercek arac ucururken YOKTU. Burada pinlenen sey
korumanin ta kendisi: arka planda baslatilan bir surecin miras aldigi
SIGINT = SIG_IGN dispozisyonunun EZILDIGI.

Testler surec genelindeki sinyal durumunu degistirdigi icin her biri
onceki dispozisyonu kaydedip finally'de GERI YUKLUYOR -- aksi halde bir test
pytest'in kendi Ctrl-C davranisini kalici olarak bozardi.
"""
import os
import signal
import threading

import pytest

from core.runtime.shutdown import install_signal_handlers


def _saved(*sigs):
    return {s: signal.getsignal(s) for s in sigs}


def _restore(saved):
    for s, handler in saved.items():
        signal.signal(s, handler)


def test_overrides_an_inherited_sig_ign():
    """KOK BULGU: `&` ile NON-INTERACTIVE kabuktan baslatilan surec
    SIGINT = SIG_IGN miras alir; Python o durumda default_int_handler'i
    kurmaz, yani KeyboardInterrupt ASLA dogamaz ve `kill -INT` sessizce
    yutulur. signal.signal() bu dispozisyonu ezmeli."""
    saved = _saved(signal.SIGINT, signal.SIGTERM)
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)      # arka plan mirasini taklit et
        assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN

        install_signal_handlers(lambda: None)

        current = signal.getsignal(signal.SIGINT)
        assert current is not signal.SIG_IGN, "SIG_IGN ezilmedi -- kill -INT hala yutulur"
        assert callable(current)
    finally:
        _restore(saved)


def test_installs_for_both_sigint_and_sigterm():
    """SIGTERM de dahil: scriptli bir kapanma Ctrl-C ile AYNI kontrollu
    donus-ve-inis yolunu almali."""
    saved = _saved(signal.SIGINT, signal.SIGTERM)
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        install_signal_handlers(lambda: None)

        for sig in (signal.SIGINT, signal.SIGTERM):
            assert callable(signal.getsignal(sig)), f"{sig} icin isleyici kurulmadi"
    finally:
        _restore(saved)


def test_signal_actually_triggers_request_stop():
    """Ucu uca: gercek bir SIGINT gonderildiginde callback CAGRILIYOR.

    Isleyici KeyboardInterrupt FIRLATMAZ -- yalnizca loglar ve request_stop()
    cagirir -- bu yuzden kendi surecimize sinyal gondermek guvenli."""
    saved = _saved(signal.SIGINT, signal.SIGTERM)
    calls = []
    try:
        install_signal_handlers(lambda: calls.append("stop"))
        os.kill(os.getpid(), signal.SIGINT)
        # Python sinyali bir sonraki bytecode sinirinda isler.
        for _ in range(1000):
            if calls:
                break
        assert calls == ["stop"], "SIGINT request_stop()'u tetiklemedi"
    finally:
        _restore(saved)


def test_sigterm_also_triggers_request_stop():
    saved = _saved(signal.SIGINT, signal.SIGTERM)
    calls = []
    try:
        install_signal_handlers(lambda: calls.append("stop"))
        os.kill(os.getpid(), signal.SIGTERM)
        for _ in range(1000):
            if calls:
                break
        assert calls == ["stop"]
    finally:
        _restore(saved)


def test_non_main_thread_logs_instead_of_raising():
    """signal.signal() yalnizca ana thread'de calisir. main_gz gorev
    coroutine'ini WORKER thread'de kosuyor (ADR-006), yani bu yol gercekten
    mumkun -- ve orada patlamak yerine loglayip gecmeli."""
    error = {}

    def _worker():
        try:
            install_signal_handlers(lambda: None)
        except Exception as e:  # noqa: BLE001 -- testin olcecegi sey tam da bu
            error["exc"] = e

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join(timeout=5)
    assert "exc" not in error, f"ana thread disinda patladi: {error.get('exc')}"


def test_accepts_a_caller_supplied_logger():
    """Cagiran kendi modul adiyla loglamak isteyebilir (main_gz/main_real
    ikisi de boyle yapiyor)."""
    import logging
    saved = _saved(signal.SIGINT, signal.SIGTERM)
    try:
        install_signal_handlers(lambda: None, log=logging.getLogger("test.custom"))
        assert callable(signal.getsignal(signal.SIGINT))
    finally:
        _restore(saved)
