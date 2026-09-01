#!/usr/bin/env python3
"""Real (gerçek donanım) bench kalibrasyonu: FLEX-14..19 için HAM VERİ üretir.

HAM VERİ ÜRETİR, HİÇBİR FLEX'İ GÜNCELLEMEZ. Script payload_config.py'ye
HİÇBİR ŞEY YAZMAZ; değerleri operatör elle, ayrı bir adımda girer.
(tools/calibrate_flex20_gazebo.py ile aynı disiplin.)

--- BU SCRIPT NEYİ ÖLÇÜYOR (VE NEYİ ÖLÇMÜYOR) -----------------------------

Bu script FİZİKSEL SONUCU ÖLÇEMEZ. Kanca/kavrama mekanizmasının konumunu
okuyacak sensör veya telemetri yolu repoda YOK -- bu, RealPayloadBackend'in
`TODO(SAFETY)` başlığı altında belgelenmiş bilinen boşluğun ta kendisidir
(await_capture() ve altı sorgu metodu bu yüzden NotImplementedError).

Dolayısıyla tek doğrulama kaynağı OPERATÖRÜN GÖZÜDÜR. Script her denemede
durup "servo hareket etti mi?" diye SORAR ve cevabı ham veri olarak
kaydeder. Otomatik doğrulama YOKTUR ve taklit de EDİLMEZ: `set_actuator()`
çağrısının başarıyla dönmesi yalnızca "komut flight controller tarafından
kabul edildi" demektir, servonun fiziksel konuma ulaştığı anlamına GELMEZ
(real_payload_backend.py'nin merkezi sözleşmesi, aynen burada da geçerli).

--- TASARIM ---------------------------------------------------------------

  * MAVSDK `action` nesnesi DOĞRUDAN kullanılır. PayloadManager ve
    RealPayloadBackend devrede DEĞİLDİR (bypass). Bunun tek nedeni var:
    backend'in CALIBRATION GUARD'ı FLEX-14..19 None iken her komutu
    PayloadCalibrationError ile durdurur -- yani üretim API'si üzerinden
    kalibrasyon YAPILAMAZ, tavuk-yumurta. Guard doğru çalışıyor; bypass
    edilmesi gereken şey guard'ın kendisi değil, kalibrasyon anıdır.
    (Gazebo tarafında GzHookClient'ın doğrudan kullanılmasıyla birebir
    aynı gerekçe.)
  * İki prosedür, SAHA_HAZIRLIK_RAPORU.md'nin bench sırasıyla birebir:
      `index` alt komutu -> Adım 1: FLEX-14 / FLEX-15 (actuator index'i)
      `value` alt komutu -> Adım 2: FLEX-16/17/18/19 (uç değerler)
    Sıra bağlayıcıdır: `value` prosedürü, `index` prosedürünün bulduğu
    index'i --index ile ister. Script bu sırayı DAYATMAZ ama --index'i
    zorunlu tutarak atlanmasını imkânsız kılar.
  * Adım 3-5 (süre ölçümleri, capture envelope, montaj ölçümleri) BU
    SCRIPT'İN KAPSAMINDA DEĞİL: hiçbiri actuator komutu göndermekle
    ölçülmez (kronometre, tekrarlı yakalama denemesi, cetvel). Bunlar
    saha raporunda operatör prosedürü olarak duruyor.

--- NEDEN BAZI ARGÜMANLARIN VARSAYILANI YOK -------------------------------

`--indices` ve `--probe-value` ZORUNLUDUR, varsayılanları YOKTUR. Bu
kasıtlı ve FLEX disiplininin aynısı (TBD = None, tahmin yok):

  * `--indices`: geçerli actuator index kümesi uçuş kartının çıkış
    haritasına bağlıdır -- ki bu prosedürün BULMAYA çalıştığı şeyin ta
    kendisi. MAVSDK yalnızca "index 1'den başlar" diyor, üst sınır
    belirtmiyor (mavsdk/action.py::set_actuator docstring'i). Uydurulmuş
    bir üst sınır SESSİZ bir boşluk yaratırdı: operatör taramayı
    çalıştırır, servo hiç oynamaz, "kablolama bozuk" der -- oysa aranan
    index tarama aralığının dışındaydı.
  * `--probe-value`: index taramasında servoyu ne kadar süreceğimiz bir
    FİZİKSEL GÜVENLİK kararıdır ve mekanizmanın stroku bilinmeden
    verilemez. Kalibre edilmemiş bir değer servoyu mekanik sınıra
    dayayabilir (FLEX-16'nın WHY FLEXIBLE bloğunun uyardığı hasar riski).
    Operatör bu değeri tezgâhın başında, mekanizmayı görerek verir.

Buna karşılık `value` prosedürünün varsayılanları UYDURMA DEĞİL, belgeden
gelir: başlangıç 0.0 ve adım 0.05 payload_config.py'deki FLEX-16 "HOW TO
CALIBRATE" bloğunun ve SAHA_HAZIRLIK_RAPORU.md Adım 2'nin yazdığı
değerlerdir; ±1.0 sınırı ise MAVSDK'nın kendi sözleşmesidir
("normalized from [-1..1]").

--- GÜVENLİK --------------------------------------------------------------

Bu GERÇEK DONANIM, simülasyon değil. Her komuttan önce script durur,
ne göndereceğini yazar ve ENTER bekler. Ayrıca:

  * Script servoyu KENDİLİĞİNDEN nötre döndürmez. Döndürmek için "güvenli
    nötr değer" gerekirdi -- ki o da kalibre edilmemiş bir değerdir ve
    tam olarak burada uydurmamamız gereken şeydir. Servo, verilen son
    komutta KALIR; her turdan sonra bu açıkça yazdırılır.
  * `value` taramasında operatör "mekanik sınır" derse tarama ANINDA
    durur ve o satır aday olarak İŞARETLENMEZ (FLEX-16: "hedef konuma
    ulaşan İLK değeri al, sınıra dayanan değerleri ALMA").
  * `--dry-run` hiçbir MAVSDK bağlantısı KURMAZ ve hiçbir actuator
    komutu GÖNDERMEZ; sadece ne göndereceğini yazar. Donanım gelmeden
    prosedürün kendisi bu modda denenebilir.
"""
import argparse
import csv
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payload import payload_config  # noqa: E402
from payload.backends.real_payload_backend import (  # noqa: E402
    REQUIRED_FLEX_NAMES,
    uncalibrated_flex_names,
)

