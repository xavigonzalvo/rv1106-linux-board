"""Phase 7 (layout constraints) generator. Writes design/layout/*.csv and design/layout/board.kicad_dru.

Usage:  design/.venv/bin/python -I design/tools/layout_calc.py design [--skip-z]
  --skip-z   keep the existing layout/impedance.csv (the field solver takes ~2 min)

Inputs: schematic/out/nets.csv, schematic/out/parts.csv, power_rails.csv, and (through courtyard.py, parsed as text)
the cached KiCad footprints in refs/kicad-footprints-*. Every constant is cited in layout.md (section given in the comments).
Outputs:
  layout/impedance.csv     field-solver results (layout.md §2.2)
  layout/trace_widths.csv  IPC-2221 current-carrying widths per power class (layout.md §3)
  layout/netclasses.csv    every net of the netlist -> one net class (layout.md §4)
  layout/zones.csv         board outline, rails, holes, fiducials, connector courtyards (computed from the cached
                           .kicad_mod at origin/rotation) and placement zones with their courtyard fill (layout.md §5)
  layout/placement.csv     every part of the netlist -> zone + placement rule (layout.md §5)
  layout/lengths.csv       floor-plan length estimates for the ETH/USB/SDMMC/FSPI rules (layout.md §5.5)
  layout/board.kicad_dru   KiCad custom design rules mirroring §4 (helper; layout.md is authoritative)
"""
import argparse, csv, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from designdir import design_dir  # noqa: E402
import courtyard as cy  # noqa: E402

# ------------------------------------------------------------------ §1 board geometry (D-61, D-67, D-H2, D-84 round 2)
# D-84 round 2: 80 x 80 mm (was 70 x 70). D-H2 allows "larger if it makes the build simpler"; at 70 x 70 the zones could
# not hold their KiCad courtyards at <= 55 % fill (verifier P7 round 1 major). Cost change recorded in cost.md / D-84.
BOARD = (0.0, 0.0, 80.0, 80.0)          # x0, y0, x1, y1 mm; KiCad coordinates, y grows downwards (south)
RAIL_W = 5.0                            # JLCPCB PCB capabilities, "Mouse bites Panel" item 5: 5 mm tooling edges
SOC_C = (34.5, 36.5)                    # SoC centre
HOLE_D, HOLE_KEEP = 3.2, 7.0            # M3 clearance hole (NPTH) and copper/part keep-out diameter
HOLES = [(3.5, 3.5), (76.5, 3.5), (3.5, 76.5), (76.5, 76.5)]
FILL_MAX = 0.55                         # courtyard area / zone area (layout.md §5.1; verifier P7 r1 fix (d))
GLOBAL_FIDS = [(-1.15, 3.85), (-1.15, 76.15), (81.15, 3.85)]   # 3.85 mm from the panel edges ([JLC-CAP])
LOCAL_FIDS = [(51.0, 20.0), (19.5, 51.2)]                     # diagonal to U9, outside every zone
TOOLING = [(-2.5, 10.0), (-2.5, 70.0), (82.5, 10.0), (82.5, 70.0)]

# Edge and board connectors: zone id, ref, footprint, origin x, y, rotation (deg CCW), mating edge (N/S or None), note.
# Library footprints: the rectangle is the cached KiCad courtyard placed at origin/rotation and clipped to the board
# (an edge connector's courtyard may overhang the routed edge by <= 0.5 mm). Custom footprints: rectangle of
# courtyard.CUSTOM centred on the origin. check_layout L6 recomputes both.
CONNECTORS = [
    ("J3-RJ45", "J3", "Connector_RJ:RJ45_Hanrun_HR911105A_Horizontal", 21.46, 17.26, 180, "N",
     "pad 1 at the origin; at 180 deg the fab front (mouth) lies on the north edge y = 0"),
    ("J5-HDR", "J5", "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical", 3.00, 9.56, 0, None,
     "pin 1 at the origin, odd row x = 3.00, even row x = 5.54"),
    ("J6-UART", "J6", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 30.77, 2.77, 90, None,
     "rotated 90 deg: row along +x, pin 1 (GND) at the origin"),
    ("J2-SD", "J2", "board:microSD_TF-01A", 19.5, 72.5, 0, "S",
     "body 14.50 x 15.35 mm (refs/tf-01a-datasheet p.1), card slot opening on the south edge"),
    ("J4-USBA", "J4", "board:USB_A_AF90_WJDG_RightAngle_THT", 35.75, 72.5, 0, "S",
     "legs 15.30 wide, 14.20 deep (refs/usb-a-af90-wjdg-datasheet p.1), opening on the south edge"),
    ("J1-USBC", "J1", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", 49.5, 76.35, 0, "S",
     "rotation 0 deg: in the cached footprint the body (F.Fab) spans y -3.65..+3.65 with the SMD pads at y = -4.045, so "
     "the mouth faces +y (south); fab front at y = 80.0 = the south edge, signal pads at y = 72.3"),
]

# zone id, x0, y0, x1, y1, kind, description (layout.md §5.1). Placement zones only; connectors come from CONNECTORS.
ZONES = [
    ("RAIL-W", -5.0, 0.0, 0.0, 80.0, "rail", "west edge rail (V-cut at x = 0), 2 global fiducials + 2 tooling holes"),
    ("RAIL-E", 80.0, 0.0, 85.0, 80.0, "rail", "east edge rail (V-cut at x = 80), 1 global fiducial + 2 tooling holes"),
    ("Z-SOC", 20.5, 22.0, 49.5, 50.0, "zone",
     "U9 at (34.5, 36.5) + ring 1 (100 nF, ZQ/EXTR/VCM/nPOR/ADC parts, R47/R48/R50/R51, Y1, Y2) + ring 2 (1-10 uF, FB1-FB3, "
     "sub-rail parts and TPs, NT1, D2)"),
    ("Z-ETH", 8.0, 22.0, 20.5, 34.0, "zone", "ETH 0R links R56-R59 and centre-tap caps C82/C83 between J3 and SoC pins 97-102"),
    ("Z-HDR", 8.0, 34.0, 20.5, 50.0, "zone", "I2C pull-ups R62-R65 for header J5 (DC; position not critical)"),
    ("Z-UART", 27.0, 5.0, 39.0, 11.0, "zone", "UART test pads TP9/TP10/TP20 next to J6"),
    ("Z-UI", 39.0, 1.0, 72.0, 11.0, "zone", "SW2 RESET, SW3 MASKROM, LED1-3 + resistors, TP7, TP11"),
    ("Z-PMU", 62.0, 12.0, 77.0, 48.0, "zone",
     "four TLV62569 cells (9 mm each), north to south: U6 3V3 y 12-21, U7 DDR 21-30, U4 0V9 30-39, U5 1V8 39-48; output "
     "links JP1/R29/R30/R31 in the west strip x 62-65, VIN side east; TP2-TP5, TP15; east edge 3 mm from the V-cut"),
    ("Z-NAND", 49.5, 28.0, 61.5, 44.0, "zone", "U10 SPI NAND + C80/C81 + R52-R55"),
    ("Z-USB", 27.0, 50.0, 45.5, 64.5, "zone",
     "U11 USB mux + C84 + R60; U2 USB-A ESD and C35 at the south end next to J4; U8 SY6280 + C11/C34/R37/R61 in the "
     "south-east corner (VBUS_USBA to J4 pin 1 <= 15 mm)"),
    ("Z-USBA-PWR", 45.5, 50.0, 55.0, 71.0, "zone",
     "U1 USB-C ESD at the south end, <= 3 mm from J1 A6/A7/B6/B7; TP17; L3 below carries the VCC5V0_SYS feed to U8"),
    ("Z-PWRIN", 55.0, 48.0, 77.0, 72.5, "zone",
     "F1, D1, R1-R3, C2 + on/off U3, Q1-Q3, C3-C6, R5-R12, SW1, power test-pad row; east edge 3 mm from the V-cut"),
    ("Z-SDPWR", 9.0, 52.5, 27.0, 64.5, "zone", "Q4 SD switch + C21-C23, C26, R38-R40, R49, TP16, TP30 between the SoC and J2"),
]

