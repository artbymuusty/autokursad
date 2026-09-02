# Flight Control Analiz Raporu — "Climb-then-Cruise" Entegrasyon Ön Çalışması

**Tarih:** 2026-09-02
**Kapsam:** FAZ 1 — yalnızca inceleme ve raporlama. Bu çalışmada **hiçbir kod değişikliği yapılmamıştır.**
**İncelenen kod tabanı:** `.scripts/olds/v34/v34_flight_stack` (KURSAD40 V34 Mission System)

> **Dosya konumu notu:** Bu rapor `v34_flight_stack/docs/` altına yazıldı, depo kökündeki
> `docs/` dizinine değil. Depo kökü bir PX4 fork'udur ve oradaki `docs/` upstream PX4'e aittir;
> projenin kendi dokümanları (ADR-004…ADR-011) zaten bu dizinde durmaktadır.

---

## 0. Yönetici Özeti

Üç cümlelik sonuç:

1. **İstenen state machine'in dört state'inin üçü, ayrı ayrı primitif olarak zaten mevcut** —
   `climb_to_altitude()` (saf dikey), `hold_position()`/`hover_and_confirm()` (pozisyon kilidi),
   `goto_global_position_and_wait()` (nokta-nokta seyir). Eksik olan şey bunları **birleştiren ve
   guard'larla yöneten bir üst katman** ile CRUISE'daki **dikey/yatay ayrıştırması**.
2. **Asıl kuplaj noktası `goto_global_position_and_wait()`** — mutlak 3B pozisyon setpoint'i
   (`north, east, down` aynı anda) gönderiyor; X, Y ve Z birlikte hareket ediyor. Tarif edilen
   "dengesiz/diagonal" davranışın kaynağı burasıdır.
3. **En büyük risk teknik değil, kapsamsal:** `go_to_and_center()` (görsel merkezleme) de üç eksenli
   kuplajlıdır, ancak bu kuplaj **kasıtlıdır ve ölçümle ayarlanmıştır** (ADR-009/ADR-010). Yeni state
   machine bu fonksiyona uygulanmamalıdır — yalnızca GPS transit bacaklarına uygulanmalıdır.

---

## 1. Mevcut Mimari

### 1.1 Katman diyagramı (gerçek dosya isimleriyle)

```
 ENTRYPOINT           gz_system/main_gz.py      real_system/main_real.py    dual_system/main_dual.py
      |                        |                          |                          |
      |               gz_system/config/         real_system/config/          (her iki config)
      |                 gz_system.yaml            real_system.yaml
      |                        \__________________________|__________________________/
      |                                          |
      |                                 control_gains YAML'dan enjekte edilir
      |                                 (main_gz.py:129-133, main_real.py:87-91,
      |                                  main_dual.py:104-108)
      v
 GÖREV KATMANI    core/mission/master_fsm.py  ......  MasterMissionController (üst seviye akış)
                  core/mission/phase.py       ......  MissionPhase (30 state, YAŞAM DÖNGÜSÜ FSM'i)
                  core/mission/context.py     ......  MissionContext.transition_to() -> MISSION_PHASE_CHANGED
                          |
                  gorev2_orchestrator.py / gorev2_fsm.py (PayloadMissionSequencer)
                  gorev3_orchestrator.py -> gorev3_{precondition,pickup,transport,redrop,finish}.py
                  payload_release.py, interlock.py, hook_seating.py
                          |
                          v
 NAVİGASYON       core/navigation/centering_controller.py  (1151 satır — TÜM hareket primitifleri)
                  core/navigation/setpoint_limiter.py      (per-eksen rate limit, ADR-010 P4)
                  core/navigation/geo.py                   (haversine, gps_to_ned_delta)
                  core/navigation/checkpoint.py
                          |
                          v
 BACKEND SOYUTLAMA core/interfaces/i_flight_backend.py  ...  IFlightBackend (ABC) + TelemetryStale
                          |
                  mavsdk_common/mavsdk_backend_base.py ...  MavsdkBackendBase (676 satır, TÜM MAVSDK mantığı)
                       /                        \
        gz_system/gz_flight_backend.py     real_system/real_flight_backend.py
              (class ...: pass)                    (class ...: pass)
                          |
                          v
 TELEMETRİ/GÖZLEM  core/telemetry/{event_bus,event_store,watchdog,health,ops_center,mission_logger}.py
                  tools/mission_dashboard_unified.py
```

