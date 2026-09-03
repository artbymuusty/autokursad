# Görev F — Mission ↔ Offboard geçişleri: FAZ 1 analizi

**Tarih:** 2026-09-03 · **Kod değişikliği YOK.**
**Birincil kanıt:** `.scripts/olds/v34/logs/mission_0600f0558de3.jsonl`
(gerçek görev yolu, `./run_mission_v34_gz.sh`, 23:03:17→23:10:18, 420 s, 6594 olay)
+ ULog `build/px4_sitl_default/rootfs/log/2026-09-03/20_02_52.ulg`
+ karşılaştırma koşumu `logs/mission_03e3d7358506.jsonl` (18:03→18:20)
+ 129 mission log'luk külliyat taraması.

---

## 0. Kısa hüküm

| | belirti | hüküm |
|---|---|---|
| **F1** | yakala → mission'a dön → tekrar yakala | **KARMA**: dönüş politikası KASITLI (ADR-004 §17); ama onu tetikleyen Offboard giriş başarısızlığı **gerçek bir arıza** — külliyat genelinde **%24.4** |
| **F2** | arama hattı devam etmiyor | **GERÇEK KUSUR**: indeks defteri doğru çalışıyor, **geometri** kırık. Resume "kaldığın yerden" değil, "bulunduğun yerden son waypoint'e düz çizgi" demek |
| **F3** | Offboard'a geçişte 15→10.8 m çökme | **BELİRTİ YANLIŞ**: böyle bir çökme **yok**. Gerçek olan, küçük hedef için **kasıtlı** 8 m + **kasıtsız** bir 8→15→10 m gidiş-dönüşü |

