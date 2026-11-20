#!/usr/bin/env python3
"""Review images of the routed board, one PNG per copper layer (+ U9 close-up), for routing phase <tag>:

    $PY design/pcb/scripts/render_routing.py l3     -> design/pcb/renders/route_l3_{F_Cu,In1_Cu,In2_Cu,B_Cu,u9}.png

kicad-cli pcb export svg (one layer + Edge.Cuts) -> rsvg-convert -> PNG (2400 px wide;
the panel 90 x 80 mm, so ~27 px/mm). Filled zones are drawn as filled.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "renders")


def svg_png(layers, png, width):
    svg = png[:-4] + ".svg"
    subprocess.run([bl.KICAD_CLI, "pcb", "export", "svg", "--mode-single", "--page-size-mode", "2",
                    "--exclude-drawing-sheet", "--fit-page-to-board", "-l", layers, "-o", svg, bl.BOARD_FILE],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["rsvg-convert", "-w", str(width), "-b", "#ffffff", "-o", png, svg], check=True)
    os.remove(svg)


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "l3"
    os.makedirs(OUT, exist_ok=True)
    made = []
    for lyr in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        png = os.path.join(OUT, "route_%s_%s.png" % (tag, lyr.replace(".", "_")))
        svg_png(lyr + ",Edge.Cuts", png, 2400)
        made.append(png)
    # U9 close-up of F.Cu: board x 22..47, y 24..49 of the 90 mm wide panel (x -5..85)
    big = os.path.join(OUT, "_big.png")
    svg_png("F.Cu,Edge.Cuts", big, 7200)
    ppm = 7200 / 90.0
    png = os.path.join(OUT, "route_%s_u9.png" % tag)
    subprocess.run(["magick", big, "-crop", "%dx%d+%d+%d" % (25 * ppm, 25 * ppm, (22 + 5) * ppm, 24 * ppm), "+repage",
                    "-resize", "2000x", png], check=True)
    os.remove(big)
    made.append(png)
    if tag != "l3":
        # L4 close-ups of the critical areas, L1 + L4 together (board mm x0, y0, x1, y1)
        crops = {"eth": (10, 14, 31, 35), "usb": (32, 42, 56, 76), "sd": (8, 42, 38, 68), "nand": (40, 33, 64, 47),
                 "pmu": (60, 10, 79, 50), "xtal": (30, 21, 44, 54), "pwrin": (44, 47, 79, 79)}
        # drawn from the exported copper (l4/board_geo.json) + the L4 routes (l4/routes.json), no zone fills, so L1
        # (red) and L4 (blue) routes are both visible; pads labelled ref.pad/net (scripts/l4_plot.py, design/.venv)
        vpy = os.path.join(bl.DESIGN, ".venv", "bin", "python")
        extra = []
        if tag == "l5":
            # L5: the new copper of every L5 step (dark) over the L4 board (light); close-ups of the L5 areas
            import json
            l5 = os.path.join(bl.PCB_DIR, "l5")
            allr = {}
            # round 4: the copper l5_finish.py ripped is left out, its own routes (finish.json) added; the light base
            # is the board after the L5 routing steps (before stitching), so a ripped L4 track is not drawn either
            rip = set()
            fin = os.path.join(l5, "finish.json")
            if os.path.exists(fin):
                for n, lay, a, b in json.load(open(fin))["rip_tracks"]:
                    rip.add((n, lay, round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)))
                    rip.add((n, lay, round(b[0], 3), round(b[1], 3), round(a[0], 3), round(a[1], 3)))
            for f in ("lanes.json", "priority.json", "fr_routes.json", "script_routes.json", "finish.json", "stitch.json",
                      "stitch2.json"):
                fp = os.path.join(l5, f)
                if os.path.exists(fp):
                    for n, r in json.load(open(fp))["routes"].items():
                        a = allr.setdefault(n, {"tracks": [], "vias": []})
                        for lay, pts, w in r["tracks"]:
                            keep = [pts[0]]
                            for p0, p1 in zip(pts, pts[1:]):
                                if (n, lay, round(p0[0], 3), round(p0[1], 3), round(p1[0], 3), round(p1[1], 3)) in rip:
                                    if len(keep) > 1:
                                        a["tracks"].append([lay, keep, w])
                                    keep = [p1]
                                else:
                                    keep.append(p1)
                            if len(keep) > 1:
                                a["tracks"].append([lay, keep, w])
                        a["vias"] += r["vias"]
            json.dump({"routes": allr}, open(os.path.join(l5, "routes_all.json"), "w"))
            base = os.path.join(l5, "board_geo_routed.json")
            extra = [os.path.join(l5, "routes_all.json"), base if os.path.exists(base) else os.path.join(l5, "board_geo.json")]
            crops = {"west": (0, 10, 30, 62), "north": (22, 0, 50, 32), "east": (40, 0, 80, 40),
                     "south": (0, 40, 80, 80), "u9": (22, 24, 47, 49)}
        for name, (x0, y0, x1, y1) in crops.items():
            png = os.path.join(OUT, "route_%s_%s%s.png" % (tag, name, "_l1l4" if tag == "l5" and name == "u9" else ""))
            subprocess.run([vpy, "-I", os.path.join(bl.HERE, "l4_plot.py"), str(x0), str(y0), str(x1), str(y1), png]
                           + extra, check=True, stderr=subprocess.DEVNULL)
            made.append(png)
    if tag == "l5":
        # 3-D top view (kicad-cli render, high quality) and the silkscreen + mask + pads view
        top = os.path.join(OUT, "route_l5_3d_top.png")
        subprocess.run([bl.KICAD_CLI, "pcb", "render", "--side", "top", "--quality", "high", "-w", "2400", "-h", "2200",
                        "--background", "opaque", "-o", top, bl.BOARD_FILE], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        made.append(top)
        png = os.path.join(OUT, "route_l5_silk.png")
        svg_png("F.Silkscreen,F.Mask,Edge.Cuts", png, 2400)
        made.append(png)
    for m in made:
        print("rendered", m)


if __name__ == "__main__":
    main()
