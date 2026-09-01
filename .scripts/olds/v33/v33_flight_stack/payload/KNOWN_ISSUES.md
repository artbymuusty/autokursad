# payload/ — Bilinen Sorunlar ve Gizli Riskler

Bu dosya, `payload/` paketini ilgilendiren ama **bu paketin içinde
düzeltilemeyecek** (veya düzeltilmesi ayrı bir fazın kararı olan)
bulguların kaydıdır. Buradaki hiçbir madde bir görev talimatı değildir —
kayıt amaçlıdır, ilgili faz geldiğinde ele alınmak üzere.

---

## 1. PayloadInterlock ↔ PayloadState drift riski (Görev 2 tarafı)

**Durum:** Bugün ÇAKIŞMA YOK. Kayıt, ileride oluşabilecek bir risk için.
**Bulundu:** Phase 6.5 (2026-08-23), MissionManager wiring araştırması.
**Kapsam:** Görev 2. Bu fazda Görev 2'ye DOKUNULMADI.

### Bugünkü durum: çakışma yok

Görev 3 boyunca `PayloadInterlock` **salt okunur**:

- `core/mission/gorev3_precondition.py:14` — `both_released()` okur
- `core/mission/gorev3_orchestrator.py:43, 47, 48` — kapı + failure event

Hiçbir Görev 3 fazı (`gorev3_pickup/transport/redrop/finish`) interlock'a
veya `MissionV3State`'e **yazmaz**. Dolayısıyla Phase 6.5'te mission
katmanının `PayloadManager`'ı sürmeye başlaması runtime drift ÜRETEMEZ.

İki şey farklı gerçekleri modelliyor:

| | Ne modelliyor |
|---|---|
| `PayloadInterlock` | Görev 2'nin **iki ayrı bırakışı** (Mavi Altıgen, Kırmızı Üçgen) + aralarındaki sıra kuralı |
| `PayloadState` | **Tek** payload'ın mekanizma yaşam döngüsü (deploy→capture→grapple→retract→transport→release→stow) |

`PayloadState`'te "iki payload da bırakıldı" diye bir değer yok;
interlock'ta "kanca şu an GRAPPLED/SECURED" diye bir alan yok.

### Gizli risk 1 — PayloadManager Görev 2'yi de sürerse

Eğer ileride Görev 2'nin iki bırakışı da `PayloadManager` üzerinden
yapılırsa, `PayloadState.RELEASED` ile
`interlock.payload_1_released`/`payload_2_released` **aynı gerçeğin iki
kopyası** olur — ama farklı doğruluk koşullarıyla:

- `core/mission/gorev2_fsm.py:77-81, 94-98` — interlock, doğrulama
  sonucuna **bakmadan koşulsuz** işaretleniyor.
- `payload/payload_manager.py:135-140` — `PayloadState.RELEASED`'a ancak
  `backend.release()` **True döndüğünde** geçiliyor.

Drift senaryosu: fiziksel bırakma başarısız olur → PayloadManager
RELEASE_TIMEOUT'ta kalır, interlock ise "bırakıldı" der. İki kaynak aynı
soruya farklı cevap verir ve hangisinin otoriter olduğu tanımlı değildir.

### Gizli risk 2 — üçüncü kopya zaten var

`core/detection/types.py:48` — `TargetPoint.payload_released` aynı
gerçeğin **bugün de var olan** üçüncü kopyasıdır.

### Not

Bu üç kaynağın birleştirilmesi (veya birinin otoriter ilan edilmesi)
**yapılmadı** — Görev 2'ye dokunmak bu fazın kapsamı dışındaydı ve karar
operatöre ait. Görev 2 payload yolu `payload/` paketine taşınırsa bu
madde önce çözülmelidir.

---

## 2. Gazebo "capture" ile "secured" ayrımını temsil edemiyor

**Kayıt yeri:** kodda `TODO(PHASE-15-PARITY)` olarak
`payload/payload_config.py` (FLEX-20 bloğu) ve
`payload/backends/gazebo_payload_backend.py` başında.
**Bulundu:** Phase 6 (2026-08-23), sarkma gözlemi.

Gazebo'da `retract()`/`stow()` no-op olduğu için (joint `"fixed"`,
re-pozisyonlama yok) payload yakalandığı açıklıkta sonsuza kadar sarkık
kalıyor. Phase 6 ölçümü: 0.30 m açıklıkta payload aracın ~0.41 m altında
asılı ve tüm transport boyunca öyle kalıyor. Ayrıntı ve muhtemel çözüm
kodda; Phase 15 parity testinde ele alınacak.

