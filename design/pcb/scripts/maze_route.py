#!/usr/bin/env python3
"""Trial router for the critical nets (layout phase L2, verifier L2 round 2): a grid maze router (A*, 2 signal layers).

    design/.venv/bin/python -I design/pcb/scripts/maze_route.py <geometry.json> <result.json> [<render.png>]

The geometry file is written by trial_route.py (KiCad's Python, from the saved board). This script needs numpy/scipy/
matplotlib, which live in design/.venv (KiCad's Python has none of them).

What it does (a feasibility trial, not the final routing):
  * grid 0.05 mm over the 80 x 80 mm board, layer 0 = F.Cu (L1), layer 1 = B.Cu (L4); L2/L3 are planes and not used.
  * every pad of every net is copper (TH pads on both layers); NPTH holes, M3 keep-outs, fiducial mask circles, board
    edges (0.3 mm routed edge, 0.4 mm V-cut) and the U9 fan square are hard keep-outs.
  * pads are hard obstacles at the class clearance (ETH/USB 0.15, SDMMC/FSPI 0.20, XTAL 0.30 mm); other nets' traces
    are soft obstacles at max(own, other) "to other nets" clearance (diff pairs 0.76, XTAL 0.30, SDMMC/FSPI 0.20; pair
    partner: the pair gap; inside the breakout boxes of geometry["breakout"] the class clearance); crystals: no other
    net on L1 within 1.0 mm of the pads of Y1/Y2/C76-C79, nothing on L4 under them (layout.md §4.3).
  * a net may use L4 only if the geometry file allows it (layer policy of decision D-106); a layer change costs 2 mm
    and needs room for a 0.5 mm via pad (+ clearance); L4 steps cost 1.5x.
  * negotiated congestion (PathFinder style): every net is routed by Dijkstra on its window with node costs
    1 + history + present-factor x (inside another net's clearance zone); nets still in conflict are rerouted with a
    rising present factor and a growing history cost, up to 40 iterations. Nets still in conflict at the end are
    reported as not routable at the rules.
Results: per net routed yes/no, length, vias, L4 length, conflicts, the polylines; the PNG shows L1 red, L4 blue, vias
as rings.
Grid error: clearances are checked to within TOL = 0.06 mm (cell-centre distances on the 0.05 mm grid).
"""
import heapq
import json
import math
import sys

import numpy as np
from matplotlib.path import Path
from scipy import ndimage, sparse
from scipy.sparse import csgraph

RES = 0.05
SIZE = 80.0
N1 = int(round(SIZE / RES))
VIA_R = 0.25
VIA_COST_MM = 2.0
L4_FACTOR = 1.5
NECK_W, NECK_C = 0.10, 0.10
XTAL_GUARD = 1.0
TOL = 0.06         # grid tolerance: on the 0.05 mm grid a clearance may come out short by up to 0.06 mm
# D-108: rules that the owner is asked to approve are enforced conservatively (the grid error is added, not
# subtracted), so the exact re-measurement in check_placement.py (segment/polygon geometry) meets them:
#   * TX vs RX separation (geometry "nets"[n]["group"]): traces >= 0.76 mm apart, traces >= 0.76 mm from the other
#     group's pads (J3 pins exempt), everywhere;
#   * vias >= max(class clearance, 0.20 mm) from other-net pads, never inside geometry "no_via" rectangles.
MARGIN = 0.07      # > half a cell diagonal (0.035) + half a diagonal step (0.035)
VIA_PAD_CLR = 0.20
COUPLE = 0.3       # extra cost per cell for an ETH line away from its routed partner (pair coupling, D-108 b)


def to_cell(x, y):
    return int(math.floor(y / RES)), int(math.floor(x / RES))


