#!/usr/bin/env python3
"""Extract core-loss curves for DMEGC DMR95B, DMR25 and DMR40B from DMEGC's vector PDFs (ABT #1518).

    python3 scripts/extract-dmegc-loss.py DMR95B.pdf catalogue.pdf --json /tmp/dmegc-points.json \
            [--report /tmp/dmegc-report.json]

Sources
-------
A. DMEGC "DMR95B Material Characteristic", DMR95B-REV.B dated 2019-04 (PDF written by Word
   2022-12-20), 2 pages:
       https://www.dmegc.de/uploads/20230401/DMR95B%20Material%20Characteristics.pdf
   Read 2026-09-30 (268,113 bytes, sha256 f18cc047ebe32c02741b363f28f78eb6f0aec3167d24e1c8a47552def0f83427).
   p1: typical-value table, Pv at 100 kHz/200 mT: 25 C 350, 100 C 300, 120 C 360 mW/cm3.
   p2: "Power Loss PV vs Temperature" (100kHz, 200mT) and "Power Loss PV vs Flux Density"
       (25 C solid / 100 C dashed, 25/50/100/200/300/500 kHz). Test core printed under the figures:
       standard toroid phi25 x phi15 x 8 (no Ve printed).
B. DMEGC MnZn material catalogue (Word 2007 PDF, 2017-04-06, 13 pages), as re-hosted on dianyuan.com
   (DMEGC's own copy is no longer online):
       https://www.dianyuan.com/upload/community/2017/09/05/1504577498-77035.pdf
   Read 2026-09-30 (497,774 bytes, sha256 0ba812c9c6dde95e0289c4cec3c35532286f125c6ce046e4b48f1e88e66b7478).
   p2 table "Low loss MnZn" (DMR40/44/47/40B) + p3 Pcv-T figure; p4 table "Wide temperature low
   loss" (DMR25/95/95L/95B/96/96A) + p5 Pcv-T figure. The figures carry no condition; the tables'
   row is "Core loss 100kHz/200mT", except DMR40B ("** At 25 kHz/200mT") and DMR96A ("* At
   300kHz/100mT").

Method -- nothing is digitised from pixels
------------------------------------------
All figures are vector (Word charts): frames and gridlines are single strokes, curves are dense
polylines (Pv-T) or polylines through the data points (Pv-B: one vertex per 50 mT gridline; the
100 C lines are dashed, i.e. drawn as dash segments, and their vertices are recovered from the
kinked dash that spans a gridline or, where a gridline falls in a gap, from the two neighbouring
dashes, which must meet there within DASH_TOL).
1. Calibration from the gridlines; every printed tick label must sit on it within LABEL_TOL and
   the gridlines must be one straight (lin or log) scale within GRID_TOL.
2. Curves are identified by colour against the legend swatches (and dash style on the Pv-B figure).
3. Every figure is checked against the maker's printed table at each temperature it covers; a
   figure more than TABLE_TOL off any printed value is dropped whole (#1006), never adjusted.
4. Pv-T points are exact reads of the drawn line at the span start and every 10 C to its end.
   Pv-B points are the drawn vertices.
Rejects (by design, see report): the DMR95B Pv-B figure (25 C / 100 kHz line reads 309 = 0.883 x the
table 350 at 200 mT, while its own Pv-T curve reads 358 there), the catalogue's DMR40B curve (the figure states no condition and DMR40B's only
printed values are at 25 kHz/200 mT, which the curve does not reproduce). DMR40B therefore ships
its printed table values (25 kHz, 200 mT, 25/60/100/120 C) only.

Output: {material: [MAS volumetricLossesPoint, ...]} in SI; waveform "sinusoidal" (not stated by
DMEGC; the usual sine Pcv), origin "manufacturer".
"""
import argparse
import json
import math
import re
import sys

import fitz

GRID_TOL = 0.6       # pt, gridline vs straight scale
LABEL_TOL = 2.5      # pt, tick-label centre vs calibrated position
DASH_TOL = 0.4       # pt, two neighbouring dashes extrapolated to a vertex
TABLE_TOL = 0.10
EPS = 0.05

RED, GREEN, BLUE, BLACK, CYAN, MAGENTA = (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0), (0, 1, 1), (1, 0, 1)

