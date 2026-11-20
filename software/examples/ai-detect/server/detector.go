package main

// Detector process manager: starts the detector child once, waits for its ready line, sends one image path per
// line on stdin and reads one JSON line per request from stdout (see ../PROTOCOL.md). Requests are serialised.
// If the child dies, times out or fails to start, it is restarted in the background with a backoff.

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Detector states reported by /api/status.
const (
	StateStarting   = "starting"
	StateReady      = "ready"
	StateRestarting = "restarting"
	StateError      = "error"
	StateStopped    = "stopped"
)

// ReadyInfo is the detector's first stdout line.
type ReadyInfo struct {
	Ready  bool    `json:"ready"`
	Model  string  `json:"model,omitempty"`
	Input  []int   `json:"input,omitempty"`
	LoadMs float64 `json:"load_ms,omitempty"`
	Error  string  `json:"error,omitempty"`
}

// Result is the part of a detector response the server looks at; Raw keeps the full line for the client.
type Result struct {
	OK      bool               `json:"ok"`
	Error   string             `json:"error,omitempty"`
	Width   int                `json:"width"`
	Height  int                `json:"height"`
	Ms      map[string]float64 `json:"ms"`
	Objects []json.RawMessage  `json:"objects"`
	Raw     json.RawMessage    `json:"-"`
}

// Errors returned by Detect. ErrNotReady and ErrTimeout mean the request was not answered.
var (
	ErrNotReady  = errors.New("detector not ready")
	ErrTimeout   = errors.New("detector timed out")
	ErrDied      = errors.New("detector exited during the request")
	ErrMalformed = errors.New("detector sent a malformed response")
	ErrStopped   = errors.New("detector manager stopped")
)

// ManagerConfig configures the child process.
type ManagerConfig struct {
	Path         string        // detector executable
	Args         []string      // e.g. --model ... --labels ...
	Env          []string      // extra environment (tests)
	Timeout      time.Duration // per request
	ReadyTimeout time.Duration // model load
	MinBackoff   time.Duration // first restart delay
	MaxBackoff   time.Duration
	Logf         func(format string, args ...any)
}

// Status is a snapshot for /api/status.
type DetectorStatus struct {
	State     string    `json:"state"`
	Model     string    `json:"model,omitempty"`
	Input     []int     `json:"input,omitempty"`
	LoadMs    float64   `json:"load_ms,omitempty"`
	PID       int       `json:"pid,omitempty"`
	Restarts  int       `json:"restarts"`
	LastError string    `json:"last_error,omitempty"`
	Since     time.Time `json:"since"`
}

type proc struct {
	cmd   *exec.Cmd
	stdin io.WriteCloser
	lines chan string   // stdout lines; closed on EOF
	done  chan struct{} // closed after Wait returns
	err   error         // Wait result, valid after done
}

func (p *proc) kill() {
	if p.cmd.Process != nil {
		p.cmd.Process.Kill()
	}
}

// Manager owns the detector child.
type Manager struct {
	cfg ManagerConfig

	reqMu sync.Mutex // serialises requests

	mu      sync.Mutex
	cur     *proc
	readyCh chan struct{} // closed while state == ready
	status  DetectorStatus

	stop   context.CancelFunc
	ctx    context.Context
	exited chan struct{}
}

// NewManager creates a manager; call Start to launch the child.
func NewManager(cfg ManagerConfig) *Manager {
	if cfg.Timeout == 0 {
		cfg.Timeout = 10 * time.Second
	}
	if cfg.ReadyTimeout == 0 {
		cfg.ReadyTimeout = 60 * time.Second
	}
	if cfg.MinBackoff == 0 {
		cfg.MinBackoff = 500 * time.Millisecond
	}
	if cfg.MaxBackoff == 0 {
		cfg.MaxBackoff = 30 * time.Second
	}
	if cfg.Logf == nil {
		cfg.Logf = log.Printf
	}
	ctx, cancel := context.WithCancel(context.Background())
	return &Manager{
		cfg:     cfg,
		readyCh: make(chan struct{}),
		status:  DetectorStatus{State: StateStarting, Since: time.Now()},
		ctx:     ctx,
		stop:    cancel,
		exited:  make(chan struct{}),
	}
}

// Start launches the supervisor goroutine (start, wait for exit, restart).
func (m *Manager) Start() { go m.supervise() }

// Close kills the child and stops restarting it.
func (m *Manager) Close() {
	m.stop()
	m.mu.Lock()
	if m.cur != nil {
		m.cur.stdin.Close() // a well-behaved detector exits on EOF
		m.cur.kill()
	}
	m.mu.Unlock()
	<-m.exited
}

