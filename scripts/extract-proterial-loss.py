#!/usr/bin/env python3
"""Extract core-loss curves from Proterial's Mn-Zn ferrite catalogue (vector PDF) (ABT #1518).

    python3 scripts/extract-proterial-loss.py hj-b3-e.pdf --json /tmp/prot-points.json \
            [--report /tmp/prot-report.json]

Source
------
Proterial, Ltd. (formerly Hitachi Metals), ferrite cores catalogue "hj-b3-e", 72 pages, PDF built
2023-01-18 (DocuWorks), section 4 "Material characteristics for Mn-Zn":
    https://www.proterial.com/e/products/soft_magnetic/pdf/hj-b3-e.pdf
Read 2026-09-30 (5,360,050 bytes, sha256 56bc2d2e4a35a5b37a05e6aa5a9d65ed99dcf487d20aed0dc74e785abe50edf3).
Test core stated on every material page: toroidal OD 25 mm, ID 15 mm, TH 5 mm (no Ve printed).

Grades and pages (PDF page numbers):
    ML24D p14 (table, "Core loss - Temperature" 100kHz/200mT) + p15 ("Core loss - Flux density"
          at 23 C and 100 C, 25/50/100/200 kHz)
    ML25D p16 + p17 (23 / 100 C)      ML33D p18 + p19 (23 / 100 C)
    MB19D p20 + p21 (23 / 120 C)      MB20D p22 + p23 (23 / 130 C)      MB28D p24 + p25 (23 / 100 C)
Printed Pcv tables (100 kHz, 200 mT) are on the material pages; MB19D and MB28D omit 23 C there,
and their 23 C values are taken from the same catalogue's p12 summary table (800 and 480).

Method -- nothing is digitised from pixels
------------------------------------------
Every figure is vector: the frame is a 1.2 pt rectangle, gridlines are 0.12 pt strokes, curves are
0.84 pt polylines. PyMuPDF reads them in page coordinates.

1. Calibration from the GRIDLINES, verified by the tick labels. Proterial's frames do not sit
   exactly on the scale (the log frames are ~0.5 pt off the decade gridlines), so the frame is
   not used. The printed tick labels give a first least-squares calibration (every label must fit
   within LABEL_TOL); each gridline is then snapped to the nearest 1..9 x 10^k (log) or
   label-step multiple (linear); the final calibration is the
   least-squares line through the snapped gridlines (snap and refit repeated until the assignment
   is stable), whose residual must stay below FIT_TOL. Some figures' grids are drawn unevenly
   (MB19D/MB28D: gridlines up to ~1.3 pt off a straight log scale, no trend), so points are read
   by interpolating between the two gridlines around them, as one reads a paper chart; the
   straight-line residual of every figure is in the report. Where the gridlines fail these checks
   but the printed tick labels fit a straight scale within LABEL_FIT_TOL and the frame edges sit
   on it, the tick-label scale is used instead (see calibrate()). Every drawn curve point is read
   on both the chosen scale and the other one; the two readings must agree within CAL_TOL (5 %)
   or the figure is dropped (report: cal_spread). Finally
   every tick label is checked again against it. A figure failing any check is dropped.
2. Curves are the 0.84 pt (MB20D p23: 0.6 pt Bezier) dark lines inside the frame that rise across it (>10 pt wide and
   >5 pt high: legend keys and label boxes are excluded). Pv-B lines are labelled by the one
   "xxkHz" word printed at their right end; the temperature is the one "xx℃" word inside the
   frame; the loss must rise with frequency at a common Bm (physics order), else the figure goes.
   The Pv-T figure must hold exactly one curve and print its condition (100kHz 200mT).
3. Points are exact reads of the drawn line: a polyline's vertices when it has at most MAX_VERTICES,
   otherwise N_SAMPLES abscissae spaced evenly over the drawn span. Never extrapolated.
4. Every figure is checked against the printed Pcv table (100 kHz/200 mT) at each temperature
   it covers; a figure reading more than TABLE_TOL off any printed value is dropped whole
   (#1006). A grade ships only if an accepted figure reproduces a printed value.

Output: {material: [MAS volumetricLossesPoint, ...]} in SI units; waveform "sinusoidal" (the
catalogue does not state the waveform; Proterial's core-loss measurements are sine-wave B-H
analyser data and the table is the usual sine Pcv), origin "manufacturer".
"""
import argparse
import importlib.util
import json
import math
import os
import re
import sys

