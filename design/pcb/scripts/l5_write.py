#!/usr/bin/env python3
"""Layout phase L5: write a routes file ({"routes": {net: {"tracks": [[layer, pts, w]], "vias": [[x, y]]}}}) into the
board as tracks and vias in one board group, then save. Like l4_write.py, it only runs on a board that does not have
that group yet (rebuild_all.sh rebuilds from scratch; pcbnew Remove() is not used, D-110).

    $PY design/pcb/scripts/l5_write.py <routes.json> <GROUP>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402


def main():
    src, group = sys.argv[1], sys.argv[2]
    data = json.load(open(src))
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, group)
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
    rl.group(board, group, items)
    board.Save(bl.BOARD_FILE)
    print("%s: wrote %d track segments, %d vias on %d nets" % (group, nt, nv, len(data["routes"])))
    if data.get("fails"):
        print("%s: the router reported %d failures: %s" % (group, len(data["fails"]), data["fails"]))


if __name__ == "__main__":
    main()
