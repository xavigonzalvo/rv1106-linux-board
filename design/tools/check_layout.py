"""Gate TP-D7 self-check (Phase 7, layout constraints).
Usage:  design/.venv/bin/python -I design/tools/check_layout.py design
Reads project files (layout.md, layout/*.csv, schematic/out/{nets,parts}.csv, power_rails.csv) and, through
courtyard.py, the cached KiCad footprints in refs/kicad-footprints-* (parsed as text; run with python -I).
Gate text (PLAN.md Phase 7): "every high-speed/sensitive net has a rule; trace widths computed for the stackup;
checklist ready for the human DRC review". Checks:
  L1  every netlist net has exactly one net class, and every class has a row in layout.md §4.1
  L2  an independent list of high-speed/sensitive patterns (written here, not imported from layout_calc.py) never lands
      in DEFAULT, and each such net's class carries a non-empty rule (length / other)
  L3  impedance: each diff class is within +-5 % of its target on both solver grids; solver validated vs Hammerstad
      within 2 %; layout.md §2 quotes the same widths/gaps
  L4  trace widths: every power-rail net of power_rails.csv is in a power class; chosen width >= IPC-2221 minimum on
      outer and inner layers (SW_NODE outer only); chosen >= JLCPCB minimum 0.09 mm; layout.md §3 quotes the widths
  L5  placement: every netlist part has a zone that exists in zones.csv; every part with a place_near hint has a
      distance rule; every SoC decoupler names its pin
  L6  geometry: board >= 70 x 70 (80 x 80, D-84 r2) stated in layout.md; connectors, holes, fiducials and zones inside the
      board and not overlapping; connector rectangles recomputed from the cached .kicad_mod courtyard at the stated
      origin/rotation, pads inside the board, body front on the mating edge; rails west/east; capacity: KiCad courtyard
      area per zone <= 55 % (Z-PWRIN, Z-NAND, Z-USBA-PWR >= 2 x their courtyards), whole board <= 55 %; connector
      rectangles hold only their connector; floor-plan length estimates (lengths.csv) recomputed and within the
      ETH/USB/SDMMC/FSPI limits
      L3 plane plan (planes.csv, round 3): the VDD_0V9 island holds every VDD_0V9/VDD_ARM SoC escape via with >= 1 mm
      margin; regions of different nets >= 0.3 mm apart, same-net regions connected; neck >= 3 mm level with the U4
      cell and reaching JP1; VCC5V0_SYS covers Z-PWRIN, the Z-PMU VIN side and U8 pin 5; VCC_3V3 holds R30 and is
      <= 7 mm from every SoC VCC_3V3 pin; VBUS_USBA reaches both J4 pin-1 candidates; VDD_0V9 drop recomputed and
      quoted once; U8 -> J4 pin 1 <= 15 mm; no MLCC zone within 3 mm of the V-cuts
  L7  layout.md contains each required section and the DRC checklist items (stackup, fiducials, rails, holes, thermal
      vias, impedance, ...)"""
import argparse, csv, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from designdir import design_dir  # noqa: E402
import courtyard as cy  # noqa: E402

FILL_MAX = 0.55

ok, err = [], []


def chk(c, m):
    (ok if c else err).append(m)


def rd(p):
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


