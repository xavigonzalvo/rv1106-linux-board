// YOLOv5 int8 head decode + NMS.
//
// Reference (copied logic, not code): rknn_model_zoo @ 837db8e examples/yolov5/cpp/postprocess.cc
//   process_i8_rv1106()  -> NHWC branch below (RV1106 zero-copy, RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR)
//   process_i8()         -> NCHW branch below
// and LuckfoxTECH/luckfox_pico_rknn_example @ 16ef54a example/luckfox_pico_yolov5/src/postprocess.cc
// (same process_i8_rv1106, used with runtime 1.6.0 and the shipped yolov5.rknn).
//
// The model already applies sigmoid in-graph (Rockchip's yolov5 export), so outputs are probabilities:
//   x = (2*sx - 0.5 + col) * stride,  y = (2*sy - 0.5 + row) * stride,
//   w = (2*sw)^2 * anchor_w,          h = (2*sh)^2 * anchor_h
#include "postprocess.h"

#include <math.h>

#include <algorithm>

const int kYolov5Anchors[3][6] = {
    {10, 13, 16, 30, 33, 23},
    {30, 61, 62, 45, 59, 119},
    {116, 90, 156, 198, 373, 326},
};

static inline float deq(int8_t q, int32_t zp, float scale) { return ((float)q - (float)zp) * scale; }

// Largest int8 q with deq(q) <= f (conservative prefilter: anything that can pass the float test passes this).
static inline int8_t qnt_floor(float f, int32_t zp, float scale)
{
    float v = floorf(f / scale + (float)zp);
    if (v < -128) v = -128;
    if (v > 127) v = 127;
    return (int8_t)v;
}

void decode_head(const HeadTensor &t, int num_classes, float threshold, std::vector<Detection> &out)
{
    const int prop = 5 + num_classes;
    const int8_t thres_i8 = qnt_floor(threshold, t.zp, t.scale);

    for (int h = 0; h < t.grid_h; h++) {
        for (int w = 0; w < t.grid_w; w++) {
            for (int a = 0; a < 3; a++) {
                // elem(k) = value of channel (a*prop + k) at (h, w)
                const int8_t *p;
                int step;  // distance between two consecutive channels
                if (t.layout == LAYOUT_NHWC) {
                    p = t.data + (size_t)(h * t.grid_w + w) * t.stride + a * prop;
                    step = 1;
                } else {
                    p = t.data + (size_t)(a * prop) * t.stride + h * t.grid_w + w;
                    step = t.stride;
                }
                int8_t conf = p[4 * step];
                if (conf < thres_i8) continue;

                int8_t best = p[5 * step];
                int best_k = 0;
                for (int k = 1; k < num_classes; k++) {
                    int8_t v = p[(5 + k) * step];
                    if (v > best) {
                        best = v;
                        best_k = k;
                    }
                }
                float score = deq(conf, t.zp, t.scale) * deq(best, t.zp, t.scale);
                if (score <= threshold) continue;

                float bx = deq(p[0], t.zp, t.scale) * 2.0f - 0.5f;
                float by = deq(p[1 * step], t.zp, t.scale) * 2.0f - 0.5f;
                float bw = deq(p[2 * step], t.zp, t.scale) * 2.0f;
                float bh = deq(p[3 * step], t.zp, t.scale) * 2.0f;
                bx = (bx + w) * (float)t.stride_px;
                by = (by + h) * (float)t.stride_px;
                bw = bw * bw * (float)t.anchors[a * 2];
                bh = bh * bh * (float)t.anchors[a * 2 + 1];

                Detection d;
                d.x1 = bx - bw * 0.5f;
                d.y1 = by - bh * 0.5f;
                d.x2 = d.x1 + bw;
                d.y2 = d.y1 + bh;
                d.score = score;
                d.cls = best_k;
                out.push_back(d);
            }
        }
    }
}

static float iou(const Detection &a, const Detection &b)
{
    float iw = std::min(a.x2, b.x2) - std::max(a.x1, b.x1);
    float ih = std::min(a.y2, b.y2) - std::max(a.y1, b.y1);
    if (iw <= 0 || ih <= 0) return 0.f;
    float inter = iw * ih;
    float uni = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
    return uni <= 0 ? 0.f : inter / uni;
}

static bool by_score_desc(const Detection &a, const Detection &b) { return a.score > b.score; }

std::vector<Detection> nms(std::vector<Detection> cand, float iou_threshold, int max_det)
{
    std::stable_sort(cand.begin(), cand.end(), by_score_desc);
    std::vector<char> removed(cand.size(), 0);
    std::vector<Detection> keep;
    for (size_t i = 0; i < cand.size() && (int)keep.size() < max_det; i++) {
        if (removed[i]) continue;
        keep.push_back(cand[i]);
        for (size_t j = i + 1; j < cand.size(); j++) {
            if (!removed[j] && cand[j].cls == cand[i].cls && iou(cand[i], cand[j]) > iou_threshold) removed[j] = 1;
        }
    }
    return keep;
}

static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

void unletterbox(std::vector<Detection> &dets, const Letterbox &lb)
{
    const float fx = (float)lb.src_w / (float)lb.new_w;
    const float fy = (float)lb.src_h / (float)lb.new_h;
    const float maxx = (float)(lb.src_w - 1), maxy = (float)(lb.src_h - 1);
    for (size_t i = 0; i < dets.size(); i++) {
        Detection &d = dets[i];
        d.x1 = clampf((d.x1 - lb.pad_x) * fx, 0, maxx);
        d.x2 = clampf((d.x2 - lb.pad_x) * fx, 0, maxx);
        d.y1 = clampf((d.y1 - lb.pad_y) * fy, 0, maxy);
        d.y2 = clampf((d.y2 - lb.pad_y) * fy, 0, maxy);
    }
}