import fitz  # PyMuPDF

_spec = importlib.util.spec_from_file_location(
    "tdk2022", os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract-tdk-loss.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

LABEL_TOL = 3.0      # pt, tick label centre vs calibration
SNAP_TOL = 2.0       # pt, gridline vs its nice value on the anchor scale
CAL_TOL = 0.05       # gridline scale vs tick-label scale, on every drawn curve point
LABEL_FIT_TOL = 0.3  # pt, tick labels vs their own straight scale (LABEL scale)
EDGE_TOL = 0.6       # pt, frame edge vs the extreme labelled value (LABEL scale)
FIT_TOL = 1.5        # pt, worst gridline residual of a straight-line fit (pattern sanity check)
TABLE_TOL = 0.10
MAX_VERTICES = 8
N_SAMPLES = 10

TABLE = {  # T degC -> Pcv kW/m^3 at 100 kHz / 200 mT
    "ML24D": {23: 680, 60: 450, 80: 400, 100: 400, 120: 480},
    "ML25D": {23: 600, 60: 300, 80: 250, 100: 300, 120: 420},
    "ML33D": {23: 400, 40: 365, 60: 340, 80: 330, 100: 355, 120: 420},
    "MB19D": {23: 800, 60: 540, 80: 430, 100: 370, 120: 350, 140: 420},
    "MB20D": {23: 700, 100: 420, 130: 370, 150: 420},
    "MB28D": {23: 480, 60: 310, 80: 400, 100: 520, 120: 620},
}
PAGES = {"ML24D": (14, 15), "ML25D": (16, 17), "ML33D": (18, 19),
         "MB19D": (20, 21), "MB20D": (22, 23), "MB28D": (24, 25)}


def cw(w):
    return ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)


def num(s):
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def g(log, v):
    return math.log10(v) if log else v


class Line:
    """Least-squares straight scale pos = a + b * g(v)."""
    def __init__(self, log, pts):
        self.log = log
        xs = [g(log, v) for v, _ in pts]
        ys = [p for _, p in pts]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        self.b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        self.a = my - self.b * mx
        self.res = max(abs(self.pos(v) - p) for v, p in pts)

    def pos(self, v):
        return self.a + self.b * g(self.log, v)

    def val(self, p):
        x = (p - self.a) / self.b
        return 10 ** x if self.log else x


class Piecewise:
    """Scale interpolated between known (value, position) pairs, end segments extended."""
    def __init__(self, log, pts):
        self.log = log
        byval = {}
        for v, p in pts:
            byval.setdefault(v, []).append(p)
        for v, ps in byval.items():
            # a gridline drawn twice (p20/p24: once as a line, once as a hairline rectangle)
            if max(ps) - min(ps) > 0.5:
                raise RuntimeError(f"two gridlines {max(ps) - min(ps):.2f} pt apart both snap to {v:g}")
        self.k = sorted((sum(ps) / len(ps), g(log, v)) for v, ps in byval.items())
        if len(self.k) < 2:
            raise RuntimeError("fewer than two calibration lines")
        d = [(b[1] - a[1]) for a, b in zip(self.k, self.k[1:])]
        if any(b[0] - a[0] < 0.5 for a, b in zip(self.k, self.k[1:])) or not (all(x > 0 for x in d) or all(x < 0 for x in d)):
            raise RuntimeError("gridlines are not strictly monotonic")

    def _seg(self, i):
        return self.k[max(0, min(len(self.k) - 2, i))], self.k[max(0, min(len(self.k) - 2, i)) + 1]

    def val(self, p):
        i = next((j for j in range(len(self.k) - 1) if p <= self.k[j + 1][0]), len(self.k) - 2)
        (p0, g0), (p1, g1) = self._seg(i)
        x = g0 + (p - p0) * (g1 - g0) / (p1 - p0)
        return 10 ** x if self.log else x

    def pos(self, v):
        x = g(self.log, v)
        gs = [q[1] for q in self.k]
        asc = gs[-1] > gs[0]
        i = next((j for j in range(len(gs) - 1) if (x <= gs[j + 1] if asc else x >= gs[j + 1])), len(gs) - 2)
        (p0, g0), (p1, g1) = self._seg(i)
        return p0 + (x - g0) * (p1 - p0) / (g1 - g0)


