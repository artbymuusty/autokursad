# Görev 3 Alma (Pickup) — Durum Raporu

**Tarih:** 2026-09-01 (önceki tur: 2026-08-31) · **Kapsam:**
`core/mission/gorev3_pickup.py`, `gz_system/gz_payload_actuator.py`,
`core/mission/visual_alignment.py`, `core/mission/hook_seating.py`,
`Tools/simulation/gz/worlds/generate_bore_collision.py`,
`worlds/default.sdf`, `models/kursad_payload/model.sdf`,
`models/x500_mono_cam_down/model.sdf` · **Test durumu:** 354 geçti / 9 kaldı

Bu belge bağımsız okunabilir olacak şekilde yazıldı: yeni bir oturum bunu
okuyup çalışmayı kaldığı yerden sürdürebilir.

---

## 1. Başlangıç durumu

Görev 3'ün alma fazı **hiç başarılı olmuyordu**. Oturma kapısı
(`hook_seating.py`) beş koşulu aynı anda ve 0.30 s kesintisiz istiyor:

    lateral   <= 23.25 mm      (yuva agiz yaricapi, CAD)
    insertion  [-4.0, +22.0] mm
    tilt      <= 15 derece
    rel_speed <= 0.05 m/s
    pose_age  <= 0.5 s
    dwell     >= 0.30 s        (20 Hz yoklama -> 6 ardisik gecerli ornek)

İlk iki bağımsız koşuda `CAPTURE_CANDIDATE` sayısı **0/1980 örnek**;
kapı hiç aralanmadı.

---

## 2. Bulunan ve düzeltilen mekanizmalar

### Mekanizma 1 — Sabit vinç salımı, çok eklemli ipi büküyordu · DÜZELTİLDİ

Vinç sabit 0.40 m salıyordu. 0.30 m irtifada güverteye tam denk gelen salım
0.29 m; aradaki 0.11 m gevşeklik 4 üniversal eklemli ipi (`HookRopeSwing1..4`)
büküyor ve kancayı yatırıyordu. **Ölçüm:** hareketsiz kanca `tilt=44.7°`
(gergin ipte 0.005–0.9° olmalı), yani tilt kapısı yanal hata 9.7 mm ile
sınırın içindeyken bile tek başına reddediyordu.

**Düzeltme:** salım artık irtifadan türetiliyor.

    payout(alt, deck) = alt - deck + CHAIN_OFFSET + MARGIN
    0.290            = 0.30 - 0.070 + 0.060 + 0        <- olculmus kalibrasyon

`gz_payload_actuator.hook_payout_m()`. İrtifa bilinmiyorsa eski sabit 0.40 m'ye
düşer (davranış değişmez). Sabiti düşürmek yerine formül seçildi: irtifa ya da
hedef yüksekliği değişirse kendini düzeltir.

**Sonuç:** tilt medyanı 40–45° → **0.4–7.7°**; eksenel +60…+70 mm → −2.3…+38.7 mm.

**`MARGIN = 0.04` GEÇİCİDİR.** 0.02/0.04/0.06 taraması sonucu belirlemedi
(üçünde de `CAPTURE_CANDIDATE`=0, yanal hatada eğilim yok). Yalnızca iki
gözlenmiş hata yönünün arasında olduğu için seçildi: 0.02'de bir denemenin
tamamı `too_high` (kanca güverteye ulaşmadı), 0.06'da `ins=+68.6 mm` (fazla
derin). Yanal sorun çözülünce **yeniden türetilmelidir**.

### Mekanizma 2 — Düzeltme döngüsü yanlış rejimde koşuyordu · DÜZELTİLDİ

Sıra "0.30 m'ye in → vinci sal → düzelt" idi. Salımdan sonra kanca yerde
duruyor ve **aracı takip etmiyordu**: araç komut yönünde kümülatif ~70 mm
öteledi, kanca bağımsız olarak 28 / 49 / 189 mm kaydı. Aynı kontrol yasası
kanca **havadayken** 18.6 / 27.3 / 13.3 mm'ye yakınsıyordu.

**Düzeltme:** sıra "vinci sal (araç hâlâ 0.94 m'de, kanca serbest) → düzelt →
saf dikey in" oldu.

**Sonuç:** kancanın araca göre ofseti artık **±1.0 mm sabit** (rijit takip);
döngü bir koşuda 13.3 → **1.6 mm**'ye yakınsadı.

### Mekanizma 2b — Dikey iniş hizalamayı bozuyor · DOĞRULANDI

