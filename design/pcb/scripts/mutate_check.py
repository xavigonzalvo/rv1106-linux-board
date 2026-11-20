#!/usr/bin/env python3
"""Self-test of check_placement.py (verifier L2 round 2): apply known-bad mutations to copies of the board and confirm
that the checker reports FAIL for each. Results go to design/pcb/trial/mutations.txt.

    PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $PY design/pcb/scripts/mutate_check.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

PY = sys.executable
OUT = os.path.join(bl.PCB_DIR, "trial", "mut")


def move(b, ref, x, y, rot=None):
    fp = b.FindFootprintByReference(ref)
    if rot is not None:
        fp.SetOrientationDegrees(rot)
    fp.SetPosition(bl.to_page(x, y))


def pos(b, ref):
    fp = b.FindFootprintByReference(ref)
    return bl.to_board(fp.GetPosition()) + (fp.GetOrientationDegrees(),)


def m_y2_round2(b):
    """Y2/C78/C79 back at their round-2 positions (verifier finding: corridor 1.71 mm)."""
    move(b, "Y2", 35.30, 48.60, 0)
    move(b, "C79", 35.55, 50.45, 180)
    move(b, "C78", 33.70, 50.45, 180)


def m_y2_round2_north(b):
    """Round-2 Y2 0.6 mm further north (the verifier's mutation, corridor 1.1 mm)."""
    move(b, "Y2", 35.30, 48.00, 0)
    move(b, "C79", 35.55, 49.85, 180)
    move(b, "C78", 33.70, 49.85, 180)


def m_y2_north_1p1(b):
    """Today's Y2 group 1.1 mm north (corridor 2.31 mm < 2.4)."""
    for r in ("Y2", "C78", "C79"):
        x, y, rot = pos(b, r)
        move(b, r, x, y - 1.1)


def m_r56_flip(b):
    """R56 (TXP 0R bridge) rotated 180 deg: TXP and TXP_J pads swap sides."""
    x, y, rot = pos(b, "R56")
    move(b, "R56", x, y, rot + 180)


def m_u10_north(b):
    """U10 back 2.5 mm north (round-2 height): the FSPI clock can no longer run over its top row."""
    x, y, rot = pos(b, "U10")
    move(b, "U10", x, y - 2.5)


def m_trial_no_sep(b):
    """Board unchanged; trial router run WITHOUT the D-108 TX/RX separation and link-gap rules (the round-3 router):
    the exact TX/RX separation check must FAIL."""
    return {"TRIAL_NO_SEP": "1"}


def m_c23_east(b):
    """C23 0.9 mm east, into the CMD (J2.3) line: the SD supply pocket / trial must FAIL."""
    x, y, rot = pos(b, "C23")
    move(b, "C23", x + 0.9, y)


MUTATIONS = [m_y2_round2, m_y2_round2_north, m_y2_north_1p1, m_r56_flip, m_u10_north, m_trial_no_sep, m_c23_east]


def main():
    os.makedirs(OUT, exist_ok=True)
    lines = []
    for m in MUTATIONS:
        b = pcbnew.LoadBoard(bl.BOARD_FILE)
        extra = m(b) or {}
        path = os.path.join(OUT, m.__name__ + ".kicad_pcb")
        pcbnew.SaveBoard(path, b)
        env = dict(os.environ, PCB_BOARD=path, TRIAL_TAG=m.__name__, **extra)
        p = subprocess.run([PY, os.path.join(bl.HERE, "check_placement.py")], env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        fails = [ln for ln in p.stdout.splitlines() if ln.startswith("FAIL")]
        summ = [ln for ln in p.stdout.splitlines() if ln.startswith("SUMMARY")]
        lines.append("== %s: %s\n   %s" % (m.__name__, m.__doc__.strip(), summ[0] if summ else "no summary"))
        for ln in fails:
            lines.append("   " + " ".join(ln.split())[:220])
        print(lines[-1 - len(fails)], flush=True)
    with open(os.path.join(bl.PCB_DIR, "trial", "mutations.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
