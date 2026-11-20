#!/bin/sh
# Rebuild design/pcb/rv1106-reva.kicad_pcb from scratch: netlist -> board -> placement -> L3 planes and SoC escape
# -> L4 critical routing -> L5 remaining routing and finishing -> L5F review fixes (D-117) -> L5G re-review fixes
# (D-H7, D-119..D-127) -> L6 fabrication outputs (D-132).
# Every board change is one of these scripts, in this order (PLAN.md "Layout phases"; D-109).
#
#   sh design/pcb/scripts/rebuild_all.sh            # from the project folder (any cwd works)
#
# Tools: KiCad 10.0.7 bundled Python (pcbnew), design/.venv (scipy for the U9 fan solver, the generators),
# kicad-cli (DRC, renders), rsvg-convert + magick (renders).
set -eu
export PYTHONHASHSEED=0      # deterministic set/dict-of-str iteration in every script (round 2, verifier minor)
HERE=$(cd "$(dirname "$0")" && pwd)
DESIGN=$(cd "$HERE/../.." && pwd)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
VPY="$DESIGN/.venv/bin/python"
run() { echo "== $*"; "$@" 2>&1 | grep -v "create wxApp\|swig/python detected a memory leak" || true; }
step() {
  echo "== $*"
  if ! out=$("$@" 2>&1); then
    echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak"; echo "FAILED: $*"; exit 1
  fi
  echo "$out" | grep -v "create wxApp\|swig/python detected a memory leak" || true
}

mkdir -p "$DESIGN/pcb/renders" "$DESIGN/pcb/l4" "$DESIGN/pcb/l5"   # round 4: clean-tree rebuild (verifier minor)
# L1/L2 (unchanged): footprints, KiCad project files, board, placement, placement check (+ trial route of D-107/D-108)
step "$PY" "$HERE/make_footprints.py"
step "$VPY" -I "$DESIGN/tools/make_kicad_project.py" "$DESIGN"
step "$PY" "$HERE/build_board.py"
step "$PY" "$HERE/place.py"
step "$PY" "$HERE/place_l3_tweaks.py"          # L3: recorded small local moves (D-109 h)
# placement check (+ trial route; writes trial/result_policy.json used by the L3 scripts, pcb/drc_placement.json and
# pcb/check_placement.txt); a FAIL stops the build
echo "== $PY $HERE/check_placement.py > pcb/check_placement.txt"
if ! "$PY" "$HERE/check_placement.py" 2>"$DESIGN/pcb/l4/check_placement.err" > "$DESIGN/pcb/check_placement.txt"; then
  grep -E "^FAIL|SUMMARY" "$DESIGN/pcb/check_placement.txt"
  grep -v "create wxApp\|swig/python detected a memory leak" "$DESIGN/pcb/l4/check_placement.err" | tail -20
  echo "FAILED: check_placement.py"; exit 1
