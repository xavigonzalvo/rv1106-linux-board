# Phase 2 — Reference research & pin map: sources and findings

Status: Executor, attempt 2 (round-2 fixes: D-27..D-31), 2026-10-28. Companion to `pinmap.csv` (129 rows = 128 pins + exposed pad) and
`tools/check_pinmap.py` (the machine self-check for gate TP-D2).

## 1. Sources

All downloaded files are kept read-only under `refs/<name>/`. Nothing in them was executed. Text was extracted with the venv's
pymupdf (`python -I`), and the scripts live outside `refs/`.

| Tag | Document | URL | Local copy | Used for |
|---|---|---|---|---|
| [DS] | Rockchip RV1106 Datasheet Rev 1.8 (2025) | https://atta.szlcsc.com/upload/public/pdf/source/20250728/0F25565987B346BAFAE15AD3F3BED3E9.pdf | `refs/rv1106-datasheet-r1.8/RV1106_Datasheet_r1.8.pdf` | Pin list **Table 2-1 pp.18–19** (pin #, full mux name, `_u`/`_d`/`_z` reset pull). Supply ranges **Tables 3-1/3-2 p.20**: `GPIOi_VCC(i=3~6, 1.8V/3.3V mode)`, `GPIO1_VCC3V3`, `MIPI_AVDD1V8/GPIO7_VCC1V8`. DC levels and pull strength **Table 3-3 p.21** (Rpu/Rpd 16/25/43 kΩ, Vih 2.0 V at 3.3 V). BootROM device list **§1.2.2 p.6**. |
| [LF] | Luckfox Pico Pro/Max schematic (one A4 sheet) | https://github.com/LuckfoxTECH/Luckfox-Pico-docs/blob/main/Hardware/Schematic/Luckfox-Pico-Pro-Max.pdf | `refs/luckfox-pico-pro-max-sch/Luckfox-Pico-Pro-Max.pdf` | Net per SoC pin (U1A–U1D). IO-domain boxes printed on the symbol: "PMU UART/PWM/I2C(3.3V only)", "VCCIO1 UART/I2C/PWM/JTAG(3.3V only)", "VCCIO2 SARADC/PWM(1.8V only)", "VCCIO3 EMMC/FSPI/UART/I2C/SPI", "VCCIO4 SDMMC/UART/JTAG/PWM/I2C", "VCCIO5 SDIO/I2S/VO_LCDC/UART/PWM/I2C", "VCCIO6 VO_LCDC/VI_CIF/…/SPI", "VCCIO7 VI_CIF/MIPI_CSI/… (1.8V only, some for input only)". Peripheral circuits: SD (TF1, R54, R16, Q1), SPI Flash (U2, R15, R18, R19, VCCIO_FLASH), Ethernet (R46–R49, R7 6.04 k), RECOVERY key (R21, C44), nPOR (R12, C38), 24 MHz (Y1, C29/C30, R9/R10), RTC (Y2, C33/C34, R11). |
| [SDK] | Luckfox Pico SDK kernel device tree (`LuckfoxTECH/luckfox-pico`, `sysdrv/source/kernel/arch/arm/boot/dts/`) | https://github.com/LuckfoxTECH/luckfox-pico/tree/main/sysdrv/source/kernel/arch/arm/boot/dts (e.g. raw `…/rv1106g-luckfox-pico-pro-max.dts`, checked online 2026-10-28) | `refs/luckfox-sdk-dts/` (`rv1106.dtsi`, `rv1106-pinctrl.dtsi`, `rv1106-evb.dtsi`, `rv1106-luckfox-pico-pro-max-ipc.dtsi`, `rv1106g-luckfox-pico-pro-max.dts`, `rv1106-amp.dtsi`) | Mux function numbers and default bias (`rv1106-pinctrl.dtsi`, e.g. L108-126 fspi, L729-732 sdmmc0_det pull_up, L405-414 pmic_sleep_m0/m1 on GPIO0_A4/A3, L994+ uart2m1_xfer). Console: `rv1106.dtsi` L227-230 fiq-debugger `rockchip,serial-id = <2>`, `rockchip,baudrate = <115200>` ("Only 115200 and 1500000"). Enabled (`status = "okay"`) in the Pro/Max DTS: `&sfc` spi-nand at 75 MHz, quad RX. `&sdmmc` 4-bit with `no-1-8-v`. `&gmac`, `&usbdrd_dwc3 dr_mode="peripheral"`. **Defined but `status = "disabled"`** (`rv1106g-luckfox-pico-pro-max.dts` L97-130): `&spi0`, `&i2c3`, `&i2c1`, `&uart3`, `&uart4`. Their pinctrl groups (I2C3_M1, I2C1_M1, UART3_M1, UART4_M1, SPI0_M0) are set in `rv1106-luckfox-pico-pro-max-ipc.dtsi` L268-356, together with groups that conflict with this board (§7). adc-keys on `saradc 0` (`rv1106-evb.dtsi` L9-14). |
| [SDKK] | Kernel io-domain driver + binding, as shipped | (same repo, `drivers/power/avs/rockchip-io-domain.c`, `Documentation/devicetree/bindings/power/rockchip-io-domain.txt`) | `refs/luckfox-sdk-kernel-src/` | Negative finding: no RV1106 entry in this driver copy, and no io-domain node in the Pro/Max DTS. See §3. |
| [CD] | "Luckfox Pico boards" (community U-Boot docs) | https://concept-docs.readthedocs.io/en/latest/board/luckfox/luckfox-pico.html | — (read online) | MASKROM: "Hold the BOOT button while applying power (or leave the boot media blank)" → BootROM USB ID 2207:110c. The page describes the Pico Mini B (same SoC family), not the Pro/Max. |
| [FORUM] | ClockworkPi forum "Luckfox Lyra on PicoCalc" + PPPwn-Luckfox README | https://forum.clockworkpi.com/t/luckfox-lyra-on-picocalc/16280?page=12 ; https://github.com/Doyle4/PPPwn-Luckfox | — | Weak evidence on boot order: users report that firmware already on NAND must be erased before the board boots from SD. |

