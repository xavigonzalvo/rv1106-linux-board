"""Block usb: TS3USB221A 2:1 mux on the single SoC USB 2.0 port (D-05), USB-A host port, USB-A ESD.

TS3USB221A (TI SCDS277A p.3 pins, p.13 Table 1): OE = L enables; S = L -> D = 1D, S = H -> D = 2D.
1D = USB-C (device / MASKROM), 2D = USB-A (host). USB_SEL (pin 65, GPIO0_A6_d) has a 10k pull-down, so the reset
state selects USB-C (D-20). OE tied to GND. VBUS_USBA from the SY6280 (power.py); 120 uF polymer at the jack (D-58).
"""
from lib import part, two

GND = "GND"


def usb():
    part("U_MUX", "TS3USB221A", {"1D+": "USBC_DP", "1D-": "USBC_DM", "2D+": "USBA_DP", "2D-": "USBA_DM",
                                 "GND": GND, "OE": GND, "D-": "USB_DM", "D+": "USB_DP", "S": "USB_SEL",
                                 "VCC": "VCC_3V3"})
    two("C_MUX", "C", "VCC_3V3", GND, place_near="U_MUX pin 10")
    two("R_USBSEL", "R", "USB_SEL", GND)
    two("R_USBAEN", "R", "USBA_VBUS_EN", GND, place_near="U_USBA pin 4")
    part("U_ESD_A", "USBLC6", {"1": "USBA_DP", "6": "USBA_DP", "3": "USBA_DM", "4": "USBA_DM",
                               "2": GND, "5": "VBUS_USBA"}, place_near="J_USBA")
    part("J_USBA", "USBA", {"1": "VBUS_USBA", "2": "USBA_DM", "3": "USBA_DP", "4": GND, "SH": GND})
    part("C_USBA_BULK", "CP", {"+": "VBUS_USBA", "-": GND}, place_near="J_USBA pin 1")
