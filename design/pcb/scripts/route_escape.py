#!/usr/bin/env python3
"""Layout phase L3, step 2: U9 (RV1106 QFN-128) fan-out of every pad with a net (escape_plan.csv, D-104; D-109).

    $PY design/pcb/scripts/route_escape.py            # after place.py; calls escape_solve.py with design/.venv

Per pin role (escape_plan.csv):
  LANE  - L1 stub from the pad to its gate point (t_planned, r = 8.00 mm from the U9 centre), where the trial route of
          D-107/D-108 starts; diff pairs (26/27, 97/98, 99/100) as two lines centred on the planned pair lane, line
          pitch at the gate = width + diff gap of the class;
  PART  - L1 link from the pad to the facing pad of its ring-1 part (the part pad on the pin's net);
  GND   - pins 37/57 (VIA role in the plan) tie inward on L1 straight to the EP (GND, 16 vias to L2), D-109 (b);
  VIA   - D-109 (a): L1 stub inward to a via under the package between the pad inner ends (5.70 mm) and the EP
          (3.50 mm), not on the outer via ring of the plan (the ring cannot hold the vias at the board's real hole
          clearances, see decisions.md): VDD_0V9
          pins 51/82/116 to the L3 island (and every VDD_0V9 pin with a ring-1 cap gets an inner via too), the DEFAULT/SENSE/sub-rail pins of D-104 (b)(e) to L4 later;
  EP 129 - its 16 thermal vias are pads of the footprint (D-85); this script sets the EP and those via pads to a solid
          zone connection (layout.md §6.2 "connect solidly (no thermal relief)").
Geometry: radial along the pad to r 6.50, then per side the polylines of escape_solve.py (one LP: order kept, <= 45 deg,
clearances of the DRU neck-down rule with the 45 deg correction, board hole clearance 0.25 mm to via holes).
Widths: 0.10 mm lanes, 0.12 mm supply/GND links, 0.15 mm diff-pair lines (0.35 mm pin pitch: a 0.235/0.255 mm line
would leave < 0.10 mm to the neighbour pad; the pairs reach class width from the gate on, in L4).
Everything this script adds is in the board group "L3_ESCAPE" (rebuild_all.sh reruns all steps).
"""
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

R_GATE = 8.00
EP_HALF = 3.50          # EP 7.0 x 7.0 mm (D-85)
INNER_EXTRA = {28: "VCC_3V3 pin 28: its cap C65 is boxed in by the USB pair and C70 (no via site); the inner via"
                    " reaches VCC_3V3 S-SOC by an L3 finger under the island (D-109 a)"}
# D-110: every VCC_3V3 pin with a ring-1 cap gets an inner via under the package, joined to a VCC_3V3 L3 region by a
# straight 0.80 mm L3 finger cut into the VDD_0V9 island ("dir": the side of the island the finger leaves by). The
# ring-1 cap pads C64.1/C63.1/C61.1/C62.1/C67.1/C68.1 then need no plane via of their own in the D-104 lane channels
# (verifier L3 r1/r2 blocker). The fingers are written to design/pcb/escape_fingers.json for planes.py and are a
# hard keep-out for every later via of another net (route_planevias.py).
FINGER_PINS = {13: "S", 28: "S", 43: "E", 81: "N", 88: "N", 108: "W"}
# pin 61 (NE corner): no finger fits between the USB_SEL / PB_INT_N / SDMMC_PWREN vias, so its inner via is joined to
# the VCC_3V3 plane by an L4 link (route_powerlinks.py, start "U9.61")
L4LINK_PINS = {61: "VCC_3V3 pin 61: inner via, L4 link to a VCC_3V3 plane via (route_powerlinks.py, D-110)"}
FINGER_W = 0.80
FINGER_TO = {"S": 45.3 + 0.6, "N": 27.7 - 0.6, "W": 25.7 - 0.6, "E": 43.3 + 0.6}   # into S-SOC / N-SOC / W-COL / NAND-S
FINGER_CLEAR = 0.30 + 0.25 + 0.02        # finger edge to another net's via centre: L3 gap + via radius + margin
SECOND_VIA = {19: "VCC3V3_RTC (PWR_SUB)", 56: "VCC_DDR (PWR_DDR)"}     # layout.md §3: >= 2 vias per layer change
for _p in FINGER_PINS:
    INNER_EXTRA.setdefault(_p, "VCC_3V3 pin %d: inner via + L3 finger (D-110)" % _p)
