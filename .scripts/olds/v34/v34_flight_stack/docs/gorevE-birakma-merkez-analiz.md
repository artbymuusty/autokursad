# Görev E — Bırakmada Hedef Merkezinden Kayma (FAZ 1: Analiz)

**Tarih:** 2026-09-03 · **Kod değişikliği YOK.**
**Veri:** canlı Görev 2 koşumu (`demo_20260903_013023`, 2 bırakma) — PX4 ULog,
görev olay kaydı, `default.sdf` yer gerçeği.

---

## 0. Hüküm: **HİPOTEZ ÇÜRÜDÜ**

> Hipotez: *"Sistem ~3 m altında vision merkezlemeyi durduruyor, o andaki yanlış
> pozisyonu 'hedefe kilitli' varsayıyor; Görev C'nin kilidi de yanlış yeri sadık
> şekilde koruyor."*

İki bağımsız kanıtla çürüdü:

**(a) Mekanizma öyle çalışmıyor.** Eşik altında pozisyon **kapalı çevrim kalmaya
devam ediyor**. `_open_loop_descend()` docstring'i birebir şöyle diyor:

> *"Open loop" is only true of VISION. Position is still closed-loop: the frozen
> estimate is a fixed GPS point and every tick steers at it using live GPS, so
> drift is corrected the whole way down.*

"Dondurulan" şey aracın konumu değil, **hedefin geri-yansıtılmış GPS'i**
(`_freeze_target_estimate`) — kamera lever-arm'ı ve payload mount ofseti dahil.

**(b) Sonuç da öyle çıkmıyor.** Bırakma anında aracın **gerçek** dünya konumu ile
şeklin **gerçek** merkezi arasındaki mesafe:

| Bırakma | Hedef | Araç dünya konumu | Şeklin gerçek merkezi | **Mesafe** |
|---|---|---|---|---|
| 1 | MAVI_ALTIGEN | (−6.15, 7.79) | (−5.406, 8.056) | **0.79 m** |
| 2 | KIRMIZI_UCGEN | (−4.91, 73.45) | (−4.886, 73.308) | **0.14 m** |

Hesap: EKF orijini = araç spawn'ı = dünya (0, −25) (`PX4_GZ_MODEL_POSE`);
dünya ekseninde **Y = Kuzey, X = Doğu** (`default.sdf` AXIS CONVENTION notu).
Şekil merkezleri o koşumun `default.sdf`'inden okundu.

`blue_hexagon` 5.00 m genişliğinde — 0.79 m sapma şeklin **içinde**. Üçgen
bırakması 14 cm ile pratikte tam merkezde.

---

## 1. Eşik nerede, değeri ne, kasıtlı mı (Soru 1)

| | |
|---|---|
| **Dosya** | `core/config/parameters.py:490` |
| **Sabit** | `LOW_ALT_VISION_LIMIT_M = 2.0` (**3.0 değil**) |
| **Şekle bağlı** | `LOW_ALT_VISION_LIMIT_BY_SHAPE = {"KIRMIZI_DIKDORTGEN": 0.5, "MAVI_DIKDORTGEN": 0.5}` |
| **Karar** | **KASITLI ve ÖLÇÜLMÜŞ** — ADR-010 P1 |

Gerekçe kodda yazılı ve geometrik (tahmin değil):

> *`_detect_hexagon` konturu TEK bir eps ile yaklaşıklıyor ve tam 6 dışbükey
> köşe istiyor; altıgen kare kenarını kırptığı anda konturu altıgen olmaktan
> çıkıyor ve hiçbir eps taraması geri getiremiyor.*

Ölçülen kayıp irtifaları (V1‴ koşumu): `MAVI_ALTIGEN` 1.63 m'de kayboldu,
`KIRMIZI_UCGEN` 0.47 m'ye kadar izlendi. 2.0 m, en yüksek gözlenen kaybın
(1.63 m) hemen üstünde, marjla seçilmiş.

Bu, **Görev B/G2'deki kadraj bulgusuyla aynı sınıf** ama aynı sayı değil:
orada 1.5 m'de kadraj ~3.55 × 2.65 m idi ve hedef 7.9 m uzaktaydı (kadraj
dışı); burada hedef kadrajın **içinde** ama kenarı kırpıyor, dolayısıyla
dedektörün şekil kapısı düşüyor.

---

## 2. Eşik altında ne oluyor (Soru 2)

