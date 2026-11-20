#!/usr/bin/env python3
"""Layout phase L5F step 2 (design/.venv; owner decision D-H6, D-117): the new copper of the buck cells, the enable
nets and the V-cut lane ends, every hand-placed piece exact-checked with l4lib, the long legs by the L4/L5 router.

    design/.venv/bin/python -I design/pcb/scripts/l5f_route.py
      in : design/pcb/l5f/geo_prep.json (l4_export.py after l5f_prep.py)
      out: design/pcb/l5f/route.json  {"routes", "fails", "violations", "log"} (written by l5_write.py, group L5F_ROUTE)

Buck cell template (IC centre (xc, yc); pins 1 EN NW, 2 GND W, 3 SW SW, 4 VIN SE, 5 FB NE; D-117 a):
  * GND strap on L1, 0.50 mm, from pin 2 east under the body between pins 5 and 4 to the GND pad of the 100 nF input
    cap (east slot, GND pad at the strap height), and 0.40 mm south from the body centre between pins 3 and 4 to the
    GND pad of the 10 uF input cap (south slot, turned 180 deg: GND pad west);
  * a GND via under the body on the strap (xc + 0.05, yc), 0.53 mm from pin 2: with the pin-2 via west of the pin,
    two GND vias within 1 mm of pin 2;
  * VIN: pin 4 -> 10 uF VIN pad straight south (0.60 mm, with a VCC5V0_SYS via on it) and pin 4 -> 100 nF VIN pad
    straight east (0.50 mm, with a second VCC5V0_SYS via between them): pin 4 keeps two plane vias <= 0.5 mm;
  * two GND vias under the 10 uF GND pad;
  * EN: a via under the body north of the strap (xc - 0.05, yc - 0.95), joined to pin 1 by a 0.15 mm stub; the enable
    nets are routed from these vias on L4 / L1 by the router, kept out of the inductor courtyards and >= 1 mm from
    the SW copper (D-H6 item 5).
U4 (the 0.9 V cell) has the same template; its 100 nF (C12) gets plane vias from a small exact-checked search.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
L5F = os.path.join(PCB, "l5f")
SRC = os.path.join(L5F, "geo_prep.json")
OUT = os.path.join(L5F, "route.json")
LOG = []
CELLS = {"U6": (71.15, 17.2, "C9", "C14"), "U7": (71.15, 26.2, "C10", "C15"), "U4": (72.35, 35.2, "C7", "C12"),
         "U5": (71.15, 44.2, "C8", "C13")}


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def main():
    sys.argv = [sys.argv[0], SRC, os.path.join(L5F, "_unused_routes.json")]
    sys.path.insert(0, HERE)
    import l4_route as R  # noqa: E402
    import l4lib as L  # noqa: E402
    import l5lib  # noqa: E402
    L.VIA_ETH = True
    L.VIA_USB_STRICT = True
    R.setup_novia()
    R.setup_sw_areas()
    F, B = L.F, L.B
    nbad = [0]
    smd = [p for p in R.S.pads if not p.get("th")]

    def vip_free(x, y, net):
        """a new via keeps its ring off every SMD pad (centre >= 0.26 mm from the pad outline; drill edge >= 0.11 mm): no new via in pad"""
        for p in smd:
            xs = [q[0] for q in p["poly"]]
            ys = [q[1] for q in p["poly"]]
            if x < min(xs) - 0.6 or x > max(xs) + 0.6 or y < min(ys) - 0.6 or y > max(ys) + 0.6:
                continue
            if L.inside_poly(x, y, p["poly"]) or min(
                    L.pt_seg_v(x, y, p["poly"][i][0], p["poly"][i][1], p["poly"][(i + 1) % len(p["poly"])][0],
                               p["poly"][(i + 1) % len(p["poly"])][1]) for i in range(len(p["poly"]))) < 0.26:
                return False
        return True

    def poly(net, pts, w, lay="F"):
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
        if not vip_free(x, y, net):
            nbad[0] += 1
            log("  VIOLATION via in pad %s (%.3f, %.3f)" % (net, x, y))
        R.add_via(net, x, y)

    log("== buck cells (D-117 a)")
    for u, (xc, yc, c10, c100) in sorted(CELLS.items()):
        x0, x1 = xc - 1.137, xc + 1.137
        e100 = xc + 2.65                                   # 100 nF cap column (GND pad at yc, VIN pad at yc + 0.95)
        poly("GND", [(x0, yc), (e100, yc)], 0.50)          # strap pin 2 -> under the body -> 100 nF GND pad
        via("GND", xc + 0.05, yc)                          # under-body GND via, 0.53 mm from pin 2
        poly("GND", [(xc + 0.05, yc), (xc + 0.05, yc + 2.25)], 0.40)    # down between pins 3 and 4 -> 10 uF GND pad
        if u == "U5":       # U5: the VCC_3V3 run to TP2 passes south of C8 (y 47.9): its GND vias go west of the pad
            poly("GND", [(xc + 0.25, yc + 2.05), (xc - 0.60, yc + 2.05)], 0.30)
            via("GND", xc - 0.60, yc + 2.05)
            poly("GND", [(xc + 0.25, yc + 2.85), (xc - 0.60, yc + 2.85)], 0.30)
            via("GND", xc - 0.60, yc + 2.85)
        else:
            poly("GND", [(xc + 0.05, yc + 2.6), (xc + 0.05, yc + 3.45)], 0.30)
            via("GND", xc + 0.05, yc + 3.45)
            poly("GND", [(xc + 0.80, yc + 2.6), (xc + 0.85, yc + 2.65), (xc + 0.85, yc + 3.45)], 0.30)
            via("GND", xc + 0.85, yc + 3.45)
        poly("VCC5V0_SYS", [(xc + 1.65, yc + 0.95), (xc + 1.65, yc + 1.65), (xc + 1.65, yc + 2.42)], 0.60)
        via("VCC5V0_SYS", xc + 1.65, yc + 1.65)
        poly("VCC5V0_SYS", [(xc + 1.50, yc + 0.95), (xc + 2.07, yc + 0.95), (e100, yc + 0.95)], 0.50)
        via("VCC5V0_SYS", xc + 2.07, yc + 0.95)
        poly(EN[u], [(x0, yc - 0.95), (xc - 0.05, yc - 0.95)], 0.15)
        via(EN[u], xc - 0.05, yc - 0.95)
    # U4's 100 nF (moved into the east slot): its own plane vias (the other cells keep theirs)
    log("== C12 plane vias (search)")
    c12 = {p["num"]: p for p in R.S.pads if p["ref"] == "C12"}
    need = {"2": ("GND", 2), "1": ("VCC5V0_SYS", 1)}
    for num, (net, cnt) in sorted(need.items()):
        p = c12[num]
        got = []
        for r in (0.62, 0.70, 0.80, 0.90):
            for ang in range(0, 360, 45):           # 0/45/90 deg pad links
                import math
                x = p["x"] + r * math.cos(math.radians(ang))
                y = p["y"] + r * math.sin(math.radians(ang))
                if len(got) >= cnt:
                    break
                if any(math.hypot(x - gx, y - gy) < 0.80 for gx, gy in got) or x > 76.0:
                    continue
                if not R.S.check_via(net, x, y, self_ok=True, own_pad_ok=True) or not vip_free(x, y, net):
                    continue
                if R.S.check_seg(net, F, (p["x"], p["y"]), (x, y), 0.15, report=True):
                    continue
                x, y = round(x, 3), round(y, 3)
                poly(net, [(p["x"], p["y"]), (x, y)], 0.30)
                via(net, x, y)
                got.append((x, y))
        log("  C12.%s %s: %d via(s) %s" % (num, net, len(got), got))
        if len(got) < cnt:
            nbad[0] += 1
    # V-cut lanes (D-H6 item 4; round 2, D-118 a): the J5 west corridor between the V-cut (x = 0) and the J5 pads
    # (pad edge x = 2.15) re-drawn so that all copper keeps >= 0.80 mm from x = 0. 0.10 mm lanes, 0.15 mm (DEFAULT
    # class) gaps: lane centres from x 0.8502 (edge 0.8002); layer-change vias from x 1.06 (ring edge 0.81). Between
    # the V-cut and the HDR_GPIO1_B1 via at (1.553, 26.022) two lanes + two gaps fit with 0.0035 mm to spare. Hand-drawn, every piece
    # exact-checked against the board (poly / via):
    #  * HDR_SPI0_MOSI drops to F.Cu at (1.30, 19.90) (was 0.76, 21.44), passes between the HDR_SPI0_CS0 and
    #    HDR_SPI0_SCLK vias and runs at x 1.1015 (was 1.087-1.138) to J5.19;
    #  * HDR_SPI0_SCLK drops to F.Cu at (1.06, 21.40) (was 0.66, 22.22) and runs at x 0.8502 (was 0.663) to J5.23;
    #  * HDR_PWM9 runs on B.Cu at x 0.8502 (was 0.663) and changes to F.Cu at (1.06, 48.93), in the gap between the
    #    J5.31 / J5.33 rows (was a via at 0.66, 53.02 below J5.35), then F.Cu into J5.33;
    #  * the B.Cu neighbours step aside round that via: HDR_PWM11 at x 1.1015 (was 1.087) with a jog to 1.512,
    #    HDR_GPIO1_B0 jogs 1.663 -> 1.764, HDR_GPIO1_B1 jogs 1.928 -> 2.016 (inside the row gap, >= 0.15 mm from the
    #    round J5 pads).
    log("== V-cut lanes (D-118 a)")
    vc = {
        "HDR_SPI0_MOSI": [("B", [(2.237, 18.392), (1.30, 19.329), (1.30, 19.90)], 0.10),
                          ("F", [(1.30, 19.90), (1.30, 20.60), (1.55, 20.85), (1.55, 21.56), (1.1015, 22.0085),
                                 (1.1015, 30.6315), (2.89, 32.42)], 0.10)],
        "HDR_SPI0_SCLK": [("B", [(1.962, 20.921), (1.483, 21.40), (1.06, 21.40)], 0.10),
                          ("F", [(1.06, 21.40), (0.8502, 21.6098), (0.8502, 35.3502), (3.0, 37.5)], 0.10)],
        "HDR_PWM9": [("B", [(2.362, 21.197), (0.8502, 22.7088), (0.8502, 48.7202), (1.06, 48.93)], 0.10),
                     ("F", [(1.06, 48.93), (2.33, 50.20), (3.0, 50.20)], 0.15)],
        "HDR_PWM11": [("B", [(2.263, 23.434), (1.1015, 24.5955), (1.1015, 48.33), (1.512, 48.7405),
                             (1.512, 49.12), (1.1015, 49.5305), (1.1015, 52.3475), (1.188, 52.434)], 0.10),
                      ("F", [(1.188, 52.434), (2.694, 52.434)], 0.15)],
        "HDR_GPIO1_B0": [("B", [(1.663, 26.585), (1.663, 48.50), (1.764, 48.601), (1.764, 49.25), (1.663, 49.351),
                                (1.663, 53.942)], 0.10)],
        "HDR_GPIO1_B1": [("B", [(1.928, 31.248), (1.928, 48.0), (2.016, 48.088), (2.016, 49.45), (1.928, 49.538),
                                (1.928, 50.873)], 0.10)],
    }
    VC_VIAS = (("HDR_SPI0_MOSI", 1.30, 19.90), ("HDR_SPI0_SCLK", 1.06, 21.40), ("HDR_PWM9", 1.06, 48.93),
               ("HDR_PWM11", 1.188, 52.434))
    for net, x, y in VC_VIAS:
        via(net, x, y)
    for net in sorted(vc):
        for lay, pts, w in vc[net]:
            poly(net, pts, w, lay)
    # router legs: enable nets (D-H6 item 5) and the V-cut lane ends (item 4)
    log("== router legs")
    forbid = []
    for ind in ("L1", "L2", "L3", "L4"):
        c = R.S.court[ind]
        forbid += [(F, (c[0] - 0.1, c[1] - 0.1, c[2] + 0.1, c[3] + 0.1)), (B, (c[0] - 0.1, c[1] - 0.1, c[2] + 0.1,
                                                                            c[3] + 0.1))]
    # 1.0 mm around the SW copper itself (IC pin 3, inductor pin 1, the SW tracks): the enable nets keep >= 1 mm
    sw_boxes = []
    for u, ind in (("U4", "L1"), ("U5", "L2"), ("U6", "L3"), ("U7", "L4")):
        for ref, num in ((u, "3"), (ind, "1"), (ind, "2")):
            pp = [q for q in R.S.pads if q["ref"] == ref and q["num"] == num][0]["poly"]
            sw_boxes.append((min(q[0] for q in pp), min(q[1] for q in pp), max(q[0] for q in pp),
                             max(q[1] for q in pp)))
    for k, r in enumerate(list(sw_boxes)):
        d = 0.85 if k % 3 == 0 else 1.0      # IC pin 3: inside the IC courtyard the 1 mm rule does not apply (l5fcheck)
        sw_boxes[k] = (r[0] - d, r[1] - d, r[2] + d, r[3] + d)
    for t in R.geo["tracks"]:      # SW tracks (axis-parallel here): body box + 1.0 mm, round caps as inscribed squares
        if t["net"].endswith("_SW"):
            h = t["w"] / 2 + 1.0
            (ax, ay), (bx, by) = t["a"], t["b"]
            if abs(ay - by) < 1e-6:
                sw_boxes.append((min(ax, bx), ay - h, max(ax, bx), ay + h))
            elif abs(ax - bx) < 1e-6:
                sw_boxes.append((ax - h, min(ay, by), ax + h, max(ay, by)))
            for (cx, cy) in (t["a"], t["b"]):
                q = h * 0.75
                sw_boxes.append((cx - q, cy - q, cx + q, cy + q))
    for r in sw_boxes:
        forbid += [(F, r), (B, r)]

    # no via of the enable nets inside an inductor courtyard (+ 0.30) or within 1 mm of the SW copper; unlike the
    # forbid areas these are not waived next to the nets' own pads
    for ind in ("L1", "L2", "L3", "L4"):
        c = R.S.court[ind]
        R.GRID_NOVIA.append((c[0] - 0.3, c[1] - 0.3, c[2] + 0.3, c[3] + 0.3))
        for num in ("1", "2"):             # inductor pads + 1.0 mm + the via ring
            pp = [q for q in R.S.pads if q["ref"] == ind and q["num"] == num][0]["poly"]
            R.GRID_NOVIA.append((min(q[0] for q in pp) - 1.27, min(q[1] for q in pp) - 1.27,
                                 max(q[0] for q in pp) + 1.27, max(q[1] for q in pp) + 1.27))

    def rt(net, terms, m=4.0, vc=2.0, w=0.15, fb=None):
        ok = l5lib.route_checked(R, R.S, net, terms, vc, layers=F | B, via_ok=True, margin=m, w=w,
                                 forbid=fb if fb is not None else forbid)
        log("  route %s: %s" % (net, "ok" if ok else "FAIL %s" % (R.FAILS[-1:],)))
        return ok

    def ptF(ref, num):
        return R.P(ref, num)

    def cpt(ref, num):        # a point terminal at the pad centre on L1: the forbid areas are not waived around it
        p = [q for q in R.S.pads if q["ref"] == ref and q["num"] == num][0]
        return R.pt(p["x"], p["y"], F)
    # R21.2 / R20.2 (the EN RC resistors south-west of U6 / U7) drop to L4 through a via just south of the pad
    for net, ref in (("U6_EN", "R21"), ("VCC_DDR_1V8_EN", "R20")):
        p = [q for q in R.S.pads if q["ref"] == ref and q["num"] == "2"][0]
        poly(net, [(p["x"], p["y"]), (p["x"], p["y"] + 0.95)], 0.15)
        via(net, p["x"], p["y"] + 0.95)
    rt("PWR_EN", [ptF("R21", "1"), ptF("R24", "2"), ptF("TP14", "1")], m=4)
    rt("U4_EN", [R.pt(72.30, 34.25, B), ptF("R23", "2")])
    rt("U6_EN", [R.pt(71.10, 16.25, B), R.pt(70.41, 20.95, B), cpt("C33", "1")])
    rt("VCC_DDR_1V8_EN", [R.pt(71.10, 25.25, B), R.pt(70.41, 29.95, B), cpt("C20", "1"), R.pt(71.10, 43.25, B)],
       m=6)
    # USB / ETH pair vias (L4 hops): a GND stitching via within 1.0 mm of each (D-H6 item 7)
    log("== hop stitching vias")
    import math
    L.VIA_ETH = False             # a GND via is exempt from the pairs' 30 mil rule (DRU: B.NetClass != 'GND')
    L.VIA_USB_STRICT = False
    PAIRS = ("USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM", "ETH_TX", "ETH_RX")
    gnd = [(v["x"], v["y"]) for v in R.geo["vias"] if v["net"] == "GND"]
    for v in sorted(R.geo["vias"], key=lambda q: (q["net"], q["x"], q["y"])):
        if not v["net"].startswith(PAIRS):
            continue
        if any(math.hypot(v["x"] - gx, v["y"] - gy) <= 1.0 for gx, gy in gnd):
            continue
        done = None
        cur = min(math.hypot(v["x"] - gx, v["y"] - gy) for gx, gy in gnd)
        for i in range(0, 35):                # nearest legal site, 0.75 .. 1.60 mm (the pair's own copper takes the rest)
            r = 0.75 + 0.025 * i
            if r >= cur:
                break
            for ang in range(0, 360, 3):
                x = round(v["x"] + r * math.cos(math.radians(ang)), 3)
                y = round(v["y"] + r * math.sin(math.radians(ang)), 3)
                if R.S.check_via("GND", x, y) and vip_free(x, y, "GND"):
                    done = (x, y)
                    break
            if done:
                break
        if done:
            via("GND", *done)
            gnd.append(done)
            log("  %s via (%.2f, %.2f): GND stitch added at (%.3f, %.3f), %.2f mm (nearest before: %.2f mm)" % (
                v["net"], v["x"], v["y"], done[0], done[1], math.hypot(done[0] - v["x"], done[1] - v["y"]), cur))
        else:
            log("  %s via (%.2f, %.2f): no legal GND site nearer than the existing %.2f mm" % (
                v["net"], v["x"], v["y"], cur))
    routes = json.loads(json.dumps(R.ROUTES))
    l5lib.polish(routes, R.S)
    log("== l5f_route: %d hand-copper violations, router fails %s" % (nbad[0], R.FAILS))
    json.dump({"routes": routes, "fails": R.FAILS, "violations": nbad[0], "log": LOG}, open(OUT, "w"), indent=0,
              sort_keys=True)
    if nbad[0] or R.FAILS:
        sys.exit(1)


EN = {"U4": "U4_EN", "U6": "U6_EN", "U5": "VCC_DDR_1V8_EN", "U7": "VCC_DDR_1V8_EN"}

if __name__ == "__main__":
    main()
