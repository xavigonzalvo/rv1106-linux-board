#!/bin/sh
# Flash a Luckfox Pico Pro Max SPI NAND image onto the Rev A board over USB-C (macOS or Linux).
#
# Usage:  sh software/tools/flash-luckfox.sh <image-folder> [path-to-rkdeveloptool]
#   <image-folder>  unpacked Luckfox_Pico_Pro_Max_Flash_*.zip (has download.bin, env.img, ... rootfs.img)
#   rkdeveloptool   default: software/tools/rkdeveloptool/rkdeveloptool (see BOARD-QUICKSTART.md §2 to build it)
#
# The board must be in MASKROM (USB 2207:110c): a blank board is, after pressing SW1.
# A board that already boots Linux: run `adb shell reboot loader`, or hold SW3 (recovery) while pressing SW1.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
IMG=${1:?usage: flash-luckfox.sh <image-folder> [rkdeveloptool]}
RK=${2:-$HERE/rkdeveloptool/rkdeveloptool}

echo "== board in MASKROM / loader mode?"
"$RK" ld

cd "$IMG"
echo "== loading the RAM loader"
"$RK" db download.bin
sleep 1
# SPI NAND layout from the image's .env.txt (mtdparts); offsets in 512-byte sectors
echo "== writing partitions"
"$RK" wl 0x0     env.img
"$RK" wl 0x200   idblock.img
"$RK" wl 0x400   uboot.img
"$RK" wl 0x800   boot.img
"$RK" wl 0x2800  oem.img
"$RK" wl 0x11800 userdata.img
"$RK" wl 0x16800 rootfs.img
echo "== rebooting the board"
"$RK" rd
echo "== done (Linux takes ~30-60 s; then 'adb devices' lists it)"
