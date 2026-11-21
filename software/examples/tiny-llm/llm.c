/* Inference for Llama-2 Transformer model in pure C, int8 quantized forward pass.
 *
 * From karpathy/llama2.c runq.c (commit 350e04f, MIT licence, see LICENSE-llama2.c), changed for the
 * RV1106 board (Cortex-A7, single core, ~180 MB RAM). It runs Hugging Face Llama-architecture models converted
 * with convert_hf.py (SmolLM2-135M-Instruct); upstream's sentencepiece tokenizer and story/chat loops are removed.
 *   - the token embedding table stays int8 in the mmap and one row is dequantized per token
 *     (upstream makes a fp32 copy: +98 MB for stories110M)
 *   - the KV cache is sized for -n steps, not the model's full seq_len (upstream: 75 MB at seq_len 1024)
 *   - NEON int8 dot product in matmul(), with software prefetch of the weights (+48 % on the A7)
 *   - prints load time and the memory it allocated
 *   - fp16 KV cache (half the memory), no classifier matmul while reading the prompt
 *   - RoPE theta from the header, GPT-2 style byte-level BPE tokenizer (.tok file, exact merge order),
 *     ChatML chat (-m chat)
 */

#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <stdint.h>
#include <time.h>
#include <math.h>
#include <string.h>
#include <fcntl.h>
#if defined _WIN32
    #include "win.h"
#else
    #include <unistd.h>
    #include <sys/mman.h>
#endif
// ----------------------------------------------------------------------------
// Globals
long time_in_ms();
int GS = 0; // group size global for quantization of the weights
// extra header fields at byte 64 of the v2 header, written by convert_hf.py
float ROPE_THETA = 10000.0f;
int TOK_TYPE = 0;            // 0 = llama2.c sentencepiece tokenizer.bin, 1 = byte-level BPE .tok + ChatML
int IM_START = -1, IM_END = -1, EOT = -1;

// KV cache element: fp16 where the compiler has it (ARM), else fp32
#if defined(__ARM_FP16_FORMAT_IEEE) || defined(__aarch64__)
typedef __fp16 kv_t;
#else
typedef float kv_t;
#endif

// ----------------------------------------------------------------------------
// Transformer model

typedef struct {
    int dim; // transformer dimension
    int hidden_dim; // for ffn layers
    int n_layers; // number of layers
    int n_heads; // number of query heads
    int n_kv_heads; // number of key/value heads (can be < query heads because of multiquery)
    int vocab_size; // vocabulary size, usually 256 (byte-level)
    int seq_len; // max sequence length
} Config;

typedef struct {
    int8_t* q;    // quantized values
    float* s; // scaling factors
} QuantizedTensor;

typedef struct {
    // token embedding table
    QuantizedTensor *q_tokens; // (vocab_size, dim)

    // weights for rmsnorms
    float* rms_att_weight; // (layer, dim) rmsnorm weights
    float* rms_ffn_weight; // (layer, dim)
    // weights for matmuls. note dim == n_heads * head_size
    QuantizedTensor *wq; // (layer, dim, n_heads * head_size)
    QuantizedTensor *wk; // (layer, dim, n_kv_heads * head_size)
    QuantizedTensor *wv; // (layer, dim, n_kv_heads * head_size)
    QuantizedTensor *wo; // (layer, n_heads * head_size, dim)
    // weights for ffn
    QuantizedTensor *w1; // (layer, hidden_dim, dim)
    QuantizedTensor *w2; // (layer, dim, hidden_dim)
    QuantizedTensor *w3; // (layer, hidden_dim, dim)
    // final rmsnorm
    float* rms_final_weight; // (dim,)
    // (optional) classifier weights for the logits, on the last layer
    QuantizedTensor *wcls;
} TransformerWeights;

typedef struct {
    // current wave of activations
    float *x; // activation at current time stamp (dim,)
    float *xb; // same, but inside a residual branch (dim,)
    float *xb2; // an additional buffer just for convenience (dim,)
    float *hb; // buffer for hidden dimension in the ffn (hidden_dim,)
    float *hb2; // buffer for hidden dimension in the ffn (hidden_dim,)
    QuantizedTensor xq; // quantized x (dim,)
    QuantizedTensor hq; // quantized hb (hidden_dim,)
    float *q; // query (dim,)
    float *k; // key (dim,)
    float *v; // value (dim,)
    float *att; // buffer for scores/attention values (n_heads, seq_len)
    float *logits; // output logits
    // kv cache
    kv_t* key_cache;   // (layer, seq_len, kv_dim)
    kv_t* value_cache; // (layer, seq_len, kv_dim)
} RunState;

typedef struct {
    Config config; // the hyperparameters of the architecture (the blueprint)
    TransformerWeights weights; // the weights of the model
    RunState state; // buffers for the "wave" of activations in the forward pass
    // some more state needed to properly clean up the memory mapping (sigh)
    int fd; // file descriptor for memory mapping
    float* data; // memory mapped data pointer
    ssize_t file_size; // size of the checkpoint file in bytes
} Transformer;

