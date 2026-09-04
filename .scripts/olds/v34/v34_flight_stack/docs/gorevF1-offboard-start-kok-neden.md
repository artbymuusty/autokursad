# Görev F1-KÖK — `offboard.start()` neden sessizce komut göndermiyor (FAZ 1)

**Tarih:** 2026-09-04 · **KOD DEĞİŞİKLİĞİ YOK** (geçici dahil).
**Veri:** ①'in gözlenebilirlik alanları (tekilleştirilmiş **14 başarılı /
7 başarısız**, oran **%33.3**) + PX4 ULog `vehicle_command` + MAVSDK 3.17.2
paket içeriği + proje kaynağı.

---

## 0. Kesin teşhis — nereye kadar gidebildim

> **Kanıtlanan:** hata **proje çağrı sırasında DEĞİL**, **yarış durumu DEĞİL**,
> **`pause_mission()` zamanlamasında DEĞİL**. `offboard.start()` gRPC çağrısı
> `SUCCESS` dönüyor ama PX4'e **hiçbir OFFBOARD mod komutu ulaşmıyor**.
>
> **Kanıtlanamayan:** `mavsdk_server`'ın **neden** göndermeden SUCCESS
> döndüğü. Sebep C++ ikilisinin içinde ve **kaynağı bu ağaçta yok**.

---

## 1. `offboard.start()` çağrı zinciri

| katman | konum | ne yapıyor |
|---|---|---|
| Python | `mavsdk/offboard.py:885-901` | `StartRequest()` → gRPC `Stub.Start()` → sonuç `SUCCESS` değilse **`OffboardError` fırlatır** |
| gRPC | — | `mavsdk_server`'a UDS/TCP |
| **C++** | `mavsdk/bin/mavsdk_server` — **Mach-O ikili, KAYNAK YOK** | mod komutunu üretmesi gereken katman |
| MAVLink | UDP 14540 → PX4 | `DO_SET_MODE` |

**Python katmanı istisna atıyor** — dolayısıyla 68 `OFFBOARD_SWITCH_FAILED`
olayının hiçbirinde `{"error": ...}` bulunmaması, `Start()` gRPC çağrısının
gerçekten **`SUCCESS`** döndüğünün kesin kanıtıdır. Olası diğer sonuçlar
(`NO_SETPOINT_SET`, `BUSY`, `TIMEOUT`, `FAILED`) hiç görülmedi.

## 2. Projenin çağrı sırası — **kusursuz, yarış yok**

```python
async def start_offboard(self) -> None:
    initial_setpoint = VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    await self.drone.offboard.set_velocity_body(initial_setpoint)   # AWAIT edilmis
    await self.drone.offboard.start()
```

- Setpoint `start()`'tan **önce** ve **await edilerek** gönderiliyor →
  `NO_SETPOINT_SET` koşulu sağlanmış, nitekim o sonuç hiç dönmedi.
- İki çağrı arasında eşzamanlılık **yok**; ikisi de tamamlanana kadar
  bekleniyor. **Yarış durumu için bir zemin yok.**
- Ayrı bir "streaming task"i yok ki ilk setpoint'i geciktirsin — MAVSDK'nin
  kendi gönderici iş parçacığı `start()` içinde kuruluyor.

**Sonuç: proje tarafında hata yok.**

## 3. Başarılı/başarısız farkı — ①'in verisi

| ölçüt | BAŞARILI (n=14) | BAŞARISIZ (n=7) |
|---|---|---|
| `pause_duration_s` (ortanca) | **0.0145 s** | **0.0170 s** |
| `poll_count` | 2 – 7 | **hepsi tam 15** |
| `confirm_s` | max **1.204 s** | — (3.0 s dolduruldu) |
| `modes_seen` | — | **7/7'sinde tam olarak `(HOLD, MISSION)`** |
| `first_mode` / `last_mode` | — | **7/7: MISSION → HOLD** |

### Bundan çıkanlar

1. **`pause_mission()` 14 milisaniye sürüyor** — başarılı ve başarısız
   denemelerde **aynı**. ADR-009 `:151` / ADR-010 `:270-283`'ün
   *"pause, resume'dan ~1 s sonra düşüyor ve PX4 OFFBOARD'ı reddediyor"*
   anlatısı bu veriyle **bir kez daha çürüyor** — pause zaten anlık ve
   iki grup arasında fark yok.
