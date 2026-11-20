"""U9 (RV1106 QFN-128) escape plan for the ring-1 row: shared by place.py (planning) and check_placement.py (checking).

Geometry (layout.md §5.3, §6.1; decision D-104), measured from the U9 centre (34.5, 36.5), radial distance r:
  pad toes          r = 6.45
  via ring          r >= 7.45 (first escape via >= 1.0 mm outside the toes, §6.1), via pad 0.5 mm
  ring-1 row        inner pad edge r >= 7.90 (the via ring stays free), courtyards r 7.77 .. 9.63
  "gate"            the radial band r 7.93 .. 9.45 in front of each side (|t| <= 7.45): every pin that does not end in a
                    via-ring via, and is not served by the ring-1 part in front of it, must pass this band on L1
                    between the copper of the ring-1 parts, at its net-class width/clearance (netclasses.csv)
  fan band          r 6.45 .. 7.90: neck-down 0.10/0.10 mm (layout.md §4.1, <= 1.5 mm from the U9 pads); traces shift
                    sideways in parallel, at most FAN_REACH = 1.45 mm (45 deg over the 1.45 mm band)

The plan below says, for every SoC pin of a side, how it leaves:
  * PART   - a ring-1 part sits in front of it (ROW_PARTS); the part's pad on the pin's net faces the pin
  * VIA    - it drops to a via-ring via (VIA_PINS, plus every VDD_0V9/VDD_ARM/GND pin without a part: island / L2)
  * LANE   - a trace that passes the gate between ring-1 parts (everything else; NC pins have nothing)
  * THRU   - pins in THRU_LANES have a part *and* a lane (OSC_XOUT: R51 in the row, the lane runs on to R50/TP6)
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT = os.path.normpath(os.path.join(HERE, "..", "..", "layout"))

CENTRE = (34.5, 36.5)
PAD_CENTRE = 6.075     # pad-centre line, from the U9 centre
TOE = 6.45
VIA_RING = 7.45
ROW_INNER = 7.90       # minimum r of a ring-1 pad's inner edge
GATE = (7.93, 9.45)    # radial band checked for lane capacity (ring-1 pads; the via ring is checked separately)
FAN_REACH = 1.45       # max sideways shift of a lane / link in the fan band (45 deg)
NC_REACH = 2.60        # a part may shift further only over NC pins (link <= 3 mm: sqrt(3^2 - 1.45^2))
PAIR_CLEAR = 0.30      # diff pair to other copper inside the gate (D-104; 0.76 mm from the gate on, DRU)
PAIR_REACH = 1.35      # a pair lane's centre shifts less: its outer line sits 0.04 mm further out than the pin (trial route, D-107)
PAIR_PAIR_CLEAR = 0.76 # pair to pair (ETH TX / RX) from the gate on: layout.md §4.1 30 mil (verifier L2 r2)

# ring-1 parts in the row and the SoC pins whose net their facing pad carries (D-104)
ROW_PARTS = {
    "S": [("C59", [1]), ("C48", [10]), ("C64", [13]), ("R48", [15]), ("C58", [24]), ("C65", [28]), ("C70", [30]),
          ("C57", [31])],
    "E": [("C61", [61]), ("R46", [58]), ("C49", [54, 55]), ("C54", [53]), ("C60", [53]), ("R41", [52]), ("C53", [49, 50]),
          ("R47", [48]), ("C63", [43])],
    "N": [("C56", [96]), ("C67", [88]), ("C62", [81]), ("C74", [71]), ("C55", [70]), ("R51", [69]), ("C51", [67])],
    "W": [("C66", [101]), ("R42", [102]), ("C50", [103]), ("C68", [108]), ("C52", [115])],
}
# pins that drop to a via in the via ring (r >= 7.45) instead of passing the gate (§2.3: L4 carries DEFAULT and the
# VCC_DDR / sub-rail feeds; VDD_0V9 goes to the L3 island)
VIA_PINS = {19: "VCC3V3_RTC -> L4 to D2/R34/C75 (PWR_SUB, uA load)",
            56: "VCC_DDR -> L4 (layout.md §2.3: VCC_DDR is an L1/L4 trace)",
            59: "SDMMC_PWREN (DEFAULT) -> L4 to R38 / Q4 (Z-SDPWR)",
            60: "PB_INT_N (DEFAULT) -> L4 to U3 / R10 / TP27 (Z-PWRIN)",
            65: "USB_SEL (DEFAULT) -> L4 to U11 pin 9 / R60",
            22: "SARADC_IN1 (SENSE, DC key/ADC) -> L4 to R45/C73 (D-104: trapped between the RTC and USB lanes)",
            23: "RECOVERY (SENSE, DC key) -> L4 to R44/C72 and R36 (D-104: same)",
            25: "USB_DET_IN (SENSE, DC divider) -> L4 under the USB pair to R4/C1 and R3 (D-104)"}
THRU_LANES = {69}      # OSC_XOUT: R51 (inner pad) in the row and a lane past it to R50 / TP6 (D-104)
PAIRS = {26: 27, 97: 98, 99: 100}   # first pin -> second pin of a diff pair (one lane)


def side_of(pin):
    pin = int(pin)
    return "S" if pin <= 32 else "E" if pin <= 64 else "N" if pin <= 96 else "W"


def t_of(side, x, y):
    return x if side in "NS" else y


def radial(side, x, y):
    cx, cy = CENTRE
    return {"S": y - cy, "N": cy - y, "E": x - cx, "W": cx - x}[side]


def point(side, t, r):
    """Board point at tangential coordinate t and radial distance r on `side`."""
    cx, cy = CENTRE
    return {"S": (t, cy + r), "N": (t, cy - r), "E": (cx + r, t), "W": (cx - r, t)}[side]


def net_rules():
    """net -> (class, width, clearance) from layout/netclasses.csv."""
    out = {}
    with open(os.path.join(LAYOUT, "netclasses.csv"), newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["net"]] = (r["netclass"], float(r["width_mm"] or 0), float(r["clearance_mm"] or 0))
    return out


def lane_wc(net, rules, pair=False):
    """(width, clearance) of the lane a pin needs in the gate. Supply lanes neck to 0.30 mm inside the gate."""
    cls, w, c = rules[net]
    if pair:
        gap = 0.15 if cls == "USB_DIFF" else 0.20
        return 2 * w + gap, PAIR_CLEAR
    if cls.startswith("PWR_"):
        w = min(w, 0.30)
    return w, c


def pin_roles(pins, rules):
    """pins: {pin: (x, y, net)} of U9 (1..128). Returns {pin: role} with role in PART/VIA/LANE/NC/PAIR2."""
    served = {p for side in ROW_PARTS.values() for _r, ps in side for p in ps}
    roles = {}
    second = set(PAIRS.values())
    for pin, (_x, _y, net) in pins.items():
        if not net:
            roles[pin] = "NC"
        elif pin in second:
            roles[pin] = "PAIR2"
        elif pin in served:
            roles[pin] = "PART"
        elif pin in VIA_PINS:
            roles[pin] = "VIA"
        elif rules[net][0] in ("GND", "PWR_0V9"):
            roles[pin] = "VIA"
        else:
            roles[pin] = "LANE"
    return roles


# ---------------------------------------------------------------------------------------------------------------
# planner: 1-D placement of the row along a side (dynamic programme over a 5 um grid)
# ---------------------------------------------------------------------------------------------------------------
def solve_row(items, need, grid=0.005):
    """items: list of dicts (in order) with keys lo, hi (target interval), L, U (hard window), w8 (weight).
    need(a, b): minimum centre distance between consecutive items. Minimises sum w8 * dist(x, [lo, hi])^2 (+ a
    stronger penalty beyond 0.5 mm) subject to the order/spacing constraints. Returns the positions, or None."""
    import math
    lo_all = min(i["L"] for i in items)
    hi_all = max(i["U"] for i in items)
    n = int(math.ceil((hi_all - lo_all) / grid)) + 1
    xs = [lo_all + k * grid for k in range(n)]
    INF = float("inf")

    def cost(it, x):
        if x < it["L"] - 1e-9 or x > it["U"] + 1e-9:
            return INF
        d = max(it["lo"] - x, 0.0, x - it["hi"])
        return it["w8"] * (d * d + 4.0 * max(0.0, d - 0.5) ** 2)

    f = [cost(items[0], x) for x in xs]
    back = []
    for i in range(1, len(items)):
        d = need(items[i - 1], items[i])
        sh = int(math.ceil(d / grid - 1e-9))
        # prefix minimum of f
        pm, pa = [INF] * n, [0] * n
        best, arg = INF, 0
        for k in range(n):
            if f[k] < best:
                best, arg = f[k], k
            pm[k], pa[k] = best, arg
        g, b = [INF] * n, [0] * n
        for k in range(n):
            j = k - sh
            if j < 0:
                continue
            c = cost(items[i], xs[k])
            if c == INF or pm[j] == INF:
                continue
            g[k], b[k] = c + pm[j], pa[j]
        back.append(b)
        f = g
    k = min(range(n), key=lambda q: f[q])
    if f[k] == INF:
        return None
    pos = [0.0] * len(items)
    pos[-1] = xs[k]
    for i in range(len(items) - 1, 0, -1):
        k = back[i - 1][k]
        pos[i - 1] = xs[k]
    return pos


def via_ring_fit(seq, side_lo, side_hi):
    """Fan-band check at the via ring (r = VIA_RING, neck-down 0.10/0.10 mm). seq: list of (name, kind, t_pin, t_gate)
    in pin order, kind 'lane' / 'link' / 'via'. A lane or a ring-1 link crosses the via ring somewhere between its pin and
    its gate position (+-0.3 mm); a via sits within FAN_REACH of its pin. Width at the ring: trace 0.10 + 0.10 clearance,
    via 0.50 + 0.10 each side (pitch to the next via >= 0.75 mm, hole-to-hole 0.45 + 0.30 drill). Greedy left-to-right
    packing; returns (ok, positions, first_failure)."""
    pos = []
    prev = None
    for name, kind, tp, tg in seq:
        if kind == "via":
            lo, hi = tp - FAN_REACH, tp + FAN_REACH
            half = 0.25
        else:
            lo, hi = min(tp, tg) - 0.3, max(tp, tg) + 0.3
            half = 0.05
        lo, hi = max(lo, side_lo + half), min(hi, side_hi - half)
        if prev is None:
            x = lo
        else:
            pk, px, ph = prev
            gap = 0.10
            if pk == "via" and kind == "via":
                d = max(0.75, ph + half + gap)
            else:
                d = ph + half + gap
            x = max(lo, px + d)
        if x > hi + 1e-9:
            return False, pos, name
        pos.append((name, x))
        prev = (kind, x, half)
    return True, pos, None
