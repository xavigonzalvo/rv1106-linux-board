#!/usr/bin/env python3
"""Layout phase L1: generate the custom footprints of layout.md §6.1/§6.2/§6.4 into design/pcb/board.pretty/.

Re-runnable; writes KiCad 10 .kicad_mod files (s-expression version 20260206, same as the stock KiCad 10.0.7 library),
then, when run with KiCad's bundled Python, loads every file back with pcbnew.FootprintLoad to prove it parses.

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        design/pcb/scripts/make_footprints.py

Sources (every number below is cited next to where it is used; full table in design/pcb/footprints.md):
  [DS]   refs/rv1106-datasheet-r1.8/RV1106_Datasheet_r1.8.pdf  p.16 Fig.2-3/2-4 (pin order), p.17 Fig.2-5 (dimensions)
  [TI]   refs/ts3usb221a-datasheet/TS3USB221A_C128396.pdf      p.3 (pinout, top view), p.23 RSE mechanical 4207268-3/D,
                                                                p.24 RSE land pattern 4208106-3/E
  [FHD]  refs/fhd4020s-datasheet/FHD4020S_C602029.pdf          p.2 "Shape and dimensions" Fig.2 + table row FHD4020
  [XKB]  refs/ts-1187a-datasheet/TS-1187A_C318884.pdf          p.1 body view + "P.C.B LAYOUT TOP VIEW"
  [TF]   refs/tf-01a-datasheet/TF-01A_C91145.pdf               p.1 "PCB Layout (Pattern Side)" + top view
  [WJDG] refs/usb-a-af90-wjdg-datasheet/usb-a-af90-wjdg_C456018.pdf p.1 PCB pattern, front/top/side views
Decisions: D-74 (pad names), D-85/D-85a (QFN-128 land pattern), D-99 (this phase: J4 VBUS side, TF-01A numbering,
drill sizes, origins).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "board.pretty"))

SILK_W = 0.15      # layout.md §1 / [JLC-CAP] "Legend: Minimum Line Width >= 0.15mm"
SILK_CLR = 0.15    # [JLC-CAP] "Pad To Silkscreen 0.15mm"
FAB_W = 0.10
CRT_W = 0.05
CRT_MARGIN = 0.25  # IPC-7351 nominal courtyard excess; reproduces the D-84a TS-1187A courtyard 7.5 x 5.6 mm


def f(v):
    """Format a number the way KiCad does (no trailing zeros)."""
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Footprint:
    def __init__(self, name, descr, tags, attr="smd"):
        self.name, self.descr, self.tags, self.attr = name, descr, tags, attr
        self.pads = []      # dicts
        self.shapes = []    # (kind, layer, data, width, fill)
        self.texts = []
        self.ref_at = (0, 0)
        self.val_at = (0, 0)

    # ---- primitives -------------------------------------------------------------------------------------------
    def pad(self, name, x, y, w, h, kind="smd", shape="rect", layers=None, drill=None, extra=()):
        if layers is None:
            layers = ["F.Cu", "F.Paste", "F.Mask"] if kind == "smd" else ["*.Cu", "*.Mask"]
        self.pads.append(dict(name=name, x=x, y=y, w=w, h=h, kind=kind, shape=shape, layers=layers,
                              drill=drill, extra=list(extra)))

    def line(self, layer, x1, y1, x2, y2, w):
        self.shapes.append(("line", layer, (x1, y1, x2, y2), w, False))

    def rect(self, layer, x1, y1, x2, y2, w, fill=False):
        self.shapes.append(("rect", layer, (x1, y1, x2, y2), w, fill))

    def circle(self, layer, cx, cy, r, w, fill=False):
        self.shapes.append(("circle", layer, (cx, cy, r), w, fill))

    def poly(self, layer, pts, w, fill=False):
        self.shapes.append(("poly", layer, pts, w, fill))

    # ---- helpers ----------------------------------------------------------------------------------------------
    def copper_boxes(self):
        """Axis-aligned boxes of everything that has copper or a mask opening (for silk clipping)."""
        out = []
        for p in self.pads:
            if not any(l.endswith(".Cu") or l.endswith(".Mask") for l in p["layers"]):
                continue
            out.append((p["x"] - p["w"] / 2, p["y"] - p["h"] / 2, p["x"] + p["w"] / 2, p["y"] + p["h"] / 2))
        return out

    def silk_line_clipped(self, x1, y1, x2, y2, min_len=0.2):
        """Draw an axis-aligned silk line, removing every part closer than SILK_CLR to a pad (edge to edge)."""
        keep = SILK_CLR + SILK_W / 2 + 0.005
        horiz = abs(y1 - y2) < 1e-9
        a, b = (min(x1, x2), max(x1, x2)) if horiz else (min(y1, y2), max(y1, y2))
        c = y1 if horiz else x1
        cuts = []
        for (bx1, by1, bx2, by2) in self.copper_boxes():
            lo, hi, plo, phi = (bx1, bx2, by1, by2) if horiz else (by1, by2, bx1, bx2)
            # perpendicular distance from the line to the box
            d = 0.0 if plo <= c <= phi else min(abs(c - plo), abs(c - phi))
            if d >= keep:
                continue
            ext = math.sqrt(max(keep * keep - d * d, 0.0))
            cuts.append((lo - ext, hi + ext))
        segs = [(a, b)]
        for (cl, ch) in cuts:
            nxt = []
            for (s, e) in segs:
                if ch <= s or cl >= e:
                    nxt.append((s, e))
                    continue
                if cl > s:
                    nxt.append((s, cl))
                if ch < e:
                    nxt.append((ch, e))
            segs = nxt
        for (s, e) in segs:
            if e - s >= min_len:
                if horiz:
                    self.line("F.SilkS", s, c, e, c, SILK_W)
                else:
                    self.line("F.SilkS", c, s, c, e, SILK_W)

    def bbox(self, layers_pred):
        xs, ys = [], []
        for p in self.pads:
            if any(layers_pred(l) for l in p["layers"]) or layers_pred("pads"):
                xs += [p["x"] - p["w"] / 2, p["x"] + p["w"] / 2]
                ys += [p["y"] - p["h"] / 2, p["y"] + p["h"] / 2]
        return xs, ys

    def add_courtyard(self, body):
        """Courtyard = bbox(pads, body) + 0.25 mm, grown if needed to hold the silk (rounded to 0.01 mm)."""
        xs = [body[0], body[2]] + [p["x"] - p["w"] / 2 for p in self.pads] + [p["x"] + p["w"] / 2 for p in self.pads]
        ys = [body[1], body[3]] + [p["y"] - p["h"] / 2 for p in self.pads] + [p["y"] + p["h"] / 2 for p in self.pads]
        x1, y1, x2, y2 = min(xs) - CRT_MARGIN, min(ys) - CRT_MARGIN, max(xs) + CRT_MARGIN, max(ys) + CRT_MARGIN
        for (kind, layer, d, w, fill) in self.shapes:
            if layer != "F.SilkS":
                continue
            if kind == "circle":
                pts = [(d[0] - d[2], d[1] - d[2]), (d[0] + d[2], d[1] + d[2])]
            elif kind == "poly":
                pts = d
            else:
                pts = [(d[0], d[1]), (d[2], d[3])]
            for (px, py) in pts:
                x1, y1 = min(x1, px - w / 2 - 0.05), min(y1, py - w / 2 - 0.05)
                x2, y2 = max(x2, px + w / 2 + 0.05), max(y2, py + w / 2 + 0.05)
        r = lambda v, up: (math.ceil if up else math.floor)(round(v * 100, 6)) / 100.0
        self.rect("F.CrtYd", r(x1, False), r(y1, False), r(x2, True), r(y2, True), CRT_W)

    # ---- output -----------------------------------------------------------------------------------------------
    def text_block(self, kind, value, x, y, layer, size, thick, hide=False):
        t = "\t(property \"%s\" \"%s\"\n" % (kind, value) if kind else "\t(fp_text user \"%s\"\n" % value
        t += "\t\t(at %s %s 0)\n\t\t(layer \"%s\")\n" % (f(x), f(y), layer)
        if hide:
            t += "\t\t(hide yes)\n"
        t += "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size %s %s)\n\t\t\t\t(thickness %s)\n\t\t\t)\n\t\t)\n\t)\n" % (
            f(size), f(size), f(thick))
        return t

    def render(self):
        o = ["(footprint \"%s\"\n" % self.name,
             "\t(version 20260206)\n\t(generator \"pcbnew\")\n\t(generator_version \"10.0\")\n",
             "\t(layer \"F.Cu\")\n",
             "\t(descr \"%s\")\n" % self.descr.replace('"', "'"),
             "\t(tags \"%s\")\n" % self.tags]
        o.append(self.text_block("Reference", "REF**", self.ref_at[0], self.ref_at[1], "F.SilkS", 1.0, 0.15))
        o.append(self.text_block("Value", self.name, self.val_at[0], self.val_at[1], "F.Fab", 1.0, 0.15))
        o.append(self.text_block("Datasheet", "", 0, 0, "F.Fab", 1.0, 0.15, hide=True))
        o.append(self.text_block("Description", self.descr.replace('"', "'"), 0, 0, "F.Fab", 1.0, 0.15, hide=True))
        o.append("\t(attr %s)\n" % self.attr)
        o.append("\t(duplicate_pad_numbers_are_jumpers no)\n")
        for (kind, layer, d, w, fill) in self.shapes:
            st = "\t\t(stroke\n\t\t\t(width %s)\n\t\t\t(type solid)\n\t\t)\n" % f(w)
            fl = "\t\t(fill %s)\n" % ("yes" if fill else "no")
            if kind == "line":
                o.append("\t(fp_line\n\t\t(start %s %s)\n\t\t(end %s %s)\n%s\t\t(layer \"%s\")\n\t)\n" % (
                    f(d[0]), f(d[1]), f(d[2]), f(d[3]), st, layer))
            elif kind == "rect":
                o.append("\t(fp_rect\n\t\t(start %s %s)\n\t\t(end %s %s)\n%s%s\t\t(layer \"%s\")\n\t)\n" % (
                    f(d[0]), f(d[1]), f(d[2]), f(d[3]), st, fl, layer))
            elif kind == "circle":
                o.append("\t(fp_circle\n\t\t(center %s %s)\n\t\t(end %s %s)\n%s%s\t\t(layer \"%s\")\n\t)\n" % (
                    f(d[0]), f(d[1]), f(d[0] + d[2]), f(d[1]), st, fl, layer))
            elif kind == "poly":
                pts = " ".join("(xy %s %s)" % (f(x), f(y)) for (x, y) in d)
                o.append("\t(fp_poly\n\t\t(pts %s)\n%s%s\t\t(layer \"%s\")\n\t)\n" % (pts, st, fl, layer))
        for t in self.texts:
            o.append(self.text_block(None, t[0], t[1], t[2], t[3], t[4], t[5]))
        for p in self.pads:
            o.append("\t(pad \"%s\" %s %s\n\t\t(at %s %s)\n\t\t(size %s %s)\n" % (
                p["name"], p["kind"], p["shape"], f(p["x"]), f(p["y"]), f(p["w"]), f(p["h"])))
            if p["drill"] is not None:
                o.append("\t\t(drill %s)\n" % f(p["drill"]))
            for e in p["extra"]:
                if e.startswith("(property"):
                    o.append("\t\t%s\n" % e)
            o.append("\t\t(layers %s)\n" % " ".join('"%s"' % l for l in p["layers"]))
            if p["kind"] == "thru_hole":
                o.append("\t\t(remove_unused_layers no)\n")
            for e in p["extra"]:
                if not e.startswith("(property"):
                    o.append("\t\t%s\n" % e)
            o.append("\t)\n")
        o.append("\t(embedded_fonts no)\n)\n")
        return "".join(o)

    def write(self):
        path = os.path.join(LIB, self.name + ".kicad_mod")
        with open(path, "w") as fh:
            fh.write(self.render())
        return path


def fab_text(fp, y, size=0.8):
    fp.texts.append(("${REFERENCE}", 0, y, "F.Fab", size, size * 0.15))


# ======================================================================================================================
# U9  RV1106G3  QFN-128 12.3 x 12.3 mm, 0.35 mm pitch, EP 7.0 mm  (layout.md §6.1/§6.2, D-85, D-85a)
# ======================================================================================================================
def qfn128(ep_drilled=True):
    """ep_drilled=False: the L5G variant "_EPboardvias" (D-119, D-129): the same land pattern without the 16 drilled
    pads 129; on the board the 16 thermal vias are GND board vias 0.5 / 0.3 at the same positions (ViaDrill, POFV)."""
    if ep_drilled:
        fp = Footprint("RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm",
                       "Rockchip RV1106 QFN-128 12.3x12.3mm BSC, pitch 0.35mm, EP 7.0x7.0mm, 16 thermal vias 0.3/0.5mm, "
                       "paste windowpane 3x3 1.65mm (RV1106 Datasheet r1.8 Fig.2-3/2-4 p.16, Fig.2-5 p.17; layout.md 6.1-6.2)",
                       "QFN-128 RV1106 rockchip 0.35mm")
    else:
        fp = Footprint("RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm_EPboardvias",
                       "Rockchip RV1106 QFN-128 12.3x12.3mm BSC, pitch 0.35mm, EP 7.0x7.0mm, no drilled pads: 16 GND "
                       "board vias 0.3/0.5mm at the thermal-via positions (D-119), paste windowpane 3x3 1.65mm "
                       "(RV1106 Datasheet r1.8 Fig.2-3/2-4 p.16, Fig.2-5 p.17; layout.md 6.1-6.2)",
                       "QFN-128 RV1106 rockchip 0.35mm")
    BODY = 12.3 / 2           # [DS] p.17 D = E = 12.3 BSC
    PITCH = 0.35              # [DS] p.17 e = 0.35 BSC
    PW, PL = 0.19, 0.75       # layout.md §6.1: covers b max 0.18; L 0.3-0.5
    PC = 6.075                # pad centre from body centre: pad 5.70 .. 6.45 (layout.md §6.1)
    n_side = 32
    first = -(n_side - 1) / 2 * PITCH   # -5.425
    # [DS] p.16 Fig.2-4 (bottom view) shows 1 at the lower-left going up to 32; mirrored to the top view (Fig.2-3:
    # "1" at the top-left corner, "128" next to it on the top edge) pins run counter-clockwise seen from the top:
    # 1-32 west side N->S, 33-64 south side W->E, 65-96 east side S->N, 97-128 north side E->W.
    for i in range(n_side):
        k = first + i * PITCH
        fp.pad(str(1 + i), -PC, k, PL, PW)            # west, N->S
        fp.pad(str(33 + i), k, PC, PW, PL)            # south, W->E
        fp.pad(str(65 + i), PC, -k, PL, PW)           # east, S->N
        fp.pad(str(97 + i), -k, -PC, PW, PL)          # north, E->W
    # Exposed pad 129 = GND ([DS] p.19 "VSS E-PAD"); 7.0 x 7.0 = D2/E2 nominal ([DS] p.17); mask 1:1, no paste on
    # the pad itself (paste comes from the windowpane below); solid zone connection.
    fp.pad("129", 0, 0, 7.0, 7.0, layers=["F.Cu", "F.Mask"], extra=["(property pad_prop_heatsink)", "(zone_connect 2)"])
    # 16 thermal vias 0.3 drill / 0.5 pad, as plated through-hole copies of pad 129 (layout.md §6.2 positions).
    # Layers *.Cu only: no mask opening of their own -> tented on the bottom; on top they sit inside the EP opening.
    vias = [(sx * 1.15, y) for sx in (-1, 1) for y in (-2.3, -1.15, 0.0, 1.15, 2.3)] + \
           [(x, sy * 1.15) for sy in (-1, 1) for x in (-2.3, 0.0, 2.3)]
    for (x, y) in (vias if ep_drilled else []):
        fp.pad("129", x, y, 0.5, 0.5, kind="thru_hole", shape="circle", drill=0.3, layers=["*.Cu"],
               extra=["(property pad_prop_heatsink)", "(zone_connect 2)"])
    # Paste windowpane: 3 x 3 squares 1.65 mm at 2.30 mm pitch (layout.md §6.2), unnamed paste-only apertures.
    for x in (-2.3, 0.0, 2.3):
        for y in (-2.3, 0.0, 2.3):
            fp.pad("", x, y, 1.65, 1.65, layers=["F.Paste"])
    # Fab: body 12.3 mm with a 1 mm pin-1 chamfer (NW).
    c = 1.0
    fp.poly("F.Fab", [(-BODY + c, -BODY), (BODY, -BODY), (BODY, BODY), (-BODY, BODY), (-BODY, -BODY + c)], FAB_W)
    fab_text(fp, 0, 1.5)
    # Silk: square at 6.68 (pad toes end at 6.45 -> 0.155 mm edge clearance), open at the NW corner, + pin-1 dot.
    S = 6.68
    fp.line("F.SilkS", -S + 1.0, -S, S, -S, SILK_W)
    fp.line("F.SilkS", S, -S, S, S, SILK_W)
    fp.line("F.SilkS", S, S, -S, S, SILK_W)
    fp.line("F.SilkS", -S, S, -S, -S + 1.0, SILK_W)
    fp.circle("F.SilkS", -6.42, -6.42, 0.1, SILK_W, fill=True)     # in the empty NW corner, outside the body edge
    fp.ref_at, fp.val_at = (0, -7.9), (0, 7.9)
    fp.add_courtyard((-BODY, -BODY, BODY, BODY))
    return fp


# ======================================================================================================================
# U11  TS3USB221A  RSE (UQFN-10) 1.5 x 2.0 mm, 0.5 mm pitch
# ======================================================================================================================
def uqfn10():
    fp = Footprint("TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm",
                   "TI RSE (R-PUQFN-N10) 1.5x2.0mm, pitch 0.5mm; TI land pattern 4208106-3/E (TS3USB221A SCDS277A p.24), "
                   "package 4207268-3/D (p.23); pin 1 top-left, drawn rotated 90 deg CW from the TI top view",
                   "UQFN-10 RSE TI TS3USB221A")
    # TI p.24 "Example Board Layout" (top view, long axis horizontal): side leads 0.58 long, x at +-0.25/+-0.75
    # (pitch 0.50, span 1.50), corner leads 0.30 wide, middle side leads 0.25 wide, rows 0.70 apart (inner edges),
    # overall 1.85; end leads 0.35 x 0.63, overall 2.35. Here the TI top view is rotated 90 deg clockwise so pin 1 is
    # top-left (KiCad convention): pins 1-4 west N->S, 5 south, 6-9 east S->N, 10 north (TI p.3 top view: 1-4 bottom
    # row W->E, 5 east, 6-9 top row E->W, 10 west).
    SL = 1.85 / 2 - 0.70 / 2   # side-pad length 0.575 (TI labels it 0.58: overall 1.85, rows 0.70 apart)
    SX = 0.35 + SL / 2         # side-pad centre x = 0.6375 (inner edge 0.35 = 0.70/2, toe 0.925 = 1.85/2)
    EY = 2.35 / 2 - 0.63 / 2   # end-pad centre y = 0.86 (toe 1.175 = 2.35/2)
    ys = (-0.75, -0.25, 0.25, 0.75)
    wid = (0.30, 0.25, 0.25, 0.30)
    for i in range(4):
        fp.pad(str(1 + i), -SX, ys[i], SL, wid[i])         # 1..4 west, N->S
        fp.pad(str(6 + i), SX, ys[3 - i], SL, wid[3 - i])  # 6..9 east, S->N
    fp.pad("5", 0, EY, 0.35, 0.63)
    fp.pad("10", 0, -EY, 0.35, 0.63)
    # Mask 1:1 (TI shows 0.05 clearance; at 0.175 mm pad gaps that would leave a 0.075 mm web < JLC 0.10 mm green
    # bridge, so the board-wide 1:1 rule of D-85 is kept). Paste 1:1 (TI note E: stencil <= 0.127 mm; the 0.10 mm
    # stencil of D-85a gives area ratio >= 0.84 on the 0.25 x 0.58 pads).
    BX, BY = 0.75, 1.0          # body 1.5 x 2.0 ([TI] p.23: 1.45-1.55 x 1.95-2.05)
    fp.poly("F.Fab", [(-BX + 0.3, -BY), (BX, -BY), (BX, BY), (-BX, BY), (-BX, -BY + 0.3)], FAB_W)
    fab_text(fp, 0, 0.35)
    for (x1, y1, x2, y2) in ((-1.15, -1.40, 1.15, -1.40), (1.15, -1.40, 1.15, 1.40),
                             (1.15, 1.40, -1.15, 1.40), (-1.15, 1.40, -1.15, -1.40)):
        fp.silk_line_clipped(x1, y1, x2, y2)
    fp.circle("F.SilkS", -1.42, -1.20, 0.1, SILK_W, fill=True)   # pin-1 dot, NW outside the silk box corner
    fp.ref_at, fp.val_at = (0, -2.4), (0, 2.4)
    fp.add_courtyard((-BX, -BY, BX, BY))
    return fp


# ======================================================================================================================
# L1-L4  FHD4020S  4.0 x 4.0 x 2.0 mm power inductor
# ======================================================================================================================
def fhd4020s():
    fp = Footprint("L_FHD4020S_4.0x4.0mm",
                   "CJiang FHD4020S wire-wound power inductor 4.0x4.0x2.0mm; land pattern FHD4020S datasheet p.2 Fig.2: "
                   "a (H) 1.9, b (I) 1.10, c (G) 3.7",
                   "inductor FHD4020S power")
    # [FHD] p.2 table, row FHD4020 (Fig.2): A 4.0, B 4.0, C 2.0 max, D 3.1, E 0.95, F 2.1; recommended land
    # a Typ 1.9 (= H, gap between pads), b Typ 1.10 (= I, pad length), c Typ 3.7 (= G, pad width).
    # Letter mapping a/b/c -> H/I/G inferred: H + 2 I = 4.1 ~ A, G = 3.7 ~ D + 0.6; holds for every row of the table.
    H, I, G = 1.9, 1.10, 3.7
    xc = H / 2 + I / 2   # 1.50
    fp.pad("1", -xc, 0, I, G)
    fp.pad("2", xc, 0, I, G)
    B = 2.0
    fp.rect("F.Fab", -B, -B, B, B, FAB_W)
    fab_text(fp, 0, 0.6)
    fp.silk_line_clipped(-B, -2.12, B, -2.12)
    fp.silk_line_clipped(-B, 2.12, B, 2.12)
    fp.circle("F.SilkS", -2.45, -1.95, 0.1, SILK_W, fill=True)   # pad-1 mark (orientation reference only)
    fp.ref_at, fp.val_at = (0, -3.1), (0, 3.1)
    fp.add_courtyard((-B, -B, B, B))
    return fp


# ======================================================================================================================
# SW1-SW3  XKB TS-1187A  5.1 x 5.1 mm SMD tact switch
# ======================================================================================================================
def ts1187a():
    fp = Footprint("SW_TS-1187A_5.1x5.1mm",
                   "XKB TS-1187A 5.1x5.1mm SMD tact switch; TS-1187A-X-X-X drawing p.1 'P.C.B LAYOUT TOP VIEW': "
                   "pads 1.0x0.75 at 6.0 x 3.75 mm centres; 1=A 2=B 3=C 4=D, A-B and C-D joined internally",
                   "switch tactile TS-1187A XKB")
    # [XKB] p.1 P.C.B LAYOUT TOP VIEW: pad outer span 7.0, inner 5.0 (-> pad 1.0 wide, centres +-3.0),
    # rows 3.0 inner / 4.5 outer (-> pad 0.75 tall, centres +-1.875). Body view (same page): A top-left,
    # B top-right, C bottom-left, D bottom-right; schematic A-B / C-D (D-74).
    for (n, x, y) in (("1", -3.0, -1.875), ("2", 3.0, -1.875), ("3", -3.0, 1.875), ("4", 3.0, 1.875)):
        fp.pad(n, x, y, 1.0, 0.75)
    B = 5.1 / 2   # [XKB] p.1 body 5.1 +- 0.05
    fp.rect("F.Fab", -B, -B, B, B, FAB_W)
    fp.circle("F.Fab", 0, 0, 1.0, FAB_W)        # actuator, [XKB] p.1 "Ø2.0"
    fab_text(fp, 0, 0.5)
    for (x1, y1, x2, y2) in ((-B, -B, B, -B), (B, -B, B, B), (B, B, -B, B), (-B, B, -B, -B)):
        fp.silk_line_clipped(x1, y1, x2, y2)
    fp.circle("F.SilkS", -3.0, -2.6, 0.05, SILK_W, fill=True)    # pin-1 (A) dot above pad 1
    fp.ref_at, fp.val_at = (0, -3.7), (0, 3.7)
    fp.add_courtyard((-B, -B, B, B))
    return fp


# ======================================================================================================================
# J2  HRO TF-01A  push-push microSD
# ======================================================================================================================
def tf01a():
    fp = Footprint("microSD_TF-01A",
                   "HRO TF-01A push-push microSD socket; TF-01A drawing p.1 'PCB Layout (Pattern Side)': 9 contacts "
                   "0.70x1.30 at 1.10 pitch, 4 shell tabs, 2x NPTH 1.00 8.00 apart; card slot opening to +y (south)",
                   "microSD TF-01A HRO card")
    # Drawing frame (mm): origin at the "cd" contact centre, x to the right (towards contact 1), y towards the card
    # slot. [TF] p.1 pattern view (same orientation as its top view: detect lever beside "cd", contact tails at the
    # back, card entry at the front):
    #   contacts: "9-0.70" wide x "9-1.30" long, pitch 1.10, "8.80" from cd to contact 1; order cd,8,7,...,1
    #   shell tabs back pair 1.20 x 1.40 ("2-1.20", "2-1.40"), centre y = contact top + 1.50 = 0.85;
    #     left x = -1.10 ("1.10" left), right x = 13.58 ("13.58" from cd)
    #   shell tabs front pair 1.20 x 2.00 ("2-2.00"), y = 0.85 + 9.70 = 10.55 ("9.70"; check: 11.20 from the
    #     contact top = 0.65 + 10.55); left x = -1.10, right x = -1.10 + 15.52 = 14.42 ("15.52")
    #   holes 2 x Ø1.00 ("2-ø1.00"), 8.00 apart ("8.00"), left one 2.81 from the left shell column ("2.81");
    #     y = 10.85: NOT dimensioned, scaled from the vector drawing (0.30 mm beyond the front tab centre) - UNVERIFIED
    #   body (top view): 14.80 wide (x -0.77 .. 14.03, left edge scaled), 14.50 deep from the back edge at y = 0.37
    #     ("0.37") to the front at y = 14.87; card protrudes 2.65 further when latched.
    X0, Y0 = 6.63, 7.62     # footprint origin = body centre in the drawing frame
    P = lambda x, y: (round(x - X0, 4), round(y - Y0, 4))
    for n in range(1, 9):
        fp.pad(str(n), *P(1.10 * (9 - n), 0.0), 0.70, 1.30)
    fp.pad("9", *P(0.0, 0.0), 0.70, 1.30)                     # cd = card detect (D-74)
    for (x, y, w, h) in ((-1.10, 0.85, 1.20, 1.40), (13.58, 0.85, 1.20, 1.40),
                         (-1.10, 10.55, 1.20, 2.00), (14.42, 10.55, 1.20, 2.00)):
        fp.pad("SH", *P(x, y), w, h)
    for x in (1.71, 9.71):
        fp.pad("", *P(x, 10.85), 1.0, 1.0, kind="np_thru_hole", shape="circle", drill=1.0, layers=["*.Cu", "*.Mask"])
    bx1, by1 = P(-0.77, 0.37)
    bx2, by2 = P(14.03, 14.87)
    fp.rect("F.Fab", bx1, by1, bx2, by2, FAB_W)
    cx1, _ = P(1.0, 0)
    cx2, _ = P(12.05, 0)
    fp.line("Dwgs.User", cx1, by2 + 2.65, cx2, by2 + 2.65, FAB_W)  # latched card front (2.65 beyond the body), Dwgs.User: off-board
    fp.line("Dwgs.User", cx1, by2, cx1, by2 + 2.65, FAB_W)
    fp.line("Dwgs.User", cx2, by2, cx2, by2 + 2.65, FAB_W)
    fab_text(fp, 0, 1.0)
    fp.texts.append(("card slot", 0, by2 - 1.2, "F.Fab", 0.8, 0.12))
    # silk: back and both sides of the body (the front lies on the board edge), clipped around the pads
    fp.silk_line_clipped(bx1, by1, bx2, by1)
    fp.silk_line_clipped(bx1, by1, bx1, by2)
    fp.silk_line_clipped(bx2, by1, bx2, by2)
    fp.circle("F.SilkS", *P(8.80, -1.0), 0.1, SILK_W, fill=True)  # contact-1 dot (behind contact 1)
    fp.ref_at, fp.val_at = (0, -2.5), (0, 2.5)
    fp.add_courtyard((bx1, by1, bx2, by2))
    return fp


# ======================================================================================================================
# J4  Shouhan AF 90 WJDG  USB-A receptacle, right angle, THT
# ======================================================================================================================
def usba():
    fp = Footprint("USB_A_AF90_WJDG_RightAngle_THT",
                   "Shouhan AF90 WJDG USB-A receptacle right angle THT; drawing p.1: 4 pins Ø0.9 (2.0 inner / 7.0 outer "
                   "pitch), 2 shell legs Ø2.1, 2.4 mm towards the mouth; mouth to +y (south); pin 1 VBUS west (D-99)",
                   "USB-A receptacle THT AF90 WJDG")
    # [WJDG] p.1 PCB pattern: "4-ø0.9±0.1" pins at 7.0 outer / 2.0 inner pitch; "ø2.1" shell legs 2.4 from the pin
    # row (side view: legs 10.4 behind the front face, pins 2.4 further back -> legs are on the mouth side).
    # Shell-leg spacing is not dimensioned: scaled from the vector drawing = 12.98 mm (pin pitch used as the scale),
    # i.e. +-6.49 -> 13.0 used (front view body 13.10) - UNVERIFIED, covered by the 2.3 mm hole.
    # Holes = drawing + 0.1 (pins) / + 0.2 (splayed shell legs), layout.md §6.4.
    # Pin numbering: the drawing has none; pin 1 (VBUS) = west outer pin with the mouth facing south (D-99).
    PY = 0.0
    for (n, x) in (("1", -3.5), ("2", -1.0), ("3", 1.0), ("4", 3.5)):
        fp.pad(n, x, PY, 1.6, 1.6, kind="thru_hole", shape="rect" if n == "1" else "circle", drill=1.0)
    for x in (-6.5, 6.5):
        fp.pad("SH", x, PY + 2.4, 3.0, 3.0, kind="thru_hole", shape="circle", drill=2.3)
    # body: 14.30 wide ([WJDG] top view), 14.20 deep: front face 12.8 in front of the pins (10.4 + 2.4), back 1.4
    BX = 14.30 / 2
    by1, by2 = PY - 1.4, PY + 12.8
    # shift so the footprint origin is the body centre
    dy = -(by1 + by2) / 2
    for p in fp.pads:
        p["y"] = round(p["y"] + dy, 4)
    by1, by2 = by1 + dy, by2 + dy
    fp.rect("F.Fab", -BX, by1, BX, by2, FAB_W)
    fp.line("F.Fab", -6.55, by2 - 0.3, 6.55, by2 - 0.3, FAB_W)
    fab_text(fp, 0, 0.0)
    fp.texts.append(("mouth", 0, by2 - 1.2, "F.Fab", 0.8, 0.12))
    fp.silk_line_clipped(-BX, by1, BX, by1)
    fp.silk_line_clipped(-BX, by1, -BX, by2)
    fp.silk_line_clipped(BX, by1, BX, by2)
    fp.circle("F.SilkS", -3.5, PY + dy - 1.85, 0.12, SILK_W, fill=True)   # pin-1 (VBUS) dot behind pin 1
    fp.ref_at, fp.val_at = (0, by1 - 1.5), (0, 2.0)
    fp.add_courtyard((-BX, by1, BX, by2))
    fp.attr = "through_hole"
    return fp


def qfn128_epboardvias():
    return qfn128(ep_drilled=False)


BUILDERS = [qfn128, qfn128_epboardvias, uqfn10, fhd4020s, ts1187a, tf01a, usba]


def main():
    os.makedirs(LIB, exist_ok=True)
    names = []
    for b in BUILDERS:
        fp = b()
        path = fp.write()
        names.append(fp.name)
        print("wrote %s (%d pads)" % (os.path.relpath(path, os.path.join(HERE, "..")), len(fp.pads)))
    stock_fid = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Fiducial.pretty/Fiducial_1mm_Mask2mm.kicad_mod"
    print("stock Fiducial:Fiducial_1mm_Mask2mm present:", os.path.exists(stock_fid), "-> no custom fiducial drawn")
    try:
        import pcbnew
    except ImportError:
        print("pcbnew not available: run with KiCad's Python to verify loading")
        return 0
    bad = 0
    for n in names:
        m = pcbnew.FootprintLoad(LIB, n)
        if m is None:
            print("LOAD FAIL", n)
            bad += 1
        else:
            print("loaded %-45s pads=%d" % (n, len(list(m.Pads()))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
