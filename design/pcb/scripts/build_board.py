#!/usr/bin/env python3
"""Layout phase L2, step 1: build design/pcb/rv1106-reva.kicad_pcb from the netlist (no placement yet).

    PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $PY design/pcb/scripts/build_board.py        # then place.py, then check_placement.py

What it does (every number from design/layout.md; decisions D-100..D-102 in design/decisions.md):
  * parses schematic/out/board.net with our own s-expression parser (boardlib.parse_sexpr);
  * loads each footprint (stock KiCad 10.0.7 libraries or design/pcb/board.pretty), sets reference, value and the
    LCSC / MPN / Functional / Block fields; parts with InBOM = no (test pads, JP1, NT1) are excluded from BOM and CPL;
  * creates the 135 nets and assigns every netlist pad (fails if a netlist pad is missing from its footprint);
  * 4 copper layers, stackup JLC04161H-7628 (layout.md §2.1), board thickness 1.6 mm, ENIG;
  * design rules of layout.md §10 "Setup" in the board and in the .kicad_pro, net classes + patterns from the .kicad_pro
    that design/tools/make_kicad_project.py generates from layout/netclasses.csv, .kicad_dru copied (+ D-102 U3/U11 rules, D-104 RTC rule);
  * Edge.Cuts = 90 x 80 mm panel (80 x 80 board + 5 mm rails W/E, layout.md §1), V-cut lines at x = 0 / 80 on User.1
    renamed "V-CUT", placement-zone rectangles on User.2 renamed "PLACE-ZONES" (review aid, never plotted to Gerbers);
  * 4 x M3 NPTH (MountingHole_3.2mm_M3, 7 mm courtyard) + copper keep-out rule areas, 3 global + 2 local fiducials
    (Fiducial_1mm_Mask2mm), 4 x 2.0 mm tooling NPTH (MountingHole_2mm), at the zones.csv coordinates;
  * drill/place (aux) origin and grid origin at the board's NW corner = page (50, 50) mm (D-100).
All footprints are left at the origin; place.py places them.
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

MM = pcbnew.FromMM

# layout.md §10 Setup (min track 0.10, min clearance 0.10 (escape only), via 0.3/0.5, hole-to-hole 0.45,
# copper-to-edge 0.40); annular ring (0.5 - 0.3) / 2 = 0.10
RULES = {
    "min_clearance": 0.10,
    "min_track_width": 0.10,
    "min_via_diameter": 0.50,
    "min_via_annular_width": 0.10,
    "min_through_hole_diameter": 0.30,
    "min_hole_to_hole": 0.45,
    "min_copper_edge_clearance": 0.40,
}

# layout.md §2.1, [JLC-IMP] JLC04161H-7628. Mask: 0.6 mil over traces, Er 3.8.
STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness 0.0152) (material "LPI") (epsilon_r 3.8) (loss_tangent 0))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness 0.0152) (material "LPI") (epsilon_r 3.8) (loss_tangent 0))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
			(copper_finish "ENIG")
			(dielectric_constraints yes)
		)
"""

FIELDS = ("LCSC", "MPN", "Functional", "Block")


