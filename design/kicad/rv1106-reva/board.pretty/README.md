# Custom footprints to draw (library `board`)

Draw each in KiCad's Footprint Editor and save it here with exactly this name. Pad names must match
decision D-74 (the netlist import reports a missing pad otherwise). Sources are under `design/refs/`.

| Footprint name | Used by | Draw from |
|---|---|---|
| `RV1106_QFN-128-1EP_12.3x12.3mm_P0.35mm` | U9 | layout.md §6.1 + §6.2 (pads, EP, thermal vias, paste windowpane); [DS] r1.8 Fig. 2-5 p.17 |
| `TI_RSE0010A_UQFN-10_1.5x2mm_P0.5mm` | U11 | refs/ts3usb221a-datasheet, RSE0010A land pattern |
| `L_FHD4020S_4.0x4.0mm` | L1-L4 | refs/fhd4020s-datasheet (image-only drawing) |
| `SW_TS-1187A_5.1x5.1mm` | SW1-SW3 | refs/ts-1187a-datasheet p.1 'P.C.B LAYOUT'; pads 1=A 2=B 3=C 4=D |
| `microSD_TF-01A` | J2 | refs/tf-01a-datasheet p.1; pad 9 = card detect, SH = shell tabs |
| `USB_A_AF90_WJDG_RightAngle_THT` | J4 | refs/usb-a-af90-wjdg-datasheet p.1; pad 1 VBUS .. 4 GND, SH = shell |

Fiducials: if `Fiducial:Fiducial_1mm_Mask2mm` is not in your KiCad libraries, draw one here as
`Fiducial_1mm_Mask2mm` (1.0 mm round copper pad, 2.0 mm mask opening, no paste), layout.md §1.
