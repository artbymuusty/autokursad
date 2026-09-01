---
phase_id: PH-15S
date: 2026-08-24
title: S serisi SITL koşuları — mission aşamasına ulaşmayan 12 launch
commit: ~
status: closed
metrics:
  kosu_sayisi: 12
  mission_log_uretilen: 0
  ham_boyut_gb: 6.09
  ortalama_kosu_mb: 520
raw_artifacts:
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15_sitl_S0[1-9].log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15_sitl_S1[0-2].log"
---

# PH-15S — S serisi: mission aşamasına ulaşmayan 12 SITL launch'ı

## Amaç

`phase15_run.sh <RUN>` harness'ıyla koşulan S01–S12 serisinin ne ürettiğini
kayda geçirmek. Harness her koşuda iki dosya yazar: `p15_sitl_<RUN>.log`
(PX4/gz konsolu) ve `p15_mission_<RUN>.log` (görev tarafı).

## Değişiklikler

Yok — bu seri kod değişikliği içermiyor, harness koşularıdır.

## Test sonucu

**12 koşunun 12'sinde de `p15_mission_S*.log` ÜRETİLMEDİ.** Yalnızca SITL
konsol çıktısı var (6.09 GB). Yani hiçbiri görev aşamasına ulaşmadı; bu
serideki hiçbir dosya görev davranışı hakkında veri içermiyor.

## Başarısızlıklar

Serinin tamamı görev aşamasına ulaşamadı. Her dosya `Error 137` ile bitiyor —
**ancak bu bir başarısızlık göstergesi DEĞİL**: `phase15_run.sh`'ın kapatma
adımı `pkill -9` kullanıyor ve başarıyla tamamlanan A–F koşuları da aynı
`Error 137` imzasıyla bitiyor. Ayırt edici olgu, 137 değil, mission log'unun
**hiç oluşmamış** olmasıdır.

## Kök neden

**Belirlenemedi.** Hayatta kalan kanıt, launch'ın neden mission adımına
geçmediğini söylemiyor. `phase15_run.sh` satır 19'daki 60 denemelik launch
bekleme döngüsü hiç başarılı olmadıysa script satır 28'e (mission başlatma)
hiç ulaşmamış olur — ama bu **doğrulanmadı**, olası bir açıklamadır.

## Uygulanan çözüm

Yok. Seri terk edildi; ölçüm A–F koşularıyla (`PH-15`) yapıldı.

## Doğrulama

12 dosyanın her biri için ayrı ayrı doğrulandı: bitiş imzası `Error 137`,
karşılık gelen `p15_mission_S*.log` **yok**. A–F ve T serileriyle karşılaştırma
yapılarak 137'nin teardown imzası olduğu teyit edildi.

## Önemli metrikler

- Koşu: 12 (S01–S12)
- Mission log üretilen: **0/12**
- Ham boyut: **6.09 GB** (ortalama ~520 MB/koşu)
- Görev davranışı verisi: **yok**

## İlgili commit

Yok — `.scripts/olds/v33/` untracked; harness `phase15_run.sh` scratchpad'de.

## Sonraki adım

Bu seri **arşivlenmeli, silinmemeli**: kök neden belirlenmediği için, launch'ın
neden mission'a geçmediği ileride sorulursa tek kanıt bu konsol çıktılarıdır.
Sıkıştırılmış arşiv katmanı (`_archive/`) tam bu durum için var. Görev
davranışı sorusu için ise değeri yoktur — o veri `PH-15`'te.
