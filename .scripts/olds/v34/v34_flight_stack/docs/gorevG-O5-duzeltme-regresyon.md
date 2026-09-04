# GÖREV G / Ö5 — düzeltmenin regresyon kanıtı ve eşik envanteri

**Tarih:** 2026-09-04 · **Düzeltme commit:** `3c816f8f` · **Push edilmedi**
**Test paketi:** 541 geçti, 1 atlandı, 0 başarısız

---

## 1 · Görev 2'ye özgü yollar — ayrı inceleme (istenen madde 1)

`motion_fsm` bilerek incelendi. **Sürpriz var ve önceden not edildi:**

| yol | irtifayı nasıl sürüyor | düzeltmeden etkilenir mi |
|---|---|---|
| `goto_position_ned_and_hold(n, e, −alt, …)` | **NED pozisyon setpoint'i** | ❌ hayır — setpoint zaten aynı çerçevede |
| `motion_fsm` CLIMB / HOLD guard (`:286`, `:292`) | `get_global_position()` ile `alt_error`, `alt_tol_m` + `vz_settle_m_s` | ✅ **evet** |
| `motion_fsm` CRUISE irtifa tutma (`:394`, `:421-422`) | `down_m_s = kp_altitude · alt_error` — **kapalı çevrim** | ✅ **evet** |
| `payload_release` / `descend_to_release` | `get_global_position()` ile iniş bandı | ✅ **evet** |

Yani düzeltme, bu bacakların uçtuğu **gerçek** irtifayı 0.178 m aşağı
kaydırıyor. Öngörülen kaymalar (ölçülen zincirden: gerçek = okuma + 0.299
→ okuma + 0.121):

| bacak | okuma | bugünkü gerçek | düzeltme sonrası gerçek |
|---|---|---|---|
| Görev 2 bırakma | 0.45 | 0.749 | **0.571** |
| Görev 3 iniş | 0.30 | 0.599 | **0.421** |
| görsel hizalama | 0.90 | 1.199 | **1.021** |
| redrop rest (en alçak) | 0.12 | 0.419 | **0.241** |

En alçak komut bile pozitif kalıyor — zemin çarpma riski yok.

---

## 2 · ZORUNLU REGRESYON — Görev 2 isabeti (istenen madde 2)

**3 bağımsız koşum (d1, d2, d3), her birinde tam SITL yeniden başlatma.
Üçünde de `RELEASED=2` ve `SEARCH_COMPLETE=1` — Görev 2 eksiksiz tamamlandı.**

Hedef merkezine uzaklık, şekil bazında:

| | n | min | **ortanca** | max | ortalama |
|---|---|---|---|---|---|
| **ÖNCE** `MAVI_ALTIGEN` | 11 | 0.020 | **0.110** | 0.181 | 0.123 |
| **SONRA** `MAVI_ALTIGEN` | 3 | 0.050 | **0.095** | 0.122 | **0.089** |
| **ÖNCE** `KIRMIZI_UCGEN` | 11 | 0.155 | **0.273** | 0.398 | 0.266 |
| **SONRA** `KIRMIZI_UCGEN` | 3 | 0.239 | **0.274** | 0.393 | 0.302 |

**Hüküm: BOZULMA YOK.**
- `MAVI_ALTIGEN` **iyileşti** (ortanca 0.110 → 0.095; ortalama 0.123 → 0.089).
- `KIRMIZI_UCGEN` ortancası **birebir aynı** (0.273 → 0.274). Ortalaması
  0.266 → 0.302; bu tek bir örnekten (d1 = 0.393) geliyor ve **önceki
  dağılımın içinde** (öncede de 0.398 vardı). n=3 ile ortalama farkı
  anlamlı değil.

"Muhtemelen iyileşir" varsayımıyla ilerlenmedi; ölçüldü, ve
`KIRMIZI_UCGEN`'de iyileşme **yok** — sadece bozulma da yok.

---

## 3 · İKİNCİ BAĞIMSIZ DOĞRULAMA — `[HIZA_KALIBRASYON]` oranı (istenen madde 3)

`_rect_pixel_offset()` piksel→metre çevrimini `get_global_position()[2]`
ile yapıyor. Okuma bozukken görüntü tahmini de o oranda bozuluyordu.

| | görüntü/gerçek oranı |
|---|---|
| **ÖNCE** (r1, r2b, r3b, r5b) | **0.30× / 3.43× / 0.15× / 0.48×** |
| **SONRA** (d1, d2) | **1.02× / 1.68×** |

**Oran 1'e yaklaştı ve saçılım daralttı** — öncesinde 0.15–3.43 (23 kat
aralık), sonrasında 1.02–1.68 (1.6 kat).

**ÜÇÜNCÜ, kendiliğinden gelen işaret:** aynı satırdaki raporlanan irtifa
**0.70–0.71 m → 0.89–0.90 m** oldu ve komut edilen
`HOOK_VISUAL_ALIGN_ALTITUDE_M = 0.90` ile **artık örtüşüyor.** Düzeltme
öncesi 0.19 m'lik fark, ölçülen datum kaymasıyla birebir aynı.

Bu, teşhisin **bağımsız üçüncü doğrulamasıdır**: ne Görev 2 isabetiyle ne
ULog karşılaştırmasıyla ilgisi var.

---

