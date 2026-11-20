# Test points (Phase 6, Rev A)

Status: Executor, Phase 6 round 2, 2026-10-29 (verifier round-1 findings fixed: D-78 amended, D-80). Companion: `bringup.md` (the order in which these points are measured).
The test pads are in the netlist (`schematic/debug.py`, `schematic/out/board.net`). `schematic/check_schematic.py` S7
checks that every TP in the table below sits on the net named here, and that every rail in `power_rails.csv` has a pad.
Decisions for this phase: **D-77** (TP list and numbering), **D-78** (rail-isolated first power-up), **D-79** (acceptance bands)
in `decisions.md`.

Sources (same tags as `power.md` §0; local copies under `refs/`, read as data only):

| Tag | Document | URL | Pages used here |
|---|---|---|---|
| [DS] | Rockchip RV1106 Datasheet Rev 1.8 | https://atta.szlcsc.com/upload/public/pdf/source/20250728/0F25565987B346BAFAE15AD3F3BED3E9.pdf | Table 3-1 absolute ratings p.20; Table 3-2 recommended operating conditions p.20; Table 2-1 pins pp.18–19 |
| [TLV] | TI TLV62569 SLVSDG1C | https://www.ti.com/lit/ds/symlink/tlv62569.pdf | p.4 VFB 0.588/0.600/0.612 V, IQ 35 µA; p.6 §7.3.1 Power Save Mode ("the output voltage rises slightly above the nominal output voltage") |
| [LTC] | LTC2954 datasheet (mirror) | https://cdn.components.ru/media/PDF/1445781.pdf (official https://www.analog.com/media/en/technical-documentation/data-sheets/2954fd.pdf) | p.2 abs-max KILL −0.3 to 7 V; p.3 VEN(VOL) ≤ 0.4 V, VINT(VOL) ≤ 0.4 V, tDB,ON / tDB,OFF 26–41 ms, VKILL(TH) 0.57–0.63 V, tKILL,ON BLANK 400–650 ms; p.9 "The KILL pin must be pulled high within 512ms" |
| [XTAL] | Yajingxin TAXM24M4RFBCCT2T (LCSC C164058) | https://www.lcsc.com/product-detail/C164058.html (local `refs/taxm24m-crystal-datasheet/`) | p.1: 24.000000 MHz, CL 12 pF, tolerance ±10 ppm at 25 °C, stability ±30 ppm over temperature |
| [KFP] | KiCad footprint library (TestPoint, Jumper, NetTie) | https://gitlab.com/kicad/libraries/kicad-footprints (master, listing + files fetched 2026-10-29, `refs/kicad-footprints-p6-2026-10-29/`) | `TestPoint_Pad_D1.5mm`: one pad "1", 1.5 mm circle, layers F.Cu + F.Mask (no paste) |
| [SDK] | Luckfox Pico SDK DTS | https://github.com/LuckfoxTECH/luckfox-pico/tree/main/sysdrv/source/kernel/arch/arm/boot/dts | fiq-debugger on UART2_M1 at 115200 (research.md §7) |

**Part names (D-80).** Every part is written `FUNCTIONAL_NAME [silkscreen ref]`; the bracket is the reference printed on
the board and in `bom.csv` / the `bom_ref` column of `refmap.csv`. Bare Luckfox [LF] designators are never used in this file or
in bringup.md, because many of them are the silkscreen refs of *other* parts on this board (refmap.csv column
`lf_name_collision`). Where refmap.csv's functional name is itself an [LF] designator, these two files use the bench name below
instead (look the part up in refmap.csv by its silkscreen ref):

