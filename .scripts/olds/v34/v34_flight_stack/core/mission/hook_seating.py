"""Physical seating validation for the KURSAD40 V4 payload hook.

WHY THIS MODULE EXISTS (acceptance test, 2026-08-26)
----------------------------------------------------
The pickup gate used to be one line in gz_payload_actuator.py:

    if hypot(hook_xy - payload_xy) <= 0.05:  -> publish /hook/attach

with `hook_xy` INFERRED from the vehicle body pose plus a fixed
x = -0.090 offset. Two independent defects, both measured:

  * The hook hangs on a four-segment rope, so it is NOT at a fixed body
    offset. Measured error of the inferred position against the real
    Gazebo pose: mean 0.86 cm, p95 2.76 cm, max 8.23 cm during the pickup
    window and 19.86 cm during transport -- against a 5 cm gate.

  * There was no vertical term at all. Acceptance Case 7 held the hook
    2.42 cm laterally from the receiver but 1.97 m ABOVE it; the old gate
    reported capture, welded the payload to the hook while the payload sat
    on the ground, and hoisted it. Measured post-lock hook<->payload
    distance: 1.68 m.

This module replaces that with a geometric predicate evaluated on the REAL
hook pose, in the RECEIVER's own frame, held for a dwell time.

WHAT IS AND IS NOT SIMULATED
----------------------------
Simulated here: the geometry of hook-vs-receiver, from the exported CAD.
The receiver bore NOW HAS collision geometry: generate_bore_collision.py
decomposes the CAD profile (pocket, both chamfers) into primitive boxes and
writes it into the payload models, so the nose physically enters the bore,
is blocked laterally by the pocket wall, and comes to rest on the lower
chamfer at a computable depth. Nothing was invented; the surfaces were
already in payload_body.stl and were being used for VISUAL only.

STILL not simulated anywhere in this build: magnetic force, servo travel,
cam/follower mechanics. Nor does the chamfer produce gravity-driven
self-centring at the default friction: SDF <mu> defaults to 1.0 and neither
body declares a <surface>, while sliding on the capture chamfer needs
mu < tan(23.20 deg) = 0.4286. What the geometry gives is confinement (a
hard wall at 10.25 mm), a defined rest depth, and no escape once entered.
The lateral force that actually drives the nose inward comes from the
vehicle's correction loop and the pendulum, which is dynamic and measured,
not assumed. The final lock remains a runtime Gazebo fixed joint
(HookAttachSystem); see gz_payload_actuator.activate_pickup_mechanism.

GEOMETRY, MEASURED FROM THE EXPORTED MESHES (not from comments)
---------------------------------------------------------------
Tools/simulation/gz/models/kursad_payload/meshes/payload_body.stl, radius
profile about the part axis (CAD frame, mm; link frame = CAD + 8.0 mm):

    CAD z   r_min   feature                       link z
    +27.00  23.98   deck top face                 +35.00
    +16.50  23.25   counterbore mouth  O46.50     +24.50
    +12.75  14.50   lead-in chamfer end O29.00    +20.75
    + 9.00  11.00   through hole       O22.00     +17.00
      0.00   6.50   magnet seat        O13.00     + 8.00
    - 2.20   6.20   target disc pocket O12.40     + 5.80

Tools/simulation/gz/models/kursad_hook/meshes/core_lower.stl (hook_body_link
frame, mm) -- the insertion nose:

    z -64.65  nose bottom face, r_max 10.43
    z -64.42 .. -51.82   r_max grows 11.25 -> 13.00  (the O26 nose)
    z -47.85 and above   r_max 22.50                 (the O45 shell)

So the nose is O26 over its first 13 mm and the shell above it is O45,
against a O46.50 counterbore 10.5 mm deep. Every threshold below is derived
from those numbers.
"""
import math
from enum import Enum
from typing import NamedTuple, Optional

# --------------------------------------------------------------------------
# GEOMETRY CONSTANTS -- straight off the meshes above. Metres.
# --------------------------------------------------------------------------

