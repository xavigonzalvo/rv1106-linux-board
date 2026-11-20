"""TP-D2 self-check for design/pinmap.csv.
Usage (from anywhere):  <venv>/bin/python -I design/tools/check_pinmap.py <design dir>
Reads the datasheet PDF under refs/ as data only (pymupdf text extraction)."""
import csv, os, re, sys
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
from ds_pins import parse

D = sys.argv[1]
ds = parse(os.path.join(D, "refs/rv1106-datasheet-r1.8/RV1106_Datasheet_r1.8.pdf"))
rows = list(csv.DictReader(open(os.path.join(D, "pinmap.csv"))))
err, ok = [], []
def chk(cond, msg):
    (ok if cond else err).append(msg)
bad0 = [r.get("pin") for r in rows if None in r or any(v is None for v in r.values())]
chk(not bad0, f"C0 pinmap.csv is well-formed: every row has exactly the header's 15 fields (bad: {bad0})")

key = lambda r: "EPAD" if r["pin"] == "EPAD" else int(r["pin"])
pins = [key(r) for r in rows]
chk(len(pins) == len(set(pins)), "C1 no duplicate pin rows")
chk(set(pins) == set(ds), f"C2 pinmap covers exactly the {len(ds)} datasheet pins (128 + EPAD)")

bad = [r["pin"] for r in rows if ds[key(r)] != r["ds_pin_name"]]
chk(not bad, f"C3 ds_pin_name matches [DS] Table 2-1 text for every pin (mismatch: {bad})")

def tokens(name):
    """[DS] mux list split on '/', with and without the _u/_d/_z reset-pull suffix."""
    t = name.split("/")
    return set(t) | {x[:-2] for x in t if x[-2:] in ("_u", "_d", "_z")}
def suffix(name):
    last = name.split("/")[-1]
    return {"_u": "pull-up", "_d": "pull-down", "_z": "high-Z"}.get(last[-2:])

badf = []
for r in rows:
    f = r["function_used"]
    if f.startswith("("): continue
    if not all(x in tokens(r["ds_pin_name"]) for x in f.split("/")): badf.append(r["pin"])
chk(not badf, f"C4 function_used is an exact token of the pin's [DS] '/'-separated mux list (bad: {badf})")

shared = {"GND", "NC", "VDD_0V9", "VCC_DDR", "VCC_1V8", "VCC_3V3"}
from collections import Counter
c = Counter(r["net"] for r in rows if r["net"] not in shared)
dup = [n for n, k in c.items() if k > 1]
chk(not dup, f"C5 every signal net is on exactly one SoC pin (no pin/net used twice) (dups: {dup})")

nosrc = [r["pin"] for r in rows if not re.search(r"\[(DS|LF|SDK)\]", r["source"])]
chk(not nosrc, f"C6 every row cites [DS]/[LF]/[SDK] (missing: {nosrc})")

# IO-domain consistency
def dom(r): return r["io_domain"], r["domain_voltage"]
rules = {"nand": ("VCCIO3", "3.3V"), "sd": None, "uart": ("VCCIO1", "3.3V"), "gpio": None}
bd = []
for r in rows:
    d, v = dom(r)
    if r["status"].startswith("NC") or r["status"] == "POWER": continue
    if r["block"] == "nand" and d != "VCCIO3": bd.append(r["pin"])
    if r["block"] == "sd" and r["net"] != "SDMMC_PWREN" and d != "VCCIO4": bd.append(r["pin"])
    if r["block"] == "uart" and d != "VCCIO1": bd.append(r["pin"])
    if r["block"] == "eth" and d != "ANALOG-ETH": bd.append(r["pin"])
    if r["block"] in ("gpio", "nand", "sd", "uart") and not v.startswith("3.3V"): bd.append(r["pin"])
    if r["net"] in ("RECOVERY", "SARADC_IN1") and (d != "VCCIO2" or not v.startswith("1.8V")): bd.append(r["pin"])
    if d == "VCCIO7" or (d == "VCCIO2" and r["net"] not in ("RECOVERY", "SARADC_IN1")): bd.append(r["pin"])
