"""Trapez hiz profili -- CRUISE ve CLIMB/DESCEND bacaklari icin.

NEDEN SetpointLimiter YETMIYOR: setpoint_limiter.py (ADR-010 P4) tick basina
hiz DEGISIMINI sinirlar (SETPOINT_MAX_DELTA_V_M_S), yani bir IVME tavani
uygular. Bu, hizlanma tarafini duzeltir ama YAVASLAMA tarafini bilemez:
kalan mesafeyi gormedigi icin "artik frene basmam gerek" diyemez. Saf P-law
ise tam tersini yapar -- hedefe yaklastikca komutu kucultur ama uzaktayken
tavan hizla gider ve yakinsama kuyrugu uzar.

Trapez profil ikisini birlestirir:

    v = min( v_cruise ,  sqrt(2*a*d_fren) ,  v_onceki + a*dt )
              |              |                    |
              |              |                    +-- hizlanma rampasi
              |              +----------------------- yavaslama rampasi (mesafeden)
              +-------------------------------------- seyir tavani

sqrt(2*a*d) terimi, sabit `a` yavaslamasiyla `d` metrede tam sifira inmenin
kapali cozumudur; her tick'te kalan mesafeden YENIDEN hesaplandigi icin
ruzgar/asim gibi bozanlara karsi kendini duzeltir -- onceden planlanmis bir
yorunge degil, mesafeye kilitli bir hiz tavanidir.

Cikti yine SetpointLimiter'dan gecer (bkz. CenteringController._send_setpoint:
"the ONE place a velocity setpoint leaves this controller"); bu modul o
katmani ATLAMAZ, ondan once gelir.
"""
import math
from dataclasses import dataclass
from enum import Enum


class ProfilePhase(str, Enum):
    ACCEL = "ACCEL"
    CRUISE = "CRUISE"
    DECEL = "DECEL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class ProfileStep:
    speed_m_s: float
    phase: ProfilePhase


def trapezoidal_speed(distance_remaining_m: float,
                      previous_speed_m_s: float,
                      cruise_speed_m_s: float,
                      accel_m_s2: float,
                      dt_s: float,
                      stop_radius_m: float = 0.0) -> ProfileStep:
    """Bir eksen icin bu tick'te komutlanacak hiz BUYUKLUGU (>=0).

    distance_remaining_m : hedefe kalan (yatay mesafe ya da |irtifa hatasi|)
    previous_speed_m_s   : bir onceki tick'te KOMUTLANAN buyukluk (istenen degil)
    stop_radius_m        : bu yaricapta sifira inilmis olmali. CRUISE icin
                           arrival_radius; dikey bacaklar icin 0 verilir cunku
                           orada yakinsama toleransi guard'in kendi isidir.

    Yon bilgisi TASIMAZ -- cagiran taraf isareti/vektoru kendisi uygular.
    Boylece ayni fonksiyon hem yatay (2B vektor) hem dikey (1B isaretli)
    bacakta kullanilabiliyor.
    """
    braking_distance_m = max(distance_remaining_m - stop_radius_m, 0.0)
    if braking_distance_m <= 0.0:
        return ProfileStep(0.0, ProfilePhase.HOLD)

    # Negatif/sifir parametreler bir yapilandirma hatasidir; sessizce garip
    # bir profil uretmektense guvenli tarafa (durma) dusuyoruz.
    if accel_m_s2 <= 0.0 or cruise_speed_m_s <= 0.0 or dt_s <= 0.0:
        return ProfileStep(0.0, ProfilePhase.HOLD)

    v_decel = math.sqrt(2.0 * accel_m_s2 * braking_distance_m)
    v_accel = max(previous_speed_m_s, 0.0) + accel_m_s2 * dt_s

    v = min(cruise_speed_m_s, v_decel, v_accel)
    v = max(v, 0.0)

    if v >= cruise_speed_m_s - 1e-9:
        phase = ProfilePhase.CRUISE
    elif v_decel <= v_accel:
        phase = ProfilePhase.DECEL
    else:
        phase = ProfilePhase.ACCEL
    return ProfileStep(v, phase)


def split_horizontal(speed_m_s: float, north_error_m: float, east_error_m: float):
    """Skaler seyir hizini NED yatay bilesenlerine dagitir.

    Hata vektoru sifira cok yakinsa (hedefin uzerindeyiz) yon tanimsizdir;
    0/0 yerine sifir komut doner."""
    magnitude = math.hypot(north_error_m, east_error_m)
    if magnitude < 1e-6:
        return (0.0, 0.0)
    return (speed_m_s * north_error_m / magnitude,
            speed_m_s * east_error_m / magnitude)


def ned_to_body(north_m_s: float, east_m_s: float, yaw_deg: float):
    """NED yatay hizi GOVDE eksenine cevirir (forward, right).

    IFlightBackend yalnizca set_velocity_body() sunuyor (NED velocity
    setpoint'i YOK, bkz. docs/flight-control-analysis.md 2.1), bu yuzden
    yatay komut her tick'te GUNCEL yaw ile dondurulmek zorunda. yaw, kuzeyden
    saat yonunde derecedir."""
    yaw_rad = math.radians(yaw_deg)
    cos_y, sin_y = math.cos(yaw_rad), math.sin(yaw_rad)
    forward = north_m_s * cos_y + east_m_s * sin_y
    right = -north_m_s * sin_y + east_m_s * cos_y
    return (forward, right)