def seg(board, layer, x0, y0, x1, y1, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(bl.to_page(x0, y0))
    s.SetEnd(bl.to_page(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(MM(w))
    board.Add(s)
    return s


def arc(board, layer, cx, cy, sx, sy, angle_deg, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetCenter(bl.to_page(cx, cy))
    s.SetStart(bl.to_page(sx, sy))
    s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle_deg, pcbnew.DEGREES_T), True)
    s.SetLayer(layer)
    s.SetWidth(MM(w))
    board.Add(s)


def text(board, layer, s, x, y, size=1.0, thick=0.15):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(bl.to_page(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(thick))
    board.Add(t)


def outline(board, zn):
    """Panel outline: board 80 x 80 + rails = x -5..85, y 0..80, R 1 mm at the four panel corners.
    The board's own corners at the V-cut ends cannot be rounded by a V-cut (D-101)."""
    L = pcbnew.Edge_Cuts
    x0, x1 = zn["RAIL-W"]["x0"], zn["RAIL-E"]["x1"]
    y0, y1 = zn["BOARD"]["y0"], zn["BOARD"]["y1"]
    r = 1.0
    seg(board, L, x0 + r, y0, x1 - r, y0)
    seg(board, L, x1, y0 + r, x1, y1 - r)
    seg(board, L, x1 - r, y1, x0 + r, y1)
    seg(board, L, x0, y1 - r, x0, y0 + r)
    arc(board, L, x1 - r, y0 + r, x1 - r, y0, 90)
    arc(board, L, x1 - r, y1 - r, x1, y1 - r, 90)
    arc(board, L, x0 + r, y1 - r, x0 + r, y1, 90)
    arc(board, L, x0 + r, y0 + r, x0, y0 + r, 90)


def fan_area(board, cx=34.5, cy=36.5, h=7.90, name="U9_FAN"):
    """Rule area (no restrictions) over the U9 fan band, used by the DRU neck-down rule (D-107)."""
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowZoneFills(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)):
        p = bl.to_page(x, y)
        o.Append(p.x, p.y)
    board.Add(z)


def keepout_circle(board, cx, cy, r, name):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowZoneFills(True)
    z.SetDoNotAllowPads(False)          # the hole's own NPTH pad sits inside
    z.SetDoNotAllowFootprints(False)    # parts are kept out by the 7 mm courtyard of MountingHole_3.2mm_M3
    ls = pcbnew.LSET()
    for lyr in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        ls.AddLayer(lyr)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    import math
    for i in range(48):
        a = 2 * math.pi * i / 48
        p = bl.to_page(cx + r * math.cos(a), cy + r * math.sin(a))
        o.Append(p.x, p.y)
    board.Add(z)


def mech(board, ref, fpid, x, y, value):
    fp = bl.load_footprint(fpid)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(bl.to_page(x, y))
    fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
                     | pcbnew.FP_BOARD_ONLY)
    fp.SetLocked(True)
    board.Add(fp)
    return fp


def write_project():
    """.kicad_pro = the generated one (net classes + patterns) + the §10 rules; .kicad_dru copied (+ U11 rule)."""
    with open(os.path.join(bl.SRC_PROJECT_DIR, bl.PROJECT + ".kicad_pro"), encoding="utf-8") as fh:
        pro = json.load(fh)
    pro["meta"]["filename"] = bl.PROJECT + ".kicad_pro"
    ds = pro.setdefault("board", {}).setdefault("design_settings", {})
    ds.setdefault("rules", {}).update(RULES)
    ds["defaults"] = ds.get("defaults", {})
    ds["track_widths"] = [0.0, 0.10, 0.15, 0.20, 0.235, 0.255, 0.30, 0.40, 0.50, 0.80, 1.00, 1.20]
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.5, "drill": 0.3}]
    with open(bl.PRO_FILE, "w", encoding="utf-8") as fh:
        json.dump(pro, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(bl.SRC_PROJECT_DIR, bl.PROJECT + ".kicad_dru"), encoding="utf-8") as fh:
        dru = fh.read()
    if "U3 pads" not in dru:
        # D-102: U3 TSOT-23-8 (LTC2954) has 0.65 mm pitch pads 0.15 mm apart; its SENSE (0.25) and PWR_5V (0.20)
        # class clearances cannot apply pad-to-pad inside the package (JLC SMD pad-to-pad minimum 0.15 mm).
        dru = dru.rstrip("\n") + (
            "\n\n# Added by design/pcb/scripts/build_board.py (D-102): U3 TSOT-23-8 pads (0.15 mm apart by package).\n"
            "(rule \"U3 pads\"\n"
            "  (condition \"A.Type == 'pad' && B.Type == 'pad' && A.memberOfFootprint('U3') && "
            "B.memberOfFootprint('U3')\")\n"
            "  (constraint clearance (min 0.15mm)))\n")
    if "U11 pads" not in dru:
        # D-102 (verifier L1 minor 4): U11 pad 10 (VCC_3V3, PWR_3V3 0.20 mm) is 0.175 mm from pads 1 and 9 by the
        # TI RSE0010A land pattern; same exception as "U9 pads" (JLC SMD pad-to-pad 0.15 mm). Kept last (priority).
        dru = dru.rstrip("\n") + (
            "\n\n# Added by design/pcb/scripts/build_board.py (D-102): U11 UQFN-10 pads, same reason as \"U9 pads\".\n"
            "(rule \"U11 pads\"\n"
            "  (condition \"A.Type == 'pad' && B.Type == 'pad' && A.memberOfFootprint('U11') && "
            "B.memberOfFootprint('U11')\")\n"
            "  (constraint clearance (min 0.15mm)))\n")
    old_clk = "(B.NetClass == 'XTAL' || B.NetClass == 'SW_NODE')"
    if old_clk in dru:
        # D-104 (f): the 32.768 kHz RTC crystal (no battery, D-75) keeps 0.76 mm (the 30 mil "other nets" rule) from the
        # diff pairs instead of the 1.27 mm clock rule: pins 20/21 sit 1.75 mm from the USB pins 26/27 and Y2 has no
        # other place. OSC_XIN/XOUT(_X) and the SW nodes keep 1.27 mm.
        dru = dru.replace(old_clk, "((B.NetClass == 'XTAL' && B.NetName != 'RTC_XIN' && B.NetName != 'RTC_XOUT') || "
                                   "B.NetClass == 'SW_NODE')")
        dru = dru.rstrip("\n") + (
            "\n\n# Added by design/pcb/scripts/build_board.py (D-104 f): RTC crystal nets vs the diff pairs.\n"
            "(rule \"diff pairs keep 30 mil from the RTC crystal\"\n"
            "  (condition \"(A.NetClass == 'ETH_DIFF' || A.NetClass == 'USB_DIFF') && "
            "(B.NetName == 'RTC_XIN' || B.NetName == 'RTC_XOUT')\")\n"
            "  (constraint clearance (min 0.76mm)))\n")
    old_neck = "(condition \"A.Type == 'track' && A.intersectsCourtyard('U9')\")"
    if old_neck in dru:
        # D-107 (verifier L2 r2): the escape plan (D-104) necks down in the whole fan band, r 6.45-7.90 mm from the U9
        # centre (layout.md §4.1 "<= 1.5 mm from U9 pads"); U9's courtyard ends at 6.8 mm. Rule area U9_FAN covers
        # the band (build_board.py adds it).
        dru = dru.replace(old_neck, "(condition \"A.Type == 'track' && (A.intersectsCourtyard('U9') || "
                                    "A.intersectsArea('U9_FAN'))\")")
    with open(bl.DRU_FILE, "w", encoding="utf-8") as fh:
        fh.write(dru)
    shutil.copy(os.path.join(bl.SRC_PROJECT_DIR, "fp-lib-table"), os.path.join(bl.PCB_DIR, "fp-lib-table"))


