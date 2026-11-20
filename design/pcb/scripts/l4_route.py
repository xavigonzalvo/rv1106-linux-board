#!/usr/bin/env python3
"""Layout phase L4: critical routing (design/.venv; numpy/scipy).

    design/.venv/bin/python -I design/pcb/scripts/l4_route.py [geo.json] [out.json]
      default in : design/pcb/l4/board_geo.json   (l4_export.py, KiCad's Python, from the saved board)
      default out: design/pcb/l4/routes.json      (l4_write.py writes it into the board, group L4_CRITICAL)

Order (kicad-guide.md step 7, layout.md §4): crystals (§4.3), Ethernet pairs (§4.2), USB pairs (§4.6), SDMMC and FSPI
(§4.4), buck loops and feedback (§4.5), power paths, the SENSE nets that leave on L4 (D-104 e). Every net is routed by
l4lib (grid search + exact octilinear pulling); the JOBS table below fixes widths, layers, via permission, waypoints
and the order, so the run is deterministic and re-runnable. Pairs are routed as an envelope along a centre line and
offset into P/N at the class gap.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import l4lib as L  # noqa: E402
import pathlen  # noqa: E402

PCB = os.path.normpath(os.path.join(HERE, ".."))
GEO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PCB, "l4", "board_geo.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PCB, "l4", "routes.json")

geo = json.load(open(GEO))
S = L.Store(geo)
PADS = {(p["ref"], p["num"]): p for p in S.pads}
ROUTES = {}          # net -> {"tracks": [(layer, pts, w)], "vias": [(x, y)]}
LOG = []
FAILS = []
GRID_NOVIA = []      # rectangles where no via of L4 may go (filled below)
ETH_SPLIT = {}
HOPS = []
STITCH_OK_AREAS = []  # no-via areas a GND stitching via may still use (U1 / J1 / U11 courtyards: tented, under the body)
STITCH = []          # GND stitching vias placed next to signal vias


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def width(net):
    return S.cls[net][1]


def lane_end(net, k=0):
    e = geo["ends"][net][k]
    x, y, lay, w, dx, dy, ln = e
    # inward normal of the gate side: the side the end lies on (|x-34.5| or |y-36.5| = 8)
    if abs(abs(x - 34.5) - 8) < 0.01:
        nx, ny = (1 if x < 34.5 else -1), 0
    else:
        nx, ny = 0, (1 if y < 36.5 else -1)
    cos = abs(dx * nx + dy * ny) or 1.0
    back = min(ln * 0.95, 0.125 / cos)
    eb = (x - dx * back, y - dy * back)
    return dict(kind="end", x=x, y=y, back=eb, out=(-nx, -ny), w=w)


def fixed(net, layer, pts, w=None, own=()):
    """a hand-placed polyline (exactly checked) - used where the grid cannot see a legal neck-down exit"""
    w = w or width(net)
    for a, b in zip(pts, pts[1:]):
        bad = S.check_seg(net, L.F if layer == "F" else L.B, a, b, w / 2, own, report=True)
        if bad:
            log("  FAIL %s: fixed segment %s-%s: %s" % (net, a, b, bad[:3]))
            FAILS.append((net, ["fixed"]))
            return False
    add_route(net, layer, pts, w)
    return True


def route_pair(P, N, cs, ce, layer="F", via_ends=False, margin=3.0, win=None, cost_fn=None, forbid=(), first=None, neck=None,
               starts=None):
    """Route the coupled part of a diff pair: the centre line from cs to ce (points), envelope 2 w + gap, offset into
    P and N at the class gap. Returns {P: (first, last), N: (first, last)} line end points, P/N assigned so that P
    starts on the side of the lane/pad it comes from (caller passes P_side = +1 left / -1 right of the start
    direction via cs/ce order: P is the left line if pair_left[P])."""
    w = width(P)
    gap = pair_gap(P)
    hw = w + gap / 2
    lay = L.F if layer == "F" else L.B
    win = win or (min(cs[0], ce[0]) - margin, min(cs[1], ce[1]) - margin, max(cs[0], ce[0]) + margin,
                  max(cs[1], ce[1]) + margin)
    G = L.Grid(S, P, hw, win, lay, own=(P, N), relax=[], cost_fn=cost_fn, forbid=forbid)
    cs0 = None
    if first:          # fixed first piece out of the U9 gate at the fan width (checked in place_pair_lines)
        f = math.hypot(*first)
        cs0 = cs
        nl = neck or NECK_LEN
        cs = (cs[0] + first[0] / f * nl, cs[1] + first[1] / f * nl)
    src = [(lay,) + G.cell(*cs)]
    dst = [(lay,) + G.cell(*ce)]
    path = G.search(src, dst)
    if path is None:
        log("  FAIL pair %s/%s: no centre path" % (P, N))
        FAILS.append((P, ["pair centre"]))
        return None
    pts = [cs] + [G.xy(c[1], c[2]) for c in corners(path, G)][1:-1] + [ce]
    pts = dedup(pts)
    res = L.pull(S, P, hw, pts, lay, own=(P, N))
    if res is None:
        pts = [cs] + [G.xy(c[1], c[2]) for c in path][1:-1] + [ce]
        res = L.pull(S, P, hw, dedup(pts), lay, own=(P, N))
    if res is None:
        log("  FAIL pair %s/%s: centre not legal" % (P, N))
        FAILS.append((P, ["pair pull"]))
        return None
    while len(res) > 2 and math.hypot(res[-1][0] - res[-2][0], res[-1][1] - res[-2][1]) < 0.3:
        res.pop()             # drop a grid-snap stub at the end; the breakouts start at the last real corner
    if cs0 is not None:
        res = [cs0] + res
    PAIR_STARTS[id(res)] = starts
    return res


NECK_LEN = 0.40      # pair lines keep the fan width (0.15 mm) for this long from the U9 gate (DRU "pairs in the U9 fan")
FAN_W = 0.15
PAIR_STARTS = {}     # centre line -> (P start, N start): the lane back points the first (fan-width) piece starts from


def pair_gap(P):
    """class gap; + 2 um where the gap equals the netclass clearance (USB 0.150 mm), so nm rounding never makes the
    partner a clearance violation"""
    g = S.cls[P][3]
    return g + 0.002 if g <= S.cls[P][2] + 1e-9 else g


def p_left_for(P, centre, p_start):
    d = (width(P) + pair_gap(P)) / 2
    a = L.offset_line(centre, d)[0]
    b = L.offset_line(centre, -d)[0]
    return math.hypot(a[0] - p_start[0], a[1] - p_start[1]) < math.hypot(b[0] - p_start[0], b[1] - p_start[1])


def place_pair_lines(P, N, centre, p_left, layer="F"):
    """offset the centre line into the two lines (P on the left of the travel direction if p_left), exact-check and
    add them. Returns (Ppts, Npts) or None."""
    w = width(P)
    d = (w + pair_gap(P)) / 2
    lp = L.offset_line(centre, d if p_left else -d)
    ln = L.offset_line(centre, -d if p_left else d)
    st = PAIR_STARTS.get(id(centre))
    if st:
        lp[0], ln[0] = tuple(st[0]), tuple(st[1])
    lay = L.F if layer == "F" else L.B
    for net, pts in ((P, lp), (N, ln)):
        for a, b in zip(pts, pts[1:]):
            ww = FAN_W if L.seg_intersects_rect(a, b, L.FAN) else w
            bad = S.check_seg(net, lay, a, b, ww / 2, own=(P, N), report=True)
            if bad:
                log("  FAIL pair line %s %s-%s: %s" % (net, a, b, bad[:3]))
                FAILS.append((net, ["pair line"]))
                return None
    # P against N (the partner was excluded above): >= 0.10 where a fan piece is involved, else the class clearance
    def wid(a, b):
        return FAN_W if L.seg_intersects_rect(a, b, L.FAN) else w
    for a, b in zip(lp, lp[1:]):
        for c, e in zip(ln, ln[1:]):
            dd = float(L.seg_seg_v(a, b, L.np.array([c]), L.np.array([e]))[0]) - wid(a, b) / 2 - wid(c, e) / 2
            fan = L.seg_intersects_rect(a, b, L.FAN) or L.seg_intersects_rect(c, e, L.FAN)
            need = 0.10 if fan else S.cls[P][2]
            if dd < need + L.EPS:
                log("  FAIL pair lines %s/%s too close (%.3f mm < %.2f) at %s" % (P, N, dd, need, a))
                FAILS.append((P, ["pair P-N"]))
                return None
    for net, pts in ((P, lp), (N, ln)):
        k = 0
        while k < len(pts) - 1 and L.seg_intersects_rect(pts[k], pts[k + 1], L.FAN):
            k += 1
        if k:
            add_route(net, layer, pts[:k + 1], FAN_W)
        if k < len(pts) - 1:
            add_route(net, layer, pts[k:], w)
    return lp, ln


def via_here(net, x, y, gnd=True, gnd_r=(0.6, 1.0)):
    """place a signal via (exact check) and, if gnd, a GND stitching via within gnd_r of it (layout.md §4.6/§2.3)"""
    if not S.check_via(net, x, y, novia=GRID_NOVIA):
        log("  FAIL %s: via (%.3f, %.3f) not legal" % (net, x, y))
        FAILS.append((net, ["via %.2f,%.2f" % (x, y)]))
        return False
    add_via(net, x, y)
    if gnd:
        HOPS.append((net, x, y, gnd_r))       # GND stitching via placed after the routing (stitch_hops)
    return True


def stitch_hops():
    """one GND via next to every signal via of the critical nets (USB: within 1 mm, layout.md §4.6 / task; ETH and
    others: same radius, well inside the 200 mil of layout.md §2.3), placed after all routes so it blocks nothing"""
    log("== GND stitching next to the signal vias")
    for net, x, y, rr in HOPS:
        # an existing GND via close enough counts
        near = [v for v in ROUTES.get("GND", {}).get("vias", []) if math.hypot(v[0] - x, v[1] - y) <= rr[1]]
        near += [(v["x"], v["y"]) for v in geo["vias"] if v["net"] == "GND" and math.hypot(v["x"] - x, v["y"] - y) <= rr[1]]
        if near:
            STITCH.append((net, x, y) + tuple(near[0]))
            continue
        gnd_stitch(x, y, rr, net)          # none within rr: recorded (D-112 j), the nearest GND via is measured


def crystal_guard_vias(need=4):
    """layout.md §4.3: the crystal GND guard is stitched to L2 with >= 4 vias - add GND vias round Y1 / Y2 (within
    1.5 mm of the courtyard) until there are `need` (D-112 l)"""
    log("== crystal guard stitching")
    for ref in ("Y1", "Y2"):
        c = S.court[ref]
        allg = [(v["x"], v["y"]) for v in geo["vias"] if v["net"] == "GND"] + \
            [tuple(v) for v in ROUTES.get("GND", {}).get("vias", [])]
        have = [q for q in allg if c[0] - 1.5 <= q[0] <= c[2] + 1.5 and c[1] - 1.5 <= q[1] <= c[3] + 1.5]
        k = 0
        cands = []
        for d in (0.6, 0.9, 1.2):
            x0, y0, x1, y1 = c[0] - d, c[1] - d, c[2] + d, c[3] + d
            n = 40
            for i in range(n):
                t = i / n
                cands += [(x0 + (x1 - x0) * t, y0), (x1, y0 + (y1 - y0) * t), (x1 - (x1 - x0) * t, y1),
                          (x0, y1 - (y1 - y0) * t)]
        nv = [q for q in GRID_NOVIA if q not in STITCH_OK_AREAS]
        for (x, y) in cands:
            if len(have) + k >= need:
                break
            if any(math.hypot(x - q[0], y - q[1]) < 1.2 for q in have):
                continue
            if S.check_via("GND", x, y, novia=nv):
                add_via("GND", round(x, 3), round(y, 3))
                have.append((x, y))
                log("  %s guard: GND via (%.2f, %.2f)" % (ref, x, y))
        log("  %s guard: %d GND vias within 1.5 mm" % (ref, len(have)))


def gnd_stitch(x, y, rr=(0.75, 1.0), tag=""):
    nv = [q for q in GRID_NOVIA if q not in STITCH_OK_AREAS]
    nr = int(round((rr[1] - rr[0]) / 0.05))
    for r in [rr[0] + (rr[1] - rr[0]) * i / max(1, nr) for i in range(nr + 1)]:
        for k in range(48):
            a = 2 * math.pi * k / 48
            gx, gy = x + r * math.cos(a), y + r * math.sin(a)
            if S.check_via("GND", gx, gy, novia=nv):
                add_via("GND", round(gx, 3), round(gy, 3))
                STITCH.append((tag, x, y, gx, gy))
                return (gx, gy)
    log("  NOTE no GND stitching via within %.2f mm of (%.2f, %.2f)" % (rr[1], x, y))
    STITCH.append((tag, x, y, None, None))
    return None


def lane_pt(x, y, out, gate):
    """a point on an existing own-net escape track inside U9_FAN (start of a neck-down exit), gate = (x, y) where the
    radial line leaves the fan band"""
    return dict(kind="end", x=gate[0], y=gate[1], back=(x, y), out=out, w=0.1)


def pad_term(ref, num):
    p = PADS[(ref, num)]
    x, y = ANCHOR.get((ref, num), (p["x"], p["y"]))
    return dict(kind="pad", ref=ref, num=num, x=x, y=y, poly=p["poly"], lay=p["lay"])


# pads whose track end must stay off the pad centre: JP1's bridge copper (no net) sits between its pads
ANCHOR = {("JP1", "1"): (64.62, 35.0)}


def add_route(net, layer, pts, w):
    R = ROUTES.setdefault(net, {"tracks": [], "vias": []})
    R["tracks"].append((layer, [list(p) for p in pts], w))
    for a, b in zip(pts, pts[1:]):
        S.add_track(net, L.F if layer == "F" else L.B, a, b, w / 2)


def add_via(net, x, y):
    R = ROUTES.setdefault(net, {"tracks": [], "vias": []})
    R["vias"].append((x, y))
    S.add_via(net, x, y, L.VIA_D / 2, L.VIA_DR / 2)


def term_cells(G, t, layers):
    """grid states of a terminal"""
    out = []
    if t["kind"] == "pad":
        xs = [q[0] for q in t["poly"]]
        ys = [q[1] for q in t["poly"]]
        for lay in (L.F, L.B):
            if not (t["lay"] & lay and layers & lay and lay in G.block):
                continue
            i0, j0 = G.cell(min(xs), min(ys))
            i1, j1 = G.cell(max(xs), max(ys))
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    x, y = G.xy(i, j)
                    if L.inside_poly(x, y, t["poly"]):
                        out.append((lay, i, j))
        if not out:
            i, j = G.cell(t["x"], t["y"])
            out.append((L.F, i, j))
    elif t["kind"] == "end":
        # the lane end at the gate (the radial exit strip starts here)
        i, j = G.cell(t["x"], t["y"])
        out.append((L.F, i, j))
    else:   # point
        i, j = G.cell(t["x"], t["y"])
        out.append((t.get("L", L.F), i, j))
    return out


def corners(path, G):
    """keep the cells where the direction or the layer changes"""
    pts = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c = path[k - 1], path[k], path[k + 1]
        if a[0] != b[0] or b[0] != c[0] or (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
            pts.append(b)
    pts.append(path[-1])
    return pts


def route_net(net, terms, layers=L.F, w=None, via_ok=False, margin=3.0, cost_fn=None, forbid=(), own=(),
              via_cost=3.0, novia=None, win=None, relax_extra=()):
    """Route a multi-terminal net (terminal order: the first is the root). Returns True on success."""
    w = w or width(net)
    hw = w / 2
    xs = [t["x"] for t in terms]
    ys = [t["y"] for t in terms]
    win = win or (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
    relax = list(relax_extra)
    for t in terms:
        if t["kind"] == "end":
            ox, oy = t["out"]
            x, y = t["x"], t["y"]
            x2, y2 = x + ox * 3.4, y + oy * 3.4
            relax.append((min(x, x2) - 0.013, min(y, y2) - 0.013, max(x, x2) + 0.013, max(y, y2) + 0.013))
    forbid = list(forbid) + [(L.B, tuple(S.court[r])) for r in ("Y1", "Y2")]    # layout.md §4.3: nothing on L4
    # layout.md §4.5: nothing on L4 under the SW nodes (D-112 g): SW_AREAS are blocked in the grid below and in the
    # pull check (never waived next to the net's own pads)
    ffree = [(t["x"] - 1.3, t["y"] - 1.3, t["x"] + 1.3, t["y"] + 1.3) for t in terms if t["kind"] == "pad"]
    G = L.Grid(S, net, hw, win, layers, own=own, via_ok=via_ok, novia=novia if novia is not None else GRID_NOVIA,
               relax=relax, cost_fn=cost_fn, forbid=forbid, forbid_free=ffree)
    if L.B in G.block:                    # SW nodes: closed on L4 even next to the net's own pads (D-112 g)
        for r in SW_AREAS:
            G.block[L.B] |= (G.X >= r[0] - hw - L.GM) & (G.X <= r[2] + hw + L.GM) & (G.Y >= r[1] - hw - L.GM) & \
                (G.Y <= r[3] + hw + L.GM)
    tree_cells = term_cells(G, terms[0], layers)
    tree_geo = []          # (layer, a, b) segments of this net already placed, for snapping tee points
    anchors = {}
    t0 = terms[0]
    anchors_t0 = (t0["back"] if t0["kind"] == "end" else (t0["x"], t0["y"]))
    for c in tree_cells:
        anchors[c] = anchors_t0
    ok = True
    rest = list(terms[1:])
    while rest:
        best = None
        for t in rest:
            dst = term_cells(G, t, layers)
            p = G.search(tree_cells, dst, via_cost=via_cost)
            if p is None:
                continue
            ln = len(p)
            if best is None or ln < best[0]:
                best = (ln, t, p)
        if best is None:
            log("  FAIL %s: no path to %s" % (net, ", ".join(term_name(t) for t in rest)))
            FAILS.append((net, [term_name(t) for t in rest]))
            ok = False
            break
        _, t, path = best
        rest.remove(t)
        # split into layer runs
        runs = []
        cur = [path[0]]
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                runs.append(cur)
                cur = [b]
            else:
                cur.append(b)
        runs.append(cur)
        start = anchors.get(path[0])
        if start is None:
            start = snap(tree_geo, G.xy(path[0][1], path[0][2]))
        end_anchor = t["back"] if t["kind"] == "end" else (t["x"], t["y"])
        vias = []
        for k, run in enumerate(runs):
            lay = run[0][0]
            cs = corners(run, G) if len(run) > 1 else run
            pts = [G.xy(c[1], c[2]) for c in cs]
            if k == 0:
                pts[0] = start
            else:
                pts[0] = vias[-1]
            if k == len(runs) - 1:
                if t["kind"] == "pad" and not (t["lay"] & lay):
                    pass
                else:
                    pts.append(end_anchor)
            else:
                vx, vy = G.xy(runs[k + 1][0][1], runs[k + 1][0][2])
                if not S.check_via(net, vx, vy, own=own, novia=GRID_NOVIA):
                    log("  note %s: via (%.3f, %.3f) fails the exact check" % (net, vx, vy))
                pts.append((vx, vy))
            pts = dedup(pts)
            lay_id = L.F if lay == L.F else L.B
            fr = [r for (m, r) in forbid if m & lay_id]

            def chk(a, b, lay_id=lay_id, fr=fr):
                if lay_id == L.B and any(L.seg_intersects_rect(a, b, r, hw - 0.02) for r in SW_AREAS):
                    return False          # never waived: nothing on L4 under a SW node (D-112 g)
                if any(L.seg_intersects_rect(a, b, r, hw) for r in fr) and not any(
                        L.seg_intersects_rect(a, b, q) and L.seg_intersects_rect(a, a, q) for q in ffree) and \
                        not any(L.seg_intersects_rect(b, b, q) for q in ffree):
                    return False
                return S.check_seg(net, lay_id, a, b, hw, own)
            res = L.pull(S, net, hw, pts, lay_id, own=own, check=chk) if len(pts) > 1 else pts
            if res is None:
                res = L.pull(S, net, hw, dedup([pts[0]] + [G.xy(c[1], c[2]) for c in run[1:-1]] + [pts[-1]]),
                             lay_id, own=own, check=chk)
            if res is None:
                log("  FAIL %s: pulled path not legal near %s" % (net, term_name(t)))
                FAILS.append((net, ["pull " + term_name(t)]))
                return False
            if len(res) > 1:
                add_route(net, "F" if lay == L.F else "B", res, w)
                for a, b in zip(res, res[1:]):
                    tree_geo.append((lay, a, b))
            if k < len(runs) - 1:
                add_via(net, *pts[-1])
                vias.append(pts[-1])
        # grow the tree: cells along the new geometry and the terminal
        for (lay, a, b) in tree_geo:
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / L.RES))
            for s in range(n + 1):
                x = a[0] + (b[0] - a[0]) * s / n
                y = a[1] + (b[1] - a[1]) * s / n
                c = (lay,) + G.cell(x, y)
                if c not in anchors:
                    anchors[c] = (x, y)
                    tree_cells.append(c)
        for c in term_cells(G, t, layers):
            if c not in anchors:
                anchors[c] = end_anchor
                tree_cells.append(c)
    return ok


def densify_pull(net, hw, run, G, pts, lay, own):
    """fallback: pull over every cell of the run (slower, finer)."""
    dense = [pts[0]] + [G.xy(c[1], c[2]) for c in run[1:-1]] + [pts[-1]]
    return L.pull(S, net, hw, dedup(dense), L.F if lay == L.F else L.B, own=own)


def dedup(pts):
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(tuple(p))
    return out


def snap(tree_geo, p):
    best = None
    for (lay, a, b) in tree_geo:
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + t * dx, a[1] + t * dy)
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if best is None or d < best[0]:
            best = (d, q)
    return best[1] if best else p


def term_name(t):
    if t["kind"] == "pad":
        return "%s.%s" % (t["ref"], t["num"])
    if t["kind"] == "end":
        return "lane(%.2f,%.2f)" % (t["x"], t["y"])
    return "pt(%.2f,%.2f)" % (t["x"], t["y"])


def pt(x, y, lay=L.F):
    return dict(kind="point", x=x, y=y, L=lay)


# ----------------------------------------------------------------------------------------------------------------
def jobs_xtal():
    log("== crystals (layout.md §4.3)")
    route_net("OSC_XIN", [lane_end("OSC_XIN"), pad_term("R51", "2"), pad_term("Y1", "1"), pad_term("C77", "1")])
    # OSC_XOUT leaves the fan between R51 and C55 as one straight neck-down segment (DRU) to R50.1, then to TP6
    fixed("OSC_XOUT", "F", [(38.76, 28.65), (38.00, 26.46)])
    route_net("OSC_XOUT", [pad_term("R50", "1"), pad_term("TP6", "1")])
    route_net("OSC_XOUT_X", [pad_term("R50", "2"), pad_term("Y1", "3"), pad_term("C76", "1")])
    # RTC: south from the gate east of the SDMMC lanes (which turn west under the ring-1 row, D-105). The lanes are
    # 0.45 mm apart (0.30 mm gap = the XTAL clearance): the neck-down exit pieces spread them to 0.50 mm before the
    # class rules apply.
    xi, xo = lane_end("RTC_XIN"), lane_end("RTC_XOUT")
    fixed("RTC_XIN", "F", [xi["back"], (36.15, 47.50), (36.15, 51.30)])
    route_net("RTC_XIN", [P("Y2", "1"), P("C79", "1")])
    fixed("RTC_XOUT", "F", [xo["back"], (35.65, 47.50), (35.65, 49.75)])
    route_net("RTC_XOUT", [pt(35.65, 49.75), P("Y2", "2"), P("C78", "1")])


SW_AREAS = []


def setup_sw_areas():
    """the four SW nodes (inductor pin 1 pad to IC pin 3 pad, the L1 SW copper) + 0.3 mm: closed to L4 routing and to
    vias of other nets (layout.md §4.5 'nothing else under them on L1/L4')"""
    for u, ind in (("U4", "L1"), ("U5", "L2"), ("U6", "L3"), ("U7", "L4")):
        polys = PADS[(u, "3")]["poly"] + PADS[(ind, "1")]["poly"]
        xs, ys = [q[0] for q in polys], [q[1] for q in polys]
        r = (min(xs) - 0.3, min(ys) - 0.3, max(xs) + 0.3, max(ys) + 0.3)
        SW_AREAS.append(r)
        GRID_NOVIA.append(r)


def setup_novia():
    """no-via areas for L4 vias: the VDD_0V9 neck and its free strips (D-110), the L3 escape fingers + 0.57 mm, under
    U9, and the courtyards of U11, U1, J1 + 0.15 mm (D-108 a)"""
    GRID_NOVIA.append((42.95, 28.05, 65.0, 37.0))
    GRID_NOVIA.append((60.5, 28.05, 63.5, 35.5))
    fj = json.load(open(os.path.join(PCB, "escape_fingers.json")))
    for f in fj:
        r = f["rect"]
        GRID_NOVIA.append((r[0] - 0.57, r[1] - 0.57, r[2] + 0.57, r[3] + 0.57))
    # the ring-1 row band (8.0-10.3 mm from the U9 centre, Chebyshev): the lane exits of L5 (D-110 inventory)
    for r in ((24.2, 26.2, 44.8, 28.5), (24.2, 44.5, 44.8, 46.8), (24.2, 28.5, 26.5, 44.5), (42.5, 28.5, 44.8, 44.5)):
        GRID_NOVIA.append(r)
    for ref, m in (("U9", 0.0), ("U11", 0.15), ("U1", 0.15), ("J1", 0.15)):
        c = S.court[ref]
        GRID_NOVIA.append((c[0] - m, c[1] - m, c[2] + m, c[3] + m))
        if ref != "U9":
            STITCH_OK_AREAS.append(GRID_NOVIA[-1])


def mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def jobs_eth():
    log("== Ethernet (layout.md §4.2, D-106 b, D-108 b)")
    rn, rp = lane_end("ETH_RXN"), lane_end("ETH_RXP")
    cs = mid(rn["back"], rp["back"])
    # RX: coupled on L1 from the gate north-west and west, south of R59 (D-106 b)
    c = route_pair("ETH_RXP", "ETH_RXN", cs, (17.3, 29.4), win=(12, 24, 28, 33), first=(-1, -1),
                   starts=(rp["back"], rn["back"]))
    if c:
        pl = p_left_for("ETH_RXP", c, rp["back"])
        lp, ln = place_pair_lines("ETH_RXP", "ETH_RXN", c, pl)
        ETH_SPLIT["RX"] = (lp[-1], ln[-1])
    # TX: coupled on L1 west, south of the RX pair, then one hop per line under the RX pair on L4 (D-106 b; owner
    # approved at D-H5), up north of RX, then L1 to R57.1 (TXN) and west of R57 to R56.1 (TXP)
    tn, tp = lane_end("ETH_TXN"), lane_end("ETH_TXP")
    cs = mid(tn["back"], tp["back"])
    c = route_pair("ETH_TXP", "ETH_TXN", cs, TX_PAIR_END, win=(18, 26, 28, 34), first=(-1, -0.2), neck=0.95,
                   starts=(tp["back"], tn["back"]))
    if not c:
        return
    pl = p_left_for("ETH_TXP", c, tp["back"])
    lp, ln = place_pair_lines("ETH_TXP", "ETH_TXN", c, pl)
    vias = {}
    for net, end, near_dn, near_up in (("ETH_TXN", ln[-1], TXN_VIAS[0], TXN_VIAS[1]),
                                       ("ETH_TXP", lp[-1], TXP_VIAS[0], TXP_VIAS[1])):
        v1 = find_via(net, near_dn, 0.8)
        v2 = find_via(net, near_up, 0.8)
        if not (v1 and v2):
            return
        via_here(net, *v1, gnd_r=(0.6, 1.0))
        via_here(net, *v2, gnd_r=(0.6, 1.0))
        vias[net] = (v1, v2)
        route_net(net, [pt(*end), pt(*v1)], layers=L.F)
        route_net(net, [pt(v1[0], v1[1], L.B), pt(v2[0], v2[1], L.B)], layers=L.B)
    # TXN is the short line of the TX pair (TXP goes round R57 to R56.1): its L1 run from the up-via to R57.1 goes
    # east through the free area south of TP25 (a length-tuning detour) and gets a meander there (below)
    # TXN is the short line of the TX pair (TXP goes round R57 to R56.1): from its up-via it takes a U through the free
    # area east of R57 (every bend 135 deg, D-112 e; it replaces the round-1 45 deg hairpin) and enters R57.1 from the
    # north between R57's pads - the U adds the length the pair skew needs (<= 1.27 mm, layout.md §4.2)
    v2 = vias["ETH_TXN"][1]
    x0, y0 = v2
    fixed("ETH_TXN", "F", [v2, (x0 + 1.0, y0), (x0 + 1.7, y0 - 0.7)] + TXN_U, w=width("ETH_TXN"))
    route_net("ETH_TXP", [pt(*vias["ETH_TXP"][1]), pad_term("R56", "1")], layers=L.F)
    # RX breakouts: RXN up into R59.1, RXP south and west of R59 to R58.1
    if "RX" in ETH_SPLIT:
        pend, nend = ETH_SPLIT["RX"]
        route_net("ETH_RXN", [pt(*nend), pad_term("R59", "1")])
        route_net("ETH_RXP", [pt(*pend), pad_term("R58", "1")])
    # centre taps first (short, straight up to J3.4/J3.5), then the jack side of the links (P/N swaps of D-106 b)
    route_net("ETH_TCT", [pad_term("C82", "1"), pad_term("J3", "4")])
    route_net("ETH_RCT", [pad_term("C83", "1"), pad_term("J3", "5")])
    route_net("ETH_RXN_J", [pad_term("R59", "2"), pad_term("J3", "6")])
    route_net("ETH_RXP_J", [pad_term("R58", "2"), pad_term("J3", "3")])
    route_net("ETH_TXN_J", [pad_term("R57", "2"), pad_term("J3", "2")])
    route_net("ETH_TXP_J", [pad_term("R56", "2"), pad_term("J3", "1")])
    # P/N skew (layout.md §4.2 <= 1.27 mm): tune the N side; the jack-side nets first, the rest on the SoC-side net
    # so that both the KiCad pair (P vs N, DRU skew rule) and the total across the 0R links match
    for p, n, pj, nj in (("ETH_RXP", "ETH_RXN", "ETH_RXP_J", "ETH_RXN_J"), ("ETH_TXP", "ETH_TXN", "ETH_TXP_J",
                                                                          "ETH_TXN_J")):
        dP = net_len(p) - net_len(n)
        dJ = net_len(pj) - net_len(nj)
        tj = 0.0
        if dJ > 0.3:
            for f in (1.0, 0.75, 0.5):
                if tune(nj, dJ * f, entry=0, g=0.6, amp_max=1.2):
                    tj = dJ * f
                    break
        tn = min(dP + dJ - tj, dP + 0.9)
        if tn > 0.3:
            if not tune(n, tn, entry=None, g=0.7, amp_max=1.4):
                tune(n, tn * 0.5, entry=None, g=0.7, amp_max=1.4) and tune(n, tn * 0.5, entry=None, g=0.7,
                                                                               amp_max=1.4)
        log("  skew %s/%s: pair %.3f mm, total across the links %.3f mm" % (
            p, n, net_len(p) - net_len(n), net_len(p) + net_len(pj) - net_len(n) - net_len(nj)))


def tune(net, delta, entry=None, g=0.7, amp_max=1.6, sides=(1, -1), min_seg=None, tag=""):
    """add `delta` mm to `net` with a trapezoid meander on one of its L4-phase polylines (the longest straight
    segments are tried first, both sides, amplitude found by bisection); every new segment is checked exactly."""
    if net not in ROUTES:
        log("  FAIL tune %s: net not routed" % net)
        FAILS.append((net, ["tune"]))
        return False
    R = ROUTES[net]
    cands = []
    for k, (layer, pts, ww) in enumerate(R["tracks"]):
        if entry is not None and k != entry:
            continue
        for i in range(len(pts) - 1):
            a, b = tuple(pts[i]), tuple(pts[i + 1])
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            if L.seg_intersects_rect(a, b, L.FAN):
                continue
            cands.append((ln, k, i, layer, ww))
    cands.sort(key=lambda c: -c[0])
    for ln, k, i, layer, ww in cands:
        lay = L.F if layer == "F" else L.B
        pts = [tuple(p) for p in R["tracks"][k][1]]
        a, b = pts[i], pts[i + 1]
        for n in range(1, 12):
            span = (2 * n - 1) * g + 2 * g
            if span + 0.4 > ln:
                break
            body = (2 * n - 1) * g
            starts = [(ln - body) / 2]
            x = 0.3
            while x + body + 0.3 <= ln:
                starts.append(x)
                x += 0.25
            for side in sides:
                for start in starts:
                    lo, hi = 0.2, amp_max
                    f = lambda A: L.plen(L.meander(a, b, start, n, A, g, side)) - ln
                    if f(hi) < delta:
                        break
                    for _ in range(30):
                        m = (lo + hi) / 2
                        if f(m) < delta:
                            lo = m
                        else:
                            hi = m
                    new = L.meander(a, b, start, n, hi, g, side)
                    S.set_track_layer(net, a, b, 0)
                    ok = all(S.check_seg(net, lay, p, q, ww / 2) for p, q in zip(new, new[1:]))
                    if ok:
                        for p, q in zip(new, new[1:]):
                            S.add_track(net, lay, p, q, ww / 2)
                        R["tracks"][k] = (layer, [list(p) for p in pts[:i] + new + pts[i + 2:]], ww)
                        log("  tune %s: +%.3f mm, %d cycles, amplitude %.2f mm on %s" % (net, delta, n, hi,
                                                                                         tag or net))
                        return True
                    S.set_track_layer(net, a, b, lay)
    log("  FAIL tune %s: no room for +%.2f mm" % (net, delta))
    FAILS.append((net, ["tune"]))
    return False


def P(ref, num):
    return pad_term(ref, num)


def jobs_sd():
    log("== microSD (layout.md §4.4, D-105, D-108 c)")
    # The bus (D-105): each line leaves its gate straight (neck-down piece), turns west in a staircase under the
    # ring-1 row (pitch SD_PITCH), runs south-west as one 45 deg bundle and drops into its J2 pin. Planar order
    # W->E = J2 order D1, D0, CLK, CMD, D3, D2 (no crossing, no via). Every segment is checked exactly.
    c0 = SD_C0
    bus = (("SDMMC_DET", None, 31.715, None), ("SDMMC_D1", None, 32.065, ("J2", "8")), ("SDMMC_D0", None, 33.235, ("J2", "7")),
           ("SDMMC_CLK_SD", ("R48", "2"), 33.83, ("J2", "5")), ("SDMMC_CMD", None, 34.33, ("J2", "3")),
           ("SDMMC_D3", None, 34.73, ("J2", "2")), ("SDMMC_D2", None, 35.125, ("J2", "1")))
    dc = SD_PITCH * math.sqrt(2)
    for k, (net, startpad, xv, pin) in enumerate(bus):
        yk = SD_Y0 + SD_PITCH * k
        ck = c0 + dc * k
        xt = ck - yk                       # where the horizontal turns south-west
        if pin is None:                    # SDMMC_DET: NW-most line of the bundle, leaves it towards TP30 / R49
            e = lane_end(net)
            pts = [e["back"], (xv, yk), (xt, yk), (13.6, ck - 13.6)]
            fixed(net, "F", pts)
            route_net(net, [pt(13.6, ck - 13.6), P("TP30", "1"), P("R49", "1")], margin=2.0)
            continue
        pp = PADS[pin]
        xpin = SD_XDROP.get(net, pp["x"])  # CMD drops 0.25 mm east of its pin: C26.2's GND via sits west of it
        yv = ck - xpin                     # where the diagonal turns south into the pin
        if startpad:
            p0 = PADS[startpad]
            pts = [(p0["x"], p0["y"]), (xv, yk)]
        else:
            e = lane_end(net)
            if yk <= 47.55:
                pts = [e["back"], (xv, yk)]
            else:
                pts = [e["back"], (xv, 47.55), (xv, yk)]
        pts += [(xt, yk), (xpin, yv)]
        if xpin != pp["x"]:
            pts += [(xpin, pp["y"] - 0.75)]
        pts += [(pp["x"], pp["y"])]
        fixed(net, "F", pts)
    # card supply after the bus: J2.4 -> C23 -> C26 on L1, then via beside C26.1 and L4 to Q4/C22/R40/TP16
    # (D-108 c); L1 is closed to it over the J2 fan-in (x 12.5-24, y 50-64.3) except around C26
    route_net("VCC3V3_SD", [P("J2", "4"), P("C23", "1"), P("C26", "1")], layers=L.F)
    fb = [(L.F, (12.5, 56.5, 16.55, 64.3)), (L.F, (18.40, 56.5, 24.0, 64.3)), (L.F, (16.55, 56.5, 18.40, 59.70))]
    route_net("VCC3V3_SD", [P("C26", "1"), P("Q4", "3"), P("C22", "1"), P("R40", "1"), P("TP16", "1")],
              layers=L.F | L.B, via_ok=True, via_cost=1.0, margin=3.0, forbid=fb)
    double_vias("VCC3V3_SD")


def jobs_nand():
    log("== SPI NAND (layout.md §4.4, D-106 c)")
    # CLK_NAND over U10's top row and down the east channel to pin 6's inner end; CS0N to R55; D2 straight to R53 and
    # pin 3; D1 passes between pins 3 and 4 and up the west channel to pin 2's inner end (D-106 c: no via, L1 only);
    # D0 (inner) and D3 round the south of U10 to pins 5 and 7
    fixed("FSPI_CLK_NAND", "F", [(43.72, 37.84), (57.90, 37.84), (57.90, 40.90), (58.33, 41.33), (59.25, 41.33)])
    # D2 runs between CS0N (above) and D1 (below): a straight neck-down exit east to x 45.2 first (DRU), then SE to
    # R53.2 and on to pin 3
    e = lane_end("FSPI_D2")
    fixed("FSPI_D2", "F", [e["back"], (45.20, e["y"])])
    route_net("FSPI_D2", [pt(45.20, e["y"]), P("R53", "2"), P("U10", "3")], margin=2.5)
    # CS0N above D2: neck-down exit rising to y 38.25 (under R47, over D2), east, then down parallel to D2 and
    # under R54 into R55.1 (hand-placed, exactly checked)
    e = lane_end("FSPI_CS0N")
    fixed("FSPI_CS0N", "F", [e["back"], (45.30, 38.30)])
    fixed("FSPI_CS0N", "F", [(45.30, 38.30), (45.60, 38.30), (47.75, 40.45), (50.40, 40.45)])
    route_net("FSPI_CS0N_NAND", [P("R55", "2"), P("U10", "1"), P("R54", "2")], margin=2.0)
    route_net("FSPI_D1", [lane_end("FSPI_D1"), pt(50.90, 41.97)], margin=3.0)
    fixed("FSPI_D1", "F", [(50.90, 41.97), (52.90, 41.97), (52.90, 40.06), (51.75, 40.06)])
    route_net("FSPI_D0", [lane_end("FSPI_D0"), P("U10", "5")], margin=3.0)
    route_net("FSPI_D3", [lane_end("FSPI_D3"), P("R52", "2"), P("U10", "7")], margin=3.0)


def match_bus(nets, clk_nets, tol=4.5, gname=""):
    """layout.md §4.4: every line within +-5 mm of its clock (CLK + CLK after the 22R). Short lines get a meander up
    to clock - tol (+-0.5 mm margin to the rule); the clock is never lengthened (the bus length limits)."""
    clk = sum(net_len(n) for n in clk_nets)
    for n in nets:
        ln = sum(net_len(m) for m in n) if isinstance(n, tuple) else net_len(n)
        if ln < clk - tol:
            for main in ((n,) if not isinstance(n, tuple) else n):
                if tune(main, clk - tol - ln + 0.3, g=0.5, amp_max=1.0):
                    break
    for n in nets:
        ln = sum(net_len(m) for m in n) if isinstance(n, tuple) else net_len(n)
        log("  %s %-26s %.2f mm, clock %.2f mm, diff %+.2f" % (gname, n, ln, clk, ln - clk))


def double_vias(net, pitch=(0.8, 1.0)):
    """layout.md §3: >= 2 vias per layer change on the power classes - a second via beside each one, tied on L1
    and L4 by short stubs"""
    vs = list(ROUTES.get(net, {}).get("vias", []))
    w = min(width(net), 0.4)
    for (x, y) in vs:
        done = False
        for r in pitch:
            for k in range(16):
                a = 2 * math.pi * k / 16
                x2, y2 = round(x + r * math.cos(a), 3), round(y + r * math.sin(a), 3)
                if not S.check_via(net, x2, y2, novia=GRID_NOVIA):
                    continue
                if not (S.check_seg(net, L.F, (x, y), (x2, y2), w / 2) and S.check_seg(net, L.B, (x, y), (x2, y2),
                                                                                         w / 2)):
                    continue
                add_via(net, x2, y2)
                add_route(net, "F", [(x, y), (x2, y2)], w)
                add_route(net, "B", [(x, y), (x2, y2)], w)
                done = True
                break
            if done:
                break
        if not done:
            log("  NOTE %s: no room for a second via at (%.2f, %.2f)" % (net, x, y))
            FAILS.append((net, ["2nd via %.2f,%.2f" % (x, y)]))


def multi_vias(net, count, w=0.4, pitch=(0.8, 1.0, 1.2)):
    """layout.md §3: >= `count` vias per layer change - extra vias beside each via of `net` placed so far, each tied on L1
    and L4 to it by short stubs of width w (PWR_5V: 3 vias, D-112 h)"""
    for (x, y) in list(ROUTES.get(net, {}).get("vias", [])):
        placed = []
        for r in pitch:
            for k in range(24):
                if len(placed) >= count - 1:
                    break
                a = 2 * math.pi * k / 24
                x2, y2 = round(x + r * math.cos(a), 3), round(y + r * math.sin(a), 3)
                if any(math.hypot(x2 - q[0], y2 - q[1]) < 0.8 for q in placed):
                    continue
                if not S.check_via(net, x2, y2, novia=GRID_NOVIA):
                    continue
                if not (S.check_seg(net, L.F, (x, y), (x2, y2), w / 2) and S.check_seg(net, L.B, (x, y), (x2, y2),
                                                                                         w / 2)):
                    continue
                add_via(net, x2, y2)
                add_route(net, "F", [(x, y), (x2, y2)], w)
                add_route(net, "B", [(x, y), (x2, y2)], w)
                placed.append((x2, y2))
        if len(placed) < count - 1:
            log("  NOTE %s: only %d vias at (%.2f, %.2f)" % (net, len(placed) + 1, x, y))
            FAILS.append((net, ["%d vias %.2f,%.2f" % (len(placed) + 1, x, y)]))


def jobs_pmu():
    log("== buck cells (layout.md §4.5): SW node, feedback, output")
    cells = (("U6", "L3", "U6_SW", "U6_FB", "VCC_3V3_BUCK", ("C18", "C25", "C31", "R22", "R30")),
             ("U7", "L4", "U7_SW", "U7_FB", "VCC_DDR_BUCK", ("C19", "C28", "C32", "R18", "R31")),
             ("U4", "L1", "U4_SW", "U4_FB", "VDD_0V9_BUCK", ("C16", "C24", "C29", "R17", "JP1")),
             ("U5", "L2", "U5_SW", "U5_FB", "VCC_1V8_BUCK", ("C17", "C27", "C30", "R19", "R29")))
    for u, ind, sw, fb, out, parts in cells:
        # SW node: 1.20 mm from the inductor pad to 0.63 mm short of the IC's pad row, then the pad width (0.60 mm)
        # into pin 3 - a 1.2 mm copper cannot sit between the 0.95 mm-pitch SOT-23-5 pins at the 0.30 mm SW_NODE
        # clearance (the SW pin itself is 0.6 mm wide); straight, on L1 only
        pu, pl = PADS[(u, "3")], PADS[(ind, "1")]
        ux0 = min(q[0] for q in pu["poly"])
        xe = ux0 - 0.63
        fixed(sw, "F", [(pl["x"], pu["y"]), (xe, pu["y"])], w=1.20)
        fixed(sw, "F", [(xe, pu["y"]), (pu["x"], pu["y"])], w=0.60)
        fbp = [p for p in S.pads if p["net"] == fb]
        route_net(fb, [P(u, "5")] + [P(p["ref"], p["num"]) for p in fbp if p["ref"] != u], margin=1.5)
        outp = [p for p in S.pads if p["net"] == out]
        terms = [P(ind, "2")] + [P(p["ref"], p["num"]) for p in outp if p["ref"] != ind]
        route_net(out, terms, margin=1.5)


def jobs_power():
    log("== power paths (layout.md §3, §4.5)")
    # USB-C VBUS -> F1 (1.0 mm), F1 -> Q1 / D1 / C2 (1.0 mm), the small loads of VBUS_5V at 0.30 mm
    # J1 VBUS pins (pad pitch 0.5 mm, NPTH pegs under the pad row): A9/B4 north 0.5 mm then 1.0 mm east to F1.1;
    # A4/B9 north 0.4 mm past the USBC_DM join via, two vias, 0.8 mm on L4 round the north of U1 back to the F1 side
    # J1 VBUS pin pairs (layout.md §3: PWR_5V 1.0 mm, >= 3 vias per layer change, D-112 h): A9/B4 north at 0.40 mm
    # for 2.1 mm (pad neck: the J1 GND via at (52.6, 71.6) / the USBC_DP via at (47.75, 70.9) leave no more) and 1.0 mm east to F1.1; A4/B9 north at the pad width, 3 vias, 1.0 mm on L4 round the north of U1
    # to 3 vias at F1 and 1.0 mm on L1 into F1.1
    fixed("VBUS_IN", "F", [(51.95, 72.31), (51.95, 70.25)], w=0.40)
    fixed("VBUS_IN", "F", [(51.95, 70.25), (55.90, 70.25), (56.46, 70.30)], w=1.00)
    fixed("VBUS_IN", "F", [(47.05, 72.31), (47.05, 70.05)], w=0.40)
    if via_here("VBUS_IN", 47.05, 70.05, gnd=False):
        route_net("VBUS_IN", [pt(47.05, 70.05, L.B), P("F1", "1")], w=1.00, layers=L.F | L.B, via_ok=True,
                  via_cost=1.0, margin=4.0, forbid=[(L.F, (44.0, 64.0, 55.0, 80.0))])
        multi_vias("VBUS_IN", 3, w=0.60)
    route_net("VBUS_IN", [P("F1", "1"), P("TP21", "1")], w=0.30, layers=L.F | L.B, via_ok=True, margin=2.5)
    route_net("VBUS_5V", [P("F1", "2"), P("D1", "1"), P("Q1", "2"), P("C2", "1")], margin=2.5)
    route_net("VBUS_5V", [P("Q1", "2"), P("C3", "1"), P("U3", "1"), P("C4", "2"), P("R5", "2"), P("R8", "1"),
                          P("TP1", "1"), pt(49.50, 66.50, L.B)], w=0.30, layers=L.F | L.B, via_ok=True, margin=3.0)
    # VCC_DDR / VCC_1V8: L1/L4 traces at the class width (no L3 region, layout.md §2.3), >= 2 vias per change
    for net, src in (("VCC_DDR", ("R31", "2")), ("VCC_1V8", ("R29", "2"))):
        pads = [p for p in S.pads if p["net"] == net]
        terms = [P(*src)] + sorted([P(p["ref"], p["num"]) for p in pads if (p["ref"], p["num"]) != src and
                                    p["ref"] != "U9" and (p["ref"], p["num"]) not in SPECIAL_PADS],
                                   key=lambda t: math.hypot(t["x"] - 63, t["y"] - 35))
        # L1 is closed to the rails north and west of the SoC (x 18-46.5, y 10-28.5 and x 18-26.5, y 28-48): the
        # header / UART / LED lanes of L5 leave the SoC there (lanecheck.py); the rails take L4 there
        fb = [(L.F, (18.0, 10.0, 36.5, 28.4)), (L.F, (18.0, 28.0, 26.4, 48.0))] if net == "VCC_1V8" else []
        route_net(net, terms, layers=L.F | L.B, via_ok=True, via_cost=2.0, margin=4.0, forbid=fb)
        # ring-2 decoupling caps boxed in by GND pads/vias inside the VDD_0V9 neck: one via each is allowed in the
        # neck (D-111; check_routing.py measures the neck cross-section afterwards)
        if net == "VCC_DDR":
            # U9.56's inner via pair (39.70, 34.03) / (39.50, 34.78) (L3 escape) joins the rail on L4 at the ring-1 rail
            # vias west of C53 (verifier L4 r1: VCC_DDR open item); before the VCC_1V8 rail takes L4 there
            route_net("VCC_DDR", [pt(39.50, 34.78, L.B), pt(41.582, 36.272, L.B)], w=0.30, layers=L.B, margin=1.5)
            # C45.1 (ring-2, boxed in by GND pads/vias in the VDD_0V9 neck): own via right beside the pad (D-112 i)
            fixed("VCC_DDR", "F", [(44.794, 35.891), C45_VIA], w=0.30)
            if fixed_via("VCC_DDR", *C45_VIA, gnd=False):
                connect_b("VCC_DDR", C45_VIA, 0.30)
        else:
            # C47.1: no via site beside the pad -> via in the pad (filled and capped, D-112 i); R44.1/R45.1 (RECOVERY /
            # SARADC_IN1 pull-ups): L1 link + via placed before the SENSE routes (jobs_sense); C47's via joins the
            # nearest VCC_1V8 L4 copper of the rail, the R44 via joins C47's via, all on L4
            if S.check_via("VCC_1V8", *C47_VIA, own_pad_ok=True):
                add_via("VCC_1V8", *C47_VIA)
                connect_b("VCC_1V8", C47_VIA, 0.30)
                route_net("VCC_1V8", [pt(R44_VIA[0], R44_VIA[1], L.B), pt(C47_VIA[0], C47_VIA[1], L.B)], w=0.30,
                          layers=L.B, margin=3.0)
            else:
                log("  FAIL VCC_1V8: C47.1 via-in-pad not legal")
                FAILS.append(("VCC_1V8", ["C47 via"]))
        connect_rest(net, 0.30, novia=[r for r in GRID_NOVIA if r != (42.95, 28.05, 65.0, 37.0)])
        double_vias(net)
    jobs_vcc1v8_north()


def nearest_b(net, p, exclude=()):
    """nearest point of the net's routed L4 copper to p (end points and points every 0.25 mm along the segments)"""
    best = None
    for layer, pts, w in ROUTES.get(net, {}).get("tracks", []):
        if layer != "B":
            continue
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.25))
            for k in range(n + 1):
                q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                if any(math.hypot(q[0] - e[0], q[1] - e[1]) < 1.0 for e in exclude):
                    continue
                d = math.hypot(q[0] - p[0], q[1] - p[1])
                if best is None or d < best[0]:
                    best = (d, q)
    return best[1] if best else None


