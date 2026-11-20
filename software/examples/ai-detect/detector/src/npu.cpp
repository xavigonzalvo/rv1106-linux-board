// RKNN setup for RV1106 zero-copy inference.
//
// Follows, step by step:
//   rknn_model_zoo @ 837db8e examples/yolov5/cpp/rknpu2/yolov5_rv1106_1103.cc  (init_yolov5_model)
//   luckfox_pico_rknn_example @ 16ef54a example/luckfox_pico_yolov5/src/yolov5.cc (same, runtime 1.6.0)
// i.e.: rknn_init(path) -> RKNN_QUERY_NATIVE_INPUT_ATTR -> force UINT8/NHWC input -> rknn_create_mem(size_with_stride)
//       -> rknn_set_io_mem; outputs: RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR (the Luckfox variant, written for runtime
//       1.6.0 like the board has; the current model zoo, written for runtime 2.x, queries RKNN_QUERY_OUTPUT_ATTR and
//       decodes NCHW instead; both layouts are handled below by looking at attr.fmt) -> create_mem -> set_io_mem.
// UINT8 input type makes the NPU do the (x - mean) / std + quantisation baked into the model (mean 0, std 255, RGB).
#include "npu.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <algorithm>

static void dump_attr(const char *what, const rknn_tensor_attr &a)
{
    fprintf(stderr,
            "detector: %s index=%u name=%s n_dims=%u dims=[%u,%u,%u,%u] n_elems=%u size=%u w_stride=%u "
            "size_with_stride=%u fmt=%s type=%s qnt=%s zp=%d scale=%f\n",
            what, a.index, a.name, a.n_dims, a.dims[0], a.dims[1], a.dims[2], a.dims[3], a.n_elems, a.size,
            a.w_stride, a.size_with_stride, get_format_string(a.fmt), get_type_string(a.type),
            get_qnt_type_string(a.qnt_type), a.zp, a.scale);
}

static std::string strf(const char *f, int v)
{
    char buf[160];
    snprintf(buf, sizeof(buf), f, v);
    return buf;
}

Npu::~Npu()
{
    // model zoo order: free tensor memory first, then the context
    if (ctx_) {
        if (in_mem_) rknn_destroy_mem(ctx_, in_mem_);
        for (size_t i = 0; i < out_mems_.size(); i++)
            if (out_mems_[i]) rknn_destroy_mem(ctx_, out_mems_[i]);
        rknn_destroy(ctx_);
    }
}

static bool by_grid_desc(const HeadTensor &a, const HeadTensor &b) { return a.grid_h > b.grid_h; }

