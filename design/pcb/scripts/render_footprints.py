#!/usr/bin/env python3
"""Layout phase L1: place every custom footprint (+ the stock fiducial) on scratch boards and render them for review.

Writes design/pcb/renders/fp_<name>.png (one per footprint: F.Cu, F.Paste, F.Mask, F.SilkS, F.CrtYd, F.Fab, pads
numbered on Fab) and design/pcb/renders/footprints_all.png (all footprints on one board), plus the scratch board
design/pcb/renders/scratch/footprints_all.kicad_pcb on which kicad-cli DRC is run (report in renders/scratch/).
Needs KiCad's Python (pcbnew) and rsvg-convert (SVG -> PNG).
"""
import json
import os
import shutil
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
LIB = os.path.join(PCB, "board.pretty")
OUT = os.path.join(PCB, "renders")
SCR = os.path.join(OUT, "scratch")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
STOCK = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
NAMES = ["RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm", "TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm", "L_FHD4020S_4.0x4.0mm",
         "SW_TS-1187A_5.1x5.1mm", "microSD_TF-01A", "USB_A_AF90_WJDG_RightAngle_THT"]
LAYERS = "F.Cu,F.Paste,F.Mask,F.SilkS,F.CrtYd,F.Fab,Edge.Cuts,Dwgs.User"
mm = pcbnew.FromMM


def edge_rect(board, x1, y1, x2, y2):
    for (a, b, c, d) in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(a), mm(b)))
        s.SetEnd(pcbnew.VECTOR2I(mm(c), mm(d)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.05))
        board.Add(s)


def place(board, lib, name, x, y, ref):
    fp = pcbnew.FootprintLoad(lib, name)
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetReference(ref)
    board.Add(fp)
    bb = fp.GetBoundingBox(False)
    return [bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6]


def svg_to_png(svg, png, width):
    subprocess.run(["rsvg-convert", "-w", str(width), "-b", "#ffffff", "-o", png, svg], check=True)


def export(board_path, png, width=1600):
    svg = png[:-4] + ".svg"
    subprocess.run([CLI, "pcb", "export", "svg", "--mode-single", "--page-size-mode", "2", "--exclude-drawing-sheet",
                    "--sketch-pads-on-fab-layers", "-l", LAYERS, "-o", svg, board_path],
                   check=True, stdout=subprocess.DEVNULL)
    svg_to_png(svg, png, width)
    os.remove(svg)


def main():
    os.makedirs(SCR, exist_ok=True)
    # one board per footprint
    for i, n in enumerate(NAMES):
        b = pcbnew.BOARD()
        bb = place(b, LIB, n, 50, 50, "U%d" % (i + 1))
        edge_rect(b, bb[0] - 1, bb[1] - 2.5, bb[2] + 1, bb[3] + 2.5)
        p = os.path.join(SCR, "fp_%s.kicad_pcb" % n)
        pcbnew.SaveBoard(p, b)
        export(p, os.path.join(OUT, "fp_%s.png" % n), 2400 if n.startswith("RV1106") else 1600)
        print("rendered", "renders/fp_%s.png" % n)
    # all on one board (+ stock fiducial) and DRC
    b = pcbnew.BOARD()
    pos = [(20, 20), (45, 12), (45, 26), (60, 12), (25, 50), (60, 45)]
    refs = ["U9", "U11", "L1", "SW1", "J2", "J4"]   # real refs, so the project DRU rules ("U9 pads") apply
    for (n, (x, y), r) in zip(NAMES, pos, refs):
        place(b, LIB, n, x, y, r)
    place(b, os.path.join(STOCK, "Fiducial.pretty"), "Fiducial_1mm_Mask2mm", 45, 36, "FID1")
    edge_rect(b, 5, 3, 75, 62)
    allp = os.path.join(SCR, "footprints_all.kicad_pcb")
    pcbnew.SaveBoard(allp, b)
    # project settings (net classes, Default clearance 0.15) and custom rules from tools/make_kicad_project.py
    proj = os.path.normpath(os.path.join(PCB, "..", "kicad", "rv1106-reva"))
    for ext in ("kicad_pro", "kicad_dru"):
        shutil.copy(os.path.join(proj, "rv1106-reva." + ext), os.path.join(SCR, "footprints_all." + ext))
    export(allp, os.path.join(OUT, "footprints_all.png"), 2000)
    subprocess.run([CLI, "pcb", "render", "--side", "top", "--quality", "basic", "-w", "1600", "-h", "1400",
                    "-o", os.path.join(OUT, "footprints_all_3d.png"), allp], check=True, stdout=subprocess.DEVNULL)
    rep = os.path.join(SCR, "footprints_all_drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", rep, allp],
                   check=False, stdout=subprocess.DEVNULL)
    d = json.load(open(rep))
    viol = d.get("violations", [])
    kinds = {}
    for v in viol:
        kinds[v["type"]] = kinds.get(v["type"], 0) + 1
    print("scratch-board DRC (project rules): %d violations %s, %d unconnected" % (len(viol), kinds, len(d.get("unconnected_items", []))))
    for v in viol:
        print("  ", v["severity"], v["type"], v["description"], "|", " / ".join(i["description"] for i in v["items"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
