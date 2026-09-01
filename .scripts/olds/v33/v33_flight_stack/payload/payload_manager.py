"""PHASE 0 (Mimari Freeze): tek public API.

MissionManager (veya eşdeğeri) SADECE bu sınıfın 4 davranışsal komutunu
(catch_box_down/grapple/catch_box_up/release) ve read-only get_state()
sorgusunu çağırır -- hiçbir zaman servo/joint/gazebo seviyesinde kod
çağırmaz. Aktif backend (Real/Gazebo) constructor'da enjekte edilir;
PayloadManager backend seçimini kendisi yapmaz.

Bu sınıf üç şeyi bir araya getirir:
  * payload_state.py::PayloadStateMachine -- her komutun state geçişlerini
    doğrular (illegal sıralama sessizce yutulmaz, IllegalPayloadTransitionError
    fırlatır).
  * payload/models/hook_behavior_model.py::HookBehaviourModel -- backend'e
    "ne durumdayız?" diye sorar.
  * payload_config.py -- her zaman aşımı bütçesini FLEX-XX sabitlerinden
    okur.

TASARIM KARARI -- zaman aşımı governance'ı: PayloadBackend'in action
primitifleri (deploy/await_capture/grapple/retract/release/stow) HİÇBİRİ
kendi timeout'unu yönetmez -- PayloadManager her çağrıyı
`asyncio.wait_for(..., timeout=<FLEX sabiti>)` ile sarmalar. Bir FLEX
sabiti henüz TBD (None) ise `timeout=None` asyncio.wait_for'da "süresiz
bekle" anlamına gelir (Python'ın belgelenmiş, güvenli davranışı) -- bu,
kalibre edilmemiş bir bütçe yerine SESSİZCE uydurulmuş bir sayı kullanmak
değil, "bu bütçe henüz kalibre edilmedi" durumunu açıkça yansıtır.

TASARIM KARARI -- backend NotImplementedError'ı yutulmaz: sadece
asyncio.TimeoutError yakalanıp False'a çevrilir. Backend'ler bu görevde
(PHASE 0-3) hâlâ skeleton olduğu için her komutun ilk backend çağrısı
NotImplementedError ile patlayacak -- bu PayloadResult(success=False,...)
olarak GİZLENMEZ, olduğu gibi yükselir. "Backend henüz yok" ile "mission
görevi gerçekten başarısız oldu" birbirine karıştırılmamalı.

2026-08-22 KARARLARI (kullanıcı onayı ile kapatıldı):
  1. retract() artık FLEX-13 (RETRACT_TIMEOUT_S) ile sarmalanıyor --
     FLEX-05 (mesafe) ile kasıtlı olarak coupling yapılmadı, ayrı FLEX
     numarası (bkz. payload_config.py).
  2. release() sonrası stow() başarısız/timeout olursa artık RETRACTED
     yerine STOW_FAILED terminal state'ine geçiliyor (get_state() ile
     görülebilir). PayloadResult.success yine de release()'in kendi
     sonucunu yansıtır (payload fiziksel olarak bırakıldıysa True kalır)
     -- ama error_reason bu durumda stow anomalisini açıklar, state ise
     STOW_FAILED olur. "success=True + error_reason dolu" kombinasyonu
     kasıtlı: birincil işlem (bırakma) başarılı, ikincil bir anomali var.
  3. Retry/reset akışı bu görevde kasıtlı olarak eklenmedi -- PHASE 13'e
     ertelendi (bkz. payload_state.py TODO(PHASE-13) notu).
"""
import asyncio
import logging
import time
from typing import Optional

from payload import payload_config
from payload.backends.payload_backend import PayloadBackend
from payload.models.hook_behavior_model import HookBehaviourModel
from payload.payload_state import NoRecoveryPathError, PayloadStateMachine
from payload.payload_types import PayloadResult, PayloadState

logger = logging.getLogger(__name__)

# PHASE 13: bir PayloadManager ornegi boyunca izin verilen TOPLAM kurtarma
# sayisi.
#
# PROVENANCE: bu bir POLITIKA sayisidir, fiziksel bir olcum DEGIL -- bu
# yuzden FLEX numarasi ALMAZ (FLEX registry'si "esnek FIZIKSEL parametre"
# icin; bir tekrar sayisi ne olcu, ne sure, ne mesafe, ne index).
#
# NEDEN 2: bir gecici aksaklik (kacirilmis mesaj, gec kalmis servo) genelde
# ilk tekrarda duzelir; ikinci tekrar da duzeltmiyorsa sorun gecici degildir
# ve tekrar etmek yalnizca gorev suresini yer. Ust sinir yok DEGIL: sinirsiz
# tekrar, 10 dakikalik gorev butcesini sessizce tuketebilirdi.
#
# BU SAYI GECICIDIR: gercek arizalarin ne siklikta ilk tekrarda duzeldigi
# ancak Phase 16/17 verisiyle bilinir.
MAX_RECOVERY_ATTEMPTS = 2


