// RV1106G3 Linux board (Rev A) — 3D-printable enclosure
// Board data from xavigonzalvo/rv1106-linux-board: design/layout.md §1, layout/zones.csv,
// pcb/rv1106-reva.kicad_pcb (board coords = KiCad coords − (50, 50); +x east, +y SOUTH).
// Two parts: a tray (board sits on 4 standoffs, connectors through the walls) and a lid
// (header/UART openings, flexure power button, reset/maskrom pinholes, LED windows, vents).
// Four M3x20 socket-head screws go lid -> lid post -> PCB -> standoff (M3 heat-set insert).
//
// Render:  openscad -D 'part="tray"' -o tray.stl rv1106_case.scad   (also "lid", "assembly")

part = "assembly";          // "tray" | "lid" | "assembly" | "print" (both, laid out flat)

// ---------- board ----------
rails      = false;         // true if the 5 mm V-cut rails (west/east) are still attached
pcb_w      = 80;  pcb_h = 80;  pcb_t = 1.6;
rail       = rails ? 5 : 0;
holes      = [[3.5,3.5],[76.5,3.5],[3.5,76.5],[76.5,76.5]];   // 4 x M3, 3.2 mm NPTH

// ---------- case ----------
gap        = 0.6;           // board edge to inner wall
wall       = 2.0;
floor_t    = 2.0;
lid_t      = 2.0;
standoff_h = 5.0;           // room for through-hole pins under J3/J4/J5
standoff_d = 6.5;           // lid posts (top-side keep-out circle is 7.0 mm)
tray_sd    = 7.8;           // tray standoffs (bottom side of the board is empty)
insert_d   = 4.2;           // M3 heat-set insert (use 2.6 for self-tapping M3)
insert_l   = 5.0;
headroom   = 15.5;          // PCB top -> lid underside (RJ45 is 13.5 mm tall)
cbore_d    = 6.0;  cbore_l = 3.0;   // M3 socket head counterbore in the lid -> M3x20 screws
fit        = 0.25;          // lid lip clearance
$fn        = 48;

in_x0 = -rail - gap;           in_x1 = pcb_w + rail + gap;
in_y0 = -gap;                  in_y1 = pcb_h + gap;
pcb_z = floor_t + standoff_h;  // PCB bottom
top_z = pcb_z + pcb_t;         // PCB top
tray_h = top_z + headroom;     // tray wall top = lid underside

// Plane y: board +y is south. Model uses y_m = pcb_h - y so north is +Y in the viewer.
function P(p) = [p[0], pcb_h - p[1]];

// ---------- connector openings (board coords, z relative to PCB top) ----------
// north edge (y = 0): RJ45 J3, body ~16 x 13.5, centre x ≈ 17.0
// south edge (y = 80): microSD J2 card centre x 18.5 (kicad_pcb; zones.csv 19.5 is stale), USB-A J4 x 35.75, USB-C J1 x 49.5
module north_cut(xc, w, z0, z1) {
    translate([xc - w/2, pcb_h - 1, top_z + z0]) cube([w, wall + gap + 3, z1 - z0]);
}
module south_cut(xc, w, z0, z1, r = 0) {
    translate([xc, 0, 0]) translate([0, -(wall + gap) - 2, top_z + (z0 + z1)/2])
        rotate([-90, 0, 0]) linear_extrude(wall + gap + 3)
            offset(r = r) square([w - 2*r, z1 - z0 - 2*r], center = true);
}

