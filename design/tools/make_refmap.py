#!/usr/bin/env python3
"""Phase 4 round 3 (D-63): one name set for Phase 5/7. Writes design/refmap.csv mapping the functional names used in
power.md / decisions.md (Q_PWR, U_USBA, C_USBA_IN, ...) and the Luckfox Pico Pro/Max [LF] designators to the bom.csv refs.

The BOM refs are recomputed exactly as make_bom.py assigns them (same part list P, same per-prefix counters), and each
entry below names the make_bom row by a substring of its role text plus the position inside that row, so a reordered
or edited part list makes this script fail (assert) instead of silently mapping a wrong part.
Column lf_name_collision (D-65) flags [LF] designators that are also the bom.csv ref of a different part.
Usage: .venv/bin/python -I tools/make_refmap.py <design_dir> [--check]   (--check: compare with refmap.csv, write nothing; -h: help)
"""
import csv, io, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_bom import P  # noqa: E402

# (functional name, [LF] designator or "", role substring of the make_bom row, index inside that row, note)
FUNC = [
    ("J_USBC", "", "USB-C receptacle", 0, "USB-C sink connector"),
    ("R_CC1", "R3", "CC1/CC2 Rd", 0, "CC1 Rd 5.1k"),
    ("R_CC2", "R6", "CC1/CC2 Rd", 1, "CC2 Rd 5.1k"),
    ("R_DET_TOP", "R2", "USB_DET_IN divider top", 0, "USB_DET divider top 10k"),
    ("R_DET_BOT", "R5", "USB_DET_IN divider bottom", 0, "USB_DET divider bottom 18k"),
    ("F1", "", "PPTC hold", 0, "PPTC BSMD1812-300 (D-56)"),
    ("D_TVS", "", "TVS 5.0 V", 0, "SMAJ5.0A"),
    ("U_ESD_C", "", "USB D+/D- ESD array", 0, "USBLC6 on USB-C D+/D-"),
    ("U_ESD_A", "", "USB D+/D- ESD array", 1, "USBLC6 on USB-A D+/D-"),
    ("C_VBUS", "C4", "VBUS_5V bulk 2.2 uF", 0, "VBUS_5V 2.2 uF"),
    ("C_ONOFF_VIN", "", "LTC2954 VIN decoupling", 0, "LTC2954 VIN 100 nF"),
    ("U_ONOFF", "", "push-button on/off controller", 0, "LTC2954CTS8-1 (D-51)"),
    ("Q_PWR", "", "Q_PWR high-side P-FET", 0, "AO3401A"),
    ("Q_EN", "", "Q_EN inverter", 0, "2N7002 (D-51)"),
    ("Q_KILL", "", "Q_KILL logic-level", 0, "AO3400A"),
    ("R_GS", "", "R_GS 100k, R_KU", 0, "Q_PWR gate-source 100k"),
    ("R_KU", "", "R_GS 100k, R_KU", 1, "KILL pull-up 100k to VCC_3V3"),
    ("R_KILLPD", "", "R_GS 100k, R_KU", 2, "PWR_KILL pull-down 100k"),
    ("R_ENPU", "", "R_GS 100k, R_KU", 3, "LTC2954-1 EN pull-up 100k to VBUS_5V"),
    ("R_G", "", "R_G 47k", 0, "Q_PWR gate series 47k"),
    ("R_INTPU", "", "PB_INT_N pull-up", 0, "PB_INT_N 4.7k"),
    ("R_PB", "", "PB series link", 0, "PB link 0R"),
    ("C_GS", "", "C_GS 470 nF", 0, "470 nF"),
    ("C_GD", "", "C_GD 10 nF", 0, "10 nF"),
    ("C_PDT", "", "C_PDT 2.2 uF", 0, "2.2 uF (D-117 c)"),
    ("R_BL5", "", "R_BL5 470R", 0, "VCC5V0_SYS bleeder"),
    ("SW_PWR", "", "POWER push button", 0, "POWER button"),
    ("U4", "U4", "buck U4 VDD_0V9", 0, "VDD_0V9 buck"),
    ("U5", "U5", "buck U4 VDD_0V9", 1, "VCC_1V8 buck"),
    ("U6", "U6", "buck U4 VDD_0V9", 2, "VCC_3V3 buck"),
    ("U7", "U7", "buck U4 VDD_0V9", 3, "VCC_DDR buck"),
    ("C_USBA_IN", "", "SY6280 VIN 10 uF", 0, "SY6280 VIN 10 uF, <= 2 mm from U_USBA pin 5 (D-57)"),
    ("C77", "C77", "buck input 100 nF x4", 8, "U5+U7 shared EN RC 100 nF"),
    ("C69", "C69", "buck input 100 nF x4", 9, "SD switch 100 nF"),
    ("C70", "C70", "buck input 100 nF x4", 10, "VCC3V3_SD 100 nF"),
    ("C72", "C72", "buck input 100 nF x4", 11, "VCC3V3_SD 100 nF"),
    ("C71", "C71", "U6 output 10 uF; VCC3V3_SD", 1, "VCC3V3_SD 10 uF"),
    ("R14", "R14", "FB top U5 200k", 1, "U5+U7 EN RC 200k"),
    ("R43", "R43", "FB top U5 200k", 2, "U6 EN RC 200k"),
    ("R35", "R35", "R35 10k U4 EN", 0, "U4 EN pull-up 10k"),
    ("R41", "R41", "R41 1k (from VCC_1V8)", 0, "PWR_EN feed 1k from VCC_1V8 (D-34)"),
    ("R_BL09", "", "R41 1k (from VCC_1V8)", 1, "VDD_0V9 bleeder"),
    ("R_BL135", "", "R41 1k (from VCC_1V8)", 2, "VCC_DDR bleeder"),
    ("R_BL18", "", "bleeders R_BL18 680R", 0, "VCC_1V8 bleeder"),
    ("R_BL33", "", "bleeders R_BL18 680R", 1, "VCC_3V3 bleeder"),
    ("C65", "C65", "C65 150 nF", 0, "U6 EN RC 150 nF (D-34)"),
    ("R_MEAS_1V8", "", "0R current-measurement links", 0, "VCC_1V8 measurement 0R at U5 output (D-32, D-68)"),
    ("R_MEAS_3V3", "", "0R current-measurement links", 1, "VCC_3V3 measurement 0R at U6 output (D-32, D-68)"),
    ("R_MEAS_DDR", "", "0R current-measurement links", 2, "VCC_DDR measurement 0R at U7 output (D-32, D-68)"),
    ("R31", "R31", "R31 (MIPI/VCCIO7", 0, "1R series"),
    ("R8", "R8", "R31 (MIPI/VCCIO7", 1, "1R series AVDD1V8_USB"),
    ("FB1", "FB1", "FB1 FEPHY 3V3", 0, "ferrite FEPHY 3V3"),
    ("FB2", "FB2", "FB1 FEPHY 3V3", 1, "ferrite CODEC 1V8"),
    ("FB3", "FB3", "FB1 FEPHY 3V3", 2, "ferrite ETH 1V8"),
    ("D_RTC", "D2", "RTC diode-OR", 0, "RTC diode from VCC_3V3"),
    ("R11", "R11", "RTC series R11 100R", 0, "RTC series 100R"),
    ("R22", "R22", "RTC series R11 100R", 1, "nPOR Key1 series 100R"),
    ("R_RECOV", "", "RTC series R11 100R", 2, "RECOVERY 100R"),
    ("U_USBA", "", "USB-A VBUS current-limited switch", 0, "SY6280AAC"),
    ("R_SET", "", "SY6280 RSET 6.8k", 0, "SY6280 ILIM set"),
    ("C_USBA_OUT", "", "VBUS_USBA output 22 uF", 0, "22 uF at U_USBA OUT"),
    ("C_USBA_BULK", "", "VBUS_USBA bulk 120 uF", 0, "120 uF polymer at USB-A (D-58)"),
    ("Q_SD", "Q1", "Q_SD card-power P-FET", 0, "SI2301CDS"),
    ("R55", "R55", "Q_SD R55 10k", 0, "Q_SD gate pull-up"),
    ("R51", "R51", "Q_SD R51 100k", 0, "Q_SD gate"),
    ("U_SOC", "", "=SoC", 0, "RV1106G3"),
    ("R1", "R1", "[LF] R1 240R", 0, "240R"),
    ("R7", "R7", "ETH_EXTR 6.04k", 0, "ETH_EXTR"),
    ("R12", "R12", "nPOR pull-up R12 1k", 0, "nPOR pull-up"),
    ("C38", "C38", "nPOR C38 100 nF", 0, "nPOR 100 nF (D-117 c)"),
    ("Y1", "Y1", "24 MHz crystal", 0, "24 MHz"),
    ("Y2", "Y2", "32.768 kHz crystal", 0, "32.768 kHz"),
    ("U_NAND", "U2", "SPI NAND 1 Gbit", 0, "W25N01KVZEIR"),
    ("C42", "C42", "NAND 10 uF", 0, "NAND 10 uF"),
    ("C43", "C43", "NAND 100 nF", 0, "NAND 100 nF"),
    ("R18", "R18", "WP#/HOLD# pull-ups", 0, "FSPI_D3 (HOLD#) pull-up, per pinmap.csv pin 39"),
    ("R19", "R19", "WP#/HOLD# pull-ups", 1, "FSPI_D2 (WP#) pull-up, per pinmap.csv pin 44"),
    ("R_CSPU", "", "WP#/HOLD# pull-ups", 2, "CS# pull-up (D-25)"),
    ("R_NANDDIS", "", "NAND-disable link", 0, "FSPI_CS0N 0R link (D-25)"),
    ("J_SD", "TF1", "microSD push-push socket", 0, "TF-01A"),
    ("J_RJ45", "J2", "RJ45 with magnetics", 0, "HR911105A"),
    ("U_MUX", "", "USB 2.0 2:1 mux", 0, "TS3USB221A"),
    ("R_USBSEL", "", "USB_SEL 10k pull-down", 0, "USB_SEL pull-down"),
    ("R_USBAEN", "", "USB_SEL 10k pull-down", 1, "USBA_VBUS_EN pull-down"),
    ("J_USBA", "", "USB-A receptacle", 0, "AF 90 WJDG"),
    ("J_HDR", "", "2x20 2.54 mm header", 0, "2x20 header"),
    ("J_UART", "", "3-pin debug UART header", 0, "debug UART"),
    ("SW_RESET", "Key1", "RESET (Key1)", 0, "RESET button"),
    ("SW_RECOV", "Key2", "RESET (Key1)", 1, "MASKROM/RECOVERY button"),
    ("LED_PWR", "", "power LED red", 0, "red"),
    ("LED_STAT", "", "status LED (pin 62", 0, "red (D-64)"),
    ("LED_ETH", "", "status LED (pin 62", 1, "red (D-64)"),
]

