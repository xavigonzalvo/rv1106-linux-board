#!/bin/sh
# Build tiny-llm and install it on the board over adb. Run from anywhere on the Mac.
#   sh software/examples/tiny-llm/deploy.sh             fetch + convert model (once), build, install
#   sh software/examples/tiny-llm/deploy.sh --no-build
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
SM="$ROOT/thirdparty/smollm2-135m-instruct"

echo "== model (SmolLM2-135M-Instruct, int8)"
if [ ! -f "$SM/smollm2-135m-instruct.bin" ]; then
	mkdir -p "$SM"
	for f in config.json tokenizer.json tokenizer_config.json model.safetensors; do          # 257 MB bf16
		[ -f "$SM/$f" ] || curl -fL -o "$SM/$f" https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/resolve/main/$f
	done
	python3 -I "$HERE/convert_hf.py" "$SM" "$SM/smollm2-135m-instruct"                        # -> 143 MB + .tok
fi

if [ "$1" != "--no-build" ]; then
	echo "== llm (C, Docker cross-compiler)"
	(cd "$ROOT" && software/docker/build.sh make -C software/examples/tiny-llm llm)
fi

echo "== install"
adb shell 'test -d /mnt/sdcard' || { echo "no microSD mounted at /mnt/sdcard"; exit 1; }
adb shell 'mkdir -p /root/tiny-llm /mnt/sdcard/tiny-llm'
adb push "$HERE/llm" /root/tiny-llm/
adb push "$HERE/chat" /usr/bin/chat
push_if_changed() {   # $1 local file -> /mnt/sdcard/tiny-llm/ (skip the slow push when the size already matches)
	r=$(adb shell "ls -l /mnt/sdcard/tiny-llm/$(basename "$1") 2>/dev/null" | awk '{print $5}')   # no stat in BusyBox
	[ "$r" = "$(stat -f %z "$1")" ] || adb push "$1" /mnt/sdcard/tiny-llm/
}
push_if_changed "$SM/smollm2-135m-instruct.bin"
push_if_changed "$SM/smollm2-135m-instruct.tok"
adb shell 'chmod +x /root/tiny-llm/llm /usr/bin/chat; sync'
echo "== done. On the board (adb shell):  chat"
