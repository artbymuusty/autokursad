"""Surec seviyesinde kontrollu kapanma -- HER entrypoint'in paylastigi.

NEDEN ORTAK BIR MODUL: bu koruma 2026-08-17'ye kadar yalnizca main_gz.py'de
yasiyordu (ADR-010 R4). Denetim (docs/v34-sistem-denetimi.md, B4) main_real.py
ve main_dual.py'de HIC olmadigini gosterdi -- yani emniyet ozelligi tam da
gercek arac ucururken yoktu. Kopyalamak yerine buraya cikarildi: uc composition
root da ayni cagriyi yapar, davranis tanim geregi ayni kalir.

core/ altinda cunku bu bir GOREV mantigi degil, her calisma ortaminda ayni olan
SUREC mantigi -- gz_system/ ya da real_system/ altinda olsaydi yine
kopyalanmasi gerekirdi.
"""
import logging
import signal

logger = logging.getLogger(__name__)


def install_signal_handlers(request_stop, log=None) -> None:
    """ADR-010 R4: Python'un varsayilanina guvenmek yerine KENDI SIGINT/SIGTERM
    isleyicilerimizi kur.

    V3'un 2026-08-17 basarisizliginin kok nedeni (dogrudan kanitlandi):
    NON-INTERACTIVE bir kabuktan `&` ile baslatilan bir surec
    SIGINT = SIG_IGN miras alir -- standart POSIX arka-plan is davranisi.
    Python default_int_handler'i YALNIZCA SIGINT baslangicta zaten
    yoksayilmiyorsa kurar; SIG_IGN miras alinmissa KeyboardInterrupt ASLA
    dogamaz ve `kill -INT` sessizce yutulur. Boyle bir kosuda iptal yolu hic
    calismaz ve arac HAVADA BIRAKILIR -- tam da ADR-008 B2'nin onlemek icin
    var oldugu basarisizlik.

    signal.signal() miras alinan dispozisyonu EZER, yani surecin nasil
    baslatildigindan bagimsiz calisir. SIGTERM de dahil: scriptli bir kapanma
    Ctrl-C ile ayni kontrollu donus-ve-inis yolunu almali.

    request_stop: cagirana ait, gorevi kontrollu durduran callable. GZ'de
        mission task'ini iptal eder (MasterMissionController.run()
        CancelledError'i yakalayip checkpoint'e donup iner); gercek/dual
        tarafta da ayni sozlesme beklenir.
    log: opsiyonel logger -- verilmezse bu modulunki kullanilir. Cagiranin
        kendi modul adiyla loglamasi istendiginde gecilir.
    """
    _log = log or logger

    def _handler(signum, _frame):
        try:
            name = signal.Signals(signum).name
        except ValueError:  # pragma: no cover
            name = str(signum)
        _log.warning("%s alindi -- gorev durduruluyor (donus + inis calisacak).", name)
        request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError) as e:  # pragma: no cover -- ana thread degil / desteklenmiyor
            _log.error("%s icin sinyal isleyici kurulamadi: %s", sig, e)
