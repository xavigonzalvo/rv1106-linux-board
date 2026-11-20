# L5F — CHECKPOINT-2 review fixes (owner decision D-H6 "Yes, fix all (POFV)"; decisions.md D-117, round 2 D-118)

> **Round 2 (2026-11-07, D-118):** the L5F verifier's findings are fixed: the three J5 west lanes now keep >= 0.8 mm
> from the V-cut (§4, the former DEV D-117 d is withdrawn), the rail notches are 1.5 x 1.5 mm with R 0.5 mm air-side
> corners and a new router-corner check (§9), the neck-downs keep the wide copper off the pads with a new polygon-overlap
> check (§8), the six test pads have bare-number silk labels (§10) and the corner renders draw Edge.Cuts / V-CUT. The
> pair-via stitching distances (§7) are unchanged, with the reason in D-118 b.

Board `design/pcb/rv1106-reva.kicad_pcb`. Coordinates are board mm (page minus 50, 50). Every change is a script in
`design/pcb/scripts/l5f_run.sh`, run by `rebuild_all.sh` after the L5 steps (clean rebuild reproduces the board; see
the end). Every measurable item has a FAIL-capable check in `scripts/l5fcheck.py` (called by `check_routing.py`) and a
mutation in `scripts/mutate_l5f.py` that makes that check FAIL (`trial/mutations_l5f.txt`). "Before" = the delivered
L5 board (CHECKPOINT 2), "after" = this board, both measured with the same l5fcheck code.

Scripts (in order): `l5f_prep.py` (rips, local cap moves, solid pads) → `l4_export.py` → `l5f_route.py` (hand copper
exact-checked with l4lib + router legs, group **L5F_ROUTE**) → `l5_write.py` → `l5f_tidy.py` (group **L5F_TIDY**) →
`l5f_board.py` (zones, outline) → `fill_zones.py` → `l5_silk.py` (moved here from `l5_run.sh`) → `render_routing.py l5`
→ `render_l5f.py`.

## 1. Buck input loops U4–U7 (MAJOR) — D-117 a

What changed (same template in all four cells, IC centre (xc, yc); TI SLVSDG1C §10.1/§10.2 p.13, Fig. 20: GND pour
runs under the DBV package from the GND pin to the input cap):
- 0.50 mm L1 GND strap from pin 2 east under the body (between FB pin 5 and VIN pin 4, 0.40 mm from each) to the
  100 nF input cap, whose GND pad sits at the strap height (C13/C14/C15 unchanged; C12 moved into that slot,
  (75.00, 35.67), 90°).
- 0.40 mm GND strap from the body centre south between SW pin 3 (0.33 mm) and pin 4 to the 10 µF input cap, moved
  inside its cell to just south of the IC and turned 180° (GND pad west): C9 (72.35, 19.64), C10 (72.35, 28.64),
  C7 (73.55, 37.64), C8 (72.35, 46.64). Local moves inside the cells as approved by D-H6; zones unchanged.
- A GND via under the body on the strap (xc + 0.05, yc), 0.52–0.53 mm from pin 2, plus the existing pin-2 via west of
  the pin; pin 2 and every input-cap GND pad connect solidly (no thermal spokes).
