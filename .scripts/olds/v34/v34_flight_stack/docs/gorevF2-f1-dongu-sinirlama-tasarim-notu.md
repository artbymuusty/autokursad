# Görev F ② — F1 döngüsünü sınırlama: TASARIM NOTU (uygulanmadı)

**Tarih:** 2026-09-04 · Onay bekliyor.

---

## 0. Sorduğunuz asıl soru: yeni sınır mı, ölü koruma dirilişi mi?

> **Asıl öneri üç ölü korumayı DİRİLTMEK. Yeni bir sınır eklemek ikincil ve
> ancak diriliş yetmezse gerekli.**

İlk raporda "(2a) yeni ayrı sayaç" önce yazılmıştı; o sıralama **yanlıştı**.
Ölçüme dönünce neden şu:

| koruma | bugünkü durumu | dirilirse F1'e etkisi |
|---|---|---|
| `TargetValidator.reset()` (`target_validator.py:85-94`) | `core/` içinde **hiç çağrılmıyor**; `_consecutive_counts` kaçan karede bile azalmıyor | Şekil, başarısız takipten sonra **yeniden nitelenmek zorunda** kalır. Ölçülen 101 ms → en az `HSV_STREAK_FRAMES` kadar kare |
| `_note_centering_failure` → `_centering_cooldown_until` (`gorev2_orchestrator.py:1015`) | **tek yazar** ve **üretimde hiç çağrılmıyor**; `:684`'teki aday filtresi kalıcı boş sözlüğü sınıyor | Aynı şekil `CENTERING_RETRY_COOLDOWN_S` (5.0 s) boyunca aday olmaz → döngü **kendiliğinden** kırılır |
| `DebounceTracker` | yalnızca **başarılı GPS kaydından sonra** kuruluyor | Başarısız takip de debounce'a girer |

Üçü de **zaten tasarlanmış**, **zaten yazılmış** ve **bağlanmamış**. Yani F1'in
sınırsızlığı bir tasarım eksiği değil, **bağlantı eksiği**.

**Bu yüzden önerim:** önce `_note_centering_failure`'ı Offboard-hatası dalından
çağır ve `TargetValidator`'ı yeniden niteletmeye zorla. Yeni sayaç **ancak**
bunlar ölçüldükten sonra, hâlâ gerekiyorsa.

**Neden yine de bir "ayrı sayaç" tartışması var:** `_centering_attempts` /
`_abandon_target` mekanizması **merkezleme** başarısızlığı için kurulmuş
(cap 3, `_center_with_retries:953`). Offboard-geçiş hatası **farklı bir sınıf**
— muhtemelen geçici bir otopilot durumu, hedefin görünürlüğüyle ilgisi yok.
İkisini aynı sayaçta toplamak, bir otopilot aksaklığı yüzünden **görünür bir
hedefi kalıcı olarak terk etmeye** yol açabilir. Bu yüzden diriltme yapılırken
**sayaçlar ayrı tutulmalı**; ama bu "yeni mekanizma" değil, mevcut olanın
doğru parametrelenmesi.

---

## 1. ADR-004 ile çelişki mi, ilkeye DÖNÜŞ mü — **DÖNÜŞ**

ADR-004 `:492-493` ve `:499` iki şey söylüyor:

> *"**no auto-retry into the same pursuit** — re-enter SEARCHING, let
> debounce/track-ready re-qualify naturally"*
>
> *"retries are only ever applied to idempotent, non-safety-critical
> operations. Anything touching the payload interlock or an armed/**Offboard
> state transition escalates instead of retrying blindly**."*

**Bugünkü davranış bu ilkenin ihlalidir**, düzeltme değil:

1. `:716-724` dalı başarısız bir **Offboard geçişinden** sonra takibi
   **aynen tekrar ediyor** — üstelik bir **rota resume'u da harcayarak**.
   Ölçülen tekrar aralığı **101 ms**. Bu, `:499`'un yasakladığı "blind retry"
   tanımının tam karşılığı ve dahası tek bir takip değil, **rota bütçesi de
   tüketen** bir tekrar.
2. `:493`'ün "doğal yeniden nitelenme" varsayımı **ölçümle çürüdü**:
   `TargetValidator` streak'i hiç sıfırlanmadığı için yeniden nitelenme
   **anlık**. ADR'nin öngördüğü yavaşlatıcı **hiç var olmamış**.

> Yani: korumaları diriltmek ADR-004'e **karşı** değil, ADR-004'ün
> **yazdığı ama gerçekleşmemiş** davranışı fiilen kurmaktır.

`:499`'un "escalate" kısmı ise ayrı bir soru — aşağıda.

---

## 2. Guard tetiklenince görev ne yapacak — seçenekler

Sorduğunuz can alıcı nokta. `:499` "escalate" diyor ama **neye** escalate
edeceğini söylemiyor. Üç seçenek:

| | davranış | artı | eksi |
|---|---|---|---|
| **A** | Şekli bu tur için **terk et**, aramaya devam et (diğer hedef ve rota sürer) | Mevcut `_abandon_target` mimarisiyle **birebir aynı**; yeni durum yok. Görev devam eder | Hedef gerçekten oradaysa ve sorun geçiciyse **fırsat kaçar** |
| **B** | **HOLD'da kal**, CRITICAL yayınla, operatör müdahalesi bekle | `:499`'un "escalate"ine en yakın okuma | Otonom yarışmada operatör yok; `MISSION_TIMEOUT` (600 s) zaten tek gerçek ağ. Pratikte **görevi bitirir** |
| **C** | Görevi **abort** et, dönüp in | En muhafazakâr | Tek bir otopilot aksaklığı için **tüm görevi** feda eder. Ölçüm bunu desteklemiyor: ≥2 hatalı koşumların %40'ı yine de aramayı tamamlıyor |

**Önerim: A.** Gerekçe ölçümde:
- 0–1 Offboard hatası olan koşumlar görevi **%2–4** kaybediyor; **≥2** olanlar **%60**.
  Yani zarar **tekrar sayısıyla** birikiyor, tek olayla değil → doğru cevap
  "durdur ve bekle" değil, **"tekrarı kes"**.
- A, rota resume'u harcamayı **durdurur** ki F2'nin görev-bitiren biçimi tam olarak odur.
- A, `_abandon_target`'ın zaten yaptığı şey; **yeni bir görev durumu icat etmiyoruz**.

**B/C'yi elememin sebebi:** ikisi de "escalate"i *görevi durdurmak* diye okuyor.
Ama ADR-004 `:499`'un karşıtlığı **retry vs escalate**, ve buradaki escalate'in
anlamı "körü körüne tekrarlama, **bir üst mercie bildir ve o hedefi bırak**"
olarak da okunabilir — A budur ve CRITICAL olayı da yayınlar.

> **Bu bir yorum farkı ve ADR açık değil. Kararı sizin vermeniz gerekiyor:
> A (terk et, devam et) mi, B (HOLD + escalate) mi?**

---

## 3. Önerilen uygulama (onaylarsanız)

| # | değişiklik | dosya | risk |
|---|---|---|---|
| 1 | `:716-724` dalında `_note_centering_failure(shape)` çağır — **ama Offboard'a özel bir sayaçla** (`_offboard_failures[shape]`), merkezleme sayacına karışmasın | `gorev2_orchestrator.py` | düşük |
| 2 | Aynı dalda `TargetValidator`'ın o şekil için streak'ini sıfırla (`reset()`'e ilk üretim çağrısı) | `gorev2_orchestrator.py` + `target_validator.py` | düşük |
| 3 | Offboard hata sayacı N'i aşınca `_abandon_target(shape, reason="offboard_switch_failed")` → **Seçenek A** | `gorev2_orchestrator.py` | orta, **onay gerekir** |
| 4 | `CENTERING_RETRY_COOLDOWN_S`'in gönderilen değeri (5.0) ile ADR-009'un yazdığı (10.0) farkını **belgele**; değeri değiştirme | yorum | yok |

**N için öneri: 3.** Gerekçe: ölçülen doz-yanıt eşiği **≥2 hatada %60 kayıp**;
3'te kesmek, tek bir geçici aksaklığa (%75 başarı oranıyla 1 hata çok yaygın)
tolerans bırakırken bütçe tüketen kuyruğu keser. **Bu değer ölçümle
doğrulanmalı** — külliyatta koşum başına hata dağılımı 0:77, 1:32, ≥2:15.

**Dokunulmayacak:** Görev C/D/E4e, `motion_fsm.py`, `_center_with_retries`'ın
mevcut cap-3 mantığı, ADR dosyaları.

---

## 4. Onayınızı istediğim iki nokta

1. **Asıl yol: üç ölü korumayı diriltmek** (yeni mekanizma değil). Kabul mü?
2. **Guard tetiklenince Seçenek A** (şekli terk et, arama ve rota devam etsin)
   mi, yoksa **B** (HOLD + operatöre escalate) mi? ADR-004 `:499` bu noktada
   açık değil ve yorum farkı sizin kararınız.

---

# UYGULANDI (2026-09-04) — implementasyon raporu

## ⚠ MADDE 1 (operatör isteği): bu düzeltme SEMPTOMU sınırlıyor, KÖK NEDENİ KAPATMIYOR

Guard, F1 döngüsünün **sınırsız olmasını** engelliyor. Ama kök neden —
`offboard.start()`'ın OFFBOARD mod komutunu PX4'e **hiç göndermeden, istisna
da atmadan sessizce dönmesi** — **açık**. Araç hâlâ, gördüğü ve gerçekten
orada olan bir hedefi, otopilotta hiçbir hata yokken terk ediyor.

**Guard bir zarar sınırlayıcıdır, düzeltme değildir.**
F1'in gerçek kapanışı: `docs/TODO-offboard-start-kok-neden.md` — ③'ten sonra.

## Yapılan

| dosya | değişiklik |
|---|---|
| `core/config/parameters.py` | `OFFBOARD_FAILURE_MAX_PER_TARGET = 3` (ayrı sabit, gerekçesi doz-yanıtla yazılı) |
| `core/mission/gorev2_orchestrator.py` | `_offboard_failures` sayacı; `_note_offboard_failure()`; `:756` başarısızlık dalından çağrı |
| `tests/test_gorevF_offboard_failure_guard.py` | 8 yeni test |

Üç koruma da dirildi: `validator.reset()` (**`core/`'daki ilk üretim çağrısı**),
`_centering_cooldown_until` yazımı, `debounce.mark_processed()`.
`_centering_attempts` **kirletilmedi** — testle çakılı.

## Testler
**492 → 500 geçti, 1 atlandı.** Regresyon yok.

## CANLI SITL DOĞRULAMASI (birim testte değil)

Guard N=3'te doğal olarak ~%1.5 olasılıkla ateşlenir; mekanizmayı kanıtlamak
için **geçici olarak N=1** yapıldı, koşum sonrası **SHA ile birebir geri
yüklendi** (`506fc82a…`, doğrulandı; yürürlükteki değer tekrar **3**).

Koşum `logs/mission_57670f47d43e.jsonl`, 01:39:32 → 01:40:37:

```
01:40:03  TARGET_SELECTED KIRMIZI_UCGEN (0.9)
01:40:06  OFFBOARD_SWITCH_FAILED  stage=confirm_timeout
          modes_seen=["HOLD","MISSION"]  poll_count=15  pause_s=0.017
01:40:06  OFFBOARD_PURSUIT_ABANDONED  {offboard_failures:1, max:1,
                                       action:"abandon_shape_continue_search"}
01:40:06  MISSION_PHASE_CHANGED -> SEARCHING (reason offboard_switch_failed)
01:40:06  MISSION_CURRENT_ITEM_SET {index:2}
01:40:07  MISSION_ROUTE_RESUMED                    <-- ROTA DEVAM ETTI
01:40:13  TARGET_SELECTED MAVI_ALTIGEN (0.9)       <-- DIGER SEKIL PESINE DUSULDU
01:40:16  OFFBOARD_PURSUIT_ABANDONED (MAVI_ALTIGEN)
01:40:18  MISSION_ROUTE_RESUMED                    <-- ROTA YINE DEVAM ETTI
01:40:34  MISSION_FAILED (search_incomplete_mission_finished) -> RETURN -> LANDING
```

**Kanıtlanan Seçenek A davranışı:**
- Şekil terk edildi, **görev durmadı** — `SEARCHING`'e dönüldü
- **Rota devam etti** (iki kez `MISSION_ROUTE_RESUMED`)
- **Diğer şeklin peşine düşüldü** (KIRMIZI terk edildikten 7 s sonra MAVI seçildi)
- **HOLD'da beklenmedi, abort edilmedi** — B ve C elenmişti, davranış A ile uyumlu
- Sonunda görev başarısız oldu çünkü **N=1'de her iki şekil de ilk hatada
  terk edildi** — bu tam olarak N=1'in anlamı ve gerçek değerin neden 3
  olduğunun kanıtı

**①'in gözlenebilirliği aynı koşumda karşılığını verdi:**
`Gozlenen modlar: 1.41s:HOLD, 1.61s:HOLD, … 2.81s:HOLD` — 15 yoklamanın
**hiçbirinde OFFBOARD yok**, külliyat bulgusu canlıda birebir doğrulandı.
Ayrıca `pause_duration_s ≈ 0.017–0.021 s`: duraklama **anlık**, yani
ADR-009/010'un "pause resume'dan ~1 s sonra düşüyor" anlatısı bir kez daha
çürüdü.

**Dikkat:** bu koşumda ~35 saniyede **üç** Offboard hatası görüldü — külliyat
ortalaması %24.4'ün belirgin üstünde. Oranın koşuma/derlemeye göre değişip
değişmediği kök-neden görevinde ölçülmeli.

## Dokunulmayanlar
Görev C/D/E4e, `motion_fsm.py`, `_center_with_retries`'ın cap-3 mantığı,
ADR dosyaları.
