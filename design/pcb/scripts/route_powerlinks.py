#!/usr/bin/env python3
"""Layout phase L3, step 6: power links for the plane-net pads that no plane via within reach could serve (D-109 f).

    $PY design/pcb/scripts/route_powerlinks.py       # after planes.py + fill_zones.py; then fill_zones.py again

Each link starts at a pad and ends in a new via 0.3/0.5 mm that lands inside the filled L3 copper of the pad's own
net (VDD_0V9 / VCC_3V3 / VCC5V0_SYS / VBUS_USBA; >= 0.5 mm inside the fill), or on a via of its net already there
(GND: any GND via, L2 is everywhere). Path: our own 2-layer grid A* (L1 and L4,
0.10 mm grid near the SoC, 0.20 mm for the long header 5 V feed) over a blocked map built from the real copper with
the class clearances + 0.03 mm, the board hole clearance and hole-to-hole for vias, the trial-route corridors of the
critical nets (D-107/D-108) and the U9 gate-lane exits kept free. Widths: the header 5 V feed 1.00 mm on L4 (layout.md
§3 "VCC5V0_SYS feed >= 1.0 mm on L4"), the others 0.30 mm (pull-ups, test pads, the ESD VBUS pin, single 100 nF / 1 uF
caps: < 50 mA; DC). The list of links is fixed below (reproducible); everything goes in the board group L3_POWERLINKS.
"""
import heapq
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import route_planevias as pv  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

# (ref, pad, width, layers allowed, grid, margin of the search window around pad + nearest fill)
LINKS = [
    ("C84", "1", 0.20, "F", 0.05),
    ("U11", "10", 0.20, "F", 0.05),
    ("C36", "1", 0.20, "F", 0.05),
    ("C42", "1", 0.20, "F", 0.05),
    ("U2", "5", 0.20, "F", 0.05),
    ("R10", "1", 0.30, "FB", 0.10),
    ("R6", "1", 0.30, "FB", 0.10),
    ("TP2", "1", 0.30, "FB", 0.10),
    ("TP4", "1", 0.30, "FB", 0.10),
    ("TP17", "1", 0.30, "FB", 0.10),
    ("U2", "2", 0.20, "F", 0.05),
    ("R60", "2", 0.20, "F", 0.05),
    ("J5", "4", 1.00, "B", 0.20, (3.5, 9.0, 78.0, 23.5)),   # north band, south of the J3 pins (§3), not across the SoC
    ("J5", "2", 1.00, "B", 0.10),
    ("U9", "61", 0.30, "B", 0.05),      # D-110: from the inner via of pin 61 (NE corner, no L3 finger fits) on L4
]
# links that start at the inner via of a U9 pin (route_escape.py) instead of at a pad; the L4 track may run under the
# package (DRU neck-down area), the via's own position is the start
VIA_START = {("U9", "61")}
# a link may also end on copper of its own net that is already on the plane: a via in the net's L3 fill, or these pads
PAD_TARGETS = {("J5", "2"): [("J5", "4")], ("U11", "10"): [("C84", "1")]}
# D-107 breakout boxes: inside them the trial pair corridors keep only the class clearance (0.15) + grid tolerance
BREAKOUT_PAD = {"U11": 2.0, "U1": 0.5, "U2": 0.5, "J1": 0.5}
VIA_COST = 1.5
_R = rl.rules()
_BOXES = []
_SW = []            # the four buck SW nodes (SW pads' box + 0.3 mm): closed to L4 links


def set_sw(board):
    del _SW[:]
    for net in ("U4_SW", "U5_SW", "U6_SW", "U7_SW"):
        pts = [q for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == net
               for q in bl.pad_polygon(p)]
        _SW.append((min(q[0] for q in pts) - 0.3, min(q[1] for q in pts) - 0.3, max(q[0] for q in pts) + 0.3,
                    max(q[1] for q in pts) + 0.3))


