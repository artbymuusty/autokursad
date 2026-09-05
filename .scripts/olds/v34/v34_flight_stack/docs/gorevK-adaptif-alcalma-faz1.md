# GÖREV K — Adaptif alçalma, **FAZ 1: mevcut kod envanteri + pencere ölçümü**

**Tarih:** 2026-09-05 · **Kod değişikliği YOK** (salt analiz)
**Kaynaklar:** `core/mission/gorev3_pickup.py`, `gz_system/gz_payload_actuator.py`,
`core/mission/hook_seating.py`, `core/config/parameters.py`,
`Tools/simulation/gz/models/x500_mono_cam_down/model.sdf`, `docs/gorevI-OA-sonuc-OB-butce.md`

---

## 1 · Adım 1–5: **hepsi zaten var.** Yeniden icat edilmeyecek.

| # | istenen | mevcut kod | durum |
|---|---|---|---|
| **1** | İlk bırakılan yükün kayıtlı konumuna git | `run()` `position_store.get(shape)` → `goto_waypoint(…, 3.0 m)` → `goto_waypoint(…, 1.5 m)` `gorev3_pickup.py:606-673` | ✅ tam |
| **2** | Şekli **büyük ölçekte** odakla/ortala | `_locate_target_with_retries()` + `compute_alignment_yaw` (uzun kenara dik yaw) + `go_to_and_center(rect, 1.2 m)` `:678-713` — 1.2 m'de kadraj **2.84 × 2.13 m** | ✅ tam |
| **3** | Yükü **küçük ölçekte, hassas** odakla/ortala | `_attempt()` ADIM 3-4: dikey iniş 0.30 m → `go_to_and_center(rect, 0.30 m)` `:831-845` — kadraj **0.71 × 0.53 m**; ardından `_rect_pixel_offset()` + görünmezse `_reacquire_by_climbing()` | ✅ tam |
| **4** | Yüke **kilitlen** (referans kayması olmasın) | `VisualHookAligner.align()` → **`vis.receiver_ned`**; yuvanın NED konumu bir kez ölçülüp **saklanıyor**, aşağıda kamera göremezken o kullanılıyor `:962-1010` | ✅ tam |
| **5** | Kilitlendikten sonra **son hassas düzeltme** | `_settle_hook_onto(recv_ned, …, 0.90 m)` — gerçek kanca pozuna karşı kapalı çevrim, 6 düzeltme, hedef 10 mm `:391-464`, çağrı `:1092` | ✅ tam |
| **6** | **Kademeli alçal, kapılar geçilene kadar** | **YOK.** Tek atış: `goto_position_ned_and_hold(_hn,_he,-0.30, yaw, 6.0)` `:1112`, sonra `_start_hold()` tüm pencere boyunca **aynı sabit −0.30**'u tutuyor `:1141` | ❌ **eksik** |
| **7** | **`nose_z` güvenlik alt sınırı** | **YOK.** Depoda kanca burnunun dünya z'sine bakan hiçbir koruma yok. (`_reach_shortfall_m()` var ama o *erişim yetiyor mu* sorusudur, zemin teması değil.) | ❌ **eksik** |

**Sonuç: yalnızca 6 ve 7 yazılacak.** 1–5 için tek gereken, 6'nın 5'ten
sonra doğru yere takılması.

---

## 2 · Pencere ÖLÇÜLDÜ — ve **70 mm genişliğinde**

Kanca zinciri **SDF'den** okundu (uydurma değil):

```
model.sdf:200-206
  hook top     base_link z = -0.1330
  hook bottom  base_link z = -0.19765     <- burun, vinc CEKILIYKEN
  base_link is at z = 0.240 when landed
```

`relative_altitude_m` yerdeyken 0 olduğuna göre base_link'in dünya z'si
`A + 0.240`. Zincir **gergin** iken:

> **nose_z = A + 0.240 − 0.19765 − P = A + 0.04235 − P**

**Çapraz doğrulama:** SDF'nin kendi hesabı (`model.sdf:753-756`)
*"0.30 m iniş irtifasından güverteye ulaşmak 0.272 m salım ister"* diyor.
Formül: `0.30 + 0.04235 − 0.070 = 0.272`. **Birebir.** Bağıntı doğru.

### Görevin kendi salımıyla pencere

`hook_payout_m(0.30) = 0.30 − 0.070 + 0.060 + 0.040 = **0.330 m**` ve bu
salım iniş boyunca **sabit** (`extend_winch_for` 0.90 m'de bir kez çağrılır,
Ö1 kuralı gereği bir daha büyümez). Yani `nose_z = A − 0.28765`:

| olay | gereken irtifa **A** |
|---|---|
| burun **güverteye** değer (`insertion = 0`) | **0.358 m** |
| burun **zemine** değer (`nose_z = 0`) | **0.288 m** |
| **kullanılabilir pencere** | **70 mm** |

Komut edilen **0.30 m**, pencerenin **12 mm** dibinde duruyor.

### Ve bu pencere KAPATILAMAZ

- **Genişliği = güverte yüksekliği (70 mm).** Salımı, payı, `CHAIN_OFFSET`'i
  değiştirmek pencereyi **kaydırır, genişletmez.**
- Ö5'te ölçülen irtifa hatası **90–290 mm**, yani pencerenin **1.3 – 4.1
  katı.**

