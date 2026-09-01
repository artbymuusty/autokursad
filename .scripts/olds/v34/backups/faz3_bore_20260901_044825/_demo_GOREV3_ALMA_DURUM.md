# Görev 3 Alma (Pickup) — Durum Raporu

**Tarih:** 2026-08-31 · **Kapsam:** `core/mission/gorev3_pickup.py`,
`gz_system/gz_payload_actuator.py`, `core/mission/visual_alignment.py`,
`core/mission/hook_seating.py` · **Test durumu:** 353 geçti / 9 kaldı

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

Bu **"test edilemez" değildir** — kapı açılıyor, iki tam görev tamamlandı.
Adlandırılmış bir güvenilirlik tavanıdır.

---

## 4. Eklenen ölçüm altyapısı (davranışa etkisiz)

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

---

## 5. Bilinen sorunlar (bu kapsamın dışında)

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

---

## 6. Sonraki adımlar (bu oturumda BAŞLATILMADI)

**(c) Yakalama yardımcılarını simülasyona eklemek.** Yuvanın collision
geometrisi ve huni CAD'de gerçekten var; simülasyona taşımak **olmayan bir
fizik uydurmak değil**, var olan geometriyi modele almaktır. Sahte manyetik
kuvvet ya da "yakınsa otur" mantığı ise ÖNERİLMİYOR — gerçek testte
yanıltıcı olur.

**Kırmızı ton render-piksel karşılaştırması.** Materyal blokları
karşılaştırıldı ve `red_square` ile `red_triangle` renk taşıyan her elemanda
**birebir aynı** çıktı (mavi çift de aynı); dosyalara dokunulmadı. Render
edilmiş **piksel** karşılaştırması yapılmadı — istenmemişti, opsiyonel.

---

## 7. Yedekler

    demo/faz3_backup_20260830T203021Z/          tek-parkur migrasyonu
    demo/faz3_gorev3_backup_20260830T233307Z/   mekanizma 1
    demo/faz3_mech2_backup_20260831T041613Z/    mekanizma 2 (siralama)
    demo/faz2_mech2b_backup_20260831T170556Z/   denge olcumu
    demo/faz2_mech2c_backup_20260831T175528Z/   gorus tanisi
    demo/faz1_y1_backup_20260831T183949Z/       10 Hz iz
    demo/faz3_realign_backup_20260831T191302Z/  yeniden hizalama
    demo/faz3_cleanup_backup_20260831T201707Z/  son temizlik
