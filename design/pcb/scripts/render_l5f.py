#!/usr/bin/env python3
"""Layout phase L5F: review images of every area the L5F fixes touched (D-117), from the saved board.

    $PY design/pcb/scripts/render_l5f.py     -> design/pcb/renders/route_l5f_<area>[_<layers>].png

For each area: a kicad-cli SVG export of the area's layers (F.Cu / B.Cu / In2.Cu + F.SilkS + Edge.Cuts) cropped with
ImageMagick (route_l5f_<area>_<layer>.png), and an annotated plot of the same window from the board copper
(l5f_geo.py + l5f_plot.py in design/.venv: pads with ref.pad / net, tracks, vias, fills, courtyards;
route_l5f_<area>.png).
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "renders")
VPY = os.path.join(bl.DESIGN, ".venv", "bin", "python")
# area: (x0, y0, x1, y1, svg layer sets, plot layers, title)
AREAS = {
    "buck_u6": (66.0, 12.0, 77.0, 22.0, ("F.Cu", "B.Cu"), "F,B", "U6 3V3 cell: input loop, EN"),
    "buck_u7": (66.0, 21.0, 77.0, 31.0, ("F.Cu", "B.Cu"), "F,B", "U7 DDR cell: input loop, EN"),
    "buck_u4": (66.0, 30.0, 78.0, 40.0, ("F.Cu", "B.Cu"), "F,B", "U4 0V9 cell: input loop, EN, C29/R17 neck"),
    "buck_u5": (66.0, 39.0, 77.0, 49.0, ("F.Cu", "B.Cu"), "F,B", "U5 1V8 cell: input loop, EN"),
    "pwr_en_l3": (61.0, 14.0, 73.0, 23.0, ("F.Cu", "B.Cu"), "F,B", "PWR_EN / U6_EN at L3"),
    "vcut_west": (-1.5, 15.0, 6.0, 56.0, ("F.Cu", "B.Cu"), "F,B", "west V-cut edge (x = 0), J5 corridor"),
    "vcut_east": (74.0, 5.0, 81.5, 75.0, ("F.Cu", "B.Cu"), "F,B", "east V-cut edge (x = 80)"),
    "hop_eth": (19.0, 26.0, 25.0, 34.0, ("In2.Cu", "B.Cu"), "In2,B", "ETH TX L4 hop over In2 GND"),
    "hop_usb": (35.0, 47.0, 43.0, 60.0, ("In2.Cu", "B.Cu"), "In2,B", "USB_DM / USBC / USBA_DM L4 hops over In2 GND"),
    "hop_usbc": (45.0, 68.0, 54.0, 76.0, ("In2.Cu", "B.Cu"), "In2,B", "USBC L4 hops at J1 over In2 GND"),
    "corner_nw": (-2.5, -0.5, 3.0, 3.5, ("F.Cu",), "F,B", "NW board corner R 1 mm + 1.5 mm rail notch (Edge.Cuts "
                  "black, V-CUT dashed)"),
    "corner_se": (77.0, 76.5, 82.5, 80.5, ("F.Cu",), "F,B", "SE board corner R 1 mm + 1.5 mm rail notch"),
    "led_silk": (56.0, 0.0, 70.0, 7.0, ("F.SilkS",), "F,S", "LED labels 1.0 mm"),
    "r62_silk": (26.0, 9.0, 35.0, 16.0, ("F.SilkS",), "F,S", "R62 / R63 references"),
    "tp_silk": (58.0, 46.0, 77.0, 56.0, ("F.SilkS",), "F,S", "test-pad labels TP3 / 13 / 14 / 27 / 28 / 29"),
    "u9_stubs": (25.5, 27.5, 43.5, 45.5, ("F.Cu",), "F", "U9 escape stubs trimmed"),
}


def main(areas=None, prefix="route_l5f", geo_dir="l5f", tag="L5F"):
    areas = areas or AREAS
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(bl.PCB_DIR, geo_dir), exist_ok=True)
    geo = os.path.join(bl.PCB_DIR, geo_dir, "geo_final.json")
    subprocess.run([sys.executable, os.path.join(bl.HERE, "l5f_geo.py"), bl.BOARD_FILE, geo], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    made = []
    with tempfile.TemporaryDirectory() as td:
        pngs = {}
        for lay in ("F.Cu", "B.Cu", "In2.Cu", "F.SilkS"):
            svg = os.path.join(td, lay.replace(".", "_") + ".svg")
            # L5G (D-H7 item 10): the silk image shows F.SilkS over the F.Mask openings, no F.Fab text
            extra = ",F.SilkS,Edge.Cuts" if lay.endswith("Cu") else ",F.Mask,Edge.Cuts"
            subprocess.run([bl.KICAD_CLI, "pcb", "export", "svg", "--mode-single", "--page-size-mode", "2",
                            "--exclude-drawing-sheet", "--fit-page-to-board", "-l", lay + extra, "-o", svg,
                            bl.BOARD_FILE], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            png = svg[:-4] + ".png"
            subprocess.run(["rsvg-convert", "-w", "9000", "-b", "#ffffff", "-o", png, svg], check=True)
            pngs[lay] = png
        ppm = 9000 / 90.0       # panel x -5 .. 85
        for name, (x0, y0, x1, y1, lays, plays, title) in areas.items():
            for lay in lays:
                out = os.path.join(OUT, "%s_%s_%s.png" % (prefix, name, lay.replace(".", "_")))
                geom = "%dx%d+%d+%d" % ((x1 - x0) * ppm, (y1 - y0) * ppm, (x0 + 5) * ppm, max(0.0, y0) * ppm)
                subprocess.run(["magick", pngs[lay], "-crop", geom, "+repage", "-resize", "1400x1400>", out],
                               check=True)
                made.append(out)
            out = os.path.join(OUT, "%s_%s.png" % (prefix, name))
            subprocess.run([VPY, "-I", os.path.join(bl.HERE, "l5f_plot.py"), geo, str(x0), str(y0), str(x1), str(y1),
                            out, plays, tag + " " + title], check=True)
            made.append(out)
    print("render %s: %d images in %s" % (prefix, len(made), OUT))


if __name__ == "__main__":
    main()