# hook_body_link origin -> nose bottom face. core_lower.stl z minimum.
HOOK_NOSE_OFFSET_M: float = -0.06465
# Largest radius of the insertion nose (the part that must enter the bore).
HOOK_NOSE_RADIUS_M: float = 0.01300
# payload link origin -> deck top face. CAD +27.00 mm + 8.00 mm link offset.
RECEIVER_DECK_OFFSET_M: float = 0.03500
# Counterbore mouth radius, CAD z +16.50.
RECEIVER_MOUTH_RADIUS_M: float = 0.02325
# Depth of the counterbore: deck top (+27.00) down to the chamfer end
# (+12.75). This is the axial length over which the bore can hold the nose.
RECEIVER_BORE_DEPTH_M: float = 0.01425
# Nose travel available before the O26 nose wedges in the lower chamfer.
# That chamfer runs (r 14.50, CAD +12.75) -> (r 11.00, CAD +9.00), so a
# nose of radius 13.00 stops where the bore has narrowed to 13.00, i.e.
#     CAD +9.00 + 3.75 * (13.00 - 11.00) / (14.50 - 11.00) = +11.14
# which is 35.00 - 19.14 = 15.86 mm below the deck top.
#   WAS 0.01800, taken as deck top straight down to the through hole
#   (+27.00 to +9.00). That is the travel a ZERO-radius probe would get;
#   the O26 nose bottoms out 2.14 mm earlier. Harmless while the bore had
#   no collision and nothing could enter; wrong now that it can.
RECEIVER_MAX_INSERTION_M: float = 0.01586

# --------------------------------------------------------------------------
# SEATING THRESHOLDS -- each one derived, none chosen to make a run pass.
# --------------------------------------------------------------------------

# LATERAL. For the O26 nose to be FULLY inside the O46.50 bore, its AXIS
# must be within
#     23.25 (mouth) - 13.00 (nose) = 10.25 mm
# of the receiver axis. Beyond that the nose fouls the pocket wall and
# lands on the deck instead.
#   WAS the mouth radius itself, 23.25 mm. That was the honest choice at
#   the time and the reason was written down: the bore had no collision, so
#   gating on 10.25 would have asserted precision the build could not
#   observe. Adding the bore collision removes exactly that objection --
#   the pocket wall is now a real surface that stops the nose at 10.25 mm,
#   so the gate and the physics agree. Note this makes the gate ~2x
#   stricter; whether the net capture rate improves is an empirical
#   question (tighter gate vs. real confinement) and is measured, not
#   predicted.
SEAT_MAX_LATERAL_M: float = (RECEIVER_MOUTH_RADIUS_M
                             - HOOK_NOSE_RADIUS_M)            # 0.01025

# AXIAL. Insertion depth is measured DOWN the receiver axis from the deck
# top face to the hook nose bottom face:
#     depth > 0  nose is below the deck plane (inside the bore)
#     depth = 0  nose exactly on the deck plane
#     depth < 0  nose is above the deck -- not seated
# The bore now has collision, so a seated nose actually descends into it
# and comes to rest on the lower chamfer at 15.86 mm. The lower bound stays
# a small negative tolerance so that a nose resting on the deck plane (the
# pre-bore behaviour, measured +0.85 mm from solver compliance) is not
# rejected on rounding alone, while a hook hovering above the payload still
# is; the upper bound is the CAD travel limit plus the same tolerance.
SEAT_TOLERANCE_M: float = 0.004
SEAT_MIN_INSERTION_M: float = -SEAT_TOLERANCE_M              # -0.004
SEAT_MAX_INSERTION_M: float = RECEIVER_MAX_INSERTION_M + SEAT_TOLERANCE_M   # 0.022

# TILT. The receiver is rotationally symmetric about its axis, so yaw is
# meaningless here; what matters is the angle between the hook axis and the
# receiver axis. The jam limit is set by the chamfer: the O26 nose must pass
# a bore that has narrowed to O29 (r 14.50) 3.75 mm below the mouth, i.e.
#     atan((14.50 - 13.00) / 3.75) = 21.8 deg.
# 15 deg keeps a clear margin inside that. A plumb-hanging hook measures
# 0.005-0.9 deg, so this is never the binding constraint in practice.
SEAT_MAX_TILT_RAD: float = math.radians(15.0)