2. **Bimodal, boşluksuz dağılım:** başarı en geç **1.204 s**'de onaylanıyor;
   başarısızlıklar **istisnasız** 15 yoklamayı (3.0 s) dolduruyor. Arada
   hiçbir gözlem yok → **zaman aşımını büyütmek işe yaramaz** (daha önce de
   ölçülmüştü, burada tekrar doğrulandı).
3. **Her başarısızlıkta gözlenen mod dizisi aynı: MISSION → HOLD.** Yani
   `pause_mission()` **çalışıyor** (araç HOLD/AUTO.LOITER'a geçiyor) ve
   ardından **hiçbir şey olmuyor**. OFFBOARD hiç istenmiyor.
4. **Öncül durum YOK.** Başarısızlıkların 5'i koşumun **ilk** takibinde
   (`önceki_başarı=0, önceki_hata=0`), diğerleri başarılardan sonra.
   Başarılar da başarısızlıklardan sonra geliyor. **"Şu durumdan sonra
   oluyor" diyebileceğim bir örüntü bulunamadı.**

## 4. PX4 tarafı — komut hiç gelmiyor

`DO_SET_MODE` (176) `param2` = PX4 ana modu (**4 = AUTO, 6 = OFFBOARD**).
Başarısız pencerelerde gönderilen tüm `DO_SET_MODE`'lar `param2=4`; **`param2=6`
hiç yok**. Sekiz ULog toplamı: AUTO **53**, OFFBOARD **16**; referans koşumda
2 başarılı giriş ↔ tam 2 adet `param2=6`.

ULog'daki diğer komutlar (1000/1001 gimbal, 2003 kamera tetikleme) MAVSDK'nin
bağlanma anındaki eklenti yoklamaları — **alakasız**.
`VEHICLE_CMD_SET_NAV_STATE (100001)` hiç kullanılmıyor.

> **PX4 hiçbir şeyi reddetmiyor; kendisine sorulmuyor.**

## 5. SITL'e mi özgü, gerçek donanımda da beklenir mi

**Dürüst cevap: bu veriyle KARARA VARILAMAZ.** Spekülasyon yapmıyorum.

Söyleyebileceklerim:
- Arıza **`mavsdk_server` ile PX4 arasındaki MAVLink katmanında**, PX4'ün
  içinde değil. Bu katman gerçek donanımda da **aynı** (aynı ikili, aynı
  protokol) — yalnızca taşıma (UDP-localhost yerine seri/telemetri) değişir.
- Dolayısıyla arızanın **simülatöre özgü olduğunu gösteren hiçbir kanıt yok**;
  ama gerçek donanımda **gözlendiğine** dair de kanıt yok.
- SITL'e özgü olabilecek tek unsur zamanlama: macOS'ta olay döngüsü ve
  `MissionRuntime` iş parçacığı (ADR-006) gerçek uçuş bilgisayarından farklı
  yüklenir. Ama `pause_duration_s`'in iki grupta **aynı** çıkması, kaba bir
  CPU/olay-döngüsü tıkanmasını **desteklemiyor**.

**Karar için gereken:** aynı MAVSDK sürümüyle gerçek donanımda ölçüm — ki bu
saha kalibrasyonu tamamlanmadan yapılmayacak.

## 6. Kalan hipotez ve onu kapatacak şey

Elde kalan en güçlü aday: **`mavsdk_server`'ın `Offboard::start()` çağrısı,
kendi iç durumuna göre "zaten aktif" sayıp komutu göndermeden `SUCCESS`
dönüyor.** Bu, kütüphanenin belgelenmiş kısa-devre davranışıyla uyumlu olurdu.

**Ama bu ağaçta kanıtlanamaz:**
- C++ kaynağı yok (yalnızca derlenmiş ikili)
- Elenmiş rakipler: proje çağrı sırası (bölüm 2), yarış durumu (bölüm 2),
  pause zamanlaması (bölüm 3), setpoint eksikliği (`NO_SETPOINT_SET` hiç
  dönmedi), PX4 reddi (bölüm 4)
- **Zayıflatan gözlem:** başarısızlıkların 5'i koşumun **ilk** takibinde
  oldu; o anda hiç offboard oturumu açılmamıştı, dolayısıyla "bayat aktif
  durum" açıklaması bu vakalar için **doğrudan geçerli değil**. Yani hipotez
  tek başına da yeterli olmayabilir.

---

## 7. ⛔ GÖREV 5 İÇİN İNTERNET GEREKİYOR — DURDUM

Sorunuzun 5. maddesi (MAVSDK sürüm notları / issue tracker'da bu davranışın
bilinen bir kaydı var mı) **internet erişimi gerektiriyor**. CLAUDE.md gereği
rapor veriyorum ve **onayınızı bekliyorum**:

### İNTERNET KULLANIM RAPORU

| | |
|---|---|
| **Yapılacak işlem** | MAVSDK deposunda (`github.com/mavlink/MAVSDK`) `Offboard::start()`'ın sessiz `SUCCESS` dönmesine dair issue/PR/sürüm notu araması; gerekirse `src/mavsdk/plugins/offboard/offboard_impl.cpp` kaynağının **3.17.2 sürümüne karşılık gelen** hâlinin okunması |
| **İndirilecek** | Yalnızca web sayfası/kaynak dosya metni. Depo klonlanmayacak, paket kurulmayacak |
| **Tahmini boyut** | < 2 MB (birkaç sayfa + tek bir .cpp dosyası) |
| **Tahmini tüketim** | Önemsiz |
| **Neden gerekli** | Kalan tek hipotez C++ ikilisinin içinde; yerel ağaçta kaynak yok. Bu olmadan teşhis "sebep `mavsdk_server` içinde, hangisi bilinmiyor" düzeyinde kalır |
| **Zorunlu mu / alternatif** | **Zorunlu değil.** Alternatifler: (a) hipotezi kapatmadan yaşamak — F1 guard'ı zaten zararı sınırlıyor; (b) `mavsdk_server`'ı `--verbose` ile çalıştırıp kendi loglarını okumak (**internet gerektirmez**, ama koşum düzeneği değişikliği ister); (c) MAVSDK'yi kaynaktan derlemek (**büyük indirme**, önermiyorum) |

**Önerim:** önce **(b)** — `mavsdk_server`'ın kendi ayrıntılı logu, komutu neden
göndermediğini kendi seviyesinde söyleyebilir ve internet gerektirmez. İnternet
onayı verirseniz (a)+web araması da hızlı bir kontrol olur.

---

## 8. Önerilen düzeltmeler (uygulanmadı) — trade-off'larıyla

| # | öneri | artı | eksi |
|---|---|---|---|
| **K1** | **`start()` sonrası doğrulama + retry-with-backoff.** Onay gelmezse `start()`'ı 1-2 kez daha çağır (F1 guard'ından **ayrı bir katman**: guard takibi terk eder, bu ise geçişi kurtarmayı dener) | Ölçülen %33'lük kaybın büyük kısmını kurtarabilir; kök nedeni bilmeden de çalışır | ADR-004 `:499` "Offboard geçişi retry değil escalate" diyor — **doğrudan gerilim**, operatör kararı gerekir |
| **K2** | **Onay öncesi setpoint akıtmayı sürdür.** Bugün tek bir setpoint gönderilip 3 s sessizlik var; oysa depo PX4'ün ~500 ms sınırını `parameters.py:343-346`'da kendisi belgeliyor | Doğru hijyen, bedava | Oranı değiştireceğine dair **ölçüm yok**; iki ölçüm aksini düşündürüyor. Uygulayan **deney** saymalı |
| **K3** | **`mavsdk_server --verbose` + logunu artefakta al** | Kalan hipotezi kapatabilir; internet gerektirmez | Koşum düzeneği değişikliği; log hacmi |
| **K4** | **MAVSDK sürümünü değiştirmek** | Bilinen bir bug'sa çözebilir | **İnternet + yeni sürümün regresyon riski**; bilinen bir bug olduğu henüz doğrulanmadı |

