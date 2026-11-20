"""Layout phase L5G (D-H7 item 2, D-120): which part every visible F.SilkS text belongs to, and how near its ink is
to its own copper and to every other part's copper. Used by l5g_silk.py (the fix) and l5gcheck.py (L5G-silk FAIL).

Rule (D-H7, gate TP-L5G): every visible F.SilkS reference, test-pad number / label, function label and pin marker is
nearer (ink box = bounding box of the stroked glyphs, to copper = pad outlines on F.Cu, THT pads included) to its own
part than to ANY other part's copper (labelled or not), by >= MARGIN, and within 2.0 mm of its own copper (3.0 mm
for parts whose courtyard is > 5 mm in either direction). For a pin marker (J5 pin numbers, the "B" buck-side marks)
"own copper" is the one pad it marks, and every other pad, of the same part too, counts as "other".
Owner of a board text (group L5_SILK / L5G_SILK): "TP<n>..." and bare numbers -> TP<n> (the J5 numbers 1, 2, 39, 40
-> J5 pin <n>); "B" -> the nearest *_BUCK pad of JP1 / R29 / R30 / R31; the function labels POWER / RESET / MASKROM /
PWR / STAT / ETH -> SW1 / SW2 / SW3 / LED1 / LED2 / LED3; the board name is not a part label (exempt, reported).
Test-pad rows (round 2, verifier minor on "3" / TP3): where two rows of test pads face each other, the bottom row is
labelled from above, so a bare-number label of an upper-row pad must not sit in the band between the two rows (it
would read as the label of the pad below it).
"""
import math
import re

import boardlib as bl

import pcbnew

MARGIN = 0.20          # mm: own copper must be nearer than any other copper by at least this (round 2: was 0.05,
                       # verifier minor: C28 / C48 0.08, R44 0.11 mm margins were near-equidistant)
LIM_SMALL, LIM_BIG, BIG = 2.0, 3.0, 5.0
FUNC = {"POWER": "SW1", "RESET": "SW2", "MASKROM": "SW3", "PWR": "LED1", "STAT": "LED2", "ETH": "LED3"}
J5_PINS = ("1", "2", "39", "40")
B_PARTS = ("JP1", "R29", "R30", "R31")
BOARD_NAME = re.compile(r"^RV1106 Rev")


