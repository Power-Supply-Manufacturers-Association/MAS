#!/usr/bin/env python3
"""Extract core-loss curves for Ferroxcube 3F37 and 4F1 from Ferroxcube's vector data sheets (ABT #1518).

    python3 scripts/extract-ferroxcube-loss-1518.py 3F37.pdf 4F1.pdf --json /tmp/fxc-points.json \
            [--report /tmp/fxc-report.json]

Sources
-------
A. Ferroxcube 3F37 Material Data Sheet, September 22nd, 2025 (Word for Microsoft 365), 3 pages:
       https://www.ferroxcube.com/upload/media/product/file/MDS/2025%20MDS%203F37.pdf
   Read 2026-09-30 (312,282 bytes, sha256 14ff95975cf08d7de34abfeed878d581bbad35739d3b1c88b73afa199c00594f).
   p1 table (Pv, kW/m3): 100 C 400 kHz 100 mT ~350; 100 C 500 kHz 100 mT ~550; 500 kHz 50 mT
   25/100/140 C ~60/60/95; 100 C 800 kHz 50 mT ~150; 100 C 1000 kHz 50 mT ~270. "Measured on T25/15/8".
   p2 Fig. 4/5/6: Pv vs T at 50/75/100 mT (four frequencies each, 25..140 C).
   p3 Fig. 9/10: Pv vs B at 100 C / 120 C (100..1000 kHz). Figs. 11-13 redraw Figs. 6/5/4 with the
   Steinmetz "Simulation" lines and are not read (the simulation is the printed formula, not data).
B. Ferroxcube 4F1 Material specification, 2008 Sep 01 (Acrobat Distiller 5.0, 2009-07-26), 4 pages:
       https://www.ferroxcube.com/upload/media/product/file/MDS/4f1.pdf
   Read 2026-09-30 (48,473 bytes, sha256 6336405b4a46be7c81aeb882ff3aca4371b4f77147d4f2578f6ca96f56e7ce51).
   p2 table: Pv at 100 C, 3 MHz/10 mT <= 200 and 10 MHz/5 mT <= 200 kW/m3 (limits, not typical values).
   p3 Fig.6: Pv vs B at T = 100 C, 3/5/10 MHz (straight lines); Fig.7: Pv vs T (0..120 C) for
   f/B = 10 MHz/7.5 mT, 5/10, 10/5, 3/10 (labelled by the table printed at the curves' right ends).

Method -- nothing is digitised from pixels
------------------------------------------
Both sheets are vector. 3F37's figures are Excel charts: gridlines are single strokes, curves are
smoothed lines (Bezier segments whose knots are the plotted data points) or straight polylines;
each curve is identified by its colour against the legend swatch next to its "NNN kHz" label.
4F1's figures are the Philips-era line art: the grid is one path, the curves are single strokes.
1. Calibration from the gridlines, checked against every printed tick label (LABEL_TOL) and for
   a straight lin/log scale (GRID_TOL).
2. Points: 3F37 -- the knots of each curve (the plotted data), only where they lie inside the
   plot area (Excel draws, clipped, beyond it). 4F1 Fig.6 -- the two ends of each straight line
   plus every 1-2-5 value of B strictly between them; Fig.7 -- every 10 C along each Bezier.
3. Checks, each able to fail and drop a figure whole (#1006):
   * 3F37: every table value a figure covers must be reproduced within TABLE_TOL.
     A figure covering no table value (Fig. 5, 75 mT; Fig. 10, 120 C) must agree within
     CROSS_TOL with the table-checked figures at every condition they share.
   * 4F1: the table gives limits only, so Fig.6 and Fig.7 must agree with each other within
     CROSS_TOL at the four shared conditions (100 C), and both must respect the <= 200 limits.
   * Physics: loss rises with frequency at a common B and T.
Result (2026-09-30): 3F37 94 points (Figs. 4/5/6 all knots, Figs. 9/10 the knots at conditions the
Pv-T figures do not carry; table ratios 0.974..1.032; cross ratios 0.998..1.005 -- the Pv-T and Pv-B
figures plot one measurement set). 4F1 REJECTED: Fig.6 and Fig.7 disagree at 100 C, 10 MHz/5 mT
(135 vs 152 kW/m3, 1.123); the other shared conditions read 0.955 (3 MHz/10 mT), 1.073 (5/10),
1.009 (10/7.5). Nothing tells which figure is wrong, so neither is stored (exit code 1).

Output: {material: [MAS volumetricLossesPoint, ...]} in SI; waveform "sinusoidal" (Ferroxcube
measures sine-wave Pv), origin "manufacturer".
"""
import argparse
import importlib.util
import json
import math
import os
import re
import sys

