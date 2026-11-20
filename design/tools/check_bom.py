#!/usr/bin/env python3
"""Gate TP-D4 checks for design/bom.csv + cost model for N assembled boards.

Usage: .venv/bin/python -I tools/check_bom.py <design_dir> [--boards N] [--verbose]   (-h: help; D-70)
                 [--cost-limit USD] [--soc-stock-rule boards+K]
                 [--service std|econ] [--format single80|single70|panel1x2|frame60x50|single60x50]
Defaults = the gate TP-D4 as amended by the owner (decisions.md D-H2, PLAN.md Phase 4):
  --boards 2 (Rev A: 2 ASSEMBLED boards; the PCB estimate is for 5 PCBs = 2 assembled + 3 bare)
  --cost-limit 380 (PCB + Standard assembly + parts + shipping)
  --soc-stock-rule boards+2 (RV1106G3 only: JLCPCB stock >= boards + 2; every other part >= 100)
  --service std (JLCPCB Standard PCBA, D-61) --format single80 (80 x 80 mm board + rails, D-61, D-84 round 2)
Re-reads the cached raw LCSC JSON / JLCPCB HTML (refs/*-2026-10-29) independently of make_bom.py.
Exit code 0 only if every check passes. Any option that differs from the D-H2 defaults prints a banner: the result is
then a what-if scenario, not the gate.

Checks
  B1  every row has an LCSC code whose LCSC product-detail record exists and names the same MPN
  B2  JLCPCB stock (assembly source) >= 100 for every row; RV1106G3 only: >= boards + 2 (D-H2)  (LCSC stock reported)
  B3a footprint: the BOM footprint key's package token appears in the LCSC package string
  B3b the footprint name is an exact KiCad library name (cached listing refs/kicad-footprints-listing-2026-10-29),
      or a custom 'board:' footprint with a cited drawing
  B3c physical pad count of the footprint (re-counted from the cached .kicad_mod, stacked pads once) equals the BOM
      SMT+THT pad count; custom footprints use the drawing count recorded in make_bom.FP
  B3d the BOM pad count equals JLCPCB's solder-joint count for that part (jlcparts mirror, read-only) when listed
  B4  Basic/Extended column equals the JLCPCB componentLibraryType
  B5  design rules carried from earlier phases are present (R32 fitted, LTC2954, 4x TLV62569, Q_KILL, ...)
  B6  cost for N assembled boards (PCB + assembly + parts + shipping) <= limit. Line costs are RECOMPUTED here from the
      cached LCSC ladders for N boards (make_bom.line_price), not read from bom.csv, so any N is reproducible.
      A panel is assembled whole, so N rounds up to a multiple of the boards per panel ("assembled").
  B7a fine-pitch parts (< 0.8 mm): pitch >= the service's Minimum IC Pin Spacing (Econ 0.4 / Std 0.35 mm)
  B7b SMD parts with a cited peak reflow rating: rating >= service reflow temperature + 5 C (Econ 260 / Std 245 C);
      reflowed parts without a cited rating are listed as INFO (UNVERIFIED), THT parts are wave-soldered
  B7c the assembled unit (and a single board itself) meets the service's minimum size (Std 70 x 70 mm)
  B8  refmap.csv (functional / [LF] names -> BOM refs, D-63) equals the make_bom.py ref assignment
"""
import csv, json, os, re, sqlite3, sys

