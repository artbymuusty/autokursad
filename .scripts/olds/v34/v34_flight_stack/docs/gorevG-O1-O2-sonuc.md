# GÖREV G — Ö1 uygulandı, Ö2 ölçüldü (kısmen), canlı sonuç

**Tarih:** 2026-09-04 · **Commit:** `9cdfa1e8` (Ö1) · **Push edilmedi**
**Test paketi:** 528 geçti, 1 atlandı, 0 başarısız

---

## ÖZET

| | durum |
|---|---|
| **Ö1** — çağrı argümanını birleştir | ✅ **uygulandı ve canlıda doğrulandı** |
| **Ö2** — `HOOK_PAYOUT_CHAIN_OFFSET_M`'i ölç | ⚠️ **YARIM: `D0` kesin ölçüldü, `B` kapanmadı** → **sabit DEĞİŞTİRİLMEDİ** |
| insertion kapıya (≥ −4 mm) girdi mi | **9 denemenin 2'sinde girdi** (o1a/1 **+4.6 mm**, o1d/2 **0.0 mm**) — güvenilir değil |
| **Ö3** — doyumda açıkça dur | **artık GEREKÇELİ** — bkz. §5, ölçüm doyumu gösteriyor |

**Ö1 tek başına insertion'ı −205 mm'den ~0 mm'ye taşıdı.** Kalan artığın
kaynağı ise CHAIN_OFFSET değil: **aracın gerçek tutma irtifası.**

---

## 1 · Ö1 — hangi kaynak doğru

Ölçümle karara bağlandı: **nominal `GOREV3_DESCENT_ALTITUDE_M` doğru kaynak.**

Gerekçe, tahmin değil ölçüm:
- Alma penceresi boyunca aracı tutan şey `_start_hold()`'dur ve o
  `-GOREV3_DESCENT_ALTITUDE_M` komut eder (`gorev3_pickup.py:983-985`).
- `_pick_alt` pencereden **önce** alınmış **tek** bir örneklemedir
  (`:1025`) ve pencereyi temsil etmediği ölçüldü: dört koşumda 0.094–0.161 m
  okurken, kancanın gerçek dünya pozundan geri hesaplanan pencere irtifası
  **~0.36–0.47 m**. `_pick_alt` geçici bir alçalma dibini yakalıyor.

**Uygulama, iki katman:**
1. `gorev3_pickup.py` → `activate_pickup_mechanism(altitude_m=GOREV3_DESCENT_ALTITUDE_M)`
2. `gz_payload_actuator.extend_winch_for` → çağıran ne verirse versin
   **ulaşılmış salımın altına inmiyor**. Açık geri çekme yolu
   (`set_winch(HOOK_WINCH_RETRACT_M)`) **etkilenmiyor**; denemeler arası
   geri çekme onu kullanıyor. Poz okunamazsa koruma da yok.

`_pick_alt` **ölçüm olarak kaldı** — yalnızca salım hesabından çıktı.

---

## 2 · Ö1'in canlı etkisi — 3 bağımsız koşum, 9 deneme

Her koşumdan önce tam SITL yeniden başlatma (bağımsızlık `run_one_v2.sh`).

| | ÖNCE (r1/r2b/r3b/r5b) | SONRA (o1a/o1b/o1d) |
|---|---|---|
| komut edilen salım | **0.124–0.191 m** | **0.330 m** (üçünde de) |
| pencere boyunca vinç | **113–186 mm GERİ ÇEKİLİYOR** | **0.3284–0.3287, sabit** |
| `too_high` reddi | **225/225 (%100)**, 12 denemenin 12'sinde | %85'e düştü, artık %100 değil |
| en iyi `insertion` | **−202.7 / −212.2 / −210.6 mm** | **−1.3 / 0.0 / +4.6 mm** (iyi durumlar) |

Deneme bazında en iyi örnek insertion (kapı ≥ −4.0 mm):

| koşum | den 1 | den 2 | den 3 |
|---|---|---|---|
| **o1a** | **+4.6** ✅ | −4.6 | −6.7 |
| o1b | −94.9 | −124.2 | −106.4 |
| o1d | −114.1 | **0.0** ✅ | −114.0 |

