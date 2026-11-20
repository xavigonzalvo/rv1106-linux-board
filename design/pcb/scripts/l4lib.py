"""Layout phase L4: geometry + grid search + exact octilinear path pulling for the critical routing (design/.venv).

Used by l4_route.py. Board mm (origin NW corner, y south). The board copper comes from l4_export.py (board_geo.json).

How a net is routed (hand-quality, not an autorouter run):
  1. grid search (0.025 mm cells, scipy Dijkstra, 8 directions, L1/L4 + vias where the net may use them) on a window
     around the terminals; a cell is blocked when a track centred there would come closer to other-net copper than
     the rule of that pair of items (class clearances, the .kicad_dru custom rules, the design rules of layout.md §4);
  2. the cell path is "pulled" into an octilinear polyline (0/45/90 deg segments, at most one elbow between two
     path points) and every candidate segment is validated with exact geometry (segment/segment, segment/polygon,
     hole clearance); the farthest valid jump wins;
  3. the result is added to the obstacle store, so the next net sees it.
Diff pairs are routed as one envelope (2 w + gap) along a centre line that is then offset into the P and N lines
(constant gap = the class gap); breakouts to pads/links are routed per line.
Exact clearance = what KiCad DRC checks (+ EPS); KiCad DRC on the written board stays the judge.
"""
import json
import math

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph

RES = 0.025
EPS = 0.001                 # exact-check safety margin (mm)
PAD_EPS = 0.003             # pad outlines are polygons inside the true (round) shape: up to ~2 um short
GM = 0.002                  # grid blocking margin (> EPS) so a path of legal cells pulls into legal segments
VIA_D, VIA_DR = 0.50, 0.30
HOLE_CLR, HOLE_HOLE = 0.25, 0.45
EDGE = 0.40
FAN = (26.6, 28.6, 42.4, 44.4)            # rule area U9_FAN (DRU neck-down)
FAN_REACH = 3.2                           # a neck-down exit segment ends within this distance of the fan band
F, B = 1, 2
LAYN = {"F": F, "B": B}
DIFF = ("ETH_DIFF", "USB_DIFF")
XTAL_GUARD_REFS = ("Y1", "Y2", "C76", "C77", "C78", "C79")
SEP = {"ETH_TXP": "TX", "ETH_TXN": "TX", "ETH_TXP_J": "TX", "ETH_TXN_J": "TX",
       "ETH_RXP": "RX", "ETH_RXN": "RX", "ETH_RXP_J": "RX", "ETH_RXN_J": "RX"}
RTC = ("RTC_XIN", "RTC_XOUT")
# breakout parts of each pair class: their pads (and other-net copper whose segment touches their courtyard) are exempt
# from the 30 mil rule (DRU 'pairs keep 30 mil', D-90 a, D-112 b)
BREAKOUT = {"ETH_DIFF": ("U9",), "USB_DIFF": ("U9", "J1", "U1", "U2", "U11")}
# U9 ring-1 band (Chebyshev <= 10.3 mm from the U9 centre): the lane exits between the ring-1 caps (D-104, D-110); the
# USB pad/via 30 mil rule starts outside it (D-112 b)
RING = (24.2, 26.2, 44.8, 46.8)
VIA_ETH = False             # L5 scripts set it: new vias keep 0.76 mm from the ETH lines too (D-113)
VIA_USB_STRICT = False      # L5 round 3 (D-115, verifier minor usbc): a new via is exempt from the USB 30 mil rule only
                            # when its centre lies inside a breakout courtyard (not within a via radius of it)


