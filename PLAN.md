# Custom Linux Board — Design Plan (Rev A)

## Goal
A small custom PCB built around the **Rockchip RV1106G3** (Cortex-A7 1.2 GHz, 256 MB DDR3L in package, QFN-128)
that boots Linux on the first revision. Fabricated and assembled by JLCPCB, total budget < $500 for two revisions.

## Requirements (frozen)
| ID | Requirement | Acceptance |
|---|---|---|
| R1 | Power from USB-C (5 V) | Boots from any USB-C charger; no USB-PD chip needed |
| R2 | 10/100 Ethernet | Link up, DHCP lease, ping and SSH work |
| R3 | Expansion | 2×20 header (2.54 mm) with GPIO, UART, I²C, SPI, PWM, 3.3 V, 5 V, GND; plus 1× USB 2.0 host (Type-A) |
| R4 | On/off button | Short press turns on from off; short press while on = clean Linux shutdown; long press (≥8 s) = hard off |
| R5 | Boots Linux | Rockchip/Luckfox Buildroot SDK boots to a shell over UART and SSH |
| R6 | Storage | microSD (boot during bring-up) + on-board SPI NAND (128 MB+) |
| R7 | Debuggability | 3-pin UART debug header, test points on every rail/clock/reset, MASKROM button, status LEDs |
| R8 | Manufacturability | 4-layer, JLCPCB standard process, JLCPCB/LCSC parts (prefer Basic parts), single-sided assembly |

## Reference designs
- **Luckfox Pico Pro / Max** (RV1106G3) — published schematics; primary reference for power, SoC core, Ethernet, SPI NAND.
- Rockchip RV1106 datasheet + hardware design guide.
- Copy proven circuits; every deviation from the reference must be justified in `design/decisions.md`.

## Process
Each phase is done by the **Executor**, then checked by the **Verifier** against the phase's design gate.
If the gate fails, the Verifier's findings go back to the Executor, who fixes them, and the Verifier checks again
(max 3 rounds, then escalate to the human). After each gate, the **Dashboard** agent updates the board visualization.

All outputs live under `design/`. Sources (datasheets, reference schematics) must be cited with URL + page/section.

---

## Phase 1 — Architecture & block diagram
Outputs: `design/requirements.md`, `design/architecture.md` (block diagram as Mermaid + text), `design/decisions.md`.
**Gate TP-D1:** every requirement R1–R8 maps to a block; every interface between blocks is named (signal type, voltage).

