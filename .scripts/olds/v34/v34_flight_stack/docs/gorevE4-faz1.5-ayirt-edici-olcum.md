# Görev E4 — FAZ 1.5: Ayırt edici ölçüm (SALT GÖZLEM)

**Tarih:** 2026-09-03 · **Kontrol mantığı değişmedi.**
**Ölçüm:** 2 canlı SITL koşumu (run4: 1 ıraksayan bırakma · run5: 2 yakınsayan
bırakma) + 3 önceki koşumun ULog'ları = **5 koşum**.
**Kaynaklar:** tick başına görev kaydı · bağımsız ~150 Hz Gazebo yer gerçeği
(`observe_payload_pose.py`, artık yönelim de kaydediyor) · PX4 ULog
(`vehicle_local_position`, `..._groundtruth`, `estimator_*`, `trajectory_setpoint`).

---

## 0. Hüküm

> **(a) doğrulandı, (b) elendi — ama asıl kök neden ikisi de değil.**
>
> Yatay durum kestirimi gerçekten hareketi izlemiyor. Ancak bunun sebebi
> GPS kapısı ya da kontrol döngüsü değil: **PX4'ün EKF'i, sıfır akış
> bildiren bir optik akış sensörünü azami güvenle füzyona sokuyor** ve
> aracın durduğuna ikna oluyor. Bu, projenin kendi airframe dosyasında
> açılmış bir ayar.

`ROMFS/px4fmu_common/init.d-posix/airframes/4014_gz_x500_mono_cam_down:31`
```
param set-default EKF2_OF_CTRL 1          # optik akis fuzyonu acik
```

Görev kodu bu olayda **kurban, fail değil**.

---

## 1. Enstrümantasyon (kontrol değeri değişmedi)

`_mount_translate` ve `_open_loop_descend`, her tick'te zaten hesapladıkları
değerleri artık kaydediyor: ham `lat/lon`, türetilmiş `north_m/east_m`,
kullanılan `yaw_deg`, **istenen** `(forward, right)` ve **gönderilen**
`(forward, right, down)`. Gönderilen değer `_send_setpoint`'in zaten
döndürdüğü ama atılan dönüşüdür — tek değişiklik onu yakalamak.
Diff: 32 ekleme, 3 silme; silinen üç satır aynı çağrıların dönüşsüz hâli.
Test paketi: **478 geçti, 1 atlandı.**

---

## 2. (a) mı (b) mi — doğrudan cevap

run4, ıraksayan bırakma, `_mount_translate` penceresi (76 tick, 7.96 s):

| ölçüt | değer | anlamı |
|---|---|---|
| \|istenen\| / \|gönderilen\| | 0.283 / 0.281 m/s | **limiter kırpmıyor** → (c) elendi |
| işaret değişimi | 2/76 (%2) | **salınım yok** |
| aci(gönderilen, doğru yön) | ortanca 14.5° (ilk 4 s: 0–3°) | **komut doğru yöne bakıyor** |
| aci(gönderilen, gerçek hareket) | ortanca 64.8° | **araç komuta uymuyor** |
| \|gerçek\| hız | ortanca 0.684, max ~2.0 m/s | komuttan 3–7× büyük |

**Kullanıcının istediği yön kontrolü:** komut doğru yöne bakıyor ama araç onu
izlemiyor → tanımınıza göre **(a)**, "(b) veya işaret hatası" değil.

**Komut integrali kesin kanıt:**

| | kuzey | doğu | toplam |
|---|---|---|---|
| gönderilen komutların integrali | +1.653 m | +0.018 m | 1.653 m |
| **gerçek yer değiştirme** | **+4.840 m** | **−2.328 m** | **5.371 m** |

Doğu ekseninde 0.018 m komut edilmişken araç 2.328 m batıya gitti. Hareket
görev kodunun komutlarıyla **açıklanamıyor** (3.2×).

**Sağlıklı koşumla karşıtlık (run5):** inanç-gerçek açığı ortanca
**0.013 m** (max 0.029), ıraksayanda ortanca **0.771 m** (max 4.816 m).

---

## 3. Kök neden: optik akış füzyonu

PX4 kayıtları (kendim doğruladım):

