# V34 Sistem Denetimi — GZ/Real Paritesi, Dashboard, Servo Noktaları, Climb-then-Cruise

**Tarih:** 2026-09-02
**Kapsam:** Yalnızca inceleme ve raporlama. **Hiçbir kod değişikliği yapılmamıştır.**
**Denetlenen kök:** `.scripts/olds/v34/`

İlgili: [flight-control-analysis.md](flight-control-analysis.md) ·
[climb-then-cruise-hw-checklist.md](climb-then-cruise-hw-checklist.md) · `docs/adr/`

---

## 0. Yönetici Özeti

Denetim beş başlıkta yapıldı. Sonuç kısaca: **görev algoritması gerçekten tek
bir paylaşılan çekirdekten geliyor, ama gerçek uçuş yolu (`main_real.py`) o
çekirdeği çalıştırmak için gereken üç parçayı kurmuyor.** İkisi gerçek uçuşta
görevi işlevsel olarak durdurur.

| # | Bulgu | Ağırlık |
|---|---|---|
| B1 | `main_real.py` **`VisionRuntime` kurmuyor** → gerçek uçuşta tespit beslemesi hiç doldurulmuyor; arama kör | **Kritik** |
| B2 | `RealPayloadActuator.activate_pickup_mechanism()` imzası çağrıyla uyumsuz → Görev 3 Faz 1'de `TypeError` | **Kritik** |
| B3 | `main_real.py` macOS ana-thread boyama pompasını kurmuyor → gerçek uçuşta dashboard penceresi **hiç açılmıyor** (macOS) | **Yüksek** |
| B4 | `main_real.py` sinyal işleyicilerini kurmuyor (ADR-010 R4) → arka planda başlatılan gerçek uçuşta Ctrl-C/`kill -INT` sessizce yutulabilir | **Yüksek** |
| B5 | `Gorev3PickupPhase` gerçek yolda `publisher` almıyor → o fazın olayları telemetriye/dashboard'a hiç düşmüyor | Orta |
| B6 | `Gorev3PickupPhase` gerçek yolda `FeedDetector` yerine ham `detector` alıyor → ADR-008 B1'in "tek detect() çağıranı" değişmezi gerçek yolda ihlal | Orta |
| B7 | README.md ve SETUP.md **tamamen v32 dönemine ait** (v34 atfı: 0). Climb-then-Cruise, `motion_profile`, `goto_waypoint` hiç geçmiyor | Orta |
| B8 | Servo noktaları var ve işaretli ama **açı/süre parametreleri yalnızca 1/4 noktada yazılı**; kalan üçü boş `TODO` | Orta |

---

## 1. İki Çalıştırma Script'i Arasındaki Mimari

### 1.1 Script katmanı

| | `run_mission_v34_gz.sh` | `run_mission_v34_real.sh` |
|---|---|---|
| Satır | 78 | 15 |
| `PYTHONPATH` | ✅ aynı | ✅ aynı |
| `resolve_python.sh` | ✅ | ✅ |
| `gz_env.sh` source | ✅ (gz-transport partition) | — (doğru, gz yok) |
| **Unified dashboard başlatma** | ✅ ayrı process | ❌ **yok** |
| Entrypoint | `gz_system/main_gz.py` | `real_system/main_real.py` |

Script katmanı sağlıklı; tek anlamlı fark dashboard (bkz. §2).

### 1.2 Paylaşılan çekirdek — gerçekten paylaşılıyor

| Katman | Satır | Durum |
|---|---|---|
| `core/` | 11.964 | **%100 ortak** |
| `mavsdk_common/` | 699 | **%100 ortak** |
| `gz_system/` | 2.755 | GZ'ye özel |
| `real_system/` | **254** | Gerçeğe özel (4 dosya) |

`real_system/` yalnızca dört dosya: `main_real.py` (153), `real_flight_backend.py`,
`real_camera_source.py`, `real_payload_actuator.py`. Uçuş backend'i boş bir alt
sınıf (`class RealFlightBackend(MavsdkBackendBase): pass`) — MAVSDK mantığı
birebir ortak.