# ==========================================================================
# MIKNATIS MODELI (GOREV I / B-S4, 2026-09-04)
# ==========================================================================
# DONANIM REVIZYONU: yakalama artik PIM-YUVA degil MIKNATIS.
# Yukaridaki RECEIVER_* / SEAT_*_INSERTION sabitleri O26 burnun O46.5
# yuvaya girmesi icindi; miknatista "giris" diye bir sey yok, TEMAS var.
# O sabitler SILINMEDI -- olcum alanlari (insertion_m) ve onlara bagli
# araclar (seat_trace, O3 erisim korumasi) calismaya devam etsin diye
# duruyorlar; yalnizca KAPI onlara bakmiyor.
#
# Her esik TURETILDI, secilmedi:

#: Miknatis yaricapi (O35 mm, SDF hook_magnet_visual radius 0.0175).
MAGNET_RADIUS_M: float = 0.0175

#: YAKALAMA YARICAPI = miknatis yaricapi.
#  Iki es-capli O35 yuz, merkezleri r kadar ayrikken %39.1 ortusur
#  (lens alani 2r^2*acos(d/2r) - (d/2)*sqrt(4r^2-d^2), d=r).
#  Bunun otesinde ortusen yuzey ucte birin altina duser ve tutma kuvveti
#  hizla kaybolur. Eski pim-yuva kapisi 10.25 mm idi (yuva agzi eksi burun
#  yaricapi); miknatis 1.7 kat daha toleransli.
MAGNET_CAPTURE_RADIUS_M: float = MAGNET_RADIUS_M

#: EKSENEL BOSLUK. Miknatis yuzu hedef diskten en fazla bu kadar uzakta
#  olabilir. Turetme: hiz kapisi 0.05 m/s x 0.1 s ornekleme = 5.0 mm, yani
#  iki ornek arasinda kat edilebilecek yol. CAD'in dinlenme acikligi
#  0.20 mm ve miknatis kalinligi 2.00 mm; 5 mm ikisini de kapsar ve bir
#  ornekleme adimini kaybetmeye dayanikli.
MAGNET_MAX_GAP_M: float = 0.005

#: EGIM. Egik bir miknatis yuzeyi kenariyla temas eder; uzak kenar
#  2r*sin(t) kadar kalkar ve bu bosluk butcesini asmamali:
#      sin(t) <= MAGNET_MAX_GAP_M / (2*MAGNET_RADIUS_M) = 0.1429
#  -> 8.2 derece. Eski pim-yuva kapisi 15 dereceydi (yuvanin acisal
#  toleransi); miknatis DAHA SIKI. Olculen egimler 0.1-4.8 derece, yani
#  yeni sinirin rahatca icinde.
MAGNET_MAX_TILT_RAD: float = math.radians(8.0)

#: DWELL -- miknatis baglaminda YENIDEN TANIMLANDI: "yakalama yaricapi
#  ICINDE kesintisiz gecirilen sure". Pim-yuvada bu "yuvada oturdu"
#  demekti; miknatista "yuzeyler temas halinde kaldi" demek.
#
#  TURETME (GOREV J, 2026-09-04 -- kanca 31 cm ile YENIDEN OLCULDU).
#  Olcum: tools/pendulum_step_flight.py (3 m'de 6 m yanal adim) +
#  tools/measure_hook_pendulum.py (dynamic_pose/info, 4745 ornek).
#    periyot  = 1.078 s  (medyan; adim sonrasi 12 s penceresi, 10 gecis,
#               min 0.942 / maks 1.098 s; dik eksen 1.094 s ile teyit)
#    genlik   = 107 mm tepe
#  Eski 25 cm geometrisinde bu degerler 0.831 s / ~60 mm idi; kanca
#  uzayinca periyot %30 buyudu, dolayisiyla ESKI 0.50 s KOPYALANAMAZ.
#
#  Kural degismedi: dwell, SAF BIR SALINIM GECISINI DISLAMALI. Salinan bir
#  kanca 17.5 mm'lik pencerede yarim periyottan uzun kesintisiz kalamaz
#  (pencere ici sure = (T/pi)*asin(w/A), A -> w iken ust siniri T/2).
#    T/2 = 0.539 s  (olculen en uzun periyot 1.098 s icin 0.549 s)
#  Secim 0.60 s: en uzun yarim periyodun 1.11 kati. Olculen 107 mm'lik
#  salinim pencerede periyot basina yalnizca 0.113 s gecirir, yani secilen
#  esik onun 5.3 kati. Eski deger de ayni kuralla secilmisti (0.50 s =
#  0.415 s'in 1.20 kati); pay orani korundu.
#
#  CAPRAZ KONTROL: salinim tepe hizi A*2pi/T = 0.62 m/s, 0.05 m/s'lik
#  bagil hiz kapisinin 12 kati -- salinan kanca zaten hiz kapisinda eleniyor.
MAGNET_DWELL_S: float = 0.60

