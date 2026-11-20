#!/usr/bin/env python3
"""Self-test of the L5G checks (l5gcheck.py via check_routing.py; D-H7, D-119..D-127): one known-bad change per check on
a copy of the delivered board, zones refilled, check_routing.py run on it; a FAIL line of the expected rule is required.
Results: design/pcb/trial/mutations_l5g.txt (same harness as mutate_l5f.py).

    $PY design/pcb/scripts/mutate_l5g.py [work dir]      # default design/pcb/trial/mut_l5g (about 60 s per case)

Mutations (expected rule):
  ep_via_gone     one of the 16 U9 EP board vias deleted                           L5G-ep
  ep_no_fill      board setup via filling off                                      L5G-ep
  silk_tp3_tp14   the "3" (TP3) label moved beside TP14                            L5G-silk
  silk_u5_c7      the U5 reference moved next to C7 (the round-2 position)         L5G-silk
  th_text         the TH3 reference shown again at (77.85, 10)                     L5G-silk
  sd_clk_close    a 3 mm SDMMC_D0 piece 0.21 mm beside the SDMMC_CLK_SD horizontal  L5G-sd
  rtc_close       a 1.5 mm SDMMC_D2 piece 0.30 mm beside RTC_XOUT below the channel  L5G-rtc
  rtc_channel     a 1.0 mm SDMMC_D2 piece 0.40 mm beside RTC_XOUT in the R48 / C58   L5G-rtc
                  channel (the round-1 exemption is gone, D-128)
  rtc_pair_long   a 2.5 mm RTC_XIN piece 0.35 mm beside RTC_XOUT (pair run > 2 mm)  L5G-rtc
  silk_margin     a passing reference moved so its margin is 0.05-0.20 mm           L5G-silk
                  (would pass the round-1 0.05 mm margin)
  silk_tp3_band   "3" (TP3) just below TP3, in the band between the TP rows          L5G-silk
  u9_lib          U9 pointed back at the drilled-pad library footprint              L5G-ep
  tht_short       the J5.2-J5.4 B.Cu link back to (5.30, 10.36)-(5.30, 10.86)       L5G-tht
  hole_close      the J1 shell GND via back to (45.647, 71.957)                   L5G-hole
  hop_one         the second In2_GND_HOP_3 via deleted                            L5G-hop
  q1_three        the two L5G Q1 drain vias deleted                               L5G-q1
  pair_skew       a 1.6 mm ETH_TXP stub (P/N skew > 1.27 mm)                       L5G-pair
"""
import math
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import mutate_l5f as M5  # noqa: E402

import pcbnew  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
REPORT = os.path.join(bl.PCB_DIR, "trial", "mutations_l5g.txt")


def via_at(b, x, y, net=None):
    for v in b.GetTracks():
        if v.GetClass() == "PCB_VIA" and (net is None or v.GetNetname() == net):
            p = bl.to_board(v.GetPosition())
            if abs(p[0] - x) < 0.01 and abs(p[1] - y) < 0.01:
                return v
    return None


def text(b, s):
    return [d for d in b.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() == s and
            d.GetLayer() == pcbnew.F_SilkS][0]


