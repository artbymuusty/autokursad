#!/bin/bash
# Climb-then-Cruise entegrasyon testi -- simulatoru ayaga kaldirir, testi
# calistirir, her durumda temizler.
#
# Bu kod tabanindaki ILK canli-simulator kosum altyapisi; bugune kadar tum
# testler mock tabanliydi (docs/flight-control-analysis.md 2.5).
#
# Kullanim:  tests/integration/run_sitl_integration.sh
# Cikis kodu = pytest'in cikis kodu.

set -uo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
REPO_ROOT="$(cd "$STACK_DIR/../../../.." &> /dev/null && pwd)"
LAUNCHER="$REPO_ROOT/safe_sitl_launcher.sh"
READY_TIMEOUT_S="${KURSAD_SITL_READY_TIMEOUT_S:-180}"

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${KURSAD_SITL_LOG_DIR:-/tmp}"
SIM_LOG="$LOG_DIR/sitl_integration_${STAMP}_sim.log"
FIFO="$LOG_DIR/sitl_integration_${STAMP}.fifo"

LAUNCHER_PID=""
HOLDER_PID=""

cleanup() {
    local rc=$?
    echo "[SITL-IT] Temizlik..."
    [ -n "$LAUNCHER_PID" ] && kill "$LAUNCHER_PID" 2>/dev/null
    [ -n "$HOLDER_PID" ] && kill "$HOLDER_PID" 2>/dev/null
    # safe_sitl_launcher.sh'in kendi anchored desenleri (ADR-010 R3):
    # cipsiz "px4" deseni cagiranin kabuklarini da olduruyordu.
    pkill -9 -f "px4_sitl_default/bin/px4$" 2>/dev/null
    pkill -9 -f "bin/px4$" 2>/dev/null
    pkill -9 -f "gz sim" 2>/dev/null
    # mavsdk_server: MAVSDK-Python'un System() ile OTOMATIK baslattigi yardimci
    # surec. Testle birlikte olmuyor ve UDP 14540'i tutmaya devam ediyor;
    # bir sonraki kosum "bind error: Address already in use (udp_connection.cpp:93)"
    # alip sessizce oluyor. Olculdu 2026-09-02: iki basarisiz kosum ardinda
    # UC yetim mavsdk_server birikti. Desen gercek binary yoluna cipli
    # (ADR-010 R3'un anchored-pattern dersi).
    #
    # TEK ATISLIK bir pkill BURADA YETMEZ ve bunun nedeni ince: launcher'i
    # oldurup PX4'u pkill'ledigimizde safe_sitl_launcher.sh'in onundeki
    # `make` DONER, o da launcher'i ADIM 6/6'ya (clear_land_mode.py)
    # ilerletir. O script KENDI MAVSDK System()'ini kurar, yani BIZ
    # temizledikten SONRA yepyeni bir mavsdk_server dogar ve olmus bir
    # PX4'e sonsuza kadar baglanmaya calisir -- 14540'i tutarak.
    # Olculdu 2026-09-02: basarili bir kosumdan 59 dakika sonra hala
    # ayaktaydi, ebeveyni canli bir clear_land_mode.py idi.
    # Bu yuzden once hijyen zincirinin KENDISI kesilir, sonra dogrulanana
    # kadar tekrarlanir.
    for _ in 1 2 3 4 5; do
        pkill -9 -f "safe_sitl_launcher.sh" 2>/dev/null
        pkill -9 -f "clear_land_mode.py" 2>/dev/null
        pkill -9 -f "mavsdk/bin/mavsdk_server" 2>/dev/null
        sleep 1
        pgrep -f "mavsdk/bin/mavsdk_server" > /dev/null 2>&1 || break
    done
    if pgrep -f "mavsdk/bin/mavsdk_server" > /dev/null 2>&1; then
        echo "[SITL-IT] UYARI: mavsdk_server temizlenemedi -- sonraki kosum" >&2
        echo "[SITL-IT] 'bind error: Address already in use' alabilir." >&2
    fi
    rm -f "$FIFO"
    echo "[SITL-IT] Simulator logu: $SIM_LOG"
    exit $rc
}
trap cleanup EXIT INT TERM

