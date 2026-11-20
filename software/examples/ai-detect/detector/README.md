# ai-detect detector

YOLOv5s (COCO 80) on the RV1106G3 NPU through `librknnmrt.so`. Implements `../PROTOCOL.md`. It loads the model once,
prints the ready line, then reads one image path per line on stdin and writes one JSON line per request on stdout.
Logs go to stderr.

```
detector --model /mnt/sdcard/ai-detect/model/yolov5.rknn --labels /mnt/sdcard/ai-detect/model/labels.txt \
         [--box-thresh 0.25] [--nms-thresh 0.45] [--max-pixels 13000000]
```

## Layout

| Path | What |
|---|---|
| `src/main.cpp` | arguments, ready line, stdin loop, timings |
| `src/npu.cpp` | RKNN zero-copy setup and run (no RKNN code anywhere else) |
| `src/postprocess.cpp` | int8 head decode (NHWC and NCHW), NMS, undo letterbox |
| `src/letterbox.cpp` | aspect-preserving bilinear resize into the NPU input buffer, grey 114 padding |
| `src/image_io.cpp` | JPEG/PNG decode (stb_image) |
| `src/json_out.cpp` | protocol JSON lines |
| `3rdparty/rknpu2/` | `rknn_api.h` and `librknnmrt.so` 1.6.0 (armhf uClibc), copied from LuckfoxTECH/luckfox_pico_rknn_example |
| `3rdparty/stb/` | `stb_image.h` v2.34 from nothings/stb |
| `cmake/toolchain-rv1106.cmake` | cross toolchain file (`TOOLCHAIN_DIR`, `CROSS_COMPILE` env vars) |
| `test/` | host unit test, fake librknnmrt for running the real main loop on the Mac, test images |
| `../model/yolov5.rknn`, `../model/labels.txt` | model (Luckfox prebuilt, rv1106, int8) and COCO labels |

## Build for the board

You need the Docker SDK from `software/docker/`. Set it up once with `software/docker/build.sh fetch-toolchain` and
`software/docker/build.sh image`. Then, from the project root:

```
software/docker/build.sh make -C software/examples/ai-detect/detector
```

This runs CMake with `cmake/toolchain-rv1106.cmake` into `build/` and strips the binary. The result is
`build/detector`, an ARM EABI5 hard-float binary linked against `librknnmrt.so` with RPATH `/oem/usr/lib`.
libstdc++ and libgcc are linked statically.

If you are not using the container, put the compiler on PATH or set
`TOOLCHAIN_DIR=/path/to/arm-rockchip830-linux-uclibcgnueabihf` (the directory that contains `bin/`), then run
`make` in this directory.

TODO: not yet built with the real toolchain. This README was written before the container existed.

## Host checks (Mac, no toolchain)

```
make -C software/examples/ai-detect/detector host-test
```

This builds and runs `build-host/host_test`, which checks:

- letterbox math and resize
- the int8 YOLOv5 decode for NHWC, padded-NHWC and NCHW layouts, using synthetic quantised tensors
- NMS
- undoing the letterbox
- the exact JSON strings
- JPEG/PNG decode and its errors

It also builds `build-host/detector_hoststub`. That is the real `main.cpp`/`npu.cpp` linked against a fake
librknnmrt (`test/rknn_stub.cpp`) that always "detects" one person. It speaks the real protocol on the Mac:

```
echo "$PWD/software/examples/ai-detect/detector/test/bus.jpg" | \
  software/examples/ai-detect/detector/build-host/detector_hoststub \
  --model software/examples/ai-detect/model/yolov5.rknn --labels software/examples/ai-detect/model/labels.txt
```

## Run on the board

```
/mnt/sdcard/ai-detect/detector --model /mnt/sdcard/ai-detect/model/yolov5.rknn \
    --labels /mnt/sdcard/ai-detect/model/labels.txt
# then type an image path, e.g. /mnt/sdcard/ai-detect/uploads/bus.jpg
```

stderr shows the runtime and driver versions and every tensor attribute, including `fmt`, `dims`, `w_stride`,
`size_with_stride`, `zp` and `scale`. Check them on the first run (see below). If exec from vfat fails, copy the binary
to `/userdata`. The Luckfox demos stop the camera app with `RkLunch-stop.sh` before using the NPU. Try that if
`rknn_init` fails or memory is short.

## Model

- `../model/yolov5.rknn` (7.2 MB, sha256 `7e72c8ca…1c44a`) is
  `example/luckfox_pico_yolov5/model/yolov5.rknn` from LuckfoxTECH/luckfox_pico_rknn_example (commit 16ef54a).
  It is the same file as `install/uclibc/luckfox_pico_yolov5_demo/model/yolov5.rknn`. Its embedded metadata:
  - target `rv1106`, built with toolkit/compiler `1.6.0+81f21f4d`
  - input `images` [1,3,640,640] int8
  - outputs `output0` [1,255,80,80], `286` [1,255,40,40] and `288` [1,255,20,20], int8 with per-layer quantisation
  - sigmoid in-graph (Rockchip yolov5 export), so the decode is `(2s-0.5+grid)*stride` and `(2s)^2*anchor`
- Normalisation is mean 0, std 255, RGB (`scripts/luckfox_onnx_to_rknn/convert/convert.py`). Passing UINT8 NHWC
  input lets the NPU apply it. stb_image gives RGB.
- Runtime: the board's `/oem/usr/lib/librknnmrt.so` is `librknnmrt version: 1.6.0 (2de554906@2024-01-17)`, read
  from the Luckfox_Pico_Pro_Max_Flash_250607 `oem.img`. The model is from toolkit 1.6.0, so the versions match.
  Do not use a model from rknn-toolkit2 2.x with this runtime: it is a newer model format and is expected to fail
  with "incompatible model version". If you do, upgrade `/oem/usr/lib/librknnmrt.so` and `rknn_api.h` too.

To rebuild the model (not needed now), use rknn-toolkit2 **1.6.0** (github.com/rockchip-linux/rknn-toolkit2 or
airockchip/rknn-toolkit2, x86-64 Linux, Python 3.8) and the Luckfox ONNX
`scripts/luckfox_onnx_to_rknn/model/yolov5.onnx` (28 MB, already in `thirdparty/`):

```
cd thirdparty/luckfox_pico_rknn_example/scripts/luckfox_onnx_to_rknn/convert
python3 convert.py ../model/yolov5.onnx ../dataset/yolov5_dataset.txt yolov5.rknn yolov5
# convert.py: rknn.config(mean_values=[[0,0,0]], std_values=[[255,255,255]], target_platform='rv1103')
#             then build(do_quantization=True). Set target_platform='rv1106' for this board.
```

## RV1106 output layout: what is assumed and what to check

The setup follows `yolov5.cc` from Luckfox, which pairs with runtime 1.6.0, and `yolov5_rv1106_1103.cc` from the
model zoo:

1. Outputs are queried with `RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR` and bound with `rknn_set_io_mem`.
2. The expected attrs are `fmt=NHWC`, `dims=[1,H,W,255]` and int8 affine. The decode is `process_i8_rv1106`:
   element `(h, w, a*85 + k)` is at `(h*W + w)*C + a*85 + k`.
3. If `size_with_stride == H*W*C'` with C' slightly larger than 255, the detector uses C' as the per-position
   stride. The reference code assumes exactly 255.
4. If the runtime reports NCHW instead, the model-zoo `process_i8` indexing is used. NC1HWC2 is rejected with an
   error at load time, so the server sees `{"ready":false,...}`.
5. Heads are matched to anchors by grid size, not output order.
