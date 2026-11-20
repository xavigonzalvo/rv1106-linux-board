#!/usr/bin/env python3
"""Layout phase L4: write design/pcb/l4/routes.json (l4_route.py) into the board as tracks and vias (group
L4_CRITICAL), then save. Re-runnable only from a fresh L3 board (rebuild_all.sh), like every other routing script.

    $PY design/pcb/scripts/l4_write.py [routes.json]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

GROUP = "L4_CRITICAL"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(bl.PCB_DIR, "l4", "routes.json")
    data = json.load(open(src))
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, GROUP)
    items = []
    nt = nv = 0
    for net in sorted(data["routes"]):
        r = data["routes"][net]
        for layer, pts, w in r["tracks"]:
            items += rl.add_track(board, net, layer, [tuple(p) for p in pts], w)
            nt += len(pts) - 1
        for x, y in r["vias"]:
            items.append(rl.add_via(board, net, x, y))
            nv += 1
    rl.group(board, GROUP, items)
    board.Save(bl.BOARD_FILE)
    print("L4: wrote %d track segments, %d vias on %d nets (group %s)" % (nt, nv, len(data["routes"]), GROUP))
    if data.get("fails"):
        print("L4: router reported %d failures: %s" % (len(data["fails"]), data["fails"]))


if __name__ == "__main__":
    main()
