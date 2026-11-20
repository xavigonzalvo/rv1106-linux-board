#!/usr/bin/env python3
"""Layout phase L3, step 1: DRU additions for the routing phases (D-109). Appends to design/pcb/rv1106-reva.kicad_dru
(written by build_board.py) once; rerunning is harmless.

  * "pairs in the U9 fan": inside the U9_FAN rule area (square +-7.90 mm, D-107) the ETH/USB pair lines leave 0.35 mm
    pitch pads as 0.15 mm lines (route_escape.py); the class diff_pair_gap / width rules apply from the gate on.
    Kept after the class pair rules (later rules take priority in KiCad).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

RULES = {
    "pairs in the U9 fan": (
        "# Added by design/pcb/scripts/l3_rules.py (D-109 c): pair lines inside the U9 fan band (0.35 mm pin pitch).\n"
        "(rule \"pairs in the U9 fan\"\n"
        "  (condition \"(A.NetClass == 'ETH_DIFF' || A.NetClass == 'USB_DIFF') && A.intersectsArea('U9_FAN')\")\n"
        "  (constraint track_width (min 0.10mm))\n"
        "  (constraint diff_pair_gap (min 0.10mm) (max 0.60mm)))\n"),
}


def main():
    with open(bl.DRU_FILE, encoding="utf-8") as fh:
        dru = fh.read()
    added = []
    for name, text in RULES.items():
        if '(rule "%s"' % name not in dru:
            dru = dru.rstrip("\n") + "\n\n" + text
            added.append(name)
    with open(bl.DRU_FILE, "w", encoding="utf-8") as fh:
        fh.write(dru)
    print("DRU: %d rule(s) added: %s" % (len(added), ", ".join(added) or "none (already there)"))


if __name__ == "__main__":
    main()
