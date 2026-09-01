#!/bin/bash
# run_demo.sh -- KURSAD40 V34: hazirlanan TUM QGC .plan rotalari icin,
# SIRASIYLA, izlenebilir uctan uca gorev demosu.
#
# NE YAPAR
# --------
#   0. On kontrol   : px4 binary, gz, venv python, MAVSDK, .plan dosyalari
#   1. SITL         : safe_sitl_launcher.sh (PX4 + Gazebo, tek otorite)
#   2. Hazir bekle  : heartbeat -> EKF global/home -> is_armable
#   3. Dashboard    : tools/mission_dashboard_unified.py (AYRI, SALT-OKUNUR)
#   4. Her plan icin: rota yukle+dogrula -> LAND modu temizle -> gorev kos
#                     -> olay akisini ozetle -> artefaktlari sakla
#   5. Ozet         : plan basina SONUC tablosu, sonra teardown
#
# NEDEN ROTAYI BU SCRIPT YUKLUYOR
# --------------------------------
# Gorev 2 rotayi kendisi URETMEZ; `confirm_existing_mission()` yalnizca aracin
# uzerinde hazir bir rota arar (core/mission/phase.py MISSION_ROUTE_CONFIRM).
# Rotayi koymak operatorun QGroundControl'deki isidir. Demo'da operator yok,
# o yuzden demo/upload_plan.py QGC'nin SADECE bu isini yapar.
#
# HER SEY ARTEFAKT BIRAKIR
# ------------------------
# demo/runs/<zaman-damgasi>/ altinda: sitl.log, dashboard.log, plan basina
# klasor (upload.log, mission.log, olay jsonl'i, pozisyon json'u, summary.txt)
# ve en ustte SUMMARY.txt. Demo bittikten SONRA da bakilabilir olmasi asil amac.
#
# KULLANIM
#   ./run_demo.sh                      # tam demo (4 lane plani, sirayla)
#   ./run_demo.sh --dry-run            # SITL + rota yukleme dogrulamasi, gorev YOK
#   ./run_demo.sh --plans "competition_1way"
#   ./run_demo.sh --mission-timeout 300
#   ./run_demo.sh --no-dashboard       # headless/CI
#   ./run_demo.sh --keep-sitl          # bitince SITL'i acik birak
#   ./run_demo.sh --preflight-only     # sadece FAZ 0, hicbir sey baslatmaz

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
V34="$REPO/.scripts/olds/v34"
STACK="$V34/v34_flight_stack"
DEMO="$V34/demo"
MISSIONS_DIR="${KURSAD_MISSIONS_DIR:-$HOME/Documents/QGroundControl Daily/Missions}"

# Sira kasitli: once tek-yon (kisa, rota ve irtifa dogrulamasi), sonra iki-yon
# (U donusu ve run-out bacaklari dahil tam tarama).
#
# 2026-08-30: tek-parkur mimarisine gecildi. Eski lane_{A,B}_{1way,2way}
# planlari silindi; bu ikisi generate_competition_plans.py tarafindan
# tasarim sabitlerinden uretiliyor ve RTL/LAND icermiyorlar (Gorev 2 rota
# sozlesmesi -- eski lane planlari RTL ile bittigi icin dordu de arm
# etmeden MISSION_ROUTE_INVALID ile reddediliyordu).
PLANS_DEFAULT="competition_1way competition_2way"

PLANS="$PLANS_DEFAULT"
MISSION_TIMEOUT=900
DRY_RUN=0
USE_DASHBOARD=1
KEEP_SITL=0
PREFLIGHT_ONLY=0
SITL_READY_TIMEOUT=240

while [ $# -gt 0 ]; do
    case "$1" in
        --plans)            PLANS="$2"; shift 2 ;;
        --mission-timeout)  MISSION_TIMEOUT="$2"; shift 2 ;;
        --dry-run)          DRY_RUN=1; shift ;;
        --no-dashboard)     USE_DASHBOARD=0; shift ;;
        --keep-sitl)        KEEP_SITL=1; shift ;;
        --preflight-only)   PREFLIGHT_ONLY=1; shift ;;
        -h|--help)          sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "bilinmeyen secenek: $1"; exit 2 ;;
    esac
done

RUN_ID="$(date +%Y%m%dT%H%M%S)"
RUN_DIR="$DEMO/runs/$RUN_ID"
mkdir -p "$RUN_DIR"
SUMMARY="$RUN_DIR/SUMMARY.txt"