İniş sonrası hata 1.6 mm → 41–50 mm'ye çıkıyor. Kanca denge kayması ölçümleri:
**1.2 / 25.5 / 27.6 / 34.4 mm** — sabit değil, rastgele yönlü.

> Uyarı: ilk ölçüm (1.2 mm, n=1) bu hipotezi "çürüdü" saydırmıştı. Sonraki
> ölçümler tersini gösterdi. **n=1'den kesin sonuç çıkarılmamalı.**

### Mekanizma 2c — Görüş sapması / zamansal eşleşmeme · ÇÜRÜTÜLDÜ

Şüphe, `VisualHookAligner._measure()`'ın kare + yaw + poz'u ayrı anlardan
birleştirmesiydi (`get_frame()` zaman damgası taşımıyor). Ölçüm reddetti:
12 iterasyonda görüş tahmini gerçekle **0.3–5.6 mm** uyumlu, derinlik
kaynakları %2 uyumlu, yaw kararlı. Elenen diğer adaylar: kaldıraç kolu
(`CAMERA_LEVER_ARM_BODY_M = (0.085, 0.0)`, SDF ile birebir), içsel
parametreler (tek kaynak), derinlik (`depth_from_detection`'daki ağız
sabitleri cebirsel olarak sadeleşiyor, etkin formül
`focal x 0.142/(long_px-1)`, CAD ile %1.4 uyumlu).

### Y1 — İnişin neresi kaydırıyor · ÖLÇÜLDÜ

10 Hz iz, 415 örnek, temas anı `nose_z` izinin düzleştiği noktadan (t=4.25 s,
`nose_z=+0.0777`, güverte üstü 0.070 m):

| pencere | net kayma | kat edilen yol |
|---|---|---|
| 1 · iniş sırasında (kanca havada) | **1.9 mm** | 14.8 mm |
| 2 · temas anı (+1.5 s) | **23.0 mm** | 27.6 mm |
| 3 · sonrasında (araç sabit) | **22.8 mm** | 2127.7 mm |

**İniş hızı sorun değil.** Sorun temas sıçraması ve sonrasındaki kayma.
`nose_z` 0.077 → 0.041: kanca kutunun üstünde durmuyor, kayıp iniyor.

Kapının **hız** koşulu %81 sağlanıyor, en uzun kesintisiz durağanlık 10.2 s —
yani kanca *duruyor*, sadece **yanlış yerde** duruyor.

### Denemeler arası yeniden hizalama · UYGULANDI, sonucu sınırlı

Her başarısız denemeden sonra vinç çekiliyor (kanca havalanıyor) ve düzeltme
döngüsü yeniden koşuyor — kanıtlı çalışan rejim. `activate_pickup_mechanism`
bir `on_retry` geri çağrısı alır; uçuş kontrolü aktuator katmanında olmadığı
için hizalamayı görev katmanı yapar.

**Mekanizma çalışıyor:** 6 hizalamanın 5'i kancayı 2.7–12.6 mm'ye getirdi.
**Sonuç anlamlı iyileşmedi:** kapı içine düşen deneme 1/10 → 2/11.
Sebep: hizalama 3–12 mm'ye getiriyor, **bırakma 10–40 mm geri ekliyor**.

---

## 3. Ölçülen güvenilirlik tavanı

Alma fazına ulaşan **10 koşuda 2 tam `MISSION_COMPLETE`** (~%20).
Toplam ~21 alma denemesinde **2 oturma** (~%10). Yeniden hizalama turunda
özel olarak: 4 temiz koşuda 1 tamamlama, 11 denemede 1 oturma + 1 deneme
`0 kapı ihlali` ile `CAPTURE_CANDIDATE`=2.

> Önceki bir ara raporda "~%18/deneme, ~%25/koşu" demiştim; o sayı
> "kapı geometrisini sağlayan deneme" oranıydı, "oturan deneme" değil.
> Doğrusu yukarıdadır.

**Kalan varyansın kaynağı fizikseldir ve yazılımla kaldırılamaz:** yuvanın
collision geometrisi yok, huni yok, manyetik yakalama simüle edilmiyor
(`hook_seating.py` başlığında zaten kayıtlı). Kancayı 23.25 mm'lik pencerede
tutacak hiçbir şey olmadığı için her bırakma 10–40 mm rastgele hata ekliyor.

> **BU PARAGRAF ARTIK GEÇERSİZ — bkz. Bölüm 4.** 2026-09-01'de yuva ve huni
> collision geometrisi eklendi; burun artık yuvaya fiziksel olarak giriyor ve
> cep duvarı yanal kaçışı 10.25 mm'de durduruyor. Bu bölümdeki %10/%20
> sayıları **değişiklik öncesi taban** olarak okunmalıdır. Manyetik yakalama
> ve servo hâlâ simüle edilmiyor; o kısım geçerli.

