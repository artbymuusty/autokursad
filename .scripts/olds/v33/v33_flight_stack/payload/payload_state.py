"""PHASE 1: backend-bağımsız ortak payload state machine.

Bu sınıf Real/Gazebo ayrımı yapmaz -- ikisi de aynı PayloadStateMachine'i
kullanmak ZORUNDA, böylece ikisinin de aynı state sırasını ürettiği ileride
(PHASE 15) doğrudan karşılaştırılabilir. Burada hiçbir fiziksel zamanlama,
sensör okuması veya backend çağrısı YOKTUR -- sadece "hangi state'den hangi
state'e geçmek legal mi" sorusuna cevap veren saf bir graf.

Timeout/başarısızlık state'lerine geçiş de normal bir transition_to()
çağrısıdır -- zaman aşımını TESPİT etmek (örn. bir asyncio.wait_for)
PayloadManager'ın/backend'in sorumluluğu, bu sınıfın değil.
"""
import logging
import time
from dataclasses import dataclass
from typing import Dict, FrozenSet, List

from payload.payload_types import PayloadState

logger = logging.getLogger(__name__)


class IllegalPayloadTransitionError(Exception):
    """current_state'den new_state'e legal bir geçiş yolu olmadığında
    fırlatılır. Sessizce yutulmamalı -- geçersiz bir geçiş her zaman bir
    çağıran mantık hatasıdır (state machine'i kendisi hiçbir zaman
    tutarsız/atlanmış bir state üretmez)."""

    def __init__(self, current_state: PayloadState, attempted_state: PayloadState,
                 legal_next_states: FrozenSet[PayloadState]):
        self.current_state = current_state
        self.attempted_state = attempted_state
        self.legal_next_states = legal_next_states
        legal = ", ".join(s.value for s in sorted(legal_next_states, key=lambda s: s.value)) or "(yok -- terminal state)"
        super().__init__(
            f"Illegal payload state transition: {current_state.value} -> {attempted_state.value}. "
            f"{current_state.value} icin legal sonraki state'ler: {legal}")


@dataclass(frozen=True)
class StateTransitionRecord:
    """Her geçişte tutulan tarihçe kaydı -- önceki state + zaman damgası."""
    previous_state: PayloadState
    new_state: PayloadState
    timestamp: float


# Legal geçiş grafiği. Terminal state'ler (RETRACTED + tüm *_TIMEOUT/
# PAYLOAD_NOT_SECURED/STOW_FAILED) kasıtlı olarak boş kume -- buradan
# hiçbir yere otomatik "reset" veya "retry" geçişi YOK.
#
# PHASE 13 (2026-08-24): retry/reset yolu artık TANIMLI, ama BU GRAFİĞE
# EKLENMEDİ -- ayrı bir _RECOVERY_TRANSITIONS grafiğinde yaşıyor ve yalnızca
# açık recover() çağrısıyla kullanılabilir. Gerekçe aşağıda.
_TRANSITIONS: Dict[PayloadState, FrozenSet[PayloadState]] = {
    PayloadState.IDLE: frozenset({PayloadState.DEPLOYING}),
    PayloadState.DEPLOYING: frozenset({PayloadState.DEPLOYED, PayloadState.DEPLOY_TIMEOUT}),
    PayloadState.DEPLOYED: frozenset({PayloadState.SEARCHING}),
    PayloadState.SEARCHING: frozenset({PayloadState.CAPTURED, PayloadState.CAPTURE_TIMEOUT}),
    PayloadState.CAPTURED: frozenset({PayloadState.GRAPPLING}),
    PayloadState.GRAPPLING: frozenset({PayloadState.GRAPPLED, PayloadState.GRAPPLE_TIMEOUT}),
    PayloadState.GRAPPLED: frozenset({PayloadState.RETRACTING}),
    PayloadState.RETRACTING: frozenset({
        PayloadState.SECURED, PayloadState.RETRACT_TIMEOUT, PayloadState.PAYLOAD_NOT_SECURED,
    }),
    PayloadState.SECURED: frozenset({PayloadState.TRANSPORTING}),
    PayloadState.TRANSPORTING: frozenset({PayloadState.RELEASING}),
    PayloadState.RELEASING: frozenset({PayloadState.RELEASED, PayloadState.RELEASE_TIMEOUT}),
    PayloadState.RELEASED: frozenset({PayloadState.RETRACTED, PayloadState.STOW_FAILED}),
    PayloadState.RETRACTED: frozenset(),
    PayloadState.DEPLOY_TIMEOUT: frozenset(),
    PayloadState.CAPTURE_TIMEOUT: frozenset(),
    PayloadState.GRAPPLE_TIMEOUT: frozenset(),
    PayloadState.RETRACT_TIMEOUT: frozenset(),
    PayloadState.RELEASE_TIMEOUT: frozenset(),
    PayloadState.PAYLOAD_NOT_SECURED: frozenset(),
    PayloadState.STOW_FAILED: frozenset(),
}