# printed tables (verified against the page text in check_table_text)
TABLE_95B = {25: 350, 100: 300, 120: 360}                                   # A p1, 100 kHz 200 mT
TABLE_CAT = {  # B p2 / p4, 100 kHz 200 mT unless noted
    "DMR40": {25: 600, 60: 450, 100: 410, 120: 500},
    "DMR44": {25: 600, 60: 400, 100: 300, 120: 380},
    "DMR47": {25: 600, 60: 400, 100: 280, 120: 380},
    "DMR40B": {25: 90, 60: 75, 100: 75, 120: 95},                           # 25 kHz 200 mT
    "DMR25": {25: 700, 80: 450, 100: 400, 120: 350, 140: 350},
    "DMR95": {25: 350, 80: 280, 100: 310, 120: 350},
    "DMR95L": {0: 360, 25: 320, 100: 290, 120: 350},
    "DMR95B": {25: 350, 100: 300, 120: 360},
    "DMR96": {-20: 360, 0: 320, 25: 290, 60: 270, 80: 270, 100: 280, 120: 320, 140: 370},
}


def col(c):
    return tuple(round(v, 2) for v in c) if c else None


def fit_line(pairs):
    n = len(pairs)
    sx = sum(p for p, _ in pairs); sy = sum(v for _, v in pairs)
    sxx = sum(p * p for p, _ in pairs); sxy = sum(p * v for p, v in pairs)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return a, (sy - a * sx) / n


class Axis:
    """value(pos) along one axis; log axes work in log10."""

    def __init__(self, grid, labels, log, step, report, name):
        self.log = log
        f = (lambda v: math.log10(v)) if log else (lambda v: v)
        # first calibration from labels (value -> position)
        a, b = fit_line([(f(v), p) for p, v in labels])
        snapped = []
        for g in grid:
            u = (g - b) / a
            if log:
                # nearest value with `step` significant digits (1: 1..9 x 10^k; 2: the Pv-B x axis
                # has a gridline every 10 mT from 50 to 300)
                k = math.floor(u + 1e-9)
                n = 10 ** (step - 1)
                cands = [math.log10(m / n * 10 ** kk) for kk in (k - 1, k, k + 1) for m in range(n, 10 * n)]
                vv = min(cands, key=lambda c: abs(c - u))
            else:
                vv = round(u / step) * step
            snapped.append((vv, g))
        a, b = fit_line(snapped)
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


def figure(page, box, xstep, ystep, xlog, ylog, report):
    """Gridlines and tick labels inside/around box -> (X, Y) axes."""
    H, V = set(), set()
    for d in page.get_drawings():
        r = d["rect"]
        if not box.contains(r) or len(d["items"]) != 1 or d["items"][0][0] != "l":
            continue
        p, q = d["items"][0][1], d["items"][0][2]
        if abs(p.y - q.y) < 0.01 and abs(p.x - q.x) > 0.4 * box.width:
            H.add(round(p.y, 2))
        elif abs(p.x - q.x) < 0.01 and abs(p.y - q.y) > 0.4 * box.height:
            V.add(round(p.x, 2))
    V = sorted(V); H = sorted(H)
    # merge double frame strokes
    V = [v for i, v in enumerate(V) if i == 0 or v - V[i - 1] > 1.0]
    H = [h for i, h in enumerate(H) if i == 0 or h - H[i - 1] > 1.0]
    xl, yl = [], []
    for w in page.get_text("words"):
        if not re.fullmatch(r"-?\d+(\.\d+)?", w[4]):
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if V[0] - 8 <= cx <= V[-1] + 8 and H[-1] < cy < H[-1] + 16:
            xl.append((cx, float(w[4])))
        elif H[0] - 8 <= cy <= H[-1] + 8 and V[0] - 30 < w[2] < V[0]:
            yl.append((cy, float(w[4])))
    X = Axis(V, xl, xlog, xstep, report, "x")
    Y = Axis(H, yl, ylog, ystep, report, "y")
    return X, Y


