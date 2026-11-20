#!/usr/bin/env python3
"""Layout phase L5 round 3 (design/.venv): the north exit of U9 as a planned bus (verifier round 2, blocker gpio;
D-115). Used as a module by l5_lanes.py, right after the lane stubs of the other sides and before every other L5
route, so the bus has the north field to itself.

Why a plan: the 21 lanes that leave U9's north side (pins 72-96) go to the header J5 on the west edge, the UART2 test
pads / resistors near J6 in the north and the LED_ETH resistor in the north-east. A free router (rounds 1/2 and the
negotiated router of l5_lanes.py in round-3 trials: 9-12 of 21) blocks the narrow corridors between the ring-2 parts
with its first nets. With the round-3 local moves (place_l3_tweaks.py, D-115: R66/R67 next to J6, TP31 north-east of
TP6, C69 north-east of the field, FB3 0.35 mm west; L4: no VCC_1V8 via in the corridor) the north side has two L1 corridors - W between
FB3.2 and C43 (6 lanes), E between C43 GND via and TP6 (15 lanes) - and an empty field north of them (x 26.4-35.8,
y 17-23) where the lanes drop to L4, which is free west of the field.

Every lane is a fixed polyline of vertical and 45 deg pieces, exact-checked by l4lib (the same rules as every other L5
route; a piece that fails is reported and the lane is left to the other L5 steps):
  1. stubs: from the lane's escape end inside U9_FAN one straight neck-down piece to y 27.30 (as l5_lanes.py); the
     nine lanes of pins 72-80 (G3) end at 0.25 mm pitch instead of 0.30 mm (a slanted neck-down piece: the east-most
     lane must clear C74's GND via at (36.24, 26.26) before it reaches it);
  2. bends to the corridors: a group of lanes turns 45 deg one after the other ("staggered": the next lane turns
     where its diagonal stays 0.364 mm from the previous one = 0.10 mm lanes at 0.15 mm + margin);
     HDR_UART3_TX passes between C43's VDD_0V9 via and C67's GND via on the 45 deg line x + y = 56.954;
  3. bends from the corridors to the field columns x = X0 + P * i (P = 0.46 mm: a 0.10 mm lane passes a 0.50 mm via
     of the next column at 0.15 mm), lanes in U9 pin order (no crossing on L1);
  4. vias: even columns in row A (y 20.30), odd columns in row B (y 19.70) (neighbouring vias 0.757 mm apart, >= the
     0.75 mm hole rule); UART2_RX/TX (to TP9/TP10, R66/R67, J6) and LED_ETH (to R70/TP11) run on north on L1;
  5. L4 from each via: row-A lanes south, row-B lanes north, nested (east lane outermost), then west in their own
     0.26 mm track row to the bus end x = X_BUS;
  6. from the bus end to the J5 pin (and the I2C3 pull-ups R62/R63) and from the column tops of the L1 lanes to their
     pads: the exact router (l4_route.route_net), L4 preferred for the bus, vias outside the no-via areas.
Corridor W holds the six lanes of pins 90-95 because FB3 moves 0.35 mm west (D-115); HDR_UART3_TX (pin 89) takes
the 45 deg passage between C43's VDD_0V9 via and C67's GND via into corridor E.
Deterministic (fixed orders and coordinates).
"""
import math

LANE_W = 0.10
HW = LANE_W / 2
D = 0.364                    # perpendicular spacing of two 45 deg lanes (0.10 + 0.15 + margin) * sqrt(2)... see bend()
P = 0.46                     # column pitch
X0 = 26.30                   # first column
Y_A, Y_B = 20.30, 19.70      # via rows
ROW_PITCH = 0.288               # 0.10 mm L4 rows 0.188 mm apart: the router grid finds free cells between two rows,
                                # and the 11 south rows stay north of C43's GND via (30.77, 24.11)
