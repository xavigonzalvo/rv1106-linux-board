#!/usr/bin/env python3
"""Gate TP-D8 checker for Phase 8 (software).

    design/.venv/bin/python -I software/tools/check_software.py [--project DIR] [--mutations] [--keep]

Checks (PASS/FAIL per line, exit 1 on any FAIL):
  S1  both board DTS variants and the Luckfox Pro/Max reference DTS compile (C preprocessor + dtc)
  S2  dtc warnings: none from software/ files; every board warning also occurs in the reference build
  S3  every pinctrl pin of every enabled node = a USED pinmap.csv row with the same function; no pin twice
  S4  every GPIO consumer and hog = the expected pinmap net, GPIO function, polarity
  S5  gpio-line-names = pinmap.csv nets (all 5 banks)
  S6  coverage: every USED digital SoC GPIO-bank pin is claimed by the DTS or has a checked reason
  S7  research.md 7.1 / D-28 "must not inherit" list, no io-domain node, no restart-poweroff, no pmic_sleep
  S8  R4 shutdown path complete (DTS + kernel config + busybox/acpid + fallback daemon test + optional patch)
  S9  CPU OPPs <= 1.2 GHz and each target voltage <= VDD_0V9 minimum at the SoC (D-94)
  S10 storage: SFC SPI NAND, SDMMC 4-bit 3.3 V removable, NAND partition table fits 128 MiB (D-52)
  S11 USB variants (host: dr_mode host, USB_SEL/USBA_VBUS_EN high; gadget: peripheral, both low)
  S12 console: fiq-debugger on UART2 (serial-id 2, 115200), console=ttyFIQ0, UART2_M1 pins = pinmap
--mutations: re-runs the checks on broken copies of the board .dtsi and expects each to FAIL.

Reads downloaded files under design/refs/ only as data (never executes them). The C preprocessor is
run on them, which only expands #include/#define.
"""
import argparse
import csv
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROJECT = os.path.abspath(os.path.join(HERE, "..", ".."))

REL = {
    "dts_dir": "software/sdk/sysdrv/source/kernel/arch/arm/boot/dts",
    "board_dtsi": "software/sdk/sysdrv/source/kernel/arch/arm/boot/dts/rv1106-custom-reva.dtsi",
    "dts_host": "software/sdk/sysdrv/source/kernel/arch/arm/boot/dts/rv1106g-custom-reva.dts",
    "dts_gadget": "software/sdk/sysdrv/source/kernel/arch/arm/boot/dts/rv1106g-custom-reva-gadget.dts",
    "kcfg": "software/sdk/sysdrv/source/kernel/arch/arm/configs/custom-reva.config",
    "bbfrag": "software/sdk/sysdrv/tools/board/buildroot/busybox-custom-reva.fragment",
    "bcfg_dir": "software/sdk/project/cfg/BoardConfig_IPC",
    "overlay": "software/sdk/project/cfg/BoardConfig_IPC/overlay/overlay-custom-reva",
    "patch": "software/patches/0001-gpio-poweroff-optional-takeover-of-pm_power_off.patch",
    "ref_dts": "design/refs/luckfox-sdk-dts",
    "ref_bind": "design/refs/luckfox-sdk-dt-bindings-2026-10-29",
    "ref_cfg": "design/refs/luckfox-sdk-boardcfg-2026-10-29",
    "ref_busybox": "design/refs/busybox-acpid-src-2026-10-29",
    "pinmap": "design/pinmap.csv",
    "rails": "design/power_rails.csv",
    "paths": "design/layout/power_paths.csv",
}

RESULTS = []
by_gpio_global = {}


def check(cond, sid, msg):
    RESULTS.append((bool(cond), sid, msg))
    return bool(cond)


