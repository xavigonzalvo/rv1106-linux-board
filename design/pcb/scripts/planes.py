#!/usr/bin/env python3
"""Layout phase L3, step 4: copper zones (layout.md §2.3, §7; D-109) and the as-built L3 plan design/pcb/planes.csv.

    $PY design/pcb/scripts/planes.py         # after route_planevias.py; then fill_zones.py

Zones (all inside the board, 0.40 mm from every edge: the V-cut edges need 0.4 mm, the routed ones 0.3 mm, layout.md §1):
  In1.Cu (L2)  one solid GND zone over the whole board, no tracks ever (§2.3). Vias connect solid (KiCad always
               does for vias); through-hole pins get thermal reliefs (hand soldering); the U9 EP and its 16 via pads
               are set to a solid connection on the pad itself (route_escape.py, layout.md §6.2).
  In2.Cu (L3)  one zone per power net (priority 1) = union of its rectangles in planes.csv (BASE + ARMS below, and the
               fingers computed here from plane vias outside their net's base region), each rectangle minus the
               rectangles of other nets of higher rank grown by 0.30 mm (rank: finger 3 > arm 2 > base 1; equal rank:
               VDD_0V9 > VCC_3V3 > VBUS_USBA > VCC5V0_SYS), so regions of different nets never overlap and keep
               >= 0.30 mm (§2.3); GND fill of the rest at priority 0. KiCad 10 reports same-net overlapping zones as
               errors (zones_intersect), hence one zone per net.
  F.Cu / B.Cu  GND pour over the whole board at priority 0, clearances of the net classes (KiCad takes the larger of the
               zone clearance 0.15 and the other item's class clearance), thermal reliefs for pads (gap 0.25, spoke
               0.30 mm), vias solid; F.Cu keeps out of the U9 fan square (+-7.90 mm, no slivers between the escape lanes)
               and from the area under the crystals' guard is left to the pour (GND).
BASE is layout/planes.csv (Phase 7, computed for the round-3 placement) adapted to the approved L2 placement (D-H5):
VCC_3V3 N-BAND reaches y 4.0 (Z-UI pull-ups R68/R69 at y 5.6), new NAND-S (U10 moved 2.5 mm south, D-106 c: U10.8,
C80/C81, R52-R54 sit south of the VDD_0V9 neck), S-SOC widened east to join NAND-S, new S-USB (U11.10 and C84 at
y 55); VCC5V0_SYS USBA strip reaches y 63 east of x 43.75 (U8 pin 5 at y 61.65); VBUS_USBA starts at x 29.8 (C35 at
x 30.6) and stops at x 43.4 west of the 5 V strip. Pads outside every base region of their net are reached by fingers
(1.6 mm wide, axis-aligned L from the via to the nearest base rectangle, at most FINGER_MAX long), listed in
planes.csv as region FINGER-<pad>-<leg>. Pads farther away (the test-row pads, the header 5 V pins, TP17) are joined
by route_powerlinks.py instead.
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

E = 0.40            # copper to board edge
L3_GAP = 0.30
FINGER_W = 1.60

# net, region, x0, y0, x1, y1, purpose  (In2.Cu = L3)
BASE = [
    ("VDD_0V9", "ISLAND", 26.05, 28.05, 42.95, 44.95, "under U9: the VDD_0V9 pin vias (inner, D-109 a) and the ring-1 VDD_0V9 cap vias"),
    ("VDD_0V9", "NECK", 42.95, 33.0, 65.0, 37.0, "4 mm neck from JP1 (63.7, 35.0), 6 vias, west to the island (layout.md §2.3)"),
    ("VDD_0V9", "NECK-N", 42.95, 28.05, 61.5, 33.0, "D-110: neck widened north over the old GND strip and the VCC_3V3 NAND tongue (no VCC_3V3 load there since U10 moved south): the free strip NECK_FREE runs here, north of the ring-1 GND via column at x 44.25"),
    ("VCC_3V3", "N-BAND", 1.0, 4.0, 65.0, 21.5, "feed from R30 (63.5, 16.5) west; header J5.1, Z-UI pull-ups (y0 4.0: R68/R69)"),
    ("VCC_3V3", "W-COL", 1.0, 21.5, 25.7, 64.5, "Z-ETH (FB1), Z-HDR (I2C pull-ups, J5.17), Z-SDPWR (Q4, C21, R39)"),
    ("VCC_3V3", "N-SOC", 26.05, 21.5, 61.5, 27.75, "north of the island: SoC VCC_3V3 cap fingers, R43 (D-110: R43.1 via at y 27.45)"),
    ("VCC_3V3", "NAND-S", 43.3, 37.35, 61.8, 47.6, "south of the neck: U10.8, C80/C81, R52-R54 (U10 2.5 mm south, D-106 c)"),
    ("VCC_3V3", "S-SOC", 25.7, 45.3, 54.6, 49.7, "south of the island: SoC pins 13/28/43 cap fingers, D2.2; joins NAND-S"),
    ("VCC_3V3", "S-USB", 33.0, 49.7, 41.6, 56.6, "U11 pin 10 and C84 (U11 at y 55, D-105)"),
    ("VCC5V0_SYS", "PMU", 65.3, 12.0, 77.0, 48.0, "VIN side of all four buck cells"),
    ("VCC5V0_SYS", "PWRIN", 55.0, 48.0, 77.0, 72.5, "all of Z-PWRIN: Q1 drain, C5, R3, R12, TP13"),
    ("VCC5V0_SYS", "USBA", 42.0, 55.0, 55.0, 60.0, "5 mm strip west to U8 and C11"),
    ("VCC5V0_SYS", "USBA-U8", 43.75, 55.0, 55.0, 63.0, "down to U8 pin 5 (44.54, 61.65)"),
    ("VBUS_USBA", "USBA", 29.8, 60.6, 43.4, 68.5, "U8 pin 1 -> C34 -> C35 -> J4 pin 1 -> U2 pin 5"),
]
# arms: added to BASE for pad groups next to a region of their net (rank 2: cut the base regions of other nets)
ARMS = [
    ("VDD_0V9", "W-ARM", 20.6, 42.25, 26.4, 45.45, "NT1.1 (>= 2 vias, layout.md §3) and C37 west of the island"),
]
FINGER_MAX = 8.0
FINGER_MARGIN = 0.30        # a via whose centre is >= 0.30 mm inside a base rectangle of its net needs no finger
NARROW = {"R43.1": 0.80}    # fingers narrower than FINGER_W (pull-up pads, DC): keep clear of the VDD_0V9 neck
# D-110: free VDD_0V9 strips of the core feed JP1 -> island (layout.md §3 PWR_0V9 >= 2.58 mm at 1.3 A, 3.0 chosen).
# No via of another net (and no finger) may come closer than 0.30 + via radius to these rectangles (route_planevias.py
# keeps them clear; check_routing.py measures the filled copper). Path: island east edge (x 42.95) -> NECK-N strip
# y 28.05-30.75 (north of the ring-1 GND column at x 44.25, south of the R43 pull-up) -> east to x 63.5 -> down to JP1.2.
NECK_FREE = [
    ("STRIP-N", 42.95, 28.05, 63.5, 30.75),
    ("STRIP-JP1", 60.5, 28.05, 63.5, 35.5),
]
ESC_FINGERS = os.path.join(bl.PCB_DIR, "escape_fingers.json")
NET_ORDER = {"VDD_0V9": 4, "VCC_3V3": 3, "VBUS_USBA": 2, "VCC5V0_SYS": 1}
PCB_PLANES = os.path.join(bl.PCB_DIR, "planes.csv")


def in_base(net, x, y, margin=0.0):
    for n, reg, x0, y0, x1, y1, _p in BASE + ARMS:
        if n == net and x0 + margin <= x <= x1 - margin and y0 + margin <= y <= y1 - margin:
            return reg
    return None


def base_rects(net):
    return [(x0, y0, x1, y1) for n, _r, x0, y0, x1, y1, _p in BASE + ARMS if n == net]


def fingers(vias):
    """vias: list of (net, x, y, ref). Returns finger rows (net, region, x0, y0, x1, y1, purpose) for each via of an
    L3 net that is not inside a base rectangle of its net with 0.45 mm margin: an axis-aligned L to the nearest base
    rectangle (the variant that crosses fewer other-net vias), FINGER_W wide."""
    out = []
    done = set()
    other = [(n, x, y) for n, x, y, _r in vias]
    for net, x, y, ref in vias:
        if in_base(net, x, y, margin=FINGER_MARGIN) or ref.startswith("U9via"):
            continue        # U9 inner vias: their fingers come from route_escape.py (escape_fingers.json, D-110)
        key = (net, round(x, 2), round(y, 2))
        if key in done:
            continue
        done.add(key)
        best = None
        fw = NARROW.get(ref, FINGER_W)
        for (x0, y0, x1, y1) in base_rects(net):
            tx = min(max(x, x0 + fw / 2), x1 - fw / 2)
            ty = min(max(y, y0 + fw / 2), y1 - fw / 2)
            h = fw / 2
            for variant in ("xy", "yx"):
                if variant == "xy":       # horizontal from the via to tx, then vertical to ty
                    rects = [(min(x, tx) - h, y - h, max(x, tx) + h, y + h), (tx - h, min(y, ty) - h, tx + h, max(y, ty) + h)]
                else:
                    rects = [(x - h, min(y, ty) - h, x + h, max(y, ty) + h), (min(x, tx) - h, ty - h, max(x, tx) + h, ty + h)]
                length = abs(tx - x) + abs(ty - y)
                hits = sum(1 for n, ox, oy in other if n != net and any(
                    r[0] - 0.6 <= ox <= r[2] + 0.6 and r[1] - 0.6 <= oy <= r[3] + 0.6 for r in rects))
                cost = length + 1.5 * hits
                if best is None or cost < best[0]:
                    best = (cost, rects)
        if sum(max(r[2] - r[0], r[3] - r[1]) - fw for r in best[1]) > FINGER_MAX:
            continue                      # too far: route_powerlinks.py joins this pad by a track
        for k, r in enumerate(best[1]):
            if r[2] - r[0] < 1e-6 or r[3] - r[1] < 1e-6:
                continue
            out.append((net, "FINGER-%s-%d" % (ref, k), round(r[0], 3), round(r[1], 3), round(r[2], 3),
                        round(r[3], 3), "via of %s at (%.2f, %.2f) outside the base region" % (ref, x, y)))
    return out


def finger_name(region):
    """FINGER-<pad>-<leg> -> FINGER-<pad>"""
    return region.rsplit("-", 1)[0]


def make_zone(board, net, layer, pts, priority, clearance, name, thermal=True, solid_vias=True, min_w=0.20,
              rects=None, polyset=None):
    import pcbnew
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    z.SetZoneName(name)
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(pcbnew.FromMM(clearance))
    z.SetMinThickness(pcbnew.FromMM(min_w))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.25))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.30))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    if polyset:
        polyset(z.Outline())
    elif rects:
        ps = z.Outline()
        for rp in rects:
            ps.NewOutline()
            for x, y in rp:
                p = bl.to_page(x, y)
                ps.Append(p.x, p.y)
        ps.Simplify()
    else:
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            p = bl.to_page(x, y)
            o.Append(p.x, p.y)
    board.Add(z)
    return z


def poly_rect(ps, r, grow=0.0):
    import pcbnew
    x0, y0, x1, y1 = r
    ps.NewOutline()
    for x, y in rect(x0 - grow, y0 - grow, x1 + grow, y1 + grow):
        p = bl.to_page(x, y)
        ps.Append(p.x, p.y)


def net_polygon(acc, net, rows):
    """acc (the zone's own outline) := union over the net's rows of (row - other-net rows of higher rank, grown by
    L3_GAP)."""
    import pcbnew
    l3 = [r for r in rows if r[0] == "In2" and r[1] != "GND"]
    for r in l3:
        if r[1] != net:
            continue
        tmp = pcbnew.SHAPE_POLY_SET()
        poly_rect(tmp, r[3:7])
        cut = pcbnew.SHAPE_POLY_SET()
        n = 0
        for s in l3:
            if s[1] != net and (s[7], NET_ORDER[s[1]]) > (r[7], NET_ORDER[r[1]]):
                poly_rect(cut, s[3:7], grow=L3_GAP)
                n += 1
        if n:
            tmp.BooleanSubtract(cut)
        acc.BooleanAdd(tmp)
    acc.Simplify()


def rect(x0, y0, x1, y1):
    x0, y0 = max(x0, E), max(y0, E)
    x1, y1 = min(x1, 80 - E), min(y1, 80 - E)
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def keepout_fan(board):
    """F.Cu pour keep-out over the U9 fan square (no GND slivers between the 0.10 mm escape lanes)."""
    import pcbnew
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName("U9_NOPOUR")
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowZoneFills(True)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    h = 8.6
    for x, y in ((34.5 - h, 36.5 - h), (34.5 + h, 36.5 - h), (34.5 + h, 36.5 + h), (34.5 - h, 36.5 + h)):
        p = bl.to_page(x, y)
        o.Append(p.x, p.y)
    board.Add(z)
    return z


def main():
    import pcbnew
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import routelib as rl
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, "L3_PLANES")
    vias = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() in rl.L3_NETS:
            x, y = bl.to_board(t.GetPosition())
            vias.append((t.GetNetname(), x, y, "via@%.1f,%.1f" % (x, y)))
    # name fingers after the pad the via serves (planevias.csv), when known
    pv = {}
    if os.path.exists(os.path.join(bl.PCB_DIR, "planevias.csv")):
        for r in csv.DictReader(open(os.path.join(bl.PCB_DIR, "planevias.csv"), encoding="utf-8")):
            if r["via_x"]:
                pv[(float(r["via_x"]), float(r["via_y"]))] = "%s.%s" % (r["ref"], r["pad"])
    def label(x, y):
        for (px, py), name in pv.items():
            if abs(px - x) < 0.006 and abs(py - y) < 0.006:
                return name
        return "U9via" if abs(x - 34.5) < 6.2 and abs(y - 36.5) < 6.2 else "via@%.2f,%.2f" % (x, y)
    vias = [(n, x, y, label(x, y)) for n, x, y, _r in vias]
    esc_f = []
    if os.path.exists(ESC_FINGERS):
        with open(ESC_FINGERS, encoding="utf-8") as fh:
            esc_f = json.load(fh)
    vias.sort(key=lambda v: (v[0], v[3], round(v[1], 3), round(v[2], 3)))
    allvias = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            x, y = bl.to_board(t.GetPosition())
            allvias.append((t.GetNetname(), x, y, ""))
    fing = fingers(vias)
    # rows of the as-built plan: layer, net, region, x0, y0, x1, y1, rank, purpose
    rows = []
    for n, reg, x0, y0, x1, y1, purp in BASE:
        rows.append(("In2", n, reg, x0, y0, x1, y1, 1, purp))
    for n, reg, x0, y0, x1, y1, purp in ARMS:
        rows.append(("In2", n, reg, x0, y0, x1, y1, 2, purp))
    for f in fing:
        rows.append(("In2", f[0], f[1], f[2], f[3], f[4], f[5], 3, f[6]))
    for f in esc_f:
        r = f["rect"]
        rows.append(("In2", f["net"], "FINGER-U9.%d" % f["pin"], r[0], r[1], r[2], r[3], 3,
                     "D-110: inner via of U9 pin %d, %.2f mm L3 finger to the %s edge of the island" %
                     (f["pin"], f["width"], f["dir"])))
    rows.append(("In2", "GND", "FILL", 0, 0, 80, 80, 0, "GND fill of the rest of L3, tied to L2 by the GND vias"))
    rows.append(("In1", "GND", "PLANE", 0, 0, 80, 80, 0, "solid GND plane, no tracks (layout.md §2.3)"))
    rows.append(("F", "GND", "POUR", 0, 0, 80, 80, 0, "L1 GND pour, out of the U9 fan square"))
    rows.append(("B", "GND", "POUR", 0, 0, 80, 80, 0, "L4 GND pour"))

    items = []
    for net in ("VDD_0V9", "VCC_3V3", "VBUS_USBA", "VCC5V0_SYS"):
        items.append(make_zone(board, net, pcbnew.In2_Cu, None, 1, L3_GAP, "In2_%s" % net,
                               polyset=lambda ps, net=net: net_polygon(ps, net, rows)))
    for lay, n, reg, x0, y0, x1, y1, pr, _p in rows:
        if n != "GND":
            continue
        layer = {"In1": pcbnew.In1_Cu, "In2": pcbnew.In2_Cu, "F": pcbnew.F_Cu, "B": pcbnew.B_Cu}[lay]
        clr = L3_GAP if lay == "In2" else 0.15
        items.append(make_zone(board, n, layer, rect(x0, y0, x1, y1), 0, clr, "%s_%s_%s" % (lay, n, reg),
                               thermal=True))
    items.append(keepout_fan(board))
    rl.group(board, "L3_PLANES", items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    with open(PCB_PLANES, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["layer", "net", "region", "x0", "y0", "x1", "y1", "rank", "purpose"])
        for r in rows:
            w.writerow(r)
    print("zones: %d; L3: %d base + %d arm rectangles, %d finger legs; plan -> %s" % (len(items), len(BASE), len(ARMS),
                                                                                    len(fing), PCB_PLANES))


if __name__ == "__main__":
    main()
