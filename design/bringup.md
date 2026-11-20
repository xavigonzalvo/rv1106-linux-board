# Bring-up procedure (Phase 6, Rev A)

Status: Executor, Phase 6 round 2, 2026-10-29 (verifier round-1 findings fixed: the rail isolation now happens **before** the
first power, Q_PWR diode check added, polarity-aware resistance limits, inrush note, USB_DET caveat, part names; D-78 amended,
D-80). For human phase **H3** (at the bench, Claude guides).
Test-point numbers, nets and acceptance bands are in `testpoints.md` (§1). Every part is written **FUNCTIONAL_NAME [silkscreen
ref]**; the bracket is what is printed on the board (bom.csv, refmap.csv `bom_ref`). Bare Luckfox designators are never used
here; for the few parts whose refmap name is a Luckfox designator the bench names of testpoints.md "Part names" are used
(e.g. R_MIPI_1R [R32]). Decisions: D-77 (TP list), **D-78 (this procedure: rail-isolated first power-up)**, D-79 (acceptance
bands), D-80 (round-2 changes). Sources: as in testpoints.md (tags [DS], [TLV], [LTC], [XTAL], [SDK]); power.md §3 (sequence)
and §6 (button) for the design numbers; [CD] = https://concept-docs.readthedocs.io/en/latest/board/luckfox/luckfox-pico.html
(MASKROM USB ID 2207:110c, research.md §4).

## 0. Ground rules

1. **One step at a time, in order.** Do not start step N+1 until step N passed on that board. Each step has a *stop* line:
   if it triggers, remove power and fix the cause before going on. Section 3 explains why the order keeps a failure at step N
   from damaging anything at step N+1.
2. **Always a current limit.** Steps 2–5 use a bench supply with a current limit, fed into the USB-C port through a USB-C
   power breakout/pigtail. Start every step at the limit given there. Raise it only as the step says. From step 3 on, a
   **≥ 470 µF / ≥ 10 V electrolytic capacitor sits across VBUS/GND at the breakout** (see step 3, "Inrush").
3. **Nothing plugged in that the step does not need.** No microSD, no USB-A device, no Ethernet cable and nothing on the 2×20
   header until the step that tests it. Accessories connected to an unpowered board can back-feed it (D-30, D-31).
4. **Only 3.3 V UART adapters.** Before connecting any USB-UART adapter, measure its TX pin idle level: it must be ≤ 3.4 V.
   A 5 V adapter can damage SoC pin 80, which is supplied from GPIO1_VCC3V3: **supply abs-max 3.63 V** ([DS] Table 3-1 p.20);
   the pin's own input limit is not given in [DS] (UNVERIFIED).
5. ESD: wrist strap or touch ground before handling. Hold boards by the edges.
6. Write every measured value into the record sheet (§4). Board #1 first; board #2 follows §2.
7. **DMM polarity.** In every unpowered resistance or diode check, the black lead is on **TP19 (GND)** unless the line says
   otherwise. Regulator, MOSFET and ESD body diodes make many unpowered readings depend on lead polarity; readings taken with
   the other polarity are not comparable with the limits below.

**Equipment.** Required: DMM with diode mode and continuity beeper; bench supply 0–6 V / ≥ 2 A with adjustable current limit;
USB-C power breakout/pigtail that brings VBUS and GND out to wires (a bench supply has no CC logic, so the board's 5.1 kΩ Rd
play no part); a ≥ 470 µF / ≥ 10 V electrolytic capacitor for the breakout; fine tweezers, soldering iron, flux, a scalpel;
one 10 kΩ through-hole resistor with clip leads; a 3.3 V USB-UART adapter; a microSD card (≥ 8 GB); a PC with the Rockchip
`rkdeveloptool` (or `upgrade_tool`); an Ethernet cable and a router with DHCP. Strongly recommended: an oscilloscope (≥ 100 MHz,
2–4 channels, 10× probes with ground springs) — steps 2, 4 and 5 have a DMM-only variant, but the 24 MHz check (TP6) and the
power sequence capture need a scope. Useful: USB-A breakout + 10 Ω / 5 W resistor (step 11), USB thermometer or IR thermometer.

**Software needed.** The SD image comes from the Phase 8 build (`software/README.md`). Nothing in steps 0–7 needs it.

## 1. Procedure (board #1)

### Step 0 — Inspect (no power)
1. Under magnification: the SoC U_SOC [U9] (QFN-128, 0.35 mm pitch) — no bridges on any side, body centred, no lifted corner.
   Same for U_ONOFF [U3], U4–U7, U_MUX [U11] (UQFN-10), U_NAND [U10].
2. Polarity/orientation: D_TVS [D1] (cathode band towards VBUS_5V), D_RTC [D2], LED1–LED3, the 120 µF polymer capacitor at the
   USB-A jack (marked side = negative), Y1 pin 1, Q1–Q4. Q_PWR [Q1] (AO3401A, P-channel) and Q_KILL [Q3] (AO3400A, N-channel)
   are both SOT-23 parts on this BOM; a reel mix-up between them cannot be seen reliably by eye — the step-1 diode check finds it.
