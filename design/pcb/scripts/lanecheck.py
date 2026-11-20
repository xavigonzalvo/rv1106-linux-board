#!/usr/bin/env python3
"""Lane-escape check (verifier L3 r1/r2 blocker, D-110): can every open U9 gate lane leave the SoC on L1?

    $PY design/pcb/scripts/lanecheck.py [board]        # prints one line per lane; exit 1 if any lane is trapped

Each U9 lane of escape_plan.csv (LANE / PAIR2 roles) ends, after route_escape.py, at its gate point (r 8.00 mm from the
U9 centre). From that end the check searches a path on L1 (F.Cu) on a 0.05 mm grid:
  * the lane is a track of its class width (netclasses.csv; diff-pair lines at their class width);
  * every copper item of another net on F.Cu (pads of every part, tracks, vias) is an obstacle at the larger of the two
    class clearances (the lane's and the obstacle's: "max-of-classes"), i.e. a cell is blocked if its distance to the
    item is < w/2 + max(c_lane, c_item);
  * the U9 fan square (|dx|, |dy| < 7.90 mm, the DRU neck-down area) is closed: lanes leave outward only; a disc of
    0.15 mm around the lane end is open (the end itself sits 0.10 mm outside the fan, at the neck-down spacing);
  * the target is any cell at r >= 11.5 mm from the U9 centre (outside the ring-1/ring-2 parts) or a pad of the lane's
    own net (not U9).
Two results per lane:
  (1) "free": the lane alone can leave (BFS on the board as it is);
  (2) "capacity": the lanes are routed one after the other (greedy, shortest grid path), each routed path then blocks
      the following lanes at w/2 + max clearance. This catches gaps between ring-1 parts that are open for one lane but
      too narrow for all the lanes that must use them. Two orders are tried (shortest-first, then the failed lanes
      first); the better one is reported. A capacity failure in both orders is a FAIL.
Board coordinates are mm from the board NW corner (boardlib).
"""
import collections
import csv
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402
import routelib as rl  # noqa: E402

GATE_OUT = 10.3     # the DRU neck-down (0.10/0.10) holds for a track segment that touches the U9_FAN area: a lane run
#                    straight from the fan through the ring-1 row (outer cap pads at r <= 10.2) keeps it (D-110)
NECK = (0.05, 0.10)  # half width, clearance of the DRU "QFN-128 escape neck-down" rule
STEP = 0.05
X0, Y0, X1, Y1 = 17.0, 19.0, 52.0, 54.0
R_OUT = 11.5
FAN = 7.90
START_FREE = 0.15
CUT = 0.50          # largest w/2 + clearance used (0.13 + 0.30) plus margin


