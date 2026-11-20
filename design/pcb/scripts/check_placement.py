#!/usr/bin/env python3
"""Layout phase L2: check the placement of design/pcb/rv1106-reva.kicad_pcb against gate TP-L2 / layout.md §10
"Placement", then run kicad-cli DRC.

    PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $PY design/pcb/scripts/check_placement.py          # exit 0 = every rule PASS (or a recorded deviation)

Distances: "edge" = shortest straight line between the two pads' copper outlines. That is a LOWER BOUND of the trace
length the router will need (a real trace is never shorter), so a pass here is necessary, not sufficient: L4 measures
the routed lengths. The centre-to-centre distance is printed beside it for information.
Deviations recorded in design/decisions.md (D-103) are listed in DEVIATIONS; they print as DEV, not FAIL.
"""
import collections
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402

import pcbnew  # noqa: E402

# ref -> (rule id prefix, reason, decision)
DEVIATIONS = {
    ("zone", "J2"): "D-103 (a): J2 courtyard 17.3 mm wide does not fit the 16 mm rectangle; moved 0.9 mm west",
    ("zone", "J4"): "D-103 (a): J4 courtyard 16.5 mm wide (drawing) does not fit the 15.5 mm rectangle",
    ("zone", "J1"): "D-103 (a): J1 courtyard follows the HRO footprint (mouth 0.55 mm over the routed edge)",
    ("zone", "J3"): "D-103 (a): J3 courtyard follows the HR911105A footprint (0.55 mm over the routed edge)",
    ("zone", "J5"): "D-103 (a): J5 courtyard follows the stock 2x20 footprint (0.05 mm larger than zones.csv)",
    ("zone", "J6"): "D-103 (a): J6 courtyard follows the stock 1x3 footprint",
    ("zone", "R61"): "D-103 (e): U8 EN pull-down next to pin 4, 0.1 mm east of Z-USB (no room inside)",
    ("zone", "TP2"): "D-103 (d): power test row at the top of Z-PWRIN (layout.md §5.4)",
    ("zone", "TP3"): "D-103 (d): power test row at the top of Z-PWRIN (layout.md §5.4)",
    ("zone", "TP4"): "D-103 (d): power test row at the top of Z-PWRIN (layout.md §5.4)",
    ("zone", "TP5"): "D-103 (d): power test row at the top of Z-PWRIN (layout.md §5.4)",
    ("zone", "TP15"): "D-115: VDD_ARM test pad moved from the power test row to 3.4 mm from C44.1 (Z-HDR edge): its 58 mm "
                      "load-free L4 branch on the core rail is gone (verifier L5 r2 minor soc)",
    ("zone", "R66"): "D-115: UART2_TX series resistor moved next to J6 / TP9 (Z-UART) to free the north exit of U9",
    ("zone", "R67"): "D-115: UART2_RX series resistor moved next to J6 / TP10 (Z-UART), same",
    ("zone", "C69"): "D-115: VCC_1V8 4.7 uF bulk moved north-east of the U9 north lane field (unzoned strip y 17-22)",
    ("zone", "TP31"): "D-115: TP6's GND reference pad moved north-east of TP6 (2.7 mm), half out of Z-SOC",
    ("zone", "TP23"): "D-115: AVDD1V8_USB test pad moved next to its rail south of U9 (Z-USB)",
    ("zone", "TP18"): "D-115: VCC3V3_RTC test pad moved next to its rail south of U9 (Z-USBA-PWR)",
    ("ring2", "C69"): "D-115: pin-70 bulk 4.7 uF moved out of the north lane corridor (the 100 nF C55 stays at pin 70); "
                      "fed by a via in its pad and L4 to C55's rail via",
    ("zone", "Y2"): "D-105: RTC crystal below the SDMMC corridor, at the top of Z-USB (corridor >= 2.4 mm)",
    ("zone", "C78"): "D-105: RTC load cap under Y2 pad 2, in Z-USB with Y2",
    ("zone", "C79"): "D-105: RTC load cap under Y2 pad 1, in Z-USB with Y2",
    ("zone", "TP24"): "D-105: VCC1V8_CODEC test pad in the unzoned strip under U10 (Z-SOC full once the FSPI run "
                      "is kept free), 3-4 mm from FB2",
    ("zone", "R53"): "D-106 (c): D2 pull-up on the D2 run west of U10 (FSPI order), 3 mm into Z-SOC",
    ("zone", "R54"): "D-106 (c): CS pull-up between the CLK and CS runs west of R55, 1.7 mm into Z-SOC",
    ("zone", "C82"): "D-106 (b): centre-tap cap right under J3 pin 4, courtyard 0.11 mm north of Z-ETH (J3 strip)",
    ("zone", "C83"): "D-106 (b): centre-tap cap under the 6|4 gap, courtyard 0.11 mm north of Z-ETH (J3 strip)",
    ("zone", "R56"): "D-106 (b): TXP 0R bridge east of the RX field (TX joins J3 pins 1/2 from the south-east)",
    ("zone", "R57"): "D-106 (b): TXN 0R below R56, same",
    ("buck", "CIN_GND"): "D-107: the 1 mm C_IN rule applies to the VIN pad; on SOT-23-5 GND pin 2 is on the far side, "
                         "the GND pad returns through the L1 pour and its vias as in [TLV] SLVSDG1C Fig. 20 p.13",
    ("xtal", "RTC_LEN"): "D-105: RTC lanes ~7-8 mm (> 6 mm) to keep the SDMMC corridor; RTC unused on Rev A (D-75)",
    ("local", "R59"): "D-106 (b), D-108 (b): R59 0.13 mm over: the RX P/N bridge R58 sits between it and the jack",
    ("local", "R58"): "D-108 (b): RXP_J pad 6.48 mm from its own pin J3.3 (top row, behind pin 4); R58 cannot move "
                      "north (C83/C82 under pins 5/4) and the RX swap needs it here",
    ("trial", "ETH_RX_SKEW"): "D-108 (b): RX P/N skew of the untuned trial route; removed by a serpentine on RXN in L5 "
                              "(RXP total stays <= 30 mm)",
    ("trial", "ETH_RX_UNCOUPLED"): "D-108 (b): RX pair split around R59/R58 and from R58 to J3 pins 6/3 (top/bottom "
                                   "rows 3.8 mm apart); layout.md allows the RX split around pins 4/5",
    ("trial", "ETH_TX_UNCOUPLED"): "D-108 (b): TX pair split at the R57/R56 P/N swap and into J3 pins 2/1 (rows "
                                   "2.54 mm apart)",
    ("trial", "ETH_TX_SKEW"): "D-108 (b): TX P/N skew of the untuned trial route; removed by a serpentine on the "
                              "short line in L5",
    ("ring1", "C72"): "D-104 (e): RECOVERY drops to L4 at the via ring; its RC sits in the NE of Z-SOC",
    ("ring1", "C73"): "D-104 (e): SARADC_IN1 drops to L4 at the via ring; its RC sits in the NE of Z-SOC",
    ("ring1", "R44"): "D-104 (e): RECOVERY pull-up, same",
    ("ring1", "R45"): "D-104 (e): SARADC_IN1 pull-up, same",
    ("ring1", "C60"): "D-104 (c): second 100 nF of VCC_1V8 moved from pin 70 to the other VCC_1V8 pin 53 (checked there)",
    ("ring1", "R50"): "D-104 (d): R50 on the OSC_XOUT lane just past the ring-1 row (R51 takes the row slot)",
    ("xtal", "Y1"): "D-104 (d): Y1 directly beyond the ring-1 row (the row now starts 1.45 mm out); XIN <= 5 mm still",
    ("xtal", "R50"): "D-104 (d): R50 on the OSC_XOUT lane just past the ring-1 row",
    ("xtal", "TP6"): "D-104 (d): TP6 beyond the row; stub to R50.1 <= 3 mm still met",
    ("xtal", "Y2"): "D-105: RTC crystal moved south of the SDMMC corridor (verifier L2 r2); RTC unused on Rev A (D-75)",
    ("ring1", "R43"): "D-104 (g): NPOR pull-up in the NE corner square; C71 (the filter cap) takes the gate slot",
    ("ring2", "C75"): "D-104 (h): VCC3V3_RTC 1 uF (uA RTC rail, no battery) in the SE corner, fed from the pin-19 L4 via",
    ("ring2", "R34"): "D-104 (h): RTC series resistor beside C75, same",
    ("ring2", "TP18"): "D-104 (h): DC sub-rail test pad in the NE of Z-SOC (no room near pins 19-25)",
    ("ring2", "TP23"): "D-104 (h): DC sub-rail test pad in the NE of Z-SOC, same",
    ("ring1", "C26"): "D-103 (g): 10 uF in line behind C23 in the free VDD column of the J2 contact row",
    ("ring1", "C83"): "D-103 (f), D-106 (b): J3 pin 5 lies under the jack body; C83 under the 6|4 gap, RCT straight up",
    ("escape", "22"): "D-104 (e): SARADC_IN1 (SENSE, DC) on L4 instead of L1 (§2.3)",
    ("escape", "23"): "D-104 (e): RECOVERY (SENSE, DC key) on L4 instead of L1 (§2.3)",
    ("escape", "25"): "D-104 (e): USB_DET_IN (SENSE, DC divider) on L4 under the USB pair (§2.3)",
}