import fitz

_spec = importlib.util.spec_from_file_location(
    "dmegc", os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract-dmegc-loss.py"))
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)
point, col, fit_line = D.point, D.col, D.fit_line
GRID_TOL, LABEL_TOL = D.GRID_TOL, D.LABEL_TOL


class Axis:
    """As extract-dmegc-loss.Axis, but the gridline snap is repeated until the assignment is
    stable: 4F1's log labels sit ~1.5 pt below their gridlines (superscript layout), so a
    label-only first guess can misplace the dense 8/9/10 lines of a decade."""

    def __init__(self, grid, labels, log, step, report, name):
        self.log = log
        f = (lambda v: math.log10(v)) if log else (lambda v: v)
        a, b = fit_line([(f(v), p) for p, v in labels])
        prev = None
        for _ in range(10):
            snapped = []
            for g in grid:
                u = (g - b) / a
                if log:
                    k = math.floor(u + 1e-9)
                    n = 10 ** (step - 1)
                    cands = [math.log10(m / n * 10 ** kk) for kk in (k - 1, k, k + 1) for m in range(n, 10 * n)]
                    vv = min(cands, key=lambda c: abs(c - u))
                else:
                    vv = round(u / step) * step
                snapped.append((vv, g))
            a, b = fit_line(snapped)
            if snapped == prev:
                break
            prev = snapped
        gres = max(abs(a * v + b - g) for v, g in snapped)
        lres = max(abs(a * f(v) + b - p) for p, v in labels)
        report[name] = dict(grid_resid=round(gres, 3), label_resid=round(lres, 3), n_grid=len(grid))
        if gres > GRID_TOL or lres > LABEL_TOL:
            raise RuntimeError(f"{name} axis: grid resid {gres:.2f} pt, label resid {lres:.2f} pt")
        self.a, self.b = a, b

    def value(self, pos):
        u = (pos - self.b) / self.a
        return 10 ** u if self.log else u

    def pos(self, v):
        return self.a * (math.log10(v) if self.log else v) + self.b

TABLE_TOL = 0.10
CROSS_TOL = 0.10
EPS = 0.6            # pt, a knot this far outside the plot area is still on it
BEZ = 24

TABLE_3F37 = [  # (T, f, B mT, Pv kW/m3)
    (100, 400e3, 100, 350), (100, 500e3, 100, 550), (25, 500e3, 50, 60), (100, 500e3, 50, 60),
    (140, 500e3, 50, 95), (100, 800e3, 50, 150), (100, 1000e3, 50, 270)]
FIGS_3F37 = [  # (page index, frame, kind, condition, title on the page)
    (1, (303.0, 90.8, 572.3, 283.5), "pv_t", 50, "Fig 4: Specific power loss at 50 mT vs temperature"),
    (1, (23.0, 299.5, 292.2, 492.3), "pv_t", 75, "Fig. 5: Specific power loss at 75 mT vs temperature"),
    (1, (303.0, 299.5, 572.3, 492.3), "pv_t", 100, "Fig. 6: Specific power loss at 100 mT vs temperature"),
    (2, (23.0, 90.8, 292.2, 283.5), "pv_b", 100, "Fig. 9: Specific power loss at 100ºC vs flux density"),
    (2, (303.0, 90.8, 572.3, 283.5), "pv_b", 120, "Fig 10: Specific power loss at 120ºC vs flux density"),
]


def bez(p0, p1, p2, p3, n=BEZ):
    return [((1 - t) ** 3 * p0.x + 3 * (1 - t) ** 2 * t * p1.x + 3 * (1 - t) * t * t * p2.x + t ** 3 * p3.x,
             (1 - t) ** 3 * p0.y + 3 * (1 - t) ** 2 * t * p1.y + 3 * (1 - t) * t * t * p2.y + t ** 3 * p3.y)
            for t in (i / n for i in range(1, n + 1))]


