"""TP-D3 self-check for the power architecture (design/power.md + design/power_rails.csv). Round 3 + Phase-4 updates
(2026-10-29 D-68: P3L series-link drop/rating terms; VDD_0V9/VDD_ARM path without 0R chips)
(2026-10-29: D-54 cited ratings in power_rails.csv, F1 derating P5t (D-56), SY6280 VIN 10 uF in C_L (D-57)).
Usage:  <venv>/bin/python -I design/tools/check_power.py <design dir>
Reads only design/pinmap.csv and design/power_rails.csv (no downloaded files).
Every constant below is cited in power.md (section given per block); this script only does the arithmetic.
Output lines: PASS / FAIL (gate checks), REQ (a number that is a Phase-4 purchasing requirement, not a cited
rating: it is checked for internal consistency only and is NOT counted as a pass)."""
import csv, math, os, sys

D = sys.argv[1]
pins = list(csv.DictReader(open(os.path.join(D, "pinmap.csv"))))
rails = {r["rail"]: r for r in csv.DictReader(open(os.path.join(D, "power_rails.csv")))}
ok, err, req = [], [], []
def chk(cond, msg): (ok if cond else err).append(msg)
f = lambda x: float(x) if x not in ("", None) else None

# ---------------------------------------------------------------- P1/P2 supply pins (power.md §2)
sup = [p for p in pins if p["status"] == "POWER" and p["net"] != "GND"]
miss = [(p["pin"], p["net"]) for p in sup if p["net"] not in rails]
chk(not miss and len(sup) == 28, f"P1 all {len(sup)} SoC supply pins map to a rail in power_rails.csv (missing: {miss})")
nf = [(p["pin"], p["net"]) for p in sup if p["net"] in rails and f"({p['pin']})" not in rails[p["net"]]["feeds"]
      and not any(f"{p['pin']}," in s or f",{p['pin']})" in s for s in [rails[p['net']]["feeds"].replace(' ', '')])]
chk(not nf, f"P2 each rail's 'feeds' column names the SoC pins it supplies (not listed: {nf})")

# ---------------------------------------------------------------- P3 set-points (power.md §2; [TLV] p.4 VFB 0.588-0.612 V)
band = {}
for n, r in rails.items():
    if r["kind"] != "buck": continue
    rt, rb, vmin, vmax = f(r["r_top_k"]), f(r["r_bot_k"]), f(r["vref_min"]), f(r["vref_max"])
    lo = vmin * (1 + rt * 0.99 / (rb * 1.01)); hi = vmax * (1 + rt * 1.01 / (rb * 0.99))
    band[n] = (lo, hi)
    chk(f(r["ds_min_v"]) <= lo and hi <= f(r["ds_max_v"]),
        f"P3 {n}: Vout band {lo:.3f}-{hi:.3f} V (Vref ±2 %, 1 % resistors) within [DS] {r['ds_min_v']}-{r['ds_max_v']} V")
    chk(rb <= 200, f"P3 {n}: bottom resistor R2 = {rb:g} k <= 200 k ([TLV] §8.2.2.2 p.9)")
# P3L (Phase 4 D-68, verifier P4 D-H2 major): series links between a buck's feedback point and its loads.
# A 0R chip (UNI-ROYAL 0603WAF, LCSC C21189) is < 50 mohm and rated 1 A (datasheet V.9 p.5 §7 Ratings, 0603 row;
# refs/uniroyal-0603waf-datasheet/C21189.pdf): its drop (R_max x worst current) comes off the band low edge and its
# current must be <= rating / 1.3. Copper links (solder jumper, net-tie) are bounded by a computed resistance:
# 1 oz (35 um) outer copper, rho 1.72e-8 ohm m, bridge >= 0.6 mm wide x <= 1.0 mm long -> 0.82 mohm; budget 2 mohm
# (x2.4 for plating/solder variation, ESTIMATE). The U4..U7 feedback divider top taps the regulator side of the link
# (as [LF]; tapping after a cuttable jumper would open the loop when it is cut), so the drop is NOT regulated out.
# (rail fed, link, kind, R_max ohm, worst current A, rating A or None, upstream rail whose band applies, extra upstream links)
LINKS = [
    ("VDD_0V9", "JP_MEAS_0V9 (U4 out, NC solder jumper)", "copper", 0.002, f(rails["VDD_0V9"]["worst_a"]), None),
    ("VDD_ARM", "NT_ARM (VDD_0V9 -> VDD_ARM net-tie, [LF] R32)", "copper", 0.002, f(rails["VDD_ARM"]["worst_a"]), None),
    ("VCC_1V8", "R_MEAS_1V8 0R 0603 C21189", "0R", 0.050, f(rails["VCC_1V8"]["worst_a"]), 1.0),
    ("VCC_3V3", "R_MEAS_3V3 0R 0603 C21189", "0R", 0.050, f(rails["VCC_3V3"]["worst_a"]), 1.0),
    ("VCC_DDR", "R_MEAS_DDR 0R 0603 C21189", "0R", 0.050, f(rails["VCC_DDR"]["worst_a"]), 1.0),
]
drop = {}
for rail, name, kind, rmax, i, rating in LINKS:
    drop[rail] = rmax * i
    if rating is not None:
        chk(rating >= 1.3 * i, f"P3L {name}: {i:.3f} A <= rating {rating} A / 1.3 = {rating/1.3:.3f} A (UNI-ROYAL p.5 §7)")
