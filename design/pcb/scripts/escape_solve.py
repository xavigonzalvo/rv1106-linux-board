#!/usr/bin/env python3
"""U9 fan-band geometry solver (layout phase L3), run with design/.venv/bin/python -I (needs scipy):

    design/.venv/bin/python -I design/pcb/scripts/escape_solve.py IN.json OUT.json

route_escape.py (pcbnew) writes IN.json: per U9 side, in pin order, the escaping items (lane to a gate point, link to
a ring-1 pad, via-ring via) and the fixed ring-1 pads near the gate. This script finds, per side, one linear programme:

  levels   r_k = 6.50, 6.55, ..., 8.00 mm from the U9 centre (radial distance; t = position along the side)
  vars     x[i,k] position of item i at level k; u[i,k] >= |x[i,k+1] - x[i,k]| (<= dr: at most 45 deg);
           s[a,b,k] >= u of both neighbours (slope of the steeper one)
  order    consecutive items present at a level keep  x_b - x_a >= need_ab * (1 + 0.4143 * s/dr)  (a horizontal gap
           of need*sqrt(2) when a line runs at 45 deg, so the perpendicular gap is never below need)
  vias     a via item ends at r_v = 7.45 (via ring); at the levels within 0.45 mm of r_v its neighbours keep the
           horizontal chord of a circle of radius 0.45 + 0.03 (track centre to via centre: 0.05 half track + 0.25
           board hole clearance + 0.15 hole radius), via to via >= 0.78 (hole-to-hole 0.45 + 0.30 drill + margin)
  pads     ring-1 pads (inner edge ~7.93) are fixed items at the levels >= inner edge - 0.15
  ends     level 0 = the pin (t0); lanes end at their gate point (t_gate, r 8.00, escape_plan.csv t_planned), links
           at their pad centre from inner edge - 0.15 on, vias anywhere within +-1.45 mm of the pin
  cost     sum u (lateral movement) + 0.5 |via - pin|
Clearances (DRU "QFN-128 escape neck-down", every segment touches the U9_FAN area): 0.10 mm between tracks and to
pads, board hole clearance 0.25 mm to via holes. Output: per item the polyline (board-independent t, r) and the
via position. route_escape.py converts to board coordinates and draws; KiCad DRC is the judge.
"""
import json
import math
import sys

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

R0, R1, DR = 6.50, 8.00, 0.05
R_VIA = 7.45
VIA_R = 0.35 + 0.075 + 0.02  # largest track centre to via centre (0.15 hole radius + 0.20 hole-to-track + half track)
VIA_VIA = 0.77
MAXSLOPE = 2.0              # |dx/dr| <= 2 (63 deg from radial)
PAD_REACH = 0.15             # pads constrain the levels >= inner edge - 0.15


DEBUG = bool(__import__("os").environ.get("ESC_DEBUG"))


