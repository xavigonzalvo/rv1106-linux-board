#!/usr/bin/env python3
"""Layout phase L3, step 3: plane vias for every power/GND pad of the plane nets (layout.md §2.3, §3, §5.3, §7; D-109).

    $PY design/pcb/scripts/route_planevias.py          # after route_escape.py, before planes.py

Plane nets: GND (L2 solid plane), VDD_0V9 / VCC_3V3 / VCC5V0_SYS / VBUS_USBA (L3 regions, planes.py). For every SMD pad
on one of these nets (U9 excluded: route_escape.py) the script searches a via 0.3/0.5 mm whose copper is <= 0.5 mm from
the pad copper (layout.md §5.3 "the GND pad gets its own via to L2 within 0.5 mm"; the task's "each cap pad to its
plane with a via <= 0.5 mm away"), joined by a short L1 stub, and if none fits there, up to 1.2 mm (reported as FAR).
Through-hole pads reach the planes through their own barrels and get no via.
Via counts: 1 per pad, more where layout.md asks: JP1.2 >= 6 (§2.3/§3), R30.2 >= 2 (§2.3), NT1.1 >= 2 (§3), the buck
input/output capacitor GND pads >= 2 (§4.5), D1 GND >= 2 (§4.5), Q1 drain (VCC5V0_SYS) >= 3 and the buck VIN pins >= 2
(PWR_5V, §3), U8 pin 1 (VBUS_USBA) >= 2 (PWR_USBA, §3), U8 pin 5 >= 3.
A candidate via must keep, from copper of other nets, the larger class clearance (netclasses.csv) + 0.02 mm; 0.25 mm
board hole clearance and 0.45 mm hole-to-hole; >= 0.65 mm from the board edges and the V-cut; out of the M3 keep-outs;
out of every pad (no via-in-pad, D-67) and of the courtyards of other ICs, connectors, crystals, inductors, switches
(U11/U1/J1: D-108 a); clear of the trial-route corridors of the 38 critical nets (D-107/D-108, approved at D-H5: diff
pairs 0.76 mm) and of a 3 mm radial exit corridor in front of every U9 gate lane, so L4 can still route them.
Preference: inside the net's L3 base region (planes.BASE), then nearest to the pad, then away from U9 for GND.
Everything is in the board group "L3_PLANEVIAS"; the placed list is written to design/pcb/planevias.csv.
"""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402
import planes  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

OUT_CSV = os.path.join(bl.PCB_DIR, "planevias.csv")
NEAR, FAR = 0.50, 1.50
NO_VIA_PREFIX = ("U", "J", "Y", "SW", "L", "F", "D", "Q")      # courtyards a via may not enter (except own part)
STUB_W = {"GND": 0.30, "PWR_5V": 0.50, "PWR_USBA": 0.50, "PWR_0V9": 0.50, "PWR_3V3": 0.40}
LANE_EXIT = 3.0
LANE_EXIT_HARD = 1.6     # D-110: the first 1.6 mm (through the ring-1 row) is a hard keep-out, the rest a soft cost
# D-110 (e) whitelist: pads that get no plane via of their own, and why (check_routing.py FAILs any other pad short
# of its via count). The ring-1 caps below sit in front of the D-104 lane channels: a via at their pad blocked the
# lanes (verifier L3 r1/r2 blocker); their U9 pin reaches the plane through an inner via under the package
# (route_escape.py; VCC_3V3 ones with an L3 finger, escape_fingers.json), and the cap pad through the pin's L1 link.
NO_OWN_VIA = {
    ("C74", "1"): "VDD_0V9 via U9.71 inner via (L1 link C74.1-U9.71)",
    ("C50", "1"): "VDD_0V9 via U9.103 inner via (L1 link C50.1-U9.103)",
    ("C62", "1"): "VCC_3V3 via U9.81 inner via + L3 finger",
    ("C67", "1"): "VCC_3V3 via U9.88 inner via + L3 finger",
    ("C68", "1"): "VCC_3V3 via U9.108 inner via + L3 finger",
    ("C61", "1"): "VCC_3V3 via U9.61 inner via + L3 finger",
    ("C63", "1"): "VCC_3V3 via U9.43 inner via + L3 finger",
    ("C64", "1"): "VCC_3V3 via U9.13 inner via + L3 finger",
    ("C65", "1"): "VCC_3V3 via U9.28 inner via + L3 finger (D-109 a)",
    ("C49", "1"): "VDD_0V9 via U9.54 inner via (D-109 a)",
}
# D-111 (L4): plane vias whose position the critical routing needs elsewhere (D-H5 local moves, recorded):
# U1.2 (USB-C ESD GND) - its via moves from between U1 and J1 (where it blocked the USBC_DM approach to J1.A7)
# under the U1 body, between pins 2 and 5 (tented, 0.23 mm to U1.5 VBUS_5V pad edge).
# U10.9 (WSON exposed pad) and U10.4 (GND pin) - their vias sat in the east / west channels that FSPI_CLK_NAND and
# FSPI_D1 use under U10 (D-106 c); they move south of the package, outside the channels.
FORCED = {("U1", "2"): (49.50, 68.90), ("U10", "9"): (55.50, 43.45), ("U10", "4"): (51.10, 43.30),
          # D-112 l (L4 round 2, recorded local moves; the L2 trial pair corridors do not block these sites, the real
          # L4 pair routes are checked against them): C34.1 via north-east of the pad, so the USB-A pair keeps
          # >= 0.76 mm from VBUS_USBA copper; a straight 0.42 mm flow-through under U2 (U2.2 GND via centred between
          # the pad rows, U2.5 via south of U2). The VCC_3V3 vias of R43.1 and C84.1 near the crystal load caps stay:
          # no legal site further away (ring-1 band inventory, R60 / U11 courtyards), recorded as DEV in D-112 l
          ("C34", "1"): (40.95, 59.30), ("U2", "2"): (36.00, 62.35), ("U2", "5"): (36.00, 64.56),
          # D-115 (L5 round 3): C43's two plane vias stay east of the cap (their round-1/2 sites): with FB3 0.35 mm
          # west and C69 gone, the free search would put the VDD_0V9 via west of C43, into the north lane corridor
          ("C43", "1"): (30.298, 25.950), ("C43", "2"): (30.766, 24.110)}
