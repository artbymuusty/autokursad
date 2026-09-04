# GÖREV I / D — Route rejoin teyidi

**Tarih:** 2026-09-04 · **Kod değişikliği: YOK** (yalnızca teyit, istendiği gibi)

---

## HÜKÜM: **çalışıyor, 10/10** ✅

Yeni koşum yapmadım — bu oturumun **10 bağımsız koşumu zaten
`competition_2way` rotasını** kullanıyor (`MISSION_ROUTE_ITEMS` = 10 item,
2way planıyla birebir). Veri hazırdı.

| koşum | rota | Offboard geçiş | `OFFBOARD_SWITCH_FAILED` | `REJOIN_STARTED` | `REJOIN_DONE` | `ROUTE_RESUMED` |
|---|---|---|---|---|---|---|
| d1, d2, d3 | 10 item | 2 | **0** | 1 | 1 | 1 |
| f1 … f5 | 10 item | 2 | **0** | 1 | 1 | 1 |
| g12a, g12b | 10 item | 2 | **0** | 1 | 1 | 1 |
| **toplam** | | **20** | **0** | **10** | **10** | **10** |

**10/10 koşumda sıra eksiksiz:** `ROUTE_AXIS_DETECTED` →
`ROUTE_REJOIN_STARTED` → `ROUTE_REJOIN_DONE` → `MISSION_ROUTE_RESUMED`.

`ROUTE_REJOIN_SKIPPED` = **0** — F1-çakışma guard'ının devreye girmesi
gerekmedi, çünkü K6 sayesinde `OFFBOARD_SWITCH_FAILED` = 0.

## Eksen tespiti doğru çalışıyor

```
ROUTE_AXIS_DETECTED  {"fixed_axis": "lon",
                      "lat_span_deg": 0.001260,   (~140 m)
                      "lon_span_deg": 0.000193}   (~14.5 m)
ROUTE_REJOIN_STARTED {"fixed_axis": "lon", "target_lat": 47.3981001, ...}
ROUTE_REJOIN_DONE    {"fixed_axis": "lon"}
```

Sabit eksen `lon` olarak doğru bulunuyor — 2way'in şeritleri Y (kuzey)
boyunca uzanıyor, X (doğu) sabit. Araç merkezlemeden döndüğünde **kesilen
şeridin kendi boylamına** geri götürülüyor, sonra rota devam ediyor.

## Neden koşum başına 1 rejoin, 2 Offboard geçişi var

İkinci hedef merkezlendiğinde `SEARCH COMPLETE` geliyor ve Mission
**kalıcı olarak** sonlanıyor (Offboard tek yetkili). Yani ikinci geçişten
sonra dönülecek bir rota yok. **Beklenen davranış**, eksiklik değil.

## C maddesindeki yeni desenle uyumlu mu

**Yapısal olarak evet, ama koşulla.** Eksen tespiti geometriye bağlı
değil — iki span'i karşılaştırıp büyüğünü "serbest", küçüğünü "sabit"
seçiyor. C'nin önerdiği desenlerde:

| desen | lat_span | lon_span | `fixed_axis` doğru bulunur mu |
|---|---|---|---|
| bugün (2 şerit, ±7.25) | ~140 m | 14.5 m | ✅ lon |
| C2-(i) 2 şerit, ±5 | ~140 m | 10 m | ✅ lon |
| C2-(ii) 3 şerit, −10/0/+10 | ~140 m | 20 m | ✅ lon |

Üçünde de `lat_span ≫ lon_span`, yani mantık aynı kalır.

⚠️ **Ama bu bir tahmin değil, bir koşul:** şeritler **Y boyunca**
kaldığı sürece geçerli. Desen 90° döndürülür (şeritler X boyunca) ya da
lat/lon span'leri birbirine yaklaşırsa eksen tespiti belirsizleşir.
C kararı verildikten sonra **yeni rotayla bir canlı koşum** yapılmalı;
şu an C engelli olduğu için o rota henüz yok.

## Kapsam

- 10 koşum, hepsi mevcut 2way geometrisi. **F2-a'ya dokunulmadı.**
- Yeni desenle uyum §son'da **analitik**; ölçülmedi, çünkü desen yok.
- Rejoin'in *doğruluğu* (aracın gerçekten kesilen hatta dönmesi)
  `ROUTE_REJOIN_DONE` + `MISSION_ROUTE_RESUMED` ile kayıtlı; ayrıca
  F2-a turunda 3/3 canlı doğrulanmıştı.