**Kod tekrarı YOK.** İki `_run()` gövdesi normalize edilip diff'lendi: ortak
kısım tüm görev algoritmasıdır — `detector`, `validator`, `selector`,
`debounce`, `position_store`, `interlock`, `checkpoint`, `detection_feed`,
`CenteringController` (+ kazanç ve `motion_profile` enjeksiyonu),
`PayloadReleaseService`, `PayloadMissionSequencer`, `Gorev2Orchestrator`,
dört Görev 3 fazı, `Gorev3Orchestrator`, `MasterMissionController`,
`ops_center`, `mission_timeout_hook`.

### 1.3 SAPMA — `main_real.py`'de eksik olanlar

Yorumsuz kod satırı: `main_gz._run` = 206, `main_real._run` = 65.

#### B1 (KRİTİK) — `VisionRuntime` hiç kurulmuyor

ADR-010 P3, vision döngülerini `Gorev2Orchestrator`'dan alıp
`core/detection/vision_runtime.py`'a taşıdı ve onu **tek üretici** yaptı.
Doğrulanmış zincir:

- `Gorev2Orchestrator`'da artık `_detection_loop` / `_frame_grab_loop` **yok**
  (grep: eşleşme yok)
- `DetectionFeed.publish()` üretimde **tek bir yerden** çağrılıyor:
  `core/detection/vision_runtime.py:206`
- `VisionRuntime(...)` üretimde **tek bir yerde** kuruluyor:
  `gz_system/main_gz.py:125`
- `Gorev2Orchestrator.__init__`'in `vision_runtime` parametresi **opsiyonel**
  (`=None`) ve sınıfın kendi yorumu diyor ki (`gorev2_orchestrator.py:210-216`):
  *"`vision_runtime` is optional and is never CREATED here -- this class does
  not own the pipeline."*
- `main_real.py` ne `VisionRuntime` kuruyor ne de `vision_runtime=` geçiriyor

**Sonuç:** gerçek uçuşta `detection_feed` hiç doldurulmaz. `Gorev2Orchestrator`
(`detection_feed.detections()`), `CenteringController` ve
`PayloadReleaseService` hepsi boş besleme okur → arama hiçbir hedefi
doğrulayamaz, merkezleme sürekli "hedef kayboldu" görür, dashboard kamera
paneli hiç güncellenmez. Aynı boşluk `dual_system/main_dual.py`'de de var.

> Not: `main_real.py` `camera.start()` çağırıyor (o kısım doğru), ama kareyi
> okuyup `detect()` çağıracak ve `detection_feed.publish()` yapacak döngü
> hiç başlatılmıyor.

#### B2 (KRİTİK) — Aktüatör imza uyumsuzluğu

- Arayüz: `IPayloadActuator.activate_pickup_mechanism(self, altitude_m=None, deck_height_m=None, on_retry=None)`
- GZ: `gz_payload_actuator.py:1238` — üç argümanı da alıyor ✅
- **Gerçek: `real_payload_actuator.py:37` — `activate_pickup_mechanism(self)`, argüman YOK** ❌
- Çağrı: `core/mission/gorev3_pickup.py:906-907`
  `await self.actuator.activate_pickup_mechanism(altitude_m=_pick_alt, on_retry=_on_retry)`

Gerçek uçuşta Görev 3 Faz 1 servo tetikleme anına ulaştığında **`TypeError`**.

#### B4 (YÜKSEK) — Sinyal işleyicileri yok

`main_gz.py:197` `_install_signal_handlers()` tanımlıyor ve ADR-010 R4'ün
gerekçesini taşıyor: arka planda (`&`) başlatılan bir process
`SIGINT = SIG_IGN` miras alır, Python o durumda `default_int_handler`
kurmaz, dolayısıyla `KeyboardInterrupt` **asla** doğmaz ve `kill -INT`
sessizce yutulur — 2026-08-17'de doğrudan kanıtlanmış.

`main_real.py`'de `signal` kelimesi **hiç geçmiyor**. Yani bu koruma
yalnızca simülasyonda var, gerçek uçuşta yok.