class Grid:
    def __init__(self):
        self.nx = int(round((X1 - X0) / STEP)) + 1
        self.ny = int(round((Y1 - Y0) / STEP)) + 1
        n = self.nx * self.ny
        # two independent "best with distinct nets" fields: D1 = distance, D2 = distance - item clearance
        self.a_d, self.a_n, self.a_d2 = [9.0] * n, [None] * n, [9.0] * n
        self.c_d, self.c_n, self.c_d2 = [9.0] * n, [None] * n, [9.0] * n

    def idx(self, x, y):
        i = int(round((x - X0) / STEP))
        j = int(round((y - Y0) / STEP))
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return j * self.nx + i
        return None

    def xy(self, k):
        return X0 + (k % self.nx) * STEP, Y0 + (k // self.nx) * STEP

    def _put(self, k, d, net, dc):
        # field A: plain distance
        if net == self.a_n[k]:
            if d < self.a_d[k]:
                self.a_d[k] = d
        elif d < self.a_d[k]:
            self.a_d2[k], self.a_d[k], self.a_n[k] = self.a_d[k], d, net
        elif d < self.a_d2[k]:
            self.a_d2[k] = d
        # field C: distance minus the item's clearance
        if net == self.c_n[k]:
            if dc < self.c_d[k]:
                self.c_d[k] = dc
        elif dc < self.c_d[k]:
            self.c_d2[k], self.c_d[k], self.c_n[k] = self.c_d[k], dc, net
        elif dc < self.c_d2[k]:
            self.c_d2[k] = dc

    def add(self, bbox, dist, net, clr):
        """bbox of the item, dist(x, y) -> distance to the item copper (0 inside)."""
        i0 = max(0, int((bbox[0] - CUT - X0) / STEP))
        i1 = min(self.nx - 1, int((bbox[2] + CUT - X0) / STEP) + 1)
        j0 = max(0, int((bbox[1] - CUT - Y0) / STEP))
        j1 = min(self.ny - 1, int((bbox[3] + CUT - Y0) / STEP) + 1)
        for j in range(j0, j1 + 1):
            y = Y0 + j * STEP
            base = j * self.nx
            for i in range(i0, i1 + 1):
                x = X0 + i * STEP
                d = dist(x, y)
                if d < CUT:
                    self._put(base + i, d, net, d - clr)

    def blocked(self, k, net, half, clr):
        da = self.a_d2[k] if self.a_n[k] == net else self.a_d[k]
        if half == NECK[0] and clr == NECK[1]:
            return da < half + clr - 1e-9          # DRU neck-down: 0.10 to everything (the rule matches A = track)
        dc = self.c_d2[k] if self.c_n[k] == net else self.c_d[k]
        return da < half + clr - 1e-9 or dc < half - 1e-9


def lanes_of(board, R):
    """Open lane ends: (pin, net, side, (x, y)) for every LANE/PAIR2 pin whose F.Cu track ends at r 8.00."""
    import pcbnew
    with open(os.path.join(bl.PCB_DIR, "escape_plan.csv"), newline="", encoding="utf-8") as fh:
        plan = {int(r["pin"]): r for r in csv.DictReader(fh)}
    u9 = board.FindFootprintByReference("U9")
    pinnet = {int(p.GetNumber()): p.GetNetname() for p in u9.Pads() if p.GetNumber() not in ("", "129")}
    ends = collections.defaultdict(list)
    # D-111 (L4): a lane whose net already has L4 copper (board group L4_CRITICAL) is routed, not open any more;
    # D-113 (L5): the same for a lane with its L5 exit stub through the ring-1 row (group L5_LANES)
    l4nets = set()
    for g in board.Groups():
        # round 4: lanes routed by l5_finish.py; L5G round 2 (D-128): the SD lanes re-drawn by l5g_fix.py (group
        # L5G_FIX) from the pin row down are routed too (their L4_CRITICAL pieces were replaced)
        if g.GetName() in ("L4_CRITICAL", "L5_LANES", "L5_FINISH", "L5G_FIX"):
            for it in g.GetItems():
                try:
                    l4nets.add(it.GetNetname())
                except AttributeError:
                    pass
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetLayer() != pcbnew.F_Cu:
            continue
        for e in (bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())):
            ends[t.GetNetname()].append(e)
    out = []
    for pin, r in sorted(plan.items()):
        if r["role"] not in ("LANE", "PAIR2") or not pinnet.get(pin):
            continue
        net, side = pinnet[pin], esc.side_of(pin)
        if net in l4nets:
            continue
        cand = [e for e in ends[net] if abs(esc.radial(side, *e) - 8.0) < 0.02]
        out.append((pin, net, side, cand[0] if cand else None))
    return out


def build(board, R):
    import pcbnew
    g = Grid()
    win = (X0 - 1, Y0 - 1, X1 + 1, Y1 + 1)

    def inwin(bb):
        return not (bb[2] < win[0] or bb[0] > win[2] or bb[3] < win[1] or bb[1] > win[3])

    def clr_of(net):
        return R[net][2] if net in R else 0.15
    own_pads = collections.defaultdict(list)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            if not p.IsOnLayer(pcbnew.F_Cu):
                continue
            poly = bl.pad_polygon(p)
            xs, ys = [q[0] for q in poly], [q[1] for q in poly]
            bb = (min(xs), min(ys), max(xs), max(ys))
            if not inwin(bb):
                continue
            net = p.GetNetname() or ("#NC%s.%s" % (ref, p.GetNumber()))
            if ref != "U9" and p.GetNetname():
                own_pads[net].append(poly)
            g.add(bb, lambda x, y, poly=poly: 0.0 if rl.inside(x, y, poly) else rl.pt_poly((x, y), poly), net,
                  clr_of(net))
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            x, y = bl.to_board(t.GetPosition())
            r = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            bb = (x - r, y - r, x + r, y + r)
            if inwin(bb):
                g.add(bb, lambda px, py, x=x, y=y, r=r: max(0.0, math.hypot(px - x, py - y) - r), net, clr_of(net))
            continue
        if t.GetLayer() != pcbnew.F_Cu:
            continue
        a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
        h = pcbnew.ToMM(t.GetWidth()) / 2
        bb = (min(a[0], b[0]) - h, min(a[1], b[1]) - h, max(a[0], b[0]) + h, max(a[1], b[1]) + h)
        if inwin(bb):
            g.add(bb, lambda px, py, a=a, b=b, h=h: max(0.0, rl.pt_seg(px, py, a[0], a[1], b[0], b[1]) - h), net,
                  clr_of(net))
    return g, own_pads


