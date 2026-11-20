#!/usr/bin/env python3
"""Phase 4: build design/bom.csv from the part list below + live LCSC/JLCPCB data.

Usage: .venv/bin/python -I tools/make_bom.py <design_dir> [--refresh] [--boards N --out PATH]   (-h: help; D-70)
Offline by default: it reads the cached raw records; only --refresh fetches live.
(bom.csv is costed for the Rev A order of D-H2: 2 ASSEMBLED boards (+ 3 bare PCBs, which need no parts).
Other scenarios: tools/check_bom.py --boards N recomputes line costs itself, or make_bom.py --boards N --out <scratch
copy> - never overwrite design/bom.csv with a costing other than the D-H2 order.)

Each PART line = one function on the board (block, role, qty per board, LCSC code, footprint ...).
Lines sharing an LCSC code are merged into one BOM row (refs concatenated). Reference designators
are PROVISIONAL (Phase 5 SKiDL renumbers); the qty and LCSC code are what Phase 4 fixes.
Live data comes from tools/lcsc_fetch.py (raw responses cached under refs/lcsc-api-2026-10-29 and
refs/jlcpcb-partdetail-2026-10-29). Nothing fetched is executed; only JSON/HTML text is parsed.
"""
import argparse, csv, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lcsc_fetch  # noqa: E402