# QFN-128 pin -> board coordinate (layout.md §5.2). [DS] r1.8 p.16 Fig.2-3/2-4: top view pin 1 at the top-left
# corner, pins counter-clockwise (1-32 down the left side, 33-64 along the bottom, 65-96 up the right, 97-128 along the
# top). The footprint is placed rotated +90 deg (counter-clockwise), so on the board: pins 1-32 run west->east along the
# SOUTH side, 33-64 south->north on the EAST side, 65-96 east->west on the NORTH side, 97-128 north->south on the WEST.
PITCH, HALF_SPAN, PAD_C = 0.35, 5.425, 6.075  # 31 x 0.35 / 2; pad centre 6.15 - 0.075 from centre (layout.md §6.1)


def soc_pin_xy(n):
    cx, cy = SOC_C
    if 1 <= n <= 32:
        return cx - HALF_SPAN + (n - 1) * PITCH, cy + PAD_C, "S"
    if 33 <= n <= 64:
        return cx + PAD_C, cy + HALF_SPAN - (n - 33) * PITCH, "E"
    if 65 <= n <= 96:
        return cx + HALF_SPAN - (n - 65) * PITCH, cy - PAD_C, "N"
    if 97 <= n <= 128:
        return cx - PAD_C, cy - HALF_SPAN + (n - 97) * PITCH, "W"
    return cx, cy, "EP"


ESC_R = 7.45   # escape via centre from the SoC centre: pad toe 6.45 + 1.0 mm (layout.md §6.1 "first via >= 1.0 mm outside")


def soc_via_xy(n):
    """Escape-via position of SoC pin n: on the pad's own line, ESC_R from the centre (layout.md §6.1)."""
    x, y, side = soc_pin_xy(n)
    cx, cy0 = SOC_C
    if side == "S": return x, cy0 + ESC_R
    if side == "N": return x, cy0 - ESC_R
    if side == "E": return cx + ESC_R, y
    return cx - ESC_R, y


# ------------------------------------------------------------------ §2.3 L3 plane plan (round 3; verifier P7 r2 major)
# Fixed points that the plane plan is built around (also written into placement.csv rules):
PMU_CELLS = [("U6", 12.0, 21.0), ("U7", 21.0, 30.0), ("U4", 30.0, 39.0), ("U5", 39.0, 48.0)]  # Z-PMU y bands
PMU_TAP_X = (62.0, 65.0)   # west strip of Z-PMU: measurement links JP1/R29/R30/R31 (outputs leave westwards)
JP1_XY = (63.7, 35.0)      # JP_MEAS_0V9, rotation 180 (pad 2 = VDD_0V9 at x 63.05); its >= 6 vias at x 61.6-62.9
JP1_VIA_X = 62.3           # centre of the JP1 via group, where the L3 neck current starts
R30_XY = (63.5, 16.5)      # R_MEAS_3V3 in the U6 cell
NECK_Y = (33.0, 37.0)      # VDD_0V9 neck band (4 mm >= 3 mm asked by the verifier), inside the U4 cell band 30-39
U8_XY = (43.4, 62.6)       # U_USBA SY6280 centre, rotation 0, south-east corner of Z-USB
U11_XY = (39.375, 53.0)    # U_MUX point used by the USB length estimate (unchanged since round 2)
VBUS_USBA_MAX = 15.0       # D-81: U8 -> J4 VBUS path <= 15 mm (1 oz copper instead of [SY] p.5 2 oz)
PLANE_GAP = 0.35           # gap between L3 regions of different nets (>= 0.3 mm rule of §2.3)
ISLAND_MARGIN = 1.0        # island edge >= 1.0 mm beyond the outermost escape-via centre (verifier P7 r2 fix)
RHO = 1.72e-8              # copper resistivity, ohm*m (layout.md §3)
T_L3 = 0.0152e-3           # L3 copper 0.5 oz (layout.md §2.1)
VIA_BARREL_L1_L3 = 0.035 + 0.2104 + 0.0152 + 1.065   # mm, L1 surface to L3 (layout.md §2.1 stack)
J4_PIN1_CANDIDATES = [(32.25, 66.5), (39.25, 66.5)]   # J4 centre x 35.75 +- 3.5 (7.0 mm outer pin pitch, refs/usb-a-
# af90-wjdg-datasheet p.1); which outer pin is VBUS is not in the drawing (UNVERIFIED), so both are checked. y = 1.5 mm
# inside the rear of J4's rectangle (same ESTIMATE as lengths.csv).


def plane_plan(nets):
    """L3 regions as rectangles (net, id, x0, y0, x1, y1, purpose). Island from the escape vias of every SoC pin on
    VDD_0V9 / VDD_ARM (NT1 joins VDD_ARM pin 115 to the island on L1, D-68)."""
    pins = sorted(int(n.split(".")[1]) for r in nets if r["net"] in ("VDD_0V9", "VDD_ARM")
                  for n in r["nodes"].split() if n.startswith("U9.") and n.split(".")[1].isdigit())
    vs = [soc_via_xy(n) for n in pins]
    ix0 = round(min(v[0] for v in vs) - ISLAND_MARGIN, 3); ix1 = round(max(v[0] for v in vs) + ISLAND_MARGIN, 3)
    iy0 = round(min(v[1] for v in vs) - ISLAND_MARGIN, 3); iy1 = round(max(v[1] for v in vs) + ISLAND_MARGIN, 3)
    g = PLANE_GAP
    R = [
        ("VDD_0V9", "ISLAND", ix0, iy0, ix1, iy1,
         f"under U9: escape vias of SoC pins {' '.join(map(str, pins))} + {ISLAND_MARGIN:g} mm; thermal and other-rail vias "
         "get 0.3 mm anti-pads"),
        ("VDD_0V9", "NECK", ix1, NECK_Y[0], PMU_TAP_X[1], NECK_Y[1],
         f"{NECK_Y[1] - NECK_Y[0]:g} mm neck from JP1 {JP1_XY} (>= 6 vias) west under Z-NAND to the island; U4 cell level with it"),
        ("VCC_3V3", "N-BAND", 1.0, 8.0, PMU_TAP_X[1], 21.5,
         f"feed corridor from R30 {R30_XY} (U6 cell) west along the free strip y 11-21.5 to the header/west region; "
         "header J5.1/J5.17, LED/UI pull-ups"),
        ("VCC_3V3", "W-COL", 1.0, 21.5, round(ix0 - g, 3), 64.5,
         "west column: Z-ETH (FB1/FEPHY), Z-HDR, Z-SDPWR (Q4 input), header J5; SoC pin 108 transfer via"),
        ("VCC_3V3", "N-SOC", ix0, 21.5, 61.5, round(iy0 - g, 3), "north of the island: SoC pins 81/88 transfer vias"),
        ("VCC_3V3", "NAND", 49.8, round(iy0 - g, 3), 61.5, round(NECK_Y[0] - 0.5, 3),
         "tongue over the north of Z-NAND: U10 pin 8, C80/C81, R52-R54; SoC pin 61 transfer via"),
        ("VCC_3V3", "S-SOC", round(ix0 - g, 3), round(iy1 + g, 3), 43.0, 49.7,
         "south of the island: SoC pins 13/28/43 transfer vias, U11 pin 10"),
        ("VCC5V0_SYS", "PMU", PMU_TAP_X[1] + 0.3, 12.0, 77.0, 48.0,
         "VIN side of all four buck cells (Z-PMU east of the link strip)"),
        ("VCC5V0_SYS", "PWRIN", 55.0, 48.0, 77.0, 72.5, "all of Z-PWRIN: Q1 drain (VCC5V0_SYS output), C5, R3, R12, TP13"),
        ("VCC5V0_SYS", "USBA", 42.0, 55.0, 55.0, 60.0,
         f"5 mm strip from Z-PWRIN west to U8 pin 5 (via at {U8_XY[0] + 1.14:.2f}, 59.5) and C11"),
        ("VBUS_USBA", "USBA", 31.0, 61.0, 46.0, 68.5,
         "3 mm+ pour U8 pin 1 -> C34 -> C35 -> J4 pin 1 (either outer pin) -> U2 pin 5, TP17 by L1 trace"),
    ]
    return pins, vs, R


