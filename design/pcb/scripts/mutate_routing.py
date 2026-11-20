#!/usr/bin/env python3
"""Self-test of check_routing.py (verifier L3 r2 major): apply known-bad changes to copies of the routed board and
confirm that the checker exits 1 (FAIL) for each. Results go to design/pcb/trial/mutations_routing.txt.

    $PY design/pcb/scripts/mutate_routing.py [work dir]      # default design/pcb/trial/mut_routing

Each copy gets the project's .kicad_pro / .kicad_dru beside it (DRC needs the net classes and rules), its zones are
refilled after the change, and check_routing.py runs on it with its own output folder.
Mutations (the verifier's six, rounds 1-2):
  c64_moved      C64 moved 5 mm east (its links and vias stay)
  c64_2_via      the GND via of C64.2 deleted
  neck_vias      3 GND vias added inside the VDD_0V9 neck at x 55 (y 33.8 / 35.0 / 36.2)
  lane_via       a VCC_3V3 via added at (42.97, 37.90), in the FSPI lane channel east of U9
  u9_11_12_swap  the nets of U9 pads 11 and 12 swapped
  jp1_5_vias     one of the 6 vias of JP1.2 deleted
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
REPORT = os.path.join(bl.PCB_DIR, "trial", "mutations_routing.txt")


def vias_near(b, net, x, y, r):
    out = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == net:
            vx, vy = bl.to_board(t.GetPosition())
            if math.hypot(vx - x, vy - y) <= r:
                out.append((math.hypot(vx - x, vy - y), t))
    out.sort(key=lambda q: q[0])
    return [t for _d, t in out]


def pad(b, ref, num):
    return [p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num][0]


def m_c64_moved(b):
    fp = b.FindFootprintByReference("C64")
    x, y = bl.to_board(fp.GetPosition())
    fp.SetPosition(bl.to_page(x + 5.0, y))


def m_c64_2_via(b):
    p = pad(b, "C64", "2")
    x, y = bl.to_board(p.GetPosition())
    return [vias_near(b, "GND", x, y, 1.0)[0]]          # deleted from the saved file (see make_one)


def m_neck_vias(b):
    for y in (33.8, 35.0, 36.2):
        rl.add_via(b, "GND", 55.0, y)


def m_lane_via(b):
    rl.add_via(b, "VCC_3V3", 42.97, 37.90)


def m_u9_11_12_swap(b):
    p11, p12 = pad(b, "U9", "11"), pad(b, "U9", "12")
    n11, n12 = p11.GetNet(), p12.GetNet()
    p11.SetNet(n12)
    p12.SetNet(n11)


def m_jp1_5_vias(b):
    p = pad(b, "JP1", "2")
    x, y = bl.to_board(p.GetPosition())
    return [vias_near(b, "VDD_0V9", x, y, 2.0)[0]]


def delete_vias_in_file(path, vias):
    """Remove via blocks by their uuid from the saved .kicad_pcb text (pcbnew's Remove() crashes in 10.0.7 here)."""
    txt = open(path, encoding="utf-8").read()
    for uid in vias:
        k = txt.index('(uuid "%s")' % uid)
        a = txt.rindex("(via", 0, k)
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


MUTATIONS = [("c64_moved", m_c64_moved), ("c64_2_via", m_c64_2_via), ("neck_vias", m_neck_vias),
             ("lane_via", m_lane_via), ("u9_11_12_swap", m_u9_11_12_swap), ("jp1_5_vias", m_jp1_5_vias)]


def make_one(name, d):
    """Separate process per mutation: pcbnew's Remove() leaves the SWIG wrappers unusable (routelib.require_fresh)."""
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
        delete_vias_in_file(dst, uids)
    b = pcbnew.LoadBoard(dst)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(dst, b)


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "--one":
        make_one(sys.argv[2], sys.argv[3])
        return
    work = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(bl.PCB_DIR, "trial", "mut_routing")
    os.makedirs(work, exist_ok=True)
    base = os.path.splitext(os.path.basename(bl.BOARD_FILE))[0]
    lines = []
    for name, _fn in [("control", None)] + MUTATIONS:
        d = os.path.join(work, name)
        subprocess.run([PY, os.path.abspath(__file__), "--one", name, d], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        dst = os.path.join(d, base + ".kicad_pcb")
        r = subprocess.run([PY, os.path.join(HERE, "check_routing.py"), dst, d], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")]
        head = [ln for ln in r.stdout.splitlines() if ln.startswith("check_routing.py:")]
        want = 0 if name == "control" else 1
        verdict = "OK" if r.returncode == want else "NOT CAUGHT" if want else "CONTROL FAILED"
        lines.append("%-14s exit %d (%s) %s" % (name, r.returncode, verdict, head[0] if head else ""))
        print(lines[-1])
        for ln in fails[:6]:
            lines.append("    " + ln[:220])
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("-> " + REPORT)
    bad = [ln for ln in lines if "NOT CAUGHT" in ln or "CONTROL FAILED" in ln]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
