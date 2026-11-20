"""Pad-to-pad copper path lengths (pure Python; used by l4_route.py in design/.venv and by l4check.py in KiCad's Python).

A net's copper is turned into a graph: track end points are nodes (per layer), a track end lying on another track of the
same net and layer splits that track (T junctions), vias join their layers, and every pad is a node joined to the track
ends inside it at the distance end -> pad centre. path() returns the shortest pad-centre -> pad-centre path: its length
(track length + the pad-entry pieces; via barrels not counted, as KiCad's net length) and its track pieces.
Stubs of a two-pin connector join (USB-C A6/B6): stub(a, b, c) = length of the branch to c off the path a -> b.
"""
import heapq
import math

TOL = 2e-3


def _inside(x, y, poly):
    c = False
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay + 1e-12) + ax:
            c = not c
    return c


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy), t


class NetGraph:
    def __init__(self, segs, vias, pads):
        """segs: [(layer, (x, y), (x, y), w)]; vias: [(x, y)]; pads: {name: (poly, (cx, cy), layers)}"""
        ends = []
        for lay, a, b, w in segs:
            ends.append((lay, a))
            ends.append((lay, b))
        pieces = []
        for lay, a, b, w in segs:
            ts = [0.0, 1.0]
            for l2, p in ends:
                if l2 != lay:
                    continue
                d, t = _pt_seg(p, a, b)
                if d < TOL and TOL < t < 1 - TOL:
                    ts.append(t)
            ts = sorted(set(round(t, 9) for t in ts))
            for t0, t1 in zip(ts, ts[1:]):
                p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
                p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
                pieces.append((lay, p0, p1, w))
        self.pieces = pieces
        self.adj = {}
        nodes = {}

        def node(lay, p):
            k = (lay, round(p[0] / TOL), round(p[1] / TOL))
            for dk in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                kk = (lay, k[1] + dk[0], k[2] + dk[1])
                if kk in nodes:
                    return nodes[kk]
            nodes[k] = ("n", lay, p)
            return nodes[k]
        self.node = node
        for i, (lay, p0, p1, w) in enumerate(pieces):
            n0, n1 = node(lay, p0), node(lay, p1)
            L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            self._edge(n0, n1, L, i)
        allnodes = list(nodes.values())
        for (x, y) in vias:
            vn = ("v", round(x, 4), round(y, 4))
            for n in allnodes:
                if math.hypot(n[2][0] - x, n[2][1] - y) < 0.01:
                    self._edge(vn, n, 0.0, None)
        for name, (poly, c, layers) in pads.items():
            pn = ("p", name)
            for n in allnodes:
                if n[1] in layers and _inside(n[2][0], n[2][1], poly):
                    self._edge(pn, n, math.hypot(n[2][0] - c[0], n[2][1] - c[1]), None)

    def _edge(self, a, b, L, i):
        self.adj.setdefault(a, []).append((b, L, i))
        self.adj.setdefault(b, []).append((a, L, i))

    def path(self, pa, pb):
        """shortest path pad pa -> pad pb: (length, [piece indices]) or (None, [])"""
        src, dst = ("p", pa), ("p", pb)
        if src not in self.adj or dst not in self.adj:
            return None, []
        dist = {src: 0.0}
        prev = {}
        h = [(0.0, 0, src)]
        cnt = 1
        while h:
            d, _, n = heapq.heappop(h)
            if n == dst:
                break
            if d > dist.get(n, 1e18):
                continue
            for m, L, i in self.adj.get(n, []):
                if m[0] == "p" and m != dst:
                    continue          # never pass through another pad (pad copper is not a track)
                nd = d + L
                if nd < dist.get(m, 1e18) - 1e-12:
                    dist[m] = nd
                    prev[m] = (n, i)
                    heapq.heappush(h, (nd, cnt, m))
                    cnt += 1
        if dst not in dist:
            return None, []
        out = []
        n = dst
        while n != src:
            n, i = prev[n]
            if i is not None:
                out.append(i)
        return dist[dst], out[::-1]

    def segs_of(self, idx):
        return [self.pieces[i] for i in idx]


def stub(g, a, b, c):
    """length of the branch to pad c off the path pad a -> pad b (tree): (d(a,c) + d(b,c) - d(a,b)) / 2"""
    ab, _ = g.path(a, b)
    ac, _ = g.path(a, c)
    bc, _ = g.path(b, c)
    if None in (ab, ac, bc):
        return None
    return (ac + bc - ab) / 2