SENSITIVE = {  # independent of layout_calc.py NET_RULES
    r"^ETH_(TX|RX)": "ETH_DIFF", r"^USB[AC]?_D[PM]$": "USB_DIFF", r"^(OSC|RTC)_X": "XTAL",
    r"^SDMMC_(CLK|CLK_SD|CMD|D[0-3])$": "SDMMC", r"^FSPI_": "FSPI", r"^U[0-9]+_SW$": "SW_NODE", r"_FB$": "SENSE",
    r"^(DRAM_ZQ|ETH_EXTR|CODEC_VCM|USBA_ISET|ONOFF_PDT|SARADC_IN1|RECOVERY|USB_DET_IN|NPOR|QPWR_G)$": "SENSE",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", type=design_dir)
    D = ap.parse_args().design
    L = os.path.join(D, "layout")
    md = open(os.path.join(D, "layout.md")).read()
    nets = rd(os.path.join(D, "schematic", "out", "nets.csv"))
    parts = rd(os.path.join(D, "schematic", "out", "parts.csv"))
    nc = rd(os.path.join(L, "netclasses.csv"))
    z = rd(os.path.join(L, "impedance.csv"))
    tw = rd(os.path.join(L, "trace_widths.csv"))
    zones = rd(os.path.join(L, "zones.csv"))
    pl = rd(os.path.join(L, "placement.csv"))
    rails = rd(os.path.join(D, "power_rails.csv"))
    lens = rd(os.path.join(L, "lengths.csv"))
    global soc_xy
    u9 = next(r for r in rd(os.path.join(L, "placement.csv")) if r["ref"] == "U9")
    c = re.search(r"centre \(([\d.]+), ([\d.]+)\)", u9["rule"])
    SC = (float(c.group(1)), float(c.group(2)))

    def soc_xy(n):  # independent of layout_calc: [DS] Fig. 2-3/2-4, footprint rotated +90 deg, pitch 0.35, pad centre 6.075
        k = (n - 1) % 32; o = -5.425 + k * 0.35
        return {0: (SC[0] + o, SC[1] + 6.075), 1: (SC[0] + 6.075, SC[1] - o), 2: (SC[0] - o, SC[1] - 6.075),
                3: (SC[0] - 6.075, SC[1] + o)}[(n - 1) // 32]

    # L1
    by = {}
    for r in nc: by.setdefault(r["net"], []).append(r["netclass"])
    names = [n["net"] for n in nets]
    chk(sorted(by) == sorted(names), f"L1 netclasses.csv covers exactly the {len(names)} netlist nets")
    chk(all(len(v) == 1 for v in by.values()), "L1 each net has exactly one class")
    sec41 = md.split("### 4.1", 1)[1].split("###", 1)[0] if "### 4.1" in md else ""
    for c in sorted({r["netclass"] for r in nc}):
        chk(f"`{c}`" in sec41, f"L1 class {c} has a row in layout.md §4.1")
    # L2
    cls_rule = {r["netclass"]: (r["length_rule"], r["other_rule"]) for r in nc}
    hits = 0
    for n in names:
        for rx, want in SENSITIVE.items():
            if re.search(rx, n):
                hits += 1
                got = by[n][0]
                chk(got == want, f"L2 sensitive net {n} -> {got} (expected {want})")
                chk(any(cls_rule[got]), f"L2 class {got} of {n} has a length/other rule")
                break
    chk(hits >= 45, f"L2 {hits} high-speed/sensitive nets found and checked")
    for r in nc:
        if r["netclass"] in ("ETH_DIFF", "USB_DIFF"):
            chk(r["diff_gap_mm"] not in ("", None) and float(r["width_mm"]) > 0,
                f"L2 {r['net']} has a width and diff gap")
    # L3
    for r in z:
        if r["item"].startswith("validation"):
            chk(abs(float(r["z_ohm"]) / float(r["ref_ohm"]) - 1) < 0.02,
                f"L3 solver validation {r['item']}: {r['z_ohm']} vs closed form {r['ref_ohm']} (< 2 %)")
        if r["item"].endswith("chosen"):
            t = float(r["ref_ohm"]); zz = float(r["z_ohm"])
            fine = float(re.search(r"fine-grid \(h/84\) ([\d.]+)", r["note"]).group(1))
            chk(abs(zz / t - 1) <= 0.05 and abs(fine / t - 1) <= 0.05,
                f"L3 {r['item']}: Z {zz} / fine {fine} within +-5 % of {t}")
            w, s = float(r["w_mm"]), float(r["s_mm"])
            chk(f"{w:.3f} mm" in md and f"{s:.3f} mm" in md, f"L3 layout.md quotes {r['item']} w {w:.3f} mm / s {s:.3f} mm")
            chk(w >= 0.09 and s >= 0.09, f"L3 {r['item']} geometry >= JLCPCB 0.09 mm minimum")
    # L4
    pcls = {}
    for r in tw:
        for n in r["nets"].split(): pcls[n] = r
        o_ok = float(r["chosen_outer_mm"]) >= float(r["ipc_outer_min_mm"])
        i_ok = r["cls"] == "SW_NODE" or float(r["chosen_inner_mm"]) >= float(r["ipc_inner_min_mm"])
        chk(o_ok and i_ok, f"L4 {r['cls']} {r['design_a']} A: outer {r['chosen_outer_mm']} >= {r['ipc_outer_min_mm']}, "
                           f"inner {r['chosen_inner_mm'] or 'n/a'} >= {r['ipc_inner_min_mm']} mm")
        chk(f"`{r['cls']}`" in md and f"{float(r['chosen_outer_mm']):.2f} mm" in md,
            f"L4 layout.md §3 quotes {r['cls']} at {float(r['chosen_outer_mm']):.2f} mm")
    for rr in rails:
        chk(rr["rail"] in pcls, f"L4 rail {rr['rail']} has a power class")
        if rr["rail"] in pcls and rr.get("worst_a"):
            chk(float(pcls[rr["rail"]]["design_a"]) >= 1.3 * float(rr["worst_a"]) - 0.01 or rr["kind"] == "subrail",
                f"L4 rail {rr['rail']} design current >= 1.3 x worst {rr['worst_a']} A")
    # L5
    L5_MOVED = {"TP18": "D-116 d", "TP23": "D-115 a", "TP24": "D-116 d"}   # D-117 j
    zid = {r["zone"] for r in zones}
    pmap = {r["ref"]: r for r in pl}
    chk(sorted(pmap) == sorted(p["ref"] for p in parts), f"L5 placement.csv covers all {len(parts)} netlist parts")
    for p in parts:
        r = pmap.get(p["ref"])
        if not r: continue
        chk(r["zone"] in zid, f"L5 {p['ref']} zone {r['zone']} exists")
        if p["place_near"]:
            chk(re.search(r"<= ?[\d.]+ mm|within [\d.]+ mm", r["rule"]) is not None, f"L5 {p['ref']} ({p['place_near']}) has a distance rule")
        m = re.match(r"U_SOC pins? (\d+)", p["place_near"] or "")
        if m:
            chk(f"SoC pin {m.group(1)}" in r["target"], f"L5 {p['ref']} target names SoC pin {m.group(1)}")
        # round 3 (verifier P7 r2 minor 5): a part tied to a SoC pin or a ring sits in Z-SOC
        if "SoC pin" in r["target"] or re.search(r"ring [12]", r["rule"]) or p["ref"] in (
                "Y1", "Y2", "C76", "C77", "C78", "C79", "R50", "R51", "TP6", "TP31"):
            # L5F (D-117 j): ring-2 test pads that the routing phases moved out of Z-SOC carry their final zone and
            # the decision that moved them
            if p["ref"] in L5_MOVED:
                chk(r["zone"] != "Z-SOC" and L5_MOVED[p["ref"]] in r["target"],
                    f"L5 {p['ref']} moved out of Z-SOC by {L5_MOVED[p['ref']]} (zone {r['zone']}, recorded in target)")
            else:
                chk(r["zone"] == "Z-SOC", f"L5 {p['ref']} (SoC pin / ring / crystal part) is in Z-SOC (got {r['zone']})")
    # test-pad rules that name a net must name the pad's netlist net (round 3: TP6 is on OSC_XOUT)
    tpnet = {nd.split(".")[0]: n["net"] for n in nets for nd in n["nodes"].split() if nd.startswith("TP")}
    for r in pl:
        m = re.search(r"test pad on ([A-Z0-9_]+)", r["rule"])
        if m:
            chk(m.group(1) == tpnet.get(r["ref"]), f"L5 {r['ref']} rule net {m.group(1)} = netlist net {tpnet.get(r['ref'])}")
    # L6
    rect = {r["zone"]: (float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"]), r["kind"]) for r in zones}
    zrow = {r["zone"]: r for r in zones}
    b = rect["BOARD"]
    BW, BH = b[2] - b[0], b[3] - b[1]
    chk(b[0] == 0 and b[1] == 0 and BW >= 70 and BH >= 70, f"L6 board outline {BW:g} x {BH:g} mm >= Standard PCBA 70 x 70 (D-H2)")
    chk(f"{BW:g} × {BH:g} mm" in md and f"{BW + 10:g} × {BH:g} mm" in md, f"L6 layout.md states the board {BW:g} × {BH:g} mm "
        f"and the panel {BW + 10:g} × {BH:g} mm")
    solid = {k: v for k, v in rect.items() if v[4] in ("connector", "hole", "zone", "fiducial")}
    for k, v in solid.items():
        chk(v[0] >= -1e-9 and v[1] >= -1e-9 and v[2] <= BW + 1e-9 and v[3] <= BH + 1e-9, f"L6 {k} inside the board")
    ks = sorted(solid)
    for i, a in enumerate(ks):
        for c in ks[i + 1:]:
            A, B = solid[a], solid[c]
            ov = min(A[2], B[2]) - max(A[0], B[0]) > 1e-6 and min(A[3], B[3]) - max(A[1], B[1]) > 1e-6
            chk(not ov, f"L6 {a} and {c} do not overlap")
    for k, v in rect.items():  # rail fiducials / tooling holes inside the rails, >= 3 mm apart
        if v[4] in ("rail-fiducial", "rail-hole"):
            cx = (v[0] + v[2]) / 2
            chk(-5 < cx < 0 or BW < cx < BW + 5, f"L6 {k} sits in a rail")
    # connector rectangles = cached KiCad courtyard at the stated origin / rotation (clipped to the board); mating edge
    con = {k: r for k, r in zrow.items() if r["kind"] == "connector"}
    chk(sorted(con) == ["J1-USBC", "J2-SD", "J3-RJ45", "J4-USBA", "J5-HDR", "J6-UART"], "L6 six connector rectangles")
    for k, r in con.items():
        fp, ox, oy, rot = r["footprint"], float(r["origin_x"]), float(r["origin_y"]), float(r["rot_deg"])
        x0, y0, x1, y1 = cy.placed_rect(fp, ox, oy, rot)
        want = (max(x0, 0), max(y0, 0), min(x1, BW), min(y1, BH))
        chk(all(abs(p - q) < 0.01 for p, q in zip(want, rect[k][:4])),
            f"L6 {k} rectangle {rect[k][:4]} = courtyard of {fp} at ({ox}, {oy}) rot {rot:g} {tuple(round(v, 2) for v in want)}")
        chk(max(0, -y0, y1 - BH, -x0, x1 - BW) <= 0.5 + 1e-6, f"L6 {k} courtyard overhangs the board by <= 0.5 mm")
        if fp.startswith("board:"):
            chk(r["edge"] == "" or (r["edge"] == "S" and abs(want[3] - BH) < 1e-6) or (r["edge"] == "N" and abs(want[1]) < 1e-6),
                f"L6 {k} (custom, drawing-based) reaches the {r['edge'] or 'no'} edge")
            continue
        fb = cy.fab_bbox(fp)
        pe = cy.placed(cy.pad_extent(fp), ox, oy, rot)
        chk(pe[0] >= 0.3 and pe[1] >= 0.3 and pe[2] <= BW - 0.3 and pe[3] <= BH - 0.3,
            f"L6 {k} pads {pe} inside the board with >= 0.3 mm to the edge")
        if r["edge"]:
            f = cy.placed(fb, ox, oy, rot)
            got = f[1] if r["edge"] == "N" else f[3]
            chk(abs(got - (0 if r["edge"] == "N" else BH)) <= 0.1,
                f"L6 {k} body front (F.Fab) at y = {got} on the {r['edge']} edge (mouth faces outward at rot {rot:g})")
    for k in ("J1-USBC", "J2-SD", "J4-USBA", "J3-RJ45"):
        chk(zrow[k]["edge"] in ("N", "S"), f"L6 {k} is an edge connector on the north/south edge (no rail overhang)")
        chk(rect[k][0] > 0.4 and rect[k][2] < BW - 0.4, f"L6 {k} keeps >= 0.4 mm from the V-cut edges")
    rw = [k for k, v in rect.items() if v[4] == "rail"]
    chk(sorted(rw) == ["RAIL-E", "RAIL-W"] and rect["RAIL-W"][2] == 0 and rect["RAIL-E"][0] == BW,
        f"L6 rails on the west and east edges (5 mm, V-cut at x = 0 / {BW:g}); no edge connector on those edges")
    # capacity: KiCad courtyard area of the parts assigned to a zone <= 55 % of the zone (routing room), board <= 55 %
    area = {}
    for r in pl:
        area[r["zone"]] = area.get(r["zone"], 0.0) + cy.courtyard_area(r["footprint"])
    for k, v in rect.items():
        if v[4] == "zone":
            za = (v[2] - v[0]) * (v[3] - v[1])
            f = area.get(k, 0.0) / za
            chk(f <= FILL_MAX, f"L6 {k}: courtyards {area.get(k, 0):.1f} mm2 / zone {za:.1f} mm2 = {100 * f:.1f} % <= {100 * FILL_MAX:.0f} %")
            chk(abs(float(zrow[k]["fill_pct"]) - 100 * f) < 0.1, f"L6 {k} fill in zones.csv matches the recomputed value")
            chk(area.get(k, 0) > 0, f"L6 zone {k} is used")
    for k in ("Z-PWRIN", "Z-NAND", "Z-USBA-PWR"):  # verifier P7 r1 fix (c): >= 2 x their courtyard sum
        v = rect[k]
        chk((v[2] - v[0]) * (v[3] - v[1]) >= 2 * area.get(k, 0), f"L6 {k} area >= 2 x its courtyard sum")
    tot = sum(area.values())
    chk(tot / (BW * BH) <= FILL_MAX, f"L6 whole board: courtyards {tot:.0f} mm2 = {100 * tot / (BW * BH):.1f} % of the board")
    for k, r in con.items():  # a connector rectangle holds only the connector
        refs = [p["ref"] for p in pl if p["zone"] == k]
        chk(len(refs) == 1 and refs[0].startswith("J"), f"L6 {k} holds only its connector ({', '.join(refs)})")
    # length estimates (layout_calc §5.5): recompute from the listed points; must meet the §4 class limit
    lim = {"ETH_DIFF": 30.0, "USB_DIFF": 50.0, "SDMMC": 40.0, "FSPI": 25.0}
    seen = set()
    for r in lens:
        pts = [tuple(float(v) for v in r["soc_xy"].split())]
        pts += [tuple(float(v) for v in h.split("@")[1].split(",")) for h in r["via"].split()]
        d = sum(max(abs(pts[i][0] - pts[i + 1][0]), abs(pts[i][1] - pts[i + 1][1])) +
                0.414 * min(abs(pts[i][0] - pts[i + 1][0]), abs(pts[i][1] - pts[i + 1][1])) for i in range(len(pts) - 1))
        est = d * float(r["detour"])
        pin = int(r["soc_pin"])
        chk(abs(est - float(r["est_mm"])) < 0.1 and float(r["detour"]) >= 1.2,
            f"L6 length estimate {r['path']}: {est:.1f} mm recomputed (detour {r['detour']})")
        chk(est <= lim[r["netclass"]] and float(r["limit_mm"]) == lim[r["netclass"]],
            f"L6 {r['path']} estimate {est:.1f} mm <= {r['netclass']} limit {lim[r['netclass']]:.0f} mm")
        sx, sy = pts[0]
        chk(abs(sx - soc_xy(pin)[0]) < 0.01 and abs(sy - soc_xy(pin)[1]) < 0.01, f"L6 {r['path']} starts at SoC pin {pin} pad")
        seen.add(r["netclass"])
    chk(seen == set(lim), "L6 length estimates exist for ETH, USB, SDMMC and FSPI")
    # L6 plane plan (round 3, verifier P7 r2 major)
    planes = rd(os.path.join(L, "planes.csv"))
    pr = [(q["net"], q["region"], float(q["x0"]), float(q["y0"]), float(q["x1"]), float(q["y1"])) for q in planes]
    chk(sorted({q[0] for q in pr}) == ["VBUS_USBA", "VCC5V0_SYS", "VCC_3V3", "VDD_0V9"], "L6 planes.csv has the four L3 nets")

    def inside(pt, q, m=0.0):
        return q[2] + m - 1e-9 <= pt[0] <= q[4] - m + 1e-9 and q[3] + m - 1e-9 <= pt[1] <= q[5] - m + 1e-9

    def gap(a, c):
        return max(c[2] - a[4], a[2] - c[4], c[3] - a[5], a[3] - c[5])  # > 0: separated by this much

    for q in pr:
        chk(q[2] >= 0.4 and q[3] >= 0.4 - 1e-9 and q[4] <= BW - 0.4 and q[5] <= BH - 0.4, f"L6 L3 {q[0]}/{q[1]} inside the board, >= 0.4 mm from the edges")
        for k, v in rect.items():
            if v[4] == "hole":
                chk(gap(q, (None, None) + v[:4]) >= 0, f"L6 L3 {q[0]}/{q[1]} clear of the {k} keep-out")
    for i, a in enumerate(pr):
        for c in pr[i + 1:]:
            if a[0] != c[0]:
                chk(gap(a, c) >= 0.3 - 1e-9, f"L6 L3 {a[0]}/{a[1]} and {c[0]}/{c[1]} do not overlap (gap {gap(a, c):.2f} >= 0.3 mm)")
    for net in {q[0] for q in pr}:  # same-net rectangles form one connected piece
        rs = [q for q in pr if q[0] == net]; seen_r = {0}; todo = [0]
        while todo:
            i = todo.pop()
            for j, c in enumerate(rs):
                if j not in seen_r and gap(rs[i], c) <= 1e-9 and min(rs[i][4], c[4]) - max(rs[i][2], c[2]) + min(rs[i][5], c[5]) - max(rs[i][3], c[3]) > 1.0:
                    seen_r.add(j); todo.append(j)
        chk(len(seen_r) == len(rs), f"L6 L3 {net}: its {len(rs)} rectangles are one connected region")
    isl = next(q for q in pr if q[1] == "ISLAND" and q[0] == "VDD_0V9")
    rail_pins = {n["net"]: sorted(int(x.split(".")[1]) for x in n["nodes"].split() if x.startswith("U9.") and x.split(".")[1].isdigit())
                 for n in nets}

    def esc(n):  # independent: escape via 1.0 mm outside the pad toe (6.45 mm) on the pad's own line
        x, y = soc_xy(n); side = (n - 1) // 32
        return {0: (x, SC[1] + 7.45), 1: (SC[0] + 7.45, y), 2: (x, SC[1] - 7.45), 3: (SC[0] - 7.45, y)}[side]

    for net in ("VDD_0V9", "VDD_ARM"):
        for n in rail_pins[net]:
            chk(inside(esc(n), isl, 0.99), f"L6 VDD_0V9 island {isl[2:]} holds the {net} pin {n} escape via {tuple(round(v, 2) for v in esc(n))} with >= 1 mm margin")
    chk(len(rail_pins["VDD_0V9"]) >= 9 and rail_pins["VDD_ARM"] == [115], "L6 VDD_0V9 has >= 9 SoC pins and VDD_ARM is pin 115")
    chk(abs((isl[2] + isl[4]) / 2 - SC[0]) < 0.5 and abs((isl[3] + isl[5]) / 2 - SC[1]) < 0.5, "L6 VDD_0V9 island centred on U9")
    neck = next(q for q in pr if q[1] == "NECK" and q[0] == "VDD_0V9")
    jp1 = tuple(map(float, re.search(r"centre \(([\d.]+), ([\d.]+)\)", pmap["JP1"]["rule"]).groups()))
    u4 = tuple(map(float, re.search(r"cell y ([\d.]+)-([\d.]+)", pmap["U4"]["rule"]).groups()))
    chk(neck[5] - neck[3] >= 3.0, f"L6 VDD_0V9 neck {neck[5] - neck[3]:g} mm wide >= 3 mm")
    chk(abs(neck[2] - isl[4]) < 1e-6 and isl[3] <= neck[3] and neck[5] <= isl[5], "L6 VDD_0V9 neck starts on the island's east edge")
    chk(inside(jp1, neck) and pmap["JP1"]["zone"] == "Z-PMU", f"L6 JP1 {jp1} (Z-PMU) sits over the neck")
    chk(u4[0] <= neck[3] and neck[5] <= u4[1], f"L6 U4 cell y {u4[0]:g}-{u4[1]:g} is level with the neck y {neck[3]:g}-{neck[5]:g}")
    v5 = [q for q in pr if q[0] == "VCC5V0_SYS"]
    zp, zm = rect["Z-PWRIN"], rect["Z-PMU"]
    chk(any(q[2] <= zp[0] and q[3] <= zp[1] and q[4] >= zp[2] and q[5] >= zp[3] for q in v5), "L6 VCC5V0_SYS covers all of Z-PWRIN (Q1 output)")
    chk(any(q[3] <= zm[1] and q[5] >= zm[3] and q[4] >= zm[2] and q[2] <= zm[0] + 3.5 for q in v5),
        "L6 VCC5V0_SYS covers the Z-PMU VIN side (full height, all but the <= 3.5 mm west link strip)")
    u8 = tuple(map(float, re.search(r"centre \(([\d.]+), ([\d.]+)\)", pmap["U8"]["rule"]).groups()))
    chk(any(inside((u8[0] + 1.1375, 59.5), q) for q in v5) and u8[1] - 1.7 - 59.5 >= 0, f"L6 VCC5V0_SYS holds the U8 pin 5 via north of U8 {u8}")
    v33 = [q for q in pr if q[0] == "VCC_3V3"]
    r30 = tuple(map(float, re.search(r"at \(([\d.]+), ([\d.]+)\)", pmap["R30"]["rule"]).groups()))
    chk(any(inside(r30, q) for q in v33), f"L6 VCC_3V3 region holds the R30 feed {r30}")
    for n in rail_pins["VCC_3V3"]:
        x, y = soc_xy(n)
        d = min(math.hypot(max(q[2] - x, 0, x - q[4]), max(q[3] - y, 0, y - q[5])) for q in v33)
        chk(d <= 7.0, f"L6 SoC VCC_3V3 pin {n}: L1 transfer to the VCC_3V3 region {d:.1f} mm <= 7 mm")
    vb = [q for q in pr if q[0] == "VBUS_USBA"]
    j4 = rect["J4-USBA"]; jc = (j4[0] + j4[2]) / 2
    cands = [(jc - 3.5, j4[1] + 1.5), (jc + 3.5, j4[1] + 1.5)]  # 7.0 mm outer pin pitch (drawing); VBUS side UNVERIFIED
    p1 = (u8[0] - 1.1375, u8[1] - 0.95)
    for c in cands:
        chk(any(inside(c, q, 1.0) for q in vb), f"L6 VBUS_USBA pour reaches J4 pin-1 candidate {c}")
        dd = (max(abs(c[0] - p1[0]), abs(c[1] - p1[1])) + 0.414 * min(abs(c[0] - p1[0]), abs(c[1] - p1[1]))) * 1.2
        chk(dd <= 15.0, f"L6 VBUS_USBA U8 pin 1 -> J4 pin 1 candidate {c}: {dd:.1f} mm <= 15 mm (D-81)")
    chk(pmap["U8"]["zone"] == "Z-USB", "L6 U8 is assigned to Z-USB")
    zu = rect["Z-USB"]
    chk(zu[0] <= u8[0] - 2.05 and u8[0] + 2.05 <= zu[2] and zu[1] <= u8[1] - 1.7 and u8[1] + 1.7 <= zu[3], f"L6 U8 courtyard at {u8} inside Z-USB")
    # VDD_0V9 drop, recomputed: neck + island half-width + vias (6 at JP1, 4 at the SoC), 0.5 oz L3, rho 1.72e-8
    ppth = rd(os.path.join(L, "power_paths.csv"))
    rho, t3 = 1.72e-8, 0.0152e-3
    jvx = float(re.search(r"JP1 vias x ([\d.]+)", ppth[0]["path"]).group(1))
    chk(neck[2] < jvx < neck[4], "L6 JP1 via group inside the neck")
    rv = rho * 1.3256e-3 / (math.pi * (0.168 ** 2 - 0.15 ** 2) * 1e-6)
    rt = rho * (jvx - neck[2]) * 1e-3 / (t3 * (neck[5] - neck[3]) * 1e-3) + rho * (isl[4] - SC[0]) * 1e-3 / (t3 * (isl[5] - isl[3]) * 1e-3) + rv / 6 + rv / 4
    w09 = next(float(r["worst_a"]) for r in rails if r["rail"] == "VDD_0V9")
    mv = rt * w09 * 1e3
    chk(abs(mv - float(ppth[0]["value"])) < 0.1, f"L6 VDD_0V9 drop recomputed {mv:.1f} mV = power_paths.csv {ppth[0]['value']}")
    s45 = md.split("### 4.5", 1)[1].split("###", 1)[0]
    chk(f"≈ {float(ppth[0]['value']):.1f} mV" in s45 and "≤ 2 mV" not in md and "15 mm long" not in md,
        f"L6 layout.md §4.5 quotes one VDD_0V9 drop figure ({float(ppth[0]['value']):.1f} mV)")
    s23 = md.split("### 2.3", 1)[1].split("## 3.", 1)[0]
    for q in pr:
        chk(f"x {q[2]:g}–{q[4]:g}, y {q[3]:g}–{q[5]:g}" in s23, f"L6 layout.md §2.3 quotes L3 {q[0]}/{q[1]} x {q[2]:g}–{q[4]:g}, y {q[3]:g}–{q[5]:g}")
    for r in ppth[1:]:
        chk(float(r["value"]) <= 15.0, f"L6 power_paths.csv {r['path']}: {r['value']} mm <= 15 mm")
    # MLCCs keep 3 mm from the V-cuts (round 3, verifier P7 r2 minor 3)
    for k, v in rect.items():
        if v[4] == "zone" and any(r["zone"] == k and r["footprint"].startswith("Capacitor_SMD:C_") for r in pl):
            chk(v[0] >= 3.0 and v[2] <= BW - 3.0, f"L6 {k} (holds MLCCs) keeps >= 3 mm from the V-cuts (x {v[0]:g}-{v[2]:g})")
    # L7
    need = ["## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8.", "## 9.", "## 10.",
            "JLC04161H-7628", "80 × 80 mm", "90 × 80 mm", "V-cut", "fiducial", "tooling hole", "M3", "ENIG",
            "thermal via", "windowpane", "0.35 mm", "edge rail", "TP-D7", "IPC-2221", "SPRAAR7J", "DRC checklist",
            "Standard PCBA", "board.kicad_dru", "UNVERIFIED", "0.10 mm stencil", "summed by hand", "within_diff_pairs",
            "courtyard", "lengths.csv", "rotation 0°"]
    for s in need:
        chk(s in md, f"L7 layout.md mentions '{s}'")
    dru = open(os.path.join(L, "board.kicad_dru")).read()
    chk(dru.count("(within_diff_pairs)") == 2 and "(constraint skew (max 1.27mm))" not in dru,
        "L7 board.kicad_dru: both skew constraints are within_diff_pairs")
    chk("NPTH" not in dru and re.search(r'\(rule "edge clearance"\s*\(constraint edge_clearance \(min 0\.40mm\)\)\)', dru),
        "L7 board.kicad_dru: plain 0.40 mm edge clearance rule, no invalid Type test")
    for cls, crt in (("ETH_DIFF", ["U9"]), ("USB_DIFF", ["U9", "J1", "U1", "U2", "U11"])):
        m = re.search(r"\(condition \"(A\.NetClass == '" + cls + r"' && A\.Type == 'track'[^\"]*)\"\)\s*\(constraint clearance \(min 0\.76mm\)\)", dru)
        chk(m is not None and "B.Type == 'track'" in m.group(1) and all(f"!A.intersectsCourtyard('{c}')" in m.group(1) for c in crt),
            f"L7 board.kicad_dru: {cls} 0.76 mm rule applies to tracks only, outside {', '.join(crt)}")
    # round 3 (verifier P7 r2 minor 1): U9 pad-pad rule; sense/XTAL vs SW rule tracks/zones only, outside U4-U7
    m = re.search(r'\(rule "U9 pads"\s*\(condition "([^"]*)"\)\s*\(constraint clearance \(min ([\d.]+)mm\)\)\)', dru)
    chk(m is not None and "A.Type == 'pad' && B.Type == 'pad'" in m.group(1) and "A.memberOfFootprint('U9')" in m.group(1)
        and "B.memberOfFootprint('U9')" in m.group(1) and 0.15 <= float(m.group(2)) <= 0.16 and dru.rfind('"U9 pads"') > dru.rfind('"sense nets'),
        "L7 board.kicad_dru: U9 pad-to-pad clearance 0.15 mm rule, after the class rules")
    m = re.search(r'\(rule "sense nets away from switch nodes"\s*\(condition "([^"]*)"\)\s*\(constraint clearance \(min 2\.0mm\)\)\)', dru)
    chk(m is not None and "A.Type != 'pad'" in m.group(1) and all(f"!A.intersectsCourtyard('U{i}')" in m.group(1) for i in (4, 5, 6, 7)),
        "L7 board.kicad_dru: sense/XTAL vs SW_NODE 2.0 mm rule excludes pads and the U4-U7 courtyards")
    # one XTAL length budget: DRU per net = netclasses.csv per net = layout.md §4.1 / §4.3
    want = {"OSC_XIN": 5, "OSC_XOUT_X": 5, "OSC_XOUT": 8, "RTC_XIN": 6, "RTC_XOUT": 6}
    for net, mm in want.items():
        rr = re.findall(r'\(condition "([^"]*)"\)\s*\(constraint length \(max (\d+)mm\)\)', dru)
        got = [int(x[1]) for x in rr if f"A.NetName == '{net}'" in x[0]]
        chk(got == [mm], f"L7 board.kicad_dru: {net} length rule {got} = [{mm}] mm")
        ncr = next(r for r in nc if r["net"] == net)
        chk(f"{net} <= {mm} mm" in ncr["length_rule"], f"L7 netclasses.csv {net} length rule says <= {mm} mm")
    chk("A.NetClass == 'XTAL'\")\n  (constraint length" not in dru, "L7 board.kicad_dru: no class-wide XTAL length rule left")
    s41 = sec41
    chk(all(t in s41 for t in ("OSC_XIN, OSC_XOUT_X ≤ 5 mm", "OSC_XOUT ≤ 8 mm", "RTC_XIN, RTC_XOUT ≤ 6 mm")), "L7 layout.md §4.1 XTAL row has the per-net budget")
    s43 = md.split("### 4.3", 1)[1].split("###", 1)[0]
    chk(all(t in s43 for t in ("≤ 5 mm", "≤ 8 mm", "≤ 6 mm", "TP6 stub ≤ 3 mm")), "L7 layout.md §4.3 states the same crystal budget")
    for t in ("no MLCC within 3 mm", "parallel to", "depaneling", "planes.csv", "power_paths.csv"):
        chk(t in md, f"L7 layout.md mentions '{t}'")
    items = re.findall(r"^- \[ \] ", md, re.M)
    chk(len(items) >= 30, f"L7 DRC checklist has {len(items)} tick-box items (>= 30)")

    for m in ok: print("PASS", m) if os.environ.get("VERBOSE") else None
    for m in err: print("FAIL", m)
    print(f"check_layout: {len(ok)} pass, {len(err)} fail")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    main()
