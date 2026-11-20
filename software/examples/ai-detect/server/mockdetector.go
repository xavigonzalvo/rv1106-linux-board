package main

// Mock detector: speaks the same stdin/stdout protocol as the real detector (../PROTOCOL.md) but returns
// made-up boxes. `server -mock` re-executes its own binary with -mock-detector, so mock mode exercises the
// real process manager. It also runs on the board, to test the server without the NPU.

import (
	"bufio"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"math/rand/v2"
	"os"
	"strings"
	"time"
)

var cocoLabels = strings.Fields(`person bicycle car motorcycle airplane bus train truck boat traffic_light
fire_hydrant stop_sign parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack
umbrella handbag tie suitcase frisbee skis snowboard sports_ball kite baseball_bat baseball_glove skateboard
surfboard tennis_racket bottle wine_glass cup fork knife spoon bowl banana apple sandwich orange broccoli carrot
hot_dog pizza donut cake chair couch potted_plant bed dining_table toilet tv laptop mouse remote keyboard
cell_phone microwave oven toaster sink refrigerator book clock vase scissors teddy_bear hair_drier toothbrush`)

func init() {
	for i, l := range cocoLabels {
		cocoLabels[i] = strings.ReplaceAll(l, "_", " ")
	}
}

func loadLabels(path string) []string {
	if path == "" {
		return cocoLabels
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return cocoLabels
	}
	var out []string
	for _, l := range strings.Split(string(b), "\n") {
		if l = strings.TrimSpace(l); l != "" {
			out = append(out, l)
		}
	}
	if len(out) == 0 {
		return cocoLabels
	}
	return out
}

type mockObject struct {
	Label string  `json:"label"`
	Class int     `json:"class"`
	Score float64 `json:"score"`
	Box   [4]int  `json:"box"`
}

// mockDetect returns one protocol response line (without newline) for an image path.
func mockDetect(path string, labels []string, sleep bool) []byte {
	t0 := time.Now()
	f, err := os.Open(path)
	if err != nil {
		return errLine("cannot open " + path)
	}
	defer f.Close()
	h := fnv.New64a()
	io.CopyN(h, f, 256*1024)
	f.Seek(0, io.SeekStart)
	cfg, _, err := image.DecodeConfig(f)
	if err != nil {
		return errLine("cannot decode " + path)
	}
	seed := h.Sum64()
	rng := rand.New(rand.NewPCG(seed, seed>>7))
	w, hgt := cfg.Width, cfg.Height

	// Plausible RV1106 timings for a 640x640 YOLOv5s, scaled a little by image size.
	mp := float64(w*hgt) / 1e6
	ms := map[string]float64{
		"decode":      round1(8 + 22*mp + rng.Float64()*4),
		"preprocess":  round1(6 + 5*mp + rng.Float64()*2),
		"npu":         round1(46 + rng.Float64()*6),
		"postprocess": round1(2 + rng.Float64()*2),
	}
	ms["total"] = round1(ms["decode"] + ms["preprocess"] + ms["npu"] + ms["postprocess"])

	n := 1 + rng.IntN(5)
	objs := make([]mockObject, 0, n)
	for range n {
		cls := 0
		if rng.IntN(3) > 0 { // people are common
			cls = rng.IntN(len(labels))
		}
		bw := int(float64(w) * (0.12 + rng.Float64()*0.4))
		bh := int(float64(hgt) * (0.15 + rng.Float64()*0.5))
		x1 := rng.IntN(max(1, w-bw))
		y1 := rng.IntN(max(1, hgt-bh))
		objs = append(objs, mockObject{
			Label: labels[cls], Class: cls, Score: float64(int(250+rng.IntN(740))) / 1000,
			Box: [4]int{x1, y1, min(w-1, x1+bw), min(hgt-1, y1+bh)},
		})
	}
	for i := 1; i < len(objs); i++ { // sort by score, highest first
		for j := i; j > 0 && objs[j].Score > objs[j-1].Score; j-- {
			objs[j], objs[j-1] = objs[j-1], objs[j]
		}
	}
	if sleep {
		time.Sleep(time.Duration(ms["total"]*float64(time.Millisecond)) - time.Since(t0))
	}
	b, _ := json.Marshal(map[string]any{"ok": true, "width": w, "height": hgt, "ms": ms, "objects": objs})
	return b
}

func round1(f float64) float64 { return float64(int(f*10+0.5)) / 10 }

func errLine(msg string) []byte {
	b, _ := json.Marshal(map[string]any{"ok": false, "error": msg})
	return b
}

// runMockDetector implements the detector protocol on the given streams. handle may be nil.
func runMockDetector(in io.Reader, out io.Writer, labels []string, loadDelay time.Duration, handle func(path string) []byte) int {
	if handle == nil {
		handle = func(p string) []byte { return mockDetect(p, labels, true) }
	}
	time.Sleep(loadDelay) // "model load"
	fmt.Fprintf(out, `{"ready":true,"model":"mock-yolov5.rknn","input":[640,640],"load_ms":%.1f}`+"\n",
		float64(loadDelay.Microseconds())/1000)
	sc := bufio.NewScanner(in)
	for sc.Scan() {
		p := strings.TrimSpace(sc.Text())
		if p == "" {
			continue
		}
		out.Write(append(handle(p), '\n'))
	}
	return 0
}
