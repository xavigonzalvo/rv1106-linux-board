#!/usr/bin/env python3
"""Top level: build the whole Rev A schematic with SKiDL, run SKiDL ERC and write the KiCad netlist.

Usage (from anywhere):  design/.venv/bin/python design/schematic/board.py
Outputs (design/schematic/out/): board.net (KiCad netlist, import in KiCad PCB editor: File > Import > Netlist),
erc.txt (SKiDL ERC report), parts.csv and nets.csv (flat listings used by check_schematic.py and for review).
No network access; reads design/bom.csv, design/refmap.csv inputs (via tools/make_refmap.py) and design/pinmap.csv.
"""
import contextlib
import csv
import io
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.chdir(OUT)                                   # SKiDL writes its own .log/.erc files into the cwd
    import skidl
    import lib
    import power, button, soc, clocks, storage, ethernet, usb, expansion, debug  # noqa: E401

    power.usbc_prot()
    button.onoff()
    power.pmu()
    soc.soc()
    clocks.clocks()
    storage.nand()
    storage.sd()
    ethernet.ethernet()
    usb.usb()
    expansion.expansion()
    button.ui()
    debug.debug()

    # --- SKiDL ERC, captured to erc.txt
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setLevel(logging.DEBUG)
    lg = logging.getLogger("ERC_Logger")
    lg.addHandler(h)
    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
        skidl.ERC()
    lg.removeHandler(h)
    erc = buf.getvalue()
    open(os.path.join(OUT, "erc.txt"), "w", encoding="utf-8").write(erc)

    skidl.generate_netlist(file_=os.path.join(OUT, "board.net"))

    # --- flat listings
    import builtins
    circ = builtins.default_circuit
    with open(os.path.join(OUT, "parts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ref", "functional", "value", "footprint", "lcsc", "mpn", "in_bom", "block", "lf_ref",
                    "place_near", "pins"])
        for p in sorted(circ.parts, key=lambda p: (p.ref_prefix, int("".join(c for c in p.ref if c.isdigit()) or 0))):
            fl = p.fields
            w.writerow([p.ref, fl.get("Functional", ""), p.value, p.footprint, fl.get("LCSC", ""), fl.get("MPN", ""),
                        fl.get("InBOM", ""), fl.get("Block", ""), fl.get("LF_ref", ""),
                        fl.get("place_near", ""), len(p.pins)])
    with open(os.path.join(OUT, "nets.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["net", "nodes"])
        for n in sorted(circ.get_nets(), key=lambda n: n.name):
            w.writerow([n.name, " ".join(sorted(f"{p.part.ref}.{p.num}" for p in n.pins))])
    with open(os.path.join(OUT, "pins.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ref", "pin", "name", "net"])
        for p in sorted(circ.parts, key=lambda p: p.ref):
            for pin in p.pins:
                nets = [n.name for n in pin.nets] if pin.is_connected() else []
                nm = "NC" if (not nets or any(type(n).__name__ == "NCNet" for n in pin.nets)) else nets[0]
                w.writerow([p.ref, pin.num, pin.name, nm])
    nparts = len(circ.parts)
    nbom = sum(1 for p in circ.parts if p.fields.get("InBOM") == "yes")
    print(f"parts: {nparts} ({nbom} BOM parts, {nparts - nbom} copper-only), nets: {len(circ.get_nets())}")
    print("ERC summary:", " | ".join(l for l in erc.splitlines() if "ERC" in l and ("found" in l or "No errors" in l)))
    print(f"wrote {OUT}/board.net, erc.txt, parts.csv, nets.csv")


if __name__ == "__main__":
    main()