#### B5 / B6 — Görev 3 pickup fazının kurulumu

| | GZ | Gerçek |
|---|---|---|
| Detector | `feed_detector` (`FeedDetector`) | ham `detector` |
| `publisher` | ✅ geçiliyor | ❌ geçilmiyor |

`FeedDetector` yerine ham detector vermek, ADR-008 B1'in *"tam olarak bir
`detect()` çağıranı"* değişmezini gerçek yolda kırar (HSVContourDetector'ın
şekil-başına streak durumu yalnızca tek çağıranla tutarlı). `publisher`
verilmemesi ise o fazın olaylarını telemetri/dashboard'dan tamamen düşürür.

#### GZ'ye özel olması DOĞRU olanlar

`GzPoseMonitor` (Gazebo ground truth), `apply_gz_env()`, `GzCameraSource` +
camera_service/ZMQ, `GzPayloadActuator`. Bunlar sapma değil, ortam farkı.

---

## 2. Mission Dashboard Entegrasyonu

**İki farklı mekanizma var ve bu tasarım bilinçli** — `ops_center.py:157-168`
gerekçeyi açıkça yazıyor:

| | GZ | Gerçek |
|---|---|---|
| In-process `MissionOpsDashboard` | **KAPALI** (`legacy_dashboard_default="0"`) | **AÇIK** (varsayılan `"1"`) |
| Ayrı process unified dashboard | ✅ `run_mission_v34_gz.sh` başlatıyor | ❌ **başlatılmıyor** |
| Nerede tetikleniyor | `run_mission_v34_gz.sh` → `tools/mission_dashboard_unified.py` | `main_real.py:41` → `build_ops_center()` → `ops_center.start()` |

`KURSAD40_LEGACY_DASHBOARD` ortam değişkeni her iki yönde de ezebiliyor.

### B3 (YÜKSEK) — Gerçek uçuşta macOS'ta pencere hiç açılmıyor

`core/telemetry/dashboard.py:287`:
```python
self._delegate_paint = (not self._headless) and sys.platform == "darwin"
```
macOS'ta dashboard `cv2.imshow` çağırmaz; kareyi `MAIN_THREAD_PAINT`
köprüsüne yayınlar (`dashboard.py:354`). Köprüyü **ana thread'de boşaltacak
bir pompa gerekir**.

- `main_gz.py::_run_with_main_thread_gui` bu pompayı çalıştırıyor
  (`MAIN_THREAD_PAINT.take()` döngüsü) ✅
- `main_real.py` `asyncio.run(_run(...))` diyor; `darwin`, `MAIN_THREAD_PAINT`,
  `threading` kelimelerinin **hiçbiri geçmiyor** ❌

**Sonuç:** macOS'ta `./run_mission_v34_real.sh` çalıştırıldığında dashboard
kareleri besler, köprüye yazar ve **kimse okumadığı için hiçbir pencere
açılmaz**. Linux/Windows'ta `_delegate_paint` False olduğu için kendi
thread'inde boyar ve çalışır.

Yani sorunun cevabı: **hayır, her iki script'te de gerçekten tetiklenmiyor.**
GZ'de açılıyor; gerçek uçuşta (bu makinenin platformu olan macOS'ta) açılmıyor.

---

## 3. Servo Noktaları

`servo1` / `servo2` / `servo3` literal dizeleri kod tabanında **hiç geçmiyor**.
Eşdeğerleri yorum işaretleriyle adlandırılmış ve **dört tane**:

| İşaret | Metot | GZ (`gz_payload_actuator.py`) | Gerçek (`real_payload_actuator.py`) |
|---|---|---|---|
| `# FIRST MISSION SERVO` | `release_payload_at_mavi_altigen()` | :552 — gerçek DetachableJoint | **:19** — no-op |
| `# SECOND MISSION SERVO` | `release_payload_at_kirmizi_ucgen()` | :557 — gerçek DetachableJoint | **:31** — no-op |
| `# THIRD MISSION SERVO` | `activate_pickup_mechanism()` | :1249 — magnet+servo simülasyonu | **:40** — no-op |
| `# GRAB SERVO` | `activate_drop_mechanism()` | :1328 — kanca açma | **:49** — no-op |

