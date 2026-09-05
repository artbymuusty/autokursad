# GÖREV O — FAZ 1: settle noktasındaki yanal hata neden 1.9–217 mm arasında değişiyor?

**Tarih:** 2026-09-05 · **Kod değişikliği YOK** (salt analiz)
**Veri:** 6 canlı koşum, 18 deneme — `demo_20260905_172017 / _173708 / _175429 / _180754 / _183335 / _191120`

---

## KESİN TEŞHİS

> **Değişkenliğin kaynağı görsel hizalama DEĞİL.** Görsel hizalama her
> koşumda 7.8–26.0 mm'ye yakınsıyor ve damgası dürüst. Hata, hizalamadan
> SONRA, **inişin başlangıç irtifası hakkındaki yanlış bir varsayımdan**
> doğuyor: `_adaptif_descend` her zaman aracın 0.90 m'de olduğunu varsayıyor,
> ama araç orada olmasını **yalnızca `_settle_hook_onto` koştuğunda**
> sağlıyor. Adım atlandığında araç 0.30 m'de kalıyor ve inişin ilk "adımı"
> **0.30 m'lik bir TIRMANIŞ** oluyor — sarkacı uyandıran şey bu.

**Bu benim Görev K'da soktuğum bir kusur.** `_settle_hook_onto`'yu
kaldırırken yalnızca ilan edilmiş işine (yanal hatayı kapatmak) baktım;
sessizce yaptığı diğer iki işi kontrol etmedim.

---

## 1 · KANIT — korelasyon kusursuz (18 deneme)

| koşum/deneme | `_settle_hook_onto` | **iniş öncesi irtifa** | kanca ofseti (kuzey) | **ilk iniş yanalı** |
|---|---|---|---|---|
| 172017/1 | koştu | 0.898 m | −0.0902 | 34.9 mm |
| 173708/1 | koştu | 0.899 m | −0.0893 | 38.3 mm |
| 173708/2 | koştu | 0.896 m | −0.0917 | 11.4 mm |
| 180754/1 | koştu | 0.860 m | −0.0901 | 10.3 mm |
| 180754/2 | koştu | 0.899 m | −0.0897 | 59.8 mm |
| 191120/1 | **KOŞULUYOR** | 0.897 m | −0.0919 | **8.1 mm** |
| 191120/3 | **KOŞULUYOR** | 0.898 m | −0.0903 | **12.2 mm** |
| **183335/1** | **ATLANDI** | **0.305 m** | **−0.0513** | — |
| **183335/3** | **ATLANDI** | **0.301 m** | **−0.2412** | **179.2 mm** |
| **191120/2** | **ATLANDI** | **0.304 m** | **−0.2318** | **207.7 mm** |