void malloc_run_state(RunState* s, Config* p) {
    // we calloc instead of malloc to keep valgrind happy
    int kv_dim = (p->dim * p->n_kv_heads) / p->n_heads;
    s->x = calloc(p->dim, sizeof(float));
    s->xb = calloc(p->dim, sizeof(float));
    s->xb2 = calloc(p->dim, sizeof(float));
    s->hb = calloc(p->hidden_dim, sizeof(float));
    s->hb2 = calloc(p->hidden_dim, sizeof(float));
    s->xq = (QuantizedTensor) { .q = calloc(p->dim, sizeof(int8_t)), .s = calloc(p->dim, sizeof(float)) };
    s->hq = (QuantizedTensor) { .q = calloc(p->hidden_dim, sizeof(int8_t)), .s = calloc(p->hidden_dim, sizeof(float)) };
    s->q = calloc(p->dim, sizeof(float));
    s->k = calloc(kv_dim, sizeof(float));
    s->v = calloc(kv_dim, sizeof(float));
    s->att = calloc(p->n_heads * p->seq_len, sizeof(float));
    s->logits = calloc(p->vocab_size, sizeof(float));
    s->key_cache = calloc(p->n_layers * p->seq_len * kv_dim, sizeof(kv_t));
    s->value_cache = calloc(p->n_layers * p->seq_len * kv_dim, sizeof(kv_t));
    // ensure all mallocs went fine
    if (!s->x || !s->xb || !s->xb2 || !s->hb || !s->hb2 || !s->q
     || !s->k || !s->v || !s->att || !s->logits || !s->key_cache
     || !s->value_cache) {
        fprintf(stderr, "malloc failed!\n");
        exit(EXIT_FAILURE);
    }
}

void free_run_state(RunState* s) {
    free(s->x);
    free(s->xb);
    free(s->xb2);
    free(s->hb);
    free(s->hb2);
    free(s->xq.q);
    free(s->xq.s);
    free(s->hq.q);
    free(s->hq.s);
    free(s->q);
    free(s->k);
    free(s->v);
    free(s->att);
    free(s->logits);
    free(s->key_cache);
    free(s->value_cache);
}

// ----------------------------------------------------------------------------
// Quantization functions

void dequantize(QuantizedTensor *qx, float* x, int n) {
    for (int i = 0; i < n; i++) {
        x[i] = qx->q[i] * qx->s[i / GS];
    }
}

void quantize(QuantizedTensor *qx, float* x, int n) {
    int num_groups = n / GS;
    float Q_MAX = 127.0f;

    for (int group = 0; group < num_groups; group++) {

        // find the max absolute value in the current group
        float wmax = 0.0;
        for (int i = 0; i < GS; i++) {
            float val = fabs(x[group * GS + i]);
            if (val > wmax) {
                wmax = val;
            }
        }

        // calculate and write the scaling factor
        float scale = wmax / Q_MAX;
        qx->s[group] = scale;

        // calculate and write the quantized values
        for (int i = 0; i < GS; i++) {
            float quant_value = x[group * GS + i] / scale; // scale
            int8_t quantized = (int8_t) round(quant_value); // round and clamp
            qx->q[group * GS + i] = quantized;
        }
    }
}

/* initialize `n` x quantized tensor (with `size_each` elements), starting from memory pointed at *ptr */
QuantizedTensor *init_quantized_tensors(void **ptr, int n, int size_each) {
    void *p = *ptr;
    QuantizedTensor *res = malloc(n * sizeof(QuantizedTensor));
    for(int i=0; i<n; i++) {
        /* map quantized int8 values*/
        res[i].q = (int8_t*)p;
        p = (int8_t*)p + size_each;
        /* map scale factors */
        res[i].s = (float*)p;
        p = (float*)p + size_each / GS;
    }
    *ptr = p; // advance ptr to current position
    return res;
}

void memory_map_weights(TransformerWeights *w, Config* p, void* ptr, uint8_t shared_classifier) {
    int head_size = p->dim / p->n_heads;
    // first are the parameters that are kept in fp32 (the rmsnorm (1D) weights)
    float* fptr = (float*) ptr; // cast our pointer to float*
    w->rms_att_weight = fptr;
    fptr += p->n_layers * p->dim;
    w->rms_ffn_weight = fptr;
    fptr += p->n_layers * p->dim;
    w->rms_final_weight = fptr;
    fptr += p->dim;

    // now read all the quantized weights
    ptr = (void*)fptr; // now cast the pointer back to void*
    w->q_tokens = init_quantized_tensors(&ptr, 1, p->vocab_size * p->dim);

    w->wq = init_quantized_tensors(&ptr, p->n_layers, p->dim * (p->n_heads * head_size));
    w->wk = init_quantized_tensors(&ptr, p->n_layers, p->dim * (p->n_kv_heads * head_size));
    w->wv = init_quantized_tensors(&ptr, p->n_layers, p->dim * (p->n_kv_heads * head_size));
    w->wo = init_quantized_tensors(&ptr, p->n_layers, (p->n_heads * head_size) * p->dim);

    w->w1 = init_quantized_tensors(&ptr, p->n_layers, p->dim * p->hidden_dim);
    w->w2 = init_quantized_tensors(&ptr, p->n_layers, p->hidden_dim * p->dim);
    w->w3 = init_quantized_tensors(&ptr, p->n_layers, p->dim * p->hidden_dim);

    w->wcls = shared_classifier ? w->q_tokens : init_quantized_tensors(&ptr, 1, p->dim * p->vocab_size);
}

