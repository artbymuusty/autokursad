"""PHASE 5.5 ADIM B: HookAttachSystem'in somut gz-transport client'ı.

payload/GazeboPayloadBackend'in beklediği duck-typed protokolü, repodaki
kanıtlanmış `gz topic` CLI subprocess deseniyle karşılar (bkz.
gz_pose_monitor.py -- abonelik bir kez açılır, bir cache'e akar, çağıranlar
bedava okur). Bu dosya KASITLI olarak gz_system/ altında yaşar: payload/
paketinin gz_system'den bağımsız kalma kuralı korunur, backend bu sınıfı
ismen hiç bilmez, sadece constructor'ında enjekte edilir.

--- NEDEN ABONELİK NESNE OLUŞURKEN BAŞLAR (RACE FIX) ----------------------

/hook/state latch'siz ve geçiş başına TEK KEZ yayınlanır
(HookAttachSystem.cc:64, :127). PHASE 5.5 ADIM A'da canlı ölçüldü: attach
isteği ile ATTACHED arası 2.485 ms. Buna karşılık taze bir `gz topic -e`
aboneliği ~2 s gz-transport discovery ister (gz_pose_monitor.py'nin kendi
ölçümü). Yani aboneliği publish'ten SONRA açmak, gözlenecek tek mesajı
yapısal olarak kaçırmak demektir -- joint fiziksel olarak oluşmuşken bile
timeout alınır. Legacy gz_payload_actuator.py::_await_attach tam bunu
yapıyor (önce publish, sonra monitor).

Burada abonelik `create()`/`start()` ile mission bootstrap'ında açılır ve
publish'i BEKLEMEZ; dahası publish_attach(), akış hazır değilken yayın
yapmayı REDDEDER (savunma katmanı -- backend'in kendi
is_state_stream_ready() kapısıyla aynı gerekçe).

--- PARSER: MESAJ AYIRICI SAYAR, "data:" SATIRI ARAMAZ --------------------

# BULGU (ADIM A doğrulaması sırasında): gz.msgs.Boolean'ın text
# encoding'i data:false için hiçbir satır üretmiyor (protobuf
# default-value omission). Legacy gz_payload_actuator.py::
# HookStateMonitor'ün "data:" satırı arayan parser'ı bu yüzden
# _attached'i hiçbir zaman False'a çeviremiyor -- bilinen, ayrı,
# bu görevin kapsamı dışında bir sorun, buraya sadece referans
# için not düşüldü.

Canlı ölçüm (ADIM A, /test/boolshape topic'ine true -> false -> true
yayınlandı, `gz topic -e` çıktısı `cat -A` ile):

    data:·true<LF>
    <LF>              <- 1. mesajın ayırıcısı
    <LF>              <- 2. mesaj (false) BOŞ içerik + kendi ayırıcısı
    data:·true<LF>
    <LF>              <- 3. mesajın ayırıcısı

Yani `false` bir mesajın TAMAMI boş satırdır. Bu yüzden buradaki parser
mesaj sınırlarını sayar: bir ayırıcı görülünce biriken içerik "data: true"
içeriyorsa True, İÇERİK BOŞSA False. Ayırıcı olarak hem boş satır (bu
kurulumda ölçülen gerçek davranış) hem de yalnız tire içeren satır kabul
edilir -- bazı gz sürümleri `---` basar, ikisini de tanımak bedavadır.
"""
import asyncio
import logging
import math
import shutil
from typing import Optional, Tuple

from gz_system.gz_pose_monitor import GzPoseMonitor

logger = logging.getLogger(__name__)

HOOK_ATTACH_TOPIC = "/hook/attach"
HOOK_DETACH_TOPIC = "/hook/detach"
HOOK_STATE_TOPIC = "/hook/state"

# gz-transport discovery bedeli. Kaynak: gz_pose_monitor.py'nin ölçümü
# ("one `gz topic -e -n 1` per poll costs ~2 s of gz-transport discovery
# EACH (measured)"). Bu bir TIMEOUT değil, aboneliğin kurulduğunu
# varsaymadan önce beklenen yerleşme süresi; is_state_stream_ready() bu
# süre dolmadan True dönmez.
DISCOVERY_SETTLE_S = 2.5

