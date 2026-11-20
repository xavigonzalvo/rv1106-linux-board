# Layout constraints (Phase 7, Rev A): rules for the KiCad layout in phase H1

Board: RV1106G3 Linux board, **80 × 80 mm** (D-84 round 2: enlarged from 70 × 70 under D-H2 "larger if it makes the build simpler"), 4-layer **JLC04161H-7628**, 1.6 mm, **ENIG**, all parts on top, built with
**JLCPCB Standard PCBA** (2 assembled + 3 bare PCBs, D-H2). The netlist to import is `schematic/out/board.net`
(226 footprints, 135 nets). This file is the rule book for the person doing the layout. The tables it quotes are
generated, and the generated files are the source of truth:

| File | Content |
|---|---|
| `layout/netclasses.csv` | each of the 135 nets → one net class, with width, clearance, diff gap, length rule and other rules |
| `layout/placement.csv` | each of the 226 parts → zone + placement rule (+ the SoC pad coordinate for every SoC-side part) |
| `layout/zones.csv` | board outline, rails, mounting-hole keep-outs, fiducials, connector courtyards (computed from the cached KiCad footprint at the stated origin and rotation) and placement zones with their courtyard fill, as rectangles (mm) |
| `layout/lengths.csv` | floor-plan length estimates for the ETH / USB / SDMMC / FSPI length rules (§5.5) |
| `layout/planes.csv` | the L3 power regions (VDD_0V9 island + neck, VCC_3V3, VCC5V0_SYS, VBUS_USBA) as rectangles computed from the placement (§2.3) |
| `layout/power_paths.csv` | VDD_0V9 L3 drop and the VBUS_USBA U8 → J4 path estimate (§2.3, §3, §4.5) |
| `layout/impedance.csv` | field-solver results for the stackup (§2.2) |
| `layout/trace_widths.csv` | IPC-2221 current-carrying widths (§3) |
| `layout/board.kicad_dru` | KiCad custom DRC rules that mirror §4 (helper; syntax UNVERIFIED, KiCad is not installed here) |

Regenerate and check:

```
design/.venv/bin/python -I design/tools/layout_calc.py design            # ~1 min (field solver); --skip-z reuses impedance.csv
design/.venv/bin/python -I design/tools/check_layout.py design           # gate TP-D7 self-check (VERBOSE=1 lists passes)
```

Coordinates are KiCad board coordinates in mm: origin at the board's north-west corner, x to the east, **y to the south**.
"North edge" = y = 0, "south edge" = y = 80. Part references are the netlist (silkscreen) references from
`schematic/out/parts.csv`; functional names follow the D-63/D-65 rule `NAME [REF]`.

Sources used in this file:

| Tag | Source | Saved copy |
|---|---|---|
| [DS] | Rockchip RV1106 Datasheet Rev 1.8 (URL in requirements.md) | `refs/rv1106-datasheet-r1.8/` |
| [JLC-IMP] | JLCPCB "Controlled Impedance PCB Layer Stackup", https://jlcpcb.com/impedance, fetched 2026-10-29 | `refs/jlcpcb-impedance-2026-10-29/impedance.html` |
| [JLC-CAP] | JLCPCB "PCB Manufacturing Capabilities", https://jlcpcb.com/capabilities/pcb-capabilities, fetched 2026-10-29 | `refs/jlcpcb-pcb-capabilities-2026-10-29/pcb-capabilities.html` |
| [JLC-ASM] | JLCPCB "PCB Assembly Capabilities" (Phase 4) | `refs/jlcpcb-assembly-capabilities-2026-10-28/` |
| [TI-HS] | TI SPRAAR7J "High-Speed Interface Layout Guidelines" (Feb 2023), https://www.ti.com/lit/an/spraar7j/spraar7j.pdf | `refs/ti-spraar7-hs-layout-2026-10-29/spraar7j.pdf` |
| [TLV] | TI TLV62569 datasheet SLVSDG1C | `refs/tlv62569-datasheet/` |
| [SY] | Silergy AN_SY6280 Rev 0.1 | `refs/sy6280aac-datasheet/` |
| [LTC] | ADI LTC2954 datasheet (rev "2954fb") | `refs/ltc2954-datasheet/` |
| [ST-ESD] | ST USBLC6-2 datasheet Doc ID 11265 Rev 5 | `refs/usblc6-2sc6-datasheet/` |
| [KFP] | KiCad footprint library files (GitLab kicad-footprints, Phase 4/6 caches); courtyards, fab outlines and pads read by `tools/courtyard.py` | `refs/kicad-footprints-mods-2026-10-29/`, `refs/kicad-footprints-p6-2026-10-29/` |

---

## 1. Board outline, panel, rails, fiducials, mounting holes

| Item | Rule | Source / decision |
|---|---|---|
| Board | **80 × 80 mm** rectangle, corners rounded R 1 mm, Edge.Cuts (on the board itself since L5F, D-117 h: 1.5 × 1.5 mm routed notches in the rails (D-118 c) with every air-side corner R 0.5 mm, cuttable by a 1.0 mm bit let the board corners be R 1 mm arcs; router-bit radius UNVERIFIED at DFM). Enlarged from 70 × 70 mm: at 70 × 70 the placement zones could not hold their KiCad courtyards with routing room (§5.1). | D-H2 ("larger if it makes the build simpler"), D-61, D-84 round 2 |
| Panel for assembly | The board plus **two 5 mm edge rails** on the **west and east** sides = **90 × 80 mm** delivered panel, drawn by us in the Gerbers (1-up "panel by customer"). Rails join the board along **V-cut** lines at x = 0 and x = 80 (straight, full height, zero gap). | [JLC-ASM] Standard PCBA "Edge Rails: Necessary", "Fiducials: Necessary" (D-61); [JLC-CAP] "Outline › Mouse bites Panel" item 5 "For SMT assembly at JLCPCB, use 5 mm tooling edges, 2 mm tooling holes, and 1 mm fiducials centered at 3.85 mm from the panel edges"; "V-Cut" items 1–4 (min panel 70 × 70 mm, zero spacing) |
| Why west/east | Every connector that must reach an edge (RJ45, microSD, USB-A, USB-C) sits on the **north or south** edge, so no connector body hangs over a rail. The rails come off after assembly. | §5 |
| V-cut copper clearance | No copper within **0.8 mm** of the V-cut lines (x = 0, x = 80) since L5F (owner D-H6; was 0.4 mm = the JLC minimum); measured against the V-CUT layer by `check_routing` L5F-vcut. No exception: the J5 west lanes were re-routed (D-118 a; tracks 0.8002 mm, vias 0.81 mm). | [JLC-CAP] "V-Cut" item 1, "Routed" item 1 |
| How JLC is told about the V-cut | Draw the two V-cut lines on a user layer named "V-CUT" and say so in the order remark. The exact way JLCPCB wants V-cut lines marked is **UNVERIFIED**: confirm it in the DFM check / with the engineer on the order (H2). | — |
| Global fiducials | **3**, on the rails: 1.0 mm round copper, 2.0 mm mask opening, no paste, centred 3.85 mm from the panel edges: west rail (−1.15, 3.85) and (−1.15, 76.15), east rail (81.15, 3.85). The asymmetric third point fixes the panel orientation. KiCad footprint `Fiducial:Fiducial_1mm_Mask2mm` (name UNVERIFIED: that library is not in the cache; drawing it by hand is equivalent). | [JLC-CAP] (above); D-67 |
| Local fiducials | **2**, diagonal to the SoC, on the board: (51.0, 20.0) (NE of Z-SOC, north of Z-NAND) and (19.5, 51.2) (SW, between Z-HDR and Z-SDPWR); rows FID1/FID2 of zones.csv, whose 2 mm mask squares overlap no zone or connector (check_layout L6); adjust by ≤ 2 mm if a courtyard needs it. Same 1 mm / 2 mm geometry. | D-67 (0.35 mm-pitch QFN, D-61) |
| Tooling holes | **4**, 2.0 mm NPTH, in the rails at x = −2.5 / 82.5 and y = 10.0 / 70.0 (at least 3 mm from each fiducial). Exact positions JLC expects: **UNVERIFIED** (JLC's text gives only the size). | [JLC-CAP] (above) |
| Mounting holes | **4 × M3**, 3.2 mm NPTH, at (3.5, 3.5), (76.5, 3.5), (3.5, 76.5), (76.5, 76.5). Keep-out: no copper on any layer and no part body within a **7.0 mm** circle (M3 screw head + washer). NPTH ≥ 0.5 mm is fine for JLC. | [JLC-CAP] "Min. Non-plated holes 0.50 mm"; layout/zones.csv H1–H4 |
| Thickness / finish | 1.6 mm, ENIG, green mask, white silk, outer 1 oz, inner 0.5 oz, vias epoxy filled and capped (POFV, D-H6 / D-117 b / D-119). | D-62, D-67; [JLC-CAP] "Finished Inner Layer Copper ... 0.5oz by default" |
| Silk | Text ≥ 1.0 mm high with ≥ 0.15 mm stroke, line ≥ 0.15 mm (stock footprint silk widened, D-117 i), ≥ 0.15 mm from pads, nothing beyond the board edge. Board name + "Rev A", pin 1 marks on every IC and connector, header pin numbers 1/2/39/40, "POWER", "RESET", "MASKROM", LED names (PWR, STAT = LED_STATUS, ETH), each test pad with its TP number and short net name (testpoints.md §2 rule 2). | [JLC-CAP] "Legend" |

## 2. Stackup and controlled impedance

### 2.1 Stackup JLC04161H-7628 (1.6 mm, 4 layers)

| Layer | Material | Thickness | Use on this board |
|---|---|---|---|
| L1 (F.Cu) | copper 1 oz | 0.035 mm | all parts; **all high-speed and differential routing**; local GND pour |
| — | prepreg 7628 × 1, Er 4.4 | 0.2104 mm | |
| L2 (In1.Cu) | copper 0.5 oz | 0.0152 mm | **solid GND plane, no splits, no traces** |
| — | core, Er 4.6 | 1.065 mm | |
| L3 (In2.Cu) | copper 0.5 oz | 0.0152 mm | power islands (§2.3) |
| — | prepreg 7628 × 1, Er 4.4 | 0.2104 mm | |
| L4 (B.Cu) | copper 1 oz | 0.035 mm | low-speed signals (header GPIO, control, LEDs), GND pour; **no parts** |

Solder mask: 1.2 mil over substrate, 0.6 mil over traces, Er 3.8. Source: [JLC-IMP] "Controlled Impedance PCB Parameters and
Stackup" and "2) JLC04161H-7628 Stackup" table. JLC impedance tolerance ±10 % ([JLC-CAP] "Impedance Tolerance").

