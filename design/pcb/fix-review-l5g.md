# L5G — re-review fixes (owner decision D-H7 "Yes, fix and accept"), gate TP-L5G

Board `design/pcb/rv1106-reva.kicad_pcb`. Coordinates are board mm (page minus 50, 50). Decisions D-119..D-127; round 2 (verifier round-1 findings) D-128..D-131.
Scripts (run by `scripts/l5g_run.sh`, called by `rebuild_all.sh` after `l5f_run.sh`): `l5g_fix.py` (copper, group
L5G_FIX) -> `fill_zones.py` -> `l5g_silk.py` (labels) -> renders (`render_routing.py l5`, `render_l5f.py`,
`render_l5g.py`). Checks: `scripts/l5gcheck.py` (called by `check_routing.py`), self-test `scripts/mutate_l5g.py`
(`trial/mutations_l5g.txt`).

## Summary of the checks

| Check | Result |
|---|---|
| KiCad DRC (kicad-cli, all severities, zones refilled) | 0 errors, 0 unconnected, 0 track/via dangling; warnings 152 lib_footprint_mismatch (all on purpose; U9 now matches its variant, D-129), 11 lib_footprint_issues (unchanged) |
| `check_routing.py` (final board; L3 + L4 + L5 + L5F + L5G checks) | 601 checks, 483 PASS, 68 DEV, 50 INFO, **0 FAIL** (round 1: 599 / 71 DEV; the 3 D-122 DEV lines are gone) |
| Clean rebuild (round 2) | `rebuild_all.sh` on a scratch copy of the tree with every .kicad_pcb deleted: exit 0, 23.4 min; rebuilt board = delivered board (0 of 6857 compared items differ: tracks, vias, footprints + lib ids, pads, fields, drawings, zones, via protection); via_in_pad.csv identical; every L5G check_routing line byte-identical on both boards; L3 board 419 / 0 FAIL, L4 board 509 / 0 FAIL, check_placement 339 / 0 FAIL |
| Mutation suites | `mutate_l5g.py` **18 of 18** caught (12 + rtc_channel, rtc_pair_long, silk_margin, silk_tp3_band, u9_lib; rtc_close re-aimed), control 0 FAIL; `mutate_l5f.py` on the round-2 board 19 of 19 caught, control 0 FAIL |
| Footprints | `check_footprints.py` 232 checks, 0 failed (incl. the U9 `_EPboardvias` variant) |

## Round 2 — verifier round-1 findings

| Finding | Fix | Guard |
|---|---|---|
| (major, xtal) RTC_XOUT–SDMMC_D2 0.321 mm in the R48 / C58 channel; XIN–XOUT 2.2 mm < 0.5 mm | C58 0.176 mm E / 0.25 mm N (recorded local move, owner to confirm), channel re-drawn: XOUT–D2 **>= 0.500 mm everywhere**, XIN–XOUT run **1.88 mm** (D-128) | L5G-rtc FAIL lines without exemption; mutations rtc_close / rtc_channel / rtc_pair_long |
| (minor) side-run lengths depended on the track order | side_runs chains samples along the net geometry; L5G-runs FAIL line compares against the reversed track list (0 of 5 differ); L5G lines identical on delivered and rebuilt boards (D-131) | L5G-runs |
| (minor, pmu) "3" between TP3 and TP14 | test-pad-row band rule; no spot above TP3, so it is printed "TP3" 0.44 mm below TP3 (D-130) | L5G-silk; mutation silk_tp3_band |
| (minor) 0.05 mm silk margin | margin 0.20 mm; smallest now 0.21 mm; hidden references 14 -> 19 (D-130) | L5G-silk; mutation silk_margin |
| (minor, soc) U9 library mismatch | board.pretty variant `_EPboardvias`, U9 points at it; 152 mismatch warnings (D-129) | L5G-ep "U9 footprint = variant"; mutation u9_lib |

## 1. U9 EP vias for POFV (major) — D-119

