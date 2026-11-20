"""Layout phase L5G checks (TP-L5G, owner decision D-H7 / D-119..D-127), called by check_routing.py on every board that
carries the L5 groups (like l5fcheck.py). Every measurable D-H7 item has a FAIL-capable line (mutations: mutate_l5g.py):

  L5G-ep     U9 EP: no drilled footprint pad left in U9; 16 GND board vias 0.5 / 0.3 inside pad 129; board setup via
             filling + capping (IPC-4761 type VII) on; kicad-cli Excellon export: no 0.3 mm ComponentDrill tool, the
             0.3 mm ViaDrill tool holds every board via; every EP paste window edge >= 0.175 mm from the EP via holes
             (layout.md §6.2, check_footprints F2)
  L5G-silk   every visible F.SilkS reference / test-pad label / function label / pin marker nearer (ink box to copper)
             to its own part (pin markers: its own pad) than to any other part's copper by >= 0.20 mm, and within
             2.0 mm of it (3.0 mm for parts > 5 mm); no tooling-hole (TH*) text inside the board outline
             (l5g_silklib.py); labels hidden for want of a spot are counted (INFO)
  L5G-sd     SDMMC_CLK / SDMMC_CLK_SD: no same-layer side-by-side run > 2.0 mm with an edge gap < 0.30 mm to any other
             SD / NAND (SDMMC_*, FSPI_*) track; SD lengths <= 40 mm and within +-5 mm of the clock (R48 summed)
  L5G-rtc    RTC_XIN / RTC_XOUT, outside the U9 pin escape (<= 1.5 mm from the U9 pads): edge gap to every other
             signal track (GND excluded) >= 0.5 mm, no exemption (round 2, D-128: C58 moved 0.175 mm east);
             RTC_XOUT - SDMMC_D2 >= 0.5 mm everywhere, the escape included; XIN-XOUT side-by-side run < 0.5 mm
             <= 2.0 mm outside the escape
  L5G-runs   the run sets of L5G-sd / L5G-rtc do not change when the track order / segment directions are reversed
  L5G-tht    every power-net (PWR_* / GND class) track that ends on a THT pad reaches the pad centre (<= 0.05 mm) or
             its copper overlaps the pad by >= half the track width (depth along the track)
  L5G-hole   every via hole edge >= 0.45 mm from every PTH / NPTH / slot hole edge (JLC), minimum reported
  L5G-hop    every In2 GND hop island (zone In2_GND_HOP_*) holds >= 2 GND vias
  L5G-q1     Q1 drain (Q1.3, VCC5V0_SYS): >= 4 VCC5V0_SYS vias within 1.0 mm of the pad (centre to pad edge)
  L5G-pair   USB / ETH pairs (KiCad DRC does not pair *_DP/*_DM or *_J nets, layout.md §10): per pair length, P/N
             skew, length off the target gap, longest uncoupled run (report lines); FAIL only for an end-to-end P/N
             skew > 1.27 mm (layout.md §4.6/§4.7: ETH net + its _J segment; USB pad to pad through U11, l4check paths)
"""
import math
import os
import re
import subprocess
import tempfile

import boardlib as bl
import l5g_silklib as S
import l5glib as G

import pcbnew

MEAS = {}
SD_NETS = ("SDMMC_D0", "SDMMC_D1", "SDMMC_D2", "SDMMC_D3", "SDMMC_CMD", "SDMMC_DET", "SDMMC_PWREN")
CLK_NETS = ("SDMMC_CLK", "SDMMC_CLK_SD")
RTC = ("RTC_XIN", "RTC_XOUT")
PAIRS = (("USBC", "USBC_DP", "USBC_DM", 0.14, 0.16), ("USBA", "USBA_DP", "USBA_DM", 0.14, 0.16),
         ("USB (SoC-U11)", "USB_DP", "USB_DM", 0.14, 0.16), ("ETH TX", "ETH_TXP", "ETH_TXN", 0.19, 0.21),
         ("ETH RX", "ETH_RXP", "ETH_RXN", 0.19, 0.21), ("ETH TX magnetics side", "ETH_TXP_J", "ETH_TXN_J", 0.19, 0.21),
         ("ETH RX magnetics side", "ETH_RXP_J", "ETH_RXN_J", 0.19, 0.21))
SKEW_MAX = 1.27


