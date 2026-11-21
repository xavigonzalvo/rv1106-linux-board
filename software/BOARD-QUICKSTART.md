# Rev A board — quickstart (what works today and how to use it)

First bring-up of board #1 on 2026-11-20: **it boots Linux and is on the network.** This page holds everything
needed to repeat it (board #2, a re-flash) and to use the board from a Mac. Full bench procedure: `design/bringup.md`;
results log: `design/LOG.md` (entry 2026-11-20).

## 1. What was tested on board #1

| Check | Result |
|---|---|
| No-power shorts check, black lead on TP19 (GND) | TP13 (5 V sys) 166 Ω, TP2 (3.3 V) 150 Ω, TP4 (0.9 V core) 60 Ω — no shorts |
| USB-C from the MacBook, press SW1 (power, right side) | PWR LED on; Mac sees Rockchip `2207:110c` (MASKROM) at 480 Mb/s |
| Flash Luckfox Pico Pro Max image to the on-board SPI NAND | all 7 partitions written, boots from NAND |
| Linux | 5.10.160 (Luckfox Buildroot 2025-06), 181 MB RAM free to Linux, SoC 37–41 °C idle |
| USB-C under Linux | gadget `2207:0019` "rk3xxx": RNDIS + ADB; `adb shell` works |
| Ethernet | RK630 PHY, 100 Mb/s full duplex, DHCP lease, internet ping 0 % loss |
| STAT and ETH LEDs | work when driven from sysfs GPIO (§4); the Luckfox image leaves them dark |
| SW1 hold | hard-off after a long hold (8–22 s by design); short press turns the board on |

Not tested yet: booting from microSD (as a data card it works, see LOG.md 2026-11-20), USB-A host, 2×20 header, debug UART (J6), RTC crystal, power button clean shutdown,
board #2, our own image (`software/README.md`).

## 2. Tools on the Mac

* **adb** — `brew install android-platform-tools` (already installed: `/opt/homebrew/bin/adb`).
* **rkdeveloptool** — Rockchip flashing tool, not in Homebrew. Built from the official source
  (github.com/rockchip-linux/rkdeveloptool, commit 304f073) into `software/tools/rkdeveloptool/`:
  ```sh
  brew install libusb pkgconf autoconf automake
  cd software/tools/rkdeveloptool && ./autogen.sh && ./configure
  make -j8 CXXFLAGS="-g -O2 -Wno-vla-cxx-extension"   # Apple clang rejects two VLAs in main.cpp otherwise
  ```
* **Go** (for programs on the board) — `/opt/homebrew/bin/go`.

## 3. Flash the board (Luckfox Pico Pro Max image)

Image: `thirdparty/luckfox-image/Luckfox_Pico_Pro_Max_Flash_250607/` (from Luckfox's official Google Drive,
folder Luckfox Pico → firmware → buildroot → Flash; wiki.luckfox.com/Luckfox-Pico-RV1106/Downloads).
Our board copies the Pro/Max closely enough that this image runs unchanged.

1. USB-C cable from the Mac to the board, press SW1. A blank board comes up in MASKROM (`2207:110c`).
   A board that already runs Linux: `adb shell reboot loader`, or hold SW3 (recovery, top edge) while pressing SW1.
2. ```sh
   sh software/tools/flash-luckfox.sh thirdparty/luckfox-image/Luckfox_Pico_Pro_Max_Flash_250607
   ```
   It runs `rkdeveloptool db download.bin`, then `wl` env/idblock/uboot/boot/oem/userdata/rootfs at sectors
   0x0/0x200/0x400/0x800/0x2800/0x11800/0x16800 (the `mtdparts` in the image's `.env.txt`), then `rd`.
3. **Linux needs 30–60 s to boot.** Then `adb devices` lists it. (The first check right after the flash found
   nothing on USB; a minute later the gadget was there.)

The Luckfox image does not touch PWR_KILL (GPIO0_A4), so the board stays on.

## 4. Using the board

**Log in**
* Over USB: `adb shell` (root shell, no password).
* Over Ethernet: `ssh root@<ip>`, password `luckfox`. The router gave 192.168.1.148 on the first boot; check with
  `adb shell ifconfig eth0`. If eth0 has no address: `adb shell udhcpc -i eth0`.
* The image also puts `usb0` at 172.32.0.93 (RNDIS), but macOS has no RNDIS driver, so use adb or Ethernet.

**LEDs** (sysfs GPIO; Linux GPIO number = bank × 32 + pin)

| LED | SoC pin | Linux GPIO | On | Off |
|---|---|---|---|---|
| STAT (middle) | GPIO0_A3, pin 62 | 3 | write 0 (active-low) | write 1 |
| ETH (right) | GPIO1_A2, pin 74 | 34 | write 1 (active-high) | write 0 |

```sh
cd /sys/class/gpio
echo 3 > export; echo out > gpio3/direction; echo 0 > gpio3/value      # STAT on
echo 34 > export; echo out > gpio34/direction; echo 1 > gpio34/value   # ETH on
# heartbeat on STAT
while true; do echo 0 > gpio3/value; sleep 0.1; echo 1 > gpio3/value; sleep 0.9; done &
# ETH as a network-activity light
p=0; while true; do n=$(cat /sys/class/net/eth0/statistics/rx_packets); [ "$n" != "$p" ] && v=1 || v=0; echo $v > gpio34/value; p=$n; sleep 0.1; done &
kill %1 %2      # stop the loops
```
**Never drive GPIO 4 (GPIO0_A4, PWR_KILL) high:** it cuts the board's power at once (that is how our own image
switches off after `poweroff`). GPIO settings reset on reboot.

## 5. Your own programs: the hello-http example

`software/examples/hello-http/main.go` is a small Go web server: `/` shows uptime and SoC temperature,
`/stat/on` and `/stat/off` switch the STAT LED. Go cross-compiles to a single static ARMv7 binary that needs
nothing from the board's uClibc.

```sh
cd software/examples/hello-http
CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -ldflags="-s -w" -o hello-http .
adb shell killall hello-http; adb push hello-http /usr/bin/
adb shell 'nohup /usr/bin/hello-http >/tmp/hello-http.log 2>&1 &'
curl http://<board-ip>:8080/
```
First run answered: `Hello from the RV1106 Rev A board! uptime 356.29 s, SoC 41.0 C`.
It does not start by itself after a reboot; add an `/etc/init.d/S99hello` script for that.
Root filesystem: ~26 MB free on a fresh flash, 18 MB on board #1 with ai-detect and tiny-llm installed (2026-11-21); `/userdata` 4.5 MB. Put big files on the microSD.

## 5b. AI demo: object detection on the NPU (ai-detect)

YOLOv5 on the RV1106 NPU with a web UI on port 8080; starts at boot. Needs the microSD (model lives there).
Details, timings and lessons: `software/examples/ai-detect/README.md`.

```sh
sh software/examples/ai-detect/deploy.sh      # build (Docker + Go), install, start
```
Open http://localhost:8080 (USB, via `adb forward tcp:8080 tcp:8080`) or http://<board-ip>:8080 on the LAN.
Board #1: bus test photo → 4 people + bus, 165 ms per photo (NPU 81 ms).

## 5c. Tiny LLM: a 135M-parameter chat model on the CPU (tiny-llm)

SmolLM2-135M-Instruct (Hugging Face, Llama architecture), int8, on the Cortex-A7. Needs the microSD (model 143 MB).
Details, memory budget and checks: `software/examples/tiny-llm/README.md`.

```sh
sh software/examples/tiny-llm/deploy.sh      # download + convert model (once), build, install
adb shell                                    # then on the board: chat   (/quit to leave)
```
Board #1: replies at 2.5 tok/s, first answer ~20 s after start, 147 MB RAM.

## 6. Next

* Our own image (`software/README.md`): STAT/ETH LEDs, USB-A host, the power button's clean shutdown and
  PWR_KILL. Needs the Luckfox SDK built on Linux (a Docker container on the Mac works).
* The rest of `design/bringup.md` steps 8–14 (microSD, USB-A, header, UART, load) and board #2 (same flash command).
