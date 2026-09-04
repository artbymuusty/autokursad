# GÖREV I — Ö-A sonucu ve Ö-B bütçesinin GERÇEK ölçümden türetilmesi

**Tarih:** 2026-09-04 · **Ö-A commit:** `8dd1f2a5` · **Koşum:** C1 · **Push edilmedi**

---

## 1 · Ö-A tuttu — kapı artık doğru yükü ölçüyor

| | B2 (öncesi) | **C1 (sonrası)** |
|---|---|---|
| alma hedefi | KIRMIZI_UCGEN | KIRMIZI_UCGEN |
| yük rengi | (sabit `red` ❌) | **`blue`** ✅ `source: interlock.first_released` |
| ölçülen lateral | **35 497 mm** | **7.9 – 36.9 mm** |

**4 500 kat düzeldi.** Kapı ilk kez gerçek yükü görüyor.

---

## 2 · Fizik ilk kez görünür oldu — ve engel DİKEY

C1'in yakalama örnekleri (n=10):

| büyüklük | min | ortanca | max | kapı | geçen |
|---|---|---|---|---|---|
| **lateral** | 7.9 mm | 24.9 mm | 36.9 mm | 17.5 mm | **4/10** |
| **eksenel boşluk** | **61.3 mm** | 65.3 mm | 151.7 mm | **5.0 mm** | **0/10** |
| tilt | — | — | 0.6° | 8.0° | 10/10 ✓ |
| hız | — | — | — | 0.05 m/s | 4/10 |
| **ikisi birden** | | | | | **0/10** |

### Sorulara cevap

**Capture radius'a giriyor mu?** **Evet, 4/10 örnekte** (min 7.9 mm).
Lateral artık gerçekçi bir mesafede salınıyor.

**`CAPTURE_CANDIDATE`'a geçildi mi?** **Hayır** — 10 örneğin 10'u
`APPROACHING`. Sebep lateral değil: **kanca 6–15 cm YÜKSEKTE.** Eksenel
boşluk kapısını (5 mm) hiçbir örnek geçmiyor.

**Dwell (0.50 s) yeterli mi?** **Sınanamadı.** Dwell ancak tüm kapılar
aynı anda sağlandığında saymaya başlar; hiçbir örnek o noktaya gelmedi.
Dwell'in yeterliliği hakkında bu veriyle **hüküm verilemez.**

> Yani engel B2'dekiyle aynı sınıfta değil: orada kapı **yanlış nesneyi**
> ölçüyordu; burada doğru nesneyi ölçüyor ve **kanca gerçekten yetişmiyor.**
> Bu, Görev G'de ölçtüğümüz erişim açığının yeni geometrideki karşılığı.

---

## 3 · `goto_position_ned_and_hold(..., 6.0)` neden 16 s sürüyor —
## **SÜRMÜYOR. Etiketleme hatası bendeydi.**

Kodu okudum (`mavsdk_backend_base.py:403-417`):

```python
deadline = now + duration_s
while now < deadline:
    await set_position_ned(setpoint)
    await sleep(OFFBOARD_SETPOINT_INTERVAL_S)
```

**Varışı BEKLEMİYOR** — setpoint'i tam `duration_s` boyunca yayınlayıp
dönüyor. Yani `6.0` tam 6.0 s'dir.

C1 ölçümü bunu doğruluyor: `vertical_descent_start → pickup_attempt_start`
= **6.1 s**, ve `BAŞLA → approach_altitude_reached` = **5.0–5.1 s**
(hold 5.0). İkisi de birebir.

**B2 raporundaki "dikey iniş 16 s" satırı YANLIŞTI:** o 16 s
`correction_airborne_start → vertical_descent_start` aralığıydı, yani
`_settle_hook_onto` (kapalı çevrim kanca oturtma) — dikey iniş değil.
Adım adlarını yanlış eşleştirmişim. **Tutarsızlık kapandı; kodda bir
anomali yok.**

---

## 4 · Ö-B — bütçenin GERÇEK ölçümden yeniden türetilmesi

