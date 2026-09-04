# DEVİR — KURSAD40 v34 flight stack (2026-09-04, K6 sonrası)

## DURUM

**35 lokal commit, PUSH EDİLMEDİ** (`public/main..HEAD` = 35). Çalışma ağacı
temiz (tek istisna: `Tools/simulation/gz/worlds/default.sdf` — her SITL
başlatmasında `generate_competition_area.py` tarafından yeniden üretilir,
benim değişikliğim değil). SITL süreçleri temizlendi.

Son 4 commit:
```
671b79eb  F1-KÖK FAZ 2 canlı doğrulama raporu (5 koşum, 10/10)
82f3316d  F1-KÖK FAZ 2 (K6): pause -> start arasına 50 ms
c31c48a6  Test düzeltmesi: route-resume 8 s penceresi (K6'dan BAĞIMSIZ)
48454638  F1-KÖK FAZ 1: K6 bekleme taraması (175 deneme)
```

**Test paketi: 515 geçti, 1 atlandı, 0 başarısız.** (~6.5 dk sürüyor.)

---

## BİTEN İŞ — Görev F1-KÖK, K6

Kök neden kapatıldı. MAVSDK v3.17.2'de `CommandIdentification` DO_SET_MODE
(176) için komut **parametrelerini içermiyor**, bu yüzden
`mission.pause_mission()` (main=4) ile `offboard.start()` (main=6) birebir
aynı kimlikle kuyruğa giriyor ve pause'un ACK'i offboard kalemine atfedilip
onu çözüyor — **komut hiç gönderilmeden**.

Düzeltme: `switch_to_offboard()` içinde iki komut **arasına**
`OFFBOARD_PAUSE_SETTLE_S = 0.05` beklemesi.

| | taban | K6 sonrası |
|---|---|---|
| geçiş | 149 (59 koşum) | 10 (5 koşum) |
| `OFFBOARD_SWITCH_FAILED` | 35 (%23.5) | **0** |
| F1 guard tetiklemesi | 0 | **0** |
| ölçülen boşluk | — | 59–73 ms, 10/10 |

**K1 (retry) EKLENMEDİ** — kök neden kapalı, ADR-004 `:499` ile gerilimde,
üçüncü katman (F1 guard) zaten var.

---

## SIRADAKİ KARAR — PUSH

Kullanıcı bunu **birlikte** karara bağlamak istedi. 35 commit birikti, hepsi
bağımsız doğrulanmış. **CLAUDE.md kuralı:** açık "pushla" komutu olmadan
push YOK. Commit/onay/uygula push izni DEĞİLDİR.

Push edilecekse: **`public` remote'una** gider (`origin` değil),
mesajın ilk satırı tarih+saat taşır.

---

## HANGİ DOSYALARI OKUMALI

Sıra önemli — ilk üçü kampanyanın omurgası:

1. `docs/gorevF1-offboard-start-kok-neden.md` — kök neden, MAVSDK kaynak
   incelemesi, K1–K6 seçenekleri.
2. `docs/gorevF1-K6-bekleme-taramasi.md` — FAZ 1, 175 deneme, diz noktası.
3. `docs/gorevF1-K6-faz2-canli-dogrulama.md` — FAZ 2, uygulama + 5 canlı
   koşum + **istatistiksel dürüstlük bölümü** (§4.3 mutlaka okunmalı).
4. `core/config/parameters.py` — `OFFBOARD_PAUSE_SETTLE_S` (satır ~426),
   gerekçe parametrenin başında.
5. `core/navigation/centering_controller.py::switch_to_offboard()` — beklemenin
   konduğu yer ve neden tam orada olduğu.
6. `tools/offboard_gap_sweep.py` — kalıcı tanı aracı, tekrar ölçüm için.
7. `docs/gorevF2a-coklu-kosum-izleme.md` — F2-a çoklu koşum metrikleri.
8. `docs/TODO-adr-guncellemeleri.md` — **7 madde, bilerek ertelendi.**

---

## AÇIK BORÇLAR (öncelik sırasıyla)

