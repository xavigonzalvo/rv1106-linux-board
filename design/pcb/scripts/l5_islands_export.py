#!/usr/bin/env python3
"""Layout phase L5 round 2 (KiCad Python): list the pieces of the L1/L4 GND pours that hold no GND via (D-114 h).

    $PY design/pcb/scripts/l5_islands_export.py      # after fill_zones.py; writes design/pcb/l5/islands.json

A pour piece without a GND via hangs on its pads' thermal spokes only; KiCad reports a 'starved_thermal' error when such
a piece reaches a through-hole GND pad with one spoke (J5.14 after the header lanes in round 2). l5_islands.py puts a
GND via into every such piece where one fits. Pieces smaller than 1 mm2 are skipped (no via fits).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402

import pcbnew  # noqa: E402


def main():
    board = pcbnew.LoadBoard(bl.BOARD_FILE)
    gv = [bl.to_board(t.GetPosition()) for t in board.GetTracks()
          if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    out = []
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for lay, name in ((pcbnew.F_Cu, "F"), (pcbnew.B_Cu, "B")):
            if not (z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay)):
                continue
            ps = z.GetFilledPolysList(lay)
            for i in range(ps.OutlineCount()):
                one = pcbnew.SHAPE_POLY_SET()
                one.AddOutline(ps.Outline(i))
                for h in range(ps.HoleCount(i)):
                    one.AddHole(ps.Hole(i, h))
                area = one.Area() / 1e12
                if area < 1.0:
                    continue
                if any(one.Contains(pcbnew.VECTOR2I(bl.to_page(x, y))) for x, y in gv):
                    continue
                o = ps.Outline(i)
                pts = [bl.to_board(o.CPoint(k)) for k in range(o.PointCount())]
                holes = []
                for h in range(ps.HoleCount(i)):
                    hc = ps.Hole(i, h)
                    holes.append([bl.to_board(hc.CPoint(k)) for k in range(hc.PointCount())])
                out.append({"layer": name, "zone": z.GetZoneName(), "area": round(area, 2), "outline": pts,
                            "holes": holes})
    out.sort(key=lambda d: (d["layer"], -d["area"], d["outline"][0]))
    json.dump(out, open(os.path.join(bl.PCB_DIR, "l5", "islands.json"), "w"), indent=0)
    print("GND pour pieces without a GND via: %d (%s)" % (len(out), ", ".join("%s %.1f mm2" % (d["layer"], d["area"])
                                                                          for d in out[:12])))


if __name__ == "__main__":
    main()
