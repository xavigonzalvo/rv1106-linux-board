#!/usr/bin/env python3
"""Layout phase L4: export the saved board's copper geometry for the L4 router (l4_router.py, design/.venv).

    $PY design/pcb/scripts/l4_export.py [out.json]       # default design/pcb/l4/board_geo.json

Board mm (origin NW corner, y south). Pads as copper polygons (F/B layers, TH on all), tracks, vias, NPTH holes,
footprint courtyards, rule areas, the board outline box, the net classes (layout/netclasses.csv) and, per net, the
free ends of its tracks (the U9 gate-lane ends written in L3) - those are the router's start terminals.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

LN = {pcbnew.F_Cu: "F", pcbnew.B_Cu: "B", pcbnew.In1_Cu: "In1", pcbnew.In2_Cu: "In2"}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(bl.PCB_DIR, "l4", "board_geo.json")
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    geo = {"pads": [], "tracks": [], "vias": [], "npth": [], "court": {}, "areas": [], "classes": {}, "ends": {}}
    for r in csv.DictReader(open(os.path.join(bl.LAYOUT, "netclasses.csv"), encoding="utf-8")):
        geo["classes"][r["net"]] = [r["netclass"], float(r["width_mm"]), float(r["clearance_mm"]),
                                    float(r["diff_gap_mm"] or 0)]
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        cb = bl.courtyard_bbox(fp)
        if cb:
            geo["court"][ref] = cb
        for pad in fp.Pads():
            x, y = bl.to_board(pad.GetPosition())
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                geo["npth"].append([x, y, pcbnew.ToMM(pad.GetDrillSize().x) / 2])
                continue
            lay = sorted(rl.pad_layers(pad) & {"F", "B"})
            th = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            geo["pads"].append({"ref": ref, "num": pad.GetNumber(), "net": pad.GetNetname(), "x": x, "y": y,
                                "poly": [list(p) for p in bl.pad_polygon(pad)], "layers": lay, "th": th,
                                "drill": pcbnew.ToMM(pad.GetDrillSize().x) / 2 if th else 0.0})
        for g in fp.GraphicalItems():                       # net-tie copper (NT1)
            if g.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
                continue
            poly = pcbnew.SHAPE_POLY_SET()
            g.TransformShapeToPolygon(poly, g.GetLayer(), 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
            for k in range(poly.OutlineCount()):
                o = poly.Outline(k)
                geo["pads"].append({"ref": ref, "num": "copper", "net": "#FPCOPPER", "x": 0, "y": 0,
                                    "poly": [list(bl.to_board(o.CPoint(i))) for i in range(o.PointCount())],
                                    "layers": [LN[g.GetLayer()]], "th": False, "drill": 0.0})
    for t in board.GetTracks():
        n = t.GetNetname()
        grp = t.GetParentGroup().GetName() if t.GetParentGroup() else ""     # round 4: board group (l5_finish.py rips)
        if t.GetClass() == "PCB_VIA":
            x, y = bl.to_board(t.GetPosition())
            geo["vias"].append({"net": n, "x": x, "y": y, "d": pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)),
                                "drill": pcbnew.ToMM(t.GetDrillValue()), "group": grp})
        else:
            geo["tracks"].append({"net": n, "layer": LN[t.GetLayer()], "a": list(bl.to_board(t.GetStart())),
                                  "b": list(bl.to_board(t.GetEnd())), "w": pcbnew.ToMM(t.GetWidth()), "group": grp})
    for z in board.Zones():
        if z.GetIsRuleArea():
            bb = z.GetBoundingBox()
            x0, y0 = bl.to_board(bb.GetOrigin())
            x1, y1 = bl.to_board(bb.GetEnd())
            geo["areas"].append({"name": z.GetZoneName(), "rect": [x0, y0, x1, y1],
                                 "no_tracks": bool(z.GetDoNotAllowTracks()), "no_vias": bool(z.GetDoNotAllowVias()),
                                 "layers": [LN[l] for l in z.GetLayerSet().Seq() if l in LN]})
    # free track ends per net (not shared with another track/via of the net, not inside one of its pads)
    from collections import defaultdict
    cnt = defaultdict(int)
    for t in geo["tracks"]:
        for p in (t["a"], t["b"]):
            cnt[(t["net"], t["layer"], round(p[0], 3), round(p[1], 3))] += 1
    vset = {(v["net"], round(v["x"], 3), round(v["y"], 3)) for v in geo["vias"]}
    padsby = defaultdict(list)
    for p in geo["pads"]:
        padsby[p["net"]].append(p)
    for t in geo["tracks"]:
        for p in (t["a"], t["b"]):
            k = (t["net"], t["layer"], round(p[0], 3), round(p[1], 3))
            if cnt[k] != 1 or (t["net"], k[2], k[3]) in vset:
                continue
            if any(t["layer"] in q["layers"] and bl._inside(p[0], p[1], q["poly"]) for q in padsby[t["net"]]):
                continue
            o = t["b"] if p is t["a"] else t["a"]
            L = ((p[0] - o[0]) ** 2 + (p[1] - o[1]) ** 2) ** 0.5 or 1.0
            geo["ends"].setdefault(t["net"], []).append([p[0], p[1], t["layer"], t["w"], (p[0] - o[0]) / L,
                                                         (p[1] - o[1]) / L, L])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(geo, fh)
    print("exported %d pads, %d tracks, %d vias, %d free ends -> %s" % (
        len(geo["pads"]), len(geo["tracks"]), len(geo["vias"]), sum(len(v) for v in geo["ends"].values()), out))


if __name__ == "__main__":
    main()