### 2.2 Differential impedance: computed widths

Method: `tools/zsolve.py`, a quasi-static 2-D finite-difference field solver of the L1-over-L2 cross-section with the
[JLC-IMP] stackup and conformal solder mask; Zdiff from the odd mode. Validated against the Hammerstad–Jensen closed form
for a bare microstrip: 70.63 vs 70.26 Ω (w = 0.20 mm) and 52.89 vs 52.97 Ω (w = 0.35 mm), both < 1 % (`layout/impedance.csv`).

| Class | Target | Trace width w | Gap s | Solver Zdiff (fine grid) | Zcm | With L1 GND pour 0.5 mm away | Etch corners (w ±20 %, s ∓20 %) |
|---|---|---|---|---|---|---|---|
| `ETH_DIFF` (10/100 Ethernet) | 100 Ω (PLAN Phase 7) | **0.235 mm** | **0.200 mm** | 99.7 Ω (98.5 Ω) | 35.3 Ω | 99.4 Ω | 88–113 Ω |
| `USB_DIFF` (USB 2.0 HS) | 90 Ω, 81–99 Ω ([TI-HS] Table A-1 p.16) | **0.255 mm** | **0.150 mm** | 90.3 Ω (89.2 Ω) | 34.9 Ω | 90.2 Ω | 80–103 Ω |

Notes:
- Both pairs are routed **only on L1 over the solid L2 GND**. TI does not recommend stripline or referencing power planes
  for high-speed pairs ([TI-HS] §2.4 p.6, §3.2 p.9).
- The two grid sizes differ by ≈ 1.2 %, inside the ±10 % fab tolerance. The etch corners show what JLC's ±20 % track
  tolerance ([JLC-CAP] "Track width tolerance") does to the pair. A 10/100 link and a 10–30 mm USB 2.0 route tolerate this.
- **H1 cross-check:** before routing, enter w/s into JLCPCB's online impedance calculator for JLC04161H-7628
  (outer layer, coplanar off). If it disagrees by more than 3 %, use its numbers and note the change in decisions.md.
  Whether our solver and JLC's calculator agree is **UNVERIFIED** (that calculator is interactive and was not run here).
- Single-ended DEFAULT traces (0.15 mm) are ≈ 73 Ω on L1. No single-ended net on this board needs a controlled impedance.
- Order the PCB **with impedance control on the JLC04161H-7628 stackup** (D-67; free on JLC 4-layer: UNVERIFIED, check on the quote).

### 2.3 Layer use and plane plan

- **L2 = one solid GND plane** under the whole board. No trace, no split, no slot. Only via anti-pads interrupt it.
- **L3 = power regions** (0.5 oz), computed by `tools/layout_calc.py` from the current placement and written to
  `layout/planes.csv` (round 3: the round-1 plan was centred on the old SoC position). Gap between regions of different
  nets ≥ 0.3 mm (the plan uses 0.35 mm). The unassigned L3 area is a GND fill tied to L2 by the stitching vias.

| Net | Region | Rectangle (mm) | What it serves |
|---|---|---|---|
| `VDD_0V9` | island | x 26.05–42.95, y 28.05–44.95 | centred on U9 (34.5, 36.5): the escape vias (1.0 mm outside the pad toes, §6.1) of every VDD_0V9 SoC pin 10, 51, 54, 55, 67, 71, 82, 103, 116 and of VDD_ARM pin 115 (NT1), each ≥ 1.0 mm inside the edge |
| `VDD_0V9` | neck | x 42.95–65, y 33–37 | **4 mm** neck from JP_MEAS_0V9 [JP1] at (63.7, 35.0) (≥ 6 vias at x 61.6–62.9) west under Z-NAND to the island. The U4 cell (Z-PMU y 30–39) is level with it |
| `VCC_3V3` | north band | x 1–65, y 8–21.5 | **feed corridor**: R_MEAS_3V3 [R30] at (63.5, 16.5) in the U6 cell (north-east), ≥ 2 vias, west along the free strip to the header (J5.1/J5.17) and the west column; LED/UI pull-ups |
| `VCC_3V3` | west column | x 1–25.7, y 21.5–64.5 | Z-ETH (FB1 → FEPHY), Z-HDR, Z-SDPWR (Q4 input), SoC pin 108 |
| `VCC_3V3` | north of SoC | x 26.05–61.5, y 21.5–27.7 | SoC pins 81/88 |
| `VCC_3V3` | NAND tongue | x 49.8–61.5, y 27.7–32.5 | U10 pin 8, C80/C81, R52–R54; SoC pin 61 |
| `VCC_3V3` | south of SoC | x 25.7–43, y 45.3–49.7 | SoC pins 13/28/43, U11 pin 10 |
| `VCC5V0_SYS` | PMU | x 65.3–77, y 12–48 | VIN side of all four buck cells (Z-PMU east of the 3 mm link strip) |
| `VCC5V0_SYS` | PWRIN | x 55–77, y 48–72.5 | all of Z-PWRIN: Q_PWR [Q1] drain (the VCC5V0_SYS output), C5, R3, R12, TP13 |
| `VCC5V0_SYS` | USB-A feed | x 42–55, y 55–60 | 5 mm strip west to U_USBA [U8] pin 5 (via at (44.54, 59.5)) and C11 |
| `VBUS_USBA` | pour | x 31–46, y 61–68.5 | U8 pin 1 → C34 → C35 → J4 pin 1 (either outer pin, §3) → U2 pin 5 |

  - The SoC's other supply pins (VCC_3V3, VCC_1V8, VCC_DDR) and the 16 thermal vias pass through the island with
    0.3 mm anti-pads ([JLC-CAP] "Inner layer via hole to copper clearance 0.2mm" + margin). Each SoC VCC_3V3 pin goes
    pin → ring-1 cap → via on L1, ≤ 7 mm, into the nearest VCC_3V3 rectangle (worst pin 43: 6.9 mm, check_layout L6).
    VCC_1V8 and VCC_DDR are L1/L4 traces at the §3 widths (no L3 region).
  - In Z-PMU every cell has its input on the east (over the VCC5V0_SYS region) and its output link (JP1, R29, R30, R31) in
    the west strip x 62–65, so power flows east → west and the VDD_0V9 neck and the VCC_3V3 band never cross the 5 V copper.
  - The header 5 V pins (J5 2/4) get VCC5V0_SYS on **L4** (§3), not on L3.
  - check_layout L6 recomputes the escape vias, the region gaps and connectivity, the neck width and position, and the
    U8/R30/JP1 points against these rectangles.
- **L4** = low-speed signals + GND pour. No `ETH_DIFF`, `USB_DIFF`, `XTAL`, `SDMMC`, `FSPI`, `SW_NODE` or `SENSE` net on L4.
  L4 traces that cross an L3 region boundary must be DEFAULT class (slow) only.
- **L1 GND pour** fills the free area, stitched to L2 with vias every ≈ 5 mm (≤ 200 mil next to diff-pair layer changes,
  [TI-HS] §2.4 Fig. 2-11 p.8), along the board edges and around the crystals.

## 3. Trace widths, copper and vias for current (IPC-2221)

Method: IPC-2221A §6.2 curve fit I = k · ΔT^0.44 · A^0.725 (A in mil², k = 0.048 outer / 0.024 inner), ΔT = 10 °C,
outer 0.035 mm, inner 0.0152 mm (§2.1). The fit is the widely published one; the IPC-2221 text itself was not downloaded,
so the constants are **UNVERIFIED** against the standard. Design current = 1.3 × worst case (the power.md margin rule).
`tools/layout_calc.py` computes the minima; the chosen widths are ≥ the minima (checked by check_layout L4).

| Class | Nets | Design current | IPC min outer | **Chosen outer (L1/L4)** | IPC min inner | **Chosen inner (L3 pour)** | Vias per layer change (0.3 mm, 0.74 A each) |
|---|---|---|---|---|---|---|---|
| `PWR_5V` | VBUS_IN, VBUS_5V, VCC5V0_SYS | 2.0 A (1.3 × 1.41 A) | 0.78 mm | **1.00 mm** | 4.68 mm | **5.0 mm** | ≥ 3 |
| `PWR_USBA` | VBUS_USBA | 1.25 A (SY6280 limit max) | 0.41 mm | **0.80 mm** | 2.45 mm | **3.0 mm** | ≥ 2 |
| `PWR_0V9` | VDD_0V9, VDD_0V9_BUCK, VDD_ARM | 1.3 A (1.3 × 1.001 A) | 0.43 mm | **0.80 mm** | 2.58 mm | **3.0 mm** (island) | ≥ 2 (JP1: ≥ 6) |
| `PWR_3V3` | VCC_3V3, VCC_3V3_BUCK | 0.72 A | 0.19 mm | **0.50 mm** | 1.14 mm | **2.0 mm** | ≥ 2 |
| `PWR_DDR` | VCC_DDR, VCC_DDR_BUCK | 0.46 A | 0.10 mm | **0.50 mm** | 0.62 mm | **1.5 mm** | ≥ 2 |
| `PWR_1V8` | VCC_1V8, VCC_1V8_BUCK | 0.27 A | 0.05 mm | **0.40 mm** | 0.30 mm | **1.0 mm** | ≥ 2 |
| `PWR_SD` | VCC3V3_SD | 0.26 A | 0.05 mm | **0.40 mm** | 0.28 mm | **1.0 mm** | ≥ 2 |
| `PWR_SUB` | MIPI_CSI_AVDD_1V8, AVDD1V8_USB, VCC1V8_CODEC, ETH_AVDD1V8, FEPHY_AVDD3V3, VCC3V3_RTC, VCC3V3_RTC_IN | 0.08 A | 0.01 mm | **0.30 mm** | 0.06 mm | **0.30 mm** | ≥ 2 |
| `SW_NODE` | U4_SW … U7_SW | 2.6 A (1.3 × TLV62569 2 A) | 1.12 mm | **1.20 mm** (L1 polygon, ≤ 3 mm long) | — | not on inner layers | none (stays on L1) |

- Via: **0.3 mm drill / 0.5 mm pad** everywhere (standard price: JLC charges extra only for 0.2/0.25 mm holes with pads
  < 0.45 mm, and for 0.1/0.15 mm holes; [JLC-CAP] "Min. Via hole size/diameter" notes ① ③). Via current 0.74 A each =
  barrel 0.3 mm with JLC's 18 µm average plating ([JLC-CAP] "Average Hole Plating Thickness"), treated as an internal
  conductor (conservative).
