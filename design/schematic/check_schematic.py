#!/usr/bin/env python3
"""Phase 5 gate self-check (TP-D5). Reads the GENERATED KiCad netlist out/board.net with its own s-expression parser
(it does not import the SKiDL code), plus out/pins.csv / out/erc.txt / out/board.log, and checks it against
design/bom.csv, design/pinmap.csv, design/power_rails.csv, PLAN.md test points and schematic/ref_connections.csv.

Usage: design/.venv/bin/python -I design/schematic/check_schematic.py   (run board.py first)
Exit code 0 = all checks pass.
"""
import csv
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.dirname(HERE)
OUT = os.environ.get("SCHEM_OUT", os.path.join(HERE, "out"))  # override only for mutation tests
RES = {"pass": 0, "fail": 0}


def chk(cond, msg, cat):
    RES["pass" if cond else "fail"] += 1
    if not cond or os.environ.get("VERBOSE"):
        print(("PASS " if cond else "FAIL ") + cat + " " + msg)


# ---------------------------------------------------------------- s-expression netlist parser
def sexp(text):
    tok = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack, cur = [], []
    for t in tok:
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def val(node, key, default=""):
    f = find(node, key)
    return f[0][1] if f and len(f[0]) > 1 else default


tree = sexp(open(os.path.join(OUT, "board.net"), encoding="utf-8").read())
comps = {}
for c in find(find(tree, "components")[0], "comp"):
    ref = val(c, "ref")
    fields = {}
    for fs in find(c, "fields"):
        for f in find(fs, "field"):
            fields[val(f, "name")] = f[2] if len(f) > 2 else ""
    props = {val(p, "name") for p in find(c, "property")}
    comps[ref] = dict(value=val(c, "value"), footprint=val(c, "footprint"), fields=fields, props=props)
nets = {}
pin_net = {}
for n in find(find(tree, "nets")[0], "net"):
    name = val(n, "name")
    nodes = [(val(x, "ref"), val(x, "pin")) for x in find(n, "node")]
    nets[name] = nodes
    for rp in nodes:
        pin_net[rp] = name