**Üçünün ortak kök nedeni YOK.** F1→F2 bir **tedarik ilişkisi** (F1 her
tetiklendiğinde bir resume harcıyor ve F2'yi doğuruyor). F3 tamamen ayrı bir
irtifa-politikası hikâyesi ve mod geçişiyle **ilgisi yok**.

---

## 1. ADR bağlamı — külliyat 2026-08-17'de duruyor

ADR-004…011'in hepsi 2026-08-16/17 tarihli. F1/F2/F3'e hükmeden kararların
**üçü ADR'lerden SONRA** alınmış (2026-08-21, 08-29, 09-02/03) ve **yalnızca
kod yorumlarında** belgeli. Yalnız ADR'lere bakan biri özellikle F3'te yanlış
sonuca varır. Bu, raporun kendi başına bir bulgusu: **ADR süreci koda ayak
uyduramamış.**

---

## 2. F1 — yakala / mission'a dön / tekrar yakala

### Tetikleyici (kesin)

Zaman aşımı, güven eşiği ya da "kaybettim" sinyali **değil**. Tek koşul
`switch_to_offboard()`'un boolean dönüşü:

```
core/mission/gorev2_orchestrator.py:716-724
    offboard_ok = await self.centering.switch_to_offboard()
    if not offboard_ok:
        self.context.transition_to(MissionPhase.SEARCHING, reason="offboard_switch_failed")
        await self._resume_mission_route()
        continue
```

### Ölçülen örnek (23:03 koşumu)

```
23:03:52.539  TRACK_STATE consecutive_frames 1
23:03:52.962  frames 5 -> esik saglandi -> TARGET_SELECTED MAVI_ALTIGEN (0.9)
23:03:55.984  OFFBOARD_SWITCH_FAILED {"timeout_s": 3.0}      <- CRITICAL
23:03:56.961  MISSION_CURRENT_ITEM_SET {index:2} -> STARTED_ONBOARD
23:03:57.971  MISSION_ROUTE_RESUMED
23:03:58.xxx  TARGET_SELECTED MAVI_ALTIGEN (0.9)             <- ikinci yakalama
23:04:00.599  OFFBOARD_SWITCH_CONFIRMED
```
Hedef **hiç kaybedilmedi** (iki tespitte de confidence 0.9, ardışık kare
eşiği yeniden sağlandı). Kayıp ~6.6 s. Aynı desen 18:03 koşumunda üçgen için.

### Kasıtlı mı, hata mı — İKİSİ DE

**KASITLI yarısı:** ADR-004 §17 (`:493`) — *"Centering timeout | **no
auto-retry into the same pursuit** — re-enter SEARCHING, let debounce/
track-ready re-qualify naturally"* ve `:499` — *"anything touching the
payload interlock or an armed/Offboard state transition escalates instead of
retrying blindly."* Yani **SEARCHING'e dönmek politikadır**, flapping değil.

**HATA yarısı:** Offboard'a girişin %24.4 oranında başarısız olması. Bu
`OFFBOARD_SWITCH_FAILED`'ın **zaman aşımı** dalı
(`centering_controller.py:203-213`), PX4 reddi (`:194-197`) **değil** —
PX4 hiçbir hata üretmiyor, yalnızca 3.0 s içinde `OFFBOARD` bildirmiyor.

### ADR-004 §004-b'nin varsayımı yanlış

ADR-004 `:277` bunu bir **reddetme** (rejection) olarak modelliyor ve
*"capture and surface PX4 mode-change rejection"* istiyor. Ölçüm: bu bir
reddetme değil, **sessiz bir gecikme**. Olayın PX4 gerekçesi taşımamasının
sebebi taşınacak bir gerekçe olmaması. → **ADR-004 §004-b güncellenmeli.**

---

## 3. F2 — arama hattının kaybolması

### Sorduğunuz (1): bayraktan bağımsız zincir tam olarak nereden geliyor

**Kesin teşhis: iki ayrı mekanizma var ve `ENABLE_ROUTE_REJOIN` bunların
yalnızca KÜÇÜK olanını kontrol ediyor.**

`_resume_mission_route()` (`gorev2_orchestrator.py:490`) gövdesi:

| adım | bayrağa bağlı mı |
|---|---|
| `if self._search_complete: return` (kalıcı kilit) | hayır |
| `if _params.ENABLE_ROUTE_REJOIN: await self._rejoin_route_axis()` (`:520`) | **EVET — tek bağlı yer** |
| `stop_offboard()` | hayır |
| `_space_out_resume()` (ADR-009 aralık) | hayır |
| **`_issue_resume()`** → `get_current_mission_index()` → `set_current_mission_item(index)` → `start_mission()` | hayır |
| `_confirm_mission_mode()` → `MISSION_ROUTE_RESUMED` yayını | hayır |

`MISSION_CURRENT_ITEM_SET` **`_issue_resume()`'dan** geliyor
(`:573-593`, ADR-010 R2) ve **her zaman çalışıyor**. Bayrak yalnızca
`_rejoin_route_axis()`'i açıyor — bu da **yanal ekseni transect hattına geri
çekmek**, yani F2'nin ta kendisi.

Yani: gördüğünüz zincir **bayraktan bağımsız, zaten var olan resume çekirdeği**;
bayrağın kontrol ettiği şey ondan **farklı ve daha küçük bir alt-küme**.

### Sorduğunuz (2): `_route_axis` AttributeError'ın kök nedeni

**Uçuş hatası DEĞİL, test koşum hatası.** `parameters.py:261-265` bunu zaten
yazmış: 9 test `Gorev2Orchestrator.__new__()` ile `__init__`'i **atlayarak**
nesne kuruyor, dolayısıyla `__init__`'in `:146`'da set ettiği `self._route_axis`
hiç oluşmuyor. Üretim kodunda mekanizma **tam**; eksik olan testlerin kurulum
biçimi.

### Sorduğunuz (3)+(4): PX4 tarafında ne oluyor, indeks doğru mu

**İndeks defteri ÇALIŞIYOR ve off-by-one DEĞİL.** Zincir iki kez ateşlendi
(T+39.2 ve T+130.8), PX4 ikisinde de MISSION'a döndü, `MISSION_RESUME_NOT_
CONFIRMED` sıfır.

**Kırık olan GEOMETRİ.** Bir PX4 mission indeksi bir **hedef waypoint** adıdır,
bacak üzerindeki **konum** değil. Duraklama anındaki bacak-üstü ilerleme
hiçbir yerde saklanmıyor. Ölçüldü (yerel NE, ilk GPS fix'e göre):

- Transect kuzeye gidiyor, boylam sabit: N 0.07→51.83 m iken E −0.18…+0.08 m
- 23:05:29.181'de MISSION'a dönüş: **N=56.23, E=−11.34 m** → hattın **11.34 m batısında**
- PX4 son waypoint'e **düz kiriş** uçuyor: dE/dN = 0.128; 34 m sonra hâlâ 7 m dışarıda

**Kapsama sonucu:** 15 m'de kamera yarı-genişliği ≈8.9 m (geniş eksen).
11.34 m ofsetle operatörün arama hattı **kadraj dışında** kalıyor —
kabaca **19–36 m'lik hat "MISSION'da uçuldu ama hiç bakılmadı."**

Ve çarpıcı bir çerçeve: Görev 2'nin 224.1 s'sinin yalnızca **23.4 s'i (%10.4)**
MISSION modunda geçmiş, üç parça hâlinde.

### Kök neden (kanıtlanmış)

> Resume ilkel işlemi **yalnızca indeks tabanlı** ve indeks daima rotanın
> **son öğesi** olduğu için, "devam et" fiilen **"bulunduğun yerden son
> waypoint'e taze bir düz çizgi uç"** anlamına geliyor.

### ADR bulgusu

`ENABLE_ROUTE_REJOIN`'in **varsayılan-kapalı gerekçesi projenin kendi
loglarıyla çürüyor.** `parameters.py:261-263` "ADR-009'un resume zamanlamasına
etkisi ölçülmedi" diyor — oysa külliyatta ölçüm mevcut. → Bu yorum ve dayandığı
ADR-009 varsayımı **güncellenmeli**.

---

## 4. F3 — irtifa

### Belirtinin birinci yarısı YOK

129 log, **189 `OFFBOARD_SWITCH_CONFIRMED`**, sonraki 12 s içinde **1.5 m'den
büyük tek bir çökme yok**. Bu koşumda:
- 1. giriş: 14.967 (MISSION) → 15.115 (OFFBOARD) → 15.065 → 14.983 → 14.978. **Tepe-tepe 0.15 m**
- 2. giriş: 14.995 → 14.947
- 18:03 koşumu: 15.04'te girdi, 52 s boyunca 14.97–15.04

**Offboard'a geçişte irtifa çökmesi diye bir olgu yok.**

### Peki 10.8 m nereden geldi

Koşumdaki 10.8'e en yakın an: **23:05:40.912 = 11.030 → 23:05:41.412 = 10.298**,
ve bu **komut edilmiş 15→8 m alçalmasının ortası**. Yani gördüğünüz sayı, aracın
kasıtlı olarak indiği 8 m'ye giderken **geçtiği** irtifa.

### Gerçek olan (a): 8.0 m KASITLI ve ölçülmüş

`gorev2_orchestrator.py:43` — `SEARCH_CENTER_ALTITUDE_M = {"KIRMIZI_UCGEN": 8.0}`,
gerekçesi `:738-746`:
> 15 m'de üçgen kameraya **561 px²** düşüyor ve `HSV_MIN_AREA_TRI_BASE=390`'ın
> yalnızca **1.4 KATI**. Ölçüldü (23:30 koşusu): **altıgen 2. denemede
> ortalandı, üçgen 62.** 8 m'de üçgen **1972 px²**, yani 5.1× pay; altıgen
> zaten 5 m genişliğinde olduğu için 15 m'de rahat görülüyor.

### Sorduğunuz (2): tırmanış hipotezi — ULog'dan ÇÜRÜTÜLDÜ

| an | saat | **gerçek irtifa (groundtruth)** |
|---|---|---|
| payload 1 bırakma | 23:05:16.869 | 0.49 m |
| **15 m'ye ulaşıldı** | **23:05:28.457** | 15.00 m (bırakmadan +11.6 s) |
| 2. hedef seçimi | 23:05:36.999 | **15.16 m** |
| 2. merkezleme başladı | 23:05:37.830 | **15.12 m**, ama `altitude_m=8.0` |

Tırmanış, hedef seçiminden **8.5 s önce** tamamlanmıştı
(`CLIMB_STARTED 23:05:18.874 → CLIMB_DONE 23:05:28.550`, 9.68 s).
**"Araç hâlâ tırmanıyordu" hipotezi yanlış.** 8.0 mevcut irtifa değil,
kasıtlı bir hedef.

### Gerçek olan (b): KASITSIZ gidiş-dönüş

Merkezleme 8 m'de bitiyor → sonra sabit-kodlu nav bacağı **15 m**'ye
tırmandırıyor → sonra kademeli yaklaşmanın ilk adımı **10 m**. Yani
**8 → 15 → 10 m**: 0.08 m yatay yol için **~9 s saf düşey seyahat**.

### Gerçek olan (c): kademeli merdiven KASITLI

`PAYLOAD_APPROACH_ALTITUDES_M = [10.0, 5.0, 0.45]` (`parameters.py:466`,
gerekçe `:450-465`). `LOW_ALT_VISION_LIMIT_M` / `LOW_ALT_BBOX_CENTER` ile
**aynı aile**, ADR-010 P1 kapsamında. Son adım 2026-08-17'de 0.30→0.45 m'ye
çekilmiş.

---

## 5. Ortak kök neden var mı — HAYIR

- **F1 → F2: tedarik ilişkisi.** Her F1 döngüsü tam bir `_issue_resume()`
  harcıyor; bu koşumda F2'nin ateşlenme sebebi de o. F1 düzelirse F2'nin
  **sıklığı** azalır ama **kendisi** düzelmez.
- **F3 bağımsız.** Mod geçişiyle ilgisi yok; irtifa her Offboard girişinde düz.
  Belirtinin mod geçişine bağlanması **yanlış bir ilişkilendirmeydi** ve bunu
  saptamak başlı başına bir bulgu.

Yani "hepsi mod-geçişi anındaki bir senkronizasyon sorununa iniyor" hipotezi
**doğrulanmadı**.

---

## 6. Güncellenmesi gereken ADR'ler (kendim değiştirmedim)

| ADR | sorun |
|---|---|
| **ADR-004 §004-b** (`:277`) | Offboard giriş başarısızlığını **reddetme** sanıyor; ölçüm **sessiz zaman aşımı** diyor |
| **ADR-004 §17 FSM tablosu** (`:120-136`) | "başarısız Offboard geçişinden sonra SEARCHING'e dönüş" ve "aynı hedefi yeniden alma" için **faz yok**; F1 döngüsü adlandırılamıyor |
| **ADR-009** (`:151`, `:184-188`) ve **ADR-010** (`:257`, `:270-283`) | `OFFBOARD_SWITCH_FAILED`'ın **nedenini** "pause, resume'dan ~1 s sonra düşüyor" diye açıklıyor; 176 geçişlik ölçüm bunu **çürütüyor** |
| **`parameters.py:261-263`** (ADR-009'a atıfla) | `ENABLE_ROUTE_REJOIN` için "etkisi ölçülmedi" diyor; **ölçüm külliyatta var** |
| **Külliyat geneli** | ADR'ler 2026-08-17'de duruyor; F1/F2/F3'e hükmeden üç karar sonrasında alınmış ve yalnızca kod yorumunda |

---

## 7. Önerilen düzeltmeler (uygulanmadı)

### F2 (en yüksek etki)
| seçenek | artı | eksi |
|---|---|---|
| **F2-a** `ENABLE_ROUTE_REJOIN`'i testleri düzeltip aç | Mekanizma **zaten yazılmış ve tam**; tek engel testlerin `__new__()` kurulumu | Yanal düzeltme *sonradan* yapılıyor; kayıp kapsama geri gelmiyor |
| **F2-b** Duraklama anında bacak-üstü konumu sakla, resume'da oraya dön | Kapsama boşluğunu **kökten** kapatır | Yeni durum + yeni goto; ADR-009 resume zamanlamasına ek yük |
| **F2-c** Rotayı kalan waypoint'lerle yeniden yükle | PX4'ün kiriş davranışını ortadan kaldırır | En invaziv; rota QGC'nin işi, proje onu üretmiyor |

### F1
| seçenek | artı | eksi |
|---|---|---|
| **F1-a** `MISSION_MODE_CONFIRM_TIMEOUT_S`/Offboard onay penceresini ölçüme göre büyüt | Tek sabit; %24.4'ü düşürür | Kök nedeni değil semptomu adresler |
| **F1-b** Onay yolunu incele (ADR-008 B0 önbelleği taze mi) | Gerçek kök nedene iner | Ölçüm gerektirir |
| **F1-c** ADR-004 §17 politikasını gevşetip aynı hedefe sınırlı retry | Döngüyü kısaltır | **ADR-004'ün bilinçli kararını çiğner** — önerilmez |

### F3
| seçenek | artı | eksi |
|---|---|---|
| **F3-a** 8 m merkezlemeden sonra 15 m'ye tırmanmayı atla, doğrudan 10 m'ye geç | ~9 s kazanç, tek yerde değişiklik | Nav bacağı irtifasının sabit-kodlu olduğu yeri bulmak gerek |
| **F3-b** `SEARCH_CENTER_ALTITUDE_M`'i 10.0 yap (merdivenin ilk basamağı) | Gidiş-dönüş tamamen kalkar | Üçgen 10 m'de 1262 px² — 390 eşiğinin 3.2 katı; hâlâ rahat ama 8 m kadar değil. **Ölçüm ister** |

**Sıra önerim: F2-a → F1-b → F3-a.** F2-a en yüksek etkiyi en düşük riskle
veriyor (kod hazır, engel testte). F1-b F2'nin sıklığını da düşürür.
F3-a saf verimlilik, uçuş güvenliğine dokunmuyor.

---

Kod değişikliği yapılmadı. Görev C/D/E4e'ye ve `motion_fsm.py`'a dokunulmadı.

---

# EK — Külliyat ölçümü (129 log) ve raporun düzeltilmesi

Yukarıdaki bölümler tek koşum + kod okumasına dayanıyordu. 129 mission log'luk
külliyat taraması birkaç sayıyı **düzeltti** ve F1'i çok daha kesinleştirdi.

## D1 — F1'in gerçek istatistiği ve mekanizması

**Doğru sayılar:** 250 takip geçişi, **61 başarısızlık = %24.4** (raporda
"176/45" yazıyordu; o kısmi bir taramaydı).

**68 `OFFBOARD_SWITCH_FAILED` olayının TAMAMI `{"timeout_s": 3.0}` taşıyor;
HİÇBİRİ `{"error": ...}` taşımıyor.** Külliyatta PX4 bir kez bile reddetme
üretmemiş.

**Belirleyici bulgu — başarısızlıklar HOLD'a gidiyor, OFFBOARD'a hiç değil:**
- 61 başarısızlığın **0 tanesinde** tek bir OFFBOARD örneği yok
- Başarısızlıkların 43'ü MISSION→**HOLD**, 12'si zaten HOLD
- **55'inin 14'ünde** araç `offboard.start()`'tan sonra **0.6 s içinde** zaten
  HOLD'da (en erken 0.18 s). PX4'ün offboard-kayıp failsafe'i (`COM_OF_LOSS_T`
  varsayılan 1.0 s) bu kadar hızlı ateşleyemez.
→ En az bu vakalarda araç **hiç OFFBOARD'a girmemiş**; mod isteği,
`pause_mission()` aracı AUTO.LOITER'a oturttuktan sonra **onurlandırılmamış**.

**Zamanlama kesimi YOK.** Başarılılar 0.218–1.245 s, başarısızlar 3.020–3.229 s;
`[1.245, 3.020]` aralığı 176 temiz denemede **tamamen boş**. İlk-gözlem
gecikmeleri iki sonuç arasında **tamamen örtüşüyor**.

**Onay döngüsünün gözlediği şey 1 Hz.** Başarı gecikmeleri 0.2 s'lik bir tarağa
düşüyor (`asyncio.sleep(0.2)`, `centering_controller.py:203-209`) ve
`TELEMETRY_STREAM_RATES`'te `flight_mode` **{0.1, 0.9, 1.0, 1.1}** Hz iken
`position`/`velocity`/`attitude` **10.0** Hz.

**Setpoint çölü GERÇEK ama nedeni kanıtlanmadı:**
`mavsdk_backend_base.py:389-393` tek bir `VelocityBodyYawspeed(0,0,0,0)`
gönderip onay döngüsü boyunca **3.0 s'ye kadar hiçbir şey akıtmıyor** — oysa bu
depo PX4'ün ~500 ms sınırını `parameters.py:343-346`'da belgeliyor ve kardeş
bir yorumda (`gorev2_orchestrator.py:989-991`) bunu **yasaklıyor**. Hijyen
kusuru kesin; **%24.4'ün nedeni olduğu kanıtlanmadı**.

## D2 — Döngünün SINIRSIZ olmasının sebebi: üç korumanın da ölü olması

| koruma | durum |
|---|---|
| `TargetValidator._consecutive_counts` (`target_validator.py:24`) | tekdüze artıyor, kaçan karede bile azalmıyor; `reset()` (`:85-94`) **`core/` içinde hiç çağrılmıyor** → bir şekil 5 kareye ulaştıysa **kalıcı olarak** track-ready |
| `_note_centering_failure` (`gorev2_orchestrator.py:1015`) | `_centering_cooldown_until`'ın **tek yazarı** ve **üretimde hiç çağrılmıyor** (yalnızca testlerde) → `:684`'teki aday filtresi **kalıcı boş** bir sözlüğü sınıyor |
| `DebounceTracker` | yalnızca **başarılı GPS kaydından sonra** kuruluyor |

`:716-724` dalı bunların hiçbirine dokunmuyor. Sonuç: yeniden nitelenme
**101 ms** sürüyor (referans koşum; iki başka koşumda 100–102 ms).

Ayrıca: `CENTERING_RETRY_COOLDOWN_S` **5.0** olarak gönderiliyor,
ADR-009'un yazdığı 10.0 değil.

## D3 — F1→F2 bağı SAYISALLAŞTI (doz-yanıt)

Takip yapan koşumlar (n=93):

| koşumdaki Offboard başarısızlığı | rota erken bitti (arama tamamlanmadan) |
|---|---|
| 0 | **%2** |
| 1 | **%4** |
| **≥2** | **%60** |

Mekanizma ADR-011 T3 (`ADR-011:255-268`): her resume rotanın **son** indeksini
yeniden dayatıyor, dolayısıyla her biri yalnızca son bacağı yeniden uçuruyor ve
`is_mission_finished()`'ı True'ya yaklaştırıyor.

> **F1 resume üretir; resume rotayı tüketir; rotanın tükenmesi F2'nin
> görev-bitiren biçimidir.**

Bağ nedensel ama **münhasır değil**: `mission_b291abb2aba8` tek takip, sıfır
Offboard hatası, tek resume ile de rotayı erken bitirmiş.

## D4 — DENENMEMESİ GEREKENLER (ölçümle elendi)

Bunlar yazıya geçmeli, yoksa biri mutlaka deneyecek:

1. **Onay zaman aşımını büyütmek İŞE YARAMAZ.** `[1.245, 3.020] s` aralığı 176
   temiz denemede boş; ek bütçe yalnızca başarısızlık başına daha uzun
   takılma satın alır.
2. **Settle süresi eklemek zaten yapıldı ve oranı oynatmadı**
   (`gorev2_orchestrator.py:708`, `:1004-1013`): settle'sız %26.1, settle'lı
   %20.3 (n=176/74).

## D5 — Güncellenmesi gereken ADR listesi genişledi

Bölüm 6'daki beşe ek olarak:

| ADR | sorun |
|---|---|
| **ADR-010 R2** (`:295`) | `MISSION_RESUME_MIN_INTERVAL_S` 15→6 gerekçesi tek koşumdan ("`OFFBOARD_SWITCH_FAILED` 4→0"); **n=1** ve tekrarlanmıyor (o günden beri 250 denemede 61 hata) |
| **ADR-009 D3** (`:87-91`) | Cap/cooldown Offboard-hatası sınıfını **kapsamıyor** ve cooldown yazarı **ölü kod**; gönderilen değer 5.0, ADR'de 10.0 |
| **ADR-008 B0** (`:53-62`) / **ADR-009 D1** (`:63-75`) | `flight_mode`'u "değişim-güdümlü, sessizlik normal" varsayıyor; ölçüm **1 Hz düzenli akış** diyor — `TELEMETRY_STALE_AFTER_FLIGHT_MODE_S = 3.0`'ın dayanağı bu |

## D6 — Yan bulgu: hız kapısı olmayan yakınsama

`CENTERING_CONVERGED` **tek kare**lik bir konum testi ve **hız kapısı yok**;
araç MISSION seyir hızını Offboard'a taşıyabiliyor. 165 yakınsamanın **2'sinde**
15 m'de yanlış yakınsama gözlendi, sonuçta 2.7–4.0 m GPS hatası.
n=2, genellenebilirliği **kanıtlanmadı** — ama mekanizma görünür.

## D7 — Kapatılamayanlar (dürüstçe)

- **PX4 neden %24.4'te OFFBOARD'ı reddediyor.** Elenenler: resume kümelenmesi,
  onay bütçesi, bayat/yavaş mod önbelleği, yer hızı, irtifa, bırakma anındaki
  mod, build regresyonu, koşum-başı koşullar. **Yerine kanıtlanmış bir sebep
  konulamadı.** Kapatmak için PX4 tarafı gerekiyor: SITL parametrelerinden
  `COM_OF_LOSS_T` ve commander'ın kendi mod-geçiş satırları — o log bu ağaçta yok.
- **Saniye-altı bir OFFBOARD penceresi olup kaçırıldı mı.** 1 Hz'lik bir
  gözlenebilir bunu göremez. 61 başarısızlıkta geçici OFFBOARD örneği
  bulunamadı ama "kanıt yok" ≠ "yok".
- **Onay sırasında setpoint akıtmanın (3a) fayda edip etmeyeceği.** Doğru
  hijyen ve bedava; oranı değiştireceğine dair **ölçüm yok**, aksini düşündüren
  iki ölçüm var. Uygulayan, sonucu **deney** saymalı, çözüm değil.

## D8 — Sıra önerisi (güncellendi)

1. **Gözlenebilirlik** (saatler, uçuş riski sıfır): `OFFBOARD_SWITCH_FAILED`'a
   her onay yoklamasında gözlenen modu, yoklama zamanlarını ve
   `pause_mission()`'dan geçen süreyi ekle; `MISSION_ROUTE_CONFIRMED`'da ham
   mission seq/command listesini yayınla. ADR-004 `:277`'nin ulaşmaya
   çalıştığı ama yanlış tarif ettiği şey budur. 3a ile 3b arasında karar
   vermenin **tek ucuz yolu**.
2. **F1 döngüsünü sınırla** (en yüksek ölçülmüş görev-sonucu kaldıracı):
   ≥2 hata → %60 kayıp, 0–1 hata → %2–4. `:716-724` dalı **bedava olmaktan
   çıkmalı**. (2a) bu dal için **ayrı** bir sayaç + cooldown; (2b)
   `TargetValidator` streak'ini sıfırla / DebounceTracker'ı kur.
   **Gerilim:** bu, ADR-004 `:499`'un "escalate, don't retry" ilkesine karşı
   duruyor ve **operatör kararı** gerektirir. Ama mevcut davranışın ne olduğu
   da yazılmalı: *rota resume'u dahil tüm takibin kör tekrarı* — önerilenlerin
   hepsinden kötü.
3. **Mekanizmaya saldır** (ikisi de hipotez): (3a) `offboard.start()` öncesinden
   onay gelene kadar `OFFBOARD_SETPOINT_INTERVAL_S`'te sıfır-hız akıt;
   (3b) PX4 tarafını ULog'dan incele.

F2 için bölüm 7'deki sıra geçerli (**F2-a** hâlâ en yüksek etki/en düşük risk).

---

# EK 2 — D7 kısmen KAPANDI: PX4 verisi bu ağaçta zaten var

**Raporda "o log bu ağaçta yok" yazmıştım. YANLIŞ.**
`vehicle_command` ve `vehicle_command_ack` **her ULog'da zaten kayıtlı**.
① için hiçbir indirme/config değişikliği gerekmedi.

## Ölçüm

`DO_SET_MODE` (cmd 176) `param2` alanı PX4 ana modudur: **4 = AUTO, 6 = OFFBOARD**.

Referans koşum `20_02_52.ulg`, **başarısız** geçiş penceresi (sim t 62–70):

| sim t | gönderilen | PX4 cevabı |
|---|---|---|
| 64.12 | `DO_SET_MODE param2=4` (**AUTO**) | ACCEPTED |
| 64.14 | `cmd 2003` (pause) | — |
| 67.13 | `DO_SET_MODE param2=4` (**AUTO**) | ACCEPTED |
| 68.10 | `DO_SET_MODE param2=4` (**AUTO**) | ACCEPTED |

`nav_state`: 62.10 AUTO.MISSION → **64.14 AUTO.LOITER** → 68.12 AUTO.MISSION.

**Başarılı** geçişte (sim 71.11) ise `DO_SET_MODE param2=6` (**OFFBOARD**) var.

Sekiz ULog'da toplam: **AUTO=53, OFFBOARD=16**. Referans koşumda 2 başarılı
giriş ↔ tam **2** adet `param2=6`.

## Sonuç

> **Başarısız denemelerde OFFBOARD mod komutu PX4'e HİÇ ULAŞMIYOR.**
> PX4 hiçbir şeyi reddetmiyor — kendisine sorulmuyor bile.

Bu, "PX4 %24.4'te OFFBOARD'ı reddediyor" çerçevesini **çürütüyor**: sorun
**PX4'te değil, istemci tarafında** (MAVSDK `offboard.start()` yolu). Ve
`start_offboard()` istisna da atmıyor (68 olayın hiçbirinde `{"error":...}`
yok), yani `offboard.start()` **hatasız dönüyor ama komutu göndermiyor**.

**Hâlâ kanıtlanmadı:** `offboard.start()`'ın komutu neden atladığı.
En olası aday, MAVSDK Offboard eklentisinin iç durum makinesi
(`set_velocity_body` + `start()` sırasının bir ön koşulu). ① ile eklenen
`stage` / `polls` alanları bunu bir sonraki koşumda ayırt edecek.

**Bu bulgu ADR listesini de etkiliyor:** ADR-004 `:277`'nin
*"PX4 mode-change **rejection**'ı yüzeye çıkar"* isteği yalnızca yanlış
tarif edilmiş değil, **konusu da yok** — ortada reddetme yok, gönderilmemiş
bir komut var.

## ① kapsamında eklenen gözlenebilirlik (uygulandı)

| olay | eklenen alanlar |
|---|---|
| `OFFBOARD_SWITCH_FAILED` | `stage`, `pause_duration_s`, `poll_count`, `modes_seen`, `first_mode`, `last_mode`, `polls[]` (her yoklamanın `t_s`+`mode`'u) |
| `OFFBOARD_SWITCH_CONFIRMED` | `confirm_s`, `poll_count`, `pause_duration_s`, `polls[]` — **başarı da kaydediliyor**, yoksa ikisi karşılaştırılamaz |
| `MISSION_ROUTE_ITEMS` (yeni) | ham `seq`/`command`/isim listesi + `start_index` — bugüne kadar yalnızca `logger.info`'daydı, olay kaydında yoktu |

Salt gözlem: hiçbir kontrol değeri, zamanlama ya da eşik değişmedi.
Testler: **492 geçti, 1 atlandı.**