chk(not any(k == "0R" for r_, _, k, *_ in LINKS if r_ in ("VDD_0V9", "VDD_ARM")),
    "P3L no 0R chip between U4 and the CPU/logic core pins (D-68)")
for rail in ("VCC_1V8", "VCC_3V3", "VCC_DDR"):
    lo_l = band[rail][0] - drop[rail]
    chk(lo_l >= f(rails[rail]["ds_min_v"]), f"P3L {rail}: low edge {band[rail][0]:.3f} V - link {drop[rail]*1e3:.1f} mV = "
        f"{lo_l:.3f} V >= [DS] {rails[rail]['ds_min_v']} V")
lo09 = band["VDD_0V9"][0] - drop["VDD_0V9"]
chk(lo09 >= f(rails["VDD_0V9"]["ds_min_v"]), f"P3L VDD_0V9 at the SoC: {band['VDD_0V9'][0]:.4f} V - "
    f"{drop['VDD_0V9']*1e3:.1f} mV jumper = {lo09:.4f} V >= {rails['VDD_0V9']['ds_min_v']} V")
lo, hi = band["VDD_0V9"]
lo_arm = lo - drop["VDD_0V9"] - drop["VDD_ARM"]
chk(0.85 <= lo_arm and hi <= 1.05, f"P3 VDD_ARM (= VDD_0V9 via jumper + net-tie, -{(drop['VDD_0V9']+drop['VDD_ARM'])*1e3:.1f} mV): "
    f"{lo_arm:.3f}-{hi:.3f} V within CPU_DVDD 0.85-1.05 V ([DS] r1.8 p.20 Table 3-2); PCB trace drop U4->SoC is a Phase 7 rule")
chk(band["VCC_3V3"][1] <= 3.465 - 0.05, f"P3 VCC_3V3 upper edge {band['VCC_3V3'][1]:.3f} V leaves >= 50 mV below 3.465 V for ripple/temperature")

# ---------------------------------------------------------------- P4 sub-rail currents
for n, r in rails.items():
    kids = [k for k in rails.values() if k["parent"] == n and k["kind"] == "subrail"]
    if kids:
        s = sum(f(k["worst_a"]) for k in kids)
        chk(s <= f(r["worst_a"]), f"P4 {n}: sub-rails draw {s:.3f} A <= rail worst-case {r['worst_a']} A")

# ---------------------------------------------------------------- P5 ratings >= 1.3 x worst-case (cited ratings only)
for n, r in rails.items():
    if r["kind"] in ("buck", "switch", "input") and r["rating_a"]:
        line = f"{n} ({r['device_ref']}): rating {r['rating_a']} A >= 1.3 x {r['worst_a']} A = {1.3*f(r['worst_a']):.2f} A"
        if r["rating_source"].startswith("REQUIREMENT"):
            (req if f(r["rating_a"]) >= 1.3 * f(r["worst_a"]) else err).append("P5 " + line + "  [Phase-4 requirement, not a cited rating]")
        else:
            chk(f(r["rating_a"]) >= 1.3 * f(r["worst_a"]), "P5 " + line)