- The PWR_5V path carries the **full board current through the PPTC and Q_PWR [Q1]**: keep VBUS_IN → F1 → VBUS_5V → Q1 →
  VCC5V0_SYS on L1 as ≥ 1.0 mm traces or pours, plus the L3 VCC5V0_SYS region. **Deviation:** [SY] p.5 "PCB Layout Guide"
  asks for "at least 2 ounce copper for all VBUS traces"; this board uses 1 oz outer copper (D-67: standard copper, no
  surcharge) and compensates with width: VBUS_USBA ≥ 0.8 mm on L1 (2 × the IPC 1 oz minimum) and ≤ 15 mm from U8 to J4,
  plus a ≥ 3 mm L3 pour (§2.3) (D-81). **Round 3:** U8 sits in the south-east corner of Z-USB at (43.4, 62.6), rotation 0
  (pin 1 OUT north-west), so the path U8 pin 1 → J4 pin 1 is **≤ 14.4 mm** (octilinear × 1.2) whichever outer J4 pin is
  VBUS: the AF90 WJDG drawing gives the 7.0 mm outer pitch but not the pin order (UNVERIFIED), so both candidates
  (32.25, 66.5) and (39.25, 66.5) are checked (`layout/power_paths.csv`, check_layout L6). In the south-west corner of the
  old Z-USBA-PWR the worst case was ≈ 15.3–16 mm, so U8 and its parts C11, C34, R37, R61 moved to Z-USB (D-91).
- Header 5 V pins (J5 2/4, 0.5 A allowance with USB-A, D-36): VCC5V0_SYS feed ≥ 1.0 mm on L4 or L3 from the east column to
  the header (≈ 55 mm, drop ≈ 0.5 A × 0.03 Ω ≈ 15 mV at 1 mm/1 oz, computed with ρ = 1.72e-8 Ω·m).
- Copper links: JP_MEAS_0V9 [JP1] bridge ≥ 0.6 mm wide (D-68; the KiCad footprint
  `Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm` has a 1.0 mm-wide pad). NT_ARM [NT1] `NetTie-2_SMD_Pad2.0mm`
  placed at SoC pin 115, joined to the VDD_0V9 island by ≥ 2 vias.

## 4. Net classes and routing rules

Every net of the netlist is in exactly one class (`layout/netclasses.csv`, check_layout L1/L2). Create these classes in
KiCad Board Setup › Net Classes, assign nets with the patterns of netclasses.csv, then load `layout/board.kicad_dru`.

**Clearance at U9 (round 3).** U9's 0.19 mm pads at 0.35 mm pitch are 0.16 mm apart, less than the XTAL (0.30), SENSE
(0.25) and SDMMC/FSPI/PWR_* (0.20 mm) class clearances. Two DRU rules cover this: "QFN-128 escape neck-down" (tracks
inside U9's courtyard, 0.10 mm) and "U9 pads" (U9 pad to U9 pad, 0.15 mm = [JLC-CAP] "SMD pad to pad clearance (different
nets) 0.15mm"). KiCad gives later custom rules priority, so "U9 pads" stays near the end of the file. The SENSE/XTAL →
SW_NODE 2.0 mm rule applies to tracks and zones only, outside the U4–U7 courtyards: on each TLV62569 SOT-23-5 the FB pad 5
and the SW pad 3 are only 1.61 mm apart edge to edge, fixed by the package, so the rule cannot apply to the pads.

### 4.1 Class table

| Class | Nets | Width | Clearance | Diff gap | Length / matching | Other rules | Source |
|---|---|---|---|---|---|---|---|
| `DEFAULT` | 59 low-speed nets: HDR_* GPIO/I²C/SPI/PWM/UART, UART2_*, LED_*, keys, enables (EN_N, ONOFF_EN, PWR_EN, U4_EN, U6_EN, VCC_DDR_1V8_EN), PB_*, PWR_KILL*, SDMMC_DET/PWREN, SD_CD_SW, SD_PWR_G, USB_SEL, USBA_VBUS_EN, CC1/CC2, GPIO0_A0_PD | 0.15 mm | 0.15 mm | — | — | neck-down to 0.10 mm / 0.10 mm only in the SoC escape (≤ 1.5 mm from U9 pads) | [JLC-CAP] "Traces": multilayer min 0.09/0.09 mm |
| `GND` | GND | ≥ 0.30 mm (pours) | 0.15 mm | — | — | §7 | — |
| `ETH_DIFF` | ETH_TXP/TXN/RXP/RXN and their `_J` segments (8 nets) | **0.235 mm** | 0.15 mm (other nets: 0.76 mm) | **0.200 mm** | pair ≤ 30 mm; P/N mismatch ≤ 1.27 mm | §4.2 | PLAN Phase 7; [TI-HS] §3.1–3.4 pp.9–10 |
| `USB_DIFF` | USB_DP/DM, USBC_DP/DM, USBA_DP/DM | **0.255 mm** | 0.15 mm (other nets: 0.76 mm) | **0.150 mm** | each path SoC → mux → connector ≤ 50 mm; P/N mismatch ≤ 1.27 mm (50 mil) | §4.6 | [TI-HS] Table A-1/A-2 p.16 |
| `XTAL` | OSC_XIN, OSC_XOUT, OSC_XOUT_X, RTC_XIN, RTC_XOUT | 0.15 mm | 0.30 mm (U9 pad to U9 pad: 0.15 mm, DRU "U9 pads") | — | per net: OSC_XIN, OSC_XOUT_X ≤ 5 mm; OSC_XOUT ≤ 8 mm total (R50 + R51 branches + TP6 stub ≤ 3 mm); RTC_XIN, RTC_XOUT ≤ 6 mm | §4.3 | layout.md §4.3 |
| `SDMMC` | SDMMC_CLK, SDMMC_CLK_SD, SDMMC_CMD, SDMMC_D0–D3 | 0.15 mm | 0.20 mm | — | all ≤ 40 mm; each within ± 5 mm of the clock length | §4.4 | engineering rule (no Rockchip layout guide found: UNVERIFIED) |
| `FSPI` | FSPI_CLK(_NAND), FSPI_CS0N(_NAND), FSPI_D0–D3 | 0.15 mm | 0.20 mm | — | all ≤ 25 mm; each within ± 5 mm of the clock length | §4.4 | engineering rule (UNVERIFIED as above) |
| `SW_NODE` | U4_SW, U5_SW, U6_SW, U7_SW | 1.20 mm polygon | 0.30 mm | — | SW pin → inductor ≤ 3 mm | §4.5 | [TLV] §10.1 p.13 |
| `SENSE` | U4–U7_FB, DRAM_ZQ, ETH_EXTR, CODEC_VCM, USBA_ISET, ONOFF_PDT, SARADC_IN1, RECOVERY, USB_DET_IN, NPOR, QPWR_G | 0.15 mm | 0.25 mm (SW nodes: 2.0 mm for tracks/zones outside the U4–U7 courtyards; U9 pads 0.15 mm) | — | FB ≤ 5 mm; ZQ/EXTR/VCM/PDT part ≤ 3 mm from its pin | §4.5, §4.7 | [TLV] §10.1 p.13 |
| `ETH_CT` | ETH_TCT, ETH_RCT | 0.30 mm | 0.15 mm | — | C_CT_TX [C82] / C_CT_RX [C83] ≤ 3 mm from J3 pins 4/5 | §4.2 | [LF] Ethernet block copy |
| `PWR_5V` `PWR_USBA` `PWR_0V9` `PWR_3V3` `PWR_DDR` `PWR_1V8` `PWR_SD` `PWR_SUB` | the rails of power_rails.csv (§3) | §3 | 0.20 mm (U9 pads 0.15 mm) | — | — | §3, §4.5 | IPC-2221 (§3) |

### 4.2 Ethernet (`eth`)

- RJ45 HR911105A [J3] (integrated magnetics) on the north edge, west part (§5). SoC PHY pins on the **west side, north
  end**: 97 RXN, 98 RXP, 99 TXN, 100 TXP, 101 FEPHY_AVDD3V3, 102 ETH_EXTR ([DS] Table 2-1 p.18; pad coordinates in
  placement.csv). The pairs run diagonally from the SoC NW corner to J3 pins 1/2 (TX) and 3/6 (RX): floor-plan estimate 18.5–21.7 mm
  (§5.5, ×1.2 detour) against the 30 mm rule.
- The 0 R links R_ETH_TXP/TXN/RXP/RXN [R56–R59] (0603, D-64) sit in the pair, **side by side and symmetric**, ≤ 5 mm from
  J3. 0603 is the largest in-line size TI allows ([TI-HS] §3.10 p.12). Void L2 under their pads only if a fine-grid check
  shows a large dip; for 10/100 this is not required (UNVERIFIED need, left out for simplicity).
- **No vias, no test pads** on the pairs ([TI-HS] §3.2 p.9). TP11 is on LED_ETH, not on the pairs.
- RX pair: J3 puts pins 3 and 6 on either side of the centre-tap pins 4/5, so the pair splits for ≤ 5 mm at the jack
  (`diff_pair_uncoupled ≤ 5 mm` in the DRU).
- ETH_EXTR 6.04 k [R42] ≤ 3 mm from pin 102 with its own GND via. FB1 + C66 (FEPHY_AVDD3V3, pin 101) and FB3 + C56
  (ETH_AVDD1V8, pin 96) next to their pins.
- C_CT_TX [C82] and C_CT_RX [C83] 10 nF ≤ 3 mm from J3 pins 4/5, GND via at the pad.
- J3 shield pins (SH) go to GND (netlist); no chassis split (Phase 5 note: [LF] C68 not placed).
- Keep the pairs ≥ 0.76 mm from other nets and ≥ 1.27 mm from clocks/SW nodes; nothing routed under J3 on L1 between
  the pins except the pairs and GND ([TI-HS] §3.1 p.9).

### 4.3 Crystals (`xtal`)

- Y1 24 MHz (3225-4) with R_Y1_SER 22 R [R50], R_Y1_FB 1 M [R51], C_Y1_XIN/XOUT 18 pF [C77/C76]: crystal ≤ 3 mm from SoC
  pins 68/69 (north side, east part, pads at (38.88, 30.43) and (38.52, 30.43)), R50 ≤ 2 mm from pin 69. Y1 and its parts are in Z-SOC ring 1 (§5.3). Load caps
  between the crystal and the SoC, their GND pads each with a via straight to L2.
- Y2 32.768 kHz (3215) with C78/C79 ≤ 4 mm from pins 20/21 (south side, (35.73, 42.58)/(36.08, 42.58)), in Z-SOC.
- GND guard: L1 GND pour ring around crystal + caps, stitched to L2 with ≥ 4 vias; no other net on L1 within 1 mm, nothing
  on L4 under the crystal area. TP6 (net `OSC_XOUT`, SoC side of R50: U9.69, R50.1, R51.1, TP6.1) within 5 mm of pin 69
  with TP31 GND within 3 mm of TP6 (testpoints.md §2 rule 3); **TP6 stub ≤ 3 mm**.
