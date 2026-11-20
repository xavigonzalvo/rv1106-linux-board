#!/usr/bin/env python3
"""Layout phase L4: DRU additions for the critical routing (D-111). Appends to design/pcb/rv1106-reva.kicad_dru once
(after l3_rules.py); rerunning is harmless. Every rule here encodes a deviation the owner approved at CHECKPOINT 1
(D-H5) or one recorded in D-111 for the owner's review at CHECKPOINT 2; the checker (l4check.py) still measures and
reports the layout.md §4 target next to each as DEV, so nothing is hidden by the relaxed DRC limit.

  * ETH TX hop: 2 vias per TX line (D-106 b; layout.md §4.2 says 0; class rule "ETH 100 ohm pair" has via_count 0).
  * ETH uncoupled length: the 0R-link P/N swaps, the TX hop and the skew meanders (D-108 b) exceed the 5 mm of
    layout.md §4.2; D-108 b recorded 11.3 / 6.7 mm in the trial; limit set to the as-routed figure + margin.
  * Crystal / RTC lengths: the per-net totals include the R51 / C77 / TP6 branches and the fan; the placement lower
    bounds of D-104 d / D-105 already exceed 5 / 6 mm. Limits = as-routed + margin, the §4.3 figure stays the target.
Later rules take priority in KiCad, so these stay at the end of the file.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

HEAD = "# Added by design/pcb/scripts/l4_rules.py (D-111): owner-approved / recorded L4 deviations, see decisions.md.\n"
RULES = {
    "ETH TX hop vias": (
        "(rule \"ETH TX hop vias\"\n"
        "  (condition \"A.NetName == 'ETH_TXP' || A.NetName == 'ETH_TXN'\")\n"
        "  (constraint via_count (max 2)))\n"),
    "ETH uncoupled (D-108 b)": (
        "(rule \"ETH uncoupled (D-108 b)\"\n"
        "  (condition \"A.NetClass == 'ETH_DIFF'\")\n"
        "  (constraint diff_pair_uncoupled (max 14mm)))\n"),
    "FSPI_D3 length as routed (D-111 c)": (
        "(rule \"FSPI_D3 length as routed (D-111 c)\"\n"
        "  (condition \"A.NetName == 'FSPI_D3'\")\n"
        "  (constraint length (max 27mm)))\n"),
    "ETH split field (D-108 b, D-111 a)": (
        "(rule \"ETH split field (D-108 b, D-111 a)\"\n"
        "  (condition \"A.NetClass == 'ETH_DIFF' && A.intersectsArea('ETH_FIELD')\")\n"
        "  (constraint diff_pair_gap (min 0.10mm) (max 5mm)))\n"),
    "USB pairs keep 30 mil from pads and vias (D-112 b)": (
        "(rule \"USB pairs keep 30 mil from pads and vias (D-112 b)\"\n"
        "  (condition \"A.NetClass == 'USB_DIFF' && A.Type == 'track' && (B.Type == 'pad' || B.Type == 'via') && "
        "B.NetClass != 'USB_DIFF' && B.NetName != 'GND' && !A.intersectsArea('U9_RING') && "
        "!A.intersectsCourtyard('U9') && !A.intersectsCourtyard('J1') && !A.intersectsCourtyard('U1') && "
        "!A.intersectsCourtyard('U2') && !A.intersectsCourtyard('U11') && "
        "!B.intersectsCourtyard('U9') && !B.intersectsCourtyard('J1') && !B.intersectsCourtyard('U1') && "
        "!B.intersectsCourtyard('U2') && !B.intersectsCourtyard('U11')\")\n"
        "  (constraint clearance (min 0.76mm)))\n"),
    "USB 45 ohm lines at the breakout parts (D-112 c)": (
        "(rule \"USB 45 ohm lines at the breakout parts (D-112 c)\"\n"
        "  (condition \"A.NetClass == 'USB_DIFF' && (A.intersectsArea('USB_Z45_A') || A.intersectsArea('USB_Z45_C'))\")\n"
        "  (constraint track_width (min 0.245mm) (max 0.43mm)))\n"),
    "Y1 XIN length as routed (D-111 b)": (
        "(rule \"Y1 XIN length as routed (D-111 b)\"\n"
        "  (condition \"A.NetName == 'OSC_XIN'\")\n"
        "  (constraint length (max 12mm)))\n"),
    "Y1 XOUT length as routed (D-111 b)": (
        "(rule \"Y1 XOUT length as routed (D-111 b)\"\n"
        "  (condition \"A.NetName == 'OSC_XOUT'\")\n"
        "  (constraint length (max 10mm)))\n"),
    "Y2 RTC length as routed (D-105, D-111 b)": (
        "(rule \"Y2 RTC length as routed (D-105, D-111 b)\"\n"
        "  (condition \"A.NetName == 'RTC_XIN' || A.NetName == 'RTC_XOUT'\")\n"
        "  (constraint length (max 13mm)))\n"),
}


ETH_FIELD = (10.0, 15.0, 26.5, 34.0)   # rule area: the ETH split/hop/meander field west of the U9 fan (D-111 a)
U9_RING = (24.2, 26.2, 44.8, 46.8)     # rule area: U9 ring-1 band, lane exits between the ring-1 caps (D-112 b)
# rule areas where the USB lines run apart at 0.42 mm (Z0 45 ohm, D-112 c): U2 + J4 pins, U1 pins
USB_Z45 = {"USB_Z45_A": (34.5, 59.4, 37.9, 67.9), "USB_Z45_C": (48.0, 65.3, 51.0, 70.3)}


def add_field(name="ETH_FIELD", rect=ETH_FIELD):
    """rule area `name` (no restrictions) on L1 and L4, used by the DRU rules that name it"""
    import pcbnew
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    if any(z.GetIsRuleArea() and z.GetZoneName() == name for z in board.Zones()):
        return False
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    for f in (z.SetDoNotAllowTracks, z.SetDoNotAllowVias, z.SetDoNotAllowZoneFills, z.SetDoNotAllowPads,
              z.SetDoNotAllowFootprints):
        f(False)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    x0, y0, x1, y1 = rect
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        p = bl.to_page(x, y)
        o.Append(p.x, p.y)
    board.Add(z)
    board.Save(bl.BOARD_FILE)
    return True


def main():
    with open(bl.DRU_FILE, encoding="utf-8") as fh:
        dru = fh.read()
    # the ETH class rule allows no via; the TX hop (D-106 b, owner-approved D-H5) needs 2 per TX line. KiCad takes the
    # class rule's via_count for both TX nets, so the class rule itself is edited (RX: 0 vias, checked by l4check.py)
    old = "  (constraint skew (max 1.27mm) (within_diff_pairs))\n  (constraint via_count (max 0)))"
    if old in dru:
        dru = dru.replace(old, "  (constraint skew (max 1.27mm) (within_diff_pairs))\n"
                               "  # via_count 0 -> 2 by l4_rules.py (D-111): TX hop; RX keeps 0 (check_routing.py)\n"
                               "  (constraint via_count (max 2)))")
    added = []
    for name, text in RULES.items():
        if '(rule "%s"' % name not in dru:
            dru = dru.rstrip("\n") + "\n\n" + (HEAD if not added else "") + text
            added.append(name)
    with open(bl.DRU_FILE, "w", encoding="utf-8") as fh:
        fh.write(dru)
    print("DRU: %d rule(s) added: %s" % (len(added), ", ".join(added) or "none (already there)"))
    if os.environ.get("L4_NO_BOARD") != "1":
        print("rule area ETH_FIELD: %s" % ("added" if add_field() else "already there"))
        print("rule area U9_RING: %s" % ("added" if add_field("U9_RING", U9_RING) else "already there"))
        for name, rect in USB_Z45.items():
            print("rule area %s: %s" % (name, "added" if add_field(name, rect) else "already there"))


if __name__ == "__main__":
    main()