Sources checked with no useful content: https://wiki.luckfox.com/Luckfox-Pico-RV1106/FAQ, `/FAQ/Flashing` and
`/Downloads/` (nothing on boot order or the MASKROM pin). The Pro/Max "Burn-image" wiki URL returned 404.

## 2. Method

1. `tools/ds_pins.py` parses [DS] Table 2-1 (PDF pp.18–19) into {pin: full name}. It finds 128 pins plus E-PAD.
2. Each pin was looked up in [LF] (U1A–U1D net labels). The net was copied when the circuit is kept. When the circuit is new (D-03 on/off, D-05 USB mux, LEDs, header), a pin was chosen whose domain, voltage and reset pull fit, and the reason is recorded.
3. Mux function, bias and peripheral instance were checked against [SDK] `rv1106-pinctrl.dtsi` and the Pro/Max DTS. Header instances are deliberately the ones Luckfox **defines** (they are disabled in its DTS). Their pinctrl group names and mux numbers are known-good, but the Luckfox fragments do **not** carry over as-is: Phase 8 enables them in its own overlay and follows the "must not inherit" list in §7 (D-22, D-28).
4. The domain of every signal pin was traced to its supply pin (`domain_supply_pin` column), then to the rail on [LF].
5. `tools/check_pinmap.py` runs the gate checks C0–C16 (below). Run it with
   `design/.venv/bin/python -I design/tools/check_pinmap.py design`. Result on 2026-10-28 (round 2): **17 pass, 0 fail**.
   Round 2 made the checks stricter. C4 now needs `function_used` to be an exact token of the `/`-split [DS] mux list. C9 derives the reset pull from the [DS] `_u`/`_d`/`_z` suffix, not from the pinmap's own column. New checks: C0 (CSV well-formed), C12 (reset_pull column = [DS] suffix on all rows), C13 (no SoC pin pulled or driven from an always-on rail VBUS_IN/VBUS_5V/VCC3V3_RTC), C14 (VBUSDET divider on VCC5V0_SYS), C15 (header I²C pull-ups) and C16 (debug UART series resistors). A mutation test confirms that C4, C12, C13 and C14 fail on deliberately broken copies.

## 3. IO voltage domains (gate: domains consistent)