def jobs_vcc1v8_north():
    """D-115 (L5 round 3, verifier round 2 blocker gpio): C69 (pin-70 bulk, moved north-east of the north lane field)
    and FB3.1 (ETH_AVDD1V8 bead input, moved 0.35 mm west) join the VCC_1V8 rail by their own vias, and no VCC_1V8
    via or L4 track sits in the north lane corridors / field (round 2: the pair at (32.04, 25.71) / (32.84, 25.71) and
    the L4 run under the field closed them). C69: a via in its pad (filled and capped, as C47.1 / D-112 i) plus a second
    one 0.8 mm east, L4 south to the rail. FB3: two vias west of FB3.1, L1 into the pad, L4 east to the rail."""
    net = "VCC_1V8"
    forbid = [(L.B, NORTH_FIELD), (L.B, WEST_LEGS)]
    c = PADS[("C69", "1")]
    v1, v2 = (c["x"], c["y"]), (round(c["x"] + C69_VIA2_DX, 3), c["y"])
    if S.check_via(net, *v1, own_pad_ok=True) and S.check_via(net, *v2):
        add_via(net, *v1)
        add_via(net, *v2)
        add_route(net, "F", [v1, v2], 0.40)
        add_route(net, "B", [v1, v2], 0.40)
        tgt = nearest_b(net, v2, exclude=(v1, v2))
        ok = tgt is not None and route_net(net, [pt(v2[0], v2[1], L.B), pt(tgt[0], tgt[1], L.B)], layers=L.B, w=0.40,
                                           margin=4.0, forbid=forbid)
        log("  VCC_1V8 C69 (via in pad + 0.8 mm east) -> rail on L4: %s" % ("ok" if ok else "FAIL"))
    else:
        log("  FAIL VCC_1V8: C69 vias not legal")
        FAILS.append((net, ["C69 vias"]))
    f = PADS[("FB3", "1")]
    xs = [q[0] for q in f["poly"]]
    a, b = FB3_VIAS
    if S.check_via(net, *a) and S.check_via(net, *b):
        add_via(net, *a)
        add_via(net, *b)
        add_route(net, "F", [b, a, (min(xs) + 0.10, a[1])], 0.40)
        add_route(net, "B", [b, a], 0.40)
        tgt = nearest_b(net, a, exclude=(a, b))
        ok = tgt is not None and route_net(net, [pt(a[0], a[1], L.B), pt(tgt[0], tgt[1], L.B)], layers=L.B, w=0.40,
                                           margin=6.0, forbid=forbid)
        log("  VCC_1V8 FB3.1 (two vias west of the pad) -> rail on L4: %s" % ("ok" if ok else "FAIL"))
    else:
        log("  FAIL VCC_1V8: FB3 vias not legal")
        FAILS.append((net, ["FB3 vias"]))