logger = logging.getLogger("calibrate_real_servos")

# MAVSDK sozlesmesi: "Value to set the actuator to (normalized from [-1..1])"
# (mavsdk/action.py::set_actuator). Uydurma degil, dogrudan kutuphaneden.
ACTUATOR_VALUE_ABS_LIMIT = 1.0

# MAVSDK sozlesmesi: "Index of actuator (starting with 1)". Ust sinir
# BELIRTILMEMISTIR -- bu yuzden --indices zorunludur (bkz. modul docstring'i).
ACTUATOR_MIN_INDEX = 1

# payload_config.py FLEX-16 "HOW TO CALIBRATE" + SAHA_HAZIRLIK_RAPORU.md
# Adim 2: "0.0'dan baslayip hedef yonde 0.05'lik adimlarla ilerle".
# Bu iki sayi BELGEDEN gelir, bu script'te secilmemistir.
VALUE_SWEEP_START = 0.0
VALUE_SWEEP_STEP = 0.05

# Hangi FLEX hangi servoya ait -- real_payload_backend.py'deki
# "Servo -> FLEX haritasi" docstring'inin veri karsiligi. Tek kaynak orasi;
# burasi operatore dogru mekanizmayi izlemesini soyleyebilmek icin var.
VALUE_FLEX_TARGETS = {
    "FLEX_16_SERVO2_DOWN_VALUE": ("Servo2", "kanca TAM INMIS konumda mi?"),
    "FLEX_17_SERVO3_GRAPPLE_VALUE": ("Servo3", "kavrama GUVENILIR tutuyor mu?"),
    "FLEX_18_SERVO2_REVERSE_VALUE": ("Servo2", "kanca TAM TOPLANMIS konumda mi?"),
    "FLEX_19_SERVO3_RELEASE_VALUE": ("Servo3", "payload TAM SERBEST kaldi mi?"),
}

