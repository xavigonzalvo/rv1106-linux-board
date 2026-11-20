#!/usr/bin/env python3
"""Layout phase L5G (re-review fixes, owner decision D-H7 "Yes, fix and accept", gate TP-L5G; decisions.md D-119..):
the copper changes, on the L5F board. Run by l5g_run.sh after l5f_run.sh (rebuild_all.sh); then fill_zones.py.

    $PY design/pcb/scripts/l5g_fix.py          # edits design/pcb/rv1106-reva.kicad_pcb; writes design/pcb/l5g/fix.json

1. U9 EP vias (D-H7 item 1, D-119): the 16 drilled pads "129" of the U9 footprint on the board (0.3 mm holes that
   export as their own ComponentDrill tool) are removed (the 7.0 mm EP copper, its F.Mask and the 3 x 3 paste
   windowpane stay); 16 GND board vias 0.5 / 0.3 (the via class) take their centres. Board setup: via filling + capping
   (IPC-4761 type VII), which POFV needs for the in-pad vias.
2. SD clock (item 3, D-121): SDMMC_CLK_SD leaves R48.2 at x 33.71 (was 33.83) and the bus opens south-east of it:
   the CLK horizontal / diagonal move 0.095 mm south-east, SDMMC_CMD / D3 / D2 0.19 mm, and below R48 CMD / D3 / D2
   jog 45 deg west (staggered at y 46.25 / 46.37 / 46.50) to x 34.165 / 34.52 / 34.875. D1 / D0 stay (SDMMC_DET runs
   0.265 mm north of D1). CLK pitch to D0 and CMD 0.455 mm = 0.305 mm edge gap; the J2 ends and the U9 escape above
   the cuts are unchanged.
3. RTC crystal (item 4, D-122; round 2 D-128, a recorded small local move under D-H5): C58 (AVDD1V8_USB 100 nF,
   pin 24) moves 0.176 mm east and 0.25 mm north ((36.71, 45.19) -> (36.886, 44.94); 0.1525 mm from USB_DM, class
   0.15); its C58.1 in-pad via and the L1 AVDD1V8_USB end follow, the L4 run to R33.2 gets a 45 deg piece; its GND via
   goes into the C58.2 pad (POFV, via_in_pad.csv) instead of the dog-bone via at (36.876, 46.288). The R48 / C58
   channel is re-drawn from the U9 pin row (y 43.0) down: SDMMC_CMD / D3 / D2 at x 34.39 / 34.745 / 35.101 (CMD
   0.165 mm from R48, was 0.147; the lane check keeps a free grid column at 34.75), jogging 45 deg west at
   y 46.25 / 46.42 / 46.58 to 34.165 / 34.52 / 34.875; RTC_XOUT at x 35.751 (0.50 mm from D2), at y 46.90 to 35.555
   and from (35.555, 49.565) at 45 deg into Y2.2; RTC_XIN at x 36.201 (0.30 mm from XOUT and from C58), at y 45.87 to
   36.41 (0.51 mm from XOUT), at y 48.15 back to 36.21 (USB_DM hop via, DRU 0.76 mm) and down to Y2.1.
   RTC_XOUT >= 0.5 mm from SDMMC_D2 everywhere (pin escape included); XIN-XOUT < 0.5 mm only from the escape to
   y ~46.3 (< 2.0 mm).
4. J5.2 -> J5.4 B.Cu 5 V link (item 5, D-123) runs pad centre to pad centre.
5. J1 shell GND vias (item 6, D-124) moved 0.07 mm away from the shell slots (hole edge 0.47 mm), their F.Cu stub
   follows.
6. In2 GND hop islands (item 7, D-125): a second GND via in In2_GND_HOP_3 (50.75, 74.10), HOP_1 (37.30, 50.80)
   and HOP_2 (37.65, 58.20) (each had one).
7. Q1 drain (item 8, D-126): two more VCC5V0_SYS plane vias on the Q1.3 drain, each with a 0.5 mm F.Cu stub to the
   pad (5 in all).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

GROUP = "L5G_FIX"
OUT = os.path.join(bl.PCB_DIR, "l5g", "fix.json")
DELTA = 0.095                 # SD bus shift either side of the clock (mm, perpendicular)
K = DELTA * math.sqrt(2)      # the same shift on the x + y = c diagonals
# SD nets: (side -1 = north-west / +1 = south-east, cut y on the old line, new vertical x below the cut or None,
#           J2 end point y)
# SD nets moved: (shift south-east in units of DELTA, cut y on the old vertical, new vertical x below the cut,
#                 J2 end point y). D1 / D0 stay (SDMMC_DET runs 0.265 mm north of D1, no room north); the jogs are
#                 staggered 0.12 mm so the parallel 45 deg pieces keep >= 0.2 mm
SD = {"SDMMC_CMD": (2, 46.25, 34.165, 64.13), "SDMMC_D3": (2, 46.37, 34.52, 64.88),
      "SDMMC_D2": (2, 46.50, 34.875, 64.88)}
CLK_X = 33.71
J1_VIAS = {(45.647, 71.957): (45.685, 71.899), (53.353, 71.957): (53.315, 71.899)}
# D-121: a GND stitching via of the F.Cu pour 0.18 mm from the moved SDMMC_D2 diagonal, moved 0.14 mm south-east
# (round 2, D-128: the C58.2 dog-bone GND via (36.876, 46.288) is replaced by a via in the C58.2 pad, see channel())
STITCH_MOVES = {(23.872, 53.417): (23.972, 53.517)}
# D-128 (round 2): C58 0.176 mm east / 0.25 mm north; the channel nets re-drawn from the pin row (y 43.0, end of the pin stubs) down to
# the kept copper (the bus horizontals, the Y2 pad pieces). (net, box of the replaced pieces x0, y0, x1, y1, new path,
# first-piece width): the first piece (pin stub end -> y 44.375, inside the U9_FAN neck-down area) is 0.10 mm wide
C58_DX, C58_DY = 0.176, -0.25        # C58 0.176 mm east (USB_DM 0.1525 mm, class 0.15) and 0.25 mm north
# x positions (nm-exact): the U9 lane check (lanecheck.py, 0.05 mm grid, class width + 0.20 mm) needs a free grid column
# at x 34.75 between CMD and D2 (CMD <= 34.40, D2 >= 35.10); XOUT = D2 + 0.65 (0.50 mm), XIN = XOUT + 0.45 (0.30 mm),
# C58 west edge = XIN + 0.375 (XTAL 0.30 mm)
CHANNEL = [
    ("SDMMC_CMD", (34.10, 43.0, 34.50, 48.58), [(34.325, 43.0), (34.39, 44.375), (34.39, 46.25), (34.165, 46.475),
                                                (34.165, 48.58)]),
    ("SDMMC_D3", (34.45, 43.0, 34.85, 48.94), [(34.675, 43.0), (34.745, 44.375), (34.745, 46.42), (34.52, 46.645),
                                               (34.52, 48.94)]),
    ("SDMMC_D2", (34.80, 43.0, 35.20, 49.30), [(35.025, 43.0), (35.101, 44.375), (35.101, 46.58), (34.875, 46.806),
                                               (34.875, 49.30)]),
    ("RTC_XOUT", (33.60, 43.0, 35.80, 51.30), [(35.725, 43.0), (35.751, 44.375), (35.751, 46.90), (35.555, 47.096),
                                               (35.555, 49.565), (33.85, 51.27)]),
    ("RTC_XIN", (35.90, 43.0, 36.45, 51.30), [(36.075, 43.0), (36.201, 44.375), (36.201, 45.87), (36.41, 46.079),
                                              (36.41, 48.15), (36.21, 48.35), (36.21, 51.30)]),
]
OLD_C58_GND_VIA = (36.876, 46.288)
U9_LIB = "RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm_EPboardvias"
# D-125: one more GND via in each In2 GND hop island that had one (sites from a clearance search, DRC-checked)
HOP_VIAS = [(50.75, 74.10), (37.30, 50.80), (37.65, 58.20)]
Q1_VIAS = [((60.50, 65.10), (60.50, 66.30)), ((59.25, 66.30), (60.34, 66.30))]   # (via, F.Cu stub end on Q1.3)
J5_LINK = ((5.54, 9.56), (5.54, 12.10))
LOG = []
# removed board items stay referenced until the script ends: a removed track whose Python proxy is garbage-collected
# is freed while its old group still points at it, which corrupts the board's item lists (seen in round 2)
KEEP = []


def segs(board, net, layer=pcbnew.F_Cu):
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net and t.GetLayer() == layer:
            out.append((bl.to_board(t.GetStart()), bl.to_board(t.GetEnd()), t))
    return out


def new_track(board, net, a, b, w, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(board)
    t.SetLayer(layer)
    t.SetWidth(pcbnew.FromMM(w))
    t.SetStart(bl.to_page(*a))
    t.SetEnd(bl.to_page(*b))
    t.SetNet(board.FindNet(net))
    board.Add(t)
    return t


def new_via(board, net, p):
    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(bl.to_page(*p))
    v.SetWidth(pcbnew.FromMM(0.5))
    v.SetDrill(pcbnew.FromMM(0.3))
    v.SetNet(board.FindNet(net))
    board.Add(v)
    return v


def cut_and_strip(board, net, cut_y, keep_below):
    """truncate the segment that crosses y = cut_y at the crossing (keeps the upper part) and remove every segment
    lying at y >= cut_y, except those with min y >= keep_below (the pad-end pieces kept). Returns the cut point."""
    pt, dead = None, []
    for a, b, t in segs(board, net):
        lo, hi = (a, b) if a[1] <= b[1] else (b, a)
        if lo[1] < cut_y - 1e-6 < hi[1] - 2e-6:
            f = (cut_y - lo[1]) / (hi[1] - lo[1])
            pt = (lo[0] + (hi[0] - lo[0]) * f, cut_y)
            if a[1] <= b[1]:
                t.SetEnd(bl.to_page(*pt))
            else:
                t.SetStart(bl.to_page(*pt))
        elif lo[1] >= cut_y - 1e-6 and lo[1] < keep_below - 1e-6:
            dead.append(t)
    for t in dead:
        KEEP.append(t)
        board.Remove(t)
    return pt, len(dead)


def diag_c(board, net):
    """x + y of the long 45 deg diagonal of an SD line (the bus runs south-west at 45 deg)"""
    best = None
    for a, b, _t in segs(board, net):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 5 and abs(abs(b[0] - a[0]) - abs(b[1] - a[1])) < 0.01 and (b[0] - a[0]) * (b[1] - a[1]) < 0:
            if best is None or L > best[0]:
                best = (L, a[0] + a[1])
    return best[1]


def horiz_y(board, net):
    best = None
    for a, b, _t in segs(board, net):
        L = abs(b[0] - a[0])
        if abs(b[1] - a[1]) < 1e-4 and L > 4 and a[1] > 46.5:
            if best is None or L > best[0]:
                best = (L, a[1])
    return best[1]


def path(board, net, pts, w, items):
    for a, b in zip(pts, pts[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-4:
            items.append(new_track(board, net, a, b, w))
    LOG.append("%s: %s" % (net, " -> ".join("(%.4f, %.4f)" % p for p in pts)))


def jog(p, x):
    return (x, p[1] + abs(x - p[0]))


def move_end(board, old, new, net):
    n = 0
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        if t.GetClass() == "PCB_VIA":
            if math.hypot(*(c - o for c, o in zip(bl.to_board(t.GetPosition()), old))) < 0.003:
                t.SetPosition(bl.to_page(*new))
                n += 1
            continue
        if math.hypot(*(c - o for c, o in zip(bl.to_board(t.GetStart()), old))) < 0.003:
            t.SetStart(bl.to_page(*new))
            n += 1
        if math.hypot(*(c - o for c, o in zip(bl.to_board(t.GetEnd()), old))) < 0.003:
            t.SetEnd(bl.to_page(*new))
            n += 1
    return n


def channel(board, items):
    """D-128 (round 2): C58 0.176 mm east / 0.25 mm north, C58.2 GND via in the pad, the R48 / C58 channel re-drawn (CHANNEL)"""
    c58 = board.FindFootprintByReference("C58")
    x, y = bl.to_board(c58.GetPosition())
    p1 = [bl.to_board(p.GetPosition()) for p in c58.Pads() if p.GetNumber() == "1"][0]
    c58.SetPosition(bl.to_page(x + C58_DX, y + C58_DY))
    p1n = (round(p1[0] + C58_DX, 4), round(p1[1] + C58_DY, 4))
    n = move_end(board, p1, p1n, "AVDD1V8_USB")
    LOG.append("C58 (%.3f, %.3f) -> (%.3f, %.3f); C58.1 in-pad via + %d AVDD1V8_USB ends -> (%.3f, %.3f)" % (
        x, y, x + C58_DX, y + C58_DY, n, p1n[0], p1n[1]))
    # the L4 (B.Cu) AVDD1V8_USB run C58.1 -> R33.2 stays horizontal at its old y: a 45 deg piece from the moved via
    for a, b, t in segs(board, "AVDD1V8_USB", pcbnew.B_Cu):
        for end, other, setter in ((a, b, t.SetStart), (b, a, t.SetEnd)):
            if math.hypot(end[0] - p1n[0], end[1] - p1n[1]) < 0.003 and abs(other[1] - p1[1]) < 0.003:
                k = (round(p1n[0] + abs(p1[1] - p1n[1]), 4), round(p1[1], 4))
                setter(bl.to_page(*k))
                items.append(new_track(board, "AVDD1V8_USB", p1n, k, pcbnew.ToMM(t.GetWidth()), pcbnew.B_Cu))
                LOG.append("  L4 AVDD1V8_USB: 45 deg piece (%.3f, %.3f)-(%.3f, %.3f), run from (%.3f, %.3f)" % (
                    p1n + k + k))
    # the C58.2 dog-bone GND via and its stub -> a GND via in the C58.2 pad
    dead = []
    for t in board.GetTracks():
        if t.GetNetname() != "GND":
            continue
        if t.GetClass() == "PCB_VIA":
            if math.hypot(*(c - o for c, o in zip(bl.to_board(t.GetPosition()), OLD_C58_GND_VIA))) < 0.01:
                dead.append(t)
        elif any(math.hypot(*(c - o for c, o in zip(bl.to_board(q), OLD_C58_GND_VIA))) < 0.01
                 for q in (t.GetStart(), t.GetEnd())):
            dead.append(t)
    assert len(dead) == 2, [(t.GetClass(), bl.to_board(t.GetStart())) for t in dead]
    for t in dead:
        KEEP.append(t)
        board.Remove(t)
    p2 = [bl.to_board(p.GetPosition()) for p in c58.Pads() if p.GetNumber() == "2"][0]
    items.append(new_via(board, "GND", (round(p2[0], 4), round(p2[1], 4))))
    LOG.append("C58.2 GND: dog-bone via (%.3f, %.3f) + stub removed, via in the pad at (%.3f, %.3f)" % (
        OLD_C58_GND_VIA + p2))
    for net, box, pts in CHANNEL:
        old = []
        for a, b, t in segs(board, net):
            if all(box[0] - 1e-4 <= q[0] <= box[2] + 1e-4 and box[1] - 1e-4 <= q[1] <= box[3] + 1e-4 for q in (a, b)):
                old.append(t)
        for t in old:
            KEEP.append(t)
            board.Remove(t)
        w = 0.15
        items.append(new_track(board, net, pts[0], pts[1], 0.10))
        path(board, net, pts[1:], w, items)
        LOG.append("  %s: %d pieces replaced" % (net, len(old)))


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, GROUP)
    items = []
    # 1. EP vias
    u9 = board.FindFootprintByReference("U9")
    drilled = [p for p in u9.Pads() if p.GetNumber() == "129" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    assert len(drilled) == 16, len(drilled)
    centres = sorted((round(bl.to_board(p.GetPosition())[0], 3), round(bl.to_board(p.GetPosition())[1], 3))
                     for p in drilled)
    for p in drilled:
        KEEP.append(p)
        u9.Remove(p)
    for c in centres:
        items.append(new_via(board, "GND", c))
    # D-129 (round 2): U9 points at the board.pretty variant without the drilled pads (make_footprints.py), so the board
    # copy equals its library footprint and "update footprints from library" cannot bring the drilled pads back
    lib = pcbnew.FootprintLoad(os.path.join(bl.PCB_DIR, "board.pretty"), U9_LIB)
    u9.SetFPID(pcbnew.LIB_ID("board", U9_LIB))
    u9.SetLibDescription(lib.GetLibDescription())
    ds = board.GetDesignSettings()
    ds.m_FillVias = True
    ds.m_CapVias = True
    LOG.append("EP: 16 drilled pads removed from U9, 16 GND vias 0.5/0.3 at %s; board via filling + capping on"
               % centres)
    # 2. SD bus
    geo = {n: (horiz_y(board, n), diag_c(board, n)) for n in SD}
    geo["SDMMC_CLK_SD"] = (horiz_y(board, "SDMMC_CLK_SD"), diag_c(board, "SDMMC_CLK_SD"))
    j2 = {p.GetNetname(): bl.to_board(p.GetPosition()) for p in board.FindFootprintByReference("J2").Pads()}
    for net, (side, cut, xv, yend) in SD.items():
        yh, c = geo[net]
        yh2, c2 = yh + side * DELTA, c + side * K
        start, nd = cut_and_strip(board, net, cut, yend)
        xp = 18.82 if net == "SDMMC_CMD" else j2[net][0]     # CMD: its vertical, then the kept jog into J2.3
        pts = [start]
        if xv is not None:
            pts.append(jog(start, xv))
            pts.append((xv, yh2))
        pts += [(c2 - yh2, yh2), (xp, c2 - xp), (xp, yend)]
        path(board, net, pts, 0.15, items)
        LOG.append("  %s: removed %d pieces, horizontal y %.3f -> %.3f, diagonal x+y %.4f -> %.4f" % (
            net, nd, yh, yh2, c, c2))
    yh, c = geo["SDMMC_CLK_SD"]
    _s, nd = cut_and_strip(board, "SDMMC_CLK_SD", 45.72, 64.88)
    r48 = bl.to_board([p for p in board.FindFootprintByReference("R48").Pads() if p.GetNumber() == "2"][0].GetPosition())
    xp = j2["SDMMC_CLK_SD"][0]
    yh, c = yh + DELTA, c + K
    pts = [r48, jog(r48, CLK_X), (CLK_X, yh), (c - yh, yh), (xp, c - xp), (xp, 64.88)]
    path(board, "SDMMC_CLK_SD", pts, 0.15, items)
    # 3. C58 move + R48 / C58 channel (SD CMD / D3 / D2, RTC crystal), round 2 (D-128)
    channel(board, items)
    # 4. J5.2 link
    for a, b, t in segs(board, "VCC5V0_SYS", pcbnew.B_Cu):
        if abs(a[0] - 5.30) < 0.01 and abs(b[0] - 5.30) < 0.01 and min(a[1], b[1]) > 10.0 and max(a[1], b[1]) < 11.0:
            t.SetStart(bl.to_page(*J5_LINK[0]))
            t.SetEnd(bl.to_page(*J5_LINK[1]))
            LOG.append("J5.2-J5.4 link (%.2f,%.2f)-(%.2f,%.2f) -> (%.2f,%.2f)-(%.2f,%.2f)" % (a + b + J5_LINK[0] +
                                                                                            J5_LINK[1]))
    # 5. J1 shell vias
    for v in board.GetTracks():
        if v.GetClass() != "PCB_VIA" or v.GetNetname() != "GND":
            continue
        x, y = bl.to_board(v.GetPosition())
        for old, new in list(J1_VIAS.items()) + list(STITCH_MOVES.items()):
            if abs(x - old[0]) < 0.003 and abs(y - old[1]) < 0.003:
                v.SetPosition(bl.to_page(*new))
                for a, b, t in segs(board, "GND"):
                    if math.hypot(a[0] - x, a[1] - y) < 0.003:
                        t.SetStart(bl.to_page(*new))
                    if math.hypot(b[0] - x, b[1] - y) < 0.003:
                        t.SetEnd(bl.to_page(*new))
                LOG.append("GND via (%.3f, %.3f) -> (%.3f, %.3f)" % (x, y, new[0], new[1]))
    # 6. hop island via, 7. Q1 drain vias
    for p in HOP_VIAS:
        items.append(new_via(board, "GND", p))
    for v, e in Q1_VIAS:
        items.append(new_via(board, "VCC5V0_SYS", v))
        items.append(new_track(board, "VCC5V0_SYS", v, e, 0.5))
    LOG.append("In2 GND hop island vias %s; Q1 drain vias %s" % (HOP_VIAS, [v for v, _e in Q1_VIAS]))
    rl.group(board, GROUP, items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"log": LOG}, open(OUT, "w"), indent=1)
    print("\n".join(LOG))


if __name__ == "__main__":
    main()