# Phase 5 (D-72/D-73): every remaining BOM ref gets a functional name, so the SKiDL schematic (design/schematic/) can
# address every part by name and refmap.csv covers the whole BOM (verifier P4 D-H2 round-2 minor).
_BUCK = ["U4", "U5", "U6", "U7"]
_LF_L = {"U4": "L2", "U5": "L1", "U6": "L3", "U7": "L4"}
for _i, _u in enumerate(_BUCK):
    FUNC.append((f"C_IN_{_u}", "", "buck input 10 uF 25 V x4", _i, f"{_u} VIN 10 uF"))
    FUNC.append((f"C_IN100_{_u}", "", "buck input 100 nF x4", _i, f"{_u} VIN 100 nF"))
    FUNC.append((f"C_OUT100_{_u}", "", "buck input 100 nF x4", 4 + _i, f"{_u} output 100 nF"))
    FUNC.append((f"C_FF_{_u}", "", "feed-forward 6.8 pF", _i, f"{_u} feed-forward 6.8 pF across FB top"))
    FUNC.append((f"R_FBB_{_u}", "", "FB bottom 100k x4", _i, f"{_u} FB bottom 100k"))
    FUNC.append((f"L_{_u}", _LF_L[_u], "buck inductors", _i, f"{_u} 2.2 uH"))
