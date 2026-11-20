#!/usr/bin/env python3
"""Layout phase L6 (fabrication outputs, gate TP-L6; decisions.md D-132): every file JLCPCB needs, regenerated from the
finished board by this one script. Nothing in design/pcb/fab/ is edited by hand.

    $PY design/pcb/scripts/l6_fab.py        # after rebuild_all.sh's L5G step (scripts/l6_run.sh); ~1 min

Board change (the only one in L6, re-runnable, idempotent):
  * aux (drill / place) origin moved to the panel lower-left corner, board (-5, 80) mm = page (45, 130) mm, so the
    Gerbers, the Excellon files and the CPL share one origin with all coordinates positive, y up;
  * the two "V-CUT" review texts move from the V-CUT user layer (User.1) to User.Drawings, so that the V-CUT Gerber
    holds only the two cut lines (x = 0 / 80 board mm).
Outputs (design/pcb/fab/):
  gerbers/        RS-274X X2 Gerbers (Protel extensions) F/In1/In2/B.Cu, F/B.Mask, F/B.Paste, F/B.Silkscreen,
                  Edge.Cuts, V-CUT; job file; Excellon PTH + NPTH (mm, X2 attributes); drill maps (PDF); drill report
  rv1106-reva-jlc-upload.zip   the Gerbers + drill + job file (the one file to upload)
  jlc-bom.csv, jlc-bom-not-assembled.csv, jlc-cpl.csv
  assembly-top-refs.pdf, assembly-top-values.pdf, fab-drawing.pdf (made from a throw-away annotated copy of the board)
  render-3d-top.png, render-3d-bottom.png, rv1106-reva.d356 (IPC-D-356 netlist)
  cpl-rotations.md, order-notes.md
The self-check is scripts/check_fab.py (design/.venv Python; writes fab/check_fab.txt and fab/gerber-view/*.png).
"""
import csv
import io
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import pcbnew  # noqa: E402

FAB = os.path.join(bl.PCB_DIR, "fab")
GERB = os.path.join(FAB, "gerbers")
WORK = os.path.join(FAB, "_work")
BOM_CSV = os.path.join(bl.DESIGN, "bom.csv")
VIP_CSV = os.path.join(bl.PCB_DIR, "via_in_pad.csv")
ZIP_NAME = "rv1106-reva-jlc-upload.zip"

PANEL_LL = (-5.0, 80.0)          # board mm: panel lower-left corner (west rail edge, south edge)
GERBER_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste",
                 "F.Silkscreen", "B.Silkscreen", "Edge.Cuts", "User.1"]
THT_ASSEMBLED = ("J3", "J4", "J5", "J6")   # JLC THT service (cost.md: 134 manual joints = 2 x 67)

