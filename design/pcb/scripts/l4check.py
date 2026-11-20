"""Layout phase L4 checks (TP-L4), called by check_routing.py: every layout.md §4 rule claimed for the critical routing
is measured here from the saved board with our own pcbnew geometry (lengths, skew, gaps, coupling, via counts,
stitching, widths, separations), and the per-net table is written to design/pcb/routing-report.md (section between
the L4-TABLE markers) and design/pcb/l4/measured.json.

Results go through check_routing.rec(): PASS / DEV (recorded deviation, decisions.md number) / INFO / FAIL.
"""
import json
import math
import os

import boardlib as bl
import routelib as rl

import pcbnew

FAN = (26.6, 28.6, 42.4, 44.4)
ETH_PAIRS = (("ETH_RXP", "ETH_RXN", "ETH_RXP_J", "ETH_RXN_J"), ("ETH_TXP", "ETH_TXN", "ETH_TXP_J", "ETH_TXN_J"))
USB_PAIRS = (("USB_DP", "USB_DM", "SoC -> U11"), ("USBA_DP", "USBA_DM", "U11 -> U2 -> J4"),
             ("USBC_DP", "USBC_DM", "U11 -> U1 -> J1"))
XTAL = ("OSC_XIN", "OSC_XOUT", "OSC_XOUT_X", "RTC_XIN", "RTC_XOUT")
XTAL_LIM = {"OSC_XIN": 5.0, "OSC_XOUT_X": 5.0, "OSC_XOUT": 8.0, "RTC_XIN": 6.0, "RTC_XOUT": 6.0}
SD = ("SDMMC_CMD", "SDMMC_D0", "SDMMC_D1", "SDMMC_D2", "SDMMC_D3")
SD_CLK = ("SDMMC_CLK", "SDMMC_CLK_SD")
FSPI = (("FSPI_D0",), ("FSPI_D1",), ("FSPI_D2",), ("FSPI_D3",), ("FSPI_CS0N", "FSPI_CS0N_NAND"))
FSPI_CLK = ("FSPI_CLK", "FSPI_CLK_NAND")
BUCKS = (("U4", "L1", "U4_SW", "U4_FB"), ("U5", "L2", "U5_SW", "U5_FB"), ("U6", "L3", "U6_SW", "U6_FB"),
         ("U7", "L4", "U7_SW", "U7_FB"))
POWER = ("VBUS_IN", "VBUS_5V", "VDD_0V9_BUCK", "VCC_3V3_BUCK", "VCC_DDR_BUCK", "VCC_1V8_BUCK", "VCC_DDR", "VCC_1V8",
         "VCC3V3_SD", "VCC5V0_SYS", "VBUS_USBA", "VDD_0V9", "VCC_3V3")
# nets whose L4 use is recorded (D-104 e, D-106, D-108, D-111): anything else critical on B.Cu is a FAIL
L4_OK = {"USB_DM", "USBA_DM", "USBC_DP", "USBC_DM", "ETH_TXP", "ETH_TXN", "VCC3V3_SD", "VCC_DDR", "VCC_1V8",
         "VBUS_IN", "VBUS_5V", "SARADC_IN1", "RECOVERY", "USB_DET_IN", "VCC5V0_SYS", "VBUS_USBA", "VCC_3V3",
         "VDD_0V9", "GND",
         "NPOR"}      # D-114 f (L5 r2): NPOR's R35 / TP7 branch north of U9 runs on L4 (DC reset line, 10 k pull-up)
CRIT_CLASSES = ("ETH_DIFF", "USB_DIFF", "XTAL", "SDMMC", "FSPI", "SW_NODE", "ETH_CT")
# thin branches of power nets that carry no load current (test pads, ESD/sense pins, bleeders): width 0.30 mm
THIN_OK = {"VBUS_IN": ("TP21",), "VBUS_5V": ("TP1", "U1", "U3", "C3", "C4", "R5", "R8")}
MEAS = {}
FSPI_DEV = {"FSPI_D3": 27.0, "FSPI_D2": 25.0, "FSPI_CS0N+FSPI_CS0N_NAND": 25.0}   # D-111 (e): max accepted length
# D-112 j: signal vias with no legal GND via site within 1 mm (nearest GND via 1.2-2.3 mm): the USB-C J1 join vias
# between U1 and the J1 pad row, the USBC_DM dive via under U11 and one ETH_TXN hop via
STITCH_DEV = ((47.75, 70.90), (49.75, 71.12), (51.15, 71.00), (38.35, 56.85), (22.85, 31.10))
LONE_DEV = ((44.49, 35.99), (44.961, 33.949), (46.27, 27.00))  # D-112 i: C45.1 / C47.1 / R44-R45 branch vias
GAP = {"ETH_DIFF": 0.200, "USB_DIFF": 0.152}     # class gap (netclasses.csv; USB as routed: 0.150 + 2 um, D-111)


def seglen(s):
    return math.hypot(s[3][0] - s[2][0], s[3][1] - s[2][1])


def pt_seg(p, a, b):
    return bl._seg_pt(p[0], p[1], a[0], a[1], b[0], b[1])


def seg_seg(a, b, c, d):
    return rl.seg_seg(a, b, c, d)


def in_fan(p):
    return FAN[0] <= p[0] <= FAN[2] and FAN[1] <= p[1] <= FAN[3]