### 3.1 Şu anki durum — gerçekten no-op mu?

Evet, dördü de. Her biri birebir aynı gövdeye sahip:
```python
# <İŞARET>
# TODO[DONANIM]: Gerçek servo entegrasyonu
await asyncio.sleep(0.5)
logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
return True
```

Olumlu yanlar: (a) `real_payload_actuator.py`'nin dosya başlığı bunun
**projede donanım komutunun yazılacağı tek yer** olduğunu açıkça söylüyor,
(b) her çağrıda `WARNING` seviyesinde "gercek servo BAGLI DEGIL" logu var —
sessizce başarılı görünmüyor, (c) `IPayloadActuator` docstring'i sözleşmeyi
belgeliyor.

### 3.2 B8 — Açıklık yeterli mi? Hayır, 1/4

Manuel açı/süre ayarı için gereken bilgi **yalnızca ilk noktada** yazılı:

**`release_payload_at_mavi_altigen` (:19-23) — YETERLİ:**
- Beklenen davranış: *"servo 90° sağa, ardından 90° sola (Görev 2 Rapor Bölüm 12)"*
- Önerilen kütüphane: *pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control)*
- Bağlantı noktası: *real_system.yaml içinde tanımlanacak*

**Diğer üçü (:31, :40, :49) — EKSİK.** Yalnızca tek satır
`# TODO[DONANIM]: Gerçek servo entegrasyonu` var. Yok olanlar:
- Beklenen açı yok (90°? kaç derece? hangi yöne?)
- Beklenen süre yok — `asyncio.sleep(0.5)` bir **yer tutucu**, ilk noktada
  *"simüle gecikme, gerçek servo süresiyle değiştirilecek"* diye işaretli,
  diğer üçünde bu not bile yok
- Kütüphane/kanal önerisi tekrarlanmamış
- Görev 3 için kanca mekaniği (kilitleme/açma sırası) hiç anlatılmamış —
  oysa GZ tarafında `gz_payload_actuator.py:1245` *"kanca icindeki servo
  donup kilitleyecek"* diye bir davranış tarif ediyor

**Ek eksik:** `real_system.yaml:14` → `pickup_channel: null` — tek bir kanal
alanı var, ama dört servo noktası var. Dört ayrı çıkış kullanılacaksa
konfigürasyon şeması eksik.

---

## 4. Climb-then-Cruise'un Gerçek Çalışma Hattındaki Durumu

### 4.1 Tek adopter doğrulandı

`goto_waypoint()` üretimde **tek yerden** çağrılıyor:
`core/mission/gorev2_fsm.py:73` (`PayloadMissionSequencer._navigate_to_recorded`).
Görev 2'nin **iki payload bacağı da** buradan geçiyor. Görev 3 fazları,
dönüş bacağı ve rota yeniden katılım hâlâ `goto_global_position_and_wait()`
kullanıyor.

### 4.2 Bayrak her iki yolda da etkili — ama sonuçları farklı

`centering.motion_profile = MotionProfile.from_config(config.get("motion_profile"))`
üç entrypoint'te de mevcut:

| Entrypoint | Satır | Profil kaynağı | `enabled` |
|---|---|---|---|
| `gz_system/main_gz.py` | 138 | `gz_system.yaml` | **`true`** |
| `real_system/main_real.py` | 96 | `real_system.yaml` | **`false`** |
| `dual_system/main_dual.py` | 113 | `real_system.yaml` (gerçek öncelikli) | **`false`** |

`goto_waypoint()` `enabled: false` iken aynen
`goto_global_position_and_wait()`'e düşüyor (`centering_controller.py`).

**Cevap:** State machine **kod olarak** her iki yolda da devrede — izole bir
yolda kalmış değil. Ama **davranış olarak** yalnızca GZ'de çalışıyor; gerçek
uçuşta 2026-09-02'de bilinçli olarak kapatılan kalibrasyon kapısı yüzünden
eski yola düşüyor. Bu kasıtlıdır ve `real_system.yaml`'da gerekçesiyle
belgelidir (eşikler kalibre edilmeden açılırsa state makinesi ilerlemez).

