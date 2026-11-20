#!/usr/bin/env python3
"""Layout phase L5, step 4 (design/.venv): GND stitching vias (layout.md §7, §2.3, §4.3, §4.6; TI SPRAAR7J §2.4).

    design/.venv/bin/python -I design/pcb/scripts/l5_stitch.py [geo.json] [out.json]
      default in : design/pcb/l5/board_geo_routed.json (l4_export.py after all L5 routing)
      default out: design/pcb/l5/stitch.json            (l5_write.py, group L5_STITCH)

Placed in this order, each candidate checked exactly (l4lib.Store.check_via: class clearances, .kicad_dru rules,
hole-to-hole 0.45 mm, pads, keep-outs) and kept out of the L4 router's no-via areas (VDD_0V9 neck and free strips, L3
escape fingers + 0.57 mm, the ring-1 band, the U9/U11/U1/J1 courtyards, the SW-node areas; D-110, D-111):
  1. next to the signal vias of the critical nets (ETH, USB, SDMMC, FSPI, XTAL; none of them should have one, but
     the hops of L4 do): one GND via within 1.0 mm where none is (L4 already did this; repeated so a gap is filled);
  2. rows along both sides of the ETH and USB pairs: every 2.5 mm along each line, 0.85-1.6 mm to the side, unless a
     GND via is already within 2.5 mm on that side (<= 5 mm pitch; layout.md §7 'rows along both sides');
  3. an edge ring: candidates every 3.0 mm on a ring 1.3 mm inside the board edge (0.4 mm V-cut / routed-edge
     clearance kept by the check), skipped near an existing GND via (< 1.5 mm);
  4. a 5 mm grid: every 5 x 5 mm cell of the board that holds L1 or L4 GND pour area gets a via if no GND via is in it
     (search from the cell centre outward, up to 2.4 mm).
GND vias are exempt from the pair 30 mil rules (DRU: 'B.NetName != GND'). The result lists cells left without a via
(no legal site), which check_routing.py reports.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
GEO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PCB, "l5", "board_geo_routed.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PCB, "l5", "stitch.json")
sys.argv = [sys.argv[0], GEO, os.path.join(PCB, "l5", "_unused_l4_routes.json")]
sys.path.insert(0, HERE)
import l4_route as R  # noqa: E402
import l4lib as L  # noqa: E402

geo = R.geo
S = R.S
NEW = []
CRIT_CLS = ("ETH_DIFF", "USB_DIFF", "SDMMC", "FSPI", "XTAL")
PAIR_CLS = ("ETH_DIFF", "USB_DIFF")
M3 = ((3.5, 3.5), (76.5, 3.5), (3.5, 76.5), (76.5, 76.5))


def gnd_vias():
    return [(v["x"], v["y"]) for v in geo["vias"] if v["net"] == "GND"] + NEW


MARGIN = 0.05        # extra clearance over the rule (the via's whole pad stays out of the no-via areas, too)


def legal(x, y):
    if any(math.hypot(x - a, y - b) < 3.5 + 0.25 for a, b in M3):
        return False
    nv = [(q[0] - 0.30, q[1] - 0.30, q[2] + 0.30, q[3] + 0.30) for q in R.GRID_NOVIA]
    if not S.check_via("GND", x, y, novia=nv):
        return False
    # the rule + MARGIN: the via must also be legal when moved MARGIN in any of 8 directions
    for k in range(8):
        a = math.pi * k / 4
        if not S.check_via("GND", x + MARGIN * math.cos(a), y + MARGIN * math.sin(a), novia=nv):
            return False
    return True


def add(x, y, why):
    x, y = round(x, 3), round(y, 3)
    S.add_via("GND", x, y, L.VIA_D / 2, L.VIA_DR / 2)
    NEW.append((x, y))
    WHY.setdefault(why, 0)
    WHY[why] += 1


WHY = {}


def near(x, y, r):
    return any(math.hypot(x - a, y - b) <= r for a, b in gnd_vias())


def ring_search(x, y, r0, r1, step=0.1, n=24):
    r = r0
    while r <= r1 + 1e-9:
        for k in range(n if r > 0 else 1):
            a = 2 * math.pi * k / n
            gx, gy = x + r * math.cos(a), y + r * math.sin(a)
            if legal(gx, gy):
                return gx, gy
        r += step
    return None


def main():
    # deterministic candidate order (round 2, verifier minor): the exported geometry lists items in pcbnew's order,
    # which follows the random item UUIDs of a fresh build; sort every list this script iterates
    geo["tracks"].sort(key=lambda t: (t["net"], t["layer"], round(t["a"][0], 4), round(t["a"][1], 4),
                                      round(t["b"][0], 4), round(t["b"][1], 4), t["w"]))
    geo["vias"].sort(key=lambda v: (v["net"], round(v["x"], 4), round(v["y"], 4)))
    R.setup_novia()
    R.setup_sw_areas()
    cls = {n: v[0] for n, v in geo["classes"].items()}
    missing = {"signal_via": [], "pair_row": [], "edge": [], "grid": []}
    # 1. signal vias of the critical nets
    for v in geo["vias"]:
        if cls.get(v["net"]) in CRIT_CLS and not near(v["x"], v["y"], 1.0):
            p = ring_search(v["x"], v["y"], 0.6, 1.0)
            if p:
                add(p[0], p[1], "signal_via")
            else:
                missing["signal_via"].append((v["net"], round(v["x"], 2), round(v["y"], 2)))
    # 2. rows along the pairs (L1 lines only: the reference plane is L2 under L1)
    for t in geo["tracks"]:
        if cls.get(t["net"]) not in PAIR_CLS or t["layer"] != "F":
            continue
        (ax, ay), (bx, by) = t["a"], t["b"]
        ln = math.hypot(bx - ax, by - ay)
        if ln < 1.0:
            continue
        ux, uy = (bx - ax) / ln, (by - ay) / ln
        nx, ny = -uy, ux
        n = max(1, int(ln / 2.5))
        for i in range(n + 1):
            px, py = ax + ux * ln * i / n, ay + uy * ln * i / n
            for side in (1, -1):
                done = False
                for off in (0.85, 1.0, 1.2, 1.4, 1.6):
                    gx, gy = px + side * nx * off, py + side * ny * off
                    if near(gx, gy, 2.5):
                        done = True
                        break
                    if legal(gx, gy):
                        add(gx, gy, "pair_row")
                        done = True
                        break
                if not done:
                    missing["pair_row"].append((t["net"], round(px, 2), round(py, 2), side))
    # 3. edge ring (1.3 mm inside the edge, 3 mm pitch)
    e = 1.3
    pts = []
    k = int((80 - 2 * e) / 3.0)
    for i in range(k + 1):
        s = e + (80 - 2 * e) * i / k
        pts += [(s, e), (80 - e, s), (80 - s, 80 - e), (e, 80 - s)]
    for (x, y) in pts:
        if near(x, y, 1.5):
            continue
        p = ring_search(x, y, 0.0, 0.8)
        if p:
            add(p[0], p[1], "edge")
        else:
            missing["edge"].append((round(x, 2), round(y, 2)))
    # 4. 5 mm grid
    for i in range(16):
        for j in range(16):
            x0, y0 = i * 5.0, j * 5.0
            if any(x0 <= a < x0 + 5 and y0 <= b < y0 + 5 for a, b in gnd_vias()):
                continue
            c = (x0 + 2.5, y0 + 2.5)
            p = ring_search(c[0], c[1], 0.0, 2.4, step=0.15, n=32)
            if p and x0 <= p[0] < x0 + 5 and y0 <= p[1] < y0 + 5:
                add(p[0], p[1], "grid")
            else:
                missing["grid"].append((x0, y0))
    print("GND stitching: %d new vias %s; without a legal site: %s" % (
        len(NEW), WHY, {k: len(v) for k, v in missing.items()}))
    json.dump({"routes": {"GND": {"tracks": [], "vias": [list(v) for v in NEW]}}, "why": WHY, "missing": missing},
              open(OUT, "w"), indent=0)


if __name__ == "__main__":
    main()
