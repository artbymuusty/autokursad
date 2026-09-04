# Görev F2-a — çoklu koşum izleme (`ENABLE_ROUTE_REJOIN = True`)

**Amaç:** hedefin rota hattından **belirgin uzakta (>2 m)** olduğu **gerçek bir
düzeltme senaryosu**nun doğal olarak oluşmasını beklemek. Hedef konumları her
açılışta `generate_competition_area.py` tarafından rastgele üretiliyor, yani
er geç hattan uzak bir hedef çıkar. **Zorlamıyoruz.**

## Neden "0.38 m" bir test değildi

`GPS_POSITION_CONVERGENCE_TOLERANCE_M = 2.0`. Ofset bunun altındaysa
`goto_global_position_and_wait()` ilk kontrolde `True` döner ve **hiç manevra
yapılmaz** — rejoin fiilen no-op olur. Gerçek testin eşiği bu yüzden **2 m**.

## Sütunlar

| sütun | anlamı |
|---|---|
| **ofset** | rejoin tetiklenmeden önce aracın rota hattına yanal mesafesi (m). `>2 m` olan koşum **gerçek test** |
| **TIMED_OUT** | `ROUTE_REJOIN_TIMED_OUT` çıktı mı — çıkarsa ADR-009 endişesi somutlaşır, **derhal bildirilir** |
| **süre** | rejoin başına eklenen gerçek süre (s), 0–15 aralığında |
| **SKIPPED** | madde 2 guard'ının kaç kez devreye girdiği (Offboard'a girilmemişti) |
| **sonuç** | Görev 2 tamamlandı mı / Görev 3'e geçildi mi / son faz |
| **offb_fail** | koşumdaki `OFFBOARD_SWITCH_FAILED` sayısı |

## Koşumlar

| koşum | eksen | ofset (m) | TIMED_OUT | süre (s) | SKIPPED | sonuç | offb_fail | süre |
|---|---|---|---|---|---|---|---|---|
| 20260904T044615/01_competition_2way | lon | 0.38 | hayir | 0.00 | 0 | G2 ✓ / G3 ✓ / MISSION_FAILED | 0 | 312s |
| 20260904T050252/01_competition_2way | lon | **16.52** ⭐ | hayir | 3.97 | 0 | G2 ✓ / G3 ✓ | 0 | 436s |
| 20260904T051051/01_competition_2way | lon | **11.47** ⭐ | hayir | 3.42 | **3** | G2 ✗ / G3 ✗ | **3** | 212s |
| 20260904T051510/01_competition_2way | lon | **6.98, 15.98** ⭐ | hayir | 3.18, 3.89 | 0 | G2 ✗ / G3 ✗ | 1 | 287s |
| 20260904T052035/01_competition_2way | lon | **15.27** ⭐ | hayir | 3.89 | 0 | G2 ✓ / G3 ✓ | 0 | 436s |
| 20260904T050252/01_competition_2way | lon | 16.52 **GERCEK TEST** | hayir | 3.97 | 0 | G2 ✓ / G3 ✓ / RETURN_TO_CHECKPOINT | 0 | 436s |

---

## ⭐ GERÇEK DÜZELTME SENARYOSU YAKALANDI — `20260904T050252`

Beklenen senaryo **doğal olarak oluştu** (zorlanmadı):

```
05:03:46.614  ROUTE_AXIS_DETECTED   {fixed_axis: lon, lat_span: 0.001260, lon_span: 0.000193}
05:06:00.142  ROUTE_REJOIN_STARTED  {fixed_axis: lon, target_lat: 47.3980204, target_lon: 8.5462571}
              (mevcut: lat 47.3980204  lon 8.5460379)
05:06:04.111  ROUTE_REJOIN_DONE                                          <- 3.969 s
05:06:04.827  MISSION_ROUTE_RESUMED
```

| ölçüt | değer |
|---|---|
| **yanal ofset (düzeltme öncesi)** | **16.52 m** |
| seyahat ekseni (lat) değişimi | **0.0000000°** — tasarım gereği birebir korundu |
| **rejoin süresi** | **3.97 s** (`ROUTE_REJOIN_TIMEOUT_S = 15.0`'ın **%26**'sı) |
| ortalama düzeltme hızı | 4.16 m/s |
| `ROUTE_REJOIN_TIMED_OUT` | **hayır** |
| `ROUTE_REJOIN_SKIPPED` | 0 |
| `OFFBOARD_SWITCH_FAILED` | 0 |
| sonuç | Görev 2 ✓, Görev 3'e geçildi ✓ |

### Neden bu bir kanıt

- **16.52 m**, `GPS_POSITION_CONVERGENCE_TOLERANCE_M = 2.0`'ın **8 katı** —
  yani `goto_global_position_and_wait()` gerçekten manevra yaptı, önceki
  koşumdaki gibi "zaten yakındı" diye anında dönmedi.
- Referans olarak: F2'nin kök neden analizinde ölçülen kapsama kaybı
  **11.34 m**'lik ofsetten geliyordu. Buradaki **16.52 m** ondan da büyük.
- **Seyahat ekseni birebir korundu** (lat farkı 0.0): düzeltme gerçekten
  *yanal*, önceki bir noktaya dönüş değil — tasarım sözleşmesi tutuyor.

### ADR-009 endişesi hakkında