# ---------------------------------------------------------------------------------------------------------------
# CPL rotation corrections per footprint family (JLC rotation = KiCad rotation + correction, mod 360).
# KiCad's 0 deg is the IPC-7351B zero orientation of the stock footprint files (pin 1 top-left for ICs, pad 1 on the
# left for two-terminal parts). JLC's 0 deg is the 0 deg of the part's model in JLC's own (EasyEDA) library, which
# for some families is turned. The values below are the widely used KiCad -> JLC correction values (SOT-23 family
# +180, QFN / SON family +270, aluminium / polymer CP_Elec +180, the rest 0), recalled, not fetched: UNVERIFIED.
# JLC's preview could not be used here (no upload, H2), so every orientation-sensitive part is listed in
# cpl-rotations.md with where its pin 1 / cathode / + must end up on the board, for the owner to confirm.
# (family, footprint-name regex, correction, polarity class, reason, source)
FAMILIES = [
    ("chip resistor", r"^R_0(402|603|805)_", 0, "none",
     "two identical terminals, pad 1 west at 0 deg in KiCad and JLC: no correction", "KiCad Resistor_SMD footprint files"),
    ("chip capacitor (MLCC)", r"^C_0(402|603|805)_", 0, "none",
     "non-polar MLCC, pads along x at 0 deg in both: no correction", "KiCad Capacitor_SMD footprint files"),
    ("ferrite bead 0603", r"^L_0603_", 0, "none", "non-polar, pads along x: no correction", "KiCad Inductor_SMD"),
    ("PTC fuse 1812", r"^Fuse_1812_", 0, "none", "non-polar, pads along x: no correction", "KiCad Fuse library"),
    ("power inductor FHD4020S", r"^L_FHD4020S_", 0, "none", "non-polar 2-pad: no correction",
     "board.pretty (D-74), refs/fhd4020s-datasheet"),
    ("crystal 3215 2-pad", r"^Crystal_SMD_3215-2Pin", 0, "none", "non-polar 2-pad: no correction",
     "KiCad Crystal library"),
    ("crystal 3225 4-pad", r"^Crystal_SMD_3225-4Pin", 0, "rot90",
     "pads 1/3 = crystal, 2/4 = case/GND: a 180 deg turn is electrically the same, a 90 deg turn is wrong; pin 1 "
     "bottom-left at 0 deg in KiCad: no correction", "KiCad Crystal library; refs/taxm24m-crystal-datasheet p.1"),
    ("tact switch TS-1187A", r"^SW_TS-1187A_", 0, "rot90",
     "4 pads in two internally joined pairs: 180 deg is the same, 90 deg would short the switch: no correction",
     "board.pretty (D-74), refs/ts-1187a-datasheet"),
    ("LED 0603", r"^LED_0603_", 0, "polar",
     "pad 1 = cathode, west at 0 deg in KiCad; JLC's 0603 LED model also has the cathode west at 0 deg: no "
     "correction (UNVERIFIED)", "KiCad LED_SMD footprint (pad 1 = K); no LED datasheet saved"),
    ("diode SOD-123", r"^D_SOD-123", 0, "polar",
     "pad 1 = cathode (band), west at 0 deg: no correction (UNVERIFIED)", "KiCad Diode_SMD footprint (pad 1 = K)"),
    ("diode SMA", r"^D_SMA", 0, "polar",
     "pad 1 = cathode (band), west at 0 deg: no correction (UNVERIFIED)", "KiCad Diode_SMD footprint (pad 1 = K)"),
    ("polymer capacitor CP_Elec 6.3", r"^CP_Elec_", 180, "polar",
     "pad 1 = + , west at 0 deg in KiCad; JLC's SMD electrolytic models are drawn with + east at 0 deg, hence +180 "
     "(UNVERIFIED)", "KiCad Capacitor_SMD CP_Elec_6.3x5.9; refs/lelon-ovz121m1atr-datasheet p.1 (polarity mark)"),
    ("SOT-23 (3 pins)", r"^SOT-23$", 180, "polar",
     "KiCad 0 deg: pins 1, 2 on the west side (pin 1 north-west), pin 3 east; JLC's SOT-23 models have pin 3 west "
     "at 0 deg, hence +180 (UNVERIFIED)",
     "KiCad Package_TO_SOT_SMD SOT-23; refs/ao3401a-datasheet p.1, ao3400a p.1, 2n7002 p.1, si2301cds p.1"),
    ("SOT-23-5", r"^SOT-23-5$", 180, "polar",
     "KiCad 0 deg: pins 1-3 west (pin 1 north-west), 4-5 east; JLC SOT-23-5 models are turned 180 deg (UNVERIFIED)",
     "KiCad SOT-23-5; refs/tlv62569-datasheet p.3, refs/sy6280aac-datasheet p.2"),
    ("SOT-23-6", r"^SOT-23-6$", 180, "polar",
     "KiCad 0 deg: pins 1-3 west (pin 1 north-west), 4-6 east; JLC SOT-23-6 models are turned 180 deg (UNVERIFIED)",
     "KiCad SOT-23-6; refs/usblc6-2sc6-datasheet p.1"),
    ("TSOT-23-8", r"^TSOT-23-8", 180, "polar",
     "same outline family as SOT-23-6 (pins 1-4 west, pin 1 north-west at 0 deg); the SOT-23 family correction is "
     "applied (UNVERIFIED: no JLC value for TSOT-23-8 known)", "KiCad TSOT-23-8; refs/ltc2954-datasheet p.2"),
    ("WSON-8 8x6", r"^WSON-8-", 270, "polar",
     "KiCad 0 deg: pin 1 north-west, pins 1-4 down the west side; JLC SON / QFN models have pin 1 south-west with "
     "pins along the south side at 0 deg, hence +270 (UNVERIFIED)",
     "KiCad Package_SON WSON-8-1EP_8x6mm; refs/w25n01kv-datasheet p.7"),
    ("UQFN-10 (TI RSE)", r"^TI_RSE0010A_UQFN-10", 270, "polar",
     "QFN family rule as WSON (+270); pin 1 at the footprint's north-west at 0 deg (UNVERIFIED)",
     "board.pretty (D-74); refs/ts3usb221a-datasheet p.3"),
    ("QFN-128 RV1106 (U9)", r"^RV1106_QFN-128-1EP", 270, "polar",
     "QFN family rule (+270); KiCad 0 deg pin 1 north-west (pin 1 at the SW corner on this board, rotation 90) "
     "(UNVERIFIED)", "board.pretty (D-74, D-129); refs/rv1106-datasheet-r1.8 p.17 Fig. 2-5"),
    ("USB-C receptacle HRO TYPE-C-31-M-12", r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", 0, "polar",
     "opening toward +y (south) at 0 deg in KiCad; SMD contacts + 4 THT shell pegs: only one way fits; no "
     "correction (UNVERIFIED)", "KiCad Connector_USB; refs/type-c-31-m-12-datasheet"),
    ("microSD TF-01A", r"^microSD_TF-01A", 0, "polar",
     "card slot toward +y (south) at 0 deg; asymmetric pads: no correction (UNVERIFIED)",
     "board.pretty (D-74); refs/tf-01a-datasheet"),
    ("RJ45 HR911105A (THT)", r"^RJ45_Hanrun_HR911105A", 0, "polar",
     "through-hole, asymmetric pins + 2 pegs: only one way fits the holes; placed by hand by JLC: no correction",
     "KiCad Connector_RJ; refs/hr911105a-datasheet"),
    ("USB-A AF90 (THT)", r"^USB_A_AF90_WJDG", 0, "polar",
     "through-hole, 4 pins + 2 shell legs: only one way fits; placed by hand by JLC: no correction",
     "board.pretty (D-74); refs/usb-a-af90-wjdg-datasheet"),
    ("pin header 2x20 (THT)", r"^PinHeader_2x20_", 0, "polar",
     "unshrouded header: fits the holes at 0 or 180 deg and is the same part either way; placed by hand: no "
     "correction", "KiCad Connector_PinHeader_2.54mm; refs/header-2x20-datasheet"),
    ("pin header 1x3 (THT)", r"^PinHeader_1x03_", 0, "polar",
     "unshrouded header, symmetric part; placed by hand: no correction",
     "KiCad Connector_PinHeader_2.54mm; refs/header-1x3-datasheet"),
]

PIN1_NAME = {"J1": "A1"}   # pad that carries the "pin 1" mark when it is not called "1"
POLARITY_WORD = {"LED 0603": "cathode", "diode SOD-123": "cathode (band)", "diode SMA": "cathode (band)",
                 "polymer capacitor CP_Elec 6.3": "+ (anode)"}


def family_of(fpname):
    for fam in FAMILIES:
        if re.search(fam[1], fpname):
            return fam
    raise SystemExit("L6: no CPL family for footprint %s" % fpname)


def mm(v):
    return v / 1e6


def to_fab(x_page, y_page, aux):
    """page mm -> fab (Gerber / drill / CPL) mm: origin = aux origin, y up."""
    return (x_page - aux[0], aux[1] - y_page)