# ============================================================
# PHASE 13 -- KURTARMA (retry/reset) GRAFİĞİ
# ============================================================
#
# NEDEN AYRI BİR GRAF (kritik tasarım kararı):
# Kurtarma kenarlarını yukarıdaki _TRANSITIONS'a eklemek iki şeyi bozardı:
#   1. PayloadState.is_terminal anlamını yitirirdi -- "dışarı giden legal
#      geçişi yok" artık hiçbir failure state için doğru olmazdı.
#   2. Kurtarma KAZA ESERİ mümkün olurdu: herhangi bir transition_to()
#      çağrısı bir failure state'ten çıkabilirdi. Kurtarma, sessizce
#      olabilecek bir şey DEĞİL, açıkça istenmesi gereken bir şeydir.
# Bu yüzden recover() ayrı bir kapıdır ve _TRANSITIONS'a dokunmaz.
#
# İKİ KURTARMA SINIFI:
#
#   ADIM TEKRARI (aynı fiziksel aşamada kal, o adımı yeniden dene):
#     CAPTURE_TIMEOUT  -> DEPLOYED     kanca zaten inik, aramayı tekrarla
#     GRAPPLE_TIMEOUT  -> CAPTURED     temas var, kavramayı tekrarla
#     RETRACT_TIMEOUT  -> GRAPPLED     yük mekanik olarak tutulu, çekmeyi
#                                      tekrarla (yarım kalmış bir geri çekme
#                                      tamamlanmalı, baştan başlanmamalı)
#     RELEASE_TIMEOUT  -> TRANSPORTING GÜVENLİK KRİTİĞİ: yük hâlâ asılı ve
#                                      araç hedefin üstünde. Takılı kalmış
#                                      bir yük, tekrarlanmış bir bırakmadan
#                                      DAHA KÖTÜDÜR.
#     STOW_FAILED      -> RELEASED     yük zaten bırakıldı (birincil görev
#                                      BAŞARILI); bu yalnızca temizlik
#                                      tekrarı, kaybedilecek bir şey yok.
#
#   TAM YENİDEN BAŞLATMA (baştan al):
#     DEPLOY_TIMEOUT       -> IDLE  hiçbir fiziksel durum kurulmadı, yük
#                                   yerinde duruyor, baştan almak güvenli.
#     PAYLOAD_NOT_SECURED  -> IDLE  retract bitti ama is_secured() False --
#                                   yani kanca yukarıda ve elde bir şey yok.
#                                   Aynı adımı tekrarlamanın anlamı yok
#                                   (çekilecek bir şey kalmadı), baştan
#                                   yaklaşılmalı.
#
# PAYLOAD_NOT_SECURED'IN BİLİNEN RİSKİ (kayıt için):
# Sensör yalan söylüyorsa (yük aslında tutuluyken "değil" diyorsa) yeniden
# deploy etmek onu düşürür. Bu risk KABUL EDİLDİ çünkü bu state yalnızca
# catch_box_up() içinde, yani alma irtifasında (~0.30 m) üretilebilir --
# oradan düşmek zararsızdır. Taşıma irtifasında bu state'e ULAŞILAMAZ.
#
# TERMINAL KALAN TEK STATE: RETRACTED (başarı). Kurtarılacak bir şey yok.
# Failure state'leri ise "bütçe bitene kadar kurtarılabilir" -- bütçe
# PayloadManager'da tutulur (bkz. MAX_RECOVERY_ATTEMPTS).
#
# BU TASARIM GEÇİCİDİR: gerçek uçuş verisi henüz YOK. Hangi başarısızlığın
# tekrarlanmaya değdiği ancak Phase 16 (bench) ve Phase 17 (gerçek uçuş)
# sonrası bilinebilir. Yanlış çıkarsa ucuza düzeltilir -- kurtarma ayrı bir
# grafta olduğu için normal akışa hiç dokunmadan değiştirilebilir.
_RECOVERY_TRANSITIONS: Dict[PayloadState, PayloadState] = {
    PayloadState.DEPLOY_TIMEOUT: PayloadState.IDLE,
    PayloadState.CAPTURE_TIMEOUT: PayloadState.DEPLOYED,
    PayloadState.GRAPPLE_TIMEOUT: PayloadState.CAPTURED,
    PayloadState.RETRACT_TIMEOUT: PayloadState.GRAPPLED,
    PayloadState.PAYLOAD_NOT_SECURED: PayloadState.IDLE,
    PayloadState.RELEASE_TIMEOUT: PayloadState.TRANSPORTING,
    PayloadState.STOW_FAILED: PayloadState.RELEASED,
}

