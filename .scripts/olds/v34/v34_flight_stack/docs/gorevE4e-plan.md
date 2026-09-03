# Görev E4e — Iraksama koruması: PLAN (uygulanmadı, onay bekliyor)

**Tarih:** 2026-09-03 · Eşikler run4/run5/run6 verisinden türetildi, uydurulmadı.

---

## 0. Önce bir uyarı: önerdiğiniz 2. guard yazıldığı hâliyle ÇALIŞMAZ

> "(2) yer hızı bir eşiği (öner: 0.5 m/s?) aşarken payload bırakılmasın"

Yer hızı **EKF'ten** okunur (`get_velocity_ned()` → `position_velocity_ned`,
aynı kestirim). Iraksama anında EKF **yalan söylüyordu**:

| run4, bırakma anı | EKF'in bildirdiği | GERÇEK |
|---|---|---|
| yatay hız | **0.05 m/s** | **3.00 m/s** |

Yani EKF hızına dayalı bir kapı, onu doğuran arızayı **tam olarak
göremezdi** — run4'te sessizce açık kalırdı. Aynı şey `get_position_ned`
için de geçerli. Araç üstünde bağımsız bir hız kaynağı yok.

Denedim, işe yaramayan bir alternatif de var — "komut ediyorum ama kendi
kestirimim hareket etmiyorum diyor" oranı **ayırmıyor**:
run4 (ıraksayan) 0.43, run5 (sağlıklı) **0.23**, run6 (sağlıklı) 0.77.
Sağlıklı koşum ıraksayandan daha düşük. Bu metriği eledim.

**Ayıran tek iç gözlem: kalan mesafenin eğilimi ve yakınsama sonucu.**

---

## 1. Guard 1 — ıraksama dedektörü

**Dosya:** `core/navigation/centering_controller.py`, `_mount_translate`
döngüsü içi.

**Mantık:**
```
residual bir önceki tick'ten EPS=1e-3 m fazlaysa  -> ardisik_buyume += 1
                                     degilse      -> ardisik_buyume = 0
if ardisik_buyume >= N  ve  residual > MOUNT_TRANSLATE_TOLERANCE_M:
     -> donguden CIK, MOUNT_TRANSLATE_DIVERGED yayinla, diverged=True dondur
```

**N için kanıt** (`MOUNT_TRANSLATE_TICK` kayıtlarından, en uzun **ardışık**
büyüme serisi):

| koşum | sonuç | n tick | en uzun ardışık büyüme | net değişim |
|---|---|---|---|---|
| run5 | yakınsadı | 6 | **0** | −0.029 m |
| run6 | yakınsadı | 13 | **1** | −0.042 m |
| run4 | SÜRE DOLDU | 76 | **12** | +0.291 m |

**Öneri: N = 5.** Sağlıklı koşumlarda görülen en kötü değerin (1) **5 katı**,
ıraksayan koşumun ulaştığı 12'nin altında. 10 Hz'de 0.5 s demek — kaçış
8 s yerine ~0.5 s'de kesilir.
`residual > tolerans` ek koşulu, normal yakınsama sırasındaki milimetrik
gürültünün guard'ı tetiklemesini imkânsız kılar.

**Dürüst sınır:** elimde tick kaydı olan yalnızca **3** `_mount_translate`
penceresi var (E4a öncesi enstrümantasyon yoktu). N=5 bu üç pencereye göre
güvenli; daha uzun bir sağlıklı pencere daha çok büyüme gösterebilir. Bu
yüzden N'i parametre yapıp E4c'nin 3 koşumunda doğrulamayı öneriyorum.

---

## 2. Guard 2 — bırakma kapısı (önerinizin yerine)

**Dosya:** `core/mission/payload_release.py`, servo ateşlenmeden önce.

**Birincil kapı: YAKINSAMA, hız değil.** 8 bırakmada kusursuz ayrışıyor:

| mount_translate | ıska aralığı |
|---|---|
| yakınsadı (n=5) | 0.059 – 0.885 m |
| süre doldu / ıraksadı (n=4) | 2.121 – 10.185 m |

