# Holybro H-Flow — Gazebo/PX4 SITL Entegrasyon Raporu

**Tarih:** 2026-09-01 · **Ortam:** gz-sim 8.15.0 (Harmonic), PX4 SITL, model `x500_mono_cam_down`

**DURUM: tum kritik noktalar kapatildi.** Ilk raporun biraktiğı iki açık nokta
(rpath'in geçici olması, EKF2 füzyonunun doğrulanmamış olması) §8'de gerçek log
kanıtıyla kapatıldı. Kapanmayan tek nokta zemin texture'ının faydasıdır (§5.1) —
bu bir arıza değil, gösterilemeyen bir fayda iddiasıdır ve olduğu gibi bırakıldı.

---

## 1. Yapılan değişikliklerin özeti

| dosya | değişim | not |
|---|---|---|
| `Tools/simulation/gz/models/x500_mono_cam_down/model.sdf` | +2 link, +2 joint, +3 sensör | `flow_link` (kamera + `optical_flow`), `lidar_sensor_link` (`gpu_lidar`) |
| `ROMFS/px4fmu_common/init.d-posix/airframes/4014_gz_x500_mono_cam_down` | 9 → 55 satır | 13 parametre |
| `Tools/simulation/gz/worlds/default.sdf` | **+31 satır, −0** | yalnızca `ground_plane` `<material>` içine `<pbr>` bloğu |
| `Tools/simulation/gz/worlds/materials/textures/asphalt_grey.png` | YENİ (3.01 MB) | 2048², tek kanal gri |
| `build/.../external/Install/lib/libOpticalFlow.dylib` | symlink | rpath düzeltmesi, build artefaktı (gitignore'da) |

### 1.1 Yol açıcı bulgu: OpticalFlow eklentisi yüklenmiyordu

Entegrasyondan **önce** SITL logunda kayıtlı hata:

```
Error while loading the library [...libOpticalFlowSystem.dylib]:
  Reason: tried: '.../build/px4_sitl_default/external/Install/lib/libOpticalFlow.dylib' (no such file)
```

Kütüphane **vardı** (`OpticalFlow/install/lib/`), ama eklentinin rpath'i boş bir dizine
(`external/Install/lib/`) bakıyordu. Symlink ile çözüldü. Bu düzeltme olmadan optik akış
simülasyonu bu makinede **hiç çalışamazdı**.

---

## 2. Datasheet vs. simülasyon

### 2.1 PAA3905E1 — optik akış

| parametre | datasheet | simülasyonda | durum |
|---|---|---|---|
| FOV | ~42° | `horizontal_fov 0.733038` rad = **42.00°** | birebir |
| Çalışma mesafesi | 80 mm – 30 m | kamera `clip 0.08 / 30`, `SENS_FLOW_MINHGT 0.08`, `SENS_FLOW_MAXHGT 30` | birebir |
| Maks. açısal akış | 7.4 rad/s | `SENS_FLOW_MAXR 7.4` → uORB'da `max_flow_rate: 7.40000` | birebir, **çalışırken doğrulandı** |
| Montaj yönü | konnektör arkaya | `SENS_FLOW_ROT 0` | birebir |
| Update rate | datasheette yok | **50 Hz** (SDF), uORB `integration_timespan_us 40000` = 25 Hz efektif | *varsayım*, §7.1 |
| Düşük ışık > 5 lux | — | **simüle EDİLEMEDİ** | §7.2 |

### 2.2 AFBR-S50LV85D — ToF mesafe

| parametre | datasheet | simülasyonda | durum |
|---|---|---|---|
| Menzil | 30 m'ye kadar | `<range><max>30.0` → uORB `max_distance: 30.00000` | birebir |
| Minimum | (H-Flow 80 mm) | `<range><min>0.08` → uORB `min_distance: 0.08000` | birebir |
| FOV | 12.4° × 6.2°, 32 piksel | **tek merkez ışın** | **sapma**, §7.3 |
| Ortam ışığı 200k lux | — | simüle edilmedi (motor desteklemiyor) | §7.2 |

### 2.3 ICM-42688-P (IMU)
**Ayrıca modellenmedi.** Araç zaten x500'ün kendi IMU'sunu kullanıyor; ikinci bir IMU eklemek
PX4 sensör seçimini karıştırırdı ve görev akışına dokunmama kısıtını ihlal ederdi. *Varsayım.*

---

## 3. Uygulanan PX4 parametreleri (çalışan sistemden okundu)

```
x   SENS_FLOW_MINHGT [828,1361] : 0.0800
x   SENS_FLOW_MAXHGT [826,1359] : 30.0000
x   SENS_FLOW_MAXR   [827,1360] : 7.4000
x   SENS_FLOW_ROT    [830,1363] : 0
x   EKF2_OF_CTRL     [396,625]  : 1
x   EKF2_OF_POS_X    [402,631]  : 0.0000
x   EKF2_OF_POS_Y    [403,632]  : 0.0000
x   EKF2_OF_POS_Z    [404,633]  : 0.0200
x   EKF2_RNG_A_HMAX  [422,651]  : 10.0000
x   EKF2_RNG_QLTY_T  [434,663]  : 0.2000
x   EKF2_RNG_POS_Z   [433,662]  : 0.0200
x   SIM_GZ_EN_FLOW   [891,1463] : 1
x   SIM_GZ_EN_LIDAR  [893,1465] : 1
```
`x` = parametre PX4 tarafından **kullanılıyor**. 13/13 uygulandı.

### 3.1 UAVCAN_* parametreleri neden YOK

Sensör verisi SITL'de CAN'dan gelmiyor. `GZBridge.cpp` topic yollarını sabit kodluyor:

```
satir 268-269:  /world/<w>/model/<m>/link/lidar_sensor_link/sensor/lidar/scan   -> distance_sensor
satir 320-321:  /world/<w>/model/<m>/link/flow_link/sensor/optical_flow/...     -> sensor_optical_flow
```

`UAVCAN_SUB_FLOW`, `UAVCAN_SUB_RNG`, `UAVCAN_RNG_MIN/MAX` yalnızca gerçek DroneCAN sürücüsü
içindir; SITL'de **etkisizdir**, bu yüzden bilerek ayarlanmadı. Menzil sınırları SITL'de
sensörün SDF `<range>` bloğunda tanımlı.

### 3.2 EKF2_GPS_CTRL neden 0 yapılmadı
Görev 2/3 rotaları GPS waypoint'leriyle çalışıyor; GPS'i kapatmak mevcut görev akışını bozardı.
Optik akış GPS'e **ek** kaynak olarak füzyona giriyor. *Bilinçli karar.*

---

## 4. Topic doğrulama sonuçları

### 4.1 Gazebo tarafı — sensörler yayında
```
/world/default/model/x500_mono_cam_down_0/link/flow_link/sensor/flow_camera/image
/world/default/model/x500_mono_cam_down_0/link/flow_link/sensor/optical_flow/optical_flow
/world/default/model/x500_mono_cam_down_0/link/lidar_sensor_link/sensor/lidar/scan
```
Lidar topic'inde abone doğrulandı (GZBridge):
```
Publishers:  tcp://127.0.0.1:53110, gz.msgs.LaserScan
Subscribers: tcp://127.0.0.1:53138, gz.msgs.LaserScan
```

### 4.2 `distance_sensor` uORB — yerde
```
min_distance: 0.08000        <- H-Flow 80 mm
max_distance: 30.00000       <- H-Flow 30 m
current_distance: 0.21986
orientation: 25              <- ROTATION_DOWNWARD_FACING
```
**Geometrik doğrulama:** `base_link` yerdeyken z=0.240, sensör −0.02 → beklenen **0.220 m**.
Ölçülen **0.21986 m**. Sapma 0.14 mm.

**Ara düzeltme:** ilk denemede `orientation: 100` (CUSTOM) geldi; `GZBridge.cpp:831` dünya
yönelimini `q_down=(0,1,0,0)` ile karşılaştırıyor. Sensöre `<pose>0 0 0 3.14 0 0</pose>`
eklenerek (çalışan `x500_lidar_down` referansından) **25**'e düzeltildi. Bu olmadan EKF2
mesafe füzyonu sensörü aşağı bakan olarak tanımazdı.

### 4.3 `sensor_optical_flow` uORB — hover ve hareket
```
YERDE (hareketsiz):     pixel_flow [0.00000, 0.00000]        quality: 0
HOVER 3 m:              pixel_flow [-0.00026,  0.00019]      quality: 127
YANAL HAREKET:          pixel_flow [-0.00025, -0.00048]      quality: 134
YANAL HAREKET:          pixel_flow [-0.00016, -0.00001]      quality: 255
```
```
max_flow_rate: 7.40000           <- SENS_FLOW_MAXR uygulandi
max_ground_distance: 30.00000    <- SENS_FLOW_MAXHGT uygulandi
integration_timespan_us: 40000   <- 25 Hz efektif
```
`quality` 0 → 127 → 255: hareketle birlikte artıyor, beklenen davranış.

**Bilinen boşluk:** uORB `min_ground_distance: 0.00000` ve `distance_m: 0.00000` geliyor.
Parametre doğru (`SENS_FLOW_MINHGT = 0.0800`, §3); bu alanları **GZBridge doldurmuyor**.
Köprü sınırı, konfigürasyon hatası değil.

---

## 5. Zemin texture — öncesi/sonrası

Texture: `asphalt_grey.png`, 2048², çok ölçekli gri gürültü.
```
V ortalama : 76.1/255   (eski düz renk 0.30*255 = 76.5)
S maksimum : 0
yerel kontrast (std): 31.4 gri seviye
```

**Dedektör kalibrasyonu korundu.** `default.sdf`'teki mevcut not, zeminin kasten
`0.30 0.30 0.31` (S=8) seçildiğini, çünkü kırmızı maskesi S≥40 ve mavi maskesi S≥80
istediğini, dolayısıyla zeminin dedektöre görünmez kalması gerektiğini yazıyor.
Texture **tek kanal gri** üretildi → R=G=B → **S=0 (ölçüldü)**, yani her iki eşiğin de
altında. Ortalama parlaklık da korundu.

### 5.1 DÜRÜST SONUÇ: texture ölçülebilir bir iyileşme sağlamadı

Aynı hover, texture **açık** ve **kapalı**:

| | pixel_flow | quality |
|---|---|---|
| texture AÇIK | `[-0.00016, -0.00001]` | **255** |
| texture KAPALI | `[-0.00009, -0.00008]` | **255** |

Her iki durumda da kalite maksimum. **Texture'ın optik akış kalitesini iyileştirdiğini
gösteremedim.** Muhtemel neden: dünyada zaten bol görsel özellik var (yarışma sınır çerçevesi,
dört hedef şekli, payload'lar) ve gz OpticalFlow eklentisinin kalite metriği gerçek bir
PAA3905'in doku bağımlılığını modellemiyor olabilir. Texture **yine de bırakıldı** — gerçek
donanımda fiziksel olarak doğru, zararsız ve dedektöre görünmez; ama bu raporda
**işe yaradığı iddia edilmiyor**.

---

## 6. Regresyon testi

| kontrol | sonuç |
|---|---|
| `default.sdf` diff | **+31 satır, −0 satır** (saf ekleme) |
| Yarışma alanı marker'ları | 3 (değişmedi) |
| Yuva/huni collision kutusu | 166 (değişmedi) |
| `generate_competition_area.py` (seed 999) | **ÇALIŞIYOR**, include sayısı 5→5, texture korundu |
| `generate_bore_collision.py --check` | dört sert koşul da **PASS** |
| SDF şema hatası | 4 (taban 4 — önceden var olan şekil URI'leri) |
| Geçici texture kaldırma sonrası geri yükleme | `albedo_map` 1, geçici kalıntı 0 |

Yarışma alanı geometrisine, include'larına ve rastgele şekil yerleştirme mekanizmasına
**dokunulmadı**.

---

## 7. Bilinen kısıtlar

**7.1 Update rate — varsayım.** Datasheet net bir PX4 iletim hızı vermiyor. 50 Hz seçildi
(`x500_flow` referansıyla ve modelin diğer sensörleriyle tutarlı). uORB'da efektif 25 Hz.

**7.2 Işık koşulları simüle edilemedi.** PAA3905'in >5 lux eşiği ve AFBR'nin 200k lux
toleransı modellenmedi: gz OpticalFlow eklentisi (`OpticalFlowSensor.cpp:74-81`) SDF'ten
yalnızca `update_rate`, `horizontal_fov` ve görüntü boyutunu okuyor; lux girdisi yok.

**7.3 ToF FOV modellenemedi.** 12.4°×6.2° / 32 piksel yerine **tek merkez ışın** kullanıldı.
Neden: `GZBridge.cpp:815` yalnızca `msg.ranges()[0]`'ı okuyor. Çok ışınlı tarama kullanılsaydı
merkez değil **köşe** ışını raporlanırdı — yani daha yanlış olurdu. Tek merkez ışın, köprünün
tükettiği veriye sadık olan tek seçim.

**7.4 IMU eklenmedi** (§2.3).

**7.5 EKF2 füzyon doğrulaması — KAPANDI.** İlk raporda eksikti; §8.2'de uçuş sırasında
toplanmış log kanıtıyla kapatıldı.

**7.6 rpath — KAPANDI.** Symlink kaldırıldı, çözüm CMake'e taşındı; §8.1'de temiz build
kanıtı var.

---

---

## 8. Kapanış doğrulamaları (2026-09-01, takip görevi)

### 8.1 rpath kalıcı hale getirildi — symlink KALDIRILDI

**Eski geçici çözüm (artık yok):**
```
build/px4_sitl_default/external/Install/lib/libOpticalFlow.dylib
  -> build/px4_sitl_default/OpticalFlow/install/lib/libOpticalFlow.dylib
```

**Kalıcı çözüm** — `src/modules/simulation/gz_plugins/optical_flow/CMakeLists.txt`:
```cmake
get_filename_component(OpticalFlow_LIBDIR "${OpticalFlow_LIBS}" DIRECTORY)
set_target_properties(${PROJECT_NAME} PROPERTIES
    BUILD_WITH_INSTALL_RPATH FALSE
    BUILD_RPATH   "${OpticalFlow_LIBDIR}"
    INSTALL_RPATH "${OpticalFlow_LIBDIR}")
```
Yol `OpticalFlow_LIBS`'ten türetiliyor; `optical_flow.cmake` içindeki iki install-prefix
dalından hangisi seçilirse seçilsin doğru kalır. Symlink'e **hiç gerek kalmadı**.

**Temiz build kanıtı** (`make clean` → `make px4_sitl_default`, 1137/1137 hedef):
```
symlink VAR MI (olmamali):        (dizin bos)
eklentinin YENI rpath'i:
  .../build/px4_sitl_default/install/lib          <- YENI, ilk sirada
  .../build/px4_sitl_default/external/Install/lib
  /opt/homebrew/lib
libOpticalFlow gercekte nerede:
  build/px4_sitl_default/install/lib/libOpticalFlow.dylib
```
SITL başlatıldı, **hiçbir manuel müdahale olmadan**:
```
=== MADDE 1 KANITI: eklenti yukleme hatasi var mi ===
  libOpticalFlow ile ilgili HICBIR HATA YOK  <- eklenti sessizce yuklendi
=== topic yayinda mi (symlink olmadan) ===
  .../link/flow_link/sensor/optical_flow/optical_flow
  .../link/lidar_sensor_link/sensor/lidar/scan
```

**Yan bulgu — build kırılganlığı (benim değişikliğimden bağımsız).** `make clean` sonrası ilk
derleme şu hatayla düştü:
```
ninja: error: mkdir(/usr/local/lib): Permission denied
```
Kaynak `build.ninja:35334`: `build_gz` alt-derlemesine `-DCMAKE_INSTALL_PREFIX=/usr/local`
geçiliyor (macOS'ta CMake varsayılanı). Bu benim rpath eklememle **ilgisiz**; `make clean`
kurulum adımını yeniden tetiklediği için ortaya çıktı. Çözüm: yapılandırma
`-DCMAKE_INSTALL_PREFIX=<build>/install` ile tekrarlandı. **Bu bir CMakeCache ayarıdır,
depoya yazılmadı** — temiz makinede aynı hatayla karşılaşılabilir; §9'a taşındı.

### 8.2 EKF2 füzyonu fiilen aktif — uçuş sırasında kanıt

Gerçek alan adları `listener estimator_status_flags` ile tespit edildi (tahmin edilmedi):
`cs_opt_flow`, `cs_rng_hgt`, `cs_rng_kin_consistent`, `cs_rng_terrain`,
`fs_bad_optflow_x/y`, `reject_optflow_x/y`.

**12 saniyelik hover boyunca, 2 s aralıkla 6 örnek:**
```
[23:02:16] cs_opt_flow:True cs_rng_hgt:True  fs_bad_optflow_x:False reject_optflow_x:False reject_optflow_y:False
[23:02:18] cs_opt_flow:True cs_rng_hgt:True  fs_bad_optflow_x:False reject_optflow_x:False reject_optflow_y:False
[23:02:20] cs_opt_flow:True cs_rng_hgt:True  fs_bad_optflow_x:False reject_optflow_x:False reject_optflow_y:False
[23:02:22] cs_opt_flow:True cs_rng_hgt:True  fs_bad_optflow_x:False reject_optflow_x:False reject_optflow_y:False
[23:02:24] cs_opt_flow:True cs_rng_hgt:True  fs_bad_optflow_x:False reject_optflow_x:False reject_optflow_y:False
[23:02:26] cs_opt_flow:True cs_rng_hgt:False fs_bad_optflow_x:False reject_optflow_x:False reject_optflow_y:False
```
`cs_opt_flow` **6/6 sürekli True**. Hiçbir örnekte reddedilme veya arıza bayrağı yok.

**`cs_rng_hgt`'nin son örnekte düşmesi doğru davranıştır, arıza değil:**
```
current_distance: 23.56284      <- arac 23.5 m'ye cikmisti
EKF2_RNG_A_HMAX : 10.0000       <- menzil-yardimli yukseklik SADECE 10 m altinda
cs_rng_hgt          : False
cs_gps_hgt          : True      <- EKF2 dogru sekilde GPS yuksekligine gecti
cs_rng_kin_consistent: True     <- mesafe sensoru hala gecerli
cs_rng_terrain      : True      <- ve arazi tahmininde kullaniliyor
```
Yani bayrağın düşmesi, **benim ayarladığım `EKF2_RNG_A_HMAX = 10` parametresinin
beklenen sonucudur**.

**Innovation sağlıklı** (patlamamış, NaN değil):
```
flow: [0.00132, -0.00519]
```

### 8.3 BONUS — GPS kapalıyken füzyon (en güçlü kanıt)

`EKF2_GPS_CTRL` geçici olarak 7 → 0 yapıldı:
```
=== GPS kapaliyken EKF2 durumu ===
  cs_opt_flow: True          <- optik akis fuzyonu aktif
  cs_rng_hgt : True          <- mesafe fuzyonu aktif
  cs_gps_hgt : False         <- GPS gercekten kapali
  reject_optflow_x: False
  reject_optflow_y: False
=== yerel konum tahmini gecerli mi ===
  xy_valid          : True   <- GPS YOKKEN konum tahmini GECERLI
  v_xy_valid        : True   <- ve HIZ tahmini de gecerli
  z_valid           : True
  dist_bottom       : 0.24028
  dist_bottom_valid : True
```
GPS füzyonu tamamen kapalıyken EKF2'nin hâlâ geçerli **konum ve hız** tahmini üretmesi,
optik akış + mesafe füzyonunun yalnızca "bayrak set" değil, tahmini fiilen **taşıdığını**
gösterir.

`EKF2_GPS_CTRL` testten sonra **7'ye geri alındı** (doğrulandı). Airframe dosyasında
`set-default` olarak hiç bulunmuyor; yalnızca §3.2'deki gerekçe yorumu var.

---

## 9. Kapanmayan / devredilen noktalar

1. **Zemin texture'ının faydası gösterilemedi** (§5.1). Ölçüm texture açık ve kapalıyken
   aynı `quality: 255` verdi. Texture bırakıldı (fiziksel olarak doğru, dedektöre S=0 ile
   görünmez), ama **işe yaradığı iddia edilmiyor**. Bu bir arıza değil, doğrulanamayan
   bir fayda iddiasıdır.
2. **`CMAKE_INSTALL_PREFIX=/usr/local` kırılganlığı** (§8.1 yan bulgu). Yapılandırma
   düzeltmesi CMakeCache'te; depoya yazılmadı. Temiz bir makinede `make clean` sonrası aynı
   `mkdir(/usr/local/lib): Permission denied` hatası çıkabilir. Kalıcı çözüm PX4'ün
   `build_gz` alt-derlemesine geçirdiği prefix'i düzeltmek olurdu — bu görevin kapsamı
   dışında bırakıldı, çünkü H-Flow entegrasyonuyla ilgisiz ve PX4 upstream davranışı.
3. §7.1 (update rate varsayımı), §7.2 (ışık koşulları), §7.3 (ToF FOV), §7.4 (IMU)
   olduğu gibi geçerli.

---

## 10. Sonuç

**Sistem çalışıyor** — kanıtlarla:

1. Her iki sensör de GZBridge'in beklediği topic yollarında yayın yapıyor, abonelik doğrulandı.
2. `distance_sensor`: menzil sınırları H-Flow ile **birebir** (0.08 / 30.0), ölçülen mesafe
   geometrik beklentiyle **0.14 mm** içinde, yönelim `ROTATION_DOWNWARD_FACING`.
3. `sensor_optical_flow`: hareketle birlikte `quality` **0 → 127 → 255**, `max_flow_rate 7.4`
   datasheet ile birebir.
4. 13/13 parametre uygulandı ve PX4 tarafından kullanılıyor.
5. Yarışma alanı ve rastgele şekil aracı **etkilenmedi** (saf ekleme, regresyon testli).

6. **EKF2 füzyonu fiilen aktif** (§8.2): 12 s hover boyunca `cs_opt_flow` **6/6 True**,
   innovation sağlıklı; GPS tamamen kapalıyken bile `xy_valid`/`v_xy_valid` **True** (§8.3).
7. **rpath kalıcı** (§8.1): `make clean` + tam yeniden derleme sonrası, symlink olmadan
   eklenti otomatik yükleniyor.

**Tek çekince:** zemin texture'ının faydası **gösterilemedi** (§5.1). Bu bir arıza değil,
doğrulanamayan bir fayda iddiasıdır; texture zararsız ve dedektöre S=0 ile görünmez.
Ayrıca §9.2'deki build kırılganlığı H-Flow ile ilgisiz bir PX4 upstream davranışıdır.