def calibrate(axis, log, labels, grid, edges, rep):
    """Two scales per axis, each with checks that can fail:
    GRID  tick labels -> anchors (the line drawn at each labelled value) -> every gridline snapped
          to its nice value by interpolating between anchors -> piecewise scale through all
          gridlines. Fails if a gridline is more than SNAP_TOL from its value, two gridlines snap
          to one value, the gridlines are more than FIT_TOL off one straight scale, or a label
          sits more than LABEL_TOL off the result.
    LABEL the straight least-squares scale through the printed tick labels, accepted only when the
          labels fit it within LABEL_FIT_TOL and both frame edges sit on it within EDGE_TOL.
    The GRID scale is used when it passes, the LABEL scale when only it passes (MB19D/MB20D/MB28D
    Pv-B: minor gridlines drawn unevenly, e.g. p25's top decade compressed by ~1 pt while the
    labels fit a log scale to 0.07 pt). The other scale -- the label scale, or the decade scale
    through the anchors -- is kept as .alt for the per-point spread check in read()."""
    if len(labels) < 3:
        raise RuntimeError(f"{axis}: {len(labels)} tick labels")
    c0 = Line(log, labels)
    if c0.res > LABEL_TOL:
        raise RuntimeError(f"{axis}: tick labels do not fit one scale (worst {c0.res:.2f} pt)")
    # The extreme labels usually sit on the frame (no gridline is drawn there), so the frame
    # edges count as anchor candidates; the GRID scale itself is built from gridlines alone.
    anchors = []
    for v, _ in labels:
        near = [p for p in list(grid) + list(edges) if abs(p - c0.pos(v)) <= LABEL_TOL]
        if near:
            anchors.append((v, min(near, key=lambda p: abs(p - c0.pos(v)))))
    if len(anchors) < 2:
        raise RuntimeError(f"{axis}: {len(anchors)} labelled values have a gridline")
    ca = Piecewise(log, anchors)
    try:
        vals = sorted(v for v, _ in labels)
        step = min(b - a for a, b in zip(vals, vals[1:])) if not log else None
        snapped, worst_snap = [], 0.0
        for p in grid:
            v = ca.val(p)
            if log:
                e = math.floor(math.log10(v))
                t = min(range(1, 11), key=lambda k: abs(v / 10 ** e - k)) * 10 ** e
            else:
                t = round(v / step) * step
            d = abs(ca.pos(t) - p)
            worst_snap = max(worst_snap, d)
            if d > SNAP_TOL:
                raise RuntimeError(f"gridline at {p:.2f} is {d:.2f} pt from {t:g}")
            snapped.append((t, p))
        if len({t for t, _ in snapped}) < 3:
            raise RuntimeError(f"{len(snapped)} gridlines, too few to calibrate")
        line = Line(log, snapped)
        if line.res > FIT_TOL:
            raise RuntimeError(f"gridlines do not form one scale (worst {line.res:.2f} pt)")
        c = Piecewise(log, snapped)
        worst = max(abs(c.pos(v) - p) for v, p in labels)
        if worst > LABEL_TOL:
            raise RuntimeError(f"a tick label is {worst:.2f} pt off the gridline calibration")
        rep[axis] = dict(scale="grid", labels=len(labels), anchors=len(anchors), grid=len(snapped),
                         snap_worst=round(worst_snap, 2), line_res=round(line.res, 2),
                         label_worst=round(worst, 2))
        c.alt = c0
        return c
    except RuntimeError as e:
        grid_err = str(e)
    edge_err = [abs(c0.pos(v) - p) for v in (min(vals), max(vals)) for p in edges
                if abs(c0.pos(v) - p) <= LABEL_TOL]
    if c0.res > LABEL_FIT_TOL or len(edge_err) != 2 or max(edge_err) > EDGE_TOL:
        raise RuntimeError(f"{axis}: grid scale failed ({grid_err}); label scale fit "
                           f"{c0.res:.2f} pt, frame edges {[round(x, 2) for x in edge_err]}")
    rep[axis] = dict(scale="labels", grid_rejected=grid_err, labels=len(labels),
                     label_res=round(c0.res, 3), edge_worst=round(max(edge_err), 2))
    c0.alt = ca
    return c0


def gridlines(d):
    """(horizontal y's, vertical x's, bbox) of a 0.12 pt gridline drawing ('l' items or hairline 're')."""
    h, v = [], []
    for it in d["items"]:
        if it[0] == "l":
            a, b = it[1], it[2]
            if abs(a.y - b.y) < 0.05:
                h.append((a.y, abs(a.x - b.x)))
            elif abs(a.x - b.x) < 0.05:
                v.append((a.x, abs(a.y - b.y)))
        elif it[0] == "re":
            r = it[1]
            if r.height < 0.3:
                h.append(((r.y0 + r.y1) / 2, r.width))
            elif r.width < 0.3:
                v.append(((r.x0 + r.x1) / 2, r.height))
    return h, v


