package main

import (
	"context"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// The test binary doubles as the fake detector: when AIDETECT_FAKE is set it speaks the detector protocol.
// FAKE_MODE: "" normal, "notready" prints ready:false, "dies" exits before the ready line, "silent" never
// becomes ready. Per request, a path containing "crash" exits, "garbage" prints a non-JSON line, "hang" never
// answers; anything else gets a mock answer.
func TestMain(m *testing.M) {
	if os.Getenv("AIDETECT_FAKE") == "1" {
		os.Exit(fakeDetector())
	}
	os.Exit(m.Run())
}

func fakeDetector() int {
	switch os.Getenv("FAKE_MODE") {
	case "notready":
		fmt.Println(`{"ready":false,"error":"cannot load model"}`)
		return 1
	case "dies":
		fmt.Fprintln(os.Stderr, "segfault (pretend)")
		return 139
	case "silent":
		time.Sleep(time.Hour)
		return 0
	}
	return runMockDetector(os.Stdin, os.Stdout, cocoLabels, 0, func(p string) []byte {
		switch {
		case strings.Contains(p, "crash"):
			fmt.Fprintln(os.Stderr, "fake detector: crashing on purpose")
			os.Exit(3)
		case strings.Contains(p, "garbage"):
			return []byte("rknn_run failed: oops")
		case strings.Contains(p, "hang"):
			time.Sleep(time.Hour)
		}
		return mockDetect(p, cocoLabels, false)
	})
}

type logBuf struct {
	mu    sync.Mutex
	lines []string
}

func (l *logBuf) logf(f string, a ...any) {
	l.mu.Lock()
	l.lines = append(l.lines, fmt.Sprintf(f, a...))
	l.mu.Unlock()
}

func (l *logBuf) contains(s string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	for _, x := range l.lines {
		if strings.Contains(x, s) {
			return true
		}
	}
	return false
}

func newFakeManager(t *testing.T, mode string, timeout time.Duration) (*Manager, *logBuf) {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	lb := &logBuf{}
	m := NewManager(ManagerConfig{
		Path:         exe,
		Args:         []string{"-test.run=^$"},
		Env:          []string{"AIDETECT_FAKE=1", "FAKE_MODE=" + mode},
		Timeout:      timeout,
		ReadyTimeout: 2 * time.Second,
		MinBackoff:   50 * time.Millisecond,
		MaxBackoff:   200 * time.Millisecond,
		Logf:         lb.logf,
	})
	m.Start()
	t.Cleanup(m.Close)
	return m, lb
}

func writePNG(t *testing.T, dir string, w, h int) string {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, color.RGBA{uint8(x), uint8(y), 128, 255})
		}
	}
	p := filepath.Join(dir, fmt.Sprintf("img-%dx%d.png", w, h))
	f, err := os.Create(p)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := png.Encode(f, img); err != nil {
		t.Fatal(err)
	}
	return p
}