X_BUS = 25.40
Y_STUB = 27.30
W_LANES = ["HDR_SPI0_CS0", "HDR_SPI0_SCLK", "HDR_SPI0_MOSI", "HDR_SPI0_MISO", "HDR_PWM8", "HDR_PWM9"]
G2 = ["HDR_UART3_RX", "HDR_I2C3_SDA", "HDR_I2C3_SCL", "HDR_PWM11", "HDR_PWM10"]
G3 = ["UART2_RX", "UART2_TX", "HDR_GPIO1_B1", "HDR_GPIO1_B0", "HDR_GPIO1_A4", "HDR_GPIO1_A3", "LED_ETH",
      "HDR_GPIO1_A1", "HDR_GPIO1_A0"]
U3TX = "HDR_UART3_TX"
E_LANES = [U3TX] + G2 + G3
CS0 = "HDR_SPI0_CS0"
NORTH = W_LANES + E_LANES
NORTH_BAND = ("HDR_SPI0_MOSI", "HDR_SPI0_MISO", U3TX, "HDR_UART3_RX", "HDR_PWM10")
# lanes that do not drop in the field: UART2_RX/TX (TP9/TP10, R66/R67, J6) and LED_ETH (R70/TP11) go north / north-east;
# the I2C3 pair goes to J5.3 / J5.5 north of the L4 VCC5V0_SYS rail (round-3 trial: as L4 bus rows they were boxed in
# between the RJ45 pin rows), so they run north on L1 over the rail first
NO_VIA = ("UART2_RX", "UART2_TX", "LED_ETH", "HDR_I2C3_SDA", "HDR_I2C3_SCL")
W_CORR = 28.14               # corridor W, first lane (FB3.2 right edge 27.884 after the D-115 move + 0.25)
E_CORR = 31.230              # corridor E, first lane (C43 GND via (30.766, 24.11) + 0.25 + 0.20 + margin)
CORR_P = 0.2525              # 0.10 mm lanes at 0.1525 mm (the exact check keeps 0.001 mm over 0.15)
G3_P = 0.2524                # G3 stub pitch: the east lane 0.4518 mm from C74's GND via (36.236, 26.26)
G3_X0 = 33.765               # G3 stub ends at 0.25 mm pitch from UART2_RX
FIELD_TOP = 19.00            # the L1 lanes that run on leave the field here


def bend(lanes, x0, x1, y0, west=True, d=D):
    """45 deg staggered bend of a group of vertical lanes going north (y decreasing).
    lanes: names in the order the bend proceeds (west->east for a west bend, east->west for an east bend); x0/x1: start
    and end x per lane; y0: y where the first lane turns. Returns {name: (y_turn, y_end)} with the next lane turning
    where its diagonal stays d (perpendicular * sqrt(2)) from the previous one."""
    out = {}
    y = y0
    for k, n in enumerate(lanes):
        if k:
            p = lanes[k - 1]
            dx = (x0[n] - x0[p]) if west else (x0[p] - x0[n])
            y = min(y, out[p][0] + dx - d)
        out[n] = (round(y, 4), round(y - abs(x0[n] - x1[n]), 4))
    return out


