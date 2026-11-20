# KiCad layout guide (phase H1, Rev A)

This is the order of work for laying out the board in KiCad, from install to the files JLCPCB needs.
[layout.md](layout.md) holds the rules (numbers, distances, zones). This guide tells you *when* to apply which section.
The tick list in layout.md §10 is the final check; don't skip it.

Written for KiCad 9 or newer on macOS. KiCad was not installed when this was written, so menu names and the generated
project files are **UNVERIFIED**. Each step says what to do by hand if a generated file doesn't load.

Plan on roughly 25–50 hours for a first board of this size. The SoC escape (step 6) is the hardest part.

---

## Step 0 — Install and learn the basics (1–3 h)

1. Install KiCad from https://www.kicad.org/download/macos/ (or `brew install --cask kicad`).
2. If you have never used the PCB editor, work through the official "Getting Started in KiCad" tutorial first (docs.kicad.org).
   You need these skills: move (M), rotate (R), flip (F), route (X), differential-pair route (6), add via (V), fill zones (B), DRC.
3. Optional: in Plugin and Content Manager, install the **JLCPCB Tools** (Bouni) plugin. It exports the BOM and CPL in
   JLC's format (step 10). Kept optional because it is third-party.

## Step 1 — Make the starter project (5 min)

```bash
design/.venv/bin/python -I design/tools/make_kicad_project.py design
```

This writes `design/kicad/rv1106-reva/`:

| File | What it gives you | If KiCad rejects it |
|---|---|---|
| `rv1106-reva.kicad_pro` | 18 net classes (widths, clearances, diff-pair sizes) and each sensitive net assigned to its class | Board Setup › Net Classes: create the classes by hand from `layout/netclasses.csv` |
| `rv1106-reva.kicad_dru` | custom DRC rules (KiCad loads `<project>.kicad_dru` automatically) | Board Setup › Custom Rules: paste `layout/board.kicad_dru`, press "Check rule syntax", fix what it reports |
| `fp-lib-table` | project footprint library `board` → `board.pretty/` | Preferences › Manage Footprint Libraries › Project Specific: add nickname `board`, path `${KIPRJMOD}/board.pretty` |
| `place_parts.py` | puts every footprint at its fixed spot or inside its zone | place by hand from `layout/placement.csv` |
| `board.pretty/README.md` | the list of custom footprints still to draw | — |

Open `rv1106-reva.kicad_pro` in KiCad. There is no schematic, only the netlist, so you'll work in the **PCB Editor** only.
Ignore warnings about a missing schematic.

## Step 2 — Board setup (30 min) → layout.md §2, §3, §10 "Setup"

In the PCB Editor, open File › Board Setup:

1. **Board Stackup › Physical Stackup:** set 4 copper layers, then enter the thicknesses and Er values of layout.md §2.1.
   Total thickness 1.6 mm, copper finish ENIG.
2. **Design Rules › Constraints:** min track 0.10, min clearance 0.10, min via 0.5 / hole 0.3, hole-to-hole 0.45,
   copper-to-edge 0.40 mm. (The starter project tries to set these; check them.)
3. **Net Classes:** check that 18 classes exist (Default, ETH_DIFF, USB_DIFF, XTAL, SENSE, SW_NODE, PWR_*, …) and that
   the assignments list has 76 nets. Spot-check: `ETH_TXP` → ETH_DIFF, `OSC_XIN` → XTAL.
4. **Custom Rules:** press "Check rule syntax". The rules were written without KiCad to test them. If a rule fails, fix
   its syntax (layout.md §4 has what each rule means), don't delete it.
5. **Cross-check impedance** with JLC's calculator (https://jlcpcb.com/impedance, JLC04161H-7628, outer layer, coplanar
   off): ETH 100 Ω differential → about 0.235 mm / 0.200 mm gap, USB 90 Ω → about 0.255 / 0.150. If JLC differs by more
   than 3 %, use JLC's numbers and note it in decisions.md.

## Step 3 — Draw the custom footprints (4–8 h) → layout.md §6.1, §6.4

Seven footprints aren't in KiCad's standard libraries. Open Footprint Editor, select library `board`, and use
File › New Footprint. Use exactly the names in `board.pretty/README.md`. **Pad numbers must match the netlist.** For
each footprint, check its pins against `schematic/out/pins.csv` before saving.