**İstisnasız:** adım koştuğunda araç ~0.90 m'de ve kanca **şakulde**
(−0.090, SDF'deki `hook_mount` x = −0.090); atlandığında araç ~0.30 m'de ve
kanca **142–151 mm sarkmış**. İlk iniş yanalı sırasıyla 8–60 mm ve
179–208 mm.

---

## 2 · `_settle_hook_onto` ÜÇ İŞ yapıyordu — ikisi görünmezdi

| # | iş | kaldırılınca ne oldu |
|---|---|---|
| **a** | Yanal hatayı kapat *(ilan edilmiş amaç)* | Yerini mıknatıs aldı — **bu kısım doğruydu** |
| **b** | **Sarkacı söndür** — 3 düzeltme × 2.5 s bekleme = **7.5 s** | Söndürme kalmadı. `HOOK_PAYOUT_SETTLE_S = 4.0` tek başına yetmiyor: ölçülen sarkaç periyodu **1.078 s** (Görev J), 4 s ≈ 3.7 periyot |
| **c** | **Aracı 0.90 m'ye geri uçur** — `_settle_hook_onto(..., HOOK_VISUAL_ALIGN_ALTITUDE_M)` | İnişin varsaydığı irtifa artık gerçek değil ⇒ ilk adım **tırmanış** |

**(c) belirleyici olan.** `_adaptive_descend(..., HOOK_VISUAL_ALIGN_ALTITUDE_M)`
sabit 0.90 alıyor (`gorev3_pickup.py:1848`). Araç 0.304 m'deyken ilk adım
`0.900 − 0.300 = 0.600` komut ediyor — **+0.296 m tırmanış**, üstelik
"SAF DIKEY, KADEMELI iniliyor (yanal hareket yok)" diye loglanarak.

**(b) ikinci katkı.** Atlanan denemelerde kanca ofseti −0.232/−0.241; şakul
−0.090. Fark **142–151 mm** ve işareti ARKAYA doğru — ADIM 5'in gövde-ileri
**+0.175 m** ötelemesinin gecikmesi. Yani kanca, ölçüm anında hâlâ o
ötelemeden **sallanıyor**.

---

## 3 · Soru 2 — "converged" damgası yalan söylüyor mu? **HAYIR, ama ilgisiz**

| koşum/deneme | görsel damga | settle yanalı |
|---|---|---|
| 183335/1 | converged **13.3 mm** | **217.1 mm** |
| 183335/3 | converged **8.9 mm** | **1.9 mm** |
| 191120/1 | converged **18.4 mm** | **161.0 mm** |
| 191120/2 | converged **19.1 mm** | **32.8 mm** |
| 191120/3 | converged **18.9 mm** | **18.9 → 161.6 mm** |

Damga **7.8–26.0 mm** bandında sabit; settle yanalı **1.9–217 mm**.
**Korelasyon yok (damga sabit, sonuç 100 kat değişiyor).** Ö5'teki
"yakınsadı damgası güvenilmez olabilir" riski burada **gerçekleşmemiş**:
damga kendi ölçtüğü şey hakkında dürüst. Sorun, **ölçtüğü şeyin sonucu
yordamaması** — arada sarkaç ve irtifa değişimi var.

---

## 4 · Soru 3 — EKF irtifa hatasının payı: **mekanizma GERÇEK, ama baskın DEĞİL**

`_rect_pixel_offset` piksel→metre çevriminde **EKF irtifasını** kullanıyor
(`gorev3_pickup.py`, `get_global_position()`):
```
want_y = res_h/2 + HOOK_BODY_OFFSET_FORWARD_M * focal / alt
donen  = hypot(dx, dy) * alt / focal
```
İkisi de `alt` ile **doğrusal** ölçekleniyor ⇒ irtifa hatası doğrudan yanal
tahmine geçiyor.

Ölçülen `[HIZA_KALIBRASYON]` (görüntü / gerçek, 9 örnek):
`3.4/2.2 · 4.3/6.7 · 1.2/2.8 · 3.0/1.8 · 7.6/8.4 · 6.1/4.0 · 4.8/6.5 · 4.3/5.0 · 17.3/17.6 cm`
⇒ oran **0.43 – 1.67**, yani **−57% … +67%** sapma.

**Hüküm:** sapma gerçek ve küçümsenemez, ama mutlak değerler 1–8 cm
mertebesinde olduğu için katkısı **santimetre**. Kovaladığımız **150–200 mm**
bundan gelmiyor. İkincil bir terim; §2'yi düzeltmeden ölçmek de anlamsız,
çünkü büyük terim onu maskeliyor.

---

## 5 · Soru 4 — iniş sırasında yanal düzeltiliyor mu? **HAYIR**

`_adaptive_descend_loop` her adımda **aynı** `n_ned, e_ned` ile komut
veriyor; yanal hiç güncellenmiyor. Tek yanal mekanizma, `gap ≤ 50 mm` **ve**
`lateral > 17.5 mm` iken tetiklenen mıknatıs bandı.

İniş boyunca yanalın gezinmesi (ölçüldü):
```
180754/2:  59.8 → 80.0 → 64.2 → [bant 71.2→85.8→110.9] → 110.6 → 102.3 mm
183335/3: 179.2 → 183.5 → 148.8 → [bant 166→148.8, 149.2→178.4] → 178.4 → 166.1 mm
191120/1:   8.1 →  28.0 →  23.3 → [bant 30.1→54.7] mm
```
**Yanal, iniş sırasında serbestçe gezinıyor** — bazı adımlarda 20 mm, bazen
30 mm. Bant iki kez düzeltti, dört kez **bozdu**.

---

## 6 · Soru 1 — sıra hâlâ doğru mu? **İKİ TUTARSIZLIK VAR**

**(i) Görsel hizalama 0.90 m'de değil, 0.30 m'de koşuyor.**
Faz önce 0.90'a çıkıp savunmacı bir tutuş yapıyor, sonra
`aligner.align(GOREV3_APPROACH_ALTITUDE_M, …)` çağırıyor — ve `align`
her düzeltmede `goto_ned_and_hold(n, e, **altitude_m**, yaw)` ile
**0.30 m** komut ediyor (`visual_alignment.py:394`). Çevredeki yorumlar
("Zaten hizalama irtifasindayiz") **0.90 diyor**; kod 0.30 uyguluyor.

**(ii) `_settle_hook_onto`'nun kendi gerekçesi kendi irtifasında geçersiz.**
Docstring'i "vinç açık ve her düzeltme **DİNLENEN** kancayı güverte üzerinde
sürüklüyor" diyor. Ama 0.90 m'de, 0.33 m salımla kanca **0.61 m'de,
havada** — dinlenmiyor. Yani adım, kendi belgelendiği rejimin dışında
çalışıyor.

---

## 7 · Özet — hangi adımda, hangi mekanizma

| katkı | büyüklük | kanıt |
|---|---|---|
| **1. İnişin yanlış başlangıç irtifası** ⇒ ilk adım tırmanış | **~180–210 mm** | 3/3 atlanan denemede; 0/7 koşan denemede |
| **2. Sarkacın sönmemesi** (öteleme + salım, 4 s yetmiyor) | **142–151 mm** | kanca ofseti −0.232/−0.241 vs şakul −0.090 |
| 3. İniş sırasında yanalın düzeltilmemesi | ~20–30 mm/adım | iniş adımlarındaki gezinme |
| 4. Mıknatıs bandının bazen bozması | ±15–29 mm | 6 bantın 4'ü negatif |
| 5. EKF irtifa hatası → piksel/metre | ~santimetre | görüntü/gerçek oranı 0.43–1.67 |
| — | | |
| **görsel hizalamanın kendisi** | **7.8–26.0 mm** | **sorun DEĞİL** |

---

## 8 · İmplementasyona geçmeden — öneri (uygulanmadı)

1 ve 2, tek bir yerden çıkıyor: **inişten önce aracın irtifası ve kancanın
şakulde olması VARSAYILIYOR, ölçülmüyor.** En küçük ve doğrudan düzeltme
`start_alt_m`'i sabit vermek yerine **ölçmek** (`_current_alt_m()`) ve
kancanın şakule dönmesini **ölçerek** beklemek olur — ikisi de zaten var
olan ölçümler. Bu, `_settle_hook_onto`'yu geri getirmeden (b) ve (c)'yi
kurtarır.

**Karar operatöre bırakıldı; hiçbir kod değiştirilmedi.**
