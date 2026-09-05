import asyncio
import math
import time
import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.interfaces.i_camera_source import ICameraSource
from core.interfaces.i_detector import IDetector
from core.interfaces.i_payload_actuator import IPayloadActuator
from core.interfaces.i_payload_visibility_strategy import IPayloadVisibilityStrategy
from core.navigation.centering_controller import CenteringController
from core.position_log.position_store import PositionStore
from core.detection.camera_intrinsics import default_camera_intrinsics
from gz_system.gz_payload_actuator import HOOK_WINCH_EXTEND_M
from core.mission.visual_alignment import VisualHookAligner
from core.mission.hook_seating import (
    HOOK_NOSE_OFFSET_M,
    MAGNET_ATTRACT_RANGE_M,
    MAGNET_CAPTURE_RADIUS_M,
    MAGNET_MAX_GAP_M,
    MAGNET_MAX_TILT_RAD,
    SEAT_MAX_REL_SPEED_MPS,
    _rotate as _quat_rotate,
)
from core.config.parameters import (
    HSV_MIN_AREA_RECT_BASE,
    GOREV3_APPROACH_ALTITUDE_M,
    GOREV3_PICKUP_ATTEMPT_TIMEOUT_S,
    GOREV3_PICKUP_VERIFY_TIMEOUT_S,
    GOREV3_PICKUP_MAX_ATTEMPTS,
    GOREV3_VERIFY_CLIMB_ALTITUDE_M,
    GOREV3_CRUISE_ALTITUDE_M,
    GOREV3_TRANSIT_ALTITUDE_M,
    GOREV3_DESCENT_ALTITUDE_M,
    GOREV3_RETREAT_DISTANCE_M,
    GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M,
    GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS,
    GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES,
    OFFBOARD_SETPOINT_INTERVAL_S,
)

# Kanca govde ofseti: mono_cam x=+0.085, hook_winch_link x=-0.090
# (Tools/simulation/gz/models/x500_mono_cam_down/model.sdf) -- ikisi de
# yuklerin (uzun kenar 0.14 m) iki ucunda 1.5 cm payla. Ortalayan
# kamera ile kanca arasi 0.175 m; eskiden 0.70 m idi ve o korlemesine
# kayma temasin en buyuk hata kaynagiydi.
HOOK_BODY_OFFSET_FORWARD_M = 0.175
# Alma denemeleri boyunca konumu tutmak icin ayrilan sure:
# 3 deneme x (12 s yakalama penceresi + vinc/geri cekme) icin pay.
PICKUP_HOLD_S = 70.0
# Kanca hizalamasinin yapildigi irtifa. Gorus burada hala guvenilir:
# 1.2 m'de yuk 63 x 22 px = 1417 px2 (HSV_MIN_AREA_RECT_BASE=400'un
# 3.5 kati) ve kadraj 2.84 x 2.13 m, yani 0.175 m'lik kanca ofseti
# hedefi kenara itmiyor (0.30 m'de ayni ofset 315 px ile kadrajin
# kenarina dayaniyordu -- PHASE 13 D3'un olcup reddettigi rejim).
HOOK_ALIGN_ALTITUDE_M = 1.2
# Yuk kamerada kaybolursa kac metre yukselip yeniden aranacak
# ve kac kez denenecek (operator, 2026-08-23).
HOOK_REACQUIRE_CLIMB_M = 1.0
# 3 -> 1 (GOREV K / B1, operator karari 2026-09-05). BUTCE KARARI, ve
# gerekcesi olculmus: O-B/C1'de ON HAZIRLIK 53.5-58.6 s surdu ve 60 s'lik
# deneme butcesinden yakalama penceresine yalnizca 1.4-6.5 s kaldi. Adaptif
# alcalma (madde 6) buraya ~+6 s daha ekliyor; yer acilmazsa her deneme
# 60 s'de kesilir ve KAPILAR HIC DENENMEZ.
#
# NEDEN ILK TIRMANIS KORUNUYOR: H1 dogrulamasi (docs/gorevG-H1-dogrulama.md)
# yeniden bulmanin CALISTIGINI olctu; kaldirmak calisan bir kurtarmayi
# atmak olurdu. Kirpilan sey TEKRARI: ayni denemede ikinci ve ucuncu
# tirmanis, ilkinin bulamadigi yuku ayni yontemle yeniden ariyor.
#
# BU DEGER OLCUMLE DOGRULANACAK: canli kosumda kac denemenin reacquire'a
# dustugu ve ilk tirmanisin yetip yetmedigi loglaniyor. Yetmiyorsa geri
# alinacak yer burasi, adaptif alcalma degil.
HOOK_REACQUIRE_MAX_CLIMBS = 1
# TESPIT TAVANI (Gorev G / H1, 2026-09-04).
#
# Yukaridaki tirmanis KOSULSUZ YUKARI gidiyordu ve tetiklendiginde kendi
# amacini imkansiz kiliyordu. Olculdu (docs/gorevG-H1-dogrulama.md):
# yuk 0.14 x 0.05 m, dedektorun alan kapisi HSV_MIN_AREA_RECT_BASE = 400 px2
# ve gorunen alan irtifanin KARESIYLE kuculuyor --
#     alan_px = (L*f/alt) * (S*f/alt) = L*S*f^2 / alt^2
# f = 539.9 px'te:
#     1.50 m -> 907 px2 (2.3x)      2.26 m ->  400 px2 (TAM SINIR)
#     1.90 m -> 566 px2 (1.4x)      2.90 m ->  242 px2 (GECEMEZ)
#     3.90 m -> 134 px2 (GECEMEZ)
# Yani ikinci tirmanistan sonra yuk MATEMATIKSEL OLARAK bulunamaz; altigen
# ayni tirmanista hayatta kalir ve "altigen var / yuk yok" imzasi cikar.
#
# TAVAN yukaridaki esitlikten TURETILIYOR, elle secilmiyor:
#     tavan = f * sqrt(L*S / min_area_px) / PAY
# PAY 1.30: tam sinirda durmak, dedektorun kapiyi ancak teget gecmesi
# demek. 1.30 ile tavan ~1.74 m'ye iner ve orada yuk hala kapinin 1.7
# katinda kalir -- olculen calisan bantla (0.9-1.5 m) tutarli.
#
# TIRMANISIN MESRU AMACI KORUNUYOR: hedef kadrajin DISINA ciktiginda
# yukselmek kadraji genisletir ve gercekten yardim eder. Kusur, o faydanin
# bittigi noktadan sonra da yukselmeye devam etmekti. Tavana kadar
# yukseliyor, tavanda pay kalmayinca ASAGI -- yani yukun buyudugu tek yone
# -- doniyor ve HOOK_VISUAL_ALIGN_ALTITUDE_M'in altina inmiyor (bu dosyanin
# kendi notlari 0.30 m'nin tuzak oldugunu zaten kaydediyor).
PAYLOAD_RECT_LONG_EDGE_M = 0.140   # default.sdf:357 bore_base <box><size>
PAYLOAD_RECT_SHORT_EDGE_M = 0.050  # ayni satir
HOOK_REACQUIRE_CEILING_MARGIN = 1.30
# Kancanin yukun ORTASINA denk geldigini goruntuden dogrulama
# esigi. Magnet zaten en fazla 5 cm'den yakaliyor; goruntu
# kontrolu ayni buyuklukte olmali ki tutarsiz olmasin.
HOOK_VISION_ALIGN_TOLERANCE_M = 0.05
# KANCA POZUNA GORE KAPALI CEVRIM HIZALAMA (2026-08-26).
# Kanca artik menteseli bir ipin ucunda ve gercek pozu Gazebo'dan
# okunabiliyor (actuator.hook_to_receiver_offset_world). Bu yuzden alma
# irtifasinda son bir duzeltme yapiliyor: olculen kanca-yuva sapmasi kadar
# arac otelenir, ip sonene kadar beklenir, tekrar olculur.
#
# NEDEN GEREKLI: govde ofsetiyle acik cevrim konumlanmanin olculen yanal
# hatasi 24-56 mm (kabul testi, 2026-08-26). Yeni oturma kapisinin yanal
# siniri yuvanin agiz yaricapi olan 23.25 mm; yani acik cevrim TEK BASINA
# CAD'in gerektirdigi hassasiyeti tutturamiyor. Duzeltme, olcumu yapan
# poz kaynaginin ta kendisiyle kapatiliyor.
# Vinci hizalamadan ONCE salmak icin beklenen sure. Vinc 0.40 m komutu
# aliyor ve SDF'deki eklem hiz siniri 0.5 m/s, yani hareketin kendisi ~0.8 s;
# geri kalani kancanin guverteye oturup ipteki salinimin (olculen periyot
# GOREV J / 31 cm kanca: 1.078 s; 25 cm'de 0.831 s idi) sonmesi icin.
# 4 s artik ~3.7 periyot (eskiden ~4.8). Sabit DEGISTIRILMEDI -- kanca
# uzamasinin sonumleme butcesine etkisi J'de olculur.
HOOK_PAYOUT_SETTLE_S = 4.0
# GORSEL HIZALAMA IRTIFASI. Hizalama alma irtifasinda (0.30 m) YAPILAMAZ, ve
# bu bir ayar meselesi degil, kadraj geometrisi:
#
# Faz, KANCAYI yuvanin uzerine getirmek icin araci HOOK_BODY_OFFSET_FORWARD_M
# (0.175 m) ileri kaydirir. O anda KAMERA yuvadan 0.175 + 0.085 = 0.260 m
# ileridedir (0.085 = kameranin govde kol mesafesi). Yuva bu durumda kadrajda
#     v = 0.260 * 539.94 / derinlik   piksel asagida gorunur,
# ve yari-kadraj yalnizca 480 px:
#     arac 0.30 m -> derinlik 0.280 -> 501 px  KADRAJ DISI
#     arac 0.45 m -> derinlik 0.430 -> 327 px  (yari-kadrajin %68'i)
#     arac 0.70 m -> derinlik 0.680 -> 206 px  (%43)
# Olculdu: 0.30 m'de gorev 30 yinelemede yalnizca 7 tespit yapabildi ve
# "receiver_lost" ile guvenli sekilde durdu -- dogru davranis, yanlis irtifa.
#
# 0.90 m: derinlik 0.88, yuva merkezden 160 px asagida, yukun uzak kenari
# 204 px'te -- yari-kadrajin (480 px) %42'si, yani servo hedefe yaklasirken
# yuvayi kadraj disina itme riski yok. 0.55 m denendi ve yetmedi: yakalama
# 20 tespitten sonra "receiver_lost" ile dustu, cunku hizalama ilerledikce
# yuva alt kenara dogru kayiyor.
#
# Yuksekte hizalamak artik BEDAVA, cunku vinc hizalama ve inis boyunca TOPLU
# (asagi bak) ve son duzeltme zaten alma irtifasinda yapiliyor. Dedektorun
# 66 kareli olcumunde bu bant (0.90-1.40 m) 0.076 cm merkez hatasi veriyor.
HOOK_VISUAL_ALIGN_ALTITUDE_M = 0.90
# 6 -> 3 (GOREV K / B1, operator karari 2026-09-05). Ayni butce karari.
# O-B/C1 olcumu: _settle_hook_onto 10.9-15.7 s surdu, yani tek basina
# denemenin dortte biri. Kazanc 0.5 ile her adim kalan hatanin yarisini
# kapatiyor, dolayisiyla 3 adim artik hatanin 1/8'ini birakir: gorsel
# hizalamanin kabul esigi HOOK_VISUAL_ALIGN_MAX_USABLE_M = 0.12 m
# oldugundan en kotu giristen sonra 15 mm kalir. 6 adim 1.9 mm'ye inerdi
# ama zaten HOOK_ALIGN_TARGET_LATERAL_M = 10 mm'de erken cikiliyor.
# OLCULEN yakinsama (2026-08-31, uc kosum) 18.6 / 27.3 / 13.3 mm idi --
# yani pratikte butce zaten hedefe varmadan doluyordu; 3 adim o rejimde
# sureyi yariya indirir ve son sozu oturma kapisi soyler.
HOOK_ALIGN_MAX_CORRECTIONS = 3
# Duzeltmeyi birakma esigi: oturma kapisinin yanal sinirinin yarisi. Yarisi,
# cunku kapinin tam sinirinda durmak PX4'un birkac mm'lik surukklenmesiyle
# hemen disari cikar.
HOOK_ALIGN_TARGET_LATERAL_M = 0.010
# Havadaki gorsel hizalamanin hedefi. Hassas is asagida yapiliyor
# (_settle_hook_onto), orada vinc acik ve her duzeltme DINLENEN kancayi
# guverte uzerinde SURUKLUYOR -- havada ayni hassasiyeti istemek yalnizca
# sarkacla bogusmak demek: olculdu, 23 saglam tespitle bile 31 mm'de zaman
# asimina ugradi. 30 mm, oturma kapisinin 23.25 mm'lik sinirinin hemen
# ustunde ve asagidaki duzeltmenin rahatca kapatabilecegi bir artik.
HOOK_VISUAL_ALIGN_TOLERANCE_M = 0.030
# Havada yakinsamamis olsa bile, bu buyuklugun altindaki bir artik hata
# asagidaki _settle_hook_onto tarafindan kapatilabilir. Uzerindeyse olcum
# guvenilmez demektir ve faz guvenli sekilde durur.
HOOK_VISUAL_ALIGN_MAX_USABLE_M = 0.12
# ALMA IRTIFASINDAKI SON DUZELTMENIN KAZANCI VE SONUMLEMESI.
#
# Vinc salinirken kanca serbest dusup salliniyor: olculdu, payout ONCESI
# yanal 14.3 mm / egim 0.2 derece iken, payout SONRASI 64.6 mm / 33.3 derece.
# Kanca artik guverte ustunde DINLENIYOR, yani her duzeltme onu surukluyor --
# ama surtunme ve sarkac nedeniyle hemen takip etmiyor.
#
# Tam hatayi tek adimda uygulamak (dead-beat) bu yuzden asiyor: olculdu,
# 93 -> 131 -> 68 -> 68 -> 48 -> 78 mm, yakinsamiyor. Kazanc 0.5 ile her adim
# kalan hatanin yarisini kapatir, ve her adimdan sonra kancanin gercekten
# durmasi beklenir (olculen sarkac periyodu GOREV J / 31 cm: 1.078 s;
# 2.5 s artik ~2.3 periyot -- 25 cm'de 0.831 s ile ~3 periyottu).
HOOK_SETTLE_GAIN = 0.5
HOOK_SETTLE_WAIT_S = 2.5
# Kanca hala hareket ediyorken olcmek, hareketin kendisini hata sanmak demek.
HOOK_SETTLE_MAX_SPEED_MPS = 0.03
# Her duzeltmeden sonra ipin sonmesi icin beklenen sure. Olculen sarkac
# periyodu GOREV J / 31 cm: 1.078 s (25 cm'de 0.831 s); 1.7 s artik ~1.6
# periyot, eskiden ~2 periyottu. Sabit DEGISTIRILMEDI.
HOOK_ALIGN_SETTLE_S = 1.7

# ==========================================================================
# ADAPTIF ALCALMA (GOREV K, operator karari 2026-09-05)
# ==========================================================================
# NEDEN SABIT BIR IRTIFA CALISAMAZ -- OLCULDU, turetme:
# docs/gorevK-adaptif-alcalma-faz1.md.
#
#   Tools/simulation/gz/models/x500_mono_cam_down/model.sdf:200-206
#       burun, vinc CEKILIYKEN base_link'in 0.19765 m altinda
#       base_link, arac yerdeyken 0.240 m yukarida
#   Zincir GERGIN iken:      nose_z = A + 0.04235 - P
#   CAPRAZ DOGRULAMA: SDF'nin kendi hesabi (model.sdf:753-756) "0.30 m iniş
#   irtifasindan guverteye ulasmak 0.272 m salim ister" diyor; formul
#   0.30 + 0.04235 - 0.070 = 0.272. BIREBIR.
#
#   Gorevin salimi P = hook_payout_m(0.30) = 0.330 ve inis boyunca SABIT
#   (extend_winch_for 0.90 m'de bir kez cagrilir, O1 kurali geregi bir daha
#   buyumez), yani:
#       burun GUVERTEYE deger (insertion=0)  ->  A = 0.358 m
#       burun ZEMINE   deger (nose_z=0)      ->  A = 0.288 m
#       KULLANILABILIR PENCERE               ->  70 mm
#   Pencerenin GENISLIGI = guverte yuksekligi; salim/pay/CHAIN_OFFSET onu
#   KAYDIRIR, GENISLETMEZ. O5'te olculen irtifa hatasi 90-290 mm, yani
#   pencerenin 1.3-4.1 KATI. Hangi sabit secilirse secilsin kosumlarin bir
#   kismi pencerenin USTUNDE, bir kismi ALTINDA biter -- ve ikisi de
#   olculdu: C1 eksenel +61..+152 mm (ustunde), P3 ins=+46 mm /
#   nose_z=-0.0987 (altinda). Ayni kod, ayni sabit, iki zit ariza.
#
# COZUM: irtifayi KOMUT ETME, EKSENEL BOSLUGU KAPAT. Karar olcusu
# seating_geometry().insertion_m, yani yuvanin KENDI cercevesinde olculen
# derinlik -- EKF irtifa hatasi denklemden tamamen cikiyor.