### 1.2 Kritik gözlem

`GzFlightBackend` ve `RealFlightBackend` **tamamen boş alt sınıflardır** (`pass`). Tüm uçuş kontrol
mantığı `MavsdkBackendBase`'de yaşar ve SITL ile gerçek donanım arasında **bire bir aynıdır**;
farklılaşan tek şey YAML'dan gelen `connection_string`'dir. Bu, istenen "aynı state machine, farklı
backend" gereksinimi için ideal bir zemindir — yeni bir soyutlama katmanı yazmaya gerek yoktur.

---

## 2. Bulgular

### 2.1 Waypoint Navigasyon Mantığı

**İki ayrı rejim var:**

| Rejim | Kim uçuruyor | Nerede |
|---|---|---|
| `AUTO.MISSION` | PX4'ün kendi kontrolcüsü | Arama rotası. Rota **operatör tarafından QGroundControl'de** tanımlanır; sistem rota üretmez, yalnızca doğrular (`confirm_existing_mission()`, `mavsdk_backend_base.py:589`). |
| `OFFBOARD` | Bu kod tabanı | Hedef angajmanı, yük bırakma, tüm Görev 3 fazları, dönüş bacakları. |

**Setpoint tipleri** (`mavsdk_backend_base.py`):

| Metot | Satır | MAVSDK tipi | Anlam |
|---|---|---|---|
| `goto_position_ned()` | 399 | `PositionNedYaw` | **Mutlak 3B pozisyon** (N, E, D birlikte) |
| `goto_position_ned_and_hold()` | 403 | `PositionNedYaw` | Aynısı, `duration_s` boyunca 10 Hz akıtılır |
| `set_velocity_body()` | 420 | `VelocityBodyYawspeed` | Gövde eksenli hız (forward, right, down) |
| `hold_position()` | 424 | `VelocityBodyYawspeed(0,0,0,0)` | Süre boyunca sıfır hız akıtır |

> **NED velocity setpoint'i yoktur.** `IFlightBackend` yalnızca *gövde* eksenli hız sunar. Yaw'a bağımsız
> bir yatay CRUISE için bu bir eksikliktir (bkz. §4.3).

**Navigasyon primitifleri** (`centering_controller.py`):

| Metot | Satır | Eksenler | Not |
|---|---|---|---|
| `go_to_and_center()` | 366 | **X+Y+Z birlikte** | Görsel servolama. `forward/right/down` **tek `_send_setpoint()` çağrısında** komutlanır (620-635, 654). Yakınsama üç hatayı da ister (603-604). |
| `climb_to_altitude()` | 1022 | **Sadece Z** | `_send_setpoint(0.0, 0.0, down_m_s)` (1044). Görüntüden bağımsız. **Zaten CLIMB state'i.** |
| `goto_global_position_and_wait()` | 1053 | **X+Y+Z birlikte** | Hedef NED bir kez hesaplanır, `goto_position_ned(target_n, target_e, -target_alt_m, yaw)` akıtılır (1136). **Asıl kuplaj noktası.** |
| `nudge_forward()` | 997 | Sadece X (gövde) | Kısa ileri öteleme |
| `hover_and_confirm()` | 1142 | Yok (kilit) | `hold_position(duration_s)` sarmalayıcısı |

**Setpoint akışı:** Elle yazılmış döngülerde, `OFFBOARD_SETPOINT_INTERVAL_S = 0.1` → **10 Hz**.