# GND stitching vias that keep an L3 GND fill island alive (verifier L3 r2 minor: no L3 copper at x 41.6-55,
# y 49.8-55 between S-USB and the VCC5V0_SYS USBA strip). (name, x0, y0, x1, y1, count)
STITCH = [("L3-S-USB-EAST", 41.9, 50.1, 54.7, 54.7, 2)]


def count_for(ref, num, net, func):
    if (ref, num) == ("JP1", "2"):
        return 6
    if (ref, num) in (("R30", "2"), ("NT1", "1"), ("U8", "1")):
        return 2
    if (ref, num) in (("Q1", "3"), ("U8", "5")):
        return 3
    if ref in ("U4", "U5", "U6", "U7") and num == "4":
        return 2
    if net == "GND" and (func.startswith("C_IN") or func.startswith("C_OUT") or ref == "D1"):
        return 2
    return 1


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, "L3_PLANEVIAS")
    R = rl.rules()
    func = {r["ref"]: r["functional"] for r in bl.read_csv("placement.csv")}
    zn = bl.zones()
    sp = rl.board_space(board, R)
    rl.trial_reserve(sp, R)
    lane_exits(board, sp, R)
    load_keepouts()
    set_boxes(board)
    holes = [(z["origin_x"], z["origin_y"]) for z in zn.values() if z["kind"] == "hole"]
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    courts = {}
    for ref, fp in fps.items():
        if ref.startswith(NO_VIA_PREFIX) and not ref.startswith("JP"):
            bb = bl.courtyard_bbox(fp)
            if bb:
                courts[ref] = bb
    allpads = []
    for ref, fp in fps.items():
        for p in fp.Pads():
            allpads.append((ref, p, bl.pad_polygon(p)))
    thth = []
    for ref, fp in fps.items():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0:
                x, y = bl.to_board(p.GetPosition())
                thth.append((x, y, pcbnew.ToMM(p.GetDrillSize().x) / 2))

    # pads to serve
    todo = []
    for ref in sorted(fps, key=sort_key):
        if ref == "U9":
            continue
        fp = fps[ref]
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in rl.PLANE_NETS or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if (ref, p.GetNumber()) in NO_OWN_VIA:
                continue
            todo.append((ref, p.GetNumber(), net, p))
    # most constrained first: ring 1/2 around U9, then the specials, then the rest
    def prio(t):
        ref, num, net, p = t
        x, y = bl.to_board(p.GetPosition())
        d = math.hypot(x - esc.CENTRE[0], y - esc.CENTRE[1])
        # supply pads before GND pads (a GND pad also reaches L2 through the L1 pour; a supply pad has only its via)
        return (0 if d < 12 else 1 if count_for(ref, num, net, func.get(ref, "")) > 1 else 2, net == "GND", d, ref, num)
    todo.sort(key=prio)

    items, rows = [], []
    nfail = nfar = ntrack = 0
    for ref, num, net, p in todo:
        want = count_for(ref, num, net, func.get(ref, ""))
        poly = bl.pad_polygon(p)
        cx, cy = bl.to_board(p.GetPosition())
        cls = R[net][0]
        sw = min(STUB_W.get(cls, 0.30), pad_short(p))
        placed = 0
        for k in range(want):
            best = None
            for reach in (NEAR, FAR):
                cl = candidates(poly, cx, cy, reach)
                if (ref, num) in FORCED and k == 0:
                    fx, fy = FORCED[(ref, num)]
                    cl = [(fx, fy, rl.pt_poly((fx, fy), poly) - rl.VIA_D / 2)]
                for c in cl:
                    vx, vy, gap = c
                    soft = legal_via(vx, vy, net, R, sp, holes, thth, courts, ref, allpads,
                                     forced=(ref, num) in FORCED and k == 0)
                    if soft is None:
                        continue
                    a, b = stub_ends(poly, cx, cy, vx, vy)
                    seg = None
                    for w_try in sorted({sw, min(sw, 0.20), min(sw, 0.15)}, reverse=True):
                        s_try = rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=a, b=b, r=w_try / 2,
                                         fan=rl.in_fan(*a) or rl.in_fan(*b))
                        hard, soft2 = split(sp.conflicts(s_try, extra=0.02), net, (ref, num) in FORCED and k == 0)
                        if not (hard or rl.hole_hits(sp, s_try) or crosses_other_pad(s_try, net, allpads)):
                            seg = s_try
                            break
                    if seg is None:
                        continue
                    cost = gap + SOFT_COST * len(soft | soft2) + (sw - 2 * seg.r)
                    if net in rl.L3_NETS and not planes.in_base(net, vx, vy, margin=planes.FINGER_MARGIN):
                        if base_dist(net, vx, vy) > planes.FINGER_MAX - 2 * planes.FINGER_W:
                            continue      # no L3 finger would reach it: route_powerlinks.py joins this pad instead
                        cost += 2.0
                    if net == "GND" and math.hypot(cx - esc.CENTRE[0], cy - esc.CENTRE[1]) < 12:
                        cost += 0.3 * max(0.0, math.hypot(cx - esc.CENTRE[0], cy - esc.CENTRE[1])
                                          - math.hypot(vx - esc.CENTRE[0], vy - esc.CENTRE[1]))
                    if best is None or cost < best[0]:
                        best = (cost, vx, vy, gap, a, b, seg)
                if best:
                    break
            if best is None:
                break
            _, vx, vy, gap, a, b, seg = best
            items += rl.add_track(board, net, "F", [a, b], 2 * seg.r)
            items.append(rl.add_via(board, net, vx, vy))
            sp.add(seg)
            sp.add(rl.Shape("circle", rl.LAYERS, net, rl.class_clear(net, R), "via", a=(vx, vy), r=rl.VIA_D / 2))
            placed += 1
            rows.append([ref, num, net, round(vx, 3), round(vy, 3), round(gap, 3), "near" if gap <= NEAR + 1e-6
                         else "FAR", planes.in_base(net, vx, vy, margin=planes.FINGER_MARGIN) or ""])
            nfar += gap > NEAR + 1e-6
        if placed == 0:
            # fallback: a short L1 track to the nearest same-net via (or a same-net pad), <= 4 mm, straight
            tgt = []
            for t in sp.items:
                if t.net == net and t.kind == "circle" and t.tag == "via":
                    tgt.append(("via", t.a))
            for r2, p2, poly2 in allpads:
                if p2.GetNetname() == net and not (r2 == ref and p2.GetNumber() == num):
                    tgt.append(("%s.%s" % (r2, p2.GetNumber()), bl.to_board(p2.GetPosition())))
            tgt.sort(key=lambda q: math.hypot(q[1][0] - cx, q[1][1] - cy))
            for name, (tx, ty) in tgt:
                if math.hypot(tx - cx, ty - cy) > 4.0:
                    break
                a, _b = stub_ends(poly, cx, cy, tx, ty)
                w = min(sw, 0.30)
                seg = rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=a, b=(tx, ty), r=w / 2,
                               fan=rl.in_fan(*a) or rl.in_fan(tx, ty))
                hard, soft = split(sp.conflicts(seg, extra=0.02), net)
                if hard or rl.hole_hits(sp, seg) or crosses_other_pad(seg, net, allpads):
                    continue
                items += rl.add_track(board, net, "F", [a, (tx, ty)], w)
                sp.add(seg)
                rows.append([ref, num, net, round(tx, 3), round(ty, 3), round(math.hypot(tx - a[0], ty - a[1]), 3),
                             "TRACK to %s" % name, ""])
                placed = want
                ntrack += 1
                break
        if placed == 0 and net == "GND":
            # no via site and no track: the GND pad joins the L1 GND pour solidly (no thermal spokes), the pour is
            # stitched to L2 by the GND vias around it (D-110 e; check_routing.py whitelist)
            p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            rows.append([ref, num, net, "", "", "", "SOLID to the L1 GND pour", ""])
            continue
        if placed < want:
            nfail += 1
            rows.append([ref, num, net, "", "", "", "MISSING %d of %d" % (want - placed, want), ""])
    for name, x0, y0, x1, y1, cnt in STITCH:
        got = []
        y = y0
        cands = []
        while y <= y1:
            x = x0
            while x <= x1:
                cands.append((round(x, 2), round(y, 2)))
                x += 0.25
            y += 0.25
        mid = ((x0 + x1) / 2, (y0 + y1) / 2)
        cands.sort(key=lambda c: abs(c[0] - mid[0]) + abs(c[1] - mid[1]))
        for vx, vy in cands:
            if len(got) >= cnt:
                break
            if any(math.hypot(vx - gx, vy - gy) < 3.0 for gx, gy in got):
                continue
            if legal_via(vx, vy, "GND", R, sp, holes, thth, courts, "", allpads) is None:
                continue
            items.append(rl.add_via(board, "GND", vx, vy))
            sp.add(rl.Shape("circle", rl.LAYERS, "GND", rl.class_clear("GND", R), "via", a=(vx, vy), r=rl.VIA_D / 2))
            got.append((vx, vy))
            rows.append(["STITCH", name, "GND", vx, vy, "", "stitch", ""])
        if len(got) < cnt:
            rows.append(["STITCH", name, "GND", "", "", "", "MISSING %d of %d" % (cnt - len(got), cnt), ""])
    rl.group(board, "L3_PLANEVIAS", items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ref", "pad", "net", "via_x", "via_y", "gap_mm", "status", "l3_region"])
        w.writerows(rows)
    nv = sum(1 for r in rows if r[3] != "" and not r[6].startswith("TRACK"))
    print("plane vias: %d pads, %d vias placed, %d FAR (0.5-%.1f mm), %d pads by a track to a same-net via/pad, "
          "%d pads short of their count -> %s" % (len(todo), nv, nfar, FAR, ntrack, nfail, OUT_CSV))
    for r in rows:
        if r[6].startswith("MISSING"):
            print("  %s.%s %s %s" % (r[0], r[1], r[2], r[6]))


def base_dist(net, x, y):
    """Distance from a point to the nearest L3 base rectangle of the net (0 inside)."""
    best = 1e9
    for x0, y0, x1, y1 in planes.base_rects(net):
        dx = max(x0 - x, 0, x - x1)
        dy = max(y0 - y, 0, y - y1)
        best = min(best, dx + dy)
    return best


def sort_key(ref):
    import re
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def pad_short(p):
    s = p.GetSize()
    return min(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y))


