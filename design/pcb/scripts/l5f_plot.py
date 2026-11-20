#!/usr/bin/env python3
"""Layout phase L5F: annotated close-up plot of the board copper (design/.venv, matplotlib).

    design/.venv/bin/python -I design/pcb/scripts/l5f_plot.py geo.json x0 y0 x1 y1 out.png [layers] [title]

layers: comma list of F,B,In2 (default F,B); S adds the silk labels (L5G: ink box, text, dotted link to the owner's
copper; green = beside its own part, red = breaks the L5G-silk rule). Fills drawn light (F red, B blue, In2 GND green / In2 power yellow),
tracks darker, Edge.Cuts black, V-CUT dashed purple, pads by net
(GND grey, SW nets orange, other nets tan), vias as rings, courtyards dashed magenta, pad labels ref.pad/net.
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402

FILL = {"F": "#f6c9c9", "B": "#c9d8f6", "In2": "#c9f0cf", "In1": "#eeeeee"}
TRK = {"F": "#c0392b", "B": "#1f5fbf", "In2": "#1e8449", "In1": "#777777"}


def main():
    geo = json.load(open(sys.argv[1]))
    x0, y0, x1, y1 = map(float, sys.argv[2:6])
    out = sys.argv[6]
    layers = (sys.argv[7] if len(sys.argv) > 7 else "F,B").split(",")
    title = sys.argv[8] if len(sys.argv) > 8 else ""
    s = 10.0
    fig, ax = plt.subplots(figsize=(s, s * (y1 - y0) / (x1 - x0)), dpi=160)
    k = 72 * s / (x1 - x0)

    def vis(pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return not (max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1)
    for lay in layers:
        for f in geo.get("fills", []):
            if f["layer"] != lay or not vis(f["outline"]):
                continue
            verts, codes = [], []
            for ring in [f["outline"]] + f["holes"]:
                verts += ring + [ring[0]]
                codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
            fc = FILL[lay] if not (lay == "In2" and f["net"] != "GND") else "#f3dc7a"    # In2: GND green, power yellow
            ax.add_patch(PathPatch(Path(verts, codes), fc=fc, ec="none", alpha=0.75, zorder=1))
    for p in geo["pads"]:
        if len(p["poly"]) < 3 or not vis(p["poly"]) or not (set(p["layers"]) & set(layers) or p["th"]):
            continue
        col = "#9a9a9a" if p["net"] == "GND" else ("#f0a040" if p["net"].endswith("_SW") else "#d9c39a")
        ax.add_patch(Polygon(p["poly"], closed=True, fc=col, ec="#555555", lw=0.4, zorder=3, alpha=0.9))
        if x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1 and (x1 - x0) <= 30:
            ax.text(p["x"], p["y"], "%s.%s\n%s" % (p["ref"], p["num"], p["net"][:14]), fontsize=4.2, ha="center",
                    va="center", color="#111111", zorder=8, clip_on=True)
    for t in geo["tracks"]:
        if t["layer"] not in layers or not vis([t["a"], t["b"]]):
            continue
        ax.plot([t["a"][0], t["b"][0]], [t["a"][1], t["b"][1]], color=TRK[t["layer"]], lw=t["w"] * k,
                solid_capstyle="round", zorder=4 if t["layer"] == "F" else 2.5, alpha=0.8)
    for v in geo["vias"]:
        if x0 - 1 <= v["x"] <= x1 + 1 and y0 - 1 <= v["y"] <= y1 + 1:
            ax.add_patch(Circle((v["x"], v["y"]), v["d"] / 2, fc="#ffffff", ec="#444444", lw=0.6, zorder=6))
            ax.add_patch(Circle((v["x"], v["y"]), v["drill"] / 2, fc="#222222", ec="none", zorder=6.5))
            if (x1 - x0) <= 30:
                ax.text(v["x"], v["y"] + 0.33, v["net"][:10], fontsize=3.2, ha="center", color="#333333", zorder=8, clip_on=True)
    for ref, cb in geo["court"].items():
        if cb and vis([cb[:2], cb[2:]]):
            ax.add_patch(Rectangle((cb[0], cb[1]), cb[2] - cb[0], cb[3] - cb[1], fc="none", ec="#cc00cc", lw=0.5,
                                   ls="--", zorder=7))
            if (x1 - x0) <= 30:
                ax.text(cb[0], cb[1] - 0.05, ref, fontsize=5, color="#990099", zorder=8, clip_on=True)
    if "S" in layers:                         # L5G: silk labels (ink box, text, link to the owner's copper)
        for t in geo.get("silk", []):
            b = t["box"]
            if not vis([b[:2], b[2:]]):
                continue
            col = "#1a7f37" if t["ok"] else "#d62728"
            ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc="#fff6b0", ec=col, lw=0.8, zorder=9.6,
                                   alpha=0.95))
            ax.text((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, t["text"], fontsize=6, ha="center", va="center",
                    color="#000000", zorder=9.7, clip_on=True, fontweight="bold")
            if t.get("own_xy"):
                ax.plot([(b[0] + b[2]) / 2, t["own_xy"][0]], [(b[1] + b[3]) / 2, t["own_xy"][1]], color=col, lw=0.6,
                        ls=":", zorder=9.65)
    for pts in geo.get("edges", []):          # board / panel outline (Edge.Cuts)
        ax.plot([q[0] for q in pts], [q[1] for q in pts], color="#000000", lw=1.4, zorder=9.5)
    for pts in geo.get("vcut", []):           # V-CUT user layer
        ax.plot([q[0] for q in pts], [q[1] for q in pts], color="#8e44ad", lw=1.0, ls="--", zorder=9.4)
    for ln in geo.get("lines", []):
        ax.plot([ln[0], ln[2]], [ln[1], ln[3]], color="#000000", lw=0.8, ls=":", zorder=9)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.2)
    ax.set_title("%s  (board mm; layers %s; fills light, tracks dark)" % (title, "+".join(layers)), fontsize=8)
    fig.tight_layout()
    fig.savefig(out)


if __name__ == "__main__":
    main()