results = []   # (status, rule, item, value, limit, note)


def rec(ok, rule, item, value, limit, note="", dev_key=None):
    st = "PASS" if ok else ("DEV" if dev_key in DEVIATIONS else "FAIL")
    if not ok and dev_key in DEVIATIONS:
        note = (note + "; " if note else "") + DEVIATIONS[dev_key]
    results.append((st, rule, item, value, limit, note))


board = pcbnew.LoadBoard(bl.BOARD_FILE)
FP = {fp.GetReference(): fp for fp in board.GetFootprints()}
PL = bl.placement()
ZN = bl.zones()
MECH = {"H1", "H2", "H3", "H4", "FID1", "FID2", "GFID1", "GFID2", "GFID3", "TH1", "TH2", "TH3", "TH4"}


class MissingPad(KeyError):
    pass


def pad(ref, num):
    """Pad `num` of `ref`; a missing footprint or pad raises MissingPad, which main() reports as a FAIL."""
    if ref not in FP:
        raise MissingPad("%s (footprint)" % ref)
    for p in FP[ref].Pads():
        if p.GetNumber() == str(num):
            return p
    raise MissingPad("%s.%s" % (ref, num))


def dist(ra, pa, rb, pb):
    a, b = pad(ra, pa), pad(rb, pb)
    return bl.edge_dist(a, b), bl.centre_dist(a, b)


def nets_of(ref):
    return {p.GetNumber(): p.GetNetname() for p in FP[ref].Pads() if p.GetNumber()}


def u9_pins_on(net):
    return [p.GetNumber() for p in FP["U9"].Pads() if p.GetNetname() == net and p.GetNumber() != "129"]


def part_pad_for_pin(ref, pin):
    """The pad of `ref` on the net of U9 `pin`; None if none."""
    net = pad("U9", pin).GetNetname()
    for n, nn in nets_of(ref).items():
        if nn == net:
            return n
    return None


def best_pad_dist(ref, pin):
    """Edge distance from the part to SoC pin: the pad on the same net, else the nearest pad."""
    pp = part_pad_for_pin(ref, pin)
    if pp:
        return dist(ref, pp, "U9", pin) + (pp,)
    best = None
    for p in FP[ref].Pads():
        if not p.GetNumber():
            continue
        e = bl.edge_dist(p, pad("U9", pin))
        if best is None or e < best[0]:
            best = (e, bl.centre_dist(p, pad("U9", pin)), p.GetNumber())
    return best


def bbox_of(ref):
    bb = bl.courtyard_bbox(FP[ref])
    if bb:
        return bb
    xs, ys = [], []
    for p in FP[ref].Pads():
        for x, y in bl.pad_polygon(p):
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


def fab_bbox(ref):
    xs, ys = [], []
    for g in FP[ref].GraphicalItems():
        if g.GetLayer() == pcbnew.F_Fab and g.GetClass() != "PCB_TEXT":
            b = g.GetBoundingBox()
            x0, y0 = bl.to_board(pcbnew.VECTOR2I(b.GetX(), b.GetY()))
            x1, y1 = bl.to_board(pcbnew.VECTOR2I(b.GetRight(), b.GetBottom()))
            xs += [x0, x1]
            ys += [y0, y1]
    return (min(xs), min(ys), max(xs), max(ys))


def check_netlist():
    comps, nets = bl.read_netlist()
    parts = [r for r in FP if r not in MECH]
    rec(len(parts) == 226 and set(parts) == set(comps), "netlist", "footprints", len(parts), 226)
    names = {board.GetNetInfo().GetNetItem(i).GetNetname() for i in range(1, board.GetNetCount())}
    rec(names == {n for _c, n, _ in nets}, "netlist", "nets", len(names), 135)
    bad = []
    for _c, name, nodes in nets:
        for ref, pin in nodes:
            ps = [p for p in FP[ref].Pads() if p.GetNumber() == pin]
            if not ps or any(p.GetNetname() != name for p in ps):
                bad.append("%s.%s" % (ref, pin))
    rec(not bad, "netlist", "pads with their netlist net", "%d missing/wrong" % len(bad), 0, " ".join(bad[:10]))
    bottom = [r for r, f in FP.items() if f.IsFlipped()]
    rec(not bottom, "side", "parts on the bottom", len(bottom), 0, " ".join(bottom))


def zone_rect(name):
    z = ZN[name]
    return (z["x0"], z["y0"], z["x1"], z["y1"])


def check_zones():
    conn_zone = {"J1": "J1-USBC", "J2": "J2-SD", "J3": "J3-RJ45", "J4": "J4-USBA", "J5": "J5-HDR", "J6": "J6-UART"}
    n_in = 0
    for ref, row in sorted(PL.items()):
        zname = conn_zone.get(ref, row["zone"])
        r = zone_rect(zname)
        b = bbox_of(ref)
        tol = 1e-3
        ok = b[0] >= r[0] - tol and b[1] >= r[1] - tol and b[2] <= r[2] + tol and b[3] <= r[3] + tol
        out = max(r[0] - b[0], r[1] - b[1], b[2] - r[2], b[3] - r[3], 0)
        if ok:
            n_in += 1
        else:
            rec(False, "zone", ref, "%.2f mm outside %s" % (out, zname), "inside", "courtyard (%.2f,%.2f)-(%.2f,%.2f)"
                % b, ("zone", ref))
    rec(True, "zone", "parts with the courtyard inside their placement.csv zone", n_in, 226)


def check_connectors():
    f3 = fab_bbox("J3")
    rec(abs(f3[1] - 0.0) <= 0.5, "connector", "J3 RJ45 mouth on the north edge (fab front y)", "%.2f" % f3[1], "0 +-0.5")
    for ref in ("J1", "J2", "J4"):
        f = fab_bbox(ref)
        rec(abs(f[3] - 80.0) <= 0.5, "connector", "%s mouth on the south edge (fab front y)" % ref, "%.2f" % f[3],
            "80 +-0.5")
    over = []
    for ref in FP:
        if ref in MECH:
            continue
        b = bbox_of(ref)
        if b[0] < 0.0 - 1e-3 or b[2] > 80.0 + 1e-3:
            over.append(ref)
    rec(not over, "connector", "nothing overhangs the west/east (V-cut) edges", len(over), 0, " ".join(over))
    # fixed positions
    def at(ref):
        x, y = bl.to_board(FP[ref].GetPosition())
        return x, y, FP[ref].GetOrientationDegrees() % 360
    for ref, (x, y, r) in {"U9": (34.5, 36.5, 90), "U8": (43.4, 62.6, 0), "JP1": (63.7, 35.0, 180),
                           "J1": (49.5, 76.35, 0), "J3": (21.46, 17.26, 180)}.items():
        ax, ay, ar = at(ref)
        rec(abs(ax - x) < 1e-3 and abs(ay - y) < 1e-3 and abs(ar - r) < 1e-3, "fixed", ref,
            "(%.2f, %.2f) %g" % (ax, ay, ar), "(%.2f, %.2f) %g" % (x, y, r))
    ax, ay, _ = at("R30")
    rec(abs(ax - 63.5) < 1e-3 and abs(ay - 16.5) < 1e-3, "fixed", "R30", "(%.2f, %.2f)" % (ax, ay), "(63.50, 16.50)")
    p1 = bl.to_board(pad("U9", "1").GetPosition())
    rec(p1[0] < 34.5 and p1[1] > 36.5, "fixed", "U9 pin 1 in the south-west corner", "(%.2f, %.2f)" % p1, "SW")
    u9 = bbox_of("U9")
    for f in ("FID1", "FID2"):
        b = bbox_of(f)
        clear = b[2] < u9[0] or b[0] > u9[2] or b[3] < u9[1] or b[1] > u9[3]
        rec(clear, "fixed", "%s clear of the U9 courtyard" % f, "clear" if clear else "overlap", "clear")