Bu **"test edilemez" değildir** — kapı açılıyor, iki tam görev tamamlandı.
Adlandırılmış bir güvenilirlik tavanıdır.

---

## 4. Yuva (bore) + huni collision · UYGULANDI · 2026-09-01

### Ne yapıldı

Yuva geometrisi zaten `meshes/payload_body.stl` içindeydi ve **VISUAL** olarak
kullanılıyordu; yalnızca collision tarafında tek bir dolu kutuyla
(140×50×70) sadeleştirilmişti. O kutunun üst yüzeyi deck seviyesinde düz ve
kapalı olduğu için burun içeri giremiyordu. Uydurulan bir şey yok; var olan
yüzeyler taşındı.

`worlds/generate_bore_collision.py` (YENİ) CAD profilini ilkel kutulara
ayrıştırıp iki SDF dosyasına marker blokları arasına yazar. Profil ve faset
sayısı orada **tek kaynakta**; script idempotent ve ürettiği şekli nokta
örneklemesiyle kendi doğrular (dört sert koşul: kovuk boş, zarf korundu,
duvar var, deck üst yüzeyi sürekli).

CAD profili (link çerçevesi, deck üstü = +35.00 mm):

| link z | r | bölge |
|---|---|---|
| +35.00 | 23.98 | deck üst yüzeyi |
| +24.50 | 23.25 | düz cep dibi / pah-1 tepesi |
| +20.75 | 14.50 | pah-1 dibi / pah-2 tepesi |
| +17.00 | 11.00 | geçiş deliği omuzu |

**Neden basamak değil, eğimli kutu.** Basamaklı (silindir yığını)
yaklaşıklamanın tek yüzeyleri yatay ve dikeydir; yatay yüzey yanal kuvvet
üretmez, dikey yüzey yalnızca bloklar — yani eğim, N ne olursa olsun yeniden
üretilemez. Buna karşılık bir `<box>`'un `<pose>`'una pitch verilebilir:
SDF 1.9'da bir kutu, yüzeyi tam 23.20°'de olan gerçek bir rampadır.
**Sürüm yükseltmesi gerekmedi.** Yaklaşıklama ekseni çevresel faset sayısına
kaydı; N=8 ve N=10 üreticinin duvar testinden geçemedi, **N=12 geçti**
(faset hatası ±0.40 mm → etkin yanal sınır 9.85–10.65 mm). Payload başına
83 kutu.

### Birlikte düzeltilen üç sabit

Üçü de aynı CAD ölçümünden geldiği için ayrılmadı:

| ne | eski | yeni | gerekçe |
|---|---|---|---|
| `hook_tip_collision` yarıçapı | 0.012 | **0.013** | CAD Ø26 burun. Sabit (`HOOK_NOSE_RADIUS_M = 13.00`) doğruydu, **sim geometrisi yanlıştı** |
| `SEAT_MAX_LATERAL_M` | 23.25 mm | **10.25 mm** | 23.25 (ağız) − 13.00 (burun). Bu sayı docstring'de zaten vardı ve neden kullanılmadığı da yazılıydı: "yuvanın collision'ı yok". O itiraz kalktı |
| `RECEIVER_MAX_INSERTION_M` | 18.00 mm | **15.86 mm** | 18.00, sıfır yarıçaplı bir prob'un alacağı yoldu; Ø26 burun pah-2 üzerinde 2.14 mm erken oturuyor |

### Sürtünme — huninin ne yapıp ne yapmadığı

SDF `<mu>` varsayılanı **1.0** ve ne payload'da ne kanca ucunda `<surface>`
bloğu var. Yerçekimiyle rampada kayma koşulu μ < tan(θ):

| yüzey | eğim | tan θ | kapsadığı ofset | μ=1.0'da kayar mı |
|---|---|---|---|---|
| pah-1 | 23.20° | 0.4286 | d = 1.50–10.25 mm ← asıl yakalama aralığı | **HAYIR** |
| pah-2 | 46.97° | 1.0714 | d = 0–1.50 mm | evet, %7 payla |

Yani bu geometri μ=1.0'da **aktif merkezleme üretmiyor**. Verdiği şey: sert
duvar (10.25 mm ötesine yanal kaçış imkânsız), tanımlı oturma derinliği ve
geri çıkamama. İçeri kaymayı sağlayan yanal kuvvet aracın düzeltme
döngüsünden ve sarkaçtan geliyor. **μ'yü malzeme değerine çekme kararı
bilinçli olarak AYRI tutuldu** — bu turun kapsamı "var olan CAD geometrisini
taşımak"tı; μ yeni bir fizik parametresi kararıdır ve gerekirse ayrı bir
FAZ 1 olarak açılacak.