| t (ULog) | GT hız | irtifa | akış gözlemi | **gereken akış** | füzyon | reddedildi |
|---|---|---|---|---|---|---|
| 106 | 0.28 m/s | 0.43 m | 0.011 rad/s | 0.67 rad/s | 1 | 0 |
| 110 | 1.78 m/s | 0.35 m | 0.018 rad/s | 5.15 rad/s | 1 | 0 |
| 114 | 3.44 m/s | 0.45 m | −0.003 rad/s | **7.59 rad/s** | 1 | 0 |

`sensor_optical_flow`: **quality = 255** (azami) ve `pixel_flow ≈ (0.0000,
0.0000)` — araç 3.4 m/s giderken sensör "hareket yok" diyor ve bunu tam
güvenle bildiriyor.

**Neden EKF buna inanıyor:** `EKF2_OF_N_MIN = 0.15` rad/s, hız gürültüsüne
menzille çarpılarak dönüşüyor → 0.4 m'de σ ≈ **0.06 m/s**, buna karşılık
`EKF2_GPS_V_NOISE = 0.30` m/s. Yani akış, GPS'ten **~5× ağır** (varyansta
25×) tartılıyor. `EKF2_OF_QMIN = 1` olduğu için kalite kapısı da pratikte
hiçbir şeyi elemiyor. İrtifa düştükçe akışın ağırlığı **artıyor** — bu
yüzden arıza tam olarak 0.35–0.45 m'lik bırakma irtifasında ortaya çıkıyor.

### Zincir (ölçülmüş)
1. 0.4 m'de akış sensörü sıfır akış + quality 255 bildiriyor.
2. EKF bunu GPS'ten 5× ağır tartıp "duruyorum" sonucuna varıyor
   (EKF \|v\| 0.05–0.19 m/s, gerçek 0.98 → 4.48 m/s).
