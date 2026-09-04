# TODO — CAD dosyası güncellemesi (gerçek donanım üretimi ÖNCESİ)

**Açılış:** 2026-09-04 (Görev I / B-S1) · **Güncelleme:** 2026-09-04 (Görev J — kanca 31 cm)
**Durum: AÇIK** · **Öncelik: üretim öncesi ZORUNLU**

---

## Neden bu not var

Görev I / B-S1'de **donanım revizyonu** uygulandı: mıknatıs **Ø10 → Ø35 mm**,
kanca **0.198 → 0.250 m**. **Görev J'de (2026-09-04) kanca yeniden uzatıldı:
0.250 → 0.310 m (31 cm).** Değişiklik **SITL tarafında** yapıldı:

| dosya | durum |
|---|---|
| `Tools/simulation/gz/models/x500_mono_cam_down/model.sdf` | ✅ güncellendi (ip segmentleri 0.07384 m + mıknatıs görseli) |
| `Tools/simulation/gz/worlds/default.sdf` | ✅ güncellendi (yükün hedef diski Ø12 → Ø35, iki yük) |
| `core/mission/hook_seating.py` | ✅ güncellendi (B-S4: pim-yuva → mıknatıs kapısı) |
| **`PCBV1_PARAMETERS.txt`** | ❌ **GÜNCELLENEMEDİ** |

## Sorun

`PCBV1_PARAMETERS.txt` **bu depoda yok.** Yalnızca `model.sdf`'in yorumundan
referans veriliyor:

```
MIKNATIS (hook_magnet, O35 x 2 mm). GOREV I / B-S1, 2026-09-04.
DONANIM REVIZYONU: onceki CAD O10.00 diyordu (PCBV1_PARAMETERS.txt,
hook_magnet_diameter 10.00).
```

Yani SITL modeli artık **Ø35** diyor, CAD dosyası hâlâ **Ø10** diyor.
İkisi **ayrışmış durumda** ve bu ayrışma depodan görünmüyor.

## Yapılması gerekenler

1. `PCBV1_PARAMETERS.txt` içinde güncellenecek alanlar:
   - `hook_magnet_diameter`: **10.00 → 35.00**
   - `hook_magnet_thickness`: spec'te verilmedi, **2.00 olduğu gibi bırakıldı** — teyit edilmeli
   - kanca toplam uzunluğu: **0.198 → 0.250 → 0.310 m** (güncel hedef **31 cm**;
     SITL'de ipi uzatarak sağlandı, gerçek donanımda hangi parçanın uzayacağı
     CAD kararı)
2. Yükün çelik hedef diski: **Ø12.4 → Ø35** (SDF'de yapıldı, CAD'de de olmalı)
3. `core_lower.stl` / `core_upper.stl` mesh'leri Ø35 mıknatıs yuvasını
   taşıyacak şekilde yeniden dışa aktarılmalı — **SITL'de yapılamadı**,
   mesh düzenlenemedi (bkz. §4).

## 4 · SITL'deki uzlaşma — gerçek donanımda tekrarlanmamalı

Kanca önce 25 cm'e, **Görev J'de 31 cm'e** yine **ipi uzatarak** ulaştırıldı
(4 segment 0.04575 → 0.05884 → **0.07384 m**), çünkü kanca gövdesi STL mesh ve
düzenlenemedi. **Gerçek donanımda uzunluğun nereden geleceği bir CAD
kararıdır** — ip mi uzayacak, kanca gövdesi mi? İkisi farklı sarkaç davranışı
verir: daha uzun ip periyodu uzatır, daha uzun rijit gövde uzatmaz.

Bu artık **varsayım değil, ölçüm**: aynı uyaranla (3 m'de 6 m yanal adım)
yapılan ölçümde periyot **0.831 s → 1.078 s** çıktı (+%30), tepe genlik
**~60 mm → 107 mm**. Yani 6 cm'lik uzatmanın tamamı ipe verildiğinde sarkaç
belirgin biçimde yavaşlıyor.

Bu fark **ölçülmüş bir eşiği doğrudan etkiliyor**: `MAGNET_DWELL_S`
sarkaç periyodundan türetiliyor (`hook_seating.py`) ve Görev J'de
**0.50 → 0.60 s** olarak yeniden türetildi (kural: dwell, saf bir salınım
geçişini dışlamak için yarım periyodu — 0.549 s — aşmalı).

**CAD kararı bu sayıyı değiştirir:** uzatma gövdeden verilirse periyot
1.078 s'den küçük kalır ve dwell yeniden türetilmelidir. Ölçüm araçları
depoda: `tools/pendulum_step_flight.py` + `tools/measure_hook_pendulum.py`.

## 5 · İlgili

- `docs/gorevI-cakisma-kontrolu.md` — hangi Görev G bulgusu yeni geometriyle geçerli
- `docs/TODO-adr-guncellemeleri.md` — ADR borçları (ayrı liste)