| | Before (L5F) | After (L5G) |
|---|---|---|
| EP via holes | 16 drilled footprint pads "129" (0.3 / 0.5) | 16 GND board vias 0.5 / 0.3 at the same centres (x 32.20-36.80, y 34.20-38.80); U9 has 0 drilled pads |
| Excellon (kicad-cli `pcb export drill`) | `T2C0.300` ComponentDrill 16 holes + `T1C0.300` ViaDrill 649 | no 0.3 mm ComponentDrill; `T1C0.300 Plated,PTH,ViaDrill` **670** holes = 670 board vias (649 + 16 EP + 3 hop + 2 Q1) |
| Via protection | none set | board setup `(filling yes) (capping yes)` = IPC-4761 type VII |
| Paste windows vs EP via holes | 0.175 mm | 0.175 mm (hole edge), 0.075 mm (ring); windowpane unchanged |

Round 2 (D-129): U9 now uses the board.pretty variant `RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm_EPboardvias` (same land
pattern, no drilled pads, written by make_footprints.py, checked by check_footprints.py), so the U9 library mismatch is
gone (DRC warnings 152 lib_footprint_mismatch, all on purpose) and "update footprints" cannot restore the drilled pads.
Guard: L5G-ep (6 lines: drilled pads / 16 board vias in the EP; U9 = the variant with equal pads; filling + capping;
paste gap >= 0.175; no 0.3 mm ComponentDrill; ViaDrill holes = vias). Mutation `u9_lib` added. check_routing "EP 129" counts both kinds. via_in_pad.csv: 28 rows, the 16 EP
rows now say "board via". Mutations `ep_via_gone`, `ep_no_fill`. Render `renders/route_l5g_ep_vias*.png`.

## 2. Silk labels next to the wrong part — D-120

Rule (new, FAIL): ink box nearer its own copper (pin marker: its own pad) than ANY other part's copper by >= **0.20 mm**
(round 2, D-130; round 1 used 0.05), and within 2.0 mm (3.0 mm for parts > 5 mm); and (round 2) a bare-number label of
an upper-row test pad may not sit in the band between its row and a facing test-pad row below.

**Round 2 result (delivered):** 0 of 143 visible labels break the rule, smallest margin 0.21 mm (was 0.08). "3" (TP3)
had no spot above TP3 (1.07 mm free for a 1.15 mm glyph between the C8 and TP3 mask clearances) and is printed **"TP3"**
0.44 mm below TP3. 71 labels moved, 2 moved to a larger margin, **19 references hidden** (kept on F.Fab): U9 L3 U5 U6
U7 C28 R17 C70 R18 R19 R22 R42 R44 R46 R51 R67 C22 C48 C72 (round 1: 14; C28 R17 R44 C22 C48 C72 new, R45 placed
again); 96 references hidden on silk in all. Mutations `silk_margin`, `silk_tp3_band` added. The round-1 table below
is kept for the before numbers.

| Label | Before (re-review / own measure) | After |
|---|---|---|
| all visible labels | 80 of 166 break the rule | **0 of 148**; smallest margin 0.08 mm |
| "U5" | 4.03 mm from U5, 0.63 from C7 | hidden (kept on F.Fab): no spot meets the rule |
| "3" (TP3) | between TP3 and TP14 (margin 0.06) | 0.45 mm from TP3, nearest other copper TP5 1.21 mm |
| "13" | 2.43 mm from TP13, 0.49 from R27 | 0.42 mm from TP13 |
| "27" / "29" | nearer R11.2 / R7.2 | 0.41 / 0.39 mm from TP27 / TP29 |
| JP1 "B" | nearer JP1.2 | 0.40 mm from JP1.1 (buck side) |
| R55 / R17 | 3.9 / 3.8 mm | 0.22 / 0.16 mm from their own pads |
| "J4" | 0.73 mm from J2's pads | 0.19 mm from J4 |
| R43 / C28 | ~3 mm | 0.21 / 0.16 mm |
| R51 / R19 | ~3 mm | hidden (no spot) |
| TH2 / TH3 / TH4 texts on the board | printed at (2.15, 70), (77.85, 10), (78.5, 70) | hidden |

