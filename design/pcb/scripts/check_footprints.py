#!/usr/bin/env python3
"""Gate TP-L1 check: load every custom footprint of design/pcb/board.pretty with pcbnew and assert

  F1  every pad name the netlist (schematic/out/pins.csv) uses for that footprint exists; no extra named pads
  F2  dimensions match an independent table of expected values typed from the drawings (EXPECTED below)
  F3  min copper gap between pads of different names >= 0.15 mm ([JLC-CAP] SMD pad to pad 0.15; D-85 / §6.1 QFN 0.16)
  F4  solder-mask web between openings >= 0.10 mm ([JLC-CAP] "Soldermask bridge 0.10mm" green), mask 1:1
  F5  silkscreen >= 0.15 mm from every pad / mask opening, line width >= 0.15 mm ([JLC-CAP] Legend, Pad To Silkscreen)
  F6  F.CrtYd present and enclosing all pads + body; F.Fab body outline present; Reference on F.SilkS (>= 1.0 mm),
      Value on F.Fab; a pin-1 silk mark (filled dot) exists
  F7  THT: drills as expected, annular ring >= 0.10 mm (vias) / >= 0.25 mm (connector pins)
  F8  QFN-128 extras: pin order / pin-1 corner per [DS] Fig.2-3/2-4, corner pad gaps >= 0.18 mm in x and y,
      16 thermal vias, paste windowpane 9 x 1.65 mm = 50 %, window edge >= 0.175 mm from via holes, perimeter
      paste area ratio >= 0.76 at a 0.10 mm stencil (D-85a)

Run with KiCad's Python:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        design/pcb/scripts/check_footprints.py
Exit code 0 = all checks pass.
"""
import csv
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, ".."))
LIB = os.path.join(PCB, "board.pretty")
SCH = os.path.normpath(os.path.join(PCB, "..", "schematic", "out"))
MM = 1e6
TOL = 0.0015