COST_LIMIT = 380.0          # D-H2: Rev A (2 assembled + 3 bare) <= $380
DEFAULT_BOARDS = 2          # D-H2: 2 assembled boards
DEFAULT_SOC_RULE = "boards+2"   # D-H2: SoC JLCPCB stock >= boards + 2 (rechecked by the owner on the order day)
PCBS_ORDERED = 5            # D-H2: 5 PCBs (JLCPCB minimum) = 2 assembled + 3 bare; FORMATS pcb_est is for 5 PCBs
HANDLING_MIN_DIFF = 14.93   # price page "Handling Fee": Std - Econ must be >= $14.93 when BOTH services are available
# ---- JLCPCB PCBA fees, refs/jlcpcb-assembly-price-2026-10-28/pcb-assembly-price.txt ("PCB Assembly Cost: What Does the
# Price Include?", https://jlcpcb.com/help/article/pcb-assembly-price, "Last updated on Oct 22, 2026"), fee table.
FEES = {
    # Economic PCBA (kept only for comparison: it CANNOT place the 0.35 mm pitch RV1106G3, see B7a / D-61)
    "econ": dict(setup=8.18, stencil=1.53, smt_joint=0.0016, manual_joint=0.0164, hand_labor=3.58,
                 ext_feeder=3.07, all_feeder=0.0, fixture=0.0, packing_base=0.0, packing_cm2=0.0,
                 confirm_placement=0.45),
    # Standard PCBA, single-side: setup $25.56, stencil $8.21, SMT $0.0016/joint (1-50,000), manual $0.0164/joint
    # (1-10,000) + $3.58 hand-soldering labour per order, feeder loading $1.53 for EVERY unique Basic/Extended part,
    # packing $0.50 + $0.00003 x PCB area (cm2), fixture (standard rigid PCB) 1-29 pcs: 2 fixtures -> $16.42.
    # The fixture row does not say which process needs it; THT parts are wave-soldered (capabilities FAQ), so it is
    # charged here conservatively: whether it applies to this order is UNVERIFIED until the real quote.
    "std": dict(setup=25.56, stencil=8.21, smt_joint=0.0016, manual_joint=0.0164, hand_labor=3.58,
                ext_feeder=0.0, all_feeder=1.53, fixture=16.42, packing_base=0.50, packing_cm2=0.00003,
                confirm_placement=0.45),
}
XRAY_LADDER = [(10, 1.64), (50, 0.82), (200, 0.49)]   # same ladder for both services (price page)
# ---- JLCPCB PCBA capabilities, refs/jlcpcb-assembly-capabilities-2026-10-28/pcb-assembly-capabilities.html, table
# "PCB Assembly Technical Capabilities" (https://jlcpcb.com/capabilities/pcb-assembly-capabilities):
# Minimum IC Pin Spacing Economic 0.4 mm / Standard 0.35 mm; Reflow temperature Economic 255 +/-5 C (not adjustable) /
# Standard 240 +/-5 C; size: Economic single 10x10-470x500 mm, panel 10x10-250x250; Standard single 70x70-460x500 mm,
# panel 70x70-250x250 mm; Minimum Package 0402 (Econ) / 01005 (Std).
SERVICE = {
    "econ": dict(name="Economic PCBA", min_pitch=0.40, reflow_max=255 + 5, min_xy=(10, 10)),
    "std": dict(name="Standard PCBA", min_pitch=0.35, reflow_max=240 + 5, min_xy=(70, 70)),
}
# ---- delivery formats (D-61). Standard PCBA needs edge rails and fiducials (capability table rows "Edge Rails" /
# "Fiducials": Economic "Not necessary", Standard "Necessary"), so every Standard unit carries 2 x 5 mm rails.
# board = PCB outline (mm), unit = what JLCPCB assembles (board(s) + rails), checked against the service minimum (B7c):
# a single board against "Single PCB Size", a panel/frame against "PCB Panel Size" (both 70 x 70 mm for Standard).
# pcb_est = 5 PCBs (or panels) 4-layer JLC04161H-7628 1.6 mm ENIG (D-62): ESTIMATE, UNVERIFIED (no quote form submitted).
FORMATS = {
    # D-84 round 2 (Phase 7): the board grew to 80 x 80 mm so the placement zones hold their courtyards at <= 55 % fill.
    # pcb_est scales the 70 x 70 ESTIMATE ($45 for an 80 x 70 panel) linearly with panel area: 45 x (90 x 80)/(80 x 70)
    # = 57.86 -> $58 (an upper bound if JLC prices by area; ESTIMATE, UNVERIFIED until the owner's live quote).
    "single80": dict(desc="80 x 80 mm board + 2 x 5 mm rails (unit 80 x 90 mm)", board=(80, 80), unit=(80, 90),
                     kind="single", per_panel=1, pcb_est=58.0),
    "single70": dict(desc="70 x 70 mm board + 2 x 5 mm rails (unit 70 x 80 mm)", board=(70, 70), unit=(70, 80),
                     kind="single", per_panel=1, pcb_est=45.0),
    "panel1x2": dict(desc="1x2 panel of 60 x 50 mm boards + 2 x 5 mm rails (unit 70 x 100 mm)", board=(60, 50),
                     unit=(70, 100), kind="panel", per_panel=2, pcb_est=50.0),
    "frame60x50": dict(desc="60 x 50 mm board, 1-up frame with rails to 70 x 70 mm (acceptance by JLCPCB UNVERIFIED)",
                       board=(60, 50), unit=(70, 70), kind="panel", per_panel=1, pcb_est=45.0),
    "single60x50": dict(desc="60 x 50 mm board, no frame (round-2 plan)", board=(60, 50), unit=(60, 50), kind="single",
                        per_panel=1, pcb_est=40.0),
}
SHIPPING = 35.0         # cheapest tracked courier to Europe for ~0.3-0.4 kg; ESTIMATE, UNVERIFIED
LEADLESS = {"QFN128", "WSON8", "UQFN10"}   # parts JLCPCB X-rays (QFN/leadless, price page)
# ---- B7a pitch for footprints whose pitch is not re-measured from a cached KiCad file (custom 'board:' footprints)
PITCH_CUSTOM = {
    "QFN128": (0.35, "RV1106 datasheet r1.8 p.14 'QFN128 (body: 12.3mm x 12.3mm pitch 0.35mm)'"),
    "UQFN10": (0.50, "TI SCDS277A p.23 RSE (R-PUQFN-N10) drawing, pitch 0,50"),
}
# ---- B7b peak reflow rating (deg C) of SMD parts with a cited rating; every other reflowed part is UNVERIFIED (INFO).
# THT parts (RJ45, USB-A, headers) are wave-soldered, not reflowed (capabilities FAQ), so they are not checked here.
REFLOW = {
    "C250087": (250, "Lelon 'Reflow Conditions for SMD Type' Cat. 2026E1 p.15, Test Conditions, OP-CAP column: peak 250 C"
                     " for 2 cycles (260 C for 1 cycle, <= 60 s above 230 C); refs/lelon-reflow-conditions-smd-2026-10-29"),
    "C883162": (260, "BHFUSE BSMD1812 datasheet p.6 reflow profile, Peak Temperature (Tp) 260 C"),
    "C141836": (260, "TI TLV62569 datasheet p.16 package option addendum 'Level-1-260C-UNLIM'"),
    "C128396": (260, "TI SCDS277A p.19 package option addendum 'Level-1-260C-UNLIM'"),
    "C55136": (260, "SY6280 AN Rev 0.1 p.2 abs. max 'Lead Temperature (Soldering, 10 sec.) 260 C' (lead temperature)"),
    "C683782": (300, "LTC2954 datasheet p.2 abs. max 'Lead Temperature (Soldering, 10 sec) 300 C' (lead temperature)"),
    "C22472329": (260, "W25N01KV p.49 note 2: J-STD-020C Pb-free compliant; 260 C is the J-STD-020 Pb-free small-body"
                       " class peak (value from the standard, UNVERIFIED in this datasheet)"),
}


