# Görev F1-KÖK — FAZ 2: K6'nın projeye uygulanması ve canlı doğrulaması

**Tarih:** 2026-09-04
**Commit:** `82f3316d` (uygulama) — öncesinde `c31c48a6` (ilgisiz test düzeltmesi)
**Durum:** uygulandı, test edildi, canlı SITL'de doğrulandı. **Push edilmedi.**

---

## 1. Ne yapıldı

`switch_to_offboard()` içinde, `switch_to_offboard_from_mission()` ile
`start_offboard()` **arasına** ölçülmüş bir bekleme kondu:

```python
await self.flight.switch_to_offboard_from_mission()   # DO_SET_MODE 176, main=4
...
if OFFBOARD_PAUSE_SETTLE_S > 0:
    await asyncio.sleep(OFFBOARD_PAUSE_SETTLE_S)      # 50 ms
await self.flight.start_offboard()                    # DO_SET_MODE 176, main=6
```

`OFFBOARD_PAUSE_SETTLE_S = 0.05` — `core/config/parameters.py`, kök neden ve
ölçüm gerekçesi parametrenin başında yazılı.

**Neden tam bu noktaya:** engellenmesi gereken şey iki DO_SET_MODE komutu
arasındaki mesafedir. Çağıran tarafta beklemek aynı garantiyi vermez —
araya başka bir `pause_mission()` girebilir.

---

## 2. Kök neden (özet)

MAVSDK v3.17.2'de `CommandIdentification` =
`{maybe_param1, maybe_param2, command, target_system_id, target_component_id}`
ve param alanları **yalnızca** `REQUEST_MESSAGE` ile `SET_MESSAGE_INTERVAL`
için doldurulur. `DO_SET_MODE` (176) için doldurulmaz. Sonuç:

| çağrı | gönderilen | MAVSDK kimliği |
|---|---|---|
| `mission.pause_mission()` | DO_SET_MODE 176, **main=4** | `{0,0,176,1,1}` |
| `offboard.start()` | DO_SET_MODE 176, **main=6** | `{0,0,176,1,1}` |

Birebir aynı. `pause`'un ACK'i hâlâ yoldayken `start()` kendi iş kalemini
kuyruğa koyarsa, gelen ACK **OFFBOARD kalemine atfedilip** onu `Success` ile
çözer — offboard komutu **hiç gönderilmeden**. `start()` hatasız döner, PX4
hiçbir şey almaz, araç HOLD'da kalır.

Ayrıntı: `docs/gorevF1-offboard-start-kok-neden.md`.

---

## 3. FAZ 1 ölçümü (tekrar)

`tools/offboard_gap_sweep.py`, 175 deneme, tek SITL oturumu:

| bekleme | başarısız | oran |
|---|---|---|
| **0 ms** | **5/25** | **%20.0** |
| 20 / 30 / 40 / 50 / 100 / 200 ms | 0/25 her biri | **%0** |

Diz noktası 0–20 ms arasında: çakışma penceresi **tam bir round-trip** kadar.
≥20 ms birleşik `0/150` → %95 üst sınır **~%2.0**.

**50 ms seçildi** çünkü 20 ms taranan *en düşük* değerdi ve altında ölçülmüş
pay yoktu. 50 ms round-trip'in (~11–14 ms) ~4 katı, gözlenen en yüksek
`start()` süresinin (25.4 ms) 2 katı.

---

## 4. Canlı SITL doğrulaması

**5 koşum, tek SITL oturumu, 2026-09-04 07:16–07:49.**

### 4.1 Boşluk gerçekten uygulanıyor mu

`mavsdk_backend_base` günlüğündeki iki satırın damgası arasındaki fark
("Mission'dan Offboard'a geçiş yapılıyor" → "Offboard başlatılıyor"):

```
70  59  70  63  65  69  65  62  63  73   (ms)
```

**10/10 geçişte ≥ 59 ms.** Hedef 50 ms + `pause_mission()`'ın kendi
round-trip'i (ölçülen `pause_duration_s`: 0.009–0.02 s). Beklenen davranış.

### 4.2 Başarısızlık oranı

| koşum | n | başarısız | poll_count | pursuit_abandoned | yük bırakma | Görev 2 |
|---|---|---|---|---|---|---|
| acc5020f3187 | 2 | **0** | 4, 7 | 0 | 2 | ✔ |
| cd6c3cf6370e | 2 | **0** | 6, 3 | 0 | 2 | ✔ |
| 4bffff2d42d3 | 2 | **0** | 5, 2 | 0 | 2 | ✔ |
| e9d16e5914fb | 2 | **0** | 6, 5 | 0 | 2 | ✔ |
| e7c0f2922093 | 2 | **0** | 3, 5 | 0 | 1 | — (*) |

(*) Bu koşum **dışarıdan iptal edildi** — ölçüm koşumunun 10 dakikalık
harness zaman aşımı ana kabuğu düşürdü, görev 07:48:51'de
`Gorev iptal edildi (cancelled)` ile kapandı. **Offboard hatası değil**;
iki geçişi de iptalden önce başarıyla tamamlanmıştı.

