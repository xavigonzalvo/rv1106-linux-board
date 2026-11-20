#!/usr/bin/env python3
"""Layout phase L6 self-check (gate TP-L6, D-132): reads the files l6_fab.py wrote in design/pcb/fab/ and compares them
with the board. Own parsers (plain Python: Gerber RS-274X, Excellon, CSV); numpy + Pillow from design/.venv only for
the raster "Gerber viewer check" images. Board facts come from pcbnew, read by this same file run under KiCad's Python
(--facts) as a subprocess.

    design/.venv/bin/python -I design/pcb/scripts/check_fab.py
        -> design/pcb/fab/check_fab.txt (PASS / FAIL lines + numbers), design/pcb/fab/gerber-view/*.png

Checks: every layer file present with the right X2 file function; Edge.Cuts one closed loop, 90 x 80 mm, origin at the
panel lower-left; copper / mask / paste / silk inside the outline (raster); copper >= 0.8 mm from the V-cut lines on
the board side; V-CUT file = exactly the lines x = 0 / 80 board mm; Excellon hole count per tool (vias, PTH, NPTH,
slots) equals the board and every via hit sits on a board via; no 0.3 mm ComponentDrill; CPL = every assembled ref
exactly once, no not-assembled ref, coordinates = board pad centres (<= 0.01 mm), rotation = KiCad + one correction
per family as in cpl-rotations.md; BOM refs = CPL refs, one row per LCSC number, every row has one, equal to bom.csv;
fiducial mask openings and tooling holes where the board has them; zip = the upload set.
"""
import csv
import json
import math
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
DESIGN = os.path.normpath(os.path.join(PCB, ".."))
FAB = os.environ.get("FAB_DIR") or os.path.join(PCB, "fab")   # FAB_DIR: mutate_fab.py
GERB = os.path.join(FAB, "gerbers")
VIEW = os.path.join(FAB, "gerber-view")
BOARD = os.environ.get("PCB_BOARD") or os.path.join(PCB, "rv1106-reva.kicad_pcb")
KPY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
P = "rv1106-reva-"
LAYERS = {   # file -> (expected TF.FileFunction, short name)
    P + "F_Cu.gtl": ("Copper,L1,Top", "F.Cu"), P + "In1_Cu.g1": ("Copper,L2,Inr", "In1.Cu"),
    P + "In2_Cu.g2": ("Copper,L3,Inr", "In2.Cu"), P + "B_Cu.gbl": ("Copper,L4,Bot", "B.Cu"),
    P + "F_Mask.gts": ("Soldermask,Top", "F.Mask"), P + "B_Mask.gbs": ("Soldermask,Bot", "B.Mask"),
    P + "F_Paste.gtp": ("Paste,Top", "F.Paste"), P + "B_Paste.gbp": ("Paste,Bot", "B.Paste"),
    P + "F_Silkscreen.gto": ("Legend,Top", "F.SilkS"), P + "B_Silkscreen.gbo": ("Legend,Bot", "B.SilkS"),
    P + "Edge_Cuts.gm1": ("Profile,NP", "Edge.Cuts"), P + "V-CUT.gbr": ("Other,User", "V-CUT"),
}
DRILL = {P + "PTH.drl": "Plated,1,4,PTH", P + "NPTH.drl": "NonPlated,1,4,NPTH"}
OTHER = [P + "job.gbrjob", P + "PTH-drl_map.pdf", P + "NPTH-drl_map.pdf", P + "drill-report.txt"]
FAB_FILES = ["jlc-bom.csv", "jlc-bom-not-assembled.csv", "jlc-cpl.csv", "cpl-rotations.md", "order-notes.md",
             "assembly-top-refs.pdf", "assembly-top-values.pdf", "fab-drawing.pdf", "render-3d-top.png",
             "render-3d-bottom.png", "rv1106-reva.d356", "rv1106-reva-jlc-upload.zip"]
PANEL_W, PANEL_H, VCUT_X, VCUT_MIN = 90.0, 80.0, (5.0, 85.0), 0.8
PXMM = 25.0    # raster resolution (px / mm): 0.04 mm pixels