- **One length budget** (netclasses.csv, the DRU per-net rules and §4.1 say the same): `OSC_XIN` ≤ 5 mm, `OSC_XOUT_X`
  (R50 → Y1 pin 3 → C76) ≤ 5 mm, `RTC_XIN` / `RTC_XOUT` ≤ 6 mm each. `OSC_XOUT` has three branches (pin 69 → R50 ≤ 2 mm,
  the R51 branch ≤ 2 mm, the TP6 stub ≤ 3 mm), and KiCad adds all tracks of a net, so its budget is **≤ 8 mm** total.
  The TP6 stub ≤ 3 mm is checked by hand (§10).
- Keep crystals and their traces ≥ 5 mm from the buck inductors and SW nodes, and ≥ 1.27 mm from diff pairs
  ([TI-HS] §3.2: no high-speed traces near crystals).

### 4.4 microSD and SPI NAND buses (`sd`, `nand`)

- SDMMC0 pins are on the **south side, west-middle** (pins 11–18; pin 15 = SDMMC_CLK). J2 (TF-01A) sits on the south edge
  to the south-west. Route all six lines together on L1 over L2, ≤ 40 mm, each within ± 5 mm of SDMMC_CLK + SDMMC_CLK_SD.
  R_SD_CLK 22 R [R48] ≤ 2 mm from pin 15 (source termination, [LF] copy). At 50 MHz high-speed mode (20 ns period) ± 5 mm
  is ≈ ± 30 ps skew; these numbers are an engineering rule, no Rockchip layout guide was found (UNVERIFIED).
- SD card power: Q_SD [Q4] with C21/C22 next to it; C_SD [C23] 100 nF and C26 10 µF ≤ 2 mm from J2 pin 4 (place_near).
  TP16 near Q4, TP30 (SDMMC_DET) near J2.
- FSPI pins are on the **east side, south part** (pins 39–48; pin 48 = FSPI_CLK). U10 W25N01KV (WSON-8 8 × 6) east of
  the SoC in Z-NAND with pins 1–4 facing the SoC. All FSPI lines ≤ 25 mm, ± 5 mm of the clock; R_FSPI_CLK 22 R [R47] ≤ 2 mm
  from pin 48. C80/C81 ≤ 2 mm from U10 pin 8. U10's exposed pad: connect to GND (Winbond allows GND or floating; GND chosen
  for heat and simplicity — the netlist already ties U10.9 to GND). R_NANDDIS 0 R [R55] at U10 pin 1 (D-25), easy to reach.

### 4.5 Bucks, power path and feedback (`pmu`, `prot`, `onoff`)