def in_fan(x, y):
    return abs(x - esc.CENTRE[0]) < FAN and abs(y - esc.CENTRE[1]) < FAN


def in_gate(x, y):
    return max(abs(x - esc.CENTRE[0]), abs(y - esc.CENTRE[1])) <= GATE_OUT


MODE = {"neck": True}


def search(g, net, end, half, clr, own_polys, extra=None, side=None):
    """Shortest path (8-neighbour Dijkstra) from the lane end; returns the cell path or None. A step costs its length,
    plus TANG x its tangential part when `side` is given (lanes prefer to run straight out, as an escape route does,
    so that the capacity pass does not let one lane wander across the gaps the others need). extra: cells near lanes
    routed before (capacity pass), {cell: (net, None, distance to that lane's copper)}."""
    import heapq
    s = g.idx(*end)
    cx, cy = esc.CENTRE
    targets = set()
    for poly in own_polys:
        xs, ys = [q[0] for q in poly], [q[1] for q in poly]
        for k in cells_in((min(xs), min(ys), max(xs), max(ys)), g):
            if rl.inside(*g.xy(k), poly):
                targets.add(k)
    radial_x = side in ("E", "W")
    via_ok = VIA_EXIT and rl.rules()[net][0] in VIA_CLASSES
    best = {s: 0.0}
    prev = {s: -1}
    pq = [(0.0, s)]
    nx = g.nx
    goal_via = {}
    while pq:
        c0, k = heapq.heappop(pq)
        if k < 0:                       # a via exit popped: it was the cheapest way out
            k = goal_via[k]
            path = []
            while k != -1:
                path.append(k)
                k = prev[k]
            return path[::-1]
        if c0 > best.get(k, 1e18) + 1e-12:
            continue
        x, y = g.xy(k)
        if math.hypot(x - cx, y - cy) >= R_OUT or k in targets:
            path = []
            while k != -1:
                path.append(k)
                k = prev[k]
            return path[::-1]
        if via_ok and math.hypot(x - cx, y - cy) >= VIA_R_MIN and not in_gate(x, y) and via_site(g, k, net, extra):
            gid = -1 - len(goal_via)
            goal_via[gid] = k
            heapq.heappush(pq, (c0 + VIA_PEN, gid))
        i, j = k % nx, k // nx
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ii, jj = i + di, j + dj
            if not (0 <= ii < nx and 0 <= jj < g.ny):
                continue
            q = jj * nx + ii
            step = 1.4142 if di and dj else 1.0
            if side:
                tang = abs(dj) if radial_x else abs(di)
                step += MODE.get("tang", TANG) * tang
            nc = c0 + step
            if nc >= best.get(q, 1e18):
                continue
            qx, qy = g.xy(q)
            near_start = math.hypot(qx - end[0], qy - end[1]) <= START_FREE
            if not near_start:
                h, c = (NECK if MODE["neck"] and in_gate(qx, qy) else (half, clr))
                if in_fan(qx, qy) or g.blocked(q, net, h, c):
                    continue
                if extra and q in extra and extra[q][0] != net and extra[q][2] < h + c - 1e-9:
                    continue
            best[q] = nc
            prev[q] = k
            heapq.heappush(pq, (nc, q))
    return None


# A DEFAULT/SENSE lane (layout.md §2.3: L4 carries DEFAULT and the DC sense nets) may also leave by a via to L4 once
# it is past the ring-1 gate band: a cell where a 0.5 mm via fits (0.25 + 0.20 mm from every other copper, 0.25 +
# 0.25 mm from routed lanes) counts as an exit. XTAL, ETH, USB, FSPI and SDMMC lanes must reach r 11.5 on L1.
VIA_CLASSES = ("DEFAULT", "SENSE")
VIA_EXIT = True
VIA_PEN = 60.0       # a via exit costs as much as 3 mm of track (grid steps of 0.05 mm): L1 first
VIA_R_MIN = 10.3     # and only past the ring-1 row, not in the gap mouths