# ----------------------------------------------------------------------------------------------------------------
# exact geometry (vectorised over obstacles)
# ----------------------------------------------------------------------------------------------------------------
def pt_seg_v(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = np.where(L > 0, ((px - ax) * dx + (py - ay) * dy) / np.where(L > 0, L, 1), 0.0)
    t = np.clip(t, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def seg_seg_v(a, b, C, D):
    """distance between segment a-b (scalars) and segments C-D (arrays Nx2)."""
    cx, cy, dx, dy = C[:, 0], C[:, 1], D[:, 0], D[:, 1]
    d = np.minimum.reduce([pt_seg_v(a[0], a[1], cx, cy, dx, dy), pt_seg_v(b[0], b[1], cx, cy, dx, dy),
                           pt_seg_v(cx, cy, a[0], a[1], b[0], b[1]), pt_seg_v(dx, dy, a[0], a[1], b[0], b[1])])

    def orient(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    o1 = orient(a[0], a[1], b[0], b[1], cx, cy)
    o2 = orient(a[0], a[1], b[0], b[1], dx, dy)
    o3 = orient(cx, cy, dx, dy, a[0], a[1])
    o4 = orient(cx, cy, dx, dy, b[0], b[1])
    cross = (o1 * o2 < 0) & (o3 * o4 < 0)
    return np.where(cross, 0.0, d)


def inside_poly(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > py) != (by > py) and px < (bx - ax) * (py - ay) / (by - ay + 1e-12) + ax:
            c = not c
    return c


def seg_intersects_rect(a, b, r, pad=0.0):
    x0, y0, x1, y1 = r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad
    # Liang-Barsky
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


# ----------------------------------------------------------------------------------------------------------------
# obstacle store
# ----------------------------------------------------------------------------------------------------------------
class Store:
    """All copper of the board. Items: kind 0 track (capsule), 1 via (circle), 2 pad edge (segment of a pad polygon,
    hw 0); pads also kept as polygons for the inside test. Per item: layer mask, net, a, b, hw, flags."""

    def __init__(self, geo):
        self.geo = geo
        self.cls = {n: v for n, v in geo["classes"].items()}
        self.court = geo["court"]
        self.items = []          # python list of tuples, converted to arrays lazily
        self.pads = []           # dicts with poly, layers, net, ref
        self.holes = []          # (x, y, r, net)
        for p in geo["pads"]:
            lay = sum(LAYN[l] for l in p["layers"] if l in LAYN)
            if not lay:
                continue
            poly = p["poly"]
            if len(poly) < 3:
                continue
            k = len(self.pads)
            self.pads.append(dict(poly=poly, lay=lay, net=p["net"], ref=p["ref"], num=p["num"], x=p["x"], y=p["y"]))
            n = len(poly)
            for i in range(n):
                self.items.append((2, lay, p["net"], poly[i][0], poly[i][1], poly[(i + 1) % n][0],
                                   poly[(i + 1) % n][1], 0.0, k))
            if p["th"]:
                self.holes.append((p["x"], p["y"], p["drill"], p["net"]))
        for t in geo["tracks"]:
            if t["layer"] not in LAYN:
                continue
            self.add_track(t["net"], LAYN[t["layer"]], t["a"], t["b"], t["w"] / 2, -1)
        for v in geo["vias"]:
            self.add_via(v["net"], v["x"], v["y"], v["d"] / 2, v["drill"] / 2)
        for x, y, r in geo["npth"]:
            self.holes.append((x, y, r, "#NPTH"))
        self.keep = [a["rect"] for a in geo["areas"] if a["no_tracks"]]
        self._arr = None

    def add_track(self, net, lay, a, b, hw, tag=-2):
        self.items.append((0, lay, net, a[0], a[1], b[0], b[1], hw, tag))
        self._arr = None

    def set_track_layer(self, net, a, b, lay):
        """disable (lay 0) or restore a stored track segment (used by the length tuner)"""
        for k, it in enumerate(self.items):
            if it[0] == 0 and it[2] == net and abs(it[3] - a[0]) < 1e-9 and abs(it[4] - a[1]) < 1e-9 \
                    and abs(it[5] - b[0]) < 1e-9 and abs(it[6] - b[1]) < 1e-9:
                self.items[k] = (it[0], lay) + it[2:]
        self._arr = None

    def add_via(self, net, x, y, r, dr):
        self.items.append((1, F | B, net, x, y, x, y, r, -3))
        self.holes.append((x, y, dr, net))
        self._arr = None

    def arr(self):
        if self._arr is None:
            it = self.items
            self._arr = dict(kind=np.array([i[0] for i in it]), lay=np.array([i[1] for i in it]),
                             net=np.array([i[2] for i in it], dtype=object),
                             A=np.array([[i[3], i[4]] for i in it]), Bp=np.array([[i[5], i[6]] for i in it]),
                             hw=np.array([i[7] for i in it]), tag=np.array([i[8] for i in it]))
            a = self._arr
            a["x0"] = np.minimum(a["A"][:, 0], a["Bp"][:, 0]) - a["hw"]
            a["x1"] = np.maximum(a["A"][:, 0], a["Bp"][:, 0]) + a["hw"]
            a["y0"] = np.minimum(a["A"][:, 1], a["Bp"][:, 1]) - a["hw"]
            a["y1"] = np.maximum(a["A"][:, 1], a["Bp"][:, 1]) + a["hw"]
            # obstacle class info
            cl = np.array([self.cls.get(n, ["DEFAULT", 0.15, 0.15, 0])[2] if n and not n.startswith("#") else 0.15
                           for n in a["net"]])
            a["clr"] = cl
            a["ncls"] = np.array([self.cls.get(n, ["", 0, 0, 0])[0] if n else "" for n in a["net"]], dtype=object)
            infan = np.array([seg_intersects_rect((i[3], i[4]), (i[5], i[6]), FAN) if i[0] == 0 else False
                              for i in it])
            a["fan"] = infan
            cu = self.court.get("U9")
            a["fanB"] = np.array([i[0] == 0 and cu is not None and seg_intersects_rect((i[3], i[4]), (i[5], i[6]), cu)
                                  for i in it])
            a["padref"] = np.array([self.pads[i[8]]["ref"] if i[0] == 2 else "" for i in it], dtype=object)
            # tracks / vias touching a USB breakout courtyard (exempt from the USB pad/via 30 mil rule, as in the DRU)
            uc = [self.court[r] for r in BREAKOUT["USB_DIFF"] if r in self.court]
            a["inring"] = np.array([i[0] == 0 and seg_intersects_rect((i[3], i[4]), (i[5], i[6]), RING, i[7])
                                    for i in it])
            a["inusb"] = np.array([i[0] in (0, 1) and any(seg_intersects_rect((i[3], i[4]), (i[5], i[6]), r, i[7])
                                                          for r in uc) for i in it])
            # obstacle tracks of a diff class outside the courtyards excluded by the DRU 0.76 rules
            a["dtrk"] = np.array([self._diff_track(i) for i in it])
        return self._arr

    def _diff_track(self, i):
        if i[0] != 0:
            return ""
        c = self.cls.get(i[2], [""])[0]
        if c not in DIFF:
            return ""
        refs = BREAKOUT[c]
        for r in refs:
            if r in self.court and seg_intersects_rect((i[3], i[4]), (i[5], i[6]), self.court[r]):
                return ""
        return c

    # ------------------------------------------------------------------------------------------------------------
    def required(self, net, kind, a, b, own=(), sub=None, nofan=False):
        """Required clearance (edge to edge) from a new item (kind 'track' or 'via') of `net` on segment a-b to every
        stored item (array; inf where not applicable = same net); sub = index subset."""
        A0 = self.arr()
        A = A0 if sub is None else {k: v[sub] for k, v in A0.items()}
        cls = self.cls.get(net, ["DEFAULT", 0.15, 0.15, 0])
        c_me = cls[2]
        mycls = cls[0]
        req = np.maximum(A["clr"], c_me)
        is_track = kind == "track"
        infan = is_track and seg_intersects_rect(a, b, FAN)
        # diff pairs: 30 mil to other tracks (DRU), not GND, own class excluded (DRU); TX vs RX 0.76 (D-108 b)
        if is_track and mycls in DIFF:
            refs = BREAKOUT[mycls]
            out_court = not any(r in self.court and seg_intersects_rect(a, b, self.court[r]) for r in refs)
            if out_court:
                m = (A["kind"] == 0) & (A["ncls"] != mycls) & (A["net"] != "GND")
                req = np.where(m, np.maximum(req, 0.76), req)
                # USB (D-112 b): also 30 mil to other-net pads and vias, except the breakout parts' own pins and copper
                # touching their courtyards, and inside the U9 ring-1 band
                if mycls == "USB_DIFF" and not seg_intersects_rect(a, b, RING):
                    m2 = (A["kind"] != 0) & (A["ncls"] != mycls) & (A["net"] != "GND") & \
                        ~np.isin(A["padref"], refs) & ~A["inusb"]
                    req = np.where(m2, np.maximum(req, 0.76), req)
        if kind in ("track", "via") and mycls not in DIFF and net != "GND":
            m = (A["dtrk"] != "") & (A["dtrk"] != mycls)
            if kind == "via":
                mu = m & (A["dtrk"] == "USB_DIFF") & ~A["inring"]
                if any(seg_intersects_rect(a, a, self.court[r], 0.0 if VIA_USB_STRICT else VIA_D / 2)
                       for r in BREAKOUT["USB_DIFF"] if r in self.court):
                    mu = mu & False
                # L5 (D-113): a new via also keeps 30 mil from the ETH lines (layout.md §4.2 'pairs >= 0.76 mm from
                # other nets'; the L4 router did not need it, so it is off unless a script sets VIA_ETH)
                me = m & (A["dtrk"] == "ETH_DIFF") if VIA_ETH else m & False
                m = mu | me
            req = np.where(m, np.maximum(req, 0.76), req)
        # diff vs clocks / SW nodes 1.27 (any item), vs RTC 0.76
        if mycls in DIFF:
            m = ((A["ncls"] == "XTAL") & ~np.isin(A["net"], RTC)) | (A["ncls"] == "SW_NODE")
            req = np.where(m, np.maximum(req, 1.27), req)
            req = np.where(np.isin(A["net"], RTC), np.maximum(req, 0.76), req)
        if mycls == "XTAL" and net not in RTC or mycls == "SW_NODE":
            m = np.isin(A["ncls"], DIFF)
            req = np.where(m, np.maximum(req, 1.27), req)
        if net in RTC:
            req = np.where(np.isin(A["ncls"], DIFF), np.maximum(req, 0.76), req)
        # SENSE/XTAL tracks vs SW nodes 2.0 (outside U4-U7 courtyards)
        if mycls in ("SENSE", "XTAL") and kind != "pad":
            if not any(r in self.court and seg_intersects_rect(a, b, self.court[r]) for r in ("U4", "U5", "U6", "U7")):
                req = np.where(A["ncls"] == "SW_NODE", np.maximum(req, 2.0), req)
        if mycls == "SW_NODE":
            m = np.isin(A["ncls"], ("SENSE", "XTAL")) & (A["kind"] != 2)
            req = np.where(m, np.maximum(req, 2.0), req)
        # crystal guard (layout.md §4.3): no other net on L1 within 1 mm of the crystal pads
        if mycls != "XTAL" and net != "GND":
            m = np.isin(A["padref"], XTAL_GUARD_REFS)
            req = np.where(m, np.maximum(req, 1.0), req)
        # DRU neck-down: any track in U9_FAN (this one or the other) -> 0.10
        if is_track:
            # DRU 'QFN-128 escape neck-down': A.intersectsCourtyard('U9') || A.intersectsArea('U9_FAN'); the U9_FAN rule
            # area is on L1 only, so for L4 copper only the U9 courtyard counts (DRC, L4 r2: an L4 VCC_1V8 track
            # ending in the fan box came 0.19 mm from a GND via)
            if nofan:
                cu = self.court.get("U9")
                fanm = A["fanB"] | (cu is not None and seg_intersects_rect(a, b, cu))
            else:
                fanm = A["fan"] | infan
            req = np.where(fanm, np.minimum(req, 0.10), req)
        # ETH TX vs RX >= 0.76 mm everywhere, also in the fan (D-108 b; our rule, not the DRU), J3 pins exempt
        if net in SEP:
            g = SEP[net]
            other = np.array([SEP.get(n, g) != g for n in A["net"]])
            jpin = A["padref"] == "J3"
            both_fan = A["fan"] & infan          # inside the fan the escape plan (L3, D-104) governs TX vs RX
            req = np.where(other & ~jpin & ~both_fan, np.maximum(req, 0.76), req)
        same = np.isin(A["net"], (net,) + tuple(own))
        req = np.where(same, -np.inf, req)
        return req

    def check_seg(self, net, lay, a, b, hw, own=(), extra=0.0, report=False):
        """Exact check of a new track segment. Returns True if legal (or list of violations if report)."""
        A = self.arr()
        x0, x1 = min(a[0], b[0]) - hw - 2.5, max(a[0], b[0]) + hw + 2.5
        y0, y1 = min(a[1], b[1]) - hw - 2.5, max(a[1], b[1]) + hw + 2.5
        # edges / keepouts
        for p in (a, b):
            if not (EDGE + hw <= p[0] <= 80 - EDGE - hw and EDGE + hw <= p[1] <= 80 - EDGE - hw):
                return [("edge", p)] if report else False
        for r in self.keep:
            if seg_intersects_rect(a, b, r, hw):
                return [("keepout", r)] if report else False
        near = np.nonzero(((A["lay"] & lay) != 0) & (A["x1"] >= x0) & (A["x0"] <= x1) & (A["y1"] >= y0) & (A["y0"] <= y1))[0]
        bad = []
        if len(near):
            # the DRU neck-down area U9_FAN is an L1 rule area: no relaxed clearance for L4 copper (DRC, L4 r2: an L4
            # VCC_1V8 track ending in the fan box came 0.19 mm from a GND via)
            req = self.required(net, "track", a, b, own, near, nofan=(lay == B))
            d = seg_seg_v(a, b, A["A"][near], A["Bp"][near]) - hw - A["hw"][near]
            pe = 0.0 if self.cls.get(net, [""])[0] == "XTAL" else PAD_EPS   # XTAL: passes verified by DRC
            v = d < req + EPS + extra + np.where(A["kind"][near] == 2, pe, 0.0)
            if v.any():
                if not report:
                    return False
                for k in np.nonzero(v)[0]:
                    bad.append((A["net"][near[k]], float(d[k]), float(req[k]), int(A["kind"][near[k]])))
        # inside another net's pad (no edge crossing)
        for p in self.pads:
            if p["lay"] & lay and p["net"] != net and p["net"] not in own and inside_poly(a[0], a[1], p["poly"]):
                if not report:
                    return False
                bad.append((p["net"], 0.0, 0.0, 2))
        # hole clearance
        for (hx, hy, hr, hn) in self.holes:
            if hn == net or hn in own:
                continue
            if abs(hx - a[0]) > 3 + abs(b[0] - a[0]) or abs(hy - a[1]) > 3 + abs(b[1] - a[1]):
                continue
            d = pt_seg_v(hx, hy, a[0], a[1], b[0], b[1]) - hw - hr
            if d < HOLE_CLR + EPS:
                if not report:
                    return False
                bad.append((hn, float(d), HOLE_CLR, 9))
        if report:
            return bad
        return True

    def check_via(self, net, x, y, own=(), novia=(), self_ok=False, own_pad_ok=False):
        A = self.arr()
        r = VIA_D / 2
        if not (EDGE + r <= x <= 80 - EDGE - r and EDGE + r <= y <= 80 - EDGE - r):
            return False
        for q in novia:
            if q[0] <= x <= q[2] and q[1] <= y <= q[3]:
                return False
        for q in self.keep:
            if q[0] - r <= x <= q[2] + r and q[1] - r <= y <= q[3] + r:
                return False
        near = np.nonzero((A["x1"] >= x - 2.5) & (A["x0"] <= x + 2.5) & (A["y1"] >= y - 2.5) & (A["y0"] <= y + 2.5))[0]
        if len(near):
            req = self.required(net, "via", (x, y), (x, y), own, near)
            d = pt_seg_v(x, y, A["A"][near, 0], A["A"][near, 1], A["Bp"][near, 0], A["Bp"][near, 1]) - r - A["hw"][near]
            if self_ok:
                d = np.where((A["kind"][near] == 1) & (np.abs(A["A"][near, 0] - x) < 1e-6) &
                             (np.abs(A["A"][near, 1] - y) < 1e-6), 9.0, d)
            if (d < req + EPS).any():
                return False
        for p in self.pads:
            if inside_poly(x, y, p["poly"]) and not (own_pad_ok and p["net"] == net):
                return False
        for (hx, hy, hr, hn) in self.holes:
            dd = math.hypot(hx - x, hy - y)
            if self_ok and dd < 1e-6:
                continue
            if dd - hr - VIA_DR / 2 < HOLE_HOLE + EPS:
                return False
        return True


# ----------------------------------------------------------------------------------------------------------------
# grid search
# ----------------------------------------------------------------------------------------------------------------
class Grid:
    def __init__(self, store, net, hw, win, layers, own=(), via_ok=False, novia=(), relax=None, cost_fn=None,
                 forbid=(), forbid_free=()):
        """win = (x0, y0, x1, y1). layers: mask F|B allowed. relax: list of rects where the DRU neck-down 0.10 applies
        to the search (the U9 gate-lane exits). forbid: [(mask, rect)] extra blocked rectangles."""
        self.s, self.net, self.hw, self.own = store, net, hw, own
        x0, y0, x1, y1 = win
        x0, y0 = max(0.0, x0), max(0.0, y0)
        x1, y1 = min(80.0, x1), min(80.0, y1)
        self.x0, self.y0 = x0, y0
        self.W = int((x1 - x0) / RES) + 1
        self.H = int((y1 - y0) / RES) + 1
        self.layers = layers
        cx = x0 + (np.arange(self.W) + 0.5) * RES
        cy = y0 + (np.arange(self.H) + 0.5) * RES
        self.cx, self.cy = cx, cy
        X, Y = np.meshgrid(cx, cy)
        A = store.arr()
        mid = ((x0 + x1) / 2, (y0 + y1) / 2)
        req_t = store.required(net, "track", (x0, y0), (x1, y1), own)     # window-wide (fan handled below)
        req_t_nofan = store.required(net, "track", (-9, -9), (-9, -8), own)
        req_v = store.required(net, "via", mid, mid, own)
        self.block = {}
        relax_m = np.zeros((self.H, self.W), bool)
        for r in (relax or []):
            relax_m |= (X >= r[0]) & (X <= r[2]) & (Y >= r[1]) & (Y <= r[3])
        fan_m = (X >= FAN[0]) & (X <= FAN[2]) & (Y >= FAN[1]) & (Y <= FAN[3])
        cu9 = store.court.get("U9", (0, 0, -1, -1))
        court_m = (X >= cu9[0]) & (X <= cu9[2]) & (Y >= cu9[1]) & (Y <= cu9[3])
        for L in (F, B):
            if not layers & L:
                continue
            blk = np.zeros((self.H, self.W), bool)
            edge = (X < EDGE + hw) | (X > 80 - EDGE - hw) | (Y < EDGE + hw) | (Y > 80 - EDGE - hw)
            blk |= edge
            for r in store.keep:
                blk |= (X >= r[0] - hw) & (X <= r[2] + hw) & (Y >= r[1] - hw) & (Y <= r[3] + hw)
            sel = np.nonzero(((A["lay"] & L) != 0) & (A["x1"] >= x0 - 3) & (A["x0"] <= x1 + 3) & (A["y1"] >= y0 - 3)
                             & (A["y0"] <= y1 + 3))[0]
            for k in sel:
                rq_far = req_t_nofan[k]
                if not np.isfinite(rq_far):
                    continue
                sepk = net in SEP and SEP.get(A["net"][k], SEP[net]) != SEP[net] and A["padref"][k] != "J3"
                rq_near = min(rq_far, 0.10) if (A["fan"][k] if L == F else A["fanB"][k]) and not sepk else rq_far
                rq = max(rq_far, rq_near)
                rr = hw + rq + A["hw"][k] + GM + (PAD_EPS if A["kind"][k] == 2 and store.cls.get(net, [""])[0] != "XTAL"
                                                  else 0.0)
                bx0, bx1 = A["x0"][k] - hw - rq - 0.05, A["x1"][k] + hw + rq + 0.05
                by0, by1 = A["y0"][k] - hw - rq - 0.05, A["y1"][k] + hw + rq + 0.05
                j0 = max(0, int((bx0 - x0) / RES))
                j1 = min(self.W, int((bx1 - x0) / RES) + 2)
                i0 = max(0, int((by0 - y0) / RES))
                i1 = min(self.H, int((by1 - y0) / RES) + 2)
                if j1 <= j0 or i1 <= i0:
                    continue
                px, py = X[i0:i1, j0:j1], Y[i0:i1, j0:j1]
                d = pt_seg_v(px, py, A["A"][k, 0], A["A"][k, 1], A["Bp"][k, 0], A["Bp"][k, 1])
                # fan / relax cells: neck-down 0.10 for tracks
                lim = rr if sepk else np.where((fan_m if L == F else court_m)[i0:i1, j0:j1] | relax_m[i0:i1, j0:j1],
                                               hw + min(rq_far, 0.10) + A["hw"][k] + GM, rr)
                blk[i0:i1, j0:j1] |= d < lim
            # pad interiors of other nets
            for p in store.pads:
                if not (p["lay"] & L) or p["net"] == net or p["net"] in own:
                    continue
                xs = [q[0] for q in p["poly"]]
                ys = [q[1] for q in p["poly"]]
                if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
                    continue
                j0 = max(0, int((min(xs) - x0) / RES))
                j1 = min(self.W, int((max(xs) - x0) / RES) + 2)
                i0 = max(0, int((min(ys) - y0) / RES))
                i1 = min(self.H, int((max(ys) - y0) / RES) + 2)
                blk[i0:i1, j0:j1] = True     # bbox of pad (edges already inflate the rest)
            # hole clearance
            for (hx, hy, hr, hn) in store.holes:
                if hn == net or hn in own or not (x0 - 2 <= hx <= x1 + 2 and y0 - 2 <= hy <= y1 + 2):
                    continue
                rr = hr + hw + HOLE_CLR + GM
                j0 = max(0, int((hx - rr - x0) / RES))
                j1 = min(self.W, int((hx + rr - x0) / RES) + 2)
                i0 = max(0, int((hy - rr - y0) / RES))
                i1 = min(self.H, int((hy + rr - y0) / RES) + 2)
                if j1 > j0 and i1 > i0:
                    blk[i0:i1, j0:j1] |= np.hypot(X[i0:i1, j0:j1] - hx, Y[i0:i1, j0:j1] - hy) < rr
            fm = np.zeros((self.H, self.W), bool)
            for (m, r) in forbid:
                if m & L:
                    fm |= (X >= r[0] - hw - GM) & (X <= r[2] + hw + GM) & (Y >= r[1] - hw - GM) & \
                        (Y <= r[3] + hw + GM)
            for r in forbid_free:          # the forbidden areas do not apply around the net's own terminals
                fm &= ~((X >= r[0]) & (X <= r[2]) & (Y >= r[1]) & (Y <= r[3]))
            blk |= fm
            self.block[L] = blk
        # via sites
        self.via = np.zeros((self.H, self.W), bool)
        if via_ok and layers == F | B:
            ok = ~self.block[F] & ~self.block[B]
            r = VIA_D / 2
            ok &= (X > EDGE + r) & (X < 80 - EDGE - r) & (Y > EDGE + r) & (Y < 80 - EDGE - r)
            for q in novia:
                ok &= ~((X >= q[0]) & (X <= q[2]) & (Y >= q[1]) & (Y <= q[3]))
            sel = np.nonzero((A["x1"] >= x0 - 3) & (A["x0"] <= x1 + 3) & (A["y1"] >= y0 - 3) & (A["y0"] <= y1 + 3))[0]
            for k in sel:
                rq = req_v[k]
                if not np.isfinite(rq):
                    continue
                rr = r + rq + A["hw"][k] + GM + 0.02
                j0 = max(0, int((A["x0"][k] - rr - x0) / RES))
                j1 = min(self.W, int((A["x1"][k] + rr - x0) / RES) + 2)
                i0 = max(0, int((A["y0"][k] - rr - y0) / RES))
                i1 = min(self.H, int((A["y1"][k] + rr - y0) / RES) + 2)
                if j1 <= j0 or i1 <= i0:
                    continue
                d = pt_seg_v(X[i0:i1, j0:j1], Y[i0:i1, j0:j1], A["A"][k, 0], A["A"][k, 1], A["Bp"][k, 0], A["Bp"][k, 1])
                ok[i0:i1, j0:j1] &= d >= rr
            for (hx, hy, hr, hn) in store.holes:
                rr = hr + VIA_DR / 2 + HOLE_HOLE + GM + 0.02
                if hn != net and hn not in own:
                    rr = max(rr, hr + r + HOLE_CLR + GM + 0.02)
                j0 = max(0, int((hx - rr - x0) / RES))
                j1 = min(self.W, int((hx + rr - x0) / RES) + 2)
                i0 = max(0, int((hy - rr - y0) / RES))
                i1 = min(self.H, int((hy + rr - y0) / RES) + 2)
                if j1 > j0 and i1 > i0:
                    ok[i0:i1, j0:j1] &= np.hypot(X[i0:i1, j0:j1] - hx, Y[i0:i1, j0:j1] - hy) >= rr
            for p in store.pads:
                xs = [q[0] for q in p["poly"]]
                ys = [q[1] for q in p["poly"]]
                j0 = max(0, int((min(xs) - r - x0) / RES))
                j1 = min(self.W, int((max(xs) + r - x0) / RES) + 2)
                i0 = max(0, int((min(ys) - r - y0) / RES))
                i1 = min(self.H, int((max(ys) + r - y0) / RES) + 2)
                if j1 > j0 and i1 > i0:
                    ok[i0:i1, j0:j1] = False
            self.via = ok
        self.cost = {L: np.ones((self.H, self.W)) for L in self.block}
        if cost_fn:
            for L in self.cost:
                self.cost[L] = cost_fn(L, X, Y)
        self.X, self.Y = X, Y

    def cell(self, x, y):
        return (min(self.H - 1, max(0, int((y - self.y0) / RES))), min(self.W - 1, max(0, int((x - self.x0) / RES))))

    def xy(self, i, j):
        return (self.x0 + (j + 0.5) * RES, self.y0 + (i + 0.5) * RES)

    def search(self, srcs, dsts, via_cost=3.0):
        """srcs/dsts: lists of (L, i, j). Returns list of (L, i, j) from a source to a destination or None."""
        Ls = sorted(self.block)
        N = self.H * self.W
        lidx = {L: k for k, L in enumerate(Ls)}
        rows, cols, wts = [], [], []
        idx = np.arange(N).reshape(self.H, self.W)
        S2 = math.sqrt(2)
        free = {L: ~self.block[L] for L in Ls}
        for s in srcs + dsts:
            if s[0] in free:
                free[s[0]][s[1], s[2]] = True
        for L in Ls:
            fr = free[L]
            c = self.cost[L]
            off = lidx[L] * N
            H, W = self.H, self.W
            for dy, dx, ln in ((0, 1, 1.0), (1, 0, 1.0), (1, 1, S2), (1, -1, S2)):
                A = (slice(0, H - dy), slice(max(0, -dx), W - max(0, dx)))
                Bs = (slice(dy, H), slice(max(0, -dx) + dx, W - max(0, dx) + dx))
                ok = fr[A] & fr[Bs]
                a = idx[A][ok] + off
                b = idx[Bs][ok] + off
                w = ln * (c[A][ok] + c[Bs][ok]) / 2 * RES
                rows += [a, b]
                cols += [b, a]
                wts += [w, w]
        if len(Ls) == 2:
            v = self.via & free[Ls[0]] & free[Ls[1]]
            a = idx[v]
            rows += [a, a + N]
            cols += [a + N, a]
            wts += [np.full(a.shape, via_cost), np.full(a.shape, via_cost)]
        G = sparse.csr_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))),
                              shape=(len(Ls) * N, len(Ls) * N))
        si = np.array(sorted({lidx[L] * N + i * self.W + j for (L, i, j) in srcs if L in lidx}))
        di = np.array(sorted({lidx[L] * N + i * self.W + j for (L, i, j) in dsts if L in lidx}))
        if not len(si) or not len(di):
            return None
        dist, pred, _ = csgraph.dijkstra(G, directed=True, indices=si, return_predecessors=True, min_only=True)
        k = di[np.argmin(dist[di])]
        if not np.isfinite(dist[k]):
            return None
        path = []
        while k >= 0:
            Lk, q = divmod(int(k), N)
            i, j = divmod(q, self.W)
            path.append((Ls[Lk], i, j))
            k = pred[k]
        path.reverse()
        return path


