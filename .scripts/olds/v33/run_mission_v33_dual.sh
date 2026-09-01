#!/bin/bash
# run_mission_v33_dual - Mission Executor Launcher (Eşzamanlı Simülasyon + Gerçek)

cd "$(dirname "$0")"
clear
echo "====================================="
echo " KURSAD40 V33 DUAL MODE (Gölge Test)"
echo " Mission Executor"
echo "====================================="
echo ""
export PYTHONPATH=$(pwd)/v33_flight_stack

source "$(dirname "$0")/resolve_python.sh"

# --- OTOMATIK KOSU KAYDI (2026-08-25) ---------------------------------------
# Ham log'a DOKUNMAZ; yaninda kucuk, olgu-only bir kayit uretir
# (docs/test-history/runs/<mission_id>.md).
#
# NEDEN IKI ADIM: kaydi yalnizca son satirda uretmek GUVENILIR DEGIL --
# launcher'a sinyal gonderildiginde (Ctrl-C, kill) script o satira
# ulasmayabiliyor. OLCULDU (2026-08-25): kabuk sinyal semantigi tekrarli
# denemelerde TUTARSIZ davrandi, uzerine guvenilirlik insa edilemez.
#
# Kayit zaten TAMAMEN diskteki .jsonl'den turetildigi icin cikis ANINDA
# uretilmek zorunda degil. Bu yuzden:
#   1) BASTA backfill  -- onceki kosulardan eksik kalan ne varsa tamamlar
#   2) SONDA best-effort -- normal bitiste kayit hemen olusur
# En kotu durumda (sert kill) kayit BIR SONRAKI kosuda olusur, ASLA kaybolmaz.
#
# Ikisi de `|| true` + arac'in kendi `return 0`'i ile korunuyor: kayit uretimi
# bir kosuyu ASLA basarisiz gosteremez ve mission'in cikis kodunu maskelemez.
"$PYTHON_BIN" -u v33_flight_stack/tools/run_record.py \
    --repo-root "$(pwd)/v33_flight_stack" --backfill || true

"$PYTHON_BIN" -u v33_flight_stack/dual_system/main_dual.py "$@"
MISSION_RC=$?

"$PYTHON_BIN" -u v33_flight_stack/tools/run_record.py \
    --repo-root "$(pwd)/v33_flight_stack" --latest --exit-code "$MISSION_RC" || true

exit $MISSION_RC
