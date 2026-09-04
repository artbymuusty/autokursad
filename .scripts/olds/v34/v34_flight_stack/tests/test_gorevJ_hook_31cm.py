"""GOREV J: kanca 31 cm geometrisi SDF'in kendisinden dogrulanir.

NEDEN VAR: kanca uzunlugu tek bir yerde yazmiyor -- hook_mount yuksekligi,
iki yarim ip ofseti, uc tam ip ofseti ve burun ofseti birlikte belirliyor.
S1 bunu 0.198 -> 0.250 m yaparken, J 0.250 -> 0.310 m yaparken degerler tek
tek elle guncellendi. Bir dahaki sefere biri unutulursa kanca sessizce
yanlis uzunlukta olur; MAGNET_DWELL_S de o uzunluktan olculen sarkac
periyoduna dayandigi icin hata gorunmeden yayilir. Bu test zinciri SDF'ten
yeniden toplayip beklenen sayilarla karsilastirir.
"""
import sdf_geometry


def test_kanca_ucu_base_linkin_31_cm_altinda():
    """base + 0.05 - (0.03692 + 3*0.07384 + 0.03692 + 0.06465) = base - 0.31001"""
    _, asagi = sdf_geometry.hook_chain_m()
    assert abs(asagi - 0.31001) < 1e-5, (
        "kanca ucu base_link'in %.5f m altinda; beklenen 0.31001" % asagi)


def test_ip_acikligi_4_segment_toplamidir():
    """Ip acikligi 4 x 0.07384 = 0.29536 m (25 cm'de 4 x 0.05884 = 0.23536)."""
    acik, _ = sdf_geometry.hook_chain_m()
    assert abs(acik - 0.29536) < 1e-5, (
        "ip acikligi %.5f m; beklenen 0.29536" % acik)


def test_uzatma_tam_6_cmdir():
    """S1'den J'ye fark ipe verildi: 0.23536 -> 0.29536, tam +0.060 m."""
    acik, _ = sdf_geometry.hook_chain_m()
    assert abs((acik - 0.23536) - 0.060) < 1e-5


def test_dwell_olculen_periyodun_yarisindan_buyuk():
    """MAGNET_DWELL_S saf salinim gecisini dislamali: dwell > T/2.

    Olculen periyot (GOREV J, 31 cm): medyan 1.078 s, en uzun 1.098 s.
    Salinan bir kanca yakalama penceresinde yarim periyottan uzun kesintisiz
    kalamaz, dolayisiyla dwell bu ust siniri asmali.
    """
    from core.mission.hook_seating import MAGNET_DWELL_S
    en_uzun_yarim_periyot = 1.098 / 2.0
    assert MAGNET_DWELL_S > en_uzun_yarim_periyot, (
        "dwell %.3f s, olculen en uzun yarim periyot %.3f s'den kucuk"
        % (MAGNET_DWELL_S, en_uzun_yarim_periyot))
