#!/usr/bin/env python3
"""Layout phase L5 round 4 (KiCad Python, D-116): apply design/pcb/l5/finish.json (l5_finish.py) to the saved board.

    $PY design/pcb/scripts/l5_finish_write.py

1. removes the ripped tracks / vias (matched by net, layer and end points within 1 um),
2. moves the parts of D-116 d/h (courtyard centre to the target, optionally turned 180 deg about it),
3. writes the new tracks and vias as board group L5_FINISH, and saves.
Runs once on a board without L5_FINISH (rebuild_all.sh rebuilds from scratch).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

SRC = os.path.join(bl.PCB_DIR, "l5", "finish.json")
LAY = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}


def close(p, q, tol=1e-3):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def main():
    data = json.load(open(SRC))
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, "L5_FINISH")
    dead = []
    want_t = [(n, LAY[l], tuple(a), tuple(b)) for n, l, a, b in data["rip_tracks"]]
    want_v = [(n, (x, y)) for n, x, y in data["rip_vias"]]
    for o in board.GetTracks():
        if o.GetClass() == "PCB_VIA":
            p = bl.to_board(o.GetPosition())
            if any(n == o.GetNetname() and close(p, q) for n, q in want_v):
                dead.append(o)
        elif o.GetClass() == "PCB_TRACK":
            a, b = bl.to_board(o.GetStart()), bl.to_board(o.GetEnd())
            for n, l_, ra, rb in want_t:
                if n == o.GetNetname() and l_ == o.GetLayer() and ((close(a, ra) and close(b, rb)) or
                                                                    (close(a, rb) and close(b, ra))):
                    dead.append(o)
                    break
    exp = len(want_t) + len(want_v)
    if len(dead) != exp:
        sys.exit("l5_finish_write: matched %d of %d ripped items" % (len(dead), exp))
    for o in dead:
        board.Remove(o)
    for ref, (x, y, rot) in sorted(data["moves"].items()):
        fp = board.FindFootprintByReference(ref)
        c = bl.courtyard_bbox(fp)
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        if rot:
            fp.Rotate(bl.to_page(cx, cy), pcbnew.EDA_ANGLE(180.0, pcbnew.DEGREES_T))
        fp.Move(pcbnew.VECTOR2I(pcbnew.FromMM(x - cx), pcbnew.FromMM(y - cy)))
        print("move %s: courtyard centre (%.2f, %.2f) -> (%.2f, %.2f)%s" % (ref, cx, cy, x, y,
                                                                         ", turned 180 deg" if rot else ""))
    items = []
    nt = nv = 0
    for net in sorted(data["routes"]):
        r = data["routes"][net]
        for layer, pts, w in r["tracks"]:
            items += rl.add_track(board, net, layer, [tuple(p) for p in pts], w)
            nt += len(pts) - 1
        for v in r["vias"]:
            items.append(rl.add_via(board, net, v[0], v[1]))
            nv += 1
    rl.group(board, "L5_FINISH", items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    print("L5_FINISH: removed %d tracks / vias, wrote %d track segments and %d vias on %d nets" % (
        len(dead), nt, nv, len(data["routes"])))


if __name__ == "__main__":
    main()
