# GÖREV G — H1 doğrulama: irtifa payı hipotezi

**Tarih:** 2026-09-04 · **Tip:** ölçüm · **Kod/config değişikliği: YOK**

## HÜKÜM (önce, kısa)

| iddia | hüküm |
|---|---|
| **H1-a**: `_reacquire_by_climbing()` koşulsuz YUKARI gidiyor | ✅ **DOĞRULANDI** — ama koddan, ölçümden değil |
| **H1-b**: tırmanış tespit payını **azaltıyor** (artırması gerekirken) | ✅ **DOĞRULANDI** (analitik) |
| **H1-c**: bu, gözlenen Faz 1 başarısızlıklarının **nedeni** | ❌ **ÇÜRÜDÜ** — mekanizma 5 bağımsız koşumun **hiçbirinde tetiklenmedi** |

**Tek cümleyle:** H1 gerçek bir tasarım kusurunu doğru teşhis ediyor, ama
**bu kusur şu an hiçbir şeyi düşürmüyor.** Faz 1'i düşüren şey başka ve
5/5'te ölçüldü: **oturma kapısının `too_high` reddi** (§5).

---

## 1 · Bağımsızlık — önce bunu kanıtladım

Önceki set (m1–m5) geçersizdi: SITL yeniden başlatılmamıştı ve beş koşumun
`PAYLOAD_FINAL_POSE`'u bit-aynı çıkmıştı (−3.317, 3.941).

Bu sette **her koşumdan önce tam süreç temizliği + SITL sıfırdan başlatma**
yapıldı. `safe_sitl_launcher.sh:132` her açılışta
`generate_competition_area.py`'yi koşturuyor ve `--seed` **varsayılanı None**
(`generate_competition_area.py:364`, `random.Random(None)` → OS entropisi),
yani her açılış **yeni saha** demek.

| koşum | `blue_hexagon` | `PAYLOAD_FINAL_POSE` (MAVI_ALTIGEN) | yük↔merkez |
|---|---|---|---|
| r1 | (−7.675, 9.249) | (−7.677, 9.355) | 0.106 m |
| r2b | (11.696, 78.398) | (11.693, 78.558) | 0.160 m |
| r3b | (−1.480, 4.672) | (−1.420, 4.761) | 0.107 m |
| r4b | (−7.525, 52.625) | (−7.608, 52.783) | 0.178 m |
| r5b | (11.616, 54.091) | (11.550, 54.247) | 0.169 m |

**Beş farklı saha, beş farklı yük pozu. Bağımsızlık sağlandı.**
(Karşılaştırma: önceki sette beşi de aynıydı.)

### 1.1 Harness arızası — dürüstlük notu

İlk denememde (v1) r2–r5 **Faz 1'e hiç ulaşamadı**; hepsi
`bind error: Address already in use (udp_connection.cpp:93)` ile ilk
saniyelerde öldü. **Bu benim koşum betiğimin hatasıydı**, sistemin değil:
temizlikten sonra MAVSDK UDP portunun boşalmasını beklemiyordum. v2'de port
boşalana kadar bekleme eklendi ve r2b–r5b'de **0 bind hatası** görüldü.
v1'in r2–r5 verisi **kullanılmadı**; yerine r2b–r5b koşuldu.

---

## 2 · Koşum başına sonuç (5 bağımsız koşum)

| koşum | Faz 1'e ulaştı | sonuç | `_reacquire_by_climbing` | `KIRMIZI_DIKDORTGEN` heartbeat |
|---|---|---|---|---|
| **r1** | ✅ | **FAIL#3** `:965` yükü alamadı | **tetiklenmedi** | 77/137 (%56) |
| **r2b** | ✅ | **FAIL#3** `:965` yükü alamadı | **tetiklenmedi** | 85/130 (%65) |
| **r3b** | ✅ | **FAIL#3** `:965` yükü alamadı | **tetiklenmedi** | 57/146 (%39) |
| **r4b** | ✅ | **FAIL#1** `:480` bulunamadı | **tetiklenmedi** | 8/111 (%7) |
| **r5b** | ✅ | **FAIL#3** `:965` yükü alamadı | **tetiklenmedi** | 44/126 (%35) |

