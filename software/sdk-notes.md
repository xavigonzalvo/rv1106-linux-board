# Buildroot / SDK board configuration notes (Phase 8, Rev A)

Build steps are in `README.md`. This file explains what each change does, why, and what is not yet verified.

## Sources

Downloaded files are kept as read-only data under `design/refs/` and were never executed.

| Tag | What | URL | Local copy |
|---|---|---|---|
| [SDK] | Luckfox Pico SDK device trees (Pro/Max DTS, ipc/evb dtsi, `rv1106.dtsi`, `rv1106-pinctrl.dtsi`) | https://github.com/LuckfoxTECH/luckfox-pico/tree/main/sysdrv/source/kernel/arch/arm/boot/dts | `refs/luckfox-sdk-dts/` |
| [SDK-H] | dt-bindings headers, `rockchip-pinconf.dtsi`, `input-event-codes.h` (used only to compile the DTS on the PC) | same repo, `sysdrv/source/kernel/include/…`, `…/arch/arm/boot/dts/rockchip-pinconf.dtsi` | `refs/luckfox-sdk-dt-bindings-2026-10-29/` |
| [SDK-B] | BoardConfig files (Pro/Max SD + NAND, Pico Plus NAND) and `project/build.sh`, `sysdrv/Makefile` | https://github.com/LuckfoxTECH/luckfox-pico/tree/main/project/cfg/BoardConfig_IPC | `refs/luckfox-sdk-boardcfg-2026-10-29/` |
| [SDK-K] | Kernel 5.10.160 files: `drivers/power/reset/gpio-poweroff.c`, `drivers/firmware/psci/psci.c`, `drivers/input/keyboard/gpio_keys.c`, `arch/arm/Kconfig`, `arch/arm/mach-rockchip/Kconfig`, `luckfox_rv1106_linux_defconfig`, `Makefile` | same repo, `sysdrv/source/kernel/…` | `refs/luckfox-sdk-boardcfg-2026-10-29/sysdrv/source/kernel/` |
| [SDK-BR] | `luckfox_pico_defconfig`, `busybox.config` | same repo, `sysdrv/tools/board/buildroot/` | `refs/luckfox-sdk-boardcfg-2026-10-29/sysdrv/tools/board/buildroot/` |
| [BB] | BusyBox `util-linux/acpid.c`, tag 1_36_0 and master (the same apart from a size comment) | https://github.com/mirror/busybox/blob/1_36_0/util-linux/acpid.c | `refs/busybox-acpid-src-2026-10-29/` |

## 1. Device tree (D-92)

`rv1106g-custom-reva.dts` uses the same include chain as the Pro/Max ([SDK] `rv1106g-luckfox-pico-pro-max.dts` L8-10):
`rv1106.dtsi` → `rv1106-evb.dtsi` → board file. The only change is the board file. `rv1106-custom-reva.dtsi` replaces
`rv1106-luckfox-pico-pro-max-ipc.dtsi` and copies only the parts this board has:
* the `chosen` bootargs (ipc L9);
* the fixed regulators `vcc_1v8`, `vcc_3v3`, `vdd_arm` (ipc L25-51) and `cpu-supply` (ipc L88-90);
* `&saradc` with `vref-supply` (ipc L93-96);
* `&sfc`, `&gmac`, the USB nodes, `&rtc` (pro-max.dts L40-49, L72-95, L132-135);
* the header peripheral pin groups (ipc L268-356), limited to the groups `pinmap.csv` uses.

Everything in research.md §7.1 / D-28 is left out:
* acodec `pa-ctl-gpios` and the `acodec-sound` card;
* `dht11_sensor` and the fbtft child;
* the `i2c3m0`, `pwm10m2`, `pwm11m2` and `spi0m0_cs1` groups;
* uart0, uart1, uart4, uart5, i2c0, i2c4 and pwm0–7;
* the camera chain and the work LED on GPIO3_C6.