def run(R, L, S, log):
    """routes the north bus; returns (stubs {net: [x, y, len]}, done [nets fully routed])"""
    stubs, pts = {}, {}
    # ---------------------------------------------------------------- 1. stubs
    for n in NORTH:
        if n not in R.geo["ends"]:
            log("  north: %s has no open lane end" % n)
            continue
        t = R.lane_end(n)
        b = t["back"]
        x = t["x"]
        if n in G3:
            x = round(G3_X0 + G3_P * G3.index(n), 4)
        e = (x, Y_STUB)
        if not R.fixed(n, "F", [b, e], w=LANE_W):
            continue
        stubs[n] = [e[0], e[1], round(math.hypot(e[0] - b[0], e[1] - b[1]), 3)]
        pts[n] = [e]
    log("  north stubs: %d of %d" % (len(stubs), len(NORTH)))
    # ---------------------------------------------------------------- 2./3. planned L1 polylines
    xcol = {n: round(X0 + P * i, 4) for i, n in enumerate(W_LANES + E_LANES)}
    x0 = {n: stubs[n][0] for n in stubs}
    # W: stubs -> corridor W (west bend from y 27.20), corridor -> columns (west bend from y 24.77, north of FB3.2)
    xw = {n: round(W_CORR + CORR_P * k, 4) for k, n in enumerate(W_LANES)}
    bw1 = bend(W_LANES, x0, xw, 26.85)          # CS0 clears C56's GND via (27.84, 26.73) by 0.45 mm
    bw2 = bend(W_LANES, xw, xcol, 24.70)          # CS0 clears FB3.2 and TP25
    for n in W_LANES:
        if n in stubs:
            pts[n] += [(x0[n], bw1[n][0]), (xw[n], bw1[n][1]), (xw[n], bw2[n][0]), (xcol[n], bw2[n][1])]
    # E: UART3_TX by the 45 deg line between the VDD_0V9 via and C67's GND via; G2 + G3 by one staggered west bend
    xe = {n: round(E_CORR + CORR_P * j, 4) for j, n in enumerate(E_LANES)}
    if U3TX in stubs:
        c = 56.99            # 0.50 mm from the VDD_0V9 via (class clearance 0.20), 0.45 from C67's GND via
        xs = x0[U3TX]
        pts[U3TX] += [(xs, round(c - xs, 4)), (xe[U3TX], round(c - xe[U3TX], 4))]
    grp = G2 + G3
    be1 = bend(grp, x0, xe, 26.60)
    # UART2_RX (first G3 lane) may turn only north of C62's GND via (33.23, 26.70): y <= 26.33
    if be1["UART2_RX"][0] > 26.33:
        y = 26.33
        be1 = dict(be1)
        for k, n in enumerate(G3):
            if k:
                y = min(y, be1[G3[k - 1]][0] + (x0[n] - x0[G3[k - 1]]) - D)
            be1[n] = (round(y, 4), round(y - abs(x0[n] - xe[n]), 4))
    for n in grp:
        if n in stubs:
            pts[n] += [(x0[n], be1[n][0]), (xe[n], be1[n][1])]
    # corridor E -> columns: the lanes whose column lies west bend west (first lane at y 23.60, north of C43's GND
    # via), the others bend east (the east-most at y 22.60, north of TP6)
    westers = [n for n in E_LANES if xcol[n] <= xe[n]]
    easters = [n for n in reversed(E_LANES) if xcol[n] > xe[n]]
    be2 = bend(westers, xe, xcol, 23.60)
    be2.update(bend(easters, xe, xcol, 22.60, west=False))
    for n in E_LANES:
        if n in stubs:
            pts[n] += [(xe[n], be2[n][0]), (xcol[n], be2[n][1])]
    # ---------------------------------------------------------------- 4. columns, vias, the L1 lanes that run on
    rowA, rowB, ok_l1 = [], [], set()
    cols = W_LANES + E_LANES
    for i, n in enumerate(cols):
        if n not in stubs:
            continue
        top = FIELD_TOP if n in NO_VIA else (Y_A if i % 2 == 0 else Y_B)
        poly = _dedup(pts[n] + [(xcol[n], top)])
        bad = None
        for a, b in zip(poly, poly[1:]):
            r = S.check_seg(n, L.F, a, b, HW, report=True)
            if r:
                bad = (a, b, r[:3])
                break
        if bad:
            log("  north L1 %-14s FAIL at %s-%s: %s" % (n, bad[0], bad[1], bad[2]))
            R.FAILS.append((n, ["north L1"]))
            continue
        R.add_route(n, "F", poly, LANE_W)
        ok_l1.add(n)
        if n in NO_VIA:
            continue
        if not S.check_via(n, xcol[n], top, novia=R.GRID_NOVIA):
            log("  north: via of %s at (%.2f, %.2f) not legal" % (n, xcol[n], top))
            R.FAILS.append((n, ["north via"]))
            continue
        R.add_via(n, xcol[n], top)
        (rowA if top == Y_A else rowB).append(n)
    log("  north L1: %d of %d lanes to their column; vias row A %d, row B %d" % (
        len(ok_l1), len(cols), len(rowA), len(rowB)))
    # ---------------------------------------------------------------- 5. L4 nested rows to the bus end
    # band: the lanes to the north J5 pins (and MOSI/MISO) take the north band, the others the south band; within a band
    # the east lane is outermost. This split gives the bus (north to south) the order closest to the J5 pin order
    # (21 inversions, the minimum over all 2^18 splits; the J5 legs cross on L1 where they must)
    bus = {}
    vias = {n: (Y_A if n in rowA else Y_B) for n in rowA + rowB}
    north = sorted([n for n in vias if n in NORTH_BAND], key=lambda n: xcol[n])
    south = sorted([n for n in vias if n not in NORTH_BAND], key=lambda n: xcol[n])
    for k, n in enumerate(south):
        yt = round(Y_A + 0.47 + ROW_PITCH * k, 4)
        if R.fixed(n, "B", [(xcol[n], vias[n]), (xcol[n], yt), (X_BUS, yt)], w=LANE_W):
            bus[n] = (X_BUS, yt)
    for k, n in enumerate(north):
        yt = round(Y_B - 0.47 - ROW_PITCH * k, 4)
        if R.fixed(n, "B", [(xcol[n], vias[n]), (xcol[n], yt), (X_BUS, yt)], w=LANE_W):
            bus[n] = (X_BUS, yt)
    log("  north bus: %d lanes on L4 at x %.2f" % (len(bus), X_BUS))
    # ---------------------------------------------------------------- 6. bus end -> pads; column tops -> pads
    return stubs, {"bus": bus, "xcol": xcol, "ok_l1": ok_l1}