def track(b, net, a, c, w=0.15, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(b)
    t.SetLayer(layer)
    t.SetWidth(pcbnew.FromMM(w))
    t.SetStart(bl.to_page(*a))
    t.SetEnd(bl.to_page(*c))
    t.SetNet(b.FindNet(net))
    b.Add(t)


def m_ep_via_gone(b):
    return [via_at(b, 34.50, 35.35, "GND")]


def m_ep_no_fill(b):
    b.GetDesignSettings().m_FillVias = False


def tp3_label(b):
    return [d for d in b.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() in ("3", "TP3") and
            d.GetLayer() == pcbnew.F_SilkS][0]


def m_silk_tp3_tp14(b):
    t = tp3_label(b)
    p14 = [p for p in b.FindFootprintByReference("TP14").Pads()][0]
    x, y = bl.to_board(p14.GetPosition())
    t.SetTextAngleDegrees(0)
    t.SetPosition(bl.to_page(x, y - 1.6))


def m_silk_u5_c7(b):
    r = b.FindFootprintByReference("U5").Reference()
    r.SetVisible(True)
    r.SetTextAngleDegrees(90)
    r.SetPosition(bl.to_page(71.15, 38.08))


def m_th_text(b):
    r = b.FindFootprintByReference("TH3").Reference()
    r.SetVisible(True)
    r.SetPosition(bl.to_page(77.85, 10.0))


def m_sd_clk_close(b):
    # the SDMMC_CLK_SD horizontal runs at y 48.125 (x 26.93-33.71); a D0 piece 0.36 mm north of it (gap 0.21)
    track(b, "SDMMC_D0", (28.0, 47.765), (31.0, 47.765))


def m_rtc_close(b):
    # RTC_XOUT runs at x 35.555 from y 47.09 to 49.565 (D-128); a D2 piece 0.45 mm west of it (gap 0.30)
    track(b, "SDMMC_D2", (35.105, 47.4), (35.105, 48.9))


def m_rtc_channel(b):
    # RTC_XOUT runs at x 35.745 in the R48 / C58 channel (y 44.375-46.90); a D2 piece 0.55 mm west of it (gap 0.40),
    # outside the pin escape (y > 44.45)
    track(b, "SDMMC_D2", (35.195, 45.0), (35.195, 46.0))


def m_rtc_pair_long(b):
    # an RTC_XIN piece 0.50 mm east of the RTC_XOUT vertical x 35.555 (gap 0.35), 2.5 mm long
    track(b, "RTC_XIN", (36.055, 47.2), (36.055, 49.7))


def m_silk_margin(b):
    import l5g_silklib as S
    cu = S.copper(b)
    rows = [r for r in S.evaluate(b) if r[8] and r[0] == "field" and r[2] and r[2][0] in "RC" and r[3] is None]
    rows.sort(key=lambda r: r[2])
    for kind, text, ref, padnum, box, d_own, other, lim, ok, why, item in rows:
        pos = bl.to_board(item.GetPosition())
        size = S.size_of(b, ref)
        for i in range(-30, 31):
            for j in range(-30, 31):
                item.SetPosition(bl.to_page(pos[0] + i * 0.05, pos[1] + j * 0.05))
                m = S.measure(S.ink_box(item), ref, None, cu, size, look=1.0)
                if m[0] is not None and m[0] <= m[2] and 0.06 <= m[1][0] - m[0] <= 0.18:
                    print("silk_margin: %s at (%.2f, %.2f): own %.3f, other %.3f %s" % (
                        ref, pos[0] + i * 0.05, pos[1] + j * 0.05, m[0], m[1][0], m[1][1]))
                    return
        item.SetPosition(bl.to_page(*pos))
    raise SystemExit("silk_margin: no position found")


def m_silk_tp3_band(b):
    t = tp3_label(b)
    t.SetText("3")
    p3 = [p for p in b.FindFootprintByReference("TP3").Pads()][0]
    x, y = bl.to_board(p3.GetPosition())
    t.SetTextAngleDegrees(0)
    t.SetPosition(bl.to_page(x, y + 1.35))


def m_u9_lib(b):
    b.FindFootprintByReference("U9").SetFPID(pcbnew.LIB_ID("board", "RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm"))


def m_tht_short(b):
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == "VCC5V0_SYS" and t.GetLayer() == pcbnew.B_Cu:
            a, c = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if abs(a[0] - 5.54) < 0.01 and abs(c[0] - 5.54) < 0.01:
                t.SetStart(bl.to_page(5.30, 10.36))
                t.SetEnd(bl.to_page(5.30, 10.86))


def m_hole_close(b):
    v = via_at(b, 45.685, 71.899, "GND")
    v.SetPosition(bl.to_page(45.647, 71.957))
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == "GND":
            a, c = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if math.hypot(a[0] - 45.685, a[1] - 71.899) < 0.003:
                t.SetStart(bl.to_page(45.647, 71.957))
            if math.hypot(c[0] - 45.685, c[1] - 71.899) < 0.003:
                t.SetEnd(bl.to_page(45.647, 71.957))


def m_hop_one(b):
    return [via_at(b, 50.75, 74.10, "GND")]


def m_q1_three(b):
    out = [via_at(b, 60.50, 65.10, "VCC5V0_SYS"), via_at(b, 59.25, 66.30, "VCC5V0_SYS")]
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == "VCC5V0_SYS":
            a = bl.to_board(t.GetStart())
            if any(math.hypot(a[0] - q[0], a[1] - q[1]) < 0.003 for q in ((60.50, 65.10), (59.25, 66.30))):
                out.append(t)
    return out


def m_pair_skew(b):
    # a 1.6 mm ETH_TXP stub from the end of an ETH_TXP track, pointing away from everything (TX skew -0.29 -> +1.31)
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == "ETH_TXP" and t.GetLayer() == pcbnew.F_Cu:
            a = bl.to_board(t.GetStart())
            track(b, "ETH_TXP", a, (a[0], a[1] + 1.6), pcbnew.ToMM(t.GetWidth()))
            return


MUTATIONS = [("ep_via_gone", m_ep_via_gone, "L5G-ep"), ("ep_no_fill", m_ep_no_fill, "L5G-ep"),
             ("silk_tp3_tp14", m_silk_tp3_tp14, "L5G-silk"), ("silk_u5_c7", m_silk_u5_c7, "L5G-silk"),
             ("th_text", m_th_text, "L5G-silk"), ("sd_clk_close", m_sd_clk_close, "L5G-sd"),
             ("rtc_close", m_rtc_close, "L5G-rtc"), ("rtc_channel", m_rtc_channel, "L5G-rtc"),
             ("rtc_pair_long", m_rtc_pair_long, "L5G-rtc"), ("silk_margin", m_silk_margin, "L5G-silk"),
             ("silk_tp3_band", m_silk_tp3_band, "L5G-silk"), ("u9_lib", m_u9_lib, "L5G-ep"),
             ("tht_short", m_tht_short, "L5G-tht"),
             ("hole_close", m_hole_close, "L5G-hole"), ("hop_one", m_hop_one, "L5G-hop"),
             ("q1_three", m_q1_three, "L5G-q1"), ("pair_skew", m_pair_skew, "L5G-pair")]


def make_one(name, d):
    fn = {n: f for n, f, _r in MUTATIONS}.get(name)
    base = os.path.splitext(os.path.basename(bl.BOARD_FILE))[0]
    os.makedirs(d, exist_ok=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(os.path.join(bl.PCB_DIR, base + ext), os.path.join(d, base + ext))
    if os.path.exists(os.path.join(bl.PCB_DIR, "fp-lib-table")):
        shutil.copy(os.path.join(bl.PCB_DIR, "fp-lib-table"), os.path.join(d, "fp-lib-table"))
    b = pcbnew.LoadBoard(bl.BOARD_FILE)
    dele = fn(b) if fn else None
    uids = [v.m_Uuid.AsString() for v in (dele or []) if v is not None]
    dst = os.path.join(d, base + ".kicad_pcb")
    pcbnew.SaveBoard(dst, b)
    if uids:
        M5.delete_blocks(dst, uids)
    b = pcbnew.LoadBoard(dst)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(dst, b)


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "--one":
        make_one(sys.argv[2], sys.argv[3])
        return
    work = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(bl.PCB_DIR, "trial", "mut_l5g")
    os.makedirs(work, exist_ok=True)
    base = os.path.splitext(os.path.basename(bl.BOARD_FILE))[0]
    lines = []
    only = [n for n in os.environ.get("MUT_ONLY", "").split(",") if n]
    for name, _fn, rule in [("control", None, None)] + MUTATIONS:
        if only and name not in only:
            continue
        d = os.path.join(work, name)
        subprocess.run([PY, os.path.abspath(__file__), "--one", name, d], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        dst = os.path.join(d, base + ".kicad_pcb")
        r = subprocess.run([PY, os.path.join(HERE, "check_routing.py"), dst, d], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")]
        head = [ln for ln in r.stdout.splitlines() if ln.startswith("check_routing.py:")]
        crashed = "Traceback" in r.stdout
        if name == "control":
            ok = r.returncode == 0 and not crashed
            verdict = "OK" if ok else "CONTROL FAILED"
        else:
            hit = [ln for ln in fails if ln[5:].startswith(rule)]
            ok = r.returncode == 1 and bool(hit) and not crashed
            verdict = "OK (%s FAIL)" % rule if ok else "NOT CAUGHT (%s)" % rule
        lines.append("%-15s exit %d %-22s %s" % (name, r.returncode, verdict, head[0] if head else "(no summary)"))
        print(lines[-1], flush=True)
        for ln in fails[:5]:
            lines.append("    " + ln[:200])
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT + (".partial" if only else ""), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("-> " + REPORT)
    bad = [ln for ln in lines if "NOT CAUGHT" in ln or "CONTROL FAILED" in ln]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
