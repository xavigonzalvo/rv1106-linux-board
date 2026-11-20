"""Blocks usbc, prot, pmu: USB-C sink, input protection, four TLV62569 bucks, sub-rails, RTC, SD and USB-A switches.

Sources: power.md §1 (tree), §2 (rail table), §3 (enable chain), §4 (USB-C/protection), §8; [LF] = Luckfox Pico
Pro/Max schematic (refs/luckfox-pico-pro-max-sch/): "Type-C" block (R3/R6 5.1K, R2 10K/R5 18K, C4 2.2uF, C7 100nF on
USB_DET_IN), "Card Power" (Q1 SI2301, R51 100K, R55 10K, C69/C70/C72 100nF, C71 10uF, R52 10K; R50 has no value
printed and is not fitted here), "RTC Power" (D3 B5819WS, R11 100R at pin 19, C35 1uF), sub-rails R31/R8 1R,
FB1/FB2/FB3. Deviations are D-03..D-72 in decisions.md.
"""
from lib import part, two

GND = "GND"


def usbc_prot():
    # --- usbc: 16-pin receptacle, sink only (Rd 5.1k on CC1/CC2), USB2 data pairs tied A/B ([LF] Type-C)
    part("J_USBC", "USBC", {
        "A4": "VBUS_IN", "A9": "VBUS_IN", "B4": "VBUS_IN", "B9": "VBUS_IN",
        "A1": GND, "A12": GND, "B1": GND, "B12": GND, "SH": GND,
        "A5": "CC1", "B5": "CC2",
        "A6": "USBC_DP", "B6": "USBC_DP", "A7": "USBC_DM", "B7": "USBC_DM",
        "A8": None, "B8": None,                        # SBU1/SBU2 unused (as [LF])
    })
    two("R_CC1", "R", "CC1", GND)
    two("R_CC2", "R", "CC2", GND)
    # --- prot: PPTC, TVS, small bulk before the on/off switch (power.md §4, D-37/D-56)
    two("F1", "F", "VBUS_IN", "VBUS_5V")
    part("D_TVS", "D", {"K": "VBUS_5V", "A": GND})
    two("C_VBUS", "C", "VBUS_5V", GND)
    # USB-C side ESD array: VBUS pin to the fused VBUS_5V (D-72: USBLC6 VBUS pin = that connector's VBUS)
    part("U_ESD_C", "USBLC6", {"1": "USBC_DP", "6": "USBC_DP", "3": "USBC_DM", "4": "USBC_DM",
                               "2": GND, "5": "VBUS_5V"}, place_near="J_USBC")
    # --- USB_VBUSDET divider on the SWITCHED VCC5V0_SYS (D-27), [LF] R2 10K / R5 18K / C7 100nF
    two("R_DET_TOP", "R", "VCC5V0_SYS", "USB_DET_IN")
    two("R_DET_BOT", "R", "USB_DET_IN", GND)
    two("C_USBDET", "C", "USB_DET_IN", GND)


# buck: (U, output net before the measurement link, rail net, EN net, measurement link name or None for JP)
BUCKS = [
    ("U4", "VDD_0V9_BUCK", "VDD_0V9", "U4_EN"),
    ("U5", "VCC_1V8_BUCK", "VCC_1V8", "VCC_DDR_1V8_EN"),
    ("U6", "VCC_3V3_BUCK", "VCC_3V3", "U6_EN"),
    ("U7", "VCC_DDR_BUCK", "VCC_DDR", "VCC_DDR_1V8_EN"),
]
MEAS = {"U4": "JP_MEAS_0V9", "U5": "R_MEAS_1V8", "U6": "R_MEAS_3V3", "U7": "R_MEAS_DDR"}