---

## 3. Real yolu kalibre değil — Görev 3 gerçek donanımda başarısız olur

**Durum:** Kasıtlı ve görünür. Kayıt, sürpriz olmasın diye.
**Kayıt yeri:** `payload/backends/real_payload_backend.py` başında
`TODO(SAFETY)`.

FLEX-14..19 hâlâ TBD (None) ve yakalamayı doğrulayacak sensör yolu yok.
Gerçek donanımda `catch_box_down()` ilk adımda `PayloadCalibrationError`
ile durur. Bu bir çökme değildir: `gorev3_pickup.py::_run_payload_pickup`
bunu temiz bir faz başarısızlığına çevirir, ve
`real_payload_backend.py::warn_if_uncalibrated()` bunu **kalkıştan önce**,
composition root'ta loglar (Phase 6.5).

Phase 6.5 öncesinde bu yol sessizce "başarılı" dönüyordu
(`real_payload_actuator.py` 0.5 s uyuyup `True` döndürüyordu), yani
hiçbir servo bağlı olmadan görev "geçiyordu". Artık geçmiyor.

---

## 4. ~~`gorev3_pickup` üzerinden uçtan uca SITL testi mümkün değil~~ — GERİ ÇEKİLDİ

**Bu madde YANLIŞTI ve 2026-08-23'te geri çekildi.** Metin silinmedi çünkü
asıl değeri, yanlış sonucun NASIL üretildiğinin kaydında — aynı tuzağa
tekrar düşülmesin diye.

### Ne iddia edilmişti

"`default.sdf`'te kırmızı dikdörtgen modeli yok, bu yüzden
`KIRMIZI_DIKDORTGEN` simülasyonda tespit edilemez ve `gorev3_pickup`
uçtan uca test edilemez."

### Neden yanlış

`KIRMIZI_DIKDORTGEN` ile `payload_red` **AYNI FİZİKSEL NESNEDİR**. Kod
bunu zaten söylüyordu: `core/mission/gorev3_pickup.py:22-25` — *"orada
artık görünen Kırmızı Dikdörtgen'e (fiziksel 1. yük)"*.

- `payload_red`, `Tools/simulation/gz/worlds/default.sdf:181`'de **literal
  `<model>` bloğu** olarak statik tanımlı — runtime'da spawn EDİLMİYOR.
  Spawn mekanizması ADR-011 ile **kasıtlı olarak kaldırılmıştı** (spawn
  edilen cisimler dünyadan düşüyordu, `z = -0.72`).
- Geometri/renk: `0.30 x 0.225 x 0.05 m` kutu, RGB (0.75, 0.05, 0.05).
  Tepeden bakıldığında 1.333 en-boy oranlı kırmızı bir dikdörtgen.
  HSV (0, 238, 191) -- detector'ın kırmızı bandının ortasında.
- Detector'da en-boy oranı / karelik / kenar-oranı kapısı **yok**; tek
  bağlayıcı kapı `HSV_MIN_AREA_RECT_BASE = 400 px2`, yani nesne ~7.0 m
  AGL üstünde görülmüyor. Görev 3'ün tüm irtifaları bunun altında.

### Uçtan uca SITL zaten ÇALIŞTI (5 koşu)

`TUM GOREVLER (2 + 3) BASARIYLA TAMAMLANDI` loglayan koşular:
`mission_20260820_215953`, `mission_20260821_180553`, `_181527`,
`_183622`, `_184251`.

Doğrudan kanıt, `mission_20260821_182945.log`:

```
18:32:12,652  Yuk ayrildi (red), gecikme 1.266 s.
18:32:13,131  bu karede 2 tespit: ['KIRMIZI_DIKDORTGEN', 'MAVI_DIKDORTGEN']
```

Payload bırakıldıktan **0.48 saniye sonra** kırmızı dikdörtgen tespit
edilmiş.

### Gerçek önkoşullar (bunlar sağlanmazsa görünmez)

1. **Görev 2'nin kırmızı bırakması tamamlanmış olmalı.** Öncesinde
   payload araca DetachableJoint ile bağlıdır; altıgenin üstünde yatıyor
   olamaz.
2. **Tespit anında irtifa ~7.0 m AGL altında olmalı.** 15 m görev
   irtifasında iz düşümü 87.5 px2, yani kapının 4.6 katı altında.

### Hatanın kökeni ve dersi

