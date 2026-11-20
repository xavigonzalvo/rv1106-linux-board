// RKNN (librknnmrt, RV1106 zero-copy API) wrapper for a 1-input / 3-output YOLOv5 model.
#pragma once

#include <stdint.h>

#include <string>
#include <vector>

#include "postprocess.h"
#include "rknn_api.h"

class Npu {
public:
    Npu() : ctx_(0), in_mem_(0), in_w_(0), in_h_(0), in_row_bytes_(0), num_classes_(0) {}
    ~Npu();

    // Load the model, set up zero-copy input/output buffers. On failure returns false and sets err.
    bool load(const char *model_path, std::string &err);

    int input_width() const { return in_w_; }
    int input_height() const { return in_h_; }
    int num_classes() const { return num_classes_; }

    // RGB888 NHWC input buffer (input_height() rows of input_row_bytes() bytes) to fill before run().
    uint8_t *input_buffer() const { return (uint8_t *)in_mem_->virt_addr; }
    int input_row_bytes() const { return in_row_bytes_; }

    // Run inference. After success, heads() describes the 3 outputs (sorted stride 8, 16, 32).
    bool run(std::string &err);
    const std::vector<HeadTensor> &heads() const { return heads_; }

private:
    rknn_context ctx_;
    rknn_tensor_mem *in_mem_;
    std::vector<rknn_tensor_mem *> out_mems_;
    std::vector<rknn_tensor_attr> out_attrs_;
    std::vector<HeadTensor> heads_;
    int in_w_, in_h_, in_row_bytes_;
    int num_classes_;
};
