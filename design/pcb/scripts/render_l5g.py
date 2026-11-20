#!/usr/bin/env python3
"""Layout phase L5G: review images of every area the L5G fixes touched (D-H7 item 10, D-119..D-127), from the saved
board, with the render_l5f.py machinery (kicad-cli SVG crops + annotated l5f_plot.py plots; "S" = silk labels drawn
with their ink box and a link to their owner, green = beside its own part).

    $PY design/pcb/scripts/render_l5g.py     -> design/pcb/renders/route_l5g_<area>[_<layer>].png
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_l5f  # noqa: E402

AREAS = {
    "ep_vias": (29.5, 31.5, 39.5, 41.5, ("F.Cu", "B.Cu"), "F,B", "U9 EP: 16 GND board vias 0.5/0.3 (no footprint drill)"),
    "sd_rtc": (14.0, 43.0, 38.0, 66.0, ("F.Cu",), "F", "SD bus: CLK 0.305 mm from D0 / CMD; RTC crystal lines (round 2)"),
    "rtc": (32.0, 42.0, 38.5, 53.5, ("F.Cu",), "F", "round 2: C58 0.176 E / 0.25 N, XOUT >= 0.50 mm from D2, XIN-XOUT 1.9 mm"),
    "rtc_b": (32.0, 42.0, 38.5, 53.5, ("B.Cu",), "B", "round 2: C58.1 via moved, L4 AVDD1V8_USB 45 deg piece to R33.2"),
    "j5_link": (2.5, 7.5, 9.0, 15.5, ("B.Cu",), "B", "J5.2 - J5.4 5 V B.Cu link pad centre to pad centre"),
    "j1_vias": (43.5, 69.0, 55.5, 76.0, ("F.Cu", "In2.Cu"), "F,In2", "J1 shell GND vias (hole edge 0.47 mm), "
                "In2_GND_HOP_3 2nd via"),
    "hop_usb": (35.0, 47.0, 43.0, 60.0, ("In2.Cu",), "In2,B", "In2 GND hop islands 1 / 2: 2nd GND vias"),
    "q1": (56.0, 62.0, 64.0, 69.0, ("F.Cu",), "F", "Q1 drain: 5 VCC5V0_SYS vias"),
    "silk_pmu": (56.0, 28.0, 80.0, 58.0, ("F.SilkS",), "F,S", "silk labels: buck cells, TP3 / 13 / 14 / 27 / 29, JP1 B (margin 0.20)"),
    "silk_soc": (14.0, 18.0, 56.0, 50.0, ("F.SilkS",), "F,S", "silk labels: SoC area (R43, R51, R55, R17 ...)"),
    "silk_south": (2.0, 50.0, 56.0, 78.0, ("F.SilkS",), "F,S", "silk labels: south (J4, J2, J5 39/40, TP30 ...)"),
    "silk_north": (2.0, 0.0, 80.0, 18.0, ("F.SilkS",), "F,S", "silk labels: north (J5 1/2, TH texts gone, C28 ...)"),
    "silk_east": (56.0, 50.0, 80.0, 80.0, ("F.SilkS",), "F,S", "silk labels: power entry, Q1, TP19 ..."),
}

if __name__ == "__main__":
    render_l5f.main(AREAS, "route_l5g", "l5g", "L5G")