# ---------------------------------------------------------------------------
# Cikti yardimcilari -- her satir zaman damgali, cunku demo bittikten sonra
# "bu ne kadar surdu" sorusu loga bakilarak cevaplanabilmeli.
# ---------------------------------------------------------------------------
T_START=$(date +%s)
_ts() { printf '%02d:%02d' $(( ($(date +%s)-T_START)/60 )) $(( ($(date +%s)-T_START)%60 )); }
say()  { echo "[$(_ts)] $*" | tee -a "$RUN_DIR/demo.log"; }
head1() { echo | tee -a "$RUN_DIR/demo.log"
          echo "===========================================================" | tee -a "$RUN_DIR/demo.log"
          echo "[$(_ts)] $*" | tee -a "$RUN_DIR/demo.log"
          echo "===========================================================" | tee -a "$RUN_DIR/demo.log"; }

# ---------------------------------------------------------------------------
# Teardown -- normal bitiste, hatada ve Ctrl-C'de ayni yol.
# safe_sitl_launcher.sh'in ANCHORED pattern'leri bilerek aynen kullanildi:
# unanchored "px4" bu kabuklarin kendisini de oldururdu (o dosyanin ADR-010 R3
# yorumuna bakiniz).
# ---------------------------------------------------------------------------
DASH_PID=""; SITL_PID=""; FIFO=""; SITL_STARTED=0
_teardown() {
    local rc=$?
    trap - EXIT INT TERM
    head1 "TEARDOWN"
    if [ -n "$DASH_PID" ] && kill -0 "$DASH_PID" 2>/dev/null; then
        say "dashboard kapatiliyor (pid=$DASH_PID)"
        kill "$DASH_PID" 2>/dev/null
        for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$DASH_PID" 2>/dev/null || break; sleep 0.3; done
        kill -9 "$DASH_PID" 2>/dev/null
    fi
    pkill -f "gz_system/main_gz.py" 2>/dev/null
    pkill -f "camera_service.py" 2>/dev/null
    # mavsdk_server: her MAVSDK System() kendi sunucusunu ayaga kaldirip UDP
    # 14540'i bind eder. Onceki kosudan kalan bir tanesi bir sonrakinin
    # bind'ini engelliyor; wait_for_vehicle gRPC "Stream removed (Socket
    # closed)" ile duserek demoyu gorev HIC BASLAMADAN asiyor (2026-08-31).
    pkill -f "mavsdk_server" 2>/dev/null
    if [ "$SITL_STARTED" != "1" ]; then
        # Bu script hicbir simulator baslatmadi (on kontrol dustu ya da
        # --preflight-only). Baskasinin calistirdigi PX4/Gazebo'yu oldurmek
        # bu script'in isi degil -- hicbir pkill yapilmaz.
        say "SITL bu kosuda baslatilmadi -- hicbir surece dokunulmadi"
    elif [ "$KEEP_SITL" = "1" ]; then
        say "SITL ACIK BIRAKILDI (--keep-sitl). Kapatmak icin:"
        say "  pkill -9 -f 'bin/px4\$'; pkill -9 -f 'gz sim'"
    else
        say "SITL kapatiliyor"
        [ -n "$SITL_PID" ] && kill "$SITL_PID" 2>/dev/null
        pkill -9 -f "px4_sitl_default/bin/px4$" 2>/dev/null
        pkill -9 -f "bin/px4$" 2>/dev/null
        pkill -9 -f "gz sim" 2>/dev/null
        pkill -9 -f "gz-transport-topic" 2>/dev/null
        pkill -9 -f "ruby-mri" 2>/dev/null
    fi
    [ -n "$FIFO" ] && rm -f "$FIFO"
    say "artefaktlar: $RUN_DIR"
    exit $rc
}
trap _teardown EXIT INT TERM

# ---------------------------------------------------------------------------
# `timeout(1)` bu makinede yok (coreutils kurulu degil). Alt surec arka planda
# baslatilir, deadline'a kadar yoklanir; asarsa once TERM, sonra KILL, ayrica
# gorevin kendi alt sureclerine (camera_service) de dokunulur -- yoksa bir
# sonraki plan 5555'i bind edemez.
# ---------------------------------------------------------------------------
run_limited() {
    local secs="$1"; shift
    "$@" &
    local pid=$! elapsed=0
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$elapsed" -ge "$secs" ]; then
            say "  !! ${secs}s duvar limiti asildi -- surec sonlandiriliyor"
            kill -TERM "$pid" 2>/dev/null
            for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
            kill -9 "$pid" 2>/dev/null
            pkill -f "gz_system/main_gz.py" 2>/dev/null
            pkill -f "camera_service.py" 2>/dev/null
            wait "$pid" 2>/dev/null
            return 124
        fi
        sleep 2; elapsed=$((elapsed+2))
    done
    wait "$pid"; return $?
}

