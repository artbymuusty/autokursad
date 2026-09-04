"""
Görev 3 Rapor Bölüm 5 (operatör revizyonu, 2026-08-13): IPayloadVisibilityStrategy'nin
ilk gerçek implementasyonu. UnimplementedVisibilityStrategy'nin kendi
docstring'i bunun "kapsam dışı, burada icat edilecek bir şey değil"
olduğunu söylüyordu -- ancak operatör artık Görev 3 algoritmasını bizzat
tanımladığı için bu yetkilendirilmiş bir kapsam genişlemesidir, icat edilen
bir mimari değil.

Kullanım: Gorev3PickupPhase, Kırmızı Dikdörtgen'e (1. yükün bırakıldığı
şekil) dik yaklaşım için bu stratejiyi kullanır -- 'SequentialReferenceStrategy'
tarzı (bkz. IPayloadVisibilityStrategy docstring): önce GPS ile Mavi Altıgen
konumuna gidilir, ardından yalnızca kamera/dikdörtgen'e bakılarak son
hizalama yapılır. compute_alignment_yaw tek referanslıdır (yalnızca
target.rotation_deg kullanılır) -- locate_carried_payload bu tasarımda
gerekli değildir, her zaman None döner.
"""
import logging
from typing import Optional

import numpy as np

from core.detection.types import Detection
from core.interfaces.i_payload_visibility_strategy import IPayloadVisibilityStrategy

logger = logging.getLogger(__name__)


class RectangleAlignmentStrategy(IPayloadVisibilityStrategy):
    """Aranan yuk dikdortgeni ARTIK SABIT DEGIL (GOREV I / A+B).

    KUSUR, canli olculdu (B1 kosumu, 2026-09-04): bu sinif her zaman
    KIRMIZI_DIKDORTGEN ariyordu. Altigene KIRMIZI, ucgene MAVI yuk
    birakildigi icin UCGEN ONCE birakildiginda alma hedefi ucgen olur ve
    aranmasi gereken sinif MAVI_DIKDORTGEN'dir. O kosumda faz, dogru
    hedefe gidip YANLIS SINIFI aradi ve transit_complete'ten 8.6 s sonra
    "bulunamadi" ile dustu -- dis deneme dongusu hic calisamadi.

    Gorev3PickupPhase, run() icinde rengi cozdukten sonra
    `set_rect_class()` ile aranan sinifi bildirir. Bildirilmezse
    varsayilan KIRMIZI_DIKDORTGEN kalir (eski davranis).
    """

    def __init__(self, rect_class: str = "KIRMIZI_DIKDORTGEN"):
        self._rect_class = rect_class

    def set_rect_class(self, rect_class: str) -> None:
        self._rect_class = rect_class

    async def locate_target(self, detector, camera_frame: np.ndarray) -> Detection:
        """Yukun dikdortgenini bu karede arar. Bulunamazsa RAISE eder --
        çağıran taraf (Gorev3PickupPhase) bir sonraki karede tekrar dener,
        tıpkı go_to_and_center()'ın kendi 'hedef kayboldu' döngüsü gibi."""
        detections = await detector.detect(camera_frame)
        for d in detections:
            if d.shape_type == self._rect_class:
                return d
        raise RuntimeError(f"{self._rect_class} bu karede bulunamadi")

    async def locate_carried_payload(self, detector, camera_frame: np.ndarray) -> Optional[Detection]:
        """Bu tasarımda kullanılmaz -- dik yaklaşım hizalaması yalnızca
        hedefin kendi yönelimine (target.rotation_deg) dayanır, ikinci bir
        referansa ihtiyaç duymaz."""
        return None

    async def compute_alignment_yaw(self, target: Detection, payload: Optional[Detection]) -> float:
        """target.rotation_deg, sabit nadir kamera montajı nedeniyle GÖVDE
        eksenlerine göre ölçülmüş uzun kenar açısıdır (bkz.
        HSVContourDetector._detect_rectangle). Dik yaklaşım için +90 derece
        döndürülür.

        DÖNÜŞ DEĞERİ GÖRECELİDİR (mutlak pusula yönü DEĞİL) -- aracın
        MEVCUT yaw'ına (flight.get_yaw_deg()) eklenmesi çağıranın
        sorumluluğundadır. Dik yaklaşım simetriktir (uzun kenarın hangi
        ucundan yaklaşıldığı önemsizdir), bu yüzden sonuç en kısa dönüşü
        veren [-90, 90) aralığına normalize edilir."""
        if target.rotation_deg is None:
            raise RuntimeError(
                "target.rotation_deg is None -- detector bu tespit için yönelim saglamadi "
                "(yalnızca dikdörtgen tespitlerinde dolu olur, ucgen/altigen icin degil)."
            )
        perpendicular_deg = target.rotation_deg + 90.0
        return ((perpendicular_deg + 90.0) % 180.0) - 90.0