3. PX4'ün hız denetleyicisi setpoint'i (0.28 m/s) tutturamadığını sanıp
   **~2°'lik eğimi hiç kaldırmıyor** → 0.34 m/s² ile sürekli hızlanma.
   (ULog: `trajectory_setpoint` mission'ın gönderdiğinin aynısı; eğim 1.2–2.1°.)
4. Araç 4.5 m/s'e kaçıyor; EKF hâlâ 0.05 m/s diyor ve
   `pos_horiz_accuracy`'yi **0.08–0.10 m** olarak bildiriyor.
5. Sapma büyüdükçe GPS yenilik kapısı **geç** devreye giriyor (t≈111.0)
   ve kestirimi büsbütün kilitliyor.

### Beş koşumda doz-yanıt

| koşum | EKF−gerçek max (alt<1.5 m) | `vel_test_ratio` | en kötü ıska |
|---|---|---|---|
| run5 (2 yakınsayan) | **0.53 m** | 0.10 | 0.06 / 0.45 m |
| run2 | 1.80 m | 0.41 | 2.12 m |
| run1 | 4.03 m | 0.75 | 4.11 m |
| run3 | 4.27 m | 0.43 | 5.31 m |
| run4 | **20.28 m** | 2.00 | 10.19 m |

Iska ≈ EKF hatası. Bu, "araç EKF koordinatlarında kusursuz tutuyor ama o
koordinatlar kayıyor" beklentisinin tam karşılığı.

---

## 4. Kendi FAZ 1 iddialarımdaki iki düzeltme

Bu bulguları çürütmeye gönderdiğim dört bağımsız mercek (metodoloji, ters
nedensellik, (b)'nin yeniden savunusu, alternatif açıklama) beni iki noktada
düzeltti; ikisini de kendi hesabımla doğruladım:

**D1 — Nedensellik yönü.** "GPS kapısı reddetmeye başlıyor → EKF ıraksıyor"
**yanlıştı.** Fiziksel kaçış t≈105.0'te başlıyor, GPS kapısı ilk reddi
t≈111.0'de yapıyor — **6 s sonra**. Kaçış boyunca GPS füzyonu açıktı
(244/245 örnek füzyona girdi) ve GPS gözlemleri gerçeğe 0.026–0.028 m/s
doğrulukta. Kapı reddi **sonuç**, tetikleyici değil. Ayrıca
`cs_inertial_dead_reckoning = 0` — EKF ölü-hesap yapmıyordu.

**D2 — "VEHICLE_TELEMETRY günlüğü 3.7 s geride" bulgum YANLIŞTI.**
O ölçümü yalnızca ıraksama pencerelerinde yapmışım; donmuş EKF konumu, yolun
daha erken bir noktasıyla tesadüfen eşleştiği için gecikme gibi görünmüş.
Tüm uçuş boyunca:

| koşum | "en-uyan gecikme" ortanca | aynı-an konum hatası ortanca |
|---|---|---|
| run5 (sağlıklı) | **+0.03 s** | 0.089 m |
| run4 (ıraksayan) | **−0.01 s** | 0.081 m (p95 12.6 — sapma anları) |

**Günlükleme yolunda kusur yok.** Görev E FAZ 1'deki hatalı okumamın sebebi
iki ayrı koşumun dosyalarını karıştırmamdı (zaten düzeltildi), gecikme değil.

---

## 5. İkincil bulgu: taban hızı bir röle üretiyor

(b) büyük ıskanın sebebi değil, ama masum da değil. Ölçüldü:
`right` ekseni run4'te 76 tick'in **63'ünde** tam `|0.1500|` m/s'e sabitlenmiş
(%83); run5'te **her iki eksen 6/6 tick'te** sabit. `|komut| / (kp·kalan)`
oranı run5'te ortanca **5.50** — yani sağlıklı koşumda bile P-yasası
0.045 m/s isterken döngü 0.212 m/s gönderiyor. Sonuç: ±0.01 m ölü bantlı bir
**röle**, ve tabandan kaynaklı ~22–24° medyan yönelme sapması. Santimetre
ölçeğinde etkili, metre ölçeğinde değil. Ayrı ve küçük bir iş kalemi.

---

## 6. Simülatör mü, gerçek donanım mı?

**Kesin olan:** `EKF2_OF_CTRL 1` projenin kendi airframe dosyasında ve PX4
yukarı akışında değil — bu bilinçli bir proje değişikliği.
**Simülatöre özgü olan:** Gazebo akış sensörünün quality 255 ile sıfır akış
üretmesi. Gerçek bir PX4Flow/PMW3901 bu şekilde davranmaz.
**Gerçek donanımda da geçerli olan:** `EKF2_OF_N_MIN × menzil` ağırlıklandırma
mantığı PX4'ün kendi kodudur. Araca **fiziksel bir akış sensörü takılıysa**,
0.4 m'de aynı aşırı-güven mekanizması işler. Sensör **takılı değilse** veri
gelmeyeceği için ayarın etkisi olmaz.

**Bu veri, gerçek donanımın nasıl davranacağını söyleyemez** — söylediği,
ayarın gerekçesiz açık olduğu ve simülasyonda ölçülebilir zarar verdiği.

---

## 7. Öneriler (UYGULANMADI, onay bekliyor)

Kritik olduğunu söylediğiniz için hiçbirine geçmedim.

| # | İş | Gerekçe | Risk |
|---|---|---|---|
| **E4a** | `4014_gz_x500_mono_cam_down` içinde `EKF2_OF_CTRL 0` yap **ve neden açıldığını araştır** | Tek satır; doz-yanıt tablosuna göre ıskaların tamamını açıklıyor | Düşük — ama önce **neden açıldığı** anlaşılmalı; bilinçli bir gerekçesi varsa onu bilmem gerek |
| E4b | Alternatif: `EKF2_OF_QMIN`'i anlamlı bir eşiğe çek ve/veya `EKF2_OF_N_MIN`'i yükselt | Akışı tamamen kapatmadan aşırı-güveni kır | Orta — ayar avı gerektirir |
| E4c | E4a sonrası 3 koşum ölç: isabet dağılımı ve EKF−gerçek hatası | Düzeltmenin kanıtı | Yok |
| E4d | Min-komut tabanı + ölü bant (bölüm 5) | Santimetre ölçeğinde iyileşme | Düşük, **kontrol yasasına dokunur** — ayrı onay |
| ~~E5~~ | ~~VEHICLE_TELEMETRY gecikmesi~~ | **İPTAL** — böyle bir kusur yok (bölüm 4/D2) | — |

E4a'yı tek başına önermemin sebebi: diğerlerinin hepsi onun sonucunu ölçmeye
bağlı. Ama bu bir PX4 parametre değişikliği ve uçuş davranışını doğrudan
etkiler — sizin onayınız olmadan dokunmuyorum.

Görev C/D değiştirilmedi, `motion_fsm.py`'a dokunulmadı, push yapılmadı.