**Dağılım: FAIL#3 = 4/5, FAIL#1 = 1/5, FAIL#2 = 0/5.**

Önceki (geçersiz) set 2/2/2 vermişti. Bağımsız ölçümde dağılım **tamamen
farklı** — o setin karışık olduğu bir kez daha görülüyor.

---

## 3 · H1'in çekirdek sorusu: tırmanış payı azaltıyor mu artırıyor mu

### 3.1 Ampirik cevap: **bu 5 koşumdan verilemez**

`_reacquire_by_climbing()` **0/5 koşumda tetiklendi.** Tetiklenmesi için
`_rect_pixel_offset()`'in `visible=False` dönmesi gerekiyor
(`gorev3_pickup.py:625-627`); beş koşumun hiçbirinde bu olmadı.
`FAIL#2` (`:632`) — ki bu, reacquire'ın çalışıp başarısız olmasının **tek**
göstergesidir — **0/5.**

Kullanıcının istediği "en az 5 bağımsız örnek" **bu mekanizma için
toplanamadı: örnek sayısı 0.** Tek örnekten genelleme yapmamam istendi;
bu yüzden önceki setteki m4 tırmanış dizisini **kanıt olarak kullanmıyorum**
(§3.3'te yalnızca not olarak duruyor).

### 3.2 Analitik cevap: **azaltıyor, ve koşulsuz**

Bu, ölçüm gerektirmiyor — kodda tek satır:

```python
# gorev3_pickup.py:233
higher = alt + HOOK_REACQUIRE_CLIMB_M      # HOOK_REACQUIRE_CLIMB_M = 1.0  (:41)
await self.flight.goto_position_ned_and_hold(n0, e0, -higher, aligned_yaw, 3.0)
```

**Koşul yok, işaret seçimi yok, aşağı inen bir dal yok.** Yön her zaman
YUKARI. Üç deneme (`HOOK_REACQUIRE_MAX_CLIMBS = 3`, `:42`) → +3 m'ye kadar.

Görev G §2.4'teki kadraj tablosuyla birleştirince (f = 539.9 px, yük
0.14 × 0.05 m, kapı `HSV_MIN_AREA_RECT_BASE = 400 px²`):

| irtifa | yük alanı px² | 400 px² kapısına pay |
|---|---|---|
| 0.90 (hizalama) | 2519 | 6.3× |
| 1.50 (arama) | 907 | 2.3× |
| 1.90 (+1 m) | 566 | 1.4× |
| 2.20 | 421 | **1.05× — sınır** |
| 2.90 (+2 m) | 242 | **0.61× — REDDEDİLİR** |
| 3.90 (+3 m) | 134 | **0.34× — REDDEDİLİR** |

**Her tırmanış payı azaltır; ikinci tırmanıştan sonra yük alan kapısını
matematiksel olarak geçemez.** Yani mekanizma, tetiklendiğinde kendi amacını
imkânsız kılıyor: "göremiyorum, o hâlde daha az görünür hâle geleyim."

Altıgen aynı tırmanışta 3.9 m'de bile 277 px kalır (kapısı 800 px², alanı
çok daha büyük) — yani tırmanış **altıgeni korur, yükü öldürür.** Gözlenen
"altıgen var / yük yok" imzası bununla tutarlıdır.

### 3.3 Not — önceki setteki tek örnek (kanıt DEĞİL)

Önceki (geçersiz) setin m4 koşumunda mekanizma bir kez çalışmıştı:
3.6 → 6.4 → 9.1 m hedefleriyle üç tırmanış, üçünde de yük bulunamadı,
`FAIL#2` ile bitti. **n=1 ve karışık bir setten**, bu yüzden hükme
katmıyorum. Yönü ve sonucu §3.2 ile tutarlı olması dışında bir ağırlığı yok.

