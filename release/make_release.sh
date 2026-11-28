#!/usr/bin/env bash
# Rebuild release/rev-a/ from the sources in this repo (fab outputs, case STLs, device trees).
# Run from anywhere:  release/make_release.sh
# It copies files only; regenerate fab outputs (design/pcb/scripts/l6_fab.py) and the case STLs first if they changed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/release/rev-a"
FAB="$ROOT/design/pcb/fab"

rm -rf "$OUT/board" "$OUT/case" "$OUT/software" "$OUT/SHA256SUMS"
mkdir -p "$OUT/board/docs" "$OUT/case" "$OUT/software"

# Board: exactly what JLCPCB's order form asks for, plus documents for checking the order
cp "$FAB/rv1106-reva-jlc-upload.zip" "$FAB/jlc-bom.csv" "$FAB/jlc-cpl.csv" "$OUT/board/"
cp "$FAB/order-notes.md" "$FAB/cpl-rotations.md" "$FAB/jlc-bom-not-assembled.csv" "$FAB/rv1106-reva.d356" \
   "$FAB/fab-drawing.pdf" "$FAB/assembly-top-refs.pdf" "$FAB/assembly-top-values.pdf" \
   "$FAB/render-3d-top.png" "$FAB/render-3d-bottom.png" "$FAB/check_fab.txt" "$OUT/board/docs/"

# Case
cp "$ROOT"/case/stl/*.stl "$ROOT/case/rv1106_case.scad" "$OUT/case/"

# Software: board device trees (the root filesystem and SDK image are not in the repo, see BOARD-QUICKSTART.md)
cp "$ROOT"/software/out/*.dtb "$OUT/software/"

( cd "$OUT" && find board case software -type f | LC_ALL=C sort | xargs sha256sum > SHA256SUMS )
echo "release/rev-a rebuilt: $(wc -l < "$OUT/SHA256SUMS") files"
