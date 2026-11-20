"""Layout phase L5F checks (TP-L5F, owner decision D-H6 / D-117), called by check_routing.py on every board that carries
the L5 groups. Every item of the CHECKPOINT-2 review list that a program can measure has a FAIL-capable line here
(mutation tests: mutate_l5f.py). Measured from the saved board with our own pcbnew geometry:

  L5F-buck   TLV62569 input loops U4-U7: the L1-only GND copper path (pads + tracks + zone fill on F.Cu) from each input
             capacitor's GND pad to IC pin 2 exists and is <= 3.0 mm (geodesic, 0.04 mm grid); pin 2 connects solidly
             to the pour (pad zone connection FULL, no spokes); >= 2 GND vias within 1.0 mm of pin 2 (centre to pad
             edge); loop dimensions recorded (MEAS)
  L5F-vip    vias whose drill circle or annular ring intersects an SMD pad or its mask opening, or whose drill edge is
             < 0.10 mm from a mask opening (= via centre < ring radius from the opening) -> FAIL unless listed in
             design/pcb/via_in_pad.csv (ref.pad, net, x, y, reason); listed rows that no longer exist -> FAIL (exact list)
  L5F-vcut   board copper (tracks, vias, pads, zone fills, all layers) >= 0.8 mm from the V-cut lines read from the
             V-CUT user layer (KiCad DRC cannot see them); the rail fiducials (JLC-mandated position) are reported
  L5F-sw     EN / FB / PWR_EN / PB nets to SW copper (SW tracks, SW pads, buck inductor pads): FB (SENSE) >= 2.0 mm,
             EN / PWR_EN / PB >= 1.0 mm, outside the U4-U7 courtyards; no copper of these nets inside an inductor
             courtyard (L1-L4)
  L5F-silk   every F.SilkS line / outline >= 0.15 mm wide; every visible silk text >= 1.0 mm high with >= 0.15 mm
             stroke; no silk outside the board outline or over the V-cut (J1 clipped by the edge)
  L5F-hop    every L4 track of a USB / ETH pair net: In2 GND copper under every point (sampled 0.05 mm) farther than
             0.6 mm from any via (the In2 anti-pads); the In2 net under it is reported; a GND via within 1.0 mm (centre
             to centre) of every pair via, or the recorded nearest legal one (HOP_STITCH_DEV, D-117 f)
  L5F-neck   tracks ending in a two-pad 0402 / 0603 passive pad are no wider than the pad's narrow side + 0.02 mm, and
             the copper of a wider track of the pad's net does not overlap the pad (polygon intersection; D-118 e)
             (tombstoning; C29.1 / R17.1 were 0.8 mm into 0.56 / 0.80 mm pads)
  L5F-dangle KiCad DRC track_dangling and via_dangling = 0
  L5F-edge   Edge.Cuts: R 1 mm arcs at the four corners of the 80 x 80 board itself; the outline is one closed loop;
             every corner of the routed outline that a router bit cannot cut (a sharp corner whose material side is
             wider than 180 deg, sampled 0.05 mm around each end point) FAILs, and every arc on the air side of the
             cut has R >= 0.5 mm (1.0 mm bit; D-118 c);
             V-CUT is a user layer with the lines x = 0 and x = 80 over the full height, and it plots (kicad-cli gerber)
  L5F-zone   final board: every part's courtyard inside its placement.csv zone (or a recorded deviation)
  L5F-geom   L5 segments >= 0.5 mm long anywhere (U9_FAN included) at 0/45/90 deg within 0.5 deg
"""
import csv
import heapq
import json
import math
import os
import subprocess
import tempfile

import boardlib as bl

import pcbnew

MEAS = {}
VIP_CSV = os.environ.get("L5F_VIP_CSV") or os.path.join(bl.PCB_DIR, "via_in_pad.csv")   # env: mutation tests
BUCKS = {"U4": ("L1", ("C7", "C12")), "U5": ("L2", ("C8", "C13")), "U6": ("L3", ("C9", "C14")),
         "U7": ("L4", ("C10", "C15"))}
EN_NETS = ("U4_EN", "U6_EN", "VCC_DDR_1V8_EN", "PWR_EN", "PB_IN", "PB_INT_N", "PWR_BTN_N")
FB_NETS = ("U4_FB", "U5_FB", "U6_FB", "U7_FB")
SW_NETS = ("U4_SW", "U5_SW", "U6_SW", "U7_SW")
PAIR_PREFIX = ("USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM", "ETH_TX", "ETH_RX")
# D-117 f: pair vias with no legal GND-via site within 1.0 mm (exact search 0.75-1.60 mm, l5f_route.py): the nearest
# GND via (centre to centre, mm) - a stitching via nearer than this is welcome, a larger distance FAILs
HOP_STITCH_DEV = {("ETH_TXN", 22.85, 31.10): 1.17, ("USBC_DM", 38.35, 56.85): 1.20, ("USBC_DM", 51.15, 71.00): 1.48,
                  ("USBC_DP", 47.75, 70.90): 1.67, ("USBC_DP", 49.75, 71.12): 2.23}
