// ai-detect detector: YOLOv5 on the RV1106 NPU, line protocol on stdin/stdout (see ../../PROTOCOL.md).
//
//   detector --model model/yolov5.rknn --labels model/labels.txt [--box-thresh 0.25] [--nms-thresh 0.45]
//            [--max-pixels 13000000]
//
// stdout carries protocol lines only (one ready line, then one JSON line per request); all logs go to stderr.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <string>
#include <vector>

#include "image_io.h"
#include "json_out.h"
#include "letterbox.h"
#include "npu.h"
#include "postprocess.h"

static double now_ms()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static void emit(const std::string &line)
{
    fputs(line.c_str(), stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

static bool load_labels(const char *path, std::vector<std::string> &labels)
{
    FILE *f = fopen(path, "r");
    if (!f) return false;
    char buf[256];
    while (fgets(buf, sizeof(buf), f)) {
        size_t n = strlen(buf);
        while (n && (buf[n - 1] == '\n' || buf[n - 1] == '\r' || buf[n - 1] == ' ')) buf[--n] = 0;
        if (n == 0 && feof(f)) break;
        labels.push_back(buf);
    }
    fclose(f);
    return !labels.empty();
}

static const char *base_name(const char *p)
{
    const char *s = strrchr(p, '/');
    return s ? s + 1 : p;
}

static void usage()
{
    fprintf(stderr,
            "usage: detector --model <yolov5.rknn> --labels <labels.txt> [--box-thresh 0.25] [--nms-thresh 0.45]\n"
            "                [--max-pixels 13000000]\n"
            "then write one image path per line on stdin; one JSON line per image on stdout.\n");
}

int main(int argc, char **argv)
{
    const char *model_path = 0, *labels_path = 0;
    float box_thresh = 0.25f, nms_thresh = 0.45f;
    long max_pixels = 13000000;  // 12 MP phone photos fit; RGB buffer + JPEG decoder state must fit in ~160 MB
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *v = i + 1 < argc ? argv[i + 1] : 0;
        if (!strcmp(a, "--model") && v) model_path = argv[++i];
        else if (!strcmp(a, "--labels") && v) labels_path = argv[++i];
        else if (!strcmp(a, "--box-thresh") && v) box_thresh = (float)atof(argv[++i]);
        else if (!strcmp(a, "--nms-thresh") && v) nms_thresh = (float)atof(argv[++i]);
        else if (!strcmp(a, "--max-pixels") && v) max_pixels = atol(argv[++i]);
        else if (!strcmp(a, "-h") || !strcmp(a, "--help")) {
            usage();
            return 0;
        } else {
            usage();
            emit(json_not_ready(std::string("bad argument: ") + a));
            return 2;
        }
    }
    if (!model_path || !labels_path) {
        usage();
        emit(json_not_ready("--model and --labels are required"));
        return 2;
    }

    double t0 = now_ms();
    std::vector<std::string> labels;
    if (!load_labels(labels_path, labels)) {
        emit(json_not_ready(std::string("cannot read labels ") + labels_path));
        return 1;
    }
    Npu npu;
    std::string err;
    if (!npu.load(model_path, err)) {
        fprintf(stderr, "detector: %s\n", err.c_str());
        emit(json_not_ready(err));
        return 1;
    }
    if ((int)labels.size() != npu.num_classes())
        fprintf(stderr, "detector: warning: %zu labels but model has %d classes\n", labels.size(), npu.num_classes());
    double load_ms = now_ms() - t0;
    fprintf(stderr, "detector: model %s loaded in %.1f ms, input %dx%d, %d classes\n", model_path, load_ms,
            npu.input_width(), npu.input_height(), npu.num_classes());
    emit(json_ready(base_name(model_path), npu.input_width(), npu.input_height(), load_ms));

    char *line = 0;
    size_t cap = 0;
    ssize_t len;
    while ((len = getline(&line, &cap, stdin)) >= 0) {
        // trim whitespace / CR / LF at both ends
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        char *e = line + len;
        while (e > p && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ' || e[-1] == '\t')) *--e = 0;
        if (*p == 0) {
            emit(json_error("empty request (expected an image path)"));
            continue;
        }

        Timings tm;
        memset(&tm, 0, sizeof(tm));
        double ts = now_ms();

        Image img;
        std::string reason;
        if (!decode_image(p, max_pixels, img, err, reason)) {
            fprintf(stderr, "detector: %s%s%s\n", err.c_str(), reason.empty() ? "" : ": ", reason.c_str());
            emit(json_error(err));
            continue;
        }
        double t1 = now_ms();
        tm.decode = t1 - ts;

        Letterbox lb = compute_letterbox(img.width, img.height, npu.input_width(), npu.input_height());
        letterbox_rgb(img.data, lb, npu.input_buffer(), npu.input_row_bytes(), 114);
        int width = img.width, height = img.height;
        img.reset();  // free the big RGB buffer before inference
        double t2 = now_ms();
        tm.preprocess = t2 - t1;

        if (!npu.run(err)) {
            fprintf(stderr, "detector: %s\n", err.c_str());
            emit(json_error(err));
            continue;
        }
        double t3 = now_ms();
        tm.npu = t3 - t2;

        std::vector<Detection> cand;
        const std::vector<HeadTensor> &heads = npu.heads();
        for (size_t i = 0; i < heads.size(); i++) decode_head(heads[i], npu.num_classes(), box_thresh, cand);
        std::vector<Detection> dets = nms(cand, nms_thresh, 128);
        unletterbox(dets, lb);
        double t4 = now_ms();
        tm.postprocess = t4 - t3;
        tm.total = t4 - ts;

        emit(json_result(width, height, tm, dets, labels));
        fprintf(stderr, "detector: %s %dx%d -> %zu objects (%zu candidates) in %.1f ms\n", p, width, height,
                dets.size(), cand.size(), tm.total);
    }
    free(line);
    return 0;
}
