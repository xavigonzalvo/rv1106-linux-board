# linux-board-sdk: cross-compile environment for the RV1106G3 board (Luckfox Buildroot, uClibc 1.0.31, armv7l).
#
# The Rockchip toolchain (arm-rockchip830-linux-uclibcgnueabihf, GCC 8.3) is an x86-64 Linux binary, so this
# image is always built and run as linux/amd64 (Rosetta / QEMU on Apple silicon).
#
# The toolchain is NOT baked into the image: build.sh mounts it read-only from
#   thirdparty/luckfox-toolchain/luckfox-pico/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf
# at /opt/toolchain. The image is just Ubuntu 22.04 + build tools, and stays small.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      make cmake ninja-build pkg-config file binutils ca-certificates bzip2 xz-utils \
 && rm -rf /var/lib/apt/lists/*

ENV CROSS_COMPILE=arm-rockchip830-linux-uclibcgnueabihf-
ENV TOOLCHAIN_DIR=/opt/toolchain
ENV PATH=/opt/toolchain/bin:$PATH
ENV CC=arm-rockchip830-linux-uclibcgnueabihf-gcc \
    CXX=arm-rockchip830-linux-uclibcgnueabihf-g++ \
    AR=arm-rockchip830-linux-uclibcgnueabihf-ar \
    STRIP=arm-rockchip830-linux-uclibcgnueabihf-strip \
    READELF=arm-rockchip830-linux-uclibcgnueabihf-readelf

COPY toolchain-rv1106.cmake /opt/toolchain-rv1106.cmake

WORKDIR /work
