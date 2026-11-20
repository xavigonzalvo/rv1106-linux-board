#!/usr/bin/env python3
"""Layout phase L2 (verifier L2 round 2): trial route of the critical nets from the saved board.

    PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $PY design/pcb/scripts/trial_route.py [board.kicad_pcb]     # writes design/pcb/trial/ + renders/trial_route*.png

Why a scripted router: Freerouting 2.5.0 (thirdparty/) is compiled for Java 25 (class file 69); the Java on this Mac is
23 (class file 67), so it does not start (UnsupportedClassVersionError). The task allows "a scripted maze route"
instead: maze_route.py (grid A*, run with design/.venv because it needs numpy/scipy/matplotlib).

Critical nets: classes SDMMC, FSPI, USB_DIFF, ETH_DIFF, ETH_CT, XTAL and SDMMC_DET (pin 11, part of the SD bus).
Layer policy (decision D-106): every critical net on L1, except the planned hops of D-106 (USB_DIFF swaps / pair
crossing / USB-C join, the ETH TX pair crossing under the RX pair), which may use L4 through vias. The trial is a
feasibility check of the placement: it ignores the non-critical nets (except the U9 via-ring vias), so passing it is
necessary, not sufficient; L5 routes everything.
"""
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import escape as esc  # noqa: E402

VENV_PY = os.path.join(bl.DESIGN, ".venv", "bin", "python")
MAZE = os.path.join(bl.HERE, "maze_route.py")
OUT_DIR = os.path.join(bl.PCB_DIR, "trial")

CRIT_CLASSES = ("XTAL", "USB_DIFF", "ETH_DIFF", "ETH_CT", "FSPI", "SDMMC")
EXTRA_NETS = ("SDMMC_DET", "VCC3V3_SD")   # VCC3V3_SD: the card supply must keep an L1 path J2.4-C23-C26 + via (D-108 c)
# D-108 (b): pair-to-pair separation groups (layout.md §10 "Diff pairs >= 0.76 mm ... from the other pair (ETH TX vs
# RX)"): between nets of different groups the 0.76 mm rule holds everywhere (also inside the R56-R59 field), and a trace
# keeps 0.76 mm from the other group's pads, except the J3 pins (2.54 mm jack pitch; class clearance there).
SEP_GROUP = {"ETH_TXP": "ETH_TX", "ETH_TXN": "ETH_TX", "ETH_TXP_J": "ETH_TX", "ETH_TXN_J": "ETH_TX",
             "ETH_RXP": "ETH_RX", "ETH_RXN": "ETH_RX", "ETH_RXP_J": "ETH_RX", "ETH_RXN_J": "ETH_RX"}
SEP_PAD_EXEMPT = ("J3",)
# D-108 (b): which line may pass between the pads of each ETH 0R link (the P/N swap of D-106 b); nobody else may
LINK_GAP_ALLOWED = {"R58": ("ETH_RXN_J",), "R56": ("ETH_TXN_J",), "R59": (), "R57": ()}
# D-108 (a): no via under / beside these packages (courtyard + 0.15 mm)
NO_VIA_REFS = ("U11", "U1", "J1")
TO_OTHER = {"ETH_DIFF": 0.76, "USB_DIFF": 0.76, "XTAL": 0.30, "SDMMC": 0.20, "FSPI": 0.20, "PWR_SD": 0.20}
# D-106: nets allowed to hop to L4 (short via hops for the topologically forced crossings)
L4_ALLOWED = {"USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM",
              "ETH_TXP", "ETH_TXN", "ETH_TXP_J", "ETH_TXN_J", "VCC3V3_SD"}
PARTNER = {}
for a, b in (("USB_DP", "USB_DM"), ("USBA_DP", "USBA_DM"), ("USBC_DP", "USBC_DM"), ("ETH_TXP", "ETH_TXN"),
             ("ETH_TXP_J", "ETH_TXN_J"), ("ETH_RXP", "ETH_RXN"), ("ETH_RXP_J", "ETH_RXN_J")):
    PARTNER[a], PARTNER[b] = b, a
ORDER_CLASSES = ("XTAL", "ETH_DIFF", "ETH_CT", "USB_DIFF", "FSPI", "PWR_SD", "SDMMC")
XGUARD = ("Y1", "Y2", "C76", "C77", "C78", "C79")


