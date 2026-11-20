#!/usr/bin/env python3
"""Layout phase L5 (design/.venv): the SoC supply nets and the boot / power-control nets, routed by script BEFORE
the lane routing and Freerouting (round 2 of L5, verifier blockers soc/onoff; D-114 a). Used as a module by
l5_lanes.py (pass 1 after the lane stubs, pass 2 after the negotiated lane routing); the routes of the non-lane nets
are written to design/pcb/l5/priority.json (group L5_PRIORITY). Standalone (for trials):

    design/.venv/bin/python -I design/pcb/scripts/l5_priority.py [geo.json] [out.json]

Per net (PRIORITY order), the pieces of the net that are not joined yet are found from the copper (l5conn: pads,
tracks, vias, the way KiCad joins them). The piece holding the U9 pin is the root; every other piece is joined to the
root by the L4 router (l4_route.route_net: exact clearances incl. every .kicad_dru rule, octilinear, vias allowed
outside the no-via areas, L4 under U9 only for the nets that leave by an inner via there), trying the closest
root/piece terminal pairs first (pads, vias, free track ends, and points along the root's tracks so a branch may tee
into the copper) and then a wider search window (4 / 12 mm).
Pass 1 joins the functional parts (pin, decoupler, filter part, pull-up, load); pass 2 the test pads (TPxx), routed
last. Width: class width first (PWR_SUB 0.30 mm, DEFAULT/SENSE 0.15 mm), then narrower where the class width has no
path (PWR_SUB 0.25/0.20 mm, DEFAULT/SENSE 0.12/0.10 mm; listed by check_routing.py L5-width, D-114 b).
The three DEFAULT nets whose U9 inner via is boxed in on L4 (USB_SEL, SDMMC_PWREN, PB_INT_N, D-114 c) only get their
parts joined to each other. Deterministic (fixed orders, sorted candidates).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
if __name__ == "__main__":
    GEO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PCB, "l5", "board_geo_prio_in.json")
    OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PCB, "l5", "priority.json")
    sys.argv = [sys.argv[0], GEO, os.path.join(PCB, "l5", "_unused_l4_routes.json")]
sys.path.insert(0, HERE)
import l4_route as R  # noqa: E402
import l4lib as L  # noqa: E402
import l5conn  # noqa: E402
import l5lib  # noqa: E402

L.VIA_ETH = True
L.VIA_USB_STRICT = True   # D-115        # D-113: new vias keep 0.76 mm from the ETH lines
geo = R.geo
S = R.S

# supply nets first (pin -> decoupler -> filter part), then boot / power control (verifier round 1, blockers soc/onoff)
# (VCC3V3_RTC leaves U9 by an inner via and is routed to D2/R34/C75 in L4, D-114 a; only TP18 is joined here.
#  USB_SEL / SDMMC_PWREN / PB_INT_N: their inner vias are boxed in on L4, D-114 c; they are tried, and stay open.)
PRIORITY = ["VCC3V3_RTC", "VCC3V3_RTC_IN", "AVDD1V8_USB", "VCC1V8_CODEC", "ETH_AVDD1V8", "FEPHY_AVDD3V3",
            "NPOR", "PWR_KILL", "USBA_VBUS_EN", "PWR_BTN_N", "UART2_TX_HDR", "UART2_RX_HDR",
            "SDMMC_PWREN", "USB_SEL", "PB_INT_N"]
MARGINS = (4.0, 12.0)
NECK_FREE = [(42.95, 28.05, 63.5, 30.75), (60.5, 28.05, 63.5, 35.5)]   # planes.NECK_FREE (STRIP-N, STRIP-JP1)
NCAND = 4
BOXED = ("SDMMC_PWREN", "USB_SEL", "PB_INT_N", "USBA_VBUS_EN")   # round 3: USBA_VBUS_EN's lane is boxed in STRIP-N
                                                                   # (D-114 k, owner); R61.1 is joined to U8.4
# routed after the negotiated lanes (pass 2) because they share the north strip with lanes of the same function:
# UART2_RX_HDR (R67.1 -> J6) taken first in a trial blocked the UART2_RX lane (U9 -> R67.2), D-114 a
LATE = ("UART2_RX_HDR",)   # D-114 c: no L4 way out of the U9 field; joined where possible


def log(*a):
    R.log(*a)


EARLY_TP = ("TP23", "TP18", "TP24")


def early_tp(comp):
    return any(r in EARLY_TP for r, _ in comp["pads"])


def is_tp(comp):
    return comp["pads"] and all(r.startswith("TP") for r, _ in comp["pads"])


def terminals(comp, net, tee=False):
    """candidate router terminals of a piece: its pads (not U9: 0.35 mm pitch), vias (both layers), free track ends;
    with tee=True also points along its tracks every 0.5 mm (a branch may tee into the piece's copper, e.g. into the
    escape between a U9 pin and its ring-1 capacitor when the capacitor pad itself is boxed in)"""
    out = []
    if tee:
        for (lay, a, b, w) in comp["segs"]:
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.5))
            for k in range(n + 1):
                out.append(R.pt(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n,
                                L.F if lay == "F" else L.B))
    for ref, num in comp["pads"]:
        if ref != "U9":
            out.append(R.P(ref, num))
    for x, y in comp["vias"]:
        out.append(R.pt(x, y, L.B))
        out.append(R.pt(x, y, L.F))
    for x, y, lay in comp["ends"]:
        out.append(R.pt(x, y, L.F if lay == "F" else L.B))
    return out


def inner(net):
    return any(L.FAN[0] <= v["x"] <= L.FAN[2] and L.FAN[1] <= v["y"] <= L.FAN[3] for v in geo["vias"] if v["net"] == net)


def join(net, root, comp, widths):
    src = terminals(root, net, tee=True)
    dst = terminals(comp, net)
    pairs = sorted(((math.hypot(a["x"] - b["x"], a["y"] - b["y"]), i, j) for i, a in enumerate(src)
                    for j, b in enumerate(dst)))
    seen = set()
    cand = []
    for d, i, j in pairs:
        k = (R.term_name(src[i]), R.term_name(dst[j]))
        if k in seen:
            continue
        seen.add(k)
        cand.append((src[i], dst[j]))
        if len(cand) >= NCAND:
            break
    forbid = [] if inner(net) else [(L.B, L.FAN)]
    # no via within 0.55 mm of the VDD_0V9 free strips (planes.NECK_FREE, checked by check_routing 'neck'): the via
    # centre rule areas of the L4 router plus those strips grown by 0.56 mm
    novia = list(R.GRID_NOVIA) + [(x0 - 0.56, y0 - 0.56, x1 + 0.56, y1 + 0.56) for x0, y0, x1, y1 in NECK_FREE]
    for w in widths:
        for margin in MARGINS:
            for a, b in cand:
                n_fail = len(R.FAILS)
                n_items, n_holes = len(S.items), len(S.holes)
                before = json.loads(json.dumps(R.ROUTES.get(net))) if net in R.ROUTES else None
                ok = l5lib.route_checked(R, S, net, [a, b], 3.0, layers=L.F | L.B, via_ok=True, margin=margin, w=w,
                                         forbid=forbid, novia=novia)
                if ok and acute_joint(net, before):
                    # the new branch meets the net's copper at an acute angle (acid trap): undo, next candidate
                    del S.items[n_items:]
                    del S.holes[n_holes:]
                    S._arr = None
                    if before is None:
                        R.ROUTES.pop(net, None)
                    else:
                        R.ROUTES[net] = before
                    log("  %s: %s -> %s gives an acute joint, next candidate" % (net, R.term_name(a), R.term_name(b)))
                    ok = False
                if ok:
                    log("  join %s: %s -> %s (w %.2f, margin %.0f)" % (net, R.term_name(a), R.term_name(b), w, margin))
                    return True
                del R.FAILS[n_fail:]
    log("  FAIL join %s: %s" % (net, ", ".join("%s.%s" % p for p in comp["pads"]) or comp["vias"]))
    R.FAILS.append((net, ["%s.%s" % p for p in comp["pads"]]))
    return False


def _segs_of(net, routes):
    out = [(t["layer"], tuple(t["a"]), tuple(t["b"])) for t in geo["tracks"] if t["net"] == net]
    for lay, pts, w in (routes or {}).get("tracks", []):
        out += [(lay, tuple(a), tuple(b)) for a, b in zip(pts, pts[1:])]
    return out


def acute_joint(net, before):
    """True if a track end of the new copper of `net` (R.ROUTES[net] minus `before`) forms an angle < 89 deg with
    another track of the net at that point (a T into a segment body counts both halves), outside the net's pads"""
    old = {(lay, tuple(map(tuple, pts))) for lay, pts, w in (before or {}).get("tracks", [])}
    new = [(lay, pts) for lay, pts, w in R.ROUTES.get(net, {}).get("tracks", []) if (lay, tuple(map(tuple, pts)))
           not in old]
    allsegs = _segs_of(net, R.ROUTES.get(net))
    pads = [q for q in S.pads if q["net"] == net]
    for lay, pts in new:
        for end, nxt in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            if any(q["lay"] & (L.F if lay == "F" else L.B) and L.inside_poly(end[0], end[1], q["poly"]) for q in pads):
                continue
            dirs = []
            for (l2, a, b) in allsegs:
                if l2 != lay:
                    continue
                for p0, p1 in ((a, b), (b, a)):
                    if math.hypot(p0[0] - end[0], p0[1] - end[1]) < 1e-3 and math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 1e-6:
                        dirs.append((p1[0] - p0[0], p1[1] - p0[1]))
                if L.pt_seg_v(end[0], end[1], a[0], a[1], b[0], b[1]) < 1e-3 and \
                        min(math.hypot(end[0] - a[0], end[1] - a[1]), math.hypot(end[0] - b[0], end[1] - b[1])) > 1e-3:
                    dirs += [(a[0] - end[0], a[1] - end[1]), (b[0] - end[0], b[1] - end[1])]
            for i in range(len(dirs)):
                for j in range(i + 1, len(dirs)):
                    u, v = dirs[i], dirs[j]
                    nu, nv = math.hypot(*u), math.hypot(*v)
                    if nu > 1e-6 and nv > 1e-6 and (u[0] * v[0] + u[1] * v[1]) / nu / nv > math.cos(math.radians(89.0)):
                        return True
    return False


