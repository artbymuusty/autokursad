# GÖREV G — Görev 3 (Alma / Taşıma) tam keşif

**Tarih:** 2026-09-04 · **Tip:** salt keşif, bilgi haritası · **Kod değişikliği: YOK**

Yollar `.scripts/olds/v34/v34_flight_stack/` göreli, aksi belirtilmedikçe.
Depo kökü göreli olanlar `autokursad/` ile başlar.

---

## 0 · Brief'teki varsayımların doğrulanması

Beş maddeyi tek tek kontrol ettim; **ikisi artık geçerli değil.**

| # | brief'teki ifade | durum |
|---|---|---|
| G2 | `_locate_target_with_retries()` 80×0.1 s, araç hareketsiz | ✅ `gorev3_pickup.py:177-186`, `GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS=80` (`parameters.py:115`), `OFFBOARD_SETPOINT_INTERVAL_S` uykuyla |
| G2 | "1.5 m'de kadraj ~3.55×2.65 m" | ✅ ölçüldü: **3.56 × 2.67 m** (f=539.9 px, hfov 1.74 rad, 1280×960) |
| G3 | üç GPS bacağı motion_profile'a bağlı değildi | ⚠️ **kısmen eskidi** — bkz. §5; ayrıca bacak sayısı **üç değil dört** |
| G4 | 1.5 m'de stabilite ölçülmemiş, arrival_radius 2.0 m | ✅ değişmemiş |
| G5 | `activate_pickup_mechanism` SITL'de gerçek, real'de no-op | ✅ `gz_payload_actuator.py:1507`, `real_payload_actuator.py:75` |
| arıza | "Kırmızı Dikdörtgen yeniden bulunamadı — Faz 1 sürekli başarısız" | ❌ **YANLIŞ TEKİLLEŞTİRME.** Faz 1 **üç ayrı yerde** düşüyor, bu yalnızca biri — bkz. §7.2 |

---

## 1 · TAM AKIŞ HARİTASI

### 1.1 Görev 2'den Görev 3'e devir

`master_fsm.py`:

| satır | olay |
|---|---|
| `:95` | `await self.gorev2.run()` |
| `:106-108` | `context.current_phase == MISSION_FAILED` ise Görev 3 **atlanır**, iniş |
| `:113` | *"Araç Offboard modundan çıkmadan doğrudan Görev 3'e geçer"* |
| `:118` | `gorev3_success = await self.gorev3.run()` |

**Kritik:** Görev 3'e girerken **Offboard zaten aktiftir** ve Mission kalıcı
olarak sonlanmıştır. Canlı kanıt (m1, 07:20:22):
`SEARCH COMPLETE: … Mission kalici olarak sona erdi, Offboard tek yetkili.`

### 1.2 Durum diyagramı

```
        Görev 2 biter (interlock: payload_1 ∧ payload_2 released)
                 │
                 ▼
   ┌───────────────────────────────┐
   │ check_gorev3_precondition()   │  gorev3_precondition.py:14
   │   interlock.both_released()   │  → False: GOREV3_PRECONDITION_FAILED, return False
   └──────────────┬────────────────┘  gorev3_orchestrator.py:43-49
                  ▼  GOREV3_START → GOREV3_RUNNING(reason="pickup")   :51-55
   ┌───────────────────────────────────────────────────────────┐
   │ FAZ 1  PICKUP   Gorev3PickupPhase.run()  :425-1036        │
   │  giriş: MAVI_ALTIGEN position_store'da kayıtlı            │
   │  çıkış: True = yük kancada VE tırmanışta görünmüyor       │
   │         False = 3 ayrı çıkıştan biri (§7.2)               │
   └──────────────┬────────────────────────────────────────────┘
        False ────┴──► MISSION_FAILED("gorev3_pickup_failed")  :59-61
                  ▼ True   GOREV3_RUNNING(reason="transport")  :63-64
   ┌───────────────────────────────────────────────────────────┐
   │ FAZ 2  TRANSPORT  Gorev3TransportPhase.run()  :15-43      │
   │  giriş: KIRMIZI_UCGEN position_store'da (yoksa RuntimeError):18-19
   │         GOREV3_TRANSIT_SPEED_M_S None değil (:21-25)      │
   │  çıkış: KOŞULSUZ — yakınsamasa da yalnızca WARN (:41-43)  │
   │  ⚠ dönüş değeri YOK; orkestratör sonucu KONTROL ETMİYOR :65│
   └──────────────┬────────────────────────────────────────────┘
                  ▼   GOREV3_RUNNING(reason="redrop")  :67-68
   ┌───────────────────────────────────────────────────────────┐
   │ FAZ 3  REDROP  Gorev3RedropPhase.run()  (183 satır)       │
   │  çıkış: bool; False → MISSION_FAILED("gorev3_redrop_failed"):70-74
   └──────────────┬────────────────────────────────────────────┘
                  ▼   RETURN_TO_CHECKPOINT(reason="gorev3_finish"):76-77
   ┌───────────────────────────────────────────────────────────┐
   │ FAZ 4  FINISH  Gorev3FinishPhase.run()  :15-48            │
   │  1) GOREV3_DROP_CLIMB_STEPS_M = [1,2] m tırmanış  :24-29  │
   │  2) checkpoint GPS'ine git                       :39-41   │
   │  çıkış: KOŞULSUZ (dönüş None)                             │
   └──────────────┬────────────────────────────────────────────┘
                  ▼   GOREV3_COMPLETE, return True   :80-81
```