def crit_nets():
    out = {}
    with open(os.path.join(bl.LAYOUT, "netclasses.csv"), newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["netclass"] in CRIT_CLASSES or r["net"] in EXTRA_NETS:
                out[r["net"]] = dict(cls=r["netclass"], w=float(r["width_mm"]), c=float(r["clearance_mm"]),
                                     co=TO_OTHER.get(r["netclass"], 0.15),
                                     gap=float(r["diff_gap_mm"] or 0) or 0.2, partner=PARTNER.get(r["net"]),
                                     group=None if os.environ.get("TRIAL_NO_SEP") == "1" else SEP_GROUP.get(r["net"]))
    return out


def via_ring_vias(fp_u9):
    """Positions of the U9 via-ring vias (escape_plan.csv roles VIA, packed like check_placement does)."""
    rows = list(csv.DictReader(open(os.path.join(bl.PCB_DIR, "escape_plan.csv"), encoding="utf-8")))
    out = []
    for side in "SENW":
        tc = esc.t_of(side, *esc.CENTRE)
        seq, nets = [], {}
        for r in sorted((r for r in rows if r["side"] == side), key=lambda r: float(r["t_pin"])):
            tp = float(r["t_pin"])
            if r["role"] == "VIA":
                seq.append((r["pin"], "via", tp, tp))
                nets[r["pin"]] = r["net"]
            elif r["role"] in ("LANE", "PART") and r["t_planned"]:
                seq.append((r["pin"], "lane" if r["role"] == "LANE" else "link", tp, float(r["t_planned"])))
        ok, pos, _bad = esc.via_ring_fit(seq, tc - 7.45, tc + 7.45)
        for name, t in pos:
            if name in nets:
                x, y = esc.point(side, t, esc.VIA_RING)        # via centre on the ring (disk r 7.20-7.70)
                out.append({"x": x, "y": y, "net": nets[name]})
    return out


def export(board_file, policy=True):
    import pcbnew
    b = pcbnew.LoadBoard(board_file)
    nets = crit_nets()
    for n, d in nets.items():
        d["l4"] = policy and n in L4_ALLOWED
    pads, holes = [], []
    # deterministic (verifier L2 r3): the footprint order inside the .kicad_pcb file is not stable between rebuilds,
    # and the pad order decides the router's tie-breaks; everything is sorted by reference and pad number
    fps = {fp.GetReference(): fp for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference())}
    for ref, fp in fps.items():
        for p in fp.Pads():
            attr = p.GetAttribute()
            x, y = bl.to_board(p.GetPosition())
            if attr == pcbnew.PAD_ATTRIB_NPTH:
                r = pcbnew.ToMM(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2 + 0.25
                if ref in ("H1", "H2", "H3", "H4"):
                    r = 3.5                     # M3 keep-out circle 7 mm (layout.md §1)
                holes.append({"x": x, "y": y, "r": r})
                continue
            if not p.IsOnLayer(pcbnew.F_Cu):
                continue
            net = p.GetNetname() or "__nc_%s_%s" % (ref, p.GetNumber())
            pads.append({"ref": ref, "num": p.GetNumber(), "net": net,
                         "layers": "FB" if attr == pcbnew.PAD_ATTRIB_PTH else "F",
                         "poly": [[round(q[0], 4), round(q[1], 4)] for q in bl.pad_polygon(p)]})
        if ref.startswith("FID"):
            x, y = bl.to_board(fp.GetPosition())
            holes.append({"x": x, "y": y, "r": 1.0})      # 2 mm mask opening: no trace inside
    # U9: the fan band (r < 7.90 mm, neck-down 0.10/0.10) is checked with exact geometry by check_placement's escape
    # check (D-104); on a 0.05 mm grid its zero-slack 45 deg fans cannot be represented. The trial therefore starts
    # every critical lane at its planned gate point (escape_plan.csv t_planned, r 8.0 mm) and keeps the fan square
    # closed; nets whose pin is served by a ring-1 part on the same net (R47, R48, R51) start at that part's pad.
    plan = {int(r["pin"]): r for r in csv.DictReader(open(os.path.join(bl.PCB_DIR, "escape_plan.csv"),
                                                           encoding="utf-8"))}
    gate_pts = {}
    for pin, r in plan.items():
        if r["net"] not in nets:
            continue
        if r["role"] == "LANE" or r["role"] == "PAIR2":
            first = pin if r["role"] == "LANE" else [a for a, b in esc.PAIRS.items() if b == pin][0]
            tl = float(plan[first]["t_planned"])
            if first in esc.PAIRS:
                d = nets[r["net"]]
                off = (d["w"] + d["gap"]) / 2
                tl += -off if pin == first else off
            gate_pts[r["net"]] = (pin, esc.side_of(pin), tl)
    pads = [p for p in pads if not (p["ref"] == "U9" and p["net"] in nets)]
    pads.sort(key=lambda p: (p["ref"], p["num"], p["net"]))
    holes.sort(key=lambda h: (h["x"], h["y"]))
    for net, (pin, side, tl) in sorted(gate_pts.items()):
        x, y = esc.point(side, tl, esc.ROW_INNER + 0.10)
        pads.append({"ref": "GATE", "num": str(pin), "net": net, "layers": "F",
                     "poly": [[x - 0.06, y - 0.06], [x + 0.06, y - 0.06], [x + 0.06, y + 0.06], [x - 0.06, y + 0.06]]})
        nets[net]["start"] = "GATE.%d" % pin
    # breakout areas: within the pin fields of the 0.5 mm-pitch USB parts and connectors the pairs keep their class
    # clearance (0.15 mm), not the 0.76 mm "other nets" rule ([TI-HS] breakout <= 0.25 in from the package)
    breakout = []
    for ref, m in (("U11", 2.0), ("U1", 0.5), ("U2", 0.5), ("J3", 0.0), ("J4", 0.0)):
        bb = bl.courtyard_bbox(fps[ref])
        breakout.append([bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m])
    # the J3 approach: the 0R links R56-R59 and the jack pin field, where the pairs split and the RX/TX P/N swaps are
    # made by passing one line between the pads of the other line's 0R link (D-106 b)
    bbs = [bl.courtyard_bbox(fps[r]) for r in ("R56", "R57", "R58", "R59")]
    breakout.append([min(b[0] for b in bbs) - 0.5, min(b[1] for b in bbs) - 0.5, max(b[2] for b in bbs) + 0.5,
                     max(b[3] for b in bbs) + 0.5])
    bb = bl.courtyard_bbox(fps["J1"])
    breakout.append([bb[0], bb[1] - 1.5, bb[2], bb[1] + 2.5])
    # D-108 (b): link gaps (between the two pads of each ETH 0R link) closed to every net but the allowed one
    net_forbid = []
    for ref, allowed in sorted(LINK_GAP_ALLOWED.items() if os.environ.get("TRIAL_NO_SEP") != "1" else []):
        p1, p2 = [bl.pad_polygon(p) for p in fps[ref].Pads()][:2]
        bx = lambda pp: (min(q[0] for q in pp), min(q[1] for q in pp), max(q[0] for q in pp), max(q[1] for q in pp))
        a, c = bx(p1), bx(p2)
        if abs(a[0] - c[0]) > abs(a[1] - c[1]):        # horizontal part: gap in x
            r = [min(a[2], c[2]), min(a[1], c[1]), max(a[0], c[0]), max(a[3], c[3])]
        else:
            r = [min(a[0], c[0]), min(a[3], c[3]), max(a[2], c[2]), max(a[1], c[1])]
        net_forbid.append({"ref": ref, "rect": [round(v, 4) for v in r], "allowed": list(allowed)})
    # D-108 (c): SD card supply pocket. The VDD column J2.4 - C23 - C26 (between the J2.5 CLK and J2.3 CMD pads) is
    # closed to every other net, so VCC3V3_SD keeps its L1 path J2.4 -> C23.1 -> C26.1; VCC3V3_SD may not leave that
    # path with a via between C23.1 and J2.4 (its via to L4 sits north of C23, in the pocket or beyond).
    j5 = bl.pad_polygon([p for p in fps["J2"].Pads() if p.GetNumber() == "5"][0])
    j3 = bl.pad_polygon([p for p in fps["J2"].Pads() if p.GetNumber() == "3"][0])
    c26 = bl.courtyard_bbox(fps["C26"])
    c23 = bl.pad_polygon([p for p in fps["C23"].Pads() if p.GetNumber() == "1"][0])
    pocket = [round(max(q[0] for q in j5), 4), round(c26[1], 4), round(min(q[0] for q in j3), 4),
              round(min(q[1] for q in j5), 4)]
    net_forbid.append({"ref": "J2-VDD", "rect": pocket, "allowed": ["VCC3V3_SD"]})
    net_novia = {"VCC3V3_SD": [[pocket[0], round(min(q[1] for q in c23), 4), pocket[2], pocket[3] + 0.6]]}
    no_via = []
    for ref in NO_VIA_REFS:
        bb = bl.courtyard_bbox(fps[ref])
        no_via.append([round(bb[0] - 0.15, 4), round(bb[1] - 0.15, 4), round(bb[2] + 0.15, 4), round(bb[3] + 0.15, 4)])
    l4f = []
    for r in XGUARD:
        bb = bl.courtyard_bbox(fps[r])
        l4f.append([bb[0], bb[1], bb[2], bb[3]])
    order = []
    for cls in ORDER_CLASSES:
        for n in sorted(nets):
            if nets[n]["cls"] == cls and n not in order:
                order.append(n)
                if nets[n]["partner"] and nets[n]["partner"] in nets:
                    order.append(nets[n]["partner"])
    for n in nets:
        if n not in order:
            order.append(n)
    # neck-down region = the U9 fan band (r <= 7.90 mm from the centre, rule area U9_FAN, D-107)
    u9bb = (esc.CENTRE[0] - esc.ROW_INNER, esc.CENTRE[1] - esc.ROW_INNER, esc.CENTRE[0] + esc.ROW_INNER,
            esc.CENTRE[1] + esc.ROW_INNER)
    labels = []
    for ref in ("U9", "U10", "U11", "U2", "U1", "J1", "J2", "J3", "J4", "Y1", "Y2", "R47", "R48", "R55", "R56", "R57",
                "R58", "R59"):
        x, y = bl.to_board(fps[ref].GetPosition())
        labels.append([x, y, ref])
    geo = {"nets": nets, "order": order, "pads": pads, "holes": holes, "vias": via_ring_vias(fps["U9"]),
           "edges": [0.4, 79.6, 0.3, 79.7], "neck": list(u9bb), "xguard_refs": list(XGUARD), "l4_forbid": l4f,
           "labels": labels,
           "no_route_l1": [[esc.CENTRE[0] - esc.ROW_INNER, esc.CENTRE[1] - esc.ROW_INNER,
                            esc.CENTRE[0] + esc.ROW_INNER, esc.CENTRE[1] + esc.ROW_INNER]],
           "breakout": breakout, "net_forbid": net_forbid, "no_via": no_via,
           "net_novia": net_novia, "sd_pocket": pocket,
           "sep_pad_exempt": list(SEP_PAD_EXEMPT),
           "crop": {"south": [12, 40, 56, 80], "east": [38, 28, 64, 48], "west": [6, 12, 32, 36],
                    "sd": [8, 44, 30, 72], "usb": [30, 44, 56, 76]}}
    return geo


def run(board_file=None, policy=True, render=True, tag=None):
    board_file = board_file or bl.BOARD_FILE
    tag = tag or ("policy" if policy else "l1only")
    os.makedirs(OUT_DIR, exist_ok=True)
    geo = export(board_file, policy)
    gj = os.path.join(OUT_DIR, "geometry_%s.json" % tag)
    rj = os.path.join(OUT_DIR, "result_%s.json" % tag)
    with open(gj, "w") as fh:
        json.dump(geo, fh)
    cmd = [VENV_PY, "-I", MAZE, gj, rj]
    if render:
        cmd.append(os.path.join(bl.PCB_DIR, "renders", "trial_route_%s.png" % tag))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError("maze_route failed:\n" + p.stdout[-3000:])
    with open(rj) as fh:
        res = json.load(fh)
    res["log"] = p.stdout
    res["geo_nets"] = geo["nets"]
    res["sd_pocket"] = geo["sd_pocket"]
    return res


if __name__ == "__main__":
    bf = sys.argv[1] if len(sys.argv) > 1 else None
    for pol in (True, False):
        r = run(bf, policy=pol)
        print("=== layer policy D-106" if pol else "=== L1 only (information: where the forced crossings are)")
        print(r["log"])