def subpaths(d):
    """[(knots, dense)] per continuous subpath of a drawing."""
    out, knots, dense, last = [], [], [], None
    for it in d["items"]:
        a = it[1]
        if last is None or abs(a.x - last.x) > 1e-3 or abs(a.y - last.y) > 1e-3:
            if knots:
                out.append((knots, dense))
            knots, dense = [(a.x, a.y)], [(a.x, a.y)]
        if it[0] == "l":
            b = it[2]; dense.append((b.x, b.y))
        elif it[0] == "c":
            b = it[4]; dense += bez(it[1], it[2], it[3], it[4])
        else:
            raise RuntimeError(f"path item {it[0]}")
        knots.append((b.x, b.y))
        last = b
    if knots:
        out.append((knots, dense))
    return out


def label_value(words, w, log):
    """Tick label value: '10'+'4' superscript word pair, '102' merged, or a plain number."""
    s = w[4]
    if log:
        sup = [v for v in words if v is not w and re.fullmatch(r"\d", v[4]) and abs(v[0] - w[2]) < 2.0
               and 0.8 < (w[1] + w[3]) / 2 - (v[1] + v[3]) / 2 < 5]
        if s == "10" and sup:
            return 10.0 ** int(sup[0][4])
        m = re.fullmatch(r"10([1-9])", s)   # "102" = 10^2 (superscript merged); "100" is a hundred
        if m and (w[2] - w[0]) > 10:
            return 10.0 ** int(m.group(1))
    return float(s)