assert set(_RECOVERY_TRANSITIONS) == {s for s in PayloadState if s.is_failure}, (
    "Her failure state icin bir kurtarma karari VERILMIS olmali -- kurtarilamaz "
    "olduguna karar verildiyse bile bu acikca yazilmali, sessizce atlanmamali."
)
assert PayloadState.RETRACTED not in _RECOVERY_TRANSITIONS, (
    "RETRACTED bir BASARI terminalidir; kurtarilacak bir sey yoktur."
)


class NoRecoveryPathError(Exception):
    """Kurtarma yolu OLMAYAN bir state'ten recover() cagrildi."""

    def __init__(self, current_state: PayloadState):
        self.current_state = current_state
        super().__init__(
            f"{current_state.value} state'inden tanimli bir kurtarma yolu YOK. "
            f"Kurtarilabilir state'ler: "
            f"{', '.join(sorted(s.value for s in _RECOVERY_TRANSITIONS))}")


assert set(_TRANSITIONS.keys()) == set(PayloadState), (
    "PayloadState enum'una eklenen her state icin _TRANSITIONS'ta bir satir olmali "
    "(bos frozenset olsa bile) -- eksik bir state sessizce 'gecis tanimsiz' anlamina gelmemeli."
)


class PayloadStateMachine:
    """Tek bir payload yaşam döngüsü örneğinin state'ini tutar ve geçişleri
    _TRANSITIONS grafiğine göre doğrular. Backend/fizik/zamanlama bilgisi
    içermez -- PayloadManager tarafından sarmalanır."""

    def __init__(self) -> None:
        self._current_state: PayloadState = PayloadState.IDLE
        self._history: List[StateTransitionRecord] = []

    @property
    def current_state(self) -> PayloadState:
        return self._current_state

    @property
    def history(self) -> List[StateTransitionRecord]:
        """Salt-okunur tarihçe görünümü (çağıran listeyi mutasyona
        uğratamasın diye kopya döner)."""
        return list(self._history)

    def recover(self) -> PayloadState:
        """PHASE 13: bir failure state'ten tanimli kurtarma state'ine gecer.

        transition_to()'dan AYRI bir kapidir ve _TRANSITIONS grafigini HIC
        kullanmaz -- kurtarma kaza eseri olamaz, acikca istenmelidir.

        Kurtarma yolu yoksa NoRecoveryPathError firlatir (RETRACTED dahil:
        basari terminalinden kurtarilacak bir sey yoktur).

        Kurtarma sayisini SINIRLAMAK bu sinifin isi DEGILDIR -- butce
        PayloadManager'da tutulur; burasi yalnizca "hangi state'ten nereye"
        sorusunu cevaplar."""
        target = _RECOVERY_TRANSITIONS.get(self._current_state)
        if target is None:
            raise NoRecoveryPathError(self._current_state)

        previous = self._current_state
        self._current_state = target
        self._history.append(StateTransitionRecord(previous, target, time.time()))
        logger.warning("[PAYLOAD_STATE] KURTARMA %s -> %s", previous.value, target.value)
        return target

    def transition_to(self, new_state: PayloadState) -> None:
        """current_state -> new_state legal değilse IllegalPayloadTransitionError
        fırlatır (sessizce yutulmaz). Legal ise state'i günceller, tarihçeye
        kaydeder ve loglar."""
        legal_next = _TRANSITIONS[self._current_state]
        if new_state not in legal_next:
            raise IllegalPayloadTransitionError(self._current_state, new_state, legal_next)

        previous = self._current_state
        timestamp = time.time()
        self._current_state = new_state
        self._history.append(StateTransitionRecord(previous, new_state, timestamp))
        logger.info("[PAYLOAD_STATE] %s -> %s", previous.value, new_state.value)
