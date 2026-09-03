# Görev E4a — Optik akış füzyonu: araştırma, uygulama, doğrulama

**Tarih:** 2026-09-03 · **Değişen tek dosya:**
`ROMFS/px4fmu_common/init.d-posix/airframes/4014_gz_x500_mono_cam_down`
(SITL airframe). **Gerçek param dosyasına dokunulmadı.**

---

## 1. Önkoşul araştırması

### S1 — Gerçek araçta fiziksel optik akış sensörü var mı?

**VAR.** Ve bu ayar bir kaza değil: commit `869f8fa1` (2026-09-01, iki gün
önce) **Holybro H-FLOW (DroneCAN)** modülünün SITL karşılığını kuruyor —
**PAA3905E1** optik akış + **AFBR-S50LV85D** mesafe sensörü. Özenle
yapılmış: model.sdf'e `flow_link`/`lidar_sensor_link` (+120 satır), 13 PX4
parametresi, OpticalFlow eklentisi için kalıcı bir rpath düzeltmesi
(eklenti sessizce yüklenmiyordu), hatta akışa doku versin diye zemine
`asphalt_grey.png` texture'ı.

Yani `EKF2_OF_CTRL 0` **gerçek tarafta no-op değildir** — orada gerçekten
takılı bir sensör var. Bu yüzden bu FAZ'da yalnızca SITL kapatıldı.