3. THT joints of J1 shell, J3 (RJ45), J4 (USB-A), J5 (2×20), J6 (1×3): filled, no bridges.
4. Check the board as delivered has all four measurement links fitted (JP_MEAS_0V9 [JP1] bridged; R_MEAS_1V8 [R29],
   R_MEAS_3V3 [R30], R_MEAS_DDR [R31] present). Step 1.B opens them.

*Stop:* any bridge on the SoC, a missing or rotated part. Fix (or ask JLCPCB) before any power.

### Step 1 — Resistance and diode checks (no power, links still fitted)

**1.A Resistance to GND.** DMM in resistance mode, **black on TP19, red on the point** (ground rule 7). Wait for the reading to
settle (capacitors charge).

| Measure | Expected | Stop |
|---|---|---|
| TP21 (VBUS_IN), TP1 (VBUS_5V) to GND | > 10 kΩ (climbs while C2–C4 charge; TVS and LTC2954 leakage only) | < 100 Ω |
| TP21 ↔ TP1 (across F1) | ≈ 0 Ω (same as shorted leads) | > 1 Ω (fuse open/bad joint) |
| TP13 (VCC5V0_SYS) to GND | ≈ 460 Ω (R_BL5 [R12] 470 Ω ∥ USB_DET divider 28 kΩ ∥ diode paths) | < 100 Ω |
| TP4 (VDD_0V9) to GND | ≤ 1.0 kΩ (R_BL09 [R25] 1 kΩ ∥ divider 150 kΩ ∥ SoC core) | < 10 Ω |
| TP5 (VCC_DDR) to GND | ≤ 1.0 kΩ (R_BL135 [R26]) | < 10 Ω |
| TP3 (VCC_1V8) to GND | ≤ 680 Ω (R_BL18 [R27]) | < 10 Ω |
| TP2 (VCC_3V3) to GND | ≤ 680 Ω (R_BL33 [R28]) | < 10 Ω |
| TP16 (VCC3V3_SD) to GND | **> 500 Ω** (R_SD_BL [R40] 10 kΩ ∥ the Q_SD [Q4] body diode into VCC_3V3 and R_BL33 680 Ω, so it reads well below 10 kΩ) | < 100 Ω |
| TP17 (VBUS_USBA) to GND | > 10 kΩ (polymer capacitor leakage; climbs) | < 100 Ω |
| Every pair of TP13, TP4, TP5, TP3, TP2 (red on the first-named) | **> 100 Ω**. Diode paths (buck switch body diodes from SW to VIN and from GND to SW, ESD structures in the SoC) make these readings polarity dependent and much lower than the sum of the two to-GND readings | < 10 Ω (rails shorted together) |
| U4 pin 5 (FB) to GND, probe **on the IC lead** | 32.6–34.4 kΩ = 100 k ∥ (49.9 k + rail), ±2 % | > 1 MΩ = open FB joint; ≈ 100 kΩ = R_FBT_U4 [R17] missing; ≈ 51 kΩ = R_FBB_U4 [R13] missing |
| U7 pin 5 (FB) to GND | 54.8–57.3 kΩ = 100 k ∥ 127 k | ≈ 100 kΩ = R_FBT_U7 [R18] missing; ≈ 128 kΩ = R_FBB_U7 [R16] missing; open |
| U5 pin 5 (FB) to GND | 65.4–68.1 kΩ = 100 k ∥ 200 k | ≈ 100 kΩ = R_FBT_U5 [R19] missing; ≈ 201 kΩ = R_FBB_U5 [R14] missing; open |
| U6 pin 5 (FB) to GND | 79.9–83.2 kΩ = 100 k ∥ 442 k | ≈ 100 kΩ = R_FBT_U6 [R22] missing; ≈ 443 kΩ = R_FBB_U6 [R15] missing; open |

The SoC adds unknown parallel paths on its rails (DMM test current through unpowered silicon; UNVERIFIED values), so the
rail-to-GND readings are upper bounds. **Compare with board #2 — the two boards should agree within ≈ 10 %** (same meter, same
range, same polarity). A bare PCB (3 spares) reads open between every rail and GND: if a rail is shorted on the assembled
board, the bare board tells you whether it is a PCB fault or an assembly fault. An open FB lead would let that buck drive its
output towards 5 V; this check catches it before any power. (A swapped divider reads the same in-circuit, which is why the
links are opened in 1.B and the bucks are proven in step 3 before their outputs meet the SoC.)

**1.Q Q_PWR [Q1] diode check.** DMM in **diode mode**. Q_PWR is a P-channel FET with source on VBUS_5V (TP1) and drain on
VCC5V0_SYS (TP13); its body diode conducts from drain to source.

