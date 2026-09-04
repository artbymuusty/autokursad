# Görev F2-a madde 4 — `ENABLE_ROUTE_REJOIN` açıldı: canlı ölçüm

**Tarih:** 2026-09-04 · **Koşum:** `demo/runs/20260904T044615/01_competition_2way/`
**Rota:** `competition_2way` (10 item) · **Süre:** 312 s · Dashboard açıktı.

Bu, `ENABLE_ROUTE_REJOIN` kod yolunun **production'da ilk kez** çalıştığı koşum.

---

## 1. `ROUTE_AXIS_DETECTED` — DOĞRU

```
sabit eksen = lon
lat_span = 0.001260 deg (~140.3 m)
lon_span = 0.000193 deg (~14.5 m)      oran 6.5x
```
2way geometrisiyle **birebir tutarlı**: rota kuzey-güney uzanıyor (140 m),
şeritler ±`TRACK_HALF`=7.25 m yani 14.5 m arayla. Sabit eksen doğru şekilde
**lon** bulundu; rota koordinatlarından türetildi, varsayılmadı.

## 2. `ROUTE_REJOIN_STARTED/DONE` — sıra ve süre

```
04:48:43.316  ROUTE_REJOIN_STARTED  {fixed_axis: lon, target_lat: 47.3981538, target_lon: 8.5462563}
04:48:43.316  ROUTE_REJOIN_DONE     {fixed_axis: lon}                    (+0.00 s)
```
Bir kez tetiklendi (koşumda tek resume vardı), `TIMED_OUT` **yok**.

## 3. Yanal ofset — **DİKKAT: doğrudan karşılaştırma YANILTICI**

```
sabit eksen (lon) farkı  : 0.38 m
seyahat ekseni (lat) farkı: 0.000 m     <- tasarım gereği korundu
```

| | önceki ölçüm (`mission_0600f0558de3`) | bu koşum |
|---|---|---|
| MISSION'a dönüşteki yanal ofset | **11.34 m** | **0.38 m** |

**Bu bir iyileşme kanıtı DEĞİL.** İki koşumun başlangıç koşulları farklı:
ofset, hedefin rota hattına göre nerede olduğuna bağlı. Önceki koşumda hedef
hattın 11 m uzağındaydı; bu koşumda hedef neredeyse hattın üzerindeydi, yani
**rejoin'in düzeltecek bir şeyi yoktu**. Aynı şey rejoin olmasa da olurdu.

## 4. Resume başına eklenen süre — **0.00 s**

`ROUTE_REJOIN_TIMEOUT_S = 15.0` aralığının **en altında**.
Sebebi belli: 0.38 m'lik ofset `GPS_POSITION_CONVERGENCE_TOLERANCE_M = 2.0`'ın
**içinde**, dolayısıyla `goto_global_position_and_wait()` daha ilk kontrolde
`True` döndü ve hiç manevra yapılmadı.

> **ADR-009 endişesi için iyi haber ama eksik kanıt:** düzeltecek bir şey
> yokken maliyet **sıfır**. Gerçek bir 11 m'lik düzeltmenin ne kadar süreceği
> bu koşumda **ölçülmedi**.

## 5. `ROUTE_REJOIN_SKIPPED` — **0 adet** (beklenen)

Madde 2 guard'ı yanlış tetiklenmedi. Koşumda `OFFBOARD_SWITCH_FAILED = 0`
olduğu için guard'ın **kesmesi gereken** hâl de hiç oluşmadı — yani guard'ın
doğru çalıştığı bu koşumda **ne doğrulandı ne çürütüldü**, yalnızca yanlış
pozitif vermediği görüldü. (Doğru davranışı 12 birim testinde çakılı.)

## 6. Hata durumu ve görev sonucu

- **Traceback: 0**
- **CRITICAL: 3** — üçü de Görev 3 pickup başarısızlık zinciri
  (`GOREV3_PHASE_FAILED{pickup}` → `MISSION_FAILED` → `LANDING`).
  **Rejoin ile ilgisi yok**, önceki koşumlarda da vardı.
- `OFFBOARD_SWITCH_FAILED = 0` · resume = 1 · `SEARCH_COMPLETE` = 1 ·
  `PAYLOAD_RELEASED` = 2
- **Görev 2 tam tamamlandı**; görev Görev 3'te düştü.

---

## Hüküm

**Beklenmedik hiçbir şey çıkmadı.** Altı maddenin hepsi tasarımla uyumlu:
eksen doğru, rejoin çalıştı, guard yanlış tetiklenmedi, hata yok, Görev 2
tamamlandı, maliyet sıfır.

**Ama koşum mekanizmayı ZORLAMADI.** Kanıtlanan ve kanıtlanmayan:

| | durum |
|---|---|
| Eksen tespiti doğru çalışıyor | **kanıtlandı** |
| Kod yolu hatasız çalışıyor (ilk kez) | **kanıtlandı** |
| Guard yanlış pozitif vermiyor | **kanıtlandı** |
| Düzeltecek şey yokken maliyet ~0 | **kanıtlandı** |
| Gerçek bir yanal ofset (>2 m) düzeltiliyor | **KANITLANMADI** |
| Gerçek düzeltmenin süresi / ADR-009 etkisi | **KANITLANMADI** |
| Guard'ın F1 hâlinde kesmesi (canlıda) | **KANITLANMADI** (birim testte var) |

## Öneri — bayrak `True` kalsın mı

**Evet, kalsın.** Gerekçe:
- Kod yolu ilk çalıştırmada temiz geçti, hata üretmedi
- Düzeltecek şey yokken maliyeti **sıfır** — yani "açık bırakmanın" bedeli
  ölçülen koşumda yok
- Madde 2 guard'ı F1 çakışmasının 90 s'lik riskini zaten kesiyor
- 12 birim testi davranışı çakıyor

**Ama iki uyarıyla:**
1. **Asıl faydası hâlâ ölçülmedi.** Hedefin rota hattından uzak olduğu bir
   koşum gerekiyor. Bu doğal olarak oluşur (hedef konumları her açılışta
   rastgele) — birkaç koşum daha yapılırsa er geç gözlenir. Zorlamayı
   önermiyorum.
2. **`ROUTE_REJOIN_TIMED_OUT` izlenmeli.** Gerçek bir düzeltme gerektiğinde
   15 s'i aşarsa, ADR-009'un resume aralığı endişesi somutlaşır. Şu an
   izlenebilir: olay yayınlanıyor.

Görev C/D/E4e'ye, `motion_fsm.py`'a, F1 düzeltmesine dokunulmadı.