def run_legs(R, L, S, state, log):
    """second half (after the west / east lanes are routed, so the legs keep out of their L1 exits): the J5 legs from
    the bus ends and the column tops of the L1 lanes to their pads"""
    bus, xcol, ok_l1 = state["bus"], state["xcol"], state["ok_l1"]
    legs, extra = {}, {}
    for n in bus:
        pads = sorted((p["ref"], p["num"]) for p in S.pads if p["net"] == n and p["ref"] != "U9")
        legs[n] = [R.pt(bus[n][0], bus[n][1], L.B)] + [R.P(r, m) for r, m in pads if r == "J5"]
        extra[n] = [(r, m) for r, m in pads if r != "J5"]       # the I2C3 pull-ups R62 / R63: joined after the J5 leg
    # the J5 legs one by one, from the south bus row to the north one: each leg turns south-west from its row, parallel
    # to the legs already routed below it (planar where the pin order follows the bus order); where it does not, the
    # exact router crosses on L1 with a via pair (the west lanes are routed already; the legs go round their exits)
    done = []

    def l4_cost(lay, X, Y):
        import numpy as np
        return np.full(X.shape, 2.5 if lay == L.F else 1.0)
    import l5lib
    for n in sorted(bus, key=lambda q: -bus[q][1]):
        ok = False
        for m in (4.0, 8.0, 14.0):    # the wider window lets a leg use the strip west of J5 (x 0.45-2.0)
            ok = l5lib.route_checked(R, S, n, legs[n], 4.0, layers=L.F | L.B, via_ok=True, margin=m, w=LANE_W,
                                     cost_fn=l4_cost, forbid=[(L.B, L.FAN)])
            if ok:
                break
        if ok:
            fold(R, n, bus[n])
            for r, m in extra[n]:
                ok_e = False
                for mg in (6.0, 12.0):
                    ok_e = R.route_net(n, [R.P(r, m), R.pt(bus[n][0], bus[n][1], L.B)], layers=L.F | L.B, w=LANE_W,
                                       via_ok=True, via_cost=2.0, margin=mg, forbid=[(L.B, L.FAN)])
                    if ok_e:
                        break
                log("  north %-14s pull-up %s.%s: %s" % (n, r, m, "ok" if ok_e else "FAIL (left to Freerouting)"))
        log("  north J5 %-14s from (%.2f, %.2f) -> %s: %s" % (n, bus[n][0], bus[n][1], " ".join(
            R.term_name(t) for t in legs[n][1:]), "ok" if ok else "FAIL"))
        if ok:
            done.append(n)
    for n in NO_VIA:
        if n not in ok_l1:
            continue
        pads = sorted((p["ref"], p["num"]) for p in S.pads if p["net"] == n and p["ref"] != "U9")
        first = [q for q in pads if q[0] in ("J5", "R66", "R67", "R70")] or pads
        import json as _json
        import l5_priority as PR
        rest = [q for q in pads if q not in first[:1]]
        first = first[:1]
        ok = False
        top = FIELD_TOP
        for k in range(4):
            if k:
                # the last start made an acute joint with the column (the route left it back south): the column
                # runs on 0.6 mm further north and the route starts there
                nt = round(top - 0.6, 3)
                if not R.fixed(n, "F", [(xcol[n], top), (xcol[n], nt)], w=LANE_W):
                    break
                top = nt
            for mg in (4.0, 8.0, 14.0):
                before = _json.loads(_json.dumps(R.ROUTES.get(n)))
                n_items, n_holes = len(S.items), len(S.holes)
                ok = l5lib.route_checked(R, S, n, [R.pt(xcol[n], top, L.F)] + [R.P(r, m) for r, m in first], 4.0,
                                         layers=L.F | L.B, w=LANE_W, via_ok=True, margin=mg, forbid=[(L.B, L.FAN)])
                if ok and PR.acute_joint(n, before):
                    del S.items[n_items:]
                    del S.holes[n_holes:]
                    S._arr = None
                    R.ROUTES[n] = before
                    ok = False
                    log("  north %-14s start (%.2f, %.2f): acute joint, retry further north" % (n, xcol[n], top))
                    break
                if ok:
                    break
            if ok:
                break
        state["top"] = state.get("top", {})
        state["top"][n] = top
        if ok:
            drop_covered(R, n)
        for r, m in rest if ok else []:
            # the further pads (test pad, pull-up) join from the first pad, not back along the lane (no tee at 45 deg)
            ok_e = False
            for mg in (3.0, 6.0, 12.0):
                ok_e = R.route_net(n, [R.P(*first[0]), R.P(r, m)], layers=L.F | L.B, w=LANE_W,
                                   via_ok=True, via_cost=2.0, margin=mg, forbid=[(L.B, L.FAN)])
                if ok_e:
                    break
            log("  north %-14s %s.%s: %s" % (n, r, m, "ok" if ok_e else "FAIL (left to Freerouting)"))
        log("  north %-14s column top -> %s: %s" % (n, " ".join("%s.%s" % q for q in pads), "ok" if ok else "FAIL"))
        if ok:
            done.append(n)
    return done