void read_checkpoint(char* checkpoint, Config* config, TransformerWeights* weights,
                     int* fd, float** data, ssize_t* file_size) {
    FILE *file = fopen(checkpoint, "rb");
    if (!file) { fprintf(stderr, "Couldn't open file %s\n", checkpoint); exit(EXIT_FAILURE); }
    // read in magic number (uint32), has to be 0x616b3432, i.e. "ak42" in ASCII
    uint32_t magic_number;
    if (fread(&magic_number, sizeof(uint32_t), 1, file) != 1) { exit(EXIT_FAILURE); }
    if (magic_number != 0x616b3432) { fprintf(stderr, "Bad magic number\n"); exit(EXIT_FAILURE); }
    // read in the version number (uint32), has to be 2
    int version;
    if (fread(&version, sizeof(int), 1, file) != 1) { exit(EXIT_FAILURE); }
    if (version != 2) { fprintf(stderr, "Bad version %d, need version 2\n", version); exit(EXIT_FAILURE); }
    int header_size = 256; // the header size for version 2 in bytes
    // read in the Config
    if (fread(config, sizeof(Config), 1, file) != 1) { exit(EXIT_FAILURE); }
    // read in flags
    uint8_t shared_classifier; // a byte to indicate if the classifier is shared
    if (fread(&shared_classifier, sizeof(uint8_t), 1, file) != 1) { exit(EXIT_FAILURE); }
    int group_size; // the group size used in quantization
    if (fread(&group_size, sizeof(int), 1, file) != 1) { exit(EXIT_FAILURE); }
    GS = group_size; // set as global, as it will be used in many places
    struct { float rope_theta; int tok_type, im_start, im_end, eot; } ext;
    fseek(file, 64, SEEK_SET);
    if (fread(&ext, sizeof(ext), 1, file) != 1) { exit(EXIT_FAILURE); }
    if (ext.rope_theta > 0) { ROPE_THETA = ext.rope_theta; }
    TOK_TYPE = ext.tok_type; IM_START = ext.im_start; IM_END = ext.im_end; EOT = ext.eot;
    // figure out the file size
    fseek(file, 0, SEEK_END); // move file pointer to end of file
    *file_size = ftell(file); // get the file size, in bytes
    fclose(file);
    // memory map the Transformer weights into the data pointer
    *fd = open(checkpoint, O_RDONLY); // open in read only mode
    if (*fd == -1) { fprintf(stderr, "open failed!\n"); exit(EXIT_FAILURE); }
    *data = mmap(NULL, *file_size, PROT_READ, MAP_PRIVATE, *fd, 0);
    if (*data == MAP_FAILED) { fprintf(stderr, "mmap failed!\n"); exit(EXIT_FAILURE); }
    // Warm the page cache with one sequential read. Faulting the mmap in 4 kB at a time from the microSD
    // took 228 s for SmolLM2 (143 MB) on the board; a straight read takes seconds. LLM_NO_WARM=1 skips it.
    if (!getenv("LLM_NO_WARM")) {
        long t0 = time_in_ms();
        char* buf = malloc(1 << 20);
        if (buf) { while (read(*fd, buf, 1 << 20) > 0) {} free(buf); }
        long dt = time_in_ms() - t0;
        if (dt > 500) fprintf(stderr, "read model into the page cache: %.1f s\n", dt / 1000.0);
    }
    void* weights_ptr = ((char*)*data) + header_size; // skip header bytes. char is 1 byte
    memory_map_weights(weights, config, weights_ptr, shared_classifier);
}

void build_transformer(Transformer *t, char* checkpoint_path, int max_steps) {
    // read in the Config and the Weights from the checkpoint
    read_checkpoint(checkpoint_path, &t->config, &t->weights, &t->fd, &t->data, &t->file_size);
    // only keep room in the KV cache / attention buffer for the steps we will run
    if (max_steps > 0 && max_steps < t->config.seq_len) { t->config.seq_len = max_steps; }
    // allocate the RunState buffers
    malloc_run_state(&t->state, &t->config);
}

void free_transformer(Transformer* t) {
    // free QuantizedTensors
    free(t->weights.q_tokens);
    free(t->weights.wq);
    free(t->weights.wk);
    free(t->weights.wv);
    free(t->weights.wo);
    free(t->weights.w1);
    free(t->weights.w2);
    free(t->weights.w3);
    if(t->weights.wcls != t->weights.q_tokens) { free(t->weights.wcls); }
    // close the memory mapping
    if (t->data != MAP_FAILED) { munmap(t->data, t->file_size); }
    if (t->fd != -1) { close(t->fd); }
    // free the RunState buffers
    free_run_state(&t->state);
}

// ----------------------------------------------------------------------------
// neural net blocks; the dynamics of the Transformer

void rmsnorm(float* o, float* x, float* weight, int size) {
    // calculate sum of squares
    float ss = 0.0f;
    for (int j = 0; j < size; j++) {
        ss += x[j] * x[j];
    }
    ss /= size;
    ss += 1e-5f;
    ss = 1.0f / sqrtf(ss);
    // normalize and scale
    for (int j = 0; j < size; j++) {
        o[j] = weight[j] * (ss * x[j]);
    }
}

void softmax(float* x, int size) {
    // find max value (for numerical stability)
    float max_val = x[0];
    for (int i = 1; i < size; i++) {
        if (x[i] > max_val) {
            max_val = x[i];
        }
    }
    // exp and sum
    float sum = 0.0f;
    for (int i = 0; i < size; i++) {
        x[i] = expf(x[i] - max_val);
        sum += x[i];
    }
    // normalize
    for (int i = 0; i < size; i++) {
        x[i] /= sum;
    }
}

#if (defined(__ARM_NEON) || defined(__ARM_NEON__)) && !defined(LLM_NO_NEON)  // -DLLM_NO_NEON: plain C, for A/B timing
#include <arm_neon.h>
#ifndef LLM_PREFETCH
#define LLM_PREFETCH 1024  // bytes ahead; measured on board #1 (stories110M): none 2.34, 128 3.21, 1024 3.47, 4096 3.42 tok/s
#endif
// int8 dot product of one group (len a multiple of 16): 16 products per step,
// pairs summed in int16 (2*127*127 fits), then widened into int32 lanes
static inline int32_t dot_i8(const int8_t* a, const int8_t* b, int len) {
    int32x4_t acc = vdupq_n_s32(0);
    for (int k = 0; k < len; k += 16) {
#if LLM_PREFETCH > 0
        __builtin_prefetch(b + k + LLM_PREFETCH);  // A7's hardware prefetcher is weak: ask for weights ahead
#endif
        int8x16_t va = vld1q_s8(a + k), vb = vld1q_s8(b + k);
        int16x8_t p = vmull_s8(vget_low_s8(va), vget_low_s8(vb));
        p = vmlal_s8(p, vget_high_s8(va), vget_high_s8(vb));
        acc = vpadalq_s16(acc, p);
    }
    int32x2_t s2 = vadd_s32(vget_low_s32(acc), vget_high_s32(acc));
    return vget_lane_s32(vpadd_s32(s2, s2), 0);
}
#define HAVE_DOT_I8 1
#endif

