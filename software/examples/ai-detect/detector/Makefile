# Cross build (inside the linux-board-sdk container):  software/docker/build.sh make -C software/examples/ai-detect/detector
# Host unit test + stub-runtime binary (on the Mac):     make -C software/examples/ai-detect/detector host-test
BUILD      ?= build
HOST_BUILD ?= build-host

.PHONY: all host-test clean

all:
	cmake -S . -B $(BUILD) -DCMAKE_TOOLCHAIN_FILE=$(CURDIR)/cmake/toolchain-rv1106.cmake -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD) -j4
	@file $(BUILD)/detector 2>/dev/null || true

host-test:
	cmake -S . -B $(HOST_BUILD) -DDETECTOR_HOST_TEST=ON
	cmake --build $(HOST_BUILD) -j4
	./$(HOST_BUILD)/host_test

clean:
	rm -rf $(BUILD) $(HOST_BUILD)