> **Tasarım dokümanındaki bir varsayımın düzeltmesi:** Doküman "MAVSDK bunu otomatik 20 Hz'de gönderir"
> diyor. Bu kod tabanında **öyle değil** — her akış döngüsü elle yazılmıştır (`hold_position`,
> `goto_position_ned_and_hold`, `go_to_and_center`, `climb_to_altitude`,
> `goto_global_position_and_wait`). Kod tabanında bu yüzden çıkmış **en az dört ayrı BUG FIX yorumu**
> vardır (setpoint boşluğu → PX4 ~500 ms sonra Offboard'dan düşüyor). Yeni state machine bu disiplini
> devralmak zorundadır.

**Eksen kuplajı — özet:** Evet, hem görsel merkezlemede (hız setpoint'i, 3 eksen) hem GPS seyrinde
(pozisyon setpoint'i, 3 eksen) tam kuplaj vardır. Kısmi ayrıştırma yalnızca `climb_to_altitude()` ve
`nudge_forward()`'dadır.

### 2.2 State / Mode Yönetimi

- **Var:** `MissionPhase` (`core/mission/phase.py`) — 30 state'lik bir enum, `TERMINAL_PHASES` kümesiyle.
- **Geçiş mekanizması:** `MissionContext.transition_to()` (`context.py:61`) — kilitli, süre ölçen ve
  `MISSION_PHASE_CHANGED` olayını `from_phase / to_phase / previous_phase_duration_s / reason`
  alanlarıyla yayınlayan tek nokta.
- **Bekleme gözlemlenebilirliği:** `set_blocking()/clear_blocking()` + `core/mission/blocking.py`.
- **Üst akış:** `MasterMissionController.run()` → Görev 2 → Görev 3 → başlangıç noktasına dönüş → iniş.

> **Ancak:** Bu bir **görev yaşam döngüsü** FSM'idir, **hareket/yörünge** FSM'i değildir. CLIMB / HOLD /
> CRUISE ayrımı yalnızca "hangi metot çağrıldı" düzeyinde örtük olarak vardır; ne bir state'i, ne bir
> guard'ı, ne de bir geçiş kaydı vardır. İstenen makine bu FSM'in **altına** yeni bir katman olarak
> girmelidir — mevcut FSM'in yerine değil.

`CLIMB_TO_ALTITUDE` adlı bir MissionPhase zaten vardır ama yalnızca kalkış sonrası bir kez kullanılır.

### 2.3 Parametre ve Konfigürasyon

- **Merkezi modül:** `core/config/parameters.py` (724 satır). Sabitler yoğun biçimde ölçüm verisiyle
  belgelenmiştir. Hardcode değil, adlandırılmış sabitler.
- **Ortama özel katman:** `gz_system/config/gz_system.yaml` ve `real_system/config/real_system.yaml`
  içindeki `control_gains` bloğu, üç entrypoint'te de `CenteringController` üzerine enjekte edilir.
  `__init__`'teki (129-136) değerler yalnızca varsayılandır.

**Hareketle ilgili başlıca sabitler:**

| Sabit | Değer | Anlam |
|---|---|---|
| `OFFBOARD_SETPOINT_INTERVAL_S` | 0.1 | Setpoint akış periyodu (10 Hz) |
| `MAX_CENTERING_SPEED_M_S` | 3.0 | Tüm hız komutlarının clamp'i |
| `SETPOINT_MAX_DELTA_V_M_S` | 0.15 | Tick başına maks. hız değişimi → **~1.5 m/s² ivme limiti** |
| `KP_ALTITUDE` | 0.5 | Dikey P kazancı |
| `ALTITUDE_CONVERGENCE_TOLERANCE_M` | 0.3 | İrtifa yakınsama toleransı |
| `GPS_POSITION_CONVERGENCE_TOLERANCE_M` | 2.0 | Yatay varış yarıçapı |
| `GPS_POSITION_VELOCITY_TOLERANCE_M_S` | 0.3 | Varışta hız eşiği |
| `HOVER_DURATION_S` | 2.0 | Hover doğrulama süresi |
| `NORMAL_MISSION_SPEED_M_S` | **None** | *"TODO: ekip tarafından doldurulacak"* — hâlâ boş |
| `GOREV3_TRANSIT_SPEED_M_S` | 2.0 | **Uygulanmıyor** (aşağıya bakınız) |

**İki önemli tespit:**

1. **Proje hiçbir PX4 parametresini set etmiyor.** Kod tabanının tamamında tek bir `param_set` /
   `MPC_*` ataması yoktur. `MPC_XY_CRUISE`, `MPC_ACC_HOR_MAX`, `MPC_JERK_MAX`, `MPC_Z_VEL_MAX_UP/DN`
   ne SITL'de ne HW'de proje tarafından ayarlanır; airframe varsayılanlarına bırakılmıştır.
   Yumuşatma iki yerden gelir: (a) `AUTO.MISSION`'da PX4'ün kendi kontrolcüsü, (b) `OFFBOARD`'da
   projenin kendi P-law + `SetpointLimiter` rate limit'i.
2. **`GOREV3_TRANSIT_SPEED_M_S` bilinçli olarak uygulanmıyor.** Kod tabanı bunu kendisi belgeliyor
   (`gorev3_transport.py:34-38`):
   > *"GOREV3_TRANSIT_SPEED_M_S is not yet actually enforced as a velocity cap here — goto_global_position_and_wait
   > streams position setpoints and lets PX4's own position controller fly toward them at its configured speed;
   > a real speed-limited transit would need a velocity-mode implementation, out of scope for this fix
   > (tracked as a remaining risk, not silently dropped)."*

   **Bu, önerilen CRUISE state'inin kapatacağı, projenin kendi kaydettiği bir açıktır.**

### 2.4 SITL / HW Paralellik Yapısı

**Değerlendirme: güçlü.** Paylaşım şeması:

| Katman | SITL | HW | Paylaşım |
|---|---|---|---|
| Uçuş backend | `GzFlightBackend` | `RealFlightBackend` | **%100 ortak** (`MavsdkBackendBase`), ikisi de boş alt sınıf |
| Navigasyon / görev / FSM | — | — | **%100 ortak** (`core/`) |
| Kamera | `gz_camera_source.py` (gz-transport → ZMQ) | `real_camera_source.py` | Ayrı, `ICameraSource` ardında |
| Payload aktüatör | `gz_payload_actuator.py` (DetachableJoint) | `real_payload_actuator.py` (servo/AUX) | Ayrı, `IPayloadActuator` ardında |
| Konfigürasyon | `gz_system.yaml` | `real_system.yaml` | Ayrı profiller |

**Bilinçli olarak farklılaşan değerler** (`real_system.yaml` yorumlarından):
- `kp_vertical`: SITL 0.5, HW 0.3 — *"a real-vehicle gain must not move on a simulator measurement"*
- Payload kütlesi: gerçek 1.05 kg, simülasyon 0.15 kg (ADR-011 gerekçesi belgelenmiş)

> Yeni eşik değerleri (`ALT_TOL`, `VZ_SETTLE`, `T_HOLD`, `ARRIVAL_RADIUS`) için **hazır ve
> kanıtlanmış bir desen** vardır: `control_gains` gibi bir `motion_profile` bloğu ekleyip aynı üç
> entrypoint'te enjekte etmek.

### 2.5 Test Altyapısı

- **Çerçeve:** `pytest` + `pytest-asyncio` (`pyproject.toml`). ~50 test dosyası.
- **Çalıştırma:** `PYTHONPATH=$PWD python -m pytest tests -q` (flight stack kökünden).
- **Mock'lar:** `tests/mocks/mock_flight_backend.py` — `IFlightBackend`'i implemente eder ve her çağrıyı
  `self.calls` listesine kaydeder; assert'ler bu liste üzerinden yapılır.
- **`conftest.py`:** Duvar-saati beklemelerini (`MISSION_START_HOLD_S`, `MISSION_RESUME_MIN_INTERVAL_S`)
  sıfırlar; testler zamanlamayı değil davranışı ölçer.

> **Kritik boşluk: canlı Gazebo SITL üzerinde çalışan otomatik entegrasyon testi YOKTUR.**
> `udp://:14540` geçen dört test dosyası yalnızca `MavsdkBackendBase`'i mock'lanmış bir `drone` nesnesiyle
> kurar; hiçbiri gerçek bir simülatöre bağlanmaz. FAZ 2'nin istediği entegrasyon testi bu kod tabanındaki
> **ilk** olacaktır — koşum altyapısı (simülatörü ayağa kaldırma, hazır olmasını bekleme, log toplama,
> temizlik) sıfırdan yazılacaktır. Bu, küçümsenmemesi gereken bir iş kalemidir.

#### Baseline koşum sonucu (2026-09-02, bu analiz sırasında alındı)

```
9 failed, 361 passed in 374.72s (0:06:14)
```

**Depo şu anda YEŞİL DEĞİL.** Dokuz başarısızlığın tamamı tek bir işlevsel kümede toplanıyor
(*mission route resume*):

| Dosya | Başarısız test sayısı |
|---|---|
| `tests/test_adr009_stale_health_backoff_speed.py` | 4 |
| `tests/test_mission_route_resume.py` | 3 |
| `tests/test_adr010_retry_in_place_and_resume.py` | 2 |

**Kök neden (doğrulandı):**

```
AttributeError: 'Gorev2Orchestrator' object has no attribute '_route_axis'
  core/mission/gorev2_orchestrator.py:466  (_rejoin_route_axis)
```

Bu testler nesneyi **bilerek** `Gorev2Orchestrator.__new__(Gorev2Orchestrator)` ile kurup
`__init__`'i atlıyor ve yalnızca ihtiyaç duydukları alanları set ediyor
(`tests/test_mission_route_resume.py:36-41`). `ENABLE_ROUTE_REJOIN` `True`'ya çevrilince
(`parameters.py:240`) `_resume_mission_route()` artık `_rejoin_route_axis()`'i çağırıyor
(`gorev2_orchestrator.py:520-521`) ve o da `self._route_axis`'i okuyor — testin hiç set etmediği
bir alan.

**Üretimde bir uçuş hatası DEĞİLDİR:** gerçek akışta `run()` bu alanı atıyor
(`gorev2_orchestrator.py:269`) ve `__init__` de varsayılanını veriyor (satır 154). Bu, geçici bir
bayrak çevrilmesinin tetiklediği **test koşum bayatlığıdır**.

**FAZ 2 için sonucu önemli:** Yeni bir state machine'i temiz bir taban üzerine kurmak gerekir.
Bu dokuz başarısızlık ya bayrak geri alınarak ya da test kurulumları düzeltilerek **implementasyona
başlamadan önce** kapatılmalıdır; aksi halde yeni kodun bir şeyi bozup bozmadığı ayırt edilemez.

### 2.6 Failsafe / Güvenlik

**Mevcut olanlar:**

| Mekanizma | Dosya | Davranış |
|---|---|---|
| `WatchdogEngine` | `core/telemetry/watchdog.py` | Adlandırılmış zamanlayıcılar. **Yalnızca bir tanesi armed:** `MISSION_TIMEOUT` @ 600 s (`ops_center.py:100`) → abort → dönüş → iniş |
| `TelemetryStale` | `i_flight_backend.py:14`, `centering_controller.py:899` | Telemetri bayatlarsa (ADR-009 D1) komut vermeyi derhal durdurur |
| `request_abort()` | `master_fsm.py:56` | Tüm abort kaynaklarının tek girişi; `ABORT_RETURN_DEADLINE_S = 45 s` ile sınırlı |
| `Interlock` | `core/mission/interlock.py` | Aynı hedefe iki kez yük bırakmayı yazılım düzeyinde imkânsız kılar |
| Sağlık izleme | `core/telemetry/health.py` | Alt sistem HEALTHY/DEGRADED durumları |
| Offboard kopması | (örtük) | Setpoint akış disiplini ile *önlenir*; ayrı bir monitör yoktur |

> **Tasarım dokümanının `failsafe_monitor.py` (offboard-loss, geofence, battery) varsayımı bu kod
> tabanında karşılığı olmayan bir varsayımdır.** Geofence ve batarya failsafe'i proje kodunda
> **hiç yoktur** — `grep` ile tüm kod tabanında yalnızca iki yorum satırı geçmektedir. Bunlar
> tamamen PX4 tarafındaki onboard failsafe'lere bırakılmıştır ve proje o parametreleri de set
> etmemektedir (§2.3).
>
> Dolayısıyla FAZ 2'deki *"Mevcut failsafe davranışlarını (offboard-loss, geofence, battery) bozma"*
> maddesi, korunacak bir kod olmadığı için pratikte **"PX4'ün kendi failsafe'lerini tetikleyecek bir
> şey yapma"** anlamına gelir — özellikle setpoint akışını kesmemek ve `MISSION_TIMEOUT` bütçesini
> aşmamak.

---

## 3. "Climb-then-Cruise" Entegrasyon Planı

### 3.1 Önerilen state'lerin mevcut karşılıkları

| Önerilen state | Mevcut karşılık | Eksik olan |
|---|---|---|
| **CLIMB** | `climb_to_altitude()` (`centering_controller.py:1022`) — zaten `vx=vy=0`, saf dikey | Çıkış guard'ı yalnızca `abs(alt_error) < 0.3 m` bakıyor; **`abs(vz) < VZ_SETTLE` koşulu yok**. Ayrıca `timeout_s` varsayılanı 20 s, sabit. |
| **HOLD/STABILIZE** | `hover_and_confirm()` → `hold_position()` (`mavsdk_backend_base.py:424`) | Yalnızca sabit süreli sayaç. **Attitude-rate varyans guard'ı yok.** Telemetri tarafında yalnızca `attitude_euler` (açılar) cache'leniyor, **açısal hız stream'i yok** (`_attitude_watcher`, backend:260) ve `IFlightBackend` yalnızca `get_yaw_deg()` sunuyor — roll/pitch bile dışarı açılmamış. |
| **CRUISE** | `goto_global_position_and_wait()` (`:1053`) | **3B kuplajlı.** Z'nin ayrılması + ayrı bir z-hold gerekiyor. Hız sınırı uygulanmıyor (§2.3). |
| **ARRIVAL_HOLD** | Büyük ölçüde mevcut: yakınsama sonrası `hold_position()` — `master_fsm.py:282-287` tam olarak bu deseni uyguluyor | Formal bir state ve geçiş kaydı yok |

### 3.2 Eklenecek yeni modüller

```
core/navigation/motion_state.py      # MotionState enum: IDLE, CLIMB, HOLD, CRUISE, ARRIVAL_HOLD
core/navigation/motion_fsm.py        # Guard'lar + geçiş mantığı; MissionContext desenini taklit eder
core/navigation/velocity_profile.py  # Trapezoidal / S-curve üreteci
```

Konfigürasyon: `gz_system.yaml` ve `real_system.yaml` içine `control_gains` ile aynı hizada yeni bir
`motion_profile:` bloğu (`alt_tol_m`, `vz_settle_m_s`, `t_hold_s`, `arrival_radius_m`,
`attitude_rate_var_limit`, `cruise_speed_m_s`, `accel_limit_m_s2`), ve `parameters.py` içine
varsayılanları.

### 3.3 Değişecek mevcut dosyalar

| Dosya | Değişiklik | Risk |
|---|---|---|
| `core/navigation/centering_controller.py` | Yeni bir `goto_global_position_decoupled()` metodu; mevcut `goto_global_position_and_wait()` **dokunulmadan bırakılır** (geri dönüş yolu) | Orta — dosya 1151 satır ve yoğun ölçüm yorumu taşıyor |
| `core/interfaces/i_flight_backend.py` | `get_attitude_euler()` (roll/pitch/yaw) ve muhtemelen `set_velocity_ned()` | **Yüksek — aşağıya bakınız** |
| `mavsdk_common/mavsdk_backend_base.py` | Yukarıdakilerin implementasyonu | Düşük — cache zaten var |
| `tests/mocks/mock_flight_backend.py` | Yeni metotların mock'ları | **Yüksek — aşağıya bakınız** |
| 6 × çağrı yeri | `goto_global_position_and_wait` → yeni metot (kademeli) | Orta |

`goto_global_position_and_wait()` çağrı yerleri:
`master_fsm.py:282` (dönüş), `gorev2_orchestrator.py:484` (rota yeniden katılım),
`gorev2_fsm.py:62` (kayıtlı hedefe git), `gorev3_pickup.py:441`, `gorev3_transport.py:39`,
`gorev3_finish.py:41`.

### 3.4 Riskli / kırılgan noktalar

1. **`IFlightBackend`'e `@abstractmethod` eklemek tüm test paketini kırar.**
   `MockFlightBackend` ABC'yi implemente eder; eksik bir soyut metot onu **instantiate edilemez** yapar
   ve ~50 test dosyasının tamamı toplama aşamasında patlar. İki güvenli yol var ve kod tabanında
   **her ikisinin de emsali mevcut:** ya mock'u aynı commit'te güncellemek, ya da `send_status_text`
   gibi (`i_flight_backend.py`, "W4: deliberately NOT abstract") varsayılan implementasyonlu,
   soyut-olmayan bir metot eklemek. İkincisi tercih edilmelidir.

2. **`go_to_and_center()` ayrıştırılmamalıdır.** Üç eksenli kuplajı kasıtlıdır: kademeli iniş
   (`PAYLOAD_APPROACH_ALTITUDES_M = [10.0, 5.0, 0.45]`) alçalırken merkezlemeye devam eder. ADR-009
   (S1/S2 komut tabanları) ve ADR-010 (P4 rate limit) bu davranış üzerinde ölçülmüş ayarlardır.
   Yeni state machine **yalnızca GPS transit bacaklarına** uygulanmalıdır.

3. **Görev 3'ün alçak irtifa fazları kapsam dışı bırakılmalıdır.** 1.5 m ve 0.30 m'de
   `goto_position_ned_and_hold()` ile yapılan gövde eksenli küçük ötelemelerde CLIMB/CRUISE ayrımı
   anlamsızdır ve mevcut ölçülmüş davranışı bozma riski yüksektir.

4. **`SetpointLimiter` atlanmamalıdır.** Yeni FSM hız setpoint'i gönderiyorsa
   `CenteringController._send_setpoint()` üzerinden geçmelidir; aksi halde ADR-010 P4'ün rate limit'i
   devre dışı kalır (o fonksiyonun docstring'i bunu açıkça "the ONE place a velocity setpoint leaves
   this controller" diye tanımlıyor).

5. **Zaman bütçesi.** `MISSION_TIMEOUT = 600 s` Şartname Bölüm 5.6 gereği **zorunludur**. Her bacağa
   eklenecek `T_HOLD` bu bütçeden yer. Referans: 2026-09-02 SITL koşumunda Görev 2, bağlantıdan
   `GOREV2_COMPLETE`'e 206 s sürdü. Kaç bacak × `T_HOLD` ekleneceği hesaplanmalıdır.

6. **Yeni telemetri stream'i eklemek riskli.** Açısal hız için
   `telemetry.attitude_angular_velocity_body()` eklemek yerine, **zaten 10 Hz akan `attitude_euler`
   cache'inden sayısal türev** almak tercih edilmelidir; ADR-008 (B0/B1) bu kod tabanında ek
   tüketici/stream eklemenin çakışma yarattığını belgeliyor.

7. **`ENABLE_ROUTE_REJOIN = True` geçici olarak açık bırakılmış** (`parameters.py:240`, yorum:
   *"TEMP: SITL measurement only ..., reverting after"*). Bu bayrağın akıbeti netleşmeden
   `gorev2_orchestrator.py:484` çağrı yerine dokunulmamalıdır.

---

## 4. Açık Sorular — implementasyondan ÖNCE netleşmeli

1. **Kapsam.** State machine yalnızca GPS transit bacaklarına mı uygulanacak (önerim: **evet**), yoksa
   görsel merkezleme de mi kapsanacak? İkincisi ADR-009/010 ayarlarını geçersiz kılar.

2. **Alçalma yönü.** "Climb-then-Cruise" adı tırmanışı varsayıyor. Hedef irtifa **mevcuttan düşükse**
   sıra ne olmalı? Önce alçalıp sonra alçak irtifada seyretmek engel riski taşır; yaygın pratik
   yüksekte seyredip hedefte alçalmaktır (yani DESCEND state'i CRUISE'dan **sonra**). Bu, dört
   state'lik tasarımı beş state'e çıkarır. Karar sizin.

3. **`T_HOLD` bütçesi.** Kaç transit bacağı var ve toplam ek süre 600 s sınırının neresine düşüyor?

4. **`VZ_SETTLE` ve attitude-rate eşikleri için taban veri yok.** Bu eşiklerin SITL'de ölçülüp
   HW'de gevşetilmesi gerekiyor; ölçüm koşumu bu işin parçası mı, yoksa ayrı bir adım mı?

5. **Hız sınırı.** CRUISE, `GOREV3_TRANSIT_SPEED_M_S = 2.0`'ı gerçekten uygulasın mı (projenin kendi
   kaydettiği açığı kapatarak)? Ve `NORMAL_MISSION_SPEED_M_S = None` nihayet doldurulacak mı?

6. **PX4 parametreleri.** Proje bugüne kadar hiçbir `MPC_*` parametresine dokunmadı. Bu politika
   korunacak mı, yoksa `MPC_ACC_HOR_MAX` / `MPC_JERK_MAX` proje tarafından mı set edilecek?
   (Korumayı öneririm: SITL/HW parite riski ve ADR geçmişi bu yönde.)

7. **Yeşil taban.** Yukarıdaki 9 başarısız test (bkz. §2.5) implementasyondan önce mi kapatılsın?
   Önerim: **evet**, ve tercihen `ENABLE_ROUTE_REJOIN`'i varsayılan `False`'a geri alarak — bayrağın
   kendi yorumu zaten *"reverting after"* diyor. Alternatif, üç test dosyasındaki `__new__` tabanlı
   kurulumlara `_route_axis = None` eklemektir.

8. **Entegrasyon testinin ön koşulu.** 2026-09-02 SITL koşumunda **Görev 3 Faz 1 (Alma) başarısız
   oluyor** (`gorev3_pickup_failed`: Kırmızı Dikdörtgen, Mavi Altıgen'in GPS konumundan 1.5 m
   irtifada aranıyor ama üretilen sahada aralarında ~7.9 m var ve `_locate_target_with_retries()`
   aracı hiç hareket ettirmiyor). Uçtan uca bir entegrasyon testi yazılacaksa bunun önce
   çözülmesi mi, yoksa testin yalnızca Görev 2 bacağını mı kapsaması gerekiyor?

---

## 5. Sonuç

Kod tabanı bu değişikliğe **beklenenden hazır**: backend soyutlaması zaten mükemmel paylaşımlı,
ortama özel config deseni kanıtlanmış, faz geçişi loglama altyapısı hazır, rate limit katmanı mevcut
ve CLIMB primitifi neredeyse olduğu gibi kullanılabilir durumda. Asıl iş üç yerde yoğunlaşıyor:
**(a)** `goto_global_position_and_wait()`'in dikey/yatay ayrıştırması, **(b)** iki guard'ın eklenmesi
(`vz` settle ve attitude stability), **(c)** sıfırdan bir Gazebo SITL entegrasyon testi altyapısı.

En büyük tehlike aşırı kapsam: `go_to_and_center()`'a veya Görev 3'ün alçak irtifa fazlarına
dokunmak, aylarca ölçümle ayarlanmış davranışı geri alır.