def figures(pg):
    """[(plot box, title)] per figure panel (the 0.6 pt panel frames). The plot box is the stroked
    frame inside the panel (Proterial draws it 0.84..1.2 pt), or, where a figure has no frame
    (p16 Pv-T), the extent of its gridlines. The box only selects curves, gridlines and tick
    labels; the calibration comes from gridlines + labels (see calibrate)."""
    words = pg.get_text("words")
    draws = pg.get_drawings()
    out = []
    for d in draws:
        if not (d.get("color") and d["items"][0][0] == "re" and abs((d.get("width") or 0) - 0.6) < 0.05
                and d["rect"].width > 150 and d["rect"].height > 120):
            continue
        panel = d["rect"]
        frames = [e["rect"] for e in draws if e.get("color") and e["items"][0][0] == "re"
                  and len(e["items"]) == 1 and 0.8 <= (e.get("width") or 0) <= 1.3
                  and panel.contains(e["rect"]) and e["rect"].width > 100 and e["rect"].height > 80]
        if frames:
            box = max(frames, key=lambda r: r.width * r.height)
        else:
            xs, ys = [], []
            for e in draws:
                if e.get("color") and abs((e.get("width") or 0) - 0.12) < 0.02 and panel.contains(e["rect"]):
                    xs += [e["rect"].x0, e["rect"].x1]
                    ys += [e["rect"].y0, e["rect"].y1]
            if not xs:
                continue
            box = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
        title = " ".join(w[4] for w in sorted(words, key=lambda w: w[0])
                         if box.y0 - 30 < w[3] <= box.y0 + 1 and panel.x0 < w[0] < panel.x1
                         and num(w[4]) is None)
        out.append((box, title))
    return out


def read(pg, box, kind):
    words = [tuple(w[:4]) + (w[4].replace("℃", "°C"),) for w in pg.get_text("words")]
    draws = pg.get_drawings()
    inside = fitz.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1)
    gh, gv, curves = [], [], []
    for d in draws:
        if not d.get("color") or not inside.contains(d["rect"]):
            continue
        w = d.get("width") or 0
        if abs(w - 0.12) < 0.02:
            h, v = gridlines(d)
            gh += [y for y, L in h if L > 0.9 * box.width]
            gv += [x for x, L in v if L > 0.9 * box.height]
        elif 0.55 < w < 1.0 and max(d["color"]) < 0.4:   # curves: 0.84 pt (0.6 pt on p23)
            for dense, knots in T.subpaths(d):
                xs = [p[0] for p in dense]
                ys = [p[1] for p in dense]
                # a curve is a function of x that crosses the plot (frames, keys, label boxes are not)
                mono = all(b[0] >= a[0] - 0.05 for a, b in zip(dense, dense[1:]))
                if mono and max(xs) - min(xs) > 10 and max(ys) - min(ys) > 5:
                    curves.append(dict(dense=dense, knots=knots,
                                       lines=all(it[0] == "l" for it in d["items"])))
    gh, gv = sorted(set(round(v, 2) for v in gh)), sorted(set(round(v, 2) for v in gv))
    log = kind == "pv_b"
    # (the y axis's bottom label sits at the frame corner, level with the frame bottom)
    xl = [(num(w[4]), cw(w)[0]) for w in words if box.y1 + 3 < cw(w)[1] < box.y1 + 14
          and box.x0 - 5 < cw(w)[0] < box.x1 + 8 and num(w[4]) is not None]
    yl = [(num(w[4]), cw(w)[1]) for w in words if box.x0 - 30 < w[2] < box.x0 + 1
          and box.y0 - 6 < cw(w)[1] < box.y1 + 6 and num(w[4]) is not None]
    if log:
        xl = [(v, p) for v, p in xl if v > 0]
        yl = [(v, p) for v, p in yl if v > 0]
    rep = {"box": [round(v, 1) for v in box]}
    cx = calibrate("x", log, xl, gv, (box.x0, box.x1), rep)
    cy = calibrate("y", log, yl, gh, (box.y0, box.y1), rep)
    inbox = [w for w in words if box.contains(fitz.Rect(w[:4]))]
    # calibration spread: every drawn curve point read on the gridline scale and on the straight
    # tick-label scale must agree within CAL_TOL, else the figure's own grid is too uneven to trust
    worst = 0.0
    for c in curves:
        for x, y in c["dense"]:
            for a, v in ((cx, x), (cy, y)):
                worst = max(worst, abs(a.val(v) / a.alt.val(v) - 1))
    rep["cal_spread"] = round(worst, 4)
    if worst > CAL_TOL:
        raise RuntimeError(f"gridline and tick-label scales disagree by {worst:.1%} on a curve point")
    return words, inbox, curves, cx, cy, rep