def limit_of(row):
    rule = row["rule"]
    if "ring 2" in rule:
        return 8.0, "ring2"
    m = re.search(r"<= (\d+(?:\.\d+)?) mm", rule) or re.search(r"within (\d+(?:\.\d+)?) mm", rule)
    if m:
        return float(m.group(1)), "ring1"
    return None, None


def check_soc_rings():
    for ref, row in sorted(PL.items(), key=lambda kv: kv[0]):
        if ref in ("U9", "Y1", "Y2"):
            continue
        tgt = bl.target_of(row)
        lim, kind = limit_of(row)
        pins = []
        if tgt:
            pins = [str(tgt[0])]
            if ref == "R51":
                pins = ["68", "69"]
        elif "ring 2" in row["rule"]:
            m = re.search(r"SoC pin (\d+)", row["rule"])
            if m:
                pins = [m.group(1)]
            else:
                for n in nets_of(ref).values():
                    pins += u9_pins_on(n)
                pins = pins[:1]
        if not pins or lim is None:
            continue
        best = None
        for pin in pins:
            e, c, pp = best_pad_dist(ref, pin)
            if best is None or e < best[0]:
                best = (e, c, pp, pin)
        e, c, pp, pin = best
        rule = "ring2" if kind == "ring2" else "ring1"
        note = ""
        if ref in TP_FEEDER and e > lim:
            # testpoints.md §2: "<= 8 mm of trace from its SoC pin / ferrite": the part that feeds the sub-rail counts
            f = TP_FEEDER[ref]
            fp_ = [p for p in FP[f].Pads() if p.GetNetname() == FP[ref].Pads()[0].GetNetname()][0]
            e2 = bl.edge_dist(pad(ref, "1"), fp_)
            note = "SoC pin %.2f; feeder %s %.2f" % (e, f, e2)
            e = min(e, e2)
        rec(e <= lim + 1e-6, rule, "%s.%s -> U9.%s" % (ref, pp, pin), "%.2f (centre %.2f)" % (e, c),
            "<= %.1f" % lim, note, (rule, ref))
    # layout.md §5.3 lists R4/C1 (USB_DET, pin 25) in ring 2; placement.csv has no rule text for them
    for ref in ("R4", "C1"):
        e, c, pp = best_pad_dist(ref, "25")
        rec(e <= 8.0, "ring2", "%s.%s -> U9.25 (layout.md §5.3 ring 2)" % (ref, pp), "%.2f (centre %.2f)" % (e, c),
            "<= 8.0")
    # C60 serves VCC_1V8 pin 53 (D-104 c)
    e, c = dist("C60", part_pad_for_pin("C60", "53"), "U9", "53")
    rec(e <= 3.0, "ring1", "C60 -> U9.53 (D-104 c: the other VCC_1V8 pin)", "%.2f (centre %.2f)" % (e, c), "<= 3.0")
    # ring 2 outside ring 1: no ring-2 courtyard reaches into the gate band (r < 9.65 in front of a side)
    inner = []
    gates = []
    for side in "SENW":
        tc = esc.t_of(side, *esc.CENTRE)
        a = esc.point(side, tc - 7.45, esc.TOE)
        b = esc.point(side, tc + 7.45, 9.65)
        gates.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
    for ref, row in PL.items():
        if "ring 2" in row["rule"] and ref != "NT1":
            bb = bbox_of(ref)
            for g in gates:
                if bb[0] < g[2] and bb[2] > g[0] and bb[1] < g[3] and bb[3] > g[1]:
                    inner.append(ref)
                    break
    rec(not inner, "ring2", "ring-2 courtyards outside the ring-1 gate bands (r < 9.65 mm)", len(inner), 0,
        " ".join(inner) + " (NT1 sits on pin 115 by design, layout.md §3, in front of NC pins 117-121)")


TP_FEEDER = {"TP18": "R34", "TP22": "R32", "TP23": "R33", "TP24": "FB2", "TP25": "FB3", "TP26": "FB1"}


def check_xtal():
    e, c = dist("Y1", "1", "U9", "68")
    rec(e <= 3.0, "xtal", "Y1.1 (XIN) -> U9.68", "%.2f (centre %.2f)" % (e, c), "<= 3.0", "", ("xtal", "Y1"))
    rec(e <= 5.0, "xtal", "OSC_XIN lower bound U9.68 -> Y1.1 (length rule <= 5 mm)", "%.2f" % e, "<= 5.0")
    near = min((bl.edge_dist(q, pad("U9", pn)), q.GetNumber(), pn) for q in FP["Y1"].Pads() for pn in ("68", "69"))
    rec(near[0] <= 3.0, "xtal", "Y1 nearest pad (Y1.%s) -> U9.%s (the crystal body, verifier figure)" % near[1:],
        "%.2f" % near[0], "<= 3.0", "", ("xtal", "Y1"))
    e, c = dist("Y1", "3", "U9", "69")
    rec(True, "xtal", "Y1.3 (XOUT_X) -> U9.69 (info)", "%.2f (centre %.2f)" % (e, c), "info")
    rx = part_pad_for_pin("R50", "69")
    e, c = dist("R50", rx, "U9", "69")
    rec(e <= 2.0, "xtal", "R50.%s -> U9.69" % rx, "%.2f (centre %.2f)" % (e, c), "<= 2.0", "", ("xtal", "R50"))
    ry = [n for n in nets_of("R50") if n != rx][0]
    e1, _ = dist("R50", ry, "Y1", "3")
    rec(e1 <= 5.0, "xtal", "OSC_XOUT_X lower bound R50.%s -> Y1.3 (length rule <= 5 mm)" % ry, "%.2f" % e1, "<= 5.0")
    for yp, pin in (("1", "21"), ("2", "20")):
        e, c = dist("Y2", yp, "U9", pin)
        rec(e <= 4.0, "xtal", "Y2.%s -> U9.%s" % (yp, pin), "%.2f (centre %.2f)" % (e, c), "<= 4.0", "",
            ("xtal", "Y2"))
    for cap, yref, yp in (("C77", "Y1", "1"), ("C76", "Y1", "3"), ("C79", "Y2", "1"), ("C78", "Y2", "2")):
        e, c = dist(cap, "1", yref, yp)
        rec(e <= 2.0, "xtal", "%s.1 -> %s.%s (load cap)" % (cap, yref, yp), "%.2f (centre %.2f)" % (e, c), "<= 2.0")
    e, c = dist("TP6", "1", "U9", "69")
    rec(c <= 5.0, "xtal", "TP6 -> U9.69 (centre)", "%.2f" % c, "<= 5.0", "", ("xtal", "TP6"))
    e, c = dist("TP6", "1", "R50", rx)
    rec(e <= 3.0, "xtal", "TP6 stub lower bound (TP6 -> R50.%s)" % rx, "%.2f (centre %.2f)" % (e, c), "<= 3.0")
    e2, _ = dist("R50", rx, "U9", "69")
    rec(e2 + e <= 8.0, "xtal", "OSC_XOUT lower bound: U9.69 -> R50 + TP6 stub (<= 8 mm incl. R51 in the row)",
        "%.2f" % (e2 + e), "<= 8.0")
    for yp, pin in (("1", "21"), ("2", "20")):
        e, c = dist("Y2", yp, "U9", pin)
        rec(e <= 6.0, "xtal", "RTC lower bound U9.%s -> Y2.%s (length rule <= 6 mm)" % (pin, yp), "%.2f" % e, "<= 6.0",
            "", ("xtal", "RTC_LEN"))
    e, c = dist("TP31", "1", "TP6", "1")
    rec(c <= 3.0, "xtal", "TP31 -> TP6 (centre)", "%.2f" % c, "<= 3.0")


