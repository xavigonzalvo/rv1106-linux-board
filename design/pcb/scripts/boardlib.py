"""Shared helpers for the layout-phase scripts (build_board.py, place.py, check_placement.py).

Run every script with KiCad's bundled Python (pcbnew lives there):
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 <script>

Coordinates: layout.md uses board coordinates in mm with the origin at the board's north-west corner, x east, y south.
On the KiCad page that corner sits at ORIGIN = (50, 50) mm (kicad-guide.md step 5, decision D-100); the helpers below
convert between the two.
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PCB_DIR = os.path.normpath(os.path.join(HERE, ".."))
DESIGN = os.path.normpath(os.path.join(PCB_DIR, ".."))
NETLIST = os.path.join(DESIGN, "schematic", "out", "board.net")
LAYOUT = os.path.join(DESIGN, "layout")
BOARD_PRETTY = os.path.join(PCB_DIR, "board.pretty")
STOCK_FP = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PROJECT = "rv1106-reva"
BOARD_FILE = os.environ.get("PCB_BOARD") or os.path.join(PCB_DIR, PROJECT + ".kicad_pcb")   # PCB_BOARD: checker mutation tests
PRO_FILE = os.path.join(PCB_DIR, PROJECT + ".kicad_pro")
DRU_FILE = os.path.join(PCB_DIR, PROJECT + ".kicad_dru")
SRC_PROJECT_DIR = os.path.join(DESIGN, "kicad", PROJECT)   # written by design/tools/make_kicad_project.py

ORIGIN = (50.0, 50.0)   # page position (mm) of board corner (0, 0)  -- D-100


# ---------------------------------------------------------------------------------------------------------------
# s-expression parser (KiCad netlist "D" format). Own code: no kinparse / skidl dependency.
# ---------------------------------------------------------------------------------------------------------------
_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse_sexpr(text):
    """Return nested Python lists; quoted strings and bare atoms both become str."""
    stack, cur, pos = [], [], 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("s-expr syntax error at %d: %r" % (pos, text[pos:pos + 40]))
        pos = m.end()
        lp, rp, q, atom = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif q is not None:
            cur.append(bytes(q, "utf-8").decode("unicode_escape") if "\\" in q else q)
        elif atom is not None:
            cur.append(atom)
    if stack:
        raise ValueError("unbalanced parentheses")
    return cur[0] if len(cur) == 1 else cur


def _child(node, key):
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def _children(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def read_netlist(path=NETLIST):
    """Return (components, nets).
    components: ordered dict ref -> {value, footprint, fields{name: value}}
    nets: list of (code, name, [(ref, pin), ...])"""
    with open(path, encoding="utf-8") as fh:
        tree = parse_sexpr(fh.read())
    comps = {}
    for comp in _children(_child(tree, "components"), "comp"):
        ref = _child(comp, "ref")[1]
        val = _child(comp, "value")
        fpn = _child(comp, "footprint")
        fields = {}
        fl = _child(comp, "fields")
        if fl:
            for fld in _children(fl, "field"):
                name = _child(fld, "name")[1]
                vals = [x for x in fld[1:] if isinstance(x, str)]
                fields[name] = vals[0] if vals else ""
        comps[ref] = dict(value=val[1] if val and len(val) > 1 else "", footprint=fpn[1] if fpn else "",
                          fields=fields)
    nets = []
    for net in _children(_child(tree, "nets"), "net"):
        code = int(_child(net, "code")[1])
        name = _child(net, "name")[1]
        nodes = [(_child(nd, "ref")[1], _child(nd, "pin")[1]) for nd in _children(net, "node")]
        nets.append((code, name, nodes))
    return comps, nets


# ---------------------------------------------------------------------------------------------------------------
# layout CSVs
# ---------------------------------------------------------------------------------------------------------------
def read_csv(name):
    with open(os.path.join(LAYOUT, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def zones():
    """zone name -> row dict with float x0,y0,x1,y1 (board mm)."""
    out = {}
    for r in read_csv("zones.csv"):
        for k in ("x0", "y0", "x1", "y1"):
            r[k] = float(r[k])
        for k in ("origin_x", "origin_y", "rot_deg"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
        out[r["zone"]] = r
    return out


def placement():
    """ref -> placement.csv row"""
    return {r["ref"]: r for r in read_csv("placement.csv")}


_TGT = re.compile(r"SoC pin (\d+) pad at \(([-\d.]+), ([-\d.]+)\) (\w) side")


def target_of(row):
    """(pin, x, y, side) from the placement.csv target column, or None."""
    m = _TGT.search(row.get("target", "") or "")
    if not m:
        return None
    return int(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4)


# ---------------------------------------------------------------------------------------------------------------
# pcbnew helpers (imported lazily so the parser can be used without KiCad)
# ---------------------------------------------------------------------------------------------------------------
def pcbnew():
    import pcbnew as _p
    return _p


def to_page(x, y):
    p = pcbnew()
    return p.VECTOR2I(p.FromMM(ORIGIN[0] + x), p.FromMM(ORIGIN[1] + y))


def to_board(v):
    p = pcbnew()
    return (p.ToMM(v.x) - ORIGIN[0], p.ToMM(v.y) - ORIGIN[1])


def load_footprint(fpid):
    """'Lib:Name' -> FOOTPRINT from the stock libraries or design/pcb/board.pretty."""
    p = pcbnew()
    lib, name = fpid.split(":", 1)
    libdir = BOARD_PRETTY if lib == "board" else os.path.join(STOCK_FP, lib + ".pretty")
    fp = p.FootprintLoad(libdir, name)
    if fp is None:
        raise RuntimeError("footprint not found: %s (%s)" % (fpid, libdir))
    fp.SetFPID(p.LIB_ID(lib, name))
    return fp


def courtyard_bbox(fp):
    """Front courtyard bbox in board mm (x0, y0, x1, y1), or None."""
    p = pcbnew()
    c = fp.GetCourtyard(p.F_CrtYd)
    if c.OutlineCount() == 0:
        return None
    xs, ys = [], []
    for k in range(c.OutlineCount()):         # outline vertices (the DRC courtyard test uses the polygon, not the
        o = c.Outline(k)                      # BBox(), which adds the 0.05 mm line width)
        for i in range(o.PointCount()):
            x, y = to_board(o.CPoint(i))
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


def pad_polygon(pad):
    """Copper outline of a pad on F.Cu as a list of (x, y) board-mm points (convex for rect/roundrect/circle)."""
    p = pcbnew()
    poly = p.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(poly, p.F_Cu, 0, p.FromMM(0.005), p.ERROR_INSIDE)
    pts = []
    if poly.OutlineCount():
        o = poly.Outline(0)
        for i in range(o.PointCount()):
            pts.append(to_board(o.CPoint(i)))
    if not pts:   # NPTH or pad without copper on F.Cu: use the centre
        pts = [to_board(pad.GetPosition())]
    return pts


def _seg_pt(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _inside(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > py) != (by > py) and px < (bx - ax) * (py - ay) / (by - ay + 1e-12) + ax:
            c = not c
    return c


def poly_dist(a, b):
    """Minimum distance between two polygons (0 if they touch/overlap)."""
    if len(a) > 2 and any(_inside(x, y, a) for x, y in b):
        return 0.0
    if len(b) > 2 and any(_inside(x, y, b) for x, y in a):
        return 0.0
    best = 1e9
    for poly1, poly2 in ((a, b), (b, a)):
        n = len(poly2)
        for (px, py) in poly1:
            if n == 1:
                d = ((px - poly2[0][0]) ** 2 + (py - poly2[0][1]) ** 2) ** 0.5
            else:
                d = min(_seg_pt(px, py, *poly2[i], *poly2[(i + 1) % n]) for i in range(n))
            best = min(best, d)
    return best


def edge_dist(pad_a, pad_b):
    """Edge-to-edge copper distance between two pads (board mm): the lower bound of any trace joining them."""
    return poly_dist(pad_polygon(pad_a), pad_polygon(pad_b))


def centre_dist(pad_a, pad_b):
    ax, ay = to_board(pad_a.GetPosition())
    bx, by = to_board(pad_b.GetPosition())
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