# ----------------------------------------------------------------------------- FDT parsing
class Node:
    def __init__(self, name, parent):
        self.name, self.parent, self.props, self.children = name, parent, {}, []

    @property
    def path(self):
        if self.parent is None:
            return "/"
        pp = self.parent.path
        return (pp if pp != "/" else "") + "/" + self.name

    def u32(self, prop):
        v = self.props.get(prop)
        return None if v is None else list(struct.unpack(">%dI" % (len(v) // 4), v))

    def str(self, prop):
        v = self.props.get(prop)
        return None if v is None else v.rstrip(b"\0").decode(errors="replace")

    def strs(self, prop):
        v = self.props.get(prop)
        return [] if v is None else [s.decode() for s in v.split(b"\0")[:-1]]

    def child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def enabled(self):
        n = self
        while n is not None:
            st = n.str("status")
            if st is not None and st not in ("okay", "ok"):
                return False
            n = n.parent
        return True


def parse_dtb(data):
    magic, _tot, off_struct, off_strings = struct.unpack(">IIII", data[:16])
    assert magic == 0xD00DFEED, "not a DTB"
    pos, root, cur = off_struct, None, None
    while True:
        tok = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        if tok == 1:
            end = data.index(b"\0", pos)
            name = data[pos:end].decode()
            pos = (end + 4) & ~3
            n = Node(name, cur)
            if cur is None:
                root = n
            else:
                cur.children.append(n)
            cur = n
        elif tok == 2:
            cur = cur.parent
        elif tok == 3:
            ln, nameoff = struct.unpack(">II", data[pos:pos + 8])
            pos += 8
            pname = data[off_strings + nameoff:data.index(b"\0", off_strings + nameoff)].decode()
            cur.props[pname] = data[pos:pos + ln]
            pos = (pos + ln + 3) & ~3
        elif tok == 4:
            continue
        elif tok == 9:
            break
        else:
            raise ValueError("bad FDT token %d" % tok)
    return root


class Tree:
    def __init__(self, root):
        self.root = root
        self.by_phandle = {}
        self.by_path = {}
        for n in root.walk():
            self.by_path[n.path] = n
            ph = n.u32("phandle") or n.u32("linux,phandle")
            if ph:
                self.by_phandle[ph[0]] = n
        aliases = root.child("aliases")
        self.gpio_bank = {}
        for b in range(5):
            p = aliases.str("gpio%d" % b) if aliases else None
            if p and p in self.by_path:
                self.gpio_bank[self.by_path[p].path] = b

    def find(self, path):
        return self.by_path.get(path)


# ----------------------------------------------------------------------------- inputs
def load_pinmap(path):
    rows, by_gpio = [], {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            m = re.search(r"GPIO?(\d)_([A-D])(\d)", r["ds_pin_name"])
            if m:
                key = (int(m.group(1)), "ABCD".index(m.group(2)) * 8 + int(m.group(3)))
                r["_gpio"] = key
                by_gpio[key] = r
    return rows, by_gpio


def gpio_name(key):
    b, off = key
    return "GPIO%d_%s%d" % (b, "ABCD"[off // 8], off % 8)


def pinctrl_source_index(path):
    """group node name -> list of (bank, offset, func, function-comment) from rv1106-pinctrl.dtsi."""
    idx, cur, comment = {}, None, None
    rx_node = re.compile(r"^\s*(?:[\w]+:\s*)?([\w-]+)\s*\{")
    rx_pin = re.compile(r"<\s*(\d)\s+RK_P([A-D])(\d)\s+(\w+)\s+&")
    rx_cmt = re.compile(r"/\*\s*([\w]+)\s*\*/")
    with open(path) as f:
        for line in f:
            m = rx_node.match(line)
            if m:
                cur, comment = m.group(1), None
                continue
            m = rx_cmt.search(line)
            if m and "<" not in line:
                comment = m.group(1)
                continue
            for m in rx_pin.finditer(line):
                key = (int(m.group(1)), "ABCD".index(m.group(2)) * 8 + int(m.group(3)))
                idx.setdefault(cur, []).append((key, m.group(4), comment))
                comment = None
    return idx


def norm_fn(s):
    s = s.lower()
    s = re.sub(r"(cs\d)n", r"\1", s)  # pinctrl comments say cs0n / fspi_cs0n
    return s


# ----------------------------------------------------------------------------- compile
def stage_includes(proj, tmp):
    inc = os.path.join(tmp, "inc")
    shutil.copytree(os.path.join(proj, REL["ref_bind"], "include", "dt-bindings"), os.path.join(inc, "dt-bindings"))
    # In the kernel tree this header is a symlink to include/uapi/linux/input-event-codes.h; the raw
    # GitHub download is the link text, so the real file is put in its place here (staging copy only).
    shutil.copy(os.path.join(proj, REL["ref_bind"], "include", "uapi", "linux", "input-event-codes.h"),
                os.path.join(inc, "dt-bindings", "input", "linux-event-codes.h"))
    return inc


def find_cpp():
    for cand in (["cpp"], ["clang", "-E"], ["gcc", "-E"]):
        exe = shutil.which(cand[0])
        if not exe:
            continue
        if cand == ["cpp"] and sys.platform == "darwin":
            continue  # macOS cpp wrapper rejects "-x assembler-with-cpp file"; use clang -E
        return cand
    return None


def compile_dts(proj, tmp, inc, dts, dts_dir, tag, extra_inc=()):
    cpp = find_cpp()
    pre = os.path.join(tmp, tag + ".pre.dts")
    dtb = os.path.join(tmp, tag + ".dtb")
    incs = [inc, os.path.join(proj, REL["ref_dts"]), os.path.join(proj, REL["ref_bind"], "arch", "arm", "boot", "dts")]
    incs = list(extra_inc) + [dts_dir] + incs
    cmd = cpp + ["-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp"]
    for d in incs:
        cmd += ["-I", d]
    cmd += ["-o", pre, dts]
    r1 = subprocess.run(cmd, capture_output=True, text=True)
    if r1.returncode != 0:
        return None, r1.stderr, []
    r2 = subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-@", "-o", dtb, pre], capture_output=True, text=True)
    warns = [l for l in r2.stderr.splitlines() if "Warning" in l or "ERROR" in l or "Error" in l]
    if r2.returncode != 0:
        return None, r2.stderr, warns
    return dtb, r2.stderr, warns


# ----------------------------------------------------------------------------- the checks
EXPECTED_GPIO = {
    # (consumer node path, property): (pinmap net, required flags)  flags: 0 active-high, 1 active-low
    ("/gpio-keys/power-key", "gpios"): ("PB_INT_N", 1),
    ("/gpio-poweroff", "gpios"): ("PWR_KILL", 0),
    ("/leds/led-status", "gpios"): ("LED_STATUS", 1),
    ("/leds/led-eth", "gpios"): ("LED_ETH", 0),
}

FORBIDDEN_ENABLED = ["i2c0", "i2c2", "i2c4", "uart0", "uart1", "uart4", "uart5", "pwm0", "pwm1", "pwm2", "pwm3",
                     "pwm4", "pwm5", "pwm6", "pwm7", "acodec", "i2s0_8ch", "spi1", "emmc", "sdio"]


def label_node(tree, label):
    sym = tree.root.child("__symbols__")
    p = sym.str(label) if sym else None
    return tree.find(p) if p else None


def run_checks(proj, variant_dtbs, ref_warns, board_warns, pinmap_rows, by_gpio, pidx, sid_prefix=""):
    host = Tree(parse_dtb(open(variant_dtbs["host"], "rb").read()))
    gadget = Tree(parse_dtb(open(variant_dtbs["gadget"], "rb").read()))
    T = host
    P = sid_prefix

    # ---------------- S2 warnings
    own = [w for w in board_warns if "/software/" in w]
    check(not own, P + "S2", "no dtc warnings from software/ files (%d found)%s" % (len(own), (": " + own[0]) if own else ""))
    strip = lambda w: re.sub(r"^.*?:\d+\.\d+-\d+\.\d+:\s*", "", w)
    refset = {strip(w) for w in ref_warns}
    extra = [w for w in board_warns if strip(w) not in refset]
    check(not extra, P + "S2", "every board dtc warning also occurs in the Luckfox Pro/Max reference build (%d board, %d extra)%s"
          % (len(board_warns), len(extra), (": " + extra[0]) if extra else ""))

    # ---------------- S3 pinctrl
    claims = {}  # gpio key -> (consumer path, how)
    s3_ok = True
    for tree, vname in ((host, "host"), (gadget, "gadget")):
        local_claims = {}
        for n in tree.root.walk():
            if not n.enabled():
                continue
            for pname in sorted(n.props):
                if not re.fullmatch(r"pinctrl-\d+", pname):
                    continue
                for ph in n.u32(pname):
                    grp = tree.by_phandle.get(ph)
                    if grp is None:
                        s3_ok = check(False, P + "S3", "%s %s: dangling phandle" % (n.path, pname)) and s3_ok
                        continue
                    cells = grp.u32("rockchip,pins") or []
                    src = pidx.get(grp.name)
                    for i in range(0, len(cells), 4):
                        bank, off, func = cells[i], cells[i + 1], cells[i + 2]
                        key = (bank, off)
                        row = by_gpio.get(key)
                        where = "%s [%s] %s -> %s" % (n.path, vname, grp.name, gpio_name(key))
                        if row is None or not row["status"].startswith("USED"):
                            s3_ok = check(False, P + "S3", "%s: pin not USED in pinmap.csv (%s)" % (where, row["status"] if row else "absent")) and s3_ok
                            continue
                        if func == 0:
                            fn_ok = row["function_used"].upper() == gpio_name(key)
                            want = gpio_name(key)
                        else:
                            cm = None
                            if src:
                                for (k, f, c) in src:
                                    if k == key and int(f) == func:
                                        cm = c
                            want = cm
                            fn_ok = cm is not None and norm_fn(cm) == norm_fn(row["function_used"])
                        if not fn_ok:
                            s3_ok = check(False, P + "S3", "%s: function %s != pinmap %s (pin %s)" % (where, want, row["function_used"], row["pin"])) and s3_ok
                        prev = local_claims.get(key)
                        if prev and prev[0] != n.path:
                            s3_ok = check(False, P + "S3", "%s: pin %s also claimed by %s" % (where, row["pin"], prev[0])) and s3_ok
                        local_claims[key] = (n.path, "pinctrl " + grp.name)
        if vname == "host":
            claims = dict(local_claims)
    check(s3_ok, P + "S3", "pinctrl: %d pins claimed by enabled nodes; each is a USED pinmap row with the same function, none twice (both variants)" % len(claims))

    # ---------------- S4 gpio consumers + hogs
    s4_ok = True
    seen = set()
    for n in T.root.walk():
        if not n.enabled():
            continue
        if "gpio-hog" in n.props:
            bank = T.gpio_bank.get(n.parent.path)
            off, flags = n.u32("gpios")[:2]
            key = (bank, off)
            row = by_gpio.get(key)
            ln = n.str("line-name")
            ok = row is not None and row["status"].startswith("USED") and row["net"] == ln and row["function_used"].upper() == gpio_name(key)
            s4_ok = check(ok, P + "S4", "hog %s -> %s pin %s net %s (line-name %s)" % (n.path, gpio_name(key), row["pin"] if row else "?", row["net"] if row else "?", ln)) and s4_ok
            claims[key] = (n.path, "hog")
            continue
        for pname, val in n.props.items():
            if not (pname in ("gpios", "gpio") or pname.endswith("-gpios") or pname.endswith("-gpio")):
                continue
            if pname == "gpio-line-names":
                continue
            cells = n.u32(pname)
            for i in range(0, len(cells), 3):
                ctrl = T.by_phandle.get(cells[i])
                bank = T.gpio_bank.get(ctrl.path) if ctrl else None
                key = (bank, cells[i + 1])
                flags = cells[i + 2]
                row = by_gpio.get(key)
                exp = EXPECTED_GPIO.get((n.path, pname))
                seen.add((n.path, pname))
                if exp is None:
                    s4_ok = check(False, P + "S4", "unexpected GPIO consumer %s %s -> %s" % (n.path, pname, gpio_name(key))) and s4_ok
                    continue
                ok = (row is not None and row["net"] == exp[0] and row["status"].startswith("USED")
                      and row["function_used"].upper() == gpio_name(key) and (flags & 1) == exp[1])
                s4_ok = check(ok, P + "S4", "%s %s -> %s = pin %s %s, %s" % (n.path, pname, gpio_name(key), row["pin"] if row else "?",
                              row["net"] if row else "?", "active-low" if flags & 1 else "active-high")) and s4_ok
                if key in claims and claims[key][0] != n.path and not n.path.startswith(claims[key][0] + "/"):
                    # pinctrl of the same consumer (e.g. /leds for /leds/led-eth) is fine
                    s4_ok = check(False, P + "S4", "%s also claimed by %s" % (gpio_name(key), claims[key][0])) and s4_ok
                claims.setdefault(key, (n.path, "gpio"))
    missing = set(EXPECTED_GPIO) - seen
    check(not missing, P + "S4", "all expected GPIO consumers present (missing: %s)" % (sorted(missing) or "none"))

    # ---------------- S5 gpio-line-names
    s5_ok = True
    for ctrl_path, bank in T.gpio_bank.items():
        names = T.find(ctrl_path).strs("gpio-line-names")
        for off in range(32):
            row = by_gpio.get((bank, off))
            want = row["net"] if row and row["status"] != "NC" and row["net"] not in ("NC", "GND") else ""
            got = names[off] if off < len(names) else ""
            if got != want:
                s5_ok = check(False, P + "S5", "%s line %d: '%s' != pinmap '%s'" % (ctrl_path, off, got, want)) and s5_ok
    check(s5_ok, P + "S5", "gpio-line-names of gpio0..gpio4 equal pinmap.csv nets (160 lines)")

    # ---------------- S6 coverage
    sfc = label_node(T, "sfc")
    fiq = label_node(T, "fiq_debugger")
    sar = label_node(T, "saradc")
    adck = T.find("/adc-keys")
    bootargs = T.find("/chosen").str("bootargs") or ""
    reasons = {
        "FSPI_": ("sfc enabled with spi-nand child; FSPI mux left to the loader exactly as [SDK] pro-max.dts (no pinctrl on &sfc)",
                  sfc is not None and sfc.enabled() and any(c.str("compatible") == "spi-nand" for c in sfc.children)),
        "UART2_": ("fiq-debugger console (serial-id 2) on UART2_M1, muxed by the loader as on [SDK]",
                   fiq is not None and fiq.enabled() and fiq.u32("rockchip,serial-id") == [2] and "console=ttyFIQ0" in bootargs),
        "RECOVERY": ("SARADC_IN0 read by adc-keys (analog input, no mux)",
                     sar is not None and sar.enabled() and adck is not None and adck.enabled()),
        "HDR_GPIO": ("free header GPIO, named by gpio-line-names, not claimed by any node", True),
        "USB_SEL": ("driven from user space by /usr/sbin/board-usb (D-96); reset pull-down = USB-C", True),
        "USBA_VBUS_EN": ("driven from user space by /usr/sbin/board-usb (D-96); reset pull-down = VBUS off", True),
    }
    s6_ok, n_cov = True, 0
    for r in pinmap_rows:
        if "_gpio" not in r or not r["status"].startswith("USED") or r["dir"] not in ("in", "out", "io"):
            continue
        n_cov += 1
        key = r["_gpio"]
        if key in claims:
            if r["net"].startswith("HDR_GPIO"):
                s6_ok = check(False, P + "S6", "free header GPIO %s (pin %s) is claimed by %s" % (r["net"], r["pin"], claims[key][0])) and s6_ok
            continue
        why = [v for k, v in reasons.items() if r["net"].startswith(k)]
        if not why:
            s6_ok = check(False, P + "S6", "pin %s %s (%s) not claimed by the DTS and no reason" % (r["pin"], r["net"], r["function_used"])) and s6_ok
        elif not why[0][1]:
            s6_ok = check(False, P + "S6", "pin %s %s: reason '%s' does not hold in the DTB" % (r["pin"], r["net"], why[0][0])) and s6_ok
    check(s6_ok, P + "S6", "coverage: all %d USED digital GPIO-bank pins are claimed by the DTS or have a checked reason" % n_cov)

    # ---------------- S7 must-not-inherit
    s7 = []
    for n in T.root.walk():
        comp = " ".join(n.strs("compatible"))
        if "dht11" in comp or "fbtft" in n.name or "st7789" in comp:
            s7.append("node %s (dht11/fbtft)" % n.path)
        if "pa-ctl-gpios" in n.props:
            s7.append("pa-ctl-gpios in %s" % n.path)
        if "io-voltage-domain" in comp or "io-domain" in n.name:
            s7.append("io-domain node %s" % n.path)
        if "restart-poweroff" in comp:
            s7.append("restart-poweroff %s" % n.path)
        if n.enabled():
            for pname in n.props:
                if re.fullmatch(r"pinctrl-\d+", pname):
                    for ph in n.u32(pname):
                        g = T.by_phandle.get(ph)
                        if g is not None and g.name.startswith("pmicm"):
                            s7.append("pmic_sleep group %s used by %s" % (g.name, n.path))
                        if g is not None and g.name in ("i2c3m0-xfer", "pwm10m2-pins", "pwm11m2-pins", "spi0m0-cs1"):
                            s7.append("conflicting group %s used by %s" % (g.name, n.path))
    for lab in FORBIDDEN_ENABLED:
        n = label_node(T, lab)
        if n is not None and n.enabled():
            s7.append("&%s enabled" % lab)
    for lab in ("rkisp", "rkcif", "rkcif_mipi_lvds", "csi2_dphy0", "mipi0_csi2", "csi2_dphy_hw"):
        n = label_node(T, lab)
        if n is not None and n.enabled():
            s7.append("camera node &%s enabled (D-12)" % lab)
    check(not s7, P + "S7", "D-28 / research.md 7.1 list respected; no io-domain, restart-poweroff, pmic_sleep or camera/audio nodes%s"
          % ((": " + "; ".join(s7)) if s7 else ""))

    # ---------------- S8 R4 path (DTS part)
    gk = T.find("/gpio-keys")
    pk = T.find("/gpio-keys/power-key")
    po = T.find("/gpio-poweroff")
    ok = (gk is not None and gk.enabled() and gk.str("compatible") == "gpio-keys" and pk is not None
          and pk.u32("linux,code") == [116])
    check(ok, P + "S8", "gpio-keys power-key: linux,code = KEY_POWER (116) on PB_INT_N (pin 60, GPIO0_A2), active-low")
    pull_ok = False
    if po is not None:
        for ph in po.u32("pinctrl-0") or []:
            g = T.by_phandle.get(ph)
            c = g.u32("rockchip,pins") if g else None
            if c and (c[0], c[1]) == (0, 4) and c[2] == 0:
                pc = T.by_phandle.get(c[3])
                pull_ok = pc is not None and "bias-pull-down" in pc.props
    row = by_gpio.get((0, 4))
    check(po is not None and po.enabled() and po.str("compatible") == "gpio-poweroff" and pull_ok
          and row["reset_pull"] == "pull-down", P + "S8",
          "gpio-poweroff on PWR_KILL (pin 63, GPIO0_A4) active-high, pinctrl GPIO + pull-down = pinmap reset pull (%s)" % row["reset_pull"])

    return host, gadget


def check_r4_files(proj, tmp):
    ov = os.path.join(proj, REL["overlay"])
    h = os.path.join(ov, "etc/acpi/PWRF/00000080")
    txt = open(h).read() if os.path.exists(h) else ""
    check(os.path.exists(h) and os.stat(h).st_mode & stat.S_IXUSR and re.search(r"^exec /sbin/poweroff", txt, re.M),
          "S8", "/etc/acpi/PWRF/00000080 exists, is executable and execs /sbin/poweroff")
    conf = open(os.path.join(ov, "etc/acpid.conf")).read()
    check(re.search(r"^PWRF\s+PWRF/00000080\s*$", conf, re.M), "S8", "/etc/acpid.conf maps PWRF -> PWRF/00000080")
    src = open(os.path.join(proj, REL["ref_busybox"], "acpid-1_36_0.c")).read()
    check('"KEY_POWER", 116, 1, "button/power PWRF 00000080"' in src and 'xchdir(opt_dir)' in src
          and 'const char *opt_dir = "/etc/acpi";' in src,
          "S8", "BusyBox 1.36.0 acpid maps KEY_POWER press to 'button/power PWRF 00000080' and runs it from /etc/acpi (acpid.c L103, L299 xchdir)")
    s50 = open(os.path.join(ov, "etc/init.d/S50powerkey")).read()
    check("busybox acpid -c /etc/acpi -a /etc/acpid.conf" in s50 and "board-powerkeyd" in s50 and " -p " not in s50.split("busybox acpid")[1].split("\n")[0]
          and os.stat(os.path.join(ov, "etc/init.d/S50powerkey")).st_mode & stat.S_IXUSR,
          "S8", "S50powerkey starts busybox acpid (no -p: FEATURE_PIDFILE is off in the Luckfox busybox.config) or the python fallback")
    bb = open(os.path.join(proj, REL["bbfrag"])).read()
    bbref = open(os.path.join(proj, REL["ref_cfg"], "sysdrv/tools/board/buildroot/busybox.config")).read()
    check("CONFIG_ACPID=y" in bb and "# CONFIG_ACPID is not set" in bbref and "CONFIG_RUN_PARTS=y" in bbref,
          "S8", "busybox fragment enables CONFIG_ACPID (off in the Luckfox busybox.config; RUN_PARTS already on)")
    k = open(os.path.join(proj, REL["kcfg"])).read()
    need = ["CONFIG_POWER_RESET_GPIO=y", "CONFIG_KEYBOARD_GPIO=y", "CONFIG_INPUT_EVDEV=y", "CONFIG_POWER_RESET=y",
            "CONFIG_LEDS_TRIGGER_HEARTBEAT=y", "CONFIG_LEDS_TRIGGER_NETDEV=y"]
    miss = [x for x in need if not re.search("^" + re.escape(x) + "$", k, re.M)]
    check(not miss, "S8", "kernel fragment custom-reva.config sets %s%s" % (", ".join(need), (" MISSING " + str(miss)) if miss else ""))
    defc = open(os.path.join(proj, REL["ref_cfg"], "sysdrv/source/kernel/arch/arm/configs/luckfox_rv1106_linux_defconfig")).read()
    akc = open(os.path.join(proj, REL["ref_cfg"], "sysdrv/source/kernel/arch/arm/Kconfig")).read()
    psci_off = "CONFIG_ARM_PSCI=y" not in defc and "CONFIG_ARCH_VIRT=y" not in defc and "CONFIG_XEN=y" not in defc
    check(psci_off and "select ARM_PSCI" in akc, "S8",
          "SDK defconfig does not enable ARM_PSCI (only ARCH_VIRT/XEN select it), so PSCI does not take pm_power_off first "
          "(inference; confirmed at bring-up by S15board)")
    gpo = open(os.path.join(proj, REL["ref_cfg"], "sysdrv/source/kernel/drivers/power/reset/gpio-poweroff.c")).read()
    check("flags = GPIOD_OUT_LOW;" in gpo and "gpiod_direction_output(reset_gpio, 1);" in gpo, "S8",
          "gpio-poweroff (5.10.160) holds PWR_KILL inactive from probe and drives it active in pm_power_off")
    # optional patch applies to the reference source
    w = os.path.join(tmp, "patchtest")
    os.makedirs(os.path.join(w, "drivers/power/reset"))
    shutil.copy(os.path.join(proj, REL["ref_cfg"], "sysdrv/source/kernel/drivers/power/reset/gpio-poweroff.c"),
                os.path.join(w, "drivers/power/reset/gpio-poweroff.c"))
    r = subprocess.run(["patch", "-p1", "--dry-run", "-d", w, "-i", os.path.join(proj, REL["patch"])], capture_output=True, text=True)
    check(r.returncode == 0, "S8", "optional patch 0001 applies cleanly to the SDK gpio-poweroff.c (patch --dry-run)%s"
          % ("" if r.returncode == 0 else ": " + r.stdout + r.stderr))
    # fallback daemon: feed a file of ARM32 input_event records
    ev = os.path.join(tmp, "events.bin")
    with open(ev, "wb") as f:
        for (t, c, v) in ((1, 115, 1), (1, 115, 0), (0, 0, 0), (1, 116, 0), (1, 116, 1)):
            f.write(struct.pack("<iiHHi", 0, 0, t, c, v))
    mark = os.path.join(tmp, "fired")
    d = os.path.join(ov, "usr/sbin/board-powerkeyd")
    r = subprocess.run([sys.executable, "-I", d, "--device", ev, "--once", "--event-format", "arm32",
                        "--action", "echo fired > '%s'" % mark], capture_output=True, text=True, timeout=30)
    check(r.returncode == 0 and os.path.exists(mark), "S8", "board-powerkeyd fallback runs the action on a KEY_POWER press record (and not on KEY_VOLUMEUP/release)")
    ev2 = os.path.join(tmp, "events2.bin")
    with open(ev2, "wb") as f:
        for (t, c, v) in ((1, 115, 1), (1, 116, 0)):
            f.write(struct.pack("<iiHHi", 0, 0, t, c, v))
    mark2 = os.path.join(tmp, "fired2")
    r = subprocess.run([sys.executable, "-I", d, "--device", ev2, "--once", "--event-format", "arm32",
                        "--action", "echo fired > '%s'" % mark2], capture_output=True, text=True, timeout=30)
    check(r.returncode == 1 and not os.path.exists(mark2), "S8", "board-powerkeyd ignores other keys and KEY_POWER release")
    s15 = os.path.join(ov, "etc/init.d/S15board")
    check(os.stat(s15).st_mode & stat.S_IXUSR and "poweroff-gpio" in open(s15).read(), "S8",
          "S15board reports at boot whether gpio-poweroff bound (driver 'poweroff-gpio')")


def check_opp(proj, T):
    rails = {r["rail"]: r for r in csv.DictReader(open(os.path.join(proj, REL["rails"])))}
    r = rails["VDD_0V9"]
    vmin = float(r["vref_min"]) * (1 + float(r["r_top_k"]) / float(r["r_bot_k"]))
    drop = 0.0
    for p in csv.DictReader(open(os.path.join(proj, REL["paths"]))):
        if p["item"].startswith("VDD_0V9"):
            drop = float(p["value"]) / 1000.0
    vsoc = vmin - drop
    opp = label_node(T, "cpu0_opp_table")
    bad, top = [], 0
    for c in opp.children:
        hz = c.props.get("opp-hz")
        if hz is None:
            continue
        f = struct.unpack(">Q", hz)[0]
        uv = c.u32("opp-microvolt")[0]
        top = max(top, f)
        if uv / 1e6 > vsoc + 1e-9 or f > 1_200_000_000:
            bad.append("%d MHz @ %d uV" % (f // 1_000_000, uv))
    cpu = label_node(T, "cpu0")
    sup = T.by_phandle.get(cpu.u32("cpu-supply")[0])
    check(not bad and top == 1_200_000_000 and sup is not None and sup.str("regulator-name") == "vdd_arm", "S9",
          "CPU OPPs: max %d MHz; every target <= VDD_0V9 min at SoC %.4f V (= %.3f x (1 + %s/%s) - %.1f mV)%s"
          % (top // 1_000_000, vsoc, float(r["vref_min"]), r["r_top_k"], r["r_bot_k"], drop * 1000, (" BAD: " + ", ".join(bad)) if bad else ""))


def part_size(tok):
    m = re.match(r"(\d+)([KMG])", tok)
    return int(m.group(1)) * {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[m.group(2)]


def check_storage(proj, T):
    sd = label_node(T, "sdmmc")
    check(sd.enabled() and sd.u32("bus-width") == [4] and "no-1-8-v" in sd.props and "non-removable" not in sd.props
          and "supports-sdio" not in sd.props and sd.u32("max-frequency") == [50000000], "S10",
          "sdmmc: okay, 4-bit, no-1-8-v (VCCIO4 = 3.3 V), removable with SDMMC0_DET, 50 MHz (D-95)")
    sfc = label_node(T, "sfc")
    fl = sfc.child("flash@0")
    check(sfc.enabled() and fl is not None and fl.str("compatible") == "spi-nand" and fl.u32("spi-rx-bus-width") == [4],
          "S10", "sfc: okay, spi-nand quad-read child (copy of [SDK] pro-max.dts L40-49)")
    bdir = os.path.join(proj, REL["bcfg_dir"])
    nand = open(os.path.join(bdir, "BoardConfig-SPI_NAND-Buildroot-RV1106_Custom_RevA-IPC.mk")).read()
    m = re.search(r'^export RK_PARTITION_CMD_IN_ENV="([^"]+)"', nand, re.M)
    total, end = 0, 0
    for part in m.group(1).split(","):
        sz = part_size(part)
        at = re.search(r"@(\d+[KMG])", part)
        start = part_size(at.group(1)) if at else end
        end = start + sz
        total = end
    check(total <= 128 * 1024 ** 2, "S10", "SPI NAND partition table ends at %.2f MiB <= 128 MiB (W25N01KV, D-52)" % (total / 1024 ** 2))
    for f in ("BoardConfig-SPI_NAND-Buildroot-RV1106_Custom_RevA-IPC.mk", "BoardConfig-SD_CARD-Buildroot-RV1106_Custom_RevA-IPC.mk"):
        s = open(os.path.join(bdir, f)).read()
        dts = re.search(r"^export RK_KERNEL_DTS=(\S+)", s, re.M).group(1)
        frag = re.search(r"^export RK_KERNEL_DEFCONFIG_FRAGMENT=(\S+)", s, re.M)
        ov = re.search(r'^export RK_POST_OVERLAY="([^"]+)"', s, re.M).group(1).split()
        check(os.path.exists(os.path.join(proj, REL["dts_dir"], dts)) and frag and frag.group(1) == "custom-reva.config"
              and "overlay-custom-reva" in ov, "S10", "%s: DTS %s exists, fragment custom-reva.config, overlay-custom-reva" % (f, dts))


def check_usb(host, gadget, proj=None, tmp=None):
    def st(T):
        d = label_node(T, "usbdrd_dwc3")
        g0 = label_node(T, "gpio0")
        hogs = {c.str("line-name"): ("output-high" in c.props) for c in g0.children if "gpio-hog" in c.props}
        return d.str("dr_mode"), hogs, d.path, g0.path
    hm, hh, hpath, g0path = st(host)
    gm, gh, _, _ = st(gadget)
    check(hm == "host" and "USB_SEL" not in hh and "USBA_VBUS_EN" not in hh and hh.get("SDMMC_PWREN") is False,
          "S11", "host DTS: dr_mode host; USB_SEL/USBA_VBUS_EN not hogged (board-usb drives them); SDMMC_PWREN hog low (card on)")
    check(gm == "peripheral" and "USB_SEL" not in gh and gh.get("SDMMC_PWREN") is False,
          "S11", "gadget DTS: dr_mode peripheral (as [SDK] pro-max.dts L91-94)")
    if proj is None:
        return
    # board-usb against a fake sysfs/device-tree tree
    script = os.path.join(proj, REL["overlay"], "usr/sbin/board-usb")
    txt = open(script).read()
    unit = g0path.rsplit("@", 1)[1]
    check("GPIO0_DEV=%s.gpio" % unit in txt and "OFF_VBUS=5" in txt and "OFF_SEL=6" in txt
          and by_gpio_global[(0, 5)]["net"] == "USBA_VBUS_EN" and by_gpio_global[(0, 6)]["net"] == "USB_SEL",
          "S11", "board-usb targets gpio0 = %s.gpio, offsets 5 = USBA_VBUS_EN (pin 64), 6 = USB_SEL (pin 65)" % unit)
    results = {}
    for mode, drm in (("auto", "host"), ("auto", "peripheral"), ("off", "host")):
        root = os.path.join(tmp, "fake_%s_%s" % (mode, drm))
        g = os.path.join(root, "sys/class/gpio")
        os.makedirs(os.path.join(g, "gpiochip0"))
        os.makedirs(os.path.join(root, "sys/devices/platform/%s.gpio" % unit))
        os.symlink("../../../devices/platform/%s.gpio" % unit, os.path.join(g, "gpiochip0", "device"))
        open(os.path.join(g, "gpiochip0", "base"), "w").write("0\n")
        os.makedirs(os.path.join(root, "sys/devices/platform/other.gpio"))
        os.makedirs(os.path.join(g, "gpiochip32"))
        os.symlink("../../../devices/platform/other.gpio", os.path.join(g, "gpiochip32", "device"))
        open(os.path.join(g, "gpiochip32", "base"), "w").write("32\n")
        for n in (5, 6):
            os.makedirs(os.path.join(g, "gpio%d" % n))
        open(os.path.join(g, "export"), "w").close()
        dtp = os.path.join(root, "dt", hpath.strip("/"))
        os.makedirs(dtp)
        open(os.path.join(dtp, "dr_mode"), "wb").write(drm.encode() + b"\0")
        env = dict(os.environ, BOARD_SYSFS=os.path.join(root, "sys"), BOARD_DT=os.path.join(root, "dt"))
        r = subprocess.run(["sh", script, mode], env=env, capture_output=True, text=True, timeout=30)
        rd = lambda n: open(os.path.join(g, "gpio%d" % n, "direction")).read().strip() if os.path.exists(os.path.join(g, "gpio%d" % n, "direction")) else None
        results[(mode, drm)] = (r.returncode, rd(6), rd(5))
    ok = (results[("auto", "host")] == (0, "high", "high") and results[("auto", "peripheral")] == (0, "low", "low")
          and results[("off", "host")] == (0, "low", "low"))
    check(ok, "S11", "board-usb on a fake sysfs: auto+host -> SEL high, VBUS high; auto+peripheral and off -> both low (%s)" % results)


def check_console(T, by_gpio, pidx):
    fiq = label_node(T, "fiq_debugger")
    ba = T.find("/chosen").str("bootargs")
    grp = pidx.get("uart2m1-xfer", [])
    pins = {c: k for (k, f, c) in grp}
    tx, rx = pins.get("uart2_tx_m1"), pins.get("uart2_rx_m1")
    ok = (fiq.enabled() and fiq.u32("rockchip,serial-id") == [2] and fiq.u32("rockchip,baudrate") == [115200]
          and "console=ttyFIQ0" in ba and tx and rx and by_gpio[tx]["net"] == "UART2_TX" and by_gpio[rx]["net"] == "UART2_RX")
    check(ok, "S12", "console: fiq-debugger serial-id 2 @ 115200, console=ttyFIQ0; uart2m1 TX %s = pin %s, RX %s = pin %s"
          % (gpio_name(tx) if tx else "?", by_gpio[tx]["pin"] if tx else "?", gpio_name(rx) if rx else "?", by_gpio[rx]["pin"] if rx else "?"))


def full_run(proj, tmp, board_dtsi_override=None, quiet=False, prefix=""):
    inc = stage_includes(proj, tmp) if not os.path.exists(os.path.join(tmp, "inc")) else os.path.join(tmp, "inc")
    dts_dir = os.path.join(proj, REL["dts_dir"])
    extra = []
    if board_dtsi_override:
        od = os.path.join(tmp, "override")
        os.makedirs(od, exist_ok=True)
        shutil.copy(board_dtsi_override, os.path.join(od, "rv1106-custom-reva.dtsi"))
        # quoted #include looks in the including file's directory first, so the .dts files move too
        for k in ("dts_host", "dts_gadget"):
            shutil.copy(os.path.join(proj, REL[k]), od)
        extra = [od]
    global by_gpio_global
    pinmap_rows, by_gpio = load_pinmap(os.path.join(proj, REL["pinmap"]))
    by_gpio_global = by_gpio
    pidx = pinctrl_source_index(os.path.join(proj, REL["ref_dts"], "rv1106-pinctrl.dtsi"))
    dtbs, warns = {}, []
    for v, key in (("host", "dts_host"), ("gadget", "dts_gadget")):
        src = os.path.join(extra[0], os.path.basename(REL[key])) if extra else os.path.join(proj, REL[key])
        dtb, err, w = compile_dts(proj, tmp, inc, src, dts_dir, prefix + v, extra)
        check(dtb is not None, prefix + "S1", "%s DTS compiles (cpp + dtc)%s" % (v, "" if dtb else ": " + err.strip()[:300]))
        if dtb is None:
            return None
        dtbs[v] = dtb
        if v == "host":
            warns = w
    ref_dtb, err, ref_w = compile_dts(proj, tmp, inc, os.path.join(proj, REL["ref_dts"], "rv1106g-luckfox-pico-pro-max.dts"),
                                      os.path.join(proj, REL["ref_dts"]), prefix + "ref")
    check(ref_dtb is not None, prefix + "S1", "reference Luckfox Pro/Max DTS compiles with the same toolchain (baseline)")
    host, gadget = run_checks(proj, dtbs, ref_w, warns, pinmap_rows, by_gpio, pidx, prefix)
    return host, gadget, dtbs, by_gpio, pidx


MUTATIONS = [
    ("pwm10 on the m2 group (UART3_RX pin)", "pinctrl-0 = <&pwm10m1_pins>;", "pinctrl-0 = <&pwm10m1_pins &pwm10m2_pins>;"),
    ("power key on GPIO0_A1", "gpios = <&gpio0 RK_PA2 GPIO_ACTIVE_LOW>;", "gpios = <&gpio0 RK_PA1 GPIO_ACTIVE_LOW>;"),
    ("poweroff active-low", "gpios = <&gpio0 RK_PA4 GPIO_ACTIVE_HIGH>;", "gpios = <&gpio0 RK_PA4 GPIO_ACTIVE_LOW>;"),
    ("i2c3 with the Luckfox m0 group", "pinctrl-0 = <&i2c3m1_xfer>;", "pinctrl-0 = <&i2c3m1_xfer &i2c3m0_xfer>;"),
    ("1416 MHz OPP kept", "\t/delete-node/ opp-1416000000;\n", ""),
    ("spi0 with cs1", "pinctrl-0 = <&spi0m0_pins &spi0m0_cs0>;", "pinctrl-0 = <&spi0m0_pins &spi0m0_cs0 &spi0m0_cs1>;"),
    ("restart-poweroff kept", "\t/delete-node/ restart-poweroff;\n", ""),
    ("wrong line name", '"HDR_GPIO2_A6", "HDR_GPIO2_A7"', '"HDR_GPIO2_A7", "HDR_GPIO2_A6"'),
    ("sdmmc non-removable", "\tdisable-wp;\n", "\tdisable-wp;\n\tnon-removable;\n"),
    ("uart0 enabled", "&uart3 {", "&uart0 {\n\tstatus = \"okay\";\n};\n\n&uart3 {"),
    ("LED_STATUS via pmic_sleep_m1", "<0 RK_PA3 RK_FUNC_GPIO &pcfg_pull_none>", "<0 RK_PA3 1 &pcfg_pull_none>"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    ap.add_argument("--mutations", action="store_true")
    ap.add_argument("--out", help="also write the compiled DTBs and decompiled DTS here")
    a = ap.parse_args()
    proj = os.path.abspath(a.project)
    if not shutil.which("dtc"):
        print("FAIL S1 dtc not found (install device-tree-compiler)")
        return 1
    tmp = tempfile.mkdtemp(prefix="check_software_")
    try:
        res = full_run(proj, tmp)
        if res:
            host, gadget, dtbs, by_gpio, pidx = res
            check_r4_files(proj, tmp)
            check_opp(proj, host)
            check_storage(proj, host)
            check_usb(host, gadget, proj, tmp)
            check_console(host, by_gpio, pidx)
            if a.out:
                os.makedirs(a.out, exist_ok=True)
                for v, p in dtbs.items():
                    name = os.path.basename(REL["dts_" + v]).replace(".dts", "")
                    shutil.copy(p, os.path.join(a.out, name + ".dtb"))
                    with open(os.path.join(a.out, name + ".decompiled.dts"), "w") as f:
                        subprocess.run(["dtc", "-I", "dtb", "-O", "dts", p], stdout=f, stderr=subprocess.DEVNULL)
        base = list(RESULTS)
        if a.mutations:
            src = open(os.path.join(proj, REL["board_dtsi"])).read()
            for i, (desc, old, new) in enumerate(MUTATIONS):
                if old not in src:
                    RESULTS.append((False, "M", "mutation '%s': anchor text not found" % desc))
                    continue
                mt = os.path.join(tmp, "mut%d" % i)
                os.makedirs(mt)
                shutil.copytree(os.path.join(tmp, "inc"), os.path.join(mt, "inc"))
                mf = os.path.join(mt, "mut.dtsi")
                open(mf, "w").write(src.replace(old, new, 1))
                before = len(RESULTS)
                r = full_run(proj, mt, board_dtsi_override=mf, prefix="m%d:" % i)
                if r:
                    check_opp(proj, r[0])
                    check_storage(proj, r[0])
                    check_usb(r[0], r[1])
                fails = [x for x in RESULTS[before:] if not x[0]]
                del RESULTS[before:]
                RESULTS.append((bool(fails), "M", "mutation '%s' is caught (%d failing checks%s)" % (desc, len(fails), (", e.g. " + fails[0][2][:90]) if fails else "")))
        npass = sum(1 for r in RESULTS if r[0])
        nfail = len(RESULTS) - npass
        for ok, sid, msg in RESULTS:
            print("%s %-4s %s" % ("PASS" if ok else "FAIL", sid, msg))
        print("\ncheck_software: %d pass, %d fail" % (npass, nfail))
        return 0 if nfail == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