## Phase 2 — Reference research & pin map
Outputs: `design/research.md` (sources), `design/pinmap.csv` (every RV1106G3 pin used: pin #, function, net name, IO voltage domain, source).
**Gate TP-D2:** each pin assignment cites the datasheet or reference schematic; no pin used twice; IO voltage domains consistent
(e.g. Ethernet, SDMMC, SPI NAND domains at the correct VCCIO); boot-mode/strap pins identified.

## Phase 3 — Power architecture
Outputs: `design/power.md`: power tree, rail table (voltage, max current, regulator, source), sequencing, power budget,
USB-C sink circuit (CC 5.1 kΩ pull-downs, TVS, fuse), on/off controller (push-button controller IC driving regulator EN +
interrupt GPIO to SoC + kill input from SoC for software power-off).
**Gate TP-D3:** every SoC supply pin has a rail; regulator ratings ≥ 1.3× worst-case current; sequencing matches datasheet;
total input power < 5 V × 1.5 A; R4 behavior fully explained at circuit level.

## Phase 4 — Part selection & BOM
Outputs: `design/bom.csv` (ref, value, description, footprint, LCSC #, Basic/Extended, stock, unit price), `design/cost.md`.
**Gate TP-D4 (amended by owner decision D-H2):** every part has an LCSC number that exists and is in stock (≥ 100 units; the RV1106G3 SoC only:
JLCPCB stock ≥ boards + 2, rechecked on the order day); footprints match; cost estimate for **2 assembled boards + 3 bare PCBs**
(PCB + Standard assembly + parts + shipping) ≤ $380, with Extended part types minimized.

## Phase 5 — Schematic
Outputs: `design/schematic/` as **SKiDL** Python (one module per block: power, soc, clocks, storage, ethernet, usb, expansion, debug, button)
generating a KiCad netlist; `design/schematic/README.md`.
**Gate TP-D5:** script runs; SKiDL ERC clean (or every warning justified); net-by-net check against `pinmap.csv` and reference schematic;
decoupling per datasheet on every supply pin; every net listed in the test-point plan exists.

## Phase 6 — Test points & bring-up plan
Outputs: `design/testpoints.md` (physical TP list: net, expected value, tolerance, how to measure), `design/bringup.md` (ordered bring-up procedure).
**Gate TP-D6:** a TP exists for every rail, the 24 MHz clock, reset, button/power-enable, UART TX/RX; bring-up steps are ordered so that a failure
at step N can't damage the board at step N+1.

Physical test points (minimum):
| TP | Net | Expected |
|---|---|---|
| TP1 | VBUS_5V (after fuse) | 5.0 V ±5 % |
| TP2 | VCC_3V3 | 3.3 V ±3 % |
| TP3 | VCC_1V8 | 1.8 V ±3 % |
| TP4 | VDD_CORE (CPU/logic/NPU) | per datasheet ±3 % |
| TP5 | VCC_DDR | per datasheet ±3 % |
| TP6 | 24 MHz oscillator | 24.000 MHz |
| TP7 | RESET_N | high after power-good |
| TP8 | PWR_EN / button controller out | high when on |
| TP9/10 | UART2 TX/RX (debug) | boot log at 115200 or 1500000 baud |
| TP11 | ETH 25 MHz / PHY LED | activity |

## Phase 7 — Layout constraints (for the human layout in KiCad)
Outputs: `design/layout.md`: JLCPCB 4-layer stackup (JLC04161H-7628), impedance targets (Ethernet 100 Ω diff, USB 90 Ω diff),
placement plan (connectors on edges, SoC centered, crystal close to SoC), ground strategy, thermal pad vias, board outline (70 × 70 mm per D-H2, JLCPCB Standard PCBA minimum, with edge rails and fiducials), mounting holes.
**Gate TP-D7:** every high-speed/sensitive net has a rule; trace widths computed for the stackup; checklist ready for the human DRC review.

## Phase 8 — Software
Outputs: `software/`: board device tree (derived from Luckfox Pico Pro DTS), Buildroot/SDK board config notes, power-button handling
(gpio-keys → systemd/acpid shutdown, gpio-poweroff to the button controller's kill input), `software/README.md` build steps.
**Gate TP-D8:** DTS pins match `pinmap.csv`; DTS compiles with `dtc` (or syntax-reviewed if dtc unavailable); shutdown path R4 complete.

---

## Human phases (after this automated run)
| Phase | Who | Test points |
|---|---|---|
| H1 Install KiCad, import netlist, PCB layout (follow `design/kicad-guide.md`) | You (Claude reviews) | KiCad ERC + DRC clean; checklist from `layout.md` |
| H2 Generate Gerbers/BOM/CPL, order JLCPCB | You (Claude prepares files) | JLCPCB DFM check passes |
| H3 Bring-up | You at the bench (Claude guides) | Follow `bringup.md`: TP1→TP5 with no SoC load, TP6–TP8, UART log, SD boot, Ethernet, USB, button |

## Definition of done (Rev A)
Board powers from USB-C, the button turns it on, Linux boots from microSD to a shell over UART, Ethernet gets DHCP and accepts SSH,
the button performs a clean shutdown.

---

## Layout phases (owner decision D-H4, 2026-10-29: Claude does the PCB layout end to end; the owner reviews at checkpoints)

Tools: KiCad 10.0.7 (`/Applications/KiCad/KiCad.app`), its bundled Python 3.9 with `pcbnew` for scripting, `kicad-cli` for DRC,
rendering and exports; Freerouting 2.5.0 for bulk routing of low-speed nets once the owner has placed the jar in
`thirdparty/freerouting-2.5.0/`. Every board change is made by a **script under `design/pcb/scripts/`** that rebuilds or edits
`design/pcb/rv1106-reva.kicad_pcb` reproducibly, never by unrecorded hand edits. Rules come from `design/layout.md` and
`design/layout/*.csv`; any deviation goes in decisions.md and `check_layout.py` is rerun.

| Phase | Outputs | Gate |
|---|---|---|
| L1 Footprints | `design/pcb/board.pretty/` with the 6 custom footprints (+ fiducial if missing), `design/pcb/scripts/make_footprints.py` | **TP-L1:** every pad name the netlist uses exists; dimensions match the cited drawing (verifier re-measures); QFN-128 pin 1/numbering direction matches [DS] Fig. 2-5; JLC pad/mask minima met; J4 VBUS side and TF-01A numbering decided and recorded |
| L2 Board build & placement | `scripts/build_board.py` (netlist → board, outline, rails, V-cut, holes, fiducials, stackup, net classes, DRU), `scripts/place.py`, renders `design/pcb/renders/*.png` | **TP-L2:** 226 footprints / 135 nets, no missing pads; every part in its placement.csv zone (or recorded deviation); ring-1/ring-2/crystal/buck/U8 distances of layout.md §10 "Placement" met; no courtyard overlaps (kicad-cli DRC); connector mouths on their edges; nothing on the bottom → **CHECKPOINT 1: owner reviews placement** |
| L3 Planes & SoC escape | L2 GND, L3 regions per planes.csv, L1/L4 pours, SoC fan-out vias, EP vias | **TP-L3:** every U9 pad escaped; plane regions match planes.csv; DRC 0 errors on what exists |
| L4 Critical routing | ETH, USB, crystals, SDMMC, FSPI, buck loops/feedback, power paths | **TP-L4:** layout.md §4 rules met with measured lengths/skew; DRC 0 errors |
| L5 Remaining routing | Freerouting (or scripted) for the rest, cleanup, stitching vias | **TP-L5:** 0 unconnected; DRC 0 errors; layout.md §10 fully ticked → **CHECKPOINT 2: owner reviews routed board** |
| L5F Review fixes (D-H6) | `scripts/l5f_run.sh` (l5f_prep/route/tidy/board, silk, renders) after L5; `scripts/l5fcheck.py` + `mutate_l5f.py`; `pcb/via_in_pad.csv`; `pcb/fix-review.md`, `renders/route_l5f_*.png`; BOM C24/C6/C71 values | **TP-L5F:** every D-H6 item fixed or recorded (decisions.md D-117); buck input-cap GND -> pin 2 on L1 <= 3 mm, pin 2 solid with >= 2 vias; via-in-pad list complete and exported; copper >= 0.8 mm from the V-cuts; EN/PWR_EN >= 1 mm from SW copper; silk lines >= 0.15 mm, text >= 1.0 mm; In2 GND under the L4 pair hops; 0 track/via_dangling; R 1 mm board corners; a FAIL-capable check (with a mutation test) for each measurable item; clean rebuild reproduces the board; DRC 0 errors / 0 unconnected; check_routing / l5check / check_placement 0 FAIL → both independent reviews re-run before L6 |
| L5G Re-review fixes (D-H7) | L5G scripts after L5F (wired into rebuild_all.sh); new checks + mutations; `pcb/fix-review-l5g.md`, `renders/route_l5g_*.png` | **TP-L5G:** U9 EP vias are board vias (ViaDrill) and board setup has via filling + capping; every visible silk reference / TP label nearer its own part than any other (FAIL check + mutation); TH text off the board; SDMMC_CLK_SD >= 0.30 mm from D0/CMD; RTC_XOUT >= 0.5 mm from SDMMC_D2; J5.2 link to pad centre; J1-shell via hole edges >= 0.45 mm; In2_GND_HOP_3 >= 2 vias; Q1 drain >= 4 VCC5V0_SYS vias; USB/ETH pair report; clean rebuild reproduces the board; DRC 0 errors / 0 unconnected; all checks 0 FAIL |
| L6 Fabrication outputs | Gerbers, drill, JLC BOM + CPL, 3-D render, order notes | **TP-L6:** files regenerate from scripts; Gerber viewer check; CPL rotations reviewed against footprints |
