#!/bin/sh
# Cross-compile for the RV1106 board inside the linux-board-sdk container.
#
# Run from anywhere; the project root is mounted at /work and the command runs in the container directory that
# matches your current directory (or /work if you are outside the project).
#
#   software/docker/build.sh fetch-toolchain   # once: sparse-clone the toolchain into thirdparty/ (~330 MB)
#   software/docker/build.sh image             # once: build the linux-board-sdk image
#   software/docker/build.sh make -C software/examples/hello-c
#   software/docker/build.sh                   # interactive shell
set -eu

IMAGE=linux-board-sdk
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
TC_REPO="$ROOT/thirdparty/luckfox-toolchain/luckfox-pico"
TC_SUB=tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf
TC="$TC_REPO/$TC_SUB"

case "${1:-}" in
fetch-toolchain)
    if [ -d "$TC/bin" ]; then echo "toolchain already at $TC"; exit 0; fi
    mkdir -p "$(dirname "$TC_REPO")"
    git clone --filter=blob:none --depth 1 --sparse --no-checkout \
        https://github.com/LuckfoxTECH/luckfox-pico.git "$TC_REPO"
    git -C "$TC_REPO" sparse-checkout set --no-cone "/$TC_SUB/"
    git -C "$TC_REPO" checkout
    exit 0 ;;
image)
    exec docker build --platform linux/amd64 -t "$IMAGE" "$HERE" ;;
esac

if [ ! -x "$TC/bin/arm-rockchip830-linux-uclibcgnueabihf-g++" ]; then
    echo "toolchain missing: run '$0 fetch-toolchain' first" >&2; exit 1
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    docker build --platform linux/amd64 -t "$IMAGE" "$HERE"
fi

# Map the current directory into /work when it is inside the project.
case "$PWD/" in
    "$ROOT"/*) WD="/work${PWD#"$ROOT"}" ;;
    *) WD=/work ;;
esac

TTY=""
[ -t 0 ] && [ -t 1 ] && TTY="-it"
[ $# -eq 0 ] && set -- bash

exec docker run --rm $TTY --platform linux/amd64 \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT":/work \
    -v "$TC":/opt/toolchain:ro \
    -w "$WD" \
    "$IMAGE" "$@"