# P5t (Phase 4, D-56): F1's rating above is its derated hold at the 60 C design ambient; at 70 C the BHFUSE chart
# (BSMD1812 Rev 2025 p.5, row BSMD1812-300) gives 1.61 A, which must still carry the worst case without tripping (>= 1.0x).
F1_HOLD_70C = 1.61
chk(F1_HOLD_70C >= f(rails["VBUS_5V"]["worst_a"]),
    f"P5t F1 BSMD1812-300 hold at 70 C {F1_HOLD_70C} A >= 1.0 x worst case {rails['VBUS_5V']['worst_a']} A "
    f"({F1_HOLD_70C / f(rails['VBUS_5V']['worst_a']):.2f}x; the 1.3x rule holds up to 60 C, D-56)")

# ---------------------------------------------------------------- P6 input power budget (power.md §5)
P5w = 0.0
for n, r in rails.items():
    if r["kind"] == "buck": P5w += f(r["nominal_v"]) * f(r["worst_a"]) / f(r["efficiency"])
R_G, R_GS = 47e3, 100e3                     # Q_PWR gate network (power.md §6.1, D-41)
direct_5v = {"VBUS_USBA + header 5 V pins, combined allowance (D-36)": 0.50,
             "USB_VBUSDET divider 10k+18k": 5.0 / 28e3, "Q_PWR gate divider R_GS+R_G (on)": 5.0 / (R_G + R_GS),
             "R_BL5 470 ohm bleeder on VCC5V0_SYS (D-42)": 5.0 / 470}
P5w += 5.0 * sum(direct_5v.values())
P_ctrl = 5.0 * 12e-6                        # LTC2954 IIN max 12 uA ([LTC] p.3)
I = (P5w + P_ctrl) / 5.0
for _ in range(6):                          # series losses fuse 0.10 ohm + Q_PWR 0.085 ohm ([AO] p.1, VGS -2.5 V row)
    P_in = P5w + P_ctrl + I * I * (0.10 + 0.085); I = P_in / 5.0
chk(P_in < 7.5, f"P6 worst-case input power {P_in:.2f} W ({I:.3f} A at 5 V) < 7.5 W")
chk(abs(I - f(rails["VBUS_5V"]["worst_a"])) < 0.03, f"P6b power_rails.csv input worst_a {rails['VBUS_5V']['worst_a']} A matches computed {I:.3f} A")

# ---------------------------------------------------------------- P9 Q_PWR gate network (power.md §6.1/§6.3, D-41)
C_GS, C_GD = 470e-9, 10e-9                  # gate-source, gate-drain (X7R ±10 %)
CISS, CRSS0 = 645e-12, 0.2e-9               # [AO] p.2 Ciss 645 pF; Crss 55 pF at VDS -15 V, taken as <= 0.2 nF at VDS ~ 0 (UNVERIFIED bound)
VTH_MIN, VTH_MAX = 0.5, 1.3                 # |VGS(th)| [AO] p.2
VPL = (0.5, 2.0)                            # |Miller plateau| bound (UNVERIFIED; Vth max + overdrive for <= 0.6 A, gFS 17 S [AO] p.2)
VOL = (0.0, 0.4)                            # LTC2954 EN-bar VOL max 0.4 V at 500 uA ([LTC] p.3)
I_LKG = 1e-6 + 0.1e-6                       # EN-bar leakage max 1 uA ([LTC] p.3) + IGSS 100 nA ([AO] p.2)
# VCC5V0_SYS capacitance bound: 4 x 10 uF buck inputs + 4 x 100 nF + 10 uF SY6280 VIN (D-57, AN_SY6280 p.5), +20 %.
# (Round 3 used 1 uF for the SY6280 input -> 50 uF.)  VBUS_USBA's 142 uF sits behind the SY6280, which is off at power-up
# (USBA_VBUS_EN 10k pull-down, D-20), so it is not part of C_L.
C_L = (4 * 10e-6 + 4 * 0.1e-6 + 10e-6) * 1.2
GFS = 17.0                                  # AO3401A forward transconductance ([AO] p.2)
INRUSH_MAX = 1.0                            # A: keeps the VPL upper bound valid (1.3 V + 1.0 A / 17 S = 1.36 V < 2.0 V) and
                                            # leaves >= 0.5 A of a 1.5 A source (D-36) for the always-on 5 V loads