def polylines(page, box, color, min_items=5):
    out = []
    for d in page.get_drawings():
        if col(d.get("color")) != color or not box.contains(d["rect"]) or len(d["items"]) < min_items:
            continue
        pts = []
        for it in d["items"]:
            if it[0] != "l":
                raise RuntimeError(f"unexpected path item {it[0]}")
            for p in (it[1], it[2]):
                if not pts or abs(pts[-1][0] - p.x) > 1e-6 or abs(pts[-1][1] - p.y) > 1e-6:
                    pts.append((p.x, p.y))
        out.append(pts)
    return out


def interp(pts, x):
    pts = sorted(pts)
    if not pts[0][0] - EPS <= x <= pts[-1][0] + EPS:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 - EPS <= x <= x1 + EPS:
            return y0 if x1 == x0 else y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return None


def point(f, B, T, pv_mw_cm3):
    sig = lambda v, n=4: float(f"{v:.{n}g}")
    return {"magneticFluxDensity": {"frequency": sig(f, 6), "magneticFluxDensity": {"processed": {
        "label": "sinusoidal", "peak": sig(B), "offset": 0.0}}},
        "temperature": sig(T, 4), "value": sig(pv_mw_cm3 * 1000.0), "origin": "manufacturer"}


def pvt_samples(X, Y, line):
    x0, x1 = min(p[0] for p in line), max(p[0] for p in line)
    t0, t1 = X.value(x0), X.value(x1)
    ts = [round(t0)] + [t for t in range(int(math.ceil(t0 / 10)) * 10, int(t1 + 0.5) + 1, 10) if t > round(t0)]
    out = []
    for t in ts:
        y = interp(line, min(max(X.pos(t), x0), x1))
        out.append((t, Y.value(y)))
    return out


def table_ratio(samples_fn, table):
    out = []
    for T, pv in sorted(table.items()):
        v = samples_fn(T)
        if v is not None:
            out.append(dict(T=T, table=pv, curve=round(v, 1), ratio=round(v / pv, 3)))
    return out


def check_table_text(text, needles, where):
    flat = re.sub(r"\s+", " ", text)
    for n in needles:
        if n not in flat:
            raise SystemExit(f"{where}: expected '{n}' in the page text")


def dmr95b_pvt(doc, report):
    pg = doc[1]
    box = fitz.Rect(80, 280, 290, 450)
    rep = report.setdefault("A_p2_pv_t", {})
    X, Y = figure(pg, box, 20, 50, False, False, rep)
    words = " ".join(w[4] for w in pg.get_text("words") if box.contains(fitz.Rect(w[:4])))
    if "100kHz，200mT" not in words:
        raise SystemExit("A p2 Pv-T: condition label missing")
    lines = polylines(pg, box, RED)
    if len(lines) != 1:
        raise SystemExit(f"A p2 Pv-T: {len(lines)} red curves")
    line = lines[0]
    samples = pvt_samples(X, Y, line)
    fn = lambda T: (lambda y: None if y is None else Y.value(y))(interp(line, X.pos(T)))
    rep["table"] = table_ratio(fn, TABLE_95B)
    rep["samples"] = [(t, round(v, 1)) for t, v in samples]
    return samples, rep, fn


def dash_vertices(segs, xs):
    """Vertices of a dashed polyline at abscissae xs from its dash segments [(p0,p1,...)]."""
    out = {}
    lo = min(p[0] for s in segs for p in s); hi = max(p[0] for s in segs for p in s)
    for xv in xs:
        if xv < lo - EPS or xv > hi + EPS:
            continue
        hit = [p[1] for s in segs for p in s if abs(p[0] - xv) < EPS]
        if hit:
            out[xv] = sum(hit) / len(hit)
            continue
        left = [s for s in segs if max(p[0] for p in s) < xv]
        right = [s for s in segs if min(p[0] for p in s) > xv]
        if not left or not right:
            continue
        L = max(left, key=lambda s: max(p[0] for p in s)); R = min(right, key=lambda s: min(p[0] for p in s))
        (a0, a1), (b0, b1) = sorted(L)[-2:], sorted(R)[:2]
        yl = a0[1] + (xv - a0[0]) / (a1[0] - a0[0]) * (a1[1] - a0[1])
        yr = b0[1] + (xv - b0[0]) / (b1[0] - b0[0]) * (b1[1] - b0[1])
        if abs(yl - yr) > DASH_TOL:
            raise RuntimeError(f"dashes disagree at x={xv:.2f}: {yl:.2f} vs {yr:.2f}")
        out[xv] = (yl + yr) / 2
    return out