---

## 4 · FAIL#1 (r4b) — tespit arızası, tek örnek

Faz 1 10:12:01'de başladı, ilk arama penceresi 10:12:02–10:12:23.
**Pencerenin tamamında yalnızca `MAVI_ALTIGEN`** (7/7 heartbeat), hiç
`KIRMIZI_DIKDORTGEN` yok → `:480` FAIL#1.

Dikkat çekici: **28 saniye sonra**, araç bölgeden ayrılırken
(10:12:51, 10:12:54, 10:12:57) `KIRMIZI_DIKDORTGEN` **görüldü**. Yani yük
oradaydı ve tespit edilebilirdi — arama penceresinde edilemedi.

r4b'nin yük↔merkez mesafesi 0.178 m ile beşin **en büyüğü**, ama r5b 0.169 m
ile çok yakın ve onda tespit çalıştı (%35). **n=5 ile bu korelasyon
kurulamaz**; sadece not ediyorum.

Bu tek örnek H1'i desteklemiyor da çürütmüyor da: reacquire tetiklenmediği
için H1'in mekanizması hiç devreye girmedi.

---

## 5 · FAIL#3 — AYRI ARIZA, ve baskın olan bu (4/5)

**Kullanıcının istediği gibi H1'den ayrı raporlanıyor.**

`HOOK_SEATING_RESULT` olayı dört koşumda da `not_seated`. Üç denemenin
her birinde ~225 örnek. Kapı reddi dağılımı (r2b, temsili):

```
gate_rejections  {"too_high": 225, "lateral": 183, "rel_speed": 26}     deneme 1
                 {"too_high": 225, "lateral": 214, "rel_speed": 15}     deneme 2
                 {"too_high": 226, "lateral": 203, "rel_speed": 15}     deneme 3
```

**`too_high` örneklerin %100'ünü reddediyor — üç denemenin üçünde de.**

`best_simultaneous` (aynı anda en iyi örnek):

| deneme | lateral | **insertion** | tilt | rel_speed | başarısız kapı |
|---|---|---|---|---|---|
| 1 | 2.0 mm | **−202.7 mm** | 0.3° | 0.025 m/s | 1 |
| 2 | 5.0 mm | **−212.2 mm** | 0.4° | 0.034 m/s | 1 |
| 3 | 2.7 mm | **−210.6 mm** | 0.3° | 0.040 m/s | 1 |

Kapı: `SEAT_MIN_INSERTION_M = −0.004 m` (`hook_seating.py:134`).
Ölçülen **−0.21 m** — **iki mertebe dışarıda.**

Yani: **lateral hizalama aslında ÇOK İYİ** (min 1.9 mm; kapı ~10.25 mm),
**tilt %100 kapı içinde** (`"regime": "temiz"`, 225/225), ama **kanca
yuvaya hiç inmiyor.** `n_gate_ok_except_lateral: 0` de bunu söylüyor:
lateral'ı görmezden gelsek bile hiçbir örnek geçmiyor, çünkü insertion
tek başına düşürüyor.

### 5.1 Vinç, yeniden denemelerde uzamıyor

`winch_at_window_start.achieved_m` (r2b):

| deneme | komut | ulaşılan | kanca burnu z |
|---|---|---|---|
| 1 | 0.191 m | **0.329 m** | 0.163 m |
| 2 | 0.191 m | **0.0018 m** | 0.473 m |
| 3 | 0.191 m | **0.0018 m** | 0.473 m |

`payout_cmd_m == payout_sent_m == 0.191` — komut gönderiliyor, **ulaşılmıyor.**
1. denemeden sonra vinç toplu kalıyor ve kanca 47 cm yukarıda asılı duruyor.
2. ve 3. denemeler bu yüzden baştan kaybedilmiş durumda.