| Leads | Expected | Stop |
|---|---|---|
| red on TP13, black on TP1 | ≈ 0.4–0.7 V (P-FET body diode, forward) | ≈ 0 V (< 0.1 V) = D-S short; ≈ 1 V or more / OL = Q1 missing, open, or an N-channel part (e.g. the AO3400A of Q_KILL [Q3]) fitted in its place. The ≈ 1 V reading comes from the parallel path through R_BL5 [R12] and the forward-biased D_TVS [D1] (computed estimate) |
| red on TP1, black on TP13 | **OL**, or a high reading > 2 V on meters whose diode-mode current partly powers U_ONOFF [U3] (may show a falling reading for a second while C_VBUS [C2] and C_GS [C4] charge) | ≈ 0 V = D-S short; a steady 0.3–0.8 V = body diode reversed, i.e. an N-channel FET fitted as Q1 |

A D-S short or a wrong FET type would let VBUS_5V reach VCC5V0_SYS at plug-in without a button press. Do not power the board
until both readings are right. **Board #2 repeats 1.Q** (§2).

**1.B Isolate the buck outputs from the SoC (still no power).** From here until step 4/5 the regulator outputs cannot reach
the SoC, so even a fault in the very first power-on (step 2) can only reach the regulator side of the links. The design puts
each buck's feedback divider and output capacitors on the regulator side of its link (D-68, D-73), so opening a link never
opens a control loop.
1. Cut the copper bridge of **JP_MEAS_0V9 [JP1]** with a scalpel (two strokes, then clean with IPA).
2. Remove **R_MEAS_1V8 [R29], R_MEAS_3V3 [R30], R_MEAS_DDR [R31]** (0R 0603). Keep them in a labelled bag.
3. Check, black on the pad 2 (SoC side), red on pad 1 (buck side, silkscreen "B"):