def dmr95b_pvb(doc, report):
    """Read the Pv-B figure and check it; returns (points, rep) -- points empty if rejected."""
    pg = doc[1]
    box = fitz.Rect(330, 470, 530, 640)
    rep = report.setdefault("A_p2_pv_b", {})
    X, Y = figure(pg, box, 2, 1, True, True, rep)
    legend = fitz.Rect(440, 574, 526, 620)
    freqs = {BLUE: 25e3, GREEN: 50e3, RED: 100e3, CYAN: 200e3, BLACK: 300e3, MAGENTA: 500e3}
    grid_x = [X.pos(b) for b in (50, 100, 150, 200, 250, 300)]
    curves = {}
    for c, f in freqs.items():
        solid, dashes = [], []
        for d in pg.get_drawings():
            if col(d.get("color")) != c or not box.contains(d["rect"]) or legend.contains(d["rect"]) \
                    or abs((d.get("width") or 0) - 1.0) > 0.05:
                continue
            seg = []
            for it in d["items"]:
                for p in (it[1], it[2]):
                    if not seg or abs(seg[-1][0] - p.x) > 1e-6 or abs(seg[-1][1] - p.y) > 1e-6:
                        seg.append((p.x, p.y))
            (solid if len(d["items"]) >= 4 and d["rect"].width > 100 else dashes).append(seg)
        if len(solid) != 1:
            raise RuntimeError(f"{f/1e3:g} kHz: {len(solid)} solid lines")
        sv = {xv: interp(solid[0], xv) for xv in grid_x}
        curves[(25, f)] = {X.value(x): Y.value(y) for x, y in sv.items() if y is not None}
        dv = dash_vertices(dashes, grid_x)
        curves[(100, f)] = {X.value(x): Y.value(y) for x, y in dv.items()}
    # physics: loss rises with f at each B and T
    for T in (25, 100):
        for b in (50, 100, 150, 200, 250, 300):
            vals = [curves[(T, f)].get(k) for f in sorted(freqs.values()) for k in curves[(T, f)] if abs(k - b) < 0.5]
            if any(v2 <= v1 for v1, v2 in zip(vals, vals[1:])):
                raise RuntimeError(f"loss not rising with f at {b} mT {T} C")
    rep["curves"] = {f"{T}C {f/1e3:g}kHz": {round(k): round(v, 2) for k, v in sorted(d.items())} for (T, f), d in curves.items()}
    checks = []
    for T in (25, 100):
        v = [v for k, v in curves[(T, 100e3)].items() if abs(k - 200) < 0.5][0]
        checks.append(dict(T=T, table=TABLE_95B[T], curve=round(v, 1), ratio=round(v / TABLE_95B[T], 3)))
    rep["table"] = checks
    bad = [c for c in checks if abs(c["ratio"] - 1) > TABLE_TOL]
    if bad:
        rep["REJECTED"] = "; ".join(f"{c['T']} C 100 kHz/200 mT reads {c['curve']} vs table {c['table']} ({c['ratio']})" for c in bad)
        return [], rep
    pts = [point(f, b / 1000, T, v) for (T, f), d in curves.items() for b, v in sorted(d.items())]
    return pts, rep


