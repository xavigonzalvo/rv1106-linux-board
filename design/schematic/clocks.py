"""Block xtal: 24 MHz and 32.768 kHz crystals, copied from [LF] (refs/luckfox-pico-pro-max-sch/, zone around Y1/Y2):
Y1 X1 -> OSC_XIN (pin 68) with C30 18pF; Y1 X2 -> R9 22R -> OSC_XOUT (pin 69) with C29 18pF on the crystal side;
R10 1M between OSC_XOUT and OSC_XIN; Y1 GND pads to GND. Y2 between RTC_XOUT (20) and RTC_XIN (21), C33/C34 18pF.
Part choice (TAXM24M4RFBCCT2T, CL 12 pF) and load-cap check: D-52.
"""
from lib import part, two

GND = "GND"


def clocks():
    part("Y1", "XTAL4", {"1": "OSC_XIN", "3": "OSC_XOUT_X", "2": GND, "4": GND}, place_near="U_SOC pins 68/69")
    two("R_Y1_SER", "R", "OSC_XOUT", "OSC_XOUT_X", place_near="U_SOC pin 69")
    two("R_Y1_FB", "R", "OSC_XOUT", "OSC_XIN", place_near="U_SOC pins 68/69")
    two("C_Y1_XOUT", "C", "OSC_XOUT_X", GND, place_near="Y1 pin 3")
    two("C_Y1_XIN", "C", "OSC_XIN", GND, place_near="Y1 pin 1")
    two("Y2", "XTAL2", "RTC_XIN", "RTC_XOUT", place_near="U_SOC pins 20/21")
    two("C_Y2_XIN", "C", "RTC_XIN", GND, place_near="Y2")
    two("C_Y2_XOUT", "C", "RTC_XOUT", GND, place_near="Y2")
