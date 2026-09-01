# KURSAD40 v33 — SAHA HAZIRLIK RAPORU (Phase 16-17 yerine)

**Tarih:** 2026-08-24
**Durum:** Phase 16 (bench kalibrasyonu) ve Phase 17 (gerçek uçuş) fiziksel
donanım gerektirir; kod tarafından yapılamaz. Bu belge onların yerine geçen
**kontrol listesidir**. Hiçbir kod değişikliği içermez.

---

## 1. GERÇEK UÇUŞU BUGÜN BLOKLAYAN ŞEYLER

Aşağıdakiler tamamlanmadan Görev 3'ün payload adımları gerçek donanımda
**çalışmaz** — sessizce değil, açıkça: `RealPayloadBackend` kalibrasyon
guard'ında durur ve `Gorev3PickupPhase` bunu temiz bir faz başarısızlığına
çevirir. Kalkışta da uyarı loglanır (`warn_if_uncalibrated`).

### 1.1 Servo FLEX'leri — HEPSİ TBD

| FLEX | Ne | Guard'ladığı metod |
|---|---|---|
| FLEX-14 | SERVO2 actuator index | `deploy()`, `retract()`, `stow()` |
| FLEX-15 | SERVO3 actuator index | `grapple()`, `release()` |
| FLEX-16 | SERVO2_DOWN değeri | `deploy()` |
| FLEX-17 | SERVO3_GRAPPLE değeri | `grapple()` |
| FLEX-18 | SERVO2_REVERSE değeri | `retract()`, `stow()` (paylaşımlı) |
| FLEX-19 | SERVO3_RELEASE değeri | `release()` |

Hepsi `payload/payload_config.py`'de `None`. Her birinin HOW TO CALIBRATE
adımları aynı dosyada.

**Bench script'i YAZILDI (2026-08-25):** `tools/calibrate_real_servos.py`.
Üretim API'sini (PayloadManager + RealPayloadBackend) bypass eder — zorunlu
olarak: backend'in CALIBRATION GUARD'ı FLEX-14..19 `None` iken her komutu
durdurur, yani üretim yolundan kalibrasyon yapılamaz. Ham veri (CSV) üretir,
`payload_config.py`'ye **HİÇBİR ŞEY YAZMAZ**. Donanım gelmeden prosedürün
kendisi `--dry-run` ile denenebilir (MAVSDK'ya hiç dokunmaz).

Bu, §1.1'i **KAPATMAZ** — kapatan şey ölçümün kendisidir. Script yalnızca
ölçümü yapılabilir kılar; FLEX-14..19 hâlâ `None`.

### 1.2 Sensör entegrasyonu — YOK

`RealPayloadBackend`'de `await_capture()` ve **altı sorgu metodunun hepsi**
`NotImplementedError`. Sebep: yakalamayı doğrulayacak telemetri/sensör yolu
repoda mevcut değil. Sahte implementasyon KASITLI olarak yazılmadı.

Bu, `TODO(SAFETY)` olarak dosyanın başında duruyor ve şunu söylüyor:
backend'in `True` dönüşü yalnızca **komutun flight controller tarafından
kabul edildiği** anlamına gelir; servonun fiziksel pozisyona ulaştığı
anlamına **GELMEZ**.

### 1.3 FLEX-01 — Real capture envelope, TBD

`FLEX_01_HOOK_CAPTURE_ENVELOPE_M = None`. Bugün **hiçbir tüketicisi yok**
(Real `is_in_capture_zone()` zaten NotImplementedError). Sensör entegrasyonu
geldiğinde tüketicisi olacak.

---

## 2. BENCH TEST SIRASI (önerilen)

Sıra önemli: her adım bir öncekinin sonucunu kullanıyor.

### Adım 1 — Actuator index'lerini bul (FLEX-14, FLEX-15)
Araç bağlıyken, propeller ÇIKARIK, MAVSDK `Action.set_actuator(index, value)`
ile index'leri **1'den başlayarak** tek tek sür. Servo2'nin (kanca
indirme/çekme) ve Servo3'ün (kavrama/bırakma) hangi index'te hareket ettiğini
kaydet. **Not: MAVSDK'da index 1'den başlar, 0'dan değil.**

```
python3 tools/calibrate_real_servos.py index --servo Servo2 \
        --indices 1 2 3 4 5 6 --probe-value 0.30
```
`--indices` ve `--probe-value` bilinçli olarak **zorunludur, varsayılanı
yoktur**: geçerli index kümesi bu adımın bulmaya çalıştığı şeydir, probe
değeri ise mekanizmayı görmeden verilemeyecek bir fiziksel güvenlik
kararıdır. Gerekçe script'in modül docstring'inde.

> Bu adım `real_system/config/real_system.yaml`'daki
> `mission_v3.servo2_actuator_channel` / `servo3_actuator_channel` alanlarını
> da cevaplar — ikisi de `null`. `TODO(CONFIG-SYNC)`: `payload_config.py` tek
> otoritedir; iki kaynak Phase 16'da tek kaynağa indirilmeli.

### Adım 2 — Servo uç değerlerini bul (FLEX-16..19)
Her servo için 0.0'dan başlayıp hedef yönde **0.05'lik adımlarla** ilerle.
Her adımda mekanizmanın konumunu gözle. Hedef konuma ulaşan **İLK** değeri
al; mekanik sınıra dayanan değerleri ALMA (servo stall'a girer, donanım
zarar görür).

