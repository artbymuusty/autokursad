#!/bin/bash
# =============================================================================
#  KURSAD40 V34 -- GZ SITL CANLI DEMO  (tek komut)
# =============================================================================
# Simulatoru ayaga kaldirir, gorevi unified dashboard ACIK olarak baslatir,
# demo bitince her seyi temizler.
#
#   .scripts/olds/v34/demo/run_demo_gz.sh
#
# Ctrl-C her an guvenlidir: ADR-010 R4 sinyal isleyicisi araci baslangic/bitis
# noktasina goturup indirir (en fazla ABORT_RETURN_DEADLINE_S=45 s), sonra
# temizlik calisir.
#
# Ortam degiskenleri (hepsi opsiyonel):
#   DEMO_MAX_S=360              gorev bu surede bitmezse kontrollu durdurulur
#   KURSAD40_DASH_FULLSCREEN=1  dashboard'u tam ekran ac (varsayilan: pencere)
#   KURSAD40_UNIFIED_DASHBOARD=0  dashboard'u hic acma (yalnizca log)
#
# NOT: demo loglari demo_logs/ altina yazilir -- gercek test loglariyla
# (logs/) KARISMAZ. Bunu saglayan sey KURSAD40_LOG_DIR: hem main_gz hem
# unified dashboard ayni degiskeni okur.
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." &> /dev/null && pwd)"
V34="$REPO/.scripts/olds/v34"
STACK="$V34/v34_flight_stack"
DEMO_LOGS="$STACK/demo_logs"
STAMP="$(date +%Y%m%d_%H%M%S)"
SIMLOG="$DEMO_LOGS/demo_${STAMP}_sim.log"
MISLOG="$DEMO_LOGS/demo_${STAMP}_mission.log"
FIFO="/tmp/kursad_demo_${STAMP}.fifo"
DEMO_MAX_S="${DEMO_MAX_S:-360}"

LP=""; HP=""; MP=""

cleanup() {
    echo ""
    echo "[DEMO] Temizlik..."
    if [ -n "$MP" ] && kill -0 "$MP" 2>/dev/null; then
        # Once KONTROLLU durdur: arac donup insin.
        pkill -INT -f "main_gz.py" 2>/dev/null
        for _ in $(seq 1 60); do
            pgrep -f "main_gz.py" >/dev/null 2>&1 || break
            sleep 1
        done
    fi
    pkill -9 -f "main_gz.py" 2>/dev/null
    pkill -9 -f "mission_dashboard_unified.py" 2>/dev/null
    pkill -9 -f "camera_service.py" 2>/dev/null
    [ -n "$LP" ] && kill "$LP" 2>/dev/null
    [ -n "$HP" ] && kill "$HP" 2>/dev/null
    pkill -9 -f "bin/px4$" 2>/dev/null
    pkill -9 -f "gz sim" 2>/dev/null
    # safe_sitl_launcher.sh adim 6/6'da clear_land_mode.py'yi baslatiyor; o da
    # kendi mavsdk_server'ini doguruyor ve UDP 14540'i tutuyor. Dogrulanana
    # kadar tekrarla, yoksa SONRAKI kosum "Address already in use" alir.
    for _ in 1 2 3 4 5; do
        pkill -9 -f "safe_sitl_launcher.sh" 2>/dev/null
        pkill -9 -f "clear_land_mode.py" 2>/dev/null
        pkill -9 -f "mavsdk/bin/mavsdk_server" 2>/dev/null
        sleep 1
        pgrep -f "mavsdk/bin/mavsdk_server" >/dev/null 2>&1 || break
    done
    rm -f "$FIFO"
    echo "[DEMO] Bitti."
    echo "[DEMO]   sim log     : $SIMLOG"
    echo "[DEMO]   gorev log   : $MISLOG"
    echo "[DEMO]   olay kaydi  : $DEMO_LOGS/mission_<id>.jsonl"
    echo "[DEMO]   dashboard   : $DEMO_LOGS/dashboard_snapshot.png (son kare)"
}
trap cleanup EXIT INT TERM

mkdir -p "$DEMO_LOGS"
echo "==========================================================="
echo " KURSAD40 V34 -- GZ SITL CANLI DEMO"
echo "==========================================================="
echo "[DEMO] loglar: $DEMO_LOGS"

# On temizlik: onceki bir kosum yetim birakmis olabilir.
pkill -9 -f "clear_land_mode.py" 2>/dev/null
pkill -9 -f "mavsdk/bin/mavsdk_server" 2>/dev/null && sleep 1

# stdin'i ACIK tutan FIFO: /dev/null verilirse PX4'un pxh kabugu EOF'ta
# prompt'u sonsuz dongude yeniden cizer (olculdu: 60 s'de 186 MB log).
rm -f "$FIFO"; mkfifo "$FIFO"
sleep 86400 > "$FIFO" 2>/dev/null & HP=$!

echo "[DEMO] 1/3 Simulator baslatiliyor (safe_sitl_launcher.sh)..."
( cd "$REPO" && ./safe_sitl_launcher.sh ) < "$FIFO" > "$SIMLOG" 2>&1 & LP=$!

for _ in $(seq 1 150); do
    grep -qa "Ready for takeoff" "$SIMLOG" && break
    kill -0 "$LP" 2>/dev/null || { echo "[DEMO] HATA: launcher hazir olmadan cikti."; tail -20 "$SIMLOG"; exit 1; }
    sleep 2
done
grep -qa "Ready for takeoff" "$SIMLOG" || { echo "[DEMO] HATA: PX4 300 s icinde hazir olmadi."; tail -20 "$SIMLOG"; exit 1; }
echo "[DEMO]     PX4 hazir (Ready for takeoff)."

echo "[DEMO] 2/3 Gorev + dashboard baslatiliyor..."
cd "$V34"
KURSAD40_LOG_DIR="$DEMO_LOGS" \
KURSAD40_DASH_SNAPSHOT="${KURSAD40_DASH_SNAPSHOT:-$DEMO_LOGS/dashboard_snapshot.png}" \
KURSAD40_DASH_SNAPSHOT_EVERY_S="${KURSAD40_DASH_SNAPSHOT_EVERY_S:-5}" \
KURSAD40_DASH_FULLSCREEN="${KURSAD40_DASH_FULLSCREEN:-0}" \
KURSAD40_UNIFIED_DASHBOARD="${KURSAD40_UNIFIED_DASHBOARD:-1}" \
    ./run_mission_v34_gz.sh > "$MISLOG" 2>&1 & MP=$!

echo "[DEMO] 3/3 Gorev calisiyor. Dashboard penceresi acilmali."
echo "[DEMO]     Canli takip:  tail -f $MISLOG"
echo "[DEMO]     Durdurmak icin Ctrl-C (arac donup iner)."
echo ""

for i in $(seq 1 "$DEMO_MAX_S"); do
    if ! kill -0 "$MP" 2>/dev/null; then
        echo "[DEMO] Gorev kendi kendine bitti (${i}s)."
        MP=""
        break
    fi
    sleep 1
done
if [ -n "$MP" ] && kill -0 "$MP" 2>/dev/null; then
    echo "[DEMO] DEMO_MAX_S=${DEMO_MAX_S}s doldu -- kontrollu durduruluyor."
fi
