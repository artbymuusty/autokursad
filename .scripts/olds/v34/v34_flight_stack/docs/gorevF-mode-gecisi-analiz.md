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