cgd_hi, cgs_lo = C_GD * 1.1 + CRSS0, C_GS * 0.9
ctot = cgs_lo + CISS + cgd_hi
v_off_lkg = I_LKG * R_GS
chk(v_off_lkg <= 0.15, f"P9 off-state: EN-bar + gate leakage x R_GS = {v_off_lkg:.3f} V <= 0.15 V")
for vbus_pk, label in ((5.25, "step to 5.25 V"), (10.5, "step with 2x hot-plug overshoot 10.5 V")):
    vgs = vbus_pk * cgd_hi / ctot + v_off_lkg
    chk(vgs <= VTH_MIN - 0.1, f"P9 plug-in {label}: |VGS| <= {vgs:.3f} V < 0.5 V min threshold - 0.1 V margin (Q_PWR stays off)")
tau_plug = R_GS * ctot
for T in (10e-6, 100e-6, 1e-3):              # linear VBUS ramp 0 -> 5.25 V in T: |u| = R Cgd (V/T)(1 - e^-T/tau)
    u = R_GS * cgd_hi * (5.25 / T) * (1 - math.exp(-T / tau_plug)) + v_off_lkg
    chk(u <= VTH_MIN - 0.1, f"P9 plug-in ramp {T*1e6:.0f} us: |VGS| <= {u:.3f} V < 0.4 V")
v_on_min = (4.75 - VOL[1]) * R_GS / (R_GS + R_G)
v_on_max = (5.25 - VOL[0]) * R_GS / (R_GS + R_G)
chk(v_on_min >= 2.5, f"P9 on-state |VGS| >= {v_on_min:.2f} V >= 2.5 V (RDS(on) <= 85 mohm row, [AO] p.1); max {v_on_max:.2f} V < 12 V")
chk(5.25 / (R_G + R_GS) <= 500e-6, f"P9 EN-bar sink {1e6*5.25/(R_G+R_GS):.0f} uA <= 500 uA (VOL spec point)")
rth = R_G * R_GS / (R_G + R_GS)
ig_max = (v_on_max - VPL[0]) / rth; ig_min = (v_on_min - VPL[1]) / rth
dvdt_max = ig_max / (C_GD * 0.9); dvdt_min = ig_min / (C_GD * 1.1 + CRSS0)
inrush = C_L * dvdt_max
chk(ig_min > 0, f"P9 gate drive exceeds the plateau in every corner (I_G min {ig_min*1e6:.1f} uA)")
chk(inrush <= INRUSH_MAX and VTH_MAX + inrush / GFS <= VPL[1],
    f"P9 button-on inrush into {C_L*1e6:.1f} uF <= {inrush:.2f} A <= {INRUSH_MAX} A (VCC5V0_SYS dV/dt {dvdt_min/1e3:.1f}-{dvdt_max/1e3:.1f} V/ms); "
    f"plateau |VGS| <= {VTH_MAX + inrush / GFS:.2f} V stays inside the {VPL[1]} V bound used above")
P_ON = inrush * 5.25                         # worst instantaneous dissipation during the turn-on ramp (VDS <= VBUS)
chk(P_ON <= 13.0 * (150 - 70) / 125 and 5.25 / dvdt_min <= 0.010,
    f"P9 turn-on stress: <= {P_ON:.1f} W for <= {5.25/dvdt_min*1e3:.2f} ms, inside the [AO] Fig. 9 10 ms SOA derated to 70 C (8.3 W)")