# D-117 d is withdrawn (round 2, D-118 a): the three J5 west-corridor lanes were re-routed >= 0.8 mm from the V-cut, so
# no net may come closer than 0.8 mm (an entry here would let a net come down to its floor in mm; keep it empty)
VCUT_DEV = {}
# final-board zone deviations (decisions.md): parts that sit outside their placement.csv zone on the routed board
ZONE_DEV = {
    "J1": "D-103 (a)", "J2": "D-103 (a)", "J3": "D-103 (a)", "J4": "D-103 (a)", "J5": "D-103 (a)", "J6": "D-103 (a)",
    "R61": "D-103 (e)", "TP2": "D-103 (d)", "TP3": "D-103 (d)", "TP4": "D-103 (d)", "TP5": "D-103 (d)",
    "TP15": "D-115", "C69": "D-115", "TP31": "D-115", "Y2": "D-105", "C78": "D-105", "TP26": "D-113 (TP26 local move)",
}
CONN_ZONE = {"J1": "J1-USBC", "J2": "J2-SD", "J3": "J3-RJ45", "J4": "J4-USBA", "J5": "J5-HDR", "J6": "J6-UART"}


def _poly_of_track(t, lay):
    ps = pcbnew.SHAPE_POLY_SET()
    t.TransformShapeToPolygon(ps, lay, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    return ps


def copper_union(board, net, lay, win):
    """union of one net's copper on one layer inside win (board mm x0, y0, x1, y1): pads, tracks, vias, zone fill"""
    u = pcbnew.SHAPE_POLY_SET()
    box = pcbnew.BOX2I(bl.to_page(win[0], win[1]), pcbnew.VECTOR2I(pcbnew.FromMM(win[2] - win[0]),
                                                                   pcbnew.FromMM(win[3] - win[1])))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net and p.IsOnLayer(lay) and p.GetBoundingBox().Intersects(box):
                p.TransformShapeToPolygon(u, lay, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    for t in board.GetTracks():
        if t.GetNetname() != net or not t.GetBoundingBox().Intersects(box):
            continue
        if t.GetClass() == "PCB_VIA" or t.GetLayer() == lay:
            t.TransformShapeToPolygon(u, lay, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetNetname() == net and z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay):
            u.Append(z.GetFilledPolysList(lay))
    u.Simplify()
    return u


def geodesic(union, src_poly, dst_poly, win, step=0.04):
    """shortest path inside union (SHAPE_POLY_SET) from any grid point in src_poly to any in dst_poly (board mm
    polygons), 8-connected grid; returns length mm or None"""
    nx = int((win[2] - win[0]) / step) + 1
    ny = int((win[3] - win[1]) / step) + 1
    inside = {}
    for i in range(nx):
        for j in range(ny):
            x, y = win[0] + i * step, win[1] + j * step
            if union.Contains(pcbnew.VECTOR2I(bl.to_page(x, y))):
                inside[(i, j)] = (x, y)
    src = [k for k, (x, y) in inside.items() if bl._inside(x, y, src_poly)]
    dst = {k for k, (x, y) in inside.items() if bl._inside(x, y, dst_poly)}
    if not src or not dst:
        return None
    dist = {k: 0.0 for k in src}
    h = [(0.0, k) for k in src]
    heapq.heapify(h)
    d2 = step * math.sqrt(2)
    while h:
        d, k = heapq.heappop(h)
        if k in dst:
            return d
        if d > dist.get(k, 1e9):
            continue
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if not di and not dj:
                    continue
                m = (k[0] + di, k[1] + dj)
                if m not in inside:
                    continue
                nd = d + (d2 if di and dj else step)
                if nd < dist.get(m, 1e9) - 1e-9:
                    dist[m] = nd
                    heapq.heappush(h, (nd, m))
    return None


def pad(board, ref, num):
    fp = board.FindFootprintByReference(ref)
    return [p for p in fp.Pads() if p.GetNumber() == num][0] if fp else None


def poly_area(pts):
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2


def check_bucks(board, rec, vias):
    rows = {}
    for u, (ind, caps) in sorted(BUCKS.items()):
        p2 = pad(board, u, "2")
        p4 = pad(board, u, "4")
        poly2 = bl.pad_polygon(p2)
        c2 = bl.to_board(p2.GetPosition())
        c4 = bl.to_board(p4.GetPosition())
        # solid connection of pin 2 (no thermal spokes)
        zc = p2.GetLocalZoneConnection()
        rec("PASS" if zc == pcbnew.ZONE_CONNECTION_FULL else "FAIL", "L5F-buck", "%s.2 (GND) zone connection solid "
            "(no thermal spokes; D-H6)" % u, {pcbnew.ZONE_CONNECTION_FULL: "solid"}.get(zc, "thermal/inherited (%d)"
                                                                                      % zc), "solid")
        near = []
        for n, x, y, v in vias:
            if n == "GND":
                d = 0.0 if bl._inside(x, y, poly2) else min(
                    bl._seg_pt(x, y, poly2[i][0], poly2[i][1], poly2[(i + 1) % len(poly2)][0],
                               poly2[(i + 1) % len(poly2)][1]) for i in range(len(poly2)))
                if d <= 1.0:
                    near.append((round(d, 2), round(x, 2), round(y, 2)))
        rec("PASS" if len(near) >= 2 else "FAIL", "L5F-buck", "%s.2 GND vias within 1.0 mm of the pin (centre to pad "
            "edge)" % u, "%d: %s" % (len(near), sorted(near)), ">= 2")
        cells = []
        for cap in caps:
            pg = [p for p in board.FindFootprintByReference(cap).Pads() if p.GetNetname() == "GND"][0]
            pv = [p for p in board.FindFootprintByReference(cap).Pads() if p.GetNetname() == "VCC5V0_SYS"][0]
            gpoly = bl.pad_polygon(pg)
            cg = bl.to_board(pg.GetPosition())
            cv = bl.to_board(pv.GetPosition())
            xs = [q[0] for q in gpoly + poly2]
            ys = [q[1] for q in gpoly + poly2]
            win = (min(xs) - 1.5, min(ys) - 1.5, max(xs) + 1.5, max(ys) + 1.5)
            un = copper_union(board, "GND", pcbnew.F_Cu, win)
            g = geodesic(un, gpoly, poly2, win)
            loop = poly_area([c4, cv, cg, c2])
            row = {"gnd_path_mm": None if g is None else round(g, 2),
                   "vin_pin4_to_cap_mm": round(math.hypot(cv[0] - c4[0], cv[1] - c4[1]), 2),
                   "gnd_cap_to_pin2_direct_mm": round(math.hypot(cg[0] - c2[0], cg[1] - c2[1]), 2),
                   "loop_area_mm2": round(loop, 2)}
            cells.append((cap, row))
            rec("PASS" if g is not None and g <= 3.0 else "FAIL", "L5F-buck", "%s input loop: %s GND pad -> %s.2 along "
                "L1 GND copper only (pads, tracks, F.Cu fill; geodesic)" % (u, cap, u),
                "no L1 path" if g is None else "%.2f mm (pin 4 -> %s VIN %.2f mm centres, loop area %.2f mm2)" % (
                    g, cap, row["vin_pin4_to_cap_mm"], loop), "<= 3.0 mm")
        rows[u] = dict(cells)
    MEAS["buck_loops"] = rows


def vip_rows():
    if not os.path.exists(VIP_CSV):
        return {}
    out = {}
    for r in csv.DictReader(open(VIP_CSV, encoding="utf-8")):
        out[(r["pad"], round(float(r["x"]), 2), round(float(r["y"]), 2))] = r
    return out


def vias_in_pads(board):
    """(ref.pad, pad net, via net, x, y, centre-to-opening mm) for every via whose ring meets an SMD pad / opening"""
    hits = []
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            lay = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            m = max(0, p.GetSolderMaskExpansion(pcbnew.F_Mask if lay == pcbnew.F_Cu else pcbnew.B_Mask))
            pads.append(("%s.%s" % (fp.GetReference(), p.GetNumber()), p, lay, m, bl.pad_polygon(p)))
    holes = []
    for v in board.GetTracks():
        if v.GetClass() == "PCB_VIA":
            holes.append((v.GetNetname(), bl.to_board(v.GetPosition()), pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2,
                          pcbnew.ToMM(v.GetDrillValue()) / 2, None))
    # drilled footprint pads inside an SMD pad of their footprint (the U9 EP thermal vias, layout.md §6.2)
    for fp in board.GetFootprints():
        for q in fp.Pads():
            if q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pcbnew.ToMM(q.GetSize().x) < 1.0:
                holes.append((q.GetNetname(), bl.to_board(q.GetPosition()), pcbnew.ToMM(q.GetSize().x) / 2,
                              pcbnew.ToMM(q.GetDrillSize().x) / 2, fp.GetReference()))
    for vnet, (x, y), ring, drill, owner in holes:
        lim = max(ring, drill + 0.10)
        for name, p, lay, m, poly in pads:
            if owner and not name.startswith(owner + "."):
                continue
            xs = [q[0] for q in poly]
            ys = [q[1] for q in poly]
            if x < min(xs) - 1 or x > max(xs) + 1 or y < min(ys) - 1 or y > max(ys) + 1:
                continue
            d = 0.0 if bl._inside(x, y, poly) else min(
                bl._seg_pt(x, y, poly[i][0], poly[i][1], poly[(i + 1) % len(poly)][0], poly[(i + 1) % len(poly)][1])
                for i in range(len(poly)))
            d -= pcbnew.ToMM(m)
            if d < lim - 1e-4:
                hits.append((name, p.GetNetname(), vnet, round(x, 2), round(y, 2), round(max(d, 0), 3)))
    return hits


def check_vip(board, rec):
    hits = vias_in_pads(board)
    wl = vip_rows()
    listed = {(h[0], h[3], h[4]) for h in hits}
    extra = [h for h in hits if (h[0], h[3], h[4]) not in wl]
    stale = [k for k in wl if k not in listed]
    MEAS["via_in_pad"] = hits
    nv = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
    rec("FAIL" if extra else "PASS", "L5F-vip", "vias whose drill circle / annular ring meets an SMD pad or its mask "
        "opening, or drill edge < 0.10 mm from it (all %d board vias + the U9 EP thermal vias)" % nv, "%d: %s" % (
            len(hits), " ".join("%s@(%.2f,%.2f)" % (h[0], h[3], h[4]) for h in sorted(hits))),
        "each listed in via_in_pad.csv (POFV, D-H6)", "not listed: %s" % extra if extra else "POFV list D-117 b")
    rec("FAIL" if stale else "PASS", "L5F-vip", "via_in_pad.csv rows that match no via in a pad (the list must be exact "
        "for the L6 fab notes)", len(stale), 0, str(stale[:4]))


def vcut_lines(board):
    xs = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.User_1 and d.GetClass() == "PCB_SHAPE" and d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            a, b = bl.to_board(d.GetStart()), bl.to_board(d.GetEnd())
            if abs(a[0] - b[0]) < 1e-3:
                xs.append((a[0], min(a[1], b[1]), max(a[1], b[1])))
    return xs


def check_vcut(board, rec):
    lines = vcut_lines(board)
    lname = board.GetLayerName(pcbnew.User_1)
    ok_layer = lname == "V-CUT" and board.IsLayerEnabled(pcbnew.User_1)
    full = sorted(round(x, 3) for x, y0, y1 in lines if y0 <= 0.001 and y1 >= 79.999)
    rec("PASS" if ok_layer and full == [0.0, 80.0] else "FAIL", "L5F-edge", "V-CUT user layer (User.1) enabled and "
        "named V-CUT, lines x = 0 and x = 80 over the full height", "layer '%s', full-height lines at %s" % (lname, full),
        "[0.0, 80.0]")
    # plotted: kicad-cli writes a Gerber of the V-CUT layer that contains the two lines
    try:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([bl.KICAD_CLI, "pcb", "export", "gerbers", "-l", "User.1", "-o", td, bl.BOARD_FILE],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            fs = [f for f in os.listdir(td) if not f.endswith(".gbrjob")]
            txt = open(os.path.join(td, fs[0])).read() if fs else ""
            segs = txt.count("D01*")
            ok = bool(fs) and "V-CUT" in fs[0].replace("V_CUT", "V-CUT") and segs >= 2
            rec("PASS" if ok else "FAIL", "L5F-edge", "V-CUT layer plots to a Gerber (kicad-cli export gerbers -l User.1; "
                "L6 adds it to the fab set)", "%s, %d draw operations" % (fs[0] if fs else "no file", segs),
                ">= 2 lines, layer named V-CUT")
    except Exception as e:      # noqa: BLE001
        rec("FAIL", "L5F-edge", "V-CUT layer plot", "error %s" % e, "")
    vx = [x for x, y0, y1 in lines if y0 <= 0.001 and y1 >= 79.999] or [0.0, 80.0]
    worst, items, rail = None, [], []
    LIM = 0.8

    devs = {}

    def note(d, what, x, net=None):
        nonlocal worst
        if net in VCUT_DEV and d >= VCUT_DEV[net] - 1e-4:
            devs[net] = min(devs.get(net, 9.0), d)
            return
        if worst is None or d < worst[0]:
            worst = (d, what)
        if d < LIM - 1e-4:
            items.append("%s %.2f" % (what, d))
    lays = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            # vias from their own geometry (an unconnected via may not be flashed, so it has no copper polygon)
            x, y = bl.to_board(t.GetPosition())
            r = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            if -r <= x <= 80 + r:
                d = min(abs(x - v) for v in vx) - r
                if d < 2.0:
                    note(d, "%s via (%.2f, %.2f)" % (t.GetNetname(), x, y), x, t.GetNetname())
            continue
        for lay in lays:
            if t.GetLayer() == lay:
                ps = _poly_of_track(t, lay)
                for k in range(ps.OutlineCount()):
                    o = ps.Outline(k)
                    for i in range(o.PointCount()):
                        x, y = bl.to_board(o.CPoint(i))
                        if 0 <= x <= 80:
                            d = min(abs(x - v) for v in vx)
                            if d < 2.0:
                                note(d, "%s %s (%.2f, %.2f)" % (t.GetNetname(), "via" if t.GetClass() == "PCB_VIA"
                                                                 else board.GetLayerName(lay), x, y), x, t.GetNetname())
                break
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for lay in lays:
            if z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay):
                ps = z.GetFilledPolysList(lay)
                for k in range(ps.OutlineCount()):
                    o = ps.Outline(k)
                    for i in range(o.PointCount()):
                        x, y = bl.to_board(o.CPoint(i))
                        if 0 <= x <= 80:
                            note(min(abs(x - v) for v in vx), "zone %s %s" % (z.GetZoneName(), board.GetLayerName(lay)),
                                 x)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for x, y in bl.pad_polygon(p):
                d = min(abs(x - v) for v in vx)
                if 0 <= x <= 80:
                    note(d, "pad %s.%s" % (fp.GetReference(), p.GetNumber()), x)
                elif d < LIM:
                    rail.append("%s %.2f" % (fp.GetReference(), d))
    seen = []
    for it in items:
        k = it.rsplit(" ", 1)[0].split(" (")[0]
        if k not in seen:
            seen.append(k)
    rec("PASS" if not items else "FAIL", "L5F-vcut", "board copper (tracks, vias, pads, zone fills; F/In1/In2/B) to the "
        "V-cut lines x = 0 / 80 (V-CUT layer; D-H6), no exceptions (D-118 a)", "min %.3f mm (%s)" % worst
        if worst else "none", ">= 0.80 mm", "; ".join(seen[:8]))
    MEAS["vcut_min"] = round(worst[0], 4) if worst else None
    if devs:        # only reachable if VCUT_DEV is filled again
        rec("DEV", "L5F-vcut", "nets allowed below 0.8 mm by VCUT_DEV", " ".join("%s %.2f" % kv for kv in
                                                                               sorted(devs.items())), ">= floor", "")
    rec("INFO", "L5F-vcut", "rail-side copper within 0.8 mm of a V-cut: the global fiducials at the JLC-mandated "
        "3.85 mm from the panel edge (layout.md §1)", ", ".join(sorted(set(rail))) or "none", "")


def check_sw(board, rec, segs, vias):
    sw_t = [s for s in segs if s[0] in SW_NETS]
    sw_p = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() in SW_NETS or fp.GetReference() in ("L1", "L2", "L3", "L4"):
                sw_p.append(("%s.%s" % (fp.GetReference(), p.GetNumber()), bl.pad_polygon(p)))
    courts = [bl.courtyard_bbox(board.FindFootprintByReference(u)) for u in ("U4", "U5", "U6", "U7")]
    lcourts = {r: bl.courtyard_bbox(board.FindFootprintByReference(r)) for r in ("L1", "L2", "L3", "L4")}

    def in_court(pts):
        return any(c and all(c[0] <= q[0] <= c[2] and c[1] <= q[1] <= c[3] for q in pts) for c in courts)

    def seg_seg(a, b, c, d):
        return min(bl._seg_pt(a[0], a[1], c[0], c[1], d[0], d[1]), bl._seg_pt(b[0], b[1], c[0], c[1], d[0], d[1]),
                   bl._seg_pt(c[0], c[1], a[0], a[1], b[0], b[1]), bl._seg_pt(d[0], d[1], a[0], a[1], b[0], b[1]))
    items = [(s[0], s[2], s[3], s[4] / 2, "track") for s in segs if s[0] in EN_NETS + FB_NETS and
             s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
    items += [(n, (x, y), (x, y), pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2, "via") for n, x, y, v in vias
              if n in EN_NETS + FB_NETS]
    worst = {}
    incy = []
    for net, a, b, hw, kind in items:
        for r, c in lcourts.items():
            if c and (any(c[0] - hw < q[0] < c[2] + hw and c[1] - hw < q[1] < c[3] + hw for q in (a, b)) or
                      _seg_hits_box(a, b, (c[0] - hw, c[1] - hw, c[2] + hw, c[3] + hw))):
                incy.append("%s %s (%.2f, %.2f) in %s" % (net, kind, a[0], a[1], r))
        key = "FB" if net in FB_NETS else "EN"
        # sample the item every 0.05 mm; the parts inside an IC courtyard (U4-U7) are not measured
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / 0.05))
        for k in range(n + 1):
            q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
            if in_court((q, q)):
                continue
            for t in sw_t:
                d = bl._seg_pt(q[0], q[1], t[2][0], t[2][1], t[3][0], t[3][1]) - hw - t[4] / 2
                if key not in worst or d < worst[key][0]:
                    worst[key] = (d, net, t[0], kind, q)
            for name, poly in sw_p:
                d = (0.0 if bl._inside(q[0], q[1], poly) else min(
                    bl._seg_pt(q[0], q[1], poly[i][0], poly[i][1], poly[(i + 1) % len(poly)][0],
                               poly[(i + 1) % len(poly)][1]) for i in range(len(poly)))) - hw
                if key not in worst or d < worst[key][0]:
                    worst[key] = (d, net, name, kind, q)
    for key, lim in (("FB", 2.0), ("EN", 1.0)):
        w = worst.get(key)
        rec("PASS" if w and w[0] >= lim - 1e-4 else "FAIL", "L5F-sw", "%s nets (%s) to SW copper (SW tracks / pads, "
            "buck inductor pads), edge to edge, outside the U4-U7 courtyards" % (
                key, " ".join(FB_NETS if key == "FB" else EN_NETS)),
            "min %.2f mm (%s %s at (%.2f, %.2f) - %s)" % (w[0], w[1], w[3], w[4][0], w[4][1], w[2]) if w else "none",
            ">= %.1f mm" % lim)
    MEAS["sw_clearance"] = {k: round(v[0], 3) for k, v in worst.items()}
    rec("PASS" if not incy else "FAIL", "L5F-sw", "EN / FB / PWR_EN / PB copper inside a buck inductor courtyard "
        "(L1-L4)", len(incy), 0, "; ".join(incy[:6]))


def _seg_hits_box(a, b, r):
    n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.02))
    for i in range(n + 1):
        x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return True
    return False


