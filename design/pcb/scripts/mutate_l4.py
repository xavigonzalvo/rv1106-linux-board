#!/usr/bin/env python3
"""Self-test of the L4 checks (l4check.py via check_routing.py), verifier L4 r1: apply known-bad changes to copies of
the routed board and confirm that each one adds at least one new FAIL line compared with the unmutated control (the
control itself carries the L5 lane-capacity watch FAILs, so the exit code alone does not decide).

    $PY design/pcb/scripts/mutate_l4.py [work dir]      # default design/pcb/trial/mut_l4 -> trial/mutations_l4.txt

Mutations:
  usbc_stub      a 3 mm L1 stub on USBC_DM from its J1 T via south-west under the receptacle body
  usb_via        a USB_SEL via 0.5 mm north of the coupled USB-C run (44.0, 56.30)
  sw_under       a 2 mm VCC_DDR track on L4 under the U5 SW node
  vbus_via       one of the 3 VBUS_IN vias at J1 A4/B9 deleted
  c45_link       the C45.1 via (VCC_DDR) and its link deleted
  usba_skew      USBA_DP's J4 entry straightened (pad-to-pad skew > 1.27 mm)
"""
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import mutate_routing as mr  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
REPORT = os.path.join(bl.PCB_DIR, "trial", "mutations_l4.txt")


def tracks_at(b, net, p, layer=None, tol=0.01):
    out = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetname() != net or (layer is not None and t.GetLayer() != layer):
            continue
        for q in (bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())):
            if math.hypot(q[0] - p[0], q[1] - p[1]) < tol:
                out.append(t)
                break
    return out


def m_usbc_stub(b):
    rl.add_track(b, "USBC_DM", "F", [(49.25, 73.75), (47.40, 75.60), (47.40, 76.00)], 0.255)


def m_usb_via(b):
    v = rl.add_via(b, "USB_SEL", 44.0, 56.30)
    v.SetIsFree(True)       # a via without tracks would otherwise take the net of the plane it sits in


def m_sw_under(b):
    rl.add_track(b, "VCC_DDR", "B", [(65.5, 45.15), (67.5, 45.15)], 0.30)


def m_vbus_via(b):
    return [mr.vias_near(b, "VBUS_IN", 47.05, 70.05, 0.05)[0]]


def m_c45_link(b):
    return [mr.vias_near(b, "VCC_DDR", 44.49, 35.99, 0.05)[0]] + tracks_at(b, "VCC_DDR", (44.794, 35.891), pcbnew.F_Cu)


def m_usba_skew(b):
    dele = []
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA" and t.GetNetname() == "USBA_DP":
            a, e = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if a[1] > 63.6 and e[1] > 63.6:
                dele.append(t)
    rl.add_track(b, "USBA_DP", "F", [(36.95, 63.90), (36.95, 66.45)], 0.42)
    return dele


def delete_in_file(path, uids):
    """remove (segment ...) / (via ...) blocks by uuid from the saved file (pcbnew's Remove() crashes in 10.0.7)"""
    txt = open(path, encoding="utf-8").read()
    for uid in uids:
        k = txt.index('(uuid "%s")' % uid)
        a = max(txt.rindex("(via", 0, k), txt.rfind("(segment", 0, k))
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


def make_one(name, d):
    import shutil
    fn = dict(MUTATIONS).get(name)
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
        delete_in_file(dst, uids)
    b = pcbnew.LoadBoard(dst)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(dst, b)


MUTATIONS = [("usbc_stub", m_usbc_stub), ("usb_via", m_usb_via), ("sw_under", m_sw_under),
             ("vbus_via", m_vbus_via), ("c45_link", m_c45_link), ("usba_skew", m_usba_skew)]


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "--one":
        make_one(sys.argv[2], sys.argv[3])
        return
    work = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(bl.PCB_DIR, "trial", "mut_l4")
    os.makedirs(work, exist_ok=True)
    base = os.path.splitext(os.path.basename(bl.BOARD_FILE))[0]
    lines, control = [], None
    bad = 0
    only = os.environ.get("MUT_ONLY")
    for name, _fn in [("control", None)] + [m for m in MUTATIONS if not only or m[0] in only.split(",")]:
        d = os.path.join(work, name)
        subprocess.run([PY, os.path.abspath(__file__), "--one", name, d], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        dst = os.path.join(d, base + ".kicad_pcb")
        subprocess.run([PY, os.path.join(HERE, "check_routing.py"), dst, d], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        txt = open(os.path.join(d, "check_routing.txt"), encoding="utf-8").read().splitlines()
        fails = set(ln.split("|")[0].strip() for ln in txt if ln.startswith("FAIL"))
        if name == "control":
            control = fails
            lines.append("%-10s %s (%d FAIL lines: the L5 lane-capacity watch)" % (name, txt[0], len(fails)))
        else:
            new = sorted(fails - control)
            ok = bool(new)
            bad += not ok
            lines.append("%-10s %s -> %s" % (name, "CAUGHT" if ok else "NOT CAUGHT", txt[0]))
            for ln in new[:5]:
                lines.append("    new: " + ln[:200])
        print(lines[-1])
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("-> " + REPORT)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