ramp = (4.75 / dvdt_max, 5.25 / dvdt_min)    # VCC5V0_SYS ramp-time window (s)
t_off = R_GS * (C_GS * 1.1 + CISS + C_GD * 1.1 + CRSS0) * math.log(v_on_max / VTH_MIN)
chk(t_off < 0.200, f"P9 turn-off: gate back inside |VGS| < 0.5 V within {t_off*1e3:.0f} ms < tEN,LOCKOUT min 200 ms ([LTC] p.3)")
t_on_delay = rth * (C_GS * 1.1 + CISS + C_GD * 1.1) * math.log(v_on_min / (v_on_min - VTH_MAX))
# P9e turn-off stress (round 3, verifier minor): EN-bar is open at turn-off, so the gate leaves the Miller plateau only through
# R_GS: I_G = |Vpl| / R_GS = 5-20 uA.  Drain (VCC5V0_SYS) falls at I_G / C_GD while Q_PWR carries the load, down to the buck
# UVLO (taken as 2.1 V, below the 2.3 V typ falling threshold [TLV] p.4).  Load: the four bucks at constant input power
# (sum of P5w buck terms) + the 0.5 A USB-A/header allowance as constant current; C_L discharge current ignored (conservative).
P_bucks = sum(f(r["nominal_v"]) * f(r["worst_a"]) / f(r["efficiency"]) for r in rails.values() if r["kind"] == "buck")
V_UVLO_F = 2.1
toff_res = {}
for vpl in VPL:
    ig = vpl / R_GS
    for kc in (0.9, 1.1):
        dv = ig / (C_GD * kc + (CRSS0 if kc > 1 else 0))           # V/s
        n, E, Ppk = 2000, 0.0, 0.0
        V0 = 5.25; dV = (V0 - V_UVLO_F) / n
        for i in range(n):
            V = V0 - (i + 0.5) * dV
            P = (V0 - V) * (P_bucks / V + 0.50)
            E += P * dV / dv; Ppk = max(Ppk, P)
        toff_res[(vpl, kc)] = ((V0 - V_UVLO_F) / dv, E, Ppk)
t_lin = max(v[0] for v in toff_res.values()); E_off = max(v[1] for v in toff_res.values()); P_off = max(v[2] for v in toff_res.values())
# [AO] p.4 Fig. 9 (SOA, TA = 25 C, single pulse): the 10 ms line runs from ~12 A at 1.1 V to ~0.45 A at 30 V, i.e. ~13 W.
# Linear derating to TA = 70 C: x (150 - 70) / (150 - 25).  Fig. 10 gives ~13 W at 10 ms as well (read from the plot: ESTIMATE).
P_SOA10 = 13.0 * (150 - 70) / 125
chk(t_lin <= 0.010 and P_off <= P_SOA10,
    f"P9e turn-off: Q_PWR in its linear region <= {t_lin*1e3:.1f} ms, peak {P_off:.1f} W, energy <= {E_off*1e3:.1f} mJ; "
    f"rectangular {P_off:.1f} W x 10 ms is inside the [AO] Fig. 9 10 ms SOA line derated to TA 70 C ({P_SOA10:.1f} W)")

# ---------------------------------------------------------------- P7 sequencing (power.md §3, D-34 round 2)
VTH = (0.4, 1.2)                            # TLV62569 EN: VIL min 0.4 V .. VIH max 1.2 V ([TLV] p.4) - only guaranteed window
TSS = 0.9e-3                                # soft start: largest listed value ([TLV] p.4: 800 us DBV / 900 us DDC, DRL; no max given)
UVLO_R = (2.2, 2.6)                         # TLV UVLO rising window: 2.3 V typ/2.45 V max falling + 100 mV typ hysteresis (+/- margin, UNVERIFIED)
R14C77 = 200e3 * 100e-9                     # R14 200k / C77 100n from VCC5V0_SYS ([LF]) -> U5 + U7 EN
R43C65 = 201e3 * 150e-9                     # R41 1k + R43 200k / C65 150n from VCC_1V8 -> U6 EN (D-34 round 2)
DT = 2e-6
def en_time(src, rc, vth, t0=0.0, tmax=0.3):
    """first time an RC fed from src(t) crosses vth (Euler)."""
    v, t = 0.0, t0
    while t < tmax:
        t += DT; v += DT * (src(t) - v) / rc
        if v >= vth: return t
    return float("inf")
def t_at(vin, tr, level):                    # linear ramp of VCC5V0_SYS reaches level
    return tr * level / vin