if [ ! -x "$LAUNCHER" ]; then
    echo "[SITL-IT] HATA: launcher bulunamadi: $LAUNCHER" >&2
    exit 2
fi

# stdin'i ACIK TUTAN FIFO. /dev/null verilirse PX4'un pxh kabugu EOF'ta
# prompt'u sonsuz dongude yeniden cizer -- olculdu 2026-09-02: log 60
# saniyede 186 MB'a ulasti. FIFO ile pxh'nin read()'i bloklanir.
# ON TEMIZLIK: onceki bir kosum cokup yetim birakmis olabilir. safe_sitl_
# launcher.sh px4/gz icin bunu kendisi yapiyor ama mavsdk_server'i bilmiyor.
pkill -9 -f "clear_land_mode.py" 2>/dev/null
pkill -9 -f "mavsdk/bin/mavsdk_server" 2>/dev/null && sleep 1

rm -f "$FIFO"; mkfifo "$FIFO"
sleep 86400 > "$FIFO" 2>/dev/null &
HOLDER_PID=$!

echo "[SITL-IT] Simulator baslatiliyor -> $SIM_LOG"
( cd "$REPO_ROOT" && "$LAUNCHER" ) < "$FIFO" > "$SIM_LOG" 2>&1 &
LAUNCHER_PID=$!

echo "[SITL-IT] PX4 hazir olmasi bekleniyor (timeout ${READY_TIMEOUT_S}s)..."
deadline=$(( $(date +%s) + READY_TIMEOUT_S ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    if grep -qa "Ready for takeoff" "$SIM_LOG" 2>/dev/null; then ready=1; break; fi
    if ! kill -0 "$LAUNCHER_PID" 2>/dev/null; then
        echo "[SITL-IT] HATA: launcher hazir olmadan cikti." >&2
        tail -30 "$SIM_LOG" >&2
        exit 1
    fi
    sleep 2
done

if [ "$ready" -ne 1 ]; then
    echo "[SITL-IT] HATA: PX4 ${READY_TIMEOUT_S}s icinde hazir olmadi." >&2
    tail -30 "$SIM_LOG" >&2
    exit 1
fi
echo "[SITL-IT] PX4 hazir."

# set -u GECICI OLARAK KAPALI: resolve_python.sh ve gz_env.sh tanimsiz
# degiskene dokunuyor ve `set -u` altinda source edildiklerinde kabugu
# OLDURUYORLAR. Olculdu 2026-09-02: script "PX4 hazir." dedikten hemen sonra
# sessizce cikiyor, trap temizligi calisiyor ve pytest HIC baslamiyordu --
# hicbir hata mesaji olmadan. Bu iki dosya bu deponun paylasilan
# yardimcilari, imzalarini bu test icin degistirmek dogru olmaz.
set +u
source "$STACK_DIR/../resolve_python.sh" 2>/dev/null
PYTHON="${PYTHON_BIN:-python3}"

# Simulator ve testin gz-transport partition'i AYNI olmali, yoksa kesif
# sessizce bos doner (gz_env.sh'in kendi aciklamasi).
source "$STACK_DIR/gz_system/gz_env.sh"
set -u

if ! "$PYTHON" -c "import mavsdk" 2>/dev/null; then
    echo "[SITL-IT] HATA: python ($PYTHON) mavsdk goremiyor." >&2
    exit 2
fi
echo "[SITL-IT] python=$PYTHON GZ_PARTITION=${GZ_PARTITION:-?}"

echo "[SITL-IT] Test calistiriliyor..."
KURSAD_SITL=1 PYTHONPATH="$STACK_DIR" "$PYTHON" -m pytest \
    "$STACK_DIR/tests/integration" -q -s -p no:cacheprovider