**Geri çekme tamamen ortadan kalktı** (vinç 0.3285'te sabit, `winch_min`
yalnızca denemeler arası açık geri çekmede düşüyor — beklenen).

**Ama hiçbir deneme OTURMADI**: oturma bütün kapıların *aynı anda*
`SEAT_DWELL_S` boyunca sağlanmasını istiyor ve artık düşüren kapı
çoğunlukla **lateral** (o1a/1'de `best_simultaneous`: insertion −1.3 mm,
lateral **48.4 mm**, `gates_failed=1`).

---

## 3 · Ö2 — ne ölçüldü, ne ölçülemedi

### 3.1 Cebir (formülden türetildi)

```
formül :  e = alt − deck + CHAIN + margin
fizik  :  burun guverteye değer  ⇔  base_z − (D0 + e) = deck
          base_z = alt + B
⇒  CHAIN + margin = B − D0        ⇒  CHAIN = B − D0
```
- `D0` = vinç çekiliyken base_link → burun mesafesi
- `B` = araç yerdeyken (alt=0) base_link'in **dünya** Z'si

### 3.2 `D0` — KESİN ÖLÇÜLDÜ

Araç 3 m'de havadayken, kanca **serbest sarkarken**
(`scratchpad/o2/measure_chain_air.py`, salt okuma):

| e (komut) | ulaşılan salım | D = base→burun |
|---|---|---|
| 0.00 | 0.00324 | **0.20088** |
| 0.35 | **0.35000** | 0.54764 |
| 0.00 | 0.00294 | **0.20058** |

**D0 = 0.20073 m** (iki okuma). Gerçek salım `D1−D0 = 0.34691` m,
komut 0.350 → **vinç %99 doğrulukla çalışıyor**, bir kez daha.

SDF'ten bağımsız hesap: `hook_mount` +0.05 (`model.sdf:126`), altındaki
zincir `0.02287 + 3×0.04575 + 0.02287 + 0.06465 = 0.24764`
(`model.sdf:439,508,577,646,217` + `hook_seating.py:80`)
→ **D0_SDF = 0.24764 − 0.05 = 0.19764 m.**
Ölçülenle farkı **3.1 mm** — SDF zincir modeli doğrulandı.

### 3.3 `B` — KAPANMADI

