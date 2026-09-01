#!/bin/bash
# N kez ayni demo kosusu (mekanizma 2 once/sonra karsilastirmasi icin).
set -uo pipefail
DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:?kullanim: repeat_runs.sh <cikti-dizini> [N]}"
N="${2:-3}"
mkdir -p "$OUT"
for i in $(seq 1 "$N"); do
    echo "==========================================================="
    echo "[REPEAT] kosu $i/$N  ($(date +%H:%M:%S))"
    echo "==========================================================="
    "$DEMO/run_demo.sh" --plans "competition_1way" --mission-timeout 900 --no-dashboard \
      > "$OUT/demo_run${i}.log" 2>&1
    /bin/ls -td "$DEMO"/runs/*/ | head -1 > "$OUT/rundir_${i}.txt"
    echo "[REPEAT] kosu $i bitti -> $(cat "$OUT/rundir_${i}.txt")"
done
echo "[REPEAT] TAMAMLANDI"