**Brief'te "varsa Faz 3" deniyor — dört faz var, üç değil.** `REDROP`
(`gorev3_redrop.py`) ayrı bir fazdır ve `FINISH`'ten ayrıdır.

### 1.3 Faz 1'in iç adımları (`gorev3_pickup.py:425-1036`)

| # | adım | satır | irtifa | çıkış koşulu |
|---|---|---|---|---|
| 1 | `MAVI_ALTIGEN` konumu okunur | `:428-430` | — | yoksa **RuntimeError** (yakalanmaz!) |
| 2 | `goto_waypoint(…, CRUISE=3.0)` | `:464-465` | 1.5→3.0→seyir | yakınsamazsa yalnızca WARN |
| 3 | `goto_waypoint(…, TRANSIT=1.5)` | `:472-473` | 3.0→1.5 | yalnızca WARN |
| 4 | `_locate_target_with_retries()` | `:478` | 1.5 | **None → FAIL #1** `:480` |
| 5 | `compute_alignment_yaw` + yaw dönüşü | `:483-509` | 1.5 | `rotation_deg` None → RuntimeError |
| 6 | `go_to_and_center(alt=1.2)` | `:533-534` | 1.2 | yakınsamazsa WARN (devam) |
| 7 | görünürlük onayı N=3 kare | `:540-552` | 1.2 | başarısızsa WARN (devam) |
| 8 | kanca ofseti +0.175 m ileri | `:592-595` | 1.2 | — |
| 9 | dikey iniş 0.90 m | `:608-609` | 0.90 | — |
| 10 | `_rect_pixel_offset()` | `:625` | 0.90 | görünmüyorsa → adım 11 |
| 11 | `_reacquire_by_climbing()` ×3 | `:227-245` | +1 m/adım | **False → FAIL #2** `:632` |
| 12 | görsel hizalama (`VisualHookAligner`) | `:734` | 0.90 | `usable` değilse **FAIL** |
| 13 | vinç sal + `_settle_hook_onto` | `:247-320` | alma irtifası | — |
| 14 | `activate_pickup_mechanism()` | `:937-938` | `_pick_alt` | **False → FAIL #3** `:965` |
| 15 | 1/2/3 m tırmanış + görünmezlik onayı | `:958-…` | 1→2→3 | yük hâlâ görünüyorsa FAIL |

---

## 2 · ARAMA / TESPİT MANTIĞI

### 2.1 Görev 3'e özgü ayrı bir arama mekanizması var mı

**Hayır, ayrı bir arama YOK.** Görev 2'nin rota-tabanlı taraması Görev 3'te
hiç kullanılmaz. Görev 3 yalnızca **tek noktada, hareketsiz** sorgular:

- `_locate_target_with_retries()` (`gorev3_pickup.py:177-186`) — 80 deneme,
  her biri `visibility_strategy.locate_target()`, aralarında
  `OFFBOARD_SETPOINT_INTERVAL_S` uyku. **Araç hiç hareket etmez.**
- `RectangleAlignmentStrategy.locate_target()`
  (`rectangle_alignment_strategy.py:29-37`) — feed'i tarar, ilk
  `KIRMIZI_DIKDORTGEN`'i döndürür, yoksa `RuntimeError`.
- Tek "arama benzeri" hareket `_reacquire_by_climbing()`
  (`:227-245`): 3 kez 1'er metre **yukarı**, yatay tarama yok.

### 2.2 Dedektör: dikdörtgen için ne gerekiyor

`hsv_contour_detector.py::_detect_rectangle` (`:113-186`), sırayla:

| # | kapı | satır | değer |
|---|---|---|---|
| 1 | kontur alanı ≥ `HSV_MIN_AREA_RECT_BASE × area_scale` | `:124` | **400 px²** (`parameters.py:822`) |
| 2 | `approxPolyDP` eps ∈ linspace(0.02, 0.06, 5) → **tam 4 köşe VE dışbükey** | `:127-129` | `HSV_EPS_RECT_MIN/MAX` (`:823-824`) |
| 3 | en kısa kenar ≥ 8 px | `:131` | |
| 4 | **çerçeve kenarına değmemeli** (margin 3 px) | `:154` | 2026-08-27 eklendi |
| 5 | poligon içi renk oranı ≥ `HSV_COLOR_FRAC_RECT` | `:162` | **0.40** (`:825`) |
| 6 | streak: 3 ardışık kare, merkez kayması ≤ 60 px | `:189-196` | `HSV_STREAK_FRAMES=3`, `HSV_STREAK_DIST_PX=60` (`:812-813`) |
| 7 | zaten commit edilmiş bir şekille "aynı nesne" olmamalı | `:319`, `:324-372` | `HSV_RECT_DUPLICATE_AREA_RATIO=0.50` (`:838`) |

