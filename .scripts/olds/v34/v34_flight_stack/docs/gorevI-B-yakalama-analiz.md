# GÖREV I / B — "Yakalama penceresine hiç girilmedi" teşhisi

**Tarih:** 2026-09-04 · **Tip:** analiz · **Kod değişikliği: YOK**
**Veri:** B2 koşumu (`5bb4c436` sonrası, 3 deneme, tam olay + `[HOOK]` izi)

---

## TEŞHİS — tek cümle

**Kanca yakalama yarıçapına hiç girmedi çünkü oturma kapısı YANLIŞ YÜKE
bakıyordu.** Ölçülen lateral hata **35 497 mm ≈ 35.5 m** ve bu, o koşumda
iki yük arasındaki mesafenin **birebir kendisi** (35.5 m).

```
[HOOK] APPROACHING  lat=35497.3mm  ins=-379.1mm  tilt=0.5deg  v=inf m/s
                    [lateral(35497.3mm>17.5mm), gap(...)]

B2 sahası:  KIRMIZI_UCGEN yükü (7.342, 51.649)
            MAVI_ALTIGEN  yükü (1.361, 86.659)
            aradaki mesafe = 35.5 m          ← ölçülen lateral ile AYNI
```

**Kök neden:** `gz_payload_actuator.py:1630` ve `:1739`

```python
color = SHAPE_TO_COLOR["MAVI_ALTIGEN"]        # payload_red
```

Bu koşumda alma hedefi **KIRMIZI_UCGEN**'di (üçgen önce bırakıldı), yani
alınacak yük **mavi**. Araç doğru yükün üzerinde duruyordu; kapı ise
35.5 m ötedeki **kırmızı** yükü ölçüyordu.

### Bu benim açık bıraktığım bir uçtu

A maddesinin commit mesajında **kendim not düşmüştüm**:

> *"NOT (B'ye devredilen): gz_payload_actuator icinde hala iki sabit var --
> :1603 ve :1712 SHAPE_TO_COLOR["MAVI_ALTIGEN"]. Aktuator ici yol B
> maddesinde zaten yeniden ele alinacak."*

B'yi yaparken **o notu kapatmadım.** Görüş tarafındaki altı sabiti ve
stratejiyi dinamikleştirdim, aktüatör tarafındaki ikisini atladım.

---

## Sorulara tek tek cevap

### 1 · Yarıçapa hiç girmedi mi, girip kalamadı mı?

**Hiç girmedi.** Lateral 35 497 mm, kapı 17.5 mm → **2 028 kat** dışarıda.
Bu bir dwell sorunu değil; `MAGNET_DWELL_S` hiç devreye girmedi çünkü
`CAPTURE_CANDIDATE` durumuna bir kez bile geçilmedi (tüm örnekler
`APPROACHING`).

`HOOK_SEATING_RESULT` olayı hiç yayınlanmadı — çünkü dış bütçe, oturma
penceresi bitmeden denemeyi kesti (§3). Bu yüzden `seat_trace` zaman
serisi yok; kanıt doğrudan `[HOOK] APPROACHING` satırlarından.

### 2 · Sarkaç genliği ile yarıçap ilişkisi

**İlişkisiz — sarkaç bu tabloda hiç rol oynamıyor.** Ölçülen genlik
~60 mm mertebesinde; buradaki hata **35 500 mm**. Aradaki fark **üç
büyüklük mertebesi**. Kanca, kapının izlediği hedefin yakınına hiç
gelmedi; salınımın 17.5 mm'lik pencereye girip girmediği sorusu bu
veriyle **sınanamadı bile**.

### 3 · Yeni CAD mi, hover-kilit hassasiyeti mi?

**İkisi de değil.**
- Yeni geometri (25 cm kanca, Ø35 mm mıknatıs) **suçsuz**: eğim 0.4–0.8°
  (kapı 8°), hız çoğunlukla < 0.04 m/s (kapı 0.05). Mekanik davranış
  sağlıklı görünüyor.
- Hover-kilit **çalıştı**: `[GORSEL_HIZA] yakınsadı: 18.7 mm, 5 iterasyon`
  ve yuva görüntüden NED=(76.659, 7.318) olarak ölçüldü.

Sorun konumlandırmada değil, **hangi nesnenin ölçüldüğünde.**

### 4 · `approach_recentered converged=True` güvenilir mi?

