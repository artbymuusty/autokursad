# Görev D — 2. Payload → Grapple Geçişinde Sert Hareket (FAZ 1: Analiz)

**Tarih:** 2026-09-03 · **Kod değişikliği YOK.**
**Veri:** koşum `90d638b5d3e7` — PX4 ULog + görev olay kaydı + ULog parametreleri.

---

## 0. Sonuç

Bacak **doğrulandı**: `core/mission/gorev3_pickup.py:441`. Ölçüldü:

| | Bu bacak | Climb-then-Cruise dönüş bacağı (referans) |
|---|---|---|
| max \|v_xy\| | **11.92 m/s** | 3.13 m/s |
| \|dv/dt\| p95 / max | **6.33 / 9.29 m/s²** | 1.48 / 1.53 m/s² |
| pitch p95 / max | **30.75° / 42.09°** | 8.19° / 9.34° |
| roll max | 14.19° | 1.98° |
| irtifa | **0.91 – 1.70 m** | 15 m |
| yol | 50.8 m | 66.1 m |

**11.9 m/s, 1.4 m irtifada, 42° pitch ile.** Belirtilen "sert/dengesiz hareket" bu.

---

## 1. Geçiş tam olarak nerede (tahmin değil, kod)

Görev logundan doğrulanan sıra:

```
23:58:09.805  PAYLOAD 2 RELEASED @0.40m
23:58:11.806  1.5m irtifasina tirmaniliyor      <- GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M
23:58:14.425  Gorev 2 tamamlandi
23:58:14.425  Gorev 3 Faz 1 (Alma) Baslatildi
              Mavi Altigen konumuna 1.5m irtifada gidiliyor
```

Kod: `gorev3_pickup.py:441`

```python
converged = await self.centering.goto_global_position_and_wait(
    mavi_altigen_point.gps_lat, mavi_altigen_point.gps_lon, GOREV3_TRANSIT_ALTITUDE_M)
```

`GOREV3_TRANSIT_ALTITUDE_M = 1.5` (`parameters.py:20`).
Görev B/G3'teki tespit doğrulandı: bu bacak **Climb-then-Cruise'a bağlı değil**.

**Mesafe neden büyük:** saha üreticisi *Mavi Altıgen ↔ Kırmızı Üçgen ≥ 25 m*
kısıtı uyguluyor, **üst sınır yok** (`generate_competition_area.py`). Araç
payload 2'yi birine bıraktıktan sonra **diğerine** gitmek zorunda — bu koşumda
ölçülen yol **50.8 m**.

---

## 2. 11.9 m/s nereden geliyor — kanıt

ULog'daki PX4 parametreleri:

| Parametre | Değer | Ölçülen karşılığı |
|---|---|---|
| `MPC_XY_VEL_MAX` | **12.0** | bu bacak: **11.92 m/s** ✓ |
| `MPC_XY_CRUISE` | 5.0 | AUTO.MISSION arama bacakları: 5.04 m/s ✓ |
| `MPC_ACC_HOR_MAX` | 5.0 | bu bacak \|dv/dt\| p95 6.33 (jerk aşımıyla) |
| `MPC_TILTMAX_AIR` | **45.0** | bu bacak max pitch **42.09°** ✓ |

`goto_global_position_and_wait()` **mutlak pozisyon setpoint'i** gönderir; hızı
PX4'ün kendi pozisyon kontrolcüsü seçer ve tavan `MPC_XY_VEL_MAX = 12 m/s`'dir.
Proje **hiçbir `MPC_*` parametresini set etmiyor** (FAZ 1 analizinde saptandı),
dolayısıyla bu tavan varsayılan olarak geçerli.

`GOREV3_TRANSIT_SPEED_M_S = 2.0` tanımlı ama **uygulanmıyor** —
`gorev3_transport.py:33` bunu zaten kendisi belgeliyor. Yani niyet 2 m/s,
gerçekleşen 11.9 m/s.

Zaman serisi (0 = Görev 3 Faz 1 başlangıcı):

```
  +0.0s   0.04 m/s   1.15 m
  +2.0s   3.62 m/s   1.68 m
  +4.0s  11.80 m/s   1.45 m     <- 4 saniyede 0 -> 11.8 m/s
  +6.0s  11.71 m/s   1.49 m
  +8.0s   0.47 m/s   1.50 m     <- 2 saniyede tam duruş
```

---

## 3. Climb-then-Cruise'a bağlamanın önündeki engeller (G4 yeniden değerlendirme)

| Risk | Bu bacak için durum |
|---|---|
| **Fren mesafesi > `arrival_radius`** | 3.0 m/s'den 1.5 m/s² ile duruş ≈ **3.0 m**; `arrival_radius_m = 2.0`. Araç yarıçapa girdiğinde hâlâ frende. **Bugünkü durumdan yine de çok daha iyi:** 11.9 m/s'den 5 m/s² ile duruş ≈ 14 m. |
| **Yer etkisi** | 1.5 m, x500 rotor çapının ~2-3 katı — itki artışı bölgesi. **Hiç ölçülmedi.** 3 m'ye çıkmak bu riski *azaltır*. |
| **Varış overshoot** | Dönüş bacağında 15 m'de 0.56 m ölçüldü. 1.5 m'de aynı overshoot hedefi kaçırır; 3 m'de yatay hareket bittiği için alçalma dikey olur. |
| **DESCEND ilk kez çalışacak** | Bu bacak projedeki **ilk gerçek DESCEND** olur (3 m → 1.5 m). Hiç uçulmamış bir state. |