**Sıra önerim: K3 → (bulguya göre) K1 veya K2.**
K1'i ADR-004 gerilimi nedeniyle **tek başına** önermiyorum.

Kod değişikliği yapılmadı. F1 guard'ına, F2-a rejoin'ine, Görev C/D/E4e'ye ve
`motion_fsm.py`'a dokunulmadı.

---

# K3 SONUCU — kısa devre KANITLANDI (2026-09-04)

**Yöntem:** projeye **hiç dokunmadan**, projenin `start_offboard()` dizisini
birebir tekrarlayan bağımsız bir tanı betiği
(`scratchpad/e2/k3_repro.py`) + `mavsdk` Python logger'ı **DEBUG**'a alındı.
`system.py:83-100` sunucunun `[ts|Seviye] ...` satırlarını bu logger'a
yönlendiriyor — **CLI'da `--verbose` yok, yol bu.**

Tekrar üretim: SITL + arm/takeoff/mission, ardından 12 kez
`pause_mission → set_velocity_body → start() → 3 s mod yoklaması → stop → resume`.

**Sonuç: 12 denemenin 5'i başarısız (%41.7)** — proje kodu tamamen devre
dışıyken. Hepsinde `err=None`, hepsi HOLD'da kaldı.

## Kusursuz ayrışma

