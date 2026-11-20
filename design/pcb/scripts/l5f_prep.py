#!/usr/bin/env python3
"""Layout phase L5F step 1 (KiCad Python; owner decision D-H6, D-117): rip the copper the L5F fixes replace and make
the local part moves inside the buck cells, on the L5 board.

    $PY design/pcb/scripts/l5f_prep.py          # edits design/pcb/rv1106-reva.kicad_pcb; writes design/pcb/l5f/prep.json

1. Buck input loops (D-H6 item 1, D-117 a): the 10 uF input capacitor of U5 / U6 / U7 (C8 / C9 / C10) moves from
   the south-east of the cell to just south of the IC, turned 180 deg (GND pad west, under the GND strap that runs
   down between pins 3 and 4); in U4 (whose input caps sat east / south) the 100 nF C12 takes the east slot of the
   other cells' 100 nF (turned 90 deg: GND pad at the strap height, VIN pad at pin 4) and the 10 uF C7 the south slot.
   Their old plane vias and pad links are removed (l5f_route.py places new ones), as is the pin-4 VCC5V0_SYS via that
   sat under the IC body (the GND strap passes there). Pin 2 of U4-U7 and the input caps' GND pads connect to the L1
   pour solidly (no thermal spokes).
2. The enable nets U4_EN, U6_EN, VCC_DDR_1V8_EN and PWR_EN are removed completely (their F.Cu runs crossed under the
   IC bodies where the strap goes, PWR_EN ran 0.38 mm from L3.1 inside L3's courtyard, the U6_EN via sat in L3's
   courtyard: D-H6 item 5); l5f_route.py routes them again.
3. V-cut (D-H6 item 4; round 2, D-118 a): the west-edge ends of HDR_PWM9, HDR_SPI0_SCLK and HDR_SPI0_MOSI
   (x 0.66-0.76) are removed from their last lane bend to the J5 pad, and the corridor pieces of the three neighbour
   lanes that make room for them (HDR_PWM11 from its lane bend to J5.35, the straight runs of HDR_GPIO1_B0 and
   HDR_GPIO1_B1 past the new HDR_PWM9 via); l5f_route.py routes them again >= 0.8 mm from the V-cut.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "l5f", "prep.json")
# (ref): (board x, y of the footprint position, orientation deg) - D-117 a (local moves inside the buck cells, D-H6)
MOVES = {"C8": (72.35, 46.64, 180.0), "C9": (72.35, 19.64, 180.0), "C10": (72.35, 28.64, 180.0),
         "C7": (73.55, 37.64, 180.0), "C12": (75.00, 35.67, 90.0)}
RIP_NETS = ("U4_EN", "U6_EN", "VCC_DDR_1V8_EN", "PWR_EN")
VCUT_NETS = ("HDR_PWM9", "HDR_SPI0_SCLK", "HDR_SPI0_MOSI")     # D-118 a (round 2): re-routed >= 0.8 mm
# D-118 a: neighbour lane pieces re-drawn by l5f_route.py (net: board-mm box; every piece / via wholly inside is removed)
VCUT_RIP = {"HDR_PWM11": (1.0, 23.3, 2.75, 52.5), "HDR_GPIO1_B0": (1.60, 26.5, 1.70, 54.0),
            "HDR_GPIO1_B1": (1.90, 31.2, 1.95, 50.9)}
SOLID = [("U4", "2"), ("U5", "2"), ("U6", "2"), ("U7", "2")]


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    for g in board.Groups():
        if g.GetName().startswith("L5F"):
            sys.exit("L5F groups already on the board: run design/pcb/scripts/rebuild_all.sh")
    moved_pads = {}
    for ref in MOVES:
        fp = board.FindFootprintByReference(ref)
        moved_pads[ref] = [(p.GetNetname(), bl.pad_polygon(p)) for p in fp.Pads()]
    ics = {u: bl.courtyard_bbox(board.FindFootprintByReference(u)) for u in ("U4", "U5", "U6", "U7")}
    pin4 = {u: bl.pad_polygon([p for p in board.FindFootprintByReference(u).Pads() if p.GetNumber() == "4"][0])
            for u in ics}
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    dead, log = [], []

    def inpad(p, polys):
        return any(bl._inside(p[0], p[1], poly) for poly in polys)
    # 1. pad links of the moved caps and the under-body pin-4 via
    via_at = {}
    for v in vias:
        x, y = bl.to_board(v.GetPosition())
        via_at[(round(x, 3), round(y, 3), v.GetNetname())] = v
    rip_vias = []
    for t in tracks:
        a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
        n = t.GetNetname()
        for ref, pads in moved_pads.items():
            polys = [poly for net, poly in pads if net == n]
            if polys and (inpad(a, polys) or inpad(b, polys)) and t not in dead:
                dead.append(t)
                log.append("pad link %s %s (%.2f,%.2f)-(%.2f,%.2f)" % (ref, n, a[0], a[1], b[0], b[1]))
                for q in (a, b):
                    v = via_at.get((round(q[0], 3), round(q[1], 3), n))
                    if v is not None:
                        (rip_vias.append(v) if v not in rip_vias else None)
        if n == "VCC5V0_SYS":
            for u, c in ics.items():
                for q, o in ((a, b), (b, a)):
                    v = via_at.get((round(q[0], 3), round(q[1], 3), n))
                    if v is not None and c[0] < q[0] < c[2] and c[1] < q[1] < c[3] and bl._inside(o[0], o[1], pin4[u]) \
                            and t not in dead:
                        dead.append(t)
                        (rip_vias.append(v) if v not in rip_vias else None)
                        log.append("under-body pin-4 via %s (%.2f,%.2f)" % (u, q[0], q[1]))
    # vias left inside a moved cap's new footprint area are caught by DRC; the old cap's own vias are ripped above
    # 2. enable nets
    for t in tracks:
        if t.GetNetname() in RIP_NETS and t not in dead:
            dead.append(t)
    for v in vias:
        if v.GetNetname() in RIP_NETS:
            (rip_vias.append(v) if v not in rip_vias else None)
    # 3. V-cut lane ends: every piece of the three nets whose end points all lie at x < 3.05 and y > 18.3 (west edge,
    # from the last lane bend to the J5 pad)
    for t in tracks:
        if t.GetNetname() in VCUT_NETS:
            a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if max(a[0], b[0]) < 3.05 and min(a[1], b[1]) > 18.3 and t not in dead:
                dead.append(t)
                log.append("v-cut %s (%.2f,%.2f)-(%.2f,%.2f)" % (t.GetNetname(), a[0], a[1], b[0], b[1]))
    for v in vias:
        if v.GetNetname() in VCUT_NETS:
            x, y = bl.to_board(v.GetPosition())
            if x < 3.05 and y > 18.3:
                (rip_vias.append(v) if v not in rip_vias else None)
    for t in tracks:
        box = VCUT_RIP.get(t.GetNetname())
        if box and t not in dead:
            a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            if all(box[0] <= q[0] <= box[2] and box[1] <= q[1] <= box[3] for q in (a, b)):
                dead.append(t)
                log.append("v-cut neighbour %s (%.2f,%.2f)-(%.2f,%.2f)" % (t.GetNetname(), a[0], a[1], b[0], b[1]))
    for v in vias:
        box = VCUT_RIP.get(v.GetNetname())
        if box:
            x, y = bl.to_board(v.GetPosition())
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                (rip_vias.append(v) if v not in rip_vias else None)
    nt, nv = len(dead), len(rip_vias)
    for o in dead + list(rip_vias):
        board.Remove(o)
    # moves
    for ref, (x, y, rot) in sorted(MOVES.items()):
        fp = board.FindFootprintByReference(ref)
        ox, oy = bl.to_board(fp.GetPosition())
        o0 = fp.GetOrientationDegrees()
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(bl.to_page(x, y))
        log.append("move %s (%.2f, %.2f) %.0f deg -> (%.2f, %.2f) %.0f deg" % (ref, ox, oy, o0, x, y, rot))
    # solid zone connection: IC pin 2 and the input caps' GND pads
    for ref, num in SOLID + [(c, "2") for c in ("C7", "C8", "C9", "C10", "C12", "C13", "C14", "C15")]:
        p = [q for q in board.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
        assert p.GetNetname() == "GND", (ref, num)
        p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"removed_tracks": nt, "removed_vias": nv, "log": log, "moves": MOVES}, open(OUT, "w"), indent=1)
    print("l5f_prep: removed %d tracks and %d vias; moved %s; pin 2 / input-cap GND pads solid" % (
        nt, nv, " ".join(sorted(MOVES))))


if __name__ == "__main__":
    main()