def via_site(g, k, net, extra):
    da = g.a_d2[k] if g.a_n[k] == net else g.a_d[k]
    dc = g.c_d2[k] if g.c_n[k] == net else g.c_d[k]
    if da < 0.25 + 0.20 + 0.05 or dc < 0.25 + 0.05:
        return False
    if extra and k in extra and extra[k][0] != net and extra[k][2] < 0.25 + 0.20:
        return False
    return True


TANG = 1.5
TANGS = (1.5, 3.0, 0.6)     # radial preference tried per side, in this order
TRIAL_TOL = 0.03
FIX_TRIAL = False
ROUNDS = 12
ORDERS = {}
LAST_PATHS = {}


def cells_in(bb, g):
    i0 = max(0, int((bb[0] - X0) / STEP))
    i1 = min(g.nx - 1, int((bb[2] - X0) / STEP) + 1)
    j0 = max(0, int((bb[1] - Y0) / STEP))
    j1 = min(g.ny - 1, int((bb[3] - Y0) / STEP) + 1)
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            yield j * g.nx + i


def stamp(g, extra, path, net, half, clr):
    """Mark the cells around a routed path: extra[cell] = (net, distance - routed track half width) for the capacity
    pass; the following lane is blocked if that distance < its half + max(clearances) (the routed lane's clearance is
    folded in by using the larger of the two classes: clr here)."""
    reach = max(half, 0.13) + 0.30 + 0.13 + 0.01
    n = int(reach / STEP) + 1
    for k in path:
        i, j = k % g.nx, k // g.nx
        for dj in range(-n, n + 1):
            for di in range(-n, n + 1):
                ii, jj = i + di, j + dj
                if not (0 <= ii < g.nx and 0 <= jj < g.ny):
                    continue
                q = jj * g.nx + ii
                qx, qy = g.xy(q)
                # the routed lane copper: neck-down width inside the gate band, class width outside
                hh = NECK[0] if MODE["neck"] and in_gate(*g.xy(k)) else half
                d = math.hypot(di, dj) * STEP - hh
                # a later lane is blocked if d < its half + max(its clearance, this lane's): fold this lane's clearance
                # excess over the later lane's in by storing d - max(0, clr_routed - 0.10) in the gate band, where the
                # neck rule makes every clearance 0.10, and d - max(0, clr - 0.15) outside
                dd = d - (0.0 if hh == NECK[0] else max(0.0, clr - 0.15))
                if q not in extra or extra[q][2] > dd:
                    extra[q] = (net, None, dd)


def lane_params(net, R):
    cls, w, c = R[net]
    return cls, w / 2, max(c, 0.15)