# ----------------------------------------------------------------------------------------------------------------
# pulling into octilinear segments
# ----------------------------------------------------------------------------------------------------------------
def octi(a, b):
    """Elbow candidates joining a to b with 0/45/90 deg legs: [] if straight octilinear, else two middle points."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 1e-6 or abs(dy) < 1e-6 or abs(abs(dx) - abs(dy)) < 1e-6:
        return [None]
    m = min(abs(dx), abs(dy))
    sx, sy = math.copysign(1, dx), math.copysign(1, dy)
    p1 = (a[0] + sx * m, a[1] + sy * m)            # diagonal first
    p2 = (b[0] - sx * m, b[1] - sy * m)            # straight first
    return [p2, p1]


def pull(store, net, hw, pts, layer, own=(), fixed_first=False, check=None):
    """pts: dense point list (cell centres) on one layer. Returns an octilinear polyline whose segments pass the exact
    check. check(a, b) overrides store.check_seg."""
    base = check or (lambda a, b: store.check_seg(net, layer, a, b, hw, own))

    def chk(a, b):
        # a neck-down segment (one that touches U9_FAN) may reach at most FAN_REACH beyond the fan band: the DRU
        # 0.10 mm clearance then covers only the ring-1 row exit, not a long run
        if seg_intersects_rect(a, b, FAN):
            ex = FAN[0] - FAN_REACH, FAN[1] - FAN_REACH, FAN[2] + FAN_REACH, FAN[3] + FAN_REACH
            for p in (a, b):
                if not (ex[0] <= p[0] <= ex[2] and ex[1] <= p[1] <= ex[3]):
                    return False
        return base(a, b)
    out = [pts[0]]
    i = 0
    n = len(pts)
    while i < n - 1:
        best = None
        # binary-ish: try from far to near
        j = n - 1
        while j > i:
            a, b = out[-1], pts[j]
            cands = octi(a, b)
            if cands[0] is not None and seg_intersects_rect(a, b, FAN):
                cands = [None] + cands          # a straight neck-down segment out of the fan (DRU) may be any angle
            for mid in cands:
                if mid is None:
                    if chk(a, b):
                        best = (j, [b])
                        break
                elif chk(a, mid) and chk(mid, b):
                    best = (j, [mid, b])
                    break
            if best:
                break
            j -= 1 if j - i < 40 else max(1, (j - i) // 8)
        if not best:
            # fall back: straight to the next point (any angle) if legal, else fail
            if chk(out[-1], pts[i + 1]):
                best = (i + 1, [pts[i + 1]])
            else:
                return None
        out += best[1]
        i = best[0]
    out = smooth(out, chk)
    # merge collinear
    res = [out[0]]
    for p in out[1:]:
        if math.hypot(p[0] - res[-1][0], p[1] - res[-1][1]) < 1e-6:
            continue
        if len(res) >= 2:
            a, b = res[-2], res[-1]
            cr = (b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])
            dot = (b[0] - a[0]) * (p[0] - b[0]) + (b[1] - a[1]) * (p[1] - b[1])
            if abs(cr) < 1e-7 and dot > 0 and not seg_intersects_rect(a, p, FAN):
                res[-1] = p
                continue
        res.append(p)
    return res


def smooth(pts, chk, rounds=3):
    """remove small jogs: replace pts[i..j] (j <= i+4) by a straight/elbow octilinear link when legal and not longer"""
    pts = list(pts)
    for _ in range(rounds):
        changed = False
        i = 0
        while i < len(pts) - 2:
            done = False
            for j in range(min(len(pts) - 1, i + 4), i + 1, -1):
                a, b = pts[i], pts[j]
                old = plen(pts[i:j + 1])
                for mid in octi(a, b):
                    new = [a, b] if mid is None else [a, mid, b]
                    if plen(new) <= old + 1e-6 and len(new) < j - i + 1 and all(chk(p, q) for p, q in zip(new, new[1:])):
                        pts = pts[:i] + new + pts[j + 1:]
                        done = changed = True
                        break
                if done:
                    break
            i += 1
        if not changed:
            break
    return pts


def plen(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def offset_line(pts, d):
    """Offset a polyline by d to the left (positive) with miter joins."""
    out = []
    n = len(pts)
    for k in range(n):
        if k == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            L = math.hypot(dx, dy)
            nx, ny = -dy / L, dx / L
            out.append((pts[0][0] + nx * d, pts[0][1] + ny * d))
        elif k == n - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
            L = math.hypot(dx, dy)
            nx, ny = -dy / L, dx / L
            out.append((pts[-1][0] + nx * d, pts[-1][1] + ny * d))
        else:
            ax, ay = pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]
            bx, by = pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            n1 = (-ay / la, ax / la)
            n2 = (-by / lb, bx / lb)
            mx, my = n1[0] + n2[0], n1[1] + n2[1]
            lm = math.hypot(mx, my)
            mx, my = mx / lm, my / lm
            c = mx * n1[0] + my * n1[1]
            out.append((pts[k][0] + mx * d / c, pts[k][1] + my * d / c))
    return out


def meander(a, b, start, n, amp, g, side, ch=0.12):
    """polyline replacing segment a-b: straight to `start` (distance along a-b), n trapezoid cycles of amplitude
    amp and leg pitch g on `side` (+1 left / -1 right of a->b), then straight to b. Every corner chamfered (45 deg),
    so no bend is sharper than 135 deg; `start` must be >= the chamfer."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    nx, ny = -uy * side, ux * side
    c = min(ch, g / 3, amp / 3)

    def P(t, h):
        return (a[0] + ux * t + nx * h, a[1] + uy * t + ny * h)
    pts = [a]
    t = start
    for _ in range(n):
        # every corner chamfered: all bends 135 deg (layout.md §4.6 'bends >= 135 deg', verifier L4 r1)
        pts += [P(t - c, 0), P(t, c), P(t, amp - c), P(t + c, amp), P(t + g - c, amp), P(t + g, amp - c), P(t + g, c),
                P(t + g + c, 0)]
        t += g + g
    pts.append(b)
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out
