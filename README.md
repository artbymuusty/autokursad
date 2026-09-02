# KURSAD40 WorkSpace

TEKNOFEST Döner Kanat KURSAD40 uçuş sistemi — PX4 Autopilot tabanlı, KURSAD40'a
özel Gazebo dünyası/modelleri ve **V34** görev yazılım yığını ile birlikte.

---

## Usage

### Repoyu yeni klonladıysan: **[SETUP.md](SETUP.md) ile başla**

Bu depo tek bir cihazda çalışacak şekilde ayarlanmış çok sayıda **cihaza-özel
değer** içerir: gz-transport partition kimliği, Python ortam yolu, Gazebo
binding yolları, uçuş kontrolcüsü seri portu, kamera cihaz index'i, dört servo
AUX kanalı, saha ışığına göre HSV eşikleri. Bunları kendi cihazına göre
ayarlamadan sistem çalışmaz — çoğu durumda **sessizce** çalışmaz (hata vermez,
sadece sıfır kamera karesi üretir veya bağlanamaz).

[SETUP.md](SETUP.md) bu değerlerin **tamamını** dosya ve satır numarasıyla,
mevcut değeriyle ve "senin cihazında doğru değeri nasıl tespit edeceğin"
komutuyla birlikte listeler.

**En hızlı yol — yapay zekâ ile kurulum:**

Repoyu klonla, repo kökünde bir AI asistanı aç (Claude Code, Cursor, Copilot vb.)
ve şunu yaz:

```
Bu repoyu yeni klonladım. SETUP.md dosyasını oku ve bu sistemi BENİM cihazıma
göre kur: cihazımı tespit et, SETUP.md §12'deki envanterdeki her değeri
doğrula ve gerekiyorsa değiştir, §1-§9'daki kurulum fazlarını uygula ve her
fazın doğrulama komutunu çalıştır. Emin olmadığın hiçbir değeri uydurma,
bana sor.
```