module tray() {
    difference() {
        union() {
            // shell
            difference() {
                translate([in_x0 - wall, in_y0 - wall, 0])
                    rounded_box(in_x1 - in_x0 + 2*wall, in_y1 - in_y0 + 2*wall, tray_h, 3);
                translate([in_x0, in_y0, floor_t])
                    cube([in_x1 - in_x0, in_y1 - in_y0, tray_h]);
            }
            // standoffs
            for (h = holes) translate([P(h)[0], P(h)[1], 0])
                cylinder(d = tray_sd, h = pcb_z);
        }
        // insert holes
        for (h = holes) translate([P(h)[0], P(h)[1], pcb_z - insert_l - 1])
            cylinder(d = insert_d, h = insert_l + 2);           // 1 mm screw-tip relief

        // north: RJ45 (jack face + 0.4 all round)
        north_cut(17.02, 16.8, -0.4, 13.9);
        // south: microSD slot + finger scoop, USB-A, USB-C (plug overmold size)
        south_cut(18.5, 13.5, -0.3, 2.6);
        translate([18.5, in_y0 - wall - 0.01, top_z + 1.2])
            scale([1, 0.5, 0.55]) rotate([-90,0,0]) cylinder(d = 16, h = 2.4, $fn = 64);
        south_cut(35.75, 16.4, -0.6, 8.2, 0.6);   // USB-A and USB-C share one opening
        south_cut(49.5, 12.8, 1.63 - 3.7, 1.63 + 3.7, 2.4);
        south_cut(44.6, 2.2, 1.63, 1.63 + 3.7);              // remove cusp between USB-A and USB-C cuts
        // thin the south wall to 1.0 mm around both USB ports so plug boots seat fully
        translate([27.6, in_y0 - wall - 0.01, top_z - 2.5]) cube([29.4, 1.01, 12]);

        // floor vents under the SoC (≈ 34.5, 36.5) and buck converters
        for (i = [0:5]) translate([24 + i*4, P([0, 48])[1], -1]) slot(2, 22, floor_t + 2);
        for (i = [0:3]) translate([58 + i*4, P([0, 44])[1], -1]) slot(2, 26, floor_t + 2);

        // feet recesses (10 mm bumpons)
        for (x = [in_x0 + 12, in_x1 - 12], y = [in_y0 + 12, in_y1 - 12])
            translate([x, y, -0.01]) cylinder(d = 10.6, h = 0.8);
    }
}

