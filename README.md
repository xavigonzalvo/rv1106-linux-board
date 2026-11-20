# RV1106G3 Linux board (Rev A)

An 80 × 80 mm Linux board around the Rockchip RV1106G3 (Cortex-A7, 256 MB DDR3L in package, 1 TOPS NPU), with
SPI NAND, microSD, 100 Mb Ethernet, USB-C (power + OTG), USB-A host and a 2×20 header.
Board #1 boots Linux, is on the network and runs YOLOv5 on the NPU (2026-11-20).

| Folder | What |
|---|---|
| `PLAN.md` | the project plan and phases |
| `design/` | requirements, decisions (`decisions.md`), schematic, PCB (`pcb/`, fab files in `pcb/fab/`), bring-up procedure and log (`bringup.md`, `LOG.md`), datasheets and references (`refs/`) |
| `software/` | board support for the Luckfox SDK, flashing tools, Docker cross-compiler, examples |
| `software/BOARD-QUICKSTART.md` | **start here** to flash and use a board |
| `software/examples/ai-detect/` | object detection on the NPU with a web UI |
| `dashboard/` | project status page |

## Not in this repo (fetch again when needed)

* `thirdparty/luckfox-image/` — Luckfox Pico Pro Max SPI NAND image 250607, from Luckfox's Google Drive (link in
  `software/BOARD-QUICKSTART.md` §3).
* `thirdparty/luckfox-toolchain/` — `software/docker/build.sh fetch-toolchain`.
* `software/tools/rkdeveloptool/` — github.com/rockchip-linux/rkdeveloptool commit 304f073, build steps in the quickstart §2.
* `thirdparty/luckfox_pico_rknn_example`, `rknn_model_zoo`, `stb` — reference sources only; what the detector needs is
  copied into `software/examples/ai-detect/detector/3rdparty/`.
* `design/.venv/` — Python environment for the design tools.
* Intermediate PCB routing trials (`design/pcb/trial`, `l5`, `l5f`) and build outputs.
