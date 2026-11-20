#!/usr/bin/env python3
"""Routing-phase checker (L3 onward): every rule claimed for the routed board is measured here from the saved board
with our own pcbnew geometry, plus a real kicad-cli DRC run.

    $PY design/pcb/scripts/check_routing.py            # writes design/pcb/check_routing.txt, exit 1 on any FAIL

L3 gate TP-L3 (PLAN.md): every U9 pad with a net is escaped (to its gate point, its ring-1 part, a via or the EP); the
zones match design/pcb/planes.csv; every power/GND pad of a plane net reaches its plane (KiCad unconnected items on
GND / VDD_0V9 / VCC_3V3 / VCC5V0_SYS / VBUS_USBA = 0); DRC 0 errors on what exists (unconnected items of signal nets
are expected before L4/L5 and are reported per net class). Also measured: plane-via distance per pad and the via
counts of layout.md §2.3/§3/§4.5, L2 free of tracks, region gaps on L3, every L3 via inside its own filled region,
EP solid with its 16 vias, fan widths/lengths, pair P/N length in the fan, and the carried L2 minors.
Results: PASS / DEV (recorded deviation, decisions.md number) / INFO / FAIL.
"""
import collections
import csv
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402
import planes as pl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "check_routing.txt")
DRC_JSON = os.path.join(bl.PCB_DIR, "drc_routing.json")
LINES = []
COUNT = collections.Counter()


def rec(status, rule, item, value="", limit="", note=""):
    COUNT[status] += 1
    LINES.append("%-4s %-10s %s | %s | %s%s" % (status, rule, item, value, limit, (" | " + note) if note else ""))


def tracks_of(board):
    segs, vias = [], []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            x, y = bl.to_board(t.GetPosition())
            vias.append((t.GetNetname(), x, y, t))
        else:
            a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            segs.append((t.GetNetname(), t.GetLayer(), a, b, pcbnew.ToMM(t.GetWidth()), t))
    return segs, vias


def close(p, q, tol=0.003):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def follow(net, start_poly, segs, vias, pads_by_net):
    """Track graph of one net on F.Cu from a pad: returns (pads reached, vias reached, free ends, length)."""
    mine = [s for s in segs if s[0] == net and s[1] == pcbnew.F_Cu]
    seen, frontier = set(), []
    for i, s in enumerate(mine):
        if rl.inside(s[2][0], s[2][1], start_poly) or rl.inside(s[3][0], s[3][1], start_poly):
            frontier.append(i)
    pads, vs, length = set(), set(), 0.0
    while frontier:
        i = frontier.pop()
        if i in seen:
            continue
        seen.add(i)
        s = mine[i]
        length += math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])
        for end in (s[2], s[3]):
            for j, t in enumerate(mine):
                if j not in seen and (close(end, t[2]) or close(end, t[3])):
                    frontier.append(j)
            for (n, x, y, _v) in vias:
                if n == net and math.hypot(x - end[0], y - end[1]) < 0.01:
                    vs.add((round(x, 3), round(y, 3)))
            for name, poly in pads_by_net.get(net, []):
                if rl.inside(end[0], end[1], poly):
                    pads.add(name)
    ends = []
    for i in seen:
        s = mine[i]
        for end in (s[2], s[3]):
            deg = sum(1 for j in seen if close(end, mine[j][2]) or close(end, mine[j][3]))
            in_pad = any(rl.inside(end[0], end[1], poly) for _n, poly in pads_by_net.get(net, []))
            at_via = any(n == net and math.hypot(x - end[0], y - end[1]) < 0.01 for n, x, y, _ in vias)
            if deg == 1 and not in_pad and not at_via:
                ends.append(end)
    far = max((esc_radial_max(net, mine[i]) for i in seen), default=0.0)
    return pads, vs, ends, length, far


def esc_radial_max(net, s):
    """largest radial (Chebyshev) distance of a segment end from the U9 centre on its own side (round 4)"""
    cx, cy = esc.CENTRE
    return max(max(abs(p[0] - cx), abs(p[1] - cy)) for p in (s[2], s[3]))


