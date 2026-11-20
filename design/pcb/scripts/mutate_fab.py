#!/usr/bin/env python3
"""Self-test of check_fab.py (TP-L6, D-132): each mutation corrupts a copy of design/pcb/fab/ in a temp folder and
check_fab.py must report FAIL on the named check; the unmodified copy (control) must pass.

    design/.venv/bin/python -I design/pcb/scripts/mutate_fab.py     -> prints one line per mutation + summary
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAB = os.path.normpath(os.path.join(HERE, "..", "fab"))
G = "gerbers/rv1106-reva-"


def sub(path, pat, rep, count=1):
    def f(root):
        p = os.path.join(root, path)
        t = open(p).read()
        t2 = re.sub(pat, rep, t, count=count, flags=re.M)
        if t2 == t:
            raise SystemExit("mutation pattern not found: %s %s" % (path, pat))
        open(p, "w").write(t2)
    return f


MUTATIONS = [
    ("control", None, None),
    ("CPL row deleted (C1)", sub("jlc-cpl.csv", r"^C1,.*\n", ""), "L6-cplrefs"),
    ("CPL row duplicated (U9)", sub("jlc-cpl.csv", r"^(U9,.*\n)", r"\1\1"), "L6-cplrefs"),
    ("CPL test pad added", sub("jlc-cpl.csv", r"^(U9,.*\n)", r"\1TP1,10.0000,10.0000,Top,0\n"), "L6-cplrefs"),
    ("CPL U9 x + 0.02 mm", sub("jlc-cpl.csv", r"^U9,39\.5000,", "U9,39.5200,"), "L6-cplxy"),
    ("CPL Q2 rotation 0 (others 180)", sub("jlc-cpl.csv", r"^(Q2,[^,]+,[^,]+,Top,)180", r"\g<1>0"), "L6-cplrot"),
    ("BOM LCSC blanked (Y2)", sub("jlc-bom.csv", r",C32346$", ","), "L6-lcsc"),
    ("BOM ref dropped (R2)", sub("jlc-bom.csv", r'"R1,R2"', "R1"), "L6-bomrefs"),
    ("BOM LCSC changed (U8)", sub("jlc-bom.csv", r",C55136$", ",C55137"), "L6-bomsrc"),
    ("drill: one via hit removed", sub(G + "PTH.drl", r"^T1\n(X[^\n]+\n)", "T1\n"), "L6-vias"),
    ("drill: via moved 0.05 mm", sub(G + "PTH.drl", r"^T1\nX([\d.]+)Y", lambda m: "T1\nX%.3fY" % (float(m.group(1)) + 0.05)), "L6-viapos"),
    ("drill: NPTH tooling hole removed", sub(G + "NPTH.drl", r"^T3\n(X[^\n]+\n)", "T3\n"), "L6-holes"),
    ("V-CUT extra line", sub(G + "V-CUT.gbr", r"^M02\*", "X45000000Y0D02*\nX45000000Y80000000D01*\nM02*"), "L6-vcut"),
    ("Edge.Cuts piece removed", sub(G + "Edge_Cuts.gm1", r"^(X\d+Y\d+D01\*)$", ""), "L6-outline"),
    ("F.Cu flash outside the outline", sub(G + "F_Cu.gtl", r"^M02\*", "D11*\nX95000000Y40000000D03*\nM02*"), "L6-inside"),
    ("F.Cu 1.7 mm pad 0.65 mm from the V-cut", sub(G + "F_Cu.gtl", r"^M02\*", "D12*\nX6500000Y40000000D03*\nM02*"), "L6-vcutcu"),
    ("not-assembled list loses JP1", sub("jlc-bom-not-assembled.csv", r"^JP1,.*\n", ""), "L6-dnp"),
    ("rotation table says SOT-23 +90", sub("cpl-rotations.md", r"(\| SOT-23 \| .*?)\*\*\+180°\*\*", r"\1**+90°**"), "L6-cplrot"),
]


def main():
    ok_all = True
    caught = 0
    for name, mut, tag in MUTATIONS:
        tmp = tempfile.mkdtemp(prefix="mutfab_")
        dst = os.path.join(tmp, "fab")
        shutil.copytree(FAB, dst, ignore=shutil.ignore_patterns("gerber-view"))
        if mut:
            mut(dst)
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "check_fab.py")], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, env=dict(os.environ, FAB_DIR=dst))
        fails = sorted(set(m.group(1) for m in re.finditer(r"^FAIL (\S+)", r.stdout, re.M)))
        if mut is None:
            good = not fails and r.returncode == 0
        else:
            good = tag in fails
            caught += good
        ok_all &= good
        print("%s %-36s expected %-11s got FAIL %s" % ("OK  " if good else "MISS", name, tag or "no FAIL", fails or "none"))
        shutil.rmtree(tmp, ignore_errors=True)
    n = len(MUTATIONS) - 1
    print("mutate_fab: %d of %d mutations caught, control %s" % (caught, n, "clean" if ok_all or caught < n else "?"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
