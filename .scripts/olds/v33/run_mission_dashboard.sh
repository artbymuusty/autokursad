#!/bin/bash
# run_mission_dashboard.sh - KURSAD40 Mission Dashboard v2 (bagimsiz izleyici)
#
# run_just_cam ile AYNI desen. Farki: bu arac camera_service'i BASLATMAZ --
# yalnizca mevcut ZMQ yayinina ikinci abone olur, JSONL/positions dosyalarini
# salt-okunur izler. Mission process'i calismiyorken de acilabilir; "waiting
# for mission..." ekraninda bekler.
#
# $0 GOREL YOL SORUNU: run_mission_v33_*.sh dosyalari once `cd "$(dirname "$0")"`
# yapip SONRA yine `"$(dirname "$0")/resolve_python.sh"` kaynak aliyor -- ikinci
# dirname yeni cwd'ye gore cozulemedigi icin gorel cagrimda ("./run_...sh")
# "No such file or directory" veriyorlar. Burada yol BASTA mutlaklastiriliyor,
# boylece script nereden cagrilirsa cagrilsin calisir.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR" || exit 1

clear
echo "====================================="
echo " KURSAD40 V33"
echo " Mission Dashboard v2 (read-only)"
echo "====================================="
echo ""

# Bu arac gz-transport'a HIC dokunmaz (kamera ZMQ'dan, telemetri dosyadan
# gelir), yani GZ_PARTITION/GZ_IP gerekmez. Yine de kaynak aliniyor: ileride
# bir gz sorgusu eklenirse sim ile ayni partition'da olmak zorunda ve bu
# dosya tek dogruluk kaynagi (gz_env.sh'in kendi yorumu).
source "$SCRIPT_DIR/v33_flight_stack/gz_system/gz_env.sh"

source "$SCRIPT_DIR/resolve_python.sh"

export PYTHONPATH="$SCRIPT_DIR/v33_flight_stack${PYTHONPATH:+:$PYTHONPATH}"

# argv[1]=log_dir (varsayilan .scripts/olds/v33/logs), argv[2]=zmq adresi
exec "$PYTHON_BIN" -u "$SCRIPT_DIR/v33_flight_stack/tools/mission_dashboard_v2.py" "$@"
