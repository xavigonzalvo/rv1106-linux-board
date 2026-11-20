"""Block gpio: 2x20 2.54 mm header (Raspberry-Pi-style positions, D-22) and the header I2C pull-ups (D-29).

Signal positions come from design/pinmap.csv (column `external`: "2x20 header pin N"), power positions from D-22:
3V3 on 1/17, 5V (switched VCC5V0_SYS, output only, D-08) on 2/4, GND on 6/9/14/20/25/30/34/39.
"""
import re

from lib import part, two
from soc import load_pinmap

GND = "GND"
POWER_PINS = {1: "VCC_3V3", 17: "VCC_3V3", 2: "VCC5V0_SYS", 4: "VCC5V0_SYS",
              **{n: GND for n in (6, 9, 14, 20, 25, 30, 34, 39)}}


def header_map():
    m = dict(POWER_PINS)
    for r in load_pinmap():
        g = re.search(r"2x20 header pin (\d+)", r["external"])
        if g:
            n = int(g.group(1))
            assert n not in m, f"header pin {n} used twice"
            m[n] = r["net"]
    assert sorted(m) == list(range(1, 41)), f"header pins missing: {sorted(set(range(1, 41)) - set(m))}"
    return m


def expansion():
    part("J_HDR", "HDR40", {str(n): net for n, net in header_map().items()})
    two("R_I2C3_SCL", "R", "VCC_3V3", "HDR_I2C3_SCL")
    two("R_I2C3_SDA", "R", "VCC_3V3", "HDR_I2C3_SDA")
    two("R_I2C1_SDA", "R", "VCC_3V3", "HDR_I2C1_SDA")
    two("R_I2C1_SCL", "R", "VCC_3V3", "HDR_I2C1_SCL")
