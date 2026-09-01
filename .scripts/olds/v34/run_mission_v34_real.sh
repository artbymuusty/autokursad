#!/bin/bash
# run_mission_v34_real - Mission Executor Launcher (Gerçek Uçuş)

cd "$(dirname "$0")"
clear
echo "====================================="
echo " KURSAD40 V34 GERÇEK UÇUŞ"
echo " Mission Executor"
echo "====================================="
echo ""
export PYTHONPATH=$(pwd)/v34_flight_stack

source "$(dirname "$0")/resolve_python.sh"

"$PYTHON_BIN" -u v34_flight_stack/real_system/main_real.py "$@"
