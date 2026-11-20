#!/usr/bin/env python3
"""Layout phase L5: capacity of the north exit of U9 (why the north header lanes cannot all be routed, D-113 f).

    design/.venv/bin/python -I design/pcb/scripts/l5_north_cut.py [geo.json]   # default design/pcb/l5/board_geo.json

On horizontal cut lines across the north side of U9 (x 24-46, y = 26.0 ... 22.0), for L1 and L4 separately, the free
intervals for a 0.10 mm lane track are computed from the board copper before any L5 routing (pads, tracks, vias and
holes of every net except the open north lanes; each obstacle grown by its own half width + 0.20 mm, the largest
class clearance a DEFAULT lane meets here, + 0.05 mm lane half width), and the number of lanes that fit side by side
at 0.25 mm pitch (0.10 mm + 0.15 mm DEFAULT-to-DEFAULT gap). Crystal guard (1 mm around Y1/C76/C77 pads, L1) and L4
under Y1 are counted as blocked. Prints a table; writes design/pcb/l5/north_cut.json.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
GEO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PCB, "l5", "board_geo.json")
X0, X1 = 24.0, 46.0
NORTH = ["HDR_SPI0_CS0", "HDR_SPI0_SCLK", "HDR_SPI0_MOSI", "HDR_SPI0_MISO", "HDR_PWM8", "HDR_PWM9", "HDR_UART3_TX",
         "HDR_UART3_RX", "HDR_I2C3_SDA", "HDR_I2C3_SCL", "HDR_PWM11", "HDR_PWM10", "UART2_RX", "UART2_TX",
         "HDR_GPIO1_B1", "HDR_GPIO1_B0", "HDR_GPIO1_A4", "HDR_GPIO1_A3", "LED_ETH", "HDR_GPIO1_A1", "HDR_GPIO1_A0"]
CLR = 0.20
HW = 0.05
PITCH = 0.25


def cover(y, items):
    """x-intervals blocked on the line y by items [(kind, data, grow)]"""
    iv = []
    for it in items:
        if it[0] == "seg":
            (ax, ay), (bx, by), g = it[1], it[2], it[3]
            # points of the segment closer than g to the line: sample
            n = max(2, int(math.hypot(bx - ax, by - ay) / 0.02))
            xs = []
            for i in range(n + 1):
                x = ax + (bx - ax) * i / n
                yy = ay + (by - ay) * i / n
                d = abs(yy - y)
                if d < g:
                    h = math.sqrt(g * g - d * d)
                    xs += [x - h, x + h]
            if xs:
                iv.append((min(xs), max(xs)))
        elif it[0] == "poly":
            poly, g = it[1], it[2]
            ys = [p[1] for p in poly]
            if min(ys) - g <= y <= max(ys) + g:
                xs = [p[0] for p in poly]
                iv.append((min(xs) - g, max(xs) + g))
    iv.sort()
    merged = []
    for a, b in iv:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def main():
    geo = json.load(open(GEO))
    res = {}
    for lay in ("F", "B"):
        items = []
        for t in geo["tracks"]:
            if t["layer"] == lay and t["net"] not in NORTH:
                items.append(("seg", t["a"], t["b"], t["w"] / 2 + CLR + HW))
        for v in geo["vias"]:
            if v["net"] not in NORTH:
                items.append(("seg", (v["x"], v["y"]), (v["x"], v["y"]), v["d"] / 2 + CLR + HW))
        for p in geo["pads"]:
            if lay in p["layers"] and p["net"] not in NORTH and len(p["poly"]) >= 3:
                g = (1.0 + HW) if (p["ref"] in ("Y1", "C76", "C77") and lay == "F") else CLR + HW
                items.append(("poly", p["poly"], g))
        if lay == "B":
            items.append(("poly", [[c, d] for c, d in ((geo["court"]["Y1"][0], geo["court"]["Y1"][1]),
                                                       (geo["court"]["Y1"][2], geo["court"]["Y1"][3]))], HW))
        for y in (26.0, 25.5, 25.0, 24.5, 24.0, 23.5, 23.0, 22.0):
            blocked = cover(y, items)
            free = []
            x = X0
            for a, b in blocked:
                if a > x:
                    free.append((x, a))
                x = max(x, b)
            if x < X1:
                free.append((x, X1))
            free = [(round(a, 2), round(b, 2)) for a, b in free if b > max(a, X0) and a < X1]
            cap = sum(int((b - a) / PITCH) + 1 for a, b in free if b - a >= 0)
            res["%s y=%.1f" % (lay, y)] = {"free": free, "lanes": cap}
            print("%s y=%4.1f  lanes side by side: %2d   free x-intervals: %s" % (
                "L1" if lay == "F" else "L4", y, cap, " ".join("%.2f-%.2f" % iv for iv in free)))
    print("north lanes to bring out: %d (+ NPOR, done in L5 by its ring-1 parts)" % len(NORTH))
    json.dump(res, open(os.path.join(PCB, "l5", "north_cut.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
