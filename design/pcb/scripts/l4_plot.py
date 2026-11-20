#!/usr/bin/env python3
"""Layout phase L4: close-up plot of the exported board geometry + routes.json (design/.venv, matplotlib).

    design/.venv/bin/python -I design/pcb/scripts/l4_plot.py x0 y0 x1 y1 out.png [routes.json] [geo.json]
Pads grey (critical nets pink), L1 tracks red, L4 tracks blue, vias rings, new routes darker and thicker.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))


def main():
    x0, y0, x1, y1 = map(float, sys.argv[1:5])
    out = sys.argv[5]
    routes = json.load(open(sys.argv[6] if len(sys.argv) > 6 else os.path.join(PCB, "l4", "routes.json")))["routes"]
    geo = json.load(open(sys.argv[7] if len(sys.argv) > 7 else os.path.join(PCB, "l4", "board_geo.json")))
    s = max(6.0, min(18.0, 0.9 * max(x1 - x0, y1 - y0)))
    fig, ax = plt.subplots(figsize=(s, s * (y1 - y0) / (x1 - x0)), dpi=150)
    for p in geo["pads"]:
        if len(p["poly"]) < 3:
            continue
        xs = [q[0] for q in p["poly"]]
        ys = [q[1] for q in p["poly"]]
        if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
            continue
        col = "#f2b8b8" if p["net"] in routes else "#cfcfcf"
        ax.add_patch(Polygon(p["poly"], closed=True, fc=col, ec="#888888", lw=0.3))
        if (x1 - x0) < 30 and x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1:
            ax.text(p["x"], p["y"], "%s.%s\n%s" % (p["ref"], p["num"], p["net"][:12]), fontsize=3.5, ha="center",
                    va="center", color="#333333")
    for t in geo["tracks"]:
        if t["layer"] not in ("F", "B"):
            continue
        ax.plot([t["a"][0], t["b"][0]], [t["a"][1], t["b"][1]], color="#e8a0a0" if t["layer"] == "F" else "#a0b8e8",
                lw=t["w"] * 72 * s / (x1 - x0) / 1.0, solid_capstyle="round", zorder=2)
    for v in geo["vias"]:
        ax.add_patch(Circle((v["x"], v["y"]), v["d"] / 2, fc="#bbbbbb", ec="#777777", lw=0.3, zorder=3))
    for net, r in routes.items():
        for layer, pts, w in r["tracks"]:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#c0392b" if layer == "F" else "#1f5fbf",
                    lw=w * 72 * s / (x1 - x0), solid_capstyle="round", zorder=4 if layer == "F" else 3.5, alpha=0.85)
        for x, y in r["vias"]:
            ax.add_patch(Circle((x, y), 0.25, fc="white", ec="#1f5fbf", lw=0.8, zorder=5))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.2)
    fig.tight_layout()
    fig.savefig(out)


if __name__ == "__main__":
    main()