def check_silk(board, rec):
    thin, small, outside = [], [], []

    def out_of_board(it):
        bb = it.GetBoundingBox()
        x0, y0 = bl.to_board(bb.GetOrigin())
        x1, y1 = bl.to_board(bb.GetEnd())
        return min(x0, x1) < -1e-3 or min(y0, y1) < -1e-3 or max(x0, x1) > 80.001 or max(y0, y1) > 80.001
    for fp in board.GetFootprints():
        for t in (fp.Reference(), fp.Value()):
            if t.IsVisible() and t.GetLayer() == pcbnew.F_SilkS:
                h, w = pcbnew.ToMM(t.GetTextHeight()), pcbnew.ToMM(t.GetTextThickness())
                if h < 1.0 - 1e-4 or w < 0.15 - 1e-4:
                    small.append("%s %.2f/%.2f" % (t.GetText(), h, w))
                if out_of_board(t):
                    outside.append("text " + t.GetText())
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_SilkS:
                continue
            if g.GetClass() == "PCB_TEXT":
                if g.IsVisible():
                    h, w = pcbnew.ToMM(g.GetTextHeight()), pcbnew.ToMM(g.GetTextThickness())
                    if h < 1.0 - 1e-4 or w < 0.15 - 1e-4:
                        small.append("%s:%s %.2f/%.2f" % (fp.GetReference(), g.GetText(), h, w))
                continue
            wd = pcbnew.ToMM(g.GetWidth())
            if wd < 0.15 - 1e-4 and not (g.IsFilled() if hasattr(g, "IsFilled") else False):
                thin.append("%s %s %.2f" % (fp.GetReference(), g.GetShapeStr(), wd))
            if out_of_board(g):
                outside.append("%s %s" % (fp.GetReference(), g.GetShapeStr()))
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.F_SilkS:
            continue
        if d.GetClass() == "PCB_TEXT":
            h, w = pcbnew.ToMM(d.GetTextHeight()), pcbnew.ToMM(d.GetTextThickness())
            if h < 1.0 - 1e-4 or w < 0.15 - 1e-4:
                small.append("%s %.2f/%.2f" % (d.GetText(), h, w))
        elif pcbnew.ToMM(d.GetWidth()) < 0.15 - 1e-4:
            thin.append("board %s %.2f" % (d.GetShapeStr(), pcbnew.ToMM(d.GetWidth())))
        if out_of_board(d):
            outside.append("board " + (d.GetText() if d.GetClass() == "PCB_TEXT" else d.GetShapeStr()))
    rec("PASS" if not thin else "FAIL", "L5F-silk", "F.SilkS lines / outlines >= 0.15 mm wide (footprints and board; "
        "layout.md §1)", len(thin), 0, "; ".join(thin[:6]))
    rec("PASS" if not small else "FAIL", "L5F-silk", "visible F.SilkS texts >= 1.0 mm high with >= 0.15 mm stroke "
        "(LED labels included)", len(small), 0, "; ".join(small[:6]))
    rec("PASS" if not outside else "FAIL", "L5F-silk", "F.SilkS items outside the 80 x 80 board (clipped by the edge, "
        "e.g. J1's outline)", len(outside), 0, "; ".join(outside[:6]))