DDR_CORRIDOR = (39.15, 33.70, 42.0, 36.60)
RECOVERY_L4 = [(37.20, 41.65), (36.71, 42.14), (36.24, 42.14), (35.94, 41.84), (35.94, 39.19), (36.14, 38.99),
               (36.14, 36.94), (39.46, 33.59), (39.51, 33.54), (39.79, 33.54), (40.19, 33.14), (40.19, 32.71),
               (43.46, 27.56), (43.46, 26.64), (44.91, 25.19)]
SPECIAL_PADS = {("C45", "1"), ("C47", "1"), ("R44", "1"), ("R45", "1"),   # joined by hand below (D-112 i)
                ("C69", "1"), ("FB3", "1")}                                 # D-115: joined by jobs_vcc1v8_north
# D-115 (L5 round 3): the north lane field of l5_north.py (corridors, field, bus rows) and the J5 legs west of it stay
# free of VCC_1V8 copper on L4 and of its vias
NORTH_FIELD = (25.2, 16.6, 36.2, 24.3)
WEST_LEGS = (0.0, 16.6, 24.6, 60.0)
FB3_VIAS = ((24.85, 25.45), (24.85, 24.65))
C69_VIA2_DX = 0.80
C45_VIA = (44.49, 35.99)
C47_VIA = (44.961, 33.949)
R44_VIA = (46.27, 27.00)