INDEX_FLEX_TARGETS = {
    "Servo2": "FLEX_14_SERVO2_ACTUATOR_INDEX",
    "Servo3": "FLEX_15_SERVO3_ACTUATOR_INDEX",
}

# Tek satir semasi: iki prosedur de ayni CSV'ye yazar ki operatorun elinde
# tek bir ham veri dosyasi olsun.
CSV_COLUMNS = [
    "trial", "procedure", "target_flex", "servo", "actuator_index",
    "commanded_value", "rpc_accepted", "operator_answer", "verdict",
    "dry_run", "timestamp", "notes",
]

# verdict degerleri (CSV'de aynen gorunur)
MOVED = "MOVED"
NO_MOVE = "NO_MOVE"
NOT_THERE_YET = "NOT_THERE_YET"
REACHED = "REACHED"
MECHANICAL_LIMIT = "MECHANICAL_LIMIT"
RPC_REJECTED = "RPC_REJECTED"
ABORTED = "ABORTED"


class OperatorAbort(Exception):
    """Operator taramayi bitirdi (veya stdin tukendi). Hata degil, karar."""


class OperatorConsole:
    """Operatorle tek temas noktasi. Enjekte edilebilir olmasi kasitli:
    testler input() olmadan tam prosedur akisini surebilsin diye."""

    def __init__(self, in_stream=None, out_stream=None):
        self._in = in_stream if in_stream is not None else sys.stdin
        self._out = out_stream if out_stream is not None else sys.stdout

    def say(self, text: str = "") -> None:
        print(text, file=self._out)

    def _flush(self) -> None:
        if hasattr(self._out, "flush"):
            self._out.flush()

    def _readline(self) -> str:
        line = self._in.readline()
        if line == "":
            # stdin tukendi. Sessizce "hayir" saymak ham veriyi kirletirdi.
            raise OperatorAbort("stdin tukendi -- operator cevabi alinamadi")
        return line.strip().lower()

    def ask(self, question: str, choices: dict) -> str:
        """`choices`: {'y': 'aciklama', ...}. Gecerli cevap gelene kadar sorar.
        Gecersiz cevaplar SESSIZCE yorumlanmaz -- yeniden sorulur."""
        menu = "  ".join(f"[{key}] {label}" for key, label in choices.items())
        while True:
            self.say(question)
            self.say(f"    {menu}")
            self._flush()
            answer = self._readline()
            if answer in choices:
                return answer
            self.say(f"    !! gecersiz cevap: {answer!r} -- tekrar deneyin")

    def confirm_ready(self, what: str) -> None:
        """Komuttan ONCE fiziksel guvenlik kapisi. GERCEK DONANIM."""
        self.say("")
        self.say("!" * 70)
        self.say("!! DIKKAT -- SERVO FIZIKSEL OLARAK HAREKET EDECEK")
        self.say(f"!! Gonderilecek: {what}")
        self.say("!! Mekanizmanin etrafinin TEMIZ, pervanelerin CIKARIK oldugundan")
        self.say("!! emin olun. Hazir oldugunuzda ENTER'a basin (iptal: 's' + ENTER).")
        self.say("!" * 70)
        self._flush()
        if self._readline() == "s":
            raise OperatorAbort("operator komut oncesi iptal etti")


class DryRunAction:
    """--dry-run modunun actuator'u: HICBIR MAVSDK cagrisi yapmaz, ne
    yapacagini yazar. Gonderilen komutlari kaydeder (testler icin)."""

    def __init__(self, console: OperatorConsole):
        self._console = console
        self.calls = []

    async def set_actuator(self, index, value):
        self.calls.append((index, value))
        self._console.say(f"    [DRY-RUN] set_actuator(index={index}, value={value:+.2f}) "
                          f"-- GONDERILMEDI, gercek donanim yok")