| deneme | sonuç | `start()` süresi | sunucu log satırı |
|---|---|---|---|
| 1, 3, 6, 9, 12 | **FAIL** | 0.6 – 6.8 ms · **ortanca 3.4 ms** | **0** |
| 2, 4, 5, 7, 8, 10, 11 | **OK** | 6.7 – 19.5 ms · **ortanca 11.5 ms** | **1–2** |

**7/7 başarıda sunucu satırı var, 5/5 başarısızlıkta hiç yok. Örtüşme sıfır.**

Başarılardaki satır:
```
[WARNING] mavsdk_server: Received ack for not-existing command: 176!
          Ignoring... (mavlink_command_sender.cpp:304)
```

## Üç soruya cevap

### 1. "Zaten offboard'da" kısa devresi — **KANITLANDI**

FAZ 1'de "zayıf ihtimal, tamamen elenmedi" diye işaretlenmişti. Artık kanıtlı:

- **Başarısızlıklarda sunucudan HİÇ MAVLink trafiği çıkmıyor.** 3.4 ms saf
  gRPC gidiş-dönüşü; MAVLink round-trip'i için çok kısa.
- **Başarılarda çıkıyor** — `mavlink_command_sender.cpp` komut 176'nın
  ACK'ini görüyor ve logluyor. 11.5 ms = gerçek MAVLink round-trip.

Yani `Offboard::start()` başarısız hâlde **komutu hiç üretmeden `SUCCESS`
dönüyor**. Kısa devre `mavsdk_server`'ın Offboard eklentisinde, komut
gönderici katmanına **ulaşmadan önce**.

### 2. Komutun yutulduğu TAM nokta

`mavlink_command_sender.cpp:304` her başarılı gönderimde konuşuyor,
başarısızlıklarda **hiç konuşmuyor** → komut **komut göndericiye hiç
ulaşmıyor**. Yutulma noktası bundan **yukarıda**, Offboard eklentisinin
kendi ön koşul kontrolünde.

### 3. Python'un göremediği seviyede fark — **VAR ve iki yönlü**

Fark yalnızca "başarıda satır var" değil. Satırın **içeriği** ikinci bir
kusuru ele veriyor:

> **`Received ack for not-existing command`** — yani ACK geldiğinde MAVSDK o
> komutu bekleyenler listesinden **çoktan silmiş**. `start()` ACK'i beklemeden,
> **iyimser** biçimde `SUCCESS` dönüyor.

Bu, `SUCCESS`'in neden hiçbir şey kanıtlamadığını açıklıyor: dönüş değeri
komutun gönderildiğini de, PX4'ün kabul ettiğini de temsil etmiyor.
25 böyle uyarı sayıldı.

## Yan gözlem: başarısızlıklar periyodik

Başarısız denemeler: **1, 3, 6, 9, 12** → aralar **2, 3, 3, 3**.
Neredeyse düzenli. Rastgele bir yarıştan çok bir **durum/sayaç döngüsüne**
benziyor. Mekanizmasını kaynak olmadan söyleyemem; **yorum yapmıyorum**,
gözlem olarak bırakıyorum.

## Sürüm bilgisi

