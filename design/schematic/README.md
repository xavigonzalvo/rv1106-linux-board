# Schematic (Phase 5): SKiDL source and KiCad netlist, Rev A

The whole board is described in Python with **SKiDL 3.0.0**, installed in `design/.venv`. Running it writes a KiCad
netlist. There is no drawn schematic. The netlist is the hand-off to KiCad layout in phase H1.

## Run

```
design/.venv/bin/python design/schematic/board.py                  # build, SKiDL ERC, write out/board.net
design/.venv/bin/python -I design/schematic/check_schematic.py     # gate TP-D5 self-check (VERBOSE=1 lists every pass)
```

Last run (2026-10-29, after Phase 6 / D-77: 11 test pads added, TP8/TP12 swapped):

| Step | Result |
|---|---|
| `board.py` | 226 parts (193 BOM parts + 33 copper-only: TP1–TP31, JP1, NT1), 135 nets |
| SKiDL ERC | "No errors or warnings found" |
| `check_schematic.py` | **1691 pass, 0 fail** (Phase 5: 1622) |

Neither script uses the network. KiCad itself is not installed here and is not needed.

## Files

| File | Content | Blocks (architecture.md ids) |
|---|---|---|
| `lib.py` | Symbol pin tables, each with its cited pin-out source (`KIND`). Parts are created by functional name; the ref, value, footprint, LCSC number and MPN come from `bom.csv` / `refmap.csv`. Net registry. | — |
| `power.py` | USB-C sink, protection, the four TLV62569 bucks, enable chain, bleeders, sub-rails, RTC supply, SD-card switch, USB-A switch | usbc, prot, pmu |
| `button.py` | LTC2954-1 on/off controller, Q_EN / Q_PWR / Q_KILL, POWER button; RESET and MASKROM buttons, 3 LEDs | onoff, ui |
| `soc.py` | RV1106G3, wired pin-for-pin from `pinmap.csv`; decoupling table (one capacitor or more per supply pin); nPOR, DRAM_ZQ, ETH_EXTR, SARADC parts | soc |
| `clocks.py` | 24 MHz crystal with 22 R / 1 M / 2 × 18 pF; 32.768 kHz crystal | xtal |
| `storage.py` | SPI NAND (with the D-25 CS link) and microSD | nand, sd |
| `ethernet.py` | HR911105A, 4 × 0 R links, centre-tap capacitors | eth |
| `usb.py` | TS3USB221A mux, USB-A jack, USB-A ESD, 120 µF bulk | usb |
| `expansion.py` | 2×20 header (positions read from `pinmap.csv`) and I²C pull-ups | gpio |
| `debug.py` | 3-pin UART header with 1 k series resistors; test pads TP1–TP31 (list and expected values: `design/testpoints.md`) | uart (+ test points) |
| `board.py` | Top level. Calls every block, runs ERC, writes `out/` | — |
| `ref_connections.csv` | 273 **hand-written** expected connections, each citing [LF], power.md, a datasheet page or a D-xx decision. They are checked against the netlist; they are not generated from the code. | all |
| `check_schematic.py` | Gate check. It parses `out/board.net` with its own parser. | — |
| `out/board.net` | **KiCad netlist** (import into the PCB editor) | — |
| `out/parts.csv`, `out/nets.csv`, `out/pins.csv` | Flat listings for review: every part with its functional name, [LF] ref and `place_near`; every net with its nodes; every pin with its net or NC | — |
| `out/erc.txt`, `out/board.erc`, `out/board.log` | SKiDL ERC report and generator log | — |

The netlist carries these fields on every part:

- `LCSC`, `MPN`
- `Functional`: the name used in power.md and decisions.md
- `LF_ref`: the Luckfox designator
- `Block`
- `place_near`: the placement hint Phase 7 uses for decouplers and series parts
- `pinout_source`: the citation for the pin numbering

Copper-only parts (TP*, JP1, NT1) carry KiCad's `exclude_from_bom` property. Fitted parts carry neither `dnp` nor
`exclude_from_bom`. SKiDL writes those fields as KiCad boolean properties, and the property counts as TRUE whenever it is
present, whatever its value.

## Gate TP-D5 self-check (what `check_schematic.py` proves)