FUNC += [
    ("C_OUT_U4", "", "U4 output 22 uF", 0, "U4 output 22 uF (local, D-47, D-117 c)"),
    ("C_OUT_U6", "", "U6 output 10 uF; VCC3V3_SD", 0, "U6 output 10 uF ([LF] C63)"),
    ("C_OUT_U5", "", "U5 and U7 output 22 uF", 0, "U5 output 22 uF"),
    ("C_OUT_U7", "", "U5 and U7 output 22 uF", 1, "U7 output 22 uF"),
    ("R_FBT_U4", "R33", "FB top U4 49.9k", 0, "U4 FB top 49.9k (D-35; [LF] R33 47k)"),
    ("R_FBT_U7", "R13", "FB top U7 127k", 0, "U7 FB top 127k"),
    ("R_FBT_U5", "R34", "FB top U5 200k", 0, "U5 FB top 200k"),
    ("R_FBT_U6", "R40", "FB top U6 442k", 0, "U6 FB top 442k (D-43)"),
    ("C_USBDET", "C7", "USB_DET_IN filter 100 nF", 0, "USB_DET_IN 100 nF (D-72)"),
    ("R_SD_BL", "R52", "VCC3V3_SD bleeder 10k", 0, "VCC3V3_SD bleeder 10k (D-72)"),
    ("R_PD58", "", "pin 58 GPIO0_A0 100k", 0, "GPIO0_A0 pull-down (D-26)"),
    ("R_RECOV_PU", "R21", "RECOVERY 10k to 1V8", 0, "RECOVERY 10k to VCC_1V8"),
    ("R_ADC1_PU", "R57", "RECOVERY 10k to 1V8", 1, "SARADC_IN1 10k to VCC_1V8"),
    ("C_RECOV", "C44", "RECOVERY 1 nF", 0, "RECOVERY 1 nF"),
    ("C_ADC1", "C73", "RECOVERY 1 nF", 1, "SARADC_IN1 1 nF"),
    ("R_FSPI_CLK", "R15", "FSPI_CLK series 22R", 0, "FSPI_CLK 22R"),
    ("R_SD_CLK", "R16", "FSPI_CLK series 22R", 1, "SDMMC_CLK 22R"),
    ("R_SD_DET", "R54", "SDMMC_DET series 100R", 0, "SDMMC_DET 100R"),
    ("DEC_0V9_P71_100N", "", "pin 71 OSC_PLL_DVDD decoupling", 0, "SoC decoupling, new (D-72)"),
    ("DEC_RTC_1U", "C35", "RTC_AVDD3V3 pin 19 decoupling", 0, "SoC decoupling, [LF] C35 (D-72)"),
    ("C_Y1_XOUT", "C29", "crystal load 18 pF x4", 0, "Y1 X2/XOUT side 18 pF"),
    ("C_Y1_XIN", "C30", "crystal load 18 pF x4", 1, "Y1 X1/XIN side 18 pF"),
    ("C_Y2_XOUT", "C33", "crystal load 18 pF x4", 2, "Y2 RTC_XOUT 18 pF"),
    ("C_Y2_XIN", "C34", "crystal load 18 pF x4", 3, "Y2 RTC_XIN 18 pF"),
    ("R_Y1_SER", "R9", "Y1 series 22R", 0, "Y1 series 22R"),
    ("R_Y1_FB", "R10", "Y1 feedback 1M", 0, "Y1 feedback 1M"),
    ("R_ETH_TXP", "R46", "ETH 0R series links", 0, "ETH TX+ 0R"),
    ("R_ETH_TXN", "R47", "ETH 0R series links", 1, "ETH TX- 0R"),
    ("R_ETH_RXP", "R48", "ETH 0R series links", 2, "ETH RX+ 0R"),
    ("R_ETH_RXN", "R49", "ETH 0R series links", 3, "ETH RX- 0R"),
    ("C_CT_TX", "C66", "magnetics centre-tap 10 nF", 0, "TX centre tap 10 nF"),
    ("C_CT_RX", "C67", "magnetics centre-tap 10 nF", 1, "RX centre tap 10 nF"),
    ("C_MUX", "", "mux VCC 100 nF", 0, "TS3USB221A VCC 100 nF"),
    ("R_I2C3_SCL", "", "I2C3_M1 pull-ups 2.2k", 0, "I2C3 SCL 2.2k"),
    ("R_I2C3_SDA", "", "I2C3_M1 pull-ups 2.2k", 1, "I2C3 SDA 2.2k"),
    ("R_I2C1_SDA", "", "I2C1_M1 pull-ups 4.7k", 0, "I2C1 SDA 4.7k"),
    ("R_I2C1_SCL", "", "I2C1_M1 pull-ups 4.7k", 1, "I2C1 SCL 4.7k"),
    ("R_UART_TX", "", "UART2 TX/RX 1k series", 0, "UART2 TX 1k"),
    ("R_UART_RX", "", "UART2 TX/RX 1k series", 1, "UART2 RX 1k"),
    ("R_LED_PWR", "", "LED series 1k x3", 0, "power LED 1k"),
    ("R_LED_STAT", "", "LED series 1k x3", 1, "status LED 1k"),
    ("R_LED_ETH", "", "LED series 1k x3", 2, "ETH LED 1k"),
]