Promptun tam ve ayrıntılı hâli [SETUP.md §0](SETUP.md#0-ai-ile-kurulum-promptu-kopyalayapıştır)'da.

**Elle kurulum:** [SETUP.md](SETUP.md) §1'den §9'a sırayla ilerle.

### Kurulum sonrası hızlı çalıştırma

```bash
# Simülasyon (iki ayrı terminal)
./safe_sitl_launcher.sh                          # terminal 1: PX4 SITL + Gazebo
.scripts/olds/v34/run_mission_v34_gz.sh          # terminal 2: görev yürütücü

# Gerçek uçuş
.scripts/olds/v34/run_mission_v34_real.sh

# Dual mod (gölge test: simülasyon + gerçek eşzamanlı)
.scripts/olds/v34/run_mission_v34_dual.sh

# Testler (donanım gerektirmez)
PYTHONPATH=$PWD/.scripts/olds/v34/v34_flight_stack \
  python3 -m pytest .scripts/olds/v34/v34_flight_stack/tests -q

# Canlı SITL entegrasyon testi (simülatörü kendisi ayağa kaldırır)
.scripts/olds/v34/v34_flight_stack/tests/integration/run_sitl_integration.sh
```

> Simülatörü **her zaman** `safe_sitl_launcher.sh` ile başlat, düz
> `make px4_sitl gz_...` ile değil. Launcher ortamı temizler, yetim
> Gazebo/PX4 süreçlerini öldürür, gz-transport partition'ını sabitler ve
> takılı kalmış LAND modunu temizler — bunların her biri daha önce görev
> kaybettirmiş bir hataya karşılık gelir. Ayrıntı: [SETUP.md §5](SETUP.md) ve
> [§13](SETUP.md).

### Üç çalıştırma yolu ve neyi paylaştıkları

Görev algoritmasının tamamı `core/` (≈12.000 satır) ve `mavsdk_common/`
içindedir ve **üç yolda da birebir aynıdır**. Ortama özel olan yalnızca uçuş
backend'i, kamera kaynağı ve payload aktüatörüdür:

| | `run_mission_v34_gz.sh` | `run_mission_v34_real.sh` | `run_mission_v34_dual.sh` |
|---|---|---|---|
| Entrypoint | `gz_system/main_gz.py` | `real_system/main_real.py` | `dual_system/main_dual.py` |
| Uçuş backend | `GzFlightBackend` (`udp://:14540`) | `RealFlightBackend` (seri) | ikisi birden |
| Kamera | Gazebo → ZMQ | `cv2.VideoCapture` | ikisi birden |
| Payload | Gazebo DetachableJoint | **dört servo noktası, no-op** | ikisi birden |
| Config | `gz_system/config/gz_system.yaml` | `real_system/config/real_system.yaml` | gerçek profil öncelikli |

`GzFlightBackend` ve `RealFlightBackend` boş alt sınıflardır — MAVSDK mantığı
tek yerde (`mavsdk_common/mavsdk_backend_base.py`).

### Climb-then-Cruise (dikey/yatay ayrıştırılmış seyir)

Bir seyahat bacağı artık beş state'ten geçer; dikey ve yatay hareket **zamanda
ayrılmıştır**. Eskiden hedefe tek bir mutlak 3B pozisyon setpoint'i gidiyordu
(X, Y, Z aynı anda) ve üç eksende birden büyük hata gören pozisyon kontrolcüsü
aşım/salınım üretiyordu.

```
CLIMB  ──►  HOLD  ──►  CRUISE  ──►  DESCEND  ──►  ARRIVAL_HOLD
(sadece   (≥2 s VE   (sadece      (sadece       (kısa oturma,
 dikey)   attitude    yatay,       dikey,        sonra çağırana
           durgun)    z tutulur)   gerekirse)    devir)
```

- **CLIMB / DESCEND** koşulludur: irtifa farkı toleransın altındaysa atlanır.
- **Seyir her zaman iki ucun YÜKSEK olanından** yapılır — hedef aşağıdaysa
  önce alçalıp alçakta seyretmek engel riski taşır, o yüzden DESCEND
  CRUISE'dan **sonra** gelir.
- **HOLD saf bir bekleme değildir:** çıkış "en az `hold_min_s` (2 s) geçti
  **VE** roll/pitch türevi eşik altında N ardışık örnek kaldı" koşuluna
  bağlıdır. `hold_max_s` emniyet tavanıdır.
- Eşiklerin tamamı `motion_profile` bloğundan okunur; SITL ve gerçek uçuş
  **ayrı profil** taşır.

Ayrıntı: [flight-control-analysis.md](.scripts/olds/v34/v34_flight_stack/docs/flight-control-analysis.md)

### ⚠️ Kalibrasyon kapısı — gerçek uçuşta Climb-then-Cruise KAPALI

`real_system.yaml` içinde `motion_profile.enabled: **false**`. Bu kasıtlıdır.

`vz_settle_m_s` ve `attitude_rate_limit_deg_s` doğrudan **sensör gürültü
tabanına** oturur ve şu an tahmindir (`TODO` işaretli). Kalibre edilmeden
açılırsa state makinesi **ilerlemez**: CLIMB `vertical_timeout_s`'te düşer,
HOLD her bacakta tavanı yer ve 600 s'lik zorunlu görev bütçesi erir.

Kapalıyken `goto_waypoint()` aynen eski `goto_global_position_and_wait()`
davranışına düşer — yani gerçek uçuş bilinen bir zeminde yapılır.

**Açmadan önce:** [climb-then-cruise-hw-checklist.md](.scripts/olds/v34/v34_flight_stack/docs/climb-then-cruise-hw-checklist.md)
§1'deki hover ölçüm protokolünü çalıştır:

```bash
cd .scripts/olds/v34/v34_flight_stack
PYTHONPATH=$PWD python3 tools/measure_motion_noise.py \
    --config real_system/config/real_system.yaml
```

Araç **pilot tarafından** hover'a alınır; araç arm etmez, setpoint göndermez,
yalnızca 60 s telemetri okur. Ölçülen p95'in ~3 katı eşik olarak yazılır ve
`TODO`'lar ölçüm tarihi + log referansıyla kapatılır. Bir test
(`tests/test_calibration_gate.py`) kapının TODO'lar dururken açılmasını
engeller.

### İki dashboard mekanizması

Her iki çalıştırma yolunda da yer kontrol ekranı açılır, ama **farklı
mekanizmayla** (gerekçe: `core/telemetry/ops_center.py`):

| | GZ | Gerçek / Dual |
|---|---|---|
| In-process `MissionOpsDashboard` | **kapalı** (`legacy_dashboard_default="0"`) | **açık** (varsayılan) |
| Ayrı process unified dashboard | ✅ `run_mission_v34_gz.sh` başlatır | — |
| Nerede başlar | `tools/mission_dashboard_unified.py` | `build_ops_center()` → `ops_center.start()` |

`KURSAD40_LEGACY_DASHBOARD=0/1` her iki yönde de ezer;
`KURSAD40_UNIFIED_DASHBOARD=0` GZ'de ayrı process'i kapatır.

**macOS notu (ADR-006):** Cocoa her `cv2` GUI çağrısını ana thread'de ister.
Dashboard macOS'ta `cv2.imshow` yerine `MAIN_THREAD_PAINT` köprüsüne yayın
yapar; köprüyü ana thread'de boşaltan bir pompa olmazsa **hiçbir pencere
açılmaz**. Üç entrypoint de bu pompayı çalıştırır
(`core/runtime/main_thread_gui.py`). Linux/Windows'ta dashboard kendi
thread'inde boyar, pompa devreye girmez.

### Dört servo noktası

Gerçek donanım komutunun yazılacağı **tek yer**
[`real_system/real_payload_actuator.py`](.scripts/olds/v34/v34_flight_stack/real_system/real_payload_actuator.py).
`core/` ve `gz_system/` içinde donanıma özel kod **yoktur**.

| İşaret | Metot | Görev | Kanal (`real_system.yaml`) |
|---|---|---|---|
| `FIRST MISSION SERVO` | `release_payload_at_mavi_altigen` | Görev 2, 1. bırakma | `actuator.mavi_altigen_release_channel` |
| `SECOND MISSION SERVO` | `release_payload_at_kirmizi_ucgen` | Görev 2, 2. bırakma | `actuator.kirmizi_ucgen_release_channel` |
| `THIRD MISSION SERVO` | `activate_pickup_mechanism` | Görev 3 Faz 1 (alma) | `actuator.pickup_channel` |
| `GRAB SERVO` | `activate_drop_mechanism` | Görev 3 Faz 3 (bırakma) | `actuator.drop_channel` |

Dördü de şu an **no-op**: her çağrıda `SIMULE edildi - gercek servo BAGLI
DEGIL` uyarısı basar, sessizce başarılı görünmez. Manuel ayar için her metodun
içindeki `# AYAR:` bloğu açıyı, süreyi ve kanalı tek yerde toplar.

### Yön bulma

| Ne arıyorsun | Nerede |
|---|---|
| Cihaza özel kurulum | [SETUP.md](SETUP.md) |
| Cihaza özel değerlerin tam listesi | [SETUP.md §12](SETUP.md) |
| Bilinen tuzaklar / "çalışmıyor" | [SETUP.md §13](SETUP.md) |
| Mimari kararlar (ADR) | [.scripts/olds/v34/v34_flight_stack/docs/adr/](.scripts/olds/v34/v34_flight_stack/docs/adr/) |
| Görev yazılım yığını | [.scripts/olds/v34/v34_flight_stack/](.scripts/olds/v34/v34_flight_stack/) |
| Climb-then-Cruise analizi | [docs/flight-control-analysis.md](.scripts/olds/v34/v34_flight_stack/docs/flight-control-analysis.md) |
| Gerçek uçuş öncesi checklist | [docs/climb-then-cruise-hw-checklist.md](.scripts/olds/v34/v34_flight_stack/docs/climb-then-cruise-hw-checklist.md) |
| GZ/real parite denetimi | [docs/v34-sistem-denetimi.md](.scripts/olds/v34/v34_flight_stack/docs/v34-sistem-denetimi.md) |
| KURSAD40 Gazebo dünyası ve modelleri | [Tools/simulation/gz/](Tools/simulation/gz/) |
| Görev/kontrol parametreleri | [core/config/parameters.py](.scripts/olds/v34/v34_flight_stack/core/config/parameters.py) |

### Bu depoyu kendi GitHub hesabına bağlama

```bash
git remote set-url origin https://github.com/<KULLANICI_ADIN>/<DEPO_ADIN>.git
git push -u origin main
```

Kendi cihaz ayarlarını commit'lemeden önce [SETUP.md §11](SETUP.md)'i oku —
`GZ_PARTITION`, seri port gibi değerler ortam değişkeni ile override
edilebilir, dosyaya yazıp commit'lersen ekibin kurulumunu bozarsın.

---

# PX4 Drone Autopilot

[![Releases](https://img.shields.io/github/release/PX4/PX4-Autopilot.svg)](https://github.com/PX4/PX4-Autopilot/releases) [![DOI](https://zenodo.org/badge/22634/PX4/PX4-Autopilot.svg)](https://zenodo.org/badge/latestdoi/22634/PX4/PX4-Autopilot)

[![Build Targets](https://github.com/PX4/PX4-Autopilot/actions/workflows/build_all_targets.yml/badge.svg?branch=main)](https://github.com/PX4/PX4-Autopilot/actions/workflows/build_all_targets.yml) [![SITL Tests](https://github.com/PX4/PX4-Autopilot/workflows/SITL%20Tests/badge.svg?branch=master)](https://github.com/PX4/PX4-Autopilot/actions?query=workflow%3A%22SITL+Tests%22)

[![Discord Shield](https://discordapp.com/api/guilds/1022170275984457759/widget.png?style=shield)](https://discord.gg/dronecode)

This repository holds the [PX4](http://px4.io) flight control solution for drones, with the main applications located in the [src/modules](https://github.com/PX4/PX4-Autopilot/tree/main/src/modules) directory. It also contains the PX4 Drone Middleware Platform, which provides drivers and middleware to run drones.

PX4 is highly portable, OS-independent and supports Linux, NuttX and MacOS out of the box.

* Official Website: http://px4.io (License: BSD 3-clause, [LICENSE](https://github.com/PX4/PX4-Autopilot/blob/main/LICENSE))
* [Supported airframes](https://docs.px4.io/main/en/airframes/airframe_reference.html) ([portfolio](https://px4.io/ecosystem/commercial-systems/)):
  * [Multicopters](https://docs.px4.io/main/en/frames_multicopter/)
  * [Fixed wing](https://docs.px4.io/main/en/frames_plane/)
  * [VTOL](https://docs.px4.io/main/en/frames_vtol/)
  * [Autogyro](https://docs.px4.io/main/en/frames_autogyro/)
  * [Rover](https://docs.px4.io/main/en/frames_rover/)
  * many more experimental types (Blimps, Boats, Submarines, High Altitude Balloons, Spacecraft, etc)
* Releases: [Downloads](https://github.com/PX4/PX4-Autopilot/releases)

## Releases

Release notes and supporting information for PX4 releases can be found on the [Developer Guide](https://docs.px4.io/main/en/releases/).

## Building a PX4 based drone, rover, boat or robot

The [PX4 User Guide](https://docs.px4.io/main/en/) explains how to assemble [supported vehicles](https://docs.px4.io/main/en/airframes/airframe_reference.html) and fly drones with PX4. See the [forum and chat](https://docs.px4.io/main/en/#getting-help) if you need help!


## Changing Code and Contributing

This [Developer Guide](https://docs.px4.io/main/en/development/development.html) is for software developers who want to modify the flight stack and middleware (e.g. to add new flight modes), hardware integrators who want to support new flight controller boards and peripherals, and anyone who wants to get PX4 working on a new (unsupported) airframe/vehicle.

Developers should read the [Guide for Contributions](https://docs.px4.io/main/en/contribute/).
See the [forum and chat](https://docs.px4.io/main/en/#getting-help) if you need help!


## Weekly Dev Call

The PX4 Dev Team syncs up on a [weekly dev call](https://docs.px4.io/main/en/contribute/).

> **Note** The dev call is open to all interested developers (not just the core dev team). This is a great opportunity to meet the team and contribute to the ongoing development of the platform. It includes a QA session for newcomers. All regular calls are listed in the [Dronecode calendar](https://www.dronecode.org/calendar/).


## Maintenance Team

See the latest list of maintainers on [MAINTAINERS](MAINTAINERS.md) file at the root of the project.

For the latest stats on contributors please see the latest stats for the Dronecode ecosystem in our project dashboard under [LFX Insights](https://insights.lfx.linuxfoundation.org/foundation/dronecode). For information on how to update your profile and affiliations please see the following support link on how to [Complete Your LFX Profile](https://docs.linuxfoundation.org/lfx/my-profile/complete-your-lfx-profile). Dronecode publishes a yearly snapshot of contributions and achievements on its [website under the Reports section](https://dronecode.org).

## Supported Hardware

For the most up to date information, please visit [PX4 User Guide > Autopilot Hardware](https://docs.px4.io/main/en/flight_controller/).

## Project Governance

The PX4 Autopilot project including all of its trademarks is hosted under [Dronecode](https://www.dronecode.org/), part of the Linux Foundation.

<a href="https://www.dronecode.org/" style="padding:20px" ><img src="https://dronecode.org/wp-content/uploads/sites/24/2020/08/dronecode_logo_default-1.png" alt="Dronecode Logo" width="110px"/></a>
<div style="padding:10px">&nbsp;</div>