| Gate clause | Check | Result |
|---|---|---|
| Script runs | `board.py` exits 0 and writes the netlist; S1: every net is named, there are no single-node nets, and every ref is prefix + number | pass |
| SKiDL ERC clean, or every warning justified | S8: `erc.txt` reads "No errors or warnings found". The generator log has 6 warnings; all are on the justified list below. | pass |
| Net-by-net check against `pinmap.csv` | S4: all 129 SoC pins. Each pin's [DS] name equals the symbol pin name. Each pin's net equals the pinmap net, and every pinmap NC pin is unconnected (exception below). | pass |
| Net-by-net check against the reference schematic | S5: 273 hand-written connections from [LF] blocks, power.md circuits and datasheet pin tables | pass |
| | S9: exactly the intended pins are NC | pass |
| | S2: every bom.csv ref is in the netlist with the same value, footprint and LCSC number; quantity 193 = 193 | pass |
| | S3: symbol pins equal the footprint pad names. Library footprints are compared with the cached `.kicad_mod` files; custom footprints with the drawing pad list below. | pass |
| | S10: refmap.csv is current and names every BOM ref | pass |
| Decoupling per datasheet on every supply pin | S6: each of the 28 non-ground SoC supply pins has at least one capacitor to GND on its own net, tagged `place_near = U_SOC pin N` | pass |
| | S6: each IC supply pin (LTC2954, 4 × TLV62569, SY6280, NAND, mux) has a local capacitor | pass |
| | S6: the capacitor total on each buck rail equals the `power_rails.csv` figures that check_power P10 uses | pass |
| Every net in the test-point plan exists | S7 (Phase 6): each of TP1–TP31 sits on the net that `design/testpoints.md` names, the netlist has exactly those pads, the md table is parsed and must agree, and **every** rail of power_rails.csv (input, switch, buck and sub-rail: 16) has a pad | pass |

Pinmap exception: pin 58 is NC in the pinmap but has a 100 k pull-down per the pinmap `external` column (D-26), so it sits
on its own two-node net.

[DS] r1.8 has no decoupling table. The per-pin set is the [LF] Pico Pro/Max set (power.md §0/§2), plus the two D-72
additions. Whether a Rockchip hardware design guide asks for more is UNVERIFIED; that guide was not found (power.md §3).

Mutation tests: each mutation was made on a copy of `out/`, and each one makes the check fail.

| Mutation | Failing check |
|---|---|
| Swap USB_DP and USB_DM | S4 and S5 |
| Remove the pin-71 decoupler tag | S6 |
| Remove TP6 from OSC_XOUT | S7 |
| Phase 6: remove TP22 from MIPI_CSI_AVDD_1V8 | S7 (4 fails) |
| Phase 6: testpoints.md names TP14 on the wrong net | S7 |
| Phase 6: remove NAND VCC pin 8 (used to crash with KeyError, verifier P5 minor 6) | S5 + S6 report FAIL, no crash |
| A SKiDL "only one pin attached to net" warning in erc.txt | S8 |

A scratch SKiDL circuit with a one-pin net showed that SKiDL ERC itself reports that case.

**How much the ERC result proves (verifier P5 minor 5).** Most symbol pins in `lib.py` are typed PASSIVE, so SKiDL's ERC
can find unconnected pins and one-pin nets but not driver conflicts. The connection-level proof is S4 (every SoC pin vs
pinmap.csv), S5 (273 hand-written expected connections) and S9 (exact NC set), not the ERC.

### Justified generator warnings (S8 whitelist)

1. `KICAD*_SYMBOL_DIR environment variable is missing`: KiCad libraries are not installed here. Every symbol is
   defined in `lib.py` with `tool=SKIDL`, so no library symbol is used.
2. `fp-lib-table file was not found` (5×): SKiDL cannot check that footprint names exist without KiCad. Phase 4
   checked the library names against the cached KiCad listing (check_bom B3b), and S3 checks the pad names.
3. `Missing tag on  instantiated at <frozen importlib…>`: raised for SKiDL's internal no-connect net object, which has
   no user tag. Every real part has a tag (= its functional name), so the netlist timestamps are stable.

## Design notes and deviations made in this phase

All are recorded in `design/decisions.md` (D-72 to D-76).

- **BOM contingencies resolved (D-72)**
  - Phase 4 carried "[LF] misc copies, net fixed in Phase 5" lines: 3 × 10 k and 2 × 100 nF. Reading [LF]:
    - R21 and R57 were already counted, so 2 × 10 k are removed.
    - R52 is the VCC3V3_SD 10 k bleeder ("Card Power").
    - [LF] C7 100 nF sits on USB_DET_IN (Type-C block).
    - [LF] C35 1 µF on RTC_AVDD3V3 (pin 19) was missing; it is added on the existing 1 µF line.
    - A new 100 nF goes on pin 71 OSC_PLL_DVDD, which had no capacitor of its own on [LF].
  - Result: 193 parts per board, 64 lines, 25 Extended types, $360.34 (check_bom 477 / 0).
  - power_rails.csv capacitance is updated (VDD_0V9 +0.1 µF). Two summing slips are corrected: VCC_1V8 16.5 → 16.4 µF
    and VCC_3V3 11.2 → 11.1 µF. check_power still gives 84 / 0.
