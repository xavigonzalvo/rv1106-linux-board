# Power architecture (Phase 3, Rev A)

Status: Executor, **round 3**, 2026-10-28. Companion files:
`power_rails.csv` (machine-readable rail table) and `tools/check_power.py` (gate self-check, run with
`design/.venv/bin/python -I design/tools/check_power.py design` → round 3: 70 pass, 0 fail, 4 `REQ`; **after the Phase-4
part selection (2026-10-29, §8): 76 pass, 0 fail, 0 `REQ`** — every rating is now a cited part rating); **after D-68 (series-link
terms P3L, no 0R chip on VDD_0V9/VDD_ARM): 84 pass, 0 fail, 0 `REQ`**, VDD_ARM low edge 0.873 V incl. 3 mV of copper links.
Builds on `architecture.md` (blocks `usbc`, `prot`, `onoff`, `pmu`), `pinmap.csv` and decisions D-01..D-31. Phase-3 decisions:
**D-32..D-50** (round 3: D-06, D-32, D-33, D-34, D-41, D-42 amended; D-47..D-50 new).

Round-3 changes in one line each (verifier round-2 findings → fix):
1. **Output capacitance is now budgeted per rail as a total**: buck-local + every SoC/peripheral decoupling capacitor Phase 5 will
   copy from [LF] on that rail (sub-rails through R32, 1 Ω and ferrites included). U4's local capacitor drops from 2×22 µF to
   **10 µF + 100 nF**, so VDD_0V9 + VDD_ARM total 43.6 µF ≈ TI's 2×22 µF cell; the [LF] SoC-side set is kept unchanged (§2, P10, D-47).
2. architecture.md §3 R41 paragraph rewritten: R41 1 kΩ is fed from **VCC_1V8**, C65 = 150 nF (D-34 r2).
3. **R32 0 Ω is FITTED** — deviation from the [LF] "0R 5% DNP" marking; without it CPU_DVDD (pin 115) is unpowered (§1, §2, D-06).
   **Phase 4 (D-68) supersedes the part:** [LF] R32 is a direct copper connection / net-tie **NT_ARM** (no 0R chip), and U4's
   measurement link is a normally-closed solder jumper **JP_MEAS_0V9**; the 0R chips (< 50 mΩ, 1 A) stay only on VCC_1V8/3V3/DDR (P3L).
4. R14 = 200 kΩ is kept on purpose instead of the [LF] hand note "200K->100K"; 100 kΩ fails P7a (D-34).
5. Bleeders on **all four** buck outputs (VDD_0V9 1 kΩ, VCC_DDR 1 kΩ, VCC_1V8 680 Ω, VCC_3V3 680 Ω) and P11 now proves every rail ≤ 0.4 V at
   the earliest restart (§3, D-42).
6. Q_PWR turn-off recomputed with I_G = |Vpl|/R_GS (5–20 µA): linear region ≤ 7.1 ms, ≤ 21 mJ, peak 7.8 W, checked against the
   [AO] Fig. 9 SOA (§6.3, P9e, D-41).
7. P8 includes the ±20 % PDT current corner: hard-off at 2.66–**7.02 s** (§6.2, D-33). **Superseded by D-117 c (L5F, owner D-H6): C_PDT = 2.2 µF X5R, hard-off at 8.07–22.4 s (never before 8 s).**
8. VBUS_USBA row corrected: port 4.44–5.20 V, can be below the USB 2.0 4.75 V host minimum (§2, D-49).
9. TP8 split into TP8a (EN̅ / controller output), TP8b (VCC5V0_SYS), TP8c (PWR_EN) (§6.5, D-50).

Round-2 changes (history; items 1 and 7 are superseded by round-3 items 1 and 7 above):
1. Buck output filters now are TI Table 4 "checked" cells (U4 2.2 µH + 2×22 µF, U7/U5 2.2 µH + 22 µF, U6 2.2 µH + 10 µF), 6.8 pF feed-forward on all four (§2, P10).
2. Q_PWR gate network re-designed so a cable plug-in cannot turn it on (C_GS 470 nF ≥ 47 × C_GD 10 nF) (§6.1, §6.3, P9).
3. Sequencing no longer depends on the EN threshold being "typical": U6 (3.3 V) is enabled from **VCC_1V8**, and every check uses the guaranteed 0.4–1.2 V window with independent corners per chip (§3, P7).
4. VCC_3V3 divider 442 k/100 k → 3.252 V nominal, 3.135–3.372 V band (§2, P3).
5. [LF] citations corrected (U6 output caps, nPOR RC location, "Power Reset" block); reset button Key1/R22 kept (D-44).
6. SD switch and other uncited ratings are now Phase-4 requirements, not passes (P5 `REQ`).
7. C_PDT 0.68 µF with X7R temperature drift included: hard-off at 2.66–6.60 s (§6.2, P8).
8. LTC2954 stock risk: §6 is written so the controller can be swapped (D-46).

## 0. Sources

| Tag | Document | URL | Local copy | Used for |
|---|---|---|---|---|
| [DS] | Rockchip RV1106 Datasheet Rev 1.8 | https://atta.szlcsc.com/upload/public/pdf/source/20250728/0F25565987B346BAFAE15AD3F3BED3E9.pdf | `refs/rv1106-datasheet-r1.8/` | Supply pins Table 2-1 pp.18–19; abs-max Table 3-1 p.20; operating ranges Table 3-2 p.20; codec standby current Table 3-11 p.24; θJA Table 4-1 p.25. **[DS] r1.8 contains no power-up/down sequence and no per-rail current figures** (full-text search of all 25 pages). |
| [LF] | Luckfox Pico Pro/Max schematic (one A4 sheet) | https://github.com/LuckfoxTECH/Luckfox-Pico-docs/blob/main/Hardware/Schematic/Luckfox-Pico-Pro-Max.pdf | `refs/luckfox-pico-pro-max-sch/` | Regulator circuits read from the rendered sheet: zone 1 top "VCC5V0_SYS--->VDD_0V9 / Setp 1" (U4, L2, R33/R37, R35, C57, R32); zone 2 top (U5, L1, R34/R38, R36, C58); zone 3 top (U7, L4, R13/R17, R14, C77, FB4); zone 3–4 bottom (U6, L3, R40/R44, R42, R43, C65, R41, PWR_EN, output **C63 10 µF + C64 100 nF, feed-forward C62 10 pF**); "Type-C" (R3/R6, R2/R5, D1, C4); **"Power Reset" block = Key1 + R22 100R + ED1 (not fitted)**; **nPOR pull-up R12 1K to VCC_3V3 and C38 10nF sit beside the SoC symbol in PART A** (not in the "Power Reset" block); "RTC Power" (D2/D3, R11); FB1/FB2/FB3, R8, R31. **The regulator IC part numbers are not printed on the sheet.** Hand notes "200K->100K" (by R14, U5/U7 enable) and "100K->200K" (by R43, U6 enable). **R32 (VDD_0V9 → VDD_ARM) is printed "0R 5% DNP"** (zone 1 top, next to C52/C53). SoC-side decoupling, bottom strip "For ARM / For DDR / For LOGIC/NPU/VEPU / For AVDD18_DDR" and PART A/B/C (read from a 600-dpi render): VDD_ARM C15 10u, C16 1u, C17 100n; VCC_DDR C18 10u, C19 10u, C20 1u, C21 100n; VDD_0V9 C22 10u, C23 10u, C24 1u, C25 1u, C26–C28 100n, C36 100n (pin 67); VCC_1V8 C11 1u + C12 100n, C32 100n (70), C31 100n (96 via FB3), C13 10u + C14 100n (codec via FB2), C10 100n (24 via R8), C45 100n (1 via R31), C46 4.7u + C47 100n and C48 1u (VCC_DDR side) at the FB4 block; VCC_3V3 C37/C39/C40/C41/C9 100n, C8 100n (FB1), C42 10u + C43 100n (SPI NAND), C69 100n, VCC3V3_SD C70 100n + C71 10u + C72 100n. |
| [TLV] | TI TLV62569 datasheet SLVSDG1C (Oct 2017) | https://www.ti.com/lit/ds/symlink/tlv62569.pdf | `refs/tlv62569-datasheet/tlv62569_SLVSDG1C.pdf` | p.9 Table 4 notes: "effective inductance can vary by +20% and -30%", "effective capacitance can vary by +20% and -50%", "Checked cells represent combinations that are proven for stability by simulation and lab test"; p.3 pinout, "EN … Do not leave floating"; p.4 abs-max (VIN 6 V), recommended IOUT 2 A, θJA, UVLO 2.3/2.45 V + 100 mV hysteresis, **EN VIH typ 0.95 / max 1.2 V, VIL min 0.4 / typ 0.85 V**, tSS 800 µs (DBV) / 900 µs (DDC, DRL) — no min/max given, VFB 0.588/0.6/0.612 V (TJ = 25 °C); p.5 ILIM 3 A; p.7 §7.4.1 enable, PG for sequencing (TLV62569P only); p.9 §8.2.2.2 Eq.2, "R2 max 200 kΩ", "6.8 pF for R2 = 100 kΩ"; **p.9 §8.2.2.3 Table 4** L/C matrix; p.10 §8.2.2.4 Isat 20–30 % above IL,MAX, §8.2.2.5 "4.7 µF input capacitance is sufficient". |
| [LTC] | ADI/Linear LTC2954 datasheet, rev "2954fb" | official: https://www.analog.com/media/en/technical-documentation/data-sheets/2954fd.pdf (timed out on fetch); copy used: https://cdn.components.ru/media/PDF/1445781.pdf | `refs/ltc2954-datasheet/LTC2954_mirror.pdf` | p.1 typical application ("1 µF → 6.4 s"); p.2 abs-max, TSOT-23-8 pinout (VIN 1, PB 2, ONT 3, GND 4, INT 5, EN/EN̅ 6, PDT 7, KILL 8); p.3 electrical table (VUVL, tDB,ON 26–41 ms, IPDT(PU) 2.4/3/3.6 µA, tEN,LOCKOUT 200–325 ms, IEN(LKG) ±1 µA, VOL, tPDT at 1500 pF 9/11.5/13.5 ms, KILL blanking 400–650 ms); p.4 Notes 3–5; p.9 "When power is first applied … the part initializes the output pins … converters … held off", CPDT equation; p.9–12 operation. |
| [AO] | AOS AO3401A datasheet Rev 3.1 (Dec 2023) | https://www.aosmd.com/res/datasheets/AO3401A.pdf | `refs/ao3401a-datasheet/AO3401A.pdf` | p.1 VDS −30 V, ID −3.2 A (70 °C), VGS ±12 V, RDS(on) < 60 mΩ at −4.5 V, < 85 mΩ at −2.5 V; p.2 VGS(th) −0.5/−0.9/−1.3 V, IGSS ±100 nA, Ciss 645 pF, Crss 55 pF (VDS −15 V), gFS 17 S; **p.4 Fig. 9 SOA** (TA 25 °C, single pulse; 10 ms line ≈ 12 A at 1.1 V → ≈ 0.45 A at 30 V, i.e. ≈ 13 W) and Fig. 10 single-pulse power (≈ 13 W at 10 ms) — values read from the plots, ESTIMATE. |
| [LCSC-LTC] | LCSC product page LTC2954CTS8-2#TRPBF | https://www.lcsc.com/product-detail/C683783.html | — | Part exists as C683783 (TSOT-23-8). **Stock and price not shown** → Phase 4 gating item (D-46). |

