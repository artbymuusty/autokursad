# GÖREV G / Ö5 — KÖK NEDEN: `relative_altitude_m` sabit datum kayması

**Tarih:** 2026-09-04 · **Tip:** ölçüm · **Kod/config değişikliği: YOK**
**Koşum:** q1, q4 (2 geçerli, her birinde tam SITL yeniden başlatma)

---

## TEŞHİS

> **Görevin irtifa okuması (`relative_altitude_m`), aracın kendi EKF
> kestiriminin SABİT ~0.177 m ALTINDA.** Kontrolcü setpoint'i doğru
> tutuyor; yanlış olan, göreve rapor edilen sayı.

Kullanıcının tarif ettiği üç kuraldan **üçüncüsü** gerçekleşti:
*"`relative_altitude_m` diğer ikisinden sistematik sapıyorsa → home/datum
referans hatası."*

---

## 1 · Ölçüm — üç kaynak, aynı pencere, hizalı

Hizalama çapraz korelasyonla (dosya adına ya da başka varsayıma
güvenilmedi): **q1 r=0.953, q4 r=0.949.**

Alma penceresi (ilk deneme, 12 s), komut **0.300 m**:

| | q1 | q4 |
|---|---|---|
| **A** — ULog `vehicle_local_position` −z (EKF) | **+0.301** | **+0.324** |
| **B** — ULog `vehicle_local_position_groundtruth` −z (GERÇEK) | **+0.422** | **+0.493** |
| **C** — jsonl `relative_altitude_m` (görevin gördüğü) | **+0.123** | **+0.122** |
| A − B (EKF − gerçek) | −0.121 | −0.169 |
| **C − A (görev − EKF)** | **−0.178** | **−0.202** |
| C − B (görev − gerçek) | −0.299 | −0.371 |
| **B − komut** | **+0.122** | **+0.193** |

### 1.1 Kayma SABİT — ölçek hatası değil

`C − A`, tüm irtifa bandı boyunca:

| EKF bandı | q1 | q4 |
|---|---|---|
| 0–1 m | **−0.175** | **−0.164** |
| 8–16 m | **−0.177** | **−0.179** |

**0.16 m'den 16 m'ye kadar aynı ~0.177 m.** Ölçekle büyümüyor → çarpan
hatası değil, **sabit referans kayması.** (1–3 ve 3–8 m bantları geçiş
rejimi: C ~1 Hz örnekleniyor, A sürekli; tırmanış/alçalış sırasında
gecikme artefaktı üretiyorlar, hükme katılmadı.)

---

## 2 · Üç adayın ayrıştırılması

| aday | hüküm | kanıt |
|---|---|---|
| **Yer etkisi / kontrolcü** | ❌ **ELENDİ** | Kontrolcü **kendi kestirimine göre setpoint'i tutuyor**: A p50 = +0.301 / +0.324, komut 0.300. Sorun kontrolde değil. |
| **Zeminde yük aktaran kanca+ip** | ❌ **ELENDİ** | Araç zeminde değil; gerçek irtifa **0.42–0.49 m**, komutun **üstünde**. Ayrıca kayma 16 m'de de aynı — orada kanca zemine değmiyor. |
| **home/datum referans hatası** | ✅ **DOĞRULANDI** | `C − A` iki koşumda ve 0–16 m'de sabit ~0.177 m. |

**Ek, ayrı bir bileşen:** `A − B` = −0.12 … −0.17 m, yani **EKF de gerçeği
~0.15 m eksik kestiriyor** ve bu sabit değil. Bu ikinci bir sorun; datum
kaymasıyla toplanınca görev, gerçekte 0.42–0.49 m'deyken **0.12 m** görüyor
— **~0.30 m'lik toplam hata.**

---

## 3 · ÖNCEKİ İKİ İDDİAMIN DURUMU — biri doğru, biri yanlıştı

Bu ölçüm, bu oturumda benim yaptığım bir düzeltmeyi **geri alıyor.**

| # | iddia | durum |
|---|---|---|
| 1 | `gorevG-O1-O2-sonuc.md` §4: *"araç komutun ÜSTÜNDE, ~0.45 m"* (kanca dünya pozundan türetilmişti) | ✅ **DOĞRUYMUŞ** — gerçek 0.42–0.49 m |
| 2 | `gorevG-O5-tutma-irtifasi.md` §0–1: *"hayır, araç komutun ALTINDA, ~0.10 m"* (telemetriden ölçülmüştü) | ❌ **YANLIŞ** |

**Neden yanılttı:** ikinci iddia `relative_altitude_m`'e dayanıyordu — yani
tam da bozuk olan kaynağa. "Türetme yerine doğrudan ölçüm" diye yaptığım
düzeltme, aslında güvenilir kaynağı bırakıp bozuk olana geçmekti. Doğru
olan **Gazebo pozundan yapılan geometrik türetmeydi.**