**Değerlendirme:** bağlamak riski azaltıyor, artırmıyor — 11.9 m/s → 3.0 m/s ve
42° → ~8° pitch. Ama 1.5 m'deki varış hâlâ ölçülmemiş bir rejim.

---

## 4. Önerilen mantık: evet, beş state — ama tek bacakta değil

İstediğiniz davranış (**önce 3 m'ye çık, stabil ol, sonra yatay**) mevcut state
machine'e **birebir oturuyor**:

```
CLIMB (1.5 → 3.0 m) → HOLD (≥2 s + attitude stabil) → CRUISE (3.0 m'de ~50 m)
                                                     → DESCEND (3.0 → 1.5 m) → ARRIVAL_HOLD
```

**Ama yapısal bir kısıt var** (Görev A'da saptandı, `motion_fsm.py:221-225`):
`cruise_alt = max(start_alt, target_alt)` olduğu için **CLIMB ve DESCEND aynı
bacakta asla birlikte tetiklenemez**. `goto_waypoint(hexagon, 1.5)` çağrılırsa:
`cruise_alt = max(1.5, 1.5) = 1.5` → **ne CLIMB ne DESCEND**, düz 1.5 m'de seyir.

Yani "3 m'ye çık, sonra git, sonra in" **tek `goto_waypoint()` çağrısıyla elde
edilemez**. İki seçenek:

**(A) İki çağrı — mevcut mekanizmayla, kod değişikliği minimum**
```python
await centering.goto_waypoint(hexagon.lat, hexagon.lon, GOREV3_CRUISE_ALTITUDE_M)  # 3.0
await centering.goto_waypoint(hexagon.lat, hexagon.lon, GOREV3_TRANSIT_ALTITUDE_M) # 1.5
```
1. çağrı: CLIMB (1.5→3.0) → HOLD → CRUISE (50 m @3 m) → ARRIVAL_HOLD
2. çağrı: yatay mesafe ~0 → DESCEND (3.0→1.5) → ARRIVAL_HOLD
İstenen profil aynen çıkar, `motion_fsm` **hiç değişmez**.

**(B) `fly_leg`'e ayrı bir `cruise_alt_m` parametresi** — beş state tek bacakta
çalışır, ama `cruise_alt = max(...)` kuralı değişir ve mevcut testler etkilenir.

> **Önerim (A).** Mevcut mekanizmayı kullanır, `motion_fsm`'e dokunmaz, aynı
> gözlemlenebilirliği (iki `MOTION_LEG_STARTED`) verir. Karar sizin.

---

## 5. Önerilen implementasyon (FAZ 2 — uygulanmadı)

**Config** — `parameters.py`, `GOREV3_TRANSIT_ALTITUDE_M`'in yanına:
```python
#: Gorev 3 gecis bacaklarinin SEYIR irtifasi. Calisma irtifasi (1.5 m) degil:
#: 50+ m'lik yatay transit 1.5 m'de 11.9 m/s ve 42 derece pitch ile uculuyordu.
GOREV3_CRUISE_ALTITUDE_M: float = 3.0
```
Her iki YAML'a `motion_profile` yanında değil, **ayrı** bir alan olarak da
eklenebilir; öneri: `parameters.py` varsayılanı + iki profilde override.

> **Not:** talimatınızda `GOREV3_TRANSIT_ALTITUDE_M = 3.0` yazıyordu. Bunu
> **değiştirmemeyi** öneririm: o sabit aracın **çalışma/alma irtifası** (1.5 m)
> ve `gorev3_transport.py`, `gorev3_redrop.py`, `gorev2_fsm.py`'nin tırmanış
> hedefi olarak da kullanılıyor — 3.0 yapmak alma geometrisini de kaydırır.
> Yeni ve ayrı bir sabit daha güvenli.

**Kod** — `gorev3_pickup.py:441`, tek satır iki satıra:
- `goto_global_position_and_wait(...)` → iki `goto_waypoint(...)` çağrısı (§4-A)

**Test** — yeni entegrasyon testi (`tests/integration/`):
CLIMB'in gerçekten 3.0 m'ye çıktığını, yatay hareketin **ondan sonra**
başladığını ve DESCEND'in 1.5 m'ye indiğini `MOTION_STATE_CHANGED` sırasından
doğrular. Mevcut `test_gorev3_pickup.py` double'ının `goto_waypoint` tanıması
gerekecek (aynı bayat-double sınıfı, daha önce üç kez karşılaşıldı).

**Kapı:** `motion_profile.enabled` gerçek uçuşta `false` — bu değişiklik SITL'de
etkin, gerçek uçuşta eski yola düşmeye devam eder.

İmplementasyona geçmedim; onayınızı bekliyorum.