class PayloadManager:
    """Görev mantığının gördüğü TEK payload arayüzü."""

    def __init__(self, backend: PayloadBackend) -> None:
        self._backend = backend
        self._hook_model = HookBehaviourModel(backend)
        self._state_machine = PayloadStateMachine()
        self._recovery_attempts = 0

    def get_state(self) -> PayloadState:
        """Side-effect'siz sorgu -- hiçbir FSM geçişini TETİKLEMEZ. PHASE 11
        (Transport Verification) burada herhangi bir komut çağırmadan
        mevcut state'i okuyabilmek için kullanacak."""
        return self._state_machine.current_state

    def select_payload(self, target_shape: str) -> None:
        """Sonraki komutlarin HANGI payload uzerinde calisacagini secer --
        backend'e delege eden bir GECIS metodu.

        DAVRANIS SOZLESMESI DEGISMEDI: 4 komut (catch_box_down/grapple/
        catch_box_up/release) ve get_state() aynen duruyor. Bu bir
        YAPILANDIRMA cagrisidir, hicbir FSM gecisi TETIKLEMEZ ve hicbir
        RPC yapmaz.

        NEDEN GEREKLI (2026-08-24): Gorev 2'de birakma sirasi artik tespit
        sirasini takip ettigi icin Gorev 3'un alacagi payload derleme
        zamaninda bilinmiyor. Mission katmani hedefi MISSION SEVIYESI sekil
        adiyla bildirir; backend-spesifik model adina cevirmek backend'in
        isidir (bkz. payload_backend.py::select_payload)."""
        self._backend.select_payload(target_shape)

    def capture_gate_excess_m(self):
        """Aracin yakalama zarfindan ne kadar yukarida oldugu (m), ya da None.

        DUCK-TYPED, KASITLI: backend'de boyle bir metod YOKSA None doner.
        Boylece RealPayloadBackend/DualPayloadBackend hicbir sekilde
        etkilenmez -- onlarda bu yetenek yok (gercek donanimda GPS/barometre
        zaten PX4 ile ayni referans oldugu icin ikilik de olusmaz).
        Bu bir FSM gecisi TETIKLEMEZ ve hicbir komut CALISTIRMAZ; salt
        olcumdur, tipki is_still_secured() gibi backend'e sorar."""
        probe = getattr(self._backend, "capture_gate_excess_m", None)
        if probe is None:
            return None
        try:
            return probe()
        except Exception:  # noqa: BLE001 -- olcum yolu gorev akisini bozamaz
            return None

    def is_still_secured(self) -> bool:
        """PHASE 11: payload HALA fiziksel olarak guvencede mi.

        get_state() ile ARASINDAKI FARK KRITIK:
          * get_state() FSM'in HAFIZASIDIR -- "bir noktada SECURED'a
            gectik" der. Bir siralama/programlama hatasini yakalar, ama
            payload ucus sirasinda DUSERSE bunu goremez; state hala
            TRANSPORTING gorunur.
          * is_still_secured() BACKEND'E SORAR -- Gazebo'da joint'in hala
            var olup olmadigini okuyan tek ground-truth biti
            (HookAttachSystem'in /hook/state yayini). Yani "hatirliyorum"
            degil, "hala orada".

        Phase 6 acceptance'i bu dogrulamayi tool seviyesinde olcmustu
        (payload araci izliyor mu, takip hatasi 0.0002 m). Bu metod ayni
        soruyu MISSION seviyesine tasir -- yeniden implement etmez, ayni
        backend sorgusuna delege eder.

        Side-effect'siz: hicbir FSM gecisi TETIKLEMEZ (get_state() ile ayni
        sozlesme).

        REAL YOLU: RealPayloadBackend.is_secured() henuz
        NotImplementedError'dir (sensor yolu yok, TODO(SAFETY)). Bu KASITLI
        olarak yutulmaz -- cagiran mission fazi onu temiz bir basarisizliga
        cevirir. Zaten catch_box_up() de ayni sorguyu yapiyor, yani bu
        metod Real yolda YENI bir kirilma noktasi EKLEMEZ."""
        return self._hook_model.is_secured()

    def can_recover(self) -> bool:
        """PHASE 13: mevcut state'ten kurtarma MUMKUN mu.

        Iki kosul birlikte: (a) state icin tanimli bir kurtarma yolu var,
        (b) kurtarma butcesi tukenmedi. Side-effect'siz."""
        if self._recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
            return False
        return self._state_machine.current_state.is_failure

    def recover(self) -> PayloadState:
        """PHASE 13: failure state'ten kurtarma state'ine gec ve yeni state'i
        don. Cagiran, donen state'e uygun komutu YENIDEN calistirmakla
        yukumludur -- bu metod hicbir backend komutu CALISTIRMAZ.

        Ornek: catch_box_up() RETRACT_TIMEOUT dondurduyse, recover()
        GRAPPLED'a doner ve cagiran catch_box_up()'i tekrar cagirir.

        Butce tukendiyse veya kurtarma yolu yoksa NoRecoveryPathError
        firlatir -- sessizce "kurtarilamadi ama devam" YOKTUR.

        KASITLI OLARAK OTOMATIK DEGIL: PayloadManager bir komut basarisiz
        oldugunda KENDILIGINDEN tekrar denemez. Gerekce -- gorunmez bir
        tekrar, guvenilirlik sorununu istatistiksel olarak olculemez hale
        getirir (bkz. payload/KNOWN_ISSUES.md §5: attach-timeout orani
        ~6 kosuda 1 ve Phase 15 bunu tekrarli kosuyla OLCMEK zorunda).
        Tekrar bir gorev karari olarak acikca verilmelidir."""
        if self._recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
            raise NoRecoveryPathError(self._state_machine.current_state)

        previous = self._state_machine.current_state
        target = self._state_machine.recover()
        self._recovery_attempts += 1
        logger.warning("[PAYLOAD] Kurtarma %d/%d: %s -> %s. Cagiran ilgili komutu "
                       "YENIDEN calistirmali.", self._recovery_attempts,
                       MAX_RECOVERY_ATTEMPTS, previous.value, target.value)
        return target

    @property
    def recovery_attempts(self) -> int:
        """Bu ornek uzerinde simdiye kadar yapilan kurtarma sayisi."""
        return self._recovery_attempts

    async def catch_box_down(self) -> PayloadResult:
        """V33: SERVO2_DOWN -> CATCH_PAYLOAD -> TIMEOUT_CHECK."""
        start = time.monotonic()
        self._state_machine.transition_to(PayloadState.DEPLOYING)
        deployed = await self._run_with_timeout(
            self._backend.deploy(), payload_config.FLEX_02_HOOK_DEPLOYMENT_TIME_S)
        if not deployed:
            self._state_machine.transition_to(PayloadState.DEPLOY_TIMEOUT)
            return self._fail("deploy() basarisiz veya zaman asimina ugradi", start)
        self._state_machine.transition_to(PayloadState.DEPLOYED)

        self._state_machine.transition_to(PayloadState.SEARCHING)
        captured = await self._run_with_timeout(
            self._backend.await_capture(), payload_config.FLEX_06_CAPTURE_TIMEOUT_S)
        if not captured:
            self._state_machine.transition_to(PayloadState.CAPTURE_TIMEOUT)
            return self._fail("await_capture() basarisiz veya zaman asimina ugradi", start)
        self._state_machine.transition_to(PayloadState.CAPTURED)

        return self._succeed(start)

    async def grapple(self) -> PayloadResult:
        """V33: SERVO3_GRAPPLE. Sadece CAPTURED state'inden çağrılabilir --
        state machine bunu zorunlu kılar (bkz. payload_state.py)."""
        start = time.monotonic()
        self._state_machine.transition_to(PayloadState.GRAPPLING)
        grappled = await self._run_with_timeout(
            self._backend.grapple(), payload_config.FLEX_11_GRAPPLE_TIMEOUT_S)
        if not grappled:
            self._state_machine.transition_to(PayloadState.GRAPPLE_TIMEOUT)
            return self._fail("grapple() basarisiz veya zaman asimina ugradi", start)
        self._state_machine.transition_to(PayloadState.GRAPPLED)

        return self._succeed(start)

    async def catch_box_up(self) -> PayloadResult:
        """V33: SERVO2_REVERSE (1. kullanım). Retract + secured doğrulaması
        başarılıysa mission otomatik olarak TRANSPORTING'e geçer."""
        start = time.monotonic()
        self._state_machine.transition_to(PayloadState.RETRACTING)
        retracted = await self._run_with_timeout(
            self._backend.retract(), payload_config.FLEX_13_RETRACT_TIMEOUT_S)
        if not retracted:
            self._state_machine.transition_to(PayloadState.RETRACT_TIMEOUT)
            return self._fail("retract() basarisiz veya zaman asimina ugradi", start)

        if not self._hook_model.is_secured():
            self._state_machine.transition_to(PayloadState.PAYLOAD_NOT_SECURED)
            return self._fail("retract() tamamlandi ama is_secured() False donuyor", start)

        self._state_machine.transition_to(PayloadState.SECURED)
        self._state_machine.transition_to(PayloadState.TRANSPORTING)
        return self._succeed(start)

    async def release(self) -> PayloadResult:
        """V33 md.17/20: SERVO2_DOWN -> SERVO3_RELEASE -> SERVO2_REVERSE
        (2./son kullanım). Sadece TRANSPORTING state'inden çağrılabilir."""
        start = time.monotonic()
        self._state_machine.transition_to(PayloadState.RELEASING)

        # V33 md.17/20: teslimat dizisi UC adimdir --
        #   SERVO2_DOWN -> SERVO3_RELEASE -> SERVO2_REVERSE
        # Ilk adim (yuku asagi indirme) eksikti; spesifikasyon denetiminde
        # (2026-08-24) bulundu ve eklendi. Real tarafta deploy() ile ayni
        # fiziksel komuttur ve ayni FLEX-14/16 guard'ini paylasir; Gazebo'da
        # indirilecek mekanizma modellenmedigi icin belgelenmis no-op'tur.
        # deploy() YENIDEN CAGRILMAZ: Gazebo'da o /hook/attach yayinlar,
        # yani teslimat aninda "yakala" komutu gonderilmis olurdu.
        lowered = await self._run_with_timeout(
            self._backend.lower_for_release(), payload_config.FLEX_02_HOOK_DEPLOYMENT_TIME_S)
        if not lowered:
            self._state_machine.transition_to(PayloadState.RELEASE_TIMEOUT)
            return self._fail(
                "lower_for_release() basarisiz veya zaman asimina ugradi -- "
                "yuk indirilemedi, SERVO3_RELEASE denenmedi", start)

        released = await self._run_with_timeout(
            self._backend.release(), payload_config.FLEX_08_RELEASE_SEQUENCE_TIMING_S)
        if not released:
            self._state_machine.transition_to(PayloadState.RELEASE_TIMEOUT)
            return self._fail("release() basarisiz veya zaman asimina ugradi", start)
        self._state_machine.transition_to(PayloadState.RELEASED)

        # 2026-08-22 karari: stow basarisiz/zaman asimina ugrarsa RETRACTED
        # yerine STOW_FAILED'a gecilir (get_state() ile gorulebilir).
        # PayloadResult.success yine de True kalir -- payload FIZIKSEL
        # OLARAK birakildi (release() basarili oldu), mekanizmanin
        # toparlanamamasi ayri, ikincil bir anomali. error_reason bunu
        # tasir.
        stowed = await self._run_with_timeout(self._backend.stow(), None)
        if not stowed:
            self._state_machine.transition_to(PayloadState.STOW_FAILED)
            logger.warning(
                "[PAYLOAD] stow() basarisiz/zaman asimina ugradi -- payload zaten RELEASED "
                "(fiziksel olarak birakildi), state=STOW_FAILED ama PayloadResult.success=True kaliyor.")
            return PayloadResult(
                success=True, final_state=PayloadState.STOW_FAILED,
                error_reason="stow() basarisiz veya zaman asimina ugradi -- payload birakildi ama mekanizma toplanamadi",
                elapsed_time=time.monotonic() - start)

        self._state_machine.transition_to(PayloadState.RETRACTED)
        return self._succeed(start)

    async def _run_with_timeout(self, coro, timeout_s: Optional[float]) -> bool:
        """asyncio.TimeoutError -> False. Başka her exception (özellikle
        backend skeleton'ların NotImplementedError'ı) OLDUĞU GİBİ
        yükselir -- yutulmaz."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout_s)
        except asyncio.TimeoutError:
            return False

    def _succeed(self, start: float) -> PayloadResult:
        return PayloadResult(success=True, final_state=self._state_machine.current_state,
                              error_reason=None, elapsed_time=time.monotonic() - start)

    def _fail(self, reason: str, start: float) -> PayloadResult:
        logger.error("[PAYLOAD] %s (state=%s)", reason, self._state_machine.current_state.value)
        return PayloadResult(success=False, final_state=self._state_machine.current_state,
                              error_reason=reason, elapsed_time=time.monotonic() - start)
