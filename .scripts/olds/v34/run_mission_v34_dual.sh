#!/bin/bash
# run_mission_v34_dual - Mission Executor Launcher (Eşzamanlı Simülasyon + Gerçek)

cd "$(dirname "$0")"
clear
echo "====================================="
echo " KURSAD40 V34 DUAL MODE (Gölge Test)"
echo " Mission Executor"
echo "====================================="
echo ""
export PYTHONPATH=$(pwd)/v34_flight_stack

source "$(dirname "$0")/resolve_python.sh"

"$PYTHON_BIN" -u v34_flight_stack/dual_system/main_dual.py "$@"