def run(board, verbose=False, neck=True):
    """Returns (rows, n_free_fail, n_cap_fail); rows: (pin, net, cls, end, free_ok, cap_ok, note).
    neck=True: DRC-legal model (the DRU neck-down 0.10/0.10 applies inside the ring-1 gate band, r <= 9.45, for a lane
    whose segment starts in the U9_FAN area); neck=False: class width/clearance from the gate end on (strict)."""
    MODE["neck"] = neck
    R = rl.rules()
    lanes = lanes_of(board, R)
    g, own = build(board, R)
    rows = {}
    free = {}
    for pin, net, side, end in lanes:
        if end is None:
            rows[pin] = [pin, net, R[net][0], None, False, False, "no open lane end at r 8.00"]
            continue
        cls, half, clr = lane_params(net, R)
        p = search(g, net, end, half, clr, own.get(net, []))
        free[pin] = p
        rows[pin] = [pin, net, cls, end, p is not None, False, "" if p else "trapped (no L1 path out)"]

    paths = {}

    def greedy(order):
        extra, ok = {}, {}
        paths.clear()
        for pin, net, side, end in order:          # the trial corridors first, as fixed lanes
            if pin in fixed:
                cells, bad = fixed[pin]
                ok[pin] = bad is None
                cls, half, clr = lane_params(net, R)
                stamp(g, extra, cells, net, half, clr)
                paths[pin] = [g.xy(k) for k in cells]
        for pin, net, side, end in order:
            if pin in fixed:
                continue
            if end is None or free.get(pin) is None:
                ok[pin] = False
                continue
            cls, half, clr = lane_params(net, R)
            p = search(g, net, end, half, clr, own.get(net, []), extra, side)
            ok[pin] = p is not None
            if p:
                stamp(g, extra, p, net, half, clr)
                ex, ey = g.xy(p[-1])
                if math.hypot(ex - esc.CENTRE[0], ey - esc.CENTRE[1]) < R_OUT:
                    stamp(g, extra, p[-1:], net, 0.25, clr)        # the exit via
                paths[pin] = [g.xy(k) for k in p]
        return ok
    # order: per side from both corners towards the middle is how an escape is drawn; start with the lanes whose
    # free path is shortest, then up to ROUNDS reorders with the failed lanes first (rip-up and retry)
    # lanes of the critical nets follow their approved trial corridor (D-107/D-108, D-H5): its L1 part from the gate
    # to r 11.5 must still be clear of the board copper (class width and clearance, the DRU neck-down in the gate band,
    # TRIAL_TOL for the trial's 0.05 mm grid); it is then fixed and blocks the other lanes
    fixed = {}
    with open(rl.TRIAL_RESULT, encoding="utf-8") as fh:
        trial = json.load(fh)["nets"]
    cx, cy = esc.CENTRE
    for pin, net, side, end in (lanes if FIX_TRIAL else []):
        if net not in trial or end is None or free.get(pin) is None:
            continue
        runs = [pts for lay, pts in trial[net]["segs"] if lay == 0]
        run0 = min(runs, key=lambda pts: math.hypot(pts[0][0] - end[0], pts[0][1] - end[1])) if runs else None
        if not run0 or math.hypot(run0[0][0] - end[0], run0[0][1] - end[1]) > 0.3:
            continue
        cls, half, clr = lane_params(net, R)
        cells, bad = [], None
        for (ax, ay), (bx, by) in zip(run0[:-1], run0[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) / 0.025))
            for i in range(n + 1):
                x, y = ax + (bx - ax) * i / n, ay + (by - ay) * i / n
                if math.hypot(x - cx, y - cy) >= R_OUT:
                    break
                k = g.idx(x, y)
                if not cells or cells[-1] != k:
                    cells.append(k)
                if math.hypot(x - end[0], y - end[1]) <= START_FREE or in_fan(x, y):
                    continue
                h, c = (NECK if MODE["neck"] and in_gate(x, y) else (half, clr))
                if bad is None and g.blocked(k, net, h, max(0.0, c - TRIAL_TOL)):
                    bad = (x, y)
            else:
                continue
            break
        fixed[pin] = (cells, bad)
        if bad:
            rows[pin][4] = False
            rows[pin][6] = "trial corridor blocked at (%.2f, %.2f)" % bad

    def tkey(l):
        return esc.t_of(l[2], *l[3]) if l[3] else 0.0
    # the capacity pass runs per side (the four lane fans meet only at the corners, where no lane turns back): for
    # each side a few deterministic orders (t ascending / descending, both ends inward, shortest free path first),
    # then rip-up rounds with the failed lanes first; the best order of each side is kept
    best = {}
    for sd in "SENW":
        ls = [l for l in lanes if l[2] == sd]
        asc = sorted(ls, key=tkey)
        inward = [x for pair in zip(asc, asc[::-1]) for x in pair][:len(asc)]
        seen = []
        for x in inward:
            if x not in seen:
                seen.append(x)
        orders = [asc, asc[::-1], seen, sorted(ls, key=lambda l: len(free.get(l[0]) or []))]
        side_best = None
        for tang, _round in [(tg, rd) for tg in TANGS for rd in range(ROUNDS)]:
            if side_best is not None and all(side_best.values()):
                break
            if _round == 0:
                order = orders[0]
                rng = random.Random(1106)    # fixed seed: the check is reproducible
            MODE["tang"] = tang
            if _round < len(orders):
                order = orders[_round]
            elif _round % 2 == 0:
                order = order[:]
                rng.shuffle(order)
            ok = greedy(order)
            if side_best is None or sum(ok.values()) > sum(side_best.values()):
                side_best = ok
                LAST_PATHS[sd] = dict(paths)
                ORDERS[sd] = (tang, [l[0] for l in order])
            order = [l for l in order if not ok[l[0]]] + [l for l in order if ok[l[0]]]
        best.update(side_best or {})
    for pin in rows:
        rows[pin][5] = best.get(pin, False)
        if rows[pin][4] and not rows[pin][5]:
            rows[pin][6] = "free alone, blocked by the other lanes (gap capacity)"
    out = [tuple(rows[p]) for p in sorted(rows)]
    return out, sum(1 for r in out if not r[4]), sum(1 for r in out if not r[5])