INNER_EXTRA.update(L4LINK_PINS)
FINGERS_JSON = os.path.join(bl.PCB_DIR, "escape_fingers.json")
# D-110: hand-set inner via sites of the crowded NE corner (pins 59/60/61 adjacent on the E side, 65 on the N side),
# staggered in two columns so that all four fit; tried first, then the normal search. Board mm.
PREFER = {61: (39.70, 31.90), 59: (39.70, 32.95), 60: (38.85, 32.45), 65: (39.15, 31.25)}


def finger_rect(vx, vy, d):
    h = FINGER_W / 2
    if d == "S":
        return (vx - h, vy - h, vx + h, FINGER_TO["S"])
    if d == "N":
        return (vx - h, FINGER_TO["N"], vx + h, vy + h)
    if d == "W":
        return (FINGER_TO["W"], vy - h, vx + h, vy + h)
    return (vx - h, vy - h, FINGER_TO["E"], vy + h)


def rect_pt(r, x, y):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return (dx * dx + dy * dy) ** 0.5
INNER_R = (3.95, 5.20)  # inner via centres: >= EP edge + clearance + via radius, <= pad inner ends - clearance - radius
INNER_EXIT = 5.60       # the inward stub leaves the pad (inner end 5.70) along the pin axis first
W_EPTIE = 0.15          # GND pin -> EP tie under the package (pin pitch 0.35: 0.175 mm to the neighbour pads)
W_LANE, W_SUPPLY, W_PAIR = 0.10, 0.12, 0.15
PAIR_GAP = {"USB_DIFF": 0.15, "ETH_DIFF": 0.20}
VENV_PY = os.path.join(bl.DESIGN, ".venv", "bin", "python")
GEOM_IN = os.path.join(bl.PCB_DIR, "escape_geom_in.json")
GEOM_OUT = os.path.join(bl.PCB_DIR, "escape_geom.json")


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    rl.require_fresh(board, "L3_ESCAPE")
    R = rl.rules()
    u9 = board.FindFootprintByReference("U9")
    pads = {}
    for p in u9.Pads():
        if p.GetNumber() and p.GetNumber() != "129":
            pads[int(p.GetNumber())] = p
        else:
            p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)       # EP + 16 thermal vias solid (§6.2)
    with open(os.path.join(bl.PCB_DIR, "escape_plan.csv"), newline="", encoding="utf-8") as fh:
        plan = {int(r["pin"]): r for r in csv.DictReader(fh)}
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    def tpin(pin):
        return esc.t_of(esc.side_of(pin), *bl.to_board(pads[pin].GetPosition()))

    def width(net):
        cls = R[net][0]
        return W_SUPPLY if cls.startswith("PWR_") or cls == "GND" else W_LANE

    # ---- solver input: items in pin order + fixed ring-1 pads near the gate
    data, meta = {}, {}
    ep_ties = []
    inner = []
    for side in "SENW":
        tc = esc.t_of(side, *esc.CENTRE)
        its, link_pads = [], set()
        for pin in sorted((q for q in plan if plan[q]["side"] == side), key=tpin):
            r = plan[pin]
            role, net = r["role"], r["net"]
            if role in ("NC", "PAIR2") or not net:
                continue
            t0 = tpin(pin)
            if role == "VIA" and net == "GND":
                ep_ties.append((pin, net))       # D-109 (b): GND pins 37/57 tie inward to the EP on L1
                continue
            if role == "VIA":
                inner.append((pin, net))         # D-109 (a): via under the package, between the pad ends and the EP
                continue
            elif role == "LANE" and pin in esc.PAIRS:
                p2 = esc.PAIRS[pin]
                half = (R[net][1] + PAIR_GAP[R[net][0]]) / 2
                tg = float(r["t_planned"])
                lo, hi = (pin, p2) if tpin(pin) < tpin(p2) else (p2, pin)
                for pp, tt in ((lo, tg - half), (hi, tg + half)):
                    its.append(dict(pin=pp, net=plan[pp]["net"], kind="lane", t0=tpin(pp), tg=tt, half=W_PAIR / 2,
                                    w=W_PAIR))
            elif role == "LANE":
                its.append(dict(pin=pin, net=net, kind="lane", t0=t0, tg=float(r["t_planned"]), half=W_LANE / 2,
                                w=W_LANE))
            else:
                if net == "VDD_0V9" or pin in INNER_EXTRA:
                    inner.append((pin, net))     # D-109 (a): every VDD_0V9 pin also straight down to the L3 island
                fp = fps[r["part"]]
                q = min((q for q in fp.Pads() if q.GetNetname() == net),
                        key=lambda q: esc.radial(side, *bl.to_board(q.GetPosition())))
                qx, qy = bl.to_board(q.GetPosition())
                t_lo, t_hi, r_lo, _r_hi = pad_span(q, side)
                link_pads.add((r["part"], q.GetNumber()))
                its.append(dict(pin=pin, net=net, kind="link", t0=t0, tg=(t_lo + t_hi) / 2, half=width(net) / 2,
                                w=width(net), pad_half=(t_hi - t_lo) / 2, r_in=r_lo, pad=(qx, qy),
                                part=r["part"]))
        its.sort(key=lambda it: it["t0"])
        # links of two pins to one pad (C53: 49/50, C49: 54/55) keep their order; give keys
        for k, it in enumerate(its):
            it["key"] = float(k)
        # fixed pads in the gate band that are not a link's own pad
        fixed = []
        for ref, fp in fps.items():
            if ref == "U9":
                continue
            for q in fp.Pads():
                if (ref, q.GetNumber()) in link_pads:
                    continue
                t_lo, t_hi, r_lo, r_hi = pad_span(q, side)
                if r_lo > R_GATE + 0.2 or r_hi < 7.5 or t_hi < tc - 7.6 or t_lo > tc + 7.6:
                    continue
                tm = (t_lo + t_hi) / 2
                ends = [(it["tg"] if it["kind"] != "via" else it["t0"]) for it in its]
                before = [k for k, e in enumerate(ends) if e < tm]
                key = (max(before) + 0.5) if before else -0.5
                fixed.append(dict(key=key, t=tm, half=(t_hi - t_lo) / 2, r_in=r_lo, ref="%s.%s" % (ref, q.GetNumber())))
        data[side] = {"items": [{k: v for k, v in it.items() if k in ("key", "kind", "t0", "tg", "half", "pad_half",
                                                                         "r_in")} for it in its],
                      "pads": fixed}
        meta[side] = its
    with open(GEOM_IN, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    subprocess.run([VENV_PY, "-I", os.path.join(bl.PCB_DIR, "scripts", "escape_solve.py"), GEOM_IN, GEOM_OUT],
                   check=True)
    with open(GEOM_OUT, encoding="utf-8") as fh:
        sol = json.load(fh)

    # ---- draw
    items, log = [], []
    for pin, net in ep_ties:
        side = esc.side_of(pin)
        t0 = tpin(pin)
        # radially to r 5.0 (clear of the neighbours' inner pad ends at 5.70), then straight into the EP, aimed at a
        # point 0.2 mm inside the EP corner when the pin lies beyond the EP's side span (pin 37: t 40.525 > 40.0)
        tc = esc.t_of(side, *esc.CENTRE)
        te = min(max(t0, tc - EP_HALF + 0.3), tc + EP_HALF - 0.3)
        pts = [esc.point(side, t0, esc.PAD_CENTRE), esc.point(side, t0, 5.0), esc.point(side, te, EP_HALF - 0.2)]
        items += rl.add_track(board, net, "F", pts, W_EPTIE)
        log.append((pin, "EP-TIE", net))
    for side in "SENW":
        if not sol[side]["ok"]:
            log.append((0, "SIDE %s SOLVER FAILED: %s" % (side, sol[side]["msg"]), ""))
            continue
        for it, s in zip(meta[side], sol[side]["items"]):
            raw = [tuple(p) for p in s["pts"]]
            # no vertex beyond r 7.85 except the end: the last segment must touch the U9_FAN rule area (DRU neck-down)
            raw = [p for p in raw[:-1] if p[1] <= 7.85 + 1e-9] + [raw[-1]]
            tr = [(it["t0"], esc.PAD_CENTRE)] + raw
            tr = simplify(tr)
            pts = [esc.point(side, t, r) for t, r in tr]
            if it["kind"] == "link":
                pts.append(it["pad"])
            items += rl.add_track(board, it["net"], "F", pts, it["w"])
            if it["kind"] == "via":
                vx, vy = esc.point(side, *s["via"])
                items.append(rl.add_via(board, it["net"], vx, vy))
                log.append((it["pin"], "VIA", it["net"]))
            else:
                log.append((it["pin"], it["kind"].upper(), it["net"]))

    # ---- inner vias (D-109 a): searched after the outer fan is drawn, against the U9 pads, the EP and each other
    sp = rl.board_space(board, R)
    inner_vias = []
    fingers = []            # (pin, net, rect) of the D-110 VCC_3V3 L3 fingers
    seconds = []            # VIA-role pins that get a second via (layout.md §3)

    def finger_bad(vx, vy, net, pin):
        """A via of another net must keep FINGER_CLEAR from every finger; a finger pin's own finger must keep it from
        every via of another net already placed."""
        if any(fn != net and rect_pt(fr, vx, vy) < FINGER_CLEAR for _fp, fn, fr in fingers):
            return True
        if pin in FINGER_PINS:
            fr = finger_rect(vx, vy, FINGER_PINS[pin])
            for c in sp.items:
                if c.kind == "circle" and c.tag == "via" and c.net != net and rect_pt(fr, *c.a) < FINGER_CLEAR:
                    return True
                if c.kind == "poly" and c.tag.startswith("U9.129") and c.net != net:
                    if any(rect_pt(fr, *q) < 0.30 for q in c.pts):
                        return True
        return False

    order = lambda q: (-1 if q[0] in PREFER else 0 if q[0] in FINGER_PINS else 1 if plan[q[0]]["role"] == "VIA"  # noqa: E731
                       else 2, q[0])
    for pin, net in sorted(inner, key=order):
        side = esc.side_of(pin)
        t0 = tpin(pin)
        w = width(net)
        best = None
        # a supply pin with a part may share a same-net inner via already placed (<= 1.3 mm away)
        if plan[pin]["role"] != "VIA" and pin not in FINGER_PINS:
            for (vx, vy, vn) in sorted(inner_vias, key=lambda v: (v[0] - esc.point(side, t0, 5.0)[0]) ** 2
                                       + (v[1] - esc.point(side, t0, 5.0)[1]) ** 2):
                ex = esc.point(side, t0, INNER_EXIT)
                if vn != net or ((vx - ex[0]) ** 2 + (vy - ex[1]) ** 2) ** 0.5 > 2.0:
                    continue
                sg = rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=ex, b=(vx, vy), r=w / 2, fan=True)
                if not (sp.conflicts(sg, extra=0.02) + rl.hole_hits(sp, sg)):
                    best = (0, vx, vy, [esc.point(side, t0, esc.PAD_CENTRE), ex, (vx, vy)], True)
                    break
        trials = []
        if pin in PREFER and not best:
            px, py = PREFER[pin]
            trials.append((esc.radial(side, px, py), esc.t_of(side, px, py) - t0, -1.0))
        for rv10 in ([] if best else range(int(INNER_R[1] * 100), int(INNER_R[0] * 100) - 1, -5)):
            for k in range(0, 81):
                trials.append((rv10 / 100.0, (k + 1) // 2 * 0.025 * (1 if k % 2 else -1), None))
        for rv, dt, fixed_cost in trials:
            if True:
                tv = t0 + dt
                vx, vy = esc.point(side, tv, rv)
                pts = [esc.point(side, t0, esc.PAD_CENTRE), esc.point(side, t0, INNER_EXIT), (vx, vy)]
                vs = rl.Shape("circle", rl.LAYERS, net, rl.class_clear(net, R), "via", a=(vx, vy), r=rl.VIA_D / 2)
                bad = sp.conflicts(vs, extra=0.02)
                hole = rl.Shape("circle", rl.LAYERS, net, rl.HOLE_CLEAR, "hole", a=(vx, vy), r=0.15)
                bad += [c for c in sp.conflicts(hole, extra=0.02) if c[0].kind in ("seg", "poly")]
                bad += [1 for c in sp.near(vs, 1.0) if c.kind == "circle" and c.tag == "via"
                        and ((c.a[0] - vx) ** 2 + (c.a[1] - vy) ** 2) ** 0.5 < rl.HOLE_PITCH + 0.02]
                for a, b in zip(pts[1:-1], pts[2:]):
                    sg = rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=a, b=b, r=w / 2, fan=True)
                    bad += sp.conflicts(sg, extra=0.02) + rl.hole_hits(sp, sg)
                if not bad and finger_bad(vx, vy, net, pin):
                    bad = [1]
                if not bad:
                    cost = fixed_cost if fixed_cost is not None else abs(dt) + 0.3 * (INNER_R[1] - rv)
                    if best is None or cost < best[0]:
                        best = (cost, vx, vy, pts, False)
        if best is None:
            if plan[pin]["role"] == "VIA":
                log.append((pin, "INNER VIA FAILED pin %d %s" % (pin, net), net))
            else:   # extra plane via of a supply pin that already reaches its ring-1 cap (and the cap's plane via)
                log.append((pin, "INNER VIA SKIPPED pin %d %s (no room; the pin reaches the plane through %s)"
                            % (pin, net, plan[pin]["part"]), net))
            continue
        _, vx, vy, pts, shared = best
        new = rl.add_track(board, net, "F", pts, w)
        items += new
        if not shared:
            items.append(rl.add_via(board, net, vx, vy))
            inner_vias.append((vx, vy, net))
        for a, b in zip(pts[:-1], pts[1:]):
            sp.add(rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=a, b=b, r=w / 2, fan=True))
        sp.add(rl.Shape("circle", rl.LAYERS, net, rl.class_clear(net, R), "via", a=(vx, vy), r=rl.VIA_D / 2))
        log.append((pin, "INNER-VIA" + (" (shared)" if shared else ""), net))
        if pin in FINGER_PINS:
            fingers.append((pin, net, finger_rect(vx, vy, FINGER_PINS[pin])))
        if pin in SECOND_VIA:
            seconds.append((pin, net, vx, vy, side))
    for pin, net, vx, vy, side in seconds:        # after every inner via: the second vias take what room is left
        if True:
            sec = second_via(sp, R, net, vx, vy, side, finger_bad, pin)
            if sec is None:
                log.append((pin, "SECOND VIA SKIPPED pin %d %s (no room)" % (pin, net), net))
            else:
                (sx, sy), sw = sec
                items += rl.add_track(board, net, "F", [(vx, vy), (sx, sy)], sw)
                items.append(rl.add_via(board, net, sx, sy))
                sp.add(rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=(vx, vy), b=(sx, sy), r=sw / 2,
                                fan=True))
                sp.add(rl.Shape("circle", rl.LAYERS, net, rl.class_clear(net, R), "via", a=(sx, sy), r=rl.VIA_D / 2))
                log.append((pin, "SECOND-VIA (%.2f, %.2f)" % (sx, sy), net))

    rl.group(board, "L3_ESCAPE", items)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    with open(FINGERS_JSON, "w", encoding="utf-8") as fh:
        json.dump([dict(pin=p_, net=n_, dir=FINGER_PINS[p_], width=FINGER_W, rect=[round(v, 3) for v in r_])
                   for p_, n_, r_ in fingers], fh, indent=1)
    for p_ in FINGER_PINS:
        if p_ not in [f[0] for f in fingers]:
            log.append((p_, "FINGER VIA FAILED pin %d" % p_, "VCC_3V3"))
    fails = [x for x in log if "FAILED" in x[1]]
    print("U9 escape: %d pins handled, %d tracks/vias added, %d failures" % (len(log), len(items), len(fails)))
    for f in fails:
        print("  " + f[1])
    for x in log:
        if "SKIPPED" in x[1]:
            print("  " + x[1])
    if fails:
        sys.exit(1)