CELLS = {  # IC: (inductor, cin10, cin100, fbt, fbb, cff, link, y-band)
    "U6": ("L3", "C9", "C14", "R22", "R15", "C31", "R30", (12, 21)),
    "U7": ("L4", "C10", "C15", "R18", "R16", "C32", "R31", (21, 30)),
    "U4": ("L1", "C7", "C12", "R17", "R13", "C29", "JP1", (30, 39)),
    "U5": ("L2", "C8", "C13", "R19", "R14", "C30", "R29", (39, 48)),
}


def check_bucks():
    for u, (L, c10, c100, fbt, fbb, cff, link, (ya, yb)) in CELLS.items():
        for c in (c100, c10):
            e, cc = dist(c, "1", u, "4")
            rec(e <= 1.0, "buck", "%s C_IN %s.1 -> %s.4 (VIN)" % (u, c, u), "%.2f (centre %.2f)" % (e, cc), "<= 1.0")
            e2, _ = dist(c, "2", u, "2")
            rec(e2 <= 1.0, "buck", "%s C_IN %s.2 -> %s.2 (GND side of the 1 mm rule)" % (u, c, u), "%.2f" % e2,
                "<= 1.0", "", ("buck", "CIN_GND"))
        e, cc = dist(L, "1", u, "3")
        rec(e <= 3.0, "buck", "%s inductor %s.1 -> %s.3 (SW)" % (u, L, u), "%.2f (centre %.2f)" % (e, cc), "<= 3.0")
        for p in (fbt, fbb, cff):
            pp = [n for n, nn in nets_of(p).items() if nn == u + "_FB"][0]
            e, cc = dist(p, pp, u, "5")
            rec(e <= 3.0, "buck", "%s divider %s.%s -> %s.5 (FB)" % (u, p, pp, u), "%.2f (centre %.2f)" % (e, cc),
                "<= 3.0")
        # divider tapped on the regulator side of the link: R_FBT top is on the *_BUCK net
        top = [nn for nn in nets_of(fbt).values() if nn != u + "_FB"][0]
        rec(top.endswith("_BUCK"), "buck", "%s divider on the regulator side of %s" % (u, link), top, "*_BUCK")
        x, y = bl.to_board(FP[u].GetPosition())
        rec(ya <= y <= yb, "buck", "%s cell band y %g-%g" % (u, ya, yb), "%.2f" % y, "%g-%g" % (ya, yb))
        lx, ly = bl.to_board(FP[link].GetPosition())
        rec(62.0 <= lx <= 65.0 and ya <= ly <= yb, "buck", "%s link %s in the x 62-65 strip" % (u, link),
            "(%.2f, %.2f)" % (lx, ly), "x 62-65")
        # cell order: VIN east of the IC, inductor west
        ix = bl.to_board(FP[u].GetPosition())[0]
        rec(bl.to_board(FP[c10].GetPosition())[0] > ix - 1.0 and bl.to_board(FP[L].GetPosition())[0] < ix, "buck",
            "%s input east / inductor west" % u, "ok", "layout.md §4.5")


def octi(a, b):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + 0.414 * min(dx, dy)


def check_power_misc():
    for c, p, u, up, lim in (("C11", "1", "U8", "5", 2.0), ("C34", "1", "U8", "1", 2.0), ("R37", "1", "U8", "3", 2.0),
                             ("R61", "1", "U8", "4", 2.0), ("C35", "1", "J4", "1", 5.0), ("C3", "1", "U3", "1", 2.0),
                             ("C6", "1", "U3", "7", 3.0), ("C21", "1", "Q4", "2", 2.0), ("C22", "1", "Q4", "3", 2.0)):
        e, cc = dist(c, p, u, up)
        rec(e <= lim, "power", "%s.%s -> %s.%s" % (c, p, u, up), "%.2f (centre %.2f)" % (e, cc), "<= %.1f" % lim)
    a = bl.to_board(pad("U8", "1").GetPosition())
    b = bl.to_board(pad("J4", "1").GetPosition())
    est = octi(a, b) * 1.2
    rec(est <= 15.0, "power", "VBUS_USBA U8.1 -> J4.1 (octilinear x 1.2 estimate)", "%.2f" % est, "<= 15.0")
    # input chain J1 -> F1 -> D1 -> Q1/U3, each <= 5 mm apart (edge)
    for a1, p1, a2, p2 in (("J1", "B4", "F1", "1"), ("F1", "2", "D1", "1"), ("F1", "2", "Q1", "2"),
                           ("F1", "2", "U3", "1")):
        e, cc = dist(a1, p1, a2, p2)
        lim = 5.0 if a2 != "U3" else 12.0
        rec(e <= lim, "power", "input chain %s.%s -> %s.%s" % (a1, p1, a2, p2), "%.2f (centre %.2f)" % (e, cc),
            "<= %.1f" % lim, "" if a2 != "U3" else "U3 is the on/off controller beside Q1; info limit")
    # SW1 next to U3: PB_IN = U3.2 -> R11.2, PWR_BTN_N = R11.1 -> SW1.1 (octilinear estimate)
    l1 = octi(bl.to_board(pad("U3", "2").GetPosition()), bl.to_board(pad("R11", "2").GetPosition()))
    l2 = octi(bl.to_board(pad("R11", "1").GetPosition()), bl.to_board(pad("SW1", "1").GetPosition()))
    rec(l1 <= 10.0, "power", "PB_IN U3.2 -> R11.2 (octilinear)", "%.2f" % l1, "<= 10.0")
    rec(l1 + l2 <= 12.0, "power", "SW1 next to U3: U3.2 -> R11 -> SW1.1 (octilinear)", "%.2f" % (l1 + l2), "<= 12.0")
    _, cc = dist("TP29", "1", "TP1", "1")
    rec(cc <= 10.0, "power", "TP29 -> TP1 (centre)", "%.2f" % cc, "<= 10.0")
    # ESD arrays at their connectors
    for u, ups, j, jps in (("U1", ("1", "3", "4", "6"), "J1", ("A6", "A7", "B6", "B7")),
                           ("U2", ("1", "3", "4", "6"), "J4", ("2", "3"))):
        best = min(dist(u, a, j, b)[0] for a in ups for b in jps)
        rec(best <= 3.0, "usb", "%s within 3 mm of %s data pins" % (u, j), "%.2f" % best, "<= 3.0")
    for c, p, u, up, lim in (("C84", "1", "U11", "10", 2.0), ("C81", "1", "U10", "8", 2.0), ("C80", "1", "U10", "8", 2.0),
                             ("R55", "2", "U10", "1", 2.0), ("C23", "1", "J2", "4", 2.0), ("C26", "1", "J2", "4", 2.0),
                             ("C82", "1", "J3", "4", 3.0), ("C83", "1", "J3", "5", 3.0)):
        e, cc = dist(c, p, u, up)
        rec(e <= lim, "local", "%s.%s -> %s.%s" % (c, p, u, up), "%.2f (centre %.2f)" % (e, cc), "<= %.1f" % lim, "",
            ("ring1", c))
    # layout.md §4.2 "R56-R59 ... <= 5 mm from J3": each link's own _J pad to its own J3 pin (same net, edge to edge;
    # verifier L2 r3: the nearest pair pin of any net hid R58)
    for r in ("R56", "R57", "R58", "R59"):
        jp = [p for p in FP[r].Pads() if p.GetNetname().endswith("_J")][0]
        own = [p for p in FP["J3"].Pads() if p.GetNetname() == jp.GetNetname()][0]
        e = bl.edge_dist(jp, own)
        rec(e <= 5.0, "local", "%s.%s (%s) -> own jack pin J3.%s (same net, edge)" % (r, jp.GetNumber(),
            jp.GetNetname(), own.GetNumber()), "%.2f" % e, "<= 5.0", "", ("local", r))
    # R12 bleeder >= 2 mm from other parts (courtyard gap)
    b = bbox_of("R12")
    near = []
    for ref in FP:
        if ref == "R12":
            continue
        o = bbox_of(ref)
        gx = max(o[0] - b[2], b[0] - o[2], 0)
        gy = max(o[1] - b[3], b[1] - o[3], 0)
        if math.hypot(gx, gy) < 2.0 - 0.5:   # courtyards include 0.25 mm each side: 1.5 mm courtyard gap = 2 mm body gap
            near.append(ref)
    rec(not near, "power", "R12 (53 mW) >= 2 mm body gap from other parts", len(near), 0, " ".join(near))