# DWELL. Derived from the MEASURED rope dynamics, not chosen: the pendulum
# period is 0.831 s (acceptance test, 6 m lateral step). A hook swinging
# with amplitude A spends only
#     (T / pi) * asin(w / A)
# of each half-cycle inside a window of half-width w. For w = 10.25 mm and a
# 50 mm swing amplitude that is 0.055 s; for a 30 mm amplitude, 0.092 s.
# Requiring 0.30 s therefore cannot be satisfied by a hook merely swinging
# through the envelope -- it has to be resting in it. (The old 23.25 mm
# window gave 0.128 s / 0.235 s; tightening to 10.25 mm only widens that
# margin, so the dwell figure needs no change.)
SEAT_DWELL_S: float = 0.30

# RELATIVE SPEED. Bound so the hook cannot traverse the bore's engagement
# depth within one dwell window -- i.e. a fast pass-through can never look
# seated: 0.01425 m / 0.30 s = 0.0475 m/s. Rounded to 0.05 m/s, which also
# absorbs the differentiation noise of a 48 Hz pose stream. A hook resting
# on the deck measures ~0.
SEAT_MAX_REL_SPEED_MPS: float = 0.05

# POSE FRESHNESS. The Gazebo pose stream runs at ~48 Hz. 0.5 s is ~24 missed
# frames -- long enough not to trip on scheduler jitter, short enough that a
# dead stream cannot be mistaken for a valid geometry sample. A stale pose
# must FAIL the gate, never pass it.
HOOK_POSE_MAX_AGE_S: float = 0.5


#: MANYETIK CEKIM MENZILI (GOREV K / D, operator karari 2026-09-04 "secenek 2").
#  SPEC: "yukun icindeki miknatisa acik delik YUZEYINDEN 5 cm yakinina,
#  kancanin ucundaki miknatis girerse, manyetik cekim simule edilir."
#
#  REFERANS YUZEY: yuvanin AGIZ DUZLEMI, yani compute_seating_geometry'nin
#  `deck` noktasi (payload origin + RECEIVER_DECK_OFFSET_M, yuva ekseni
#  boyunca). Mesafe, miknatis yuzunun o agza olan UC BOYUTLU uzakligi:
#      d = hypot(lateral_m, max(0, -insertion_m))
#  Yani hem yandan hem yukaridan yaklasmayi ayni sayiyla olcuyor.
#
#  BU KAPILARI GEVSETMEZ. Cekim yalnizca "miknatis kancayi ceker" asamasini
#  baslatir; KILITLENME hala MAGNET_CAPTURE_RADIUS_M / MAGNET_MAX_GAP_M /
#  MAGNET_MAX_TILT_RAD / SEAT_MAX_REL_SPEED_MPS kapilarindan ve
#  MAGNET_DWELL_S dwell'inden gecmek zorunda (operator, 2026-09-04).
MAGNET_ATTRACT_RANGE_M: float = 0.05


