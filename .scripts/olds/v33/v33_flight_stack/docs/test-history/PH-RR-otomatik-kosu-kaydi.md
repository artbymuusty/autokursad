---
phase_id: PH-RR
date: 2026-08-25
title: Otomatik koşu kaydı (runs/) — akış özeti mimarisi
commit: ~
status: closed
metrics:
  test_toplam: 719
  run_record_testi: 22
  canli_kosu_olay_sayisi: 2558
  ham_to_kayit_orani: "2.0 MB -> 6681 bayt"
  backfill_kapsama: "126 MB ham -> 604 KB, 57 tarihsel koşu"
  tasarim_revizyonu: 2
raw_artifacts:
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/live_sitl.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/live_mission.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/live_wrap.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/record_sitl.log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/record_mission.log"
  - "../logs/mission_d18fc518f894.jsonl"
  - "../logs/mission_20260825_190855.log"
  - "../logs/mission_20260825_190008.log"
---

# PH-RR — Otomatik koşu kaydı (runs/)

## Amaç

Phase özeti yazımını elle olmaktan çıkarmak. PH-15/PH-15S/PH-Y2 özetlerini ham
log okuyup doğrulayarak elle yazmıştım; yeni koşular için bu işin
otomatikleşmesi istendi. Onaylanan tasarım (2026-08-25): **Seçenek A** (ham log
korunur) + koşu başına makine kaydı + insan roll-up + makine kaydının insan
yargısı alanlarını **hiç içermemesi**.

## Değişiklikler

`tools/run_record.py` (452 satır, yeni), `conftest.py` kök `pytest_sessionfinish`
kancası (56 satır, yeni), `run_mission_v33_{gz,dual,real}.sh` iki adımlı kanca,
`docs/test-history/runs/README.md`, `retention.config.json`'da
`recent_keep_days: 3 → 1`. Eşikler ve altı cleanup şartı değişmedi.

## Test sonucu

Canlı mission koşusunda launcher kancası kendiliğinden tetiklendi:

```
[RUN_RECORD] docs/test-history/runs/d18fc518f894.md (2558 olay, terminal=MISSION_FAILED)
```

2.0 MB ham `.jsonl` → 6.681 bayt olgu. Kayıtta yalnızca altı başlık var (Faz
zinciri, Health geçişleri, Merkezleme sonuçları, WARN+ olaylar, Tespit edilen
şekiller, Olay sayımları); yedi yasak yorum alanı ve `phase_id`/`commit`
anahtarları grep ile tek tek yokluğu doğrulandı.

Backfill 57 tarihsel koşuyu kayda geçirdi: **126 MB ham → 604 KB**, ikinci
çağrıda hiçbir şey yapmıyor (idempotent).

## Başarısızlıklar

**İlk tasarım canlı koşuda başarısız oldu.** Kanca launcher'ın son satırına
konmuştu; koşu bitti, hiçbir kayıt oluşmadı.

Testlerin yakaladığı ikinci kusur: `unrecorded_jsonls()` kaydı **dosya
adından**, `build_mission_record()` ise **olay gövdesinden** türetiyordu.
Üretimde ikisi hep aynı, ama ayrışırlarsa backfill aradığını asla bulamaz ve
her çağrıda aynı kaydı yeniden üretirdi.

## Kök neden

**(a)** Launcher shell'ine sinyal gönderildiğinde (Ctrl-C, kill) script son
satıra hiç ulaşmıyor. Operatörün mission'ı Ctrl-C ile durdurması normal bir
bitiş biçimi olduğundan, en çok ilgilenilen koşular tam da kayıtsız kalanlar
olurdu. `trap` ile düzeltme denendi; stub ölçümünde kabuk sinyal semantiği
**iki koşuda farklı davrandı** (bir kez trap hemen ateşledi ve `$?` yanlıştı,
bir kez normal yol işledi) ve `setsid` macOS'te bulunmadığından gerçek Ctrl-C
(süreç grubu) senaryosu izole edilemedi.

**(b)** İki ayrı türetme kaynağının uyuşmasına bağlı yakınsama — tek anahtar
yerine iki kaynağın anlaşmasına güvenmek.

## Uygulanan çözüm

**(a)** Tasarım sinyalden **bağımsız** hale getirildi. Kayıt zaten tamamen
diskteki `.jsonl`'den türetildiği için çıkış anında üretilmek zorunda değil.
Launcher artık **başta** `--backfill` (eksik kalan ne varsa tamamlar),
**sonda** best-effort çalıştırıyor. En kötü durumda kayıt bir sonraki koşuda
oluşur, asla kaybolmaz. Doğrulanamayan bir kabuk davranışının üzerine
güvenilirlik inşa etmek yerine ona hiç bağlı olmayan bir yol seçildi.

**(b)** `run_id` tek anahtara — dosya adına — bağlandı.

## Doğrulama

Canlı launcher koşusu kaydı otomatik üretti (yukarıdaki çıktı). **719 test**
geçiyor (önceki 714 + 5 yeni backfill testi); `run_record` için 22 test.
Yakınsama testi: dosya adı ile olay gövdesi çeliştiğinde bile backfill ikinci
çağrıda duruyor. Çıkış kodu her iki yönde korunuyor (başarısız mission 1,
başarılı 0, kanca patlasa bile maskelemiyor) — stub ile ölçüldü.

Güvenlik sözleşmesi iki testle sabitlendi: koşu kaydı özet listesine sızmıyor,
ve kayıt varken bile artifact `COMPLETED` (özetsiz) kalıyor.

## Önemli metrikler

- Test: **719 passed** (`run_record`: 22, toplam yeni: 5)
- Canlı koşu: 2558 olay, 146.8 s, terminal `MISSION_FAILED`
- Sıkıştırma: 2.0 MB → 6.681 bayt (~300:1); backfill 126 MB → 604 KB (~200:1)
- Tasarım revizyonu: 2 (son-satır → trap → sinyalden bağımsız)
- `recent_keep_days`: 3 → 1 (diğer eşikler ve altı şart değişmedi)

## İlgili commit

Yok — `.scripts/olds/v33/` git'te untracked.

## Sonraki adım

Bu fazın koşuları **1.3 GB** ham SITL log'u üretti ve bu özetle artık temsil
ediliyorlar. Kapsamsız kalan eski veri: `sitl*.log` ailesi (~8.0 GB, 08-23),
`p15_sitl_SH*` serisi (2.4 GB) ve `insp_sitl.log`. Bunlara özet **yazılmadı**
— ne test ettikleri doğrulanamadı, tahminle özet yazmak sistemin güvenlik
özelliğini bozardı. Arşivlenebilmeleri için önce ne oldukları belirlenmeli.