bool Npu::load(const char *model_path, std::string &err)
{
    int ret = rknn_init(&ctx_, (void *)model_path, 0, 0, NULL);  // size 0 => `model` is a file path
    if (ret < 0) {
        ctx_ = 0;
        err = strf("rknn_init failed (ret=%d)", ret);
        return false;
    }

    rknn_sdk_version ver;
    memset(&ver, 0, sizeof(ver));
    if (rknn_query(ctx_, RKNN_QUERY_SDK_VERSION, &ver, sizeof(ver)) == RKNN_SUCC)
        fprintf(stderr, "detector: rknn api %s, driver %s\n", ver.api_version, ver.drv_version);

    rknn_input_output_num io;
    memset(&io, 0, sizeof(io));
    ret = rknn_query(ctx_, RKNN_QUERY_IN_OUT_NUM, &io, sizeof(io));
    if (ret != RKNN_SUCC) {
        err = strf("rknn_query(IN_OUT_NUM) failed (ret=%d)", ret);
        return false;
    }
    if (io.n_input != 1 || io.n_output != 3) {
        err = "model must have 1 input and 3 outputs (YOLOv5 without in-graph postprocess), got " +
              strf("%d", (int)io.n_input) + "/" + strf("%d", (int)io.n_output);
        return false;
    }

    // ---- input ----
    rknn_tensor_attr in;
    memset(&in, 0, sizeof(in));
    in.index = 0;
    ret = rknn_query(ctx_, RKNN_QUERY_NATIVE_INPUT_ATTR, &in, sizeof(in));
    if (ret != RKNN_SUCC) {
        err = strf("rknn_query(NATIVE_INPUT_ATTR) failed (ret=%d)", ret);
        return false;
    }
    dump_attr("input ", in);
    int c;
    if (in.fmt == RKNN_TENSOR_NCHW) {
        c = in.dims[1];
        in_h_ = in.dims[2];
        in_w_ = in.dims[3];
    } else {
        in_h_ = in.dims[1];
        in_w_ = in.dims[2];
        c = in.dims[3];
    }
    if (c != 3 || in_w_ <= 0 || in_h_ <= 0) {
        err = "unexpected model input shape";
        return false;
    }
    // "default input type is int8 (normalize and quantize need compute in outside); if set uint8, will fuse
    //  normalize and quantize to npu" / "1106 npu only support NHWC in zero copy mode" (model zoo comments)
    in.type = RKNN_TENSOR_UINT8;
    in.fmt = RKNN_TENSOR_NHWC;
    int w_stride = in.w_stride ? (int)in.w_stride : in_w_;
    in_row_bytes_ = w_stride * 3;
    if (in.size_with_stride < (uint32_t)(in_row_bytes_ * in_h_)) {
        err = "input size_with_stride smaller than h*w_stride*3";
        return false;
    }
    in_mem_ = rknn_create_mem(ctx_, in.size_with_stride);
    if (!in_mem_) {
        err = "rknn_create_mem(input) failed";
        return false;
    }
    ret = rknn_set_io_mem(ctx_, in_mem_, &in);
    if (ret < 0) {
        err = strf("rknn_set_io_mem(input) failed (ret=%d)", ret);
        return false;
    }

    // ---- outputs ----
    out_attrs_.resize(io.n_output);
    out_mems_.assign(io.n_output, (rknn_tensor_mem *)0);
    for (uint32_t i = 0; i < io.n_output; i++) {
        rknn_tensor_attr &a = out_attrs_[i];
        memset(&a, 0, sizeof(a));
        a.index = i;
        ret = rknn_query(ctx_, RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR, &a, sizeof(a));
        if (ret != RKNN_SUCC) {
            err = strf("rknn_query(NATIVE_NHWC_OUTPUT_ATTR) failed (ret=%d)", ret);
            return false;
        }
        dump_attr("output", a);
        out_mems_[i] = rknn_create_mem(ctx_, a.size_with_stride);
        if (!out_mems_[i]) {
            err = "rknn_create_mem(output) failed";
            return false;
        }
        ret = rknn_set_io_mem(ctx_, out_mems_[i], &a);
        if (ret < 0) {
            err = strf("rknn_set_io_mem(output) failed (ret=%d)", ret);
            return false;
        }
    }

    // ---- describe heads for the decoder ----
    heads_.clear();
    for (size_t i = 0; i < out_attrs_.size(); i++) {
        const rknn_tensor_attr &a = out_attrs_[i];
        // RV1106 only supports int8 output (model zoo: "RV1106 only support i8")
        if (a.type != RKNN_TENSOR_INT8 || a.qnt_type != RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC) {
            err = "output tensors must be int8 affine-quantised";
            return false;
        }
        if (a.n_dims != 4) {
            err = "output tensors must be 4-D";
            return false;
        }
        HeadTensor t;
        memset(&t, 0, sizeof(t));
        t.data = (const int8_t *)out_mems_[i]->virt_addr;
        t.zp = a.zp;
        t.scale = a.scale;
        if (a.fmt == RKNN_TENSOR_NHWC) {
            t.layout = LAYOUT_NHWC;
            t.grid_h = a.dims[1];
            t.grid_w = a.dims[2];
            t.channels = a.dims[3];
            // Per-position channel stride = C (255), exactly as the Luckfox reference (postprocess.cc
            // process_i8_rv1106, align_c = 85 * 3). On board #1 (runtime 1.6.0) size_with_stride is H*W*256, but
            // that is tail padding: reading with stride 256 gives garbage (tested 2026-11-20). DETECTOR_OUT_STRIDE
            // overrides it for experiments.
            t.stride = t.channels;
            if (const char *s = getenv("DETECTOR_OUT_STRIDE")) t.stride = atoi(s);
        } else if (a.fmt == RKNN_TENSOR_NCHW) {
            t.layout = LAYOUT_NCHW;
            t.channels = a.dims[1];
            t.grid_h = a.dims[2];
            t.grid_w = a.dims[3];
            t.stride = t.grid_h * t.grid_w;
        } else {
            err = std::string("unsupported output layout ") + get_format_string(a.fmt) +
                  " (expected NHWC from RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR)";
            return false;
        }
        if (t.grid_h <= 0 || t.grid_w <= 0 || t.channels % 3 != 0 || t.channels / 3 <= 5) {
            err = "unexpected output shape";
            return false;
        }
        fprintf(stderr, "detector: head %zu: %s grid %dx%d C=%d stride=%d\n", i,
                t.layout == LAYOUT_NHWC ? "NHWC" : "NCHW", t.grid_h, t.grid_w, t.channels, t.stride);
        heads_.push_back(t);
    }
    num_classes_ = heads_[0].channels / 3 - 5;
    for (size_t i = 1; i < heads_.size(); i++) {
        if (heads_[i].channels != heads_[0].channels) {
            err = "output heads disagree on channel count";
            return false;
        }
    }
    // Assign anchors by grid size (largest grid = stride 8 = smallest anchors), independent of output order.
    std::stable_sort(heads_.begin(), heads_.end(), by_grid_desc);
    for (size_t i = 0; i < heads_.size(); i++) {
        heads_[i].anchors = kYolov5Anchors[i];
        heads_[i].stride_px = in_h_ / heads_[i].grid_h;
    }
    return true;
}

bool Npu::run(std::string &err)
{
    // rknn_run flushes/invalidates the zero-copy buffers itself by default (see RKNN_FLAG_DISABLE_FLUSH_*_MEM_CACHE
    // in newer rknn_api.h), so the explicit syncs are belt and braces; they are cheap.
    rknn_mem_sync(ctx_, in_mem_, RKNN_MEMORY_SYNC_TO_DEVICE);
    int ret = rknn_run(ctx_, NULL);
    if (ret < 0) {
        err = strf("rknn_run failed (ret=%d)", ret);
        return false;
    }
    for (size_t i = 0; i < out_mems_.size(); i++) rknn_mem_sync(ctx_, out_mems_[i], RKNN_MEMORY_SYNC_FROM_DEVICE);
    return true;
}