def jlc_fields(design, code):
    p = os.path.join(design, "refs", "jlcpcb-partdetail-2026-10-29", f"{code}.html")
    try:
        s = open(p, encoding="utf-8", errors="replace").read().replace('\\"', '"')
    except OSError:
        return None, None
    lib = stock = None
    for m in re.finditer(r'"componentLibraryType":"(\w*)"', s):
        if '"componentCode":"' + code + '"' in s[max(0, m.start() - 6000): m.start()]:
            # D-71: only known values; anything else (e.g. a truncated 'bas') is reported as INVALID so B4 fails
            lib = {"base": "Basic", "expand": "Extended", "preferred": "Extended"}.get(m.group(1), f"INVALID({m.group(1)})")
            break
    for m in re.finditer(r'"overseasStockCount":(\d+)', s):
        if '"componentCode":"' + code + '"' in s[max(0, m.start() - 3000): m.start()]:
            stock = int(m.group(1)); break
    return lib, stock


def lcsc_rec(design, code):
    try:
        with open(os.path.join(design, "refs", "lcsc-api-2026-10-29", f"{code}.json"), encoding="utf-8") as f:
            r = json.load(f).get("result") or {}
        return r if r.get("productCode") == code else None
    except (OSError, ValueError):
        return None


def kicad_names(design):
    names = set()
    d = os.path.join(design, "refs", "kicad-footprints-listing-2026-10-29")
    for fn in os.listdir(d) if os.path.isdir(d) else []:
        if fn.endswith(".json"):
            lib = fn.rsplit("_p", 1)[0]
            try:
                for e in json.load(open(os.path.join(d, fn), encoding="utf-8")):
                    if e.get("name", "").endswith(".kicad_mod"):
                        names.add(lib + ":" + e["name"][:-len(".kicad_mod")])
            except ValueError:
                pass
    return names