def compass(dx, dy):
    """dx east, dy north (mm) -> 8-point compass word."""
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return "centre"
    a = math.degrees(math.atan2(dy, dx)) % 360
    names = ["east", "north-east", "north", "north-west", "west", "south-west", "south", "south-east"]
    return names[int(((a + 22.5) % 360) // 45)]


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = "\n".join(line for line in r.stdout.splitlines() if "create wxApp" not in line)
    if r.returncode != 0:
        print(out)
        raise SystemExit("L6: command failed: %s" % " ".join(cmd))
    return out


# ---------------------------------------------------------------------------------------------------------------
# 1. board change: aux origin + V-CUT layer holds only the cut lines
# ---------------------------------------------------------------------------------------------------------------
def edit_board():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    ds = board.GetDesignSettings()
    ds.SetAuxOrigin(bl.to_page(*PANEL_LL))
    moved = 0
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.User_1 and d.GetClass() == "PCB_TEXT":
            d.SetLayer(pcbnew.Dwgs_User)
            moved += 1
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    print("L6 board: aux origin -> board (%.1f, %.1f) mm; V-CUT texts moved to User.Drawings: %d" % (PANEL_LL + (moved,)))
    return pcbnew.LoadBoard(bl.BOARD_FILE)


# ---------------------------------------------------------------------------------------------------------------
# 2. part data from the board + bom.csv
# ---------------------------------------------------------------------------------------------------------------
def pad_centre(fp):
    pads = list(fp.Pads())
    xs = [mm(p.GetPosition().x) for p in pads]
    ys = [mm(p.GetPosition().y) for p in pads]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def read_bom():
    rows = list(csv.DictReader(open(BOM_CSV, newline="")))
    return rows


def parts(board, aux):
    bom = read_bom()
    bomref = {}
    for r in bom:
        for ref in r["ref"].split():
            bomref[ref] = r
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    missing = sorted(set(bomref) - set(fps))
    if missing:
        raise SystemExit("L6: bom.csv refs not on the board: %s" % missing)
    out = {}
    for ref, fp in fps.items():
        fpname = fp.GetFPID().GetLibItemName().wx_str() if hasattr(fp.GetFPID().GetLibItemName(), "wx_str") \
            else str(fp.GetFPID().GetLibItemName())
        cx, cy = pad_centre(fp)
        fx, fy = to_fab(cx, cy, aux)
        rot = round(fp.GetOrientationDegrees(), 3) % 360
        assembled = ref in bomref
        d = dict(ref=ref, fp=fp, fpname=fpname, fpid=fp.GetFPIDAsString(), value=fp.GetValue(), cx=cx, cy=cy,
                 fx=fx, fy=fy, rot=rot, assembled=assembled, bom=bomref.get(ref),
                 tht=bool(fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE),
                 anchor=to_fab(mm(fp.GetPosition().x), mm(fp.GetPosition().y), aux))
        if assembled:
            fam = family_of(fpname)
            d["family"] = fam
            d["jlc_rot"] = (rot + fam[2]) % 360
            if fp.IsExcludedFromPosFiles() or fp.IsExcludedFromBOM() or fp.IsDNP():
                raise SystemExit("L6: %s is in bom.csv but flagged DNP / excluded on the board" % ref)
            # pin-1 / polarity pad
            p1name = PIN1_NAME.get(ref, "1")
            p1 = [p for p in fp.Pads() if p.GetNumber() == p1name]
            if p1:
                px, py = mm(p1[0].GetPosition().x), mm(p1[0].GetPosition().y)
                d["pin1"] = (p1name, px, py, compass(px - cx, -(py - cy)))
                rels = [q.GetFPRelativePosition() for q in fp.Pads()]
                c0x = (min(mm(q.x) for q in rels) + max(mm(q.x) for q in rels)) / 2.0
                c0y = (min(mm(q.y) for q in rels) + max(mm(q.y) for q in rels)) / 2.0
                rel = p1[0].GetFPRelativePosition()
                d["pin1_at0"] = compass(mm(rel.x) - c0x, -(mm(rel.y) - c0y))   # footprint frame, 0 deg
        out[ref] = d
    return bom, out


def ref_key(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def fmt_rot(r):
    r = r % 360
    return ("%d" % r) if abs(r - round(r)) < 1e-6 else ("%.2f" % r)


def write_bom_cpl(bom, P):
    asm = sorted([d for d in P.values() if d["assembled"]], key=lambda d: ref_key(d["ref"]))
    # JLC BOM: one row per unique part (bom.csv is already one row per part number)
    with open(os.path.join(FAB, "jlc-bom.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for r in bom:
            refs = sorted(r["ref"].split(), key=ref_key)
            fpn = P[refs[0]]["fpname"]
            w.writerow([r["value"], ",".join(refs), fpn, r["lcsc"]])
    # not assembled (on the board, no part): test pads, fiducials, holes, solder jumper, net tie
    with open(os.path.join(FAB, "jlc-bom-not-assembled.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Designator", "Value", "Footprint", "Reason"])
        for d in sorted([d for d in P.values() if not d["assembled"]], key=lambda d: ref_key(d["ref"])):
            fpn = d["fpname"]
            reason = ("bare test pad (Phase 6), no part" if fpn.startswith("TestPoint") else
                      "fiducial (copper + mask opening only)" if fpn.startswith("Fiducial") else
                      "NPTH hole (mounting / tooling), no part" if fpn.startswith("MountingHole") else
                      "solder jumper, PCB copper only, normally closed (D-68)" if fpn.startswith("SolderJumper") else
                      "net tie, PCB copper only (D-68)" if fpn.startswith("NetTie") else "no part")
            w.writerow([d["ref"], d["value"], fpn, reason])
    # JLC CPL
    with open(os.path.join(FAB, "jlc-cpl.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for d in asm:
            w.writerow([d["ref"], "%.4f" % d["fx"], "%.4f" % d["fy"], "Top", fmt_rot(d["jlc_rot"])])
    print("L6 BOM: %d rows, %d assembled refs; not assembled: %d; CPL: %d rows (THT placed by JLC: %s)" % (
        len(bom), len(asm), sum(1 for d in P.values() if not d["assembled"]), len(asm),
        ", ".join(r for r in THT_ASSEMBLED)))
    return asm


# ---------------------------------------------------------------------------------------------------------------
# 3. kicad-cli outputs
# ---------------------------------------------------------------------------------------------------------------
def export_gerbers_drill():
    run([bl.KICAD_CLI, "pcb", "export", "gerbers", "-o", GERB + "/", "--layers", ",".join(GERBER_LAYERS),
         "--use-drill-file-origin", "--subtract-soldermask", bl.BOARD_FILE])
    run([bl.KICAD_CLI, "pcb", "export", "drill", "-o", GERB + "/", "--format", "excellon", "--drill-origin", "plot",
         "--excellon-units", "mm", "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate",
         "--excellon-separate-th", "--generate-map", "--map-format", "pdf", "--generate-report",
         "--report-path", os.path.join(GERB, "rv1106-reva-drill-report.txt"), bl.BOARD_FILE])
    files = sorted(os.listdir(GERB))
    print("L6 Gerber + drill files: %d (%s)" % (len(files), ", ".join(files)))
    return files


def make_zip(files):
    upload = [f for f in files if re.search(r"\.(gtl|g1|g2|gbl|gts|gbs|gtp|gbp|gto|gbo|gm1|gbr|gbrjob|drl)$", f)]
    path = os.path.join(FAB, ZIP_NAME)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in upload:
            zi = zipfile.ZipInfo(f, date_time=(2026, 11, 7, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, open(os.path.join(GERB, f), "rb").read())
    print("L6 upload zip: %s (%d files)" % (ZIP_NAME, len(upload)))
    return upload


def annotated_copy(P, aux, name, mode):
    """Throw-away copy of the board with drawing notes (never saved over the design board)."""
    board = pcbnew.LoadBoard(bl.BOARD_FILE)

    def text(layer, s, x, y, h=1.0, just_left=True):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(h), pcbnew.FromMM(h)))
        t.SetTextThickness(pcbnew.FromMM(h * 0.13))
        if just_left:
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        t.SetPosition(bl.to_page(x, y))
        board.Add(t)

    def seg(layer, x1, y1, x2, y2, w=0.1):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(layer)
        s.SetWidth(pcbnew.FromMM(w))
        s.SetStart(bl.to_page(x1, y1))
        s.SetEnd(bl.to_page(x2, y2))
        board.Add(s)

    def circle(layer, x, y, r, w=0.1, filled=False):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetLayer(layer)
        s.SetWidth(pcbnew.FromMM(w))
        s.SetStart(bl.to_page(x, y))
        s.SetEnd(bl.to_page(x + r, y))
        if filled:
            s.SetFilled(True)
        board.Add(s)

    def fab_xy(x_board, y_board):
        return to_fab(x_board + bl.ORIGIN[0], y_board + bl.ORIGIN[1], aux)

    L = pcbnew.Dwgs_User if mode == "fab" else pcbnew.Cmts_User
    if mode == "fab":
        text(L, "V-CUT  x = 0 (board) / %.2f (Gerber)" % fab_xy(0, 0)[0], 0.3, -1.6, 0.8)
        text(L, "V-CUT  x = 80 (board) / %.2f (Gerber)" % fab_xy(80, 0)[0], 58.0, -1.6, 0.8)
        for x in (0.0, 80.0):
            for y0 in range(0, 80, 4):
                seg(L, x, y0, x, y0 + 2.0, 0.3)
        text(L, "ORIGIN (0, 0) of Gerbers, drill and CPL = panel lower-left", -5.0, 86.0, 0.9)
        seg(L, -6.0, 80.0, -4.0, 80.0, 0.1)
        seg(L, -5.0, 79.0, -5.0, 81.0, 0.1)
        notes = ["PANEL 90 x 80 mm = board 80 x 80 mm + 2 x 5 mm rails (west / east), delivered as one piece "
                 "('panel by customer')",
                 "V-cut: two straight full-height lines at board x = 0 and x = 80, zero gap, layer V-CUT "
                 "(file rv1106-reva-V-CUT.gbr)",
                 "Board corners R 1 mm, made by 1.5 x 1.5 mm routed notches with R 0.5 mm inner corners (router "
                 "bit <= 1.0 mm)",
                 "4 layers JLC04161H-7628, 1.6 mm, ENIG, green / white, 1 oz outer / 0.5 oz inner; all vias "
                 "epoxy filled + capped (POFV)"]
        y = 88.0
        for s in notes:
            text(L, s, -5.0, y, 0.8)
            y += 1.6
        for d in P.values():
            if d["fpname"].startswith("Fiducial") or d["ref"].startswith("TH"):
                bx, by = d["cx"] - bl.ORIGIN[0], d["cy"] - bl.ORIGIN[1]
                fx, fy = d["fx"], d["fy"]
                circle(L, bx, by, 1.5, 0.1)
                text(L, "%s (%.2f, %.2f)" % (d["ref"], fx, fy), bx + 2.2 if bx < 40 else bx - 12.5,
                     by + (2.4 if by < 40 else -2.4), 0.7)
    else:
        # assembly: pin-1 / polarity dot (User.Comments) on every orientation-sensitive assembled part
        for d in P.values():
            if not d["assembled"] or "pin1" not in d or d["family"][3] == "none":
                continue
            _, px, py, _ = d["pin1"]
            circle(L, px - bl.ORIGIN[0], py - bl.ORIGIN[1], 0.16, 0.0, filled=True)
        text(L, "RV1106 Rev A assembly drawing, top (all parts on top). Filled dot = pin 1 / cathode / + pad. "
                "References are F.Fab copies (19 are not on silk).", -5.0, 82.0, 1.0)
        # readable F.Fab texts (copy only): references >= 0.5 mm (test pads 0.45), values 0.25 mm
        # on chip parts, <= 0.6 mm elsewhere; chip R / C / L F.Fab body boxes go to
        # Eco2 (unplotted; their lines would cross the text); test-pad net labels are hidden (the TP numbers stay)
        chip = re.compile(r"^(R|C|L)_0(402|603|805)_")

        def grow(item, hmin, hmax=9.0):
            sz = item.GetTextSize()
            h = min(max(mm(sz.y), hmin), hmax)
            item.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(h * 0.9), pcbnew.FromMM(h)))
            item.SetTextThickness(pcbnew.FromMM(h * 0.13))
        for d in P.values():
            fpb = board.FindFootprintByReference(d["ref"])
            is_chip = bool(chip.search(d["fpname"]))
            is_tp = d["fpname"].startswith("TestPoint")
            for v in fpb.GetFields():
                if v.GetName() == "Value" and v.GetLayer() == pcbnew.F_Fab:
                    grow(v, 0.25, 0.25 if is_chip else 0.6)
                    if is_tp:
                        v.SetVisible(False)
            drop = []
            for item in fpb.GraphicalItems():
                if item.GetLayer() != pcbnew.F_Fab:
                    continue
                if item.GetClass() == "PCB_TEXT":
                    if item.GetText() in ("${REFERENCE}", "%R"):
                        item.SetVisible(True)
                        grow(item, 0.45 if is_tp else 0.5)
                    elif is_tp:
                        item.SetVisible(False)
                elif is_chip and item.GetClass() == "PCB_SHAPE":
                    drop.append(item)
            for item in drop:              # moved to an unplotted layer, not removed (pcbnew ownership)
                item.SetLayer(pcbnew.Eco2_User)
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, name + ".kicad_pcb")
    pcbnew.SaveBoard(path, board)
    txt = open(path).read().replace('(paper "A4")', '(paper "A3")', 1)
    open(path, "w").write(txt)
    return path


def export_docs(P, aux):
    fabpcb = annotated_copy(P, aux, "fabdrawing", "fab")
    run([bl.KICAD_CLI, "pcb", "export", "pdf", "--mode-single", "-o", os.path.join(FAB, "fab-drawing.pdf"),
         "--layers", "Edge.Cuts,User.1,User.Drawings", "--black-and-white", "--scale", "2.5", fabpcb])
    asmpcb = annotated_copy(P, aux, "assembly", "asm")
    run([bl.KICAD_CLI, "pcb", "export", "pdf", "--mode-single", "-o", os.path.join(FAB, "assembly-top-refs.pdf"),
         "--layers", "F.Fab,Edge.Cuts,User.Comments", "--ev", "--black-and-white", "--scale", "3", asmpcb])
    run([bl.KICAD_CLI, "pcb", "export", "pdf", "--mode-single", "-o", os.path.join(FAB, "assembly-top-values.pdf"),
         "--layers", "F.Fab,Edge.Cuts,User.Comments", "--erd", "--black-and-white", "--scale", "3", asmpcb])
    for side in ("top", "bottom"):
        run([bl.KICAD_CLI, "pcb", "render", "-o", os.path.join(FAB, "render-3d-%s.png" % side), "--side", side,
             "--quality", "high", "-w", "1800", "-h", "1600", "--background", "opaque", bl.BOARD_FILE])
    run([bl.KICAD_CLI, "pcb", "export", "ipcd356", "-o", os.path.join(FAB, "rv1106-reva.d356"), bl.BOARD_FILE])
    shutil.rmtree(WORK, ignore_errors=True)
    print("L6 docs: fab-drawing.pdf, assembly-top-refs.pdf, assembly-top-values.pdf, render-3d-top/bottom.png, "
          "rv1106-reva.d356")


# ---------------------------------------------------------------------------------------------------------------
# 4. the two notes for the owner
# ---------------------------------------------------------------------------------------------------------------
def write_rotations_md(asm):
    L = []
    L.append("# CPL rotations (JLC) — generated by `design/pcb/scripts/l6_fab.py`, do not edit")
    L.append("")
    L.append("JLC rotation = KiCad rotation + correction (mod 360). KiCad's 0° is the IPC-7351B zero orientation of the "
             "footprint file (pin 1 top-left on ICs, pad 1 on the left on two-terminal parts). JLC's 0° is the 0° of "
             "the part's model in JLC's library. **The corrections are the widely used KiCad → JLC values (SOT-23 "
             "family +180°, QFN / SON family +270°, CP_Elec +180°, everything else 0°), recalled, not fetched: "
             "UNVERIFIED.** JLC's online preview could not be used (no upload by the team, H2), so the owner checks "
             "every orientation-sensitive part below in JLC's 3-D / assembly preview at order time and fixes the "
             "rotation there if a part shows turned.")
    L.append("")
    L.append("How to check one part: in JLC's preview (top view, north = the RJ45 / buttons edge at the top) the "
             "part's pin-1 dot / cathode band / + mark must sit on the side given in the last column. That column "
             "comes from the board itself (where pad 1 is), so it is right whatever JLC's 0° convention is. The "
             "assembly drawing `assembly-top-refs.pdf` shows the same pad with a filled dot.")
    L.append("")
    L.append("Mid X / Mid Y = centre of the bounding box of all the part's pads (origin: panel lower-left, y up, the "
             "same origin as the Gerbers and the drill files). For parts whose KiCad origin is not that centre, the "
             "shift is listed at the end.")
    L.append("")
    L.append("## Per footprint family")
    L.append("")
    L.append("| Family | KiCad footprint | Refs | KiCad rotations used | Correction | Pin 1 / polarity pad at 0° (KiCad) | Why | Source |")
    L.append("|---|---|---|---|---|---|---|---|")
    fams = {}
    for d in asm:
        fams.setdefault(d["family"][0], []).append(d)
    for fam in FAMILIES:
        ds = fams.get(fam[0])
        if not ds:
            continue
        refs = sorted((d["ref"] for d in ds), key=ref_key)
        rots = sorted(set(fmt_rot(d["rot"]) for d in ds), key=float)
        p0 = sorted(set(d.get("pin1_at0", "-") for d in ds))
        fpn = sorted(set(d["fpname"] for d in ds))
        L.append("| %s | %s | %s (%d) | %s | **%+d°** | %s | %s | %s |" % (
            fam[0], ", ".join(fpn), " ".join(refs), len(refs), ", ".join(rots), fam[2],
            ", ".join(p0) if fam[3] != "none" else "n/a (non-polar)", fam[4], fam[5]))
    L.append("")
    L.append("## Every orientation-sensitive part (owner: confirm each in JLC's preview)")
    L.append("")
    L.append("| # | Ref | Value | Family | KiCad rot | Correction | JLC rot | Mid X | Mid Y | Mark | Must be at (board top view) | Checked |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    n = 0
    for d in asm:
        fam = d["family"]
        if fam[3] == "none":
            continue
        n += 1
        word = POLARITY_WORD.get(fam[0], "pin %s" % d["pin1"][0] if "pin1" in d else "pin 1")
        where = d["pin1"][3] if "pin1" in d else "-"
        if fam[3] == "rot90":
            word = "pin 1 (90° matters, 180° does not)"
        L.append("| %d | %s | %s | %s | %s | %+d | %s | %.4f | %.4f | %s | %s of the part centre | [ ] |" % (
            n, d["ref"], d["value"], fam[0], fmt_rot(d["rot"]), fam[2], fmt_rot(d["jlc_rot"]), d["fx"], d["fy"],
            word, where))
    L.append("")
    L.append("%d orientation-sensitive parts. Non-polar parts (chip R / C, ferrites, fuse, power inductors, 2-pad "
             "crystal) need no check beyond 'pads along the right axis'." % n)
    L.append("")
    L.append("## Parts whose KiCad origin is not the pad centre (CPL uses the pad centre)")
    L.append("")
    L.append("| Ref | KiCad origin (fab mm) | CPL Mid (fab mm) | Shift (mm) |")
    L.append("|---|---|---|---|")
    for d in asm:
        dx, dy = d["fx"] - d["anchor"][0], d["fy"] - d["anchor"][1]
        if math.hypot(dx, dy) > 0.005:
            L.append("| %s | (%.3f, %.3f) | (%.3f, %.3f) | %.3f |" % (d["ref"], d["anchor"][0], d["anchor"][1],
                                                                 d["fx"], d["fy"], math.hypot(dx, dy)))
    L.append("")
    L.append("If JLC's preview puts one of these parts off its pads, move it there in the preview (JLC's own model "
             "origin decides); the pad centre is what the CPL gives.")
    open(os.path.join(FAB, "cpl-rotations.md"), "w").write("\n".join(L) + "\n")
    return n


def bom_cost():
    """the live cost model: design/tools/check_bom.py (design/.venv) prints one 'cost: {json}' line."""
    vpy = os.path.join(bl.DESIGN, ".venv", "bin", "python")
    out = run([vpy, "-I", os.path.join(bl.DESIGN, "tools", "check_bom.py"), bl.DESIGN])
    line = [x for x in out.splitlines() if x.startswith("cost: ")]
    if not line:
        raise SystemExit("L6: check_bom.py printed no cost line")
    import json
    return json.loads(line[-1][6:])


def board_numbers(board, aux):
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vd = sorted(set(round(mm(v.GetDrillValue()), 3) for v in vias))
    vw = sorted(set(round(mm(v.GetWidth(pcbnew.F_Cu)), 3) for v in vias))
    tw = min(round(mm(t.GetWidth()), 3) for t in tracks)
    ds = board.GetDesignSettings()
    return dict(nvias=len(vias), via_drills=vd, via_diams=vw, min_track=tw,
                min_clear=round(mm(ds.m_MinClearance), 3), ntracks=len(tracks))


def write_order_notes(board, P, asm, aux, upload, nrot):
    N = board_numbers(board, aux)
    vip = list(csv.DictReader(open(VIP_CSV, newline="")))
    bom = read_bom()
    edge = board.GetBoardEdgesBoundingBox()
    w = mm(edge.GetWidth()) - 0.1
    h = mm(edge.GetHeight()) - 0.1
    fids = sorted([d for d in P.values() if d["fpname"].startswith("Fiducial")], key=lambda d: d["ref"])
    ths = sorted([d for d in P.values() if d["ref"].startswith("TH")], key=lambda d: ref_key(d["ref"]))
    tht = [d for d in asm if d["tht"]]
    tht_j = sum(1 for d in tht for p in d["fp"].Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
    j1_pegs = sum(1 for p in P["J1"]["fp"].Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
    U = []
    a = U.append
    a("# Order notes for the owner (JLCPCB, Rev A) — generated by `design/pcb/scripts/l6_fab.py`, do not edit")
    a("")
    a("Everything here is for you to type into JLCPCB's order form yourself. The team did not log in, upload, quote or "
      "pay (owner step H2). Values marked **ESTIMATE** or **UNVERIFIED** must be confirmed on the live quote.")
    a("")
    a("## 1. Files to upload")
    a("")
    a("| Order step | File (in `design/pcb/fab/`) |")
    a("|---|---|")
    a("| PCB (Gerber + drill, one zip) | `%s` (%d files: %s) |" % (ZIP_NAME, len(upload), ", ".join(upload)))
    a("| Assembly BOM | `jlc-bom.csv` (%d rows = %d unique parts, %d placed parts per board, every row has an LCSC number) |"
      % (len(bom), len(bom), len(asm)))
    a("| Assembly CPL (pick and place) | `jlc-cpl.csv` (%d rows, top side; rotations see `cpl-rotations.md`) |" % len(asm))
    a("| For you / JLC engineer if asked | `assembly-top-refs.pdf`, `assembly-top-values.pdf`, `fab-drawing.pdf`, "
      "`gerbers/*drl_map.pdf`, `render-3d-top.png`, `render-3d-bottom.png`, `rv1106-reva.d356` (IPC-D-356 netlist, "
      "optional upload for the electrical test) |")
    a("")
    a("Not assembled (no part, listed in `jlc-bom-not-assembled.csv`): %d footprints — 31 test pads, 5 fiducials, "
      "4 M3 holes, 4 tooling holes, JP1 (closed solder jumper), NT1 (net tie). Schematic DNP items without a footprint "
      "on the board (ED1/ED2 ESD, RTC battery holder, battery diode, PB 100 nF) are not in any file."
      % sum(1 for d in P.values() if not d["assembled"]))
    a("")
    a("## 2. PCB options")
    a("")
    a("| JLC field | Set to | Why / source |")
    a("|---|---|---|")
    a("| Base material, layers | FR-4, **4** | layout.md §2 |")
    a("| Dimensions | **%.1f × %.1f mm** (the panel: board 80 × 80 + two 5 mm rails west / east) | measured from Edge.Cuts; layout.md §1 |" % (w, h))
    a("| PCB qty | **5** | D-H2 (2 assembled + 3 bare) |")
    a("| Delivery format / panel | **Panel by customer**, 1 × 1, **no extra edge rails** (rails, fiducials and tooling holes are already in the Gerbers) | layout.md §1, D-61 |")
    a("| V-cut | V-cut lines are drawn: file `rv1106-reva-V-CUT.gbr` (two straight full-height lines at board x = 0 and x = 80, i.e. 5.00 and 85.00 mm from the panel's left edge), see remark | layout.md §1; how JLC wants V-cuts marked is UNVERIFIED |")
    a("| Thickness | **1.6 mm** | D-67 |")
    a("| Impedance control | **Yes, JLC04161H-7628** | layout.md §2.2 (D-83): ETH pairs 100 Ω (0.235 mm / gap 0.200 mm), USB pairs 90 Ω (0.255 / 0.150 mm), L1 over the L2 GND plane |")
    a("| Surface finish | **ENIG** | D-62 |")
    a("| Outer / inner copper | **1 oz / 0.5 oz** | layout.md §2.1 (stackup table; there is no separate stackup.md) |")
    a("| Colour | **green** mask, **white** silk | D-67 |")
    a("| Via covering | **Epoxy filled & capped (POFV / via-in-pad)** for all %d vias (0.3 mm drill / %s mm pad) | D-H6, D-117 b, D-119 |" % (N["nvias"], "/".join("%.2f" % x for x in N["via_diams"])))
    a("| Min via hole / diameter | %s mm / %s mm | board |" % ("/".join("%.2f" % x for x in N["via_drills"]), "/".join("%.2f" % x for x in N["via_diams"])))
    a("| Min track / spacing | **%.2f mm / %.2f mm** (only inside the U9 QFN-128 escape; 0.15 / 0.15 mm elsewhere) | board tracks + design rules; JLC 4-layer minimum 0.09 / 0.09 mm [JLC-CAP] |" % (N["min_track"], N["min_clear"]))
    a("| Board outline tolerance, others | defaults | — |")
    a("")
    a("Vias in or touching SMD pads (`design/pcb/via_in_pad.csv`, %d rows; POFV fills and caps every via anyway):" % len(vip))
    a("")
    a("| Pad | Net | x (board mm) | y (board mm) | Reason |")
    a("|---|---|---|---|---|")
    for r in vip:
        a("| %s | %s | %s | %s | %s |" % (r["pad"], r["net"], r["x"], r["y"], r["reason"].replace("|", "/")))
    a("")
    a("## 3. Assembly options")
    a("")
    a("| JLC field | Set to |")
    a("|---|---|")
    a("| PCBA type | **Standard** (the 0.35 mm-pitch QFN rules out Economic) |")
    a("| Assembly side | **Top** only (no parts on the bottom) |")
    a("| PCBA qty | **2** |")
    a("| Tooling holes | **Added by customer** (4 × 2.0 mm NPTH in the rails) |")
    a("| Confirm parts placement | **Yes** |")
    a("| Stencil | **0.10 mm** if the form has the field, otherwise in the remark (0.35 mm-pitch QFN, D-85a / D-H7 item 3) |")
    a("")
    a("Fiducials and tooling holes (Gerber / CPL origin = panel lower-left, y up; board mm = origin board NW corner, y down):")
    a("")
    a("| Ref | What | Gerber / CPL x, y (mm) | board x, y (mm) |")
    a("|---|---|---|---|")
    for d in fids + ths:
        what = "1.0 mm fiducial, 2.0 mm mask opening" if d in fids else "2.0 mm NPTH tooling hole"
        a("| %s | %s | %.2f, %.2f | %.2f, %.2f |" % (d["ref"], what, d["fx"], d["fy"], d["cx"] - bl.ORIGIN[0], d["cy"] - bl.ORIGIN[1]))
    a("")
    a("Global fiducials GFID1-3 sit on the rails 3.85 mm from the panel edges (JLC's text); FID1/FID2 are local, "
      "diagonal to U9. The tooling-hole positions JLC expects are UNVERIFIED (JLC states only the 2.0 mm size).")
    a("")
    a("Through-hole parts: %s are placed and soldered **by JLC** (THT service, %d plated joints per board); the USB-C J1 is "
      "an SMD part with %d plated shell pegs, also soldered by JLC: %d manual joints per board, %d for 2 boards as "
      "costed. Nothing is left for you to hand-solder." % (", ".join("%s (%s)" % (d["ref"], d["value"]) for d in tht),
                                                            tht_j, j1_pegs, tht_j + j1_pegs, 2 * (tht_j + j1_pegs)))
    a("")
    a("**Remark to paste** (PCB + assembly):")
    a("")
    a("> Panel by customer: board 80 x 80 mm with 5 mm edge rails on the left and right (total 90 x 80 mm). Please "
      "V-cut along the two lines in file rv1106-reva-V-CUT.gbr (x = 5.00 mm and x = 85.00 mm from the panel's left "
      "edge, full height, zero gap) to remove the rails; do not add more rails. Fiducials and 2.0 mm tooling holes "
      "are on the rails. Via covering: epoxy filled and capped (via-in-pad) for all vias, incl. the 16 vias in the "
      "U9 exposed pad. U9 is a 0.35 mm-pitch QFN-128: please use a 0.10 mm stencil. Board corners have 1.5 x 1.5 mm "
      "routed notches with R 0.5 mm inner corners.")
    a("")
    a("## 4. Check before paying (JLC's DFM and parts preview)")
    a("")
    a("1. **RV1106G3 (C5328706) stock >= 4** (2 boards + 2, D-H2). It was 23 on 2026-10-29. If lower, do not order.")
    a("2. **POFV price** on the 4-layer quote (UNVERIFIED; not in the cost estimate below). JLC's DFM must keep all %d "
      "vias filled + capped, including the 16 EP vias (they are real board vias since D-119)." % N["nvias"])
    a("3. **Router bit** for the four 1.5 × 1.5 mm rail notches with R 0.5 mm inner corners (needs a bit <= 1.0 mm; "
      "UNVERIFIED, D-117 h / D-118 c). If the DFM flags it, accept a larger inner radius only on the rail side.")
    a("4. **V-cut** is read from the V-CUT file / remark (UNVERIFIED how JLC wants it); the DFM view must show two "
      "cuts at 5 mm from each side, nothing else.")
    a("5. **Every CPL rotation**: open the 3-D / assembly preview and tick the %d rows of `cpl-rotations.md` (pin 1 / "
      "cathode / + position). The SOT-23 / QFN / SON / CP corrections are UNVERIFIED community values." % nrot)
    a("6. **THT parts** J3, J4, J5, J6 appear in the parts list (THT assembly) and the USB-C J1 pegs are soldered.")
    a("7. **No part 'not matched'**: the BOM has %d LCSC numbers; any part JLC cannot source stops the order (replace "
      "only after a team review)." % len(bom))
    a("8. **Fixture fee / pre-reflow fee**: cost.md counts the fixture ($16.42) and not the pre-reflow fee (see below).")
    a("9. RV1106G3 is MSL3 ([DS] r1.8 p.18); how JLC bakes MSL3 parts is UNVERIFIED.")
    a("")
    a("## 5. Cost against the $380 cap (D-H2)")
    a("")
    C = bom_cost()
    a("Numbers from `design/tools/check_bom.py design` run by this script on today's bom.csv (cost.md still shows "
      "the pre-D-117 c figure $373.34 with 64 part types; the BOM now has %d)." % C["unique_types"])
    a("")
    a("| Item | USD | Status |")
    a("|---|---|---|")
    a("| Parts (%d unique, %d Extended) | %.2f | LCSC ladder prices fetched 2026-10-29 (cost.md) |" % (
        C["unique_types"], C["extended_types"], C["parts"]))
    ai = C["assembly_items"]
    a("| Assembly: setup %.2f, stencil %.2f, %d SMT joints %.2f, %d THT joints %.2f, feeder loading %.2f, X-ray %.2f, "
      "fixture %.2f, packing %.2f, confirm placement %.2f | %.2f | price page 2026-10-28 |" % (
          ai["setup"], ai["stencil"], C["smt_joints"], ai["smt"], C["tht_joints"], ai["manual"], ai["feeders"],
          ai["xray"], ai["fixture"], ai["packing"], ai["confirm"], C["assembly"]))
    a("| PCB, 5 pcs, 4-layer, 90 × 80 mm, ENIG | %.2f | **ESTIMATE** (no live quote) |" % C["pcb_est"])
    a("| Shipping | %.2f | **ESTIMATE** |" % C["shipping_est"])
    a("| **Total (check_bom)** | **%.2f** | margin %.2f to the cap |" % (C["total"], 380 - C["total"]))
    a("| POFV (epoxy-filled, capped vias) on 4 layers | not costed | **UNVERIFIED**: chosen by D-H6 after the estimate; "
      "if it costs more than $%.2f the total exceeds $380 |" % (380 - C["total"]))
    a("| Pre-reflow soldering fee (if charged) | 0 to 21 | UNVERIFIED (cost.md §1) |")
    a("")
    a("So the order stays within the cap only if the live PCB + POFV + shipping price is <= $%.2f (%.2f + %.2f + "
      "%.2f). If the live total exceeds $380, stop: the cap is the owner's rule." % (
          C["pcb_est"] + C["shipping_est"] + 380 - C["total"], C["pcb_est"], C["shipping_est"], 380 - C["total"]))
    a("")
    a("## 6. Do not")
    a("")
    a("- **Never run 'Update footprints from library'** (or 'Update PCB from schematic' with footprint replacement) on "
      "this board: 152 footprints were edited on purpose (silk widths, trimmed silk, U9 `_EPboardvias` variant "
      "without drilled EP pads, D-117 i, D-129). It would bring back the U9 ComponentDrill pads and undo the silk "
      "fixes. Rebuild only with `design/pcb/scripts/rebuild_all.sh`.")
    a("- Do not hand-edit anything in `design/pcb/fab/`: run `sh design/pcb/scripts/l6_run.sh` again.")
    a("- Depanel by breaking the rails off with pliers close to the V-cut, not by bending the board (layout.md §8).")
    a("")
    open(os.path.join(FAB, "order-notes.md"), "w").write("\n".join(U) + "\n")


def main():
    if os.path.isdir(FAB):
        for name in os.listdir(FAB):
            if name in ("check_fab.txt", "gerber-view"):
                continue
            p = os.path.join(FAB, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(GERB, exist_ok=True)
    board = edit_board()
    a = board.GetDesignSettings().GetAuxOrigin()
    aux = (mm(a.x), mm(a.y))
    bom, P = parts(board, aux)
    asm = write_bom_cpl(bom, P)
    files = export_gerbers_drill()
    upload = make_zip(files)
    export_docs(P, aux)
    nrot = write_rotations_md(asm)
    write_order_notes(board, P, asm, aux, upload, nrot)
    print("L6 done: aux origin page (%.2f, %.2f) mm; %d orientation-sensitive parts in cpl-rotations.md" % (aux + (nrot,)))


if __name__ == "__main__":
    main()
