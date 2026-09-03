# Görev E4 — FAZ 1: Donmuş görüş kestiriminin doğruluğu (ANALİZ)

**Tarih:** 2026-09-03 · **Kod değişikliği YOK.**
**Veri:** 3 canlı SITL koşumu (6 bırakma tam kayıtlı) + `observe_payload_pose.py`
ile ~150 Hz bağımsız yer gerçeği + görev olay kayıtları.

---

> **DÜZELTME (2026-09-03, FAZ 1.5 ölçümü sonrası).** Bu raporun iki iddiası
> ölçümle çürüdü ve `docs/gorevE4-faz1.5-ayirt-edici-olcum.md`'de düzeltildi:
>
> 1. **Kök neden**: "yatay inancın neden ıraksadığı" burada açık bırakılmıştı.
>    Cevap bulundu — **optik akış füzyonu** (`EKF2_OF_CTRL 1`, projenin kendi
>    `4014_gz_x500_mono_cam_down` airframe dosyasında). Sensör 0.4 m'de
>    quality 255 ile sıfır akış bildiriyor, EKF onu GPS'ten ~5× ağır tartıp
>    aracın durduğuna karar veriyor.
> 2. **"VEHICLE_TELEMETRY günlüğü ~3.7 s geride" bulgusu YANLIŞ.** O ölçüm
>    yalnızca ıraksama pencerelerinde yapılmıştı. Tüm uçuşta gecikme medyanı
>    +0.03 s, konum hatası 0.089 m. Günlükleme yolunda kusur yok; E5 iş
>    kalemi iptal.
>
> Geri kalan bulgular (kestirim hatası kök neden değil, montaj ofseti temiz,
> lever-arm gürültü, kontrol yolu gecikmesiz, inanç-gerçek ıraksaması) FAZ
> 1.5'te bağımsız olarak doğrulandı.

## 0. Hüküm

> **Kök neden donmuş görüş kestirimi DEĞİL.** Kestirim ölçüldü: şeklin gerçek
> merkezinden **0.062–0.417 m**. `held` noktası da aynı derecede iyi
> (**0.082–0.440 m**). Yani nişan alma doğru.
>
> Kök neden, o doğru noktaya **uçan** halkada: `_mount_translate`/tutma
> döngüsünün **konum inancı ile gerçek arasındaki ıraksama**. Kontrolcü
> yakınsadığına inanırken araç uzaklaşıyor.

Bu, E3'teki 8/8 korelasyonu açıklıyor: `MOUNT_TRANSLATE` süresi dolan her
bırakma 2 m'nin üstünde ıskalıyor — kestirim iyi olduğu hâlde.

---

## 1. `_freeze_target_estimate` ne zaman tetikleniyor ve hatası ne (Soru 1)

**Tetikleme:** 2.0 m eşiğinde DEĞİL. `centering_controller.py:602`, merkezleme
döngüsünün **taahhütlü tespit içeren HER tick'inde** çağrılıyor ve
`self._last_frozen_estimate` her seferinde üzerine yazılıyor. Yani "dondurulmuş
kestirim" = **en son taahhütlü tespitin** geri-yansıtması. Eşik yalnızca
tespitin kaybolmasına izin verildiği noktayı belirliyor.

Kullanım: merkezleme yakınsayınca `descend_to_release()` bu son kestirimi alıp
montaj vektörü kadar öteliyor → `held`.

**Dondurma anındaki ham hata** (şeklin GERÇEK merkezine mesafe):

| koşum | şekil | yakınsadı? | kestirim hatası | `held` hatası | ölçüm irtifası |
|---|---|---|---|---|---|
| koşum-2 | MAVI_ALTIGEN | evet | **0.062 m** | 0.082 m | 0.49 m |
| koşum-1 | MAVI_ALTIGEN | evet | **0.146 m** | 0.128 m | 0.65 m |
| koşum-3 | MAVI_ALTIGEN | **hayır** | **0.145 m** | 0.179 m | 0.52 m |
| koşum-3 | KIRMIZI_UCGEN | evet | **0.187 m** | 0.183 m | 0.73 m |
| koşum-1 | KIRMIZI_UCGEN | **hayır** | **0.271 m** | 0.239 m | 0.49 m |
| koşum-2 | KIRMIZI_UCGEN | **hayır** | **0.417 m** | 0.440 m | 0.72 m |