def via_res(n_par):
    a = math.pi * ((0.15 + 0.018) ** 2 - 0.15 ** 2) * 1e-6
    return RHO * VIA_BARREL_L1_L3 * 1e-3 / a / n_par


def power_paths(planes, worst_0v9=1.001):
    """VDD_0V9 plane drop and the VBUS_USBA U8 -> J4 distance (layout.md §2.3, §3, §4.5)."""
    isl = next(r for r in planes if r[1] == "ISLAND"); nk = next(r for r in planes if r[1] == "NECK")
    w = nk[5] - nk[3]; ln = JP1_VIA_X - nk[2]
    r_neck = RHO * ln * 1e-3 / (T_L3 * w * 1e-3)
    r_isl = RHO * (isl[4] - SOC_C[0]) * 1e-3 / (T_L3 * (isl[5] - isl[3]) * 1e-3)
    r_v = via_res(6) + via_res(4)
    r_tot = r_neck + r_isl + r_v
    rows = [dict(item="VDD_0V9 L3 drop", path=f"JP1 vias x {JP1_VIA_X} -> neck {ln:.2f} x {w:g} mm -> island edge x {nk[2]} "
                 f"-> SoC centre x {SOC_C[0]}", length_mm=round(ln + isl[4] - SOC_C[0], 2), limit_mm="",
                 r_mohm=round(r_tot * 1e3, 2), current_a=worst_0v9, value=round(r_tot * worst_0v9 * 1e3, 1),
                 unit="mV", note=f"neck {r_neck * 1e3:.2f} + island half-width {r_isl * 1e3:.2f} + vias (6 at JP1, >= 4 "
                 f"carrying at the SoC; {VIA_BARREL_L1_L3:.2f} mm barrels, 18 um plating) {r_v * 1e3:.2f} mOhm; 0.5 oz L3, "
                 "rho 1.72e-8; worst-case current power_rails.csv")]
    ux, uy = U8_XY
    p1 = (ux - 1.1375, uy - 0.95)  # SOT-23-5 pad 1 at (-1.1375, -0.95), rotation 0 (cached KiCad footprint)
    for jx, jy in J4_PIN1_CANDIDATES:
        d = octi(p1, (jx, jy)) * DETOUR
        rows.append(dict(item="VBUS_USBA U8 -> J4 pin 1", path=f"U8 pin 1 ({p1[0]:.2f}, {p1[1]:.2f}) -> J4 pin 1 candidate "
                         f"({jx}, {jy})", length_mm=round(d, 1), limit_mm=VBUS_USBA_MAX, r_mohm="", current_a="",
                         value=round(d, 1), unit="mm", note=f"octilinear x {DETOUR} detour (as lengths.csv); D-81 limit"))
    return rows


# ------------------------------------------------------------------ §3 IPC-2221 current capacity
# IPC-2221A §6.2 design chart, curve fit as published: I = k * dT^0.44 * A^0.725 (A in mil^2), k = 0.048 external,
# 0.024 internal. (Standard not downloaded: the constants are the widely reproduced fit, UNVERIFIED against the text.)
T_OUT_MIL = 0.035 / 0.0254   # JLC04161H-7628 outer copper 0.035 mm (layout.md §2.1)
T_IN_MIL = 0.0152 / 0.0254   # inner copper 0.0152 mm
DT = 10.0                    # allowed temperature rise, degC


def ipc_width_mm(i_a, internal=False, dt=DT):
    k = 0.024 if internal else 0.048
    area = (i_a / (k * dt ** 0.44)) ** (1 / 0.725)
    return area / (T_IN_MIL if internal else T_OUT_MIL) * 0.0254


def via_amps(drill=0.3, plating=0.018, dt=DT):
    """Barrel as an internal conductor (conservative k = 0.024). JLCPCB average hole plating 18 um (capabilities)."""
    r = drill / 2
    a_mm2 = math.pi * ((r + plating) ** 2 - r ** 2)
    a_mil2 = a_mm2 / 0.0254 ** 2
    return 0.024 * dt ** 0.44 * a_mil2 ** 0.725


# class, nets, design current (A), basis, chosen outer width (mm), chosen inner width/pour (mm), vias per transition
POWER_CLASSES = [
    ("PWR_5V", ["VBUS_IN", "VBUS_5V", "VCC5V0_SYS"], 2.0,
     "1.3 x 1.41 A worst case (power.md §5) = 1.83 A, rounded up to 2.0 A", 1.0, 5.0),
    ("PWR_USBA", ["VBUS_USBA"], 1.25, "SY6280 current-limit maximum 1.25 A at RSET 6.8 k (power_rails.csv)", 0.8, 3.0),
    ("PWR_0V9", ["VDD_0V9", "VDD_0V9_BUCK", "VDD_ARM"], 1.3, "1.3 x 1.001 A (power_rails.csv VDD_0V9 worst_a)", 0.8, 3.0),
    ("PWR_3V3", ["VCC_3V3", "VCC_3V3_BUCK"], 0.72, "1.3 x 0.550 A (power_rails.csv)", 0.5, 2.0),
    ("PWR_DDR", ["VCC_DDR", "VCC_DDR_BUCK"], 0.46, "1.3 x 0.352 A (power_rails.csv)", 0.5, 1.5),
    ("PWR_1V8", ["VCC_1V8", "VCC_1V8_BUCK"], 0.27, "1.3 x 0.203 A (power_rails.csv)", 0.4, 1.0),
    ("PWR_SD", ["VCC3V3_SD"], 0.26, "1.3 x 0.20 A SD allowance (power_rails.csv)", 0.4, 1.0),
    ("PWR_SUB", ["MIPI_CSI_AVDD_1V8", "AVDD1V8_USB", "VCC1V8_CODEC", "ETH_AVDD1V8", "FEPHY_AVDD3V3", "VCC3V3_RTC",
                 "VCC3V3_RTC_IN"], 0.08, "1.3 x the largest sub-rail estimate 0.06 A (FEPHY_AVDD3V3)", 0.3, 0.3),
    ("SW_NODE", ["U4_SW", "U5_SW", "U6_SW", "U7_SW"], 2.6,
     "1.3 x 2.0 A TLV62569 rated output (inductor current incl. ripple); short wide copper, not a trace", 1.2, None),
]

