#!/usr/bin/env python3
"""Layout phase L5, step 2 (KiCad Python): Freerouting 2.5.0 for the remaining low-speed nets.

    $PY design/pcb/scripts/l5_freeroute.py [--rerun] [--passes N]

1. Export: the saved board (after L5_LANES) is loaded in memory, every existing track and via is locked (exported as
   `(type fix)`: Freerouting cannot move the L3/L4 copper or the lane stubs), every copper pour and every rule area
   except the M3 hole keep-outs is dropped from the copy (the L2/L3 planes are complete; their nets are taken out of the
   DSN network below so their pads are plain obstacles), In1/In2 are typed 'power' (no routing there), and
   pcbnew.ExportSpecctraDSN writes design/pcb/l5/fr/in.dsn (in a child process). The board file is not changed.
2. DSN edits (text, deterministic), so that Freerouting sees the rules KiCad's DSN export leaves out:
   - plane nets GND, VCC_3V3, VDD_0V9, VCC5V0_SYS, VBUS_USBA removed from the network (pads stay as obstacles);
   - keep-outs: the panel rails and a 0.40 mm strip along every board edge (layout.md §1, DRU edge clearance), the
     U9 fan square on L1 (DRU neck-down area: the lane stubs of l5_lanes.py carry the nets out of it), the crystal
     guard (no other net on L1 within 1 mm of the Y1/Y2/C76-C79 pads, nothing on L4 under Y1/Y2; layout.md §4.3), L4
     and vias under the four buck SW nodes (§4.5); via keep-outs = the L4 router's no-via areas (VDD_0V9 neck and
     free strips, L3 escape fingers, the ring-1 band, U9/U11/U1/J1 courtyards; D-110, D-111) so no new via perforates
     the VDD_0V9 neck or sits in a lane channel;
   - the lane nets get their own class LANE: 0.10 mm wide, 0.15 mm clearance (D-113: the lanes leave the ring-1
     row at 0.30 mm pitch; l5_cleanup.py widens them to 0.15 mm wherever the exact check allows);
   - VDD_ARM (class PWR_0V9, 0.80 mm) is routed at 0.30 mm here and widened by l5_cleanup.py (test-pad branch to TP15).
3. Freerouting (owner-supplied jar, Java >= 25 from Homebrew) runs headless: -de in.dsn -do out.ses -mp N. The session
   design/pcb/l5/fr/out.ses is kept with the design: a rebuild re-imports it (Freerouting's result is not bit-for-bit
   repeatable between runs); --rerun forces a new Freerouting run.
4. Import: pcbnew.ImportSpecctraSES on a second in-memory copy of the board; the tracks and vias that are not in the
   board already are written to design/pcb/l5/fr_raw.json (board mm) for l5_cleanup.py. Nothing is written to the board
   here: cleanup, the exact rule check and the write (l5_write.py, group L5_FREEROUTE) come next.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402

FR_DIR = os.path.join(bl.PCB_DIR, "l5", "fr")
DSN = os.path.join(FR_DIR, "in.dsn")
SES = os.path.join(FR_DIR, "out.ses")
RAW = os.path.join(bl.PCB_DIR, "l5", "fr_raw.json")
LANES = os.path.join(bl.PCB_DIR, "l5", "lanes.json")
GEO = os.path.join(bl.PCB_DIR, "l5", "board_geo.json")      # l4_export.py of the board before the lane stubs
JAVA = "/opt/homebrew/opt/openjdk/bin/java"
JAR = os.path.join(bl.DESIGN, "..", "thirdparty", "freerouting-2.5.0", "freerouting-2.5.0.jar")
PLANE_NETS = ("GND", "VCC_3V3", "VDD_0V9", "VCC5V0_SYS", "VBUS_USBA")
XTAL_GUARD = ("Y1", "Y2", "C76", "C77", "C78", "C79")
LANE_W = 100          # um
ROUTE_W = {"PWR_0V9": 300}     # class -> routing width (um) in the DSN
# class -> clearance (um) in the DSN. Freerouting applies the clearance of the class it routes against the obstacle
# without KiCad's "larger of the two classes" rule, so DEFAULT is raised to the 0.20 mm of the power/SDMMC/FSPI
# classes (conservative for DEFAULT-DEFAULT pairs), and the pair classes carry the 30 mil pair rule of the DRU.
CLR = {"kicad_default": 200, "USB_DIFF": 760, "ETH_DIFF": 760}
LANE_CLR = 200


def um(x, y):
    """board mm -> DSN um (page coordinates, y up)"""
    return "%.1f %.1f" % ((x + bl.ORIGIN[0]) * 1000.0, -(y + bl.ORIGIN[1]) * 1000.0)


def rect(kind, layer, r):
    x0, y0, x1, y1 = r
    pts = " ".join(um(*p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)))
    return '    (%s "" (polygon %s 0 %s))' % (kind, layer, pts)


def export(board):
    for t in board.GetTracks():
        t.SetLocked(True)
    drop = [z for z in board.Zones() if not z.GetZoneName().startswith("KEEPOUT_")]
    for z in drop:
        board.Remove(z)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    os.makedirs(FR_DIR, exist_ok=True)
    if not pcbnew.ExportSpecctraDSN(board, DSN):
        sys.exit("ExportSpecctraDSN failed")


def pad_bbox(geo, ref):
    xs = [q[0] for p in geo["pads"] if p["ref"] == ref for q in p["poly"]]
    ys = [q[1] for p in geo["pads"] if p["ref"] == ref for q in p["poly"]]
    return min(xs), min(ys), max(xs), max(ys)


def patch(geo, lanes):
    s = open(DSN).read()
    # 1. plane nets out of the network and the class lists
    i = s.index("(network")
    head, net = s[:i], s[i:]
    j = net.index("(class ")
    net_re = re.compile(r'\(net ("[^"]*"|\S+)\s*\(pins[^)]*\)\s*\)\s*')
    nets_part = net_re.sub(lambda m: "" if m.group(1).strip('"') in PLANE_NETS else m.group(0), net[:j])
    cls = net[j:]
    lane_nets = sorted(lanes["stubs"])

    def cl(m):
        names = [n for n in m.group(2).split() if n.strip('"') not in PLANE_NETS and n.strip('"') not in lane_nets]
        return "(class %s %s\n" % (m.group(1), " ".join(names))
    cls = re.sub(r"\(class (\S+)((?:\s+[^\s()]+)*)\s*\n", cl, cls)
    for c, v in CLR.items():
        cls = re.sub(r"(\(class %s [^()]*\(circuit[^)]*\)\s*\)\s*\(rule\s*\(width \d+\)\s*\(clearance )\d+" % c,
                     lambda m: m.group(1) + str(v), cls)
    for c, w in ROUTE_W.items():
        cls = re.sub(r"(\(class %s [^()]*\(circuit[^)]*\)\s*\)\s*\(rule\s*\(width )\d+" % c,
                     lambda m: m.group(1) + str(w), cls)
    lane_cls = ('(class LANE %s\n      (circuit\n        (use_via "Via[0-3]_500:300_um")\n      )\n'
                '      (rule\n        (width %d)\n        (clearance %d)\n      )\n    )\n    ' %
                (" ".join(lane_nets), LANE_W, LANE_CLR))
    cls = lane_cls + cls
    s = head + nets_part + cls
    # inner layers out of the structure (Freerouting treats a 'power' layer without a plane as a signal layer and
    # routes on it); their pad/via shapes go with them
    s = re.sub(r"\n    \(layer In[12]\.Cu\n      \(type \w+\)\n      \(property\n        \(index \d\)\n      \)\n    \)", "", s)
    s = re.sub(r"\n\s*\(shape \(\w+ In[12]\.Cu [^()]*\)\)", "", s)
    s = re.sub(r"\n\s*\(keepout \"\" \(polygon In[12]\.Cu 0[^)]*\)\)", "", s)
    s = re.sub(r"\n\s*\(keepout \"\" \(circle In[12]\.Cu [^)]*\)\)", "", s)
    # wires and vias of the plane nets: no net (plain obstacles), the nets are no longer in the network
    s = re.sub(r"\(net (%s)\)" % "|".join(PLANE_NETS), "", s)
    # 2. keep-outs
    ko = []
    for L in ("F.Cu", "B.Cu"):
        for r in ((-6.0, -1.0, 0.40, 81.0), (79.60, -1.0, 86.0, 81.0), (-6.0, -1.0, 86.0, 0.40),
                  (-6.0, 79.60, 86.0, 81.0)):
            ko.append(rect("keepout", L, r))
    ko.append(rect("keepout", "F.Cu", (26.6, 28.6, 42.4, 44.4)))             # U9_FAN (lanes leave by their stubs)
    ko.append(rect("keepout", "B.Cu", (26.6, 28.6, 42.4, 44.4)))             # L4 under U9: kept for inner-via nets
    for ref in XTAL_GUARD:
        x0, y0, x1, y1 = pad_bbox(geo, ref)
        ko.append(rect("keepout", "F.Cu", (x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0)))
    for ref in ("Y1", "Y2"):
        ko.append(rect("keepout", "B.Cu", geo["court"][ref]))
    for r in lanes["sw_areas"]:
        ko.append(rect("keepout", "B.Cu", r))
    for r in lanes["novia"]:
        ko.append(rect("via_keepout", "F.Cu", r))
    marker = '    (via "Via[0-3]_500:300_um")\n    (rule'
    assert marker in s
    s = s.replace(marker, "\n".join(ko) + "\n" + marker, 1)
    open(DSN, "w").write(s)
    print("DSN: %s (%d keep-outs added, %d lane nets in class LANE)" % (DSN, len(ko), len(lane_nets)))


def run_freerouting(passes):
    cmd = [JAVA, "-jar", os.path.normpath(JAR), "-de", DSN, "-do", SES, "-mp", str(passes), "--gui.enabled=false"]
    print("running:", " ".join(cmd))
    log = open(os.path.join(FR_DIR, "freerouting.log"), "w")
    rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=FR_DIR)
    print("freerouting exit", rc)
    if not os.path.exists(SES):
        sys.exit("no session file written")


def key(p):
    return (round(p[0], 3), round(p[1], 3))


def import_new():
    base = pcbnew.LoadBoard(bl.BOARD_FILE)
    old_t = set()
    old_v = set()
    for t in base.GetTracks():
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            old_v.add((n,) + key(bl.to_board(t.GetPosition())))
        else:
            a, b = key(bl.to_board(t.GetStart())), key(bl.to_board(t.GetEnd()))
            old_t.add((n, t.GetLayer(), min(a, b), max(a, b)))
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    if not pcbnew.ImportSpecctraSES(board, SES):
        sys.exit("ImportSpecctraSES failed")
    out = {}
    nt = nv = 0
    for t in board.GetTracks():
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            x, y = bl.to_board(t.GetPosition())
            if (n,) + key((x, y)) in old_v:
                continue
            out.setdefault(n, {"tracks": [], "vias": []})["vias"].append([round(x, 4), round(y, 4)])
            nv += 1
        else:
            a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if (n, t.GetLayer(), min(key(a), key(b)), max(key(a), key(b))) in old_t:
                continue
            lay = "F" if t.GetLayer() == pcbnew.F_Cu else "B" if t.GetLayer() == pcbnew.B_Cu else "?"
            out.setdefault(n, {"tracks": [], "vias": []})["tracks"].append(
                [lay, [[round(a[0], 4), round(a[1], 4)], [round(b[0], 4), round(b[1], 4)]],
                 round(pcbnew.ToMM(t.GetWidth()), 4)])
            nt += 1
    json.dump({"routes": out}, open(RAW, "w"), indent=0, sort_keys=True)
    print("SES import: %d new track segments, %d new vias on %d nets -> %s" % (nt, nv, len(out), RAW))


def main():
    rerun = "--rerun" in sys.argv
    passes = int(sys.argv[sys.argv.index("--passes") + 1]) if "--passes" in sys.argv else 40
    if "--export" in sys.argv:          # child process: pcbnew Remove() leaves SWIG unusable for later boards
        export(pcbnew.LoadBoard(bl.BOARD_FILE))
        return
    lanes = json.load(open(LANES))
    geo = json.load(open(GEO))
    if subprocess.call([sys.executable, os.path.abspath(__file__), "--export"]) != 0:
        sys.exit("DSN export failed")
    patch(geo, lanes)
    left = [ln for ln in open(DSN) if "In1.Cu" in ln or "In2.Cu" in ln]
    if left:
        sys.exit("DSN still names an inner layer: %s" % left[:3])
    if rerun or not os.path.exists(SES):
        run_freerouting(passes)
    else:
        print("re-using the stored session %s (--rerun runs Freerouting again)" % SES)
    import_new()


if __name__ == "__main__":
    main()
