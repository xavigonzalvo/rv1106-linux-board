#pragma once

#include <stdint.h>

#include <string>

// Decoded RGB888 image, tightly packed (width*3 bytes per row).
struct Image {
    uint8_t *data;
    int width, height;
    Image() : data(0), width(0), height(0) {}
    ~Image() { reset(); }
    void reset();

private:
    Image(const Image &);
    Image &operator=(const Image &);
};

// err: the protocol-level message ("cannot open <path>", "cannot decode <path>", "image too large ...").
// reason: extra detail from stb for stderr. Note: EXIF orientation is NOT applied (raw pixel order).
bool decode_image(const char *path, long max_pixels, Image &img, std::string &err, std::string &reason);