Per [TLV] §10.1 p.13 ("input/output capacitors and the inductor ... as close as possible to the IC", "low side of the
input and output capacitors ... connected properly to the power GND", "sense traces connected to FB ... away from SW
nodes") and its Fig. 20 DBV layout example:
- Each TLV62569 [U4–U7] cell: C_IN 10 µF + 100 nF [C7–C10, C12–C15] ≤ 1 mm from pin 4 (VIN) to pin 2 (GND), GND vias at
  both cap pads (≥ 2 each); inductor [L1–L4] ≤ 3 mm from pin 3 (SW); output caps at the inductor's far end with ≥ 2 GND
  vias each. The **hot loop** C_IN → VIN → GND → C_IN is the smallest loop on the board.
- Feedback divider (R_FBT/R_FBB, C_FF) ≤ 3 mm from pin 5 (FB), tapped on the **regulator side** of the measurement link
  (D-68/D-73: JP1, R29, R30, R31). FB trace ≤ 5 mm, ≥ 2 mm from the SW node and the inductor.
- The four SW nodes are one compact L1 polygon each; nothing else under them on L1/L4 (L2 GND below).
- Cell order in Z-PMU (x 62–77), 9 mm per cell, north → south: **U6 (3V3) y 12–21, U7 (DDR) y 21–30, U4 (0V9) y 30–39,
  U5 (1V8) y 39–48**. Each cell has VIN and C_IN on the east (over the L3 VCC5V0_SYS region) and the inductor, output caps
  and measurement link (R30, R31, JP1, R29) in the west strip x 62–65. U4 is level with the L3 VDD_0V9 neck (y 33–37);
  JP1 sits at (63.7, 35.0), rotation 180° (pad 2 = VDD_0V9 on the west), with ≥ 6 vias west of it into the neck (§2.3).
- VDD_0V9 copper from U4 to the SoC: short and wide (D-68 Phase-7 note). Path: JP1 vias (x 62.3) → 4 mm × 19.35 mm neck
  → island edge (x 42.95) → SoC centre, 27.8 mm in all. Resistance: neck 5.47 mΩ + island 0.57 mΩ + vias 0.53 mΩ = 6.57 mΩ
  (0.5 oz L3, ρ 1.72e-8 Ω·m; 6 vias at JP1 and ≥ 4 carrying at the SoC, 1.33 mm barrels with 18 µm plating). **Drop ≈ 6.6 mV
  at the 1.001 A worst case** (`layout/power_paths.csv`, recomputed by check_layout L6). With D-68's 0.873 V low edge
  (regulator side, links included) the SoC pins see ≥ 0.866 V, still ≥ the 0.85 V minimum of D-68.
- Input: J1 VBUS pins → F1 → D_TVS [D1] → U_ONOFF / Q_PWR [Q1] in this order, each ≤ 5 mm apart, all ≥ 1.0 mm copper.
  D1's GND pad has ≥ 2 vias right at the pad.
- U_USBA SY6280 [U8] in the south-east corner of Z-USB at (43.4, 62.6), rotation 0 (§3, D-91): C_USBA_IN 10 µF [C11]
  ≤ 2 mm from U8 pin 5 with a GND via at the pad (D-57; note the BOM ref is C11, D-57's "[C10]" is stale, see D-81);
  C_USBA_OUT 22 µF [C34] ≤ 2 mm from pin 1, west of U8; C_USBA_BULK 120 µF polymer [C35] at J4 pin 1 ([SY] p.5 "output
  capacitor as close to the connectors as possible"). R_SET [R37] ≤ 2 mm from pin 3 (`SENSE` USBA_ISET), R_USBAEN [R61] at
  pin 4. VBUS_USBA U8 pin 1 → J4 pin 1 ≤ 14.4 mm (≤ 15 mm rule).
- Bleeders R_BL5 [R12] (0805, 53 mW) and R25–R28: anywhere on their rails; R_BL5 ≥ 2 mm from other parts (it is the
  warmest small part: 5 V²/470 Ω = 53 mW, computed).

### 4.6 USB 2.0 (`usb`, `usbc`)

- SoC USB pins on the **south side, east part**: 26 USB_DM, 27 USB_DP (pads (37.83, 42.58) / (38.17, 42.58)).
  U_MUX TS3USB221A [U11] in the north-east part of Z-USB right below them (≈ 10 mm), then one path south to J4 (USB-A)
  and one south-east to J1 (USB-C). Floor-plan estimates (§5.5, ×1.2 detour) ≈ 31 mm (USB-A) and ≈ 41 mm (USB-C), under
  our 50 mm rule and well under the 4000 mil (≈ 100 mm) typical / 12000 mil
  maximum ([TI-HS] Table A-1 p.16).
- Rules ([TI-HS] Table A-1/A-2 p.16, §3.1–3.3 pp.9–10, §3.14 p.15): 90 Ω ± 10 %; P/N skew ≤ 50 mil (1.27 mm); **0 stubs;
  0 test points**; ≤ 4 vias per line (target 0: all on L1); ≥ 30 mil to other signals, ≥ 50 mil to clocks/periodic signals;
  bends ≥ 135°; break-out from a package within 0.25 in.
- USB-C J1: D+ and D− appear twice (A6/B6, A7/B7). Join A6–B6 and A7–B7 right at the connector (short stubs < 2 mm are
  unavoidable on a USB-C receptacle; keep them symmetric). U_ESD_C USBLC6 [U1] within 3 mm of J1, flow-through, GND pin
  with a via at the pad ([ST-ESD] §2.3 p.5: data, VBUS and GND tracks "as short as possible").
- USB-A J4 is through-hole. [TI-HS] §3.5 p.10 recommends connecting TH receptacles on the bottom layer to avoid a pin
  stub. **Deviation:** we connect on L1 (no vias in the pair); the stub is the 1.6 mm board + pin, ≈ 10 ps, negligible at
  480 Mb/s (computed, 1.6 mm / ≈ 0.16 mm/ps). U_ESD_A [U2] within 3 mm of J4 pins 2/3. (D-81)
- CC1/CC2 5.1 k [R1/R2] next to J1; no constraint beyond DEFAULT.

### 4.7 On/off controller and high-impedance nodes (`onoff`, `ui`)

- SW_PWR [SW1] sits **next to U_ONOFF [U3]** in Z-PWRIN, PB_IN ≤ 10 mm. [LTC] p.12 warns that a pushbutton "physically
  located far from the LTC2954 PB pin" picks up coupling/ringing on the high-impedance PB input; keeping it short avoids
  the extra 5.1 k / 0.1 µF parts it suggests. R_PB 0 R [R11] at the switch.
- C_PDT 2.2 µF [C6] (680 nF before D-117 c) ≤ 3 mm from U3 pin 7 (ONOFF_PDT, µA timer current); QPWR_G (100 k/47 k gate network) compact around
  Q1. Both `SENSE`: guard with GND, keep away from SW nodes, wash flux (leakage shifts the timing; [LTC] p.3 IPDT 2.4–3.6 µA).
- C3 100 nF ≤ 2 mm from U3 pin 1 (VIN). TP27–TP29 next to U3; TP29 and TP1 ≤ 10 mm apart (testpoints.md §2 rule 5).
- RESET [SW2] and MASKROM [SW3] in Z-UI with R_NPOR_KEY [R35] and R_RECOV [R36] at the switches; NPOR's R_NPOR_PU [R43]
  and C71 10 nF stay at SoC pin 66 (D-44), R_RECOV_PU [R44] and C_RECOV [C72] at pin 23.

### 4.8 ESD and connectors

- ESD arrays at the connector, before anything else on the line ([TI-HS] §3.14 p.15; [ST-ESD] §2.3).
- J1 shell (SH) and J4 shell (SH) to GND with ≥ 2 vias per shell pad; J3 SH to GND.
- Header J5 lines have no series parts (D-31); keep them on L1/L4 as DEFAULT. The two I²C pull-up pairs [R62/R63],
  [R64/R65] sit in Z-HDR, west of the SoC, anywhere on their lines (DC pull-ups; the header courtyard has no room for
  SMD parts).

## 5. Placement plan

### 5.1 Floor plan (top view, mm; rails not shown)

```
 x: 0         10        20        30        40        50        60        70        80
 y=0 +---------[ J3 RJ45 180° ]---[J6 UART]-[ Z-UI: SW2 SW3 LED1-3 TP7 TP11 ]-------+  north edge (routed)
     |H1    | (7.5-26.5, 0-21.8)  |29-37.6| (39-72, 1-11)                       H2 |
     |J5    |                     |Z-UART (27-39, 5-11)                            |
     |2x20  |                     |                     FID1 (51,20)  +--------+   |
     |hdr   +-------------+-------+------------------+                | Z-PMU  |   |
     |x1.2- | Z-ETH       |                          |  Z-NAND        | U6 3V3 |   |
     |7.3   | (8-20.5,    |   Z-SOC  U9 + Y1 + Y2    |  (49.5-61.5,   | U7 DDR |   |
     |y7.8- |  22-34)     |   (20.5-49.5, 22-50)     |   28-44)       | U4 0V9 |   |
     |59.6  +-------------+   centre (34.5, 36.5)    |                | U5 1V8 |   |
     |      | Z-HDR       |                          |                |(62-77, |   |
     |      | (8-20.5,    |                          |                | 12-48) |   |
     |      |  34-50)     +----------+---------------+-------+        +--------+   |
     |      | FID2 (19.5,51.2)       | Z-USB (27-45.5,       |Z-USBA-| Z-PWRIN     |
     |      +--Z-SDPWR (9-27,        |  50-64.5): U11, U2,   |PWR    | (55-77,     |
     |      |   52.5-64.5)           |  C35, C84, R60, U8 SE |(45.5- | 48-72.5)    |
     |H3    [ J2 microSD 11.5-27.5 ][ J4 USB-A 28-43.5  ]   | 55,   | F1 D1 U3 SW1|
     |      [   y 65-80           ][   y 65-80          ][J1 USB-C 44.2-54.8]    H4 |
 y=80+--------------------------------------------------(y 71.1-80)-----------------+  south edge (routed)
   west rail (V-cut x = 0)    (x 77-80: no zone, MLCC-free 3 mm strip)  east rail (V-cut x = 80)
```

Every rectangle is a row of `layout/zones.csv`. **Board size (D-84 round 2):** the round-1 plan on 70 × 70 mm put
328 mm² of courtyards into a 256 mm² SoC zone (128 %) and filled Z-PWRIN, Z-NAND and Z-USBA-PWR to 87–100 %. All 226
courtyards together are 2728 mm² (cached [KFP] courtyards, custom footprints from their drawings, `tools/courtyard.py`).
Without the six connectors (1342 mm²) that leaves 1385 mm² of parts, which at ≤ 55 % fill need ≈ 2520 mm² of
zones; a 70 × 70 board has ≈ 3400 mm² left after the connectors and M3 keep-outs, and three quarters of that would have to
be rectangular zones fitted around fixed edge connectors and a ≥ 28 mm SoC square. That is not a plan a first-time
layout can follow. The board is therefore **80 × 80 mm** (panel 90 × 80 mm), which D-H2 allows when it makes the build
simpler. Courtyards now fill 42.6 % of the board before routing.

**Capacity rule (check_layout L6):** the KiCad courtyard area of the parts assigned to a zone is **≤ 55 %** of the zone
area (the rest is routing, vias and the GND stitching). Z-PWRIN, Z-NAND and Z-USBA-PWR are also ≥ 2 × their courtyard
sum. A connector rectangle holds only its connector.

| Zone | Rectangle (mm) | Area mm² | Courtyards mm² | Fill |
|---|---|---|---|---|
| Z-SOC | x 20.5–49.5, y 22–50 | 812 | 428.4 (77 parts) | 52.8 % |
| Z-ETH | x 8–20.5, y 22–34 | 150 | 20.6 | 13.8 % |
| Z-HDR | x 8–20.5, y 34–50 | 200 | 7.0 | 3.5 % |
| Z-UART | x 27–39, y 5–11 | 72 | 18.8 | 26.0 % |
| Z-UI | x 39–72, y 1–11 | 330 | 118.2 | 35.8 % |
| Z-PMU | x 62–77, y 12–48 | 540 | 286.6 | 53.1 % |
| Z-NAND | x 49.5–61.5, y 28–44 | 192 | 71.9 | 37.4 % |
| Z-USB | x 27–45.5, y 50–64.5 | 268 | 123.5 | 46.0 % |
| Z-USBA-PWR | x 45.5–55, y 50–71 | 200 | 20.2 | 10.1 % |
| Z-PWRIN | x 55–77, y 48–72.5 | 539 | 248.1 | 46.0 % |
| Z-SDPWR | x 9–27, y 52.5–64.5 | 216 | 42.0 | 19.4 % |
| Board | 80 × 80 | 6400 | 2727.6 (226 parts) | 42.6 % |

The free strips (x 27–62 between y 11 and 22; x 49.5–62 between y 44 and 48) are spare room for H1. The strip x 77–80
(and x 0–3 on the west, where only the header sits) holds no zone.

**MLCCs near the V-cuts (round 3).** The rails are snapped off along the V-cuts at x = 0 and x = 80 after assembly, and
the score position has a ±0.4 mm tolerance ([JLC-CAP] "V-Cut" item 2). Ceramic capacitors close to a scored edge and at
right angles to it can crack when the board flexes (general depaneling practice; no source saved in refs/, UNVERIFIED
citation). Rules: **no MLCC within 3 mm of x = 0 or x = 80** (every zone that holds an MLCC stays inside x 3–77, check_layout
L6), and any MLCC within 5 mm of a V-cut (x < 5 or x > 75, i.e. the east 2 mm of Z-PMU and Z-PWRIN) lies **parallel to**
the V-cut (long axis along y). Break the rails off as §8 says.

| Zone / part | Position | Why |
|---|---|---|
| U9 RV1106G3 | centre (34.5, 36.5), rotated **+90°** (§5.2) | every interface side faces its connector |
| J3 RJ45 HR911105A | pad 1 at (21.46, 17.26), rotated 180°; at 180° the [KFP] fab front lies on y = 0 (mouth north); courtyard x 7.52–26.52, y −0.5…21.8 (clipped at the edge) | PHY pins at the SoC NW corner |
| J5 2×20 header | pin 1 at (3.00, 9.56), rotation 0°, odd pins x = 3.00, even x = 5.54, pins 39/40 at y = 57.82 | header GPIO pins are on the SoC west and north sides; Raspberry-Pi pin order kept (D-22) |
| J6 UART 1×3 | pin 1 (GND) at (30.77, 2.77), rotated 90° (row along +x) | near UART2 pins 79/80 (north side, x ≈ 34.0–34.4); TP9/TP10/TP20 in Z-UART below it |
| Z-UI | SW2 RESET, SW3 MASKROM, LED1 PWR, LED2 STAT, LED3 ETH + resistors, TP7, TP11 | buttons and LEDs on one edge |
| Z-PMU (x 62–77) | four 9 mm cells north → south U6 3V3, U7 DDR, U4 0V9 (level with the L3 neck), U5 1V8; inputs east, output links JP1/R29/R30/R31 in the west strip x 62–65; TP2–TP5, TP15 | east side faces the DDR and VDD_0V9 pins; next to the 5 V entry; 3 mm from the V-cut |
| Z-NAND | U10, C80/C81, R52–R55 | FSPI pins on the east side |
| Z-USB (x 27–45.5) | U11 (NE part, under pins 26/27), C84, R60; U2 and C35 at the south end next to J4 pins; **U8 + C11, C34, R37, R61 in the south-east corner**, U8 at (43.4, 62.6) | short USB path, ESD and bulk cap at the USB-A pins; VBUS_USBA U8 → J4 pin 1 ≤ 14.4 mm (§3, D-91) |
| Z-USBA-PWR (x 45.5–55) | **U1** at the south end next to J1, TP17 | U1 within 3 mm of J1 data pins; L3 below carries the VCC5V0_SYS feed to U8 |
| Z-PWRIN (x 55–77) | F1, D1, R1–R3, C2, U3, Q1–Q3, C3–C6, R5–R12, SW1, power test-pad row | J1 VBUS pads are at its west edge; SW1 next to U3 (§4.7); 3 mm from the V-cut |
| J1 USB-C | footprint origin (49.5, 76.35), **rotation 0°**; mating face on the south edge (see below) | power entry on the south edge; clear of H4 |
| J4 USB-A | x 28–43.5, y 65–80, opening on the south edge (legs 15.30 wide, 14.20 deep: refs/usb-a-af90-wjdg-datasheet p.1) | below U11 |
| J2 microSD TF-01A | x 11.5–27.5, y 65–80 (body 14.50 × 15.35 mm: refs/tf-01a-datasheet p.1), slot opening on the edge | SDMMC pins on the south side |
| Z-SDPWR | Q4, C21–C23, C26, R38–R40, R49, TP16, TP30 | between the SoC south-west and J2 |
| Z-ETH / Z-HDR | R56–R59, C82, C83 / I²C pull-ups R62–R65 (DC; position on the line not critical) | west of the SoC |
| Z-SOC | U9, all SoC decouplers, Y1/Y2 + load parts, TP6/TP31, nPOR/ZQ/EXTR/ADC parts, FB1–FB3, R32/R33/R34, D2, R4/C1 (USB_DET), NT1, R66/R67, TP18/TP22–TP26 | rings around U9 (§5.3); check_layout L5 fails any part with a SoC-pin target or a ring rule, and any crystal part, outside Z-SOC |

**J1 rotation 0° (round-2 fix).** In the cached `USB_C_Receptacle_HRO_TYPE-C-31-M-12` the body (F.Fab) spans y −3.65…+3.65
and the SMD signal pads sit at y = −4.045, so at **rotation 0°** the mouth faces +y = south. With the origin at (49.5,
76.35) the fab front is at y = 80.0 (the edge) and the signal pads at y = 72.3. (Round 1 wrote "rotated 180°", which puts
the mouth north and the pads at y ≈ 80.4, off the board.) check_layout L6 now computes every library connector's
rectangle from the cached `.kicad_mod` at the stated origin and rotation, checks the pads are on the board and the body
front is on the mating edge, instead of trusting typed-in rectangles.

### 5.2 SoC orientation and pin sides

[DS] Fig. 2-3/2-4 p.16: top view has pin 1 at the top-left corner and the pins run counter-clockwise (1–32 down the
left side, 33–64 along the bottom, 65–96 up the right side, 97–128 along the top). Placed **rotated +90°** (KiCad
counter-clockwise), the board sides are:

| Board side | Pins (direction) | Functions on that side | Faces |
|---|---|---|---|
| South | 1 → 32 (west → east) | MIPI AVDD 1, SDMMC 11–18, RTC 19–21, SARADC 22–23, USB 24–28 (DM 26, DP 27), codec 30–31 | J2 microSD, Y2, U11 → J4/J1 |
| East | 33 → 64 (south → north) | codec GND 37, FSPI 39–48, DDR VDDQ 49/50/56, ZQ 52, VDD_0V9 51/54/55, GPIO0 58–64 (PB_INT_N 60, LED_STATUS 62, PWR_KILL 63, USBA_VBUS_EN 64) | U10 NAND, Z-PMU |
| North | 65 → 96 (east → west) | USB_SEL 65, nPOR 66, OSC 68/69, PLL 70/71, GPIO1 72–80 (UART2 79/80), header GPIO 83–95, ETH_AVDD1V8 96 | Y1, J6, Z-UI, header (via L4) |
| West | 97 → 128 (north → south) | ETH 97–102, header GPIO 104–114, VDD_ARM 115, VDD_0V9 116 | J3 RJ45 (NW), J5 header |

The pin-1 mark of the footprint ends up at the **south-west** corner. `layout/placement.csv` column `target` gives the board
coordinate of the SoC pad each SoC-side part belongs to.

### 5.3 Decoupling and SoC-side parts (single-sided assembly, two rings)

All parts are on the top (D-67), so the SoC decouplers cannot go under the SoC as on many references. Geometry, measured
from the SoC centre: pad toes at 6.45 mm (§6.1), escape vias ≥ 1.0 mm outside the toes (≥ 7.45 mm), Z-SOC edge at
13.5–15.0 mm (west 14.0, east 15.0, north 14.5, south 13.5). That leaves ≈ 6 mm all round for two rings:

- **Ring 1 (≈ 7.5–10.5 mm from the centre), ≤ 3.0 mm of trace from the pin:** every **100 nF** decoupler tagged
  `U_SOC pin N` (22 parts, smallest value closest), ZQ 240 R [R41] at pin 52, ETH_EXTR 6.04 k [R42] at pin 102,
  CODEC_VCM 4.7 µF [C70] at pin 30 (reference node), nPOR R43/C71 at pin 66, RECOVERY R44/C72 at pin 23, SARADC R45/C73
  at pin 22, R_PD58 [R46] at pin 58; R47/R48 ≤ 2 mm from pins 48/15; Y1 + R50/R51/C76/C77 at pins 68/69 and Y2 + C78/C79
  at pins 20/21 (§4.3). The trace goes **pin → capacitor → plane via**; the GND pad gets its own via to L2 within 0.5 mm.
- **Ring 2 (≈ 10.5–14 mm), ≤ 8 mm of trace from the pin, placed outside ring 1:** the **1 µF, 4.7 µF and 10 µF**
  decouplers, ferrite beads FB1 (pin 101), FB2 (pin 31), FB3 (pin 96), R_MIPI_1R [R32] (pin 1), R_USB18_1R [R33] (pin 24),
  D_RTC [D2] + R_RTC_SER [R34] (pin 19), NT1 at pin 115, R4/C1 (USB_DET, pin 25), UART resistors R66/R67 (pins 79/80, with
  TP9/TP10 in Z-UART, D-30) and the sub-rail test pads TP18, TP22–TP26 (DC pads, short stubs). Bulk capacitors work
  through the plane/island inductance, so a few mm more trace does not matter at their frequencies; the 100 nF parts are
  the ones that must be close.
- `layout/placement.csv` states ring 1 / ring 2 and the distance for each part.

### 5.4 Test pads

31 pads TP1–TP31, `TestPoint_Pad_D1.5mm` (courtyard 2.5 × 2.5 mm), top side, per `testpoints.md` §2: the power row
(TP21, TP1, TP13, TP4, TP15, TP5, TP3, TP2, TP14, TP8, TP12, TP19) along the boundary of Z-PWRIN and the south end of
Z-PMU (y ≈ 48); TP6/TP31 at Y1 (Z-SOC); TP9/TP10/TP20 in Z-UART at J6; TP27–TP29 at U3; TP30 and TP16 in Z-SDPWR; TP17 in
Z-USBA-PWR. None on a differential pair (§4.2, §4.6).

### 5.5 Length estimates from the floor plan (`layout/lengths.csv`)

The length rules of §4 (ETH ≤ 30 mm, USB ≤ 50 mm per path, SDMMC ≤ 40 mm, FSPI ≤ 25 mm) are checked against this floor
plan before H1, so a later rearrangement cannot silently break them. Estimate = octilinear distance (45° routing:
max(dx, dy) + 0.414 × min(dx, dy)) × **1.2 detour**, from the SoC pad to the far end, summed over the path. Far ends:
J3 and J1 pads from the cached footprints at their placed origin/rotation; J2 contacts, J4 pins 2/3 (custom footprints,
not drawn yet) at a point 1.5 mm inside the rear edge of their rectangle (ESTIMATE); U10 at the centre of Z-NAND; U11
in the north-east of Z-USB. check_layout L6 recomputes each estimate.

| Class | Path | Estimate | Limit | Use |
|---|---|---|---|---|
| ETH_DIFF | SoC 97–100 → R56–R59 → J3 pins 1/2/3/6 | 18.5–21.7 mm | 30 mm | 72 % |
| USB_DIFF | SoC 26/27 → U11 → J1 A6/A7 | 41.2 mm | 50 mm | 82 % |
| USB_DIFF | SoC 26/27 → U11 → J4 pins 2/3 | 31.1 mm | 50 mm | 62 % |
| SDMMC | SoC 12–18 → (R48) → J2 | 35.4–36.4 mm | 40 mm | 91 % |
| FSPI | SoC 39–48 → (R47) → U10 | 18.2–19.8 mm | 25 mm | 79 % |

SDMMC is the tightest: route the SD bus first after the SoC escape, straight south-west, and keep J2 at x 11.5–27.5.

## 6. SoC footprint, exposed pad and thermal

### 6.1 QFN-128 land pattern (`board:RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm`, drawn in H1; D-74)

Package ([DS] Fig. 2-5 p.17): body 12.3 × 12.3 mm BSC, pitch **0.35 mm**, lead width b 0.08/0.13/0.18 mm, lead length L
0.3/0.4/0.5 mm, EP D2 = E2 = 6.9/7.0/7.1 mm, K (lead tip to EP) 2.25 mm REF, thickness 0.85 mm.

| Feature | Value | Reason |
|---|---|---|
| Perimeter pad | **0.19 × 0.75 mm**, centre 6.075 mm from the body centre (pad from 5.70 to 6.45 mm) | covers b max 0.18; toe 0.30 mm outside the body edge, inner end 0.05 mm past the nominal lead end (5.75 mm) |
| Pad-to-pad gap | 0.35 − 0.19 = **0.16 mm** | ≥ JLC "SMD pad to pad clearance (different nets) 0.15mm" ([JLC-CAP] "Traces") |
| Corner pads | ≥ 0.18 mm in x and y between the last pads of adjacent rows (0.25 mm diagonal) | the inner pad end is held at 5.70 mm for this |
| Solder mask | 1:1 openings (0 expansion), mask web 0.16 mm | [JLC-CAP] "Soldermask Expansion 1:1", "Soldermask bridge 0.10mm (green)" |
| Paste, perimeter | 1:1 with the pads | area ratio = L·W / (2 (L + W) t) = 0.1425 / (1.88 t): **0.76 at a 0.10 mm stencil** (target), 0.63 at 0.12 mm, below the usual 0.66 minimum for reliable release. The order remark (§8) asks JLC for a **0.10 mm stencil** (D-85 amendment); JLC's default thickness for Standard PCBA is UNVERIFIED |
| EP pad 129 | **7.0 × 7.0 mm**, mask 1:1 | = D2/E2 nominal; netlist pad 129 = GND ([DS] p.19 "VSS E-PAD") |
| Note | 0.19 mm pads are below JLC's generic "Minimum SMD pad 0.25 × 0.25 mm" line in [JLC-CAP]; that line cannot apply to 0.35 mm-pitch parts, which JLC lists as its Standard minimum ([JLC-ASM], D-61). Expect a DFM comment; answer it on the order (UNVERIFIED how JLC treats it). | D-61 |

Escape: one 0.10–0.15 mm trace straight out of each pad (escape trace pitch 0.35 mm leaves ≥ 0.20 mm between neighbours),
first via ≥ 1.0 mm outside the pad toes. Do not route between perimeter pads. Supply pins fan out to vias into the L3
islands; GND pins (37, 57) go straight to an L1 GND finger and via.

### 6.2 Exposed pad: thermal vias and paste (windowpane)

- **16 thermal vias**, 0.3 mm drill / 0.5 mm pad (standard size, §3), placed in the gaps of the paste windows:
  x = ±1.15 mm with y ∈ {−2.3, −1.15, 0, 1.15, 2.3} (10 vias) and y = ±1.15 mm with x ∈ {−2.3, 0, 2.3} (6 vias), relative to
  the EP centre. All connect solidly (no thermal relief) to L2 GND and the L4 GND pour; anti-pads in the L3 VDD_0V9 island.
- **Tenting / filling:** since D-H6 / D-117 b the board is ordered with **POFV** (JLCPCB epoxy-filled and capped via-in-pad,
  supersedes D-67): the 16 EP vias and every board via in or touching an SMD pad are filled and capped; the list for the
  order is `pcb/via_in_pad.csv` (28 rows, checked exact by `check_routing` L5F-vip). The 4-layer POFV price is UNVERIFIED
  (owner, at order time).
- **Paste windowpane:** 3 × 3 squares of **1.65 × 1.65 mm** at 2.30 mm pitch, centred on the EP: 9 × 2.72 = 24.5 mm² =
  **50 %** of the 49 mm² pad (computed). Every window edge is ≥ 0.175 mm from the nearest via hole, so paste is not printed
  over a hole (less wicking, fewer voids).
- Barrel conduction (computed, information): one via ≈ 230 K/W, 16 vias ≈ 14 K/W to the bottom; the main heat path is the
  EP → L2 plane 0.21 mm below.

### 6.3 Thermal estimate

[DS] Table 4-1 p.25: θJA 27.3 °C/W, θJB 12.5 °C/W, measured on a JEDEC 2S2P 4-layer 114.3 × 76.2 mm board; Tj max 125 °C
([DS] §4.1). SoC power, from the power.md §5 **estimates** (UNVERIFIED, no [DS] figure): VDD_0V9 0.90 W + VCC_DDR 0.48 W +
1.8 V analog ≈ 0.36 W + 3.3 V IO/PHY ≈ 0.46 W ≈ **2.2 W worst case**. With θJA 27.3: ΔT ≈ 60 °C → Tj ≈ 85 °C at 25 °C
ambient. Our board (6400 mm², 80 × 80 mm) is ≈ 73 % of the JEDEC board's area, so θJA will be higher (by how much is UNVERIFIED).
Rev A is a bench board at room temperature: OK with margin. At the 60 °C design ambient of D-56 the worst-case estimate
reaches ≈ 120 °C, too close to 125 °C: measure SoC case temperature under load at bring-up (H3) and add a stick-on heatsink
if it exceeds 85 °C (owner decision only if needed; no layout change: keep the top of U9 clear of silk and parts).

### 6.4 Other custom footprints (drawn in H1, pad names fixed by D-74)

| Footprint | Draw from | Key check |
|---|---|---|
| `board:TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm` (U11) | TI TS3USB221A datasheet, RSE0010A package / land-pattern pages (`refs/ts3usb221a-datasheet/`) | pins 7/8 (SoC side) toward the SoC, flow-through |
| `board:L_FHD4020S_4.0x4.0mm` (L1–L4) | FHD4020S drawing (`refs/fhd4020s-datasheet/`, image-only PDF: read the land pattern from the drawing) | 2 pads, 4.0 × 4.0 mm body |
| `board:SW_TS-1187A_5.1x5.1mm` (SW1–SW3) | TS-1187A drawing (`refs/ts-1187a-datasheet/`) | pads 1 = A, 2 = B, 3 = C, 4 = D; A–B and C–D joined internally |
| `board:microSD_TF-01A` (J2) | refs/tf-01a-datasheet p.1 "PCB Layout (Pattern Side)": 9 contacts at 1.10 mm pitch, 2 × Ø1.00 locating holes 8.00 mm apart, 4 shell tabs | pad 9 = card detect "cd", SH = 4 shell tabs; pad numbering against the drawing is UNVERIFIED until drawn (Phase 5 note) |
| `board:USB_A_AF90_WJDG_RightAngle_THT` (J4) | refs/usb-a-af90-wjdg-datasheet p.1: 4 × Ø0.9 mm pins (2.0 mm inner pitch, 7.0 mm outer), 2 × Ø2.1 shell legs | pad 1 VBUS … 4 GND, SH = shell; hole sizes = drawing + 0.1–0.2 mm |
| QFN-128 (U9) | §6.1 / §6.2 | — |

## 7. Ground strategy

- **One GND net, no analog/digital split** (the netlist has a single GND; [DS] gives no split requirement and [LF] is
  copied). L2 is solid under the whole board; L1 and L4 are GND-poured and stitched to L2.
- Return paths: every high-speed net runs on L1 directly over L2 and never crosses an L2 opening ([TI-HS] §2.4 p.6).
- Each GND pad of a decoupler, buck, ESD part, crystal cap and TVS gets its own via (or two) to L2 right at the pad.
- Buck GND: input-cap GND, IC GND pin and output-cap GND joined on L1 in a small copper area with ≥ 4 vias to L2 per cell
  ([TLV] §10.1 "low side of the input and output capacitors must be connected properly to the power GND").
- Connector shells (USB-C, USB-A, RJ45) to GND directly (netlist); no chassis ground, no RC to chassis (Phase 5: [LF] C68
  not placed).
- Stitching vias: ≤ 5 mm grid over poured areas, rows along both sides of the diff pairs at ≤ 5 mm, a ring along the
  board edge at ≈ 3 mm pitch (keeping 0.4 mm from the V-cut).

## 8. Fabrication and assembly notes (for the H2 order)

| JLCPCB order field | Value |
|---|---|
| Base material / layers | FR-4, 4 layers |
| Dimensions | 90 × 80 mm (board 80 × 80 + rails); delivery format: panel by customer, 1 design, rails + V-cut drawn in the Gerbers |
| PCB qty | 5 (2 assembled + 3 bare, D-H2) |
| Thickness / stackup | 1.6 mm, impedance control **JLC04161H-7628** |
| Surface finish | **ENIG** |
| Outer / inner copper | 1 oz / 0.5 oz |
| Via covering | **epoxy filled & capped (POFV)**, all vias (D-H6, D-117 b, D-119; was tented, D-67) |
| Min via hole | 0.3 mm (no small-via option) |
| Generated order notes | `pcb/fab/order-notes.md` (D-132) supersedes this table where they differ |
| Colour | green / white |
| Assembly | **Standard PCBA**, top side, qty 2, "confirm parts placement" on |
| Stencil | ask for **0.10 mm** thickness in the PCBA remark (below); if the form has a stencil-thickness field, set it to 0.10 mm |
| Remark | "Edge rails and fiducials included in the Gerbers; V-cut along x = 0 and x = 80 (layer V-CUT) to remove the rails. U9 is a 0.35 mm-pitch QFN; please use a 0.10 mm stencil (or confirm the thickness)." |

- CPL rotation: KiCad's rotations do not always match JLC's reels; check every IC and polarised part (diodes, LEDs, C35,
  Q1–Q4, U1–U11, Y1) in JLC's placement preview before paying (H2).
- PCB price: cost.md now carries **$58** for the 80 × 80 board (90 × 80 panel), the round-1 $45 estimate scaled with
  panel area; total $373.34 ≤ $380 (`check_bom.py design`). ESTIMATE, UNVERIFIED until the live quote (D-H2, D-84).
- **Depaneling:** break the two rails off with a depaneling tool or with flat pliers gripping the rail close to the V-cut,
  not by bending the whole board by hand; this keeps flex away from the MLCCs (§5.1). No MLCC is within 3 mm of a V-cut.
- THT parts (J3, J4, J5, J6, J1 shell pegs) are hand/wave soldered by JLC (D-67); keep ≥ 3 mm around their pins free of
  SMD parts on the bottom (there are none) and ≥ 1 mm on the top.

## 9. Gate TP-D7 self-check

Gate text (PLAN.md Phase 7): "every high-speed/sensitive net has a rule; trace widths computed for the stackup; checklist
ready for the human DRC review". `tools/check_layout.py`: **see the result line in LOG.md** (last run: all pass).

| Gate clause | Evidence | Check |
|---|---|---|
| Every high-speed/sensitive net has a rule | netclasses.csv: 135/135 nets classified; 76 nets in 17 non-default classes with width/clearance and length/other rules; an independent pattern list (ETH, USB, crystal, SDMMC, FSPI, SW, FB, ZQ, EXTR, VCM, ISET, PDT, ADC, RECOVERY, USB_DET, nPOR, gate) never lands in DEFAULT | L1, L2 |
| Trace widths computed for the stackup | impedance: field solver on the JLC04161H-7628 cross-section, validated < 1 % vs closed form; ETH 0.235/0.200 mm, USB 0.255/0.150 mm within ±5 % on two grids. Current: IPC-2221 for outer 1 oz and inner 0.5 oz, chosen ≥ minimum for every rail of power_rails.csv | L3, L4 |
| Checklist ready for the human DRC review | §10, ≥ 30 tick-box items; board.kicad_dru for KiCad DRC | L7 |
| PLAN outputs: stackup, impedance targets, placement plan, ground strategy, thermal-pad vias, outline (80 × 80 mm, D-H2 "larger if simpler") with rails and fiducials, mounting holes | §1–§8; L3 plane plan computed from the placement (planes.csv: island holds every VDD_0V9/VDD_ARM escape via, regions ≥ 0.3 mm apart and connected, neck ≥ 3 mm level with U4, VCC_3V3 fed from R30, VCC5V0_SYS over Z-PWRIN/Z-PMU/U8); VDD_0V9 drop 6.6 mV and VBUS_USBA ≤ 14.4 mm (power_paths.csv); one crystal length budget; U9 pad and buck-pad DRU exceptions; no MLCC within 3 mm of a V-cut; every SoC-pin/ring/crystal part in Z-SOC; placement.csv covers all 226 parts; zones, connectors, holes and fiducials do not overlap; connector rectangles recomputed from the cached footprints at their origin/rotation with the body front on the edge; every zone ≤ 55 % courtyard fill; floor-plan length estimates within the §4 limits (§5.5) | L5, L6, L7 |

## 10. DRC checklist for the human review (H1)

Setup
- [ ] Board Setup › Stackup: 4 layers, thicknesses and Er of §2.1; board thickness 1.6 mm.
- [ ] Board Setup › Constraints: min track 0.10 mm, min clearance 0.10 mm (escape only), via 0.3/0.5 mm, hole-to-hole 0.45 mm, copper-to-edge 0.4 mm.
- [ ] Net classes created from `layout/netclasses.csv` (17 classes + DEFAULT); every net assigned (Board Setup shows no unassigned sensitive net).
- [ ] `layout/board.kicad_dru` loaded in Custom Rules, syntax check passes (fix syntax if KiCad complains; the rules are in §4). Skew rules use `(within_diff_pairs)`; the 0.76 mm pair-clearance rules apply to tracks only, outside the U9/J1/U1/U2/U11 courtyards; edge clearance is one plain 0.40 mm rule.
- [ ] Diff-pair naming: KiCad pairs nets whose names end in P/N or +/−. `ETH_TXP`/`ETH_TXN` pair; the `_J` segments (`ETH_TXP_J`) and the USB nets (`USB_DP`/`USB_DM`, …) do **not** end in P/N, so the diff-pair router and the DRU gap/skew rules do not see them as pairs. **Confirmed on KiCad 10.0.7 (L4 r1 verifier probe, D-112 d):** a probe DRU with skew ≤ 0.01 mm and uncoupled ≤ 0.1 mm on both pair classes flagged only `ETH_RX*`/`ETH_TX*`; the USB skew, diff_pair_gap and diff_pair_uncoupled constraints never run, so "DRC 0 errors" says nothing about them. The authority for USB skew (pad to pad, per USB-C plug orientation), gap, coupling and stubs is `pcb/scripts/l4check.py` (`pcb/routing-report.md`); the USB 30 mil clearance rules are class rules and do run. Renaming the nets would be a schematic change (not done).
- [ ] Custom footprints of §6.1/§6.4 drawn and checked against their drawings; pad names = D-74 (netlist import shows no missing pads).
- [ ] JLCPCB impedance calculator gives w/s within 3 % of §2.2 (else update the classes and decisions.md).

Outline and mechanics
- [ ] Edge.Cuts 80 × 80 mm, R 1 mm corners on the board itself (rail notches, D-117 h); rails 5 mm west/east drawn, V-cut lines at x = 0 and x = 80 on layer V-CUT (User.1, plotted with the fab set in L6); panel 90 × 80 mm.
- [ ] Diff-pair L4 hops have In2 GND under them and a GND via within 1 mm of each hop via (D-H6; recorded exceptions D-117 f).
- [ ] 3 global fiducials on the rails, 2 local fiducials near U9, all 1 mm copper / 2 mm mask, no paste.
- [ ] 4 tooling holes 2.0 mm NPTH in the rails.
- [ ] 4 × M3 3.2 mm NPTH at the corners with 7 mm keep-out on all layers.
- [ ] RJ45, microSD, USB-A and USB-C faces on their edges; nothing overhangs the west/east edges. J1 at (49.5, 76.35) with **rotation 0°** (mouth south, signal pads at y ≈ 72.3); J3 at (21.46, 17.26) rotated 180° (mouth north).
- [ ] No copper within 0.8 mm of the V-cut lines (D-H6; no exception since D-118 a), 0.3 mm of the routed edges.
- [ ] Via in pad: POFV ordered (D-H6); every via in / touching an SMD pad or within 0.10 mm of its mask opening is listed in `pcb/via_in_pad.csv`.

Placement
- [ ] Every part inside its zone of `layout/placement.csv` (or the change written in decisions.md).
- [ ] U9 rotated so pin 1 is at the south-west corner; local fiducials clear of its courtyard.
- [ ] Ring 1: every 100 nF SoC decoupler ≤ 3.0 mm trace from its pin, cap before via, own GND via. Ring 2: 1/4.7/10 µF decouplers, FB1–FB3, R32–R34, D2, NT1 and TP18/TP22–TP26 ≤ 8 mm, outside ring 1 (§5.3).
- [ ] Zone fill: no zone more crowded than its §5.1 courtyard fill suggests; if a part moves zone, update placement.csv/zones.csv and rerun check_layout (≤ 55 % rule).
- [ ] Y1 ≤ 3 mm from pins 68/69; R50 ≤ 2 mm from pin 69; Y2 ≤ 4 mm from pins 20/21; GND guard rings stitched.
- [ ] Crystal lengths (DRU per-net rules): OSC_XIN and OSC_XOUT_X ≤ 5 mm, RTC_XIN and RTC_XOUT ≤ 6 mm, OSC_XOUT ≤ 8 mm in total with the TP6 stub ≤ 3 mm (measure the stub by hand).
- [ ] Each buck cell: C_IN ≤ 1 mm from VIN/GND pins, inductor ≤ 3 mm from SW, divider ≤ 3 mm from FB on the regulator side of JP1/R29/R30/R31. Since D-H6: the input loop closes on L1 — each input cap's GND pad reaches IC pin 2 along L1 GND copper in ≤ 3 mm, pin 2 solid (no spokes) with ≥ 2 GND vias within 1 mm (on the SOT-23-5 the GND and VIN pins are on opposite sides, so the GND strap runs under the body, TI SLVSDG1C Fig. 20).
- [ ] U8 in the south-east corner of Z-USB at (43.4, 62.6), rotation 0; VBUS_USBA U8 pin 1 → J4 pin 1 ≤ 15 mm measured on the real J4 footprint (estimate 14.4 mm worst case); C_USBA_IN [C11] ≤ 2 mm from U8 pin 5 with a GND via at the pad; C34 ≤ 2 mm from pin 1; R37 ≤ 2 mm from pin 3; C35 at J4 pin 1.
- [ ] No MLCC within 3 mm of the V-cuts (x = 0, x = 80); MLCCs within 5 mm of a V-cut lie parallel to it (long axis along y).
- [ ] Z-PMU cells at y 12–21 (U6), 21–30 (U7), 30–39 (U4), 39–48 (U5), inputs east, links in the x 62–65 strip; JP1 at (63.7, 35.0) rotated 180°, R30 at (63.5, 16.5).
- [ ] U1 ≤ 3 mm from J1 data pins, U2 ≤ 3 mm from J4 pins 2/3, both flow-through.
- [ ] SW1 next to U3 (PB_IN ≤ 10 mm); C6 ≤ 3 mm from U3 pin 7.
- [ ] Test pads per testpoints.md §2; none on ETH/USB pairs; TP29–TP1 ≤ 10 mm.

Routing
- [ ] ETH pairs 0.235/0.200 mm on L1, ≤ 30 mm, skew ≤ 1.27 mm, no vias, uncoupled ≤ 5 mm at J3.
- [ ] USB pairs 0.255/0.150 mm on L1, skew ≤ 1.27 mm, 0 stubs except the USB-C A/B join (< 2 mm, symmetric), ≤ 4 vias (target 0).
- [ ] Diff pairs ≥ 0.76 mm from other nets **and from the other pair** (ETH TX vs RX, USB-A vs USB-C paths; the DRU cannot check pair-to-pair inside one class), ≥ 1.27 mm from crystal and SW nets; never over an L2 gap.
- [ ] SDMMC ≤ 40 mm and FSPI ≤ 25 mm, each within ± 5 mm of its clock; R47/R48 ≤ 2 mm from pins 48/15. Lengths across a series part are **summed by hand**: KiCad measures each net separately, so add SDMMC_CLK + SDMMC_CLK_SD (R48), FSPI_CLK + FSPI_CLK_NAND (R47), FSPI_CS0N + FSPI_CS0N_NAND (R55) and each ETH net + its `_J` segment (R56–R59) for the 30 mm ETH rule and the P/N skew.
- [ ] SW nodes ≤ 3 mm, 1.2 mm wide; FB and all SENSE nets ≥ 2 mm from SW nodes and inductors; EN / PWR_EN / PB nets ≥ 1 mm from SW copper and out of the inductor courtyards (D-H6).
- [ ] Power widths ≥ §3 (PWR_5V 1.0 mm, PWR_USBA 0.8 mm, PWR_0V9 0.8 mm, ...); via counts ≥ §3 at each layer change; JP1 ≥ 6 vias.
- [ ] No ETH/USB/XTAL/SDMMC/FSPI/SW/SENSE net on L4; L4 traces crossing L3 island edges are DEFAULT only.
- [ ] VDD_0V9 L3 island x 26.05–42.95 / y 28.05–44.95 covers every VDD_0V9 pin via (and VDD_ARM pin 115 / NT1) with ≥ 1 mm margin; 4 mm neck y 33–37 from JP1 to the island; NT1 at pin 115.

Planes and thermal
- [ ] L2 solid GND: zero tracks, no slots (check with the layer alone visible).
- [ ] L3 regions drawn from `layout/planes.csv` (VDD_0V9 island + neck, VCC_3V3 band/column/tongues fed from R30, VCC5V0_SYS PMU/PWRIN/USB-A strip, VBUS_USBA pour) with ≥ 0.3 mm gaps; rest of L3 GND fill; no region boundary under ETH/USB/XTAL/SDMMC/FSPI routing on L1 (L2 shields it, but keep it tidy).
- [ ] DRC shows no U9 pad-to-pad errors (DRU rule "U9 pads", 0.15 mm) and no FB-pad-to-SW-pad errors on U4–U7 (the 2.0 mm sense rule is tracks/zones only, outside their courtyards); if it does, the DRU syntax needs fixing, not the footprint.
- [ ] EP: 16 thermal vias at the §6.2 positions, solid connection to L2/L4, real board vias filled and capped (POFV, D-119); paste windowpane 3 × 3 × 1.65 mm (50 %).
- [ ] QFN pads 0.19 × 0.75 mm, gap 0.16 mm, mask 1:1; corner pads ≥ 0.18 mm apart; perimeter paste 1:1, area ratio ≥ **0.76** at the 0.10 mm stencil asked for in the order remark (§6.1, §8).
- [ ] GND stitching ≤ 5 mm grid, along diff pairs and around crystals; edge ring 0.4 mm clear of the V-cut.

Final
- [ ] KiCad DRC: 0 errors, every warning explained in decisions.md.
- [ ] KiCad "Update PCB from netlist" clean (226 footprints, 135 nets), no unconnected items.
- [ ] Silkscreen per §1 (TP labels, pin 1 marks, button/LED names, Rev A), ≥ 1.0 mm text / 0.15 mm stroke, lines ≥ 0.15 mm, ≥ 0.15 mm from pads, none beyond the edge.
- [ ] 3-D viewer: connector bodies on the edges, no part collisions, nothing on the bottom side.
- [ ] Gerbers + drill + CPL + BOM exported; JLCDFM check passes (H2 gate); CPL rotations checked in JLC's preview.
- [ ] After delivery: rails removed with a depaneling tool or pliers at the V-cut, not by bending the board (§8).

## 11. Open items (UNVERIFIED, resolved in H1/H2/H3)

1. JLC's impedance calculator vs our solver (§2.2) — H1 cross-check.
2. How JLC wants V-cut lines and customer rails marked; tooling-hole positions (§1) — H2 DFM/engineer.
3. Fiducial footprint library name (§1) — draw by hand if absent. **L1: stock `Fiducial:Fiducial_1mm_Mask2mm` exists in KiCad 10.0.7 (D-99).**
4. Stencil: the order remark asks for 0.10 mm (area ratio 0.76); whether JLC confirms it, and the DFM comment on the
   0.19 mm pads (§6.1) — H2.
5. SoC thermal on the 80 × 80 board (§6.3) — H3 temperature measurement.
6. SDMMC/FSPI length rules are engineering rules, no Rockchip layout guide found (§4.4).
7. IPC-2221 constants from the published fit, not the standard text (§3).
8. TF-01A pad numbering (§6.4) — when the footprint is drawn. **L1: pads = the drawing's labels cd, 8 … 1 (D-99, design/pcb/footprints.md).**
9. Floor-plan length estimates (§5.5) use assumed contact positions for the custom J2/J4 footprints — recheck SDMMC
   (91 % of its limit) once TF-01A is drawn in H1.
10. KiCad diff-pair recognition of `_J`, `_DP`/`_DM` net names (§10) — H1; renaming the nets is a Phase 5 change.
11. PCB price at 80 × 80 mm ($58 ESTIMATE, cost.md) — the owner's live quote at H2.
12. Which outer pin of the AF90 WJDG USB-A (J4) is VBUS: the drawing gives the 7.0 mm pitch but no pin numbers. U8's
    placement meets ≤ 15 mm for either side (14.4 / 7.3 mm); confirm when the J4 footprint is drawn in H1. **L1: pin 1 = west
    outer pin with the mouth south (the 14.4 mm case), D-99.**
13. KiCad rule-priority and `memberOfFootprint` / `intersectsCourtyard` behaviour of the round-3 DRU rules ("U9 pads",
    sense rule) — check in H1 with the DRC (DRU syntax is UNVERIFIED as a whole).
14. MLCC flex-crack distance from a V-cut (3 mm / 5 mm parallel, §5.1) is general practice without a saved source.