| Bench name | Silkscreen ref | Part |
|---|---|---|
| R_MIPI_1R | R32 | 1 Ω, VCC_1V8 → MIPI_CSI_AVDD_1V8 (pin 1) |
| R_USB18_1R | R33 | 1 Ω, VCC_1V8 → AVDD1V8_USB (pin 24) |
| R_RTC_SER | R34 | 100 Ω, D_RTC → VCC3V3_RTC (pin 19) |
| R_NPOR_KEY | R35 | 100 Ω in series with SW_RESET on NPOR |
| R_NPOR_PU | R43 | 1 kΩ NPOR pull-up to VCC_3V3 |
| C_NPOR | C71 | 100 nF NPOR cap to GND (Luckfox schematic ref C38; 100 nF since D-117 c, τ = 100 µs; D-127) |
| R_PWREN_FEED | R24 | 1 kΩ VCC_1V8 → PWR_EN (U6 enable) |
| R_EN4_PU | R23 | 10 kΩ U4 EN pull-up to VCC5V0_SYS |
| R_EN57_RC | R20 | 200 kΩ U5/U7 EN RC from VCC5V0_SYS |
| C_EN57_RC | C20 | 100 nF U5/U7 EN RC |

`schematic/check_schematic.py` S7 checks every `NAME [REF]` pair in testpoints.md and bringup.md against the netlist parts list
(functional name or this bench-name table).

Design numbers (set-point bands, drops, timings) come from `power.md` §2, §3, §6 and `power_rails.csv`, which cite their own sources.

## 1. Test-point list

Pads: **KiCad `TestPoint:TestPoint_Pad_D1.5mm`** on the top side ([KFP]: copper + solder mask opening only, so JLCPCB puts no
paste on it and it is not an assembly item; it costs nothing). Every TP is on the top side so it can be probed with the board
lying on the bench. "On" = after a button press with a 5.00 V source; DMM = 10 MΩ input. Values with ≈ are design values,
not datasheet limits. **Stop limit** = the value at which you remove power and investigate before doing anything else.