def candidates(poly, cx, cy, reach):
    """Via centres around the pad with copper gap (via edge to pad edge) <= reach, sorted by gap."""
    out = []
    for i in range(48):
        ang = 2 * math.pi * i / 48
        dx, dy = math.cos(ang), math.sin(ang)
        # distance from the centre to the pad boundary along the ray
        lo, hi = 0.0, 5.0
        for _ in range(30):
            m = (lo + hi) / 2
            if rl.inside(cx + dx * m, cy + dy * m, poly):
                lo = m
            else:
                hi = m
        for g10 in range(1, int(reach * 100) + 1, 5):
            g = 0.1 + (g10 - 1) / 100.0
            if g > reach + 1e-9:
                break
            vx, vy = cx + dx * (hi + rl.VIA_D / 2 + g), cy + dy * (hi + rl.VIA_D / 2 + g)
            gap = rl.pt_poly((vx, vy), poly) - rl.VIA_D / 2
            if 0.05 <= gap <= reach + 1e-6:
                out.append((round(vx, 3), round(vy, 3), gap))
    out.sort(key=lambda c: c[2])
    return out


HARD_TRIAL = ("ETH_DIFF", "USB_DIFF", "XTAL")
BREAKOUT_PAD = {"U11": 2.0, "U1": 0.5, "U2": 0.5, "J1": 0.5}     # D-107 breakout boxes (courtyard + margin)
BOXES = []


