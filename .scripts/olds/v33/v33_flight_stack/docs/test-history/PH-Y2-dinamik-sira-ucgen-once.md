---
phase_id: PH-Y2
date: 2026-08-24
title: Dinamik görev sırası — "üçgen önce" senaryosu SITL'de üretilemedi
commit: ~
status: open-risk
metrics:
  altigen_once_sonuc: "3/3 tam basari"
  ucgen_once_sonuc: "senaryo uretilemedi"
  deneme_sayisi: 2
  kamera_yer_izi_yaricapi_m: 18
  home_altigen_mesafe_m: 15
raw_artifacts:
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15tri_sitl_T[12].log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15tri_mission_T[12].log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15_sitl_T[123].log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15_mission_T[12].log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/tri*.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/hexfirst.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/trifirst.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/restore_sitl.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/route_*.json"
---

# PH-Y2 — Dinamik görev sırası: "üçgen önce" SITL'de kanıtlanamadı

## Amaç

2026-08-24'te Görev 2 dinamik sıraya geçirildi: hangi şekil önce tespit
edilirse onun yükü önce bırakılır (V33 spec md.6/11). Kabul kriteri **iki
senaryonun da** SITL'de kanıtlanmasıydı.

## Değişiklikler

Görev 2 sabit sıradan dinamik sıraya geçirildi. `gorev3_redrop.py` ve
`gorev3_pickup.py` `mission_v3_state` üzerinden `second_mission_shape` /
`1st_mission` okuyacak şekilde güncellendi (sabit `KIRMIZI_UCGEN` düştü).

## Test sonucu

| Senaryo | SITL sonucu |
|---|---|
| Mavi Altıgen önce | ✅ 3/3 tam başarı, `1st_mission=MAVI_ALTIGEN` |
| Kırmızı Üçgen önce | ❌ senaryo üretilemedi |

## Başarısızlıklar

İki deneme de "üçgen önce" senaryosunu üretemedi.

**Deneme 1 — spawn noktası varyantı.** `PX4_GZ_MODEL_POSE="0,60,..."` ile araç
üçgenin kuzeyine spawn edildi. Rota çalıştı ama 9 dakikada **hiçbir şekil
tespit edilmedi**. Ham log doğrulaması: `p15tri_mission_T1/T2.log` boyunca
`[VISION] ... 0 tespit: []` tekrar ediyor.

**Deneme 2 — rota geometrisi.** Rota MAVSDK ile hedefleri doğudan dolanacak
şekilde değiştirildi (WP0 0K/60D → WP1 40K/60D → WP2 40K/0D üçgen → WP3
15K/0D altıgen). Görev tam başarıyla tamamlandı ama altıgen **yine** önce
tespit edildi.

## Kök neden

**Kesin.** Altıgen, rota başlamadan ÖNCE tespit ediliyor. `p15_mission_T1.log`
ham kanıtı:

```
23:58:34,332  [MISSION_START] Rota dogrulandi (4 item)
23:58:35,072  [VISION] bu karede 1 tespit: ['MAVI_ALTIGEN']   <-- tespit
23:58:37,335  [MISSION_START] Yuklu gorev baslatiliyor...     <-- rota HENUZ baslamamis
```

Home (0,0) ile altıgen (0,15) arası 15 m; 15 m irtifada kamera yer izi
yarıçapı ~18 m. Yani **altıgen kalkış noktasından zaten görünüyor.** Bu dünya
geometrisi ve bu home konumuyla altıgen HER ZAMAN önce tespit edilir.

## Uygulanan çözüm

**Yok — çözüm uygulanmadı.** Rota değiştirmek bu sorunu çözemez. Çözüm yalnızca
(a) home konumunu taşımak (GPS referansını bozuyor, Deneme 1'in başarısızlık
nedeni) veya (b) dünya modellerini taşımak (world/SDF, yetki dışı) ile mümkün.

## Doğrulama

Kod seviyesinde kapsandı: `tests/test_dynamic_mission_order.py` (10 test) her
iki sırayı da simetrik olarak sürüyor. SITL seviyesinde **kanıtlanmadı.**

Yarışma rotası deney sırasında geçici olarak değiştirildi, sonra geri yüklendi
ve dataman'den indirilerek doğrulandı (4 waypoint birebir aynı) —
`route_original.json` / `route_verify.json`.

## Önemli metrikler

- "Altıgen önce": 3/3 tam başarı
- "Üçgen önce": 0 başarılı üretim, 2 deneme
- Deneme 1: 9 dakika, 0 tespit
- Deneme 2: görev başarılı, sıra yine yanlış; tespit rotadan **~2 s önce**
- Home ↔ altıgen: 15 m; kamera yer izi yarıçapı @15 m irtifa: ~18 m

## İlgili commit

Yok — `.scripts/olds/v33/` untracked. Kayıt: `payload/KNOWN_ISSUES.md §7`.

## Sonraki adım

`KNOWN_ISSUES §7` **bilinçli açık risk olarak kalıyor** (operatör onayı,
2026-08-25). Kapatmak için world/SDF'te hedef konumlarını taşıma yetkisi
gerekir; bu ayrı bir karar.