func = {c["fields"].get("Functional"): r for r, c in comps.items()}
pins = {}
with open(os.path.join(OUT, "pins.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        pins.setdefault(r["ref"], []).append(r)

# ---------------------------------------------------------------- S1 netlist sanity
chk(len(comps) > 0 and len(nets) > 0, f"netlist parsed: {len(comps)} components, {len(nets)} nets", "S1")
auto = [n for n in nets if re.match(r"^(N\$|Net-|unconnected)", n)]
chk(not auto, f"every net is named (auto-named: {auto[:5]})", "S1")
single = [n for n, nodes in nets.items() if len(nodes) < 2]
chk(not single, f"no single-node nets ({single})", "S1")
chk(all(re.match(r"^[A-Z]+\d+$", r) for r in comps), "every ref is prefix+number", "S1")

# ---------------------------------------------------------------- S2 BOM <-> schematic
bom = {}
with open(os.path.join(DESIGN, "bom.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        for r in row["ref"].split():
            bom[r] = row
for r, row in bom.items():
    c = comps.get(r)
    chk(c is not None, f"BOM ref {r} present in netlist", "S2")
    if c:
        chk(c["value"] == row["value"] and c["footprint"] == row["footprint"] and c["fields"].get("LCSC") == row["lcsc"],
            f"{r}: value/footprint/LCSC = bom.csv ({row['value']}, {row['footprint']}, {row['lcsc']})", "S2")
        chk("exclude_from_bom" not in c["props"] and "dnp" not in c["props"], f"{r}: fitted, in BOM (no dnp/exclude property)", "S2")
extra = sorted(set(comps) - set(bom))
chk(all(re.match(r"^(TP|JP|NT)\d+$", r) and "exclude_from_bom" in comps[r]["props"] for r in extra),
    f"non-BOM parts are copper-only TP/JP/NT with exclude_from_bom: {len(extra)} ({' '.join(extra)})", "S2")
qty = sum(int(row["qty_per_board"]) for row in {id(v): v for v in bom.values()}.values())
chk(qty == len(bom) == len(comps) - len(extra), f"BOM qty/board {qty} = netlist BOM parts {len(comps) - len(extra)}", "S2")

# ---------------------------------------------------------------- S3 symbol pins = footprint pads
CUSTOM_PADS = {  # board: footprints (drawn in Phase 7 / H1, D-74): pad names the drawing must carry
    "board:RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm": {str(i) for i in range(1, 130)},
    "board:TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm": {str(i) for i in range(1, 11)},
    "board:L_FHD4020S_4.0x4.0mm": {"1", "2"},
    "board:SW_TS-1187A_5.1x5.1mm": {"1", "2", "3", "4"},
    "board:microSD_TF-01A": {str(i) for i in range(1, 10)} | {"SH"},
    "board:USB_A_AF90_WJDG_RightAngle_THT": {"1", "2", "3", "4", "SH"},
}
modcache = os.path.join(DESIGN, "refs", "kicad-footprints-mods-2026-10-29")
modcache6 = os.path.join(DESIGN, "refs", "kicad-footprints-p6-2026-10-29")   # TestPoint/Jumper/NetTie (Phase 6)
for r, c in sorted(comps.items()):
    fp = c["footprint"]
    sym = {p["pin"] for p in pins.get(r, [])}
    if fp.startswith("board:"):
        chk(sym == CUSTOM_PADS[fp], f"{r} {fp}: symbol pins = drawing pad names ({len(sym)})", "S3")
        continue
    mod = os.path.join(modcache, fp.replace(":", "__") + ".kicad_mod")
    if not os.path.exists(mod):
        mod = os.path.join(modcache6, fp.replace(":", "__") + ".kicad_mod")
    if os.path.exists(mod):
        pads = set(re.findall(r'\(pad "([^"]+)"', open(mod, encoding="utf-8").read()))
        chk(sym == pads, f"{r} {fp}: symbol pins {sorted(sym)} = cached .kicad_mod pad names", "S3")
    else:
        chk(re.match(r"^(TP|JP|NT)\d+$", r) is not None, f"{r} {fp}: footprint not cached (copper-only part, UNVERIFIED name)", "S3")

# ---------------------------------------------------------------- S4 SoC pin-by-pin vs pinmap.csv
soc = func["U_SOC"]
NC_WITH_EXTERNAL = {"58"}
with open(os.path.join(DESIGN, "pinmap.csv"), encoding="utf-8") as f:
    pm = list(csv.DictReader(f))
socpins = {p["pin"]: p for p in pins[soc]}
chk(len(socpins) == 129 == len(pm), f"SoC symbol has 129 pins = pinmap rows {len(pm)}", "S4")
for row in pm:
    num = "129" if row["pin"] == "EPAD" else row["pin"]
    actual = pin_net.get((soc, num), "NC")
    chk(socpins[num]["name"] == row["ds_pin_name"], f"pin {num} name = [DS] name {row['ds_pin_name'][:30]}", "S4")
    if row["net"] == "NC" and num not in NC_WITH_EXTERNAL:
        chk(actual == "NC", f"pin {num} unconnected (pinmap NC)", "S4")
    elif row["net"] == "NC":
        chk(actual != "NC" and len(nets[actual]) == 2, f"pin {num}: pinmap NC + external '{row['external']}' -> own net {actual}", "S4")
    else:
        chk(actual == row["net"], f"pin {num} net {actual} = pinmap {row['net']}", "S4")

# ---------------------------------------------------------------- S5 reference connections (hand-written)
n_ref = 0
with open(os.path.join(HERE, "ref_connections.csv"), encoding="utf-8") as f:
    lines = [l for l in f if not l.startswith("#")]
for row in csv.DictReader(lines):
    n_ref += 1
    r = func.get(row["functional"])
    if r is None:
        chk(False, f"{row['functional']}: not in netlist ({row['source']})", "S5")
        continue
    if row["pin"] == "*":
        ok = any(net == row["net"] for (rr, _), net in pin_net.items() if rr == r)
    else:
        num = row["pin"]
        ok = pin_net.get((r, num)) == row["net"]
    chk(ok, f"{row['functional']} [{r}] pin {row['pin']} on {row['net']} ({row['source']})", "S5")
chk(n_ref >= 200, f"{n_ref} reference connections checked", "S5")

# ---------------------------------------------------------------- S6 decoupling on every supply pin
for row in pm:
    if row["status"] != "POWER" or row["net"] == "GND":
        continue
    num = row["pin"]
    caps = [r for r, c in comps.items() if r.startswith("C") and c["fields"].get("place_near") == f"U_SOC pin {num}"]
    good = [r for r in caps if {pin_net.get((r, "1")), pin_net.get((r, "2"))} == {row["net"], "GND"}]
    chk(len(good) >= 1, f"SoC pin {num} {row['ds_pin_name']} ({row['net']}): decoupling {good}", "S6")
IC_SUPPLY = [("U_ONOFF", "1"), ("U4", "4"), ("U5", "4"), ("U6", "4"), ("U7", "4"), ("U_USBA", "5"),
             ("U_NAND", "8"), ("U_MUX", "10")]
for fn, pn in IC_SUPPLY:
    r = func.get(fn)
    net = pin_net.get((r, pn))
    if net is None or net == "NC":      # missing pin/part: report a FAIL instead of crashing (verifier P5 minor 6)
        chk(False, f"{fn} [{r}] supply pin {pn} is not connected in the netlist", "S6")
        continue
    caps = [c for c in comps if c.startswith("C") and {pin_net.get((c, "1")), pin_net.get((c, "2"))} == {net, "GND"}
            and comps[c]["fields"].get("place_near", "").startswith(fn)]
    chk(len(caps) >= 1, f"{fn} [{r}] supply pin {pn} ({net}): local capacitor(s) {caps}", "S6")
rails = {}
with open(os.path.join(DESIGN, "power_rails.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rails[r["rail"]] = r
for row in pm:
    if row["status"] == "POWER" and row["net"] != "GND":
        chk(row["net"] in rails, f"SoC pin {row['pin']} net {row['net']} is a rail in power_rails.csv", "S6")
# total capacitance per buck rail = power_rails.csv budget (check_power P10 input)
def cap_uf(v):
    m = re.match(r"([\d.]+)\s*(uF|nF|pF)", v)
    return float(m.group(1)) * {"uF": 1, "nF": 1e-3, "pF": 1e-6}[m.group(2)] if m else 0.0
GROUP = {"VDD_0V9": ["VDD_0V9", "VDD_ARM"], "VCC_DDR": ["VCC_DDR"],
         "VCC_1V8": ["VCC_1V8", "MIPI_CSI_AVDD_1V8", "AVDD1V8_USB", "VCC1V8_CODEC", "ETH_AVDD1V8"],
         "VCC_3V3": ["VCC_3V3", "FEPHY_AVDD3V3"]}
for rail, members in GROUP.items():
    tot = 0.0
    for r, c in comps.items():
        if r.startswith("C") and not c["value"].startswith("6.8pF"):
            ns = {pin_net.get((r, "1")), pin_net.get((r, "2"))}
            if "GND" in ns and ns & set(members):
                tot += cap_uf(c["value"])
    exp = float(rails[rail]["c_soc_min_uf"])
    tol = 0.05 if rail != "VCC_3V3" else 0.0
    if rail == "VCC_3V3":   # power_rails counts 11.2 uF incl. NAND, mux, SD-switch input; schematic must match
        chk(abs(tot - exp) < 0.05, f"{rail} SoC/peripheral caps {tot:.1f} uF = power_rails c_soc_min {exp}", "S6")
    else:
        chk(abs(tot - exp) <= tol + 1e-6, f"{rail} SoC/peripheral caps {tot:.2f} uF = power_rails c_soc {exp}", "S6")

# ---------------------------------------------------------------- S7 test-point plan nets exist and carry a TP
# Phase 6 (D-77): the physical TP list is design/testpoints.md; refs are checked, not only nets.
TP_PLAN = {"TP1": "VBUS_5V", "TP2": "VCC_3V3", "TP3": "VCC_1V8", "TP4": "VDD_0V9", "TP5": "VCC_DDR",
           "TP6": "OSC_XOUT", "TP7": "NPOR", "TP8": "ONOFF_EN", "TP9": "UART2_TX", "TP10": "UART2_RX",
           "TP11": "LED_ETH", "TP12": "EN_N", "TP13": "VCC5V0_SYS", "TP14": "PWR_EN", "TP15": "VDD_ARM",
           "TP16": "VCC3V3_SD", "TP17": "VBUS_USBA", "TP18": "VCC3V3_RTC", "TP19": "GND", "TP20": "GND",
           "TP21": "VBUS_IN", "TP22": "MIPI_CSI_AVDD_1V8", "TP23": "AVDD1V8_USB", "TP24": "VCC1V8_CODEC",
           "TP25": "ETH_AVDD1V8", "TP26": "FEPHY_AVDD3V3", "TP27": "PB_INT_N", "TP28": "PWR_KILL",
           "TP29": "PWR_KILL_N", "TP30": "SDMMC_DET", "TP31": "GND"}
tp_net = {r: n for n, nodes in nets.items() for r, _ in nodes if r.startswith("TP")}
for tp, net in TP_PLAN.items():
    chk(tp_net.get(tp) == net, f"test point {tp} on net {net} (netlist: {tp_net.get(tp)})", "S7")
chk(set(tp_net) == set(TP_PLAN), f"netlist test pads = testpoints.md list ({len(tp_net)}); extra "
    f"{sorted(set(tp_net) - set(TP_PLAN))}, missing {sorted(set(TP_PLAN) - set(tp_net))}", "S7")
for rail, r in rails.items():           # every rail of power_rails.csv (input, switch, buck, subrail) has a pad
    has = rail in nets and any(x.startswith("TP") for x, _ in nets[rail])
    chk(has, f"rail {rail} ({r['kind']}) has a test pad", "S7")
tpmd = os.path.join(DESIGN, "testpoints.md")
if os.path.exists(tpmd):                # every TP row in testpoints.md names the same net as the netlist
    rows = re.findall(r"^\|\s*\*{0,2}(TP\d+)\*{0,2}\s*\|\s*`?([A-Z0-9_]+)`?", open(tpmd, encoding="utf-8").read(), re.M)
    md = {}
    for tp, net in rows:
        md.setdefault(tp, net)
    chk(set(md) == set(TP_PLAN), f"testpoints.md lists {len(md)} TPs = netlist set", "S7")
    for tp, net in md.items():
        chk(tp_net.get(tp) == net, f"testpoints.md {tp} = {net}, netlist {tp_net.get(tp)}", "S7")
    # Phase 6 r2 (D-80): every "NAME [REF]" in the bench documents names the part printed as REF on the board
    # (functional name from the netlist, or a bench name from the testpoints.md "Part names" table).
    tptext = open(tpmd, encoding="utf-8").read()
    bench = dict(re.findall(r"^\|\s*(R_[A-Z0-9_]+|C_[A-Z0-9_]+)\s*\|\s*([A-Z]+\d+)\s*\|", tptext, re.M))
    chk(len(bench) >= 9, f"testpoints.md bench-name table parsed ({len(bench)} names)", "S7")
    byref = {r: n for n, r in func.items() if n}
    for doc in ("testpoints.md", "bringup.md"):
        path = os.path.join(DESIGN, doc)
        if not os.path.exists(path):
            continue
        pairs = sorted(set(re.findall(r"\b([A-Z][A-Za-z0-9_]*) \[([A-Z]+\d+)\]", open(path, encoding="utf-8").read())))
        bad = [f"{n} [{r}]" for n, r in pairs
               if r not in comps or (func.get(n) != r and bench.get(n) != r)
               or (n in comps and n != r)]       # a bare [LF] designator that is another part's silkscreen ref
        chk(not bad, f"{doc}: {len(pairs)} 'NAME [silkscreen ref]' pairs all match the netlist (bad: {bad[:6]})", "S7")

# ---------------------------------------------------------------- S8 ERC and generator warnings
erc = open(os.path.join(OUT, "erc.txt"), encoding="utf-8").read()
chk("No errors or warnings found" in erc, f"SKiDL ERC: {erc.strip()[:80]}", "S8")
log = open(os.path.join(OUT, "board.log"), encoding="utf-8").read() if os.path.exists(os.path.join(OUT, "board.log")) else ""
JUSTIFIED = [r"fp-lib-table file was not found", r"_SYMBOL_DIR environment variable is missing",
             r"Missing tag on\s+instantiated at .*<frozen importlib"]
warns = [l for l in log.splitlines() if l.startswith("WARNING")]
unjust = [w for w in warns if not any(re.search(p, w) for p in JUSTIFIED)]
chk(not unjust, f"{len(warns)} generator warnings, all justified in README §ERC ({unjust[:3]})", "S8")
chk("ERROR" not in log, "no generator errors", "S8")

# ---------------------------------------------------------------- S9 only the intended pins are unconnected
ALLOWED_NC = {(func["J_USBC"], "A8"), (func["J_USBC"], "B8"), (func["U_ONOFF"], "3"),
              *[(func["J_RJ45"], p) for p in ("7", "9", "10", "11", "12")],
              *[(soc, "129" if r["pin"] == "EPAD" else r["pin"]) for r in pm if r["net"] == "NC" and r["pin"] not in NC_WITH_EXTERNAL]}
nc = {(r, p["pin"]) for r, pl in pins.items() for p in pl if p["net"] == "NC"}
chk(nc == ALLOWED_NC, f"unconnected pins = intended set ({len(nc)}); unexpected {sorted(nc - ALLOWED_NC)[:5]}, "
                      f"missing {sorted(ALLOWED_NC - nc)[:5]}", "S9")

# ---------------------------------------------------------------- S10 refmap up to date
rc = subprocess.run([sys.executable, "-I", os.path.join(DESIGN, "tools", "make_refmap.py"), DESIGN, "--check"],
                    capture_output=True, text=True)
chk(rc.returncode == 0, f"refmap.csv up to date with make_bom part list ({rc.stdout.strip()})", "S10")
with open(os.path.join(DESIGN, "refmap.csv"), encoding="utf-8") as f:
    rm = list(csv.DictReader(f))
chk({r["bom_ref"] for r in rm if r["bom_ref"]} == set(bom), "refmap.csv names every bom.csv ref", "S10")
for r in rm:
    if r["bom_ref"]:
        chk(comps[r["bom_ref"]]["fields"].get("Functional") == r["functional_name"],
            f"{r['bom_ref']} Functional field = refmap {r['functional_name']}", "S10")

print(f"RESULT: {RES['pass']} pass, {RES['fail']} fail")
sys.exit(1 if RES["fail"] else 0)