> Uyarı: B1 (VisionRuntime eksikliği) yüzünden gerçek uçuşta Görev 2 zaten
> hedef bulamayacağı için `_navigate_to_recorded`'a hiç ulaşılamaz. Yani
> kalibrasyon kapısı açılsa bile bu bacak gerçek uçuşta bugün çalışmaz.

### 4.3 Mevcut HOLD konfigürasyonu

| Profil | `hold_min_s` | `hold_max_s` | `arrival_hold_s` | `attitude_rate_limit_deg_s` | `attitude_stable_samples` |
|---|---|---|---|---|---|
| SITL (`gz_system.yaml`) | **0.30** | 3.0 | 1.0 | 15.0 | 3 |
| Gerçek (`real_system.yaml`) | **0.50** | 5.0 | 1.0 | 25.0 | 3 |
| `parameters.py` varsayılan | 0.30 | 3.0 | 1.0 | 15.0 | 3 |

Mevcut davranış: **min süre + attitude durgunluk guard'ı**. `hold_min_s`
dolduktan sonra çıkış, roll/pitch türevinin eşik altında ardışık N örnek
kalmasına bağlı; attitude okunamazsa sayaca düşer; `hold_max_s` emniyet tavanı.

**NOT (karar sonraki fazda):** Kullanıcı yeni talimatında **sabit ~2 s hold**
yeterli diyor. Bu, mevcut tasarımdan iki yönde farklı:
1. Süre: 0.30/0.50 s → ~2.0 s (**~4-6 kat artış**)
2. Mekanizma: guard'lı → sabit (attitude stabilite koşulu kaldırılır mı,
   yoksa 2 s taban + guard olarak mı kalır?)

Bütçe etkisi hesaplanmalı: Görev 2'de iki payload bacağı × (HOLD +
ARRIVAL_HOLD). Sabit 2 s HOLD + 1 s ARRIVAL_HOLD = bacak başına 3 s, iki
bacakta 6 s. 600 s'lik zorunlu bütçenin **%1'i** — kabul edilebilir görünüyor,
ama karar verilmeden `MOTION_HOLD_MIN_S` değiştirilmemeli. Kümülatif hold
zaten `MOTION_HOLD_SETTLED` olayında `cumulative_hold_pct_of_budget` ile
izleniyor.

---

## 5. README.md ve SETUP.md'nin Mevcut Durumu

`SETUP.md` ve `setup.md` **aynı dosyadır** (aynı inode: 6636994 — dosya
sistemi büyük/küçük harf duyarsız). Tek dosya, 600 satır.

### 5.1 B7 — Her iki doküman da v32 dönemine ait

| Dosya | Satır | `v32` atfı | `v34` atfı |
|---|---|---|---|
| README.md | 151 | **8** | **0** |
| SETUP.md | 600 | **55** | **0** |

README'nin hızlı çalıştırma bölümü hâlâ
`.scripts/olds/v32/run_mission_v32_gz.sh` gösteriyor. SETUP.md'nin tüm dosya
bağlantıları `v32_flight_stack/` altına işaret ediyor (örn. §7.3 →
`.scripts/olds/v32/v32_flight_stack/real_system/config/real_system.yaml#L14`).

### 5.2 Başlık başlık ne var / ne yok

**Climb-then-Cruise:** Her iki dosyada da **hiç geçmiyor**. `climb`, `cruise`,
`motion_profile`, `goto_waypoint`, `MotionStateMachine` — sıfır eşleşme.
Kalibrasyon kapısı (`enabled: false`) ve hover ölçüm protokolü de yok;
bunlar yalnızca `docs/climb-then-cruise-hw-checklist.md`'de.

**Dashboard:** Kısmen var ama eksik/eskimiş:
- SETUP.md §13.7 macOS Cocoa ana-thread kısıtını doğru anlatıyor, ama
  yalnızca `main_gz.py` için — B3'teki `main_real.py` boşluğundan haberi yok
