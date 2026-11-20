#!/usr/bin/env python3
"""Self-test of the L5F checks (l5fcheck.py via check_routing.py; D-117): apply one known-bad change per check to a copy
of the delivered board, refill its zones, run check_routing.py on it and require a FAIL line of the expected rule.
Results go to design/pcb/trial/mutations_l5f.txt.

    $PY design/pcb/scripts/mutate_l5f.py [work dir]      # default design/pcb/trial/mut_l5f (about 50 s per case)

Mutations (expected rule):
  buck_strap      C14 (U6 100 nF input cap) moved 2.5 mm east                     L5F-buck (path > 3 mm)
  buck_spokes     U5.2 back to the inherited (thermal) zone connection           L5F-buck (solid)
  buck_cap_moved  C8 moved 2.5 mm east (input-cap GND pad far from pin 2)        L5F-buck (path > 3 mm)
  vip_new         a GND via whose ring touches C24.2 (not in via_in_pad.csv)     L5F-vip
  vip_stale       via_in_pad.csv with an extra row that matches no via           L5F-vip (stale rows)
  vcut_via        a GND via at (0.75, 61.6)                                      L5F-vcut
  vcut_pour       F_GND_POUR outline back to x = 0.40                             L5F-vcut
  vcut_lane       the HDR_PWM9 B.Cu lane back to x = 0.663 (the L5 position)      L5F-vcut (round 2, D-118 a)
  en_near_sw      a PWR_EN track inside L3's courtyard, 0.4 mm from L3.1         L5F-sw
  silk_thin       a 0.12 mm silk line on R13 and the PWR label at 0.8 mm         L5F-silk
  hop_island      the In2 GND island under the ETH TX hop deleted                L5F-hop
  neck_wide       the C29.1 branch widened back to 0.80 mm                       L5F-neck
  neck_overlap    a 0.80 mm VDD_0V9_BUCK track ending 0.15 mm outside C16.1        L5F-neck (overlap, D-118 e)
  dangle          a 0.5 mm PWR_EN stub from R24.2 ending in nothing on F.Cu              L5F-dangle
  corner_square   one R 1 mm board corner arc deleted                            L5F-edge
  notch_sharp     the NW rail notch back to the round-1 1.0 x 1.0 mm shape         L5F-edge (router corner, D-118 c)
  zone_out        R13 moved 4 mm east (out of Z-PMU)                             L5F-zone
  geom_30deg      a 30 deg L5F segment on PWR_EN (1 mm)                          L5F-geom
  u9_pad_162      U9 pad 62 renumbered 162 (the round-4 KeyError)                escape (FAIL line, no crash)
"""
import math
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
REPORT = os.path.join(bl.PCB_DIR, "trial", "mutations_l5f.txt")


def pad(b, ref, num):
    return [p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num][0]


def tracks(b, net, a=None, layer=None):
    out = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net and (layer is None or t.GetLayer() == layer):
            p, q = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if a is None or any(math.hypot(e[0] - a[0], e[1] - a[1]) < 0.01 for e in (p, q)):
                out.append(t)
    return out


def m_buck_strap(b):
    # the U6 100 nF input cap C14 moved 2.5 mm east: its GND pad is no longer within 3 mm of U6.2 on L1 (the strap
    # itself cannot be the mutation: with it deleted the L1 pour fills its path under the body)
    fp = b.FindFootprintByReference("C14")
    x, y = bl.to_board(fp.GetPosition())
    fp.SetPosition(bl.to_page(x + 2.5, y))


def m_buck_spokes(b):
    pad(b, "U5", "2").SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_INHERITED)


def m_buck_cap_moved(b):
    fp = b.FindFootprintByReference("C8")
    x, y = bl.to_board(fp.GetPosition())
    fp.SetPosition(bl.to_page(x + 2.5, y))


def m_vip_new(b):
    p = pad(b, "C24", "2")
    x, y = bl.to_board(p.GetPosition())
    rl.add_via(b, "GND", x + 0.62, y)


def m_vcut_via(b):
    rl.add_via(b, "GND", 0.75, 61.6)        # west edge south of the J5 lanes, between two edge-ring GND vias


def m_vcut_pour(b):
    for z in b.Zones():
        if z.GetZoneName() == "F_GND_POUR":
            o = z.Outline()
            for i in range(o.TotalVertices()):
                x, y = bl.to_board(o.CVertex(i))
                if x < 1.0:
                    o.SetVertex(i, bl.to_page(0.40, y))