| TP | Net | Block | What it is | Expected (board on) | Accept band · stop limit | Off / other states | How to measure | Source |
|---|---|---|---|---|---|---|---|---|
| TP21 | `VBUS_IN` | usbc | USB-C VBUS before the fuse | 5.00 V (bench) / 4.75–5.25 V (charger) | 4.75–5.25 V · stop > 5.5 V | same when off (always live with a cable) | DMM to TP19 | power_rails.csv VBUS_IN (USB range, spec not downloaded: UNVERIFIED) |
| TP1 | `VBUS_5V` | prot | after F1 + TVS (PLAN TP1) | TP21 − ≤ 0.07 V | 5.0 V ± 5 % = 4.75–5.25 V · stop > 5.5 V | same when off | DMM; TP21 − TP1 = fuse drop (≤ 0.05 Ω × I) | PLAN TP1; F1 R1max 0.050 Ω (power.md §4) |
| TP13 | `VCC5V0_SYS` | onoff | switched 5 V, Q_PWR drain (power.md TP8b) | TP1 − ≤ 0.12 V | ≥ TP21 − 0.26 V at full load · stop if > 0.1 V while off | **0 V when off, also right after plug-in** (R_BL5 470 Ω) | DMM; scope at plug-in and at turn-on/off | power.md §4 (D-39), §6.3 |
| TP8 | `ONOFF_EN` | onoff | LTC2954-1 EN output, pin 6 = "button controller out" (PLAN TP8; power.md TP8a′) | ≈ TP1 (high = on) | ≥ TP1 − 0.1 V · — | ≤ 0.4 V when off | DMM (100 kΩ pull-up R_ENPU [R8]: a 10 MΩ meter reads ≈ 1 % low) | [LTC] p.3 VEN(VOL); power.md §6.4a |
| TP12 | `EN_N` | onoff | Q_EN drain, inverted enable at the R_G end of the Q_PWR gate (power.md TP8a) | ≈ 0 V | ≤ 0.4 V · — | ≈ 0.985 × TP1 when off (147 kΩ source, 10 MΩ meter) | DMM | power.md §6.4a, §6.5 |
| TP14 | `PWR_EN` | pmu | U6 (3.3 V) enable node, fed from VCC_1V8 through R_PWREN_FEED [R24] 1 kΩ (power.md TP8c) | ≈ TP3 | 1.74–1.86 V (must be > 1.2 V = TLV VIH max) · — | 0 V | DMM | power.md §3 P7d, §6.5; [TLV] p.4 |
| TP4 | `VDD_0V9` | pmu | logic/PMU core (PLAN TP4 "VDD_CORE"), SoC side of JP_MEAS_0V9 [JP1] | 0.900 V | **0.876–0.924 V** · stop > 0.95 V | 0 V | DMM; scope for ripple (20 MHz BW limit) | power.md §2 (VFB ±2 %, 1 % R); [DS] Table 3-2 p.20 DVDD 0.81–0.95 V, Table 3-1 abs-max 0.99 V |
| TP15 | `VDD_ARM` | pmu | CPU_DVDD (pin 115), behind net-tie NT_ARM [NT1] | = TP4 | **0.873–0.924 V** · stop < 0.85 V or > 1.05 V | 0 V | DMM; TP4 − TP15 = copper drop (≤ 3 mV) | power.md P3L (D-68); [DS] Table 3-2 CPU_DVDD 0.85–1.05 V |
| TP5 | `VCC_DDR` | pmu | DDR3L VDDQ (PLAN TP5) | 1.362 V | **1.320–1.405 V** · stop > 1.45 V | 0 V | DMM; scope during the DDR training in the boot log | power.md §2 (127k/100k); [DS] Table 3-2 1.283–1.45 V, Table 3-1 abs-max 1.45 V |
| TP3 | `VCC_1V8` | pmu | 1.8 V (PLAN TP3) | 1.800 V | **1.741–1.861 V** · stop > 1.98 V | 0 V | DMM | power.md §2; [DS] Table 3-2 1.62–1.98 V |
| TP22 | `MIPI_CSI_AVDD_1V8` | pmu | VCC_1V8 via R_MIPI_1R [R32] 1 Ω → pin 1 | ≈ TP3 | TP3 − ≤ 0.01 V (≥ 1.73 V) · stop > 1.98 V | 0 V | DMM | power_rails.csv (0.01 A × 1 Ω); [DS] Table 3-2 MIPI 1.62–1.98 V |
| TP23 | `AVDD1V8_USB` | pmu | VCC_1V8 via R_USB18_1R [R33] 1 Ω → pin 24 | ≈ TP3 | TP3 − ≤ 0.03 V (≥ 1.71 V) · stop > 1.98 V | 0 V | DMM | power_rails.csv (0.03 A × 1 Ω); [DS] Table 3-2 SARADC_USB 1.62–1.98 V |
| TP24 | `VCC1V8_CODEC` | pmu | VCC_1V8 via FB2 → pin 31 | = TP3 | TP3 − ≤ 1 mV · stop > 1.98 V | 0 V | DMM | FB2 50 mΩ (D-53); [DS] Table 3-2 1.62–1.98 V |
| TP25 | `ETH_AVDD1V8` | pmu | VCC_1V8 via FB3 → pin 96 | = TP3 | TP3 − ≤ 3 mV · stop > 1.98 V | 0 V | DMM | FB3 50 mΩ × 0.05 A; [DS] Table 3-2 1.62–1.98 V |
| TP2 | `VCC_3V3` | pmu | 3.3 V IO (PLAN TP2) | 3.252 V | **3.135–3.372 V** · stop > 3.465 V | 0 V | DMM | power.md §2 (442k/100k, D-43); [DS] Table 3-2 3.0–3.465 V |
| TP26 | `FEPHY_AVDD3V3` | pmu | VCC_3V3 via FB1 → pin 101 | = TP2 | TP2 − ≤ 3 mV · stop > 3.63 V | 0 V | DMM | FB1 50 mΩ × 0.06 A; [DS] Table 3-2 ETH 2.97–3.63 V |
| TP18 | `VCC3V3_RTC` | pmu | RTC supply at pin 19, after D_RTC [D2] + R_RTC_SER [R34] 100 Ω | ≈ TP2 − 0.1…0.3 V | 2.9–3.37 V · stop > 3.6 V | 0 V (no battery, D-75) | DMM | power_rails.csv; Schottky Vf at µA not in a downloaded datasheet (UNVERIFIED); [DS] Table 3-2 1.6–3.6 V |
| TP16 | `VCC3V3_SD` | sd | card power after Q_SD [Q4] | ≈ TP2 (card powered by default) | TP2 − ≤ 0.05 V · — | 0 V (R_SD_BL [R40] 10 kΩ) when SDMMC_PWREN is high or the board is off | DMM | pinmap pin 59 (low = card powered, reset pull-down); power.md §2 |
| TP17 | `VBUS_USBA` | usb | USB-A port power after U_USBA [U8] | 0 V until Linux sets USBA_VBUS_EN | enabled: ≈ TP13 no load; **4.44–5.20 V at 0.5 A** · stop > 5.5 V | 0 V (EN pull-down R_USBAEN [R61]) | DMM; scope on TP13 + TP17 when enabling | power.md §2 VBUS_USBA (D-49), §8 (D-58) |
| TP6 | `OSC_XOUT` | xtal | 24 MHz crystal, SoC pin 69 side of R_Y1_SER [R50] 22 Ω (PLAN TP6) | 24.000 MHz | 24.000 MHz ± 50 ppm (± 1.2 kHz) · no oscillation = stop | flat when off | scope, **10× probe, ground spring to TP31**, frequency counter; a probe adds ≈ 10–15 pF and can pull the frequency down by tens of ppm (ESTIMATE). Final proof: readable 115200-baud console | [XTAL] p.1 (±10 ppm + ±30 ppm; load-mismatch pulling with 18 pF caps UNVERIFIED, D-52); amplitude: no [DS] figure (UNVERIFIED) |
| TP7 | `NPOR` | soc | SoC power-on reset, active low (PLAN TP7 RESET_N) | ≈ TP2 (high) after VCC_3V3 | ≥ 0.9 × TP2 · — | ≈ 0.30 V while SW_RESET [SW2] is held (R_NPOR_KEY [R35] 100 Ω vs R_NPOR_PU [R43] 1 kΩ); 0 V off | DMM; scope with TP2 for the release edge (τ = R_NPOR_PU [R43] 1 kΩ × C_NPOR [C71] 100 nF = 100 µs; [LF] calls this cap C38) | power.md §3 step 4; [LF] "Power Reset" |
| TP9 | `UART2_TX` | uart | SoC debug UART TX (pin 79, SoC side of R_UART_TX [R66] 1 kΩ) | idle high ≈ TP2; frames during boot | idle ≥ 2.9 V · — | low before the UART is set up (pin 79 reset pull-down, [DS] Table 2-1 p.18 `_d`) | scope (bit time 8.68 µs at 115200) or the USB-UART adapter on J_UART [J6] | [DS] Table 2-1 p.18; [SDK] 115200 |
| TP10 | `UART2_RX` | uart | SoC debug UART RX (pin 80, SoC side of R_UART_RX [R67] 1 kΩ) | idle high ≈ TP2 | idle ≥ 2.9 V · — | ≈ adapter TX level when the board is off and an adapter is attached (≤ 3 mA through 1 kΩ, D-30) | scope or DMM | [DS] Table 2-1 p.18 `_u`; D-30 |
| TP11 | `LED_ETH` | eth | Ethernet activity GPIO (pin 74) → LED3 (PLAN TP11; there is no 25 MHz node: the PHY is inside the SoC and the board has only the 24 MHz and 32.768 kHz crystals) | toggles with traffic (ledtrig-netdev) | high ≈ TP2 when lit · — | 0 V (reset pull-down) until Linux drives it | scope or watch LED3 | D-21; pinmap pin 74 |
| TP27 | `PB_INT_N` | onoff | LTC2954 INT → SoC pin 60 (power-button interrupt) | ≈ TP2 idle | idle ≥ 2.55 V; ≤ 0.4 V while the button is held ≥ 41 ms · — | 0 V off | scope with SW_PWR [SW1] press | [LTC] p.3 VINT(VOL), tDB,OFF 26–41 ms; D-19 |
| TP28 | `PWR_KILL` | onoff | SoC pin 63 power-off request (active high) | 0 V | ≤ 0.3 V while running · — | goes ≈ TP2 for the last instant of a Linux power-off, then everything falls | scope single-shot during `poweroff` | D-03, D-20; power.md §6.2 |
| TP29 | `PWR_KILL_N` | onoff | LTC2954 KILL pin 8 (100 kΩ R_KU [R6] to VCC_3V3) | ≈ TP2 | > 0.63 V needed by 400–650 ms after turn-on · — | 0 V off; ≈ 0 V when PWR_KILL is high. **Hold-up point for the rail-isolated step of bringup.md (10 kΩ from TP1)** | DMM / scope | [LTC] p.2 KILL abs-max 7 V, p.3 VKILL(TH), tKILL,ON BLANK, p.9 |
| TP30 | `SDMMC_DET` | sd | microSD card detect at SoC pin 11 (via R_SD_DET [R49] 100 Ω) | card in: ≈ 0 V; card out: ≈ TP2 (pin 11 reset pull-up) | record both levels at bring-up · — | — | DMM, with and without a card | pinmap pin 11 ("switch to GND = card present"); TF-01A switch polarity UNVERIFIED (verifier P5 minor 1) |
| TP19 | `GND` | — | probe ground, power area | 0 V | — | — | DMM black lead / scope ground | — |
| TP20 | `GND` | — | probe ground, SoC / UART area | 0 V | — | — | — | — |
| TP31 | `GND` | — | probe ground next to TP6 for a short scope ground spring | 0 V | — | — | — | — |