def check_l4(board, rec, segs, vias, per_net, R):
    by = {}
    for s in segs:
        by.setdefault(s[0], []).append(s)
    vby = {}
    for v in vias:
        vby.setdefault(v[0], []).append(v)
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pads.setdefault(p.GetNetname(), []).append((fp.GetReference(), p.GetNumber(), bl.pad_polygon(p), p))

    def L(net):
        return sum(seglen(s) for s in by.get(net, []))

    def nvias(net):
        return len(vby.get(net, []))

    # ---------------------------------------------------------------- connectivity of every critical net
    crit = sorted(n for n in R if R[n][0] in CRIT_CLASSES or R[n][0] in ("SENSE",) and n.endswith("_FB")
                  or n in POWER or n in ("SDMMC_DET",))
    bad = [n for n in crit if per_net.get(n)]
    rec("PASS" if not bad else "FAIL", "L4-conn", "TP-L4 net set fully connected (KiCad unconnected items = 0): the "
        "classes ETH_DIFF, USB_DIFF, XTAL, SDMMC, FSPI, SW_NODE, ETH_CT, the *_FB nets, SDMMC_DET and the power-path "
        "nets (D-112 k)", "%d nets, %d open" % (len(crit), len(bad)),
        0, " ".join("%s(%d)" % (n, per_net[n]) for n in bad))
    lit = sorted(n for n in R if n.startswith(("ETH", "USB", "SDMMC", "FSPI", "OSC", "RTC")) and n not in crit)
    rec("INFO", "L4-conn", "nets matching the gate's name patterns but outside the TP-L4 set (DEFAULT control / PWR_SUB "
        "supply nets, routed in L5; D-112 k)", " ".join("%s(%d)" % (n, per_net.get(n, 0)) for n in lit), "")
    MEAS["connectivity"] = {n: per_net.get(n, 0) for n in crit}

    # ---------------------------------------------------------------- layer policy
    onb = sorted({s[0] for s in segs if s[1] == pcbnew.B_Cu and s[0] in R and (R[s[0]][0] in CRIT_CLASSES or
                                                                               R[s[0]][0] == "SENSE")})
    badb = [n for n in onb if n not in L4_OK]
    rec("PASS" if not badb else "FAIL", "L4-layer", "critical/SENSE nets on L4 only where recorded (D-104 e, D-106, "
        "D-108, D-111)", " ".join(onb), "", " ".join(badb))

    # ---------------------------------------------------------------- crystals
    MEAS["xtal"] = {}
    for n in XTAL:
        ln = L(n)
        MEAS["xtal"][n] = round(ln, 2)
        st = "PASS" if ln <= XTAL_LIM[n] + 1e-6 else "DEV"
        rec(st, "L4-xtal", "%s length (all tracks, KiCad sum)" % n, "%.2f mm" % ln, "<= %.1f" % XTAL_LIM[n],
            "" if st == "PASS" else "D-111 (b): placement lower bounds of D-104 d / D-105 already exceed it")
    guard = []
    xpads = [(r, num, poly) for net in pads for (r, num, poly, p) in pads[net] if r in ("Y1", "Y2", "C76", "C77",
                                                                                       "C78", "C79")]
    for s in segs:
        if s[1] != pcbnew.F_Cu or s[0] in XTAL or s[0] == "GND" or not s[0]:
            continue
        if s[5].GetParentGroup() is None or s[5].GetParentGroup().GetName() != "L4_CRITICAL":
            continue          # L3 plane-via stubs (checked by the DRC class clearances in L3)
        for r, num, poly in xpads:
            d = rl.seg_poly(s[2], s[3], poly) - s[4] / 2
            if d < 1.0 - 1e-6:
                guard.append((s[0], r, round(d, 3)))
    rec("PASS" if not guard else "FAIL", "L4-xtal", "no other net's L4-phase track on L1 within 1 mm of the crystal "
        "pads (Y1, Y2, C76-C79; layout.md §4.3)", len(guard), 0, str(sorted(set(guard))[:6]))
    under = []
    for ref in ("Y1", "Y2"):
        fp = board.FindFootprintByReference(ref)
        bb = bl.courtyard_bbox(fp)
        for s in segs:
            if s[1] == pcbnew.B_Cu and rl.seg_poly(s[2], s[3], [(bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]),
                                                               (bb[0], bb[3])]) == 0:
                under.append((s[0], ref))
    rec("PASS" if not under else "FAIL", "L4-xtal", "nothing on L4 under the crystals", len(under), 0, str(under[:4]))
    # TP6 stub: OSC_XOUT copper from R50.1 to TP6.1
    MEAS["tp6_stub"] = round(stub_len(by.get("OSC_XOUT", []), "R50", "TP6", pads["OSC_XOUT"]), 2)
    rec("PASS" if MEAS["tp6_stub"] <= 3.0 else "DEV", "L4-xtal", "TP6 stub (R50.1 -> TP6.1 track length)",
        "%.2f mm" % MEAS["tp6_stub"], "<= 3.0", "" if MEAS["tp6_stub"] <= 3.0 else "D-104 d: TP6 7.18 mm placement")

    # ---------------------------------------------------------------- Ethernet
    MEAS["eth"] = {}
    for p, n, pj, nj in ETH_PAIRS:
        lp, ln_, lpj, lnj = L(p), L(n), L(pj), L(nj)
        d = {"P": round(lp, 2), "N": round(ln_, 2), "P_J": round(lpj, 2), "N_J": round(lnj, 2),
             "skew_pair": round(lp - ln_, 2), "skew_total": round(lp + lpj - ln_ - lnj, 2),
             "total_P": round(lp + lpj, 2), "total_N": round(ln_ + lnj, 2),
             "vias_P": nvias(p) + nvias(pj), "vias_N": nvias(n) + nvias(nj)}
        cp = coupling(by.get(p, []), by.get(n, []), R[p][1], GAP[R[p][0]])
        d.update(cp)
        MEAS["eth"][p[:6]] = d
        rec("PASS" if abs(d["skew_pair"]) <= 1.27 else "FAIL", "L4-eth", "%s/%s P/N skew (KiCad pair, U9 -> link)" % (
            p, n), "%.2f mm" % d["skew_pair"], "<= 1.27")
        rec("PASS" if abs(d["skew_total"]) <= 1.27 else "FAIL", "L4-eth", "%s P/N skew U9 -> J3 across the 0R links"
            % p[:6], "%.2f mm" % d["skew_total"], "<= 1.27")
        mx = max(d["total_P"], d["total_N"])
        rec("PASS" if mx <= 30 else "FAIL", "L4-eth", "%s longest line U9 -> J3" % p[:6], "%.2f mm" % mx, "<= 30")
        lim = 2 if "TX" in p else 0
        rec("PASS" if max(d["vias_P"], d["vias_N"]) <= max(lim, 0) else "FAIL", "L4-eth", "%s vias per line" % p[:6],
            "%d / %d" % (d["vias_P"], d["vias_N"]), "<= %d (D-106 b, D-H5)" % lim)
        ok = cp["coupled"] > 0 and cp["gap_min"] >= 0.19 - 1e-3 and cp["gap_max"] <= 0.21 + 1e-3
        rec("PASS" if ok else "FAIL", "L4-eth", "%s gap on the coupled L1/L4 runs outside the fan" % p[:6],
            "%.3f-%.3f mm over %.2f mm" % (cp["gap_min"], cp["gap_max"], cp["coupled"]), "0.19-0.21")
        rec("DEV", "L4-eth", "%s uncoupled length (P line, outside the fan)" % p[:6], "%.2f mm" % cp["uncoupled"],
            "<= 5 at J3", "D-108 b / D-H5: link P/N swap + TX hop + skew meander; DRU limit set in l4_rules.py")
    tx = [s for s in segs if s[0] in ("ETH_TXP", "ETH_TXN", "ETH_TXP_J", "ETH_TXN_J")]
    rx = [s for s in segs if s[0] in ("ETH_RXP", "ETH_RXN", "ETH_RXP_J", "ETH_RXN_J")]
    best = (9, None)
    for a in tx:
        for b in rx:
            if a[1] != b[1] or (in_fan(a[2]) and in_fan(b[2])) or (in_fan(a[2]) or in_fan(a[3])) and \
                    (in_fan(b[2]) or in_fan(b[3])):
                continue
            dd = seg_seg(a[2], a[3], b[2], b[3]) - a[4] / 2 - b[4] / 2
            if dd < best[0]:
                best = (dd, (a[0], b[0], a[2], b[2]))
    for v in [v for v in vias if v[0].startswith("ETH_TX")]:
        for b in rx:
            dd = pt_seg((v[1], v[2]), b[2], b[3]) - 0.25 - b[4] / 2
            if dd < best[0]:
                best = (dd, (v[0], b[0], (v[1], v[2]), b[2]))
    MEAS["eth_tx_rx_gap"] = round(best[0], 3)
    rec("PASS" if best[0] >= 0.76 - 1e-3 else "FAIL", "L4-eth", "TX vs RX separation (tracks + vias, beyond the U9 "
        "fan, same layer; D-108 b)", "%.3f mm" % best[0], ">= 0.76", str(best[1]))

    # ---------------------------------------------------------------- USB
    MEAS["usb"] = {}
    for p, n, what in USB_PAIRS:
        lp, ln_ = L(p), L(n)
        cp = coupling(by.get(p, []), by.get(n, []), R[p][1], GAP[R[p][0]])
        d = {"P": round(lp, 2), "N": round(ln_, 2), "skew": round(lp - ln_, 2), "vias_P": nvias(p),
             "vias_N": nvias(n), "path": what}
        d.update(cp)
        MEAS["usb"][p] = d
        rec("INFO", "L4-usb", "%s/%s net-total length difference (all copper of the nets incl. the J1 join legs; the "
            "skew rule is checked on the pad-to-pad paths below)" % (p, n), "%.2f mm" % d["skew"], "")
        rec("PASS" if max(d["vias_P"], d["vias_N"]) <= 4 else "FAIL", "L4-usb", "%s/%s vias per line" % (p, n),
            "%d / %d" % (d["vias_P"], d["vias_N"]), "<= 4")
        rec("PASS" if max(lp, ln_) <= 50 else "FAIL", "L4-usb", "%s/%s length" % (p, n), "%.2f / %.2f mm" % (lp, ln_),
            "<= 50")
        rec("INFO", "L4-usb", "%s/%s coupled / uncoupled length, gap range on coupled runs" % (p, n),
            "%.2f / %.2f mm, gap %.3f-%.3f" % (cp["coupled"], cp["uncoupled"], cp["gap_min"], cp["gap_max"]),
            "0.15 gap")
    gvias = [(v[1], v[2]) for v in vias if v[0] == "GND"]
    far = []
    for v in vias:
        if v[0] in ("USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM"):
            dn = min(math.hypot(v[1] - g[0], v[2] - g[1]) for g in gvias)
            if dn > 1.0 + 1e-6:
                far.append((v[0], round(v[1], 2), round(v[2], 2), round(dn, 2)))
    nusbv = sum(1 for v in vias if v[0].startswith(("USB_", "USBA_", "USBC_")))
    far_dev = [f for f in far if any(abs(f[1] - x) < 0.05 and abs(f[2] - y) < 0.05 for x, y in STITCH_DEV)
               and f[3] <= 2.5]
    far_bad = [f for f in far if f not in far_dev]
    rec("PASS" if not far else "FAIL" if far_bad else "DEV", "L4-usb", "GND stitching via within 1 mm of every USB "
        "signal via", "%d vias, %d without" % (nusbv, len(far)), 0, str(far) + (
            " (D-112 j: USB-C J1 join vias and the USBC_DM dive via, no legal GND via site within 1 mm; nearest "
            "listed)"
            if far_dev else ""))
    sep = min_other(segs, pads, ("USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM"), board,
                    ("U9", "J1", "U1", "U2", "U11"))
    MEAS["usb_other"] = sep
    rec("PASS" if sep[0] >= 0.76 - 1e-3 else "FAIL", "L4-usb", "USB lines to other-net tracks (outside U9/U11/U1/U2/J1"
        " courtyards, GND excluded)", "%.3f mm" % sep[0], ">= 0.76", str(sep[1]))
    sep = min_other(segs, pads, tuple(n for p in ETH_PAIRS for n in p), board, ("U9",))
    MEAS["eth_other"] = sep
    rec("PASS" if sep[0] >= 0.76 - 1e-3 else "FAIL", "L4-eth", "ETH lines to other-net tracks (outside the U9 "
        "courtyard, GND and ETH excluded)", "%.3f mm" % sep[0], ">= 0.76", str(sep[1]))

    # ---------------------------------------------------------------- SD / FSPI
    MEAS["sd"] = {}
    clk = sum(L(n) for n in SD_CLK)
    for n in SD:
        ln = L(n)
        MEAS["sd"][n] = (round(ln, 2), round(ln - clk, 2))
        rec("PASS" if ln <= 40 and abs(ln - clk) <= 5 else "FAIL", "L4-sd", "%s length / vs clock %.2f mm" % (n, clk),
            "%.2f / %+.2f mm" % (ln, ln - clk), "<= 40, +-5")
    MEAS["sd"]["CLK"] = round(clk, 2)
    MEAS["fspi"] = {}
    clk = sum(L(n) for n in FSPI_CLK)
    for grp in FSPI:
        ln = sum(L(n) for n in grp)
        MEAS["fspi"]["+".join(grp)] = (round(ln, 2), round(ln - clk, 2))
        okk = ln <= 25 and abs(ln - clk) <= 5
        st = "PASS" if okk else ("DEV" if "+".join(grp) in FSPI_DEV and ln <= FSPI_DEV["+".join(grp)] else "FAIL")
        rec(st, "L4-fspi", "%s length / vs clock %.2f mm" % ("+".join(grp), clk), "%.2f / %+.2f mm" % (ln, ln - clk),
            "<= 25, +-5", "" if okk else "D-111 (e): engineering rule (UNVERIFIED, layout.md §4.4); see decisions")
    MEAS["fspi"]["CLK"] = round(clk, 2)
    rec("PASS" if not any(s[1] == pcbnew.B_Cu for n in SD + SD_CLK + FSPI_CLK + ("FSPI_D0", "FSPI_D1", "FSPI_D2",
                                                                              "FSPI_D3", "FSPI_CS0N",
                                                                              "FSPI_CS0N_NAND")
                          for s in by.get(n, [])) and not any(nvias(n) for n in SD + SD_CLK) else "FAIL",
        "L4-sd", "SDMMC and FSPI on L1 only, no vias", "", "")

    # ---------------------------------------------------------------- bucks
    MEAS["buck"] = {}
    for u, ind, sw, fb in BUCKS:
        fpu = board.FindFootprintByReference(u)
        cbu = bl.courtyard_bbox(fpu)
        swp_all = [poly for (r, num, poly, p) in pads.get(sw, [])]
        swl = 0.0
        for s in by.get(sw, []):          # copper outside the SW pads (the pin -> inductor gap)
            n = max(1, int(seglen(s) / 0.02))
            for k in range(n):
                t = (k + 0.5) / n
                q = (s[2][0] + (s[3][0] - s[2][0]) * t, s[2][1] + (s[3][1] - s[2][1]) * t)
                if not any(bl._inside(q[0], q[1], poly) for poly in swp_all):
                    swl += seglen(s) / n
        outside = [s for s in by.get(sw, []) if not (cbu[0] - 0.7 <= (s[2][0] + s[3][0]) / 2 <= cbu[2] and
                                                   cbu[1] <= (s[2][1] + s[3][1]) / 2 <= cbu[3])]
        wmin = min((s[4] for s in outside), default=0)
        fbl = L(fb)
        swcu = [s for s in by.get(sw, [])] + []
        swp = [poly for (r, num, poly, p) in pads.get(sw, [])]
        dmin = 9.0
        fp = board.FindFootprintByReference(u)
        bb = bl.courtyard_bbox(fp)
        for s in by.get(fb, []):
            if rl.seg_poly(s[2], s[3], [(bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3])]) == 0:
                continue
            for t in swcu:
                dmin = min(dmin, seg_seg(s[2], s[3], t[2], t[3]) - s[4] / 2 - t[4] / 2)
            for poly in swp:
                dmin = min(dmin, rl.seg_poly(s[2], s[3], poly) - s[4] / 2)
        MEAS["buck"][u] = {"sw_len": round(swl, 2), "sw_w": round(wmin, 2), "fb_len": round(fbl, 2),
                           "fb_to_sw": round(dmin, 2)}
        rec("PASS" if swl <= 3.0 and wmin >= 1.2 - 1e-6 else "FAIL", "L4-buck", "%s SW node (%s.3 -> %s.1) copper between the "
            "pads / width (outside the IC pad row, where it is the 0.6 mm pin width)" % (u, u, ind), "%.2f mm / %.2f mm" % (swl, wmin), "<= 3 / >= 1.2")
        rec("PASS" if fbl <= 5.0 else "DEV", "L4-buck", "%s FB net copper (pin 5 + divider + C_FF)" % u,
            "%.2f mm" % fbl, "<= 5", "" if fbl <= 5 else "D-111 (c): FB net incl. divider branches")
        rec("PASS" if dmin >= 2.0 - 1e-3 else "FAIL", "L4-buck", "%s FB tracks (outside the IC courtyard) to the SW "
            "node" % u, "%.2f mm" % dmin, ">= 2.0")
        nsb = sum(1 for s in by.get(sw, []) if s[1] != pcbnew.F_Cu) + nvias(sw)
        rec("PASS" if not nsb else "FAIL", "L4-buck", "%s SW node on L1 only" % u, nsb, 0)

    # ---------------------------------------------------------------- power widths and via pairs
    MEAS["power"] = {}
    for n in POWER:
        if n not in R or not by.get(n):
            continue
        need = R[n][1]
        mine = [s for s in by[n] if s[5].GetParentGroup() is not None and
                s[5].GetParentGroup().GetName() == "L4_CRITICAL"]
        if not mine:
            continue
        thin = [s for s in mine if s[4] + 1e-6 < need]
        thin_len = sum(seglen(s) for s in thin)
        MEAS["power"][n] = {"class_w": need, "min_w_l4": round(min(s[4] for s in mine), 2), "vias_l4": 0,
                            "thin_len": round(thin_len, 2), "len_l4": round(sum(seglen(s) for s in mine), 2)}
        if not thin:
            rec("PASS", "L4-power", "%s L4 tracks at the class width" % n, "min %.2f mm" % min(s[4] for s in mine),
                ">= %.2f" % need)
        else:
            st = "DEV" if min(s[4] for s in thin) >= 0.30 - 1e-6 else "FAIL"
            rec(st, "L4-power", "%s tracks below the class width %.2f mm (pad-width necks at fine-pitch pins, "
                "load-free test/sense/decoupling branches)" % (n, need), "%.2f mm of %.2f mm, min %.2f mm" % (
                    thin_len, MEAS["power"][n]["len_l4"], min(s[4] for s in thin)), ">= 0.30 for branches",
                "D-111 (d)")
    for n in ("VCC_DDR", "VCC_1V8", "VCC3V3_SD"):
        vs = [(v[1], v[2]) for v in vby.get(n, []) if v[3].GetParentGroup() is not None and
              v[3].GetParentGroup().GetName() == "L4_CRITICAL"]
        lone = [v for v in vs if not any(0 < math.hypot(v[0] - w[0], v[1] - w[1]) <= 1.05 for w in vs)]
        MEAS["power"].setdefault(n, {})["vias_l4"] = len(vs)
        rec_l = [v for v in lone if any(math.hypot(v[0] - x, v[1] - y) < 0.05 for x, y in LONE_DEV)]
        other = [v for v in lone if v not in rec_l]
        st = "PASS" if not lone else ("DEV" if len(other) <= 1 and n in ("VCC_1V8", "VCC_DDR") else "FAIL")
        rec(st, "L4-power", "%s: >= 2 vias at every layer change (layout.md §3)" % n,
            "%d vias, %d single" % (len(vs), len(lone)), 0, str([(round(a, 2), round(b, 2)) for a, b in lone[:5]]) + (
                " D-111 (h) / D-112 i: no second site; branch vias of one decoupling cap / pull-up pair (load-free) and"
                " one rail via (0.74 A rating > 0.46 A design current)" if st == "DEV" else ""))
    check_round2(board, rec, segs, vias, per_net, R, pads, MEAS)
    return MEAS


