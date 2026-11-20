# Requirements (Rev A) — frozen copy + traceability

Source of truth: `PLAN.md` § "Requirements (frozen)". This file copies R1–R8 verbatim in meaning, splits each into
checkable sub-requirements, and maps every one to the board blocks defined in `architecture.md`
(block ids: `usbc, prot, onoff, pmu, soc, xtal, nand, sd, eth, usb, gpio, uart, ui`).

Source list used in this phase (all saved under `design/refs/`, never executed):

| Ref | Document | URL | Local copy |
|---|---|---|---|
| [DS] | Rockchip RV1106 Datasheet Rev 1.8 (2025) | https://atta.szlcsc.com/upload/public/pdf/source/20250728/0F25565987B346BAFAE15AD3F3BED3E9.pdf | `refs/rv1106-datasheet-r1.8/RV1106_Datasheet_r1.8.pdf` |
| [LF] | Luckfox Pico Pro/Max schematic (single sheet, A4) | https://github.com/LuckfoxTECH/Luckfox-Pico-docs/blob/main/Hardware/Schematic/Luckfox-Pico-Pro-Max.pdf (raw: https://raw.githubusercontent.com/LuckfoxTECH/Luckfox-Pico-docs/main/Hardware/Schematic/Luckfox-Pico-Pro-Max.pdf; repo commit dated 2026-07-14) | `refs/luckfox-pico-pro-max-sch/Luckfox-Pico-Pro-Max.pdf` |
| [LFDL] | Luckfox RV1106 downloads page (points to the repo above) | https://wiki.luckfox.com/Luckfox-Pico-RV1106/Downloads/ | — |
| [JLC] | JLCPCB part page RV1106G3 (C5328706) | https://jlcpcb.com/partdetail/Rockchip-RV1106G3/C5328706 | — (stock checked in Phase 4) |

Because [LF] is one A4 sheet, locations below are given as the sheet's printed zone/title block (e.g. "Setp 1 VCC5V0_SYS--->VDD_0V9",
"Micro-SD Card", "Type-C", "Ethernet").

---

## R1 — Power from USB-C (5 V), no USB-PD chip
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R1.1 | 5 V input from a USB-C receptacle; sink-only, default USB power (no PD) | `usbc` | [LF] "Type-C" block: CC1/CC2 each 5.1 kΩ to GND (R3, R6) |
| R1.2 | Input protected: fuse, TVS, ESD | `prot` | Deviation from [LF] (no fuse/TVS shown) — see decisions D-04 |
| R1.3 | All SoC rails generated on-board from 5 V | `pmu` | [LF] bucks U4/U5/U6/U7; [DS] Table 3-2 |
| R1.4 | Total input < 5 V × 1.5 A (Phase 3 gate) | `pmu`, `usb` | PLAN.md TP-D3 |

## R2 — 10/100 Ethernet
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R2.1 | RV1106 internal MAC + embedded PHY, RMII internal | `soc`, `eth` | [DS] §1.2.13 p.13 "MAC 10/100M Ethernet controller and embedded PHY" |
| R2.2 | RJ45 with integrated magnetics on PHY pins ETH_PHY_TXP/TXN/RXP/RXN | `eth` | [DS] Table 2-1 p.18 pins 97–100; [LF] "Ethernet" block J2 |
| R2.3 | Acceptance: link, DHCP, ping, SSH | `eth`, `soc` (software Phase 8) | PLAN.md R2 |

## R3 — Expansion
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R3.1 | 2×20 2.54 mm header: GPIO, UART, I²C, SPI, PWM, 3.3 V, 5 V, GND | `gpio` | [DS] §1.2.13 p.13 (SPI0–1, I2C0–4, UART0–5), §1.2.3 p.7 PWM0–PWM11 |
| R3.2 | 1× USB 2.0 host, Type-A | `usb` | [DS] §1.2.13 "Support one USB 2.0 Host/Device" — shared with USB-C, see D-05 |

## R4 — On/off button
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R4.1 | Short press from off → power on | `ui` (POWER button), `onoff`, `pmu` | Push-button controller drives main load switch (D-03) |
| R4.2 | Short press while on → interrupt to SoC → clean Linux shutdown → SoC asserts KILL | `onoff`, `soc` | PLAN.md Phase 3 / Phase 8 |
| R4.3 | Long press ≥ 8 s → hard off independent of software | `onoff` | Controller timer, chosen in Phase 3 (UNVERIFIED which IC gives ≥ 8 s) |

