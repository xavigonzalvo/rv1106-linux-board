cmake_minimum_required(VERSION 3.10)
project(ai_detect_detector CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# RKNN runtime: header + link stub copied from LuckfoxTECH/luckfox_pico_rknn_example (librknnmrt 1.6.0, armhf uClibc).
# At run time the board's /oem/usr/lib/librknnmrt.so (also 1.6.0) is used.
set(RKNPU2_DIR ${CMAKE_CURRENT_SOURCE_DIR}/3rdparty/rknpu2 CACHE PATH "rknpu2 include/ + lib/ tree")
set(RKNN_LIB ${RKNPU2_DIR}/lib/armhf-uclibc/librknnmrt.so CACHE FILEPATH "librknnmrt to link against")

# Host unit test (no NPU): cmake -B build-host -DDETECTOR_HOST_TEST=ON && cmake --build build-host && ./build-host/host_test
option(DETECTOR_HOST_TEST "Build only the host-side unit test (no RKNN)" OFF)

set(CORE_SRC src/postprocess.cpp src/letterbox.cpp src/json_out.cpp src/image_io.cpp)
include_directories(src 3rdparty/stb)

if(DETECTOR_HOST_TEST)
  add_executable(host_test test/host_test.cpp ${CORE_SRC})
  target_compile_options(host_test PRIVATE -Wall -Wextra -O1 -g)
  target_compile_definitions(host_test PRIVATE TEST_DATA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/test")
  # The real main loop against a fake librknnmrt (test/rknn_stub.cpp): exercises the stdin/stdout protocol on the host.
  add_executable(detector_hoststub src/main.cpp src/npu.cpp test/rknn_stub.cpp ${CORE_SRC})
  target_include_directories(detector_hoststub PRIVATE ${RKNPU2_DIR}/include)
  target_compile_options(detector_hoststub PRIVATE -Wall -O1 -g)
  return()
endif()

add_executable(detector src/main.cpp src/npu.cpp ${CORE_SRC})
target_include_directories(detector PRIVATE ${RKNPU2_DIR}/include)
target_compile_options(detector PRIVATE -Wall -O2)
# Find librknnmrt.so in /oem/usr/lib on the board without LD_LIBRARY_PATH; libstdc++/libgcc linked statically so the
# binary does not depend on the board's C++ runtime version.
set_target_properties(detector PROPERTIES BUILD_RPATH "/oem/usr/lib" INSTALL_RPATH "/oem/usr/lib")
target_link_libraries(detector PRIVATE ${RKNN_LIB} m -static-libstdc++ -static-libgcc)

add_custom_command(TARGET detector POST_BUILD
  COMMAND ${CMAKE_STRIP} $<TARGET_FILE:detector>
  COMMENT "strip detector")