# D-65: every [LF] SoC-side decoupler cited in power.md §0 / power_rails.csv c_soc_refs (D-47) gets a BOM ref too.
# The index order inside each make_bom row is defined by that row's role text ("in [LF] order: ...").
_DEC = [
    ("SoC decoupling 10 uF", [("DEC_0V9_10U_1", "C22"), ("DEC_0V9_10U_2", "C23"), ("DEC_ARM_10U", "C15"),
                              ("DEC_DDR_10U_1", "C18"), ("DEC_DDR_10U_2", "C19"), ("DEC_CODEC_10U", "C13")]),
    ("SoC decoupling 1 uF", [("DEC_0V9_1U_1", "C24"), ("DEC_0V9_1U_2", "C25"), ("DEC_ARM_1U", "C16"),
                             ("DEC_DDR_1U", "C20"), ("DEC_DDR_FB4_1U", "C48"), ("DEC_1V8_P53_1U", "C11")]),
    ("SoC decoupling 100 nF", [("DEC_0V9_100N_1", "C26"), ("DEC_0V9_100N_2", "C27"), ("DEC_0V9_100N_3", "C28"),
                               ("DEC_0V9_P67_100N", "C36"), ("DEC_ARM_100N", "C17"), ("DEC_DDR_100N", "C21"),
                               ("DEC_1V8_P53_100N", "C12"), ("DEC_1V8_P70_100N", "C32"), ("DEC_1V8_P96_100N", "C31"),
                               ("DEC_CODEC_100N", "C14"), ("DEC_1V8_P24_100N", "C10"), ("DEC_1V8_P1_100N", "C45"),
                               ("DEC_1V8_FB4_100N", "C47"), ("DEC_3V3_P61_100N", "C37"), ("DEC_3V3_P81_100N", "C39"),
                               ("DEC_3V3_P43_100N", "C40"), ("DEC_3V3_P13_100N", "C41"), ("DEC_3V3_P28_100N", "C9"),
                               ("DEC_3V3_P101_100N", "C8"), ("DEC_3V3_P88_100N", ""), ("DEC_3V3_P108_100N", "")]),
    ("C46 4.7 uF (1V8 FB4 block)", [("DEC_1V8_FB4_4U7", "C46"), ("C_CODEC_VCM", "C3")]),
]
for _sub, _items in _DEC:
    for _i, (_n, _lf) in enumerate(_items):
        FUNC.append((_n, _lf, _sub, _i, f"SoC decoupling, [LF] {_lf}" if _lf else "SoC decoupling, new (no [LF] ref)"))


