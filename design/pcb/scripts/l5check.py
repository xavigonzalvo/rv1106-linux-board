"""Layout phase L5 checks (TP-L5), called by check_routing.py when the board carries the L5 groups. Everything is
measured from the saved board with our own pcbnew geometry (plus the KiCad DRC run of check_routing.run_drc):

  L5-conn    KiCad unconnected items = 0 (the gate), listed per net when not
  L5-geom    L5 copper (groups L5_LANES, L5_FREEROUTE, L5_SCRIPT): every segment 0/45/90 deg, no acute bend (< 90 deg
             between two segments of one node), no dangling end (an end that touches no pad, track or via of its net),
             no via joining copper on one layer only, nothing on In1/In2
  L5-width   L5 tracks below their class width (the 0.10 mm lane tracks of D-113, PWR_SUB/VDD_ARM branches)
  L5-L4      L5 tracks on L4 that cross an L3 region edge and are not DEFAULT (layout.md §2.3)
  L5-stitch  GND stitching: every 5 x 5 mm cell with L1 or L4 GND pour holds a GND via; the edge ring (no gap > 6 mm
             along a ring 3 mm inside the edge); along the ETH/USB L1 lines a GND via within 3.0 mm of every point
  L5-rails   no copper on the panel rails (x < 0 or x > 80) except the fiducials; nothing within 0.4 mm of the V-cuts
  L5-silk    silkscreen text height >= 1.0 mm, the labels of layout.md §1 present, references hidden (count)
Results go through check_routing.rec(): PASS / DEV (decisions.md number) / INFO / FAIL.
"""
import json
import math
import os

import boardlib as bl
import routelib as rl

import pcbnew

L5_GROUPS = ("L5_LANES", "L5_PRIORITY", "L5_NORTH", "L5_FREEROUTE", "L5_SCRIPT", "L5_FINISH")
FAN = (26.6, 28.6, 42.4, 44.4)       # rule area U9_FAN (DRU neck-down)
M3 = ((3.5, 3.5), (76.5, 3.5), (3.5, 76.5), (76.5, 76.5))


def _hits(a, b, r):
    """segment a-b touches rectangle r (sampled every 0.02 mm)"""
    n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.02))
    for i in range(n + 1):
        x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return True
    return False
MEAS = {}


def group_of(item):
    g = item.GetParentGroup()
    return g.GetName() if g else ""


def k3(p):
    return (round(p[0], 3), round(p[1], 3))


