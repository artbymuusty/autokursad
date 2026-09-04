"""GOREV K / A: yarisma alanindaki dort seklin OLCUSU ve RENGI.

OPERATOR SPEC (2026-09-04), olculer KENAR uzunlugu cinsinden:
    Mavi Altigen 2 m   Mavi Kare 2 m   Kirmizi Ucgen 1 m   Kirmizi Kare 1 m
Ton referanslari: Kirmizi Ucgen (kirmiziler icin), Mavi Altigen (maviler icin).

NEDEN TEST: boyut iki yerde (visual mesh scale + collision box), renk dort
alanda (ambient/diffuse/specular/emissive) yaziyor. Elle guncellemede biri
unutulunca gorunen sekil ile carpisan sekil ayrisiyor ya da iki kirmizi
farkli tonda kaliyor -- ikisi de dedektoru sessizce etkiler.
"""
import math

import sdf_geometry


def test_kenar_uzunluklari_spec_ile_ayni():
    beklenen = {
        "blue_hexagon": 2.0,
        "blue_square": 2.0,
        "red_triangle": 1.0,
        "red_square": 1.0,
    }
    for ad, kenar_m in beklenen.items():
        kenar, _, _ = sdf_geometry.shape_model(ad)
        assert abs(kenar - kenar_m) < 1e-9, (
            "%s kenari %.4f m; beklenen %.4f m" % (ad, kenar, kenar_m))


def test_collision_footprint_visual_ile_ortusur():
    """Carpisan sekil, gorunen seklin ayak izini birebir tasimali."""
    kenar, _, kutu = sdf_geometry.shape_model("blue_hexagon")
    # duzgun altigen: kose-kose 2*kenar, duz-duz sqrt(3)*kenar
    assert abs(kutu[0] - 2 * kenar) < 1e-3
    assert abs(kutu[1] - math.sqrt(3) * kenar) < 2e-3

    kenar, _, kutu = sdf_geometry.shape_model("blue_square")
    assert abs(kutu[0] - kenar) < 1e-9 and abs(kutu[1] - kenar) < 1e-9

    kenar, _, kutu = sdf_geometry.shape_model("red_square")
    assert abs(kutu[0] - kenar) < 1e-9 and abs(kutu[1] - kenar) < 1e-9

    kenar, _, kutu = sdf_geometry.shape_model("red_triangle")
    assert abs(kutu[0] - kenar) < 1e-9
    assert abs(kutu[1] - math.sqrt(3) / 2 * kenar) < 2e-3


def test_kirmizi_kare_tonu_ucgenden_kopyalanmis():
    _, ucgen, _ = sdf_geometry.shape_model("red_triangle")
    _, kare, _ = sdf_geometry.shape_model("red_square")
    assert kare == ucgen, "kirmizi kare tonu ucgenle ayni degil: %r != %r" % (kare, ucgen)


def test_mavi_kare_tonu_altigenden_kopyalanmis():
    _, altigen, _ = sdf_geometry.shape_model("blue_hexagon")
    _, kare, _ = sdf_geometry.shape_model("blue_square")
    assert kare == altigen, "mavi kare tonu altigenle ayni degil: %r != %r" % (kare, altigen)