- **Not placed:**
  - [LF] R50 (bypass across the SD switch; no value printed)
  - ED1/ED2 (not fitted on [LF])
  - [LF] R4 0 R on CODEC_AVSS: the codec is unused, so pin 37 goes straight to GND as pinmap says
  - [LF] C68 chassis cap: HR911105A pin 8 goes to GND, per the Hanrun note "Connect CHS GND to PCB Ground"
  - The RJ45 jack LEDs (pins 9–12 NC; the activity LED is LED_ETH, D-21)
  - The RTC battery branch (H2, battery diode, NC/1.1K): D-11 already said DNP, and with "whatever is easiest" no
    footprint is added (D-75)
- **USBLC6 VBUS pin (D-72):** USB-C side to VBUS_5V (after F1), USB-A side to VBUS_USBA.
- **Buck feedback taps the regulator side** of every measurement link: JP_MEAS_0V9 and R_MEAS_1V8/3V3/DDR (D-68
  principle, D-73). Opening a link therefore never opens a control loop. The local output capacitors sit on the
  regulator side too.
- **Net names added here (D-73):**
  - `VDD_0V9_BUCK`, `VCC_1V8_BUCK`, `VCC_3V3_BUCK`, `VCC_DDR_BUCK`: regulator side of each link
  - `U4_EN`, `U6_EN`, `VCC_DDR_1V8_EN` ([LF] name), `PWR_EN` (R41/R43 junction = TP8c)
  - `EN_N` (TP8a), `ONOFF_EN` (TP8a′), `QPWR_G`, `PB_IN`, `PWR_BTN_N`, `PWR_KILL_N`, `ONOFF_PDT`
  - `VCC3V3_RTC_IN` (diode output; pinmap keeps VCC3V3_RTC on pin 19, after R11)
  - `SD_PWR_G`, `SDMMC_CLK_SD`, `SD_CD_SW`, `FSPI_CLK_NAND`, `FSPI_CS0N_NAND`
  - `OSC_XOUT_X`, `ETH_*_J`, `ETH_TCT/RCT`, `USBC_DP/DM`, `USBA_DP/DM`, `USBA_ISET`
  - `UART2_TX_HDR`/`UART2_RX_HDR`, `GPIO0_A0_PD`, `LED_*_A`, `NPOR_KEY`, `RECOVERY_KEY`
- **refmap.csv names every BOM part (D-73).** It now has 195 names; make_refmap asserts full coverage. This closes the
  last Phase-4 verifier minor. R18/R19 notes now follow pinmap: R18 on FSPI_D3 (HOLD#), R19 on FSPI_D2 (WP#).

## Footprints that do not exist in the KiCad library (D-74)

Six parts use `board:` footprints. Phase 7 / H1 draws them in a project library named `board`. The netlist fixes their
**pad names** (S3 checks them):

| Footprint | Pad names | Drawing |
|---|---|---|
| `board:RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm` | 1–128, exposed pad **129** (VSS) | [DS] r1.8 p.14 package drawing; [LF] "ePAD 129" |
| `board:TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm` | 1–10 | TI SCDS277A RSE drawing |
| `board:L_FHD4020S_4.0x4.0mm` | 1, 2 | refs/fhd4020s-datasheet |
| `board:SW_TS-1187A_5.1x5.1mm` | 1 = A, 2 = B, 3 = C, 4 = D (A–B and C–D joined internally) | refs/ts-1187a-datasheet (XKB TS-1187A-X-X-X) |
| `board:microSD_TF-01A` | 1–8 contacts, 9 = "cd", **SH** = all 4 shell tabs | refs/tf-01a-datasheet |
| `board:USB_A_AF90_WJDG_RightAngle_THT` | 1 VBUS, 2 D−, 3 D+, 4 GND, **SH** = 2 shell legs | refs/usb-a-af90-wjdg-datasheet |

The three copper-only library footprints were verified in Phase 6 against the KiCad library (GitLab
kicad-footprints master, listing and files in `design/refs/kicad-footprints-p6-2026-10-29/`), and S3 now compares their pads:

- `Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm` (JP1): pads 1, 2
- `NetTie:NetTie-2_SMD_Pad2.0mm` (NT1): pads 1, 2
- `TestPoint:TestPoint_Pad_D1.5mm` (TP*): pad 1, 1.5 mm circle, F.Cu + F.Mask (no paste)

## Items still UNVERIFIED (carried to bring-up / layout)

- **TF-01A card-detect polarity.** Assumed: the "cd" contact closes to the shell/GND when a card is inserted, as pinmap
  pin 11 expects. Check: TP30 (SDMMC_DET) with and without a card, bringup.md step 5.9 (H3).
- **TF-01A and AF 90 WJDG pad numbering** against their drawings, when the footprints are drawn (Phase 7).
- **HR911105A centre taps to 10 nF (voltage-mode PHY, as [LF]).** The RV1106 PHY mode is not stated in [DS]; [LF] is
  copied.