# ---------------------------------------------------------------------------------------------------------------
# U9 escape capacity (verifier L2 round 1, blocker): measured from the pads on the saved board
# ---------------------------------------------------------------------------------------------------------------
def u9_pin_table():
    out = {}
    for p in FP["U9"].Pads():
        n = p.GetNumber()
        if n and n != "129":
            x, y = bl.to_board(p.GetPosition())
            out[int(n)] = (x, y, p.GetNetname())
    return out


def pad_span(p, side):
    """(t0, t1, r0, r1) of a pad's copper on `side`."""
    pts = bl.pad_polygon(p)
    ts = [esc.t_of(side, x, y) for x, y in pts]
    rs = [esc.radial(side, x, y) for x, y in pts]
    return min(ts), max(ts), min(rs), max(rs)


def check_escape():
    """Per side: (1) every ring-1 part of the plan has its pad on the pin's net in the gate band (r 7.93-9.45 mm),
    facing the SoC, shifted sideways <= 1.45 mm (45 deg fan over the 1.45 mm fan band; up to 2.6 mm where only NC /
    same-net pins lie that way); (2) the via ring r 7.45 is free of ring-1 copper; (3) every LANE pin finds, in pin
    order, a gap between the gate copper with room for it at its class width + clearance (lanes do not cross the
    parts' links: monotone assignment), within 1.45 mm of its pin; (4) the vias of the VIA pins, the lanes and the
    links fit along the via ring in pin order (escape.via_ring_fit); (5) the band 1-2 mm beyond the gate has free
    width >= the lanes' demand; (6) XTAL lanes keep 1.27 mm (OSC) / 0.76 mm (RTC, D-104) from the diff-pair lanes.
    The distances are straight-line pad geometry: a lower bound, the L3 fan-out is the proof."""
    rules = esc.net_rules()
    pins = u9_pin_table()
    roles = esc.pin_roles(pins, rules)
    for p, role in roles.items():
        if role == "VIA":
            cls = rules[pins[p][2]][0]
            ok = cls in ("DEFAULT", "GND") or cls.startswith("PWR_")
            if not ok or str(p) in [k[1] for k in DEVIATIONS if k[0] == "escape"]:
                rec(ok, "escape", "pin %d %s (%s) drops to L4 at the via ring" % (p, pins[p][2], cls),
                    "L4", "§2.3 classes", "", ("escape", str(p)))
    part_of = {}
    for side, lst in esc.ROW_PARTS.items():
        for ref, served in lst:
            for p in served:
                part_of[p] = ref
    totals = collections.Counter()
    for side in "SENW":
        tc = esc.t_of(side, *esc.CENTRE)
        spins = sorted((p for p in pins if esc.side_of(p) == side), key=lambda p: esc.t_of(side, *pins[p][:2]))
        tpin = {p: esc.t_of(side, *pins[p][:2]) for p in spins}
        # gate copper (any non-U9 pad intersecting the gate band in front of the side)
        blocks = []
        ring_intrusions = []
        for ref, fp in FP.items():
            if ref == "U9":
                continue
            for p in fp.Pads():
                t0, t1, r0, r1 = pad_span(p, side)
                if t1 < tc - 9.6 or t0 > tc + 9.6:
                    continue
                if r1 >= esc.GATE[0] - 0.02 and r0 <= esc.GATE[1]:
                    blocks.append([t0, t1, ref, p.GetNetname(), r0])
                if r0 < esc.ROW_INNER - 0.02 and r1 > esc.VIA_RING - 0.25 and abs((t0 + t1) / 2 - tc) < 7.45:
                    ring_intrusions.append(ref)
        rec(not ring_intrusions, "escape", "%s: via ring r 7.20-7.90 free of part copper" % side, len(ring_intrusions),
            0, " ".join(sorted(set(ring_intrusions))))
        blocks.sort()
        merged = []
        for b in blocks:
            if merged and b[0] <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], b[1])
                merged[-1][2].append((b[2], b[3]))
            else:
                merged.append([b[0], b[1], [(b[2], b[3])]])
        gaps = []
        prev = tc - 9.6
        for m in merged:
            gaps.append([prev, m[0]])
            prev = m[1]
        gaps.append([prev, tc + 9.6])
        # (1) ring-1 parts: facing pad in the gate, shift
        sep = {}
        n05 = nall = 0
        for ref, served in esc.ROW_PARTS[side]:
            net = pins[served[0]][2]
            cand = [b for b in blocks if b[2] == ref and b[3] == net]
            if not cand:
                rec(False, "escape", "%s: %s has no pad on %s in the gate band" % (side, ref, net), "missing", "in gate")
                continue
            b = cand[0]
            tpad = (b[0] + b[1]) / 2
            facing = all(b[4] <= o[4] + 1e-6 for o in blocks if o[2] == ref)
            shift = min(abs(tpad - tpin[p]) for p in served)
            pnear = min(served, key=lambda p: abs(tpad - tpin[p]))
            # crosses only NC / same-net pins?
            lo, hi = sorted((tpad, tpin[pnear]))
            crossed = [q for q in spins if lo + 0.2 < tpin[q] < hi - 0.2 and pins[q][2] and pins[q][2] != net]
            lim = esc.FAN_REACH if crossed else esc.NC_REACH
            nall += 1
            n05 += shift <= 0.5 + 1e-6
            rec(facing and shift <= lim + 1e-6, "escape", "%s: %s pad on %s faces pin %d, sideways shift" %
                (side, ref, net, pnear), "%.2f%s" % (shift, "" if facing else " NOT FACING"), "<= %.2f" % lim,
                "crosses only NC/same-net pins" if not crossed else ("pins in front: %s" % " ".join(map(str, crossed))
                                                                     if shift > 0.5 else ""))
            for p in served:
                sep[p] = next(i for i, m in enumerate(merged) if any(r == ref for r, _n in m[2]))
        rec(True, "escape", "%s: ring-1 parts within 0.5 mm of their pin (verifier target; D-104)" % side,
            "%d of %d" % (n05, nall), "info")
        # (3) lanes, monotone over the gaps
        gi = 0
        used = {}
        last_pos = {}
        lane_pos = {}
        fails = []
        last_part = {}
        for p in spins:
            role = roles[p]
            seq = []
            if role == "LANE" or (role == "PART" and p in esc.THRU_LANES):
                seq.append("lane")
            if role == "PART":
                seq.append("part")
            for kind in seq:
                if kind == "part":
                    k = sep.get(p)
                    if k is None:
                        continue
                    if gi > k + 1 or (gi == k + 1 and last_part.get("k") != k):
                        fails.append("pin %d: its part sits before lanes already placed (crossing)" % p)
                    gi = max(gi, k + 1)
                    last_part["k"] = k
                    continue
                net = pins[p][2]
                w, c = esc.lane_wc(net, rules, p in esc.PAIRS)
                t = tpin[p] if p not in esc.PAIRS else (tpin[p] + tpin[esc.PAIRS[p]]) / 2
                placed = False
                while gi < len(gaps):
                    g0, g1 = gaps[gi]
                    start = last_pos.get(gi)
                    pair = p in esc.PAIRS
                    if start is not None:
                        cc = esc.PAIR_PAIR_CLEAR if (pair and used[gi][2]) else max(c, used[gi][1])
                    reach = esc.PAIR_REACH if pair else esc.FAN_REACH
                    pos = max(g0 + c + w / 2 if start is None else start + cc + used[gi][0] / 2 + w / 2,
                              t - reach)
                    if pos <= min(g1 - c - w / 2, t + reach) + 1e-9:
                        last_pos[gi] = pos
                        used[gi] = (w, c, pair)
                        lane_pos[p] = (pos, w, c, gi)
                        placed = True
                        break
                    if g0 > t + esc.FAN_REACH:
                        break
                    gi += 1
                if not placed:
                    fails.append("pin %d %s: no gap with room within %.2f mm" % (p, net, esc.FAN_REACH))
        nl = len(lane_pos)
        rec(not fails, "escape", "%s: %d lanes pass the gate between ring-1 parts at class width/clearance" % (side, nl),
            "%d unplaced" % len(fails), 0, "; ".join(fails[:4]))
        per_gap = collections.defaultdict(list)
        for p, (pos, w, c, g) in lane_pos.items():
            per_gap[g].append(p)
        desc = []
        for g in sorted(per_gap):
            g0, g1 = gaps[g]
            need = sum(esc.lane_wc(pins[q][2], rules, q in esc.PAIRS)[0] + esc.lane_wc(pins[q][2], rules,
                       q in esc.PAIRS)[1] for q in per_gap[g]) + max(esc.lane_wc(pins[q][2], rules, q in esc.PAIRS)[1]
                                                                   for q in per_gap[g])
            desc.append("pins %s: gap %.2f mm, need %.2f" % (",".join(map(str, sorted(per_gap[g]))),
                                                            min(g1, tc + 7.45) - max(g0, tc - 7.45), need))
        rec(True, "escape", "%s: gaps used (width inside |t| <= 7.45 / demand)" % side, len(per_gap), "info",
            "; ".join(desc))
        # (4) via ring
        seq = []
        for p in spins:
            role = roles[p]
            if role == "VIA":
                seq.append((str(p), "via", tpin[p], tpin[p]))
            if role == "LANE" or (role == "PART" and p in esc.THRU_LANES):
                if p in lane_pos:
                    seq.append((str(p), "lane", tpin[p], lane_pos[p][0]))
            if role == "PART" and p in sep:
                ref = part_of[p]
                b = [b for b in blocks if b[2] == ref and b[3] == pins[p][2]][0]
                seq.append((str(p), "link", tpin[p], (b[0] + b[1]) / 2))
        ok, _pos, bad = esc.via_ring_fit(seq, tc - 7.45, tc + 7.45)
        nv = sum(1 for q in seq if q[1] == "via")
        rec(ok, "escape", "%s: %d via-ring vias + lanes + links fit along r 7.45 in pin order" % (side, nv),
            "fits" if ok else "fails at pin %s" % bad, "fits")
        # (5) beyond the gate
        demand = sum(lane_pos[p][1] + lane_pos[p][2] for p in lane_pos)
        occ = []
        for ref, fp in FP.items():
            if ref == "U9":
                continue
            for p in fp.Pads():
                t0, t1, r0, r1 = pad_span(p, side)
                if r1 >= 9.65 and r0 <= 11.65 and t1 > tc - 7.45 and t0 < tc + 7.45:
                    occ.append((max(t0, tc - 7.45), min(t1, tc + 7.45)))
        occ.sort()
        cov, cur = 0.0, None
        for a, b in occ:
            if cur is None or a > cur[1]:
                if cur:
                    cov += cur[1] - cur[0]
                cur = [a, b]
            else:
                cur[1] = max(cur[1], b)
        if cur:
            cov += cur[1] - cur[0]
        free = 14.9 - cov
        rec(free >= demand, "escape", "%s: free width 1-2 mm beyond the gate >= lane demand" % side,
            "%.2f free / %.2f" % (free, demand), ">= demand")
        # (6) XTAL lanes vs pair lanes
        for p, (pos, w, c, g) in lane_pos.items():
            if rules[pins[p][2]][0] != "XTAL":
                continue
            for q, (pq, wq, cq, gq) in lane_pos.items():
                if q in esc.PAIRS:
                    d = abs(pos - pq) - w / 2 - wq / 2
                    lim = 0.76 if pins[p][2].startswith("RTC") else 1.27
                    rec(d >= lim - 1e-6, "escape", "%s: %s lane to the %s pair lane at the gate" % (side, pins[p][2],
                        pins[q][2]), "%.2f" % d, ">= %.2f" % lim, "RTC: D-104" if lim < 1 else "")
        totals[side] = nl