> **Bu, sabit bir `GOREV3_APPROACH_ALTITUDE_M` değerinin neden çalışamayacağının
> sayısal kanıtıdır.** Hangi sabit seçilirse seçilsin, hata penceresinden
> büyük olduğu için koşumların bir kısmı yukarıda (kanca yetişmez), bir
> kısmı aşağıda (burun zemine gömülür) biter.

### Gözlem ikisini de doğruluyor

| koşum | ölçülen | pencereye göre |
|---|---|---|
| **C1** (gerçek görev) | eksenel boşluk **+61 … +152 mm** (burun güvertenin ÜSTÜNDE), 0/10 kapı | pencerenin **ÜSTÜNDE** |
| **P3** (probe) | `insertion = +46 mm`, `nose_z = −0.0987` | pencerenin **ALTINDA** |

Aynı kod, aynı sabit, **iki zıt arıza.** Beklenen davranış tam da bu.

---

## 3 · Ek bulgu — fazla salım, eğim kapısını kıran şey

Gereken salım `A − 0.02765`, formülün verdiği `A + 0.030` ⇒ **her zaman
57.7 mm fazla.** Kordon gergin bir tel değil: burun bir yüzeye değdiği anda
bu fazlalık **gevşekliğe** dönüşür, zincir bükülür (P3: `span` 0.235 → 0.094,
`fold` 68°'ye kadar) ve kanca yan yatar ⇒ **tilt kapısı 493/493 reddeder.**

SDF bunu zaten yazmış (`model.sdf:748-752`): *"her fazladan santim,
yerdeki kancayı deviren gevşekliğe dönüşür."*

**Dolayısıyla kademeli alçalmanın durma koşulu iki iş birden yapıyor:**
eksenel kapıyı sağlıyor **ve** eğim kapısını öldüren bükülmeyi önlüyor.

---

## 4 · Ölçülecek/uygulanacak — 6 ve 7'nin somut tanımı

**Durma kararının ölçüsü `insertion_m`** (yuvanın kendi çerçevesinde,
`seating_geometry()` zaten üretiyor) — irtifa **değil**. Böylece EKF hatası
denklemden tamamen çıkar.

**Güvenlik alt sınırının ölçüsü `nose_z`** (dünya çerçevesi,
`get_hook_world_pose()` + `HOOK_NOSE_OFFSET_M`). Yanal hata büyükse burun
güverteden yana düşer, `insertion` hiç kapanmaz ve tek koruma zemindir.
Zemin **z = 0**; bu seçilmiş bir sayı değil, dünyanın kendisi. Adım
büyüklüğü her adımda `nose_z ≥ 0` kalacak şekilde kırpılır — yani **sınırın
altına inen bir adım hiç komut edilmez** (aşım payı gerektirmez).

---

## 5 · ÇATIŞMA — 60 s bütçesi zaten dolu

Ö-B'nin C1 ölçümü (`docs/gorevI-OA-sonuc-OB-butce.md`):

```
ön hazırlık          53.5 – 58.6 s
YAKALAMA PENCERESI    1.4 –  6.5 s     <- 60 s'den artakalan
```

Kademeli alçalma **rel_speed kapısı yüzünden sürekli olamaz:** kapı
`≤ 0.05 m/s` ve dwell 0.60 s istiyor; alçalırken kanca da araçla birlikte
iniyor, dolayısıyla **in → dur → ölç** zorunlu. En iyi durumda (oransal adım,
kazanç ~1.0) 1 büyük + 2–3 küçük adım ⇒ mevcut 6.0 s'lik tek inişin yerine
**~11–13 s**, yani **+5 … +7 s**.

**O +6 s, yakalama penceresinin tamamıdır.** Bütçeye başka yerden yer
açılmazsa her deneme 60 s'de kesilir ve kapılar hiç denenmez.

Ö-B'nin zaten ölçülmüş iki seçeneği (henüz **hiçbiri uygulanmadı**):

| # | ne | kazanç |
|---|---|---|
| **B1** | `HOOK_ALIGN_MAX_CORRECTIONS` 6 → 3, reacquire denemeye 1 ile sınırlı | ~15 s |
| **B2** | `_settle_hook_onto`'yu yakalama penceresinin içine al (aynı işi yapıyor) | ~16 s |

**Bu bir mimari karardır ve operatöre soruluyor** — FAZ 2'ye geçmeden önce.

---

## 6 · FAZ 2 planı (onay bekliyor)

1. `_adaptive_descend()` — 5. adımdan sonra, `:1112`'deki tek atış inişin yerine
2. `_start_hold()` ve `activate_pickup_mechanism()` **ulaşılan** irtifayı alsın
   (salım **yeniden hesaplanmasın**: `extend_winch_for` yine 0.30 ile çağrılıp
   Ö1 kuralıyla etkisiz kalmalı, aksi halde fazladan salım kapıyı bozar)
3. Birim test: sahte geometriyle durma koşulu, zemin kırpması, bütçe kesmesi
4. **≥ 2 canlı SITL koşumu** — kilitlenmenin oluştuğu gerçek irtifa
   koşumdan koşuma **değişmeli** (EKF hatasının telafi edildiğinin kanıtı)
5. Ancak sonra P3'ün A/B'si tekrarlanacak