res = {}
import itertools
for vin in (4.75, 5.25):
    for tr in (vin / dvdt_max, vin / dvdt_min, 20e-6):                  # fast / slow soft-start ramp, and an instant ramp
        v5 = (lambda vin, tr: (lambda t: vin * min(t / tr, 1.0)))(vin, tr)
        k = f"Vin={vin} ramp={tr*1e3:.2f} ms"
        # each regulator has its own (independent) EN threshold and UVLO: test every corner combination
        u4_good_late = t_at(vin, tr, UVLO_R[1]) + TSS                   # U4: EN = VCC5V0_SYS via R35 10k ([LF]) -> starts at UVLO
        # capacitor tolerance +/-10 % (X7R) on C77 (shared by U5 and U7) and on C65; resistors 1 % ignored (< C tolerance)
        first57, worstB, worstC = float("inf"), float("inf"), 0.0
        for k77 in (0.9, 1.1):
            en57 = {th: en_time(v5, R14C77 * k77, th) for th in VTH}
            start57 = {(th, uv): max(en57[th], t_at(vin, tr, uv)) for th in VTH for uv in UVLO_R}
            first57 = min(first57, min(start57.values()))
            for (th5, uv5), (th7, uv7), th6 in itertools.product(start57, start57, VTH):
                t5, t7 = start57[(th5, uv5)], start57[(th7, uv7)]
                # earliest U6 EN: VCC_1V8 an instant step to its max 1.861 V at t5, C65 at -10 %
                t6e = en_time(lambda t: 1.861 if t >= t5 else 0.0, R43C65 * 0.9, th6, t0=t5 - DT)
                worstB = min(worstB, t6e - (max(t5, t7) + TSS))
                # latest U6 EN: VCC_1V8 ramps to its min 1.741 V over tSS from t5, C65 at +10 %
                t6l = en_time(lambda t: 1.741 * min(max(t - t5, 0) / TSS, 1.0), R43C65 * 1.1, th6, t0=t5 - DT)
                worstC = max(worstC, t6l + TSS)
        chk(u4_good_late < first57, f"P7a {k}: VDD_0V9 good by {1e3*u4_good_late:.2f} ms < earliest U5/U7 EN {1e3*first57:.2f} ms")
        chk(worstB > 1e-3, f"P7b {k}: VCC_1V8 AND VCC_DDR good >= {1e3*worstB:.2f} ms before VCC_3V3 EN (> 1 ms), over all threshold/UVLO/capacitor corners (U5, U7, U6 independent)")
        chk(worstC + t_on_delay < 0.300, f"P7c {k}: VCC_3V3 (KILL pull-up, nPOR) good by {1e3*(worstC+t_on_delay):.1f} ms incl. Q_PWR turn-on delay < 300 ms (KILL blanking min 400 ms - 100 ms)")
        res[(vin, round(tr * 1e3, 2))] = (u4_good_late, first57, worstB, worstC)
i_tol = (1.741 - 1.2) / 201e3
chk(i_tol > 1e-6, f"P7d U6 EN settles >= 1.2 V from VCC_1V8 min 1.741 V with up to {i_tol*1e6:.1f} uA EN input current (not specified in [TLV]; UNVERIFIED)")

# ---------------------------------------------------------------- P11 restart after shortest off time (power.md §3, D-42 round 3)
t_gap = 0.200 + 0.026                       # tEN,LOCKOUT min + tDB,ON min ([LTC] p.3; Note 5: lockout excludes tDB,ON)
tau5 = (470 * 28e3 / (470 + 28e3)) * C_L    # R_BL5 || VBUSDET divider, C_L
def two_pole(v0, ta, tb, t):                # cap (tau tb) discharging into a node that itself decays with tau ta
    return v0 * (tb * math.exp(-t / tb) - ta * math.exp(-t / ta)) / (tb - ta)
t_rem = t_gap - t_off                       # conservative: VCC5V0_SYS held at 5.25 V until Q_PWR is fully off
v77 = two_pole(5.25, tau5, 200e3 * 110e-9, t_rem)
chk(v77 < VTH[0], f"P11 restart {t_gap*1e3:.0f} ms after EN-bar release: C77 (U5/U7 EN) <= {v77:.3f} V < 0.4 V")
v5r = 5.25 * math.exp(-t_rem / tau5)
chk(v5r < 2.1, f"P11 restart: VCC5V0_SYS <= {v5r:.3f} V, below buck UVLO before the next turn-on")
# every buck output: held at its band maximum until the bucks stop (VCC5V0_SYS < 2.1 V), then RC decay into its bleeder
# with the rail's MAXIMUM total capacitance +10 % (SoC load current ignored: it only speeds the decay)
t_stop = t_off + tau5 * math.log(5.25 / 2.1)
tau_rail = {}
for n, r in rails.items():
    if r["kind"] != "buck": continue
    ctot_max = (f(r["c_local_uf"]) + f(r["c_soc_max_uf"])) * 1.1e-6
    tau_rail[n] = f(r["bleeder_ohm"]) * ctot_max
    vr = band[n][1] * math.exp(-(t_gap - t_stop) / tau_rail[n])
    chk(vr <= 0.4, f"P11 restart: {n} <= {vr:.3f} V <= 0.4 V (bleeder {r['bleeder_ohm']} ohm, C <= {ctot_max*1e6:.1f} uF, tau {tau_rail[n]*1e3:.1f} ms)")