async def connect_real_action(connection_string: str, console: OperatorConsole):
    """Gercek MAVSDK baglantisini KURAR ve `action` nesnesini dondurur.

    mavsdk import'u KASITLI OLARAK burada (modul basinda degil): --dry-run
    yolunun mavsdk'ya hic dokunmadigi boylece yapisal olarak garanti olur,
    bir bayrak kontrolune degil import grafigine dayanir."""
    from mavsdk import System

    console.say(f"MAVSDK baglantisi kuruluyor: {connection_string}")
    system = System()
    await system.connect(system_address=connection_string)
    async for state in system.core.connection_state():
        if state.is_connected:
            console.say("Baglanti KURULDU.")
            break
    return system.action


class CalibrationSession:
    """Iki prosedurun ortak govdesi: guvenlik kapisi -> komut -> operator
    gozlemi -> ham satir. FLEX'e HICBIR SEY YAZMAZ."""

    def __init__(self, action, console: OperatorConsole, dry_run: bool):
        self._action = action
        self._console = console
        self._dry_run = dry_run
        self.rows = []
        self._trial = 0

    async def _drive(self, index: int, value: float) -> bool:
        """Tek set_actuator cagrisi. Donus: RPC kabul edildi mi.

        DIKKAT: True = komut flight controller tarafindan kabul edildi.
        Servonun fiziksel konuma ulastigi anlamina GELMEZ -- bu ayrimin
        tek dogrulayicisi operatorun gozudur (bkz. modul docstring'i)."""
        try:
            await self._action.set_actuator(index, value)
        except Exception as exc:  # noqa: BLE001
            # ActionError dahil her sey: bench'te baglanti/izin hatalari da
            # ham veriye gecmeli, sessizce yutulmamali.
            self._console.say(f"    !! set_actuator REDDEDILDI: {exc}")
            return False
        return True

    def _record(self, procedure, target_flex, servo, index, value,
                rpc_accepted, answer, verdict, notes=""):
        self._trial += 1
        self.rows.append({
            "trial": self._trial, "procedure": procedure,
            "target_flex": target_flex, "servo": servo,
            "actuator_index": index, "commanded_value": value,
            "rpc_accepted": rpc_accepted, "operator_answer": answer,
            "verdict": verdict, "dry_run": self._dry_run,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "notes": notes,
        })

    # -- Adim 1: actuator index'i bul (FLEX-14 / FLEX-15) -----------------

    async def run_index_sweep(self, servo: str, indices, probe_value: float) -> None:
        """SAHA_HAZIRLIK_RAPORU.md Adim 1. Her index'i tek tek surer ve
        operatore hangisinde hareket oldugunu sorar."""
        target_flex = INDEX_FLEX_TARGETS[servo]
        self._console.say("")
        self._console.say(f"=== ADIM 1: {servo} actuator index taramasi -> {target_flex} ===")
        self._console.say(f"Taranacak index'ler: {list(indices)}   probe degeri: {probe_value:+.2f}")
        self._console.say(f"{servo} mekanizmasini GOZLEYIN: "
                          f"{'kanca (indirme/cekme)' if servo == 'Servo2' else 'kavrama (tutma/birakma)'}")

        for index in indices:
            try:
                self._console.confirm_ready(
                    f"index={index}, value={probe_value:+.2f}  ({servo} arastiriliyor)")
            except OperatorAbort:
                self._record("index", target_flex, servo, index, probe_value,
                             None, "s", ABORTED, "operator komut oncesi durdurdu")
                raise

            accepted = await self._drive(index, probe_value)
            if not accepted:
                # RPC reddedildiyse operatore sormanin anlami yok: servoya
                # komut hic ulasmadi, hareketsizlik bir bulgu DEGIL.
                self._record("index", target_flex, servo, index, probe_value,
                             False, None, RPC_REJECTED,
                             "komut kabul edilmedi -- hareketsizlik BULGU DEGIL")
                continue

            try:
                answer = self._console.ask(
                    f"  {servo} HAREKET ETTI MI? (index={index})",
                    {"y": "evet, hareket etti", "n": "hayir, kimildamadi",
                     "s": "taramayi durdur"})
            except OperatorAbort:
                self._record("index", target_flex, servo, index, probe_value,
                             True, None, ABORTED, "operator cevabi alinamadi")
                raise
            if answer == "s":
                self._record("index", target_flex, servo, index, probe_value,
                             True, answer, ABORTED, "operator taramayi durdurdu")
                raise OperatorAbort("operator taramayi durdurdu")

            self._record("index", target_flex, servo, index, probe_value,
                         True, answer, MOVED if answer == "y" else NO_MOVE)
            self._console.say(f"    NOT: servo son komutta KALDI (index={index}, "
                              f"value={probe_value:+.2f}) -- script notre DONDURMEZ.")

    # -- Adim 2: uc degerleri bul (FLEX-16..19) ---------------------------

    async def run_value_sweep(self, target_flex: str, index: int, direction: int,
                              step: float = VALUE_SWEEP_STEP,
                              start: float = VALUE_SWEEP_START) -> None:
        """SAHA_HAZIRLIK_RAPORU.md Adim 2. start'tan itibaren `direction`
        yonunde `step` adimlarla ilerler; operator "ulasti" diyene, "mekanik
        sinir" diyene veya ±1.0'a varilana kadar."""
        servo, question = VALUE_FLEX_TARGETS[target_flex]
        self._console.say("")
        self._console.say(f"=== ADIM 2: {target_flex} deger taramasi ({servo}, index={index}) ===")
        self._console.say(f"Baslangic {start:+.2f}, adim {step:.2f}, yon {'+' if direction > 0 else '-'}, "
                          f"sinir ±{ACTUATOR_VALUE_ABS_LIMIT:.1f}")
        self._console.say("KURAL: hedef konuma ulasan ILK degeri alin. Mekanik sinira")
        self._console.say("dayanan degeri ALMAYIN -- servo stall'a girer, donanim zarar gorur.")

        value = start
        while abs(value) <= ACTUATOR_VALUE_ABS_LIMIT + 1e-9:
            try:
                self._console.confirm_ready(f"index={index}, value={value:+.2f}  ({target_flex})")
            except OperatorAbort:
                self._record("value", target_flex, servo, index, round(value, 4),
                             None, "s", ABORTED, "operator komut oncesi durdurdu")
                raise

            accepted = await self._drive(index, round(value, 4))
            if not accepted:
                self._record("value", target_flex, servo, index, round(value, 4),
                             False, None, RPC_REJECTED,
                             "komut kabul edilmedi -- gozlem BULGU DEGIL")
                value += direction * step
                continue

            try:
                answer = self._console.ask(
                    f"  {question}  (value={value:+.2f})",
                    {"n": "henuz degil, devam et", "y": "EVET, hedef konumda",
                     "l": "MEKANIK SINIR -- dur", "s": "taramayi durdur"})
            except OperatorAbort:
                self._record("value", target_flex, servo, index, round(value, 4),
                             True, None, ABORTED, "operator cevabi alinamadi")
                raise

            if answer == "y":
                self._record("value", target_flex, servo, index, round(value, 4),
                             True, answer, REACHED)
                self._console.say(f"    Hedef konuma ulasildi: {value:+.2f}. Tarama bitti.")
                return
            if answer == "l":
                # FLEX-16 HOW TO CALIBRATE: sinira dayanan degerler ALINMAZ.
                # Bu satir CSV'ye girer ama ADAY OLARAK sayilmaz.
                self._record("value", target_flex, servo, index, round(value, 4),
                             True, answer, MECHANICAL_LIMIT,
                             "sinira dayandi -- ADAY DEGIL, tarama durduruldu")
                self._console.say(f"    MEKANIK SINIR ({value:+.2f}). Tarama DURDURULDU; "
                                  f"bu deger aday DEGILDIR.")
                return
            if answer == "s":
                self._record("value", target_flex, servo, index, round(value, 4),
                             True, answer, ABORTED, "operator taramayi durdurdu")
                raise OperatorAbort("operator taramayi durdurdu")

            self._record("value", target_flex, servo, index, round(value, 4),
                         True, answer, NOT_THERE_YET)
            value += direction * step

        self._console.say(f"    ±{ACTUATOR_VALUE_ABS_LIMIT:.1f} sinirina ulasildi, hedef konum "
                          f"BULUNAMADI. Bu bir BULGUDUR: mekanizma bu yonde bu servo ile "
                          f"hedefe varmiyor (yon/montaj/index gozden gecirilmeli).")

    # -- Rapor -------------------------------------------------------------

    def candidates(self) -> dict:
        """Ham satirlardan aday ozetini cikarir. SECIM YAPMAZ -- birden fazla
        aday varsa hepsini dondurur ve belirsizligi cagirana birakir."""
        found = {}
        for row in self.rows:
            if row["verdict"] == MOVED:
                found.setdefault(row["target_flex"], []).append(row["actuator_index"])
            elif row["verdict"] == REACHED:
                found.setdefault(row["target_flex"], []).append(row["commanded_value"])
        return found

    def print_table(self) -> None:
        header = (f"{'#':>2}  {'prosedur':>8}  {'FLEX':<30}  {'idx':>3}  "
                  f"{'deger':>6}  {'cevap':>5}  {'sonuc':<17}  notlar")
        self._console.say("")
        self._console.say(header)
        self._console.say("-" * len(header))
        for row in self.rows:
            value = row["commanded_value"]
            self._console.say(
                f"{row['trial']:>2}  {row['procedure']:>8}  {row['target_flex']:<30}  "
                f"{row['actuator_index']:>3}  "
                f"{('-' if value is None else f'{value:+.2f}'):>6}  "
                f"{str(row['operator_answer']):>5}  {row['verdict']:<17}  {row['notes']}")

    def write_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        self._console.say(f"\nHam veri yazildi: {path}")


