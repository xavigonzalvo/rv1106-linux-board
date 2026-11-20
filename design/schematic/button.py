"""Blocks onoff + ui: LTC2954-1 push-button controller, Q_EN inverter, Q_PWR high-side switch, KILL inverter,
POWER / RESET / MASKROM buttons and the three LEDs.

Sources: power.md §6.1 (circuit), §6.4a (LTC2954-1 + Q_EN, D-51), §6.5 (TP8a/a'/b/c); D-19 (PB_INT_N 4.7k),
D-20 (PWR_KILL 100k pull-down), D-41 (gate network); [LF] "Power Reset" (Key1 + R22 100R on NPOR) and
"System RECOVERY Key" (R21 10K to VCC_1V8, C44 1nF, R23 100R, Key2); D-09/D-21/D-69 (LEDs).
"""
from lib import part, two

GND = "GND"


def onoff():
    part("U_ONOFF", "LTC2954", {"VIN": "VBUS_5V", "PB": "PB_IN", "ONT": None,       # ONT open: tDB,ON 26-41 ms
                                "GND": GND, "INT": "PB_INT_N", "EN": "ONOFF_EN", "PDT": "ONOFF_PDT",
                                "KILL": "PWR_KILL_N"})
    two("C_ONOFF_VIN", "C", "VBUS_5V", GND, place_near="U_ONOFF pin 1")
    two("C_PDT", "C", "ONOFF_PDT", GND)        # 2.2 uF X5R (D-117 c: hard-off >= 8 s worst case; value from bom.csv)
    # POWER button -> 0R link -> PB (the [LTC] p.12 RC option is not fitted, power.md §6.1)
    part("SW_PWR", "TACT", {"1": "PWR_BTN_N", "2": "PWR_BTN_N", "3": GND, "4": GND})
    two("R_PB", "R", "PWR_BTN_N", "PB_IN")
    # EN (-1: active-high open drain) -> Q_EN inverter -> EN_N = EN-bar-equivalent node (TP8a)
    two("R_ENPU", "R", "VBUS_5V", "ONOFF_EN")
    part("Q_EN", "MOS", {"G": "ONOFF_EN", "S": GND, "D": "EN_N"})
    two("R_G", "R", "EN_N", "QPWR_G")
    # Q_PWR AO3401A: S = VBUS_5V, D = VCC5V0_SYS; gate network R_GS/C_GS (G-S), C_GD (G-D) per D-41
    part("Q_PWR", "MOS", {"G": "QPWR_G", "S": "VBUS_5V", "D": "VCC5V0_SYS"})
    two("R_GS", "R", "QPWR_G", "VBUS_5V")
    two("C_GS", "C", "QPWR_G", "VBUS_5V")
    two("C_GD", "C", "QPWR_G", "VCC5V0_SYS")
    two("R_BL5", "R", "VCC5V0_SYS", GND)
    # interrupt to SoC pin 60 (D-19) and kill path from SoC pin 63 (D-03/D-20)
    two("R_INTPU", "R", "VCC_3V3", "PB_INT_N")
    two("R_KU", "R", "VCC_3V3", "PWR_KILL_N")
    part("Q_KILL", "MOS", {"G": "PWR_KILL", "S": GND, "D": "PWR_KILL_N"})
    two("R_KILLPD", "R", "PWR_KILL", GND)


def ui():
    # RESET: NPOR -> R22 100R -> Key1 -> GND ([LF] "Power Reset"; ED1 TVS not fitted on [LF] and not placed here)
    two("R22", "R", "NPOR", "NPOR_KEY")
    part("SW_RESET", "TACT", {"1": "NPOR_KEY", "2": "NPOR_KEY", "3": GND, "4": GND})
    # MASKROM/RECOVERY: RECOVERY -> 100R -> Key2 -> GND ([LF] R23 100R; ED2 not fitted)
    two("R_RECOV", "R", "RECOVERY", "RECOVERY_KEY")
    part("SW_RECOV", "TACT", {"1": "RECOVERY_KEY", "2": "RECOVERY_KEY", "3": GND, "4": GND})
    # LEDs (KT-0603R red, 1k series)
    two("R_LED_PWR", "R", "VCC_3V3", "LED_PWR_A")
    part("LED_PWR", "LED", {"A": "LED_PWR_A", "K": GND})
    two("R_LED_STAT", "R", "VCC_3V3", "LED_STAT_A")                 # active-LOW on pin 62 (GPIO0_A3_u)
    part("LED_STAT", "LED", {"A": "LED_STAT_A", "K": "LED_STATUS"})
    two("R_LED_ETH", "R", "LED_ETH", "LED_ETH_A")                   # active-HIGH on pin 74 (GPIO1_A2_d)
    part("LED_ETH", "LED", {"A": "LED_ETH_A", "K": GND})
