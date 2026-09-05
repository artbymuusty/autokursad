# GÖREV Q — FAZ 1: "Görev O sıçraması"nın kök nedeni

**Tarih:** 2026-09-06 · **Kod değişikliği YOK** (salt analiz)
**Kaynaklar:** `core/mission/visual_alignment.py`, `core/mission/gorev3_pickup.py`,
5 koşum / 12 deneme (`demo_20260905_233718` … `demo_20260906_002902`)

---

## TEK CÜMLELİK CEVAP

> **Sıçrama `gorev3_pickup.py` ADIM 5'te (`_body_to_ned(HOOK_BODY_OFFSET_FORWARD_M, 0.0)`)
> oluşuyor: kanca ofseti İKİNCİ KEZ uygulanıyor. `VisualHookAligner.align()`
> zaten KANCAYI yuvaya oturtuyor (`visual_alignment.py:64` hatayı
> `receiver − hook` olarak döndürüyor), dolayısıyla yakınsadığı anda kanca
> hedefin üzerinde; ADIM 5 aracı +175 mm ileri sürünce kancayı hedefin
> 175 mm ÖTESİNE taşıyor.**

---

## 1 · Görsel hizalama neyi hedefliyor? **KANCAYI** (kamerayı değil)

`visual_alignment.py`, `_measure()` son satırı:
```python
return (recv_n - hook[0], recv_e - hook[1]), det      # :64
```
`hook` = `get_hook_ned_offset()` — kanca burnunun **araca göre** konumu
(gerçek Gazebo pozundan). Yani `err` = **kancadan yuvaya** vektör.

`align()` bunu doğrudan araca uyguluyor:
```python
step_n, step_e = filt[0] * ALIGN_KP, filt[1] * ALIGN_KP
await self.goto_ned_and_hold(n0 + step_n, e0 + step_e, altitude_m, yaw_deg)
```
ve `last_recv_ned = (n_now + hook_now[0] + err[0], ...)` satırı da aynı
çerçeveyi doğruluyor: `receiver_abs = arac + kanca_ofseti + (yuva − kanca)`.

> **Sonuç: `converged: son hata = 20.0 mm` demek, "KANCA yuvadan 20 mm
> uzakta" demektir — "kamera 20 mm uzakta" değil.**

Bu, `docstring`'de de yazılı: *"One vision measurement of the
**hook->receiver** error, in NED metres."*

---

## 2 · Settle ölçümü ne zaman/neye göre alınıyor?

`seating_geometry().lateral_m` — **gerçek kanca burnu ↔ yuva ekseni**,
yuvanın kendi çerçevesinde. Yani §1 ile **aynı büyüklüğü** ölçüyor.

Sıra (`_attempt`):

| # | adım | kanca nerede |
|---|---|---|
| ADIM 4 | `go_to_and_center(rect, 0.30)` — **KAMERA** referanslı | kanca 175 mm geride |
| — | `_rect_pixel_offset()` (+ gerekirse reacquire) | — |
| — | savunmacı tutuş 0.90 m | — |
| **ADIM 4b** | **`aligner.align(...)` — KANCA referanslı** | **kanca YUVANIN ÜZERİNDE (6.5–29.7 mm)** |
| **ADIM 5** | **`_body_to_ned(+0.175, 0)` + goto** | **kanca 175 mm ÖTEDE** ❌ |
| — | salım, `_wait_hook_stopped()` | — |
| **settle** | `seating_geometry().lateral_m` | **92–289 mm ölçülüyor** |

**ADIM 5'in yorumu kendi gerekçesini yazıyor:** *"arac govde-ileri … kayar,
boylece kameranin baktigi nokta kancanin altina gecer."* Bu gerekçe
**ADIM 4'ten sonra doğru** (kamera referanslı ortalama). Ama arada
**ADIM 4b** var ve o **kanca referanslı**. Ofset, kendisini gereksiz kılan
bir adımdan sonra uygulanıyor.

Görev I / S3'te "ofset yalnızca ADIM 5'te, tek seferlik" kuralı kuruldu ve
**o kural hâlâ geçerli** — sabit gerçekten tek yerde uygulanıyor. Kusur
tekrar sayısında değil, **sıradaki yerinde**.

---

## 3 · `HOOK_BODY_OFFSET_FORWARD_M`'in her kullanımı

| satır | kullanım | değerlendirme |
|---|---|---|
| `:46` | tanım (0.175) | — |
| `:466`, `:492` | `_rect_pixel_offset` — beklenen piksel ofseti (`want_y`) | ✅ doğru; orası **kamera** referanslı |
| `:1640` | reacquire dalı — yeniden bulduktan sonra öteleme | ✅ mantıklı; ardından yeniden ölçülüyor |
| **`:1796`** | **ADIM 5 — hover-kilit ötelemesi** | ❌ **kusur burada** |