# ------------------------------------------------------------------ §4 net classes
# Rules are text; numeric rules are in CLASS_RULES. Order matters: first match wins. Every net must match one class.
NET_RULES = [
    ("ETH_DIFF", r"^ETH_(TX|RX)[PN](_J)?$"),
    ("USB_DIFF", r"^(USB|USBC|USBA)_D[PM]$"),
    ("XTAL", r"^(OSC_XIN|OSC_XOUT|OSC_XOUT_X|RTC_XIN|RTC_XOUT)$"),
    ("SDMMC", r"^(SDMMC_(CLK|CLK_SD|CMD|D[0-3]))$"),
    ("FSPI", r"^FSPI_(CLK|CLK_NAND|CS0N|CS0N_NAND|D[0-3])$"),
    ("SW_NODE", r"^U[4-7]_SW$"),
    ("SENSE", r"^(U[4-7]_FB|DRAM_ZQ|ETH_EXTR|CODEC_VCM|USBA_ISET|ONOFF_PDT|SARADC_IN1|RECOVERY|USB_DET_IN|NPOR|"
              r"QPWR_G)$"),
    ("ETH_CT", r"^ETH_(TCT|RCT)$"),
    ("GND", r"^GND$"),
]
for cls, nets, *_ in POWER_CLASSES:
    if cls != "SW_NODE":
        NET_RULES.append((cls, "^(" + "|".join(re.escape(n) for n in nets) + ")$"))
NET_RULES.append(("DEFAULT", r".*"))

# class -> (width mm, clearance mm, diff gap mm or '', length rule, other rule, source)
CLASS_RULES = {
    "DEFAULT": (0.15, 0.15, "", "", "neck-down to 0.10 mm allowed inside the SoC escape ring (<= 1.5 mm from U9 pads)",
                "JLCPCB PCB capabilities 'Traces' (multilayer min 0.09/0.09 mm)"),
    "GND": (0.30, 0.15, "", "", "planes L2 (solid) and pours on L1/L4; every GND pad gets its own via to L2",
            "layout.md §7"),
    "ETH_DIFF": (None, 0.15, None, "pair <= 30 mm; P/N mismatch <= 1.27 mm",
                 ">= 0.76 mm (30 mil) to other signals, >= 1.27 mm (50 mil) to clocks/SW nodes; L1 only over solid L2; no vias, "
                 "no test pads; RX pair may split around J3 pins 4/5 for <= 5 mm", "PLAN Phase 7 (100 ohm); TI SPRAAR7J §3.1-3.4"),
    "USB_DIFF": (None, 0.15, None, "SoC->mux->connector <= 50 mm per path; P/N mismatch <= 1.27 mm (50 mil)",
                 ">= 0.76 mm (30 mil) to other signals, >= 1.27 mm (50 mil) to clocks/SW nodes; L1 only over solid L2; "
                 "<= 4 vias per line (target 0); no stubs, no test pads; ESD U1/U2 at the connector, flow-through",
                 "TI SPRAAR7J Table A-1/A-2 p.16, §3.1-3.3, §3.14"),
    "XTAL": (0.15, 0.30, "", "per net (XTAL_LEN)",
             "GND pour guard ring on L1 around crystal + caps, stitched to L2; no other signal on L1/L4 under or within "
             "1 mm; load-cap GND straight to L2", "layout.md §4.3"),
    "SDMMC": (0.15, 0.20, "", "all lines <= 40 mm; each line within +-5 mm of SDMMC_CLK(+_SD)",
              "R48 22R within 2 mm of SoC pin 15; continuous L2 under the bus", "layout.md §4.4 (engineering rule, UNVERIFIED vs a Rockchip guide)"),
    "FSPI": (0.15, 0.20, "", "all lines <= 25 mm; each within +-5 mm of FSPI_CLK(+_NAND)",
             "R47 22R within 2 mm of SoC pin 48; continuous L2 under the bus", "layout.md §4.4 (engineering rule, UNVERIFIED vs a Rockchip guide)"),
    "SW_NODE": (1.2, 0.30, "", "SW pin -> inductor <= 3 mm; whole node one L1 polygon",
                "no other net under the node on L1/L4 (L2 solid GND below); keep FB nets and all SENSE/XTAL/diff nets "
                ">= 2 mm away", "[TLV] §10.1 p.13"),
    "SENSE": (0.15, 0.25, "", "FB: divider at the IC, FB trace <= 5 mm; ZQ/EXTR/VCM/PDT resistor or cap <= 3 mm from the pin",
              "route away (>= 2 mm) from SW nodes and inductors; QPWR_G/ONOFF_PDT are high-impedance: clean the area of flux "
              "(leakage)", "[TLV] §10.1 p.13; layout.md §4.5"),
    "ETH_CT": (0.30, 0.15, "", "C82/C83 <= 3 mm from J3 pins 4/5", "", "layout.md §4.2"),
}
XTAL_LEN = {  # one XTAL length budget (round 3): layout.md §4.1/§4.3, netclasses.csv and board.kicad_dru say the same
    "OSC_XIN": (5.0, "OSC_XIN <= 5 mm (pin 68 - Y1 pin 1 - C77 - R51)"),
    "OSC_XOUT_X": (5.0, "OSC_XOUT_X <= 5 mm (R50 - Y1 pin 3 - C76)"),
    "OSC_XOUT": (8.0, "OSC_XOUT <= 8 mm total: pin 69 -> R50 <= 2 mm, R51 branch <= 2 mm, TP6 stub <= 3 mm"),
    "RTC_XIN": (6.0, "RTC_XIN <= 6 mm (pin 21 - Y2 - C79)"),
    "RTC_XOUT": (6.0, "RTC_XOUT <= 6 mm (pin 20 - Y2 - C78)"),
}
for cls, nets, i_a, basis, w_out, w_in in POWER_CLASSES:
    if cls != "SW_NODE":
        CLASS_RULES[cls] = (w_out, 0.20, "", "", f"design current {i_a} A; inner-layer pour >= {w_in} mm wide", "layout.md §3")


# ------------------------------------------------------------------ §2.2 impedance
Z_TARGETS = [("ETH_DIFF", 100.0, 0.20), ("USB_DIFF", 90.0, 0.15)]


def run_impedance(out):
    import zsolve as z
    rows = []
    h = z.STACK["h"]
    # validation: FD vs Hammerstad-Jensen on a thin bare microstrip (HJ + Wheeler thickness correction)
    st = dict(z.STACK); st["t_cu"] = 0.0101
    for w in (0.20, 0.35):
        fd = float(z.microstrip(w, stack=st, mask=False))
        dw = st["t_cu"] / math.pi * (1 + math.log(2 * h / st["t_cu"]))
        hj = float(z.hammerstad(w + dw))
        rows.append(dict(item=f"validation w={w}", w_mm=w, s_mm="", z_ohm=round(fd, 2), ref_ohm=round(hj, 2),
                         note="FD (t=10 um, no mask) vs Hammerstad-Jensen + Wheeler thickness correction"))
    grid = [round(0.08 + 0.005 * i, 3) for i in range(45)]  # 0.080 .. 0.300 mm, solver grid ~5 um
    for cls, target, s in Z_TARGETS:
        lo, hi = 0, len(grid) - 1
        zl = None
        while hi - lo > 1:  # Zdiff falls with w
            mid = (lo + hi) // 2
            zm = float(z.microstrip(grid[mid], s=s))
            if zm > target: lo = mid
            else: hi = mid
        cands = {}
        for i in (lo, hi):
            cands[grid[i]] = float(z.microstrip(grid[i], s=s))
        w_best = min(cands, key=lambda w: abs(cands[w] - target))
        zd = cands[w_best]
        zfine = float(z.microstrip(w_best, s=s, H=h / 84))
        zcm = float(z.microstrip(w_best, s=s, mode="even"))
        zpour = float(z.microstrip(w_best, s=s, gnd_gap=0.5))
        zlo = float(z.microstrip(round(w_best * 1.2 / 0.005) * 0.005, s=round(s * 0.8 / 0.005) * 0.005))
        zhi = float(z.microstrip(round(w_best * 0.8 / 0.005) * 0.005, s=round(s * 1.2 / 0.005) * 0.005))
        rows.append(dict(item=f"{cls} chosen", w_mm=w_best, s_mm=s, z_ohm=round(zd, 2), ref_ohm=target,
                         note=f"Zdiff; fine-grid (h/84) {zfine:.2f}; Zcm {zcm:.2f}; with L1 GND pour at 0.5 mm {zpour:.2f}; "
                              f"etch corners (w +-20 %, s -+20 %, JLC track tolerance) {zlo:.1f}..{zhi:.1f}"))
    for w in (0.15, 0.10):
        rows.append(dict(item=f"single-ended w={w}", w_mm=w, s_mm="", z_ohm=round(float(z.microstrip(w)), 2), ref_ohm="",
                         note="information: DEFAULT/SDMMC/FSPI trace on L1 over L2"))
    rows.append(dict(item="single-ended 50 ohm", w_mm="", s_mm="", z_ohm="", ref_ohm=50,
                     note="not needed on this board (no single-ended controlled-impedance net)"))
    with open(out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["item", "w_mm", "s_mm", "z_ohm", "ref_ohm", "note"])
        wr.writeheader(); wr.writerows(rows)
    return rows


