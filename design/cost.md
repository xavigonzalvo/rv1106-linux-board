# Cost estimate: Phase 4, Rev A (owner decision D-H2: 2 assembled boards + 3 bare PCBs)


> **Phase 5 update (2026-10-29, D-72):** the schematic resolved the BOM's contingency lines: two duplicate 10 k ([LF] R21/R57 were already counted) removed, [LF] R52 kept as the VCC3V3_SD bleeder, the two contingency 100 nF became [LF] C7 (USB_DET_IN) and the pin-71 decoupler, and one 1 µF ([LF] C35, RTC_AVDD3V3) was added. Still 64 lines / 25 Extended types; **193 parts per board; `check_bom.py design` total $360.34** (was $360.35). Figures below are otherwise unchanged.

> **Phase 7 update (2026-10-29, D-84 round 2):** the board grew from 70 × 70 to **80 × 80 mm** (panel with rails 90 × 80 mm) so that every placement zone holds its KiCad courtyards at ≤ 55 % fill (layout.md §5.1). D-H2 allows a larger board when it makes the build simpler. The only cost line that changes is the PCB ESTIMATE: $45 → **$58** (scaled linearly with panel area, 45 × 7200/5600 = 57.86; an upper bound if JLC prices by area, UNVERIFIED until the live quote). Packing changes by < $0.01. **`check_bom.py design` total $373.34** (margin $6.66 to the $380 cap). The 70 × 70 figure is still available as the what-if `--format single70` ($360.34).

**Command:** `design/.venv/bin/python -I design/tools/check_bom.py design`

With no options, the tool checks the gate TP-D4 as amended by D-H2 (PLAN.md Phase 4):
- 2 assembled boards out of 5 PCBs ordered;
- total ≤ **$380**;
- RV1106G3 JLCPCB stock ≥ boards + 2; every other part ≥ 100;
- JLCPCB Standard PCBA (D-61), on an 80 × 80 mm board (D-84 round 2) with 2 × 5 mm edge rails (D-61, D-67), ENIG (D-62).

Any other option prints "WHAT-IF SCENARIO, NOT THE D-H2 GATE" (D-66).

The tool recomputes every line cost from the cached LCSC price ladders for the number of boards assembled (D-60).
bom.csv is costed for the same 2 boards, and check B6 cross-checks the two: $113.81 vs $113.80, a rounding difference.

**Data sources, fetched 2026-10-29:**
- Prices and stock: LCSC product-detail API (`https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=<C#>`) and the
  JLCPCB part pages (`https://jlcpcb.com/partdetail/<C#>`), cached in `refs/lcsc-api-2026-10-29/` and
  `refs/jlcpcb-partdetail-2026-10-29/`.
