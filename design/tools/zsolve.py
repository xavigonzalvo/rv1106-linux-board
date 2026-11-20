"""Quasi-static 2-D finite-difference field solver for outer-layer (surface) microstrip on the JLCPCB
JLC04161H-7628 stackup (Phase 7, layout.md §2). Pure arithmetic, no downloaded files are read.

Stackup constants (JLCPCB "Controlled Impedance PCB Layer Stackup" page, section "JLC04161H-7628 Stackup" and
"Controlled Impedance PCB Parameters", fetched 2026-10-29 into refs/jlcpcb-impedance-2026-10-29/impedance.html):
  top copper 0.035 mm, prepreg 7628x1 0.2104 mm (Er 4.4), inner copper 0.0152 mm, core 1.065 mm (Er 4.6);
  solder mask: C1 = 1.2 mil above substrate, C2 = 0.6 mil above trace, C3 = 1.2 mil between traces, Er 3.8.

Method: Laplace equation div(eps grad V) = 0 on a uniform grid (node spacing H), conductors as fixed-potential nodes,
L2 ground plane at y = 0 (V = 0), a far V = 0 lid and far V = 0 side walls. Capacitance per unit length from the
stored field energy, once with the dielectrics (C) and once in vacuum (C0); Z = 1 / (c0 * sqrt(C * C0)).
Edge-coupled pair: odd mode (+1 V / -1 V) gives Zodd; Zdiff = 2 Zodd. Even mode gives Zeven; Zcm = Zeven / 2.
Optional coplanar ground strips (pour) at a given gap from the outer trace edges.
Validated in layout_calc.py against the Hammerstad-Jensen closed form for a bare microstrip (no mask)."""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

EPS0 = 8.8541878128e-12
C0 = 299792458.0
MIL = 0.0254  # mm

STACK = dict(t_cu=0.035, h=0.2104, er=4.4, mask_sub=1.2 * MIL, mask_trace=0.6 * MIL, er_mask=3.8)


def _solve(widths_x, lefts_x, volts, w_dom, h_top, H, t, h, er, mask_sub, mask_trace, er_mask, gnd_strips=()):
    nx = int(round(w_dom / H)) + 1
    ny = int(round(h_top / H)) + 1
    x = np.arange(nx) * H - w_dom / 2
    y = np.arange(ny) * H
    # cell permittivity (cells between nodes): (ny-1) x (nx-1), cell centre coordinates
    xc = (x[:-1] + x[1:]) / 2
    yc = (y[:-1] + y[1:]) / 2
    XC, YC = np.meshgrid(xc, yc)
    eps = np.ones_like(XC)
    eps[YC < h] = er
    if er_mask:
        cond_cells = np.zeros_like(XC, dtype=bool)
        for xl, w in list(zip(lefts_x, widths_x)) + [(g0, g1 - g0) for g0, g1 in gnd_strips]:
            cond_cells |= (XC >= xl) & (XC <= xl + w) & (YC >= h) & (YC <= h + t)
        # mask over substrate: h .. h+mask_sub ; over trace: h+t .. h+t+mask_trace ; near trace sides: conformal
        m = (YC >= h) & (YC < h + mask_sub) & ~cond_cells
        for xl, w in list(zip(lefts_x, widths_x)) + [(g0, g1 - g0) for g0, g1 in gnd_strips]:
            m |= (XC >= xl - mask_trace) & (XC <= xl + w + mask_trace) & (YC >= h) & (YC < h + t + mask_trace) & ~cond_cells
        eps[m] = er_mask
    # node classification
    X, Y = np.meshgrid(x, y)
    fixed = np.zeros(X.shape, dtype=bool)
    val = np.zeros(X.shape)
    fixed[0, :] = True; fixed[-1, :] = True; fixed[:, 0] = True; fixed[:, -1] = True  # V=0 box
    tol = H * 0.01
    for xl, w, v in zip(lefts_x, widths_x, volts):
        n = (X >= xl - tol) & (X <= xl + w + tol) & (Y >= h - tol) & (Y <= h + t + tol)
        fixed |= n; val[n] = v
    for g0, g1 in gnd_strips:
        n = (X >= g0 - tol) & (X <= g1 + tol) & (Y >= h - tol) & (Y <= h + t + tol)
        fixed |= n; val[n] = 0.0
    # face coefficients: horizontal edge (j,i)-(j,i+1) touches cells (j-1,i) and (j,i)
    epad = np.pad(eps, 1, mode="edge")  # (ny+1) x (nx+1); epad[j, i] = cell (j-1, i-1)
    ex = (epad[0:ny, 1:nx] + epad[1:ny + 1, 1:nx]) / 2  # ny x (nx-1)
    ey = (epad[1:ny, 0:nx] + epad[1:ny, 1:nx + 1]) / 2  # (ny-1) x nx
    idx = -np.ones(X.shape, dtype=np.int64)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    N = free.sum()
    rows, cols, data = [], [], []
    b = np.zeros(N)
    diag = np.zeros(N)
    J, I = np.nonzero(free)
    k = idx[J, I]
    for dj, di, coef in ((0, 1, ex[J, I]), (0, -1, ex[J, I - 1]), (1, 0, ey[J, I]), (-1, 0, ey[J - 1, I])):
        jj, ii = J + dj, I + di
        diag += coef
        nb_free = free[jj, ii]
        rows.append(k[nb_free]); cols.append(idx[jj[nb_free], ii[nb_free]]); data.append(-coef[nb_free])
        b[~nb_free] += coef[~nb_free] * val[jj[~nb_free], ii[~nb_free]]
    rows.append(k); cols.append(k); data.append(diag)
    A = sp.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(N, N))
    V = val.copy()
    V[free] = spla.spsolve(A, b)
    # energy per unit length / eps0: 1/2 sum eps_face dV^2 (square cells: H cancels)
    W = 0.5 * (np.sum(ex * np.diff(V, axis=1) ** 2) + np.sum(ey * np.diff(V, axis=0) ** 2))
    return W * EPS0  # J/m per V^2 units


