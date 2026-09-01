"""
Mission Flow V3 — F0 (state/config iskeleti, uçuş YOK).

Mevcut PayloadInterlock (core/mission/interlock.py) ve PositionStore
(core/position_log/position_store.py) etrafında ince bir sarmalayıcı.
Yeni bir paralel state sistemi KURMAZ -- F0 kararı (bkz. konuşma geçmişi)
mevcut, test edilmiş mekanizmaları genişletmekti.

DİNAMİK SIRA (2026-08-24, operatör kararı):
Bu dosya eskiden "1st_mission HER ZAMAN MAVI_ALTIGEN" diyordu, çünkü
PayloadInterlock sabit bir bırakma sırası dayatıyordu. O kural
kaldırıldı (bkz. interlock.py docstring'i) ve V33 spec md.6/11'in tarif
ettiği davranışa geçildi: hangi şekil önce tespit edilip işlenirse onun
yükü önce bırakılır, ve 1st_mission/2nd_mission etiketleri o GERÇEK
sırayı yansıtır.

Bu yüzden mission_order artık hexagon_done/triangle_done bayraklarından
TÜRETİLMİYOR -- bırakma anında kaydedilen gerçek sıradan okunuyor
(_completion_order). Spec md.11: "İlk başarı completed_count==0 iken
1st_mission, ikinci başarı completed_count==1 iken 2nd_mission."
"""
from __future__ import annotations

import datetime
from typing import Optional

from core.mission.interlock import PayloadInterlock
from core.mission.mission_v3_types import GpsPos, MissionSlot
from core.telemetry.event_bus import NULL_PUBLISHER, EventPublisher
from core.telemetry.events import Category, Event, Severity

