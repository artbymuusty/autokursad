#!/bin/bash
# FAZ 3 / ADIM 2 -- HOOK_PAYOUT_MARGIN_M taramasi.
#
# Her MARGIN degeri icin TAM bir demo kosusu (SITL yeniden baslatilir,
# Gorev 2 bastan kosar, ardindan Gorev 3 alma denenir). Amac iki soruyu
# ayni kosudan cevaplamak:
#   1. Oturma kapisi araliyor mu (CAPTURE_CANDIDATE > 0)?
#   2. Gorev 2 hala GOREV2_COMPLETE'e ulasiyor mu (zarar yok kaniti)?
set -uo pipefail
DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:?kullanim: margin_sweep.sh <cikti-dizini>}"
mkdir -p "$OUT"
MARGINS="${MARGINS:-0.02 0.04 0.06}"

for M in $MARGINS; do
    echo "==========================================================="
    echo "[SWEEP] MARGIN = $M m  ($(date +%H:%M:%S))"
    echo "==========================================================="
    KURSAD_HOOK_PAYOUT_MARGIN_M="$M" \
      "$DEMO/run_demo.sh" --plans "competition_1way" --mission-timeout 900 --no-dashboard \
      > "$OUT/demo_margin_${M}.log" 2>&1
    R="$(/bin/ls -td "$DEMO"/runs/*/ | head -1)"
    echo "$R" > "$OUT/rundir_${M}.txt"
    echo "[SWEEP] MARGIN=$M bitti -> $R"
done
echo "[SWEEP] TARAMA TAMAMLANDI"
