#!/usr/bin/env python3
"""Layout phase L5, step 0: small local placement moves needed for routing (D-H5 allows them; each is recorded in
decisions.md D-113). Runs on the L4 board, before the L5 routing scripts.

  TP26 (FEPHY_AVDD3V3 sub-rail test pad, ring 2, fed by FB1): moved from (22.27, 36.37) to (20.90, 33.40), north-west of
  FB1. At the old spot its 1.5 mm pad sat in the only corridor (y 35.4-37.2, x 21-23.5) through which the ten west
  header lanes of U9 (pins 104-114) can leave the ring-1 row towards the header J5: with it there the lane router
  could not bring out more than 6 of 10 lanes. The new spot is free copper (no track within 2 mm, checked by
  l5_lanes.py's self-check and DRC), 2.2 mm from FB1.2 (the TP's feeder, layout.md §5.3 ring 2 'short stub').
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

PLACE = {"TP26": (20.90, 33.40)}      # board mm (footprint origin = pad centre)


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    for ref, (x, y) in PLACE.items():
        fp = board.FindFootprintByReference(ref)
        x0, y0 = bl.to_board(fp.GetPosition())
        fp.SetPosition(bl.to_page(x, y))
        print("%s moved (%.2f, %.2f) -> (%.2f, %.2f)" % (ref, x0, y0, x, y))
    pcbnew.SaveBoard(bl.BOARD_FILE, board)


if __name__ == "__main__":
    main()