def read_csv(p):
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", type=design_dir)
    ap.add_argument("--skip-z", action="store_true")
    a = ap.parse_args()
    D = a.design
    L = os.path.join(D, "layout")
    if not os.path.isdir(L):
        os.mkdir(L)  # the single output folder of this phase, inside the existing design tree
    zpath = os.path.join(L, "impedance.csv")
    if a.skip_z and os.path.exists(zpath):
        zrows = read_csv(zpath)
    else:
        zrows = run_impedance(zpath)
    zch = {r["item"].split()[0]: r for r in zrows if r["item"].endswith("chosen")}
    for cls, target, s in Z_TARGETS:
        w = float(zch[cls]["w_mm"])
        CLASS_RULES[cls] = (w, CLASS_RULES[cls][1], s) + CLASS_RULES[cls][3:]

    # §3 trace widths
    tw = []
    for cls, nets, i_a, basis, w_out, w_in in POWER_CLASSES:
        need_o, need_i = ipc_width_mm(i_a), ipc_width_mm(i_a, internal=True)
        nv = math.ceil(i_a / via_amps())
        tw.append(dict(cls=cls, nets=" ".join(nets), design_a=i_a, basis=basis, ipc_outer_min_mm=round(need_o, 3),
                       chosen_outer_mm=w_out, ipc_inner_min_mm=round(need_i, 3),
                       chosen_inner_mm="" if w_in is None else w_in,
                       vias_0p3_min=max(nv, 2), via_amps_each=round(via_amps(), 2)))
    with open(os.path.join(L, "trace_widths.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(tw[0])); wr.writeheader(); wr.writerows(tw)

    # §4 net classes
    nets = read_csv(os.path.join(D, "schematic", "out", "nets.csv"))
    nc = []
    for n in nets:
        cls = next(c for c, rx in NET_RULES if re.match(rx, n["net"]))
        w, clr, gap, length, other, src = CLASS_RULES[cls]
        if cls == "XTAL":
            length = XTAL_LEN[n["net"]][1]
        nc.append(dict(net=n["net"], netclass=cls, width_mm=w, clearance_mm=clr, diff_gap_mm=gap, length_rule=length,
                       other_rule=other, source=src, nodes=n["nodes"]))
    with open(os.path.join(L, "netclasses.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(nc[0])); wr.writeheader(); wr.writerows(nc)

    # §5 zones + placement
    parts = read_csv(os.path.join(D, "schematic", "out", "parts.csv"))
    pl = [place(p) for p in parts]
    fill = {}
    for r in pl:
        fill[r["zone"]] = fill.get(r["zone"], 0.0) + cy.courtyard_area(r["footprint"])
    bw, bh = BOARD[2] - BOARD[0], BOARD[3] - BOARD[1]
    cols = ["zone", "x0", "y0", "x1", "y1", "kind", "footprint", "origin_x", "origin_y", "rot_deg", "edge",
            "courtyard_mm2", "fill_pct", "description"]
    rows = [dict(zone="BOARD", x0=BOARD[0], y0=BOARD[1], x1=BOARD[2], y1=BOARD[3], kind="outline",
                 courtyard_mm2=round(sum(fill.values()), 1), fill_pct=round(100 * sum(fill.values()) / (bw * bh), 1),
                 description=f"{bw:.0f} x {bh:.0f} mm routed board (D-H2, D-84 r2); panel with rails "
                             f"{bw + 2 * RAIL_W:.0f} x {bh:.0f} mm; courtyard total of all {len(pl)} parts")]
    for zid, ref, fp, ox, oy, rot, edge, note in CONNECTORS:
        x0, y0, x1, y1 = connector_rect(fp, ox, oy, rot)
        a = fill.get(zid, 0.0)
        rows.append(dict(zone=zid, x0=x0, y0=y0, x1=x1, y1=y1, kind="connector", footprint=fp, origin_x=ox, origin_y=oy,
                         rot_deg=rot, edge=edge or "", courtyard_mm2=round(a, 1),
                         fill_pct="", description=f"{ref}: {note}"))
    for zid, x0, y0, x1, y1, kind, desc in ZONES:
        a = fill.get(zid, 0.0)
        rows.append(dict(zone=zid, x0=x0, y0=y0, x1=x1, y1=y1, kind=kind, courtyard_mm2=round(a, 1) if kind == "zone" else "",
                         fill_pct=round(100 * a / ((x1 - x0) * (y1 - y0)), 1) if kind == "zone" else "", description=desc))
    for i, (x, y) in enumerate(HOLES, 1):
        r = HOLE_KEEP / 2
        rows.append(dict(zone=f"H{i}", x0=x - r, y0=y - r, x1=x + r, y1=y + r, kind="hole", origin_x=x, origin_y=y,
                         description=f"M3 NPTH {HOLE_D} mm at ({x}, {y}), keep-out {HOLE_KEEP} mm"))
    for i, (x, y) in enumerate(LOCAL_FIDS, 1):
        rows.append(dict(zone=f"FID{i}", x0=x - 1, y0=y - 1, x1=x + 1, y1=y + 1, kind="fiducial", origin_x=x, origin_y=y,
                         description="local fiducial 1 mm copper / 2 mm mask opening (rectangle = mask opening)"))
    for i, (x, y) in enumerate(GLOBAL_FIDS, 1):
        rows.append(dict(zone=f"GFID{i}", x0=x - 1, y0=y - 1, x1=x + 1, y1=y + 1, kind="rail-fiducial", origin_x=x,
                         origin_y=y, description="global fiducial on the rail, 3.85 mm from the panel edges"))
    for i, (x, y) in enumerate(TOOLING, 1):
        rows.append(dict(zone=f"TH{i}", x0=x - 1, y0=y - 1, x1=x + 1, y1=y + 1, kind="rail-hole", origin_x=x,
                         origin_y=y, description="tooling hole 2.0 mm NPTH in the rail"))
    for zr in rows:
        for k in cols: zr.setdefault(k, "")
    with open(os.path.join(L, "zones.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
    with open(os.path.join(L, "placement.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(pl[0])); wr.writeheader(); wr.writerows(pl)

    lens = length_estimates(nets, {z[0]: z for z in rows_as_tuples(rows)})
    with open(os.path.join(L, "lengths.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(lens[0])); wr.writeheader(); wr.writerows(lens)

    pins09, vias09, planes = plane_plan(nets)
    with open(os.path.join(L, "planes.csv"), "w", newline="") as fh:
        wr = csv.writer(fh); wr.writerow(["net", "region", "x0", "y0", "x1", "y1", "purpose"]); wr.writerows(planes)
    pp = power_paths(planes)
    with open(os.path.join(L, "power_paths.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(pp[0])); wr.writeheader(); wr.writerows(pp)

    write_dru(os.path.join(L, "board.kicad_dru"))
    worst = max((100 * a / ((z[3] - z[1]) * (z[4] - z[2])), z[0]) for z in ZONES if z[5] == "zone" for a in [fill.get(z[0], 0)])
    print(f"layout_calc: {len(nc)} nets classified, {len(pl)} parts placed, {len(tw)} power classes, "
          f"impedance {', '.join(f"{k} w={zch[k]['w_mm']} -> {zch[k]['z_ohm']}" for k in zch)}; "
          f"fullest zone {worst[1]} {worst[0]:.0f} %, board courtyard {rows[0]['fill_pct']} %; "
          f"{len(lens)} length estimates, worst {max(float(r['est_mm']) / float(r['limit_mm']) for r in lens) * 100:.0f} % of limit; "
          f"L3 island {planes[0][2:6]}, VDD_0V9 drop {pp[0]['value']} mV, VBUS_USBA {max(r['value'] for r in pp[1:])} mm")


def rows_as_tuples(rows):
    return [(r["zone"], float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"])) for r in rows]


def connector_rect(fp, ox, oy, rot):
    x0, y0, x1, y1 = cy.placed_rect(fp, ox, oy, rot)
    return (max(x0, BOARD[0]), max(y0, BOARD[1]), min(x1, BOARD[2]), min(y1, BOARD[3]))


# ------------------------------------------------------------------ §5.5 length estimates from the floor plan
# Estimate = octilinear distance (max(dx,dy) + 0.414 min(dx,dy), 45-degree routing) x DETOUR between the SoC pad and the
# far end, summed over the segments of the path. Far ends: library connector pads from the cached footprint at the
# placed origin/rotation; custom connectors and intermediate parts at a stated point (ESTIMATE, the custom pads are not
# drawn yet). This checks that the §4 length rules can be met by the floor plan; it is not a routed length.
DETOUR = 1.2
LEN_LIMIT = {"ETH_DIFF": 30.0, "USB_DIFF": 50.0, "SDMMC": 40.0, "FSPI": 25.0}


def octi(a, b):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + 0.414 * min(dx, dy)


def length_estimates(nets, zr):
    con = {c[1]: c for c in CONNECTORS}

    def lib_pad(ref, pad):
        _, _, fp, ox, oy, rot, _, _ = con[ref]
        x, y = cy.pad_xy(fp, pad)[0]
        return cy.place_point(x, y, ox, oy, rot)

    def zone_pt(zid, where):
        _, x0, y0, x1, y1 = zr[zid]
        xc = (x0 + x1) / 2
        return {"north": (xc, y0 + 1.5), "centre": (xc, (y0 + y1) / 2)}[where]

    j2 = zone_pt("J2-SD", "north")        # TF-01A contact row assumed 1.5 mm inside the rear (north) edge, ESTIMATE
    j4 = zone_pt("J4-USBA", "north")      # USB-A pins 2/3 at the rear centre (2.0 mm inner pitch), ESTIMATE
    u10 = zone_pt("Z-NAND", "centre")
    u11 = U11_XY  # U11 under SoC pins 26/27, north part of Z-USB (stated point, unchanged since round 2)
    paths = []
    for n, (pin, j3pad) in {"ETH_TXP": (100, "1"), "ETH_TXN": (99, "2"), "ETH_RXP": (98, "3"), "ETH_RXN": (97, "6")}.items():
        paths.append(("ETH_DIFF", n + " + " + n + "_J", pin, [("J3." + j3pad, lib_pad("J3", j3pad))]))
    paths.append(("USB_DIFF", "USB_DP/DM -> U11 -> USBC_DP/DM -> J1 A6/A7", 27, [("U11", u11), ("J1.A6", lib_pad("J1", "A6"))]))
    paths.append(("USB_DIFF", "USB_DP/DM -> U11 -> USBA_DP/DM -> J4 2/3", 27, [("U11", u11), ("J4.2/3", j4)]))
    for n, pin in {"SDMMC_CLK + SDMMC_CLK_SD": 15, "SDMMC_CMD": 16, "SDMMC_D0": 14, "SDMMC_D1": 12, "SDMMC_D2": 18,
                   "SDMMC_D3": 17}.items():
        paths.append(("SDMMC", n, pin, [("J2", j2)]))
    for n, pin in {"FSPI_CLK + FSPI_CLK_NAND": 48, "FSPI_CS0N + FSPI_CS0N_NAND": 47, "FSPI_D0": 41, "FSPI_D1": 42,
                   "FSPI_D2": 44, "FSPI_D3": 39}.items():
        paths.append(("FSPI", n, pin, [("U10", u10)]))
    out = []
    for cls, name, pin, hops in paths:
        x, y, _ = soc_pin_xy(pin)
        pts = [(x, y)] + [p for _, p in hops]
        d = sum(octi(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        out.append(dict(netclass=cls, path=name, soc_pin=pin, soc_xy=f"{x:.3f} {y:.3f}",
                        via=" ".join(f"{h}@{p[0]:.2f},{p[1]:.2f}" for h, p in hops), octilinear_mm=round(d, 2),
                        detour=DETOUR, est_mm=round(d * DETOUR, 1), limit_mm=LEN_LIMIT[cls]))
    return out


BLOCK_ZONE = {"usbc": "Z-PWRIN", "prot": "Z-PWRIN", "onoff": "Z-PWRIN", "pmu": "Z-PMU", "soc": "Z-SOC",
              "xtal": "Z-SOC", "nand": "Z-NAND", "sd": "Z-SDPWR", "eth": "Z-ETH", "usb": "Z-USB", "gpio": "Z-HDR",
              "uart": "Z-UART", "ui": "Z-UI"}
# A connector rectangle holds only its connector (check_layout L6); every other part is in a placement zone.
REF_ZONE = {
    "J1": "J1-USBC", "J2": "J2-SD", "J3": "J3-RJ45", "J4": "J4-USBA", "J5": "J5-HDR", "J6": "J6-UART",
    "U8": "Z-USB", "C11": "Z-USB", "C34": "Z-USB", "C35": "Z-USB", "R37": "Z-USB",
    "R61": "Z-USB", "U2": "Z-USB", "U1": "Z-USBA-PWR", "SW1": "Z-PWRIN", "SW2": "Z-UI", "SW3": "Z-UI",
    "Q4": "Z-SDPWR", "C21": "Z-SDPWR", "C22": "Z-SDPWR",
    "C23": "Z-SDPWR", "C26": "Z-SDPWR", "R38": "Z-SDPWR", "R39": "Z-SDPWR", "R40": "Z-SDPWR", "R49": "Z-SDPWR",
    "D2": "Z-SOC", "R34": "Z-SOC", "R20": "Z-PMU", "C20": "Z-PMU", "R21": "Z-PMU", "R24": "Z-PMU", "C33": "Z-PMU",
    "R3": "Z-PWRIN", "R4": "Z-SOC", "C1": "Z-SOC", "R12": "Z-PWRIN", "R33": "Z-SOC", "R32": "Z-SOC",
    "FB1": "Z-SOC", "FB2": "Z-SOC", "FB3": "Z-SOC", "R60": "Z-USB", "R35": "Z-UI", "R36": "Z-UI",
    "LED1": "Z-UI", "LED2": "Z-UI", "LED3": "Z-UI", "R68": "Z-UI", "R69": "Z-UI", "R70": "Z-UI",
    "R66": "Z-SOC", "R67": "Z-SOC", "JP1": "Z-PMU", "NT1": "Z-SOC",
}
TP_ZONE = {  # testpoints.md §2 rules 2-6
    **{f"TP{i}": "Z-PWRIN" for i in (1, 8, 12, 13, 14, 19, 21, 27, 28, 29)},
    **{f"TP{i}": "Z-PMU" for i in (2, 3, 4, 5, 15)},
    "TP6": "Z-SOC", "TP31": "Z-SOC", "TP7": "Z-UI", "TP9": "Z-UART", "TP10": "Z-UART", "TP20": "Z-UART",
    "TP11": "Z-UI", "TP16": "Z-SDPWR", "TP17": "Z-USBA-PWR", "TP18": "Z-SOC", "TP30": "Z-SDPWR",
    **{f"TP{i}": "Z-SOC" for i in (22, 23, 24, 25, 26)},
}
RING2 = ("ring 2 (outside the 100 nF ring): <= 8 mm of trace from SoC pin {n}")
SPECIAL_RULE = {
    "U9": f"centre {SOC_C}, rotation +90 deg: pin 1 at the SW corner, pins 1-32 on the south side W->E, 33-64 east "
          "S->N, 65-96 north E->W, 97-128 west N->S; 2 local fiducials diagonal (layout.md §6)",
    "Y1": "ring 1: crystal body <= 3 mm from SoC pins 68/69; OSC_XIN, OSC_XOUT_X <= 5 mm each; OSC_XOUT <= 8 mm total "
          "incl. the TP6 stub; GND guard (layout.md §4.3)",
    "Y2": "ring 1/2: crystal body <= 4 mm from SoC pins 20/21; RTC_XIN, RTC_XOUT <= 6 mm each; GND guard",
    "C76": "next to Y1 pin 3: <= 2 mm pad-to-pad, GND via at the pad", "C77": "next to Y1 pin 1: <= 2 mm pad-to-pad, GND via at the pad",
    "C78": "next to Y2: <= 2 mm pad-to-pad, GND via at the pad", "C79": "next to Y2: <= 2 mm pad-to-pad, GND via at the pad",
    "TP6": "test pad on OSC_XOUT (SoC pin 69 side of R50): <= 5 mm from SoC pin 69, stub <= 3 mm (testpoints.md §2 rule 3)",
    "TP31": "GND test pad within 3 mm of TP6 (scope ground for TP6, testpoints.md §2 rule 3)",
    "JP1": f"solder jumper U4 output -> VDD_0V9 L3 neck: centre {JP1_XY}, rotation 180 deg (pad 2 = VDD_0V9 west), "
           f">= 6 vias west of pad 2 (x 61.6-62.9) into the neck (layout.md §2.3, §3)",
    "R30": f"R_MEAS_3V3 at {R30_XY} in the U6 cell west strip; pad 2 (VCC_3V3) -> >= 2 vias into the L3 VCC_3V3 band "
           "(layout.md §2.3)",
    "U4": "cell y 30-39 of Z-PMU, level with the L3 VDD_0V9 neck (y {0}-{1}); VIN/C_IN east, inductor/output west to "
          "JP1".format(*NECK_Y),
    "U6": "cell y 12-21 of Z-PMU (north); VIN/C_IN east, output west to R30", "U7": "cell y 21-30 of Z-PMU; output west to R31",
    "U5": "cell y 39-48 of Z-PMU (south); output west to R29",
    "U8": f"south-east corner of Z-USB, centre {U8_XY}, rotation 0 (pin 1 OUT north-west, pin 5 IN north-east); "
          f"VBUS_USBA path U8 pin 1 -> J4 pin 1 <= {VBUS_USBA_MAX:g} mm (layout.md §3, power_paths.csv)",
    "R37": "R_SET 6.8k (USBA_ISET, SENSE): <= 2 mm from U8 pin 3, south-west of U8, GND via at the pad",
    "TP17": "VBUS_USBA test pad: L1 stub to the VBUS_USBA pour or C34, <= 10 mm from U8 (testpoints.md §2)",
    "C34": "C_USBA_OUT 22 uF: <= 2 mm pad-to-pad from U8 pin 1, west of U8 in the Z-USB south-east corner, GND via at the pad",
    "NT1": "net-tie VDD_0V9 -> VDD_ARM at SoC pin 115, <= 8 mm, >= 0.6 mm copper (D-68)",
    "U10": "rotate so pins 1-4 face the SoC; FSPI <= 25 mm",
    "U11": "NE part of Z-USB, between SoC pins 26/27 and the USB connectors; flow-through: SoC side pins 7/8 toward the SoC",
    "U1": "south end of Z-USBA-PWR, within 3 mm of J1 A6/A7/B6/B7, flow-through",
    "U2": "south end of Z-USB, within 3 mm of J4 pins 2/3, flow-through",
    "C35": "120 uF polymer at J4 pin 1 (VBUS): <= 5 mm pad-to-pad, south end of Z-USB",
    "F1": "first part after J1 VBUS pins (west edge of Z-PWRIN, next to J1); VBUS_IN copper >= 1.0 mm",
    "D1": "TVS right after F1, GND via at the pad",
    "R42": "ETH_EXTR 6.04k <= 3 mm from SoC pin 102, GND via at the pad",
    "R41": "DRAM_ZQ 240R <= 3 mm from SoC pin 52, GND via at the pad",
    "C70": "CODEC_VCM 4.7u <= 3 mm from SoC pin 30 (reference node, ring 1)",
    "C6": "ONOFF_PDT cap <= 3 mm from U3 pin 7 (high-impedance timing node)",
    "R47": "22R within 2 mm of SoC pin 48 (source series termination)",
    "R48": "22R within 2 mm of SoC pin 15 (source series termination)",
    "R50": "22R within 2 mm of SoC pin 69", "R51": "1M across pins 68/69, within 2 mm of them",
    "R62": "I2C3 pull-up (DC): anywhere in Z-HDR on its line", "R63": "I2C3 pull-up (DC): anywhere in Z-HDR on its line",
    "R64": "I2C1 pull-up (DC): anywhere in Z-HDR on its line", "R65": "I2C1 pull-up (DC): anywhere in Z-HDR on its line",
    **{r: RING2.format(n=n) + f" (sub-rail part of pin {n}, layout.md §5.3)"
       for r, n in (("R32", 1), ("R33", 24), ("FB2", 31), ("FB3", 96), ("FB1", 101), ("D2", 19), ("R34", 19))},
    **{f"TP{i}": "sub-rail test pad, ring 2: <= 8 mm of trace from its SoC pin / ferrite (testpoints.md §2)"
       for i in (18, 22, 23, 24, 25, 26)},
}


def place(p):
    ref, fn, pn, blk = p["ref"], p["functional"], p["place_near"], p["block"]
    zone = REF_ZONE.get(ref) or TP_ZONE.get(ref) or BLOCK_ZONE.get(blk) or "Z-SOC"
    rule, target = SPECIAL_RULE.get(ref, ""), ""
    m = re.match(r"U_SOC pins? (\d+)", pn or "")
    if m:
        n = int(m.group(1))
        x, y, side = soc_pin_xy(n)
        target = f"SoC pin {n} pad at ({x:.2f}, {y:.2f}) {side} side"
        if fn.startswith("DEC_") and p["value"].startswith("100nF"):
            rule = rule or (f"ring 1 decoupler: supply pad of this 100 nF cap <= 3.0 mm trace from SoC pin {n} (just "
                            "outside the escape vias), GND pad -> own via to L2 within 0.5 mm")
        elif fn.startswith("DEC_") or ref.startswith("FB") or ref in ("R32", "R33", "R34", "D2"):
            rule = rule or (RING2.format(n=n) + ("; GND pad -> own via to L2 within 0.5 mm" if ref.startswith("C") else ""))
        else:
            rule = rule or f"ring 1: <= 3 mm from SoC pin {n}"
    elif pn:
        rule = rule or f"next to {pn}: <= 2 mm pad-to-pad, GND via at the pad"
    if ref.startswith("TP"):
        rule = rule or "test pad per testpoints.md §2 (top side, >= 1 mm from bodies)"
    if not rule:
        rule = "inside its zone; short connections to its block (layout.md §5)"
    return dict(ref=ref, functional=fn, block=blk, footprint=p["footprint"], zone=zone, target=target, rule=rule)


def write_dru(path):
    w_eth, g_eth = CLASS_RULES["ETH_DIFF"][0], CLASS_RULES["ETH_DIFF"][2]
    w_usb, g_usb = CLASS_RULES["USB_DIFF"][0], CLASS_RULES["USB_DIFF"][2]
    txt = f"""(version 1)
# Generated by design/tools/layout_calc.py (Phase 7). Helper only: design/layout.md is authoritative.
# Net classes must be created in Board Setup > Net Classes with the names and patterns of layout/netclasses.csv.
# KiCad is not installed in the design environment: this file's syntax is UNVERIFIED (check it in H1, DRC tab).

(rule "ETH 100 ohm pair"
  (condition "A.NetClass == 'ETH_DIFF'")
  (constraint track_width (min {w_eth - 0.01:.3f}mm) (opt {w_eth:.3f}mm) (max {w_eth + 0.01:.3f}mm))
  (constraint diff_pair_gap (min {g_eth - 0.01:.3f}mm) (opt {g_eth:.3f}mm) (max {g_eth + 0.01:.3f}mm))
  (constraint diff_pair_uncoupled (max 5mm))
  (constraint skew (max 1.27mm) (within_diff_pairs))
  (constraint via_count (max 0)))

(rule "USB 90 ohm pair"
  (condition "A.NetClass == 'USB_DIFF'")
  (constraint track_width (min {w_usb - 0.01:.3f}mm) (opt {w_usb:.3f}mm) (max {w_usb + 0.01:.3f}mm))
  (constraint diff_pair_gap (min {g_usb - 0.01:.3f}mm) (opt {g_usb:.3f}mm) (max {g_usb + 0.01:.3f}mm))
  (constraint diff_pair_uncoupled (max 3mm))
  (constraint skew (max 1.27mm) (within_diff_pairs))
  (constraint via_count (max 4)))

# Pair spacing to other nets: tracks only, and not inside the courtyards of the fine-pitch parts whose own pad pitch is
# below 0.76 mm (U9 QFN-128 0.35 mm, J1 USB-C, U1/U2 SOT-23-6, U11 UQFN-10). Pads are checked by the normal clearance.
# Pair-to-pair spacing inside one class (ETH TX vs RX, USB segments) is a manual check (layout.md §10): a net-based rule
# here would also hit the P/N partner, which must sit at the diff gap.
(rule "ETH pairs keep 30 mil from other nets"
  (condition "A.NetClass == 'ETH_DIFF' && A.Type == 'track' && B.Type == 'track' && B.NetClass != 'ETH_DIFF' && B.NetClass != 'GND' && !A.intersectsCourtyard('U9')")
  (constraint clearance (min 0.76mm)))

(rule "USB pairs keep 30 mil from other nets"
  (condition "A.NetClass == 'USB_DIFF' && A.Type == 'track' && B.Type == 'track' && B.NetClass != 'USB_DIFF' && B.NetClass != 'GND' && !A.intersectsCourtyard('U9') && !A.intersectsCourtyard('J1') && !A.intersectsCourtyard('U1') && !A.intersectsCourtyard('U2') && !A.intersectsCourtyard('U11')")
  (constraint clearance (min 0.76mm)))

(rule "diff pairs keep 50 mil from clocks and switch nodes"
  (condition "(A.NetClass == 'ETH_DIFF' || A.NetClass == 'USB_DIFF') && (B.NetClass == 'XTAL' || B.NetClass == 'SW_NODE')")
  (constraint clearance (min 1.27mm)))

# Tracks and zones only, outside the buck ICs: on each TLV62569 SOT-23-5 pad 5 (FB) and pad 3 (SW) are only 1.61 mm apart.
(rule "sense nets away from switch nodes"
  (condition "(A.NetClass == 'SENSE' || A.NetClass == 'XTAL') && B.NetClass == 'SW_NODE' && A.Type != 'pad' && !A.intersectsCourtyard('U4') && !A.intersectsCourtyard('U5') && !A.intersectsCourtyard('U6') && !A.intersectsCourtyard('U7')")
  (constraint clearance (min 2.0mm)))

# Length rules below are per net. ETH (R56-R59), SDMMC_CLK (R48) and FSPI_CLK (R47) are split into two nets by a
# series part; KiCad does not add length through a component, so those totals are summed by hand (layout.md §10).
# One crystal budget (layout.md §4.3): per net, and OSC_XOUT includes the R51 branch and the TP6 stub (<= 3 mm, by hand).
(rule "Y1 XIN and XOUT_X length"
  (condition "A.NetName == 'OSC_XIN' || A.NetName == 'OSC_XOUT_X'")
  (constraint length (max 5mm)))

(rule "Y1 OSC_XOUT length incl. TP6 stub"
  (condition "A.NetName == 'OSC_XOUT'")
  (constraint length (max 8mm)))

(rule "Y2 RTC length"
  (condition "A.NetName == 'RTC_XIN' || A.NetName == 'RTC_XOUT'")
  (constraint length (max 6mm)))

(rule "SDMMC length" (condition "A.NetClass == 'SDMMC'") (constraint length (max 40mm)))
(rule "FSPI length" (condition "A.NetClass == 'FSPI'") (constraint length (max 25mm)))
(rule "ETH length" (condition "A.NetClass == 'ETH_DIFF'") (constraint length (max 30mm)))
(rule "USB length" (condition "A.NetClass == 'USB_DIFF'") (constraint length (max 50mm)))

(rule "QFN-128 escape neck-down"
  (condition "A.Type == 'track' && A.intersectsCourtyard('U9')")
  (constraint track_width (min 0.10mm))
  (constraint clearance (min 0.10mm)))

# U9 pad to U9 pad: the 0.35 mm pitch leaves 0.16 mm between 0.19 mm pads, below the XTAL (0.30), SENSE (0.25) and
# SDMMC/FSPI/PWR_* (0.20 mm) class clearances. Later rules take priority in KiCad, so this one stays after the class rules.
(rule "U9 pads"
  (condition "A.Type == 'pad' && B.Type == 'pad' && A.memberOfFootprint('U9') && B.memberOfFootprint('U9')")
  (constraint clearance (min 0.15mm)))

# Copper to board edge: 0.4 mm everywhere (V-cut edges need 0.4 mm, routed edges 0.3 mm; [JLC-CAP] "V-Cut", "Routed").
(rule "edge clearance"
  (constraint edge_clearance (min 0.40mm)))
"""
    with open(path, "w") as fh:
        fh.write(txt)


if __name__ == "__main__":
    main()