# =====================================================================================================================
# board facts (run under KiCad's Python)
# =====================================================================================================================
def facts():
    import pcbnew
    b = pcbnew.LoadBoard(BOARD)
    a = b.GetDesignSettings().GetAuxOrigin()
    ax, ay = a.x / 1e6, a.y / 1e6

    def f(v):
        return [round(v.x / 1e6 - ax, 5), round(ay - v.y / 1e6, 5)]
    edge = b.GetBoardEdgesBoundingBox()
    out = dict(aux=[ax, ay], edge_min=[edge.GetX() / 1e6, edge.GetY() / 1e6],
               edge_max=[(edge.GetX() + edge.GetWidth()) / 1e6, (edge.GetY() + edge.GetHeight()) / 1e6],
               vias=[], holes=[], fps={})
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            out["vias"].append(f(t.GetPosition()) + [round(t.GetDrillValue() / 1e6, 4)])
    for fp in b.GetFootprints():
        pads = list(fp.Pads())
        xs = [p.GetPosition().x for p in pads]
        ys = [p.GetPosition().y for p in pads]
        c = pcbnew.VECTOR2I(int(round((min(xs) + max(xs)) / 2.0)), int(round((min(ys) + max(ys)) / 2.0)))
        name = str(fp.GetFPID().GetLibItemName())
        out["fps"][fp.GetReference()] = dict(fp=name, rot=round(fp.GetOrientationDegrees() % 360, 3), centre=f(c),
                                             excl_pos=fp.IsExcludedFromPosFiles(), excl_bom=fp.IsExcludedFromBOM(),
                                             dnp=fp.IsDNP(), smd=bool(fp.GetAttributes() & pcbnew.FP_SMD),
                                             tht=bool(fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE),
                                             pads=[[p.GetNumber()] + f(p.GetPosition()) for p in pads])
        for p in pads:
            ds = p.GetDrillSize()
            if ds.x > 0:
                out["holes"].append(dict(ref=fp.GetReference(), pad=p.GetNumber(), xy=f(p.GetPosition()),
                                         dx=round(ds.x / 1e6, 4), dy=round(ds.y / 1e6, 4),
                                         plated=p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
    print(json.dumps(out))


# =====================================================================================================================
# Gerber parser + geometry
# =====================================================================================================================
def _eval(expr, var):
    e = expr.replace("x", "*").replace("X", "*")
    e = re.sub(r"\$(\d+)", lambda m: repr(var.get(int(m.group(1)), 0.0)), e)
    if not re.fullmatch(r"[0-9.+\-*/() e]*", e):
        raise ValueError("macro expression %r" % expr)
    return float(eval(e)) if e.strip() else 0.0


def _rot(pts, deg):
    if not deg:
        return pts
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def _circle_pts(cx, cy, r, n=24):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _capsule(x1, y1, x2, y2, w):
    """stroke of a round aperture: polygon (rectangle) + two circles."""
    r = w / 2.0
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    shapes = [("c", x1, y1, r), ("c", x2, y2, r)]
    if L > 1e-9:
        nx, ny = -dy / L * r, dx / L * r
        shapes.append(("p", [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]))
    return shapes


def aperture_shapes(ap, macros):
    """aperture -> list of (dark, shape) relative to the flash point; shape ('c', x, y, r) or ('p', pts)."""
    kind, params = ap
    if kind == "C":
        return [(True, ("c", 0, 0, params[0] / 2.0))]
    if kind in ("R", "O"):
        w, h = params[0], params[1]
        if kind == "R" or abs(w - h) < 1e-9:
            if kind == "O":
                return [(True, ("c", 0, 0, w / 2.0))]
            return [(True, ("p", [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]))]
        r = min(w, h) / 2.0
        if w > h:
            return [(True, s) for s in _capsule(-(w / 2 - r), 0, w / 2 - r, 0, 2 * r)]
        return [(True, s) for s in _capsule(0, -(h / 2 - r), 0, h / 2 - r, 2 * r)]
    if kind == "P":
        d, n = params[0], int(params[1])
        rot = params[2] if len(params) > 2 else 0
        return [(True, ("p", _rot(_circle_pts(0, 0, d / 2.0, n), rot)))]
    body = macros[kind]
    var = {i + 1: v for i, v in enumerate(params)}
    out = []
    for prim in body:
        prim = prim.strip()
        if not prim or prim.startswith("0"):
            continue
        if prim.startswith("$"):
            k, e = prim.split("=", 1)
            var[int(k[1:])] = _eval(e, var)
            continue
        a = [s.strip() for s in prim.split(",")]
        code = int(a[0])
        v = [_eval(x, var) for x in a[1:]]
        dark = v[0] >= 0.5
        if code == 1:
            rot = v[4] if len(v) > 4 else 0
            (cx, cy), = _rot([(v[2], v[3])], rot)
            out.append((dark, ("c", cx, cy, v[1] / 2.0)))
        elif code == 4:
            n = int(v[1])
            pts = [(v[2 + 2 * i], v[3 + 2 * i]) for i in range(n + 1)]
            out.append((dark, ("p", _rot(pts, v[4 + 2 * n] if len(v) > 4 + 2 * n else 0))))
        elif code == 20:
            w, x1, y1, x2, y2, rot = v[1], v[2], v[3], v[4], v[5], (v[6] if len(v) > 6 else 0)
            L = math.hypot(x2 - x1, y2 - y1) or 1e-9
            nx, ny = -(y2 - y1) / L * w / 2, (x2 - x1) / L * w / 2
            out.append((dark, ("p", _rot([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny),
                                          (x1 - nx, y1 - ny)], rot))))
        elif code == 21:
            w, h, cx, cy, rot = v[1], v[2], v[3], v[4], (v[5] if len(v) > 5 else 0)
            out.append((dark, ("p", _rot([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2),
                                          (cx - w / 2, cy + h / 2)], rot))))
        elif code == 5:
            n, cx, cy, d, rot = int(v[1]), v[2], v[3], v[4], (v[5] if len(v) > 5 else 0)
            out.append((dark, ("p", _rot(_circle_pts(cx, cy, d / 2.0, n), rot))))
        else:
            raise ValueError("macro primitive %d" % code)
    return out