def axes(page, plot, xlog, ylog, H, V, rep, xstep=None, ystep=None):
    words = page.get_text("words")
    xl, yl = [], []
    for w in words:
        if not re.fullmatch(r"-?\d+(\.\d+)?", w[4]) or w[3] - w[1] < 6.5:   # superscripts are 5.9 pt
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if plot.x0 - 8 <= cx <= plot.x1 + 8 and plot.y1 + 0.5 < cy < plot.y1 + 14:
            if xlog and re.fullmatch(r"\d", w[4]) and any(v[4] == "10" and abs(w[0] - v[2]) < 2 for v in words):
                continue  # an exponent
            xl.append((cx, label_value(words, w, xlog)))
        elif plot.y0 - 8 <= cy <= plot.y1 + 8 and plot.x0 - 12 < w[2] < plot.x0 - 0.5:
            if ylog and re.fullmatch(r"\d", w[4]) and any(v[4] == "10" and abs(w[0] - v[2]) < 2 for v in words):
                continue
            # the exponent sits higher than the base: centre the label on the base word
            yl.append((cy, label_value(words, w, ylog)))

    def step(labels, grid):
        if len(labels) < 2:
            raise RuntimeError("fewer than two tick labels")
        ls = sorted(labels)
        vs = sorted(v for _, v in labels)
        dv = min(b - a for a, b in zip(vs, vs[1:]))
        dp = abs(ls[1][0] - ls[0][0]) / abs((ls[1][1] - ls[0][1]) / dv)
        g = sorted(grid); dg = sorted(b - a for a, b in zip(g, g[1:]))[len(g) // 2 - 1]
        return dv / max(1, round(dp / dg))

    X = Axis(V, xl, xlog, 1 if xlog else (xstep or step(xl, V)), rep, "x")
    Y = Axis(H, yl, ylog, 1 if ylog else (ystep or step(yl, H)), rep, "y")
    return X, Y


def interp(pts, x):
    pts = sorted(pts)
    if not pts[0][0] - 0.05 <= x <= pts[-1][0] + 0.05:   # 0.05 pt: a curve end read at its own knot
        return None
    x = min(max(x, pts[0][0]), pts[-1][0])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 - 1e-6 <= x <= x1 + 1e-6:
            return y0 if x1 == x0 else y0 + (x - x0) / (x1 - x0) * (y1 - y0)


class Curve:
    def __init__(self, f, cond, knots, dense, X, Y, plot):
        self.f, self.cond = f, cond
        inside = lambda p: plot.x0 - EPS <= p[0] <= plot.x1 + EPS and plot.y0 - EPS <= p[1] <= plot.y1 + EPS
        self.knots = [(X.value(x), Y.value(y)) for x, y in knots if inside((x, y))]
        self.dropped = len(knots) - len(self.knots)
        self.dense = [(x, y) for x, y in dense if inside((x, y))]
        self.X, self.Y = X, Y

    def at(self, xv):
        y = interp(self.dense, self.X.pos(xv))
        return None if y is None else self.Y.value(y)


# ----------------------------------------------------------------------------------------- 3F37
def fig_3f37(page, frame, kind, cond, rep):
    frame = fitz.Rect(frame)
    H, V = set(), set()
    for d in page.get_drawings():
        c = col(d.get("color"))
        if c not in ((0.5, 0.5, 0.5), (0.85, 0.85, 0.85)) or not frame.contains(d["rect"]):
            continue
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.01 and abs(a.x - b.x) > 100:
                    H.add(round(a.y, 2))
                elif abs(a.x - b.x) < 0.01 and abs(a.y - b.y) > 100:
                    V.add(round(a.x, 2))
    H, V = sorted(H), sorted(V)
    plot = fitz.Rect(V[0], H[0], V[-1], H[-1])
    X, Y = axes(page, plot, kind == "pv_b", kind == "pv_b", H, V, rep)
    words = [w for w in page.get_text("words") if frame.contains(fitz.Rect(w[:4]))]
    text = " ".join(w[4] for w in words)
    need = f"{cond} mT" if kind == "pv_t" else f"{cond}ºC"
    if need not in text:
        raise RuntimeError(f"condition '{need}' not printed in the figure")
    # legend: swatch (short stroke) -> the 'NNN kHz' label right of it
    legend = {}
    for d in page.get_drawings():
        r = d["rect"]
        if frame.contains(r) and (d.get("width") or 0) >= 1.0 and 15 < r.width < 30 and r.height < 0.5 \
                and d.get("dashes") in (None, "[] 0"):
            lab = [w for w in words if 0 < w[0] - r.x1 < 5 and abs((w[1] + w[3]) / 2 - r.y0) < 3]
            if len(lab) == 1 and re.fullmatch(r"\d+", lab[0][4]):
                legend[col(d["color"])] = float(lab[0][4]) * 1e3
    if len(set(legend.values())) != len(legend) or len(legend) < 3:
        raise RuntimeError(f"legend {legend}")
    curves = []
    for d in page.get_drawings():
        r = d["rect"]
        c = col(d.get("color"))
        if c not in legend or (d.get("width") or 0) < 1.0 or d.get("dashes") not in (None, "[] 0") \
                or r.width < 30 or not r.intersects(plot) or r.x0 < frame.x0 - 1 or r.x1 > frame.x1 + 1:
            # Excel paths may run on (clipped) above/below the frame, never sideways out of it
            continue
        for knots, dense in subpaths(d):
            cv = Curve(legend[c], cond, knots, dense, X, Y, plot)
            curves.append(cv)
    fs = sorted(c.f for c in curves)
    if fs != sorted(legend.values()):
        raise RuntimeError(f"curves {fs} vs legend {sorted(legend.values())}")
    rep["curves"] = {f"{c.f/1e3:g}kHz": dict(knots=[(round(x, 1), round(y, 2)) for x, y in c.knots],
                                             dropped_outside=c.dropped) for c in curves}
    # physics: rising with f at shared knot abscissae
    cs = sorted(curves, key=lambda c: c.f)
    for a, b in zip(cs, cs[1:]):
        for x, _ in a.knots:
            va, vb = a.at(x), b.at(x)
            if va is not None and vb is not None and vb <= va:
                raise RuntimeError(f"loss not rising with f at {x:.3g}: {a.f:g} {va:.1f} vs {b.f:g} {vb:.1f}")
    return curves


def value_3f37(fig, T, f, B):
    """Read an accepted figure at (T, f, B), or None if it does not cover it."""
    kind, cond, curves = fig["kind"], fig["cond"], fig["curves"]
    c = [c for c in curves if c.f == f]
    if not c:
        return None
    if kind == "pv_t":
        return c[0].at(T) if B == cond else None
    return c[0].at(B) if T == cond else None


def run_3f37(pdf, report):
    doc = fitz.open(pdf)
    t1 = re.sub(r"\s+", " ", doc[0].get_text())
    for s in ("100ºC; 400kHz; 100mT ≈ 350", "100ºC; 500kHz; 100mT ≈ 550", "25ºC; 500kHz; 50mT ≈ 60",
              "100ºC; 500kHz; 50mT ≈ 60", "140ºC; 500kHz; 50mT ≈ 95", "100ºC; 800kHz; 50mT ≈ 150",
              "100ºC; 1000kHz; 50mT ≈ 270", "Measured on T25/15/8"):
        if s not in t1.replace(" ; ", "; ").replace("  ", " "):
            raise SystemExit(f"3F37 p1: '{s}' not found")
    figs = []
    for pidx, frame, kind, cond, title in FIGS_3F37:
        if title not in re.sub(r"\s+", " ", doc[pidx].get_text()):
            raise SystemExit(f"3F37 p{pidx+1}: title '{title}' not found")
        rep = report.setdefault(title.split(":")[0], {})
        try:
            curves = fig_3f37(doc[pidx], frame, kind, cond, rep)
        except RuntimeError as e:
            rep["REJECTED"] = str(e)
            continue
        figs.append(dict(name=title.split(":")[0], kind=kind, cond=cond, curves=curves, rep=rep))
    # table checks
    for fg in figs:
        fg["rep"]["table"] = []
        for T, f, B, pv in TABLE_3F37:
            v = value_3f37(fg, T, f, B)
            if v is not None:
                fg["rep"]["table"].append(dict(T=T, f=f, B=B, table=pv, curve=round(v, 1), ratio=round(v / pv, 3)))
        bad = [c for c in fg["rep"]["table"] if abs(c["ratio"] - 1) > TABLE_TOL]
        if bad:
            fg["rep"]["REJECTED"] = f"table: {bad}"
    ok = [fg for fg in figs if "REJECTED" not in fg["rep"] and fg["rep"]["table"]]
    # cross checks: every figure vs every table-checked figure at shared conditions (knots of either)
    for fg in figs:
        cross = []
        for ref in ok:
            if ref is fg:
                continue
            for c in fg["curves"]:
                for x, v in c.knots:
                    T, B = (x, fg["cond"]) if fg["kind"] == "pv_t" else (fg["cond"], x)
                    r = None
                    # shared condition: the other figure's fixed parameter equals this knot's
                    if ref["kind"] == "pv_t" and abs(B - ref["cond"]) < 0.5:
                        r = [cc for cc in ref["curves"] if cc.f == c.f]
                        r = r[0].at(T) if r else None
                    elif ref["kind"] == "pv_b" and abs(T - ref["cond"]) < 0.5:
                        r = [cc for cc in ref["curves"] if cc.f == c.f]
                        r = r[0].at(B) if r else None
                    if r is not None:
                        cross.append(dict(ref=ref["name"], f=c.f, T=round(T, 1), B=round(B, 1),
                                          this=round(v, 1), other=round(r, 1), ratio=round(v / r, 3)))
        fg["rep"]["cross"] = cross
        if not fg["rep"]["table"] and "REJECTED" not in fg["rep"]:
            if not cross:
                fg["rep"]["REJECTED"] = "no table value and no shared condition with a checked figure"
            elif any(abs(c["ratio"] - 1) > CROSS_TOL for c in cross):
                fg["rep"]["REJECTED"] = "cross-check off: " + str([c for c in cross if abs(c["ratio"] - 1) > CROSS_TOL])
    # Figs. 4-6 (Pv-T) and 9-10 (Pv-B) plot one measurement set (cross ratios 0.998..1.005): a
    # condition already stored from an earlier figure is not stored again.
    pts, seen = [], []
    for fg in figs:
        if "REJECTED" in fg["rep"]:
            continue
        n = dup = 0
        for c in fg["curves"]:
            for x, v in c.knots:
                T, B = (x, fg["cond"]) if fg["kind"] == "pv_t" else (fg["cond"], x)
                if any(f == c.f and abs(T - t) < 0.5 and abs(B - b) < 0.5 for f, t, b in seen):
                    dup += 1
                    continue
                seen.append((c.f, T, B))
                pts.append(point(c.f, B / 1000, T, v))
                n += 1
        fg["rep"]["points"] = n
        fg["rep"]["already_stored"] = dup
    return pts


# ------------------------------------------------------------------------------------------ 4F1
def grid_from_path(page, box):
    H, V = set(), set()
    for d in page.get_drawings():
        if not box.contains(d["rect"]) or abs((d.get("width") or 0) - 0.33) > 0.02 or len(d["items"]) < 8:
            continue
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.01:
                    H.add(round(a.y, 2))
                elif abs(a.x - b.x) < 0.01:
                    V.add(round(a.x, 2))
    return sorted(H), sorted(V)


def run_4f1(pdf, report):
    doc = fitz.open(pdf)
    t2 = re.sub(r"\s+", " ", doc[1].get_text())
    for s in ("100 °C; 3 MHz; 10 mT ≤ 200", "100 °C; 10 MHz; 5 mT ≤ 200"):
        if s not in t2:
            raise SystemExit(f"4F1 p2: '{s}' not found")
    pg = doc[2]
    t3 = re.sub(r"\s+", " ", pg.get_text())
    for s in ("Fig.6 Specific power loss as a function of peak", "Fig.7 Specific power loss for several"):
        if s not in t3:
            raise SystemExit(f"4F1 p3: '{s}' missing")
    words = pg.get_text("words")
    # Fig.6
    rep6 = report.setdefault("4F1 Fig.6", {})
    box6 = fitz.Rect(50, 480, 290, 700)
    H, V = grid_from_path(pg, box6)
    plot6 = fitz.Rect(V[0], H[0], V[-1], H[-1])
    X6, Y6 = axes(pg, plot6, True, True, H, V, rep6)
    if not any(w[4] == "100" and box6.contains(fitz.Rect(w[:4])) and w[1] < 520 for w in words) or \
            "T = 100 oC" not in t3:
        raise SystemExit("4F1 Fig.6: 'T = 100 oC' missing")
    lines = [d for d in pg.get_drawings() if box6.contains(d["rect"]) and abs((d.get("width") or 0) - 1.0) < 0.05
             and col(d.get("color")) == (0, 0, 0)]
    if len(lines) != 3 or any(len(d["items"]) != 1 or d["items"][0][0] != "l" for d in lines):
        raise SystemExit(f"4F1 Fig.6: {len(lines)} curves")
    # label order: the rotated 'N MHz' labels, left to right, sit at the lines' upper ends
    labs = sorted([w for w in words if box6.contains(fitz.Rect(w[:4])) and w[4] in ("3", "5", "10")
                   and any(v[4] == "MHz" and abs(v[0] - w[0]) < 4 and v[1] < w[1] for v in words)], key=lambda w: w[0])
    tops = sorted(lines, key=lambda d: min((d["items"][0][1], d["items"][0][2]), key=lambda p: p.y).x)
    if [w[4] for w in labs] != ["10", "5", "3"]:
        raise SystemExit(f"4F1 Fig.6 labels {[w[4] for w in labs]}")
    c6 = {}
    for d, w in zip(tops, labs):
        a, b = d["items"][0][1], d["items"][0][2]
        top = min((a, b), key=lambda p: p.y)
        if abs(w[0] - top.x) > 6:
            raise SystemExit(f"4F1 Fig.6: label {w[4]} MHz not at a line end ({w[0]:.1f} vs {top.x:.1f})")
        f = float(w[4]) * 1e6
        c6[f] = Curve(f, 100, [(a.x, a.y), (b.x, b.y)], [(a.x, a.y), (b.x, b.y)], X6, Y6, plot6)
    # physics: at a common B, loss rises with f (log-log straight lines -> compare at overlap)
    fs = sorted(c6)
    for f1, f2 in zip(fs, fs[1:]):
        lo = max(min(k[0] for k in c6[f1].knots), min(k[0] for k in c6[f2].knots))
        if not c6[f2].at(lo) > c6[f1].at(lo):
            raise SystemExit("4F1 Fig.6: loss not rising with f")
    rep6["lines"] = {f"{f/1e6:g}MHz": [(round(x, 2), round(v, 1)) for x, v in c.knots] for f, c in c6.items()}
    # Fig.7
    rep7 = report.setdefault("4F1 Fig.7", {})
    box7 = fitz.Rect(305, 480, 545, 700)
    H, V = grid_from_path(pg, box7)
    # the grid runs on under the label table to 160 C; the tick labels stop at 120 C
    plot7 = fitz.Rect(V[0], H[0], V[-1], H[-1])
    X7, Y7 = axes(pg, plot7, False, False, H, V, rep7, xstep=20, ystep=100)
    rows = []
    for w in words:
        if box7.contains(fitz.Rect(w[:4])) and 465 < w[0] < 480 and re.fullmatch(r"\d+", w[4]) and w[1] > 540:
            bw = [v for v in words if 485 < v[0] < 505 and abs(v[1] - w[1]) < 1 and re.fullmatch(r"[\d.]+", v[4])]
            if len(bw) == 1:
                rows.append(((w[1] + w[3]) / 2, float(w[4]) * 1e6, float(bw[0][4])))
    if sorted((f, b) for _, f, b in rows) != sorted([(10e6, 7.5), (5e6, 10.0), (10e6, 5.0), (3e6, 10.0)]):
        raise SystemExit(f"4F1 Fig.7 rows {rows}")
    subs = []
    for d in pg.get_drawings():
        if box7.contains(d["rect"]) and abs((d.get("width") or 0) - 1.0) < 0.05 and col(d.get("color")) == (0, 0, 0):
            subs += subpaths(d)
    if len(subs) != 4:
        raise SystemExit(f"4F1 Fig.7: {len(subs)} curves")
    c7 = {}
    used = set()
    for knots, dense in subs:
        end = max(knots, key=lambda p: p[0])
        row = min(rows, key=lambda r: abs(r[0] - end[1]))
        if abs(row[0] - end[1]) > 8 or row in used:
            raise SystemExit(f"4F1 Fig.7: curve end y {end[1]:.1f} has no label row ({rows})")
        used.add(row)
        c7[(row[1], row[2])] = Curve(row[1], row[2], knots, dense, X7, Y7, plot7)
    rep7["ends"] = {f"{f/1e6:g}MHz/{b:g}mT": (round(c.knots[0][0], 1), round(c.knots[-1][0], 1)) for (f, b), c in c7.items()}
    # checks: limits and Fig.6 vs Fig.7 at 100 C
    checks, cross = [], []
    for (f, b), lim in (((3e6, 10.0), 200), ((10e6, 5.0), 200)):
        for name, v in (("Fig.7", c7[(f, b)].at(100)), ("Fig.6", c6[f].at(b))):
            if v is not None:
                checks.append(dict(fig=name, f=f, B=b, T=100, value=round(v, 1), limit=lim, ok=v <= lim))
    for (f, b), c in c7.items():
        v6, v7 = c6[f].at(b), c.at(100)
        if v6 is not None:
            cross.append(dict(f=f, B=b, fig6=round(v6, 1), fig7=round(v7, 1), ratio=round(v7 / v6, 3)))
    report["4F1 checks"] = dict(limits=checks, cross=cross)
    if not cross:
        report["4F1 checks"]["REJECTED"] = "no shared condition between Fig.6 and Fig.7"
        return []
    bad = [c for c in cross if abs(c["ratio"] - 1) > CROSS_TOL] + [c for c in checks if not c["ok"]]
    if bad:
        report["4F1 checks"]["REJECTED"] = str(bad)
        return []
    pts = []
    for f, c in c6.items():
        (b0, _), (b1, _) = sorted(c.knots)
        bs = [b0, b1] + [m * 10 ** k for k in range(-1, 4) for m in (1, 2, 5) if b0 * 1.001 < m * 10 ** k < b1 / 1.001]
        for b in sorted(bs):
            pts.append(point(f, b / 1000, 100, c.at(b)))
    for (f, b), c in c7.items():
        t0, t1 = c.knots[0][0], c.knots[-1][0]
        for T in range(int(math.ceil(t0 - 0.5)), int(t1 + 0.5) + 1, 10):
            v = c.at(min(max(T, t0), t1))
            pts.append(point(f, b / 1000, T, v))
    rep7["samples"] = len(pts)
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_3f37")
    ap.add_argument("pdf_4f1")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()
    report, result, rc = {}, {}, 0
    for mat, fn, pdf in (("3F37", run_3f37, a.pdf_3f37), ("4F1", run_4f1, a.pdf_4f1)):
        pts = fn(pdf, report)
        keys = [json.dumps(p, sort_keys=True) for p in pts]
        conds = [json.dumps({k: v for k, v in p.items() if k != "value"}, sort_keys=True) for p in pts]
        if len(set(conds)) != len(conds):
            dup = sorted({c for c in conds if conds.count(c) > 1})
            report.setdefault("duplicates", {})[mat] = dup
        if len(pts) >= 4:
            result[mat] = pts
            print(f"{mat}: {len(pts)} points")
        else:
            rc = 1
            print(f"{mat}: REJECTED")
    for k, r in report.items():
        print(k, json.dumps({kk: vv for kk, vv in r.items() if kk not in ("curves", "lines")} if isinstance(r, dict) else r)[:1500])
    json.dump(result, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