class SeatState(Enum):
    """Where the hook is in the capture sequence.

    APPROACHING and CAPTURE_CANDIDATE are both "not seated" -- they are kept
    distinct because the difference between 'near the receiver' and 'seated'
    is precisely what the old gate could not express.
    """
    APPROACHING = "APPROACHING"              # geometry does not satisfy seating
    ATTRACTING = "ATTRACTING"                # magnet in range (<= 5 cm), pulling in
    CAPTURE_CANDIDATE = "CAPTURE_CANDIDATE"  # geometry valid, dwell not yet met
    SEATED = "SEATED"                        # valid continuously for SEAT_DWELL_S
    LOCKING = "LOCKING"                      # /hook/attach sent, awaiting /hook/state
    LOCKED = "LOCKED"                        # lock confirmed by the plugin


class SeatingGeometry(NamedTuple):
    """Hook pose expressed in the receiver's own frame."""
    lateral_m: float          # perpendicular distance to the receiver axis
    insertion_m: float        # depth below the deck plane, along the axis
    tilt_rad: float           # hook axis vs receiver axis
    rel_speed_mps: float      # |d(hook - payload)/dt|
    pose_age_s: float
    # Yanal hatanin YONU, NED bilesenleri (GOREV K / D). lateral_m yalnizca
    # BUYUKLUK; cekimi uygulayacak taraf hangi yone cekecegini bilmeli.
    # Isaret kurali: kanca = agiz + (perp_n, perp_e), yani kancayi eksene
    # getirmek icin araci (-perp_n, -perp_e) kadar oteler.
    # Varsayilanlari 0.0 -- eski cagrilar (ve testler) bozulmadan calisir.
    perp_n: float = 0.0
    perp_e: float = 0.0

    def magnet_distance_m(self) -> float:
        """Miknatis yuzunun yuva AGZINA uc boyutlu uzakligi (GOREV K / D)."""
        return math.hypot(self.lateral_m, max(0.0, -self.insertion_m))

    def attraction_active(self) -> bool:
        """Cekim menzilinde mi? (kilitlenme kapilarindan BAGIMSIZ)"""
        return self.magnet_distance_m() <= MAGNET_ATTRACT_RANGE_M

    def failures(self) -> list:
        """Every threshold this geometry violates. Empty == seatable."""
        bad = []
        if self.pose_age_s > HOOK_POSE_MAX_AGE_S:
            bad.append(f"stale_pose({self.pose_age_s:.2f}s>{HOOK_POSE_MAX_AGE_S}s)")
        # MIKNATIS KAPISI (GOREV I / B-S4). Pim-yuvanin uc kapisi
        # (lateral clearance + iki yonlu insertion penceresi) yerine
        # iki kapi: yuzey ortusmesi ve eksenel bosluk.
        if self.lateral_m > MAGNET_CAPTURE_RADIUS_M:
            bad.append(f"lateral({self.lateral_m*1000:.1f}mm>"
                       f"{MAGNET_CAPTURE_RADIUS_M*1000:.1f}mm)")
        # insertion_m > 0 = burun guverte duzleminin ALTINDA. Miknatista
        # "cok derin" diye bir hata yok (guverte kati, burun gecemez);
        # tek anlamli hata yuzeyin UZAK kalmasidir.
        if self.insertion_m < -MAGNET_MAX_GAP_M:
            bad.append(f"gap({-self.insertion_m*1000:.1f}mm>"
                       f"{MAGNET_MAX_GAP_M*1000:.1f}mm)")
        if self.tilt_rad > MAGNET_MAX_TILT_RAD:
            bad.append(f"tilt({math.degrees(self.tilt_rad):.1f}deg>"
                       f"{math.degrees(MAGNET_MAX_TILT_RAD):.1f}deg)")
        if self.rel_speed_mps > SEAT_MAX_REL_SPEED_MPS:
            bad.append(f"rel_speed({self.rel_speed_mps:.3f}>{SEAT_MAX_REL_SPEED_MPS}m/s)")
        return bad

    def is_seatable(self) -> bool:
        return not self.failures()

    def describe(self) -> str:
        return (f"lat={self.lateral_m*1000:6.1f}mm ins={self.insertion_m*1000:+7.1f}mm "
                f"tilt={math.degrees(self.tilt_rad):5.1f}deg "
                f"v={self.rel_speed_mps:5.3f}m/s age={self.pose_age_s:.2f}s")


