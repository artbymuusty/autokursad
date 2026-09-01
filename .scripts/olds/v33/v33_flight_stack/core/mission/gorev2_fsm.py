import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.navigation.centering_controller import CenteringController
from core.mission.interlock import PayloadInterlock
from core.position_log.position_store import PositionStore
from core.mission.payload_release import PayloadReleaseService
from core.config.parameters import MISSION_ALTITUDE_M
from core.telemetry.event_bus import NULL_PUBLISHER, EventPublisher
from core.telemetry.events import Category, Event, Severity

logger = logging.getLogger(__name__)


class PayloadMissionSequencer:
    """Kilitlenmiş bir hedefin yükünü bırakır.

    DİNAMİK SIRA (2026-08-24, operatör kararı):
    Bu sınıf 2026-08-13 revizyonunda "iki hedefi de bul, SONRA sabit
    sırada (Mavi Altıgen -> Kırmızı Üçgen) bırak" mantığındaydı. O sıra
    kuralı kaldırıldı (bkz. interlock.py). Artık sequencer bir SIRA
    ÇALIŞTIRICI değil, "şu anda kilitlenmiş hedefin yükünü bırak"
    arayüzüdür: execute_payload_mission_for(shape_type).

    Sıra artık TESPİT sırasını takip eder ve Gorev2Orchestrator'ın arama
    döngüsü tarafından belirlenir -- burada sabit bir sıra YOKTUR.

    execute_all() geriye dönük uyumluluk için korundu ama artık yalnızca
    "kalan hedefleri sırayla işle" anlamına gelir (bkz. kendi
    docstring'i)."""

    def __init__(self, flight: IFlightBackend, centering: CenteringController,
                 interlock: PayloadInterlock, position_store: PositionStore,
                 release_service: PayloadReleaseService, publisher: EventPublisher = NULL_PUBLISHER,
                 mission_v3_state=None):
        self.flight = flight
        self.centering = centering
        self.interlock = interlock
        self.position_store = position_store
        self.release_service = release_service
        self.publisher = publisher
        # Mission Flow V3 (F2, opsiyonel -- verilmezse aşağıdaki iki metod
        # tam olarak önceki davranışına döner, interlock.py'nin sıra kuralı
        # her iki yolda da AYNI kalır). Verilirse mark_hexagon_done/
        # mark_triangle_done zaten interlock'u kendi içinde çağırır --
        # burada AYRICA self.interlock.mark_payload_*_released() çağırmak
        # aynı event'i iki kez yayınlar, o yüzden ya biri ya diğeri.
        self.mission_v3_state = mission_v3_state

    def _publish(self, code, message="", severity=Severity.INFO, data=None):
        self.publisher.publish(Event(
            code=code, subsystem="PayloadMissionSequencer", category=Category.PAYLOAD,
            severity=severity, message=message, data=data or {},
        ))

    async def _navigate_to_recorded(self, shape_type: str) -> None:
        """Search sırasında kaydedilen GPS konumuna döner -- araç o an
        büyük olasılıkla İKİNCİ hedefin yakınındadır, kaydedilen konumda
        DEĞİL (bkz. CenteringController.goto_global_position_and_wait)."""
        tp = self.position_store.get(shape_type)
        if tp is None:
            raise RuntimeError(
                f"PayloadMissionSequencer: {shape_type} icin kayitli konum yok -- "
                "bu yalnizca both_required_targets_found() True iken cagrilmali."
            )
        converged = await self.centering.goto_global_position_and_wait(
            tp.gps_lat, tp.gps_lon, MISSION_ALTITUDE_M)
        if not converged:
            logger.warning(f"{shape_type} kayitli konumuna navigasyon zaman asimina ugradi -- "
                            "yine de devam ediliyor (best-effort).")

    _SLOT = {"MAVI_ALTIGEN": 1, "KIRMIZI_UCGEN": 2}

    async def execute_payload_mission_for(self, shape_type: str,
                                          navigate: bool = True) -> bool:
        """Verilen hedefin yükünü bırakır. Sıra ÇAĞIRAN tarafından
        belirlenir (2026-08-24 dinamik sıra kararı).

        `navigate=False`: araç hedefin üstünde kilitliyse kayıtlı GPS'e
        yeniden gitmeye gerek yoktur -- dinamik akışta bırakma tam
        kilitlenme anında, yerinde yapılır."""
        if shape_type not in self._SLOT:
            raise ValueError(f"Bilinmeyen hedef: {shape_type}")
        slot = self._SLOT[shape_type]
        logger.info("PAYLOAD MISSION %d basliyor (%s)", slot, shape_type)
        self._publish(f"PAYLOAD_MISSION_{slot}_STARTED")
        if navigate:
            await self._navigate_to_recorded(shape_type)
        result = await self.release_service.release_and_verify(shape_type)
        if self.mission_v3_state is not None:
            if shape_type == "MAVI_ALTIGEN":
                self.mission_v3_state.mark_hexagon_done()
            else:
                self.mission_v3_state.mark_triangle_done()
        elif shape_type == "MAVI_ALTIGEN":
            self.interlock.mark_payload_1_released()
        else:
            self.interlock.mark_payload_2_released()
        self.position_store.mark_payload_released(shape_type)
        self._publish(f"PAYLOAD_MISSION_{slot}_COMPLETE", data={"verified": result})
        return result

    async def execute_payload_mission_1(self) -> bool:
        """Geriye dönük uyumluluk: Mavi Altıgen'in yükünü bırakır.
        Artık "her zaman ilk" ANLAMINA GELMEZ -- yalnızca hangi hedef
        olduğunu söyler."""
        return await self.execute_payload_mission_for("MAVI_ALTIGEN")

    async def execute_payload_mission_2(self) -> bool:
        """Geriye dönük uyumluluk: Kırmızı Üçgen'in yükünü bırakır.
        ÖNKOŞUL YOK (2026-08-24)."""
        return await self.execute_payload_mission_for("KIRMIZI_UCGEN")

    async def execute_all(self) -> None:
        """HENÜZ BIRAKILMAMIŞ hedeflerin yükünü bırakır.

        Dinamik akışta bırakma zaten kilitlenme anında yapıldığı için bu
        normalde hiçbir şey yapmaz; yedek/telafi yoludur (ör. bir hedefin
        yükü herhangi bir sebeple bırakılmadan arama bittiyse). Sabit
        1->2 sırası KALDIRILDI: kalanlar kayıt sırasına göre işlenir."""
        if not self.position_store.both_required_targets_found():
            raise RuntimeError(
                "PayloadMissionSequencer.execute_all() cagrildi ancak iki hedef de "
                "henuz kayitli degil -- Search Phase invariant'i ihlal edildi."
            )
        for shape in ("MAVI_ALTIGEN", "KIRMIZI_UCGEN"):
            tp = self.position_store.get(shape)
            if tp is not None and not getattr(tp, "payload_released", False):
                await self.execute_payload_mission_for(shape)