def check_hops(board, rec, segs, vias):
    fills = []
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In2_Cu) and z.HasFilledPolysForLayer(pcbnew.In2_Cu):
            fills.append((z.GetNetname(), z.GetFilledPolysList(pcbnew.In2_Cu)))

    def under(x, y):
        v = pcbnew.VECTOR2I(bl.to_page(x, y))
        for n, ps in fills:
            if ps.Contains(v):
                return n
        return None
    pair = lambda n: n.startswith(PAIR_PREFIX)  # noqa: E731
    bad, rows = [], []
    for s in segs:
        if not pair(s[0]) or s[1] != pcbnew.B_Cu:
            continue
        own = [(x, y) for n, x, y, _v in vias]      # every via's In2 anti-pad (its own and the neighbours')
        a, b = s[2], s[3]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / 0.05))
        nets = set()
        miss = 0
        for i in range(n + 1):
            x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
            if any(math.hypot(x - vx, y - vy) <= 0.6 for vx, vy in own):
                continue
            u = under(x, y)
            nets.add(u or "none")
            if u != "GND":
                miss += 1
        rows.append((s[0], round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2), sorted(nets)))
        if miss:
            bad.append("%s (%.2f,%.2f)-(%.2f,%.2f) over %s" % (s[0], a[0], a[1], b[0], b[1], sorted(nets)))
    MEAS["l4_hops"] = rows
    rec("PASS" if not bad else "FAIL", "L5F-hop", "L4 tracks of USB / ETH pair nets: In2 GND copper under every point "
        "(beyond 0.6 mm of a via centre: the via anti-pads in In2); In2 net under each listed", "%d segments, %d not over GND: %s" % (
            len(rows), len(bad), "; ".join(bad[:4])) if bad else "%d segments, all over In2 GND (%s)" % (
            len(rows), ", ".join(sorted(set(r[0] for r in rows)))), "all over GND")
    gv = [(x, y) for n, x, y, _v in vias if n == "GND"]
    far, dev = [], []
    for n, x, y, _v in vias:
        if pair(n):
            d = min(math.hypot(x - gx, y - gy) for gx, gy in gv)
            if d > 1.0 + 1e-4:
                lim = HOP_STITCH_DEV.get((n, round(x, 2), round(y, 2)))
                (dev if lim and d <= lim + 0.005 else far).append("%s (%.2f, %.2f) %.2f" % (n, x, y, d))
    MEAS["hop_stitch_dev"] = dev
    rec("PASS" if not far else "FAIL", "L5F-hop", "a GND stitching via within 1.0 mm (centre to centre) of every USB / "
        "ETH pair via, or the recorded nearest legal site (D-117 f)", "%d pair vias, %d over 1.0 mm unrecorded" % (
            sum(1 for v in vias if pair(v[0])), len(far)), 0, "; ".join(far[:6]))
    rec("DEV" if dev else "PASS", "L5F-hop", "pair vias whose nearest GND via is over 1.0 mm (every site within 1.0 mm "
        "is taken by the pair's own L1 / L4 tracks and vias; the nearest legal site is used)", len(dev), "",
        "D-117 f: " + "; ".join(dev))


