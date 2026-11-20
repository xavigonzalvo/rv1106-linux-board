// ai-detect server: web UI + HTTP API in front of the NPU object detector (see ../PROTOCOL.md).
//
// Build for the board on the Mac:
//
//	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -ldflags="-s -w" -o server .
//
// Run on the Mac without the board:  go run . -mock
package main

import (
	"bytes"
	"crypto/rand"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"sync"
	"sync/atomic"
	"time"
)

//go:embed web
var embeddedWeb embed.FS

const maxUpload = 8 << 20 // bytes of image data

type stats struct {
	mu          sync.Mutex
	requests    int64   // successful detections
	objects     int64   // boxes returned in total
	failures    int64   // requests that got an error
	lastInferMs float64 // detector ms.total of the last success
	lastNpuMs   float64
	lastAt      time.Time
}

type server struct {
	mgr        *Manager
	uploads    string // absolute directory
	modelName  string
	mock       bool
	started    time.Time
	maxWaiting int32
	waiting    atomic.Int32
	st         stats
}

func main() {
	addr := flag.String("addr", ":8080", "listen address")
	detector := flag.String("detector", "/mnt/sdcard/ai-detect/detector", "detector executable")
	model := flag.String("model", "/mnt/sdcard/ai-detect/model/yolov5.rknn", "RKNN model passed to the detector")
	labels := flag.String("labels", "/mnt/sdcard/ai-detect/model/labels.txt", "class names, one per line")
	uploads := flag.String("uploads", "/mnt/sdcard/ai-detect/uploads", "directory for temporary uploads")
	webDir := flag.String("web", "", "serve the UI from this directory instead of the embedded copy (development)")
	mock := flag.Bool("mock", false, "use the built-in mock detector (no NPU needed)")
	timeout := flag.Duration("timeout", 10*time.Second, "per-image detector timeout")
	mockDetector := flag.Bool("mock-detector", false, "internal: act as the mock detector on stdin/stdout")
	flag.Parse()

	if *mockDetector {
		os.Exit(runMockDetector(os.Stdin, os.Stdout, loadLabels(*labels), 300*time.Millisecond, nil))
	}

	// Little RAM on the board: keep the Go heap small.
	debug.SetMemoryLimit(48 << 20)
	debug.SetGCPercent(50)

	dir, err := filepath.Abs(*uploads)
	if err == nil {
		err = os.MkdirAll(dir, 0o755)
	}
	if err != nil {
		log.Fatalf("uploads dir: %v", err)
	}
	cleanUploads(dir)

	cfg := ManagerConfig{Path: *detector, Args: []string{"--model", *model, "--labels", *labels}, Timeout: *timeout}
	modelName := filepath.Base(*model)
	if *mock {
		self, err := os.Executable()
		if err != nil {
			log.Fatalf("mock: %v", err)
		}
		lbl := *labels
		if _, err := os.Stat(lbl); err != nil {
			lbl = "" // built-in COCO names
		}
		cfg.Path, cfg.Args = self, []string{"-mock-detector", "-labels", lbl}
		modelName = "mock-yolov5.rknn"
		log.Printf("mock mode: detector is %s -mock-detector", self)
	}
	mgr := NewManager(cfg)
	mgr.Start()

	var web fs.FS
	if *webDir != "" {
		web = os.DirFS(*webDir)
		log.Printf("serving UI from %s", *webDir)
	} else {
		web, _ = fs.Sub(embeddedWeb, "web")
	}
	s := &server{mgr: mgr, uploads: dir, modelName: modelName, mock: *mock, started: time.Now(), maxWaiting: 6}

	srv := &http.Server{
		Addr:              *addr,
		Handler:           s.routes(web),
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("listening on %s", *addr)
	log.Fatal(srv.ListenAndServe())
}

func (s *server) routes(web fs.FS) http.Handler {
	mux := http.NewServeMux()
	files := http.FileServerFS(web)
	mux.Handle("/", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Cache-Control", "no-cache")
		files.ServeHTTP(w, r)
	}))
	mux.HandleFunc("POST /api/detect", s.handleDetect)
	mux.HandleFunc("/api/", func(w http.ResponseWriter, r *http.Request) {
		apiError(w, http.StatusMethodNotAllowed, "use POST /api/detect or GET /api/status")
	})
	mux.HandleFunc("GET /api/status", s.handleStatus)
	return mux
}

// cleanUploads removes leftovers from a previous run (e.g. after a power cut).
func cleanUploads(dir string) {
	ents, _ := os.ReadDir(dir)
	for _, e := range ents {
		if !e.IsDir() && filepath.Ext(e.Name()) != "" && len(e.Name()) == 32+len(filepath.Ext(e.Name())) {
			os.Remove(filepath.Join(dir, e.Name()))
		}
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func apiError(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]any{"ok": false, "error": msg})
}

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000 }