fi
grep SUMMARY "$DESIGN/pcb/check_placement.txt"
# L3: planes and SoC escape
step "$PY" "$HERE/l3_rules.py"
step "$PY" "$HERE/route_escape.py"
step "$PY" "$HERE/route_planevias.py"
step "$PY" "$HERE/planes.py"
step "$PY" "$HERE/fill_zones.py"
step "$PY" "$HERE/route_powerlinks.py"
step "$PY" "$HERE/fill_zones.py"
step "$PY" "$HERE/render_routing.py" l3
step "$PY" "$HERE/check_routing.py"            # L3 gate (TP-L3) on the L3 board; a FAIL stops the build
cp "$DESIGN/pcb/check_routing.txt" "$DESIGN/pcb/check_routing_l3.txt"
mkdir -p "$DESIGN/pcb/l4"
cp "$DESIGN/pcb/rv1106-reva.kicad_pcb" "$DESIGN/pcb/l4/l3_board.kicad_pcb"      # L3 snapshot (L4 iterations)
# L4: critical routing (D-111). The router runs in design/.venv (numpy/scipy) on the exported copper; the result is
# written back as tracks/vias in the board group L4_CRITICAL; zones refilled; checked (TP-L4) and rendered.
step "$PY" "$HERE/l4_rules.py"
step "$PY" "$HERE/l4_export.py"
step "$VPY" -I "$HERE/l4_route.py"
step "$PY" "$HERE/l4_write.py"
step "$PY" "$HERE/fill_zones.py"
step "$PY" "$HERE/render_routing.py" l4
# L3 + L4 checks (TP-L4) on the L4 board, kept as pcb/check_routing_l4.txt; the L4 report is written either way
echo "== $PY $HERE/check_routing.py (L4 board)"
"$PY" "$HERE/check_routing.py" 2>&1 | grep -v "create wxApp\|swig/python detected a memory leak" | grep -v "^PASS" || true
cp "$DESIGN/pcb/check_routing.txt" "$DESIGN/pcb/check_routing_l4.txt"
step "$VPY" -I "$HERE/l4_report.py"            # design/pcb/routing-report.md measured table (L4 section)
head -1 "$DESIGN/pcb/check_routing_l4.txt"
# L5: remaining routing and finishing (D-113): from the L4 snapshot, lane stubs + negotiated lane routing, Freerouting
# (stored session re-imported; L5_FR_RERUN=1 runs Freerouting again), clean-up and script routing, GND stitching,
# zone fill, silkscreen, renders (scripts/l5_run.sh); then the L3 + L4 + L5 checks on the final board (TP-L5)
mkdir -p "$DESIGN/pcb/l5"
cp "$DESIGN/pcb/rv1106-reva.kicad_pcb" "$DESIGN/pcb/l5/l4_board.kicad_pcb"
sh "$HERE/l5_run.sh"
# L5F: CHECKPOINT-2 review fixes (owner decision D-H6, D-117): from the L5 snapshot, buck input loops, enable nets,
# clean-up, V-cut / hop zones, outline corners, silkscreen, renders (scripts/l5f_run.sh); then the checks (TP-L5F)
mkdir -p "$DESIGN/pcb/l5f"
cp "$DESIGN/pcb/rv1106-reva.kicad_pcb" "$DESIGN/pcb/l5f/l5_board.kicad_pcb"
sh "$HERE/l5f_run.sh"
# L5G: re-review fixes (owner decision D-H7, D-119..D-127): from the L5F snapshot, EP board vias + via filling/capping,
# SD clock / RTC spacing, J5.2 link, J1 / hop-island / Q1 vias, silk labels beside their own part, renders
# (scripts/l5g_run.sh); then the checks on the final board (TP-L5G, l5gcheck.py via check_routing.py)
mkdir -p "$DESIGN/pcb/l5g"
cp "$DESIGN/pcb/rv1106-reva.kicad_pcb" "$DESIGN/pcb/l5g/l5f_board.kicad_pcb"
sh "$HERE/l5g_run.sh"
echo "== $PY $HERE/check_routing.py (final board)"
rc=0
"$PY" "$HERE/check_routing.py" 2>&1 | grep -v "create wxApp\|swig/python detected a memory leak" | grep -v "^PASS" || true
grep -q " 0 FAIL$" "$DESIGN/pcb/check_routing.txt" || rc=1
step "$VPY" -I "$HERE/l5_report.py"            # design/pcb/routing-report.md L5 section
head -1 "$DESIGN/pcb/check_routing.txt"
[ $rc -eq 0 ] || { echo "FAILED: check_routing.py (see design/pcb/check_routing.txt)"; exit 1; }
# L6: fabrication outputs (D-132, gate TP-L6): aux origin at the panel lower-left, V-CUT layer = the two cut lines only,
# Gerbers / Excellon / job / zip, JLC BOM + CPL, assembly + fab drawings, 3-D renders, IPC-D-356, order notes, then the
# self-check check_fab.py (scripts/l6_run.sh); a FAIL stops the build
sh "$HERE/l6_run.sh"
