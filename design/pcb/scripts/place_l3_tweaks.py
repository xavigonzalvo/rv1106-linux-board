#!/usr/bin/env python3
"""Layout phase L3, step 0: small local placement moves needed for routing (D-H5 allows them, each recorded in
decisions.md D-109 (h)). Runs after place.py, before check_placement.py and the L3 scripts.

  C36, C42 (VDD_0V9 ring-2 bulk caps east of U9, 1 mm-pitch stack C46/C36/C47/C42/C45): rotated 180 deg in place, so the
  VDD_0V9 pad sits on the east side, where the free spot for its plane via is (over the L3 VDD_0V9 neck); on the west
  side the 0.35 mm gaps to C47/C45 and the ring-1 GND column left no via site. Centre and footprint unchanged.
  R50 (OSC_XOUT series resistor, D-110 / verifier L3 r2 minor xtal): moved 0.15 mm west (37.95 -> 37.80), so that
  R50.1 (OSC_XOUT) to Y1.4 (GND) is 0.78 mm copper to copper and the OSC_XIN track (0.15 mm) passes between them at
  the XTAL clearance 0.30 mm (needs 0.75 mm). R50 stays <= 2 mm from U9 pin 69 (check_placement.py).

Round 3 of L5 (D-115, verifier round 2 blocker gpio: the north exit of U9; minor soc: the VDD_ARM test branch). The
north side of U9 has 21 gate lanes but the ring-2 parts north of the ring-1 row left room for 13; these small moves
open two corridors and a free field for them (l5_north.py):
  R66 / R67 (UART2 series resistors, U9 side -> J6): from the strip north of the ring-1 row to Z-UART between J6 and
  their test pads TP9 / TP10 ((32.60, 5.70) and (35.40, 5.70), R67 turned 180 deg so its U9-side pad faces TP10).
  TP31 (GND reference pad of the crystal test pad TP6): from between C69 and TP6 to north-east of TP6 (37.00, 21.15),
  2.7 mm from TP6 (testpoints.md rule 3: <= 3 mm).
  C69 (4.7 uF VCC_1V8 bulk for pin 70, ring 2): from the corridor to (36.70, 18.30) north-east of the field; its
  VCC_1V8 via goes into its pad (L4 to C55's rail via, l4_route.py jobs_power).
  FB3 (VCC_1V8 -> ETH_AVDD1V8 bead): 0.35 mm west, so the corridor between FB3.2 and C43 takes six lanes.
  TP15 (VDD_ARM test pad): from the power test row (67.35, 49.45) to (19.50, 41.50), 3.4 mm from C44.1; its branch
  was a 58 mm load-free 0.30 mm VDD_ARM stub on L4 (verifier round 2 minor soc).
  TP23 (AVDD1V8_USB) and TP18 (VCC3V3_RTC) test pads: from the NE corner of Z-SOC, where the north lane field and
  NPOR's L4 branch left them no path to their rails, to free spots 6.8 / 2.2 mm from their rail copper south of U9
  ((41.30, 51.30) and (46.90, 50.70)).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

ROTATE_180 = ("C36", "C42")
MOVES = {"R50": (-0.15, 0.0), "FB3": (-0.35, 0.0)}        # dx, dy in mm (board coordinates)
PLACE = {"R66": (32.60, 5.70, 0.0), "R67": (35.40, 5.70, 180.0), "TP31": (37.00, 21.15, 0.0),
         "C69": (36.70, 18.30, 0.0), "TP15": (19.50, 41.50, 0.0),
         "TP23": (41.30, 51.30, 0.0), "TP18": (46.90, 50.70, 0.0)}   # D-115: centre (board mm), turn in deg


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    for ref in ROTATE_180:
        fp = board.FindFootprintByReference(ref)
        before = fp.GetOrientationDegrees()
        fp.SetOrientationDegrees((before + 180.0) % 360.0)
        p1 = [p for p in fp.Pads() if p.GetNumber() == "1"][0]
        print("%s rotated %.0f -> %.0f deg, pad 1 (%s) now at (%.2f, %.2f)" % (
            ref, before, fp.GetOrientationDegrees(), p1.GetNetname(), *bl.to_board(p1.GetPosition())))
    for ref, (dx, dy) in MOVES.items():
        fp = board.FindFootprintByReference(ref)
        x, y = bl.to_board(fp.GetPosition())
        fp.SetPosition(bl.to_page(x + dx, y + dy))
        print("%s moved (%.2f, %.2f) -> (%.2f, %.2f)" % (ref, x, y, x + dx, y + dy))
    for ref, (x, y, rot) in PLACE.items():
        fp = board.FindFootprintByReference(ref)
        x0, y0 = bl.to_board(fp.GetPosition())
        if rot:
            fp.SetOrientationDegrees((fp.GetOrientationDegrees() + rot) % 360.0)
        fp.SetPosition(bl.to_page(x, y))
        print("%s moved (%.2f, %.2f) -> (%.2f, %.2f)%s" % (ref, x0, y0, x, y, " turned %.0f deg" % rot if rot else ""))
    pcbnew.SaveBoard(bl.BOARD_FILE, board)


if __name__ == "__main__":
    main()