def connect_b(net, start, w):
    """route `net` on L4 from `start` to the nearest L4 point of its routed copper"""
    best = None
    for layer, pts, ww in ROUTES.get(net, {}).get("tracks", []):
        if layer != "B":
            continue
        for q in pts:
            d = math.hypot(q[0] - start[0], q[1] - start[1])
            if d > 0.3 and (best is None or d < best[0]):
                best = (d, q)
    if best:
        route_net(net, [pt(start[0], start[1], L.B), pt(best[1][0], best[1][1], L.B)], w=w, layers=L.B, margin=2.5)


def connected_pads(net):
    """pads of `net` touched by its L4 routes (end points inside the pad polygon, layer-aware)"""
    got = set()
    for layer, pts, w in ROUTES.get(net, {}).get("tracks", []):
        lay = L.F if layer == "F" else L.B
        for q in (pts[0], pts[-1]):
            for p in S.pads:
                if p["net"] == net and p["lay"] & lay and L.inside_poly(q[0], q[1], p["poly"]):
                    got.add((p["ref"], p["num"]))
    return got


def connect_rest(net, w, layers=L.F | L.B, refs=None, novia=None):
    """join every still unconnected pad of `net` (decoupling caps boxed in by the ring-2 column, test pads) to the
    nearest point of the net's routed copper with a narrower branch (w); recorded in D-111 (d)"""
    done = connected_pads(net)
    for p in [p for p in S.pads if p["net"] == net and (p["ref"], p["num"]) not in done]:
        if refs and p["ref"] not in refs or p["ref"] == "U9" or (p["ref"], p["num"]) in SPECIAL_PADS:
            continue                        # U9 pins reach their ring-1 caps through the L3 escape
        best = None
        for layer, pts, ww in ROUTES.get(net, {}).get("tracks", []):
            for q in pts:
                d = math.hypot(q[0] - p["x"], q[1] - p["y"])
                if best is None or d < best[0]:
                    best = (d, q, L.F if layer == "F" else L.B)
        if best is None:
            continue
        # drop the earlier failure of this pad, if any
        FAILS[:] = [f for f in FAILS if not (f[0] == net and any(("%s.%s" % (p["ref"], p["num"])) in x
                                                                  for x in f[1]))]
        route_net(net, [P(p["ref"], p["num"]), pt(best[1][0], best[1][1], best[2])], w=w, layers=layers,
                  via_ok=layers == L.F | L.B, via_cost=2.0, margin=3.0, novia=novia)