**Eşik bir KAPI, mod anahtarı değil.** Kodun kendi ifadesiyle: eşiğin üstünde
hedefi kaybetmek "bir şeyler ters" demek ve araç bekler; altında kaybetmek
**beklenen** ve alçalma dondurulmuş kestirimle sürer.

**Ölçülen koşumda vision 0.22 m'ye kadar izlendi** — yani merkezleme 2 m'de
durmadı:

```
LOW_ALT_OPEN_LOOP_DESCENT  KIRMIZI_UCGEN
  görüş kaybı @0.22 m   (eşik 2.0)
  dondurulmuş kestirim: offset 42.54 cm @0.422 m  (dx=313.5, dy=445.0 px)
```

Yani kapı, merkezlemeyi *kapatmıyor*; yalnızca hedef kaybolursa alçalmanın
**durmamasına izin veriyor**. `MAVI_ALTIGEN` bırakmasında bu olay hiç
yayınlanmadı — o bırakmada görüş hiç kopmadı.

**Görev C'nin kilidi hangi konumu kilitliyor:** `_start_release_hold()`,
`get_position_ned()` ile **o anki gerçek konumu** okuyor. O konum, açık çevrim
alçalmanın dondurulmuş kestirime doğru sürdüğü düzeltmelerin **sonucu** —
yani "merkezleme durduğu andaki ham konum" değil, düzeltilmiş son konum.
Ölçüm bunu doğruluyor (0.14 m / 0.79 m).

---

## 3. Bırakma öncesi son saniyeler (Soru 3)

```
01:33:26.5  KIRMIZI_UCGEN yük bırakma başlatıldı (kademeli yaklaşma)
   ...      görüş 0.22 m'ye kadar izledi (eşik 2.0 m'nin ÇOK altında)
   ...      dondurulmuş kestirim @0.422 m, artık offset 42.54 cm
01:33:50.7  RELEASE_HOLD  n=98.45  e=−4.91  d=−0.69  yaw=5.2
01:33:51.8  PAYLOAD 2 RELEASED @0.49 m
```

Kilit anındaki araç konumu → dünya (−4.91, 73.45); gerçek üçgen merkezi
(−4.886, 73.308) → **14 cm**. Yani 42.5 cm'lik dondurma-anı artığı, açık
çevrim alçalma boyunca ~14 cm'ye **kapanmış**.

---

## 4. Görev C ile çakışma riski (Soru 4)

**Konusuz kaldı** — hipotez çürüdüğü için merkezlemeyi düşük irtifada "daha
uzun açık tutma" gibi bir değişiklik önerilmiyor. Tek-setpoint-kaynağı ilkesi
korunuyor: bugün de açık çevrim alçalma biter, sonra `_start_release_hold`
başlar; ikisi hiçbir zaman aynı anda yayın yapmıyor.

---

## 5. Davranışın kasıtlı olma gerekçesi (Soru 5)

Evet, kasıtlı ve **zaten sizin önerdiğiniz biçimde**: *"güvenilir kaldığı sürece
aç, güvenilmez olduğu noktada en son güvenilir düzeltmeyi kilitle."* Sistem tam
bunu yapıyor —

