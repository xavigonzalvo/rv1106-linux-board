#!/bin/sh
# Layout phase L5G (re-review fixes, owner decision D-H7, gate TP-L5G; decisions.md D-119..D-127): runs every L5G
# script in order on the L5F board. Called by rebuild_all.sh after l5f_run.sh; can be run alone from the L5F snapshot:
#
#   sh design/pcb/scripts/l5g_run.sh            # from design/pcb/l5g/l5f_board.kicad_pcb (written by rebuild_all.sh)
set -eu
export PYTHONHASHSEED=0
HERE=$(cd "$(dirname "$0")" && pwd)
PCB=$(cd "$HERE/.." && pwd)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
L5G="$PCB/l5g"
step() {
  echo "== $*"
  if ! out=$("$@" 2>&1); then
    echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate"; echo "FAILED: $*"; exit 1
  fi
  echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate" | tail -25 || true
}
mkdir -p "$L5G"
cp "$L5G/l5f_board.kicad_pcb" "$PCB/rv1106-reva.kicad_pcb"
# 1. copper: EP board vias + via filling/capping, SD clock / RTC spacing, J5.2 link, J1 / hop / Q1 vias (D-119..D-126)
step "$PY" "$HERE/l5g_fix.py"
step "$PY" "$HERE/fill_zones.py"
# 2. silk labels beside their own part, TH texts off the board (D-120)
step "$PY" "$HERE/l5g_silk.py"
# 3. renders of the final board: the L5 set, the L5F set (silk plots now draw the labels) and the L5G areas
step "$PY" "$HERE/render_routing.py" l5
step "$PY" "$HERE/render_l5f.py"
step "$PY" "$HERE/render_l5g.py"