def to_xy(cx, cy, pts):
    return [(cx.val(x), cy.val(y)) for x, y in pts]


def samples(cx, cy, c, log):
    if c["lines"] and len(c["knots"]) <= MAX_VERTICES:
        return to_xy(cx, cy, c["knots"])
    xy = to_xy(cx, cy, c["dense"])
    lo, hi = min(p[0] for p in xy), max(p[0] for p in xy)
    out = []
    for i in range(N_SAMPLES):
        t = i / (N_SAMPLES - 1)
        xq = min(max(lo * (hi / lo) ** t if log else lo + t * (hi - lo), lo), hi)
        out.append((xq, T.curve_value(xy, xq, log, log)))
    return out


def pv_b(pg, box):
    words, inbox, curves, cx, cy, rep = read(pg, box, "pv_b")
    temps = [w for w in inbox if re.fullmatch(r"-?\d+°C", w[4])]
    if len(temps) != 1:
        raise RuntimeError(f"{len(temps)} temperature labels in the figure")
    Tc = float(temps[0][4][:-2])
    khz = [w for w in words if re.fullmatch(r"\d+kHz", w[4]) and box.contains(fitz.Rect(w[:4]))]
    if len(curves) != len(khz) or not curves:
        raise RuntimeError(f"{len(curves)} curves but {len(khz)} frequency labels")
    labelled, used = [], set()
    for c in curves:
        x, y = max(c["dense"], key=lambda p: p[0])
        near = [w for w in words if re.fullmatch(r"\d+kHz", w[4]) and x - 2 <= w[0] <= x + 20
                and abs(cw(w)[1] - y) <= 10]
        if len(near) != 1:
            raise RuntimeError(f"curve ending at {x:.1f},{y:.1f}: {len(near)} kHz labels at its end")
        if near[0][4] in used:
            raise RuntimeError(f"label {near[0][4]} used by two curves")
        used.add(near[0][4])
        labelled.append((float(near[0][4][:-3]) * 1e3, c))
    labelled.sort(key=lambda t: t[0])
    xys = [to_xy(cx, cy, c["dense"]) for _, c in labelled]
    for (fa, a), (fb, b) in zip(zip([f for f, _ in labelled], xys), zip([f for f, _ in labelled][1:], xys[1:])):
        lo = max(min(p[0] for p in a), min(p[0] for p in b))
        hi = min(max(p[0] for p in a), max(p[0] for p in b))
        if lo > hi:
            continue
        xq = math.sqrt(lo * hi)
        va, vb = T.curve_value(a, xq, True, True), T.curve_value(b, xq, True, True)
        if not va < vb:
            raise RuntimeError(f"physics order violated: {fa:g} Hz {va:.4g} >= {fb:g} Hz {vb:.4g} at {xq:.1f} mT")
    pts, out = [], []
    for (f, c), xy in zip(labelled, xys):
        s = samples(cx, cy, c, True)
        pts += [T.point(f, x * 1e-3, Tc, y * 1e3) for x, y in s]
        out.append(dict(f=f, T=Tc, xy=xy, n=len(s)))
    rep["T"] = Tc
    return pts, out, rep


def pv_t(pg, box):
    words, inbox, curves, cx, cy, rep = read(pg, box, "pv_t")
    cond = T.parse_cond(" ".join(w[4] for w in inbox))
    if abs(cond.get("f", 0) - 100e3) > 1 or abs(cond.get("B", 0) - 0.2) > 1e-9:
        raise RuntimeError(f"figure prints {cond}, expected 100kHz/200mT")
    if len(curves) != 1:
        raise RuntimeError(f"{len(curves)} curves in the Pv-T figure")
    c = curves[0]
    s = samples(cx, cy, c, False)
    pts = [T.point(100e3, 0.2, x, y * 1e3) for x, y in s]
    return pts, [dict(f=100e3, T=None, xy=to_xy(cx, cy, c["dense"]), n=len(s))], rep


