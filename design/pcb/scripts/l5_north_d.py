#!/usr/bin/env python3
"""Layout phase L5 round 2 (design/.venv): evaluation of option D for the north exit of U9 (verifier round 1, blocker
gpio): "a row of 0.3/0.5 mm vias at y ~ 25.6, x 33.5-35.8 that drops some north lanes from L1 into the free L4 field".
Measures, on the board after the lane step with the north lanes' own routed copper taken out (only their 1.2 mm
stubs kept, i.e. the best case for every north lane):

  1. via sites: the cells where a lane via (0.30/0.50 mm, DEFAULT net) passes the exact rules (l4lib Grid: class
     clearances, every .kicad_dru rule, hole-to-hole 0.45 mm, keep-outs, the L4 router's no-via areas) in the pocket
     x 32.0-37.0, y 24.0-26.2 north of the ring-1 band; the largest set of mutually legal vias (>= 0.75 mm apart,
     greedy scan) and the largest set in one row (a row is what lanes coming from the south can reach: a lane cannot
     pass between two vias 0.75 mm apart, the gap is 0.25 mm and a 0.10 mm lane needs 0.40 mm);
  2. the free L1 width between TP31 and TP6 at y = 23.7 (the only L1 way north out of the pocket) in 0.10 mm lanes at
     0.25 mm pitch;
  3. per lane group (stub x ranges: G1 28.6-30.4, G2 31.5-32.7, G3 33.8-36.2) whether the pocket can be reached on L1
     at all (flood fill on the free L1 cells of a lane from each stub end, then: does it touch a pocket via site?).
Writes design/pcb/l5/north_d.json and prints a summary. Nothing is written to the board.

    design/.venv/bin/python -I design/pcb/scripts/l5_north_d.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
L5 = os.path.join(PCB, "l5")
SRC = os.path.join(L5, "board_geo_prio_in.json")
TMP = os.path.join(L5, "north_d_geo.json")
lanes = json.load(open(os.path.join(L5, "lanes.json")))
stubs = lanes["stubs"]
NORTH = sorted([n for n, (x, y, _) in stubs.items() if abs(y - 27.3) < 1e-6], key=lambda n: stubs[n][0])


def same(t, a, b):
    def eq(p, q):
        return abs(p[0] - q[0]) < 1e-4 and abs(p[1] - q[1]) < 1e-4
    return (eq(t["a"], a) and eq(t["b"], b)) or (eq(t["a"], b) and eq(t["b"], a))


geo = json.load(open(SRC))
for n in NORTH:
    r = lanes["routes"].get(n)
    if not r:
        continue
    sx, sy, _ = stubs[n]
    for lay, pts, w in r["tracks"]:
        stub = len(pts) == 2 and w <= 0.1001 and abs(pts[1][0] - sx) < 1e-6 and abs(pts[1][1] - sy) < 1e-6
        if stub:
            continue
        for a, b in zip(pts, pts[1:]):
            geo["tracks"] = [t for t in geo["tracks"] if not (t["net"] == n and t["layer"] == lay and same(t, a, b))]
    for v in r["vias"]:
        geo["vias"] = [g for g in geo["vias"] if not (g["net"] == n and abs(g["x"] - v[0]) < 1e-4 and
                                                     abs(g["y"] - v[1]) < 1e-4)]
json.dump(geo, open(TMP, "w"))
sys.argv = [sys.argv[0], TMP, os.path.join(L5, "_unused_l4_routes.json")]
sys.path.insert(0, HERE)
import l4_route as R  # noqa: E402
import l4lib as L  # noqa: E402
import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

L.VIA_ETH = True
R.setup_novia()
R.setup_sw_areas()
POCKET = (32.0, 24.0, 37.0, 26.2)
WIN = (26.0, 20.0, 39.0, 28.0)


def pack(cells, step=0.75):
    out = []
    for (x, y) in cells:
        if all(math.hypot(x - a, y - b) >= step for a, b in out):
            out.append((x, y))
    return out


def main():
    res = {"north_lanes": NORTH, "groups": {}}
    net = "HDR_GPIO1_B1"
    G = L.Grid(R.S, net, 0.05, WIN, L.F | L.B, via_ok=True, novia=R.GRID_NOVIA, relax=[], forbid=[], forbid_free=[])
    ii, jj = np.nonzero(G.via)
    sites = sorted({(round(G.xy(i, j)[0], 3), round(G.xy(i, j)[1], 3)) for i, j in zip(ii, jj)
                    if POCKET[0] <= G.xy(i, j)[0] <= POCKET[2] and POCKET[1] <= G.xy(i, j)[1] <= POCKET[3]},
                   key=lambda p: (p[0], p[1]))
    # step the cells to 0.05 mm for the packing scan (deterministic)
    coarse = sorted({(round(x * 20) / 20, round(y * 20) / 20) for x, y in sites}, key=lambda p: (-p[1], p[0]))
    allpack = pack(coarse)
    rows = {}
    for y0 in sorted({p[1] for p in coarse}):
        row = pack(sorted([p for p in coarse if abs(p[1] - y0) < 0.2], key=lambda p: p[0]))
        rows[y0] = row
    best_row = max(rows.items(), key=lambda kv: (len(kv[1]), kv[0])) if rows else (None, [])
    res["pocket"] = {"area": POCKET, "via_site_cells": len(sites), "max_vias_mutually_legal": len(allpack),
                     "max_vias_one_row": len(best_row[1]), "best_row_y": best_row[0],
                     "best_row": best_row[1], "packing": allpack}
    # TP31-TP6 gap on L1 at y 23.7
    i, _ = G.cell(0, 23.7)
    free = ~G.block[L.F][i, :]
    xs = [G.xy(i, j)[0] for j in range(G.W) if free[j] and 33.5 <= G.xy(i, j)[0] <= 36.0]
    width = (max(xs) - min(xs) + L.RES) if xs else 0.0
    res["tp_gap"] = {"free_centre_span_mm": round(width, 3),
                     "lanes_0p10_at_0p25": int(width / 0.25 + 1e-6) + (1 if width > 0 else 0)}
    # per group: can a lane stub end reach a pocket via site on L1 (flood fill on its own free cells)?
    groups = {"G1": (28.5, 30.5), "G2": (31.4, 32.8), "G3": (33.7, 36.2)}
    for g, (x0, x1) in groups.items():
        members = [n for n in NORTH if x0 <= stubs[n][0] <= x1]
        reach = 0
        for n in members:
            Gn = L.Grid(R.S, n, 0.05, WIN, L.F | L.B, via_ok=True, novia=R.GRID_NOVIA, relax=[], forbid=[],
                        forbid_free=[])
            fr = ~Gn.block[L.F]
            si, sj = Gn.cell(stubs[n][0], stubs[n][1])
            seed = np.zeros_like(fr)
            seed[si, sj] = True
            fr[si, sj] = True
            reg = ndimage.binary_propagation(seed, structure=np.ones((3, 3), bool), mask=fr)
            pocket_m = (Gn.X >= POCKET[0]) & (Gn.X <= POCKET[2]) & (Gn.Y >= POCKET[1]) & (Gn.Y <= POCKET[3])
            if (reg & Gn.via & pocket_m).any():
                reach += 1
        res["groups"][g] = {"lanes": members, "lanes_that_reach_a_pocket_via_site_alone": reach}
    json.dump(res, open(os.path.join(L5, "north_d.json"), "w"), indent=1)
    print("option D: pocket %s: %d via-site cells; max %d vias mutually legal, %d in one row (y %.2f)" % (
        POCKET, len(sites), len(allpack), len(best_row[1]), best_row[0] or 0))
    print("option D: TP31-TP6 gap at y 23.7: %.2f mm of lane centres -> %d lanes" % (
        res["tp_gap"]["free_centre_span_mm"], res["tp_gap"]["lanes_0p10_at_0p25"]))
    for g, v in res["groups"].items():
        print("option D: %s %d lanes, %d reach a pocket via site on L1 (each alone, nothing else routed)" % (
            g, len(v["lanes"]), v["lanes_that_reach_a_pocket_via_site_alone"]))


if __name__ == "__main__":
    main()
