# GÖREV G / Ö5 — Soru 1: kayma NEREDEN geliyor + Soru 3-lite + Soru 4 değerlendirmesi

**Tarih:** 2026-09-04 · **Tip:** ölçüm + değerlendirme · **Kod/config değişikliği: YOK**

---

## SORU 1 — CEVAP: `ref_alt` ile `home_position.alt` arasındaki fark

Cebir önceden kuruldu, ölçüm birebir tuttu:

```
relative_altitude_m = global.alt − home.alt
global.alt          = ref_alt + (−local.z)
⇒ C − A = (relative_alt) − (−local.z) = ref_alt − home.alt
```

| koşum | `ref_alt` | `home.alt` (son) | **`ref_alt − home.alt`** | **ölçülen `C − A`** |
|---|---|---|---|---|
| q1 | 0.2757 | 0.4525 | **−0.1768 m** | **−0.178 m** (8–16 m bandı: −0.177) |
| q4 | 0.2655 | 0.4440 | **−0.1786 m** | −0.179 m (8–16 m bandı) |

**Fark 1 mm'nin altında. Mekanizma kesin.**

### Kayma nasıl doğuyor

| alan | yazılma sayısı | davranış |
|---|---|---|
| `vehicle_local_position.ref_alt` | **1** (`n_uniq=1`) | EKF yerel orijini, **bir kez** kurulup sabitleniyor |
| `home_position.alt` | **43–45** kayıt, t≈5.0 s'den itibaren | commander tarafından **sürekli güncelleniyor**, 0.240 → **0.452**'ye sürükleniyor |

Yani: **EKF orijini erken sabitleniyor; home ise araç yerde dururken EKF'in
kendi irtifa kestirimi süründükçe güncelleniyor ve 0.177 m yukarıda
kalıyor.** İkisi arasındaki fark, `relative_altitude_m`'in taşıdığı hata.

### Kritik sonuç: sistem KENDİ İÇİNDE tutarsız

- **Setpoint'ler** `goto_position_ned_and_hold(n, e, −0.30, …)` ile
  **NED / EKF-orijini** çerçevesinde veriliyor.
- **Okumalar** `_current_alt_m()` → `get_global_position()[2]` ile
  **home-referanslı** `relative_altitude_m`'den geliyor.

Ölçüm bunu doğruluyor: kontrolcü A'yı (EKF −z) 0.301/0.324'te tutuyor,
yani **komutu tam tutturuyor**; yanlış olan tek şey göreve rapor edilen
sayı. **Hata kontrolde değil, iki farklı çerçevenin karıştırılmasında.**

---

## SORU 3-lite — SITL'e özgü mü, PX4 mantığı mı

**PX4'ün kendi mantığı. Gazebo'ya özgü hiçbir yapılandırma devrede değil.**

Kanıt:
- `ref_alt` ve `home_position.alt`, EKF2 ve commander tarafından üretiliyor;
  `PX4_GZ_MODEL_POSE` ya da başka bir Gazebo değişkeni bu iki alana
  **girmiyor** (ne SDF spawn pozu ne de gz ortamı bu hesaba dahil).
- `home_position` yerdeyken tekrar tekrar güncellenip `ref_alt`'ın bir kez
  kurulması, **platformdan bağımsız PX4 davranışı**dır.
- `manual_home = 0`, `valid_alt = 1` — home normal otomatik yoldan kuruluyor,
  özel bir SITL kısayolu yok.

**Dolayısıyla gerçek donanımda AYNI SINIF hata beklenir.** Değişebilecek
tek şey **büyüklüğü**: burada 0.177 m, ve bu, EKF'in ilk saniyelerdeki
irtifa sürüklenmesinden geliyor. Gerçek baro sürüklenmesi tipik olarak
**daha az değil, daha fazla** olur — yani gerçek uçuşta hata küçülmeyi
değil büyümeyi bekletir.

> Bu bir **kesin donanım hükmü değil** (donanım yok); ancak mekanizmanın
> platformdan bağımsız olduğu **ölçülmüş bir gözlemdir**, ve kararı
> "SITL artefaktı, boş ver" yönünde vermeyi engeller.

---

## SORU 4 — DEĞERLENDİRME: tek noktada düzeltme

**Ön görüşünüze katılıyorum, ve ölçüm onu beklediğimden daha güçlü
destekliyor.**

### Neden düşük riskli — eşikleri taşımaya gerek YOK

Kritik nokta şu: **setpoint'ler zaten doğru çerçevede.** Düzeltme,
okumayı setpoint'in zaten kullandığı çerçeveye taşımak demek — yani
**komut edilen hiçbir irtifa değişmiyor.**

