#!/usr/bin/env python3
"""Layout phase L5G (D-H7 item 2, D-120): silk labels beside their own part. Runs after l5g_fix.py / fill_zones.py.

    $PY design/pcb/scripts/l5g_silk.py          # edits the saved board; writes design/pcb/l5g/silk.json

Rule (l5g_silklib.py, checked by l5gcheck.py L5G-silk): every visible F.SilkS reference, test-pad label, function label
and pin marker is nearer (ink box to copper) to its own part (pin marker: its own pad) than to ANY other part's copper by
>= 0.20 mm (round 2; was 0.05), and within 2.0 mm of it (3.0 mm for parts > 5 mm); a bare-number label of an
upper-row test pad never sits between its row and the test-pad row below (round 2: "3" / TP3 above TP14).
1. The tooling-hole references TH2 / TH3 / TH4 (printed on the board next to the rail holes) are hidden.
2. Every label that breaks the rule is moved: candidate centres every 0.1 mm around its own copper, 0 and 90 deg; a
   candidate must be free as in l5_silk.py (>= 0.15 mm from every pad / mask opening, off footprint silk, off the
   bottom-terminated parts, >= 0.15 mm from every other text, >= 0.5 mm inside the board, outside the M3 keep-outs)
   and meet the rule; preferred: >= 0.25 mm margin to the nearest other copper, then nearest to its own copper; else
   the largest margin. Larger parts first.
   Labels that already pass but with < 0.25 mm margin (e.g. "3" between TP3 and TP14) are moved only to a spot
   with >= 0.25 mm margin, else left.
   A bare test-pad number with no such spot is tried as "TP<n>" (round 2: "3" -> "TP3").
3. A label with no such spot is hidden: a reference keeps its F.Fab copy; a board label moves to F.Fab. Counted in
   silk.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import l5_silk as L5  # noqa: E402
import l5g_silklib as S  # noqa: E402

import pcbnew  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "l5g", "silk.json")
STEP = 0.1
PREF = 0.25
TROWS = []          # test-pad rows (l5g_silklib.tp_rows), set in main()


def bottom_boxes(board):
    """courtyard and F.Fab body boxes of the bottom-terminated parts, as l5check.py L5-silk measures them (no text cell
    box may overlap them)"""
    out = []
    for fp in board.GetFootprints():
        if not L5.is_bottom_terminated(fp):
            continue
        for lay in (pcbnew.F_CrtYd, pcbnew.F_Fab):
            xs, ys = [], []
            for g in fp.GraphicalItems():
                if g.GetLayer() == lay and g.GetClass() != "PCB_TEXT":
                    bb = g.GetBoundingBox()
                    for q in (bb.GetOrigin(), bb.GetEnd()):
                        x, y = bl.to_board(q)
                        xs.append(x)
                        ys.append(y)
            if xs:
                out.append((min(xs) - 0.02, min(ys) - 0.02, max(xs) + 0.02, max(ys) + 0.02))
    return out


def search(item, P, cu, ref, padnum, size, lim, own_box, bots):
    """best spot for item (or None): see the module docstring"""
    ox0, oy0, ox1, oy1 = own_box
    best = None
    for ang in (0, 90):
        item.SetTextAngleDegrees(ang)
        item.SetPosition(bl.to_page(0, 0))
        ib = S.ink_box(item)
        hw, hh = (ib[2] - ib[0]) / 2, (ib[3] - ib[1]) / 2
        cx0, cy0 = (ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2      # ink centre relative to the position
        cb = L5.bb_mm(item.GetBoundingBox())                    # text cell box (l5check L5-silk), relative
        cb = (cb[0] - cx0, cb[1] - cy0, cb[2] - cx0, cb[3] - cy0)
        ext = lim + max(hw, hh) + 0.1
        lbots = [b for b in bots if b[2] > ox0 - ext - 2 and b[0] < ox1 + ext + 2 and b[3] > oy0 - ext - 2 and
                 b[1] < oy1 + ext + 2]
        local = [o for o in P.obst if o[2] > ox0 - ext - 1 and o[0] < ox1 + ext + 1 and o[3] > oy0 - ext - 1 and
                 o[1] < oy1 + ext + 1]
        save = P.obst
        P.obst = local
        nx = int((ox1 - ox0 + 2 * ext) / STEP) + 1
        ny = int((oy1 - oy0 + 2 * ext) / STEP) + 1
        for i in range(nx):
            for j in range(ny):
                cx, cy = ox0 - ext + i * STEP, oy0 - ext + j * STEP
                r = (cx - hw, cy - hh, cx + hw, cy + hh)
                if S._rd(r, (ox0, oy0, ox1, oy1)) > lim:
                    continue
                if not P.free(r):
                    continue
                rc = (cx + cb[0], cy + cb[1], cx + cb[2], cy + cb[3])
                if any(L5.hit(rc, b) for b in lbots):
                    continue
                m = S.measure(r, ref, padnum, cu, size, look=PREF)
                if not m[3]:
                    continue
                if S.band_bad(item.GetText(), ref, r, TROWS):
                    continue
                margin = m[1][0] - m[0]
                key = (0, round(m[0], 3), -margin) if margin >= PREF else (1, -margin, m[0])
                if best is None or key < best[0]:
                    best = (key, ang, (cx - cx0, cy - cy0), r, m)
        P.obst = save
    return best


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    log = {"th_hidden": [], "moved": [], "hidden": [], "to_fab": []}
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("TH") and fp.Reference().IsVisible():
            fp.Reference().SetVisible(False)
            log["th_hidden"].append(fp.GetReference())
    cu = S.copper(board)
    TROWS[:] = S.tp_rows(cu)
    bots = bottom_boxes(board)
    P = L5.Placer(board)
    rows = S.evaluate(board)
    P.texts = [r[4] for r in rows]
    bad = [r for r in rows if not r[8] and r[2] not in (None, "BOARD")]
    bad.sort(key=lambda r: (-S.size_of(board, r[2]), r[2], r[1]))
    # labels that pass with a thin margin (< PREF, e.g. "3" between TP3 and TP14) move only to a spot with >= PREF
    weak = [r for r in rows if r[8] and r[2] not in (None, "BOARD") and r[6] and r[6][0] - r[5] < PREF]
    weak.sort(key=lambda r: (-S.size_of(board, r[2]), r[2], r[1]))
    log["improved"] = []
    for kind, text, ref, padnum, box, d_own, other, lim, ok, why, item in weak:
        P.texts = [t for t in P.texts if t != box]
        own = [b for n, p, b, _ in cu[ref] if padnum is None or n == padnum]
        obox = (min(b[0] for b in own), min(b[1] for b in own), max(b[2] for b in own), max(b[3] for b in own))
        size = S.size_of(board, ref)
        lim = S.LIM_BIG if (padnum is None and size > S.BIG) else S.LIM_SMALL
        pos0, ang0 = item.GetPosition(), item.GetTextAngleDegrees()
        best = search(item, P, cu, ref, padnum, size, lim, obox, bots)
        if best and best[0][0] == 0:
            _k, ang, (px, py), r, m = best
            item.SetTextAngleDegrees(ang)
            item.SetPosition(bl.to_page(px, py))
            log["improved"].append({"label": text, "owner": ref + ("." + padnum if padnum else ""),
                                    "margin_before": round(other[0] - d_own, 3), "at": [round(px, 2), round(py, 2), ang],
                                    "own_mm": round(m[0], 3)})
        else:
            item.SetTextAngleDegrees(ang0)
            item.SetPosition(pos0)
        P.texts.append(S.ink_box(item))
    for kind, text, ref, padnum, box, d_own, other, lim, ok, why, item in bad:
        P.texts = [t for t in P.texts if t != box]
        own = [b for n, p, b, _ in cu[ref] if padnum is None or n == padnum]
        ox0, oy0 = min(b[0] for b in own), min(b[1] for b in own)
        ox1, oy1 = max(b[2] for b in own), max(b[3] for b in own)
        size = S.size_of(board, ref)
        lim = S.LIM_BIG if (padnum is None and size > S.BIG) else S.LIM_SMALL
        pos0 = item.GetPosition()
        ang0 = item.GetTextAngleDegrees()
        best = search(item, P, cu, ref, padnum, size, lim, (ox0, oy0, ox1, oy1), bots)
        if best is None and kind == "board" and text.startswith("TP") and "\n" in text:
            item.SetText(text.split("\n")[0][2:])       # D-118 d fallback: the bare TP number
            best = search(item, P, cu, ref, padnum, size, lim, (ox0, oy0, ox1, oy1), bots)
            if best is None:
                item.SetText(text)
            else:
                text = text + " -> bare number"
        if best is None and kind == "board" and text.isdigit() and ref and ref.startswith("TP"):
            # round 2 (verifier minor, "3" / TP3): a bare number with no spot (margin or test-pad-row band) is
            # printed in full, "TP<n>", which cannot be read as the label of another pad
            item.SetText("TP" + text)
            best = search(item, P, cu, ref, padnum, size, lim, (ox0, oy0, ox1, oy1), bots)
            if best is None:
                item.SetText(text)
            else:
                text = text + " -> TP" + text
        if best:
            _k, ang, (px, py), r, m = best
            item.SetTextAngleDegrees(ang)
            item.SetPosition(bl.to_page(px, py))
            P.texts.append(S.ink_box(item))
            log["moved"].append({"label": text, "owner": ref + ("." + padnum if padnum else ""), "why": why,
                                 "at": [round(px, 2), round(py, 2), ang], "own_mm": round(m[0], 3),
                                 "nearest_other": [round(m[1][0], 3), m[1][1]]})
        else:
            item.SetTextAngleDegrees(ang0)
            item.SetPosition(pos0)
            if kind == "board":
                item.SetLayer(pcbnew.F_Fab)
                log["to_fab"].append({"label": text, "owner": ref, "why": why})
            else:
                item.SetVisible(False)
                log["hidden"].append({"label": text, "owner": ref, "why": why})
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(log, open(OUT, "w"), indent=1)
    print("l5g_silk: %d thin-margin labels moved to >= %.2f mm margin" % (len(log["improved"]), PREF))
    print("l5g_silk: TH texts hidden %s; %d labels moved, %d references hidden (F.Fab), %d board labels to F.Fab: %s" % (
        log["th_hidden"], len(log["moved"]), len(log["hidden"]), len(log["to_fab"]),
        " ".join(h["label"].split("\n")[0] for h in log["hidden"] + log["to_fab"])))


if __name__ == "__main__":
    main()