```
MAVSDK version: v3.17.2 (mavsdk_impl.cpp:35)
Python paketi : mavsdk 3.17.2
```

## Hâlâ gereken

Kısa devrenin **hangi koşulu** kontrol ettiği yalnızca kaynaktan okunur:
`src/mavsdk/plugins/offboard/offboard_impl.cpp`, **v3.17.2** etiketinde.

Sunucu DEBUG seviyesinde satır yaymıyor (12 denemede 0 adet) — yani
`mavsdk_server` bu bilgiyi log üzerinden **vermiyor**. K3'ün verebileceğinin
sonuna gelindi.

### ⛔ İNTERNET ONAYI TEKRAR İSTENİYOR

| | |
|---|---|
| **İşlem** | `github.com/mavlink/MAVSDK`, tag **`v3.17.2`**, tek dosya: `src/mavsdk/plugins/offboard/offboard_impl.cpp` (+ varsa aynı davranışa dair issue/PR) |
| **İndirilecek** | Tek kaynak dosyanın metni (~30 KB) + birkaç sayfa. **Klonlama yok, kurulum yok** |
| **Boyut / tüketim** | < 1 MB · önemsiz |
| **Neden** | K3 kısa devrenin **varlığını** kanıtladı; **koşulunu** yalnızca kaynak verir |
| **Zorunlu mu** | Hayır. Alternatif: koşulu bilmeden **K1/K2** ile yaşamak (aşağı bkz.) |

## K3 sonrası öneri güncellemesi

K3'ün bulgusu öneri sırasını **değiştiriyor**:

- **K2 (onay boyunca setpoint akıtmak) artık daha zayıf bir aday.** Başarısız
  denemede komut hiç gönderilmediğine göre, PX4'ün setpoint görüp görmemesi
  sonucu değiştirmez — PX4'e zaten sorulmuyor.
- **K1 (retry) daha güçlü hâle geldi.** Kısa devre durumsalsa ve periyodikse,
  ikinci bir `start()` çağrısı farklı bir iç durumda yakalanabilir. Ölçüm de
  bunu destekliyor: başarısızlığı hemen bir başarı izliyor (1→2, 3→4, 6→7,
  9→10, 12→son). **Ama ADR-004 `:499` gerilimi aynen duruyor** — operatör
  kararı.
- Yeni aday **K5: `start()` sonrası mod onayı gelmezse `stop()` + yeniden
  `start()`.** MAVSDK'nin iç durumunu sıfırlamayı hedefler; retry'den farkı,
  körlemesine tekrar değil **durum temizleme** olması.

Hiçbiri uygulanmadı.

---

# KÖK NEDEN BULUNDU — komut-ACK yanlış eşleşmesi (MAVSDK v3.17.2 kaynağı)

## Kanıt zinciri (hepsi v3.17.2 etiketinden, birebir)

**1. `OffboardImpl::start()` kısa devre YAPMIYOR:**
```cpp
Offboard::Result OffboardImpl::start()
{
    {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_mode == Mode::NotActive) {
            return Offboard::Result::NoSetpointSet;
        }
        _watchdog_grace_start = _time.steady_time();
    }
    return offboard_result_from_command_result(_system_impl->set_flight_mode(FlightMode::Offboard));
}
```
Tek erken dönüş `NoSetpointSet` — o da Python'da **istisna** olurdu, bizde hiç
olmadı. Yani `set_flight_mode` **her zaman** çağrılıyor.
→ **FAZ 1'deki "zaten aktif sayıp kısa devre yapıyor" hipotezi ÇÜRÜDÜ.**

**2. `SystemImpl::set_flight_mode()` de kısa devre yapmıyor:**
`make_command_flight_mode()` → `make_command_px4_mode()` → `send_command()`.
Önbellekteki moda karşı hiçbir erken dönüş yok.

**3. `send_command()` senkron ve ACK bekliyor:**
```cpp
auto prom = std::make_shared<std::promise<Result>>();
auto res = prom->get_future();
queue_command_async(command, [prom](Result result, float progress) {
    if (result != Result::InProgress) { prom->set_value(result); } }, retries);
return res.get();
```