def print_flex_reminder(console: OperatorConsole, session: CalibrationSession) -> None:
    """Gazebo script'inin _print_flex20_reminder()'inin Real karsiligi:
    hicbir sey yazilmadigini ACIKCA soyler ve mevcut degerleri gosterir."""
    console.say("=" * 74)
    console.say("HICBIR FLEX GUNCELLENMEDI -- bu script payload_config.py'ye HICBIR SEY YAZMAZ.")
    console.say("")
    for name in REQUIRED_FLEX_NAMES:
        console.say(f"  payload_config.{name} = {getattr(payload_config, name)!r}")
    console.say("")
    found = session.candidates()
    if found:
        console.say("  BU OTURUMUN ADAYLARI (ham gozlem, KARAR DEGIL):")
        for flex_name, values in found.items():
            marker = "  <-- BIRDEN FAZLA ADAY, BELIRSIZ" if len(values) > 1 else ""
            console.say(f"    {flex_name}: {values}{marker}")
    else:
        console.say("  BU OTURUMDA ADAY BULUNAMADI (hicbir tur MOVED/REACHED donmedi).")
    console.say("")
    console.say("  Degerleri payload_config.py'ye ELLE girin; ayni blokta CURRENT")
    console.say("  DEFAULT notunu da bu olcumle guncelleyin. Birden fazla aday varsa")
    console.say("  once belirsizligi cozun -- script sizin yerinize SECMEZ.")
    console.say("=" * 74)