`base_link`'in **dünya** pozu gz-transport'ta yayınlanmıyor (modelin
kanonik linki), `dynamic_pose/info` yalnızca model-çerçevesi pozu veriyor
(3 m'de bile sabit 0.24000 döndü — bu dünya değeri değil).
İki uçuş denemem MAVSDK port çakışması ve bir askıda kalmayla düştü.

Sonuç: **iki aday da hâlâ ayakta ve fark tamamen `B`'den geliyor.**

| `B` varsayımı | kaynak | `CHAIN = B − D0` | hangi adaya yakın |
|---|---|---|---|
| 0.2400 | SDF + spawn pozu (model z=0) | **0.03927** | SDF **0.04236** (3.1 mm) |
| 0.2627 | 2026-09-01 ölçümü (`winch_state` docstring) | **0.06197** | kalibrasyon **0.060** (2.0 mm) |

**`HOOK_PAYOUT_CHAIN_OFFSET_M` DEĞİŞTİRİLMEDİ** — talimat gereği ölçüm
sonucu gelmeden formülde karar verilmedi.

**`B`'yi kapatmanın yolu (bir sonraki tura):** araç yerdeyken *ve* bilinen
bir irtifada havadayken `hook_body_link`'in **dünya** Z'sini `GzPoseMonitor`
ile okuyup `B = burun_dünya + D0 − alt` hesaplamak. `hook_body_link` dünya
pozu **yayınlanıyor** (denendi, çalışıyor); eksik olan tek şey aynı anda
temiz bir MAVSDK bağlantısı.

---

## 4 · Kalan artığın gerçek kaynağı — CHAIN_OFFSET DEĞİL

Ölçülen insertion'dan araç irtifasını geri hesaplayınca
(`base = burun + D0 + e`, `alt = base − 0.240`):

| koşum | insertion | geri hesaplanan alt | **komut** |
|---|---|---|---|
| o1a/1 | +4.6 mm | **0.355 m** | 0.30 |
| o1b/1 | −94.9 mm | **0.454 m** | 0.30 |
| o1d/1 | −114.1 mm | **0.473 m** | 0.30 |

**Kalan artık, aracın tutma irtifasındaki 55–173 mm'lik hatayla birebir
gidiyor.** CHAIN_OFFSET tartışması 22.7 mm mertebesinde; buradaki artık
onun **5 katı**. Yani Ö2 kapansa bile bu artık kapanmaz.

`o1a` neden başardı: araç 0.355 m'de, komuta en yakın olan koşum.
`o1b`/`o1d` 0.45–0.47 m'de kaldı ve tam o kadar yukarıda.

---

## 5 · Ö3 artık GEREKÇELİ (öneri, uygulanmadı)

O irtifalarda kapıya girmek için gereken salım:

| koşum | alt | gereken `e` | sınır 0.35 |
|---|---|---|---|
| o1a | 0.355 | 0.328 | sığar |
| o1b | 0.454 | **0.423** | **DOYUM** |
| o1d | 0.473 | **0.442** | **DOYUM** |

**3 koşumun 2'sinde gereken salım fiziksel sınırın üstünde.** Yani o
koşumlarda alma **hiçbir denemede mümkün değildi** ve sistem 3 denemeyi
sessizce tüketti. Ö3 tam olarak bunun içindi:

> doyuma ulaşıldığında **açıkça dur**, imkânsız işi tekrarlama.

`extend_winch_for` doyumu zaten `[HOOK] VINC DOYUMU` diye **logluyor**
(`gz_payload_actuator.py:1447`) ama **karar vermiyor** — döngü devam ediyor.

**Ama asıl düzeltme Ö3 değil:** doyumun sebebi aracın 0.15 m yukarıda
kalması. Doğru sıra:
1. **Ö5 (yeni)** — tutma irtifasının neden 0.30 yerine 0.45 olduğunu ölç.
   Bu, artığın **tek** baskın kaynağı.
2. **Ö3** — ikinci savunma katmanı: doyumdayken 3 deneme yakma.
3. **Ö2** — `B`'yi kapat; 22.7 mm'lik ince ayar, öncelik en düşük.

---

## 6 · Ö4 — arayüz sözleşmesi (bu turda uygulanmadı, not)

`IPayloadActuator.activate_pickup_mechanism(altitude_m=...)` — bu argüman
**nominal mi, ölçülen mi?** Ö1 bunu *çağrı yerinde* çözdü ama
**arayüz hâlâ söylemiyor.** Ölçüm artık cevabı veriyor:

> `altitude_m`, alma penceresi boyunca aracın **tutulduğu** irtifadır
> (komut edilen nominal değer), o andaki anlık telemetri okuması değil.
> Salım bu referanstan hesaplanır ve çağrı asla geri çekme üretmez.

Bu cümle `i_payload_actuator.py:22` docstring'ine yazılmalı. Gerçek
donanımda vinç yok (`real_payload_actuator.py`'de "winch" hiç geçmiyor),
ama aynı belirsizlik THIRD MISSION SERVO yazılırken tekrar edebilir.

---

## 7 · Kapsam ve dürüstlük notları

- 3 geçerli koşum (o1a, o1b, o1d). `o1c` MAVSDK parametre zaman aşımıyla
  (`set_takeoff_altitude` PARAMETER_ERROR) Faz 1'e ulaşamadı — altyapı
  arızası, konuyla ilgisiz, veriye katılmadı.
- `B` ölçülemedi; §3.3'teki iki satır **varsayım**, ölçüm değil.
- §4 ve §5'teki geri hesaplar `B = 0.240` varsayımına dayanıyor. `B`
  0.2627 olsaydı irtifalar 23 mm düşerdi — **sonucu değiştirmez**
  (artık 55–173 mm).
- Ö1'in etkisi ölçüldü ve büyük; ama **oturma hâlâ gerçekleşmiyor** ve
  şimdi baskın engel **lateral**, dikey değil.