Do them in this order (hardest and most important first):

1. **RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm (U9).** Start from the KiCad Footprint Wizard's QFN generator (or copy
   `Package_DFN_QFN` QFN-128 if your version has a 12.3 mm / 0.35 mm one), then adjust to layout.md §6.1:
   - pads 0.19 × 0.75 mm, pitch 0.35, mask 1:1
   - EP 7.0 × 7.0 mm, pad 129
   - 16 thermal vias 0.3 / 0.5 mm placed per §6.2
   - paste on the EP as a 3 × 3 windowpane of 1.65 mm squares

   Check pin 1's position and the counting direction against [DS] Fig. 2-5 p.17. A mirrored QFN is the most expensive
   mistake on this board.
2. **USB_A_AF90_WJDG_RightAngle_THT (J4).** While drawing it, **decide which outer pin is VBUS** from the drawing and the
   part's pin-1 mark (layout.md §11 item 12). Write the answer in decisions.md. U8's position works for either side.
3. **microSD_TF-01A (J2).** Pad 9 = card detect, SH = shell tabs. Pad numbering against the drawing is the open item
   in layout.md §11 item 8: compare with the datasheet's contact list (DAT2, CD/DAT3, CMD, VDD, CLK, VSS, DAT0, DAT1).
4. **TI_RSE0010A_UQFN-10 (U11)**, **L_FHD4020S (L1–L4)**, **SW_TS-1187A (SW1–SW3**, pads 1–4 = A–D).
5. Fiducial: use `Fiducial:Fiducial_1mm_Mask2mm` if your KiCad has it, else draw one in `board`.

## Step 4 — Import the netlist (10 min)

1. File › Import › Netlist… → `design/schematic/out/board.net`.
2. Options: Link footprints by **reference**. Press **Update PCB**.
3. The report must show **226 footprints and 135 nets** and no "footprint not found" or "pad not found" error. A missing
   pad means a custom footprint's pad names are wrong: fix the footprint and import again.

## Step 5 — Outline, rails and holes (1 h) → layout.md §1

Coordinates in layout.md are from the board's north-west corner. Place that corner at **(50, 50) mm on the page** (the
same origin `place_parts.py` uses). Then set Place › Drill/Place File Origin and the Grid Origin to it.

1. Edge.Cuts: the board outline is 80 × 80 mm with 1 mm corner radius. Add the two 5 mm rails west and east, for a
   90 × 80 mm panel. JLC's exact way of marking V-cuts is still open (layout.md §11 item 2). Draw the V-cut lines at
   x = 0 and x = 80 on a User layer named `V-CUT`, and ask JLC in the order remark (layout.md §8).
2. 4 × M3 holes (3.2 mm NPTH) at (3.5, 3.5), (76.5, 3.5), (3.5, 76.5), (76.5, 76.5), each with a 7 mm keep-out on all layers.
3. 3 global fiducials and 4 tooling holes on the rails, and 2 local fiducials near the SoC, at the positions in layout.md §1.

## Step 6 — Placement (8–15 h) → layout.md §5, §6

1. Tools › Scripting Console, then run:
   ```
   exec(open(r"<full path>/design/kicad/rv1106-reva/place_parts.py").read())
   ```
   It moves the 6 connectors, U9, U8, JP1 and R30 to their fixed positions and drops every other part inside its zone.
   It doesn't rotate small parts or arrange them sensibly; that's your job. If the script fails, place by hand from
   `layout/placement.csv` (zone column) and `layout/zones.csv` (zone rectangles). Turn on a user drawing of the zone
   rectangles if that helps.