async def main_async(args) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console = OperatorConsole()

    still_tbd = uncalibrated_flex_names()
    if not still_tbd:
        console.say("NOT: FLEX-14..19'un hepsi zaten dolu. Karakterizasyon yine de calisir "
                    "(bu script backend'i bypass eder), ama ONCEKI bir kalibrasyonun "
                    "uzerine bakiyorsunuz.")

    if args.dry_run:
        console.say("=" * 74)
        console.say("DRY-RUN: MAVSDK baglantisi KURULMAYACAK, actuator komutu GONDERILMEYECEK.")
        console.say("Prosedur akisi aynen calisir; sadece komutlar yazdirilir.")
        console.say("=" * 74)
        action = DryRunAction(console)
    else:
        action = await connect_real_action(args.connection, console)

    session = CalibrationSession(action, console, dry_run=args.dry_run)
    try:
        if args.procedure == "index":
            await session.run_index_sweep(args.servo, args.indices, args.probe_value)
        else:
            await session.run_value_sweep(args.flex, args.index,
                                          1 if args.direction == "+" else -1,
                                          step=args.step)
    except OperatorAbort as exc:
        console.say(f"\nTarama SONLANDIRILDI: {exc}")
        console.say("O ana kadarki ham veri yine de kaydediliyor.")

    session.print_table()
    session.write_csv(args.out)
    print_flex_reminder(console, session)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Real bench kalibrasyonu (FLEX-14..19) -- HAM VERI uretir, "
                    "hicbir FLEX'i GUNCELLEMEZ.")
    parser.add_argument("--connection", default="serial:///dev/ttyUSB0:57600",
                        help="MAVSDK baglanti dizesi (--dry-run ile kullanilmaz).")
    parser.add_argument("--dry-run", action="store_true",
                        help="MAVSDK'ya HIC dokunma; komutlari sadece yazdir.")
    parser.add_argument("--out", default=None,
                        help="CSV cikti yolu (varsayilan: logs/real_servo_calibration_<ts>.csv)")
    sub = parser.add_subparsers(dest="procedure", required=True)

    p_index = sub.add_parser("index", help="ADIM 1: actuator index'i bul (FLEX-14/15)")
    p_index.add_argument("--servo", required=True, choices=sorted(INDEX_FLEX_TARGETS))
    # Varsayilan YOK -- bkz. modul docstring'i "NEDEN BAZI ARGUMANLARIN
    # VARSAYILANI YOK". Uydurma bir ust sinir SESSIZ bir bosluk yaratirdi.
    p_index.add_argument("--indices", type=int, nargs="+", required=True,
                         help=f"Taranacak actuator index'leri (MAVSDK: "
                              f"{ACTUATOR_MIN_INDEX}'den baslar, ust sinir belirtilmemis).")
    p_index.add_argument("--probe-value", type=float, required=True,
                         help="Tarama sirasinda gonderilecek deger. VARSAYILANI YOK: "
                              "fiziksel guvenlik karari, mekanizmayi gorerek verin.")

    p_value = sub.add_parser("value", help="ADIM 2: uc degeri bul (FLEX-16..19)")
    p_value.add_argument("--flex", required=True, choices=sorted(VALUE_FLEX_TARGETS))
    p_value.add_argument("--index", type=int, required=True,
                         help="ADIM 1'de bulunan actuator index'i.")
    p_value.add_argument("--direction", required=True, choices=["+", "-"])
    p_value.add_argument("--step", type=float, default=VALUE_SWEEP_STEP,
                         help=f"Adim buyuklugu (varsayilan {VALUE_SWEEP_STEP}: "
                              f"payload_config FLEX-16 HOW TO CALIBRATE).")
    return parser


