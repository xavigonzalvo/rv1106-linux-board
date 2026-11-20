#!/bin/sh
# Layout phase L5 (remaining routing and finishing, gate TP-L5): runs every L5 script in order on the L4 board.
# Called by rebuild_all.sh after the L4 steps; can be run alone to redo L5 from the L4 snapshot:
#
#   sh design/pcb/scripts/l5_run.sh            # from the L4 snapshot design/pcb/l5/l4_board.kicad_pcb
#   L5_FR_RERUN=1 sh design/pcb/scripts/l5_run.sh   # also re-run Freerouting (else the stored session is re-imported)
set -eu
export PYTHONHASHSEED=0      # deterministic set/dict-of-str iteration in every script (round 2, verifier minor)
HERE=$(cd "$(dirname "$0")" && pwd)
PCB=$(cd "$HERE/.." && pwd)
DESIGN=$(cd "$PCB/.." && pwd)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
VPY="$DESIGN/.venv/bin/python"
L5="$PCB/l5"
step() {
  echo "== $*"
  if ! out=$("$@" 2>&1); then
    echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate"; echo "FAILED: $*"; exit 1
  fi
  echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak\|Debug: Adding duplicate" | tail -25 || true
}
mkdir -p "$L5"
cp "$L5/l4_board.kicad_pcb" "$PCB/rv1106-reva.kicad_pcb"
step python3 "$HERE/l5_rules.py"                            # D-114 h: DRU addition (J5 GND pins, one L1 spoke)
step "$PY" "$HERE/place_l5_tweaks.py"                       # D-113: TP26 local move (D-115 moves: place_l3_tweaks.py)
step "$PY" "$HERE/l4_export.py" "$L5/board_geo.json"
# lane stubs; SoC supply / boot-control nets (l5_priority.py, D-114 a); negotiated lanes; their test pads (l4lib, exact)
step "$VPY" -I "$HERE/l5_lanes.py"
step "$PY" "$HERE/l5_write.py" "$L5/lanes.json" L5_LANES
step "$PY" "$HERE/l5_write.py" "$L5/priority.json" L5_PRIORITY
# option-D evaluation of the north exit of U9 (round 2, verifier blocker gpio; nothing written to the board)
step "$PY" "$HERE/l4_export.py" "$L5/board_geo_prio_in.json"
step "$VPY" -I "$HERE/l5_north_d.py"
step python3 "$HERE/l5_drc.py" "$L5/drc_lanes.json" "$L5/open_nets.json"
step "$PY" "$HERE/l4_export.py" "$L5/board_geo_lanes.json"
if [ "${L5_FR_RERUN:-0}" = "1" ]; then
  step "$PY" "$HERE/l5_freeroute.py" --rerun --passes "${L5_FR_PASSES:-8}"
else
  step "$PY" "$HERE/l5_freeroute.py"
fi
step "$VPY" -I "$HERE/l5_cleanup.py"                        # clean-up, exact check, script routing, widening
step "$PY" "$HERE/l5_write.py" "$L5/fr_routes.json" L5_FREEROUTE
step "$PY" "$HERE/l5_write.py" "$L5/script_routes.json" L5_SCRIPT
step "$PY" "$HERE/l5_prune.py"                             # D-115: L5 copper that ends in nothing (open lanes' stubs)
# round 4 (D-116): the nets rounds 1-3 left open (SENSE re-route, inner-via nets, east lanes, codec loop, GPIO2_A7,
# I2C3 pull-ups), hand-placed + router legs; then redundant L5 segments removed
step "$PY" "$HERE/l4_export.py" "$L5/board_geo_prefinish.json"
step "$VPY" -I "$HERE/l5_finish.py"
step "$PY" "$HERE/l5_finish_write.py"
step "$PY" "$HERE/l5_tidy.py"
step "$PY" "$HERE/l4_export.py" "$L5/board_geo_routed.json"
step "$VPY" -I "$HERE/l5_stitch.py"                         # GND stitching vias
step "$PY" "$HERE/l5_write.py" "$L5/stitch.json" L5_STITCH
step "$PY" "$HERE/fill_zones.py"
# round 2 (D-114 h): a GND via in every L1/L4 GND pour piece that has none (starved-thermal islands), then refill
step "$PY" "$HERE/l5_islands_export.py"
step "$PY" "$HERE/l4_export.py" "$L5/board_geo_stitched.json"
step "$VPY" -I "$HERE/l5_islands.py"
step "$PY" "$HERE/l5_write.py" "$L5/stitch2.json" L5_STITCH2
step "$PY" "$HERE/fill_zones.py"
# L5F (D-117): the silkscreen step (l5_silk.py) and the L5 renders now run at the end of l5f_run.sh, after the L5F
# fixes moved parts in the buck cells