def stub_len(segs, ref_a, ref_b, padlist):
    """track length on the shortest copper path between two pads of one net (graph of track end points)"""
    import heapq
    pa = [poly for (r, num, poly, p) in padlist if r == ref_a]
    pb = [poly for (r, num, poly, p) in padlist if r == ref_b]
    if not pa or not pb:
        return 0.0
    nodes = {}

    def key(q):
        return (round(q[0], 3), round(q[1], 3))
    adj = {}
    for s in segs:
        a, b = key(s[2]), key(s[3])
        adj.setdefault(a, []).append((b, seglen(s)))
        adj.setdefault(b, []).append((a, seglen(s)))
    starts = [k for k in adj if bl._inside(k[0], k[1], pa[0]) or rl.pt_poly(k, pa[0]) < 0.05]
    goals = {k for k in adj if bl._inside(k[0], k[1], pb[0]) or rl.pt_poly(k, pb[0]) < 0.05}
    dist = {k: 0.0 for k in starts}
    h = [(0.0, k) for k in starts]
    while h:
        d, k = heapq.heappop(h)
        if k in goals:
            return d
        if d > dist.get(k, 1e9):
            continue
        for k2, w in adj.get(k, []):
            # T junctions: a node that lies on a segment interior is not in adj; acceptable for our routes (each
            # route starts / ends on track end points)
            if d + w < dist.get(k2, 1e9):
                dist[k2] = d + w
                heapq.heappush(h, (d + w, k2))
    return 0.0


