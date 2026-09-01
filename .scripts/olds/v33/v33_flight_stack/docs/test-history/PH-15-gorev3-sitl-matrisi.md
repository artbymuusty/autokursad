---
phase_id: PH-15
date: 2026-08-24
title: Görev 3 uçtan uca SITL matrisi (koşu A–F)
commit: ~
status: closed
metrics:
  kosu_sayisi: 6
  catch_payload_timeout: 0
  envelope_kapisi_reddi: 1
  duzeltme_oncesi: "A, B, C"
  duzeltme_sonrasi: "D, E, F"
raw_artifacts:
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15_sitl_[A-F].log"
  - "/private/tmp/claude-501/-Users-muusty/980520ef-e135-405a-b43f-d63fbd0e2d33/scratchpad/p15_mission_[A-F].log"
---

# PH-15 — Görev 3 uçtan uca SITL matrisi (koşu A–F)

## Amaç

`KNOWN_ISSUES §5`'te kayıtlı **HookAttachSystem attach-timeout** güvenilirlik
sorununu ölçmek. Phase 7 log incelemesinde gözlenen oran ~6 koşuda 1'di ve
"tek koşuyla geçti denmemeli, tekrarlı koşu/istatistiksel oran olarak ele
alınmalı" diye kaydedilmişti.

## Değişiklikler

Koşular iki gruba ayrıldı: **A/B/C** bir düzeltme öncesi, **D/E/F** sonrası.
Düzeltmenin kendisi bu özetin kapsamı dışında; burada kayıtlı olan ölçümdür.

## Test sonucu

6 uçtan uca SITL koşusunun **hiçbirinde `[CATCH_PAYLOAD_TIMEOUT]` görülmedi.**
Ham log'a karşı doğrulandı: altı `p15_mission_*.log` dosyasında da eşleşme
sayısı sıfır.

## Başarısızlıklar

Tek alma başarısızlığı **koşu B**'de görüldü ve bu attach-timeout değil,
**FLEX-20 envelope kapısı** reddiydi. Ham log doğrulaması: envelope/FLEX-20
eşleşmesi yalnızca `p15_mission_B.log`'ta (1 kez), diğer beş koşuda 0.

## Kök neden

Attach-timeout için kök neden **belirlenmedi ve bu madde kapatılmadı.**
Doğrulanmamış açıklama: ~6'da 1 oranı legacy
`gz_payload_actuator::_await_attach` yolunda gözlenmişti; o yol
`/hook/state` aboneliğini publish'ten SONRA açıyor ve latch'siz tek-seferlik
onayı yapısal olarak kaçırabiliyor. Yeni `payload/` yolu (`GzHookClient`)
aboneliği mission bootstrap'ında açtığı için o yarışı barındırmıyor.

## Uygulanan çözüm

Bu phase'de attach-timeout'a çözüm uygulanmadı — ölçüm phase'iydi.

## Doğrulama

6 koşu, ~6'da 1'lik bir oranı ayırt etmek için **yeterli örneklem değildir**
(beklenen olay sayısı ~1; sıfır gözlemek şansla tamamen tutarlı). Bu nedenle
`KNOWN_ISSUES §5` **açık bırakıldı**. Legacy yol hâlâ Görev 2'de kullanımda.

## Önemli metrikler

- Koşu sayısı: 6 (A/B/C düzeltme öncesi, D/E/F sonrası)
- `[CATCH_PAYLOAD_TIMEOUT]`: **0/6**
- FLEX-20 envelope reddi: **1/6** (koşu B)
- Phase 5.5 referans ölçümü: attach isteği → `ATTACHED` arası **2.485 ms**

## İlgili commit

Yok — `.scripts/olds/v33/` git'te untracked. Kanıt `KNOWN_ISSUES.md §5`
"GÜNCELLEME (2026-08-24, Phase 15 ölçümü)" bölümünde.

## Sonraki adım

Phase 15 test matrisi attach-timeout oranını **tekrarlı koşuyla ölçmeye devam
etmeli**. 6 koşu yetersiz; oranı ayırt etmek için daha büyük örneklem gerekir.
