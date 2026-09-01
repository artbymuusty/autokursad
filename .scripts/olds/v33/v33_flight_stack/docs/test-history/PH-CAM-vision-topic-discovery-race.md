---
phase_id: PH-CAM
date: 2026-08-25
title: Kamera akışı yok — tek atışlık topic keşfi yarışı
commit: ~
status: fixed
metrics:
  vision_down_esigi_s: 0.3
  kamera_topic_yayina_girme_s: "6.3-9.4 (3/3 koşu)"
  ilk_kare_s: 12.0
  yayin_hizi_fps: "27.3-29.7"
  vision_down_sayisi_duzeltme_sonrasi: 0
raw_artifacts:
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/cam_diag_sitl*.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/verify*_sitl.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/verify_cam.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/verify2_mission.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/verify3_justcam.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/cam_timing*.log"
---

# PH-CAM — Kamera akışı yok: tek atışlık topic keşfi yarışı

## Amaç

`run_just_cam` ve tam mission'da kamera görüntüsünün akmaması. Dashboard
HEALTH paneli `Gorev2Orchestrator.vision: DOWN` / `MavsdkBackendBase: HEALTHY`
gösteriyordu — yani arıza uçuş/MAVSDK tarafında değil, vision zincirindeydi.

## Değişiklikler

`gz_system/camera_service.py` (+147/−27): keşif bekleyen döngüye çevrildi,
kare-açlık dedektörü eklendi, topic çözümü watchdog döngüsünün içine alındı.
`payload/` ve world/SDF dosyalarına **dokunulmadı**.

## Test sonucu

Düzeltme sonrası, yarış kasten tetiklenerek (kamera servisi sim ile aynı anda
başlatılarak): servis boş pencerede başladı, bekledi, 5. denemede topic'i
buldu, 27–30 FPS'e ulaştı. Mission koşusunda `Gorev2Orchestrator.vision`
UNKNOWN → **HEALTHY**, DOWN sayısı **0**.

## Başarısızlıklar

Düzeltme öncesi: `camera_service` "Service is running." yazıp sonsuza kadar
sıfır kare üretiyordu. Sessizdi, çünkü hiçbir hata yolu tetiklenmiyordu.

## Kök neden

**İki kusur birlikte sessiz kalıcı arıza üretiyordu:**

1. `resolve_camera_topic()` **tek atışlıktı**. Kamera sensörü topic'i sim
   ayağa kalktıktan 6.3–9.4 s SONRA advertise ediliyor (ölçüldü, 3/3 koşu).
   O pencerede çağrılırsa liste boş/eksik döner, fonksiyon yapılandırılmış
   topic'e geri düşer ve **bir daha asla denemez**. `timeout_s=10.0` bir
   bekleme penceresi değil, subprocess timeout'uydu.
2. gz-transport **var olmayan bir topic'e abone olmaya izin verir** —
   `subscribe()` True döner. Bu yüzden watchdog'un `except RuntimeError`
   dalı hiç tetiklenmiyordu; ayrıca topic çözümü döngünün DIŞINDAYDI ve aynı
   `service` nesnesi (start()'ın finally'si ZMQ socket'ini kapattıktan sonra)
   yeniden kullanılıyordu.

`Gorev2Orchestrator.vision` DOWN eşiği: `VISION_HEARTBEAT_INTERVAL_S` (0.1 s)
× `HEALTH_GRACE_MULTIPLIER` (3.0) = **0.3 s**. `VISION_FRAME_PROCESSED`
yalnızca `get_frame()` başarılı olduğunda yayınlandığı için, kare akmadığında
vision 0.3 s içinde DOWN'a düşüyordu.

### ⚠️ EK BULGU (2026-08-25, PH-RR turunda): bu bir REGRESYONDU

Yukarıdaki iki madde arızayı doğru tarif ediyor ama **eksik**: kod hep böyle
değildi. Legacy V30/V31 stack'i bu sorunu **zaten çözmüştü**.

`.scripts/olds/v33/process_manager.py:107`'deki `verify_gazebo_ready(timeout_s=60.0)`,
`camera_service`'i doğurmadan ÖNCE `gz topic -l`'i 60 saniyeye kadar yokluyor.
Docstring'i buradaki arıza modunu birebir tarif ediyor:

> *"camera_service.py would subscribe successfully (subscribe() returns True
> even if nothing is publishing) and then spin forever with zero frames"*