| Measure | Expected | Stop |
|---|---|---|
| JP1, R29, R30, R31: pad 1 ↔ pad 2 | **not ≈ 0 Ω**: continuity beeper silent and > 500 Ω (real readings are ~1–3 kΩ: diode paths through the buck body diodes, R_BL5 470 Ω and the SoC-side bleeder, and the 150–540 kΩ dividers; polarity dependent, so record and compare with board #2 only if both were isolated) | beeper sounds / < 10 Ω = still bridged or solder left on the pads |
| JP1, R29, R30, R31: pad 1 to GND (black on TP19) | > 500 Ω (divider ∥ output capacitors ∥ body diode via VIN and R_BL5) | < 10 Ω = shorted buck output |
| Step 1.A row "TP4/TP5/TP3/TP2 to GND" again | now ≈ the bleeder alone: ≤ 1.0 kΩ / ≤ 1.0 kΩ / ≤ 680 Ω / ≤ 680 Ω | < 10 Ω |

*Stop (whole step 1):* any value in a stop column. Fix before any power.

### Step 2 — First power, board stays off (plug-in test), links open
Setup: bench supply 5.00 V, **limit 100 mA**, into the USB-C breakout (no electrolytic yet: this step tests the plug-in edge as
a real cable delivers it). Scope (if available): CH1 TP13, trigger rising 0.2 V.
1. Connect. Supply current **< 2 mA** (LTC2954 + R_ENPU [R8] 50 µA + TVS leakage; the SMAJ5.0A leakage at 5 V is not from a
   downloaded datasheet: UNVERIFIED, hence the 2 mA allowance).
2. TP21, TP1 = 4.95–5.05 V. TP8 (ONOFF_EN) ≤ 0.4 V. TP12 (EN_N) ≈ 0.985 × TP1. **TP13 < 0.1 V.** TP4, TP5, TP3, TP2 < 0.05 V.
   **Buck-side link pads while off: JP1 pad 1, R29 pad 1, R30 pad 1, R31 pad 1 all < 0.05 V** (proves no buck is running).
3. Unplug and re-plug 10 times while the scope watches TP13: it must not rise above 0.4 V (power.md §6.3: the C_GS/C_GD
   divider keeps Q_PWR off at plug-in; computed |VGS| ≤ 0.25 V).

*Stop:* current > 5 mA, TP13 > 0.4 V at any plug-in, TP8 high while nobody pressed the button, or any buck-side pad > 0.1 V.
*Proves:* input protection, fuse, controller supply, and that Q_PWR stays off. Only `usbc`, `prot` and `onoff` are powered.
*If it fails:* because the links were opened in 1.B, a Q_PWR that conducts at plug-in can only start U4/U5/U7 into their own
dividers and output capacitors (rated ≥ 6.3 V: C_OUT_U5 [C27], C_OUT_U7 [C28] 22 µF 6.3 V; C_OUT_U4 [C24] 10 µF 10 V;
bom.csv), never into the SoC. U6 cannot start at all: its enable comes from the SoC-side VCC_1V8 through R_PWREN_FEED [R24]
(power.md §3). The only VCC5V0_SYS path into the SoC is the USB_DET divider (≤ 0.44 mA through R_DET_TOP [R3] 10 kΩ, see step 3).

### Step 3 — Rail-isolated power-up (buck outputs disconnected from the SoC since 1.B)
Purpose: prove that U4, U5 and U7 regulate to the right voltage **before** their output reaches the SoC (a wrong or swapped
divider would otherwise overvolt the SoC: e.g. 1.8 V on the VDD_0V9 core with its 0.99 V abs-max, [DS] Table 3-1 p.20).

Prepare (unpowered):
1. **Inrush:** solder or clip a **≥ 470 µF / ≥ 10 V electrolytic across VBUS and GND at the USB-C breakout** (mind the
   polarity). Reason: the turn-on inrush into VCC5V0_SYS is up to 0.65 A for ≈ 1–2 ms (60.5 µF, power.md §6.3, check P9), while
   VBUS_5V on the board has only ≈ 2.8 µF (C_VBUS [C2] 2.2 µF, C_ONOFF_VIN [C3] 100 nF, C_GS [C4] 470 nF). A bench supply with a
   fast constant-current loop at 100 mA could let VBUS_5V sag below the LTC2954 undervoltage lockout (VUVL 2.2–2.5 V, VIN
   falling, [LTC] p.3), and the board would switch on and off at once — a false stop, not damage. Keep the capacitor for all
   bench-supply steps (3, 4, 5, 7).
2. Clip the **10 kΩ resistor from TP1 (VBUS_5V) to TP29 (PWR_KILL_N)**. Reason: with VCC_3V3 disconnected from the SoC side,
   nothing pulls the LTC2954 KILL pin high, and the controller would switch the board off again after 400–650 ms ([LTC] p.3
   tKILL,ON BLANK; p.9). With the resistor KILL sits at ≈ 4.5 V, below its 7 V abs-max ([LTC] p.2), and only ≈ 30 mV leaks
   into the disconnected VCC_3V3 net (through R_KU [R6] 100 kΩ into R_BL33 [R28] 680 Ω).
3. **USB_DET caveat.** During this step the SoC is completely unpowered, but VCC5V0_SYS feeds the USB_DET divider R_DET_TOP [R3]
   10 kΩ / R_DET_BOT [R4] 18 kΩ into pin 25 (USB_VBUSDET). That pushes up to **≈ 0.44 mA** ((5 − 0.6 V) / 10 kΩ, upper bound;
   ≈ 0.37 mA computed with R4 and R_BL33 in place) through the pin's protection structure into the unpowered USB_AVDD3V3 /
   VCC_3V3. [DS] gives no injection limit (UNVERIFIED, D-40). So **keep every powered interval of steps 3 and 4 short: about
   2 minutes — measure, then power off.** Option (removes the injection completely): remove R_DET_TOP [R3] (0402) now and refit
   it in step 5 together with R_MEAS_3V3 [R30].

Run: supply 5.00 V, **limit 100 mA**.
4. Press SW_PWR [SW1] for ≈ 0.2 s. The board turns on and stays on. Supply current after the inrush **10–30 mA** (R_BL5 10.6 mA;
   bucks without load draw ≈ 35 µA each, [TLV] p.4; plus ≤ 0.44 mA USB_DET).
   *If the board switches on and immediately off* (TP13 falls in well under 400 ms, i.e. before the KILL blanking could end):
   that is the supply's current limit dragging VBUS_5V into UVLO, not a design fault. Power off, re-check the step-1 readings
   (TP13 to GND, rail pairs, 1.B pads), confirm the electrolytic is fitted, and retry at **300 mA**. Record which limit was used.
5. Measure on the buck-side pads (testpoints.md §1.2):

| Point | Accept | Stop |
|---|---|---|
| TP13 VCC5V0_SYS | ≥ TP1 − 0.05 V | — |
| JP1 pad 1 (VDD_0V9_BUCK) | 0.876–0.94 V | > 0.95 V |
| R31 pad 1 (VCC_DDR_BUCK) | 1.320–1.43 V | > 1.45 V |
| R29 pad 1 (VCC_1V8_BUCK) | 1.741–1.90 V | > 1.98 V |
| R30 pad 1 (VCC_3V3_BUCK) | **0 V — expected**: U6 is enabled from the SoC-side VCC_1V8 through R_PWREN_FEED [R24] (power.md §3), which is disconnected now | > 0.1 V |
| TP4, TP5, TP3, TP14 | < 0.05 V (isolation works) | > 0.1 V |
| TP2 (VCC_3V3) | < 0.05 V with R_DET_TOP [R3] removed; **≤ 0.35 V with it fitted** (USB_DET injection × R_BL33 680 Ω ≈ 0.25 V computed + ≈ 30 mV from the KILL hold-up; the path through the SoC is UNVERIFIED) | > 0.5 V |

   With no load the bucks run in Power Save Mode and sit "slightly above the nominal output voltage" ([TLV] p.6 §7.3.1;
   amount not given, UNVERIFIED), hence the upper accept edges ≈ 2 % above the design bands. They stay below the [DS] Table 3-2
   maxima.
6. Short press SW_PWR: TP27 (PB_INT_N) stays ≈ 0 V (its pull-up is on the unpowered VCC_3V3) — the board stays on. Then **hold
   SW_PWR**: the board turns off after **8.07–22.4 s** (nominal ≈ 14 s; C_PDT 2.2 µF since D-117 c; power.md §6.2 hard-off window). Time it. Release; wait 1 s.
7. Optional, scope: remove the 10 kΩ hold-up, press SW_PWR once. TP13 goes high and falls again after **400–650 ms** (aborted
   power-on, [LTC] p.9). This proves the safety net that switches the board off when VCC_3V3 never comes up.

*Stop:* any value in the stop column, current > 50 mA after the inrush, anything warm.
*Proves:* the three first-stage bucks regulate correctly with nothing of the SoC attached; the button's on and hard-off work.

### Step 4 — Core, DDR and 1.8 V to the SoC; 3.3 V still isolated
Prepare (unpowered): solder JP1 closed again (a solder blob across the pads; check ≈ 0 Ω, beeper sounds); refit
**R_MEAS_DDR [R31]** and **R_MEAS_1V8 [R29]** (check each ≈ 0 Ω). R_MEAS_3V3 [R30] stays out (and R_DET_TOP [R3] too, if you
removed it). Electrolytic at the breakout stays. Now the SoC gets VDD_0V9, VDD_ARM, VCC_DDR and VCC_1V8, U6 starts from
VCC_1V8, and the SoC stays in reset because the NPOR pull-up R_NPOR_PU [R43] is on the disconnected VCC_3V3.

Scope variant (preferred): remove the hold-up resistor. Supply 5.00 V, **limit 300 mA**. Scope CH1 R30 pad 1
(VCC_3V3_BUCK), CH2 TP4, CH3 TP3, CH4 TP5, single-shot, 50 ms/div. Press SW_PWR. The board turns on and the LTC2954 turns it
off again after 400–650 ms; that short window is all this step needs and keeps the "3.3 V missing" state brief.
DMM variant: keep the hold-up, measure quickly, and **unplug within 30 s** (D-78: the state with core/DDR/1.8 V up and 3.3 V
down is the normal intermediate state of every power-on (power.md §3 steps 1–3), and [DS] r1.8 gives no sequencing rule,
but holding it for long is not proven harmless; e.g. the USB_DET divider still pushes up to ≈ 0.44 mA into pin 25 while
USB_AVDD3V3 is unpowered, unless R_DET_TOP [R3] is out (D-40, injection limit UNVERIFIED)).
*If the board switches off at once* (TP13 falls in < 100 ms, much earlier than the 400–650 ms KILL abort), the supply limit
dragged VBUS_5V into the LTC2954 UVLO during the inrush: re-check the step-1 readings, confirm the electrolytic, retry at
**500 mA**, and record which limit was used.

| Point | Accept | Stop |
|---|---|---|
| TP4 VDD_0V9 / TP15 VDD_ARM (TP15 is west of the SoC beside C44, not in the power row: testpoints.md §2 rule 2) | 0.876–0.924 / 0.873–0.924 V | > 0.95 V or TP15 < 0.85 V |
| TP5 VCC_DDR | 1.320–1.405 V | > 1.45 V |
| TP3 VCC_1V8; TP22–TP25 | 1.741–1.861 V; sub-rails per testpoints.md | > 1.98 V |
| TP14 PWR_EN | 1.74–1.86 V | < 1.2 V (U6 would not start) |
| R30 pad 1 VCC_3V3_BUCK | 3.135–3.44 V (no load) | > 3.465 V |
| TP2 VCC_3V3 (SoC side, isolated) | ≤ 0.35 V (as step 3) | > 0.5 V |
| Order on the scope | TP4 first; TP3 and TP5 ≥ 0.5 ms later; VCC_3V3_BUCK ≥ 1.2 ms after TP3 and TP5 | any rail before TP4 |
| Supply current | record (SoC in reset; no datasheet figure, UNVERIFIED) | > 300 mA (or > the raised limit) sustained |

*Proves:* the SoC's low-voltage rails are correct under the real load, the order is right, and U6 regulates correctly before
its output reaches the SoC.

### Step 5 — Full power-up, no boot media (BootROM → MASKROM)
Prepare (unpowered): refit **R_MEAS_3V3 [R30]** (check ≈ 0 Ω) and, if you removed it, **R_DET_TOP [R3]**. Remove the hold-up
resistor if it is still there. Electrolytic at the breakout stays. Nothing else plugged in.
Supply 5.00 V, **limit 500 mA**.
1. Scope: CH1 TP13, CH2 TP4, CH3 TP3, CH4 TP2, trigger TP13 rising, 1 ms/div. Press SW_PWR. Expect the power.md §3 order:
   VDD_0V9 good ≤ 1.87 ms after TP13 starts; VCC_1V8/VCC_DDR later; VCC_3V3 ≥ 1.2 ms after both; no overshoot above the stop
   limits; monotonic ramps. Repeat with CH4 = TP7 (NPOR): it rises with TP2, last of all
   (RC of R_NPOR_PU [R43] 1 kΩ and the nPOR cap C_NPOR [**C71**] 100 nF, τ = 100 µs; the Luckfox schematic calls this
   cap C38, on this board C38 is a VDD_ARM 10 µF decoupler).
2. The board stays on for > 1 s: TP29 (KILL) ≈ TP2 well within the 400 ms blanking.
3. DMM on every TP of testpoints.md §1: all within their accept bands. In particular TP8 ≈ TP1, TP12 ≤ 0.4 V,
   TP13 ≥ TP1 − 0.12 V, TP16 ≈ TP2 (card power on by default), TP17 = 0 V, TP27 ≈ TP2, TP28 ≈ 0 V, TP11 = 0 V.
   LED1 (power) on, LED2 (status) dark (pin 62 pull-up, active-low, D-20), LED3 dark.
4. TP6: 24.000 MHz ± 50 ppm (10× probe, ground spring to TP31). No oscillation = stop.
5. Supply current: record. The NAND is blank and there is no SD card, so the BootROM ends in MASKROM ([CD]); no datasheet
   figure exists for this current (UNVERIFIED). Stop above 500 mA.
6. After 2 minutes: no part hot to the touch (U4–U7, SoC, Q_PWR [Q1]). An IR thermometer reading > 60 °C on any part = stop.
7. Button without Linux: a short press makes TP27 go low while held (≥ 26–41 ms after the press, [LTC] p.3) and nothing else
   happens. Hold: off after 8.07–22.4 s (never before 8 s; D-117 c). Press again ≥ 0.4 s later: it starts again (lockout 200–325 ms, [LTC] p.3).
8. SW_RESET [SW2] held: TP7 ≈ 0.30 V; power stays on.
9. Card-detect polarity (verifier P5 minor 1): with the board on, TP30 without a card, then with any microSD inserted. Record
   both. Expected per pinmap.csv: ≈ TP2 without a card, ≈ 0 V with one. If reversed, Phase 8 sets `cd-inverted`.

*Stop:* any rail outside its stop limit, wrong order, no 24 MHz, current > 500 mA, a hot part.
*Proves:* the whole power system, reset and clock with the SoC alive.

### Step 6 — USB-C data path (MASKROM)
Power the board from a PC USB port with a USB-C data cable instead of the bench supply (the PC port is current-limited; the
board is in MASKROM, well below the full budget). Press SW_PWR. On the PC, `rkdeveloptool ld` (or `lsusb`) lists a
Rockchip device **2207:110c** ([CD]). Do not write anything yet.
*Proves:* USB PHY, USB_DET, the USB mux default position (USB_SEL low → USB-C, D-05/D-20) and the recovery path. If this
works, a bad SD or NAND image can always be recovered later.

### Step 7 — Debug UART
1. Check the adapter (ground rule 4). Board off: connect adapter GND → J_UART [J6] pin 1 and adapter RX → J6 pin 2 (board TX).
   Leave the adapter's TX unconnected for now (D-30: an adapter TX driving pin 80 while the board is off back-feeds VCCIO1,
   limited to ≈ 3 mA by R_UART_RX [R67]).
