#!/usr/bin/env python3
"""Layout phase L5 round 3 (design/.venv): the verifier's suggested scripted route for the three inner-via nets
(verifier round 2, major onoff), measured on the L4 board (design/pcb/l5/board_geo.json). Nothing is written to the
board; the result goes to design/pcb/l5/inner_probe.txt and decisions.md D-115 (g).

  1. USB_SEL / PB_INT_N: their inner vias sit in the L4 corridor between SARADC_IN1 and RECOVERY; the corridor's south
     end is the gap between the two SENSE vias at y 41.65: exact check of a 0.10 mm track through it.
  2. SDMMC_PWREN: the verifier's via site (41.6, 40.7); all legal via sites at x 41.55-42.25, y 36.5-42.5 (the strip
     between the U9 courtyard and the ring-1 no-via band); the exact L4 router (0.10 mm) from the inner via to each.

    design/.venv/bin/python -I design/pcb/scripts/l5_inner_probe.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
GEO = os.path.join(PCB, "l5", "board_geo.json")
OUT = os.path.join(PCB, "l5", "inner_probe.txt")
sys.argv = [sys.argv[0], GEO, os.path.join(PCB, "l5", "_unused_probe.json")]
sys.path.insert(0, HERE)
import l4_route as R  # noqa: E402
import l4lib as L  # noqa: E402

L.VIA_ETH = True
R.setup_novia()
R.setup_sw_areas()
S = R.S
lines = []


def out(s):
    print(s)
    lines.append(s)


vs = {n: sorted((v["x"], v["y"]) for v in R.geo["vias"] if v["net"] == n and L.FAN[0] <= v["x"] <= L.FAN[2] and
                L.FAN[1] <= v["y"] <= L.FAN[3]) for n in ("USB_SEL", "PB_INT_N", "SDMMC_PWREN")}
out("inner vias: %s" % vs)
sa = [v for v in R.geo["vias"] if v["net"] == "SARADC_IN1" and abs(v["y"] - 41.65) < 0.05]
rc = [v for v in R.geo["vias"] if v["net"] == "RECOVERY" and abs(v["y"] - 41.65) < 0.05]
if sa and rc:
    xm = (sa[0]["x"] + rc[0]["x"]) / 2
    gap = abs(rc[0]["x"] - sa[0]["x"]) - (sa[0]["d"] + rc[0]["d"]) / 2
    out("SENSE via gap at y 41.65: SARADC_IN1 x %.3f, RECOVERY x %.3f, copper gap %.3f mm" % (sa[0]["x"], rc[0]["x"], gap))
    for n in ("USB_SEL", "PB_INT_N"):
        r = S.check_seg(n, L.B, (xm, 41.0), (xm, 42.3), 0.05, report=True)
        out("%s: 0.10 mm track through the gap: %s" % (n, "legal" if not r else "violations %s" % [
            (a, round(b, 4), c) for a, b, c, _ in r[:4]]))
out("via (41.6, 40.7) for SDMMC_PWREN legal: %s" % S.check_via("SDMMC_PWREN", 41.6, 40.7, novia=R.GRID_NOVIA))
sites = [(round(41.55 + i * 0.025, 3), round(36.5 + j * 0.1, 2)) for i in range(28) for j in range(60)
         if S.check_via("SDMMC_PWREN", 41.55 + i * 0.025, 36.5 + j * 0.1, novia=R.GRID_NOVIA)]
out("legal SDMMC_PWREN via sites x 41.55-42.25, y 36.5-42.5: %d" % len(sites))
src = vs["SDMMC_PWREN"][0]
reach = 0
for (x, y) in sites[::3]:
    n_i, n_h = len(S.items), len(S.holes)
    ok = R.route_net("SDMMC_PWREN", [R.pt(src[0], src[1], L.B), R.pt(x, y, L.B)], layers=L.B, w=0.10, margin=3.0)
    del S.items[n_i:]
    del S.holes[n_h:]
    S._arr = None
    R.ROUTES.pop("SDMMC_PWREN", None)
    if ok:
        reach += 1
        out("  L4 route inner via -> (%.3f, %.2f): ok" % (x, y))
out("SDMMC_PWREN: L4 routes from the inner via to %d of %d sampled sites" % (reach, len(sites[::3])))
open(OUT, "w").write("\n".join(lines) + "\n")