# ---- independent expected values (typed from the drawings; see design/pcb/footprints.md) ----------------------------
# Each: pad name -> (x, y, w, h) for spot-checked pads (positions relative to the footprint origin) and global facts.
EXPECTED = {
    "RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm": dict(
        named=set(str(i) for i in range(1, 130)),
        spots={"1": (-6.075, -5.425, 0.75, 0.19), "32": (-6.075, 5.425, 0.75, 0.19),
               "33": (-5.425, 6.075, 0.19, 0.75), "64": (5.425, 6.075, 0.19, 0.75),
               "65": (6.075, 5.425, 0.75, 0.19), "96": (6.075, -5.425, 0.75, 0.19),
               "97": (5.425, -6.075, 0.19, 0.75), "128": (-5.425, -6.075, 0.19, 0.75)},
        ep=(7.0, 7.0), vias=(16, 0.3, 0.5), paste_windows=(9, 1.65, 2.30), min_gap=0.16, body=(12.3, 12.3)),
    # L5G variant (D-119, D-129): the same land pattern, no drilled pads (the 16 thermal vias are GND board vias at
    # the same positions); the netlist names the base footprint, so F1 compares against its pins
    "RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm_EPboardvias": dict(
        named=set(str(i) for i in range(1, 130)), netlist_as="RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm",
        spots={"1": (-6.075, -5.425, 0.75, 0.19), "32": (-6.075, 5.425, 0.75, 0.19),
               "33": (-5.425, 6.075, 0.19, 0.75), "64": (5.425, 6.075, 0.19, 0.75),
               "65": (6.075, 5.425, 0.75, 0.19), "96": (6.075, -5.425, 0.75, 0.19),
               "97": (5.425, -6.075, 0.19, 0.75), "128": (-5.425, -6.075, 0.19, 0.75)},
        ep=(7.0, 7.0), vias=(0, 0.3, 0.5), paste_windows=(9, 1.65, 2.30), min_gap=0.16, body=(12.3, 12.3)),
    "TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm": dict(
        named=set(str(i) for i in range(1, 11)),
        spots={"1": (-0.6375, -0.75, 0.575, 0.30), "2": (-0.6375, -0.25, 0.575, 0.25), "3": (-0.6375, 0.25, 0.575, 0.25),
               "4": (-0.6375, 0.75, 0.575, 0.30), "5": (0.0, 0.86, 0.35, 0.63), "6": (0.6375, 0.75, 0.575, 0.30),
               "7": (0.6375, 0.25, 0.575, 0.25), "8": (0.6375, -0.25, 0.575, 0.25), "9": (0.6375, -0.75, 0.575, 0.30),
               "10": (0.0, -0.86, 0.35, 0.63)},
        span=(1.85, 2.35), min_gap=0.175, body=(1.5, 2.0)),
    "L_FHD4020S_4.0x4.0mm": dict(
        named={"1", "2"}, spots={"1": (-1.5, 0.0, 1.10, 3.7), "2": (1.5, 0.0, 1.10, 3.7)}, min_gap=1.9, body=(4.0, 4.0)),
    "SW_TS-1187A_5.1x5.1mm": dict(
        named={"1", "2", "3", "4"},
        spots={"1": (-3.0, -1.875, 1.0, 0.75), "2": (3.0, -1.875, 1.0, 0.75), "3": (-3.0, 1.875, 1.0, 0.75),
               "4": (3.0, 1.875, 1.0, 0.75)},
        courtyard=(7.5, 5.6), min_gap=2.25, body=(5.1, 5.1)),
    "microSD_TF-01A": dict(
        named={"1", "2", "3", "4", "5", "6", "7", "8", "9", "SH"},
        # relative positions in the drawing frame (cd contact = origin); checked after subtracting pad 9's position
        rel={"9": (0.0, 0.0, 0.70, 1.30), "8": (1.10, 0.0, 0.70, 1.30), "1": (8.80, 0.0, 0.70, 1.30),
             "SH@back-left": (-1.10, 0.85, 1.20, 1.40), "SH@back-right": (13.58, 0.85, 1.20, 1.40),
             "SH@front-left": (-1.10, 10.55, 1.20, 2.00), "SH@front-right": (14.42, 10.55, 1.20, 2.00)},
        npth=[(1.71, 10.85, 1.0), (9.71, 10.85, 1.0)], sh_count=4, min_gap=0.15, body=(14.80, 14.50)),
    "USB_A_AF90_WJDG_RightAngle_THT": dict(
        named={"1", "2", "3", "4", "SH"},
        rel={"1": (-3.5, 0.0), "2": (-1.0, 0.0), "3": (1.0, 0.0), "4": (3.5, 0.0),
             "SH@left": (-6.5, 2.4), "SH@right": (6.5, 2.4)},
        drills={"1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "SH": 2.3}, sh_count=2, min_gap=0.4, body=(14.30, 14.20)),
}

results = []


def check(cond, fpname, cid, msg):
    results.append((bool(cond), fpname, cid, msg))
    return cond


def pads_of(fp):
    out = []
    for p in fp.Pads():
        pos = p.GetPosition()
        sz = p.GetSize(pcbnew.F_Cu)
        attr = p.GetAttribute()
        out.append(dict(
            name=p.GetNumber(), x=pos.x / MM, y=pos.y / MM, w=sz.x / MM, h=sz.y / MM,
            circle=(p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE),
            drill=p.GetDrillSize().x / MM, attr=attr,
            cu=p.IsOnLayer(pcbnew.F_Cu), fmask=p.IsOnLayer(pcbnew.F_Mask), bmask=p.IsOnLayer(pcbnew.B_Mask),
            paste=p.IsOnLayer(pcbnew.F_Paste), npth=(attr == pcbnew.PAD_ATTRIB_NPTH),
            pth=(attr == pcbnew.PAD_ATTRIB_PTH), mmargin=p.GetLocalSolderMaskMargin(),
            zone=p.GetLocalZoneConnection()))
    return out


def rect_rect(a, b):
    dx = max(abs(a["x"] - b["x"]) - (a["w"] + b["w"]) / 2, 0)
    dy = max(abs(a["y"] - b["y"]) - (a["h"] + b["h"]) / 2, 0)
    return math.hypot(dx, dy)


def pad_dist(a, b):
    """Edge-to-edge copper distance of two axis-aligned pads (rect or circle)."""
    if a["circle"] and b["circle"]:
        return max(math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - a["w"] / 2 - b["w"] / 2, 0)
    if a["circle"] or b["circle"]:
        c, r = (a, b) if a["circle"] else (b, a)
        dx = max(abs(c["x"] - r["x"]) - r["w"] / 2, 0)
        dy = max(abs(c["y"] - r["y"]) - r["h"] / 2, 0)
        return max(math.hypot(dx, dy) - c["w"] / 2, 0)
    return rect_rect(a, b)


def point_pad_dist(px, py, p, size=None):
    w, h = (p["w"], p["h"]) if size is None else size
    if p["circle"] or p["npth"]:
        return math.hypot(px - p["x"], py - p["y"]) - w / 2
    dx = max(abs(px - p["x"]) - w / 2, 0)
    dy = max(abs(py - p["y"]) - h / 2, 0)
    inside = abs(px - p["x"]) < w / 2 and abs(py - p["y"]) < h / 2
    return -1.0 if inside else math.hypot(dx, dy)


def silk_items(fp):
    items = []
    for g in fp.GraphicalItems():
        if g.GetLayer() != pcbnew.F_SilkS or not isinstance(g, pcbnew.PCB_SHAPE):
            continue
        items.append(g)
    return items


def silk_points(g):
    """Sample points (x, y, half_width) of a silk shape."""
    w = g.GetWidth() / MM
    st = g.GetShapeStr()
    pts = []
    if st == "Line":
        s, e = g.GetStart(), g.GetEnd()
        L = math.hypot(e.x - s.x, e.y - s.y) / MM
        n = max(int(L / 0.005), 1)
        for i in range(n + 1):
            pts.append(((s.x + (e.x - s.x) * i / n) / MM, (s.y + (e.y - s.y) * i / n) / MM, w / 2))
    elif st == "Circle":
        c = g.GetCenter()
        r = g.GetRadius() / MM
        filled = g.IsSolidFill() if hasattr(g, "IsSolidFill") else g.IsFilled()
        for i in range(72):
            a = 2 * math.pi * i / 72
            pts.append((c.x / MM + r * math.cos(a), c.y / MM + r * math.sin(a), w / 2))
        if filled:
            pts.append((c.x / MM, c.y / MM, r + w / 2))
    else:
        bb = g.GetBoundingBox()
        for (x, y) in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetBottom())):
            pts.append((x / MM, y / MM, 0))
    return pts