- VIN: pin 4 → 10 µF VIN pad straight south (0.60 mm) and pin 4 → 100 nF VIN pad straight east (0.50 mm), each with a
  VCC5V0_SYS plane via (pin 4 keeps its 2 vias ≤ 0.5 mm; the old under-body via was in the strap's path).
- 10 µF GND pads: 2 GND vias each (south; U5 west because of the VCC_3V3 run to TP2).
- EN pin 1 → via under the body north of the strap (xc − 0.05, yc − 0.95); the enable nets are re-routed (item 5).
- FB untouched; SW node untouched (pin 3 → inductor pin 1, 2.07 mm of 1.2 / 0.6 mm track).

| Cell | L1 GND path 10 µF GND pad → pin 2 (before → after) | L1 path 100 nF → pin 2 | pin 4 → cap VIN pad (centres) 10 µF / 100 nF | loop area pin4–capVIN–capGND–pin2 10 µF / 100 nF | GND vias ≤ 1 mm of pin 2 | pin 2 |
|---|---|---|---|---|---|---|
| U4 (0V9) | C7: no L1 path → **2.03 mm** | C12: 5.30 → **2.84 mm** | 1.71 / 1.51 mm | 3.19 / 2.54 mm² | 1 → **2** (0.34, 0.52 mm) | spokes → **solid** |
| U5 (1V8) | C8: 6.35 → **2.03 mm** | C13: 2.84 → **2.84 mm** | 1.71 / 1.51 mm | 3.19 / 2.54 mm² | 1 → **2** (0.34, 0.53 mm) | spokes → **solid** |
| U6 (3V3) | C9: no L1 path → **2.03 mm** | C14: no L1 path → **2.84 mm** | 1.71 / 1.51 mm | 3.19 / 2.54 mm² | 1 → **2** | spokes → **solid** |
| U7 (DDR) | C10: no L1 path → **2.03 mm** | C15: no L1 path → **2.84 mm** | 1.71 / 1.51 mm | 3.19 / 2.54 mm² | 1 → **2** | spokes → **solid** |

FB nets to SW copper (outside the IC courtyards): 2.79 mm min (≥ 2.0). Check: **L5F-buck** (geodesic over the L1 GND
copper union, 0.04 mm grid; zone connection; via count) — mutations `buck_strap`, `buck_spokes`, `buck_cap_moved`.
Note: layout.md §10's "C_IN ≤ 1 mm from VIN/GND pins" cannot hold for both pins of a SOT-23-5 whose VIN and GND are
on opposite sides; the new §10 line states the L1-path rule. Renders: `route_l5f_buck_u4/u5/u6/u7.png` (+ `_F_Cu`,
`_B_Cu`).

## 2. Via in pad with POFV — D-117 b

POFV ordered (supersedes D-67; layout.md §6.2 and the D-67 row updated). **L5F-vip** FAILs any via whose drill circle
or annular ring meets an SMD pad or its mask opening, or whose drill edge is < 0.10 mm from it, unless listed in
**`pcb/via_in_pad.csv`** (pad, net, x, y, via net, centre-to-opening, reason); listed rows that match nothing also
FAIL, so the list stays exact for the L6 fab notes. Searched: all 649 board vias + the 16 U9 EP thermal vias.

Before: 6 counted (centre-in-pad rule). After: **28 rows** = the 11 of D-H6 (C47.1, C58.1, C66.1, C69.1, FB2.2,
R33.2, C45.1, R27.1, F1.1, R27.2 (63.75, 46.98), R40.1 (10.14, 58.68)) + **TP16.1** (VCC3V3_SD test-pad via (24.93,
59.72), ring 0.04 mm into the pad — found by the new rule) + the 16 EP vias. The new L5F vias keep their centre ≥ 0.26
mm from every SMD pad (none added to the list). Mutations `vip_new`, `vip_stale`.

## 3. BOM / schematic values — D-117 c

| Part | Before | After | LCSC (already in the BOM) | Basis |
|---|---|---|---|---|
| C24 (C_OUT_U4) | 10 µF 10 V X5R 0603 C19702 | **22 µF 6.3 V X5R 0603** | C59461 (C27/C28) | TI SLVSDG1C Table 4 p.9: 2 × 22 µF for 0.6–1.2 V at 2.2 µH |
| C6 (C_PDT) | 680 nF 16 V X7R C107067 | **2.2 µF 16 V X5R 0603** | C23630 (C2) | LTC2954 p.9 CPDT = 1.56e-4 µF/ms × (tPDT − 1 ms); D-33 model: hard-off **8.07–22.4 s** (nominal 14.2 s), never before 8 s; 1.5 µF would give 5.8 s worst case |
| C71 ([LF] C38, nPOR) | 10 nF 50 V X7R C15195 | **100 nF 16 V X7R 0402** | C1525 | D-H6; τ = 1 kΩ × 100 nF = 100 µs |

Footprints unchanged (no pad moved). Edited: `tools/make_bom.py`, `tools/make_refmap.py` (BOM refs unchanged),
SKiDL comments (`schematic/button.py`, `soc.py`), `schematic/ref_connections.csv`; regenerated `bom.csv`, `refmap.csv`,
`schematic/out/*`; `power_rails.csv` (VDD_0V9 local C 22.1 µF), `power.md`, D-33. Checks: check_schematic **1694 pass /
0 fail**, check_bom **408 / 0**, check_power **84 / 0** (P8 now requires the earliest hard-off ≥ 8 s; P10 VDD_0V9: the
total 55.7 µF puts the upper effective-C corner 16 % above the 2 × 22 µF cell's +20 % bound — recorded DEV, owner
question). The board footprints carry the new values and LCSC fields from the regenerated netlist.

## 4. V-cut clearance (≥ 0.8 mm) — D-117 d, D-118 a

Every copper pour / plane outline (F, In1, In2, B GND) clipped to x 0.80–79.20 (was 0.40). Round 2: the J5 west
corridor (V-cut to the J5 pad edge at x 2.15) re-drawn by hand in `l5f_route.py` (each piece exact-checked against the
board; `l5f_prep.py` rips the old pieces), no part moved, lane order unchanged. **L5F-vcut** measures tracks, vias, pads
and zone fills on all four layers against the V-cut lines read from the V-CUT layer, with no exceptions (VCUT_DEV is
empty).

| | Before (L5) | Round 1 | After (round 2) |
|---|---|---|---|
| min board copper to a V-cut | 0.40 mm (pours) | 0.40 mm (3 lanes, DEV) | **0.800 mm** (pour edge); tracks ≥ 0.8002, vias ≥ 0.81 |
| HDR_PWM9 B.Cu run / via | x 0.663 (0.59 mm) / via (0.66, 53.02) 0.41 mm | same | run **x 0.8502** (0.80 mm); via **(1.06, 48.93)** 0.81 mm, in the J5.31/J5.33 row gap; F.Cu into J5.33 |
| HDR_SPI0_SCLK via / F.Cu run | (0.66, 22.22) 0.41 mm / x 0.663 | same | via **(1.06, 21.40)** 0.81 mm; run **x 0.8502** |
| HDR_SPI0_MOSI via / F.Cu run | (0.76, 21.44) 0.51 mm / x 1.087–1.138 | same | via **(1.30, 19.90)** 1.05 mm; run **x 1.1015**, passing between the HDR_SPI0_CS0 and SCLK vias |
| neighbours | — | — | HDR_PWM11 x 1.087 → 1.1015 (jog to 1.512 round the PWM9 via); HDR_GPIO1_B0 jog 1.663 → 1.764; HDR_GPIO1_B1 jog 1.928 → 2.016 (≥ 0.15 mm from the round J5 pads) |

Clearances in the corridor: lanes 0.10 mm, gaps ≥ 0.151 mm (DEFAULT class 0.15), KiCad DRC clean. The corridor is now
full: between the V-cut and the HDR_GPIO1_B1 via (1.553, 26.022) two lanes + two gaps leave 0.0035 mm. The rail
fiducials (JLC-mandated 3.85 mm from the panel edge) are at 0.65 mm on the rail side (INFO). Mutations `vcut_via`,
`vcut_pour`, `vcut_lane` (PWM9 back at x 0.663). Renders `route_l5f_vcut_west*.png`, `route_l5f_vcut_east*.png`.

## 5. PWR_EN / enable nets near L3 — D-117 e

U4_EN, U6_EN, VCC_DDR_1V8_EN and PWR_EN were removed and re-routed by the router with the inductor courtyards (+0.1 mm)
and 1.0 mm round the SW copper forbidden, and no via within 1.27 mm of an inductor pad; R21.2 / R20.2 drop to L4
through a via just south of the pad; the old U6_EN via in L3's courtyard is gone.

| | Before | After |
|---|---|---|
| EN / PWR_EN / PB nets to SW copper (SW tracks, SW pads, inductor pads; outside the IC courtyards) | −0.07 mm (VCC_DDR_1V8_EN B.Cu across L1); PWR_EN 0.38 mm from L3.1 | **1.01 mm** min |
| copper of these nets inside an inductor courtyard | 10 items (PWR_EN in L3, VCC_DDR_1V8_EN in L1, U6_EN via) | **0** |
| FB nets to SW copper | 2.79 mm | 2.79 mm |

Check **L5F-sw** (sampled every 0.05 mm, extends the SENSE check to EN/FB/PWR_EN/PB nets). Mutation `en_near_sw`.
Render `route_l5f_pwr_en_l3*.png`.

## 6. Silkscreen — D-117 i

| | Before | After |
|---|---|---|
| F.SilkS lines < 0.15 mm | 277 | **0** (507 stock-footprint lines set to 0.15 mm, then trimmed 0.15 mm from pads) |
| silk texts < 1.0 mm or stroke < 0.15 mm | 3 (PWR / STAT / ETH at 0.8 / 0.12) | **0**: LED labels 1.0 mm / 0.15 mm in one row above the LEDs (PWR x 59.51, STAT 63.20, ETH 66.67, y 1.30) |
| silk outside the board (J1) | 3 | **0**; DRC silk_edge_clearance 2 → 0 |

Check **L5F-silk** (plus the existing L5-silk pad clearance / bottom-part checks). Mutation `silk_thin`. Test-pad
labels: see §10 (round 2). Renders
`route_l5f_led_silk*.png`, `route_l5f_r62_silk*.png`, `renders/route_l5_silk.png`.

## 7. L4 hops of the USB / ETH pairs — D-117 f

In2 GND islands (zones `In2_GND_HOP_0..3`, priority 3 over the In2 power regions, 0.20 mm anti-pads, solid) under the
hop clusters: ETH TX (20.60–23.45, 27.40–32.35), USB_DM (36.70–39.55, 48.60–51.45), USBC/USBA_DM at y 57
(37.20–41.10, 56.25–58.75), USBC at J1 (47.15–51.75, 70.30–74.35). No power-plane via falls inside an island.

| | Before | After |
|---|---|---|
| L4 pair segments with In2 GND under every point (beyond 0.6 mm of a via) | 14 of 21 (USB_DM, ETH_TX ×4, USBA_DM, USBC_DP over VCC_3V3 or voids) | **21 of 21** |
| pair vias with a GND via ≤ 1.0 mm | 11 of 16 | 11 of 16; ETH_TXN (22.85, 31.10) 1.63 → **1.17 mm** (new via (21.68, 31.16)); the rest recorded |
| recorded (DEV D-117 f, no legal site ≤ 1.0 mm: the pair's own tracks / vias take them) | — | USBC_DM (38.35, 56.85) 1.20, USBC_DM (51.15, 71.00) 1.48, USBC_DP (47.75, 70.90) 1.67, USBC_DP (49.75, 71.12) 2.23, ETH_TXN 1.17 mm |

Round 2 (verifier minor): not changed, justified in D-118 b. A second search with the board model showed what takes
the sites: around the three J1 vias the receptacle's own F.Cu pad rows (0.25–0.30 mm pitch, y 71.65–72.95) and the
pair meanders, around the other two the pair's own tracks / vias. Moving a pair via 0.2–0.3 mm means re-routing an L4
critical pair (length, skew, 45-ohm sections). The In2 GND reference under every hop is in place and a GND via is within
2.23 mm of every hop via. The owner may still ask for the re-route (open question).

Check **L5F-hop** (In2 net under every L4 pair point reported; stitching distances FAIL above the recorded value).
Mutation `hop_island`. Renders `route_l5f_hop_eth*.png`, `route_l5f_hop_usb*.png`, `route_l5f_hop_usbc*.png`.

## 8. Clean-up — D-117 g

| | Before | After |
|---|---|---|
| VDD_0V9_BUCK into C29.1 / R17.1 | 0.80 mm into a 0.56 / 0.80 mm pad | branch L1.2 → R17.1 → C29.1 at **0.40 mm** (divider top + feed-forward, µA) |
| other wide tracks into 0402/0603 pads | C16.1 (0.80 into 0.56), C2.1 (1.00 into 0.90) | necked to 0.40 mm; **0** of 436 track ends too wide |
| wide copper overlapping a small pad from outside (round 2) | round 1: C16.1 0.13 mm² (0.425 mm neck), C2.1 0.017 mm² | **0** of 19 wide tracks near small pads overlap: C16.1 neck 0.496 mm, wide end 0.102 mm outside the pad; C2.1 neck 1.165 mm, 0.105 mm outside |
| DRC track_dangling | 42 (escape overshoot stubs) | **0** (51 stub ends trimmed back to the lane joint) |
| DRC via_dangling | 2 | **0**: the two vias (VCC_DDR (39.70, 34.03), VCC3V3_RTC (35.38, 41.65)) are the second vias of U9 supply-pin layer changes (layout.md §3 ≥ 2); they now carry an L4 link to their partner via instead of being removed (removal would leave one via) |
| DRC errors / unconnected | 0 / 0 | **0 / 0** |

Checks **L5F-neck** (end-point width, and since round 2 the polygon overlap of wide tracks with the pad),
**L5F-dangle**, and check_routing's escape "layer change: vias ≥ 2". Mutations `neck_wide`, `neck_overlap`, `dangle`. Render `route_l5f_u9_stubs*.png`, `route_l5f_buck_u4.png` (neck).

## 9. Outline and V-CUT layer — D-117 h, D-118 c

R 1 mm arcs at the four corners of the 80 × 80 board itself. Each corner is a routed notch in the rail, so the board
corner can be an arc while the V-cut runs straight (supersedes D-101's square corners). Round 2: the notch is
**1.5 × 1.5 mm** (was 1.0 × 1.0) and every air-side corner is R 0.5 mm. The path is: rail edge → wall at x −1.5 (81.5)
→ R 0.5 → floor at y 1.5 (78.5) → an R 0.5 arc that meets the R 1 board arc tangentially at (0, 1) on the V-cut line.
A 1.0 mm bit clears the whole board arc. The only material fillet left lies on the rail side and goes with the rail.
In round 1 the corner at (0, 1) was a sharp concave material corner (75 % material in a 0.05 mm circle), which a bit
cannot cut. JLC's router-bit size is still UNVERIFIED (ask at DFM, L6).
V-CUT = User.1 named "V-CUT", lines x = 0 / 80 over the full height; `kicad-cli pcb export gerbers -l User.1` writes
`*-V-CUT.gbr` (checked; L6 adds it to the fab set). Check **L5F-edge**: 4/4 corners, outline closed (32 items), layer
present and plotted, and (new) "routed outline cuttable by a 1.0 mm router bit" (0 concave corners, 0 air-side arcs
< R 0.5 at 32 end points). Mutations `corner_square`, `notch_sharp` (the round-1 shape). Renders
`route_l5f_corner_nw.png` and `route_l5f_corner_se.png` (Edge.Cuts black, V-CUT dashed), `route_l5f_corner_nw_F_Cu.png`.

## 10. Round-4 minors — D-117 j

- placement.csv zone column: TP18 → Z-USBA-PWR, TP23 / TP24 → Z-USB, R62 / R63 → BOARD (no zone); zones.csv fills
  recomputed (Z-SOC 50.0 %, Z-HDR 4.9 %, Z-USB 50.7 %, Z-USBA-PWR 13.3 %); tools/check_layout **1259 / 0 FAIL** (ring-2
  test pads moved out of Z-SOC accepted with their decision in the target column). Final-board zone check **L5F-zone**
  (25 recorded deviations, 0 unrecorded; mutation `zone_out`).
- check_escape: an unknown / non-numeric U9 pad is a FAIL line (KeyError guard; mutation `u9_pad_162`).
- R62 / R63 references beside their parts (R62 upright east of the pair, R63 turned 90° west).
- TP3, TP13, TP14, TP27, TP28, TP29: round 1 found no spot for "TP<n>". Round 2 (D-118 d) gives each one its **bare
  number** ("3", "13", "14", "27", "28", "29") on F.SilkS at 1.0 mm / 0.15 mm beside its own pad (≤ 2.0 mm, nearer to
  it than to any other labelled part; TP28 by a 0.05 mm fine search using the ink box). "TP<n>" + net stay on F.Fab.
  Side effect: Q3 and R27 references hidden, R7 now placed (83 hidden vs 82). Render `route_l5f_tp_silk*.png`.
- The 46.3° PB_INT_N piece (42.20, 41.15)–(44.81, 43.89) → 0.125 mm vertical + 45°; the same check found a 50.8° NPOR
  piece at C71.1 → 0.16 mm vertical + 45°. Check **L5F-geom** (0 off-angle L5 pieces ≥ 0.5 mm outside the U9
  neck-down zone; mutation `geom_30deg`).

## Results (final board, clean rebuild, round 2)

| Check | Result |
|---|---|
| Clean rebuild (`rebuild_all.sh`, from the netlist, 14 min 50 s) | runs through (exit 0); rebuilt board = development board (**0 of 4929** items differ: tracks / vias by net, layer, width and ends, footprints, pad nets and zone connections, texts, drawings, zones) |
| KiCad DRC (refilled, all severities) | **0 errors, 0 unconnected items**; warnings lib_footprint_mismatch 152 only; track_dangling 0, via_dangling 0, silk_edge_clearance 0 |
| `check_routing.py` final board (L3 + L4 + L5 + L5F) | **566 checks, 459 PASS, 69 DEV, 38 INFO, 0 FAIL** (round 1: 565 / 457 PASS / 70 DEV; the L5F-vcut DEV is gone, new PASS lines: neck overlap, router-bit corners) |
| L3 board / L4 board checks during the rebuild | 419 / 0 FAIL; 509 / 0 FAIL |
| `check_placement.py` | 339 checks, 277 PASS, 62 DEV, 0 FAIL |
| `tools/check_layout.py` | 1259 pass, 0 fail |
| schematic / BOM / power checks | not affected in round 2 (no schematic change); round 1: 1694 / 0, 408 / 0, 84 / 0 |
| Mutation self-test (`mutate_l5f.py`, `trial/mutations_l5f.txt`) | control 0 FAIL; **19 of 19 mutations caught** by the expected rule (buck ×3, vip ×2, vcut ×3 incl. new `vcut_lane`, sw, silk, hop, neck ×2 incl. new `neck_overlap`, dangle, edge ×2 incl. new `notch_sharp`, zone, geom, escape KeyError guard) |

DEV lines still open for the owner: L5F-hop (5 pair vias, D-117 f / D-118 b) and L5F-zone (25 recorded zone
deviations, decisions unchanged).

## Renders (`design/pcb/renders/`)

`route_l5f_<area>.png` = annotated plot (pads ref.pad / net, tracks, vias, fills, courtyards); `route_l5f_<area>_<layer>.png`
= kicad-cli SVG export of that layer (+ F.SilkS, Edge.Cuts) cropped. Areas: `buck_u4`, `buck_u5`, `buck_u6`, `buck_u7`,
`pwr_en_l3`, `vcut_west`, `vcut_east`, `hop_eth`, `hop_usb`, `hop_usbc`, `corner_nw`, `corner_se`, `led_silk`,
`r62_silk`, `tp_silk`, `u9_stubs`; plus the whole-board `route_l5_*.png`.