HEXAGON_SHAPE = "MAVI_ALTIGEN"
TRIANGLE_SHAPE = "KIRMIZI_UCGEN"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class MissionV3State:
    """Mission Flow V3 §2'deki paylaşılan state: `hexagon_done`,
    `triangle_done`, `completed_count`, `rectangle_scan_enabled`,
    `mission_order`, ve Görev A/B adım 2'deki 5m `payload_ortalama`
    ara-konumları."""

    def __init__(
        self,
        interlock: PayloadInterlock,
        publisher: EventPublisher = NULL_PUBLISHER,
    ):
        self._interlock = interlock
        self._publisher = publisher
        self._payload_ortalama: dict[str, GpsPos] = {}
        self._completed_at_utc: dict[str, str] = {}
        # GERCEK tamamlanma sirasi (2026-08-24). mission_order artik
        # bundan okunuyor; hexagon_done/triangle_done bayraklarindan
        # TURETILMIYOR -- bayraklar hangi sekil oldugunu soyler, SIRAYI
        # degil.
        self._completion_order: list[str] = []

    # ------------------------------------------------------------ okuma

    @property
    def hexagon_done(self) -> bool:
        return self._interlock.payload_1_released

    @property
    def triangle_done(self) -> bool:
        return self._interlock.payload_2_released

    @property
    def completed_count(self) -> int:
        return int(self.hexagon_done) + int(self.triangle_done)

    @property
    def rectangle_scan_enabled(self) -> bool:
        """Mission Flow V3 §1: sadece completed_count==2 olunca True."""
        return self.completed_count == 2

    @property
    def allowed_shape_classes(self) -> frozenset[str]:
        """F1 (Vision Dry-Run): arama fazında hangi Detection.shape_type
        değerlerinin adayı sayılacağı. rectangle_scan_enabled=False iken
        dikdörtgen sınıfları (KIRMIZI_DIKDORTGEN/MAVI_DIKDORTGEN) hariç
        tutulur -- bu iki sınıf yalnızca payload_release.py'nin doğrulama
        adımında ayrıca aranır (bkz. VERIFICATION_MARKER), Faz 1 arama
        döngüsünün ilgi alanı değildir."""
        base = frozenset({HEXAGON_SHAPE, TRIANGLE_SHAPE})
        if self.rectangle_scan_enabled:
            return base | frozenset({"KIRMIZI_DIKDORTGEN", "MAVI_DIKDORTGEN"})
        return base

    def filter_candidates(self, detections) -> list:
        """detections: Iterable[Detection]. allowed_shape_classes'a göre
        süzülmüş liste döner -- Faz 1 arama döngüsünün gerçek Detection
        nesneleriyle veya testteki sentetik nesnelerle aynı şekilde
        çalışır (sadece .shape_type attribute'u okunur)."""
        allowed = self.allowed_shape_classes
        return [d for d in detections if d.shape_type in allowed]

    _LABELS = ("1st_mission", "2nd_mission")

    @property
    def mission_order(self) -> dict[str, MissionSlot]:
        """Tamamlanan görevlerin 1st_mission/2nd_mission etiketli görünümü.

        DİNAMİK (2026-08-24): etiketler GERÇEK tamamlanma sırasından gelir,
        şekle göre sabit DEĞİLDİR. Kırmızı Üçgen önce tamamlanırsa
        1st_mission = KIRMIZI_UCGEN olur. Henüz tamamlanmamış bir görev
        sözlükte hiç yer almaz."""
        return {self._LABELS[i]: self._slot(self._LABELS[i], shape)
                for i, shape in enumerate(self._completion_order)}

    @property
    def first_mission_shape(self) -> Optional[str]:
        """Görev 3'ün döneceği hedefin şekli -- yoksa None.
        Görev 3 bunu okur, artık MAVI_ALTIGEN varsaymaz."""
        return self._completion_order[0] if self._completion_order else None

    @property
    def second_mission_shape(self) -> Optional[str]:
        """Görev 3'ün yükü bırakacağı hedefin şekli -- yoksa None."""
        return self._completion_order[1] if len(self._completion_order) > 1 else None

    def _slot(self, label: str, shape: str) -> MissionSlot:
        return MissionSlot(
            label=label,
            shape=shape,
            pos_5m=self._payload_ortalama.get(shape),
            completed_at_utc=self._completed_at_utc.get(shape, ""),
        )

    def get_payload_ortalama(self, shape_type: str) -> Optional[GpsPos]:
        return self._payload_ortalama.get(shape_type)

    # ------------------------------------------------------------ yazma

    def record_payload_ortalama(self, shape_type: str, gps: GpsPos) -> None:
        """Görev A/B adım 2: 5m'deki merkezleme konumunu kaydet. Final
        bırakma konumundan (PositionStore.try_save) AYRI bir kayıt --
        Görev 3'ün "1st_mission'ın 5m konumuna dön" adımı bunu okur."""
        self._payload_ortalama[shape_type] = gps
        self._publisher.publish(Event(
            code="PAYLOAD_ORTALAMA_RECORDED", subsystem="MissionV3State",
            category=Category.NAVIGATION,
            message=f"{shape_type} payload_ortalama @ {gps.rel_alt_m}m",
            data={"shape_type": shape_type, "pos_5m": gps.__dict__},
        ))

    def mark_hexagon_done(self) -> None:
        """Mavi Altıgen'in yükü bırakıldı. ÖNKOŞUL YOK (2026-08-24):
        ilk de ikinci de olabilir; etiket gerçek sıradan gelir."""
        self._record_done(HEXAGON_SHAPE, self._interlock.mark_payload_1_released)

    def mark_triangle_done(self) -> None:
        """Kırmızı Üçgen'in yükü bırakıldı. ÖNKOŞUL YOK (2026-08-24):
        sıra kuralı kaldırıldı, bu ilk de olabilir."""
        self._record_done(TRIANGLE_SHAPE, self._interlock.mark_payload_2_released)

    def _record_done(self, shape: str, mark_interlock) -> None:
        """Ortak yol: etiket GERÇEK sıradan türer (spec md.11 --
        completed_count==0 iken 1st_mission). Aynı şekil iki kez
        işaretlenirse sıraya İKİ KEZ eklenmez."""
        mark_interlock()
        if shape not in self._completion_order:
            self._completion_order.append(shape)
        label = self._LABELS[self._completion_order.index(shape)]
        self._completed_at_utc[shape] = _utc_now()
        self._publish_success(shape, label)

    def _publish_success(self, shape: str, label: str) -> None:
        pos_5m = self._payload_ortalama.get(shape)
        self._publisher.publish(Event(
            code="GOREV_V3_SUCCESS", subsystem="MissionV3State",
            category=Category.PAYLOAD, severity=Severity.INFO,
            message=f"{label} ({shape}) tamamlandı, completed_count={self.completed_count}",
            data={
                "completed_count": self.completed_count,
                "label": label,
                "shape": shape,
                "pos_5m": pos_5m.__dict__ if pos_5m else None,
                "rectangle_scan_enabled": self.rectangle_scan_enabled,
            },
        ))