| Domain | Supply pin ([DS] T2-1) | Rail ([LF]) | Voltage | Capability ([DS] T3-2 / [LF] box) | Used for on this board |
|---|---|---|---|---|---|
| PMU | 61 PMU_VCC3V3 | VCC_3V3 | 3.3 V | 3.3 V only | SDMMC_PWREN (59), PB_INT_N (60), LED_GREEN (62), PWR_KILL (63), USBA_VBUS_EN (64), USB_SEL (65), nPOR (66) |
| VCCIO1 | 81 GPIO1_VCC3V3 | VCC_3V3 | 3.3 V | 3.3 V only | UART2_M1 debug (79/80), LED_ETH (74), header GPIO1_A0/A1/A3/A4/B0/B1 |
| VCCIO2 | 24 SARADC_USB_AVDD1V8 | AVDD1V8_USB (1 Ω from VCC_1V8, [LF] R8) | 1.8 V | 1.8 V only ([LF] "VCCIO2_VCC1V8 supply from USB_AVDD1V8") | RECOVERY/MASKROM (23), SARADC_IN1 terminated (22) |
| VCCIO3 | 43 GPIO3_VCC | VCCIO_FLASH = VCC_3V3 | 3.3 V | 1.8/3.3 V | **SPI NAND** FSPI (39, 41, 42, 44, 47, 48) |
| VCCIO4 | 13 GPIO4_VCC | VCC_3V3 | 3.3 V | 1.8/3.3 V | **microSD** SDMMC0 (11, 12, 14–18). Fixed 3.3 V, matches [SDK] `no-1-8-v` (D-13) |
| VCCIO5 | 108 GPIO5_VCC | VCC_3V3 | 3.3 V | 1.8/3.3 V | Header: I2C1_M1, GPIO2_A0–A7 |
| VCCIO6 | 88 GPIO6_VCC | VCC_3V3 | 3.3 V | 1.8/3.3 V | Header: SPI0_M0, I2C3_M1, UART3_M1, PWM8–11_M1 |
| VCCIO7 | 1 MIPI_AVDD1V8/GPIO7_VCC1V8 | MIPI_CSI_AVDD_1V8 (1 Ω [LF] R31) | 1.8 V | 1.8 V only | **Nothing**. All 20 GPIO3_B/C/D pins are NC (D-12) |
| Ethernet | 96 ETH_AVDD1V8, 101 ETH_AVDD3V3 | ETH_AVDD1V8 (FB3), FEPHY_AVDD3V3 (FB1) | analog | embedded PHY | ETH_TXP/N, RXP/N, EXTR (97–100, 102) |
| USB | 24 (1.8 V), 28 USB_AVDD3V3 | AVDD1V8_USB, VCC_3V3 | analog | USB 2.0 PHY | USB_DP/DM (27/26), USB_VBUSDET (25). The VBUSDET divider ([LF] R2/R5) is fed from switched VCC5V0_SYS, so the pin never sees voltage while the SoC is unpowered (D-27). VBUSDET input threshold/max UNVERIFIED in [DS] |

Every 1.8/3.3 V-capable domain (VCCIO3–6) is tied to 3.3 V, as on [LF], so every header pin is 3.3 V logic. No 3.3 V signal goes to
a 1.8 V-only domain. [LF] LED1 on GPIO3_C6 (pin 4) sits in VCCIO7 at 1.8 V, which is why the reference work-LED is not copied (D-09).

**Software coupling (UNVERIFIED):** the shipped io-domain driver has no RV1106 entry, and the Pro/Max DTS has no io-domain node.
So Luckfox relies on the BootROM/hardware default for VCCIO3–6 at 3.3 V. Our supply wiring is identical to [LF], so we inherit the
same behaviour. Phase 8 must not add an io-domain node that sets any of VCCIO3–6 to 1.8 V.

## 4. Boot mode and strap pins (gate: boot-mode/strap pins identified)

| Pin | Name | Role at reset | Circuit (copied from [LF]) | Evidence |
|---|---|---|---|---|
| **23** | SARADC_IN0 (GPI4_C0_z) | **MASKROM/RECOVERY strap.** Held low while the SoC comes out of reset, the BootROM skips all media and waits for USB download on the OTG port (2207:110c). Released (pulled up), it boots normally. Linux also reads it as adc-keys channel 0. | 10 kΩ pull-up to VCC_1V8 (R21) + 1 nF (C44); push-button to GND through 100 Ω | [LF] "System RECOVERY Key" Key2, net RECOVERY on U1 pin 23. [SDK] `rv1106-evb.dtsi` adc-keys `io-channels = <&saradc 0>`. [CD] "hold BOOT while applying power" → 2207:110c. **That the BootROM samples SARADC_IN0 is inferred from [LF] + [CD]; a Rockchip document stating it was not found (UNVERIFIED).** |
| 66 | nPOR | Power-on reset, active low | 1 kΩ pull-up (R12) + 10 nF (C38), reset key via 100 Ω | [DS] T2-1 p.19; [LF] "Power Reset" |
| 15 / 48 | SDMMC0_CLK / FSPI_CLK | Boot-media interfaces the BootROM probes; no strap function | 22 Ω series (R16 / R15) | [DS] §1.2.2 p.6 ("SPI interface, eMMC interface, SD/MMC interface") |
| 47 | FSPI_CS0 (`_u`) | Not a strap. Its reset pull-up keeps the NAND deselected. Hardware NAND-disable link proposed in D-25 | 10 kΩ pull-up on the NAND side (new, D-25) | [SDK] pinctrl L123-126 |
| 59, 62, 63, 64, 65 | GPIO0_A1/A3/A4/A5/A6 | Not straps, but they control other blocks during reset; the reset pull matches each safe state (D-16/D-20) | see `pinmap.csv` | [DS] T2-1 suffixes; T3-3 Rpu/Rpd |