#: Oransal adim kazanci (operator karari 2026-09-05).
#  NEDEN 1'IN ALTINDA: asim = fazladan inis = ipte gevseklik = zincirin
#  bukulmesi = kanca yan yatar = TILT KAPISI OLUR. Bu tam olarak P3'un
#  ariza modu (span 0.235 -> 0.094, fold 68 deg, tilt 493/493 red).
#  Olculen en buyuk baslangic boslugundan (420 mm) 0.7 ile:
#      420 -> 126 -> 38 -> 11 -> 3.4 mm, yani 4 adimda 5 mm'lik kapinin
#  icine giriyor. Kazanc 1.0 bunu 2-3 adima indirirdi ama olcum gurultusunu
#  dogrudan asima cevirirdi.
ADAPTIVE_DESCENT_GAIN = 0.7
#: Alcalma hizi. YENI BIR HIZ DEGIL: mevcut tek atis inis 0.90 -> 0.30 m'yi
#  (0.60 m) 6.0 s'de komut ediyordu = 0.10 m/s. Adim suresi buradan cikar.
ADAPTIVE_DESCENT_RATE_MPS = 0.10
#: Bundan kucuk bir adim komut edilmez -- kapinin KENDI toleransindan
#  (MAGNET_MAX_GAP_M = 5 mm) kucuk bir hareket hukmu degistiremez.
ADAPTIVE_DESCENT_MIN_STEP_M = MAGNET_MAX_GAP_M
#: Tek adim tavani. FIZIKSEL sinir zemin kirpmasidir; bu yalnizca bozuk bir
#  geometri okumasina karsi akil sagligi kapisi ve mevcut tek atis inisin
#  (0.60 m) yarisi.
ADAPTIVE_DESCENT_MAX_STEP_M = 0.30
#: Adim tavani. Kazanc 0.7 ile olculen en kotu boslugu 4 adimda kapatiyor.
#  6 -> 8: canli kosumda en kotu baslangic boslugu 800 mm cikti ve tam 6
#  adim gerekti (2026-09-05 r1); miknatis bandi beklemesi de bir yineleme
#  harcadigi icin 6 tavani yetmiyordu. Asil sinir zaman butcesi.
ADAPTIVE_DESCENT_MAX_STEPS = 8
#: SERT ZAMAN BUTCESI. Olculen adim maliyeti (4 adim): hold
#  2.94+0.9+1.0+1.0 = 5.8 s + sonumleme 4 x 1.2 = 4.8 s ~= 10.6 s.
#  14 s bunu pay ile kapsar. Bu +6 s'lik artis icin yer B1 ile acildi
#  (reacquire 3->1, son duzeltme 6->3).
ADAPTIVE_DESCENT_BUDGET_S = 20.0   # 14.0 + 3.0 s bant + 2.0 s dogrultma + pay
#: Her adimdan sonra kancanin sonumlenmesi icin TAVAN (erken cikilir).
#  Olculen sarkac periyodu GOREV J / 31 cm: 1.078 s; 1.2 s ~= 1.1 periyot.
#  _settle_hook_onto'nun 2.5 s'inden kisa, cunku oradaki uyarim YATAY
#  oteleme; burada hareket SAF DIKEY ve bu dosyanin kendi olcumu dikey
#  inisin sarkaci cok daha az uyardigini kaydediyor.
ADAPTIVE_DESCENT_SETTLE_S = 1.2
#: Cok kucuk adimlarda bile setpoint akisinin oturmasi icin en az sure.
ADAPTIVE_DESCENT_MIN_HOLD_S = 1.0
#: GUVENLIK ALT SINIRI -- kanca burnunun dunya z'si. SECILMIS BIR SAYI
#  DEGIL: zeminin kendisi. Yanal hata buyukse burun guverteden yana duser,
#  eksenel bosluk hic kapanmaz ve tek koruma budur. Adim, burun bu sinirin
#  ALTINA inecek sekilde HIC komut edilmez -- yani asim payi gerekmez.
ADAPTIVE_DESCENT_NOSE_FLOOR_M = 0.0

#: MIKNATIS BANDI (operator karari 2026-09-05): "yukun ortasindaki delige
#  3-5 cm yukari alaninda" cekim calismali. Inis bu banda gelince DURUR ve
#  miknatisin yanal hatayi kapatmasi BEKLENIR; sonra inise devam edilir.
#
#  NEDEN BURADA DURMAK ISE YARIYOR: bu irtifada kanca SERBEST ASILI.
#  Guverteye dayanmis bir kancayi yana kaydirmak ~0.196 N statik surtunme
#  yenmek demek; serbest asili kancayi 35 mm yana getiren sarkac kuvveti ise
#  yalnizca m*g*x/L = 0.196 * 0.035 / 0.53 = 0.013 N. Yani miknatis serbest
#  rejimde 15 kat daha kolay is yapiyor. Guvertede iken yapamadigi olculdu
#  (7 adimda 33.8 -> 33.4 mm).
#
#  DIKKAT -- MIKNATIS EKSENEL BOSLUGU KAPATAMAZ: kanca gergin bir kordonun
#  ucunda; asagi cekmek yalnizca kordonu gerer. Bandin isi YANAL hatayi
#  kapatmak; eksenel bosluk yine ARACIN inisiyle kapanir. Isbolumu budur.
ADAPTIVE_DESCENT_MAGNET_GAP_M = 0.04      # 3-5 cm bandinin ortasi
#: Bantta ne kadar beklenecek. TURETME: menzil kenarinda kuvvet 0.044 N,
#  sonumleme 2.0 N*s/m, yani sinir yaklasma hizi v = F/c = 0.022 m/s.
#  Olculen en kotu yanal artik (_settle_hook_onto sonrasi 53 mm) bu hizla
#  2.4 s'de kapanir. 3.0 s bunu pay ile kapsar ve 14 s'lik inis butcesine
#  sigar.
ADAPTIVE_DESCENT_MAGNET_HOLD_S = 3.0
#: Bant kac kez kullanilabilir. 2026-09-05 kosumu: bant yanali 29.2 -> 15.0 mm
#  kapatti (kapinin ICINE), ama sonraki inis adimi onu 36.3 mm'ye geri acti.
#  Tek atislik bir bant, kazanci inise geri veriyor. Ikinci sefer, kazanci
#  temasa EN YAKIN noktada tazeler. Ust sinir 2, cunku her bant 3 s ve
#  inis butcesi 17 s.
ADAPTIVE_DESCENT_MAGNET_HOLDS_MAX = 2

#: SON BOSLUK HEDEFI -- burun guverteye DAYANMASIN.
#  2026-09-05 kosumunda inis boslugu 0.0 mm'ye kadar kapatti, yani burun
#  guverteye oturdu; egim o ana kadar 0.9 derece iken pencerede
#  34.7 -> 42.0 -> 39.4 dereceye firladi. Mekanizma: burun guvertede SIKISIK
#  iken miknatisin yanal kuvveti kancayi kaydirmiyor, TEMAS NOKTASI ETRAFINDA
#  DEVIRIYOR (kutle merkezine uygulanan kuvvet bile sabitlenmis bir uc
#  etrafinda tork uretir). Serbest asili kanca ise 0.005-0.9 derece olcuyor
#  (hook_seating.py).
#  Cozum: temasin hemen USTUNDE dur. Kapi zaten -5 mm'ye kadar kabul ediyor;
#  2.5 mm o pencerenin ortasi, yani hem kapi saglanir hem burun serbest kalir
#  ve miknatis yanali kapatmaya devam edebilir.
ADAPTIVE_DESCENT_TARGET_GAP_M = MAGNET_MAX_GAP_M / 2.0

#: DEVRILME DOGRULTMA (GOREV M, operator karari 2026-09-05).
#  Devrilme gorulunce deneme HEMEN atilmiyor: once hizalama torkuyla
#  dogrultulmasi deneniyor. Torkun asil isi tam olarak budur; denemeyi
#  sinamadan atmak, yeni mekanizmayi hic denemeden cope atmak olurdu.
#  Basarisiz olursa eski davranisa (denemeyi bastan baslat) dusulur.
#
#  2.0 s: kancanin tork altindaki yerlesme suresi. Kritik sonumlemede
#  yerlesme ~4/omega_n; k = 0.03 N*m ve I = 9.6e-6 kg*m^2 icin
#  omega_n = sqrt(k/I) = 55.9 rad/s, yani ~0.07 s. Iki saniye bunun 28 kati
#  -- yani sinir tork degil, kancanin TEMASTAN kurtulup donebilmesi.
ADAPTIVE_DESCENT_RIGHTING_S = 2.0
#: Inis basina TEK dogrultma denemesi (operator tarifi). Basarisizsa dis
#  dongu zaten vinci toplayip gorsel isi ve _settle_hook_onto'yu bastan
#  kosuyor -- kancayi yeniden dikey astiran mekanizma odur.
ADAPTIVE_DESCENT_RIGHTING_MAX = 1

#: _settle_hook_onto ANA YOLDA KOSSUN MU (operator karari 2026-09-05).
#  False: adim atlanir, yanal hatayi miknatis kapatir. Gerekcesi ve olculen
#  sayilari cagri yerindeki notta. True yapmak eski davranisi aynen geri
#  getirir -- fonksiyon SILINMEDI, _on_retry hala kullaniyor.
GOREV3_SETTLE_HOOK_ONTO_ENABLED = False
# Alma dogrulamasi: yuk en az bu kadar yukselmis olmali.
# Tirmanis adimlari 1/2/3 m oldugu icin bu esik cok gevsek
# secildi -- amac 'gercekten kalkti mi', 'ne kadar' degil.
PICKUP_LIFT_CONFIRM_M = 0.30
# GOREV I / A (2026-09-04): HEDEF ARTIK SABIT DEGIL.
#
# Buradaki iki sabit "Gorev 3 kirmizi payload'i alir (mavi altigene
# birakilan)" varsayimini tasiyordu. O varsayim YANLIS: ilk yuk, hangi
# sekil ONCE birakildiysa odur ve ucgen de olabilir (V33 spec madde 11;
# interlock 2026-09-01'den beri sirayi zaten tutuyor).
#
# Fazin hedefi artik run(target_shape=...) ile disaridan geliyor ve rengi
# SHAPE_TO_COLOR'dan turetiliyor. Asagidaki sabitler yalnizca GERI DUSUS:
# cagiran bir sekil vermezse eski davranis korunur, boylece mevcut
# testler ve alternatif giris noktalari kirilmaz.
SEARCH_CENTER_RED = "red"
SHAPE_TO_COLOR_RED = SEARCH_CENTER_RED
DEFAULT_PICKUP_SHAPE = "MAVI_ALTIGEN"

def _WARN():
    """Severity.WARN'i tembel al -- modul yuklenirken telemetri paketini
    zorunlu kilmamak icin (bu dosyanin _publish'i de ayni deseni kullaniyor)."""
    from core.telemetry.events import Severity
    return Severity.WARN


logger = logging.getLogger(__name__)