v65 = two_pole(1.861, tau_rail["VCC_1V8"], R43C65 * 1.1, t_gap - t_stop)
chk(v65 < VTH[0], f"P11 restart: C65 (U6 EN) <= {v65:.4f} V < 0.4 V")

# ---------------------------------------------------------------- P10 TI Table 4 L/C, with the TOTAL rail capacitance (round 3)
# [TLV] §8.2.2.3 Table 4 p.9: checked cells per (row, L). Table notes p.9: effective L may vary +20 %/-30 %, effective C +20 %/-50 %.
# Every checked cell therefore covers effective C in [0.5, 1.2] x its nominal.  The rail passes if its whole effective-capacitance
# range lies inside the union of those intervals for every row its set-point band touches.
# Total rail C = buck-local + every SoC/peripheral decoupling capacitor on the same rail, incl. ferrite/1-ohm sub-rails and R32
# (the [LF] values Phase 5 will place, column c_soc_*).  Effective range: min = (local + soc_min) x 0.9 (cap tolerance)
# x DC-bias retention (ESTIMATE per rail, Phase-4 requirement); max = (local + soc_max) x 1.1 (DC bias only lowers C).
T4 = {("0.6-1.2", 1.0): {"2x22"}, ("0.6-1.2", 2.2): {"2x22"},
      ("1.2-1.8", 1.0): {"22", "2x22"}, ("1.2-1.8", 2.2): {"22", "2x22"},
      ("1.8+", 1.0): {"10", "22", "2x22"}, ("1.8+", 2.2): {"10", "22", "2x22"}}
CVAL = {"10": 10.0, "22": 22.0, "2x22": 44.0}
def rows(v):  # every Table-4 row the rail can fall into over its whole set-point band
    return {("0.6-1.2" if x < 1.2 else "1.2-1.8" if x < 1.8 else "1.8+") for x in v}
def covered(lo, hi, cells):                  # is [lo, hi] inside the union of [0.5c, 1.2c]?
    iv = sorted((0.5 * CVAL[c], 1.2 * CVAL[c]) for c in cells)
    x = lo
    for a, b in iv:
        if a <= x <= b: x = max(x, b)
        if x >= hi: return True
    return x >= hi
P10_DEV = {"VDD_0V9": "D-117 c: owner-ordered 22 uF local output (D-H6); allowed <= +20 % over the cell; bring-up load step"}
for n, r in rails.items():
    if r["kind"] != "buck": continue
    L = f(r["l_uh"])
    cmin = (f(r["c_local_uf"]) + f(r["c_soc_min_uf"])) * 0.9 * f(r["vbias_retention"])
    cmax = (f(r["c_local_uf"]) + f(r["c_soc_max_uf"])) * 1.1
    rs = rows((f(r["nominal_v"]),) + band[n])
    good = all(covered(cmin, cmax, T4.get((row, L), set())) for row in rs)
    # D-117 c (owner order D-H6): C24 (C_OUT_U4) 10 -> 22 uF puts the VDD_0V9 total above the 2 x 22 cell's +20 % bound
    # (the far SoC-side 33.6 uF sits behind JP1 and the L3 neck). Recorded deviation with its own bound: the lower corner
    # must stay inside the cell and the upper corner may exceed 1.2 x 44 uF by at most 20 %; bring-up load-step check.
    if not good and n in P10_DEV:
        hi = max(1.2 * CVAL[c] for row in rs for c in T4.get((row, L), set()))
        lo = min(0.5 * CVAL[c] for row in rs for c in T4.get((row, L), set()))
        good = cmin >= lo and cmax <= hi * 1.20
        print(f"DEV  P10 {n}: effective upper corner {cmax:.1f} uF is {100 * (cmax / hi - 1):.0f} % above the checked "
              f"cell bound {hi:.1f} uF ({P10_DEV[n]})")
    chk(good, f"P10 {n}: L = {L:g} uH; total C {f(r['c_local_uf'])+f(r['c_soc_min_uf']):.1f}-{f(r['c_local_uf'])+f(r['c_soc_max_uf']):.1f} uF nominal "
              f"(local {r['c_local_uf']} + SoC/peripheral {r['c_soc_min_uf']}-{r['c_soc_max_uf']}), effective {cmin:.1f}-{cmax:.1f} uF inside the "
              f"checked Table 4 cells' +20 %/-50 % range in every row {sorted(rs)}" + (" (upper corner: recorded deviation, DEV line above)" if n in P10_DEV else ""))
    chk(f(r["cff_pf"]) == 6.8 and f(r["r_bot_k"]) == 100, f"P10 {n}: feed-forward {r['cff_pf']} pF with R2 = {r['r_bot_k']} k ([TLV] p.9: 6.8 pF for R2 = 100 k)")