def layer_bbox(fp, layer):
    xs, ys, n = [], [], 0
    for g in fp.GraphicalItems():
        if g.GetLayer() == layer and isinstance(g, pcbnew.PCB_SHAPE):
            bb = g.GetBoundingBox()
            xs += [bb.GetLeft() / MM, bb.GetRight() / MM]
            ys += [bb.GetTop() / MM, bb.GetBottom() / MM]
            n += 1
    return (min(xs), min(ys), max(xs), max(ys), n) if n else None


def netlist_pads():
    fp_of = {}
    with open(os.path.join(SCH, "parts.csv")) as fh:
        for r in csv.DictReader(fh):
            fp_of[r["ref"]] = r["footprint"]
    used = {}
    with open(os.path.join(SCH, "pins.csv")) as fh:
        for r in csv.DictReader(fh):
            fpn = fp_of.get(r["ref"], "")
            if fpn.startswith("board:"):
                used.setdefault(fpn[6:], set()).add(r["pin"])
    refs = {}
    for ref, fpn in fp_of.items():
        if fpn.startswith("board:"):
            refs.setdefault(fpn[6:], []).append(ref)
    return used, refs


def near(a, b):
    return abs(a - b) <= TOL


def main():
    used, refs = netlist_pads()
    summary = {}
    for name, exp in EXPECTED.items():
        fp = pcbnew.FootprintLoad(LIB, name)
        if not check(fp is not None, name, "LOAD", "FootprintLoad"):
            continue
        pads = pads_of(fp)
        named = set(p["name"] for p in pads if p["name"])
        # ---- F1 netlist pad names --------------------------------------------------------------------------------
        nlname = exp.get("netlist_as", name)
        nl = used.get(nlname, set())
        check(nl, name, "F1", "footprint used in the netlist by %s%s" % (",".join(sorted(refs.get(nlname, []))),
                                                                        " (as %s)" % nlname if nlname != name else ""))
        check(nl <= named, name, "F1", "netlist pads present (missing: %s)" % sorted(nl - named))
        check(named == exp["named"], name, "F1", "named pads == expected set (extra: %s, missing: %s)" % (
            sorted(named - exp["named"]), sorted(exp["named"] - named)))
        check(named == nl, name, "F1", "no named pad without a netlist pin (extra: %s)" % sorted(named - nl))
        # ---- F2 dimensions ----------------------------------------------------------------------------------------
        by = {}
        for p in pads:
            by.setdefault(p["name"], []).append(p)
        for pn, (x, y, w, h) in exp.get("spots", {}).items():
            p = by[pn][0]
            ok = near(p["x"], x) and near(p["y"], y) and near(p["w"], w) and near(p["h"], h)
            check(ok, name, "F2", "pad %s at (%.3f, %.3f) %.3f x %.3f (expected %s)" % (pn, p["x"], p["y"], p["w"], p["h"], (x, y, w, h)))
        if "rel" in exp:
            ref_pad = by["9"][0] if "9" in by and name.startswith("microSD") else by["1"][0]
            ox, oy = (ref_pad["x"], ref_pad["y"]) if name.startswith("microSD") else (ref_pad["x"] + 3.5, ref_pad["y"])
            for key, v in exp["rel"].items():
                pn = key.split("@")[0]
                cands = [p for p in by.get(pn, []) if near(p["x"] - ox, v[0]) and near(p["y"] - oy, v[1])]
                ok = bool(cands) and (len(v) == 2 or (near(cands[0]["w"], v[2]) and near(cands[0]["h"], v[3])))
                check(ok, name, "F2", "pad %s at rel (%.2f, %.2f)%s" % (key, v[0], v[1], (" size %.2f x %.2f" % (v[2], v[3])) if len(v) > 2 else ""))
            if "npth" in exp:
                np_ = [p for p in pads if p["npth"]]
                for (x, y, d) in exp["npth"]:
                    ok = any(near(p["x"] - ox, x) and near(p["y"] - oy, y) and near(p["drill"], d) for p in np_)
                    check(ok, name, "F2", "NPTH Ø%.2f at rel (%.2f, %.2f)" % (d, x, y))
                if len(np_) == 2:
                    check(near(abs(np_[0]["x"] - np_[1]["x"]), 8.00), name, "F2", "locating holes 8.00 apart")
            if "sh_count" in exp:
                check(len(by.get("SH", [])) == exp["sh_count"], name, "F2", "%d SH pads" % exp["sh_count"])
        if "span" in exp:
            xs = [p["x"] - p["w"] / 2 for p in pads] + [p["x"] + p["w"] / 2 for p in pads]
            ys = [p["y"] - p["h"] / 2 for p in pads] + [p["y"] + p["h"] / 2 for p in pads]
            check(near(max(xs) - min(xs), exp["span"][0]) and near(max(ys) - min(ys), exp["span"][1]), name, "F2",
                  "land pattern span %.3f x %.3f (TI 1.85 x 2.35)" % (max(xs) - min(xs), max(ys) - min(ys)))
        if "drills" in exp:
            for p in pads:
                if p["name"] in exp["drills"]:
                    check(near(p["drill"], exp["drills"][p["name"]]), name, "F7", "pad %s drill %.2f" % (p["name"], p["drill"]))
            p1 = by["1"][0]
            check(p1["x"] < 0 and not p1["circle"], name, "F2", "pin 1 (VBUS) is the west outer pin, square pad (D-99)")
        fab = layer_bbox(fp, pcbnew.F_Fab)
        bw, bh = exp["body"]
        fab_ok = fab is not None and (near(fab[2] - fab[0], bw) or fab[2] - fab[0] >= bw - TOL) and (near(fab[3] - fab[1], bh) or fab[3] - fab[1] >= bh - TOL)
        check(fab_ok, name, "F6", "F.Fab body outline >= %.2f x %.2f (fab bbox %s)" % (bw, bh, fab and "%.2f x %.2f" % (fab[2] - fab[0], fab[3] - fab[1])))
        # ---- F3 / F4 gaps and mask web ----------------------------------------------------------------------------
        cu = [p for p in pads if (p["cu"] or p["pth"]) and not p["npth"]]
        mingap, pair = 1e9, None
        for i in range(len(cu)):
            for j in range(i + 1, len(cu)):
                if cu[i]["name"] == cu[j]["name"]:
                    continue
                d = pad_dist(cu[i], cu[j])
                if d < mingap:
                    mingap, pair = d, (cu[i]["name"], cu[j]["name"])
        check(mingap >= 0.15 - 1e-6, name, "F3", "min pad-to-pad copper gap %.3f mm (pads %s) >= 0.15" % (mingap, pair))
        check(mingap >= exp["min_gap"] - TOL, name, "F3", "min gap %.3f matches the drawing value %.3f" % (mingap, exp["min_gap"]))
        mk = [p for p in pads if p["fmask"]]
        margins = set(p["mmargin"] for p in mk)
        check(margins <= {None, 0}, name, "F4", "mask openings 1:1 (local margins %s; board default 0)" % sorted(str(m) for m in margins))
        minweb, wpair = 1e9, None
        for i in range(len(mk)):
            for j in range(i + 1, len(mk)):
                if mk[i]["name"] == mk[j]["name"] and mk[i]["name"]:
                    continue
                a, b = dict(mk[i]), dict(mk[j])
                for q in (a, b):
                    if q["npth"]:
                        q["w"] = q["h"] = q["drill"]
                        q["circle"] = True
                d = pad_dist(a, b)
                if d < minweb:
                    minweb, wpair = d, (mk[i]["name"], mk[j]["name"])
        check(minweb >= 0.10 - 1e-6, name, "F4", "min solder-mask web %.3f mm (%s) >= 0.10" % (minweb, wpair))
        # ---- F5 silk ------------------------------------------------------------------------------------------------
        sil = silk_items(fp)
        minsil, minw, dot = 1e9, 1e9, False
        for g in sil:
            minw = min(minw, g.GetWidth() / MM)
            if g.GetShapeStr() == "Circle":
                dot = True
            for (px, py, hw) in silk_points(g):
                for p in pads:
                    if not (p["fmask"] or p["cu"] or p["pth"]):
                        continue
                    size = (p["drill"], p["drill"]) if p["npth"] else None
                    minsil = min(minsil, point_pad_dist(px, py, p, size) - hw)
        check(sil and minsil >= 0.15 - 1e-6, name, "F5", "silk-to-pad clearance %.3f mm >= 0.15" % minsil)
        check(sil and minw >= 0.15 - 1e-6, name, "F5", "silk line width %.3f mm >= 0.15" % minw)
        check(dot, name, "F6", "pin-1 silk mark present")
        # ---- F6 courtyard, texts ----------------------------------------------------------------------------------
        crt = layer_bbox(fp, pcbnew.F_CrtYd)
        xs = [p["x"] - p["w"] / 2 for p in pads] + [p["x"] + p["w"] / 2 for p in pads] + [fab[0], fab[2]]
        ys = [p["y"] - p["h"] / 2 for p in pads] + [p["y"] + p["h"] / 2 for p in pads] + [fab[1], fab[3]]
        crt_ok = crt is not None and crt[0] <= min(xs) and crt[1] <= min(ys) and crt[2] >= max(xs) and crt[3] >= max(ys)
        check(crt_ok, name, "F6", "F.CrtYd present and encloses pads + body (%s)" % (crt and "%.2f x %.2f mm" % (crt[2] - crt[0] - 0.05, crt[3] - crt[1] - 0.05)))
        if "courtyard" in exp and crt:
            check(near(crt[2] - crt[0] - 0.05, exp["courtyard"][0]) and near(crt[3] - crt[1] - 0.05, exp["courtyard"][1]),
                  name, "F6", "courtyard %.2f x %.2f = D-84a %s" % (crt[2] - crt[0] - 0.05, crt[3] - crt[1] - 0.05, exp["courtyard"]))
        ref, val = fp.Reference(), fp.Value()
        check(ref.GetLayer() == pcbnew.F_SilkS and ref.GetTextHeight() / MM >= 1.0 - 1e-6 and ref.GetTextThickness() / MM >= 0.15 - 1e-6,
              name, "F6", "Reference on F.SilkS, %.2f mm high, %.2f mm stroke" % (ref.GetTextHeight() / MM, ref.GetTextThickness() / MM))
        check(val.GetLayer() == pcbnew.F_Fab and val.GetText() == name, name, "F6", "Value on F.Fab")
        smd = [p for p in pads if p["attr"] == pcbnew.PAD_ATTRIB_SMD and p["cu"]]
        check(all(p["fmask"] and (p["paste"] or p["name"] == "129") for p in smd), name, "F6",
              "every SMD copper pad has F.Mask and F.Paste (EP 129 gets paste from the windowpane)")
        # ---- F7 THT -----------------------------------------------------------------------------------------------
        for p in pads:
            if p["pth"]:
                ring = (min(p["w"], p["h"]) - p["drill"]) / 2
                lim = 0.10 if p["name"] == "129" else 0.25
                check(ring >= lim - 1e-6, name, "F7", "pad %s @(%.2f,%.2f) annular ring %.3f >= %.2f" % (p["name"], p["x"], p["y"], ring, lim))
        # ---- F8 QFN-128 ---------------------------------------------------------------------------------------------
        if name.startswith("RV1106"):
            qfn_checks(name, pads, by, exp)
        summary[name] = dict(pads=len(pads), named=len(named), mingap=mingap, minweb=minweb, minsil=minsil,
                             crt=crt and (crt[2] - crt[0] - 0.05, crt[3] - crt[1] - 0.05))
    # ---- report -----------------------------------------------------------------------------------------------------
    nfail = 0
    for ok, fpn, cid, msg in results:
        if not ok:
            nfail += 1
        print("%s %-3s %-40s %s" % ("PASS" if ok else "FAIL", cid, fpn[:40], msg))
    print()
    for n, s in summary.items():
        print("%-42s pads=%3d named=%3d min_gap=%.3f mask_web=%.3f silk_clr=%.3f courtyard=%.2f x %.2f" % (
            n, s["pads"], s["named"], s["mingap"], s["minweb"], s["minsil"], s["crt"][0], s["crt"][1]))
    print("\n%d checks, %d failed" % (len(results), nfail))
    return 1 if nfail else 0