| Node | Board setting | Pin(s) / net (pinmap.csv) | Source / reason |
|---|---|---|---|
| `gpio-keys/power-key` | KEY_POWER, active-low, 20 ms debounce, wakeup | 60 GPIO0_A2 PB_INT_N, bias off (4.7 k external) | D-19, power.md §6.2 |
| `gpio-poweroff` | active-high, 3000 ms timeout | 63 GPIO0_A4 PWR_KILL, pull-down | D-03/D-20, power.md §6.1 |
| `leds/led-status` | heartbeat, active-low | 62 GPIO0_A3 LED_STATUS | D-20, D-69 |
| `leds/led-eth` | netdev (set by `S15board`), active-high | 74 GPIO1_A2 LED_ETH | D-21 |
| `sdmmc-pwren-hog` | output low (card powered) | 59 GPIO0_A1 SDMMC_PWREN | D-13, D-20 |
| `&sdmmc` | 4-bit, `no-1-8-v`, removable with CD, 50 MHz | 11–18 SDMMC0 | pro-max.dts L52-70; D-95 |
| `&sfc` + `flash@0` spi-nand | 75 MHz, quad RX | 39–48 FSPI (mux left to the loader, as [SDK]) | pro-max.dts L40-49 |
| `&usbdrd_dwc3` | `dr_mode = "host"` (default) / `"peripheral"` (gadget .dts) | 26/27 USB_DP/DM | D-05, D-96 |
| `&i2c3` / `&i2c1` | 100 kHz, `i2c3m1_xfer` / `i2c1m1_xfer` | 85/86, 104/105 | D-22, D-28, D-29 |
| `&uart3` | `uart3m1_xfer` | 87/89 | D-22 |
| `&spi0` + `spidev@0` | `spi0m0_pins` + `spi0m0_cs0` (no cs1: pin 86 is I2C3_SDA) | 92–95 | ipc L268-276, D-28 |
| `&pwm8`…`&pwm11` | m1 groups | 91, 90, 83, 84 | D-22, D-28 |
| `&saradc` + evb `adc-keys` | RECOVERY key on channel 0 (reports KEY_VOLUMEUP, as on Luckfox) | 23 SARADC_IN0 | evb L9-27, D-23 |
| `fiq_debugger` (evb) | console ttyFIQ0 = UART2, 115200 | 79/80 UART2_M1 | `rv1106.dtsi` L225-233, D-15 |
| `gpio-line-names` | pinmap.csv net names on all 160 lines | — | `gpioinfo` shows schematic names |

The following are deliberately not in the DTS:
* No io-domain node (research.md §3: VCCIO3–6 are wired to 3.3 V, and Luckfox has none either).
* No `pmicm0`/`pmicm1` pin groups (D-20).
* No `restart-poweroff`. The evb.dtsi adds it at L29-31 and the board file deletes it, because it would turn poweroff into a reboot (D-93).

**D-15 confirmed:** the console is UART2_M1. `rv1106.dtsi` gives `fiq-debugger` `rockchip,serial-id = <2>` at 115200, and
`uart2` uses `uart2m1_xfer`. In `rv1106-pinctrl.dtsi` that group is GPIO1_B2 (TX) and GPIO1_B3 (RX), which are pins 79 and 80.

## 2. CPU frequency (D-94; answers the D-06 Phase 8 question)

VDD_ARM is the fixed VDD_0V9 rail (no DVFS, D-06). At the SoC it is at least 0.588 V × (1 + 49.9/100) − 6.6 mV =
**0.875 V**. Sources: `power_rails.csv` VFB min and divider, and `layout/power_paths.csv` plane drop.

The [SDK] OPP table (`rv1106.dtsi` L112-173) asks for 850 mV up to 1200 MHz and 875–1000 mV for 1296–1608 MHz. The
board DTS deletes 1296, 1416, 1512 and 1608 MHz, so the top speed is **1.2 GHz**. Every OPP left then has a target voltage
at or below the rail. 1296 MHz needs 875 mV against a 0.8748 V worst case, so it is removed. The 1.2 GHz figure is the
project's stated CPU speed (PLAN.md). [DS] r1.8 gives no CPU frequency (checked: §1.2.1 p.6 has none), so that speed is
**UNVERIFIED** against the datasheet. Below 10 °C the Rockchip OPP code asks for ≥ 0.90 V (`rockchip,low-temp-min-volt`).
The fixed regulator reports 0.90 V, so the kernel accepts it, but the real rail can be 0.875–0.918 V. A cold board is
therefore marginal at 1.2 GHz (**UNVERIFIED**, see open questions).