| | taban (K6 öncesi) | K6 sonrası |
|---|---|---|
| geçiş denemesi | 149 (59 koşum) | 10 (5 koşum) |
| `OFFBOARD_SWITCH_FAILED` | **35 (%23.5)** | **0 (%0)** |
| `OFFBOARD_PURSUIT_ABANDONED` (F1 guard) | 0 | **0** |
| `ROUTE_REJOIN_SKIPPED` (F2-a guard) | 3 | **0** |

### 4.3 İstatistiksel dürüstlük

**Canlı koşumlar tek başına kanıt DEĞİL.** Taban oranı (%23.5) geçerli
olsaydı 10 denemede sıfır başarısızlık görme olasılığı **%6.9** — düşük ama
"olmaz" değil. `0/10`'un %95 üst sınırı (rule of three) **%30**, yani canlı
veri tek başına taban oranını dışlamıyor.

**Kanıtın ağırlığı FAZ 1 taramasındadır:** aynı düzenekte, aynı çağrı çiftiyle
`0/150` → %95 üst sınır **~%2.0**. Canlı koşumların işi farklı ve daha dar:
**beklemenin gerçek kod yolunda fiilen uygulandığını** (4.1) ve gerçek görev
koşullarında hiçbir yan etki üretmediğini göstermek. İkisi birlikte iddiayı
taşıyor; ayrı ayrı taşımıyor.

### 4.4 F1 guard tetiklendi mi

**Hayır — 5 koşumun hiçbirinde `OFFBOARD_PURSUIT_ABANDONED` yok.** Guard'ın
sayacı hiç 1'e bile çıkmadı, çünkü hiç başarısızlık olmadı.

**Guard KALDIRILMAMALI.** `0/150`'in %95 üst sınırı **%2**, sıfır değil.
Katman sırası: **K6 (önle) → F1 guard (sınırla)**.

---

## 5. K1 (retry) eklenmedi

Karar: **eklenmiyor.**

1. K6 **kök nedeni kapatıyor**; K1 yarışı bekleyerek aşan **dolaylı** bir
   çözüm. Kök neden kapalıyken tetiklenmesi beklenmez.
2. K1 **ADR-004 `:499`** ("otomatik yeniden deneme yok, yukarı bildir") ile
   doğrudan gerilimde. Gerekmeyen bir katman için o gerilimi satın almaya
   değmez.
3. **Üçüncü katman zaten var:** F1 guard (N=3, Seçenek A).

---

## 6. Testler

`tests/test_f1_offboard_pause_settle.py` — 3 test:
- parametrenin makul aralıkta olduğu (0.020–0.200 s),
- beklemenin iki komut **ARASINDA** gerçekleştiği (sırayı + mesafeyi korur),
- `start()` **reddedilse bile** beklemenin önceden yapıldığı — aksi halde F1
  guard'ı hiç gönderilmemiş bir komutu "başarısızlık" olarak sayardı.

Tam paket: **515 geçti, 1 atlandı, 0 başarısız.**

### 6.1 Yol boyunca bulunan, K6'dan bağımsız kırmızı test

`test_mission_route_resume.py::test_centering_timeout_resumes_the_paused_route`
HEAD'de (`48454638`) de düşüyordu — `git stash` ile doğrulandı, K6 ile ilgisi
yok. Testin ölçtüğü davranış (**"merkezleme zaman aşımına uğrayınca rota
kaldığı yerden devam eder"**) **gerçekleşiyor**; sadece testin 8 s'lik yoklama
penceresinden geç gerçekleşiyor. 40 s'lik pencereyle test 18.4 s'de geçiyor
(ölçüldü).

8 s'i geçersiz kılan iki değişiklik, ikisi de bu testten sonra geldi:
1. `CENTERING_RETRY_COOLDOWN_S = 5 s` (RETRY_IN_PLACE) → 3 × 5 s = 15 s.
2. **F2-a: `ENABLE_ROUTE_REJOIN` False → True.** Pursuit bırakılınca önce ara
   noktadan rotaya dönülmeye çalışılıyor; `MockFlightBackend` **statik**
   olduğu için rejoin hiçbir zaman yakınsayamaz ve her seferinde
   `ROUTE_REJOIN_TIMEOUT_S`'in (15 s) tamamını yakar.
   Ölçülen zaman çizelgesi: bırakma t=3.3 s, `start_mission` #2 t=18.4 s.

İkisi de bu testte sıfırlanıyor/kısaltılıyor — `conftest.py`'nin
`MISSION_START_HOLD_S` için yaptığının aynısı. **Ürün kodunda değişiklik
yok.** Ayrı commit: `c31c48a6`.

---

## 7. Açık kalan

- **Bu bir önlemdir, sınırlayıcı değil.** F1 guard'ı ikinci katman olarak
  kalır ve kaldırılmamalıdır (%2 üst sınır).
- 100–200 ms'nin **ek faydası ölçülmedi**; 50 ms'nin altına inmek için de
  ölçülmüş pay yok (20 ms taranan en düşük değerdi).
- Gerçek donanımda round-trip farklı olabilir (telemetri linki, baud).
  Değer SITL'de ölçüldü; gerçek uçuş öncesi aynı taramanın gerçek link
  üzerinde tekrarı **ayrı bir kapı**.
- ADR güncellemeleri: `docs/TODO-adr-guncellemeleri.md` (7 madde, bilerek
  ertelendi).
