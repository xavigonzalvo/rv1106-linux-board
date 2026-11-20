# ai-detect — object detection on the board's NPU, with a web UI

Open the page, drop in or take a photo, and the board's NPU finds objects (YOLOv5s, 80 COCO classes) and the page
draws the boxes. First run on board #1: 2026-11-20.

| Part | What | Where on the board |
|---|---|---|
| `server/` | Go web server + UI (embedded), port 8080. Standard library only. | `/root/ai-detect/server` |
| `detector/` | C++ YOLOv5 on the NPU via `librknnmrt.so` 1.6.0 (already on the board in `/oem/usr/lib`) | `/root/ai-detect/detector` |
| `model/` | `yolov5.rknn` (Luckfox, rv1106, int8, 640×640) + `labels.txt` | `/mnt/sdcard/ai-detect/model/` |
| `S99ai-detect` | boot script: waits for the microSD, starts the server (which starts the detector) | `/etc/init.d/` |
| `PROTOCOL.md` | the stdin/stdout contract between server and detector | — |

Binaries are on the root filesystem because the FAT32 microSD is mounted without exec permission.

## Install / update (from the Mac, board on USB, microSD inserted)

```sh
sh software/examples/ai-detect/deploy.sh
```
It builds the detector in Docker (`software/docker/`, see `software/README.md`), builds the Go server, pushes
everything and restarts the app. Then open **http://localhost:8080** (over USB, via `adb forward`) or
**http://&lt;board-ip&gt;:8080** from any device on the LAN with the Ethernet cable in (a phone can then use the
"Take photo" button).

On the board: `/etc/init.d/S99ai-detect start|stop|restart`, log in `/tmp/ai-detect.log`.
Uninstall: `rm /etc/init.d/S99ai-detect; rm -r /root/ai-detect`.
`hello-http` also uses port 8080: don't run both.

## Measured on board #1 (Luckfox image, 2026-11-20)

`detector/test/bus.jpg` (640×640) → 4 × person + bus, the expected result.

| Stage | ms |
|---|---|
| JPEG decode (stb, CPU) | 41 |
| letterbox to 640×640 (CPU) | 40 |
| NPU (`rknn_run`) | 81 |
| postprocess + NMS | 1.6 |
| detector total | 165 |
| browser round trip over USB | ~205 |

Model load 45–440 ms (slowest right after boot). Memory: ~19 MB for the detector, ~6 MB Go; 159 of 181 MB stay free.
Starts on its own ~11 s after power-on.

## Things learned

* **Output stride:** the RV1106 runtime 1.6.0 reports `size_with_stride = H×W×256` for the 255-channel heads, but the
  data is packed at 255 per cell (tail padding only). Reading with 256 gives hundreds of nonsense boxes.
  `DETECTOR_OUT_STRIDE` env var overrides it for experiments.
* Background jobs started from `adb shell` die when the shell closes; use the init script (start-stop-daemon).
* The load average shows ~10 with the CPU idle: ten Rockchip media kernel threads (`vlog`, `venc`, `vrga_*`…) sit in
  D state in the Luckfox image. Not ours, harmless.

## Ideas for next

* Speed: decode + letterbox on the CPU take as long as the NPU. Use RGA (`librga.so` is on the board) for the resize,
  or downscale to 640 px in the browser.
* Live camera: a USB webcam on the USB-A port once our own image enables host mode.
