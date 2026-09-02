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

source "$STACK_DIR/../resolve_python.sh" 2>/dev/null
PYTHON="${PYTHON_BIN:-python3}"

# Simulator ve testin gz-transport partition'i AYNI olmali, yoksa kesif
# sessizce bos doner (gz_env.sh'in kendi aciklamasi).
source "$STACK_DIR/gz_system/gz_env.sh"

echo "[SITL-IT] Test calistiriliyor..."
KURSAD_SITL=1 PYTHONPATH="$STACK_DIR" "$PYTHON" -m pytest \
    "$STACK_DIR/tests/integration" -q -s -p no:cacheprovider
