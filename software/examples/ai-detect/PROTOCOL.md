# ai-detect: interface between the Go server and the detector

Two programs run on the board (RV1106G3, armv7l, uClibc 1.0.31, Luckfox Buildroot image):

* `server/` — Go web server (static ARMv7 binary, like `software/examples/hello-http`). Serves the UI on port 8080.
* `detector/` — C/C++ program built with the Luckfox toolchain `arm-rockchip830-linux-uclibcgnueabihf`. Runs YOLOv5
  on the NPU through `librknnmrt.so` (already on the board in `/oem/usr/lib`).

## Files on the board

Everything lives on the microSD card, mounted at `/mnt/sdcard` (FAT32: no symlinks, no exec bit issues are expected,
but if exec from vfat fails, copy the binaries to `/userdata`).

```
/mnt/sdcard/ai-detect/
  server            Go binary
  detector          detector binary
  model/yolov5.rknn model for RV1106
  model/labels.txt  one class name per line (COCO 80)
  web/              index.html, app.js, style.css (the server may also embed them)
  uploads/          temporary images
```

## Process model

The server starts the detector **once** as a child process and keeps it running (model loaded once):

```
detector --model /mnt/sdcard/ai-detect/model/yolov5.rknn --labels /mnt/sdcard/ai-detect/model/labels.txt
```

On start the detector loads the model, then prints exactly one line to stdout:

```
{"ready":true,"model":"yolov5.rknn","input":[640,640],"load_ms":812.4}
```
or on failure `{"ready":false,"error":"..."}` and exits non-zero.

## Request / response (line-based, stdin → stdout)

One request = one line on the detector's stdin: an absolute path to an image file (JPEG or PNG), terminated by `\n`.
One response = exactly one line of JSON on stdout, terminated by `\n`. Requests are handled strictly one at a time
(the server serialises them). Logs and debug output go to **stderr only**, never stdout.

Success:
```json
{"ok":true,"width":1280,"height":720,"ms":{"decode":35.1,"preprocess":12.0,"npu":48.2,"postprocess":3.1,"total":98.4},
 "objects":[{"label":"person","class":0,"score":0.87,"box":[x1,y1,x2,y2]}]}
```
* `width`/`height`: original image size in pixels.
* `box`: integer pixel coordinates in the **original** image (letterbox undone), clamped to the image.
* `score`: 0–1, after NMS. Default thresholds: box 0.25, NMS 0.45. Objects sorted by score, highest first.

Error (detector keeps running):
```json
{"ok":false,"error":"cannot decode /mnt/sdcard/ai-detect/uploads/abc.jpg"}
```

The server must cope with the detector dying: report an error to the client and restart it.

## Details settled during the first build (2026-11-20)

* `"input":[w,h]` is width first. Boxes are clamped to `[0,w-1]` × `[0,h-1]`.
* The detector ignores EXIF orientation (raw pixel order). The UI's downscale step re-encodes the image with the
  rotation applied, so boxes line up; with downscale off the UI shows the image unrotated.
* An empty request line gets `{"ok":false,...}`, so there is always one response per line. The detector exits when
  stdin closes.
* Binaries run from `/root/ai-detect/` (the vfat card has no exec); model and uploads stay on the card.

## Mock detector

`server/` ships a mock mode (`-mock`) that returns fake but well-formed responses, so the UI can be developed and tested
on the Mac without the board.
