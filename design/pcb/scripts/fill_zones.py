#!/usr/bin/env python3
"""Layout phase L3, step 5: fill every copper zone (pcbnew ZONE_FILLER) and save the board.

    $PY design/pcb/scripts/fill_zones.py          # after planes.py (and again after any later copper change)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    empty = []
    for z in zones:
        area = 0.0
        for lyr in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(lyr) and z.HasFilledPolysForLayer(lyr):
                area += z.GetFilledPolysList(lyr).Area() / 1e12
        if area <= 0:
            empty.append(z.GetZoneName())
    print("filled %d zones; empty after fill: %d %s" % (len(zones), len(empty), " ".join(empty)))


if __name__ == "__main__":
    main()