def fill_hit(board, net, x, y, margin=0.5):
    pts = [(x, y)] + [(x + margin * math.cos(a), y + margin * math.sin(a)) for a in
                      (0, math.pi / 2, math.pi, 3 * math.pi / 2, math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4,
                       7 * math.pi / 4)]
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != net or z.GetLayer() != pcbnew.In2_Cu:
            continue
        if all(z.HitTestFilledArea(pcbnew.In2_Cu, bl.to_page(px, py)) for px, py in pts):
            return True
    return False


def route(board, sp, R, ref, num, w, layers, grid, ctx, box=None):
    fp = board.FindFootprintByReference(ref)
    pad = [p for p in fp.Pads() if p.GetNumber() == num][0]
    net = pad.GetNetname()
    poly = bl.pad_polygon(pad)
    sx, sy = bl.to_board(pad.GetPosition())
    via_start = (ref, num) in VIA_START
    if via_start:
        # the same-net via joined by an L1 track to this pad, under the package
        best = None
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == net:
                vx, vy = bl.to_board(t.GetPosition())
                if rl.in_fan(vx, vy):
                    d = math.hypot(vx - sx, vy - sy)
                    if d < 2.5 and (best is None or d < best[0]):
                        best = (d, vx, vy)
        if best is None:
            return None, "no inner via of %s.%s" % (ref, num)
        _d, sx, sy = best
        poly = [(sx - 0.12, sy - 0.12), (sx + 0.12, sy - 0.12), (sx + 0.12, sy + 0.12), (sx - 0.12, sy + 0.12)]
    clr = rl.class_clear(net, R)
    # search window: grow until a target exists
    for half in ((None,) if box else (6.0, 12.0, 20.0, 40.0, 70.0)):
        if box:
            x0, y0, x1, y1 = box
        else:
            x0, y0 = max(0.7, sx - half), max(0.7, sy - half)
            x1, y1 = min(79.3, sx + half), min(79.3, sy + half)
        nx, ny = int((x1 - x0) / grid) + 1, int((y1 - y0) / grid) + 1
        if nx * ny > 400000:
            continue
        # targets: via-legal cells inside the own net's L3 fill
        targets = set()
        step = max(1, int(0.3 / grid))
        for i in range(0, nx, step):
            for j in range(0, ny, step):
                x, y = x0 + i * grid, y0 + j * grid
                if (net == "GND" or fill_hit(board, net, x, y)) and pv.legal_via(x, y, net, R, sp, ctx[0], ctx[1], ctx[2], ref, ctx[3]) is not None:
                    targets.add((i, j))
        own = []
        for t in sp.items:
            if t.net == net and t.kind == "circle" and t.tag == "via" and (net == "GND" or
                                                                           fill_hit(board, net, t.a[0], t.a[1], 0.3)):
                own.append(t)
        for r2, n2 in PAD_TARGETS.get((ref, num), []):
            p2 = [q for q in board.FindFootprintByReference(r2).Pads() if q.GetNumber() == n2][0]
            own.append(rl.Shape("poly", rl.LAYERS, net, clr, "pad", pts=bl.pad_polygon(p2)))
        touch = set()
        for t in own:
            bb = t.bbox
            for i in range(max(0, int((bb[0] - x0 - w) / grid)), min(nx, int((bb[2] - x0 + w) / grid) + 2)):
                for j in range(max(0, int((bb[1] - y0 - w) / grid)), min(ny, int((bb[3] - y0 + w) / grid) + 2)):
                    probe = rl.Shape("circle", rl.LAYERS, net, clr, "probe", a=(x0 + i * grid, y0 + j * grid), r=w / 2)
                    if rl.shape_dist(probe, t) <= -0.05:
                        touch.add((i, j))
        targets |= touch
        if targets:
            break
    if not targets:
        return None, "no via site in the %s L3 fill" % net
    blocked = {}

    def free(i, j, L):
        k = (i, j, L)
        if k not in blocked:
            x, y = x0 + i * grid, y0 + j * grid
            s = rl.Shape("circle", [L], net, clr, "probe", a=(x, y), r=w / 2)
            bad = [c for c in sp.conflicts(s, extra=0.03) if hard_conflict(c[0], c[1], x, y)]
            hole = [c for c in sp.near(s, 0.8) if c.kind == "circle" and c.tag == "via" and c.net != net and
                    math.hypot(c.a[0] - x, c.a[1] - y) - w / 2 - rl.VIA_DRILL / 2 < rl.HOLE_CLEAR + 0.02]
            under_sw = L == "B" and any(r[0] - w / 2 <= x <= r[2] + w / 2 and r[1] - w / 2 <= y <= r[3] + w / 2
                                        for r in _SW)    # layout.md §4.5: nothing on L4 under a SW node (D-112 g)
            blocked[k] = not bad and not hole and not under_sw and (not rl.in_fan(x, y) or (via_start and L == "B"))
        return blocked[k]

    start = []
    for i in range(nx):
        for j in range(ny):
            x, y = x0 + i * grid, y0 + j * grid
            if rl.inside(x, y, poly) and rl.pt_poly((x, y), [(px, py) for px, py in poly]) >= 0:
                start.append((i, j))
    if not start:
        return None, "pad not on the grid"
    tx = sum(t[0] for t in targets) / len(targets)
    ty = sum(t[1] for t in targets) / len(targets)
    L0 = "B" if layers == "B" else "F"
    pq, best, prev = [], {}, {}
    for (i, j) in start:
        st = (i, j, "F")
        if not via_start:
            best[st] = 0.0
            heapq.heappush(pq, (0.0, st))
        if L0 == "B":   # a THT pad: start on L4 too
            st = (i, j, "B")
            best[st] = 0.0
            heapq.heappush(pq, (0.0, st))
    goal = None
    nb = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142),
          (-1, -1, 1.4142)]
    sset = set(start)
    n_exp = 0
    while pq:
        c, st = heapq.heappop(pq)
        if c > best.get(st, 1e18) + 1e-9:
            continue
        i, j, L = st
        n_exp += 1
        if n_exp > 2000000:
            break
        if (i, j) in targets and (i, j) not in sset:
            goal = st
            break
        for di, dj, dc in nb:
            a, b = i + di, j + dj
            if not (0 <= a < nx and 0 <= b < ny):
                continue
            if (a, b) not in sset and not free(a, b, L):
                continue
            if L == "F" and (a, b) not in sset and (i, j) not in sset and not free(i, j, L):
                continue
            nst = (a, b, L)
            ncost = c + dc * grid
            if ncost < best.get(nst, 1e18):
                best[nst] = ncost
                prev[nst] = st
                heapq.heappush(pq, (ncost, nst))
        if len(layers) == 2 and (i, j) not in sset:
            x, y = x0 + i * grid, y0 + j * grid
            other = "B" if L == "F" else "F"
            if free(i, j, other) and pv.legal_via(x, y, net, R, sp, ctx[0], ctx[1], ctx[2], ref, ctx[3]) is not None:
                nst = (i, j, other)
                ncost = c + VIA_COST
                if ncost < best.get(nst, 1e18):
                    best[nst] = ncost
                    prev[nst] = st
                    heapq.heappush(pq, (ncost, nst))
    if goal is None:
        return None, "no path (%d expansions)" % n_exp
    path = [goal]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    # to board items: segments per layer run, vias at layer changes and at the end
    items, shapes = [], []
    run = [path[0]]
    vias = []

    first = [True]

    def flush(run):
        pts = simplify([(x0 + p[0] * grid, y0 + p[1] * grid) for p in run])
        if via_start and first[0]:
            pts = [(sx, sy)] + pts          # start exactly on the inner via centre
        first[0] = False
        if len(pts) >= 2:
            items.extend(rl.add_track(board, net, run[0][2], pts, w))
            for a, b in zip(pts[:-1], pts[1:]):
                shapes.append(rl.Shape("seg", [run[0][2]], net, clr, "track", a=a, b=b, r=w / 2))
    for p in path[1:]:
        if p[2] != run[-1][2]:
            flush(run)
            vias.append((x0 + p[0] * grid, y0 + p[1] * grid))
            run = [p]
        else:
            run.append(p)
    flush(run)
    gx, gy = x0 + goal[0] * grid, y0 + goal[1] * grid
    if (goal[0], goal[1]) not in touch:
        vias.append((gx, gy))
    for vx, vy in vias:
        items.append(rl.add_via(board, net, vx, vy))
        shapes.append(rl.Shape("circle", rl.LAYERS, net, clr, "via", a=(vx, vy), r=rl.VIA_D / 2))
    for s in shapes:
        sp.add(s)
    length = sum(math.hypot(path[k + 1][0] - path[k][0], path[k + 1][1] - path[k][1]) * grid
                 for k in range(len(path) - 1) if path[k][2] == path[k + 1][2])
    return items, "%s.%s %s: %.1f mm, %d via(s), layers %s" % (ref, num, net, length, len(vias),
                                                               "".join(sorted({p[2] for p in path})))


