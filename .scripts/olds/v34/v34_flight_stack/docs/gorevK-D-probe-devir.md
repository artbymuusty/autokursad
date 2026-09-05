# DEVİR — Görev K / D: manyetik çekim probe'u

**Tarih:** 2026-09-05 · **Durum: YARIM** · **31 commit, PUSH EDİLMEDİ**
**Son commit:** `32227a02`

Bu dosya, probe işinin **tek** devir noktasıdır. Yeni bir oturum yalnızca
bunu okuyarak devam edebilmeli.

---

## 1 · CEVAPLANMAMIŞ ASIL SORU

> Manyetik çekim (`MAGNET_ATTRACT_RANGE_M = 0.05`), J demosunda ölçülen
> **41–72 mm**'lik yanal hatayı gerçekten kapatıyor mu?

**Hâlâ bilinmiyor.** Toplam **5 canlı koşum** yapıldı (1 × v1, 4 × v2–v4);
hiçbiri kontrollü bir A/B üretmedi. Çekim kodu bir kez tetiklendi
(`cekim adimi: d=25.8 mm`) ama ölçüm geçerli değildi.

---

## 2 · ÇÖZÜLENLER

### K1 ✅ — yükü deterministik ve dik yerleştir
v1 yükü 0.55 m'den **düşürüyordu** ve duruşu doğrulamıyordu; ölçüldü:
yan yattı (**90.0°**), yuva ağzı yatay kaldı, tilt 179.6° okundu, ölçüm
daha başlamadan geçersizleşti.

Çözüm: `/world/default/set_pose` (`gz.msgs.Pose`) ile birim kuaterniyonla
yerleştirme + duruş **ölçümü**; 5°'yi aşarsa probe hiç başlamıyor.
**İki koşumda da `DURUS egimi = 0.0°`.**

Bırakma çağrısı korundu — yük `DetachableJoint` ile bağlı, ayrılmadan
taşınamıyor. Ama nereye düştüğü artık önemsiz.

### K3 ✅ — kendiliğinden kapandı
Düşürme ortadan kalkınca, görevin bırakma koreografisini (`RELEASE_HOLD` +
aim-offset) taklit etme ihtiyacı da kalmadı.

### Yan bulgu ✅ — yükler görevde yan YATMIYOR
`PAYLOAD_FINAL_POSE` zaten `tilt_deg` taşıyormuş. **202 bağımsız bırakma**
tarandı: ortanca **0.2°**, p90 0.6°, max 6.7°, **0/202** > 15°.
→ Yerleştirme/düşürme fizik modelini önce düzeltmeye **gerek yok**;
Görev K'nın D/E/F/G/H önceliği **değişmiyor**.

---

## 3 · ÇÖZÜLMEYEN — K2 (konumlandırmayı kapalı çevrime al)

| sürüm | ayar | sonuç |
|---|---|---|
| **v2** | kazanç 0.6, bekleme 0.5 s | **Iraksadı.** 418 → 574 → 1822 → **178 844 893 mm**; setpoint (+71393, −423256), araç ~400 km uçtu, sim bozuldu. Sebep: düzeltme uygulanıp aracın **varması beklenmeden** yenisi ekleniyordu (integrator windup). |
| **v3** | görevin ölçtüğü ayar (`HOOK_SETTLE_GAIN=0.5`, `HOOK_SETTLE_WAIT_S=2.5`, max 6) + "1 m üstü geçersiz" kapısı | Iraksama **durdu** ✅, yakınsama **yok**. KONTROL 197→636→420→**350 mm**, ÇEKİM 84→252→429→**339 mm**. Pencerede `tilt=78.9°`, `v=0.760 m/s` — araç hâlâ hareketli, kanca savruluyor: 200 mm'lik düzeltme sarkacı uyandırıyor, sonraki okuma salınımı ölçüyor, döngü kendi uyandırdığını kovalıyor. |
| **v4** | **vinci önce sal, sonra hizala** (görevin kendi notu, `gorev3_pickup.py`) | Artık **kararlı** (`v=0.000`, artık 1180.6 / 1091.9 mm) ama **1 m'lik akıl sağlığı kapısı her düzeltmeyi blokluyor**: probe yükü aracın **1.0 m** kuzeyine koyuyor, başlangıç hatası zaten ~1.18 m. **Eşik yanlış seçildi** — kapı, yakalamak istediği çöp okumayı (178 milyon mm) değil kurulumun meşru hatasını engelliyor. |

