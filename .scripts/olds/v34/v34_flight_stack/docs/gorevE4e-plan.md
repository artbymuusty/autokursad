# Görev E4e — Iraksama koruması: PLAN (uygulanmadı, onay bekliyor)

**Tarih:** 2026-09-03 · Eşikler run4/run5/run6 verisinden türetildi, uydurulmadı.

---

## 0. Önce bir uyarı: önerdiğiniz 2. guard yazıldığı hâliyle ÇALIŞMAZ

> "(2) yer hızı bir eşiği (öner: 0.5 m/s?) aşarken payload bırakılmasın"

Yer hızı **EKF'ten** okunur (`get_velocity_ned()` → `position_velocity_ned`,
aynı kestirim). Iraksama anında EKF **yalan söylüyordu**:

| run4, bırakma anı | EKF'in bildirdiği | GERÇEK |
|---|---|---|
| yatay hız | **0.05 m/s** | **3.00 m/s** |

Yani EKF hızına dayalı bir kapı, onu doğuran arızayı **tam olarak
göremezdi** — run4'te sessizce açık kalırdı. Aynı şey `get_position_ned`
için de geçerli. Araç üstünde bağımsız bir hız kaynağı yok.

Denedim, işe yaramayan bir alternatif de var — "komut ediyorum ama kendi
kestirimim hareket etmiyorum diyor" oranı **ayırmıyor**:
run4 (ıraksayan) 0.43, run5 (sağlıklı) **0.23**, run6 (sağlıklı) 0.77.
Sağlıklı koşum ıraksayandan daha düşük. Bu metriği eledim.

**Ayıran tek iç gözlem: kalan mesafenin eğilimi ve yakınsama sonucu.**

---

## 1. Guard 1 — ıraksama dedektörü

**Dosya:** `core/navigation/centering_controller.py`, `_mount_translate`
döngüsü içi.

**Mantık:**
```
residual bir önceki tick'ten EPS=1e-3 m fazlaysa  -> ardisik_buyume += 1
                                     degilse      -> ardisik_buyume = 0
if ardisik_buyume >= N  ve  residual > MOUNT_TRANSLATE_TOLERANCE_M:
     -> donguden CIK, MOUNT_TRANSLATE_DIVERGED yayinla, diverged=True dondur
```

**N için kanıt** (`MOUNT_TRANSLATE_TICK` kayıtlarından, en uzun **ardışık**
büyüme serisi):

| koşum | sonuç | n tick | en uzun ardışık büyüme | net değişim |
|---|---|---|---|---|
| run5 | yakınsadı | 6 | **0** | −0.029 m |
| run6 | yakınsadı | 13 | **1** | −0.042 m |
| run4 | SÜRE DOLDU | 76 | **12** | +0.291 m |

**Öneri: N = 5.** Sağlıklı koşumlarda görülen en kötü değerin (1) **5 katı**,
ıraksayan koşumun ulaştığı 12'nin altında. 10 Hz'de 0.5 s demek — kaçış
8 s yerine ~0.5 s'de kesilir.
`residual > tolerans` ek koşulu, normal yakınsama sırasındaki milimetrik
gürültünün guard'ı tetiklemesini imkânsız kılar.

**Dürüst sınır:** elimde tick kaydı olan yalnızca **3** `_mount_translate`
penceresi var (E4a öncesi enstrümantasyon yoktu). N=5 bu üç pencereye göre
güvenli; daha uzun bir sağlıklı pencere daha çok büyüme gösterebilir. Bu
yüzden N'i parametre yapıp E4c'nin 3 koşumunda doğrulamayı öneriyorum.

---

## 2. Guard 2 — bırakma kapısı (önerinizin yerine)

**Dosya:** `core/mission/payload_release.py`, servo ateşlenmeden önce.

**Birincil kapı: YAKINSAMA, hız değil.** 8 bırakmada kusursuz ayrışıyor:

| mount_translate | ıska aralığı |
|---|---|
| yakınsadı (n=5) | 0.059 – 0.885 m |
| süre doldu / ıraksadı (n=4) | 2.121 – 10.185 m |

`converged` zaten hesaplanıyor ve loglanıyor; yeni telemetri gerekmiyor
(ADR-008 B0/B1 uyarısına uyar).

**İkincil kapı: yer hızı < 0.5 m/s.** Sizin önerdiğiniz değeri **koruyorum**
ve veriyle destekliyorum — ama *ikincil* olarak, sınırını açıkça yazarak:

| bırakma | EKF'ten okunan hız | ıska |
|---|---|---|
| run5 KIRMIZI | 0.036 m/s | 0.059 m |
| run6 KIRMIZI | 0.035 m/s | 0.341 m |
| run5 MAVI | 0.206 m/s | 0.448 m |
| run4 KIRMIZI | (gerçek 2.864) | 10.185 m |