İddia `core/config/parameters.py:43-49` ve ADR-010 Phase 12 Q2'den
alınmıştı. **Yazıldığı anda (2026-08-17 19:14) DOĞRUYDU**: o tarihte
payload'lar spawn-on-release silindirlerdi. `default.sdf` **55 dakika
sonra** (20:09) yeniden yazılıp dünya-yüklü prizmalarla değiştirildi.
Sonraki her tekrar bayattı -- ADR-012:48 dahil, ki aynı belge 34/40/42.
satırlarında `payload_red`'in yerde durduğunu tartışıyor.

İddianın öncülü dosya hakkında da yanlıştı: `default.sdf` **beş** model
tanımlıyor (`ground_plane`, `blue_hexagon`, `red_triangle`, `payload_red`,
`payload_blue`), iki değil. İki payload `<include>` değil literal
`<model>` bloğu; `model://` araması onları ıskalar.

**Ders:** repo yorumları bir zaman damgası taşır. Bir yorumun anlattığı
"mevcut durum", o yorumun yazıldığı andaki durumdur -- aktarmadan önce
bugünkü dosyaya bakılmalı. Bu maddeyi yazarken tam olarak bu yapılmadı.

### İki "bulunamadı" hatası neydi

Vision bug'ıydı, eksik nesne değil. Sadece iki koşuda görüldü (2026-08-20
20:46 ve 21:44); ikisinde de Görev 2 payload'ı 111 s / 148 s önce hedefe
bırakmıştı. O tarihteki `_overlaps_committed()` **renk kontrolü
yapmıyordu**, dolayısıyla merkezi taahhüt edilmiş bir bbox içine düşen
her dikdörtgeni atıyordu -- yani kırmızı payload'ın mavi altıgenin
üstüne düştüğü tam durumu. İmza: düzeltme öncesi MAVI_ALTIGEN +
KIRMIZI_DIKDORTGEN birlikteliği 0/3111 kare, sonrası her koşuda 32-75.
`hsv_contour_detector.py` 2026-08-20 21:54'te düzeltildi -- iki hatadan
da SONRA. `default.sdf` bu süreçte hiç değişmedi.

### Kalan gerçek belirsizlik