def check_neck(board, rec, segs):
    bad, n = [], 0
    for fp in board.GetFootprints():
        name = fp.GetFPIDAsString()
        if not any(k in name for k in ("_0402_", "_0603_")) or len(fp.Pads()) != 2:
            continue
        for p in fp.Pads():
            poly = bl.pad_polygon(p)
            sz = p.GetSize()
            narrow = pcbnew.ToMM(min(sz.x, sz.y))
            for s in segs:
                if s[0] != p.GetNetname() or s[1] != pcbnew.F_Cu:
                    continue
                if bl._inside(s[2][0], s[2][1], poly) or bl._inside(s[3][0], s[3][1], poly):
                    n += 1
                    if s[4] > narrow + 0.02 + 1e-4:
                        bad.append("%s.%s %s %.2f mm into a %.2f mm pad" % (fp.GetReference(), p.GetNumber(),
                                                                           s[0], s[4], narrow))
    rec("PASS" if not bad else "FAIL", "L5F-neck", "F.Cu tracks ending in a 0402 / 0603 two-pad passive pad no wider "
        "than the pad's narrow side + 0.02 mm (tombstoning)", "%d track ends, %d too wide" % (n, len(bad)), 0,
        "; ".join(sorted(set(bad))[:6]))
    # round 2 (D-118 e): copper of a too-wide track must not reach into the pad from outside either (a wide track
    # ending just outside the pad with its round end over the pad): intersection area of every such track's copper
    # polygon with the pad copper, any overlap FAILs
    over, nw_ = [], 0
    tr = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.F_Cu]
    for fp in board.GetFootprints():
        name = fp.GetFPIDAsString()
        if not any(k in name for k in ("_0402_", "_0603_")) or len(fp.Pads()) != 2:
            continue
        for p in fp.Pads():
            sz = p.GetSize()
            narrow = pcbnew.ToMM(min(sz.x, sz.y))
            pbox = p.GetBoundingBox()
            pbox.Inflate(pcbnew.FromMM(1.5))
            pp = None
            for t in tr:
                if t.GetNetname() != p.GetNetname() or pcbnew.ToMM(t.GetWidth()) <= narrow + 0.02 + 1e-4:
                    continue
                if not t.GetBoundingBox().Intersects(pbox):
                    continue
                if pp is None:
                    pp = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(pp, pcbnew.F_Cu, 0, pcbnew.FromMM(0.002), pcbnew.ERROR_INSIDE)
                nw_ += 1
                tp = _poly_of_track(t, pcbnew.F_Cu)
                x = pcbnew.SHAPE_POLY_SET(tp)
                x.BooleanIntersection(pp)
                area = sum(x.Outline(k).Area() for k in range(x.OutlineCount())) / 1e12
                if area > 1e-6:
                    over.append("%s.%s %s %.2f mm track overlaps the pad by %.4f mm2" % (
                        fp.GetReference(), p.GetNumber(), p.GetNetname(), pcbnew.ToMM(t.GetWidth()), area))
    rec("PASS" if not over else "FAIL", "L5F-neck", "copper of F.Cu tracks wider than a 0402 / 0603 pad's narrow side "
        "+ 0.02 mm does not overlap that pad (intersection area of track and pad polygons)",
        "%d wide tracks near small pads, %d overlapping" % (nw_, len(over)), 0, "; ".join(sorted(set(over))[:6]))


