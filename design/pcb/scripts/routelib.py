"""Shared helpers for the routing-phase scripts (L3+): planes.py, route_escape.py, route_planevias.py, fill_zones.py,
check_routing.py.

Everything is in board mm (origin = board NW corner, y south; boardlib.to_page/to_board convert). The obstacle model
below is our own geometry (segments with half-width, convex pad polygons, circles), used to *place* copper legally;
KiCad DRC (kicad-cli) is the judge afterwards.
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402

VIA_D, VIA_DRILL = 0.50, 0.30          # layout.md §3 (D-86)
HOLE_PITCH = 0.75                      # via centre to via centre: hole-to-hole 0.45 + 0.30 drill
HOLE_CLEAR = 0.25                      # board setup "hole clearance" (copper to hole edge)
FAN_H = 7.90                           # U9_FAN rule area half size (D-107)
LAYERS = ("F", "In1", "In2", "B")
PLANE_NETS = ("GND", "VDD_0V9", "VCC_3V3", "VCC5V0_SYS", "VBUS_USBA")
L3_NETS = ("VDD_0V9", "VCC_3V3", "VCC5V0_SYS", "VBUS_USBA")
PCB_PLANES = os.path.join(bl.PCB_DIR, "planes.csv")       # as-built L3 plan (recomputed from the placement, D-109)
TRIAL_RESULT = os.path.join(bl.PCB_DIR, "trial", "result_policy.json")


def pcbnew():
    import pcbnew as _p
    return _p


def layer_id(name):
    p = pcbnew()
    return {"F": p.F_Cu, "In1": p.In1_Cu, "In2": p.In2_Cu, "B": p.B_Cu}[name]


def rules():
    return esc.net_rules()


# ---------------------------------------------------------------------------------------------------------------
# board writing
# ---------------------------------------------------------------------------------------------------------------
def net_item(board, name):
    ni = board.FindNet(name)
    if ni is None:
        raise KeyError(name)
    return ni


def add_track(board, net, layer, pts, w):
    p = pcbnew()
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        if math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-4:
            continue
        t = p.PCB_TRACK(board)
        t.SetStart(bl.to_page(*a))
        t.SetEnd(bl.to_page(*b))
        t.SetWidth(p.FromMM(w))
        t.SetLayer(layer_id(layer))
        t.SetNet(net_item(board, net))
        board.Add(t)
        out.append(t)
    return out


def add_via(board, net, x, y):
    p = pcbnew()
    v = p.PCB_VIA(board)
    v.SetPosition(bl.to_page(x, y))
    v.SetViaType(p.VIATYPE_THROUGH)
    v.SetLayerPair(p.F_Cu, p.B_Cu)
    v.SetDrill(p.FromMM(VIA_DRILL))
    try:
        v.SetWidth(p.FromMM(VIA_D))
    except TypeError:
        v.SetWidth(p.F_Cu, p.FromMM(VIA_D))
    v.SetNet(net_item(board, net))
    board.Add(v)
    return v


def require_fresh(board, name):
    """Scripts own their copper through a board group. pcbnew's Python Remove() corrupts the SWIG wrappers in KiCad
    10.0.7 (seen here), so a script never edits its own earlier output: if its group exists it stops and asks for
    scripts/rebuild_all.sh, which rebuilds the board from the netlist in order."""
    for g in board.Groups():
        if g.GetName() == name:
            sys.exit("%s is already on the board: run design/pcb/scripts/rebuild_all.sh (rebuilds from scratch)" % name)


def group(board, name, items):
    p = pcbnew()
    g = p.PCB_GROUP(board)
    g.SetName(name)
    board.Add(g)
    for it in items:
        g.AddItem(it)
    return g


# ---------------------------------------------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------------------------------------------
def pt_seg(px, py, ax, ay, bx, by):
    return bl._seg_pt(px, py, ax, ay, bx, by)


def seg_seg(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)) and o1 * o2 < 0 and o3 * o4 < 0:
        return 0.0
    return min(pt_seg(*a, *c, *d), pt_seg(*b, *c, *d), pt_seg(*c, *a, *b), pt_seg(*d, *a, *b))


def inside(px, py, poly):
    return bl._inside(px, py, poly)


def seg_poly(a, b, poly):
    if inside(a[0], a[1], poly) or inside(b[0], b[1], poly):
        return 0.0
    n = len(poly)
    return min(seg_seg(a, b, poly[i], poly[(i + 1) % n]) for i in range(n))


def pt_poly(p, poly):
    if len(poly) > 2 and inside(p[0], p[1], poly):
        return 0.0
    n = len(poly)
    if n == 1:
        return math.hypot(p[0] - poly[0][0], p[1] - poly[0][1])
    return min(pt_seg(p[0], p[1], *poly[i], *poly[(i + 1) % n]) for i in range(n))


class Shape:
    """kind 'seg' (a, b, half width), 'circle' (c, r) or 'poly' (points). layers: set of LAYERS. Copper or reserve."""
    __slots__ = ("kind", "a", "b", "r", "pts", "layers", "net", "clr", "tag", "bbox", "fan")

    def __init__(self, kind, layers, net, clr, tag, a=None, b=None, r=0.0, pts=None, fan=False):
        self.kind, self.layers, self.net, self.clr, self.tag = kind, set(layers), net, clr, tag
        self.a, self.b, self.r, self.pts, self.fan = a, b, r, pts, fan
        if kind == "seg":
            self.bbox = (min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)
        elif kind == "circle":
            self.bbox = (a[0] - r, a[1] - r, a[0] + r, a[1] + r)
        else:
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            self.bbox = (min(xs), min(ys), max(xs), max(ys))


def shape_dist(s, t):
    """Edge-to-edge distance between two shapes (0 if they overlap)."""
    if s.kind == "poly" and t.kind != "poly":
        s, t = t, s
    if s.kind == "circle":
        if t.kind == "circle":
            d = math.hypot(s.a[0] - t.a[0], s.a[1] - t.a[1])
        elif t.kind == "seg":
            d = pt_seg(s.a[0], s.a[1], *t.a, *t.b)
        else:
            d = pt_poly(s.a, t.pts)
        return d - s.r - t.r
    if s.kind == "seg":
        if t.kind == "circle":
            return pt_seg(t.a[0], t.a[1], *s.a, *s.b) - s.r - t.r
        if t.kind == "seg":
            return seg_seg(s.a, s.b, t.a, t.b) - s.r - t.r
        return seg_poly(s.a, s.b, t.pts) - s.r
    return bl.poly_dist(s.pts, t.pts)


class Space:
    """Spatial hash of copper / reserved shapes."""

    def __init__(self, cell=2.0):
        self.cell = cell
        self.grid = {}
        self.items = []

    def _cells(self, bb):
        c = self.cell
        for i in range(int(math.floor(bb[0] / c)), int(math.floor(bb[2] / c)) + 1):
            for j in range(int(math.floor(bb[1] / c)), int(math.floor(bb[3] / c)) + 1):
                yield (i, j)

    def add(self, s):
        self.items.append(s)
        for k in self._cells(s.bbox):
            self.grid.setdefault(k, []).append(s)

    def near(self, s, margin):
        bb = (s.bbox[0] - margin, s.bbox[1] - margin, s.bbox[2] + margin, s.bbox[3] + margin)
        seen = set()
        for k in self._cells(bb):
            for t in self.grid.get(k, ()):
                if id(t) in seen:
                    continue
                seen.add(id(t))
                if t.bbox[0] > bb[2] or t.bbox[2] < bb[0] or t.bbox[1] > bb[3] or t.bbox[3] < bb[1]:
                    continue
                yield t

    def conflicts(self, s, extra=0.0, ignore_net=True):
        """Shapes of other nets closer than the required clearance (max of both, + extra)."""
        out = []
        for t in self.near(s, 1.0):
            if not (s.layers & t.layers):
                continue
            if ignore_net and s.net and t.net == s.net:
                continue
            need = max(s.clr, t.clr)
            if s.tag == "hole" or t.tag == "hole":
                pass
            elif (s.fan and t.kind != "circle") or (t.fan and s.kind != "circle") or (s.fan and t.fan):
                need = min(need, 0.10)        # DRU "QFN-128 escape neck-down": tracks in the U9 fan
            if (s.fan or t.fan) and (s.kind == "seg" or t.kind == "seg") and "hole" not in (s.tag, t.tag):
                need = min(need, 0.10)
            d = shape_dist(s, t)
            if d < need + extra - 1e-6:
                out.append((t, d, need))
        return out


def hole_hits(sp, seg, margin=0.02):
    """Board 'hole clearance' (0.25 mm copper to hole edge) of a new track segment against the via holes in sp."""
    out = []
    for t in sp.near(seg, 1.0):
        if t.kind == "circle" and t.tag == "via" and t.net != seg.net:
            d = pt_seg(t.a[0], t.a[1], *seg.a, *seg.b) - seg.r - VIA_DRILL / 2
            if d < HOLE_CLEAR + margin:
                out.append((t, d, HOLE_CLEAR))
    return out


def in_fan(x, y):
    return abs(x - esc.CENTRE[0]) <= FAN_H and abs(y - esc.CENTRE[1]) <= FAN_H


def pad_layers(pad):
    p = pcbnew()
    ls = pad.GetLayerSet()
    out = set()
    for nm in LAYERS:
        if ls.Contains(layer_id(nm)):
            out.add(nm)
    if pad.GetAttribute() in (p.PAD_ATTRIB_PTH, p.PAD_ATTRIB_NPTH) and pad.GetDrillSize().x > 0:
        out = set(LAYERS) if pad.GetAttribute() == p.PAD_ATTRIB_PTH else set(LAYERS)
    return out


def class_clear(net, R):
    if not net:
        return 0.15
    return R[net][2] if net in R else 0.15


def board_space(board, R=None, with_tracks=True):
    """Space with every pad, track and via of the board."""
    p = pcbnew()
    R = R or rules()
    sp = Space()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            net = pad.GetNetname()
            lay = pad_layers(pad)
            if pad.GetAttribute() == p.PAD_ATTRIB_NPTH:
                hx, hy = bl.to_board(pad.GetPosition())
                d = p.ToMM(pad.GetDrillSize().x)
                sp.add(Shape("circle", LAYERS, "#NPTH", 0.25, ref, a=(hx, hy), r=d / 2))
                continue
            poly = bl.pad_polygon(pad)
            sh = Shape("poly", lay, net, class_clear(net, R), "%s.%s" % (ref, pad.GetNumber()), pts=poly)
            sp.add(sh)
    # copper graphics inside footprints (the NT1 net-tie bridge): no net, keep 0.25 (board hole clearance)
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() not in (p.F_Cu, p.B_Cu):
                continue
            poly = p.SHAPE_POLY_SET()
            g.TransformShapeToPolygon(poly, g.GetLayer(), 0, p.FromMM(0.005), p.ERROR_INSIDE)
            for k in range(poly.OutlineCount()):
                o = poly.Outline(k)
                pts = [bl.to_board(o.CPoint(i)) for i in range(o.PointCount())]
                if pts:
                    sp.add(Shape("poly", ["F" if g.GetLayer() == p.F_Cu else "B"], "#FPCOPPER", 0.25,
                                 fp.GetReference() + ".copper", pts=pts))
    if with_tracks:
        for t in board.GetTracks():
            net = t.GetNetname()
            if t.GetClass() == "PCB_VIA":
                x, y = bl.to_board(t.GetPosition())
                sp.add(Shape("circle", LAYERS, net, class_clear(net, R), "via", a=(x, y), r=p.ToMM(t.GetWidth(p.F_Cu)) / 2))
            else:
                a = bl.to_board(t.GetStart())
                b = bl.to_board(t.GetEnd())
                lay = {p.F_Cu: "F", p.B_Cu: "B", p.In1_Cu: "In1", p.In2_Cu: "In2"}[t.GetLayer()]
                fan = in_fan(*a) or in_fan(*b)
                sp.add(Shape("seg", [lay], net, class_clear(net, R), "track", a=a, b=b, r=p.ToMM(t.GetWidth()) / 2,
                             fan=fan))
    return sp


def trial_reserve(sp, R, skip_nets=()):
    """Reserve the trial-route corridors of the 38 critical nets (D-107/D-108; approved at D-H5) so that plane vias
    and stubs placed in L3 do not block the L4 routes. Diff pairs reserve 0.76 mm (layout.md §10), XTAL 0.30 + 1 mm
    guard handled by pads, others class clearance; + 0.06 mm for the trial's grid tolerance."""
    with open(TRIAL_RESULT, encoding="utf-8") as fh:
        res = json.load(fh)
    n = 0
    for net, r in sorted(res["nets"].items()):
        if net in skip_nets:
            continue
        cls, w, c = R[net]
        clr = 0.76 if cls in ("ETH_DIFF", "USB_DIFF") else c
        for lay, pts in r["segs"]:
            L = "F" if lay == 0 else "B"
            for a, b in zip(pts[:-1], pts[1:]):
                sp.add(Shape("seg", [L], net, clr + 0.06, "trial", a=tuple(a), b=tuple(b), r=w / 2))
                n += 1
        for v in r["vias"]:
            sp.add(Shape("circle", LAYERS, net, max(c, 0.2) + 0.06, "trialvia", a=tuple(v), r=VIA_D / 2))
    return n


# ---------------------------------------------------------------------------------------------------------------
# L3 plane plan (design/pcb/planes.csv)
# ---------------------------------------------------------------------------------------------------------------
def read_planes():
    if not os.path.exists(PCB_PLANES):
        return []
    with open(PCB_PLANES, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("x0", "y0", "x1", "y1"):
            r[k] = float(r[k])
        r["priority"] = int(r["priority"])
    return rows


def in_region(net, x, y, margin=0.0, rows=None):
    rows = rows if rows is not None else read_planes()
    for r in rows:
        if r["net"] == net and r["layer"] == "In2" and r["x0"] + margin <= x <= r["x1"] - margin \
                and r["y0"] + margin <= y <= r["y1"] - margin:
            return r["region"]
    return None
