# RV1106G3 Linux board (Rev A)

An 80 × 80 mm Linux board around the Rockchip RV1106G3 (Cortex-A7, 256 MB DDR3L in package, 1 TOPS NPU), with
SPI NAND, microSD, 100 Mb Ethernet, USB-C (power + OTG), USB-A host and a 2×20 header.
Board #1 boots Linux, is on the network, runs YOLOv5 on the NPU (2026-11-20) and a 135M-parameter chat model on
the CPU (2026-11-21).

| Folder | What |
|---|---|
| `PLAN.md` | the project plan and phases |
| `design/` | requirements, decisions (`decisions.md`), schematic, PCB (`pcb/`, fab files in `pcb/fab/`), bring-up procedure and log (`bringup.md`, `LOG.md`), datasheets and references (`refs/`) |
| `software/` | board support for the Luckfox SDK, flashing tools, Docker cross-compiler, examples |
| `software/BOARD-QUICKSTART.md` | **start here** to flash and use a board |
| `software/examples/ai-detect/` | object detection on the NPU with a web UI |
| `software/examples/tiny-llm/` | SmolLM2-135M-Instruct chat on the CPU (`chat` in the board shell) |
| `dashboard/` | project status page |

## Not in this repo (fetch again when needed)

* `thirdparty/luckfox-image/` — Luckfox Pico Pro Max SPI NAND image 250607, from Luckfox's Google Drive (link in
  `software/BOARD-QUICKSTART.md` §3).
* `thirdparty/luckfox-toolchain/` — `software/docker/build.sh fetch-toolchain`.
* `software/tools/rkdeveloptool/` — github.com/rockchip-linux/rkdeveloptool commit 304f073, build steps in the quickstart §2.
* `thirdparty/luckfox_pico_rknn_example`, `rknn_model_zoo`, `stb` — reference sources only; what the detector needs is
  copied into `software/examples/ai-detect/detector/3rdparty/`.
* `thirdparty/smollm2-135m-instruct/` — the chat model from huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct and
  its int8 conversion; `software/examples/tiny-llm/deploy.sh` fetches and converts it.
* `thirdparty/llama2.c/` — github.com/karpathy/llama2.c commit 350e04f, the source `tiny-llm/llm.c` started from
  (reference only).
* `design/.venv/` — Python environment for the design tools.
* Intermediate PCB routing trials (`design/pcb/trial`, `l5`, `l5f`) and build outputs.
