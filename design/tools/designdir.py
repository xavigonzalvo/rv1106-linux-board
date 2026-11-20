"""Shared argparse type for the Phase 4 tools (D-70): the design directory must already exist and look like this
project's design/ folder. The tools never create a new tree (verifier minor: `make_bom.py -h` used to create '-h/')."""
import argparse, os

MARKERS = ("requirements.md", "power_rails.csv", "pinmap.csv")


def design_dir(path):
    p = os.path.abspath(path)
    if not os.path.isdir(p):
        raise argparse.ArgumentTypeError(f"{path!r} is not an existing directory (the tools never create one)")
    missing = [m for m in MARKERS if not os.path.isfile(os.path.join(p, m))]
    if missing:
        raise argparse.ArgumentTypeError(f"{path!r} is not the project design/ directory (missing {', '.join(missing)})")
    return p