def L(s):
    return math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])


# ------------------------------------------------------------------------------------------------------------ EP
def excellon(board_file):
    d = tempfile.mkdtemp(prefix="l5g_drl_")
    subprocess.run([bl.KICAD_CLI, "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                    "-o", d + "/", board_file],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tools = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".drl"):
            continue
        txt = open(os.path.join(d, fn), encoding="utf-8").read()
        cur = {}
        attr = None
        for line in txt.splitlines():
            m = re.match(r"; #@! TA\.AperFunction,(.*)", line)
            if m:
                attr = m.group(1)
            m = re.match(r"^T(\d+)C([\d.]+)", line)
            if m:
                cur[m.group(1)] = {"file": fn, "tool": "T%sC%s" % (m.group(1), m.group(2)), "dia": float(m.group(2)),
                                   "attr": attr or "", "holes": 0}
                attr = None
        t = None
        for line in txt.splitlines():
            m = re.match(r"^T(\d+)$", line)
            if m:
                t = m.group(1)
            elif t and re.match(r"^X[-\d.]+Y[-\d.]+", line) and t in cur:
                cur[t]["holes"] += 1
            elif t and line.startswith("G85") and t in cur:
                pass
        tools += list(cur.values())
    return tools


def check_ep(board, rec, vias):
    u9 = board.FindFootprintByReference("U9")
    drilled = [p for p in u9.Pads() if p.GetDrillSize().x > 0]
    ep = [p for p in u9.Pads() if p.GetNumber() == "129" and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD][0]
    poly = bl.pad_polygon(ep)
    inside = [v for v in vias if v[0] == "GND" and bl._inside(v[1], v[2], poly)]
    good = [v for v in inside if abs(pcbnew.ToMM(v[3].GetDrillValue()) - 0.3) < 1e-3 and
            abs(pcbnew.ToMM(v[3].GetWidth(pcbnew.F_Cu)) - 0.5) < 1e-3]
    rec("PASS" if not drilled and len(good) == 16 and len(inside) == 16 else "FAIL", "L5G-ep",
        "U9 EP: drilled footprint pads in U9 / GND board vias 0.5/0.3 inside pad 129 (D-H7 item 1)",
        "%d / %d (of %d vias inside)" % (len(drilled), len(good), len(inside)), "0 / 16")
    check_u9_lib(rec, u9)
    ds = board.GetDesignSettings()
    ok = bool(ds.m_FillVias) and bool(ds.m_CapVias)
    rec("PASS" if ok else "FAIL", "L5G-ep", "board setup via protection: filling / capping (IPC-4761 type VII, POFV)",
        "%s / %s" % ("yes" if ds.m_FillVias else "no", "yes" if ds.m_CapVias else "no"), "yes / yes")
    # paste windows vs the EP via holes
    paste = [bl.pad_polygon(p) if p.IsOnLayer(pcbnew.F_Cu) else _paste_poly(p) for p in u9.Pads()
             if p.IsOnLayer(pcbnew.F_Paste) and p.GetNumber() == ""]
    worst = 9.0
    for v in inside:
        r = pcbnew.ToMM(v[3].GetDrillValue()) / 2
        for q in paste:
            d = 0.0 if bl._inside(v[1], v[2], q) else min(
                bl._seg_pt(v[1], v[2], *q[i], *q[(i + 1) % len(q)]) for i in range(len(q)))
            worst = min(worst, d - r)
    rec("PASS" if paste and worst >= 0.175 - 1e-3 else "FAIL", "L5G-ep", "EP paste windowpane (%d windows) to the EP "
        "via holes, smallest edge gap" % len(paste), "%.3f mm" % worst, ">= 0.175 (layout.md §6.2)")
    MEAS["ep_paste_gap"] = round(worst, 3)
    try:
        tools = excellon(bl.BOARD_FILE)
    except Exception as e:      # noqa: BLE001
        rec("FAIL", "L5G-ep", "kicad-cli Excellon export", "error %s" % e, "")
        return
    comp03 = [t for t in tools if "ComponentDrill" in t["attr"] and abs(t["dia"] - 0.3) < 1e-3]
    via_t = [t for t in tools if "ViaDrill" in t["attr"]]
    nvia = sum(1 for v in vias if abs(pcbnew.ToMM(v[3].GetDrillValue()) - 0.3) < 1e-3)
    nhole = sum(t["holes"] for t in via_t if abs(t["dia"] - 0.3) < 1e-3)
    MEAS["excellon"] = tools
    rec("PASS" if not comp03 else "FAIL", "L5G-ep", "Excellon: 0.3 mm ComponentDrill tools (footprint via pads)",
        len(comp03), 0, " ".join("%s %s %d holes" % (t["file"], t["tool"], t["holes"]) for t in comp03))
    rec("PASS" if nhole == nvia and nvia >= 649 + 16 else "FAIL", "L5G-ep", "Excellon: holes in the 0.3 mm ViaDrill "
        "tool = board vias (L5F 649 + 16 EP + L5G extras)", "%d holes / %d vias" % (nhole, nvia), "equal, >= 665",
        " ".join("%s %s %s" % (t["file"], t["tool"], t["attr"]) for t in via_t))


U9_LIB = "RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm_EPboardvias"


def _pad_sig(fp, rel):
    out = []
    for p in fp.Pads():
        x, y = (pcbnew.ToMM(p.GetFPRelativePosition().x), pcbnew.ToMM(p.GetFPRelativePosition().y)) if rel else (
            pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
        out.append((p.GetNumber(), round(x, 4), round(y, 4), round(pcbnew.ToMM(p.GetSize().x), 4),
                    round(pcbnew.ToMM(p.GetSize().y), 4), round(pcbnew.ToMM(p.GetDrillSize().x), 4),
                    int(p.GetAttribute())))
    return sorted(out)


def check_u9_lib(rec, u9):
    """L5G round 2 (verifier minor, D-129): U9 points at the board.pretty variant without the 16 drilled pads, and its
    pads equal that library footprint (pad number, position relative to the footprint, size, drill, type), so an
    "update footprints from library" cannot bring the drilled pads back"""
    name = u9.GetFPID().GetLibItemName().wx_str()
    lib = pcbnew.FootprintLoad(os.path.join(bl.PCB_DIR, "board.pretty"), U9_LIB)
    same = lib is not None and _pad_sig(lib, False) == _pad_sig(u9, True)
    rec("PASS" if name == U9_LIB and same else "FAIL", "L5G-ep", "U9 footprint = board.pretty %s (pads equal, no "
        "drilled pads; no U9 library mismatch)" % U9_LIB, "%s, pads %s" % (name, "equal" if same else "DIFFER"),
        "variant, equal")


def _paste_poly(p):
    poly = pcbnew.SHAPE_POLY_SET()
    p.TransformShapeToPolygon(poly, pcbnew.F_Paste, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    o = poly.Outline(0)
    return [bl.to_board(o.CPoint(i)) for i in range(o.PointCount())]


# ---------------------------------------------------------------------------------------------------------- silk
def check_silk(board, rec):
    rows = S.evaluate(board)
    bad = [r for r in rows if not r[8]]
    MEAS["silk"] = [(r[0], r[1], r[2], r[3], [round(v, 2) for v in r[4]], r[5] and round(r[5], 3),
                     r[6] and (round(r[6][0], 3), r[6][1]), r[9]) for r in rows]
    parts = [r for r in rows if r[2] not in (None, "BOARD")]
    margin = min((r[6][0] - r[5] for r in parts if r[8]), default=0)
    rec("PASS" if not bad else "FAIL", "L5G-silk", "visible F.SilkS labels (%d: references, TP labels, function labels, "
        "pin markers) nearer own copper than any other part's by >= %.2f mm and within 2.0 / 3.0 mm (D-H7 item 2)" % (
            len(parts), S.MARGIN), "%d bad" % len(bad), 0, "; ".join("%r %s%s: %s" % (
                r[1], r[2], "." + r[3] if r[3] else "", r[9]) for r in bad[:8]))
    if parts:
        far = max(parts, key=lambda r: r[5] or 0)
        rec("INFO", "L5G-silk", "label to own copper, largest / smallest margin to the nearest other copper",
            "%.2f mm (%s %r) / %.2f mm" % (far[5], far[2], far[1], margin), "")
    th = []
    for r in rows:
        x0, y0, x1, y1 = r[4]
        if r[2] and r[2].startswith("TH") and x1 > 0 and x0 < 80 and y1 > 0 and y0 < 80:
            th.append("%s %r (%.2f, %.2f)" % (r[2], r[1], (x0 + x1) / 2, (y0 + y1) / 2))
    rec("PASS" if not th else "FAIL", "L5G-silk", "tooling-hole (TH*) texts on the board (x 0-80, y 0-80)", len(th), 0,
        "; ".join(th))
    hidden = [fp.GetReference() for fp in board.GetFootprints() if not fp.Reference().IsVisible() and
              not fp.GetReference().startswith(("TH", "H", "FID", "GFID", "TP", "LED"))]
    fab_lbl = [d.GetText().split("\n")[0] for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT" and
               d.GetLayer() == pcbnew.F_Fab and d.GetParentGroup() is not None and
               d.GetParentGroup().GetName() == "L5G_SILK"]
    rec("INFO", "L5G-silk", "references hidden on silk (kept on F.Fab; assembly drawing) / board labels moved to F.Fab "
        "by L5G", "%d / %d" % (len(hidden), len(fab_lbl)), "", " ".join(sorted(fab_lbl)))


# ------------------------------------------------------------------------------------------------------ SD / RTC
def check_sd(board, rec, segs):
    A = G.segs_of(board, CLK_NETS)
    others = [n for n in set(s[0] for s in segs) if (n.startswith("SDMMC_") or n.startswith("FSPI_")) and
              n not in CLK_NETS]
    B = G.segs_of(board, others)
    runs = G.side_runs(A, B, 0.30)
    MEAS["sd_clk_runs"] = [(r[0], r[1], round(r[3], 2), round(r[4], 3)) for r in runs[:10]]
    bad = [r for r in runs if r[3] > 2.0]
    gmin = min((r[4] for r in runs), default=None)
    rec("PASS" if not bad else "FAIL", "L5G-sd", "SD clock side-by-side runs > 2.0 mm with edge gap < 0.30 mm to "
        "another SD / NAND track (D-H7 item 3)", len(bad), 0, "longest < 0.30: %s" % (
            "; ".join("%s-%s %.2f mm at %.3f" % (r[0], r[1], r[3], r[4]) for r in (bad or runs)[:4]) or "none"))
    # gap to the neighbours along the bus (information)
    near = G.side_runs(A, B, 0.45)
    MEAS["sd_clk_near"] = [(r[0], r[1], round(r[3], 2), round(r[4], 3)) for r in near[:10]]
    rec("INFO", "L5G-sd", "SD clock nearest SD / NAND neighbours (runs with gap < 0.45 mm)",
        "; ".join("%s-%s %.2f mm at %.3f" % (r[0], r[1], r[3], r[4]) for r in near[:4]), "",
        "smallest gap of the short runs %.3f mm" % gmin if gmin is not None else "")
    lens = {}
    for s in segs:
        if s[0].startswith("SDMMC_") and s[1] in (pcbnew.F_Cu, pcbnew.B_Cu):
            lens[s[0]] = lens.get(s[0], 0) + L(s)
    clk = lens.get("SDMMC_CLK", 0) + lens.get("SDMMC_CLK_SD", 0)
    data = {n: lens.get(n, 0) for n in ("SDMMC_D0", "SDMMC_D1", "SDMMC_D2", "SDMMC_D3", "SDMMC_CMD")}
    MEAS["sd_lengths"] = {"CLK (R48 summed)": round(clk, 2), **{k: round(v, 2) for k, v in data.items()}}
    ok = clk <= 40 and all(v <= 40 and abs(v - clk) <= 5 for v in data.values())
    rec("PASS" if ok else "FAIL", "L5G-sd", "SD lengths (track length per net, CLK = SDMMC_CLK + SDMMC_CLK_SD)",
        "CLK %.2f; %s" % (clk, ", ".join("%s %.2f (%+.2f)" % (k[6:], v, v - clk) for k, v in data.items())),
        "<= 40, within +-5 of CLK (layout.md §4.4)")
    return [("sd", A, B, 0.30, None), ("sd_near", A, B, 0.45, None)]


def _in_box(x, y, b):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def u9_pad_zone(board, d=1.5):
    u9 = board.FindFootprintByReference("U9")
    xs, ys = [], []
    for p in u9.Pads():
        if p.GetNumber() and p.GetNumber() != "129":
            for q in bl.pad_polygon(p):
                xs.append(q[0])
                ys.append(q[1])
    return (min(xs) - d, min(ys) - d, max(xs) + d, max(ys) + d)


def _fmt_runs(runs, n=4, at=">="):
    return "; ".join("%s-%s %.2f mm at %s %.3f" % (r[0], r[1], r[3], at, r[4]) for r in runs[:n]) or "none"


def _runs_sig(runs):
    return [(r[0], r[1], r[2], round(r[3], 3), round(r[4], 3)) for r in runs]


def check_runs_stable(rec, cases):
    """L5G round 2 (verifier minor): the side-by-side run lengths must depend on the geometry only. Every run set the
    L5G-sd / L5G-rtc lines use is recomputed from the reversed track lists (file order reversed, every segment drawn
    the other way round); any difference FAILs."""
    diffs = []
    for name, A, B, gap, ex in cases:
        r1 = G.side_runs(A, B, gap, exempt=ex)
        rev = lambda L: [(s[0], s[1], s[3], s[2], s[4], s[5]) for s in reversed(L)]   # noqa: E731
        r2 = G.side_runs(rev(A), rev(B), gap, exempt=ex)
        if _runs_sig(r1) != _runs_sig(r2):
            diffs.append(name)
    rec("PASS" if not diffs else "FAIL", "L5G-runs", "side-by-side run sets (L5G-sd / L5G-rtc) identical when the track "
        "order and segment directions are reversed (geometry only)", "%d of %d differ" % (len(diffs), len(cases)), 0,
        ", ".join(diffs))


def check_rtc(board, rec, segs):
    zone = u9_pad_zone(board)
    ex = lambda x, y: _in_box(x, y, zone)   # noqa: E731
    A = G.segs_of(board, RTC)
    B = G.segs_of(board, [n for n in set(s[0] for s in segs) if n not in RTC and n != "GND" and n])
    runs = G.side_runs(A, B, 0.50, exempt=ex)
    MEAS["rtc_runs"] = [(r[0], r[1], round(r[3], 2), round(r[4], 3), [round(v, 2) for v in r[5]],
                         [round(v, 2) for v in r[6]]) for r in runs]
    # round 2 (D-128): no channel exemption any more; C58 moved 0.175 mm east so the whole route meets 0.5 mm
    rec("PASS" if not runs else "FAIL", "L5G-rtc", "RTC_XIN / RTC_XOUT edge gap to other signal tracks < 0.5 mm "
        "outside the U9 pin escape (<= 1.5 mm from the pads), no exemption (D-H7 item 4, D-128)",
        len(runs), 0, _fmt_runs(runs))
    near = G.side_runs(A, B, 0.60, exempt=ex)
    gmin = min((r[4] for r in near), default=None)
    rec("INFO", "L5G-rtc", "RTC nearest other signal tracks outside the escape (gap < 0.6 mm)", _fmt_runs(near), "",
        "smallest %.3f mm" % gmin if gmin is not None else "")
    # XOUT - D2 over the whole route, the pin escape included (verifier round 1 measured from the pin row)
    d2 = G.side_runs([s for s in A if s[0] == "RTC_XOUT"], G.segs_of(board, ["SDMMC_D2"]), 0.50)
    MEAS["rtc_xout_d2_all"] = [(round(r[3], 2), round(r[4], 3)) for r in d2]
    rec("PASS" if not d2 else "FAIL", "L5G-rtc", "RTC_XOUT - SDMMC_D2 edge gap < 0.5 mm anywhere, U9 pin escape "
        "included (D-H7 item 4)", len(d2), 0, _fmt_runs(d2))
    xo = [s for s in A if s[0] == "RTC_XOUT"]
    xi = [s for s in A if s[0] == "RTC_XIN"]
    pair = G.side_runs(xo, xi, 0.50, exempt=ex)
    MEAS["rtc_pair_runs"] = [(round(r[3], 2), round(r[4], 3), [round(v, 2) for v in r[5]], [round(v, 2) for v in r[6]])
                             for r in pair]
    longest = max((r[3] for r in pair), default=0.0)
    rec("PASS" if longest <= 2.0 else "FAIL", "L5G-rtc", "RTC_XIN-RTC_XOUT side-by-side run < 0.5 mm outside the pin "
        "escape (C58 pads + XTAL 0.30 mm clearance hold XIN beside XOUT down to y 46.3)",
        "%.2f mm (min gap %.3f)" % (longest, min((r[4] for r in pair), default=9)), "<= 2.0 (D-H7 item 4)")
    return [("rtc", A, B, 0.50, ex), ("rtc_near", A, B, 0.60, ex), ("rtc_pair", xo, xi, 0.50, ex)]


# ------------------------------------------------------------------------------------------------ THT power links
def check_tht(board, rec, segs):
    pclass = {}
    try:
        import routelib as rl
        R = rl.rules()
        pclass = {n: R[n][0] for n in R}
    except Exception:          # noqa: BLE001
        pass
    power = lambda n: n == "GND" or pclass.get(n, "").startswith("PWR")   # noqa: E731
    bad, n_ok = [], 0
    worst = (9.0, "")
    ends = {}
    for s in segs:            # track ends shared with another same-net track / via are joints, not pad joints
        for e in (s[2], s[3]):
            k = (s[0], s[1], round(e[0], 3), round(e[1], 3))
            ends[k] = ends.get(k, 0) + 1
    for v in board.GetTracks():
        if v.GetClass() == "PCB_VIA":
            x, y = bl.to_board(v.GetPosition())
            for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                k = (v.GetNetname(), lay, round(x, 3), round(y, 3))
                ends[k] = ends.get(k, 0) + 1
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or not power(p.GetNetname()):
                continue
            poly = bl.pad_polygon(p)
            c = bl.to_board(p.GetPosition())
            for s in segs:
                if s[0] != p.GetNetname() or not p.IsOnLayer(s[1]):
                    continue
                for e, o in ((s[2], s[3]), (s[3], s[2])):
                    w = s[4]
                    din = 0.0 if bl._inside(e[0], e[1], poly) else min(
                        bl._seg_pt(e[0], e[1], *poly[i], *poly[(i + 1) % len(poly)]) for i in range(len(poly)))
                    if din > w / 2 + 1e-6:
                        continue           # this end does not touch the pad
                    if ends.get((s[0], s[1], round(e[0], 3), round(e[1], 3)), 0) > 1:
                        continue           # the end continues into more copper (a joint, not the pad joint)
                    if bl._inside(o[0], o[1], poly):
                        continue           # the whole track lies on the pad
                    if math.hypot(e[0] - c[0], e[1] - c[1]) <= 0.05:
                        n_ok += 1
                        continue
                    # copper overlap depth along the track: from the pad edge crossing to the end + round cap
                    if bl._inside(e[0], e[1], poly):
                        lo, hi = 0.0, 1.0           # bisect the crossing on o -> e
                        for _ in range(30):
                            m = (lo + hi) / 2
                            q = (o[0] + (e[0] - o[0]) * m, o[1] + (e[1] - o[1]) * m)
                            lo, hi = (lo, m) if bl._inside(q[0], q[1], poly) else (m, hi)
                        depth = math.hypot(e[0] - o[0], e[1] - o[1]) * (1 - hi) + w / 2
                    else:
                        depth = w / 2 - din
                    name = "%s.%s %s (%.2f,%.2f) w %.2f" % (fp.GetReference(), p.GetNumber(), s[0], e[0], e[1], w)
                    if depth < worst[0]:
                        worst = (depth / w, name)
                    if depth < w / 2 - 1e-6:
                        bad.append("%s overlap %.3f" % (name, depth))
                    else:
                        n_ok += 1
    rec("PASS" if not bad else "FAIL", "L5G-tht", "power-net tracks ending on a THT pad: at the pad centre or "
        "overlapping it >= half the track width (D-H7 item 5)", "%d ok, %d short" % (n_ok, len(bad)), "0 short",
        "; ".join(bad[:4]) or "smallest overlap / width %.2f (%s)" % worst)


# ---------------------------------------------------------------------------------------------------------- holes
def check_holes(board, rec):
    hs = G.holes(board)
    vias = [h for h in hs if h[0] == "via"]
    pth = [h for h in hs if h[0] != "via"]
    worst, bad = (9.0, ""), []
    for v in vias:
        for h in pth:
            if abs(v[2][0] - h[2][0]) > 4 or abs(v[2][1] - h[2][1]) > 4:
                continue
            g = G.hole_gap(v, h)
            cand = (round(g, 6), "%s via (%.3f, %.3f) - %s" % (v[1], v[2][0], v[2][1], h[1]))
            if cand < worst:        # ties broken by the text: independent of the file order (round 2)
                worst = cand
            if g < 0.45 - 1e-4:
                bad.append("%s via (%.3f, %.3f) - %s %.3f" % (v[1], v[2][0], v[2][1], h[1], g))
    MEAS["via_pth_hole_min"] = (round(worst[0], 3), worst[1])
    rec("PASS" if not bad else "FAIL", "L5G-hole", "via hole edge to PTH / NPTH / slot hole edge (%d vias, %d holes)" % (
        len(vias), len(pth)), "min %.3f mm (%s)" % worst, ">= 0.45 (JLC; D-H7 item 6)", "; ".join(bad[:4]))


# ---------------------------------------------------------------------------------------------------- hop / Q1
def check_hops(board, rec, vias):
    rows, bad = [], []
    for z in sorted(board.Zones(), key=lambda z: z.GetZoneName()):
        if not z.GetZoneName().startswith("In2_GND_HOP"):
            continue
        o = z.Outline().Outline(0)
        poly = [bl.to_board(o.CPoint(i)) for i in range(o.PointCount())]
        n = sum(1 for v in vias if v[0] == "GND" and bl._inside(v[1], v[2], poly))
        rows.append("%s %d" % (z.GetZoneName(), n))
        if n < 2:
            bad.append(z.GetZoneName())
    rec("PASS" if rows and not bad else "FAIL", "L5G-hop", "GND vias in every In2 GND hop island (D-H7 item 7)",
        ", ".join(rows), ">= 2 each")


def check_q1(board, rec, vias):
    p = [q for q in board.FindFootprintByReference("Q1").Pads() if q.GetNumber() == "3"][0]
    poly = bl.pad_polygon(p)
    near = []
    for v in vias:
        if v[0] != p.GetNetname():
            continue
        d = 0.0 if bl._inside(v[1], v[2], poly) else min(
            bl._seg_pt(v[1], v[2], *poly[i], *poly[(i + 1) % len(poly)]) for i in range(len(poly)))
        if d <= 1.0:
            near.append("(%.2f, %.2f)" % (v[1], v[2]))
    rec("PASS" if len(near) >= 4 else "FAIL", "L5G-q1", "Q1 drain (Q1.3 %s): vias within 1.0 mm of the pad (D-H7 "
        "item 8)" % p.GetNetname(), "%d: %s" % (len(near), " ".join(sorted(near))), ">= 4")


# --------------------------------------------------------------------------------------------------------- pairs
def coupling(ps, ns, lo, hi, step=0.05):
    """sample the P line; on target where the nearest same-layer N track's edge gap is within [lo, hi] (mitred
    corners: +-0.03 mm within 0.25 mm of a segment end). Returns (length, off-target length, longest off run)."""
    pts = []
    tot = off = 0.0
    for s in ps:
        Ls = L(s)
        n = max(1, int(Ls / step))
        for k in range(n):
            t = (k + 0.5) / n
            q = (s[2][0] + (s[3][0] - s[2][0]) * t, s[2][1] + (s[3][1] - s[2][1]) * t)
            tot += Ls / n
            g = min((bl._seg_pt(q[0], q[1], m[2][0], m[2][1], m[3][0], m[3][1]) - (s[4] + m[4]) / 2 for m in ns
                     if m[1] == s[1]), default=9.0)
            near_v = min(math.hypot(q[0] - c[0], q[1] - c[1]) for c in (s[2], s[3]))
            okk = lo - 1e-6 <= g <= hi + 1e-6 or (near_v < 0.25 and lo - 0.03 <= g <= hi + 0.03)
            if not okk:
                off += Ls / n
                pts.append((q, Ls / n))
    # longest connected off-target run (samples within 1.6 steps of each other)
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    grid = {}
    for i, (q, _l) in enumerate(pts):
        grid.setdefault((int(q[0] / 0.1), int(q[1] / 0.1)), []).append(i)
    for i, (q, _l) in enumerate(pts):
        gx, gy = int(q[0] / 0.1), int(q[1] / 0.1)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), []):
                    if j > i and math.hypot(pts[j][0][0] - q[0], pts[j][0][1] - q[1]) <= step * 1.6:
                        parent[find(j)] = find(i)
    runs = {}
    for i, (_q, ll) in enumerate(pts):
        runs[find(i)] = runs.get(find(i), 0) + ll
    return tot, off, max(runs.values(), default=0.0)


def check_pairs(board, rec, segs, vias):
    tot = {}
    for s in segs:
        if s[1] in (pcbnew.F_Cu, pcbnew.B_Cu):
            tot[s[0]] = tot.get(s[0], 0) + L(s)
    MEAS["pairs"] = {}
    for name, p, n, lo, hi in PAIRS:
        ps = [s for s in segs if s[0] == p and s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
        ns = [s for s in segs if s[0] == n and s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
        t, off, run = coupling(ps, ns, lo, hi)
        sk = tot.get(p, 0) - tot.get(n, 0)
        MEAS["pairs"][name] = {"P": round(tot.get(p, 0), 2), "N": round(tot.get(n, 0), 2), "skew": round(sk, 2),
                               "off_gap": round(off, 2), "longest_uncoupled": round(run, 2)}
        rec("INFO", "L5G-pair", "%s %s/%s: length P / N, net skew, P length off the %.2f-%.2f mm gap, longest uncoupled "
            "run" % (name, p, n, lo, hi), "%.2f / %.2f mm, %+.2f mm, %.1f of %.1f mm, %.2f mm" % (
                tot.get(p, 0), tot.get(n, 0), sk, off, t, run), "", "report only (D-H7 accepts the coupling)")
    # end-to-end skew (FAIL-capable)
    for lbl, (p, n, pj, nj) in (("ETH TX", ("ETH_TXP", "ETH_TXN", "ETH_TXP_J", "ETH_TXN_J")),
                                ("ETH RX", ("ETH_RXP", "ETH_RXN", "ETH_RXP_J", "ETH_RXN_J"))):
        sk = tot.get(p, 0) + tot.get(pj, 0) - tot.get(n, 0) - tot.get(nj, 0)
        rec("PASS" if abs(sk) <= SKEW_MAX else "FAIL", "L5G-pair", "%s P/N skew U9 -> J3 (net + _J segment)" % lbl,
            "%+.2f mm" % sk, "<= %.2f" % SKEW_MAX)
    import l4check
    pads = {}
    for fp in board.GetFootprints():
        for q in fp.Pads():
            pads.setdefault(q.GetNetname(), []).append((fp.GetReference(), q.GetNumber(), bl.pad_polygon(q), q))
    graphs = {nn: l4check._graph(nn, segs, vias, pads) for nn in l4check.USB_NETS}
    leg = {}
    for what, p, pa, pb, n, na, nb in l4check.USB_PATHS:
        lp, _i = graphs[p].path(pa, pb)
        ln, _j = graphs[n].path(na, nb)
        leg[what] = None if lp is None or ln is None else (lp, ln)
    soc = leg.get("SoC -> U11")
    for what in [w for w in leg if w != "SoC -> U11"]:
        if soc is None or leg[what] is None:
            rec("FAIL", "L5G-pair", "SoC -> %s pad-to-pad paths" % what, "no copper path", "")
            continue
        lp, ln = soc[0] + leg[what][0], soc[1] + leg[what][1]
        rec("PASS" if abs(lp - ln) <= SKEW_MAX else "FAIL", "L5G-pair", "USB P/N skew SoC -> %s end to end (pad to pad, "
            "through U11)" % what.replace("U11 -> ", ""), "%.2f / %.2f mm, %+.2f mm" % (lp, ln, lp - ln),
            "<= %.2f" % SKEW_MAX)
    sk = tot.get("USB_DP", 0) + tot.get("USBA_DP", 0) - tot.get("USB_DM", 0) - tot.get("USBA_DM", 0)
    rec("INFO", "L5G-pair", "SoC -> USB-A net-total skew (USB_D* + USBA_D* all copper incl. branches; the reviewer's "
        "1.42 mm)", "%+.2f mm" % sk, "", "the pad-to-pad line above is the rule")


def check_l5g(board, rec, segs, vias):
    check_ep(board, rec, vias)
    check_silk(board, rec)
    cases = check_sd(board, rec, segs)
    cases += check_rtc(board, rec, segs)
    check_runs_stable(rec, cases)
    check_tht(board, rec, segs)
    check_holes(board, rec)
    check_hops(board, rec, vias)
    check_q1(board, rec, vias)
    check_pairs(board, rec, segs, vias)
    return MEAS