def hard_conflict(t, d=0.0, x=None, y=None):
    """For these short power links the trial corridors of the non-pair critical nets and the gate-lane exits are
    passable (L4 routes those around); diff-pair and crystal corridors stay hard, except inside the D-107 breakout
    boxes, where a pair keeps the class clearance 0.15 mm (+ 0.06 grid tolerance) to other nets."""
    if t.tag == "lane-exit-far":
        return False
    if t.tag == "lane-exit":
        return True           # D-110: the first 1.6 mm of every gate-lane exit stays free of power links too
    if t.tag in ("trial", "trialvia"):
        cls = _R[t.net][0]
        if cls not in ("ETH_DIFF", "USB_DIFF", "XTAL"):
            return False
        if cls != "XTAL" and x is not None and any(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for bb in _BOXES):
            return d < 0.21
        return True
    return True


def simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) < 1e-9:
                out[-1] = p
                continue
        out.append(p)
    return out


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, "L3_POWERLINKS")
    set_sw(board)
    R = rl.rules()
    sp = rl.board_space(board, R)
    rl.trial_reserve(sp, R)
    pv.lane_exits(board, sp, R)
    zn = bl.zones()
    holes = [(z["origin_x"], z["origin_y"]) for z in zn.values() if z["kind"] == "hole"]
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    thth = []
    allpads = []
    for ref, fp in fps.items():
        for p in fp.Pads():
            allpads.append((ref, p, bl.pad_polygon(p)))
            if p.GetDrillSize().x > 0:
                x, y = bl.to_board(p.GetPosition())
                thth.append((x, y, pcbnew.ToMM(p.GetDrillSize().x) / 2))
    courts = {}
    for ref, fp in fps.items():
        if ref.startswith(pv.NO_VIA_PREFIX) and not ref.startswith("JP"):
            bb = bl.courtyard_bbox(fp)
            if bb:
                courts[ref] = bb
    ctx = (holes, thth, courts, allpads)
    pv.set_boxes(board)
    for ref, m in BREAKOUT_PAD.items():
        bb = bl.courtyard_bbox(fps[ref])
        _BOXES.append((bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m))
    all_items, fails = [], []
    own_via = set()
    import csv
    with open(pv.OUT_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["status"] == "near":
                own_via.add((r["ref"], r["pad"]))
    for link in LINKS:
        ref, num, w, layers, grid = link[:5]
        box = link[5] if len(link) > 5 else None
        if (ref, num) in own_via and (ref, num) not in VIA_START:
            print("  %s.%s: has its own plane via <= 0.5 mm (route_planevias.py), no link" % (ref, num))
            continue
        items, msg = route(board, sp, R, ref, num, w, layers, grid, (holes, thth, courts, allpads), box)
        if items:
            print("  " + msg)
            all_items += items
            continue
        pad = [q for q in fps[ref].Pads() if q.GetNumber() == num][0]
        if pad.GetNetname() == "GND":
            # no room for a via or a track: the pad joins the L1 GND pour solidly (no thermal spokes), which is
            # stitched to L2 by the GND vias around it (D-109 e)
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            print("  %s.%s GND: %s -> solid connection to the L1 GND pour" % (ref, num, msg))
        else:
            print("  FAILED %s.%s: %s" % (ref, num, msg))
            fails.append("%s.%s" % (ref, num))
    rl.group(board, "L3_POWERLINKS", all_items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    print("power links: %d failed of %d" % (len(fails), len(LINKS)))
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
