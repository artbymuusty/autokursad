# Görev F1-KÖK — K6 bekleme süresi taraması (FAZ 1)

**Tarih:** 2026-09-04 · **Görev koduna dokunulmadı** (yalnızca yeni tanı aracı).
**Araç:** `tools/offboard_gap_sweep.py` — `scratchpad`'den kalıcı hâle getirildi.
**Ölçüm:** tek SITL oturumu, **175 deneme**, 7 bekleme değeri.

## Sonuçlar

| bekleme | başarısız | oran | `start()` ms min/ortanca/max | başarısızların süreleri |
|---|---|---|---|---|
| **0 ms** | **5 / 25** | **%20.0** | 2.9 / 7.6 / 20.1 | [4.5, 3.5, 3.5, **2.9**, 7.6] |
| 20 ms | 0 / 25 | **%0** | 4.4 / 11.1 / 21.0 | — |
| 30 ms | 0 / 25 | **%0** | 4.8 / 13.1 / 21.9 | — |
| 40 ms | 0 / 25 | **%0** | 5.7 / 15.2 / 24.4 | — |
| 50 ms | 0 / 25 | **%0** | 5.2 / 16.4 / 25.4 | — |
| 100 ms | 0 / 25 | **%0** | 6.3 / 14.2 / 22.3 | — |
| 200 ms | 0 / 25 | **%0** | 6.0 / 11.8 / 19.9 | — |

Taban (%20.0), külliyat ortalaması **%24.4** ve K3'ün **%41.7**'siyle aynı
mertebede — ölçüm düzeneği temsili.

## Alt sınıra ne kadar inilebiliyor

**Diz noktası 0 ile 20 ms arasında.** 20 ms zaten sıfır veriyor ve ölçülen
MAVLink round-trip'i (~11–14 ms) ile aynı mertebede — yani çakışma penceresi
**tam olarak bir round-trip kadar**, teşhisin öngördüğü gibi.

**İstatistiksel dürüstlük:**
- Tek bekleme değeri için `0/25` → %95 üst sınır **~%12** (rule of three).
  Yani "20 ms sıfırlıyor" tek başına **kanıtlanmış değil**.
- Ama **≥20 ms olan altı bekleme birleştiğinde `0/150`** → %95 üst sınır
  **~%2.0**. Taban %20–24 olduğuna göre bu, **en az 10 kat** düşüş demek ve
  istatistiksel olarak sağlam.
- Tabanın kendisi de doğrulandı: 20 ms'de hâlâ %20 olsaydı 25 denemede sıfır
  hata görme olasılığı `0.8²⁵ ≈ %0.4`.

**"Sahte başarı" imzası da kayboldu:** 0 ms'de başarısızlıkların süresi
2.9–7.6 ms (pause ACK'inin kalan yolu). Bekleme konan **150 denemenin
hiçbirinde** 4.4 ms'nin altına inen bir `start()` yok — yani her denemede
komut fiilen gönderiliyor.

## Öneri: **50 ms**

| aday | artı | eksi |
|---|---|---|
| 20 ms | En ucuz | Ölçülen round-trip'in (11–14 ms) sadece ~1.5 katı; **test edilen en düşük değer**, altında pay yok |
| **50 ms** | Round-trip'in **~4 katı**, en düşük güvenli değerin **2.5 katı**. Takip başına maliyet ihmal edilebilir | — |
| 100–200 ms | Daha çok pay | Ek fayda **ölçülmedi** (üçü de %0); boşuna süre |

**Maliyet:** görev başına 2–4 takip × 50 ms = **0.1–0.2 s**, 600 s'lik bütçeye
karşı. Ölçülemez düzeyde.

50 ms'yi seçmemin sebebi 20 ms'nin yanlış olması değil; **20 ms taranan en alt
değer** ve altında ölçülmüş pay yok. 50 ms, round-trip dalgalanmasına
(max gözlenen `start()` 25.4 ms) karşı da rahat pay bırakıyor.

## FAZ 2 için öneri — K1 (retry) EKLENMESİN

**K6 tek başına yeterli görünüyor** ve K1'i eklememeyi öneriyorum:

1. K6 **kök nedeni kapatıyor**; K1 ise yarışı bekleyerek aşan dolaylı bir
   çözüm. Kök neden kapalıyken K1'in tetiklenmesi beklenmez.
2. K1, **ADR-004 `:499` ile doğrudan gerilimde** ("Offboard geçişi retry değil
   escalate"). Gerekmeyen bir katman için o gerilimi satın almaya değmez.
3. **Üçüncü savunma katmanı zaten var:** F1 guard'ı (N=3, Seçenek A).
   K6 birincil nedeni kapatıyor, guard artık nadiren tetiklenmeli — ama
   `0/150`'in %95 üst sınırı %2 olduğu için guard **kaldırılmamalı**.

Yani katman sırası: **K6 (önle) → F1 guard (sınırla)**. K1 aradaki üçüncü
katman olarak **gereksiz karmaşıklık**.

Karar sizin; ölçüm gerekirse K1 sonradan da eklenebilir.

## Araç hakkında

`tools/offboard_gap_sweep.py` kalıcı hâle getirildi (öneriniz kabul).
Görev koduna dokunmuyor, kendi MAVSDK bağlantısını kuruyor, çalışan bir SITL
istiyor. Kök neden ve "sahte başarı" imzası docstring'inde yazılı — ileride
biri aynı belirtiyi görürse aracı ve gerekçesini birlikte bulur.