def _rotate(q, v):
    """Rotate vector v by quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def compute_seating_geometry(hook_pos, hook_quat, payload_pos, payload_quat,
                             rel_speed_mps: float, pose_age_s: float) -> SeatingGeometry:
    """Express the hook's pose in the receiver frame.

    hook_pos/hook_quat  : WORLD pose of hook_body_link (NOT a body-offset estimate)
    payload_pos/..._quat: WORLD pose of the payload link (receiver axis = its +Z)

    The receiver is a bore about the payload's local +Z through its origin,
    opening at the deck top face. 'lateral' is measured perpendicular to that
    axis and 'insertion' along it, because that is the axis the bore actually
    constrains -- a plain XY/Z split would be wrong the moment the payload is
    not level.
    """
    axis = _rotate(payload_quat, (0.0, 0.0, 1.0))
    deck = tuple(payload_pos[i] + axis[i] * RECEIVER_DECK_OFFSET_M for i in range(3))
    nose_off = _rotate(hook_quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))
    nose = tuple(hook_pos[i] + nose_off[i] for i in range(3))

    v = tuple(nose[i] - deck[i] for i in range(3))
    along = sum(v[i] * axis[i] for i in range(3))          # <0 => below the deck
    perp = tuple(v[i] - along * axis[i] for i in range(3))
    lateral = math.sqrt(sum(c * c for c in perp))

    hook_axis = _rotate(hook_quat, (0.0, 0.0, 1.0))
    dot = max(-1.0, min(1.0, sum(hook_axis[i] * axis[i] for i in range(3))))

    # perp DUNYA cercevesinde ve Gazebo dunyasi ENU: x = Dogu, y = Kuzey.
    # Gorev katmani NED konusuyor, bu yuzden burada cevriliyor -- bu proje
    # 2026-08-13'te tam bu eksen karisikligindan bir hata yasadi
    # (generate_competition_area.py basligindaki kanit metnine bakin).
    return SeatingGeometry(lateral_m=lateral,
                           insertion_m=-along,
                           tilt_rad=math.acos(dot),
                           rel_speed_mps=rel_speed_mps,
                           pose_age_s=pose_age_s,
                           perp_n=perp[1],
                           perp_e=perp[0])


class SeatingEvaluator:
    """Tracks the dwell requirement across successive geometry samples.

    Deliberately dependency-free (no clock, no Gazebo): the caller supplies
    `now`, so the whole gate is unit-testable without a simulator.
    """

    def __init__(self, dwell_s: float = MAGNET_DWELL_S):
        self.dwell_s = dwell_s
        self._valid_since: Optional[float] = None
        self.state = SeatState.APPROACHING
        self.last: Optional[SeatingGeometry] = None
        self.last_failures: list = []

    def reset(self) -> None:
        self._valid_since = None
        self.state = SeatState.APPROACHING
        self.last = None
        self.last_failures = []

    def dwell_elapsed(self, now: float) -> float:
        if self._valid_since is None:
            return 0.0
        return now - self._valid_since

    def update(self, geom: Optional[SeatingGeometry], now: float) -> SeatState:
        """Feed one sample; returns the resulting state.

        A missing geometry (no hook pose at all) is treated exactly like a
        failed one: it breaks the dwell. Absence of evidence must never be
        evidence of seating.
        """
        self.last = geom
        if geom is None:
            self.last_failures = ["no_pose"]
            self._valid_since = None
            self.state = SeatState.APPROACHING
            return self.state

        self.last_failures = geom.failures()
        if self.last_failures:
            self._valid_since = None
            self.state = SeatState.APPROACHING
            return self.state

        if self._valid_since is None:
            self._valid_since = now
        if (now - self._valid_since) >= self.dwell_s:
            self.state = SeatState.SEATED
        else:
            self.state = SeatState.CAPTURE_CANDIDATE
        return self.state
