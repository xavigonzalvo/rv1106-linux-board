#!/bin/sh
# Build ai-detect and install it on the board over adb. Run from anywhere on the Mac.
#   sh software/examples/ai-detect/deploy.sh          build + install + (re)start
#   sh software/examples/ai-detect/deploy.sh --no-build
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)

if [ "$1" != "--no-build" ]; then
	echo "== detector (C++, Docker cross-compiler)"
	(cd "$ROOT" && software/docker/build.sh make -C software/examples/ai-detect/detector)
	echo "== server (Go, static ARMv7)"
	(cd "$HERE/server" && CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 \
		go build -trimpath -ldflags="-s -w" -o server .)
fi

echo "== install"
adb shell 'test -d /mnt/sdcard' || { echo "no microSD mounted at /mnt/sdcard"; exit 1; }
adb shell '[ -x /etc/init.d/S99ai-detect ] && /etc/init.d/S99ai-detect stop; mkdir -p /root/ai-detect /mnt/sdcard/ai-detect/model /mnt/sdcard/ai-detect/uploads'
adb push "$HERE/server/server" "$HERE/detector/build/detector" /root/ai-detect/
adb push "$HERE/model/yolov5.rknn" "$HERE/model/labels.txt" /mnt/sdcard/ai-detect/model/
adb push "$HERE/S99ai-detect" /etc/init.d/S99ai-detect
adb shell 'chmod +x /root/ai-detect/server /root/ai-detect/detector /etc/init.d/S99ai-detect; sync; /etc/init.d/S99ai-detect start'

IP=$(adb shell "ifconfig eth0" | sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p')
adb forward tcp:8080 tcp:8080 >/dev/null
echo "== done: http://localhost:8080 (over USB)${IP:+  or  http://$IP:8080 (Ethernet)}"
