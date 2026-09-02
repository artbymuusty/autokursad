# Görev 3 — Analiz Raporu (FAZ 1)

**Tarih:** 2026-09-03
**Kapsam:** Yalnızca inceleme. **Hiçbir kod değişikliği yapılmamıştır.**
**İlgili:** [v34-sistem-denetimi.md](v34-sistem-denetimi.md) · [flight-control-analysis.md](flight-control-analysis.md)

---

## 0. Yönetici Özeti

| # | Bulgu | Ağırlık |
|---|---|---|
| **G1** | Görev 3 **birim testleri (13) ŞU AN GEÇİYOR**. Başarısız olan şey canlı SITL koşumuydu — ikisi karıştırılmamalı. | Netleştirme |
| **G2** | Canlı Faz 1 başarısızlığının kök nedeni **kesin**: `_locate_target_with_retries()` aracı **hiç hareket ettirmiyor**, 8 s boyunca aynı noktadan sorgu yapıyor; hedef kadrajın dışında. | **Kritik** |
| **G3** | Görev 3'ün **üç GPS bacağı da** `goto_global_position_and_wait()` kullanıyor — Climb-then-Cruise hiç uygulanmadı. | Yüksek |
| **G4** | Bu bacaklar **1.5 m irtifada** uçuluyor; Görev 2'nin dönüş bacağında ölçülen 3.13 m/s'lik seyir burada yere 1.5 m kala olur. Stabilite riski Görev 2'dekinden **farklı ve daha yüksek**. | **Kritik** |
| **G5** | `activate_pickup_mechanism` gövdesi hâlâ no-op; ama SITL'de zaten `GzPayloadActuator` kullanılıyor, yani **Faz 1'in SITL başarısızlığıyla ilgisi yok**. Ayrı iş kalemi. | Netleştirme |

---

## 1. Görev 3'ün Tam Akışı

`Gorev3Orchestrator.run()` (`core/mission/gorev3_orchestrator.py`, 81 satır) dört fazı sırayla yürütür:

```
  [precondition]  check_gorev3_precondition(interlock)      gorev3_precondition.py (14 satır)
        │         interlock.both_released() -- iki payload da bırakılmadan Görev 3'e GİRİLMEZ
        ▼
  GOREV3_START ──► GOREV3_RUNNING (pickup)                  gorev3_pickup.py   (1005 satır)
        │         başarısız → MISSION_FAILED (gorev3_pickup_failed)
        ▼
  GOREV3_RUNNING (transport)                                gorev3_transport.py  (43 satır)
        ▼
  GOREV3_RUNNING (redrop)                                   gorev3_redrop.py    (172 satır)
        │         başarısız → MISSION_FAILED (gorev3_redrop_failed)
        ▼
  RETURN_TO_CHECKPOINT (finish)                             gorev3_finish.py     (48 satır)
        ▼
  GOREV3_COMPLETE
```

**Destek modülleri:** `hook_seating.py` (317), `visual_alignment.py` (397),
`visual_placement.py` (301), `rectangle_alignment_strategy.py` (62).
Toplam Görev 3 yüzeyi ≈ **2.440 satır** — `gorev3_pickup.py` tek başına %41'i.

**Faz durumları:** Görev 3'ün kendi `MissionPhase` girdileri yalnızca üç tane
(`GOREV3_START`, `GOREV3_RUNNING`, `GOREV3_COMPLETE`); alt fazlar
(`pickup`/`transport`/`redrop`/`finish`) `transition_to(..., reason=...)` ile
ayırt ediliyor, ayrı enum değeri yok.

---

## 2. Testler Neden "Başarısız" Sanılıyor — G1/G2

### 2.1 Birim testleri geçiyor

```
tests/test_gorev3_pickup.py  tests/test_gorev3_transport.py  tests/test_gorev3_redrop.py
→ 13 passed
```

Yani **kod tabanında kırık bir Görev 3 testi yok.** Karışıklığın kaynağı,
2026-09-02 canlı SITL koşumundaki `gorev3_pickup_failed` sonucu.

### 2.2 Canlı Faz 1 başarısızlığının kök nedeni (G2 — kesin)

Ölçülen olay dizisi (2026-09-02 13:52):

```
13:52:20  Mavi Altıgen konumuna 1.5m irtifada gidiliyor: 47.3985602, 8.5461869
13:52:23  GOREV3_PICKUP_STEP transit_complete
13:52:31  [ERROR] Kırmızı Dikdörtgen bulunamadı -- Görev 3 Faz 1 başarısız.
```

Arada **8 saniye** var ve bu tam olarak şuna denk geliyor:

`gorev3_pickup.py::_locate_target_with_retries()`
- `GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS = 80` deneme
- her denemede `await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)` = 0.1 s
- **80 × 0.1 = 8.0 s**

Fonksiyonun tamamı şu: `visibility_strategy.locate_target()` çağır, `RuntimeError`
alırsan 0.1 s bekle, tekrar dene. **Aracı hiçbir yere hareket ettirmiyor.**

Geometri (o koşumun üretilen sahası):

| | Konum | |
|---|---|---|
| `blue_hexagon` (MAVI_ALTIGEN) | x=−7.779, y=93.111 | aracın gittiği yer |
| `red_square` (KIRMIZI_DIKDORTGEN) | x=−2.358, y=87.331 | aranan hedef |
| **Aralarındaki mesafe** | **7.92 m** | |

Kadraj: kodun kendi ölçümüne göre (`gorev3_pickup.py:483` civarı) 0.30 m'de
0.71 × 0.53 m. `GOREV3_TRANSIT_ALTITUDE_M = 1.5 m`'de ≈ **3.55 × 2.65 m**,
yarı-köşegen ≈ 2.22 m. **7.92 m uzaktaki hedef kadrajın tamamen dışında.**

Kanıt: `KIRMIZI_DIKDORTGEN` görev boyunca 12 karede tespit edildi — sonuncusu
13:52:18'de, Faz 1 başlamadan **2 saniye önce**. Faz 1 penceresinde
(13:52:20–31) **hiç** görülmedi.

**Tasarım varsayımı:** `gorev3_pickup.py:438-441`'deki yorum, Faz 1'in
Kırmızı Dikdörtgen'i **Mavi Altıgen'in konumunda** bulmayı beklediğini
söylüyor. `generate_competition_area.py` ise yalnızca *Altıgen↔Üçgen ≥ 25 m*
kısıtını uyguluyor; **altıgen ile kareyi birbirine yakın tutan hiçbir kısıt
yok**. Yani rastgele yerleşimle bu varsayım neredeyse her koşumda ihlal olur.

> **Sonuç:** hata bir "arama yetersizliği" değil, bir **varsayım ihlali**.
> Deneme sayısını artırmak çözmez — araç hareket etmedikçe hedef asla kadraja girmez.

---

## 3. Climb-then-Cruise'u Görev 3'e Entegre Etmek — G3

Görev 3'ün **üç GPS navigasyon bacağı** var, üçü de hâlâ eski yolda:

| # | Yer | Hedef | İrtifa | Şu anki çağrı |
|---|---|---|---|---|
| L1 | `gorev3_pickup.py:441` | Mavi Altıgen (kayıtlı GPS) | `GOREV3_TRANSIT_ALTITUDE_M` = **1.5 m** | `goto_global_position_and_wait` |
| L2 | `gorev3_transport.py:39` | Kırmızı Üçgen (kayıtlı GPS) | **1.5 m** | `goto_global_position_and_wait` |
| L3 | `gorev3_finish.py:41` | Checkpoint (start/finish) | `checkpoint_alt` (≈15 m) | `goto_global_position_and_wait` |

Ayrıca **rota yeniden katılım** (`gorev2_orchestrator.py:484`) de eski yolda ama
o Görev 2'ye ait ve `ENABLE_ROUTE_REJOIN=False` olduğu için şu an ölü kod yolu.

### 3.1 Bu bacaklarda beş state nasıl davranır

Hareket makinesinin yapısal özelliği: `cruise_alt = max(start_alt, target_alt)`
olduğu için **CLIMB ve DESCEND aynı bacakta ASLA birlikte tetiklenemez**
(`motion_fsm.py:221-225`).

| Bacak | Araç nereden gelir | Hedef | Tetiklenecek |
|---|---|---|---|
| **L1** | ~15 m (Görev 2 sonu) | 1.5 m | CRUISE **+ DESCEND** ← projedeki **tek DESCEND fırsatı** |
| **L2** | ~0.3–1.5 m (alma sonrası) | 1.5 m | CLIMB + CRUISE |
| **L3** | ~0.3 m (bırakma sonrası) | ~15 m | CLIMB + CRUISE |

> **L1, DESCEND'i gerçekten uçuran tek yerdir.** Görev 2 tarafında hiçbir bacağın
> hedefi araçtan alçakta değil, bu yüzden DESCEND bugüne kadar hiç çalışmadı.

### 3.2 Pickup fazı için ek gereksinim

L1'i Climb-then-Cruise'a almak **G2'yi çözmez** — araç yine altıgenin üzerine
gider. G2 için ayrıca bir **arama davranışı** gerekir (aracı hareket ettiren);
bu, `_locate_target_with_retries`'ın yerine geçecek yeni bir mantıktır ve
Climb-then-Cruise entegrasyonundan **bağımsız** bir iş kalemidir.

