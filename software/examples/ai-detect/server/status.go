package main

// System information for /api/status. Every source is optional: on the Mac none of these files exist.

import (
	"os"
	"strconv"
	"strings"
)

type SystemStatus struct {
	UptimeS   *float64  `json:"uptime_s"`         // system uptime (/proc/uptime)
	TempC     *float64  `json:"temp_c"`           // SoC temperature
	MemTotalK *int64    `json:"mem_total_kb"`     // /proc/meminfo
	MemAvailK *int64    `json:"mem_available_kb"` //
	MemFreeK  *int64    `json:"mem_free_kb"`      //
	Load      []float64 `json:"load,omitempty"`   // 1, 5, 15 min
	ServerRSS *int64    `json:"server_rss_kb"`    // this process
}

// Paths are variables so tests can point them elsewhere.
var (
	pathUptime  = "/proc/uptime"
	pathTemp    = "/sys/class/thermal/thermal_zone0/temp"
	pathMeminfo = "/proc/meminfo"
	pathLoadavg = "/proc/loadavg"
	pathSelfSt  = "/proc/self/status"
)

func readSystemStatus() SystemStatus {
	var s SystemStatus
	if b, err := os.ReadFile(pathUptime); err == nil {
		if f := strings.Fields(string(b)); len(f) > 0 {
			if v, err := strconv.ParseFloat(f[0], 64); err == nil {
				s.UptimeS = &v
			}
		}
	}
	if b, err := os.ReadFile(pathTemp); err == nil {
		if v, err := strconv.ParseFloat(strings.TrimSpace(string(b)), 64); err == nil {
			c := v / 1000
			s.TempC = &c
		}
	}
	if m := readKV(pathMeminfo); m != nil {
		s.MemTotalK, s.MemAvailK, s.MemFreeK = m["MemTotal"], m["MemAvailable"], m["MemFree"]
	}
	if b, err := os.ReadFile(pathLoadavg); err == nil {
		f := strings.Fields(string(b))
		for i := 0; i < 3 && i < len(f); i++ {
			if v, err := strconv.ParseFloat(f[i], 64); err == nil {
				s.Load = append(s.Load, v)
			}
		}
	}
	if m := readKV(pathSelfSt); m != nil {
		s.ServerRSS = m["VmRSS"]
	}
	return s
}

// readKV parses "Key:   123 kB" lines.
func readKV(path string) map[string]*int64 {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	m := map[string]*int64{}
	for _, line := range strings.Split(string(b), "\n") {
		k, v, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		f := strings.Fields(v)
		if len(f) == 0 {
			continue
		}
		if n, err := strconv.ParseInt(f[0], 10, 64); err == nil {
			m[strings.TrimSpace(k)] = &n
		}
	}
	return m
}