### Sorduğunuz ayrım: gruplar arasında fark var mı?

**Anlamlı bir fark YOK.** Yakınsayanların kestirim hatası 0.062–0.187 m,
süresi dolanların 0.145–0.417 m. Aralıklar **örtüşüyor** (0.145 < 0.187).
Süresi dolan bir bırakma (koşum-3 MAVI, 0.145 m) yakınsayan bir bırakmadan
(koşum-3 KIRMIZI, 0.187 m) **daha isabetli** başlamış, buna rağmen 5.305 m
ıskalamış.

Dolayısıyla hipotezinizin ikinci şıkkı geçerli değil: sorun
"`_mount_translate`'in düzeltemediği büyük bir başlangıç hatası" değil.
Başlangıç hatası her vakada küçük; büyüyen şey uçuş sırasında oluşuyor.

---

## 2. `_mount_translate` bütçe içinde ne yapıyor (Soru 2)

**İstenen öteleme sekiz bırakmanın hepsinde yalnızca 0.04 m.** Yani 4 cm için
8 s bütçe harcanıyor.

Yer gerçeğiyle ölçülen davranış (`held`'e mesafe, başlangıç → bitiş):

| koşum · şekil | bildirilen kalan | başla → bitir (GERÇEK) | davranış |
|---|---|---|---|
| koşum-3 · KIRMIZI_UCGEN | 4.1 cm | 0.166 → **0.043 m** | yakınsadı, 0.43 s |
| koşum-1 · MAVI_ALTIGEN | 4.7 cm | 0.211 → **0.195 m** | yakınsadı, 0.42 s |
| koşum-2 · MAVI_ALTIGEN | 4.2 cm | 0.206 → **0.387 m** | "yakınsadı" ama UZAKLAŞTI |
| koşum-2 · KIRMIZI_UCGEN | 108.7 cm | 0.488 → **2.289 m** | ıraksadı, 8.04 s |
| koşum-3 · MAVI_ALTIGEN | 45.6 cm | 0.541 → **3.629 m** | ıraksadı, 8.03 s |

**Salınım değil, IRAKSAMA.** koşum-3 MAVI'de araç önce 0.83 m'ye açılıyor,
0.34 m'ye dönüyor, sonra **düz bir çizgide** 3.58 m'ye kaçıyor — son 3.4 s'de
3.48 m, yani ~**1.02 m/s**. Bu, `CENTERING_MIN_CMD_SPEED_M_S = 0.15` tabanının
çok üstünde; kontrolcü büyük bir hata olduğuna inanıp `kp_horizontal = 0.5` ile
komut üretiyor.

**Bütçe neden yetmiyor:** yetmemesi gereken bir mesafe yok — istenen 4 cm.
Bütçe, aracın hedefe *gitmemesi* yüzünden doluyor.

### "Yakınsadı" damgası da güvenilmez

koşum-2 MAVI 0.42 s'de "yakınsadı" yazdı çünkü **ilk** okuma zaten ≤5 cm'ydi;
döngü hiç kontrol etmeden çıktı. Aynı anda araç gerçekte uzaklaşıyordu
(0.206 → 0.387 m). Yakınsama burada kontrolün değil, tesadüfün sonucu.

---

## 3. İnanç ile gerçeğin ıraksaması — asıl bulgu

`LOW_ALT_OPEN_LOOP_STEP.hold_error_m`, kontrol döngüsünün **kendi** hesabı
(10 Hz). Yer gerçeğiyle yan yana:

```
koşum-3 MAVI_ALTIGEN
  kontrolcü:  0.085 → 0.046 m   (AZALIYOR: "yakınsıyorum")
  GERÇEK   :  0.322 → 0.587 m   (ARTIYOR:  uzaklaşıyor)
  fark     :  0.237 → 0.521 m   tekdüze BÜYÜYOR
```
koşum-2'de aynı desen, daha küçük genlikte (0.051 → 0.196 m).

Kontrolcü, gerçekte uzaklaşırken yakınsadığına inanıyor. Geri besleme bu
yüzden düzeltmiyor — düzeltilecek bir hata **göremiyor**.

### Bu bir telemetri gecikmesi DEĞİL — test edildi ve elendi

Kontrol yolundaki irtifa (`LOW_ALT_OPEN_LOOP_STEP.altitude_m` +
`CENTERING_STEP`, ~1100 örnek) gz izine karşı çapraz-ilintilendi:

| varsayılan gecikme | 0.0 s | 0.1 s | 0.3 s | 0.5 s | 0.8 s |
|---|---|---|---|---|---|
| rms uyum (koşum-2) | **0.167 m** | 0.178 | 0.229 | 0.300 | 0.422 |
| rms uyum (koşum-3) | **0.169 m** | 0.182 | 0.238 | 0.314 | 0.441 |

En iyi uyum **sıfır gecikmede**; gecikme arttıkça uyum tekdüze bozuluyor.
Konum akışı da 9.7–9.8 Hz'de sağlıklı geliyor ve koşumların hiçbirinde
`TELEMETRY_STALE` yok. Yani `get_global_position()` kontrol yolunda TAZE.

Iraksama **yatay** eksende ve **dikey** eksende yok — ikisi aynı MAVSDK
mesajından geliyor. Bu, taşıma katmanını eler ve işaret parmağını yatay
kestirim/hareket eşleşmesine çevirir.

### Yan bulgu: `VEHICLE_TELEMETRY` günlüğü ~3.7 s geride

`VEHICLE_TELEMETRY` olayları ~1.95 Hz'de yayınlanıyor ve içerikleri izdeki
**~3.7 s öncesine** uyuyor (artık hata 0.10–0.19 m; yani gerçek ama eski
konumlar). Kontrol yolunu etkilemiyor — ama **sonradan yapılan her analizi**
etkiliyor. Görev E FAZ 1'deki kendi hatalı okumam da bu yoldan geldi. Ayrı ve
küçük bir iş kalemi olarak not ediyorum.

---

## 4. Montaj ofseti: ölçülen ile KULLANILAN aynı mı (Soru 3)

**Aynı.** `MOUNT_VECTOR_MEASURED` servo anında gz'den gerçek vektörü ölçüyor;
`applied_body_m` ise `PAYLOAD_MOUNT_OFFSET_BODY_M`'den geliyor:

| bırakma | ölçülen `body_right_m` | uygulanan | fark |
|---|---|---|---|
| koşum-1 MAVI | +0.0352 | +0.035 | 0.2 mm |
| koşum-1 KIRMIZI | −0.0356 | −0.035 | 0.6 mm |
| koşum-2 MAVI | +0.0351 | +0.035 | 0.1 mm |
| koşum-2 KIRMIZI | −0.0353 | −0.035 | 0.3 mm |
| koşum-3 MAVI | +0.0351 | +0.035 | 0.1 mm |
| koşum-3 KIRMIZI | −0.0354 | −0.035 | 0.4 mm |

`body_forward_m` her vakada ≤1.0 mm. **Bayat/farklı ofset kullanılmıyor,
burada kusur yok.** Zaten 3.5 cm'lik bir hata, gözlenen 2–5 m'lik ıskaların
yanında iki mertebe küçük.

---

## 5. Kamera lever-arm: sistematik sapma mı, gürültü mü (Soru 4)

`CAMERA_LEVER_ARM_BODY_M = (0.085, 0.0)` ve düz-yansıtma yaklaşıklığı
(`m_per_px = alt/focal`, düz zemin, sıfır eğim varsayımı) kullanılıyor.

Kestirim hatasının **yönü** altı bırakmada tutarlı bir yöne bakmıyor; büyüklük
0.062–0.417 m arasında dağılıyor ve ölçüm irtifasıyla (0.49–0.73 m) anlamlı
şekilde ölçeklenmiyor. Yani **sistematik bir bias değil, rastgele gürültü**
görünümünde — ve zaten 0.15 m civarındaki tipik değeriyle, ıskaların
açıklaması olamayacak kadar küçük.

**Bilinen ve belgelenmiş bir yaklaşıklık var:** `LOW_ALT_BBOX_CENTER = True`,
eşik altında kontur momenti yerine **sınır-kutu merkezi** kullanıyor. Üçgen
için bu ihmal edilebilir değil: eşkenar üçgende sınır-kutu merkezi ile ağırlık
merkezi arasındaki fark **yükseklik/6 = 0.144 m**'dir (bu proje için ölçüldü;
E3 eşik çalışmasında SDF'den doğrulandı). Üçgen bırakmalarında bu, tek başına
~14 cm'lik bir yönlü sapma üretebilir. Iskaların ana nedeni değil, ama
`held`'i sistematik olarak üçgenin tepesine doğru kaydırır ve düzeltilmesi
ucuzdur.

---

## 6. Teşhis özeti

| Aday | Hüküm | Kanıt |
|---|---|---|
| Dondurma anı hatası | **DEĞİL** | 0.062–0.417 m; gruplar örtüşüyor |
| Montaj ofseti hatası | **DEĞİL** | ölçülen-uygulanan farkı ≤0.6 mm |
| Lever-arm sistematik sapması | **DEĞİL** (gürültü) | yön tutarsız, büyüklük ~0.15 m |
| Telemetri gecikmesi (kontrol yolu) | **DEĞİL** | en iyi uyum 0 s, akış 9.8 Hz, stale yok |
| **`_mount_translate`/tutma halkasında inanç-gerçek ıraksaması** | **KÖK NEDEN** | inanç 0.085→0.046 m azalırken gerçek 0.322→0.587 m artıyor; 4/8 vakada 2.3–3.6 m |
| bbox-merkez yaklaşıklığı (üçgen) | ikincil, ~0.144 m yönlü | SDF geometrisinden türetildi |
| `VEHICLE_TELEMETRY` günlüğü ~3.7 s geride | ayrı kusur, analizi bozar | içerik 3.7 s öncesine uyuyor |

---

## 7. Kapatılmamış tek soru ve onu kapatacak ölçüm

Yatay inancın gerçekten neden ıraksadığı **tek bir mekanizmaya
indirgenemedi**. İki aday, ikisi de eldeki veriyle ayrıştırılamıyor:

- **(a) Yatay durum kestiriminin hareketi izlememesi** — EKF yatay çözümü
  yumuşak; araç fiziksel olarak kayarken kestirim sabit görünüyor.
- **(b) `CENTERING_MIN_CMD_SPEED_M_S = 0.15` tabanının ürettiği limit çevrim**
  — hata 1 cm'yi aşar aşmaz tam 0.15 m/s komut ediliyor; 10 Hz'de araç
  ataletiyle birlikte sönümlenmeyen bir avlanma üretebilir.

**Ayırt edici ölçüm (FAZ 2'de ilk iş, uçuş davranışını değiştirmez):**
`_mount_translate` ve `_open_loop_descend` döngülerinin her tick'inde
şu üçlüyü olay kaydına yazmak — okunan ham `(lat, lon)`, hesaplanan
`(north_m, east_m)` ve **gönderilen** `(forward_m_s, right_m_s)`. Bunu
`observe_payload_pose.py`'nin yer gerçeğiyle yan yana koymak (a) ile (b)'yi
tek koşumda ayırır: komut sıfıra yakınken araç kayıyorsa (a), komut taban
hızında salınıyorsa (b).

Bu salt gözlem; hiçbir kontrol yolunu değiştirmez, ek MAVSDK tüketicisi
açmaz (ADR-008 B0/B1 uyarısına uyar).

---

## 8. Önerilen sıra (uygulanmadı, onay bekliyor)

1. **E4a — ayırt edici ölçüm** (yukarıdaki üçlü log). Tek koşum, risksiz.
2. **E4b — bulgunun gerektirdiği düzeltme.** (a) ise geri besleme kaynağı /
   filtreleme; (b) ise min-komut tabanının ölü bant ile birlikte ele alınması.
   Hangisi olduğu ölçülmeden seçilmemeli.
3. **E4c — üçgende bbox-merkez sapması** (~0.144 m): ucuz, bağımsız, tek
   başına uygulanabilir.
4. **E4d — `VEHICLE_TELEMETRY` günlük gecikmesi**: uçuşu etkilemiyor ama her
   sonradan-analizi bozuyor.

Görev C/D'ye dokunulmadı, `motion_fsm.py` değişmedi, kod değişikliği yok.
