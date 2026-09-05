# GÖREV K / D — Manyetik çekim probe'u: ÖLÇÜM ALINAMADI

**Tarih:** 2026-09-05 · **Araç:** `tools/magnet_attract_probe.py` · **Push edilmedi**

---

## HÜKÜM

**İstenen "41 mm → ? mm" karşılaştırması ALINAMADI.** Probe uçtan uca
koştu ama ürettiği sayılar geçersiz. Üç sebep, üçü de **ölçüldü**:

| # | sorun | ölçülen |
|---|---|---|
| 1 | **Yük YAN YATTI** | `payload_blue` yerel +Z ekseni dünyada (+0.995, +0.103, 0.000) → **dikeyden 90.0°**, z = 0.025 m. Karşılaştırma: `payload_red` **4.9°** (dik duruyor). |
| 2 | İstenen yanal tutturulamadı | istenen **41 mm**, gerçekleşen **192–229 mm** (kontrol) / **96–109 mm** (çekim) |
| 3 | **Çekim hiç çalışmadı** | `cekim=None adim=None` — yanal, 50 mm'lik menzilin çok dışında kaldı |

Ayrıca iki kol **aynı noktadan başlamadı** (198 mm vs 109 mm medyan), yani
kontrollü bir A/B değil.

### Neden 1 belirleyici

Yük yan yatınca yuvanın ağız ekseni **yatay** olur. Oturma geometrisi
kanca eksenini yuva eksenine göre ölçtüğü için tilt **179.6°** (kontrol)
ve **54.3°** (çekim) okundu — kapı 8°. `tilt` reddi **494/494** ve
**492/493**. Bu geometride oturma **fizikselolarak imkânsız**, çekim
çalışsa bile.

Yani probe, ölçmek istediği şeyi ölçemeden kendi kurulumunda düştü.

---

## Probe'un iki kusuru (araç tarafı, sistem değil)

**K1 — Yükü DÜŞÜREREK yerleştiriyor.** 0.55 m'den bırakıyor ve duruşu
doğrulamıyor. Görev G, düşen yükün kenarı üstünde kalabildiğini zaten
kaydetmişti; bu koşumda yan yattı. Probe, yükü **deterministik biçimde
dik** yerleştirmeli (ör. Gazebo'ya doğrudan poz yazmak) ya da duruşu
ölçüp uygun değilse **tekrar denemeli**.

**K2 — Konumlandırma matematiği 150–190 mm tutarsız.** Hedef NED
hesabı (`d_n = Δy − hook_off_n + lateral`, `d_e = Δx − hook_off_e`)
Gazebo dünya deltası ile EKF NED'ini karıştırıyor; iki kolda farklı
artıklar çıkması da bunu gösteriyor. Ayrıca kanca ofseti kol başına
farklı okundu ((−0.089, −0.014) vs (−0.064, −0.029)) — kanca salınırken
tek örnekten okunuyor.

---

## Bu, sistem hakkında ne SÖYLEMİYOR

- Çekimin 41–72 mm'yi kapatıp kapatmadığı hakkında **hiçbir şey**.
  `MAGNET_ATTRACT_RANGE_M` kodu bir kez bile çalışmadı.
- Çekim kapılarının doğruluğu hakkında hiçbir şey (kapılar zaten
  `test_gorevK_miknatis_cekim.py` ile birim testinde kilitli).

---

## Bu, sistem hakkında ne SORDURUYOR (yeni, ölçülmedi)

**Görevde bırakılan yük de yan yatıyor olabilir mi?**
Probe 0.55 m'den bıraktı ve yan yattı. Görev 2 ~0.45–0.48 m'den bırakıyor.
`PAYLOAD_FINAL_POSE` olayı yalnızca **x, y** taşıyor — **duruş kaydedilmiyor.**
Eğer görevde de yan yatıyorsa, Faz 1'in alma başarısızlığının bir kısmı
erişim/çekim değil **duruş** kaynaklı olabilir ve bu şimdiye kadarki
teşhislerin hiçbirinde görünmedi.

Bu **bir iddia değil, bir soru** — tek bir probe düşüşünden görev
davranışına genelleme yapmıyorum.

---

## Sıradaki için seçenekler (uygulanmadı)

| # | ne | neden |
|---|---|---|
| **S1** | Probe'u düzelt: yükü deterministik ve DİK yerleştir (K1), konumlandırmayı kapalı çevrime çevir (K2) | İstenen ölçümü almanın en kısa yolu |
| **S2** | Önce görev bırakmalarının duruşunu ölç (`PAYLOAD_FINAL_POSE`'a kuaternion ekle) | Yukarıdaki soruyu kapatır; S1'den bağımsız ve daha küçük |
| **S3** | İkisi birden | S2 ucuz, S1 asıl ölçümü verir |

Önerim: **S2 → S1.** S2 tek bir alan ekler ve mevcut koşum verisini
anlamlandırır; S1 ise ancak yük dik durduğunda anlamlı sonuç verir.
