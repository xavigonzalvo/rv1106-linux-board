#!/usr/bin/env python3
"""Layout phase L5, step 1 (design/.venv): the open U9 gate lanes (header GPIO, UART2, LEDs, power control, NPOR).

    design/.venv/bin/python -I design/pcb/scripts/l5_lanes.py [geo.json] [out.json]
      default in : design/pcb/l5/board_geo.json   (l4_export.py on the board after place_l5_tweaks.py)
      default out: design/pcb/l5/lanes.json       (l5_write.py writes it, group L5_LANES)

1. Stubs: each open lane ends at its gate point 8.0 mm from the U9 centre and must cross the ring-1 row with the DRU
   neck-down (0.10/0.10 for a track that touches U9_FAN, D-110). Freerouting only knows the class clearance, so it
   cannot leave the SoC there. For every open lane one straight radial 0.10 mm segment is drawn from inside the fan
   outward: the shortest of 1.2 ... 3.0 mm that passes the exact check of l4lib.Store (class clearances, every
   .kicad_dru rule, the neck-down only where KiCad applies it) and whose end is clear at the class rules. Stubs of
   neighbouring lanes are 0.30 mm apart. NPOR is joined to C71.1 (one neck-down segment) and R43.2 (router).
2. Negotiated routing (PathFinder style) of the lane nets from their stub ends to their pads: every net is planned
   on its own grid with the board copper as hard obstacles and the other lane nets' plans as a soft cost that grows
   per iteration (history + present congestion); then the nets are committed one by one with the exact router
   (l4_route.route_net, 0.10 mm, vias allowed, L4 under U9 kept free for the inner-via nets) whose cost follows the
   plans. A route with two vias of the net closer than the hole rule is undone and retried with dearer vias.
3. Polish (end points inside the own pad dropped) and widening to the DEFAULT 0.15 mm segment by segment where the
   exact check passes (D-113 b). New vias keep 0.76 mm from the ETH lines (l4lib.VIA_ETH).
Deterministic (fixed orders, fixed grid). Lanes that do not route stay as stubs (open; check_routing.py FAILs them).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
GEO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PCB, "l5", "board_geo.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PCB, "l5", "lanes.json")
sys.argv = [sys.argv[0], GEO, os.path.join(PCB, "l5", "_unused_l4_routes.json")]
sys.path.insert(0, HERE)
import l4_route as R  # noqa: E402  (module level: loads GEO into the obstacle store R.S)
import l4lib as L  # noqa: E402
import l5lib  # noqa: E402

L.VIA_ETH = True
L.VIA_USB_STRICT = True   # D-115        # D-113: new vias keep 0.76 mm from the ETH lines
geo = R.geo
S = R.S

LANES = ["HDR_I2C1_SDA", "HDR_I2C1_SCL", "HDR_GPIO2_A7", "HDR_GPIO2_A6", "HDR_GPIO2_A0", "HDR_GPIO2_A1",
         "HDR_GPIO2_A2", "HDR_GPIO2_A3", "HDR_GPIO2_A4", "HDR_GPIO2_A5",
         "HDR_SPI0_CS0", "HDR_SPI0_SCLK", "HDR_SPI0_MOSI", "HDR_SPI0_MISO", "HDR_PWM8", "HDR_PWM9",
         "HDR_UART3_TX", "HDR_UART3_RX", "HDR_I2C3_SDA", "HDR_I2C3_SCL", "HDR_PWM11", "HDR_PWM10",
         "UART2_RX", "UART2_TX", "HDR_GPIO1_B1", "HDR_GPIO1_B0", "HDR_GPIO1_A4", "HDR_GPIO1_A3",
         "LED_ETH", "HDR_GPIO1_A1", "HDR_GPIO1_A0",
         "USBA_VBUS_EN", "PWR_KILL", "LED_STATUS"]
STUB_W = 0.10
LANE_W = 0.10         # widened to 0.15 by l5_cleanup.py where it fits (D-113)
LENGTHS = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]


# ----------------------------------------------------------------------------------------------------------------
# negotiated routing of the lane nets (PathFinder-style): plan every net with the board copper as hard obstacles and
# the other lane nets' plans as a soft, growing cost; then commit the nets one by one with the exact router
# (l4_route.route_net) whose cost follows the plans, so a net keeps to its planned corridor and leaves the others'.
# ----------------------------------------------------------------------------------------------------------------
import math  # noqa: E402

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

NX = int(round(80.0 / L.RES))
ITER = int(os.environ.get("L5_NEG_ITER", "8"))
OCC_R = 0.25          # lane track half width 0.05 + DEFAULT clearance 0.15 + other half width 0.05
VIA_R = 0.45          # via radius 0.25 + 0.15 + 0.05
LANE_VIA_COST = 5.0   # mm equivalent: L1 first, a via where a crossing needs it


def touched_pads(net):
    pts = [(tuple(t["a"]), t["layer"]) for t in geo["tracks"] if t["net"] == net]
    pts += [(tuple(t["b"]), t["layer"]) for t in geo["tracks"] if t["net"] == net]
    pts += [((v["x"], v["y"]), lay) for v in geo["vias"] if v["net"] == net for lay in ("F", "B")]
    for layer, ppts, w in R.ROUTES.get(net, {}).get("tracks", []):
        pts += [(tuple(q), layer) for q in ppts]
    got = set()
    for q in S.pads:
        if q["net"] != net:
            continue
        for p, lay in pts:
            if q["lay"] & (L.F if lay == "F" else L.B) and L.inside_poly(p[0], p[1], q["poly"]):
                got.add((q["ref"], q["num"]))
                break
    return got


def terms_of(net, stubs):
    x, y, _ = stubs[net]
    terms = [R.pt(x, y, L.F)]
    done = touched_pads(net)
    for q in S.pads:
        if q["net"] == net and q["ref"] != "U9" and (q["ref"], q["num"]) not in done:
            terms.append(R.P(q["ref"], q["num"]))
    return terms


class Plan:
    """one net: its grid (hard obstacles = the board copper, built once), terminals, current plan"""

    def __init__(self, net, terms):
        self.net, self.terms = net, terms
        xs = [t["x"] for t in terms]
        ys = [t["y"] for t in terms]
        m = 4.0
        win = [max(0.0, min(xs) - m), max(0.0, min(ys) - m), min(80.0, max(xs) + m), min(80.0, max(ys) + m)]
        win = [math.floor(win[0] / L.RES) * L.RES, math.floor(win[1] / L.RES) * L.RES, win[2], win[3]]
        forbid = [(L.B, tuple(S.court[r])) for r in ("Y1", "Y2")] + [(L.B, L.FAN)]   # L4 under U9: inner vias
        ffree = [(t["x"] - 1.3, t["y"] - 1.3, t["x"] + 1.3, t["y"] + 1.3) for t in terms if t["kind"] == "pad"]
        G = L.Grid(S, net, LANE_W / 2, win, L.F | L.B, via_ok=True, novia=R.GRID_NOVIA, relax=[], forbid=forbid,
                   forbid_free=ffree)
        for r in R.SW_AREAS:
            hw = LANE_W / 2
            G.block[L.B] |= (G.X >= r[0] - hw - L.GM) & (G.X <= r[2] + hw + L.GM) & (G.Y >= r[1] - hw - L.GM) & \
                (G.Y <= r[3] + hw + L.GM)
        self.i0 = int(round(G.y0 / L.RES))
        self.j0 = int(round(G.x0 / L.RES))
        del G.X, G.Y
        self.G = G
        self.cells = {lay: R.term_cells(G, t, L.F | L.B) for lay, t in enumerate(terms)}
        self.path = []          # list of (L, i, j) window cells (all branches)
        self.occ = None         # {layer: global flat indices of the dilated plan}
        self.line = {}          # {layer: global flat indices of the plan's centre cells}

    def sl(self):
        return slice(self.i0, self.i0 + self.G.H), slice(self.j0, self.j0 + self.G.W)


def occupancy(P):
    """global cells the plan of P occupies (dilated by the clearance radius), per layer"""
    out = {}
    if not P.path:
        return out
    for lay in (L.F, L.B):
        m = np.zeros((P.G.H, P.G.W), bool)
        for (Lc, i, j) in P.path:
            if Lc == lay:
                m[i, j] = True
        vm = np.zeros((P.G.H, P.G.W), bool)
        for k in range(1, len(P.path)):
            a, b = P.path[k - 1], P.path[k]
            if a[0] != b[0] and a[1:] == b[1:]:
                vm[a[1], a[2]] = True
        r = int(math.ceil(OCC_R / L.RES))
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        m = ndimage.binary_dilation(m, structure=(xx * xx + yy * yy <= r * r))
        rv = int(math.ceil(VIA_R / L.RES))
        yy, xx = np.mgrid[-rv:rv + 1, -rv:rv + 1]
        if vm.any():
            m |= ndimage.binary_dilation(vm, structure=(xx * xx + yy * yy <= rv * rv))
        ii, jj = np.nonzero(m)
        out[lay] = (ii + P.i0) * NX + (jj + P.j0)
        c = np.zeros((P.G.H, P.G.W), bool)
        for (Lc, i, j) in P.path:
            if Lc == lay:
                c[i, j] = True
        c |= vm
        ii, jj = np.nonzero(c)
        P.line[lay] = (ii + P.i0) * NX + (jj + P.j0)
    return out


def plan_route(P, occ, hist, pres):
    """route P on its grid with cost (1 + hist) * (1 + pres * occupancy of the others); tree growth like route_net"""
    G = P.G
    si, sj = P.sl()
    for lay in (L.F, L.B):
        o = occ[lay][si, sj]
        h = hist[lay][si, sj]
        G.cost[lay] = (1.0 + h) * (1.0 + pres * o)
    tree = list(P.cells[0])
    rest = list(range(1, len(P.terms)))
    path = []
    while rest:
        best = None
        for k in rest:
            p = G.search(tree, P.cells[k], via_cost=LANE_VIA_COST)
            if p is not None and (best is None or len(p) < len(best[1])):
                best = (k, p)
        if best is None:
            return None
        k, p = best
        rest.remove(k)
        path += p
        tree += p + P.cells[k]
    return path


def negotiated(stubs, skip=()):
    nets = [n for n in LANES if n in stubs and n not in skip]
    plans = []
    for n in nets:
        terms = terms_of(n, stubs)
        if len(terms) < 2:
            continue
        plans.append(Plan(n, terms))
    R.log("== negotiated routing of %d lane nets (%d iterations max)" % (len(plans), ITER))
    occ = {lay: np.zeros((NX, NX), np.float32) for lay in (L.F, L.B)}
    hist = {lay: np.zeros((NX, NX), np.float32) for lay in (L.F, L.B)}
    pres = 0.5
    for it in range(ITER):
        for P in plans:
            if P.occ:
                for lay, idx in P.occ.items():
                    occ[lay].flat[idx] -= 1
            p = plan_route(P, occ, hist, pres)
            P.path = p or []
            if p is None:
                R.log("  plan %s: no path" % P.net)
            P.occ = occupancy(P)
            for lay, idx in P.occ.items():
                occ[lay].flat[idx] += 1
        # a conflict: a centre cell of one plan inside the clearance zone of another plan
        over = 0
        bad = []
        for P in plans:
            for lay, idx in P.line.items():
                own = np.zeros(len(idx), np.float32)
                own += 1.0          # the plan's own dilation covers its centre cells
                c = occ[lay].flat[idx] - own > 0
                if c.any():
                    over += int(c.sum())
                    bad.append(P.net)
                    hist[lay].flat[idx[c]] += 0.5
        R.log("  iteration %d: %d conflicting centre cells, nets in conflict: %d %s" % (
            it + 1, over, len(set(bad)), " ".join(sorted(set(bad)))))
        if not over:
            break
        pres *= 1.8
    # commit: one by one with the exact router, cost = (1 + hist) * (1 + 20 * plans of the nets not committed yet)
    order = sorted(plans, key=lambda P: len(P.path))
    pending = {lay: occ[lay].copy() for lay in occ}
    for P in order:
        for lay, idx in P.occ.items():
            pending[lay].flat[idx] -= 1

        def cost_fn(lay, X, Y, P=P):
            jj = np.clip(np.rint(X / L.RES - 0.5).astype(int), 0, NX - 1)
            ii = np.clip(np.rint(Y / L.RES - 0.5).astype(int), 0, NX - 1)
            return (1.0 + hist[lay][ii, jj]) * (1.0 + 20.0 * np.maximum(pending[lay][ii, jj], 0))
        ok = l5lib.route_checked(R, S, P.net, P.terms, LANE_VIA_COST, layers=L.F | L.B, via_ok=True, margin=4.0,
                                 w=LANE_W, cost_fn=cost_fn, forbid=[(L.B, L.FAN)])
        R.log("  commit %s: %s" % (P.net, "ok" if ok else "FAIL"))


def main():
    R.setup_novia()
    R.setup_sw_areas()
    # round 2: no new via within 0.55 mm of the VDD_0V9 free strips (planes.NECK_FREE; check_routing 'neck')
    R.GRID_NOVIA.extend([(42.95 - 0.56, 28.05 - 0.56, 63.5 + 0.56, 30.75 + 0.56), (60.5 - 0.56, 28.05 - 0.56, 63.5 + 0.56, 35.5 + 0.56)])
    # round 3 (D-115, verifier round 2 blocker gpio): the 21 north lanes first, as a planned bus (l5_north.py)
    import l5_north as NB
    stubs, north_state = NB.run(R, L, S, R.log)
    for net in LANES:
        if net in NB.NORTH:
            continue
        if net not in geo["ends"]:
            R.log("  skip %s: no open lane end" % net)
            continue
        t = R.lane_end(net)
        ox, oy = t["out"]
        b = t["back"]
        for ln in LENGTHS:
            e = (round(t["x"] + ox * ln, 4), round(t["y"] + oy * ln, 4))
            # the shortest stub whose end is clear at the class rules (a short piece beyond the end, which does not
            # touch U9_FAN, passes the exact check): from there the router may turn the lane at the class clearance
            f = (e[0] + ox * 0.05, e[1] + oy * 0.05)
            if S.check_seg(net, L.F, b, e, STUB_W / 2) and S.check_seg(net, L.F, e, f, STUB_W / 2):
                R.add_route(net, "F", [b, e], STUB_W)
                stubs[net] = [e[0], e[1], ln]
                R.log("  stub %-14s (%.2f, %.2f) -> (%.2f, %.2f) %.1f mm" % (net, t["x"], t["y"], e[0], e[1], ln))
                break
        else:
            R.log("  FAIL stub %s: no legal radial exit" % net)
            R.FAILS.append((net, ["stub"]))
    # NPOR: lane -> C71.1 (its ring-1 cap, 1 mm away) and R43.2 (pull-up), SENSE 0.15 mm
    # (one straight neck-down segment from inside the fan to the C71.1 pad centre, then the router C71.1 -> R43.2)
    t = R.lane_end("NPOR")
    c71 = R.PADS[("C71", "1")]
    R.fixed("NPOR", "F", [t["back"], (c71["x"], c71["y"])], w=STUB_W)
    R.route_net("NPOR", [R.P("C71", "1"), R.P("R43", "2")], margin=1.5)
    # round 2 (D-114 a, verifier blockers soc/onoff): the SoC supply and boot / power-control nets first (functional
    # parts), then the negotiated lanes, then those nets' test pads
    import l5_priority as PR
    PR.run(passes=(False,))
    # the priority lane nets (PWR_KILL, USBA_VBUS_EN) are done by PR, the north lanes by l5_north (its unfinished J5
    # legs are left to Freerouting, which starts from the bus copper)
    negotiated(stubs, skip=set(PR.PRIORITY) | set(NB.NORTH))
    NB.run_legs(R, L, S, north_state, R.log)     # the north J5 legs after the west lanes (they keep out of their exits)
    # round 3: a west lane the negotiation left open gets one more exact-router try in a wide window (the strip west of
    # J5 and the free L4 west of the bus included)
    for n in [n for n in LANES if n in stubs and n not in NB.NORTH and n not in PR.PRIORITY]:
        pads = [p for p in terms_of(n, stubs)[1:]]
        if pads:
            ok = l5lib.route_checked(R, S, n, terms_of(n, stubs), LANE_VIA_COST, layers=L.F | L.B, via_ok=True,
                                     margin=12.0, w=LANE_W, forbid=[(L.B, L.FAN)])
            R.log("  second try %s: %s" % (n, "ok" if ok else "FAIL"))
            if ok:
                R.FAILS[:] = [f for f in R.FAILS if f[0] != n]
    PR.run(passes=(True,))
    PR.report()
    npol = l5lib.polish(R.ROUTES, S)
    keep = set()
    for net, r in R.ROUTES.items():
        for lay, pts, w in r["tracks"]:
            if len(pts) == 2 and w == STUB_W and net in stubs and abs(pts[1][0] - stubs[net][0]) < 1e-6 and \
                    abs(pts[1][1] - stubs[net][1]) < 1e-6:
                keep.add((net, tuple(pts[0]), tuple(pts[1])))
    # the store holds the routes as committed: rebuild the lane items from the polished routes before widening
    S.items[:] = [it for it in S.items if it[8] != -2]
    S._arr = None
    for net, r in R.ROUTES.items():
        for lay, pts, w in r["tracks"]:
            for a, b in zip(pts, pts[1:]):
                S.add_track(net, L.F if lay == "F" else L.B, tuple(a), tuple(b), w / 2)
    nw = l5lib.widen(R.ROUTES, sorted(R.ROUTES), (0.15,), S, keep)
    R.log("== polish: %d end points dropped inside pads; widening to 0.15 mm: %d of %d segments" % ((npol,) + nw))
    R.selfcheck()
    # the non-lane priority nets go to their own file / board group (L5_PRIORITY); lane nets stay in lanes.json
    prio = {n: R.ROUTES.pop(n) for n in sorted(list(R.ROUTES)) if n in PR.PRIORITY and n not in stubs}
    json.dump({"routes": prio, "fails": [f for f in R.FAILS if f[0] in prio or f[0] in PR.PRIORITY]},
              open(os.path.join(os.path.dirname(OUT), "priority.json"), "w"), indent=0, sort_keys=True)
    json.dump({"routes": R.ROUTES, "log": R.LOG, "fails": R.FAILS, "stubs": stubs, "novia": R.GRID_NOVIA,
               "sw_areas": R.SW_AREAS}, open(OUT, "w"), indent=0)
    R.log("L5 lanes: %d stubs, fails %s" % (len(stubs), R.FAILS))


if __name__ == "__main__":
    main()