### Görev 2 regresyonu — 4/4 PASS

| adım | öncesi | sonrası |
|---|---|---|
| statik dinginlik (45 s) | z 35.004–35.007 mm, titreşim 0.157/0.158 mm, XY kayma 0 | **aynı** |
| RTF (medyan) | 0.978 | **0.990** |
| tam koşu, bırakma | @0.43–0.50 m, koşu başına 2–3 | @0.45–0.50 m, koşu başına 2–3 |
| bırakma sonrası | kararsızlık/NaN/penetrasyon 0 | **aynı** (43 vs 42 eşleşme, hepsi `[INF]` log etiketi) |

Payload başına collision 1'den 83'e çıktı; ölçülebilir fizik maliyeti yok.

### Ölçüm — eşik sıkılaşması vs fiziksel haps

3 koşu, 8 deneme, **1 oturma**, **1 `MISSION_COMPLETE`**.

| koşu·dnm | oturdu | yanal min | p50 | eski kapı (23.25) | yeni kapı (10.25) |
|---|---|---|---|---|---|
| 1·1 | – | 17.85 | 21.01 | 8 örnek | 0 |
| 1·2 | – | 32.17 | 35.03 | 0 | 0 |
| 1·3 | – | 38.17 | 50.78 | 0 | 0 |
| 2·1 | – | 34.67 | 37.00 | 0 | 0 |
| 2·2 | – | 23.80 | 24.39 | 0 | 0 |
| 2·3 | – | **1.62** | 5.00 | 0 | 0 |
| 3·1 | – | 26.53 | 30.38 | 0 | 0 |
| 3·2 | **EVET** | **0.60** | 11.64 | 8 | **8** |

Eski kapı 8 denemenin 2'sinde, yeni kapı 1'inde tam-geçen örnek görürdü:
eşik sıkılaşması bu sette **bir deneme kaybettirdi**.

Oran olarak %12.5/deneme, %33/koşu çıkıyor (taban %10 ve %20).
**Bu bir iyileşme iddiası DEĞİLDİR** — 1/8 ile 2/21 istatistiksel olarak
ayırt edilemez, n çok küçük. Bu turun kazanımı oran değil, aşağıdaki
mekanizma kanıtıdır.

### Asıl sonuç: burun gerçekten yuvaya giriyor

Oturan denemede **`ins = +15.4 mm`**. Hesaplanan azami girme derinliği
15.86 mm (Ø26 burun, pah-2 üzerinde r=13.00 noktası). Fark 0.46 mm — faset
hatası (±0.40 mm) artı çözücü esnekliği mertebesinde. Değişiklikten önce
azami girme ~0'dı; ölçülen +0.85 mm ve o da çözücü esnekliğiydi.

İkinci kanıt: 2·3'te yanal 1.62 mm'ye inilmiş ve **`ins = +7.0 mm`** ile
yuvaya girilmiş — ama tilt **58.7°** olduğu için 222 örneğin 208'i tilt'ten
reddedilmiş.

### Yeni darboğaz: tilt

Yuvaya giren iki denemenin birinde bağlayıcı terim artık yanal değil,
**tilt**. Bu mekanizma (1) komşusu bir durum; bu oturumda araştırılmadı.
**2026-09-01 akşamı araştırıldı — bkz. Bölüm 4b.**

### 4b. DÜZELTME: yuva collision'ının bedeli de var (2026-09-01)

Yukarıdaki "asıl sonuç" bölümü **eksikti**. Girme derinliği bulgusu
(15.4 mm ölçülen vs 15.86 mm hesaplanan) doğrudan ölçülmüş mekanik bir
olgudur ve **geçerliliğini koruyor**. Ama aynı değişikliğin bir de
bedeli olduğu o rapor yazılırken bilinmiyordu:

**Tilt 2.7 kat kötüleşti.** Kontrollü deney (aynı oturum, aynı kod, tek
fark yuva collision'ı; marj 0.04'e sabit):

| ölçüt | yuva KAPALI | yuva AÇIK |
|---|---|---|
| tilt medyanı (1 Hz, birleşik) | **7.4°** (n=411) | **20.0°** (n=208) |
| tilt ≤ 15° oranı | %64 | %45 |
| `B_surekli` rejimi | **0/12 deneme** | **2/8 deneme** |
| dwell **ulaşılamaz** | **0/12** | **3/8** |