def add_stackup(path):
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    s = re.sub(r"\n\t\t\(stackup\n.*?\n\t\t\)\n", "\n", s, flags=re.S)   # idempotent
    s = s.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)


def main():
    comps, nets = bl.read_netlist()
    zn = bl.zones()
    assert len(comps) == 226, len(comps)
    assert len(nets) == 135, len(nets)

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ls = board.GetEnabledLayers()
    for lyr in (pcbnew.User_1, pcbnew.User_2):
        ls.AddLayer(lyr)
    board.SetEnabledLayers(ls)
    board.SetLayerName(pcbnew.User_1, "V-CUT")
    board.SetLayerName(pcbnew.User_2, "PLACE-ZONES")

    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    ds.m_MinClearance = MM(RULES["min_clearance"])
    ds.m_TrackMinWidth = MM(RULES["min_track_width"])
    ds.m_ViasMinSize = MM(RULES["min_via_diameter"])
    ds.m_ViasMinAnnularWidth = MM(RULES["min_via_annular_width"])
    ds.m_MinThroughDrill = MM(RULES["min_through_hole_diameter"])
    ds.m_HoleToHoleMin = MM(RULES["min_hole_to_hole"])
    ds.m_CopperEdgeClearance = MM(RULES["min_copper_edge_clearance"])
    ds.SetAuxOrigin(bl.to_page(0, 0))
    ds.SetGridOrigin(bl.to_page(0, 0))

    # nets
    netinfo = {}
    for code, name, _nodes in nets:
        ni = pcbnew.NETINFO_ITEM(board, name, code)
        board.Add(ni)
        netinfo[name] = ni
    pinnet = {}
    for _code, name, nodes in nets:
        for ref, pin in nodes:
            pinnet[(ref, pin)] = name

    # footprints
    missing = []
    for ref, c in comps.items():
        fp = bl.load_footprint(c["footprint"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        for f in FIELDS:
            if c["fields"].get(f):
                fp.SetField(f, c["fields"][f])
        for fld in fp.GetFields():
            if fld.GetName() in FIELDS:
                fld.SetVisible(False)
        if c["fields"].get("InBOM", "yes") == "no":
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        fp.SetPosition(bl.to_page(0, 0))
        names = {}
        for pad in fp.Pads():
            names.setdefault(pad.GetNumber(), []).append(pad)
        for (r, pin), net in pinnet.items():
            if r != ref:
                continue
            if pin not in names:
                missing.append("%s.%s" % (ref, pin))
                continue
            for pad in names[pin]:
                pad.SetNet(netinfo[net])
        board.Add(fp)
    if missing:
        sys.exit("netlist pads missing from footprints: " + " ".join(missing))

    # outline, rails, V-cut, zones
    outline(board, zn)
    vc = pcbnew.User_1
    for x in (0.0, 80.0):
        seg(board, vc, x, 0.0, x, 80.0, 0.15)
    text(board, vc, "V-CUT", -2.5, 40.0, 1.0)
    text(board, vc, "V-CUT", 82.5, 40.0, 1.0)
    pz = pcbnew.User_2
    for name, z in zn.items():
        if z["kind"] in ("zone", "connector", "rail"):
            x0, y0, x1, y1 = z["x0"], z["y0"], z["x1"], z["y1"]
            for a, b, c2, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
                seg(board, pz, a, b, c2, d, 0.1)
            if z["kind"] == "zone":
                text(board, pz, name, x0 + 0.3 + 0.35 * len(name), y0 + 0.8, 0.7, 0.1)

    fan_area(board)            # D-107: U9 fan band for the DRU neck-down rule

    # mechanical parts (zones.csv rows H*, FID*, GFID*, TH*)
    for name, z in zn.items():
        k = z["kind"]
        if k == "hole":
            mech(board, name, "MountingHole:MountingHole_3.2mm_M3", z["origin_x"], z["origin_y"], "M3 NPTH")
            keepout_circle(board, z["origin_x"], z["origin_y"], 3.5, "KEEPOUT_" + name)
        elif k in ("fiducial", "rail-fiducial"):
            fp = mech(board, name, "Fiducial:Fiducial_1mm_Mask2mm", z["origin_x"], z["origin_y"], "Fiducial")
            if k == "rail-fiducial":
                # D-102: on the rail the fiducial's 1.3 mm courtyard reaches 0.15 mm into the M3 keep-out courtyard
                # (H1-H3, layout.md §1 positions). The rail is removed after assembly; drop the courtyard and mark
                # the footprint so DRC does not ask for one.
                for g in list(fp.GraphicalItems()):
                    if g.GetLayer() == pcbnew.F_CrtYd:
                        fp.Remove(g)
                fp.SetAllowMissingCourtyard(True)
        elif k == "rail-hole":
            mech(board, name, "MountingHole:MountingHole_2mm", z["origin_x"], z["origin_y"], "Tooling 2.0 NPTH")

    text(board, pcbnew.Cmts_User, "RV1106 Linux board Rev A - board origin (0,0) = NW corner = page (50,50) mm",
         40.0, -3.0, 1.0)

    os.makedirs(bl.PCB_DIR, exist_ok=True)
    write_project()
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    add_stackup(bl.BOARD_FILE)

    # reload: proves the file (with the stackup) parses, and report
    b2 = pcbnew.LoadBoard(bl.BOARD_FILE)
    nfp = len(list(b2.GetFootprints()))
    nnet = b2.GetNetCount() - 1   # minus the unconnected net 0
    print("board: %s" % bl.BOARD_FILE)
    print("footprints %d (226 netlist + %d mechanical), nets %d, copper layers %d, thickness %.3f mm"
          % (nfp, nfp - 226, nnet, b2.GetCopperLayerCount(), pcbnew.ToMM(b2.GetDesignSettings().GetBoardThickness())))


if __name__ == "__main__":
    main()