class Gorev3PickupPhase:
    """Görev 3 Rapor Bölüm 5 (operatör revizyonu, 2026-08-13): Mavi Altıgen
    konumuna (1. yükün bırakıldığı yer) dönülür, orada artık görünen Kırmızı
    Dikdörtgen'e (fiziksel 1. yük) uzun kenarına dik olacak şekilde
    hizalanılır, 30cm geriden görüntüyle doğrulanır, 60cm ileri gidilerek
    alma pozisyonuna geçilir, THIRD MISSION SERVO ile alınır, ve
    GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M irtifalarına yükselerek Kırmızı
    Dikdörtgen'in artık görünmediği doğrulanır."""

    def __init__(self, flight: IFlightBackend, camera: ICameraSource, detector: IDetector,
                 actuator: IPayloadActuator, position_store: PositionStore,
                 visibility_strategy: IPayloadVisibilityStrategy, centering: CenteringController,
                 publisher=None):
        # publisher OPSIYONEL ve varsayilani None: bu faz simdiye kadar event
        # bus'a HIC yayin yapmiyordu ve tum alma detayi yalnizca mission.log'a
        # gidiyordu. Sonucu 2026-08-31'de olculdu: olay akisinda faz basi ile
        # faz sonu arasinda 77-89 s "sessizlik" gorunuyordu ve bu YANLISLIKLA
        # "kod takilmis" diye okundu -- oysa kod her adimi calistiriyordu.
        # Yayin yalnizca GORUNURLUK ekler, davranisi degistirmez; None
        # verildiginde (testler) hicbir sey yayinlanmaz.
        self.publisher = publisher
        self.flight = flight
        self.camera = camera
        self.detector = detector
        self.actuator = actuator
        self.position_store = position_store
        self.visibility_strategy = visibility_strategy
        self.centering = centering
        # GOREV I / A: run() bunlari hedefe gore ayarlar. Yardimci metotlar
        # (_settle_hook_onto, _align_hook_on_receiver) run()'dan cagriliyor
        # ama testler onlari dogrudan da cagirabiliyor -- varsayilan burada.
        self._shape = DEFAULT_PICKUP_SHAPE
        self._color = SHAPE_TO_COLOR_RED
        self._rect_class = "KIRMIZI_DIKDORTGEN"

    def _publish(self, code: str, message: str = "", data: dict = None,
                 severity=None):
        """Olay yayinla; publisher yoksa sessizce gec (davranis degismez)."""
        if self.publisher is None:
            return
        try:
            from core.telemetry.events import Event, Severity, Category
            self.publisher.publish(Event(
                code=code, subsystem="Gorev3PickupPhase",
                category=Category.LIFECYCLE,
                severity=severity or Severity.INFO,
                message=message, data=data or {}))
        except Exception:  # noqa: BLE001 -- gorunurluk gorevi dusuremez
            logger.debug("[GOREV3] olay yayinlanamadi: %s", code, exc_info=True)

    async def _locate_target_with_retries(self):
        """Kırmızı Dikdörtgen bulunana kadar (veya deneme sınırına kadar)
        her karede yeniden dener -- go_to_and_center()'ın 'hedef kayboldu'
        döngüsüyle aynı mantık."""
        for _ in range(GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS):
            try:
                return await self.visibility_strategy.locate_target(self.detector, None)
            except RuntimeError:
                await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)
        return None


    async def _rect_pixel_offset(self):
        """KIRMIZI_DIKDORTGEN'in kanca hedef noktasina gore PIKSEL sapmasi.

        Kamera govde +0.085'te, kanca -0.090'da. Kamera bir noktayi kare
        MERKEZINDE gorurken o nokta govde (+0.085, 0)'dadir; kanca ise
        HOOK_BODY_OFFSET_FORWARD_M kadar geridedir. Dolayisiyla kanca yukun
        TAM ORTASINDAYKEN yuk, kare merkezinin GERISINDE su kadar piksel
        gorunur:
            offset_px = HOOK_BODY_OFFSET_FORWARD_M * f / irtifa
        Asagi bakan kamerada govde-ileri, goruntu -y yonudur (bkz.
        centering_controller'daki isaret notu), yani beklenen nokta
        merkezin ALTINDA +offset_px'tedir.

        Doner: (sapma_m, gorunur_mu). Gorunmuyorsa (None, False)."""
        try:
            detections = await self.detector.detect(None)
        except Exception:  # noqa: BLE001
            return (None, False)
        rect = next((d for d in detections
                     if d.shape_type == self._rect_class), None)
        if rect is None:
            return (None, False)
        try:
            _lat, _lon, alt = await self.flight.get_global_position()
        except Exception:  # noqa: BLE001
            return (None, True)
        intr = default_camera_intrinsics()
        res_w, res_h = self.camera.get_resolution()
        if intr is None or not alt or alt <= 0:
            return (None, True)
        focal = intr.scaled_to(res_w, res_h).focal_px
        if not focal:
            return (None, True)
        want_x = res_w / 2.0
        want_y = res_h / 2.0 + HOOK_BODY_OFFSET_FORWARD_M * focal / alt
        dx_px = rect.center_px[0] - want_x
        dy_px = rect.center_px[1] - want_y
        return (math.hypot(dx_px, dy_px) * alt / focal, True)

    def _detection_ceiling_m(self):
        """Yukun dedektorun alan kapisini hala gecebildigi EN YUKSEK irtifa.

        Elle secilmis bir sayi DEGIL: kamera ic parametrelerinden ve
        HSV_MIN_AREA_RECT_BASE'ten turetiliyor (bkz. dosya basindaki
        TESPIT TAVANI notu). Kaynaklardan biri okunamazsa None doner ve
        cagiran taraf eski davranisa duser -- tavan bilinmiyorsa onu
        uydurmak, olculmemis bir sinir koymak olurdu.
        """
        intr = default_camera_intrinsics()
        if intr is None:
            return None
        try:
            res_w, res_h = self.camera.get_resolution()
        except Exception:  # noqa: BLE001
            return None
        if not res_w or not res_h:
            return None
        focal = intr.scaled_to(res_w, res_h).focal_px
        if not focal:
            return None
        area_scale = (res_w * res_h) / float(1280 * 960)
        min_area_px = HSV_MIN_AREA_RECT_BASE * area_scale
        if min_area_px <= 0:
            return None
        payload_area_m2 = PAYLOAD_RECT_LONG_EDGE_M * PAYLOAD_RECT_SHORT_EDGE_M
        return (focal * math.sqrt(payload_area_m2 / min_area_px)
                / HOOK_REACQUIRE_CEILING_MARGIN)

    async def _reacquire_by_climbing(self, aligned_yaw: float) -> bool:
        """Yuk kamerada yoksa irtifayi degistirip yeniden bul ve ortala.

        Operator istegi (2026-08-23). Alma irtifasinda kadraj 0.71 x 0.53 m;
        kucuk bir konum hatasi yuku kadraj disina atmaya yetiyor ve o
        noktadan korlemesine devam etmek anlamsiz.

        GOREV G / H1 (2026-09-04): yon artik KOSULSUZ YUKARI degil. Tavana
        kadar yukselir (kadraji genisletmek mesru), tavanda pay kalmayinca
        ASAGI doner -- yukun gorunen alaninin buyudugu tek yon. Alt sinir
        HOOK_VISUAL_ALIGN_ALTITUDE_M; altina inilmez.
        """
        ceiling = self._detection_ceiling_m()
        for step in range(1, HOOK_REACQUIRE_MAX_CLIMBS + 1):
            n0, e0, _d = await self.flight.get_position_ned()
            _lat, _lon, alt = await self.flight.get_global_position()

            if ceiling is None:
                # Tavan olculemedi: eski davranis (yukari), cunku alternatifi
                # uydurulmus bir sinirla asagi inmek olurdu.
                target = alt + HOOK_REACQUIRE_CLIMB_M
                direction = "yukari"
                reason = "tavan_bilinmiyor"
            elif alt + HOOK_REACQUIRE_CLIMB_M <= ceiling:
                target = alt + HOOK_REACQUIRE_CLIMB_M
                direction = "yukari"
                reason = "tavan_altinda"
            elif alt < ceiling:
                # Tam bir adim sigmiyor ama pay var: tavana kadar cik.
                target = ceiling
                direction = "yukari"
                reason = "tavana_kirpildi"
            else:
                # Pay bitti. Yukselmek yuku KUCULTUR; tek anlamli yon asagi.
                target = max(HOOK_VISUAL_ALIGN_ALTITUDE_M,
                             alt - HOOK_REACQUIRE_CLIMB_M)
                direction = "asagi"
                reason = "tavan_asildi"

            if abs(target - alt) < 0.05:
                logger.warning("Kirmizi Dikdortgen kamerada yok -- %d/%d: irtifa "
                               "%.2f m, hareket edilebilecek yer yok (%s, tavan=%s) "
                               "-- tirmanis birakiliyor.",
                               step, HOOK_REACQUIRE_MAX_CLIMBS, alt, reason,
                               f"{ceiling:.2f} m" if ceiling is not None else "yok")
                self._publish("HOOK_REACQUIRE_STEP", reason,
                              data={"step": step, "alt_m": round(alt, 3),
                                    "target_m": round(target, 3),
                                    "direction": "yok", "reason": reason,
                                    "ceiling_m": (round(ceiling, 3)
                                                  if ceiling is not None else None)})
                return False

            logger.warning("Kirmizi Dikdortgen kamerada yok -- %d/%d: %.2f m -> %.2f m "
                           "(%s, %s, tavan=%s).",
                           step, HOOK_REACQUIRE_MAX_CLIMBS, alt, target, direction, reason,
                           f"{ceiling:.2f} m" if ceiling is not None else "yok")
            self._publish("HOOK_REACQUIRE_STEP", reason,
                          data={"step": step, "alt_m": round(alt, 3),
                                "target_m": round(target, 3),
                                "direction": direction, "reason": reason,
                                "ceiling_m": (round(ceiling, 3)
                                              if ceiling is not None else None)})
            await self.flight.goto_position_ned_and_hold(n0, e0, -target, aligned_yaw, 3.0)
            if await self._locate_target_with_retries() is None:
                continue
            logger.info("Hedef yeniden bulundu -- %.2f m'de kancaya gore ortalanıyor.", target)
            await self.centering.go_to_and_center(self._rect_class, altitude_m=target)
            return True
        return False

    async def _settle_hook_onto(self, recv_ned, yaw_deg: float, alt_m: float):
        """Drive the RESTING hook onto a receiver position measured earlier.

        The camera cannot see the receiver down here, so the target comes from
        the visual alignment done at HOOK_VISUAL_ALIGN_ALTITUDE_M. What closes
        the loop is the hook's own real pose: the winch is out and the hook is
        resting, so each nudge drags it across the deck rather than swinging
        it, which is why this converges where a mid-air correction would not.

        Returns the final lateral error in metres, or None if the hook pose
        was unreadable (in which case the seating gate will refuse anyway).
        """
        last = None
        for i in range(1, HOOK_ALIGN_MAX_CORRECTIONS + 1):
            hook = getattr(self.actuator, "hook_nose_ned_offset_m", lambda: None)()
            if hook is None:
                logger.warning("[SON_DUZELTME] kanca pozu okunamadi.")
                return None
            n0, e0, _ = await self.flight.get_position_ned()
            err_n = recv_ned[0] - (n0 + hook[0])
            err_e = recv_ned[1] - (e0 + hook[1])
            last = math.hypot(err_n, err_e)
            if last <= HOOK_ALIGN_TARGET_LATERAL_M:
                logger.info("[SON_DUZELTME] %d/%d yanal %.1f mm -- hedefin icinde.",
                            i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000)
                return last
            step_n = err_n * HOOK_SETTLE_GAIN
            step_e = err_e * HOOK_SETTLE_GAIN
            # ITERASYON BASINA HAM OLCUM (2026-08-31). Onceden yalnizca hata
            # BUYUKLUGU ve komut loglaniyordu; kancanin araci takip edip
            # etmedigini anlamak icin poz gerekiyordu ve bu tur onu
            # err = 2 x komut ozdesliginden TURETMEK zorunda kalindi. Artik
            # dogrudan yaziliyor: kanca ofseti, arac NED'i ve ikisinden
            # cikan MUTLAK kanca konumu.
            logger.info("[SON_DUZELTME] %d/%d yanal %.1f mm -> (kuzey %+.3f, dogu %+.3f)"
                        "  | kanca_ofset=(%+.4f, %+.4f) arac_ned=(%.4f, %.4f)"
                        " kanca_mutlak=(%.4f, %.4f)",
                        i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000, step_n, step_e,
                        hook[0], hook[1], n0, e0, n0 + hook[0], e0 + hook[1])
            self._publish("GOREV3_CORRECTION_STEP", f"{i}/{HOOK_ALIGN_MAX_CORRECTIONS}",
                          data={"iteration": i, "lateral_mm": round(last * 1000, 1),
                                "step_n": round(step_n, 4), "step_e": round(step_e, 4),
                                "hook_offset": [round(hook[0], 4), round(hook[1], 4)],
                                "vehicle_ned": [round(n0, 4), round(e0, 4)],
                                "hook_abs": [round(n0 + hook[0], 4), round(e0 + hook[1], 4)],
                                "altitude_m": round(alt_m, 3)})
            await self.flight.goto_position_ned_and_hold(
                n0 + step_n, e0 + step_e, -alt_m, yaw_deg, HOOK_SETTLE_WAIT_S)
            # Kanca gercekten durana kadar bekle: hareket halindeyken olcmek
            # hareketi hata sanmaktir.
            #
            # BEKLEME YETERLILIGI OLCULUYOR (2026-08-31): 10 x 0.25 s = 2.5 s
            # tavani, o zamanki 0.831 s'lik sarkac periyodunun ~3 kati olarak
            # secilmisti -- ama o periyot VINC CEKILIYKEN olculdu. Tam
            # salimda ip daha uzun, periyot daha buyuk olabilir. Tavana
            # dayanip dayanmadigimiz artik loglaniyor; dayaniyorsa sabit
            # ayni orani koruyarak yeniden turetilmelidir.
            _settle_polls = 0
            for _ in range(10):
                g = getattr(self.actuator, "seating_geometry", lambda _c: None)(
                    self._color)
                if g is None or g.rel_speed_mps <= HOOK_SETTLE_MAX_SPEED_MPS:
                    break
                _settle_polls += 1
                await asyncio.sleep(0.25)
            if _settle_polls >= 10:
                logger.warning("[SON_DUZELTME] %d/%d kanca 2.5 s'de DURMADI "
                               "(bekleme tavanina dayandi) -- olcum hareket "
                               "halinde alinmis olabilir.",
                               i, HOOK_ALIGN_MAX_CORRECTIONS)
        logger.warning("[SON_DUZELTME] butce doldu; son yanal %s",
                       f"{last * 1000:.1f} mm" if last is not None else "olculemedi")
        return last

    def _hook_nose_z_m(self):
        """Kanca burnunun DUNYA z'si (metre), yoksa None.

        Guvenlik alt sinirinin olcusu. Yanal hata buyukse burun guverteden
        YANA duser ve seating_geometry().insertion_m hic kapanmaz; o durumda
        alcalmayi durduracak tek sey zemindir. Zincir buruldugunde
        (P3: span 0.235 -> 0.094) kinematik bagintiyla HESAPLANAN burun
        konumu artik gecerli degildir, bu yuzden deger GERCEK Gazebo pozundan
        okunuyor -- ayni poz, oturma kapisinin da guvendigi poz.
        """
        get_pose = getattr(self.actuator, "get_hook_world_pose", None)
        if get_pose is None:
            return None
        try:
            pose = get_pose()
        except Exception:  # noqa: BLE001 -- salt olcum, fazi dusuremez
            return None
        if pose is None:
            return None
        pos, quat, _age = pose
        off = _quat_rotate(quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))
        return pos[2] + off[2]

    def _seating_geometry(self):
        """Oturma geometrisi (aktuator yoksa/okuyamazsa None)."""
        fn = getattr(self.actuator, "seating_geometry", None)
        if fn is None:
            return None
        try:
            return fn(self._color)
        except Exception:  # noqa: BLE001
            return None

    async def _set_magnet_torque(self, enabled: bool) -> None:
        """Hizalama torkunu ac/kapa (GOREV M). Aktuator desteklemiyorsa
        (testler, gercek donanim backend'i) sessizce gecilir."""
        fn = getattr(self.actuator, "set_magnet_torque", None)
        if fn is None:
            return
        try:
            await fn(enabled)
        except Exception:  # noqa: BLE001 -- tork bir iyilestirme, fazi dusuremez
            logger.warning("[MIKNATIS] tork komutu gonderilemedi (%s).",
                           "acma" if enabled else "kapatma", exc_info=True)

    async def _magnet_righting(self, n_ned: float, e_ned: float,
                               yaw_deg: float, alt_m: float,
                               tilt0_rad: float) -> bool:
        """DEVRILMIS KANCAYI TORKLA DOGRULT (GOREV M).

        Inis DURUR, arac yerinde tutar, hizalama torku sinirli bir sure
        acilir. Egim oturma kapisinin (8 derece) icine girerse True doner ve
        inis kaldigi yerden devam eder; girmezse False ve deneme bastan
        baslar.

        SINIR -- DURUSTCE: bu, temastaki kancayi dondurmeye calisiyor. Burun
        guverteye dayaliyken donme kisitli; torkun kazanci OLCULEN devirme
        torkuna gore boyutlandirildi (3.04e-3 N*m) ama temas surtunmesi ayrica
        olculmedi. Basari orani bu yuzden VARSAYILMIYOR, olculuyor.
        """
        logger.warning("[TORK_DOGRULTMA] kanca %.1f derece devrilmis -- inis "
                       "DURDU, tork %.1f s acilip dogrultma deneniyor.",
                       math.degrees(tilt0_rad), ADAPTIVE_DESCENT_RIGHTING_S)
        self._publish("GOREV3_MAGNET_RIGHTING_START",
                      f"{math.degrees(tilt0_rad):.1f} deg",
                      data={"tilt_before_deg": round(math.degrees(tilt0_rad), 1),
                            "hold_s": ADAPTIVE_DESCENT_RIGHTING_S})
        hold = asyncio.create_task(self.flight.goto_position_ned_and_hold(
            n_ned, e_ned, -alt_m, yaw_deg, ADAPTIVE_DESCENT_RIGHTING_S))
        waited = 0.0
        tilt = tilt0_rad
        try:
            while waited < ADAPTIVE_DESCENT_RIGHTING_S:
                await asyncio.sleep(0.25)
                waited += 0.25
                g = self._seating_geometry()
                if g is None:
                    continue
                tilt = g.tilt_rad
                if tilt <= MAGNET_MAX_TILT_RAD:
                    break
        finally:
            await hold
        ok = tilt <= MAGNET_MAX_TILT_RAD
        logger.info("[TORK_DOGRULTMA] %s: egim %.1f -> %.1f derece (kapi %.1f), %.2f s",
                    "BASARILI" if ok else "BASARISIZ",
                    math.degrees(tilt0_rad), math.degrees(tilt),
                    math.degrees(MAGNET_MAX_TILT_RAD), waited)
        self._publish("GOREV3_MAGNET_RIGHTING_RESULT",
                      "basarili" if ok else "basarisiz",
                      data={"tilt_before_deg": round(math.degrees(tilt0_rad), 1),
                            "tilt_after_deg": round(math.degrees(tilt), 1),
                            "gate_deg": round(math.degrees(MAGNET_MAX_TILT_RAD), 1),
                            "waited_s": round(waited, 2), "success": bool(ok)})
        return ok

    async def _magnet_band_hold(self, n_ned: float, e_ned: float,
                                yaw_deg: float, alt_m: float, gap_m: float):
        """3-5 cm MIKNATIS BANDINDA bekle: yanal hatayi FIZIK kapatsin.

        Burada arac hicbir sey yapmaz -- yerinde durur. Kancayi ceken sey
        MagnetForceSystem'in hook_body_link'e uyguladigi gercek kuvvettir.
        Gorev katmani araci OYNATMAZ; iki ayri sey ayni kancayi cekerse
        hangisinin ne yaptigi olculemez (eski taklit tam olarak buydu ve
        7 adimda 33.8 -> 33.4 mm ile curutuldu).

        Erken cikis: yanal, yakalama yaricapinin icine girdiginde beklemenin
        surdurulmesi yalnizca butce harcar.
        """
        g0 = self._seating_geometry()
        lat0 = g0.lateral_m if g0 is not None else None
        tilt0 = g0.tilt_rad if g0 is not None else None
        logger.info("[MIKNATIS_BANDI] %.1f mm eksenel boslukta duruluyor "
                    "(%.0f-%.0f mm bandi) -- yanal %s, fizik cekiyor, en fazla "
                    "%.1f s.", gap_m * 1000,
                    MAGNET_ATTRACT_RANGE_M * 1000 * 0.6, MAGNET_ATTRACT_RANGE_M * 1000,
                    f"{lat0 * 1000:.1f} mm" if lat0 is not None else "olculemedi",
                    ADAPTIVE_DESCENT_MAGNET_HOLD_S)
        self._publish("GOREV3_MAGNET_BAND_HOLD_START", f"{gap_m * 1000:.1f} mm",
                      data={"gap_mm": round(gap_m * 1000, 1),
                            "lateral_mm": (round(lat0 * 1000, 1)
                                           if lat0 is not None else None),
                            "hold_s": ADAPTIVE_DESCENT_MAGNET_HOLD_S})
        # GOREV M: tork zaten ACIK -- artik inis basina TEK KEZ aciliyor
        # (_adaptive_descend). Gerekce orada.
        hold = asyncio.create_task(self.flight.goto_position_ned_and_hold(
            n_ned, e_ned, -alt_m, yaw_deg, ADAPTIVE_DESCENT_MAGNET_HOLD_S))
        waited = 0.0
        lat = lat0
        try:
            while waited < ADAPTIVE_DESCENT_MAGNET_HOLD_S:
                await asyncio.sleep(0.25)
                waited += 0.25
                g = self._seating_geometry()
                if g is None:
                    continue
                lat = g.lateral_m
                if lat <= MAGNET_CAPTURE_RADIUS_M:
                    logger.info("[MIKNATIS_BANDI] yanal %.1f mm -- yakalama "
                                "yaricapinin (%.1f mm) icine girdi, %.2f s'de.",
                                lat * 1000, MAGNET_CAPTURE_RADIUS_M * 1000, waited)
                    break
        finally:
            await hold
        delta = ((lat0 - lat) * 1000) if (lat0 is not None and lat is not None) else None
        logger.info("[MIKNATIS_BANDI] BITTI: yanal %s -> %s (%s), %.2f s",
                    f"{lat0 * 1000:.1f} mm" if lat0 is not None else "yok",
                    f"{lat * 1000:.1f} mm" if lat is not None else "yok",
                    f"{delta:+.1f} mm kazanc" if delta is not None else "olculemedi",
                    waited)
        self._publish("GOREV3_MAGNET_BAND_HOLD_RESULT",
                      f"{delta:+.1f} mm" if delta is not None else "olculemedi",
                      data={"lateral_before_mm": (round(lat0 * 1000, 1)
                                                  if lat0 is not None else None),
                            "lateral_after_mm": (round(lat * 1000, 1)
                                                 if lat is not None else None),
                            "gain_mm": (round(delta, 1) if delta is not None else None),
                            "waited_s": round(waited, 2),
                            "inside_capture_radius": bool(
                                lat is not None and lat <= MAGNET_CAPTURE_RADIUS_M),
                            # GOREV M: torkun bantta ne yaptigini ayri olc.
                            "tilt_before_deg": (round(math.degrees(tilt0), 2)
                                                if tilt0 is not None else None),
                            "tilt_after_deg": (round(math.degrees(gN.tilt_rad), 2)
                                               if (gN := self._seating_geometry())
                                               is not None else None)})
        return waited

    async def _adaptive_descend(self, n_ned: float, e_ned: float,
                                yaw_deg: float, start_alt_m: float):
        """KADEMELI al: sabit hedef irtifa yok, EKSENEL BOSLUK kapatilir.

        Neden bu var ve neden sabit bir irtifa calisamaz: yukaridaki
        ADAPTIF ALCALMA sabitler blokuna bakin (pencere 70 mm, EKF hatasi
        90-290 mm, yani pencerenin 1.3-4.1 kati).

        DURMA KOSULU eksenel kapidir (insertion_m >= -MAGNET_MAX_GAP_M),
        cunku alcalmanin KONTROL ETTIGI buyukluk odur. Yanal hatayi inis
        kapatmaz -- onu gorsel hizalama, _settle_hook_onto ve yakalama
        penceresindeki miknatis cekimi kapatir. Bu yuzden burasi yanal
        kapiyi BEKLEMEZ; yalnizca olcup raporlar.

        NEDEN ADIM ADIM, SUREKLI DEGIL: kapi rel_speed <= 0.05 m/s ve 0.60 s
        dwell istiyor. Alcalirken kanca da araçla birlikte iniyor, yani
        alcalma SIRASINDA kapi yapisal olarak saglanamaz. In -> dur -> olc
        zorunlu; bu bir tercih degil.

        Donen deger: fiilen KOMUT EDILEN son irtifa (m). Cagiran taraf tutma
        ve yeniden hizalamayi bu irtifada surdurmeli, GOREV3_DESCENT_
        ALTITUDE_M'de degil.
        """
        alt = start_alt_m
        t0 = time.monotonic()
        reason = "adim_tavani"
        steps = []
        magnet_holds = 0
        rightings = 0
        # ==================================================================
        # TORK: INIS BASINA TEK CIFT AC/KAPA (2026-09-05, OLCULDU)
        # ==================================================================
        # Once her epizot (bant tutusu, dogrultma) torku kendi acip
        # kapatiyordu. OLCULDU (demo_20260905_173708): her `gz topic -p`
        # yeni bir surec ve kendi gz-transport kesfini oduyor --
        #     [MIKNATIS] hizalama torku ACIK  (gonderildi, 1.18 s)
        #     [MIKNATIS] hizalama torku KAPALI (gonderildi, 1.23 s)
        # Alti gecis ~7 s saf IPC etti ve 20 s'lik inis butcesini yedi:
        #     [ADAPTIF_INIS] BITTI (butce): 6 adim, 18.6 s ... ins = -14.3 mm
        # Yani inis, ALCALMADIGI icin degil BEKLEDIGI icin 14.3 mm eksik
        # kaldi ve yakalama penceresinin yedi orneginin yedisi de yalnizca
        # eksenel kapidan dondu (yanal 0 red, egim 0 red).
        #
        # OPERATOR KARARI ("tork yalnizca serbest rejimde") KORUNUYOR:
        # inisin TAMAMI artik serbest rejim. Burun hicbir noktada guverteye
        # DAYANMIYOR -- son bosluk hedefi 2.5 mm (ADAPTIVE_DESCENT_TARGET_
        # GAP_M) ve pencere de vinci tekrar salmiyor. Ayni kosumun olcumu
        # bunu dogruluyor: inis boyunca egim 1.4-5.6 derece, yani kanca
        # serbestce sarkiyor. Degisen sey POLITIKA degil, onu uygulayan
        # mekanizmanin maliyeti.
        #
        # GERI ALMAK TEK SATIR: asagidaki iki cagriyi kaldirip epizotlarin
        # icine geri koymak yeter.
        await self._set_magnet_torque(True)
        try:
            return await self._adaptive_descend_loop(
                n_ned, e_ned, yaw_deg, start_alt_m, alt, t0, reason, steps,
                magnet_holds, rightings)
        finally:
            await self._set_magnet_torque(False)

    async def _adaptive_descend_loop(self, n_ned, e_ned, yaw_deg, start_alt_m,
                                     alt, t0, reason, steps, magnet_holds,
                                     rightings):
        """_adaptive_descend'in govdesi. Ayrildi ki tork ac/kapa tek bir
        try/finally ile inisin TAMAMINI sarsin."""
        for step in range(1, ADAPTIVE_DESCENT_MAX_STEPS + 1):
            geom = self._seating_geometry()
            if geom is None:
                # POZ YOKSA KOR ALCALMA YOK. Yokluk, "guvenli" demek degil.
                reason = "poz_yok"
                break
            gap_m = -geom.insertion_m          # >0 => burun guverteden YUKARIDA

            # DEVRILME KORUMASI (2026-09-05 kosumunda olculdu). Devrilmis bir
            # kancanin burnu, govdesi yattigi icin guverte duzlemine yakin
            # okunabilir ve eksenel kapi YANLISLIKLA "gecildi" der. Kosumun
            # 2. ve 3. denemesi tam bunu yapti: 0.90 m irtifada, tek adimda,
            # "KAPI GECILDI ... tilt=64.4 deg". 0.90 m'de burnun guvertede
            # olmasi fiziksel olarak imkansiz; okuma anlamsizdi.
            #
            # ESIK SECILMEDI: serbest asili kanca 0.005-0.9 derece olcuyor
            # (hook_seating.py) ve oturma kapisinin kendi siniri 8 derece.
            # Bunun uzerindeki bir kanca ASILI DEGILDIR -- burun konumunu
            # kordon degil TEMAS belirliyordur, dolayisiyla o poz bir inis
            # kararina temel olamaz.
            if geom.tilt_rad > MAGNET_MAX_TILT_RAD:
                # GOREV M (operator karari): once TORKLA dogrultmayi dene.
                if rightings < ADAPTIVE_DESCENT_RIGHTING_MAX:
                    rightings += 1
                    if await self._magnet_righting(n_ned, e_ned, yaw_deg,
                                                   alt, geom.tilt_rad):
                        steps.append({"step": step, "action": "tork_dogrultma",
                                      "sonuc": "basarili"})
                        continue
                    steps.append({"step": step, "action": "tork_dogrultma",
                                  "sonuc": "basarisiz"})
                reason = "devrilmis_kanca"
                logger.error("[ADAPTIF_INIS] %d: kanca DEVRILMIS (egim %.1f deg > "
                             "%.1f deg) -- burun konumu kordonla degil TEMASLA "
                             "belirleniyor, bu poz inis karari veremez. Inis "
                             "durduruluyor, deneme basarisiz sayilacak.",
                             step, math.degrees(geom.tilt_rad),
                             math.degrees(MAGNET_MAX_TILT_RAD))
                break

            # EKSENEL OKUMA, BURUN YUVANIN USTUNDE DEGILSE ANLAMSIZ.
            # OLCULDU (demo_20260905_183335, deneme 1):
            #     1 adim, 0.9 s, irtifa 0.900 m
            #     lat=217.5mm ins=+68.4mm tilt=0.4deg
            # 0.90 m irtifada burnun guverte duzleminin 68 mm ALTINDA olmasi
            # imkansiz. Sebep: insertion, yuva EKSENI boyunca alinan bir
            # IZDUSUM. Burun yukun 217 mm YANINDA duruyorsa o izdusum
            # "guverteye ne kadar yaklastim" sorusunu yanitlamaz -- yanindaki
            # bos havayi olcer. Inis bunu "kapi gecildi" sanip 0.90 m'de durdu
            # ve denemeyi harcadi.
            #
            # SINIR SECILMEDI: miknatis menzili (50 mm). Bunun otesinde ne
            # kilitlenme mumkun ne de cekim; yani burun zaten "yuvanin
            # uzerinde" sayilamaz. Devrilme korumasi bunu yakalayamiyor cunku
            # kanca DIK asili (olculen egim 0.4 derece) -- kusur duruste degil
            # KONUMDA.
            if (geom.insertion_m >= -MAGNET_MAX_GAP_M
                    and geom.lateral_m > MAGNET_ATTRACT_RANGE_M):
                reason = "yanal_menzil_disi"
                logger.error("[ADAPTIF_INIS] %d: eksenel okuma anlamsiz -- yanal "
                             "%.1f mm, miknatis menzilinin (%.0f mm) DISINDA. "
                             "Burun yuvanin ustunde degil YANINDA; insertion "
                             "(%.1f mm) bos havayi olcuyor. Inis durduruluyor.",
                             step, geom.lateral_m * 1000,
                             MAGNET_ATTRACT_RANGE_M * 1000, geom.insertion_m * 1000)
                break

            if geom.insertion_m >= -MAGNET_MAX_GAP_M:
                reason = "eksenel_kapi_gecti"
                steps.append({"step": step, "gap_mm": round(gap_m * 1000, 1),
                              "action": "dur"})
                logger.info("[ADAPTIF_INIS] %d: eksenel bosluk %.1f mm -- KAPI "
                            "GECILDI (sinir %.1f mm), inis burada duruyor "
                            "(irtifa %.3f m).", step, gap_m * 1000,
                            MAGNET_MAX_GAP_M * 1000, alt)
                break

            # ---- 3-5 cm MIKNATIS BANDI (operator karari 2026-09-05) ----
            # Kanca burada SERBEST ASILI ve miknatis yanal hatayi ancak bu
            # rejimde kapatabiliyor. Bant gecildikten sonra kanca guverteye
            # dayanir ve ayni kuvvet statik surtunmeye carpar.
            if (magnet_holds < ADAPTIVE_DESCENT_MAGNET_HOLDS_MAX
                    and gap_m <= MAGNET_ATTRACT_RANGE_M
                    and geom.lateral_m > MAGNET_CAPTURE_RADIUS_M):
                magnet_holds += 1
                spent_band = await self._magnet_band_hold(
                    n_ned, e_ned, yaw_deg, alt, gap_m)
                steps.append({"step": step, "gap_mm": round(gap_m * 1000, 1),
                              "action": "miknatis_bandi",
                              "waited_s": round(spent_band, 2)})
                continue

            nose_z = self._hook_nose_z_m()
            if nose_z is None:
                reason = "burun_z_yok"
                break
            room_m = nose_z - ADAPTIVE_DESCENT_NOSE_FLOOR_M
            if room_m <= 0.0:
                reason = "zemin_siniri"
                logger.warning("[ADAPTIF_INIS] %d: burun zemin sinirinda "
                               "(nose_z=%.4f m) -- eksenel bosluk %.1f mm hala "
                               "acik ama ALCALMA DURDURULUYOR. Bu, yanal hatanin "
                               "burnu guverteden yana dusurdugu anlamina gelir.",
                               step, nose_z, gap_m * 1000)
                break

            step_m = min(gap_m * ADAPTIVE_DESCENT_GAIN,
                         ADAPTIVE_DESCENT_MAX_STEP_M,
                         room_m)
            # Banda TAM inmek icin kirp: bandin ALTINA dusmek, miknatisin
            # serbest-asili rejimde calisma firsatini atlamak demek.
            #
            # UC KOSUL BIRDEN: (a) bant henuz kullanilmadi, (b) yanal hata
            # gercekten kapinin DISINDA -- zaten iceride ise bantta durmanin
            # kapatacagi bir sey yok ve 3 s bosa gider, (c) bandin USTUNDEYIZ.
            # (c) olmadan kirpma NEGATIF adim uretiyordu ve inis kilitleniyordu
            # (birim testte yakalandi: bosluk 6.8 mm iken kirpma -33.2 mm).
            if (magnet_holds == 0
                    and geom.lateral_m > MAGNET_CAPTURE_RADIUS_M
                    and gap_m > ADAPTIVE_DESCENT_MAGNET_GAP_M):
                step_m = min(step_m, gap_m - ADAPTIVE_DESCENT_MAGNET_GAP_M)
            # BURUN GUVERTEYE DAYANMASIN: son bosluk hedefinin altina inme.
            # Gerekcesi ADAPTIVE_DESCENT_TARGET_GAP_M'in basinda (devrilme).
            step_m = min(step_m, gap_m - ADAPTIVE_DESCENT_TARGET_GAP_M)
            if step_m < ADAPTIVE_DESCENT_MIN_STEP_M:
                # DUZELTME (r2/A kosumunda olculdu, 2026-09-05): burada
                # KOSULSUZ durulunca bosluk 6.8 mm iken oransal adim 4.76 mm
                # cikti, esik 5.0 mm oldugu icin inis kesildi ve kapi
                # ins = -6.8 mm ile 1.8 mm FARKLA kacirildi.
                #
                # Esigin gerekcesi "kapinin hukmunu degistiremeyecek kadar
                # kucuk adim atma"ydi; oysa o adim hukmu TAM DA DEGISTIRIYORDU
                # (6.8 - 4.76 = 2.0 mm, kapinin 5.0 mm'lik icinde). Dogru kural
                # adimin BUYUKLUGU degil, KAPIYA YETIP YETMEDIGI.
                if (gap_m - step_m) > MAGNET_MAX_GAP_M:
                    reason = "adim_cok_kucuk"
                    logger.info("[ADAPTIF_INIS] %d: adim %.1f mm ve sonrasinda "
                                "bosluk %.1f mm kalir (kapi %.1f mm) -- bu adim "
                                "kapiyi acamaz, duruluyor.",
                                step, step_m * 1000, (gap_m - step_m) * 1000,
                                MAGNET_MAX_GAP_M * 1000)
                    break

            hold_s = max(ADAPTIVE_DESCENT_MIN_HOLD_S,
                         step_m / ADAPTIVE_DESCENT_RATE_MPS)
            elapsed = time.monotonic() - t0
            if elapsed + hold_s + ADAPTIVE_DESCENT_SETTLE_S > ADAPTIVE_DESCENT_BUDGET_S:
                reason = "butce"
                logger.warning("[ADAPTIF_INIS] %d: butce (%.0f s) dolmak uzere "
                               "(%.1f s harcandi, adim %.1f s + %.1f s isterdi) "
                               "-- inis burada birakiliyor, bosluk %.1f mm acik.",
                               step, ADAPTIVE_DESCENT_BUDGET_S, elapsed, hold_s,
                               ADAPTIVE_DESCENT_SETTLE_S, gap_m * 1000)
                break

            alt = alt - step_m
            logger.info("[ADAPTIF_INIS] %d/%d: bosluk=%.1f mm burun_z=%.4f m "
                        "-> adim %.1f mm (hold %.1f s), yeni irtifa %.3f m "
                        "| yanal=%.1f mm tilt=%.1f deg",
                        step, ADAPTIVE_DESCENT_MAX_STEPS, gap_m * 1000, nose_z,
                        step_m * 1000, hold_s, alt, geom.lateral_m * 1000,
                        math.degrees(geom.tilt_rad))
            self._publish("GOREV3_ADAPTIVE_DESCENT_STEP", f"{step}",
                          data={"step": step,
                                "gap_mm": round(gap_m * 1000, 1),
                                "nose_z_m": round(nose_z, 4),
                                "step_mm": round(step_m * 1000, 1),
                                "alt_after_m": round(alt, 3),
                                "lateral_mm": round(geom.lateral_m * 1000, 1),
                                "tilt_deg": round(math.degrees(geom.tilt_rad), 1),
                                "rel_speed_mps": round(geom.rel_speed_mps, 3)
                                if geom.rel_speed_mps != float("inf") else None,
                                "clamped_by_floor": bool(step_m >= room_m - 1e-9)})
            steps.append({"step": step, "gap_mm": round(gap_m * 1000, 1),
                          "step_mm": round(step_m * 1000, 1),
                          "alt_after_m": round(alt, 3)})
            await self.flight.goto_position_ned_and_hold(
                n_ned, e_ned, -alt, yaw_deg, hold_s)

            # SONUMLEME. Hareket halinde olcmek, hareketi hata sanmaktir --
            # ve kapinin kendi hiz esigi (SEAT_MAX_REL_SPEED_MPS) zaten bu.
            waited = 0.0
            while waited < ADAPTIVE_DESCENT_SETTLE_S:
                g = self._seating_geometry()
                if g is None or g.rel_speed_mps <= SEAT_MAX_REL_SPEED_MPS:
                    break
                await asyncio.sleep(0.2)
                waited += 0.2

        final = self._seating_geometry()
        spent = time.monotonic() - t0
        logger.info("[ADAPTIF_INIS] BITTI (%s): %d adim, %.1f s, son irtifa "
                    "%.3f m (baslangic %.3f m). Son geometri: %s",
                    reason, len(steps), spent, alt, start_alt_m,
                    final.describe() if final is not None else "okunamadi")
        self._publish("GOREV3_ADAPTIVE_DESCENT_RESULT", reason,
                      data={"reason": reason, "steps": steps,
                            "elapsed_s": round(spent, 2),
                            "start_alt_m": round(start_alt_m, 3),
                            "reached_alt_m": round(alt, 3),
                            "final_gap_mm": (round(-final.insertion_m * 1000, 1)
                                             if final is not None else None),
                            "final_lateral_mm": (round(final.lateral_m * 1000, 1)
                                                 if final is not None else None),
                            "final_failures": (final.failures()
                                               if final is not None else None)})
        return alt, reason

    async def _hook_trace(self, duration_s: float, hz: float = 10.0):
        """Kanca izini ~hz Hz orneklet (SALT OLCUM, Y1 turu 2026-08-31).

        Amac, inisin kancayi ne zaman kaydirdigini UC AYRI ANA ayirmak:
          1. inis SIRASINDA (kanca havada asili)
          2. TEMAS aninda (burun kutuya/zemine deger)
          3. SONRASINDA (arac sabit, kanca yerde)
        Tek bir "inis kaydiriyor" sonucuna indirgememek icin burun DUNYA z'si
        de kaydedilir: temas ani, z izinin duzlestigi noktadir.

        Gorev akisina hicbir sekilde girmez; arka planda calisir, her hata
        yutulur ve iptal edilebilir.
        """
        import time as _t
        t0 = _t.monotonic()
        try:
            while _t.monotonic() - t0 < duration_s:
                off = nose_z = alt = None
                try:
                    off = self.actuator.hook_nose_ned_offset_m()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    hp = self.actuator.get_hook_world_pose()
                    if hp is not None:
                        from core.mission.hook_seating import HOOK_NOSE_OFFSET_M, _rotate
                        pos, quat, _age = hp
                        nose_z = pos[2] + _rotate(quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))[2]
                except Exception:  # noqa: BLE001
                    pass
                try:
                    alt = await self._current_alt_m()
                except Exception:  # noqa: BLE001
                    pass
                logger.info("[KANCA_IZ] t=%.2f alt=%s off_n=%s off_e=%s nose_z=%s",
                            _t.monotonic() - t0,
                            f"{alt:.3f}" if alt is not None else "-",
                            f"{off[0]:+.4f}" if off else "-",
                            f"{off[1]:+.4f}" if off else "-",
                            f"{nose_z:+.4f}" if nose_z is not None else "-")
                await asyncio.sleep(1.0 / hz)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 -- olcum gorevi dusuremez
            logger.debug("[KANCA_IZ] ornekleyici hata verdi", exc_info=True)

    async def _current_alt_m(self):
        """Vehicle relative altitude, or None. Telemetry only -- no sim truth."""
        try:
            _lat, _lon, alt = await self.flight.get_global_position()
            return alt
        except Exception:  # noqa: BLE001
            return None

    async def _align_hook_on_receiver(self, aligned_yaw: float, alt_m: float):
        """Close the loop on the REAL hook pose before attempting a pickup.

        Reads the measured hook-nose -> receiver-axis offset straight from
        Gazebo and translates the vehicle by it. Repeats until the lateral
        error is inside HOOK_ALIGN_TARGET_LATERAL_M or the correction budget
        runs out.

        Returns the final measured lateral error in metres, or None if the
        hook pose was never available (in which case the pickup will be
        refused downstream -- a hook we cannot see is a hook we cannot seat).

        Gazebo world is ENU and PX4's local frame is NED with the same axes,
        so a world (dx_east, dy_north) displacement maps to
        (north += dy, east += dx). Only a DELTA is used, so the two frames'
        origins never have to be reconciled.
        """
        last = None
        for i in range(1, HOOK_ALIGN_MAX_CORRECTIONS + 1):
            off = None
            try:
                off = self.actuator.hook_to_receiver_offset_world(self._color)
            except Exception:  # noqa: BLE001
                off = None
            if off is None:
                logger.warning("[KANCA_HIZA] kanca pozu okunamadi (%d/%d) -- "
                               "duzeltme yapilamiyor.", i, HOOK_ALIGN_MAX_CORRECTIONS)
                return None
            d_east, d_north = off
            last = math.hypot(d_east, d_north)
            if last <= HOOK_ALIGN_TARGET_LATERAL_M:
                logger.info("[KANCA_HIZA] %d/%d yanal %.1f mm -- hedefin (%.0f mm) icinde.",
                            i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000,
                            HOOK_ALIGN_TARGET_LATERAL_M * 1000)
                return last
            n0, e0, _d = await self.flight.get_position_ned()
            logger.info("[KANCA_HIZA] %d/%d yanal %.1f mm -> arac (kuzey %+.3f, dogu %+.3f) m oteleniyor.",
                        i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000, d_north, d_east)
            await self.flight.goto_position_ned_and_hold(
                n0 + d_north, e0 + d_east, -alt_m, aligned_yaw, HOOK_ALIGN_SETTLE_S)
        try:
            off = self.actuator.hook_to_receiver_offset_world(self._color)
            if off is not None:
                last = math.hypot(off[0], off[1])
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[KANCA_HIZA] butce doldu; son yanal %s",
                       f"{last * 1000:.1f} mm" if last is not None else "olculemedi")
        return last

    async def run(self, target_shape: str = None) -> bool:
        """`target_shape`: ILK birakilan seklin adi (GOREV I / A).
        Verilmezse eski davranisa dusulur (DEFAULT_PICKUP_SHAPE)."""
        from gz_system.gz_payload_actuator import SHAPE_TO_COLOR as _S2C
        shape = target_shape or DEFAULT_PICKUP_SHAPE
        # Yukun RENGI de sekle bagli: altigene KIRMIZI, ucgene MAVI yuk
        # birakiliyor. Sabit "red" varsayimi, ucgen once birakildiginda
        # aktuatoru YANLIS yuke baktiriyordu.
        self._color = _S2C.get(shape, SHAPE_TO_COLOR_RED)
        self._shape = shape
        # GOREV I / A+B: ARANAN SINIF, arena sekli DEGIL YUKUN DIKDORTGENI.
        # Altigene KIRMIZI yuk birakilir -> KIRMIZI_DIKDORTGEN aranir;
        # ucgene MAVI yuk birakilir -> MAVI_DIKDORTGEN aranir. Sabit
        # "KIRMIZI_DIKDORTGEN" varsayimi, ucgen once birakildiginda
        # YANLIS SINIFI aratiyordu.
        self._rect_class = ("KIRMIZI_DIKDORTGEN" if self._color == "red"
                            else "MAVI_DIKDORTGEN")
        # Gorunurluk stratejisi de AYNI sinifi aramali. Aksi halde faz
        # dogru hedefe gider ama strateji KIRMIZI_DIKDORTGEN arar ve
        # "bulunamadi" ile duser (canli olculdu, B1 kosumu).
        _set = getattr(self.visibility_strategy, "set_rect_class", None)
        if _set is not None:
            _set(self._rect_class)
        # GOREV I / O-A: AKTUATOR de dogru yuku olcmeli. Oturma kapisi
        # sabit "red" kullaniyordu; ucgen once birakildiginda 35.5 m
        # otedeki yanlis yuke bakiyor ve yakalama HIC mumkun olmuyordu.
        _setc = getattr(self.actuator, "set_pickup_color", None)
        if _setc is not None:
            _setc(self._color)
        logger.info("Görev 3 Faz 1 (Alma) Başlatıldı -- hedef: %s (yuk rengi: %s)",
                    shape, self._color)
        self._publish("GOREV3_PICKUP_TARGET", shape,
                      data={"shape": shape, "payload_color": self._color,
                            "source": "interlock.first_released" if target_shape
                                      else "varsayilan (geri dusus)"})

        mavi_altigen_point = self.position_store.get(shape)
        if mavi_altigen_point is None:
            raise RuntimeError(f"{shape} konumu bulunamadı! Görev 3 başlatılamaz.")

        logger.info(f"Mavi Altıgen konumuna {GOREV3_TRANSIT_ALTITUDE_M}m irtifada gidiliyor: "
                    f"{mavi_altigen_point.gps_lat}, {mavi_altigen_point.gps_lon}")
        # BUG FIX (continuous audit, 2026-08-13): this used to hold north=0/
        # east=0 -- i.e. NOT actually navigate anywhere, just change
        # altitude in place. That was an accepted simplification before
        # CenteringController.goto_global_position_and_wait() existed (see
        # its own docstring); left unfixed after that, it meant Görev 3
        # Faz 1 started searching for Kırmızı Dikdörtgen wherever Payload
        # Mission 2 happened to leave the vehicle (Kırmızı Üçgen's
        # position), never at Mavi Altıgen where the payload actually is.
        # GOREV D (2026-09-03): CLIMB-THEN-CRUISE, IKI ASAMADA.
        #
        # Onceki hal tek bir goto_global_position_and_wait(..., 1.5 m) idi ve
        # OLCULDU (PX4 ULog): 50.8 m yol, max |v_xy| 11.92 m/s, pitch max
        # 42.09 derece, 0.9-1.7 m irtifada. Mutlak pozisyon setpoint'i hizi
        # PX4'e birakiyor; tavan MPC_XY_VEL_MAX = 12.0 (olculen 11.92) ve
        # MPC_TILTMAX_AIR = 45 (olculen 42.09).
        #
        # NEDEN IKI CAGRI, TEK DEGIL: motion_fsm'de cruise_alt =
        # max(start_alt, target_alt) oldugu icin CLIMB ve DESCEND ayni bacakta
        # ASLA birlikte tetiklenemez (motion_fsm.py:221-225). Tek bir
        # goto_waypoint(..., 1.5) cagrisi max(1.5,1.5)=1.5 verir, yani duz
        # 1.5 m'de seyir -- istenen "once 3 m'ye cik, sonra yatay" profili
        # cikmaz. motion_fsm DEGISTIRILMEDI; iki cagri istenen profili
        # mevcut mekanizmayla uretiyor:
        #
        #   1) CLIMB (1.5 -> 3.0) -> HOLD -> CRUISE (~50 m @3 m) -> ARRIVAL_HOLD
        #   2) DESCEND (3.0 -> 1.5) -> ARRIVAL_HOLD          (yatay mesafe ~0)
        #
        # Kapi: motion_profile.enabled False iken goto_waypoint zaten eski
        # goto_global_position_and_wait'e duser, yani gercek ucus davranisi
        # degismez.
        converged = await self.centering.goto_waypoint(
            mavi_altigen_point.gps_lat, mavi_altigen_point.gps_lon, GOREV3_CRUISE_ALTITUDE_M)
        if not converged:
            logger.warning("Mavi Altigen'e seyir irtifasinda (%.1f m) navigasyon zaman "
                           "asimina ugradi -- yine de devam ediliyor.", GOREV3_CRUISE_ALTITUDE_M)

        # ==============================================================
        # ADIM 2 -- ONCE ARENA SEKLINI ORTALA (operator karari, 2026-09-05)
        # ==============================================================
        # OLCULEN KUSUR: bu faz, kayitli GPS noktasina varir varmaz DOGRUDAN
        # kucuk DIKDORTGENI ariyordu ve bulamayinca dusuyordu. Iki kosumda
        # ust uste (demo_20260905_152220 ve _161333) uc denemenin ucu de
        # "Kirmizi Dikdortgen yeniden bulunamadi" ile bitti.
        #
        # NEDEN ARENA SEKLI DOGRU BASLANGIC: yuk, Gorev 2'de tam bu seklin
        # MERKEZINE birakiliyor. Yani sekli ortalamak, kamerayi yukun
        # uzerine getirir -- aramaya gerek kalmaz.
        #
        # NEDEN KUCUK HEDEFLE BASLAMAK CALISMIYOR (sayilarla):
        #   yuk dikdortgeni  0.14 x 0.05 m
        #   blue_hexagon     4.00 x 3.464 m   (worlds/models/blue_hexagon/model.sdf:65)
        # 1.5 m'de kadraj 3.56 x 2.67 m. GPS/EKF hatasi 1.3 m'yi asinca
        # dikdortgen kadrajin DISINDA kalir; altigen ise hala kadrajin
        # buyuk bolumunu kaplar. Yani kucuk hedef kaybolurken buyuk hedef
        # asla kaybolmuyor.
        #
        # NEDEN SEYIR IRTIFASINDA (3.0 m), 1.5'te DEGIL: altigen 4 m ve
        # 1.5 m'de kadraja SIGMIYOR (3.56 m genislik) -- kenara degen kontur
        # dedektorun sinir kapisinda elenir. 3.0 m'de kadraj 7.11 x 5.33 m,
        # altigen 720 x 623 px ile rahatca iceride.
        logger.info("%s (arena sekli) %.1f m'de ortalanıyor -- yuk bu seklin "
                    "merkezine birakilmisti.", shape, GOREV3_CRUISE_ALTITUDE_M)
        shape_centered = await self.centering.go_to_and_center(
            shape, altitude_m=GOREV3_CRUISE_ALTITUDE_M)
        self._publish("GOREV3_PICKUP_STEP", "arena_shape_centered",
                      data={"shape": shape, "converged": bool(shape_centered),
                            "altitude_m": GOREV3_CRUISE_ALTITUDE_M})
        if not shape_centered:
            logger.warning("%s ortalanamadi -- yine de devam ediliyor "
                           "(dikdortgen aramasi kayitli konumdan baslayacak).",
                           shape)

        # ADIM 3 -- SAF DIKEY ALCALMA. Kayitli GPS noktasina GERI GITMEK
        # yukaridaki ortalamayi CÖPE ATARDI; yalnizca irtifa degisiyor.
        _sn, _se, _ = await self.flight.get_position_ned()
        _syaw = await self.flight.get_yaw_deg()
        logger.info("Ortalanan noktadan %.1f m'ye SAF DIKEY iniliyor "
                    "(yatay hareket yok).", GOREV3_TRANSIT_ALTITUDE_M)
        await self.flight.goto_position_ned_and_hold(
            _sn, _se, -GOREV3_TRANSIT_ALTITUDE_M, _syaw, 5.0)

        self._publish("GOREV3_PICKUP_STEP", "transit_complete")
        # ADIM 4 -- ARTIK kucuk dikdortgen araniyor: kamera seklin
        # merkezinde, yani yukun uzerinde.
        target = await self._locate_target_with_retries()
        if target is None:
            logger.error("%s bulunamadi -- Görev 3 Faz 1 başarısız "
                         "(alma dongusu hic baslamadi).", self._rect_class)
            return False

        alignment_delta_deg = await self.visibility_strategy.compute_alignment_yaw(target, None)
        current_yaw = await self.flight.get_yaw_deg()
        aligned_yaw = current_yaw + alignment_delta_deg
        logger.info(f"Kırmızı Dikdörtgenin uzun kenarına dik hizalanılıyor: "
                    f"{current_yaw:.1f} -> {aligned_yaw:.1f} derece")
        # BUG FIX (2026-08-21): goto_position_ned_and_hold MUTLAK NED alir
        # (mavsdk_backend_base.py: PositionNedYaw(north,east,down) dogrudan
        # offboard.set_position_ned'e gider, EKF orijinine gore). Bu faz onu
        # goreli govde otelemesiymis gibi cagiriyordu: (0, -0.30, -0.30) "0.3m
        # geride" degil, EVDEN 0.30 m batida demekti. Altigen evden 15 m
        # kuzeyde oldugu icin arac yukun ustunde kalmayip eve donuyordu.
        # Olculdu (mission7, 12:36:22): "30cm pozisyonunda hedef gorunurlugu
        # dogrulanamadi" -- hedef 15 m uzaktaydi; ve fazin son testi
        # ("Kirmizi Dikdortgen goruntude yok -> Yuk Alma Basarili") tam da
        # hedeften UZAKLASILDIGI icin gecti. Artik her hedef, o anki NED
        # konumundan govde ötelemesiyle hesaplaniyor -- log mesajlarinin
        # zaten iddia ettigi davranis.
        n0, e0, _d0 = await self.flight.get_position_ned()
        _c = math.cos(math.radians(aligned_yaw))
        _s = math.sin(math.radians(aligned_yaw))

        def _body_to_ned(forward_m: float, right_m: float):
            return (n0 + forward_m * _c - right_m * _s,
                    e0 + forward_m * _s + right_m * _c)

        await self.flight.goto_position_ned_and_hold(
            n0, e0, -GOREV3_TRANSIT_ALTITUDE_M, aligned_yaw, 2.0)

        # GERI CEKILME KALDIRILDI (2026-08-21) ve ortalama GORUS DOSTU bir
        # irtifaya tasindi. Olculdu (mission17):
        #
        #   16:25:43,257 [CENTERING] KIRMIZI_DIKDORTGEN 1/150 dx=+162px dy=+374px
        #   16:25:43,379 [LOW_ALT_OPEN_LOOP_DESCENT] goruntu 0.38m'de kayboldu
        #   16:25:43,640 [LOW_ALT_OPEN_LOOP_DESCENT] 0.341m'ye ulasildi
        #
        # Yeniden ortalama 390 ms'de dondu, yani hic ortalamadi. Sebep zincirleme:
        # GOREV3_RETREAT_DISTANCE_M=0.30 hedefi 0.30 m geriye atiyor, ardindan
        # 0.30 m'ye inildiginde kadraj yalnizca 0.71 x 0.53 m kaliyor, hedef
        # kenara/disari dusuyor ve kontrolcu acik cevrim alcalmaya geciyor.
        # dy=+374px zaten 0.208 m demek -- kamera-kanca ofsetiyle ayni mertebe.
        #
        # Geri cekilme, sabit uzunlukta sarkan bir ipi yukun uzerinden
        # SURUKLEMEK icin tasarlanmisti; vincle dogru hareket supurmek degil
        # hedefin uzerinde durup ipi salmak, yani bu adimin artik bir islevi
        # yok. Simdi: gorus dostu irtifada ortala -> kanca ofsetini orada
        # uygula -> yalnizca DIKEY in. Yatay is bittikten sonra iniyoruz, yani
        # kadrajin daralmasi artik onemli degil.
        self._publish("GOREV3_PICKUP_STEP", "yaw_aligned",
                      data={"aligned_yaw_deg": round(aligned_yaw, 2)})
        logger.info(f"{HOOK_ALIGN_ALTITUDE_M}m irtifada (gorus dostu) hedefe ortalanıyor...")
        centered = await self.centering.go_to_and_center(
            self._rect_class, altitude_m=HOOK_ALIGN_ALTITUDE_M)
        if not centered:
            logger.warning("Hizalama irtifasinda ortalama yakinsamadi -- devam ediliyor (best-effort).")

        # Bu 30cm'lik pozisyonda hedefin hâlâ görüntüde olduğunu N kare
        # boyunca doğrula (Görev 3 Rapor: "bu 30 cm'de görüntü işleme ile
        # aktif görmek istiyorum") -- best-effort görünürlük onayı, tam
        # yeniden ortalama değil (araç zaten hizalı ve konumlanmış).
        visible_frames = 0
        for _ in range(GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES * 3):
            try:
                await self.visibility_strategy.locate_target(self.detector, None)
                visible_frames += 1
                if visible_frames >= GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES:
                    break
            except RuntimeError:
                visible_frames = 0
            await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)
        if visible_frames < GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES:
            logger.warning("30cm pozisyonunda hedef görünürlüğü doğrulanamadı -- devam ediliyor (best-effort).")

        # KANCA HIZALAMASI (2026-08-21): kamera govde +0.35'te, kanca -0.35'te,
        # yani aralarinda 0.70 m var. Ortalamayi kamera yapiyor, dolayisiyla
        # hedef ORTALANDIGINDA kanca hala 0.35 m geride. Kancayi hedefin
        # uzerine getirmek icin arac 0.35 m ILERI kayar: kanca = arac +
        # govde(-0.35,0) oldugundan, arac hedef + govde(+0.35,0)'a gidince
        # kanca tam hedefe oturur. Hedef bu kaymada kameradan cikar; ayni
        # "olc, sonra korlemesine uygula" deseni payload birakmada da
        # kullaniliyor (bkz. [AIM_OFFSET_APPLIED]/[MOUNT_VECTOR_MEASURED]).
        #
        # Geri-cekil/ileri-git supurmesi kaldirildi: o koreografi sabit
        # uzunlukta sarkan bir ipi yukun uzerinden SURUKLEMEK icindi. Vincle
        # dogru hareket supurmek degil, hedefin uzerinde durup ipi salmak.
        # ALCAK IRTIFADA YENIDEN ORTALA (2026-08-21). Asagidaki oteleme
        # KOR: hedef, arac ilerledigi anda kameradan cikar. Dolayisiyla
        # otelemenin dogrulugu, BASLADIGI konumun dogrulugu kadardir.
        # Onceden baslangic noktasi 1.5 m'de yapilmis ortalamadan sonra bir
        # geri-cekilme ve bir alcalma gecirmis oluyordu; hatalar birikiyordu.
        # Olculdu: kanca yakalama alani 2.7 cm iken mission12 1. denemede
        # tuttu, mission14'te 3 denemenin hicbiri tutmadi.
        #
        # Burada tazelenmis bir ortalama, otelemeyi sifira yakin hatadan
        # baslatir. 0.30 m'de kadraj 0.71 x 0.53 m, yuk 0.14 x 0.05 m --
        # hedef rahatlikla goruste.
        #
        # NOT: gorus hatasini yanlamak (go_to_and_center'in aim_offset_body_m
        # parametresi) BILEREK kullanilmiyor: PHASE 13 D3 o yolu olcup
        # reddetti -- hedefi kadraj kenarina itip olcumun kendisini
        # bozuyordu. 0.175 m ofset 0.30 m'de 315 px eder, ayni tuzak.
        # Oteleme tazelenmis konumdan hesaplanmali.
        n0, e0, _d0 = await self.flight.get_position_ned()
        _c = math.cos(math.radians(aligned_yaw))
        _s = math.sin(math.radians(aligned_yaw))

        # GOREV I / B-S3 (2026-09-04): KANCA OFSETI BURADAN KALDIRILDI.
        #
        # OLCULEN KUSUR: ofset burada, yani GORSEL ISLERDEN ONCE
        # uygulaniyordu. Ofsetten sonra kamera yuvadan 0.175 + 0.085 =
        # 0.260 m ileride kaliyor ve 0.30 m'de bu, hedefi kadrajin
        #     0.260 * 539.9 / 0.28 = 501 px
        # asagisina atiyor -- yari-kadraj yalnizca 480 px. Yani hedef
        # KADRAJ DISINA cikiyordu ve ardindan gelen her gorsel adim
        # (gorunurluk onayi, _rect_pixel_offset, VisualHookAligner)
        # bakabilecegi bir yuk bulamiyordu. Olculdu: 0.30 m'de 30
        # yinelemede yalnizca 7 tespit.
        #
        # ONCEKI CARE 0.90 m'de hizalamakti -- kadraji genisleterek
        # semptomu bastiriyordu, sebebi degil.
        #
        # YENI SIRA (operator karari, S3): MERKEZLEME ile
        # KANCA-KONUMLANDIRMA iki AYRI adim.
        #   - Merkezleme (bu satirdan onceki go_to_and_center ve asagidaki
        #     0.30 m tekrar-ortalamasi) KAMERA OPTIK EKSENINE gore yapilir;
        #     kanca ofseti hesaba HIC girmez.
        #   - Ofset yalnizca SON konumlandirmada, tum gorsel is BITTIKTEN
        #     sonra uygulanir (asagida "hover-kilit" adiminda).
        # Ofsetten sonra hedefin kadrajdan cikmasi artik ONEMSIZ, cunku
        # ondan sonra bakan kimse yok.
        _hn, _he = n0, e0
        # Sonra YALNIZCA dikey: ayni yatay noktada alma irtifasina in.
        # HIZALAMA IRTIFASINA in, ALMA irtifasina degil.
        #
        # Kanca ofseti uygulandiktan sonra kamera yuvadan 0.260 m ileridedir
        # (0.175 kanca + 0.085 kamera kolu). 0.30 m'de bu, yuku kadrajin
        # 501 px asagisina atar -- yari-kadraj 480 px, yani DISARI. Olculdu
        # (2026-08-27 kosusu): tam burada "Kirmizi Dikdortgen yeniden
        # bulunamadi" ile faz dustu, cunku asagidaki goruntu kontrolu
        # bakabilecegi bir yuk bulamadi.
        #
        # 0.90 m'de yuva 160 px'te, yari-kadrajin %33'u. Hem asagidaki
        # goruntu dogrulamasi hem de onu izleyen gorsel hizalama ayni
        # irtifada calisir; alma irtifasina inis hizalama bittikten SONRA.
        # ==============================================================
        # DIS DENEME DONGUSU (GOREV I / B, maddeler 3-11)
        # ==============================================================
        # Spec: 3 deneme hakki, her deneme adim 3'ten (yaklasma irtifasina
        # inis) yeniden basliyor ve 60 s'lik UST BUTCESI var.
        #
        # NEDEN IC ICE FONKSIYON: asagidaki govde run()'in yerel
        # degiskenlerini (aligned_yaw, _body_to_ned, n0/e0, self._rect_class)
        # kapanisla kullaniyor. Parametre olarak gecirmek 15+ arguman
        # demekti; kapanis hem daha az koddur hem de yanlis arguman
        # gecirme sinifini tamamen ortadan kaldirir.
        #
        # DENEME SAYISI FAZDA, AKTUATORDE DEGIL: aktuatorun kendi ic
        # dongusu (HOOK_PICKUP_ATTEMPTS) 1'e cekildi. Ikisi birden 3
        # olsaydi toplam 9 yakalama penceresi olurdu; spec 3 diyor.
        # Aktuatorun ic dongusu vinci cekip yeniden hizaliyordu ama
        # 2 m'ye TIRMANIP GORSEL DOGRULAMA yapmiyordu -- spec'in istedigi
        # deneme tam olarak odur, bu yuzden sahiplik faza gecti.
        async def _attempt(attempt: int) -> bool:
            # KAPANIS BAGI: bu govde n0/e0/_c/_s'i YENIDEN ATIYOR ve
            # _body_to_ned() onlari DIS kapsamdan okuyor. nonlocal olmadan
            # atamalar yerel kalir, _body_to_ned eski (deneme oncesi)
            # konumu kullanir ve kanca ofseti yanlis noktadan hesaplanir.
            # _hn/_he ayrica atanmadan ONCE okunuyor (adim 3'teki dikey
            # inis), yani onlarsiz UnboundLocalError olur.
            nonlocal n0, e0, _c, _s, _hn, _he
            # ADIM 3 -- YAKLASMA IRTIFASINA DIKEY IN (kanca ofseti YOK).
            logger.info("%.2f m yaklasma irtifasina dikey iniliyor (ofsetsiz)...",
                        GOREV3_APPROACH_ALTITUDE_M)
            await self.flight.goto_position_ned_and_hold(
                _hn, _he, -GOREV3_APPROACH_ALTITUDE_M, aligned_yaw, 5.0)

            # ADIM 4 -- YAKLASMA IRTIFASINDA IKINCI, HASSAS ORTALAMA.
            # Hala KAMERA eksenine gore; kadraj burada 0.71 x 0.53 m oldugu
            # icin ayni piksel hatasi cok daha kucuk bir metre hatasi demek --
            # hassas gecis tam da bu yuzden burada yapiliyor.
            self._publish("GOREV3_PICKUP_STEP", "approach_altitude_reached",
                          data={"altitude_m": GOREV3_APPROACH_ALTITUDE_M})
            recentered = await self.centering.go_to_and_center(
                self._rect_class, altitude_m=GOREV3_APPROACH_ALTITUDE_M)
            if not recentered:
                logger.warning("%.2f m'de ikinci ortalama yakinsamadi -- devam "
                               "ediliyor (best-effort).", GOREV3_APPROACH_ALTITUDE_M)
            self._publish("GOREV3_PICKUP_STEP", "approach_recentered",
                          data={"converged": bool(recentered)})

            # GOREV I / B-S3: BU BLOK OFSETTEN ONCEYE TASINDI ve
            # yaklasma irtifasinda (0.30 m) kosuyor. Onceden ofsetten
            # SONRA, 0.90 m'de kosuyordu -- yani tam da 501 px kusurunun
            # icinde. Artik tum gorsel is bittikten SONRA otelenildigi
            # icin 0.90 m'lik telafi irtifasina gerek kalmadi.
            # GORUNTU ILE HIZA DOGRULAMASI (operator, 2026-08-23): "kancanin
            # yukun ortasina temas ettigini goruntu isleme ile algila".
            # Kanca yukun ortasindayken yuk, kare merkezinin
            # HOOK_BODY_OFFSET_FORWARD_M * f / irtifa kadar gerisinde gorunmeli.
            # Sapma buradan metre cinsinden okunuyor.
            #
            # Yuk kamerada HIC yoksa korlemesine devam etmek anlamsiz: 0.30 m'de
            # kadraj yalnizca 0.71 x 0.53 m, kucuk bir hata yuku disari atiyor.
            # O durumda 1 m yukselip yeniden bulunur ve kancaya gore ortalanir.
            offset_m, visible = await self._rect_pixel_offset()
            if not visible:
                if await self._reacquire_by_climbing(aligned_yaw):
                    n0, e0, _d0 = await self.flight.get_position_ned()
                    _c = math.cos(math.radians(aligned_yaw))
                    _s = math.sin(math.radians(aligned_yaw))
                    _hn, _he = _body_to_ned(HOOK_BODY_OFFSET_FORWARD_M, 0.0)
                    await self.flight.goto_position_ned_and_hold(
                        _hn, _he, -HOOK_VISUAL_ALIGN_ALTITUDE_M, aligned_yaw, 5.0)
                    offset_m, visible = await self._rect_pixel_offset()
                if not visible:
                    logger.error("Kirmizi Dikdortgen yeniden bulunamadi -- Görev 3 Faz 1 başarısız.")
                    return False
            # KALIBRASYON: goruntu tahmini ile simulator gercegini YAN YANA yaz.
            # 2026-08-23 kosusunda ikisi ayristi -- goruntu 5.7 cm, gercek 0.7 cm.
            # Sebebi henuz bilinmiyor (irtifa kaynagi dogru cikti:
            # get_global_position()[2] zaten relative_altitude_m; kamera da
            # gercekten govde +0.085'te). Tahminle duzeltmek yerine olcuyoruz:
            # birkac kosunun verisi sistematik bir sapma gosterirse duzeltilir.
            # KARAR MERCII ARTIK IKISI DE DEGIL: alma, kancanin GERCEK Gazebo
            # pozundan hesaplanan OTURMA GEOMETRISIYLE karara baglaniyor
            # (core/mission/hook_seating.py). Buradaki iki sayi yalnizca
            # goruntunun guvenilirligini olcmek icin yan yana yaziliyor.
            truth_gap = None
            try:
                # Gercek kanca pozundan olculen yanal hata (magnet DEGIL: bu
                # yapida manyetik kuvvet simule edilmiyor).
                truth_gap = self.actuator.hook_lateral_error_m(self._color)
            except Exception:  # noqa: BLE001
                pass
            try:
                _la, _lo, _alt_now = await self.flight.get_global_position()
            except Exception:  # noqa: BLE001
                _alt_now = None
            logger.info("[HIZA_KALIBRASYON] goruntu=%s  gercek=%s  irtifa=%s",
                        f"{offset_m * 100:.1f} cm" if offset_m is not None else "yok",
                        f"{truth_gap * 100:.1f} cm" if truth_gap is not None else "yok",
                        f"{_alt_now:.2f} m" if _alt_now is not None else "yok")

            if offset_m is not None:
                if offset_m <= HOOK_VISION_ALIGN_TOLERANCE_M:
                    logger.info("[GORUNTU] kanca yukun ortasinda: sapma %.1f cm (tol %.0f cm).",
                                offset_m * 100, HOOK_VISION_ALIGN_TOLERANCE_M * 100)
                else:
                    logger.warning("[GORUNTU] kanca yukun ortasinda DEGIL: sapma %.1f cm "
                                   "(tol %.0f cm) -- alma yine de denenecek; oturma kapisi "
                                   "gercek kanca pozundan kendi kararini veriyor.",
                                   offset_m * 100, HOOK_VISION_ALIGN_TOLERANCE_M * 100)

            # KAPALI CEVRIM KANCA HIZALAMASI (Blocker 1, 2026-08-26).
            # Buraya kadar her sey acik cevrimdi: kamera hedefi ortalar, arac
            # govde ofseti kadar oteler, iner. Kanca ipin ucunda oldugu icin o
            # zincirin sonunda nerede oldugu OLCULMEDEN bilinemez. Simdi
            # olculuyor ve duzeltiliyor; oturma kapisi da ayni pozu kullaniyor.
            # VINCI ONCE SAL, SONRA HIZALA (2026-08-26 canli kosusu).
            #
            # Ilk surumde sira tersti: once hizala, sonra alma mekanizmasini
            # cagir -- ve alma mekanizmasi ilk isi olarak vinci 0.40 m saliyordu.
            # Yani hizalama kanca HAVADAYKEN (vinc cekili, base_link-0.133)
            # olculuyor, sonra kanca 30 cm asagi iniyor, o inis sirasinda
            # salliniyor ve yukun YANINA konuyordu. Olculdu: hizalama 9.0 mm'ye
            # yakinsadi, ardindan oturma kapisi 12 s boyunca 38-103 mm gordu ve
            # ucunde de hakli olarak reddetti.
            #
            # Ip sarkan bir kancada olcumun BIRAKILACAGI yerde yapilmasi gerekir.
            # Vinc simdi once saliniyor, kanca guverteye/zemine oturuyor, ve
            # duzeltmeler kancanin gercek calisma pozisyonunu suruyor.
            # VINC HIZALAMA BOYUNCA TOPLU KALIR -- olculdu, 2026-08-27.
            #
            # Onceki sira (once sal, sonra hizala) gorsel hizalamayi 5.1 mm'ye
            # yakinsatiyordu ve ardindan oturma kapisi 222 mm olcuyordu. Sebep
            # gorus degil, ip: vinc acikken alma irtifasina inilince kanca
            # guverteye/zemine dayanir ve inisin geri kalani ipte GEVSEKLIK olur.
            # Bu dosyanin ve arac SDF'sinin kendi notlari gevsekligin kancayi
            # devirdigini zaten kaydediyor (olculen 49 derece). Devrilen kanca
            # hizalandigi yerde durmaz.
            #
            # Toplu vincle kanca govdenin (-0.090, 0) altinda dik sarkar ve
            # nerede oldugu bellidir. Hizalama orada bitirilir, dikey inilir
            # (dikey inis yatay hizayi bozmaz), ve vinc EN SON salinir; boylece
            # payout saf dikey bir harekettir.
            # Zaten hizalama irtifasindayiz (yukaridaki inis oraya yapildi); bu
            # yalnizca savunmaci bir teyit tutusu.
            await self.flight.goto_position_ned_and_hold(
                _hn, _he, -HOOK_VISUAL_ALIGN_ALTITUDE_M, aligned_yaw, 2.0)

            # GORSEL HIZALAMA (2026-08-27). Alici artik KAMERADAN olculuyor.
            #
            # Onceki surum yuvanin konumunu dogrudan Gazebo'dan (ground truth)
            # aliyordu. O, gercek bir dronede var olmayan bir bilgi: gorev artik
            # yuvayi goruntuden buluyor (core/detection/receiver_detector.py,
            # 66 etiketli karede alma irtifasinda 0.68 mm ortalama merkez hatasi),
            # ve hatayi kancanin GERCEK pozuna karsi kapatiyor.
            #
            # Neden piksel farki degil de metre farki: kanca kameranin ALTINDA,
            # yuva ise YERDE; iki farkli derinlik. Goruntude ust uste getirmek
            # 1.2 m'lik bir suzulmede ~0.2 m yanilir ve kancanin O45 govdesi
            # 0.65 m'nin altinda yuvanin agzini zaten kapatir. Ayrinti:
            # core/mission/visual_alignment.py.
            aligner = VisualHookAligner(
                get_frame=self.camera.get_frame,
                get_alt_m=lambda: self._current_alt_m(),
                get_yaw_deg=self.flight.get_yaw_deg,
                get_position_ned=self.flight.get_position_ned,
                get_hook_ned_offset=getattr(self.actuator, "hook_nose_ned_offset_m",
                                            lambda: None),
                goto_ned_and_hold=lambda n, e, alt, yaw: self.flight.goto_position_ned_and_hold(
                    n, e, -alt, yaw, 1.2),
                color=self._color,
                # SALT OLCUM (mekanizma 2c): gorus tahmininin yaninda gercek
                # yanal hatayi da kaydeder, karar akisina girmez.
                get_truth_lateral_m=lambda: getattr(
                    self.actuator, "hook_lateral_error_m", lambda _c: None)(self._color))
            vis = await aligner.align(GOREV3_APPROACH_ALTITUDE_M, aligned_yaw,
                                      tolerance_m=HOOK_VISUAL_ALIGN_TOLERANCE_M)
            logger.info("[GORSEL_HIZA] %s: son hata=%s, %d iterasyon, %d tespit, "
                        "%.3f m hareket", vis.reason,
                        f"{vis.final_error_m * 1000:.1f} mm" if vis.final_error_m is not None else "yok",
                        vis.iterations, vis.detections, vis.travel_m)
            # GORUS KAYBOLURSA KOR DEVAM ETME. Ama "yakinsamadi" ile "goremedim"
            # ayni sey degil: elde saglam bir yuva olcumu varsa ve artik hata
            # asagidaki duzeltmenin kapatabilecegi buyuklukteyse devam etmek
            # dogru -- son sozu zaten oturma kapisi soyluyor.
            usable = vis.converged or (
                vis.receiver_ned is not None
                and vis.final_error_m is not None
                and vis.final_error_m <= HOOK_VISUAL_ALIGN_MAX_USABLE_M)
            if not usable:
                logger.error("Görsel hizalama kullanilabilir bir olcum vermedi (%s, "
                             "hata=%s) -- Görev 3 Faz 1 GUVENLI SEKILDE durduruluyor.",
                             vis.reason,
                             f"{vis.final_error_m * 1000:.1f} mm" if vis.final_error_m else "yok")
                return False
            if not vis.converged:
                logger.warning("Görsel hizalama yakinsamadi (%s) ama yuva olcumu "
                               "saglam (artik %.1f mm) -- alma irtifasindaki "
                               "duzeltmeyle devam ediliyor.",
                               vis.reason, vis.final_error_m * 1000)
            final_lateral = vis.final_error_m
            recv_ned = vis.receiver_ned
            logger.info("[GORSEL_HIZA] yuva GORUNTUDEN olculdu: NED=(%.3f, %.3f)",
                        recv_ned[0], recv_ned[1]) if recv_ned else None
            # ADIM 5 -- HOVER-KILIT + KANCA KONUMLANDIRMA.
            # Gorsel is BITTI. Ofset SIMDI uygulaniyor: arac govde-ileri
            # HOOK_BODY_OFFSET_FORWARD_M kadar kayar, boylece kameranin
            # baktigi nokta kancanin altina gecer. Bu oteleme KOR ve tek
            # seferliktir; dogrulugu, basladigi ortalamanin dogrulugu kadardir
            # -- ve o ortalama az once 0.30 m'de tazelendi.
            n0, e0, _d0 = await self.flight.get_position_ned()
            _c = math.cos(math.radians(aligned_yaw))
            _s = math.sin(math.radians(aligned_yaw))
            _hn, _he = _body_to_ned(HOOK_BODY_OFFSET_FORWARD_M, 0.0)
            logger.info("Kanca hedefin uzerine getiriliyor (govde +%.3f m ileri, "
                        "gorsel is bitti)...", HOOK_BODY_OFFSET_FORWARD_M)
            await self.flight.goto_position_ned_and_hold(
                _hn, _he, -GOREV3_APPROACH_ALTITUDE_M, aligned_yaw, 4.0)
            self._publish("GOREV3_PICKUP_STEP", "hook_offset_applied",
                          data={"forward_m": HOOK_BODY_OFFSET_FORWARD_M,
                                "altitude_m": GOREV3_APPROACH_ALTITUDE_M,
                                "after_visual_work": True})

            # DIKEY IN, sonra VINCI SAL, sonra GORUS OLCUMUNE GORE SON DUZELTME.
            #
            # Kamera, kancanin yuvaya ULASTIGI irtifada yuvayi GOREMEZ: kanca
            # yuvanin ustundeyken kamera 0.26 m ileridedir ve 0.30 m'de bu 501 px
            # asagi duser, yari-kadraj ise 480 px. Olculdu: gorev orada 30
            # yinelemede 7 tespit yapabildi ve hakli olarak reddetti.
            #
            # Bu yuzden gorus YUKARIDA olcer, asagida UYGULANIR. Yuva hareket
            # etmez, dolayisiyla iyi olculmus bir konum sonradan kullanilabilir.
            # Son duzeltme, saklanan GORUS konumuna karsi kancanin GERCEK pozuyla
            # kapatilir -- ve sonucu her halukarda oturma kapisi dogrular.
            # SIRALAMA (2026-08-31): SAL -> HAVADA DUZELT -> DIKEY IN.
            #
            # Onceki sira "dikey in -> sal -> duzelt" idi ve iki olcum onu
            # reddediyor:
            #
            #   a) Salim hatayi aciyor. Kayitli olcum (bu dosyanin 100-113
            #      satirlari): payout ONCESI yanal 14.3 mm / egim 0.2 derece,
            #      payout SONRASI 64.6 mm / 33.3 derece.
            #   b) Salimdan SONRA kanca guverte/zemin uzerinde DINLENIYOR ve
            #      duzeltme onu takip ettiremiyor. Olculdu (2026-08-31, uc temiz
            #      kosu): arac komut yonunde kumulatif ~70 mm oteledi, kanca ise
            #      BAGIMSIZ olarak 28 / 49 / 189 mm kaydi. Ayni kontrol yasasi
            #      kanca HAVADAYKEN (gorsel hizalama fazi, vinc cekili) 18.6 /
            #      27.3 / 13.3 mm'ye yakinsiyor.
            #
            # Yani sorun kontrol yasasinda ya da olcumde degil (ikisi de dogru,
            # hook_nose_ned_offset_m gercek Gazebo pozunu okuyor); YANLIS
            # REJIMDE calistirilmasinda. Cozum rejimi degistirmek:
            #
            #   1. Vinci burada, HALA YUKARIDAYKEN sal. Kanca ~0.5 m'de serbest
            #      asili kalir, yani salimin acdigi hata duzeltilebilir bir anda
            #      olusur.
            #   2. Duzeltmeyi kanca SERBESTKEN kos -- calistigi kanitlanmis rejim.
            #   3. Sonra SAF DIKEY in. Yanal surukleme hic olmaz; dikey inis
            #      sarkaci yatay otelemeye kiyasla cok daha az uyarir.
            #
            # hook_payout_m() DEGISMEDI: salim yine SON irtifaya gore hesaplanir,
            # kanca yalnizca inis tamamlanana kadar daha yuksekte asili kalir.
            # SALIM HESABI TEK KAYNAKTAN: actuator.extend_winch_for(). Gorev
            # katmani artik hook_payout_m'i kendisi cagirmiyor; hedef irtifayi
            # verir, hesabi aktuator yapar -- alma anindaki yeniden hesapla ayni
            # kod yolundan gecer.
            _extend = getattr(self.actuator, "extend_winch_for", None)
            if _extend is not None:
                _payout_alt = await self._current_alt_m()
                logger.info("Vinc salinacak (hedef irtifa %.2f m icin) -- ARAC HALA "
                            "%.2f m'de, kanca serbest asili kalacak.",
                            GOREV3_DESCENT_ALTITUDE_M,
                            _payout_alt if _payout_alt is not None else float("nan"))
                await _extend(GOREV3_DESCENT_ALTITUDE_M)
                await asyncio.sleep(HOOK_PAYOUT_SETTLE_S)

            # ==============================================================
            # _settle_hook_onto ANA YOLDAN CIKARILDI (operator karari 2026-09-05)
            # ==============================================================
            # OLCULDU (demo_20260905_180754, deneme 2 -- kilidin oldugu deneme).
            # 60 s'lik butcenin dagilimi:
            #     gorsel blok                 22.8 s
            #     _settle_hook_onto           13.9 s  -> yanal 113.7 mm
            #     adaptif inis                15.2 s
            #     pencere -> MAGNET_LOCKED     5.6 s  -> yanal   9.5 mm
            #     SERVO3 kavrama               1.5 s sonra BUTCE DOLDU
            # Yani kanca GERCEKTEN kilitlendi (dwell 0.65 s, dort kapi da
            # gecti) ve butce tam kavrama sirasinda kesti.
            #
            # NEDEN BU ADIM KALKIYOR: 13.9 s harcayip yanali 113.7 mm'de
            # birakiyor; miknatis ayni hatayi yakalama penceresinde 5.6 s'de
            # 9.5 mm'ye indiriyor (9 cekim adimi). Yani adim artik hem daha
            # pahali hem daha kotu. Yerini alan mekanizma tesadufi degil:
            # _settle_hook_onto araci oynatarak DINLENEN kancayi surukluyordu
            # (surtunme rejimi); miknatis kancaya dogrudan kuvvet uyguluyor.
            #
            # NE KAYBEDIYORUZ (durustce): miknatisin menzili 5 cm. Yanal hata
            # bu adimin girisinde 5 cm'den buyukse kapatacak kimse kalmiyor.
            # Gorsel hizalama o hatayi kucuk birakiyor (ayni kosumda
            # "yakinsadi: 7.8 mm") ama bu bir GARANTI degil -- bu yuzden
            # atlanan noktadaki yanal OLCULMEYE DEVAM EDIYOR (asagida).
            #
            # GERI ALMAK TEK SATIR: GOREV3_SETTLE_HOOK_ONTO_ENABLED = True.
            if recv_ned is not None:
                _lat_now = None
                try:
                    _g = self._seating_geometry()
                    _lat_now = _g.lateral_m if _g is not None else None
                except Exception:  # noqa: BLE001 -- salt olcum
                    pass
                # MIKNATIS YETISEMIYORSA ESKI DUZELTME DEVREDE.
                # OLCULDU (demo_20260905_183335): ayni kosumun iki denemesinde
                # bu noktadaki yanal 217.1 mm ve 1.9 mm cikti. Ikincisinde
                # miknatis isi bitiriyor; BIRINCISINDE menzilin (50 mm) dort
                # kati uzakta ve kapatacak KIMSE yok -- adimi kosulsuz atlamak
                # o denemeyi pesinen harciyor.
                # Butce kazanci korunuyor: adim yalnizca miknatisin
                # erisemedigi durumda kosuyor, yani tipik kosumda hic kosmuyor.
                _magnet_can_reach = (_lat_now is not None
                                     and _lat_now <= MAGNET_ATTRACT_RANGE_M)
                if GOREV3_SETTLE_HOOK_ONTO_ENABLED or not _magnet_can_reach:
                    logger.info("[SON_DUZELTME] KOSULUYOR -- yanal %s, miknatis "
                                "menzili %.0f mm (%s).",
                                f"{_lat_now * 1000:.1f} mm" if _lat_now is not None
                                else "olculemedi", MAGNET_ATTRACT_RANGE_M * 1000,
                                "zorlandi" if GOREV3_SETTLE_HOOK_ONTO_ENABLED
                                else "miknatis yetisemiyor")
                    self._publish("GOREV3_PICKUP_STEP", "correction_airborne_start")
                    corrected = await self._settle_hook_onto(
                        recv_ned, aligned_yaw, HOOK_VISUAL_ALIGN_ALTITUDE_M)
                    if corrected is not None:
                        final_lateral = corrected
                else:
                    logger.info("[SON_DUZELTME] ATLANDI (operator karari): yanal "
                                "hatayi miknatis kapatiyor. Bu noktadaki yanal: %s "
                                "(miknatis menzili %.0f mm).",
                                f"{_lat_now * 1000:.1f} mm" if _lat_now is not None
                                else "olculemedi", MAGNET_ATTRACT_RANGE_M * 1000)
                    self._publish("GOREV3_SETTLE_SKIPPED",
                                  f"{_lat_now * 1000:.1f} mm" if _lat_now is not None
                                  else "olculemedi",
                                  data={"lateral_mm": (round(_lat_now * 1000, 1)
                                                       if _lat_now is not None else None),
                                        "magnet_range_mm": MAGNET_ATTRACT_RANGE_M * 1000,
                                        "in_magnet_range": bool(
                                            _lat_now is not None
                                            and _lat_now <= MAGNET_ATTRACT_RANGE_M)})
                    if _lat_now is not None:
                        final_lateral = _lat_now

            _hn, _he, _ = await self.flight.get_position_ned()
            # KANCA DENGE KONUMU: INIS ONCESI. Mekanizma 2b olcumu (2026-08-31).
            # Duzeltme dongusu kancayi 0.94 m'de hizaliyor, oturma kapisi ise
            # 0.33 m'de olcuyor. Aradaki sistematik kayma olculdu (+22.7 / +43.1
            # mm) ve bunun yalnizca %22-51'i aracin kendi kaymasiyla aciklandi.
            # Kalan terim "kancanin ARACA GORE denge konumu irtifayla degisiyor"
            # hipotezi; onu kanitlamak ya da curutmek icin ayni buyuklugu inisin
            # IKI YANINDA olcup karsilastirmak gerekiyor.
            try:
                _off_before = getattr(self.actuator, "hook_nose_ned_offset_m", lambda: None)()
            except Exception:  # noqa: BLE001 -- salt olcum, gorevi dusuremez
                _off_before = None
            _alt_before = await self._current_alt_m()
            logger.info("[KANCA_DENGE] INIS ONCESI irtifa=%s kanca_ofset=%s",
                        f"{_alt_before:.3f} m" if _alt_before is not None else "yok",
                        f"({_off_before[0]:+.4f}, {_off_before[1]:+.4f})" if _off_before else "yok")
            # Y1 OLCUM TURU: iz, inisin BASINDAN ilk alma denemesinin sonuna
            # kadar kesintisiz akar ki uc an (inis / temas / sonrasi) tek bir
            # zaman ekseninde ayirt edilebilsin.
            _trace = asyncio.create_task(self._hook_trace(45.0))
            logger.info("Hizalandi -- SAF DIKEY, KADEMELI iniliyor (yanal "
                        "hareket yok). Sabit hedef irtifa YOK: eksenel bosluk "
                        "kapanana kadar inilir.")
            self._publish("GOREV3_PICKUP_STEP", "vertical_descent_start",
                          data={"from_m": HOOK_VISUAL_ALIGN_ALTITUDE_M,
                                "mode": "adaptive",
                                "lateral_before_mm": (round(final_lateral * 1000, 1)
                                                      if final_lateral is not None else None)})
            # GOREV K (2026-09-05): SABIT IRTIFA KALDIRILDI.
            #
            # Buraya kadar tek atis vardi: goto(..., -GOREV3_DESCENT_ALTITUDE_M,
            # 6.0). Olculdu ki o sabitin isabet etmesi gereken pencere yalnizca
            # 70 mm genisliginde (burun guverteye A=0.358 m'de, zemine
            # A=0.288 m'de deger) ve PX4'un irtifa hatasi 90-290 mm, yani
            # pencerenin 1.3-4.1 KATI. Sonuc iki zit ariza olarak olculdu:
            # C1 eksenel +61..+152 mm (kanca yetismedi), P3 ins=+46 mm /
            # nose_z=-0.0987 (burun zemine gomuldu). Turetme:
            # docs/gorevK-adaptif-alcalma-faz1.md.
            #
            # ULASILAN IRTIFA ARTIK BIR DEGISKEN: tutma, yeniden hizalama ve
            # olay kayitlari bunu kullanmali. SALIM REFERANSI DEGISMEDI --
            # extend_winch_for hala GOREV3_DESCENT_ALTITUDE_M ile cagriliyor,
            # cunku inis boyunca salimin SABIT kalmasi bu hesabin on kabulu;
            # yeniden hesaplanirsa fazladan salim kapiyi bozar.
            pickup_alt, _descent_reason = await self._adaptive_descend(
                _hn, _he, aligned_yaw, HOOK_VISUAL_ALIGN_ALTITUDE_M)
            if _descent_reason == "devrilmis_kanca":
                # Devrilmis kancayla yakalama penceresine girmek, 30 s'lik
                # butceyi kesin bir basarisizliga harcamaktir: egim kapisi
                # her ornegi reddeder. Denemeyi burada bitirmek, dis dongunun
                # gorsel isi ve _settle_hook_onto'yu bastan kosmasini saglar --
                # kancayi yeniden dikey astiran sey odur.
                logger.error("Kanca devrilmis durumda -- bu deneme yakalama "
                             "penceresine sokulmuyor, bastan denenecek.")
                self._publish("GOREV3_PICKUP_ABORT", "devrilmis_kanca",
                              data={"attempt": attempt}, severity=_WARN())
                return False
            # Hizalama araci otelemis olabilir; tutma noktasi tazelenmeli.
            _hn, _he, _ = await self.flight.get_position_ned()

            logger.info("Yük alma mekanizması aktifleşiyor...")
            # KONUMU ALMA BOYUNCA TUT (2026-08-21). Yukaridaki
            # goto_position_ned_and_hold, alma baslamadan ONCE doner; alma ise
            # 3 denemede ~50 s surebiliyor. O sure boyunca hicbir setpoint
            # yayinlanmadigi icin PX4 Offboard'dan dusuyor ve arac kayiyor.
            # Olculdu (mission15, magnet mesafesi denemeler boyunca):
            #     1. deneme  4.1 cm   <- 4.0 cm esigin 1 mm disi
            #     2. deneme  9.8 cm
            #     3. deneme 11.1 cm
            # Yani ilk deneme neredeyse tutmus, sonra arac surekli uzaklasmis.
            # Setpoint akisini almaya PARALEL surdurmek bu kaymayi kaldirir.
            # TUTMA GOREVI, yeniden hizalama sirasinda DURDURULUP yeni konumda
            # yeniden baslatilabilsin diye bir kapta tutuluyor: iki ayri gorev
            # ayni anda setpoint yayinlarsa PX4 celiskili hedefler alir.
            _hold_ref = {}

            # Yalnizca "kac kez menzilde goruldu" sayaci (salt kayit).
            _attract = {"steps": 0}

            def _start_hold(n_, e_):
                _hold_ref["t"] = asyncio.create_task(self.flight.goto_position_ned_and_hold(
                    n_, e_, -pickup_alt, aligned_yaw, PICKUP_HOLD_S))

            async def _stop_hold():
                t = _hold_ref.pop("t", None)
                if t is None:
                    return
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

            # GOREV K / D: MIKNATIS ARTIK GERCEK -- BU GERI CAGRI SALT KAYIT.
            #
            # ONCEKI HALI TAKLITTI ve OLCULEREK CURUTULDU. Menzile girince
            # ARACIN tutma hedefi kancayi agiza getirecek yone kaydiriliyordu.
            # 2026-09-05 kosumu, yedi ardisik adim:
            #     adim 1: d=33.8 mm -> hedef (+58.946, -7.657)
            #     adim 2: d=33.8 mm -> hedef (+58.931, -7.670)
            #     ...
            #     adim 7: d=33.4 mm
            # Yedi adimda 33.8 -> 33.4 mm. Sebep yapisal: kanca guvertede
            # DURUYOR; araci kaydirmak onu suruklemiyor, yalnizca ipi egiyor.
            # P3'un A/B'si de ayni sonucu vermisti (yanal medyan 59.9 -> 60.3 mm).
            #
            # ARTIK: cekimi fizik cozucusu yapiyor -- MagnetForceSystem
            # hook_body_link'e gercek kuvvet uyguluyor (src/modules/simulation/
            # gz_plugins/hook_attach/HookAttachSystem.cc). Gorev katmani
            # KUVVETE KARISMAZ; aracin tutma hedefi sabit kalir, cunku iki
            # ayri sey ayni kancayi cekerse hangisinin ne yaptigi olculemez.
            async def _on_attract(d_n: float, d_e: float, dist_m: float):
                _attract["steps"] += 1
                logger.info("[MIKNATIS] menzilde: d=%.1f mm (cekimi FIZIK "
                            "uyguluyor, gorev katmani araci OYNATMIYOR)",
                            dist_m * 1000.0)
                self._publish("MAGNET_ATTRACTION_ACTIVE",
                              f"{dist_m * 1000.0:.1f} mm",
                              data={"sample": _attract["steps"],
                                    "distance_mm": round(dist_m * 1000.0, 1),
                                    "applied_by": "MagnetForceSystem"})

            async def _on_retry(attempt: int):
                """Vinc cekili (kanca havada) -- duzeltmeyi yeniden kos."""
                if recv_ned is None:
                    return
                await _stop_hold()
                logger.info("[YENIDEN_HIZA] deneme %d oncesi, kanca havada -- "
                            "duzeltme yeniden kosuluyor", attempt + 1)
                corrected = await self._settle_hook_onto(recv_ned, aligned_yaw,
                                                         pickup_alt)
                logger.info("[YENIDEN_HIZA] deneme %d icin yeni yanal: %s",
                            attempt + 1,
                            f"{corrected * 1000:.1f} mm" if corrected is not None else "olculemedi")
                self._publish("GOREV3_REALIGN_BETWEEN_ATTEMPTS",
                              f"deneme {attempt + 1}",
                              data={"next_attempt": attempt + 1,
                                    "lateral_mm": (round(corrected * 1000, 1)
                                                   if corrected is not None else None)})
                n2, e2, _ = await self.flight.get_position_ned()
                _start_hold(n2, e2)

            _start_hold(_hn, _he)
            # Vinc salimi artik IRTIFADAN turetiliyor (gz_payload_actuator.
            # hook_payout_m). Irtifa okunamazsa None gecilir ve actuator eski
            # sabit salima duser -- davranis bilinmeyen irtifada degismez.
            # KANCA DENGE KONUMU: INIS SONRASI. Yukaridaki olcumun esi.
            try:
                _off_after = getattr(self.actuator, "hook_nose_ned_offset_m", lambda: None)()
            except Exception:  # noqa: BLE001 -- salt olcum, gorevi dusuremez
                _off_after = None
            _pick_alt = await self._current_alt_m()
            if _off_before is not None and _off_after is not None:
                _d_n = _off_after[0] - _off_before[0]
                _d_e = _off_after[1] - _off_before[1]
                _d = math.hypot(_d_n, _d_e)
                logger.info("[KANCA_DENGE] INIS SONRASI irtifa=%s kanca_ofset=(%+.4f, %+.4f)"
                            "  ->  DEGISIM=(%+.1f, %+.1f) mm  |%.1f mm|",
                            f"{_pick_alt:.3f} m" if _pick_alt is not None else "yok",
                            _off_after[0], _off_after[1], _d_n * 1000, _d_e * 1000, _d * 1000)
                self._publish("GOREV3_HOOK_EQUILIBRIUM_SHIFT",
                              f"{_d * 1000:.1f} mm",
                              data={"alt_before_m": (round(_alt_before, 3)
                                                     if _alt_before is not None else None),
                                    "alt_after_m": (round(_pick_alt, 3)
                                                    if _pick_alt is not None else None),
                                    "offset_before": [round(_off_before[0], 4), round(_off_before[1], 4)],
                                    "offset_after": [round(_off_after[0], 4), round(_off_after[1], 4)],
                                    "shift_mm": round(_d * 1000, 1)})
            # O1 (Gorev G, 2026-09-04): SALIM REFERANSI ARTIK TEK KAYNAK.
            #
            # Buraya kadar iki ayri cagri extend_winch_for()'a IKI FARKLI irtifa
            # veriyordu ve ikincisi vinci GERI CEKIYORDU:
            #   :924  extend_winch_for(GOREV3_DESCENT_ALTITUDE_M=0.30) -> salim 0.330 m
            #   aktuator, her denemede: extend_winch_for(_pick_alt)    -> salim 0.124-0.191 m
            # Olculdu (docs/gorevG-FAIL3-vinc-analiz.md, 4 bagimsiz kosum): ikinci
            # cagri vinci 113-186 mm geri cekiyor ve insertion TAM O KADAR
            # bozuluyor (r1 ve r3b'de 1.00 oranla, milimetre duzeyinde birebir).
            #
            # NEDEN NOMINAL DEGER DOGRU KAYNAK, olculen _pick_alt degil:
            # alma penceresi boyunca araci tutan sey _start_hold()'dur ve o
            # -GOREV3_DESCENT_ALTITUDE_M'i komut eder. _pick_alt ise pencereden
            # ONCE alinmis TEK bir orneklemedir ve pencereyi temsil etmedigi
            # olculdu: dort kosumda _pick_alt 0.094-0.161 m okurken, kancanin
            # gercek dunya pozundan geri hesaplanan pencere irtifasi ~0.44 m
            # cikiyor. Yani _pick_alt gecici bir alcalma dibini yakaliyor,
            # tutmanin oturdugu irtifayi degil.
            #
            # _pick_alt OLCUM OLARAK KALIYOR (asagidaki olayda ve
            # [KANCA_DENGE] satirinda) -- yalnizca SALIM HESABINDA
            # kullanilmiyor.
            self._publish("GOREV3_PICKUP_STEP", "pickup_attempt_start",
                          data={"altitude_m": (round(_pick_alt, 3)
                                               if _pick_alt is not None else None),
                                # Adaptif inisin ULASTIGI komut irtifasi. Tutma
                                # bunu kullaniyor; kosumdan kosuma DEGISMESI
                                # beklenen ve istenen sonuctur -- EKF hatasinin
                                # telafi edildiginin kaniti odur.
                                "commanded_alt_m": round(pickup_alt, 3),
                                "payout_reference_alt_m": GOREV3_DESCENT_ALTITUDE_M})
            try:
                picked = await self.actuator.activate_pickup_mechanism(
                    altitude_m=GOREV3_DESCENT_ALTITUDE_M, on_retry=_on_retry,
                    on_attract=_on_attract,
                    # GOREV K (operator karari 2026-09-05): pencere vinci
                    # TEKRAR SALMASIN. Adaptif inis burnu guvertenin 4.5 mm
                    # ustunde, dort kapinin da gecilebildigi bir durumda
                    # birakiyor; tekrar salim onu guverteye indirip miknatisin
                    # devirmesine yol aciyordu (olculdu: 2.7 -> 21.7 derece,
                    # bes orneğin besi de yalnizca egim kapisindan dondu).
                    extend_winch=False)
            finally:
                await _stop_hold()
            _trace.cancel()
            try:
                await _trace
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            _report = getattr(self.actuator, "last_pickup_report", None)
            if _report is not None:
                from core.telemetry.events import Severity as _Sev
                # Severity uyesi WARN'dir, WARNING DEGIL (events.py:31). Ilk
                # yazimda WARNING kullanildi ve bu, _publish'in kendi try/except'i
                # DISINDA, cagri yerinde AttributeError'a yol acti -- olay hic
                # yayinlanmadi. 2026-08-31 taramasinin 0.04 kosusunda yakalandi.
                self._publish("HOOK_SEATING_RESULT",
                              "seated" if picked else "not_seated",
                              data=_report,
                              severity=_Sev.INFO if picked else _Sev.WARN)
            # THIRD MISSION SERVO
            # BUG FIX (2026-08-21): donus degeri ATILIYORDU. Mekanizma simule bir
            # placeholder oldugu surece zararsizdi (hep True donuyordu), ama artik
            # gercek kancayi suruyor ve basarisiz olabiliyor. Olculdu (mission10):
            # kanca 3 denemede de yuku alamadi, faz yine de devam etti ve
            # "TUM GOREVLER BASARIYLA TAMAMLANDI" raporlandi -- hicbir yuk
            # tasinmadan. Yuk alinamadiysa faz basarisizdir.
            if not picked:
                logger.error("Yük alma mekanizması yükü alamadı -- Görev 3 Faz 1 başarısız.")
                return False

            # ==============================================================
            # KILIT ONAYLANDI -- DOGRULAMA BUTCE DISINDA (2026-09-05)
            # ==============================================================
            # OLCULDU (demo_20260905_172017, deneme 1): kanca gercekten
            # kilitlendi --
            #   MAGNET_LOCKED lat=15.9mm ins=+0.2mm tilt=4.7deg v=0.013m/s
            #                 dwell 0.61 s (cekim kullanildi)
            #   SERVO3 KAVRAMA ... [HOOK] LOCKED (payload_blue) -- yuk ipte
            # -- ve hemen ardindan dogrulama tirmanisi baslarken 60 s'lik
            # deneme butcesi doldu. Faz, BASARILMIS bir almayi 'basarisiz'
            # sayip bastan denedi.
            #
            # Butcenin amaci BASARISIZ bir denemeyi kesmektir; basarilmis
            # birini atmak degil. Kilit onaylandiktan sonrasi artik yakalama
            # denemesi degil, MUHASEBE. Bu yuzden _attempt burada doner ve
            # dogrulama dis dongude, KENDI zaman asimiyla kosar.
            #
            # 3 x 60 s SPEC'I KORUNUYOR: butce hala yakalamayi sinirliyor.
            return True

        async def _verify_lift(attempt: int) -> bool:
            """KILIT SONRASI DOGRULAMA -- deneme butcesinin DISINDA.

            Gerekce _attempt'in sonundaki notta. Kendi zaman asimi var:
            2 m tirmanis (hold 2.0 s) + tespit + iki kontrol.
            """
            # Tirmanistan ONCEKI yuk irtifasi -- asagidaki dogrulama "yuk aracla
            # birlikte yukseldi mi" sorusunu buna gore cevapliyor.
            payload_z_before = self.actuator.payload_altitude_m(self._color)

                # MADDE 9 -- TEK BIR DOGRULAMA IRTIFASINA TIRMAN (2 m).
            # Eskiden [1, 2, 3] m'ye sirayla cikiliyordu; spec tek bir 2 m
            # istiyor. Uc kademe her denemeye ~3x sure ekliyordu ve 60 s'lik
            # ust butceye sigmiyordu. 2 m'de kadraj 4.7 x 3.6 m, yani yuk
            # (0.14 x 0.05 m) hala 38 x 13 px = 510 px2 ile alan kapisinin
            # (400 px2) uzerinde -- gorsel dogrulama orada calisir.
            for alt in (GOREV3_VERIFY_CLIMB_ALTITUDE_M,):
                logger.info(f"Yükseliniyor: {alt}m")
                # BUG FIX (2026-08-21): (0, 0) mutlak NED'de EV demek. Bu dongu
                # "yukselmek" isterken araci her adimda eve ucuruyordu; mission10
                # bu yuzden evden 48 m otede indi ve fazin son testi ("Kirmizi
                # Dikdortgen goruntude yok") hedeften uzaklasildigi icin gecti.
                # Yalnizca irtifa degismeli, yatay konum korunmali.
                _vn, _ve, _ = await self.flight.get_position_ned()
                await self.flight.goto_position_ned_and_hold(_vn, _ve, -alt, aligned_yaw, 2.0)
                # ADR-010 P3: `self.detector` is a FeedDetector, which answers
                # from the shared DetectionFeed and ignores the frame -- Görev 3
                # must not be a second detect() caller (see vision_runtime.py).
                # None is passed rather than a freshly grabbed frame precisely to
                # make that explicit: the frame this phase could grab is NOT the
                # frame the streak logic was advanced on.
                detections = await self.detector.detect(None)
                still_visible = any(d.shape_type == self._rect_class for d in detections)
                if still_visible:
                    logger.warning(f"{alt}m irtifada Kırmızı Dikdörtgen hâlâ görüntüde.")

            logger.info("Doğrulama kontrolü yapılıyor (son irtifa)...")
            detections = await self.detector.detect(None)
            still_visible = any(d.shape_type == self._rect_class for d in detections)

            # HUKUM TERSINE CEVRILDI (olculdu, 2026-08-23 kosusu).
            #
            # Eski test: "yuk alindiysa yerden kalkar, dolayisiyla kamerada
            # GORUNMEZ" -- ve goruntude kalmasi basarisizlik sayiliyordu. Bu,
            # yuk YERDE kalirken dogruydu. Artik yuk KANCADA asili ve kanca
            # govdenin altinda: arac yukseldikce yuk de birlikte yukseliyor ve
            # kamerada gorunmeye DEVAM ediyor. Yani eski test, basarinin ta
            # kendisini basarisizlik sayiyordu:
            #     23:35:25 [HOOK] KILITLENDI (payload_red) -- vinc acik, yuk ipte
            #     23:35:34 Kirmizi Dikdortgen hala goruntude! Alma basarisiz.
            #
            # Yeni hukum iki gercek kanita dayaniyor:
            #   1) HookAttachSystem'in /hook/state onayi (fixed joint kuruldu)
            #   2) yukun aracla BIRLIKTE yukselmis olmasi
            # Eski gozlem SILINMEDI, yalnizca hukum olmaktan cikarilip log'a
            # dusuruldu -- yuk yerde kalsaydi gorunmemesi hala anlamli bir
            # isaret, ama tek basina karar verdirmiyor.
            attached = self.actuator.is_hook_attached()
            lifted_m = None
            if payload_z_before is not None:
                z_now = self.actuator.payload_altitude_m(self._color)
                if z_now is not None:
                    lifted_m = z_now - payload_z_before

            logger.info("[ALMA_DOGRULAMA] kanca_kilitli=%s  yuk_yukseldi=%s  "
                        "dikdortgen_goruntude=%s (bu sonuncusu artik yalnizca gozlem)",
                        attached,
                        f"{lifted_m:+.2f} m" if lifted_m is not None else "olculemedi",
                        still_visible)

            if not attached:
                logger.warning("Kanca kilitli degil -- Alma başarısız.")
                return False
            if lifted_m is not None and lifted_m < PICKUP_LIFT_CONFIRM_M:
                logger.warning("Yuk aracla birlikte yukselmedi (%.2f m < %.2f m) -- "
                               "Alma başarısız.", lifted_m, PICKUP_LIFT_CONFIRM_M)
                return False

            logger.info("Yük Alma Başarılı (kanca kilitli%s).",
                        f", yuk {lifted_m:+.2f} m yukseldi" if lifted_m is not None else "")
            return True

        for attempt in range(1, GOREV3_PICKUP_MAX_ATTEMPTS + 1):
            logger.info("[ALMA] deneme %d/%d basliyor (ust butce %.0f s).",
                        attempt, GOREV3_PICKUP_MAX_ATTEMPTS,
                        GOREV3_PICKUP_ATTEMPT_TIMEOUT_S)
            self._publish("GOREV3_PICKUP_ATTEMPT_STARTED", f"{attempt}/{GOREV3_PICKUP_MAX_ATTEMPTS}",
                          data={"attempt": attempt,
                                "max_attempts": GOREV3_PICKUP_MAX_ATTEMPTS,
                                "budget_s": GOREV3_PICKUP_ATTEMPT_TIMEOUT_S})
            try:
                ok = await asyncio.wait_for(_attempt(attempt),
                                            GOREV3_PICKUP_ATTEMPT_TIMEOUT_S)
            except asyncio.TimeoutError:
                # 60 s UST BUTCESI DOLDU. Bu bir arac arizasi degil, bir
                # butce karari: denemenin ic dagilimi (4+6+30+15+5 s)
                # tasti demektir. Sonraki deneme temiz baslasin.
                ok = False
                logger.warning("[ALMA] deneme %d/%d ust butceyi (%.0f s) doldurdu "
                               "-- kesiliyor.", attempt, GOREV3_PICKUP_MAX_ATTEMPTS,
                               GOREV3_PICKUP_ATTEMPT_TIMEOUT_S)
                self._publish("GOREV3_PICKUP_ATTEMPT_TIMEOUT", f"{attempt}",
                              data={"attempt": attempt,
                                    "budget_s": GOREV3_PICKUP_ATTEMPT_TIMEOUT_S},
                              severity=_WARN())
            except Exception:  # noqa: BLE001 -- tek deneme fazi dusuremez
                ok = False
                logger.warning("[ALMA] deneme %d/%d hata ile bitti.", attempt,
                               GOREV3_PICKUP_MAX_ATTEMPTS, exc_info=True)
            self._publish("GOREV3_PICKUP_ATTEMPT_RESULT", "basarili" if ok else "basarisiz",
                          data={"attempt": attempt, "success": bool(ok)})
            if ok:
                logger.info("[ALMA] deneme %d/%d: KILIT ONAYLANDI -- dogrulama "
                            "butce disinda kosuluyor.", attempt,
                            GOREV3_PICKUP_MAX_ATTEMPTS)
                try:
                    verified = await asyncio.wait_for(
                        _verify_lift(attempt), GOREV3_PICKUP_VERIFY_TIMEOUT_S)
                except asyncio.TimeoutError:
                    verified = False
                    logger.warning("[ALMA] kilit sonrasi dogrulama %.0f s'de "
                                   "tamamlanamadi.", GOREV3_PICKUP_VERIFY_TIMEOUT_S)
                except Exception:  # noqa: BLE001
                    verified = False
                    logger.warning("[ALMA] kilit sonrasi dogrulama hata verdi.",
                                   exc_info=True)
                if verified:
                    logger.info("[ALMA] deneme %d/%d BASARILI.", attempt,
                                GOREV3_PICKUP_MAX_ATTEMPTS)
                    return True
                logger.warning("[ALMA] deneme %d/%d: kanca kilitlendi ama "
                               "dogrulama gecmedi.", attempt,
                               GOREV3_PICKUP_MAX_ATTEMPTS)

        # MADDE 12: uc denemenin hicbiri tutmadi. Bu FATAL DEGIL --
        # orkestrator GOREV3_PICKUP_ABANDONED yayinlayip finish/start
        # cizgisine doner ve gorev '2 is tamamlandi' diye biter.
        logger.error("Yük alma %d denemede de basarisiz -- alma birakiliyor "
                     "(gorev 2 is ile bitecek).", GOREV3_PICKUP_MAX_ATTEMPTS)
        self._publish("GOREV3_PICKUP_EXHAUSTED",
                      f"{GOREV3_PICKUP_MAX_ATTEMPTS} deneme tukendi",
                      data={"attempts": GOREV3_PICKUP_MAX_ATTEMPTS}, severity=_WARN())
        return False
