#!/usr/bin/env python3
"""Layout phase L5 round 4 (KiCad Python, D-116 i; verifier round-3 minor soc): remove redundant L5 track segments.

    $PY design/pcb/scripts/l5_tidy.py

In the L5 routing groups a track segment is removed when
  - it is (nearly) zero length (< 10 um): the segments attached at its end are moved to its start, or
  - both its end points lie on the copper of one other track of the same net and layer (distance to that track's
    centre line <= its half width - 1 um, projecting onto it), the two run within 5 deg of each other, it is not wider
    than that track, and an end where other segments attach lies on that track's centre line (within 2 um)
    (a duplicate lying on top of / beside another one: the NPOR pair at C71.1, the UART2_RX piece at R67.2).
Whatever was attached at the removed segment's ends lies on the kept track, so connectivity does not change
(KiCad joins a track end lying on another track). Repeated until nothing changes; the board is saved.
check_routing.py (L5-geom) FAILs any such segment left on the board and any joint of two segments under 5 deg.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

GROUPS = ("L5_LANES", "L5_PRIORITY", "L5_NORTH", "L5_FREEROUTE", "L5_SCRIPT", "L5_FINISH")


def redundant(T):
    """indices of redundant segments in T = [(net, layer, a, b, hw, group, obj)] (pure geometry, also used by the
    checker)"""
    out = []
    by = {}
    for i, t in enumerate(T):
        by.setdefault((t[0], t[1]), []).append(i)
    alive = [True] * len(T)

    def on_body(p, o):
        """p within o's copper and projecting onto o (not beyond its ends by more than 0.01 mm)"""
        dx, dy = o[3][0] - o[2][0], o[3][1] - o[2][1]
        L2 = dx * dx + dy * dy
        tt = ((p[0] - o[2][0]) * dx + (p[1] - o[2][1]) * dy) / L2
        L = math.sqrt(L2)
        return -0.01 / L <= tt <= 1 + 0.01 / L and bl._seg_pt(p[0], p[1], o[2][0], o[2][1], o[3][0], o[3][1]) <= o[4] - 1e-3

    def attached(p, i, j):
        """another live segment of the net/layer (not i, not j) ends at p"""
        t = T[i]
        for k in by[(t[0], t[1])]:
            if k in (i, j) or not alive[k]:
                continue
            for q in (T[k][2], T[k][3]):
                if abs(q[0] - p[0]) < 2e-3 and abs(q[1] - p[1]) < 2e-3:
                    return True
        return False
    changed = True
    while changed:
        changed = False
        for i, t in enumerate(T):
            if not alive[i] or t[5] not in GROUPS:
                continue
            ln = math.hypot(t[3][0] - t[2][0], t[3][1] - t[2][1])
            if ln < 0.01:
                # keep the end whose attached segments are not collinear with the piece (moving a collinear
                # neighbour's end along its own line keeps it at 0/45/90 deg)
                def coll(p_):
                    for k in by[(t[0], t[1])]:
                        if k == i or not alive[k]:
                            continue
                        o = T[k]
                        for q, r in ((o[2], o[3]), (o[3], o[2])):
                            if abs(q[0] - p_[0]) < 2e-3 and abs(q[1] - p_[1]) < 2e-3:
                                dx, dy = r[0] - q[0], r[1] - q[1]
                                ux, uy = t[3][0] - t[2][0], t[3][1] - t[2][1]
                                if abs(dx * uy - dy * ux) > 0.02 * math.hypot(dx, dy) * max(1e-9, math.hypot(ux, uy)):
                                    return False
                    return True
                if not coll(t[3]) and coll(t[2]):
                    T[i] = t = (t[0], t[1], t[3], t[2]) + t[4:]
                alive[i] = False
                out.append((i, "zero length (< 10 um; the segments at its end %s are moved to %s)" % (
                    tuple(round(c, 4) for c in t[3]), tuple(round(c, 4) for c in t[2]))))
                changed = True
                continue
            for j in by[(t[0], t[1])]:
                if j == i or not alive[j]:
                    continue
                o = T[j]
                lo = math.hypot(o[3][0] - o[2][0], o[3][1] - o[2][1])
                if lo < 1e-3 or t[4] > o[4] + 1e-6:
                    continue
                cosang = abs(((t[3][0] - t[2][0]) * (o[3][0] - o[2][0]) + (t[3][1] - t[2][1]) * (o[3][1] - o[2][1]))
                             / ln / lo)
                if cosang < math.cos(math.radians(5.0)):
                    continue
                if all(on_body(p, o) for p in (t[2], t[3])) and \
                        all(not attached(p, i, j) or bl._seg_pt(p[0], p[1], o[2][0], o[2][1], o[3][0], o[3][1]) <= 2e-3
                            for p in (t[2], t[3])):
                    alive[i] = False
                    out.append((i, "on %s" % j))
                    changed = True
                    break
    return out


def segments(board):
    gmap = {}
    for g in board.Groups():
        for it in g.GetItems():
            o = it.Cast()
            if o.GetClass() == "PCB_TRACK":
                gmap[o.m_Uuid.AsString()] = g.GetName()
    T = []
    for o in board.GetTracks():
        if o.GetClass() == "PCB_TRACK":
            T.append((o.GetNetname(), o.GetLayer(), bl.to_board(o.GetStart()), bl.to_board(o.GetEnd()),
                      pcbnew.ToMM(o.GetWidth()) / 2, gmap.get(o.m_Uuid.AsString(), ""), o))
    return T


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    T = segments(board)
    red = redundant(T)
    for i, why in red:
        t = T[i]
        print("  remove %s %s (%.3f, %.3f)-(%.3f, %.3f) w %.3f [%s]: %s" % (
            t[0], "F" if t[1] == pcbnew.F_Cu else "B", t[2][0], t[2][1], t[3][0], t[3][1], 2 * t[4], t[5], why))
    for i, why in red:
        if why.startswith("zero length"):
            t = T[i]
            for k, o in enumerate(T):
                if k == i or o[0] != t[0] or o[1] != t[1]:
                    continue
                for getp, setp in ((o[6].GetStart, o[6].SetStart), (o[6].GetEnd, o[6].SetEnd)):
                    q = bl.to_board(getp())
                    if abs(q[0] - t[3][0]) < 2e-3 and abs(q[1] - t[3][1]) < 2e-3:
                        setp(bl.to_page(*t[2]))
    for i, _ in red:
        board.Remove(T[i][6])
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    print("tidy: removed %d redundant L5 track segments" % len(red))


if __name__ == "__main__":
    main()