def m_vcut_lane(b):
    for t in tracks(b, "HDR_PWM9", layer=pcbnew.B_Cu):
        p, q = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
        if abs(p[0] - q[0]) < 1e-3 and abs(p[0] - 0.8502) < 1e-3 and abs(p[1] - q[1]) > 10:
            t.SetStart(bl.to_page(0.663, p[1]))
            t.SetEnd(bl.to_page(0.663, q[1]))


def m_neck_overlap(b):
    # outward from C16.1 (away from C16.2): the track's centre-line end 0.15 mm outside the pad, so its 0.4 mm round
    # end reaches 0.25 mm into the pad while no end point lies inside it (the first L5F-neck line cannot see it)
    p1, p2 = pad(b, "C16", "1"), pad(b, "C16", "2")
    (x1, y1), (x2, y2) = bl.to_board(p1.GetPosition()), bl.to_board(p2.GetPosition())
    L = math.hypot(x1 - x2, y1 - y2)
    ux, uy = (x1 - x2) / L, (y1 - y2) / L
    half = abs(ux) * pcbnew.ToMM(p1.GetSize().x) / 2 + abs(uy) * pcbnew.ToMM(p1.GetSize().y) / 2
    if abs(p1.GetOrientation().AsDegrees()) % 180 > 45:
        half = abs(ux) * pcbnew.ToMM(p1.GetSize().y) / 2 + abs(uy) * pcbnew.ToMM(p1.GetSize().x) / 2
    s0 = (x1 + ux * (half + 0.15), y1 + uy * (half + 0.15))
    rl.add_track(b, "VDD_0V9_BUCK", "F", [s0, (s0[0] + ux * 1.0, s0[1] + uy * 1.0)], 0.80)


def m_notch_sharp(b):
    import l5f_board as lb
    dead = []
    for d in b.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        a, e = bl.to_board(d.GetStart()), bl.to_board(d.GetEnd())
        if all(-4.01 < q[0] < 0.01 and -0.01 < q[1] < 1.51 for q in (a, e)) and not (
                d.GetShape() == pcbnew.SHAPE_T_ARC and abs(bl.to_board(d.GetCenter())[0] - 1.0) < 0.01):
            dead.append(d)
    lb.seg(b, -4.0, 0.0, -1.0, 0.0)
    lb.seg(b, -1.0, 0.0, -1.0, 0.5)
    lb.arc(b, -0.5, 0.5, -1.0, 0.5, -0.5, 1.0)
    lb.seg(b, -0.5, 1.0, 0.0, 1.0)
    return dead


def m_en_near_sw(b):
    rl.add_track(b, "PWR_EN", "F", [(66.0, 19.1), (67.0, 19.1)], 0.15)


def m_silk_thin(b):
    fp = b.FindFootprintByReference("R13")
    g = pcbnew.PCB_SHAPE(fp)
    g.SetShape(pcbnew.SHAPE_T_SEGMENT)
    g.SetLayer(pcbnew.F_SilkS)
    g.SetWidth(pcbnew.FromMM(0.12))
    x, y = bl.to_board(fp.GetPosition())
    g.SetStart(bl.to_page(x - 0.5, y - 1.2))
    g.SetEnd(bl.to_page(x + 0.5, y - 1.2))
    fp.Add(g)
    for d in b.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetText() == "PWR":
            d.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
            d.SetTextThickness(pcbnew.FromMM(0.12))


def m_neck_wide(b):
    for t in tracks(b, "VDD_0V9_BUCK"):
        p, q = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
        if any(abs(e[0] - 71.075) < 0.01 and 30.9 < e[1] < 32.5 for e in (p, q)):
            t.SetWidth(pcbnew.FromMM(0.80))


def m_dangle(b):
    # a 0.5 mm PWR_EN stub from R24.2 ending in nothing (a GND stub would be joined by the pour)
    p = pad(b, "R24", "2")
    x, y = bl.to_board(p.GetPosition())
    rl.add_track(b, "PWR_EN", "F", [(x, y), (x, y + 0.5)], 0.15)


def m_zone_out(b):
    fp = b.FindFootprintByReference("R13")
    x, y = bl.to_board(fp.GetPosition())
    fp.SetPosition(bl.to_page(x + 4.0, y))


