"""Layout phase L5 round 2: DRU addition (D-114 h). Appends to design/pcb/rv1106-reva.kicad_dru once (after
l4_rules.py); rerunning is harmless. Plain Python.

  * J5 GND pins (2x20 header) and the J1 (USB-C) shell pins, all plated through: the L1 GND pour round such a pin
    can be cut by the lanes / the USB-C breakout next to it, leaving one thermal spoke (KiCad DRC 'starved_thermal', default minimum 2 spokes). The
    pins are tied to the solid L2 GND plane (and the L4 pour) in every case, so one L1 spoke is
    enough: minimum resolved spokes 1 for the J5 GND pins only. check_routing.py still lists the spoke situation
    through KiCad's DRC report (no error any more, the rule is named in the DRC item).

    python3 design/pcb/scripts/l5_rules.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

HEAD = "# Added by design/pcb/scripts/l5_rules.py (D-114 h): recorded L5 deviation, see decisions.md.\n"
RULES = {
    "J5 / J1 GND pins: one L1 spoke (D-114 h)": (
        "(rule \"J5 / J1 GND pins: one L1 spoke (D-114 h)\"\n"
        "  (condition \"A.Type == 'pad' && (A.memberOfFootprint('J5') || A.memberOfFootprint('J1')) && "
        "A.NetName == 'GND'\")\n"
        "  (constraint min_resolved_spokes 1))\n"),
    # round 3 (D-115): the north lane bus legs run on L4 past the RJ45's GND pin 8 and shield pins; the L4 pour round
    # them keeps one spoke (the pins are tied to the solid L2 GND plane and the L1 pour)
    "J3 GND pins: one spoke (D-115)": (
        "(rule \"J3 GND pins: one spoke (D-115)\"\n"
        "  (condition \"A.Type == 'pad' && A.memberOfFootprint('J3') && A.NetName == 'GND'\")\n"
        "  (constraint min_resolved_spokes 1))\n"),
}


def main():
    with open(bl.DRU_FILE, encoding="utf-8") as fh:
        dru = fh.read()
    added = []
    for name, text in RULES.items():
        if '(rule "%s"' % name not in dru:
            dru = dru.rstrip("\n") + "\n\n" + (HEAD if not added else "") + text
            added.append(name)
    with open(bl.DRU_FILE, "w", encoding="utf-8") as fh:
        fh.write(dru)
    print("DRU: %d rule(s) added: %s" % (len(added), ", ".join(added) or "none (already there)"))


if __name__ == "__main__":
    main()