def _arc_pts(x0, y0, x1, y1, cx, cy, cw):
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    r = math.hypot(x0 - cx, y0 - cy)
    if cw:
        while a1 >= a0 - 1e-12:
            a1 -= 2 * math.pi
    else:
        while a1 <= a0 + 1e-12:
            a1 += 2 * math.pi
    if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
        a1 = a0 + (-2 * math.pi if cw else 2 * math.pi)
    n = max(2, int(abs(a1 - a0) / math.radians(5)) + 1)
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(1, n + 1)]


def parse_gerber(path):
    """-> dict(attrs, items=[(dark, shape)], flashes=[(apdef, x, y)], draws=[(apdef, pts)], regions=n)."""
    txt = open(path).read()
    attrs, macros, aps = {}, {}, {}
    items, flashes, draws = [], [], []
    fs = (4, 6)
    unit = None
    x = y = 0.0
    interp, quad, region, dark = "G01", None, False, True
    cur = None
    contour, nregions = [], 0
    pos = 0
    n = len(txt)
    while pos < n:
        ch = txt[pos]
        if ch in "\r\n ":
            pos += 1
            continue
        if ch == "%":
            end = txt.index("%", pos + 1)
            block = txt[pos + 1:end]
            pos = end + 1
            if block.startswith("AM"):
                parts = block.split("*")
                macros[parts[0][2:]] = [p for p in parts[1:] if p.strip()]
                continue
            for cmd in [c for c in block.split("*") if c]:
                if cmd.startswith("FSLA"):
                    m = re.match(r"FSLAX(\d)(\d)Y(\d)(\d)", cmd)
                    fs = (int(m.group(1)), int(m.group(2)))
                elif cmd.startswith("MO"):
                    unit = cmd[2:]
                elif cmd.startswith("TF"):
                    k, _, v = cmd[2:].lstrip(".").partition(",")
                    attrs[k] = v
                elif cmd.startswith("LP"):
                    dark = cmd[2] == "D"
                elif cmd.startswith("ADD"):
                    m = re.match(r"ADD(\d+)([A-Za-z_][A-Za-z0-9_.]*),?(.*)", cmd)
                    params = [float(p) for p in m.group(3).split("X") if p != ""] if m.group(3) else []
                    aps[int(m.group(1))] = (m.group(2), params)
            continue
        end = txt.index("*", pos)
        word = txt[pos:end]
        pos = end + 1
        if word.startswith("G04"):
            continue
        if word in ("M02", "M00"):
            break
        m = re.fullmatch(r"(G0?[123]|G36|G37|G75|G74)?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?(D0?[123]|D\d{2,})?",
                         word)
        if not m:
            raise ValueError("%s: unknown Gerber word %r" % (os.path.basename(path), word))
        g, sx, sy, si, sj, d = m.groups()
        if g in ("G01", "G1"):
            interp = "G01"
        elif g in ("G02", "G2"):
            interp = "G02"
        elif g in ("G03", "G3"):
            interp = "G03"
        elif g == "G75":
            quad = "multi"
        elif g == "G36":
            region, contour = True, []
        elif g == "G37":
            if len(contour) > 2:
                items.append((dark, ("p", contour)))
                nregions += 1
            region, contour = False, []
        if d and int(d[1:]) >= 10:
            cur = int(d[1:])
            continue
        div = 10.0 ** fs[1]
        nx = int(sx) / div if sx is not None else x
        ny = int(sy) / div if sy is not None else y
        if d in ("D01", "D1"):
            if interp == "G01":
                seg = [(x, y), (nx, ny)]
            else:
                cx = x + (int(si) / div if si else 0.0)
                cy = y + (int(sj) / div if sj else 0.0)
                seg = [(x, y)] + _arc_pts(x, y, nx, ny, cx, cy, interp == "G02")
            if region:
                if not contour:
                    contour = [seg[0]]
                contour.extend(seg[1:])
            else:
                ap = aps[cur]
                w = ap[1][0] if ap[0] == "C" else (min(ap[1][:2]) if ap[1] else 0)
                draws.append((ap, seg))
                for (ax_, ay_), (bx_, by_) in zip(seg[:-1], seg[1:]):
                    for s in _capsule(ax_, ay_, bx_, by_, w):
                        items.append((dark, s))
        elif d in ("D02", "D2"):
            if region and len(contour) > 2:
                items.append((dark, ("p", contour)))
                nregions += 1
            contour = [(nx, ny)] if region else []
        elif d in ("D03", "D3"):
            ap = aps[cur]
            flashes.append((ap, nx, ny))
            for dk, s in aperture_shapes(ap, macros):
                if s[0] == "c":
                    items.append((dark == dk, ("c", s[1] + nx, s[2] + ny, s[3])))
                else:
                    items.append((dark == dk, ("p", [(px + nx, py + ny) for px, py in s[1]])))
        x, y = nx, ny
    return dict(attrs=attrs, unit=unit, fs=fs, items=items, flashes=flashes, draws=draws, regions=nregions,
                quad=quad)


def extents(items):
    xs, ys = [], []
    for dark, s in items:
        if not dark:
            continue
        if s[0] == "c":
            xs += [s[1] - s[3], s[1] + s[3]]
            ys += [s[2] - s[3], s[2] + s[3]]
        else:
            xs += [p[0] for p in s[1]]
            ys += [p[1] for p in s[1]]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