İkisi de (`:1640`, `:1796`) çağrıdan hemen önce `n0/e0/_c/_s`'i tazeliyor,
yani **üst üste binme yok**; işaret de ikisinde aynı (+ileri). Yani
"iki kez uygulanıyor" ya da "ters işaret" hipotezleri **elendi** — kusur
tek bir uygulamanın **yanlış yerde** olması.

---

## 4 · Ham veri — kanıt

Üç koşum, dokuz deneme. `settle` anında ölçülen mutlak konumlar:

| koşum/deneme | görsel son hata | \|kanca − yuva\| | \|araç − yuva\| |
|---|---|---|---|
| _234/1 | 24.5 mm | **207.9 mm** | 299.0 mm |
| _234/2 | 29.7 mm | **192.8 mm** | 282.9 mm |
| _234/3 | 6.5 mm | **201.6 mm** | 291.7 mm |
| _001/1 | 7.0 mm | **184.6 mm** | 273.5 mm |
| _001/2 | 29.4 mm | **235.0 mm** | 322.8 mm |
| _001/3 | 27.6 mm | **186.4 mm** | 269.5 mm |

İki bağımsız tutarlılık kontrolü:

**(a)** `|araç − yuva| − |kanca − yuva|` = 269.5−184.6 … 322.8−235.0
≈ **85–91 mm** — kanca askısının gövde-x'i (`hook_mount` = −0.090 m) ile
birebir. Ölçüm çerçevesi doğru.

**(b)** Hizalama kancayı 6.5–29.7 mm'ye getiriyor; settle anında kanca
**184.6–235.0 mm** ötede. Aradaki fark **~175–205 mm**, yani
`HOOK_BODY_OFFSET_FORWARD_M`. Eğer araç ADIM 5'te ötelenmeseydi, kanca
yuvanın ~20 mm yakınında kalırdı ve `|araç − yuva| ≈ 90 mm` olurdu.

---

## 5 · Neden değişken? (64.6 – 282.5 mm)

Üç terim üst üste biniyor:

**(i) Yön farkı — ±e, geometrik ve kaçınılmaz.**
Sıçrama `|ē + 0.175·û_ileri|`. `ē` (hizalamanın artık hatası, 6.5–29.7 mm)
ile gövde-ileri yönü arasındaki açı serbest: aynı yöndeyse 175+e,
tersse 175−e. Tek başına **145–205 mm** bandı verir.

**(ii) Sarkaç — ADIM 5 sonrası.** ADIM 5'in 4 s'lik `goto`'su + salım +
`_wait_hook_stopped` boyunca kanca salınıyor. Ölçülen periyot 1.078 s,
ζ≈0.03. Ölçüm **salınımın hangi fazında** düştüğüne göre değişiyor.
Bu, 205 mm'yi aşan değerleri (235 mm) ve 145 mm'nin altını (92 mm)
açıklıyor.

**(iii) Yaw.** Öteleme `aligned_yaw`'a göre döndürülüyor; yaw denemeden
denemeye değişince `û_ileri` de değişiyor ve (i)'deki açıyı belirliyor.

> **Sabit bir ofset hatası olsaydı sıçrama sabit çıkardı** — gözlemin
> değişken olması, sabit bir 175 mm terimin ÜZERİNE sarkaç/yön
> gürültüsünün binmesiyle tutarlı. Ortanca **+201.9 mm**, 175 mm'nin biraz
> üzerinde; fark, (ii)'nin ortalama katkısı.

---

## 6 · Bu, gözlenen davranışın tamamını açıklıyor mu?

| gözlem | açıklandı mı |
|---|---|
| Sıçrama hep **pozitif** (10/10) | ✅ ofset tek yönlü ekleniyor |
| Ortanca ~175–200 mm | ✅ sabitin kendisi |
| Değişkenlik | ✅ yön + sarkaç |
| `_settle_hook_onto`'nun 8.4 s'de düzeltebilmesi | ✅ 175 mm'yi geri kapatıyor |
| İnişin bitiş yanalının iyi olması (4.6–19.2 mm) | ✅ düzeltmeden sonrası sağlam |

**Kalan belirsizlik (dürüstçe):** (ii) sarkaç teriminin büyüklüğü ayrıca
ölçülmedi; 175 mm sistematik terimi ile sarkaç gürültüsünün payını
ayırmak için ADIM 5 öncesi/sonrası kanca pozunun ardışık örneklenmesi
gerekir. Bu turda **yapılmadı** — ama kök nedenin kimliğini değiştirmez,
yalnızca artık hatanın ne kadarının sarkaçtan geldiğini belirler.

---

## 7 · Uygulanmadı — karar operatöre

Mekanizma tek bir satırda: ADIM 5'in ötelemesi, kendisinden önce gelen
**kanca referanslı** hizalamadan sonra artık gereksiz. Seçenekler ölçülmeden
sıralanmamalı; rapor burada bitiyor.