def pieces(net):
    comps = l5conn.components(geo, net, R.ROUTES.get(net))
    root = None
    for c in comps:
        if any(r == "U9" for r, _ in c["pads"]):
            root = c
            break
    root = root or comps[0]
    return root, [c for c in comps if c is not root]


def widths_of(net):
    """class width first; then narrower where the class width has no path (each such branch is listed in the log and
    in check_routing's L5-width lines, D-114 b): PWR_SUB down to 0.20 mm (DC, <= 50 mA sub-rails), DEFAULT/SENSE
    down to 0.10 mm (static control lines, as the lanes of D-113 b)"""
    w = R.width(net)
    if w >= 0.3:
        return (0.30, 0.25, 0.20)
    return (0.15, 0.12, 0.10)


def run(passes=(False, True), nets=None):
    """join the pieces of the PRIORITY nets (pass False: functional parts, pass True: test pads) on the router state
    R.ROUTES / R.S as it is (standalone: the exported board; from l5_lanes.py: the stubs, before / after the lanes)"""
    nets = nets or PRIORITY
    for tp_pass in passes:
        log("== priority pass %d: %s" % (2 if tp_pass else 1, "test pads" if tp_pass else "functional parts"))
        for net in nets:
            while True:
                root, rest = pieces(net)
                if net in LATE:          # routed whole after the lanes (pass 2): they share the lanes' space
                    todo = [c for c in rest if c["pads"]] if tp_pass else []
                else:
                    # round 3: TP23 / TP18 (NE of the SoC) join in pass 1, before NPOR's L4 branch to R35/TP7 takes
                    # the L4 corridor south of them (they were open after round 3's first rebuild)
                    todo = [c for c in rest if (is_tp(c) and not early_tp(c)) == tp_pass and c["pads"]]
                todo = [c for c in todo if (net, tuple(c["pads"])) not in DONE_FAIL]
                if not todo:
                    break
                # the piece closest to the root first
                rp = [(R.PADS[q]["x"], R.PADS[q]["y"]) for q in root["pads"]] + list(root["vias"])
                todo.sort(key=lambda c: (min(math.hypot(R.PADS[p]["x"] - x, R.PADS[p]["y"] - y)
                                             for p in c["pads"] for x, y in rp), c["pads"]))
                c = todo[0]
                if net in BOXED and any(r == "U9" for r, _ in root["pads"]):
                    # the U9 piece cannot be left on L4 (D-114 c): join the parts among themselves only
                    others = [q for q in rest if q is not c and q["pads"] and not is_tp(q)]
                    if not others or not join(net, others[0], c, widths_of(net)):
                        DONE_FAIL.add((net, tuple(c["pads"])))
                    continue
                if not join(net, root, c, widths_of(net)) and not via_in_pad_join(net, root, c):
                    DONE_FAIL.add((net, tuple(c["pads"])))


