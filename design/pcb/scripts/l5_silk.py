#!/usr/bin/env python3
"""Layout phase L5, step 6 (KiCad Python): silkscreen clean-up and labels (layout.md §1 "Silk", testpoints.md §2).

    $PY design/pcb/scripts/l5_silk.py          # edits the saved board; writes design/pcb/l5/silk.json (what was done)

1. Reference designators (1.0 mm text, 0.15 mm line, layout.md §1): each one is moved to the first free spot from a
   fixed candidate list around its own courtyard (above, below, left, right, the corners; 0 or 90 deg, kept upright),
   free meaning: >= 0.15 mm from every pad / mask opening, hole and fiducial of the board (JLC "Pad to silkscreen
   0.15 mm"), clear of the footprint silk outlines and of every text already placed, >= 0.5 mm inside the board edge
   and outside the M3 keep-outs. Larger parts are placed first. A reference with no free spot is hidden on the
   silkscreen (it stays on F.Fab and in the assembly drawing) and listed in silk.json.
2. Board labels, placed by the same search near their part: "RV1106 Rev A 2026-11" (board name, revision, date);
   POWER / RESET / MASKROM at SW1 / SW2 / SW3; PWR / STAT / ETH at LED1 / LED2 / LED3; header pin numbers 1, 2, 39, 40
   at J5; a short net name next to every test pad (testpoints.md §2 rule 2, e.g. "5V", "3V3", "XO"); "B" at the
   buck-side pad of JP1, R29, R30, R31 (testpoints.md Phase 7 rule).
All labels are board texts in the group L5_SILK. The footprints' own silk outlines and pin-1 marks are unchanged.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

GROUP = "L5_SILK"
H = 1.0           # text height (mm), layout.md §1 >= 1.0
TW = 0.15         # stroke
PAD_GAP = 0.15
TXT_GAP = 0.15
EDGE = 0.5
M3 = ((3.5, 3.5), (76.5, 3.5), (3.5, 76.5), (76.5, 76.5))
TP_LABEL = {"TP21": "VBUS", "TP1": "5V", "TP13": "5VSYS", "TP8": "ONEN", "TP12": "EN_N", "TP14": "PWREN",
            "TP4": "0V9", "TP15": "ARM", "TP5": "DDR", "TP3": "1V8", "TP22": "MIPI", "TP23": "USB1V8", "TP24": "COD",
            "TP25": "E18", "TP2": "3V3", "TP26": "E33", "TP18": "RTC", "TP16": "SD", "TP17": "VUSBA", "TP6": "XO",
            "TP7": "NPOR", "TP9": "TX", "TP10": "RX", "TP11": "LED", "TP27": "INT", "TP28": "KILL", "TP29": "KILLN",
            "TP30": "DET", "TP19": "GND", "TP20": "GND", "TP31": "GND"}
SMALL_H = 0.8      # D-114 g: fallback text height for the LED labels only (owner approval asked)
SMALL_OK = ("LED1", "LED2", "LED3")
OWN_REFS = ("R62", "R63")    # L5F: references that must sit beside their own part (verifier L5 r4 minor)
PART_LABEL = {"SW1": "POWER", "SW2": "RESET", "SW3": "MASKROM", "LED1": "PWR", "LED2": "STAT", "LED3": "ETH"}


def bb_mm(box):
    x0, y0 = bl.to_board(box.GetOrigin())
    x1, y1 = bl.to_board(box.GetEnd())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def grow(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def silk_rects(g):
    """thin rectangles along a footprint silk shape (a rectangle or polygon outline is its edges, not its area)"""
    w = max(0.15, pcbnew.ToMM(g.GetWidth())) / 2 + 0.05
    pts = None
    try:
        if g.GetShape() == pcbnew.SHAPE_T_RECT:
            c = [bl.to_board(v) for v in g.GetRectCorners()]
            pts = c + [c[0]]
        elif g.GetShape() == pcbnew.SHAPE_T_POLY:
            o = g.GetPolyShape().Outline(0)
            pts = [bl.to_board(o.CPoint(i)) for i in range(o.PointCount())]
            pts.append(pts[0])
    except Exception:          # noqa: BLE001  (unknown shape API: fall back to the bounding box)
        pts = None
    if not pts:
        return [grow(bb_mm(g.GetBoundingBox()), 0.05)]
    out = []
    for a, b in zip(pts, pts[1:]):
        out.append((min(a[0], b[0]) - w, min(a[1], b[1]) - w, max(a[0], b[0]) + w, max(a[1], b[1]) + w))
    return out


class Placer:
    def __init__(self, board):
        self.board = board
        self.obst = []        # rectangles nothing may touch
        self.texts = []       # rectangles of placed texts
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask):
                    xs = [q[0] for q in bl.pad_polygon(p)]
                    ys = [q[1] for q in bl.pad_polygon(p)]
                    m = max(0.0, pcbnew.ToMM(p.GetSolderMaskExpansion(pcbnew.F_Mask))) if hasattr(
                        p, "GetSolderMaskExpansion") else 0.05
                    self.obst.append(grow((min(xs), min(ys), max(xs), max(ys)), PAD_GAP + m))
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    x, y = bl.to_board(p.GetPosition())
                    r = pcbnew.ToMM(p.GetDrillSize().x) / 2 + 0.3
                    self.obst.append((x - r, y - r, x + r, y + r))
            for g in fp.GraphicalItems():
                if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != "PCB_TEXT":
                    self.obst += silk_rects(g)
        # round 3 (verifier major soc): no silk over a bottom-terminated part (QFN / SON / UQFN, crystals, molded
        # inductors): ink under a 0-0.05 mm standoff package can tilt it or starve the exposed pad of solder. Their
        # courtyards are closed to every text (their own reference goes outside, the candidate spots are outside)
        self.bottom = []
        for fp in board.GetFootprints():
            if is_bottom_terminated(fp):
                self.bottom.append(grow(court(fp), 0.06))     # + the courtyard line width
        self.obst += self.bottom

    def free(self, r):
        if r[0] < EDGE or r[1] < EDGE or r[2] > 80 - EDGE or r[3] > 80 - EDGE:
            return False
        for (cx, cy) in M3:
            nx = min(max(cx, r[0]), r[2])
            ny = min(max(cy, r[1]), r[3])
            if math.hypot(nx - cx, ny - cy) < 3.6:
                return False
        if any(hit(r, o) for o in self.obst):
            return False
        if any(hit(r, grow(t, TXT_GAP)) for t in self.texts):
            return False
        return True

    def place(self, txt, box, prefer=None, ok=None):
        """try candidate positions around box (board mm rect) for the text item txt; True if placed. ok(rect): an
        extra test of a candidate (e.g. the label must be nearer to its own part than to any other labelled part)"""
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        cands = []
        for ang in (0, 90):
            txt.SetTextAngleDegrees(ang)
            txt.SetPosition(bl.to_page(cx, cy))
            r = bb_mm(txt.GetBoundingBox())
            w, h = r[2] - r[0], r[3] - r[1]
            g = 0.1
            spots = [(cx, y0 - g - h / 2), (cx, y1 + g + h / 2), (x0 - g - w / 2, cy), (x1 + g + w / 2, cy),
                     (x0 - g - w / 2, y0 - g - h / 2), (x1 + g + w / 2, y0 - g - h / 2),
                     (x0 - g - w / 2, y1 + g + h / 2), (x1 + g + w / 2, y1 + g + h / 2)]
            for s in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
                spots += [(cx - s, y0 - g - h / 2), (cx + s, y0 - g - h / 2), (cx - s, y1 + g + h / 2),
                          (cx + s, y1 + g + h / 2), (x0 - g - w / 2, cy - s), (x0 - g - w / 2, cy + s),
                          (x1 + g + w / 2, cy - s), (x1 + g + w / 2, cy + s)]
            for s in (0.2, 0.4, 0.8, 1.2, 1.6, 2.4, 3.2):   # round 2: 0.2 / 0.4 / 1.2 added (LED labels)
                spots += [(cx, y0 - g - h / 2 - s), (cx, y1 + g + h / 2 + s), (x0 - g - w / 2 - s, cy),
                          (x1 + g + w / 2 + s, cy)]
            for p in spots:
                cands.append((ang, p))
        if prefer:
            cands = [c for c in cands if c[0] == prefer] + [c for c in cands if c[0] != prefer]
        for ang, (px, py) in cands:
            txt.SetTextAngleDegrees(ang)
            txt.SetPosition(bl.to_page(px, py))
            r = bb_mm(txt.GetBoundingBox())
            if self.free(r) and (ok is None or ok(r)):
                self.texts.append(r)
                return True
        return False


BOTTOM_LIBS = ("QFN", "SON", "DFN", "LGA", "BGA", "Crystal_SMD", "L_FHD4020S")


def is_bottom_terminated(fp):
    """parts whose terminals are under the body (no silk may go over their courtyard), from the footprint name"""
    name = fp.GetFPIDAsString()
    return any(k in name for k in BOTTOM_LIBS)


def court(fp):
    cb = bl.courtyard_bbox(fp)
    if cb:
        return cb
    return bb_mm(fp.GetBoundingBox(False, False))


def style(t):
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(H), pcbnew.FromMM(H)))
    t.SetTextThickness(pcbnew.FromMM(TW))
    t.SetKeepUpright(True)


SILK_PAD = 0.15     # silk to pad / mask opening (JLC "Pad to silkscreen 0.15 mm"); round 2: measured and enforced


def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _inside(px, py, poly):
    c = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _pad_dist(px, py, poly):
    if _inside(px, py, poly):
        return 0.0
    return min(_pt_seg(px, py, poly[i][0], poly[i][1], poly[(i + 1) % len(poly)][0], poly[(i + 1) % len(poly)][1])
               for i in range(len(poly)))


KEEP = []


def trim_footprint_silk(board):
    """round 2 (verifier minor): the stock footprints' own silk (0402 R/C bars between the pads, the 1.5 mm test-pad
    ring, a few IC outline pieces) comes closer than 0.15 mm to pads; JLC clips it anyway. Every footprint F.SilkS line
    / ring / outline that comes closer than SILK_PAD to a pad (F.Cu or mask opening; pad polygons in board mm) is
    trimmed: a line keeps its pieces that are clear and >= 0.2 mm long, a test-pad ring is enlarged to clear its pad,
    a rectangle / polygon outline is split into its edges (each trimmed like a line), anything else (arcs) is removed.
    Returns counts. (Pure geometry: SHAPE objects from GetEffectiveShape leak in this pcbnew build and broke later
    SWIG calls in a long loop.)"""
    out = {"trimmed": 0, "removed": 0, "rings": 0, "pieces_kept": 0}
    allpads, own_pads = [], {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask):
                m = max(0.0, pcbnew.ToMM(p.GetSolderMaskExpansion(pcbnew.F_Mask))) if p.IsOnLayer(pcbnew.F_Mask) \
                    else 0.0
                poly = bl.pad_polygon(p)
                xs = [q[0] for q in poly]
                ys = [q[1] for q in poly]
                item = (poly, m, (min(xs), min(ys), max(xs), max(ys)), p)
                allpads.append(item)
                own_pads.setdefault(fp.GetReference(), []).append(item)
    # L5F (D-H6 item 6, D-117 i): every footprint silk line / outline / circle at >= 0.15 mm (stock parts use 0.12 mm)
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != "PCB_TEXT" and g.GetWidth() < pcbnew.FromMM(0.15):
                g.SetWidth(pcbnew.FromMM(0.15))
                out["widened"] = out.get("widened", 0) + 1
    for fp in board.GetFootprints():
        pads = allpads              # every pad of the board (another part's pad next to this outline counts too)

        def clear(x, y, hw):
            # L5F (D-H6 item 6): no silk beyond the board edge (J1's outline crossed the south edge)
            if x - hw < 0.0 or x + hw > 80.0 or y - hw < 0.0 or y + hw > 80.0 - 0.15:
                return False
            for poly, m, bb, p in pads:
                lim = SILK_PAD + m + hw
                if x < bb[0] - lim - 0.01 or x > bb[2] + lim + 0.01 or y < bb[1] - lim - 0.01 or \
                        y > bb[3] + lim + 0.01:
                    continue
                if _pad_dist(x, y, poly) < lim - 1e-4:
                    return False
            return True

        def seg_runs(a, b, hw):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(2, int(L / 0.01))
            good = [clear(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, hw) for i in range(n + 1)]
            runs, k = [], 0
            while k <= n:
                if good[k]:
                    j = k
                    while j + 1 <= n and good[j + 1]:
                        j += 1
                    runs.append((k, j))
                    k = j + 1
                else:
                    k += 1
            return all(good), [((a[0] + (b[0] - a[0]) * i0 / n, a[1] + (b[1] - a[1]) * i0 / n),
                                (a[0] + (b[0] - a[0]) * i1 / n, a[1] + (b[1] - a[1]) * i1 / n))
                               for i0, i1 in runs if (i1 - i0) * L / n >= 0.2]

        def add_seg(p0, p1, w):
            ng = pcbnew.PCB_SHAPE(fp)
            ng.SetShape(pcbnew.SHAPE_T_SEGMENT)
            ng.SetLayer(pcbnew.F_SilkS)
            ng.SetWidth(w)
            ng.SetStart(bl.to_page(*p0))
            ng.SetEnd(bl.to_page(*p1))
            fp.Add(ng)
            KEEP.append(ng)           # keep the SWIG wrapper alive (the footprint owns the item now)

        for g in list(fp.GraphicalItems()):
            if g.GetLayer() != pcbnew.F_SilkS or g.GetClass() == "PCB_TEXT":
                continue
            w = g.GetWidth()
            hw = pcbnew.ToMM(w) / 2
            shape = g.GetShape()
            if shape == pcbnew.SHAPE_T_CIRCLE:
                c = bl.to_board(g.GetCenter())
                r = pcbnew.ToMM(g.GetRadius())
                ok = all(clear(c[0] + r * math.cos(2 * math.pi * k / 72), c[1] + r * math.sin(2 * math.pi * k / 72), hw)
                         for k in range(72))
                if ok:
                    continue
                mine = own_pads.get(fp.GetReference(), [])
                if len(mine) == 1:
                    poly, m, bb, p = mine[0]
                    r2 = max(math.hypot(q[0] - c[0], q[1] - c[1]) for q in poly) + m + SILK_PAD + hw + 0.01
                    g.SetEnd(bl.to_page(c[0], c[1] + r2))
                    out["rings"] += 1
                else:
                    fp.Remove(g)
                    KEEP.append(g)
                    out["removed"] += 1
                continue
            if shape == pcbnew.SHAPE_T_SEGMENT:
                edges = [(bl.to_board(g.GetStart()), bl.to_board(g.GetEnd()))]
            elif shape == pcbnew.SHAPE_T_RECT:
                cs = [bl.to_board(v) for v in g.GetRectCorners()]
                edges = list(zip(cs, cs[1:] + cs[:1]))
            elif shape == pcbnew.SHAPE_T_POLY:
                o = g.GetPolyShape().Outline(0)
                cs = [bl.to_board(o.CPoint(i)) for i in range(o.PointCount())]
                edges = list(zip(cs, cs[1:] + cs[:1]))
            else:
                bb = g.GetBoundingBox()
                x0, y0 = bl.to_board(bb.GetOrigin())
                x1, y1 = bl.to_board(bb.GetEnd())
                if all(clear(x, y, hw) for x in (x0, (x0 + x1) / 2, x1) for y in (y0, (y0 + y1) / 2, y1)):
                    continue
                fp.Remove(g)
                KEEP.append(g)
                out["removed"] += 1
                print("silk: removed a %s of %s (closer than %.2f mm to a pad)" % (g.GetShapeStr(), fp.GetReference(),
                                                                                    SILK_PAD))
                continue
            res = [seg_runs(a, b, hw) for a, b in edges]
            if all(r[0] for r in res):
                continue
            fp.Remove(g)
            KEEP.append(g)
            kept = 0
            for (allok, runs), (a, b) in zip(res, edges):
                for p0, p1 in runs:
                    add_seg(p0, p1, w)
                    kept += 1
            out["trimmed" if kept else "removed"] += 1
            out["pieces_kept"] += kept
    return out


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, GROUP)
    trim = trim_footprint_silk(board)
    P = Placer(board)
    hidden, moved = [], 0
    items, labels = [], []

    def place_ref(fp):
        nonlocal moved
        ref = fp.Reference()
        if not ref.IsVisible() or ref.GetLayer() != pcbnew.F_SilkS:
            return
        style(ref)
        ok = None
        if fp.GetReference() in OWN_REFS:
            # L5F (D-H6 item 10): R62 / R63 sit in a crowded strip; their references must be beside their own part:
            # <= 1.2 mm from its courtyard and >= 0.05 mm nearer to it than to any other courtyard
            mine = court(fp)
            others = [court(f) for f in board.GetFootprints() if f.GetReference() != fp.GetReference() and
                      not f.GetReference().startswith(("GFID", "FID", "TH", "H"))]

            def ok(r, mine=mine, others=others):
                def rd(a, b):
                    return math.hypot(max(0.0, max(a[0], b[0]) - min(a[2], b[2])),
                                      max(0.0, max(a[1], b[1]) - min(a[3], b[3])))
                d0 = rd(r, mine)
                return d0 <= 1.2 and all(rd(r, o) >= d0 + 0.05 for o in others)
        if fp.GetReference() in OWN_REFS:
            # first choice: turned 90 deg on the outer side of the pair (R62 east, R63 west), 0.1 mm off the courtyard
            # (R62: upright east of the pair at the courtyard's south end, below TP9's label; R63: turned, west)
            c = court(fp)
            if fp.GetReference() == "R62":
                ref.SetTextAngleDegrees(0)
                ref.SetPosition(bl.to_page(0, 0))
                w = pcbnew.ToMM(ref.GetBoundingBox().GetWidth())
                x, y = c[2] + 0.1 + w / 2, c[3] - 0.55
                ref.SetPosition(bl.to_page(x, y))
                r = (x - w / 2, y - 0.575, x + w / 2, y + 0.575)                         # ink box of the text
            else:
                ref.SetTextAngleDegrees(90)
                ref.SetPosition(bl.to_page(c[0] - 0.1 - 0.6, (c[1] + c[3]) / 2))
                r = bb_mm(ref.GetBoundingBox())
                r = ((r[0] + r[2]) / 2 - 0.575, r[1], (r[0] + r[2]) / 2 + 0.575, r[3])  # ink width of a turned text
            if P.free(r) and ok(r):
                P.texts.append(r)
                moved += 1
                return
            print("silk: %s first-choice spot taken (free %s, own %s) %s" % (fp.GetReference(), P.free(r), ok(r), [t for t in P.texts if hit(r, grow(t, TXT_GAP))][:3]))
        if P.place(ref, court(fp), ok=ok):
            moved += 1
        else:
            ref.SetVisible(False)
            hidden.append(fp.GetReference())

    def label(text, box, near, ok=None, h=None):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        style(t)
        if h:
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(h), pcbnew.FromMM(h)))
            t.SetTextThickness(pcbnew.FromMM(0.12))
        if P.place(t, box, ok=ok):
            board.Add(t)
            items.append(t)
            labels.append((text, near, "placed"))
        else:
            labels.append((text, near, "NO ROOM"))
    # L5F: R62 / R63 references first (crowded strip; they must sit beside their own part, verifier L5 r4 minor)
    for r_ in OWN_REFS:
        place_ref(board.FindFootprintByReference(r_))
    # 1. board name, revision, date: the first free spot of a 1 mm scan, nearest to the preferred corner
    t = pcbnew.PCB_TEXT(board)
    t.SetText("RV1106 Rev A 2026-11")
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.5), pcbnew.FromMM(1.5)))
    t.SetTextThickness(pcbnew.FromMM(0.2))
    t.SetKeepUpright(True)
    spots = sorted(((x, y) for x in range(8, 73) for y in range(6, 75)),
                   key=lambda p: math.hypot(p[0] - 30.0, p[1] - 47.0))
    done = None
    for (x, y) in spots:
        t.SetTextAngleDegrees(0)
        t.SetPosition(bl.to_page(x, y))
        r = bb_mm(t.GetBoundingBox())
        if P.free(r):
            P.texts.append(r)
            board.Add(t)
            items.append(t)
            done = (x, y)
            break
    labels.append((t.GetText(), "board", "placed at (%d, %d)" % done if done else "NO ROOM"))
    # 2. test pads: reference (TP number) and net label; 3. buttons and LEDs; 4. header pin numbers; 5. 'B' marks
    tps = sorted([f for f in board.GetFootprints() if f.GetReference().startswith("TP")],
                 key=lambda f: int(f.GetReference()[2:]))
    # round 2 (verifier minor ui): one label per test pad and LED that carries the TP number and the short net name
    # together ("TP12" over "EN_N"), placed beside its own part only: the label rectangle must be nearer to its own
    # courtyard (<= 0.6 mm) than to the courtyard of any other test pad, LED or button, by at least 0.3 mm. The TP's
    # reference text itself is hidden (the label replaces it). A label without such a spot goes to F.Fab (assembly
    # drawing) and is listed.
    owners = {f.GetReference(): court(f) for f in tps}
    for ref in PART_LABEL:
        owners[ref] = court(board.FindFootprintByReference(ref))

    def rdist(a, b):
        dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
        dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
        return math.hypot(dx, dy)

    def own_ok(ref, dmax=0.6, margin=0.3):
        def ok(r):
            d0 = rdist(r, owners[ref])
            return d0 <= dmax and all(rdist(r, b) >= d0 + margin for k, b in owners.items() if k != ref)
        return ok

    def label_own(text, ref):
        """strict (<= 0.6 mm from its own part, >= 0.3 mm nearer than to any other), then relaxed (<= 1.2 mm,
        >= 0.15 mm nearer): the label is always nearest to its own part"""
        label(text, owners[ref], ref, ok=own_ok(ref))
        if labels[-1][2] == "NO ROOM":
            labels.pop()
            label(text, owners[ref], ref, ok=own_ok(ref, 1.2, 0.15))
        if labels[-1][2] == "NO ROOM" and ref in SMALL_OK:
            # D-114 g (owner approval asked): 0.8 mm text where 1.0 mm has no room next to its own part (LED row:
            # 1.65 mm between the board edge and the LED silk, a 1.0 mm text box is 1.7 mm tall)
            labels.pop()
            label(text, owners[ref], ref, ok=own_ok(ref, 1.2, 0.15), h=SMALL_H)
            if labels[-1][2] != "NO ROOM":
                labels[-1] = (labels[-1][0], labels[-1][1], "placed %.1f mm" % SMALL_H)
        if labels[-1][2] == "NO ROOM" and ref in SMALL_OK:
            # round 3 (STAT open since round 1): the middle LED of the row is as near to its neighbours as the label
            # can be; the label may be equally near (not nearer) to them, centred over its own LED
            labels.pop()
            label(text, owners[ref], ref, ok=own_ok(ref, 1.2, 0.0), h=SMALL_H)
            if labels[-1][2] != "NO ROOM":
                labels[-1] = (labels[-1][0], labels[-1][1], "placed %.1f mm (centred, row neighbours equally near)"
                              % SMALL_H)

    fab = []
    numonly = []
    bare = []
    for fp in tps:
        ref = fp.GetReference()
        text = ref + ("\n" + TP_LABEL[ref] if ref in TP_LABEL else "")
        fp.Reference().SetVisible(False)
        label_own(text, ref)
        if labels[-1][2] == "NO ROOM":
            # L5F (D-H6 item 10): within 2.0 mm of its own pad and nearer to it than to any other labelled part
            labels.pop()
            label(text, owners[ref], ref, ok=own_ok(ref, 2.0, 0.05))
            if labels[-1][2] != "NO ROOM":
                labels[-1] = (labels[-1][0], labels[-1][1], "placed (<= 2.0 mm)")
        if labels[-1][2] == "NO ROOM":
            # round 3 (verifier minor ui): at least the TP number on the silkscreen next to its own pad (the net name
            # goes to F.Fab with it); only a TP with no room even for its number is F.Fab-only
            labels.pop()
            label_own(ref, ref)
            if labels[-1][2] == "NO ROOM":
                labels.pop()
                label(ref, owners[ref], ref, ok=own_ok(ref, 2.0, 0.05))
            if labels[-1][2] != "NO ROOM":
                labels[-1] = (labels[-1][0], labels[-1][1], "placed (number only)")
                numonly.append(ref)
        if labels[-1][2] == "NO ROOM":
            # round 2 (D-118 d, verifier minor pmu): the bare number ("3", "13") at 1.0 mm / 0.15 mm, beside its own
            # pad (<= 2.0 mm, nearer to it than to any other labelled part); "TP<n>" and the net go to F.Fab
            labels.pop()
            label(ref[2:], owners[ref], ref, ok=own_ok(ref, 2.0, 0.05))
            if labels[-1][2] == "NO ROOM":
                # fine search: every 0.05 mm within 2.6 mm of the pad centre, 0 / 90 deg, nearest first
                labels.pop()
                t = pcbnew.PCB_TEXT(board)
                t.SetText(ref[2:])
                t.SetLayer(pcbnew.F_SilkS)
                style(t)
                c = owners[ref]
                cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
                ok_ = own_ok(ref, 2.0, 0.05)
                cand = sorted(((cx + 0.05 * i, cy + 0.05 * j) for i in range(-52, 53) for j in range(-52, 53)),
                              key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
                done_ = False
                for ang in (0, 90):
                    t.SetTextAngleDegrees(0)
                    t.SetPosition(bl.to_page(0, 0))
                    w = pcbnew.ToMM(t.GetBoundingBox().GetWidth())     # ink box: text width x (1.0 + stroke)
                    t.SetTextAngleDegrees(ang)
                    hw, hh = (w / 2, 0.575) if ang == 0 else (0.575, w / 2)
                    for q in cand:
                        t.SetPosition(bl.to_page(*q))
                        r = (q[0] - hw, q[1] - hh, q[0] + hw, q[1] + hh)
                        if P.free(r) and ok_(r):
                            P.texts.append(r)
                            board.Add(t)
                            items.append(t)
                            done_ = True
                            break
                    if done_:
                        break
                labels.append((ref[2:], ref, "placed" if done_ else "NO ROOM"))
            if labels[-1][2] != "NO ROOM":
                labels[-1] = (labels[-1][0], labels[-1][1], "placed (bare number)")
                numonly.append(ref)
                bare.append(ref)
        if labels[-1][2] == "NO ROOM" or ref in bare:
            if ref not in bare:
                fab.append(ref)
            t = pcbnew.PCB_TEXT(board)
            t.SetText(text)
            t.SetLayer(pcbnew.F_Fab)
            style(t)
            c = owners[ref]
            t.SetPosition(bl.to_page((c[0] + c[2]) / 2, (c[1] + c[3]) / 2))
            board.Add(t)
            items.append(t)
    for ref, text in sorted(PART_LABEL.items()):
        fp = board.FindFootprintByReference(ref)
        if ref in SMALL_OK:
            # L5F (D-H6 item 6, D-117 i): the LED labels at 1.0 mm / 0.15 mm in one row above the LEDs (y 1.30; ink
            # 0.72-1.88, board edge >= 0.5 mm, LED silk below); STAT centred over LED2, PWR / ETH set 0.2 mm off its
            # ends (the 1.0 mm words are wider than the 3.2 mm LED pitch). Ink box = text width x (1.0 + stroke).
            # The LED references stay hidden (kept on F.Fab).
            if ref != "LED2":
                continue                      # placed together with LED2
            row = []
            c2 = owners["LED2"]
            mid = (c2[0] + c2[2]) / 2

            def mk(word, x):
                t = pcbnew.PCB_TEXT(board)
                t.SetText(word)
                t.SetLayer(pcbnew.F_SilkS)
                style(t)
                t.SetTextAngleDegrees(0)
                t.SetPosition(bl.to_page(x, 1.30))
                w = pcbnew.ToMM(t.GetBoundingBox().GetWidth())
                return t, w
            t2, w2 = mk("STAT", mid)
            t1, w1 = mk("PWR", 0)
            t3, w3 = mk("ETH", 0)
            t1.SetPosition(bl.to_page(mid - w2 / 2 - 0.2 - w1 / 2, 1.30))
            t3.SetPosition(bl.to_page(mid + w2 / 2 + 0.2 + w3 / 2, 1.30))
            for t, w, led in ((t1, w1, "LED1"), (t2, w2, "LED2"), (t3, w3, "LED3")):
                x = bl.to_board(t.GetPosition())[0]
                r = (x - w / 2, 1.30 - 0.575, x + w / 2, 1.30 + 0.575)
                ok = P.free(r)
                if ok:
                    P.texts.append(r)
                    board.Add(t)
                    items.append(t)
                labels.append((t.GetText(), led, "placed 1.0 mm (row above the LEDs, x %.2f)" % x if ok else "NO ROOM"))
            for led in SMALL_OK:
                board.FindFootprintByReference(led).Reference().SetVisible(False)
                hidden.append(led)
            continue
        label_own(text, ref)  # the function name first (layout.md §1), then the reference
        place_ref(fp)
    # mounting holes: the reference is not printed (it is not a part to place or probe; verifier round 1: H2's
    # reference landed 5.8 mm from its hole)
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("H") and fp.GetReference()[1:].isdigit():
            fp.Reference().SetVisible(False)
    j5 = board.FindFootprintByReference("J5")
    for num in ("1", "2", "39", "40"):
        p = [q for q in j5.Pads() if q.GetNumber() == num][0]
        xs = [q[0] for q in bl.pad_polygon(p)]
        ys = [q[1] for q in bl.pad_polygon(p)]
        label(num, (min(xs), min(ys), max(xs), max(ys)), "J5.%s" % num)
    for ref in ("JP1", "R29", "R30", "R31"):
        fp = board.FindFootprintByReference(ref)
        for p in fp.Pads():
            if p.GetNetname().endswith("_BUCK"):
                xs = [q[0] for q in bl.pad_polygon(p)]
                ys = [q[1] for q in bl.pad_polygon(p)]
                label("B", (min(xs), min(ys), max(xs), max(ys)), "%s.%s %s" % (ref, p.GetNumber(), p.GetNetname()))
    # 6. every other reference, larger parts first
    rest = [f for f in board.GetFootprints() if not f.GetReference().startswith("TP") and
            f.GetReference() not in PART_LABEL and f.GetReference() not in OWN_REFS]
    for fp in sorted(rest, key=lambda f: (f.GetReference() not in OWN_REFS,
                                          -((court(f)[2] - court(f)[0]) * (court(f)[3] - court(f)[1])),
                                          f.GetReference())):
        place_ref(fp)
    rl.group(board, GROUP, items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    out = {"refs_placed": moved, "refs_hidden": hidden, "labels": labels, "tp_labels_on_fab": fab, "tp_number_only": numonly, "tp_bare_number": bare, "footprint_silk": trim}
    json.dump(out, open(os.path.join(bl.PCB_DIR, "l5", "silk.json"), "w"), indent=1)
    print("silk: footprint silk near pads: %s" % trim)
    print("silk: %d references placed, %d hidden (%s); %d labels placed, %d without room: %s" % (
        moved, len(hidden), " ".join(hidden), sum(1 for x in labels if x[2] != "NO ROOM"),
        sum(1 for x in labels if x[2] == "NO ROOM"), [x[:2] for x in labels if x[2] == "NO ROOM"]))


if __name__ == "__main__":
    main()
