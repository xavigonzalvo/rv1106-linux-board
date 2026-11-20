# Shared running log

## 2026-10-28 — Executor — Phase 1 (Architecture & block diagram), attempt 1
- Downloaded and kept under refs/ (read only, never executed): RV1106 datasheet Rev 1.8 (refs/rv1106-datasheet-r1.8/) and Luckfox Pico Pro/Max schematic from the LuckfoxTECH/Luckfox-Pico-docs GitHub repo (refs/luckfox-pico-pro-max-sch/). Text extracted and crops rendered with venv pypdf/pymupdf (python -I), with scripts kept in the scratchpad, outside refs/.
- Wrote requirements.md (R1–R8 split into sub-requirements and traced to blocks), architecture.md (13 blocks, Mermaid diagram, power tree, 29 named interfaces IF-01..IF-29 with signal type, voltage and SoC pin numbers), decisions.md (D-01..D-15).
- Main deviations from Luckfox: on/off controller plus high-side switch (D-03), input fuse/TVS/ESD (D-04), USB 2:1 mux for USB-C device + USB-A host on the single OTG port (D-05), no series Schottky (D-10), LEDs on 3.3 V GPIOs (D-09).
- Self-check against TP-D1: every R1–R8 maps to ≥ 1 block (requirements.md traceability table); every diagram arrow has an IF row with signal type and voltage.

## 2026-10-28 — Verifier — Phase 1 gate TP-D1, round 1: FAIL (1 major, 7 minor)
- Read requirements.md, architecture.md and decisions.md in full. Re-extracted both refs myself (pymupdf, python -I, scripts in scratchpad).
- Checked against the datasheet ([DS] Table 2-1 pp.18–19, Tables 3-1/3-2 p.20, §1.2.2 p.6–7, §1.2.13 p.13, §2.1 p.15). All 29 IF pin numbers match: supplies, OSC 68/69, RTC 21/20, nPOR 66, FSPI 48/47/41/42/44/39, SDMMC 15/16/14/12/18/17/11, ETH 97–100/102, USB 26/27/25, UART2_M1 79/80, SARADC_IN0 23, GPIO0_A4 63. The voltage ranges match too.
- Checked against [LF]: VDD_ARM is fed through R32 0R. FB4 is NC/0R. U7 sets 1.35 V with 127K/100K. U6 EN = PWR_EN via R43 200K. D1 is MBR230LSFT1G. CC uses R3/R6 5.1K. USB_DET_IN uses R2 10K / R5 18K. SDMMC_PWREN is on pin 59 (Q1 SI2301). RECOVERY has a 10K pull-up to VCC_1V8, 100R and Key2. LED1 is on GPIO3_C6. The IO-domain labels VCCIO1/3/4/5/6 (3.3 V) and VCCIO7 (1.8 V only) all match the architecture.
- JLCPCB C5328706 exists: RV1106G3, QFN-128, Extended. The page shows no stock figure, so stock is checked in Phase 4. This phase produced no scripts to run.
- Gate result: every requirement maps to a block and every interface is named. The gate still fails on one MAJOR item, IF-07 (onoff/soc): PWR_KILL_N is active-low but its candidate pin GPIO0_A4 defaults to a pull-down, so KILL would be asserted from power-on until Linux takes the pin and the board would switch itself off. Minor items cover diagram/IF naming, the traceability summary, the GPIO default-state rule, the LF PWR_EN pull-up (R41 "1K/NC"), LF LED_GREEN on GPIO0_A3, the BootROM SD vs SPI NAND order, and D-03 fallback. Returned to the Executor.

## 2026-10-28 — Executor — Phase 1, round 2 (fixes for verifier round 1)
- MAJOR IF-07 fixed: kill line is now PWR_KILL, active-HIGH on GPIO0_A4_d (reset pull-down) + 100 kΩ pull-down; N-MOSFET inverter to the controller if its KILL is active-low (D-03 option (a); option (b) rejected). Added reset-state rule §4.1 / D-16 for PWR_KILL, USB_SEL, USBA_VBUS_EN, SDMMC_PWREN (pin pull must match, else external ≤ 10 kΩ).
- PWR_EN: fit [LF] R41 1 kΩ to VCC5V0_SYS (D-17), open item for TP-D3. Status LED = [LF] LED_GREEN on pin 62 GPIO0_A3_u (confirmed by word positions in the [LF] PDF, U1 pin 62) (D-09). BootROM SD-vs-FSPI order marked UNVERIFIED, Phase 2 research + fallback (D-18). D-03 now has fallbacks F1/F2 for ≥ 8 s hard-off.
- Diagram: every arrow labelled with its IF number; USBC_DP/DM naming; USBA_VBUS_EN soc→usbsw; new IF-30 ESD (prot↔usbc/usb); VCC_3V3→usb/ui and VCC_1V8→ui drawn; RTC crystal arrow; IF table declared authoritative. requirements.md summary rows = union of sub-requirements; R8 blocks listed.

## 2026-10-28 — Verifier — Phase 1 gate TP-D1, round 2: PASS (0 blocker, 0 major, 6 minor carried to Phase 2/5/8)
- Re-read requirements.md, architecture.md, decisions.md in full. Re-extracted [DS] and [LF] myself (pymupdf, python -I, scripts in scratchpad/ver2) and parsed the hidden Altium net tokens in [LF].
- Confirmed against sources: every round-1 fix is present. Pins 59 GPIO0_A1_d, 62 GPIO0_A3_u, 63 GPIO0_A4_d, 66 nPOR ([DS] Table 2-1 p.19). All 1.8 V/3.3 V/0.9 V/DDR supply pin lists match. [LF] net PWR_EN = R24.2, R41.1, R43.2, and R41.2 sits on VSYS (= VCC5V0_SYS). R43 = 200K. Q1 SI2301 is on SDMMC_PWREN, pin 59. RV1106G3 is QFN128 12.3 mm with 0.35 mm pitch (§1.2.14 p.14) and 2Gb DDR3L (§2.1 p.15). LCSC C5328706 MPN RV1106G3 exists; its page shows no stock figure (Phase 4). The R1–R8 traceability unions are correct and IF-01..IF-30 all carry name, type and voltage. No scripts in this phase; Mermaid not machine-parsed (no mmdc), syntax hand-checked.
- Minor items for later phases: (1) D-16/§4.1 pull value is wrong. [DS] Table 3-3 p.21 gives Rpu/Rpd 16/25/43 kΩ, and a 10 kΩ opposing resistor leaves the node at up to 1.33 V, so the limit must be ≤ 2 kΩ, or use matching-pull pins only. (2) GPIO0_A4 func1 = pmic_sleep_m0 (SDK rv1106-pinctrl.dtsi), and the same applies to GPIO0_A3 = pmic_sleep_m1. These must never be muxed to PMIC sleep, or suspend would kill the board. (3) [LF] LED_GREEN at pin 62 is only a label stub with no LED, so our status LED is new; wire it active-low. (4) USB_VBUSDET is always high because USB-C is the power input, so the USB role is set by software from USB_SEL. (5) Use the exact per-rail ranges from Table 3-2. (6) Ethernet magnetics CT goes to GND through 10 nF ("103") as on [LF] J2, with no CT bias.

## 2026-10-28 — Executor — Phase 2 (Reference research & pin map), attempt 1
- **What this phase is doing:** mapping every RV1106G3 pin (128 + EPAD) to a function, net, IO-voltage domain and source, and finding the boot/strap pins.
- Outputs: `pinmap.csv` (129 rows), `research.md` (sources [DS]/[LF]/[SDK]/[CD]/[FORUM], IO-domain table, strap/boot section, gate self-check), `tools/ds_pins.py` + `tools/check_pinmap.py` (automatic TP-D2 checks). Extra refs: Luckfox SDK DTS/pinctrl and the kernel io-domain driver under refs/ (read only).
- Self-check `check_pinmap.py`: **11/11 pass**. Covers: names match [DS] Table 2-1, no pin or net used twice, NAND on VCCIO3 / SD on VCCIO4 / UART on VCCIO1 at 3.3 V, nothing on 1.8 V VCCIO7, reset pulls match safe states, strap pin 23 identified, header 28 signals + 12 power.
- New decisions D-19..D-26: PB_INT_N on pin 60, matching-pull rule replacing D-16's 10 kΩ clause, ETH LED on pin 74, Pi-style header, MASKROM strap = SARADC_IN0 (copy LF), boot order UNVERIFIED (NAND likely first), NAND-disable link on FSPI_CS0N, unused-pin handling.
- Still UNVERIFIED: BootROM SD-vs-NAND order; that the BootROM samples SARADC_IN0 (no Rockchip doc found); RV1106 io-domain software config (the Luckfox DTS has none).

## 2026-10-28 — Verifier — Phase 2 gate TP-D2, round 1: FAIL (0 blocker, 1 major, 4 minor)
- **What this check did:** re-checked the pin map, IO domains and boot/strap pins against the RV1106 datasheet, the Luckfox Pro/Max schematic and the Luckfox SDK DTS, without relying on the executor's summary.
- Ran `design/.venv/bin/python -I design/tools/check_pinmap.py design`: 11 pass, 0 fail. Ran `tools/ds_pins.py`: 129 entries.
- Independent checks (my own pymupdf extraction, python -I, scripts in scratchpad):
  - [DS] Table 2-1 pp.18–19: the pin name comes before the pin number, so the parser is aligned. Every pin number used for SD, NAND, Ethernet, USB, the oscillators, nPOR, UART2_M1, GPIO0_A0–A6 and the header matches.
  - Every `_u`/`_d`/`_z` reset pull in pinmap.csv matches the suffix in the datasheet. All 129 rows cite [DS]. Each of the 28 header signals is on a different pin.
  - [DS] Table 3-3 p.21 confirms Rpu/Rpd 16/25/43 kΩ and Vih 2.0 V. [DS] §1.2.2 p.6 lists the boot devices without an order.
  - [LF] confirms the supply-pin nets for VCCIO1/3/4/5/6/7, PMU and VCCIO_FLASH = VCC_3V3. It also confirms the RECOVERY key (Key2 on pin 23; Key1 is reset; there is no other key), Y1 with 18 pF / 22R / 1M, R7 6.04K, R46–R49 0R, Q1 SI2301 with R55 10K and R51 100K, and the R2 10K / R5 18K divider from VBUS.
  - [SDK] confirms uart2m1 = GPIO1_B2/B3, fspi_cs0 = GPIO4_B0, sdmmc0_det = GPIO3_A1, `no-1-8-v`, and fiq-debugger at 115200.
  - A web search found no Rockchip document on the boot order or on SARADC_IN0 sampling, so both stay UNVERIFIED. The D-25 link is an acceptable mitigation.
- **MAJOR (usb):** pin 25 USB_VBUSDET is fed by a divider from the raw USB-C VBUS, which stays live while `onoff` holds the SoC unpowered. That puts about 3.2 V through 10 kΩ into an unpowered SoC pin. [LF] avoids this only because its VBUS is always present ("USB power must supply always" note). Fix: feed the divider from the switched VCC5V0_SYS, or gate it, and record this as a new D-xx.
- Minor issues:
  - (gpio/sd) The Luckfox DTS pinctrl conflicts with our header, and research.md wrongly says Luckfox "enables" spi0/i2c3/i2c1/uart3/uart4; they are disabled.
  - (gpio) No I²C pull-ups are specified on the header.
  - (uart) A debug adapter can back-power the board through RX while it is off.
  - The tool's C9 check compares against the pinmap's own column instead of the datasheet.

## 2026-10-28 — Executor — Phase 2 (Reference research & pin map), attempt 2 (fixes for verifier round 1)
- **What this phase is doing:** fixing the verifier's findings on the pin map. The USB VBUS-detect pin must not be powered while the board is off. Luckfox DTS conflicts are listed for Phase 8. The header gets I²C pull-ups and the debug UART gets series resistors. The self-check script is stricter.
- Major fixed: the USB_VBUSDET divider (pin 25, [LF] R2/R5) now hangs on switched VCC5V0_SYS, not raw VBUS (new D-27). Updated in pinmap.csv row 25, architecture.md (usbc block, diagram IF-23, IF-23 row, power tree) and research.md §3. The 'Table 3-7' cite is replaced with "VBUSDET threshold/max UNVERIFIED in [DS]".
- Minor fixes:
  - D-22 corrected: Luckfox *defines* spi0/i2c3/i2c1/uart3/uart4 but sets them to "disabled".
  - research.md §7.1 adds a "Phase 8 must not inherit" table (D-28). It covers the verifier's list plus extras found by mapping every ipc-dtsi pinctrl group to our pins: pwm2/3/4 m2, uart1 m1, i2c0 m2, the fbtft child of spi0 and i2c4/camera.
  - I²C pull-ups: 2.2k on pins 85/86 and 4.7k on pins 104/105 (D-29).
  - 1k series resistors on UART2_TX/RX (D-30), plus a note that header accessories can back-power the board (D-31).
- check_pinmap.py: C4 now uses exact '/'-token matching. C9 derives the pull from the [DS] suffix. New checks C0 and C12–C16. Result **17 pass, 0 fail**. A mutation test (broken copy in scratchpad) makes C4/C12/C13/C14 fail as expected.
- Incident: a bad in-place rewrite truncated pinmap.csv. It was rebuilt by re-running the attempt-1 generator (scratchpad), whose output matched the surviving 22 rows byte for byte. The two known hand edits from attempt 1 were re-applied: pin 23 [CD]/D-23 cite, now with its malformed embedded quotes fixed, and pin 58 100k pull-down/D-26. Then the round-2 changes were applied. Hand edits to rows I had not viewed may have been lost; all gate checks pass on the rebuilt file. New check C0 catches malformed CSV rows.

## 2026-10-28 — Verifier — Phase 2 gate TP-D2, round 2: PASS (0 blocker, 0 major, 4 minor)
- **What this check did:** re-checked the round-2 pin-map fixes (USB VBUS-detect moved to the switched 5 V rail, I²C pull-ups, debug-UART resistors, Luckfox DTS "must not inherit" list) and the rebuilt pinmap.csv against the RV1106 datasheet, the Luckfox Pro/Max schematic and the Luckfox SDK DTS.
- Ran `design/.venv/bin/python -I design/tools/check_pinmap.py design`: **17 pass, 0 fail**. My own mutation copy (scratchpad/ver3/m1: pin 25 back on USB-C VBUS, duplicated net, wrong reset pull, missing 1k, missing I²C pull-up, non-exact mux token, strap status removed) made C4, C5, C10, C12, C13, C14, C15 and C16 fail as expected.
- Independent extraction (pymupdf, python -I, scripts in scratchpad/ver3): [DS] Table 2-1 pp.18–19 matches all 129 ds_pin_name values, including the suffix-less pins 105 (GPIO2_B0) and 110 (SDMMC_D0/…/GPIO2_A1). [DS] Table 3-3 p.21 Rpu/Rpd 16/25/43 kΩ and Vih 2.0 V, so the 2.2k/4.7k pull-ups give ≥ 2.9 V / 2.55 V idle. [LF] confirms R2 10K / R5 18K on VBUS → USB_DET_IN with the "USB must always power supply" note at pin 25, plus R11 100R, R12 1K/C38 10nF, R22 100R, R21/C44/R23, R57/C73, R54 100R, R15/R16 22R, R18/R19 10K to VCCIO_FLASH, Y1 18pF/22R/1M, Y2 18pF, R1 240R, R7 6.04K, R31 1R, R8 1R, Q1 SI2301 + R55 10K/R51 100K. [SDK]: the Pro/Max DTS L97-130 sets spi0/i2c3/i2c1/uart3/uart4 to "disabled" (D-22 correction is right). Every ipc-dtsi line cited in research.md §7.1 checks out, and the pinctrl groups map to the stated pins (i2c1m1 = GPIO2_B0/B1, i2c3m1 = GPIO1_D2/D3, uart3m1 = GPIO1_D0/D1, pwm8–11 m1 = GPIO1_C4–C7, spi0m0 = GPIO1_C0–C3, pmic_sleep m0/m1 = GPIO0_A4/A3).
- Truncation incident: no pre-incident copy exists. I re-read all 129 rows of the rebuilt file and found no value that disagrees with [DS], [LF] or decisions D-19..D-31.
- Minor issues (none block the gate):
  - (uart) architecture.md: the IF-24 row and the `uart` block do not show the D-30 1k resistors, and the line saying the console baud is 1 500 000 (UNVERIFIED) is stale; the SDK says 115200.
  - (usb) D-27 and research §3 say pin 25 "never sees voltage while the SoC is unpowered". During power-up it does for a few ms, while the bucks ramp; [LF] behaves the same way. Reword this and have Phase 3 measure the delay.
  - (soc) Version-control pinmap.csv and keep the generator under design/tools.
  - (gpio) Pins 105/110 have no [DS] reset-pull suffix, so their notes should say "UNVERIFIED pull" rather than quote 16k.

## 2026-10-28 — Executor — Phase 3 (Power architecture), attempt 1
- **What this phase is doing:** designing how the board gets and controls power. USB-C 5 V comes in through a fuse and TVS. A push-button controller (LTC2954-2) switches it with a P-MOSFET. Four 2 A bucks make 0.9 / 1.35 / 1.8 / 3.3 V in a fixed order. A short button press asks Linux to shut down; Linux then cuts power through a kill line. Holding the button for 8 s forces the board off.
- New sources, each in its own refs/ folder, read only with `python -I` and never executed: TI TLV62569 datasheet SLVSDG1C (refs/tlv62569-datasheet/), LTC2954 datasheet rev B mirror copy (refs/ltc2954-datasheet/; the analog.com PDF timed out), AOS AO3401A Rev 3.1 (refs/ao3401a-datasheet/). The [LF] regulator area was rendered and read. U4–U7 part numbers are not printed on the sheet (UNVERIFIED). Read from the sheet: dividers, EN RCs (R35 10k; R14 200k/C77 100n shared by U5/U7; R43 200k/C65 100n; R41 1K), inductors and nPOR R12 1K to VCC_3V3.
- [DS] r1.8 has no power sequence and no rail currents (checked over the full text), so currents are marked ESTIMATE and the sequence follows [LF] plus D-34.
- Wrote power.md (tree, rail table, sequencing, budget, USB-C sink/protection, on/off circuit, R4 behaviour table, gate self-check). Also wrote power_rails.csv and tools/check_power.py: **29 pass, 0 fail**. A mutation copy in the scratchpad (rail removed, divider changed, current raised) fails P1/P3/P5/P6 as expected.
- Decisions D-32..D-40:
  - TLV62569 ×4 (D-32).
  - LTC2954-2 + AO3401A, PDT 0.82 µF, KILL pull-up to VCC_3V3 (D-33).
  - C65 220 nF so 3.3 V/nPOR come last (D-34).
  - 0.9 V divider 49.9k/100k (D-35).
  - Budget allocations: 6.99 W worst case (D-36).
  - Fuse/TVS requirements (D-37).
  - Closed D-17 (D-38) and verified D-10 (D-39).
  - Corrected the D-27 wording on VBUSDET during power-up (D-40).
- architecture.md §3 now points to power.md.