**Bu koşumda EVET, ve Ö5'teki durumdan farklı.**

Ö5'te `relative_altitude_m` gerçeği yanlış raporluyordu — "yakınsadı"
damgası bozuk bir ölçüme dayanıyordu. Burada öyle bir şey yok: araç
gerçekten doğru yükün üzerine yakınsadı (görsel hizalama 18.7 mm'ye indi
ve yuvayı NED'de ölçtü). **Tutarsız olan damga değil, kapının baktığı
nesne.**

Yani: iki farklı hata sınıfı, karıştırılmamalı.

---

## 3 · İKİNCİ VE BAĞIMSIZ BULGU — 60 s bütçesi tutmuyor

Renk hatası düzeltilse bile bu ayrıca sorun:

| deneme | yaklaşma | ikinci ortalama | **görsel blok** | düzeltme | **dikey iniş** | yakalama penceresi |
|---|---|---|---|---|---|---|
| 1 | 5.1 s | 0.8 s | **14.1 s** | 5.0 s | **17.5 s** | **11.5 s** |
| 2 | 5.1 s | **16.2 s** | **34.8 s** | — | — | **0 s (hiç girilmedi)** |
| 3 | 5.0 s | 2.6 s | **18.6 s** | 4.0 s | **16.1 s** | **7.5 s** |

**S5'te türettiğim iç dağılım gerçekle uyuşmuyor:**

| kalem | S5 varsayımı | **ölçülen** |
|---|---|---|
| vinç salımı + sönümleme | 4 s | (görsel bloğa gömülü) |
| yaklaşma irtifasına iniş | 6 s | **5.0–5.1 s** ✓ |
| görsel blok (ortalama + hizalama) | *bütçede yok* | **14.1–34.8 s** ❌ |
| dikey iniş | *bütçede yok* | **16.1–17.5 s** ❌ |
| **yakalama penceresi** | **30 s** | **0–11.5 s** ❌ |
| doğrulama | 15 s | hiç sıra gelmedi |

Yani 60 s'nin **48.5–56.1 s**'i yakalamadan ÖNCE tükeniyor. Yakalama
penceresi tasarlanan 30 s'nin **dörtte birini bile** almıyor, 2. denemede
hiç açılmıyor.

**Not:** `HOOK_REACQUIRE_STEP` iki kez tetiklendi (`tavan_altinda`,
0.306 → 1.306 m, tavan 1.737 m). H1'de eklediğim tavan koruması canlıda
**ilk kez çalıştı ve doğru yönde davrandı** — ama her tetiklenme görsel
bloğa saniyeler ekliyor, yani bütçe baskısının bir parçası.

---

## Öneri (uygulanmadı, onay bekliyor)

**Ö-A (zorunlu, küçük):** `gz_payload_actuator`'daki iki sabit
(`:1630`, `:1739`) alma hedefinin renginden türetilsin. `activate_pickup_mechanism`
zaten `altitude_m`/`on_retry` alıyor; renk de parametre olarak geçmeli.
Bu, A maddesinin kapatılmamış son ucu.

**Ö-B (bağımsız, bütçe):** S5'in iç dağılımı **ölçülen** sürelerle yeniden
türetilmeli. Seçenekler: (i) 60 s'yi büyüt, (ii) görsel bloğu kısalt
(ör. `HOOK_ALIGN_MAX_CORRECTIONS` düşür), (iii) dikey inişin 16 s'sini
incele — `goto_position_ned_and_hold(..., 6.0)` çağrılıyor ama 16 s
sürüyor, aradaki fark açıklanmadı.

**Sıra önerim: önce Ö-A** (tek satırlık kök neden), sonra düzeltilmiş
koşumla bütçeyi yeniden ölç — çünkü renk düzelince yakalama penceresinde
ne olduğunu ilk kez göreceğiz ve Ö-B'nin sayıları o veriye göre
türetilmeli.

---

## Kapsam

- Tek koşum (B2), 3 deneme. Kök neden **deterministik** (sabit kod yolu),
  tekrar için ek koşuma gerek yok.
- `seat_trace` zaman serisi **yok** — oturma penceresi hiç tamamlanmadı,
  o alan yalnızca `HOOK_SEATING_RESULT` ile yayınlanıyor.
- Ö-B'nin sayıları bu koşumdan; renk düzeltilince yeniden ölçülmeli.