# =====================================================================================================================
# raster
# =====================================================================================================================
def raster(items, size, origin=(-2.0, -2.0)):
    from PIL import Image, ImageDraw
    im = Image.new("L", size, 0)
    dr = ImageDraw.Draw(im)
    H = size[1]

    def px(x, y):
        return ((x - origin[0]) * PXMM, H - (y - origin[1]) * PXMM)
    for dark, s in items:
        col = 255 if dark else 0
        if s[0] == "c":
            cx, cy = px(s[1], s[2])
            r = s[3] * PXMM
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        else:
            dr.polygon([px(*p) for p in s[1]], fill=col)
    return im


def outline_loops(draws):
    segs = []
    for ap, pts in draws:
        for a, b in zip(pts[:-1], pts[1:]):
            segs.append((a, b))
    key = lambda p: (round(p[0], 3), round(p[1], 3))  # noqa: E731
    adj = {}
    for a, b in segs:
        adj.setdefault(key(a), []).append((key(b), b))
        adj.setdefault(key(b), []).append((key(a), a))
    odd = [k for k, v in adj.items() if len(v) != 2]
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [k for k, _ in adj[cur] if k != prev and (k not in seen or (k == start and len(loop) > 2))]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            if cur == start:
                break
            seen.add(cur)
            loop.append(cur)
        loops.append(loop)
    return loops, odd, len(segs)


# =====================================================================================================================
# Excellon
# =====================================================================================================================
def parse_excellon(path):
    tools, hits, slots = {}, {}, {}
    attrs, func = {}, None
    cur = None
    metric = False
    for line in open(path):
        line = line.strip()
        if line.startswith("; #@! TF.FileFunction"):
            attrs["FileFunction"] = line.split(",", 1)[1]
        elif line.startswith("; #@! TA.AperFunction"):
            func = line.split(",", 1)[1]
        elif line == "METRIC" or line.startswith("METRIC"):
            metric = True
        m = re.fullmatch(r"T(\d+)C([\d.]+)", line)
        if m:
            tools[int(m.group(1))] = (float(m.group(2)), func)
            continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.fullmatch(r"X(-?[\d.]+)Y(-?[\d.]+)G85X(-?[\d.]+)Y(-?[\d.]+)", line)
        if m:
            slots.setdefault(cur, []).append(tuple(float(v) for v in m.groups()))
            continue
        m = re.fullmatch(r"X(-?[\d.]+)Y(-?[\d.]+)", line)
        if m:
            hits.setdefault(cur, []).append((float(m.group(1)), float(m.group(2))))
    return dict(tools=tools, hits=hits, slots=slots, attrs=attrs, metric=metric)


# =====================================================================================================================
# main check
# =====================================================================================================================
class Rec:
    def __init__(self):
        self.lines = []
        self.nf = 0
        self.np = 0

    def __call__(self, ok, tag, what, got):
        s = "%s %-10s %s: %s" % ("PASS" if ok else "FAIL", tag, what, got)
        self.lines.append(s)
        if ok:
            self.np += 1
        else:
            self.nf += 1
        print(s)


