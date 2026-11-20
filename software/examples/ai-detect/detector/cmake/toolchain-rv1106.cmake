# CMake toolchain file: Rockchip arm-rockchip830-linux-uclibcgnueabihf (GCC 8.3, uClibc) for RV1106 (Cortex-A7).
#
# Compiler location (first match wins):
#   TOOLCHAIN_DIR  env var: directory containing bin/arm-rockchip830-linux-uclibcgnueabihf-g++
#                  (the linux-board-sdk container sets TOOLCHAIN_DIR=/opt/toolchain)
#   CROSS_COMPILE  env var: prefix, default "arm-rockchip830-linux-uclibcgnueabihf-" (compiler then found on PATH
#                  if TOOLCHAIN_DIR is not set)
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR armv7l)

if(DEFINED ENV{CROSS_COMPILE})
  set(_prefix "$ENV{CROSS_COMPILE}")
else()
  set(_prefix "arm-rockchip830-linux-uclibcgnueabihf-")
endif()

if(DEFINED ENV{TOOLCHAIN_DIR})
  set(_bin "$ENV{TOOLCHAIN_DIR}/bin/")
else()
  set(_bin "")
endif()

set(CMAKE_C_COMPILER   "${_bin}${_prefix}gcc")
set(CMAKE_CXX_COMPILER "${_bin}${_prefix}g++")
set(CMAKE_STRIP        "${_bin}${_prefix}strip" CACHE FILEPATH "strip")

set(CMAKE_C_FLAGS_INIT   "-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard")
set(CMAKE_CXX_FLAGS_INIT "-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard")

# Use the compiler's built-in sysroot; never pick up host libraries/headers.
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
