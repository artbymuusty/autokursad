#!/bin/bash
# run_mission_dashboard_unified.sh - KURSAD40 Mission Dashboard (unified)
#
# run_mission_dashboard.sh ile AYNI desen; farki, uc kolonlu tam ekran surumu
# ve ikinci bir ZMQ abonesi (tespit geometrisi, tcp://127.0.0.1:5556).
# camera_service'i BASLATMAZ, hicbir dosyaya yazmaz.
#
# $0 GOREL YOL SORUNU: run_mission_v33_*.sh dosyalari once `cd "$(dirname "$0")"`
# yapip SONRA yine `"$(dirname "$0")/resolve_python.sh"` kaynak aliyor -- ikinci
# dirname yeni cwd'ye gore cozulemedigi icin gorel cagrimda hata veriyorlar.
# Burada yol BASTA mutlaklastiriliyor.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR" || exit 1

clear
echo "====================================="
echo " KURSAD40 V33"
echo " Mission Dashboard UNIFIED (read-only)"
echo "====================================="
echo ""

# Bu arac gz-transport'a HIC dokunmaz (kamera ZMQ'dan, telemetri dosyadan,
# tespit ZMQ'dan gelir). gz_env.sh yine de kaynak aliniyor: tek dogruluk
# kaynagi odur ve ileride bir gz sorgusu eklenirse ayni partition gerekir.
source "$SCRIPT_DIR/v33_flight_stack/gz_system/gz_env.sh"

source "$SCRIPT_DIR/resolve_python.sh"

export PYTHONPATH="$SCRIPT_DIR/v33_flight_stack${PYTHONPATH:+:$PYTHONPATH}"

# argv[1]=log_dir, argv[2]=kamera zmq, argv[3]=tespit zmq
exec "$PYTHON_BIN" -u "$SCRIPT_DIR/v33_flight_stack/tools/mission_dashboard_unified.py" "$@"