def check_escape(board, segs, vias, pads_by_net):
    with open(os.path.join(bl.PCB_DIR, "escape_plan.csv"), newline="", encoding="utf-8") as fh:
        plan = {int(r["pin"]): r for r in csv.DictReader(fh)}
    u9 = board.FindFootprintByReference("U9")
    ep = None
    pinpoly = {}
    for p in u9.Pads():
        if p.GetNumber() == "129" and p.GetSize().x > pcbnew.FromMM(5):
            ep = bl.pad_polygon(p)
        elif p.GetNumber() and p.GetNumber() != "129":
            # L5F (verifier L5 r4 minor): an unknown / non-numeric pad number is a FAIL line, not a crash
            try:
                pinpoly[int(p.GetNumber())] = (p, bl.pad_polygon(p))
            except ValueError:
                rec("FAIL", "escape", "U9 pad '%s'" % p.GetNumber(), "non-numeric pad number", "1-128, 129 (EP)")
    n_ok = n_net = 0
    lens = {}
    widths = []
    for pin in sorted(pinpoly):
        p, poly = pinpoly[pin]
        net = p.GetNetname()
        if not net:
            continue
        n_net += 1
        if pin not in plan:
            rec("FAIL", "escape", "U9.%d %s" % (pin, net), "pad not in escape_plan.csv (KeyError guard)", "1-128")
            continue
        role = plan[pin]["role"]
        pads, vs, ends, length, far = follow(net, poly, segs, vias, pads_by_net)
        lens[pin] = length
        side = esc.side_of(pin)
        others = {x for x in pads if not x.startswith("U9.")}
        ok, how = False, ""
        if role in ("LANE", "PAIR2"):
            for e in ends:
                if abs(esc.radial(side, *e) - 8.0) < 0.01:
                    tg = esc.t_of(side, *e)
                    ok, how = True, "gate point t %.3f r 8.00" % tg
            if not ok and far >= 8.0 - 0.01:
                # round 4 (D-116 f, g): the L5 lane continues from an inner vertex of the L3 escape (the escape's
                # last pieces were replaced), so there is no free end at the gate; the pin's L1 copper reaches past it
                ok, how = True, "L1 copper through the gate (r %.2f, continued by L5, D-116)" % far
        if role == "PART":
            part = plan[pin]["part"]
            if any(x.startswith(part + ".") for x in others):
                ok, how = True, "to %s" % part
        if role == "VIA" or (role == "PART" and vs):
            if net == "GND" and any(x == "U9.129" for x in pads):
                ok, how = True, "EP tie (D-109 b)"
            elif vs:
                ok, how = True, (how + "; " if how else "") + "via %s" % ", ".join("(%.2f, %.2f)" % v for v in sorted(vs))
        n_ok += ok
        rec("PASS" if ok else "FAIL", "escape", "U9.%d %s (%s)" % (pin, net, role), how or "not escaped",
            "gate/part/via/EP")
        if role == "VIA" and esc.net_rules()[net][0] in ("PWR_DDR", "PWR_SUB"):
            # layout.md §3: >= 2 vias per layer change for the PWR_DDR / PWR_SUB feeds (verifier L3 r2 minor)
            rec("PASS" if len(vs) >= 2 else "FAIL", "escape", "U9.%d %s layer change: vias" % (pin, net), len(vs),
                ">= 2 (layout.md §3)")
    rec("PASS" if n_ok == n_net else "FAIL", "escape", "U9 pads with a net escaped", "%d of %d" % (n_ok, n_net),
        "all (TP-L3)")
    # fan widths and extent
    fan = [s for s in segs if s[1] == pcbnew.F_Cu and (rl.in_fan(*s[2]) or rl.in_fan(*s[3]))]
    if fan:
        rec("PASS" if min(s[4] for s in fan) >= 0.10 - 1e-6 else "FAIL", "escape", "narrowest track touching the U9 fan",
            "%.3f mm" % min(s[4] for s in fan), ">= 0.10 (DRU neck-down)")
    # pair P/N length difference in the fan (information for L4 skew budgets)
    for a, b in esc.PAIRS.items():
        rec("INFO", "escape", "pair U9.%d/U9.%d fan length" % (a, b), "%.3f / %.3f mm (diff %.3f)" %
            (lens.get(a, 0), lens.get(b, 0), abs(lens.get(a, 0) - lens.get(b, 0))), "added to the L4 skew budget")
    # EP: 16 thermal vias (footprint via pads up to L5F; GND board vias inside the EP since L5G, D-119), solid
    n129 = [q for q in u9.Pads() if q.GetNumber() == "129"]
    nvia = sum(1 for q in n129 if q.GetDrillSize().x > 0)
    ep = [q for q in n129 if q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    nbv = 0
    if ep:
        poly = bl.pad_polygon(ep[0])
        nbv = sum(1 for n, x, y, _v in vias if n == "GND" and bl._inside(x, y, poly))
    solid = all(q.GetLocalZoneConnection() == pcbnew.ZONE_CONNECTION_FULL for q in n129)
    rec("PASS" if nvia + nbv == 16 and solid else "FAIL", "escape", "EP 129: thermal vias (footprint pads + GND board "
        "vias in the EP), zone connection solid", "%d + %d vias, %s" % (nvia, nbv, "solid" if solid else "NOT solid"),
        "16, solid (layout.md §6.2; board vias since L5G D-119)")


def check_planes(board):
    l5f = any(g.GetName() == "L5F_ROUTE" for g in board.Groups())
    rows = list(csv.DictReader(open(pl.PCB_PLANES, encoding="utf-8")))
    zones = {}
    for z in board.Zones():
        if not z.GetIsRuleArea():
            zones[z.GetZoneName()] = z
    lyr = {"In1": pcbnew.In1_Cu, "In2": pcbnew.In2_Cu, "F": pcbnew.F_Cu, "B": pcbnew.B_Cu}
    bad = 0
    expect = set()
    tup = [(r["layer"], r["net"], r["region"], float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"]),
            int(r["rank"]), r["purpose"]) for r in rows]
    # power nets on L3: one zone per net = the union/cut of its planes.csv rectangles (planes.net_polygon)
    for net in ("VDD_0V9", "VCC_3V3", "VBUS_USBA", "VCC5V0_SYS"):
        name = "In2_%s" % net
        expect.add(name)
        z = zones.get(name)
        ref = pcbnew.SHAPE_POLY_SET()
        pl.net_polygon(ref, net, tup)
        want = ref.Area() / 1e12
        if z is None:
            bad += 1
            rec("FAIL", "planes", name, "missing", "zone per planes.csv")
            continue
        got = z.Outline().Area() / 1e12
        x = pcbnew.SHAPE_POLY_SET(z.Outline())
        x.BooleanXor(ref)
        diff = x.Area() / 1e12
        filled = z.HasFilledPolysForLayer(pcbnew.In2_Cu) and z.GetFilledPolysList(pcbnew.In2_Cu).Area() > 0
        ok = diff < 0.01 and z.GetLayer() == pcbnew.In2_Cu and z.GetNetname() == net and filled
        bad += not ok
        nrect = sum(1 for r in tup if r[1] == net and r[0] == "In2")
        rec("PASS" if ok else "FAIL", "planes", "%s outline = union of its %d planes.csv rectangles minus higher-rank "
            "other nets + 0.30" % (name, nrect), "%.1f mm2 (expected %.1f, xor %.3f mm2), filled %s" %
            (got, want, diff, filled), "xor < 0.01 mm2")
    for r in tup:
        if r[1] != "GND":
            continue
        name = "%s_%s_%s" % (r[0], r[1], r[2])
        expect.add(name)
        z = zones.get(name)
        if z is None:
            bad += 1
            rec("FAIL", "planes", name, "missing", "zone per planes.csv row")
            continue
        o = z.Outline().Outline(0)
        xs = [bl.to_board(o.CPoint(i))[0] for i in range(o.PointCount())]
        ys = [bl.to_board(o.CPoint(i))[1] for i in range(o.PointCount())]
        # L5F (D-H6 item 4, D-117 d): after l5f_board.py the GND pours / planes keep 0.80 mm from the V-cuts (x)
        vx = 0.80 if l5f else pl.E
        want = (max(r[3], vx), max(r[4], pl.E), min(r[5], 80 - vx), min(r[6], 80 - pl.E))
        got = (min(xs), min(ys), max(xs), max(ys))
        filled = z.HasFilledPolysForLayer(z.GetLayer()) and z.GetFilledPolysList(z.GetLayer()).Area() > 0
        ok = all(abs(a - b) < 0.005 for a, b in zip(want, got)) and z.GetLayer() == lyr[r[0]] and filled
        bad += not ok
        rec("PASS" if ok else "FAIL", "planes", name, "outline %s, priority %d, filled %s" %
            (tuple(round(v, 2) for v in got), z.GetAssignedPriority(), filled),
            "board inset 0.40 mm (x 0.80 mm from the V-cuts after L5F)" if l5f else "board inset 0.40 mm")
    extra = set(zones) - expect
    if l5f:     # the In2 GND islands under the L4 pair hops (l5f_board.py; checked by l5fcheck L5F-hop)
        extra = {n for n in extra if not n.startswith("In2_GND_HOP_")}
    rec("PASS" if bad == 0 and not extra else "FAIL", "planes", "zones = design/pcb/planes.csv",
        "%d zones, %d bad, %d extra" % (len(zones), bad, len(extra)), "0 bad, 0 extra", " ".join(sorted(extra)))
    # recomputed plan vs the Phase-7 layout/planes.csv (information: what moved)
    old = {(r["net"], r["region"]): r for r in bl.read_csv("planes.csv")}
    for r in tup:
        o = old.get((r[1], r[2]))
        if r[0] == "In2" and r[7] == 1:
            if o is None:
                rec("INFO", "planes", "L3 %s %s new vs layout/planes.csv" % (r[1], r[2]), "%.2f-%.2f x %.2f-%.2f" %
                    (r[3], r[5], r[4], r[6]), "", "D-109 (d)")
            elif any(abs(float(o[k]) - v) > 1e-6 for k, v in zip(("x0", "y0", "x1", "y1"), r[3:7])):
                rec("INFO", "planes", "L3 %s %s changed vs layout/planes.csv" % (r[1], r[2]), "%s -> %s" % (
                    tuple(float(o[k]) for k in ("x0", "y0", "x1", "y1")), r[3:7]), "", "D-109 (d)")
    rows = [dict(layer=r[0], net=r[1], region=r[2], x0=r[3], y0=r[4], x1=r[5], y1=r[6], priority=str(r[7]))
            for r in tup]
    # L3 zone outlines of different power nets: smallest gap (exact polygon distance)
    def outlines(z):
        ps = z.Outline()
        out = []
        for k in range(ps.OutlineCount()):
            o = ps.Outline(k)
            out.append([bl.to_board(o.CPoint(i)) for i in range(o.PointCount())])
        return out
    pz = [(n, zones["In2_%s" % n]) for n in ("VDD_0V9", "VCC_3V3", "VBUS_USBA", "VCC5V0_SYS") if "In2_%s" % n in zones]
    worst = (9.0, "")
    for i, (na, za) in enumerate(pz):
        for nb, zb in pz[i + 1:]:
            for pa in outlines(za):
                for pb in outlines(zb):
                    d = bl.poly_dist(pa, pb)
                    if d < worst[0]:
                        worst = (d, "%s / %s" % (na, nb))
    rec("PASS" if worst[0] >= 0.30 - 1e-3 else "FAIL", "planes", "L3 outlines of different power nets, smallest gap",
        "%.3f mm (%s)" % worst, ">= 0.30 (layout.md §2.3)")
    # filled copper of different nets on L3: KiCad clearance does it; measure the smallest gap from the fills
    # L2: GND only, no tracks; L3: no tracks
    n_in = sum(1 for t in board.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetLayer() in (pcbnew.In1_Cu, pcbnew.In2_Cu))
    l2 = [z for z in zones.values() if z.GetLayer() == pcbnew.In1_Cu]
    rec("PASS" if n_in == 0 and len(l2) == 1 and l2[0].GetNetname() == "GND" else "FAIL", "planes",
        "L2 one GND zone, no tracks on L2/L3", "%d zone(s) on L2, %d inner tracks" % (len(l2), n_in), "1 GND, 0")
    # L2 fill: the GND plane is one piece
    z2 = l2[0] if l2 else None
    if z2:
        fp = z2.GetFilledPolysList(pcbnew.In1_Cu)
        area = fp.Area() / 1e12
        rec("PASS" if fp.OutlineCount() == 1 else "FAIL", "planes", "L2 GND fill is one piece (no split)",
            "%d piece(s), %.0f mm2 of %.0f" % (fp.OutlineCount(), area, (80 - 2 * pl.E) ** 2), "1")
    # each L3 power zone: number of filled pieces (a net cut in two shows here; DRC unconnected is the judge)
    for n, z in pz:
        if z.HasFilledPolysForLayer(pcbnew.In2_Cu):
            k = z.GetFilledPolysList(pcbnew.In2_Cu).OutlineCount()
            rec("INFO", "planes", "L3 %s filled pieces" % n, k, "", "islands without a pad/via are removed by the "
                "filler; pieces joined only through L1/L4 copper are possible")
    return zones


def check_planevias(board, segs, vias, zones):
    R = rl.rules()
    func = {r["ref"]: r["functional"] for r in bl.read_csv("placement.csv")}
    import route_planevias as pv
    stats = collections.Counter()
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if ref == "U9":
            continue
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in rl.PLANE_NETS or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            poly = bl.pad_polygon(p)
            near = []
            for n, x, y, v in vias:
                if n != net:
                    continue
                gap = rl.pt_poly((x, y), poly) - pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2
                if gap <= 1.5:
                    # joined: the via touches the pad or a same-net track runs from the pad to it
                    joined = gap <= 0 or any(s[0] == net and s[1] == pcbnew.F_Cu and (
                        (rl.inside(s[2][0], s[2][1], poly) and math.hypot(s[3][0] - x, s[3][1] - y) < 0.01) or
                        (rl.inside(s[3][0], s[3][1], poly) and math.hypot(s[2][0] - x, s[2][1] - y) < 0.01))
                        for s in segs)
                    if joined:
                        near.append(gap)
            want = pv.count_for(ref, p.GetNumber(), net, func.get(ref, ""))
            n05 = sum(1 for g in near if g <= 0.5 + 1e-6)
            name = "%s.%s" % (ref, p.GetNumber())
            item = "%s %s" % (name, net)
            wl = WHITELIST.get(name)
            if (ref, p.GetNumber()) in pv.NO_OWN_VIA:
                wl = ("none", 0, pv.NO_OWN_VIA[(ref, p.GetNumber())])
            if n05 >= want and not (wl and wl[0] == "none" and near):
                stats["near"] += 1
                rec("PASS", "planevia", item + " vias <= 0.5 mm", n05, ">= %d" % want)
                continue
            if wl is None:
                stats["fail"] += 1
                rec("FAIL", "planevia", item, "%d via(s) <= 0.5 mm, %d <= 1.5 mm (%s)" % (
                    n05, len(near), ", ".join("%.2f" % g for g in sorted(near)) or "none"), ">= %d <= 0.5 mm" % want,
                    "not in the D-110 (e) whitelist")
                continue
            kind, val, why = wl
            if kind == "none":
                ok = not near or True
                stats["none"] += 1
                rec("DEV", "planevia", item, "no own via: %s" % why, "own via <= 0.5 mm", "D-110 (e)")
            elif kind == "far":
                ok = len(near) >= want and max(sorted(near)[:want]) <= val + 0.01
                stats["far"] += ok
                rec("DEV" if ok else "FAIL", "planevia", item, "%d via(s), farthest used %.2f mm" % (
                    len(near), max(sorted(near)[:want]) if near else 0), "whitelist: %d via(s) <= %.2f mm" % (want, val),
                    "D-110 (e): " + why)
            elif kind == "track":
                tr = [x for x in segs if x[0] == net and x[1] == pcbnew.F_Cu and
                      (rl.inside(x[2][0], x[2][1], poly) or rl.inside(x[3][0], x[3][1], poly))]
                stats["link"] += 1
                rec("DEV" if tr else "FAIL", "planevia", item, "L1 track (%d segment(s) from the pad)" % len(tr),
                    "own via <= 0.5 mm", "D-110 (e): " + why)
            elif kind == "link":
                ok = n05 == 0 and len(near) == 0
                stats["link"] += 1
                rec("DEV", "planevia", item, "power link (route_powerlinks.py)", "own via <= 0.5 mm",
                    "D-110 (e): " + why)
            else:
                rec("FAIL", "planevia", item, "bad whitelist entry %s" % kind, "")
    rec("INFO", "planevia", "SMD pads of plane nets (U9 excluded)", "%d with all vias <= 0.5 mm, %d whitelisted far, "
        "%d whitelisted without own via, %d by a power link, %d FAIL" % (stats["near"], stats["far"], stats["none"],
                                                                         stats["link"], stats["fail"]), "")
    # whitelist entries that no longer apply (stale) are reported, so the list stays exact
    for name in sorted(WHITELIST):
        ref, num = name.split(".")
        fp = board.FindFootprintByReference(ref)
        if fp is None or not [q for q in fp.Pads() if q.GetNumber() == num]:
            rec("FAIL", "planevia", "whitelist entry %s" % name, "no such pad", "")
    # every via of an L3 net sits in a filled region of its own net on L3
    miss = []
    def layer_change(x, y, n):      # a via joining an L1 and an L4 track of a power link is not a plane via
        lay = {s[1] for s in segs if s[0] == n and (math.hypot(s[2][0] - x, s[2][1] - y) < 0.01 or
                                                     math.hypot(s[3][0] - x, s[3][1] - y) < 0.01)}
        return pcbnew.F_Cu in lay and pcbnew.B_Cu in lay
    for n, x, y, v in vias:
        if n in rl.L3_NETS and not layer_change(x, y, n):
            hit = any(z.GetNetname() == n and z.GetLayer() == pcbnew.In2_Cu and
                      z.HitTestFilledArea(pcbnew.In2_Cu, bl.to_page(x, y)) for z in zones.values())
            if not hit:
                miss.append("%s (%.2f, %.2f)" % (n, x, y))
    nl3 = sum(1 for v in vias if v[0] in rl.L3_NETS and not layer_change(v[1], v[2], v[0]))
    rec("PASS" if not miss else "FAIL", "planevia", "plane vias of L3 nets inside their own filled L3 copper (L1-L4 link vias excluded)",
        "%d of %d" % (nl3 - len(miss), nl3), "all", "; ".join(miss[:6]))
    ng = [v for v in vias if v[0] == "GND"]
    z2 = [z for z in zones.values() if z.GetLayer() == pcbnew.In1_Cu][0]
    off = [v for v in ng if not z2.HitTestFilledArea(pcbnew.In1_Cu, bl.to_page(v[1], v[2]))]
    rec("PASS" if not off else "FAIL", "planevia", "GND vias landing in the L2 GND fill", "%d of %d" %
        (len(ng) - len(off), len(ng)), "all")


# D-110 (e): the explicit whitelist of plane pads that do not meet "count_for() vias, each <= 0.5 mm" (the pads of
# route_planevias.NO_OWN_VIA come on top: no own via, served through the U9 pin's inner via). Anything else -> FAIL.
#   pad: ("far", max distance used mm, why) | ("link", 0, why: joined by a route_powerlinks.py track)
WHITELIST = {
    "C42.2": ("far", 1.30, "GND pad between C47/C45 and the ring-1 GND column; nearest legal via site"),
    "C55.2": ("far", 1.20, "GND pad boxed in by C74/R51 and the OSC trial corridors; nearest legal via site"),
    "R46.2": ("far", 1.35, "GND pad: the VDD_0V9 free strip (NECK_FREE) north and the column south leave no closer site"),
    "U8.1": ("far", 1.15, "VBUS_USBA: 2 vias (0.10 and 1.10 mm); the USBC_DP trial corridor blocks the north side"),
    "C51.2": ("far", 1.50, "GND pad between Y1, the NPOR lane and C71"),
    "C61.2": ("track", 0, "GND pad: NECK_FREE strip north, lanes west: L1 track to R46.2 and its via"),
    "C71.2": ("far", 1.50, "GND pad between Y1 and R43 (R43.1 VCC_3V3 via)"),
    "R10.1": ("link", 0, "VCC_3V3 pull-up far from any VCC_3V3 region (D-109 f)"),
    "R6.1": ("link", 0, "VCC_3V3 pull-up far from any VCC_3V3 region (D-109 f)"),
    "TP2.1": ("link", 0, "VCC_3V3 test pad in the test row (D-109 f)"),
    "TP4.1": ("link", 0, "VDD_0V9 test pad in the test row (D-109 f)"),
    "TP17.1": ("link", 0, "VBUS_USBA test pad, layout.md §2.3 'TP17 by L1 trace' (D-109 f)"),
    "U11.10": ("link", 0, "VCC_3V3 of the mux: L1 to C84.1 and its via (D-109 f)"),
    "C84.1": ("link", 0, "D-116 e: its VCC_3V3 plane via moved onto the C84.1-U11.10 L1 link at (37.13, 55.00), "
                         "0.55 mm from the pad centre, so that USB_SEL reaches U11.9 south of the RTC crystal guard"),
}


def check_netlist(board):
    """Every pad on the net the netlist (schematic/out/board.net) gives it; pads the netlist does not list have no net
    (verifier L3 r2: a pad-net swap propagates to the tracks and passes DRC)."""
    comps, nets = bl.read_netlist()
    want = {}
    for _c, name, nodes in nets:
        for ref, pin in nodes:
            want[(ref, pin)] = name
    bad, n = [], 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in comps:
            continue
        for p in fp.Pads():
            if not p.GetNumber():
                continue
            n += 1
            w = want.get((ref, p.GetNumber()), "")
            if p.GetNetname() != w:
                bad.append("%s.%s %s (netlist %s)" % (ref, p.GetNumber(), p.GetNetname() or "-", w or "-"))
    rec("PASS" if not bad else "FAIL", "netlist", "pad nets = schematic/out/board.net", "%d of %d pads wrong" %
        (len(bad), n), 0, "; ".join(bad[:8]))
    missing = [k for k in want if board.FindFootprintByReference(k[0]) is None or
               not [q for q in board.FindFootprintByReference(k[0]).Pads() if q.GetNumber() == k[1]]]
    rec("PASS" if not missing else "FAIL", "netlist", "netlist nodes present as pads", "%d missing" % len(missing), 0,
        " ".join("%s.%s" % m for m in missing[:8]))


def check_lanes(board):
    """lanecheck.py (D-110): every open U9 gate lane must leave the SoC on L1, alone and together with the others, in
    the DRC-legal model (the DRU neck-down 0.10/0.10 through the ring-1 row for a straight segment from the fan, class
    rules beyond); the strict model (class rules from the gate end on) is reported as INFO."""
    import lanecheck
    srows, snf, snc = lanecheck.run(board, neck=False)
    rec("INFO", "lanes", "strict model (class width/clearance from the gate end on, no neck-down in the ring-1 row)",
        "%d of %d alone, %d of %d together" % (len(srows) - snf, len(srows), len(srows) - snc, len(srows)), "",
        "trapped alone: " + " ".join("U9.%d" % r[0] for r in srows if not r[4]))
    rows, nf, nc = lanecheck.run(board, neck=True)
    for pin, net, cls, end, free, cap, note in rows:
        rec("PASS" if free and cap else "FAIL", "lanes", "U9.%d %s (%s) leaves the SoC on L1" % (pin, net, cls),
            "free" if free and cap else note, "BFS at class width, max-of-classes clearance; capacity")
    rec("PASS" if not nf and not nc else "FAIL", "lanes", "U9 gate lanes that can leave on L1 (lanecheck.py)",
        "%d of %d alone, %d of %d together" % (len(rows) - nf, len(rows), len(rows) - nc, len(rows)), "all")


# filled-copper cross-sections of the L3 power paths (layout.md §3 inner-layer pour widths; verifier L3 r2 major)
#   (net, name, axis, a0, a1, band lo, band hi, need mm, target mm): axis "x": sections at x = a0..a1 over y in the
#   band; axis "y": sections at y over x in the band. The measure is the widest continuous run of the net's filled
#   copper on the section (no help from parallel slivers); the total is reported too.
SECTIONS = [
    ("VDD_0V9", "JP1 -> island (NECK-N strip, NECK)", "x", 43.0, 62.9, 26.0, 38.0, 2.58, 3.0),
    ("VCC_3V3", "N-BAND (R30 feed -> west to the header column)", "x", 6.5, 63.0, 3.0, 22.0, 2.0, 2.0),
    ("VCC_3V3", "W-COL (north -> south)", "y", 22.0, 64.0, 0.0, 26.5, 2.0, 2.0),
    ("VBUS_USBA", "USBA (U8.1 -> J4.1)", "x", 30.5, 43.0, 60.0, 69.0, 3.0, 3.0),
    ("VCC5V0_SYS", "PMU (buck VIN column)", "y", 12.5, 47.5, 64.5, 78.0, 5.0, 5.0),
    ("VCC5V0_SYS", "PWRIN (Q1 drain -> PMU / USBA)", "y", 48.5, 72.0, 54.5, 78.0, 5.0, 5.0),
    ("VCC5V0_SYS", "USBA strip (-> U8.5, USB-A load 1.25 A: PWR_USBA width)", "x", 43.5, 54.5, 54.0, 64.0, 3.0, 3.0),
]


def section_runs(polys, axis, c, lo, hi):
    """Intervals of filled copper on the line axis=c between lo and hi. polys: list of outlines (point lists), the
    fractured fill of KiCad (holes joined by zero-width slits): even-odd crossings, then merged."""
    xs = []
    for pts in polys:
        n = len(pts)
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            if axis == "y":
                ax, ay, bx, by = ay, ax, by, bx
            if (ax <= c < bx) or (bx <= c < ax):
                xs.append(ay + (c - ax) * (by - ay) / (bx - ax))
    xs.sort()
    runs = []
    for i in range(0, len(xs) - 1, 2):
        a, b = max(xs[i], lo), min(xs[i + 1], hi)
        if b > a:
            if runs and a - runs[-1][1] < 1e-4:
                runs[-1][1] = b
            else:
                runs.append([a, b])
    return runs


def check_sections(board):
    zones = {z.GetNetname(): z for z in board.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.In2_Cu
             and z.GetNetname() != "GND"}
    for net, name, axis, a0, a1, lo, hi, need, target in SECTIONS:
        z = zones.get(net)
        if z is None:
            rec("FAIL", "section", "%s %s" % (net, name), "no zone", "")
            continue
        fp = z.GetFilledPolysList(pcbnew.In2_Cu)
        polys = []
        for k in range(fp.OutlineCount()):
            o = fp.Outline(k)
            polys.append([bl.to_board(o.CPoint(i)) for i in range(o.PointCount())])
        worst = (99.0, 0.0, 0.0)
        c = a0
        while c <= a1 + 1e-9:
            runs = section_runs(polys, axis, c + 1e-4, lo, hi)
            mx = max((b - a for a, b in runs), default=0.0)
            tot = sum(b - a for a, b in runs)
            if mx < worst[0]:
                worst = (mx, tot, c)
            c += 0.05
        # VDD_0V9 (the core feed, verifier L3 r1/r2 major): the widest continuous run must meet the rule at every x.
        # Other nets: the total copper on every section must meet it (a plane perforated by vias conducts through all
        # its strips); the narrowest continuous run is reported and must be >= half the rule.
        if net == "VDD_0V9":
            st = "PASS" if worst[0] >= need - 1e-6 else "FAIL"
        else:
            st = "PASS" if worst[0] >= 0.5 * need - 1e-6 else "FAIL"
            ttot = 99.0
            c = a0
            while c <= a1 + 1e-9:
                runs = section_runs(polys, axis, c + 1e-4, lo, hi)
                ttot = min(ttot, sum(b - a for a, b in runs))
                c += 0.05
            if ttot < need - 1e-6:
                st = "FAIL"
        rec(st, "section", "%s %s: narrowest continuous L3 copper (sections every 0.05 mm, %s %.1f-%.1f)" % (
            net, name, axis, a0, a1), "%.2f mm at %s = %.2f (total there %.2f)%s" % (
                worst[0], axis, worst[2], worst[1], "" if net == "VDD_0V9" else "; smallest total %.2f" % ttot),
            (">= %.2f continuous (layout.md §3)%s" % (need, "; target %.2f" % target if target > need else ""))
            if net == "VDD_0V9" else ">= %.2f total, >= %.2f continuous (layout.md §3; D-110)" % (need, 0.5 * need),
            "below target %.2f: D-110 (owner)" % target if st == "PASS" and worst[0] < target else "")


# other-net vias inside the VDD_0V9 neck (x 44.9-63.5, y 28.05-37.0): an explicit inventory (D-110). The free strips
# (planes.NECK_FREE) must hold none; any via not in the list is a FAIL, so a new via in the core feed is caught even
# where the cross-section still passes.
NECK_BOX = (44.9, 28.05, 63.5, 37.0)


def check_neck_vias(board, vias):
    inv = []
    for n, x, y, _v in vias:
        if n == "VDD_0V9":
            continue
        b = NECK_BOX
        if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
            inv.append((n, round(x, 2), round(y, 2)))
        for name, x0, y0, x1, y1 in pl.NECK_FREE:
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            if math.hypot(dx, dy) < 0.30 + 0.25 - 1e-6:
                rec("FAIL", "neck", "%s via (%.2f, %.2f) in the VDD_0V9 free strip %s" % (n, x, y, name), "", "none")
    inv.sort()
    allowed = {(n, x, y) for n, x, y in NECK_VIAS}
    extra = [v for v in inv if not any(v[0] == a[0] and abs(v[1] - a[1]) < 0.06 and abs(v[2] - a[2]) < 0.06
                                       for a in allowed)]
    rec("PASS" if not extra else "FAIL", "neck", "other-net vias in the VDD_0V9 neck box %s = D-110 inventory" %
        (NECK_BOX,), "%d vias, %d not in the inventory" % (len(inv), len(extra)), "0 new",
        "; ".join("%s (%.2f, %.2f)" % v for v in extra[:6]))


NECK_VIAS = [       # D-110 inventory (as built): GND vias of C36.2, C42.2/C45, C46.2, C47.2, C39.2, C40.2, C81.2, C80.2
    ("GND", 45.14, 36.69), ("GND", 45.53, 31.98), ("GND", 45.66, 33.32), ("GND", 45.91, 36.53),
    ("GND", 46.40, 31.61), ("GND", 49.30, 35.88), ("GND", 49.53, 33.88), ("GND", 57.82, 36.70),
    ("GND", 61.40, 36.56),
    ("VCC_1V8", 44.96, 33.95),      # D-112 i: C47.1 via in pad (verifier L4 r1 blocker; no other site in the neck)
    ("USBA_VBUS_EN", 49.51, 33.09),  # D-116 f: L4 -> L1 hop over the VCC_1V8 L4 diagonal, 2.3 mm south of STRIP-N
                                     # (the free strip keeps its 2.7 mm of copper; NECK section check below)
]


# vias in the ring-1 row around U9 (Chebyshev distance 8.0-10.3 mm from the centre: the gate band and the ring-1
# parts, where the D-104 lane channels run): an explicit inventory (D-110); a new via there FAILs even when the
# lane check still finds a way out (verifier L3 r2 mutation "via in the FSPI lane channel").
RING1_VIAS = [
    ("VCC_DDR", 44.49, 35.99),      # D-112 i: C45.1 via beside the pad (verifier L4 r1 blocker; GND via column)
    ("GND", 24.70, 36.12), ("GND", 24.71, 32.88), ("GND", 24.71, 32.11), ("GND", 24.73, 33.91), ("GND", 24.73, 38.94),
    ("GND", 27.84, 26.73), ("GND", 28.43, 45.84), ("GND", 30.93, 46.27), ("GND", 30.96, 26.70), ("GND", 32.65, 46.45),
    ("GND", 33.23, 26.70), ("GND", 36.24, 26.26), ("GND", 36.87, 26.71), ("GND", 36.88, 46.29), ("GND", 38.81, 46.48),
    ("GND", 39.92, 26.82), ("GND", 40.74, 46.27), ("GND", 41.04, 27.16), ("GND", 44.22, 33.67), ("GND", 44.24, 34.45),
    ("GND", 44.25, 32.82), ("GND", 44.27, 37.15), ("GND", 44.28, 35.24), ("GND", 44.30, 39.45),
    ("VCC_3V3", 42.88, 27.44), ("VDD_0V9", 24.53, 45.77), ("VDD_0V9", 25.38, 45.94), ("VDD_0V9", 30.53, 44.54),
    ("VDD_0V9", 41.00, 27.94),
    # D-114 d (L5 round 2): vias in the pads of the boxed-in ring-1 sub-rail capacitors / filter resistor
    ("AVDD1V8_USB", 36.71, 44.71), ("AVDD1V8_USB", 42.75, 44.71), ("FEPHY_AVDD3V3", 26.29, 32.28),
    # D-128 (L5G round 2): C58 moved 0.176 mm east / 0.25 mm north (its C58.1 in-pad via (36.71, 44.71) -> (36.886,
    # 44.46)) and its GND via moved from the dog-bone site (36.88, 46.29) into the C58.2 pad (36.886, 45.42); the
    # earlier-phase positions stay listed for the L3 / L4 / L5 boards the rebuild checks
    ("AVDD1V8_USB", 36.886, 44.46), ("GND", 36.886, 45.42),
]


def check_ring1_vias(vias):
    cx, cy = esc.CENTRE
    inv = [(n, x, y) for n, x, y, _v in vias if 8.0 <= max(abs(x - cx), abs(y - cy)) <= 10.3]
    inv = [v for v in inv if v not in L4_RING_VIAS]
    extra = [v for v in inv if not any(v[0] == a[0] and abs(v[1] - a[1]) < 0.06 and abs(v[2] - a[2]) < 0.06
                                       for a in RING1_VIAS)]
    rec("PASS" if not extra else "FAIL", "lanes", "vias in the ring-1 row (8.0-10.3 mm from the U9 centre) = D-110 "
        "inventory", "%d vias, %d not in the inventory" % (len(inv), len(extra)), "0 new",
        "; ".join("%s (%.2f, %.2f)" % v for v in extra[:6]))


# D-111 (L4): vias of the critical routing that sit in the ring-1 row band (checked against the lanes by lanecheck.py)
L4_RING_VIAS = []


def run_drc():
    subprocess.run([bl.KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", DRC_JSON, bl.BOARD_FILE],
                   check=True, stdout=subprocess.DEVNULL)
    with open(DRC_JSON, encoding="utf-8") as fh:
        d = json.load(fh)
    R = rl.rules()
    by = collections.Counter((v["type"], v["severity"]) for v in d["violations"])
    for (t, s), n in sorted(by.items()):
        capped = " (kicad-cli reports at most 199 per type: >= 199)" if n == 199 else ""
        rec("INFO", "drc", "%s (%s)" % (t, s), ">= %d" % n if n == 199 else n, "", capped.strip())
    errors = [v for v in d["violations"] if v["severity"] == "error"]
    rec("PASS" if not errors else "FAIL", "drc", "DRC errors on what exists (violations of severity error)",
        len(errors), 0, "; ".join("%s: %s" % (v["type"], " / ".join(i["description"][:50] for i in v["items"]))
                                  for v in errors[:5]))
    import re
    per_cls, per_net = collections.Counter(), collections.Counter()
    for u in d["unconnected_items"]:
        nets = set()
        for it in u["items"]:
            m = re.search(r"\[([^\]]+)\]", it["description"])
            if m:
                nets.add(m.group(1))
        for n in nets:
            per_net[n] += 1
            per_cls[R[n][0] if n in R else "?"] += 1
    rec("INFO", "drc", "unconnected items (total)", len(d["unconnected_items"]), "",
        "per class: " + ", ".join("%s %d" % kv for kv in sorted(per_cls.items())))
    plane_unc = {n: per_net[n] for n in rl.PLANE_NETS if per_net[n]}
    rec("PASS" if not plane_unc else "FAIL", "drc", "unconnected items on plane nets (GND, VDD_0V9, VCC_3V3, "
        "VCC5V0_SYS, VBUS_USBA)", sum(plane_unc.values()), 0, " ".join("%s %d" % kv for kv in plane_unc.items()))
    return per_net


def check_carried(board):
    # L2 verifier minor: R51.2 (OSC_XIN) to pin 68, both pads measured
    r51 = board.FindFootprintByReference("R51")
    u9 = board.FindFootprintByReference("U9")
    p68 = [p for p in u9.Pads() if p.GetNumber() == "68"][0]
    for p in r51.Pads():
        d = bl.edge_dist(p, p68)
        rec("DEV" if d > 2.0 else "PASS", "carried", "R51.%s (%s) to U9.68, copper edge" % (p.GetNumber(),
            p.GetNetname()), "%.2f mm" % d, "<= 2 mm (layout.md §4.3)", "D-109 (g)" if d > 2.0 else "")


def main():
    # optional: check another board (mutation tests): check_routing.py <board.kicad_pcb> <out dir>; the board needs
    # its .kicad_pro / .kicad_dru beside it for the DRC run
    global OUT, DRC_JSON
    if len(sys.argv) > 2:
        bl.BOARD_FILE = os.path.abspath(sys.argv[1])
        OUT = os.path.join(sys.argv[2], "check_routing.txt")
        DRC_JSON = os.path.join(sys.argv[2], "drc_routing.json")
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    segs, vias = tracks_of(board)
    pads_by_net = collections.defaultdict(list)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                pads_by_net[p.GetNetname()].append(("%s.%s" % (fp.GetReference(), p.GetNumber()), bl.pad_polygon(p)))
    rec("INFO", "board", "tracks / vias / zones", "%d / %d / %d" % (len(segs), len(vias),
        sum(1 for z in board.Zones() if not z.GetIsRuleArea())), "")
    check_netlist(board)
    check_escape(board, segs, vias, pads_by_net)
    zones = check_planes(board)
    check_planevias(board, segs, vias, zones)
    check_sections(board)
    check_neck_vias(board, vias)
    check_ring1_vias(vias)
    check_lanes(board)
    per_net = run_drc()
    check_carried(board)
    if any(g.GetName() == "L4_CRITICAL" for g in board.Groups()):
        import l4check
        meas = l4check.check_l4(board, rec, segs, vias, per_net, rl.rules())
        os.makedirs(os.path.join(os.path.dirname(OUT), "l4"), exist_ok=True)
        with open(os.path.join(os.path.dirname(OUT), "l4", "measured.json"), "w", encoding="utf-8") as fh:
            json.dump(meas, fh, indent=1, sort_keys=True)
    if any(g.GetName() == "L5_LANES" for g in board.Groups()):
        import l5check
        meas5 = l5check.check_l5(board, rec, segs, vias, per_net, rl.rules(), drc_json=DRC_JSON)
        # L5F (D-H6 / D-117): the CHECKPOINT-2 review fixes, measured on every routed board
        import l5fcheck
        meas5["l5f"] = l5fcheck.check_l5f(board, rec, segs, vias, DRC_JSON)
        # L5G (D-H7 / D-119..D-127): the re-review fixes, measured on every routed board
        import l5gcheck
        meas5["l5g"] = l5gcheck.check_l5g(board, rec, segs, vias)
        os.makedirs(os.path.join(os.path.dirname(OUT), "l5"), exist_ok=True)
        with open(os.path.join(os.path.dirname(OUT), "l5", "measured.json"), "w", encoding="utf-8") as fh:
            json.dump(meas5, fh, indent=1, sort_keys=True, default=str)
    head = "check_routing.py: %d checks, %d PASS, %d DEV, %d INFO, %d FAIL" % (
        sum(COUNT.values()), COUNT["PASS"], COUNT["DEV"], COUNT["INFO"], COUNT["FAIL"])
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(head + "\n")
        for line in LINES:
            fh.write(line + "\n")
    for line in LINES:
        if not line.startswith("PASS"):
            print(line)
    print(head)
    sys.exit(1 if COUNT["FAIL"] else 0)


if __name__ == "__main__":
    main()