def validate_args(args) -> None:
    """argparse'in yakalayamadigi FIZIKSEL sozlesme ihlalleri. Hepsi
    komut gonderilmeden ONCE, tipki CALIBRATION GUARD gibi."""
    if args.procedure == "index":
        bad = [i for i in args.indices if i < ACTUATOR_MIN_INDEX]
        if bad:
            raise SystemExit(f"HATA: actuator index {ACTUATOR_MIN_INDEX}'den baslar "
                             f"(MAVSDK sozlesmesi). Gecersiz: {bad}")
        if abs(args.probe_value) > ACTUATOR_VALUE_ABS_LIMIT:
            raise SystemExit(f"HATA: --probe-value MAVSDK sinirinin disinda "
                             f"(|{args.probe_value}| > {ACTUATOR_VALUE_ABS_LIMIT}).")
    else:
        if args.index < ACTUATOR_MIN_INDEX:
            raise SystemExit(f"HATA: actuator index {ACTUATOR_MIN_INDEX}'den baslar "
                             f"(MAVSDK sozlesmesi). Verilen: {args.index}")
        if args.step <= 0:
            raise SystemExit(f"HATA: --step pozitif olmali (yon --direction ile verilir). "
                             f"Verilen: {args.step}")


def main(argv=None) -> int:
    import asyncio
    args = build_parser().parse_args(argv)
    validate_args(args)
    if args.out is None:
        args.out = os.path.join("logs", f"real_servo_calibration_{int(time.time())}.csv")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
