"""Block soc: RV1106G3 (QFN-128 + exposed pad 129), all supply decoupling, nPOR RC, DRAM_ZQ, ETH_EXTR,
SARADC strap/termination, CODEC_VCM and unused-pin handling.

Every SoC pin is wired from design/pinmap.csv (column `net`, 'NC' = no connection), so the schematic cannot drift from
the Phase-2 pin map. Pin names are [DS] Table 2-1 (RV1106 datasheet r1.8 pp.18-19). The exposed pad is pad 129 (VSS),
as on the [LF] symbol ("ePAD 129").

Decoupling = the [LF] Pico Pro/Max set (power.md §0/§2, refmap.csv DEC_*), placed one-per-pin as listed in DECOUPLING
below, plus D-72 additions (pin 71 100 nF, pin 19 [LF] C35 1 uF). [DS] r1.8 gives no decoupling table (UNVERIFIED that
a Rockchip hardware design guide does), so the reference design is the "datasheet" for this rule.
"""
import csv
import os

from lib import DESIGN, part, two, Pin

GND = "GND"

# Pins whose pinmap net is 'NC' but which still carry a part (pinmap `external` column says so)
NC_WITH_EXTERNAL = {"58": "GPIO0_A0_PD"}   # D-26: GPIO0_A0_z has no internal pull; 100k pull-down (R_PD58)

# functional name -> (SoC pin it sits next to, rail net). Order and values = [LF] (refmap.csv _DEC) + D-72.
DECOUPLING = [
    ("DEC_0V9_100N_1", "10", "VDD_0V9"), ("DEC_0V9_1U_1", "51", "VDD_0V9"), ("DEC_0V9_10U_1", "54", "VDD_0V9"),
    ("DEC_0V9_100N_2", "55", "VDD_0V9"), ("DEC_0V9_1U_2", "82", "VDD_0V9"), ("DEC_0V9_100N_3", "103", "VDD_0V9"),
    ("DEC_0V9_10U_2", "116", "VDD_0V9"), ("DEC_0V9_P67_100N", "67", "VDD_0V9"), ("DEC_0V9_P71_100N", "71", "VDD_0V9"),
    ("DEC_ARM_10U", "115", "VDD_ARM"), ("DEC_ARM_1U", "115", "VDD_ARM"), ("DEC_ARM_100N", "115", "VDD_ARM"),
    ("DEC_DDR_100N", "49", "VCC_DDR"), ("DEC_DDR_10U_1", "49", "VCC_DDR"), ("DEC_DDR_1U", "50", "VCC_DDR"),
    ("DEC_DDR_10U_2", "50", "VCC_DDR"), ("DEC_DDR_FB4_1U", "56", "VCC_DDR"),
    ("DEC_1V8_P53_1U", "53", "VCC_1V8"), ("DEC_1V8_P53_100N", "53", "VCC_1V8"), ("DEC_1V8_P70_100N", "70", "VCC_1V8"),
    ("DEC_1V8_FB4_4U7", "70", "VCC_1V8"), ("DEC_1V8_FB4_100N", "70", "VCC_1V8"),
    ("DEC_1V8_P1_100N", "1", "MIPI_CSI_AVDD_1V8"), ("DEC_1V8_P24_100N", "24", "AVDD1V8_USB"),
    ("DEC_CODEC_10U", "31", "VCC1V8_CODEC"), ("DEC_CODEC_100N", "31", "VCC1V8_CODEC"),
    ("DEC_1V8_P96_100N", "96", "ETH_AVDD1V8"),
    ("DEC_3V3_P13_100N", "13", "VCC_3V3"), ("DEC_3V3_P28_100N", "28", "VCC_3V3"), ("DEC_3V3_P43_100N", "43", "VCC_3V3"),
    ("DEC_3V3_P61_100N", "61", "VCC_3V3"), ("DEC_3V3_P81_100N", "81", "VCC_3V3"), ("DEC_3V3_P88_100N", "88", "VCC_3V3"),
    ("DEC_3V3_P108_100N", "108", "VCC_3V3"), ("DEC_3V3_P101_100N", "101", "FEPHY_AVDD3V3"),
    ("DEC_RTC_1U", "19", "VCC3V3_RTC"),
]


def load_pinmap():
    with open(os.path.join(DESIGN, "pinmap.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def soc():
    rows = load_pinmap()
    from lib import KIND, P as PAS, PI
    pins, conns = [], {}
    for r in rows:
        num = "129" if r["pin"] == "EPAD" else r["pin"]
        typ = PI if r["status"] == "POWER" else PAS
        pins.append((num, r["ds_pin_name"], typ))
        net = r["net"]
        if net == "NC":
            conns[num] = NC_WITH_EXTERNAL.get(num)
        else:
            conns[num] = net
    KIND["RV1106"] = ("U", pins, "RV1106 datasheet r1.8 Table 2-1 pp.18-19 via design/pinmap.csv; EP = pad 129 ([LF] 'ePAD 129')")
    part("U_SOC", "RV1106", conns)

    for func, pin, rail in DECOUPLING:
        two(func, "C", rail, GND, place_near=f"U_SOC pin {pin}")
    # SoC-side passives copied from [LF]
    two("R1", "R", "DRAM_ZQ", GND, place_near="U_SOC pin 52")            # [LF] R1 240R DRAM_ZQ
    two("R7", "R", "ETH_EXTR", GND, place_near="U_SOC pin 102")          # [LF] R7 6.04K 1% FEPHY_REXT
    two("R12", "R", "VCC_3V3", "NPOR", place_near="U_SOC pin 66")        # [LF] R12 1K
    two("C38", "C", "NPOR", GND, place_near="U_SOC pin 66")              # [LF] C38 10nF; Rev A 100 nF (D-117 c, value from bom.csv)
    two("R_RECOV_PU", "R", "VCC_1V8", "RECOVERY", place_near="U_SOC pin 23")   # [LF] R21 10K
    two("C_RECOV", "C", "RECOVERY", GND, place_near="U_SOC pin 23")            # [LF] C44 1nF
    two("R_ADC1_PU", "R", "VCC_1V8", "SARADC_IN1", place_near="U_SOC pin 22")  # [LF] R57 10K
    two("C_ADC1", "C", "SARADC_IN1", GND, place_near="U_SOC pin 22")           # [LF] C73 1nF
    two("C_CODEC_VCM", "C", "CODEC_VCM", GND, place_near="U_SOC pin 30")       # [LF] C3 4.7uF
    two("R_PD58", "R", "GPIO0_A0_PD", GND, place_near="U_SOC pin 58")          # D-26