Everything not covered by these is marked **UNVERIFIED** or **ESTIMATE**.

## 1. Power tree

```
USB-C J1 VBUS_IN ── F1 PPTC BSMD1812-300 (3 A hold @25 °C, 2.01 A @60 °C; D-56) ──┬── D_TVS (5 V standoff, uni) ── GND
  CC1 ─ 5.1k ─ GND  (R3, copy [LF])    ├── C 2.2 µF (copy [LF] C4) + 100 nF          ← ≤ 10 µF before the switch
  CC2 ─ 5.1k ─ GND  (R6, copy [LF])    │
                                        VBUS_5V [TP1] (present whenever a cable is plugged in)
                                        ├── U_ONOFF LTC2954-1 VIN  ── PB ← SW_PWR to GND   (Phase 4: -1 + Q_EN, §6.4a, D-51)
                                        │        EN (pin 6, R_ENPU 100k to VBUS_5V) → Q_EN 2N7002 → drain ─ R_G 47k ─ Q_PWR gate    INT → PB_INT_N (pin 60)
                                        │        KILL ← Q_KILL inverter ← PWR_KILL (pin 63)
                                        └── Q_PWR AO3401A (S = VBUS_5V, D = VCC5V0_SYS); R_GS 100k + C_GS 470n G–S, C_GD 10n G–D
                                                 │
VCC5V0_SYS [TP8b] ─┬── R_BL5 470 Ω to GND (discharge, D-42)
 (switched)        ├── U4 TLV62569 ─ 2.2 µH ─ 10 µF ─ VDD_0V9 0.90 V [TP4] ─ JP_MEAS_0V9 ─┬─ DVDD_1..7, PMU_DVDD0V9, OSC_PLL_DVDD (+[LF] C22–C28, C36)
                   │     EN ← R35 10k from VCC5V0_SYS ([LF])  R_BL09 1 kΩ      └─ NT_ARM copper (≠ [LF] R32 DNP; D-68) ─ VDD_ARM ─ CPU_DVDD (+C15–C17)
                   ├── U7 TLV62569 ─ 2.2 µH ─ 22 µF ─ VCC_DDR 1.35 V [TP5] ─── DDR_VDDQ_1..3 (+[LF] C18–C21, C48); R_BL135 1 kΩ
                   ├── U5 TLV62569 ─ 2.2 µH ─ 22 µF ─ VCC_1V8 1.80 V [TP3] ─┬─ DDR_PLL_AVDD1V8, OSC/PLL_AVDD1V8, RECOVERY pull-up
                   │     U5+U7 EN = VCC_DDR_1V8_EN: R14 200k / C77 100n from VCC5V0_SYS ([LF])
                   │                                                         ├─ R_BL18 680 Ω to GND (discharge, D-42)
                   │                                                         ├─ R41 1k → PWR_EN [TP8c] → R43 200k → U6 EN, C65 150n (D-34 r2)
                   │                                                         ├─ R31 1 Ω ─ MIPI_CSI_AVDD_1V8 (pin 1)
                   │                                                         ├─ R8 1 Ω ─ AVDD1V8_USB (pin 24)
                   │                                                         ├─ FB2 ─ VCC1V8_CODEC (pin 31)
                   │                                                         └─ FB3 ─ ETH_AVDD1V8 (pin 96)
                   ├── U6 TLV62569 ─ 2.2 µH ─ 10 µF ─ VCC_3V3 3.25 V [TP2] ─┬─ GPIO1/3/4/5/6, PMU_VCC3V3, USB_AVDD3V3
                   │     EN from VCC_1V8 (above), not from VCC5V0_SYS         ├─ R_BL33 680 Ω to GND (discharge, D-42)
                   │                                                         ├─ FB1 ─ FEPHY_AVDD3V3 (pin 101)
                   │                                                         ├─ D3 B5819WS ─ VCC3V3_RTC ─ R11 100 Ω ─ RTC_AVDD3V3 (19)
                   │                                                         ├─ Q_SD SI2301 (SDMMC_PWREN) ─ VCC3V3_SD ─ microSD
                   │                                                         ├─ SPI NAND, USB mux, LEDs, I²C pull-ups, KILL pull-up
                   │                                                         ├─ nPOR: R12 1k pull-up + C38 100n (PART A; 10n in [LF], 100 nF here, D-117 c), Key1 via R22 100R
                   │                                                         └─ header 3V3 pins (≤ 150 mA allowance)
                   ├── U_USBA SY6280AAC (USBA_VBUS_EN; VIN 10 µF, D-57) ─ VBUS_USBA (22 µF + 120 µF polymer, D-58) ─ USB-A
                   ├── R2 10k / R5 18k ─ USB_DET_IN ─ pin 25 USB_VBUSDET (D-27, D-40)
                   └── header 5 V pins (output only, D-08)
```

## 2. Rail table

Full data with per-pin mapping, L/C values and feed-forward: `power_rails.csv`. Worst-case currents are **ESTIMATES** because
[DS] r1.8 publishes no rail currents (§5). Ratings ≥ 1.3 × worst case (gate clause 2, check P5) — only **cited** ratings count;
parts not yet chosen carry a Phase-4 **requirement** (P5 `REQ`).

