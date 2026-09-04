# TODO — CAD dosyası güncellemesi (gerçek donanım üretimi ÖNCESİ)

**Açılış:** 2026-09-04 (Görev I / B-S1) · **Durum: AÇIK** · **Öncelik: üretim öncesi ZORUNLU**

---

## Neden bu not var

Görev I / B-S1'de **donanım revizyonu** uygulandı: mıknatıs **Ø10 → Ø35 mm**,
kanca **0.198 → 0.250 m**. Değişiklik **SITL tarafında** yapıldı:

| dosya | durum |
|---|---|
| `Tools/simulation/gz/models/x500_mono_cam_down/model.sdf` | ✅ güncellendi (ip segmentleri + mıknatıs görseli) |
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
   - kanca toplam uzunluğu: **0.198 → 0.250 m** (SITL'de ipi uzatarak sağlandı;
     gerçek donanımda hangi parçanın uzayacağı CAD kararı)
2. Yükün çelik hedef diski: **Ø12.4 → Ø35** (SDF'de yapıldı, CAD'de de olmalı)
3. `core_lower.stl` / `core_upper.stl` mesh'leri Ø35 mıknatıs yuvasını
   taşıyacak şekilde yeniden dışa aktarılmalı — **SITL'de yapılamadı**,
   mesh düzenlenemedi (bkz. §4).

## 4 · SITL'deki uzlaşma — gerçek donanımda tekrarlanmamalı

Kanca 25 cm'e **ipi uzatarak** ulaştırıldı (4 segment 0.04575 → 0.05884 m),
çünkü kanca gövdesi STL mesh ve düzenlenemedi. **Gerçek donanımda uzunluğun
nereden geleceği bir CAD kararıdır** — ip mi uzayacak, kanca gövdesi mi?
İkisi farklı sarkaç davranışı verir (ölçülen periyot bugün 0.831 s; daha
uzun ip periyodu uzatır, daha uzun rijit gövde uzatmaz).

Bu fark **ölçülmüş bir eşiği doğrudan etkiliyor**: `MAGNET_DWELL_S = 0.50 s`
sarkaç periyodundan türetildi (`hook_seating.py`).

## 5 · İlgili

- `docs/gorevI-cakisma-kontrolu.md` — hangi Görev G bulgusu yeni geometriyle geçerli
- `docs/TODO-adr-guncellemeleri.md` — ADR borçları (ayrı liste)