No other pin in [DS] Table 2-1 carries a boot/strap function. The datasheet has no "boot mode" pins. The media order is fixed in BootROM (§5).

## 5. BootROM media order (D-18 follow-up), **UNVERIFIED**

- [DS] §1.2.2 lists the devices (SPI, eMMC, SD/MMC; download via USB and UART) with **no order**.
- Weak evidence ([FORUM]): after firmware is flashed to NAND, it must be erased before SD boot works. That suggests **SPI NAND is tried before SD**.
- The SDK asks which medium to build for (SD_CARD or SPI_NAND). It does not document the priority.
- **Consequence for Rev A (D-24):** a factory-fresh SPI NAND is blank, so the first SD-card boot on new boards should work in either
  order. Once NAND holds firmware, SD boot needs one of: erasing the NAND (MASKROM + `rkdeveloptool`/SocToolKit), or the hardware
  NAND-disable link (D-25), which keeps FSPI_CS0N high so the BootROM sees no NAND.

## 6. Gate TP-D2 self-check

| Gate clause | How it is met | Check |
|---|---|---|
| Each pin assignment cites the datasheet or reference schematic | `source` column: every one of the 129 rows cites [DS] Table 2-1 page, plus [LF] symbol/net and/or [SDK] pinctrl line. Every new assignment also cites its D-xx | C6 (all rows), C3 (name = [DS] text verbatim), C4 (function is a real mux option of that pin) |
| No pin used twice | One row per pin. Each signal net appears on exactly one pin (only GND and supply nets repeat). Each of the 28 header signal positions maps to one pin | C1, C2, C5, C11 |
| IO voltage domains consistent (Ethernet, SDMMC, SPI NAND at the correct VCCIO) | NAND → VCCIO3 3.3 V; SD → VCCIO4 3.3 V; Ethernet → dedicated ETH_AVDD1V8/3V3 analog pins; UART → VCCIO1 3.3 V; header → 3.3 V domains only; strap → VCCIO2 1.8 V with a 1.8 V pull-up; nothing on VCCIO7. Cross-domain/unpowered-domain: no SoC pin is pulled or driven from an always-on rail (VBUSDET moved to VCC5V0_SYS, D-27); debug UART has 1 kΩ series resistors (D-30) | C7, C8, C12–C16 + §3 table |
| Boot-mode/strap pins identified | Pin 23 SARADC_IN0 = MASKROM strap (`status = USED (BOOT STRAP)`), nPOR, boot-media pins, reset-state-critical outputs | C10, C9 + §4 |

## 7. Notes carried forward
- Phase 3: PB_INT_N (60) has a reset pull-down against a 4.7 kΩ pull-up, so the node stays ≥ 2.55 V (> Vih 2.0 V). Choose the onoff controller's INT and KILL polarity to fit pins 60/63 (D-03, D-19).
- Phase 5: pin 58 GPIO0_A0 is `_z` (no internal pull) and left NC; add a 100 kΩ pull-down or test pad (D-26). Decoupling per supply pin. NAND-disable link (D-25).
- Phase 8: never mux GPIO0_A3/A4 to `pmic_sleep_m1/m0` (func 1); keep console UART2_M1 at 115200; `&usbdrd_dwc3` becomes OTG with USB_SEL control (D-05); adc-keys on SARADC 0.
- Phase 3: the USB_VBUSDET divider ([LF] R2 10 kΩ / R5 18 kΩ) hangs on **VCC5V0_SYS** after the onoff switch, never on VBUS_5V (D-27). Include its ~0.18 mA in the budget.
- Phase 5: I²C pull-ups 2.2 kΩ on HDR_I2C3_SCL/SDA (pins 85/86) and 4.7 kΩ on HDR_I2C1_SCL/SDA (pins 104/105), all to VCC_3V3 (D-29). 1 kΩ series on UART2_TX/RX, with TP9/TP10 on the SoC side (D-30).
- Phase 6 bring-up: connect the USB-UART adapter only **after** the board is powered on. If it stays attached while the board is off, the 1 kΩ limits the back-feed to about 3 mA; the RV1106 injection limit is UNVERIFIED (D-30). Accessories on the 2×20 header that have their own power can also back-power the SoC (D-31, user note).