## 3. Kernel configuration

The fragment `custom-reva.config` is merged after `luckfox_rv1106_linux_defconfig`. It adds:
* `CONFIG_POWER_RESET_GPIO=y`. This is the only option R4 needs that the Luckfox defconfig lacks.
* `CONFIG_LEDS_TRIGGER_HEARTBEAT=y` and `CONFIG_LEDS_TRIGGER_NETDEV=y`.

It also repeats a few options the defconfig already sets (`KEYBOARD_GPIO`, `INPUT_EVDEV`, `GPIO_SYSFS`, `POWER_RESET`,
`LEDS_GPIO`), so the board does not depend on them silently. No U-Boot change: the storage, console and DDR are the same
as the Pro/Max, so `luckfox_rv1106_uboot_defconfig` and its fragments (`rk-emmc.config` for SD, `rk-sfc.config` for NAND)
are kept.

## 4. BoardConfig files

Both files are copies of the Pro/Max files. Every changed line is marked `# CUSTOM-REVA:`. The changes:
* `RK_KERNEL_DTS=rv1106g-custom-reva.dts`.
* `RK_KERNEL_DEFCONFIG_FRAGMENT=custom-reva.config`.
* `overlay-custom-reva` added to `RK_POST_OVERLAY`.
* NAND only: the Pro/Max partition table (256 MB, ends at 255.5 MiB) is replaced by the **Luckfox Pico Plus 128 MB table**
  `256K(env),256K@256K(idblock),512K(uboot),4M(boot),30M(oem),6M(userdata),85M(rootfs)`. It ends at 126 MiB on the
  128 MiB W25N01KV (D-52, D-97). UBIFS and bad-block headroom is the same as on the Pico Plus.

These Luckfox settings are kept as they are:
* the camera app (`RK_APP_TYPE=RKIPC_RV1106`, IQ files);
* `RK_ENABLE_WIFI` and the WiFi overlay.

With no camera fitted, the camera app logs errors and exits. Removing it is optional cleanup, not needed to boot.

## 5. R4 — the complete shutdown path (D-93)

| # | Stage | What happens | Where it is set / source |
|---|---|---|---|
| 1 | Button | SW_PWR [SW1] short press while on. After tDB,OFF the LTC2954 pulls INT low; PB_INT_N reads low. INT does not touch EN, so power stays on | power.md §6.2; [LTC] p.9/p.11 |
| 2 | Kernel input | `gpio-keys` on GPIO0_A2, active-low, emits EV_KEY KEY_POWER (116) value 1, then 0 on release | DTS `gpio-keys/power-key`; `CONFIG_KEYBOARD_GPIO=y` |
| 3 | User space | BusyBox `acpid` reads `/dev/input/event*`. KEY_POWER press maps to `button/power PWRF 00000080`. `/etc/acpid.conf` maps `PWRF` to `PWRF/00000080`, which runs `/etc/acpi/PWRF/00000080`. That script execs `/sbin/poweroff`. Fallback if acpid is not built: `board-powerkeyd` (python3), same action | [BB] acpid.c L103 (event table), L113-116 (actions), L145-163 (spawn), L299 `xchdir(opt_dir)`; `S50powerkey` |
| 4 | init | BusyBox init runs the `::shutdown` actions (rcK stops services, `umount -a -r`), then `reboot(RB_POWER_OFF)` | Buildroot BusyBox inittab (not re-checked here, **UNVERIFIED** for the Luckfox overlay `overlay-luckfox-buildroot-init`) |
| 5 | Kernel | `kernel_power_off()` calls `pm_power_off` = `gpio_poweroff_do_poweroff`. It drives PWR_KILL high for 100 ms, then low for 100 ms, then high, then waits 3 s | [SDK-K] gpio-poweroff.c L28-47, L77 |
| 6 | Hardware | PWR_KILL high turns Q_KILL [Q3] on. LTC2954 KILL goes < 0.57 V and EN is released within 30 µs. Q_EN turns off and R_GS turns Q_PWR off (≤ 104 ms). Every rail falls. PB is ignored for 200–325 ms | power.md §6.1–6.2; [LTC] pp.2-3 |

