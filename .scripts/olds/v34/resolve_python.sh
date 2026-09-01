#!/bin/bash
# resolve_python.sh - shared Python interpreter resolution for KURSAD40 V34 launchers.
#
# PORTABILITY (Ubuntu -> macOS): the V34 launchers originally invoked
# "../../.venv/bin/python" directly, i.e. the Ubuntu repo-local venv at
# <repo>/.scripts/.venv. That path does not exist on macOS.
#
# CANONICAL ENVIRONMENT (2026-08-20): the KURSAD40 environment on this Mac is
# the WORKSPACE venv at ~/KURSAD40/.venv (Python 3.12, MAVSDK + kconfiglib +
# jinja2 + empy + the YOLO/OpenCV stack), one level ABOVE the autokursad repo.
# It was missing from this list entirely, so every candidate below failed and
# resolution fell through to `python3` on PATH -- which on this machine is
# Homebrew's /opt/homebrew/bin/python3 (3.14.7) with none of those packages.
# That is why clear_land_mode.py died with "ModuleNotFoundError: No module
# named 'mavsdk'" even though MAVSDK was installed and working. The workspace
# venv is now candidate #3.
#
# Source this file from a launcher; it sets PYTHON_BIN to the first candidate
# that exists and is executable, in this order:
#   1. $VIRTUAL_ENV             - an already-activated venv always wins (any OS)
#   2. $KURSAD40_VENV           - explicit override
#   3. <workspace>/.venv        - canonical macOS environment (~/KURSAD40/.venv)
#   4. <repo>/.scripts/.venv    - original Ubuntu repo-local environment
#   5. ~/Projects/kursad40-venv - earlier macOS location (historical)
#   6. python3 on PATH          - last resort, WARNS (likely the wrong Python)
#
# Candidates are anchored to this file's own location, not the caller's
# working directory, so launchers work when invoked from anywhere.
#
# Usage:
#   source "$(dirname "$0")/resolve_python.sh"
#   "$PYTHON_BIN" -u some_script.py "$@"

# ${BASH_SOURCE[0]} is empty when this file is sourced from zsh (the default
# login shell on this Mac), which made dirname resolve to "." -- i.e. the
# CALLER's working directory -- and every relative candidate below then
# pointed somewhere that does not exist. Fall back to $0, which zsh sets to
# the sourced file path.
_RESOLVE_PYTHON_SRC="${BASH_SOURCE[0]:-$0}"
_RESOLVE_PYTHON_DIR="$(cd "$(dirname "$_RESOLVE_PYTHON_SRC")" &> /dev/null && pwd)"

# <repo>/.scripts/.venv -- two levels up from .scripts/olds/v34/
_KURSAD40_LEGACY_VENV="$_RESOLVE_PYTHON_DIR/../../.venv"

# <workspace>/.venv -- .scripts/olds/v34 -> .scripts/olds -> .scripts -> <repo>
# -> <workspace>. This is ~/KURSAD40/.venv for the canonical checkout at
# ~/KURSAD40/autokursad.
_KURSAD40_WORKSPACE_VENV="$_RESOLVE_PYTHON_DIR/../../../../.venv"

PYTHON_BIN=""

for _candidate in \
	"$VIRTUAL_ENV/bin/python" \
	"$KURSAD40_VENV/bin/python" \
	"$_KURSAD40_WORKSPACE_VENV/bin/python" \
	"$_KURSAD40_LEGACY_VENV/bin/python" \
	"$HOME/Projects/kursad40-venv/bin/python" \
	; do
	# Skip candidates whose env var was unset (leaving a bare "/bin/python").
	case "$_candidate" in
		/bin/python) continue ;;
	esac
	if [ -x "$_candidate" ]; then
		# Normalise ../.. away so downstream messages and CMake cache entries
		# show a real path instead of .scripts/olds/v34/../../../../.venv/...
		PYTHON_BIN="$(cd "$(dirname "$_candidate")" &> /dev/null && pwd)/$(basename "$_candidate")"
		break
	fi
done

if [ -z "$PYTHON_BIN" ]; then
	if command -v python3 > /dev/null 2>&1; then
		PYTHON_BIN="$(command -v python3)"
		echo "WARNING: no KURSAD40 venv found; falling back to $PYTHON_BIN" >&2
		echo "         ($("$PYTHON_BIN" --version 2>&1)). MAVSDK/kconfiglib are" >&2
		echo "         almost certainly NOT installed there. Expected the" >&2
		echo "         workspace venv at $_KURSAD40_WORKSPACE_VENV" >&2
	else
		echo "ERROR: no usable Python interpreter found." >&2
		echo "  Tried, in order:" >&2
		echo "    \$VIRTUAL_ENV/bin/python           (VIRTUAL_ENV=${VIRTUAL_ENV:-<unset>})" >&2
		echo "    \$KURSAD40_VENV/bin/python         (KURSAD40_VENV=${KURSAD40_VENV:-<unset>})" >&2
		echo "    $_KURSAD40_WORKSPACE_VENV/bin/python" >&2
		echo "    $_KURSAD40_LEGACY_VENV/bin/python" >&2
		echo "    $HOME/Projects/kursad40-venv/bin/python" >&2
		echo "    python3 on PATH" >&2
		echo "  Fix: activate the KURSAD40 environment, or set KURSAD40_VENV" >&2
		echo "       to its root, e.g. export KURSAD40_VENV=\$HOME/KURSAD40/.venv" >&2
		exit 1
	fi
fi

# Exported so child processes (make -> cmake -> Tools/*.py) inherit the same
# interpreter instead of re-resolving to whatever `python3` means on PATH.
export PYTHON_BIN

unset _candidate _RESOLVE_PYTHON_SRC _RESOLVE_PYTHON_DIR _KURSAD40_LEGACY_VENV _KURSAD40_WORKSPACE_VENV