void matmul(float* xout, QuantizedTensor *x, QuantizedTensor *w, int n, int d) {
    // W (d,n) @ x (n,) -> xout (d,)
    // by far the most amount of time is spent inside this little function
    // inputs to this function are both quantized

    int i;
    #pragma omp parallel for private(i)
    for (i = 0; i < d; i++) {

        float val = 0.0f;
        int32_t ival = 0;
        int in = i * n;

        // do the matmul in groups of GS
        int j;
        for (j = 0; j <= n - GS; j += GS) {
#ifdef HAVE_DOT_I8
            if ((GS & 15) == 0) { ival = dot_i8(x->q + j, w->q + in + j, GS); } else
#endif
            for (int k = 0; k < GS; k++) {
                ival += ((int32_t) x->q[j + k]) * ((int32_t) w->q[in + j + k]);
            }
            val += ((float) ival) * w->s[(in + j) / GS] * x->s[j / GS];
            ival = 0;
        }

        xout[i] = val;
    }
}

// want_logits = 0: only fill the KV cache (prompt tokens), skip the vocab-size classifier matmul
float* forward_ex(Transformer* transformer, int token, int pos, int want_logits) {

    // a few convenience variables
    Config* p = &transformer->config;
    TransformerWeights* w = &transformer->weights;
    RunState* s = &transformer->state;
    float *x = s->x;
    int dim = p->dim;
    int kv_dim = (p->dim * p->n_kv_heads) / p->n_heads;
    int kv_mul = p->n_heads / p->n_kv_heads; // integer multiplier of the kv sharing in multiquery
    int hidden_dim =  p->hidden_dim;
    int head_size = dim / p->n_heads;

    // copy the token embedding into x
    // (dequantize just this row of the int8 embedding table)
    for (int i = 0; i < dim; i++) {
        int k = token * dim + i;
        x[i] = w->q_tokens->q[k] * w->q_tokens->s[k / GS];
    }

    // forward all the layers
    for(int l = 0; l < p->n_layers; l++) {

        // attention rmsnorm
        rmsnorm(s->xb, x, w->rms_att_weight + l*dim, dim);

        // qkv matmuls for this position
        quantize(&s->xq, s->xb, dim);
        matmul(s->q, &s->xq, w->wq + l, dim, dim);
        matmul(s->k, &s->xq, w->wk + l, dim, kv_dim);
        matmul(s->v, &s->xq, w->wv + l, dim, kv_dim);

        // RoPE relative positional encoding: complex-valued rotate q and k in each head
        for (int i = 0; i < dim; i+=2) {
            int head_dim = i % head_size;
            float freq = 1.0f / powf(ROPE_THETA, head_dim / (float)head_size);
            float val = pos * freq;
            float fcr = cosf(val);
            float fci = sinf(val);
            int rotn = i < kv_dim ? 2 : 1; // how many vectors? 2 = q & k, 1 = q only
            for (int v = 0; v < rotn; v++) {
                float* vec = v == 0 ? s->q : s->k; // the vector to rotate (query or key)
                float v0 = vec[i];
                float v1 = vec[i+1];
                vec[i]   = v0 * fcr - v1 * fci;
                vec[i+1] = v0 * fci + v1 * fcr;
            }
        }

        // save key,value at this time step (pos) to our kv cache
        int loff = l * p->seq_len * kv_dim; // kv cache layer offset for convenience
        kv_t* key_cache_row = s->key_cache + loff + pos * kv_dim;
        kv_t* value_cache_row = s->value_cache + loff + pos * kv_dim;
        for (int i = 0; i < kv_dim; i++) { key_cache_row[i] = s->k[i]; value_cache_row[i] = s->v[i]; }

        // multihead attention. iterate over all heads
        int h;
        #pragma omp parallel for private(h)
        for (h = 0; h < p->n_heads; h++) {
            // get the query vector for this head
            float* q = s->q + h * head_size;
            // attention scores for this head
            float* att = s->att + h * p->seq_len;
            // iterate over all timesteps, including the current one
            for (int t = 0; t <= pos; t++) {
                // get the key vector for this head and at this timestep
                kv_t* k = s->key_cache + loff + t * kv_dim + (h / kv_mul) * head_size;
                // calculate the attention score as the dot product of q and k
                float score = 0.0f;
                for (int i = 0; i < head_size; i++) {
                    score += q[i] * k[i];
                }
                score /= sqrtf(head_size);
                // save the score to the attention buffer
                att[t] = score;
            }

            // softmax the scores to get attention weights, from 0..pos inclusively
            softmax(att, pos + 1);

            // weighted sum of the values, store back into xb
            float* xb = s->xb + h * head_size;
            memset(xb, 0, head_size * sizeof(float));
            for (int t = 0; t <= pos; t++) {
                // get the value vector for this head and at this timestep
                kv_t* v = s->value_cache + loff + t * kv_dim + (h / kv_mul) * head_size;
                // get the attention weight for this timestep
                float a = att[t];
                // accumulate the weighted value into xb
                for (int i = 0; i < head_size; i++) {
                    xb[i] += a * v[i];
                }
            }
        }

        // final matmul to get the output of the attention
        quantize(&s->xq, s->xb, dim);
        matmul(s->xb2, &s->xq, w->wo + l, dim, dim);

        // residual connection back into x
        for (int i = 0; i < dim; i++) {
            x[i] += s->xb2[i];
        }

        // ffn rmsnorm
        rmsnorm(s->xb, x, w->rms_ffn_weight + l*dim, dim);

        // Now for FFN in PyTorch we have: self.w2(F.silu(self.w1(x)) * self.w3(x))
        // first calculate self.w1(x) and self.w3(x)
        quantize(&s->xq, s->xb, dim);
        matmul(s->hb, &s->xq, w->w1 + l, dim, hidden_dim);
        matmul(s->hb2, &s->xq, w->w3 + l, dim, hidden_dim);

        // SwiGLU non-linearity
        for (int i = 0; i < hidden_dim; i++) {
            float val = s->hb[i];
            // silu(x)=x*σ(x), where σ(x) is the logistic sigmoid
            val *= (1.0f / (1.0f + expf(-val)));
            // elementwise multiply with w3(x)
            val *= s->hb2[i];
            s->hb[i] = val;
        }

        // final matmul to get the output of the ffn
        quantize(&s->hq, s->hb, hidden_dim);
        matmul(s->xb, &s->hq, w->w2 + l, hidden_dim, dim);

        // residual connection
        for (int i = 0; i < dim; i++) {
            x[i] += s->xb[i];
        }
    }

    if (!want_logits) { return NULL; }

    // final rmsnorm
    rmsnorm(x, x, w->rms_final_weight, dim);

    // classifier into logits
    quantize(&s->xq, x, dim);
    matmul(s->logits, &s->xq, w->wcls, dim, p->vocab_size);
    return s->logits;
}

