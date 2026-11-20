# Build inside the linux-board-sdk container (from the project root):
#   software/docker/build.sh make -C software/examples/hello-c
CROSS_COMPILE ?= arm-rockchip830-linux-uclibcgnueabihf-
CXX      := $(CROSS_COMPILE)g++
STRIP    := $(CROSS_COMPILE)strip
CXXFLAGS ?= -O2 -Wall -Wextra -std=c++17 -march=armv7-a -mfpu=neon -mfloat-abi=hard
LDFLAGS  ?=

hello-c: main.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)
	$(STRIP) $@

clean:
	rm -f hello-c

.PHONY: clean