# Publisher'ın (plugin'in) ayakta olduğunu doğrularken `gz topic -l`
# yoklama aralığı ve üst sınırı.
#
# PROVENANCE (PHASE 5.5 ADIM B, 2026-08-23): bu iki değer YENİDİR -- mevcut
# bir pattern'den türetilmedi ve hiçbir ölçüme dayanmıyor. Repodaki en yakın
# komşuları KASITLI olarak kaynak gösterilmedi, çünkü farklı şeyleri
# ölçüyorlar: parameters.py::PAYLOAD_DETACH_POLL_INTERVAL_S (0.05 s) fiziksel
# ayrılmayı izleyen sıkı bir poz yoklamasıdır; parameters.py::
# MISSION_MODE_CONFIRM_TIMEOUT_S (10.0 s) ise MAVLink mod onayıdır. Buradaki
# 10.0 ile oradaki 10.0 arasında bir akrabalık YOKTUR.
#
# NEDEN FLEX GEREKTİRMİYOR: bunlar fiziksel kalibrasyon değeri değil --
# drone, kanca, payload veya envelope hakkında hiçbir şey söylemiyorlar.
# Yalnızca bir TANI beklemesini sınırlıyorlar ve süre dolduğunda akış iptal
# EDİLMEZ, sadece uyarı loglanır (bkz. _await_publisher_present); yani yanlış
# seçilmeleri sessiz bir yanlış sonuç üretemez, en fazla bootstrap'ta 10 s
# gecikme + bir uyarı satırı demektir. Normal durumda topic ilk yoklamada
# bulunur ve bedel ~0.25 s'dir.
_TOPIC_POLL_INTERVAL_S = 0.25
_TOPIC_POLL_LIMIT_S = 10.0

Pose = Tuple[float, float, float]

# payload_red/_blue kutu geometrisi: Tools/simulation/gz/worlds/default.sdf
# icinde <box><size>0.30 0.225 0.05</size></box> -- yani yari-yukseklik
# 0.05/2 = 0.025 m. Bu bir KALIBRASYON degeri DEGIL, world SDF'ten okunan
# TAM BILINEN bir model olcusudur; bu yuzden FLEX numarasi almaz. World
# SDF'teki kutu boyutu degisirse burasi da guncellenmelidir.
PAYLOAD_HALF_HEIGHT_M = 0.025



def _distance(pose_a: Optional[Pose], pose_b: Optional[Pose]) -> Optional[float]:
    """İki poz arasındaki 3B mesafe (m), biri bile bilinmiyorsa None.

    BU, PROJEDEKİ TEK MESAFE FORMÜLÜDÜR. Hem GazeboPayloadBackend'in
    FLEX-20 guard'lı yakınlık kapısı (backend, read_vehicle_payload_distance()
    üzerinden buraya iner -- kendi içinde math.dist ÇAĞIRMAZ) hem de
    PayloadManager'ı bypass eden FLEX-20 karakterizasyon scripti aynı
    fonksiyondan geçer. İki bağımsız hesap KASITLI OLARAK yok: formül
    değişirse (ör. yalnız yatay mesafeye geçilirse) iki yol sessizce
    ayrışamaz.

    None'ı sayıya çevirmez: "bilmiyorum" asla "yakınım" olarak okunamaz.
    """
    if pose_a is None or pose_b is None:
        return None
    return math.dist(pose_a, pose_b)