def qfn_checks(name, pads, by, exp):
    P = lambda n: by[str(n)][0]
    # pin order: 1-32 west N->S, 33-64 south W->E, 65-96 east S->N, 97-128 north E->W ([DS] p.16)
    ok = all(near(P(i)["x"], -6.075) and near(P(i + 1)["y"] - P(i)["y"], 0.35) for i in range(1, 32))
    ok &= all(near(P(i)["y"], 6.075) and near(P(i + 1)["x"] - P(i)["x"], 0.35) for i in range(33, 64))
    ok &= all(near(P(i)["x"], 6.075) and near(P(i)["y"] - P(i + 1)["y"], 0.35) for i in range(65, 96))
    ok &= all(near(P(i)["y"], -6.075) and near(P(i)["x"] - P(i + 1)["x"], 0.35) for i in range(97, 128))
    check(ok, name, "F8", "pins counter-clockwise from the top: 1-32 W (N->S), 33-64 S (W->E), 65-96 E (S->N), 97-128 N (E->W)")
    check(P(1)["x"] < 0 and P(1)["y"] < 0 and P(128)["x"] < 0 and P(128)["y"] < 0, name, "F8",
          "pin 1 and pin 128 meet at the NW (pin-1) corner ([DS] Fig.2-3 top view)")
    for (a, b) in ((1, 128), (32, 33), (64, 65), (96, 97)):
        pa, pb = P(a), P(b)
        gx = abs(pa["x"] - pb["x"]) - (pa["w"] + pb["w"]) / 2
        gy = abs(pa["y"] - pb["y"]) - (pa["h"] + pb["h"]) / 2
        check(gx >= 0.18 - TOL and gy >= 0.18 - TOL, name, "F8", "corner pads %d/%d gap x %.3f y %.3f >= 0.18 (diag %.3f)" % (a, b, gx, gy, math.hypot(gx, gy)))
    inner = min(min(abs(p["x"]) - p["w"] / 2, abs(p["y"]) - p["h"] / 2) if False else (abs(p["x"]) - p["w"] / 2 if p["w"] > p["h"] else abs(p["y"]) - p["h"] / 2)
                for p in pads if p["name"] not in ("129", "") and p["cu"])
    outer = max(abs(p["x"]) + p["w"] / 2 if p["w"] > p["h"] else abs(p["y"]) + p["h"] / 2 for p in pads if p["name"] not in ("129", "") and p["cu"])
    check(near(inner, 5.70) and near(outer, 6.45), name, "F2", "perimeter pads from %.3f to %.3f mm (layout.md §6.1: 5.70-6.45)" % (inner, outer))
    ep = [p for p in by["129"] if p["attr"] == pcbnew.PAD_ATTRIB_SMD]
    check(len(ep) == 1 and near(ep[0]["w"], 7.0) and near(ep[0]["h"], 7.0) and ep[0]["fmask"] and not ep[0]["paste"],
          name, "F2", "EP 129 7.0 x 7.0, mask opening, no paste on the pad")
    vias = [p for p in by["129"] if p["pth"]]
    nv = exp["vias"][0]
    check(len(vias) == nv and all(near(v["drill"], 0.3) and near(v["w"], 0.5) for v in vias), name, "F2",
          "%d thermal vias 0.3/0.5 named 129 (expected %d)" % (len(vias), nv))
    if nv == 0:
        # board vias 0.3 / 0.5 at the layout.md §6.2 thermal-via positions stand in for the paste-window check
        vias = [dict(x=x, y=y, drill=0.3, w=0.5, fmask=False, bmask=False)
                for (x, y) in [(sx * 1.15, y) for sx in (-1, 1) for y in (-2.3, -1.15, 0.0, 1.15, 2.3)] +
                [(x, sy * 1.15) for sy in (-1, 1) for x in (-2.3, 0.0, 2.3)]]
    check(all(not v["fmask"] and not v["bmask"] for v in vias), name, "F2", "thermal vias have no own mask opening (tented on the bottom)")
    check(all(abs(v["x"]) + 0.25 <= 3.5 and abs(v["y"]) + 0.25 <= 3.5 for v in vias), name, "F2", "thermal vias inside the EP")
    zc = set(p["zone"] for p in by["129"])
    check(zc == {pcbnew.ZONE_CONNECTION_FULL}, name, "F2", "pad 129 copies connect solid to zones (no thermal relief)")
    win = [p for p in pads if p["name"] == "" and p["paste"] and not p["cu"]]
    n, s, pitch = exp["paste_windows"]
    xs = sorted(set(round(p["x"], 3) for p in win))
    check(len(win) == n and all(near(p["w"], s) and near(p["h"], s) for p in win) and
          len(xs) == 3 and near(xs[1] - xs[0], pitch), name, "F2", "paste windowpane %d x %.2f mm at %.2f pitch" % (len(win), s, pitch))
    cover = sum(p["w"] * p["h"] for p in win) / 49.0
    check(abs(cover - 0.50) < 0.01, name, "F8", "EP paste coverage %.1f %% (target 50 %%)" % (cover * 100))
    mind = min(point_pad_dist(v["x"], v["y"], dict(w, circle=False, npth=False)) - v["drill"] / 2 for v in vias for w in win)
    check(mind >= 0.175 - TOL, name, "F8", "paste window edge to via hole >= %.3f mm (>= 0.175)" % mind)
    t = 0.10
    peri = [p for p in pads if p["name"] not in ("129", "") and p["cu"]]
    ar = min(p["w"] * p["h"] / (2 * (p["w"] + p["h"]) * t) for p in peri)
    check(ar >= 0.76 - 0.005 and all(p["paste"] for p in peri), name, "F8", "perimeter paste 1:1, area ratio %.2f at a 0.10 mm stencil (>= 0.76, D-85a)" % ar)


if __name__ == "__main__":
    sys.exit(main())
