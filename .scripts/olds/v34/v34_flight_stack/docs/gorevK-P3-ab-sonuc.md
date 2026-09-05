# GÖREV K / P3 — Manyetik çekim A/B: **ÇEKİM YANAL HATAYI KAPATMIYOR**

**Tarih:** 2026-09-05 · **Koşum:** `p41j` · **Push edilmedi**
P1 ✅ · P2 ✅ (açıklandı) · P3 ✅ (ölçüm alındı)

---

## 1 · Kurulum ilk kez TEMİZ

| kontrol | değer |
|---|---|
| yük duruşu (iki kolda da) | **dikeyden 0.0°** ✅ |
| kanca zinciri | poz (0.011, −24.67, −0.034) — **km ölçeği yok**, patlama yok ✅ |
| kapalı çevrim | 75 → 39 → 52 → 27 → 65 → 52 mm — **ıraksamıyor** ✅ |
| **çekim tetiklendi mi** | **EVET — 11 adım**, d = 49.7 → 41.7 mm ✅ *(ilk kez)* |

Önceki beş koşumun hiçbirinde çekim kodu çalışmamıştı.

---

## 2 · SONUÇ — çekim ölçülebilir bir fayda sağlamadı

| | KONTROL (çekim kapalı) | **ÇEKİM (5 cm menzil)** |
|---|---|---|
| örnek | 246 | 247 |
| yanal ilk → son | 63.6 → 59.9 mm | 64.3 → **82.0 mm** |
| yanal **min** | **44.5 mm** | **41.4 mm** |
| yanal medyan | 59.9 mm | **60.3 mm** |
| **17.5 mm altına inen** | **0/246** | **0/247** |
| oturdu mu | hayır | hayır |

**Medyan 59.9 → 60.3 mm, min 44.5 → 41.4 mm.** Fark, tek koşumun
gürültüsü mertebesinde. **Çekim, 41–72 mm bandındaki yanal hatayı
kapatmıyor.**

Çekim adımları hedefe doğru ~20 mm'lik düzeltmeler üretti ama ölçülen
mesafe 41–50 mm arasında **salındı, kapanmadı**.

---

## 3 · P2 — tilt anomalisi AÇIKLANDI

Ham bileşenler aynı anda ölçüldü:

```
kanca  poz=(0.0105, -24.6662, -0.0341)   dikeyden=153.2 deg
yuva   poz=(0.0159, -24.7012,  0.0350)   dikeyden=  0.0 deg   ← DİK
vinc   achieved=0.3203   span=0.0941 (gergin: 0.235)
       fold=[20.4, 68.2, 68.6, 48.2]     ← zincir BÜKÜLMÜŞ
       nose_z=-0.0987                    ← burun ZEMİNİN 10 cm ALTINDA
GEOMETRI lateral=64.4 mm  insertion=+46.4 mm  tilt=153.2 deg
```

**Yük dik (0.0°) ama kanca 153° yatık.** Sebep ölçüldü: 0.30 m irtifada
0.32 m salım + 0.25 m kanca ⇒ burun z = **−0.099 m**, yani **zemine
sürülüyor**. Zincir buna bükülerek tepki veriyor (`span` 0.235 → 0.094,
mafsallar 68°'ye kadar) ve kanca yan yatıyor.

**Yani anomali probe ile görev arasında bir MODEL farkı değil:** probe
kancayı yere sürüyor, görev sürmüyor. Önceki turda "aday açıklama
yetersiz" denmişti çünkü görevde de aynı salım var sanılıyordu — fark,
görevde kancanın yuvanın **üstünde** kalmasında: C1'de `ins = −61…−152 mm`
(burun güvertenin ÜSTÜNDE), burada `ins = +46 mm` (altında).

⚠️ **Bu, A/B sonucunu geçersiz kılmıyor ama sınırlıyor:** tilt kapısı
493/493 ve 494/494 reddettiği için oturma zaten imkânsızdı. Ölçtüğümüz
şey **çekimin lateral üzerindeki etkisi** — ve orada da fayda yok.

---

## 4 · Ne biliyoruz, ne bilmiyoruz

**Biliyoruz (ölçüldü):**
- Çekim kodu çalışıyor, adım üretiyor, menzile giriyor.
- 41–64 mm bandında **lateral'i kapatmıyor** (medyan 59.9 → 60.3 mm).
- Probe'un tilt anomalisi kancanın zemine sürülmesinden; yük duruşundan
  veya model farkından değil.

**Bilmiyoruz:**
- Kanca **serbest asılıyken** (zemine değmeden) çekim işe yarar mıydı?
  Bu koşumda tilt kapısı zaten kapalıydı; çekimin lateral etkisi ölçüldü
  ama "tam koşullarda oturur muydu" sınanmadı.
- Çekim ayarı (kazanç 0.6, adım tavanı 20 mm, periyot 0.4 s) hiç
  taranmadı; bunlar `9980813e`'de "ölçümle ayarlanacak" diye konmuştu.

---

## 5 · Öneri — karar operatörde

Çekim modeli mevcut ayarıyla **beklenen faydayı vermiyor.** Üç yol:

| # | ne | maliyet |
|---|---|---|
| **A** | Çekimi **kancayı yere sürmeden** ölç: alma irtifasını 0.30 → ~0.45 m çıkar, tilt kapısı açılsın, A/B'yi tekrarla | 1 koşum |
| **B** | Çekim ayarını tara (kazanç / adım tavanı / periyot) | 3–5 koşum |
| **C** | Çekim modelini yeniden düşün — kancayı aracı oynatarak çekmek, sarkacı uyandırdığı için kendi kendini bozuyor olabilir | tasarım |

**Önerim: A.** En ucuz ve tek başına belirleyici — tilt kapısı açıkken
çekimin lateral'i kapatıp kapatmadığı görülür. B ve C ancak A'dan sonra
anlamlı.

**Görev K'nın E-F-G-H maddelerine geçme kararı operatöre bırakıldı.**