2. Terminal 115200 8N1 ([SDK] fiq-debugger). Power on (bench supply, limit 500 mA). In MASKROM the BootROM prints little or
   nothing; that is fine. TP9 idles high once the UART is set up (pin 79 resets with a pull-down, [DS] Table 2-1 p.18).
3. After power-on, connect adapter TX → J6 pin 3. From now on connect TX only while the board is on, or accept the limited
   back-feed.

### Step 8 — Boot Linux from microSD (R5)
Board off. Insert the microSD card with the Phase 8 image. Raise the current limit to **1.5 A** (budget 1.41 A, power.md §5).
Power on. The console shows the DDR init (expect 256 MB), U-Boot, the kernel and a login prompt. If the loader prints garbage
before U-Boot, try 1 500 000 baud for that part (the pre-loader baud of this SDK is UNVERIFIED; the SDK console is 115200).
At the shell: repeat the DMM check of TP4, TP15, TP5, TP3, TP2 (Linux idle) and record the supply current.
If the board does not boot from SD: the BootROM order SD vs NAND is UNVERIFIED (D-24). The NAND is blank on a new board, so
it cannot be the cause yet; check the image, TP16 (card power) and TP30.

### Step 9 — Power button under Linux (R4)
1. Short press SW_PWR: the console shows a clean shutdown (BusyBox acpid → `poweroff`, software/sdk-notes.md §5), then the
   board switches itself off: TP13 → 0 V. Before this step check that the boot log of step 8 shows `gpio-poweroff bound` (S15board).
   Scope single-shot: TP27 low during the press; TP28 pulses high at the end of the shutdown; TP29 falls; TP13 falls.