Dwell'in ulaşılamaz hale gelmesi tek istatistiksel olarak anlamlı fark:
Fisher kesin testi **p = 0.049**. (`B_surekli` için p = 0.147 — anlamlı
değil.) `dwell_reachable=False`, tilt'in eşiğin altında 6 ardışık örnek
bile tutamadığı, yani oturmanın **yapısal olarak imkânsız** olduğu
anlamına geliyor.

**Net etki belirlenemiyor.** Oturma ve `MISSION_COMPLETE` oranları:

| | koşu | ulaşan | deneme | oturma | COMPLETE |
|---|---|---|---|---|---|
| KAPALI (bu oturum kontrol) | 6 | 4 | 12 | 0 | 0 |
| AÇIK | 7 | 7 | 19 | 2 | 2 |

Fisher: oturma/deneme **p = 0.510**, COMPLETE/ulaşan **p = 0.491**.
Nokta tahminleri yuva lehine ama her iki kolda başarı sayısı 0–2; bu n
ile **hiçbir yönde** oran iddiası desteklenmiyor.

**Çerçevelemenin durumu:** "Asıl kazanım burnun gerçek CAD derinliğine
oturması" ifadesi **doğru kalıyor** — o bir oran iddiası değil, doğrudan
ölçüm. Ama tek başına bırakılırsa yanıltıcı: aynı değişiklik tilt'i
belirgin biçimde kötüleştirdi ve toplam alma başarısına etkisi henüz
bilinmiyor. Yuva geometrisi doğru olan ama **bedeli olan** bir adımdır;
tilt çözülmeden "iyileştirme" denemez.

---

## 4c. Mekanizma (1) — vinç doyumu ve kord ölçümü · 2026-09-01 akşamı

`B_surekli`'nin kaynağı Bölüm 7'de mekanizma (1) alanına havale edilmişti.
FAZ 1–3 yapıldı. **Düzeltme tasarımı yapılmadı**; `gorev3_pickup.py` ve
`CHAIN_OFFSET` bu turda da değişmedi.

### Geometri, SDF zincirinden ölçüldü

Kord = 0.02287 + 3×0.04575 + 0.02287 = **0.18299 m**. `nose_z = alt + K − P`.
Doğrulama: `alt=0, P=0` → 0.0424 m; `model.sdf` satır 206 bağımsız olarak
*"hook tip is 42.4 mm above ground"* diyor. Birebir tutuyor.

### Bulgu A — retry denemeleri penceresinin çoğunu boşa harcıyor

Deneme 2–3'te vinç **~0.002 m'den** başlıyor ve **oturma penceresi sırasında**
salıyor. `t=0.05 s`'de burun deck'in **318 mm üstünde**. İzden doğrudan
okunuyor, hipotez değil. 12 s'lik pencerenin etkin kısmı çok daha kısa.

### Bulgu B — vinç komut edilen değere hiç ulaşmıyor

**32/32 denemede** hesaplanan salım `HookRopeJoint`'in **0.35 m** limitini
aşıyordu (ortalama 28.1 mm) ve bunu ne log ne uyarı gösteriyordu — fizik
sessizce kırpıyordu. Deneme 1'de bile pencere başında ulaşılan 0.327–0.329 m,
pencere sonunda ~0.346–0.350.

**Sonucu:** o irtifa rejiminde `MARGIN` **etkisiz**; 0.04 ve 0.06 kolları aynı
fiziksel salımı (0.350 m) üretiyor. 2026-08-31'in *"tarama sonucu belirlemedi"*
bulgusu büyük olasılıkla bu yüzden — üç koldan ikisi (çoğu irtifada üçü) aynı
deneydi.

**Yapılan:** `HOOK_WINCH_MAX_EXTENSION_M = 0.35` (kaynağı SDF satırına atıflı)
ile kırpma + `VINC DOYUMU` uyarısı. **Davranış değişikliği sıfır** — fizik
zaten kırpıyordu; biten şey yalnızca sessiz arıza.

### Bulgu C — `CHAIN_OFFSET` hâlâ karara bağlanamadı

Ölçüm, araç-tarafı ofseti **0.2627 m** veriyor; SDF'den beklenen 0.290 değil
(**27.3 mm** fark). Bu `CHAIN_OFFSET ≈ 0.015` demek — iki adayın (SDF
geometrisi 0.04236, kayıtlı kalibrasyon 0.060) **hiçbiri**. Kalan bilinmeyen
`alt` → `base_link` eşlemesi. Bunu kilitleyecek ölçüm (`base_z_m`) eklendi ve
stub'landı; **bu oturumda yalnızca toplanıyor, değerlendirilmiyor.**