CUT_R = [8.3 + 0.1 * i for i in range(18)]      # radial lines r 8.3 .. 10.0 (the ring-1 row and just past it)


def cut_capacity(board=None, g=None, lanes=None, R=None):
    """Per-side cut check of the gate capacity (deterministic; verifier L3 r2 "per-gap capacity check"). On each
    radial line r = 8.3 .. 10.0 mm in front of a side (t over the side's 90 deg sector, tc +- r), the free stretches
    for a lane centre are measured on the board (DRU neck-down 0.10/0.10 inside the gate band r <= 9.45, DEFAULT
    0.15/0.15 beyond, against every copper item at the larger clearance); a stretch of length L holds floor(L / p) + 1
    lane centres at the pitch p (0.20 neck-down, 0.30 DEFAULT). The lanes that must cross the line (the side's lanes,
    less those whose own pad lies inside r) need sum of their pitches (class width + max(class clearance, 0.15); 0.20
    in the band); the stretches offer sum of (count x 0.30 or 0.20) pitch. Lanes only pass the row between the parts,
    so if need > offer on any line the side cannot escape on L1 (a necessary condition; the greedy pass of run() is
    the constructive one). Returns rows (side, r, n_lanes, need_mm, offer_mm, ok)."""
    if g is None:
        R = rl.rules()
        lanes = lanes_of(board, R)
        g, _own = build(board, R)
    out = []
    own_r = {}
    for fp in board.GetFootprints() if board else []:
        if fp.GetReference() == "U9":
            continue
        for p in fp.Pads():
            n = p.GetNetname()
            if n:
                x, y = bl.to_board(p.GetPosition())
                own_r.setdefault(n, []).append((x, y))
    for side in "SENW":
        ls = [l for l in lanes if l[2] == side and l[3]]
        tc = esc.t_of(side, *esc.CENTRE)
        for r in CUT_R:
            neck = MODE["neck"] and r <= GATE_OUT
            w, c = (0.10, 0.10) if neck else (0.15, 0.15)
            pitch0 = w + c
            runs, cur = [], 0.0
            t = tc - r
            while t <= tc + r + 1e-9:
                x, y = esc.point(side, t, r)
                k = g.idx(x, y)
                free = k is not None and not g.blocked(k, "#probe", w / 2, c)
                if free:
                    cur += 0.025
                elif cur > 0:
                    runs.append(cur)
                    cur = 0.0
                t += 0.025
            if cur > 0:
                runs.append(cur)
            offer = sum((int(L / pitch0 + 1e-9) + 1) * pitch0 for L in runs if L > 0)
            need, n = 0.0, 0
            for pin, net, sd, end in ls:
                pads = own_r.get(net, [])
                if any(esc.radial(side, *q) < r and abs(esc.t_of(side, *q) - tc) < r for q in pads):
                    continue
                cls, half, clr = lane_params(net, R or rl.rules())
                need += pitch0 if neck else 2 * half + max(clr, 0.15)
                n += 1
            out.append((side, round(r, 2), n, round(need, 3), round(offer, 3), need <= offer + 1e-9))
    return out


def main():
    import pcbnew
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    board = pcbnew.LoadBoard(args[0] if args else bl.BOARD_FILE)
    rows, nf, nc = run(board, neck="--strict" not in sys.argv)
    cut = cut_capacity(board)
    for side, r, n, need, offer, ok in cut:
        if not ok or "--cut" in sys.argv:
            print("%s cut side %s r %.1f: %d lanes need %.2f mm, free %.2f mm" % ("OK  " if ok else "FAIL", side, r, n,
                                                                                 need, offer))
    for a in sys.argv:
        if a.startswith("--dump="):
            import json
            with open(a[7:], "w") as fh:
                json.dump({str(k): v for k, v in LAST_PATHS.items()}, fh)
    for pin, net, cls, end, f, c, note in rows:
        print("%-4s U9.%-3d %-16s %-9s %s %s" % ("OK" if f and c else "FAIL", pin, net, cls,
              "(%.2f, %.2f)" % end if end else "-", note))
    print("lanecheck: %d lanes, %d trapped alone, %d not routable together (capacity)" % (len(rows), nf, nc))
    sys.exit(1 if nf or nc else 0)


if __name__ == "__main__":
    main()
