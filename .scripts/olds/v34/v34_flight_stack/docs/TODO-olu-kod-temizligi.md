# Bekleyen görev — `GOREV3_APPROACH_ALTITUDE_M` ölü kod temizliği

**Durum:** SIRAYA ALINDI, şimdi değil (operatör kararı, 2026-09-06).
Üç açık konudan birine geçildiğinde, ayrı ve küçük bir temizlik olarak
ele alınacak.
**Kaynak:** Görev T (SETUP.md fresh-clone doğrulaması, commit `e23a9cb0`)
sırasında tespit edildi.
**Kural:** Görev T'de **hiçbir kod değiştirilmedi**; aşağısı yalnızca
tespittir ve kapsamı ölçülmüştür.

## Tespit

Görev S, yaklaşma irtifasını sabit sayı olmaktan çıkarıp
`_approach_altitude_m()` ile türetilen değere geçirdi:

    low_alt_vision_limit(rect_class) + GOREV3_APPROACH_VISION_MARGIN_M
      = 0.50 + 0.08 = 0.58 m

Eski sabit `GOREV3_APPROACH_ALTITUDE_M = 0.30` **hiçbir yerde
kullanılmıyor** ama hâlâ tanımlı ve üç dosyada import ediliyor. Dosyayı
okuyan biri 0.30'u yürürlükteki değer sanar.

## Kapsam — dört nokta, ölçüldü

| # | Yer | Ne var | Yapılacak |
|---|---|---|---|
| 1 | [`core/config/parameters.py:184`](../core/config/parameters.py#L184) | `GOREV3_APPROACH_ALTITUDE_M: float = 0.30` — tanım | Kaldır |
| 2 | [`core/mission/gorev3_pickup.py:27`](../core/mission/gorev3_pickup.py#L27) | import listesinde; gövdede **hiç kullanılmıyor** (kalan tüm geçişler yorum satırı) | Import'tan çıkar |
| 3 | [`tests/test_gorev3_pickup.py:14`](../tests/test_gorev3_pickup.py#L14) | import; dosyada **tek geçiş**, hiçbir testin gövdesinde kullanılmıyor | Import'tan çıkar |
| 4 | [`core/mission/visual_alignment.py:310-318`](../core/mission/visual_alignment.py#L310) | `align()` docstring'i **bayat**: "Gorev 3 passes GOREV3_APPROACH_ALTITUDE_M (0.30), which means the visual alignment actually runs at 0.30 m" | 0.58 m'ye ve türetim formülüne göre düzelt |

**Asıl değeri olan madde 4'tür.** 1–3 lint seviyesinde ölü koddur; 4 ise
Görev O'da (2026-09-05) doğru yazılmış, Görev S'te (2026-09-06) yanlışa
dönüşmüş ve okuyanı **aktif olarak yanlış yönlendiren** bir docstring'dir.

## Dokunulmayacaklar

`docs/gorevK-D-probe-devir2.md`, `docs/gorevK-adaptif-alcalma-faz1.md`,
`docs/gorevO-gorsel-hizalama-darbogaz-analiz.md`,
`docs/DEVIR-2026-09-06-gorevS-sonrasi.md` ve `gorev3_pickup.py`'nin
`:52`, `:1818`, `:1920` yorumları sabiti **tarihsel kayıt** olarak anıyor.
Bunlar o günün doğru tespitidir, **değiştirilmeyecek**.

## Kabul ölçütü

- `grep -rn GOREV3_APPROACH_ALTITUDE_M --include="*.py"` yalnızca
  `gorev3_pickup.py`'nin tarihsel yorum satırlarını döndürmeli.
- Test paketi düşmemeli (referans: 659 passed, 1 skipped).
- `SETUP.md` §12.7'deki "artık kullanılmıyor" notu, sabit kaldırıldığında
  güncellenmeli (not artık gereksizleşir).