### Bulgu D — kord katlanması görünür oldu, ama tilt'i açıklamıyor

Katlanma kancaya en yakın iki eklemde toplanıyor (5 katlanmış vakanın 4'ünde
j3/j4 = 14–46°, j1/j2 < 4°). Ama katlanma toplamı tilt'i **öngörmüyor**:

| katlanma toplamı | tilt p50 |
|---|---|
| 81.8° | **0.0°** |
| 32.2° | **47.1°** |
| 98.6° | 27.5° |
| 1.9° | 0.3° |

**Pearson r = +0.175 (n=9).** Koşu-içi 80°'lik yayılımın kaynağı olarak
önerdiğim aday **çürütüldü**.

---

## 5. Eklenen ölçüm altyapısı (davranışa etkisiz)

| log / event | ne verir |
|---|---|
| `[GORSEL_HIZA_TANI]` | iterasyon başına derinlik+kaynağı, u/v, long_px, yaw, gövde ofseti, ham hata **ve gerçek yanal hata** |
| `[SON_DUZELTME] ... kanca_ofset / arac_ned / kanca_mutlak` | kancanın aracı takip edip etmediği |
| `[KANCA_DENGE]` | iniş öncesi/sonrası kanca ofseti ve değişimi |
| `[KANCA_IZ]` | 10 Hz kanca izi (`off_n`, `off_e`, `nose_z`) |
| `[YENIDEN_HIZA]` | denemeler arası hizalamanın ulaştığı yanal |
| en iyi **eşzamanlı** örnek + kapı ret histogramı | hangi kapının kaç örnekte reddettiği |
| `GOREV3_PICKUP_STEP`, `HOOK_SEATING_RESULT`, `GOREV3_CORRECTION_STEP`, `GOREV3_REALIGN_BETWEEN_ATTEMPTS`, `GOREV3_HOOK_EQUILIBRIUM_SHIFT` | event bus'a yayın (faz eskiden hiç yayın yapmıyordu) |

**Önemli ders:** faz event bus'a hiç yayın yapmadığı için olay akışında
77–89 s "sessizlik" görünüyordu ve bu yanlışlıkla "kod takılmış" diye
okundu — oysa kod her adımı çalıştırıyor, sadece `logger`'a yazıyordu.

