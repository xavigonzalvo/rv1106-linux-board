#include "json_out.h"

#include <math.h>
#include <stdio.h>

std::string json_escape(const std::string &s)
{
    std::string o;
    o.reserve(s.size() + 8);
    for (size_t i = 0; i < s.size(); i++) {
        unsigned char c = (unsigned char)s[i];
        switch (c) {
        case '"': o += "\\\""; break;
        case '\\': o += "\\\\"; break;
        case '\n': o += "\\n"; break;
        case '\r': o += "\\r"; break;
        case '\t': o += "\\t"; break;
        default:
            if (c < 0x20) {
                char buf[8];
                snprintf(buf, sizeof(buf), "\\u%04x", c);
                o += buf;
            } else {
                o += (char)c;  // UTF-8 bytes pass through unchanged
            }
        }
    }
    return o;
}

static std::string fmt(const char *f, double v)
{
    if (!isfinite(v)) v = 0;
    char buf[64];
    snprintf(buf, sizeof(buf), f, v);
    return buf;
}

std::string json_ready(const std::string &model_name, int in_w, int in_h, double load_ms)
{
    char buf[64];
    snprintf(buf, sizeof(buf), "[%d,%d]", in_w, in_h);
    return "{\"ready\":true,\"model\":\"" + json_escape(model_name) + "\",\"input\":" + buf +
           ",\"load_ms\":" + fmt("%.1f", load_ms) + "}";
}

std::string json_not_ready(const std::string &error)
{
    return "{\"ready\":false,\"error\":\"" + json_escape(error) + "\"}";
}

std::string json_error(const std::string &error) { return "{\"ok\":false,\"error\":\"" + json_escape(error) + "\"}"; }

std::string json_result(int width, int height, const Timings &t, const std::vector<Detection> &dets,
                        const std::vector<std::string> &labels)
{
    char buf[160];
    snprintf(buf, sizeof(buf), "{\"ok\":true,\"width\":%d,\"height\":%d,\"ms\":{", width, height);
    std::string o = buf;
    o += "\"decode\":" + fmt("%.1f", t.decode);
    o += ",\"preprocess\":" + fmt("%.1f", t.preprocess);
    o += ",\"npu\":" + fmt("%.1f", t.npu);
    o += ",\"postprocess\":" + fmt("%.1f", t.postprocess);
    o += ",\"total\":" + fmt("%.1f", t.total);
    o += "},\"objects\":[";
    for (size_t i = 0; i < dets.size(); i++) {
        const Detection &d = dets[i];
        std::string label;
        if (d.cls >= 0 && (size_t)d.cls < labels.size()) {
            label = labels[d.cls];
        } else {
            snprintf(buf, sizeof(buf), "class%d", d.cls);
            label = buf;
        }
        if (i) o += ",";
        o += "{\"label\":\"" + json_escape(label) + "\"";
        snprintf(buf, sizeof(buf), ",\"class\":%d,\"score\":%.3f,\"box\":[%d,%d,%d,%d]}", d.cls, (double)d.score,
                 (int)lroundf(d.x1), (int)lroundf(d.y1), (int)lroundf(d.x2), (int)lroundf(d.y2));
        o += buf;
    }
    o += "]}";
    return o;
}