| | bugün | okuma düzeltilirse |
|---|---|---|
| `goto_position_ned_and_hold(…, −0.30)` | NED −0.30 | **değişmez** |
| aracın gerçekte gittiği yer | EKF −z ≈ 0.30 | **değişmez** |
| `_current_alt_m()` ne diyor | **0.12** (yanlış) | **0.30** (setpoint'le tutarlı) |

Yani bu, "eşikleri yeni bir çerçeveye taşımak" değil; **okumayı, eşiklerin
zaten yazıldığı çerçeveye geri getirmek.** Sizin umduğunuz ölçeklenebilirlik
tam olarak burada.

### Kaynak hazır — yeni akış/abonelik gerekmiyor

`get_position_ned()` **zaten var, zaten önbellekli, zaten kullanılıyor**
(`mavsdk_backend_base.py:474-480`, `position.down_m`). Yatay bileşenleri
her yerde kullanılıyor, dikey bileşen (`down_m`) atılıyor.

```
mavsdk_backend_base.py:521   return (…, pos.relative_altitude_m)     ← home-referansli
mavsdk_backend_base.py:480   return (…, pos.position.down_m)         ← EKF-orijini
```

`position_velocity_ned` ile `vehicle_local_position` aynı uORB kaynağının
MAVLink karşılığıdır, yani `−down_m == −local.z` **yapı gereği**.
*(Bu eşitlik ayrıca uçuşta ölçülmedi; düzeltmenin doğrulamasında ilk
kontrol bu olmalı.)*

### Kapsam — 36 çağrı, 8 dosya

`get_global_position()` külliyatta **36 yerde** çağrılıyor
(`centering_controller`, `motion_fsm`, `payload_release`,
`gorev2_orchestrator`, `gorev3_pickup`, `gorev3_redrop`, `master_fsm`).
Hepsi aynı bozuk irtifayı okuyor. **Tek noktadan düzeltme 36'sını birden
düzeltir** — parça parça düzeltmenin anlamı yok.

### Beklenen ikinci kazanç: `[HIZA_KALIBRASYON]` sapması

`_rect_pixel_offset()` piksel→metre çevrimini `get_global_position()[2]`
ile yapıyor (`gorev3_pickup.py:301` civarı, `offset = hypot(dx,dy) · alt / focal`).
`alt` gerçeğin ~2.5 katı küçükse **görüntü tahmini de o oranda küçük çıkar.**

Ölçülen oranlar (görüntü/gerçek): 0.29× / 2.1× / 3.3× / 6.7× — çoğunlukla
görüntü **küçük**, ve mertebe irtifa hatasıyla uyumlu. Bunu ayrı bir sorun
diye işaretlemiştim; **büyük ihtimalle aynı kök nedenin bir başka yüzü.**
Düzeltme sonrası bu oranın 1'e yaklaşması, düzeltmenin **bağımsız bir
doğrulaması** olur.

### Düzeltmenin KAPATMADIĞI şey

`A − B` = −0.12 … −0.17 m: **EKF'in kendisi gerçeği eksik kestiriyor.**
Bu telemetri katmanında düzeltilemez (kestirim doğruluğu, çerçeve değil).
Düzeltme sonrası araç "EKF 0.30"da duracak, gerçekte ~0.42'de olacak.

Ama iki hafifletici var:
1. **Ö1** salım referansını zaten nominal 0.30'a bağladı, yani salım yolu
   bu hatadan zaten etkilenmiyor.
2. **Ö3** erişilemez durumları ölçerek yakalıyor ve 3 denemeyi yakmıyor.

---

## ÖNERİM (uygulanmadı)

**Tek noktada, `get_global_position()`'ın irtifa bileşenini EKF-orijini
çerçevesine taşımak** — sizin ön görüşünüzle aynı yönde, ve ölçüm bunu
"eşik taşıma" işi olmaktan çıkarıyor.

Uygulanırsa doğrulama sırası:
1. `−down_m == −local.z` eşitliğini canlı bir koşumda **ölç** (yapı
   argümanına güvenme).
2. Aynı üç kaynaklı hizalı ölçümü tekrarla: `C − A` **0'a** inmeli.
3. `[HIZA_KALIBRASYON]` görüntü/gerçek oranı **1'e** yaklaşmalı.
4. Tam test paketi + en az 2 bağımsız koşum.

**Riskli olan tek yer:** `motion_fsm` ve `payload_release` da aynı okumayı
kullanıyor ve Görev 2 bugün **çalışıyor**. Okuma 0.177 m büyüyünce
Görev 2'nin bırakma irtifası (`0.45 m`) aynı komutla **daha alçakta**
gerçekleşmez — çünkü o da NED setpoint'iyle sürülüyor — ama
**doğrulanmalı**, varsayılmamalı. Görev 2'nin isabetini (bu oturumda
0.106–0.178 m) düzeltme öncesi/sonrası karşılaştırmak yeterli.

**DURUYORUM — uygulama için onay bekliyorum.**

---

## Kapsam ve sınırlar

- Soru 1 **kesin** (2 koşum, 1 mm uyum).
- Soru 3-lite: mekanizmanın platformdan bağımsız olduğu **gösterildi**;
  gerçek donanımda büyüklüğün ne olacağı **ölçülmedi** ve ölçülemez.
- `−down_m == −local.z` eşitliği **yapı argümanı**, uçuşta doğrulanmadı.
- EKF↔gerçek farkı (0.12–0.17 m) bu turda **incelenmedi**.
- Kod ve config değiştirilmedi.
