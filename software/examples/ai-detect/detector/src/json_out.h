// JSON lines of PROTOCOL.md (ready line, success response, error response). No dependencies.
#pragma once

#include <string>
#include <vector>

#include "postprocess.h"

struct Timings {
    double decode, preprocess, npu, postprocess, total;  // milliseconds
};

std::string json_escape(const std::string &s);

// {"ready":true,"model":"yolov5.rknn","input":[640,640],"load_ms":812.4}
std::string json_ready(const std::string &model_name, int in_w, int in_h, double load_ms);
// {"ready":false,"error":"..."}
std::string json_not_ready(const std::string &error);
// {"ok":false,"error":"..."}
std::string json_error(const std::string &error);
// {"ok":true,"width":..,"height":..,"ms":{...},"objects":[...]}; dets in original-image coordinates, sorted.
std::string json_result(int width, int height, const Timings &t, const std::vector<Detection> &dets,
                        const std::vector<std::string> &labels);
