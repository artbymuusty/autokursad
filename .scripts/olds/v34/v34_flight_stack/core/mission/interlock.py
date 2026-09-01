"""Yük bırakma sıra kilidi.

SPEC DEGISIKLIGI (2026-09-01). Bu modul onceden "Gorev 2 Rapor Bolum
11.1"deki kurali sekle BAGLI olarak uyguluyordu:

    _payload_1_released  # Mavi Altigen
    _payload_2_released  # Kirmizi Ucgen
    can_release_payload_2() -> _payload_1_released

Yani Kirmizi Ucgen'e yuk birakmak, Mavi Altigen'e birakilmis olmasina
KOSULLUYDU. Bunun gozlenen sonucu: hangi hedef once tespit edilirse
edilsin ILK birakma HER ZAMAN Mavi Altigen'e gidiyordu. Ucgen once
merkezlendiginde gorev2_orchestrator yerinde birakmayi atliyor ve
"toplu birakmada dogru sirada yapilacak" diyordu (12 kosunun 6'sinda
uclen once merkezlendi ve altisinda da bu atlama logda goruldu).

Bu, V33 spec madde 11 ile CELISIYOR:

    "Gorev sirasi sekle gore sabit degil. Ilk basari completed_count==0
     iken 1st_mission, ikinci basari completed_count==1 iken 2nd_mission.
     ... Mavi Altigen once veya Kirmizi Ucgen once tamamlanabilir."

Artik sira SEKILDEN degil TAMAMLANMA SIRASINDAN turuyor: hangi hedef
once tamamlanirsa o birinci, digeri ikincidir.

KORUNAN SEYLER:
  * Renk<->hedef eslemesi DEGISMEDI. RED payload <-> Mavi Altigen,
    BLUE payload <-> Kirmizi Ucgen; gz_payload_actuator.py'de "deliberate
    team assignment" olarak kayitli, dokunulmadi.
  * Ayni hedefe IKI KEZ birakma hala yazilim seviyesinde imkansiz
    (RuntimeError). Gercekten korunmaya deger degismez kosul buydu.

KALDIRILAN SEY: "ikinci birakma birinciden once olamaz" kapisi. O kapi
sekle bagliyken anlamliydi; sira tamamlanmadan turetilince kendiliginden
saglaniyor (once gelen zaten birincidir), yani vacuous hale geliyor.

ESKI GEREKCE HAKKINDA: kod eskiden bu kurali "Gorev 2 Rapor Bolum 11.1"e
dayandirip "KESINLIKLE gerceklestirilemez" diye tarif ediyordu, yani bir
YARISMA ZORUNLULUGU gibi. 2026-09-01'de dogrulandi: bu bir zorunluluk
DEGIL, onceden alinmis ve artik TERK EDILMIS bir tasarim tercihiydi.
Guncel davranis spec madde 11'e gore SIRA-BAZLIDIR ve sekle bagli
zorunluluk yoktur. Eski gerekce metni bu yuzden kaldirildi; burada
yalnizca tarihce olarak aniliyor ki eski loglari okuyan biri
"KESINLIKLE gerceklestirilemez" ifadesini hala gecerli sanmasin.
"""
from core.telemetry.event_bus import NULL_PUBLISHER, EventPublisher
from core.telemetry.events import Category, Event, Severity

# Renk esleme SABIT (gz_payload_actuator.py: "deliberate team assignment").
SHAPE_PAYLOAD_COLOR = {"MAVI_ALTIGEN": "RED", "KIRMIZI_UCGEN": "BLUE"}
REQUIRED_SHAPES = ("MAVI_ALTIGEN", "KIRMIZI_UCGEN")


class PayloadInterlock:
    def __init__(self, publisher: EventPublisher = NULL_PUBLISHER):
        self._order: list[str] = []          # tamamlanma sirasi
        self.publisher = publisher

    # -- sira tabanli API ------------------------------------------------
    def can_release(self, shape: str) -> bool:
        """Bu hedefe yuk birakilabilir mi?

        Tek engel: ayni hedefe daha once birakilmis olmasi. Sira kisiti
        YOK -- hangi hedef once gelirse o birincidir (V33 spec madde 11).
        """
        return shape not in self._order

    def is_terminal_release(self, shape: str) -> bool:
        """Bu birakma IKINCI (yani Gorev 2'yi bitiren) birakma mi?

        gorev2_fsm bunu tirmanis optimizasyonu icin kullaniyor; o
        optimizasyon SIRAYA bagli (terminal birakmadan sonra tirmanisi
        tuketen bir sey kalmiyor), SEKLE degil.
        """
        return shape not in self._order and len(self._order) == 1

    def mark_released(self, shape: str) -> None:
        if shape not in REQUIRED_SHAPES:
            raise ValueError(f"bilinmeyen hedef: {shape}")
        if shape in self._order:
            self.publisher.publish(Event(
                code="INTERLOCK_VIOLATION_BLOCKED", subsystem="PayloadInterlock",
                category=Category.PAYLOAD, severity=Severity.CRITICAL,
                message=f"{shape} icin IKINCI kez birakma denendi -- engellendi",
                data={"order": list(self._order)},
            ))
            raise RuntimeError(
                f"INTERLOCK IHLALI: {shape} hedefine zaten yuk birakildi, "
                f"ikinci kez birakilamaz")
        self._order.append(shape)
        ordinal = len(self._order)
        self.publisher.publish(Event(
            code=f"PAYLOAD_{ordinal}_RELEASED", subsystem="PayloadInterlock",
            category=Category.PAYLOAD,
            message=f"payload {ordinal} ({shape} / "
                    f"{SHAPE_PAYLOAD_COLOR[shape]} payload) released",
            data={"shape": shape, "ordinal": ordinal, "order": list(self._order),
                  "payload_1_released": self.payload_1_released,
                  "payload_2_released": self.payload_2_released},
        ))

    @property
    def release_order(self) -> list:
        return list(self._order)

    def both_released(self) -> bool:
        return len(self._order) == 2

    # -- ESKI API: SEKLE bagli okumalar (dashboard, gorev3) --------------
    # Bu iki ozellik SEKIL anlamini korur -- payload_1 = Mavi Altigen'in
    # RED yuku, payload_2 = Kirmizi Ucgen'in BLUE yuku. Sira bilgisi icin
    # release_order kullanilmalidir. Boylece mevcut okuyucularin hicbiri
    # degismek zorunda kalmadi.
    @property
    def payload_1_released(self) -> bool:
        return "MAVI_ALTIGEN" in self._order

    @property
    def payload_2_released(self) -> bool:
        return "KIRMIZI_UCGEN" in self._order

    def mark_payload_1_released(self) -> None:
        """Geriye donuk uyumluluk sarmalayicisi."""
        self.mark_released("MAVI_ALTIGEN")

    def mark_payload_2_released(self) -> None:
        """Geriye donuk uyumluluk sarmalayicisi."""
        self.mark_released("KIRMIZI_UCGEN")

    def can_release_payload_2(self) -> bool:
        """ESKI API. Artik SIRA kisiti icermez; yalnizca "Kirmizi Ucgen'e
        henuz birakilmadi mi" sorusunu cevaplar."""
        return self.can_release("KIRMIZI_UCGEN")