## R5 — Boots Linux
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R5.1 | Cortex-A7 SoC with in-package 2 Gb (256 MB) DDR3L | `soc` | [DS] §2.1 p.15 order info "RV1106G3 … 2Gb DDR3L" |
| R5.2 | 24 MHz reference clock | `xtal` | [DS] §1.2.3 p.7 "One oscillator with 24MHz clock input"; [LF] Y1 24MHz |
| R5.3 | Boot media: SD / SPI NAND; USB download (MASKROM) | `sd`, `nand`, `usbc`, `ui` | [DS] §1.2.2 p.6 BootRom boot devices + download via USB/UART |
| R5.4 | Shell over UART and SSH with Luckfox/Rockchip Buildroot SDK | `uart`, `eth`, `soc` | PLAN.md R5 |

## R6 — Storage
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R6.1 | microSD on SDMMC0 (4-bit), bring-up boot device | `sd` | [DS] §1.2.2 p.7 SD/MMC 4-bit; [LF] "Micro-SD Card" TF1 |
| R6.2 | SPI NAND ≥ 128 MB on FSPI | `nand` | [DS] §1.2.2 p.7 FSPI 1/2/4-bit; [LF] U2 W25N02KVZE (2 Gb) |

## R7 — Debuggability
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R7.1 | 3-pin debug UART header (TX, RX, GND) on UART2 | `uart` | [LF] UART2_TX/UART2_RX on SoC pins 79/80 ([DS] Table 2-1 p.18 UART2_TX_M1/RX_M1) |
| R7.2 | Test points on every rail / clock / reset (TP1–TP11) | power blocks `prot`, `onoff`, `pmu`; `xtal`, `soc`, `uart`, `eth` | PLAN.md Phase 6 table |
| R7.3 | MASKROM button | `ui` | [LF] "System RECOVERY Key" Key2 on net RECOVERY (= SARADC_IN0) |
| R7.4 | Reset button | `ui` | [LF] "Power Reset" Key1 on NPOR |
| R7.5 | Status LEDs (power + activity) | `ui`, `pmu` (PWR LED on VCC_3V3), `soc` (LED GPIOs) | [LF] net LED_GREEN on U1 pin 62 (GPIO0_A3_u); see D-09 |

## R8 — Manufacturability
| Sub | Statement | Blocks | Basis |
|---|---|---|---|
| R8.1 | 4-layer JLCPCB standard (JLC04161H-7628) | whole board (all 13 blocks share the stack-up) | PLAN.md Phase 7 |
| R8.2 | JLCPCB/LCSC parts, prefer Basic | every block: usbc, prot, onoff, pmu, soc, xtal, nand, sd, eth, usb, gpio, uart, ui | RV1106G3 is LCSC C5328706 [JLC]; rest Phase 4 |
| R8.3 | Single-sided assembly (all SMD on top); fine-pitch rules | every block (top side); `soc` drives the fine-pitch rules | QFN128 12.3 mm, 0.35 mm pitch ([DS] §1.2.14 p.14) drives fine-pitch rules — Phase 7 |

## Traceability summary (R → block)
| Req | Blocks |
|---|---|
| R1 | usbc, prot, pmu, usb |
| R2 | soc, eth |
| R3 | gpio, usb |
| R4 | ui, onoff, pmu, soc |
| R5 | soc, xtal, sd, nand, usbc, ui, uart, eth |
| R6 | sd, nand |
| R7 | uart, ui, prot, onoff, pmu, soc, xtal, eth |
| R8 | R8.1 all blocks (board stack-up); R8.2 usbc, prot, onoff, pmu, soc, xtal, nand, sd, eth, usb, gpio, uart, ui (every part from LCSC); R8.3 all blocks top-side, soc for fine-pitch (QFN128 0.35 mm) rules |

Each summary row is the union of the blocks in its sub-requirement table above (checked in round 2). Every block id in
`architecture.md` maps to at least one requirement, and every requirement to at least one block.