def negotiate(R, L, S, legs, log, iters=8):
    import numpy as np
    import l5_lanes as LN
    import l5lib
    plans = [LN.Plan(n, legs[n]) for n in sorted(legs)]
    NX = LN.NX
    occ = {lay: np.zeros((NX, NX), np.float32) for lay in (L.F, L.B)}
    hist = {lay: np.zeros((NX, NX), np.float32) for lay in (L.F, L.B)}
    pres = 0.5
    for it in range(iters):
        for Pl in plans:
            if Pl.occ:
                for lay, idx in Pl.occ.items():
                    occ[lay].flat[idx] -= 1
            p = LN.plan_route(Pl, occ, hist, pres)
            Pl.path = p or []
            Pl.occ = LN.occupancy(Pl)
            for lay, idx in Pl.occ.items():
                occ[lay].flat[idx] += 1
        over, bad = 0, set()
        for Pl in plans:
            for lay, idx in Pl.line.items():
                c = occ[lay].flat[idx] - 1.0 > 0
                if c.any():
                    over += int(c.sum())
                    bad.add(Pl.net)
                    hist[lay].flat[idx[c]] += 0.5
        log("  north legs: iteration %d: %d conflicting cells, %d nets" % (it + 1, over, len(bad)))
        if not over:
            break
        pres *= 1.8
    pending = {lay: occ[lay].copy() for lay in occ}
    done = []
    for Pl in sorted(plans, key=lambda q: (len(q.path), q.net)):
        for lay, idx in Pl.occ.items():
            pending[lay].flat[idx] -= 1

        def cost_fn(lay, X, Y, Pl=Pl):
            jj = np.clip(np.rint(X / L.RES - 0.5).astype(int), 0, NX - 1)
            ii = np.clip(np.rint(Y / L.RES - 0.5).astype(int), 0, NX - 1)
            return (1.0 + hist[lay][ii, jj]) * (1.0 + 20.0 * np.maximum(pending[lay][ii, jj], 0)) * \
                (2.5 if lay == L.F else 1.0)
        ok = l5lib.route_checked(R, S, Pl.net, Pl.terms, 4.0, layers=L.F | L.B, via_ok=True, margin=4.0,
                                 w=LANE_W, cost_fn=cost_fn, forbid=[(L.B, L.FAN)])
        log("  north J5 %-14s -> %s: %s" % (Pl.net, " ".join(R.term_name(t) for t in Pl.terms[1:]),
                                            "ok" if ok else "FAIL"))
        if ok:
            done.append(Pl.net)
    return done


