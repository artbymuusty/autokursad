# Koşu kayıtları — makine üretimi, olgu-only

Bu dizindeki `.md` dosyalarını `tools/run_record.py` üretir. Her mission ve
her pytest oturumu bittiğinde **otomatik** oluşurlar.

## Ne içerirler

Yalnızca olay kaydından **türetilebilen olgular**: faz zinciri, health
geçişleri, WARN/CRITICAL/FATAL olaylar, merkezleme sonuçları, payload
olayları, olay sayımları, tespit edilen şekiller ve hangi ham dosyalardan
üretildikleri.

## Ne içermezler — ve neden

`phase_id`, Amaç, Değişiklikler, **Kök neden**, Uygulanan çözüm, Doğrulama,
İlgili commit, Sonraki adım. Bu alanlar için **boş başlık bile** yazılmaz.

Gerekçe kayıtlıdır: 2026-08-25'te S serisi koşularının `Error 137` ile
bitmesi "12 başarısız koşu" diye yorumlanacaktı; A–F koşularıyla
karşılaştırınca bunun **normal teardown imzası** (`pkill -9`) olduğu ortaya
çıktı. Bir makine bu çıkarımı yapamazdı. Ayrıca `.scripts/olds/v33/` git'te
untracked olduğu için "İlgili commit" alanına yazılacak doğru bir değer
**yoktur** — repo HEAD'ini yazmak aktif olarak yanlış olurdu.

## Güvenlik sözleşmesi

Koşu kayıtları bu **alt dizinde** yaşar. `artifact_retention.py::load_summaries()`
`os.listdir` ile yalnızca `docs/test-history/` üst seviyesindeki `.md`
dosyalarını okur, alt dizinlere inmez. Dolayısıyla bir koşu kaydı **hiçbir
koşulda** doğrulanmış özet sayılamaz ve **hiçbir ham veriyi silinebilir
yapamaz**. Bu otomasyon kanıt kapısını gevşetmez; yalnızca phase özeti
yazmayı mekanik hale getirir.

## Akış

    koşu biter → runs/<id>.md (otomatik, olgu)
                      ↓ kaynak olarak okunur
              PH-*.md (insan/agent yazar, yorum + yargı)
                      ↓ verify'dan geçer
              ham veri ARCHIVABLE olur

## Devre dışı bırakma

`KURSAD40_NO_RUN_RECORD=1` ortam değişkeni pytest kancasını susturur.