Further ground points that need no pad: J_UART [J6] pin 1, every GND pin of the 2×20 header (6, 9, 14, 20, 25, 30, 34, 39).

### 1.1 PLAN table → physical pads

| PLAN row | Physical pad(s) | Note |
|---|---|---|
| PLAN TP1 VBUS_5V (after fuse) | TP1 | TP21 adds the input side, so a blown or high-resistance fuse is visible |
| PLAN TP2 VCC_3V3 | TP2 | Design nominal is 3.252 V, not 3.30 V (D-43). The design band 3.135–3.372 V is used, not the plain ±3 % of 3.3 V (3.20–3.40 V); see D-79 |
| PLAN TP3 VCC_1V8 | TP3 | ±3 % of 1.8 V = 1.746–1.854 V; design band 1.741–1.861 V |
| PLAN TP4 VDD_CORE | TP4 (logic) + TP15 (CPU) | one buck, two nets (D-06, D-68) |
| PLAN TP5 VCC_DDR | TP5 | nominal 1.362 V ([LF] divider), inside [DS] 1.283–1.45 V |
| PLAN TP6 24 MHz | TP6 + TP31 ground | |
| PLAN TP7 RESET_N | TP7 | net NPOR |
| PLAN TP8 PWR_EN / button controller out | **TP8 = controller out (high when on, as PLAN says)**, TP12 = inverted EN_N, TP13 = VCC5V0_SYS, TP14 = PWR_EN | D-77 swaps the Phase-5 numbering of TP8/TP12 so TP8 reads "high when on" (verifier P5 minor 2) |
| PLAN TP9/10 UART2 TX/RX | TP9, TP10 | baud 115200 ([SDK]) |
| PLAN TP11 ETH 25 MHz / PHY LED | TP11 | no 25 MHz exists on this board (internal PHY) |