chk(not bd, f"C7 IO domains: NAND on VCCIO3, SD on VCCIO4, UART on VCCIO1, header on 3.3V domains, SARADC on 1.8V VCCIO2, nothing used on 1.8V VCCIO7 (bad: {bd})")

sup = {43: "3V3", 13: "3V3", 108: "3V3", 88: "3V3", 81: "3V3", 61: "3V3", 1: "1V8", 24: "1V8"}
bs = [p for p, v in sup.items() if v not in next(r for r in rows if key(r) == p)["net"]]
chk(not bs, f"C8 domain supply pins tied to the rail the pinmap assumes (bad: {bs})")

safe = {"PWR_KILL": "pull-down", "USB_SEL": "pull-down", "USBA_VBUS_EN": "pull-down",
        "LED_STATUS": "pull-up", "LED_ETH": "pull-down", "SDMMC_PWREN": "pull-down"}
bsafe = []
for n, want in safe.items():
    rr = [r for r in rows if r["net"] == n]
    if len(rr) != 1 or suffix(ds[key(rr[0])]) != want: bsafe.append(n)
chk(not bsafe, f"C9 reset pull of every control output, derived from the [DS] _u/_d suffix, agrees with its safe state (bad: {bsafe})")

col = {"pull-up": "pull-up", "pull-down": "pull-down", "high-Z": "high-Z"}
bcol = [r["pin"] for r in rows
        if (suffix(ds[key(r)]) or "none") != (col.get(r["reset_pull"]) or "none")]
chk(not bcol, f"C12 reset_pull column agrees with the [DS] suffix on all rows (bad: {bcol})")

ALWAYS_ON = re.compile(r"\bVBUS(_IN|_5V)?\b|USB-C VBUS|VCC3V3_RTC")
bao = [r["pin"] for r in rows if r["io_domain"] != "ANALOG-RTC" and ALWAYS_ON.search(r["external"])]
chk(not bao, f"C13 no external pull-up/divider/driven source on a SoC pin comes from an always-on rail (VBUS_IN/VBUS_5V/VCC3V3_RTC) (bad: {bao})")
v = next(r for r in rows if r["pin"] == "25")
chk("VCC5V0_SYS" in v["external"] and "R2/R5" in v["external"],
    "C14 pin 25 USB_VBUSDET divider (LF R2/R5) is fed from switched VCC5V0_SYS (D-27)")

def ext(n): return next(r["external"] for r in rows if r["net"] == n)
bi2c = [n for n in ("HDR_I2C3_SCL", "HDR_I2C3_SDA", "HDR_I2C1_SCL", "HDR_I2C1_SDA")
        if not re.search(r"\d(\.\d)?k pull-up to VCC_3V3", ext(n))]
chk(not bi2c, f"C15 header I2C lines have external pull-ups to VCC_3V3 (D-29) (missing: {bi2c})")
bser = [n for n in ("UART2_RX", "UART2_TX") if "1k series" not in ext(n)]
chk(not bser, f"C16 debug UART lines have 1k series resistors against back-powering (D-30) (missing: {bser})")

strap = [r["pin"] for r in rows if "BOOT STRAP" in r["status"]]
chk(strap == ["23"], f"C10 boot strap pin identified: SARADC_IN0 pin 23 (found {strap})")

hdr = {}
for r in rows:
    m = re.search(r"2x20 header pin (\d+)", r["external"])
    if m: hdr.setdefault(int(m.group(1)), []).append(r["pin"])
power_hdr = {1, 17, 2, 4, 6, 9, 14, 20, 25, 30, 34, 39}
dupe_h = [h for h, v in hdr.items() if len(v) > 1 or h in power_hdr]
chk(not dupe_h and set(hdr) | power_hdr == set(range(1, 41)),
    f"C11 2x20 header: 28 signal + 12 power positions, each used once (problem: {dupe_h}, signals={len(hdr)})")

for m in ok: print("PASS", m)
for m in err: print("FAIL", m)
print(f"\n{len(ok)} pass, {len(err)} fail")
sys.exit(1 if err else 0)