float* forward(Transformer* transformer, int token, int pos) { return forward_ex(transformer, token, pos, 1); }

// ----------------------------------------------------------------------------
// The Sampler, which takes logits and returns a sampled token
// sampling can be done in a few ways: greedy argmax, sampling, top-p sampling

typedef struct {
    float prob;
    int index;
} ProbIndex; // struct used when sorting probabilities during top-p sampling

typedef struct {
    int vocab_size;
    ProbIndex* probindex; // buffer used in top-p sampling
    float temperature;
    float topp;
    unsigned long long rng_state;
} Sampler;

int sample_argmax(float* probabilities, int n) {
    // return the index that has the highest probability
    int max_i = 0;
    float max_p = probabilities[0];
    for (int i = 1; i < n; i++) {
        if (probabilities[i] > max_p) {
            max_i = i;
            max_p = probabilities[i];
        }
    }
    return max_i;
}

int sample_mult(float* probabilities, int n, float coin) {
    // sample index from probabilities (they must sum to 1!)
    // coin is a random number in [0, 1), usually from random_f32()
    float cdf = 0.0f;
    for (int i = 0; i < n; i++) {
        cdf += probabilities[i];
        if (coin < cdf) {
            return i;
        }
    }
    return n - 1; // in case of rounding errors
}

int compare(const void* a, const void* b) {
    ProbIndex* a_ = (ProbIndex*) a;
    ProbIndex* b_ = (ProbIndex*) b;
    if (a_->prob > b_->prob) return -1;
    if (a_->prob < b_->prob) return 1;
    return 0;
}

int sample_topp(float* probabilities, int n, float topp, ProbIndex* probindex, float coin) {
    // top-p sampling (or "nucleus sampling") samples from the smallest set of
    // tokens that exceed probability topp. This way we never sample tokens that
    // have very low probabilities and are less likely to go "off the rails".
    // coin is a random number in [0, 1), usually from random_f32()

    int n0 = 0;
    // quicksort indices in descending order of probabilities
    // values smaller than (1 - topp) / (n - 1) cannot be part of the result
    // so for efficiency we crop these out as candidates before sorting
    const float cutoff = (1.0f - topp) / (n - 1);
    for (int i = 0; i < n; i++) {
        if (probabilities[i] >= cutoff) {
            probindex[n0].index = i;
            probindex[n0].prob = probabilities[i];
            n0++;
        }
    }
    qsort(probindex, n0, sizeof(ProbIndex), compare);

    // truncate the list where cumulative probability exceeds topp
    float cumulative_prob = 0.0f;
    int last_idx = n0 - 1; // in case of rounding errors consider all elements
    for (int i = 0; i < n0; i++) {
        cumulative_prob += probindex[i].prob;
        if (cumulative_prob > topp) {
            last_idx = i;
            break; // we've exceeded topp by including last_idx
        }
    }

    // sample from the truncated list
    float r = coin * cumulative_prob;
    float cdf = 0.0f;
    for (int i = 0; i <= last_idx; i++) {
        cdf += probindex[i].prob;
        if (r < cdf) {
            return probindex[i].index;
        }
    }
    return probindex[last_idx].index; // in case of rounding errors
}

void build_sampler(Sampler* sampler, int vocab_size, float temperature, float topp, unsigned long long rng_seed) {
    sampler->vocab_size = vocab_size;
    sampler->temperature = temperature;
    sampler->topp = topp;
    sampler->rng_state = rng_seed;
    // buffer only used with nucleus sampling; may not need but it's ~small
    sampler->probindex = malloc(sampler->vocab_size * sizeof(ProbIndex));
}

void free_sampler(Sampler* sampler) {
    free(sampler->probindex);
}

unsigned int random_u32(unsigned long long *state) {
    // xorshift rng: https://en.wikipedia.org/wiki/Xorshift#xorshift.2A
    *state ^= *state >> 12;
    *state ^= *state << 25;
    *state ^= *state >> 27;
    return (*state * 0x2545F4914F6CDD1Dull) >> 32;
}
float random_f32(unsigned long long *state) { // random float32 in [0,1)
    return (random_u32(state) >> 8) / 16777216.0f;
}