| Rail | V nom | Set-point band (Vref ±2 %, 1 % R) | [DS] T3-2 range | Regulator / device | Rating | Worst-case I | Rating / worst | Source of circuit |
|---|---|---|---|---|---|---|---|---|
| VBUS_IN → VBUS_5V | 5.0 | source: 4.75–5.25 | — | J1 HRO TYPE-C-31-M-12, F1 BSMD1812-300-16V | J1 5 A (HRO note 4-1); F1 hold **2.01 A at 60 °C**, 1.61 A at 70 °C (BHFUSE p.5 derating chart) | 1.41 A | J1 3.5×; F1 1.43× at 60 °C, 1.14× at 70 °C | D-04, D-37, D-54, D-56 |
| VCC5V0_SYS | 5.0 | VBUS − ≤ 0.26 V | — | Q_PWR AO3401A | 3.2 A at 70 °C [AO] p.1 | 1.41 A | 2.3× | D-03, D-33, D-41 |
| VDD_0V9 (+VDD_ARM) | 0.90 | 0.876–0.924 V | DVDD 0.81–0.95; CPU 0.85–1.05 | U4 TLV62569, 49.9k/100k, **2.2 µH + 22 µF local** (55.7 µF total with SoC side; D-117 c, was 10 µF) | 2 A [TLV] p.4 | 1.001 A | 2.0× | [LF] U4 topology; D-32, D-35 |
| VCC_DDR | 1.35 | 1.320–1.405 V | 1.283–1.45 | U7 TLV62569, 127k/100k ([LF] R13/R17), **2.2 µH + 22 µF** | 2 A | 0.352 A | 5.7× | [LF] U7; D-07, D-32 |
| VCC_1V8 | 1.80 | 1.741–1.861 V | 1.62–1.98 | U5 TLV62569, 200k/100k ([LF] R34/R38), **2.2 µH + 22 µF** | 2 A | 0.203 A | 9.9× | [LF] U5; D-32 |
| VCC_3V3 | 3.25 | **3.135–3.372 V** | 3.0–3.465 (ETH 2.97–3.63) | U6 TLV62569, **442k/100k**, 2.2 µH + 10 µF | 2 A | 0.550 A | 3.6× | [LF] U6 (C63 10 µF + C64 100 nF); D-43 |
| VCC3V3_SD | 3.25 | = VCC_3V3 | — | Q_SD SI2301CDS ([LF] Q1) | 1.8 A at 70 °C (Vishay 68741 p.1) | 0.20 A | 9× | [LF] "Card Power"; D-45, D-54 |
| VBUS_USBA | 5.0 | **4.44–5.20 V at the port** (VBUS 4.75–5.25 V − ≤ 0.26 V input drop − ≤ 0.05 V switch drop at 0.5 A); 4.69 V from a 5.00 V charger | USB 2.0 host port 4.75–5.25 V (USB 2.0 spec §7.2.1 — not downloaded, UNVERIFIED) | U_USBA SY6280AAC, RSET 6.8k | ILIM min 0.75 A (AN_SY6280 p.3); RDS(on) 80 mΩ typ (no max: UNVERIFIED) | 0.50 A | 1.5× | D-05, D-49, D-54 |
| VCC3V3_RTC | ~3.0 | 3.25 V − Schottky Vf | RTC 1.6–3.6 | D3 B5819WS + R11 100 Ω | — (µA load) | µA | — | [LF] "RTC Power" |
| sub-rails | | | | R31/R8 1 Ω, FB1/FB2/FB3 ferrites copied from [LF]; [LF] R32 → **direct copper / net-tie NT_ARM** (D-68; deviation: [LF] prints "0R 5% DNP"; no 0R chip in the core path) | — | ≤ 0.5 A (VDD_ARM), ≤ 0.06 A others | — | [LF]; D-06 |

**VBUS_USBA note (D-49).** The USB-A port can sit below the USB 2.0 host minimum of 4.75 V when the source itself is at its 4.75 V
minimum (worst case 4.44 V). Most bus-powered devices work down to the 4.4 V that USB 2.0 allows at the far end of a bus-powered hub,
but this is not guaranteed for every device. Mitigations for Phase 4: U_USBA RDS(on) ≤ 100 mΩ, F1 R1max ≤ 0.10 Ω (already D-37).
Measured at bring-up (TP1 vs USB-A VBUS at 0.5 A).

**Every SoC supply pin has a rail** (gate clause 1; checks P1/P2): the 28 non-ground supply pins in `pinmap.csv` (status POWER) map to
VDD_0V9 (10, 51, 54, 55, 67, 71, 82, 103, 116), VDD_ARM (115), VCC_DDR (49, 50, 56), VCC_1V8 (53, 70), MIPI_CSI_AVDD_1V8 (1),
AVDD1V8_USB (24), VCC1V8_CODEC (31), ETH_AVDD1V8 (96), VCC_3V3 (13, 28, 43, 61, 81, 88, 108), FEPHY_AVDD3V3 (101), VCC3V3_RTC (19).
Ground: E-PAD, CODEC_AVSS (37, 0 Ω), TVSS (57) → GND. Unused analog domains (MIPI, codec) are still powered (D-12, D-26).

**Regulator details (D-32, corrected round 3).** All four bucks are **TLV62569** (2 A, VIN 2.5–5.5 V, VFB 0.6 V ±2 %, 1.5 MHz,
internal soft start; [TLV] pp.1/4/5). The [LF] sheet does not print its regulator part numbers, so "copy [LF]" is done at circuit
level: same topology, same rail split, same enable structure, same DDR and 1V8 dividers. **The output filters are sized against TI's
checked combinations in [TLV] Table 4 (p.9)**, because [LF]'s inductors (1.0 µH on L1/L2/L4) belong to an unknown IC and our inductors
are 2.2 µH.

**Total output-capacitance budget (round 3, D-47).** The regulator loop sees every capacitor on its rail, not only the ones next to it:
the SoC decoupling, the sub-rails behind NT_ARM ([LF] R32, copper), R8/R31 (1 Ω) and the ferrites FB1–FB3 (≪ 1 Ω at the 10–100 kHz loop crossover,
so counted in full — pessimistic for the upper bound). Phase 5 copies the [LF] SoC-side set unchanged (values in §0 [LF]); the local
buck capacitor is chosen so the total sits in a checked cell. TI states (Table 4 notes, p.9) that effective capacitance may vary
**+20 % / −50 %** around a checked cell, so a checked cell C covers effective 0.5·C … 1.2·C; check P10 requires the rail's whole
effective range — min = nominal × 0.9 (tolerance) × DC-bias retention, max = nominal × 1.1 — to lie inside the union of the checked
cells of every Table 4 row its band touches.

| Buck | Table 4 row(s), L 2.2 µH | Local (next to IC) | SoC / peripheral side ([LF] copy) | Total nominal | Effective (P10) | Covered by checked cell(s) |
|---|---|---|---|---|---|---|
| U4 VDD_0V9 (+VDD_ARM via NT_ARM, [LF] R32) | 0.6–1.2 V: only 2×22 µF → 22–52.8 µF | **10 µF** + 100 nF ([LF] had C52 22 µF + C1 4.7 µF) | 22.4 µF (C22–C28, C36) + 11.1 µF (C15–C17) = 33.5 µF | **43.6 µF** | 27.5–48.0 µF (retention 0.7) | 2×22 ✓ |
| U7 VCC_DDR | 1.2–1.8 V: 22, 2×22 → 11–52.8 µF | **22 µF** + 100 nF | 21.1 µF (C18–C21) + 1 µF (C48) = 22.1 µF | **44.2 µF** | 27.8–48.6 µF | 2×22 ✓ |
| U5 VCC_1V8 (band 1.741–1.861 V straddles 1.8 V) | 1.2–1.8 and ≥ 1.8: 22, 2×22 (10 also in ≥ 1.8) | **22 µF** + 100 nF | 16.5 µF (C11/C12, C32, C31, C13/C14, C10, C45, C46/C47) | **38.6 µF** | 24.3–42.5 µF | 2×22 ✓ in both rows |
| U6 VCC_3V3 | ≥ 1.8 V: 10, 22, 2×22 → 5–52.8 µF (overlapping) | **10 µF** + 100 nF (= [LF] C63/C64) | 11.2 µF always (C37, C39, C40, C41, C9, C8, C42/C43, C69, + 3 × 100 nF Phase-5 additions: pins 88/108, USB mux) + 10.2 µF VCC3V3_SD when Q_SD is on + **≤ 10 µF external on the header 3V3 pins (board rule, D-48)** | **21.3–41.5 µF** | 9.6–45.7 µF (retention 0.5) | 10/22/2×22 union ✓ |

Not counted: VCC3V3_RTC C35 1 µF (behind the D3 Schottky and R11 100 Ω), RECOVERY C44 (behind 10 kΩ), nPOR C38 100 nF (behind R12 1 kΩ; D-117 c).
**Phase 5 update (2026-10-29, D-72):** the schematic netlist recount gives VDD_0V9 SoC side **33.6 µF** (+100 nF on pin 71 OSC_PLL_DVDD, total 43.7 µF), VCC_1V8 **16.4 µF** (the 16.5 above was a summing slip; total 38.5 µF) and VCC_3V3 **11.1 µF** always-on (11.2 was a slip; total 21.2–41.4 µF). power_rails.csv carries these values; check_power P10 still passes (84 pass, 0 fail) and design/schematic/check_schematic.py S6 checks that the netlist matches power_rails.csv.