def kicad_pads(design, fpname):
    """physical copper pads (smd, tht) of a cached KiCad footprint; pads at the same position and type count once"""
    lib, name = fpname.split(":", 1)
    p = os.path.join(design, "refs", "kicad-footprints-mods-2026-10-29", f"{lib}__{name}.kicad_mod")
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        return None
    pos = {"smd": set(), "thru_hole": set()}
    for m in re.finditer(r'\(pad "([^"]*)" (smd|thru_hole|np_thru_hole)\s+\w+\s+\(at ([-\d.]+) ([-\d.]+)', s):
        if m.group(2) in pos and m.group(1) != "":
            pos[m.group(2)].add((m.group(3), m.group(4)))
    return len(pos["smd"]), len(pos["thru_hole"])


def kicad_min_pitch(design, fpname):
    """smallest centre-to-centre distance between distinct SMD pad positions of a cached KiCad footprint (mm)"""
    lib, name = fpname.split(":", 1)
    p = os.path.join(design, "refs", "kicad-footprints-mods-2026-10-29", f"{lib}__{name}.kicad_mod")
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        return None
    pts = {(float(m.group(2)), float(m.group(3))) for m in
           re.finditer(r'\(pad "([^"]+)" smd\s+\w+\s+\(at ([-\d.]+) ([-\d.]+)', s)}
    pts = sorted(pts)
    d = [((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for i, a in enumerate(pts) for b in pts[i + 1:]]
    return round(min(d), 3) if d else None


def jlc_joints(design, code):
    p = os.path.join(design, "refs", "jlcparts-db-2026-10-29", "cache.sqlite3")
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        r = con.execute("select joints from jlc_components where lcsc = ?", (int(code[1:]),)).fetchone()
        con.close()
        return r[0] if r else None
    except sqlite3.Error:
        return None


def main():
    import argparse
    from designdir import design_dir
    ap = argparse.ArgumentParser(description="Gate TP-D4 (D-H2) checks for design/bom.csv and the Rev A cost model. "
                                 "Offline: reads only cached files. Non-default options print a WHAT-IF banner.")
    ap.add_argument("design", type=design_dir, help="the project design/ directory (must exist)")
    ap.add_argument("--boards", type=int, default=DEFAULT_BOARDS)
    ap.add_argument("--cost-limit", type=float, default=COST_LIMIT)
    ap.add_argument("--soc-stock-rule", default=DEFAULT_SOC_RULE, help="boards+K, or none (>= 100)")
    ap.add_argument("--service", choices=sorted(SERVICE), default="std")
    ap.add_argument("--format", choices=sorted(FORMATS), default="single80")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.soc_stock_rule != "none" and not re.fullmatch(r"boards\+\d+", a.soc_stock_rule):
        ap.error("--soc-stock-rule must be boards+K or none")
    if a.boards < 1:
        ap.error("--boards must be >= 1")
    design, boards, limit = a.design, a.boards, a.cost_limit
    soc_rule = None if a.soc_stock_rule == "none" else a.soc_stock_rule
    svc_key, fmt_key = a.service, a.format
    svc, fmt, fee = SERVICE[svc_key], FORMATS[fmt_key], FEES[svc_key]
    # boards actually assembled: a panel is assembled whole, so N rounds up to a multiple of per_panel
    units = -(-boards // fmt["per_panel"])
    assembled = units * fmt["per_panel"]
    print(f"service: {svc['name']}; format: {fmt_key} ({fmt['desc']}); boards wanted {boards}, assembled {assembled}")
    print(f"PCBs ordered: {max(PCBS_ORDERED, boards)} ({assembled} assembled + {max(PCBS_ORDERED, boards) - assembled} bare)")
    if (boards, limit, soc_rule, svc_key, fmt_key) != (DEFAULT_BOARDS, COST_LIMIT, DEFAULT_SOC_RULE, "std", "single80"):
        print(f"*** WHAT-IF SCENARIO, NOT THE D-H2 GATE: boards {boards}, cost limit {limit:.0f} USD, "
              f"SoC stock rule {soc_rule or '>= 100'}, service {svc_key}, format {fmt_key} ***")
    rows = list(csv.DictReader(open(os.path.join(design, "bom.csv"), encoding="utf-8")))
    unverified_reflow = []
    min_pitch_seen = []
    res = []
    from make_bom import FP, line_price  # same footprint table and price rule as the generator
    kn = kicad_names(design)

    def chk(cid, ok, msg):
        res.append((cid, ok, msg))

    for r in rows:
        code = r["lcsc"]
        rec = lcsc_rec(design, code)
        chk("B1", bool(rec) and rec.get("productModel") == r["mpn"],
            f"{code} {r['mpn']}: LCSC record {'found' if rec else 'MISSING'}"
            + (f", model {rec.get('productModel')}" if rec else ""))
        lib, jst = jlc_fields(design, code)
        lst = rec.get("stockNumber") if rec else None
        need = int(r['qty_per_board']) * assembled
        min_stock = 100
        if soc_rule and code == "C5328706":
            min_stock = need + int(soc_rule.split("+")[1])
        chk("B2", jst is not None and jst >= min_stock,
            f"{code} {r['mpn']}: JLCPCB stock {jst} (rule >= {min_stock}), LCSC stock {lst}, need {need} for {assembled} assembled boards")
        pkg = (rec or {}).get("encapStandard", "")
        fpname, tok, smt, tht, padsrc = FP[r["footprint_key"]]
        norm = lambda x: x.replace(" ", "").lower()
        chk("B3a", norm(tok) in norm(pkg), f"{code} {r['mpn']}: footprint {r['footprint_key']} token '{tok}' vs LCSC package '{pkg}'")
        chk("B3b", r["footprint"] == fpname and (fpname in kn if padsrc == "kicad" else fpname.startswith("board:")),
            f"{code}: footprint '{r['footprint']}' " + ("is an exact KiCad library name" if padsrc == "kicad"
                                                          else f"is custom, drawing: {padsrc}"))
        bom_pads = (int(r["smt_joints_per_part"]), int(r["tht_joints_per_part"]))
        if padsrc == "kicad":
            kp = kicad_pads(design, fpname)
            chk("B3c", kp == bom_pads, f"{code}: KiCad {fpname} has {kp} physical (SMD, THT) pads; BOM says {bom_pads}")
        else:
            chk("B3c", bom_pads == (smt, tht), f"{code}: custom footprint pads {bom_pads} = drawing count {(smt, tht)}")
        jj = jlc_joints(design, code)
        if jj is not None:
            chk("B3d", jj == sum(bom_pads), f"{code}: JLCPCB solder joints {jj} = BOM pads {sum(bom_pads)}")
        else:
            print(f"INFO B3d {code}: not in the jlcparts mirror; pad count rests on B3c only")
        # B7a pitch vs the service's minimum IC pin spacing
        if padsrc == "kicad":
            pt = kicad_min_pitch(design, fpname)
            psrc = f"min SMD pad centre spacing re-measured in cached {fpname}"
        else:
            pt, psrc = PITCH_CUSTOM.get(r["footprint_key"], (None, ""))
        if pt is not None and pt < 0.8:   # only fine-pitch multi-pin parts are relevant to the IC pin-spacing limit
            min_pitch_seen.append(pt)
            chk("B7a", pt >= svc["min_pitch"] - 1e-6,
                f"{code} {r['mpn']}: pitch {pt:.2f} mm vs {svc['name']} minimum {svc['min_pitch']:.2f} mm ({psrc})")
        # B7b reflow peak rating vs the service's reflow temperature (+5 C tolerance); SMD parts only
        if int(r["smt_joints_per_part"]) > 0:
            if code in REFLOW:
                pk, src = REFLOW[code]
                chk("B7b", pk >= svc["reflow_max"],
                    f"{code} {r['mpn']}: rated peak {pk} C >= {svc['name']} reflow max {svc['reflow_max']} C ({src})")
            else:
                unverified_reflow.append(code)
        chk("B4", r["basic_extended"] in ("Basic", "Extended") and lib == r["basic_extended"],
            f"{code}: BOM says {r['basic_extended']}, JLCPCB page says {lib} (only Basic/Extended accepted, D-71)")

    def has(code, minqty=1):
        return any(r["lcsc"] == code and int(r["qty_per_board"]) >= minqty for r in rows)
    desc = " ".join(r["description"] for r in rows)
    # D-68 (verifier P4 D-H2 major): no 0R chip in the VDD_0V9 / VDD_ARM path; VDD_ARM gets direct copper (NT_ARM) and
    # the U4 measurement point is a normally-closed solder jumper (JP_MEAS_0V9). C21189 = 1 PB + 3 meas + 1 NAND + 4 ETH.
    import make_bom
    zr = [p for p in make_bom.P if p["lcsc"] == "C21189"]
    bad = [p["role"][:60] for p in zr if p["block"] == "pmu" and ("VDD_0V9 (" in p["role"] or "VDD_ARM FITTED" in p["role"])]
    pmu_links = sum(p["qty"] for p in zr if p["block"] == "pmu")
    chk("B5", not bad and pmu_links == 3 and has("C21189", 9) and not has("C21189", 10)
        and any("NT_ARM" in d for d in make_bom.DNP) and any("JP_MEAS_0V9" in d for d in make_bom.DNP),
        f"VDD_0V9/VDD_ARM path has no 0R part: [LF] R32 -> copper NT_ARM, U4 link -> solder jumper JP_MEAS_0V9; "
        f"{pmu_links} pmu 0R links (VCC_1V8, VCC_3V3, VCC_DDR) (D-68)")
    chk("B5", has("C141836", 4), "4x TLV62569 (D-32)")
    chk("B5", has("C683782") or has("C683783"), "LTC2954 on/off controller (D-33/D-51)")
    chk("B5", has("C20917"), "Q_KILL logic-level N-FET (power.md §6.1)")
    chk("B5", has("C8545"), "Q_EN inverter for LTC2954-1 (D-51)")
    chk("B5", has("C23228", 2) and has("C17710") and "R_BL5" in desc, "bleeders 470R/1k/1k/680R/680R (D-42)")
    chk("B5", has("C162182") and has("C23630") and has("C1623"), "C65 150nF, C_PDT 2.2uF (D-117 c), C_GS 470nF (D-34/D-33/D-41)")
    chk("B5", has("C883162") and "2.01 A at 60 C" in desc, "F1 BSMD1812-300-16V, derated hold 2.01 A at 60 C >= 1.3 x 1.41 A (D-56)")
    chk("B5", "SY6280 VIN 10 uF" in desc and has("C96446", 5), "SY6280 VIN 10 uF ceramic (AN_SY6280 p.5, D-57)")
    chk("B5", has("C250087") and has("C45783"), "VBUS_USBA bulk 120 uF polymer + 22 uF = 142 uF >= 120 uF (D-58)")

    # ---- B7c assembled unit size vs the service's minimum (capabilities table "Dimension")
    chk("B7c", fmt["unit"][0] >= svc["min_xy"][0] and fmt["unit"][1] >= svc["min_xy"][1]
        and (fmt["kind"] == "panel" or fmt["board"] == fmt["unit"] or
             (fmt["board"][0] >= svc["min_xy"][0] and fmt["board"][1] >= svc["min_xy"][1])),
        f"{fmt_key}: board {fmt['board'][0]} x {fmt['board'][1]} mm, assembled unit {fmt['unit'][0]} x {fmt['unit'][1]} mm "
        f"({fmt['kind']}) vs {svc['name']} minimum {svc['min_xy'][0]} x {svc['min_xy'][1]} mm")
    if unverified_reflow:
        print(f"INFO B7b {len(unverified_reflow)} reflowed lines have no cited peak rating (UNVERIFIED; passives, "
              f"connectors, discretes, RV1106G3 MSL3 only): {' '.join(unverified_reflow)}")
    # ---- B8 the functional-name map (refmap.csv, D-63) matches the generator's ref assignment
    import make_refmap
    rm = make_refmap.render(make_refmap.build())
    chk("B8", os.path.exists(os.path.join(design, "refmap.csv"))
        and open(os.path.join(design, "refmap.csv"), encoding="utf-8").read() == rm,
        "refmap.csv (functional/[LF] name -> BOM ref) equals the make_bom.py ref assignment")
    bomrefs = {x for r in rows for x in r["ref"].split()}
    rm_lines = make_refmap.build()
    chk("B8", all(l["bom_ref"] in bomrefs for l in rm_lines if l["bom_ref"]), "every refmap.csv bom_ref exists in bom.csv")
    nop = {l["functional_name"] for l in rm_lines if not l["bom_ref"]}
    chk("B8", nop == {"JP_MEAS_0V9", "NT_ARM"}, f"refmap.csv no-part (copper) entries are exactly JP_MEAS_0V9, NT_ARM (D-68): {sorted(nop)}")
    meas = {l["functional_name"]: l["bom_ref"] for l in rm_lines if l["functional_name"].startswith("R_MEAS_")}
    chk("B8", sorted(meas) == ["R_MEAS_1V8", "R_MEAS_3V3", "R_MEAS_DDR"] and all(meas.values()),
        f"every buck measurement 0R link has a per-rail name (verifier minor): {meas}")
    rmap = make_refmap.build()
    lfnames = [l["luckfox_ref"] for l in rmap if l["luckfox_ref"]]
    chk("B8", len(lfnames) == len(set(lfnames)), "every [LF] designator in refmap.csv maps to exactly one BOM part")
    cited = set()
    for pr in csv.DictReader(open(os.path.join(design, "power_rails.csv"), encoding="utf-8")):
        txt = pr.get("c_soc_refs") or ""
        for m in re.finditer(r"\bC(\d+)(?:-C(\d+))?\b", txt):
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            cited.update(f"C{i}" for i in range(lo, hi + 1))
    missing = sorted(cited - set(lfnames), key=lambda x: int(x[1:]))
    chk("B8", not missing, f"every [LF] SoC-side capacitor cited in power_rails.csv c_soc_refs ({len(cited)}) has a "
        f"refmap.csv entry (D-65){'; missing: ' + ' '.join(missing) if missing else ''}")
    ncoll = sum(1 for l in rmap if l["lf_name_collision"])
    print(f"INFO B8 {ncoll} [LF] designators are also the bom.csv ref of a different part; refmap.csv column "
          f"lf_name_collision lists them. Rule (D-65): never write a bare [LF] designator; use '[LF] X' or 'NAME [bomref]'.")

    # ---- cost model (B6), for the ASSEMBLED board count
    lines = {}
    for r in rows:
        oq, unit = line_price(design, r["lcsc"], int(r["qty_per_board"]), r["footprint_key"], assembled)
        lines[r["lcsc"]] = (unit or 0.0) * oq
    parts = sum(lines.values())
    if str(assembled) == rows[0].get("costed_for_boards"):
        csv_parts = sum(float(r["line_cost_usd"] or 0) for r in rows)
        chk("B6", abs(csv_parts - parts) < 0.05, f"bom.csv line costs ({csv_parts:.2f}) = recomputed from cached ladders ({parts:.2f})")
    smt = sum(int(r["qty_per_board"]) * int(r["smt_joints_per_part"]) for r in rows) * assembled
    tht = sum(int(r["qty_per_board"]) * int(r["tht_joints_per_part"]) for r in rows) * assembled
    n_ext = sum(1 for r in rows if r["basic_extended"] != "Basic")
    xray_pcs = sum(int(r["qty_per_board"]) for r in rows if r["footprint_key"] in LEADLESS) * assembled
    xray = xray_pcs * next(p for lim, p in XRAY_LADDER if xray_pcs <= lim)
    area_cm2 = fmt["unit"][0] * fmt["unit"][1] / 100.0 * units

    def asm_items(f):
        return dict(setup=f["setup"], stencil=f["stencil"], smt=smt * f["smt_joint"],
                    manual=tht * f["manual_joint"] + (f["hand_labor"] if tht else 0),
                    feeders=n_ext * f["ext_feeder"] + len(rows) * f["all_feeder"], xray=xray,
                    fixture=f["fixture"] if tht else 0.0, packing=f["packing_base"] + f["packing_cm2"] * area_cm2,
                    confirm=f["confirm_placement"])
    items = asm_items(fee)
    # Handling fee (price page, "Handling Fee"): only "when both Economic PCBA and Standard PCBA are available for the
    # same order" and Std - Econ < $14.93. Economic is available only if every fine-pitch part meets its 0.40 mm minimum.
    econ_ok = all(p >= SERVICE["econ"]["min_pitch"] - 1e-6 for p in min_pitch_seen)
    diff = sum(asm_items(FEES["std"]).values()) - sum(asm_items(FEES["econ"]).values())
    items["handling"] = max(0.0, HANDLING_MIN_DIFF - diff) if (svc_key == "std" and econ_ok) else 0.0
    print(f"INFO handling fee: Economic available for this BOM: {econ_ok} (min fine pitch "
          f"{min(min_pitch_seen) if min_pitch_seen else 'n/a'} mm); Std - Econ assembly difference {diff:.2f} USD "
          f"(rule >= {HANDLING_MIN_DIFF}); handling fee charged {items['handling']:.2f} USD")
    asm = sum(items.values())
    total = parts + asm + fmt["pcb_est"] + SHIPPING
    soc = lines.get("C5328706", 0.0)
    cost = dict(service=svc_key, format=fmt_key, boards=boards, assembled=assembled,
                pcbs_ordered=max(PCBS_ORDERED, boards), parts=round(parts, 2),
                soc_only=round(soc, 2), smt_joints=smt, tht_joints=tht, extended_types=n_ext, unique_types=len(rows),
                xray_pcs=xray_pcs, assembly_items={k: round(v, 2) for k, v in items.items()}, assembly=round(asm, 2),
                pcb_est=fmt["pcb_est"], shipping_est=SHIPPING, total=round(total, 2))
    chk("B6", total <= limit, f"total for {assembled} assembled boards ({svc['name']}, {fmt_key}) = {total:.2f} USD "
        f"+ {max(PCBS_ORDERED, boards) - assembled} bare PCBs (limit {limit:.0f}); parts {parts:.2f} (of which RV1106G3 {soc:.2f}), assembly {asm:.2f}, "
        f"PCB {fmt['pcb_est']:.2f} (EST, ENIG), shipping {SHIPPING:.2f} (EST)")

    fails = [x for x in res if not x[1]]
    for cid, ok, msg in res:
        if not ok or a.verbose:
            print(f"{'PASS' if ok else 'FAIL'} {cid} {msg}")
    by = {}
    for cid, ok, _ in res:
        by.setdefault(cid, [0, 0])[0 if ok else 1] += 1
    print("summary:", ", ".join(f"{k} {v[0]} pass/{v[1]} fail" for k, v in sorted(by.items())))
    print("cost:", json.dumps(cost))
    print(f"RESULT: {len(res) - len(fails)} pass, {len(fails)} fail")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