# ---------------------------------------------------------------------------------------------------------------
# verifier L2 round 2: SD corridor, NT1 clearance, trial route of the critical nets
# ---------------------------------------------------------------------------------------------------------------
def check_sd_corridor():
    """D-105: the SDMMC bus (pins 11-18 and R48) turns west right under the south ring-1 row. Free height between
    the lowest ring-1 pad over x 26-35.6 and the crystal guard (1 mm around the pads of Y2/C78/C79, layout.md §4.3) must
    be >= 2.4 mm (verifier L2 r2: 4 SDMMC lanes at 0.15/0.20 mm + edge clearances = 1.70 mm, + C64's GND via)."""
    x0, x1 = 26.0, 35.6
    row_bottom = 0.0
    for ref, _pins in esc.ROW_PARTS["S"]:
        for p in FP[ref].Pads():
            pts = bl.pad_polygon(p)
            if max(q[0] for q in pts) >= x0 and min(q[0] for q in pts) <= x1:
                row_bottom = max(row_bottom, max(q[1] for q in pts))
    guard_top = 99.0
    who = ""
    for ref in ("Y2", "C78", "C79"):
        for p in FP[ref].Pads():
            pts = bl.pad_polygon(p)
            if max(q[0] for q in pts) + 1.0 >= x0 and min(q[0] for q in pts) - 1.0 <= x1:
                top = min(q[1] for q in pts) - 1.0
                if top < guard_top:
                    guard_top, who = top, "%s.%s" % (ref, p.GetNumber())
    gap = guard_top - row_bottom
    rec(gap >= 2.4, "sd", "SDMMC corridor under the S row (row pad bottom %.2f -> %s guard %.2f)" % (row_bottom, who,
        guard_top), "%.2f" % gap, ">= 2.40", "lanes need 1.70 mm + C64 GND via; the trial route below is the proof")


def check_nt1():
    """NT1 (net tie VDD_ARM/VDD_0V9, pin 115) has no courtyard, so the DRC courtyard test skips it: its pads keep
    >= 0.20 mm from every other part's pads and stay out of every other courtyard."""
    worst, wref = 99.0, ""
    inside = []
    for p in FP["NT1"].Pads():
        pp = bl.pad_polygon(p)
        xs = [q[0] for q in pp]
        ys = [q[1] for q in pp]
        for ref, fp in FP.items():
            if ref == "NT1":
                continue
            bb = bl.courtyard_bbox(fp)
            if bb and min(xs) < bb[2] and max(xs) > bb[0] and min(ys) < bb[3] and max(ys) > bb[1]:
                if ref != "U9":
                    inside.append(ref)
            for q in fp.Pads():
                if q.GetNetname() and q.GetNetname() == p.GetNetname():
                    continue
                d = bl.poly_dist(pp, bl.pad_polygon(q))
                if d < worst:
                    worst, wref = d, "%s.%s %s" % (ref, q.GetNumber(), q.GetNetname())
    rec(worst >= 0.20, "nt1", "NT1 pads to the nearest other-net pad (%s)" % wref, "%.2f" % worst, ">= 0.20")
    rec(not inside, "nt1", "NT1 pads outside other parts' courtyards (U9 excepted: the tie sits at pin 115)",
        len(set(inside)), 0, " ".join(sorted(set(inside))))


TRIAL = {}