def set_boxes(board):
    del BOXES[:]
    for ref, m in BREAKOUT_PAD.items():
        bb = bl.courtyard_bbox(board.FindFootprintByReference(ref))
        BOXES.append((bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m))


def in_box(t):
    cx, cy = (t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in BOXES)
SOFT_COST = 0.6


def split(conf, net, forced=False):
    """Hard conflicts (real copper; trial corridors of diff pairs/crystals) vs soft ones (trial corridors of the
    other critical nets and the gate-lane exits: L4 routes around a via; each soft net costs SOFT_COST)."""
    R = rl.rules()
    hard, soft = [], set()
    for t, d, need in conf:
        if t.tag in ("trial", "trialvia"):
            cls = R[t.net][0]
            if cls in HARD_TRIAL:
                if forced and cls in ("USB_DIFF", "ETH_DIFF"):
                    continue          # D-112 l: a FORCED site placed for the real L4 pair route (l4_route.py checks it)
                if net == "GND" and cls != "XTAL" and d >= R[t.net][2] - 1e-6 + 0.02:
                    continue          # GND vias: the DRU 30 mil pair rule excludes GND, class clearance suffices
                if net == "GND" and cls != "XTAL" and in_box(t):
                    continue          # D-110: GND via of an ESD/mux pad inside a D-107 breakout box (U2.2, R60.2):
                    #                   the trial pair there is a placeholder; L4 routes the pair around the via
                if cls != "XTAL" and d >= 0.21 and in_box(t):
                    continue          # D-107 breakout boxes: pairs keep the class clearance 0.15 (+0.06) there
                hard.append(t)
            else:
                soft.add(t.net)
        elif t.tag == "lane-exit":
            hard.append(t)            # D-110: hard (the soft cost let ring-1 vias into the lane channels)
        elif t.tag == "lane-exit-far":
            soft.add(t.net)
        else:
            hard.append(t)
    return hard, soft


