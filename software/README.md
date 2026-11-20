# Software for the RV1106G3 custom board, Rev A (Phase 8)

This folder turns the Luckfox Pico SDK into a Linux image for this board. The board copies the Luckfox Pico Pro/Max
almost exactly: same SoC, same DDR, the same storage pins and the same debug UART. So the Luckfox U-Boot, kernel and
Buildroot are used unchanged. Only these pieces are new: the board device tree, one kernel config fragment, one BusyBox
option, and a rootfs overlay for the power button, the LEDs and the USB port.

* Configuration notes, the shutdown path behind the power button (R4) and every deviation from Luckfox: `sdk-notes.md`.
* Decisions D-92 to D-98: `design/decisions.md`.

## What is here

| Path | What it is | Goes to (in the SDK tree) |
|---|---|---|
| `sdk/sysdrv/source/kernel/arch/arm/boot/dts/rv1106-custom-reva.dtsi` | Board device tree body. Derived from the Luckfox Pro/Max DTS | same path |
| `sdk/.../dts/rv1106g-custom-reva.dts` | **Default** build: USB-A host (R3) | same path |
| `sdk/.../dts/rv1106g-custom-reva-gadget.dts` | Alternative: USB-C device/gadget, the way the Luckfox works | same path |
| `sdk/sysdrv/source/kernel/arch/arm/configs/custom-reva.config` | Kernel config fragment: `gpio-poweroff`, LED triggers | same path |
| `sdk/sysdrv/tools/board/buildroot/busybox-custom-reva.fragment` | BusyBox `acpid` (the power-key daemon) | merge into `busybox.config` (step 4) |
| `sdk/project/cfg/BoardConfig_IPC/BoardConfig-SD_CARD-…-RV1106_Custom_RevA-IPC.mk` | SD-card build (bring-up) | same path |
| `sdk/project/cfg/BoardConfig_IPC/BoardConfig-SPI_NAND-…-RV1106_Custom_RevA-IPC.mk` | SPI NAND build, 128 MB partition table | same path |
| `sdk/project/cfg/BoardConfig_IPC/overlay/overlay-custom-reva/` | Rootfs overlay: `S15board`, `S50powerkey`, `board-usb`, `board-powerkeyd`, acpid files | same path |
| `patches/0001-gpio-poweroff-optional-takeover-of-pm_power_off.patch` | **Optional** kernel patch. Use it only if the boot log asks for it (step 9) | kernel tree, `patch -p1` |
| `alt-systemd/` | Only for a systemd rootfs (not the Luckfox default) | — |
| `tools/check_software.py` | Gate TP-D8 checker: compiles the DTS and checks it against `design/pinmap.csv` | run on the PC |
| `out/` | DTBs and decompiled DTS from the last checker run (for review only) | — |

## 0. Check the files first (any PC with `dtc` and a C compiler)

```sh
design/.venv/bin/python -I software/tools/check_software.py --mutations --out software/out
```
Expected result: `check_software: 51 pass, 0 fail`. The checker does these things:
* It compiles both DTS variants and the Luckfox reference DTS (C preprocessor + `dtc` 1.8.1), using SDK headers saved under
  `design/refs/`.
* It checks every pin the device tree claims against `pinmap.csv`.
* It tests the power-key fallback daemon and `board-usb` on fake input.
* It confirms that 11 deliberate mistakes are caught.

## 1. Build host and SDK

The Luckfox SDK builds on an x86-64 Linux PC. Luckfox recommends Ubuntu 22.04; this was not checked here (**UNVERIFIED**).
```sh
git clone https://github.com/LuckfoxTECH/luckfox-pico.git
cd luckfox-pico
cd tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/ && source env_install_toolchain.sh && cd -
```
(`project/build.sh` prints this toolchain step when the compiler is missing. Toolchain name: `RK_TOOLCHAIN_CROSS` in the
BoardConfig.)

## 2. Copy this board into the SDK

```sh
cp -rv /path/to/project/software/sdk/. luckfox-pico/
# optional, so a plain "make dtbs" also builds it:
echo 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rv1106g-custom-reva.dtb rv1106g-custom-reva-gadget.dtb' \
  >> luckfox-pico/sysdrv/source/kernel/arch/arm/boot/dts/Makefile
```
The SDK build makes the DTB from `RK_KERNEL_DTS` (`sysdrv/Makefile` L57-58, L246). It merges the kernel fragment through
`RK_KERNEL_DEFCONFIG_FRAGMENT` (`sysdrv/Makefile` L64, L490). Both are set in our BoardConfig files.