Karşılaştırma — **altıgen** (`:256-291`): tam 6 köşe (`:264`), tek eps
(`HSV_EPS_HEX=0.026`), min alan **800 px²**, renk oranı 0.45,
**kenara değme kontrolü YOK**. Brief'teki "6 dışbükey köşe" doğru.

**Üçgen** (`:210-255`): 3 köşe, eps ∈ linspace(0.03, 0.09, 6), min alan 390 px².

### 2.3 `HSV_STREAK_FRAMES` Görev 3'te farklı mı

**Farklı değil — global.** `parameters.py:812`, dedektörün kendi iç durumu
(`_update_streak`, `:189-196`), faz farkındalığı yok. Ama streak sayacı
**şekil sınıfı başına ayrı** (`red_rect`, `blue_rect`, `triangle`, `hexagon`).

Önemli: Görev 3'e **gerçek dedektör verilmiyor.** `main_gz.py:158`
`feed_detector` (bir `FeedDetector`, `vision_runtime.py:58-77`) veriyor —
yani Görev 3 `detect()` çağırmaz, tek üreticinin (`VisionRuntime`, 10 Hz,
`vision_runtime.py:254`) yayınladığını okur. ADR-010 P3, `main_gz.py:155-157`:
eskiden gerçek dedektör veriliyordu ve streak durumunu bozuyordu — **bu
hata kapatılmış.**

`[VISION] detect() calisiyor` günlük satırı **3 s'lik bir heartbeat**tir
(`vision_runtime.py:199,222,225`), döngü hızı değil.

### 2.4 Kadraj hesabı — ölçülmüş sayılar

f = (1280/2)/tan(1.74/2) = **539.9 px** (`mono_cam/model.sdf:54-57`,
`camera_intrinsics.py:93-131`).

| irtifa | kadraj (m) | yük 0.14×0.05 m → px | alan px² | 400 px² kapısına pay | altıgen 2.00 m → px |
|---|---|---|---|---|---|
| 0.90 | 2.13 × 1.60 | 84 × 30 | **2519** | 6.3× | 1200 → **kadrajı taşar** |
| 1.20 | 2.84 × 2.13 | 63 × 22 | **1417** | 3.5× | 900 → sığar |
| **1.50** | **3.56 × 2.67** | 50 × 18 | **907** | **2.3×** | 720 → sığar |
| 2.20 | 5.21 × 3.91 | 34 × 12 | **421** | **1.05×** | 491 |
| 2.60 | 6.16 × 4.62 | 29 × 10 | **302** | **0.76× → REDDEDİLİR** | 415 |
| 3.00 | 7.11 × 5.33 | 25 × 9 | **227** | **0.57× → REDDEDİLİR** | 360 |

**Bu tablo raporun en önemli tek çıktısı.** Arama irtifası 1.5 m'de yük
alan kapısına yalnızca **2.3 kat** pay bırakıyor; **~2.25 m'de pay biter.**
Altıgen ise 3 m'de bile rahatça görünür — yani "altıgeni görüyor, yükü
görmüyor" tam olarak beklenen imzadır.

**"Kadraja girme olasılığı" HİÇ HESAPLANMIYOR.** Kodda ne saha üretim
kurallarına ne şekil mesafelerine bakan bir kontrol var; faz "gittiğim yerde
göreceğim" varsayar.

---

## 3 · GEOMETRİ VE SAHA ÜRETİMİ

`autokursad/Tools/simulation/gz/worlds/generate_competition_area.py`:

| sabit | değer | satır |
|---|---|---|
| `AREA_WIDTH_M` × `AREA_LENGTH_M` | 30 × 100 m | `:114-115` |
| `EDGE_MARGIN_M` | 3.0 m | `:117` |
| `HEX_TRI_MIN_DIST_M` | **25.0 m alt sınır, üst sınır YOK** | `:120` |
| `MIN_SHAPE_SEPARATION_M` | 5.0 m (kareler ↔ diğer her şey) | `:121` |

Dört şekil üretilir (`:222-241`): `blue_hexagon`, `red_triangle`,
`red_square`, `blue_square` — hepsi reject-sampling ile rastgele.

**Kırmızı Dikdörtgen bir saha şekli DEĞİLDİR.** Görev 3'ün hedefi
`payload_red` — Görev 2'nin mavi altıgene bıraktığı **fiziksel yük**.
Konumu üretim kuralıyla değil, Görev 2'nin bırakma isabetiyle belirlenir.

### 3.1 Ölçülen mevcut yerleşim ve isabet

`default.sdf` (bu oturumun sahası):

| nesne | konum |
|---|---|
| `blue_hexagon` | (−3.274, 3.834) |
| `red_triangle` | (0.788, 82.664) |
| `red_square` | (6.942, 57.330) |
| `blue_square` | (−9.315, 79.064) |

`PAYLOAD_FINAL_POSE` (MAVI_ALTIGEN), **5 koşumun beşinde de bit-aynı**:
(−3.317, 3.941) → altıgen merkezine **0.115 m**. Yük gerçekten hedefin
üzerinde.

