"""Block uart + test points.

Debug UART: 3-pin header J_UART (1 GND, 2 TX out of the board, 3 RX into the board), 1k series on both lines
(D-30); TP9/TP10 sit on the SoC side of the resistors.

Test points: bare pads (no BOM part, KiCad TestPoint:TestPoint_Pad_D1.5mm, F.Cu + F.Mask only, so no paste and
nothing to assemble). The authoritative list with expected values is design/testpoints.md (Phase 6, D-77):
  TP1..TP11 follow PLAN.md "Physical test points". TP8 = LTC2954-1 EN output ONOFF_EN (high when on, as PLAN says;
  = power.md TP8a'); TP12 = EN_N, the inverted Q_EN-drain node (= power.md TP8a); TP13 = VCC5V0_SYS (TP8b);
  TP14 = PWR_EN (TP8c); TP15..TP18 and TP21..TP26 put a pad on every other rail in power_rails.csv (R7);
  TP27..TP30 = on/off and SD control lines for bring-up; TP19, TP20, TP31 = ground pads for the probe.
"""
from lib import part, two

GND = "GND"

# (ref, functional name, net, PLAN / power.md label)
TESTPOINTS = [
    ("TP1", "TP_VBUS_5V", "VBUS_5V", "TP1"), ("TP2", "TP_VCC_3V3", "VCC_3V3", "TP2"),
    ("TP3", "TP_VCC_1V8", "VCC_1V8", "TP3"), ("TP4", "TP_VDD_0V9", "VDD_0V9", "TP4 (VDD_CORE)"),
    ("TP5", "TP_VCC_DDR", "VCC_DDR", "TP5"), ("TP6", "TP_OSC_XOUT", "OSC_XOUT", "TP6 24 MHz"),
    ("TP7", "TP_NPOR", "NPOR", "TP7 RESET_N"), ("TP8", "TP_ONOFF_EN", "ONOFF_EN", "TP8 controller out, high when on (power.md TP8a')"),
    ("TP9", "TP_UART2_TX", "UART2_TX", "TP9"), ("TP10", "TP_UART2_RX", "UART2_RX", "TP10"),
    ("TP11", "TP_LED_ETH", "LED_ETH", "TP11 ETH activity"),
    ("TP12", "TP_EN_N", "EN_N", "Q_EN drain, low when on (power.md TP8a)"), ("TP13", "TP_VCC5V0_SYS", "VCC5V0_SYS", "TP8b"),
    ("TP14", "TP_PWR_EN", "PWR_EN", "TP8c"), ("TP15", "TP_VDD_ARM", "VDD_ARM", "rail"),
    ("TP16", "TP_VCC3V3_SD", "VCC3V3_SD", "rail"), ("TP17", "TP_VBUS_USBA", "VBUS_USBA", "rail"),
    ("TP18", "TP_VCC3V3_RTC", "VCC3V3_RTC", "rail"),
    ("TP19", "TP_GND1", GND, "probe ground"), ("TP20", "TP_GND2", GND, "probe ground"),
    # Phase 6 additions (D-77): every remaining rail, the on/off control lines, SD card detect
    ("TP21", "TP_VBUS_IN", "VBUS_IN", "rail (before F1)"),
    ("TP22", "TP_MIPI_CSI_AVDD_1V8", "MIPI_CSI_AVDD_1V8", "sub-rail"),
    ("TP23", "TP_AVDD1V8_USB", "AVDD1V8_USB", "sub-rail"),
    ("TP24", "TP_VCC1V8_CODEC", "VCC1V8_CODEC", "sub-rail"),
    ("TP25", "TP_ETH_AVDD1V8", "ETH_AVDD1V8", "sub-rail"),
    ("TP26", "TP_FEPHY_AVDD3V3", "FEPHY_AVDD3V3", "sub-rail"),
    ("TP27", "TP_PB_INT_N", "PB_INT_N", "button interrupt to SoC"),
    ("TP28", "TP_PWR_KILL", "PWR_KILL", "SoC power-off request"),
    ("TP29", "TP_PWR_KILL_N", "PWR_KILL_N", "LTC2954 KILL pin (hold-up point for rail-isolated bring-up)"),
    ("TP30", "TP_SDMMC_DET", "SDMMC_DET", "SD card detect at the SoC"),
    ("TP31", "TP_GND3", GND, "probe ground near the SoC / 24 MHz"),
]


def debug():
    part("J_UART", "HDR3", {"1": GND, "2": "UART2_TX_HDR", "3": "UART2_RX_HDR"})
    two("R_UART_TX", "R", "UART2_TX", "UART2_TX_HDR")
    two("R_UART_RX", "R", "UART2_RX_HDR", "UART2_RX")
    for ref, func, net, label in TESTPOINTS:
        part(func, "TP", {"_ref": ref, "1": net}, note=label)