Why `gpio-poweroff` can bind:
* The driver refuses with -EBUSY when `pm_power_off` is already set ([SDK-K] gpio-poweroff.c L54-60).
* Two candidates exist. `restart-poweroff` from evb.dtsi is deleted in the board DTS. PSCI would set it in `psci_0_2_set_functions()` (psci.c L481), but `rv1106.dtsi` has a `psci` node only. `CONFIG_ARM_PSCI` is not in `luckfox_rv1106_linux_defconfig`, and in `arch/arm/Kconfig` only `ARCH_VIRT` (L603) and `XEN` (L1647) select it.
* So `pm_power_off` should be free. This is an **inference from the config files, not a test**. `S15board` reports at every boot whether the driver bound.
* If it did not, apply the optional patch `patches/0001…` (README step 9). It takes over `pm_power_off` when the DTS property `custom,override-pm-power-off` is present, and the board DTS already has that property.

Other cases:
* **Long press ≥ 8 s:** the LTC2954 cuts power by itself, whatever the software state.
* **`reboot`:** does not touch PWR_KILL. The pin returns to its reset pull-down, so power stays on (D-20).
* **systemd rootfs (not the default):** `alt-systemd/` has `HandlePowerKey=poweroff` and a udev rule that tags the gpio-keys device `power-switch`. Steps 4–6 are the same.

## 6. USB port (D-96)

The single OTG port sits behind the TS3USB221A mux (D-05). The kernel role comes from the DTS:
* `rv1106g-custom-reva.dts` (default): `dr_mode = "host"`, for R3.
* `-gadget.dts`: `"peripheral"`, as on the Luckfox.

USB_SEL and USBA_VBUS_EN are not claimed by the kernel. They stay at their reset pull-downs (USB-C, VBUS off) until
`S15board` runs `board-usb $USB_MODE` from `/etc/default/board` (default `auto` = follow `dr_mode`). In host mode the script
sets SEL high first, then VBUS. Any other mode turns VBUS off first, then sets SEL low. Leaving the two GPIOs to user space
means:
* the bring-up can switch VBUS and the mux by hand (bringup.md step 11);
* `USB_MODE=off` keeps the 500 mA USB-A allowance unused on a weak supply (D-36).

MASKROM never depends on Linux: the BootROM runs with the pins at reset, so the mux is on USB-C.

## 7. microSD (D-95)

The [SDK] Pro/Max node marks the slot `non-removable` with SDIO capabilities (`cap-sdio-irq`, `supports-sdio`). It also
misspells `max-freqency` (pro-max.dts L54), so the 200 MHz limit from `rv1106.dtsi` applies there. This board has a real
card-detect switch on SDMMC0_DET (pin 11, `sdmmc0_det` group). The board DTS therefore makes the slot a removable SD-only
slot (`no-sdio`, `no-mmc`) with card detect, and spells `max-frequency = <50000000>` correctly. `no-1-8-v` stays, so the
slot never switches to UHS, because VCCIO4 is fixed at 3.3 V (D-13). Bring-up step 5.9 measures the card-detect polarity.
If it reads inverted, add `cd-inverted;` to `&sdmmc`. If card detect misbehaves, the fallback is the Luckfox setting
`non-removable;`.

## 8. Open items (software)

| Item | Status |
|---|---|
| `gpio-poweroff` binds on the real kernel (no earlier `pm_power_off`) | Inferred from the defconfig and Kconfig; confirm with `S15board` at H3. Patch 0001 is ready |
| Luckfox inittab/overlay keeps the BusyBox `::shutdown` sequence | **UNVERIFIED** (overlay not downloaded); confirm at bring-up step 9 |
| SD/NAND flashing tools and commands | **UNVERIFIED**; follow the Luckfox wiki for the Pro/Max |
| 1.2 GHz at < 10 °C with a fixed 0.875–0.918 V rail | **UNVERIFIED**; lower to 1104 MHz if cold boots fail |
| Kernel builds an unlisted DTS from `RK_KERNEL_DTS` | Expected from `sysdrv/Makefile` L246; the README adds a `dtb-y` line anyway |