1. **ADR güncellemeleri** — 7 madde. Kullanıcı bilerek erteledi. Kampanya
   boyunca ADR-004 `:277` ve `:499`'un yanlış/eksik tarif edildiği ölçüldü.
2. **Gerçek donanımda round-trip taraması** — 50 ms değeri SITL'de ölçüldü.
   Gerçek telemetri linkinde farklı olabilir. `tools/offboard_gap_sweep.py`
   aynen kullanılabilir. **Ayrı kapı.**
3. **≥2 başarısızlıklı rota tükenmesi ölçümü** — F2-a'dan kalan borç.
   Kullanıcı "zorlama" dedi, fırsat çıkarsa ölçülecek.
4. **`docs/TODO-offboard-start-kok-neden.md`** — içerik olarak bu iş
   tarafından karşılandı, silinebilir/kapatılabilir.

---

## DOKUNULMAYACAKLAR (kullanıcı kararı)

- Görev C / D / E4e
- `motion_fsm.py`
- **F1 guard** (`OFFBOARD_FAILURE_MAX_PER_TARGET = 3`, Seçenek A) — K6 önlem,
  guard sınırlayıcı; `0/150`'in %95 üst sınırı %2, sıfır değil.
- F2-a'nın rejoin mekanizması
- `motion_profile.enabled = false` — saha hover kalibrasyonu yapılmadan
  gerçek uçuş yok.
- Gerçek `EKF2_OF_CTRL` kararı ayrı bir kapı (SITL'de 1→0 yapıldı, gerçek
  param dosyasına dokunulmadı).

---

## ÇALIŞMA KURALLARI (bu oturumda teyit edilenler)

- **"FAZ 1 / sadece analiz" = geçici bile olsa HİÇBİR değişiklik yok.**
  Deneyip geri almak, hiç yapmamaktan farklı risk taşır (SITL paylaşılan
  durum tutuyor).
- **Push:** yalnızca açık "pushla" komutu. Başka hiçbir ifade sayılmaz.
- **İnternet:** git clone/pull, pip/brew install vb. öncesi
  "İNTERNET KULLANIM RAPORU" ver, dur, onay bekle.
- Her adım ayrı commit.
- Beklenmedik bir şey çıkarsa hemen dur ve raporla; sonraki koşuma geçme.

---

## OPERASYONEL NOTLAR (zaman kazandırır)

- Testler: `source .scripts/olds/v34/resolve_python.sh` sonra
  `cd v34_flight_stack && PYTHONPATH=$(pwd) "$PYTHON_BIN" -m pytest tests/ -q`
  — ~6.5 dk, 2 dk'lık varsayılan zaman aşımını aşar.
- Async testler **`@pytest.mark.asyncio` ister** (asyncio_mode ayarı yok).
- SITL: `./safe_sitl_launcher.sh`, hazır sinyali sim log'unda
  **"Ready for takeoff"** (~11 s). `gz topic -l` ile yoklama YAPMA —
  launcher'ın 3/6 yetim kontrolünü tetikler.
- **Ardışık koşumlar arasında** `clear_land_mode.py` şart (PX4 LAND'de
  takılı kalıp arm'ı reddediyor). **`resolve_python.sh` ile:** düz `python3`
  ile `ModuleNotFoundError: mavsdk` verir ve sessizce hiçbir şey yapmaz.
- Görev logları: `.scripts/olds/v34/logs/mission_<id>.jsonl`. Alan adı
  **`code`**, `event` değil. Anahtar kodlar: `OFFBOARD_SWITCH_CONFIRMED`,
  `OFFBOARD_SWITCH_FAILED`, `OFFBOARD_PURSUIT_ABANDONED`,
  `ROUTE_REJOIN_SKIPPED`.
- Taban çizgisi külliyatı: `.scripts/olds/v34/demo/runs/*/*/mission_*.jsonl`
  (59 koşum, 149 geçiş).
- Bir görev koşumu ~6–8 dk. Harness zaman aşımını 10 dk'ya kurma —
  5. koşumu bu düşürdü.
