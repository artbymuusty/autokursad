# Görev F2-a — `ENABLE_ROUTE_REJOIN`: FAZ 1 analizi

**Tarih:** 2026-09-04 · **KOD DEĞİŞİKLİĞİ YOK** (salt okuma).
**Kaynak:** kod okuması + `logs/mission_57670f47d43e.jsonl`,
`mission_0600f0558de3.jsonl`, `mission_30a86d7d2e1c.jsonl`.

> **Süreç notu:** analiz sırasında bayrağı geçici açıp test paketini koşturmayı
> denedim; operatör bunu reddetti (FAZ 1 = salt analiz). Düzenleme kısmı
> reddedilmeden önce çalışmıştı, `git checkout` ile geri alındı ve
> `core/config/parameters.py` SHA `506fc82a…` olarak doğrulandı. Aşağıdaki
> hiçbir bulgu bayrak açılarak elde edilmedi.

---

## 1. İDDİANIN ÇAKILMASI

### 1a. `_route_axis` gerçekten `__init__`'te kuruluyor mu — **EVET**

`gorev2_orchestrator.py:158-160`:
```python
self._route_axis: str = None
self._pre_pursuit_lat: float = None
self._pre_pursuit_lon: float = None
```
Yorumu da açık: *"None means `_rejoin_route_axis()` is a no-op."*

### 1b. Kaç test, hangileri, neden — **RAPOR SAYIYI YANLIŞ VERMİŞTİ**