def _vertical_clearance(payload_pose: Optional[Pose], vehicle_pose: Optional[Pose],
                        payload_half_height_m: float = PAYLOAD_HALF_HEIGHT_M
                        ) -> Optional[float]:
    """Aracın altı ile payload'ın üst yüzeyi arasındaki DİKEY açıklık (m),
    poz bilinmiyorsa None.

    BU, FLEX-20'NİN KAPILADIĞI TEK FORMÜLDÜR (2026-08-23 operatör kararı).
    3B merkez-merkez mesafe (_distance) ile KASITLI olarak ayrıdır: Phase
    5.5 Adım D'de ölçüldü ki araç üretim irtifasındayken (0.339 m)
    merkez-merkez 0.317 m, dikey açıklık ise 0.289 m'dir -- 0.30'luk eşikle
    birincisi kapıyı hiç açmaz, ikincisi açar. "İrtifa AGL" ile
    "merkez-merkez ayrım" aynı fiziksel büyüklük değildir.

    "Aracın altı" base_link orijiniyle YAKLAŞIKLANIR (sim'de ayrı bir kanca
    gövdesi yok). base_link gerçek alt yüzeyin ÜSTÜNDE olduğu için hesap
    gerçek açıklığı OLDUĞUNDAN BÜYÜK gösterir, yani kapı olması
    gerekenden KATIdır -- emin olunmayan durumda reddeden, güvenli yön.

    None'ı sayıya çevirmez.
    """
    if payload_pose is None or vehicle_pose is None:
        return None
    payload_top_z = payload_pose[2] + payload_half_height_m
    return vehicle_pose[2] - payload_top_z