2. Power on again, hold SW_PWR: hard off after 8.07–22.4 s (nominal ≈ 14 s) whatever Linux is doing.
3. Unplug and re-plug the supply: the board stays off until the button is pressed.
4. `reboot`: power stays on (TP13 stays high), board reboots. SW_RESET [SW2]: same.

### Step 10 — Ethernet (R2)
Cable to a router. `ip link` shows 100 Mb/s full duplex; TP11/LED3 blinks with traffic; DHCP lease; `ping` the router;
`ssh` into the board from the PC.

### Step 11 — USB-A host (R3)
1. Nothing plugged in. Set `USB_MODE=off` in `/etc/default/board` and reboot (software/README.md §7), then enable the port
   power from Linux with `board-usb vbus on` (USBA_VBUS_EN = GPIO0_A5 high).
   Scope CH1 TP13, CH2 TP17: TP17 rises to ≈ TP13 in about 1 ms (charging 142 µF at the U_USBA [U8] current limit, D-58);
   TP13 dips but the board keeps running (stop: the board resets or TP13 < 4.5 V).
2. Load test with a USB-A breakout and 10 Ω / 5 W: TP17 ≥ **4.44 V** at 0.5 A (D-49); TP13 ≥ 4.6 V.
3. Switch the mux to USB-A with `board-usb sel usba` (USB_SEL = GPIO0_A6 high; USB-C data is disconnected while it is high).
   The default image has `dr_mode = "host"` (`rv1106g-custom-reva.dts`). Plug in a USB flash drive:
   `lsusb` lists it; mount and read a file. Hot-plug it again with the scope on TP13.
