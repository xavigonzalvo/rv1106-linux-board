"""Shared helpers of the L5 scripts (design/.venv): route polishing and widening against the l4lib obstacle store.

polish(routes, S): a route that ends at a pad's anchor point after an approach from inside the same pad (the router
    pulls the last cell to the pad centre) can form an acute corner inside the pad; such a last (or first) point is
    dropped, so the track ends inside the pad on its approach line. Pads are the store's pad polygons of the same net.
widen(routes, nets, widths, S): try each segment of the given nets at wider widths (exact check against everything;
    the store item is taken out while it is checked and updated when it grows).
"""
import json
import math

import l4lib as L

LAYERS = {"F": L.F, "B": L.B}


def _in_own_pad(S, net, lay, p):
    for q in S.pads:
        if q["net"] == net and q["lay"] & LAYERS[lay] and L.inside_poly(p[0], p[1], q["poly"]):
            return q
    return None


def polish(routes, S):
    """drop an end point when the point before it is already inside the same pad of the net (the router's pull to the
    pad centre then only adds a jog, often an acute one, inside the pad)"""
    n = 0
    for net, r in routes.items():
        out = []
        for lay, pts, w in r["tracks"]:
            pts = [tuple(p) for p in pts]
            changed = True
            while changed and len(pts) >= 3:
                changed = False
                for end in (-1, 0):
                    b, c = (pts[-2], pts[-1]) if end == -1 else (pts[1], pts[0])
                    pad = _in_own_pad(S, net, lay, c)
                    if pad is not None and _in_own_pad(S, net, lay, b) is pad:
                        pts = pts[:-1] if end == -1 else pts[1:]
                        n += 1
                        changed = True
                        break
            out.append([lay, [list(p) for p in pts], w])
        r["tracks"] = out
    return n


def find_item(S, net, lay, a, b):
    for k in range(len(S.items) - 1, -1, -1):
        it = S.items[k]
        if it[0] == 0 and it[2] == net and it[1] == LAYERS[lay] and \
                abs(it[3] - a[0]) < 1e-6 and abs(it[4] - a[1]) < 1e-6 and abs(it[5] - b[0]) < 1e-6 and \
                abs(it[6] - b[1]) < 1e-6:
            return k
    return None


def widen(routes, nets, widths, S, keep=()):
    """keep: segments (net, a, b) that must not change (e.g. the lane stubs in the fan)"""
    n_ok = n_all = 0
    for net in nets:
        r = routes.get(net)
        if not r:
            continue
        new = []
        for lay, pts, w in r["tracks"]:
            # split polylines into single segments so that each can take its own width
            for a, b in zip(pts, pts[1:]):
                n_all += 1
                a, b = tuple(a), tuple(b)
                best = w
                k = find_item(S, net, lay, a, b)
                if (net, a, b) not in keep and k is not None and not L.seg_intersects_rect(a, b, L.FAN):
                    for w2 in widths:
                        if w2 <= w + 1e-9:
                            break
                        S.items[k] = S.items[k][:1] + (0,) + S.items[k][2:]
                        S._arr = None
                        ok = S.check_seg(net, LAYERS[lay], a, b, w2 / 2)
                        S.items[k] = S.items[k][:1] + (LAYERS[lay],) + S.items[k][2:]
                        S._arr = None
                        if ok:
                            best = w2
                            break
                    if best > w:
                        it = S.items[k]
                        S.items[k] = it[:7] + (best / 2,) + it[8:]
                        S._arr = None
                        n_ok += 1
                new.append([lay, [list(a), list(b)], best])
        r["tracks"] = new
    return n_ok, n_all


def _close_vias(R, net, n_holes0, S):
    """True if a via added since n_holes0 is closer than the hole-to-hole rule to another via of the same net"""
    new = [(h[0], h[1]) for h in S.holes[n_holes0:] if h[3] == net]
    allv = [(h[0], h[1]) for h in S.holes if h[3] == net and h[2] <= L.VIA_DR / 2 + 1e-6]
    for a in new:
        for b in allv:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if 1e-6 < d < L.VIA_DR + L.HOLE_HOLE + L.EPS:
                return True
    return False


def route_checked(R, S, net, terms, via_cost, **kw):
    """R.route_net, then undo and retry with dearer vias (x4, x16) when the route put two vias of the net closer than
    the hole-to-hole rule (the grid search places both vias of a short hop in one search, unchecked against each
    other). Returns True on a clean success."""
    for k, vc in enumerate((via_cost, via_cost * 4, via_cost * 16)):
        n_items, n_holes = len(S.items), len(S.holes)
        before = json.loads(json.dumps(R.ROUTES.get(net))) if net in R.ROUTES else None
        n_fail = len(R.FAILS)
        ok = R.route_net(net, terms, via_cost=vc, **kw)
        if ok and not _close_vias(R, net, n_holes, S):
            return True
        # undo
        del S.items[n_items:]
        del S.holes[n_holes:]
        S._arr = None
        if before is None:
            R.ROUTES.pop(net, None)
        else:
            R.ROUTES[net] = before
        if ok:
            R.log("  %s: two vias closer than the hole rule, retry with via cost %.1f" % (net, vc * 4))
            del R.FAILS[n_fail:]
        else:
            return False
    R.FAILS.append((net, ["close vias"]))
    return False
