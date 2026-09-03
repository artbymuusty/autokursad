# BEKLEYEN — F1'in GERÇEK kapanışı: `offboard.start()` komutu neden göndermiyor

**Durum:** AÇIK. ③ (F2-a) tamamlandıktan sonra ele alınacak (operatör kararı,
2026-09-04).

---

## Neden ayrı bir görev

Görev F ② ile eklenen guard **F1'in SEMPTOMUNU sınırlıyor**: döngü artık
sınırsız değil, `OFFBOARD_FAILURE_MAX_PER_TARGET` (3) denemeden sonra hedef
bu tur için terk ediliyor ve arama/rota devam ediyor (Seçenek A).

**Kök nedeni KAPATMIYOR.** Araç hâlâ, gördüğü ve gerçekten orada olan bir
hedefi, otopilot tarafında hiçbir hata olmadığı hâlde **terk ediyor**.
Guard bir zarar sınırlayıcıdır, bir düzeltme değildir.

## Kanıtlanmış olan (Görev F ①, `gorevF-mode-gecisi-analiz.md` EK 2)

`DO_SET_MODE` (cmd 176) `param2` = PX4 ana modu: **4 = AUTO, 6 = OFFBOARD**.

- Başarısız geçiş penceresinde gönderilen `DO_SET_MODE`'ların **hepsi
  `param2=4` (AUTO)** ve hepsi `ACCEPTED`. **`param2=6` HİÇ gönderilmiyor.**
- Başarılı geçişte `param2=6` var. Sekiz ULog toplamı: AUTO=53, OFFBOARD=16;
  referans koşumda 2 başarılı giriş ↔ tam **2** adet `param2=6`.
- `start_offboard()` **istisna atmıyor** — 68 `OFFBOARD_SWITCH_FAILED`
  olayının hiçbirinde `{"error": ...}` yok.
- 2026-09-04 canlı doğrulama koşumu: üç başarısızlıkta da
  `modes_seen: ["HOLD", "MISSION"]`, 15 yoklama, **hiç OFFBOARD yok**;
  `pause_duration_s` ≈ **0.017–0.021 s**.

> **`offboard.start()` hatasız dönüyor ama OFFBOARD mod komutunu PX4'e hiç
> göndermiyor. PX4 bir şeyi reddetmiyor — kendisine sorulmuyor bile.**

Bu, sorunu **PX4'ten istemciye** taşıyor: `mavsdk_common/mavsdk_backend_base.py`
`start_offboard()` → `drone.offboard.set_velocity_body(...)` +
`drone.offboard.start()`.

## Kapatmak için yapılacaklar

1. **MAVSDK Offboard eklentisinin iç durum makinesini incele.** En olası aday:
   eklentinin `start()`'ı, kendi iç durumuna göre "zaten başlatılmış" sayıp
   komutu atlaması, ya da `set_velocity_body` ile `start()` arasındaki bir
   ön koşulun sağlanmaması.
2. **`start()`'ın dönüş değerini kontrol et.** Bugün dönüş **yok sayılıyor**;
   yalnızca istisna yakalanıyor. MAVSDK `OffboardResult` döndürüyorsa ve
   `SUCCESS` dışında bir değer geliyorsa, bu tek satırlık bir tespit olur.
3. **`mavsdk_server` loglarını yükselt.** Sunucu tarafı, komutu neden
   göndermediğini kendi seviyesinde raporlayabilir.
4. **Hipotez testi:** `offboard.start()` öncesi setpoint akışını
   `OFFBOARD_SETPOINT_INTERVAL_S`'te sürekli hâle getir (bugün tek bir
   `VelocityBodyYawspeed(0,0,0,0)` gönderilip onay boyunca 3.0 s hiçbir şey
   akıtılmıyor — oysa depo PX4'ün ~500 ms sınırını `parameters.py:343-346`'da
   kendisi belgeliyor ve kardeş bir yorumda bunu yasaklıyor). **Bunun
   oranı değiştireceğine dair ölçüm YOK**; uygulayan sonucu **deney** saymalı.

## Ölçülen etki (neden önemli)

| koşumdaki Offboard hatası | rota erken bitti |
|---|---|
| 0 | %2 |
| 1 | %4 |
| **≥2** | **%60** |

Guard bu kuyruğu kesiyor ama hataların **kendisini** azaltmıyor. Kök neden
kapanmadıkça, her hata hâlâ bir hedefin kaybı demek.

**Not:** 2026-09-04 doğrulama koşumunda ~35 saniyede **üç** başarısızlık
görüldü — külliyat ortalaması olan %24.4'ün belirgin şekilde üstünde.
Oranın koşuma/derlemeye göre değişip değişmediği de bu görevde ölçülmeli.