Yani koruma vardı — ama **çağıran tarafta** yaşıyordu. `gz_system` yeniden
yazımı (`GzCameraSource` → `camera_service_manager` → `camera_service`) bu
kapıyı taşımadı ve `run_just_cam` ile üç mission launcher'ı korumasız kaldı.

**Bunun düzeltmeyi değerlendirmeye etkisi:** bugünkü çözüm korumayı
`camera_service.py`'nin KENDİ İÇİNE koydu (keşif beklemesi + kare-açlık
dedektörü). Bu, legacy'nin çağıran-taraf kapısından daha dayanıklıdır: çağıran
kim olursa olsun koruma taşınır, dolayısıyla bir sonraki yeniden yazımda aynı
şekilde düşürülemez.

**Legacy tarafın bugünkü durumu** (kapsam dışı, DEĞİŞTİRİLMEDİ):
`verify_gazebo_ready()` yalnızca `start_cam`, `start_foreground_cam` ve
`start_mission` tarafından çağrılıyor. `start_camera_test()` — yani
`run_camera_test` launcher'ı — onu **çağırmıyor**; doğrudan `camera_test.py`'yi
çalıştırıyor ve o dosyada keşif hiç yok (`config.DEFAULT_GZ_TOPIC`'e sabit
abonelik, bekleme/yeniden deneme yok). Düzeltilmedi: bir TANI aracı olduğu,
arızasının görünür olduğu (`subscribe() returned: True` + callback yok,
`logs/diagnostic.log`'da okunuyor) ve ADR-005'in düz legacy stack'i
"superseded debris" ilan ettiği için. Operatör notu: Gazebo hazır değilken
`run_camera_test` "abone oldum" der ve sessizce kare üretmez.

## Uygulanan çözüm

Keşif artık topic yayına girene kadar yokluyor (0.25 s aralık, 30 s tavan);
abone olup 15 s kare gelmezse `CameraStarvationError` (RuntimeError türevi)
fırlatılıp watchdog'a topic yeniden çözdürülüyor; çözüm watchdog döngüsünün
içinde ve her turda taze `CameraService` nesnesi kuruluyor.

## Doğrulama

Yarış kasten tetiklenerek üç yoldan da doğrulandı: `GzCameraSource` (ilk kare
+12.0 s, 1280x960, 20/20 kare), tam mission (`vision -> HEALTHY`, DOWN=0,
`MAVI_ALTIGEN` tespit edildi), `run_just_cam`. 14 yeni birim testi
(`gz_system/tests/test_camera_service_discovery.py`).

## Önemli metrikler

- vision DOWN eşiği: **0.3 s**
- kamera topic'i yayına girme: **6.3–9.4 s** (3/3 koşu, ~3 s çözünürlük)
- ilk kare: **+12.0 s** (sim başlangıcından)
- yayın: **27.3–29.7 FPS**, 1280×960
- düzeltme sonrası vision DOWN: **0**

## İlgili commit

Yok — `.scripts/olds/v33/` untracked. Yedek: `camera_service.py.orig`.

## Sonraki adım

`camera_viewer.py::DEFAULT_FIRST_FRAME_TIMEOUT_S = 15.0` ile ölçülen ilk-kare
süresi (12.0 s) arasında yalnızca **3 s marj** var. Soğuk başlangıçta
`run_just_cam` hemen çalıştırılırsa sınıra yaklaşır. Değiştirilmedi (bu
koşuda geçti); operatör kararı.

**v32'de aynı kök neden var** (`camera_service.py` satır 58/95/219/230
birebir aynı) — kapsam dışı, düzeltilmedi.
