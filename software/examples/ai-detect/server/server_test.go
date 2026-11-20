package main

import (
	"bytes"
	"encoding/json"
	"io"
	"io/fs"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func newTestServer(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	m, _ := newFakeManager(t, "", 5*time.Second)
	up := t.TempDir()
	web, _ := fs.Sub(embeddedWeb, "web")
	s := &server{mgr: m, uploads: up, modelName: "mock", mock: true, started: time.Now(), maxWaiting: 6}
	ts := httptest.NewServer(s.routes(web))
	t.Cleanup(ts.Close)
	return ts, up
}

func upload(t *testing.T, url, field, name string, data []byte) (*http.Response, map[string]any) {
	t.Helper()
	var body bytes.Buffer
	mw := multipart.NewWriter(&body)
	mw.WriteField("note", "ignored")
	fw, _ := mw.CreateFormFile(field, name)
	fw.Write(data)
	mw.Close()
	resp, err := http.Post(url+"/api/detect", mw.FormDataContentType(), &body)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	b, _ := io.ReadAll(resp.Body)
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatalf("response is not JSON: %q", b)
	}
	return resp, out
}

func TestAPIDetect(t *testing.T) {
	ts, up := newTestServer(t)
	img, _ := os.ReadFile(writePNG(t, t.TempDir(), 640, 480))

	resp, out := upload(t, ts.URL, "image", "photo.png", img)
	if resp.StatusCode != 200 || out["ok"] != true {
		t.Fatalf("status %d: %v", resp.StatusCode, out)
	}
	if out["width"].(float64) != 640 || out["height"].(float64) != 480 {
		t.Errorf("size: %v x %v", out["width"], out["height"])
	}
	objs := out["objects"].([]any)
	if len(objs) == 0 {
		t.Fatal("no objects")
	}
	o := objs[0].(map[string]any)
	for _, k := range []string{"label", "class", "score", "box"} {
		if _, ok := o[k]; !ok {
			t.Errorf("object missing %q: %v", k, o)
		}
	}
	ms := out["ms"].(map[string]any)
	for _, k := range []string{"decode", "preprocess", "npu", "postprocess", "total"} {
		if _, ok := ms[k]; !ok {
			t.Errorf("ms missing %q", k)
		}
	}
	srv := out["server"].(map[string]any)
	if srv["total_ms"].(float64) <= 0 || srv["upload_size"].(float64) != float64(len(img)) {
		t.Errorf("server timing: %v", srv)
	}
	if ents, _ := os.ReadDir(up); len(ents) != 0 {
		t.Errorf("uploads dir not cleaned: %v", ents)
	}

	// Status reflects the detection.
	r, err := http.Get(ts.URL + "/api/status")
	if err != nil {
		t.Fatal(err)
	}
	var st map[string]any
	json.NewDecoder(r.Body).Decode(&st)
	r.Body.Close()
	if st["detector"].(map[string]any)["state"] != "ready" {
		t.Errorf("detector state: %v", st["detector"])
	}
	if st["served"].(map[string]any)["detections"].(float64) != 1 || st["last_inference"] == nil {
		t.Errorf("served: %v last: %v", st["served"], st["last_inference"])
	}
	if _, ok := st["system"]; !ok {
		t.Error("no system section")
	}
}

func TestAPIDetectErrors(t *testing.T) {
	ts, up := newTestServer(t)

	resp, out := upload(t, ts.URL, "image", "notes.txt", []byte("just some text, not an image"))
	if resp.StatusCode != http.StatusUnsupportedMediaType || out["ok"] != false {
		t.Errorf("text upload: %d %v", resp.StatusCode, out)
	}
	resp, _ = upload(t, ts.URL, "file", "a.png", []byte("x"))
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("missing image field: %d", resp.StatusCode)
	}
	// A JPEG header with a broken body reaches the detector, which answers ok:false.
	resp, out = upload(t, ts.URL, "image", "broken.jpg", append([]byte{0xFF, 0xD8, 0xFF, 0xE0}, make([]byte, 100)...))
	if resp.StatusCode != http.StatusUnprocessableEntity || out["ok"] != false || !strings.Contains(out["error"].(string), "decode") {
		t.Errorf("broken jpeg: %d %v", resp.StatusCode, out)
	}
	// Too large.
	big := append([]byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}, make([]byte, maxUpload+10)...)
	resp, _ = upload(t, ts.URL, "image", "big.png", big)
	if resp.StatusCode != http.StatusRequestEntityTooLarge {
		t.Errorf("big upload: %d", resp.StatusCode)
	}
	if r, _ := http.Get(ts.URL + "/api/detect"); r.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("GET /api/detect: %d", r.StatusCode)
	}
	if ents, _ := os.ReadDir(up); len(ents) != 0 {
		t.Errorf("uploads dir not cleaned: %v", ents)
	}
}

func TestUIServed(t *testing.T) {
	ts, _ := newTestServer(t)
	for _, p := range []string{"/", "/app.js", "/style.css"} {
		r, err := http.Get(ts.URL + p)
		if err != nil {
			t.Fatal(err)
		}
		b, _ := io.ReadAll(r.Body)
		r.Body.Close()
		if r.StatusCode != 200 || len(b) < 100 {
			t.Errorf("%s: %d, %d bytes", p, r.StatusCode, len(b))
		}
	}
}