---

## 4 · AÇIKLANAMAYAN ANOMALİ — `tilt` 165–169°

v4'te oturma kapısı **165.3° / 169.2°** okudu, kanca **hareketsizken**
(`v = 0.000 m/s`, `age = 0.00 s`).

**Çelişki:** gerçek görev koşumlarında aynı kapı **0.1–0.5°** okuyor
(B2, C1). Yük duruşu her iki durumda da dik (probe 0.0°, görev ortanca 0.2°).

Aday açıklama (**doğrulanmadı, yetersiz**): probe 0.30 m irtifada 0.33 m
salım yapıyor → kanca zemine yaslanıp devriliyor olabilir. Ama **aynı şey
görevde de oluyor ve orada tilt küçük okunuyor.**

⚠️ **A/B ölçümü bu kapanmadan anlamsız** — oturma kapısı tilt'te takılı
kaldığı sürece çekimin lateral'i kapatıp kapatmadığı görünmez.

---

## 5 · SIRADAKİ İŞ — P1 → P2 → P3 (bu sırayla)

**P1 — probe kurulumunu düzelt (küçük, mekanik)**
- Yükü aracın **1.0 m** değil **~0.15 m** yanına yerleştir
  (`main()` içinde `hedef_y = arac0[1] + 1.0`)
- Akıl sağlığı kapısını **1.0 m → 2.0 m** çıkar
  (`pencere()` içinde `if son_hata > 1.0`)
- Beklenen: başlangıç hatası kapının altına iner, döngü fiilen çalışır

**P2 — 165° tilt anomalisini açıkla (ZORUNLU, P3'ten önce)**
- Aynı anda ölç: kanca kuaterniyonu, yuva kuaterniyonu, vinç `achieved_m`,
  kanca burnu dünya z'si
- Karşılaştır: probe penceresi vs görev penceresi (B2/C1 logları)
- Soru: kanca gerçekten mi deviriliyor, yoksa geometri farklı bir
  referansla mı hesaplanıyor?

**P3 — asıl A/B'yi koş**
- `--lateral-mm 41`, kontrol (`on_attract=None`) vs çekim
- Rapor: yanal zaman serisi, **17.5 mm** altına inen örnek sayısı,
  **5 mm** eksenel, **8°** tilt kapılarının geçilip geçilmediği,
  `CAPTURE_CANDIDATE`'a geçiş, dwell (**0.60 s**) yeterli mi

---

## 6 · OKUNACAK DOSYALAR (öncelik sırasıyla)

1. **bu dosya**
2. `docs/gorevK-S1-probe-v2.md` — K1/K2/K3'ün ayrıntılı ölçümleri
3. `docs/gorevK-D-probe-sonuc.md` — v1'in neden geçersiz olduğu (90° yan yatma)
4. `tools/magnet_attract_probe.py` — aracın kendisi; K1/K2 notları kod içinde
5. `docs/gorevI-OA-sonuc-OB-butce.md` — Ö-A düzeltmesi (kapı yanlış yüke
   bakıyordu) + 60 s bütçesinin gerçek dağılımı
6. `docs/gorevI-B-yakalama-analiz.md` — "yakalama penceresine hiç
   girilmedi" teşhisi
7. `docs/gorevG-O5-kok-neden.md` — EKF↔gerçek farkı 0.09–0.29 m
   (**K2'nin açık çevrimde neden çalışamadığının sebebi**)

---

## 7 · ÇALIŞMA DURUMU

- Çalışma ağacı **temiz** (tek `M`: `default.sdf`, SITL her açılışta
  yeniden üretiyor)
- **31 commit, push edilmedi**
- Süreç kalıntısı yok (px4 / gz sim / mavsdk_server kapalı)
- Test paketi son tam koşumda **568 geçti / 1 atlandı / 0 başarısız**

### Operasyonel tuzaklar (bu turda bedeli ödendi)
- Probe'u **`gz_env.sh` source etmeden** çalıştırma → GZ_PARTITION
  uyuşmazlığı, poz izleyici sessizce boş döner
- Koşumlar arası `mavsdk_server` **öldürülmeli** ve **14540 portu
  boşalana kadar beklenmeli**; yoksa `bind error` / `Stream removed`
- Foreground `timeout` bu kabukta **yok**; uzun koşumlar arka planda
