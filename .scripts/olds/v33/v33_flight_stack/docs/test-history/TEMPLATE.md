---
phase_id: PH-XX
date: 2026-08-25
title: Kısa başlık
commit: ~
status: draft
metrics: {}
raw_artifacts: []
---

# PH-XX — Kısa başlık

## Amaç

Bu test/phase neyi öğrenmek için koşuldu. Bir-iki cümle.

## Değişiklikler

Bu phase'de koda/konfigürasyona ne değişti. Değişmediyse "Yok — yalnızca ölçüm."

## Test sonucu

Ne oldu. Geçti/kaldı değil, ne gözlendi.

## Başarısızlıklar

Neler başarısız oldu. Hiçbiri olmadıysa "Yok." yazın — boş bırakmayın.

## Kök neden

Başarısızlığın gerçek nedeni. Bilinmiyorsa bunu açıkça yazın.

## Uygulanan çözüm

Ne yapıldı. Yapılmadıysa neden yapılmadığı.

## Doğrulama

Çözümün işe yaradığı NASIL doğrulandı. Doğrulanmadıysa bunu yazın.

## Önemli metrikler

Sayılar. Süre, oran, deneme sayısı, boyut.

## İlgili commit

Commit SHA'ları / dosya yolları. Yoksa "Yok — commit'lenmemiş çalışma."

## Sonraki adım

Bundan sonra ne yapılmalı.

---

<!--
raw_artifacts: BU ÖZETİN HANGİ HAM VERİDEN ÜRETİLDİĞİ.
Frontmatter'daki listeye glob veya tam yol yazın, repo köküne göreli:
  raw_artifacts:
    - "../logs/mission_20260824_2354*.log"
    - "/private/tmp/claude-501/-Users-muusty/<session>/scratchpad/p15_sitl_*.log"

Bu liste temizlik güvenliğinin 5. şartıdır: bir artifact'in hangi özet
tarafından temsil edildiğinin kaydı. Liste boşsa hiçbir ham veri bu özete
bağlanmaz ve hiçbir şey silinemez.

tools/artifact_retention.py verify ile bu dosyayı doğrulayın.
-->