def m_geom_30deg(b):
    t = rl.add_track(b, "GND", "F", [(14.0, 44.0), (14.866, 44.5)], 0.30)
    g = [x for x in b.Groups() if x.GetName() == "L5F_ROUTE"][0]       # an L5F piece (the check covers L5* groups)
    for it in t:
        g.AddItem(it)


def m_u9_pad_162(b):
    pad(b, "U9", "62").SetNumber("162")


def delete_blocks(path, uids, kinds=("(via", "(segment", "(arc", "(zone", "(gr_arc", "(gr_line")):
    """remove items by uuid from the saved .kicad_pcb text (pcbnew's Remove() crashes in 10.0.7 here)"""
    txt = open(path, encoding="utf-8").read()
    for uid in uids:
        k = txt.index('(uuid "%s")' % uid)
        a = max(txt.rfind(kd, 0, k) for kd in kinds)
        depth, i = 0, a
        while True:
            if txt[i] == "(":
                depth += 1
            elif txt[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        txt = txt[:a] + txt[i + 1:]
    open(path, "w", encoding="utf-8").write(txt)


def m_hop_island(b):
    return [z for z in b.Zones() if z.GetZoneName() == "In2_GND_HOP_0"]


def m_corner_square(b):
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_ARC:
            c = bl.to_board(d.GetCenter())
            if abs(c[0] - 1.0) < 0.01 and abs(c[1] - 1.0) < 0.01:
                return [d]
    return []


MUTATIONS = [("buck_strap", m_buck_strap, "L5F-buck"), ("buck_spokes", m_buck_spokes, "L5F-buck"),
             ("buck_cap_moved", m_buck_cap_moved, "L5F-buck"), ("vip_new", m_vip_new, "L5F-vip"),
             ("vip_stale", None, "L5F-vip"), ("vcut_via", m_vcut_via, "L5F-vcut"),
             ("vcut_pour", m_vcut_pour, "L5F-vcut"), ("vcut_lane", m_vcut_lane, "L5F-vcut"),
             ("en_near_sw", m_en_near_sw, "L5F-sw"),
             ("silk_thin", m_silk_thin, "L5F-silk"), ("hop_island", m_hop_island, "L5F-hop"),
             ("neck_wide", m_neck_wide, "L5F-neck"), ("neck_overlap", m_neck_overlap, "L5F-neck"),
             ("dangle", m_dangle, "L5F-dangle"), ("corner_square", m_corner_square, "L5F-edge"),
             ("notch_sharp", m_notch_sharp, "L5F-edge"), ("zone_out", m_zone_out, "L5F-zone"),
             ("geom_30deg", m_geom_30deg, "L5F-geom"), ("u9_pad_162", m_u9_pad_162, "escape")]


def make_one(name, d):
    fn = {n: f for n, f, _r in MUTATIONS}.get(name)
    base = os.path.splitext(os.path.basename(bl.BOARD_FILE))[0]
    os.makedirs(d, exist_ok=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(os.path.join(bl.PCB_DIR, base + ext), os.path.join(d, base + ext))
    b = pcbnew.LoadBoard(bl.BOARD_FILE)
    dele = fn(b) if fn else None
    uids = [v.m_Uuid.AsString() for v in (dele or [])]
    dst = os.path.join(d, base + ".kicad_pcb")
    pcbnew.SaveBoard(dst, b)
    if uids:
        delete_blocks(dst, uids)
    b = pcbnew.LoadBoard(dst)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(dst, b)


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "--one":
        make_one(sys.argv[2], sys.argv[3])
        return
    work = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(bl.PCB_DIR, "trial", "mut_l5f")
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
        env = dict(os.environ)
        if name == "vip_stale":
            csvp = os.path.join(d, "via_in_pad.csv")
            shutil.copy(os.path.join(bl.PCB_DIR, "via_in_pad.csv"), csvp)
            with open(csvp, "a", encoding="utf-8") as fh:
                fh.write("C99.1,GND,10.00,10.00,GND,0.000,stale row (mutation)\n")
            env["L5F_VIP_CSV"] = csvp
        dst = os.path.join(d, base + ".kicad_pcb")
        r = subprocess.run([PY, os.path.join(HERE, "check_routing.py"), dst, d], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, env=env)
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