## 4 · EŞİK ENVANTERİ — "bozuk okumayla mı kalibre edildi" (istenen madde 4)

> Bu bir **liste**; kontroller ayrı bir doğrulama turunda sırayla yapılacak.
> "Etkilenir mi" sütunu, eşiğin `get_global_position()[2]` okumasına
> **bağlı olup olmadığını** söyler — yanlış olduğunu değil.

### 4.1 Doğrudan etkilenenler (okuma ile karşılaştırılıyor)

| eşik | değer | nerede | etkilenir? | not |
|---|---|---|---|---|
| `MOTION_ALT_TOL_M` | yaml | `motion_fsm:66,292` | ✅ **evet** | CLIMB/HOLD guard'ı `alt_error`'ı bu okumadan alıyor |
| `MOTION_VZ_SETTLE_M_S` | yaml | `motion_fsm:67,292` | ⚠️ **dolaylı** | hız terimi; ama guard'ın diğer yarısı okumaya bağlı |
| `kp_altitude` | 0.5 | `motion_fsm:144,422` | ✅ **evet** | kapalı çevrim kazancı, hata bu okumadan |
| `GOREV3_DESCENT_ALTITUDE_M` | 0.30 | `parameters:63` | ✅ **evet** | hem setpoint hem salım girdisi |
| `HOOK_VISUAL_ALIGN_ALTITUDE_M` | 0.90 | `gorev3_pickup:66` | ✅ **evet** | ölçülerek seçilmişti (0.30→0.55→0.90) |
| `HOOK_ALIGN_ALTITUDE_M` | 1.2 | `gorev3_pickup:33` | ✅ **evet** | "1.2 m'de yük 63×22 px" gerekçesi bu okumaya dayanıyor |
| `LOW_ALT_VISION_LIMIT_M` | 2.0 | `parameters:540` | ✅ **evet** | ölçülerek seçildi |
| `LOW_ALT_VISION_LIMIT_BY_SHAPE` | 0.5 | `parameters:558` | ✅ **evet** | aynı |
| `PAYLOAD_RELEASE_ALTITUDE` (0.45) | — | `payload_release` | ✅ **evet** | bırakma bandı |
| `GOREV3_REDROP_REST_HEIGHT_M` | 0.12 | `parameters:72` | ✅ **evet** | en alçak komut |
| Görev G §2.4 kadraj tablosu | — | `docs/gorevG-*` | ✅ **evet** | 1.5 m sanılan irtifa gerçekte ~1.8 m'ydi |

### 4.2 ETKİLENMEYENLER (bilerek okumadan bağımsız)

| eşik | neden bağımsız |
|---|---|
| **Ö3 doyum sınırı** (`_reach_shortfall_m`) | Ölçütü `ulaşılan_salım + (−insertion)`; irtifa girmiyor. Bir test bunu (`test_olcut_SABIT_ICERMEZ`) koruyor. **Canlıda d1/d2'de tetiklendi.** |
| `HOOK_WINCH_MAX_EXTENSION_M` (0.35) | SDF eklem limitinden geliyor (`model.sdf` `HookRopeJoint`), okumadan değil |
| **E4a** `EKF2_OF_CTRL` | Airframe parametresi; irtifa okumasıyla ilgisiz |
| `MOTION_ATTITUDE_RATE_LIMIT` (15°/s) | Attitude, irtifa değil |
| Oturma kapıları (`SEAT_*`) | Gazebo kanca pozundan; telemetri girmiyor |
| K6 `OFFBOARD_PAUSE_SETTLE_S` | Zamanlama; irtifa yok |
| `HSV_*` tespit eşikleri | Piksel/renk; irtifa yok (ama **kadraj analizi** etkilendi, §4.1 son satır) |
| Tespit tavanı (`_detection_ceiling_m`) | İç parametrelerden türetiliyor; ama **karşılaştırdığı `alt` bu okumadan** → ⚠️ sınırda, kontrol edilmeli |

---

## 5 · Görev 3'ün durumu — düzelmedi, ama artık ölçülebilir

3 koşumun 3'ünde de Faz 1 hâlâ başarısız:
- d1, d2: **Ö3 doyum koruması tetiklendi** — gereken salım **0.395 / 0.429 m**,
  sınır 0.350 m. 1 deneme yapıldı, 2 atlandı.
- d3: FAIL#1 (tespit).

**Kalan açık tam olarak öngörüldüğü yerde:** gereken 0.395–0.429, komut
0.330 → eksik **0.065–0.099 m**, ve bu, ölçülen **EKF↔gerçek farkıyla
(0.121 m)** aynı mertebede. Yani datum düzeltildi; geriye **kestirim
hatası** kaldı ve telemetri katmanında düzeltilemez.

---

## 6 · Kapsam ve sınırlar

- Regresyon: **n=3 koşum / 6 bırakma**. Öncesi n=11 / 22. `KIRMIZI_UCGEN`
  ortalamasındaki fark n=3 ile ayırt edilemez.
- `[HIZA_KALIBRASYON]` sonrası örneklem **n=2** (d3 o adıma ulaşmadı).
- `−down_m == −local.z` eşitliği hâlâ yapı argümanı; bu turda da ayrıca
  ölçülmedi. Ama raporlanan irtifanın komutla örtüşmesi (§3) dolaylı kanıt.
- §4 bir **envanter**, doğrulama değil.