# round 3 (D-115, verifier round 2 blocker soc: VCC1V8_CODEC split, FB2.2 alone): a pad boxed in on L1 gets a via in
# the pad (filled and capped, as C47.1 / C58.1 / R33.2 / C66.1 of D-112 i / D-114 d) and joins the net's L4 copper
VIA_IN_PAD = {("FB2", "2"), ("TP18", "1"), ("TP24", "1")}   # TP18: the VCC_1V8 L1 run walls it in at its D-115 spot


def via_in_pad_join(net, root, comp):
    pads = [p for p in comp["pads"] if p in VIA_IN_PAD]
    if not pads:
        return False
    q = R.PADS[pads[0]]
    if not S.check_via(net, q["x"], q["y"], own_pad_ok=True, novia=R.GRID_NOVIA):
        log("  FAIL %s: via in pad %s.%s not legal" % (net, pads[0][0], pads[0][1]))
        return False
    n_items, n_holes = len(S.items), len(S.holes)
    before = json.loads(json.dumps(R.ROUTES.get(net))) if net in R.ROUTES else None
    R.add_via(net, q["x"], q["y"])
    src = [t for t in terminals(root, net, tee=True) if t.get("L") == L.B or t["kind"] == "point" and t.get("L") == L.B]
    src.sort(key=lambda t: math.hypot(t["x"] - q["x"], t["y"] - q["y"]))
    for t in src[:NCAND]:
        if R.route_net(net, [R.pt(q["x"], q["y"], L.B), t], layers=L.B, w=widths_of(net)[0], margin=2.0):
            log("  join %s: via in pad %s.%s -> %s on L4" % (net, pads[0][0], pads[0][1], R.term_name(t)))
            tag = ["%s.%s" % p for p in comp["pads"]]
            R.FAILS[:] = [f for f in R.FAILS if not (f[0] == net and list(f[1]) == tag)]
            return True
    del S.items[n_items:]
    del S.holes[n_holes:]
    S._arr = None
    if before is None:
        R.ROUTES.pop(net, None)
    else:
        R.ROUTES[net] = before
    return False


def report(nets=None):
    for net in nets or PRIORITY:
        root, rest = pieces(net)
        log("  priority %s: %d piece(s) left%s" % (net, len(rest), (": " + "; ".join(
            ",".join("%s.%s" % p for p in c["pads"]) or str(c["vias"]) for c in rest)) if rest else ""))


def main():
    R.setup_novia()
    R.setup_sw_areas()
    R.ROUTES.clear()
    run()
    report()
    R.selfcheck()
    json.dump({"routes": R.ROUTES, "log": R.LOG, "fails": R.FAILS}, open(OUT, "w"), indent=0, sort_keys=True)
    log("L5 priority: %d nets routed, fails %s" % (len(R.ROUTES), R.FAILS))


DONE_FAIL = set()

if __name__ == "__main__":
    main()