`HSV_MIN_AREA_RECT_BASE` ve dikdörtgen eps/renk sabitleri repoda
**kalibre edilmemiş yeni varsayılanlar** olarak işaretli (üçgen/altıgen
sabitlerinin aksine v29'dan taşınmadılar). ~7.0 m sınırı doğrulanmış bir
sayı DEĞİLDİR; gerçek kamera intrinsics'i bu sınırı orantılı kaydırır
(`h_cutoff = sqrt(0.0675/400) * f_px`).

---

## 5. [YÜKSEK ÖNCELİK] HookAttachSystem attach-timeout güvenilirliği

**Durum:** Kök neden analizi YAPILMADI. Kayıt amaçlı, kod değişikliği yok.
**Bulundu:** 2026-08-23, Phase 7 log incelemesi.

HookAttachSystem attach-timeout: gözlenen oran yaklaşık **6 koşuda 1**
(örnek: `mission_20260821_192011` -- dikdörtgen bulundu ve hizalandı,
sonra `[CATCH_PAYLOAD_TIMEOUT]`). Kök neden analizi YAPILMADI.

Bu, Phase 5.5'te bulunan "plugin hiç yüklenmiyordu" sorunundan **AYRI**
ve ondan **SONRA** gözlenen bir güvenilirlik sorunu -- plugin şimdi
yükleniyor ama yine de aralıklı başarısız oluyor.

Phase 15 (Full Task 3 SITL) test matrisi bunu **TEK koşulla değil,
TEKRARLI koşu/istatistiksel oran** olarak ele almalı; "geçti" diye
kapatılmamalı.

### GÜNCELLEME (2026-08-24, Phase 15 ölçümü) — oran yeni yolda gözlenmedi

Bugün 6 uçtan uca SITL koşusu yapıldı (A/B/C düzeltme öncesi, D/E/F sonrası).
**Hiçbirinde `[CATCH_PAYLOAD_TIMEOUT]` görülmedi.** Tek alma başarısızlığı
(koşu B) FLEX-20 envelope kapısıydı, attach-timeout değil.

Muhtemel açıklama — ama DOĞRULANMADI: ~6'da 1 oranı **legacy**
`gz_payload_actuator::_await_attach` yolunda gözlenmişti; o yol `/hook/state`
aboneliğini publish'ten SONRA açıyor ve latch'siz tek-seferlik onayı yapısal
olarak kaçırabiliyor. Yeni `payload/` yolu `GzHookClient` ile aboneliği
mission bootstrap'ında açıyor, yani o yarışı barındırmıyor.

**Bu madde KAPATILMADI.** Gerekçe: 6 koşu, ~6'da 1'lik bir oranı ayırt etmek
için yeterli örneklem DEĞİLDİR (beklenen olay sayısı ~1; sıfır gözlemek
şansla tamamen tutarlı). Legacy yol da hâlâ Görev 2'de kullanımda. Phase 15
test matrisi bunu tekrarlı koşuyla ölçmeye devam etmeli.

### Bunu değerlendirirken bilinmesi gerekenler

- Phase 5.5'te ölçüldü: plugin yüklüyken attach isteği ile `ATTACHED`
  arası **2.485 ms**; yani mekanizmanın kendisi hızlı.
- `/hook/state` latch'siz ve geçiş başına TEK KEZ yayınlanıyor
  (`HookAttachSystem.cc:64`, `:127`). Geç bağlanan bir abone hiçbir zaman
  göremez -- `gz_system/gz_hook_client.py` aboneliği bootstrap'ta açarak
  bunu kapatır, ama legacy `gz_payload_actuator.py::_await_attach` hala
  publish'ten SONRA abone oluyor.
- Zaten attach'liyken gelen istek sessizce yok sayılıyor
  (`HookAttachSystem.cc:135-139`) -- yeniden deneme bu durumda kurtarmaz.
- Başarısızlıkta plugin **hiç yayın yapmıyor** (`:119-120`, çıplak
  `return`), yani "çözülemedi" ile "geç kaldı" ayırt edilemiyor.

---

## 6. [ÜST SEVİYE — payload/ paketine ÖZEL DEĞİL] Düşük irtifa vision detector güvenilirliği

**Kapsam:** Genel V33 sınırlaması. Bu madde `payload/` paketinin bir
sorunu DEĞİL — burada, projedeki tek merkezi "bilinen sorunlar" kaydı
olduğu için tutuluyor. Görev 2 ve Görev 3'ün her ikisini de etkiler.

**Durum:** Bu proje bu sorunu **ÇÖZMÜYOR** — yalnızca etkisini belgeliyor
ve izliyor.

### Ölçülmüş davranış

Alçak irtifada detector hedefi kaybediyor ve kayıp **şekle bağlı**:

| Şekil | Kayıp irtifası | Kaynak |
|---|---|---|
| Dikdörtgen (payload) | ~**0.4–0.5 m** | Phase 15 koşuları D/E/F |
| Üçgen / Altıgen | ~**1.6–2.0 m** | ADR-010 P1 (ölçülmüş), Phase 15 |

Kayıp **GEOMETRİKtir, ayarlanabilir bir eşik değildir**: `_detect_hexagon`
konturu tek bir eps ile yaklaşıklıyor ve tam 6 dışbükey köşe istiyor;
şekil kare kenarını kırptığı an konturu artık altıgen olmuyor. Dikdörtgen
daha küçük olduğu ve 4 köşe istendiği için daha alçağa kadar dayanıyor.

### Etkisi: açık-döngü sapması

Vision kaybolunca iniş `[LOW_ALT_OPEN_LOOP_DESCENT]` ile dondurulmuş
kestirim üzerinden tamamlanıyor. Kestirimin ne kadar eski/uzak olduğu
doğrudan sapmaya dönüşüyor. Phase 15 (2026-08-24) ölçümü:

| Koşu | Dikdörtgen: kayıp @ / ofset | Üçgen: kayıp @ / ofset |
|---|---|---|
| D | 0.40 m / **2.7 cm** | 0.63 m / **13.8 cm** |
| E | 0.50 m / **3.4 cm** | 1.01 m / **26.3 cm** |
| F | 0.50 m / **8.3 cm** | 1.99 m / **133.3 cm** |

Dikdörtgen tarafı iyi (2.7–8.3 cm). **Üçgen tarafı kırılgan** ve F
koşusundaki 133.3 cm ciddi bir sapma. Bu maddenin altındaki "örneklem"
bölümü, bunun aykırı değer mi yoksa tekrarlayan örüntü mü olduğunu
ölçmek için genişletiliyor.

### Neden çözülmüyor

ADR-010 P1 bunu **açıkça kapsam dışı** ilan etti:

> *"Detector gates are explicitly out of scope, so the fix is to stop
> REQUIRING vision below this altitude."*

ADR-010'un çözümü detector'ı düzeltmek değil, o irtifada vision'a bağımlı
olmamaktı — `LOW_ALT_VISION_LIMIT_M = 2.0` ve açık-döngü iniş bu kararın
ürünü. Kod bugün buna uyuyor.

### Sonuçları

- V33 spec'in **1 m'de görüntü-işlemeli merkezleme** ve **1 m'de lokal
  doğrulama taraması** adımları bu yüzden uygulanamaz durumda
  (`docs/SPEC_SAPMALARI.md` SAPMA-02, `parameters.py::
  V3_GOREV_AB_DESCENT_ALTITUDES_M` DEPRECATED).
- **Teslimat isabeti üst sınırı bu sapmayla belirleniyor.** Ölçüldü
  (2026-08-24, 12 koşuluk seri + önceki tur): Görev 3'ün redrop adımında
  üçgen yüksekte kaybolduğunda yük hedefin **64.1 / 76.5 / 78.5 cm**
  yanına bırakılıyor (kayıp irtifaları sırasıyla 1.77 / 1.40 / 1.69 m);
  önceki turda **133.3 cm** (kayıp 1.99 m) ölçülmüştü. Bu bir aykırı
  değer DEĞİL, kayıp irtifasıyla doğrudan ilişkili tekrarlayan bir
  örüntüdür -- üçgen alçakta (0.10-0.61 m) kaybolduğunda sapma
  0.3-6.6 cm'de kalıyor.

  Rahatsız edici ayrıntı: bu büyük sapmalar **başarıyla biten**
  koşularda görülüyor, çünkü yalnızca başarılı koşular redrop adımına
  ulaşıyor. Yani mevcut başarı ölçütü ("TÜM GÖREVLER BAŞARIYLA
  TAMAMLANDI") bu kalite kaybını GÖRMÜYOR.

  **AKSİYON ALINMIYOR (2026-08-24 operatör kararı):** yarışma puanlama
  kurallarının isabete ne kadar duyarlı olduğu netleşene kadar bu
  konuda düzeltme yapılmayacak. Netleştiğinde yeniden değerlendirilecek;
  o zamana kadar yalnızca ölçülüp izlenecek.
- Çözülmek istenirse: altıgen/üçgen için çok-eps sweep veya kırpılmış
  kontur toleransı gerekir. Ayrı bir iş, bu projenin kapsamı dışında.

---

## 7. "Üçgen önce" senaryosu SITL'de KANITLANAMADI

**Durum:** Kod seviyesinde kapsandı, SITL'de üretilemedi. **Açık boşluk.**
**Bulundu:** 2026-08-24, dinamik sıralama geçişi (Y2).

### Bağlam

2026-08-24'te Görev 2 dinamik sıraya geçirildi: hangi şekil önce tespit
edilirse onun yükü önce bırakılır (V33 spec md.6/11). Kabul kriteri iki
senaryonun da SITL'de kanıtlanmasıydı.

| Senaryo | SITL sonucu |
|---|---|
| Mavi Altıgen önce | ✅ **3/3 tam başarı**, `1st_mission=MAVI_ALTIGEN` |
| Kırmızı Üçgen önce | ❌ **senaryo üretilemedi** |

### Neden üretilemedi — İKİ DENEME, KÖK NEDEN KESİN

**Deneme 1 (spawn noktası varyantı) — başarısız.**
`PX4_GZ_MODEL_POSE="0,60,..."` ile araç üçgenin kuzeyine spawn edildi.
Rota çalıştı (`Rota dogrulandi (4 item)`, `PX4 MISSION moduna gecti`) ama
9 dakikada hiçbir şekil tespit edilmedi. Neden: `px4-rc.gzsim`'in
`set_spherical_coordinates` çağrısı dünya lat/lon referansını spawn ile
birlikte taşıyor, dolayısıyla `dataman`'deki rotanın MUTLAK GPS'i
hedeflerin fiziksel konumundan kayıyor ve araç hedeflerin üzerinden hiç
geçmiyor.

**Deneme 2 (rota geometrisi) — başarısız, ve KÖK NEDENİ ORTAYA ÇIKARDI.**
Rota MAVSDK ile (QGC'nin yaptığı işin aynısı; dosya yok, `dataman`'de
kalıcı) hedefleri **doğudan dolanacak** şekilde değiştirildi:
`WP0 (0m K, 60m D) → WP1 (40m K, 60m D) → WP2 (40m K, 0m D = üçgen) →
WP3 (15m K, 0m D = altıgen)`. İlk iki bacak 60 m doğuda, yani her iki
hedef de ~18 m'lik kamera yer izi yarıçapının dışında.

Sonuç: rota geçerli oldu, görev **tam başarıyla** tamamlandı -- ama
altıgen YİNE önce tespit edildi. Log zaman damgaları nedeni kesinleştirdi:

```
23:58:35  [VISION] bu karede 1 tespit: ['MAVI_ALTIGEN']     <-- tespit
23:58:38  [MISSION_START] PX4 MISSION moduna gecti          <-- rota HENUZ baslamamis
```

**Altıgen, rota başlamadan 3 saniye ÖNCE tespit edildi.** Home (0,0) ile
altıgen (0,15) arası 15 m; 15 m irtifada kamera yer izi yarıçapı ~18 m.
Yani altıgen **kalkış noktasından zaten görünüyor**.

**KESİN SONUÇ:** bu dünya geometrisi ve bu home konumuyla altıgen HER
ZAMAN önce tespit edilir -- rota ne olursa olsun. Rota değiştirmek bu
sorunu ÇÖZEMEZ. Çözüm yalnızca (a) home konumunu taşımak (GPS
referansını bozuyor, Deneme 1) veya (b) dünya modellerini taşımak
(world/SDF, yetki dışı) ile mümkün.



Tespit sırasını rotanın geometrisi belirliyor. `default.sdf`'te altıgen
(0, 15), üçgen (0, 40) — QGC rotası kuzeye gittiği için altıgen **her
zaman** önce görülüyor.

Denenen yöntem: aracı `PX4_GZ_MODEL_POSE="0,60,..."` ile üçgenin kuzeyine
spawn edip rotayı güneye koşturmak (world/SDF dosyasına dokunulmadı, bu
yalnızca bir PX4 ortam değişkeni).

Sonuç: rota çalıştı (`[MISSION_START] Rota dogrulandi (4 item)`,
`PX4 MISSION moduna gecti`), arama fazı başladı, ama **9 dakikada hiçbir
şekil tespit edilmedi**. Muhtemel neden -- DOĞRULANMADI: spawn noktası
değişince `px4-rc.gzsim`'in `set_spherical_coordinates` çağrısı dünya
lat/lon referansını da taşıyor, dolayısıyla `dataman`'de kayıtlı rotanın
MUTLAK GPS koordinatları hedeflerin fiziksel konumundan kayıyor ve araç
hedeflerin üzerinden hiç geçmiyor.

### Kod seviyesinde ne kanıtlandı

`tests/test_dynamic_mission_order.py` (10 test) her iki sırayı da
**simetrik olarak** sürüyor:

- `test_labels_follow_detection_order` -- iki yönde de etiketler gerçek
  sırayı yansıtıyor
- `test_pickup_targets_the_real_first_mission[TRI-HEX]` -- üçgen önce
  tamamlandığında Görev 3 **üçgene** dönüyor, **MAVI_DIKDORTGEN** arıyor
  ve backend'e **KIRMIZI_UCGEN** payload'ını bildiriyor
- `test_redrop_targets_the_real_second_mission[TRI-HEX]` -- bırakma
  hedefi doğru
- `test_select_payload_translates_shape_to_model` -- iki yönde de doğru
  Gazebo modeline çeviriyor

Ayrıca `test_interlock.py`, `test_mission_v3_state.py`,
`test_payload_mission_sequencer.py` yeniden yazılıp iki sırayı da
kapsıyor.

### Bu boşluğun anlamı

Üçgen-önce yolu **kod seviyesinde doğrulanmış ama uçuşta hiç
çalıştırılmamıştır**. Gerçek uçuşta o dalın ilk kez çalışacağı an
yarışma olabilir. Kapatmak için gereken (iki denemeden sonra netleşti): home konumu ile
dünya modellerinin BİRLİKTE tutarlı şekilde kaydırıldığı bir SITL
varyantı -- yani ya `set_spherical_coordinates` sonrası rotanın yeniden
hesaplanması, ya da test amaçlı ayrı bir world dosyası (hedefler
kalkış noktasından uzağa yerleştirilmiş). İkisi de ayrı bir yetki ve
ayrı bir iş.

**NOT (2026-08-25):** test sırasında `dataman`'deki yarışma rotası
geçici olarak değiştirildi, ardından ORİJİNALİ GERİ YÜKLENDİ ve
indirilerek doğrulandı (4 waypoint, koordinatlar birebir aynı).
Kalıcı bir değişiklik YOKTUR.