func waitState(t *testing.T, m *Manager, want string, within time.Duration) DetectorStatus {
	t.Helper()
	end := time.Now().Add(within)
	for time.Now().Before(end) {
		if st := m.Status(); st.State == want {
			return st
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("state %q not reached within %v (now %+v)", want, within, m.Status())
	return DetectorStatus{}
}

func TestReadyAndDetect(t *testing.T) {
	m, _ := newFakeManager(t, "", 5*time.Second)
	img := writePNG(t, t.TempDir(), 320, 200)

	// Detect waits for the ready line itself.
	res, err := m.Detect(context.Background(), img)
	if err != nil {
		t.Fatal(err)
	}
	st := m.Status()
	if st.State != StateReady || st.Model != "mock-yolov5.rknn" || len(st.Input) != 2 || st.PID == 0 {
		t.Fatalf("status after ready: %+v", st)
	}
	if !res.OK || res.Width != 320 || res.Height != 200 || len(res.Objects) == 0 || res.Ms["total"] <= 0 {
		t.Fatalf("unexpected result: %s", res.Raw)
	}
	// Several requests in a row, from several goroutines: all answered, in sync.
	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for i := range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			p := img
			if i%2 == 1 {
				p = "/does/not/exist.jpg"
			}
			r, err := m.Detect(context.Background(), p)
			if err != nil {
				errs <- err
				return
			}
			if r.OK != (i%2 == 0) {
				errs <- fmt.Errorf("request %d: ok=%v: %s", i, r.OK, r.Raw)
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Error(err)
	}
}

func TestDetectorErrorResponse(t *testing.T) {
	m, _ := newFakeManager(t, "", 5*time.Second)
	bad := filepath.Join(t.TempDir(), "notimage.jpg")
	os.WriteFile(bad, []byte("hello"), 0o644)
	res, err := m.Detect(context.Background(), bad)
	if err != nil {
		t.Fatal(err)
	}
	if res.OK || !strings.Contains(res.Error, "cannot decode") {
		t.Fatalf("want ok:false cannot decode, got %s", res.Raw)
	}
}

func TestCrashAndRestart(t *testing.T) {
	m, lb := newFakeManager(t, "", 5*time.Second)
	img := writePNG(t, t.TempDir(), 64, 64)
	if _, err := m.Detect(context.Background(), img); err != nil {
		t.Fatal(err)
	}
	pid := m.Status().PID

	_, err := m.Detect(context.Background(), "/tmp/crash.jpg")
	if !errors.Is(err, ErrDied) {
		t.Fatalf("want ErrDied, got %v", err)
	}
	st := waitState(t, m, StateReady, 3*time.Second)
	if st.Restarts != 1 || st.PID == pid || st.PID == 0 {
		t.Fatalf("after restart: %+v (old pid %d)", st, pid)
	}
	if !strings.Contains(st.LastError, "exit status 3") {
		t.Errorf("last error %q", st.LastError)
	}
	if !lb.contains("crashing on purpose") {
		t.Error("detector stderr was not logged")
	}
	res, err := m.Detect(context.Background(), img)
	if err != nil || !res.OK {
		t.Fatalf("after restart: %v %v", res, err)
	}
}

func TestRequestDuringRestartWaits(t *testing.T) {
	m, _ := newFakeManager(t, "", 5*time.Second)
	img := writePNG(t, t.TempDir(), 64, 64)
	m.Detect(context.Background(), img)
	m.Detect(context.Background(), "/tmp/crash.jpg")
	// Immediately after the crash the detector is restarting; the next request waits for it.
	res, err := m.Detect(context.Background(), img)
	if err != nil || !res.OK {
		t.Fatalf("want success after waiting for restart, got %v %v", res, err)
	}
}

func TestMalformedLine(t *testing.T) {
	m, _ := newFakeManager(t, "", 5*time.Second)
	img := writePNG(t, t.TempDir(), 64, 64)
	_, err := m.Detect(context.Background(), "/tmp/garbage.jpg")
	if !errors.Is(err, ErrMalformed) {
		t.Fatalf("want ErrMalformed, got %v", err)
	}
	// The stream is still in sync and the detector was not restarted.
	res, err := m.Detect(context.Background(), img)
	if err != nil || !res.OK {
		t.Fatalf("after malformed line: %v %v", res, err)
	}
	if st := m.Status(); st.Restarts != 0 {
		t.Errorf("unexpected restart: %+v", st)
	}
}

func TestTimeoutKillsAndRestarts(t *testing.T) {
	m, _ := newFakeManager(t, "", 300*time.Millisecond)
	img := writePNG(t, t.TempDir(), 64, 64)
	waitState(t, m, StateReady, 3*time.Second)
	t0 := time.Now()
	_, err := m.Detect(context.Background(), "/tmp/hang.jpg")
	if !errors.Is(err, ErrTimeout) {
		t.Fatalf("want ErrTimeout, got %v", err)
	}
	if d := time.Since(t0); d > 2*time.Second {
		t.Errorf("timeout took %v", d)
	}
	st := waitState(t, m, StateReady, 3*time.Second)
	if st.Restarts < 1 {
		t.Errorf("no restart after timeout: %+v", st)
	}
	if res, err := m.Detect(context.Background(), img); err != nil || !res.OK {
		t.Fatalf("after timeout: %v %v", res, err)
	}
}

func TestNotReady(t *testing.T) {
	for _, mode := range []string{"notready", "dies"} {
		t.Run(mode, func(t *testing.T) {
			m, _ := newFakeManager(t, mode, 300*time.Millisecond)
			st := waitState(t, m, StateError, 3*time.Second)
			if st.LastError == "" {
				t.Error("no error message")
			}
			if mode == "notready" && !strings.Contains(st.LastError, "cannot load model") {
				t.Errorf("last error %q", st.LastError)
			}
			_, err := m.Detect(context.Background(), "/tmp/x.jpg")
			if !errors.Is(err, ErrNotReady) {
				t.Fatalf("want ErrNotReady, got %v", err)
			}
			// It keeps retrying.
			time.Sleep(400 * time.Millisecond)
			if m.Status().Restarts < 1 {
				t.Errorf("no retries: %+v", m.Status())
			}
		})
	}
}

func TestReadyTimeout(t *testing.T) {
	m, _ := newFakeManager(t, "silent", time.Second)
	st := waitState(t, m, StateError, 4*time.Second)
	if !strings.Contains(st.LastError, "no ready line") {
		t.Errorf("last error %q", st.LastError)
	}
}

func TestMissingExecutable(t *testing.T) {
	m := NewManager(ManagerConfig{Path: "/nonexistent/detector", Timeout: 200 * time.Millisecond,
		MinBackoff: 20 * time.Millisecond, Logf: func(string, ...any) {}})
	m.Start()
	defer m.Close()
	waitState(t, m, StateError, 2*time.Second)
	if _, err := m.Detect(context.Background(), "/x.jpg"); !errors.Is(err, ErrNotReady) {
		t.Fatalf("want ErrNotReady, got %v", err)
	}
}

func TestStatusFilesMissing(t *testing.T) {
	old := []string{pathUptime, pathTemp, pathMeminfo, pathLoadavg, pathSelfSt}
	defer func() {
		pathUptime, pathTemp, pathMeminfo, pathLoadavg, pathSelfSt = old[0], old[1], old[2], old[3], old[4]
	}()
	dir := t.TempDir()
	pathUptime, pathTemp, pathMeminfo, pathLoadavg, pathSelfSt = "/nope", "/nope", "/nope", "/nope", "/nope"
	if s := readSystemStatus(); s.TempC != nil || s.MemTotalK != nil || s.UptimeS != nil {
		t.Fatalf("expected empty status, got %+v", s)
	}
	pathTemp = filepath.Join(dir, "temp")
	pathMeminfo = filepath.Join(dir, "meminfo")
	pathLoadavg = filepath.Join(dir, "loadavg")
	os.WriteFile(pathTemp, []byte("41000\n"), 0o644)
	os.WriteFile(pathMeminfo, []byte("MemTotal:          35000 kB\nMemFree:            9000 kB\nMemAvailable:      16700 kB\n"), 0o644)
	os.WriteFile(pathLoadavg, []byte("0.52 0.31 0.12 1/58 812\n"), 0o644)
	s := readSystemStatus()
	if s.TempC == nil || *s.TempC != 41 || *s.MemAvailK != 16700 || len(s.Load) != 3 || s.Load[0] != 0.52 {
		t.Fatalf("parsed status wrong: %+v", s)
	}
}
