#!/bin/sh
# Layout phase L6 (fabrication outputs, gate TP-L6; decisions.md D-132): regenerates everything in design/pcb/fab/ from
# the finished board and runs the self-check. Called by rebuild_all.sh after the L5G step and its final checks; can
# be run alone on the delivered board:
#
#   sh design/pcb/scripts/l6_run.sh
set -eu
export PYTHONHASHSEED=0
HERE=$(cd "$(dirname "$0")" && pwd)
DESIGN=$(cd "$HERE/../.." && pwd)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
VPY="$DESIGN/.venv/bin/python"
filt() { grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate" || true; }
echo "== $PY $HERE/l6_fab.py"
if ! out=$("$PY" "$HERE/l6_fab.py" 2>&1); then echo "$out" | filt; echo "FAILED: l6_fab.py"; exit 1; fi
echo "$out" | filt | grep "^L6"
echo "== $VPY -I $HERE/check_fab.py"
if ! out=$("$VPY" -I "$HERE/check_fab.py" 2>&1); then echo "$out" | grep -v "^PASS"; echo "FAILED: check_fab.py (see design/pcb/fab/check_fab.txt)"; exit 1; fi
echo "$out" | tail -1