2026-09-01 turunda eklenen (yine davranışa etkisiz, stub'la doğrulandı):

| alan | ne veriyor |
|---|---|
| `lateral_dist` (oturma raporunda) | pencere boyunca yanal ofset dağılımı: `n`, `min`, `p10/p50/p90` ve **iki eşiğe göre** sayımlar (`*_le_10_25`, `*_le_23_25`), hem tüm örnekler hem de "yanal dışındaki bütün kapı terimlerini geçen" örnekler için |

Bu son ikili, kapı sıkılaşmasının etkisini fiziksel hapsin etkisinden **ek
uçuş gerektirmeden, aynı koşudan** ayırmayı sağlıyor.

2026-09-01 akşamı eklenenler (yine salt-ölçüm, stub'la doğrulandı):

| alan | ne veriyor |
|---|---|
| `tilt_dist` | tilt dağılımı + **eşik geçişi sayısı**, `longest_run_le_gate`, `dwell_reachable` ve türetilmiş `regime`. Geçiş sayısı iki rejimi ayırır: salınımda çok, sürekli yatmada ~0. Yalnızca medyana bakmak ikisini aynı gösterir. |
| `seat_trace` | oturma penceresinin 10 Hz zaman serisi `[t_s, tilt_deg, lat_mm, ins_mm, winch_m, span_m, fold_deg]`. `ins > 0` temas başlangıcını verir; `winch_m` ulaşılan salımı, `fold_deg` dört eklemin katlanma açısını. |
| `winch_state()` | ulaşılan salım, kord açıklığı, dört katlanma açısı, `base_z_m`, `nose_z_m`. **SDF'ye dokunmadan** mevcut poz akışından türetiliyor — yeni eklenti/konu yok. |
| `payout_cmd_m` / `payout_sent_m` | formülün istediği vs fiziksel sınıra kırpıldıktan sonra gönderilen salım. |

---

## 6. Bilinen sorunlar (bu kapsamın dışında)

1. **Görev 2 kırılganlığı.** Koşuların ~%40'ı alma fazına hiç ulaşamıyor:
   `OFFBOARD_SWITCH_FAILED`, `TARGET_SEEN_BUT_NOT_CENTERED`,
   `search_incomplete_mission_finished`, `Kirmizi Dikdortgen bulunamadi`.
2. **9 önceden var olan kırmızı test** — `test_adr009_*`,
   `test_adr010_retry_*`, `test_mission_route_resume.py`. Hepsi "route resume"
   ailesinden, bu çalışmayla ilgisiz (kanıtlandı: `parameters.py` kod satırları
   yedekle birebir, testler `sdf_geometry` import etmiyor).
3. **`depth_from_detection` docstring hatası** — "detector reports the mouth
   radius it measured" diyor; detektör ağzı ölçmüyor, uzun kenardan türetiyor
   (`receiver_detector.py:288`). Sadece yorum düzeltmesi.
4. **`competition_day.sdf` / `competition_overcast.sdf`** — şekil yerleşimleri
   migrasyon öncesi (iki şekil, sabit konum, sınır çerçevesi yok). Payload
   pose'ları düzeltildi, şekiller düzeltilmedi.
5. **`models/kursad_hook/` dizini repoda YOK** ve git geçmişinde hiç commit
   edilmemiş. `x500_mono_cam_down/model.sdf` dört mesh'e atıf yapıyor,
   dördü de yükleme hatası veriyor:
   `core_lower.stl`, `core_upper.stl`, `servo_cam.stl`,
   `locking_arm_locked.stl` (`[Err] [MeshManager.cc:211] Unable to find
   file[...]`). Bunlar yalnızca **visual**; fizik etkilenmiyor (kanca
   collision'ı `hook_tip_collision` silindiri olarak duruyor). İki sonucu
   var: GUI'de kanca görünmüyor, ve `hook_seating.py` kanca sayılarının
   kaynağı olarak `core_lower.stl`'i gösterdiği için **kanca tarafı
   repodan doğrulanamıyor**. Yuva tarafı mesh'ten doğrulandı.
   Bkz. Bölüm 7, açık iş 2.

---

## 7. Açık işler

### 1. Tilt darboğazı — ARAŞTIRMA KAPANDI (tasarım ayrı oturuma)

Yuva collision'ı eklendikten sonra bağlayıcı terim değişti. 2026-09-01
setinde yuvaya giren iki denemeden biri (`2·3`) yanal 1.62 mm ve
`ins = +7.0 mm` ile içerideydi ama **tilt 58.7°** olduğu için 222 örneğin
208'i tilt'ten reddedildi (`SEAT_MAX_TILT_RAD = 15°`).

Gergin ipte tilt 0.005–0.9° ölçülüyor (Bölüm 2, mekanizma 1); 58.7° ipin
gevşediğini gösteriyor. Bu **mekanizma (1) komşusu** bir durum — salım
hesabı ve ip dinamiği alanına giriyor. Bu turda kapsam dışıydı ve
kasıtlı olarak açılmadı.

**DURUM (2026-09-01 akşamı):** FAZ 1 ve FAZ 2 yapıldı. `tilt_dist` ve
`seat_trace` eklendi, kontrollü deney koşuldu — sonuçlar Bölüm 4b'de.
Özet: tilt'in kötüleşmesi yuva collision'ıyla **ilişkili ve
tekrarlanabilir**; dwell'in ulaşılamaz hale gelmesi p = 0.049.

**KAPANDI (2026-09-01, son tur).** 9 koşu daha yapıldı (yuva AÇIK,
`seat_trace` etkin) ve `B_surekli` yakalandı. Sonuç, beklediğimin tersi
çıktı ve iki ayrı olguyu **karıştırdığımı** ortaya koydu.

**Bulgu 1 — genel tilt temasla tetikleniyor (geometri tarafı).**
17 denemenin hiçbirinde tilt temastan önce eşiği aşmıyor (temas öncesi
maksimum 2.8°, eşiği aşan 0/17). Yuvanın içinde temas edildiğinde tilt
**0.12–0.22 s** içinde geliyor; yuva kapalıyken benzer yanal ofsetlerde
(15.8 / 21.9 mm) aynı eşik **1.20–5.46 s** sonra aşılıyor. İki küme hiç
örtüşmüyor. Bu, yuva geometrisinin temas anında devirici bir tork
uyguladığına işaret ediyor.

**Bulgu 2 — ama `B_surekli` bunun bir örneği DEĞİL.** Üç `B_surekli`
örneğinin **ikisinde temas hiç yok**:

| koşu | yanal | ins | tilt | temas |
|---|---|---|---|---|
| 081226 d1 | 10.3 mm | **+11.4 mm** | 31.1° | evet (yuva içinde) |
| 081900 d3 | 16.8 mm | **−10.0 mm** | 51.7° | **hayır** |
| 120334 d1 | 25.7 mm | **−9.5 mm** | 47.3° | **hayır** |

İzi alınan örnekte (120334 d1) kanca oturma penceresine **daha ilk
örnekte 39.2° eğik** giriyor, deck'in 7.4–10.0 mm üstünde asılı kalıyor,
12 saniye boyunca hiçbir şeye değmiyor ve tilt 35–53° arasında sabit
duruyor (`crossings = 0`, `longest_run = 0`).

Yani `B_surekli` **yukarı akıştan geliyor**: kanca temas edebileceği
noktaya varmadan ÖNCE yatmış oluyor. Geometri değil, iniş/ip/sarkaç
dinamiği alanı. Bulgu 1'in işaret ettiği yön `B_surekli` için geçerli
değil; ikisi ayrı olgu.

**Yan bulgu ÇÜRÜTÜLDÜ.** "Temas anındaki yanal ofset, tilt'in kalıcı
olup olmayacağını belirler" hipotezi n=2'de makul görünüyordu; n=5'te
yıkıldı (Pearson r = +0.50, monoton değil): **16.8 mm → 34.5° (düştü)**
ama **17.2 mm → 9.2° (OTURDU)**. Neredeyse aynı ofset, zıt sonuç.

**Sıklık:** `B_surekli` 3/32 deneme (~%9) — nadir bir olay. Daha fazla
kovalanmadı.

**Kapsam dışı bırakılan:** düzeltme tasarımı. Mekanizma (1)'in salım
formülüne bu turda da dokunulmadı. Bulgu 2 doğrudan mekanizma (1)
alanına girdiği için, tasarım AYRI bir oturuma bırakıldı.

### 1b. Retry penceresi / salım örtüşmesi — YENİ, açılmadı

Bulgu A. Deneme 2–3'te oturma penceresi vinç salımıyla örtüşüyor ve pencerenin
büyük kısmı burun deck'in 300+ mm üstündeyken geçiyor. Düzeltme
`gorev3_pickup.py`'nin retry akışına girmeyi gerektirdiği için **yeni bir
FAZ 1'e** bırakıldı (2026-09-01 kararı).

### 1c. `CHAIN_OFFSET` kararı — ölçüm hazır, karar verilmedi

Bulgu C. `base_z_m` ölçümü eklendi ve stub'landı; `alt` telemetrisine hiç
güvenmeden hesap yapmayı sağlıyor. Karar bilinçli olarak sonraki oturuma
bırakıldı. **MARGIN taraması bu karar netleşmeden anlamsız** — bekletiliyor.

### 2. `kursad_hook` eksik mesh'leri

Bölüm 6, madde 5. Dört STL repoda yok. Fizik etkilenmiyor ama kanca
geometrisi repodan doğrulanamıyor ve GUI'de kanca görünmüyor.
CAD dışa aktarımının (`~/KURSAD40/cad_exports/`, bu makinede yok) yeniden
üretilmesi veya mesh'lerin repoya alınması gerekiyor. Küçük ve bağımsız iş.

### 3. Kırmızı ton render-piksel karşılaştırması

Materyal blokları karşılaştırıldı: `red_square` ile `red_triangle` renk
taşıyan **her elemanda birebir aynı** (mavi çift de aynı); dosyalara
dokunulmadı. Render edilmiş **piksel** karşılaştırması hâlâ yapılmadı.
Küçük, bağımsız ve simülasyon koşusu gerektiren tek açık iş — ileride
zaten yapılacak bir doğrulama koşusuna bindirmek en ucuzu.

---

## 8. Yedekler

    demo/faz3_backup_20260830T203021Z/          tek-parkur migrasyonu
    demo/faz3_gorev3_backup_20260830T233307Z/   mekanizma 1
    demo/faz3_mech2_backup_20260831T041613Z/    mekanizma 2 (siralama)
    demo/faz2_mech2b_backup_20260831T170556Z/   denge olcumu
    demo/faz2_mech2c_backup_20260831T175528Z/   gorus tanisi
    demo/faz1_y1_backup_20260831T183949Z/       10 Hz iz
    demo/faz3_realign_backup_20260831T191302Z/  yeniden hizalama
    demo/faz3_cleanup_backup_20260831T201707Z/  son temizlik
    backups/faz3_bore_20260901_044825/          yuva + huni collision
    backups/faz2_tilt_20260901_074413/          tilt_dist enstrumantasyonu
    backups/faz3_trace_20260901_091532/         seat_trace (10 Hz iz)
    backups/faz3_winch_20260901_153658/         vinc doyumu + kord olcumu
    backups/faz3_baselink_20260901_201948/      base_link Z olcumu (bu tur)
