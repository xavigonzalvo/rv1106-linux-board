#!/usr/bin/env python3
"""Layout phase L5 round 3 (KiCad Python): remove the L5 copper that ends in nothing (verifier round 2, blocker gpio:
"remove every stub that stays open"). D-115.

    $PY design/pcb/scripts/l5_prune.py        # edits the saved board; prints what was removed

Only the L5 routing groups are touched (L5_LANES, L5_PRIORITY, L5_FREEROUTE, L5_SCRIPT); L3/L4 copper and the GND
stitching are never removed. On a geometric copy of the copper, repeated until nothing changes:
  - a track whose end touches no pad, no via and no other track of its net on its layer (the end point inside the
    other copper's width or the pad polygon) is dropped;
  - a via of these groups that keeps copper (a track of its net on the layer, or a pad) on fewer than two outer layers
    is dropped.
The dropped items are then removed from the board in one pass and the board is saved. A lane whose route stopped
(its net stays unconnected) thus loses its stub, column and bus copper back to the L3 escape end at the U9 gate;
nets that are connected keep everything (no end of theirs dangles).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

GROUPS = ("L5_LANES", "L5_PRIORITY", "L5_FREEROUTE", "L5_SCRIPT")


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    gmap = {}
    for g in board.Groups():
        for it in g.GetItems():
            o = it.Cast()
            if o.GetClass() == "PCB_VIA":
                p = bl.to_board(o.GetPosition())
                gmap[("v", o.GetNetname(), round(p[0], 4), round(p[1], 4))] = g.GetName()
            elif o.GetClass() == "PCB_TRACK":
                a, b = bl.to_board(o.GetStart()), bl.to_board(o.GetEnd())
                gmap[("t", o.GetNetname(), o.GetLayer(), round(a[0], 4), round(a[1], 4), round(b[0], 4),
                      round(b[1], 4))] = g.GetName()
    T, V = [], []
    for o in board.GetTracks():
        if o.GetClass() == "PCB_VIA":
            p = bl.to_board(o.GetPosition())
            V.append([o.GetNetname(), p, pcbnew.ToMM(o.GetWidth(pcbnew.F_Cu)) / 2,
                      gmap.get(("v", o.GetNetname(), round(p[0], 4), round(p[1], 4)), ""), True, o])
        elif o.GetClass() == "PCB_TRACK":
            a, b = bl.to_board(o.GetStart()), bl.to_board(o.GetEnd())
            T.append([o.GetNetname(), o.GetLayer(), a, b, pcbnew.ToMM(o.GetWidth()) / 2,
                      gmap.get(("t", o.GetNetname(), o.GetLayer(), round(a[0], 4), round(a[1], 4), round(b[0], 4),
                                round(b[1], 4)), ""), True, o])
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            lays = [l_ for l_ in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l_)]
            pads.setdefault(p.GetNetname(), []).append((bl.pad_polygon(p), lays))
    tn, vn = {}, {}
    for t in T:
        tn.setdefault(t[0], []).append(t)
    for v in V:
        vn.setdefault(v[0], []).append(v)
    changed = True
    while changed:
        changed = False
        for t in T:
            if not t[6] or t[5] not in GROUPS:
                continue
            net, lay = t[0], t[1]
            for e in (t[2], t[3]):
                ok = any(v[4] and math.hypot(e[0] - v[1][0], e[1] - v[1][1]) <= v[2] + 1e-3 for v in vn.get(net, []))
                ok = ok or any(lay in lays and bl._inside(e[0], e[1], poly) for poly, lays in pads.get(net, []))
                ok = ok or any(o is not t and o[6] and o[1] == lay and
                               bl._seg_pt(e[0], e[1], o[2][0], o[2][1], o[3][0], o[3][1]) <= o[4] + 1e-3
                               for o in tn.get(net, []))
                if not ok:
                    t[6] = False
                    changed = True
                    break
        for v in V:
            if not v[4] or v[3] not in GROUPS:
                continue
            net, q = v[0], v[1]
            lays = {o[1] for o in tn.get(net, []) if o[6] and
                    bl._seg_pt(q[0], q[1], o[2][0], o[2][1], o[3][0], o[3][1]) <= v[2] + 1e-3}
            for poly, pl in pads.get(net, []):
                if bl._inside(q[0], q[1], poly):
                    lays |= set(pl)
            if len(lays & {pcbnew.F_Cu, pcbnew.B_Cu}) < 2:
                v[4] = False
                changed = True
    dead_t = [t for t in T if not t[6]]
    dead_v = [v for v in V if not v[4]]
    nets = sorted({x[0] for x in dead_t + dead_v})
    for x in dead_t:
        board.Remove(x[7])
    for x in dead_v:
        board.Remove(x[5])
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    print("prune: removed %d dangling L5 track segments and %d L5 vias on %d nets: %s" % (
        len(dead_t), len(dead_v), len(nets), " ".join(nets)))


if __name__ == "__main__":
    main()
