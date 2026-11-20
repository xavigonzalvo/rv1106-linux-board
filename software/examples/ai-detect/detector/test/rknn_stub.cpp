// Fake librknnmrt for the host: lets the real detector main loop run on the Mac (protocol / JSON / decode / letterbox
// end to end). Mimics RV1106 attrs: NHWC uint8 input 640x640x3, three int8 NHWC outputs 80/40/20 x 255.
// The "inference" puts one fixed box (class 0, score ~0.72) in the 80x80 head so a non-empty response is produced.
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>

#include "rknn_api.h"

struct StubCtx {
    rknn_tensor_mem *out[3];
};

static const int kGrid[3] = {80, 40, 20};

int rknn_init(rknn_context *context, void *model, uint32_t, uint32_t, rknn_init_extend *)
{
    if (!model || access((const char *)model, 0) != 0) return RKNN_ERR_MODEL_INVALID;
    StubCtx *c = (StubCtx *)calloc(1, sizeof(StubCtx));
    *context = (rknn_context)(uintptr_t)c;
    return RKNN_SUCC;
}

int rknn_destroy(rknn_context context)
{
    free((void *)(uintptr_t)context);
    return RKNN_SUCC;
}

int rknn_query(rknn_context, rknn_query_cmd cmd, void *info, uint32_t)
{
    switch (cmd) {
    case RKNN_QUERY_SDK_VERSION: {
        rknn_sdk_version *v = (rknn_sdk_version *)info;
        strcpy(v->api_version, "host-stub");
        strcpy(v->drv_version, "none");
        return RKNN_SUCC;
    }
    case RKNN_QUERY_IN_OUT_NUM: {
        rknn_input_output_num *n = (rknn_input_output_num *)info;
        n->n_input = 1;
        n->n_output = 3;
        return RKNN_SUCC;
    }
    case RKNN_QUERY_NATIVE_INPUT_ATTR: {
        rknn_tensor_attr *a = (rknn_tensor_attr *)info;
        a->n_dims = 4;
        a->dims[0] = 1; a->dims[1] = 640; a->dims[2] = 640; a->dims[3] = 3;
        a->fmt = RKNN_TENSOR_NHWC;
        a->type = RKNN_TENSOR_INT8;
        a->qnt_type = RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC;
        a->zp = -128; a->scale = 1.0f / 255;
        a->n_elems = a->size = a->size_with_stride = 640 * 640 * 3;
        a->w_stride = 640;
        strcpy(a->name, "images");
        return RKNN_SUCC;
    }
    case RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR: {
        rknn_tensor_attr *a = (rknn_tensor_attr *)info;
        int g = kGrid[a->index];
        a->n_dims = 4;
        a->dims[0] = 1; a->dims[1] = g; a->dims[2] = g; a->dims[3] = 255;
        a->fmt = RKNN_TENSOR_NHWC;
        a->type = RKNN_TENSOR_INT8;
        a->qnt_type = RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC;
        a->zp = -128; a->scale = 1.0f / 255;
        a->n_elems = a->size = a->size_with_stride = g * g * 255;
        strcpy(a->name, "out");
        return RKNN_SUCC;
    }
    default:
        return RKNN_ERR_PARAM_INVALID;
    }
}

rknn_tensor_mem *rknn_create_mem(rknn_context, uint32_t size)
{
    rknn_tensor_mem *m = (rknn_tensor_mem *)calloc(1, sizeof(rknn_tensor_mem));
    m->virt_addr = calloc(1, size);
    m->size = size;
    return m;
}

int rknn_destroy_mem(rknn_context, rknn_tensor_mem *mem)
{
    free(mem->virt_addr);
    free(mem);
    return RKNN_SUCC;
}

int rknn_set_io_mem(rknn_context context, rknn_tensor_mem *mem, rknn_tensor_attr *attr)
{
    StubCtx *c = (StubCtx *)(uintptr_t)context;
    if (attr->fmt == RKNN_TENSOR_NHWC && attr->dims[3] == 255) c->out[attr->index] = mem;
    return RKNN_SUCC;
}

int rknn_mem_sync(rknn_context, rknn_tensor_mem *, rknn_mem_sync_mode) { return RKNN_SUCC; }

int rknn_run(rknn_context context, rknn_run_extend *)
{
    StubCtx *c = (StubCtx *)(uintptr_t)context;
    for (int i = 0; i < 3; i++) memset(c->out[i]->virt_addr, (int8_t)-128, c->out[i]->size);  // all 0.0
    // one box at cell (40, 40) anchor 2 of the 80x80 head: centre (324, 324), size ~133x93 model px
    int8_t *p = (int8_t *)c->out[0]->virt_addr + (40 * 80 + 40) * 255 + 2 * 85;
    p[0] = p[1] = 0;      // 0.502 -> centre offset 0.5
    p[2] = p[3] = 127;    // ~1.0 -> (2*1)^2 * anchor
    p[4] = 102;           // conf 0.902
    p[5 + 0] = 76;        // person 0.8
    return RKNN_SUCC;
}