4. Set `USB_MODE=auto` again and reboot: `board-usb status` shows `dr_mode=host USB_SEL=1 USBA_VBUS_EN=1`.

### Step 12 — On-board SPI NAND (R6)
Linux sees the W25N01KV U_NAND [U10] (`/proc/mtd`, 128 MB). Write the NAND image only after steps 0–11 passed. Afterwards the
BootROM may prefer NAND over SD (D-24). Recovery if a NAND image is bad: hold SW_RECOV [SW3] while pressing SW_PWR (MASKROM,
D-23) and reflash from the PC, or remove R_NANDDIS [R55] (0R in the NAND CS line, D-25) to hide the NAND.

### Step 13 — 2×20 header (R3)
Before connecting anything: J_HDR [J5] pins 1/17 ≈ TP2, pins 2/4 ≈ TP13, I²C lines idle ≈ TP2 (pull-ups 2.2 k / 4.7 k, D-29).
Then test GPIO, I²C (`i2cdetect -y 3`, `-y 1`), UART3 (`/dev/ttyS3`), SPI0 (`/dev/spidev0.0`) and PWM8–11 as the Phase 8 DTS
   enables them (software/sdk-notes.md §1); free header GPIOs carry their pinmap names in `gpioinfo`.

### Step 14 — Load, temperature and rail currents
1. Full load: CPU stress on all cores + Ethernet traffic + 0.5 A on USB-A. Supply current ≤ 1.42 A (power budget 7.09 W,
   power.md §5). TP15 ≥ 0.873 V, TP4 ripple on the scope (20 MHz limit) — record. After 10 minutes record the temperatures of
   U4, the SoC, Q_PWR [Q1], F1.
2. At full load, hard-off (hold until off, ≤ 22.4 s) and touch/measure Q_PWR straight after (power.md §6.3: turn-off stress inside the SOA,
   computed ≤ 21 mJ; this confirms it).
3. Optional per-rail current: replace a removed link (R_MEAS_1V8 [R29], R_MEAS_3V3 [R30], R_MEAS_DDR [R31]) by an ammeter in
   its 2 A/10 A range. **Do not do this on VDD_0V9** unless TP15 stays ≥ 0.85 V with the meter in circuit (a meter's burden of
   ≈ 50 mΩ at 1 A eats most of the 23 mV margin, power.md P3L). Refit the link after each measurement.

## 2. Board #2
Do steps 0, **1.A and 1.Q** (the Q_PWR diode check is kept on every board), 2 (without the buck-side pad check of 2.2, since
the links stay fitted), then 5–14 (in step 5 there is nothing to refit). Steps 1.B, 3 and 4 can be skipped on board #2 only if
board #1 passed them **and** board #2 passed every FB-lead check of step 1.A and both 1.Q readings: a wrong or swapped divider
would be a placement (systematic) error that board #1 already ruled out, the random defects (open FB joint, missing divider
resistor) are what the step-1.A FB readings catch, and the Q_PWR faults that could start the bucks at plug-in (D-S short,
wrong FET type) are what 1.Q catches. Board #2's step-1.A readings must agree with board #1's within ≈ 10 %. If any step-1
reading on board #2 is off, do 1.B, 3 and 4 on it as well.

## 3. Why the order is safe (gate TP-D6)