# D-68: functions that are PCB copper, not BOM parts. They are listed so Phase 5/7 find them by name; bom_ref stays empty.
NOPART = [
    ("JP_MEAS_0V9", "", "pmu", "VDD_0V9 measurement: normally-closed solder jumper at U4 output (copper bridge, cut to "
     "measure, re-bridge with solder); U4 feedback divider top taps the U4 side (D-68)"),
    ("NT_ARM", "R32", "pmu", "VDD_0V9 -> VDD_ARM direct copper / KiCad net-tie replacing [LF] R32 '0R 5% DNP' (D-06, D-68)"),
]


def rows_refs():
    c, out = {}, []
    for p in P:
        refs = []
        for _ in range(p["qty"]):
            c[p["pre"]] = c.get(p["pre"], 0) + 1
            refs.append(f"{p['pre']}{c[p['pre']]}")
        out.append((p, refs))
    return out


def build():
    rr = rows_refs()
    lines = []
    for name, lf, sub, idx, note in FUNC:
        hits = [(p, refs) for p, refs in rr if (p["role"] == sub[1:] if sub.startswith("=") else sub in p["role"])]
        assert len(hits) == 1, f"{name}: role substring '{sub}' matches {len(hits)} rows"
        p, refs = hits[0]
        assert idx < len(refs), f"{name}: index {idx} outside row {refs}"
        lines.append(dict(functional_name=name, luckfox_ref=lf, bom_ref=refs[idx], block=p["block"], lcsc=p["lcsc"],
                          value=p["value"], note=note, lf_name_collision=""))
    for name, lf, block, note in NOPART:
        lines.append(dict(functional_name=name, luckfox_ref=lf, bom_ref="", block=block, lcsc="",
                          value="no part (PCB copper)", note=note, lf_name_collision=""))
    # D-65: flag every [LF] designator that is ALSO a bom.csv ref of a DIFFERENT part (e.g. [LF] J2 = RJ45 but
    # bom J2 = microSD). Phase 5/7 must then always write "[LF] J2" / "J_RJ45 [J3]", never a bare "J2".
    allrefs = {}
    for p, refs in rr:
        for r in refs:
            allrefs[r] = p
    byref = {l["bom_ref"]: l["functional_name"] for l in lines}
    for l in lines:
        lf = l["luckfox_ref"]
        if lf and lf != l["bom_ref"] and lf in allrefs:
            q = allrefs[lf]
            l["lf_name_collision"] = (f"COLLIDES: bom {lf} is {byref.get(lf, '(unnamed)')} {q['value']}; "
                                      + (f"this part is bom {l['bom_ref']}" if l["bom_ref"] else "this function has no BOM part"))
    seen = {}
    for l in lines:
        if not l["bom_ref"]:
            continue
        assert l["bom_ref"] not in seen, f"{l['bom_ref']} mapped twice ({seen.get(l['bom_ref'])}, {l['functional_name']})"
        seen[l["bom_ref"]] = l["functional_name"]
    # Phase 5 (D-73): every BOM ref has exactly one functional name
    missing = sorted(set(allrefs) - set(seen))
    assert not missing, f"BOM refs without a functional name: {missing}"
    return lines


def render(lines):
    s = io.StringIO()
    w = csv.DictWriter(s, fieldnames=list(lines[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(lines)
    return s.getvalue()


if __name__ == "__main__":
    import argparse
    from designdir import design_dir
    ap = argparse.ArgumentParser(description="Write (or --check) design/refmap.csv from make_bom.py's part list. Offline.")
    ap.add_argument("design", type=design_dir, help="the project design/ directory (must exist; never created)")
    ap.add_argument("--check", action="store_true", help="compare with refmap.csv, write nothing")
    a = ap.parse_args()
    path = os.path.join(a.design, "refmap.csv")
    text = render(build())
    if a.check:
        ok = os.path.exists(path) and open(path, encoding="utf-8").read() == text
        print("refmap.csv up to date" if ok else "refmap.csv STALE")
        sys.exit(0 if ok else 1)
    open(path, "w", encoding="utf-8").write(text)
    print(f"wrote {path}: {text.count(chr(10)) - 1} names")