`converged` zaten hesaplanıyor ve loglanıyor; yeni telemetri gerekmiyor
(ADR-008 B0/B1 uyarısına uyar).

**İkincil kapı: yer hızı < 0.5 m/s.** Sizin önerdiğiniz değeri **koruyorum**
ve veriyle destekliyorum — ama *ikincil* olarak, sınırını açıkça yazarak:

| bırakma | EKF'ten okunan hız | ıska |
|---|---|---|
| run5 KIRMIZI | 0.036 m/s | 0.059 m |
| run6 KIRMIZI | 0.035 m/s | 0.341 m |
| run5 MAVI | 0.206 m/s | 0.448 m |
| run4 KIRMIZI | (gerçek 2.864) | 10.185 m |

Sağlıklı bırakmaların en kötüsü **0.206 m/s**; 0.5 m/s bunun **2.4 katı**,
yani yanlış tetiklemez. Kaba bir hareketi yakalar; **kestirim arızasına
kördür** ve dosyada böyle belgelenecek.

---

## 3. Guard tetiklendiğinde görev ne yapar — ÖNERİM

Üç seçenek ve gerekçeleri:

| | ne yapar | değerlendirme |
|---|---|---|
| (i) Tam abort | görevi bitir | **Fazla sert.** Yük hâlâ araçta, araç sağlam, Görev 2'nin ikinci yükü ve Görev 3 duruyor |
| (ii) **Yükselip bir kez tekrar dene** | son yaklaşma irtifasına (5.0 m) tırman, `go_to_and_center` + final adımı tekrarla | **ÖNERİM.** Tırmanmak iki sorunu birden çözer: 2.0 m'lik `LOW_ALT_VISION_LIMIT_M` üstüne çıkıp **görüşü geri kazandırır**, ve kestirimin en kötü olduğu güverte bölgesinden uzaklaştırır |
| (iii) Bu yükü atla | yükü araçta tut, CRITICAL yayınla, `release_and_verify` False dönsün | (ii) de başarısız olursa **buraya düş** |

**Önerim: (ii) → başarısızsa (iii).**

Mimariye uyumu: `release_and_verify`'ın dönüşü zaten `gorev2_fsm.py:93/119`
tarafından kullanılıyor, yani "bu bırakma olmadı" durumu **zaten** temsil
edilebiliyor. Yeni bir görev durumu icat etmeye gerek yok.

**Dikkat çekmek istediğim mimari çelişki:** `_staged_approach`'un docstring'i
şu anda bunun tersini söylüyor —
> "Ara adımlardan biri yakınsayamazsa akışı durdurmak yerine devam edilir
> (best-effort -- alçalmanın ortasında durup hiç bırakmamak, hafif kusurlu
> bir pozisyondan bırakmaktan daha kötüdür)."

Bu karar **"hafif kusurlu"** varsayımıyla alınmış. Ölçüm o varsayımı çürüttü:
yakınsamama **10 m** demek olabiliyor. Guard 2, bu politikayı **yalnızca son
adım için** tersine çevirir; ara adımlar (10 m, 5 m) best-effort kalır.
Bu, bilinçli bir tasarım kararının değiştirilmesidir — onayınızı bu yüzden
ayrıca istiyorum.

---

## 4. Dokunulacak dosyalar

| dosya | değişiklik |
|---|---|
| `core/config/parameters.py` | `MOUNT_TRANSLATE_DIVERGE_TICKS = 5`, `MOUNT_TRANSLATE_DIVERGE_EPS_M = 0.001`, `PAYLOAD_RELEASE_MAX_GROUND_SPEED_M_S = 0.5`, `PAYLOAD_RELEASE_RETRY_ALTITUDE_M = 5.0` |
| `core/navigation/centering_controller.py` | `_mount_translate`: ıraksama sayacı + erken çıkış + `MOUNT_TRANSLATE_DIVERGED` olayı; sonucu `self.last_translate_diverged` alanına yaz (mevcut `getattr` ile zarif düşme desenine uyar) |
| `core/mission/payload_release.py` | son adımda servo öncesi kapı; tetiklenirse (ii) tırman-ve-tekrar-dene, sonra (iii) atla |
| `tests/` | yeni testler: N eşiği, gürültüde tetiklenmeme, kapının ateşlemeyi engellemesi, tekrar-deneme yolu, atlama yolu |

