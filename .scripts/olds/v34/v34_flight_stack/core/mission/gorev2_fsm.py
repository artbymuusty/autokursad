import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.navigation.centering_controller import CenteringController
from core.mission.interlock import PayloadInterlock
from core.position_log.position_store import PositionStore
from core.mission.payload_release import PayloadReleaseService
from core.config.parameters import (
    MISSION_ALTITUDE_M, GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M,
)
from core.telemetry.event_bus import NULL_PUBLISHER, EventPublisher
from core.telemetry.events import Category, Event, Severity

logger = logging.getLogger(__name__)


class PayloadMissionSequencer:
    """Görev 2 Rapor (operatör revizyonu, 2026-08-13, "Mission Lifecycle"
    yeniden yapılandırması) -- eski Gorev2DurumMachine'in (DURUM-1..4,
    hangi hedefin ÖNCE tespit edildiğine göre dallanan mantık) yerini alır.

    Yeni kural: Mission (Search Phase) ASLA yük bırakma işlemi yapmaz --
    yalnızca iki hedefi de tespit edip PositionStore'a kaydeder. Hangi
    hedefin önce bulunduğu artık ÖNEMLİ DEĞİL: payload sırası HER ZAMAN
    sabittir -- önce Payload Mission 1 (Mavi Altıgen / RED payload), sonra
    Payload Mission 2 (Kırmızı Üçgen / BLUE payload) -- ve bu yalnızca
    Search Phase TAMAMEN bittikten (PositionStore.both_required_targets_found()
    True olduktan) SONRA, Offboard'ın tek yetkili olduğu evrede çalışır.

    PayloadInterlock ARTIK SIRA KISITI UYGULAMAZ (2026-09-01). Eskiden
    "payload_2, payload_1'den önce asla bırakılamaz" garantisi vardı; o
    garanti sırayı ŞEKLE bağlıyordu ve gözlenen sonucu, hangi hedef önce
    tespit edilirse edilsin ilk bırakmanın hep Mavi Altıgen'e gitmesiydi.
    Spec madde 11 bunu yasakladığı için kaldırıldı. Interlock'un koruduğu
    tek değişmez koşul artık aynı hedefe İKİ KEZ bırakılamamasıdır."""

    def __init__(self, flight: IFlightBackend, centering: CenteringController,
                 interlock: PayloadInterlock, position_store: PositionStore,
                 release_service: PayloadReleaseService, publisher: EventPublisher = NULL_PUBLISHER):
        self.flight = flight
        self.centering = centering
        self.interlock = interlock
        self.position_store = position_store
        self.release_service = release_service
        self.publisher = publisher

    def _publish(self, code, message="", severity=Severity.INFO, data=None):
        self.publisher.publish(Event(
            code=code, subsystem="PayloadMissionSequencer", category=Category.PAYLOAD,
            severity=severity, message=message, data=data or {},
        ))

    async def _navigate_to_recorded(self, shape_type: str) -> None:
        """Search sırasında kaydedilen GPS konumuna döner -- araç o an
        büyük olasılıkla İKİNCİ hedefin yakınındadır, kaydedilen konumda
        DEĞİL.

        CLIMB-THEN-CRUISE (2026-09-02): bu bacak artık goto_waypoint()
        kullanıyor, goto_global_position_and_wait() değil. İkisinin sözleşmesi
        aynı (imza ve dönüş anlamı); fark, eskisinin hedefe mutlak 3B pozisyon
        setpoint'i gönderip X/Y/Z'yi birlikte hareket ettirmesi, yenisinin ise
        dikey ile yatayı zamanda ayırmasıdır. motion_profile.enabled False
        iken goto_waypoint zaten eski davranışa düşer.

        Bu, Görev 2'nin İKİ payload bacağının da geçtiği tek navigasyon
        noktası -- Climb-then-Cruise'un bu PR'daki tek adopter'ı kasıtlı
        olarak burası. Görev 3 fazları ve dönüş bacağı eski yolda kaldı."""
        tp = self.position_store.get(shape_type)
        if tp is None:
            raise RuntimeError(
                f"PayloadMissionSequencer: {shape_type} icin kayitli konum yok -- "
                "bu yalnizca both_required_targets_found() True iken cagrilmali."
            )
        converged = await self.centering.goto_waypoint(
            tp.gps_lat, tp.gps_lon, MISSION_ALTITUDE_M)
        if not converged:
            logger.warning(f"{shape_type} kayitli konumuna navigasyon zaman asimina ugradi -- "
                            "yine de devam ediliyor (best-effort).")

    async def execute_payload_mission_1(self) -> bool:
        """Mavi Altıgen'e (RED payload) bırakma.

        "her zaman ilk" DEGIL (2026-09-01): sira artik tespit sirasindan
        turuyor, bkz. interlock.py. Bu metot yalnizca HEDEFI belirler;
        kacinci birakma oldugunu interlock soyler."""
        logger.info("PAYLOAD MISSION 1 basliyor (Mavi Altigen / RED payload)")
        self._publish("PAYLOAD_MISSION_1_STARTED")
        await self._navigate_to_recorded("MAVI_ALTIGEN")
        # TIRMANIS: terminal (ikinci) birakmadan sonra 15 m'ye geri tirmanisi
        # TUKETEN hicbir sey kalmiyor. Bu SIRAYA bagli bir optimizasyon,
        # SEKLE degil -- eskiden yalnizca mission_2'de vardi cunku ikinci
        # olmak sekle sabitlenmisti.
        terminal = self.interlock.is_terminal_release("MAVI_ALTIGEN")
        result = await self.release_service.release_and_verify(
            "MAVI_ALTIGEN",
            **({"climb_back_alt_m": GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M}
               if terminal else {}))
        self.interlock.mark_released("MAVI_ALTIGEN")
        self.position_store.mark_payload_released("MAVI_ALTIGEN")
        self._publish("PAYLOAD_MISSION_1_COMPLETE", data={"verified": result})
        return result

    async def execute_payload_mission_2(self) -> bool:
        """Kırmızı Üçgen'e (BLUE payload) bırakma.

        "her zaman ikinci" DEGIL (2026-09-01): onkosul kaldirildi, cunku
        o onkosul sirayi SEKLE sabitliyordu ve V33 spec madde 11 bunu
        yasakliyor. Ucgen once merkezlenirse birinci birakma budur."""
        logger.info("PAYLOAD MISSION 2 basliyor (Kirmizi Ucgen / BLUE payload)")
        self._publish("PAYLOAD_MISSION_2_STARTED")
        await self._navigate_to_recorded("KIRMIZI_UCGEN")
        # TERMİNAL bırakma: bundan sonra Görev 2 biter ve master_fsm doğrudan
        # Görev 3'e devreder; Görev 3'ün ilk komutu GOREV3_TRANSIT_ALTITUDE_M =
        # 1.5 m'dir. Varsayılan MISSION_ALTITUDE_M (15 m) geri tırmanışını
        # TÜKETEN hiçbir şey kalmadığı için ölçülen ~13.2 m tırmanış + ~13.2 m
        # alçalma / ~9 s tamamen boşa gidiyordu. Payload 1 (yukarıdaki) bilerek
        # dokunulmadan bırakıldı: oradaki tırmanış rota devamı ve ikinci hedefin
        # aranması tarafından gerçekten tüketiliyor.
        terminal = self.interlock.is_terminal_release("KIRMIZI_UCGEN")
        result = await self.release_service.release_and_verify(
            "KIRMIZI_UCGEN",
            **({"climb_back_alt_m": GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M}
               if terminal else {}))
        self.interlock.mark_released("KIRMIZI_UCGEN")
        self.position_store.mark_payload_released("KIRMIZI_UCGEN")
        self._publish("PAYLOAD_MISSION_2_COMPLETE", data={"verified": result})
        return result

    async def execute_all(self) -> None:
        """Henuz birakilmamis payload gorevlerini calistirir. Yalnizca
        Search Phase TAMAMEN bittiğinde (both_required_targets_found())
        çağrılmalıdır -- çağıran taraf (Gorev2Orchestrator) bu invariant'ı
        garanti eder; burada da savunma amaçlı yeniden doğrulanır."""
        if not self.position_store.both_required_targets_found():
            raise RuntimeError(
                "PayloadMissionSequencer.execute_all() cagrildi ancak iki hedef de "
                "henuz kayitli degil -- Search Phase invariant'i ihlal edildi."
            )
        # SEBEKE: yalnizca HENUZ birakilmamis hedefler calistirilir.
        # Onceden ikisi de kosulsuz cagriliyordu; bu, eski interlock'ta
        # zararsizdi cunku yerinde birakma yalnizca MAVI_ALTIGEN icin
        # olabiliyordu ve mark_payload_1_released() cift cagriyi sessizce
        # yutuyordu. Artik yerinde birakma HER IKI hedef icin de mumkun
        # (2026-09-01 sira duzeltmesi) ve interlock ayni hedefe ikinci
        # birakmayi RuntimeError ile engelliyor -- dolayisiyla burada
        # atlama ZORUNLU.
        if self.interlock.can_release("MAVI_ALTIGEN"):
            await self.execute_payload_mission_1()
        else:
            logger.info("Toplu birakma: MAVI_ALTIGEN zaten birakilmis, atlaniyor.")
        if self.interlock.can_release("KIRMIZI_UCGEN"):
            await self.execute_payload_mission_2()
        else:
            logger.info("Toplu birakma: KIRMIZI_UCGEN zaten birakilmis, atlaniyor.")