---

## 4. `activate_pickup_mechanism` Bu İşin Kapsamında mı — G5

**Ayrı iş kalemi.** Gerekçe:

- SITL'de `GzPayloadActuator` kullanılıyor ve onun gövdesi **gerçek**
  (HookAttachSystem / DetachableJoint). Faz 1'in SITL başarısızlığı
  aktüatörden **önce**, hedef bulunamadığı için oldu — servo tetikleme anına
  hiç ulaşılmadı.
- `RealPayloadActuator.activate_pickup_mechanism` imzası B2'de düzeltildi
  (artık `TypeError` yok), gövdesi bilinçli olarak no-op + `# AYAR:` bloğu.
- Dolayısıyla gerçek implementasyon **donanım işidir** ve Görev 3'ün yazılım
  akışını düzeltmekten ayrılabilir.

**Karar sizin** — ama teknik olarak birbirini bloklamıyorlar.

---

## 5. Görev 3'ün Kendi Stabilite Riski — G4

Görev 2'nin dönüş bacağında ölçülen (2026-09-02, ULog):

```
max |v_xy| = 3.13 m/s ,  |dv/dt| p95 = 1.48 m/s^2 ,  varış overshoot 0.56 m
```

**Bu ölçüm 15 m irtifada yapıldı.** Görev 3'ün L1 ve L2 bacakları ise
**1.5 m irtifada** uçuluyor. Aynı hız profili orada uygulanırsa:

1. **Overshoot yerle buluşur.** 0.56 m'lik yatay aşım 15 m'de zararsız; 1.5 m'de
   araç yükün/hedefin üzerinden kayar ve alma denemesi kaçar.
2. **Fren mesafesi irtifadan bağımsız.** 3.0 m/s'den 1.5 m/s² ile durmak ≈ 3 m
   yol ister. `arrival_radius_m = 2.0` bundan küçük — yani araç yarıçapa
   girdiğinde hâlâ frende.
3. **Yer etkisi (ground effect) modellenmiyor.** 1.5 m, x500 için rotor
   çapının ~2-3 katı; bu bölgede itki artar ve irtifa tutma bozulur. Görev 2
   ölçümü bu rejimi hiç görmedi.
4. `GOREV3_TRANSIT_SPEED_M_S = 2.0` tanımlı ama **uygulanmıyor** —
   `gorev3_transport.py:33` bunu kendisi belgeliyor. Yani bugün L2 PX4'ün
   kendi hızıyla uçuyor; aynı uçuşta ölçülen PX4 AUTO.MISSION bacakları
   **5.04 m/s** yapıyordu.

> **Ham gözlem, eşik önermiyorum:** Görev 3 bacakları için hız/ivme/varış
> yarıçapı değerleri Görev 2'den **devralınmamalı**; 1.5 m'de ayrıca ölçülmeli.
> `motion_profile`'a Görev 3'e özel bir alt profil gerekip gerekmediği
> kararı sizindir.

---

## 6. Önerilen İmplementasyon Sırası (onay bekliyor)

| Sıra | İş | Gerekçe |
|---|---|---|
| **1** | **G2**: Faz 1 arama davranışı — `_locate_target_with_retries` aracı hareket ettirmeli (ya da hedefe kendi kayıtlı GPS'inden gidilmeli) | Faz 1 bugün **her koşumda** düşüyor; altındaki hiçbir şey test edilemiyor |
| **2** | **L3** (finish bacağı) → `goto_waypoint()` | En düşük risk: yüksek irtifa, Görev 2'nin dönüş bacağıyla aynı rejim, ölçümü zaten var |
| **3** | **L1** → `goto_waypoint()` + **DESCEND'in ilk gerçek ölçümü** | Projedeki tek DESCEND fırsatı; ama 1.5 m rejimi ölçülmeden hız devralınmamalı |
| **4** | **L2** → `goto_waypoint()` + `GOREV3_TRANSIT_SPEED_M_S`'in gerçekten uygulanması | En riskli bacak (alçak + yüklü); 1-3 ölçülmeden yapılmamalı |
| **5** | `activate_pickup_mechanism` gerçek implementasyonu | Donanım işi, yazılım akışından bağımsız |

**Uyarı:** 3 ve 4, aracı 1.5 m'de otonom yatay uçuşa sokar. O rejimde
overshoot ve yer etkisi ölçülmeden gerçek donanımda denenmemelidir —
`motion_profile.enabled` gerçek uçuşta zaten `false` (kalibrasyon kapısı).

İmplementasyona geçmedim; onayınızı bekliyorum.
