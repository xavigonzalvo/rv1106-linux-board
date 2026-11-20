// Host-side unit test for the parts of the detector that do not need the NPU:
// letterbox math + resize, YOLOv5 int8 head decode (NHWC and NCHW, padded stride), NMS, unletterbox, JSON, decode.
//   cmake -S . -B build-host -DDETECTOR_HOST_TEST=ON && cmake --build build-host && ./build-host/host_test
#include <math.h>
#include <stdio.h>
#include <string.h>

#include <string>
#include <vector>

#include "image_io.h"
#include "json_out.h"
#include "letterbox.h"
#include "postprocess.h"

static int failures = 0;
#define CHECK(c)                                                         \
    do {                                                                 \
        if (!(c)) {                                                      \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); \
            failures++;                                                  \
        }                                                                \
    } while (0)
#define NEAR(a, b, tol) CHECK(fabs((double)(a) - (double)(b)) <= (tol))

static void test_letterbox_math()
{
    Letterbox a = compute_letterbox(1280, 720, 640, 640);
    CHECK(a.new_w == 640 && a.new_h == 360 && a.pad_x == 0 && a.pad_y == 140);
    Letterbox b = compute_letterbox(720, 1280, 640, 640);
    CHECK(b.new_w == 360 && b.new_h == 640 && b.pad_x == 140 && b.pad_y == 0);
    Letterbox c = compute_letterbox(640, 640, 640, 640);
    CHECK(c.new_w == 640 && c.new_h == 640 && c.pad_x == 0 && c.pad_y == 0);
    Letterbox d = compute_letterbox(100, 50, 640, 640);  // upscale
    CHECK(d.new_w == 640 && d.new_h == 320 && d.pad_y == 160);
    Letterbox e = compute_letterbox(5000, 1, 640, 640);  // degenerate
    CHECK(e.new_h >= 1 && e.new_w == 640);
}

static void test_letterbox_resize()
{
    const int sw = 300, sh = 100;
    std::vector<uint8_t> src(sw * sh * 3);
    for (int i = 0; i < sw * sh; i++) {
        src[i * 3 + 0] = 200;
        src[i * 3 + 1] = 10;
        src[i * 3 + 2] = 77;
    }
    Letterbox lb = compute_letterbox(sw, sh, 64, 64);  // 64x21, pad_y 21
    const int row = 70 * 3;                             // padded row stride (w_stride 70)
    std::vector<uint8_t> dst(row * 64, 0xEE);
    letterbox_rgb(&src[0], lb, &dst[0], row, 114);
    CHECK(dst[0] == 114 && dst[row * (lb.pad_y - 1) + 63 * 3 + 2] == 114);  // top pad
    CHECK(dst[row * (lb.pad_y + lb.new_h) + 5] == 114);                     // bottom pad
    const uint8_t *mid = &dst[row * (lb.pad_y + lb.new_h / 2) + 32 * 3];
    CHECK(mid[0] == 200 && mid[1] == 10 && mid[2] == 77);
    CHECK(dst[row * 30 + 64 * 3] == 0xEE);  // bytes beyond dst_w*3 in a row are not touched

    // gradient: left-to-right ramp stays monotonic
    std::vector<uint8_t> g(256 * 4 * 3);
    for (int y = 0; y < 4; y++)
        for (int x = 0; x < 256; x++)
            for (int k = 0; k < 3; k++) g[(y * 256 + x) * 3 + k] = (uint8_t)x;
    Letterbox lg = compute_letterbox(256, 4, 64, 64);
    std::vector<uint8_t> gd(64 * 64 * 3);
    letterbox_rgb(&g[0], lg, &gd[0], 64 * 3, 114);
    int yrow = lg.pad_y;
    for (int x = 1; x < 64; x++) CHECK(gd[(yrow * 64 + x) * 3] >= gd[(yrow * 64 + x - 1) * 3]);
}

// Quantise like the toolkit (affine int8): q = round(v / scale) + zp
static int8_t q(float v, int zp, float scale)
{
    float r = roundf(v / scale) + zp;
    if (r < -128) r = -128;
    if (r > 127) r = 127;
    return (int8_t)r;
}