def drop_covered(R, n):
    """a second branch of a multi-pad route can start back along the first one (the router's tree root is the column
    top): a segment that lies inside another segment of the net on the same layer is dropped (no duplicate copper,
    no 0 deg joint)"""
    segs = []
    for lay, pts, w in R.ROUTES[n]["tracks"]:
        for a, b in zip(pts, pts[1:]):
            segs.append([lay, tuple(a), tuple(b), w])

    def on(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            return False
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
        if t < -1e-6 or t > 1 + 1e-6:
            return False
        return math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]) < 1e-3
    keep = []
    for i, s1 in enumerate(segs):
        cov = False
        for j, s2 in enumerate(segs):
            if i == j or s1[0] != s2[0] or s2[3] < s1[3] - 1e-9:
                continue
            l1 = math.hypot(s1[2][0] - s1[1][0], s1[2][1] - s1[1][1])
            l2 = math.hypot(s2[2][0] - s2[1][0], s2[2][1] - s2[1][1])
            if (l2 > l1 + 1e-9 or (abs(l2 - l1) < 1e-9 and j < i)) and on(s1[1], s2[1], s2[2]) and \
                    on(s1[2], s2[1], s2[2]):
                cov = True
                break
        if not cov:
            keep.append(s1)
    R.ROUTES[n]["tracks"] = [(lay, [list(a), list(b)], w) for lay, a, b, w in keep]


def fold(R, n, end):
    """a leg that leaves its bus end back along its own row (to a via further east) would retrace the row (a 180 deg
    joint): the row is cut back to where the leg leaves it and the retraced piece dropped"""
    tr = R.ROUTES[n]["tracks"]
    row = [k for k, (lay, pts, w) in enumerate(tr) if lay == "B" and len(pts) >= 2 and
           abs(pts[-1][0] - end[0]) < 1e-6 and abs(pts[-1][1] - end[1]) < 1e-6]
    leg = [k for k, (lay, pts, w) in enumerate(tr) if lay == "B" and len(pts) >= 2 and k not in row and
           abs(pts[0][0] - end[0]) < 1e-6 and abs(pts[0][1] - end[1]) < 1e-6]
    if not row or not leg:
        return
    rp, lp = tr[row[0]][1], tr[leg[0]][1]
    q = lp[1]
    if abs(q[1] - end[1]) > 1e-6 or q[0] <= end[0]:
        return                                   # the leg leaves westward or sideways: nothing to fold
    if q[0] >= rp[-2][0] - 1e-6:
        return
    rp[-1] = [q[0], q[1]]
    del lp[0]
    # a leg that then climbs back east at 45 deg (to a via) would meet the row at 45 deg (acute): the row ends further
    # east instead, where the mirrored 45 deg piece starts, so the leg turns off the row at 135 deg
    if len(lp) >= 2:
        p = lp[1]
        dx, dy = p[0] - q[0], p[1] - q[1]
        if dx > 1e-6 and abs(abs(dx) - abs(dy)) < 1e-3:
            ne = [round(p[0] + abs(dy), 4), q[1]]
            if ne[0] < rp[-2][0] - 1e-6:
                rp[-1] = ne
                lp[0] = ne
    if len(lp) < 2:
        del tr[leg[0]]


def _dedup(poly):
    out = [poly[0]]
    for p in poly[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    # drop collinear middle points
    k = 1
    while k < len(out) - 1:
        a, b, c = out[k - 1], out[k], out[k + 1]
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-9:
            del out[k]
        else:
            k += 1
    return out