# ===========================================================================
head1 "FAZ 0/5 -- ON KONTROL"
# ===========================================================================
FAIL=0
check() { # check <etiket> <kosul-cikis-kodu> <detay>
    if [ "$2" = "0" ]; then say "  [OK]   $1${3:+  -- $3}"
    else say "  [HATA] $1${3:+  -- $3}"; FAIL=1; fi
}

# resolve_python.sh $VIRTUAL_ENV / $KURSAD40_VENV'i ciplak okur; `set -u`
# altinda bu "unbound variable" ile duser. Sadece o source icin -u kapatilir.
set +u; source "$V34/resolve_python.sh"; set -u
PYTHON="${PYTHON_BIN:-python3}"
say "python: $PYTHON"

[ -x "$REPO/build/px4_sitl_default/bin/px4" ]; check "PX4 SITL binary" $? "$REPO/build/px4_sitl_default/bin/px4"
command -v gz >/dev/null 2>&1;                 check "gz (Gazebo)" $? "$(command -v gz 2>/dev/null) $(gz sim --versions 2>/dev/null | head -1)"
"$PYTHON" -c "import mavsdk" 2>/dev/null;      check "python: mavsdk" $?
"$PYTHON" -c "import cv2, zmq, numpy" 2>/dev/null; check "python: cv2/zmq/numpy (dashboard)" $?
[ -x "$REPO/safe_sitl_launcher.sh" ];          check "safe_sitl_launcher.sh" $?
[ -d "$MISSIONS_DIR" ];                        check "QGC missions dizini" $? "$MISSIONS_DIR"

PLAN_PATHS=()
for p in $PLANS; do
    f="$MISSIONS_DIR/$p.plan"
    if [ -f "$f" ]; then
        n=$("$PYTHON" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['mission']['items']))" "$f" 2>/dev/null)
        check "plan: $p.plan" 0 "${n:-?} waypoint"
        PLAN_PATHS+=("$f")
    else
        check "plan: $p.plan" 1 "bulunamadi: $f"
    fi
done

if [ "$FAIL" != "0" ]; then
    say ""
    say "ON KONTROL BASARISIZ -- demo baslatilmadi. Yukaridaki [HATA] satirlarina bakin."
    exit 1
fi
say "on kontrol temiz: ${#PLAN_PATHS[@]} plan sirayla kosulacak"

if [ "$PREFLIGHT_ONLY" = "1" ]; then
    say "--preflight-only: SITL baslatilmadi, cikiliyor"
    exit 0
fi

# ===========================================================================
head1 "FAZ 1/5 -- PX4 SITL + GAZEBO"
# ===========================================================================
# PX4'un NSH kabugu stdin'den okur. /dev/null verirsek aninda EOF alip cikar,
# o yuzden bir FIFO aciyoruz ve yazan ucunu bu kabukta acik tutuyoruz (fd 9):
# hicbir sey yazilmaz, sadece EOF olusmaz.
FIFO="$RUN_DIR/px4_stdin.fifo"
mkfifo "$FIFO"
exec 9<>"$FIFO"

say "safe_sitl_launcher.sh baslatiliyor (log: $RUN_DIR/sitl.log)"
"$REPO/safe_sitl_launcher.sh" < "$FIFO" > "$RUN_DIR/sitl.log" 2>&1 &
SITL_PID=$!
SITL_STARTED=1
say "  pid=$SITL_PID"

