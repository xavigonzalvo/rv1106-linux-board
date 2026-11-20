#include "letterbox.h"

#include <math.h>
#include <string.h>

#include <vector>

Letterbox compute_letterbox(int src_w, int src_h, int dst_w, int dst_h)
{
    Letterbox lb;
    lb.src_w = src_w;
    lb.src_h = src_h;
    lb.dst_w = dst_w;
    lb.dst_h = dst_h;
    float sx = (float)dst_w / (float)src_w;
    float sy = (float)dst_h / (float)src_h;
    float s = sx < sy ? sx : sy;
    lb.new_w = (int)lroundf(src_w * s);
    lb.new_h = (int)lroundf(src_h * s);
    if (lb.new_w < 1) lb.new_w = 1;
    if (lb.new_h < 1) lb.new_h = 1;
    if (lb.new_w > dst_w) lb.new_w = dst_w;
    if (lb.new_h > dst_h) lb.new_h = dst_h;
    lb.pad_x = (dst_w - lb.new_w) / 2;
    lb.pad_y = (dst_h - lb.new_h) / 2;
    return lb;
}

// Fixed-point bilinear (11-bit weights), pixel-centre aligned like cv::resize INTER_LINEAR.
void letterbox_rgb(const uint8_t *src, const Letterbox &lb, uint8_t *dst, int dst_row_bytes, uint8_t fill)
{
    const int W = lb.new_w, H = lb.new_h;
    const int sw = lb.src_w, sh = lb.src_h;
    const int src_row = sw * 3;
    enum { BITS = 11, ONE = 1 << BITS };

    std::vector<int> xo0(W), xo1(W), xw(W);
    for (int x = 0; x < W; x++) {
        float fx = ((float)x + 0.5f) * (float)sw / (float)W - 0.5f;
        if (fx < 0) fx = 0;
        int x0 = (int)fx;
        if (x0 > sw - 1) x0 = sw - 1;
        int x1 = x0 + 1 < sw ? x0 + 1 : sw - 1;
        xw[x] = (int)((fx - x0) * ONE);
        xo0[x] = x0 * 3;
        xo1[x] = x1 * 3;
    }

    for (int y = 0; y < lb.dst_h; y++) {
        uint8_t *drow = dst + (size_t)y * dst_row_bytes;
        int yy = y - lb.pad_y;
        if (yy < 0 || yy >= H) {
            memset(drow, fill, (size_t)lb.dst_w * 3);
            continue;
        }
        memset(drow, fill, (size_t)lb.pad_x * 3);
        memset(drow + (size_t)(lb.pad_x + W) * 3, fill, (size_t)(lb.dst_w - lb.pad_x - W) * 3);

        float fy = ((float)yy + 0.5f) * (float)sh / (float)H - 0.5f;
        if (fy < 0) fy = 0;
        int y0 = (int)fy;
        if (y0 > sh - 1) y0 = sh - 1;
        int y1 = y0 + 1 < sh ? y0 + 1 : sh - 1;
        int wy = (int)((fy - y0) * ONE);
        const uint8_t *r0 = src + (size_t)y0 * src_row;
        const uint8_t *r1 = src + (size_t)y1 * src_row;
        uint8_t *d = drow + (size_t)lb.pad_x * 3;
        for (int x = 0; x < W; x++) {
            const uint8_t *a = r0 + xo0[x], *b = r0 + xo1[x];
            const uint8_t *c = r1 + xo0[x], *e = r1 + xo1[x];
            int wx = xw[x];
            for (int k = 0; k < 3; k++) {
                int top = a[k] * ONE + (b[k] - a[k]) * wx;  // << BITS
                int bot = c[k] * ONE + (e[k] - c[k]) * wx;
                int v = (top * ONE + (bot - top) * wy + (1 << (2 * BITS - 1))) >> (2 * BITS);
                d[k] = (uint8_t)(v < 0 ? 0 : (v > 255 ? 255 : v));
            }
            d += 3;
        }
    }
}
