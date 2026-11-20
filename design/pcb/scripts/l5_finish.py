#!/usr/bin/env python3
"""Layout phase L5, round 4 (D-116): route the nets the L5 rounds 1-3 left open, by hand-placed polylines (every piece
exact-checked against the board with l4lib) and the L4/L5 router (l4_route.route_net) for the long legs.

    design/.venv/bin/python -I design/pcb/scripts/l5_finish.py
      in : design/pcb/l5/board_geo_prefinish.json (l4_export.py after l5_prune.py, with board groups)
      out: design/pcb/l5/finish.json  {"rip_tracks", "rip_vias", "moves", "routes", "fails", "log"}
           (applied to the board by l5_finish_write.py, group L5_FINISH)

What it does (verifier L5 round 3 findings; D-116 a-h):
  a. SENSE re-route (L4): RECOVERY / SARADC_IN1 leave their south escape vias up the corridor west of the U9 inner
     vias, run east under the north pad row and turn north beside the VCC_1V8 rail to their end vias; they no longer
     enclose the inner vias of USB_SEL / PB_INT_N / SDMMC_PWREN.
  b. VCC_3V3 pin-61 inner via: its L3 L4 link to the plane via north of the SoC is replaced by an L4 link to the
     pin-43 inner via (39.70, 38.43) (both are U9 VCC_3V3 pins; pin 43 reaches the plane through C63).
  c. The three inner nets leave the U9 field on L4 through the south-east corridor; USB_SEL and SDMMC_PWREN run south
     beside the VCC_1V8 rail (east of FB2) and west along y 52.8-53.1 (south of the codec loop), PB_INT_N hops to L1
     at (42.20, 41.15) and is routed by the router.
  d. Codec rail (VCC1V8_CODEC): the L5 L4 loop is rebuilt inside the new nets (C57 via -> south loop -> FB2.2 via ->
     C41 via north of C41.1); TP24 and TP18 are moved next to the loop / their rail (local moves) and joined by a via
     beside the pad (TP18 loses its via-in-pad).
  e. C84.1 (U11 decoupling) VCC_3V3 plane via moves from (36.41, 54.35) onto the C84-U11.10 link at (37.13, 55.00) so
     that USB_SEL reaches U11.9 on L1 south of the RTC crystal guard.
  f. East lanes of U9 (pins 64/63/62): USBA_VBUS_EN, PWR_KILL, LED_STATUS re-planned in the NPOR / PWR_KILL channel on
     L1 (0.10 mm); LED_STATUS reaches LED2 on L1/L4 north, USBA_VBUS_EN drops to L4 north of the neck.
  g. HDR_GPIO2_A7 / A6 west lanes: A6's L1 route is re-routed after A7 (A7 first takes the path north of A6).
  h. I2C3 pull-ups R62 / R63 move north-west of U9 next to the I2C3 lanes (rotated 180 deg), VCC_3V3 vias north.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
L5 = os.path.join(PCB, "l5")
SRC = os.path.join(L5, "board_geo_prefinish.json")
TMP = os.path.join(L5, "board_geo_finish_in.json")
OUT = os.path.join(L5, "finish.json")

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def _box(t, x0, y0, x1, y1):
    return x0 <= min(t["a"][0], t["b"][0]) and max(t["a"][0], t["b"][0]) <= x1 and \
        y0 <= min(t["a"][1], t["b"][1]) and max(t["a"][1], t["b"][1]) <= y1


def _seg(t, a, b, tol=0.005):
    def eq(p, q):
        return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol
    return (eq(t["a"], a) and eq(t["b"], b)) or (eq(t["a"], b) and eq(t["b"], a))


# NPOR near-duplicate pair at C71.1 (verifier round-3 minor soc): the 0.15 mm piece to (42.482, 29.153) and its
# continuation (42.482, 29.153)-(43.108, 29.153) lie 9 um beside the main run; the R43.2 branch keeps its start on it
NPOR_RIP = [("NPOR", (41.82, 28.29), (42.482, 29.153)), ("NPOR", (42.482, 29.153), (43.108, 29.153)),
            # VDD_ARM C38 branch (round 3): its L4 diagonal started 73 um off the via (joined by overlap only) with a
            # 4 um stub; replaced by a run that starts at the via centre (below, L4_PL)
            ("VDD_ARM", (22.723, 40.918), (21.138, 39.332)), ("VDD_ARM", (22.723, 40.922), (22.723, 40.918))]
# lane pieces replaced by the east-lane plan (f)
EAST_RIP = [("USBA_VBUS_EN", (42.1, 30.387), (42.35, 30.236)), ("USBA_VBUS_EN", (42.35, 30.236), (42.5, 30.145)),
            ("PWR_KILL", (42.25, 30.553), (42.35, 30.51)), ("PWR_KILL", (42.35, 30.51), (42.5, 30.445)),
            ("LED_STATUS", (42.35, 30.772), (42.5, 30.745))]


def rip_track(t):
    g, n = t.get("group", ""), t["net"]
    if n in ("RECOVERY", "SARADC_IN1") and t["layer"] == "B" and g == "L4_CRITICAL":            # (a)
        return True
    if n == "VCC_3V3" and t["layer"] == "B" and g == "L3_POWERLINKS" and _box(t, 39, 27, 42.8, 32.1):   # (b)
        return True
    if n == "VCC_3V3" and g == "L3_PLANEVIAS" and _seg(t, (36.481, 54.781), (36.406, 54.352), 0.01):   # (e)
        return True
    if g == "L5_PRIORITY" and n == "VCC1V8_CODEC" and t["layer"] == "B":                           # (d)
        return True
    if g == "L5_PRIORITY" and n == "VCC1V8_CODEC" and t["layer"] == "F" and _box(t, 46.5, 44.5, 47.5, 45.4):
        return True
    if g == "L5_PRIORITY" and n == "VCC3V3_RTC":                                                      # (d) TP18
        return True
    if n == "PWR_KILL" and g == "L5_LANES" and t["layer"] == "F" and max(t["a"][1], t["b"][1]) < 31 and \
            min(t["a"][0], t["b"][0]) >= 42.3:                                                        # (f)
        return True
    if any(t["net"] == en and _seg(t, a, b) for en, a, b in EAST_RIP + NPOR_RIP):
        return True
    if n == "HDR_GPIO2_A6" and g == "L5_LANES" and abs(t["a"][0] - 26.625) > 0.01:                  # (g)
        return True
    if n == "VCC_3V3" and g == "L3_PLANEVIAS" and 9 < t["a"][0] < 11.5 and 35.5 < t["a"][1] < 36.5:   # (h)
        return True
    return False


def rip_via(v):
    g, n = v.get("group", ""), v["net"]
    if n == "VCC_3V3" and abs(v["x"] - 36.406) < 0.01 and abs(v["y"] - 54.352) < 0.01:
        return True
    if g == "L5_PRIORITY" and n == "VCC1V8_CODEC" and abs(v["x"] - 47.377) < 0.01:
        return True
    if g == "L5_PRIORITY" and n == "VCC3V3_RTC":
        return True
    if n == "VCC_3V3" and g == "L3_PLANEVIAS" and 9 < v["x"] < 11.5 and 35.5 < v["y"] < 36.5:
        return True
    return False


# local part moves (centre x, y, turned 180 deg) - D-116 d, h; owner approval items at CHECKPOINT 2
MOVES = {"TP18": (46.60, 52.30, False), "TP24": (43.85, 52.30, False),
         "R62": (30.60, 12.60, True), "R63": (29.60, 12.60, True)}

SENSE_PL = {
    "SARADC_IN1": [(36.425, 41.65), (37.3, 40.775), (37.3, 35.0), (36.85, 34.55), (36.85, 30.6), (37.75, 29.7),
                   (43.6, 29.7), (43.6, 26.907), (44.312, 26.195)],
    "RECOVERY": [(37.2, 41.65), (37.65, 41.2), (37.65, 34.78), (37.25, 34.38), (37.25, 31.0), (38.15, 30.1),
                 (44.05, 30.1), (44.05, 28.3), (44.91, 27.44), (44.91, 25.19)],
}
INNER_PL = {
    "USB_SEL": ([(39.15, 31.35), (37.925, 32.575), (37.925, 37.625), (41.5, 41.2), (42.9, 42.6), (47.58, 42.6),
                 (47.58, 52.85), (37.95, 52.85), (37.85, 52.75), (34.0, 52.75), (34.0, 55.6)], 0.10),
    "PB_INT_N": ([(38.85, 32.45), (38.175, 33.125), (38.175, 37.555), (41.5, 40.88), (41.95, 40.88), (42.2, 41.13),
                  (42.2, 41.15)], 0.10),
    "VCC_3V3": ([(39.7, 31.9), (39.7, 32.275), (38.525, 33.45), (38.525, 37.25), (39.7, 38.425)], 0.15),
    "SDMMC_PWREN": ([(39.7, 32.95), (38.875, 33.775), (38.875, 36.4), (41.5, 39.025), (44.725, 42.25),
                     (47.835, 42.25), (47.835, 53.11), (38.09, 53.11), (34.99, 56.21)], 0.10),
}
L1_PL = [   # (net, points, width)
    ("USB_SEL", [(37.85, 54.40), (34.5, 54.40), (34.5, 56.0), (34.8, 56.3), (35.59, 56.3)], 0.15),
    ("USB_SEL", [(34.5, 55.1), (34.0, 55.6)], 0.15),
    ("VCC1V8_CODEC", [(46.9, 44.4), (46.625, 44.675), (46.625, 45.3)], 0.30),
    ("VCC3V3_RTC", [(46.3, 51.1), (46.6, 51.4), (46.6, 51.7)], 0.30),
    ("VCC1V8_CODEC", [(43.85, 51.1), (43.85, 51.7)], 0.30),
    ("USBA_VBUS_EN", [(42.1, 30.387), (42.947, 29.54), (47.31, 29.54), (49.5, 27.35)], 0.10),
    ("PWR_KILL", [(42.25, 30.553), (43.008, 29.795), (47.755, 29.795), (50.067, 27.483), (57.838, 27.483)], 0.10),
    ("LED_STATUS", [(42.35, 30.772), (43.072, 30.05), (47.87, 30.05), (49.97, 27.95), (58.7, 27.95)], 0.10),
    ("VCC_3V3", [(29.6, 11.4), (29.6, 12.09)], 0.50),
    ("VCC_3V3", [(30.6, 11.4), (30.6, 12.09)], 0.50),
]
L4_PL = [
    ("VCC1V8_CODEC", [(40.427, 48.547), (40.078, 48.547), (39.577, 49.047), (39.577, 49.547), (41.77, 51.74),
                      (47.15, 51.74), (47.15, 47.251), (47.076, 47.177)], 0.30),
    ("VCC1V8_CODEC", [(47.076, 47.177), (46.95, 47.05), (46.95, 44.45), (46.9, 44.4)], 0.30),
    ("VCC1V8_CODEC", [(43.85, 51.1), (43.85, 51.74)], 0.30),
    ("VCC3V3_RTC", [(45.582, 48.888), (45.582, 50.8), (45.882, 51.1), (46.3, 51.1)], 0.30),
    ("VDD_ARM", [(22.688, 40.982), (22.688, 40.882), (21.138, 39.332)], 0.50),
]
VIAS = [("VCC_3V3", 37.13, 55.0), ("USB_SEL", 34.0, 55.6), ("PB_INT_N", 42.2, 41.15),
        ("VCC1V8_CODEC", 46.9, 44.4), ("VCC1V8_CODEC", 43.85, 51.1), ("VCC3V3_RTC", 46.3, 51.1),
        ("USBA_VBUS_EN", 49.5, 27.35), ("VCC_3V3", 29.6, 11.4), ("VCC_3V3", 30.6, 11.4)]


def main():
    geo = json.load(open(SRC))
    nt, nv = len(geo["tracks"]), len(geo["vias"])
    rip_t = [t for t in geo["tracks"] if rip_track(t)]
    rip_v = [v for v in geo["vias"] if rip_via(v)]
    geo["tracks"] = [t for t in geo["tracks"] if not rip_track(t)]
    geo["vias"] = [v for v in geo["vias"] if not rip_via(v)]
    log("== rip: %d of %d tracks, %d of %d vias" % (len(rip_t), nt, len(rip_v), nv))
    for p in geo["pads"]:
        if p["ref"] in MOVES:
            nx, ny, rot = MOVES[p["ref"]]
            c = geo["court"][p["ref"]]
            cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
            if rot:
                p["poly"] = [[2 * cx - q[0], 2 * cy - q[1]] for q in p["poly"]]
                p["x"], p["y"] = 2 * cx - p["x"], 2 * cy - p["y"]
            dx, dy = nx - cx, ny - cy
            p["x"] += dx
            p["y"] += dy
            p["poly"] = [[q[0] + dx, q[1] + dy] for q in p["poly"]]
    for r, (nx, ny, rot) in MOVES.items():
        c = geo["court"][r]
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        geo["court"][r] = [c[0] + nx - cx, c[1] + ny - cy, c[2] + nx - cx, c[3] + ny - cy]
    json.dump(geo, open(TMP, "w"))
    sys.argv = [sys.argv[0], TMP, os.path.join(L5, "_unused_finish_routes.json")]
    sys.path.insert(0, HERE)
    import l4_route as R  # noqa: E402
    import l4lib as L  # noqa: E402
    import l5lib  # noqa: E402
    L.VIA_ETH = True
    L.VIA_USB_STRICT = True
    R.setup_novia()
    R.setup_sw_areas()
    R.GRID_NOVIA.extend([(42.95 - 0.56, 28.05 - 0.56, 63.5 + 0.56, 30.75 + 0.56),
                         (60.5 - 0.56, 28.05 - 0.56, 63.5 + 0.56, 35.5 + 0.56)])
    F, B = L.F, L.B
    nbad = [0]

    def poly(net, pts, w, lay):
        for a, b in zip(pts, pts[1:]):
            v = R.S.check_seg(net, F if lay == "F" else B, a, b, w / 2, report=True)
            if v:
                nbad[0] += 1
                log("  VIOLATION %s %s %s-%s %s" % (net, lay, a, b, v[:3]))
        R.add_route(net, lay, pts, w)

    def via(net, x, y):
        if not R.S.check_via(net, x, y, self_ok=True, own_pad_ok=True):
            nbad[0] += 1
            log("  VIOLATION via %s (%.3f, %.3f)" % (net, x, y))
        R.add_via(net, x, y)

    def rt(net, terms, m=6.0, vc=2.0, w=0.15, layers=None):
        ok = l5lib.route_checked(R, R.S, net, terms, vc, layers=layers or (F | B), via_ok=True, margin=m, w=w)
        log("  route %s: %s" % (net, "ok" if ok else "FAIL %s" % (R.FAILS[-1:],)))
        return ok

    log("== hand-placed copper (a-f, h)")
    for n, pl in SENSE_PL.items():
        poly(n, pl, 0.15, "B")
    for n, (pl, w) in INNER_PL.items():
        poly(n, pl, w, "B")
    for n, pl, w in L1_PL:
        poly(n, pl, w, "F")
    for n, pl, w in L4_PL:
        poly(n, pl, w, "B")
    for n, x, y in VIAS:
        via(n, x, y)
    log("== router legs")
    rt("PB_INT_N", [R.pt(42.2, 41.15, F), R.P("R10", "2")], m=8)
    rt("SDMMC_PWREN", [R.pt(34.99, 56.21, B), R.P("R38", "2")], m=4)
    # the neck box takes one USBA_VBUS_EN via outside the free strips (D-116 f; check_routing NECK inventory)
    R.GRID_NOVIA[:] = [r for r in R.GRID_NOVIA if not (abs(r[0] - 42.95) < 0.01 and abs(r[1] - 28.05) < 0.01
                                                        and r[2] >= 64)]
    rt("USBA_VBUS_EN", [R.pt(49.5, 27.35, B), R.P("R61", "1")], m=6)
    rt("LED_STATUS", [R.pt(58.7, 27.95, F), R.P("LED2", "1")], m=4)
    rt("HDR_GPIO2_A7", [R.pt(26.5, 35.29, F), R.P("J5", "7")], m=6, vc=1.0, w=0.10)
    rt("HDR_GPIO2_A6", [R.pt(25.3, 35.59, F), R.P("J5", "11")], m=6, vc=1.0, w=0.10)
    rt("HDR_I2C3_SDA", [R.P("R63", "2"), R.pt(26.45, 13.1, F)], m=2, w=0.15, layers=F)
    rt("HDR_I2C3_SCL", [R.P("R62", "2"), R.pt(29.062, 15.028, F)], m=2, w=0.15, layers=F)
    routes = json.loads(json.dumps(R.ROUTES))
    l5lib.polish(routes, R.S)
    log("== finish: %d hand-copper violations, router fails %s" % (nbad[0], R.FAILS))
    json.dump({"rip_tracks": [[t["net"], t["layer"], t["a"], t["b"]] for t in rip_t],
               "rip_vias": [[v["net"], v["x"], v["y"]] for v in rip_v],
               "moves": {k: list(v) for k, v in MOVES.items()},
               "routes": routes, "fails": R.FAILS, "violations": nbad[0], "log": LOG},
              open(OUT, "w"), indent=0, sort_keys=True)
    if nbad[0] or R.FAILS:
        sys.exit(1)


if __name__ == "__main__":
    main()