int sample(Sampler* sampler, float* logits) {
    // sample the token given the logits and some hyperparameters
    int next;
    if (sampler->temperature == 0.0f) {
        // greedy argmax sampling: take the token with the highest probability
        next = sample_argmax(logits, sampler->vocab_size);
    } else {
        // apply the temperature to the logits
        for (int q=0; q<sampler->vocab_size; q++) { logits[q] /= sampler->temperature; }
        // apply softmax to the logits to get the probabilities for next token
        softmax(logits, sampler->vocab_size);
        // flip a (float) coin (this is our source of entropy for sampling)
        float coin = random_f32(&sampler->rng_state);
        // we sample from this distribution to get the next token
        if (sampler->topp <= 0 || sampler->topp >= 1) {
            // simply sample from the predicted probability distribution
            next = sample_mult(logits, sampler->vocab_size, coin);
        } else {
            // top-p (nucleus) sampling, clamping the least likely tokens to zero
            next = sample_topp(logits, sampler->vocab_size, sampler->topp, sampler->probindex, coin);
        }
    }
    return next;
}

// ----------------------------------------------------------------------------
// utilities: time

long time_in_ms() {
    // return time in milliseconds, for benchmarking the model speed
    struct timespec time;
    clock_gettime(CLOCK_REALTIME, &time);
    return time.tv_sec * 1000 + time.tv_nsec / 1000000;
}

// ----------------------------------------------------------------------------
// CLI, include only if not testing
#ifndef TESTING


// ----------------------------------------------------------------------------
// Byte-level BPE tokenizer (GPT-2 / SmolLM2 style), from the .tok file written by convert_hf.py.
// Encoding is exact BPE: text is split like the GPT-2 regex (+ single digits), each piece starts as bytes,
// and the adjacent pair with the lowest merge rank is merged until none is left.

typedef struct {
    int n, max_len;
    unsigned char** str; int* len; int* rank;
    int byte_id[256];
    uint64_t* hkey; int* hval; int hmask;   // (left,right) -> merged token
} Bpe;

static uint64_t bpe_key(int a, int b) { return ((uint64_t)(uint32_t)a << 32) | (uint32_t)b; }
static uint32_t bpe_hash(uint64_t k) { k ^= k >> 29; k *= 0xbf58476d1ce4e5b9ULL; k ^= k >> 32; return (uint32_t)k; }

void build_bpe(Bpe* t, const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "couldn't load %s\n", path); exit(EXIT_FAILURE); }
    char magic[4];
    if (fread(magic, 4, 1, f) != 1 || memcmp(magic, "BPE1", 4) || fread(&t->n, 4, 1, f) != 1 || fread(&t->max_len, 4, 1, f) != 1) {
        fprintf(stderr, "%s: not a BPE1 tokenizer (convert_hf.py)\n", path); exit(EXIT_FAILURE);
    }
    t->str = malloc(t->n * sizeof(char*)); t->len = malloc(t->n * sizeof(int)); t->rank = malloc(t->n * sizeof(int));
    for (int i = 0; i < 256; i++) t->byte_id[i] = -1;
    t->hmask = 1; while (t->hmask < 2 * t->n) t->hmask <<= 1; t->hmask--;
    t->hkey = calloc(t->hmask + 1, sizeof(uint64_t)); t->hval = malloc((t->hmask + 1) * sizeof(int));
    for (int i = 0; i <= t->hmask; i++) t->hval[i] = -1;
    for (int i = 0; i < t->n; i++) {
        int lr[3];
        if (fread(&t->len[i], 4, 1, f) != 1) { fprintf(stderr, "%s truncated\n", path); exit(EXIT_FAILURE); }
        t->str[i] = malloc(t->len[i] + 1);
        if (fread(t->str[i], 1, t->len[i], f) != (size_t)t->len[i] || fread(lr, 4, 3, f) != 3) { fprintf(stderr, "%s truncated\n", path); exit(EXIT_FAILURE); }
        t->str[i][t->len[i]] = 0;
        t->rank[i] = lr[0];
        if (t->len[i] == 1 && lr[0] < 0) t->byte_id[t->str[i][0]] = i;
        if (lr[0] >= 0) {
            uint32_t h = bpe_hash(bpe_key(lr[1], lr[2])) & t->hmask;
            while (t->hval[h] >= 0) h = (h + 1) & t->hmask;
            t->hkey[h] = bpe_key(lr[1], lr[2]); t->hval[h] = i;
        }
    }
    fclose(f);
}

static int bpe_merge(Bpe* t, int a, int b) {
    uint64_t k = bpe_key(a, b);
    for (uint32_t h = bpe_hash(k) & t->hmask; t->hval[h] >= 0; h = (h + 1) & t->hmask)
        if (t->hkey[h] == k) return t->hval[h];
    return -1;
}