Aynı commit'te GPS'siz uçuş için not da var:
> `EKF2_GPS_CTRL 0` (GPS'siz optik akış uçuşu) BİLEREK ayarlanmadı — Görev
> 2/3 rotaları GPS tabanlı waypoint'lerle çalışıyor.

Yani akış **GPS'e EK** bir kaynak olarak düşünülmüş; GPS-denied bir senaryo
için kullanılmıyor. Kapatmanın başka bir yeteneği düşürmediği bu notla da
teyitli.

### S2 — Param setlerinde şu an ne var, fark var mı, kasıtlı mı?

| yer | `EKF2_OF_CTRL` |
|---|---|
| SITL airframe `4014_gz_x500_mono_cam_down` | **1 idi → 0 yapıldı** |
| `real_system.yaml` / `gz_system.yaml` / `dual` | **hiç yok** |
| görev kodu (core/, mavsdk_common/, *_system/) | **hiç PX4 parametresi yazmıyor** |

Yani `EKF2_OF_CTRL` **tek bir yerde**, SITL airframe'inde tanımlı. real/gz
config'leri arasında fark yok çünkü ikisi de bu parametreye hiç dokunmuyor.
Kasıtlı mı? **Evet** — `869f8fa1` commit mesajı 13/13 parametreyi tek tek
gerekçelendiriyor.

**Ama doğrulaması eksikti.** Aynı commit'in kendi doğrulaması:
> 12 s hover, cs_opt_flow 6/6 True, flow innovation [0.00132, −0.00519] (sağlıklı)

Bu **hover'da** yapıldı — hover'da gerçek akış zaten ~0 olduğu için "sıfır
innovation" sağlıklı görünür. Arıza bu testle **görünemezdi**.
Commit ayrıca dürüst bir not da düşmüş:
> DÜRÜST NOT: texture'ın optik akış kalitesini iyileştirdiği GÖSTERİLEMEDİ —
> aynı hover'da texture açık ve kapalı, ikisinde de quality 255.

Yani quality'nin hep 255 olduğu fark edilmiş ama anlamı çözülmemiş.

### S3 — Bağımlılık var mı?

**Yok.**
- Test paketinde optik akışa bağlı **tek bir test yok** (üç "flow" eşleşmesi
  yanlış pozitif: "gate flow", "optical axis", "mission flow").
- Görev kodu **hiçbir PX4 parametresi yazmıyor** → çalışma zamanı bağımlılığı yok.
- `EKF2_RNG_*` (mesafe sensörü/irtifa yardımı) ayrı ve dokunulmadı.

---

## 2. Sensörün gerçekte ne yaptığı — ölçüldü

`quality = 255` sanıldığı gibi "güvenilir" demek değil:
`OpticalFlowSensor.cpp:151` quality'yi `OpticalFlowOpenCV::calcFlow`'dan
alıyor ve orada 255 **"hesap çalıştı"** anlamına geliyor.

Ölçülen akış / geometrik olarak gereken akış (`GT hız / irtifa`), hız > 0.5 m/s:

| irtifa bandı | run4 | run5 |
|---|---|---|
| 0.0–0.8 m | **0.00×** | — |
| 0.8–2.0 m | **0.00×** | — |
| 2.0–5.0 m | 0.02× | 0.01× |
| 5.0–12.0 m | 0.04× | 0.20× |
| 12–40 m | 0.63× | 0.79× |

Ölçülen değer harekete göre **hiç ölçeklenmiyor**; 0.011–0.157 rad/s'lik bir
gürültü tabanında sabit. 12–40 m'de "iyi" görünmesinin sebebi gereken akışın
da orada küçük olması (0.199 rad/s), izleme değil.

**Bu bir parametre hatası değil, simülatör sensör arızasıdır.**

---

## 3. Uygulanan değişiklik

Tek satır + gerekçe bloğu:
```
param set-default EKF2_OF_CTRL 0          # SITL akis sensoru arizali
```
- `SIM_GZ_EN_FLOW 1` **bilerek açık bırakıldı**: `sensor_optical_flow`
  yayını sürüyor, sensör çalışılabilir/düzeltilebilir; yalnızca EKF ona
  **inanmayı** bırakıyor.
- `SENS_FLOW_*` ve `EKF2_OF_POS_*` **korundu** — gerçek modülü belgeliyorlar.
- Dosyaya geri-açma koşulu yazıldı: yukarıdaki oran tablosu tüm bantlarda
  ~1.0× olana kadar 0 kalır.

---

## 4. Doğrulama (canlı SITL, run6)

| ölçüt | run4 (öncesi) | run5 (öncesi en iyi) | **run6 (E4a)** |
|---|---|---|---|
| `EKF2_OF_CTRL` | 1 | 1 | **0** |
| `cs_opt_flow` aktif örnek | çoğunluk | %93.5 | **0 / 292** |
| EKF−gerçek (alt<1.5 m) ortanca | 0.306 m | 0.087 m | **0.027 m** |
| aynı, p95 | 14.216 m | 0.468 m | **0.050 m** |
| aynı, **MAX** | **20.28 m** | 0.53 m | **0.063 m** |
| alt<1.2 m tepe hız | 4.42 m/s | 0.28 m/s | **0.30 m/s** |
| `MOUNT_TRANSLATE` | 55.0 cm SÜRE DOLDU | yakınsadı | **5.0 cm yakınsadı (1.39 s)** |
| **ıska** | **10.19 m** | 0.06 / 0.45 m | **0.341 m** |

**Eğim yanlılığı ölçülemedi — çünkü ölçülecek bir kaçış olmadı.** Düşük
irtifada 0.3 m/s üzeri hareket hiç gerçekleşmedi, dolayısıyla t≈115'teki
+3.8°'lik pitch yanlılığı **tekrar etmedi**. İstenen doğrulama budur.

Seyir yeteneği korundu: tepe yatay hız 5.48 m/s.
Test paketi: **478 geçti, 1 atlandı.**

---

## 5. Açık kalanlar

1. **Simülatör akış sensörü hâlâ arızalı** (E4b adayı). `EKF2_OF_CTRL 0`
   arızayı gizlemiyor, yalnızca EKF'in ona inanmasını kesiyor. Sensörün
   kendisi düzeltilene kadar SITL, H-FLOW'u **modellemiyor**.
2. **Gerçek donanım kararı ayrı bir kapı.** Gerçek araçta H-FLOW takılı ve
   `EKF2_OF_CTRL` orada hâlâ PX4 varsayılanında. O kararın verilmesi için
   saha kalibrasyonu gerekiyor — bu FAZ'da dokunulmadı.
3. Bu koşum tek bırakma yaptı (görev tek hedef buldu). E4c'de 3 koşum
   ölçülecek.

Görev C/D değiştirilmedi, `motion_fsm.py`'a dokunulmadı, push yapılmadı.
