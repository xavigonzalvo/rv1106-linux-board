#!/usr/bin/env python3
"""Layout phase L2: review images of the placement.

    PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $PY design/pcb/scripts/render_placement.py

  renders/placement_top.png   kicad-cli pcb render, top view, high quality (3-D models)
  renders/placement_fab.png   kicad-cli pcb export svg of F.Fab + F.CrtYd + Edge.Cuts + User.1 (V-CUT) +
                              User.2 (PLACE-ZONES) + F.SilkS (references), converted with rsvg-convert at 2800 px
  renders/placement_soc.png   the same layers cropped to Z-SOC (U9 rings), 2400 px
Needs rsvg-convert (Homebrew librsvg) for SVG -> PNG.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "renders")
LAYERS = "F.Fab,F.Courtyard,Edge.Cuts,User.1,User.2,F.Silkscreen,F.Cu"


def svg_png(board, png, width, layers=LAYERS):
    svg = png[:-4] + ".svg"
    subprocess.run([bl.KICAD_CLI, "pcb", "export", "svg", "--mode-single", "--page-size-mode", "2",
                    "--exclude-drawing-sheet", "--sketch-pads-on-fab-layers", "--fit-page-to-board",
                    "-l", layers, "-o", svg, board], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["rsvg-convert", "-w", str(width), "-b", "#ffffff", "-o", png, svg], check=True)
    os.remove(svg)


def review_copy():
    """Copy of the board with the value texts hidden (they clutter F.Fab); references stay."""
    import pcbnew
    b = pcbnew.LoadBoard(bl.BOARD_FILE)
    for fp in b.GetFootprints():
        fp.Value().SetVisible(False)
    tmp = os.path.join(OUT, "_review.kicad_pcb")
    pcbnew.SaveBoard(tmp, b)
    return tmp


def main():
    os.makedirs(OUT, exist_ok=True)
    rev = review_copy()
    top = os.path.join(OUT, "placement_top.png")
    subprocess.run([bl.KICAD_CLI, "pcb", "render", "--side", "top", "--quality", "high", "-w", "2400", "-h", "2200",
                    "--background", "opaque", "-o", top, bl.BOARD_FILE], check=True, stdout=subprocess.DEVNULL)
    print("rendered", top)
    fab = os.path.join(OUT, "placement_fab.png")
    svg_png(rev, fab, 2800)
    print("rendered", fab)
    # SoC close-up: crop the fab PNG with ImageMagick (board x 18..52, y 20..52 of the 90 x 80 panel)
    soc = os.path.join(OUT, "placement_soc.png")
    big = os.path.join(OUT, "_big.png")
    svg_png(rev, big, 6000)
    # panel spans x -5..85 (90 mm) -> 6000 px: 66.67 px/mm; y 0..80 plus the margin kicad adds (none with fit)
    ppm = 6000 / 90.0
    x0, y0, w, h = (18 + 5) * ppm, 19 * ppm, 34 * ppm, 34 * ppm
    subprocess.run(["magick", big, "-crop", "%dx%d+%d+%d" % (w, h, x0, y0), "+repage", "-resize", "2400x", soc],
                   check=True)
    os.remove(big)
    for f in os.listdir(OUT):
        if f.startswith("_review"):
            os.remove(os.path.join(OUT, f))
    print("rendered", soc)


if __name__ == "__main__":
    main()
