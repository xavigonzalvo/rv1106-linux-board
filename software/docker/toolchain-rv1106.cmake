# CMake toolchain file for the RV1106 board (used inside the linux-board-sdk container).
#   cmake -B build -DCMAKE_TOOLCHAIN_FILE=/opt/toolchain-rv1106.cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR armv7l)

set(TOOLCHAIN_PREFIX arm-rockchip830-linux-uclibcgnueabihf)
set(CMAKE_C_COMPILER   /opt/toolchain/bin/${TOOLCHAIN_PREFIX}-gcc)
set(CMAKE_CXX_COMPILER /opt/toolchain/bin/${TOOLCHAIN_PREFIX}-g++)
set(CMAKE_SYSROOT      /opt/toolchain/${TOOLCHAIN_PREFIX}/sysroot)

set(CMAKE_C_FLAGS_INIT   "-march=armv7-a -mfpu=neon -mfloat-abi=hard")
set(CMAKE_CXX_FLAGS_INIT "-march=armv7-a -mfpu=neon -mfloat-abi=hard")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