Sağlıklı bırakmaların en kötüsü **0.206 m/s**; 0.5 m/s bunun **2.4 katı**,
yani yanlış tetiklemez. Kaba bir hareketi yakalar; **kestirim arızasına
kördür** ve dosyada böyle belgelenecek.

---

## 3. Guard tetiklendiğinde görev ne yapar — ÖNERİM

Üç seçenek ve gerekçeleri:

| | ne yapar | değerlendirme |
|---|---|---|
| (i) Tam abort | görevi bitir | **Fazla sert.** Yük hâlâ araçta, araç sağlam, Görev 2'nin ikinci yükü ve Görev 3 duruyor |
| (ii) **Yükselip bir kez tekrar dene** | son yaklaşma irtifasına (5.0 m) tırman, `go_to_and_center` + final adımı tekrarla | **ÖNERİM.** Tırmanmak iki sorunu birden çözer: 2.0 m'lik `LOW_ALT_VISION_LIMIT_M` üstüne çıkıp **görüşü geri kazandırır**, ve kestirimin en kötü olduğu güverte bölgesinden uzaklaştırır |
| (iii) Bu yükü atla | yükü araçta tut, CRITICAL yayınla, `release_and_verify` False dönsün | (ii) de başarısız olursa **buraya düş** |

**Önerim: (ii) → başarısızsa (iii).**

Mimariye uyumu: `release_and_verify`'ın dönüşü zaten `gorev2_fsm.py:93/119`
tarafından kullanılıyor, yani "bu bırakma olmadı" durumu **zaten** temsil
edilebiliyor. Yeni bir görev durumu icat etmeye gerek yok.

**Dikkat çekmek istediğim mimari çelişki:** `_staged_approach`'un docstring'i
şu anda bunun tersini söylüyor —
> "Ara adımlardan biri yakınsayamazsa akışı durdurmak yerine devam edilir
> (best-effort -- alçalmanın ortasında durup hiç bırakmamak, hafif kusurlu
> bir pozisyondan bırakmaktan daha kötüdür)."

Bu karar **"hafif kusurlu"** varsayımıyla alınmış. Ölçüm o varsayımı çürüttü:
yakınsamama **10 m** demek olabiliyor. Guard 2, bu politikayı **yalnızca son
adım için** tersine çevirir; ara adımlar (10 m, 5 m) best-effort kalır.
Bu, bilinçli bir tasarım kararının değiştirilmesidir — onayınızı bu yüzden
ayrıca istiyorum.

---

## 4. Dokunulacak dosyalar

| dosya | değişiklik |
|---|---|
| `core/config/parameters.py` | `MOUNT_TRANSLATE_DIVERGE_TICKS = 5`, `MOUNT_TRANSLATE_DIVERGE_EPS_M = 0.001`, `PAYLOAD_RELEASE_MAX_GROUND_SPEED_M_S = 0.5`, `PAYLOAD_RELEASE_RETRY_ALTITUDE_M = 5.0` |
| `core/navigation/centering_controller.py` | `_mount_translate`: ıraksama sayacı + erken çıkış + `MOUNT_TRANSLATE_DIVERGED` olayı; sonucu `self.last_translate_diverged` alanına yaz (mevcut `getattr` ile zarif düşme desenine uyar) |
| `core/mission/payload_release.py` | son adımda servo öncesi kapı; tetiklenirse (ii) tırman-ve-tekrar-dene, sonra (iii) atla |
| `tests/` | yeni testler: N eşiği, gürültüde tetiklenmeme, kapının ateşlemeyi engellemesi, tekrar-deneme yolu, atlama yolu |

**Dokunulmayacak:** `motion_fsm.py`, Görev C'nin `_start_release_hold`
mekanizması, `go_to_and_center`, ara yaklaşma adımlarının best-effort'u.

---

## 5. Onayınızı istediğim üç nokta

1. **Yer hızı kapısını ikincil**e indirip **yakınsamayı birincil** yapmam —
   çünkü hız kapısı tek başına run4'ü kaçırırdı.
2. **Guard tetiklenince (ii) tırman-ve-tekrar-dene, sonra (iii) atla.**
3. `_staged_approach`'un **son adım** için best-effort politikasının
   tersine çevrilmesi (ara adımlar aynı kalır).

E4a uygulandıktan sonra bu guard'ın SITL'de **hiç tetiklenmemesi** beklenir;
amacı gerçek donanım ve gelecekteki kestirim sorunları için derinlemesine
savunmadır.