def jobs_sense():
    log("== SENSE nets (layout.md §4.5, §4.7; D-104 e: 22/23/25 leave on L4)")
    for net in ("ONOFF_PDT", "QPWR_G", "USBA_ISET"):
        pads = [p for p in S.pads if p["net"] == net]
        route_net(net, [P(p["ref"], p["num"]) for p in pads], margin=2.0)
    # VCC_1V8 to the RECOVERY / SARADC_IN1 pull-ups R44.1 / R45.1 first (verifier L4 r1 blocker): an L1 link between the
    # two pads and a via south of them; the SENSE routes then pass round it (jobs_power joins the via on L4)
    fixed("VCC_1V8", "F", [(45.763, 26.353), (45.763, 26.493), (46.27, 27.00)], w=0.30)
    fixed("VCC_1V8", "F", [(46.769, 26.242), (46.769, 26.501), (46.27, 27.00)], w=0.30)
    fixed_via("VCC_1V8", *R44_VIA, gnd=False)
    # RECOVERY first: L4 from its inner via (router, north of the VCC_DDR corridor) to a via west of R45, then
    # hand-placed L1 to R44.2, C72.1 and north to the recovery key; then USB_DET_IN and SARADC_IN1 by the router
    # the L4 corridor from U9.56's VCC_DDR inner vias (39.70, 34.03) / (39.50, 34.78) east to the VCC_DDR rail vias is
    # kept free for jobs_power (verifier L4 r1: VCC_DDR open item); the SENSE nets pass north of it
    if fixed_via("RECOVERY", *RECOVERY_L4[-1], gnd=False):
        route_net("RECOVERY", [pt(RECOVERY_L4[0][0], RECOVERY_L4[0][1], L.B), pt(RECOVERY_L4[-1][0],
                                                                                RECOVERY_L4[-1][1], L.B)],
                  layers=L.B, margin=3.0, forbid=[(L.B, DDR_CORRIDOR)])
        fixed("RECOVERY", "F", [RECOVERY_L4[-1], (45.39, 24.71), (46.26, 24.71), (46.769, 25.219)])
        # (RECOVERY_L4 keeps only its end points: the round-1 L4 path is re-routed by the grid around DDR_CORRIDOR)
        fixed("RECOVERY", "F", [(46.769, 25.219), (47.73, 26.19), (47.87, 26.19)])
        fixed("RECOVERY", "F", [(46.769, 25.219), (46.769, 15.12), (52.49, 9.40)])
    for net in ("USB_DET_IN", "SARADC_IN1"):
        vs = [v for v in geo["vias"] if v["net"] == net]
        pads = [p for p in S.pads if p["net"] == net and p["ref"] != "U9"]
        terms = [pt(vs[0]["x"], vs[0]["y"], L.B)] + [P(p["ref"], p["num"]) for p in pads]
        # keep L4 free east of the ring-1 VCC_1V8 caps C54/C60 (their rail via sits there, see jobs_power)
        route_net(net, terms, layers=L.F | L.B, via_ok=True, via_cost=2.0, margin=4.0,
                  forbid=[(L.B, (41.2, 33.0, 44.8, 36.6)), (L.B, DDR_CORRIDOR)])