def coupling(ps, ns, w, gap, step=0.05):
    """sample the P line every 0.05 mm (outside the U9 fan): coupled where the N centre line is at the pair pitch
    (+-0.03 mm) on the same layer; returns coupled / uncoupled lengths and the gap range on the coupled samples"""
    pitch = w + gap
    cpl = unc = 0.0
    gmin, gmax = 9.0, 0.0
    for s in ps:
        L = seglen(s)
        n = max(1, int(L / step))
        for k in range(n):
            t = (k + 0.5) / n
            q = (s[2][0] + (s[3][0] - s[2][0]) * t, s[2][1] + (s[3][1] - s[2][1]) * t)
            if in_fan(q):
                continue
            near_v = min(math.hypot(q[0] - c[0], q[1] - c[1]) for c in (s[2], s[3]))
            dm = min(((pt_seg(q, m[2], m[3]), m[4]) for m in ns if m[1] == s[1]), default=(9.0, w))
            d, wn = dm
            pitch_here = (s[4] + wn) / 2 + gap        # the fan-width (0.15 mm) exit pieces have their own pitch
            if near_v < 0.25 and abs(d - pitch_here) <= 0.03:
                cpl += L / n          # at a mitred corner the centre-line distance dips by design (offset geometry)
                continue
            if abs(d - pitch_here) <= 0.012:
                cpl += L / n
                g = d - (s[4] + wn) / 2
                gmin, gmax = min(gmin, g), max(gmax, g)
            else:
                unc += L / n
    return {"coupled": round(cpl, 2), "uncoupled": round(unc, 2), "gap_min": round(gmin if cpl else 0, 3),
            "gap_max": round(gmax, 3)}


def min_other(segs, pads, mine, board, courts):
    bbs = []
    for r in courts:
        fp = board.FindFootprintByReference(r)
        bb = bl.courtyard_bbox(fp)
        bbs.append([(bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3])])
    eth = set(mine)
    best = (9.0, None)
    def touches_fan(s):
        return FAN[0] <= max(s[2][0], s[3][0]) and min(s[2][0], s[3][0]) <= FAN[2] and \
            FAN[1] <= max(s[2][1], s[3][1]) and min(s[2][1], s[3][1]) <= FAN[3]
    ms = [s for s in segs if s[0] in eth and not any(rl.seg_poly(s[2], s[3], b) == 0 for b in bbs)
          and not touches_fan(s)]
    for s in ms:
        for t in segs:
            if t[1] != s[1] or t[0] in eth or t[0] == "GND" or not t[0]:
                continue
            if abs(t[2][0] - s[2][0]) > 6 and abs(t[3][0] - s[3][0]) > 6:
                continue
            # the DRU neck-down rule wins for tracks that touch the U9 fan (both orders)
            if FAN[0] <= max(t[2][0], t[3][0]) and min(t[2][0], t[3][0]) <= FAN[2] and \
                    FAN[1] <= max(t[2][1], t[3][1]) and min(t[2][1], t[3][1]) <= FAN[3]:
                continue
            d = seg_seg(s[2], s[3], t[2], t[3]) - s[4] / 2 - t[4] / 2
            if d < best[0]:
                best = (round(d, 3), (s[0], t[0], [round(c, 2) for c in s[2]]))
    return best


