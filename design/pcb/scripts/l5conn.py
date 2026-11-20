"""Connectivity of one net in an l4_export geometry (design/.venv or any Python): union-find over the net's pads, track
segments and vias, the way KiCad joins them (a track end inside a pad of the same layer, a track end on another track
of the same layer, a via inside a pad or on a track end). Used by l5_priority.py to find the pieces of a net that are
not joined yet and by l5_priority.py's self-report.

    comps = components(geo, net, extra_routes)   # list of dicts {"pads": [(ref, num)], "vias": [(x, y)],
                                                 #                "ends": [(x, y, layer)], "segs": [...]}
"""
import math


def _inside(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def components(geo, net, extra=None):
    """extra: {"tracks": [[layer, pts, w]], "vias": [[x, y]]} of the net not in geo yet"""
    pads = [p for p in geo["pads"] if p["net"] == net]
    segs = [(t["layer"], tuple(t["a"]), tuple(t["b"]), t["w"]) for t in geo["tracks"] if t["net"] == net]
    vias = [(v["x"], v["y"], v["d"]) for v in geo["vias"] if v["net"] == net]
    if extra:
        for lay, pts, w in extra.get("tracks", []):
            for a, b in zip(pts, pts[1:]):
                segs.append((lay, tuple(a), tuple(b), w))
        for v in extra.get("vias", []):
            vias.append((v[0], v[1], 0.5))
    nodes = [("pad", i) for i in range(len(pads))] + [("seg", i) for i in range(len(segs))] + \
        [("via", i) for i in range(len(vias))]
    idx = {n: k for k, n in enumerate(nodes)}
    par = list(range(len(nodes)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    def pad_on(p, lay):
        return p["th"] or lay in p["layers"]

    for i, (lay, a, b, w) in enumerate(segs):
        for j, p in enumerate(pads):
            if pad_on(p, lay) and (_inside(a[0], a[1], p["poly"]) or _inside(b[0], b[1], p["poly"])):
                union(idx[("seg", i)], idx[("pad", j)])
        for k in range(i + 1, len(segs)):
            l2, c, d, w2 = segs[k]
            if l2 != lay:
                continue
            tol = (w + w2) / 2 * 0.5 + 1e-3
            if min(_pt_seg(a, c, d), _pt_seg(b, c, d), _pt_seg(c, a, b), _pt_seg(d, a, b)) <= tol:
                union(idx[("seg", i)], idx[("seg", k)])
        for k, (x, y, dd) in enumerate(vias):
            if min(_pt_seg((x, y), a, b), math.hypot(a[0] - x, a[1] - y), math.hypot(b[0] - x, b[1] - y)) <= dd / 2:
                union(idx[("seg", i)], idx[("via", k)])
    for k, (x, y, dd) in enumerate(vias):
        for j, p in enumerate(pads):
            if _inside(x, y, p["poly"]):
                union(idx[("via", k)], idx[("pad", j)])
    for j, p in enumerate(pads):          # pads that overlap (none expected; e.g. net-tie halves)
        for j2 in range(j + 1, len(pads)):
            q = pads[j2]
            if p["ref"] == q["ref"] and p["num"] == q["num"]:
                union(idx[("pad", j)], idx[("pad", j2)])
    groups = {}
    for n, k in idx.items():
        groups.setdefault(find(k), []).append(n)
    out = []
    for g in groups.values():
        c = {"pads": [], "vias": [], "segs": [], "ends": []}
        for kind, i in sorted(g):
            if kind == "pad":
                c["pads"].append((pads[i]["ref"], pads[i]["num"]))
            elif kind == "via":
                c["vias"].append(vias[i][:2])
            else:
                c["segs"].append(segs[i])
        # free track ends (a candidate start point): an end that touches nothing else of the net
        for (lay, a, b, w) in c["segs"]:
            for p in (a, b):
                deg = sum(1 for (l2, c2, d2, w2) in c["segs"] if l2 == lay and
                          (math.hypot(p[0] - c2[0], p[1] - c2[1]) < 1e-3 or math.hypot(p[0] - d2[0], p[1] - d2[1]) < 1e-3))
                inpad = any(_inside(p[0], p[1], q["poly"]) for q in pads if pad_on(q, lay))
                if deg == 1 and not inpad:
                    c["ends"].append((p[0], p[1], lay))
        c["pads"].sort()
        c["vias"].sort()
        c["ends"].sort()
        out.append(c)
    out.sort(key=lambda c: (-len(c["pads"]) - len(c["segs"]), c["pads"], c["vias"]))
    return out
