# Bekleyen görev — ADR'lerdeki hatalı varsayımların düzeltilmesi

**Durum:** NOT DÜŞÜLDÜ, öncelik değil (operatör kararı, 2026-09-04).
**Kaynak:** `docs/gorevF-mode-gecisi-analiz.md` bölüm 6 + D5 + EK 2.
**Kural:** ADR'ler bu görevde **değiştirilmedi**; aşağısı yalnızca tespittir.

| # | ADR / konum | hatalı varsayım | ölçüm |
|---|---|---|---|
| 1 | **ADR-009** `:151`, `:184-188` ve **ADR-010** `:257`, `:270-283` | `OFFBOARD_SWITCH_FAILED`'ın nedeni "pause, resume'dan ~1 s sonra düşüyor, PX4 OFFBOARD'ı reddediyor" | Popülasyonda çürüdü: hata oranı <2 s / 2–6 s / >6 s boşluklarda %20/%29/%26 (n=242). Önerdiği çare (`OFFBOARD_AFTER_RESUME_SETTLE_S`) uygulandı, oran oynamadı (%26.1 → %20.3). **Ayrıca EK 2:** ortada reddetme yok, komut hiç gönderilmiyor |
| 2 | **ADR-010 R2** `:295` | `MISSION_RESUME_MIN_INTERVAL_S` 15→6 gerekçesi: "`OFFBOARD_SWITCH_FAILED` 4→0" | **n=1** (tek koşum) ve tekrarlanmıyor: o günden beri 250 denemede 61 hata |
| 3 | **ADR-004 §17** `:492-493` | "re-enter SEARCHING, let debounce/track-ready re-qualify **naturally**" — yeniden nitelenmenin yavaş olduğu | Ölçüm: **101 ms** (üç koşumda 100–102 ms). `TargetValidator` streak'i hiç sıfırlanmadığı için yavaşlatıcı **hiç var olmamış**. Politika, `:499`'un yasakladığı blind retry'ye dönüşüyor |
| 4 | **ADR-004 §17** `:277` (`WAITING_OFFBOARD_MODE_ACTIVE`) | "PX4 mode-change **rejection**'ı yakala ve yüzeye çıkar" | 68 olayın **0'ı** reddetme. **Konusu da yok**: EK 2'ye göre OFFBOARD komutu PX4'e hiç ulaşmıyor. Doğru istek: "onay sırasında gözlenen modu ve duraklamadan geçen süreyi yayınla" — bu ① ile **uygulandı** |
| 5 | **ADR-009 D3** `:87-91` | Cap/cooldown'ın takip başarısızlıklarını kapsadığı | Offboard-hatası sınıfını **kapsamıyor**; cooldown yazarı (`_note_centering_failure`) **üretimde çağrılmıyor**. Gönderilen `CENTERING_RETRY_COOLDOWN_S` **5.0**, ADR'de 10.0 |
| 6 | **ADR-008 B0** `:53-62` / **ADR-009 D1** `:63-75` | `flight_mode`'un "değişim güdümlü, sessizlik normal" olduğu — `TELEMETRY_STALE_AFTER_FLIGHT_MODE_S = 3.0`'ın dayanağı | Ölçüm: **düzenli 1 Hz akış** (`observed_hz` ∈ {0.1, 0.9, 1.0, 1.1}), diğer akışlar 10 Hz |
| 7 | **Külliyat geneli** | — | ADR'ler **2026-08-17'de duruyor**. F1/F2/F3'e hükmeden üç karar (2026-08-21, 08-29, 09-02/03) yalnızca **kod yorumlarında** belgeli. ADR süreci koda ayak uyduramamış |

**Öneri:** 3, 4 ve 7 birlikte ele alınırsa ADR-004 §17 tutarlı hâle gelir;
1 ve 2 birlikte ADR-009/010'un `OFFBOARD_SWITCH_FAILED` anlatısını düzeltir.
5 ve 6 tek satırlık tashihler.