⚠️ **Beş koşumda bit-aynı olması bir ölçüm uyarısıdır:** SITL oturumu
koşumlar arasında yeniden başlatılmadı, dolayısıyla yükler m1'de bırakıldığı
yerde kaldı ve m2–m5 onları yeniden bırakmadı. Görev 3 açısından sonuç aynı
(yük altıgenin üzerinde), ama **bağımsız beş örnek değil, bir örnek.**

### 3.2 Şekil ve yük boyutları

| nesne | geometri | kaynak |
|---|---|---|
| `blue_hexagon` | mesh scale **2** → **2.00 × 1.732 m** | `worlds/models/blue_hexagon/model.sdf:11,57` |
| `red_square` | 1 × 1 m | `worlds/models/red_square/model.sdf:27` |
| `payload_red` gövde | **box 0.140 × 0.050 × 0.052 m** | `default.sdf:357` |
| `payload_red` görsel | `kursad_payload/meshes/payload_body.stl`, ambient/diffuse **0.75 0.05 0.05** | `default.sdf:713-721` |

Renk kontrolü: RGB(0.75,0.05,0.05) → OpenCV HSV **H=0, S=238, V=191**;
`HSV_RED_LO_1=(0,40,40)` … `HI_1=(15,255,255)` → **maskeye giriyor.** Renk
sorun değil.

⚠️ **Ölü model uyarısı:** `Tools/simulation/gz/models/payload_cyl_red/model.sdf`
hâlâ depoda ve **silindir (r=0.15, h=0.05)** tanımlıyor. `default.sdf` onu
kullanmıyor — ama kod ve testlerdeki bazı yorumlar hâlâ "payload cylinder's
0.30 m" diyor (`hsv_contour_detector.py:344`, `test_d2c…py:83`). **Belge ile
gerçek ayrışmış durumda.**

### 3.3 Arama başlangıç noktası — kadraja girme garantisi

Faz 1, `position_store`'daki **MAVI_ALTIGEN** konumuna gider
(`gorev3_pickup.py:428-473`), Görev 2'nin bıraktığı yere değil. Bu doğru
tasarım. Ama:

- **Garanti YOK.** 1.5 m'de kadraj 3.56 × 2.67 m. Yük altıgen merkezinden
  0.115 m'de, yani navigasyon hatası **~1.3 m**'yi (kadrajın yarısı) geçmedikçe
  yük kadrajın içindedir. Bu geniş bir pay.
- **Asıl kırılganlık konum değil, İRTİFA** (§2.4 tablosu): 2.25 m üzerinde
  yük alan kapısını geçemez, oysa kadrajın içindedir.

---

## 4 · AKTÜATÖR VE INTERLOCK ZİNCİRİ

### 4.1 Dört servo noktası

`real_system/real_payload_actuator.py:10-13` (denetim B8, 2026-09-02):

| servo | metot | görev |
|---|---|---|
| FIRST MISSION SERVO | `release_payload_at_mavi_altigen` | Görev 2, 1. bırakma |
| SECOND MISSION SERVO | `release_payload_at_kirmizi_ucgen` | Görev 2, 2. bırakma |
| **THIRD MISSION SERVO** | **`activate_pickup_mechanism`** | **Görev 3 Faz 1 (alma)** |
| GRAB SERVO | `activate_drop_mechanism` | Görev 3 Faz 3 (redrop) |

**Faz 1'de yalnızca THIRD MISSION SERVO kullanılır.**

### 4.2 Çağrı zinciri

```
Gorev3PickupPhase.run()                       gorev3_pickup.py:937-938
  └─ actuator.activate_pickup_mechanism(altitude_m=_pick_alt, on_retry=_on_retry)
        ├─ SITL : GzPayloadActuator                gz_payload_actuator.py:1507-…
        │           HOOK_PICKUP_ATTEMPTS kez:
        │             extend_winch_for(altitude_m, deck_height_m)
        │             temas doğrulanır → HookAttachSystem fixed joint
        └─ GERÇEK: RealPayloadActuator             real_payload_actuator.py:75-110
                    yalnızca log + asyncio.sleep(YER TUTUCU) — TODO[DONANIM]
```

Arayüz: `i_payload_actuator.py:22`
`activate_pickup_mechanism(self, altitude_m=None, deck_height_m=…, on_retry=None)`.
İmza uyumsuzluğu (denetim B2) düzeltilmiş; `tests/test_actuator_interface_parity.py:25,32`
bunu koruyor.

### 4.3 Başarı doğrulaması — üç katmanlı

1. **Oturma kapısı** (`hook_seating.py`), gerçek Gazebo kanca pozundan:
   `SEAT_MAX_LATERAL_M` (`:119`, ağız yarıçapı türevi), `SEAT_MIN/MAX_INSERTION_M`
   (`:134-135`, −0.004 … +0.022 m), `SEAT_MAX_TILT_RAD` 15° (`:144`),
   `SEAT_DWELL_S` 0.30 s (`:156`), `SEAT_MAX_REL_SPEED_MPS` 0.05 (`:163`).
   **Eşiklerin hiçbiri "koşum geçsin diye" seçilmemiş** (`:102` notu).