def check_trial():
    """Trial route of the critical nets (scripts/trial_route.py + maze_route.py, D-107): every SDMMC, FSPI, USB,
    ETH, ETH_CT and XTAL net (and SDMMC_DET) must route at its class rules with the layer policy of D-106 (L1 only;
    L4 hops only for the USB swaps / pair crossing / USB-C join and the ETH TX crossing). Unrouted or clearance-
    conflicting nets are FAILs."""
    import trial_route as tr
    tag = os.environ.get("TRIAL_TAG")            # mutation tests: separate outputs, no render
    res = tr.run(bl.BOARD_FILE, policy=True, render=tag is None, tag=tag)
    TRIAL["policy"] = res
    nets = res["nets"]
    bad = [n for n, r in nets.items() if not r["ok"]]
    rec(not bad, "trial", "critical nets routed at their class rules (%d nets, layer policy D-106)" % len(nets),
        "%d unrouted/conflicting" % len(bad), 0, "; ".join("%s: %s%s" % (n, " ".join(nets[n]["missing"]),
                                                    " x " + " ".join(nets[n]["conflict_with"]) if nets[n].get(
                                                        "conflict_with") else "") for n in bad[:8]))
    l4 = sorted(n for n, r in nets.items() if r["l4"] > 0 or r["vias"])
    off = [n for n in l4 if n not in tr.L4_ALLOWED]
    rec(not off, "trial", "L4 / vias used only by the planned D-106 hops", " ".join(l4) or "none", "D-106 list",
        " ".join(off))
    for n in l4:
        r = nets[n]
        cls = res["geo_nets"][n]["cls"]
        lim = 4 if cls == "USB_DIFF" else 2 if cls == "ETH_DIFF" else 99      # supply nets (VCC3V3_SD): no limit
        rec(len(r["vias"]) <= lim, "trial", "%s vias / L4 length" % n, "%d / %.1f mm" % (len(r["vias"]), r["l4"]),
            "<= %d vias" % lim if lim < 99 else "info", "at " + " ".join("(%.1f, %.1f)" % tuple(v) for v in r["vias"]))
    # lengths (information: grid route, from the gate point; the U9 fan band adds ~1.5-2 mm)
    groups = collections.OrderedDict()
    for n, r in nets.items():
        groups.setdefault(res["geo_nets"][n]["cls"], []).append("%s %.1f" % (n, r["length"]))
    for cls, lst in groups.items():
        rec(True, "trial", "%s lengths (mm, trial grid route from the U9 gate)" % cls, len(lst), "info", ", ".join(lst))
    if tag:
        return
    with open(os.path.join(bl.PCB_DIR, "trial", "trial_summary.csv"), "w", encoding="utf-8") as fh:
        fh.write("net,class,routed,length_mm,vias,l4_mm,via_positions,conflict_with,missing\n")
        for n, r in nets.items():
            fh.write("%s,%s,%s,%.2f,%d,%.2f,%s,%s,%s\n" % (n, res["geo_nets"][n]["cls"], "yes" if r["ok"] else "NO",
                     r["length"], len(r["vias"]), r["l4"], " ".join("%.2f/%.2f" % tuple(v) for v in r["vias"]),
                     " ".join(r.get("conflict_with", [])), " ".join(r["missing"])))


# ---------------------------------------------------------------------------------------------------------------
# verifier L2 round 3: exact re-measurement of the trial route (segment / polygon geometry, no grid tolerance)
# ---------------------------------------------------------------------------------------------------------------
def _simplify(pts):
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) > 1e-9:
            out.append(b)
    if len(pts) > 1:
        out.append(pts[-1])
    return out


def _segs(res, net, layer):
    out = []
    for L, pts in res["nets"][net]["segs"]:
        if L != layer:
            continue
        pts = _simplify([tuple(p) for p in pts])
        if len(pts) == 1:
            out.append((pts[0], pts[0]))
        out += list(zip(pts, pts[1:]))
    return out


def _cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def _segseg(s, t):
    if _cross(s[0], s[1], t[0], t[1]):
        return 0.0
    return min(bl._seg_pt(*s[0], *t[0], *t[1]), bl._seg_pt(*s[1], *t[0], *t[1]), bl._seg_pt(*t[0], *s[0], *s[1]),
               bl._seg_pt(*t[1], *s[0], *s[1]))


def _seg_poly(s, poly):
    if len(poly) > 2 and (bl._inside(s[0][0], s[0][1], poly) or bl._inside(s[1][0], s[1][1], poly)):
        return 0.0
    n = len(poly)
    return min(_segseg(s, (poly[i], poly[(i + 1) % n])) for i in range(n))


def _pt_poly(p, poly):
    if len(poly) > 2 and bl._inside(p[0], p[1], poly):
        return 0.0
    n = len(poly)
    return min(bl._seg_pt(p[0], p[1], *poly[i], *poly[(i + 1) % n]) for i in range(n))


