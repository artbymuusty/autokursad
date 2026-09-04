# GÖREV I / C — Rota irtifaları ve tarama deseni

**Tarih:** 2026-09-04 · **Kod/config değişikliği: YOK** (1way zaten doğru; 2way **engelli**)

---

## 1 · ONE-WAY: **zaten doğru, değişiklik gerekmedi** ✅

`Tools/simulation/gz/worlds/plans/competition_1way.plan` — 3 item,
**irtifa 15 m** (hepsi). `generate_competition_plans.py:63` → `ALT = 15`.
Spec'le **birebir uyuşuyor.**

Geometri: tek düz hat, X=0 merkez çizgisinde, Y −20 → +120 (LEADIN=20 ile
alanın iki ucundan da taşıyor).

---

## 2 · TWO-WAY: mevcut durum

`competition_2way.plan` — 10 item, **irtifa 15 m** (spec 10 m diyor).

Ölçülen geometri (home'a göre X/Y):

| seq | X | Y |
|---|---|---|
| 1 | **+7.25** | +5.00 |
| 2 | **+7.25** | +138.00 |
| 3–7 | yarım daire yay (X +6.28 → −6.28, tepe Y=+145.25) |
| 8 | **−7.25** | +138.00 |
| 9 | **−7.25** | +5.00 |

- İki şerit, **X = ±7.25** → şerit aralığı **14.50 m**
- Kuzey ucunda **yarım daire yay** ile dönüş (fren mesafesi için, `ARC_OFFSET = 13`)
- Alan X ∈ [−15, +15] olduğuna göre şeritler kenarlardan **7.75 m** içeride

**F2-a bulgusuyla tutarlı mı: EVET.** Canlı `ROUTE_AXIS_DETECTED`
olayı `lat_span = 0.001260°` (≈140 m) / `lon_span = 0.000193°` (≈14.5 m)
diyor — "lat_span ≫ lon_span, iki şerit" bulgusu **birebir doğrulandı.**

---

## 3 · ⛔ SERT ENGEL — 2way'i 10 m'ye indirmek Görev 2'yi ÇALIŞMAZ HALE GETİRİR

`core/detection/target_validator.py:32`:
```python
self._altitude_ok[shape] = abs(current_altitude_m - target_altitude_m) < 0.5
```
ve `:20` — `target_altitude_m: float = MISSION_ALTITUDE_M` (**varsayılan
argüman**, `parameters.py:9` = **15.0**).

Tek çağıran (`gorev2_orchestrator.py:740`):
```python
self.validator.update(d, current_alt, frame_center)   # target_altitude_m VERILMIYOR
```

**Sonuç:** rota 10 m'de uçarsa `|10 − 15| = 5.0 > 0.5` → `altitude_ok`
**kalıcı olarak False** → `is_track_ready()` hiç True olmaz →
Mission→Offboard devri hiç tetiklenmez → **hiçbir hedef kaydedilmez.**

Bu, `generate_competition_plans.py:24-31`'de zaten yazılı bir uyarı:
*"12 m'lik bir rotayla Görev 2'nin başarılı olması yapısal olarak
imkânsızdır."* Aynı şey 10 m için de geçerli.

**Yani "2way = 10 m" tek başına bir rota-üretim değişikliği DEĞİL** —
irtifa kapısının **rota-farkında** hale gelmesini gerektiriyor.

---

## 4 · Doğru katman sorusu (spec'in sorduğu)

Değişiklik **iki katmana birden** dokunmak zorunda:

| katman | ne değişir |
|---|---|
| `generate_competition_plans.py` | `ALT` artık tek sabit olamaz; rota başına irtifa |
| `parameters.py` + `target_validator` + `gorev2_orchestrator` | kapı, o an yüklü rotanın irtifasını bilmeli |

Bugün `MISSION_ALTITUDE_M` **tek global** ve hem tırmanış hedefi
(`_wait_for_altitude`) hem tespit kapısı olarak kullanılıyor.

---

## 5 · Kamera kapsaması — spec'in şerit genişliğiyle karşılaştırma

f = 539.9 px (hfov 1.74, 1280×960):

| irtifa | kadraj | alan genişliği 30 m |
|---|---|---|
| 10 m | **23.7 × 17.8 m** | tek geçiş alanın %79'unu kaplar |
| 15 m | **35.6 × 26.7 m** | tek geçiş **tamamını** kaplar |

**Spec'in 10 m'lik şerit genişliği, 10 m irtifadaki kamera ayak izinden
(23.7 m) 2.4 kat DAR.** Yani optik olarak gerekenden fazla şerit
öneriliyor. Mevcut 14.50 m aralık da 23.7 m'den dar, yani bugün de
örtüşme var.

---

## 6 · ❓ CEVAP GEREKTİREN İKİ SORU

**C1 — İrtifa kapısı rota-farkında mı olsun?**
2way'i 10 m'ye indirmek için `MISSION_ALTITUDE_M`'in tek global olmaktan
çıkması gerekiyor. İki seçenek:
- **(a)** Yüklü rotadan okunan irtifa kapıya beslensin (`validator.update`
  çağrısına gerçek hedef irtifa geçsin). Doğru çözüm ama **Görev 2'nin
  çekirdek kapısına** dokunuyor.
- **(b)** `MISSION_ALTITUDE_M` 10'a çekilsin ve **1way de 10 m** olsun.
  Tek sayı, düşük risk — ama spec "1way 15 m" diyor, yani spec'e aykırı.

Hangisi?

**C2 — Şerit deseni tam olarak ne?**
"Kenardan 10 m içeride, 10 m yana dön" iki farklı okunuşa açık:
- **(i)** 2 şerit, X = **−5 ve +5** (her kenardan 10 m içeride, aralarında
  10 m). Kamera ayak iziyle alanın tamamı zaten kapanır.
- **(ii)** 3 şerit, X = **−10, 0, +10** (10 m şerit genişliğiyle 30 m'yi
  tam bölme). "Kalan alanı da kapla" cümlesi buna işaret ediyor olabilir.

Ayrıca: kuzey ucundaki **yarım daire yay** korunacak mı? O yay fren
mesafesi için konmuş (`ARC_OFFSET = 13 m`); keskin 10 m'lik yana kayma
onun yerine geçerse fren davranışı değişir.

---

## 7 · Bu turda yapılan

- 1way irtifası **kontrol edildi, doğru, dokunulmadı.**
- 2way'in mevcut geometrisi **ölçüldü ve F2-a bulgusuyla doğrulandı.**
- 10 m'ye inişin **sert engeli belgelendi** — uydurma bir çözüm
  üretilmedi, C1/C2 soruldu.
