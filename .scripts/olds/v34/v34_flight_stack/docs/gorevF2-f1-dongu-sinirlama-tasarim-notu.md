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