INNER_NETS = ("VCC3V3_RTC",)   # D-114 c: USB_SEL / PB_INT_N / SDMMC_PWREN are boxed in by the SENSE routes (open item)
# L4 areas the inner-via nets must leave free: the SENSE nets RECOVERY / SARADC_IN1 (west of x 37.8 and north-west of
# x + y = 69.9 in the U9 field), the VCC_1V8 rail of jobs_power (east of x 43.3 in y 31-43, the bar at y 47.86 and the
# column at x 31.59 south of the field); the inner nets leave the U9 field to the south / south-east between them
INNER_FORBID = [(L.B, (26.6, 31.0, 37.8, 41.3)), (L.B, (43.3, 31.0, 50.0, 43.0)),
                (L.B, (24.0, 47.3, 42.0, 48.45)), (L.B, (31.0, 34.4, 32.2, 48.45)),
                (L.B, (42.9, 46.2, 44.4, 47.7))]      # USB_DET_IN's L4->L1 via at (43.64, 46.96): the grid passed it
                                                      # at 0.193 mm (PWR_SUB 0.20) in a trial; kept clear here


def jobs_subrail():
    """D-114 d (L5 round 2): sub-rail joins that need L4 before the SENSE nets take it"""
    log("== PWR_SUB sub-rails with a boxed-in ring-1 capacitor (D-114 d)")
    # D-114 d: two PWR_SUB sub-rails whose ring-1 decoupling capacitor pad is boxed in on L1 (ETH TX pair 0.76 mm keep-off,
    # GND pads, lane row, the no-via ring band): via in the capacitor pad (filled and capped, as C47.1 of D-112 i), L4
    # to the filter part. AVDD1V8_USB: C58.1 <-> R33.2 (both pads in the ring band, via in both pads, straight L4 run at
    # y 44.71, routed before the SENSE nets and VCC3V3_RTC, which pass round it); FEPHY_AVDD3V3: C66.1 <- FB1.2 (FB1 west of the
    # C66/R42/C50 GND column).
    vip = {}
    for net, ref, num in (("AVDD1V8_USB", "C58", "1"), ("AVDD1V8_USB", "R33", "2"), ("FEPHY_AVDD3V3", "C66", "1")):
        p = PADS[(ref, num)]
        if S.check_via(net, p["x"], p["y"], own_pad_ok=True):
            add_via(net, p["x"], p["y"])
            vip[(ref, num)] = (p["x"], p["y"])
            log("  via in pad %s.%s (%s) at (%.3f, %.3f)" % (ref, num, net, p["x"], p["y"]))
        else:
            log("  FAIL via in pad %s.%s (%s)" % (ref, num, net))
            FAILS.append((net, ["via in pad %s.%s" % (ref, num)]))
    if ("C58", "1") in vip and ("R33", "2") in vip:
        a, b = vip[("C58", "1")], vip[("R33", "2")]
        ok = route_net("AVDD1V8_USB", [pt(a[0], a[1], L.B), pt(b[0], b[1], L.B)], layers=L.B, w=0.30, margin=1.5)
        log("  inner AVDD1V8_USB (C58.1 - R33.2 on L4): %s" % ("ok" if ok else "FAIL"))
    if ("C66", "1") in vip:
        c = vip[("C66", "1")]
        ok = route_net("FEPHY_AVDD3V3", [P("FB1", "2"), pt(c[0], c[1], L.B)], layers=L.F | L.B, via_ok=True,
                       via_cost=1.0, w=0.30, margin=3.0)
        log("  inner FEPHY_AVDD3V3 (FB1.2 - C66.1): %s" % ("ok" if ok else "FAIL"))