def pmu():
    for u, out, rail, en in BUCKS:
        part(u, "TLV62569", {"VIN": "VCC5V0_SYS", "GND": GND, "SW": f"{u}_SW", "EN": en, "FB": f"{u}_FB"})
        two(f"C_IN_{u}", "C", "VCC5V0_SYS", GND, place_near=f"{u} pin 4")
        two(f"C_IN100_{u}", "C", "VCC5V0_SYS", GND, place_near=f"{u} pin 4")
        two(f"L_{u}", "L", f"{u}_SW", out)
        two(f"C_OUT_{u}", "C", out, GND)
        two(f"C_OUT100_{u}", "C", out, GND)
        # feedback divider taps the REGULATOR side of the measurement link (D-68: cutting it never opens the loop)
        two(f"R_FBT_{u}", "R", out, f"{u}_FB")
        two(f"C_FF_{u}", "C", out, f"{u}_FB")
        two(f"R_FBB_{u}", "R", f"{u}_FB", GND)
        kind = "JP2" if MEAS[u].startswith("JP") else "R"
        two(MEAS[u], kind, out, rail)
    # --- enable chain (power.md §3, D-34): U4 EN from VCC5V0_SYS; U5+U7 RC from VCC5V0_SYS; U6 from VCC_1V8
    two("R35", "R", "VCC5V0_SYS", "U4_EN")
    two("R14", "R", "VCC5V0_SYS", "VCC_DDR_1V8_EN")
    two("C77", "C", "VCC_DDR_1V8_EN", GND)
    two("R41", "R", "VCC_1V8", "PWR_EN")
    two("R43", "R", "PWR_EN", "U6_EN")
    two("C65", "C", "U6_EN", GND)
    # --- discharge bleeders (D-42); R_BL5 on VCC5V0_SYS is in button.py (onoff)
    two("R_BL09", "R", "VDD_0V9", GND)
    two("R_BL135", "R", "VCC_DDR", GND)
    two("R_BL18", "R", "VCC_1V8", GND)
    two("R_BL33", "R", "VCC_3V3", GND)
    # --- CPU core: VDD_0V9 -> VDD_ARM copper net-tie ([LF] R32, D-06/D-68)
    two("NT_ARM", "NT2", "VDD_0V9", "VDD_ARM")
    # --- SoC sub-rails copied from [LF]
    two("R31", "R", "VCC_1V8", "MIPI_CSI_AVDD_1V8")
    two("R8", "R", "VCC_1V8", "AVDD1V8_USB")
    two("FB2", "FB", "VCC_1V8", "VCC1V8_CODEC")
    two("FB3", "FB", "VCC_1V8", "ETH_AVDD1V8")
    two("FB1", "FB", "VCC_3V3", "FEPHY_AVDD3V3")
    # --- RTC supply ([LF] "RTC Power": D3 from VCC_3V3, R11 100R to pin 19; battery branch not placed, D-75)
    part("D_RTC", "D", {"A": "VCC_3V3", "K": "VCC3V3_RTC_IN"})
    two("R11", "R", "VCC3V3_RTC_IN", "VCC3V3_RTC")
    # --- microSD card power ([LF] "Card Power")
    part("Q_SD", "MOS", {"G": "SD_PWR_G", "S": "VCC_3V3", "D": "VCC3V3_SD"})
    two("R51", "R", "VCC_3V3", "SD_PWR_G")
    two("R55", "R", "SD_PWR_G", "SDMMC_PWREN")
    two("C69", "C", "VCC_3V3", GND, place_near="Q_SD source")
    two("C70", "C", "VCC3V3_SD", GND, place_near="Q_SD drain")
    two("C71", "C", "VCC3V3_SD", GND, place_near="J_SD pin 4")
    two("C72", "C", "VCC3V3_SD", GND, place_near="J_SD pin 4")
    two("R_SD_BL", "R", "VCC3V3_SD", GND)
    # --- USB-A VBUS switch (D-05, D-57; AN_SY6280 p.2 pinout, ILIM = 6800/RSET)
    part("U_USBA", "SY6280", {"IN": "VCC5V0_SYS", "GND": GND, "ISET": "USBA_ISET", "EN": "USBA_VBUS_EN",
                              "OUT": "VBUS_USBA"})
    two("C_USBA_IN", "C", "VCC5V0_SYS", GND, place_near="U_USBA pin 5 (<= 2 mm, D-57)")
    two("R_SET", "R", "USBA_ISET", GND)
    two("C_USBA_OUT", "C", "VBUS_USBA", GND, place_near="U_USBA pin 1")