63 labels moved, 13 more moved from < 0.25 mm to >= 0.25 mm margin, 14 references hidden (U9 L3 U5 U6 U7 C70 R18 R19
R22 R42 R45 R46 R51 R67; references hidden on silk now 91, kept on F.Fab for the assembly drawing), 0 board labels moved
to F.Fab. Guard: L5G-silk (rule line + TH line + hidden count INFO). Mutations `silk_tp3_tp14`, `silk_u5_c7`,
`th_text`. Renders `route_l5g_silk_{pmu,soc,south,north,east}.png` (green box = beside its own part, dotted link to the
owner) and the fixed `route_l5f_tp_silk.png`.

## 3. SD clock crosstalk — D-121

| | Before | After |
|---|---|---|
| SDMMC_CLK_SD to D0 | 0.21 mm edge gap over 24.4 mm | **0.305 mm** (15.2 + 6.7 mm runs) |
| SDMMC_CLK_SD to CMD | 0.21 mm over 21.6 mm | **0.305 mm** |
| runs < 0.30 mm | — | only SoC-side SDMMC_CLK in the pin escape: CMD 1.17 mm, D0 0.66 mm at 0.25 mm (< 2 mm) |
| lengths (CLK = SDMMC_CLK + SDMMC_CLK_SD) | CLK 32.62, D0 34.05, D1 33.61, D2 32.82, D3 32.97, CMD 33.05 | CLK 32.52, D0 34.05 (+1.53), D1 33.61 (+1.09), D2 32.62 (+0.10), D3 32.80 (+0.28), CMD 32.92 (+0.39) — all <= 40, within ±5 |

How: CLK_SD leaves R48.2 at x 33.71; the CLK horizontal/diagonal moves 0.095 mm and CMD / D3 / D2 0.19 mm south-east,
with staggered 45° jogs below R48 (D1 / D0 stay: SDMMC_DET 0.265 mm north of D1). One GND stitching via moved 0.14 mm.
Guard: L5G-sd (FAIL for a run > 2 mm at < 0.30 mm to any SDMMC_* / FSPI_* track; lengths line). Mutation
`sd_clk_close`. Render `route_l5g_sd_rtc.png`.

## 4. RTC crystal — D-122, round 2 D-128

| | Before (L5F) | Round 1 (D-122) | Round 2 (D-128, delivered) |
|---|---|---|---|
| RTC_XOUT – SDMMC_D2 | 0.32 mm over 5.9 mm | >= 0.518 below y 47; 2.46 mm at >= 0.323 in the R48 / C58 channel (DEV) | **>= 0.500 mm everywhere, pin escape included** |
| RTC_XIN / XOUT – any other signal track (outside the escape) | — | 0 runs outside the channel | **0 runs < 0.5 mm, no exemption** (nearest: D2 0.500, AVDD1V8_USB 0.551) |
| RTC_XIN – RTC_XOUT, run < 0.5 mm outside the escape | 0.25 mm over 7.6 mm | 2.16-2.21 mm at >= 0.293 (DEV) | **1.88 mm** at >= 0.300 mm (limit 2.0), then >= 0.505 |

How (round 2): C58 moved **0.176 mm east and 0.25 mm north** ((36.71, 45.19) -> (36.886, 44.94); east is limited by
USB_DM, 0.1525 mm from C58.2 with class 0.15); its C58.1 in-pad via follows with a 45° piece on the L4 run to R33.2, and
its GND via moved from the dog-bone site into the C58.2 pad (POFV, via_in_pad.csv 29 rows). The channel is re-drawn from
the pin row: CMD / D3 / D2 at x 34.39 / 34.745 / 35.101 (CMD 0.165 mm from R48, was 0.147), XOUT at 35.751, XIN at
36.201 (0.30 mm from XOUT and from C58), XIN leaves at y 45.87 to x 36.41. This is a placement change: the L5G brief froze
placement except tiny via / label moves; it uses the D-H5 allowance (small local moves for routing, recorded) and is
listed for the owner to confirm (D-128). Guard: L5G-rtc (FAIL for any run < 0.5 mm outside the escape, FAIL for
XOUT–D2 < 0.5 mm anywhere, FAIL for an XIN–XOUT run > 2.0 mm); L5G-runs (run sets independent of the track order,
D-131). Mutations `rtc_close`, `rtc_channel`, `rtc_pair_long`. Renders `route_l5g_rtc.png`, `route_l5g_rtc_b*.png`.