**DC-bias retention** (0.7 at ≤ 1.8 V, 0.5 at 3.3 V) is an ESTIMATE for X5R/X7R 0402–0805 MLCCs; Phase 4 must pick parts whose vendor
DC-bias curve keeps at least that fraction (otherwise re-run P10). Phase 5 must not add capacitance beyond this budget on these four rails
without re-running P10 (e.g. adding a 22 µF "for good measure" to VDD_0V9 would push it outside the checked range: a mutation with
2×22 µF local gives 77.6 µF and fails P10). Phase 7: VDD_0V9 copper from U4 to the SoC must be short and wide, since half the rail's
capacitance now sits at the SoC.

The 100 nF parts next to each IC are high-frequency decoupling and are counted in the totals. Inductors: 2.2 µH, Isat ≥ 3.6 A (≥ 1.2 × ILIM 3 A,
[TLV] §8.2.2.4). Inputs: 10 µF + 100 nF each ([TLV] §8.2.2.5: 4.7 µF is sufficient; [LF] fits 4.7–10 µF).
**Feed-forward:** every divider has R2 (bottom) = 100 kΩ, so all four get **6.8 pF** across R1, exactly TI's recommendation
([TLV] p.9 §8.2.2.2). This is why the VCC_3V3 divider is 442 kΩ / 100 kΩ (D-43) rather than 44.2 k / 10 k: same ratio (3.252 V),
but it uses the TI-recommended feed-forward value instead of an untuned one, and R2 stays within TI's 200 kΩ maximum.
VCC_3V3 band 3.135–3.372 V leaves 93 mV below the 3.465 V IO maximum ([DS] Table 3-2) for ripple and the VFB drift outside
TJ = 25 °C (VFB is only specified at 25 °C, [TLV] p.4); [LF]'s own 3.3 V rail runs at 0.8 × (1 + 40.2/13) ≈ 3.27 V.
Thermal: worst loss is U4, P = 0.9 × 1.0 × (1/0.78 − 1) ≈ 0.25 W; with the DBV θJA 188 °C/W ([TLV] p.4) → +48 °C. Phase 4 should
prefer the DDC/DRL packages (106/146 °C/W) or Phase 7 should give U4 a copper pour.

## 3. Sequencing

**What the datasheet requires:** [DS] r1.8 states **no** power-up or power-down order (§0). The RV1106 Hardware Design Guide was not
found (UNVERIFIED). Rules used: (1) [LF]'s order — core first ("Setp 1"), then 1.8 V + DDR, then 3.3 V (the [LF] hand notes
"200K->100K" by R14 and "100K->200K" by R43 show Luckfox deliberately moving 1.8 V/DDR earlier and 3.3 V later); (2) never exceed
the [DS] Table 3-1 absolute maximum; (3) release nPOR only after every rail is in range.

**Mechanism (D-34, round 2).** Each rail's enable is driven by the previous stage, so the order does not rely on two RC delays racing:

| Step | Event | Mechanism | Guaranteed time (from start of VCC5V0_SYS ramp; check P7, all corners) |
|---|---|---|---|
| 0 | Button press → EN̅ low → Q_PWR on | LTC2954 tDB,ON 26–41 ms; gate delay ≤ 9.8 ms; VCC5V0_SYS ramps 0.45–1.96 ms (§6.3) | t = 0 |
| 1 | **VDD_0V9 / VDD_ARM** | U4 EN = VCC5V0_SYS via R35 10k ([LF]); U4 starts at its UVLO (≤ 2.6 V on the ramp), tSS ≤ 0.9 ms | good by **≤ 0.91–1.87 ms** |
| 2 | **VCC_DDR and VCC_1V8** | U5 + U7 EN = R14 200 kΩ / C77 100 nF from VCC5V0_SYS ([LF] printed values; R36/C58 not fitted). **R14 stays 200 kΩ on purpose**, not the [LF] hand note "200K->100K": with 100 kΩ, U5/U7 can enable at 0.72 ms, before U4 is good at 0.91 ms (P7a fails in all six corners, mutation run) | EN **≥ 1.44–2.48 ms** (EN 0.4 V, C77 −10 %) → U4 already good, margin ≥ 0.53 ms |
| 3 | **VCC_3V3** | U6 EN = **VCC_1V8** → R41 1 kΩ → PWR_EN → R43 200 kΩ / **C65 150 nF** to GND | EN ≥ **1.2 ms after** both VCC_1V8 *and* VCC_DDR are good (worst corner below); good by ≤ 47.4 ms |
| 4 | nPOR high | R12 1 kΩ pull-up to VCC_3V3 + C38 100 nF ([LF] PART A has 10 nF; 100 nF since D-117 c), τ = 100 µs → follows VCC_3V3, the last rail | after step 3 |
| 5 | LTC2954 samples KILL | blanking tKILL,ON 400–650 ms ([LTC] p.3) | KILL pull-up (VCC_3V3) valid by ≤ 57 ms incl. gate delay → ≥ 343 ms margin |

How P7 is computed (`check_power.py`): Euler simulation of the RC networks fed by a linear VCC5V0_SYS ramp (fast 0.45 ms, slow 1.96 ms,
and an instant 20 µs step) at VIN 4.75 and 5.25 V. **Each TLV62569 is a separate chip, so U5, U7 and U6 each get their own EN
threshold anywhere in the guaranteed window 0.4–1.2 V ([TLV] p.4: VIL min 0.4 V, VIH max 1.2 V) and their own UVLO (2.2–2.6 V);
C77 and C65 are taken at ±10 %.** All combinations are checked:
- P7a: latest U4-good (UVLO 2.6 V + 0.9 ms) < earliest U5/U7 enable (0.4 V threshold, C77 −10 %). Worst margin 0.53 ms (5.25 V, fast ramp).
- P7b: the worst case is U5 enabling at 0.4 V while U7 (same C77) only enables at 1.2 V, and U6 at 0.4 V with VCC_1V8 treated as an
  instant step to its 1.861 V maximum and C65 −10 %. U6 still enables ≥ **1.2 ms** after both VCC_1V8 and VCC_DDR are good. With
  [LF]'s C65 = 100 nF this margin would be negative (U6 could start before VCC_DDR is up), which is why C65 is 150 nF.
- P7c: latest U6-good (1.2 V thresholds, VCC_1V8 at its 1.741 V minimum ramping over tSS, C65 +10 %) plus the 9.8 ms gate delay is
  ≤ 57 ms, far below the 400 ms KILL blanking.
- P7d: VCC_1V8 (≥ 1.741 V) settles U6 EN above VIH max 1.2 V even with up to 2.7 µA EN input current through 201 kΩ ([TLV] gives
  no EN input current; "do not leave floating", p.3 → UNVERIFIED, bring-up check of PWR_EN at TP).
- Residual assumption: tSS ≤ 0.9 ms. [TLV] gives only 800/900 µs without a max (UNVERIFIED); P7a/P7b keep ≥ 0.53/1.2 ms in hand,
  i.e. they hold for soft-start times up to ≈ 1.4 ms/2.1 ms.

U6 EN is fed from a regulated 1.74–1.86 V rail: above VIH max 1.2 V and far below the 6 V EN abs-max ([TLV] p.4). If VCC_1V8 fails
(short, dead U5), VCC_3V3 never starts, KILL stays low and the LTC2954 aborts the power-on after the blanking time (§6.1).

**Restart after the shortest off time (check P11, D-42 round 3).** The bucks have no output discharge, and the EN capacitors discharge
only through their source rail. The LTC2954 ignores the button for tEN,LOCKOUT ≥ 200 ms and then needs tDB,ON ≥ 26 ms, so a new
power-on can start 226 ms after EN̅ releases ([LTC] p.3, Note 5). Bleeders: **R_BL5 470 Ω** on VCC5V0_SYS, **R_BL09 1 kΩ** on VDD_0V9,
**R_BL135 1 kΩ** on VCC_DDR, **R_BL18 680 Ω** on VCC_1V8 (was 1 kΩ: the larger VCC_1V8 capacitance of the round-3 budget needs it to
empty C65 in time) and **R_BL33 680 Ω** on VCC_3V3. Pessimistic model: VCC5V0_SYS held at 5.25 V until Q_PWR is fully off (≤ 104 ms);
every buck output held at its band maximum until VCC5V0_SYS falls below 2.1 V (≈ 123 ms), then an RC decay into its bleeder with the
rail's **maximum** total capacitance + 10 % (§2 budget; SoC load current ignored, it only helps). At the earliest restart:

| Node | Voltage at 226 ms (P11) |
|---|---|
| VCC5V0_SYS | ≤ 0.03 V |
| C77 (U5/U7 EN) | ≤ 0.15 V |
| C65 (U6 EN) | ≤ 0.31 V |
| VDD_0V9 | ≤ 0.11 V |
| VCC_DDR | ≤ 0.18 V |
| VCC_1V8 | ≤ 0.06 V |
| VCC_3V3 (incl. SD, header allowance, PWR LED off) | ≤ 0.13 V |

