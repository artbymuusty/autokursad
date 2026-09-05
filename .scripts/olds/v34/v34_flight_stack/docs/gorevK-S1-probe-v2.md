# GÖREV K / S1 — Probe v2: K1 çözüldü, K2 çözülmedi

**Tarih:** 2026-09-05 · **Push edilmedi** · **4 canlı koşum**

---

## HÜKÜM

| madde | durum |
|---|---|
| **K1** yükü deterministik/dik yerleştir | ✅ **ÇÖZÜLDÜ ve iki kez doğrulandı** |
| **K3** bırakma koreografisi tutarlılığı | ✅ **kendiliğinden kapandı** (K1 düşürmeyi ortadan kaldırdı) |
| **K2** konumlandırmayı kapalı çevrime al | ❌ **ÇÖZÜLMEDİ** |
| **Asıl A/B ölçümü (41 mm)** | ❌ **HÂLÂ ALINAMADI** |

---

## K1 ✅ — düşürme yerine doğrudan yerleştirme

`/world/default/set_pose` (`gz.msgs.Pose`) ile yük istenen noktaya birim
kuaterniyonla konuyor, ardından duruş **ölçülüyor** ve 5°'yi aşarsa probe
durup ölçümü geçersiz saymak yerine **hiç başlamıyor**.

İki koşumda da: **`DURUS egimi = 0.0 deg`**, z = 0.0279–0.0280 m.
v1'in 90.0°'lik yan yatması tamamen ortadan kalktı.

Bırakma çağrısı **korundu** — yük dünyaya `DetachableJoint` ile bağlı ve
ayrılmadan taşınamıyor. Ama nereye düştüğü artık önemsiz; yerleştirme
konumu da duruşu da eziyor. **K3 bu yüzden ayrı bir iş olmaktan çıktı.**

---

## K2 ❌ — üç ardışık deneme, üçü de yetersiz

### v2: açık çevrimden kapalı çevrime — **ıraksadı**

Kazanç 0.6, bekleme 0.5 s. Düzeltme uygulanıp aracın **varması
beklenmeden** yenisi ekleniyordu (integrator windup):
```
artik 418 → 574 → 1822 → ... → 178 844 893 mm
setpoint (+71393, −423256)      ← araç ~400 km uçtu, sim bozuldu
```

### v3: görevin ölçülmüş ayarı + akıl sağlığı kapısı — **ıraksama durdu, yakınsama yok**

`HOOK_SETTLE_GAIN=0.5`, `HOOK_SETTLE_WAIT_S=2.5`,
`HOOK_ALIGN_MAX_CORRECTIONS=6` + "1 m'den büyük düzeltme okuma hatasıdır"
kapısı.

**Kapı işini yaptı** — uçup gitme bir daha olmadı. Ama:
```
KONTROL: 197 → (2 geçersiz) → 636 → 420 → 350 mm
CEKIM  :  84 → 252 → 414 → 429 → 419 → 339 mm
```
Ölçüm penceresinde `tilt = 78.9°`, `v = 0.760 m/s` — **araç hâlâ hareket
halinde ve kanca savruluyordu.** 200 mm'lik bir düzeltme sarkacı
uyandırıyor, sonraki okuma salınımı ölçüyor, döngü kendi uyandırdığı
salınımı kovalıyor.

### v4: "vinci önce sal, sonra hizala" — **artık sabit ama kapı bloklu**

Görevin kendi notunu taşıdım (`gorev3_pickup.py`: *"Ilk surumde sira
tersti: once hizala, sonra... vinci saliyordu"*). Vinç artık hizalamadan
önce salınıyor.

Sonuç: artık **kararlı** (1180.6 / 1091.9 mm, salınım yok, `v=0.000`) ama
**benim 1 m'lik akıl sağlığı kapım her düzeltmeyi blokluyor** — çünkü
probe yükü aracın **1.0 m kuzeyine** koyuyor, yani başlangıç hatası
zaten ~1.18 m.

**Kapı, yakalamak istediği çöp okumayı (178 milyon mm) değil, kendi
kurulumumun meşru başlangıç hatasını engelliyor.** Eşik yanlış seçildi.

---

## Açıklanamayan bulgu — `tilt` 165–169°

v4'te oturma geometrisi **tilt = 165.3° / 169.2°** okudu (kapı 8°),
`v = 0.000 m/s` ile, yani kanca hareketsizken.

Bu, gerçek görev koşumlarındaki okumalarla **çelişiyor**: B2/C1'de aynı
kapı `tilt = 0.1–0.5°` okuyordu. Yük duruşu her iki durumda da dik
(ölçüldü: probe 0.0°, görev 0.2° ortanca).

Aday açıklama (**doğrulanmadı**): probe 0.30 m irtifada 0.33 m salım
yapıyor, yani kanca zemine yaslanıp deviriliyor olabilir. Ama aynı şey
görevde de oluyor ve orada tilt küçük okunuyor — yani açıklama eksik.
**Bu ayrıca incelenmeli; A/B ölçümünden önce kapanması gerekebilir.**

---

## Ne öğrenildi (ölçülmüş, kalıcı)

1. **Yükü düşürmek ölçüm için güvenilir değil**; doğrudan yerleştirme + duruş
   doğrulaması çalışıyor ve ucuz.
2. **Açık çevrim konumlandırma EKF sapmasını devralıyor** — Ö5'te ölçülen
   0.09–0.29 m'lik EKF↔gerçek farkı doğrudan hedefe biniyor.
3. **Kapalı çevrim, sönümleme olmadan pozitif geri besleme** — görevin
   2026-08-26'da ölçtüğü tuzağın aynısı; ayarını kopyalamak zorunlu.
4. **Akıl sağlığı kapısı şart** ama eşiği kurulumun başlangıç hatasından
   büyük seçilmeli.

---

## Sıradaki (uygulanmadı)

| # | ne | neden |
|---|---|---|
| **P1** | Yükü aracın 1.0 m değil **~0.15 m** yanına yerleştir | Başlangıç hatası kapının altına iner; kapı 2 m'ye çıkarılmalı |
| **P2** | 165° tilt'i açıkla — görevde 0.5°, probe'da 165° | Kapanmadan A/B anlamsız; oturma kapısı tilt'te takılı kalır |
| **P3** | P1+P2 sonrası A/B'yi tekrar koş | Asıl ölçüm |

**Dürüst durum: dört koşumda asıl soru (41 mm → ? mm) hâlâ
cevaplanmadı.** Probe iki kusurundan birini kapattı, diğerini kapatmadı ve
yolda yeni bir soru (165° tilt) açtı.
