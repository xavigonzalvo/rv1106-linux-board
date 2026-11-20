#!/usr/bin/env python3
"""Layout phase L5, step 3 (design/.venv): clean up the Freerouting result, check it exactly, route what Freerouting
left or got wrong by script, and widen the 0.10 mm lane tracks where they fit.

    design/.venv/bin/python -I design/pcb/scripts/l5_cleanup.py
      in : design/pcb/l5/board_geo_lanes.json (l4_export.py after L5_LANES), l5/fr_raw.json (l5_freeroute.py),
           l5/lanes.json (stubs), l5/open_nets.json (nets with KiCad unconnected items before Freerouting)
      out: design/pcb/l5/fr_routes.json (group L5_FREEROUTE), l5/script_routes.json (group L5_SCRIPT), l5/cleanup.log

Steps, per net of the Freerouting session:
  1. graph clean-up: dangling segments (an end that touches no pad, track or via of the net) are removed until none is
     left; vias that join copper on one layer only are removed ("pointless" vias); collinear consecutive segments of
     the same width are merged;
  2. exact check of every segment and via against all copper with the board's rules (l4lib.Store.required: class
     clearances, the .kicad_dru rules incl. the 30 mil pair rules, the crystal guard, SW-node areas, hole rules);
     a net with any violation, a non-octilinear segment or an acute bend loses all its Freerouting copper and is
     routed by script instead (l4_route.route_net, the L4 router: exact, octilinear);
  3. nets Freerouting did not finish are routed by script the same way (terminals: the lane stub end and every pad of
     the net that the existing copper does not reach);
  4. widening: lane tracks (0.10 mm, D-113) are widened to the DEFAULT 0.15 mm segment by segment where the exact check
     passes; VDD_ARM tracks to 0.80 / 0.50 / 0.40 mm (PWR_0V9, layout.md §3) where they fit, else they stay 0.30 mm.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
L5 = os.path.join(PCB, "l5")
GEO = os.path.join(L5, "board_geo_lanes.json")
sys.argv = [sys.argv[0], GEO, os.path.join(L5, "_unused_l4_routes.json")]
sys.path.insert(0, HERE)
import l4_route as R  # noqa: E402
import l4lib as L  # noqa: E402
import l5lib  # noqa: E402

L.VIA_ETH = True
L.VIA_USB_STRICT = True   # D-115        # D-113: new vias keep 0.76 mm from the ETH lines
geo = R.geo
S = R.S
LOG = []
VDD_ARM_W = (0.80, 0.50, 0.40)
LANE_W_TO = 0.15


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def k3(p):
    return (round(p[0], 3), round(p[1], 3))


def on_seg(p, a, b, tol):
    return L.pt_seg_v(p[0], p[1], a[0], a[1], b[0], b[1]) <= tol


LAYERS = {"F": L.F, "B": L.B}


def anchor(net, p, lay):
    """True if point p on layer lay touches existing copper of the net (pad, track, via)"""
    for q in S.pads:
        if q["net"] == net and q["lay"] & LAYERS[lay] and L.inside_poly(p[0], p[1], q["poly"]):
            return True
    for t in geo["tracks"]:
        if t["net"] == net and t["layer"] == lay and on_seg(p, t["a"], t["b"], t["w"] / 2 + 1e-3):
            return True
    for v in geo["vias"]:
        if v["net"] == net and math.hypot(v["x"] - p[0], v["y"] - p[1]) <= v["d"] / 2:
            return True
    return False


def clean_net(net, r):
    segs = [(t[0], tuple(t[1][0]), tuple(t[1][1]), t[2]) for t in r["tracks"] if t[0] in LAYERS]
    vias = [tuple(v) for v in r["vias"]]
    removed_s = removed_v = 0
    changed = True
    while changed:
        changed = False
        deg = {}
        for (lay, a, b, w) in segs:
            for p in (a, b):
                deg[(lay, k3(p))] = deg.get((lay, k3(p)), 0) + 1
        vset = {k3(v) for v in vias}
        keep = []
        for s in segs:
            lay, a, b, w = s
            dead = False
            for p in (a, b):
                if deg[(lay, k3(p))] == 1 and k3(p) not in vset and not anchor(net, p, lay):
                    # an end on another new segment's body (T junction) is not dangling
                    if not any(o is not s and o[0] == lay and on_seg(p, o[1], o[2], 1e-3) for o in segs):
                        dead = True
            if dead:
                removed_s += 1
                changed = True
            else:
                keep.append(s)
        segs = keep
        nv = []
        for v in vias:
            sides = set()
            for (lay, a, b, w) in segs:
                if on_seg(v, a, b, 1e-3):
                    sides.add(lay)
            for lay in ("F", "B"):
                if anchor(net, v, lay):
                    sides.add(lay)
            if len(sides) < 2:
                removed_v += 1
                changed = True
            else:
                nv.append(v)
        vias = nv
    # merge collinear chains (degree-2 nodes, same layer and width, no via, no anchor)
    merged = 0
    again = True
    while again:
        again = False
        ends = {}
        for i, (lay, a, b, w) in enumerate(segs):
            ends.setdefault((lay, k3(a)), []).append(i)
            ends.setdefault((lay, k3(b)), []).append(i)
        vset = {k3(v) for v in vias}
        for (lay, p), idx in ends.items():
            if len(idx) != 2 or p in vset:
                continue
            i, j = idx
            s1, s2 = segs[i], segs[j]
            if s1[3] != s2[3]:
                continue
            a = s1[1] if k3(s1[2]) == p else s1[2]
            c = s2[2] if k3(s2[1]) == p else s2[1]
            m = s1[2] if k3(s1[2]) == p else s1[1]
            cr = (m[0] - a[0]) * (c[1] - m[1]) - (m[1] - a[1]) * (c[0] - m[0])
            dot = (m[0] - a[0]) * (c[0] - m[0]) + (m[1] - a[1]) * (c[1] - m[1])
            if abs(cr) < 1e-6 and dot > 0 and not anchor(net, m, lay):
                segs = [s for q, s in enumerate(segs) if q not in (i, j)] + [(lay, a, c, s1[3])]
                merged += 1
                again = True
                break
    return segs, vias, removed_s, removed_v, merged


def geometry_faults(segs):
    """non-octilinear segments and acute bends (< 90 deg interior angle) between two segments of one node"""
    bad = []
    for (lay, a, b, w) in segs:
        dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
        if min(dx, dy) > 0.002 and abs(dx - dy) > 0.002:
            bad.append(("angle", lay, k3(a), k3(b)))
    ends = {}
    for (lay, a, b, w) in segs:
        ends.setdefault((lay, k3(a)), []).append((a, b))
        ends.setdefault((lay, k3(b)), []).append((b, a))
    for (lay, p), lst in ends.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                u = (lst[i][1][0] - lst[i][0][0], lst[i][1][1] - lst[i][0][1])
                v = (lst[j][1][0] - lst[j][0][0], lst[j][1][1] - lst[j][0][1])
                nu, nv = math.hypot(*u), math.hypot(*v)
                if nu < 1e-6 or nv < 1e-6:
                    continue
                cosang = (u[0] * v[0] + u[1] * v[1]) / nu / nv
                if cosang > math.cos(math.radians(89.0)):      # interior angle < 90 deg: acute
                    bad.append(("acute", lay, p))
    return bad


def store_add(net, segs, vias):
    idx = []
    for (lay, a, b, w) in segs:
        S.add_track(net, LAYERS[lay], a, b, w / 2)
        idx.append(len(S.items) - 1)
    for v in vias:
        S.add_via(net, v[0], v[1], L.VIA_D / 2, L.VIA_DR / 2)
    return idx


def check_net(net, segs, vias):
    bad = []
    for (lay, a, b, w) in segs:
        v = S.check_seg(net, LAYERS[lay], a, b, w / 2, report=True)
        if v:
            bad.append(("seg", lay, k3(a), k3(b), v[:2]))
    for v in vias:
        if not S.check_via(net, v[0], v[1], self_ok=True, own_pad_ok=True):
            bad.append(("via", k3(v)))
    return bad


def touched(net, extra_tracks=()):
    """pads of `net` reached by the copper of the net (existing tracks/vias + extra tracks)"""
    pts = [(tuple(t["a"]), t["layer"]) for t in geo["tracks"] if t["net"] == net]
    pts += [(tuple(t["b"]), t["layer"]) for t in geo["tracks"] if t["net"] == net]
    pts += [((v["x"], v["y"]), lay) for v in geo["vias"] if v["net"] == net for lay in ("F", "B")]
    for (lay, a, b, w) in extra_tracks:
        pts += [(a, lay), (b, lay)]
    got = set()
    for q in S.pads:
        if q["net"] != net:
            continue
        for p, lay in pts:
            if q["lay"] & LAYERS[lay] and L.inside_poly(p[0], p[1], q["poly"]):
                got.add((q["ref"], q["num"]))
                break
    return got


def script_route(net, stubs, margin=4.0, via_cost=4.0):
    """route a net by the L4 router: the lane stub end (if any) + every pad not reached by the existing copper"""
    terms = []
    if net in stubs:
        x, y, _ = stubs[net]
        terms.append(R.pt(x, y, L.F))
    done = touched(net)
    for q in S.pads:
        if q["net"] == net and q["ref"] != "U9" and (q["ref"], q["num"]) not in done and q["num"] != "copper":
            terms.append(R.P(q["ref"], q["num"]))
    if net not in stubs and done:
        # start from a pad the existing copper already reaches (it carries the rest of the net)
        ref, num = sorted(done)[0]
        if ref != "U9":
            terms.insert(0, R.P(ref, num))
        else:
            # U9 pin reached by an L3 escape: start at the free end / via of the escape
            vs = [v for v in geo["vias"] if v["net"] == net]
            if vs:
                terms.insert(0, R.pt(vs[0]["x"], vs[0]["y"], L.B))
    if len(terms) < 2:
        log("  script %s: nothing to route (%d terminals)" % (net, len(terms)))
        return True
    w = 0.30 if R.width(net) > 0.30 else max(0.15, R.width(net)) if net not in stubs else 0.10
    log("  script %s (w %.2f): %s" % (net, w, ", ".join(R.term_name(t) for t in terms)))
    # L4 under U9 (the U9_FAN square) is kept for the nets that leave by an inner via there (PB_INT_N, USB_SEL, ...)
    inner = any(L.FAN[0] <= v["x"] <= L.FAN[2] and L.FAN[1] <= v["y"] <= L.FAN[3] for v in geo["vias"]
                if v["net"] == net)
    forbid = [] if inner else [(L.B, L.FAN)]
    return l5lib.route_checked(R, S, net, terms, via_cost, layers=L.F | L.B, via_ok=True, margin=margin, w=w,
                               forbid=forbid)


def widen(routes, nets, widths):
    """try wider widths per segment (exact check against everything, the store updated as we go)"""
    n_ok = n_all = 0
    for net in nets:
        r = routes.get(net)
        if not r:
            continue
        new = []
        for lay, pts, w in r["tracks"]:
            for a, b in zip(pts, pts[1:]):
                n_all += 1
                a, b = tuple(a), tuple(b)
                k = find_item(net, lay, a, b)
                best = w
                for w2 in widths:
                    if w2 <= w + 1e-9:
                        break
                    if k is not None:
                        S.items[k] = S.items[k][:1] + (0,) + S.items[k][2:]      # take it out while checking
                        S._arr = None
                    ok = S.check_seg(net, LAYERS[lay], a, b, w2 / 2)
                    if k is not None:
                        S.items[k] = S.items[k][:1] + (LAYERS[lay],) + S.items[k][2:]
                        S._arr = None
                    if ok:
                        best = w2
                        break
                if best > w and k is not None:
                    it = S.items[k]
                    S.items[k] = it[:7] + (best / 2,) + it[8:]
                    S._arr = None
                    n_ok += 1
                new.append([lay, [list(a), list(b)], best])
        r["tracks"] = new
    return n_ok, n_all


def find_item(net, lay, a, b):
    for k in range(len(S.items) - 1, -1, -1):
        it = S.items[k]
        if it[0] == 0 and it[2] == net and it[1] == LAYERS[lay] and \
                abs(it[3] - a[0]) < 1e-6 and abs(it[4] - a[1]) < 1e-6 and abs(it[5] - b[0]) < 1e-6 and \
                abs(it[6] - b[1]) < 1e-6:
            return k
    return None


def main():
    # NT1.2 (VDD_ARM side of the net tie): end the track in the round part of the pad, 0.6 mm away from the net-tie
    # copper bar (no net) that joins it to NT1.1, which a track must not touch
    R.ANCHOR[("NT1", "2")] = (25.2, 40.0)
    R.setup_novia()
    R.setup_sw_areas()
    # round 2: no new via within 0.55 mm of the VDD_0V9 free strips (planes.NECK_FREE; check_routing 'neck')
    R.GRID_NOVIA.extend([(42.95 - 0.56, 28.05 - 0.56, 63.5 + 0.56, 30.75 + 0.56), (60.5 - 0.56, 28.05 - 0.56, 63.5 + 0.56, 35.5 + 0.56)])
    raw = json.load(open(os.path.join(L5, "fr_raw.json")))["routes"]
    # deterministic order (round 2): the SES import lists items in pcbnew's (UUID) order; sort segments and vias
    for r in raw.values():
        r["tracks"] = sorted(r["tracks"], key=lambda t: (t[0], [[round(c, 4) for c in q] for q in t[1]], t[2]))
        r["vias"] = sorted(r["vias"], key=lambda v: (round(v[0], 4), round(v[1], 4)))
        # round 3 (DRC track_width on ONOFF_EN): Freerouting necks some pad entries to 0.09 mm; nothing below the
        # 0.10 mm floor is kept (the exact check below rips the net if 0.10 mm does not fit there)
        r["tracks"] = [[t[0], t[1], max(t[2], 0.10)] for t in r["tracks"]]
    geo["tracks"].sort(key=lambda t: (t["net"], t["layer"], round(t["a"][0], 4), round(t["a"][1], 4),
                                      round(t["b"][0], 4), round(t["b"][1], 4), t["w"]))
    geo["vias"].sort(key=lambda v: (v["net"], round(v["x"], 4), round(v["y"], 4)))
    stubs = json.load(open(os.path.join(L5, "lanes.json")))["stubs"]
    open_nets = json.load(open(os.path.join(L5, "open_nets.json")))
    plane = ("GND", "VCC_3V3", "VDD_0V9", "VCC5V0_SYS", "VBUS_USBA")
    cleaned = {}
    tot = [0, 0, 0]
    for net in sorted(raw):
        if net in plane or net not in open_nets:
            log("  ignore Freerouting copper on %s (not an open net)" % net)
            continue
        segs, vias, rs, rv, mg = clean_net(net, raw[net])
        tot[0] += rs
        tot[1] += rv
        tot[2] += mg
        cleaned[net] = (segs, vias)
    log("== clean-up: %d dangling segments, %d pointless vias removed, %d collinear joints merged" % tuple(tot))
    # exact check: add everything, then check each net
    for net, (segs, vias) in cleaned.items():
        store_add(net, segs, vias)
    rip = {}
    for net, (segs, vias) in sorted(cleaned.items()):
        bad = check_net(net, segs, vias) + geometry_faults(segs)
        if bad:
            rip[net] = bad
            log("  RIP %s: %d faults, first %s" % (net, len(bad), bad[:2]))
    # rebuild the store without the ripped nets
    n0 = len(geo["tracks"])  # noqa: F841
    S.items[:] = [it for it in S.items if not (it[8] == -2 and it[2] in rip)]
    S.holes[:] = [h for h in S.holes if not (h[3] in rip and any(
        abs(h[0] - v[0]) < 1e-6 and abs(h[1] - v[1]) < 1e-6 for v in cleaned.get(h[3], ([], []))[1]))]
    S._arr = None
    fr_routes = {}
    for net, (segs, vias) in cleaned.items():
        if net in rip:
            continue
        fr_routes[net] = {"tracks": [[lay, [list(a), list(b)], w] for (lay, a, b, w) in segs],
                          "vias": [list(v) for v in vias]}
    # script routing: ripped nets and nets Freerouting did not touch (KiCad connectivity decides completeness later)
    todo = sorted(set(rip) | {n for n in open_nets if n not in cleaned and n not in plane})
    log("== script routing (%d nets): %s" % (len(todo), " ".join(todo)))
    R.ROUTES.clear()
    for net in todo:
        if not script_route(net, stubs):
            log("  FAIL script %s" % net)
    # second attempt for what is still open: larger window, cheaper vias (deterministic)
    again = sorted({f[0] for f in R.FAILS})
    if again:
        log("== script routing, second attempt (margin 9 mm, via cost 1.5): %s" % " ".join(again))
        R.FAILS.clear()
        for net in again:
            if not script_route(net, stubs, margin=9.0, via_cost=1.5):
                log("  FAIL script (2nd) %s" % net)
    script_routes = json.loads(json.dumps(R.ROUTES))
    npol = l5lib.polish(script_routes, S)
    log("== polish: %d end points dropped inside pads" % npol)
    # widen
    lane_nets = sorted(stubs)
    allr = {}
    for d in (fr_routes, script_routes):
        for n, r in d.items():
            allr.setdefault(n, r)
    n1 = widen(fr_routes, lane_nets, (LANE_W_TO,))
    n2 = widen(script_routes, lane_nets, (LANE_W_TO,))
    n3 = widen(fr_routes, ["VDD_ARM"], VDD_ARM_W)
    n4 = widen(script_routes, ["VDD_ARM"], VDD_ARM_W)
    log("== widening: lanes %d/%d (Freerouting) %d/%d (script) segments to 0.15 mm; VDD_ARM %d/%d, %d/%d" %
        (n1 + n2 + n3 + n4))
    # round 2 (verifier minor): Freerouting left some segments of non-lane DEFAULT nets below 0.15 mm (0.112 mm on
    # U4_EN, PWR_EN, VCC_DDR_1V8_EN, PB_IN, EN_N, UART2_RX_HDR): widen every such segment to its class width where the
    # exact check allows; what stays thin is listed (D-114 b)
    thin = sorted({n for d in (fr_routes, script_routes) for n, r in d.items() if n not in lane_nets and
                   any(w < R.width(n) - 1e-6 for _, _, w in r["tracks"])})
    for n in thin:
        cw = R.width(n)
        ws = tuple(x for x in (cw, 0.15, 0.12) if x <= cw + 1e-9 and x >= 0.12)
        widen(fr_routes, [n], ws)
        widen(script_routes, [n], ws)
    still = {}
    for d in (fr_routes, script_routes):
        for n, r in d.items():
            if n in lane_nets:
                continue
            for lay, pts, w in r["tracks"]:
                if w < R.width(n) - 1e-6:
                    ln = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
                    still.setdefault(n, [0.0, 9.0])
                    still[n][0] += ln
                    still[n][1] = min(still[n][1], w)
    log("== widening of non-lane nets below class width (%s): still thin %s" % (
        " ".join(thin), {n: (round(v[0], 2), v[1]) for n, v in sorted(still.items())}))
    # final self-check of all new copper
    nbad = 0
    for tag, d in (("fr", fr_routes), ("script", script_routes)):
        for net, r in sorted(d.items()):
            for lay, pts, w in r["tracks"]:
                for a, b in zip(pts, pts[1:]):
                    v = S.check_seg(net, LAYERS[lay], tuple(a), tuple(b), w / 2, report=True)
                    if v:
                        nbad += 1
                        log("  SELFCHECK %s %s %s %s-%s %s" % (tag, net, lay, a, b, v[:2]))
            for x, y in r["vias"]:
                if not S.check_via(net, x, y, self_ok=True, own_pad_ok=True):
                    nbad += 1
                    log("  SELFCHECK via %s %s (%.3f, %.3f)" % (tag, net, x, y))
    log("== self-check: %d violations; Freerouting nets kept %d, script nets %d, script fails %s" %
        (nbad, len(fr_routes), len(script_routes), R.FAILS))
    json.dump({"routes": fr_routes, "ripped": sorted(rip), "log": LOG}, open(os.path.join(L5, "fr_routes.json"), "w"),
              indent=0, sort_keys=True)
    json.dump({"routes": script_routes, "fails": R.FAILS, "log": R.LOG}, open(os.path.join(L5, "script_routes.json"),
                                                                               "w"), indent=0, sort_keys=True)
    open(os.path.join(L5, "cleanup.log"), "w").write("\n".join(LOG + R.LOG) + "\n")


if __name__ == "__main__":
    main()
