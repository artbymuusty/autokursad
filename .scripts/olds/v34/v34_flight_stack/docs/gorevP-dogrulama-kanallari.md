# GÖREV P — Doğrulama kanalları ve "doğrulanamayan durumda ALINMADI" ilkesi

**Tarih:** 2026-09-05 · Kaynaklar: `core/mission/gorev3_pickup.py` (`_verify_lift`),
`gz_system/gz_payload_actuator.py`, `real_system/real_payload_actuator.py`

---

## 1 · Hangi kanal nerede var?

| kanal | ne söyler | SITL | **GERÇEK DONANIM** |
|---|---|---|---|
| `SERVO3_GRIP_ENGAGED` olayı | servo3 **tetiklendi** | ✅ | ✅ (komut gönderildi) |
| `/hook/state` onayı → `is_hook_attached()` | fixed joint **kuruldu** | ✅ | ❌ **YOK** — simülasyon gerçeği |
| `payload_altitude_m()` yer-gerçeği | yük araçla **yükseldi** | ✅ | ❌ **YOK** — Gazebo poz akışı |
| Görüntü işleme (2 m'ye çık, yük hâlâ şeklin üstünde mi) | yük **yerinde değil** | ✅ | ✅ **tek gerçek kanal** |
| kavrama kolu geri bildirimi (mikroşalter / akım / Hall) | kollar **kapandı ve tutuyor** | ❌ | ❌ **tasarımda yok** |

**Açık boşluk:** gerçek donanımda servo3'ün fiziksel kavramayı doğrulayan
**hiçbir** sensörü yok. Hobi servoları pozisyon komutu alır, pozisyon
raporlamaz. SITL'de bu boşluğu `HookAttachSystem`'in fixed joint'i
kapatıyor — ama o bir **simülasyon gerçeğidir**, sahada karşılığı yoktur.

> **Sonuç: gerçek donanımda tek doğrulama kaynağı GÖRÜNTÜ İŞLEMEDİR.**
> `real_payload_actuator.py`'ye bu, TODO[DONANIM] olarak işlendi.

---

## 2 · İlke kodda nerede uygulanıyor

`_verify_lift()` içinde **iki ayrı bayrak**, biri diğerinin yerine geçmez:

```python
grip_engaged    = True                          # servo3 tetiklendi + /hook/state onayladi
                                                #   -> "DENEME YAPILDI", "BASARILI" DEGIL
lift_ok         = lifted_m is not None and lifted_m >= PICKUP_LIFT_CONFIRM_M
pickup_verified = bool(attached and lift_ok)    # BAGIMSIZ kanit

if not pickup_verified:
    return False                                # mission ASLA "alindi" demez
```

### Düzeltilen kusur (bu turda bulundu)

Önceki kod:
```python
if lifted_m is not None and lifted_m < PICKUP_LIFT_CONFIRM_M:
    return False
return True
```
`lifted_m` **ölçülemediğinde** (`None`) kontrol atlanıyor ve fonksiyon
`True` dönüyordu — yani *"ölçemedim, o hâlde almışımdır."* Bu tam olarak
yasaklanan iyimser varsayım. Artık **kanıt yokluğu başarısızlıktır** ve log
bunu açıkça yazıyor: *"Yuk irtifasi OLCULEMEDI -- kaldirma DOGRULANAMADI.
GUVENLI VARSAYIM: yuk ALINMADI."*

---

## 3 · "Servo3 tetiklendi ama gerçekte tutmadı" senaryosu simüle edilebiliyor mu?

**Hayır — güvenilir şekilde değil.** SITL'de kavrama, `/hook/attach` ile
kurulan bir fixed joint; joint kurulduysa yük *tanım gereği* tutulur.
"Komut gitti ama mekanik tutmadı" ara durumu bu modelde **yok**.

Bu yüzden mimari, o senaryonun **var olduğunu varsayarak** kuruldu:
`SERVO3_GRIP_ENGAGED` tek başına başarı saymıyor; hükmü **Adım 9-10**
(2 m'ye tırmanış + görüntü doğrulaması + yük yüksekliği) veriyor.

⚠️ Dürüst sınır: SITL'de `is_hook_attached()` de `pickup_verified`'ın bir
koşulu. O kanal sahada olmayacağı için, gerçek donanımda `pickup_verified`
**yalnızca görüntü işlemeye** dayanacak — ve o geçiş yapılırken bu dosyadaki
tablo yeniden gözden geçirilmeli.

---

## 4 · Servo3 zamanlaması — sıra ve çakışma

`MAGNET_LOCKED` → `SERVO3_GRIP_ENGAGED` arasındaki **tüm** adımlar:

| # | adım | süre | nerede |
|---|---|---|---|
| 1 | dwell (`MAGNET_DWELL_S`) dolar | 0.60 s | `SeatingEvaluator` |
| 2 | **kilit sonrası doğrulama penceresi** (`GOREV3_SERVO3_POST_LOCK_DELAY_S`) — kapılar örneklenmeye **devam eder**, bozulursa kavrama YAPILMAZ | **2.00 s** | `_await_seating` |
| 3 | `MAGNET_LOCKED` loglanır, `_await_seating` döner | ~0 | |
| 4 | `SERVO3 KAVRAMA` → `/hook/attach` publish + `/hook/state` onayı | ölçülen ~1.7 s (tavan `HOOK_STATE_TIMEOUT_S`=5.0) | aktüatör |
| 5 | `SERVO3_GRIP_ENGAGED` | — | |
| 6 | kilit sonrası sönümleme (`HOOK_SETTLE_S`) | 3.00 s — **artık bütçe DIŞINDA** | `_verify_lift` başı |
| 7 | 2 m doğrulama tırmanışı + tespit + kontroller | ~15 s — **bütçe dışında** | `_verify_lift` |

**Çakışma yok, sıralılar:** adım 2 kilitten *önce*, adım 6 servo3'ten
*sonra*. İkisi farklı amaca hizmet ediyor (biri kilidin kararlılığını
doğruluyor, diğeri ipin salınımını söndürüyor) ve artık farklı bütçelerde.

**Her denemede çalışır:** gecikmenin tek koşulu sabitin pozitif olması;
deneme numarasına bağlı değil ve `_await_seating` alma döngüsünün her
turunda çağrılıyor. Teste bağlandı (`test_gorevP_dogrulama.py`).

**60 s bütçesi:** kilit yolu artık dwell 0.6 + doğrulama 2.0 + attach ~1.7
= **~4.3 s**. Önceki hâli buna 3.0 s sönümleme ekliyordu (~7.3 s) ve üç
koşumda da bütçe tam orada kesiyordu. 3.0 s dışarı alınınca o risk kalktı.