- ADR-005/ADR-006 tabloda listelenmiş (satır 375-376)
- v34'ün **iki dashboard mekanizması** (ayrı process unified vs in-process
  legacy, `legacy_dashboard_default`) hiç anlatılmamış
- `run_mission_v34_gz.sh`'ın unified dashboard'u başlattığı, `run_mission_v34_real.sh`'ın
  başlatmadığı yazmıyor

**Servo noktaları:** Kısmen var:
- README satır 14 "servo AUX" diye geçiyor (tek cümle)
- SETUP.md §7.3 "Servo / AUX kanalı" bölümü var ve `null` bırakılırsa payload
  bırakmanın çalışmayacağını söylüyor — ama **v32 yoluna** işaret ediyor
- SETUP.md §464 tablosunda `R3 | Servo/AUX kanalı | ... | null TODO` satırı var
- **Dört servo noktasının ayrı ayrı listesi, açı/süre beklentileri ve
  `real_payload_actuator.py`'nin "tek yer" rolü hiçbir dokümanda yok**

---

## 6. Önerilen Sıra (implementasyon için — onay bekliyor)

1. **B1** — `main_real.py`'ye `VisionRuntime` kur ve `main_gz` ile aynı
   yaşam döngüsüne bağla. Bu olmadan gerçek uçuş kör.
2. **B2** — `RealPayloadActuator.activate_pickup_mechanism` imzasını arayüze
   uydur.
3. **B3 + B4** — macOS ana-thread boyama pompası ve sinyal işleyicileri:
   `main_gz`'deki `_run_with_main_thread_gui` ve `_install_signal_handlers`
   ortak bir modüle çıkarılıp iki entrypoint tarafından paylaşılabilir
   (kod tekrarı yaratmadan).
4. **B5 + B6** — `Gorev3PickupPhase`'e gerçek yolda `FeedDetector` ve
   `publisher` geçir.
5. **B8** — Dört servo noktasının açı/süre yorumlarını ilk noktadaki
   ayrıntı seviyesine getir; `real_system.yaml`'daki kanal şemasını dört
   noktayı karşılayacak şekilde genişlet.
6. **HOLD kararı** — sabit ~2 s mi, 2 s taban + guard mı (§4.3).
7. **B7** — README.md ve SETUP.md'yi v34'e taşı.

> 1-4 arası maddeler **gerçek donanım denemesinden önce** kapatılmalıdır;
> hiçbiri simülasyonda görünmez çünkü hepsi yalnızca `real_system` yolunda.

---

## 7. Uygulama Sonrası Durum (2026-09-02, FAZ 3B)

§0'daki bulguların tamamı kapatıldı: **B1** (`VisionRuntime` üç entrypoint'te),
**B2** (aktüatör imzası), **B3** (macOS boyama pompası), **B4** (sinyal
işleyicileri), **B5/B6** (`publisher` + `FeedDetector`), **B7** (README/SETUP
v34'e taşındı), **B8** (dört servo noktası + dört kanal).

Doğrulama: 469 birim testi (73'ü yeni) · canlı SITL entegrasyon testi ·
`main_gz` görev regresyonu · `main_real` vision duman testi (§9.2, SETUP.md).

### 7.1 Bilinen borç — kapatılmadı

| # | Borç | Etki | Neden bekliyor |
|---|---|---|---|
| **D1** | `main_gz.py` `main()`'in **Linux/Windows dalı** `asyncio.run(_run(...))` diyor ve **hiçbir sinyal işleyicisi kurmuyor** — o platformda `kill -INT` B4'ün tarif ettiği şekilde yutulabilir ve araç havada kalabilir. macOS dalı (`_run_with_main_thread_gui` → ortak pompa) ve `main_real`/`main_dual`'in Linux dalı (`_run_with_shutdown`) bu boşluğu **taşımıyor**. | Yalnızca GZ + Linux/Windows | Ekip macOS'ta çalışıyor; düşük öncelik. Kapatması tek sarmalayıcı (`main_real.py`'deki `_run_with_shutdown` deseninin aynısı). |

> D1 kodda da işaretli: `gz_system/main_gz.py:206-211`.
