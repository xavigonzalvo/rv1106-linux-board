// Letterbox (keep aspect ratio, pad with grey 114) from an RGB888 image into the model input buffer.
#pragma once

#include <stdint.h>

struct Letterbox {
    int src_w, src_h;  // original image
    int dst_w, dst_h;  // model input (e.g. 640x640)
    int new_w, new_h;  // size of the resized image inside dst
    int pad_x, pad_y;  // top-left of the resized image inside dst
};

Letterbox compute_letterbox(int src_w, int src_h, int dst_w, int dst_h);

// Bilinear resize src (RGB888, tightly packed rows) into dst (RGB888, dst_row_bytes per row, may be > dst_w*3)
// at (pad_x, pad_y), filling the rest with `fill`.
void letterbox_rgb(const uint8_t *src, const Letterbox &lb, uint8_t *dst, int dst_row_bytes, uint8_t fill);
