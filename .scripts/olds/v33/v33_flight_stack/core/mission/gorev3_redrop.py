import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.navigation.centering_controller import CenteringController
from core.position_log.position_store import PositionStore
from payload import PayloadManager
from payload.errors import PayloadCalibrationError
from core.config.parameters import GOREV3_DESCENT_ALTITUDE_M

logger = logging.getLogger(__name__)

class Gorev3RedropPhase:
    """Görev 3 Rapor Bölüm 7 (operatör revizyonu, 2026-08-13): "İkinci yük
    bırakma konumunda; Araç tekrar 30 cm irtifaya alçalacaktır. Son
    merkezleme tamamlandıktan sonra GRAB SERVO ... yük hedef konuma
    bırakılacaktır." No alignment/retreat sequence needed here (unlike
    pickup) -- reuses CenteringController.go_to_and_center's staged
    descend-and-center primitive, same one Görev 2's payload drops use
    (core/mission/payload_release.py), rather than the previous hand-rolled
    IPayloadVisibilityStrategy-based approach that gorev3_pickup.py now owns
    instead."""

    def __init__(self, flight: IFlightBackend, payload_manager: PayloadManager,
                 position_store: PositionStore, centering: CenteringController,
                 mission_v3_state=None):
        self.flight = flight
        self.payload_manager = payload_manager
        self.position_store = position_store
        self.centering = centering
        # DINAMIK (2026-08-24): 2nd_mission sabit KIRMIZI_UCGEN degil.
        self.mission_v3_state = mission_v3_state

    def _second_mission_shape(self) -> str:
        """2nd_mission'in sekli; mission_v3_state yoksa eski sabite duser."""
        if self.mission_v3_state is not None:
            shape = self.mission_v3_state.second_mission_shape
            if shape is not None:
                return shape
        return "KIRMIZI_UCGEN"

    async def run(self) -> bool:
        logger.info("Görev 3 Faz 3 (Yeniden Bırakma) Başlatıldı.")

        target_shape = self._second_mission_shape()
        logger.info("Gorev 3 birakma hedefi: 2nd_mission=%s", target_shape)
        kirmizi_ucgen_point = self.position_store.get(target_shape)
        if kirmizi_ucgen_point is None:
            raise RuntimeError(f"{target_shape} konumu bulunamadı! Görev 3 Faz 3 başlatılamaz.")

        converged = await self.centering.go_to_and_center(target_shape, altitude_m=GOREV3_DESCENT_ALTITUDE_M)
        if not converged:
            logger.warning("Son merkezleme yakınsamadı -- yine de bırakma denenecek (best-effort).")

        logger.info("Taşınan yük bırakma mekanizması aktifleşiyor...")
        # PHASE 6.5: IPayloadActuator.activate_drop_mechanism() yerine
        # payload/PayloadManager.release() -- V33: SERVO3_RELEASE ardından
        # SERVO2_REVERSE (2./son kullanım). Eski çağrının dönüşü ATILIYORDU,
        # yani run() koşulsuz True dönüyordu ve orchestrator'daki
        # `if not redrop_ok` dalı ulaşılamazdı; artık sonuç bağlayıcı.
        #
        # Real yolun bilinen boşluğu pickup ile aynı şekilde ele alınır
        # (bkz. gorev3_pickup.py::_run_payload_pickup docstring'i).
        try:
            result = await self.payload_manager.release()
        except (PayloadCalibrationError, NotImplementedError) as e:
            logger.error("Yük bırakma durduruldu: gerçek donanım payload yolu henüz "
                         "hazır değil (kalibrasyon/sensör entegrasyonu Phase 17 "
                         "bekliyor). Ayrıntı: %s", e)
            return False

        if not result.success:
            logger.error("Yük bırakma başarısız: %s (state=%s)",
                         result.error_reason, result.final_state.value)
            return False

        # KASITLI: success=True iken final_state STOW_FAILED olabilir --
        # payload fiziksel olarak bırakıldı ama mekanizma toplanamadı
        # (payload_manager.py 2026-08-22 kararı). Bu görevi düşürmez, ama
        # sessiz de kalmaz.
        if result.error_reason:
            logger.warning("Yük bırakıldı ama ikincil anomali var: %s (state=%s)",
                           result.error_reason, result.final_state.value)

        logger.info("Görev 3 Faz 3 Başarılı (state=%s).", result.final_state.value)
        return True