def jobs_inner():
    """D-114 a (L5 round 2, verifier blocker soc): VCC3V3_RTC (U9.19, PWR_SUB) leaves U9 by an L3 inner via; it is
    routed from that via to D2/R34/C75 here in L4, after the SENSE nets and before the power rails (kept free by
    INNER_FORBID); its test pad TP18 is joined in L5. Round 1 left it to L5, where no path was left.
    The three other inner-via DEFAULT nets (USB_SEL U9.65, SDMMC_PWREN U9.59, PB_INT_N U9.60) are NOT routable on this
    L4: the SENSE routes RECOVERY / SARADC_IN1 (south via row -> R44/R45 north-east) cross the U9 field between them and
    every exit, and a west passage for the SENSE pair is closed by the EP thermal pads and the VDD_0V9 island vias at
    (37.83, 31.30) / (41.00, 27.94) (trials D-114 c). They need an L3 escape re-plan (open item, D-114 c)."""
    log("== inner-via nets out of the U9 L4 field (D-114 a)")
    for net in INNER_NETS:
        vs = sorted((v["x"], v["y"]) for v in geo["vias"] if v["net"] == net and
                    L.FAN[0] <= v["x"] <= L.FAN[2] and L.FAN[1] <= v["y"] <= L.FAN[3])
        if not vs:
            log("  %s: no inner via" % net)
            continue
        pads = sorted((p["ref"], p["num"]) for p in S.pads if p["net"] == net and p["ref"] != "U9" and
                      not p["ref"].startswith("TP"))
        terms = [pt(vs[0][0], vs[0][1], L.B)] + [P(r, n) for r, n in pads]
        w = 0.30 if width(net) >= 0.3 else 0.15
        ok = route_net(net, terms, layers=L.F | L.B, via_ok=True, via_cost=2.0, margin=6.0, w=w,
                       forbid=[(L.B, (41.2, 33.0, 44.8, 36.6)), (L.B, DDR_CORRIDOR)] + INNER_FORBID)
        log("  inner %s: %s" % (net, "ok" if ok else "FAIL"))


def L4_COST(lay, X, Y):
    """L4 steps cost 2.5x: a hop stays a hop (layout.md §2.3: L1 for every critical net)"""
    import numpy as np
    return np.full(X.shape, 2.5 if lay == L.B else 1.0)


W45 = 0.42           # single-ended ~45 ohm on L1 over L2 (tools/zsolve.py: 45.1 ohm; 2 x 45 ~ 90 ohm uncoupled, D-112 c)
USBW = 0.255


def pair_lines(centre, pnet, nnet, p_side):
    """offset a centre polyline into the P and N lines at the class pitch; p_side = +1: P on the +offset side"""
    d = (USBW + pair_gap(pnet)) / 2
    a = L.offset_line(centre, d)
    b = L.offset_line(centre, -d)
    return (a, b) if p_side > 0 else (b, a)


def side_of(centre, pt_):
    """+1 if pt_ lies on the +offset side of the first centre segment"""
    (x0, y0), (x1, y1) = centre[0], centre[1]
    nx, ny = -(y1 - y0), (x1 - x0)
    return 1 if (pt_[0] - x0) * nx + (pt_[1] - y0) * ny > 0 else -1


def fixed_via(net, x, y, gnd=True):
    """a hand-placed signal via (exact check, D-108 a no-via areas waived where recorded in D-112) + GND stitching"""
    if not S.check_via(net, x, y):
        log("  FAIL %s: via (%.3f, %.3f) not legal" % (net, x, y))
        FAILS.append((net, ["via %.2f,%.2f" % (x, y)]))
        return False
    add_via(net, x, y)
    if gnd:
        HOPS.append((net, x, y, (0.6, 1.0)))
    return True


def jobs_usb():
    """USB 2.0 (layout.md §4.6; D-106 a, D-108 a hops as approved at D-H5; D-112 round-2 rework).
    Every line is a hand-placed, exactly checked polyline. Pairs run coupled (0.255 / 0.152 mm) and leave the pair only
    at the approved hops and at the breakout pins; where the two lines must run apart (pin pitch 1.9-2.5 mm at U1, U2,
    J4) they are widened to 0.42 mm (Z0 45 ohm, so Zdiff stays ~90 ohm). P/N skew is tuned on pad-to-pad paths."""
    log("== USB (layout.md §4.6, D-106 a, D-108 a, D-112)")
    # ---- SoC -> U11: coupled south from the gate (x 37.68), USB_DM hops under USB_DP (P/N swap, D-106 a) north of
    # U11 and comes up east of it; both lines then run coupled straight into U11.8 / U11.7 (pitch 0.407 inside the
    # 0.5 mm pin pitch). Y2 / C79 guard (1 mm) on the west, D2 (VCC3V3_RTC_IN) >= 0.76 mm on the east.
    dm, dp = lane_end("USB_DM"), lane_end("USB_DP")
    fixed("USB_DM", "F", [dm["back"], (37.476, 45.475)], w=FAN_W)
    fixed("USB_DP", "F", [dp["back"], (37.883, 45.475)], w=FAN_W)
    fixed("USB_DP", "F", [(37.883, 45.475), (37.883, 50.30), (38.397, 50.814), (38.397, 54.362)], w=USBW)
    fixed("USB_DM", "F", [(37.476, 45.475), (37.476, 49.024), (37.30, 49.20)], w=USBW)
    if fixed_via("USB_DM", 37.30, 49.20) and fixed_via("USB_DM", 38.95, 50.85):
        fixed("USB_DM", "B", [(37.30, 49.20), (38.95, 50.85)], w=USBW)
        fixed("USB_DM", "F", [(38.95, 50.85), (38.804, 50.996), (38.804, 54.362)], w=USBW)
    # ---- south of U11 (pins W->E: USBC_DP, USBC_DM, USBA_DP, USBA_DM). USB-C dives right under U11 and crosses east
    # under the USB-A pair on L4 (D-108 a); USB-A leaves coupled (pitch 0.407) and USBA_DM swaps under USBA_DP.
    fixed("USBC_DP", "F", [(37.80, 55.638), (37.80, 57.45)], w=USBW)
    fixed("USBC_DM", "F", [(38.35, 55.638), (38.35, 56.85)], w=USBW)
    ok = all([fixed_via("USBC_DP", 37.80, 57.45), fixed_via("USBC_DM", 38.35, 56.85),
              fixed_via("USBC_DP", 40.50, 57.45), fixed_via("USBC_DM", 39.90, 56.85)])
    if ok:
        fixed("USBC_DP", "B", [(37.80, 57.45), (40.50, 57.45)], w=USBW)
        fixed("USBC_DM", "B", [(38.35, 56.85), (39.90, 56.85)], w=USBW)
    fixed("USBA_DP", "F", [(38.8965, 55.638), (38.8965, 58.80)], w=USBW)
    fixed("USBA_DM", "F", [(39.3035, 55.638), (39.3035, 57.70), (39.45, 57.8465), (39.45, 58.0)], w=USBW)
    if fixed_via("USBA_DM", 39.45, 58.0) and fixed_via("USBA_DM", 38.34, 58.65):
        fixed("USBA_DM", "B", [(39.45, 58.0), (38.80, 58.65), (38.34, 58.65)], w=USBW)
    # ---- USB-C pair U11 -> U1: east north of U8/C11 (>= 0.76 mm from their pads), SE, south to U1; split 1.75 mm
    # above U1 into its flow-through pins 6 / 4 (0.42 mm from there, Z0 45 ohm)
    cc = [(40.693, 57.0535), (46.60, 57.0535), (49.50, 59.9535), (49.50, 64.80)]
    lp, ln = pair_lines(cc, "USBC_DP", "USBC_DM", side_of(cc, (40.693, 57.257)))
    fixed("USBC_DM", "F", [(39.90, 56.85)] + ln, w=USBW)
    fixed("USBC_DP", "F", [(40.50, 57.45)] + lp, w=USBW)
    fixed("USBC_DP", "F", [lp[-1], (48.55, lp[-1][1] + abs(lp[-1][0] - 48.55))], w=USBW)
    fixed("USBC_DM", "F", [ln[-1], (50.45, ln[-1][1] + abs(ln[-1][0] - 50.45))], w=USBW)
    ys = lp[-1][1] + abs(lp[-1][0] - 48.55)
    fixed("USBC_DP", "F", [(48.55, ys), (48.55, 67.763), (48.55, 70.037)], w=W45)
    fixed("USBC_DM", "F", [(50.45, ys), (50.45, 67.763), (50.45, 70.037)], w=W45)
    # U1.5 (VBUS_5V, the ESD diode reference) is fed by a via north of U1 between the two breakout lines
    fixed("VBUS_5V", "F", [(49.50, 66.50), (49.50, 67.40)], w=0.30)
    add_via("VBUS_5V", 49.50, 66.50)
    # ---- J1 joins (layout.md §4.6 'join A6-B6 and A7-B7 right at the connector, short symmetric stubs'): each net is
    # joined by a via T midway between its two pins, DP on the north side (between U1 and the pad row, above A7), DM on
    # the south side (under the receptacle body, below A6); each trunk reaches its T on L4 (2 vias per line here, 4 in
    # all). Both legs of each T have the same length, so the stub is the same in either plug orientation.
    fixed("USBC_DP", "F", [(48.55, 70.037), (48.55, 70.10), (47.75, 70.90)], w=USBW)
    fixed("USBC_DM", "F", [(50.45, 70.037), (50.45, 70.30), (51.15, 71.00)], w=USBW)
    if all([fixed_via("USBC_DP", 47.75, 70.90), fixed_via("USBC_DP", 49.75, 71.12),
            fixed_via("USBC_DM", 51.15, 71.00), fixed_via("USBC_DM", 49.25, 73.75)]):
        fixed("USBC_DP", "B", J1_DP_L4, w=USBW)
        fixed("USBC_DM", "B", J1_DM_L4, w=USBW)
        fixed("USBC_DP", "F", [(49.75, 71.12), (49.45, 71.12), (49.25, 71.32), (49.25, 72.20)], w=USBW)
        fixed("USBC_DP", "F", [(49.75, 71.12), (50.05, 71.12), (50.25, 71.32), (50.25, 72.20)], w=USBW)
        fixed("USBC_DM", "F", [(49.25, 73.75), (48.75, 73.25), (48.75, 72.40)], w=USBW)
        fixed("USBC_DM", "F", [(49.25, 73.75), (49.75, 73.25), (49.75, 72.40)], w=USBW)
    # ---- USB-A pair after the swap: coupled S, SW and W over U2; USBA_DP drops into U2.1, USBA_DM runs on (0.42 mm)
    # to U2.3; flow-through under U2 and straight down into J4.3 / J4.2 at 0.42 mm (1.9-2.0 mm apart)
    ca = [(38.69325, 58.80), (38.69325, 58.95), (37.85, 59.79325), (37.15, 59.79325)]
    ap, an = pair_lines(ca, "USBA_DP", "USBA_DM", side_of(ca, (38.8965, 58.80)))
    fixed("USBA_DP", "F", [(38.8965, 58.80)] + ap[1:] + [(36.95, ap[-1][1] + abs(ap[-1][0] - 36.95)), (36.95, 61.213)],
          w=USBW)
    fixed("USBA_DM", "F", [(38.34, 58.65), an[0]] + an[1:] + [(36.80, an[-1][1])], w=USBW)
    fixed("USBA_DM", "F", [(36.80, an[-1][1]), (35.05 + 0.2, an[-1][1]), (35.05, an[-1][1] + 0.2), (35.05, 61.213)],
          w=W45)
    fixed("USBA_DP", "F", [(36.95, 61.213), (36.95, 63.487)], w=W45)
    # USBA_DP is the short line of the USB-A pair (its pin U2.1 is the near one at the split): it steps 0.5 mm east
    # under U2's south edge (>= 0.76 mm from the U2.5 VBUS_USBA via stub) and enters J4.3 from the south, which adds
    # the length the pad-to-pad skew needs without a meander between the U2.5 stub and the R37 / J4.4 GND copper
    fixed("USBA_DP", "F", [(36.95, 63.487), (36.95, 63.90), (37.45, 64.40), (37.45, 67.25), (37.15, 67.55),
                           (36.90, 67.55)], w=W45)
    fixed("USBA_DM", "F", [(35.05, 61.213), (35.05, 63.487), (35.05, 66.45)], w=W45)
    # P/N skew on the pad-to-pad paths (layout.md §4.6 <= 1.27 mm; D-112 a): USB-C gets a 45 deg-mitred meander on the
    # short line where it runs alone (USBC_DP on its L4 run to the J1 T via)
    for (p, pa, pb, n, na, nb), (net, first, g, amax) in zip(USB_PATHS[2:3], (("USBC_DP", J1_DP_L4[0], 0.45, 0.9),)):
        d = pad_len(n, na, nb) - pad_len(p, pa, pb)
        if d > 0.3:
            tune(net, d, entry=track_index(net, first), g=g, amp_max=amax)
    usb_skews()


