"""
Mission Flow V3 — F0 (state/config iskeleti). Bu dosya, mevcut PositionStore/
PayloadInterlock'un taşımadığı iki yeni veri parçasını tanımlar: 5m'deki
"payload_ortalama" ara-konum kaydı ve bu konumun 1st_mission/2nd_mission
etiketiyle ilişkilendirilmiş görünümü.

Bilinçli olarak PositionStore/TargetPoint'in yerini almaz -- onları sarar
(mission_v3_state.py). Ayrı bir paralel state sistemi kurmamak, F0
kararının (mevcut mekanizmaları genişletme) doğrudan sonucudur.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GpsPos:
    lat: float
    lon: float
    rel_alt_m: float
    timestamp_utc: str  # ISO-8601


@dataclass(frozen=True)
class MissionSlot:
    """Mission Flow V3 §2 Görev A/B adım 7: bir görevin 5m konumu, hangi
    sırada tamamlandığına göre "1st_mission"/"2nd_mission" etiketiyle."""
    label: str          # "1st_mission" | "2nd_mission"
    shape: str           # "MAVI_ALTIGEN" | "KIRMIZI_UCGEN"
    pos_5m: GpsPos | None
    completed_at_utc: str
