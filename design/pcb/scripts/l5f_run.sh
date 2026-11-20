#!/bin/sh
# Layout phase L5F (CHECKPOINT-2 review fixes, owner decision D-H6, gate TP-L5F; decisions.md D-117): runs every L5F
# script in order on the L5 board. Called by rebuild_all.sh after l5_run.sh; can be run alone from the L5 snapshot:
#
#   sh design/pcb/scripts/l5f_run.sh            # from design/pcb/l5f/l5_board.kicad_pcb (written by rebuild_all.sh)
set -eu
export PYTHONHASHSEED=0
HERE=$(cd "$(dirname "$0")" && pwd)
PCB=$(cd "$HERE/.." && pwd)
DESIGN=$(cd "$PCB/.." && pwd)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
VPY="$DESIGN/.venv/bin/python"
L5F="$PCB/l5f"
step() {
  echo "== $*"
  if ! out=$("$@" 2>&1); then
    echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate"; echo "FAILED: $*"; exit 1
  fi
  echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate" | tail -25 || true
}
mkdir -p "$L5F"
cp "$L5F/l5_board.kicad_pcb" "$PCB/rv1106-reva.kicad_pcb"
# 1. buck input loops, enable nets (D-117 a, e): rips + local cap moves, then the new copper (exact-checked + router)
step "$PY" "$HERE/l5f_prep.py"
step "$PY" "$HERE/l4_export.py" "$L5F/geo_prep.json"
step "$VPY" -I "$HERE/l5f_route.py"
step "$PY" "$HERE/l5_write.py" "$L5F/route.json" L5F_ROUTE
# 2. clean-up (D-117 g): escape overshoot stubs, stub vias, neck-down at small passives, the 46.3 deg PB_INT_N piece
step "$PY" "$HERE/l5f_tidy.py"
# 3. zones and outline (D-117 d, f, h): V-cut clearance of the pours, In2 GND islands under the L4 pair hops, R 1 mm
# board corners
step "$PY" "$HERE/l5f_board.py"
step "$PY" "$HERE/fill_zones.py"
# 4. silkscreen (moved here from l5_run.sh: the buck-cell caps moved): line widths, 1.0 mm LED labels, edge clip,
# R62 / R63 references, test-pad labels (D-117 i); then the renders of the final board
step "$PY" "$HERE/l5_silk.py"
step "$PY" "$HERE/render_routing.py" l5
step "$PY" "$HERE/render_l5f.py"                         # route_l5f_*.png review images (D-117)