def solve_side(side, side_name=""):
    items = side["items"]
    pads = list(side["pads"])
    levels = [round(R0 + k * DR, 4) for k in range(int(round((R1 - R0) / DR)) + 1)]
    K = len(levels)
    n = len(items)
    kv_of = {}
    pres = []
    for i, it in enumerate(items):
        if it["kind"] == "via":
            kv = max(k for k, r in enumerate(levels) if r <= R_VIA + 1e-9)
            kv_of[i] = kv
            pres.append(list(range(0, kv + 1)))
        elif it["kind"] == "link":
            last = max(k for k, r in enumerate(levels) if r <= it["r_in"] + 1e-9)
            pres.append(list(range(0, last + 1)))
            pads.append({"key": it["key"], "t": it["tg"], "half": it["pad_half"], "r_in": it["r_in"], "own": i})
        else:
            pres.append(list(range(K)))
    idx = {}
    nv = 0
    for i in range(n):
        for k in pres[i]:
            idx[("x", i, k)] = nv
            nv += 1
    for i in range(n):
        for k in pres[i][:-1]:
            idx[("u", i, k)] = nv
            nv += 1
    rows, rhs, cost = [], [], {}

    tags = []

    def add(coefs, b, tag=None):  # sum coefs <= b
        rows.append(coefs)
        rhs.append(b)
        tags.append(tag)

    bounds = [(None, None)] * nv
    for i, it in enumerate(items):
        for k in pres[i][:-1]:
            xu, xa, xb = idx[("u", i, k)], idx[("x", i, k)], idx[("x", i, k + 1)]
            add({xa: 1, xb: -1, xu: -1}, 0.0)
            add({xa: -1, xb: 1, xu: -1}, 0.0)
            bounds[xu] = (0, MAXSLOPE * DR)
            cost[xu] = cost.get(xu, 0) + 1.0
        # bends: penalise |second difference| so the lines run straight between few bends
        for k in pres[i][1:-1]:
            cv = nv
            nv += 1
            bounds.append((0, None))
            xm, x0_, xp = idx[("x", i, k - 1)], idx[("x", i, k)], idx[("x", i, k + 1)]
            add({xm: 1, x0_: -2, xp: 1, cv: -1}, 0.0)
            add({xm: -1, x0_: 2, xp: -1, cv: -1}, 0.0)
            cost[cv] = 0.5
        bounds[idx[("x", i, 0)]] = (it["t0"], it["t0"])
        if it["kind"] == "lane":
            bounds[idx[("x", i, K - 1)]] = (it["tg"], it["tg"])
        elif it["kind"] == "link":
            m = it["pad_half"] - it["half"] - 0.02
            for k in pres[i]:
                if levels[k] >= it["r_in"] - PAD_REACH - 1e-9:
                    bounds[idx[("x", i, k)]] = (it["tg"] - m, it["tg"] + m)
        else:
            kv = kv_of[i]
            xv = idx[("x", i, kv)]
            bounds[xv] = (it["t0"] - 1.45, it["t0"] + 1.45)
            for k in pres[i]:
                if levels[k] >= R_VIA - VIA_R - 1e-9 and k != kv:
                    add({idx[("x", i, k)]: 1, xv: -1}, 0.0)
                    add({idx[("x", i, k)]: -1, xv: 1}, 0.0)
            dv = nv
            nv += 1
            bounds.append((0, None))
            add({xv: 1, dv: -1}, it["t0"])
            add({xv: -1, dv: -1}, -it["t0"])
            cost[dv] = 0.5

    def term(q, k, r):
        kind, j = q[0], q[1]
        if kind == "p":
            return None, pads[j]["t"], pads[j]["half"], "pad"
        it = items[j]
        if it["kind"] == "via" and r >= R_VIA - VIA_R - 1e-9:
            return idx[("x", j, kv_of[j])], 0.0, 0.25, "via"
        return idx[("x", j, k)], 0.0, it["half"], ("u", j, k) if ("u", j, k) in idx else None

    def constrain(a, b, k, r):
        nonlocal nv
        va, ca, ha, ua = term(a, k, r)
        vb, cb, hb, ub = term(b, k, r)
        if ua == "pad" and ub == "pad":
            return
        if ua == "via" and ub == "via":
            need, slope_u = VIA_VIA, []
        elif ua == "via" or ub == "via":
            j = a[1] if ua == "via" else b[1]
            dy = abs(r - levels[kv_of[j]])
            if dy > VIA_R:
                return
            other = hb if ua == "via" else ha
            rr = 0.35 + other + 0.02
            if dy > rr:
                return
            need = math.sqrt(max(rr ** 2 - dy ** 2, 0.0))
            slope_u = []
        else:
            need = ha + hb + 0.10 + 0.005
            slope_u = [q for q in (ua, ub) if q not in (None, "pad", "via")]
        coefs = {}
        if va is not None:
            coefs[va] = coefs.get(va, 0) + 1
        if vb is not None:
            coefs[vb] = coefs.get(vb, 0) - 1
        b0 = cb - ca - need
        if slope_u:
            sv = nv
            nv += 1
            bounds.append((0, MAXSLOPE * DR))
            for q in slope_u:
                add({idx[q]: 1, sv: -1}, 0.0)
            # sqrt(1 + m^2) <= max(1 + 0.4142 m, 0.5924 + 0.8219 m) on [0, 2] (two secants of a convex function)
            c1 = dict(coefs)
            c1[sv] = need * (math.sqrt(2) - 1) / DR
            add(c1, b0, ("order", a, b, r))
            c2 = dict(coefs)
            c2[sv] = need * (math.sqrt(5) - math.sqrt(2)) / DR
            add(c2, cb - ca - need * (2 * math.sqrt(2) - math.sqrt(5)), ("order", a, b, r))
            return
        if not coefs:
            if b0 < -1e-9:
                print("  fixed conflict", side_name, a, b, r, b0)
            return
        add(coefs, b0, ("order", a, b, r))

    for k, r in enumerate(levels):
        seq = []
        for i, it in enumerate(items):
            in_pad = it["kind"] == "link" and r >= it["r_in"] - PAD_REACH - 1e-9
            if k in pres[i] and not in_pad:
                seq.append(("i", i, it["key"]))
            elif it["kind"] == "via" and r <= levels[kv_of[i]] + VIA_R + 1e-9 and k not in pres[i]:
                seq.append(("i", i, it["key"]))
        for j, pd in enumerate(pads):
            if r >= pd["r_in"] - PAD_REACH - 1e-9 and (pd.get("own") is None or k in pres[pd["own"]]
                                                       or r >= pd["r_in"]):
                seq.append(("p", j, pd["key"]))
        seq.sort(key=lambda q: q[2])
        isvia = [q[0] == "i" and items[q[1]]["kind"] == "via" and r >= R_VIA - VIA_R - 1e-9 for q in seq]
        for m in range(len(seq) - 1):
            a, b = seq[m], seq[m + 1]
            if (a[0] == "p" and isvia[m + 1]) or (isvia[m] and b[0] == "p"):
                continue
            constrain(a, b, k, r)
        # pads also keep clear of the next non-via item beyond a via
        for m, q in enumerate(seq):
            if q[0] != "p":
                continue
            for step in (1, -1):
                j = m + step
                if 0 <= j < len(seq) and isvia[j]:
                    while 0 <= j < len(seq) and isvia[j]:
                        j += step
                    if 0 <= j < len(seq):
                        constrain(q, seq[j], k, r) if step == 1 else constrain(seq[j], q, k, r)
    if DEBUG:
        for ri, tg in enumerate(tags):
            if tg:
                rows[ri][nv] = -1
                cost[nv] = 1000.0
                bounds.append((0, None))
                nv += 1
    A = lil_matrix((len(rows), nv))
    for ri, row in enumerate(rows):
        for c, v in row.items():
            A[ri, c] = v
    c = np.zeros(nv)
    for kk, v in cost.items():
        c[kk] = v
    res = linprog(c, A_ub=A.tocsr(), b_ub=np.array(rhs), bounds=bounds, method="highs")
    if res.status != 0:
        return {"ok": False, "msg": res.message}
    x = res.x
    if DEBUG:
        for ri, tg in enumerate(tags):
            if tg:
                sl = [c for c in rows[ri] if cost.get(c) == 1000.0]
                if sl and x[sl[0]] > 1e-6:
                    print("  slack %.3f" % x[sl[0]], tg[1][2], tg[2][2], "r", tg[3], tg[1][0], tg[2][0])
    out = []
    for i, it in enumerate(items):
        pts = [(round(float(x[idx[("x", i, k)]]), 5), levels[k]) for k in pres[i]]
        o = {"key": it["key"], "pts": pts}
        if it["kind"] == "via":
            o["via"] = pts[-1]
        out.append(o)
    return {"ok": True, "items": out, "cost": float(res.fun)}


def main():
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    out = {}
    for name, side in data.items():
        out[name] = solve_side(side, name)
        print("side %s: %s" % (name, "ok, cost %.2f" % out[name]["cost"] if out[name]["ok"] else out[name]["msg"]))
    with open(sys.argv[2], "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