# ---------------------------------------------------------------- P8 R4 hard-off window (power.md §6.2, D-33, D-117 c)
# D-H6 / D-117 c: R4 "long press (>= 8 s) = hard off" is read as "the hard-off never happens before 8 s" (worst case
# >= 8 s; the independent review of CHECKPOINT 2). C_PDT = 2.2 uF X5R 16 V (C23630, the C2 part).
C = 2.2                                     # uF, X5R: ±10 % initial (K), ±15 % over -55..85 °C (X5R class definition)
DCB = 0.95                                  # DC-bias loss at VPDT <= 1.3 V on a 16 V 0603 X5R part: <= 5 % assumed (UNVERIFIED)
tnom = C / 1.56e-4 + 1                      # ms, CPDT = 1.56e-4 uF/ms x (tPDT - 1 ms) ([LTC] p.9)
tmin = tnom * (9 / 11.5) * 0.90 * 0.85 * DCB + 52     # timer spread at 1500 pF 9/11.5/13.5 ms ([LTC] p.3) + tPD,MIN min
tmax = tnom * (13.5 / 11.5) * 1.10 * 1.15 + 82 + 41   # + tPD,MIN max + tDB,OFF max
# round 3: the PDT pull-up current is specified 2.4/3/3.6 uA ([LTC] p.3, IPDT(PU)); for a large C_PDT the time scales with
# 1/I, so the slow corner is 3/2.4 = 1.25 (> 13.5/11.5) and the fast corner 3/3.6 (the 9/11.5 timing corner is faster still)
tmax_i = tnom * (3 / 2.4) * 1.10 * 1.15 + 82 + 41
tmin_i = tnom * (3 / 3.6) * 0.90 * 0.85 * DCB + 52
tmax, tmin = max(tmax, tmax_i), min(tmin, tmin_i)
chk(tmin >= 8000, f"P8 no hold shorter than 8 s is a hard-off: worst-case earliest hard-off {tmin/1e3:.2f} s >= 8.0 s "
                  f"(C_PDT {C} uF, nominal {(tnom + 64)/1e3:.1f} s; D-117 c)")
chk(tmax <= 30000, f"P8 every hold >= {tmax/1e3:.1f} s is a hard-off (worst-case latest point <= 30 s, information bound)")

for m in ok: print("PASS", m)
for m in req: print("REQ ", m)
for m in err: print("FAIL", m)
print(f"\n{len(ok)} pass, {len(err)} fail, {len(req)} Phase-4 requirements (not counted)")
print("\nSequencing detail (ms): (Vin, ramp) -> (U4 good latest, U5/U7 EN earliest, min margin U5+U7 good -> U6 EN, U6 good latest)")
for k, v in res.items(): print(" ", k, tuple(round(1e3 * x, 2) for x in v))
print(f"Q_PWR: on |VGS| {v_on_min:.2f}-{v_on_max:.2f} V; VCC5V0_SYS ramp {ramp[0]*1e3:.2f}-{ramp[1]*1e3:.2f} ms; inrush <= {inrush:.2f} A; "
      f"turn-on delay <= {t_on_delay*1e3:.1f} ms; turn-off <= {t_off*1e3:.0f} ms; plug-in tau {tau_plug*1e3:.0f} ms")
print(f"Hard-off threshold: nominal {(tnom+67)/1e3:.2f} s, range {tmin/1e3:.2f}-{tmax/1e3:.2f} s; input {P_in:.2f} W")
sys.exit(1 if err else 0)