def ink_box(t):
    ps = pcbnew.SHAPE_POLY_SET()
    t.TransformShapeToPolygon(ps, pcbnew.F_SilkS, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    bb = ps.BBox()
    x0, y0 = bl.to_board(bb.GetOrigin())
    x1, y1 = bl.to_board(bb.GetEnd())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def rect_poly(r):
    return [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]


def copper(board):
    """{ref: [(pad number, polygon, bbox)]} of every footprint's F.Cu copper (THT pads included)"""
    out = {}
    for fp in board.GetFootprints():
        lst = []
        for p in fp.Pads():
            if not p.IsOnLayer(pcbnew.F_Cu):
                continue
            poly = bl.pad_polygon(p)
            xs, ys = [q[0] for q in poly], [q[1] for q in poly]
            lst.append((p.GetNumber(), poly, (min(xs), min(ys), max(xs), max(ys)), p.GetNetname()))
        if lst:
            out[fp.GetReference()] = lst
    return out


def _rd(a, b):
    return math.hypot(max(0.0, max(a[0], b[0]) - min(a[2], b[2])), max(0.0, max(a[1], b[1]) - min(a[3], b[3])))


def dist_box(r, poly, pb):
    if _rd(r, pb) > 6.0:
        return 99.0
    return bl.poly_dist(rect_poly(r), poly)


def owner_of_board_text(text, box, cu):
    """(ref, pad or None) or None (board name / unknown)"""
    s = text.split("\n")[0]
    if BOARD_NAME.match(s):
        return ("BOARD", None)
    m = re.match(r"^TP(\d+)$", s)
    if m:
        return ("TP" + m.group(1), None)
    if s in FUNC:
        return (FUNC[s], None)
    if s in J5_PINS:
        return ("J5", s)
    if s.isdigit():
        return ("TP" + s, None)
    if s == "B":
        best = None
        for ref in B_PARTS:
            for num, poly, pb, net in cu.get(ref, []):
                if net.endswith("_BUCK"):
                    d = dist_box(box, poly, pb)
                    if best is None or d < best[0]:
                        best = (d, ref, num)
        return (best[1], best[2]) if best else None
    return None


def labels(board, cu=None):
    """[(kind, text, owner ref, owner pad or None, ink box, item)] of every visible F.SilkS text"""
    cu = cu or copper(board)
    out = []
    for fp in board.GetFootprints():
        for f in fp.GetFields():
            if f.IsVisible() and f.GetLayer() == pcbnew.F_SilkS and f.GetText().strip():
                out.append(("field", f.GetText(), fp.GetReference(), None, ink_box(f), f))
        for t in fp.GraphicalItems():
            if t.GetClass() == "PCB_TEXT" and t.GetLayer() == pcbnew.F_SilkS and t.IsVisible():
                out.append(("fptext", t.GetText(), fp.GetReference(), None, ink_box(t), t))
    for d in board.GetDrawings():
        if d.GetClass() in ("PCB_TEXT", "PCB_TEXTBOX") and d.GetLayer() == pcbnew.F_SilkS and d.IsVisible():
            box = ink_box(d)
            o = owner_of_board_text(d.GetText(), box, cu)
            out.append(("board", d.GetText(), o[0] if o else None, o[1] if o else None, box, d))
    return out


def size_of(board, ref):
    fp = board.FindFootprintByReference(ref)
    c = bl.courtyard_bbox(fp) if fp else None
    return max(c[2] - c[0], c[3] - c[1]) if c else 0.0


def measure(box, ref, padnum, cu, size, look=0.0):
    """(d_own, (d_other, 'REF.pad'), limit, ok, why); other copper is searched up to d_own + max(MARGIN, look) + 0.01
    (99.0 = none that near)"""
    own = [(n, p, b) for n, p, b, _ in cu.get(ref, []) if padnum is None or n == padnum]
    if not own:
        return (None, None, None, False, "owner %s.%s has no F.Cu copper" % (ref, padnum))
    d_own = min(dist_box(box, p, b) for n, p, b in own)
    other = (99.0, "")
    for r2, lst in cu.items():
        for n, p, b, _ in lst:
            if r2 == ref and (padnum is None or n == padnum):
                continue
            if _rd(box, b) > d_own + max(MARGIN, look) + 0.01:
                continue
            d = dist_box(box, p, b)
            if d < other[0]:
                other = (d, "%s.%s" % (r2, n))
    lim = LIM_BIG if (padnum is None and size > BIG) else LIM_SMALL
    ok = d_own <= lim + 1e-6 and other[0] >= d_own + MARGIN - 1e-6
    why = "" if ok else ("%.2f mm from own copper > %.1f" % (d_own, lim) if d_own > lim + 1e-6 else
                         "nearer %s (%.2f) than own (%.2f)" % (other[1], other[0], d_own))
    return (d_own, other, lim, ok, why)


def tp_rows(cu):
    """[(y, x0, x1, pad top, pad bottom, [refs])] rows of >= 2 single-pad test pads at the same y (0.2 mm)"""
    tps = []
    for ref, lst in cu.items():
        if re.match(r"^TP\d+$", ref) and len(lst) == 1:
            b = lst[0][2]
            tps.append(((b[1] + b[3]) / 2, (b[0] + b[2]) / 2, b, ref))
    tps.sort()
    rows, cur = [], []
    for t in tps:
        if cur and t[0] - cur[0][0] > 0.2:
            rows.append(cur)
            cur = []
        cur.append(t)
    rows.append(cur)
    out = []
    for r in rows:
        if len(r) >= 2:
            out.append((sum(t[0] for t in r) / len(r), min(t[2][0] for t in r), max(t[2][2] for t in r),
                        min(t[2][1] for t in r), max(t[2][3] for t in r), [t[3] for t in r]))
    return out


def band_bad(text, ref, box, rows):
    """'' or why: a bare-number label of an upper-row test pad lying between its row and the row below"""
    s = text.split("\n")[0]
    if not s.isdigit() or not ref or not ref.startswith("TP"):
        return ""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for r in rows:
        if ref not in r[5]:
            continue
        for r2 in rows:
            if r2[0] > r[0] + 0.2 and r2[0] - r[0] < 6.0 and r2[1] < r[2] and r[1] < r2[2]:
                if r[4] <= cy <= r2[3] and max(r[1], r2[1]) - 1.0 <= cx <= min(r[2], r2[2]) + 1.0:
                    return "between the test-pad rows of %s and %s (reads as a label of the row below)" % (
                        ref, "/".join(r2[5]))
    return ""


def evaluate(board):
    cu = copper(board)
    trows = tp_rows(cu)
    rows = []
    for kind, text, ref, padnum, box, item in labels(board, cu):
        if ref == "BOARD":
            rows.append((kind, text, ref, padnum, box, None, None, None, True, "board name (not a part label)", item))
            continue
        if ref is None:
            rows.append((kind, text, ref, padnum, box, None, None, None, False, "no owner", item))
            continue
        d_own, other, lim, ok, why = measure(box, ref, padnum, cu, size_of(board, ref), look=1.0)
        bb = band_bad(text, ref, box, trows)
        if bb:
            ok, why = False, (why + "; " if why else "") + bb
        rows.append((kind, text, ref, padnum, box, d_own, other, lim, ok, why, item))
    return rows