// Status returns a snapshot of the detector state.
func (m *Manager) Status() DetectorStatus {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.status
}

func (m *Manager) setState(state, errMsg string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if state == StateReady {
		select {
		case <-m.readyCh:
		default:
			close(m.readyCh)
		}
	} else {
		select {
		case <-m.readyCh:
			m.readyCh = make(chan struct{})
		default:
		}
	}
	m.status.State = state
	m.status.Since = time.Now()
	if errMsg != "" {
		m.status.LastError = errMsg
	}
}

func (m *Manager) supervise() {
	defer close(m.exited)
	backoff := m.cfg.MinBackoff
	first := true
	for {
		if !first {
			m.mu.Lock()
			m.status.Restarts++
			m.mu.Unlock()
		}
		first = false
		started := time.Now()
		p, info, err := m.spawn()
		if err != nil {
			if m.ctx.Err() != nil {
				m.setState(StateStopped, "")
				return
			}
			m.cfg.Logf("detector: start failed: %v (retry in %v)", err, backoff)
			m.setState(StateError, err.Error())
		} else {
			m.mu.Lock()
			m.cur = p
			m.status.Model, m.status.Input, m.status.LoadMs = info.Model, info.Input, info.LoadMs
			m.status.PID = p.cmd.Process.Pid
			m.mu.Unlock()
			m.cfg.Logf("detector: ready (pid %d, model %s, load %.1f ms)", p.cmd.Process.Pid, info.Model, info.LoadMs)
			m.setState(StateReady, "")

			select {
			case <-p.done:
			case <-m.ctx.Done():
				p.stdin.Close()
				p.kill()
				<-p.done
			}
			if m.ctx.Err() != nil {
				m.setState(StateStopped, "")
				return
			}
			m.cfg.Logf("detector: exited: %v (restart in %v)", exitText(p.err), backoff)
			m.markDown(p, "detector exited: "+exitText(p.err)) // no-op if a request already did it
			if time.Since(started) > time.Minute {
				backoff = m.cfg.MinBackoff // it ran fine for a while: restart quickly
			}
		}
		select {
		case <-time.After(backoff):
		case <-m.ctx.Done():
			m.setState(StateStopped, "")
			return
		}
		backoff = min(backoff*2, m.cfg.MaxBackoff)
	}
}

func exitText(err error) string {
	if err == nil {
		return "exit status 0"
	}
	return err.Error()
}

// spawn starts the child and waits for the ready line.
func (m *Manager) spawn() (*proc, ReadyInfo, error) {
	var info ReadyInfo
	cmd := exec.Command(m.cfg.Path, m.cfg.Args...)
	if len(m.cfg.Env) > 0 {
		cmd.Env = append(os.Environ(), m.cfg.Env...)
	}
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, info, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, info, err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, info, err
	}
	if err := cmd.Start(); err != nil {
		return nil, info, err
	}
	p := &proc{cmd: cmd, stdin: stdin, lines: make(chan string, 4), done: make(chan struct{})}

	name := filepath.Base(m.cfg.Path)
	var wg sync.WaitGroup
	wg.Add(2)
	go func() { // stderr -> log
		defer wg.Done()
		sc := bufio.NewScanner(stderr)
		sc.Buffer(make([]byte, 4096), 64*1024)
		for sc.Scan() {
			m.cfg.Logf("[%s] %s", name, sc.Text())
		}
		io.Copy(io.Discard, stderr)
	}()
	go func() { // stdout -> lines
		defer wg.Done()
		defer close(p.lines)
		sc := bufio.NewScanner(stdout)
		sc.Buffer(make([]byte, 64*1024), 4*1024*1024)
		for sc.Scan() {
			p.lines <- sc.Text()
		}
		if err := sc.Err(); err != nil {
			m.cfg.Logf("detector: stdout: %v", err)
			p.kill()
		}
		io.Copy(io.Discard, stdout)
	}()
	go func() {
		wg.Wait() // Wait must not be called before the pipes are drained
		p.err = cmd.Wait()
		close(p.done)
	}()

	fail := func(err error) (*proc, ReadyInfo, error) {
		p.kill()
		<-p.done
		return nil, info, err
	}
	timer := time.NewTimer(m.cfg.ReadyTimeout)
	defer timer.Stop()
	select {
	case line, ok := <-p.lines:
		if !ok {
			<-p.done
			return nil, info, fmt.Errorf("exited before ready line: %s", exitText(p.err))
		}
		if err := json.Unmarshal([]byte(line), &info); err != nil {
			return fail(fmt.Errorf("bad ready line %q", truncate(line, 200)))
		}
		if !info.Ready {
			if info.Error == "" {
				info.Error = "ready:false"
			}
			return fail(fmt.Errorf("not ready: %s", info.Error))
		}
		return p, info, nil
	case <-timer.C:
		return fail(fmt.Errorf("no ready line after %v", m.cfg.ReadyTimeout))
	case <-m.ctx.Done():
		return fail(ErrStopped)
	}
}