- Kapı, dedektörün geometrik olarak çöktüğü noktanın üstüne konmuş (ölçülmüş).
- Kaybolana kadar merkezleme sürüyor (bu koşumda 0.22 m'ye kadar).
- Kaybolunca **en son güvenilir düzeltme** (geri-yansıtılmış hedef GPS'i)
  kilitleniyor ve ona doğru kapalı çevrim uçuluyor.
- Ek olarak `LOW_ALT_BBOX_CENTER = True`: eşik altında kontur-moment merkezi
  yerine **bounding-box merkezi** kullanılıyor, çünkü kırpılmış bir bloğun
  momentleri yalnızca görünen parça üzerinden hesaplanıyor (ölçülen sapma
  15 m'de 3.51 px, 0.45 m'de 77.99 px).

---

## 6. Asıl bulgu: sorun KONTROLDE değil, ÖLÇÜMDE

Belirtinin ("yükler merkeze bırakılmıyor") kaynağı büyük olasılıkla iki
**ölçüm/gözlem** kusuru:

### D1 — `TARGET_CENTERS` bayat (kesin)

`gz_system/gz_payload_actuator.py:312`:
```python
TARGET_CENTERS = {"MAVI_ALTIGEN": (0.0, 15.0), "KIRMIZI_UCGEN": (0.0, 40.0)}
```
Yorumu *"read straight off default.sdf"* diyor — ama `default.sdf` artık
**her koşumda `generate_competition_area.py` tarafından rastgele yeniden
üretiliyor**. O koşumun gerçek değerleri: altıgen (−5.406, 8.056), üçgen
(−4.886, 73.308).

Sonuç: `offset_from_center_cm`, `settled_on_target` ve "HEDEF DISINDA"
uyarılarının **tamamı yanlış referansa karşı hesaplanıyor**. Ölçülen örnek:
raporlanan 1396.7 cm, gerçek 3351.6 cm — ikisi de aracın gerçek 14 cm'lik
isabetiyle ilgisiz.

### D2 — GEÇERSİZ: bu tutarsızlık benim okuma hatamdı

> **DÜZELTME (2026-09-03, E2 ölçümü sonrası).** Aşağıdaki 33.5 m'lik
> tutarsızlık **gerçek değil**. `PAYLOAD_FINAL_POSE`'u
> `mission_ef9d617d8725.jsonl`'den (01:26–01:29 koşumu), uçuş telemetrisini
> ise `mission_0b9d78556168.jsonl`'den (01:30–01:35 koşumu) okumuşum — iki
> ayrı koşumu karşılaştırmışım. Doğru eşleştirmede aynı bırakma **0.157 m**
> tutarlı çıkıyor. Yükün erken ayrıldığına dair de kanıt yok:
> `MOUNT_VECTOR_MEASURED` servo anında yükü araçtan **3.4–3.6 cm** ötede
> ölçüyor (dört bırakmanın dördünde). `PAYLOAD_FINAL_POSE` okuması bağımsız
> bir ~150 Hz poz iziyle doğrulandı: hata **0.0–0.2 cm**, önbellek yaşı
> **3–5 ms**. Ayrıntı: `docs/gorevE-E2-E3-olcum-raporu.md`.
>
> Aşağıdaki özgün metin, ne iddia edildiğinin kaydı olarak duruyor.

### D2 (özgün, GEÇERSİZ) — `PAYLOAD_FINAL_POSE` bırakma noktasıyla tutarsız

Aynı bırakma için:
- araç dünya konumu (−4.91, **73.45**), bırakma irtifası 0.49 m
- raporlanan yük konumu (−13.93, **41.03**) → bırakma noktasından **33.5 m**

0.49 m'den bırakılan bir yük 33 m öteye düşemez. Dikkat çekici olan, y≈41'in
altıgen (y≈8) ile üçgen (y≈73) arasındaki **geçiş yolunun ortasına** denk
gelmesi — mavi yükün transit sırasında erken ayrılmış olabileceğini
düşündürüyor. Bu **ayrı bir kusur** (yük tutma ya da poz okuma) ve Görev E'nin
kapsamı dışında; doğrulanmadan iddia etmiyorum.

---

## 7. Öneri

**FAZ 2'ye geçmedim** — talimatınız: bulgu hipotezle çelişiyorsa dur ve raporla.

Merkezleme/eşik tarafında **değişiklik önermiyorum**: ölçüm, mekanizmanın
tasarlandığı gibi çalıştığını ve aracın hedefte olduğunu gösteriyor.

Sıradaki iş kalemi olarak önerim, öncelik sırasıyla:

| # | İş | Gerekçe | Risk |
|---|---|---|---|
| **E1** | `TARGET_CENTERS`'ı `default.sdf`'ten **koşum anında** oku (ya da `generate_competition_area.py`'ın yazdığı bir dosyadan) | Bugün hiçbir isabet ölçümü güvenilir değil; bu düzelmeden "merkeze bırakıyor muyuz" sorusu **cevaplanamaz** | Düşük — yalnızca ölçüm yolu, kontrol yolu değil |
| ~~E2~~ | ~~D2'yi araştır~~ — **YAPILDI, kusur yok**: okuma doğru (0.0–0.2 cm), erken ayrılma dışlandı | — | — |
| **E3** | E1 sonrası 2-3 koşumda gerçek isabet dağılımını ölç, `PAYLOAD_ON_TARGET_RADIUS_M = 0.5` eşiğinin makul olup olmadığına karar ver | 0.79 m bugün "başarısız" sayılır ama şeklin içinde | Düşük |

Kararı size bırakıyorum.