class GzHookClient:
    """GazeboPayloadBackend'in enjekte edilen client'ı.

    ÖNERİLEN KULLANIM -- abonelik nesne oluşurken açılsın diye:

        client = await GzHookClient.create(payload_model_name="payload_red",
                                           vehicle_model_name="x500_mono_cam_down_0")

    Düz constructor I/O YAPMAZ (test edilebilirlik + çalışan bir event loop
    zorunluluğu olmasın diye); bu haliyle is_state_stream_ready() False
    döner ve publish_attach() yayın yapmayı reddeder, yani "start()
    çağırmayı unutma" hatası sessizce race'e dönüşemez.
    """

    def __init__(self, payload_model_name: str, vehicle_model_name: str,
                 world_name: str = "default", pose_monitor: Optional[GzPoseMonitor] = None,
                 discovery_settle_s: float = DISCOVERY_SETTLE_S,
                 subprocess_exec=None) -> None:
        if not payload_model_name:
            raise ValueError("payload_model_name zorunlu.")
        if not vehicle_model_name:
            raise ValueError("vehicle_model_name zorunlu.")
        self.payload_model_name = payload_model_name
        self.vehicle_model_name = vehicle_model_name
        self.world_name = world_name
        # gz_pose_monitor.py'nin kanıtlanmış cache'i tekrar kullanılıyor --
        # mesafe okuması için ikinci bir poz altyapısı YAZILMADI.
        self.pose_monitor = pose_monitor or GzPoseMonitor(world_name)
        self._discovery_settle_s = discovery_settle_s
        # Testlerin gerçek subprocess'i değiştirebilmesi için enjekte
        # edilebilir; varsayılanı gerçek asyncio subprocess'idir.
        self._subprocess_exec = subprocess_exec or asyncio.create_subprocess_exec

        self._state: Optional[bool] = None
        self._state_event = asyncio.Event()
        self._stream_ready = False
        self._proc = None
        self._task = None
        self._pending_lines = []

    # -- Yaşam döngüsü ----------------------------------------------------

    @classmethod
    async def create(cls, *args, **kwargs) -> "GzHookClient":
        """Nesneyi oluşturur VE /hook/state aboneliğini hemen açar.
        Mission bootstrap'ında (ADIM C) kullanılacak giriş noktası."""
        client = cls(*args, **kwargs)
        await client.start()
        return client

    async def start(self) -> bool:
        """/hook/state aboneliğini açar ve gerçekten yerleşene kadar
        is_state_stream_ready()'i False tutar.

        İki gerçek kapı: (1) topic `gz topic -l` listesinde görünsün
        (plugin ayakta ve advertise etmiş), (2) discovery yerleşme süresi
        dolsun. İkisi de geçilmeden ready denmez."""
        if self._proc is not None:
            return True
        try:
            self._proc = await self._subprocess_exec(
                "gz", "topic", "-e", "-t", HOOK_STATE_TOPIC,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            logger.error("GzHookClient: /hook/state aboneligi acilamadi: %s", e)
            self._proc = None
            return False

        self._task = asyncio.create_task(self._read_loop())
        await self._await_publisher_present()
        await asyncio.sleep(self._discovery_settle_s)
        self._stream_ready = True
        logger.info("GzHookClient: /hook/state aboneligi hazir (settle=%.2fs).",
                    self._discovery_settle_s)
        return True

    async def stop(self) -> None:
        """gz_pose_monitor.py::stop() ile aynı desen."""
        self._stream_ready = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
            self._proc = None

    async def _await_publisher_present(self) -> bool:
        """Plugin'in /hook/state'i advertise ettiğini `gz topic -l` ile
        doğrular. Bulunamazsa ENGELLEMEZ -- sadece uyarır: topic listesi
        geçici olarak boş dönebilir ve bu, aboneliği iptal etmek için bir
        gerekçe değildir."""
        waited = 0.0
        while waited < _TOPIC_POLL_LIMIT_S:
            if HOOK_STATE_TOPIC in await self._list_topics():
                return True
            await asyncio.sleep(_TOPIC_POLL_INTERVAL_S)
            waited += _TOPIC_POLL_INTERVAL_S
        logger.warning("GzHookClient: %s, %.1fs icinde `gz topic -l` listesinde "
                       "gorunmedi -- plugin yuklu olmayabilir (bkz. model.sdf "
                       "HookAttachSystem blogu). Abonelik yine de aciliyor.",
                       HOOK_STATE_TOPIC, _TOPIC_POLL_LIMIT_S)
        return False

    async def _list_topics(self):
        try:
            proc = await self._subprocess_exec(
                "gz", "topic", "-l",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            return stdout.decode(errors="replace").split()
        except Exception:  # noqa: BLE001
            return []

    # -- Okuma yolu -------------------------------------------------------

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            try:
                raw = await self._proc.stdout.readline()
            except Exception:  # noqa: BLE001
                return
            if not raw:
                return
            self._consume_line(raw.decode(errors="replace"))

    def _consume_line(self, line: str) -> None:
        """Mesaj AYIRICI sayan parser (modül docstring'indeki BULGU'ya bkz.).

        "data:" satırı ARAMAZ: gz.msgs.Boolean{data:false} hiçbir satır
        üretmez, bu yüzden False'un tek işareti BOŞ bir mesaj gövdesidir.
        """
        stripped = line.strip()
        if stripped and set(stripped) != {"-"}:
            self._pending_lines.append(stripped)
            return
        # Ayirici geldi -> bir mesaj tamamlandi.
        body = self._pending_lines
        self._pending_lines = []
        if not body:
            # BOS govde = data:false (protobuf default-value omission).
            self._set_state(False)
            return
        for entry in body:
            if entry.startswith("data:"):
                self._set_state(entry.split(":", 1)[1].strip() == "true")
                return
        # Beklenmedik govde: state'i BOZMA, sadece rapor et.
        logger.warning("GzHookClient: %s uzerinde taninmayan mesaj govdesi: %r",
                       HOOK_STATE_TOPIC, body)

    def _set_state(self, value: bool) -> None:
        self._state = value
        self._state_event.set()

    # -- GazeboPayloadBackend'in bekledigi protokol -----------------------

    def set_payload_model_name(self, model_name: str) -> None:
        """Hedef payload modelini calisma zamaninda degistirir.

        GazeboPayloadBackend.select_payload() bunu cagirir. Gerekce: Gorev
        2'de birakma sirasi artik tespit sirasini takip ediyor, dolayisiyla
        Gorev 3'un alacagi payload derleme zamaninda bilinmiyor."""
        if not model_name:
            raise ValueError("model_name bos olamaz -- sessiz bir varsayilan "
                             "yanlis payload'a kaynaklanma riskidir.")
        self.payload_model_name = model_name

    def hook_state(self) -> Optional[bool]:
        """Son gözlenen /hook/state. None = henüz hiç geçiş görülmedi.
        Buffered: latch'siz tek-seferlik yayın bir kez yakalandıktan sonra
        kaybolmaz."""
        return self._state

    def is_state_stream_ready(self) -> bool:
        return self._stream_ready

    async def wait_for_hook_state(self, expected: bool) -> bool:
        """/hook/state `expected` değerine ULAŞANA KADAR bekler.

        Zaman aşımı YOK ve poll/sleep YOK -- olay güdümlü. Süreyi
        PayloadManager'ın asyncio.wait_for'u sınırlar ve bu coroutine'i
        iptal eder. clear() KASITLI olarak kontrolden ÖNCE: aksi halde
        kontrol ile bekleme arasına düşen bir güncelleme kaybolurdu."""
        while True:
            self._state_event.clear()
            if self._state is expected:
                return True
            await self._state_event.wait()

    async def publish_attach(self, model_name: Optional[str] = None) -> bool:
        """/hook/attach'e StringMsg(data=<child model adı>) yayınlar.

        Akış hazır değilken REDDEDER: onayı gözlenemeyecek bir attach
        yayınlamak, joint oluşsa bile timeout'la sonuçlanır (modül
        docstring'indeki RACE FIX)."""
        name = model_name or self.payload_model_name
        if not self._stream_ready:
            logger.error("GzHookClient: /hook/state aboneligi hazir DEGIL -- "
                         "/hook/attach YAYINLANMADI (onay gozlenemezdi).")
            return False
        return await self._publish(HOOK_ATTACH_TOPIC, "gz.msgs.StringMsg",
                                   f'data: "{name}"')

    async def publish_detach(self) -> bool:
        """/hook/detach'e Boolean(data=true) yayınlar.

        Yalnızca true: plugin false'u sessizce yok sayar
        (HookAttachSystem.cc:150-151). is_state_stream_ready() kapısı
        KASITLI olarak YOK -- bırakmayı gözlemlenebilirlik yüzünden
        engellemek payload'ı araca takılı bırakırdı."""
        return await self._publish(HOOK_DETACH_TOPIC, "gz.msgs.Boolean", "data: true")

    async def _publish(self, topic: str, msg_type: str, payload: str) -> bool:
        cmd = ["gz", "topic", "-t", topic, "-m", msg_type, "-p", payload]
        logger.info("GzHookClient: %s <- %s", topic, payload)
        try:
            proc = await self._subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("GzHookClient: %s yayini basarisiz: %s", topic,
                             (stderr or b"").decode(errors="replace").strip())
                return False
            return True
        except FileNotFoundError:
            logger.error("`gz` CLI bulunamadi -- Gazebo ortami PATH'te degil.")
            return False
        except Exception as e:  # noqa: BLE001
            logger.error("GzHookClient: %s yayini istisna verdi: %s", topic, e)
            return False

    def pose(self, model_name: str) -> Optional[Pose]:
        """GazeboPayloadBackend.is_in_capture_zone()'un kullandığı poz
        okuması -- gz_pose_monitor.py cache'ine delege eder."""
        return self.pose_monitor.get(model_name)

    def read_vehicle_payload_distance(self) -> Optional[float]:
        """Araç ile payload arasındaki mesafe (m), poz bilinmiyorsa None.

        Modül seviyesindeki TEK formüle (_distance) delege eder. İki çağıran
        da buradan geçer: GazeboPayloadBackend.is_in_capture_zone()'un
        FLEX-20 guard'lı yolu ve FLEX-20 karakterizasyon scriptinin
        PayloadManager'ı bypass eden yolu."""
        return _distance(self.pose(self.payload_model_name),
                         self.pose(self.vehicle_model_name))

    def read_vehicle_payload_clearance(self) -> Optional[float]:
        """Aracın altı ile payload üstü arasındaki dikey açıklık (m).

        GazeboPayloadBackend.is_in_capture_zone()'un FLEX-20 ile
        karşılaştırdığı büyüklük budur. Modül seviyesindeki TEK formüle
        (_vertical_clearance) delege eder; backend kendi hesabını TUTMAZ."""
        return _vertical_clearance(self.pose(self.payload_model_name),
                                   self.pose(self.vehicle_model_name))

    @staticmethod
    def gz_cli_available() -> bool:
        return shutil.which("gz") is not None
