"""Blocks nand + sd.

nand: copy of [LF] "SPI Flash" (U2 W25N02KVZE -> here W25N01KVZEIR, D-52): /CS FSPI_CS0N, DO FSPI_D1, /WP FSPI_D2,
DI FSPI_D0, CLK FSPI_CLK (via [LF] R15 22R at the SoC), /HOLD FSPI_D3, VCC = VCCIO_FLASH = VCC_3V3, EPAD GND;
R18/R19 10K pull-ups on FSPI_D3/FSPI_D2; C42 10uF + C43 100nF. Deviation D-25: 0R link on CS# + 10k CS# pull-up on
the NAND side (remove the link to hide the NAND from the BootROM).

sd: copy of [LF] "Micro-SD Card" (TF1): D2/D3/CMD/CLK/D0/D1 direct, CLK via [LF] R16 22R, card detect via [LF] R54
100R to SDMMC_DET (SoC internal pull-up, GPIO3_A1_u), VDD = VCC3V3_SD (card switch in power.py), shell to GND.
No external CMD/DAT pull-ups, as [LF] (SoC internal pull-ups; pinmap reset_pull = pull-up), D-72.
"""
from lib import part, two

GND = "GND"


def nand():
    two("R_NANDDIS", "R", "FSPI_CS0N", "FSPI_CS0N_NAND", place_near="U_NAND pin 1")
    two("R_CSPU", "R", "VCC_3V3", "FSPI_CS0N_NAND")
    two("R_FSPI_CLK", "R", "FSPI_CLK", "FSPI_CLK_NAND", place_near="U_SOC pin 48")
    part("U_NAND", "W25N", {"1": "FSPI_CS0N_NAND", "2": "FSPI_D1", "3": "FSPI_D2", "4": GND, "5": "FSPI_D0",
                            "6": "FSPI_CLK_NAND", "7": "FSPI_D3", "8": "VCC_3V3", "9": GND})
    two("R18", "R", "VCC_3V3", "FSPI_D3")
    two("R19", "R", "VCC_3V3", "FSPI_D2")
    two("C42", "C", "VCC_3V3", GND, place_near="U_NAND pin 8")
    two("C43", "C", "VCC_3V3", GND, place_near="U_NAND pin 8")


def sd():
    two("R_SD_CLK", "R", "SDMMC_CLK", "SDMMC_CLK_SD", place_near="U_SOC pin 15")
    two("R_SD_DET", "R", "SDMMC_DET", "SD_CD_SW")
    part("J_SD", "MICROSD", {"1": "SDMMC_D2", "2": "SDMMC_D3", "3": "SDMMC_CMD", "4": "VCC3V3_SD",
                             "5": "SDMMC_CLK_SD", "6": GND, "7": "SDMMC_D0", "8": "SDMMC_D1",
                             "9": "SD_CD_SW", "SH": GND})
