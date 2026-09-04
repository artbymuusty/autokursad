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