### 7.1 Phase 8 must not inherit (Luckfox DTS nodes that conflict with this pin map, D-28)

The Pro/Max DTS includes `rv1106-luckfox-pico-pro-max-ipc.dtsi`. Pin numbers below come from pinmap.csv ([DS] Table 2-1). Group-to-pin mapping comes from `rv1106-pinctrl.dtsi`.

| Luckfox node (file, line) | What it claims | Our use of that pin | Phase 8 action |
|---|---|---|---|
| `&acodec` `pa-ctl-gpios = <&gpio1 RK_PA1>`, status okay (ipc L82-86) | GPIO1_A1 = pin 73 | header 36 (HDR_GPIO1_A1) | Remove `pa-ctl-gpios`. Disable acodec and the `acodec-sound` card (audio not fitted, D-12) |
| `dht11_sensor` (ipc L62-72, pinctrl `gpio1_pc7` L375), no status = enabled | GPIO1_C7 = pin 84 | header 35 (PWM11_M1) | Delete the node |
| `&i2c3 pinctrl-0 = <&i2c3m1_xfer &i2c3m0_xfer>` (ipc L299-301) | m0 = GPIO2_A6/A7 = pins 107/106 | header 11/7 (GPIO) | `pinctrl-0 = <&i2c3m1_xfer>` only |
| `&pwm10 = <&pwm10m1_pins &pwm10m2_pins>` (ipc L351-353) | m2 = GPIO1_D1 = pin 87 | header 10 UART3_RX | m1 only (pin 83) |
| `&pwm11 = <&pwm11m1_pins &pwm11m2_pins>` (ipc L354-356) | m2 = GPIO1_D3 = pin 85 | header 5 I2C3_SCL | m1 only (pin 84) |
| `&pwm0 = <&pwm0m1_pins>` (ipc L327-329) | GPIO1_D2 = pin 86 | header 3 I2C3_SDA | Never enable pwm0 with this group |
| `&pwm5 = <&pwm5m1_pins &pwm5m2_pins>`, `&pwm6 = <&pwm6m1 &pwm6m2>` (ipc L339-344) | m1 = GPIO2_B0/B1 = pins 105/104; m2 = GPIO1_C2/C3 = pins 93/92 | I2C1 (header 28/27); SPI0 MOSI/MISO | Never enable pwm5/pwm6 with these groups |
| `&pwm2 = <&pwm2m2_pins>`, `&pwm3 = <&pwm3m2_pins>`, `&pwm4 = <&pwm4m2_pins>` (ipc L330-338) | pins 95, 89, 94 | SPI0_CS0, UART3_TX, SPI0_CLK | Never enable pwm2/3/4 with these groups |
| `&uart0 = <&uart0m0_xfer &uart0m1_xfer>` (ipc L310-312) | m0 = GPIO0_A0/A1 = pins 58/59; m1 = pins 104/105 | pin 59 = SDMMC_PWREN (card power); I2C1 | Never enable uart0 |
| `&uart5 = <&uart5m0_xfer>` (ipc L322-324) | GPIO3_A6/A7 = pins 17/18 | SDMMC0_D3/D2 | Never enable uart5 |
| `&uart1 = <&uart1m1_xfer>` (ipc L313-315) | GPIO2_A4/A5 = pins 113/114 | header GPIO2_A4/A5 | Leave disabled unless those header pins are deliberately repurposed |
| `&i2c0 = <&i2c0m2_xfer>` (ipc L291-293) | pins 15/16 | SDMMC0_CLK/CMD | Never enable i2c0 with m2 |
| `&spi0` child `fbtft@0` (ipc L268-289, fbtft L278-288): `led-gpios` GPIO2_B0, `dc-gpios` GPIO2_B1, `reset-gpios` GPIO1_C3 | pins 105, 104, 92 | I2C1 SCL/SDA, SPI0_MISO | Delete the fbtft child; keep only `spidev@0` |
| `&i2c4` (okay; m2 = pins 5/7, alt state "conifg" = m0 GPIO2_A1/A0 = pins 110/109), camera sensor, `work_led` GPIO3_C6 (pin 4) | VCCIO7 NC pins; header GPIO2_A0/A1 through the alt state | camera not fitted (D-12) | Disable i2c4, the CSI/CIF/ISP chain and the work LED |
| Enabled as-is and safe to keep | `&sfc`, `&sdmmc`, `&gmac`, `&usbdrd_dwc3` (becomes OTG, D-05), `&saradc`/adc-keys, `fiq_debugger` (UART2_M1 115200), `&rtc` | — | Keep |