def check_dangling(rec, drc_json):
    try:
        d = json.load(open(drc_json))
    except Exception as e:     # noqa: BLE001
        rec("FAIL", "L5F-dangle", "DRC report", "error %s" % e, "")
        return
    for t in ("track_dangling", "via_dangling"):
        items = [v for v in d["violations"] if v["type"] == t]
        rec("PASS" if not items else "FAIL", "L5F-dangle", "KiCad DRC %s warnings (D-H6 item 8)" % t, len(items), 0,
            "; ".join(i["items"][0]["description"][:60] for i in items[:4]))


def check_edge(board, rec):
    arcs, segs = [], []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        if d.GetShape() == pcbnew.SHAPE_T_ARC:
            c = bl.to_board(d.GetCenter())
            arcs.append((c, pcbnew.ToMM(d.GetRadius()), bl.to_board(d.GetStart()), bl.to_board(d.GetEnd())))
        elif d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            segs.append((bl.to_board(d.GetStart()), bl.to_board(d.GetEnd())))
    found = []
    for cx, cy in ((1, 1), (79, 1), (1, 79), (79, 79)):
        ok = any(abs(c[0] - cx) < 0.01 and abs(c[1] - cy) < 0.01 and abs(r - 1.0) < 0.01 for c, r, a, b in arcs)
        found.append(ok)
    rec("PASS" if all(found) else "FAIL", "L5F-edge", "R 1 mm corners on the 80 x 80 board itself (Edge.Cuts arcs "
        "centred 1 mm inside each corner; layout.md §1)", "%d of 4" % sum(found), "4")
    # one closed loop: every end point used exactly twice
    ends = {}
    for a, b in segs + [(a, b) for c, r, a, b in arcs]:
        for p in (a, b):
            k = (round(p[0], 3), round(p[1], 3))
            ends[k] = ends.get(k, 0) + 1
    odd = [k for k, v in ends.items() if v != 2]
    rec("PASS" if not odd else "FAIL", "L5F-edge", "Edge.Cuts is closed (every end point shared by exactly two items)",
        "%d items, %d open ends" % (len(segs) + len(arcs), len(odd)), 0, str(odd[:4]))
    # round 2 (D-118 c): router-bit corners. At every end point of the outline, sample a 0.05 mm circle: the share of
    # it inside the panel material (board outline polygon) is ~0.5 at a smooth joint, ~0.25 at a convex material
    # corner (cut sharp by the bit going round it) and ~0.75 at a concave material corner, which a bit of radius r
    # leaves as a cusp of material of radius r: FAIL. Arcs whose centre lies in the air (the inner corners of the rail
    # notches) need R >= 0.5 mm.
    outl = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outl, False)
    sharp, small = [], []
    for k in ends:
        sh = 0
        for i in range(72):
            a_ = 2 * math.pi * i / 72
            q = bl.to_page(k[0] + 0.05 * math.cos(a_), k[1] + 0.05 * math.sin(a_))
            sh += 1 if outl.Contains(pcbnew.VECTOR2I(q.x, q.y)) else 0
        if sh / 72.0 > 0.6:
            sharp.append("(%.2f, %.2f) %.0f%% material" % (k[0], k[1], 100.0 * sh / 72))
    for c, r, a, b in arcs:
        q = bl.to_page(*c)
        if not outl.Contains(pcbnew.VECTOR2I(q.x, q.y)) and r < 0.5 - 1e-4:
            small.append("arc R %.2f at (%.2f, %.2f)" % (r, c[0], c[1]))
    MEAS["edge_corners"] = {"sharp_concave": sharp, "small_air_arcs": small}
    rec("PASS" if not sharp and not small else "FAIL", "L5F-edge", "routed outline cuttable by a 1.0 mm router bit: no "
        "concave material corner (cusp), air-side arcs R >= 0.5 mm (rail notches at the board corners)",
        "%d end points, %d concave corners, %d small air arcs" % (len(ends), len(sharp), len(small)), 0,
        "; ".join((sharp + small)[:4]))