def poly_cells(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    i0, i1 = max(0, int(min(ys) / RES) - 1), min(N1, int(max(ys) / RES) + 2)
    j0, j1 = max(0, int(min(xs) / RES) - 1), min(N1, int(max(xs) / RES) + 2)
    if i1 <= i0 or j1 <= j0:
        return np.zeros((0,), int), np.zeros((0,), int)
    jj, ii = np.meshgrid(np.arange(j0, j1), np.arange(i0, i1))
    pts = np.column_stack([(jj.ravel() + 0.5) * RES, (ii.ravel() + 0.5) * RES])
    inside = Path(poly).contains_points(pts, radius=1e-9)
    if not inside.any():          # tiny pad: at least the centre cell
        ci, cj = to_cell(sum(xs) / len(xs), sum(ys) / len(ys))
        return np.array([ci]), np.array([cj])
    return ii.ravel()[inside], jj.ravel()[inside]


def circle_cells(x, y, r):
    i0, i1 = max(0, int((y - r) / RES) - 1), min(N1, int((y + r) / RES) + 2)
    j0, j1 = max(0, int((x - r) / RES) - 1), min(N1, int((x + r) / RES) + 2)
    if i1 <= i0 or j1 <= j0:
        return np.zeros((0,), int), np.zeros((0,), int)
    jj, ii = np.meshgrid(np.arange(j0, j1), np.arange(i0, i1))
    m = ((jj + 0.5) * RES - x) ** 2 + ((ii + 0.5) * RES - y) ** 2 <= r * r
    return ii[m], jj[m]


def disk_offsets(r):
    k = int(math.ceil(r / RES))
    out = []
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            if (di * RES) ** 2 + (dj * RES) ** 2 <= (r + RES / 2) ** 2:
                out.append((di, dj))
    return out


class Board:
    def __init__(self, geo):
        self.geo = geo
        self.nets = geo["nets"]
        names = sorted({p["net"] for p in geo["pads"]} | {v["net"] for v in geo["vias"]} | set(self.nets))
        self.nid = {n: i for i, n in enumerate(names)}
        self.nname = names
        nn = len(names)
        # trace clearance group of every net: 1 = 0.76 (diff), 2 = 0.30 (xtal), 3 = other
        self.grp = np.zeros(nn + 1, np.int8)
        for n, d in self.nets.items():
            co = d["co"]
            self.grp[self.nid[n]] = 1 if co >= 0.7 else 2 if co >= 0.29 else 3
        self.pad_lab = [np.full((N1, N1), -1, np.int32) for _ in range(2)]
        self.keep = [np.zeros((N1, N1), bool) for _ in range(2)]
        self.xguard = np.zeros((N1, N1), np.int32) - 1      # crystal-area pads (label = net), layer 0
        self.pad_cells = {}                                  # net -> list of (pad name, [(layer, i, j arrays)])
        self.via_ok_pad = np.zeros((N1, N1), bool)           # any pad cell (no via inside a pad)
        for p in geo["pads"]:
            ii, jj = poly_cells(p["poly"])
            lab = self.nid[p["net"]]
            layers = [0, 1] if p["layers"] == "FB" else [0]
            for L in layers:
                self.pad_lab[L][ii, jj] = lab
            self.via_ok_pad[ii, jj] = True
            if p["ref"] in geo["xguard_refs"]:
                self.xguard[ii, jj] = lab
            self.pad_cells.setdefault(p["net"], []).append(("%s.%s" % (p["ref"], p["num"]), layers, ii, jj,
                                                             p["poly"]))
        # D-108 (b): pads of each separation group (exempt refs excluded)
        self.gpad = {}
        exempt = set(geo.get("sep_pad_exempt", []))
        for p in geo["pads"]:
            g = self.nets.get(p["net"], {}).get("group")
            if g and p["ref"] not in exempt:
                ii, jj = poly_cells(p["poly"])
                self.gpad.setdefault(g, np.zeros((N1, N1), bool))[ii, jj] = True
        self.nforbid = {}
        for f in geo.get("net_forbid", []):
            i0, j0 = to_cell(f["rect"][0], f["rect"][1])
            i1, j1 = to_cell(f["rect"][2], f["rect"][3])
            for n in self.nets:
                if n not in f["allowed"]:
                    self.nforbid.setdefault(n, []).append((i0, i1, j0, j1))
        self.net_novia = {}
        for n, rects in geo.get("net_novia", {}).items():
            m = np.zeros((N1, N1), bool)
            for r in rects:
                i0, j0 = to_cell(r[0], r[1])
                i1, j1 = to_cell(r[2], r[3])
                m[max(0, i0):i1 + 1, max(0, j0):j1 + 1] = True
            self.net_novia[n] = m
        self.novia = np.zeros((N1, N1), bool)
        for r in geo.get("no_via", []):
            i0, j0 = to_cell(r[0], r[1])
            i1, j1 = to_cell(r[2], r[3])
            self.novia[max(0, i0):i1 + 1, max(0, j0):j1 + 1] = True
        for v in geo["vias"]:
            ii, jj = circle_cells(v["x"], v["y"], VIA_R)
            for L in (0, 1):
                self.pad_lab[L][ii, jj] = self.nid[v["net"]]
        # hard keep-outs
        e = geo["edges"]          # x0 x1 y0 y1 of the copper-allowed area
        cx = (np.arange(N1) + 0.5) * RES
        for L in (0, 1):
            k = self.keep[L]
            k[:, (cx < e[0]) | (cx > e[1])] = True
            k[(cx < e[2]) | (cx > e[3]), :] = True
            for h in geo["holes"]:
                ii, jj = circle_cells(h["x"], h["y"], h["r"])
                k[ii, jj] = True
        # no trace under U9 between its pad ring and the exposed pad (0.35 mm-pitch QFN, solder-mask web only)
        if geo.get("no_route_l1"):
            for r in geo["no_route_l1"]:
                i0, j0 = to_cell(r[0], r[1])
                i1, j1 = to_cell(r[2], r[3])
                self.keep[0][i0:i1 + 1, j0:j1 + 1] = True
        self.bk = np.zeros((N1, N1), bool)
        for r in geo.get("breakout", []):
            i0, j0 = to_cell(r[0], r[1])
            i1, j1 = to_cell(r[2], r[3])
            self.bk[max(0, i0):i1 + 1, max(0, j0):j1 + 1] = True
        self.l4_forbid = np.zeros((N1, N1), bool)
        for r in geo["l4_forbid"]:
            i0, j0 = to_cell(r[0], r[1])
            i1, j1 = to_cell(r[2], r[3])
            self.l4_forbid[max(0, i0):i1 + 1, max(0, j0):j1 + 1] = True
        self.neck = np.zeros((N1, N1), bool)
        r = geo["neck"]
        i0, j0 = to_cell(r[0], r[1])
        i1, j1 = to_cell(r[2], r[3])
        self.neck[i0:i1 + 1, j0:j1 + 1] = True

    # -------------------------------------------------------------------------------------------------------------
    def window(self, net, margin):
        pads = self.pad_cells[net]
        ys = np.concatenate([p[2] for p in pads])
        xs = np.concatenate([p[3] for p in pads])
        mg = int(margin / RES)
        return (int(max(0, ys.min() - mg)), int(min(N1, ys.max() + mg + 1)), int(max(0, xs.min() - mg)),
                int(min(N1, xs.max() + mg + 1)))

    def hard(self, net, win):
        """Hard blocks inside win: foreign pads (+clearance), keep-outs, crystal guard, L4 policy. Returns
        ([track-blocked L0, L1], via-blocked)."""
        d = self.nets[net]
        n = self.nid[net]
        hw = d["w"] / 2
        i0, i1, j0, j1 = win
        sl = (slice(i0, i1), slice(j0, j1))
        neck = self.neck[sl]
        cp = max(d["c"], 0.15)
        bt, bv = [], []
        for L in (0, 1):
            pl = self.pad_lab[L][sl]
            Dp = _dist((pl >= 0) & (pl != n), pl.shape)
            t = np.where(neck, Dp < NECK_W / 2 + NECK_C - TOL, Dp < hw + cp - TOL) | self.keep[L][sl]
            v = (Dp < VIA_R + max(cp, VIA_PAD_CLR) + MARGIN) | self.keep[L][sl] | neck | self.via_ok_pad[sl] | \
                self.novia[sl]
            if net in self.net_novia:
                v |= self.net_novia[net][sl]
            g = d.get("group")
            if g:
                om = np.zeros(pl.shape, bool)
                for g2, m in self.gpad.items():
                    if g2 != g:
                        om |= m[sl]
                Dg = _dist(om, pl.shape)
                t |= Dg < hw + d["co"] + MARGIN
                v |= Dg < VIA_R + d["co"] + MARGIN
            if L == 0:
                for (a0, a1, b0, b1) in self.nforbid.get(net, []):
                    a0, a1, b0, b1 = max(a0, i0) - i0, min(a1 + 1, i1) - i0, max(b0, j0) - j0, min(b1 + 1, j1) - j0
                    if a1 > a0 and b1 > b0:
                        t[a0:a1, b0:b1] = True
            if L == 0 and d["cls"] != "XTAL":
                xg = self.xguard[sl]
                Dx = _dist((xg >= 0) & (xg != n), xg.shape)
                t |= Dx < hw + XTAL_GUARD
                v |= Dx < VIA_R + XTAL_GUARD
            if L == 1:
                t |= self.l4_forbid[sl]
                v |= self.l4_forbid[sl]
                if not d["l4"]:
                    t[:] = True
            bt.append(t)
            bv.append(v)
        return bt, bv[0] | bv[1]

    def soft(self, net, win):
        """Cells (per layer) where a trace of `net` would violate the clearance to another net's current trace."""
        d = self.nets[net]
        hw = d["w"] / 2
        i0, i1, j0, j1 = win
        shape = (i1 - i0, j1 - j0)
        neck = self.neck[i0:i1, j0:j1]
        out = []
        for L in (0, 1):
            groups = {}
            for m, r in self.paths.items():
                if m == net or not r.get("cells"):
                    continue
                dm = self.nets[m]
                if m == d.get("partner"):
                    key = ("par", dm["w"] / 2, d["gap"], d["gap"])
                elif d.get("group") and dm.get("group") and d["group"] != dm["group"]:
                    sep = max(d["co"], dm["co"]) + MARGIN + TOL      # TOL is subtracted below
                    key = ("grp", dm["w"] / 2, sep, sep)
                else:
                    key = ("oth", dm["w"] / 2, max(d["co"], dm["co"]), max(d["c"], dm["c"]))
                cl = r["cells"][L]
                if cl is None or not len(cl[0]):
                    continue
                ii, jj = cl[0] - i0, cl[1] - j0
                ok = (ii >= 0) & (ii < shape[0]) & (jj >= 0) & (jj < shape[1])
                if not ok.any():
                    continue
                g = groups.setdefault(key, np.zeros(shape, bool))
                g[ii[ok], jj[ok]] = True
            sm = np.zeros(shape, bool)
            bk = self.bk[i0:i1, j0:j1]
            sv = np.zeros(shape, bool)
            for (kind, hwm, c, cb), mask in groups.items():
                D = _dist(mask, shape)
                cc = np.where(bk, cb, c)
                sm |= np.where(neck, D < NECK_W + NECK_C - TOL, D < hw + cc + hwm - TOL)
                sv |= D < VIA_R + cc + hwm - TOL
            out.append(sm)
            self._softv = sv if L == 0 else (self._softv | sv)
        return out

    # -------------------------------------------------------------------------------------------------------------
    def route_net(self, net, margin, pfac):
        pads = self.pad_cells.get(net, [])
        if len(pads) < 2:
            return dict(ok=True, pads=len(pads), length=0.0, vias=[], l4=0.0, segs=[], missing=[], cells=None)
        win = self.window(net, margin)
        i0, i1, j0, j1 = win
        H, W = i1 - i0, j1 - j0
        N = H * W
        bt, bv = self.hard(net, win)
        sf = self.soft(net, win)
        pad_states = []
        for name, layers, ii, jj, poly in pads:
            st = []
            for L in layers:
                li, lj = ii - i0, jj - j0
                bt[L][li, lj] = False            # own copper is always passable
                st.append(L * N + li * W + lj)
            pad_states.append((name, np.concatenate(st)))
        # D-108 (b): pair coupling for the ETH pairs. Once the partner is routed, a cell farther than the pair pitch
        # (+ 0.25 mm) from the partner's track costs COUPLE extra, so the second line runs beside the first wherever
        # the rules allow (the P/N swaps at the 0R links still split them). The grid router has no pair primitive;
        # this only makes the trial lengths and the uncoupled length representative.
        dn = self.nets[net]
        att = [0.0, 0.0]
        pm = dn.get("partner")
        if dn["cls"] == "ETH_DIFF" and pm in self.paths and self.paths[pm].get("cells"):
            for L in (0, 1):
                cl = self.paths[pm]["cells"][L]
                if cl is None or not len(cl[0]):
                    att[L] = COUPLE
                    continue
                mk = np.zeros((H, W), bool)
                ii, jj = cl[0] - i0, cl[1] - j0
                ok = (ii >= 0) & (ii < H) & (jj >= 0) & (jj < W)
                mk[ii[ok], jj[ok]] = True
                Dm = _dist(mk, (H, W))
                att[L] = COUPLE * (Dm > dn["w"] + dn["gap"] + 0.25)
        cost = []
        for L in (0, 1):
            c = 1.0 + self.hist[L][i0:i1, j0:j1] + pfac * sf[L] + att[L]
            if L:
                c = c * L4_FACTOR
            c = np.where(bt[L], np.inf, c)
            cost.append(c)
        G = _graph(cost, bv, H, W, VIA_COST_MM / RES + pfac * 20.0 * self._softv)
        d = self.nets[net]
        order = list(range(len(pad_states)))
        if d.get("start"):
            k = [i for i, p in enumerate(pad_states) if p[0] == d["start"]]
            if k:
                order.remove(k[0])
                order.insert(0, k[0])
        tree = set(pad_states[order[0]][1].tolist())
        remaining = order[1:]
        res = dict(ok=True, pads=len(pads), length=0.0, vias=[], l4=0.0, segs=[], missing=[])
        allpath = []
        while remaining:
            src = np.sort(np.fromiter(tree, dtype=np.int64))      # stable source order (deterministic ties)
            dist, pred, _srcs = csgraph.dijkstra(G, directed=True, indices=src, return_predecessors=True,
                                                 min_only=True)
            best = None
            for k in remaining:
                st = pad_states[k][1]
                dd = dist[st]
                m = int(np.argmin(dd))
                if np.isfinite(dd[m]) and (best is None or dd[m] < best[0]):
                    best = (dd[m], k, int(st[m]))
            if best is None:
                res["ok"] = False
                res["missing"] = [pad_states[k][0] for k in remaining]
                break
            _, k, s = best
            path = []
            while s >= 0 and s not in tree:
                path.append(s)
                s = int(pred[s])
            if s >= 0:
                path.append(s)
            path.reverse()
            allpath.append(path)
            tree.update(path)
            tree.update(pad_states[k][1].tolist())
            remaining.remove(k)
        # geometry of the result
        cells = [[], []]
        for path in allpath:
            cur, curL = [], None
            for a, b in zip(path, path[1:]):
                La, qa = divmod(a, N)
                Lb, qb = divmod(b, N)
                if La != Lb:
                    yv, xv = divmod(qa, W)
                    res["vias"].append((float((j0 + xv + 0.5) * RES), float((i0 + yv + 0.5) * RES)))
                    for L in (0, 1):
                        for di, dj in self.via_offs[net]:
                            cells[L].append((i0 + yv + di, j0 + xv + dj))
                    continue
                ya, xa = divmod(qa, W)
                yb, xb = divmod(qb, W)
                stp = math.hypot(ya - yb, xa - xb) * RES
                res["length"] += stp
                if La:
                    res["l4"] += stp
            for s in path:
                L, q = divmod(s, N)
                y, x = divmod(q, W)
                cells[L].append((i0 + y, j0 + x))
                pt = (round(float((j0 + x + 0.5) * RES), 3), round(float((i0 + y + 0.5) * RES), 3))
                if L != curL and cur:
                    res["segs"].append((int(curL), cur))
                    cur = []
                curL = L
                cur.append(pt)
            if cur:
                res["segs"].append((int(curL), cur))
        # trace cells inside the net's own pads are copper anyway (the pad is already a hard obstacle with its pad
        # clearance for the other nets): leave them out of the trace used for trace-to-trace clearance
        rc = []
        for L in (0, 1):
            cl = cells[L]
            if not cl:
                rc.append(None)
                continue
            a = np.array(cl, int)
            keep = self.pad_lab[L][a[:, 0], a[:, 1]] != self.nid[net]
            a = a[keep]
            rc.append((a[:, 0], a[:, 1]) if len(a) else None)
        res["cells"] = rc
        res["length"] = round(float(res["length"]), 2)
        res["l4"] = round(float(res["l4"]), 2)
        res["win"] = win
        return res

    def conflicts(self, net):
        """Other nets whose clearance zone this net's trace enters (empty = clean)."""
        r = self.paths.get(net)
        if not r or not r.get("cells"):
            return set()
        win = r["win"]
        i0, i1, j0, j1 = win
        d = self.nets[net]
        hw = d["w"] / 2
        neck = self.neck[i0:i1, j0:j1]
        bad = set()
        for L in (0, 1):
            cl = r["cells"][L]
            if cl is None or not len(cl[0]):
                continue
            mine = np.zeros((i1 - i0, j1 - j0), bool)
            ii, jj = cl[0] - i0, cl[1] - j0
            ok = (ii >= 0) & (ii < i1 - i0) & (jj >= 0) & (jj < j1 - j0)
            mine[ii[ok], jj[ok]] = True
            for m, rm in self.paths.items():
                if m == net or not rm.get("cells") or rm["cells"][L] is None:
                    continue
                dm = self.nets[m]
                if m == d.get("partner"):
                    c = d["gap"]
                elif d.get("group") and dm.get("group") and d["group"] != dm["group"]:
                    c = max(d["co"], dm["co"]) + MARGIN + TOL
                else:
                    c = np.where(self.bk[i0:i1, j0:j1], max(d["c"], dm["c"]), max(d["co"], dm["co"]))
                ci, cj = rm["cells"][L][0] - i0, rm["cells"][L][1] - j0
                okm = (ci >= 0) & (ci < i1 - i0) & (cj >= 0) & (cj < j1 - j0)
                if not okm.any():
                    continue
                other = np.zeros_like(mine)
                other[ci[okm], cj[okm]] = True
                D = _dist(other, other.shape)
                lim = np.where(neck, NECK_W + NECK_C, hw + c + dm["w"] / 2) - TOL - 1e-6
                if (mine & (D < lim)).any():
                    bad.add(m)
        return bad


def _dist(mask, shape):
    if not mask.any():
        return np.full(shape, 1e9)
    return ndimage.distance_transform_edt(~mask) * RES


def _graph(cost, via_blk, H, W, vcost):
    """Directed grid graph (2 layers, 8-neighbour moves, vias) with node costs; returns a CSR matrix."""
    N = H * W
    idx = np.arange(N).reshape(H, W)
    rows, cols, wts = [], [], []
    SQ2 = math.sqrt(2)
    for L in (0, 1):
        c = cost[L]
        fin = np.isfinite(c)
        for dy, dx, ln in ((0, 1, 1.0), (1, 0, 1.0), (1, 1, SQ2), (1, -1, SQ2)):
            ya0, ya1 = 0, H - dy
            xa0, xa1 = max(0, -dx), W - max(0, dx)
            A = (slice(ya0, ya1), slice(xa0, xa1))
            B = (slice(ya0 + dy, ya1 + dy), slice(xa0 + dx, xa1 + dx))
            ok = fin[A] & fin[B]
            if dy and dx:      # no corner cutting
                C1 = (slice(ya0 + dy, ya1 + dy), slice(xa0, xa1))
                C2 = (slice(ya0, ya1), slice(xa0 + dx, xa1 + dx))
                ok &= fin[C1] & fin[C2]
            a = idx[A][ok] + L * N
            b = idx[B][ok] + L * N
            w = ln * (c[A][ok] + c[B][ok]) / 2
            rows += [a, b]
            cols += [b, a]
            wts += [w, w]
        if L == 0:
            v = (~via_blk) & np.isfinite(cost[0]) & np.isfinite(cost[1])
            a = idx[v]
            rows += [a, a + N]
            cols += [a + N, a]
            vc = vcost[v] if isinstance(vcost, np.ndarray) else np.full(a.shape, vcost)
            wts += [vc, vc]
    r = np.concatenate(rows)
    cc = np.concatenate(cols)
    w = np.concatenate(wts)
    return sparse.csr_matrix((w, (r, cc)), shape=(2 * N, 2 * N))


def run(geo, iters=40):
    """Negotiated-congestion routing (PathFinder style): traces of other nets are soft obstacles whose cost rises
    every iteration (present factor) and leaves a history cost where they collided; pads and keep-outs are hard. Nets
    still in conflict after the last iteration are reported as unroutable at the rules."""
    b = Board(geo)
    b.paths = {}
    b.hist = [np.zeros((N1, N1), np.float32) for _ in range(2)]
    b.via_offs = {n: [(di, dj) for di, dj in disk_offsets(max(RES, VIA_R - d["w"] / 2))] for n, d in b.nets.items()}
    order = list(geo["order"])
    todo = list(order)
    pfac = 0.6
    log = []
    for it in range(iters):
        for net in todo:
            r = b.route_net(net, 6.0, pfac)
            if not r["ok"]:
                r = b.route_net(net, 14.0, pfac)
            b.paths[net] = r
        conf = {n: b.conflicts(n) for n in order}
        bad = [n for n in order if conf[n] or not b.paths[n]["ok"]]
        log.append({"iter": it + 1, "rerouted": len(todo), "in_conflict": [n for n in order if conf[n]],
                    "unrouted": [n for n in order if not b.paths[n]["ok"]]})
        print("iteration %d: rerouted %d, conflicts %d, unrouted %d" % (it + 1, len(todo), sum(1 for n in order
              if conf[n]), sum(1 for n in order if not b.paths[n]["ok"])), flush=True)
        if not bad:
            break
        # history cost on the cells where conflicting nets overlap other nets' zones
        for n in order:
            if conf[n] and b.paths[n].get("cells"):
                for L in (0, 1):
                    cl = b.paths[n]["cells"][L]
                    if cl is not None and len(cl[0]):
                        b.hist[L][cl[0], cl[1]] += 1.0
        todo = [n for n in order if n in bad or any(n in conf[m] for m in bad)]
        pfac *= 1.6
    out = {}
    for n in order:
        r = dict(b.paths[n])
        r.pop("cells", None)
        r.pop("win", None)
        r["conflict_with"] = sorted(conf[n])
        if conf[n]:
            r["ok"] = False
        out[n] = r
    return {"nets": out, "order": order, "passes": log}


def render(geo, result, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon
    crit = set(geo["nets"])
    fig, ax = plt.subplots(figsize=(14, 14), dpi=200)
    ax.add_patch(Polygon([(0, 0), (80, 0), (80, 80), (0, 80)], closed=True, fill=False, ec="#444444", lw=0.8))
    for p in geo["pads"]:
        if len(p["poly"]) < 3:
            continue
        col = "#f2b8b8" if p["net"] in crit else "#d8d8d8"
        ax.add_patch(Polygon(p["poly"], closed=True, fc=col, ec="none"))
    for h in geo["holes"]:
        ax.add_patch(Circle((h["x"], h["y"]), h["r"], fc="none", ec="#999999", lw=0.4, ls=":"))
    for v in geo["vias"]:
        ax.add_patch(Circle((v["x"], v["y"]), VIA_R, fc="#bbbbbb", ec="none"))
    for net, r in result["nets"].items():
        w = geo["nets"][net]["w"]
        for L, pts in r["segs"]:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(xs, ys, color="#c0392b" if L == 0 else "#1f5fbf", lw=max(0.6, w * 6), solid_capstyle="round",
                    alpha=0.9, zorder=3 if L == 0 else 2)
        for (x, y) in r["vias"]:
            ax.add_patch(Circle((x, y), VIA_R, fc="white", ec="#1f5fbf", lw=1.0, zorder=4))
        if not r["ok"]:
            for name, layers, ii, jj, poly in []:
                pass
    for p in geo["pads"]:
        if p["net"] in result["nets"] and not result["nets"][p["net"]]["ok"]:
            xs = [q[0] for q in p["poly"]]
            ys = [q[1] for q in p["poly"]]
            ax.add_patch(Circle((sum(xs) / len(xs), sum(ys) / len(ys)), 0.6, fc="none", ec="#e67e22", lw=1.5,
                                zorder=5))
    for lab in geo.get("labels", []):
        ax.text(lab[0], lab[1], lab[2], fontsize=6, color="#333333", ha="center", va="center", zorder=6)
    ax.set_xlim(-1, 81)
    ax.set_ylim(81, -1)
    ax.set_aspect("equal")
    ax.set_title("Trial route of the critical nets (L1 red, L4 blue, vias = rings; orange = unrouted pad)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(png)
    crop = geo.get("crop")
    if crop:
        for name, (x0, y0, x1, y1) in crop.items():
            ax.set_xlim(x0, x1)
            ax.set_ylim(y1, y0)
            fig.savefig(png.replace(".png", "_%s.png" % name))
    plt.close(fig)


def main():
    geo = json.load(open(sys.argv[1]))
    out = run(geo)
    with open(sys.argv[2], "w") as fh:
        json.dump(out, fh)
    if len(sys.argv) > 3:
        render(geo, out, sys.argv[3])
    for net in out["order"]:
        r = out["nets"][net]
        why = ""
        if r["missing"]:
            why = "missing " + " ".join(r["missing"])
        if r.get("conflict_with"):
            why += " clearance conflict with " + " ".join(r["conflict_with"])
        print("%-4s %-16s len %6.2f  vias %d  L4 %5.2f %s" % ("OK" if r["ok"] else "FAIL", net, r["length"],
                                                              len(r["vias"]), r["l4"], why))
    print("passes:", out["passes"])


if __name__ == "__main__":
    main()
