#!/usr/bin/env python3
"""Layout phase L5F: export the board copper for the L5F plots (l5f_plot.py) and checks run in design/.venv.

    $PY design/pcb/scripts/l5f_geo.py [board.kicad_pcb] out.json

Same content as l4_export.py (pads, tracks, vias, courtyards) plus the filled zone polygons of every copper layer
(net, layer, outlines with holes) and the footprint values, so a plot shows pours and part names.
"""
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

LN = {pcbnew.F_Cu: "F", pcbnew.B_Cu: "B", pcbnew.In1_Cu: "In1", pcbnew.In2_Cu: "In2"}


def main():
    args = sys.argv[1:]
    board_file = args[0] if len(args) > 1 else bl.BOARD_FILE
    out = args[-1]
    tmp = out + ".base.json"
    env = dict(os.environ, PCB_BOARD=os.path.abspath(board_file))
    subprocess.run([sys.executable, os.path.join(bl.HERE, "l4_export.py"), tmp], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    geo = json.load(open(tmp))
    os.remove(tmp)
    board = pcbnew.LoadBoard(board_file)
    geo["fills"] = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for lay, ln in LN.items():
            if not z.IsOnLayer(lay) or not z.HasFilledPolysForLayer(lay):
                continue
            ps = z.GetFilledPolysList(lay)
            for k in range(ps.OutlineCount()):
                o = ps.Outline(k)
                holes = [[list(bl.to_board(ps.Hole(k, h).CPoint(i))) for i in range(ps.Hole(k, h).PointCount())]
                         for h in range(ps.HoleCount(k))]
                geo["fills"].append({"net": z.GetNetname(), "layer": ln, "name": z.GetZoneName(),
                                     "outline": [list(bl.to_board(o.CPoint(i))) for i in range(o.PointCount())],
                                     "holes": holes})
    # round 2 (verifier minor): the outline (Edge.Cuts, arcs as polylines) and the V-CUT lines, for the corner plots
    geo["edges"], geo["vcut"] = [], []
    for d in board.GetDrawings():
        lay = d.GetLayer()
        if lay not in (pcbnew.Edge_Cuts, pcbnew.User_1) or d.GetClass() != "PCB_SHAPE":
            continue
        if d.GetShape() == pcbnew.SHAPE_T_ARC:
            c = bl.to_board(d.GetCenter())
            r = pcbnew.ToMM(d.GetRadius())
            st, md, en = (bl.to_board(v) for v in (d.GetStart(), d.GetArcMid(), d.GetEnd()))
            a0 = math.atan2(st[1] - c[1], st[0] - c[0])
            am = (math.atan2(md[1] - c[1], md[0] - c[0]) - a0) % (2 * math.pi)
            da = (math.atan2(en[1] - c[1], en[0] - c[0]) - a0) % (2 * math.pi)
            if am > da:                  # the arc runs the other way round
                da -= 2 * math.pi
            pts = [[c[0] + r * math.cos(a0 + da * i / 24), c[1] + r * math.sin(a0 + da * i / 24)] for i in range(25)]
        elif d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            pts = [list(bl.to_board(d.GetStart())), list(bl.to_board(d.GetEnd()))]
        else:
            continue
        (geo["edges"] if lay == pcbnew.Edge_Cuts else geo["vcut"]).append(pts)
    # L5G (D-H7 item 10): the visible silk texts (ink box, owner, rule result; l5g_silklib.py) for the silk plots
    import l5g_silklib as S
    geo["silk"] = []
    for r in S.evaluate(board):
        own = None
        if r[2] and r[2] != "BOARD":
            fp = board.FindFootprintByReference(r[2])
            pads = [p for p in fp.Pads() if r[3] is None or p.GetNumber() == r[3]] if fp else []
            if pads:
                own = [sum(bl.to_board(p.GetPosition())[0] for p in pads) / len(pads),
                       sum(bl.to_board(p.GetPosition())[1] for p in pads) / len(pads)]
        geo["silk"].append({"text": r[1], "box": list(r[4]), "owner": r[2], "pad": r[3], "own_xy": own,
                            "ok": bool(r[8]), "d_own": r[5], "other": list(r[6]) if r[6] else None})
    geo["parts"] = {fp.GetReference(): [list(bl.to_board(fp.GetPosition())), fp.GetOrientation().AsDegrees(),
                                        fp.GetValue()] for fp in board.GetFootprints()}
    with open(out, "w") as fh:
        json.dump(geo, fh)
    print("l5f_geo: %d pads, %d tracks, %d vias, %d fill pieces -> %s" % (
        len(geo["pads"]), len(geo["tracks"]), len(geo["vias"]), len(geo["fills"]), out))


if __name__ == "__main__":
    main()
