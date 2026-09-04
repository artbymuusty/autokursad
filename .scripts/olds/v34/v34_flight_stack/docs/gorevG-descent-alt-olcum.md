# GÖREV G — `GOREV3_DESCENT_ALTITUDE_M` aday değerinin ÖLÇÜMÜ

**Tarih:** 2026-09-04 · **Kalıcı config değişikliği: YOK** (geçici uygulandı, geri alındı, git ile doğrulandı)
**Koşumlar:** g12a, g12b — her birinde tam SITL yeniden başlatma

---

## HÜKÜM (önce, kısa)

| | sonuç |
|---|---|
| Kapıya giren deneme | **0/5 → 1/2** (g12a `+10.7 mm`, kapı `−4 … +22 mm`) |
| `too_high` reddi | %100 → **%82–90** |
| Ö3 doyum koruması | 5/5 tetikleniyordu → **0/2** (erişim artık sınır içinde) |
| Yeni bağlayıcı kapı | **LATERAL** — dikey değil |
| Güvenlik (zeminde mi) | **hayır**, ölçüldü: gerçek irtifa p10 **0.177 m** |
| Görev 2'ye sızma | **yok** (kod + ölçüm) |
| **Tutarlılık** | ❌ **1/2** — kalıcı değişiklik için yetersiz, §4 |

---

## 1 · Aday değerin türetilmesi (istenen madde 1)

5 koşumun **gerçek** açığı (gereken salım − `HOOK_WINCH_MAX_EXTENSION_M`):

| koşum | gereken | açık |
|---|---|---|
| f1 | 0.488 | **138.0 mm** |
| f2 | 0.422 | 72.0 mm |
| f3 | 0.390 | 40.0 mm |
| f4 | 0.466 | 116.0 mm |
| f5 | 0.441 | 91.0 mm |
| | ortalama | **91.4 mm** · ortanca **91.0 mm** · max **138.0 mm** |

İrtifayı Δ kadar düşürmek gereken salımı **1:1** azaltır (araç–güverte
mesafesi o kadar kısalır).

| yeni hedef | Δ | yeni gereken | sınıra kullanım | marj | kapıya girebilen |
|---|---|---|---|---|---|
| 0.210 | 0.090 | 0.300–0.398 | 113.7% | −13.7% | 2/5 |
| 0.180 | 0.120 | 0.270–0.368 | 105.1% | −5.1% | 4/5 |
| 0.160 | 0.140 | 0.250–0.348 | 99.4% | 0.6% | 5/5 |
| 0.150 | 0.150 | 0.240–0.338 | 96.6% | 3.4% | 5/5 |
| 0.130 | 0.170 | 0.220–0.318 | 90.9% | 9.1% | 5/5 |
| **0.120** | **0.180** | **0.210–0.308** | **88.0%** | **12.0%** | **5/5** |
| 0.100 | 0.200 | 0.190–0.288 | 82.3% | 17.7% | 5/5 |

**Seçilen aday: 0.12 m.** Gerekçe:

- **Ortalamaya/ortancaya (91 mm) göre boyutlamak yanlış olurdu:** o
  değerde 2/5 koşum hâlâ dışarıda kalıyor. Bağlayıcı kısıt **en kötü
  koşum** (138 mm), ortalama değil — yarı zamanlı çalışan bir eşik
  düzeltme sayılmaz.
- 0.12, en kötü açığı kapatıp üstüne **42 mm** pay bırakıyor →
  sınırın **%88.0**'i, yani **%12.0 marj**, istediğiniz 10–15 bandında.
- 0.13 → %9.1 (bandın hemen altında), 0.15 → %3.4 (çok dar).

---

## 2 · Ölçüm sonucu (istenen madde 2)

| koşum | Faz 1 | deneme | **en derin insertion** | Ö3 | lateral (min / p50) | düşüren kapı |
|---|---|---|---|---|---|---|
| **g12a** | FAIL#3 | 3 | **+10.7 mm ✅ kapı içinde** | tetiklenmedi | 3.1 / 46.3 mm | **LATERAL** 226/226 |
| **g12b** | FAIL#3 | 3 | −157.5 mm ❌ | tetiklenmedi | 3.9 / — | lateral + too_high |

**Karşılaştırma:**

| | 0.30 komut (f1–f5) | 0.12 komut (g12a/b) |
|---|---|---|
| komut edilen salım | 0.330 m | **0.150 m** |
| en derin insertion | −61.8 … −159.5 mm | **+10.7** / −157.5 mm |
| kapıya giren | **0/5** | **1/2** |
| `too_high` reddi | 225/226 (%100) | 185–224/226 (%82–99) |
| Ö3 doyum | **5/5 tetiklendi** | **0/2** (gereken 0.326 < 0.350) |

**Dikey engel kalktı, yerine yatay engel geçti.** g12a'da insertion
kapının içindeyken (`best_simultaneous`: insertion −1.1 mm) **lateral
37.9 mm** ile tek başına düşürüyor; kapı ~10.25 mm.

---

## 3 · Güvenlik — ölçüldü, varsayılmadı (istenen madde 3)

