# Görev F2-b1 — Çok bacaklı arama rotası (ADIM 1)

**Tarih:** 2026-09-04 · **KOD DEĞİŞİKLİĞİ YOK** — yalnızca operasyonel.
**Ölçüm:** `demo/runs/20260904T035723/` (iki plan, aynı SITL oturumu, aynı derleme).

---

## 1. Rota nasıl üretilip yükleniyor (belgeleme)

Görev 2 rotayı **üretmez**; `confirm_existing_mission()` yalnızca araçta hazır
bir rota arar. Rotayı koymak operatörün QGroundControl'deki işidir (ADR-007).
Demoda operatör olmadığı için zincir şu:

| aşama | dosya | ne yapar |
|---|---|---|
| **üretim** | `Tools/simulation/gz/worlds/generate_competition_plans.py` | Tasarım sabitlerinden (`TRACK_HALF`, `LEADIN`, `ARC_R`, `ARC_SEGS`, `ARC_OFFSET`) `.plan` üretir. **Tek doğruluk kaynağı budur.** Çıktısını yazmadan önce Görev 2 rota sözleşmesine karşı kendisi doğrular |
| **format** | QGroundControl `.plan` (JSON), `mission.items[]` | `NAV_TAKEOFF` (22) yalnızca seq 0'da opsiyonel; gerisi `NAV_WAYPOINT` (16). `NAV_LAND` (21) ve `NAV_RTL` (20) **YASAK** — rota bir inişe kadar uçarsa araç yük fazı için havada olması gerekirken iner |
| **konum** | `~/Documents/QGroundControl Daily/Missions/` (`KURSAD_MISSIONS_DIR` ile değiştirilebilir) | Depo **dışında**. Depoda referans kopyalar: `Tools/simulation/gz/worlds/plans/` |
| **dönüştürme** | `demo/make_gorev_plan.py` | Elle çizilmiş bir QGC planından RTL/LAND item'larını silip görev-uyumlu varyant üretir. Orijinale dokunmaz |
| **yükleme** | `demo/upload_plan.py <plan>` | Araca yükler ve **geri okuyarak** birebir doğrular (ack yeterli sayılmaz) |
| **orkestrasyon** | `demo/run_demo.sh --plans "..."` | Ön kontrol → SITL → plan başına (yükle+doğrula → LAND temizle → görev koş → özet). Eksik plan varsa üreticiyi kendisi çağırır |

> **Not:** benim önceki koşumlarda kullandığım `demo/run_demo_gz.sh` rota
> **yüklemez** — araçta ne varsa onunla uçar. Üç koşumda 3 item görmemizin
> sebebi buydu: araçta `competition_1way` duruyordu.

### Mevcut iki rota

| plan | item | geometri |
|---|---|---|
| `competition_1way` | **3** | takeoff + lead-in + tek kuzey bacağı → **tek arama bacağı** |
| `competition_2way` | **10** | takeoff + 2 uzun bacak (±7.25 m, 14.5 m aralık) + kuzey ucunda 5 noktalı yarım daire dönüş |

> **Yeni plan üretmeye gerek yok — çok bacaklı rota zaten var.**

Daha yoğun bir tarama gerekirse `TRACK_HALF` küçültülüp üretici yeniden
çalıştırılır; ama bu bir **kapsama tasarımı** kararıdır (15 m'de kamera izi
~17.8 × 13.3 m, yani 14.5 m aralık zaten örtüşüyor) ve operatörün onayını
gerektirir.

---

## 2. Ölçüm

`./run_demo.sh --plans "competition_1way competition_2way" --no-dashboard --mission-timeout 420`

Her iki plan da aynı oturumda, arka arkaya koştu.

### Dürüst negatif sonuç: arıza senaryosu tekrar üretilemedi

| | 1way | 2way |
|---|---|---|
| `OFFBOARD_SWITCH_FAILED` | **0** | **0** |
| resume sayısı | 1 | 1 |
| rota erken bitti mi | hayır | hayır |
| SEARCH_COMPLETE | ✓ | ✓ |
| bırakılan yük | 2 | 2 |
| sonuç | MISSION_FAILED (Görev 3 pickup) | MISSION_FAILED (Görev 3 pickup) |