def table_check(mat, kind, curves):
    out = []
    for Tc, pv in TABLE[mat].items():
        for c in curves:
            if kind == "pv_b":
                if abs(c["f"] - 100e3) > 1 or c["T"] != Tc:
                    continue
                v = T.curve_value(c["xy"], 200.0, True, True)
                end = max(c["xy"])
                if v is None and end[0] >= 198.0:
                    # ML33D p19: the 100 kHz lines stop at 199.3 mT; read at the drawn end (loss
                    # rises with B, so the end value may sit at most ~1 % under the table)
                    v = end[1]
            else:
                v = T.curve_value(c["xy"], Tc, False, False)
            if v is not None:
                out.append(dict(kind=kind, T=Tc, table=pv, curve=round(v, 1), ratio=round(v / pv, 3)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()
    doc = fitz.open(a.pdf)
    result, report, rc = {}, {}, 0
    for mat, (p1, p2) in PAGES.items():
        head = re.sub(r"\s+", "", doc[p1 - 1].get_text())   # the heading is letter-spaced
        if "Material：" + mat not in head and "Material:" + mat not in head:
            raise SystemExit(f"p{p1} is not the {mat} page")
        figs = [(p1, b, "pv_t") for b, t in figures(doc[p1 - 1]) if "Core loss - Temperature" in t] + \
               [(p2, b, "pv_b") for b, t in figures(doc[p2 - 1]) if "Core loss - Flux density" in t]
        # a Pv-B figure whose title is not in the text layer (p23 right: outlined title) is still
        # identified by what it prints: >= 2 "xxkHz" labels and one "xx℃" label inside the frame
        pg2 = doc[p2 - 1]
        for b, t in figures(pg2):
            if t.strip():
                continue
            inb = [w[4] for w in pg2.get_text("words") if b.contains(fitz.Rect(w[:4]))]
            if sum(bool(re.fullmatch(r"\d+kHz", w)) for w in inb) >= 2 and \
                    sum(bool(re.fullmatch(r"-?\d+℃", w)) for w in inb) == 1:
                figs.append((p2, b, "pv_b"))
        kinds = [k for _, _, k in figs]
        if kinds.count("pv_t") != 1 or kinds.count("pv_b") not in (1, 2):
            raise SystemExit(f"{mat}: figures found {[(p, k) for p, _, k in figs]}")
        pts, figrep, checks_all = [], [], []
        if kinds.count("pv_b") == 1:
            # MB19D p21: the second Pv-B figure (120 C) has no text layer at all (title, ticks and
            # frequency labels are outlines), so nothing can verify it; it is not read.
            figrep.append(dict(page=p2, kind="pv_b", REJECTED="a Pv-B figure without any text layer (no title, tick or frequency labels to verify)"))
        for pn, box, kind in figs:
            try:
                p, curves, rep = (pv_t if kind == "pv_t" else pv_b)(doc[pn - 1], box)
            except RuntimeError as e:
                figrep.append(dict(page=pn, kind=kind, REJECTED=str(e)))
                continue
            checks = table_check(mat, kind, curves)
            rep.update(page=pn, kind=kind, table=checks, curves=[dict(f=c["f"], T=c["T"], n=c["n"]) for c in curves])
            bad = [c for c in checks if abs(c["ratio"] - 1) > TABLE_TOL]
            if bad:
                rep["REJECTED"] = ", ".join(f"{c['T']}C curve {c['curve']} vs table {c['table']}" for c in bad)
                figrep.append(rep)
                continue
            pts += p
            checks_all += checks
            figrep.append(rep)
        report[mat] = dict(points=len(pts), figures=figrep, table=checks_all)
        if not checks_all:
            report[mat]["REJECTED"] = "no accepted figure reproduces a printed table value"
            rc = 1
            print(f"{mat}: REJECTED")
        else:
            result[mat] = pts
            r = [c["ratio"] for c in checks_all]
            print(f"{mat}: {len(pts)} points, {len(r)} table checks, ratio {min(r):.3f}..{max(r):.3f}")
        for f in figrep:
            if "REJECTED" in f:
                print(f"    figure dropped: p{f['page']} {f['kind']}{' T=%g' % f['T'] if f.get('T') else ''}: {f['REJECTED']}")
    json.dump(result, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