KEEPOUTS = []          # (rect, allowed net, name): D-110 escape fingers and the VDD_0V9 neck free strips


def load_keepouts():
    import json
    del KEEPOUTS[:]
    with open(os.path.join(bl.PCB_DIR, "escape_fingers.json"), encoding="utf-8") as fh:
        for f in json.load(fh):
            KEEPOUTS.append((tuple(f["rect"]), f["net"], "finger U9.%d" % f["pin"]))
    for name, x0, y0, x1, y1 in planes.NECK_FREE:
        KEEPOUTS.append(((x0, y0, x1, y1), "VDD_0V9", name))


KO_CLEAR = 0.30 + rl.VIA_D / 2 + 0.02


def rect_pt(r, x, y):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


def rect_rect(a, b):
    dx = max(a[0] - b[2], 0.0, b[0] - a[2])
    dy = max(a[1] - b[3], 0.0, b[1] - a[3])
    return math.hypot(dx, dy)


def keepout_hit(vx, vy, net, ref=""):
    """True if a via of `net` at (vx, vy), or the L3 finger planes.py would draw for it, comes into a keep-out of
    another net."""
    for r, allowed, _name in KEEPOUTS:
        if allowed != net and rect_pt(r, vx, vy) < KO_CLEAR:
            return True
    if net in rl.L3_NETS and not planes.in_base(net, vx, vy, margin=planes.FINGER_MARGIN):
        for f in planes.fingers([(net, vx, vy, ref)]):
            fr = f[2:6]
            for r, allowed, _name in KEEPOUTS:
                if allowed != net and rect_rect(r, fr) < planes.L3_GAP:
                    return True
    return False