## 3. Pick the board

The `./build.sh lunch` menu only lists Luckfox boards (`project/build.sh` L151-159). Do by hand what lunch does
(L368 `ln -rfs … $BOARD_CONFIG`, with `BOARD_CONFIG=.BoardConfig.mk`, L27):
```sh
cd luckfox-pico
ln -rfs project/cfg/BoardConfig_IPC/BoardConfig-SD_CARD-Buildroot-RV1106_Custom_RevA-IPC.mk .BoardConfig.mk
```
Use the `SPI_NAND` file for the on-board NAND image (step 8). For the USB-C gadget variant, change `RK_KERNEL_DTS` in that
file to `rv1106g-custom-reva-gadget.dts`.

## 4. Turn on BusyBox acpid (power key) before the first build

The Luckfox `busybox.config` has `# CONFIG_ACPID is not set`. It is copied into Buildroot only when Buildroot is first
unpacked (`sysdrv/Makefile` L608-619). Change it before the first build:
```sh
sed -i 's/^# CONFIG_ACPID is not set/CONFIG_ACPID=y/; s/^# CONFIG_FEATURE_ACPID_COMPAT is not set/CONFIG_FEATURE_ACPID_COMPAT=y/' \
  sysdrv/tools/board/buildroot/busybox.config
```
If Buildroot is already unpacked, make the same change in
`sysdrv/source/buildroot/buildroot-2023.02.6/package/busybox/busybox.config`, then run `make busybox-dirclean` in that
Buildroot directory. You can skip this step: `S50powerkey` then uses the python3 fallback `board-powerkeyd` (python3 is in
`luckfox_pico_defconfig`).

## 5. Build

```sh
./build.sh            # = build_allsave: U-Boot, kernel + DTB, Buildroot rootfs, overlays, images
```
The images land in `output/image/` (`project/build.sh` L59). The overlay `overlay-custom-reva` is copied over the rootfs by
`post_overlay` (L2487-2499), after the Luckfox overlays.

## 6. Write the microSD card (bring-up boot, R5, R6)

Write `output/image/` to the card with the Luckfox tool for the SD-card build. Luckfox documents SocToolKit on Windows and
a block-device script on Linux; the tool name and options were not checked here (**UNVERIFIED**). Use the Luckfox wiki
"burn image" page for the Pro/Max SD-card image: the image layout is the same as the Pro/Max, and only the files inside
differ.

## 7. First boot (bringup.md step 8 onward)

* Console on J_UART [J6], 115200 8N1 (`fiq-debugger`, `rockchip,serial-id = <2>`, [SDK] `rv1106.dtsi` L225-233).
* At the shell, check:
  * `dmesg | grep -i poweroff`: no "pm_power_off function already registered".
  * `S15board` prints `gpio-poweroff bound`.
  * `cat /sys/kernel/debug/gpio` (or `gpioinfo`) shows the schematic net names.
* USB: `board-usb status`. Bring-up step 11 wants the port under manual control. Before that step, set `USB_MODE=off` in
  `/etc/default/board` and reboot. Then:
  ```sh
  board-usb vbus on      # step 11.1: USB-A VBUS only
  board-usb sel usba     # step 11.3: mux to USB-A
  board-usb host         # normal use (also what USB_MODE=auto does with the default DTS)
  ```
* Ethernet LED: `S15board` sets the `netdev` trigger on `eth0`. Status LED: heartbeat.

## 8. On-board SPI NAND (R6, bringup.md step 12)

Run steps 3 and 5 again with the `SPI_NAND` BoardConfig. The partition table is the Luckfox Pico Plus 128 MB table
(126 MiB used). Flash it in MASKROM: hold SW_RECOV [SW3] and press SW_PWR [SW1], then use the Luckfox `rkdeveloptool` /
SocToolKit flow for SPI NAND (**UNVERIFIED** commands, see the Luckfox wiki). The BootROM may prefer NAND over SD once the
NAND holds an image (D-24). To boot from SD again, erase the NAND or remove R_NANDDIS [R55] (D-25).

## 9. If `poweroff` halts but the board stays on

The kernel's `gpio-poweroff` driver refuses to load if another driver already registered `pm_power_off`
(`gpio-poweroff.c` L54-60). The Luckfox defconfig does not enable `CONFIG_ARM_PSCI`, and the board DTS deletes the
evb's `restart-poweroff`, so this should not happen. If the log still shows that message:
```sh
cd luckfox-pico/sysdrv/source/kernel && patch -p1 < /path/to/project/software/patches/0001-gpio-poweroff-optional-takeover-of-pm_power_off.patch
```
and rebuild. The DTS already contains the property `custom,override-pm-power-off` that the patch reads. Until then the
hard-off (hold SW_PWR ≥ 8 s) always works.

