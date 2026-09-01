# Test History — Phase Index

Bu dosya **index**tir, kayıt değildir. `docs/adr/README.md` ile aynı rolü oynar:
hiçbir teknik iddianın kaynağı değildir, yalnızca kayıtları işaret eder.

## Ajanlar için okuma protokolü

1. **Önce bu index'i oku.**
2. Yalnızca ilgili phase'in özetine git.
3. Ham log arama. Ham log **kalıcı hafıza değildir** — arşivlenmiş veya silinmiş
   olabilir. Bir özette olmayan bilgi, o testten öğrenilmemiş sayılır.

Ham veriye gerçekten ihtiyaç varsa: özetin `raw_artifacts` alanı hangi dosyalardan
üretildiğini söyler; `_archive/` altında hâlâ duruyor olabilir, yoksa
`cleanup-history.md` ne zaman ve hangi özet karşılığında kaldırıldığını gösterir.

## Neden var

SITL/test koşuları gigabyte'larca konsol çıktısı üretir. Ölçülen olgu ise
kilobyte'larca metindir. Bu dizin ikincisini kalıcı tutar, birincisini geçici
sayar:

    RAW TEST DATA = geçici        TEST KNOWLEDGE = kalıcı

## Yaşam döngüsü

    ACTIVE → COMPLETED → ANALYZED → SUMMARIZED → VERIFIED → ARCHIVABLE → PURGED

Durum bir state dosyasında **tutulmaz**, her çağrıda diskteki kanıttan hesaplanır
(`tools/artifact_retention.py`):

| Durum | Kanıt |
|---|---|
| `ACTIVE` | bir süreç dosyayı açık tutuyor **veya** mtime `active_grace_seconds` içinde |
| `COMPLETED` | yazım bitmiş, hiçbir özet kapsamıyor |
| `ANALYZED` | bir özetin `raw_artifacts`'ı kapsıyor, ama özet dosyası bulunamıyor |
| `SUMMARIZED` | özet var, doğrulama bekliyor |
| `VERIFIED` | özet zorunlu alan doğrulamasından geçti |
| `ARCHIVABLE` | `VERIFIED` **+** recent-retention penceresi dışında |
| `PURGED` | kaldırıldı; yalnızca özet + `cleanup-history.md` içinde yaşıyor |

**Hiçbir ham veri, kendisinden türetilen özet doğrulanmadan silinemez.**

## Kurallar

- Özet yazmak **insan/agent** işidir. Araç özet **yazmaz**, yalnızca "doğrulanmış
  bir özet var mı" sorusunu cevaplar.
- Bir özet, `TEMPLATE.md`'deki on `##` bölümünün hepsini doldurmalıdır. Boş
  bölüm = doğrulama başarısız = temsil ettiği ham veri **silinemez**.
- "Yok." geçerli bir cevaptır (bilinçli beyan). "TODO", "-", "TBD" değildir.
- Claude'un `/tmp` scratchpad'i **proje hafızası değildir**. Oraya hiçbir kalıcı
  bilgi yazılmaz; yalnızca temizlik kapsamındadır.

## Dosyalar

| Dosya | Ne |
|---|---|
| `README.md` | bu index |
| `TEMPLATE.md` | yeni phase özeti şablonu |
| `PH-*.md` | phase özetleri (kalıcı bilgi) |
| `cleanup-history.md` | temizlik denetim kaydı (araç üretir, elle düzenlenmez) |
| `retention.config.json` | eşikler ve izlenen kökler |
| `_archive/` | sıkıştırılmış ham veri (ara katman) |
| `runs/` | **otomatik koşu kayıtları** (makine üretimi, olgu-only — özet değil) |

## Komutlar

```bash
cd .scripts/olds/v33/v33_flight_stack
python3 tools/artifact_retention.py scan     # ne var, hangi durumda
python3 tools/artifact_retention.py verify   # özetler geçerli mi
python3 tools/artifact_retention.py plan     # ne yapılacak (yazma yok)
python3 tools/artifact_retention.py apply --dry-run --yes
python3 tools/artifact_retention.py apply --yes
```

---

## INDEX

Yeni phase eklerken bu tabloya bir satır ekleyin.

| Phase | Tarih | Başlık | Sonuç | Özet |
|---|---|---|---|---|
| `PH-15` | 2026-08-24 | Görev 3 uçtan uca SITL matrisi (A–F) | 6/6 koşuda attach-timeout yok; koşu B'de FLEX-20 envelope reddi | [PH-15](PH-15-gorev3-sitl-matrisi.md) |
| `PH-15S` | 2026-08-24 | S serisi — mission aşamasına ulaşmayan 12 launch | 0/12 mission log; kök neden belirlenemedi | [PH-15S](PH-15S-sitl-kosulari-mission-asamasiz.md) |
| `PH-RR` | 2026-08-25 | Otomatik koşu kaydı (runs/) — akış özeti mimarisi | **Kuruldu**: canlı koşuda kanca tetiklendi, 719 test | [PH-RR](PH-RR-otomatik-kosu-kaydi.md) |
| `PH-CAM` | 2026-08-25 | Kamera akışı yok — tek atışlık topic keşfi yarışı | **Düzeltildi**: vision HEALTHY, 30 FPS | [PH-CAM](PH-CAM-vision-topic-discovery-race.md) |
| `PH-Y2` | 2026-08-24 | Dinamik sıra — "üçgen önce" SITL'de üretilemedi | Altıgen 3/3; üçgen senaryosu üretilemedi (**açık risk**) | [PH-Y2](PH-Y2-dinamik-sira-ucgen-once.md) |

## Mevcut test workflow'una bağlantı

Yeni bir mekanizma eklenmedi; mevcut akışa iki adım eklendi:

1. **Test koş** — değişmedi (`run_mission_v33_gz.sh`, SITL harness'ları).
2. **Özeti yaz** — `TEMPLATE.md`'yi kopyalayıp doldur, `raw_artifacts`'a hangi
   ham dosyalardan üretildiğini yaz, index'e bir satır ekle.
3. **Doğrula** — `python3 tools/artifact_retention.py verify`.

Adım 2 artık boş sayfadan başlamıyor: her koşu bittiğinde
`runs/<id>.md` otomatik üretilir (bkz. [runs/README.md](runs/README.md)).
Faz zinciri, health geçişleri ve WARN+ olaylar orada hazırdır; phase
özetine yalnızca **yorum ve yargı** eklemek kalır.

Testler mevcut pytest ağacına bağlıdır (`tools/tests/`), ayrı bir koşucu yok:

```bash
python3 -m pytest tests/ gz_system/tests/ tools/tests/
```