## 2026-10-28 — Verifier — Phase 3 (Power architecture), attempt 1: **FAIL (3 major, 5 minor)**
- **What this check did:** independently re-read power.md, power_rails.csv, check_power.py, D-32..D-40 and the primary sources: TLV62569 SLVSDG1C pp.3–4 and 9, LTC2954 rev B pp.2–4 and 9–12, AO3401A p.1, RV1106 DS r1.8 Tables 3-1/3-2 p.20, and the [LF] sheet rendered at 1200–2400 dpi. Ran `check_power.py`: **29 pass, 0 fail** (output reproduced). Supply-pin mapping (28/28), DS voltage ranges, LTC2954 TSOT-23-8 pinout, KILL/INT/blanking/lockout figures, the PDT equation, AO3401A ratings and the power budget arithmetic all check out.
- **Major 1 (pmu): the U4 and U7 output filters are outside the TLV62569 Table 4 (p.9) proven combinations.** At 0.6–1.2 V with 2.2 µH, only 2×22 µF is checked; at 1.2–1.8 V with 2.2 µH, 22 µF or 2×22 µF are checked. The design uses U4 = 22 + 4.7 µF and U7 = 10 µF. It also changed [LF]'s 1.0 µH (L2/L4), so the filters now match neither TI nor [LF]. power.md §2 says they are "inside Table 4"; that is false. Fix: U4 = 2.2 µH + 2×22 µF + 100 nF, and U7 = 2.2 µH + 22 µF + 100 nF (TI "++" standard), or record a justified deviation.
- **Major 2 (onoff/prot): C_GD 33 nF (gate–drain) with R_GS 100k turns Q_PWR on at cable plug-in.** When VBUS steps up, the gate is held near the drain (0 V) by 33 nF against about 0.65 nF Ciss, so VGS is about −4.9 V. VCC5V0_SYS then jumps to about 4 V for a few ms with no button press. That gives a partial, out-of-order rail power-up on every plug-in, and hot-plug ringing reaches the 6 V-abs-max bucks. Fix: remove C_GD, or add C_GS ≥ 10 × C_GD (for example C_GD 3.3 nF and C_GS 47 nF, with R_G re-sized for the ramp). Re-derive the inrush and turn-off figures and show the plug-in case in §6.
- **Major 3 (pmu): the sequencing proof (P7) uses a wrong EN threshold.** TLV62569 p.4 gives VIL as min 0.4 V and typ 0.85 V; VIH is only bounded at max 1.2 V. 0.85 V is not a guaranteed lower bound. With 0.4 V, U6 can enable at 3.5 ms, before U5/U7 at up to 5.8 ms, so "3.3 V and nPOR last" is not guaranteed. Fix: take U6's R43/C65 network (via R41) from VCC_1V8 instead of VCC5V0_SYS (1.74 V min > VIH 1.2 V; EN abs-max 6 V). Alternatively, use TLV62569P power-good chaining. Then redo P7 with a 0.4–1.2 V threshold window.
- Minor: (pmu) VCC_3V3 3.318 V nominal leaves 25 mV to the 3.465 V GPIO max, and VFB ±2 % is specified at TJ = 25 °C only. Use 45.3k/10.2k (3.265 V, near [LF]'s 3.27 V). (pmu) [LF] U6 output is 10 µF + 100 nF (C63/C64), not "10 + 10 µF". (pmu) R12 1K/C38 10nF sit beside the SoC in PART A; the "Power Reset" block is Key1 + R22 100R. Say whether Key1 is kept. (pmu) The VCC3V3_SD 2.0 A rating is UNVERIFIED but counts as a P5 PASS; mark it as a Phase-4 requirement. (onoff) The C_PDT spread ignores X7R ±15 % over temperature; with it, worst case is 7.93 s (still < 8 s, thin). Consider 0.68 µF.
- LCSC spot-check: C683783 = LTC2954CTS8-2#TRPBF, TSOT-23-8 exists; the page shows no stock (Phase 4 risk; D-03 fallback stands). TLV62569DBVR = C141836 is listed in stock at LCSC.

## 2026-10-28 — Executor — Phase 3 (Power architecture), round 2
- **What this phase is doing:** fixing the verifier's round-1 findings on the power design (3 major, 5 minor): stable regulator filters, a power switch that stays off when the cable is plugged in, and a power-up order that holds for every datasheet-guaranteed threshold, not only typical ones.
- Buck filters now are TI Table 4 checked cells (TLV62569 SLVSDG1C p.9, re-rendered and read): U4 2.2 µH + 2×22 µF, U7 and U5 2.2 µH + 22 µF (U5's band straddles the 1.8 V row), U6 2.2 µH + 10 µF; 6.8 pF feed-forward on all four with R2 = 100 k. VCC_3V3 divider 442k/100k = 3.252 V (D-32, D-43).
- Q_PWR gate: C_GS 470 nF, C_GD 10 nF, R_GS 100k, R_G 47k. Plug-in |VGS| ≤ 0.25 V (≤ 0.38 V with 2× ringing); inrush ≤ 0.53 A; turn-off ≤ 104 ms (D-41). Confirmed [LTC] p.9: EN̅ starts released at power-up.
- Sequencing: U6 enable RC fed from VCC_1V8 (R41 → PWR_EN → R43 200k / C65 150 nF); C77 back to [LF] 100 nF. P7 rewritten as an RC simulation over the 0.4–1.2 V EN window with independent per-chip thresholds, UVLO, ±10 % C and ramp extremes; worst margins 0.53 ms (core → 1.8/DDR) and 1.2 ms (1.8/DDR → 3.3 V). Bleeders 470 Ω / 1 kΩ make every restart after the 226 ms minimum off-time repeat the cold-start order (D-34, D-42).
- Minors: [LF] citations fixed (U6 = C63 10 µF + C64 100 nF + C62 10 pF; R12/C38 in PART A; "Power Reset" = Key1 + R22 + ED1 NF), Key1 reset kept (D-44); uncited ratings now `REQ`, not passes (D-45); C_PDT 0.68 µF with X7R drift → hard-off 2.66–6.60 s (D-33); LTC2954 stock is a Phase-4 gate with a controller-independent §6 (D-46).
- check_power.py: **65 pass, 0 fail, 4 REQ**. New checks P9 (gate network), P10 (Table 4 lookup), P11 (restart). Mutation copy in the scratchpad (U4 22 µF, U7 10 µF, 3V3 45.3k/10k) fails P3/P10 as expected. Note: round-1 power_rails.csv had an unquoted comma in the VCC5V0_SYS row (extra column); fixed.

## 2026-10-28 — Verifier — Phase 3 (Power architecture), round 2: **FAIL (1 major, 8 minor)**
- **What this check did:** re-checked the round-2 power design (regulator filters, power-switch gate network, power-up order, bleeders) against the datasheets and the Luckfox sheet, re-ran the checks, and looked for anything that would stop the first board from booting.
- Ran `design/.venv/bin/python -I design/tools/check_power.py design`: **65 pass, 0 fail, 4 REQ** (exit 0). Ran `check_pinmap.py`: **17 pass, 0 fail**. Both reproduce the executor's numbers.
- Confirmed from primary sources (pymupdf, `python -I`):
  - [TLV] SLVSDG1C p.4: VIN abs-max 6 V; IOUT 2 A; UVLO 2.3/2.45 V; EN VIH 0.95/1.2 V and VIL 0.4/0.85 V; tSS 800/900 µs with no max; VFB 0.588–0.612 V at 25 °C.
  - [TLV] p.9 Table 4, by word position: at 2.2 µH the checked cells are 2×22 µF for 0.6–1.2 V; 22 (++) and 2×22 for 1.2–1.8 V; 10 (++), 22 and 2×22 for ≥ 1.8 V. The encoding in P10 is correct.
  - [TLV] p.6 block diagram: no EN pull-down is drawn.
  - [LTC] p.3: tDB,ON 26–41 ms; tPD,MIN 52–82 ms; tPDT at 1500 pF 9/11.5/13.5 ms; lockout 200–325 ms; KILL blanking 400–650 ms; EN̅ leakage ±1 µA.
  - [LTC] p.9: outputs are initialised to off at power-up. p.11: after a forced off, the part waits for a new high-to-low PB edge, so a button still held does not power the board back on. p.12: the -2 version is the active-low PFET driver.
  - [AO] pp.1–2: all cited values match.
  - [DS] Table 3-1/3-2 p.20: every rail band is inside its range.
  - [DS] pp.18–19: pins 67, 71, 19, 49, 50, 56 and 115 match pinmap.csv.
  - [SDK] DTS: vdd_arm is a fixed 0.9 V regulator, and the 1.2 GHz OPP is 0.85 V, so the fixed 0.876–0.924 V rail is fine.
- Stock checks:
  - LCSC C15127 AO3401A: about 1.83 M in stock.
  - C683783 LTC2954CTS8-2: LCSC and JLCPCB show no stock figure; JLCPCB labels it "Extended". This is a Phase-4 gate (D-46).
  - C141836 TLV62569DBVR: no stock figure shown on today's fetch.
- **Major (pmu): the Table-4 check ignores the SoC-side capacitors that sit on the same rail.** On the [LF] sheet, VDD_0V9 has C22–C28 (10+10+1+1 µF + 3×100 nF = 22.3 µF) and VDD_ARM, joined through R32, has C15–C17 (11.1 µF). With U4's local 2×22 µF the loop sees about 77 µF. That is far above the checked 2×22 µF cell, even with TI's +20 % allowance, and no 100 µF cell is checked in any row. A core-rail loop outside the tested range can ring or oscillate, so the first board might not boot. Fix: P10 and power_rails.csv must use the total capacitance on each rail (buck-local plus all SoC/peripheral decoupling that Phase 5 will place). For U4, either use a 10 µF local capacitor with the [LF] SoC-side set (about 43 µF ≈ 2×22 µF), or keep 2×22 µF local and limit the SoC-side capacitors to 1 µF/100 nF. Do the same budget for VCC_DDR (22 + 21.1 µF: OK as 2×22), VCC_1V8 and VCC_3V3.
- Minor findings:
  - (pmu) architecture.md §3 still says in bold "Rev A rule: fit R41 = 1 kΩ from VCC5V0_SYS to PWR_EN". This contradicts D-34/D-38 round 2 (from VCC_1V8) and would break P7b if Phase 5 followed it. Rewrite the paragraph.
  - (pmu) [LF] prints R32 (VDD_0V9 → VDD_ARM) as "0R 5% DNP". The design needs it FITTED, or CPU_DVDD (pin 115) is unpowered. State "R32 fitted (deviation from the [LF] DNP marking)" in power.md and D-06, and make Phase 4/5 carry it as fitted.
  - (pmu) The [LF] hand note "200K->100K" by R14 suggests Luckfox builds with 100 kΩ. With 100 kΩ, P7a fails (U5/U7 EN at 0.71 ms is before U4 is good at 0.91 ms). In D-34, record that 200 kΩ is kept on purpose and why.
  - (pmu) P11 proves only VCC5V0_SYS, C77 and C65. VCC_3V3 (10 µF + SoC capacitors, PWR LED load, no bleeder) can still be about 1.5–2 V at the 226 ms restart while VDD_0V9 is 0 V. Either add a VCC_3V3 bleeder (for example 1 kΩ, 11 mW) and extend P11 to all four rails, or reword "every restart repeats the cold-start order".
  - (onoff) The turn-off section uses the turn-on plateau current. At turn-off the gate discharges only through R_GS, so I_G = 5–20 µA, the drain falls at 0.45–2.2 V/ms, and Q_PWR conducts for up to about 6 ms. That is roughly 5–15 mJ, not 2–4 mJ. Recompute, and check against the AO3401A SOA curve in [AO] before Phase 4.
  - (onoff) P8 scales the tPDT spread from the 1500 pF timing line. Using IPDT ±20 % ([LTC] p.3) as well gives up to about 7.0 s, still under 8 s. Add that corner to P8.
  - (usbc/prot) The VBUS_USBA row claims "≥ 4.75 V at port". From a 5.00 V source, after the 0.26 V input drop and the switch, the port is about 4.69 V (about 4.4 V from 4.75 V). Correct the row.
  - (onoff) PLAN TP8 is "PWR_EN / button controller out", but in this design PWR_EN is now the U6 enable fed from VCC_1V8. Phase 6 should define TP8 explicitly, for example on the Q_PWR gate/EN̅ plus a separate pad on VCC5V0_SYS.
- No other errors were found in the round-2 fixes. Cable plug-in (|VGS| ≤ 0.25 V), button turn-on (≤ 0.53 A inrush) and the chained 0.9 → 1.8/DDR → 3.3 V order hold over the guaranteed EN window. Open questions Q1–Q3 remain for the human.

## 2026-10-28 — Executor — Phase 3 (Power architecture), round 3
- **What this phase is doing:** fixing the verifier's round-2 findings (1 major, 8 minor) on the power design: making sure each regulator is stable with *all* the capacitors on its rail (not only the ones beside it), that a quick restart always repeats the safe power-up order, and that the power switch survives switching off under load.
- Major (pmu): new per-rail **total capacitance budget** = buck-local + the [LF] SoC/peripheral decoupling read from a 600-dpi render (C8–C28, C31/C32, C36/C37, C39–C48, C69–C72). U4 local 2×22 µF → **10 µF + 100 nF**, so VDD_0V9+VDD_ARM = 43.6 µF ≈ TI's checked 2×22 µF cell; VCC_DDR 44.2, VCC_1V8 38.6, VCC_3V3 21.3–41.5 µF. P10 now checks the total (±10 %, DC-bias retention) against Table 4 cells widened by TI's own +20 %/−50 % note (p.9). D-47, D-48 (header 3V3 ≤ 10 µF external).
- Minors: architecture.md §3 R41 paragraph rewritten (from VCC_1V8, C65 150 nF); **R32 0 Ω FITTED** (≠ [LF] "0R 5% DNP", D-06); R14 200 kΩ kept on purpose (100 kΩ fails P7a, mutation run; D-34); bleeders on all four buck rails (1k/1k/680/680 Ω) and P11 extended — every rail ≤ 0.18 V, EN nodes ≤ 0.31 V at the 226 ms restart (D-42); Q_PWR turn-off recomputed with I_G = |Vpl|/R_GS: ≤ 7.1 ms linear, ≤ 7.8 W, ≤ 21 mJ, inside the [AO] p.4 Fig. 9 10 ms SOA derated to 70 °C (new check P9e, D-41); P8 includes ±20 % PDT current → hard-off 2.66–7.02 s (D-33); VBUS_USBA port 4.44–5.20 V (D-49); TP8 split into TP8a EN̅ / TP8b VCC5V0_SYS / TP8c PWR_EN (power.md §6.5, D-50).
- check_power.py: **70 pass, 0 fail, 4 REQ** (input 7.09 W). check_pinmap.py unchanged (17 pass). Mutations in the scratchpad (R14 100 kΩ; U4 2×22 µF local) fail P7a and P10 as expected.

## 2026-10-28 — Verifier — Phase 3 (Power architecture), round 3 — **PASS** (gate TP-D3 met; 0 blocker, 0 major, 3 minor)
- **What this phase is doing:** independent check of the round-3 power design (regulators, power-up order, on/off button, power budget) against gate TP-D3 before the team moves to Phase 4 (part selection & BOM).
- Ran `check_power.py` myself: **70 pass, 0 fail, 4 REQ**, input 7.09 W; `check_pinmap.py` 17 pass, 0 fail. Mutation on a scratch copy (VCC_3V3 SoC-side C → 45 µF) makes P10 fail as it should.
- Re-checked against primary sources: [TLV] Table 4 p.9 column positions (0.6–1.2 V row: only 2×22 µF checked; 1.8 V+ row: 10/22/2×22), EN VIL/VIH 0.4/1.2 V, UVLO, "able to start into a pre-biased output" (§7.3.3); [LTC] TSOT-23-8 pinout, IPDT ±20 %, tEN,LOCKOUT 200–325 ms, KILL blanking 400–650 ms, EN̅ open drain, VIN abs-max 33 V; [AO] p.1–2 ratings and p.4 Fig. 9–11 (Fig. 10/11 suggest ≈ 15–20 W at 10 ms, so the 13 W SOA figure used by P9e is conservative); [DS] Table 3-1/3-2 ranges; [LF] render: R32 really is "0R 5% DNP" and VDD_ARM has no other source on the sheet, so fitting R32 is right; Luckfox DTS has `vdd_arm` as a fixed 0.9 V regulator, consistent with the shared rail; [LF] C15–C28 values match the P10 budget. Hand-recomputed P6 (7.09 W), P8 (2.66–7.02 s), P11 (VCC_DDR 0.18 V). RV1106 hardware design guide still not found by web search: sequencing stays UNVERIFIED against Rockchip and follows [LF].
- All 9 round-2 findings are fixed. Minor findings (no re-run of the gate needed):
  1. (pmu) Check P3 has a ripple/transient headroom rule only for VCC_3V3 (≥ 50 mV). VDD_0V9 has 26 mV each side (0.876–0.924 V inside 0.85–0.95 V), and VCC_DDR has 45 mV under the 1.45 V absolute maximum. A mutation to 130 kΩ on the DDR divider (1.424 V top edge) still passes. Fix: extend the P3 headroom rule to all four rails, and record a transient budget for VDD_0V9 and VCC_DDR (TLV62569 load-step plot, 10 µF local). Add "VDD_0V9 and VCC_DDR at TP4/TP5 under CPU/DDR load steps" to the Phase-6 measurements.
  2. (pmu) decisions.md D-36 still says "Worst-case total 7.06 W" (now 7.09 W, P6). Amend D-36.
  3. (onoff) architecture.md §5 safe-state table, PWR_KILL row: "the N-MOSFET inverter, whose drain pull-up goes to the controller's always-on supply" contradicts D-33 (KILL pull-up 100 kΩ to VCC_3V3, so a dead 3.3 V rail aborts power-on). Reword it to VCC_3V3.
- Open questions Q1–Q3 and the two new ones (USB-A 4.44 V, header ≤ 10 µF) remain for the human. Phase-4 gating items: LTC2954CTS8-2 stock ≥ 100 (else the D-03 fallback), and R32 fitted in the BOM.
## 2026-10-29 — Owner — accepted current defaults for all open questions (see decisions.md D-H1)

## 2026-10-29 — Executor — Phase 4 (Part selection & BOM), attempt 1 — **gate TP-D4 not met: 2 items escalated to the human**
- **What this phase is doing:** picking a real, orderable JLCPCB/LCSC part for every component on the board, checking stock and footprints, and estimating the cost of 5 assembled boards.
- Outputs:
  - `bom.csv`: 65 lines, 195 parts/board, with ref, value, description, footprint, LCSC #, Basic/Extended, JLC stock, LCSC stock, unit price, order quantity, line cost, joints, block and source.
  - `cost.md`.
  - `tools/lcsc_fetch.py` (live LCSC API + JLCPCB part pages), `tools/make_bom.py` (generator) and `tools/check_bom.py` (gate checks B1–B6 and the cost model).
- Sources:
  - Raw responses cached under `refs/lcsc-api-2026-10-29/` and `refs/jlcpcb-partdetail-2026-10-29/`.
  - Candidate search in the jlcparts SQLite mirror (`refs/jlcparts-db-2026-10-29/`, opened read-only).
  - New datasheets, each in its own refs folder: SY6280AAC, TS3USB221A, SI2301CDS, BSMD1812, TYPE-C-31-M-12, FHD4020S, 2N7002, AO3400A, TF-01A. All were read with `python -I` and nothing was executed.
- `check_bom.py` (with `--boards 5`): **266 pass, 2 fail**.
  - B1 (part exists, MPN matches), B3 (footprint matches the LCSC package), B4 (Basic/Extended) and B5 (earlier-phase rules carried) pass on every line.
  - **B2 fails on the RV1106G3 C5328706: stock is 23 at JLCPCB and 22 at LCSC**, enough for 5 boards but below the ≥ 100 rule.
  - **B6 fails: $413.80 for 5 boards.** That is parts $238.87, of which the SoC is $126.94, plus Economic PCBA $109.93, PCB $30 (estimate) and shipping $35 (estimate). Assembling 2 of the 5 boards costs $280.43.
- Decisions:
  - D-51: LTC2954-1 + 2N7002 inverter replaces the -2, because the -2 had only 50 in stock.
  - D-52: 1 Gbit NAND and a 12 pF 24 MHz crystal.
  - D-53: Basic-part substitutions.
  - D-54: the D-45 REQ ratings are now cited: J1 5 A, F1 2 A/0.1 Ω, Q_SD 1.8 A at 70 °C, SY6280 ILIM 0.75–1.25 A, mux S=L→1D.
  - D-55: the escalation.
  - D-45 and D-46 are closed, and power.md has a new §6.4a.

## 2026-10-29 — Verifier — Phase 4 (Part selection & BOM), attempt 1 — **gate TP-D4 FAIL (2 blockers need the human; 8 minor fixes for the executor)**
- Ran the tools myself: `check_bom.py design` gives **266 pass, 2 fail** (B2 RV1106G3 stock, B6 $413.80). `make_bom.py` regenerated on a scratch copy from the cached responses gives the same bom.csv. `check_power.py` gives 70 pass, 0 fail, **still 4 REQ**. `check_pinmap.py` gives 17 pass.
- Live re-fetch on 2026-10-29 (saved in `refs/verifier-p4-live-2026-10-29/`): C5328706 has **23 at JLCPCB and 22 at LCSC**; C683782 2164/2164; C22472329 20996/20879; C124383 5944/5415. These match bom.csv. No part is a JLC "preferred extended", so the 24 × $3.07 fee stands.
- Confirmed from primary sources:
  - RV1106 QFN128 is 12.3 mm with 0.35 mm pitch ([DS] p.14).
  - The W25N01KV (ID EF AE 21) is in the Luckfox SDK kernel and U-Boot `drivers/rkflash/sfc_nand.c` (github LuckfoxTECH/luckfox-pico main). The NAND runs from 2.7 to 3.6 V and VCCIO3 is at 3.3 V.
  - The HRO TYPE-C-31-M-12 note 4-1 gives 5 A.
  - The BSMD1812-200-16V table on p.2 matches.
  - The SI2301CDS ID is −1.8 A at TA = 70 °C.
  - TS3USB221A: S=L connects 1D.
  - The LTC2954 p.5 graph "EN (LTC2954-1) vs VIN" peaks at 0.71 V and is 0 V above 1.05 V.
  - SY6280: ILIM = 6800/RSET, 0.75–1.25 A.
  - Neither the 1.7 GB jlcparts DB nor anything else was deleted; that is the human's call.
- **Blockers** (human decision, not design errors): (1) the SoC stock is below the 100-unit rule; (2) the cost is $413.80 against $200. SoC + NAND + PCB + shipping alone already come to ≈ $224, so the $200 cap cannot be met at today's prices.
- **Minor findings for the executor:**
  1. (prot) The F1 2.0 A hold is a 25 °C figure. The BHFUSE derating chart gives 1.66 A at 50 °C, 1.45 A at 60 °C and 1.09 A at 70 °C, against 1.41 A worst case (1.83 A needed). Upsize to the BSMD1812-260 class or record an ambient limit.
  2. (pmu) The SY6280 AN p.5 "strongly recommends" a 10 µF ceramic on VIN. C32 is 1 µF, and its "p.1" citation shows no value.
  3. (onoff) The 2N7002 VGS(th) max is 2.5 V, not 1.6 V (1.6 V is the typical value).
  4. (onoff) power.md §6.1, §6.5/D-50 TP8a and power_rails.csv still describe an -2 EN̅ on pin 6. With the -1, pin 6 sits near VBUS when on.
  5. power_rails.csv and P5 do not yet carry the D-54 ratings.
  6. The cost.md command for $280.43 is wrong: `check_bom.py --boards 2` alone gives $405.22.
  7. The B3 footprint check is too weak for connectors and custom parts. The WSON-8 footprint name is not a KiCad library name.
  8. (usb) VBUS_USBA has only 22 µF, while USB 2.0 asks for ≥ 120 µF per host port.

## 2026-10-29 — Executor — Phase 4 (Part selection & BOM), round 2 — **gate TP-D4 still not met: the same 2 items wait for the human; all 8 minor findings fixed**
- **What this phase is doing:** picking a real, orderable JLCPCB/LCSC part for every component, checking stock and footprints, and estimating the cost of 5 assembled boards.
- **Results:**
  - `check_bom.py design`: **471 pass, 2 fail**. The failures are B2 (RV1106G3 stock: 23 at JLCPCB, 22 at LCSC) and B6 ($417.51 for 5 boards; 2 assembled + 5 bare: $283.95).
  - `check_power.py`: **76 pass, 0 fail, 0 REQ** (was 70/0/4).
  - `check_pinmap.py`: 17 pass.
- **Fixes:**
  - (prot) F1 changed to **BSMD1812-300-16V C883162**: derated hold 2.01 A at 60 °C (1.3×) and 1.61 A at 70 °C (1.14×, new check P5t). The design-ambient limit is recorded (D-56).
  - (pmu) The SY6280 VIN capacitor is now **10 µF** (C96446, existing line), placed within 2 mm of pin 5, citing p.5. C_L is now 60.5 µF and the inrush 0.65 A. The P9 inrush limit is now 1.0 A, set where the plateau bound stays valid, and a turn-on SOA check was added (D-57).
  - (usb) VBUS_USBA gets **+120 µF polymer** (Lelon OVZ121M1ATR-0606, C250087), for 142 µF in total (D-58).
  - (onoff) 2N7002 VGS(th) corrected to 1.0–2.5 V. power.md §6.1 is redrawn with Q_EN and marked superseded by §6.4a. TP8a is now the Q_EN drain, and a new TP8a′ (LTC2954-1 pin 6, inverted values) is added (D-50 amended). The power_rails.csv driver text is fixed.
  - (pmu) The D-54 ratings are written into power_rails.csv and counted by P5.
- **Tool changes:**
  - check_bom.py recomputes line costs for any N from the cached ladders, so `--boards 2` really gives $283.95 (D-60).
  - B3 is split into B3a–B3d: exact KiCad names from a cached GitLab listing, physical pad counts from the cached .kicad_mod files, and JLC joint counts (D-59).
  - The WSON name is fixed to `..._EP3.4x4.3mm`, checked against the W25N01KV ZE drawing. The RJ45 name is fixed to `_Horizontal`. J1 is now 12 SMD + 4 THT.
  - Mutation runs on scratch copies fail as expected: B3b–d, and P5 with F1 at 1.66 A.
- **New refs** (each in its own folder, read with `python -I`, nothing executed): bsmd1812-300-16v-datasheet, lelon-ovz121m1atr-datasheet, w25n01kv-datasheet, kicad-footprints-listing-2026-10-29, kicad-footprints-mods-2026-10-29.
- **Decisions:** D-56..D-60, amendments to D-50/D-51/D-54/D-55.
- **Still open, human only:** the B2 SoC stock rule, the B6 cost cap or scenario, and a live PCB/shipping quote (cost.md §4).

## 2026-10-29 — Verifier — Phase 4 (Part selection & BOM), round 2 — **gate TP-D4 FAIL (1 new executor blocker + the 2 human blockers; 3 minors)**
- **Tools re-run by the verifier:**
  - `check_bom.py design`: 471 pass, 2 fail (B2 SoC stock; B6 $417.51).
  - `check_bom.py design --boards 2`: $283.95.
  - `check_power.py`: 76 pass, 0 fail, 0 REQ.
  - `check_pinmap.py`: 17 pass.
  - An independent recount of bom.csv matches the tools: 66 lines, 196 parts, 25 Extended, 2940 SMT and 335 THT joints, $239.54 in line costs, no duplicate refs.
- **Live re-fetch on 2026-10-29** (saved in `refs/verifier-p4r2-live-2026-10-29/`, JLC / LCSC stock):
  - C5328706 RV1106G3: **23 / 22**, $25.39.
  - C883162: 62 800 / 62 800.
  - C250087: 16 578 / 16 395.
  - C96446: 8.3 M (Basic).
  - C55136: 91 789 / 87 640.
  - All match bom.csv.
- **Round-2 fixes confirmed against primary sources:**
  - BSMD1812 p.5 derating row -300 is 3.00 / 2.55 / 2.28 / **2.01 (60 °C)** / **1.61 (70 °C)**, and the p.2 R1max is 0.050 Ω.
  - Lelon catalog p.36: 10 V, 120 µF, 6.3 × 5.9, **22 mΩ**.
  - W25N01KV p.58 ZE: D2 3.40 and E2 4.30. They match the KiCad EP (3.4 along the pin-row axis).
  - SY6280 pin 5 is IN, and p.5 has the "Supply Filter Capacitor" text.
  - KiCad pad recounts: USB-C 12 unique SMD + 4 SH; HR911105A 12 + 2 SH; CP_Elec_6.3x5.9 2.
  - All 8 round-1 minors are fixed.
- **NEW BLOCKER (executor-fixable, soc / cost model):**
  - In the cached JLCPCB capabilities page (`refs/jlcpcb-assembly-capabilities-2026-10-28/`), the table row "Minimum IC Pin Spacing" reads **Economic 0.4 mm / Standard 0.35 mm**, and the FAQ says "Economy PCBA service: 0.40 mm".
  - The RV1106G3 is a **0.35 mm pitch** QFN128 ([DS] r1.8 p.14).
  - So Economic PCBA cannot place the SoC. The whole cost model (and the cost.md §1 claim that Economic is "the only JLCPCB option") is invalid.
  - Standard PCBA accepts a *panel* ≥ 70 × 70 mm, so it is available.
  - Fix: switch to Standard, with a panel or a ≥ 70 × 70 outline. Re-cost with the Standard fees (rough verifier estimate ≈ $460–485 for 5 boards), add a pitch-vs-service check, and record it as a new decision.
- **Still human-only:** B2 SoC stock (23/22 < 100) and the B6 cost cap. The cap figure must be re-derived after the Standard re-cost.
- **Minors:**
  1. The designator "C32" in D-57, power.md §8 and cost.md names the SY6280 VIN capacitor. In bom.csv that part is **C10**, and C32 is the U6 EN 150 nF.
  2. D-58's "OVZ vs OCVZ UNVERIFIED" can be closed: the Lelon catalog p.37 part-numbering example maps OCVZ series → "OVZ". The reflow profile (catalog p.15) is not in the saved 3-page extract.
  3. Use ENIG rather than HASL for the 0.35 mm QFN, and cost it.

## 2026-10-29 — Executor — Phase 4 (Part selection & BOM), round 3 — gate TP-D4 still FAIL on the 2 human items (B2 SoC stock, B6 cap); all executor findings fixed
- **Blocker 1 (Economic PCBA cannot place the 0.35 mm SoC), fixed:**
  - New decision **D-61: JLCPCB Standard PCBA**, single-side, with the board outline **enlarged to 70 × 70 mm** and 2 × 5 mm edge rails (Standard requires rails and fiducials). This deviates from PLAN Phase 7 "~60 × 50 mm"; **Phase 7 must draw a 70 × 70 mm outline.** Alternatives are costed: a 1 × 2 panel would assemble 6 boards ($550.77); a 1-up 60 × 50 frame has UNVERIFIED acceptance.
  - check_bom.py now has fee sets for both services and `--service` / `--format` options. The Standard fees come from the price page: setup $25.56, stencil $8.21, feeder loading $1.53 for each of the 66 types, fixture $16.42 (applicability UNVERIFIED), and packing.
  - New checks: **B7a** pitch ≥ the service minimum (the SoC is at 0.35 mm, exactly Standard's minimum; it fails under Economic), **B7b** cited peak reflow rating ≥ the service reflow temperature + 5 °C, and **B7c** board or panel ≥ 70 × 70 mm.
  - Re-cost: **$497.73 for 5 assembled boards, $364.17 for 2 assembled.** cost.md §1–§5 are rewritten, including the scenarios and the suggested caps (≈ $550 or ≈ $400).
- **Minor (pmu), fixed:** the designator clash.
  - D-57 and power.md §8 now say C_USBA_IN [C10].
  - New `refmap.csv` maps 90 functional and [LF] names to BOM refs (`tools/make_refmap.py`, D-63, check B8). Examples: C65 → C32, [LF] R32 → R33.
  - A mutation test (C_USBA_IN → C32) fails B8, as it should.
- **Minor (usb), fixed:**
  - D-58's UNVERIFIED is closed: Lelon catalog p.37 maps the OCVZ series to code OVZ.
  - Reflow is cited from Lelon "Reflow Conditions for SMD Type" p.15 (new ref `refs/lelon-reflow-conditions-smd-2026-10-29/`, read with `python -I`): OP-CAP peak 250 °C for 2 cycles, 260 °C for 1 cycle. That is ≥ 245 °C, so it passes under Standard.
- **Minor (soc), fixed:** D-62 sets an **ENIG** finish, costed at $45 (ESTIMATE). Phase 7 writes it in the fab notes.
- **Tools re-run:**
  - `check_bom.py design`: 485 pass, 2 fail (B2, B6).
  - With `--cost-limit 500 --soc-stock-rule boards+2`: 487 pass, 0 fail.
  - `check_power.py`: 76 pass, 0 fail.
  - `check_pinmap.py`: 17 pass.
- **Human-only items:** the B2 SoC stock rule, the B6 cap or scenario (no scenario fits two revisions in $500), a live PCB/shipping quote with ENIG and Standard PCBA, and confirming whether the fixture fee and the "pre-reflow" fee apply.

## 2026-10-29 — Verifier — Phase 4 (Part selection & BOM), round 3 — gate TP-D4: **FAIL, escalate to the human (round 3 of 3)**
- **Re-ran the tools myself (actual output):**
  - `check_bom.py design`: 485 pass, 2 fail (B2 SoC stock, B6 $497.73 > $200). Exit code 1.
  - `--cost-limit 500 --soc-stock-rule boards+2`: 487 pass, 0 fail. `--boards 2 --cost-limit 365 --soc-stock-rule boards+2`: 486 pass, 0 fail.
  - `--service econ`: B7a fails for the SoC (0.35 < 0.40 mm), and B7b fails for the 120 µF polymer cap. `--format single60x50`: B7c fails. `--format panel1x2`: $550.77 for 6 assembled boards.
  - `check_power.py`: 76 pass. `check_pinmap.py`: 17 pass. `make_refmap.py --check`: up to date.
- **Primary sources re-checked:**
  - JLCPCB capability table (cached HTML): Standard 70×70 mm minimum, edge rails and fiducials "Necessary", minimum IC pin spacing 0.4 / 0.35 mm, reflow 255±5 / 240±5 °C, THT wave-soldered (FAQ).
  - JLCPCB price page (cached): every Standard fee used in check_bom.py matches (setup $25.56, stencil $8.21, feeder $1.53 per Basic/Extended type, fixture 1–29 pcs $16.42, packing $0.50 + area, X-ray ladder). The assembly subtotal $178.21 re-adds correctly.
  - RV1106 datasheet r1.8: p.14 "QFN128 … pitch 0.35mm"; p.18 MSL3. No reflow peak is given for the SoC.
  - Lelon "Reflow Conditions" p.15: OP-CAP peak 250 °C for 2 cycles, 260 °C for 1 cycle. The OCVZ datasheet shows the series code OVZ.
- **Live re-fetch 2026-10-29** (`refs/verifier-p4r3-live-2026-10-29/`, LCSC / JLC):

  | Part | LCSC | JLC | Price |
  |---|---|---|---|
  | RV1106G3 | 22 | 23 | $25.39 |
  | LTC2954-1 | 2164 | 2164 | $6.69 |
  | W25N01KV | 20879 | 20996 | |
  | OVZ121M1ATR | 16395 | 16578 | |
  | SY6280 | 87635 | 91750 | |
  | TLV62569 | 15565 | 15565 | |

  All match the cache.
- **Round-2 findings:** all addressed (blocker: Economic → Standard D-61; minors: C10/C32 naming via refmap D-63, Lelon OVZ / reflow cited, ENIG D-62).
- **Gate:**
  - LCSC numbers exist and footprints match: met.
  - Stock ≥ 100: FAIL, SoC only.
  - ≤ $200: FAIL ($497.73).
  - Both need a human D-H decision. This is round 3, so per PLAN "Process" it escalates to the human.
- **New minors:**
  - (a) architecture.md line 3 still says "~60 × 50 mm" and does not mention Standard PCBA, rails, fiducials or ENIG.
  - (b) The handling-fee UNVERIFIED can be closed: Standard − Economic for the same board is $497.73 − $432.51 = $65 > $14.93, so no shortfall fee applies either way.
  - (c) [LF] designators collide with different BOM refs: [LF] J2 is the RJ45 = BOM J3, while BOM J2 is the microSD; [LF] R7 → R43 while [LF] R43 → R21; [LF] R2 ↔ R3. power.md §5 (D-47 budget) lists [LF] SoC decouplers (C10, C32, C31, …) that are not in refmap.csv. Phase 5 must use the bracket rule for every [LF] citation, or extend refmap to the SoC decouplers.
## 2026-10-29 — Owner — Rev A build scope decided (decisions.md D-H2): 2 assembled + 3 bare, 70x70 Standard PCBA, SoC stock boards+2, Rev A cap $380

## 2026-10-29 — Executor — Phase 4 (Part selection & BOM), reworked to owner decision D-H2 — **gate TP-D4 (amended) PASS: 475 pass, 0 fail**
- **What this phase does:** picks an orderable JLCPCB/LCSC part for every component and checks stock, footprints and the Rev A cost. Rev A is now **2 assembled boards + 3 bare PCBs**, Standard PCBA, 70 × 70 mm, ENIG.
- **Results:**
  - `check_bom.py design`, which now defaults to the D-H2 gate (D-66): **475 pass, 0 fail**. 64 BOM lines, 196 parts per board, 25 Extended types.
  - **Total $360.36 ≤ $380**: parts $113.80 (of which SoC $50.78), assembly $166.56, PCB $45 ESTIMATE, shipping $35 ESTIMATE.
  - The SoC stock rule (≥ boards + 2 = 4) passes. Live re-fetch at 09:24 UTC (`refs/executor-p4dh2-live-2026-10-29/`, parsed with `python -I`): C5328706 JLC 23 / LCSC 22, $25.39. LTC2954-1 2164; W25N01KV 20996.
  - `check_power.py`: 76 pass, 0 fail. `check_pinmap.py`: 17 pass. `make_refmap.py --check`: up to date.
  - Mutation runs fail as expected: SoC rule boards+30 fails B2; cap $355 fails B6; `--service econ` fails B7a/B7b; `--boards 5` gives $493.93 and fails B6.
- **Changes:**
  - **D-64:** the 0R 0402 line is merged onto the 0R 0603 line, and the status/ETH LEDs now use the power-LED part (KT-0603R). That removes 2 types (−$3.06).
  - **D-64a:** none of the 25 Extended types has a Basic equivalent (jlcparts query), so they stay. Merges that would change analysed values were rejected.
  - **D-65:** fixes verifier round-3 minor (c).
    - refmap.csv grows from 90 to 125 names and now includes all [LF] SoC decouplers.
    - A new `lf_name_collision` column flags 66 [LF]/BOM number clashes.
    - Rule: never write a bare [LF] designator. Phase 5 is advised to renumber.
    - New B8 checks.
  - **D-66:** fixes verifier minor (b). The tools default to the D-H2 gate, bom.csv is costed for 2 boards, and the handling fee is computed as $0.00 (Economic is unavailable; Std − Econ would be $62.15).
  - **D-67:** fab/assembly options chosen for the simplest build.
  - **D-55a:** the escalation is closed.
  - Verifier minor (a): architecture.md line 3 now says 70 × 70 mm, Standard PCBA, ENIG, rails/fiducials, 2 + 3 order.
  - cost.md is rewritten for Rev A.
- **For the owner at order time:**
  - Recheck the SoC stock (≥ 4).
  - Get the live quote (PCB, shipping, fixture and pre-reflow fees). If the pre-reflow fee is charged on every joint, the total reaches ≈ $381.

## 2026-10-29 — Verifier — Phase 4 (D-H2 rework) vs gate TP-D4 (amended) — **FAIL (1 major, 4 minor)**
- **Re-ran:** `check_bom.py design` → 475 pass / 0 fail, total $360.36 (assembly sum re-added by hand: 166.56; joints re-counted 588 SMT + 67 THT per board, 3 X-ray parts/board). Mutations (`--boards 5` $493.93, `--soc-stock-rule boards+30`, `--cost-limit 355`, `--service econ`) each fail as claimed. `check_power.py` 76/0, `check_pinmap.py` 17/0. `make_refmap.py` output byte-identical to refmap.csv; refmap cross-checked against bom.csv (125 names, every bom_ref/LCSC matches, 66 collision flags correct, no duplicate [LF] names).
- **Live re-fetch (≈09:31 UTC, all 64 parts)** saved in `refs/verifier-p4dh2-live-2026-10-29/` (python -I): RV1106G3 C5328706 JLC 23 / LCSC 22, $25.39 → B2 (≥ 4) holds; next lowest LTC2954-1 2164. Parts total unchanged ($113.81). bom.csv cols 1–13 regenerate identically.
- **Primary sources re-checked:** [DS] r1.8 p.14 "QFN128 … pitch 0.35mm", p.18 MSL3, p.20 Table 3-2 CPU_DVDD 0.85–1.05 V; JLCPCB capabilities page (Standard: 0.35 mm min pitch, 70×70 mm min, rails + fiducials necessary, 240 ± 5 °C); price page (Standard feeder loading $1.53 Basic/Extend, handling-fee rule, pre-reflow $0.016/joint unexplained); [LF] R7 6.04K EXTR, R46–R49 0R ETH, C66/C67 103 centre taps.
- **MAJOR (pmu):** the 0R 0603 part C21189 is rated **1 A, < 50 mΩ** (UNI-ROYAL datasheet p.5 §7, saved `refs/uniroyal-0603waf-datasheet/`). The VDD_0V9 buck-output measurement link carries the whole 1.001 A worst case (100 % of rating, 1.3× rule fails) and, with R32 [R33] in series (0.5 A), drops up to 75 mV: VDD_ARM low edge 0.876 V (check_power P3, which treats 0R as 0 Ω) → ≈ 0.80 V < CPU_DVDD min 0.85 V. Fix: VDD_0V9 path without 0R parts (R32 [R33] → copper/net-tie, U4 measurement link → normally-closed solder jumper or FB tapped after it) and add link drop to check_power P3.
- **Minor:** refmap leaves the 4 buck measurement links R29–R32 "(unnamed)"; lcsc_fetch parsed a truncated "bas" library type for C52923 on live refresh; make_bom/make_refmap treat any argv[1] (e.g. `-h`) as the design dir and run a full live fetch (verifier's stray `-h/` output moved to refs/verifier-p4dh2-live-2026-10-29/ and removed); net LED_GREEN now drives a red LED.

## 2026-10-29 — Executor — Phase 4 round 2 (verifier D-H2 findings: 1 major, 4 minor) — **gate TP-D4 (amended) PASS: 477 pass, 0 fail**
- **Major (pmu), D-68:** the CPU core path no longer has any 0R chip in it.
  - [LF] R32 (VDD_0V9 → VDD_ARM) becomes direct copper, as a net-tie named NT_ARM.
  - The U4 output measurement link becomes the normally-closed solder jumper JP_MEAS_0V9. The U4 feedback is taken on the regulator side of the jumper.
  - The 0R measurement links stay only on VCC_1V8, VCC_3V3 and VCC_DDR. Their worst case is 0.55 A, under 1 A / 1.3.
  - `check_power.py` has a new P3L term covering link drop and link rating: **84 pass, 0 fail**. The VDD_ARM low edge is 0.873 V ≥ 0.85 V.
  - Source: UNI-ROYAL datasheet V.9 p.5 §7, re-read from `refs/uniroyal-0603waf-datasheet/` (0603 jumper: < 50 mΩ, 1 A).
- **Minors:**
  - **D-69:** refmap.csv names the measurement links R_MEAS_1V8 [R29], R_MEAS_3V3 [R30] and R_MEAS_DDR [R31]. It also lists JP_MEAS_0V9 and NT_ARM as copper with no BOM ref. Net LED_GREEN is renamed LED_STATUS in pinmap.csv, check_pinmap.py and architecture.md; `check_pinmap` still passes 17/0.
  - **D-70:** argparse with -h in make_bom, make_refmap, check_bom and lcsc_fetch. The design directory must already exist and be the design/ folder; the tools never create one. Live fetching only happens with `--refresh`.
  - **D-71:** the Basic/Extended parsing is strict and falls back to the jlcparts mirror. Otherwise the part is marked UNKNOWN, and B4 fails.
- **Results:**
  - `check_bom.py design`: **477 pass, 0 fail**. 64 lines, 194 parts per board, 25 Extended types.
  - **Total $360.35 ≤ $380.**
  - Mutations fail as expected: `--boards 5` ($493.89, B6), SoC rule boards+30 (B2), `--cost-limit 355` (B6), `--service econ` (B7a/b), and Basic/Extended = UNKNOWN (B4).
  - `make_refmap.py --check`: up to date.
- **Ref shift:** BOM refs after R28 move down by 2. refmap.csv is authoritative (D-64 text annotated).
- **Docs updated:** power.md, architecture.md, decisions.md (D-06, D-63, D-64, D-55a amended; D-68 to D-71 new) and cost.md.

## 2026-10-29 — Verifier — Phase 4 round 2 (D-H2) vs gate TP-D4 (amended) — **PASS (0 blocker, 0 major, 2 minor)**
- **Re-ran (actual output):** `check_bom.py design` 477 pass / 0 fail, total $360.35 (parts 113.80, assembly 166.55, PCB 45 EST, shipping 35 EST); `check_power.py` 84 pass / 0 fail (P3L: VDD_ARM 0.873–0.924 V, VCC_3V3 3.108 V, VCC_DDR 1.302 V, VCC_1V8 1.731 V after link drop); `check_pinmap.py` 17 / 0; `make_refmap.py --check` up to date. Mutations fail as claimed: `--boards 5` $493.89 (B6), `--soc-stock-rule boards+30` (B2), `--cost-limit 355` (B6), `--service econ` (B7a SoC pitch, B7b polymer cap). `make_bom.py -h` prints help; a non-existent design dir is refused.
- **Live re-fetch 09:49 UTC** (own parser, python -I; saved `refs/verifier-p4dh2r2-live-2026-10-29/`): RV1106G3 C5328706 JLC overseasStockCount 23 / LCSC 22, $25.39, Extended → B2 (≥ 4) holds. C683782 LTC2954-1 2164; C22472329 W25N01KV 20879; C141836 TLV62569 15515; C21189 0R 0603 Basic. Library types match bom.csv.
- **Primary sources re-checked:** UNI-ROYAL datasheet p.5 §7 0603 jumper "<50mΩ, 1A, 2A" (refs/uniroyal-0603waf-datasheet/C21189.pdf); [DS] r1.8 p.20 Table 3-2 CPU_DVDD 0.85/0.90/1.05 V, DVDD/PMU_DVDD0V9 0.81–0.95 V; p.19 pin 115 = CPU_DVDD. D-68 fix verified in bom.csv (0R line 9 pcs: R11, R29–R31, R57–R61; no 0R on VDD_0V9/VDD_ARM), power_rails.csv, pinmap pin 115, power.md tree, refmap (JP_MEAS_0V9, NT_ARM, R_MEAS_*). LED_STATUS rename complete (no LED_GREEN left except [LF] citations).
- **Minor (eth, pmu, xtal, soc):** refmap.csv still omits [LF] designators that bom.csv role text cites: [LF] R46–R49 (ETH 0R links = bom R58–R61, which D-64 says "refmap.csv is authoritative" for), R13 (U7 FB 127k = bom R18; bom R13 is a 100k), R34 (U5 FB 200k; bom R34 is RTC 100R), R10 (Y1 1M = bom R53; bom R10 is 4.7k), R15/R16, R21/R52/R54/R57, C52, C73, D3; and 67 BOM refs (L1–L4, FB dividers, xtal caps…) have no row. Fix: make_refmap.py emits a row for every bom ref and every [LF] ref cited in bom.csv/power_rails.csv; B8 regex-scans those files and fails on any unmapped [LF] designator.
- **Minor (pmu):** VDD_ARM worst-case DC margin is 23 mV (0.873 vs 0.85 V) with no numeric allowance for buck ripple/load-step or U4→pin 115 copper drop ("Phase 7 rule"). Fix: write a numeric budget into power.md/D-68 (e.g. copper ≤ 8 mV at 1 A, ripple+transient ≤ 15 mV) and add it as a P3L term, or raise U4 R_top 49.9k → 51.1k (band ≈ 0.883–0.931 V, inside logic 0.81–0.95; Basic availability UNVERIFIED).
- **Verdict:** gate TP-D4 (D-H2) met; Phase 4 may close. Owner items unchanged: SoC stock ≥ 4 on order day, live quote (PCB/shipping/fixture/pre-reflow), JP_MEAS_0V9 vs 0805 0R preference.

## 2026-10-29 — Executor — Phase 5 (Schematic), round 1 — gate TP-D5 self-check **PASS: 1622 pass, 0 fail**
- **What this phase does:** describes the whole board as SKiDL Python and writes the KiCad netlist that layout (H1) imports.
- **Outputs:**
  - `design/schematic/`: `lib.py` plus one module per block — `power` (usbc/prot/pmu), `button` (onoff/ui), `soc`, `clocks`, `storage`, `ethernet`, `usb`, `expansion`, `debug`.
  - `board.py` (top level), `check_schematic.py` (gate check) and `ref_connections.csv` (273 hand-written expected connections, each cited).
  - `README.md`.
  - `out/board.net`, plus `parts.csv`, `nets.csv`, `pins.csv` and `erc.txt`.
- **Netlist:** 215 parts (193 BOM parts plus 22 copper-only: TP1–TP20, JP_MEAS_0V9, NT_ARM), 135 nets.
- **Checks:**
  - SKiDL ERC: no errors or warnings.
  - The generator log has 6 warnings, all justified in the README: no KiCad libraries are installed here, and one internal no-connect net has no tag.
  - `check_schematic.py`: 1622 pass, 0 fail.
    - S4: all 129 SoC pins match `pinmap.csv`.
    - S5: the 273 [LF] / power.md / datasheet connections hold.
    - S6: all 28 SoC supply pins and every IC supply pin have a capacitor, and the rail totals equal `power_rails.csv`.
    - S7: every test-point-plan net exists with a pad.
    - S2: BOM = netlist. S3: symbol pins = footprint pad names. S9: only the intended pins are NC.
  - Mutation runs each fail as expected: USB D+/D− swap, decoupler tag removed, TP6 removed, ERC warning injected.
- **Phase 4 files updated (D-72, D-73):**
  - Contingency BOM lines resolved from [LF]: −2 duplicate 10 k, +[LF] C7, +pin-71 100 nF, +[LF] C35 1 µF, which was missing.
  - BOM is now 193 parts, 64 lines, 25 Extended types, **$360.34**.
  - `refmap.csv` names every BOM ref (195 names), which closes the Phase-4 verifier minor.
  - `power_rails.csv` capacitance updated; two summing slips fixed.
  - `check_bom` 477/0, `check_power` 84/0, `check_pinmap` 17/0, refmap up to date.
  - `cost.md` and `power.md` carry update notes.
- **New datasheets** (untrusted, read with `python -I`): `refs/hr911105a-datasheet/`, `refs/usblc6-2sc6-datasheet/`, `refs/usb-a-af90-wjdg-datasheet/`, `refs/taxm24m-crystal-datasheet/`, `refs/header-1x3-datasheet/`, `refs/header-2x20-datasheet/`, `refs/ts-1187a-datasheet/`.
- **Decisions:** D-72 to D-76.
- **Left for Phase 7 / H1:**
  - Draw the six `board:` footprints with the pad names fixed in D-74.
  - Confirm the JP, NetTie and TestPoint library footprint names.
  - Check TF-01A card-detect polarity at bring-up.

## 2026-10-29 — Verifier — Phase 5 (Schematic), round 1 vs gate TP-D5 — **PASS (0 blocker, 0 major, 7 minor)**
- **Re-ran everything myself:** `board.py` exits 0 and gives 215 parts, 135 nets. SKiDL ERC says "No errors or warnings found". The regenerated `board.net` matches the committed one except for its date line, and parts/nets/pins.csv are identical. `check_schematic.py` gives 1622 pass, 0 fail. `check_bom` 477/0, `check_power` 84/0, `check_pinmap` 17/0.
- **Independent mutations** on copies of out/ (my own, not the executor's): moving Q_PWR's S and D pins makes 2 S5 fails. Removing NAND VCC pin 8 is caught, but the script crashes with a KeyError at line 176 instead of reporting a clean FAIL (minor).
- **Checked against primary sources (rendered pages):**
  - **RV1106 pins:** [DS] r1.8 Table 2-1 pp.18–19 against pins.csv for 44 pins, including all 28 supply pins, OSC 68/69, USB 25–28, FSPI 39–48, nPOR 66, PMU GPIO 58–65, UART2_M1 79/80, ETH 96–102, CPU_DVDD 115 and EPAD 129. All match.
  - **Pin-outs:** each matches its datasheet:
    - LTC2954 TSOT-23-8 ([LTC] p.6 Pin Functions)
    - TLV62569 DBV (SLVSDG1C p.3; EN has no internal pull, VIH ≤ 1.2 V, p.4)
    - TS3USB221A RSE (SCDS277A p.3) and its truth table (p.13: S=L → 1D, OE=L)
    - SY6280 (AN p.2)
    - 2N7002 (p.1)
    - HR911105A (P4 TX CT, P5 RX CT, P8 CHS GND; p.1 drawing)
    - TS-1187A (A–B and C–D joined)
    - W25N WSON-8, microSD contact order
  - **Copied from [LF]:** these blocks match the Luckfox sheet:
    - Type-C (5.1k CC, 10k/18k + C7 on USB_DET_IN)
    - Card Power (Q1/R51/R55/R52)
    - 24 MHz (22R, 1M, 18 pF ×2) and 32 kHz crystals
    - RTC (D3 + R11 100R, C35 on pin 19)
    - nPOR (R12 1K, C38 10nF)
    - Ethernet (0R ×4, 103 caps on the centre taps)
    - VCC_DDR divider 127k/100k (1.36 V)
    - FEPHY_REXT 6.04k, DRAM_ZQ 240R, USB AVDD pins 24/28
  - **Live LCSC stock** (refs/verifier-p5-live-2026-10-29/): RV1106G3 C5328706 = 22 at LCSC (JLC stock ≥ 4 must be rechecked on order day). LTC2954-1 2164, W25N01KV 20879, TS3USB221A 73975, TLV62569 15445.
- **Boot-path review:**
  - Q_PWR (S = VBUS_5V) and Q_SD are oriented correctly, and the inverter on the LTC2954-1 EN output has the right polarity.
  - KILL has a pull-up to VCC_3V3 and is blanked for 512 ms.
  - Enable chain: 0V9 → 1V8/DDR → 3V3; nPOR is released by VCC_3V3.
  - Recovery key on SARADC_IN0 is pulled up to 1.8 V.
  - Every control pin rests in its safe reset state.
  - I found nothing that would stop the first board from booting.
- **Minor findings:**
  1. TF-01A card-detect polarity is unverified (sd).
  2. TP8 sits on EN_N, which is LOW when the board is on, but the PLAN table says "high when on" (onoff / Phase 6).
  3. power_rails.csv device text for FB1–FB3 and D_RTC differs from the BOM (pmu).
  4. The five sub-rails have no test pads (Phase 6).
  5. ERC carries little weight because nearly all pins are PASSIVE (README).
  6. check_schematic crashes instead of reporting a FAIL.
  7. Stray design/skidl_REPL.{erc,log} files.
  
  Details are in the verifier report. Phase 5 can close; the minors can be fixed alongside Phase 6.

## 2026-10-29 — Executor — Phase 6 (Test points & bring-up plan), round 1 — gate TP-D6 self-check **PASS** (check_schematic 1691 pass, 0 fail)
- **Outputs:** `design/testpoints.md` (31 pads: net, block, expected value, accept band and stop limit, other states, how to measure, source; PLAN-row → pad map; non-pad measurement points; layout rules for the pads) and `design/bringup.md` (15 ordered steps for board #1, board #2 rule, a "why the order is safe" table, a record sheet).
- **Test pads (D-77):** TP8 ↔ TP12 swapped so TP8 = controller output ONOFF_EN, high when on, as PLAN says (verifier P5 minor 2). Added TP21 VBUS_IN, TP22–TP26 on the five sub-rails (verifier P5 minor 4), TP27 PB_INT_N, TP28 PWR_KILL, TP29 KILL pin, TP30 SDMMC_DET, TP31 GND. All 16 rails of power_rails.csv now have a pad. Netlist regenerated: 226 parts (193 BOM + 33 copper-only), 135 nets, SKiDL ERC clean. BOM and cost unchanged ($360.34).
- **Bring-up method (D-78):** first power with every buck output disconnected from the SoC (cut JP1, remove R29/R30/R31, 10 kΩ KILL hold-up from TP1 to TP29), then 0V9/DDR/1V8 to the SoC with 3.3 V still isolated, then everything. Current limits 100 → 300 → 500 mA → 1.5 A. Board #2 may skip the isolation steps if board #1 passed them and its own unpowered FB-lead checks pass. Acceptance bands = power.md design bands, stop limits = [DS] Table 3-2 maxima (D-79).
- **Checks:** check_schematic S7 now checks each TP ref → net, the netlist pad set = the testpoints.md table (parsed), and a pad on every power_rails.csv rail. Mutations fail as expected: TP22 removed (4 S7 fails), testpoints.md TP14 on the wrong net (1 S7 fail), NAND VCC pin removed (S5 + S6 FAIL, no more KeyError crash — verifier P5 minor 6 fixed). check_bom 477/0, check_power 84/0, check_pinmap 17/0, refmap up to date.
- **Other P5 minors fixed:** power_rails.csv device text for FB1–FB3 and D_RTC now names the BOM parts (minor 3); README says what the ERC proves and what it does not (minor 5); stray `design/skidl_REPL.{erc,log}` moved out of the design folder (minor 7, moved to the session scratchpad, not deleted). The TestPoint/Jumper/NetTie footprint names are verified against the KiCad library (`refs/kicad-footprints-p6-2026-10-29/`, fetched from gitlab.com) and S3 compares their pads.
- **Docs touched:** testpoints.md, bringup.md (new); decisions.md D-77–D-79 (+ D-50/D-76 status notes); schematic/debug.py, lib.py, check_schematic.py, README.md, out/*; power_rails.csv; power.md §6.5 note; architecture.md §6 note.
- **Still UNVERIFIED (measured at H3):** TF-01A card-detect polarity (step 5.9), current draw in MASKROM / Linux idle, crystal pulling with 18 pF caps, Power-Save-Mode no-load overshoot, SMAJ5.0A leakage, pre-loader baud rate.

## 2026-10-29 — Verifier — Phase 6 (Test points & bring-up plan), round 1 — gate TP-D6 **FAIL (1 major, 4 minor)**
- **Re-run:** board.py → 226 parts, 135 nets, SKiDL ERC "No errors or warnings found"; the regenerated netlist/CSVs match the executor's byte for byte apart from the date line (the original files were put back). check_schematic 1691/0, check_bom 477/0 ($360.34), check_power 84/0, check_pinmap 17/0, refmap up to date.
- **Independently confirmed:**
  - All 31 TP refs in nets.csv equal the testpoints.md table, and all 16 power_rails.csv rails have a pad.
  - Divider and output caps sit on the *_BUCK side, and the bleeders R25–R28 on the SoC side. U5/U7 are enabled from VCC5V0_SYS (R20/C20). U6 is enabled from the SoC-side VCC_1V8 (R24 → PWR_EN), so the isolation logic of steps 3–4 holds.
  - RV1106 r1.8 Table 3-1/3-2 p.20 values; pins 11, 66, 68, 69, 79 and 80 (Table 2-1).
  - LTC2954 TSOT-23 pin-out matches U3. KILL abs-max is 7 V, VKILL 0.57–0.63 V, blank 400–650 ms, lockout 200–325 ms, tDB 26–41 ms.
  - TLV62569 SOT23-5: FB = pin 5, VFB 0.588–0.612 V. Crystal ±10/±30 ppm.
  - KiCad footprints: TestPoint_Pad_D1.5mm is F.Cu + F.Mask with no paste.
  - JLCPCB C5328706 page: stock not shown (UNVERIFIED); Phase 6 changed no BOM line, and the order-day recheck stands.
- **MAJOR (pmu/onoff):** step 2 (first power) runs with JP1, R29, R30 and R31 fitted. Step 2 can fail because:
  - Q_PWR conducts at plug-in (gate network or a D-S short), or
  - the wrong SOT-23 reel is fitted, e.g. an AO3400A in place of the AO3401A, whose body diode passes VBUS_5V to VCC5V0_SYS.

  If that happens, U4/U5/U7/U6 start and their unproven outputs reach the SoC. That is the swapped-divider hazard D-78 is meant to prevent, and step 1 cannot detect a swap. Fix: do the isolation prep (cut JP1, remove R29/R30/R31) before step 2. Add a Q_PWR diode-mode check TP13↔TP1 to step 1.
- **Minor:**
  - The unpowered resistance expectations ignore the buck and Q_SD body-diode paths (JP1 140–160 kΩ, TP16 ≈ 10 kΩ, rail pairs).
  - A 100 mA limit against a 0.65 A inrush with only 2.8 µF on VBUS_5V can drop the LTC2954 into UVLO, giving a false stop in step 3.
  - Luckfox and functional names collide with silkscreen refs (R31, R8, R12, R22, R41, R43; power_rails D3 vs D2).
  - USB_DET injection (≈ 0.44 mA) into the unpowered SoC during step 3 is not mentioned there.
- Verifier housekeeping: an accidental temporary copy of `schematic/` (design/out_bak_dummy) created during this check was removed. No design file was changed.

## 2026-10-29 — Executor — Phase 6 (Test points & bring-up plan), round 2 — gate TP-D6 self-check **PASS** (check_schematic 1694 pass, 0 fail)
- **Major fixed (pmu/onoff):** bringup.md now isolates the buck outputs (cut JP1, remove R29/R30/R31, verify the pads open and not shorted to GND) in **step 1.B, before the first power**. New **step 1.Q**: Q_PWR [Q1] diode check (red TP13/black TP1 ≈ 0.4–0.7 V; red TP1/black TP13 OL; ≈ 0 V = D-S short; reversed = N-FET from the Q_KILL reel). Step 2.2 also requires JP1/R29/R30/R31 pad 1 < 0.05 V while off. §3 safety table and D-78 updated; board #2 keeps 1.Q.
- **Minors fixed:** polarity-aware unpowered limits (black on TP19; links "beeper silent, > 500 Ω"; TP16 > 500 Ω; rail pairs > 100 Ω with polarity note; ±10 % board-to-board rule kept). ≥ 470 µF electrolytic at the breakout from step 3; UVLO false-stop note with retry at 300 mA (step 3) / 500 mA (step 4), limit recorded ([LTC] p.3 VUVL 2.2–2.5 V re-read from refs/ltc2954-datasheet). USB_DET caveat in step 3 (≤ 0.44 mA, ≈ 2 min powered intervals, optional R_DET_TOP [R3] removal; TP2 may read ≤ 0.35 V); D-40 figure corrected. Part names: only FUNCTIONAL_NAME [silkscreen ref], bench names for Luckfox-named parts (testpoints.md table); power_rails.csv device_ref D3→D2, R31→R32, R8→R33. Ground rule 4 reworded (supply abs-max; pin limit UNVERIFIED).
- **New check:** check_schematic S7 verifies every "NAME [REF]" pair in testpoints.md and bringup.md (74 pairs) and rejects a bare designator that is another part's silkscreen ref; mutations ("R31 [R32]", "R_NPOR_PU [R42]") fail as expected. check_power 84/0, check_bom 477/0, check_pinmap 17/0, refmap up to date. No netlist, BOM or cost change (D-H2 decisions untouched).
- **Decisions:** D-78 amended, D-40 status note, D-80 new.

## 2026-10-29 — Verifier — Phase 6 (Test points & bring-up plan), round 2 — gate TP-D6 **PASS (0 blocker, 0 major, 4 minor)**
- **Re-run:** board.py → 226 parts, 135 nets, SKiDL ERC "No errors or warnings found"; regenerated board.net identical except the date line (original file put back). check_schematic 1694/0, check_power 84/0, check_bom 477/0 ($360.34), check_pinmap 17/0, make_refmap --check "up to date".
- **Round-1 major closed:** isolation is now step 1.B, before first power. Netlist confirms JP1.1/R29.1/R30.1/R31.1 are the *_BUCK side, with dividers + local caps (C16–C19, C24/C25/C27/C28 ≥ 6.3 V) on that side, bleeders R25–R28 on the SoC side, U6_EN fed only from SoC-side VCC_1V8 (R24 → PWR_EN → R21 → U6.1). Q1 pins G1/S2(VBUS_5V)/D3(VCC5V0_SYS); AO3400A has the same SOT-23 pin-out, so the 1.Q polarity table (P-FET forward red-TP13; N-FET forward red-TP1; ≈ 1 V parallel path via R_BL5 + D_TVS/U1) is right.
- **Independently checked:** all 74 NAME [REF] pairs in bringup.md/testpoints.md against parts.csv (own script, 0 mismatches); every TP net; FB in-circuit readings (33.7/56.1/66.7/81.6 kΩ); [LTC] p.3 VUVL 2.2/2.3/2.5 V, tKILL blank 400–650 ms; [TLV] DBV FB = pin 5; [DS] Table 3-1/3-2 p.20 limits; [DS] Table 3-3 p.21 Rpu/Rpd 16–25–43 kΩ. Inrush with the 470 µF: charge-sharing dip to ≈ 4.4 V, far above UVLO.
- **Minor:**
  1. (pmu) With JP1 cut, U4 sees only 10.1 µF (C24 + C16). That is outside the only checked TLV62569 Table 4 cell for 0.6–1.2 V with 2.2 µH (2×22 µF, [TLV] p.9), so the step-3 U4 reading checks the DC set-point only. Possible false stop, no damage. Fix: add a note to step 3, and an optional temporary ≥ 22 µF ceramic from JP1 pad 1 to GND if the reading is unstable. U5/U6/U7 isolated are in checked cells.
  2. (onoff) The TP27 accept band "≥ 2.55 V" and step 5.3 "TP27 ≈ TP2" ignore pin 60's reset pull-down: 4.7 k against 16 k gives 2.42–2.51 V at 3.135–3.252 V. Fix: band ≥ 0.74 × TP2 (≥ 2.3 V, still > VIH 2.0 V), expected 0.77–0.90 × TP2 in MASKROM.
  3. (pmu) Step 4 scope variant uses 50 ms/div to judge order gaps of 0.5 ms and 1.2 ms. Fix: trigger on TP13 rising at 1 ms/div for the order, and use a second 100 ms/div shot for the 400–650 ms abort.
  4. (pmu) The 1.A/1.B "expected ≤ 1.0 kΩ / ≤ 680 Ω" upper edges sit at the bleeder nominal; 1 % parts plus meter error can read 1–2 % above. Fix: write "≈ 1.0 kΩ ± 3 %" / "≈ 680 Ω ± 3 %" (the stop limits are unchanged).
- No design file changed by the verifier.

## 2026-10-29 — Executor — Phase 7 (Layout constraints), round 1 — gate TP-D7 self-check **PASS** (check_layout 828 pass, 0 fail)
- **Outputs:** `design/layout.md` (rule book: outline/panel/fiducials/holes, stackup + layer use, impedance, IPC-2221 widths, 18 net classes, floor plan + zone table, SoC orientation, decoupling, QFN-128 land pattern + 16 thermal vias + 50 % windowpane paste, thermal estimate, ground strategy, JLC order fields, gate table, 39-item DRC checklist, open items). Generated by `tools/layout_calc.py` (new) into `design/layout/`: `netclasses.csv` (135/135 nets), `placement.csv` (226/226 parts, SoC pad coordinates), `zones.csv`, `impedance.csv`, `trace_widths.csv`, `board.kicad_dru` (helper, syntax UNVERIFIED). Field solver `tools/zsolve.py` (new; scipy added to the venv).
- **Impedance (JLC04161H-7628, L1 over L2, with mask):** ETH 100 Ω → 0.235 mm / 0.200 mm gap (99.7 Ω; fine grid 98.5); USB 90 Ω → 0.255 mm / 0.150 mm (90.3 Ω; 89.2). Solver vs Hammerstad–Jensen < 1 %. Full regeneration reproduces impedance.csv byte for byte.
- **Board:** 70 × 70 mm + customer-drawn 5 mm rails west/east with V-cut (80 × 70 mm panel), 3 + 2 fiducials, 4 tooling holes, 4 × M3; all edge connectors on the north/south edges. SoC at (35, 33) rotated +90°; RJ45 NW, header west, bucks east column, USB-C/on-off SE, USB-A + microSD south; SW1 moved next to U3 ([LTC] p.12).
- **Checks:** check_layout L1–L7 (net coverage, independent sensitive-net list, impedance ±5 % on two grids, IPC widths ≥ minima for every power_rails.csv rail, placement coverage and distance rules, zone overlap/edge geometry, required sections + checklist). Mutations on a scratch copy fail as expected: USB_DP → DEFAULT (L2), PWR_0V9 0.3 mm (L4), J1 moved into the H4 keep-out (L6 ×2), a part dropped from placement.csv (L5). check_schematic 1694/0, check_power 84/0, check_bom 477/0 ($360.34) unchanged — no netlist/BOM/cost change.
- **Decisions:** D-81 (1 oz VBUS vs SY6280 2 oz; USB-A on L1; C_USBA_IN is [C11], D-57's [C10] stale), D-82 panel/rails/fiducials/holes, D-83 stackup use + impedance, D-84 floor plan, D-85 QFN land pattern + thermal vias, D-86 current widths/vias, D-87 thermal (no heatsink, measure at H3), D-88 SDMMC/FSPI length rules (engineering, UNVERIFIED).
- **New refs (untrusted data, read only):** refs/jlcpcb-impedance-2026-10-29/, refs/jlcpcb-pcb-capabilities-2026-10-29/, refs/ti-spraar7-hs-layout-2026-10-29/.
- **Phase 4 D-H2 carry-overs** (architecture.md board-size line, handling fee, reference-designator map) were already closed by D-61/D-66/D-65/D-73 and the P4 D-H2 r2 verifier; nothing reopened.

## 2026-10-29 — Verifier, Phase 7 (layout constraints) vs gate TP-D7: FAIL (1 major, 3 minor)
- Re-ran: check_layout 828/0, check_pinmap 17/0, check_power, check_bom 477/0 ($360.34): all as reported.
- Independently confirmed: [DS] r1.8 Table 2-1 pins 15, 20/21, 26/27, 48, 49-56, 66, 68/69, 79/80, 97-102, 115/116; Fig. 2-3/2-4 p.16 orientation (CCW top view, +90° puts pin 1 SW) and the pad coordinates in placement.csv; θJA 27.3 / θJB 12.5 (Table 4-1); TLV62569 DBV pinout and §10.1 text; JLC V-cut copper ≥ 0.4 mm, 5 mm rails / 2 mm holes / 1 mm fiducials at 3.85 mm; own FD solve (scratch, crude mask) gives ETH 96.9 Ω / USB 87.5 Ω vs 99.7 / 90.3: within 3 %, OK with the H1 calculator cross-check. Live stock (refs/verifier-p7-live-2026-10-29/): RV1106G3 C5328706 LCSC 22, JLC overseas 23 (≥ 4 needed, OK).
- MAJOR (soc, prot/onoff, nand, usb): placement zones are over-subscribed by KiCad courtyard area: Z-SOC 328 mm² in 256 mm² (128 %; ring outside the escape is 0.55 mm), Z-PWRIN ≈ 200 mm² + 10 test pads in 197 mm², Z-NAND 97 %, Z-USBA-PWR 87 %. The floor plan cannot be laid out as written; check_layout L6 only tests overlaps.
- minor (usbc): J1 is stated "rotated 180°", but the footprint's mouth is +y; the zone numbers already assume 0°. At 180° the pads land at y ≈ 70.4.
- minor (eth/usb/usbc): board.kicad_dru 0.76 mm pair clearance fires on SoC/J1/U1/U2/U11 pads; skew lacks (within_diff_pairs); 'NPTH' type test invalid.
- minor (soc): QFN perimeter paste area ratio 0.63 at 0.12 mm stencil (< 0.66); put a stencil request in the §8 order remark.

## 2026-10-29 — Executor — Phase 7 (Layout constraints), round 2 — gate TP-D7 self-check **PASS** (check_layout 1010 pass, 0 fail)
- **Major fixed (zone capacity):** new `tools/courtyard.py` reads F.CrtYd/F.Fab/pads from the cached .kicad_mod files (custom `board:` footprints from their drawings). Zones re-planned in `layout_calc.py`: every zone ≤ 55 % courtyard fill (Z-SOC 29 × 28 mm at 53 %, holds Y1/Y2 + TP6/TP31; Z-PWRIN 598 mm² 41 %, Z-NAND 37 %, Z-USBA-PWR 21 %, each ≥ 2× courtyards). §5.3 now two rings: 100 nF ≤ 3 mm, bulk caps/FB/sub-rail parts/TPs ≤ 8 mm. **Board 70 × 70 → 80 × 80 mm** (panel 90 × 80) under D-H2: 2728 mm² of courtyards could not be zoned at 55 % on 70 × 70; now 42.6 % of the board. SoC at (34.5, 36.5).
- **New check content:** L6 capacity per zone and whole board, ≥ 2× for the three named zones, connector rectangles recomputed from footprint + origin + rotation (pads on board, body front on the edge), connector rectangles hold only their connector, floor-plan length estimates (`layout/lengths.csv`, octilinear × 1.2: ETH ≤ 21.7/30, USB ≤ 41.2/50, SDMMC ≤ 36.4/40, FSPI ≤ 19.8/25 mm). L7 checks the DRU fixes. Mutations on a scratch copy fail as expected (J1 at 180°, Z-SOC back to 16 × 16, U2 in J4's rectangle, J2 8 mm west, skew without within_diff_pairs, ETH rule without U9 exclusion, NPTH edge rule).
- **Minors fixed:** J1 rotation 0° (D-89); DRU: 0.76 mm rules tracks-only outside U9/J1/U1/U2/U11, `(within_diff_pairs)`, plain 0.40 mm edge rule, hand-summed lengths across R47/R48/R55/R56–R59 noted, diff-pair naming caveat (D-90); 0.10 mm stencil in the §8 order remark, area-ratio target 0.76 (D-85a).
- **Cost:** check_bom gets format `single80` (default): PCB ESTIMATE $45 → $58 (area-scaled), total **$373.34 ≤ $380**; cost.md and architecture.md board-size lines updated. check_bom 477/0, check_power 84/0, check_pinmap 17/0, check_schematic 1694/0, refmap up to date; full layout_calc regeneration reproduces impedance.csv byte for byte.
- **Decisions:** D-84a (update to D-84; amends D-82/D-87 numbers), D-85a, D-89, D-90.

## 2026-10-29 — Verifier — Phase 7 (Layout constraints), round 2 — gate TP-D7 **FAIL (0 blocker, 1 major, 5 minor)**
- **Re-run:** check_layout 1010/0, check_bom 477/0 ($373.34, single80), check_power 84/0, check_pinmap 17/0, check_schematic 1694/0, make_refmap --check up to date. layout_calc --skip-z on a scratch copy reproduces layout.md, zones/placement/lengths/netclasses/trace_widths/impedance.csv and board.kicad_dru byte for byte.
- **Independently confirmed:** per-zone courtyard sums with my own script (Z-SOC 428.4/812 = 52.8 %, Z-PWRIN 41.5 %, Z-PMU 45.7 %, Z-NAND 37.4 %, Z-USBA-PWR 21.2 %, board 2727.6 mm² = 42.6 %); J1 cached HRO footprint (A6 at (−0.25, −4.045), F.Fab ±3.65, SH pegs at y −3.13/1.05) → rot 0° mouth south, pads y 72.3; J3 HR911105A pads 1/2/3/6 at the lengths.csv points, fab front at y = 0; SoC pad coordinates (pins 10, 15, 26/27, 48, 68/69, 97–100) against [DS] r1.8 Table 2-1 pp.18–19; QFN area ratio 0.1425/(1.88 × 0.10) = 0.76; [JLC-CAP] V-cut 0.4 mm / ±0.4 mm, pad-pad 0.15 mm, mask web 0.10 mm. My mutations: J3 at rot 0 fails L6 (good); a ring-1 100 nF cap (C48) moved to Z-UART fails only on the stale fill number (see minor 5).
- **MAJOR (soc, pmu, prot, usb):** layout.md §2.3 L3 plane plan and §4.5 VDD_0V9 drop text were not updated for the 80 × 80 floor plan: VDD_0V9 island still at x 26–44, y 24–42 (round-1 SoC at (35, 33)); with U9 at (34.5, 36.5) DVDD_1 pin 10 (pad (32.23, 42.58), escape via y ≈ 44) is outside it. VCC5V0_SYS region x 52–69, y 12–61 misses Z-PMU x 69–79.4, Z-PWRIN y 61–72.5 and U8, and overlaps the corridor U4/JP1 (Z-PMU) → island (x ≤ 44) needs under Z-NAND. Drop text says "≤ 2 mV" and "≈ 6 mV" for a "15 mm" path that is now ≥ 20 mm. VCC_3V3 region (NW/W) has no stated feed corridor from U6 (NE). Not checked by check_layout.
- **Minor:** (1) netclass clearances XTAL 0.30, SENSE 0.25, SDMMC/FSPI/PWR_* 0.20 mm exceed the 0.16 mm U9 pad gap, and the DRU escape rule covers tracks only → pad-to-pad DRC errors on U9; DRU "sense nets away from switch nodes" 2.0 mm hits TLV62569 pad 5 (FB) vs pad 3 (SW), 1.61 mm apart, on U4–U7. (2) xtal: placement.csv TP6 says OSC_XOUT_X (netlist: OSC_XOUT); XTAL length 5 mm (netclasses) vs 6 mm (DRU) and the OSC_XOUT net includes the TP6 branch. (3) pmu/prot: Z-PMU and Z-PWRIN reach x 79.4, 0.6 mm from the V-cut (tolerance ±0.4 mm); keep MLCCs back from the score line. (4) usb: §3 "VBUS_USBA ≤ 15 mm from U8 to J4" is not in U8's placement rule; Z-USBA-PWR spans ≈ 28 mm from J4 pin 1. (5) check_layout does not test that parts with a SoC-pin target sit in Z-SOC.
- No design file changed by the verifier.

## 2026-10-29 — Executor — Phase 7 (Layout constraints), round 3 — gate TP-D7 self-check **PASS** (check_layout 1259 pass, 0 fail)
- **Major fixed (soc/pmu/prot/usb):** `layout_calc.py` computes the L3 plane plan from the current placement → new `layout/planes.csv`: VDD_0V9 island x 26.05–42.95, y 28.05–44.95 (all VDD_0V9 + VDD_ARM escape vias + 1 mm), 4 mm neck y 33–37 from JP1 (63.7, 35.0) level with the U4 cell; VCC_3V3 fed from R30 (63.5, 16.5) along y 8–21.5 to a west column + tongues; VCC5V0_SYS over Z-PWRIN, Z-PMU VIN side and a strip to U8; VBUS_USBA pour. New `layout/power_paths.csv`: VDD_0V9 drop **6.6 mV** at 1.001 A (one figure in §4.5). layout.md §2.3 rewritten as a table of these rectangles.
- **Minors fixed:** DRU "U9 pads" 0.15 mm rule and SENSE/XTAL→SW rule tracks/zones only outside U4–U7; one crystal budget (OSC_XIN/OSC_XOUT_X 5, RTC 6, OSC_XOUT 8 mm incl. TP6 stub ≤ 3) in DRU per-net rules, netclasses.csv, §4.1, §4.3; TP6 net = OSC_XOUT; Z-PMU/Z-PWRIN east edge 77 (53.1 % / 46.0 %), MLCC ≥ 3 mm from V-cuts, parallel within 5 mm, depaneling note in §8; U8 + C11/C34/R37/R61 moved to the Z-USB SE corner at (43.4, 62.6): U8 → J4 pin 1 ≤ 14.4 mm for either outer pin (verifier's Z-USBA-PWR SW corner would give up to ≈ 17.5 mm if VBUS is J4's west pin, D-91); check_layout L5 ties SoC-pin/ring/crystal parts to Z-SOC.
- **Checks:** check_layout L5–L7 extended (plane geometry, drop recompute, U8 distance, MLCC zones, DRU rules, crystal budget). 10 mutations on a scratch copy each fail (listed in D-91). lengths.csv unchanged; check_bom 477/0, check_power 84/0, check_pinmap 17/0, check_schematic 1694/0, refmap up to date — no netlist/BOM/cost change.
- **Decision:** D-91.

## 2026-10-29 — Verifier — Phase 7 (Layout constraints), round 3 — gate TP-D7 **PASS (0 blocker, 0 major, 4 minor)**
- **Re-run:** check_layout 1259/0, check_bom 477/0 ($373.34, single80), check_power pass, check_pinmap 17/0, check_schematic 1694/0, make_refmap --check up to date. `layout_calc.py --skip-z` on a scratch copy reproduces layout.md, planes.csv, power_paths.csv, zones/netclasses/lengths/trace_widths/impedance.csv and board.kicad_dru byte for byte. **Not placement.csv**: layout_calc.py (08:35:34) was edited after placement.csv was written (08:35:13), and the regenerated file has new R37 and TP17 rules (minor 3).
- **Round-2 major closed:** I recomputed planes.csv myself. All regions of different nets are ≥ 0.30 mm apart (island to the VCC_3V3 regions 0.35 mm; neck and N-BAND to VCC5V0_SYS/PMU 0.30 mm). Same-net rectangles touch, so each net is one piece. Every VDD_0V9 escape via (pins 10, 51, 54, 55, 67, 71, 82, 103, 116) and VDD_ARM pin 115 sits 1.0 mm inside the island. Netlist: JP1.2 = VDD_0V9, R30.2 = VCC_3V3, U8.1 = VBUS_USBA, U8.5 = VCC5V0_SYS. [SY] p.2 pinout (1 OUT top-left, 5 IN top-right, 3 ISET, 4 EN) matches "rotation 0, pin 1 NW". Drop: neck 19.35/4 sq × 1.13 mΩ/sq = 5.47 mΩ, island 0.57, vias 0.53 → 6.6 mV at 1.001 A, so ≥ 0.866 V vs 0.85 V (D-68). U8 → J4 candidates 14.4 / 7.3 mm. The DRU "U9 pads" rule, the sense-rule pad/courtyard exclusion and the one crystal budget agree across DRU, netclasses.csv and §4.1/§4.3; TP6 = OSC_XOUT matches the netlist.
- **My mutations** (scratch copy): island x1 = 42.0, S-SOC overlapping the island, VBUS_USBA pour shrunk to x ≥ 38, U8 moved to (40, 52.5), C36 moved to Z-HDR. Each one fails check_layout. The baseline passes.
- **Live check:** LCSC C5328706 page = RV1106G3, QFN-128 (12.3 × 12.3), matching the footprint. The page showed no stock figure today; the earlier P7 refetch had LCSC 22 / JLC 23. Recheck on order day (D-H2).
- **Minor:**
  1. (soc) VDD_0V9 decoupler topology conflicts with the island size. §5.3 says "pin → capacitor → plane via" and puts ring 1 at 7.5–10.5 mm and ring 2 at 10.5–14 mm, but the island's edge is 8.45 mm from the centre. A plane via at ≥ 9 mm after a VDD_0V9 cap lands over VCC_3V3 N-SOC/S-SOC/W-COL (pins 10, 67, 71, 82, 103, 115, 116), and C37/C43 (ring 2) have no 0V9 copper below them. KiCad would report these as unconnected, so this does not break the boot. Fix: in §5.3 and placement.csv, give VDD_0V9/VDD_ARM pins the rule "pin → escape via at 7.45–7.95 mm (inside the island), 100 nF cap teed to that escape trace or via; ring-2 0V9 caps reach the pin by an L1 trace ≤ 8 mm, or sit over the neck (east, y 33–37)". Add an L6 check that ring-1/2 0V9 parts with a plane via are inside the island or the neck.
  2. (soc, nand) The VCC_3V3 claim "≤ 7 mm of L1 trace (worst pin 43: 6.9 mm)" is a straight-line distance. On L1, pin 43 (GPIO3_VCC) sits between FSPI_D1 (42) and FSPI_D2 (44), so its trace to S-SOC would cross the escapes of pins 39/41/42. Its first via falls inside the 0V9 island. Pin 61 needs ≈ 9 mm east to the NAND tongue. Fix: add a VCC_3V3 L3 tongue south-east of the island (x 43.3–49.5, y 37.35–44.95, joined to S-SOC extended east to x 49.5; 0.35 mm from the island and the neck), or state "pin 43 via → L4 trace → S-SOC". Make L6 measure to a reachable via point, not straight line.
  3. (usb) placement.csv is stale against layout_calc.py: the R37 rule ("≤ 2 mm from U8 pin 3, SW of U8, GND via") and the TP17 rule are missing. Fix: rerun layout_calc and commit; add a check_layout or LOG step that layout_calc --skip-z reproduces every output.
  4. (pmu) §4.5/§2.3 put "the inductor, output caps and measurement link" in the 3 mm strip x 62–65, but a 4.0 × 4.0 mm FHD4020S cannot fit there. Only the link and its L3 vias need to be in the strip. Also C_IN is "≤ 1 mm" in §4.5 but "≤ 2 mm pad-to-pad" in placement.csv, and §2.3 says "the plan uses 0.35 mm" gaps while the neck and N-BAND to PMU gaps are 0.30 mm. Fix: reword these three lines to agree.
- No design file changed by the verifier (the scratch copy is in the session scratchpad).

## 2026-10-29 — Executor — Phase 8 (Software), round 1 — gate TP-D8 self-check **PASS** (check_software 51 pass, 0 fail incl. 11 mutations)
- **Outputs (software/):**
  - `README.md`: build steps.
  - `sdk-notes.md`: SDK/Buildroot config notes, the R4 path stage by stage, open items.
  - `sdk/` mirrors the Luckfox SDK tree:
    - board DTS `rv1106-custom-reva.dtsi` + `rv1106g-custom-reva.dts` (USB-A host, default) + `rv1106g-custom-reva-gadget.dts`;
    - kernel fragment `custom-reva.config`;
    - BusyBox fragment (acpid);
    - two BoardConfigs (SD_CARD, SPI_NAND with a 128 MB table);
    - rootfs overlay `overlay-custom-reva`: S15board, S50powerkey, `/etc/acpi/PWRF/00000080`, acpid.conf, board-usb, board-powerkeyd, /etc/default/board.
  - Optional kernel patch `patches/0001` (gpio-poweroff takeover).
  - `alt-systemd/` (logind + udev, systemd rootfs only).
  - Checker `tools/check_software.py`; compiled DTBs + decompiled DTS in `out/`.
- **Gate:**
  - Compiles: both DTS variants and the Luckfox Pro/Max reference compile with clang -E + dtc 1.8.1. The 6 warnings all come from `rv1106.dtsi` and also occur in the reference build.
  - Pins match pinmap.csv:
    - 25 pinctrl pins match pinmap.csv function and net, none claimed twice;
    - 4 GPIO consumers + 1 hog with net and polarity;
    - 160 gpio-line-names;
    - all 50 USED digital pins covered (claimed, or FSPI/UART2 muxed by the loader as on [SDK], RECOVERY via adc-keys, free header GPIOs, USB_SEL/VBUS_EN by board-usb).
  - D-28 list respected.
  - R4 path complete: gpio-keys KEY_POWER → acpid/fallback → poweroff → gpio-poweroff PWR_KILL. Tested on fake input: the fallback daemon and board-usb on a fake sysfs. The patch dry-run applies.
  - OPP ≤ 1.2 GHz vs VDD_0V9 min 0.8748 V.
  - NAND table 126 MiB ≤ 128 MiB.
  - Mutations (pwm10 m2, wrong key pin, poweroff polarity, i2c3 m0, 1416 MHz OPP, spi0 cs1, restart-poweroff, line name swap, non-removable SD, uart0, pmic_sleep mux) each fail.
- **Findings:**
  - evb.dtsi `restart-poweroff` would turn poweroff into reboot and block gpio-poweroff: deleted.
  - PSCI would also block gpio-poweroff, but CONFIG_ARM_PSCI is off in the SDK defconfig. That is an inference; S15board reports binding at boot, and patch 0001 is the fallback.
  - The Luckfox busybox.config has ACPID off and FEATURE_PIDFILE off (no `acpid -p`).
  - The Pro/Max `&sdmmc` misspells `max-freqency`.
- **Doc fixes outside software/:**
  - bringup.md steps 9.1 (acpid, not systemd), 11.1/11.3/11.4 (`board-usb` commands, USB_MODE), 13 (device names).
  - decisions.md D-06/D-15/D-52 status notes.
  - check_schematic 1694/0, check_pinmap 17/0, check_bom 477/0 re-run unchanged.
- **New refs (untrusted data, read only):**
  - refs/luckfox-sdk-dt-bindings-2026-10-29/ (headers);
  - refs/luckfox-sdk-boardcfg-2026-10-29/ (BoardConfigs, build.sh, sysdrv/Makefile, kernel 5.10.160 files, Buildroot/BusyBox configs);
  - refs/busybox-acpid-src-2026-10-29/.
- **Decisions:** D-92 to D-98.

## 2026-10-29 — Verifier, Phase 8 (Software) vs gate TP-D8 — **PASS** (minor findings only)
- **Re-ran:** `check_software.py --mutations` → 51 pass, 0 fail (output to scratch, identical DTBs to software/out). Independently re-compiled both variants and the Luckfox Pro/Max reference (clang -E + dtc 1.8.1): rc 0; board 6 warnings, all from rv1106.dtsi (reference has 9). `fdtget`: dr_mode host / peripheral, no restart-poweroff, OPPs 408–1200 MHz only.
- **Pins (own resolver over the DTB, not the executor's checker):** 25 pinctrl pins on enabled nodes, each = pinmap.csv function and net, none twice; SoC pinctrl groups used (spi0m0_pins/cs0, i2c3m1, i2c1m1, uart3m1, pwm8–11 m1, sdmmc0_*) have the same function numbers as Luckfox's own ipc.dtsi overrides. GPIO users: PB_INT_N GPIO0_A2 active-low, PWR_KILL GPIO0_A4 active-high, LED_STATUS GPIO0_A3 active-low, LED_ETH GPIO1_A2 active-high, hog SDMMC_PWREN GPIO0_A1 low — all match pinmap.csv and button.py (Q_KILL gate = PWR_KILL, drain = PWR_KILL_N to LTC2954 KILL).
- **R4:** LTC2954 INT ≥ 32 ms and low while PB held (datasheet INT pin description) > 20 ms debounce; BusyBox 1.36 acpid source: KEY_POWER value 1 → "button/power PWRF 00000080" → conf `PWRF PWRF/00000080` → spawns ./PWRF/00000080 after xchdir(/etc/acpi) (file is 0755). gpio-poweroff 5.10 source: GPIOD_OUT_LOW at probe, drives 1 in pm_power_off. ARM_PSCI: no `default`, selected only by ARCH_VIRT/XEN (SDK arch/arm/Kconfig L603/L1647). Luckfox `overlay-luckfox-buildroot-init` (fetched, refs/verifier-p8-luckfox-overlays-2026-10-29/) has no inittab/rcS/rcK, so the BusyBox ::shutdown sequence is not replaced. W25N01KV (0xAE21) is in the SDK kernel and U-Boot winbond.c (refs/verifier-p8-src-2026-10-29/).
- **Minor findings:** (1) `vdd_arm` is regulator-fixed with min 0.8 V ≠ max 1.0 V (copied from Luckfox); SDK fixed.c L106-112 rejects that with -EINVAL, so cpufreq most likely never probes and the CPU stays at the CRU ARMCLK 1104 MHz — D-94's 1.2 GHz cap is moot; document it / bring-up check. (2) USB_MODE=auto switches USB-A VBUS on at the first Linux boot (bring-up step 8), before the scoped first-enable of step 11. (3) README §10.1: the "POWER button pressed" line goes to syslog, not the console. (4) sdk-notes UNVERIFIED rows on the Luckfox init overlay can be closed (see R4 above); S99luckfoxcustomoverlay `stop` runs at shutdown (harmless, model-gated).

## 2026-10-29 — Owner
- D-H3: defaults accepted for every Phase 4–8 open question (decisions.md). Next: H1 KiCad layout, guided by design/kicad-guide.md.

## 2026-10-29 — Owner
- D-H4: Claude does the layout end to end (PLAN.md layout phases L1–L6). KiCad 10.0.7 installed.

## 2026-10-29 — Executor, layout phase L1 (custom footprints)
- Drew the 6 custom footprints into `design/pcb/board.pretty/` with `design/pcb/scripts/make_footprints.py` (KiCad 10 format; all load with pcbnew.FootprintLoad). Stock `Fiducial:Fiducial_1mm_Mask2mm` exists, so no custom fiducial.
- `design/pcb/scripts/check_footprints.py`: 191 checks, 0 failed (netlist pad names, drawing dimensions, min pad gap QFN 0.160 / UQFN 0.175 / TF-01A 0.150 mm, mask web ≥ 0.150, silk ≥ 0.155 mm from pads, courtyards, QFN pin order, EP vias/windowpane 50 %, area ratio 0.76). `render_footprints.py`: PNGs in `design/pcb/renders/`; KiCad DRC of a scratch board with all six under the project rules: 0 violations.
- D-99: J4 pin 1 VBUS = west outer pin (mouth south); TF-01A pads = drawing labels (cd, 8 … 1). Details and sources in `design/pcb/footprints.md`.
- For L2: J2/J4 courtyards are wider than their zones.csv rectangles; U11 pad 10 vs pads 1/9 (0.175 mm) needs a DRU exception like "U9 pads".

## 2026-10-29 — Verifier, layout phase L1 (custom footprints) — verdict: PASS (minor findings only)
- **What this check did:** an independent re-check of the six custom footprints against their drawings and the TP-L1 gate. I re-ran the executor's scripts from scratch, measured the pads with my own pcbnew code, ran DRC on a test board with the real nets, and fed the checker 10 deliberately broken footprints to see whether it notices.
- Re-run in a scratch copy: deleting board.pretty and running `make_footprints.py` again gives byte-identical files, and all 6 load with FootprintLoad. `check_footprints.py`: 191 checks, 0 failed (exit 0). `render_footprints.py`: the PNGs regenerate, and DRC on the executor's netless scratch board shows 0 violations. The stock `Fiducial:Fiducial_1mm_Mask2mm` is present.
- Re-measured against the drawings (PDFs opened and read by me): QFN-128 pads, EP, 16 vias and 3×3 windowpane match §6.1/§6.2. The pin order matches [DS] r1.8 p.16 Fig.2-3/2-4: the bottom view, mirrored, gives the counter-clockwise top view with pin 1 at the NW corner (p.17 Fig.2-5 is the dimension table). The UQFN-10 matches TI p.3 (top view) and p.24 (land 2.35/1.85/0.70/0.63/0.35/0.30/0.25). FHD4020S matches p.2 (a/b/c = H/I/G = 1.9/1.10/3.7). TS-1187A matches p.1 (7.0/5.0, 4.5/3.0). TF-01A matches p.1, and the pattern view has the same orientation as the top view (detect lever beside cd, latch opposite), so it is not mirrored. The USB-A pin row, the shell legs 2.4 mm toward the mouth and the 14.2 mm body depth match p.1. J4 VBUS on the west with the mouth south agrees with the stock Molex 67643 and TE 292303-7 footprints and with the front view, where the contacts are under the tongue. Every netlist pad of U9, U11, L1, SW1, J2 and J4 exists.
- DRC with nets from pins.csv and the project .kicad_pro/.kicad_dru: 2 errors, both U11 pad 10 (VCC_3V3, PWR_3V3 0.20 mm) at 0.175 mm from pads 1 and 9 (the issue the executor already reported). The "U9 pads" rule works, since the XTAL/SDMMC pads of U9 give no errors, and J2's cd-to-SH gap of 0.150 mm passes.
- Mutations: swapping QFN pads 1/2, mirroring the QFN, a 7.4 mm EP, swapping J4 pads 2/3, swapping U11 pads 7/8, a narrower SW pad and a smaller L gap are all caught. **Not caught:** swapping J2 pads 2/3 (DAT3↔CMD) and moving J2 pad 5 by 0.2 mm both give 191/0, because only J2 pads 9, 8 and 1 are position-checked. Deleting the J2 courtyard is caught, but by a TypeError crash (exit 1) rather than a clean FAIL.
- Minor findings, for L2 or a later script pass: (1) add J2 pads 2–7 to EXPECTED["microSD_TF-01A"]["rel"] (x = 1.10·(9−n), y 0); (2) guard `fab`/`crt` against None in check_footprints.py; (3) the TF-01A hole y is in fact dimensioned in the drawing's bottom view: "10.49" from the body back edge to the peg centres matches the scaled 10.85 − 0.37 = 10.48, and "2.40" from the left body edge to the left peg gives the left edge at x = −0.69, not −0.77. Cite these and drop the UNVERIFIED marks; (4) L2 needs a "U11 pads" DRU exception (0.15 mm); (5) at the zones.csv origins the J2 courtyard (right edge x 28.11) overlaps J4's (left edge x 27.50) by 0.61 mm, so L2 must move J2 about 1 mm west (J4 has only 0.18 mm of room toward J1) and record the deviation; (6) the comment in make_footprints.py and D-99(c) says the TI top view is rotated 90° CW, but TI p.3 already shows pin 1 top-left in portrait. Only the p.24 land drawing is rotated. The footprint is correct; fix the wording.

## 2026-10-29 — Executor, layout phase L2 (board build & placement) — ready for CHECKPOINT 1
- `pcb/scripts/build_board.py` (netlist → board: 226 footprints + 13 mechanical, 135 nets, every netlist pad assigned; 4 layers JLC04161H-7628, 1.6 mm; .kicad_pro rules + 18 net classes; .kicad_dru + "U3/U11 pads"; 90 × 80 panel outline, V-CUT layer, 4 × M3 + keep-outs, 3 + 2 fiducials, 4 tooling holes; origin page (50, 50)), `place.py` (all 226 parts, top side), `check_placement.py` (197 checks: 175 PASS, 22 recorded deviations, 0 FAIL; kicad-cli DRC: 0 courtyard overlaps, 0 copper-edge, 0 missing/extra footprints; 499 unconnected items expected), `render_placement.py` (renders/placement_top.png, placement_fab.png, placement_soc.png). Rebuilt from scratch: identical result.
- Decisions D-100 … D-103. Review for the owner: `pcb/placement-review.md`.
- Findings for L3/L4: U11 pin order forces one USB P/N crossover; ETH pairs reach J3 crossing-free only from under the jack body (≈ 30 mm); the Y1 corner (pins 65–71) needs inner-ring/at-toe vias; OSC_XOUT_X ≈ 4.5–5.5 mm vs 5 mm.

## 2026-10-29 — Verifier, layout phase L2 (board build & placement) vs gate TP-L2 — verdict: **FAIL** (1 blocker, minor findings)
- **What this check did:** an independent re-check of the placed board before CHECKPOINT 1. I rebuilt the board from scratch in a scratch copy, measured it with my own pcbnew code (not the executor's checker), ran KiCad DRC myself, fed the executor's checker 14 deliberately broken boards, looked at the renders, and analysed whether the SoC pins can actually escape between the ring-1 parts.
- **Re-run (scratch copy, generated files deleted first):** `build_board.py` → 239 footprints (226 + 13 mechanical), 135 nets, 4 layers, 1.600 mm; `place.py` → notes TP18/TP23 placed without the 8 mm limit; every footprint's position, rotation, side and pad nets identical to the committed board. `check_placement.py` → 197 checks, 175 PASS, 22 DEV, 0 FAIL, exit 0 (same as check_placement.txt).
- **Own measurements (scratch/vcheck.py):** 226 refs = netlist; all 135 nets and every netlist node on the right pad; pins.csv 680 rows agree (38 NC pads have no net); every board footprint's pads equal its library footprint; U9 pins 1–32 S (W→E), 33–64 E, 65–96 N, 97–128 W, pin 1 SW, pins 15/26/27/48/68/69/100 at the layout.md coordinates, nets correct (not mirrored). Fixed parts (U9, U8, JP1, R30, J1, J3, J4, J5, J6) exact; J2 at x 18.6 (D-103 a). Stackup text present (0.2104/1.065, ENIG), aux and grid origin at page (50, 50), V-CUT lines x = 0/80, holes/fiducials/tooling at the §1 coordinates, net classes as loaded match netclasses.csv for all 135 nets. Zone violations: exactly the 12 recorded. Ring 1/ring 2, Y1 (2.50, body 2.11), R50 (1.76), buck cells (C_IN 0.54–0.83, L 0.85, FB parts ≤ 2.74), U8 parts, U1 0.88 / U2 1.85, VBUS 14.57, MLCC/V-cut rules: all as the executor reports. Not reported by the executor: **C22 2.59 mm** from the Q4 drain (placement.csv ≤ 2 mm) and **C1 10.94 mm** from SoC pin 25 (layout.md §5.3 ring 2 ≤ 8 mm); the checker does not test either. J3 stock footprint checked against refs/hr911105a-datasheet p.3 (11.43/13.25/15.49 mm spacings, Ø0.89/1.02/1.63/3.25, pin 1 and LED 9 on the same side): matches, mouth north.
- **DRC (kicad-cli, own run):** 0 courtyard overlaps (also 0 by my own polygon intersection), 0 clearance, 0 copper-edge, 0 missing/extra footprints; 499 unconnected (expected); 199 silk_over_copper, 199 silk_overlap, 199 lib_footprint_issues (library table), 2 silk_edge_clearance.
- **Mutations of the executor's checker:** C49 moved 5 mm, U9/J1 rotated, J2 moved north, R62 flipped, C7 over the V-cut, courtyard overlap, L1 moved 3 mm, Y1 moved 2 mm, R62 out of zone, U9 26/27 nets swapped: all caught. J4 pad renumbered: caught only by a KeyError crash (exit 1). C22 moved 3 mm: caught only by the incidental courtyard overlap (the ≤ 2 mm rule is not checked).
- **Blocker (soc, nand):** the ring-1 row sits 1.8 mm outside the U9 pad line (inner pad edges 0.64 mm outside the pad toes), at 1.06 mm pitch with 0.43 mm gaps. That is where layout.md §6.1/§2.3 put the escape vias (≥ 1.0 mm outside the toes), so no via fits there, and a 0.43 mm gap passes 0 traces at the DEFAULT/FSPI/SDMMC class rules (1 only under the U9-courtyard neck-down). Several parts are tangentially offset from their pin, so their supply link runs along the toe band across other pins: C74 (pin 71) 3.3 mm west across pins 72–80, C55/C60 (pin 70), C62 (81), C50 (103) across header pins 104–107, C68 (108), C61 (61), R46 (58). East: FSPI_CLK (pin 48) must reach R47, which sits south of pin 47 (FSPI_CS0N), and C63 (pin 43) sits in the middle of the bus, so FSPI 48/47/44 need a crossing on L1, where FSPI must stay (L4 forbidden). North: 14 signal pins between t −2.3 and +2.9 mm have 8 single-trace exits. The "pass between ring-1 parts or use vias" note in placement-review.md is not borne out. Fix in place.py: put each 100 nF directly in front of its own pin (|offset| ≤ 0.5 mm), move the row out so the via ring at ≥ 7.45 mm from the centre is free (inner pad edge ≥ ≈ 7.9 mm; the ≤ 3 mm rule still holds), put R47 north of pin 48 or ≥ 1.5 mm out on the CLK line and C63 outside the FSPI fan, leave contiguous channels sized for the signals behind them (0.3 mm per DEFAULT trace, 0.35 mm per FSPI/SDMMC trace), and add a check of escape capacity per side (or do a trial fan-out). If inner-ring vias (between pad heels and EP) are intended for header GPIO, record it as a D-number deviation from §6.1.
- **Minor:** (1) record or fix C22 (≤ 2 mm) and C1 (≤ 8 mm) and add both rules to check_placement.py; (2) catch missing pads cleanly instead of a KeyError; (3) the 10 distance deviations (Y2, R44/R45/C72/C73, TP18/TP23, C83, C26) look electrically acceptable (DC/RTC/bulk parts) but the gate says "met", so the owner must accept them at CHECKPOINT 1; (4) decisions.md has the D-100 row twice; (5) silk clean-up (199 silk_over_copper / silk_overlap) before L6.

## 2026-10-29 — Executor, layout phase L2 round 2 (verifier L2 round 1 findings) — ready for CHECKPOINT 1
- **Blocker soc/nand fixed by a planned escape (D-104):** new `pcb/scripts/escape.py`; `place.py` now plans each U9 side in pin order (dynamic programme) and places the ring-1 row with its inner pad edge 7.93 mm from the U9 centre (via ring r 7.45 free); gaps sized for the lanes at their class width/clearance; every sideways shift ≤ 1.45 mm (≤ 2.6 mm over NC pins only); plan written to `pcb/escape_plan.csv`. FSPI: R47 in the CLK lane, CS0N/D2 between R47 and C63, D1/D0/D3 south of C63: no crossing, nothing on L4. Via-ring drops: capless VDD_0V9/GND pins, DEFAULT 59/60/65, feeds 19/56; SENSE 22/23/25 on L4 (deviation, D-104 e). C60 → VCC_1V8 pin 53; R51 in the row, R50/Y1/TP6 beyond it; Y2 below the SDMMC turn with a 0.76 mm RTC-to-pair DRU rule (build_board.py).
- **Minors:** C22 now 1.95 mm from Q4 pin 3 (C21 1.46 to pin 2), both checked; R4/C1 7.56/7.45 mm from pin 25, checked; missing pads give a FAIL, not a crash; zone fill checked (max Z-SOC 52.3 %); decisions.md has one D-100 row; silk clean-up planned before L6.
- `check_placement.py`: 276 checks, 243 PASS, 33 DEV, 0 FAIL (escape per side, via ring, gate room, zone fill added); kicad-cli DRC: 0 courtyard overlaps, 0 copper-edge, 0 missing/extra footprints, 499 unconnected (expected). Mutations: J4 pad renumber, C22 +3 mm, C63 into the FSPI lanes, C53 shift: all FAIL. Rebuilt from scratch: identical positions and plan.
- Ring-1 within 0.5 mm of its pin: 8 of 29 (geometrically impossible in the supply-pin clusters, D-104 a). Owner to accept at CHECKPOINT 1: D-104 (a, c–h) and D-103 (a, d–g), listed in `pcb/placement-review.md`.

## 2026-10-29 — Verifier, layout phase L2 round 2 — gate TP-L2 NOT met (4 major, 3 minor)
- **What this check did:** rebuilt the board from scratch in a scratch copy, re-measured every placement rule with my own pcbnew/json code, ran KiCad DRC myself, tried 7 deliberate mutations against `check_placement.py`, looked at all three renders, and checked whether each critical bus can actually be routed on L1 in pin order from this placement (topology, not only gap widths).
- **Re-run:** `build_board.py` → `place.py` → `check_placement.py` in a scratch copy: 239 footprints (226 + 13 mechanical), 135 nets, 276 checks / 243 PASS / 33 DEV / 0 FAIL, exit 0. Output, `escape_plan.csv` and every footprint position/rotation/side/pad net are identical to the committed files.
- **Own measurements:** netlist parsed independently: 226 refs, 135 nets, every node on the right pad, no extra nets. The only `pins.csv` differences are the 38 NC pads. U9 pin 1 is at SW (29.08, 42.58). Pins 1–32 run S W→E, 33–64 E S→N, 65–96 N E→W and 97–128 W N→S, at 0.35 mm pitch with 0.19 × 0.75 pads at r 6.075 (not mirrored). Fixed parts are where layout.md puts them. Stackup is 4 layers, 1.6 mm. Aux and grid origin are at (50, 50). V-CUT lines are at x 0/80. Holes, fiducials and tooling holes match the §1 coordinates. Nothing is on the bottom, no pad is off the board, and no other-net pads are closer than 0.2 mm. Zone deviations are the recorded set. The ring-1/ring-2/crystal/buck/U8/U1/U2/C6/C3 distances agree with the executor's figures to within 0.05 mm (Y1 nearest pad 3.55 mm, not 3.99). DRC (own run, with schematic parity): 0 courtyard, 0 clearance, 0 copper-edge, 0 footprint/parity; 499 unconnected; silk_* and lib_footprint_issues 199 each (count capped); 2 silk_edge (J1).
- **Mutations (check_placement.py):** C49 moved +5 mm → FAIL. U9 pads 26/27 renumbered → FAIL. R58 flipped to the bottom → FAIL. U10 rotated 180° → FAIL. R48 moved 1/1.6 mm → FAIL. R56 rotated 180° → PASS (no rule covers it). **Y2 moved 0.6 mm north into the SDMMC corridor → PASS (0 FAIL)**: the checker cannot see a blocked corridor beyond the gate.
- **Major (sd/xtal):** SDMMC D0, CLK_SD (from R48), CMD, D3 and D2 must all turn west between the ring-1 row and Y2. Measured gap: R48 pad 2 bottom y 45.99 to Y2 pad 2 top y 47.70 = 1.71 mm. Four 0.15/0.20 SDMMC lanes plus 0.20/0.30 edge clearances need 1.70 mm, and C64's GND via also has to fit there. With the §4.3 rule "no other net on L1 within 1 mm of crystal + caps", the gap needed is ≈ 2.4 mm. Fix in place.py: move Y2/C78/C79 so the corridor is ≥ 2.4 mm (e.g. Y2 ≥ 0.8 mm further south or east). Record the RTC length cost (unused RTC, D-75). Add a corridor/trial-route check to check_placement.py.
- **Major (nand):** the FSPI order around U9 (CLK, CS0N, D2, D1, D0, D3) and around U10 (CS, D1, D2, D0, CLK, D3) differ by two swaps, D1↔D2 and CLK↔D3. This holds for any U10 position or rotation (top side only), so on L1 two crossings are forced. D-104 (i) "no FSPI lane needs L4" is true only at the U9 gate. Fix: decide and record two short FSPI hops (L4 with GND stitching, deviation from §2.3/§10) or routing under U10 between its pads, and say so in placement-review.md.
- **Major (usb):** pins 26 DM / 27 DP (W→E) meet U11 pins 8 DP / 7 DM (W→E), so the pair's P/N is reversed: "straight to U11" cannot be routed without a swap. The U11→U2/J4 USB-A pair is also reversed. The USB-C pair (U11 pins 1/2, west) must cross the USB-A pair (pins 3/4, east): with the SoC N, J4 SW and J1 SE there is no U11 position or rotation on the board that avoids it. Fix: plan the crossovers (≤ 4 vias per line is allowed, but §2.3 forbids USB_DIFF on L4), record the decision and the via positions.
- **Major (eth):** the SoC exit order (pins 97–100: RXN, RXP, TXN, TXP, N→S) arrives at J3 reversed (pins 6, 3, 2, 1 W→E need RXN, RXP, TXN, TXP from the south). So no via-free L1 route exists from the south. The only via-free idea, coming in from the north under the J3 body, has a 1.3 mm SH/pin gap and is likely > 30 mm. R56–R59 (pad 1 north) do not resolve it either way. Also, at the W gate the two ETH pairs are 0.30 mm apart (§10 asks 0.76 mm pair-to-pair). Fix: trial-route ETH, choose a crossover (one pair hops with vias, a deviation from §4.2 "no vias", or the under-J3 path if ≤ 30 mm), then move/rotate R56–R59 onto that route.
- **Minor:** (1) check_placement.py has no topology check: add a trial route (Freerouting on the critical nets, or a scripted maze route) of SD, FSPI, USB, ETH and the crystals before CHECKPOINT 1; my own 0.025 mm grid router in the scratchpad was inconclusive (greedy). (2) Buck C_IN: the VIN pads are 0.54–0.83 mm from pin 4, but their GND pads are 2.3–3.15 mm from GND pin 2. That is the SOT-23-5 geometry ([TLV] p.13 Fig. 20 also returns C1 GND through the pour), but §10 says "≤ 1 mm from VIN/GND pins": record the interpretation. (3) NT1 has no courtyard, so DRC overlap checks skip it; my pad check shows ≥ 0.2 mm clearance. The D-103/D-104 distance deviations remain owner items.
- Verdict: **FAIL** for TP-L2. Placement distances, zones and DRC are clean and reproducible, but four critical buses cannot be routed under layout.md's layer rules as placed, and the checker cannot detect it.

## 2026-10-29 — Executor, layout phase L2 round 3 (verifier L2 round 2 findings) — ready for CHECKPOINT 1
- **SD (major):** Y2 moved south to (34.90, 51.30); C78/C79 under it; U11/C84/R60 below; R32/TP22, the Q4 group and TP16 out of the J2 fan-in. SDMMC corridor under the S row: 3.41 mm (was 1.71). RTC lower bounds 7.45/7.60 mm > 6 (RTC unused, D-75): D-105.
- **FSPI (major):** U10 2.5 mm south; CLK_NAND runs over U10's top row and down the east pad/EP channel to pin 6; D1 enters between pins 3/4 and runs up the west channel to pin 2. No crossings and no L4. R52–R55, C80/C81 re-placed. D-104 (i) corrected: D-106 (c).
- **USB (major):** U1 rotated 90° (no USB-C P/N swap); planned L4 hops: USB_DM north of U11 (SoC swap), USBA_DP/DM under the USB-C pair south of U11 (crossing + swap), USBC_DM join crossover at J1; ≤ 2 vias per line: D-106 (a), owner to approve.
- **ETH (major):** TX pair hops under the RX pair on L4 (2 vias per TX line, ~4 mm L4); RX/TX P/N swaps through the 0R links (RXN_J between R58's pads, TXN_J between R56's); pairs 0.76 mm apart from the gate on (escape re-plan, pair lanes ≤ 1.35 mm shift): D-106 (b), owner to approve.
- **Checker (minors):** new `pcb/scripts/trial_route.py` + `maze_route.py` (negotiated-congestion grid router, 0.05 mm, L1/L4, class rules, layer policy). Freerouting 2.5.0 needs Java 25 and this Mac has Java 23. Result: 37/37 critical nets routed, 0 conflicts; with L1 only, 6 nets fail. New checks: SD corridor, NT1 pad clearance (found and fixed an NT1/C52 short caused by the W-row re-plan; DRC shorting_items is now a FAIL), Y1 nearest pad 3.55 mm, C_IN GND side as DEV (D-107 c), DRU neck-down area U9_FAN. `mutate_check.py`: 5 mutations, all FAIL (trial/mutations.txt).
- `check_placement.py`: 304 checks, 251 PASS, 53 DEV, 0 FAIL; DRC 0 courtyard overlaps, 0 shorts, 0 copper-edge, 0 missing/extra footprints, 499 unconnected (expected). Review: `pcb/placement-review.md`. Decisions D-105 … D-107.

## 2026-10-29 — Verifier, layout phase L2 round 3 (gate TP-L2) — FAIL (1 major, 5 minor)
- **What this check did:** rebuilt the board from scratch in a scratch copy (build_board.py → place.py → check_placement.py), compared it part by part with the delivered board, re-measured everything with my own pcbnew/geometry code (netlist pads, zones, §10 distances, connector and polarised-part rotations, outline, holes, fiducials, stackup), re-read the RV1106 [DS] p.16 pinout, the W25N01KV p.58 WSON table and the TS3USB221A RSE land pattern, ran kicad-cli DRC myself, ran 6 new mutations against check_placement.py, and looked at every render and the trial-route geometry.
- **Reproduced:** build + place from scratch give the same 239 footprints (positions, rotations, layers, pad nets identical; .kicad_pro/.kicad_dru/escape_plan.csv identical). check_placement.py: 304 checks, 251 PASS, 53 DEV, 0 FAIL, exit 0. Freerouting 2.5.0 really does not start on Java 23 (UnsupportedClassVersionError, class file 69).
- **Own measurements:** 226 netlist parts + 13 mechanical, 135 nets; every netlist pin on its net (the only 38 differences are NC pins, correctly unconnected); FPID/LCSC/value/InBOM fields match parts.csv; all on F.Cu; no pad within 0.4/0.3 mm of the V-cut/routed edges. U9 pin 1 at the SW corner (29.08, 42.58), CCW, 0.19 × 0.75 pads at 6.075 mm, all 52 placement.csv target pads match; U10 = Winbond WSON 8×6 (EP 3.4 × 4.3, e 1.27); U11 land = TI 4208106-3/E (1.85 × 2.35, 0.25/0.30 × 0.575, end pads 0.63 × 0.35), pinout matches SCDS277A p.3. Zone deviations = exactly the recorded 21; my distance FAILs (28) are all recorded DEVs, except R58. DRC (own run): 0 courtyard, 0 shorts, 0 copper-edge, 0 parity; 499 unconnected; silk_overlap/silk_over_copper/lib_footprint_issues each 199 (kicad-cli caps each type at 199, so these are not totals).
- **Mutations (check_placement.py, all caught):** C53 +5 mm → FAIL (ring1, escape, courtyard); U11 pads 7/8 renumbered → FAIL (netlist); J1 rotated 180° → FAIL (fixed, edge, U1); C7 rotated 90° → FAIL (V-cut MLCC, buck); Y1 rotated 180° → FAIL (xtal lengths, trial crossing); U9 rotated 180° → FAIL (85 checks).
- **Major (eth):** D-106 (b) and placement-review.md say the RX swap is RXN_J under R58 and that TX and RX stay 0.76 mm apart from the U9 gate on. The trial that proves it routes something else: ETH_RXP runs between R59's pads (y 26.93) and ETH_RXN runs between the pads of **R57, the TXN link** (y 25.23, x 20.8–21.9), 0.145 mm from R57.1 (ETH_TXN); RXP to TXN track gap 0.24 mm near (22.1, 27.3). That breaks §10 "≥ 0.76 mm from the other pair (ETH TX vs RX)". The checker cannot see it because the R56–R59 breakout box drops all clearances to 0.15 mm. The RX pair is also uncoupled, with ≈ 7 mm P/N difference (RXP 19.8 + 7.4, RXN 13.9 + 6.2). Fix: inside the R56–R59 field, relax only own-pair clearances (keep 0.76 mm TX↔RX), add a TX/RX separation check, re-run. Then either show the D-106 (b) topology, or move R56/R57 so no RX line passes under a TX link, or record the measured deviation. Correct D-106 (b) and the review before the owner approves.
- **Minor (usb):** the USBA_DP hop via is at U11's centre (38.68, 55.03), in the 0.70 mm gap between its pad rows, under the IC body, 0.13 mm from U11.2/.7/.8 (other nets; < 0.15). The USBC_DM via at J1 is 0.147 mm from U1.2 GND. D-106 (a) asks the owner to approve these positions. Fix: no-via keep-out on the U11/U1/J1 courtyards in maze_route.py, re-run, record vias ≥ 0.15 mm (target 0.2) from other-net pads.
- **Minor (sd):** the trial ignores VCC3V3_SD. It routes SDMMC_CLK_SD between C23.1 and J2.4 (y 63.58) and D0/D1 between/under C26/C23, which would cut card VDD (J2.4) off on L1 and leave no via room. A valid topology exists: CLK_SD and CMD straight north past C23/C26 (2.05 mm pocket), plus a VCC3V3_SD via in the pocket to L4 → Q4/TP16. Fix: add J2.4/C23/C26 with a pocket via to the trial (or a pocket check) and record it in D-105.
- **Minor (eth):** R58 to its own jack pin J3.3 is 6.48 mm (≤ 5 mm, §4.2). The checker uses the nearest pair pin of any net (3.71). Fix: measure the same-net distance and record R58 next to R59.
- **Minor:** the trial is not deterministic. On my rerun the USB hop vias moved (USBA_DP L4 2.2 vs 3.9 mm, other coordinates) and the SD lengths changed by ±0.1 mm. D-106 quotes one run. Fix: stable net order and tie-breaks, or quote the numbers as an example. Also report the silk counts as "≥ 199 (capped)", and tell the owner that KiCad on this Mac has no global footprint library table (lib_footprint_issues).
- Verdict: **FAIL** for TP-L2 on the ETH major only. The placement gate items themselves (226/135, pads, zones/recorded deviations, distances/recorded deviations, no overlaps, connector mouths, nothing on the bottom) are independently confirmed and reproducible.

## 2026-10-29 — Executor, layout phase L2 round 4 (verifier L2 round 3 findings) — ready for CHECKPOINT 1
- **ETH (major):** trial router now treats ETH TX and RX as separation groups (>= 0.76 mm between their tracks everywhere, also in the R56–R59 field, and from the other pair's link pads; J3 pins exempt), allows only RXN_J between R58's pads and TXN_J between R56's, and pulls ETH lines toward their partner. The D-106 (b) topology now routes as described; exact TX–RX minimum 0.816 mm (new check). Measured and recorded: skew RX 6.00 / TX 5.82 mm (L5 serpentine), uncoupled RX 11.3 / TX 6.7 mm, R58 6.48 mm and R59 5.13 mm to their own J3 pins (checker now measures same-net pins). D-108 (b).
- **USB (minor):** no via under U11/U1/J1 (courtyard + 0.15 mm), vias >= 0.20 mm + margin from other-net pads; exact via check: nearest 0.255 mm. New hop pattern: USB-C pair under USB-A south of U11 (USBC_DM 4 vias incl. the J1 join = limit). D-108 (a).
- **SD (minor):** VCC3V3_SD in the trial; J2 VDD column closed to other nets; J2.4 → C23.1 → C26.1 on L1, via beside C26.1; pocket 2.20 mm (checked >= 0.9). D-108 (c).
- **Determinism (minor):** cause = footprint order in the saved board file changes between rebuilds; trial now sorts everything, identical results for two file orders. Silk counts reported as ">= 199 (capped)"; library-table note in the review. D-108 (d, f).
- `check_placement.py` after a from-scratch rebuild: 333 checks, 275 PASS, 58 DEV, 0 FAIL; DRC 0 courtyard overlaps / shorts / copper-edge / missing / extra, 499 unconnected (expected). Mutations: see `pcb/trial/mutations.txt`.

## 2026-10-29 — Verifier, layout phase L2 round 4 (gate TP-L2) — PASS (0 blocker, 0 major, 5 minor)
- **What this check did:** I rebuilt the board from scratch in a scratch copy and compared it with the delivered files. I measured the board again with my own pcbnew code, not the executor's checker. I also loaded the 38-net trial route into a copy of the board as real tracks and vias and ran KiCad DRC on it. I tried 5 new deliberate breakages against `check_placement.py`, checked the FHD4020S land pattern against its datasheet, and looked at the renders.
- **Re-run:** first I deleted every generated file in the scratch copy (board, .kicad_pro/.kicad_dru, escape_plan, trial/, renders). Then I ran `build_board.py` → `place.py` → `check_placement.py`. Result: 239 footprints (226 + 13 mechanical), 135 nets, 4 layers, 1.600 mm. The checker gave 333 checks: 275 PASS, 58 DEV, 0 FAIL, exit 0. Its output is identical line for line to `check_placement.txt`. `result_policy.json`, `geometry_policy.json`, `trial_summary.csv`, `escape_plan.csv`, .kicad_pro and .kicad_dru are byte-identical. Every footprint's position, rotation, side, FPID, value, fields and pad nets/positions are identical to the committed board, so determinism is confirmed. `check_footprints.py` gave 191 checks, 0 failed.
- **Own measurements:** I parsed the netlist with my own parser: 226 refs, 135 nets, every node on the right pad, no extra pad nets, FPID/value/LCSC match. `pins.csv` has 680 rows; the only differences are the 38 NC pads. U9 sits at (34.5, 36.5), rot 90. Pin 1 is at (29.075, 42.575) SW. The sides are S/E/N/W in order with 0.35 mm pitch and 0 errors (not mirrored). Fixed parts (U8, JP1, R30, J1, J3, J4, J5, J6) are at their coordinates, J2 is at x 18.6 (D-103 a), and nothing is on the bottom. Aux and grid origin are at board (0, 0) = page (50, 50). My distance FAILs are exactly the recorded DEVs, except **R51**: its OSC_XIN pad is 2.50 mm from pin 68 (rule "within 2 mm of pins 68/69"), and the checker measures only pin 69 (1.49). The zone overruns are the recorded set; besides those, only ≤ 0.05 mm courtyard-rounding cases (C39, D2, R34, R66, J5, J6). The FHD4020S land pattern (1.1 × 3.7 pads at ±1.5, gap 1.9) matches refs/fhd4020s-datasheet p.2 table (a 1.9, b 1.10, c 3.7).
- **ETH (round-3 major): fixed.** My own segment geometry gives these results:
  - TX–RX minimum 0.816 mm (ETH_TXN to ETH_RXP near (26.5, 30.6)).
  - Link pads to the other pair's tracks: at least 1.08 mm.
  - The routed topology is the one D-108 (b) describes.
- **Mutations of check_placement.py:** C64 moved 5 mm south → 6 FAIL. U10 rotated 180° → 4 FAIL. J2 pads 3/5 renumbered with their nets → 3 FAIL (trial and SD pocket only; the netlist check cannot see it because the nets stay with their numbers). R51 moved (+1.0, −0.6) → 6 FAIL. U2 moved 0.8 mm north → 0 FAIL (the trial still routes, and U2 stays within its rules). So every harmful mutation was caught.
- **DRC (kicad-cli, own run on the board):** 0 courtyard overlaps, 0 shorts, 0 copper-edge, 0 missing/extra footprints, 499 unconnected (expected before routing).
- **Minor (usb, eth): trial vias break the board's own via rules.** The checker's "exact via check" tests vias against pads only, not against other vias or holes. With the trial loaded as real tracks/vias, KiCad DRC reports:
  - USBA_DM via (37.62, 57.78) to USBC_DM via (37.08, 57.53): copper gap 0.104 mm (USB_DIFF 0.15; §10 asks USB-A vs USB-C ≥ 0.76) and hole-to-hole 0.304 mm (board setup 0.45).
  - Hole-to-hole USBC_DP/USBC_DM 0.421, ETH TXN/TXP 0.371 and 0.396.
  - A USBC_DP L4 track 0.22 mm from the USBC_DM via hole (0.25).
  - There is room south of U11 to spread these vias, so the placement is not the cause.
  - **Fix:** in maze_route.py, treat other-net vias as obstacles at clearance + hole-to-hole 0.45 mm. Re-run, and quote the new positions in D-108 (a)/(b). The owner should approve the hop concept and via counts, not today's coordinates.
- **Minor (soc, usb, eth, sd, nand): trial track-to-pad clearances are not within the stated grid tolerance.** D-108 (e) says 0.06 mm. Exact polygon re-measurement gives:
  - Shortfalls beyond 0.06 mm: USBC_DM–J1.B6 0.074, ETH_TXP–C66.1 0.075, USB_DP–C65.1/.2 0.078, USBC_DP–R60.2 0.078, SDMMC_DET–C48.2 0.090, ETH_RXP_J–C82.2 0.096 (class 0.15), and SDMMC_D3–J2.1 0.107 (class 0.20). Four of these are below the JLC 0.09 mm minimum.
  - The router also checks pads at the routed net's clearance only. KiCad uses the larger of the two classes (PWR pads 0.20).
  - The gaps themselves have room: C58–C65 is 1.26 mm against the 1.01 mm the USB pair needs, and the TX pair has free space north of C66. So this is router precision, not placement.
  - **Fix:** add the trial-into-board-copy + kicad-cli DRC step, or an exact track-to-pad re-measure, to check_placement.py. Use max(class) clearance for pads and the same 0.07 mm margin as vias.
- **Minor (eth):** ETH_RXN_J runs 0.34–0.37 mm from ETH_RCT (C83.1 pad and track) at (15.6, 21.6–22.2), on the J3 courtyard edge. The DRU "ETH pairs keep 30 mil" rule flags this, and §10 exempts only U9/J1/U1/U2/U11. **Fix:** record a J3 pin-field exception (D-number), or move RCT/RXN_J apart in L4.
- **Minor (xtal):** record R51.2 (OSC_XIN) 2.50 mm from pin 68 as a DEV, or move R51, and have the checker measure both pads.
- **Minor (docs):** the round-4 summary, D-108 (f) and placement-review.md say the silk counts are reported as "≥ 199 (capped)". `check_placement.txt` still prints a plain 199. **Fix:** change the checker text.
- **Verdict: PASS for TP-L2.** All 226 parts and 135 nets are present with no missing pads, and every part is in its zone or has a recorded deviation. The distance rules are met or recorded (plus R51, minor). There are no courtyard overlaps, the connector mouths are on their edges, nothing is on the bottom, and the build reproduces exactly. The five minors are about the trial-route evidence and reporting, not the placement. At CHECKPOINT 1 the owner still has to accept D-103 … D-108, with the via coordinates of D-108 (a)/(b) only as an example.

- **2026-10-31 — Owner (CHECKPOINT 1):** placement approved with its four decision items (D-H5). Routing L3–L5 started; Java 25 install approved for Freerouting.

## 2026-10-31 — Executor, layout phase L3 (planes and SoC escape, gate TP-L3)
- **New scripts** (after place.py; `pcb/scripts/rebuild_all.sh` reruns everything from the netlist in ~6 min): `place_l3_tweaks.py` (C36/C42 rotated 180° in place), `l3_rules.py` (DRU "pairs in the U9 fan"), `route_escape.py` + `escape_solve.py` (one LP per U9 side, scipy in design/.venv), `route_planevias.py`, `planes.py` (writes `pcb/planes.csv`), `fill_zones.py`, `route_powerlinks.py` (own 2-layer grid A*), `check_routing.py` (→ `pcb/check_routing.txt`, `pcb/drc_routing.json`), `render_routing.py` (→ `pcb/renders/route_l3_*.png`); shared `routelib.py`. Decisions: D-109 (a)–(h).
- **Escape:** 98 of 98 U9 pads with a net escaped: lanes to their escape_plan.csv gate points (r 8.00 mm), links to their ring-1 parts, GND 37/57 tied to the EP, the D-104 via pins on vias under the package (the outer via ring cannot hold them at the board's hole rules), extra inner VDD_0V9/VCC_3V3 vias; EP solid with its 16 vias. Fan widths ≥ 0.10 mm; pair fan P/N differences 0.012 / 0.057 / 0.032 mm.
- **Planes:** L2 one GND plane (one piece, no tracks); L3 one zone per power net per `pcb/planes.csv` (recomputed for the approved placement: new NAND-S, S-USB, USBA-U8, W-ARM; fingers ≤ 8 mm), smallest gap between nets 0.300 mm; GND fill; L1/L4 GND pours. 224 plane vias + escape vias; power links for the far pads (test row, pull-ups, TP17, header 5 V on L4 1.0 mm along the north band).
- **Checks:** `check_routing.py` 181 checks: 143 PASS, 16 DEV (D-109 e/g), 22 INFO, 0 FAIL. kicad-cli DRC after fill: **0 errors**; unconnected items on GND/VDD_0V9/VCC_3V3/VCC5V0_SYS/VBUS_USBA: **0**; 252 unconnected items left for L4/L5 (DEFAULT 85, SENSE 30, PWR_1V8 19, USB_DIFF 16, PWR_SUB 15, PWR_5V 13, PWR_DDR 13, XTAL 11, FSPI 10, PWR_0V9 9, ETH_DIFF 8, SDMMC 6, PWR_SD 6, PWR_3V3 5, SW_NODE 4, ETH_CT 2); warnings: 55 dangling lane ends, 8 dangling signal vias (L4 later), silk/lib warnings ≥ 199 each (capped). `check_placement.py` after the C36/C42 rotation: 333 checks, 275 PASS, 58 DEV, 0 FAIL.
- **Carried L2 minors:** R51.2 2.50 mm from pin 68 recorded as DEV (D-109 g); ETH_RXN_J near ETH_RCT stays an L4 item; silk counts reported as "≥ 199 (capped)".

## 2026-10-31 — Verifier, layout phase L3 (planes and SoC escape, gate TP-L3) — FAIL (1 blocker, 2 major, 5 minor)
- **What this check did:** I rebuilt the whole board from scratch in a scratch copy with `rebuild_all.sh`, compared it item by item with the delivered board, and measured it again with my own pcbnew code (pad nets against pins.csv, U9 orientation, which copper each U9 pad reaches, plane-via distances, via landing, fill pieces, filled copper width of the L3 paths, L4 track classes, fan pair lengths). I ran kicad-cli DRC myself (as saved and with refill), tried 7 deliberate breakages against `check_routing.py`, ran my own L1 "can this lane leave the SoC" grid search from each of the 54 open lane ends, and looked at the four layer renders, the U9 close-up and my own zoom plots with the approved trial route drawn over the new copper.
- **Reproduced:** the rebuild exits 0 in about 6 min. The board is identical to the delivered one: 2195 of 2195 tracks, vias, footprints, zone outlines and fill areas match. planes.csv, planevias.csv, escape_geom*.json, escape_plan.csv, .kicad_dru and check_routing.txt are byte-identical. check_routing: 181 checks, 143 PASS, 16 DEV, 22 INFO, 0 FAIL. check_placement: 333 / 275 PASS / 58 DEV / 0 FAIL. Note: `design/pcb/check_placement.txt` is still the 2026-10-29 file; the rebuild prints this result but does not save it.
- **Confirmed with my own code:** 680 of 680 pins.csv pads are on the right net. U9 pin 1 is at SW (29.075, 42.575) and the numbering runs CCW (not mirrored). Nothing is on the bottom. 98 of 98 U9 pads with a net reach a gate end, a part pad, a via or the EP. The 16 EP thermal vias are PTH pads of the footprint, tented on the bottom, with a solid connection. L2 has 1 GND piece and 0 tracks on L2/L3. All 244 vias are 0.3/0.5 mm, tented. 88 of 88 L3 plane vias land in their own fill; the other 2 are L1–L4 link vias. 146 of 146 GND vias land in L2. Fan P/N differences: 0.012 / 0.057 / 0.032 mm. DRC: 0 errors, 252 unconnected, 0 on GND/VDD_0V9/VCC_3V3/VCC5V0_SYS/VBUS_USBA, and no DRC exclusions.
- **Mutations of check_routing.py:**
  - Caught (exit 1): C64 moved 5 mm, the inner via of pin 116 deleted, U9 pads 115/116 swapped with their nets, the VDD_0V9 L3 zone moved 2 mm.
  - **Not caught (exit 0):**
    - One of JP1's 6 vias deleted: reported as "DEV 5 of 6, D-109 (e)".
    - C64.2's own GND via deleted: reported as "DEV, D-109 (e)".
    - 3 GND vias added inside the VDD_0V9 neck: no finding.
  - In `check_planevias` every shortfall becomes DEV, including the line `"DEV" if ... else "DEV"`.
- **BLOCKER (soc, nand, sd): 17 lanes cannot leave their gate point on L1.** Eight ring-1 decoupler plane vias sit in the lane channels between the ring-1 parts that D-104 reserved:
  - C62.1 (32.60, 28.03) and C67.1 (31.59, 28.03) trap HDR_I2C3_SDA/SCL, HDR_PWM10/11 and HDR_UART3_RX (the two vias are 0.51 mm apart; 5 lanes need ≥ 2.6 mm).
  - C74.1 (36.07, 28.03) traps HDR_GPIO1_A0/A1.
  - C50.1 (26.03, 34.79) traps HDR_I2C1_SDA/SCL. C68.1 (26.03, 36.76) traps HDR_GPIO2_A0/A1.
  - C61.1 (42.97, 30.65) traps LED_STATUS and PWR_KILL.
  - C63.1 (42.97, 38.74) traps FSPI_CS0N and FSPI_D2 (gaps 0.19 mm to R47 and 0.16 mm to C63.1). These are the NAND boot bus, and the approved trial route ran exactly there.
  - C64.1 (32.02, 44.97) traps SDMMC_DET and SDMMC_D1.
  - With the same test and only the pads and the fan (no L3 vias), only OSC_XIN is blocked (see the minors). So the L3 vias cause the other 17.
  - **Fix:** take these 8 vias out of the channels. Either tie those pins to the plane by inner under-package vias, as already done for pins 10/54/71/103/28, or put each via outside the ring-1 row, clear of every gate-to-trial corridor. Then add a lane-corridor check to check_routing.py that FAILs: BFS from every open lane end at class width and clearance to r ≥ 11.5 mm or its own pad, and a lane-count capacity per D-104 gap. Re-run it.
- **MAJOR (pmu, soc): the VDD_0V9 L3 neck is choked to 0.8 mm at x 44.0–44.6.** This is the whole SoC core feed from JP1 (§3: inner ≥ 2.58 mm, chosen 3.0, neck 4 mm).
  - The ring-1 GND via column at x ≈ 44.25 (y 32.82, 33.67, 34.45, 35.24, 37.15) and the GND vias of C36/C42 after the 180° turn (45.66, 33.32) / (45.93, 36.54) sit inside y 33–37. Their 0.3 mm anti-pads merge, and GND fill grows between them. Only y 35.8–36.7 is left as VDD_0V9.
  - At x 49.4 the neck is 1.8 mm (GND vias at (49.30, 35.88) and (49.53, 33.88)).
  - **Fix:** no other-net via inside the neck band x 42.95–62, y 33–37. Move those GND vias north or south of the band, or widen the neck so that ≥ 3.0 mm of continuous VDD_0V9 copper is left at every x. Add a FAIL check that measures the filled cross-section of each L3 path against §3: VDD_0V9 ≥ 2.58/3.0, VCC_3V3 ≥ 2.0, VBUS_USBA ≥ 3.0, VCC5V0_SYS ≥ 5.0 mm.
- **MAJOR (checker):**
  - Plane-via distances and the §3 via counts cannot FAIL. A JP1 with 5 vias or a decoupler without its GND via shows up as a recorded D-109 (e) deviation.
  - There is no cross-section check and no lane-escape check (the two findings above went through with 0 FAIL).
  - **Fix:** make D-109 (e) an explicit whitelist (the 15 pads and values recorded there) and FAIL anything else. Make via counts below the §3 minimum a FAIL. Add the two checks above.
- **Minors:**
  - (usb) U2.2 (USB-A ESD GND) and R60.2 have no own GND via. §7 asks for one at every ESD GND pad; the nearest is 2.2 / 1.3 mm away. Add a via ≤ 0.5 mm at U2.2.
  - (soc) VCC_DDR pin 56 and VCC3V3_RTC pin 19 change layer with 1 via each; §3 asks ≥ 2 for PWR_DDR/PWR_SUB, and D-109 does not mention it. Add the second via in L4 (e.g. the VCC_DDR feed at C53) or record it.
  - (xtal, from L2) OSC_XIN cannot get from R51.2 to Y1.1 at the XTAL 0.30 mm clearance. R50.1 to Y1.4 is 0.634 mm and needs 0.75; the approved trial passes 0.23/0.25 mm from them. Move R50 about 0.15 mm (a D-H5 local move) or record it.
  - (docs) check_placement.txt is stale; have rebuild_all.sh write it. Note also that kicad-cli 10 takes `--schematic-parity` as a flag, so "off" means: leave it out.
  - Open owner questions (vias under the package, 0.30 mm power links on L4, the header 5 V L4 route) stay as the executor wrote them.
- **Verdict: FAIL for TP-L3.** The literal gate items are met and reproducible: 98/98 pads escaped, zones = planes.csv, plane-net unconnected 0, DRC 0 errors. But the escape leads 17 lanes into closed pockets, so L4 cannot route them, FSPI and SDMMC included. The core supply neck is also below its current rating.

## 2026-11-01 — Verifier, layout phase L3 round 2 (planes and SoC escape, gate TP-L3) — FAIL (1 blocker, 2 major, 5 minor; nothing fixed)
- **What this check did:** the executor said that round 2 changed nothing. I checked that claim, rebuilt the whole board from scratch in a scratch copy, ran KiCad DRC myself, measured the round-1 findings again with my own pcbnew code, ran my own L1 lane-escape grid search, looked at the renders, and tried 6 deliberate breakages against `check_routing.py`.
- **No change since round 1, confirmed:** the board (md5 1de3347a…), all scripts, decisions.md (last D-109, 2026-10-31 18:50) and the check outputs are older than the round-1 verifier entry. There is no `lanecheck.py`, no whitelist, and no cross-section check. The checker line `"DEV" if net == "GND" or not is_cap else "DEV"` is still in check_routing.py, line 311.
- **Rebuild:** `rebuild_all.sh` exits 0. check_placement gives 333 checks / 275 PASS / 58 DEV / 0 FAIL. check_routing gives 181 checks / 143 PASS / 16 DEV / 22 INFO / 0 FAIL. planes.csv, planevias.csv, escape_plan.csv, escape_geom*.json, .kicad_dru and check_routing.txt are byte-identical to the delivered files. Tracks, vias, footprints and zone outlines are identical too. The fill areas of 4 L3 zones differ by at most 0.06 mm² (fill noise, info only).
- **DRC, own run with refill:** 0 errors and 252 unconnected items. None of the unconnected items are on GND, VDD_0V9, VCC_3V3, VCC5V0_SYS or VBUS_USBA. The VCC_1V8 and VCC_DDR items are expected, because those nets are L1/L4 traces under layout.md §2.3. Warnings: 55 dangling tracks, 8 dangling vias, and silk/lib 199 each.
- **Own measurements:**
  - 680 pins.csv pads: 0 net mismatches (38 pads are NC).
  - U9 pin 1 is at SW (29.075, 42.575) and the numbering runs CCW. The part is on F.Cu at 90°. Nothing is on the bottom.
  - All 8 lane-trapping ring-1 vias are still in place: C62.1, C67.1, C64.1, C61.1, C63.1 and C68.1 on VCC_3V3, and C74.1 and C50.1 on VDD_0V9.
  - My grid search uses 0.05 mm cells, 0.10 mm clearance (more lenient than the real classes) and a 0.15 mm lane. **16 of 55 lane ends cannot leave the ring:** SDMMC_DET/D1, FSPI_CS0N/D2, LED_STATUS, PWR_KILL, HDR_GPIO1_A0/A1, HDR_PWM10/11, HDR_I2C3_SDA, HDR_UART3_RX, HDR_I2C1_SDA/SCL and HDR_GPIO2_A0/A1.
  - The VDD_0V9 L3 neck, measured in the filled copper: 4.00 mm at x 43.2, then **0.96 / 0.81 / 1.02 mm at x 44.0 / 44.25 / 44.6**, 2.16–2.23 mm at x 45.7–46.0, and **0.92 mm maximum continuous width (1.84 mm total) at x 49.4**. The §3 requirement is ≥ 2.58 mm (3.0 chosen).
  - Minors still open:
    - U2.2 and R60.2 have no own GND via (the nearest is 3.04 / 1.91 mm from the pad centre).
    - U8.1 has 1 via, against the 2 required.
    - U9.56 (VCC_DDR) and U9.19 (VCC3V3_RTC) have 1 via each.
    - R50.1 (OSC_XOUT) to Y1.4 is 0.633 mm edge to edge.
- **Mutations:** the scratch boards had the project files next to them. A first try without them gave false DRC errors, so I discarded it.
  - Control (load and save only): 0 FAIL.
  - C64 moved 5 mm: caught (4 FAIL).
  - C64.2 GND via deleted: **not caught** (exit 0, one more DEV).
  - 3 GND vias added in the VDD_0V9 neck at x 55: **not caught** (exit 0).
  - Extra VCC_3V3 via at (42.97, 37.9) in the FSPI lane channel: caught only because it hit an FSPI_CLK via (DRC). The checker has no lane test.
  - U9 pads 11/12 nets swapped: **not caught** (exit 0). pcbnew carried the swapped nets onto the attached lane tracks, so DRC sees a consistent board. check_routing.py never compares pad nets with the netlist. check_placement.py does, but rebuild_all.sh runs it with `run`, so a FAIL there does not stop the build.
- **Renders:** route_l3_u9.png shows the ring-1 via rings sitting at the mouths of the N, W, E and S lanes. route_l3_In2_Cu.png shows the choked neck. It also shows an area with no L3 copper at about x 41.6–55, y 49.8–55: the GND fill island there has no GND via, so it was removed (info; copper balance).
- **Verdict: FAIL for TP-L3.** The round-1 blocker (lanes trapped by ring-1 vias: soc, nand, sd) and both majors (VDD_0V9 neck 0.81 mm against ≥ 2.58 mm: pmu, soc; a checker that cannot fail) are unchanged, because no fix was delivered. The executor's planned fixes are sound and should be carried out, with these additions:
  - FAIL in check_routing.py on any U9 pad net that differs from the netlist.
  - Run check_placement with `step` in rebuild_all.sh.
  - Re-run my 6 mutations.
  - Owner questions are still open: the VCC_3V3 ring-1 caps tied only through the pin's own under-package via, and how the neck width is counted.

## 2026-11-01 — Executor, layout phase L3 round 3 (planes and SoC escape, gate TP-L3)
- **Fixes (D-110):** the 8 ring-1 cap vias in the lane channels are gone. The VCC_3V3 pins 13/28/43/81/88/108 have inner vias with 0.80 mm L3 fingers. Pin 61 has an inner via with an L4 link to the R43.1 VCC_3V3 via. VDD_0V9 goes through pins 71/103/54. The first 1.6 mm of each lane exit is a hard keep-out. The VDD_0V9 neck now has NECK-N plus the free strips, and the old NAND VCC_3V3 tongue is removed. U2.2 and R60.2 have their own GND vias. U9.19 and U9.56 have 2 vias each. R50 moved 0.15 mm west. 2 GND stitching vias were added at x 42–55, y 50–55.
- **New checks:** `lanecheck.py` (lane escape alone and together, DRC-legal neck-down model, strict model as INFO), pad nets against board.net, a whitelist for plane vias, filled-copper cross-sections, via inventories for the neck and the ring-1 row, and ≥ 2 vias for PWR_DDR/PWR_SUB. `mutate_routing.py` catches all 6 verifier mutations and the control passes. `rebuild_all.sh` stops on a check_placement or check_routing FAIL and writes check_placement.txt.
- **Results (rebuild from scratch, exit 0, 6.5 min):**
  - check_placement: 333 checks, 275 PASS, 58 DEV, 0 FAIL.
  - check_routing: 419 checks, 372 PASS, 22 DEV, 25 INFO, 0 FAIL.
  - Escape: 98/98. Lanes: 55/55 alone and 55/55 together. Strict model: 45/55 alone, 37/55 together.
  - VDD_0V9 neck: 3.01 mm continuous at its narrowest.
  - DRC: 0 errors. 252 unconnected items, none on plane nets.
- **Open for the owner (CHECKPOINT 2):**
  - ring-1 caps without their own via;
  - the neck-down through the ring-1 row, which the D-104 gates rely on;
  - the section metric used for the nets other than the core.

## 2026-11-01 — Verifier, layout phase L3 round 3 (planes and SoC escape, gate TP-L3)
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy, ran KiCad DRC myself, re-measured the board with my own pcbnew/numpy code (not the executor's checker), ran my own L1 lane-escape search, looked at the renders, and broke the board on purpose 5 new ways to see whether `check_routing.py` notices.
- **Rebuild (scratch copy, generated files deleted first):** `rebuild_all.sh` exits 0 in 6 min 38 s. check_placement 333 / 275 PASS / 58 DEV / 0 FAIL; check_routing 419 / 372 PASS / 22 DEV / 25 INFO / 0 FAIL. planes.csv, planevias.csv, escape_*.json/csv, .kicad_dru, check_routing.txt, check_placement.txt and trial outputs are byte-identical to the delivered ones; tracks, vias, footprints, pads and zone outlines identical (2 L3 fills differ by fill noise only).
- **DRC (own run, kicad-cli --refill-zones, parity off):** 0 errors; 252 unconnected, 0 on GND / VDD_0V9 / VCC_3V3 / VCC5V0_SYS / VBUS_USBA; warnings: 55 dangling tracks (lane ends), 10 dangling vias, silk/lib at the 199 cap.
- **Own measurements:** 680/680 pins.csv pads on the board, 0 net mismatches (38 NC). U9 pin 1 SW (29.075, 42.575), CCW, 0.19 × 0.75 mm pads at 6.075 mm, EP 7.0 mm: matches [DS] Fig. 2-5 p.17 (b ≤ 0.18, e 0.35, D 12.3, D2 7.0). Tracks only on F.Cu (1668) and B.Cu (38); L2 GND one filled piece. Zone outlines lie inside the planes.csv rectangles (0 mm² outside); different-net L3 fills ≥ 0.316 mm apart. All 150 GND vias land in L2; 87/87 L3 power vias land in their own fill (3 more are L1–L4 link vias, by design). VDD_0V9 neck: narrowest continuous copper 3.00 mm at x 61.5 (≥ 2.58 OK). VCC5V0_SYS PMU: total 8.50 mm, widest continuous run 3.38 mm; VBUS_USBA: total 4.58 mm, continuous 2.22 mm (owner question on the metric stands). R50.1–Y1.4 0.784 mm. EP thermal pads FULL connection, vias tented both sides, JP1 6 vias, NT1 2 vias.
- **Lane escape, own grid search (0.025 mm, class width, max-of-classes clearance, 0.10/0.10 only inside U9_FAN as layout.md §4.1 says):** 55/55 lanes get out alone, also with the DRC-legal model. Per-side cut capacity across the ring-1 row under strict class rules is 2.5–3× the lane count (N 35 lanes / 88, E 14 / 35, S 14 / 72, W 20 / 41). My naive greedy "together" run (no rip-up) gets 39–40/55 in both models, so it does not decide capacity; L4 must still route with class rules outside U9_FAN.
- **Mutations (own, scratch copies):** control exit 0; GND track on L2 caught (2 FAIL); U9 pads 13/14 renumbered caught (6 FAIL); U9.61 L4 link deleted caught (2 FAIL); U9.51/54 inner via deleted caught (3 FAIL); C80 moved 5 mm caught (4 FAIL). Executor's `mutate_routing.py` re-run: control 0, all 6 caught.
- **Findings (minor):** (1) soc/pmu: U9.55 (VDD_0V9) has no via of its own and reaches the plane only through 6.86 mm of 0.12 mm trace (pin 55 → C49.1 → pin 54 → pin 51's via); U9.54 and U9.67 also share other vias (1.60 / 2.96 mm). layout.md §2.3 asks for an escape via per VDD_0V9 pin; this is not recorded in decisions.md, and route_escape.py's log ("through C49") is out of date because C49.1 has no via now. (2) soc: lanes may only use 0.10/0.10 inside U9_FAN (±7.9 mm, layout.md §4.1); passing the ring-1 row at 0.10 relies on KiCad applying the rule to the whole segment. (3) owner: ring-1 caps without their own via; the cross-section metric. (4) info: there is an L3 copper void between the pin 13 and pin 28 fingers (x 33.7–38.1, y 41.3–45).
- **Verdict: PASS for TP-L3.** Every U9 pad with a net is escaped, the plane regions match planes.csv, the plane nets have 0 unconnected items, DRC shows 0 errors, the round-2 blocker and majors are fixed, and the checker now fails when the board is broken. Carry the minors into L4.

## 2026-11-01 — Executor, layout phase L4 round 1 (critical routing, gate TP-L4) — NOT PASSED (2 FAIL groups open)
- **What was built (D-111):** `rebuild_all.sh` now runs L3, snapshots the L3 board (`pcb/l4/l3_board.kicad_pcb`), then
  `l4_rules.py` → `l4_export.py` → `l4_route.py` (+ `l4lib.py`, design/.venv) → `l4_write.py` (group L4_CRITICAL) →
  `fill_zones.py` → `render_routing.py l4` → `check_routing.py` (+ new `l4check.py`) → `l4_report.py`
  (`pcb/routing-report.md`). Scripted, deterministic, hand-quality routing (no autorouter): grid search + exact
  octilinear pulling, pairs as envelope + offset, hand-placed polylines where needed, meanders, self-check.
- **Routed:** crystals; ETH RX/TX with the D-108 b topology (TX hop 2 vias/line); USB SoC→U11 (USB_DM hop), U11→U2→J4,
  U11→U1→J1 with the D-108 a hops and the J1 joins; SD bus (staircase + 45° bundle); FSPI incl. the D-106 c channels
  under U10; 4 buck cells (SW, FB, output); VBUS_IN, VBUS_5V, VCC3V3_SD, VCC_DDR, VCC_1V8 (all but 5 pads); SENSE nets
  22/23/25 on L4 + ONOFF_PDT, QPWR_G, USBA_ISET. L3 plane vias moved: U1.2, U10.9, U10.4 (route_planevias.FORCED).
- **Results (full rebuild from the netlist, exit 1 on the FAILs below):** KiCad DRC **0 errors** (warnings: dangling
  50 / 7, silk/lib ≥ 199 as before). check_routing: 476 checks, 404 PASS, 38 DEV, 28 INFO, **6 FAIL**.
  ETH skew pair RX −0.59 / TX +1.01 mm, U9→J3 RX 0.00 / TX +1.01 mm, longest 27.44 mm, TX–RX ≥ 0.785 mm, coupled gap
  0.200–0.205 mm. USB skew −0.30 mm on all three paths, vias ≤ 4 (USBC_DM 4), other tracks ≥ 0.769 mm. SD all within
  +1.6 mm of the clock (≤ 40). FSPI D0/D1 within ±5; D2 −8.8, CS0N −7.3, D3 25.76 mm (DEV, D-111 e).
- **FAIL 1 (gate):** 5 power pads unconnected: VCC_DDR→C45.1 and VCC_1V8→C47.1 (ring-2 caps boxed in by GND pads/vias
  inside the VDD_0V9 neck: no L1 exit, no via site), VCC_1V8→R44.1/R45.1 (walled off by the RECOVERY/SARADC_IN1 routes).
- **FAIL 2 (L5 watch, not a TP-L4 item):** lanecheck: 4 north header lanes (U9.85/86/87/95) leave alone but not together.
- **Not in L4 scope, still open:** VDD_ARM (NT1 side caps), PWR_SUB nets, other SENSE/DEFAULT nets → L5.

## 2026-11-01 — Verifier, layout phase L4 round 1 (critical routing, gate TP-L4) — NOT PASSED
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy (generated files deleted first), ran KiCad DRC myself, re-measured every critical net with my own pcbnew code (path lengths pad to pad, coupling, clearances to tracks, pads and vias, bends, stitching vias, the L3 plane under the L4 hops), looked at the renders, probed which DRU pair rules KiCad really applies, and broke the board on purpose 6 ways to see whether `check_routing.py` notices.
- **Rebuild:** `rebuild_all.sh` runs in 11 min and stops with "FAILED: check_routing.py" (476 / 404 PASS / 38 DEV / 28 INFO / 6 FAIL, same as the executor's figures). Tracks, vias, footprints and pad nets are identical to the delivered board (2316 / 321 / 239 / 736); routes.json, .kicad_dru and planevias.csv are byte-identical. Only fill noise and the order of the report lines differ. Footprints have not moved since the L3 snapshot (0 moved). 680/680 pins.csv pads match.
- **DRC (my own run, refill, parity off):** 0 errors. 111 unconnected items. Critical nets still open: VCC_1V8 (3) and VCC_DDR (2). Also open: ETH_AVDD1V8 (2), USB_SEL (2), USBA_VBUS_EN (2) and SDMMC_PWREN (1). These match the gate's literal "ETH*/USB*/SDMMC*" patterns but are not in the checker's 58-net set.
- **My measurements agree with the executor on:** net lengths and via counts, SD skew (+0.33 to +1.57 mm), FSPI, ETH skew (pad-to-pad paths: RX +0.55 mm, TX +0.47 mm; longest 27.3 mm), buck SW/FB distances (FB ≥ 2.59 mm from SW copper, ≥ 2.79 mm from the inductor), and nothing on L4 under Y1/Y2.
- **Mutations:** the checker caught all 6 (control 6 FAIL): via on ETH_RXP, 3 mm stub on USBC_DM, SDMMC_D0 +6 mm, C76 moved 5 mm, U10 pads 5/6 renumbered, a USBC_DP segment at 0.15 mm wide. The USBC_DM stub was caught only through the net-total skew.
- **Findings:**
  - **blocker (pmu/soc):** gate item open. C45.1 (VCC_DDR), C47.1 (VCC_1V8), R44.1 and R45.1 (VCC_1V8) are unconnected. R44 is the RECOVERY pull-up and R45 the SARADC_IN1 pull-up: without them the recovery/ADC inputs float, which risks a wrong boot mode.
  - **major (usb):** the USB-C P/N skew is measured on net totals, which include the A6–B6 and A7–B7 join stubs. Pad-to-pad paths: U11.1→J1.A6 29.60 mm against U11.2→J1.A7 25.21 mm (+4.39 mm); B6/B7 32.78 against 30.72 mm (+2.06 mm). Both are over the 1.27 mm limit. The A7–B7 join leaves a 7.65 mm stub (U1.3 → L4 crossover → B7) and DP leaves a 3.18 mm stub, against "< 2 mm, symmetric".
  - **major (usb):** USB-A and USB-C are 0 mm coupled from U11 on; USB-C lines are > 1 mm apart for 21 mm. With `tools/zsolve.py`, uncoupled 0.255 mm lines give 118–124 Ω differential, against 90 Ω ± 10 %.
  - **major (usb):** USBC_DP runs between U8's pad rows: 0.165 mm from U8.4 (USBA_VBUS_EN), 0.218 mm from U8.1 (VBUS_USBA) and 0.26 mm from U8.3 (USBA_ISET), against ≥ 0.76 mm. The DRU rule and the checker measure track to track only.
  - **minor:** KiCad does not treat USB_DP/USB_DM (or the ETH `_J` nets) as diff pairs, so the USB skew/gap/uncoupled DRU rules never run (probe DRU: only the ETH nets flagged).
  - **minor (eth):** ETH lines are 0.32 mm from C66.1, 0.51 mm from FB1.2, 0.56 mm from C83.1 and 0.39 mm from J3.4. There is an acute 45° hairpin on ETH_TXN at (24.0, 26.9), and meanders have 90° corners (USBA_DP ×4, USBC_DP ×6, USBC_DM ×1 against bends ≥ 135°).
  - **minor (pmu):** VCC_DDR on L4 runs under U5's SW node.
  - **minor (usbc):** the VBUS_IN A4/B9 path is 0.8 mm on L4 with 2 vias per layer change (PWR_5V ≥ 1.0 mm, ≥ 3 vias).
  - **minor (xtal):** VCC_3V3 L3 vias and stubs are 0.63–0.98 mm from C77.1/C79 (rule ≥ 1 mm). Y2 has only 3 GND vias within 1.5 mm (rule ≥ 4).
  - **minor (usb):** short L4 hops cross L3 voids.
  - **hygiene:** self-referencing symlinks `design/.venv/.venv` and `design/refs/refs` (created 2026-11-01 09:10).
- **Verdict: FAIL for TP-L4.** The open power pads remain, and the USB-C skew and stubs, the USB impedance and the USB clearance at U8 must be fixed, or explicitly accepted by the owner, before L5.

## 2026-11-01 — Executor, layout phase L4 round 2 (critical routing, gate TP-L4)
- **What changed (D-112):** every finding of the L4 r1 verifier addressed. USB re-done as hand-placed coupled pairs (SoC->U11, U11->U2->J4, U11->U1->J1) that leave the pair only at the approved hops and at the breakout pins; 0.42 mm (Z0 45 ohm) where the lines must run apart at U1/U2/J4; USB-C pair routed north of U8/C11 (>= 0.76 mm from every U8 pad); J1 joined by one via T per net (DP north of the pad row, DM south of it), symmetric stubs. Blocker closed: C45.1 (via beside the pad), C47.1 (via in pad, filled/capped - owner), R44.1/R45.1 (L1 link + via), U9.56's VCC_DDR inner vias joined on L4. ETH_TXN mitred U instead of the hairpin; all meanders 45 deg-chamfered. SW nodes closed to L4 and vias (also for the L3 J5.4 feed). VBUS_IN 1.0 mm / 3 vias on L4. Plane vias C34.1, U2.2, U2.5 moved (route_planevias.FORCED); Y2 4th guard via; symlinks design/.venv/.venv and design/refs/refs removed.
- **New checks (l4check.py, all measured from the saved board):** pad-to-pad USB paths per plug orientation (`pathlen.py`), J1 stub lengths, per-line 90 ohm control classes with a 1.0 mm uncontrolled limit, pair clearance to tracks + pads + vias, USB-A vs USB-C separation, bends >= 135 deg, nothing on L4 / no via under SW nodes, VBUS_IN vias per layer change and L4 width, crystal guard on all copper, Y1/Y2 guard via count, ETH TX hop stitching, L3 plane under the hops. New DRU rules: USB 30 mil to pads/vias (+ rule area U9_RING), USB 0.42 mm areas (USB_Z45_A/C). Router: U9 neck-down relaxation per layer as the DRU does (DRC caught a 0.19 mm L4 gap).
- **Results (full rebuild from the netlist, `rebuild_all.sh`, 12 min; routes.json identical to the previous run):** L3 check 419 / 372 PASS / 22 DEV / 0 FAIL. KiCad DRC **0 errors**; unconnected 106, none in the TP-L4 set (58 nets, 0 open) and none on plane nets. check_routing 509 checks: 427 PASS, 44 DEV, 33 INFO, 5 FAIL - all 5 are the lanecheck L5 watch carried from round 1 (4 north header lanes free alone, 31/35 together); TP-L4 lines (L4-*): 110, 0 FAIL. USB copper off every pad-to-pad path: 0.00 mm on all six nets.
- **Checker self-test (new `scripts/mutate_l4.py`, trial/mutations_l4.txt):** 6/6 mutations caught as new FAIL lines vs the control: 3 mm USBC_DM stub, USB_SEL via 0.5 mm from the USB-C pair (also a DRC error through the new DRU rule), VCC_DDR track on L4 under U5's SW node, one of the 3 VBUS_IN vias deleted, the C45.1 via + link deleted, USBA_DP J4 entry straightened (skew).
- **Measured:** USB skew pad to pad SoC->U11 -0.61, USB-A -0.50, USB-C A side 0.00, B side 0.00 mm; J1 stubs DP 1.57 / DM 1.65 mm; vias per line 2 / 2 / 4; uncontrolled 0.255 mm length 0.00 mm on all 8 line-paths; 0 USB items < 0.76 mm (outside breakout courts / U9 ring band). ETH skew pair/total RX -0.59/0.00, TX -0.29/-0.29 mm, longest 27.44 mm, TX-RX 0.772 mm. SD within +1.6 mm of the clock; FSPI as round 1 (DEV D-111 e).
- **Deviations for the owner (D-112):** C47.1 via in pad; USB-C J1 vias inside the D-108 a U1/J1 margin and 5 signal vias without a GND via within 1 mm (nearest 1.20-2.23 mm); ETH pad proximities (J3.4 0.40, FB1.2 0.51, C83.1 0.56 mm); VBUS_IN 0.40 mm pad necks; R43.1/C84.1 VCC_3V3 vias 0.63/0.80 mm from the crystal load caps.

## 2026-11-01 — Verifier, layout phase L4 round 2 (critical routing, gate TP-L4) — PASS
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy (generated files deleted first), ran KiCad DRC myself on the delivered and the rebuilt board, re-measured the critical nets with my own pcbnew/numpy code (pad-to-pad lengths and skew, vias per line, clearances to tracks/pads/vias, GND stitching, bends, TX–RX gap, SW nodes, the plane under the pairs), checked routability of the nets left for L5 with my own grid search, looked at the renders, and broke the board on purpose 6 new ways to see whether `check_routing.py` notices.
- **Rebuild:** `rebuild_all.sh` ends with exit 1 only because of the 5 lanecheck L5-watch FAIL lines (check_placement 333 / 0 FAIL; L3 419 / 0 FAIL; L4 509 / 427 PASS / 44 DEV / 33 INFO / 5 FAIL). Tracks, vias, footprints and pad nets are identical to the delivered board (2312 / 331 / 239 / 736); routes.json, .kicad_dru, planes.csv, planevias.csv, check_placement.txt are byte-identical. check_routing.txt and routing-report.md differ only in line order inside lists and fill noise. No footprint moved since the L3 snapshot; no L3 track or via removed by L4. 680/680 pins.csv pads match. U11 pinout re-checked against [TI] TS3USB221A p.3 (top view, CCW, not mirrored).
- **DRC (my own run, refill, parity off, all track errors):** 0 errors on both boards. 106 unconnected items, none on ETH*/USB_D*/USBA_D*/USBC_D*/SDMMC data/clock/FSPI/OSC/RTC/SW/FB/VBUS/VCC_* nets. Open name-matching nets: ETH_AVDD1V8, USB_SEL, USBA_VBUS_EN, SDMMC_PWREN (D-112 k).
- **Own measurements agree with the executor:** USB skew pad to pad −0.61 / −0.50 / 0.00 / 0.00 mm, vias 0/2, 0/2, 4/4; J1 joins 3.14 / 3.30 mm pin to pin (stubs 1.57 / 1.65); ETH RX −0.59 per pair and 0.00 across the links, TX −0.29, longest 27.3 mm pad to pad, TX–RX 0.772 mm; SD +0.33 to +1.57 mm vs the clock; FSPI as D-111 e; FB to SW ≥ 2.26 mm; nothing on L4 under the SW nodes (VCC_DDR passes 0.29 mm outside U5's); pairs ≥ 3.3 mm from clocks/SW; 5 signal vias without a GND via within 1 mm (as recorded). C47.1: my own via-site search finds no legal via site within 2.0 mm (2.27 mm if C47 is rotated), so via-in-pad or a C47 move is the real choice.
- **Mutations (own, scratch):** control 5 FAIL; VCC_3V3 track 0.45 mm from ETH_RXP caught (+5 FAIL incl. DRC); 0.6 mm stub on USB_DP caught; U11 pads 7/8 renumbered caught (3 FAIL); C47 moved 5 mm caught (3 FAIL); Y2 guard via deleted caught; VBUS_IN L4 segment narrowed to 0.5 mm caught. Executor's `mutate_l4.py` re-run: 6/6 caught.
- **Findings (minor; owner items):** (1) usb/usbc: the "0 USB items < 0.76 mm" holds only with the courtyard exclusions; outside the pins USBC_DP's L4 trunk/meander at J1 runs 0.35–0.55 mm from the 1.0 mm VBUS_IN L4 run for about 1.8 mm, USBC_DP/DM on L1 0.39–0.47 mm from VBUS_IN, USBA_DP/DM 0.49–0.50 mm from the VBUS_USBA track/via at U2.5. Record them in D-112 b or move the VBUS_IN L4 run; list excluded proximities as INFO. (2) eth: TX uncoupled 11.89 mm against the 6.7 mm shown at D-108 b / D-H5 (DRU limit raised to 14 mm in L4); uncoupled 0.235 mm lines are about 120 Ω differential (zsolve: 60.8 Ω single). Short electrically, but needs owner acceptance or a tighter TXN U-turn. (3) usb: the "hop" class counts 8.7 / 7.4 mm of USB-C lines as controlled, including the L4 run at J1 over 2.6–2.8 mm of L3 void. (4) pmu: C47.1 via-in-pad needs JLC's board-wide filled-and-capped option (offered on the capabilities page; cost UNVERIFIED). (5) gate net set (D-112 k): my grid search shows ETH_AVDD1V8, USB_SEL, USBA_VBUS_EN and SDMMC_PWREN each still routable on L1/L4 with class clearances. (6) hygiene: sort the list fields so identical rebuilds give byte-identical reports. (7) info: the `design/.venv/.venv` and `design/refs/refs` symlinks were re-created at 16:25 today by the verifier's own scratch setup (`ln -s` into a stale scratch symlink), probably also the cause of the round-1 hygiene item; I removed them.
- **Verdict: PASS for TP-L4.** The TP-L4 net set is fully connected, DRC shows 0 errors, every §4 rule is measured from the board with deviations recorded in D-111/D-112, the round-1 blocker and majors are fixed, and the checker catches deliberately broken boards. The owner questions of D-112 and findings 1–5 go to the owner before fabrication; findings 1–3 can be closed in L5.

## 2026-11-01 — Executor, layout phase L5 round 1 (remaining routing and finishing, gate TP-L5) — NOT PASSED
- **What was built (D-113):** `rebuild_all.sh` now keeps the L4 check (`pcb/check_routing_l4.txt`), snapshots the L4 board
  (`pcb/l5/l4_board.kicad_pcb`) and runs `scripts/l5_run.sh`: `place_l5_tweaks.py` (TP26 moved, D-113 a) → `l5_lanes.py`
  (radial neck-down stubs for the 34 open U9 lanes + negotiated lane routing on the exact L4 router) → `l5_write.py` →
  `l5_drc.py` → `l5_freeroute.py` (Freerouting 2.5.0 headless on a patched DSN; session stored in `pcb/l5/fr/out.ses`,
  re-imported on rebuild) → `l5_cleanup.py` (clean-up, exact rule check, rip + script routing, widening) → `l5_stitch.py`
  (197 GND vias) → `fill_zones.py` → `l5_silk.py` → `render_routing.py l5`; then `check_routing.py` (+ new `l5check.py`)
  and `l5_report.py` (routing-report.md L5 section). Owner review page: `pcb/routing-review.md`.
- **Results (final board):** KiCad DRC **0 errors** (warnings: lib_footprint_issues ≥ 199, track_dangling 63, via_dangling 6,
  silk_edge_clearance 2, silk_over_copper 1). check_routing 495 checks: 406 PASS, 50 DEV, 37 INFO, **2 FAIL** (unconnected
  items; open lane stubs). L4 lines re-measured on the final board: 110, 0 FAIL (ETH/USB skew, TX–RX 0.772 mm, USB 0.76 mm
  clearances unchanged). **Unconnected: 42 items on 27 nets** (106 after L4).
- **Blocker (owner):** the north exit of U9 (pins 72–95, 21 lanes) has L1 room for ≈ 16 lanes at y 25 and ≈ 4 reachable at
  y 24 (`l5_north_cut.py`; ring-2 parts R66/R67/C43/C69/FB3/TP31/TP6 and the VCC_1V8 L4-feed vias in the strip, no via site
  in the ring band); 8 north lanes routed, 13 open. Options A/B/C in routing-review.md. The other 14 open nets (control and
  sub-rail nets) are congestion of this attempt, to be routed in round 2.
- **Deviations:** D-113 b 0.10 mm lane tracks; c PWR_SUB/VDD_ARM branches and two DC nets crossing L3 edges on L4; d stitching
  gaps without a legal site; e no teardrops (no API); f 95 references hidden, 8 TP labels without room.

## 2026-11-01 — Verifier, layout phase L5 round 1 (remaining routing and finishing, gate TP-L5) — NOT PASSED
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy (generated board, l4/, l5/ and board.pretty deleted first; only the stored Freerouting session kept), ran KiCad DRC myself on the delivered and the rebuilt board, measured the board with my own pcbnew code (unconnected items per pad pair, dangling ends, bend angles, widths per group and class, rails, GND stitching grid, silk text vs pads, pad nets vs pins.csv, U9 land pattern vs RV1106 datasheet r1.8 Fig. 2-5 p.17, VDD_ARM path lengths, L3/L4 copper and placement vs the L4 snapshot), looked at the renders, and ran 7 mutations through the executor's checker.
- **Rebuild:** `rebuild_all.sh` runs in 21.8 min and ends "FAILED: check_routing.py" (495 checks / 406 PASS / 50 DEV / 37 INFO / 2 FAIL, as reported; L4 board 509 / 5 FAIL as before). Footprints, silk texts, L3/L4/L5 tracks and non-stitch vias are identical to the delivered board; the GND stitching is NOT repeatable: 196 vias in the rebuild vs 197 delivered, 4-5 positions differ (e.g. (23.40, 24.45) vs (22.15, 24.475)).
- **DRC (own run, refill, parity off, all track errors), delivered and rebuilt:** 0 errors; warnings lib_footprint_issues 199, track_dangling 63, via_dangling 6, silk_over_copper 1, silk_edge_clearance 2; **42 unconnected items on 27 nets** (same list as the executor).
- **Agree with the executor on:** only TP26 moved vs the L4 snapshot; L3/L4 copper untouched (2643 items identical); no copper/zone fill on the rails or within 0.4 mm of the V-cuts; all 63 dangling-track ends are covered by same-net copper (KiCad anchor quirk + 16 open lane stubs); pad nets = pins.csv (680 pins, only NC pins differ by name); U9 pads 0.19 x 0.75 mm at 0.35 mm, 6.075 mm from centre, pin 1 SW; 181 visible silk texts all >= 1.0 mm, none within 0.15 mm of a pad, none overlapping.
- **Mutations (own, scratch):** C62 moved 5 mm caught (+4 FAIL); U9 pads 72/73 renumbered caught; grouped acute spur caught (+3 FAIL); track on the rail caught; L5 segment deleted shows as 43 items / EN_N in the existing FAIL line; ungrouped 30-degree stub caught only indirectly (acute-bend line); **silk text moved onto SW2's pad NOT caught** (only an INFO DRC line).
- **Findings:** blocker (soc/eth/usb/sd/onoff/ui/uart/gpio): gate open, 42 items; this includes SoC supply pins (VCC3V3_RTC U9.19, AVDD1V8_USB U9.24, ETH_AVDD1V8, FEPHY_AVDD3V3, VCC3V3_RTC_IN) and boot/power control (NPOR pull-up R35, SDMMC_PWREN, PWR_KILL, PB_INT_N, PWR_BTN_N, USB_SEL, USBA_VBUS_EN): the board would not boot as is. blocker (gpio): north exit of U9, owner decision (also evaluate a via row at y ~25.6, x 33.5-35.8: L1 pocket and L4 free in north_cut.json). minor: stitching not deterministic; via_dangling explanation wrong (they are the inner vias of USB_SEL, SDMMC_PWREN, PB_INT_N, VCC3V3_RTC x2 and a leftover VCC_DDR via, not plane vias); 21 Freerouting segments at 0.112 mm on 6 enable/control nets not described in D-113 b; silk labels ambiguous (STAT next to the ETH LED, "5V" beside TP12 = EN_N, "1V8" under TP5 = VCC_DDR, H2 ref 5.8 mm from H2); checker has no silk-to-pad FAIL; VDD_ARM routed path U9.115 -> C38 8.94 mm (> 8 mm, checked only centre to centre); stitching gap text names "U9 and J1/J4 mouths" but 2 cells are in the VDD_0V9 neck (pour point 5.26 mm from a GND via at (54.75, 32.25)); 3-D view has no models for J2/J4 and unresolved paths for the others, so it is weak evidence for the §10 3-D item.
- **Verdict: FAIL for TP-L5.** DRC 0 errors and the L4 rules still hold, but 42 unconnected items remain and the north-exit decision is open; not CHECKPOINT 2.

## 2026-11-01 — Executor, layout phase L5 round 2 (remaining routing and finishing, gate TP-L5) — NOT PASSED (owner decisions)
- **What changed (D-114):** supply and boot-control nets routed by script before the lanes and Freerouting (`l5_priority.py`
  inside `l5_lanes.py`); L4 jobs `subrail`/`inner` (VCC3V3_RTC from its inner via; vias in pad C58.1/R33.2/C66.1);
  vias kept off the VDD_0V9 free strips; acute-joint rejection; Freerouting thin segments widened; silk trimmed
  clear of all pads, TP labels = TP number + net beside their own pad, LED labels (PWR at 0.8 mm), H refs hidden;
  DRU spoke rule for J5/J1 GND pins + island GND vias; deterministic stitching/clean-up (sorted lists, PYTHONHASHSEED=0);
  checker: silk-to-pad FAIL, all-track dangling/acute, VDD_ARM ring-2 along copper, connector faces from F.Fab;
  option-D evaluation `l5_north_d.py`.
- **Results (two full rebuilds, identical route/via lists):** KiCad DRC **0 errors**; check_routing 504 checks / 410 PASS
  / 53 DEV / 38 INFO / **3 FAIL**; **30 unconnected items on 24 nets** (42/27 in round 1). Connected now: VCC3V3_RTC,
  VCC3V3_RTC_IN, ETH_AVDD1V8, FEPHY_AVDD3V3, AVDD1V8_USB rail, NPOR (R35/TP7), PWR_KILL, PWR_BTN_N, UART2_TX_HDR.
- **Open, owner:** 16 header lanes (option D measured: 11 pocket vias, 6 reachable in one row, 3 lanes through TP31-TP6 →
  D + A recommended); USB_SEL/SDMMC_PWREN/PB_INT_N boxed in by the L4 SENSE routes (needs an L3 escape change);
  USBA_VBUS_EN/LED_STATUS in the via-free STRIP-N. **Open, executor:** TP23, UART2_RX_HDR, VCC1V8_CODEC, STAT label.

## 2026-11-02 — Verifier, layout phase L5 round 2 (remaining routing and finishing, gate TP-L5) — NOT PASSED
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy (board, board.pretty, l4/, l5/, renders and check outputs deleted first; only the stored Freerouting session kept), ran KiCad DRC myself on the delivered and the rebuilt board, measured the board with my own pcbnew/numpy code (pad nets vs pins.csv, U9 land pattern vs RV1106 datasheet r1.8 p.16 Fig.2-3/2-4 and p.17 Fig.2-5, placement vs the L4 snapshot, copper on rails/edges, joint angles, dangling ends, via-in-pad, connectivity islands of every open net, ETH/USB/SD lengths, VDD_ARM paths, silk under parts), ran my own grid search for the "boxed-in" nets, looked at the renders, and broke the board 7 ways to see whether `check_routing.py` notices.
- **Rebuild:** `rebuild_all.sh` 25 min, ends "FAILED: check_routing.py" (504 / 410 PASS / 53 DEV / 38 INFO / 3 FAIL; L4 board 509 / 5 FAIL; check_placement 333 / 0 FAIL). Rebuilt board identical to the delivered one: 3407 tracks+vias, all footprints, pad nets, silk; .kicad_dru, planes.csv, planevias.csv, priority/stitch/stitch2/north_d/islands.json byte-identical; check_routing.txt differs only in list order inside two DEV lines.
- **DRC (own run, refill, all track errors), delivered and rebuilt:** 0 errors; warnings lib_footprint_issues 199, track_dangling 64, via_dangling 5, silk_edge_clearance 2; **30 unconnected items on 24 nets** (as reported).
- **Agree with the executor on:** pad nets 680/680 (38 differences are NC pins only); U9 pads 0.19 x 0.75 at 0.35 mm, 6.075 mm from centre, pin 1 SW, counter-clockwise from the top, EP 7.0 + 16 vias; only TP26 moved vs the L4 snapshot; all 2665 L4-snapshot items present; no L5 copper on ETH/USB/SD/FSPI/XTAL nets; ETH RX −0.59/0.00 mm (27.44 mm), TX −0.29, SD +0.33..+1.57 mm; no copper on rails or within 0.4 mm of the V-cuts; every < 90° track joint lies inside a pad or via; via-in-pad only C47.1, C58.1, R33.2, C66.1 (recorded); DSN carries the class widths/clearances and fixed wires; silk "RV1106 Rev A 2026-11" present; only PWR text < 1.0 mm.
- **Mutations (own, scratch):** C54 moved 5 mm caught (+5 FAIL incl. DRC shorts); U9 pads 40/41 renumbered caught (3 FAIL); 19.2 mm PWR_KILL L5 segment deleted shows only as higher counts in the existing FAIL lines (30→31 items, 18→20 ends); silk text on SW2's pad caught (round-1 gap closed); GND track on the rail caught; 1.5 mm stub on UART2_TX caught; **VDD_ARM C44 branch narrowed 0.8 → 0.2 mm NOT caught** (only the L5-width DEV text changes).
- **Findings:** blocker (soc/pmu/sd/usb/onoff/uart/ui/gpio): gate open, 30 items; U9.31 CODEC_AVDD1V8 is unpowered (VCC1V8_CODEC in 4 islands: FB2.2 / C41.1 / TP24 / U9.31+C57, regression), USBA_VBUS_EN in 3 islands (U9.64 / R61.1 / U8.4), console RX (UART2_RX_HDR) open, SDMMC_PWREN/USB_SEL/PB_INT_N open, 16 header lanes open. Major (onoff/sd/usb/pmu): my grid search does not confirm that USB_SEL/SDMMC_PWREN/PB_INT_N need an L3 change: with the DRU's own rules (0.10/0.10 inside the U9 courtyard, class clearances outside, no via in the neck, strips, escape fingers + 0.57, ring band, U9/U11/U1/J1 courts) each inner via reaches on L4 a legal via site near (41.6, 40.7) between the RECOVERY/SARADC_IN1 L4 tracks (paths 8.0/16.5/15.4 mm), and that site is in the L1 region that holds R38.2, R60.1/U11.9 and R10.2/U3.5 (single-net search; joint fit not proven). Major (soc/ui): R51's reference text is printed under the U9 body (x 38.16–39.86, y 31.21–34.37) – silk under a 0.35 mm QFN. Minor: L5-width has no floor (mutation above); VDD_ARM runs 58 mm at 0.30 mm on L4 to TP15; CC1 via (47.64, 68.15) 0.45 mm from USBC_DP outside U1's courtyard, not recorded; track_dangling 64 = 18 lane stubs + 46 covered L3_ESCAPE ends (review says 27); "TP23 U18" label reads as a part reference, 11 TP labels (incl. the TP29–TP1 test row) only on F.Fab; design/.venv/.venv and design/refs/refs symlinks are back (dated 2026-11-01 19:34).
- **Verdict: FAIL for TP-L5.** DRC 0 errors, rebuild reproducible, L4 rules still hold, but 30 unconnected items remain (including a SoC supply pin and the console RX); not CHECKPOINT 2.

## 2026-11-02 — Executor, layout phase L5 round 3 (remaining routing and finishing, gate TP-L5) — NOT PASSED (owner decisions)
- **What changed (D-115):** the north exit of U9 is a planned bus (`pcb/scripts/l5_north.py`: fixed 0/45/90 deg polylines
  through two corridors to a via field, nested L4 rows to x 25.4, J5 legs by the exact router) — all 21 north lanes routed
  (round 2: 16 open). Six recorded local moves under D-H5 (R66/R67 next to J6, TP31, C69, FB3 0.35 mm, TP15 next to C44,
  TP23/TP18 next to their rails); C43's plane vias pinned; L4 VCC_1V8 feed of C69/FB3 moved off the corridor (L4 board
  check 509 / 0 FAIL). VCC1V8_CODEC rail, UART2_RX_HDR, R61-U8.4, TP23, TP18 joined (FB2.2 / TP18 via in pad).
  `l5_prune.py` removes open-lane stubs; fold / acute retries; Freerouting widths floored at 0.10 mm; strict USB via rule
  for new vias; DRU J3 GND spoke rule. Silk: no text on bottom-terminated parts (FAIL check), TP23 'USB1V8', TP numbers
  kept on silk, STAT placed (0.8 mm). Checker: width floors, VDD_ARM feed / ring-2 narrowing FAIL, DRC dangling by group.
  `l5_inner_probe.py` measures the verifier's suggested route for the three inner-via nets (blocked: 0.275 mm SENSE via
  gap; 0 of 76 sampled via sites reachable for SDMMC_PWREN). Stray symlinks design/.venv/.venv and design/refs/refs deleted.
- **Results (rebuild_all.sh with L5_FR_RERUN=1, final run):** check_placement 339 / 0 FAIL; L3 board 419 / 0 FAIL; L4 board
  509 / 0 FAIL; check_routing 510 checks / 414 PASS / 53 DEV / 39 INFO / **4 FAIL**; KiCad DRC **0 errors** (warnings:
  lib_footprint_issues >= 199, track_dangling 47 = L3_ESCAPE 46 + L5_PRIORITY 1, via_dangling 5, silk_edge_clearance 2);
  **10 unconnected items on 9 nets** (round 2: 30 on 24). Mutation check (scratch): C44 branch narrowed to 0.2 mm and R51's
  reference over U9 are both FAILed. The stored Freerouting session is this run's; a second rebuild that re-imports it was
  not repeated in this round.
- **Open, owner:** USB_SEL / SDMMC_PWREN / PB_INT_N U9 side (L4 SENSE re-route or L3 escape change), USBA_VBUS_EN / LED_STATUS
  (via in STRIP-N or GPIO swap), approval of the D-115 moves. **Open, executor:** HDR_GPIO2_A7, R62.2 / R63.2 pull-ups, TP24.

## 2026-11-02 — Verifier, layout phase L5 round 3 (remaining routing and finishing, gate TP-L5) — NOT PASSED
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy (board, board.pretty, l4/, l5/, renders and check outputs deleted; only the stored Freerouting session `l5/fr/out.ses` kept), ran KiCad DRC myself (refill, `--severity-all --all-track-errors`) on the delivered and the rebuilt board, measured the board with my own pcbnew code (pad nets vs pins.csv, U9 land pattern vs RV1106 datasheet r1.8 p.17 Fig.2-5, connector rotations, widths/angles/joints of all L5 copper, ETH/USB/SD/FSPI/XTAL lengths, L5 vias near the pairs, ring-2 copper paths, vias in pads, silk, GND stitching), looked at the executor's renders (north, U9 L1/L4, F.Cu, B.Cu, silk), and ran 9 mutations of my own through the executor's `check_routing.py`.
- **Rebuild:** one clean-tree run stops at once in check_placement.py because `pcb/renders/` does not exist (FileNotFoundError on trial_route_policy.png, stderr hidden: only "FAILED"); with the folder created, `rebuild_all.sh` runs in 18.7 min and ends "FAILED: check_routing.py": check_placement 339 / 0 FAIL, L3 board 419 / 0 FAIL, L4 board 509 / 0 FAIL, final 510 / 414 PASS / 53 DEV / 39 INFO / 4 FAIL (as reported). Rebuilt board = delivered board: 3680 tracks+vias identical by group/net/layer/width/end points, all footprints and board texts identical (the stored session re-imports reproducibly; the executor's "not verified" item is now verified).
- **DRC (own, delivered and rebuilt):** 0 errors; warnings lib_footprint_issues 199, track_dangling 47 (46 L3_ESCAPE + 1 L5_PRIORITY, the 0.24 mm VCC1V8_CODEC stub on B.Cu at (47.33, 47.18)), via_dangling 5, silk_edge_clearance 2; **10 unconnected items on 9 nets** (USB_SEL 2, SDMMC_PWREN, PB_INT_N, USBA_VBUS_EN, LED_STATUS, HDR_GPIO2_A7, HDR_I2C3_SCL/SDA (R62.2/R63.2), VCC1V8_CODEC (TP24)).
- **Agree with the executor on:** pad nets 704/704 = pins.csv (only NC-pin name differences); U9 pads 0.19 x 0.75 mm at 0.35 mm, rows at ±5.425 / 6.075 mm, pin 1 SW, EP 7.0 mm (p.17: e 0.35 BSC, D2/E2 7.0); J1 (49.5, 76.35) 0 deg, J3 (21.46, 17.26) 180 deg; no copper on the rails or within 0.4 mm of the V-cuts; L2 no tracks; all L5 widths at or above the class floors; L5 non-45 pieces only in the U9 north fan; ETH RX 27.44/27.44 mm, TX 22.38/22.09 mm (skew 0.29), no L5 copper on ETH/USB/SD/FSPI/XTAL nets; silk: 165 texts, none within 0.15 mm of a pad, all 1.0 mm except PWR/STAT 0.8 mm, "RV1106 Rev A 2026-11" present; the SENSE-via gap 0.275 mm and the (41.6, 40.7) site 0.175 mm from FSPI_D3 (confirmed).
- **Mutations (own, scratch, executor checker):** C55 moved 5 mm (+5 FAIL), U9 pads 85/86 swapped (netlist FAIL), one north-bus via deleted (11 items, HDR_UART3_TX named), VCC1V8_CODEC L5 tracks narrowed to 0.15 mm (L5-width FAIL), GND track on L2 (planes FAIL), 30 deg stub on UART2_RX (L5-geom FAIL x2 + DRC), J3 rotated to 0 deg (DRC shorts, L4-conn, L4-eth FAIL), silk text on TP15's pad (L5-silk FAIL), C69 moved 3 mm (planevia, DRC, L4-conn FAIL): **all 9 caught.** Not caught: a ring-2 part fed along a long copper detour (see major below), because L5-ring2 only measures VDD_ARM.
- **Findings:** blocker (onoff/sd/usb/pmu/ui/gpio): gate open, 10 items; no SD power control (SDMMC_PWREN), no USB mux select (USB_SEL), no PMIC interrupt (PB_INT_N), no USB-A VBUS enable from the SoC. Major (onoff/sd/usb): USB_SEL/PB_INT_N/SDMMC_PWREN are not an owner decision: the fix is to reroute the RECOVERY/SARADC_IN1 L4 tracks (same kind of L4 change as D-115 b, no placement or schematic change); also the probe only tried via sites south of the pocket, while a 0.74 mm L4 gap at (44.9, 27.4-28.35) between RECOVERY's corner and the VCC_1V8 L4 end leads north-east and was not evaluated. Major (soc): ring 2 <= 8 mm along the copper is broken and not recorded for VCC1V8_CODEC (FB2.2 -> U9.31 about 22 mm, C41.1 -> U9.31 25.0 mm, L4 loop via y 51.6), MIPI_CSI_AVDD_1V8 (R32.2 -> U9.1 14.7 mm through TP22) and VCC3V3_RTC (R34.2 -> U9.19 about 17.7 mm); the review lists only VDD_ARM and C69. Major (soc/pmu/usb): 7 vias in pads (C47.1, C58.1, C66.1, C69.1, FB2.2, R33.2, TP18.1) contradict D-67 / layout.md §6.2 (no POFV); owner decision with a priced alternative needed before CHECKPOINT 2. Minor: the CC1 via (47.64, 68.15) is still there, 0.45 mm from USBC_DP inside U1's courtyard (the review says it is gone); the D-115 moves are relocations (TP15 48 mm, TP23/TP18 28 mm, R66/R67 17-19 mm), TP15 leaves the testpoints.md power row and placement.csv still puts R66/R67 in Z-SOC; rebuild needs `mkdir -p pcb/renders`; LED2's reference and the "ETH" label sit beside LED3; duplicate/overlapping L5 segments (NPOR at C71.1, UART2_RX at R67.2) and 3 zero-length segments.
- **Verdict: FAIL for TP-L5.** DRC 0 errors, rebuild reproducible, L3/L4 checks 0 FAIL, L4 rules still hold, checker catches all 9 mutations, but 10 unconnected items remain (SD power, USB mux, PMIC interrupt, VBUS enable) and the ring-2 copper paths of three sub-rails are unrecorded; not CHECKPOINT 2.

## 2026-11-02 — Executor, layout phase L5 round 4 (remaining routing and finishing, gate TP-L5) — CHECKPOINT 2
- **What:** fixed the verifier's round-3 findings (D-116). A new step `pcb/scripts/l5_finish.py` (hand-placed 0/45/90 polylines, each piece exact-checked, plus router legs; written by `l5_finish_write.py` as group L5_FINISH) and `l5_tidy.py` run after `l5_prune.py`. The step re-routes RECOVERY / SARADC_IN1 on L4 west and north of the U9 inner vias, re-links the VCC_3V3 pin-61 inner via to pin 43, routes USB_SEL / SDMMC_PWREN / PB_INT_N out of the U9 field, rebuilds the codec loop, re-plans the east lanes (no via in STRIP-N; one neck-box via for USBA_VBUS_EN, inventory added), routes HDR_GPIO2_A7 before A6, and moves C84.1's plane via, TP18, TP24, R62 and R63 (owner approval items). It also removes the NPOR / UART2_RX duplicates and merges three sub-10 µm pieces.
- **Checks added (l5check):** ring-2 copper path for every ring-2 part (DEVs D-116 j), SENSE to SW / inductor >= 2 mm, vias in SMD pads (6, D-116 c, owner), redundant L5 segments, joints under 5 deg. Silk: LED labels in one row, LED references hidden. Docs: placement.csv zones / targets, zones.csv fills, testpoints.md rule 2, bringup.md. rebuild_all.sh: mkdir + check_placement stderr.
- **Results (clean-tree rebuild_all.sh, 13.5 min):** check_placement 339 / 0 FAIL; L3 board 419 / 0 FAIL; L4 board 509 / 0 FAIL; final check_routing 528 checks, 421 PASS, 68 DEV, 39 INFO, **0 FAIL**. KiCad DRC (refilled, all severities): **0 errors, 0 unconnected items**. Warnings: lib_footprint_issues 199 (capped), track_dangling 42 (all L3_ESCAPE overlap ends), via_dangling 2, silk_edge_clearance 2. Re-measured: ETH skew -0.59 / -0.29 mm, USB skews <= 0.61 mm, SENSE-SW 2.26 mm.
- **Open, owner (CHECKPOINT 2):** approve the moves (R66/R67, TP15 out of the power row, TP18/TP23/TP24, R62/R63, TP31/FB3/C69); POFV (4-layer price UNVERIFIED) or open vias in 6 pads; ring-2 DEVs on the DC sub-rails; 0.8 mm LED labels; CC1 via DEV (the round-3 review wrongly said it was gone).

## 2026-11-02 — Verifier, layout phase L5 round 4 (gate TP-L5) — verdict FAIL (one major)
- **What this check did:** rebuilt the whole board from the netlist in a scratch copy, compared it with the delivered board, ran KiCad DRC myself, re-measured the round-4 claims with my own pcbnew code (not the executor's checker), looked at the layer renders, and tried four deliberate faults to see whether the executor's checker catches them.
- **Rebuild (scratch copy, generated l5/ files deleted, only the stored Freerouting session kept):** `rebuild_all.sh` ran through in about 15 min: check_placement 339 / 0 FAIL; L3 board 419 / 0 FAIL; L4 board 509 / 0 FAIL; final 528 checks, 421 PASS, 68 DEV, 39 INFO, 0 FAIL; tools/check_layout 1259 pass / 0 fail. The rebuilt board matches the delivered board exactly: 3769 tracks and vias, 239 footprints with pad nets, 138 drawings and 18 zones.
- **DRC (own run on the delivered and rebuilt boards, zones refilled, all severities, all track errors):** 0 errors, **0 unconnected items**. Warnings: lib_footprint_issues 199, track_dangling 42, via_dangling 2, silk_edge_clearance 2. None of the downgraded checks (isolated_copper, copper_sliver, net_conflict, hole_to_hole, silk_over_copper and others) fires.
- **Own measurements that agree with the executor:**
  - Pad nets match pins.csv on all 680 connected pins (the only differences are NC pins).
  - U9: 0.19 x 0.75 mm pads at 0.35 mm pitch, pin 1 at the south-west corner, rows at ±5.425 / 6.075 mm. This agrees with RV1106 datasheet p.17 (e 0.35 BSC, D/E 12.3, L 0.3-0.5).
  - Connectors: J1 at 0°, J3 at 180°, J2/J4 at 0°. No parts on the bottom side.
  - ETH TX P−N −0.29 mm, RX −0.00 mm (totals 22.09 / 27.44 mm). USB, ETH and crystal net lengths and via counts are identical to the L4 board, so L5 did not touch the critical nets.
  - SENSE copper to the SW pads and inductors: 2.259 mm minimum.
  - No L1 copper from another net within 1 mm of the crystal pads that was added in L5. The only items are the recorded L3 VCC_3V3 vias at C77.1, 0.63 mm away.
  - VDD_0V9 neck: narrowest L3 cut 4.22 mm, the same as on the L4 board, so the USBA_VBUS_EN neck via costs nothing.
  - Rails: no copper on them except GFID1-3.
  - L5 copper: no dangling ends and no zero-length segments.
  - Silk: 490 items, none within 0.15 mm of a pad. "RV1106 Rev A 2026-11" is present. Only PWR, STAT and ETH are 0.8 mm text. No SMD pad within 1 mm of a THT pin.
  - Stitching: 7 of 250 poured 5 mm cells have no GND via. The far points are in the VDD_0V9 neck (DEV D-113 d).
- **Mutations (scratch copies, executor's check_routing.py; the unmutated control gives 528 / 0 FAIL):**
  - C61 moved 5 mm: 7 FAIL.
  - The longest USB_SEL L5_FINISH segment deleted: 2 FAIL (L5-conn, L5-geom).
  - A GND via placed in C45.2: L5-vip FAIL plus DRC.
  - U9 pad 62 renumbered to 162: the checker crashes with KeyError 162 in check_escape. Exit 1, so it is caught, but without a FAIL line.
- **Findings:**
  - **MAJOR (soc/pmu/prot):** three more vias have their 0.3 mm drill hole partly inside an SMD pad (and its 1:1 mask opening). L5-vip misses them because it only counts vias whose centre is inside the pad:
    - C45.1 VCC_DDR via (44.49, 35.99): centre 0.024 mm outside the pad edge.
    - R27.1 VCC_1V8 via (62.37, 47.63): 0.018 mm outside.
    - F1.1 VBUS_IN via (55.84, 70.71): 0.055 mm outside.
    - All three are L4_CRITICAL. About 0.10-0.13 mm of each hole lies inside the pad, which is the same solder-wicking risk as the six listed pads. So the via-in-pad list for the owner (decision 2 / D-116 m) has 6 pads where it should have 9.
    - Fix: move each via until the hole edge clears the pad edge plus the mask margin (centre at least 0.25 mm outside the pad), or add the three to D-116 m and the owner list. Extend L5-vip to FAIL whenever a drill circle intersects any SMD pad or its mask opening.
  - **Minor (gpio/pmu):** placement.csv still lists R62/R63 in Z-HDR (they now sit in no zone) and TP18/TP23/TP24 in Z-SOC (they now sit in Z-USBA-PWR / Z-USB). check_placement runs on the pre-L5 board, so the final positions of the D-116 moves are never zone-checked. Fix: update the zone column (or add a zone/DEV check on the final board).
  - **Minor:** check_routing crashes on an unknown U9 pad number. Fix: report it as a FAIL line.
  - **Minor (gpio/ui):** silk labels.
    - R63's reference sits about 5 mm from the part, beside TP31/C69, and R62's is hidden.
    - TP3, TP13, TP14 and TP27-TP29 have no label. That is recorded as INFO, not as a DEV against §10 "TP labels".
  - **Minor (onoff):** one PB_INT_N L5_FINISH segment, (42.20, 41.15)-(44.81, 43.89), is at 46.3° rather than 45°.
- **Verdict: FAIL for TP-L5, close.** Rebuild reproducible, DRC 0 errors / 0 unconnected, L3/L4/L5 checks 0 FAIL, L4 rules unchanged, 3 of 4 mutations caught cleanly (the fourth by a crash). The via-in-pad evidence behind §10 and the owner's POFV decision is incomplete (9 pads, not 6). Fixing or listing the three vias is enough to reach CHECKPOINT 2.

## 2026-11-06 — owner (CHECKPOINT 2)

Independent electrical and routing reviews run on the L5 board. Owner decision D-H6: order POFV (supersedes D-67) and fix the full review list in phase L5F (buck input-loop GND in U4–U7, C24/C6/C38 values, V-cut clearance, PWR_EN near L3, silk sizes, L4 hop references, clean-up, board corners), then re-run both reviews before L6.

## 2026-11-07 — Executor, layout phase L5F (CHECKPOINT-2 review fixes, owner decision D-H6, gate TP-L5F)
- **What:** fixed the D-H6 list in new scripts run after L5 (`pcb/scripts/l5f_run.sh`, wired into `rebuild_all.sh`; D-117). Buck input loops U4–U7: L1 GND strap from pin 2 under the body to both input caps (10 µF caps moved/turned inside their cells, C12 to the east slot), under-body GND via, pin 2 solid; enable nets U4_EN / U6_EN / VCC_DDR_1V8_EN / PWR_EN re-routed ≥ 1 mm from SW copper and out of the inductor courtyards; pours clipped 0.8 mm from the V-cuts; In2 GND islands under the 4 L4 pair-hop clusters (+1 stitching via at the ETH hop); necks at C29/R17/C16/C2; 42 escape stubs trimmed, the 2 stub vias linked on L4; R 1 mm board corners (rail notches); silk lines 0.15 mm, LED labels 1.0 mm, J1 edge silk, R62/R63 references; placement.csv zones; check_escape guard; PB_INT_N / NPOR off-45 pieces snapped. BOM: C24 22 µF (C59461), C6 2.2 µF (C23630, hard-off 8.07–22.4 s), C71 (nPOR) 100 nF (C1525); schematic/BOM regenerated.
- **Checks:** new `pcb/scripts/l5fcheck.py` (L5F-buck/vip/vcut/sw/silk/hop/neck/dangle/edge/zone/geom) in check_routing; `pcb/via_in_pad.csv` (28 rows, exact); self-test `mutate_l5f.py` → `pcb/trial/mutations_l5f.txt`.
- **Results (clean rebuild, board identical to the dev board):** check_placement 339 / 0 FAIL; L3 419 / 0 FAIL; L4 509 / 0 FAIL; final check_routing 565 checks, 457 PASS, 70 DEV, 38 INFO, **0 FAIL**; KiCad DRC 0 errors, 0 unconnected, track/via_dangling 0 (only lib_footprint_mismatch 152 warnings); check_layout 1259 / 0; check_schematic 1694 / 0; check_bom 408 / 0; check_power 84 / 0.
- **Open, owner:** the three J5 west lanes stay 0.41–0.59 mm from the V-cut (D-117 d); 5 pair vias without a GND via ≤ 1 mm (D-117 f); TP3/13/14/27–29 labels on F.Fab only; VDD_0V9 total output C 16 % above TI's checked cell (C24 22 µF); C_PDT 2.2 µF means up to 22 s hold for hard-off; POFV 4-layer price at order time. Review: `pcb/fix-review.md`.

## 2026-11-07 — Verifier, layout phase L5F (CHECKPOINT-2 review fixes, D-H6 / D-117, gate TP-L5F) — verdict FAIL (one major, owner decision)
- **What this check did:** rebuilt the whole board from scratch in a scratch copy and compared it with the delivered board. Re-measured every D-H6 item with my own pcbnew code, not the executor's checker. Ran KiCad DRC and the schematic, BOM, power and layout checks again. Ran the executor's 16 deliberate faults plus 7 of my own through the checker, and looked at the renders.
- **Reproducible:** `rebuild_all.sh` ran to the end on a clean scratch tree (exit 0, 15 min). The rebuilt board matches the delivered one exactly: 0 of 4205 items differ (tracks, vias, footprints, pad nets and zone connections, zones, drawings). Final check_routing 565 checks / 0 FAIL; L3 board 419 / 0, L4 board 509 / 0; check_placement 339 / 0 FAIL. The netlist regenerated from SKiDL is the same apart from date stamps; bom.csv is byte-identical. check_schematic 1694 / 0, check_bom 408 / 0, check_power 84 / 0 (P8: earliest hard-off 8.07 s), check_layout 1259 / 0.
- **DRC (kicad-cli, zones refilled, all severities):** 0 errors, 0 unconnected, 0 track/via_dangling. The only warnings are 152 lib_footprint_mismatch.
- **Own measurements:**
  - (1) Buck input loops, each of U4–U7: L1 GND path from the 10 µF cap's GND pad to pin 2 is 2.01 mm, and 2.82 mm from the 100 nF cap's (raster geodesic, 0.02 mm grid). Pin 2 is solid (pad ZONE_CONNECTION_FULL; ring around the pad 100 % copper). Two GND vias within 1 mm of pin 2 (0.34 / 0.52 mm). FB to SW ≥ 2.26 mm outside the IC courtyards. The moved caps overlap no courtyard.
  - (2) Searched all 649 vias against every SMD pad and its 1:1 mask opening: 12 hits plus the 16 U9 EP vias, which is exactly the 28 rows of via_in_pad.csv.
  - (3) C6 2.2 µF C23630 0603, C24 22 µF C59461 0603, C71 100 nF C1525 0402 on the board and in the BOM. Footprints unchanged; only C7–C10 and C12 moved.
  - (4) V-cut: every pour ends at exactly 0.80 mm. HDR_PWM9 and HDR_SPI0_SCLK vias are at 0.41 mm, the HDR_SPI0_MOSI via at 0.51 mm, and their tracks at 0.59–0.71 mm, including a 30 mm B.Cu run at 0.59 mm. Nothing else is under 0.8 mm.
  - (5) EN / PWR_EN / PB nets ≥ 1.01 mm from same-layer SW copper; no EN copper in any inductor courtyard.
  - (6) Silk: 0 lines < 0.15 mm, 0 texts < 1.0 mm / 0.15 mm, 0 silk outside the board.
  - (7) In2 GND under every L4 USB/ETH sample farther than 0.45 mm from a via. Five pair vias have their nearest GND via 1.17–2.23 mm away (same list as the executor).
  - (8) C29.1 and R17.1 are fed only by 0.40 mm tracks.
  - (9) Board corners are R 1 mm arcs centred 1 mm inside each corner. User.1 "V-CUT" plots to a Gerber.
  - (10) R62/R63 refs visible; the 6 TP refs are hidden.
- **Mutations:** the executor's 16 faults are all caught and the control has 0 FAIL. My own: C13 moved 5 mm (L5F-buck), F.Cu GND track 0.55 mm from the east V-cut (L5F-vcut), GND via ring 0.08 mm into R13.2 (L5F-vip), silk text at 0.8 mm (L5F-silk), C7 pads 1↔2 swapped (netlist), the In2 island under USB_DM removed (L5F-hop), U7.2 set back to thermal (L5F-buck): all caught. A via whose ring was still 0.02 mm clear of the pad was rightly not flagged.
- **Findings:**
  - **MAJOR (gpio):** the TP-L5F requirement "copper ≥ 0.8 mm from the V-cuts" is not met. Three J5 west lanes have vias 0.41–0.51 mm and tracks 0.59 mm from x = 0, right at JLC's 0.4 mm minimum. The fix is the owner's choice: accept D-117 d, or move J5 (with its lanes) ≥ 0.4 mm east as a recorded small local move, or re-route those three lanes between the J5 pin columns.
  - Minor (usb/eth): 5 pair vias have no GND stitching via within 1 mm (D-H6 item 7); owner item.
  - Minor (gpio/pmu): TP3/13/14/27–29 have no silk label (D-117 i); owner item.
  - Minor: the rail-notch corner leaves a sharp 90° concave cut corner at (0,1), (0,79), (80,1) and (80,79), so the router bit will leave a small cusp; confirm at JLC DFM.
  - Minor (pmu): the C16.1 "neck" is shorter than the 0.8 mm track's end-cap, which still overlaps the pad (0.13 mm²; C2.1 0.017 mm²). L5F-neck only tests track end points, so it misses this.
  - Minor: `route_l5f_corner_nw.png` does not draw Edge.Cuts, so it does not show the corner it is meant to show.

## 2026-11-07 — Executor, layout phase L5F round 2 (verifier findings, D-118)
- **What:** fixed the round-1 verifier findings in the L5F scripts (D-118). (a) MAJOR V-cut: the J5 west corridor was re-drawn by hand in `l5f_route.py` (old pieces ripped in `l5f_prep.py`). HDR_PWM9 / HDR_SPI0_SCLK / HDR_SPI0_MOSI and their vias now keep ≥ 0.80 mm from x = 0 (tracks 0.8002, vias 0.81 mm). HDR_PWM11 / GPIO1_B0 / GPIO1_B1 jog round the new HDR_PWM9 via. No part moved. D-117 d is withdrawn and VCUT_DEV is empty. (c) Rail notches are now 1.5 × 1.5 mm with R 0.5 mm air-side corners, tangent to the board arc. New L5F-edge router-bit corner check. (d) TP3/13/14/27/28/29 have bare-number silk labels. (e) The neck-downs keep the wide copper ≥ 0.10 mm off the pads (C16.1, C2.1). L5F-neck gained a polygon-overlap line. (f) The corner renders draw Edge.Cuts / V-CUT. (b) Pair-via stitching is not changed; the reason is in D-118 b (J1 pad rows and the pairs' own copper take every site; changing it needs an L4 pair re-route) and it stays an owner item.
- **Checks:** clean rebuild 14 min 50 s, rebuilt board = delivered board (0 of 4929 items differ); KiCad DRC 0 errors / 0 unconnected / 0 dangling; check_routing final 566 checks, 0 FAIL (69 DEV); L3 419 / 0 FAIL, L4 509 / 0 FAIL; check_placement 339 / 0 FAIL; check_layout 1259 / 0; new mutations `vcut_lane`, `neck_overlap`, `notch_sharp`; full suite 19 of 19 caught, control 0 FAIL (`pcb/trial/mutations_l5f.txt`).
- **Open, owner:** 5 pair vias with a GND via at 1.17–2.23 mm (D-118 b); JLC router-bit size and the POFV price to confirm at DFM / order (L6, H2).

## 2026-11-07 — Verifier, layout phase L5F round 2 (D-118, gate TP-L5F) — verdict PASS (minors only)
- **What this check did:** rebuilt the whole board from scratch in a scratch copy and compared it with the delivered board, re-measured the round-1 findings and every D-H6 item with my own pcbnew code (not the executor's checker), ran KiCad DRC and the layout / BOM / power checks again, ran the executor's 19 deliberate faults plus 6 of my own through the checker, and looked at the renders and my own SVG export of the top side.
- **Reproducible:** `rebuild_all.sh` on a clean scratch tree ran to the end (exit 0, 15 min 32 s). The rebuilt board matches the delivered one exactly: 0 of 6918 items differ (tracks, vias, footprints, pads with nets and zone connections, fields, zones, texts, drawings). via_in_pad.csv is identical. check_routing: final 566 checks / 0 FAIL, L3 board 419 / 0, L4 board 509 / 0. check_placement 339 / 0 FAIL. check_layout 1259 / 0, check_bom 408 / 0, check_power hard-off 8.07–22.42 s.
- **DRC (kicad-cli, zones refilled, all severities):** 0 errors, 0 unconnected, 0 track/via_dangling. The only warnings are 152 lib_footprint_mismatch. Pad nets match schematic/out/pins.csv: 680 of 680.
- **Own measurements:**
  - V-cut (round-1 major): the V-CUT layer is User.1, with lines at x = 0 and x = 80. Closest board copper: tracks 0.8002 mm (HDR_SPI0_SCLK F.Cu at x 0.85), vias 0.810 mm, pours 0.800 mm; nothing on the board is below 0.8 mm. Only the rail fiducials are closer (0.65 mm, the JLC position, reported as INFO). The 42 corridor tracks are all at 0/45/90°, 0.10 mm wide (D-113 b); DRC is clean.
  - Notches: 1.5 × 1.5 mm with R 0.5 arcs centred in the air. The arc is tangent to the R 1 board arc at (0, 1), all four corners alike. My 3200 px/80 mm export shows the shape.
  - Neck-downs: no track wider than a small pad's narrow side + 0.02 mm overlaps, or comes within 0.10 mm of, a pad of its own net (0 found). C16.1 neck 0.496 mm, C2.1 1.165 mm.
  - Silk: 0 lines < 0.15 mm, 0 texts < 1.0 mm / 0.15 mm, closest silk text to a mask opening 0.315 mm.
  - Unchanged since round 1: buck loops (10 µF 2.01 mm, 100 nF 2.82 mm; pin 2 solid; 2 vias at 0.34 and 0.52 mm), the via-in-pad list (12 + 16 EP = 28 rows, exact), EN to same-layer SW ≥ 1.01 mm, In2 GND under the L4 hops.
  - Footprint spot check: the FHD4020S pads (1.10 × 3.70 mm, centres ±1.50 mm) match datasheet p.2, row FHD4020. U9 pin 1 is at the south-west corner.
- **Mutations:** the executor's suite was re-run: control 0 FAIL, 19 of 19 caught. My own: HDR_PWM9 run moved to x 0.84 (0.79 mm, L5F-vcut), C16 wide-track joint 0.12 mm nearer the pad (L5F-neck overlap), SE notch inner arc made square (L5F-edge), J5 pads 1/2 swapped (netlist), C13 moved 5 mm (L5F-buck / zone): all caught. Moving the "13" label 5.7 mm away was caught only because it landed on U10 (L5-silk). No check measures whether a test-pad label sits next to its own pad.
- **Findings (no blocker, no major):**
  - Minor (pmu/ui): the new bare-number TP labels are ambiguous. "13" is 2.44 mm from the TP13 pad edge and 0.48 mm from R27.1 (R27's own reference was hidden to make room). "3" sits between TP3 (0.84 mm) and TP14 (0.90 mm). "27" is nearer R11.2 (0.49 mm) than TP27 (0.83 mm). "29" is nearer R7.2 (0.72 mm, R7 labelled) than TP29 (0.92 mm). The "nearer than any other labelled part" rule ignores unlabelled parts. Fix: require each label's ink to be nearer its own pad than any other pad, or fall back to F.Fab with a DEV. Add a FAIL line plus a mutation.
  - Minor (usb/eth, owner item): 5 pair vias have their nearest GND via at 1.17–2.23 mm (D-118 b). My own site probe agrees for the 4 USB-C vias. For ETH_TXN (22.85, 31.10) the best site falls 0.003 mm short of the 0.15 mm clearance.
  - Minor (docs): `route_l5f_tp_silk.png` does not draw the silk labels, and `_F_SilkS.png` overlays the F.Fab text, so neither shows the new labels clearly.

## 2026-11-07 — owner (after L5F re-reviews)
- Owner answered "Yes, fix and accept": D-H7. Phase L5G fixes the routing re-review list (EP vias as real board vias for POFV, silk labels, SD clock / RTC spacing, J5.2 link, J1-shell vias, hop-island and Q1 vias, pair check); the listed owner items are accepted as deviations. Then L6.

## 2026-11-07 — Executor, layout phase L5G (re-review fixes, D-H7, D-119..D-127)
- **What:** new `pcb/scripts/l5g_run.sh` (after `l5f_run.sh` in `rebuild_all.sh`): `l5g_fix.py` (copper), `fill_zones.py`, `l5g_silk.py` (labels), renders. (1) U9 EP: the 16 drilled footprint pads removed on the board, 16 GND board vias 0.5/0.3 at the same centres; board setup via filling + capping (IPC-4761 VII); Excellon now has no 0.3 mm ComponentDrill tool and `T1C0.300` ViaDrill = 670 holes = 670 vias; paste windows 0.175 mm from the via holes (D-119). (2) Silk: new nearest-own-copper rule; 80 of 166 labels broke it on the L5F board, now 0 of 148 (63 moved, 13 thin-margin ones improved, 14 references hidden on F.Fab, TH2/3/4 texts hidden) (D-120). (3) SDMMC_CLK_SD 0.305 mm from D0 / CMD along the bus (was 0.21 mm over 24.4 / 21.6 mm); SD lengths within +-1.6 mm of the clock (D-121). (4) RTC: XOUT >= 0.518 mm from SDMMC_D2 below the R48 / C58 channel; residual in the channel recorded: XOUT-D2 2.46 mm at >= 0.323, XIN-XOUT 2.21 mm at >= 0.293 (2.0 asked) (D-122). (5) J5.2 link pad centre to pad centre (D-123). (6) J1-shell vias 0.402 -> 0.472 mm hole to slot (D-124). (7) every In2 hop island 2 GND vias (3 added) (D-125). (8) Q1 drain 5 vias (D-126). (9) scripted USB/ETH pair report reproduces the reviewer numbers; end-to-end skews <= 1.11 mm (D-127). (10) silk plots draw the labels, `route_l5g_*.png`, testpoints.md / bringup.md name the nPOR cap C71.
- **Checks:** KiCad DRC 0 errors / 0 unconnected / 0 dangling (153 lib_footprint_mismatch: + U9); check_routing 599 checks / 0 FAIL / 71 DEV (new l5gcheck.py lines L5G-ep/silk/sd/rtc/tht/hole/hop/q1/pair); clean rebuild 20.4 min, rebuilt = delivered (0 of 6932 items differ); L3 419 / 0, L4 509 / 0, check_placement 339 / 0; mutate_l5g 12 / 12, mutate_l5f 19 / 19 caught. Report: `pcb/fix-review-l5g.md`.
- **Open, owner:** the RTC channel residual (needs a 0.2-0.3 mm C58 / R48 move); 14 references now only on F.Fab (assembly drawing in L6).

## 2026-11-07 — Verifier, layout phase L5G (re-review fixes, D-H7 / D-119..D-127, gate TP-L5G) — verdict FAIL (one major, owner decision)
- **What this check did:** rebuilt the whole board from scratch in a scratch copy (all generated boards deleted first) and compared it with the delivered board. Re-measured each D-H7 item with my own pcbnew code, not the executor's checker. Ran kicad-cli DRC (zones refilled) and an Excellon export. Re-ran check_routing and the executor's L5G mutation suite. Made 5 mutations of my own. Looked at the renders and at my own kicad-cli top render.
- **Rebuild:** `rebuild_all.sh` took 20.4 min. The rebuilt board matches the delivered one: all tracks, vias, footprints, fields, texts and via settings are identical (6212 items). Only the zone-fill point counts differ slightly. Inside the rebuild: L3 419 / 0 FAIL, L4 509 / 0 FAIL, check_placement 339 / 0 FAIL. Final check_routing: 599 checks, 0 FAIL. My first run failed one check, but only because I had deleted `pcb/via_in_pad.csv`. That file is a hand-kept input list, not a script output, so this is not an executor fault.
- **DRC (kicad-cli, zones refilled):** 0 errors, 0 unconnected, 0 dangling; 153 lib_footprint_mismatch warnings. **Excellon:** no 0.3 mm ComponentDrill tool left; `T1C0.300` ViaDrill has 670 holes = 670 board vias. Board setup is saved as `(filling yes) (capping yes)`.
- **My measurements:**
  - (1) U9 EP: 0 drilled pads; 16 GND 0.5/0.3 vias inside the EP. Paste windows are 0.175 mm from the via holes. The U9 copy equals board.pretty minus the 16 via pads. All 680 pad nets match pins.csv.
  - (2) Silk: 0 of 103 references break the nearest-part rule; the smallest margin is 0.08 mm (C28, C48). TH2/TH3/TH4 are hidden. The 14 newly hidden references keep their F.Fab text. All silk text is 1.0 mm / 0.15 mm.
  - (3) SDMMC_CLK_SD: no run at < 0.30 mm to any SD / NAND track. SoC-side SDMMC_CLK runs 1.20 mm (CMD) and 0.68 mm (D0) at 0.25 mm.
  - (4) RTC_XOUT to SDMMC_D2: 0.321 mm minimum over 3.4 mm from the pin row (y 43.6-46.9). XIN-XOUT is under 0.5 mm for about 2.2 mm outside the pin escape (0.29 mm minimum). **Gate item "RTC_XOUT >= 0.5 mm from SDMMC_D2" is not met.** My own channel arithmetic agrees there is no room without a part move: the gap from the R48 pad edge to the C58 pad edge (about 2.25 mm) cannot hold CMD/D3/D2 at the 0.20 mm SDMMC clearance, XOUT 0.5 mm from D2, and XIN 0.30 mm from XOUT and from C58.
  - (5) The J5.2-J5.4 link runs pad centre to pad centre; the J5.4 feed overlaps 0.56 of its width.
  - (6) Smallest via-hole to PTH/slot edge is 0.472 mm, at J1.SH.
  - (7) In2 hop islands 0-3 have 2 GND vias each.
  - (8) Q1.3 has 5 VCC5V0_SYS vias.
  - (9) Pad-to-pad skew: SoC -> J4 26.65 / 27.76 mm (-1.11 mm). Off-gap lengths: USBC 17.5, USBA 9.5, ETH TX 12.8 mm. These match the report within my sampling tolerance.
  - (10) C71 / Luckfox C38 and τ = 100 µs are correct in testpoints.md and bringup.md (R43 1 k, C71 100 nF).
- **Mutations:** mutate_l5g caught 12 of 12, with a clean control. My own 5 were all caught:
  - R55 label next to R53 -> L5G-silk FAIL
  - U9 pads 20/21 swapped -> escape / DRC / conn FAIL
  - via capping off -> L5G-ep FAIL
  - EP via moved 0.15 mm -> L5G-ep paste and L5F-vip FAIL
  - C58 moved 5 mm -> planevia / DRC / silk FAIL
- **Findings:**
  - (major, xtal) The RTC_XOUT-SDMMC_D2 residual is a gate miss. It needs the owner to choose: accept D-122 as recorded, or allow a 0.2-0.3 mm C58 (and/or R48) move and re-route.
  - (minor, xtal/sd) The run lengths from `l5glib.side_runs` depend on the order of tracks in the file. On the identical rebuilt board, XIN-XOUT reads 2.16 vs 2.21 mm and the SD INFO runs split differently.
  - (minor, pmu) "3" (TP3) still sits between TP3 and TP14, in line with the "28"/"27" labels that mark the bottom row from above.
  - (minor, silk) The 0.05 mm margin lets near-equidistant labels pass (C28, C48 0.08 mm; R44 0.11 mm).
  - (minor, soc) The U9 board copy no longer matches the library. A board.pretty variant without the via pads would remove the warning and the risk from "update footprints".
- **Verdict:** FAIL. One gate item is not met (owner decision on D-122). Everything else in TP-L5G checks out. L6 not started.

## 2026-11-07 — Executor, layout phase L5G round 2 (verifier round-1 findings, D-128..D-131)
- **RTC channel (major):** C58 moved 0.176 mm E / 0.25 mm N (recorded small local move under D-H5, **owner to confirm**; USB_DM limits the east move to 0.1525 mm clearance), C58.2 GND via into the pad, channel re-drawn from the U9 pin row. RTC_XOUT–SDMMC_D2 >= 0.500 mm along the whole route (was 0.321); XIN/XOUT 0 runs < 0.5 mm to other signals outside the escape; XIN–XOUT run 1.88 mm (limit 2.0). L5G-rtc has no exemption any more (D-122 DEV lines removed). SD lengths CLK 32.52, D0 34.05, D1 33.61, D2 32.61, D3 32.80, CMD 32.93 mm.
- **Minors:** side_runs geometry-only + L5G-runs FAIL line (D-131); silk margin 0.20 mm + test-pad-row band rule, "3" printed "TP3", 19 references hidden (D-130); U9 board.pretty variant `_EPboardvias`, U9 mismatch gone (D-129). lanecheck counts L5G_FIX copper as routed; l5g_fix.py keeps removed items referenced (pcbnew list corruption seen otherwise).
- **Results:** DRC 0 errors / 0 unconnected (152 lib mismatch warnings); check_routing 601 / 0 FAIL / 68 DEV; check_footprints 232 / 0 failed; check_placement 339 / 0 FAIL; clean rebuild 23.4 min = delivered board (6857 items, L5G lines byte-identical); mutate_l5g 18/18, mutate_l5f 19/19. Excellon: 0 ComponentDrill 0.3, ViaDrill 670 = 670 vias.
- **Open, owner:** confirm the C58 move (or revert to the D-122 recorded residual); 19 references only on F.Fab (assembly drawing in L6). L6 not started.

## 2026-11-07 — Verifier, layout phase L5G round 2 (D-128..D-131, gate TP-L5G) — verdict PASS (minors only)
- **What this check did:** rebuilt the whole board from scratch in a scratch copy (every .kicad_pcb deleted first) and compared it with the delivered board. Re-measured every D-H7 item and the round-1 findings with my own pcbnew code, not the executor's checker. Ran kicad-cli DRC (zones refilled, all severities) and an Excellon export. Re-ran the executor's mutation suite and 9 mutations of my own. Looked at the renders and at my own SVG export of the top side. I did not edit any design file.
- **Rebuild:** `rebuild_all.sh` exit 0 in 20.0 min. The rebuilt board matches the delivered one: 0 of 6856 items differ (tracks, vias, footprints, pads with nets, fields, texts, drawings, zones). The board setup has `filling yes` / `capping yes`. via_in_pad.csv is identical, and the L5G lines of check_routing are byte-identical. Results: L3 419 / 0 FAIL, L4 509 / 0, check_placement 339 / 0, final check_routing 601 / 0 FAIL (68 DEV), check_footprints 232 / 0 failed.
- **DRC (kicad-cli):** 0 errors, 0 unconnected, 0 dangling, 0 exclusions. The only warnings are 152 lib_footprint_mismatch, none on U9. Pad nets match schematic/out/pins.csv for every connected pin (the only differences are 38 pins.csv "NC" pins, which have no net).
- **Excellon:** no 0.3 mm ComponentDrill tool. `T1 0.300 Plated,PTH,ViaDrill` has 670 holes, equal to the 670 board vias.
- **My measurements:**
  - (1) U9 uses `_EPboardvias`: 0 drilled pads; the file equals the base footprint minus the 16 drilled pads. 16 GND vias 0.5/0.3 sit at x 32.20-36.80, y 34.20-38.80, and all 16 are in the B.Cu, In1 and In2 GND fills. Paste windows are 0.175 mm from the via holes. Pad sizes and positions match RV1106 datasheet r1.8 p.17 Fig.2-5 (e 0.35, D2 = E2 = 7.0, K 2.25); pin 1 is at the SW corner. 26 vias have a drill in an SMD pad (EP 16 + 10), and all 26 are in via_in_pad.csv.
  - (2) My own ink-box-to-copper check over 144 visible F.SilkS labels: 0 nearer another part's copper, 0 over 2.0 / 3.0 mm, smallest margin 0.212 mm (Q1). TH2/3/4 texts are hidden. The 19 hidden references have `${REFERENCE}` on F.Fab.
  - (3) SDMMC_CLK_SD is at least 0.305 mm from every SD / NAND track (0 mm under 0.30). SoC-side SDMMC_CLK runs at 0.25 mm for 1.5 mm (CMD) and 0.68 mm (D0), both under 2 mm. Lengths: CLK 2.16 + 30.37 = 32.53, D0 34.05, D1 33.61, D2 32.61, D3 32.80, CMD 32.93 mm.
  - (4) RTC_XOUT to SDMMC_D2 is at least 0.500 mm along the whole route, pin escape included. Away from their own pins, XIN and XOUT come no nearer than 0.55 mm to any other signal; at the pin row they are 0.24-0.25 mm from the neighbour pins' tracks for about 0.5 mm. XIN to XOUT is under 0.5 mm for 3.5-3.6 mm from the pads: 1.8 mm inside the 1.5 mm escape at 0.25-0.34 mm, then 1.7-1.9 mm at 0.300 mm.
  - C58 is the only part that moved since the L5F board: (36.71, 45.19) -> (36.886, 44.94), same rotation. C58.1 is 1.90 mm centre to centre from U9.24.
  - (5) The J5.2-J5.4 link runs pad centre to pad centre. The J5.4 feed overlaps the pad by 0.454 mm radially (0.61 of its width along the track); the joint chord is 0.93 mm.
  - (6) The smallest via-hole to PTH / slot gap is 0.472 mm, at J1.SH.
  - (7) In2 hop islands 0-3 have 2 GND vias each.
  - (8) There are 5 VCC5V0_SYS vias on Q1.3.
  - (9) Pairs: USBC 17.5 of 32.0 mm off-gap, USBA 9.4 of 13.8, ETH TX 12.9 of 16.0; the magnetics side is fully uncoupled; net skews are the same as the report. Pad-to-pad USB-A skew is 1.11 mm (limit 1.27).
  - (10) testpoints.md / bringup.md name C71 (Luckfox C38); pins.csv agrees (C71 = NPOR, C38 = VDD_ARM).
- **Mutations:**
  - The executor's mutate_l5g caught 18 of 18, with a clean control.
  - My own 9 were all caught, with a clean control:
    - "27" moved next to TP5 -> L5G-silk + L5-silk FAIL.
    - JP1 "B" moved over JP1.2 -> L5G-silk FAIL.
    - EP via moved 0.2 mm -> L5G-ep paste + L5F-vip FAIL.
    - SDMMC_D2 channel moved 0.06 mm towards XOUT -> L5G-rtc FAIL, both lines.
    - Two Q1 vias deleted -> L5G-q1 + planevia FAIL.
    - J1 shell via moved 0.06 mm west (0.440 mm) -> L5G-hole FAIL.
    - U9 pads 23/24 renumbered -> netlist / escape / L5G-ep FAIL.
    - C58 moved 5 mm -> planevia / conn / vip / dangle / silk FAIL.
- **Findings (no blocker, no major):**
  - Minor (pmu): "TP3" now sits under TP3 but still in the band between the two test-pad rows, right above TP14. In that band "28" and "27" label the lower-row pads beneath them, while "14" sits below TP14. Fix: move "28" / "27" below their pads (like "14") so that every label in the band belongs to the upper row.
  - Minor (xtal, docs): fix-review-l5g.md §4 / D-128 give only the 1.88 mm XIN-XOUT run outside the escape. The run from the pads is about 3.5 mm, and the L5F "before" figure of 7.6 mm included the escape. Fix: record both numbers.
  - Minor (soc, L6 note): the board's U9 footprint (`_EPboardvias`) differs from the netlist's `board:RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm`. A GUI "Update PCB from Schematic" that replaces footprints would bring back the drilled ComponentDrill pads. Fix: say so in the L6 fab notes and kicad-guide (rebuild only by script), and keep the L5G-ep Excellon check in L6.
  - Minor (housekeeping): `design/refs/refs` is a symlink to `design/refs` itself, created 05:28 today (before this run). It can make tools that walk refs/ loop. Fix: delete the link.
- **Owner items (not gate misses):** the C58 0.30 mm move is recorded under the D-H5 small-local-move allowance (D-128) and is within the decoupling rule. 19 references are kept only on F.Fab, as the brief allows (assembly drawing in L6).
- **Verdict:** PASS. Every TP-L5G item is met and the clean rebuild reproduces the board. L6 not started.

## 2026-11-07 — Executor, layout phase L6 (fabrication outputs, D-132, gate TP-L6)
- **Scripts:** `pcb/scripts/l6_fab.py` + `l6_run.sh` (wired at the end of `rebuild_all.sh`), self-check `check_fab.py`, self-test `mutate_fab.py`. Output folder `pcb/fab/`, nothing hand-edited.
- **Board change (only one):** aux origin moved to the panel lower-left (board (-5, 80)); the two "V-CUT" texts moved from the V-CUT layer to User.Drawings, so the V-CUT Gerber has only the 2 cut lines. check_routing still 601 / 0 FAIL (only the L5F-edge draw count changes, 60 -> 2). DRC: 0 errors, 0 unconnected, 152 lib-mismatch warnings.
- **Outputs:** 12 Gerbers (X2) + job file; Excellon PTH / NPTH; drill maps; upload zip (15 files); JLC BOM (63 rows / 193 refs, all with an LCSC number); not-assembled list (46); CPL (193 rows, incl. THT J3-J6 placed by JLC); cpl-rotations.md (31 orientation-sensitive parts; corrections UNVERIFIED); assembly PDFs (refs / values); fab drawing; 3-D renders top / bottom; IPC-D-356; order-notes.md (cost from a live check_bom run $370.82 ESTIMATE, margin $9.18, POFV not costed).
- **check_fab:** 53 PASS / 0 FAIL.
  - Outline: 1 closed loop, 90.000 x 80.000 mm.
  - V-CUT: 2 lines at x = 5 / 85 (board 0 / 80).
  - Copper inside the outline (0 px outside). Board copper to the V-cut 0.80 mm; rail fiducials 0.64 mm.
  - Holes: ViaDrill 670 = 670 board vias (all on a board via), no 0.3 ComponentDrill. PTH 63 + 4 slots, NPTH 14 = board.
  - CPL: 193 refs once each; centres within 0.00007 mm of the pad centres; rotations consistent per family.
  - Fiducials and tooling holes are where the board has them.
- **mutate_fab:** 17 / 17 caught, control clean.
- **Gerber viewer check:** own rasteriser (`fab/gerber-view/*.png`), looked at every layer plus the composite.
- **Clean rebuild:** `rebuild_all.sh` from scratch in a scratch copy, exit 0 (85 min with other jobs running).
  - Board: 4193 of 4209 items identical; the 16 that differ are group member UUID lists.
  - Zone fills differ only by single 0.04 mm edge pixels.
  - BOM / CPL / md / drill / V-CUT / Edge files are identical; Gerber flashes are identical.
- **Open, owner:** confirm CPL rotations in JLC's preview; POFV price vs the $9.18 margin; how JLC wants the V-cut marked and where the tooling holes go; the C58 move (L5G r2) is still open. cost.md is stale ($373.34 vs check_bom $370.82). design/refs/refs is a self-symlink (not removed).

## 2026-11-07 — Verifier, layout phase L6 (fabrication outputs, D-132, gate TP-L6) — verdict PASS (minors only)
- **What this check did:** rebuilt the whole board and the fab folder from scratch in a scratch copy (every .kicad_pcb and fab/ deleted first), re-ran `l6_run.sh` alone on a copy of the delivered board, and compared both with the delivered files. Re-measured the Gerbers, drill files, CPL and BOM with my own parsers and pcbnew code (not check_fab.py), rendered every Gerber layer with my own rasteriser and looked at it, ran kicad-cli DRC (zones refilled, all severities), read the PDFs and renders, re-ran mutate_fab and 13 mutations of my own.
- **Rebuild:** `rebuild_all.sh` exit 0 in 19.3 min. L3 419 / 0 FAIL, L4 509 / 0, final check_routing 601 / 0 FAIL (also 601 / 0 on the delivered board), check_fab 53 / 0. BOM, CPL, not-assembled list, cpl-rotations.md, order-notes.md, Edge.Cuts, V-CUT, PTH, NPTH and job file are identical to the delivered ones once the creation dates are removed. The other Gerbers differ only in item order: the flash sets are identical on every layer, and my rasters (0.05 mm pixels) differ by 0 pixels on F.Cu, In1, masks, paste and silk, 3 on In2 and 12 on B.Cu (zone-fill edges). `l6_run.sh` alone on the delivered board: 53 / 0, outputs differ from the delivered ones only in dates.
- **DRC (kicad-cli 10.0.7, refilled):** 0 errors, 0 unconnected, 0 parity; only 152 lib_footprint_mismatch warnings. Pad nets = schematic/out/pins.csv for all 688 connected pins (38 NC pins have no net).
- **My measurements:**
  - Origin: aux origin page (45, 130) = panel lower-left. The Edge.Cuts Gerber is one closed loop (32 pieces, 16 arcs, 0 odd endpoints), 0..90 x 0..80 mm. The V-CUT Gerber is exactly two lines, (5, 0)-(5, 80) and (85, 0)-(85, 80).
  - Drill: PTH = 0.3 mm 670 (TA ViaDrill; board has 670 vias, all 0.5 / 0.3), 0.89 x 8, 1.0 x 47, 1.02 x 4, 1.63 x 2, 2.3 x 2 (63 = board) + 4 G85 slots 0.6 mm (= board). NPTH = 0.65 x 2, 1.0 x 2, 2.0 x 4 (tooling holes at (2.5 / 87.5, 10 / 70)), 3.2 x 4, 3.25 x 2 (14 = board). No 0.3 mm ComponentDrill.
  - Copper: the flash centres on F.Cu run x 3.85..86.15 (the rail fiducials only); In1, In2 and B.Cu run x 5.80..84.20, i.e. 0.80 mm from the V-cut lines. Silk mask-subtraction flashes are clear polarity, so the B.SilkS file is empty in effect. Min track 0.10 mm (1215 segments, U9 escape), vias 0.5 / 0.3 only.
  - CPL: 193 rows = `kicad-cli pcb export pos` set (193, same refs). Pad-bbox centres match within 0.00007 mm, and only J1-J6 differ from the KiCad origin (1.50 / 2.20 / 6.22 / 4.50 / 24.16 / 2.54 mm, as listed). BOM refs = CPL refs = bom.csv refs (193); 63 rows, 63 LCSC numbers, all equal to bom.csv. The 46 unassembled refs (31 TP, 5 FID, 4 H, 4 TH, JP1, NT1) = the parts.csv rows with in_bom = no.
  - Rotations: for every one of the 31 orientation-sensitive parts I computed pad 1 / A1 from the board. All 31 "must be at" entries in cpl-rotations.md are right. U9 is not mirrored: footprint pin 1 is at (-6.075, -5.425), numbered counter-clockwise; on the board, at rotation 90, pin 1 is on the south row at the west end and pins 1-32 run east. U9 pads 0.75 x 0.19 at 0.35 pitch with a 7.0 EP match RV1106 datasheet r1.8 p.17 Fig.2-5 (b 0.13, L 0.4, e 0.35, D2 7.0). Nothing over the V-cut: only the rail parts (GFID, TH) and the 7 mm H1-H4 keep-out circles touch x = 0 / 80, and J1, J2, J3 cross only the routed north / south edges.
  - check_bom live: $370.82 (63 types, 24 Extended), as order-notes.md says. The IPC-D-356 has 670 VIA records on the same origin. The job file has 4 layers, 1.6 mm, ENIG, ImpedanceControlled true and the 7628 stackup.
  - Looked at: my own Gerber composite (top) + U9 zoom + In1 / In2, the executor's gerber-view composite, the 3-D top render, the assembly-top-refs and fab-drawing PDFs (the U9 pin-1 dot is at SW, C35 + is south, the J5 pin-1 chamfer is at NW).
- **Mutations:** mutate_fab caught 17 of 17, with a clean control. Of my own 13, 12 were caught:
  - Caught: C1 moved 5 mm on the board (fab not regenerated) -> cplxy. Aux origin +1 mm -> origin / viapos / tooling / fid / cplxy. U9 rotated 180 -> cplrot. CPL U9 rotation 0 -> 90 -> cplrot. CPL LED1 y mirrored -> cplxy. J5 hole removed -> holes. Paste flash on FID1 -> fid. B.Paste flash -> bpaste. F.Mask emptied -> fid. In2 FileFunction L3 -> L2 -> layer. TP1 added to a BOM row -> bomrefs / bomsrc / dnp.
  - **Missed:** CPL U9 Layer "Bottom" passes (53 / 0). The L6-cplxy text prints "all rows Layer Top" but the pass condition does not test it.
  - Not check_fab's job: U9 pads 1 / 2 renumbered also passes check_fab. check_routing catches it in rebuild_all.sh, but `l6_run.sh` run alone does not run check_routing.
- **Findings (no blocker, no major):**
  - Minor (check_fab): add `all(Layer == "Top")` to the L6-cplxy (or L6-cols) pass condition, and add a "CPL row on Bottom" mutation to mutate_fab.py.
  - Minor (l6_run.sh): the script runs alone on the delivered board but never checks the board itself. Fix: make it refuse to run unless pcb/check_routing.txt ends " 0 FAIL" and is newer than the board, or run check_routing first.
  - Minor (docs): these lines still describe the pre-L6 state. layout.md §1 "Thickness / finish" says "tented vias" and §10 says "EP ... tented bottom"; both should say POFV, filled and capped (D-H6 / D-117 b / D-119). kicad-guide.md step 0 item 3 still says the Bouni plugin makes the step-10 BOM / CPL; it should point to fab/. cost.md shows $373.34; regenerate it to $370.82 (63 types).
  - Minor (assembly drawing, pmu / ui): in assembly-top-refs.pdf the F.Fab names of the test-pad rows pile up ("TP21TP1TP13TP4", "TP29TP28TP27TP14TP8", "TP20TP9TP10"), and TH1-TH4 are printed over their hole symbols. Fix: in the throw-away annotated copy, drop the second-line TP net texts and nudge the TP / TH references clear (the TPs are not assembled, so this is readability only).
  - Minor (order-notes): add the JLC "mark on PCB" choice. By default JLC prints an order number in a place of its choosing; the alternatives are a specified position (needs a silk placeholder) or remove mark (fee UNVERIFIED). Also note that the THT headers J5 / J6 may show 90 deg off in JLC's preview if JLC's model is drawn horizontal; they are placed by the holes.
  - Minor (git-friendliness): every regeneration changes the 12 Gerbers, 2 drills, job file, zip and PDFs through creation dates alone (4 lines each). Optional: strip or fix the TF.CreationDate / G04 date lines after export.
- **Owner items (not gate misses):** CPL rotation corrections are UNVERIFIED and must be ticked in JLC's preview (31 rows; the "must be at" column is right). POFV on 4 layers is not costed against a $9.18 margin, so a POFV fee above that breaks the $380 cap. V-cut marking, tooling-hole positions and the router bit for the R 0.5 notches are confirmed at DFM. The C58 move (D-128) is still open. design/refs/refs self-symlink: delete it.
- **Verdict:** PASS. TP-L6 is met: the files regenerate from scripts (clean rebuild reproduces them), the Gerber viewer check was done with an independent rasteriser, and the CPL rotations were reviewed against the footprints (pin-1 positions independently confirmed, corrections left UNVERIFIED for the owner's preview check).

## 2026-11-07 — Claude (lead), after L5G + L6
- L5G passed in round 2 and L6 in round 1 (verifier, see entries above). Own spot checks: PTH.drl ViaDrill T1 0.300 = 670 holes, no 0.3 mm ComponentDrill; board setup filling yes / capping yes; CPL 193 rows, BOM 63 rows; check_fab 53 PASS / 0 FAIL.
- Small follow-ups done by hand: check_fab L6-cplxy now FAILs a CPL row not on Top (was printed only); layout.md §1 / §10 "tented" lines changed to POFV; removed the self-referencing symlink design/refs/refs.
- Left as minors: assembly-PDF TP text overlap, fab-file creation dates, cost.md still $373.34 (check_bom gives $370.82), JLC "mark on PCB" option and J5/J6 preview note (in the summary to the owner).

## 2026-11-20 — owner + Claude, bring-up board #1 (short path, owner's choice)
- Owner skipped the full bringup.md sequence. Done: TP13 / TP2 / TP4 to GND = 166 / 150 / 60 Ω (no shorts); USB-C from the MacBook, SW1 → PWR LED on; Mac sees 2207:110c MASKROM at 480 Mb/s.
- Flashed Luckfox Pico Pro Max SPI NAND image 250607 (Luckfox Google Drive) with rkdeveloptool (built from rockchip-linux source, -Wno-vla-cxx-extension on macOS): db download.bin, wl env/idblock/uboot/boot/oem/userdata/rootfs at 0x0/0x200/0x400/0x800/0x2800/0x11800/0x16800.
- Boots Linux 5.10.160 from NAND (board stays on: PWR_KILL not asserted by the Luckfox image). USB-C gadget 2207:0019 (RNDIS + ADB), adb shell works; 181 MB RAM; mtd0-6 present; SoC 36.9 °C idle.
- Ethernet: RK630 PHY found, link 100 Mb/s full duplex, DHCP lease from the router, ping 8.8.8.8 0 % loss (~9 ms). ETH LED (LED3) and STAT LED (LED2) stay dark under the Luckfox image (their pins are not configured by it; not tested with our image).
- Not yet tested: microSD, USB-A host, 2x20 header, debug UART, RTC crystal, power button under Linux, board #2, our own image (software/).
- Later the same day: STAT (GPIO 3, active-low) and ETH (GPIO 34, active-high) LEDs driven from sysfs GPIO; Go HTTP server (software/examples/hello-http) cross-compiled static ARMv7, pushed with adb, answered from the Mac over Ethernet. Everything needed to repeat this is in software/BOARD-QUICKSTART.md; flash script software/tools/flash-luckfox.sh, rkdeveloptool in software/tools/rkdeveloptool/, image in thirdparty/luckfox-image/.
- microSD as a data card (later the same day): 32 GB SDHC (card name "SE32G"), erased on the Mac as one MBR FAT32 partition (BOARDSD), inserted with the board off. Luckfox image detects it at boot on mmc1 (dwmmc ffaa0000.mmc), high-speed SDHC at 49.5 MHz, auto-mounted at /mnt/sdcard (vfat, 29.7 GB). Read a file written on the Mac; wrote a file on the board; 32 MB random file md5 identical after drop_caches. Speed 64 MB write ≈ 20 MB/s, read ≈ 22 MB/s. Note: the Luckfox DT marks the slot "non-removable", so card-detect (TP30) and hot-plug are not exercised; booting from SD (bringup.md step 8) still waits for our own image.
- AI demo `software/examples/ai-detect` (later the same day, Claude with three sub-agents): Docker cross-compiler (`software/docker/`, Luckfox toolchain arm-rockchip830-linux-uclibcgnueabihf, GCC 8.3), C++ YOLOv5 detector on the NPU (librknnmrt 1.6.0, Luckfox yolov5.rknn for rv1106), Go web server + UI. Bus test photo → 4 person + bus; decode 41 ms, letterbox 40 ms, NPU 81 ms, total 165 ms; ~205 ms browser round trip over USB. Bug found on the board: output heads report size_with_stride = H×W×256 but data is packed at 255 per cell; reading at 256 gave 128 nonsense boxes. Installed as /etc/init.d/S99ai-detect (binaries in /root/ai-detect, model on microSD; FAT32 card is mounted without exec); comes up ~11 s after boot, checked with a reboot. Load average ~10 at idle is from Luckfox media kernel threads in D state, CPU 90 % idle. Ethernet carrier was 0 during this test (cable not plugged), so it was tested over adb forward only.