All are ≤ 0.4 V: the enables are below VIL min 0.4 V, and every rail is below a silicon-junction forward voltage, so no domain can
back-feed another through IO or ESD diodes and the restart repeats the cold-start order. The 0.4 V rail criterion is a design rule ([DS]
states no discharge requirement). The power LED on VCC_3V3 is not relied on for discharge.

**Absolute-maximum check during the ramp:** the only cross-rail paths are the IO pins. No SoC output is driven before VCC_3V3 (it is
the IO supply), and no external pull-up goes to a rail that is up before its domain except: (a) the USB_VBUSDET divider on
VCC5V0_SYS (D-27) — pin 25 sees ≈ 3.2 V through 10 kΩ for up to ≈ 57 ms per power-on before USB_AVDD3V3 is up, limiting any
injection to < 0.33 mA (the pin's injection limit is UNVERIFIED in [DS]; D-40); (b) the PWR_EN and EN networks, which only touch
regulator pins.

**Power-down:** whatever the cause (KILL, hard-off, cable pulled), Q_PWR opens and VCC5V0_SYS decays under load. All four bucks lose
input together; VCC_3V3 falls out of regulation first (most headroom needed, [TLV] Eq.1 100 % duty), then the lower rails; all stop at
UVLO ([TLV] p.4). U6 is also disabled as VCC_1V8 falls. [DS] states no power-down requirement.

## 4. USB-C sink and input protection (`usbc`, `prot`)

| Item | Circuit | Basis |
|---|---|---|
| Sink role, no PD | CC1 and CC2 each 5.1 kΩ (Rd) to GND, separate resistors, 1 % | copy [LF] R3/R6 "5.1K"; PLAN R1 |
| VBUS pins | all four VBUS pins (A4/B9/A9/B4) tied → VBUS_IN; GND A1/B12/A12/B1 + shell to GND | [LF] "Type-C" pin list |
| Fuse F1 | **BSMD1812-300-16V** (C883162): Ihold 3.00 A / Itrip 6.0 A at 25 °C, Vmax 16 V, R1max 0.050 Ω (BHFUSE BSMD1812 Rev 2025 p.2). Derated hold (p.5 chart): 2.55 A at 40 °C, 2.28 A at 50 °C, **2.01 A at 60 °C**, 1.61 A at 70 °C | D-04/D-37/D-56; hold ≥ 1.3 × 1.41 A = 1.83 A up to **60 °C ambient**; ≥ 1.0× (no nuisance trip at worst-case load) up to 70 °C |
| TVS D_TVS | unidirectional, VRWM 5.0 V (SMBJ5.0A/SMF5.0A class), after F1, at the connector | D-04; part in Phase 4 |
| Bulk on VBUS_5V | 2.2 µF ([LF] C4) + 100 nF (LTC2954 VIN) — kept small; the regulator input capacitors sit after Q_PWR | USB Type-C sink bulk-capacitance limit (≤ 10 µF at attach) is the usual rule; spec clause UNVERIFIED |
| Reverse/back-feed | no series Schottky (D-10). Q_PWR's body diode points VCC5V0_SYS → VBUS_5V; nothing feeds VCC5V0_SYS (header 5 V is output only, D-08) | D-10, D-39 |
| ESD on data | low-capacitance array on USBC_DP/DM and USBA_DP/DM (IF-30) | D-04, Phase 4 |
| Current advertisement | Rd only, so the board cannot read the source's Rp. Full budget (1.41 A) needs a 1.5 A or 3 A source; a "Default USB power" source guarantees only 500/900 mA (D-36) | open question Q2 |

**Plug-in transient:** while the board is off, Q_PWR stays off through plug-in (§6.3), so hot-plug ringing on the 2.2 µF input reaches
only F1, the TVS and the LTC2954 (VIN abs-max 33 V, [LTC] p.2), not the 6 V-abs-max bucks.
**Residual risk (D-37):** a 5 V-standoff TVS clamps around 9 V at its peak pulse current, above the 6 V abs-max of the TLV62569. When
the board is on, Q_PWR passes such a surge to the bucks. [LF] has no TVS at all. Alternative for the human: an eFuse with over-voltage
cut-off instead of F1 (open question Q3).

**D-10 verification (D-39):** worst-case drop VBUS_IN → VCC5V0_SYS = 1.41 A × (0.10 Ω F1 + 0.085 Ω Q_PWR at |VGS| ≥ 2.5 V) ≈ 0.26 V.
From a 5.0 V charger VCC5V0_SYS stays ≥ 4.74 V. Accepted for Rev A; measured at bring-up (TP1 vs TP8).

## 5. Power budget (worst case)

Basis for the estimates (all UNVERIFIED — no [DS] figure exists): VDD_0V9 1.0 A = Cortex-A7 at 1.2 GHz + NPU + ISP/logic at
≈ 0.9 W. VCC_DDR 0.35 A for the in-package 2 Gb DDR3L + PHY. 3.3 V items itemised below. Efficiencies from the [TLV] 5 V-input
curves (p.1/p.10); 0.9 V is not plotted and 78 % is assumed. External-port allowances are a board rule (D-36).

| Load | Rail | Current | Power at 5 V input |
|---|---|---|---|
| CPU + logic + NPU + PMU core, R_BL09 1 kΩ 0.9 mA | VDD_0V9 | 1.001 A | 0.9 × 1.001 / 0.78 = **1.16 W** |
| DDR3L in package + DDR IO, R_BL135 1 kΩ 1.4 mA | VCC_DDR | 0.352 A | 1.35 × 0.352 / 0.85 = **0.56 W** |
| SoC 1.8 V analog (PLL, OSC, DDR-PLL, USB, ETH, OTP, TSADC, MIPI, codec), RECOVERY pull-up, R_BL18 680 Ω 2.7 mA, U6 EN network | VCC_1V8 | 0.203 A | 1.8 × 0.203 / 0.85 = **0.43 W** |
| VCC_3V3 total: SoC 3.3 V IO + PMU + USB 0.08 A; FEPHY 0.06 A; SPI NAND 0.04 A; microSD 0.20 A; header 3V3 allowance 0.15 A; LEDs 3 × 2 mA; I²C pull-ups 4.4 mA; PB_INT_N 0.7 mA; nPOR with Key1 pressed 3 mA; R_BL33 680 Ω 5 mA; mux, KILL pull-up, RTC < 1 mA | VCC_3V3 | 0.550 A | 3.3 × 0.550 / 0.90 = **2.02 W** (3.252 V nominal: slightly less) |
| USB-A VBUS + header 5 V pins, **combined** allowance | VCC5V0_SYS | 0.50 A | **2.50 W** |
| R_BL5 470 Ω bleeder 10.6 mA; USB_VBUSDET divider 0.18 mA; Q_PWR gate divider 0.03 mA; LTC2954 ≤ 12 µA | 5 V | 10.9 mA | **0.05 W** |
| Series losses F1 + Q_PWR at 1.41 A (0.10 + 0.085 Ω) | — | — | **0.37 W** |
| **Total** (computed by P6) | | **1.42 A** | **7.09 W < 7.5 W (5 V × 1.5 A)** ✓ (P6) |

Margin 0.41 W (5 %). The four buck-output bleeders added in round 3 cost ≈ 25 mW at the input. If bring-up shows VDD_0V9 higher than estimated, the first lever is the header/USB-A allowance (software can
keep USBA_VBUS_EN low). Phase 6 adds current measurement (0 Ω links on the VCC_1V8/3V3/DDR buck outputs, a normally-closed solder jumper JP_MEAS_0V9 on VDD_0V9; D-32, D-68).

## 6. On/off controller (`onoff`) — circuit and R4 behaviour

### 6.1 Circuit (D-33, D-41)

> **Superseded in part by §6.4a (Phase 4, D-51).** The fitted controller is **LTC2954CTS8-1**, whose pin 6 is an active-high EN.
> Pin 6 now drives Q_EN (2N7002), and **Q_EN's drain is the "EN̅" node** that this section and §6.2–6.4 refer to: wherever they say
> "EN̅" or "pin 6 EN̅", read "Q_EN drain (EN̅-equivalent node)". The diagram below is redrawn with Q_EN. The on/off behaviour,
> the R_G/R_GS/C_GS/C_GD network and the timing are unchanged.

```
VBUS_5V ─┬──────────────────────────────────────────── U_ONOFF pin 1 VIN  (+100 nF to GND)
         │                                             LTC2954CTS8-1 (pin 6 EN active-high open drain, [LTC] p.2/p.12)
         ├── R_ENPU 100k ──┬── pin 6 EN
         │                 └── Q_EN 2N7002 gate; source GND; drain = EN̅-equivalent node [TP8a]
         ├── Q_PWR AO3401A source ──── drain → VCC5V0_SYS (→ R_BL5 470 Ω, C_L ≤ 60.5 µF)
         │        gate ●
         ├─ R_GS 100k ─● ─ C_GS 470 nF X7R (gate–source)
         │             ● ─ C_GD 10 nF X7R (gate–drain, sets the turn-on dV/dt)
         │             ● ─ R_G 47k ── Q_EN drain (EN̅-equivalent; was "pin 6 EN̅" of the -2)
SW_PWR (tact, to GND) ── [R 5.1k DNP-0Ω] ── pin 2 PB  (+100 nF DNP; [LTC] p.12 suggests both if the switch is remote)
pin 3 ONT: open (tDB,ON 26–41 ms)          pin 7 PDT: C_PDT 2.2 µF X5R ±10 % to GND (D-117 c)
pin 5 INT (open drain) ── PB_INT_N ── 4.7k to VCC_3V3 ── SoC pin 60 GPIO0_A2_d (D-19)
pin 8 KILL ── R_KU 100k to VCC_3V3 ── drain of Q_KILL (logic-level N-FET, VGS(th) max ≤ 1.5 V, AO3400A class; Phase 4)
                                      Q_KILL gate ── PWR_KILL ── SoC pin 63 GPIO0_A4_d, + 100k to GND (D-20); source GND
pin 4 GND
```

**On state:** EN̅ sinks (VOL ≤ 0.4 V at 500 µA, [LTC] p.3). The gate settles at the R_GS/R_G divider:
|VGS| = (VBUS − VOL) × 100k/147k = **2.96–3.57 V** (VBUS 4.75–5.25 V). That is beyond VGS(th) max 1.3 V and at or above the −2.5 V
row where RDS(on) ≤ 85 mΩ ([AO] p.1), which the budget uses. EN̅ sinks ≤ 36 µA. VGS stays inside ±12 V.
**Off state:** EN̅ is high-Z (leakage ≤ ±1 µA, [LTC] p.3) and "initializes the output pins … held off" when power is first applied
([LTC] p.9). R_GS holds the gate at the source: |VGS| ≤ (1 µA + IGSS 0.1 µA) × 100 kΩ = 0.11 V < 0.5 V min threshold.

KILL side: KILL threshold 0.57–0.63 V, abs-max 7 V ([LTC] p.2/p.3). Inactive: Q_KILL off, KILL = VCC_3V3. Active: Q_KILL on, KILL ≈ 0 V.
PWR_KILL is active-high with the SoC reset pull-down and the 100k pull-down (D-03/D-20), so 0 V on the SoC side (unpowered, in reset,
BootROM, U-Boot) means "do not kill". The KILL pull-up goes to **VCC_3V3** (D-33): the LTC2954 only samples KILL after the 400–650 ms
blanking ([LTC] Note 3, p.4); VCC_3V3 is up by ≤ 57 ms (§3). If VCC_3V3 never starts (short, faulty U5 or U6), KILL stays low and the
controller switches the board back off after the blanking ("aborted power-on", [LTC] p.11).

### 6.2 R4 behaviour at circuit level

| R4 clause | What happens, signal by signal | Timing (source) |
|---|---|---|
| **Cable plugged in (board off)** | VBUS_5V rises; LTC2954 powers up with EN̅ released ([LTC] p.9); C_GS (470 nF) ≫ C_GD (10 nF) keeps Q_PWR's gate with its source, so |VGS| ≤ 0.25 V (≤ 0.38 V even with a 2× ringing overshoot to 10.5 V) — below the 0.5 V minimum threshold. Q_PWR stays off, VCC5V0_SYS stays at 0 V (R_BL5 holds the drain at ground), every buck stays off. Board waits for the button. | §6.3, P9 |
| **Short press turns on from off** | Press pulls PB below 0.6–1.0 V ([LTC] VPB(VTH) p.3). After tDB,ON EN̅ pulls low → gate charges through R_G (delay ≤ 9.8 ms) → C_GD Miller plateau ramps VCC5V0_SYS in 0.45–1.96 ms with ≤ 0.65 A inrush (Phase 4: C_L 60.5 µF) → §3 sequence → nPOR releases → BootROM. During the next 400–650 ms the controller ignores PB and KILL. | press ≥ 41 ms (tDB,ON 26–41 ms) |
| **Short press while on = clean Linux shutdown** | After PB is low for tDB,OFF, INT pulls PB_INT_N low (≥ 32 ms, then follows PB; [LTC] p.9/p.11). INT does **not** touch EN̅. Linux `gpio-keys` on GPIO0_A2 (active-low) reports KEY_POWER; systemd-logind (`HandlePowerKey=poweroff`) runs a normal shutdown (filesystems unmounted, SD/NAND synced). As its last step `gpio-poweroff` drives GPIO0_A4 = PWR_KILL high → Q_KILL pulls KILL below 0.57 V → EN̅ released within 30 µs ([LTC] tKILL(PD)) → R_GS turns Q_PWR off (≤ 104 ms worst case) → all rails fall. PB ignored for 200–325 ms. | INT after 26–41 ms; a "short press" is anything < 2.66 s |
| **Long press (≥ 8 s) = hard off** | If PB stays low past tPD,MIN + tPDT, the controller releases EN̅ itself, whatever the SoC is doing. CPDT = 1.56×10⁻⁴ µF/ms × (tPDT − 1 ms) ([LTC] p.9; consistent with "1 µF → 6.4 s" p.1). **C_PDT 0.68 µF → tPDT ≈ 4.36 s nominal.** Worst case: the larger of two timer-spread corners — the timing spec at 1500 pF (9/11.5/13.5 ms, p.3) applied proportionally, and the **PDT current 2.4/3/3.6 µA (±20 %, IPDT(PU) p.3), which dominates for a large C_PDT (slow corner 3/2.4 = 1.25×)** — times ±10 % capacitor tolerance **and ±15 % X7R drift over temperature**, plus tPD,MIN 52–82 ms and the 41 ms debounce: the hard-off point lies in **2.66–7.02 s**. Every hold of 8 s or more turns the board off (≈ 1.0 s margin); every press shorter than 2.66 s is only an interrupt. | hard-off at 2.66–7.02 s (nominal ≈ 4.4 s); P8 |
| **Long press, D-117 c (L5F, supersedes the 0.68 µF row above)** | Owner D-H6: R4 read as "the hard-off never happens before 8 s". **C_PDT = 2.2 µF X5R 16 V (C23630)**: tPDT nominal ≈ 14.1 s (+64 ms tPD,MIN ≈ 14.2 s). Same worst-case model (timer spread at 1500 pF, IPDT ±20 %, ±10 % tolerance, ±15 % X5R over temperature) plus an assumed ≤ 5 % DC-bias loss at VPDT ≤ 1.3 V (UNVERIFIED): hard-off at **8.07–22.4 s**. Every press shorter than 8.07 s is only an interrupt; a hard-off needs a hold of up to 22.4 s in the slowest corner. | hard-off at 8.07–22.4 s (nominal ≈ 14.2 s); P8 |
| Restart after off | PB ignored for tEN,LOCKOUT 200–325 ms after EN̅ releases; bleeders have emptied VCC5V0_SYS, all four buck rails and both EN capacitors (≤ 0.4 V) by then (§3, P11), so the next press repeats the cold-start order. | [LTC] p.3, Note 5 |
| Software reboot | `reboot` does not touch PWR_KILL; GPIO0_A4 returns to its reset pull-down, KILL stays high, power stays on. Key1 (reset button) pulls nPOR low through R22 100R: SoC reset, power stays on. | D-20, D-44 |
| Linux ignores the press | Nothing changes until the user holds the button into the hard-off window. | [LTC] p.9 "failsafe" |
| Cable unplugged / brown-out | VBUS_5V below LTC2954 UVLO 2.2–2.5 V resets the controller; the next plug-in leaves the board **off** (first row) until the button is pressed. | [LTC] p.3 VUVL |
| MASKROM | Hold RECOVERY, short-press POWER: board powers up and BootROM enters MASKROM; KILL stays inactive, board stays on. | D-23 |

Phase 8 needs: `gpio-keys` (GPIO0_A2, GPIO_ACTIVE_LOW, KEY_POWER), `gpio-poweroff` (GPIO0_A4, GPIO_ACTIVE_HIGH), logind
`HandlePowerKey=poweroff`, and never muxing GPIO0_A4 to pmic_sleep (D-20).

### 6.3 Q_PWR gate network: plug-in, inrush, turn-off (D-41; check P9)

Values: R_GS 100 kΩ, R_G 47 kΩ, C_GS 470 nF, C_GD 10 nF (both X7R ±10 %). AO3401A: Ciss 645 pF, Crss 55 pF at VDS −15 V ([AO] p.2);
Crss at VDS ≈ 0 is taken as ≤ 0.2 nF (UNVERIFIED bound, it rises at low VDS). Load on VCC5V0_SYS: 4 × 10 µF buck inputs + 4 × 100 nF +
**10 µF SY6280 VIN capacitor** (Phase 4, D-57; round 3 had ≈ 1 µF), +20 % → **C_L ≤ 60.5 µF** (round 3: 50 µF). The VBUS_USBA
capacitors (142 µF) sit behind the SY6280, which is off at power-up (USBA_VBUS_EN pull-down, D-20), so they are not in C_L.

**Plug-in (board off).** VBUS_5V steps or ramps from 0 to VBUS while the drain is held at 0 V by C_L and R_BL5. The gate is a
capacitive divider between source (C_GS + Ciss) and drain (C_GD + Crss) with R_GS pulling it back to the source:
- Step (worst case, any rise faster than τ = R_GS × C_total ≈ 43 ms): |VGS| = VBUS × (C_GD·1.1 + Crss) / (C_GS·0.9 + Ciss + C_GD·1.1 + Crss)
  + 0.11 V leakage term = **0.245 V** at 5.25 V; **0.380 V** for a 2× hot-plug ringing peak of 10.5 V.
- Linear ramp in T = 10 µs / 100 µs / 1 ms: |VGS| = R_GS·C_GD·(VBUS/T)·(1 − e^(−T/τ)) + 0.11 V = 0.245 / 0.245 / 0.244 V.
- All stay below 0.4 V (= 0.5 V minimum |VGS(th)| − 0.1 V margin). Q_PWR does not conduct, so no rail moves at plug-in.
  (Round 1 used C_GD 33 nF with no C_GS: |VGS| ≈ 4.9 V at plug-in, i.e. fully on — fixed.)

**Button turn-on (inrush).** EN̅ low gives a Thevenin drive of 2.96–3.57 V behind R_G‖R_GS = 32 kΩ. The gate first charges C_GS to the
threshold (delay ≤ 9.8 ms), then sits on the Miller plateau (|Vpl| between 0.5 V and 2.0 V — UNVERIFIED bound: VGS(th) max 1.3 V plus
the overdrive for ≤ 1.0 A at gFS 17 S, [AO] p.2: 1.3 + 1.0/17 = 1.36 V) while C_GD sets the drain slope: I_G = 30–96 µA → dV/dt = 2.7–10.7 V/ms →
VCC5V0_SYS ramp 0.45–1.96 ms, **inrush ≤ 60.5 µF × 10.7 V/ms = 0.65 A** (round 3 with 50 µF: 0.53 A; round 1: ≈ 3 A). Check P9
now limits the inrush to 1.0 A, the value for which the plateau bound above stays valid, and leaves ≥ 0.5 A of a 1.5 A source. It also
checks the turn-on stress: ≤ 0.65 A × 5.25 V = 3.4 W for ≤ 1.96 ms, inside the [AO] Fig. 9 10 ms SOA derated to 70 °C (8.3 W). The bucks soft-start after the ramp (§3), so
load current adds little during it.

**Turn-off (recomputed round 3, check P9e).** When EN̅ releases it is high-Z, so the only discharge path for the gate is R_GS.
1. Gate from |VGS| ≤ 3.57 V down to the plateau: no drain movement.
2. **Miller phase:** the gate sits at the plateau |Vpl| 0.5–2.0 V and R_GS takes I_G = |Vpl| / R_GS = **5–20 µA** out of C_GD, so the
   drain (VCC5V0_SYS) falls at I_G / C_GD = **0.45–2.2 V/ms** while Q_PWR still carries the load. The load does not let go until the
   bucks reach UVLO (taken as 2.1 V): from 5.25 V that is **1.4–7.1 ms** in the linear region.
3. Load model (pessimistic): the four bucks at constant input power (4.2 W from §5, so their current rises as VCC5V0_SYS falls) plus the
   0.5 A USB-A/header allowance as constant current; the discharge current of C_L is ignored. P_D = VDS × I_D peaks just before UVLO:
   **≤ 7.8 W** (3.15 V × 2.5 A), energy **≤ 21 mJ** over ≤ 7.1 ms (round 2 said 2–4 mJ; the verifier's 5–15 mJ estimate is confirmed
   in order of magnitude, with the constant-power load giving the upper end).
4. SOA: [AO] p.4 Fig. 9 (single pulse, TA 25 °C, TJ max 150 °C) — the 10 ms line runs from ≈ 12 A at 1.1 V to ≈ 0.45 A at 30 V,
   ≈ 13 W, matching Fig. 10 (≈ 13 W at 10 ms). At VDS 3.15 V it allows ≈ 4.2 A ≫ 2.5 A. Treating the whole event as a rectangular
   7.8 W × 10 ms pulse and derating linearly to TA 70 °C (× 80/125 → 8.3 W) still passes (P9e). Margin is thin only at 70 °C ambient
   **and** full load at the instant of turn-off; in normal use KILL comes after Linux has halted (load ≪ 4 W), and the Fig. 9 curve
   assumes the AOS test board (Note F, 1 in² 2 oz copper) → Phase 7: give Q_PWR's drain pad ≥ 1 in² of copper; Phase 6: check Q_PWR
   temperature after a hard-off at full load. Curve values are read from the plot (ESTIMATE).
5. Gate back below 0.5 V within ≤ 104 ms (+10 % capacitors, from 3.57 V); 104 ms < tEN,LOCKOUT min 200 ms, so a restart never meets a
   half-on switch.

### 6.4 Controller independence and fallback (D-46)

LCSC C683783 (LTC2954CTS8-2#TRPBF) exists but shows no stock; JLCPCB stock is not confirmed. **Phase 4 must confirm ≥ 100 units;
otherwise switch to the D-03 F1/F2 fallback.** Everything in §6.1/§6.3 except the timing constants is controller-independent: the
Q_PWR gate network needs only an active-low open-drain enable (any EN̅ with ≤ 1 µA leakage and VOL ≤ 0.4 V); PB_INT_N needs an
open-drain interrupt; KILL is driven by the Q_KILL inverter from the active-high PWR_KILL. A replacement must give (a) a power-on
debounce, (b) a hard-off timer settable to < 8 s worst case and (c) an EN̅ that starts released at plug-in; §6.2's table and P8 would
then be recomputed from its datasheet.

### 6.4a Phase-4 part change: LTC2954**-1** + Q_EN inverter (D-51)
The LTC2954CTS8-2 failed the stock gate (50 at JLCPCB, 31 at LCSC). The BOM uses **LTC2954CTS8-1** (C683782, 2164 in stock).
Its EN output (TSOT pin 6) is open-drain and active-high ([LTC] p.6, p.12: "-1 and -2 differ only by the polarity of the …
enable pin"), so it drives Q_PWR through an inverter:
```
VBUS_5V ── R_ENPU 100k ──┬── U_ONOFF pin 6 EN (-1)
                         └── gate Q_EN 2N7002 (C8545); source GND; drain ── R_G 47k ── Q_PWR gate network (unchanged)
```
The Q_EN drain is the "EN̅" node of §6.1–6.4. On: VGS(Q_EN) ≈ VBUS ≥ 4.75 V ≫ VGS(th) 1.0–2.5 V (min–max at ID = 250 µA,
2N7002 datasheet p.2; 1.6 V is the typical value), RDS(on) ≤ 7 Ω at VGS = 5 V, and the drain sinks ≤ 36 µA
(VOL ≈ 0). Off: IDSS ≤ 80 nA. Both are inside the §6.4 contract (≤ 1 µA leakage, VOL ≤ 0.4 V). Plug-in: the -1 EN pin peaks
at ≈ 0.7 V while VIN ≈ 0.75 V and is then held low ([LTC] p.5, typical graph). That is below the 1.0 V minimum threshold of
Q_EN, and in that window VBUS < 1 V anyway (bucks in UVLO), so the board stays off. Timing (tDB,ON, blanking, lockout, PDT)
and checks P7–P11 are unchanged. Phase 6 still scopes VCC5V0_SYS at plug-in.

### 6.5 Test points for the on/off path (D-50; refines PLAN TP8 for Phase 6)

> **Phase 6 (D-77):** physical pad numbers — TP8a′ (ONOFF_EN) = **TP8**, TP8a (EN_N) = **TP12**, TP8b = **TP13**, TP8c = **TP14**. The full list with expected values is `testpoints.md`; the bring-up order is `bringup.md`.

PLAN defines TP8 as "PWR_EN / button controller out". In this design PWR_EN is the U6 (3.3 V) enable fed from VCC_1V8, not the
controller output, so TP8 is split into three pads:

| TP | Net | On (after button) | Off / plugged in | What it proves |
|---|---|---|---|---|
| **TP8a** | **Q_EN drain** = EN̅-equivalent node at the R_G end of the Q_PWR gate network (Phase 4, D-50 amended) | ≈ 0 V (Q_EN on, ≤ 36 µA × 7 Ω; ≤ 0.4 V) | ≈ VBUS_5V (pulled through R_G + R_GS) | the controller has switched on and the inverter works; this is the "button controller out" of PLAN TP8 |
| **TP8a′** | **LTC2954-1 pin 6 EN** (controller output itself, R_ENPU 100k to VBUS_5V) | ≈ VBUS_5V (EN released = on) | ≤ 0.4 V (EN pulls low = off; VOL [LTC] p.3) | **inverted** with respect to TP8a: separates a controller fault from a Q_EN fault |
| **TP8b** | **VCC5V0_SYS** (Q_PWR drain) | VBUS_5V − ≤ 0.26 V (≥ 4.74 V from a 5.0 V source) | 0 V (R_BL5) | the high-side switch passes power; TP1 − TP8b = input drop (D-39) |
| **TP8c** | **PWR_EN** (U6 enable node, R41/R43 junction) | ≈ VCC_1V8 (1.74–1.86 V, ≥ VIH max 1.2 V) | 0 V | the 3.3 V buck is enabled from 1.8 V (P7d) |

## 7. Gate TP-D3 self-check

| Gate clause | Result | Where / check |
|---|---|---|
| Every SoC supply pin has a rail | 28/28 supply pins mapped (plus 3 ground pins) | §2, `power_rails.csv`; P1, P2 |
| Regulator ratings ≥ 1.3 × worst-case current | all four bucks 2.0–9.9× (cited [TLV] p.4; bleeder currents included); Q_PWR 2.3× (cited [AO] p.1). Round 3: not-yet-chosen parts (J1, F1, SD switch, USB-A switch) were Phase-4 requirements, not passes. **Phase 4: all four now carry cited ratings (D-54, D-56) and P5 counts them (0 `REQ`)** | §2; P5 (+ `REQ`) |
| Sequencing matches datasheet | [DS] r1.8 specifies no sequence (stated). Design follows [LF]'s order (core → 1.8 V/DDR → 3.3 V → nPOR), now chained (3.3 V enabled from VCC_1V8) and proven over the guaranteed EN window 0.4–1.2 V with per-chip corners, capacitor tolerance and ramp-rate extremes; restart order guaranteed by bleeders on VCC5V0_SYS and all four buck outputs (every rail and enable ≤ 0.4 V at the earliest restart); all set-points inside [DS] Table 3-2 / Table 3-1; **total** rail capacitance (buck-local + SoC side) inside the [TLV] Table 4 checked range | §2, §3; P3, P7, P10, P11 |
| Total input power < 5 V × 1.5 A | 7.09 W worst case incl. losses and bleeders | §5; P6 |
| R4 behaviour fully explained at circuit level | plug-in stays off, power-on, soft-off via INT → gpio-keys → logind → gpio-poweroff → KILL, hard-off ≥ 8 s (8.07–22.4 s since D-117 c, incl. ±20 % PDT current), lockout/restart, reboot/reset, unplug, MASKROM; turn-off stress inside the [AO] SOA | §6; P8, P9, P9e |

Open items carried forward: Phase 4 — LCSC/JLCPCB stock ≥ 100 for LTC2954CTS8-2 (C683783, D-46) else D-03 fallback; TLV62569
(DBV C141836 seen in stock at LCSC, JLCPCB unconfirmed; prefer DDC/DRL for U4), AO3401A, AO3400A-class N-FET, 2 A PPTC, TVS,
USB-C receptacle ≥ 3 A, USB-A switch meeting §2, SI2301 ID(70 °C) citation ≥ 0.26 A, 2.2 µH Isat ≥ 3.6 A inductors, 22 µF X5R/X7R
≥ 6.3 V. Phase 4 also — R32 as a **fitted** 0 Ω (done as copper NT_ARM, D-68); MLCC DC-bias retention ≥ 0.7 (≤ 1.8 V rails) / ≥ 0.5 (3.3 V); U_USBA RDS(on) ≤ 100 mΩ.
Phase 5 — feed-forward 6.8 pF ×4, five bleeders, gate network, 0 Ω current-measurement links, **[LF] SoC-side decoupling exactly as
listed in §2 (no extra bulk on the four buck rails without re-running P10), U4 local 10 µF**, NT_ARM copper + JP_MEAS_0V9 jumper (D-68), TP8a/b/c. Phase 7 — VDD_0V9
copper short and wide; Q_PWR drain copper ≥ 1 in². Phase 6 — measure TP1/TP8 drop,
rail ramps and order (§3 table) with a 4-channel scope, plug-in with no press (VCC5V0_SYS must stay 0 V), hard-off time, PWR_EN level,
Q_PWR temperature at turn-off, rail currents.

## 8. Phase-4 part-level updates (2026-10-29, D-54, D-56, D-57, D-58)

`check_power.py` after these changes: **76 pass, 0 fail, 0 `REQ`** (round 3: 70/0/4). The new or changed checks are P5 (×4 cited
ratings), P5t, P9 inrush (C_L 60.5 µF) and P9 turn-on stress.

| Item | Change | Basis |
|---|---|---|
| Ratings formerly `REQ` | J1 5 A; F1 2.01 A at 60 °C; Q_SD 1.8 A at 70 °C; U_USBA ILIM min 0.75 A, now in `power_rails.csv` `rating_a`/`rating_source` | HRO TYPE-C-31-M-12 note 4-1; BHFUSE BSMD1812 Rev 2025 p.5; Vishay 68741 p.1; AN_SY6280 Rev 0.1 p.3 |
| F1 | BSMD1812-200-16V → **BSMD1812-300-16V** (C883162). The -200 holds only 1.80 A at 40 °C, 1.66 A at 50 °C and 1.09 A at 70 °C, so 1.3 × 1.41 A held only to ≈ 35 °C. The -300 holds 2.01 A at 60 °C (1.43×) and 1.61 A at 70 °C (1.14×, P5t). **Design ambient for the full 1.3× margin: ≤ 60 °C**; up to 70 °C the fuse still carries the worst case without tripping. R1max 0.050 Ω (was 0.100 Ω): §4/D-39 keep 0.10 Ω, so the 0.26 V drop and the 4.44 V USB-A low corner are conservative. Itrip 6.0 A is above the J1 5 A contact rating; a sink with Rd only and no PD is offered at most 3 A by a compliant source (USB Type-C current; spec not downloaded, UNVERIFIED), so J1 sees > 5 A only from a non-compliant charger into a fault, and then only until F1 trips | BHFUSE BSMD1812 Rev 2025 p.2 table, p.5 Thermal Derating Chart (`refs/bsmd1812-300-16v-datasheet/`, byte-identical to the -200 file) |
| SY6280 VIN | C_USBA_IN (bom.csv **C10**; refmap.csv, D-63) 1 µF → **10 µF 25 V X5R 0603** (C96446, already a BOM line), placed within 2 mm of U_USBA pin 5 (Phase 7 rule). C_L of VCC5V0_SYS rises to 60.5 µF; inrush 0.65 A (P9) | AN_SY6280 Rev 0.1 p.5 "Supply Filter Capacitor": 10 µF ceramic "strongly recommended"; without it an output short rings VIN above the 6 V abs-max (round 1 wrongly cited p.1) |
| VBUS_USBA bulk | 22 µF ceramic at U_USBA OUT + **120 µF 10 V polymer** (Lelon OVZ121M1ATR-0606, C250087, ESR ≤ 22 mΩ) at the USB-A connector = 142 µF nominal (≥ 120 µF; ≈ 107 µF at −20 % polymer tolerance and 50 % MLCC DC-bias retention, UNVERIFIED corner). Charge time at ILIM 0.75–1.25 A: 142 µF × 5.25 V / 0.75 A ≈ **1.0 ms** (TON 120 µs typ, AN_SY6280 p.3), during which VCC5V0_SYS supplies up to 1.25 A extra; done once, when Linux sets USBA_VBUS_EN | USB 2.0 §7.2.4.1 (≥ 120 µF low-ESR per downstream port; spec not downloaded, UNVERIFIED); Lelon OCVZ catalog p.36 (the LCSC-linked datasheet for this MPN; series name printed "OCVZ", UNVERIFIED that it is the same series as "OVZ") |
| Phase 6 additions | Scope VCC5V0_SYS (TP8b) when USBA_VBUS_EN goes high with no device, and when a device is hot-plugged into USB-A; measure TP8a (≈ 0 V on) and TP8a′ (≈ VBUS on) | D-50 amended, D-58 |
| Phase 7 additions | C_USBA_IN (bom.csv **C10**) ≤ 2 mm from U_USBA (bom.csv U8) pin 5 with a direct GND via; the 120 µF next to the USB-A VBUS pin; VBUS_USBA traces short and wide | AN_SY6280 p.5 layout guide |