2. **Dönüş değeri** `picked` (`:937`) → False ise **FAIL #3** (`:965`).
   `last_pickup_report` `HOOK_SEATING_RESULT` olayı olarak yayınlanır (`:946-951`).
3. **Görsel görünmezlik onayı**: `GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M = [1,2,3]` m
   (`parameters.py:74`) — tırmanışta yük artık görünmemeli.
   Ayrıca `PICKUP_LIFT_CONFIRM_M = 0.30` (`gorev3_pickup.py:126`).

---

## 5 · MOTION_PROFILE ENTEGRASYONU — ŞU ANKİ TAM DURUM

**Kodu okudum, varsaymadım.** Görev D'den bu yana **başka kimse
değiştirmemiş** (`git log public/main..HEAD -- gorev3_transport.py gorev3_finish.py` boş).

| bacak | dosya:satır | çağrı | motion_profile'a bağlı mı |
|---|---|---|---|
| pickup — seyir | `gorev3_pickup.py:464` | `centering.goto_waypoint(…, CRUISE=3.0)` | ✅ **EVET** |
| pickup — iniş | `gorev3_pickup.py:472` | `centering.goto_waypoint(…, TRANSIT=1.5)` | ✅ **EVET** |
| **transport** | `gorev3_transport.py:39-40` | `goto_global_position_and_wait(…, TRANSIT=1.5)` | ❌ **HAYIR — eski yol** |
| **finish** | `gorev3_finish.py:41` | `goto_global_position_and_wait(lat, lon, checkpoint_alt)` | ❌ **HAYIR — eski yol** |
| finish — tırmanış | `gorev3_finish.py:29` | `goto_position_ned_and_hold` | ❌ (zaten NED) |
| redrop | `gorev3_redrop.py` | ayrı incelenmedi (kapsam dışı bırakılmadı, §9'a borç) | — |

Görev D **yalnızca pickup bacağını** iki aşamalıya çevirdi
(`gorev3_pickup.py:441-473` yorumu). **transport ve finish hâlâ eski yolda.**

### 5.1 Config değerleri — teyit edildi

| parametre | değer | satır | not |
|---|---|---|---|
| `GOREV3_CRUISE_ALTITUDE_M` | **3.0** | `parameters.py:38` | ✅ |
| `GOREV3_TRANSIT_ALTITUDE_M` | **1.5** | `parameters.py:20` | ✅ |
| `GOREV3_TRANSIT_SPEED_M_S` | **2.0** | `parameters.py:126` | ⚠️ bkz. aşağı |
| `GOREV3_DESCENT_ALTITUDE_M` | 0.30 | `:63` | import ediliyor, `run()`'da kullanılmıyor |
| `GOREV3_RETREAT_DISTANCE_M` | 0.30 | `:68` | **geri çekilme 2026-08-21'de kaldırıldı** (`gorev3_pickup.py:536-556`) — parametre ölü |
| `GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS` | 80 | `:115` | |
| `GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES` | 3 | `:116` | |

**`GOREV3_TRANSIT_SPEED_M_S` hâlâ "tanımlı ama uygulanmıyor".** İki rolü var:
- `gorev3_transport.py:21-25` — **None ise faz RuntimeError ile durur** (kapı olarak işlevsel),
- `:33-38` yorumu açıkça: *"not yet actually enforced as a velocity cap …
  goto_global_position_and_wait streams position setpoints and lets PX4's own
  position controller fly toward them at its configured speed"*.

Yani **hız sınırı hiçbir yerde uygulanmıyor**; değer yalnızca bir "ölçüldü mü"
bayrağı. Brief'teki tespit **hâlâ geçerli.**

---

## 6 · F SERİSİ İLE ETKİLEŞİM

### 6.1 F1 guard (Offboard flapping, Seçenek A) — Görev 3'te **DEVREDE DEĞİL**

`_note_offboard_failure` yalnızca `gorev2_orchestrator.py:786`'dan çağrılıyor;
sayaç `self._offboard_failures` `Gorev2Orchestrator`'a ait (`:142`).
`switch_to_offboard()` yalnızca **iki** yerden çağrılıyor:
`master_fsm.py:328` ve `gorev2_orchestrator.py:762`. **Görev 3 hiç çağırmıyor**
— Offboard'u zaten devralmış durumda (§1.1). Guard Görev 2'ye özgüdür.

### 6.2 F2-a (`ENABLE_ROUTE_REJOIN`) — Görev 3'te **UYGULANMIYOR**

Rejoin `Gorev2Orchestrator._resume_mission_route()` içinde
(`gorev2_orchestrator.py:275`, `:427-449`, `:530`) ve **PX4 Mission rotasına**
dönmek içindir. Görev 3'ün kendi rotası yoktur; hepsi Offboard GPS/NED
bacaklarıdır. Ayrıca Görev 3'e girildiğinde Mission kalıcı olarak sonlanmıştır.

### 6.3 E4e (ıraksama guard'ı, `_mount_translate`) — Görev 3'te **KULLANILMIYOR**

`_mount_translate` (`centering_controller.py:385-445`) yalnızca
`descend_to_release()` içinden çağrılıyor (`:374`) ve yalnızca
`aim_offset_body_m`/`mount_body_m` verildiğinde iş yapıyor (`:311`).
Bu, **Görev 2'nin yük bırakma yoludur.**

Görev 3 bu yolu **bilerek kullanmıyor** — `gorev3_pickup.py:579-582`:
*"gorus hatasini yanlamak (go_to_and_center'in aim_offset_body_m parametresi)
BILEREK kullanilmiyor: PHASE 13 D3 o yolu olcup reddetti — hedefi kadraj
kenarina itip olcumun kendisini bozuyordu."*

Görev 3 bunun yerine **kendi** kapalı çevrimini kurmuş:
`VisualHookAligner` (`visual_alignment.py`) + `_settle_hook_onto`
(`gorev3_pickup.py:247-320`) + `hook_seating.py` kapısı.

**Özet: F serisinin üç mekanizmasının hiçbiri Görev 3'e dokunmuyor.**
Görev 3'ün başarısızlığı F kampanyasından bağımsızdır.

---

## 7 · MEVCUT TEST KAPSAMI

### 7.1 Birim testleri — neyi kapsıyor, neyi kapsamıyor

`tests/test_gorev3_pickup.py` (6 test, `:166-311`):

| test | ne kapsıyor |
|---|---|
| `…raises_without_recorded_mavi_altigen` | adım 1 |
| `…full_sequence_succeeds_and_confirms_shape_gone` | mutlu yol |
| `…fails_when_rectangle_never_found` | FAIL #1 |
| `…aborts_when_the_real_hook_pose_is_unavailable` | poz kaynağı |
| `…closes_the_loop_on_the_seen_receiver` | kapalı çevrim |
| `…refuses_safely_when_the_receiver_is_never_seen` | güvenli durma |

**Hepsi `_RectangleUntilPickedUpDetector` ile mock'lanmış** (`:20-32`):
`Detection(shape_type="KIRMIZI_DIKDORTGEN", …)` doğrudan üretiliyor.
**Gerçek tespit mantığı (HSV, kontur, alan kapısı, streak) bu testlerde
HİÇ çalışmıyor.** Faz mantığı test ediliyor, görüş test edilmiyor.

Gerçek dedektörü koşturan testler: `test_hsv_contour_detector.py`,
`test_d2c_one_contour_one_class.py`, `test_detector_exclusivity.py`,
`test_adr010_release_altitude_and_display.py`.

**Görev 3 senaryosunun tek uçtan uca görüş testi:**
`test_d2c_one_contour_one_class.py:112-122`
`test_payload_on_hexagon_is_reported_end_to_end_at_gorev3_altitude`.
Sentetik kareyi `_hexagon_frame()` (`:78-93`) üretiyor ve **geometrisi
GÜNCEL DEĞİL**:

| testin varsaydığı | gerçek | kaynak |
|---|---|---|
| altıgen **900 px** = "5.00 m @ 3.0 m" | altıgen **2.00 m** (2026-08-29'da 5→2 düşürüldü) → 3.0 m'de **360 px** | `blue_hexagon/model.sdf:11,47-53` |
| yük **`cv2.circle`, 54 px** = "payload cylinder's 0.30 m" | yük **box 0.140 × 0.050 m** → 3.0 m'de **25 × 9 px** | `default.sdf:357` |
| irtifa **3.0 m** | `run()` **1.5 m**'de arıyor (`:472,478`) | `parameters.py:20` |

Yani bu test **hiçbir gerçek irtifada, hiçbir gerçek şekil boyutuyla** yükü
temsil etmiyor. 54 px'lik daire alanı ≈ 2290 px² (kapı 400 px²) — **5.7 kat
pay**; gerçek yük 1.5 m'de 907 px² ile **2.3 kat**, 3.0 m'de 227 px² ile
**kapıyı geçemez**. Test yeşil kalırken saha kırmızı olabilir — **ve öyle.**

### 7.2 Canlı SITL — Faz 1'in TÜM başarısızlıkları

Bu oturumun 5 koşumu + bugünkü diğer 2 koşum tarandı
(`.scripts/olds/v34/logs/mission_20260904_*.log`):

| koşum | saat | düştüğü yer | mesaj |
|---|---|---|---|
| m1 `acc5020f3187` | 07:22:48 | **FAIL #3** `:965` | Yük alma mekanizması yükü alamadı |
| m2 `cd6c3cf6370e` | 07:31:53 | **FAIL #3** `:965` | Yük alma mekanizması yükü alamadı |
| m3 `4bffff2d42d3` | 07:37:45 | **FAIL #1** `:480` | Kırmızı Dikdörtgen bulunamadı |
| m4 `e9d16e5914fb` | 07:45:17 | **FAIL #2** `:632` | Kirmizi Dikdortgen yeniden bulunamadi |
| m5 `e7c0f2922093` | — | ulaşamadı | koşum dışarıdan iptal edildi |
| 04:08:59 | — | **FAIL #1** | Kırmızı Dikdörtgen bulunamadı |
| 04:51:31 | — | **FAIL #2** | Kirmizi Dikdortgen yeniden bulunamadi |

**Ortak örüntü YOK — üç farklı çıkış, dağılım 2/2/2.** Brief'in
"her zaman aynı" varsayımı **çürüdü**.

Ama tespit tarafındaki iki başarısızlığın (FAIL #1, #2) **ortak imzası var:**

```
m3 07:37:26 → 07:37:45  (8 s, 7 heartbeat)   hepsi:  ['MAVI_ALTIGEN']
m4 07:44:10 → 07:44:42  (32 s, 200/200 deneme)      hepsi:  ['MAVI_ALTIGEN']
m1 07:21:07 (BAŞARILI)                       ['MAVI_ALTIGEN', 'KIRMIZI_DIKDORTGEN']
```

**Altıgen her karede görülüyor, yük görülmüyor.** Araç doğru yerde, kamera
çalışıyor, hedef kadrajda — yalnızca yük sınıflandırılamıyor. Ve **aynı
nominal irtifada m1'de sınıflandırılıyor.** Yani tespit **kesintili**, yapısal
olarak imkânsız değil.

m4'ün tırmanış dizisi ayrıca bir irtifa tutarsızlığı gösteriyor:
```
1/3: 3.6 m'ye yukseliniyor    → sonraki okuma 5.4 m  (+1.8)
2/3: 6.4 m'ye yukseliniyor    → sonraki okuma 8.1 m  (+1.7)
3/3: 9.1 m'ye yukseliniyor
```
İlk tırmanış 0.90 m komutundan sonra **2.6 m**'de tetiklenmiş. m1/m2'de aynı
komut **0.72 m** ve **1.28 m** vermiş (`[HIZA_KALIBRASYON]` satırları).
Yani irtifa tutarlılığı **±0.4 m ile +1.7 m arasında değişiyor.**

---

## 8 · İLGİLİ ADR'LER

`docs/adr/` — ADR-004…011, hepsi **2026-08-16/17 tarihli.**

| ADR | Görev 3 hakkında ne diyor | güncel kodla tutarlı mı |
|---|---|---|
| **ADR-004** `:112`, `:136-138`, `:252` | Görev 3 fazlarını (precondition/pickup/transport/redrop/finish) sayar; `GOREV3_START`'ın girişi *"Görev 2 complete, Offboard not exited"* | ✅ tutarlı (§1.1) |
| **ADR-005** `:107`, `:133-137`, `:216` | O tarihte Görev 3 **erişilemezdi** (`MasterMissionController` bağlı değildi); dashboard'un `Gorev3Orchestrator`'a enjekte edildiğini söyler | ❌ **eskimiş** — artık erişilebilir ve dashboard enjeksiyonu ADR-004 §3 gereği **kaldırılmış** (`gorev3_orchestrator.py:16-23`) |
| **ADR-008 / 009 / 010** | Görev 3'e **özgü** bir arama/kadraj/aktüatör kararı **YOK** | — |
| **ADR-010 P3** | Görev 3 gerçek dedektör yerine feed kullanmalı | ✅ uygulanmış (`main_gz.py:155-158`) |
| **ADR-011** `:160` | *"Görev 3's pickup target **is** a rectangle"* | ⚠️ doğru ama **boyut belirtmiyor**; silindir/kutu karışıklığını çözmüyor |

**Hiçbir ADR şunları kaydetmiyor:** arama stratejisi (tek nokta, hareketsiz,
80 deneme), kadraj varsayımları, alan kapısının irtifa payı, aktüatör
oturma geometrisi. Bunların **tamamı yalnızca kod yorumlarında** belgeli.

`docs/TODO-adr-guncellemeleri.md:15` bunu zaten madde 7 olarak yazmış:
*"ADR'ler 2026-08-17'de duruyor … ADR süreci koda ayak uyduramamış."*
**Görev 3 bu boşluğun en büyük mağduru:** faz 2026-08-21 → 08-27 arasında
en az beş kez yeniden tasarlanmış (geri çekilme kaldırıldı, hizalama irtifası
0.30 → 0.55 → 0.90 m, vinç sırası ters çevrildi, kapalı çevrim eklendi) ve
**bunların hiçbiri ADR'lere girmemiş.**

---

## 9 · KAPSAM DIŞI BIRAKTIKLARIM (dürüstlük notu)

- `gorev3_redrop.py` (183 satır) ve `visual_placement.py` (301 satır)
  **okunmadı** — Faz 3'ün iç mantığı bu raporda yok. Faz 1 odaklı istendi,
  ama §1'in tamlığı için borç olarak işaretliyorum.
- `visual_alignment.py` (397 satır) yalnızca çağrı noktasından incelendi.
- `payload_body.stl` mesh'inin **tepeden siluetinin** gerçekten temiz bir
  dikdörtgen olup olmadığı **doğrulanmadı** (kanca yuvası/bore var). Bu,
  §10'daki H2'nin doğrudan konusu.
- Faz 1'in başarısız olduğu koşumlarda **gerçek irtifa telemetrisi**
  (ULog `vehicle_local_position`) çekilmedi; §7.2'deki irtifa tutarsızlığı
  yalnızca uygulama günlüğünden çıkarıldı.

---

## 10 · HİPOTEZ — KANITLANMAMIŞ

> ⚠️ **BU BÖLÜM KESİN TEŞHİS DEĞİLDİR.** Aşağıdakilerin hiçbiri ölçümle
> kapatılmadı; PROMPT 2'nin başlangıç noktası olarak yazıldı. Her biri için
> onu çürütecek ölçümü de yazdım.

### Önce: "tek bir neden" arayışı yanlış kurulmuş

Faz 1 üç ayrı yerde düşüyor (§7.2) ve dağılım 2/2/2. **En az iki bağımsız
arıza var:** bir *tespit* arızası (FAIL #1, #2) ve bir *oturma* arızası
(FAIL #3). Bunları tek hipotezle açıklamaya çalışmak hata olur.

### H1 — İRTİFA PAYI (tespit arızası için EN OLASI)

**İddia:** Arama irtifası 1.5 m'de yük, alan kapısına yalnızca **2.3 kat**
pay bırakıyor (907 px² / 400 px²) ve **~2.25 m'de pay biter.** Ölçülen irtifa
tutarlılığı ise **+1.7 m**'ye kadar sapıyor (§7.2, m4). Araç nominalde
1.5 m'de olduğunu sanırken 2.3–2.6 m'de olduğunda yük **sessizce** alan
kapısında elenir — **altıgen aynı karede rahatça görülmeye devam eder** (415 px),
ki gözlenen imza tam budur.

**Neden en olası:** gözlenen üç olguyu birden açıklıyor — (a) altıgen var/yük
yok imzası, (b) aynı nominal irtifada kesintili başarı, (c) m4'te tırmanma
denemelerinin hiçbirinin işe yaramaması (her tırmanış payı daha da azaltır —
`_reacquire_by_climbing` **yanlış yönde** hareket ediyor).

**Çürütme ölçümü:** FAIL #1/#2 anında ULog `vehicle_local_position.z` ile
`get_global_position()[2]`'yi yan yana koy. İkisi de ~1.5 m ise H1 ölür.

### H2 — MESH SİLUETİ / 4-KÖŞE KAPISI

**İddia:** `payload_body.stl` tepeden bakıldığında temiz bir dikdörtgen
olmayabilir (kanca yuvası, pah, alt plaka). `approxPolyDP` eps ∈ [0.02, 0.06]
aralığında **tam 4 dışbükey köşe** vermiyorsa (`hsv_contour_detector.py:129`)
tespit sessizce düşer. Küçük piksel sayısında (1.5 m'de 50 × 18 px) bir-iki
pikselllik yuvarlama bunu kolayca çevirir.

**Çürütme ölçümü:** Faz 1 irtifasında tek bir kareyi kaydet, kırmızı maskeyi
çıkar, beş eps değerinin her birinde `len(approx)` ve `isContourConvex` bas.

### H3 — STREAK KAPISI (3 ardışık kare, ≤60 px)

**İddia:** `HSV_STREAK_FRAMES=3` yük için de geçerli. 1.5 m'de yük 50 px
uzunluğunda; araç Offboard'da sallanırken merkez 60 px'ten fazla
kayarsa streak sıfırlanır ve **hiç commit edilmez.** Altıgen 720 px olduğu
için aynı sallanmadan etkilenmez — **imza yine aynı.**

**Çürütme ölçümü:** `_update_streak` çağrılarını yükle birlikte logla; FAIL
anında `_streak["red_rect"]` sayacının kaç olduğunu gör.

### H4 — OTURMA GEOMETRİSİ (FAIL #3 için, ayrı arıza)

**İddia:** m1/m2'de tespit çalıştı, hizalama çalıştı, **oturma kapısı
reddetti.** `[HIZA_KALIBRASYON]` m1'de görüntü 5.3 cm / gerçek 3.7 cm,
m2'de 4.9 cm / **9.8 cm** — görüntü ile gerçek arasında **iki kat sapma** ve
`SEAT_MAX_LATERAL_M` ~23 mm mertebesinde. Yani hizalama "iyi" derken kanca
yuvanın 4× dışında olabiliyor.

**Çürütme ölçümü:** `HOOK_SEATING_RESULT` olayının `failures()` listesini
oku — `lateral`, `too_high`, `tilt`, `speed`'den hangisi düşürüyor.

### Öncelik önerim

1. **H1** — en ucuz ölçüm, en çok olguyu açıklıyor, ve doğruysa
   `_reacquire_by_climbing`'in yönü **ters** demektir (yukarı değil aşağı).
2. **H4** — ayrı arıza, ayrı ölçüm, m1/m2 verisi zaten elde.
3. **H2/H3** — H1 çürürse sıraya girer.

**Ölçüm hijyeni uyarısı:** bir sonraki koşum setinde **SITL her koşumdan önce
yeniden başlatılmalı.** Bu oturumda başlatılmadı ve beş koşumun yük pozları
bit-aynı çıktı (§3.1) — o veri bağımsız beş örnek değil.