`parameters.py:262-265` "9 tests in three files" diyor. Gerçek: **4 dosya**,
7 `__new__` çağrı noktası (3 doğrudan test + 3 fabrika fonksiyonu + 1 benim
F1 testim, ki o `_route_axis`'i **kuruyor**).

`__new__` ile kurulup `_resume_mission_route()`'a ulaşan **11 test** var, ama
**3'ü kırılmaz**: `_search_complete` guard'ı bayrak kontrolünden **önce**
`return` ediyor —

```python
if self._search_complete:            # <-- ONCE bu
    ...
    return
if _params.ENABLE_ROUTE_REJOIN:      # <-- SONRA bu
    await self._rejoin_route_axis()
```

| dosya | ulaşan | kırılan |
|---|---|---|
| `test_mission_route_resume.py` | 3 | 2 |
| `test_adr010_retry_in_place_and_resume.py` | 2 | 2 |
| `test_adr009_stale_health_backoff_speed.py` | 5 | 4 |
| `test_mission_lifecycle_spec.py` | 1 | 0 |
| **toplam** | **11** | **8** |

**Neden `__new__`:** bilinçli bir fixture kısayolu. `test_mission_route_resume.py:36`
kendi yorumunda söylüyor: *"bypass full `__init__`, only need
`self.flight`/`self.publisher`"*. Gerçek `__init__` kamera, dedektör, event
bus, interlock, position store gibi bir sürü bağımlılık istiyor; bu testler
yalnızca resume yolunu sınıyor.

### 1c. Testleri düzeltmeden bayrağı açmak güvenli mi — **HAYIR, ama düzeltme tek satır**

`_rejoin_route_axis`'in ilk satırı:
```python
if self._route_axis is None or self._pre_pursuit_lat is None:
    return
```
Python soldan sağa kısa devre yapar → `_route_axis` **önce** okunur →
`AttributeError`. Yani dört fabrikaya **`orch._route_axis = None`** eklemek
yeterli; `_pre_pursuit_lat` hiç okunmaz. Ve `None` = belgelenmiş no-op
olduğu için **testlerin anlamı hiç değişmez**.

> **İddia doğrulandı:** üretim kodunda mekanizma tam, engel fixture'da.
> Sayı düzeltmesi: 9 değil **8** test, üç değil **dört** dosya.

### 1d. Mekanizmanın bağımlılıkları gerçekten var mı — **DÖRDÜ DE VAR**

| bağımlılık | konum |
|---|---|
| `centering.goto_global_position_and_wait()` | `centering_controller.py:1223` |
| `ROUTE_REJOIN_TIMEOUT_S = 15.0` | `parameters.py:274` |
| `flight.get_raw_mission_items()` | `mavsdk_backend_base.py:645` |
| `_CMD_NAV_WAYPOINT = 16` | `gorev2_orchestrator.py:293` |

---

## 2. `_rejoin_route_axis()` ne yapıyor ve F2'yi çözüyor mu

### Satır satır

1. `_route_axis` veya `_pre_pursuit_lat` yoksa **no-op** (`:484`)
2. Mevcut `(lat, lon)` okunur; okunamazsa **no-op** (`:487-490`)
3. Sabit eksen hedefe konur, **diğer eksen mevcut konumda bırakılır** (`:492-495`)
   → yani **yanal düzeltme**, önceki bir noktaya dönüş DEĞİL
4. Hedef irtifa **`MISSION_ALTITUDE_M`** (rotanın seyir irtifası), aracın o
   anki alçalmış irtifası değil
5. `goto_global_position_and_wait(..., timeout=15 s)`; sonuç ne olursa olsun
   normal resume devam eder (best-effort)

Eksen tespiti (`_detect_route_axis`, `:413`): rotanın **kendi** ham
koordinatlarından `lat_span` vs `lon_span`; büyük olan seyahat ekseni, küçük
olan **sabit** eksen. Global çerçevede değilse veya 2'den az `NAV_WAYPOINT`
varsa `None` döner (varsayım yapmaz).

### F2'yi çözer mi — **KISMEN**

F2'nin ölçülen iki yarısı var:

| yarı | ölçüm | rejoin çözer mi |
|---|---|---|
| **(i) Kapsama KALİTESİ** — araç hattın 11.34 m batısında MISSION'a dönüyor, PX4 son waypoint'e kiriş uçuyor, 15 m'de kamera yarı-genişliği ~8.9 m olduğu için **19–36 m'lik hat kadraj dışında** kalıyor | 11.34 m yanal ofset | **EVET.** Rejoin tam olarak bu yanal ofseti sıfırlar; araç hatta dönüp MISSION'a öyle girer |
| **(ii) Kapsama KAPSAMI** — her resume rotanın **son** indeksini yeniden dayatıyor, `is_mission_finished()` True'ya yaklaşıyor, rota **tükeniyor** (ADR-011 T3) | ≥2 Offboard hatasında **%60** erken rota bitişi | **HAYIR.** Rejoin rotaya **hat eklemez**; yalnızca yana kaydırır. Seyahat ekseni **mevcut konumda bırakılır**, yani bacak üzerindeki ilerleme geri alınmaz |

**Ölçülen rota yapısı bunu keskinleştiriyor** (`mission_57670f47d43e`, yeni
`MISSION_ROUTE_ITEMS` olayı):
```
3 item:  seq=0 NAV_TAKEOFF   seq=1 NAV_WAYPOINT   seq=2 NAV_WAYPOINT
```
→ **tek arama bacağı**. Her resume `set_current_mission_item(2)` = **son
waypoint**. Üç koşumda da aynı: `[1, 2, 2]`. Tek bacakta, bacağın sonuna
varmak = görev bitti.

> **Net teşhis: KISMEN.** Bayrağı açmak F2'nin **kapsama kalitesi** yarısını
> kapatır; **rota tükenmesi** yarısını kapatmaz. Ve rota tükenmesi, F2'nin
> **görev bitiren** biçimidir.

---

## 3. Rota tükenmesi için ayrı tasarım gerekiyor mu — EVET, ama muhtemelen KOD DEĞİL

Kök neden: PX4 mission indeksi bir **hedef waypoint**tir; "bacağın neresinde
kaldım" diye bir kavram yok. Tek bacaklı bir rotada her duraklama, kalan tek
hedefe yeniden nişan almak demek.

| seçenek | değerlendirme |
|---|---|
| **F2-b1 — Operatör rotayı çok bacaklı yükler** (boustrophedon, ~8-12 waypoint) | **En güçlü aday.** Rota üretimi ADR-007'ye göre **zaten operatörün işi** ve sistem rotayı asla değiştirmiyor. Çok bacakta bir resume yalnızca **o bacağı** yeniden hedefler, tüm aramayı değil. **Kod değişikliği sıfır.** Ayrıca `_detect_route_axis` de daha güvenilir olur (şu an tam 2 waypoint ile sınırda çalışıyor) |
| F2-b2 — Duraklama anında bacak-üstü konumu sakla, resume'da oraya dön | Kapsama boşluğunu kökten kapatır ama **yeni durum + yeni goto**; ADR-009 resume zamanlamasına ek yük; rejoin ile işlevsel örtüşme |
| F2-b3 — Kalan waypoint'lerle rotayı yeniden yükle | En invaziv ve **ADR-007'yi ihlal eder** (sistem rotayı üretmez/değiştirmez) |

**Önerim: F2-b1'i önce ölç.** Çok bacaklı bir rotayla tek koşum, rota
tükenmesinin gerçekten ortadan kalkıp kalkmadığını kod yazmadan gösterir.

---

## 4. YAN ETKİLER — **ciddi bir çakışma buldum**

### 4a. F1 düzeltmesiyle çakışma (KRİTİK)

`_rejoin_route_axis`'in docstring'i şunu **varsayıyor**:
> *"Called from `_resume_mission_route()`, **BEFORE** `flight.stop_offboard()`,
> so the vehicle is **still under Offboard authority** while it moves."*

**Bu varsayım F1 başarısızlık yolunda YANLIŞ.** `:760`:
```python
if not offboard_ok:
    self._note_offboard_failure(...)
    ...
    await self._resume_mission_route()     # <-- rejoin buradan da cagrilir
```
Offboard geçişi **başarısız** olduğu için araç **Offboard'da değil** — HOLD /
AUTO.LOITER'da. Sonuç, bayrak açıkken:

1. `goto_global_position_and_wait` Offboard setpoint'leri akıtır, **PX4 onları yok sayar**
2. Araç hareket etmez → **15 s tam zaman aşımı** → `ROUTE_REJOIN_TIMED_OUT`
3. Ve **düzeltilecek bir sapma zaten yoktur**: geçiş başarısız olduğu için
   araç rotadan hiç ayrılmamıştı

`_pre_pursuit_lat` **geçiş denemesinden önce** yakalandığı için (`:727-730`)
guard da devreye girmez — `_route_axis` ve `_pre_pursuit_lat` ikisi de dolu.

**Maliyet:** F1 guard'ı şekil başına 3 hataya izin veriyor × 2 şekil = en kötü
**6 × 15 s = 90 s**, 600 s'lik görev bütçesine karşı. 2026-09-04 doğrulama
koşumunda ~35 saniyede üç Offboard hatası görülmüştü.

> **Bayrak, F1 düzeltmesi olmadan tasarlanmıştı. İkisi bir arada, hiçbir işe
> yaramayan 15 saniyelik bloklar üretir.**

**Çözüm basit:** rejoin'i yalnızca Offboard'a **gerçekten girildiyse** çalıştır
(başarı yolunda `stop_offboard()` öncesi) — ama bu **kod değişikliğidir** ve
FAZ 2'ye aittir.

### 4b. Görev C / D / E4e ile çakışma — **YOK**

Üçü de **yük bırakma fazında** çalışıyor. `_resume_mission_route()` ise
`_search_complete` olduğu anda **kalıcı olarak** no-op:
```python
if self._search_complete:
    ... MISSION_RESUME_REJECTED ... return
```
Yük fazı Search Phase bittikten sonra başladığı için rejoin o fazda **hiç
çalışamaz**. Temiz ayrım.

### 4c. ADR-009 resume zamanlaması

`_rejoin_route_axis()` `_space_out_resume()`'dan **önce** çalışıyor, yani
resume başına **+0–15 s Offboard süresi** ekliyor. `parameters.py:261-263`'ün
"ADR-009'un resume zamanlamasına etkisi ölçülmedi" endişesi **hâlâ geçerli**
ve şimdi F1 guard'ıyla birlikte daha da büyüdü (daha çok resume).

---

## 5. TEST KAPSAMI — **SIFIR**

`tests/` içinde `_rejoin_route_axis`, `_detect_route_axis`,
`ROUTE_REJOIN_STARTED/DONE/TIMED_OUT`, `ROUTE_AXIS_DETECTED` geçen **tek bir
satır yok**.

Bu kod yolu bayrak baştan beri `False` olduğu için **hiç çalışmamış** — ne
testte, ne SITL'de, ne uçuşta. Açmak, **ilk kez** çalıştırmak demek.

> Bayrağı açmadan önce **en az bir entegrasyon testi ZORUNLU**:
> eksen tespiti (lat/lon), yanal düzeltmenin doğru eksene uygulandığı,
> `None` durumlarında no-op, zaman aşımında resume'un yine de sürdüğü,
> ve **4a'daki "Offboard'a girilmemişken çağrılma" senaryosu**.

---

## 6. ÖNERİLEN YOL

**(c) — bayrak tek başına yetersiz; fixture düzeltmesi + bir kod düzeltmesi +
test gerekiyor.**

Sıra önerim:

| # | iş | gerekçe | risk |
|---|---|---|---|
| **1** | 4 fabrikaya `orch._route_axis = None` (tek satır ×4) | Engeli kaldırır, **test semantiği değişmez** | ~yok |
| **2** | Rejoin'i yalnızca Offboard'a **gerçekten girildiyse** çalıştır | 4a'daki 15 s'lik boş bloklar F1 guard'ıyla birlikte 90 s'ye çıkabilir | düşük, ama **kod değişikliği** |
| **3** | Entegrasyon testi yaz (yukarıdaki 5 senaryo) | Kod yolu **hiç** çalışmamış | ~yok |
| **4** | Bayrağı aç, **1 canlı koşumla** ölç: yanal ofset düştü mü, resume süresi ne kadar arttı | ADR-009 endişesi ölçümle kapanır | orta, ölçüm koşumu |
| **5** | Ayrı: **F2-b1** — operatör çok bacaklı rota yüklesin, rota tükenmesi ölçülsün | Kod değişikliği sıfır; F2'nin görev-bitiren yarısını hedefler | ~yok |

**(a) doğrudan açmak** elendi: 8 test kırılır, kod yolu hiç çalışmamıştır ve
F1 ile çakışması ölçülmemiştir.
**(b) sadece fixture düzeltip açmak** yetersiz: 4a'daki çakışma ve sıfır test
kapsamı kalır.

---

## 7. Özet cevaplar

| soru | cevap |
|---|---|
| `_route_axis` `__init__`'te set ediliyor mu | **Evet** (`:158`) |
| Kaç test kırılır | **8** (11 ulaşıyor, 3'ü `_search_complete` ile erken dönüyor) — rapor "9 test / 3 dosya" diyordu, doğrusu **8 test / 4 dosya** |
| Üretimde mekanizma tam mı | **Evet**, dört bağımlılığın dördü de mevcut |
| Bayrak F2'yi kapatır mı | **KISMEN** — kapsama kalitesini evet, rota tükenmesini hayır |
| Yan etki riski | **Var ve ciddi**: F1 düzeltmesiyle çakışıyor (4a). C/D/E4e ile çakışma **yok** (4b) |
| Test kapsamı | **Sıfır** — entegrasyon testi zorunlu |
| Önerilen yol | **(c)**, yukarıdaki 5 adımlı sıra |

Kod değişikliği yapılmadı. Görev C/D/E4e'ye, `motion_fsm.py`'a ve F1
düzeltmesine dokunulmadı.