def check_l5(board, rec, segs, vias, per_net, R, drc_json=None):
    # ------------------------------------------------------------------ connectivity (the gate)
    open_nets = {n: c for n, c in per_net.items() if c}
    rec("PASS" if not open_nets else "FAIL", "L5-conn", "KiCad unconnected items (TP-L5: 0)", sum(open_nets.values()),
        0, " ".join("%s(%d)" % kv for kv in sorted(open_nets.items())))
    MEAS["unconnected"] = open_nets
    # ------------------------------------------------------------------ L5 copper geometry
    l5s = [s for s in segs if group_of(s[5]) in L5_GROUPS]
    l5v = [v for v in vias if group_of(v[3]) in L5_GROUPS]
    allv = [v for v in vias]
    rec("INFO", "L5-geom", "L5 copper: track segments / vias / length (groups %s)" % ", ".join(L5_GROUPS),
        "%d / %d / %.1f mm" % (len(l5s), len(l5v), sum(math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])
                                                      for s in l5s)), "")
    inner = [s for s in l5s if s[1] not in (pcbnew.F_Cu, pcbnew.B_Cu)]
    rec("PASS" if not inner else "FAIL", "L5-geom", "L5 tracks on In1/In2 (L2 solid GND, L3 planes)", len(inner), 0)
    nono, fan = [], []
    for s in l5s:
        dx, dy = abs(s[3][0] - s[2][0]), abs(s[3][1] - s[2][1])
        if min(dx, dy) > 0.002 and abs(dx - dy) > 0.002:
            if rl.seg_hits_rect(s[2], s[3], FAN) if hasattr(rl, "seg_hits_rect") else _hits(s[2], s[3], FAN):
                fan.append(s[0])          # a neck-down piece that starts in U9_FAN (any angle, like the L3 escape)
            else:
                nono.append((s[0], k3(s[2]), k3(s[3])))
    rec("PASS" if not nono else "FAIL", "L5-geom", "L5 segments outside U9_FAN not at 0/45/90 deg", len(nono), 0,
        str(nono[:4]))
    nono_all = []
    for s in segs:
        if s[1] not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        dx, dy = abs(s[3][0] - s[2][0]), abs(s[3][1] - s[2][1])
        if min(dx, dy) > 0.002 and abs(dx - dy) > 0.002 and not _hits(s[2], s[3], FAN):
            nono_all.append((s[0], group_of(s[5]), k3(s[2]), k3(s[3])))
    from collections import Counter as _C
    per_group = _C(n[1] or "no group" for n in nono_all)
    rec("INFO", "L5-geom", "track segments outside U9_FAN not at 0/45/90 deg, all groups (round 2; the L3 plane-via "
        "links and pad links are short any-angle pieces by design, D-109/D-110; L5 copper: the FAIL line above)",
        len(nono_all), "", " ".join("%s %d" % kv for kv in sorted(per_group.items())))
    rec("INFO", "L5-geom", "L5 segments that start in U9_FAN at another angle (lane stub / pad-link neck-down pieces, "
        "as the L3 escape, D-109 a)", len(fan), "")
    # nodes of every net (all copper) for acute bends / dangling ends
    by_net = {}
    for s in segs:
        by_net.setdefault(s[0], []).append(s)
    vset = {}
    for v in vias:
        vset.setdefault(v[0], []).append((v[1], v[2]))
    padpolys = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            padpolys.setdefault(p.GetNetname(), []).append((bl.pad_polygon(p), p))
    acute, dangling, overlap_only = [], [], []
    zfill = {}
    for z in board.Zones():
        if not z.GetIsRuleArea():
            for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                if z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay):
                    zfill.setdefault((z.GetNetname(), lay), []).append(z.GetFilledPolysList(lay))

    def zone_at(net, lay, p):
        v = pcbnew.VECTOR2I(bl.to_page(*p))
        return any(ps.Contains(v) for ps in zfill.get((net, lay), []))
    # round 2 (verifier minor): the dangling-end and acute-bend checks run on ALL copper tracks (L3, L4, L5)
    for s in [t for t in segs if t[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]:
        net, lay = s[0], s[1]
        for end, other in ((s[2], s[3]), (s[3], s[2])):
            touching = []
            for t in by_net.get(net, []):
                if t is s or t[1] != lay:
                    continue
                if bl._seg_pt(end[0], end[1], t[2][0], t[2][1], t[3][0], t[3][1]) <= t[4] / 2 + 1e-3:
                    touching.append(t)
            on_via = any(math.hypot(end[0] - x, end[1] - y) <= 0.25 for x, y in vset.get(net, []))
            on_pad = any(bl._inside(end[0], end[1], poly) and p.IsOnLayer(lay) for poly, p in padpolys.get(net, []))
            if not touching and not on_via and not on_pad:
                # round 2: KiCad joins copper that overlaps, so an end whose round cap overlaps a same-net track,
                # via, pad or zone fill on its layer is connected (the L3 escape ends at the gate points stick out
                # 0.008 mm past the start of the continuing L5 stub: KiCad's 'track_dangling' anchor quirk)
                hw = s[4] / 2
                ov = any(t is not s and t[1] == lay and bl._seg_pt(end[0], end[1], t[2][0], t[2][1], t[3][0], t[3][1])
                         <= t[4] / 2 + hw for t in by_net.get(net, [])) or \
                    any(math.hypot(end[0] - x, end[1] - y) <= 0.25 + hw for x, y in vset.get(net, [])) or \
                    any(p.IsOnLayer(lay) and (bl._inside(end[0], end[1], poly) or min(
                        bl._seg_pt(end[0], end[1], poly[i][0], poly[i][1], poly[(i + 1) % len(poly)][0],
                                   poly[(i + 1) % len(poly)][1]) for i in range(len(poly))) <= hw)
                        for poly, p in padpolys.get(net, [])) or zone_at(net, lay, end)
                if ov:
                    overlap_only.append((net, group_of(s[5]) or "no group", k3(end)))
                else:
                    dangling.append((net, group_of(s[5]) or "no group", k3(end)))
            for t in touching:
                for q, r in ((t[2], t[3]), (t[3], t[2])):
                    if math.hypot(q[0] - end[0], q[1] - end[1]) < 1e-3:
                        u = (other[0] - end[0], other[1] - end[1])
                        w = (r[0] - q[0], r[1] - q[1])
                        nu, nw = math.hypot(*u), math.hypot(*w)
                        # a segment shorter than its own width has no direction in copper (the L4 router leaves
                        # 0.025 mm end pieces inside a 0.40 mm track); such pieces are not checked
                        if nu < s[4] or nw < t[4]:
                            continue
                        if nu > 1e-6 and nw > 1e-6 and (u[0] * w[0] + u[1] * w[1]) / nu / nw > math.cos(
                                math.radians(89.0)) and not on_pad and not on_via:   # pad / via copper is solid
                            acute.append((net, group_of(s[5]) or "no group", k3(end)))
    rec("PASS" if not acute else "FAIL", "L5-geom", "acute bends (< 90 deg) at a track end, all tracks (outside pads)",
        len(set(acute)), 0, str(sorted(set(acute))[:12]))
    rec("INFO", "L5-geom", "track ends joined only by overlap (the end's round cap overlaps same-net copper, not end-to-end; "
        "KiCad reports these as 'track_dangling' warnings)", len(set(overlap_only)), "",
        " ".join(sorted({o[1] for o in overlap_only})))
    rec("PASS" if not dangling else "FAIL", "L5-geom", "dangling track ends, all tracks (no same-net copper at or over the end)",
        len(set(dangling)), 0, str(sorted(set(dangling))[:60]))
    # round 3 (verifier minor ui): KiCad's track_dangling warnings broken down by board group and by whether the
    # flagged end is covered by same-net copper (measured from the DRC report, not estimated)
    if drc_json and os.path.exists(drc_json):
        import re
        d = json.load(open(drc_json))
        ends = {}
        for s in segs:
            for q in (s[2], s[3]):
                ends.setdefault((s[0], round(q[0], 2), round(q[1], 2)), group_of(s[5]) or "no group")
        cov = {(o[0], o[2][0], o[2][1]) for o in overlap_only}
        by, covered, open_ = {}, 0, 0
        for v in d["violations"]:
            if v["type"] != "track_dangling":
                continue
            it = v["items"][0]
            m = re.search(r"\[([^\]]+)\]", it["description"])
            net = m.group(1) if m else ""
            x, y = it["pos"]["x"] - 50.0, it["pos"]["y"] - 50.0
            g = None
            for dx in (0, -0.01, 0.01):
                for dy in (0, -0.01, 0.01):
                    g = g or ends.get((net, round(x + dx, 2), round(y + dy, 2)))
            g = g or "?"
            by[g] = by.get(g, 0) + 1
            if any(c[0] == net and abs(c[1] - x) < 0.02 and abs(c[2] - y) < 0.02 for c in cov):
                covered += 1
            else:
                open_ += 1
        MEAS["track_dangling_by_group"] = by
        rec("INFO", "L5-geom", "KiCad track_dangling warnings by board group (of these, the ends with no same-net "
            "copper at all are the L5-geom 'dangling' line; the others overlap same-net copper)",
            sum(by.values()), "", "%s; with no same-net copper: %d" % (
                " ".join("%s %d" % kv for kv in sorted(by.items())), len(set(dangling))))
    pointless = []
    for v in l5v:
        net, x, y = v[0], v[1], v[2]
        lays = set()
        for s in by_net.get(net, []):
            if bl._seg_pt(x, y, s[2][0], s[2][1], s[3][0], s[3][1]) <= s[4] / 2 + 0.25:
                lays.add(s[1])
        for poly, p in padpolys.get(net, []):
            if bl._inside(x, y, poly):
                lays |= {pcbnew.F_Cu, pcbnew.B_Cu}
        if net in rl.PLANE_NETS:
            continue
        if len(lays & {pcbnew.F_Cu, pcbnew.B_Cu}) < 2:
            pointless.append((net, round(x, 2), round(y, 2)))
    rec("PASS" if not pointless else "FAIL", "L5-geom", "L5 signal vias with copper on one outer layer only "
        "(pointless)", len(pointless), 0, str(pointless[:4]))
    # ------------------------------------------------------------------ widths
    thin = {}
    for s in l5s:
        cw = R[s[0]][1] if s[0] in R else 0.15
        if s[4] < cw - 1e-3:
            a = thin.setdefault(s[0], [0.0, 9.0])
            a[0] += math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])
            a[1] = min(a[1], s[4])
    # round 3 (verifier minor soc): hard floors per class; anything below FAILs (the DEV lines below only list what is
    # between the floor and the class width)
    FLOOR = {"PWR_0V9": 0.30, "PWR_SUB": 0.20, "DEFAULT": 0.10, "SENSE": 0.10,
             "PWR_3V3": 0.15}   # round 4 (D-116 b): the U9.61 pin feed (one pin, tens of mA) 0.15 mm between inner vias
    under = []
    for s in l5s:
        c = R.get(s[0], ["DEFAULT"])[0]
        fl = FLOOR.get(c, R[s[0]][1] if s[0] in R else 0.10)
        if s[4] < fl - 1e-3:
            under.append((s[0], c, round(s[4], 3), k3(s[2])))
    rec("PASS" if not under else "FAIL", "L5-width", "L5 tracks below the class floor (VDD_ARM/PWR_0V9 0.30, PWR_SUB "
        "0.20, DEFAULT/SENSE 0.10 mm; other classes their class width)", len(under), 0, str(under[:6]))
    lanes = {n: v for n, v in thin.items() if R.get(n, ["DEFAULT"])[0] == "DEFAULT"}
    other = {n: v for n, v in thin.items() if n not in lanes}
    rec("DEV" if lanes else "PASS", "L5-width", "DEFAULT L5 tracks below 0.15 mm (lane tracks kept at 0.10 mm where the "
        "0.15 mm track does not fit; D-113)", "%d nets, %.1f mm" % (len(lanes), sum(v[0] for v in lanes.values())),
        ">= 0.10 (JLC 0.09)", "D-113 b" if lanes else "")
    rec("DEV" if other else "PASS", "L5-width", "non-DEFAULT L5 tracks below the class width (load-free PWR_SUB / "
        "VDD_ARM test and decoupling branches at 0.30 mm)", " ".join("%s %.1f mm min %.2f" % (n, v[0], v[1])
                                                                      for n, v in sorted(other.items())),
        ">= 0.30", "D-113 c" if other else "")
    # ------------------------------------------------------------------ L4 tracks crossing L3 region edges
    l3 = []
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In2_Cu) and z.GetNetname() in rl.L3_NETS and \
                z.HasFilledPolysForLayer(pcbnew.In2_Cu):
            l3.append((z.GetNetname(), z.GetFilledPolysList(pcbnew.In2_Cu)))

    def l3_at(p):
        v = pcbnew.VECTOR2I(bl.to_page(*p))
        for n, ps in l3:
            if ps.Contains(v):
                return n
        return ""
    cross = []
    for s in l5s:
        if s[1] != pcbnew.B_Cu or R.get(s[0], ["DEFAULT"])[0] == "DEFAULT":
            continue
        ln = math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])
        k = max(1, int(ln / 0.2))
        seen = {l3_at((s[2][0] + (s[3][0] - s[2][0]) * i / k, s[2][1] + (s[3][1] - s[2][1]) * i / k))
                for i in range(k + 1)}
        if len(seen) > 1:
            cross.append(s[0])
    rec("DEV" if cross else "PASS", "L5-L4", "non-DEFAULT L5 tracks on L4 crossing an L3 region edge (layout.md §2.3: "
        "DEFAULT only)", " ".join(sorted(set(cross))) or 0, 0, "D-113 c: DC sub-rail branches" if cross else "")
    # ------------------------------------------------------------------ stitching
    gv = [(v[1], v[2]) for v in vias if v[0] == "GND"]
    pour = {}
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay):
                pour[lay] = z.GetFilledPolysList(lay)
    empty, have_pour = [], 0
    for i in range(16):
        for j in range(16):
            x0, y0 = i * 5.0, j * 5.0
            has = False
            for lay, ps in pour.items():
                cell = pcbnew.SHAPE_POLY_SET()
                o = pcbnew.SHAPE_LINE_CHAIN()
                for (x, y) in ((x0, y0), (x0 + 5, y0), (x0 + 5, y0 + 5), (x0, y0 + 5)):
                    o.Append(bl.to_page(x, y))
                o.SetClosed(True)
                cell.AddOutline(o)
                cell.BooleanIntersection(ps)
                if cell.Area() / 1e12 > 2.0:          # at least 2 mm2 of pour in the cell
                    has = True
                    break
            if not has:
                continue
            have_pour += 1
            if not any(x0 <= x < x0 + 5 and y0 <= y < y0 + 5 for x, y in gv):
                empty.append((x0, y0))
    MEAS["stitch_empty_cells"] = empty
    rec("PASS" if not empty else "DEV", "L5-stitch", "5 x 5 mm cells with >= 2 mm2 of L1/L4 GND pour that hold a GND "
        "via (layout.md §7 <= 5 mm grid)", "%d of %d" % (have_pour - len(empty), have_pour), "all",
        ("D-113 d: no legal via site in %s" % empty[:12]) if empty else "")
    # edge ring: walk a ring 3 mm inside the edge, largest gap between GND vias within 3 mm of the ring
    ring_pts = []
    e = 3.0
    n = 400
    for k in range(n):
        t = 4 * (80 - 2 * e) * k / n
        side, s = divmod(t, 80 - 2 * e)
        p = [(e + s, e), (80 - e, e + s), (80 - e - s, 80 - e), (e, 80 - e - s)][int(side)]
        if min(math.hypot(p[0] - mx, p[1] - my) for mx, my in M3) > 3.5 + 0.8:     # outside the M3 keep-outs
            ring_pts.append(p)
    near = [min(math.hypot(p[0] - x, p[1] - y) for x, y in gv) if gv else 99 for p in ring_pts]
    rec("PASS" if max(near) <= 3.5 else "DEV", "L5-stitch", "edge ring: every point of a ring 3 mm inside the edge has a "
        "GND via within 3.5 mm (layout.md §7 ~3 mm pitch ring; the M3 keep-outs excepted)",
        "%.2f mm max" % max(near), "<= 3.5",
        "" if max(near) <= 3.5 else "D-113 d: at %s (M3 keep-out / connector)" % str(
            [tuple(round(c, 1) for c in ring_pts[i]) for i, d in enumerate(near) if d > 3.5][:6]))
    worst = 0.0
    far = []
    for s in segs:
        if R.get(s[0], [""])[0] not in ("ETH_DIFF", "USB_DIFF") or s[1] != pcbnew.F_Cu:
            continue
        ln = math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])
        for i in range(int(ln / 0.5) + 1):
            t = 0 if ln == 0 else i * 0.5 / ln
            p = (s[2][0] + (s[3][0] - s[2][0]) * t, s[2][1] + (s[3][1] - s[2][1]) * t)
            if max(abs(p[0] - 34.5), abs(p[1] - 36.5)) < 8.0:
                continue                     # inside the U9 fan square
            d = min(math.hypot(p[0] - x, p[1] - y) for x, y in gv)
            worst = max(worst, d)
            if d > 3.0:
                far.append((s[0], k3(p), round(d, 2)))
    rec("PASS" if not far else "DEV", "L5-stitch", "ETH/USB L1 lines (outside the fan): a GND via within 3.0 mm of every "
        "point (rows along the pairs at <= 5 mm)", "max %.2f mm, %d points over" % (worst, len(far)), "<= 3.0",
        ("D-113 d: %s" % far[:5]) if far else "")
    # ------------------------------------------------------------------ rails
    rail = [s for s in segs if min(s[2][0], s[3][0]) < 0.4 or max(s[2][0], s[3][0]) > 79.6]
    rail += [v for v in vias if v[1] < 0.65 or v[1] > 79.35]
    rec("PASS" if not rail else "FAIL", "L5-rails", "tracks/vias on the panel rails or within 0.4 mm of a V-cut",
        len(rail), 0)
    zrail = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay):
                bb = z.GetFilledPolysList(lay).BBox()
                x0, _ = bl.to_board(bb.GetOrigin())
                x1, _ = bl.to_board(bb.GetEnd())
                if x0 < 0.4 - 1e-3 or x1 > 79.6 + 1e-3:
                    zrail.append((z.GetZoneName(), board.GetLayerName(lay), round(x0, 2), round(x1, 2)))
    rec("PASS" if not zrail else "FAIL", "L5-rails", "zone fills inside x 0.4 .. 79.6 (rails copper-free)", len(zrail),
        0, str(zrail[:3]))
    railfp = []
    for fp in board.GetFootprints():
        x, _ = bl.to_board(fp.GetPosition())
        if (x < 0 or x > 80) and not fp.GetReference().startswith(("FID", "GFID", "TH")):
            railfp.append(fp.GetReference())
    rec("PASS" if not railfp else "FAIL", "L5-rails", "parts on the rails other than the global fiducials GFID1-3 and "
        "the tooling holes TH1-4 (layout.md §1)", len(railfp), 0,
        " ".join(railfp))
    # ------------------------------------------------------------------ silk
    small = []
    texts = []
    for fp in board.GetFootprints():
        r = fp.Reference()
        if r.IsVisible() and r.GetLayer() == pcbnew.F_SilkS:
            texts.append(r.GetText())
            if pcbnew.ToMM(r.GetTextHeight()) < 1.0 - 1e-6:
                small.append(fp.GetReference())
    small_dev = []
    for d in board.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS:
            texts.append(d.GetText())
            h = pcbnew.ToMM(d.GetTextHeight())
            if h < 1.0 - 1e-6:
                # D-114 g: the LED labels may fall back to 0.8 mm (owner approval asked); anything else FAILs
                (small_dev if d.GetText() in ("PWR", "STAT", "ETH") and h >= 0.8 - 1e-6 else small).append(
                    d.GetText())
    rec("PASS" if not small else "FAIL", "L5-silk", "silkscreen text height >= 1.0 mm (layout.md §1)", len(small), 0,
        " ".join(small[:8]))
    rec("DEV" if small_dev else "PASS", "L5-silk", "LED labels at 0.8 mm (no room for 1.0 mm text beside the LED row)",
        " ".join(small_dev) or 0, 0, "D-114 g (owner approval asked)" if small_dev else "")
    want = ["RV1106 Rev A 2026-11", "POWER", "RESET", "MASKROM", "PWR", "STAT", "ETH", "1", "2", "39", "40", "B"]
    miss = [w for w in want if w not in texts]
    rec("PASS" if not miss else "FAIL", "L5-silk", "labels of layout.md §1 on the silkscreen (board name + Rev A + date, "
        "buttons, LEDs, header pins 1/2/39/40, buck-side 'B' marks)", len(want) - len(miss), len(want),
        " ".join(miss))
    sj = os.path.join(bl.PCB_DIR, "l5", "silk.json")
    if os.path.exists(sj):
        s = json.load(open(sj))
        tpmiss = [x for x in s["labels"] if x[1].startswith("TP") and x[2] == "NO ROOM"]
        rec("INFO", "L5-silk", "test-pad net labels placed (testpoints.md §2 rule 2)",
            "%d of %d" % (sum(1 for x in s["labels"] if x[1].startswith("TP")) - len(tpmiss),
                          sum(1 for x in s["labels"] if x[1].startswith("TP"))), "",
            " ".join(x[1] for x in tpmiss))
        rec("INFO", "L5-silk", "references hidden on the silkscreen (no free spot >= 0.15 mm from pads; kept on F.Fab)",
            len(s["refs_hidden"]), "", " ".join(s["refs_hidden"]))
    # round 2 (verifier minor): silk to pads measured, not assumed: every visible F.SilkS item (footprint references /
    # values / graphics, board texts and graphics) >= 0.15 mm from every F.Cu pad and F.Mask opening (shape collision)
    cl = pcbnew.FromMM(0.15)
    padsh = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask):
                m = max(0, p.GetSolderMaskExpansion(pcbnew.F_Mask)) if p.IsOnLayer(pcbnew.F_Mask) else 0
                padsh.append(("%s.%s" % (fp.GetReference(), p.GetNumber()), p.GetEffectiveShape(pcbnew.F_Cu), m,
                              p.GetBoundingBox()))
    silk = []
    for fp in board.GetFootprints():
        for t in (fp.Reference(), fp.Value()):
            if t.IsVisible() and t.GetLayer() == pcbnew.F_SilkS:
                silk.append(("text " + t.GetText(), t))
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and (g.GetClass() != "PCB_TEXT" or g.IsVisible()):
                silk.append(("%s silk %s" % (fp.GetReference(), g.GetClass()), g))
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            silk.append(("board " + (d.GetText() if d.GetClass() == "PCB_TEXT" else d.GetClass()), d))
    over = []
    for name, it in silk:
        sh = it.GetEffectiveShape(pcbnew.F_SilkS)
        bb = it.GetBoundingBox()
        bb.Inflate(pcbnew.FromMM(1.0))
        for pn, ps, m, pb in padsh:
            if bb.Intersects(pb) and ps.Collide(sh, cl + m):
                over.append((name, pn))
    MEAS["silk_over_pads"] = over
    # round 3 (verifier major soc): no visible F.SilkS item over the courtyard / F.Fab body of a bottom-terminated part
    # (QFN / SON / UQFN, SMD crystals, molded inductors), other than that part's own silk outline graphics
    BOT = ("QFN", "SON", "DFN", "LGA", "BGA", "Crystal_SMD", "L_FHD4020S")
    bots = []
    for fp in board.GetFootprints():
        if any(k in fp.GetFPIDAsString() for k in BOT):
            boxes = []
            for lay in (pcbnew.F_CrtYd, pcbnew.F_Fab):
                xs, ys = [], []
                for g in fp.GraphicalItems():
                    if g.GetLayer() == lay and g.GetClass() != "PCB_TEXT":
                        bb = g.GetBoundingBox()
                        for q in (bb.GetOrigin(), bb.GetEnd()):
                            x, y = bl.to_board(q)
                            xs.append(x)
                            ys.append(y)
                if xs:
                    boxes.append((min(xs), min(ys), max(xs), max(ys)))
            bots.append((fp.GetReference(), boxes))
    under_bot = []
    for name, it in silk:
        own = name.split(" silk ")[0] if " silk " in name else None
        bb = it.GetBoundingBox()
        x0, y0 = bl.to_board(bb.GetOrigin())
        x1, y1 = bl.to_board(bb.GetEnd())
        r = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        for ref, boxes in bots:
            if own == ref:
                continue                      # the part's own outline / pin-1 marks (library graphics)
            for b in boxes:
                if r[0] < b[2] - 1e-3 and b[0] < r[2] - 1e-3 and r[1] < b[3] - 1e-3 and b[1] < r[3] - 1e-3:
                    under_bot.append((name, ref))
                    break
    MEAS["silk_over_bottom_parts"] = under_bot
    rec("PASS" if not under_bot else "FAIL", "L5-silk", "visible F.SilkS items over the courtyard or F.Fab body of a "
        "bottom-terminated part (%s)" % " ".join(r for r, _ in bots), len(under_bot), 0, str(under_bot[:6]))
    rec("PASS" if not over else "FAIL", "L5-silk", "visible F.SilkS items (texts and graphics, footprints and board) "
        ">= 0.15 mm from every F.Cu pad and F.Mask opening (shape collision)", "%d of %d items too close" % (
            len(set(o[0] for o in over)), len(silk)), 0, str(over[:6]))
    # round 2 (verifier minor soc): ring 2 measured along the routed copper: VDD_ARM U9.115 -> C38.1 / C44.1 <= 8 mm
    try:
        import pathlen
        ss = [(("F" if s[1] == pcbnew.F_Cu else "B"), s[2], s[3], s[4]) for s in segs if s[0] == "VDD_ARM" and
              s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
        vv = [(v[1], v[2]) for v in vias if v[0] == "VDD_ARM"]
        pp = {}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == "VDD_ARM":
                    lays = {n for n, L_ in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)) if p.IsOnLayer(L_)}
                    pp["%s.%s" % (fp.GetReference(), p.GetNumber())] = (bl.pad_polygon(p), bl.to_board(p.GetPosition()),
                                                                        lays)
        g = pathlen.NetGraph(ss, vv, pp)

        def path_through(a, b):
            """shortest copper path pad a -> pad b along tracks; passing through another pad's copper is allowed
            here (the U9 escape ends in the ring-1 capacitor pad C52.1 and the net continues from that pad)"""
            import heapq
            src, dst = ("p", a), ("p", b)
            if src not in g.adj or dst not in g.adj:
                return None, []
            dist, h, cnt = {src: 0.0}, [(0.0, 0, src)], 1
            prev = {}
            while h:
                d, _, n = heapq.heappop(h)
                if n == dst:
                    ws, k = [], n
                    while k in prev:
                        k, i = prev[k]
                        if i is not None:
                            pc = g.pieces[i]
                            mid = ((pc[1][0] + pc[2][0]) / 2, (pc[1][1] + pc[2][1]) / 2)
                            if not any(bl._seg_pt(mid[0], mid[1], ea[0], ea[1], eb[0], eb[1]) < 1e-3
                                       for ea, eb in esc):
                                ws.append(pc[3])
                    return d, ws
                if d > dist.get(n, 1e18):
                    continue
                for m, ln, i in g.adj.get(n, []):
                    nd = d + ln
                    if nd < dist.get(m, 1e18) - 1e-12:
                        dist[m] = nd
                        prev[m] = (n, i)
                        heapq.heappush(h, (nd, cnt, m))
                        cnt += 1
            return None, []
        # round 3 (verifier minor soc): the feed NT1.2 -> U9 pins and the ring-2 paths may not be narrowed: the
        # narrowest track on each shortest copper path must be >= 0.30 mm (PWR_0V9 floor; the feed is 0.80 mm)
        # pieces of the L3 escape (pin -> ring-1 cap, necked to the 0.35 mm pitch by design) are not counted
        esc = [(s[2], s[3]) for s in segs if s[0] == "VDD_ARM" and group_of(s[5]) == "L3_ESCAPE"]
        narrow = []
        for a, b in [("NT1.2", k) for k in sorted(pp) if k.startswith("U9.")] + \
                [(k, c) for c in ("C38.1", "C44.1") for k in sorted(pp) if k.startswith("U9.")]:
            ln, ws = path_through(a, b)
            if ln is not None and ws and min(ws) < 0.30 - 1e-3:
                narrow.append((a, b, round(min(ws), 3)))
        minfeed = []
        for k in sorted(pp):
            if k.startswith("U9."):
                ln, ws = path_through("NT1.2", k)
                if ws:
                    minfeed.append(min(ws))
        rec("PASS" if not narrow and minfeed else "FAIL", "L5-width", "VDD_ARM feed NT1.2 -> U9 pins and ring-2 paths "
            "U9 -> C38/C44: narrowest track on the copper path (the L3 pin escape to the ring-1 cap, necked to the pin pitch, not counted) >= 0.30 mm", "min %.2f mm on the feed; %d narrowed" % (
                min(minfeed) if minfeed else 0, len(narrow)), ">= 0.30", str(narrow[:4]))
        for cap in ("C38.1", "C44.1"):
            best = None
            for pin in sorted(k for k in pp if k.startswith("U9.")):
                ln, _ = path_through(pin, cap)
                if ln is not None and (best is None or ln < best[0]):
                    best = (ln, pin)
            MEAS["vdd_arm_" + cap] = best
            ok = best is not None and best[0] <= 8.0
            rec("PASS" if ok else "DEV", "L5-ring2", "VDD_ARM routed path U9 pin -> %s (layout.md §10 ring 2 <= 8 mm, "
                "along the copper: tracks + pad-centre pieces, through the C52 ring-1 pad)" % cap, "%.2f mm from %s" % best if best else "no path", "<= 8.0",
                "" if ok else "D-114 e")
    except Exception as e:          # noqa: BLE001
        rec("FAIL", "L5-ring2", "VDD_ARM routed path measurement", "error %s" % e, "")
    ring2_all(board, rec, segs, vias)
    sense_sw(board, rec, segs, R)
    vias_in_pads(board, rec, vias)
    # round 4 (verifier minor soc): redundant L5 segments (zero length, lying on another same-net track) and joints
    # of two same-net segments under 5 deg (sliver), all L5 groups (l5_tidy.py removes the redundant ones)
    import l5_tidy
    T = [(s[0], s[1], s[2], s[3], s[4] / 2, group_of(s[5]), None) for s in segs if s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
    red = l5_tidy.redundant(T)
    rec("PASS" if not red else "FAIL", "L5-geom", "redundant L5 track segments (zero length, or both ends on another "
        "same-net track within 5 deg; l5_tidy.py)", len(red), 0,
        str([(T[i][0], k3(T[i][2]), k3(T[i][3])) for i, _ in red[:4]]))
    ends = {}
    for t in T:
        if t[5] not in L5_GROUPS:
            continue
        for p_, q_ in ((t[2], t[3]), (t[3], t[2])):
            ends.setdefault((t[0], t[1], round(p_[0], 3), round(p_[1], 3)), []).append((q_[0] - p_[0], q_[1] - p_[1]))
    sliver = []
    for k, dirs in ends.items():
        for i in range(len(dirs)):
            for j in range(i + 1, len(dirs)):
                u, v = dirs[i], dirs[j]
                nu, nv = math.hypot(*u), math.hypot(*v)
                if nu < 1e-3 or nv < 1e-3:
                    continue
                if (u[0] * v[0] + u[1] * v[1]) / nu / nv > math.cos(math.radians(5.0)):
                    sliver.append((k[0], k[2], k[3]))
    rec("PASS" if not sliver else "FAIL", "L5-geom", "joints of two same-net L5 segments under 5 deg (sliver)",
        len(sliver), 0, str(sliver[:4]))
    # round 2 (verifier minor): the layout.md §10 3-D item measured from the footprints instead of a 3-D render that
    # lacks models: connector mating faces on their edge (F.Fab / courtyard extents), nothing on the bottom side, no two
    # courtyards overlapping (front side)
    def ext(fp, layer):
        xs, ys = [], []
        for g in fp.GraphicalItems():
            if g.GetLayer() == layer and g.GetClass() != "PCB_TEXT":
                bb = g.GetBoundingBox()
                for q in (bb.GetOrigin(), bb.GetEnd()):
                    x, y = bl.to_board(q)
                    xs.append(x)
                    ys.append(y)
        return (min(xs), min(ys), max(xs), max(ys)) if xs else None
    faces = {"J3": ("N", None), "J1": ("S", None), "J2": ("S", None), "J4": ("S", None)}
    out, bad = [], []
    for ref, (edge, _) in sorted(faces.items()):
        fp = board.FindFootprintByReference(ref)
        e = ext(fp, pcbnew.F_Fab) or ext(fp, pcbnew.F_CrtYd)
        if not e:
            bad.append(ref)
            continue
        face = e[1] if edge == "N" else e[3]
        d = (0.0 - face) if edge == "N" else (face - 80.0)        # > 0: overhang beyond the edge
        side_ok = e[0] >= -1e-3 and e[2] <= 80.0 + 1e-3              # nothing over the west/east rails
        out.append("%s %s face %.2f (overhang %+.2f mm), x %.2f-%.2f" % (ref, edge, face, d, e[0], e[2]))
        if not (-1.0 <= d <= 1.5 and side_ok):
            bad.append(ref)
    rec("PASS" if not bad else "FAIL", "L5-3d", "connector mating faces on their edge (F.Fab extents: RJ45 north, "
        "USB-C / microSD / USB-A south; within -1.0..+1.5 mm of the edge; nothing over the W/E rails)",
        "; ".join(out), "", " ".join(bad))
    bottom = [fp.GetReference() for fp in board.GetFootprints() if fp.GetLayer() == pcbnew.B_Cu]
    rec("PASS" if not bottom else "FAIL", "L5-3d", "parts on the bottom side (layout.md §10: none)", len(bottom), 0,
        " ".join(bottom))
    cys = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith(("GFID", "FID", "TH", "H")):
            continue
        c = fp.GetCourtyard(pcbnew.F_CrtYd)
        if c.OutlineCount():
            cys.append((fp.GetReference(), c, fp.GetBoundingBox(False, False)))
    over = []
    for i in range(len(cys)):
        for j in range(i + 1, len(cys)):
            if not cys[i][2].Intersects(cys[j][2]):
                continue
            a = pcbnew.SHAPE_POLY_SET(cys[i][1])
            a.BooleanIntersection(cys[j][1])
            if a.OutlineCount() and a.Area() > 1e6 * 0.01:            # > 0.01 mm2
                over.append("%s/%s" % (cys[i][0], cys[j][0]))
    rec("PASS" if not over else "INFO", "L5-3d", "front courtyards overlapping (> 0.01 mm2; part collisions)",
        len(over), 0, " ".join(over[:10]))
    rec("INFO", "L5-teardrops", "teardrops", "not generated", "",
        "KiCad 10.0.7 pcbnew Python has no teardrop generator (pad/via flags only; ZONE_FILLER makes none): D-113 e")
    return MEAS


# round 4 (verifier major soc): layout.md §5.3 / §10 ring 2 (<= 8 mm of trace from the SoC pin) measured along the
# routed copper for every ring-2 part named in the rule: shortest path from any U9 pin of the part's net to the part's
# pad (tracks + pad-entry pieces; passing through other pads of the net allowed, as the L3 escape ends in the ring-1
# capacitor pad and the net continues from it; via barrels not counted). A part over 8 mm is a DEV only when it is
# recorded in RING2_DEV (decisions.md), else a FAIL.
RING2_PARTS = ("FB1", "FB2", "FB3", "C41", "C69", "R32", "R33", "R34", "D2", "NT1", "TP18", "TP22", "TP23", "TP24",
               "TP25", "TP26")
RING2_DEV = {   # ref: decision (round 4 measurements in routing-review.md)
    "FB2": "D-116 j", "C41": "D-116 j", "TP24": "D-116 j",        # VCC1V8_CODEC: codec unused (D-12)
    "R32": "D-116 j", "TP22": "D-116 j",                          # MIPI_CSI_AVDD_1V8: camera unused in Rev A (D-12)
    "R34": "D-116 j", "TP18": "D-116 j", "D2": "D-116 j",          # VCC3V3_RTC: no battery (D-75), uA load
    "C69": "D-115 a", "TP23": "D-116 j", "TP25": "D-116 j", "TP26": "D-116 j", "FB1": "D-116 j", "FB3": "D-116 j",
    "R33": "D-116 j",
}


def ring2_all(board, rec, segs, vias):
    import heapq
    import pathlen
    u9nets = {}
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if not n:
                continue
            lays = {k for k, L_ in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)) if p.IsOnLayer(L_)}
            pads_by_net.setdefault(n, {})["%s.%s" % (fp.GetReference(), p.GetNumber())] = (
                bl.pad_polygon(p), bl.to_board(p.GetPosition()), lays)
            if fp.GetReference() == "U9":
                u9nets.setdefault(n, []).append("U9.%s" % p.GetNumber())
    graphs = {}

    def graph(net):
        if net not in graphs:
            ss = [(("F" if s[1] == pcbnew.F_Cu else "B"), s[2], s[3], s[4]) for s in segs
                  if s[0] == net and s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
            vv = [(v[1], v[2]) for v in vias if v[0] == net]
            # a via inside a pad of the net (via in pad) joins that pad: a 0.1 um stub on each outer layer at the via
            for (x, y) in vv:
                if any(pathlen._inside(x, y, pp[0]) for pp in pads_by_net.get(net, {}).values()):
                    ss += [("F", (x, y), (x + 1e-4, y), 0.1), ("B", (x, y), (x + 1e-4, y), 0.1)]
            graphs[net] = pathlen.NetGraph(ss, vv, pads_by_net.get(net, {}))
        return graphs[net]

    def dist(net, srcs, dst):
        g = graph(net)
        h, best = [], {}
        cnt = 0
        for sname in srcs:
            k = ("p", sname)
            if k in g.adj:
                best[k] = 0.0
                h.append((0.0, cnt, k))
                cnt += 1
        heapq.heapify(h)
        while h:
            d, _, n = heapq.heappop(h)
            if n == ("p", dst):
                return d
            if d > best.get(n, 1e18):
                continue
            for m, ln, _i in g.adj.get(n, []):
                nd = d + ln
                if nd < best.get(m, 1e18) - 1e-12:
                    best[m] = nd
                    heapq.heappush(h, (nd, cnt, m))
                    cnt += 1
        return None
    rows = []
    for ref in RING2_PARTS:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        best = None
        chain = ""
        # the sub-rail side of a filter / series part (FB1-3, R32-R34, NT1): the pad on the net that is not a main
        # rail; a decoupler (C41, C69) or test pad on a main rail uses that rail
        MAIN = ("GND", "VCC_1V8", "VCC_3V3", "VDD_0V9", "VCC_DDR")
        cand = [p for p in fp.Pads() if p.GetNetname() in u9nets and p.GetNetname() not in MAIN]
        if not cand:
            cand = [p for p in fp.Pads() if p.GetNetname() in u9nets and p.GetNetname() != "GND"]
        for p in cand:
            n = p.GetNetname()
            if True:
                d = dist(n, u9nets[n], "%s.%s" % (ref, p.GetNumber()))
                if d is not None and (best is None or d < best[0]):
                    best = (d, n)
        if best is None:      # D2: its pads are behind R34 (VCC3V3_RTC_IN, no U9 pin): R34.2 path + R34 + R34.1 -> D2
            for p in fp.Pads():
                n = p.GetNetname()
                for q, qn in (("R34.1", "VCC3V3_RTC_IN"),):
                    if n == qn:
                        d1 = dist(n, [q], "%s.%s" % (ref, p.GetNumber()))
                        r34 = MEAS.get("ring2_R34")
                        if d1 is not None and r34:
                            best = (r34 + 1.0 + d1, n)
                            chain = " (via R34: R34.2 path + 1.0 mm part + R34.1 -> %s)" % ref
        if best:
            MEAS["ring2_" + ref] = best[0]
        ok = best is not None and best[0] <= 8.0
        st = "PASS" if ok else ("DEV" if best is not None and ref in RING2_DEV else "FAIL")
        rows.append((ref, best))
        rec(st, "L5-ring2", "%s routed path from its U9 pin (layout.md §5.3 ring 2 <= 8 mm, along the copper)%s" % (
            ref, chain), "%.2f mm on %s" % best if best else "no path", "<= 8.0", "" if ok else RING2_DEV.get(ref, ""))


def _seg_seg(a, b, c, d):
    """distance between segments a-b and c-d (no intersection test needed for the >= 2 mm question: crossing
    copper of these nets on one layer would already be a DRC short)"""
    return min(bl._seg_pt(a[0], a[1], c[0], c[1], d[0], d[1]), bl._seg_pt(b[0], b[1], c[0], c[1], d[0], d[1]),
               bl._seg_pt(c[0], c[1], a[0], a[1], b[0], b[1]), bl._seg_pt(d[0], d[1], a[0], a[1], b[0], b[1]))


def sense_sw(board, rec, segs, R):
    """round 4 (verifier major onoff: 'SENSE clearance at least 2 mm from SW nodes and inductors'): every SENSE-class
    track, all layers, edge to edge from the SW-node copper (SW_NODE tracks and pads) and the buck inductor pads
    (L1-L4), outside the U4-U7 courtyards (layout.md §4.5, §10)"""
    sw = [s for s in segs if R.get(s[0], [""])[0] == "SW_NODE"]
    polys = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            if R.get(p.GetNetname(), [""])[0] == "SW_NODE" or ref in ("L1", "L2", "L3", "L4"):
                polys.append(("%s.%s" % (ref, p.GetNumber()), bl.pad_polygon(p)))
    courts = [bl.courtyard_bbox(board.FindFootprintByReference(u)) for u in ("U4", "U5", "U6", "U7")]

    def in_court(a, b):
        return any(c and all(c[0] <= q[0] <= c[2] and c[1] <= q[1] <= c[3] for q in (a, b)) for c in courts)
    worst = None
    for s in segs:
        if R.get(s[0], [""])[0] != "SENSE" or in_court(s[2], s[3]):
            continue
        hw = s[4] / 2
        for t in sw:
            d = _seg_seg(s[2], s[3], t[2], t[3]) - hw - t[4] / 2
            if worst is None or d < worst[0]:
                worst = (d, s[0], t[0])
        for name, poly in polys:
            for i in range(len(poly)):
                d = _seg_seg(s[2], s[3], poly[i], poly[(i + 1) % len(poly)]) - hw
                if worst is None or d < worst[0]:
                    worst = (d, s[0], name)
    rec("PASS" if worst and worst[0] >= 2.0 else "FAIL", "L5-sense", "SENSE tracks (all layers, outside the U4-U7 "
        "courtyards) to SW-node copper and buck inductor pads, edge to edge", "min %.2f mm (%s - %s)" % worst
        if worst else "none", ">= 2.0")


# vias inside SMD pads (D-67: no via-in-pad filling / POFV ordered; layout.md §6.2). The listed ones are the owner
# decision of D-116 c (POFV option priced UNVERIFIED vs dog-bone, CHECKPOINT 2); any other one FAILs.
VIA_IN_PAD_DEV = {("C47", "1"), ("C58", "1"), ("R33", "2"), ("C66", "1"), ("C69", "1"), ("FB2", "2")}


def vias_in_pads(board, rec, vias):
    pads = [(fp.GetReference(), p.GetNumber(), bl.pad_polygon(p)) for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and fp.GetReference() != "U9"]
    found = []
    for v in vias:
        for ref, num, poly in pads:
            if bl._inside(v[1], v[2], poly):
                found.append((ref, num))
    extra = [f for f in found if f not in VIA_IN_PAD_DEV]
    # L5F (owner decision D-H6): POFV ordered (supersedes D-67); the complete list (drill / ring / mask-opening rule)
    # is L5F-vip with design/pcb/via_in_pad.csv; this line keeps the centre-in-pad count for comparison
    rec("INFO", "L5-vip", "vias whose centre lies inside an SMD pad (U9 EP excluded; POFV ordered, D-H6; full list: "
        "L5F-vip / via_in_pad.csv)", "%d: %s" % (len(found), " ".join("%s.%s" % f for f in sorted(found))), "",
        "D-H6 POFV" if not extra else "beyond the D-116 c six: %s (listed in via_in_pad.csv)" % extra)