# ==================================================================================================================
# Round 2 (D-112): pad-to-pad USB paths, stubs, coupling / impedance classes, pair clearance to pads and vias, bend
# angles, L4 under the SW nodes, VBUS_IN vias, crystal guard on all copper, hop reference planes.
# ==================================================================================================================
import pathlen  # noqa: E402

USB_BREAKOUT = ("U9", "J1", "U1", "U2", "U11")
RING = (24.2, 26.2, 44.8, 46.8)       # U9 ring-1 band (lane exits between the ring-1 caps; D-104, D-110, D-112 b)
USB_PATHS = (("SoC -> U11", "USB_DP", "U9.27", "U11.8", "USB_DM", "U9.26", "U11.7"),
             ("U11 -> U2 -> J4", "USBA_DP", "U11.3", "J4.3", "USBA_DM", "U11.4", "J4.2"),
             ("U11 -> U1 -> J1 (plug A side: A6/A7)", "USBC_DP", "U11.1", "J1.A6", "USBC_DM", "U11.2", "J1.A7"),
             ("U11 -> U1 -> J1 (plug B side: B6/B7)", "USBC_DP", "U11.1", "J1.B6", "USBC_DM", "U11.2", "J1.B7"))
USB_NETS = ("USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM")
ETH_NETS = ("ETH_RXP", "ETH_RXN", "ETH_RXP_J", "ETH_RXN_J", "ETH_TXP", "ETH_TXN", "ETH_TXP_J", "ETH_TXN_J")
XTAL_GUARD_DEV = {("VCC_3V3", "C77.1"), ("VCC_3V3", "C77.2"), ("VCC_3V3", "C79.1"), ("VCC_3V3", "C79.2")}
BRK_R = 2.5           # pin breakout: within 2.5 mm of a pin of the path's breakout parts, or inside the U9 ring band
UNCTRL_MAX = 1.0      # mm per line per path of 0.255 mm line that is neither coupled nor at a hop / pin breakout
# ETH pad proximities recorded as deviations (D-112 f): (ETH net, ref.pad) -> reason
ETH_PAD_DEV = {
    ("ETH_RXP_J", "J3.4"): "J3 4|2 gap, approved D-108 b / D-H5 (ETH_TCT centre tap of the same jack)",
    ("ETH_RXN_J", "C83.1"): "ETH_RCT centre-tap cap at J3.5 (L2 carried minor, D-108 b); part of the jack's RX winding",
    ("ETH_RXP_J", "C83.1"): "ETH_RCT centre-tap cap at J3.5 (D-108 b)",
    ("ETH_TXN_J", "C82.1"): "ETH_TCT centre-tap cap at J3.4 (D-108 b)",
    ("ETH_TXP_J", "C82.1"): "ETH_TCT centre-tap cap at J3.4 (D-108 b)",
    ("ETH_TXP", "FB1.2"): "FEPHY_AVDD3V3 ferrite output pad (DC rail, C66-decoupled) next to the TX exit; TX-RX 0.76 "
                          "mm leaves no room to move the TX run north",
    ("ETH_TXN", "FB1.2"): "as ETH_TXP",
}
# ETH-to-via proximities recorded as deviations: (ETH net, "via NET") -> reason
ETH_VIA_DEV = {("ETH_TXP", "via FEPHY_AVDD3V3"): "D-114 d via in the C66.1 pad (FEPHY_AVDD3V3, DC; the copper stays "
                                                  "inside the C66.1 pad, which is in the U9 ring-1 band)"}
STITCH_DEV2 = ()      # filled from the router log: USB/ETH signal vias without a GND via within 1 mm (D-112 j)