C1, 3 deneme (doğru etiketlerle):

| adım | ölçülen | S5 varsayımı |
|---|---|---|
| yaklaşma inişi (hold 5.0) | **5.0–5.1 s** | 6 s |
| ikinci ortalama | **0.4–5.7 s** | *yok* |
| **görsel blok** (`_rect_pixel_offset` + reacquire + `VisualHookAligner`) | **21.2–32.1 s** | *yok* |
| vinç salımı + sönümleme (`HOOK_PAYOUT_SETTLE_S`=4) | **4.0–5.1 s** | 4 s ✓ |
| **`_settle_hook_onto`** (kapalı çevrim) | **10.9–15.7 s** | *yok* |
| dikey iniş (hold 6.0) | **6.1 s** | *yok* |
| **yakalama penceresi** | **1.4–6.5 s** | **30 s** |
| doğrulama tırmanışı | hiç sıra gelmedi | 15 s |

**Ön hazırlık 53.5–58.6 s**, yani 60 s'nin neredeyse tamamı.

### Gerçek bütçe ne olmalı (p90 değerlerle)

```
yaklaşma inişi          5 s
ikinci ortalama         6 s
görsel blok            32 s
vinç + sönümleme        5 s
_settle_hook_onto      16 s
dikey iniş              6 s
YAKALAMA PENCERESI     30 s     ← tasarlanan
doğrulama              15 s
pay                     5 s
                    -------
                      120 s / deneme
```
3 deneme = **360 s**. Görev 2 ölçülen ~215 s + 360 = **575 s**, 600 s
bütçenin kenarında; taşıma/bırakma/finish'e yer kalmaz.

### Üç seçenek (hiçbiri uygulanmadı)

| # | ne | kazanç | risk |
|---|---|---|---|
| **B1** | Görsel bloğu kısalt: `HOOK_ALIGN_MAX_CORRECTIONS` 6 → 3, reacquire'ı denemeye 1 ile sınırla | ~15 s/deneme | hizalama hassasiyeti düşebilir |
| **B2** | `_settle_hook_onto`'yu yakalama penceresinin İÇİNE al — zaten aynı işi yapıyor (kancayı yuvaya sürüyor), ayrı bütçe tutması gereksiz | ~16 s/deneme | orta; iki mekanizma birleşir |
| **B3** | Deneme sayısını 3 → 2 indir | 1 deneme | spec'e aykırı, **önermiyorum** |

**B1 + B2 birlikte:** deneme ~89 s, 3 deneme 267 s, toplam ~482 s —
sığar. Ama **ikisi de ölçülmemiş varsayım içeriyor**; uygulanırsa
her biri ayrı ölçülmeli.

---

## 5 · Yan doğrulama (bu turun odağı değil)

`HOOK_REACQUIRE_STEP` B2'de **iki kez** tetiklendi:
`tavan_altinda`, 0.306 → 1.306 m, tavan 1.737 m, yön **yukarı**.
H1'de eklediğim tavan koruması **canlıda ilk kez çalıştı ve doğru yönde
davrandı** — tavanın altındayken yükselmeye izin verdi, tavanı aşmadı.

---

## 6 · Açık kalan — B'nin kapanması için

1. **Eksenel açık 61–152 mm** (kapı 5 mm). Bu, Görev G'nin erişim
   probleminin yeni geometrideki hâli. **Henüz teşhis edilmedi.**
2. Bütçe: §4'teki seçeneklerden biri seçilmeli.
3. Dwell'in yeterliliği **hâlâ sınanmadı** (kapılar aynı anda hiç
   sağlanmadı).

## Kapsam

- Tek koşum (C1), 3 deneme, 10 yakalama örneği. Yakalama penceresi
  1.4–6.5 s olduğu için örnek sayısı **az** — lateral/boşluk dağılımı
  bu kadarla kesin değil.
- Ö-A'nın düzeltmesi **deterministik** (sabit kod yolu), tekrar gerekmez.