def catalogue_pvt(doc, pidx, legend_names, report, key):
    pg = doc[pidx]
    box = fitz.Rect(150, 130, 450, 365)
    rep = report.setdefault(key, {})
    X, Y = figure(pg, box, 10 if pidx == 4 else 20, 50 if pidx == 4 else 100, False, False, rep)   # gridline steps
    # legend: swatch colour -> name (swatch = short 1-item stroke left of the name)
    words = [w for w in pg.get_text("words") if box.contains(fitz.Rect(w[:4]))]
    swatch = {}
    for d in pg.get_drawings():
        r = d["rect"]
        if box.contains(r) and len(d["items"]) == 1 and 15 < r.width < 25 and r.height < 0.5:
            nm = [w[4] for w in words if w[0] > r.x1 and w[0] - r.x1 < 6 and abs((w[1] + w[3]) / 2 - r.y0) < 3]
            if len(nm) == 1:
                swatch[nm[0]] = col(d["color"])
    if sorted(swatch) != sorted(legend_names):
        raise SystemExit(f"{key}: legend {swatch}")
    curves, fns = {}, {}
    for nm, c in swatch.items():
        ls = polylines(pg, box, c)
        if len(ls) != 1:
            raise SystemExit(f"{key}: {nm} {len(ls)} lines")
        curves[nm] = ls[0]
        fns[nm] = (lambda line: lambda T: (lambda y: None if y is None else Y.value(y))(interp(line, X.pos(T))))(ls[0])
    rep["table"] = {nm: table_ratio(fns[nm], TABLE_CAT[nm]) for nm in swatch if nm in TABLE_CAT}
    return X, Y, curves, fns, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dmr95b_pdf")
    ap.add_argument("catalogue_pdf")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()
    A, B = fitz.open(a.dmr95b_pdf), fitz.open(a.catalogue_pdf)
    check_table_text(A[0].get_text(), ["DMR95B", "100kHz, 200mT", "350", "300", "360"], "A p1")
    check_table_text(B[1].get_text(), ["DMR40B", "90**", "75**", "95**", "At 25 kHz/200mT"], "B p2")
    check_table_text(B[3].get_text(), ["DMR25", "700", "450", "400", "At 300kHz/100mT"], "B p4")
    report, result, rc = {}, {}, 0

    # DMR95B
    s95, rep_t, fn_a = dmr95b_pvt(A, report)
    bad = [c for c in rep_t["table"] if abs(c["ratio"] - 1) > TABLE_TOL]
    pts95 = []
    if bad:
        rep_t["REJECTED"] = str(bad)
    else:
        pts95 += [point(100e3, 0.2, T, v) for T, v in s95]
    pvb_pts, rep_b = dmr95b_pvb(A, report)
    pts95 += pvb_pts

    # catalogue p5: DMR25 (stored) + DMR95B (cross-check of figure A only)
    X5, Y5, c5, f5, rep5 = catalogue_pvt(B, 4, ["DMR25", "DMR95", "DMR95B", "DMR96", "DMR96A"], report, "B_p5_pv_t")
    rep5["DMR95B_vs_figureA"] = [dict(T=T, A=round(v, 1), B=round(f5["DMR95B"](T), 1),
                                      ratio=round(f5["DMR95B"](T) / v, 3)) for T, v in s95 if f5["DMR95B"](T)]
    fig_bad = [(nm, c) for nm in ("DMR25", "DMR95", "DMR95B", "DMR96") for c in rep5["table"][nm]
               if abs(c["ratio"] - 1) > TABLE_TOL]
    rep5["figure_check_fails"] = fig_bad
    pts25 = []
    if [c for nm, c in fig_bad if nm == "DMR25"]:
        rep5["DMR25_REJECTED"] = "DMR25 curve off its table"
    else:
        pts25 = [point(100e3, 0.2, T, v) for T, v in pvt_samples(X5, Y5, c5["DMR25"])]
        rep5["DMR25_samples"] = [(T, round(v, 1)) for T, v in pvt_samples(X5, Y5, c5["DMR25"])]

    # catalogue p3: DMR40B -- figure checked on DMR40/44/47, DMR40B curve vs its 25 kHz table
    X3, Y3, c3, f3, rep3 = catalogue_pvt(B, 2, ["DMR40", "DMR44", "DMR47", "DMR40B"], report, "B_p3_pv_t")
    rep3["DMR40B_REJECTED"] = ("figure states no condition; DMR40B's printed values are at 25 kHz/200 mT and the "
                               "curve reads %s of them" % [c["ratio"] for c in rep3["table"]["DMR40B"]])
    pts40b = [point(25e3, 0.2, T, v) for T, v in sorted(TABLE_CAT["DMR40B"].items())]

    for nm, pts in (("DMR95B", pts95), ("DMR25", pts25), ("DMR40B", pts40b)):
        if len(pts) >= 4:
            result[nm] = pts
            print(f"{nm}: {len(pts)} points")
        else:
            rc = 1
            print(f"{nm}: REJECTED")
    for k, r in report.items():
        print(k, json.dumps({kk: vv for kk, vv in r.items() if kk not in ("curves",)}))
    json.dump(result, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
