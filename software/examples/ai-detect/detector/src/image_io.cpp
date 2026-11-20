// JPEG/PNG decode via stb_image (github.com/nothings/stb, single header, public domain / MIT).
#include "image_io.h"

#include <stdio.h>

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_JPEG
#define STBI_ONLY_PNG
#define STBI_FAILURE_USERMSG
#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#define STBI_NEON
#endif
#include "stb_image.h"

bool decode_image(const char *path, long max_pixels, Image &img, std::string &err, std::string &reason)
{
    FILE *f = fopen(path, "rb");
    if (!f) {
        err = std::string("cannot open ") + path;
        return false;
    }
    int w = 0, h = 0, n = 0;
    if (!stbi_info_from_file(f, &w, &h, &n)) {
        fclose(f);
        err = std::string("cannot decode ") + path;
        reason = stbi_failure_reason() ? stbi_failure_reason() : "unknown";
        return false;
    }
    if ((long)w * (long)h > max_pixels) {
        fclose(f);
        char buf[96];
        snprintf(buf, sizeof(buf), "image too large (%dx%d, max %ld pixels)", w, h, max_pixels);
        err = buf;
        return false;
    }
    unsigned char *data = stbi_load_from_file(f, &w, &h, &n, 3);  // force RGB (alpha dropped, grey expanded)
    fclose(f);
    if (!data) {
        err = std::string("cannot decode ") + path;
        reason = stbi_failure_reason() ? stbi_failure_reason() : "unknown";
        return false;
    }
    img.reset();
    img.data = data;
    img.width = w;
    img.height = h;
    return true;
}

void Image::reset()
{
    if (data) stbi_image_free(data);
    data = 0;
    width = height = 0;
}