Offboard hataları stokastik (külliyatta %24.4) ve bu iki koşumda **hiç
olmadı**. Dolayısıyla **≥2-hata senaryosu karşılaştırılamadı** — 1way tarafında
da rota tükenmesi yaşanmadı. Bunu başarı diye sunmuyorum.

### Ama yapısal pay ÖLÇÜLDÜ — ve fark keskin

Arama tamamlandığı anda rotanın neresinde olduğumuz:

| plan | rota | ulaşılan indeks | **kalan waypoint** |
|---|---|---|---|
| `competition_1way` | 3 item (son indeks 2) | **2** | **0** |
| `competition_2way` | 10 item (son indeks 9) | **2** | **7** |

> **1way'de rota TAM BİTMİŞTİ.** Bir resume daha olsaydı
> `is_mission_finished()` True olur ve görev `search_incomplete_mission_finished`
> ile biterdi. O koşum **şansla** kurtuldu.
>
> **2way'de 7 waypoint'lik pay vardı** — o kadar ek resume/takip tolere
> edilebilirdi.

Bu, F2'nin "rota tükenmesi" yarısının doğrudan ölçüsüdür: **pay 0 → 7**.

### Yan fayda: eksen tespiti anlamlı hâle geliyor

`_detect_route_axis()` en az 2 `NAV_WAYPOINT` istiyor; 1way'de **tam 2** var,
yani sınırda çalışıyor. 2way'de 9 waypoint var ve iki farklı boylamda iki şerit
bulunuyor — `lat_span` (~120 m) ≫ `lon_span` (14.5 m) olduğu için sabit eksen
doğru şekilde **lon** tespit edilir ve rejoin, aracı **kendi şeridinin**
boylamına geri çeker. 1way'de tek şerit olduğu için bu ayrım hiç test edilemezdi.

---

## 3. Hüküm ve öneri

**F2-b1 gerçek ve ölçülmüş bir kazanç sağlıyor**, sıfır kod değişikliğiyle:
rota payı 0 → 7. Ama **mekanizmayı ortadan kaldırmıyor, marj ekliyor** — yeterince
çok resume hâlâ 2way'i de tüketebilir.

**F2-b1 tek başına yeterli mi — HAYIR.** F2'nin iki yarısı vardı:

| yarı | F2-b1 çözer mi |
|---|---|
| Rota tükenmesi (görev bitiren) | **büyük ölçüde** — pay 0 → 7 |
| Yanal ofset / kapsama kalitesi (11.34 m, 19–36 m hat kadraj dışı) | **hayır** — araç hâlâ hattın dışında MISSION'a dönüyor, PX4 hâlâ kiriş uçuyor |

**Önerim:**
1. **`competition_2way`'i varsayılan arama rotası yap** (operasyonel karar,
   kod değişikliği yok). `run_demo.sh` zaten ikisini de koşuyor; standart
   akış için 2way'e geçilmeli.
2. **ADIM 2 hâlâ gerekli** ama önceliği düştü: görev-bitiren yarı büyük ölçüde
   kapandığı için rejoin artık "kapsama kalitesi" iyileştirmesi, "görev
   kurtarıcı" değil. Sizin sıraladığınız 1-4 aynen geçerli — özellikle
   **madde 2 (F1 çakışma guard'ı) olmadan bayrak açılmamalı**.
3. **Ölçüm borcu:** ≥2-hata senaryosu bu koşumda tekrar üretilemedi. Rota
   tükenmesinin 2way'de gerçekten azaldığını görmek için ya daha çok koşum
   ya da hatayı zorlayan bir düzenek gerekir. Bunu **kapanmamış** sayıyorum.

Kod değişikliği yapılmadı. Görev C/D/E4e'ye, `motion_fsm.py`'a, F1
düzeltmesine dokunulmadı.