def second_via(sp, R, net, vx, vy, side, finger_bad, pin):
    """Second via of a PWR_DDR/PWR_SUB VIA-role pin (layout.md §3: >= 2 vias per layer change): a spot 0.77-1.30 mm
    from the first via, in the inner band (r 3.95-5.20), clear of everything; joined by an L1 track (0.20, else 0.12)."""
    import math
    best = None
    for k in range(72):
        a = 2 * math.pi * k / 72
        for d in (0.78, 0.85, 0.95, 1.1, 1.3):
            sx, sy = vx + d * math.cos(a), vy + d * math.sin(a)
            r = esc.radial(side, sx, sy)
            if not (INNER_R[0] <= r <= INNER_R[1]):
                continue
            # stay within the side's own sector (not under another side's inner vias' stubs)
            tc = esc.t_of(side, *esc.CENTRE)
            if abs(esc.t_of(side, sx, sy) - tc) > r:
                continue
            vs = rl.Shape("circle", rl.LAYERS, net, rl.class_clear(net, R), "via", a=(sx, sy), r=rl.VIA_D / 2)
            bad = sp.conflicts(vs, extra=0.02)
            hole = rl.Shape("circle", rl.LAYERS, net, rl.HOLE_CLEAR, "hole", a=(sx, sy), r=0.15)
            bad += [c for c in sp.conflicts(hole, extra=0.02) if c[0].kind in ("seg", "poly")]
            bad += [1 for c in sp.near(vs, 1.0) if c.kind == "circle" and c.tag == "via"
                    and ((c.a[0] - sx) ** 2 + (c.a[1] - sy) ** 2) ** 0.5 < rl.HOLE_PITCH + 0.02]
            if bad or finger_bad(sx, sy, net, pin):
                continue
            for w in (0.20, 0.12):
                sg = rl.Shape("seg", ["F"], net, rl.class_clear(net, R), "track", a=(vx, vy), b=(sx, sy), r=w / 2,
                              fan=True)
                if not (sp.conflicts(sg, extra=0.02) + rl.hole_hits(sp, sg)):
                    cost = d + (0.5 if w < 0.2 else 0)
                    if best is None or cost < best[0]:
                        best = (cost, (sx, sy), w)
                    break
    return None if best is None else (best[1], best[2])


def pad_span(p, side):
    pts = bl.pad_polygon(p)
    ts = [esc.t_of(side, x, y) for x, y in pts]
    rs = [esc.radial(side, x, y) for x, y in pts]
    return min(ts), max(ts), min(rs), max(rs)


def simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) < 1e-6 and abs(p[1] - out[-1][1]) < 1e-6:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            cr = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            if abs(cr) < 1e-7:
                out[-1] = p
                continue
        out.append(p)
    return out


if __name__ == "__main__":
    main()