**4. VE İŞTE KUSUR — `CommandIdentification` parametreleri içermiyor:**
```cpp
struct CommandIdentification {
    uint32_t maybe_param1{0}; // only for commands where this matters
    uint32_t maybe_param2{0}; // only for commands where this matters
    uint16_t command{0};
    uint8_t target_system_id{0};
    uint8_t target_component_id{0};
    bool operator==(const CommandIdentification& other) const { ... beş alan ... }
};
```
`maybe_param1/2` yalnızca `MAV_CMD_REQUEST_MESSAGE` ve
`MAV_CMD_SET_MESSAGE_INTERVAL` için doldurulur. **`DO_SET_MODE` (176) için
ikisi de 0 kalır.**

## Mekanizma

Projenin (ve tekrar üretim betiğinin) dizisi:

| adım | gönderilen MAVLink |
|---|---|
| `mission.pause_mission()` | `DO_SET_MODE` **176**, main=4 (AUTO), sub=3 (LOITER) |
| ~1–15 ms sonra `offboard.start()` | `DO_SET_MODE` **176**, main=6 (OFFBOARD) |

İkisinin `CommandIdentification`'ı **birebir aynı**:
`{0, 0, 176, 1, 1}` — çünkü main/sub mod alanları `param1/param2`'de taşınıyor
ve kimliğe **girmiyor**.

**Sonuç:** `pause_mission()`'ın ACK'i hâlâ yoldayken `start()` kendi iş
kalemini kuyruğa koyuyor. Gelen ACK, kimlik eşleştiğinden **offboard iş
kalemine atfediliyor** ve onu **`Success`** ile çözüyor — offboard komutu
**hiç gönderilmeden**.

### İki dalın da ölçümle birebir örtüşmesi

| | FAIL | OK |
|---|---|---|
| `start()` süresi | **3.4 ms** = pause ACK'inin kalan yolu | **11.5 ms** = gerçek MAVLink round-trip |
| ULog'da `param2=6` | **yok** — komut hiç gönderilmedi | **var** |
| `mavlink_command_sender.cpp:304` uyarısı | **yok** — ACK bir iş kalemine eşleşti | **var** — offboard'ın KENDİ ACK'i geç geldi, kalem çoktan silinmişti |

> Uyarının yalnızca **başarılarda** çıkması, ilk bakışta ters görünüyordu;
> mekanizma bunu tam tersine çeviriyor ve **doğruluyor**.

Periyodiklik (1, 3, 6, 9, 12) de bununla uyumlu: çakışma penceresi ACK
zamanlamasına bağlı, dolayısıyla yarı-düzenli.

## Bu bir MAVSDK kusuru — proje kodu suçsuz