# ===========================================================================
head1 "FAZ 2/5 -- ARAC HAZIR MI"
# ===========================================================================
# Her MAVSDK System() kendi mavsdk_server'ini ayaga kaldirip UDP 14540'i bind
# eder. Onceki kosudan kalan bir tanesi ya bind'i engelleyip gRPC "Stream
# removed" ile dusuruyor, ya da baglantiyi ASIYOR: 2026-08-31'de
# wait_for_vehicle.py kendi 240 s timeout'una RAGMEN 40 dakika asili kaldi,
# PX4 "Ready for takeoff" demis olmasina ragmen. Teardown zaten topluyor ama
# kosular ARASINDA olmesi yetmiyor -- basta da temizle.
pkill -f "mavsdk_server" 2>/dev/null
# run_limited: Python'un KENDI timeout'una guvenmeyen, kabuk duzeyinde sert
# sinir. wait_for_vehicle.py'nin ic timeout'u asyncio/gRPC katmaninda
# takilabiliyor; bu sinir surecin kendisini oldurur ve demo asili kalmaz.
run_limited $((SITL_READY_TIMEOUT + 60)) \
    "$PYTHON" -u "$DEMO/wait_for_vehicle.py" "$SITL_READY_TIMEOUT" 2>&1 | tee -a "$RUN_DIR/demo.log"
if [ "${PIPESTATUS[0]}" != "0" ]; then
    say "SITL ${SITL_READY_TIMEOUT}s icinde ucusa hazir hale gelmedi. sitl.log son 40 satir:"
    tail -40 "$RUN_DIR/sitl.log" | tee -a "$RUN_DIR/demo.log"
    exit 1
fi

# ===========================================================================
head1 "FAZ 3/5 -- MISSION DASHBOARD"
# ===========================================================================
if [ "$USE_DASHBOARD" = "1" ]; then
    # run_mission_v34_gz.sh ile ayni sekilde: AYRI process, salt-okunur, mission
    # runtime'ina hicbir baglantisi yok. Gorevlerden ONCE baslatilir ki ilk
    # olaylar (CHECKPOINT_SAVED, MISSION_START) ekrana ilk saniyeden itibaren
    # dussun.
    mkdir -p "$V34/logs"
    ( cd "$V34" && source "$STACK/gz_system/gz_env.sh" \
      && PYTHONPATH="$STACK" "$PYTHON" -u "$STACK/tools/mission_dashboard_unified.py" \
         >> "$RUN_DIR/dashboard.log" 2>&1 ) &
    DASH_PID=$!
    sleep 3
    if kill -0 "$DASH_PID" 2>/dev/null; then
        say "dashboard acildi (pid=$DASH_PID, log: $RUN_DIR/dashboard.log)"
    else
        say "UYARI: dashboard acilmadi -- demo gorevlerle devam ediyor. dashboard.log:"
        tail -20 "$RUN_DIR/dashboard.log" | tee -a "$RUN_DIR/demo.log"
        DASH_PID=""
    fi
else
    say "dashboard KAPALI (--no-dashboard)"
fi

# ===========================================================================
head1 "FAZ 4/5 -- PLANLAR (SIRAYLA)"
# ===========================================================================
: > "$SUMMARY"
{
  echo "KURSAD40 V34 -- demo $RUN_ID"
  echo "plan sirasi: $PLANS"
  echo "gorev duvar limiti: ${MISSION_TIMEOUT}s   dry-run: $DRY_RUN"
  echo
  printf '%-4s %-16s %-10s %-12s %s\n' "#" "PLAN" "YUKLEME" "GOREV" "SONUC"
  printf '%s\n' "-------------------------------------------------------------------------"
} >> "$SUMMARY"