struct FakeHead {
    std::vector<int8_t> buf;
    HeadTensor t;
};

static FakeHead make_head(TensorLayout layout, int grid, int c_stride_extra, int stride_px, int anchor_idx)
{
    const int zp = -128;
    const float scale = 1.0f / 255.0f;
    FakeHead f;
    memset(&f.t, 0, sizeof(f.t));
    f.t.layout = layout;
    f.t.grid_h = f.t.grid_w = grid;
    f.t.channels = 255;
    f.t.stride = layout == LAYOUT_NHWC ? 255 + c_stride_extra : grid * grid;
    f.t.zp = zp;
    f.t.scale = scale;
    f.t.anchors = kYolov5Anchors[anchor_idx];
    f.t.stride_px = stride_px;
    size_t n = layout == LAYOUT_NHWC ? (size_t)grid * grid * f.t.stride : (size_t)255 * grid * grid;
    f.buf.assign(n, q(0.0f, zp, scale));
    f.t.data = &f.buf[0];
    return f;
}

static void set_val(FakeHead &f, int h, int w, int ch, float v)
{
    size_t idx = f.t.layout == LAYOUT_NHWC ? (size_t)(h * f.t.grid_w + w) * f.t.stride + ch
                                           : (size_t)ch * f.t.stride + h * f.t.grid_w + w;
    f.buf[idx] = q(v, f.t.zp, f.t.scale);
}

static void put_box(FakeHead &f, int h, int w, int a, float sx, float sy, float sw, float sh, float conf, int cls,
                    float p)
{
    int base = a * 85;
    set_val(f, h, w, base + 0, sx);
    set_val(f, h, w, base + 1, sy);
    set_val(f, h, w, base + 2, sw);
    set_val(f, h, w, base + 3, sh);
    set_val(f, h, w, base + 4, conf);
    set_val(f, h, w, base + 5 + cls, p);
}

static void test_decode(TensorLayout layout, int extra)
{
    FakeHead f = make_head(layout, 80, extra, 8, 0);
    // cell (h=10, w=20), anchor 1 (16x30): centre (164, 84), size (16, 30)
    put_box(f, 10, 20, 1, 0.5f, 0.5f, 0.5f, 0.5f, 0.9f, 3, 0.8f);
    // below threshold: 0.4 * 0.5 = 0.2 < 0.25
    put_box(f, 40, 40, 0, 0.5f, 0.5f, 0.5f, 0.5f, 0.4f, 7, 0.5f);
    std::vector<Detection> out;
    decode_head(f.t, 80, 0.25f, out);
    CHECK(out.size() == 1);
    if (out.size() == 1) {
        const Detection &d = out[0];
        CHECK(d.cls == 3);
        NEAR(d.score, 0.72, 0.01);
        NEAR(d.x1, 156, 0.2);
        NEAR(d.y1, 69, 0.2);
        NEAR(d.x2, 172, 0.2);
        NEAR(d.y2, 99, 0.2);
    }
}

static void test_nms()
{
    std::vector<Detection> c;
    Detection a = {10, 10, 110, 110, 0.6f, 0};
    Detection b = {12, 12, 112, 112, 0.9f, 0};   // overlaps a, higher score
    Detection d = {12, 12, 112, 112, 0.5f, 1};   // same place, other class -> kept
    Detection e = {300, 300, 350, 350, 0.3f, 0}; // far away -> kept
    c.push_back(a);
    c.push_back(b);
    c.push_back(d);
    c.push_back(e);
    std::vector<Detection> k = nms(c, 0.45f, 128);
    CHECK(k.size() == 3);
    if (k.size() == 3) {
        CHECK(k[0].score == 0.9f && k[1].score == 0.5f && k[2].score == 0.3f);
    }
    CHECK(nms(c, 0.45f, 1).size() == 1);
}