def check_trial_geometry():
    """Exact geometry of the trial route (the router enforces these rules with a margin larger than its grid error):
    (1) ETH TX vs RX separation >= 0.76 mm (layout.md §10, D-108 b): track-track per layer, via-track, track and via to
        the other pair's pads (J3 pins exempt: 2.54 mm jack pitch); (2) every trial via >= 0.15 mm (target 0.20) from
        other-net pads and outside the U11/U1/J1 no-via areas (D-108 a); (3) ETH P/N lengths across the 0R links and
        their skew (layout.md §4.2 <= 1.27 mm, tuned in L5); (4) SD card supply: VCC3V3_SD joins J2.4, C23.1, C26.1 on
        L1, no via between C23.1 and J2.4, and the pocket between the CLK_SD and CMD lines (D-108 c)."""
    import trial_route as tr
    res = TRIAL.get("policy")
    if not res:
        return
    nets = res["nets"]
    geo = res["geo_nets"]
    tx = [n for n in nets if tr.SEP_GROUP.get(n) == "ETH_TX"]
    rx = [n for n in nets if tr.SEP_GROUP.get(n) == "ETH_RX"]
    worst = (99.0, "")
    for a in tx:
        for b in rx:
            lim_off = geo[a]["w"] / 2 + geo[b]["w"] / 2
            for L in (0, 1):
                for s1 in _segs(res, a, L):
                    for s2 in _segs(res, b, L):
                        d = _segseg(s1, s2) - lim_off
                        if d < worst[0]:
                            worst = (d, "%s/%s track-track L%d near (%.2f, %.2f)" % (a, b, 1 if L == 0 else 4,
                                                                                        s1[0][0], s1[0][1]))
            for (n1, n2) in ((a, b), (b, a)):
                for v in nets[n1]["vias"]:
                    for L in (0, 1):
                        for s2 in _segs(res, n2, L):
                            d = bl._seg_pt(v[0], v[1], *s2[0], *s2[1]) - 0.25 - geo[n2]["w"] / 2
                            if d < worst[0]:
                                worst = (d, "%s via (%.2f, %.2f) to %s track" % (n1, v[0], v[1], n2))
    # tracks / vias to the other group's pads
    gpads = []
    for ref, fp in FP.items():
        if ref in tr.SEP_PAD_EXEMPT:
            continue
        for p in fp.Pads():
            g = tr.SEP_GROUP.get(p.GetNetname())
            if g:
                gpads.append((g, "%s.%s" % (ref, p.GetNumber()), bl.pad_polygon(p)))
    for n in tx + rx:
        g = tr.SEP_GROUP[n]
        for g2, name, poly in gpads:
            if g2 == g:
                continue
            for s1 in _segs(res, n, 0):
                d = _seg_poly(s1, poly) - geo[n]["w"] / 2
                if d < worst[0]:
                    worst = (d, "%s track to %s pad %s" % (n, g2, name))
            for v in nets[n]["vias"]:
                d = _pt_poly(v, poly) - 0.25
                if d < worst[0]:
                    worst = (d, "%s via to %s pad %s" % (n, g2, name))
    rec(worst[0] >= 0.76 - 1e-3, "trial", "ETH TX vs RX separation, exact (tracks, vias, link pads; J3 pins exempt)",
        "%.3f" % worst[0], ">= 0.76", worst[1])
    # (2) vias to other-net pads and no-via areas
    allpads = [(p.GetNetname(), "%s.%s" % (ref, p.GetNumber()), bl.pad_polygon(p)) for ref, fp in FP.items()
               for p in fp.Pads() if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
    novia = {ref: bl.courtyard_bbox(FP[ref]) for ref in tr.NO_VIA_REFS}
    for n in sorted(nets):
        for v in nets[n]["vias"]:
            best = (99.0, "")
            for pn, name, poly in allpads:
                if pn == n or abs(poly[0][0] - v[0]) > 3 or abs(poly[0][1] - v[1]) > 3:
                    continue
                d = _pt_poly(v, poly) - 0.25
                if d < best[0]:
                    best = (d, "%s (%s)" % (name, pn))
            inside = [r for r, bb in novia.items() if bb[0] - 0.15 <= v[0] <= bb[2] + 0.15 and
                      bb[1] - 0.15 <= v[1] <= bb[3] + 0.15]
            rec(best[0] >= 0.15 and not inside, "trial", "%s via (%.2f, %.2f) to nearest other-net pad, no-via areas"
                % (n, v[0], v[1]), "%.3f" % best[0] if best[0] < 99 else "> 3", ">= 0.15 (target 0.20)",
                (best[1] or "no other-net pad within 3 mm") + (" INSIDE no-via area " + " ".join(inside) if inside else ""))
    # (3) ETH lengths across the links and skew (trial route from the U9 gate; + ~1.5 mm fan each line, equal per pair)
    for pair, p_, n_ in (("ETH_RX", "ETH_RXP", "ETH_RXN"), ("ETH_TX", "ETH_TXP", "ETH_TXN")):
        lp = nets[p_]["length"] + nets[p_ + "_J"]["length"]
        ln = nets[n_]["length"] + nets[n_ + "_J"]["length"]
        rec(abs(lp - ln) <= 1.27, "trial", "%s P/N lengths gate->J3 (P %.2f, N %.2f mm, + ~1.5 mm fan)" % (pair, lp, ln),
            "skew %.2f" % abs(lp - ln), "<= 1.27", "", ("trial", pair + "_SKEW"))
        # uncoupled length: P-line length (L1 and L4, both segments) farther than pitch + 0.3 mm from the N line
        pitch = geo[p_]["w"] + geo[p_]["gap"]
        nseg = [(L, s2) for nn in (n_, n_ + "_J") for L in (0, 1) for s2 in _segs(res, nn, L)]
        unc = 0.0
        for pp in (p_, p_ + "_J"):
            for L in (0, 1):
                for s1 in _segs(res, pp, L):
                    (ax, ay), (bx, by) = s1
                    ln_ = math.hypot(bx - ax, by - ay)
                    k = max(1, int(ln_ / 0.1))
                    for i in range(k):
                        t = (i + 0.5) / k
                        q = (ax + (bx - ax) * t, ay + (by - ay) * t)
                        d = min(bl._seg_pt(q[0], q[1], *s2[0], *s2[1]) for L2, s2 in nseg if L2 == L) if any(
                            L2 == L for L2, _ in nseg) else 99
                        if d > pitch + 0.3:
                            unc += ln_ / k
        rec(unc <= 5.0, "trial", "%s uncoupled length (P line > pitch + 0.3 mm from N; P/N swap at the links)" % pair,
            "%.2f" % unc, "<= 5.0", "", ("trial", pair + "_UNCOUPLED"))
        rec(max(lp, ln) + 1.5 <= 30.0, "trial", "%s longest line incl. fan (layout.md §4.2 <= 30 mm)" % pair,
            "%.2f" % (max(lp, ln) + 1.5), "<= 30.0", "tuning the short line to the long one keeps it <= 30")
    # (4) SD card supply
    if "VCC3V3_SD" in nets:
        r = nets["VCC3V3_SD"]
        c23 = bl.pad_polygon(pad("C23", "1"))
        j24 = bl.pad_polygon(pad("J2", "4"))
        ytop = min(q[1] for q in c23)
        bad_v = [v for v in r["vias"] if v[1] >= ytop and 16.0 <= v[0] <= 19.0]
        l1 = _segs(res, "VCC3V3_SD", 0)

        def touches(poly):
            return any(_seg_poly(s1, poly) < 1e-6 for s1 in l1)
        joined = touches(j24) and touches(c23) and touches(bl.pad_polygon(pad("C26", "1")))
        rec(r["ok"] and joined and not bad_v, "trial", "VCC3V3_SD: J2.4, C23.1, C26.1 on L1, no via between C23 and J2",
            "ok" if joined and not bad_v else "broken", "joined", "vias " + " ".join("(%.2f, %.2f)" % tuple(v) for v in
                                                                                       r["vias"]))
        # pocket: free width between the nearest other-net L1 tracks west and east of the VDD column (x 17.47)
        pk = res.get("sd_pocket")
        xc = bl.to_board(pad("J2", "4").GetPosition())[0]
        y0, y1 = pk[1], pk[3]
        west, east = -99.0, 99.0
        for m in nets:
            if m == "VCC3V3_SD":
                continue
            for s1 in _segs(res, m, 0):
                for k in range(0, 61):
                    y = y0 + (y1 - y0) * k / 60.0
                    (ax, ay), (bx, by) = s1
                    if min(ay, by) - 1e-9 <= y <= max(ay, by) + 1e-9:
                        x = ax if abs(by - ay) < 1e-9 else ax + (bx - ax) * (y - ay) / (by - ay)
                        hw = geo[m]["w"] / 2
                        if x < xc:
                            west = max(west, x + hw)
                        else:
                            east = min(east, x - hw)
        rec(east - west >= 0.9, "trial", "SD supply pocket between the other-net L1 tracks around J2.4/C23/C26 "
            "(y %.2f-%.2f)" % (y0, y1), "%.2f" % (east - west), ">= 0.90", "track edges x %.2f / %.2f" % (west, east))


def is_mlcc(ref):
    return ref.startswith("C") and FP[ref].GetFPID().GetLibItemName().wx_str().startswith("C_0")


def check_vcut():
    bad3, badpar = [], []
    for ref in FP:
        if not is_mlcc(ref):
            continue
        b = bbox_of(ref)
        fab = fab_bbox(ref)
        if fab[0] < 3.0 or fab[2] > 77.0:
            bad3.append(ref)
        if fab[0] < 5.0 or fab[2] > 75.0:
            rot = FP[ref].GetOrientationDegrees() % 180
            if abs(rot - 90) > 1e-3:
                badpar.append(ref)
    rec(not bad3, "vcut", "no MLCC body within 3 mm of x = 0 / 80", len(bad3), 0, " ".join(bad3))
    rec(not badpar, "vcut", "MLCCs within 5 mm of a V-cut parallel to it", len(badpar), 0, " ".join(badpar))


def check_zone_fill():
    """layout.md §5.1 capacity rule: courtyard area of the parts assigned to a zone <= 55 % of the zone."""
    area = collections.Counter()
    for ref, row in PL.items():
        if row["zone"] not in ZN or ref.startswith("J"):
            continue
        b = bbox_of(ref)
        area[row["zone"]] += (b[2] - b[0]) * (b[3] - b[1])
    for z, a in sorted(area.items()):
        r = zone_rect(z)
        za = (r[2] - r[0]) * (r[3] - r[1])
        rec(a / za <= 0.55 + 1e-9, "zonefill", "%s courtyard fill (bbox areas)" % z, "%.1f %%" % (100 * a / za), "<= 55 %",
            "", ("zonefill", z))


def run_drc():
    rep = os.path.join(bl.PCB_DIR, "drc_placement.json" if not os.environ.get("TRIAL_TAG") else
                       "trial/drc_%s.json" % os.environ["TRIAL_TAG"])
    subprocess.run([bl.KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", rep, bl.BOARD_FILE],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(rep, encoding="utf-8") as fh:
        d = json.load(fh)
    cnt = collections.Counter(v["type"] for v in d["violations"])
    for t in ("courtyards_overlap", "malformed_courtyard", "missing_courtyard", "missing_footprint",
              "extra_footprint", "duplicate_footprints", "footprint", "shorting_items"):
        rec(cnt.get(t, 0) == 0, "drc", t, cnt.get(t, 0), 0)
    # items off board: no pad / courtyard outside the panel outline (copper_edge_clearance on pads counts too)
    off = [v for v in d["violations"] if v["type"] == "copper_edge_clearance"]
    rec(not off, "drc", "copper_edge_clearance (pads too close to / off the board edge)", len(off), 0,
        "; ".join(v["items"][0]["description"] for v in off[:6]))
    rec(True, "drc", "unconnected items (expected before routing)", len(d["unconnected_items"]), "info")
    other = {k: (">= 199 (capped)" if v == 199 else v) for k, v in cnt.items()
             if k not in ("courtyards_overlap", "copper_edge_clearance", "shorting_items")}
    rec(True, "drc", "other DRC items (info; routing-phase or library-table messages)", json.dumps(other), "info")
    return d


def main():
    funcs = [check_netlist, check_zones, check_zone_fill, check_connectors, check_soc_rings, check_escape, check_xtal,
             check_bucks, check_power_misc, check_vcut, check_sd_corridor, check_nt1]
    if os.environ.get("NO_TRIAL") != "1":
        funcs += [check_trial, check_trial_geometry]
    for f in funcs:
        try:
            f()
        except MissingPad as e:
            rec(False, "pads", "%s stopped: missing pad %s" % (f.__name__, e), "missing", "present")
    run_drc()
    w = max(len(r[2]) for r in results)
    for st, rule, item, val, lim, note in results:
        print("%-4s %-9s %-*s %-22s %-10s %s" % (st, rule, w, item, val, lim, note))
    c = collections.Counter(r[0] for r in results)
    print("\nSUMMARY: %d checks: %d PASS, %d DEV (recorded deviations), %d FAIL" % (len(results), c["PASS"], c["DEV"],
                                                                               c["FAIL"]))
    sys.exit(1 if c["FAIL"] else 0)


if __name__ == "__main__":
    main()