static int is_sp(unsigned char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f'; }
static int is_dg(unsigned char c) { return c >= '0' && c <= '9'; }
static int is_lt(unsigned char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c >= 0x80; } // non-ASCII = letter
static int is_pu(unsigned char c) { return !is_sp(c) && !is_dg(c) && !is_lt(c); }

// length of the next pre-token at s[0..n), following ByteLevel's regex
//   's|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+   after Digits(individual)
static int pretoken_len(const unsigned char* s, int n) {
    if (s[0] == '\'' && n >= 2) {
        if (n >= 3 && ((s[1] == 'r' && s[2] == 'e') || (s[1] == 'v' && s[2] == 'e') || (s[1] == 'l' && s[2] == 'l'))) return 3;
        if (s[1] == 's' || s[1] == 't' || s[1] == 'm' || s[1] == 'd') return 2;
    }
    if (is_dg(s[0])) return 1;
    int i = (s[0] == ' ' && n >= 2 && (is_lt(s[1]) || is_pu(s[1]))) ? 1 : 0;
    if (is_lt(s[i])) { while (i < n && is_lt(s[i])) i++; return i; }
    if (is_pu(s[i])) { while (i < n && is_pu(s[i])) i++; return i; }
    // whitespace run: leave the last char for the next word if it is a space before a letter/punct
    int j = 0; while (j < n && is_sp(s[j])) j++;
    if (j < n && !is_dg(s[j])) {            // followed by non-space (a digit ends a Digits piece instead)
        if (j > 1) return j - 1;
        return 1;                            // single '\n' etc. before a word stands alone
    }
    return j;
}

// encode text, append to tokens[*n] (no BOS/EOS)
void bpe_encode(Bpe* t, const char* text, int* tokens, int* n) {
    const unsigned char* s = (const unsigned char*)text;
    int len = strlen(text);
    while (len > 0) {
        int m = pretoken_len(s, len);
        int start = *n;
        for (int i = 0; i < m; i++) tokens[(*n)++] = t->byte_id[s[i]];
        for (;;) {
            int best = -1, best_rank = 0x7fffffff, best_id = -1;
            for (int i = start; i < *n - 1; i++) {
                int id = bpe_merge(t, tokens[i], tokens[i + 1]);
                if (id >= 0 && t->rank[id] < best_rank) { best_rank = t->rank[id]; best = i; best_id = id; }
            }
            if (best < 0) break;
            tokens[best] = best_id;
            memmove(tokens + best + 1, tokens + best + 2, (*n - best - 2) * sizeof(int));
            (*n)--;
        }
        s += m; len -= m;
    }
}

void bpe_print(Bpe* t, int id) {
    if (id >= 0 && id < t->n && t->len[id] > 0) { fwrite(t->str[id], 1, t->len[id], stdout); fflush(stdout); }
}

// plain continuation of -i text (no chat template)
void generate_bpe(Transformer* tr, Bpe* t, Sampler* sampler, const char* prompt, int steps) {
    int* toks = malloc((strlen(prompt) + 1) * sizeof(int)); int n = 0;
    bpe_encode(t, prompt, toks, &n);
    if (n == 0) { fprintf(stderr, "empty prompt\n"); exit(EXIT_FAILURE); }
    if (n >= steps) { fprintf(stderr, "prompt is %d tokens; -n %d leaves no room to generate\n", n, steps); exit(EXIT_FAILURE); }
    if (getenv("LLM_SHOW_TOKENS")) { for (int i = 0; i < n; i++) printf("%d ", toks[i]); printf("\n"); exit(0); }  // test hook
    fwrite(prompt, 1, strlen(prompt), stdout);
    long start = 0; int pos = 0, gen = 0;
    for (; pos < n - 1; pos++) forward_ex(tr, toks[pos], pos, 0);
    int token = toks[n - 1];
    while (pos < steps) {
        float* logits = forward(tr, token, pos++);
        if (start == 0) start = time_in_ms();
        token = sample(sampler, logits);
        if (token == EOT || token == IM_END) break;
        bpe_print(t, token); gen++;
    }
    printf("\n");
    if (gen > 1) fprintf(stderr, "achieved tok/s: %f\n", (gen - 1) / (double)(time_in_ms() - start) * 1000);
    free(toks);
}

// ChatML: <|im_start|>role\ncontent<|im_end|>\n ... <|im_start|>assistant\n
void chat_ml(Transformer* tr, Bpe* t, Sampler* sampler, const char* cli_user, const char* sys, int steps) {
    char user[2048], text[2100];
    // one turn is at most "system\n"+sys and "user\n"+user (each < sizeof(text) bytes, >= 1 byte per token) + 8 ids
    int* toks = malloc((2 * sizeof(text) + 16) * sizeof(int));
    int pos = 0, turn = 0;
    if (!sys) sys = "You are a helpful AI assistant named SmolLM, trained by Hugging Face";
    for (;;) {
        if (turn == 0 && cli_user) { snprintf(user, sizeof(user), "%s", cli_user); }
        else {
            printf("\n> "); fflush(stdout);
            if (!fgets(user, sizeof(user), stdin)) break;
            size_t l = strlen(user); if (l && user[l - 1] == '\n') user[--l] = 0;
            if (l == 0) continue;
            if (!strcmp(user, "/quit") || !strcmp(user, "/exit")) break;
        }
        int n = 0;
        if (turn == 0) {
            toks[n++] = IM_START;
            snprintf(text, sizeof(text), "system\n%s", sys); bpe_encode(t, text, toks, &n);
            toks[n++] = IM_END; bpe_encode(t, "\n", toks, &n);
        } else {
            toks[n++] = IM_END; bpe_encode(t, "\n", toks, &n);   // close the previous assistant turn
        }
        toks[n++] = IM_START;
        snprintf(text, sizeof(text), "user\n%s", user); bpe_encode(t, text, toks, &n);
        toks[n++] = IM_END; bpe_encode(t, "\n", toks, &n);
        toks[n++] = IM_START; bpe_encode(t, "assistant\n", toks, &n);
        if (pos + n + 1 >= steps) { printf("[context full: %d of %d tokens used; restart, or raise -n]\n", pos, steps); break; }
        long t0 = time_in_ms();
        for (int i = 0; i < n - 1; i++) forward_ex(tr, toks[i], pos++, 0);
        float* logits = forward(tr, toks[n - 1], pos++);
        long t1 = time_in_ms(); int gen = 0;
        for (;;) {
            int next = sample(sampler, logits);
            if (next == IM_END || next == EOT) break;
            if (pos >= steps) { printf(" [context full]"); break; }
            bpe_print(t, next); gen++;
            logits = forward(tr, next, pos++);
        }
        long t2 = time_in_ms();
        fprintf(stderr, "\n[prompt %d tok %.1f s, reply %d tok %.1f tok/s, context %d/%d]", n, (t1 - t0) / 1000.0,
                gen, gen ? gen / ((t2 - t1) / 1000.0) : 0.0, pos, steps);
        if (pos >= steps) break;
        turn++;
    }
    printf("\n");
    free(toks);
}


void error_usage() {
    fprintf(stderr, "Usage:   llm <model.bin> [options]\n");
    fprintf(stderr, "Example: llm smollm2-135m-instruct.bin -m chat -n 512 -t 0.3\n");
    fprintf(stderr, "Options:\n");
    fprintf(stderr, "  -t <float>  temperature in [0,inf], default 1.0\n");
    fprintf(stderr, "  -p <float>  p value in top-p (nucleus) sampling in [0,1] default 0.9\n");
    fprintf(stderr, "  -s <int>    random seed, default time(NULL)\n");
    fprintf(stderr, "  -n <int>    number of steps to run for, default 256. 0 = max_seq_len\n");
    fprintf(stderr, "  -i <string> input prompt\n");
    fprintf(stderr, "  -z <string> tokenizer, default: <model>.tok\n");
    fprintf(stderr, "  -m <string> mode: generate (continue -i text) | chat, default: generate\n");
    fprintf(stderr, "  -y <string> (optional) system prompt in chat mode\n");
    fprintf(stderr, "Models come from convert_hf.py. In chat, type /quit to leave.\n");
    exit(EXIT_FAILURE);
}

int main(int argc, char *argv[]) {

    // default parameters
    char *checkpoint_path = NULL;  // e.g. out/model.bin
    char *tokenizer_path = NULL;   // default: the checkpoint path with .bin -> .tok
    float temperature = 1.0f;   // 0.0 = greedy deterministic. 1.0 = original. don't set higher
    float topp = 0.9f;          // top-p in nucleus sampling. 1.0 = off. 0.9 works well, but slower
    int steps = 256;            // number of steps to run for
    char *prompt = NULL;        // prompt string
    unsigned long long rng_seed = 0; // seed rng with time by default
    char *mode = "generate";    // generate|chat
    char *system_prompt = NULL; // the (optional) system prompt to use in chat mode

    // poor man's C argparse so we can override the defaults above from the command line
    if (argc >= 2) { checkpoint_path = argv[1]; } else { error_usage(); }
    for (int i = 2; i < argc; i+=2) {
        // do some basic validation
        if (i + 1 >= argc) { error_usage(); } // must have arg after flag
        if (argv[i][0] != '-') { error_usage(); } // must start with dash
        if (strlen(argv[i]) != 2) { error_usage(); } // must be -x (one dash, one letter)
        // read in the args
        if (argv[i][1] == 't') { temperature = atof(argv[i + 1]); }
        else if (argv[i][1] == 'p') { topp = atof(argv[i + 1]); }
        else if (argv[i][1] == 's') { rng_seed = atoi(argv[i + 1]); }
        else if (argv[i][1] == 'n') { steps = atoi(argv[i + 1]); }
        else if (argv[i][1] == 'i') { prompt = argv[i + 1]; }
        else if (argv[i][1] == 'z') { tokenizer_path = argv[i + 1]; }
        else if (argv[i][1] == 'm') { mode = argv[i + 1]; }
        else if (argv[i][1] == 'y') { system_prompt = argv[i + 1]; }
        else { error_usage(); }
    }

    // parameter validation/overrides
    if (rng_seed <= 0) rng_seed = (unsigned int)time(NULL);
    if (temperature < 0.0) temperature = 0.0;
    if (topp < 0.0 || 1.0 < topp) topp = 0.9;
    if (steps < 0) steps = 0;

    // build the Transformer via the model .bin file
    Transformer transformer;
    long t_load = time_in_ms();
    build_transformer(&transformer, checkpoint_path, steps);
    {
        Config *c = &transformer.config;
        int kv_dim = (c->dim * c->n_kv_heads) / c->n_heads;
        double kv_mb = 2.0 * c->n_layers * c->seq_len * kv_dim * sizeof(kv_t) / 1e6;
        fprintf(stderr, "model %s: %.1f MB int8 (mmap), dim %d, %d layers, vocab %d; KV cache %.1f MB for %d steps; load %ld ms\n",
                checkpoint_path, transformer.file_size / 1e6, c->dim, c->n_layers, c->vocab_size,
                kv_mb, c->seq_len, time_in_ms() - t_load);
    }
    if (steps == 0 || steps > transformer.config.seq_len) steps = transformer.config.seq_len; // override to ~max length

    if (TOK_TYPE == 1) {   // Hugging Face model: byte-level BPE + ChatML
        char tok_default[1024];
        if (!tokenizer_path) {
            snprintf(tok_default, sizeof(tok_default), "%s", checkpoint_path);
            char* dot = strrchr(tok_default, '.');
            if (dot && !strcmp(dot, ".bin")) strcpy(dot, ".tok"); else strncat(tok_default, ".tok", sizeof(tok_default) - strlen(tok_default) - 1);
            tokenizer_path = tok_default;
        }
        Bpe bpe; build_bpe(&bpe, tokenizer_path);
        if (bpe.n != transformer.config.vocab_size) { fprintf(stderr, "tokenizer has %d tokens, model %d\n", bpe.n, transformer.config.vocab_size); exit(EXIT_FAILURE); }
        Sampler sampler;
        build_sampler(&sampler, transformer.config.vocab_size, temperature, topp, rng_seed);
        if (strcmp(mode, "chat") == 0) chat_ml(&transformer, &bpe, &sampler, prompt, system_prompt, steps);
        else generate_bpe(&transformer, &bpe, &sampler, prompt ? prompt : "Once upon a time", steps);
        free_sampler(&sampler); free_transformer(&transformer);
        return 0;
    }

    fprintf(stderr, "%s: not a convert_hf.py model (needs the byte-level BPE + ChatML header)\n", checkpoint_path);
    free_transformer(&transformer);
    return 1;
}
#endif
