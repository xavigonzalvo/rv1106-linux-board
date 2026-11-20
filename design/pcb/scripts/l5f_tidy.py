#!/usr/bin/env python3
"""Layout phase L5F step 3 (KiCad Python; D-H6 items 8 and 10, D-117 g): copper clean-up on the routed board.

    $PY design/pcb/scripts/l5f_tidy.py          # edits the saved board; writes design/pcb/l5f/tidy.json

1. Escape overshoot stubs (KiCad track_dangling): the L3 escape chains end at their old gate point, 0.1-0.25 mm past the
   point where the continuing L4 / L5 lane starts on the chain's last piece. For every track end that touches no other
   item of its net (end point, via, pad), the nearest end point of another same-net track lying on this piece's centre
   line becomes the piece's new end (the piece is trimmed back to the joint); a piece trimmed to zero is removed.
2. Stub vias (KiCad via_dangling: VCC_DDR (39.70, 34.03), VCC3V3_RTC (35.38, 41.65)): each is the first of the two
   vias of a U9 supply-pin layer change (layout.md §3 >= 2 vias) and had copper on L1 only; an L4 link to its
   partner via makes it a real second via (removing it would leave the layer change with one via).
3. Neck-down at small passives (tombstoning, D-H6 item 8): the VDD_0V9_BUCK branch L1.2 -> R17.1 -> C29.1 (divider
   top and feed-forward cap, uA) is 0.40 mm over its length; every other F.Cu track wider than the pad's narrow side
   + 0.02 mm whose copper reaches a two-pad 0402 / 0603 pad of its net gets a 0.40 mm neck (or the pad width when
   narrower) long enough that the wide copper (round end included) stays >= 0.10 mm outside the pad (round 2,
   D-118 e: the C16.1 neck was 0.425 mm and the 0.8 mm end still overlapped the pad).
4. PB_INT_N (D-H6 item 10): the 46.3 deg L5_FINISH piece (42.20, 41.15)-(44.81, 43.89) becomes a 0.13 mm vertical
   + a 45 deg piece.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "l5f", "tidy.json")
# off-45 L5 pieces snapped to a straight + 45 deg pair (PB_INT_N: verifier L5 r4 minor; NPOR at C71.1: same check)
SNAP = (((42.20, 41.15), (44.81, 43.89)), ((41.82, 28.29), (42.53, 29.16)))
STUB_VIAS = (("VCC_DDR", 39.70, 34.03), ("VCC3V3_RTC", 35.38, 41.65))
TOL = 0.0015


def P(v):
    return bl.to_board(v)


def poly_dist(q, poly):
    """distance from point q to a pad polygon (0 inside)"""
    if bl._inside(q[0], q[1], poly):
        return 0.0
    best = 9e9
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2))
        best = min(best, math.hypot(q[0] - ax - u * dx, q[1] - ay - u * dy))
    return best


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, "L5F_TIDY")
    log = []
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pads.setdefault(p.GetNetname(), []).append((bl.pad_polygon(p), p, fp))
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    bynet = {}
    for t in tracks:
        bynet.setdefault(t.GetNetname(), []).append(t)
    vby = {}
    for v in vias:
        vby.setdefault(v.GetNetname(), []).append(v)

    def connected(t, q):
        n = t.GetNetname()
        for o in bynet.get(n, []):
            if o is t or o.GetLayer() != t.GetLayer():
                continue
            for e in (P(o.GetStart()), P(o.GetEnd())):
                if math.hypot(e[0] - q[0], e[1] - q[1]) < TOL:
                    return True
        hw = pcbnew.ToMM(t.GetWidth()) / 2
        for v in vby.get(n, []):           # the end on (or overlapping) a via of the net
            if math.hypot(P(v.GetPosition())[0] - q[0], P(v.GetPosition())[1] - q[1]) < \
                    pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2 + hw:
                return True
        for poly, p, fp in pads.get(n, []):
            if p.IsOnLayer(t.GetLayer()) and (bl._inside(q[0], q[1], poly) or min(
                    bl._seg_pt(q[0], q[1], poly[i][0], poly[i][1], poly[(i + 1) % len(poly)][0],
                               poly[(i + 1) % len(poly)][1]) for i in range(len(poly))) < hw):
                return True
        return False
    # 1. overshoot stubs
    items = []
    dead = []
    trimmed = 0
    def grp(o):
        g = o.GetParentGroup()
        return g.GetName() if g else ""
    for t in tracks:
        if t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu) or grp(t) != "L3_ESCAPE":
            continue
        a, b = P(t.GetStart()), P(t.GetEnd())
        for which, q, o in (("s", a, b), ("e", b, a)):
            if connected(t, q):
                continue
            best = None
            for u in bynet.get(t.GetNetname(), []):
                if u is t or u.GetLayer() != t.GetLayer() or grp(u) == "L3_ESCAPE":
                    continue
                for e in (P(u.GetStart()), P(u.GetEnd())):
                    if bl._seg_pt(e[0], e[1], a[0], a[1], b[0], b[1]) < 0.005 and \
                            math.hypot(e[0] - q[0], e[1] - q[1]) < 0.6:
                        d = math.hypot(e[0] - q[0], e[1] - q[1])
                        if best is None or d < best[0]:
                            best = (d, e)
            if best is None:
                continue
            e = best[1]
            if math.hypot(e[0] - o[0], e[1] - o[1]) < 0.001:
                dead.append(t)
                log.append("removed stub %s (%.3f,%.3f)-(%.3f,%.3f)" % (t.GetNetname(), a[0], a[1], b[0], b[1]))
            else:
                (t.SetStart if which == "s" else t.SetEnd)(bl.to_page(*e))
                trimmed += 1
                log.append("trimmed %s end (%.3f,%.3f) -> (%.3f,%.3f)" % (t.GetNetname(), q[0], q[1], e[0], e[1]))
            break
    # 2. stub vias: each is one of the two vias of a U9 supply-pin layer change (layout.md §3: >= 2 vias) but had
    # copper on L1 only; an L4 link to its partner via (0.30 mm, the L4 width of the feed) makes both vias carry the
    # current and ends the via_dangling warning
    nvia = 0
    for net, x, y in STUB_VIAS:
        mine = [v for v in vby.get(net, []) if math.hypot(P(v.GetPosition())[0] - x, P(v.GetPosition())[1] - y) < 0.02]
        if not mine:
            continue
        vx, vy = P(mine[0].GetPosition())
        onB = any(t.GetLayer() == pcbnew.B_Cu and any(math.hypot(e[0] - vx, e[1] - vy) < TOL for e in (
            P(t.GetStart()), P(t.GetEnd()))) for t in bynet.get(net, []))
        if onB:
            continue
        part = min((v for v in vby.get(net, []) if v is not mine[0]),
                   key=lambda v: math.hypot(P(v.GetPosition())[0] - vx, P(v.GetPosition())[1] - vy))
        px, py = P(part.GetPosition())
        dx, dy = px - vx, py - vy
        if abs(abs(dx) - abs(dy)) < 1e-3 or abs(dx) < 1e-3 or abs(dy) < 1e-3:
            pts = [(vx, vy), (px, py)]
        elif abs(dy) > abs(dx):            # straight piece, then 45 deg into the partner via
            pts = [(vx, vy), (vx, py - math.copysign(abs(dx), dy)), (px, py)]
        else:
            pts = [(vx, vy), (px - math.copysign(abs(dy), dx), vy), (px, py)]
        items += rl.add_track(board, net, "B", pts, 0.30)
        nvia += 1
        log.append("stub via %s (%.3f, %.3f): L4 link to its partner via (%.3f, %.3f)" % (net, vx, vy, px, py))
    # 3. neck-down at 0402 / 0603 pads
    necked = []
    for t in tracks:
        if t in dead or t.GetLayer() != pcbnew.F_Cu:
            continue
        n = t.GetNetname()
        a, b = P(t.GetStart()), P(t.GetEnd())
        w = pcbnew.ToMM(t.GetWidth())
        if n == "VDD_0V9_BUCK" and any(abs(q[0] - 71.075) < 0.01 and 30.9 < q[1] < 32.5 for q in (a, b)):
            t.SetWidth(pcbnew.FromMM(0.40))          # the divider / feed-forward branch (R17.1, C29.1)
            necked.append("%s branch (%.2f,%.2f)-(%.2f,%.2f) 0.80 -> 0.40" % (n, a[0], a[1], b[0], b[1]))
            continue
    # round 2 (D-118 e, verifier minor): a wide track whose copper overlaps a 0402 / 0603 pad from outside (its round
    # end reaching into the pad) is necked too. Every F.Cu track of the pad's net wider than the pad's narrow side
    # + 0.02 mm whose copper comes within its half width of the pad polygon is cut where its centre line is
    # w / 2 + 0.10 mm clear of the pad: the piece on the pad side becomes the neck (0.40 mm, or the pad width when
    # narrower), the rest keeps its width, so the wide copper ends >= 0.10 mm outside the pad (>= w / 2 + 0.10 mm of
    # neck). A piece that is close to the pad over its whole length is necked whole and the next piece is examined.
    smalls = []
    for fp in board.GetFootprints():
        name = fp.GetFPIDAsString()
        if any(k in name for k in ("_0402_", "_0603_")) and len(fp.Pads()) == 2:
            for p in fp.Pads():
                sz = p.GetSize()
                smalls.append((bl.pad_polygon(p), p, fp, pcbnew.ToMM(min(sz.x, sz.y))))
    for _round in range(6):
        changed = 0
        live = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.F_Cu]
        for poly, p, fp, narrow in smalls:
            n = p.GetNetname()
            for t in live:
                if t in dead or t.GetNetname() != n:
                    continue
                w = pcbnew.ToMM(t.GetWidth())
                if w <= narrow + 0.02 + 1e-4:
                    continue
                a, b = P(t.GetStart()), P(t.GetEnd())
                da, db = poly_dist(a, poly), poly_dist(b, poly)
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                dseg = min(poly_dist((a[0] + (b[0] - a[0]) * k / 40.0, a[1] + (b[1] - a[1]) * k / 40.0), poly)
                           for k in range(41)) if L > 0 else da
                if dseg >= w / 2 - 1e-4:
                    continue
                nw = min(0.40, narrow) if w > 0.6 else narrow
                pin, far = (a, b) if da <= db else (b, a)
                need = w / 2 + 0.10
                m = None
                steps = max(1, int(L / 0.005))
                for k in range(steps + 1):
                    q = (pin[0] + (far[0] - pin[0]) * k / steps, pin[1] + (far[1] - pin[1]) * k / steps)
                    if poly_dist(q, poly) >= need and all(
                            poly_dist((pin[0] + (far[0] - pin[0]) * j / steps, pin[1] + (far[1] - pin[1]) * j / steps),
                                      poly) >= need for j in range(k, steps + 1, max(1, steps // 20))):
                        m = q
                        break
                if m is None or math.hypot(far[0] - m[0], far[1] - m[1]) < 0.02:
                    t.SetWidth(pcbnew.FromMM(nw))
                    necked.append("%s.%s %s whole piece (%.2f,%.2f)-(%.2f,%.2f) %.2f -> %.2f" % (
                        fp.GetReference(), p.GetNumber(), n, a[0], a[1], b[0], b[1], w, nw))
                else:
                    if pin is a:
                        t.SetStart(bl.to_page(*m))
                    else:
                        t.SetEnd(bl.to_page(*m))
                    items += rl.add_track(board, n, "F", [pin, m], nw)
                    necked.append("%s.%s %s neck %.3f mm (%.2f,%.2f)-(%.2f,%.2f) %.2f -> %.2f, wide copper ends %.3f "
                                  "mm outside the pad" % (fp.GetReference(), p.GetNumber(), n, math.hypot(
                                      m[0] - pin[0], m[1] - pin[1]), pin[0], pin[1], m[0], m[1], w, nw,
                                      poly_dist(m, poly) - w / 2))
                changed += 1
        if not changed:
            break
    # 4. PB_INT_N 46.3 deg piece
    snapped = []
    for t in tracks:
        if t in dead or t.GetNetname() not in ("PB_INT_N", "NPOR"):
            continue
        a, b = P(t.GetStart()), P(t.GetEnd())
        for s, e in ((a, b), (b, a)):
            if any(abs(s[0] - p0[0]) < 0.01 and abs(s[1] - p0[1]) < 0.01 and abs(e[0] - p1[0]) < 0.01 and
                   abs(e[1] - p1[1]) < 0.01 for p0, p1 in SNAP):
                dx, dy = e[0] - s[0], e[1] - s[1]
                k = (s[0], s[1] + (dy - dx))                      # vertical piece, then 45 deg to e
                if s is a:
                    t.SetStart(bl.to_page(*k))
                else:
                    t.SetEnd(bl.to_page(*k))
                items += rl.add_track(board, t.GetNetname(), "F" if t.GetLayer() == pcbnew.F_Cu else "B", [s, k],
                                      pcbnew.ToMM(t.GetWidth()))
                snapped.append(t.GetNetname() + " (%.3f,%.3f)-(%.3f,%.3f) -> vertical %.3f mm + 45 deg" % (
                    s[0], s[1], e[0], e[1], dy - dx))
    for o in dead:
        board.Remove(o)
    rl.group(board, "L5F_TIDY", items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"trimmed": trimmed, "removed": len(dead), "stub_vias_linked": nvia, "necked": necked, "snapped": snapped,
               "log": log}, open(OUT, "w"), indent=1)
    print("l5f_tidy: %d stub ends trimmed, %d items removed, %d stub vias linked on L4, %d necked, %s" % (
        trimmed, len(dead), nvia, len(necked), snapped))
    for n in necked:
        print("  neck " + n)


if __name__ == "__main__":
    main()