Alma penceresine kısıtlı ULog `groundtruth` (tüm uçuş değil):

| koşum | EKF (komut 0.12) | **GERÇEK p10** | **GERÇEK p50** | zeminde mi |
|---|---|---|---|---|
| g12a | 0.129 | **0.177 m** | 0.221 m | **hayır** |
| g12b | 0.119 | **0.366 m** | 0.404 m | **hayır** |

Kontrolcü komutu tutuyor (EKF 0.129 / 0.119 vs komut 0.12). Pencerede
gözlenen **en düşük gerçek irtifa 0.177 m** — zemin teması yok, yer
etkisi bandına inilmedi. `land_detected` yalnızca kalkış/iniş
anlarında 1.

---

## 4 · Neden 1/2 — ve kalıcı değişikliği neden ÖNERMİYORUM

Ayırt edici sayı, iki koşum arasındaki **EKF ↔ gerçek** farkı:

| koşum | EKF | gerçek | **hata** | sonuç |
|---|---|---|---|---|
| q1 | 0.301 | 0.422 | +0.121 | — |
| q4 | 0.324 | 0.493 | +0.169 | — |
| **g12a** | 0.129 | 0.221 | **+0.092** | kanca **ULAŞTI** (+10.7 mm) |
| **g12b** | 0.119 | 0.404 | **+0.285** | kanca **18 cm yetişemedi** |

**EKF hatası sabit değil: 0.092 – 0.285 m arasında oynuyor.** Seçtiğim
%12'lik marj (42 mm), bu oynamanın (193 mm) **beşte biri**. Yani:

> Sabit bir irtifa değeri bu problemi **güvenilir** biçimde çözemez.
> g12a ile g12b arasındaki fark seçilen değerden değil, o koşumdaki
> kestirim hatasından geliyor.

Daha da düşük bir değer (0.10 → %17.7 marj) g12b'yi de kurtarmazdı:
g12b'nin gerçek irtifası 0.404 m'ydi, yani komuttan **0.285 m yukarıda**.

**Kalıcı değişiklik önermiyorum.** Bu ölçüm, değerin *işe yaradığını*
değil, **doğru büyüklükte olduğunu ve engelin yer değiştirdiğini**
gösterdi. Kalıcı yapmak, çözülmemiş bir dalgalanmanın üstüne sabit bir
sayı koymak olur.

---

## 5 · Görev 2'ye sızma yok (istenen madde 4)

**Kod tarafı:** `GOREV3_DESCENT_ALTITUDE_M` yalnızca `gorev3_pickup.py`
ve `gorev3_redrop.py`'de geçiyor. `motion_fsm`, `payload_release`,
`gorev2_orchestrator`, `gorev2_fsm`, `centering_controller` — **hiçbiri
kullanmıyor.**

**Ölçüm tarafı:** her iki koşumda `RELEASED=2`, isabet
`MAVI_ALTIGEN` 0.037 / 0.065 m (düzeltme sonrası tabanı 0.018–0.161),
`KIRMIZI_UCGEN` 0.349 / 0.319 m (tabanı 0.053–0.393). **İkisi de
mevcut dağılımın içinde.**

⚠️ Not: sabit **Faz 3 (redrop)** tarafından da kullanılıyor
(`gorev3_redrop.py:124-136`). Faz 1 geçmediği için bu turda hiç
çalışmadı; kalıcı bir değişiklikte Faz 3 ayrıca ölçülmeli.

---

## 6 · Bundan sonra ne yapılmalı (öneri, uygulanmadı)

Engel dikeyden yataya geçtiği için sıra da değişti:

1. **EKF dikey kestirim hatasını kovala** (0.09–0.29 m, değişken) —
   artık *tek* baskın belirsizlik. E4a'da `EKF2_OF_CTRL` kapatılmıştı;
   baro/GPS dikey füzyonu ve `dist_bottom` (mesafe sensörü var ve
   `dist_bottom_valid=1`) incelenmeli. **Mesafe sensörü zaten çalışıyor
   ve gerçek irtifayı doğrudan verebilir** — kapalı çevrimi ona bağlamak
   bu sınıfı tamamen kapatabilir.
2. **Lateral hizalama** — g12a'da dikey çözülmüşken tek düşüren kapı
   buydu (37.9 mm vs 10.25 mm).
3. Sabit bir `GOREV3_DESCENT_ALTITUDE_M` düşürmesi ancak (1) çözülünce
   anlamlı olur.

---

## 7 · Kapsam ve dürüstlük

- **n=2.** Bir koşumda çalıştı, birinde çalışmadı; güvenilirlik
  hükmü verilemez.
- Geçici değer uygulanıp **geri alındı**; `git diff` ile
  `parameters.py` üzerinde fark olmadığı doğrulandı, değer 0.30.
- §1'deki 1:1 varsayımı (Δ irtifa → Δ gereken salım) g12a'da tuttu
  (gereken 0.488→~0.32), g12b'de EKF hatası yüzünden sınanamadı.
- Faz 3 (redrop) bu turda hiç çalışmadı.
