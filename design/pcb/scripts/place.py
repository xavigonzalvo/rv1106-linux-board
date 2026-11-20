#!/usr/bin/env python3
"""Layout phase L2, step 2: place all 226 parts of design/pcb/rv1106-reva.kicad_pcb (run build_board.py first).

    PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $PY design/pcb/scripts/place.py

Coordinates below are board mm (layout.md: origin = board NW corner, x east, y south); boardlib converts them to the
page ((0, 0) = page (50, 50) mm). Rotations are KiCad degrees (counter-clockwise on screen).

How the placement was decided (layout.md §5, the review is in design/pcb/placement-review.md):
  * FIXED: connectors, U9, U8, JP1, R30 at the zones.csv / layout.md §5 / placement.csv positions (J2 moved 0.9 mm
    west, D-103: its courtyard is 1.7 mm wider than the planned rectangle and would overlap J4).
  * U9 ring 1 (§5.3, §6.1, D-104): escape.py plans each side in pin order; every ring-1 part sits radially with its
    inner pad edge 7.93 mm from the U9 centre (via ring free), every gap is sized for the lanes that pass it at class
    width/clearance, sideways shifts <= 1.45 mm. The plan is written to design/pcb/escape_plan.csv. Ring 2 and the
    crystal/NPOR/sub-rail parts sit beyond the row, legalized around keep-outs over the lanes (add_lane_kos).
  * Buck cells (Z-PMU, §4.5): each is the TLV62569 DBV layout example ([TLV] SLVSDG1C §10.2 Fig. 20 p.13) rotated 180 deg:
    VIN + C_IN east, inductor west of the IC (pad 1 = SW next to pin 3), output caps and the measurement link in the
    x 62-65 strip, divider on the quiet north side next to FB.
  * Everything else: hand positions, or a preferred position given to legalize() which searches the nearest free spot
    (no courtyard overlap, inside the zone rectangle) so small parts pack without overlaps.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402

import pcbnew  # noqa: E402

SOC = (34.5, 36.5)
PADLINE = {"S": 42.575, "N": 30.425, "E": 40.575, "W": 28.425}   # U9 pad-centre lines at rotation +90

board = pcbnew.LoadBoard(bl.BOARD_FILE)
FP = {fp.GetReference(): fp for fp in board.GetFootprints()}
ZONES = bl.zones()
PLACED = {}          # ref -> courtyard bbox (board mm)
GAP = 0.05           # courtyard-to-courtyard gap kept by the legalizer


def bbox(ref):
    return bl.courtyard_bbox(FP[ref])


def place(ref, x, y, rot):
    fp = FP[ref]
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(bl.to_page(x, y))
    bb = bbox(ref)
    if bb:
        PLACED[ref] = bb
    return fp


def pad(ref, num):
    for p in FP[ref].Pads():
        if p.GetNumber() == str(num):
            return p
    raise KeyError("%s.%s" % (ref, num))


def padxy(ref, num):
    return bl.to_board(pad(ref, num).GetPosition())


def overlaps(bb, skip=None):
    for r, o in PLACED.items():
        if r == skip:
            continue
        if bb[0] < o[2] + GAP and bb[2] > o[0] - GAP and bb[1] < o[3] + GAP and bb[3] > o[1] - GAP:
            return r
    return None


def inside(bb, rect):
    return bb[0] >= rect[0] - 1e-6 and bb[1] >= rect[1] - 1e-6 and bb[2] <= rect[2] + 1e-6 and bb[3] <= rect[3] + 1e-6


def pad_by(ref, key):
    """Pad of ref by number, or by net name (the first pad on that net)."""
    for p in FP[ref].Pads():
        if p.GetNumber() == str(key):
            return p
    for p in FP[ref].Pads():
        if p.GetNetname() == key:
            return p
    raise KeyError("%s.%s" % (ref, key))


def near_ok(ref, near):
    """near = list of (pad-or-net, (ref2, pad-or-net2), max_mm[, 'centre']): copper edge-to-edge distance (or centre
    distance) constraints."""
    for c in near:
        a, (r2, b), lim = c[0], c[1], c[2]
        pa, pb = pad_by(ref, a), pad_by(r2, b)
        d = bl.centre_dist(pa, pb) if len(c) > 3 and c[3] == "centre" else bl.edge_dist(pa, pb)
        if d > lim:
            return False
    return True


def legalize(ref, x, y, rots, zone, radius=8.0, step=0.1, near=None):
    """Put ref at the free spot nearest to (x, y) (spiral search), trying the rotations in order, keeping the
    courtyard inside `zone` (name or rect). near: list of distance constraints, see near_ok()."""
    if near and not isinstance(near, list):
        near = [near]
    rect = zone if isinstance(zone, tuple) else (ZONES[zone]["x0"], ZONES[zone]["y0"], ZONES[zone]["x1"],
                                                    ZONES[zone]["y1"])
    PLACED.pop(ref, None)
    r = 0.0
    while r <= radius + 1e-9:
        n = max(1, int(round(2 * math.pi * r / step))) if r > 0 else 1
        cands = []
        for i in range(n):
            a = 2 * math.pi * i / n
            cands.append((x + r * math.cos(a), y + r * math.sin(a)))
        for cx, cy in cands:
            for rot in rots:
                place(ref, cx, cy, rot)
                PLACED.pop(ref, None)
                bb = bbox(ref)
                if not inside(bb, rect) or overlaps(bb, ref):
                    continue
                if near and not near_ok(ref, near):
                    continue
                PLACED[ref] = bb
                return cx, cy, rot
        r += step
    raise RuntimeError("legalize: no free spot for %s near (%.2f, %.2f) in %s" % (ref, x, y, zone))


# ---------------------------------------------------------------------------------------------------------------
# SoC ring 1: the escape plan of escape.py (D-104)
# ---------------------------------------------------------------------------------------------------------------
RULES = esc.net_rules()
ROT_IN = {"S": 270, "N": 90, "E": 0, "W": 180}      # radial rotation that puts pad 1 toward the SoC


def u9_pins():
    out = {}
    for p in FP["U9"].Pads():
        n = p.GetNumber()
        if n and n != "129":
            x, y = bl.to_board(p.GetPosition())
            out[int(n)] = (x, y, p.GetNetname())
    return out


PINS = None


def pin_t(pin):
    x, y, _ = PINS[pin]
    return esc.t_of(esc.side_of(pin), x, y)


def radial_geom(ref, side, net):
    """Place ref radially on `side` at the U9 centre with the pad on `net` toward the SoC; return
    (rotation, copper half-width along t, courtyard half-width along t, radial extent of the pads beyond the centre
    toward the SoC)."""
    inner = "1" if pad(ref, "1").GetNetname() == net else "2"
    rot = ROT_IN[side] if inner == "1" else (ROT_IN[side] + 180) % 360
    cx, cy = esc.CENTRE
    place(ref, cx, cy, rot)
    PLACED.pop(ref, None)
    ts, rs = [], []
    for p in FP[ref].Pads():
        for x, y in bl.pad_polygon(p):
            ts.append(esc.t_of(side, x, y) - esc.t_of(side, cx, cy))
            rs.append(esc.radial(side, x, y))
    bb = bbox(ref)
    if side in "NS":
        hc = (bb[2] - bb[0]) / 2
    else:
        hc = (bb[3] - bb[1]) / 2
    return rot, max(abs(min(ts)), max(ts)), hc, -min(rs)


def plan_side(side):
    """Solve the ring-1 row of one side. Returns (items, positions)."""
    roles = esc.pin_roles(PINS, RULES)
    pins = sorted(p for p in PINS if esc.side_of(p) == side)
    items = []
    for ref, served in esc.ROW_PARTS[side]:
        net = PINS[served[0]][2]
        rot, hw, hc, rin = radial_geom(ref, side, net)
        ts = [pin_t(p) for p in served]
        items.append(dict(kind="part", ref=ref, pins=served, net=net, lo=min(ts), hi=max(ts), rot=rot, hw=hw, hc=hc,
                          rin=rin, w8=1.0))
    for p in pins:
        role = roles[p]
        if role != "LANE" and not (role == "PART" and p in esc.THRU_LANES):
            continue
        net = PINS[p][2]
        pair = p in esc.PAIRS
        w, c = esc.lane_wc(net, RULES, pair)
        t = pin_t(p) if not pair else (pin_t(p) + pin_t(esc.PAIRS[p])) / 2
        items.append(dict(kind="lane", ref=p, net=net, lo=t, hi=t, w=w, c=c, w8=0.2, pair=pair))
    items.sort(key=lambda i: ((i["lo"] + i["hi"]) / 2, 0 if i["kind"] == "lane" else 1))
    # hard windows: lanes +-FAN_REACH; parts FAN_REACH, or NC_REACH where only NC / same-net pins lie that way
    tc = esc.t_of(side, *esc.CENTRE)
    for it in items:
        if it["kind"] == "lane":
            reach = esc.PAIR_REACH if it.get("pair") else esc.FAN_REACH
            it["L"], it["U"] = it["lo"] - reach, it["hi"] + reach
            continue
        def reach(t0, d):
            for p in pins:
                dd = (pin_t(p) - t0) * d
                if 0.2 < dd <= esc.NC_REACH and PINS[p][2] and PINS[p][2] != it["net"]:
                    return esc.FAN_REACH
            return esc.NC_REACH
        it["L"] = max(it["lo"] - reach(it["lo"], -1), tc - 8.6 + it["hc"])
        it["U"] = min(it["hi"] + reach(it["hi"], 1), tc + 8.6 - it["hc"])

    def need(a, b):
        if a["kind"] == "part" and b["kind"] == "part":
            return max(a["hc"] + b["hc"] + 0.02, a["hw"] + b["hw"] + 0.20)
        if a["kind"] == "lane" and b["kind"] == "lane":
            c = esc.PAIR_PAIR_CLEAR if a.get("pair") and b.get("pair") else max(a["c"], b["c"])
            return a["w"] / 2 + c + b["w"] / 2
        ln, pt = (a, b) if a["kind"] == "lane" else (b, a)
        return pt["hw"] + ln["c"] + ln["w"] / 2

    pos = esc.solve_row(items, need)
    if pos is None:
        sys.exit("ring-1 row of side %s has no solution (escape plan over-subscribed)" % side)
    for it, x in zip(items, pos):
        it["x"] = x
    return items


def place_ring1():
    """Place every ring-1 row part at its planned position; return the plan rows for escape_plan.csv."""
    rows = []
    for side in "SENW":
        items = plan_side(side)
        for it in items:
            if it["kind"] != "part":
                continue
            r = esc.ROW_INNER + 0.03 + it["rin"]
            x, y = esc.point(side, it["x"], r)
            place(it["ref"], x, y, it["rot"])
            # the facing pad must carry the pin's net
            fx = [p for p in FP[it["ref"]].Pads() if p.GetNetname() == it["net"]][0]
            fr = min(esc.radial(side, *q) for q in bl.pad_polygon(fx))
            assert abs(fr - esc.ROW_INNER - 0.03) < 0.02, (it["ref"], fr)
        rows.append((side, items))
    return rows


def write_plan(rows):
    roles = esc.pin_roles(PINS, RULES)
    path = os.path.join(bl.PCB_DIR, "escape_plan.csv")
    lane_at = {}
    part_at = {}
    for side, items in rows:
        for it in items:
            if it["kind"] == "lane":
                lane_at[it["ref"]] = it["x"]
            else:
                for p in it["pins"]:
                    part_at[p] = (it["ref"], it["x"])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("pin,side,net,netclass,role,part,t_pin,t_planned,shift_mm,note\n")
        for p in sorted(PINS):
            side = esc.side_of(p)
            net = PINS[p][2]
            role = roles[p]
            part, tp, note = "", "", ""
            if role == "PART":
                part, tp = part_at[p][0], part_at[p][1]
            elif role == "LANE":
                tp = lane_at[p]
            elif role == "PAIR2":
                tp = lane_at[[a for a, b in esc.PAIRS.items() if b == p][0]]
                note = "second pin of the pair"
            elif role == "VIA":
                note = esc.VIA_PINS.get(p, "VDD_0V9 island via" if RULES[net][0] == "PWR_0V9" else "GND via to L2")
            sh = ("%.3f" % (tp - pin_t(p))) if tp != "" else ""
            fh.write("%d,%s,%s,%s,%s,%s,%.3f,%s,%s,%s\n" % (p, side, net, RULES[net][0] if net else "", role, part,
                                                         pin_t(p), ("%.3f" % tp) if tp != "" else "", sh, note))
    print("wrote", path)


FACE_ROT = {"W": 0, "E": 180, "S": 90, "N": 270}     # rotation that puts pad 1 of a 2-pad part toward that side


def face(ref, x, y, net, direction):
    """Place a 2-pad part with its pad on `net` toward `direction` (N/S/E/W)."""
    rot = FACE_ROT[direction]
    if pad(ref, "1").GetNetname() != net:
        rot = (rot + 180) % 360
    place(ref, x, y, rot)


def add_lane_kos(rows):
    """Keep-outs (for the legalizer) over the lanes: through the gate and 1 mm (DEFAULT) / 2 mm (other classes) beyond
    it, plus the continuation of the in-lane series resistors R47/R48. XTAL and NPOR lanes are placed by hand."""
    for side, items in rows:
        run = []

        def flush():
            if not run:
                return
            dflt = all(RULES[i["net"]][0] == "DEFAULT" for i in run)
            r1 = 9.65 + (1.0 if dflt else 2.0)
            t0 = run[0]["x"] - run[0]["w"] / 2
            t1 = run[-1]["x"] + run[-1]["w"] / 2
            x0, y0 = esc.point(side, t0, esc.VIA_RING)
            x1, y1 = esc.point(side, t1, r1)
            PLACED["KO_%s_%s" % (side, run[0]["ref"])] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            del run[:]

        for it in items:
            if it["kind"] == "lane" and RULES[it["net"]][0] not in ("XTAL",) and it["net"] != "NPOR":
                run.append(it)
            else:
                flush()
                if it["kind"] == "part" and it["ref"] in ("R47", "R48"):
                    x0, y0 = esc.point(side, it["x"] - 0.1, 9.65)
                    x1, y1 = esc.point(side, it["x"] + 0.1, 11.65)
                    PLACED["KO_%s_%s" % (side, it["ref"])] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        flush()
    # the four gate bands themselves (via ring to the outside of the row): only ring-1 parts live there
    for side in "SENW":
        tc = esc.t_of(side, *esc.CENTRE)
        a = esc.point(side, tc - 7.45, esc.TOE)
        b = esc.point(side, tc + 7.45, 9.65)
        PLACED["KO_GATE_%s" % side] = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def main():
    # ===========================================================================================================
    # Fixed positions: connectors (zones.csv), U9, U8, JP1, R30 (layout.md §5.1, placement.csv)
    # ===========================================================================================================
    place("U9", 34.5, 36.5, 90)
    place("J3", 21.46, 17.26, 180)
    place("J5", 3.00, 9.56, 0)
    place("J6", 30.77, 2.77, 90)
    place("J2", 18.60, 72.50, 0)      # D-103: zones.csv x 19.5 -> 18.6 (J2/J4 courtyards would overlap by 0.73 mm)
    place("J4", 35.75, 72.50, 0)
    place("J1", 49.50, 76.35, 0)
    place("U8", 43.40, 62.60, 0)
    place("JP1", 63.70, 35.00, 180)
    place("R30", 63.50, 16.50, 270)   # pad 1 (VCC_3V3_BUCK) north, pad 2 (VCC_3V3) south toward the L3 band vias
    for ref in ("H1", "H2", "H3", "H4", "FID1", "FID2", "GFID1", "GFID2", "GFID3", "TH1", "TH2", "TH3", "TH4"):
        bb = bbox(ref)
        if bb:
            PLACED[ref] = bb

    # ===========================================================================================================
    # Z-SOC ring 1: the escape plan (escape.py, D-104). Every ring-1 part sits radially in one row whose inner pad edge
    # is 7.93 mm from the U9 centre (the via ring r 7.45 stays free); the planner orders parts and lanes like the pins,
    # sizes every gap for the lanes that pass it at their class width/clearance and minimises the sideways shifts.
    # ===========================================================================================================
    global PINS
    PINS = u9_pins()
    rows = place_ring1()
    write_plan(rows)
    add_lane_kos(rows)

    def near_pin(ref, key, pin, lim):
        return [(key, ("U9", str(pin)), lim)]

    def try_near(ref, x, y, rots, near, zone="Z-SOC", radius=6.0):
        try:
            return legalize(ref, x, y, rots, zone, radius=radius, near=near)
        except RuntimeError:
            legalize(ref, x, y, rots, zone, radius=radius)
            print("note: %s placed without its distance limit (no free spot), see D-104" % ref)

    # ---- north, beyond the row (y < 26.9): crystal Y1, OSC_XOUT parts, NPOR parts in the NE corner ----------------
    # OSC_XIN passes east of R51 to its outer pad and on to Y1 pad 1 (SE); OSC_XOUT passes west of R51 to R50 (in the
    # lane) and TP6; R50 pad 2 (XOUT_X) -> Y1 pad 3 (NW). NPOR turns east inside the gate into the NE corner square.
    place("Y1", 40.35, 24.70, 90)                       # pad 1 XIN SE, pad 3 XOUT_X NW (rot 90)
    face("R50", 37.95, 25.95, "OSC_XOUT", "S")
    try_near("C76", 38.00, 23.60, [90, 270, 0, 180], [("OSC_XOUT_X", ("Y1", "3"), 2.0)])
    try_near("C77", 42.60, 25.80, [90, 270, 0, 180], [("OSC_XIN", ("Y1", "1"), 2.0)])
    # NPOR: C71 (filter cap) radially in the N gate just east of the NPOR lane (the lane passes west of it and lands on
    # its inner pad); R43 (pull-up) in the NE corner square next to it
    face("C71", 41.82, 36.5 - (esc.ROW_INNER + 0.03 + 0.76), "NPOR", "S")
    try_near("R43", 43.25, 28.50, [0, 180, 90, 270], near_pin("R43", "NPOR", 66, 3.0), radius=1.5)
    try_near("TP6", 36.00, 23.70, [0], [("1", ("R50", "OSC_XOUT"), 3.0)])
    try_near("TP31", 33.40, 23.70, [0], [("1", ("TP6", "1"), 3.0, "centre")])
    try_near("C69", 36.90, 22.80, [0, 180, 90, 270], near_pin("C69", "VCC_1V8", 70, 8.0), radius=9.0)
    try_near("C43", 33.20, 25.30, [90, 270, 0, 180], near_pin("C43", "VDD_0V9", 82, 8.0))
    legalize("R66", 31.90, 24.60, [90, 270], "Z-SOC")   # UART2_TX series (pin 79 -> J6)
    legalize("R67", 30.90, 24.60, [90, 270], "Z-SOC")   # UART2_RX series (pin 80 -> J6)
    try_near("FB3", 28.20, 25.30, [0, 180], near_pin("FB3", "ETH_AVDD1V8", 96, 8.0))
    legalize("TP25", 25.60, 24.30, [0], "Z-SOC")

    # ---- east, beyond the row (x > 44.1): ring-2 column behind the 49-56 cluster, FSPI corridors kept free ----------
    # FSPI corridor east of the row (D-106 c): CLK runs straight east at y 37.84 over the top of U10, CS/D2/D1 to
    # the west face of U10, D0/D3 under it; nothing else may sit there (legalizer keep-out)
    PLACED["KO_FSPI"] = (44.15, 37.25, 51.15, 43.95)
    for ref, pin, tx, ty in (("C46", 56, 45.2, 31.2), ("C36", 54, 45.2, 32.3), ("C47", 53, 45.2, 33.4),
                             ("C42", 51, 45.2, 34.5), ("C45", 50, 45.2, 35.6), ("C40", 50, 45.2, 36.7),
                             ("C39", 49, 46.6, 34.0)):
        net = PINS[pin][2]
        try_near(ref, tx, ty, [0, 180], near_pin(ref, net, pin, 8.0))

    # ---- south, beyond the row (y > 46.1): SDMMC bus SW, RTC crystal in the 20/21 corridor, USB pair straight down --
    ko = [v for k, v in PLACED.items() if k == "KO_S_26"][0]
    PLACED["KO_S_26"] = (ko[0], ko[1], ko[2] + 0.6, 54.0)  # USB pair: from the gate down to U11 (pins 7/8)
    # SDMMC corridor (D-105): the bus (pins 11-18, R48) turns west right under the ring-1 row, between the row and
    # Y2's 1 mm guard, then runs south-west to J2. Keep-outs for the legalizer along that path.
    PLACED["KO_SD1"] = (25.6, 46.15, 35.4, 48.95)
    PLACED["KO_SD2"] = (23.4, 48.95, 31.0, 53.0)
    PLACED["KO_SD3"] = (19.8, 53.0, 27.0, 56.5)
    PLACED["KO_SD4"] = (12.7, 56.5, 23.4, 63.6)
    # Y2 below that corridor: pad tops at y 50.4 (corridor 45.99 -> 49.4 = 3.4 mm free of the crystal guard), west of
    # the USB pair; load caps under the pads (D-105; RTC lengths ~ 7-8 mm > 6 mm, RTC unused on Rev A, D-75)
    place("Y2", 34.90, 51.30, 0)                        # pad 1 RTC_XIN east (pin 21), pad 2 RTC_XOUT west (pin 20)
    face("C79", 36.15, 53.00, "RTC_XIN", "W")
    face("C78", 33.65, 53.00, "RTC_XOUT", "E")
    # SE corner: CODEC rail (pin 31), sub-rails of pins 19/24 (L4 / PWR_SUB), key/ADC RC parts of pins 22/23 and the
    # USB_DET divider bottom of pin 25 (these three drop to L4 at the via ring, D-104)
    # SE corner: D2 west next to pin 19's via, then the sub-rail / divider parts nearest to their pins; the CODEC
    # rail (C41/FB2) and TP24 further east. The DC test pads TP18/TP23 go to the NE of Z-SOC (D-104 h: no room).
    place("D2", 41.00, 48.85, 0)                        # VCC_3V3 -> VCC3V3_RTC_IN, K (pad 1) west toward pin 19
    try_near("R33", 42.70, 45.45, [90, 270], near_pin("R33", "AVDD1V8_USB", 24, 8.0), radius=3.0)
    try_near("R4", 44.95, 45.45, [90, 270], near_pin("R4", "USB_DET_IN", 25, 8.0), radius=3.0)
    try_near("C1", 43.40, 47.25, [0, 180, 90, 270], near_pin("C1", "USB_DET_IN", 25, 8.0), radius=4.0)
    legalize("C75", 44.80, 47.40, [0, 180, 90, 270], "Z-SOC")   # RTC rail, uA load: D-104 (h)
    legalize("R34", 44.80, 48.60, [0, 180, 90, 270], "Z-SOC")
    try_near("C41", 47.40, 45.30, [90, 270, 0, 180], near_pin("C41", "VCC1V8_CODEC", 31, 8.0), radius=4.0)
    try_near("FB2", 47.40, 48.20, [90, 270, 0, 180], near_pin("FB2", "VCC1V8_CODEC", 31, 8.0), radius=4.0)
    # VCC1V8_CODEC test pad: Z-SOC is full once the FSPI run is kept free; TP24 sits just east of it, in the unzoned
    # strip under U10 (D-105), 3-4 mm from FB2
    legalize("TP24", 51.00, 46.20, [0], (49.5, 44.0, 55.0, 50.0), radius=4.0)
    legalize("TP23", 45.60, 23.50, [0], "Z-SOC")
    legalize("TP18", 48.20, 23.50, [0], "Z-SOC")
    # pins 22/23 drop to L4 at the via ring (D-104): their RC parts sit in the free NE area of Z-SOC, on the way of
    # RECOVERY to R36 / SW3 in Z-UI
    legalize("R44", 46.20, 23.40, [90, 270], "Z-SOC")   # RECOVERY pull-up
    legalize("C72", 47.20, 23.40, [90, 270], "Z-SOC")
    legalize("R45", 46.20, 25.60, [90, 270], "Z-SOC")   # SARADC_IN1 pull-up
    legalize("C73", 47.20, 25.60, [90, 270], "Z-SOC")
    # SW corner: pin 1 sub-rail (MIPI_CSI_AVDD_1V8), west of the SDMMC bus
    try_near("R32", 22.60, 45.30, [90, 270], near_pin("R32", "MIPI_CSI_AVDD_1V8", 1, 8.0))
    legalize("TP22", 21.90, 46.60, [0], "Z-SOC")

    # ---- west, beyond the row (x < 24.9): VDD_ARM / VDD_0V9 bulk, net tie NT1 in front of the NC pins 117-121 --------
    face("NT1", 25.20, 42.60, "VDD_ARM", "N")           # VDD_ARM pad north next to C52 (pin 115), VDD_0V9 pad south
    PLACED["NT1"] = (24.20, 39.60, 26.20, 45.60)        # NT1 has no courtyard: reserve its two 2 mm pads
    try_near("C38", 23.60, 38.60, [0, 180], near_pin("C38", "VDD_ARM", 115, 8.0))
    try_near("C44", 23.60, 39.70, [0, 180], near_pin("C44", "VDD_ARM", 115, 8.0))
    try_near("C37", 22.40, 43.40, [0, 180, 90, 270], near_pin("C37", "VDD_0V9", 116, 8.0))
    try_near("FB1", 23.07, 33.60, [90, 270], near_pin("FB1", "FEPHY_AVDD3V3", 101, 8.0))
    legalize("TP26", 21.90, 33.80, [0], "Z-SOC")

    # ===========================================================================================================
    # Z-PMU: four TLV62569 cells, Fig. 20 of [TLV] rotated 180 deg (VIN east, output west, divider north).
    # ===========================================================================================================
    def cell(u, L, cin10, cin100, cout, cout100, link, fbt, fbb, cff, y0, cx=71.15, lx=66.65, link_xy=None):
        cy = y0 + 5.2
        place(u, cx, cy, 0)                                   # pins: 1 EN NW, 2 GND W, 3 SW SW, 5 FB NE, 4 VIN SE
        place(L, lx, cy - 0.55, 90)                           # pad 1 (SW) south next to pin 3, pad 2 (VOUT) north
        place(cout, lx - 0.45, y0 + 1.45, 0)                  # output 10/22 uF north of the inductor (pad 1 = VOUT west)
        place(cout100, lx - 3.2, y0 + 1.45, 0)
        if link_xy:
            place(link, *link_xy)
        # divider on the quiet north side of FB (pin 5)
        place(fbt, cx + 0.2, y0 + 2.4, 0)                     # pad 1 VOUT_BUCK west, pad 2 FB east
        place(fbb, cx + 2.3 if FP[fbt].GetFPID().GetLibItemName().wx_str().startswith("R_0402") else cx + 3.0,
              y0 + 2.4, 0)                                    # pad 1 FB west, pad 2 GND east
        place(cff, cx + 0.2, y0 + 1.3, 0)                     # C_FF across R_FBT
        # input caps: 100 nF hugging pin 4 (east), 10 uF just south of pin 4
        place(cin100, cx + 2.65, cy + 0.47, 90)               # pad 1 (VIN) south, level with pin 4
        place(cin10, cx + 1.80, cy + 2.55, 0)                 # pad 1 (VIN) west, under pin 4

    cell("U6", "L3", "C9", "C14", "C25", "C18", "R30", "R22", "R15", "C31", 12.0)
    cell("U7", "L4", "C10", "C15", "C28", "C19", "R31", "R18", "R16", "C32", 21.0, link_xy=(63.50, 25.50, 270))
    cell("U5", "L2", "C8", "C13", "C27", "C17", "R29", "R19", "R14", "C30", 39.0, link_xy=(63.50, 43.50, 270))
    # U4 cell (0V9) sits 1.2 mm further east: JP1 (fixed, 63.7/35.0) takes the west strip at the L3 neck level
    y0 = 30.0
    place("U4", 72.35, 35.20, 0)
    place("L1", 67.85, 34.65, 90)
    place("C24", 67.40, 31.45, 0)
    place("C16", 64.60, 31.45, 0)
    place("R17", 71.90, 32.40, 0)        # R_FBT_U4 0603
    place("R13", 74.45, 32.40, 0)
    place("C29", 71.60, 31.00, 0)
    place("C12", 73.25, 37.50, 0)        # 100 nF: pad 1 VIN under pin 4
    place("C7", 75.27, 35.375, 90)       # 10 uF vertical east of pin 4 (parallel to the V-cut, x > 75)
    # enables, bleeders, small parts of the cells
    place("C33", 69.60, 13.90, 90)       # U6_EN cap next to EN (pin 1) of U6
    legalize("R21", 69.90, 20.00, [0, 180], "Z-PMU")   # PWR_EN -> U6_EN
    legalize("R24", 67.00, 20.10, [0, 180], "Z-PMU")   # VCC_1V8 -> PWR_EN
    legalize("R28", 63.55, 20.20, [0, 180], "Z-PMU")   # VCC_3V3 bleeder
    place("C20", 69.60, 22.90, 90)       # VCC_DDR_1V8_EN cap next to U7 EN
    legalize("R20", 69.90, 29.00, [0, 180], "Z-PMU")   # 5 V -> VCC_DDR_1V8_EN
    legalize("R26", 63.55, 29.20, [0, 180], "Z-PMU")   # VCC_DDR bleeder
    legalize("R23", 76.00, 31.00, [90, 270], "Z-PMU")  # 5 V -> U4_EN
    legalize("R25", 63.20, 37.90, [0, 180], "Z-PMU")   # VDD_0V9 bleeder
    legalize("R27", 63.55, 47.20, [0, 180], "Z-PMU")   # VCC_1V8 bleeder

    # ===========================================================================================================
    # Z-PWRIN: power entry J1 -> F1 -> D1 -> Q1 / U3 (layout.md §4.5, §4.7); power test row at y = 49.45 (§5.4)
    # ===========================================================================================================
    for i, ref in enumerate(("TP21", "TP1", "TP13", "TP4", "TP15", "TP5", "TP3", "TP2")):
        place(ref, 56.35 + 2.75 * i, 49.45, 0)
    place("F1", 58.60, 70.30, 0)         # pad 1 VBUS_IN west (from J1 B4/A9), pad 2 VBUS_5V east
    place("D1", 65.40, 70.60, 0)         # TVS: pad 1 VBUS_5V west, pad 2 GND east
    place("U3", 63.00, 60.00, 180)       # LTC2954: PB (2) east toward SW1, VIN (1) SE, INT/EN/PDT/KILL west
    place("SW1", 71.50, 60.00, 0)
    place("C3", 64.20, 62.75, 270)       # U3 VIN 100 nF under pin 1
    place("C6", 60.05, 59.55, 90)        # PDT 680 nF: pad 1 level with pin 7
    place("R11", 66.40, 56.30, 0)        # PB_IN series, pad 1 (PWR_BTN_N) east toward SW1 pad 1
    place("Q1", 59.40, 66.30, 0)         # P-FET: G NW, S SW, D east
    place("C2", 62.70, 67.20, 90)
    legalize("R5", 56.60, 65.00, [90, 270], "Z-PWRIN")
    legalize("C4", 56.60, 62.50, [90, 270], "Z-PWRIN")
    legalize("C5", 58.60, 63.40, [0, 180], "Z-PWRIN")
    legalize("R9", 60.60, 63.40, [0, 180], "Z-PWRIN")
    legalize("Q2", 57.20, 59.00, [0, 180], "Z-PWRIN")
    legalize("R8", 57.00, 56.60, [0, 180], "Z-PWRIN")
    legalize("Q3", 61.00, 55.60, [0, 180], "Z-PWRIN")
    legalize("R6", 63.20, 56.40, [90, 270], "Z-PWRIN")
    legalize("R7", 59.40, 54.20, [0, 180], "Z-PWRIN")
    legalize("R10", 60.60, 57.20, [0, 180], "Z-PWRIN")
    legalize("TP29", 63.40, 53.40, [0], "Z-PWRIN")
    legalize("TP28", 66.20, 53.40, [0], "Z-PWRIN")
    legalize("TP27", 69.00, 53.40, [0], "Z-PWRIN")
    legalize("TP14", 71.80, 53.40, [0], "Z-PWRIN")
    legalize("TP8", 74.60, 53.40, [0], "Z-PWRIN")
    legalize("TP12", 56.60, 52.30, [0], "Z-PWRIN")
    legalize("TP19", 74.60, 66.50, [0], "Z-PWRIN")
    legalize("R12", 70.00, 65.80, [0, 180], "Z-PWRIN")   # 5 V bleeder 0805 (warm: kept >= 2 mm from others)
    legalize("R3", 57.00, 61.80, [90, 270], "Z-PWRIN")    # VCC5V0_SYS -> USB_DET_IN
    legalize("R1", 56.20, 67.60, [90, 270], "Z-PWRIN")    # CC1 5.1k
    legalize("R2", 56.20, 65.60, [90, 270], "Z-PWRIN")    # CC2 5.1k

    # ===========================================================================================================
    # Z-USB: U11 under pins 26/27, U2 + C35 at J4, U8 corner parts (layout.md §4.5, §4.6)
    # ===========================================================================================================
    # U11 below Y2's guard, east of C79: pins 7/8 (SoC side) north, 1-4 (connector side) south. The planned USB hops
    # (D-106 a): SoC pair P/N swap just north of U11, the USB-A pair under the USB-C pair just south of it.
    place("U11", 38.60, 55.00, 90)
    face("C84", 36.10, 55.00, "VCC_3V3", "E")         # pad 1 (VCC_3V3) east, next to pin 10 (west side at rot 90)
    legalize("R60", 36.10, 56.30, [0, 180], "Z-USB", near=[("USB_SEL", ("U11", "9"), 3.0)])   # USB_SEL pull-down
    place("U2", 36.00, 62.35, 270)       # USB-A ESD, flow-through: DM pin 4 SW / DP pin 6 SE toward J4 pins 2/3
    place("C35", 30.60, 58.70, 90)       # 120 uF polymer, + pad south toward J4 pin 1
    place("C11", 43.60, 59.60, 180)      # U8 input 10 uF: pad 1 (VCC5V0_SYS) east above pin 5
    place("C34", 40.23, 61.15, 270)      # U8 output 22 uF west of U8: pad 1 (VBUS_USBA) north
    place("R37", 39.75, 63.70, 180)      # ISET: pad 1 east next to pin 3
    legalize("R61", 46.00, 63.40, [90, 270], (45.5, 50.0, 55.0, 71.0))   # EN pull-down: no room in Z-USB (D-103)

    # Z-USBA-PWR: U1 at J1, TP17
    place("U1", 49.50, 68.90, 90)        # USB-C ESD, rot 90 (D-106 a): DP pins 6/1 west, DM 4/3 east = the order the
                                         # pair leaves U11 in (no P/N swap), DP -> J1 A6 / DM -> A7 straight down
    legalize("TP17", 53.00, 57.50, [0], "Z-USBA-PWR")  # east, out of the USB-C pair's path

    # ===========================================================================================================
    # Z-SDPWR: SD power switch, card-detect, VDD caps at J2 pin 4
    # ===========================================================================================================
    place("C23", 17.47, 62.55, 90)      # 100 nF right at J2 pin 4 (VDD), between the CLK and CMD approach
    place("C26", 17.47, 59.95, 90)      # 10 uF in line behind it
    # west strip x 9-12.7 + the row y < 56.5: the J2 fan-in (x 12.7-23.4) stays free for the SD bus (D-105)
    place("Q4", 12.00, 54.40, 0)          # G (1) NW, S (2) SW, D (3) east
    face("R39", 9.60, 54.20, "SD_PWR_G", "N")         # gate pull-up next to pin 1
    face("C21", 10.60, 57.10, "VCC_3V3", "N")         # at the source (pin 2)
    face("C22", 14.90, 54.40, "VCC3V3_SD", "W")       # at the drain (pin 3)
    face("R38", 16.80, 54.40, "SD_PWR_G", "W")        # gate series from SDMMC_PWREN
    face("R40", 9.60, 59.00, "VCC3V3_SD", "N")        # VCC3V3_SD bleeder
    place("TP30", 11.40, 59.60, 0)                    # SDMMC_DET test pad
    face("R49", 11.40, 62.60, "SD_CD_SW", "E")        # SDMMC_DET -> SD_CD_SW (J2 pin 9 at x 11.97)
    legalize("TP16", 25.20, 58.80, [0], "Z-SDPWR")   # VCC3V3_SD test pad east of the J2 fan-in (D-105)

    # ===========================================================================================================
    # Z-NAND: U10 with pins 1-4 facing the SoC (west), VCC caps at pin 8, pull-ups next to their pins
    # ===========================================================================================================
    # FSPI without crossings on L1 (D-106 c). Around U9 the lanes run CLK, CS0N, D2, D1, D0, D3 (north -> south); U10
    # has CS 1, D1 2, D2 3 on its west face and D0 5, CLK 6, D3 7 on its east face. U10 sits so that its top pad row
    # (pins 1/8, y 38.55) is just south of the CLK lane (R47, y 37.84): CLK runs straight east over the top of U10 and
    # enters the 1.7 mm channel between the east pads and the exposed pad, down to pin 6's inner end; D3 lands on pin 7
    # from outside. On the west face CS0N and D2 land from outside, D1 enters between pins 3 and 4 and runs up the west
    # channel to pin 2's inner end. D0 and D3 pass under U10's south side.
    place("U10", 55.50, 40.70, 0)
    face("C81", 58.90, 36.95, "VCC_3V3", "E")         # 100 nF NE of pin 8, GND pad west (CLK passes under it)
    face("C80", 60.60, 37.00, "VCC_3V3", "S")         # 1 uF east of C81, pad 1 south toward pin 8
    face("R55", 50.40, 39.63, "FSPI_CS0N_NAND", "N")  # CS0N 0R vertical west of pin 1: pad 2 level with pin 1
    face("R54", 48.70, 38.80, "FSPI_CS0N_NAND", "E")  # CS pull-up between the CLK and CS runs, VCC via west of it
    face("R53", 47.40, 41.25, "FSPI_D2", "E")         # D2 pull-up on the D2 run (D2 pad east), VCC via west
    face("R52", 60.95, 42.00, "FSPI_D3", "N")         # D3 pull-up beside the D3 run on the east side

    # ===========================================================================================================
    # Z-ETH: ETH 0R links side by side, centre-tap caps toward J3 pins 4/5
    # ===========================================================================================================
    # D-106 (b): the pairs leave U9 as RXN, RXP, TXN, TXP (north -> south) and J3 wants, from the south, RXN (pin 6),
    # RXP (pin 3 through the 4|2 gap), TXN (pin 2), TXP (pin 1 east of pin 2): fully reversed. The TX pair drops to L4
    # right after the west gate, passes under the RX pair and comes back to L1 east of it (one via hop per line);
    # each pair's own P/N swap is made by its 0R link: RXN runs north under R58 (RXP link), TXN_J under R56 (TXP link).
    face("R58", 15.60, 24.60, "ETH_RXP", "W")         # horizontal, RXN passes between its pads
    face("R59", 15.60, 26.90, "ETH_RXN", "S")         # vertical in the RXN line, RXN_J north -> under R58 -> pin 6
    face("R56", 21.15, 23.00, "ETH_TXP", "W")         # horizontal, TXN_J passes between its pads -> pin 2
    face("R57", 21.15, 25.30, "ETH_TXN", "S")         # vertical in the TXN line
    face("C83", 16.39, 22.80, "ETH_RCT", "N")  # 0.11 mm into the J3 strip (D-106 b)         # under the 6|4 gap: RCT goes straight up to pin 5
    face("C82", 17.66, 22.80, "ETH_TCT", "N")         # under pin 4

    # Z-HDR: I2C pull-ups
    legalize("R62", 10.00, 35.20, [90, 270], "Z-HDR")
    legalize("R63", 11.10, 35.20, [90, 270], "Z-HDR")
    legalize("R64", 10.00, 42.60, [90, 270], "Z-HDR")
    legalize("R65", 11.10, 42.60, [90, 270], "Z-HDR")

    # Z-UART: test pads under J6
    place("TP20", 29.60, 7.90, 0)        # GND
    place("TP9", 32.40, 7.90, 0)         # UART2_TX
    place("TP10", 35.20, 7.90, 0)        # UART2_RX

    # Z-UI: buttons and LEDs along the north edge
    place("SW2", 44.20, 5.20, 0)         # RESET
    place("SW3", 53.00, 5.20, 0)         # MASKROM
    legalize("R35", 44.20, 9.40, [0, 180], "Z-UI")
    legalize("R36", 53.00, 9.40, [0, 180], "Z-UI")
    for i, (led, res) in enumerate((("LED1", "R68"), ("LED2", "R69"), ("LED3", "R70"))):
        place(led, 60.00 + 3.2 * i, 3.00, 0)
        legalize(res, 60.00 + 3.2 * i, 5.60, [0, 180], "Z-UI")
    legalize("TP7", 62.00, 9.20, [0], "Z-UI")
    legalize("TP11", 67.40, 9.20, [0], "Z-UI")

    # every part placed?
    missing = [r for r in FP if r not in PLACED and FP[r].GetCourtyard(pcbnew.F_CrtYd).OutlineCount()]
    unplaced = [r for r, fp in FP.items() if bl.to_board(fp.GetPosition()) == (0.0, 0.0)]
    if unplaced:
        sys.exit("not placed: " + " ".join(sorted(unplaced)))
    for r, fp in FP.items():
        if fp.IsFlipped():
            sys.exit("%s is on the bottom" % r)
    # quick courtyard bbox overlap report (the real check is check_placement.py + kicad-cli DRC)
    for k in [k for k in PLACED if k.startswith("KO_")]:
        del PLACED[k]
    refs = sorted(PLACED)
    clash = []
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            A, B = PLACED[a], PLACED[b]
            if A[0] < B[2] and A[2] > B[0] and A[1] < B[3] and A[3] > B[1]:
                clash.append("%s/%s" % (a, b))
    if clash:
        print("courtyard bbox overlaps: " + " ".join(clash))
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    print("placed %d footprints; saved %s" % (len(FP), bl.BOARD_FILE))
    if missing:
        print("no courtyard (not overlap-checked): " + " ".join(sorted(missing)))


if __name__ == "__main__":
    main()
