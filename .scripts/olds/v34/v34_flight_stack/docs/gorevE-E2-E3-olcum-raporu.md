# Görev E — E2 (teşhis) · E1 (düzeltme) · E3 (ölçüm)

**Tarih:** 2026-09-03 · **Veri:** 3 canlı SITL koşumu + 1 önceki koşum = **8 bırakma**
Yeni araç: `tools/observe_payload_pose.py` — gz-transport poz akışını görevden
**bağımsız** olarak ~150 Hz dinleyip duvar saatiyle damgalar. Salt-okunur.

---

## E2 — HÜKÜM: ne zamanlama hatası, ne erken ayrılma

### 1. `PAYLOAD_FINAL_POSE` hangi yolda, ne zaman yazılıyor

`core/mission/payload_release.py:417` → `_log_payload_final_pose()`:

```
PAYLOAD_RELEASED  →  await asyncio.sleep(PAYLOAD_FINAL_POSE_DELAY_S = 2.0)
                  →  actuator.get_released_payload_pose()
                  →  pose_monitor.get("payload_<renk>")     # TEK önbellek okuması
```

`GzPoseMonitor.get()` **son görülen** pozu döndürür ve `age_s()` **hiç kontrol
edilmiyor** — yani kod, bayat bir pozu bayat olduğunu bilmeden raporlayabilir.
Mekanizma olarak açık bir boşluk; ama ölçüm bunun pratikte gerçekleşmediğini
gösterdi (aşağı bkz.).

### 2. Poz taze mi, bayat mı — ÖLÇÜLDÜ

Bağımsız izle, `PAYLOAD_FINAL_POSE`'un yazıldığı anda karşılaştırma:

| koşum · bırakma | görevin bildirdiği | bağımsız iz | **fark** | önbellek yaşı |
|---|---|---|---|---|
| k-1 · MAVI_ALTIGEN | (−6.766, 86.718) | (−6.766, 86.718) | **0.0 cm** | 4.5 ms |
| k-2 · MAVI_ALTIGEN | (9.309, 37.214) | (9.309, 37.214) | **0.0 cm** | 5.3 ms |
| k-2 · KIRMIZI_UCGEN | (8.962, 71.189) | (8.963, 71.189) | **0.1 cm** | 2.8 ms |
| k-1 · KIRMIZI_UCGEN | (4.713, 13.322) | (4.713, 13.320) | **0.2 cm** | (28 s sonra da aynı) |

**Okuma doğru ve taze.** Zamanlama hatası YOK.

### 3. Erken ayrılma — DIŞLANDI

`MOUNT_VECTOR_MEASURED`, servo komutunun tam anında yükün araca göre yerini
ölçüyor. Dört bırakmanın dördünde de **3.4–3.6 cm** çıktı; yani yük servo
anına kadar araca bağlıydı. Yük erken ayrılmış olsaydı bu sayı metrelerce
olurdu. Ayrıca izde yük, ayrılana kadar aracın z'siyle birlikte hareket
ediyor (z≈0.68 → 0.03).

Bırakma sonrası yükün yer değiştirmesi (tam kapsanan üç bırakma):
**0.036 m, 0.044 m, 0.207 m.** Yük dik düşüp duruyor.

### 4. Diğer bırakma da aynı mı — EVET, sistemik değil

Her iki hedef tipi için de aynı sonuç. Sistemik bir kusur yok.

### 5. Peki "33.5 m" nereden çıktı — BENİM HATAM

FAZ 1 raporundaki tutarsızlık gerçek değil: `PAYLOAD_FINAL_POSE`'u
`mission_ef9d617d8725.jsonl`'den (01:26–01:29 koşumu), uçuş telemetrisini ise
`mission_0b9d78556168.jsonl`'den (01:30–01:35 koşumu) okumuşum. İki **ayrı
koşumu** karşılaştırmışım. Doğru eşleştirmede aynı bırakma **0.157 m**
tutarlı. D2 diye bir kusur yok; kayıt için düzeltiyorum.

> Tam kapsanmayan tek veri: k-1'in 1. bırakmasında yük, ayrılma anındaki araç
> konumundan 2.9 m uzağa yerleşmiş. O bırakma gözlemci başlamadan önce olduğu
> için yüksek hızlı izle kapsanmıyor ve **açıklanmadı**. Tam izlenen üç
> bırakmada karşılığı yok (≤0.21 m). Olduğu gibi bırakıyorum.

---

## E1 — TARGET_CENTERS artık gerçek kaynaktan okunuyor

**Kusur kesindi:** `gz_payload_actuator.py` içinde sabit kodlu
`{"MAVI_ALTIGEN": (0.0, 15.0), "KIRMIZI_UCGEN": (0.0, 40.0)}`, oysa
`safe_sitl_launcher.sh` adım 4a her açılışta `default.sdf`'i **rastgele
konumlarla yeniden üretiyor**.

**Yapılan:** `read_target_centers()` — koşum anında dünya SDF'inin
`KURSAD_COMPETITION_AREA_START/END` bloğunu ayrıştırır. Yedek sabit **yok**:
dünya okunamazsa `landing_reference()` None döner ve çekirdek, belgelenmiş
"yerden yüksek mi" kontrolüne düşer. *Eksik puan dürüst, bayat puan değil.*

Ek olarak `core/mission/gorev3_redrop.py` aynı sabiti `gz_system`'den ithal
ediyordu (hem kaldırılan sabit, hem katman ihlali) — `landing_reference()`
üzerinden geçirildi.

