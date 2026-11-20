"""Courtyard sizes for the Phase 7 floor-plan capacity check (layout.md §5.1, D-84 round 2).

Library footprints: the F.CrtYd bounding box is read from the cached KiCad .kicad_mod files (downloaded data, parsed as
text only; run the tools with python -I). Custom `board:` footprints (D-74, not drawn yet): a rectangle from the part
drawing, listed in CUSTOM with its source. Public functions:
  courtyard_bbox(footprint)              -> (x0, y0, x1, y1) in footprint coordinates (mm, y down)
  courtyard_area(footprint)              -> mm^2
  placed_rect(footprint, x, y, rot_deg)  -> board rectangle of the courtyard for a footprint origin at (x, y), rotated
                                           rot_deg counter-clockwise (KiCad convention, y grows downwards)
  pad_extent(footprint)                  -> (x0, y0, x1, y1) of the SMD/THT pads (for edge checks)
  fab_bbox(footprint), pad_xy(footprint, name), place_point(x, y, ox, oy, rot_deg)
"""
import math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(HERE), "refs")
CACHE_DIRS = [os.path.join(REFS, "kicad-footprints-mods-2026-10-29"), os.path.join(REFS, "kicad-footprints-p6-2026-10-29")]

# Custom footprints (drawn in H1, D-74). Rectangle = land-pattern/body extent + 0.25 mm courtyard margin per side
# (IPC-7351 nominal), centred on the footprint origin. Values are what the capacity check uses; the H1 drawing must
# not be larger (layout.md §6.4).
CUSTOM = {
    "board:RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm": (
        13.5, 13.5, "pads to +-6.45 mm (layout.md §6.1, [DS] r1.8 Fig. 2-5 p.17) + 0.30 mm"),
    "board:SW_TS-1187A_5.1x5.1mm": (
        7.5, 5.6, "refs/ts-1187a-datasheet p.1 'P.C.B LAYOUT TOP VIEW': pads span 7.0 x 4.5 mm, body 5.1 x 5.1 mm; "
                  "+0.25 mm"),
    "board:L_FHD4020S_4.0x4.0mm": (
        4.6, 4.6, "body 4.0 x 4.0 mm (refs/fhd4020s-datasheet, image-only drawing); pads assumed inside the body "
                  "outline + 0.3 mm (ESTIMATE, UNVERIFIED until drawn in H1)"),
    "board:TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm": (
        2.4, 2.9, "body 1.5 x 2.0 mm (refs/ts3usb221a-datasheet RSE0010A); land pattern assumed <= 1.9 x 2.4 mm "
                  "+ 0.25 mm (ESTIMATE)"),
    "board:microSD_TF-01A": (
        16.0, 15.0, "body 14.50 x 15.35 mm (refs/tf-01a-datasheet p.1) incl. shell tabs; zone J2-SD of zones.csv"),
    "board:USB_A_AF90_WJDG_RightAngle_THT": (
        15.5, 15.0, "legs 15.30 wide, 14.20 deep (refs/usb-a-af90-wjdg-datasheet p.1); zone J4-USBA of zones.csv"),
}

_cache = {}


def _tokens(txt):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', txt)


def _parse(tokens):
    stack, cur = [], []
    for t in tokens:
        if t == "(":
            stack.append(cur); cur = []
        elif t == ")":
            done = cur; cur = stack.pop(); cur.append(done)
        else:
            cur.append(t.strip('"'))
    return cur[0]


def _find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            yield c


def _mod_path(footprint):
    lib, name = footprint.split(":", 1)
    for d in CACHE_DIRS:
        p = os.path.join(d, f"{lib}__{name}.kicad_mod")
        if os.path.isfile(p):
            return p
    return None


def _load(footprint):
    if footprint in _cache:
        return _cache[footprint]
    p = _mod_path(footprint)
    if p is None:
        raise KeyError(f"footprint {footprint} is neither cached nor in CUSTOM")
    with open(p, encoding="utf-8") as fh:
        tree = _parse(_tokens(fh.read()))
    _cache[footprint] = tree
    return tree


def _pts(item):
    if item[0] == "fp_circle":
        cx, cy = (float(v) for v in next(_find(item, "center"))[1:3])
        ex, ey = (float(v) for v in next(_find(item, "end"))[1:3])
        r = math.hypot(ex - cx, ey - cy)
        return [(cx - r, cy - r), (cx + r, cy + r)]
    pts = []
    for key in ("start", "end", "center", "mid"):
        for c in _find(item, key):
            pts.append((float(c[1]), float(c[2])))
    for c in _find(item, "pts"):
        for xy in _find(c, "xy"):
            pts.append((float(xy[1]), float(xy[2])))
    return pts


def _layer_bbox(footprint, layer):
    tree = _load(footprint)
    pts = []
    for item in tree:
        if isinstance(item, list) and item and item[0] in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
            if any(c[1] == layer for c in _find(item, "layer")):
                pts += _pts(item)
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def fab_bbox(footprint):
    """Body outline (F.Fab) bounding box, footprint coordinates; None for custom footprints."""
    return None if footprint in CUSTOM else _layer_bbox(footprint, "F.Fab")


def pad_xy(footprint, name):
    """Footprint coordinates of every pad called `name`."""
    return [(float(next(_find(p, "at"))[1]), float(next(_find(p, "at"))[2]))
            for p in _find(_load(footprint), "pad") if p[1] == name]


def place_point(x, y, ox, oy, rot_deg):
    rx, ry = _rot(x, y, rot_deg)
    return (round(rx + ox, 3), round(ry + oy, 3))


def courtyard_bbox(footprint):
    if footprint in CUSTOM:
        w, h, _ = CUSTOM[footprint]
        return (-w / 2, -h / 2, w / 2, h / 2)
    bb = _layer_bbox(footprint, "F.CrtYd")
    if bb is None:  # e.g. NetTie-2_SMD_Pad2.0mm has no courtyard: pad extent + 0.25 mm
        x0, y0, x1, y1 = pad_extent(footprint)
        return (x0 - 0.25, y0 - 0.25, x1 + 0.25, y1 + 0.25)
    return bb


def courtyard_area(footprint):
    x0, y0, x1, y1 = courtyard_bbox(footprint)
    return (x1 - x0) * (y1 - y0)


def pad_extent(footprint):
    tree = _load(footprint)
    xs, ys = [], []
    for pad in _find(tree, "pad"):
        at = next(_find(pad, "at")); size = next(_find(pad, "size"))
        x, y = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        w, h = float(size[1]), float(size[2])
        if round(rot) % 180 == 90:
            w, h = h, w
        xs += [x - w / 2, x + w / 2]; ys += [y - h / 2, y + h / 2]
    return (min(xs), min(ys), max(xs), max(ys))


def _rot(x, y, deg):
    t = math.radians(deg)
    return (x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t))


def placed(bbox, ox, oy, rot_deg):
    x0, y0, x1, y1 = bbox
    c = [_rot(x, y, rot_deg) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    xs, ys = [p[0] + ox for p in c], [p[1] + oy for p in c]
    return (round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3))


def placed_rect(footprint, ox, oy, rot_deg):
    return placed(courtyard_bbox(footprint), ox, oy, rot_deg)
