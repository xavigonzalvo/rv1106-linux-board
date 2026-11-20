// hello-http: tiny HTTP server for the RV1106 board.
// Build on the Mac:  CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -ldflags="-s -w"
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
)

func read(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return "?"
	}
	return strings.TrimSpace(string(b))
}

func led(gpio, on string) {
	os.WriteFile("/sys/class/gpio/export", []byte(gpio), 0) // ignore "already exported"
	os.WriteFile("/sys/class/gpio/gpio"+gpio+"/direction", []byte("out"), 0)
	os.WriteFile("/sys/class/gpio/gpio"+gpio+"/value", []byte(on), 0)
}

func main() {
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		t, _ := strconv.Atoi(read("/sys/class/thermal/thermal_zone0/temp"))
		up := strings.Fields(read("/proc/uptime"))[0]
		fmt.Fprintf(w, "Hello from the RV1106 Rev A board!\nuptime %s s, SoC %.1f C\n", up, float64(t)/1000)
		fmt.Fprintf(w, "Try /stat/on, /stat/off\n")
	})
	// STAT LED: GPIO0_A3 = gpio 3, active-low
	http.HandleFunc("/stat/on", func(w http.ResponseWriter, r *http.Request) { led("3", "0"); fmt.Fprintln(w, "STAT on") })
	http.HandleFunc("/stat/off", func(w http.ResponseWriter, r *http.Request) { led("3", "1"); fmt.Fprintln(w, "STAT off") })
	log.Println("listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