def _graph(net, segs, vias, pads):
    ss = [(("F" if s[1] == pcbnew.F_Cu else "B"), s[2], s[3], s[4]) for s in segs if s[0] == net and
          s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
    vv = [(v[1], v[2]) for v in vias if v[0] == net]
    pp = {}
    for (r, num, poly, p) in pads.get(net, []):
        lays = set()
        if p.IsOnLayer(pcbnew.F_Cu):
            lays.add("F")
        if p.IsOnLayer(pcbnew.B_Cu):
            lays.add("B")
        pp["%s.%s" % (r, num)] = (poly, bl.to_board(p.GetPosition()), lays)
    return pathlen.NetGraph(ss, vv, pp)


def _rect_hit(a, b, r, pad=0.0):
    x0, y0, x1, y1 = r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad
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


def check_round2(board, rec, segs, vias, per_net, R, pads, MEAS):
    courts = {}
    for fp in board.GetFootprints():
        bb = bl.courtyard_bbox(fp)
        if bb:
            courts[fp.GetReference()] = bb
    grp = lambda o: o.GetParentGroup() is not None and o.GetParentGroup().GetName() == "L4_CRITICAL"  # noqa: E731

    # ------------------------------------------------------------ USB pad-to-pad paths, skew, stubs, coupling
    MEAS["usb_paths"] = []
    graphs = {n: _graph(n, segs, vias, pads) for n in USB_NETS}
    gvias = [(v[1], v[2]) for v in vias if v[0] == "GND"]
    for what, p, pa, pb, n, na, nb in USB_PATHS:
        lp, ip = graphs[p].path(pa, pb)
        ln, inn = graphs[n].path(na, nb)
        if lp is None or ln is None:
            rec("FAIL", "L4-usb", "%s: pad-to-pad path %s %s->%s / %s %s->%s" % (what, p, pa, pb, n, na, nb),
                "no copper path", "")
            continue
        sk = lp - ln
        cls_p = _classify(graphs[p].segs_of(ip), graphs[n].segs_of(inn), vias, (p, n), pads, (pa, pb))
        cls_n = _classify(graphs[n].segs_of(inn), graphs[p].segs_of(ip), vias, (p, n), pads, (na, nb))
        d = {"path": what, "P": p, "N": n, "len_P": round(lp, 2), "len_N": round(ln, 2), "skew": round(sk, 2),
             "vias_P": sum(1 for v in vias if v[0] == p), "vias_N": sum(1 for v in vias if v[0] == n),
             "class_P": cls_p, "class_N": cls_n}
        MEAS["usb_paths"].append(d)
        rec("PASS" if abs(sk) <= 1.27 else "FAIL", "L4-usb", "%s P/N skew, pad-to-pad paths %s %s->%s / %s %s->%s"
            % (what, p, pa, pb, n, na, nb), "%.2f / %.2f mm, skew %+.2f mm" % (lp, ln, sk), "<= 1.27")
        rec("PASS" if max(lp, ln) <= 50 else "FAIL", "L4-usb", "%s longest line (pad to pad)" % what,
            "%.2f mm" % max(lp, ln), "<= 50")
        for net, c in ((p, cls_p), (n, cls_n)):
            st = "PASS" if c["other"] <= UNCTRL_MAX + 1e-6 else "FAIL"
            rec(st, "L4-usb", "%s %s: 90 ohm control along the path - coupled 0.255/0.152 | 0.42 mm Z0 45 ohm | hop "
                "(D-H5) | pin breakout | uncontrolled 0.255 mm" % (what, net),
                "%.2f | %.2f | %.2f | %.2f | %.2f mm" % (c["coupled"], c["wide"], c["hop"], c["breakout"], c["other"]),
                "uncontrolled <= %.1f" % UNCTRL_MAX)
    # copper of a USB net that lies on none of its pad-to-pad paths (dangling stubs; layout.md §4.6 '0 stubs' except
    # the USB-C join legs, which are on the B-side / A-side paths)
    used = {}
    for what, p, pa, pb, n, na, nb in USB_PATHS:
        for net, a, b in ((p, pa, pb), (n, na, nb)):
            used.setdefault(net, set()).update(graphs[net].path(a, b)[1])
    dang = {}
    for net in USB_NETS:
        pcs = graphs[net].pieces
        ownp = [poly for (r, num, poly, p) in pads.get(net, [])]
        on = [pcs[i] for i in used.get(net, set())]

        def buried(q):
            # an off-path piece whose both ends lie under path copper of the same layer adds no stub (e.g. the last
            # 0.13 mm of an L3 gate lane under the L4 neck-down piece that continues it)
            return all(any(o[0] == q[0] and pt_seg(e, o[1], o[2]) <= o[3] / 2 + 1e-3 for o in on) for e in (q[1], q[2]))
        dang[net] = round(sum(math.hypot(q[2][0] - q[1][0], q[2][1] - q[1][1]) for i, q in enumerate(pcs)
                              if i not in used.get(net, set()) and not buried(q) and not any(
                                  bl._inside((q[1][0] + q[2][0]) / 2, (q[1][1] + q[2][1]) / 2, poly) for poly in ownp)),
                          2)
    MEAS["usb_dangling"] = dang
    bad_d = {k: v for k, v in dang.items() if v > 0.05}
    rec("PASS" if not bad_d else "FAIL", "L4-usb", "USB copper off every pad-to-pad path (dangling stubs; the J1 join "
        "legs are on the A/B paths; copper inside the net's own pads excluded)", " ".join("%s %.2f" % kv for kv in sorted(dang.items())), "<= 0.05 mm per net",
        str(bad_d) if bad_d else "")
    # USB-C stubs at J1 (layout.md §4.6 'short stubs < 2 mm ... symmetric')
    st = {}
    for net, a, b, c in (("USBC_DP", "U11.1", "J1.A6", "J1.B6"), ("USBC_DP", "U11.1", "J1.B6", "J1.A6"),
                         ("USBC_DM", "U11.2", "J1.A7", "J1.B7"), ("USBC_DM", "U11.2", "J1.B7", "J1.A7")):
        st[(net, c)] = pathlen.stub(graphs[net], a, b, c)
    MEAS["usbc_stubs"] = {"%s->%s" % k: (round(v, 2) if v is not None else None) for k, v in st.items()}
    for side, (kp, kn) in (("A (stubs to B6/B7)", (("USBC_DP", "J1.B6"), ("USBC_DM", "J1.B7"))),
                           ("B (stubs to A6/A7)", (("USBC_DP", "J1.A6"), ("USBC_DM", "J1.A7")))):
        sp, sn = st[kp], st[kn]
        ok = sp is not None and sn is not None and max(sp, sn) <= 2.0 + 1e-6 and abs(sp - sn) <= 0.3
        rec("PASS" if ok else "FAIL", "L4-usb", "USB-C J1 join stubs, plug side %s: DP / DM" % side,
            "%s / %s mm" % (sp and round(sp, 2), sn and round(sn, 2)), "<= 2.0 each, |DP - DM| <= 0.3")
    MEAS["usb_vias"] = {n: sum(1 for v in vias if v[0] == n) for n in USB_NETS}

    # ------------------------------------------------------------ pair clearance to other nets (tracks, pads, vias)
    allpads = [(r, num, poly, p) for net in pads for (r, num, poly, p) in pads[net]]
    for cls_name, nets, brk in (("USB", USB_NETS, USB_BREAKOUT), ("ETH", ETH_NETS, ("U9",))):
        worst = []
        mine = [s for s in segs if s[0] in nets and s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
        for s in mine:
            if _rect_hit(s[2], s[3], FAN):
                continue
            in_brk = any(_rect_hit(s[2], s[3], courts[r]) for r in brk if r in courts)
            if in_brk:
                continue
            in_ring = _rect_hit(s[2], s[3], RING)
            for t in segs:
                if t[1] != s[1] or t[0] in nets or t[0] in ("GND", "") or (cls_name == "USB" and t[0] in USB_NETS):
                    continue
                if R.get(t[0], [""])[0] == ("USB_DIFF" if cls_name == "USB" else "ETH_DIFF"):
                    continue
                if _rect_hit(t[2], t[3], FAN):
                    continue
                if abs(t[2][0] - s[2][0]) > 8 and abs(t[3][0] - s[3][0]) > 8:
                    continue
                dd = seg_seg(s[2], s[3], t[2], t[3]) - s[4] / 2 - t[4] / 2
                if dd < 0.76 - 1e-3:
                    worst.append((round(dd, 3), s[0], "track " + t[0], [round(c, 2) for c in s[2]]))
            if in_ring:
                continue
            for v in vias:
                if v[0] in nets or v[0] == "GND" or v[0] in USB_NETS + ETH_NETS:
                    continue
                if cls_name == "USB" and any(courts[r][0] - 0.25 <= v[1] <= courts[r][2] + 0.25 and
                                             courts[r][1] - 0.25 <= v[2] <= courts[r][3] + 0.25
                                             for r in brk if r in courts):
                    continue
                dd = pt_seg((v[1], v[2]), s[2], s[3]) - 0.25 - s[4] / 2
                if dd < 0.76 - 1e-3:
                    worst.append((round(dd, 3), s[0], "via " + v[0], [round(v[1], 2), round(v[2], 2)]))
            for (r, num, poly, p) in allpads:
                if r in brk or p.GetNetname() in ("GND",) or p.GetNetname() in nets:
                    continue
                if not p.IsOnLayer(s[1]):
                    continue
                if abs(poly[0][0] - s[2][0]) > 8 and abs(poly[0][0] - s[3][0]) > 8:
                    continue
                dd = rl.seg_poly(s[2], s[3], poly) - s[4] / 2
                if dd < 0.76 - 1e-3:
                    worst.append((round(dd, 3), s[0], "pad %s.%s %s" % (r, num, p.GetNetname()),
                                  [round(c, 2) for c in s[2]]))
        # one line per (net, item)
        uniq = {}
        for w in sorted(worst):
            uniq.setdefault((w[1], w[2]), w)
        items = sorted(uniq.values())
        MEAS["%s_clearance" % cls_name.lower()] = [list(w) for w in items]
        dev, bad = [], []
        for w in items:
            key = (w[1], w[2].split()[1]) if w[2].startswith("pad") else None
            if w[2].startswith("via") and (w[1], w[2]) in ETH_VIA_DEV:
                key = (w[1], w[2])
            (dev if cls_name == "ETH" and (key in ETH_PAD_DEV or key in ETH_VIA_DEV) else bad).append(w)
        st = "FAIL" if bad else ("DEV" if dev else "PASS")
        rec(st, "L4-%s" % cls_name.lower(), "%s lines >= 0.76 mm from other-net tracks, pads and vias (GND excluded; "
            "breakout parts %s and the U9 ring-1 band excluded, D-112 b)" % (cls_name, "/".join(brk)),
            "%d below" % len(items), ">= 0.76", "; ".join("%s %s %.3f mm" % (w[1], w[2], w[0]) for w in items[:8]) +
            ("" if not dev else " | DEV D-112 f: " + "; ".join("%s-%s: %s" % (w[1], w[2], ETH_PAD_DEV.get(
                (w[1], w[2].split()[1])) or ETH_VIA_DEV[(w[1], w[2])]) for w in dev)))

    # ------------------------------------------------------------ USB-A vs USB-C paths (layout.md §10: >= 0.76 mm)
    A, C = ("USBA_DP", "USBA_DM"), ("USBC_DP", "USBC_DM")
    cu = courts["U11"]
    field = (cu[0] - 0.6, cu[1], cu[2] + 1.5, cu[3] + 2.9)     # the D-108 a crossing south of U11 (USB-C dives under)
    pa = [s for s in segs if s[0] in A]
    pc = [s for s in segs if s[0] in C]
    sep = []
    for s in pa:
        for t in pc:
            if s[1] == t[1]:
                sep.append((seg_seg(s[2], s[3], t[2], t[3]) - s[4] / 2 - t[4] / 2, s, t[2]))
    for v in vias:
        for grp_, other in ((A, pc), (C, pa)):
            if v[0] in grp_:
                for t in other:
                    sep.append((pt_seg((v[1], v[2]), t[2], t[3]) - 0.25 - t[4] / 2, ("via",), (v[1], v[2])))
    inside = lambda q: field[0] <= q[0] <= field[2] and field[1] <= q[1] <= field[3]  # noqa: E731
    out_f = [x for x in sep if x[0] < 0.76 - 1e-3 and not inside(x[2])]
    in_f = [x for x in sep if x[0] < 0.76 - 1e-3 and inside(x[2])]
    mo = min((x[0] for x in sep if not inside(x[2])), default=9)
    MEAS["usba_usbc_sep"] = {"outside_crossing": round(mo, 3), "crossing_min": round(min((x[0] for x in in_f),
                                                                                            default=9), 3)}
    rec("FAIL" if out_f else ("DEV" if in_f else "PASS"), "L4-usb", "USB-A path vs USB-C path separation (layout.md "
        "§10), outside / inside the D-108 a crossing field south of U11", "%.3f / %.3f mm" % (
            mo, MEAS["usba_usbc_sep"]["crossing_min"]), ">= 0.76", "" if not in_f else
        "DEV D-108 a / D-112 a: the approved crossing (USB-C under the USB-A pair, 0.5 mm pin pitch) keeps the class "
        "clearance; %d close pairs, all inside x %.1f-%.1f, y %.1f-%.1f" % (len(in_f), field[0], field[2], field[1],
                                                                       field[3]))

    # ------------------------------------------------------------ bends >= 135 deg on the pair lines (L4 copper)
    sharp = []
    for net in USB_NETS + ETH_NETS:
        mine = [s for s in segs if s[0] == net and grp(s[5]) and s[1] in (pcbnew.F_Cu, pcbnew.B_Cu)]
        ends = {}
        for s in mine:
            for k, q in ((0, s[2]), (1, s[3])):
                ends.setdefault((s[1], round(q[0], 3), round(q[1], 3)), []).append((s, k))
        vxy = [(v[1], v[2]) for v in vias if v[0] == net]
        for (lay, x, y), lst in ends.items():
            if len(lst) != 2:
                continue
            if any(math.hypot(x - vx, y - vy) < 0.3 for vx, vy in vxy):
                continue
            if any(p.IsOnLayer(lay) and bl._inside(x, y, poly) for (r, num, poly, p) in pads.get(net, [])):
                continue
            (s1, k1), (s2, k2) = lst
            d1 = (s1[3][0] - s1[2][0], s1[3][1] - s1[2][1]) if k1 == 1 else (s1[2][0] - s1[3][0], s1[2][1] - s1[3][1])
            d2 = (s2[3][0] - s2[2][0], s2[3][1] - s2[2][1]) if k2 == 0 else (s2[2][0] - s2[3][0], s2[2][1] - s2[3][1])
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            if l1 < 1e-6 or l2 < 1e-6:
                continue
            c = max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / l1 / l2))
            turn = math.degrees(math.acos(c))
            if turn > 45.0 + 0.5 and not (RING[0] <= x <= RING[2] and RING[1] <= y <= RING[3]):
                sharp.append((net, round(x, 2), round(y, 2), round(180 - turn)))
    MEAS["sharp_bends"] = sharp
    rec("PASS" if not sharp else "FAIL", "L4-bend", "ETH/USB L4 copper outside the U9 ring-1 band (lane exits): every "
        "bend >= 135 deg (layout.md §4.6; meanders mitred, D-112 e)", "%d sharper" % len(sharp), 0, str(sharp[:6]))

    # ------------------------------------------------------------ nothing on L4 under the SW nodes (layout.md §4.5)
    under = []
    for u, ind, sw, fb in BUCKS:
        polys = [poly for (r, num, poly, p) in pads.get(sw, [])]
        xs = [q[0] for poly in polys for q in poly]
        ys = [q[1] for poly in polys for q in poly]
        box = (min(xs), min(ys), max(xs), max(ys))
        for s in segs:
            if s[1] == pcbnew.B_Cu and _rect_hit(s[2], s[3], box, s[4] / 2):
                under.append((s[0], u))
        for v in vias:
            if _rect_hit((v[1], v[2]), (v[1], v[2]), box, 0.25) and v[0] != sw:
                under.append((v[0] + " via", u))
    under = sorted(set(under))
    rec("PASS" if not under else "FAIL", "L4-buck", "nothing on L4 (tracks) and no via under the four SW nodes "
        "(SW pads bounding box)", len(under), 0, str(under[:6]))

    # ------------------------------------------------------------ VBUS_IN: >= 3 vias per layer change, 1.0 mm on L4
    vv = [(v[1], v[2]) for v in vias if v[0] == "VBUS_IN" and grp(v[3])]
    groups = []
    for q in vv:
        for g in groups:
            if any(math.hypot(q[0] - r[0], q[1] - r[1]) <= 1.35 for r in g):
                g.append(q)
                break
        else:
            groups.append([q])
    thin = [s for s in segs if s[0] == "VBUS_IN" and grp(s[5]) and 0.30 + 1e-6 < s[4] < 1.0 - 1e-6 and
            s[1] == pcbnew.B_Cu and seglen(s) > 1.3]
    main_groups = [g for g in groups if len(g) > 1 or not any(
        math.hypot(g[0][0] - x, g[0][1] - y) < 1.0 for (x, y) in ((57.36, 65.96), (56.64, 50.49)))]
    few = [g for g in main_groups if len(g) < 3]
    MEAS["vbus_in_vias"] = [len(g) for g in groups]
    rec("PASS" if not few else "FAIL", "L4-power", "VBUS_IN main path: vias per layer change (layout.md §3 PWR_5V "
        ">= 3; the TP21 0.30 mm test branch excluded)", " / ".join(str(len(g)) for g in main_groups), ">= 3",
        str(few[:2]))
    rec("PASS" if not thin else "FAIL", "L4-power", "VBUS_IN main L4 runs at 1.0 mm (via-cluster stubs <= 1.3 mm and "
        "the 0.30 mm TP21 test branch excluded)", "%d thinner" % len(thin), 0, str([(round(t[4], 2), [round(c, 2) for c
                                                                                   in t[2]]) for t in thin[:4]]))
    necks = [t for t in segs if t[0] == "VBUS_IN" and grp(t[5]) and t[1] == pcbnew.F_Cu and 0.30 + 1e-6 < t[4] < 1.0
             - 1e-6]
    rec("DEV" if necks else "PASS", "L4-power", "VBUS_IN L1 pad necks below 1.0 mm (J1 A4/B9, A9/B4 pin pairs)",
        "%.2f mm at %.2f mm" % (sum(seglen(t) for t in necks), min((t[4] for t in necks), default=0)), ">= 1.0",
        "D-112 h: 0.40 mm for 2.1-2.3 mm per pin pair between the J1 GND pad vias and the USB-C J1 vias; each pin pair "
        "carries half the 2.0 A design current (both pairs are joined at the plug)" if necks else "")

    # ------------------------------------------------------------ crystal guard, all copper (layout.md §4.3)
    xp = [(r, num, poly, p) for (r, num, poly, p) in allpads if r in ("Y1", "Y2", "C76", "C77", "C78", "C79")]
    g = []
    xtal_nets = set(n for n in R if R[n][0] == "XTAL")
    for s in segs:
        if s[1] != pcbnew.F_Cu or s[0] in xtal_nets or s[0] in ("GND", ""):
            continue
        for r, num, poly, p in xp:
            d = rl.seg_poly(s[2], s[3], poly) - s[4] / 2
            if d < 1.0 - 1e-3:
                g.append(("track " + s[0], "%s.%s" % (r, num), round(d, 3)))
    for v in vias:
        if v[0] in xtal_nets or v[0] in ("GND", ""):
            continue
        for r, num, poly, p in xp:
            d = rl.pt_poly((v[1], v[2]), poly) - 0.25
            if d < 1.0 - 1e-3:
                g.append(("via " + v[0], "%s.%s" % (r, num), round(d, 3)))
    for (r2, num2, poly2, p2) in allpads:
        if r2 in ("Y1", "Y2", "C76", "C77", "C78", "C79", "U9") or p2.GetNetname() in xtal_nets or \
                p2.GetNetname() in ("GND", ""):
            continue
        for r, num, poly, p in xp:
            if abs(poly[0][0] - poly2[0][0]) > 4 or abs(poly[0][1] - poly2[0][1]) > 4:
                continue
            d = min(rl.seg_poly(poly2[i], poly2[(i + 1) % len(poly2)], poly) for i in range(len(poly2)))
            if d < 1.0 - 1e-3:
                g.append(("pad %s.%s %s" % (r2, num2, p2.GetNetname()), "%s.%s" % (r, num), round(d, 3)))
    g = sorted(set(g), key=lambda t: t[2])
    MEAS["xtal_guard_all"] = g
    gdev = [t for t in g if (t[0].split()[1], t[1]) in XTAL_GUARD_DEV and t[0].split()[0] in ("via", "track")]
    gbad = [t for t in g if t not in gdev]
    rec("PASS" if not g else ("FAIL" if gbad else "DEV"), "L4-xtal", "crystal guard on all copper: no other net's track (L1), via or L1 pad "
        "within 1 mm of the Y1/Y2/C76-C79 pads (GND and the crystal nets excluded; U9 pins excluded)", len(g), 0,
        str(g[:8]) + ("" if not gdev else " | DEV D-112 l: L3 VCC_3V3 plane vias (and stubs) of R43.1 at (42.88, "
                                          "27.44) and C84.1 at (36.41, 54.35); no legal site further away"))
    # Y2 guard stitching (>= 4 GND vias within 1.5 mm of its courtyard)
    for ref in ("Y1", "Y2"):
        bb = courts[ref]
        n = sum(1 for (x, y) in gvias if bb[0] - 1.5 <= x <= bb[2] + 1.5 and bb[1] - 1.5 <= y <= bb[3] + 1.5)
        rec("PASS" if n >= 4 else "FAIL", "L4-xtal", "%s GND guard: GND vias within 1.5 mm of the courtyard" % ref,
            n, ">= 4")

    # ------------------------------------------------------------ GND stitching next to ETH TX hop vias
    far = []
    for v in vias:
        if v[0] in ("ETH_TXP", "ETH_TXN"):
            dn = min(math.hypot(v[1] - q[0], v[2] - q[1]) for q in gvias)
            if dn > 1.0 + 1e-6:
                far.append((v[0], round(v[1], 2), round(v[2], 2), round(dn, 2)))
    far_bad = [f for f in far if not any(abs(f[1] - x) < 0.05 and abs(f[2] - y) < 0.05 for x, y in STITCH_DEV)
               or f[3] > 2.5]
    rec("PASS" if not far else ("FAIL" if far_bad else "DEV"), "L4-eth", "GND stitching via within 1 mm of every ETH "
        "TX hop via (D-112 j)", "%d without" % len(far), 0, str(far) + (" DEV D-112 j: no legal GND site within 1 mm "
                                                                        "(nearest listed)" if far and not far_bad
                                                                        else ""))

    # ------------------------------------------------------------ L3 reference under the L4 hop copper
    l3 = [z for z in board.Zones() if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In2_Cu)]
    ref = {}
    for s in segs:
        if s[0] not in USB_NETS + ETH_NETS or s[1] != pcbnew.B_Cu:
            continue
        L = seglen(s)
        n = max(1, int(L / 0.05))
        for k in range(n):
            t = (k + 0.5) / n
            q = (s[2][0] + (s[3][0] - s[2][0]) * t, s[2][1] + (s[3][1] - s[2][1]) * t)
            nets = [z.GetNetname() for z in l3 if z.HitTestFilledArea(pcbnew.In2_Cu, bl.to_page(*q), 0)]
            key = (s[0], nets[0] if nets else "none")
            ref[key] = ref.get(key, 0.0) + L / n
    MEAS["hop_reference"] = {"%s over %s" % k: round(v, 2) for k, v in sorted(ref.items())}
    void = {k: v for k, v in ref.items() if k[1] == "none"}
    rec("INFO", "L4-hop", "L3 plane under the L4 hop copper of the pairs (length per net and L3 net)",
        "; ".join("%s over %s %.2f mm" % (k[0], k[1], v) for k, v in sorted(ref.items())), "",
        "void %.2f mm in all" % sum(void.values()))
    return MEAS