// handleDetect streams the uploaded image to disk, runs the detector and returns its JSON plus a "server" object.
func (s *server) handleDetect(w http.ResponseWriter, r *http.Request) {
	t0 := time.Now()
	if n := s.waiting.Add(1); n > s.maxWaiting {
		s.waiting.Add(-1)
		apiError(w, http.StatusServiceUnavailable, "busy: too many images queued, try again")
		return
	}
	defer s.waiting.Add(-1)

	r.Body = http.MaxBytesReader(w, r.Body, maxUpload+64<<10)
	mr, err := r.MultipartReader()
	if err != nil {
		apiError(w, http.StatusBadRequest, "expected multipart/form-data with an image field")
		return
	}
	var path string
	var size int64
	defer func() {
		if path != "" {
			os.Remove(path)
		}
	}()
	for {
		part, err := mr.NextPart()
		if err == io.EOF {
			break
		}
		if err != nil {
			apiError(w, http.StatusBadRequest, "bad upload: "+err.Error())
			return
		}
		if part.FormName() != "image" || path != "" {
			part.Close()
			continue
		}
		path, size, err = s.saveUpload(part)
		part.Close()
		if err != nil {
			code := http.StatusBadRequest
			var mbe *http.MaxBytesError
			if errors.As(err, &mbe) || errors.Is(err, errTooLarge) {
				code = http.StatusRequestEntityTooLarge
			} else if errors.Is(err, errType) {
				code = http.StatusUnsupportedMediaType
			}
			apiError(w, code, err.Error())
			return
		}
	}
	if path == "" {
		apiError(w, http.StatusBadRequest, "no image field in the upload")
		return
	}
	tUp := time.Now()

	res, err := s.mgr.Detect(r.Context(), path)
	tDet := time.Now()
	if err != nil {
		s.st.mu.Lock()
		s.st.failures++
		s.st.mu.Unlock()
		code := http.StatusServiceUnavailable
		if errors.Is(err, ErrTimeout) {
			code = http.StatusGatewayTimeout
		} else if errors.Is(err, ErrMalformed) || errors.Is(err, ErrDied) {
			code = http.StatusBadGateway
		}
		log.Printf("detect: %v", err)
		apiError(w, code, err.Error())
		return
	}

	s.st.mu.Lock()
	if res.OK {
		s.st.requests++
		s.st.objects += int64(len(res.Objects))
		s.st.lastInferMs = res.Ms["total"]
		s.st.lastNpuMs = res.Ms["npu"]
		s.st.lastAt = tDet
	} else {
		s.st.failures++
	}
	s.st.mu.Unlock()

	// Detector JSON, unchanged, plus the server's own timing.
	var out map[string]json.RawMessage
	if err := json.Unmarshal(res.Raw, &out); err != nil {
		apiError(w, http.StatusBadGateway, "detector response is not a JSON object")
		return
	}
	srvTiming, _ := json.Marshal(map[string]any{
		"upload_ms":   ms(tUp.Sub(t0)),
		"detect_ms":   ms(tDet.Sub(tUp)), // includes waiting for other requests
		"total_ms":    ms(time.Since(t0)),
		"upload_size": size,
	})
	out["server"] = srvTiming
	code := http.StatusOK
	if !res.OK {
		code = http.StatusUnprocessableEntity
	}
	writeJSON(w, code, out)
}

var (
	errTooLarge = fmt.Errorf("image larger than %d MB", maxUpload>>20)
	errType     = errors.New("only JPEG and PNG images are supported")
)

// saveUpload copies one multipart part to a randomly named file in the uploads dir, never holding it in memory.
func (s *server) saveUpload(part io.Reader) (string, int64, error) {
	head := make([]byte, 512)
	n, err := io.ReadFull(part, head)
	if err != nil && err != io.ErrUnexpectedEOF {
		if err == io.EOF {
			return "", 0, errors.New("empty image")
		}
		return "", 0, err
	}
	head = head[:n]
	var ext string
	switch ct := http.DetectContentType(head); ct {
	case "image/jpeg":
		ext = ".jpg"
	case "image/png":
		ext = ".png"
	default:
		return "", 0, fmt.Errorf("%w (got %s)", errType, ct)
	}
	rnd := make([]byte, 16)
	rand.Read(rnd)
	path := filepath.Join(s.uploads, hex.EncodeToString(rnd)+ext)
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		return "", 0, err
	}
	written, err := io.Copy(f, io.MultiReader(bytes.NewReader(head), io.LimitReader(part, maxUpload+1-int64(n))))
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	if err == nil && written > maxUpload {
		err = errTooLarge
	}
	if err != nil {
		os.Remove(path)
		return "", 0, err
	}
	return path, written, nil
}

func (s *server) handleStatus(w http.ResponseWriter, r *http.Request) {
	det := s.mgr.Status()
	model := det.Model
	if model == "" {
		model = s.modelName
	}
	s.st.mu.Lock()
	served := map[string]any{
		"detections": s.st.requests,
		"objects":    s.st.objects,
		"failures":   s.st.failures,
	}
	var last any
	if !s.st.lastAt.IsZero() {
		last = map[string]any{"total_ms": s.st.lastInferMs, "npu_ms": s.st.lastNpuMs, "at": s.st.lastAt}
	}
	s.st.mu.Unlock()
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)
	writeJSON(w, http.StatusOK, map[string]any{
		"server_uptime_s": time.Since(s.started).Seconds(),
		"mock":            s.mock,
		"model":           model,
		"detector":        det,
		"served":          served,
		"last_inference":  last,
		"queue":           s.waiting.Load(),
		"system":          readSystemStatus(),
		"go_heap_kb":      mem.HeapAlloc >> 10,
		"go_sys_kb":       mem.Sys >> 10,
	})
}