`gorevG-O5-tutma-irtifasi.md` §0, §1 ve §2 bu doğrultuda **düzeltilmelidir**
(§3'teki doyum koruması etkilenmiyor — o zaten hiçbir irtifa kaynağı
kullanmıyor, bkz. §5).

---

## 4 · Neden bu Görev 3'ün gerçek kapanışı

Faz 1'in irtifaya bağlı **her** kararı `_current_alt_m()` →
`get_global_position()[2]` → `relative_altitude_m` üzerinden geçiyor
(`gorev3_pickup.py:477-483`). Yani faz, **sistematik olarak ~0.30 m
alçakta olduğunu sanıyor.** Doğrudan sonuçları:

1. **Salım formülü eksik hesaplıyor.** `payout = alt + 0.030`; `alt`
   0.30 m eksikse salım da 0.30 m eksik. Ö1'den sonra bile insertion'ın
   ~−0.11 m'de takılmasının açıklaması bu.
2. **Ö2 çıkmazı çözülüyor.** `CHAIN_OFFSET`'in iki adayı (0.042 / 0.060)
   arasındaki tartışma anlamsızdı: formülün **girdisi** 0.30 m yanlıştı,
   sabiti değil. `gorevG-O5-tutma-irtifasi.md` §2'de `B`'nin sabit
   çıkmaması da bununla açıklanıyor.
3. **Kadraj/tespit analizi (Görev G §2.4) yanlış irtifalarda yapılmış.**
   Araç 1.5 m sanırken gerçekte ~1.8 m'de; yük alan kapısına olan pay
   hesaplanandan dar. FAIL#1'in (tespit) neden kesintili olduğuna da
   buradan bakılmalı.
4. **`LOW_ALT_VISION_LIMIT_*`, `GOREV3_DESCENT_ALTITUDE_M`,
   `HOOK_VISUAL_ALIGN_ALTITUDE_M`** — hepsi bu bozuk okuma üzerine
   kalibre edilmiş olabilir.

---

## 5 · Ö3 doyum koruması bu bulgudan ETKİLENMİYOR

Tasarım gereği: ölçütü `gereken_salım = ulaşılan_salım + (−insertion)` ve
ikisi de irtifadan bağımsız ölçülüyor. **Canlıda tetiklendi** (q1,
14:09:11): gereken 0.3875 m > sınır 0.350 m → 1 deneme yapıldı, 2 atlandı.
`last_pickup_report["aborted"]` gerekçeyi sayıyla kaydetti.

---

## 6 · DÜZELTMEYE GEÇMEDEN — açık sorular

**Kök neden katmanı belirlendi (`relative_altitude_m` datum kayması), ama
o kaymanın NEDENİ belirlenmedi.** Düzeltmeden önce cevaplanmalı:

1. Kayma MAVSDK'nin `relative_altitude_m` hesabından mı, PX4'ün
   `home_position`'ından mı, yoksa EKF `ref_alt`'ından mı geliyor?
   (q1 ULog'da `vehicle_local_position.ref_alt = 0.2757`, sabit — bu sayı
   0.177'ye yakın değil ama aynı mertebede; incelenmeli.)
2. Kalkışın yapıldığı an home nerede kuruluyor — araç yerdeyken mi,
   yoksa `PX4_GZ_MODEL_POSE` z=0 ile base_link 0.240 arasındaki fark
   devreye mi giriyor?
3. **Gerçek donanımda da var mı?** Bu bir SITL spawn/datum artefaktıysa
   gerçek uçuşta olmayabilir; varsa saha kalibrasyonunu doğrudan etkiler.
4. Düzeltme nerede yapılmalı — telemetri katmanında tek noktada mı
   (`get_global_position`), yoksa Faz 3'ün kalibre edilmiş sabitleri de
   birlikte mi taşınmalı? **İkincisi büyük bir iş** ve bu oturumun
   kalibre ettiği her eşiği yeniden değerlendirmeyi gerektirir.

---

## 7 · Kapsam ve sınırlar

- 2 geçerli koşum (q1, q4). `p1` harness hatasıyla (paralel `gz topic`
  örnekleyicim launcher'ın yetim kontrolünü tetikledi) SITL'i hiç
  başlatamadı; `q2` Faz 1'e ulaşamadı (merkezleme zaman aşımı); `q3`
  FAIL#1 ile düştü, alma penceresi oluşmadı. Hiçbiri veriye katılmadı.
- D kaynağı (`hook_body_link` dünya z, eşzamanlı örneklenmiş) **toplanamadı**;
  hüküm A/B/C üçlüsüne dayanıyor. B (Gazebo gerçeği) zaten mekanik dalı
  eledi.
- Datum kaymasının **nedeni** ölçülmedi (§6).
- Kod ve config değiştirilmedi.
