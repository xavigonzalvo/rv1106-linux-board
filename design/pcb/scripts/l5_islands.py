#!/usr/bin/env python3
"""Layout phase L5 round 2 (design/.venv): one GND via in every L1/L4 GND pour piece that has none (D-114 h).

    design/.venv/bin/python -I design/pcb/scripts/l5_islands.py
      in : design/pcb/l5/islands.json (l5_islands_export.py), l5/board_geo_stitched.json (l4_export.py)
      out: design/pcb/l5/stitch2.json (l5_write.py, group L5_STITCH2)

Candidates on a 0.1 mm grid inside the piece (not in its holes), nearest to the piece's centroid first; the first one
that passes l5_stitch.legal (exact l4lib via check with a 0.05 mm margin, no-via areas, M3 keep-outs) is taken.
Deterministic (sorted candidates).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
L5 = os.path.join(PCB, "l5")
sys.argv = [sys.argv[0], os.path.join(L5, "board_geo_stitched.json"), os.path.join(L5, "_unused_stitch.json")]
sys.path.insert(0, HERE)
import l5_stitch as ST  # noqa: E402  (loads the geometry into ST.S; legal() / add())
import l4lib as L  # noqa: E402


def inside(x, y, poly):
    return L.inside_poly(x, y, poly)


def main():
    ST.R.setup_novia()
    ST.R.setup_sw_areas()
    isl = json.load(open(os.path.join(L5, "islands.json")))
    got, miss = [], []
    for d in isl:
        poly = d["outline"]
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        cands = []
        x = math.floor(min(xs) * 10) / 10
        while x <= max(xs):
            y = math.floor(min(ys) * 10) / 10
            while y <= max(ys):
                if inside(x, y, poly) and not any(inside(x, y, h) for h in d["holes"]):
                    cands.append((round(math.hypot(x - cx, y - cy), 4), round(x, 3), round(y, 3)))
                y += 0.1
            x += 0.1
        cands.sort()
        for _, x, y in cands:
            if ST.legal(x, y):
                ST.add(x, y, "island")
                got.append((d["layer"], x, y))
                break
        else:
            miss.append((d["layer"], d["area"], [round(c, 2) for c in poly[0]]))
    print("GND pour pieces without a via: %d; via added in %d; no legal site in %d: %s" % (len(isl), len(got),
                                                                                         len(miss), miss[:8]))
    json.dump({"routes": {"GND": {"tracks": [], "vias": [[x, y] for _, x, y in got]}}, "missing": miss},
              open(os.path.join(L5, "stitch2.json"), "w"), indent=0)


if __name__ == "__main__":
    main()