// Detect sends one image path and returns the detector's answer. It waits (up to the request timeout) for the
// detector to become ready, so a request that arrives during a restart is served once the model is loaded.
func (m *Manager) Detect(ctx context.Context, path string) (*Result, error) {
	if strings.ContainsAny(path, "\r\n") {
		return nil, errors.New("path contains a newline")
	}
	deadline := time.NewTimer(m.cfg.Timeout)
	defer deadline.Stop()

	// Wait for our turn.
	locked := make(chan struct{})
	go func() { m.reqMu.Lock(); close(locked) }()
	select {
	case <-locked:
	case <-ctx.Done():
		go func() { <-locked; m.reqMu.Unlock() }()
		return nil, ctx.Err()
	}
	defer m.reqMu.Unlock()
	// The queue wait does not count against the detector: restart the timer for the detector itself.
	deadline.Reset(m.cfg.Timeout)

	var p *proc
	for p == nil {
		m.mu.Lock()
		readyCh := m.readyCh
		m.mu.Unlock()
		select {
		case <-readyCh:
		case <-deadline.C:
			return nil, fmt.Errorf("%w (%s)", ErrNotReady, m.Status().State)
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-m.ctx.Done():
			return nil, ErrStopped
		}
		m.mu.Lock()
		p = m.cur
		m.mu.Unlock()
		if p == nil {
			continue
		}
		// It may have died while idle, before the supervisor noticed: wait for the restart.
		select {
		case <-p.done:
			m.markDown(p, "detector exited: "+exitText(p.err))
			p = nil
			continue
		default:
		}
		// Drop anything stale (should never happen with a well-behaved detector).
		for drained := false; !drained && p != nil; {
			select {
			case l, ok := <-p.lines:
				if !ok {
					<-p.done
					m.markDown(p, "detector exited: "+exitText(p.err))
					p = nil
					break
				}
				m.cfg.Logf("detector: dropping unexpected line %q", truncate(l, 200))
			default:
				drained = true
			}
		}
	}

	if _, err := io.WriteString(p.stdin, path+"\n"); err != nil {
		p.kill()
		<-p.done
		m.markDown(p, "detector exited: "+exitText(p.err))
		return nil, fmt.Errorf("%w: write: %v", ErrDied, err)
	}
	select {
	case line, ok := <-p.lines:
		if !ok {
			<-p.done
			m.markDown(p, "detector exited: "+exitText(p.err))
			return nil, fmt.Errorf("%w: %s", ErrDied, exitText(p.err))
		}
		var res Result
		if err := json.Unmarshal([]byte(line), &res); err != nil {
			m.cfg.Logf("detector: malformed line %q", truncate(line, 200))
			return nil, fmt.Errorf("%w: %q", ErrMalformed, truncate(line, 120))
		}
		res.Raw = json.RawMessage(line)
		return &res, nil
	case <-deadline.C:
		m.cfg.Logf("detector: no answer after %v, killing pid %d", m.cfg.Timeout, p.cmd.Process.Pid)
		p.kill() // the supervisor restarts it; we cannot resynchronise a stuck detector
		<-p.done
		m.markDown(p, "timeout after "+m.cfg.Timeout.String())
		return nil, ErrTimeout
	case <-ctx.Done():
		// Client went away; still wait for the answer so the stream stays in sync.
		select {
		case <-p.lines:
		case <-deadline.C:
			p.kill()
		}
		return nil, ctx.Err()
	}
}

// markDown flags the detector as restarting as soon as a request notices it is gone, so the next request waits
// for the supervisor's restart instead of using the dead process.
func (m *Manager) markDown(p *proc, msg string) {
	m.mu.Lock()
	if m.cur != p {
		m.mu.Unlock()
		return
	}
	m.cur = nil
	m.status.PID = 0
	m.mu.Unlock()
	m.setState(StateRestarting, msg)
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
