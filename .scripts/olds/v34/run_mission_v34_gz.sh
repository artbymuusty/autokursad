#!/bin/bash
# run_mission_v34_gz - Mission Executor Launcher (Gazebo Simulator)

cd "$(dirname "$0")"
clear
echo "====================================="
echo " KURSAD40 V34 GAZEBO SIMULATION"
echo " Mission Executor"
echo "====================================="
echo ""
export PYTHONPATH=$(pwd)/v34_flight_stack

# Shared gz-transport env (GZ_PARTITION/GZ_IP) -- must match the sim launcher,
# otherwise gz-transport discovery silently yields zero camera frames.
source "$(pwd)/v34_flight_stack/gz_system/gz_env.sh"

source "$(dirname "$0")/resolve_python.sh"

# --- UNIFIED DASHBOARD -------------------------------------------------------
# Sim akisinda in-process MissionOpsDashboard artik kurulmuyor (main_gz.py
# build_ops_center'a legacy_dashboard_default="0" veriyor). Izleme burada,
# AYRI bir process olarak otomatik acilir -- operatorun ikinci bir komut
# calistirmasi gerekmez.
#
# NEDEN MISSION'DAN ONCE: dashboard en yeni mission_*.jsonl'i tarayarak
# baglanir. Once baslatmak, ilk event'lerin (CHECKPOINT_SAVED, MISSION_START)
# yazildigi ani kacirmamasini garantiler. Zaten dosyayi BASTAN okudugu icin
# gec baglanma da veri kaybettirmez; bu yalnizca ekranin ilk saniyeden
# itibaren dolu olmasini saglar.
#
# SALT-OKUNUR: mission runtime'ina hicbir baglantisi yok, hicbir dosyaya
# yazmaz, camera_service'i BASLATMAZ. Coktugunde ya da kapatildiginda gorev
# etkilenmez.
#
# KURSAD40_UNIFIED_DASHBOARD=0 ile kapatilabilir (headless/CI kosulari icin;
# aksi halde cv2 penceresi acmaya calisirdi).
DASH_PID=""
_stop_unified_dashboard() {
    if [ -n "$DASH_PID" ] && kill -0 "$DASH_PID" 2>/dev/null; then
        kill "$DASH_PID" 2>/dev/null
        # Once nazik TERM, sonra sinirli bekleme, en son KILL: dashboard cv2
        # penceresini kendi thread'inde kapatiyor, ani KILL Qt/Cocoa uyarisi
        # birakiyor.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "$DASH_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -9 "$DASH_PID" 2>/dev/null
    fi
}
# EXIT: normal bitis, hata cikisi ve sinyal sonrasi kabuk cikisi -- ucu de.
# INT/TERM ayrica yakalanir ki Ctrl-C'de temizlik kabuk cikmadan once ossun.
trap _stop_unified_dashboard EXIT INT TERM

if [ "${KURSAD40_UNIFIED_DASHBOARD:-1}" != "0" ]; then
    mkdir -p logs
    "$PYTHON_BIN" -u "$(pwd)/v34_flight_stack/tools/mission_dashboard_unified.py" \
        >> logs/dashboard_unified.log 2>&1 &
    DASH_PID=$!
    echo "[LAUNCHER] Unified dashboard baslatildi (pid=$DASH_PID, log: logs/dashboard_unified.log)"
else
    echo "[LAUNCHER] Unified dashboard KAPALI (KURSAD40_UNIFIED_DASHBOARD=0)"
fi
# ---------------------------------------------------------------------------

"$PYTHON_BIN" -u v34_flight_stack/gz_system/main_gz.py "$@"
MISSION_RC=$?

_stop_unified_dashboard

exit $MISSION_RC