def microstrip(w, s=None, gnd_gap=None, H=None, stack=STACK, mask=True, mode="odd", w_dom=None, h_top=1.6):
    """Return impedance (ohm). Single trace when s is None (returns Z0); pair: mode 'odd' returns Zdiff, 'even' Zcm."""
    t, h, er = stack["t_cu"], stack["h"], stack["er"]
    H = H or h / 42  # grid snapped so the dielectric height is a whole number of cells (~5 um)
    ms, mt, em = (stack["mask_sub"], stack["mask_trace"], stack["er_mask"]) if mask else (0, 0, 0)
    if s is None:
        lefts, widths, volts = [-w / 2], [w], [1.0]
        span = w
    else:
        lefts, widths = [-s / 2 - w, s / 2], [w, w]
        volts = [1.0, -1.0] if mode == "odd" else [1.0, 1.0]
        span = 2 * w + s
    strips = ()
    if gnd_gap is not None:
        strips = ((-span / 2 - gnd_gap - 1.0, -span / 2 - gnd_gap), (span / 2 + gnd_gap, span / 2 + gnd_gap + 1.0))
        span += 2 * (gnd_gap + 1.0)
    w_dom = w_dom or max(4.0, span + 3.0)
    kw = dict(w_dom=w_dom, h_top=h_top, H=H, t=t, h=h, gnd_strips=strips)
    Wd = _solve(widths, lefts, volts, er=er, mask_sub=ms, mask_trace=mt, er_mask=em, **kw)
    Wa = _solve(widths, lefts, volts, er=1.0, mask_sub=0, mask_trace=0, er_mask=0, **kw)
    if s is None:
        C, Ca = 2 * Wd, 2 * Wa
        return 1 / (C0 * np.sqrt(C * Ca))
    if mode == "odd":   # W = Q1 (V1=+1, V2=-1) -> C_odd per line = W
        C, Ca = Wd, Wa
        return 2 / (C0 * np.sqrt(C * Ca))
    C, Ca = Wd, Wa      # even: W = Q1 (both +1) -> C_even per line = W
    return 0.5 / (C0 * np.sqrt(C * Ca))


def hammerstad(w, h=STACK["h"], er=STACK["er"]):
    """Hammerstad-Jensen zero-thickness microstrip (validation only)."""
    u = w / h
    eta = 376.73
    f = 6 + (2 * np.pi - 6) * np.exp(-(30.666 / u) ** 0.7528)
    z01 = eta / (2 * np.pi) * np.log(f / u + np.sqrt(1 + (2 / u) ** 2))
    a = 1 + np.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + np.log(1 + (u / 18.1) ** 3) / 18.7
    bb = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * bb)
    return z01 / np.sqrt(ee)