| Step | What passing it guarantees | What that protects in the next step |
|---|---|---|
| 0 Inspect | no visible bridges, parts present and oriented | step 1 readings are meaningful; a bridged SoC is never powered |
| 1.A Resistance | no rail shorted to GND or to another rail; every buck FB pin connected with both divider resistors | first power cannot drive a short; no buck can run open-loop to 5 V |
| 1.Q Q_PWR diode | Q_PWR is a P-FET the right way round with no D-S short | a wrong or shorted FET cannot pass VBUS_5V to VCC5V0_SYS at the step-2 plug-in |
| 1.B Isolate | JP1 cut, R29/R30/R31 out, verified open; no buck output shorted | **in step 2 and 3 no buck output can reach the SoC**, whatever goes wrong in the input/on-off path; a swapped divider (which 1.A cannot see) only meets its own output capacitors (rated ≥ 6.3 V) |
| 2 Plug-in, off | input path sound; Q_PWR stays off without a press; current < 2 mA; buck-side pads 0 V | step 3 is the first time any buck runs, and only when you press the button |
| 3 Isolated bucks | U4/U5/U7 outputs correct with the SoC disconnected; button on and hard-off work; inrush handled (electrolytic, limit recorded) | step 4 connects only rails that were just proven correct; a wrong divider can no longer reach the SoC |
| 4 Low rails to SoC, 3.3 V isolated | SoC low-voltage rails correct under real load; order right; U6 proven before its output reaches the SoC (R30 out) | step 5 connects VCC_3V3 that was just proven; the SoC never sees an unproven rail |
| 5 Full power, MASKROM | all rails, order, NPOR, 24 MHz, KILL/blanking, button paths, current and temperature OK with no software running | step 6 attaches a PC only to a board whose power is proven; step 7 attaches the UART adapter to a powered, correct VCCIO1 |
| 6 USB-C MASKROM | recovery path works | any later bad SD/NAND image is recoverable without rework |
| 7 UART (RX first, TX after power-on) | console works; no back-feed through pin 80 while off | step 8 can be watched; a boot failure is visible, not guessed |
| 8 SD boot | Linux runs at the full current limit 1.5 A, rails hold under load | step 9 tests the software power path on a running OS |
| 9 Button under Linux | clean shutdown, hard off, plug-in stays off | later steps can always be ended cleanly; no need to yank power while writing to SD/NAND |
| 10 Ethernet | network | step 11/12 can be driven over SSH |
| 11 USB-A | port power proven with no device and with a resistor before a real device is attached | a short or low-voltage port never meets a user's USB device |
| 12 NAND | NAND written last, recovery known (MASKROM, R_NANDDIS [R55]) | a bad NAND image cannot lock the board out |
| 13 Header | header voltages checked before anything is connected | accessories never see a wrong voltage |
| 14 Load | budget and temperatures at full load | — |

Each step adds exactly one new thing (a new rail, a new connector, a new current limit) and only after the step before
proved everything it depends on. The current limits (100 → 300 → 500 mA → 1.5 A) make a fault in any step a limited-energy
event. The only path from VCC5V0_SYS into the unpowered SoC that the links do not break is the USB_DET divider; it is limited
by R_DET_TOP [R3] 10 kΩ to ≤ 0.44 mA, kept to short powered intervals in steps 3–4, and can be removed entirely by lifting R3.

## 4. Record sheet (copy per board)

| Step | Item | Board #1 | Board #2 |
|---|---|---|---|
| 1.A | TP13 / TP4 / TP5 / TP3 / TP2 / TP16 to GND (Ω); meter model and range | | |
| 1.A | U4 / U7 / U5 / U6 FB to GND (kΩ) | | |
| 1.Q | Q_PWR diode: TP13→TP1 (V); TP1→TP13 (OL?) | | |
| 1.B | JP1 / R29 / R30 / R31 pad 1↔2 (Ω); pad 1 to GND (Ω) | | n/a unless isolated |
| 2 | current off (mA); TP1; TP8; TP12; TP13; buck-side pads (V) | | |
| 3 | current limit used (mA); current (mA); 0V9_BUCK; DDR_BUCK; 1V8_BUCK; TP2; hard-off time (s); R3 removed (y/n) | | |
| 4 | current limit used; TP4; TP15; TP5; TP3; TP14; 3V3_BUCK; TP2; current (mA) | | |
| 5 | all TPs (attach testpoints.md table); TP6 frequency; current (mA); TP30 with/without card | | |
| 6 | 2207:110c seen (y/n) | | |
| 8 | boot log saved; Linux idle current (mA); rails under Linux | | |
| 9 | clean shutdown (y/n); hard-off time (s); plug-in stays off (y/n) | | |
| 10 | link speed; DHCP; ping; SSH | | |
| 11 | TP17 at 0.5 A; TP13 at 0.5 A; device enumerates | | |
| 12 | NAND seen; NAND boot | | |
| 14 | full-load current (A); temperatures U4/SoC/Q_PWR/F1 | | |