**Canlı doğrulama (koşum-3):**
```
[TARGET_CENTERS] default dunyasindan okundu: KIRMIZI_UCGEN=(1.257, 39.363),
                 MAVI_ALTIGEN=(10.272, 12.305), ...
[PAYLOAD_FINAL_POSE] KIRMIZI_UCGEN: x=1.052 y=39.665 merkeze 36.5 cm (HEDEFTE)
```
Elle doğrulandı: √((1.052−1.257)² + (39.665−39.363)²) = 0.365 m = 36.5 cm ✓
Bu, sistemin kendi telemetrisinin bir bırakmayı **ilk kez doğru puanlaması**.

**Testler:** 469 → **474 geçti, 1 atlandı.** Sabitleri çakan test, dünyayı
okuduğunu doğrulayan 6 teste dönüştü (fixture dünya, işaret bloğu dışını
saymama, okunamayan dünyada susma, tek kez okuma, sabitin geri gelmesine
karşı regresyon nöbeti).

---

## E3 — Gerçek isabet dağılımı (8 bırakma)

| koşum | şekil | **isabet** | mount_translate | şeklin üzerinde? |
|---|---|---|---|---|
| önceki | KIRMIZI_UCGEN | 0.152 m | 4.1 cm yakınsadı | **EVET** |
| koşum-3 | KIRMIZI_UCGEN | 0.365 m | 4.1 cm yakınsadı | hayır (kıl payı) |
| koşum-1 | MAVI_ALTIGEN | 0.474 m | 4.7 cm yakınsadı | **EVET** |
| koşum-2 | MAVI_ALTIGEN | 0.885 m | 4.2 cm yakınsadı | hayır (kıl payı) |
| koşum-2 | KIRMIZI_UCGEN | 2.121 m | 108.7 cm SÜRE DOLDU | hayır |
| koşum-1 | KIRMIZI_UCGEN | 4.111 m | 107.8 cm SÜRE DOLDU | hayır |
| önceki | MAVI_ALTIGEN | 4.359 m | 62.6 cm SÜRE DOLDU | hayır |
| koşum-3 | MAVI_ALTIGEN | 5.305 m | 45.6 cm SÜRE DOLDU | hayır |

**Dağılım:** min 0.152 · p50 1.503 · p95/max 5.305 m
**Yakınsayan (n=4):** min 0.152 · p50 0.419 · **max 0.885**
**Süre dolan (n=4):** **min 2.121** · p50 4.235 · max 5.305

### Bulgu: `MOUNT_TRANSLATE` sonucu isabeti TAM AYIRIYOR

8/8, örtüşme sıfır. Yakınsayan her bırakma 1 m'nin altında, süre dolan her
bırakma 2 m'nin üstünde. Bu, "yükler merkeze bırakılmıyor" belirtisinin
**tek başına baskın nedeni**.

Neden önemli: `AIM_OFFSET_APPLIED`, sekiz bırakmanın hepsinde yalnızca
**0.04 m**'lik bir öteleme istiyor. Yani `_mount_translate` 4 cm için
çağrılıyor ama 8 s bütçesini tüketip 45–109 cm uzakta bitiriyor — araç
hedefe yaklaşmıyor, **uzaklaşıyor** (koşum-1: üçgene 0.53 m iken başlıyor,
1.77 m'de bırakıyor). Sebep `_mount_translate`'in kendisinde değil, uçtuğu
`held` noktasında: `held` = **dondurulmuş görüş kestirimi** + montaj ofseti.
Kestirim şeklin merkezinden metrelerce uzaktaysa, araç sadık şekilde yanlış
yere gidiyor.

### `PAYLOAD_ON_TARGET_RADIUS_M = 0.5` değerlendirmesi — ÖNERİ, uygulanmadı

SDF geometrisi (ölçüldü, varsayılmadı):

| şekil | ölçü | çevrel yarıçap | **iç teğet** | yük (r=0.15) tam üzerinde |
|---|---|---|---|---|
| blue_hexagon | mesh 1 m × ölçek 2 | 1.000 m | **0.866 m** | ≤ 0.716 m |
| red_triangle | kenar 1.0 m | 0.577 m | **0.289 m** | ≤ 0.139 m |

Tek bir 0.5 m yarıçapı iki şekle birden **uyamaz**: üçgen için fazla gevşek
(0.5 m'de yük üçgenin dışında), altıgen için gereksiz dar.

**Önerim (kararı siz verin):**

1. **Yarıçapı GEVŞETMEYİN.** Dağılımın iki kutuplu olması bir eşik sorunu
   değil; 0.5'i büyütmek yalnızca 2–5 m'lik ıskaları "başarı" yazdırır.
2. **Şekil başına eşik**, SDF geometrisinden türetilsin (altıgen 0.716,
   üçgen 0.139 — yükün tamamen şeklin üzerinde olması ölçütüyle). Bu, E1'in
   yaptığı işin aynısıdır: sayıyı yazmak yerine kaynaktan okumak.
3. **Asıl iş kalemi (E4 önerisi):** `_mount_translate`'in neden 4 cm için
   8 s harcayıp uzaklaştığını çöz — yani dondurulmuş görüş kestiriminin
   doğruluğunu. Ölçüm bunun 8/8 belirleyici olduğunu söylüyor; bu düzelirse
   dağılımın tamamı 0.885 m'nin altına iner ve eşik tartışması anlamlı hale
   gelir. **Bu Görev C/D'ye dokunmaz** ama merkezleme/kestirim yolunu
   değiştirir, o yüzden ayrı ve onaylı bir görev olmalı.

Kısıt uyumu: Görev C/D düzeltmeleri değiştirilmedi, `motion_fsm.py`'a
dokunulmadı, push yapılmadı.
