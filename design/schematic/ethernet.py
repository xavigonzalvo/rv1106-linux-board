"""Block eth: RJ45 with magnetics on the SoC's embedded 10/100 PHY.

Copy of [LF] "Ethernet" (J2): ETH_T_P/N, ETH_R_P/N through 0R R46-R49 to jack pins 1 TD+, 2 TD-, 3 RD+, 6 RD-;
centre taps 4 and 5 each 10 nF (103) to GND (C66/C67); pin 7 NC; pin 8 chassis -> ground ([LF] C68 '0R/1nF/100V';
Hanrun HR911105A datasheet p.1 note "Connect CHS GND to PCB Ground" -> direct GND here); jack shield to GND.
ETH_EXTR 6.04k is in soc.py. The jack's two LEDs (9/10 green, 11/12 yellow) are not used: the activity LED is the
discrete LED_ETH on pin 74 (D-21), so pins 9-12 are NC (D-72).
"""
from lib import part, two

GND = "GND"


def ethernet():
    two("R_ETH_TXP", "R", "ETH_TXP", "ETH_TXP_J")
    two("R_ETH_TXN", "R", "ETH_TXN", "ETH_TXN_J")
    two("R_ETH_RXP", "R", "ETH_RXP", "ETH_RXP_J")
    two("R_ETH_RXN", "R", "ETH_RXN", "ETH_RXN_J")
    part("J_RJ45", "RJ45", {"1": "ETH_TXP_J", "2": "ETH_TXN_J", "3": "ETH_RXP_J", "6": "ETH_RXN_J",
                            "4": "ETH_TCT", "5": "ETH_RCT", "7": None, "8": GND,
                            "9": None, "10": None, "11": None, "12": None, "SH": GND})
    two("C_CT_TX", "C", "ETH_TCT", GND, place_near="J_RJ45 pin 4")
    two("C_CT_RX", "C", "ETH_RCT", GND, place_near="J_RJ45 pin 5")