def _placement_devs():
    """the zone deviations recorded in check_placement.py (DEVIATIONS[("zone", ref)]) plus ZONE_DEV"""
    import re
    src = open(os.path.join(bl.HERE, "check_placement.py"), encoding="utf-8").read()
    out = dict(ZONE_DEV)
    for m in re.finditer(r'\("zone", "([A-Z0-9]+)"\): "(D-[0-9]+[^:"]*)', src):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


def check_final_zones(board, rec):
    devs = _placement_devs()
    zn = bl.zones()
    pl = {r["ref"]: r for r in bl.read_csv("placement.csv")}
    out, dev = [], []
    for ref, row in sorted(pl.items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            out.append(ref + " missing")
            continue
        z = zn.get(CONN_ZONE.get(ref, row["zone"]))
        b = bl.courtyard_bbox(fp)
        if not b:
            b = (lambda bb: (min(bl.to_board(bb.GetOrigin())[0], bl.to_board(bb.GetEnd())[0]),
                             min(bl.to_board(bb.GetOrigin())[1], bl.to_board(bb.GetEnd())[1]),
                             max(bl.to_board(bb.GetOrigin())[0], bl.to_board(bb.GetEnd())[0]),
                             max(bl.to_board(bb.GetOrigin())[1], bl.to_board(bb.GetEnd())[1])))(
                fp.GetBoundingBox(False, False))
        if not z:
            out.append("%s zone %s" % (ref, row["zone"]))
            continue
        tol = 1e-3
        if b[0] >= z["x0"] - tol and b[1] >= z["y0"] - tol and b[2] <= z["x1"] + tol and b[3] <= z["y1"] + tol:
            continue
        if ref in devs:
            dev.append("%s (%s)" % (ref, devs[ref]))
        else:
            out.append("%s outside %s by %.2f mm" % (ref, row["zone"], max(z["x0"] - b[0], z["y0"] - b[1],
                                                                            b[2] - z["x1"], b[3] - z["y1"])))
    rec("PASS" if not out else "FAIL", "L5F-zone", "final board: every part's courtyard inside its placement.csv zone",
        "%d parts, %d recorded deviations" % (len(pl), len(dev)), "0 unrecorded", "; ".join(out[:6]))
    rec("DEV" if dev else "PASS", "L5F-zone", "final board: parts outside their zone by a recorded decision",
        len(dev), "", " ".join(dev))


def check_angles(board, rec, segs):
    u9 = bl.courtyard_bbox(board.FindFootprintByReference("U9"))
    bad = []
    for s in segs:
        g = s[5].GetParentGroup()
        g = g.GetName() if g else ""
        if not g.startswith("L5") or s[1] not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        dx, dy = s[3][0] - s[2][0], s[3][1] - s[2][1]
        L = math.hypot(dx, dy)
        if L < 0.5:
            continue
        # neck-down pieces that leave a U9 pad row or the fan gate may take any angle (D-109 a): one end inside the
        # U9 courtyard, or one end inside the U9_FAN box and the other within 1.5 mm of it (the 46.3 deg PB_INT_N
        # piece ran 2.4 mm out of the box and is no longer exempt)
        if any(u9[0] <= q[0] <= u9[2] and u9[1] <= q[1] <= u9[3] for q in (s[2], s[3])):
            continue
        F_ = (26.6, 28.6, 42.4, 44.4)
        ins = [F_[0] <= q[0] <= F_[2] and F_[1] <= q[1] <= F_[3] for q in (s[2], s[3])]
        if any(ins):
            o = s[3] if ins[0] else s[2]
            if max(F_[0] - o[0], o[0] - F_[2], F_[1] - o[1], o[1] - F_[3], 0) <= 1.5:
                continue
        a = math.degrees(math.atan2(abs(dy), abs(dx)))
        dev = min(abs(a - 0), abs(a - 45), abs(a - 90))
        if dev > 0.5:
            bad.append("%s %s (%.2f,%.2f)-(%.2f,%.2f) %.1f deg" % (s[0], g, s[2][0], s[2][1], s[3][0], s[3][1], a))
    rec("PASS" if not bad else "FAIL", "L5F-geom", "L5 / L5F segments >= 0.5 mm long at 0/45/90 deg within 0.5 deg "
        "(U9_FAN included; only neck-down pieces with an end inside the U9 courtyard exempt; the 46.3 deg PB_INT_N piece)", len(bad), 0, "; ".join(bad[:4]))


def check_l5f(board, rec, segs, vias, drc_json):
    check_bucks(board, rec, vias)
    check_vip(board, rec)
    check_vcut(board, rec)
    check_sw(board, rec, segs, vias)
    check_silk(board, rec)
    check_hops(board, rec, segs, vias)
    check_neck(board, rec, segs)
    check_dangling(rec, drc_json)
    check_edge(board, rec)
    check_final_zones(board, rec)
    check_angles(board, rec, segs)
    return MEAS