IDX=0
for plan_path in "${PLAN_PATHS[@]}"; do
    IDX=$((IDX+1))
    name="$(basename "$plan_path" .plan)"
    slot="$RUN_DIR/$(printf '%02d' $IDX)_$name"
    mkdir -p "$slot"

    head1 "PLAN $IDX/${#PLAN_PATHS[@]} -- $name"

    # --- 4a. rota yukle + geri okuyup dogrula ------------------------------
    say "rota yukleniyor ve dogrulaniyor"
    "$PYTHON" -u "$DEMO/upload_plan.py" "$plan_path" 2>&1 | tee "$slot/upload.log" | tee -a "$RUN_DIR/demo.log"
    up_rc=${PIPESTATUS[0]}
    if [ "$up_rc" != "0" ]; then
        say "YUKLEME BASARISIZ -- bu plan icin gorev KOSULMADI (yanlis rotayla ucmak gorev testi degildir)"
        printf '%-4s %-16s %-10s %-12s %s\n' "$IDX" "$name" "HATA" "-" "atlandi" >> "$SUMMARY"
        continue
    fi
    UPLOAD_CELL="OK"

    if [ "$DRY_RUN" = "1" ]; then
        say "--dry-run: gorev kosulmuyor, sadece yukleme dogrulandi"
        printf '%-4s %-16s %-10s %-12s %s\n' "$IDX" "$name" "OK" "atlandi" "dry-run" >> "$SUMMARY"
        continue
    fi

    # --- 4b. LAND modu temizligi -------------------------------------------
    # ADR-010 R3: onceki gorev indikten sonra PX4 flight_mode=LAND'de kalir ve
    # oradan arm etmeyi reddeder (is_armable False, ama tek tek her pre-arm
    # check True). Bu bir rig-reset islemi, gorev mantigi degil.
    if [ -f "$V34/../v32/clear_land_mode.py" ]; then
        say "LAND modu temizligi"
        "$PYTHON" -u "$V34/../v32/clear_land_mode.py" 2>&1 | tee -a "$slot/upload.log" | tee -a "$RUN_DIR/demo.log"
    fi

    # --- 4c. gorevi kos ----------------------------------------------------
    say "gorev basliyor (main_gz.py, duvar limiti ${MISSION_TIMEOUT}s)"
    say "  canli log: tail -f $slot/mission.log"
    BEFORE="$(/bin/ls "$V34/logs"/mission_*.jsonl 2>/dev/null | sort)"
    # gz-transport env'i main_gz.py zaten apply_gz_env() ile kendisi uyguluyor;
    # burada da veriyoruz ki `gz topic -l` gibi alt cagrilar da ayni partition'i
    # gorsun. env -i KULLANILMIYOR: macOS'ta cv2 penceresi acan bir surecin
    # bosaltilmis bir ortamda calismasi guvenilir degil.
    run_limited "$MISSION_TIMEOUT" \
        env GZ_PARTITION=kursad40 GZ_IP=127.0.0.1 PYTHONPATH="$STACK" \
        bash -c "cd '$V34' && exec '$PYTHON' -u '$STACK/gz_system/main_gz.py'" \
        > "$slot/mission.log" 2>&1
    m_rc=$?
    case $m_rc in
        0)   say "gorev sureci 0 ile bitti" ;;
        124) say "gorev DUVAR LIMITINDE kesildi (${MISSION_TIMEOUT}s)" ;;
        *)   say "gorev sureci $m_rc ile bitti" ;;
    esac

    # --- 4d. artefaktlar + ozet -------------------------------------------
    AFTER="$(/bin/ls "$V34/logs"/mission_*.jsonl 2>/dev/null | sort)"
    NEWJSONL="$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") | tail -1)"
    if [ -z "$NEWJSONL" ]; then
        say "UYARI: bu kosuda yeni olay dosyasi olusmadi -- gorev surecine hic girilmemis olabilir"
        printf '%-4s %-16s %-10s %-12s %s\n' "$IDX" "$name" "$UPLOAD_CELL" "rc=$m_rc" "olay yok" >> "$SUMMARY"
        continue
    fi
    MID="$(basename "$NEWJSONL" .jsonl)"; MID="${MID#mission_}"
    cp "$NEWJSONL" "$slot/" 2>/dev/null
    cp "$V34/logs/mission_positions_$MID.json" "$slot/" 2>/dev/null

    say "olay akisi ozeti ($MID)"
    "$PYTHON" -u "$DEMO/summarize_mission.py" "$slot/$(basename "$NEWJSONL")" \
        2>&1 | tee "$slot/summary.txt" | tee -a "$RUN_DIR/demo.log"
    s_rc=${PIPESTATUS[0]}
    OUTCOME="$(grep -m1 '^  SONUC:' "$slot/summary.txt" | sed 's/^  SONUC: //')"
    printf '%-4s %-16s %-10s %-12s %s\n' "$IDX" "$name" "$UPLOAD_CELL" "rc=$m_rc" "${OUTCOME:-?}" >> "$SUMMARY"

    # Bir sonraki plan icin 5555/5556 soketleri ve gz abonelikleri serbest kalsin.
    pkill -f "camera_service.py" 2>/dev/null
    sleep 5
done

# ===========================================================================
head1 "FAZ 5/5 -- OZET"
# ===========================================================================
cat "$SUMMARY" | tee -a "$RUN_DIR/demo.log"
say ""
say "her plan icin: $RUN_DIR/<NN>_<plan>/{upload.log,mission.log,summary.txt,mission_*.jsonl}"