Proje `pause_mission()` ve `start()`'ı arka arkaya çağırmakta haklı; MAVSDK'nin
komut göndericisi aynı komut kimliğini taşıyan iki farklı mod komutunu
ayırt edemiyor. İlgili kayıtlı davranış: MAVSDK issue
[#1307](https://github.com/mavlink/MAVSDK/issues/1307) `is_active()`/`_mode`
yarışını, MAVSDK-Python
[#374](https://github.com/mavlink/MAVSDK-Python/issues/374) offboard
iş parçacığı davranışını anlatıyor — **ama bu tam kusur (176 kimlik çakışması)
için açılmış bir kayıt bulamadım.**

## K1 mi K5 mi — **ikisi de mekanizmayı hedeflemiyor; K6 hedefliyor**

| | mekanizmayı hedefliyor mu |
|---|---|
| **K1 — `start()` retry** | **Dolaylı.** Yeniden denemek, bayat ACK tüketildikten sonraki bir pencereye denk gelir ve çalışır. Ölçüm destekliyor: **her başarısızlığı hemen bir başarı izledi** (1→2, 3→4, 6→7, 9→10). Ama kök nedeni bilmeden "yarışı bekleyerek aşmak" |
| **K5 — `stop()` + yeniden `start()`** | **HAYIR — hatta ters tepebilir.** `OffboardImpl::stop()` `set_flight_mode(FlightMode::Hold)` çağırıyor, yani **yine `DO_SET_MODE` 176**. K5, çakışma penceresine **üçüncü bir 176** sokar. Ayrıca sıfırlamayı hedeflediği `_mode` **ilgili durum değil** — ilgili durum komut göndericinin **iş kuyruğu**, ve `stop()` ona dokunmuyor |
| **K6 (YENİ) — iki 176 komutunu zamanda ayır** | **EVET.** `pause_mission()` ile `offboard.start()` arasına, önceki ACK'in tüketilmesine yetecek bir bekleme koymak çakışma penceresini **doğrudan kapatır**. Ölçülen round-trip ~11 ms; ölçülerek seçilecek küçük bir bekleme (ör. 100–200 ms) yeterli olmalı |

**Değerlendirmem:** K5'i **eliyorum** — sorunu yanlış yerde arıyor ve çakışmayı
artırma riski taşıyor. **K6 birincil**, **K1 ikincil savunma** olarak
anlamlı (K6 sonrası kalan artık vakalar için).

**Ölçüm borcu:** K6'nın gerçekten çalıştığı, tekrar üretim betiğiyle
(`k3_repro.py` + araya bekleme) **kod değiştirmeden** sınanabilir — betiği
projeye dokunmadan çağırıyor.

Hiçbiri uygulanmadı.

---

# K6 ÖLÇÜMÜ — çakışma penceresi kapatıldı (2026-09-04)

**Yöntem:** `k3_repro.py`'ın birebir kopyası, tek fark `pause_mission()` ile
`offboard.start()` arasına **200 ms** bekleme. **Projeye hiç dokunulmadı.**
Aynı SITL, aynı derleme, aynı 12 denemelik protokol.

| | K3 (bekleme yok) | **K6 (bekleme 200 ms)** |
|---|---|---|
| başarısız | **5 / 12 (%41.7)** | **0 / 12 (%0)** |
| `start()` süresi ortanca | FAIL 3.4 ms · OK 11.5 ms | **14.0 ms** (min 6.6, max 19.7) |
| 3.4 ms'lik "sahte başarı" imzası | 5 kez | **hiç yok** |
| sunucu ACK uyarısı | 25 | 39 |

## Neden bu bir doğrulama

1. **Başarısızlık tamamen kayboldu** — %41.7'den %0'a.
2. **Zamanlama imzası da değişti:** K3'te başarısızlıkların ayırt edici işareti
   3.4 ms'lik dönüştü (pause ACK'inin kalan yolu). K6'da **12 denemenin
   hiçbirinde** o imza yok; hepsi gerçek MAVLink round-trip bandında
   (ortanca 14.0 ms). Yani artık **her denemede komut fiilen gönderiliyor**.
3. **ACK uyarısı arttı (25 → 39):** beklenen yön. Artık her deneme kendi 176
   komutunu gerçekten gönderiyor, dolayısıyla her denemede geç gelen kendi
   ACK'i "not-existing command" uyarısı üretiyor. Uyarının **kusurun kendisi
   değil, komutun gönderildiğinin işareti** olduğu bir kez daha doğrulanıyor.

Üçü birlikte, kök neden teşhisini (aynı `CommandIdentification`'lı iki 176
komutunun çakışması) **bağımsız olarak doğruluyor**: pencereyi kapatınca
belirti tamamen gidiyor.

## Sınırlar (dürüstçe)

- **n=12, tek oturum.** %0, "asla olmaz" demek değil; K3 tabanı da aynı
  büyüklükteydi (5/12).
- **200 ms ölçülerek seçilmedi**, ilk denemede tuttu. Gerçek alt sınır daha
  küçük olabilir (round-trip ~11–14 ms). Uygulamadan önce 50/100/200 ms
  taraması yapılmalı — görev bütçesine eklenen süre takip başına ödenir.
- Bu ölçüm **tanı betiğinde**; projede `switch_to_offboard()` yolunda aynı
  etkiyi göstermek ayrı bir koşum ister.

## Durum

Öneri sırası netleşti ve **değişmedi**: **K6 birincil** (mekanizmayı doğrudan
kapatıyor, ölçümle doğrulandı), **K1 ikincil savunma**, **K5 elendi**
(`stop()` de 176 gönderdiği için çakışmayı artırır).

**İmplementasyona geçilmedi.** Sıradaki adım, onay verilirse, projenin
`start_offboard()` yoluna ölçülmüş bir bekleme eklemek ve canlı görev
koşumunda `OFFBOARD_SWITCH_FAILED` oranını yeniden ölçmek olur.