module lid() {
    post_h = headroom;               // lid underside down to PCB top
    difference() {
        union() {
            translate([in_x0 - wall, in_y0 - wall, 0])
                rounded_box(in_x1 - in_x0 + 2*wall, in_y1 - in_y0 + 2*wall, lid_t, 3);
            // locating lip
            difference() {
                translate([in_x0 + fit, in_y0 + fit, -1.5])
                    cube([in_x1 - in_x0 - 2*fit, in_y1 - in_y0 - 2*fit, 1.5]);
                translate([in_x0 + fit + 1.6, in_y0 + fit + 1.6, -3])
                    cube([in_x1 - in_x0 - 2*fit - 3.2, in_y1 - in_y0 - 2*fit - 3.2, 4]);
            }
            // collars so the counterbore keeps >= 0.8 mm of wall
            for (h = holes) translate([P(h)[0], P(h)[1], -1.5]) cylinder(d = 7.6, h = 1.51);
            // clamp posts
            for (h = holes) translate([P(h)[0], P(h)[1], -post_h])
                cylinder(d = standoff_d, h = post_h + 0.01);
            // LED light-pipe tubes (stop 1 mm above the 0603 LEDs)
            hull() for (x = [60.0, 66.4]) translate([P([x, 3])[0], P([x, 3])[1], -(post_h - 1.8)])
                cylinder(d = 3.6, h = post_h - 1.8 + 0.01);
            // pinhole guides for RESET / MASKROM (stop 2.5 mm above the switch)
            for (x = [44.2, 53.0]) translate([P([x, 5.2])[0], P([x, 5.2])[1], -(post_h - 4.0)])
                cylinder(d = 4.4, h = post_h - 4.0);
        }
        // screw holes + counterbores
        for (h = holes) translate([P(h)[0], P(h)[1], 0]) {
            translate([0, 0, -post_h - 1]) cylinder(d = 3.4, h = post_h + lid_t + 2);
            translate([0, 0, lid_t - cbore_l]) cylinder(d = cbore_d, h = cbore_l + 1);
        }
        // 2x20 header J5 (pins x 3.0/5.54, y 9.56..57.82) — open so cables / boards plug in
        translate([P([0.6, 0])[0], P([0, 60.4])[1], -3]) rcube(7.9, 53.0, lid_t + 4, 1);
        // UART J6 (x 30.77..35.85, y 2.77)
        translate([P([28.6, 0])[0], P([0, 5.1])[1], -3]) rcube(9.4, 4.6, lid_t + 4, 1);
        // LED windows + RESET/MASKROM pinholes (paperclip)
        for (x = [60.0, 63.2, 66.4]) translate([P([x, 3])[0], P([x, 3])[1], -post_h]) cylinder(d = 2.5, h = post_h + 5);
        for (x = [44.2, 53.0]) translate([P([x, 5.2])[0], P([x, 5.2])[1], -post_h]) cylinder(d = 2.2, h = post_h + 5);
        // flexure for SW1 power (71.5, 60): U-slot tongue (hinge to the south), thinned to 1.0 mm
        translate([P([71.5, 60])[0], P([71.5, 60])[1], 0]) {
            translate([0, 0, -1]) linear_extrude(lid_t + 2) difference() {
                translate([-5.5, -12]) square([11, 17.8]);
                translate([-4.7, -12]) square([9.4, 17.0]);
            }
            translate([-4.8, -12.01, -1]) cube([9.6, 17.1, 2.0]);     // thin to 1.0 mm from inside
            translate([0, 0, lid_t - 0.4]) cylinder(d = 5, h = 1);   // finger dimple
        }
        // vents over the SoC and the PMU
        for (i = [0:5]) translate([24 + i*4, P([0, 48])[1], -1]) slot(2, 22, lid_t + 2);
        for (i = [0:3]) translate([58 + i*4, P([0, 44])[1], -1]) slot(2, 26, lid_t + 2);
        // label
        translate([P([20, 0])[0], P([0, 62])[1], lid_t - 0.5])
            linear_extrude(1) text("RV1106 Rev A", size = 4.5, font = "Liberation Sans:style=Bold");
    }
    // plunger under the flexure tongue -> SW1 (TS-1187A, 1.5 mm tall), 0.4 mm pre-travel gap
    translate([P([71.5, 60])[0], P([71.5, 60])[1], -(post_h - 1.9)])
        cylinder(d = 3.2, h = post_h - 1.9 + 1.5);   // fused into the 1.0 mm tongue
}

// ---------- helpers ----------
module rounded_box(w, d, h, r) {
    linear_extrude(h) translate([r, r]) offset(r = r) square([w - 2*r, d - 2*r]);
}
module rcube(w, d, h, r) { linear_extrude(h) translate([r, r]) offset(r = r) square([w - 2*r, d - 2*r]); }
module slot(w, l, h) { linear_extrude(h) hull() { translate([0, w/2]) circle(d = w); translate([0, l - w/2]) circle(d = w); } }

module pcb_ghost() {
    color("darkgreen", 0.8) translate([-rail, 0, pcb_z]) cube([pcb_w + 2*rail, pcb_h, pcb_t]);
    color("silver") translate([17.02 - 8, P([0, 21.3])[1], top_z]) cube([16, 21.3, 13.5]);   // RJ45
    color("silver") translate([35.75 - 7.25, 0, top_z]) cube([14.5, 14.2, 7.0]);             // USB-A
    color("silver") translate([49.5 - 4.5, 0, top_z]) cube([9, 7.3, 3.3]);                   // USB-C
    color("silver") translate([18.5 - 7.25, 0, top_z]) cube([14.5, 15.3, 1.9]);              // microSD
    color("black")  translate([1.8, P([0, 59.1])[1], top_z]) cube([5, 50.8, 8.5]);           // J5
}

if (part == "tray") tray();
else if (part == "lid") translate([0, 0, lid_t]) rotate([180, 0, 0]) lid();          // print lid top-down
else if (part == "print") { tray(); translate([in_x1 - in_x0 + 15, 0, 0]) rotate([180,0,0]) translate([0, -pcb_h, 0]) lid(); }
else { color("lightgray") tray(); pcb_ghost(); color("white", 0.5) translate([0, 0, tray_h]) lid(); }
