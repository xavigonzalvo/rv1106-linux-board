"""Layout phase L5G (D-H7, D-119..D-127) shared geometry: same-layer side-by-side runs of two nets' tracks, and the
via / hole helpers used by l5g_fix.py and l5gcheck.py. Coordinates are board mm (page minus 50, 50)."""
import math

import boardlib as bl

import pcbnew

STEP = 0.05


def segs_of(board, nets=None):
    out = []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        n = t.GetNetname()
        if nets is not None and n not in nets:
            continue
        out.append((n, t.GetLayer(), bl.to_board(t.GetStart()), bl.to_board(t.GetEnd()), pcbnew.ToMM(t.GetWidth()), t))
    return out


def seg_seg(a, b, c, d):
    """distance between segments ab and cd"""
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(bl._seg_pt(a[0], a[1], c[0], c[1], d[0], d[1]), bl._seg_pt(b[0], b[1], c[0], c[1], d[0], d[1]),
               bl._seg_pt(c[0], c[1], a[0], a[1], b[0], b[1]), bl._seg_pt(d[0], d[1], a[0], a[1], b[0], b[1]))


def _seg_key(s):
    a, b = s[2], s[3]
    if (round(b[0], 4), round(b[1], 4)) < (round(a[0], 4), round(a[1], 4)):
        a, b = b, a
    return (s[0], s[1], round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4), round(s[4], 4))


def side_runs(segs_a, segs_b, gap, exempt=None):
    """runs where a track of set A has same-layer copper of a track of set B closer than gap (edge to edge).
    Every A segment is cut into n = ceil(L / STEP) equal pieces, sampled at the piece midpoints (each sample stands for
    L / n of track; the sample set does not depend on the segment direction). Close samples of one (A net, B net,
    layer) are chained along the A net's own path: consecutive samples of a segment, and the end samples of two
    segments whose ends touch (0.003 mm). A run = one chain; its length = the sum of its samples' track lengths.
    The result depends only on the geometry, not on the order of the tracks in the file (L5G round 2, verifier minor).
    exempt(x, y) -> True skips a sample (e.g. inside the U9 pin escape).
    Returns [(net_a, net_b, layer, length mm, min gap mm, (x0, y0), (x1, y1))], longest first, ties by a stable key;
    (x0, y0) / (x1, y1) = the lexicographically smallest / largest sample of the run."""
    by_layer = {}
    for s in sorted(segs_b, key=_seg_key):
        by_layer.setdefault(s[1], []).append(s)
    A = sorted(segs_a, key=_seg_key)
    # samples: per A segment index, list of (x, y, weight, {net_b: gap})
    samp = []
    for k, (na, lay, a, b, wa, _t) in enumerate(A):
        if _seg_key(A[k])[2:4] != (round(a[0], 4), round(a[1], 4)):
            a, b = b, a                      # walk every segment from its canonical first end
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(L / STEP - 1e-9)))
        cand = [s for s in by_layer.get(lay, []) if s[0] != na and
                seg_seg(a, b, s[2], s[3]) - (wa + s[4]) / 2 < gap]
        row = []
        for i in range(n):
            f = (i + 0.5) / n
            x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            hits = {}
            if cand and not (exempt and exempt(x, y)):
                for s in cand:
                    g = bl._seg_pt(x, y, s[2][0], s[2][1], s[3][0], s[3][1]) - (wa + s[4]) / 2
                    if g < gap - 1e-6 and g < hits.get(s[0], 9):
                        hits[s[0]] = g
            row.append((x, y, L / n, hits))
        samp.append((a, b, row))
    # node id = (segment index, sample index); edges along segments and across touching segment ends
    edges = {}

    def link(p, q):
        edges.setdefault(p, []).append(q)
        edges.setdefault(q, []).append(p)
    for k, (a, b, row) in enumerate(samp):
        for i in range(len(row) - 1):
            link((k, i), (k, i + 1))
    for k in range(len(samp)):
        for m in range(k + 1, len(samp)):
            if A[k][0] != A[m][0] or A[k][1] != A[m][1]:
                continue
            ek = ((samp[k][0], 0), (samp[k][1], len(samp[k][2]) - 1))
            em = ((samp[m][0], 0), (samp[m][1], len(samp[m][2]) - 1))
            for pk, ik in ek:
                for pm, im in em:
                    if abs(pk[0] - pm[0]) < 0.003 and abs(pk[1] - pm[1]) < 0.003:
                        link((k, ik), (m, im))
    runs = []
    nets_b = sorted(set(nb for _a, _b, row in samp for _x, _y, _w, h in row for nb in h))
    for nb in nets_b:
        seen = set()
        for k, (_a, _b, row) in enumerate(samp):
            for i, smp in enumerate(row):
                if nb not in smp[3] or (k, i) in seen:
                    continue
                comp, stack = [], [(k, i)]
                seen.add((k, i))
                while stack:
                    node = stack.pop()
                    comp.append(node)
                    for q in edges.get(node, []):
                        if q not in seen and nb in samp[q[0]][2][q[1]][3]:
                            seen.add(q)
                            stack.append(q)
                pts = sorted((samp[c[0]][2][c[1]][0], samp[c[0]][2][c[1]][1], samp[c[0]][2][c[1]][2],
                              samp[c[0]][2][c[1]][3][nb]) for c in comp)
                length = sum(p[2] for p in pts)
                runs.append((A[k][0], nb, A[k][1], length, min(p[3] for p in pts), (pts[0][0], pts[0][1]),
                             (pts[-1][0], pts[-1][1])))
    runs.sort(key=lambda r: (-round(r[3], 6), r[0], r[1], r[2], round(r[5][0], 4), round(r[5][1], 4)))
    return runs


def u9_escape(board, d=1.5):
    """exempt(x, y): inside the U9 courtyard grown by d (the 0.35 mm pin escape, where the pin pitch sets the gap)"""
    c = bl.courtyard_bbox(board.FindFootprintByReference("U9"))
    return lambda x, y: c[0] - d <= x <= c[2] + d and c[1] - d <= y <= c[3] + d


def holes(board):
    """[(kind, ref/net, x, y, radius)] of every drilled hole: vias, PTH pads (round or slot as its centre line)"""
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            x, y = bl.to_board(t.GetPosition())
            out.append(("via", t.GetNetname(), (x, y), (x, y), pcbnew.ToMM(t.GetDrillValue()) / 2))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            ds = p.GetDrillSize()
            if ds.x <= 0:
                continue
            x, y = bl.to_board(p.GetPosition())
            dx, dy = pcbnew.ToMM(ds.x), pcbnew.ToMM(ds.y)
            r = min(dx, dy) / 2
            h = (max(dx, dy) - min(dx, dy)) / 2
            ang = math.radians(p.GetOrientationDegrees())
            if dx >= dy:
                ux, uy = math.cos(ang), -math.sin(ang)
            else:
                ux, uy = math.sin(ang), math.cos(ang)
            a, b = (x - ux * h, y - uy * h), (x + ux * h, y + uy * h)
            kind = "pth" if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else "npth"
            out.append((kind, "%s.%s" % (fp.GetReference(), p.GetNumber()), a, b, r))
    return out


def hole_gap(h1, h2):
    return seg_seg(h1[2], h1[3], h2[2], h2[3]) - h1[4] - h2[4]
