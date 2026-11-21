# Cross build for the board (inside the linux-board-sdk container, from the project root):
#   software/docker/build.sh make -C software/examples/tiny-llm
# Host build on the Mac, to check the output:
#   make -C software/examples/tiny-llm host
CROSS_COMPILE ?= arm-rockchip830-linux-uclibcgnueabihf-
CC     := $(CROSS_COMPILE)gcc
STRIP  := $(CROSS_COMPILE)strip
CFLAGS ?= -O3 -std=gnu11 -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard -mfp16-format=ieee -ffast-math

llm: llm.c
	$(CC) $(CFLAGS) -o $@ $< -lm
	$(STRIP) $@

host: llm.c
	cc -O3 -ffast-math -o llm-host $< -lm

clean:
	rm -f llm llm-host

.PHONY: host clean