# footprint key -> (exact KiCad footprint name, package token expected in LCSC 'encapStandard',
#                   SMT pads, THT pads, pad-count source)
# Pad counts are PHYSICAL copper pads (one joint each): stacked pad entries at the same position (e.g. USB-C A1/B12)
# count once. "kicad" = check_bom.py B3c re-counts them from the cached KiCad library file
# refs/kicad-footprints-mods-2026-10-29/<lib>__<name>.kicad_mod (gitlab.com/kicad/libraries/kicad-footprints, master,
# fetched 2026-10-29). "board:" footprints are custom (Phase 5 draws them); their count is taken from the cited drawing.
FP = {
    "R0402": ("Resistor_SMD:R_0402_1005Metric", "0402", 2, 0, "kicad"),
    "C0402": ("Capacitor_SMD:C_0402_1005Metric", "0402", 2, 0, "kicad"),
    "R0603": ("Resistor_SMD:R_0603_1608Metric", "0603", 2, 0, "kicad"),
    "C0603": ("Capacitor_SMD:C_0603_1608Metric", "0603", 2, 0, "kicad"),
    "R0805": ("Resistor_SMD:R_0805_2012Metric", "0805", 2, 0, "kicad"),
    "C0805": ("Capacitor_SMD:C_0805_2012Metric", "0805", 2, 0, "kicad"),
    "LED0603": ("LED_SMD:LED_0603_1608Metric", "0603", 2, 0, "kicad"),
    "LED0805": ("LED_SMD:LED_0805_2012Metric", "0805", 2, 0, "kicad"),
    "L0603": ("Inductor_SMD:L_0603_1608Metric", "0603", 2, 0, "kicad"),
    "SOD123": ("Diode_SMD:D_SOD-123", "SOD-123", 2, 0, "kicad"),
    "F1812": ("Fuse:Fuse_1812_4532Metric", "1812", 2, 0, "kicad"),
    "SMA": ("Diode_SMD:D_SMA", "SMA", 2, 0, "kicad"),
    "SOT23": ("Package_TO_SOT_SMD:SOT-23", "SOT-23", 3, 0, "kicad"),
    "SOT23-5": ("Package_TO_SOT_SMD:SOT-23-5", "SOT-23-5", 5, 0, "kicad"),
    "SOT23-6": ("Package_TO_SOT_SMD:SOT-23-6", "SOT-23-6", 6, 0, "kicad"),
    "TSOT23-8": ("Package_TO_SOT_SMD:TSOT-23-8", "TSOT-23-8", 8, 0, "kicad"),
    "CPE6359": ("Capacitor_SMD:CP_Elec_6.3x5.9", "D6.3xL5.9mm", 2, 0, "kicad"),
    "QFN128": ("board:RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm", "QFN-128(12.3x12.3)", 129, 0,
               "[DS] r1.8 p.14 package drawing: 128 pins + exposed GND pad; EP size per [DS] §2.3 checked in Phase 5"),
    "WSON8": ("Package_SON:WSON-8-1EP_8x6mm_P1.27mm_EP3.4x4.3mm", "WSON-8", 9, 0, "kicad"),
    "UQFN10": ("board:TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm", "UQFN-10(1.5x2)", 10, 0,
               "TS3USB221A (TI SCDS277A) RSE0010A drawing: 10 pads, no EP; geometry checked in Phase 5"),
    "IND4040": ("board:L_FHD4020S_4.0x4.0mm", "4x4mm", 2, 0, "FHD4020S drawing (refs/fhd4020s-datasheet): 2 terminals; geometry in Phase 5"),
    "XTAL3225": ("Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "SMD3225-4P", 4, 0, "kicad"),
    "XTAL3215": ("Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", "SMD3215-2P", 2, 0, "kicad"),
    "TACT5151": ("board:SW_TS-1187A_5.1x5.1mm", "5.1x5.1mm", 4, 0, "TS-1187A drawing (LCSC C318884): 4 SMD legs; geometry in Phase 5"),
    "USBC16": ("Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", "SMD", 12, 4, "kicad"),
    "TF01A": ("board:microSD_TF-01A", "SMD", 13, 0,
              "TF-01A drawing (refs/tf-01a-datasheet, image-only): 9 contacts + 4 shell tabs; count = JLC joints; geometry in Phase 5 (UNVERIFIED until drawn)"),
    "RJ45": ("Connector_RJ:RJ45_Hanrun_HR911105A_Horizontal", "Through Hole", 0, 14, "kicad"),
    "USBA": ("board:USB_A_AF90_WJDG_RightAngle_THT", "Through Hole", 0, 6, "AF 90 WJDG drawing (LCSC C456018): 4 pins + 2 shell legs; geometry in Phase 5"),
    "HDR2x20": ("Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical", "Through Hole", 0, 40, "kicad"),
    "HDR1x3": ("Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", "Through Hole", 0, 3, "kicad"),
}

# (block, ref prefix, role/net note, qty/board, LCSC, value, fp key, source)
P = []
def add(block, pre, role, qty, lcsc, value, fp, src):
    P.append(dict(block=block, pre=pre, role=role, qty=qty, lcsc=lcsc, value=value, fp=fp, src=src))

# ---- usbc
add("usbc", "J", "USB-C receptacle (sink, USB2), VBUS contacts rated 5 A", 1, "C165948", "TYPE-C-31-M-12", "USBC16", "D-04; HRO drawing note 4-1 'Current rating 5A'")
add("usbc", "R", "CC1/CC2 Rd 5.1k to GND", 2, "C25905", "5.1k 1%", "R0402", "[LF] R3/R6 5.1K")
add("usbc", "R", "USB_DET_IN divider top (from VCC5V0_SYS, D-27)", 1, "C25744", "10k 1%", "R0402", "[LF] R2 10K")
add("usbc", "R", "USB_DET_IN divider bottom", 1, "C25810", "18k 1%", "R0603", "[LF] R5 18K (0603 Basic instead of 0402 Extended)")
add("usbc", "C", "USB_DET_IN filter 100 nF ([LF] C7; Phase 5 D-72)", 1, "C1525", "100nF 16V X7R", "C0402", "[LF] Type-C block C7 100nF on USB_DET_IN")
# ---- prot
add("prot", "F", "PPTC hold 3.0 A (25 C) / 2.01 A at 60 C / 1.61 A at 70 C, trip 6.0 A, 16 V, R1max 0.050 ohm", 1, "C883162", "BSMD1812-300-16V", "F1812", "D-37, D-56; BHFUSE BSMD1812 Rev 2025 p.2 table, p.5 Thermal Derating Chart")
add("prot", "D", "TVS 5.0 V standoff unidirectional on VBUS_5V", 1, "C113952", "SMAJ5.0A", "SMA", "D-37")
add("prot", "U", "USB D+/D- ESD array (USB-C side, USB-A side)", 2, "C7519", "USBLC6-2SC6", "SOT23-6", "D-04, IF-30")
add("prot", "C", "VBUS_5V bulk 2.2 uF 16 V ([LF] C4)", 1, "C23630", "2.2uF 16V X5R", "C0603", "[LF] C4; power.md §4")
add("prot", "C", "LTC2954 VIN decoupling", 1, "C1525", "100nF 16V X7R", "C0402", "power.md §6.1")
# ---- onoff
add("onoff", "U", "push-button on/off controller (-1 = active-high EN, see D-51)", 1, "C683782", "LTC2954CTS8-1#TRPBF", "TSOT23-8", "D-33, D-46, D-51; [LTC] p.6, p.12")
add("onoff", "Q", "Q_PWR high-side P-FET", 1, "C15127", "AO3401A", "SOT23", "D-33, D-41")
add("onoff", "Q", "Q_EN inverter: LTC2954-1 EN (pulled up to VBUS_5V) -> Q_PWR gate network via R_G (D-51)", 1, "C8545", "2N7002", "SOT23", "D-51")
add("onoff", "Q", "Q_KILL logic-level N-FET (VGS(th) max 1.45 V)", 1, "C20917", "AO3400A", "SOT23", "power.md §6.1 'AO3400A class'")
add("onoff", "R", "R_GS 100k, R_KU 100k, PWR_KILL pull-down 100k, R_ENPU 100k (D-51)", 4, "C25741", "100k 1%", "R0402", "D-41, D-33, D-20, D-51")
add("onoff", "R", "R_G 47k", 1, "C25792", "47k 1%", "R0402", "D-41")
add("onoff", "R", "PB_INT_N pull-up 4.7k", 1, "C25900", "4.7k 1%", "R0402", "D-19")
add("onoff", "R", "PB series link (0603 footprint, fitted 0R; D-64 merged onto the 0R 0603 line)", 1, "C21189", "0R 0603", "R0603", "power.md §6.1; D-64")
add("onoff", "C", "C_GS 470 nF X7R 25 V", 1, "C1623", "470nF 25V X7R", "C0603", "D-41")
add("onoff", "C", "C_GD 10 nF X7R 50 V", 1, "C15195", "10nF 50V X7R", "C0402", "D-41")
add("onoff", "C", "C_PDT 2.2 uF X5R +-10 % (D-117 c: hard-off >= 8 s worst case; was 0.68 uF C107067)", 1, "C23630", "2.2uF 16V X5R", "C0603", "D-33, D-117 c")
add("onoff", "R", "R_BL5 470R bleeder on VCC5V0_SYS (53 mW)", 1, "C17710", "470R 1% 0805", "R0805", "D-42")
add("onoff", "SW", "POWER push button", 1, "C318884", "TS-1187A-B-A-B", "TACT5151", "R4")
# ---- pmu
add("pmu", "U", "buck U4 VDD_0V9 / U5 VCC_1V8 / U6 VCC_3V3 / U7 VCC_DDR", 4, "C141836", "TLV62569DBVR", "SOT23-5", "D-32")
add("pmu", "L", "buck inductors 2.2 uH, Isat 7.5 A, Irated 4.8 A", 4, "C602029", "FHD4020S-2R2MT", "IND4040", "D-32 (Isat >= 3.6 A)")
add("pmu", "C", "buck input 10 uF 25 V x4", 4, "C96446", "10uF 25V X5R", "C0603", "D-32")
add("pmu", "C", "SY6280 VIN 10 uF 25 V ceramic, within 2 mm of U_USBA pin 5 (Phase 7)", 1, "C96446", "10uF 25V X5R", "C0603", "D-57; AN_SY6280 Rev 0.1 p.5 Supply Filter Capacitor")
add("pmu", "C", "buck input 100 nF x4 + output 100 nF x4 + C77 + SD-switch C69/C70/C72", 12, "C1525", "100nF 16V X7R", "C0402", "D-32, D-34, [LF] C69-C72")
add("pmu", "C", "U4 output 22 uF (D-117 c: TI Table 4 for VDD_0V9; was 10 uF C19702)", 1, "C59461", "22uF 6.3V X5R", "C0603", "D-32, D-117 c; TLV62569 SLVSDG1C Table 4")
add("pmu", "C", "U6 output 10 uF; VCC3V3_SD C71 10 uF", 2, "C19702", "10uF 10V X5R", "C0603", "D-32, D-47, [LF] C71")
add("pmu", "C", "U5 and U7 output 22 uF", 2, "C59461", "22uF 6.3V X5R", "C0603", "D-32")
add("pmu", "C", "feed-forward 6.8 pF C0G x4", 4, "C1576", "6.8pF 50V C0G", "C0402", "D-32")
add("pmu", "R", "FB bottom 100k x4", 4, "C25741", "100k 1%", "R0402", "D-32")
add("pmu", "R", "FB top U4 49.9k (0603 Basic)", 1, "C23184", "49.9k 1%", "R0603", "D-35")
add("pmu", "R", "FB top U7 127k", 1, "C25751", "127k 1%", "R0402", "[LF] R13")
add("pmu", "R", "FB top U5 200k, R14 200k, R43 200k", 3, "C25764", "200k 1%", "R0402", "[LF] R34/R14/R43")
add("pmu", "R", "FB top U6 442k", 1, "C5101", "442k 1%", "R0402", "D-43")
add("pmu", "R", "R35 10k U4 EN", 1, "C25744", "10k 1%", "R0402", "[LF] R35")
add("pmu", "R", "R41 1k (from VCC_1V8), bleeders R_BL09 1k, R_BL135 1k", 3, "C11702", "1k 1%", "R0402", "D-34, D-42")
add("pmu", "R", "bleeders R_BL18 680R, R_BL33 680R (0603 Basic; 16 mW each)", 2, "C23228", "680R 1%", "R0603", "D-42")
add("pmu", "C", "C65 150 nF X7R (U6 EN RC)", 1, "C162182", "150nF 16V X7R", "C0402", "D-34")
add("pmu", "R", "0R current-measurement links, one per rail in this order: VCC_1V8 (U5 out), VCC_3V3 (U6 out), VCC_DDR (U7 out); worst 0.55 A <= 1 A / 1.3. VDD_0V9 has NO 0R part: U4 out = normally-closed solder jumper JP_MEAS_0V9, VDD_0V9->VDD_ARM ([LF] R32) = direct copper net-tie NT_ARM (D-68)", 3, "C21189", "0R 0603", "R0603", "D-32, D-06, D-68; UNI-ROYAL 0603WAF datasheet V.9 p.5 §7 (0603 jumper < 50 mohm, 1 A rated)")
add("pmu", "R", "R31 (MIPI/VCCIO7 1.8 V) and R8 (AVDD1V8_USB) 1R series (0603 Basic)", 2, "C22936", "1R 1%", "R0603", "[LF] R31/R8")
add("pmu", "FB", "FB1 FEPHY 3V3, FB2 CODEC 1V8, FB3 ETH 1V8 (120R@100MHz, 2 A, 50 mohm, 0603 Basic)", 3, "C14709", "BLM18PG121SN1D", "L0603", "[LF] FB1-FB3 (BLM15PD121SN1 / UPZ1005D121); D-53")
add("pmu", "D", "RTC diode-OR from VCC_3V3 (battery-side diode DNP), SOD-123 Basic", 1, "C8598", "B5819W SL", "SOD123", "D-11, [LF] D2/D3 B5819WS; D-53")
add("pmu", "R", "RTC series R11 100R; nPOR Key1 R22 100R; RECOVERY 100R", 3, "C25076", "100R 1%", "R0402", "[LF] R11, R22, RECOVERY")
add("pmu", "U", "USB-A VBUS current-limited switch (ILIM 0.75-1.25 A with RSET 6.8k)", 1, "C55136", "SY6280AAC", "SOT23-5", "D-05, D-45, D-49; SY6280 p.2-3")
add("pmu", "R", "SY6280 RSET 6.8k (ILIM = 6800/RSET), 0603 Basic", 1, "C23212", "6.8k 1%", "R0603", "SY6280 p.2, p.3")
add("pmu", "C", "VBUS_USBA output 22 uF 25 V ceramic at U_USBA OUT", 1, "C45783", "22uF 25V X5R", "C0805", "AN_SY6280 Rev 0.1 p.5 layout guide (ceramic bypass at VOUT)")
add("usb", "C", "VBUS_USBA bulk 120 uF 10 V polymer at the USB-A connector (total 142 uF >= 120 uF)", 1, "C250087", "120uF 10V polymer", "CPE6359", "D-58; USB 2.0 §7.2.4.1 (UNVERIFIED, spec not downloaded); Lelon OCVZ catalog p.36 (10 V, 120 uF, 6.3x5.9, ESR 22 mohm max)")
add("pmu", "Q", "Q_SD card-power P-FET (ID 1.8 A at TA 70 C)", 1, "C10487", "SI2301CDS-T1-GE3", "SOT23", "[LF] Q1; D-45; Si2301CDS p.1")
add("pmu", "R", "Q_SD R55 10k", 1, "C25744", "10k 1%", "R0402", "[LF] R55")
add("pmu", "R", "Q_SD R51 100k", 1, "C25741", "100k 1%", "R0402", "[LF] R51")
add("pmu", "R", "VCC3V3_SD bleeder 10k ([LF] R52; Phase 5 D-72)", 1, "C25744", "10k 1%", "R0402", "[LF] Card Power R52 10K")
# ---- soc
add("soc", "U", "SoC", 1, "C5328706", "RV1106G3", "QFN128", "D-01")
add("soc", "C", "SoC decoupling 10 uF ([LF] C22 C23 C15 C18 C19 C13)", 6, "C19702", "10uF 10V X5R", "C0603", "[LF]; D-47")
add("soc", "C", "SoC decoupling 1 uF ([LF] C24 C25 C16 C20 C48 C11)", 6, "C52923", "1uF 25V X5R", "C0402", "[LF]; D-47")
add("soc", "C", "SoC decoupling 100 nF (0V9 x5, DDR x1, 1V8 x7, 3V3 x8) in [LF] order: 0V9 C26 C27 C28 C36 C17(ARM); DDR C21; 1V8 C12 C32 C31 C14 C10 C45 C47; 3V3 C37 C39 C40 C41 C9 C8 + 2 new (pins 88/108, no [LF] ref)", 21, "C1525", "100nF 16V X7R", "C0402", "[LF] C8-C47; power_rails.csv")
add("soc", "C", "C46 4.7 uF (1V8 FB4 block) + C3 CODEC_VCM 4.7 uF", 2, "C19666", "4.7uF 16V X5R", "C0603", "[LF] C46, C3")
add("soc", "R", "[LF] R1 240R (DDR/ZQ-area resistor, net confirmed in Phase 5)", 1, "C114755", "240R 1%", "R0402", "[LF] R1")
add("soc", "R", "ETH_EXTR 6.04k", 1, "C97819", "6.04k 1%", "R0402", "[LF] R7")
add("soc", "R", "nPOR pull-up R12 1k", 1, "C11702", "1k 1%", "R0402", "[LF] R12")
add("soc", "C", "nPOR C38 100 nF (D-117 c; was 10 nF C15195)", 1, "C1525", "100nF 16V X7R", "C0402", "[LF] C38; D-117 c")
add("soc", "R", "RECOVERY 10k to 1V8; SARADC_IN1 10k", 2, "C25744", "10k 1%", "R0402", "D-23, D-26")
add("soc", "C", "RECOVERY 1 nF; SARADC_IN1 1 nF", 2, "C1523", "1nF 50V X7R", "C0402", "D-23, D-26")
add("soc", "R", "pin 58 GPIO0_A0 100k pull-down", 1, "C25741", "100k 1%", "R0402", "D-26")
add("soc", "R", "FSPI_CLK series 22R ([LF] R15) and SDMMC_CLK series 22R ([LF] R16)", 2, "C25092", "22R 1%", "R0402", "[LF] R15/R16")
add("soc", "R", "SDMMC_DET series 100R ([LF] R54)", 1, "C25076", "100R 1%", "R0402", "[LF] R54")
add("soc", "C", "pin 71 OSC_PLL_DVDD decoupling 100 nF (new, Phase 5 D-72)", 1, "C1525", "100nF 16V X7R", "C0402", "Phase 5 D-72: every supply pin gets a capacitor")
add("soc", "C", "RTC_AVDD3V3 pin 19 decoupling 1 uF ([LF] C35; Phase 5 D-72)", 1, "C52923", "1uF 25V X5R", "C0402", "[LF] C35 1uF at pin 19")
# ---- xtal
add("xtal", "Y", "24 MHz crystal CL 12 pF", 1, "C164058", "TAXM24M4RFBCCT2T", "XTAL3225", "[LF] Y1 24MHz; D-52")
add("xtal", "Y", "32.768 kHz crystal CL 12.5 pF", 1, "C32346", "Q13FC13500004", "XTAL3215", "[LF] Y2")
add("xtal", "C", "crystal load 18 pF x4 (Y1, Y2)", 4, "C1549", "18pF 50V C0G", "C0402", "[LF] Y1/Y2 18pF")
add("xtal", "R", "Y1 series 22R", 1, "C25092", "22R 1%", "R0402", "[LF] 22R")
add("xtal", "R", "Y1 feedback 1M", 1, "C26083", "1M 1%", "R0402", "[LF] R10 1M")
# ---- nand
add("nand", "U", "SPI NAND 1 Gbit (128 MB) (D-14 fallback, D-52)", 1, "C22472329", "W25N01KVZEIR", "WSON8", "D-14, D-52")
add("nand", "C", "NAND 10 uF ([LF] C42)", 1, "C19702", "10uF 10V X5R", "C0603", "[LF] C42")
add("nand", "C", "NAND 100 nF ([LF] C43)", 1, "C1525", "100nF 16V X7R", "C0402", "[LF] C43")
add("nand", "R", "WP#/HOLD# pull-ups R18/R19 10k + CS# pull-up 10k (D-25)", 3, "C25744", "10k 1%", "R0402", "[LF] R18/R19; D-25")
add("nand", "R", "NAND-disable link on FSPI_CS0N (0R 0603, D-25, D-64)", 1, "C21189", "0R 0603", "R0603", "D-25; D-64")
# ---- sd
add("sd", "J", "microSD push-push socket with card detect (9 contacts)", 1, "C91145", "TF-01A", "TF01A", "[LF] TF1; TF-01A drawing")
# ---- eth
add("eth", "J", "RJ45 with magnetics and LEDs", 1, "C12074", "HR911105A", "RJ45", "[LF] J2 (HR911105A footprint class)")
add("eth", "R", "ETH 0R series links ([LF] R46-R49), 0603 (D-64)", 4, "C21189", "0R 0603", "R0603", "[LF] R46-R49; D-64")
add("eth", "C", "magnetics centre-tap 10 nF to GND", 2, "C15195", "10nF 50V X7R", "C0402", "[LF] J2 '103'")
# ---- usb
add("usb", "U", "USB 2.0 2:1 mux (S=L -> 1D = USB-C; OE tied low)", 1, "C128396", "TS3USB221ARSER", "UQFN10", "D-05; TS3USB221A Table 1 p.13")
add("usb", "C", "mux VCC 100 nF", 1, "C1525", "100nF 16V X7R", "C0402", "TS3USB221A §10")
add("usb", "R", "USB_SEL 10k pull-down; USBA_VBUS_EN 10k pull-down", 2, "C25744", "10k 1%", "R0402", "D-20")
add("usb", "J", "USB-A receptacle right-angle THT", 1, "C456018", "AF 90 WJDG", "USBA", "R3")
# ---- gpio
add("gpio", "J", "2x20 2.54 mm header", 1, "C124383", "B-2100S40P-B110", "HDR2x20", "R3, D-22")
add("gpio", "R", "I2C3_M1 pull-ups 2.2k", 2, "C25879", "2.2k 1%", "R0402", "D-29")
add("gpio", "R", "I2C1_M1 pull-ups 4.7k", 2, "C25900", "4.7k 1%", "R0402", "D-29")
# ---- uart
add("uart", "J", "3-pin debug UART header", 1, "C49257", "1x3P 2.54mm", "HDR1x3", "D-15")
add("uart", "R", "UART2 TX/RX 1k series", 2, "C11702", "1k 1%", "R0402", "D-30")
# ---- ui
add("ui", "SW", "RESET (Key1) and MASKROM/RECOVERY (Key2) buttons", 2, "C318884", "TS-1187A-B-A-B", "TACT5151", "[LF] Key1/Key2; R7")
add("ui", "LED", "power LED red (VCC_3V3)", 1, "C2286", "KT-0603R red", "LED0603", "D-09")
add("ui", "LED", "status LED (pin 62 net LED_STATUS, active-low; D-69) and Ethernet activity LED (pin 74), red 0603 Basic (same part as the power LED, D-64)", 2, "C2286", "KT-0603R red", "LED0603", "D-09, D-20, D-21; D-53; D-64; D-69")
add("ui", "R", "LED series 1k x3", 3, "C11702", "1k 1%", "R0402", "D-09")

# Not fitted / no part (documented, excluded from cost): ED1 ESD (DNP, [LF]); RTC battery holder H2 (DNP, D-11);
# battery-side B5819WS D3 (DNP); PB 100 nF (DNP); test points = bare pads (Phase 6).
DNP = ["ED1/ED2 ESD5451N footprints (DNP as on [LF])", "H2 RTC battery connector (DNP, D-11)",
       "RTC battery-side diode B5819WS (DNP, D-11)", "PB RC 100 nF (DNP, power.md §6.1)",
       "Test points TP1..TP11 are bare pads (Phase 6), no BOM part",
       "JP_MEAS_0V9: normally-closed solder jumper on U4 output (VDD_0V9), PCB copper only, cut to measure (D-68)",
       "NT_ARM: VDD_0V9 -> VDD_ARM direct copper / KiCad net-tie in place of [LF] R32 (D-68)"]


def price_at(prices, n):
    p = None
    for ladder, usd in sorted(prices):
        if n >= ladder:
            p = usd
    if p is None and prices:
        p = sorted(prices)[0][1]
    return p


def attrition(fpkey, n):
    # JLCPCB adds machine loss on small passives; assume +10 % (min 5) for 0402/0603/0805, 0 for others (ESTIMATE)
    small = fpkey in ("R0402", "C0402", "R0603", "C0603", "R0805", "C0805", "L0402", "L0603", "LED0603", "LED0805", "SOD123")
    return max(5, math.ceil(0.10 * n)) if small else 0


def line_price(design, code, qty_per_board, fpkey, boards):
    """Order quantity and unit price for one BOM line and N boards, from the cached LCSC record only
    (refs/lcsc-api-2026-10-29/<code>.json: productPriceList ladder + minBuyNumber). Shared by make_bom.py and
    check_bom.py so that any --boards N scenario is reproducible without regenerating bom.csv."""
    need = qty_per_board * boards
    order_qty = need + attrition(fpkey, need)
    prices, minbuy = [], 1
    try:
        with open(os.path.join(design, "refs", "lcsc-api-2026-10-29", f"{code}.json"), encoding="utf-8") as f:
            r = json.load(f).get("result") or {}
        minbuy = int(r.get("minBuyNumber") or 1)
        prices = [(int(x.get("ladder")), float(x.get("usdPrice"))) for x in (r.get("productPriceList") or [])]
    except (OSError, ValueError, TypeError):
        pass
    order_qty = max(order_qty, minbuy)
    return order_qty, price_at(prices, order_qty)


def parse_args(argv=None):
    from designdir import design_dir
    ap = argparse.ArgumentParser(description="Phase 4: write design/bom.csv from the part list P and the cached LCSC/JLCPCB "
                                 "records (refs/*-2026-10-29). No network access unless --refresh is given.")
    ap.add_argument("design", type=design_dir, help="the project design/ directory (must exist; never created)")
    ap.add_argument("--refresh", action="store_true", help="opt-in: re-fetch every part live (saved under refs/)")
    ap.add_argument("--boards", type=int, default=2, help="assembled boards to cost (default 2 = D-H2 Rev A)")
    ap.add_argument("--out", help="write here instead of <design>/bom.csv (what-if costings must use this)")
    a = ap.parse_args(argv)
    if a.boards < 1:
        ap.error("--boards must be >= 1")
    if a.out is None and a.boards != 2:
        ap.error("bom.csv is costed for the D-H2 order (2 boards); use --out for other --boards values")
    if a.out and not os.path.isdir(os.path.dirname(os.path.abspath(a.out))):
        ap.error(f"--out directory does not exist: {a.out}")
    return a


def main():
    a = parse_args()
    design, refresh, boards = a.design, a.refresh, a.boards
    counters = {}
    rows = {}
    order = []
    for p in P:
        refs = []
        for _ in range(p["qty"]):
            counters[p["pre"]] = counters.get(p["pre"], 0) + 1
            refs.append(f"{p['pre']}{counters[p['pre']]}")
        key = p["lcsc"]
        if key not in rows:
            rows[key] = dict(refs=[], qty=0, roles=[], blocks=[], srcs=[], value=p["value"], fp=p["fp"])
            order.append(key)
        r = rows[key]
        assert r["fp"] == p["fp"], f"{key}: footprint conflict {r['fp']} vs {p['fp']}"
        r["refs"] += refs
        r["qty"] += p["qty"]
        r["roles"].append(f"{p['block']}: {p['role']} ({','.join(refs)})")
        if p["block"] not in r["blocks"]:
            r["blocks"].append(p["block"])
        if p["src"] not in r["srcs"]:
            r["srcs"].append(p["src"])
    out = []
    for key in order:
        r = rows[key]
        s = lcsc_fetch.summary(design, key, refresh)
        fpname, pkgtok, smt, tht, padsrc = FP[r["fp"]]
        order_qty, unit = line_price(design, key, r["qty"], r["fp"], boards)
        if not s.get("exists"):
            unit = None
        out.append({
            "ref": " ".join(r["refs"]),
            "qty_per_board": r["qty"],
            "value": r["value"],
            "description": " | ".join(r["roles"]),
            "footprint": fpname,
            "footprint_key": r["fp"],
            "pads_smd_tht": f"{smt}+{tht}",
            "footprint_source": "KiCad library (cached .kicad_mod, pads re-counted by check_bom B3c)" if padsrc == "kicad" else padsrc,
            "lcsc_package": s.get("package", ""),
            "lcsc": key,
            "mpn": s.get("model", ""),
            "manufacturer": s.get("brand", ""),
            "basic_extended": s.get("jlc_lib", "UNKNOWN"),   # only Basic/Extended/UNKNOWN (D-71); B4 fails on UNKNOWN
            "stock": s.get("jlc_stock") if s.get("jlc_stock") is not None else "",
            "lcsc_stock": s.get("stock", ""),
            "unit_price_usd": f"{unit:.4f}" if unit is not None else "",
            "costed_for_boards": boards,
            "order_qty": order_qty,
            "line_cost_usd": f"{unit * order_qty:.2f}" if unit is not None else "",
            "smt_joints_per_part": smt,
            "tht_joints_per_part": tht,
            "blocks": " ".join(r["blocks"]),
            "source": "; ".join(r["srcs"]),
            "data_fetched": "2026-10-29 wmsc.lcsc.com product/detail + jlcpcb.com/partdetail",
        })
    path = a.out or os.path.join(design, "bom.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {path}: {len(out)} lines, {sum(o['qty_per_board'] for o in out)} parts/board")
    for o in out:
        print(f"{o['lcsc']:>10} {o['mpn'][:22]:22} q{o['qty_per_board']:>3} {o['basic_extended']:9} jlc={o['stock']!s:>9} lcsc={o['lcsc_stock']!s:>9} ${o['line_cost_usd']:>7} {o['lcsc_package'][:22]}")


if __name__ == "__main__":
    main()