2. **Check connector orientation in the 3D viewer (Alt+3):** RJ45 mouth north; USB-C, USB-A and microSD mouths south.
   Nothing may overhang the west or east edge (that's where the rails break off).
3. **SoC first.** U9 pin 1 at the south-west corner. Then ring 1 (every 100 nF decoupler ≤ 3 mm from its pin), then
   the crystals (Y1 ≤ 3 mm from pins 68/69), then ring 2. The target pad of every SoC-side part is in the `target`
   column of placement.csv.
4. **Power column (east):** four buck cells north → south U6, U7, U4, U5, each laid out like the TLV62569 datasheet's
   layout example: input cap tight on VIN/GND, inductor ≤ 3 mm from SW, feedback divider on the quiet side.
5. **Power entry (south-east):** USB-C → fuse → TVS → Q1, the LTC2954 (U3) with SW1 beside it.
6. Then Ethernet links, NAND, SD power, header pull-ups, UART, LEDs and buttons, test pads.
7. Rule of thumb: if a zone feels too full, move a part to a neighbouring zone. Note it in decisions.md and rerun
   `check_layout.py`, as layout.md §5.1 says.

## Step 7 — Routing (10–20 h) → layout.md §4, §2.3, §7

Route in this order; each item is a section of layout.md §4:

1. **Planes first:** L2 is one solid GND zone (never route on it). On L3, draw the power regions of `layout/planes.csv`:
   the VDD_0V9 island under the SoC with its neck to JP1, VCC_3V3, VCC5V0_SYS and VBUS_USBA, plus GND fill elsewhere.
   L1 and L4 get GND pours.
2. **SoC escape:** fan out every SoC pad. Inner rows go to vias (0.3 / 0.5 mm); power pins go straight down to the L3 island.
3. **Crystals** (§4.3): short, guarded by GND, nothing else nearby.
4. **Ethernet** (§4.2): use the diff-pair router (key 6), L1 only, no vias, ≤ 30 mm including the `_J` segment after
   each 0 Ω link. KiCad may not see `ETH_TXP_J`/`ETH_TXN_J` or `USB_DP`/`USB_DM` as pairs (§10). If the 6 key
   refuses, route both tracks side by side with the gap from §2.2 and measure.
5. **USB** (§4.6): same method, 90 Ω geometry.
6. **SDMMC and SPI NAND** (§4.4): length-match each line to its clock within ±5 mm. KiCad's length tuner is key 7.
7. **Buck loops and feedback** (§4.5): short SW nodes, feedback away from inductors.
8. Everything else, low-speed signals on L4 where L1 is crowded.
9. **GND stitching vias** (§7): a ≤ 5 mm grid, rows along both sides of the diff pairs, and a ring along the board edge.

Press B (fill zones) often, and run DRC after every major step, not only at the end.

## Step 8 — Final checks (2–4 h)

1. DRC (Inspect › Design Rules Checker) with "Test for parity between PCB and schematic" **off** (there is no
   schematic). Target: 0 errors and 0 unconnected items. Explain each remaining warning in decisions.md.
2. Go through **every box in layout.md §10**.
3. 3D viewer: nothing on the bottom side, no collisions, connector mouths on the edges.
4. Silkscreen: TP labels, pin-1 marks, button and LED names, "Rev A".

## Step 9 — Ask for a review before ordering

Save, then tell Claude in this session that the layout is ready. Claude will read `rv1106-reva.kicad_pcb` and check:

- the placement and parameters against layout.md
- the DRC report
- the parts' positions against `check_layout.py`'s rules

The files are plain text, so no KiCad is needed for that review.

## Step 10 — Manufacturing files (H2) → `pcb/fab/order-notes.md` (D-132)

The fabrication files are made by script, not in the GUI: `sh design/pcb/scripts/l6_run.sh` (also the last step of
`rebuild_all.sh`) writes everything to `design/pcb/fab/` and runs the self-check (`fab/check_fab.txt`).

1. Upload `fab/rv1106-reva-jlc-upload.zip` (Gerbers + drill + job file), then `fab/jlc-bom.csv` and `fab/jlc-cpl.csv`.
2. Fill the order form from `fab/order-notes.md` (fields, remark text, things to check in the DFM and parts preview).
3. In JLC's placement preview, tick every row of `fab/cpl-rotations.md` (the rotation corrections are UNVERIFIED);
   check the RV1106G3 stock (>= 4) and read the live total before paying (estimate $370.82, cap $380, POFV not costed).

   Paying is your step.

**Never run "Update footprints from library" / "Update PCB from schematic" with footprint replacement on this board:**
152 footprints were edited on purpose (U9 `_EPboardvias` variant without drilled EP pads, silk), and the board is
rebuilt only by `rebuild_all.sh`.