def legal_via(vx, vy, net, R, sp, holes, thth, courts, own, allpads, forced=False):
    if not (0.70 <= vx <= 79.30 and 0.70 <= vy <= 79.30):
        return None
    if keepout_hit(vx, vy, net, own):
        return None
    if any(math.hypot(vx - hx, vy - hy) < 3.5 + 0.30 for hx, hy in holes):
        return None
    for ref, bb in courts.items():
        if ref != own and bb[0] - 0.05 <= vx <= bb[2] + 0.05 and bb[1] - 0.05 <= vy <= bb[3] + 0.05:
            return None
    if rl.in_fan(vx, vy):
        return None
    for _ref, _p, poly in allpads:
        if abs(poly[0][0] - vx) < 4 and abs(poly[0][1] - vy) < 4:
            if rl.pt_poly((vx, vy), poly) < rl.VIA_D / 2 + 0.05:
                return None
    vs = rl.Shape("circle", rl.LAYERS, net, rl.class_clear(net, R), "via", a=(vx, vy), r=rl.VIA_D / 2)
    hard, soft = split(sp.conflicts(vs, extra=0.02), net, forced)
    if hard:
        return None
    hole = rl.Shape("circle", rl.LAYERS, net, rl.HOLE_CLEAR, "hole", a=(vx, vy), r=rl.VIA_DRILL / 2)
    if [c for c in sp.conflicts(hole, extra=0.02) if c[0].kind in ("seg", "poly")
            and c[0].tag not in ("trial", "trialvia", "lane-exit", "lane-exit-far")]:
        return None
    for c in sp.near(vs, 1.2):
        if c.kind == "circle" and c.tag in ("via", "trialvia"):
            if math.hypot(c.a[0] - vx, c.a[1] - vy) < rl.HOLE_PITCH + 0.02:
                return None
    for hx, hy, hr in thth:
        if math.hypot(hx - vx, hy - vy) - hr - rl.VIA_DRILL / 2 < 0.45 + 0.02:
            return None
    return soft


def stub_ends(poly, cx, cy, vx, vy):
    """Stub from the pad copper nearest to the via (0.10 mm inside the pad edge) to the via centre: on a large pad
    (an exposed pad) the stub must not run from the pad centre across the part's other pads."""
    best = None
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((vx - ax) * dx + (vy - ay) * dy) / L))
        qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(vx - qx, vy - qy)
        if best is None or d < best[0]:
            best = (d, qx, qy)
    _, qx, qy = best
    L = math.hypot(cx - qx, cy - qy)
    if L > 0.2:
        qx, qy = qx + (cx - qx) * 0.1 / L, qy + (cy - qy) * 0.1 / L
    else:
        qx, qy = cx, cy
    return (qx, qy), (vx, vy)


def crosses_other_pad(seg, net, allpads):
    for _ref, p, poly in allpads:
        n = p.GetNetname()
        if n == net:
            continue
        if abs(poly[0][0] - seg.a[0]) > 4 or abs(poly[0][1] - seg.a[1]) > 4:
            continue
        if rl.seg_poly(seg.a, seg.b, poly) - seg.r < 0.10:
            return True
    return False


def lane_exits(board, sp, R):
    """Reserve a radial corridor (3 mm) beyond every U9 gate lane end (r 8.0), so plane vias leave the lanes a way out."""
    import json
    with open(os.path.join(bl.PCB_DIR, "escape_geom_in.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    n = 0
    ends = {}
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" and t.GetLayer() == pcbnew.F_Cu:
            for e in (bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())):
                ends[(round(e[0], 2), round(e[1], 2))] = t.GetNetname()
    netpads = {}
    for fp in board.GetFootprints():
        if fp.GetReference() == "U9":
            continue
        for p in fp.Pads():
            netpads.setdefault(p.GetNetname(), []).append(bl.to_board(p.GetPosition()))
    for side, d in data.items():
        for it in d["items"]:
            if it["kind"] != "lane":
                continue
            a = esc.point(side, it["tg"], 8.0)
            lnet = None
            for (ex, ey), en in ends.items():
                if abs(ex - a[0]) < 0.03 and abs(ey - a[1]) < 0.03:
                    lnet = en
                    break
            if lnet and any(math.hypot(q[0] - a[0], q[1] - a[1]) < 1.5 for q in netpads.get(lnet, [])):
                continue          # the lane's own pad is next to its gate (NPOR -> C71.1): no exit corridor
            b = esc.point(side, it["tg"], 8.0 + LANE_EXIT)
            m = esc.point(side, it["tg"], 8.0 + LANE_EXIT_HARD)
            sp.add(rl.Shape("seg", ["F"], "#LANE%s%d" % (side, int(it["key"])), 0.15, "lane-exit", a=a, b=m,
                            r=0.075))
            sp.add(rl.Shape("seg", ["F"], "#LANE%s%d" % (side, int(it["key"])), 0.15, "lane-exit-far", a=m, b=b,
                            r=0.075))
            n += 1
    return n


if __name__ == "__main__":
    main()