`ROUTE_REJOIN_TIMEOUT_S`'in yalnızca **%26**'sı kullanıldı ve `TIMED_OUT`
çıkmadı. 16.52 m gibi büyük bir düzeltme 4 saniyede tamamlandığına göre,
"rejoin resume zamanlamasını bozar" endişesi bu ölçümde **somutlaşmadı**.
Yine de tek gözlem; izlemeye devam.
| 20260904T051051/01_competition_2way | lon | 11.47 **GERCEK TEST** | hayir | 3.42 | 3 | G2 ✗ / G3 ✗ / MISSION_FAILED | 3 | 212s |
| 20260904T051510/01_competition_2way | lon | 6.98, 15.98 **GERCEK TEST** | hayir | 3.18, 3.89 | 0 | G2 ✗ / G3 ✗ / MISSION_FAILED | 1 | 287s |
| 20260904T052035/01_competition_2way | lon | 15.27 **GERCEK TEST** | hayir | 3.89 | 0 | G2 ✓ / G3 ✓ / RETURN_TO_CHECKPOINT | 0 | 436s |

---

# TOPLU RAPOR — 5 koşum, 6 rejoin olayı

## 1. Büyük-ofset dağılımı ve süre değişkenliği

**6 rejoin olayının 5'i >5 m** — yani "düzeltecek şey yoktu" sınıfı yalnızca
ilk koşumdu (0.38 m).

| ofset (m) | 0.38 | 6.98 | 11.47 | 15.27 | 15.98 | 16.52 |
|---|---|---|---|---|---|---|
| **süre (s)** | 0.00 | 3.18 | 3.42 | 3.89 | 3.89 | 3.97 |

**Süre şaşırtıcı derecede kararlı: 3.18 – 3.97 s, yayılım yalnızca 0.79 s.**

Dikkat çekici olan: **ofset 2.4 kat artarken (6.98 → 16.52 m) süre yalnızca
1.25 kat artıyor.** Yani süre mesafeye zayıf bağlı — sabit bir maliyet
(ivmelenme/yavaşlama, `MISSION_ALTITUDE_M`'ye tırmanış, yakınsama kontrolü)
baskın, yanal yol değil. Pratik sonucu: **daha büyük ofsetler orantılı olarak
daha pahalı değil.**

## 2. `ROUTE_REJOIN_TIMED_OUT` — **5 koşumun hiçbirinde, 6 olayın hiçbirinde**

`ROUTE_REJOIN_TIMEOUT_S = 15.0`'a karşı en kötü gözlem **3.97 s = %26**.
ADR-009'un "resume zamanlamasına etkisi ölçülmedi" endişesi **6 gözlemde de
somutlaşmadı**. En büyük ofset (16.52 m) bile bütçenin dörtte birini kullandı.

## 3. Görev 2/3 tamamlanma — örneklem ne diyor, ne demiyor

| koşum | offb_fail | SEARCH_COMPLETE | ilk başarısızlık nedeni |
|---|---|---|---|
| 044615 | 0 | ✓ | `gorev3_pickup_failed` |
| 050252 | 0 | ✓ | `gorev3_pickup_failed` |
| 051051 | **3** | ✗ | `search_incomplete_mission_finished` |
| 051510 | 1 | ✗ | `search_incomplete_mission_finished` |
| 052035 | 0 | ✓ | — (Görev 3'e geçti) |

**Görev 2 tamamlanma: 3/5.** İki başarısızlığın **ikisi de** Offboard geçiş
hatasına bağlı (`offb_fail` 3 ve 1), rejoin'e değil. Rejoin'in devre dışı
kaldığı koşumlarda da aynı sonuç çıkardı.

**Dürüst hüküm: örneklem şu an yalnızca "BOZMADI" diyebilecek kadar.**
Bayrak-kapalı karşılaştırılabilir örneklem 2–3 koşum (F2-b1 karşılaştırması +
`mission_0600f0558de3`), üstelik aradaki koşumlarda E4a, E4e ve F1 guard'ı da
değişti. **Nedensel bir tamamlanma-oranı karşılaştırması yapılamaz** ve
yapmıyorum.

## 4. BONUS — madde 2 guard'ının CANLI kanıtı (`051051`)

Madde 4 raporunda "canlıda kanıtlanmadı" diye işaretlediğim şey bu koşumda
kanıtlandı:

```
05:12:05  OFFBOARD_SWITCH_FAILED   {modes_seen: [HOLD, MISSION]}
05:12:05  OFFBOARD_FAILURE_NOTED   {MAVI_ALTIGEN, offboard_failures: 1}
05:12:05  ROUTE_REJOIN_SKIPPED     {reason: offboard_never_engaged}    <-- GUARD
05:12:19  OFFBOARD_SWITCH_FAILED   -> ROUTE_REJOIN_SKIPPED             <-- GUARD
05:12:48  OFFBOARD_SWITCH_CONFIRMED
05:14:18  ROUTE_REJOIN_STARTED -> DONE (3.42 s)                        <-- NORMAL YOL
05:14:34  OFFBOARD_SWITCH_FAILED   -> ROUTE_REJOIN_SKIPPED             <-- GUARD
```

- **3 Offboard hatasının 3'ünde de** rejoin kesildi
- **Başarılı geçişte kesilmedi**, rejoin normal çalıştı
- Kazanılan: **3 × 15 s = 45 s** boşa bekleme, 212 s'lik bir koşumda

Madde 2'nin gerekçesi (90 s riski) sadece teorik değilmiş — bir koşumda
yarısı gerçekleşti ve guard onu kesti.

## 5. Kalan açık nokta

`OFFBOARD_PURSUIT_ABANDONED` **hiç tetiklenmedi**: 051051'de hatalar şekiller
arasına dağıldı (MAVI 2, KIRMIZI 1), N=3 eşiğine tek şekilde ulaşılmadı.
F1 guard'ının **terk etme** dalı hâlâ yalnızca N=1 doğrulama koşumunda
gözlendi.
