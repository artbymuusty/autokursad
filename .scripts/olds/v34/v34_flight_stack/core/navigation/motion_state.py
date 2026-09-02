"""Climb-then-Cruise hareket state'leri.

Bu, core/mission/phase.py'deki MissionPhase'in YERINE GECMEZ. MissionPhase bir
GOREV YASAM DONGUSU makinesidir (CONNECTING, SEARCHING, PAYLOAD_RELEASE, ...);
buradaki MotionState onun ALTINDA, tek bir seyahat bacagi suresince calisan bir
HAREKET makinesidir. Bir Gorev 2 bacagi boyunca MissionPhase sabit kalirken
MotionState bes state'in tamamindan gecer.

NEDEN VAR: goto_global_position_and_wait() hedefe MUTLAK 3B pozisyon setpoint'i
gonderiyor (centering_controller.py, goto_position_ned(target_n, target_e,
-target_alt_m, yaw)) -- yani X, Y ve Z ayni anda hareket ediyor. Uc eksende
birden buyuk hata goren pozisyon kontrolcusu asim ve salinim uretiyor. Bu
makine dikey ile yatayi ZAMANDA ayirir: once irtifayi al, dur ve otur, sonra
yatay uc, sonra alcal.

SIRA (operator karari, 2026-09-02):

    CLIMB -> HOLD -> CRUISE -> DESCEND -> ARRIVAL_HOLD

DESCEND'in CRUISE'dan SONRA gelmesi kasitlidir: hedef irtifa mevcuttan
dusukse once alcalip alcak irtifada seyretmek engel riski tasir. Seyir her
zaman iki ucun YUKSEK olanindan yapilir (cruise_alt = max(mevcut, hedef)),
alcalma hedefin uzerinde yapilir.

CLIMB ve DESCEND kosullu state'lerdir: irtifa farki tolerans altindaysa
atlanirlar (bkz. motion_fsm.py::plan_leg).
"""
from enum import Enum


class MotionState(str, Enum):
    IDLE = "IDLE"
    #: Sadece dikey. vx=vy=0, vz P-law. Cikis: |alt_err|<ALT_TOL VE |vz|<VZ_SETTLE.
    CLIMB = "CLIMB"
    #: Pozisyon kilidi (sifir hiz akisi). Cikis: min sure DOLDU VE attitude durgun.
    HOLD = "HOLD"
    #: Sadece yatay. vz yalnizca irtifa TUTMA icin. Cikis: yatay mesafe<ARRIVAL_RADIUS.
    CRUISE = "CRUISE"
    #: Sadece dikey, asagi. CLIMB ile ayni yasa ve ayni guard.
    DESCEND = "DESCEND"
    #: Varista kisa stabilizasyon; ardindan cagirana (orn. go_to_and_center) devreder.
    ARRIVAL_HOLD = "ARRIVAL_HOLD"
    COMPLETE = "COMPLETE"
    #: Telemetri oldu, guard butcesi doldu ya da Offboard kaybedildi.
    ABORTED = "ABORTED"


TERMINAL_MOTION_STATES = frozenset({MotionState.COMPLETE, MotionState.ABORTED})

#: Hangi state'lerde YATAY eksen komutlanabilir. Bir bacagin dogru
#: ayristirildigini iddia eden testler bunu kullanir (bkz.
#: tests/test_motion_fsm.py): CLIMB/DESCEND sirasinda yatay komut cikmamalidir.
HORIZONTAL_STATES = frozenset({MotionState.CRUISE})

#: Hangi state'lerde DIKEY eksen SEYAHAT amaciyla komutlanabilir. CRUISE'daki
#: vz bunun disindadir -- orada vz bir irtifa TUTMA terimidir, seyahat degil.
VERTICAL_TRAVEL_STATES = frozenset({MotionState.CLIMB, MotionState.DESCEND})