### 1.2 Measurement points that are not test pads

| Point | Net | Used in | Expected |
|---|---|---|---|
| JP_MEAS_0V9 [JP1] pad 1 (buck side) | `VDD_0V9_BUCK` | bringup.md step 1.B (cut), steps 2–3 (measured) | 0.876–0.924 V; with no load, Power Save Mode may read up to ≈ 2 % higher ([TLV] p.6, amount UNVERIFIED) but must stay < 0.95 V |
| R_MEAS_DDR [R31] pad 1 (buck side) | `VCC_DDR_BUCK` | step 1.B (removed), steps 2–3 | 1.320–1.405 V (≤ 1.43 V no-load) |
| R_MEAS_1V8 [R29] pad 1 (buck side) | `VCC_1V8_BUCK` | step 1.B (removed), steps 2–3 | 1.741–1.861 V (≤ 1.90 V no-load) |
| R_MEAS_3V3 [R30] pad 1 (buck side) | `VCC_3V3_BUCK` | step 1.B (removed), steps 2–4 | 3.135–3.372 V (≤ 3.44 V no-load) |
| U4–U7 pin 5 (FB), on the IC lead (not the pad) | `U4_FB` … `U7_FB` | step 1 (unpowered) | see bringup.md step 1 table |
| J_HDR [J5] pins 1/17 and 2/4 | VCC_3V3 / VCC5V0_SYS | step 11 | = TP2 / = TP13 |