**Dokunulmayacak:** `motion_fsm.py`, Görev C'nin `_start_release_hold`
mekanizması, `go_to_and_center`, ara yaklaşma adımlarının best-effort'u.

---

## 5. Onayınızı istediğim üç nokta

1. **Yer hızı kapısını ikincil**e indirip **yakınsamayı birincil** yapmam —
   çünkü hız kapısı tek başına run4'ü kaçırırdı.
2. **Guard tetiklenince (ii) tırman-ve-tekrar-dene, sonra (iii) atla.**
3. `_staged_approach`'un **son adım** için best-effort politikasının
   tersine çevrilmesi (ara adımlar aynı kalır).

E4a uygulandıktan sonra bu guard'ın SITL'de **hiç tetiklenmemesi** beklenir;
amacı gerçek donanım ve gelecekteki kestirim sorunları için derinlemesine
savunmadır.

---

# EK — Onay sonrası üç şart (A, B, C)

## A) N=5'in yanlış-pozitif riski

Örneklem büyütüldü: `MOUNT_TRANSLATE_TICK.residual_m` yalnızca run4/5/6'da
var (enstrümantasyon FAZ 1.5'te eklendi), ama `LOW_ALT_OPEN_LOOP_STEP.hold_error_m`
**aynı niceliği** (held noktasına mesafe) **aynı 10 Hz kontrol döngüsünde**
ve **tüm koşumlarda** taşıyor. İkisi birlikte 7 pencere / 15 artış serisi:

| koşum | şekil | kaynak | n | yakınsadı | seriler | max |
|---|---|---|---|---|---|---|
| run2 | MAVI | OPEN_LOOP | 8 | evet | – | **0** |
| run5 | KIRMIZI | MOUNT_TR | 6 | evet | – | **0** |
| run5 | MAVI | OPEN_LOOP | 11 | evet | – | **0** |
| run6 | KIRMIZI | MOUNT_TR | 13 | evet | 1,1,1 | **1** |
| run3 | MAVI | OPEN_LOOP | 13 | hayır | 3,1 | 3 |
| run4 | KIRMIZI | OPEN_LOOP | 4 | hayır | 3 | 3 |
| run4 | KIRMIZI | MOUNT_TR | 76 | hayır | 12,9,3,2,2,1,1,1 | **12** |

**Seri uzunluğu dağılımı (n=15):** 1×8 · 2×2 · 3×3 · 9×1 · 12×1

**Belirleyici gözlem: 3 ile 9 arasında HİÇ seri yok.** N=5 bu boşluğun tam
ortasında; 4–8 arasındaki her N bu veride **aynı** sınıflandırmayı yapar.

- Yakınsayan pencerelerde ≥5 olan seri: **0 / 3 (%0)**, gözlenen en uzun **1**
- N=5, sağlıklı en kötünün **5 katı**; yakalanması gereken en kısa kötü
  serinin (9) **4 tick öncesinde** ateşler

**Örneklem sınırı (açıkça):** 7 pencere, 15 seri, bunların yalnızca **3'ü**
yakınsayan pencerelerden. Bu küçük bir örneklemdir. Bu yüzden N **parametre**
olarak eklenir ve E4c'nin 3 koşumunda doğrulanır.

**Guard 1 tek başına yeterli değil — ve zaten değil:** run3 MAVI (süre doldu,
45.6 cm, 5.305 m ıska) proxy sinyalinde en uzun 3'lük seri gösteriyor, yani
N=5 onu **yakalamazdı**. Guard 2 (yakınsama kapısı) onu yakalar. İkisi
birlikte derinlemesine savunmadır; bu bilerek böyledir.

## B) "Atla" durumunda görev durumu — BEKLENMEDİK BİR KUSUR BULDUM

Bu şartı incelerken **mevcut ve benim değişikliğimden bağımsız** bir kusur
çıktı:

`core/mission/gorev2_fsm.py:93-99` ve `119-126`:
```python
result = await self.release_service.release_and_verify(...)
self.interlock.mark_released("MAVI_ALTIGEN")        # <-- KOSULSUZ
self.position_store.mark_payload_released("MAVI_ALTIGEN")
```
`mark_released` **`result`'a bakmıyor.** Ve `core/mission/gorev3_precondition.py`:
> Görev 3 YALNIZCA `payload_1_released == True VE payload_2_released == True`
> olduğunda başlar. … Eğer bu False dönerse Görev 3'e **ASLA girilmez**.

Yani bugün bile, bırakılmamış bir yük "bırakıldı" işaretlenir ve Görev 3'ün
kapısı **yanlışlıkla açılır**. Kapının var oluş amacı tam da budur ve
koşulsuz `mark_released` onu **etkisiz kılıyor**.

**Ayrıca `result`'ı bu iş için kullanamayız:** `release_and_verify`'ın dönüşü
*marker doğrulaması*dır ("bu doğrulama görev akışını durdurmaz"), bırakmanın
gerçekleşip gerçekleşmediği değil — kayıtlarda başarıyla bırakılmış bir yük
için `PAYLOAD_MISSION_1_COMPLETE {"verified": false}` görülüyor.

**Planlanan:** ayrı ve açık bir sinyal — `self.last_payload_retained` (bool).
`gorev2_fsm` bunu `getattr` ile okur; True ise `mark_released` **çağrılmaz**,
`PAYLOAD_RETAINED` CRITICAL yayınlanır. Sonuç: `both_released()` False kalır
ve Görev 3 tasarlandığı gibi **girilmez**. Bu bir politika değişikliği değil,
kapının **amacına iadesidir**.

Diğer kontroller:
- **Görev 2'nin ikinci yükü etkilenmez** — ayrı hedef, ayrı servo kanalı.
- **Aktüatör** yeniden ateşlemez; `_confirm_separation` False döner ve
  `mark_released` çağrılmadığı için interlock ikinci denemeyi de engellemez
  (INTERLOCK_VIOLATION yalnızca `_order`'a girmiş şekiller için).
- **`gorev3_redrop`** `get_released_payload_pose` ile yükün pozunu okuyor;
  yük hâlâ takılıysa "HAVADA (hala kancada olabilir)" yazar — kabul edilebilir
  bozunma, zaten Görev 3'e girilmeyecek.

## C) Guard'ın log işareti

Olay adı: **`MOUNT_TRANSLATE_ABORTED_DIVERGING`** (önerdiğiniz gibi), severity
CRITICAL. `_mount_translate` döngüsünün **içinden**, `self._publish` ile
yayınlanır — yani `MOUNT_TRANSLATE_TICK` ile **aynı 10 Hz kontrol yolu**;
`VEHICLE_TELEMETRY`'ye hiç dokunmaz.

Olay verisine kanıt gömülür (post-analiz başka kaynağa ihtiyaç duymasın):
ardışık büyüme sayacı, tetikleme anındaki ve serinin başındaki `residual`,
son N `residual` değeri, geçen süre, `held` noktası, o anki `lat/lon`.

> **Not — 3.7 s gecikme bulgusu geri çekilmişti.** FAZ 1.5'te ölçüldü:
> `VEHICLE_TELEMETRY` gecikmesi tüm uçuşta ortanca **+0.03 s**, konum hatası
> 0.089 m. Önceki "3.7 s" rakamı yalnızca ıraksama pencerelerinde ölçülmüştü
> ve donmuş EKF konumunun yolun erken bir noktasıyla eşleşmesinden
> kaynaklanıyordu. Yine de guard'ı kontrol yoluna bağlama gerekçesi geçerli:
> tek kaynak, aynı tick, türetilmemiş veri.

## Genel felsefeyle çelişki — KOD İÇİNDE de yazılacak

`_staged_approach`'ın docstring'i "ara adım yakınsamazsa devam edilir
(best-effort)" diyor. Guard 2 bunu **yalnızca son adım** için tersine çevirir.
Bu istisna hem `_staged_approach` docstring'ine hem son adım kapısının
yanına, ölçümle birlikte yazılacak — "neden burası farklı" sorusu kodun
içinde cevaplanmış olacak.

---

# FAZ 2 — UYGULANDI (2026-09-03)

## Değişen dosyalar

| dosya | değişiklik |
|---|---|
| `core/config/parameters.py` | `MOUNT_TRANSLATE_DIVERGE_TICKS=5`, `MOUNT_TRANSLATE_DIVERGE_EPS_M=0.001`, `PAYLOAD_RELEASE_MAX_GROUND_SPEED_M_S=0.5`, `PAYLOAD_RELEASE_RETRY_ALTITUDE_M=5.0` — her biri ölçüm gerekçesiyle |
| `core/navigation/centering_controller.py` | Guard 1: `_mount_translate`'e ardışık büyüme sayacı + erken çıkış + `MOUNT_TRANSLATE_ABORTED_DIVERGING`; `last_translate_diverged` bayrağı; `MOUNT_TRANSLATE_DONE`'a `diverged` alanı |
| `core/mission/payload_release.py` | `_approach_step()` çıkarıldı (son adım tek başına tekrarlanabilsin); `_staged_approach` artık son adımın yakınsamasını döndürüyor; `_release_gate_ok()`; tırman→tekrar→atla zinciri; `last_payload_retained` |
| `core/mission/gorev2_fsm.py` | (B) `mark_released` artık **koşullu** |
| `tests/test_e4e_divergence_guard.py` | 14 yeni test |

## Doğrulama

**Test paketi: 478 → 492 geçti, 1 atlandı.** Regresyon yok.

**Canlı SITL (run7), yanlış-pozitif kontrolü:**
```
MOUNT_TRANSLATE_ABORTED_DIVERGING : 0
PAYLOAD_RELEASE_GATE_BLOCKED      : 0
PAYLOAD_RELEASE_RETRY             : 0
PAYLOAD_RETAINED                  : 0
PAYLOAD_RELEASE_GATE_PASSED       : 1
   {"passed": true, "final_step_converged": true, "translate_diverged": false,
    "ground_speed_m_s": 0.135, "max_ground_speed_m_s": 0.5,
    "ground_speed_note": "EKF kaynakli -- kestirim arizasina kor"}
MOUNT_TRANSLATE_DONE: kalan 4.3 cm, 0.32 s (yakinsadi)
PAYLOAD_FINAL_POSE : merkeze 6.9 cm (HEDEFTE)
```
Guard sessiz kaldı, kapı çalıştı ve geçti, bırakma **6.9 cm**.

## Entegrasyon testi (istediğiniz)

`test_integration_guard1_fires_and_stops_early_on_diverging_estimate`
**gerçek** `_mount_translate`'i, kestirimi bozuk bir sahte araçla çalıştırıyor
(`_DivergingFlight`: komut ne olursa olsun raporlanan konum tekdüze uzaklaşır,
`get_velocity_ned` run4'teki gibi 0.05 m/s "duruyorum" der). Çakılanlar:
`MOUNT_TRANSLATE_ABORTED_DIVERGING` yayınlandı · `last_translate_diverged`
True · bütçe **dolmadan** çıkıldı · kanıt olayın içinde (`growth_streak`,
seri başı/sonu residual, son N değer) · `MOUNT_TRANSLATE_DONE.diverged` True.

`test_integration_climb_retry_then_skip_and_payload_is_retained` tam zinciri
çakıyor: `GATE_BLOCKED` → `RETRY` → 5.0 m'ye tırmanış (>2.0 m görüş kapısı) →
son adım tekrar → `RETAINED` → **servo hiç ateşlenmedi** → `last_payload_retained`.

`test_integration_retained_payload_is_not_marked_released` (B): interlock
işaretlenmeyince `check_gorev3_precondition` False kalıyor.
