#!/usr/bin/env python3
"""Layout phase L5: run KiCad DRC (kicad-cli, zones refilled in memory, all severities, schematic parity off) on the
saved board and summarise it.

    python3 design/pcb/scripts/l5_drc.py <out.json> [open_nets.json]

Prints the violation counts per type and severity and the unconnected items per net; with a second argument it writes
the list of nets that still have unconnected items (used by l5_cleanup.py to know what Freerouting has to finish).
Plain Python (no pcbnew): any interpreter works.
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boardlib as bl  # noqa: E402


def main():
    out = sys.argv[1]
    subprocess.run([bl.KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones", "-o", out,
                    bl.BOARD_FILE], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = json.load(open(out))
    c = Counter((v["severity"], v["type"]) for v in d["violations"])
    for (sev, t), n in sorted(c.items()):
        print("DRC %-8s %-28s %d%s" % (sev, t, n, " (capped)" if n == 199 else ""))
    nets = Counter()
    for u in d["unconnected_items"]:
        m = re.search(r"\[([^\]]+)\]", u["items"][0]["description"])
        nets[m.group(1) if m else "?"] += 1
    print("DRC errors %d, unconnected items %d on %d nets: %s" % (
        sum(n for (s, t), n in c.items() if s == "error"), len(d["unconnected_items"]), len(nets),
        " ".join("%s(%d)" % kv for kv in sorted(nets.items()))))
    if len(sys.argv) > 2:
        json.dump(sorted(nets), open(sys.argv[2], "w"), indent=0)


if __name__ == "__main__":
    main()