In steps 2 and 3 these buck-side pads must read **< 0.05 V while the board is off** (Q_PWR not conducting) and, in step 3,
0 V on R_MEAS_3V3 [R30] pad 1 (U6 is not enabled while VCC_1V8 is isolated).

Pin 1 vs pin 2 of each link is the netlist numbering (`schematic/out/nets.csv`: JP1.1, R29.1, R30.1, R31.1 are the `*_BUCK`
side). **Phase 7 rule:** mark the buck-side pad of JP1, R29, R30 and R31 with a "B" on the silkscreen.

## 2. Layout rules for the pads (Phase 7 / H1)

1. All pads on the top side, ≥ 1 mm from any component body, none under a connector or the heatsink area of the SoC.
2. Group the power pads (TP21, TP1, TP13, TP4, TP5, TP3, TP2, TP14, TP8, TP12) in one row near the bucks, with TP19 at
   the end of the row, so one DMM ground stays put. Silkscreen each pad with its TP number and a short net name (e.g. "TP4 0V9").
   **As built (layout L5, D-115 a / D-116 d, owner approval items at CHECKPOINT 2):** TP15 (VDD_ARM) is not in the row: it sits
   west of the SoC at (19.50, 41.50), 3.4 mm from C44.1 (its 58 mm load-free L4 branch to the row was removed); probe it
   with the DMM ground on any GND pad (TP19 or a header GND pin). The sub-rail pads sit next to their rails south of the
   SoC: TP23 (AVDD1V8_USB) at (41.30, 51.30), TP24 (VCC1V8_CODEC) at (43.85, 52.30), TP18 (VCC3V3_RTC) at (46.60, 52.30).
3. TP6 within 5 mm of SoC pin 69, TP31 (GND) within 3 mm of TP6. Keep the TP6 stub short and away from the buck switch nodes.
4. TP22–TP26 sit near their decoupling capacitors; a short stub off the rail is fine (DC measurement only).
5. TP9/TP10/TP20 next to J_UART; TP27–TP29 next to U_ONOFF; TP29 and TP1 close enough for a 10 kΩ through-hole resistor to bridge
   them (≤ 10 mm) — used once in bringup.md step 3.
6. TP30 near the microSD socket.

## 3. Gate TP-D6 self-check (test-point clause)

| Gate item | Pad | Check |
|---|---|---|
| Every rail | VBUS_IN TP21, VBUS_5V TP1, VCC5V0_SYS TP13, VDD_0V9 TP4, VDD_ARM TP15, VCC_DDR TP5, VCC_1V8 TP3, MIPI_CSI_AVDD_1V8 TP22, AVDD1V8_USB TP23, VCC1V8_CODEC TP24, ETH_AVDD1V8 TP25, VCC_3V3 TP2, FEPHY_AVDD3V3 TP26, VCC3V3_RTC TP18, VCC3V3_SD TP16, VBUS_USBA TP17 — all 16 rows of power_rails.csv | check_schematic S7 "rail … has a test pad" (16/16) |
| 24 MHz clock | TP6 (+ TP31 GND) | S7 |
| Reset | TP7 | S7 |
| Button / power enable | TP8 (controller out), TP12, TP13, TP14, plus TP27–TP29 for the interrupt/kill path | S7 |
| UART TX/RX | TP9, TP10 | S7 |
| This file = netlist | 31 TPs, each net above = netlist net | S7 parses this table |
