"""GOREV N/C -- dashboard SERVO DURUM paneli.

Panel bir OLCUM gostermiyor; olay akisindan yapilmis bir CIKARIM gosteriyor.
Bu testler o cikarimin dogru olaylardan yapildigini ve panelin kendi
sinirlari icinde kaldigini kilitler.
"""
import inspect

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
D = pytest.importorskip("tools.mission_dashboard_unified")


def _st(events):
    st = D.MissionState()
    for e in events:
        st.apply(e)
    return st


# --------------------------------------------------------------------------
# Durum cikarimi
# --------------------------------------------------------------------------

def test_baslangicta_hepsi_pasif():
    st = D.MissionState()
    assert [st.servo[k]["active"] for k in ("1", "2", "3")] == [False, False, False]
    assert st.servo["1"]["label"] == "ORTA"
    assert st.servo["3"]["label"] == "ACIK"


def test_servo1_birakirken_AKTIF_sonra_ortaya_doner():
    st = _st([{"code": "PAYLOAD_MISSION_1_STARTED"},
              {"code": "PAYLOAD_RELEASE_REQUESTED"}])
    assert st.servo["1"]["active"] is True
    assert st.servo["1"]["label"] == "SOL"
    st.apply({"code": "PAYLOAD_RELEASED"})
    assert st.servo["1"]["active"] is False
    assert st.servo["1"]["label"] == "ORTA"


def test_servo1_ikinci_yuk_SAG():
    st = _st([{"code": "PAYLOAD_MISSION_2_STARTED"},
              {"code": "PAYLOAD_RELEASE_REQUESTED"}])
    assert st.servo["1"]["label"] == "SAG"


def test_servo2_sarkitip_salim_acik_kaliyor():
    st = _st([{"code": "GOREV3_PICKUP_STEP", "message": "hook_offset_applied"}])
    assert st.servo["2"]["label"] == "SARKITIYOR" and st.servo["2"]["active"] is True
    st.apply({"code": "GOREV3_PICKUP_STEP", "message": "vertical_descent_start"})
    assert st.servo["2"]["label"] == "SALIM ACIK" and st.servo["2"]["active"] is False


def test_servo2_salimi_raporundan_okuyor():
    st = _st([{"code": "HOOK_SEATING_RESULT", "message": "not_seated",
               "data": {"payout_m": 0.33}}])
    assert st.servo["2"]["label"] == "SALIM ACIK"
    assert "0.330" in st.servo["2"]["detail"]


def test_servo3_miknatis_cekerken_aktif_oturunca_KAVRADI():
    st = _st([{"code": "MAGNET_ATTRACTION_ACTIVE"}])
    assert st.servo["3"]["active"] is True and st.servo["3"]["label"] == "ACIK"
    st.apply({"code": "HOOK_SEATING_RESULT", "message": "seated", "data": {}})
    assert st.servo["3"]["label"] == "KAVRADI"
    assert "0 deg" in st.servo["3"]["detail"]


def test_her_satir_KAYNAK_OLAYI_tasiyor():
    """Gosterilen durumun nereden geldigi ekranda okunabilmeli -- yoksa panel
    sessizce yaniltabilir."""
    st = _st([{"code": "PAYLOAD_RELEASED"}])
    assert st.servo["1"]["src"] == "PAYLOAD_RELEASED"


# --------------------------------------------------------------------------
# YENI OLAY KAYNAGI ICAT EDILMEDI
# --------------------------------------------------------------------------

def test_panel_YALNIZCA_zaten_yayinlanan_olaylari_okuyor():
    """Operator sarti: yeni bir event kaynagi icat etme.

    Panelin tukettigi her kod, gorev katmaninda GERCEKTEN yayinlaniyor
    olmali."""
    # Yayin noktalari tek modulde degil: birakma olaylari orkestratorlerde
    # de uretiliyor. Testin dar bir dosya listesine bakmasi, kodu degil
    # TESTIN VARSAYIMINI sinar -- bu yuzden gorev agacinin tamami taraniyor.
    import pathlib
    kok = pathlib.Path(inspect.getsourcefile(D)).resolve().parents[1]
    mission_src = ""
    for f in (kok / "core").rglob("*.py"):
        mission_src += f.read_text(encoding="utf-8", errors="ignore")
    tuketilen = {
        "PAYLOAD_MISSION_1_STARTED", "PAYLOAD_MISSION_2_STARTED",
        "PAYLOAD_RELEASE_REQUESTED", "PAYLOAD_RELEASED",
        "PAYLOAD_RELEASE_CONFIRMED", "PAYLOAD_1_RELEASED", "PAYLOAD_2_RELEASED",
        "GOREV3_PICKUP_STEP", "HOOK_SEATING_RESULT", "MAGNET_ATTRACTION_ACTIVE",
        "GOREV3_PICKUP_EXHAUSTED", "GOREV3_PICKUP_ABORT",
    }
    panel_src = inspect.getsource(D.MissionState._apply_servo)
    for code in tuketilen:
        if code not in panel_src:
            continue
        # Gorev katmaninda ya da orkestratorlerde yayinlanmali.
        assert code in mission_src, \
            f"{code} panelde okunuyor ama gorev katmaninda hic yayinlanmiyor"


# --------------------------------------------------------------------------
# Yerlesim ve cizim
# --------------------------------------------------------------------------

def test_panel_minimap_ile_status_ARASINDA():
    lay = D.Layout(1920, 1080)
    assert lay.servo_y == lay.map_h, "servo paneli minimap'in hemen altinda degil"
    assert lay.servo_y + lay.servo_h + lay.status_h == lay.H, \
        "kolon yuksekligi tutmuyor -- status kirpilmis olabilir"
    assert lay.servo_h > 0 and lay.map_h > 0


def test_cizim_panel_SINIRLARI_disina_tasmiyor():
    """Ilk yazimda kaynak olay kodu 7*len/2 ile TAHMIN ediliyordu ve panelin
    sag kenarindan tasiyordu. Artik cv2.getTextSize ile olculuyor."""
    st = _st([{"code": "GOREV3_PICKUP_EXHAUSTED"},
              {"code": "MAGNET_ATTRACTION_ACTIVE"},
              {"code": "PAYLOAD_RELEASE_CONFIRMED"}])
    lay = D.Layout(1920, 1080)
    img = np.zeros((lay.H, lay.W, 3), np.uint8)
    D.draw_servos(img, lay.col_x, lay.servo_y, lay.col_w, lay.servo_h, st)
    # Panelin SAGINDAKI serit tamamen bos kalmali (cizim tasmadi).
    # cv2.rectangle kenari x0+w'ye DAHIL cizer (panel cercevesi). Tasma
    # kontrolu bu yuzden +1'den baslar.
    sag = img[lay.servo_y:lay.servo_y + lay.servo_h,
              lay.col_x + lay.col_w + 1: lay.col_x + lay.col_w + 41]
    assert int(sag.max()) == 0, "servo paneli kendi genisliginin disina cizdi"
    # Panelin kendisi bos da olmamali.
    icerik = img[lay.servo_y:lay.servo_y + lay.servo_h,
                 lay.col_x: lay.col_x + lay.col_w]
    assert int(icerik.max()) > 0