- Live re-fetch by the executor at 09:24 UTC of the parts that matter for this round: `refs/executor-p4dh2-live-2026-10-29/`.
- PCBA fees: `refs/jlcpcb-assembly-price-2026-10-28/` (https://jlcpcb.com/help/article/pcb-assembly-price, "Last updated on
  Oct 22, 2026").
- Assembly limits: `refs/jlcpcb-assembly-capabilities-2026-10-28/` (https://jlcpcb.com/capabilities/pcb-assembly-capabilities,
  table "PCB Assembly Technical Capabilities").

## Gate TP-D4 result: **PASS** (477 pass, 0 fail; round 2 after verifier findings, D-68 to D-71)

| Check (tools/check_bom.py) | Result |
|---|---|
| B1: every BOM line has an LCSC number that exists and names the same MPN | 64/64 |
| B2: JLCPCB stock ≥ 100; **RV1106G3 only: ≥ boards + 2 = 4** (D-H2) | 64/64. **RV1106G3 C5328706: JLC 23, LCSC 22** (live re-fetch 09:24 UTC). The owner rechecks this on the order day. |
| B3a: the footprint package token matches the LCSC package | 64/64 |
| B3b: the footprint is an exact KiCad library name, or a custom `board:` footprint with a cited drawing | 64/64 |
| B3c: the physical pad count equals the BOM pad count (re-counted from the cached .kicad_mod) | 64/64 |
| B3d: the BOM pad count equals the JLCPCB solder-joint count (jlcparts mirror) | 63/63. The RV1106G3 is not in the mirror; its 129 pads come from [DS] p.14. |
| B4: the Basic/Extended column matches the JLCPCB library type; only Basic/Extended accepted, a truncated or unknown value fails (D-71) | 64/64 |
| B5: rules carried from Phases 3–4 are present (no 0R chip in the VDD_0V9/VDD_ARM path: [LF] R32 → copper NT_ARM, U4 link → solder jumper JP_MEAS_0V9 (D-68); 4× TLV62569, LTC2954-1 + Q_EN, Q_KILL, bleeders, F1 -300, SY6280 10 µF, 142 µF USB-A) | 10/10 |
| B6: the bom.csv line costs equal the recomputed parts total | pass ($113.81 vs $113.80) |
| **B6: 2 assembled + 3 bare, total ≤ $380** | **pass: $373.34** (margin $6.66; Phase 7 board 80 × 80 mm) |
| B7a: every fine-pitch part meets Standard's 0.35 mm minimum IC pin spacing | 4/4. The SoC is at 0.35 mm, exactly the minimum, which is why Standard PCBA and ENIG were chosen. |
| B7b: cited peak reflow rating ≥ 245 °C (Standard 240 ± 5 °C) | 7/7. The other 53 reflowed lines have no cited rating; they are listed as INFO / UNVERIFIED. |
| B7c: the board meets the Standard minimum of 70 × 70 mm | pass: 80 × 80 mm board, 80 × 90 mm with rails |
| B8: refmap.csv matches the generator; every [LF] name is unique; every [LF] SoC capacitor cited in power_rails.csv has an entry (D-65); copper entries JP_MEAS_0V9/NT_ARM present; R_MEAS_1V8/3V3/DDR named (D-68, D-69) | 6/6 |

Mutation runs, made to show that the gate can fail:
- `--soc-stock-rule boards+30` fails B2.
- `--cost-limit 355` fails B6.
- `--service econ` fails B7a (SoC pitch) and B7b (polymer capacitor).
- `--boards 5` gives $493.89 and fails B6.
- A bom.csv with Basic/Extended = UNKNOWN for C52923 fails B4 (476/1), D-71.
- `make_bom.py -h` prints help; a non-existent or non-design directory is refused (D-70).

## 1. Cost model (Rev A: 5 PCBs, 2 assembled with Standard PCBA, single-side, 80 × 80 mm, ENIG)

Phase 7 (D-84 round 2): only the PCB line below changes ($45 → $58) and the total becomes **$373.34**; the assembly
lines are those of the 70 × 70 run (packing + $0.0005).

| Item | Basis | USD |
|---|---|---|
| **Parts** (64 lines, 194 parts per board) | LCSC ladder price at the order quantity: 2 × qty per board, + 10 % (min 5) attrition on chip passives, rounded up to the LCSC minimum buy | **113.80** |
|  · RV1106G3 (C5328706) | 2 × $25.39 | 50.78 |
|  · LTC2954CTS8-1 (C683782) | 2 × $6.69 | 13.38 |
|  · W25N01KVZEIR (C22472329) | 2 × $6.41 | 12.81 |
|  · 22 µF 25 V 0805 (C45783), minimum buy 20 | 20 × $0.193 | 3.87 |
|  · HR911105A RJ45 (C12074) | 2 × $1.74 | 3.48 |
|  · the other 59 lines | mostly LCSC minimum-buy quantities of Basic passives | 29.49 |
| Setup | Standard, single-side | 25.56 |
| Stencil | Standard, single-side assembly | 8.21 |
| SMT joints | 1168 joints × $0.0016 | 1.87 |
| Manual (THT) joints + hand-soldering labour | 134 joints × $0.0164 + $3.58 per order | 5.78 |
| **Feeder loading** | **$1.53 × 64 unique parts.** Standard charges every Basic and Extended part; D-64 removed 2 types. | **97.92** |
| X-ray (QFN-128, WSON-8, UQFN-10) | 6 pcs × $1.64 (1–10 pcs rate) | 9.84 |
| Fixture (standard rigid PCB) | 1–29 pcs: 2 fixtures. Whether it applies to this order is **UNVERIFIED**; it is charged to be safe. | 16.42 |
| Packing | $0.50 + $0.00003 × PCB area | 0.50 |
| Confirm parts placement | | 0.45 |
| Handling fee | **$0.00, now computed (D-66).** The rule applies only "when both Economic PCBA and Standard PCBA are available for the same order" and Std − Econ < $14.93. Economic cannot place the 0.35 mm SoC, and Std − Econ would be $62.15 in any case. | 0.00 |
| **Assembly subtotal** | | **166.55** |
| PCB: 5 pcs, 4-layer JLC04161H-7628, 1.6 mm, **80 × 80 mm** + rails (panel 90 × 80), **ENIG** | **ESTIMATE, UNVERIFIED.** No live quote: quoting needs the online form, which this team does not submit. The owner gets the live quote at order time (D-H2). Phase 7: the 70 × 70 estimate ($45) scaled with panel area. | 58.00 |
| Shipping | **ESTIMATE, UNVERIFIED.** Cheapest tracked courier, ≈ 0.3–0.4 kg, to Europe. Excludes import VAT and duty. | 35.00 |
| **Total, Rev A** | `check_bom.py design` | **373.34** |

**What could still move the number**, all to be confirmed on the live quote:
- The two estimates (PCB and shipping, $93 together). If JLC prices 4-layer boards up to 100 × 100 mm in one band, the
  80 × 80 board costs about the same as 70 × 70 and the total falls back toward $360 (UNVERIFIED).
- The fixture fee ($16.42, possibly not charged).
- "Pre-reflow Soldering" at $0.016/joint, which is listed on the price page without explanation and not counted. If it
  were charged on the 134 THT joints it would add $2.14; on every joint, $21. The second case would take the total to about
  $394 on the 80 × 80 estimate (was $381 at 70 × 70), over the cap: if the live quote shows it, ask JLC what it is
  before paying.
- Stencil and fixture storage ($4.93 each). These are optional and not counted.

The large-size surcharge and the single-board surcharge do not apply: the area is far below 650 cm², and the assembly fee is far
above $0.48 per board.

## 2. Cost reductions in this BOM

| Change | Saving (Rev A) | Decision |
|---|---|---|
| Rev A = 2 assembled + 3 bare instead of 5 assembled | $133.54 ($493.89 → $360.35) | D-H2 |
| 0R 0402 merged onto the 0R 0603 line; status and ETH LEDs use the power-LED part | 2 feeders, $3.06 | D-64 |
| SPI NAND 1 Gbit instead of 2 Gbit | ≈ $10 | D-52 |
| LTC2954-1 + 2N7002 instead of LTC2954-2 (which also had only 50 in stock) | ≈ $3.4 (2 × $2.45 − one feeder $1.53) | D-51 |
| SY6280 VIN 10 µF reuses the C96446 line | one feeder, $1.53 | D-57 |
| VDD_0V9 measurement link and [LF] R32 as copper instead of 0R chips (D-68) | ≈ $0.01 (2 parts, 8 joints per 2 boards) | D-68 |
| Single 70 × 70 mm board instead of a 1 × 2 panel | $5 (`--format panel1x2`: $365.35) | D-61 |

**Extended types (25) were not reduced further** (D-64a):
- The jlcparts mirror has no Basic part with the same value and package for any remaining Extended passive (6.8 pF, 127 k,
  442 k, 6.04 k, 240 R, 150 nF, 680 nF).
- It also has no Basic 24 MHz crystal, no 5 V unidirectional TVS and no pin header.
- The rest are ICs and connectors chosen in Phases 1–4.
- Under Standard PCBA a Basic part pays the same $1.53 feeder fee as an Extended one. Only removing a whole part type saves
  money.

Further merges were rejected because each one changes an analysed value: 10 µF tolerance (check_power P10), buck output
capacitance (D-47), RC time constants, I²C pull-ups and bleeders.

## 3. Scenarios (same BOM; what-if runs, not the gate)

| Scenario | Total | Command |
|---|---|---|
| **Rev A (D-H2): 5 PCBs, 2 assembled, 80 × 80 mm** | **$373.34** | `check_bom.py design` |
| Same on the round-1 70 × 70 mm outline | $360.34 | `--format single70` (not buildable: the zones do not fit, layout.md §5.1) |
| Same, as 1 × 2 panels of 60 × 50 mm | $365.35 | `--format panel1x2` (not chosen: needs depanelling and a smaller layout) |
| 5 assembled boards | $493.89 | `--boards 5` (prints the WHAT-IF banner and fails B6, as intended) |

**Budget context:** PLAN.md allows < $500 for two revisions. Rev A at about $373 (Phase 7, 80 × 80 mm) leaves about $127 for Rev B. A Rev B
of the same kind would cost about the same as Rev A, so the two-revision total would be about $720 unless Rev B
re-uses the 3 bare PCBs (hand-assembled) or the prices drop. This is reported for the owner; it does not change the
D-H2 gate.

## 4. What the owner does at order time (H2)
1. **Recheck the RV1106G3 stock** (C5328706) on jlcpcb.com. The rule is ≥ 4 (2 boards + 2); it was 23 today. If it is
   below 4, do not order. Wait for a restock, or pre-order the part into the JLCPCB parts library (a purchase the owner
   makes, not the agents).
2. **Get the live quote** with these settings:
   - 5 PCBs, 4-layer JLC04161H-7628, 1.6 mm, ENIG, 80 × 80 mm board, 90 × 80 mm with edge rails and fiducials (D-67, D-84);
   - Standard PCBA, top side, 2 boards assembled.

   Confirm that the total stays ≤ $380, and check whether the fixture fee and the pre-reflow fee are charged.
3. The RV1106G3 is **MSL3** ([DS] r1.8 p.18). How JLCPCB stores and bakes MSL3 parts is UNVERIFIED; ask on the order if
   in doubt.

## 5. Notes on prices and assembly
- Unit prices come from the LCSC ladder at the order quantity. JLCPCB's own ladder for C5328706, C22472329 and C683782
  matches LCSC to within 1 %.
- Basic passives are costed at the LCSC minimum buy (often 100 pcs), which overstates their cost slightly.
- Joint counts are physical pads (B3c), including the exposed pads of the QFN-128 and WSON-8. The USB-C has 12 SMD + 4 THT
  shell pads.
- Reflow: Standard reflows at 240 ± 5 °C. The 120 µF polymer capacitor (C_USBA_BULK [C34]) is rated 250 °C for ≤ 2 cycles
  (Lelon p.15, D-58). The board is single-sided, so it goes through reflow once.
- Test points are bare pads with no part. DNP footprints are not costed (list in `tools/make_bom.py`, `DNP`).
- Designators: bom.csv refs are assigned by the generator. Functional and [LF] names map to them in `refmap.csv`
  (D-63, D-65). Never write a bare [LF] designator; write "[LF] X" or "NAME [bomref]", e.g. "C_USBA_IN [C10]", "C65 [C32]",
  "J_RJ45 [J3]". The `lf_name_collision` column lists the 66 [LF] numbers that are also the bom.csv ref of a different part.