## 10. Checklist for the bench (R4, bringup.md step 9)

1. Short press SW_PWR while Linux runs. The console logs `POWER button pressed: clean shutdown`, then the shutdown, then
   power off. TP28 (PWR_KILL) pulses high and TP13 (VCC5V0_SYS) falls.
2. Hold SW_PWR ≥ 8 s: power goes off at 2.66–7.02 s, whatever Linux is doing.
3. `reboot`: power stays on.
4. Unplug and plug in the cable: the board stays off until you press the button.

## Cross-compiling for the board (Docker)

Programs for the board (C/C++) are built on the Mac in a Docker container (`linux-board-sdk`, Ubuntu 22.04,
`linux/amd64`, runs under Docker Desktop on Apple silicon). The compiler is the Rockchip toolchain
`arm-rockchip830-linux-uclibcgnueabihf` (GCC 8.3.0) from the Luckfox SDK. It targets the board's uClibc 1.0.31
(`/lib/ld-uClibc.so.0`), armv7-a, hard-float.

The toolchain is **not inside the image**. `build.sh` mounts it read-only from `thirdparty/luckfox-toolchain/` at
`/opt/toolchain`. The image holds only the build tools (make, cmake, ninja, binutils) and is 78.5 MB.

Files: `software/docker/Dockerfile`, `software/docker/build.sh`, `software/docker/toolchain-rv1106.cmake`.

**One-time setup** (from the project root):
```sh
software/docker/build.sh fetch-toolchain   # sparse clone of only tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf
                                           # from github.com/LuckfoxTECH/luckfox-pico: 72 MiB download, 333 MB on disk
software/docker/build.sh image             # docker build --platform linux/amd64 -t linux-board-sdk software/docker (~35 s)
```

**Build anything.** `build.sh <command>` mounts the project root at `/work` and runs the command in the
container's copy of your current directory. The toolchain is on `PATH`. `CC`, `CXX`, `CROSS_COMPILE` are set.
```sh
software/docker/build.sh make -C software/examples/hello-c            # ~2 s
software/docker/build.sh cmake -S <dir> -B <dir>/build -DCMAKE_TOOLCHAIN_FILE=/opt/toolchain-rv1106.cmake
software/docker/build.sh cmake --build <dir>/build
software/docker/build.sh                                               # interactive shell
```

**Run it on the board**:
```sh
adb push software/examples/hello-c/hello-c /tmp/
adb shell /tmp/hello-c
```
Output on board #1 (2026-11-20): `Hello from C++ on the RV1106 board`, `release 5.10.160`, `machine armv7l`,
`libc uClibc 1.0.31`, exceptions work. The binary needs `libstdc++.so.6`, `libgcc_s.so.1`, `libc.so.0`. All three
are on the board.

**Where binaries can run**: `/tmp` (tmpfs, 90 MB, lost on reboot), the root filesystem (`/usr/bin`, ~26 MB free) and `/userdata`
(4.5 MB). **Not `/mnt/sdcard`**: the microSD is mounted vfat with `fmask=0133`, so no file has the x bit. `chmod`
does nothing there, and running a file gives `Permission denied` (exit 126). Running it through the loader does not
work either: `/lib/ld-uClibc.so.0 file` prints "Standalone execution is not enabled". Copy the binary to `/tmp`
first. Remounting the card with `fmask=0022` should fix this but was not tested (**UNVERIFIED**).

**NPU runtime (librknnmrt)**: a copy of the board's `/oem/usr/lib/librknnmrt.so` is in `thirdparty/board-libs/`
(`adb pull`, md5 `5118caecec7f4da43e1b74029c5cebce`). It matches the toolchain: ELF32 ARM, EABI5 hard-float,
`Tag_ABI_VFP_args: VFP registers`, and it needs only `libc.so.0`. A test program linked with
`-Lthirdparty/board-libs -lrknnmrt -Wl,--no-allow-shlib-undefined` links: all 60 libc symbols the library imports
are in the toolchain's uClibc. The program also loads and runs on the board. Under `adb shell`, `LD_LIBRARY_PATH`
already contains `/oem/usr/lib`. The headers (`rknn_api.h`) are not in this toolchain; they come from
github.com/airockchip/rknn-toolkit2 (`rknpu2/runtime/Linux/librknn_api/include`).