## 5. J5.2 5 V link — D-123

Before: B.Cu 1.0 mm link (5.30, 10.36)-(5.30, 10.86), 0.105 mm into J5.4 (0.44 mm neck). After: (5.54, 9.56)-(5.54,
12.10), pad centre to pad centre. Guard: L5G-tht (power-net track ends on THT pads at the centre or overlapping >= half
the width; smallest overlap / width now 0.61). Mutation `tht_short`. Render `route_l5g_j5_link*.png`.

## 6. J1 shell vias — D-124

Before: hole edge to shell slot 0.403 mm at (45.65, 71.96) / (53.35, 71.96). After: vias at (45.685, 71.899) /
(53.315, 71.899), stubs follow, **0.472 mm**. Guard: L5G-hole (every via hole >= 0.45 mm from every PTH / NPTH / slot
hole; board minimum 0.472 mm). Mutation `hole_close`. Render `route_l5g_j1_vias*.png`.

## 7. In2 GND hop islands — D-125

Before: HOP_3 1 via (and, found by the new check, HOP_1 and HOP_2 1 via each). After: HOP_0..3 = 2 / 2 / 2 / 2
(new vias (50.75, 74.10), (37.30, 50.80), (37.65, 58.20)). Guard: L5G-hop. Mutation `hop_one`. Renders
`route_l5g_j1_vias_In2_Cu.png`, `route_l5g_hop_usb*.png`.

## 8. Q1 drain — D-126

Before: 3 VCC5V0_SYS vias. After: 5 ((60.50, 65.10) and (59.25, 66.30) added, 0.5 mm stubs to Q1.3). Guard: L5G-q1
(>= 4 within 1.0 mm of the pad). Mutation `q1_three`. Render `route_l5g_q1*.png`.

## 9. USB / ETH pair report — D-127

| Pair | Length P / N (mm) | Net skew | Off the target gap | Longest uncoupled |
|---|---|---|---|---|
| USBC_DP/DM | 32.04 / 32.20 | -0.15 | 17.4 of 32.0 mm (0.14-0.16) | 12.69 |
| USBA_DP/DM | 13.76 / 14.56 | -0.80 | 9.0 of 13.8 | 8.16 |
| USB_DP/DM (SoC-U11) | 12.03 / 12.65 | -0.62 | 4.9 of 12.0 | 2.93 |
| ETH_TXP/N | 16.01 / 16.30 | -0.29 | 12.4 of 16.0 (0.19-0.21) | 10.82 |
| ETH_RXP/N | 18.43 / 19.02 | -0.59 | 9.5 of 18.4 | 6.39 |
| ETH_TXP_J/N_J (magnetics side) | 5.95 / 5.95 | 0.00 | 6.0 of 6.0 (fully uncoupled) | 5.95 |
| ETH_RXP_J/N_J (magnetics side) | 8.85 / 8.25 | +0.59 | 8.8 of 8.8 (fully uncoupled) | 8.85 |

End-to-end P/N skew (FAIL-capable, limit 1.27 mm): ETH TX -0.29, RX +0.00 (net + _J); USB pad to pad SoC -> J4 -1.11,
SoC -> J1 A / B -0.61 mm. The reviewer's SoC -> USB-A 1.42 mm is the net-total figure (counts branch copper), reported
as INFO. Pairs not re-routed (D-H7 accepts the coupling). Guard: L5G-pair; mutation `pair_skew`.

## 10. Docs and renders — D-127

`route_l5f_tp_silk.png` (and the other l5f silk plots) now draw the labels; the `_F_SilkS.png` crops show F.Mask instead
of F.Fab text. New `route_l5g_*.png`: ep_vias, sd_rtc, rtc, j5_link, j1_vias, hop_usb, q1, silk_pmu / soc / south /
north / east. testpoints.md (role table + TP7 row, τ = 100 µs) and bringup.md step 5 name the nPOR cap **C_NPOR [C71]**
(Luckfox C38).