static void test_unletterbox()
{
    Letterbox lb = compute_letterbox(1280, 720, 640, 640);
    std::vector<Detection> v;
    Detection a = {-5, 100, 700, 520, 0.5f, 0};  // spills into padding / outside
    Detection b = {320, 320, 480, 410, 0.5f, 0}; // -> (640, 360, 960, 540)
    v.push_back(a);
    v.push_back(b);
    unletterbox(v, lb);
    NEAR(v[0].x1, 0, 1e-3);
    NEAR(v[0].y1, 0, 1e-3);
    NEAR(v[0].x2, 1279, 1e-3);
    NEAR(v[0].y2, 719, 1e-3);
    NEAR(v[1].x1, 640, 1e-3);
    NEAR(v[1].y1, 360, 1e-3);
    NEAR(v[1].x2, 960, 1e-3);
    NEAR(v[1].y2, 540, 1e-3);
}

static void test_json()
{
    CHECK(json_escape("a\"b\\c\n\x01") == "a\\\"b\\\\c\\n\\u0001");
    CHECK(json_ready("yolov5.rknn", 640, 640, 812.44) ==
          "{\"ready\":true,\"model\":\"yolov5.rknn\",\"input\":[640,640],\"load_ms\":812.4}");
    CHECK(json_not_ready("rknn_init failed (ret=-1)") == "{\"ready\":false,\"error\":\"rknn_init failed (ret=-1)\"}");
    CHECK(json_error("cannot decode /x/\"y\".jpg") == "{\"ok\":false,\"error\":\"cannot decode /x/\\\"y\\\".jpg\"}");
    Timings t = {35.12, 12.0, 48.25, 3.1, 98.4};
    std::vector<std::string> labels;
    labels.push_back("person");
    std::vector<Detection> d;
    Detection a = {10.4f, 20.6f, 100.5f, 200.0f, 0.8712f, 0};
    Detection b = {1, 2, 3, 4, 0.5f, 5};  // no label -> "class5"
    d.push_back(a);
    d.push_back(b);
    std::string s = json_result(1280, 720, t, d, labels);
    const char *want =
        "{\"ok\":true,\"width\":1280,\"height\":720,\"ms\":{\"decode\":35.1,\"preprocess\":12.0,\"npu\":48.2,"
        "\"postprocess\":3.1,\"total\":98.4},\"objects\":[{\"label\":\"person\",\"class\":0,\"score\":0.871,"
        "\"box\":[10,21,101,200]},{\"label\":\"class5\",\"class\":5,\"score\":0.500,\"box\":[1,2,3,4]}]}";
    if (s != want) fprintf(stderr, "got  %s\nwant %s\n", s.c_str(), want);
    CHECK(s == want);
    CHECK(json_result(1, 1, t, std::vector<Detection>(), labels).find("\"objects\":[]}") != std::string::npos);
}

static void test_decode_files()
{
    Image img;
    std::string err, reason;
    CHECK(decode_image(TEST_DATA_DIR "/bus.jpg", 13000000, img, err, reason));
    CHECK(img.width == 640 && img.height == 640 && img.data);
    CHECK(decode_image(TEST_DATA_DIR "/bus_320x240.png", 13000000, img, err, reason));
    CHECK(img.width == 320 && img.height == 240);
    CHECK(!decode_image(TEST_DATA_DIR "/bus.jpg", 1000, img, err, reason));
    CHECK(err.find("image too large") == 0);
    CHECK(!decode_image("/nonexistent/x.jpg", 13000000, img, err, reason));
    CHECK(err == "cannot open /nonexistent/x.jpg");
    CHECK(!decode_image(TEST_DATA_DIR "/host_test.cpp", 13000000, img, err, reason));
    CHECK(err.find("cannot decode ") == 0);
}

int main()
{
    test_letterbox_math();
    test_letterbox_resize();
    test_decode(LAYOUT_NHWC, 0);
    test_decode(LAYOUT_NHWC, 1);   // runtime-padded channel stride (256)
    test_decode(LAYOUT_NCHW, 0);
    test_nms();
    test_unletterbox();
    test_json();
    test_decode_files();
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("host_test: all checks passed\n");
    return 0;
}