def ref_key(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def main():
    import numpy as np
    from PIL import Image
    rec = Rec()
    r = subprocess.run([KPY, os.path.abspath(__file__), "--facts"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True, env=dict(os.environ, PCB_BOARD=BOARD))
    B = json.loads(r.stdout.strip().splitlines()[-1])
    ax, ay = B["aux"]
    ll = (B["edge_min"][0] + 0.05, B["edge_max"][1] - 0.05)       # Edge.Cuts line width 0.1 mm
    rec(abs(ax - ll[0]) < 1e-6 and abs(ay - ll[1]) < 1e-6, "L6-origin",
        "aux (drill / place) origin = panel lower-left corner of Edge.Cuts",
        "aux page (%.3f, %.3f) mm, Edge.Cuts lower-left (%.3f, %.3f) mm = board (%.1f, %.1f)" % (
            ax, ay, ll[0], ll[1], ax - 50, ay - 50))

    # ---------------------------------------------------------------- files
    missing = [f for f in list(LAYERS) + list(DRILL) + OTHER if not os.path.isfile(os.path.join(GERB, f))]
    missing += [f for f in FAB_FILES if not os.path.isfile(os.path.join(FAB, f))]
    rec(not missing, "L6-files", "every Gerber / drill / job / map / BOM / CPL / PDF / render / netlist / zip file "
        "present", "%d files checked, missing %s" % (len(LAYERS) + len(DRILL) + len(OTHER) + len(FAB_FILES), missing or "none"))
    G = {}
    for f, (ff, short) in LAYERS.items():
        g = parse_gerber(os.path.join(GERB, f))
        G[short] = g
        ok = g["attrs"].get("FileFunction", "").startswith(ff) and g["unit"] == "MM" and g["fs"] == (4, 6)
        e = extents(g["items"])
        rec(ok, "L6-layer", "%s (%s): X2 FileFunction %s, mm, 4.6" % (short, f, ff),
            "FileFunction '%s', unit %s, %d flashes, %d draws, %d regions, extents %s" % (
                g["attrs"].get("FileFunction"), g["unit"], len(g["flashes"]), len(g["draws"]), g["regions"],
                ("x %.3f..%.3f y %.3f..%.3f" % (e[0], e[2], e[1], e[3])) if e else "empty"))
    job = json.load(open(os.path.join(GERB, P + "job.gbrjob")))
    jf = sorted(a["Path"] for a in job["FilesAttributes"])
    rec(sorted(jf) == sorted(LAYERS), "L6-job", "job file lists the 12 Gerbers, 4 layers, 1.6 mm, ENIG",
        "%d files, LayerNumber %s, thickness %s, finish %s, impedance %s" % (
            len(jf), job["GeneralSpecs"]["LayerNumber"], job["GeneralSpecs"]["BoardThickness"],
            job["GeneralSpecs"].get("Finish"), job["GeneralSpecs"].get("ImpedanceControlled")))

    # ---------------------------------------------------------------- outline
    loops, odd, nseg = outline_loops(G["Edge.Cuts"]["draws"])
    allp = [p for lp in loops for p in lp]
    xs = [p[0] for p in allp]
    ys = [p[1] for p in allp]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    rec(len(loops) == 1 and not odd and abs(w - PANEL_W) < 0.005 and abs(h - PANEL_H) < 0.005
        and abs(min(xs)) < 0.005 and abs(min(ys)) < 0.005, "L6-outline",
        "Edge.Cuts: one closed loop, 90 x 80 mm, lower-left at (0, 0)",
        "%d loop(s) from %d pieces (arcs as 5 deg chords), %d open ends; x %.3f..%.3f y %.3f..%.3f = %.3f x %.3f mm" % (
            len(loops), nseg, len(odd), min(xs), max(xs), min(ys), max(ys), w, h))

    # ---------------------------------------------------------------- V-CUT
    vd = G["V-CUT"]["draws"]
    lines = sorted((round(pts[0][0], 4), round(min(pts[0][1], pts[-1][1]), 4), round(pts[-1][0], 4),
                    round(max(pts[0][1], pts[-1][1]), 4)) for _, pts in vd)
    ok = (len(vd) == 2 and not G["V-CUT"]["flashes"] and G["V-CUT"]["regions"] == 0 and
          [ln[0] for ln in lines] == list(VCUT_X) and all(ln[0] == ln[2] and ln[1] == 0 and ln[3] == PANEL_H for ln in lines))
    rec(ok, "L6-vcut", "V-CUT file = exactly two vertical full-height lines at Gerber x = 5 / 85 (board x = 0 / 80)",
        "%d draws, %d flashes, %d regions: %s" % (len(vd), len(G["V-CUT"]["flashes"]), G["V-CUT"]["regions"], lines))

    # ---------------------------------------------------------------- raster: inside outline, V-cut clearance
    os.makedirs(VIEW, exist_ok=True)
    size = (int((PANEL_W + 4) * PXMM), int((PANEL_H + 4) * PXMM))
    poly = [(p[0], p[1]) for p in loops[0]]
    inside = np.array(raster([(True, ("p", poly))], size)) > 127
    inside_grow = np.array(raster([(True, ("p", poly))] + [(True, ("c", p[0], p[1], 0.08)) for p in poly], size)) > 127
    colx = (np.arange(size[0]) + 0.5) / PXMM - 2.0
    composite = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    imgs = {}
    for short, g in G.items():
        im = raster(g["items"], size)
        a = np.array(im) > 127
        imgs[short] = a
        Image.fromarray(np.where(a, 0, 255).astype(np.uint8)).convert("L").save(
            os.path.join(VIEW, "%s.png" % short.replace(".", "_")))
        if short in ("Edge.Cuts", "V-CUT"):
            continue
        outside = int((a & ~inside_grow).sum())
        e = extents(g["items"])
        in_box = e is None or (e[0] >= -1e-6 and e[1] >= -1e-6 and e[2] <= PANEL_W + 1e-6 and e[3] <= PANEL_H + 1e-6)
        rec(outside == 0 and in_box, "L6-inside", "%s: nothing outside the board outline (extents inside 0..90 x "
            "0..80; raster %.2f mm px, outline grown 0.08 mm)" % (short, 1 / PXMM),
            "%d px outside, %d px drawn, extents %s" % (outside, int(a.sum()), (
                "x %.3f..%.3f y %.3f..%.3f" % (e[0], e[2], e[1], e[3])) if e else "empty"))
        if short.endswith("Cu"):
            cols = np.where(a.any(axis=0))[0]
            board_cols = colx[cols][(colx[cols] > VCUT_X[0]) & (colx[cols] < VCUT_X[1])]
            rail_cols = colx[cols][(colx[cols] < VCUT_X[0]) | (colx[cols] > VCUT_X[1])]
            dmin = min(board_cols.min() - VCUT_X[0], VCUT_X[1] - board_cols.max()) - 0.5 / PXMM
            drail = min([VCUT_X[0] - rail_cols[rail_cols < VCUT_X[0]].max() if (rail_cols < VCUT_X[0]).any() else 99,
                         rail_cols[rail_cols > VCUT_X[1]].min() - VCUT_X[1] if (rail_cols > VCUT_X[1]).any() else 99]) - 0.5 / PXMM
            rec(dmin >= VCUT_MIN - 1 / PXMM, "L6-vcutcu", "%s: board copper >= 0.8 mm from the V-cut lines (D-H6), "
                "raster" % short, "board side %.2f mm (west copper from x %.2f, east to x %.2f); rail copper "
                "(fiducials) %.2f mm" % (dmin, board_cols.min(), board_cols.max(), drail if drail < 50 else float('nan')))
    composite[...] = 20
    composite[imgs["F.Cu"]] = (184, 115, 51)
    composite[imgs["F.Mask"] & imgs["F.Cu"]] = (230, 200, 90)
    composite[imgs["F.SilkS"]] = (250, 250, 250)
    composite[imgs["Edge.Cuts"]] = (255, 255, 0)
    composite[imgs["V-CUT"]] = (255, 0, 255)
    Image.fromarray(composite).save(os.path.join(VIEW, "composite_top.png"))

    # ---------------------------------------------------------------- drill
    D = {f: parse_excellon(os.path.join(GERB, f)) for f in DRILL}
    pth, npth = D[P + "PTH.drl"], D[P + "NPTH.drl"]
    for f, ff in DRILL.items():
        rec(D[f]["attrs"].get("FileFunction") == ff and D[f]["metric"] and
            all(t[1] for t in D[f]["tools"].values()), "L6-drillfmt", "%s: X2 FileFunction %s, METRIC, every tool "
            "has a TA.AperFunction" % (f, ff), "FileFunction '%s', metric %s, tools %s" % (
                D[f]["attrs"].get("FileFunction"), D[f]["metric"],
                "; ".join("T%d %.3f %s: %d holes%s" % (t, d, fn.split(",")[-1], len(D[f]["hits"].get(t, [])),
                                                        (" + %d slots" % len(D[f]["slots"][t])) if t in D[f]["slots"] else "")
                          for t, (d, fn) in sorted(D[f]["tools"].items()))))
    via_tools = [t for t, (d, fn) in pth["tools"].items() if fn.endswith("ViaDrill")]
    via_hits = [h for t in via_tools for h in pth["hits"].get(t, [])]
    comp03 = [t for t, (d, fn) in pth["tools"].items() if abs(d - 0.3) < 1e-6 and fn.endswith("ComponentDrill")]
    bvias = B["vias"]
    rec(len(via_hits) == len(bvias) and not comp03 and all(abs(pth["tools"][t][0] - 0.3) < 1e-6 for t in via_tools),
        "L6-vias", "ViaDrill hits = board vias, all 0.3 mm; no 0.3 mm ComponentDrill tool",
        "ViaDrill %d hits (tools %s), board vias %d (drills %s); 0.3 ComponentDrill tools: %d" % (
            len(via_hits), via_tools, len(bvias), sorted(set(v[2] for v in bvias)), len(comp03)))
    bset = sorted((round(v[0], 3), round(v[1], 3)) for v in bvias)
    hset = sorted((round(x, 3), round(y, 3)) for x, y in via_hits)
    far = 0
    import bisect
    for x, y in hset:
        i = bisect.bisect_left(bset, (x - 0.006, -1e9))
        ok = False
        while i < len(bset) and bset[i][0] <= x + 0.006:
            if abs(bset[i][1] - y) <= 0.006:
                ok = True
                break
            i += 1
        far += not ok
    rec(far == 0, "L6-viapos", "every ViaDrill hit sits on a board via (<= 0.006 mm, aux origin)",
        "%d of %d hits without a board via" % (far, len(hset)))

    def board_holes(plated, slot):
        c = {}
        for hh in B["holes"]:
            if hh["plated"] != plated:
                continue
            is_slot = abs(hh["dx"] - hh["dy"]) > 1e-6
            if is_slot != slot:
                continue
            d = round(min(hh["dx"], hh["dy"]), 3)
            c[d] = c.get(d, 0) + 1
        return c

    def file_holes(dd, slot, skip_via=False):
        c = {}
        for t, (d, fn) in dd["tools"].items():
            if skip_via and fn.endswith("ViaDrill"):
                continue
            n = len(dd["slots"].get(t, [])) if slot else len(dd["hits"].get(t, []))
            if n:
                c[round(d, 3)] = c.get(round(d, 3), 0) + n
        return c
    for name, plated, dd in (("PTH", True, pth), ("NPTH", False, npth)):
        bh, fh = board_holes(plated, False), file_holes(dd, False, skip_via=True)
        rec(bh == fh, "L6-holes", "%s round component holes per size: Excellon = board pads" % name,
            "file %s / board %s (total %d / %d)" % (dict(sorted(fh.items())), dict(sorted(bh.items())),
                                                     sum(fh.values()), sum(bh.values())))
        bs, fs_ = board_holes(plated, True), file_holes(dd, True)
        rec(bs == fs_, "L6-slots", "%s slots per width: Excellon (G85) = board oval pads" % name,
            "file %s / board %s" % (dict(sorted(fs_.items())), dict(sorted(bs.items()))))
    th = [hh for hh in B["holes"] if hh["ref"].startswith("TH")]
    npth_hits = [h for t in npth["hits"] for h in npth["hits"][t]]
    th_ok = all(any(abs(x - hh["xy"][0]) < 0.005 and abs(y - hh["xy"][1]) < 0.005 for x, y in npth_hits) for hh in th)
    rec(len(th) == 4 and th_ok and all(abs(hh["dx"] - 2.0) < 1e-6 and not hh["plated"] for hh in th), "L6-tooling",
        "4 tooling holes 2.0 mm NPTH in the NPTH file at the board positions",
        "; ".join("%s (%.2f, %.2f) %.2f mm" % (hh["ref"], hh["xy"][0], hh["xy"][1], hh["dx"]) for hh in sorted(th, key=lambda q: q["ref"])))
    fids = {k: v for k, v in B["fps"].items() if v["fp"].startswith("Fiducial")}
    mfl = [(ap, x, y) for ap, x, y in G["F.Mask"]["flashes"] if ap[0] == "C" and abs(ap[1][0] - 2.0) < 1e-6]
    cfl = [(ap, x, y) for ap, x, y in G["F.Cu"]["flashes"] if ap[0] == "C" and abs(ap[1][0] - 1.0) < 1e-6]
    fok = all(any(abs(x - v["centre"][0]) < 0.005 and abs(y - v["centre"][1]) < 0.005 for _, x, y in mfl) and
              any(abs(x - v["centre"][0]) < 0.005 and abs(y - v["centre"][1]) < 0.005 for _, x, y in cfl)
              for v in fids.values())
    pfl = [(x, y) for _, x, y in G["F.Paste"]["flashes"]]
    nopaste = all(not any(abs(x - v["centre"][0]) < 0.3 and abs(y - v["centre"][1]) < 0.3 for x, y in pfl) for v in fids.values())
    rec(len(fids) == 5 and fok and nopaste, "L6-fid", "5 fiducials: 1.0 mm copper + 2.0 mm mask opening flashed, "
        "no paste", "; ".join("%s (%.2f, %.2f)" % (k, v["centre"][0], v["centre"][1]) for k, v in sorted(fids.items())))
    bp = G["B.Paste"]
    rec(not bp["items"], "L6-bpaste", "B.Paste empty (no bottom parts)", "%d items" % len(bp["items"]))

    # ---------------------------------------------------------------- CPL / BOM
    cpl = list(csv.DictReader(open(os.path.join(FAB, "jlc-cpl.csv"), newline="")))
    bomj = list(csv.DictReader(open(os.path.join(FAB, "jlc-bom.csv"), newline="")))
    nas = list(csv.DictReader(open(os.path.join(FAB, "jlc-bom-not-assembled.csv"), newline="")))
    bomsrc = list(csv.DictReader(open(os.path.join(DESIGN, "bom.csv"), newline="")))
    rec(list(cpl[0].keys()) == ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"] and
        list(bomj[0].keys()) == ["Comment", "Designator", "Footprint", "LCSC Part #"], "L6-cols",
        "CPL / BOM column names as JLC's templates", "CPL %s; BOM %s" % (list(cpl[0].keys()), list(bomj[0].keys())))
    src_refs = set(x for rr in bomsrc for x in rr["ref"].split())
    assembled = sorted([k for k, v in B["fps"].items() if k in src_refs], key=ref_key)
    not_asm = sorted([k for k, v in B["fps"].items() if k not in src_refs], key=ref_key)
    flags_ok = all(not (B["fps"][k]["excl_pos"] or B["fps"][k]["excl_bom"] or B["fps"][k]["dnp"]) for k in assembled) and \
        all(B["fps"][k]["excl_pos"] and B["fps"][k]["excl_bom"] for k in not_asm)
    rec(flags_ok, "L6-flags", "board attributes: bom.csv parts not DNP / excluded; every other footprint excluded "
        "from BOM and position files", "%d assembled, %d not assembled (of %d footprints)" % (
            len(assembled), len(not_asm), len(B["fps"])))
    cref = [rr["Designator"] for rr in cpl]
    dup = sorted(set(x for x in cref if cref.count(x) > 1))
    rec(sorted(cref, key=ref_key) == assembled and not dup and not (set(cref) & set(not_asm)), "L6-cplrefs",
        "CPL holds every assembled ref exactly once and no not-assembled ref",
        "%d rows, %d unique, duplicates %s, missing %s, extra %s, not-assembled refs in CPL %s" % (
            len(cref), len(set(cref)), dup or "none", sorted(set(assembled) - set(cref)) or "none",
            sorted(set(cref) - set(assembled)) or "none", sorted(set(cref) & set(not_asm)) or "none"))
    dmax, worst = 0.0, None
    for rr in cpl:
        c = B["fps"][rr["Designator"]]["centre"]
        d = math.hypot(float(rr["Mid X"]) - c[0], float(rr["Mid Y"]) - c[1])
        if d > dmax:
            dmax, worst = d, rr["Designator"]
    rec(dmax <= 0.01 and all(rr["Layer"] == "Top" for rr in cpl), "L6-cplxy", "CPL Mid X / Mid Y = board pad-bbox centre in the aux origin (<= 0.01 mm)",
        "max deviation %.5f mm (%s); all rows Layer Top: %s" % (dmax, worst, all(rr["Layer"] == "Top" for rr in cpl)))
    # rotation: one correction per footprint, matching cpl-rotations.md
    corr = {}
    for rr in cpl:
        fpv = B["fps"][rr["Designator"]]
        corr.setdefault(fpv["fp"], set()).add(round((float(rr["Rotation"]) - fpv["rot"]) % 360, 3))
    md = open(os.path.join(FAB, "cpl-rotations.md")).read()
    mdcorr = {}
    for line in md.splitlines():
        m = re.match(r"\| [^|]+ \| ([^|]+) \| [^|]+ \| [^|]+ \| \*\*([+-]\d+)°\*\* \|", line)
        if m:
            for fpn in m.group(1).split(", "):
                mdcorr[fpn.strip()] = int(m.group(2)) % 360
    bad = {k: sorted(v) for k, v in corr.items() if len(v) != 1 or mdcorr.get(k) != list(v)[0]}
    rec(not bad and set(mdcorr) == set(corr), "L6-cplrot", "CPL rotation = KiCad rotation + one correction per "
        "footprint, equal to the cpl-rotations.md family table",
        "%d footprints: %s; mismatches %s" % (len(corr), ", ".join("%s %+d" % (k, list(v)[0]) for k, v in sorted(corr.items())
                                                                  if list(v)[0]), bad or "none"))
    nlisted = len(re.findall(r"^\| \d+ \| ", md, re.M))
    polar_need = [rr["Designator"] for rr in cpl if not re.match(r"^(R_|C_0|L_0603|Fuse_|L_FHD|Crystal_SMD_3215)",
                                                                  B["fps"][rr["Designator"]]["fp"])]
    listed = set(re.findall(r"^\| \d+ \| (\w+) \|", md, re.M))
    rec(set(polar_need) == listed, "L6-cplpol", "every orientation-sensitive part (ICs, diodes, LEDs, C35, Q, "
        "crystals 4-pad, switches, connectors, U9) listed once in cpl-rotations.md", "%d listed (%d rows), expected %d; "
        "missing %s" % (len(listed), nlisted, len(polar_need), sorted(set(polar_need) - listed) or "none"))
    brefs = [x for rr in bomj for x in rr["Designator"].split(",")]
    lcsc = [rr["LCSC Part #"] for rr in bomj]
    rec(sorted(brefs, key=ref_key) == sorted(cref, key=ref_key) and len(brefs) == len(set(brefs)), "L6-bomrefs",
        "BOM designators = CPL designators, each once", "%d BOM refs, %d CPL refs, symmetric difference %s" % (
            len(brefs), len(cref), sorted(set(brefs) ^ set(cref)) or "none"))
    rec(all(re.fullmatch(r"C\d+", x) for x in lcsc) and len(lcsc) == len(set(lcsc)) and len(bomj) == len(bomsrc),
        "L6-lcsc", "every BOM row has one LCSC number, one row per unique part, rows = bom.csv rows",
        "%d rows (bom.csv %d), %d unique LCSC numbers, empty %d" % (len(bomj), len(bomsrc), len(set(lcsc)),
                                                                   sum(1 for x in lcsc if not x)))
    srcmap = {x: rr["lcsc"] for rr in bomsrc for x in rr["ref"].split()}
    mism = [x for rr in bomj for x in rr["Designator"].split(",") if srcmap.get(x) != rr["LCSC Part #"]]
    rec(not mism, "L6-bomsrc", "every BOM ref has the bom.csv LCSC number", "mismatches %s" % (mism or "none"))
    nref = [rr["Designator"] for rr in nas]
    rec(sorted(nref, key=ref_key) == not_asm and not (set(nref) & set(brefs)), "L6-dnp",
        "not-assembled list = board footprints without a part, disjoint from the BOM",
        "%d listed: %d TP, %d fiducial, %d holes, others %s" % (
            len(nref), sum(1 for x in nref if x.startswith("TP")), sum(1 for x in nref if "FID" in x),
            sum(1 for x in nref if re.match(r"^(H|TH)\d", x)),
            [x for x in nref if not re.match(r"^(TP|GFID|FID|H|TH)\d", x)]))

    # ---------------------------------------------------------------- zip
    z = zipfile.ZipFile(os.path.join(FAB, "rv1106-reva-jlc-upload.zip"))
    names = sorted(z.namelist())
    want = sorted(list(LAYERS) + list(DRILL) + [P + "job.gbrjob"])
    same = all(z.read(nm) == open(os.path.join(GERB, nm), "rb").read() for nm in names if nm in want)
    rec(names == want and same and z.testzip() is None, "L6-zip", "upload zip = 12 Gerbers + 2 Excellon + job file, "
        "byte-identical to gerbers/", "%d entries, identical %s, extra %s, missing %s" % (
            len(names), same, sorted(set(names) - set(want)) or "none", sorted(set(want) - set(names)) or "none"))
    out = ["check_fab (TP-L6): %d PASS, %d FAIL" % (rec.np, rec.nf)] + rec.lines
    open(os.path.join(FAB, "check_fab.txt"), "w").write("\n".join(out) + "\n")
    print(out[0])
    return 1 if rec.nf else 0


if __name__ == "__main__":
    if "--facts" in sys.argv:
        facts()
    else:
        sys.exit(main())
