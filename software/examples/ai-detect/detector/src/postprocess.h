// YOLOv5 output decoding, NMS and letterbox undo.
//
// Pure C++ (no RKNN headers) so it can be unit-tested on the host. The decode follows
// rknn_model_zoo examples/yolov5/cpp/postprocess.cc (process_i8_rv1106 for NHWC, process_i8 for NCHW),
// which is also what LuckfoxTECH/luckfox_pico_rknn_example example/luckfox_pico_yolov5/src/postprocess.cc ships.
#pragma once

#include <stdint.h>
#include <vector>

#include "letterbox.h"

enum TensorLayout {
    LAYOUT_NHWC = 0,  // [1, H, W, C]: what RV1106 gives for RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR
    LAYOUT_NCHW = 1,  // [1, C, H, W]: what non-native (RKNN_QUERY_OUTPUT_ATTR) outputs look like
};

// One YOLOv5 head output (int8, affine-quantised, one zp/scale for the whole tensor).
struct HeadTensor {
    const int8_t *data;
    TensorLayout layout;
    int grid_h;
    int grid_w;
    int channels;  // logical channels = 3 * (5 + num_classes) = 255 for COCO
    // NHWC: elements between two consecutive (h, w) positions (>= channels; > channels if the runtime pads C).
    // NCHW: elements between two consecutive channel planes (>= grid_h * grid_w).
    int stride;
    int32_t zp;
    float scale;
    const int *anchors;  // 6 values: w0 h0 w1 h1 w2 h2 (input-pixel units)
    int stride_px;       // model input pixels per grid cell (8 / 16 / 32)
};

struct Detection {
    float x1, y1, x2, y2;  // model-input coordinates before unletterbox(), original image after
    float score;
    int cls;
};

// Decode one head into candidates (model-input coordinates). score = obj_conf * max_class_prob,
// kept if score > threshold. Appends to out.
void decode_head(const HeadTensor &t, int num_classes, float threshold, std::vector<Detection> &out);

// Sort by score (desc) and run per-class greedy NMS. Returns at most max_det detections.
std::vector<Detection> nms(std::vector<Detection> cand, float iou_threshold, int max_det);

// Map boxes from the letterboxed model input back to the original image and clamp to [0, w-1] x [0, h-1].
void unletterbox(std::vector<Detection> &dets, const Letterbox &lb);

// Standard YOLOv5 COCO anchors, index 0 = stride 8 head (largest grid).
extern const int kYolov5Anchors[3][6];