Dört koşumun `payout_m` değerleri: r1 0.138, r2b 0.191, r3b 0.127, r5b 0.124;
`altitude_m` sırasıyla 0.108 / 0.161 / 0.097 / 0.094. **Hiçbiri −4 mm
insertion kapısına yaklaşacak bir geometri üretmiyor.**

### 5.2 Görüntü ile gerçek arasındaki sapma (yan bulgu)

`[HIZA_KALIBRASYON]`, dördü de ~0.70–0.71 m irtifada:

| koşum | görüntü | gerçek | oran |
|---|---|---|---|
| r1 | 2.6 cm | 8.6 cm | 3.3× |
| r2b | 7.2 cm | 2.1 cm | 0.29× |
| r3b | 1.1 cm | 7.4 cm | 6.7× |
| r5b | 2.7 cm | 5.6 cm | 2.1× |

**Görüntü tahmini ile gerçek kanca pozu tutarlı biçimde ayrışıyor, ve
yönü bile sabit değil** (r2b'de görüntü büyük, diğerlerinde küçük).
Kodun kendi notu (`gorev3_pickup.py:634-641`) bunu 2026-08-23'te
fark etmiş ve "birkaç koşumun verisi sistematik sapma gösterirse
düzeltilir" demiş. **Dört koşum daha var artık ve sistematik DEĞİL —
rastgele.** Karar mercii zaten gerçek poz olduğu için Faz 1'i düşüren
bu değil; ama görüntü tabanlı hizalamanın bu irtifada **güvenilmez**
olduğu artık dört bağımsız örnekle kayıtlı.

---

## 6 · Sonuç ve öneri

1. **H1 kapatılmadı, yeniden konumlandırıldı.** `_reacquire_by_climbing()`
   koşulsuz yukarı gidiyor ve tetiklendiğinde kendi amacını imkânsız
   kılıyor — gerçek bir kusur, ama **5/5'te hiç tetiklenmedi**, yani
   şu anki başarısızlıkların nedeni değil. Düzeltilmesi gereken bir
   **gizli kusur** olarak kalır, acil değil.

2. **Asıl arıza FAIL#3 ve ölçüldü:** kanca yuvaya **~21 cm** yaklaşamıyor,
   `too_high` örneklerin %100'ünü reddediyor, ve vinç 2./3. denemelerde
   hiç uzamıyor. Lateral ve tilt zaten kapı içinde — sorun **dikey**.

3. **Sıradaki iş bu olmalı** (uygulama değil, ölçüm): vinç komutunun neden
   `achieved_m ≈ 0` döndüğü ve alma irtifasının (0.09–0.16 m) neden
   insertion kapısına 21 cm uzak kaldığı. `seat_trace` sütunları
   (`t_s, tilt_deg, lat_mm, ins_mm, winch_m, span_m, fold_deg`) bunun için
   gereken her şeyi zaten kaydediyor — **yeni log eklemeye gerek yok.**

4. **Ölçüm hijyeni artık kurulu:** `run_one_v2.sh` (scratchpad) her koşumda
   tam restart + port bekleme yapıyor ve bağımsızlığı `blue_hexagon`
   pozundan doğrulanabilir kılıyor. Sonraki setler bunu kullanmalı.

---

## 7 · Kapsam ve sınırlar

- 5 bağımsız koşum; FAIL#2 için **n=0**, FAIL#1 için **n=1**, FAIL#3 için **n=4**.
- `_reacquire_by_climbing()`'in davranışı **ölçülemedi** (hiç çalışmadı);
  §3.2'deki hüküm **koddan ve geometriden** türetildi, ölçümden değil.
- Faz 1 başarısızlığında gerçek irtifa telemetrisi (ULog) yine çekilmedi;
  §3.2 tablosu nominal irtifalara dayanıyor.
- Kod ve config **değiştirilmedi**; tüm sayılar mevcut log satırlarından
  ve `HOOK_SEATING_RESULT` olayından çıkarıldı.