def _classify(mine, other, vias, pair, pads, ends):
    """sample a line's pad-to-pad path every 0.05 mm (outside the U9 fan and outside its own pads): coupled (partner at
    the class pitch, same layer), wide (>= 0.40 mm and partner edge >= 0.45 mm away: Z0 45 ohm each, ~90 ohm
    differential), hop (within 1.5 mm of a via of the pair), breakout (within BRK_R of a pin of the path's breakout
    parts, or inside the U9 ring-1 band), else uncontrolled"""
    out = {"coupled": 0.0, "wide": 0.0, "hop": 0.0, "breakout": 0.0, "other": 0.0}
    pv = [(v[1], v[2]) for v in vias if v[0] in pair]
    ownpads = [poly for n in pair for (r, num, poly, p) in pads.get(n, [])]
    brk = [poly for n in pair for (r, num, poly, p) in pads.get(n, []) if r in USB_BREAKOUT + ("J4",)]
    for lay, a, b, w in mine:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / 0.05))
        for k in range(n):
            t = (k + 0.5) / n
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if in_fan(q) or any(bl._inside(q[0], q[1], poly) for poly in ownpads):
                continue
            best = (9.0, w)
            for l2, c, d, w2 in other:
                if l2 != lay:
                    continue
                dd = pt_seg(q, c, d)
                if dd < best[0]:
                    best = (dd, w2)
            dist, w2 = best
            pitch = (w + w2) / 2 + GAP["USB_DIFF"]
            near_v = min((math.hypot(q[0] - x, q[1] - y) for x, y in pv), default=9)
            if abs(dist - pitch) <= 0.015 or (min(math.hypot(q[0] - a[0], q[1] - a[1]), math.hypot(q[0] - b[0],
                                                                                                   q[1] - b[1])) < 0.25
                                               and abs(dist - pitch) <= 0.03):
                out["coupled"] += L / n
            elif w >= 0.40 - 1e-6 and dist - (w + w2) / 2 >= 0.45:
                out["wide"] += L / n
            elif near_v <= 1.5:
                out["hop"] += L / n
            elif any(rl.pt_poly(q, poly) <= BRK_R for poly in brk) or (RING[0] <= q[0] <= RING[2] and
                                                                       RING[1] <= q[1] <= RING[3]):
                out["breakout"] += L / n
            else:
                out["other"] += L / n
    return {k: round(v, 2) for k, v in out.items()}