- FLEX-16: kanca tam inmiş
- FLEX-18: kanca tam toplanmış — **yüklü VE yüksüz** doğrula. İkisi farklı
  değer istiyorsa bu bir **tasarım bulgusudur**: FLEX-18'in ikiye bölünmesi
  TARTIŞILMALI, sessizce ikinci bir sayı eklenmemeli.
- FLEX-17: kavrama güvenilir tutuyor, servo akımı stall seviyesine çıkmıyor
- FLEX-19: payload takılmadan tam serbest kalıyor (en az 10 tekrar)

```
python3 tools/calibrate_real_servos.py value \
        --flex FLEX_16_SERVO2_DOWN_VALUE --index <ADIM 1'in sonucu> --direction +
```
Script `0.0`'dan `0.05` adımlarla ilerler (bu iki sayı FLEX-16 HOW TO
CALIBRATE'ten gelir, script'te seçilmemiştir) ve `±1.0`'ı (MAVSDK
sözleşmesi) aşmaz. Operatör "mekanik sınır" derse tarama **anında durur**
ve o değer aday olarak **işaretlenmez**.

### Adım 3 — Süre ölçümleri (FLEX-02, 04, 08, 13)
Her komuttan fiziksel tamamlanmaya kadar geçen süre, **en az 10 tekrar**,
ortalama + %50 güvenlik payı.

### Adım 4 — Capture envelope (FLEX-01)
Kancayı payload'a kademeli mesafelerle yaklaştır, her mesafede yakalama
başarı oranını kaydet. Güvenilir (>%95) yakalamanın başladığı **en büyük**
mesafeyi envelope olarak al.

### Adım 5 — Montaj ölçümleri (FLEX-09, FLEX-21)
- FLEX-09: kanca merkezinden payload yakalama noktasına X/Y/Z (CAD/cetvel)
- FLEX-21: aracı bilinen bir işaretin üstünde merkezle, kancayı indir,
  kancanın indiği nokta ile işaret arasındaki **ileri/sağ** farkı ölç.
  En az 5 tekrar. Konvansiyon: `(forward_m, right_m)`, PX4 body/FRD —
  `CAMERA_LEVER_ARM_BODY_M` ile aynı.

### Adım 6 — Sensör entegrasyonu (kod işi, bench değil)
`await_capture()` ve sorgu metodlarını besleyecek yol kurulmalı. Bu
yapılmadan `TODO(SAFETY)` kapanmaz ve **gerçek uçuşa GEÇİLMEMELİ**.

---

## 3. KOD TARAFINDA NELERİN AÇILMASI GEREKTİĞİ

| Ne | Nerede | Ne zaman kapanır |
|---|---|---|
| `TODO(SAFETY)` — fiziksel tamamlanma doğrulanamıyor | `real_payload_backend.py` başı | Adım 6 sonrası |
| `TODO(CONFIG-SYNC)` — yaml/config çift kaynak | `payload_config.py` FLEX-14/15 | Adım 1 sonrası |
| `TODO(PHASE-15-PARITY)` — Gazebo capture/secured ayrımı | `gazebo_payload_backend.py` + FLEX-20 | Phase 15 parity |
| ~~Real bench kalibrasyon script'i~~ | `tools/calibrate_real_servos.py` | **YAZILDI 2026-08-25** (Adım 1-2; Adım 3-5 script işi değil) |

---

## 4. KALİBRASYON SONRASI GÖZDEN GEÇİRİLECEK KARARLAR

Bunlar bugün **gerçek uçuş verisi olmadan** verilmiş kararlardır. Veri
geldiğinde yeniden bakılmalı:

1. **FLEX-20 = 0.35 m** — politika eşiği, fiziksel ölçüm değil. PROVENANCE
   `payload_config.py`'de. FLEX-01 bench'te ölçüldüğünde Real/Gazebo envelope
   semantiğinin tutarlılığı Phase 15 parity testinde denetlenmeli.
2. **`MAX_RECOVERY_ATTEMPTS = 2`** ve kurtarma haritası (Phase 13) — hangi
   arızanın ilk tekrarda düzeldiği ancak gerçek veriyle bilinir.
3. **`PAYLOAD_NOT_SECURED → IDLE` kurtarması** — sensör yalan söylerse
   yeniden deploy yükü düşürür. Risk alma irtifasında (~0.30 m) kabul
   edildi; sensör entegrasyonu sonrası yeniden değerlendirilmeli.
4. **HookAttachSystem attach-timeout oranı** — `KNOWN_ISSUES.md` §5,
   YÜKSEK ÖNCELİK. Tekrarlı koşuyla istatistiksel ölçülmeli.

---

## 5. BUGÜN GÜVENLE YAPILABİLECEKLER

- **Gazebo SITL**: payload yolu fiziksel olarak doğrulanmış durumda (Phase 6
  acceptance: yakalama + payload aracı izliyor, takip hatası 0.0002 m).
- **Görev 2**: payload yolundan etkilenmiyor, `IPayloadActuator` üzerinden
  çalışmaya devam ediyor.
- **Gerçek uçuşta Görev 1/2**: payload kalibrasyonu bunları BLOKLAMAZ;
  yalnızca Görev 3'ün alma/bırakma adımları düşer, o da temiz şekilde.