def net_graph(net):
    """pathlen graph of `net` from the exported board copper + the L4 routes so far"""
    segs = [(t["layer"], tuple(t["a"]), tuple(t["b"]), t["w"]) for t in geo["tracks"] if t["net"] == net
            and t["layer"] in ("F", "B")]
    for layer, pts, w in ROUTES.get(net, {}).get("tracks", []):
        segs += [(layer, tuple(a), tuple(b), w) for a, b in zip(pts, pts[1:])]
    vias = [(v["x"], v["y"]) for v in geo["vias"] if v["net"] == net] + [tuple(v) for v in
                                                                         ROUTES.get(net, {}).get("vias", [])]
    pads = {}
    for p in S.pads:
        if p["net"] == net:
            lays = set(l for l, m in (("F", L.F), ("B", L.B)) if p["lay"] & m)
            pads["%s.%s" % (p["ref"], p["num"])] = (p["poly"], (p["x"], p["y"]), lays)
    return pathlen.NetGraph(segs, vias, pads)


def track_index(net, first):
    for k, (layer, pts, w) in enumerate(ROUTES[net]["tracks"]):
        if math.hypot(pts[0][0] - first[0], pts[0][1] - first[1]) < 1e-6:
            return k
    return -1


def pad_len(net, a, b):
    return net_graph(net).path(a, b)[0]


USB_PATHS = (("USB_DP", "U9.27", "U11.8", "USB_DM", "U9.26", "U11.7"),
             ("USBA_DP", "U11.3", "J4.3", "USBA_DM", "U11.4", "J4.2"),
             ("USBC_DP", "U11.1", "J1.A6", "USBC_DM", "U11.2", "J1.A7"),
             ("USBC_DP", "U11.1", "J1.B6", "USBC_DM", "U11.2", "J1.B7"))


def usb_skews():
    out = []
    for p, pa, pb, n, na, nb in USB_PATHS:
        lp, ln = pad_len(p, pa, pb), pad_len(n, na, nb)
        out.append((p, pb, n, nb, lp, ln))
        log("  path %s %s->%s %s / %s %s->%s %s: skew %s" % (p, pa, pb, lp and round(lp, 3), n, na, nb,
                                                           ln and round(ln, 3), lp and ln and round(lp - ln, 3)))
    return out


J1_DP_L4 = [(47.75, 70.90), (47.97, 71.12), (49.75, 71.12)]
J1_DM_L4 = [(51.15, 71.00), (51.15, 71.85), (49.25, 73.75)]


def net_len(net):
    """KiCad-style net length: all tracks of the net (the L3 escape + L4), vias not counted"""
    n = sum(math.hypot(t["b"][0] - t["a"][0], t["b"][1] - t["a"][1]) for t in geo["tracks"] if t["net"] == net)
    for layer, pts, w in ROUTES.get(net, {}).get("tracks", []):
        n += L.plen(pts)
    return n


def find_via(net, near, rmax, step=0.05):
    """the legal via site closest to `near` (within rmax)"""
    best = None
    n = int(rmax / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = near[0] + i * step, near[1] + j * step
            d = math.hypot(x - near[0], y - near[1])
            if d > rmax or (best and d >= best[0]):
                continue
            if S.check_via(net, x, y, novia=GRID_NOVIA):
                best = (d, (round(x, 3), round(y, 3)))
    if not best:
        log("  FAIL %s: no via site within %.2f of %s" % (net, rmax, near))
        FAILS.append((net, ["via site"]))
        return None
    return best[1]


TX_PAIR_END = (23.4, 31.2)
TXN_VIAS = ((22.85, 30.95), (21.9, 28.0))
SD_Y0, SD_PITCH, SD_C0 = 46.95, 0.36, 73.39      # SDMMC bus staircase (first line y, pitch, first diagonal x+y)
SD_XDROP = {"SDMMC_CMD": 18.82}
TXN_U = [(23.60, 25.50), (23.40, 25.30), (21.35, 25.30), (21.15, 25.50), (21.15, 26.125)]
TXP_VIAS = ((22.2, 31.75), (21.2, 28.4))


def selfcheck():
    """re-check every routed segment and via against the final copper (exact geometry)"""
    log("== self-check of all L4 copper against the final board")
    nbad = 0
    for net, R in sorted(ROUTES.items()):
        for layer, pts, w in R["tracks"]:
            lay = L.F if layer == "F" else L.B
            for a, b in zip(pts, pts[1:]):
                bad = S.check_seg(net, lay, tuple(a), tuple(b), w / 2, report=True)
                if bad:
                    nbad += 1
                    log("  FAIL selfcheck %s %s %s-%s: %s" % (net, layer, [round(c, 2) for c in a],
                                                           [round(c, 2) for c in b], bad[:2]))
        for (x, y) in R["vias"]:
            if not S.check_via(net, x, y, self_ok=True, own_pad_ok=True):
                nbad += 1
                log("  FAIL selfcheck via %s (%.2f, %.2f)" % (net, x, y))
    log("  self-check: %d violations" % nbad)


def main():
    only = os.environ.get("L4_JOBS")          # debugging aid: run the first jobs only (comma list of stop names)
    setup_novia()
    setup_sw_areas()
    steps = [("xtal", jobs_xtal), ("eth", jobs_eth), ("usb", jobs_usb), ("sd", jobs_sd), ("nand", jobs_nand),
             ("match", lambda: (match_bus(["SDMMC_CMD", "SDMMC_D0", "SDMMC_D1", "SDMMC_D2", "SDMMC_D3"],
                                          ["SDMMC_CLK", "SDMMC_CLK_SD"], gname="SD"),
                                match_bus(["FSPI_D0", "FSPI_D1", "FSPI_D2", "FSPI_D3", ("FSPI_CS0N", "FSPI_CS0N_NAND")],
                                          ["FSPI_CLK", "FSPI_CLK_NAND"], gname="FSPI"))),
             ("pmu", jobs_pmu), ("subrail", jobs_subrail), ("sense", jobs_sense), ("inner", jobs_inner), ("power", jobs_power), ("stitch", stitch_hops),
             ("guard", crystal_guard_vias)]
    for name, fn in steps:
        if only and name not in only.split(","):
            continue
        fn()
    selfcheck()
    json.dump({"routes": ROUTES, "log": LOG, "fails": FAILS, "stitch": STITCH}, open(OUT, "w"), indent=0)
    log("routes: %d nets, fails %d" % (len(ROUTES), len(FAILS)))


if __name__ == "__main__":
    main()
