# RV1106 board, Rev A: release

Everything needed to order and build the board and its case, in one place. Rebuild this folder with
`release/make_release.sh`. It copies from the sources, and `SHA256SUMS` lists every file.

| Folder | Contents | Source |
|---|---|---|
| `board/` | `rv1106-reva-jlc-upload.zip` (Gerbers + drill, 15 files), `jlc-bom.csv` (63 parts), `jlc-cpl.csv` (193 placements) | `design/pcb/fab/` |
| `board/docs/` | `order-notes.md` (every JLCPCB order option and why), CPL rotations, not-assembled list, IPC-D-356 netlist, fab drawing, assembly drawings, 3D renders, `check_fab.txt` (53 PASS / 0 FAIL) | `design/pcb/fab/` |
| `case/` | tray and lid STLs, with and without the V-cut rails, plus the OpenSCAD source | `case/` |
| `software/` | device trees `rv1106g-custom-reva.dtb` and `-gadget.dtb` | `software/out/` |

## 1. Order the board (JLCPCB)

1. **PCB:** upload `board/rv1106-reva-jlc-upload.zip`.
2. **Assembly:** upload `board/jlc-bom.csv` and `board/jlc-cpl.csv`.
3. **Options:** set them as listed in `board/docs/order-notes.md` §2. In short:
   - 4 layers, panel 90 × 80 mm with V-cuts, "panel by customer", 1.6 mm
   - JLC04161H-7628 with impedance control, ENIG
   - epoxy-filled and capped vias
   - green mask with white silk
4. **Check the quote:** compare the part placement preview with `board/docs/assembly-top-refs.pdf`, and the rotations
   with `cpl-rotations.md`.

## 2. Print the case

Rails still on the board → `case/rv1106_tray_rails.stl` and `case/rv1106_lid_rails.stl`. Rails snapped off → the
files without `_rails`.

- **Print settings:** PETG/PLA FDM, no supports. For JLC3DP, MJF PA12 nylon.
- **Hardware:** 4 × M3 heat-set inserts and 4 × M3×20 socket-head screws.
- **More details:** see `case/README.md` in the repo root.

## 3. Bring up and flash

Follow `software/BOARD-QUICKSTART.md`. The Luckfox SPI NAND image and the toolchain are not stored in the repo; the
quickstart explains how to fetch them. `software/` here has the board's device trees.

## Status

- **Board:** built and running. Board #1 boots Linux from SPI NAND, gets on Ethernet, and runs YOLOv5 on the NPU
  (2026-11-20). See `design/LOG.md`.
- **Case:** reviewed against the KiCad data but not yet printed.
