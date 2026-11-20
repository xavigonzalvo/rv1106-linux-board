#!/usr/bin/env python3
"""Layout phase L5F step 4 (KiCad Python; D-H6 items 4, 7, 9; D-117 d, f, h): zones and outline.

    $PY design/pcb/scripts/l5f_board.py         # edits the saved board; writes design/pcb/l5f/board.json

1. V-cut clearance (item 4): every copper zone outline is clipped to x 0.80 .. 79.20 (the four full-board GND pours /
   planes of F, In1, In2, B started at x 0.40); fills follow at the next fill_zones.py.
2. L4 hops of the USB / ETH pairs (item 7): an In2 GND island (zone, priority 3, solid connection) under every
   cluster of L4 pair segments: the bounding box of the cluster's L4 segments + 0.60 mm. Inside it the In2 power
   region (VCC_3V3 under the ETH TX hop and the USB_DM hop) gives way to GND; plane vias of the power net inside an
   island would lose their plane, so an island that would contain one is shrunk away from it (reported).
3. Outline (item 9): the four corners of the 80 x 80 board itself get R 1 mm arcs. The rails join the board along the
   V-cuts at x = 0 / 80, so each corner is a small routed notch in the panel outline (round 2, D-118 c: 1.5 x 1.5 mm,
   so a 1.0 mm router bit clears the board arc): rail edge -> 1.5 mm wall into the rail -> R 0.5 mm -> notch floor
   at y = 1.5 (78.5) -> R 0.5 mm arc that meets the R 1 mm board-corner arc tangentially at (0, 1) on the V-cut line
   -> board edge. Every air-side corner is R 0.5 mm; the only material fillet (under the R 0.5 mm arc next to the
   board) lies on the rail side of the V-cut and leaves with the rail.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402
import routelib as rl  # noqa: E402

import pcbnew  # noqa: E402

OUT = os.path.join(bl.PCB_DIR, "l5f", "board.json")
XMIN, XMAX = 0.80, 79.20
PAIRS = ("USB_DP", "USB_DM", "USBA_DP", "USBA_DM", "USBC_DP", "USBC_DM", "ETH_TX", "ETH_RX")
L3 = ("VDD_0V9", "VCC_3V3", "VCC5V0_SYS", "VBUS_USBA")


def clip_zones(board, log):
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        o = z.Outline()
        changed = False
        for i in range(o.TotalVertices()):
            v = o.CVertex(i)
            x, y = bl.to_board(v)
            nx = min(max(x, XMIN), XMAX)
            if abs(nx - x) > 1e-6:
                o.SetVertex(i, bl.to_page(nx, y))
                changed = True
        if changed:
            log.append("zone %s (%s): outline clipped to x %.2f .. %.2f" % (z.GetZoneName(), z.GetNetname(), XMIN,
                                                                           XMAX))


def hop_islands(board, log):
    segs = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.B_Cu and t.GetNetname().startswith(PAIRS):
            a, b = bl.to_board(t.GetStart()), bl.to_board(t.GetEnd())
            segs.append([min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), {t.GetNetname()}])
    # cluster boxes that come within 1.5 mm of each other
    changed = True
    while changed:
        changed = False
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                a, b = segs[i], segs[j]
                if a[0] - 1.5 <= b[2] and b[0] - 1.5 <= a[2] and a[1] - 1.5 <= b[3] and b[1] - 1.5 <= a[3]:
                    segs[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]), a[4] | b[4]]
                    del segs[j]
                    changed = True
                    break
            if changed:
                break
    pv = [(t.GetNetname(), ) + bl.to_board(t.GetPosition()) for t in board.GetTracks()
          if t.GetClass() == "PCB_VIA" and t.GetNetname() in L3]
    out = []
    for k, (x0, y0, x1, y1, nets) in enumerate(sorted(segs)):
        r = [x0 - 0.6, y0 - 0.6, x1 + 0.6, y1 + 0.6]
        # keep power-plane vias outside the island (+ 0.55 mm: via ring + plane clearance)
        for n, vx, vy in pv:
            if r[0] - 0.55 < vx < r[2] + 0.55 and r[1] - 0.55 < vy < r[3] + 0.55:
                # shrink the side nearest to the via
                dists = [(vx - r[0], 0), (r[2] - vx, 2), (vy - r[1], 1), (r[3] - vy, 3)]
                d, side = min(dists)
                if side == 0:
                    r[0] = vx + 0.55
                elif side == 2:
                    r[2] = vx - 0.55
                elif side == 1:
                    r[1] = vy + 0.55
                else:
                    r[3] = vy - 0.55
                log.append("  island %d: shrunk away from the %s via (%.2f, %.2f)" % (k, n, vx, vy))
        z = pcbnew.ZONE(board)
        z.SetLayer(pcbnew.In2_Cu)
        z.SetNet(rl.net_item(board, "GND"))
        z.SetZoneName("In2_GND_HOP_%d" % k)
        z.SetAssignedPriority(3)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocalClearance(pcbnew.FromMM(0.2))      # GND island: 0.20 mm anti-pads (the planes use 0.30 mm)
        z.SetMinThickness(pcbnew.FromMM(0.15))
        o = z.Outline()
        o.NewOutline()
        for x, y in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])):
            p = bl.to_page(x, y)
            o.Append(p.x, p.y)
        board.Add(z)
        out.append({"name": z.GetZoneName(), "rect": [round(v, 3) for v in r], "nets": sorted(nets)})
        log.append("In2 GND island %s (%.2f, %.2f)-(%.2f, %.2f) under %s" % (z.GetZoneName(), r[0], r[1], r[2], r[3],
                                                                              " ".join(sorted(nets))))
    return out


NOTCH = 1.5      # D-118 c (round 2): rail notch at each board corner, NOTCH x NOTCH mm (was 1.0 x 1.0)


def seg(board, x0, y0, x1, y1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.1))
    s.SetStart(bl.to_page(x0, y0))
    s.SetEnd(bl.to_page(x1, y1))
    board.Add(s)
    return s


def arc(board, cx, cy, sx, sy, ex, ey):
    """arc centre (cx, cy) from (sx, sy) to (ex, ey) through the shorter side"""
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.1))
    a0 = math.atan2(sy - cy, sx - cx)
    a1 = math.atan2(ey - cy, ex - cx)
    d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    r = math.hypot(sx - cx, sy - cy)
    m = (cx + r * math.cos(a0 + d / 2), cy + r * math.sin(a0 + d / 2))
    s.SetArcGeometry(bl.to_page(sx, sy), bl.to_page(*m), bl.to_page(ex, ey))
    board.Add(s)
    return s


def outline(board, log):
    """replace the north and south panel edges (y = 0 / 80, straight from x -4 to 84) by edges with the 4 notches"""
    dead = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            a, b = bl.to_board(d.GetStart()), bl.to_board(d.GetEnd())
            if abs(a[1] - b[1]) < 1e-6 and abs(a[1]) < 1e-6 or abs(a[1] - b[1]) < 1e-6 and abs(a[1] - 80) < 1e-6:
                dead.append(d)
    assert len(dead) == 2, len(dead)
    for d in dead:
        board.Remove(d)
    for y0, s in ((0.0, 1), (80.0, -1)):          # s: +1 north edge (inside is +y), -1 south edge
        y1 = y0 + s * 1.0                                    # end of the R 1 board-corner arc on the V-cut line
        y15 = y0 + s * NOTCH
        for sx, x0 in ((1, 0.0), (-1, 80.0)):                # sx: +1 west V-cut (rail at x < 0), -1 east (x > 80)
            xr = x0 - sx * NOTCH                             # rail-side wall of the notch
            seg(board, x0 - sx * 4.0, y0, xr, y0)                                    # rail edge
            seg(board, xr, y0, xr, y1)                                               # notch wall in the rail
            arc(board, xr + sx * 0.5, y1, xr, y1, xr + sx * 0.5, y15)                # R 0.5 inner corner (rail side)
            seg(board, xr + sx * 0.5, y15, x0 - sx * 0.5, y15)                       # notch floor
            arc(board, x0 - sx * 0.5, y1, x0 - sx * 0.5, y15, x0, y1)                # R 0.5 into the board arc
            arc(board, x0 + sx * 1.0, y1, x0, y1, x0 + sx * 1.0, y0)                 # R 1 board corner
        seg(board, 1.0, y0, 79.0, y0)                        # board edge
    log.append("outline: R 1 mm arcs at the 4 corners of the 80 x 80 board; %.1f x %.1f mm routed notches into the "
               "rails, every air-side corner R 0.5 mm (1.0 mm router bit; the notch floor meets the board arc "
               "tangentially at the V-cut line, its material fillet lies on the rail side; D-118 c)" % (NOTCH, NOTCH))


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    if any(z.GetZoneName().startswith("In2_GND_HOP") for z in board.Zones()):
        sys.exit("l5f_board already applied: run design/pcb/scripts/rebuild_all.sh")
    log = []
    clip_zones(board, log)
    isl = hop_islands(board, log)
    outline(board, log)
    pcbnew.SaveBoard(bl.BOARD_FILE, board)
    json.dump({"islands": isl, "log": log}, open(OUT, "w"), indent=1)
    for line in log:
        print(line)


if __name__ == "__main__":
    main()
