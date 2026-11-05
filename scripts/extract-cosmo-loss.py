#!/usr/bin/env python3
"""Extract core-loss curves for 11 Cosmo Ferrites MnZn power grades from Cosmo's raster data sheets (ABT #2266 / #1518).

    python3 -I scripts/extract-cosmo-loss.py <dir with CF*.pdf> --json /tmp/cosmo_points.json \
            [--report /tmp/cosmo_report.json] [--overlay-dir /tmp/cosmo_overlays]

Sources
-------
Cosmo Ferrites Ltd. (India) "Material Specifications" data sheets, one page each (Microsoft Word for
Microsoft 365), linked from https://www.cosmoferrites.com/product-store/material :
    https://www.cosmoferrites.com/uploads/power/<grade>.pdf
CF297A is not linked from that page; the file exists at the same path. Read 2026-11-04 (UTC):
    CF124    292,264 B  sha256 8d4a518cf605d2d0a5b09e383f7fb252da415dcd12169963302fb90ee2a07490
    CF130    319,590 B  sha256 e1a5b09d24bcdbbb79896b3203f246c395727a63c9072a82a387b6e0485bb239
    CF138    370,638 B  sha256 6814a98f40a7f00203fab1b8be529fb3e7d4f686b7982b91c35a43fac0065ebc
    CF139    370,280 B  sha256 8a2adeb22f01759ef082112997cd3ccb05bc4bb58c5abf30bdac884d38fed408
    CF249    384,538 B  sha256 19ac340197c4534b7128c30ace6977fba4efbb7c0fd97808e2c7df847d4425bc
    CF292    360,792 B  sha256 d1209382bc9b6204bfa33e9d3e3581a0dc411ee0a89db1c308b08a3a4f76a786
    CF295    363,664 B  sha256 379500295e9abd381d7e3443cc589e560b3d62862a83aff989fd315ec0cd9985
    CF296    366,614 B  sha256 64fb3746510a34d9b88c7c7a675813e3055fec6734f1b058ef9a7b9449d88a09
    CF296A   364,051 B  sha256 6aa235195878538e1d27a22038da8ecd1a8a45c40f8bb786c69acf0ff1407102
    CF297    366,133 B  sha256 ad7a6618cb6741de94e513ecdefa1b73a73d32a686e603416782bed5d77dfcbc
    CF297A   373,100 B  sha256 b255f37e2f125a79e648cd503181a122c6b06cb10c82f71856db975e2d70a2fb
The catalogue https://www.cosmoferrites.com/uploads/Catalogue_2026.pdf (2,224,681 B, sha256
b60c59a097159ce5daca518ac648a8303fbc242caa477935501d1444f92d5519, the
"Cosmo-Ferrites-Catalogue-2026" the MAS records cite) prints only the material tables (pp. 4-5, the
same Pcv limits as the sheets) and no loss figure; it is not read here.

What the sheets publish (test core printed on every sheet: toroid 25 x 15 x 12 mm, no Ve):
    CF124   table 100 C: 16 kHz/200 mT = 90, 25 kHz/200 mT = 130 kW/m3 (typical values);
            Pv-T figure, two curves 25 kHz/200 mT and 25 kHz/100 mT.
    CF130   table 100 C: 16 kHz/200 mT <= 130, 100 kHz/200 mT <= 800; Pv-T figure 100 kHz/200 mT.
    CF249   table 100 C: 500 kHz/50 mT <= 90, 1 MHz/50 mT <= 480; Pv-T figure (500 kHz/50 mT,
            1 MHz/50 mT); Pv-B figures at 25 and 100 C, 200/300/500/700/1000 kHz.
    CF292   table 100 C: 100 kHz/100 mT <= 70, 100 kHz/200 mT <= 410; Pv-T 100 kHz/200 mT;
            Pv-B 25/100 C at 50/100/200 kHz.
    CF295, CF296, CF297, CF297A   table 25/100 C 100 kHz/200 mT; Pv-T 100 kHz/200 mT; Pv-B 25/100 C
            (CF295/CF296: 100/200/300 kHz; CF297/CF297A: 50/100/200 kHz).
    CF296A  table 25/80/100 C 100 kHz/200 mT; Pv-T; Pv-B 25/100 C at 100/200/300 kHz.
    CF138, CF139   table 100 C: 100 kHz/100 mT and 100 kHz/200 mT; their three loss figures are
            byte-identical embedded images to CF297's (same sha256) -- not data of these grades.
All "<=" values are guaranteed maxima; CF124's are plain values.

Method -- raster (every figure is an embedded Excel-chart bitmap; nothing is vector)
----------------------------------------------------------------------------------
The embedded image is read at its native resolution (PyMuPDF extract, no re-rendering).
1. Calibration from the GRIDLINES, verified against the printed tick labels. Tick-label positions are
   found as text blobs left of / below the plot; their VALUES are the ones printed (read by eye,
   in FIGS). The labels give a first fit; every detected gridline is then snapped to the nearest
   label-step multiple (linear) or 1..9 x 10^k (log) and the final scale is the least-squares line
   through the snapped gridlines. Every gridline must sit within GRID_TOL px of that scale and
   every tick label within LABEL_TOL px, else the figure is dropped.
2. Pv-T curves: the black (CF249: also orange) line inside the plot. Per pixel column the curve is
   the centre of its vertical run of curve-coloured pixels. Legend keys printed inside the plot
   (CF124, CF249) are masked; a column whose run touches a mask or is thinner than the line is not
   used. Two curves of one colour (CF124) are separated top/bottom and labelled by the legend and
   the physics order (200 mT above 100 mT); dash gaps (CF124 25 kHz/100 mT) are bridged only by
   linear interpolation between drawn dashes <= DASH_GAP px apart. Samples: the first multiple of 5
   at or after the drawn start, then every 10 C to the drawn end. Never extrapolated.
3. Pv-B figures: the data are the chart markers (Excel draws straight segments between them).
   Each series is separated by its legend colour (line colour + marker fill); markers are the
   blobs that survive a morphological opening that removes the thin line. A marker's B is its
   blob centre on the B axis, which must lie within B_SNAP of 25/50/100/200 mT (the stored B is
   that nominal value); its Pv is the centre of the marker's vertical extent in its centre column
   (unopened mask: the opening clips a triangle's apex). For circles and squares that must agree
   with the opened blob's centre within MARKER_TOL px. The series lines are Excel smoothed lines
   (curved between markers), so they are not read: only the markers are data. The legend
   colour order top->bottom must equal the configured order, and at every common B the loss must
   rise with frequency, else the figure is dropped. Markers outside the plot (CF296 100 C,
   100 kHz at 50 mT lies below 10 mW/cc) are not drawn and so not read.
4. Table check (#1006), per curve: every curve is read at every printed table condition it covers;
   a curve more than TABLE_TOL off a printed value is dropped (never rescaled). Other curves of the
   same figure with no printed condition are kept only if a curve of that figure passed (they share
   its calibration, as for the Samwha/Proterial Pv-T figures). A figure that covers no printed
   condition at all (the 25 C Pv-B figures of CF292 and CF249: their tables are 100 C only) is kept
   only if it agrees within TABLE_TOL with an accepted Pv-T curve of the same sheet at every
   condition both cover (25 C), else dropped. The printed values themselves are not output (they
   are limits, and the accepted curves reproduce them), except CF124's 16 kHz/200 mT/100 C value, a
   plain (typical) value at a frequency no curve covers.
   Where a Pv-T sample and a Pv-B marker give the same condition (100 kHz/200 mT -- CF249: 1 MHz/50 mT
   -- at 25 and 100 C) only the marker is output; both readings are in the report.
5. Accepted figures of different grades that read identically are reported (_same_chart_on_two_sheets):
   CF296's 25 C Pv-B chart is CF295's (same pixels in a wider frame); both kept, flagged.
6. CF138/CF139: their figures are byte-identical to CF297's (sha256 of the embedded images), and
   they fail the CF138/CF139 tables (ratios 0.74-0.88): rejected, nothing output.

Result (2026-11-05; details in the --report JSON): 228 points for 9 grades. Pv-T curves read the printed
tables at 0.95-0.98, Pv-B markers at 0.90-1.10. Rejected: CF249 Pv-T 500 kHz/50 mT
(100 C reads 80.7 vs <= 90, ratio 0.897), CF138, CF139 (all figures).

Output: JSON array of MAS core-material fragments
    {"name", "manufacturerInfo": {"name": "Cosmo Ferrites"}, "volumetricLosses": {"default": [[points]]}}
in SI (Hz, T, W/m3, C); waveform "sinusoidal" (the sheets do not state it; standard sine Pcv),
origin "manufacturer". mW/cc == kW/m3; values are stored as kW/m3 * 1000.
"""
import argparse
import hashlib
import json
import math
import os
import site
import sys

sys.path.append(site.getusersitepackages())   # PyMuPDF/numpy/scipy live in the user site; run with -I
import fitz  # noqa: E402
import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

GRID_TOL = 1.6      # px, gridline vs fitted scale
LABEL_TOL = 3.5     # px, tick-label blob centre vs fitted scale
TABLE_TOL = 0.10
B_SNAP = 0.06       # relative
MARKER_TOL = 1.5    # px, column centre vs opened-blob centre (circles, squares)
DASH_GAP = 12       # px (CF124 dash-dot: dash, dot, dash with ~11 px between drawn dashes)

URL = "https://www.cosmoferrites.com/uploads/power/{}.pdf"
SOURCES = {   # bytes, sha256 -- read 2026-11-04 UTC
    "CF124": (292264, "8d4a518cf605d2d0a5b09e383f7fb252da415dcd12169963302fb90ee2a07490"),
    "CF130": (319590, "e1a5b09d24bcdbbb79896b3203f246c395727a63c9072a82a387b6e0485bb239"),
    "CF138": (370638, "6814a98f40a7f00203fab1b8be529fb3e7d4f686b7982b91c35a43fac0065ebc"),
    "CF139": (370280, "8a2adeb22f01759ef082112997cd3ccb05bc4bb58c5abf30bdac884d38fed408"),
    "CF249": (384538, "19ac340197c4534b7128c30ace6977fba4efbb7c0fd97808e2c7df847d4425bc"),
    "CF292": (360792, "d1209382bc9b6204bfa33e9d3e3581a0dc411ee0a89db1c308b08a3a4f76a786"),
    "CF295": (363664, "379500295e9abd381d7e3443cc589e560b3d62862a83aff989fd315ec0cd9985"),
    "CF296": (366614, "64fb3746510a34d9b88c7c7a675813e3055fec6734f1b058ef9a7b9449d88a09"),
    "CF296A": (364051, "6aa235195878538e1d27a22038da8ecd1a8a45c40f8bb786c69acf0ff1407102"),
    "CF297": (366133, "ad7a6618cb6741de94e513ecdefa1b73a73d32a686e603416782bed5d77dfcbc"),
    "CF297A": (373100, "b255f37e2f125a79e648cd503181a122c6b06cb10c82f71856db975e2d70a2fb"),
}

# colours (Excel default palette as drawn)
BLACK = "black"
ORANGE_L = (237, 125, 49)
YELLOW = (255, 192, 0)
BLUE = (68, 114, 196)
LBLUE = (91, 155, 213)
PURPLE = (112, 48, 160)
GREEN = (146, 208, 80)
GRAY = (165, 165, 165)

LIN = lambda a, b, s: [a + i * s for i in range(int(round((b - a) / s)) + 1)]
DEC = lambda a, b: [10.0 ** k for k in range(int(round(math.log10(a))), int(round(math.log10(b))) + 1)]
# (legend label, f, line colour, marker colours, marker shape)
F3 = [("200 KHz", 200e3, BLUE, [BLUE], "triangle"), ("100 KHz", 100e3, PURPLE, [PURPLE], "circle"),
      ("50 KHz", 50e3, ORANGE_L, [YELLOW, ORANGE_L], "square")]
F1 = [("100 KHz", 100e3, GRAY, [GRAY], "square"), ("200 KHz", 200e3, GREEN, [GREEN], "circle"),
      ("300 KHz", 300e3, BLUE, [BLUE], "triangle")]
F249 = [("200 KHz", 200e3, GREEN, [GREEN], "circle"), ("300 KHz", 300e3, BLUE, [BLUE], "circle"),
        ("500 KHz", 500e3, ORANGE_L, [ORANGE_L], "circle"), ("700 kHz", 700e3, GRAY, [GRAY], "circle"),
        ("1000 kHz", 1e6, LBLUE, [LBLUE], "circle")]

# Figures, keyed by the image's placement (x0, y0) on the page in pt (int-truncated).
# pvt: curves listed top->bottom: (label, f, B, colour). pvb: series in legend order top->bottom.
FIGS = {
    "CF124": [dict(kind="pvt", at=(296, 413), x=LIN(20, 140, 20), y=LIN(0, 200, 20), grid="gray",
                   curves=[("25 kHz, 200 mT", 25e3, 0.2, BLACK), ("25 kHz, 100 mT", 25e3, 0.1, BLACK)],
                   masks=[(575, 122, 642, 136), (575, 208, 632, 222)])],
    "CF130": [dict(kind="pvt", at=(22, 410), x=LIN(20, 140, 20), y=LIN(0, 1000, 100), grid="gray",
                   curves=[("100 KHz, 200 mT", 100e3, 0.2, BLACK)])],
    "CF249": [dict(kind="pvt", at=(374, 119), x=LIN(20, 120, 20), y=LIN(0, 1000, 100), grid="blue",
                   curves=[("1 MHz, 50 mT", 1e6, 0.05, ORANGE_L), ("500 kHz, 50 mT", 500e3, 0.05, BLACK)],
                   masks=[(520, 70, 600, 140)]),
              dict(kind="pvb", at=(30, 408), T=25, x=DEC(10, 1000), y=DEC(10, 10000), series=F249),
              dict(kind="pvb", at=(323, 407), T=100, x=DEC(10, 1000), y=DEC(10, 10000), series=F249)],
    "CF292": [dict(kind="pvt", at=(374, 132), x=LIN(20, 140, 20), y=LIN(0, 1200, 200), grid="gray",
                   curves=[("100 KHz, 200 mT", 100e3, 0.2, BLACK)]),
              dict(kind="pvb", at=(22, 419), T=25, x=DEC(10, 1000), y=DEC(1, 10000), series=F3),
              dict(kind="pvb", at=(314, 422), T=100, x=DEC(10, 1000), y=DEC(1, 10000), series=F3)],
    "CF295": [dict(kind="pvt", at=(380, 110), x=LIN(20, 120, 20), y=LIN(0, 500, 50), grid="gray",
                   curves=[("100 kHz, 200 mT", 100e3, 0.2, BLACK)]),
              dict(kind="pvb", at=(22, 395), T=25, x=DEC(10, 1000), y=DEC(10, 10000), series=F1),
              dict(kind="pvb", at=(320, 395), T=100, x=DEC(10, 1000), y=DEC(10, 10000), series=F1)],
    "CF296": [dict(kind="pvt", at=(379, 120), x=LIN(20, 120, 20), y=LIN(0, 450, 50), grid="gray",
                   curves=[("100 kHz, 200 mT", 100e3, 0.2, BLACK)]),
              dict(kind="pvb", at=(34, 407), T=25, x=DEC(10, 1000), y=DEC(10, 10000), series=F1),
              dict(kind="pvb", at=(316, 407), T=100, x=DEC(10, 1000), y=DEC(10, 10000), series=F1)],
    "CF296A": [dict(kind="pvt", at=(370, 119), x=LIN(20, 140, 20), y=LIN(50, 500, 50), grid="blue",
                    curves=[("100 kHz, 200 mT", 100e3, 0.2, BLACK)]),
               dict(kind="pvb", at=(37, 420), T=25, x=DEC(10, 1000), y=DEC(1, 10000), series=F1),
               dict(kind="pvb", at=(319, 421), T=100, x=DEC(10, 1000), y=DEC(1, 10000), series=F1)],
    "CF297": [dict(kind="pvt", at=(368, 119), x=LIN(20, 140, 20), y=LIN(0, 800, 100), grid="gray",
                   curves=[("100 KHz, 200 mT", 100e3, 0.2, BLACK)]),
              dict(kind="pvb", at=(33, 396), T=25, x=DEC(10, 1000), y=DEC(1, 10000), series=F3),
              dict(kind="pvb", at=(329, 400), T=100, x=DEC(10, 1000), y=DEC(1, 10000), series=F3)],
    "CF297A": [dict(kind="pvt", at=(374, 120), x=LIN(20, 140, 20), y=LIN(0, 700, 100), grid="gray",
                    curves=[("100 KHz, 200 mT", 100e3, 0.2, BLACK)]),
               dict(kind="pvb", at=(32, 399), T=25, x=DEC(10, 1000), y=DEC(1, 10000), series=F3),
               dict(kind="pvb", at=(323, 399), T=100, x=DEC(10, 1000), y=DEC(1, 10000), series=F3)],
}
FIGS["CF138"] = FIGS["CF297"]   # same placement; the images are CF297's (checked by hash below)
FIGS["CF139"] = FIGS["CF297"]

# printed Pcv tables: (T C, f Hz, B T) -> (kW/m3, is_limit)
TABLES = {
    "CF124": {(100, 16e3, 0.2): (90, False), (100, 25e3, 0.2): (130, False)},
    "CF130": {(100, 16e3, 0.2): (130, True), (100, 100e3, 0.2): (800, True)},
    "CF138": {(100, 100e3, 0.1): (90, True), (100, 100e3, 0.2): (450, True)},
    "CF139": {(100, 100e3, 0.1): (60, True), (100, 100e3, 0.2): (380, True)},
    "CF249": {(100, 500e3, 0.05): (90, True), (100, 1e6, 0.05): (480, True)},
    "CF292": {(100, 100e3, 0.1): (70, True), (100, 100e3, 0.2): (410, True)},
    "CF295": {(25, 100e3, 0.2): (350, True), (100, 100e3, 0.2): (350, True)},
    "CF296": {(25, 100e3, 0.2): (350, True), (100, 100e3, 0.2): (290, True)},
    "CF296A": {(25, 100e3, 0.2): (300, True), (80, 100e3, 0.2): (300, True), (100, 100e3, 0.2): (300, True)},
    "CF297": {(25, 100e3, 0.2): (700, True), (100, 100e3, 0.2): (350, True)},
    "CF297A": {(25, 100e3, 0.2): (600, True), (100, 100e3, 0.2): (300, True)},
}
DUPLICATE_OF = {"CF138": "CF297", "CF139": "CF297"}
B_NOMINAL = [0.025, 0.05, 0.1, 0.2]


def point(f, B, T, pv_kw):
    sig = lambda v, n=4: float(f"{v:.{n}g}")
    return {"magneticFluxDensity": {"frequency": sig(f, 6), "magneticFluxDensity": {"processed": {
        "label": "sinusoidal", "peak": sig(B), "offset": 0.0}}},
        "temperature": sig(T, 4), "value": sig(pv_kw * 1000.0), "origin": "manufacturer"}


def runs(idx):
    """consecutive integer runs -> list of (start, end) inclusive"""
    out = []
    for i in idx:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [tuple(r) for r in out]


def cdist(a, rgb):
    return np.sqrt(((a - np.array(rgb)) ** 2).sum(2))


class Scale:
    def __init__(self, log, a, b):
        self.log, self.a, self.b = log, a, b

    def pos(self, v):
        return self.a + self.b * (math.log10(v) if self.log else v)

    def value(self, p):
        u = (p - self.a) / self.b
        return 10 ** u if self.log else u


def snap(v, log, step):
    if log:
        k = math.floor(math.log10(v) + 1e-9)
        m = v / 10 ** k
        return round(m) * 10 ** k if round(m) < 10 else 10 ** (k + 1)
    return round(v / step) * step


def calibrate(lines, labels, values, log, name):
    """lines: gridline pixel positions; labels: label blob centres in the same order as values."""
    if len(labels) != len(values):
        raise ValueError(f"{name}: {len(labels)} tick-label blobs for {len(values)} printed labels")
    tr = (lambda v: math.log10(v)) if log else (lambda v: v)
    b, a = np.polyfit([tr(v) for v in values], labels, 1)
    S = Scale(log, a, b)
    step = None if log else values[1] - values[0]
    lo, hi = min(values), max(values)
    for _ in range(4):
        pairs = []
        for p in lines:
            v = S.value(p)
            if v <= 0:
                continue
            s = snap(v, log, step)
            if lo * (1 - 1e-6) - (0 if log else 1e-9) <= s <= hi * (1 + 1e-6) + (0 if log else 1e-9):
                pairs.append((p, s))
        b, a = np.polyfit([tr(s) for _, s in pairs], [p for p, _ in pairs], 1)
        S = Scale(log, a, b)
    gres = max(abs(S.pos(s) - p) for p, s in pairs)
    lres = max(abs(S.pos(v) - p) for p, v in zip(labels, values))
    snapped = sorted({s for _, s in pairs})
    if not log and snapped != sorted(values):
        missing = sorted(set(values) - set(snapped))
        if len(missing) > 1:
            raise ValueError(f"{name}: gridlines missing at {missing}")
    if gres > GRID_TOL:
        raise ValueError(f"{name}: gridline residual {gres:.2f} px")
    if lres > LABEL_TOL:
        raise ValueError(f"{name}: tick-label residual {lres:.2f} px")
    return S, dict(gridlines=len(pairs), grid_res_px=round(gres, 2), label_res_px=round(lres, 2))


def gridlines(a, fig):
    h, w, _ = a.shape
    mn, mx = a.min(2), a.max(2)
    sat = mx - mn
    if fig.get("grid") == "blue":
        g = (cdist(a, (143, 170, 220)) < 40) | (cdist(a, (157, 195, 230)) < 40)
    elif fig["kind"] == "pvt":
        g = (sat < 15) & (mn >= 150) & (mn < 235)
    else:
        g = (sat < 15) & (mn < 235)
    dark = (sat < 15) & (mx < 60)
    inner = lambda n, i: 3 <= i < n - 3
    rows = [i for i in range(h) if inner(h, i) and g[i].sum() > 0.35 * w]
    cols = [j for j in range(w) if inner(w, j) and g[:, j].sum() > 0.35 * h]
    R = [(r0 + r1) / 2 for r0, r1 in runs(rows)]
    C = [(c0 + c1) / 2 for c0, c1 in runs(cols)]
    if fig["kind"] == "pvt":   # dark axis lines spanning the whole grid
        x0, x1 = int(min(C)), int(max(C))
        y0, y1 = int(min(R)), int(max(R))
        drows = [i for i in range(h) if dark[i, x0:x1 + 1].sum() > 0.95 * (x1 - x0)]
        dcols = [j for j in range(w) if dark[y0:y1 + 1, j].sum() > 0.95 * (y1 - y0)]
        R = sorted(R + [(r0 + r1) / 2 for r0, r1 in runs(drows)])
        C = sorted(C + [(c0 + c1) / 2 for c0, c1 in runs(dcols)])
    return R, C


def label_blobs(a, R, C):
    """tick-label text blobs: y labels in a strip left of the plot, x labels in a strip below it."""
    mn, mx = a.min(2), a.max(2)
    text = (mx - mn < 30) & (mx < 140)
    left, bottom = min(C), max(R)
    # y labels are right-aligned next to the axis: keep rows whose rightmost text pixel lies in
    # the label column (the rotated axis title sits further left)
    lo = max(0, int(left) - 45)
    rx = np.full(a.shape[0], -1)
    for i in range(a.shape[0]):
        nz = np.nonzero(text[i, lo:int(left) - 3])[0]
        if len(nz):
            rx[i] = lo + nz[-1]
    edge = rx[(np.arange(a.shape[0]) > min(R) - 12) & (np.arange(a.shape[0]) < bottom + 12)].max()
    yb = [i for i in range(a.shape[0]) if rx[i] >= edge - 8]
    yl = [(r0 + r1) / 2 for r0, r1 in runs(yb) if 5 <= r1 - r0 <= 22 and min(R) - 12 <= (r0 + r1) / 2 <= bottom + 12]
    # x labels: blobs in the first text rows below the plot; every label starts on the same top
    # row, the axis title (which may touch them) starts lower
    rows_ = [i for i in range(int(bottom) + 8, min(a.shape[0], int(bottom) + 45))
             if text[i, int(left) - 12:int(max(C)) + 40].any()]
    xl = []
    if rows_:
        r0 = rows_[0]
        strip = text[r0:r0 + 16, :]
        cb = [j for j in range(a.shape[1]) if strip[:, j].any()]
        groups = []
        for c0, c1 in runs(cb):
            if groups and c0 - groups[-1][1] <= 9:
                groups[-1][1] = c1
            else:
                groups.append([c0, c1])
        for c0, c1 in groups:
            top = np.nonzero(strip[:, c0:c1 + 1].any(1))[0][0]
            if top <= 2 and left - 12 <= (c0 + c1) / 2 <= max(C) + 40:
                xl.append((c0 + c1) / 2)
    return yl, xl


def axes(a, fig, name):
    R, C = gridlines(a, fig)
    yl, xl = label_blobs(a, R, C)
    log = fig["kind"] == "pvb"
    ys = sorted(fig["y"], reverse=True)   # top label first (smallest pixel y)
    X, xr = calibrate(C, xl, fig["x"], log, name + " x")
    Y, yr = calibrate(R, yl, ys, log, name + " y")
    box = (min(C), min(R), max(C), max(R))
    return X, Y, box, dict(x=xr, y=yr)


def pvt(a, fig, name, rep):
    X, Y, (x0, y0, x1, y1), cal = axes(a, fig, name)
    rep["calibration"] = cal
    h, w, _ = a.shape
    mn, mx = a.min(2), a.max(2)
    masks = np.zeros((h, w), bool)
    for (mx0, my0, mx1, my1) in fig.get("masks", []):
        masks[my0:my1 + 1, mx0:mx1 + 1] = True
    inside = np.zeros((h, w), bool)
    # a curve may run to the right frame; read up to it unless that frame is a dark axis line
    dark_right = ((mx[int(y0):int(y1), int(x1)] < 60).mean() > 0.5)
    inside[int(y0) + 3:int(y1) - 2, int(x0) + 3:int(x1) - 2 if dark_right else int(x1) + 2] = True
    colours = {}
    for lab, f, B, col in fig["curves"]:
        colours.setdefault(col, []).append((lab, f, B))
    out = []
    for col, curves in colours.items():
        m = ((mx < 60) & (mx - mn < 25)) if col == BLACK else (cdist(a, col) < 70)
        m &= inside & ~masks
        n = len(curves)
        per = [dict() for _ in range(n)]     # column -> (centre y, run height)
        last = None                          # per curve: (column, centre) last seen
        for j in range(int(x0) + 3, int(x1) + 2):
            rr = runs(list(np.nonzero(m[:, j])[0]))
            if last is None:                 # start where all n curves are present, top->bottom
                if len(rr) == n and not any(masks[max(0, r0 - 1):r1 + 2, j].any() for r0, r1 in rr):
                    last = [(j, (r0 + r1) / 2) for r0, r1 in rr]
                    for k, (r0, r1) in enumerate(rr):
                        per[k][j] = ((r0 + r1) / 2, r1 - r0 + 1)
                continue
            used = set()
            for k in range(n):
                lj, ly = last[k]
                # tolerance grows with the columns since last seen (curve hidden behind a legend key)
                cand = [(abs((r0 + r1) / 2 - ly), i) for i, (r0, r1) in enumerate(rr) if i not in used]
                cand = [c for c in cand if c[0] <= 6 + 0.3 * (j - lj - 1)]
                if not cand:
                    continue
                i = min(cand)[1]
                used.add(i)
                r0, r1 = rr[i]
                if masks[max(0, r0 - 1):r1 + 2, j].any():
                    continue                 # run touches a legend mask: not used
                per[k][j] = ((r0 + r1) / 2, r1 - r0 + 1)
                last[k] = (j, (r0 + r1) / 2)
        for k, (lab, f, B) in enumerate(curves):
            cols = sorted(per[k])
            thick = np.median([per[k][j][1] for j in cols])
            good = {j: per[k][j][0] for j in cols if thick - 1 <= per[k][j][1] <= thick + 2}
            gj = sorted(good)
            t0, t1 = X.value(gj[0]), X.value(gj[-1])
            first = 5 * math.ceil((t0 - 0.5) / 5)
            if first < t0 - 0.2:     # the drawn line starts after it (CF296A: drawn from ~20.5 C)
                first += 5
            temps = [first] + [t for t in range(10 * math.ceil(first / 10 + 1e-9), int(t1 + 0.5) + 1, 10) if t > first]
            if temps[-1] > t1 + 0.5:
                temps.pop()
            samples, dropped = [], []
            for T in temps:
                xp = X.pos(T)
                lft = [j for j in gj if j <= xp]
                rgt = [j for j in gj if j >= xp]
                if not lft or not rgt:
                    if lft and xp - lft[-1] <= 1.0:
                        samples.append((T, Y.value(good[lft[-1]]))); continue
                    if rgt and rgt[0] - xp <= 1.0:
                        samples.append((T, Y.value(good[rgt[0]]))); continue
                    dropped.append((T, "beyond drawn line")); continue
                jl, jr = lft[-1], rgt[0]
                if jr - jl > (DASH_GAP if "100 mT" in lab and fig["at"] == (296, 413) else 2):
                    dropped.append((T, f"no drawn line within {jl}..{jr} px (legend mask / gap)")); continue
                yv = good[jl] if jr == jl else good[jl] + (good[jr] - good[jl]) * (xp - jl) / (jr - jl)
                samples.append((T, Y.value(yv)))
            out.append(dict(label=lab, f=f, B=B, T0=round(t0, 1), T1=round(t1, 1), samples=samples,
                            dropped=dropped, cols=good, colour=col))
    # physics / legend order: listed top->bottom, so values must decrease down the list at every T
    order = [(c["label"]) for c in sorted(out, key=lambda c: np.mean(list(c["cols"].values())))]
    if order != [c[0] for c in fig["curves"]]:
        raise ValueError(f"{name}: curve order top->bottom {order}")
    rep["curves"] = {c["label"]: dict(T_range=[c["T0"], c["T1"]], samples=[(t, round(v, 1)) for t, v in c["samples"]],
                                      dropped=c["dropped"]) for c in out}

    def read(f, B, T):
        for c in out:
            if c["f"] == f and abs(c["B"] - B) < 1e-9 and c["T0"] - 0.6 <= T <= c["T1"] + 0.6:
                xp = X.pos(T)
                gj = sorted(c["cols"])
                jl = max([j for j in gj if j <= xp], default=None)
                jr = min([j for j in gj if j >= xp], default=None)
                if jl is None or jr is None:
                    jl = jr = jl if jl is not None else jr
                yv = c["cols"][jl] if jr == jl else c["cols"][jl] + (c["cols"][jr] - c["cols"][jl]) * (xp - jl) / (jr - jl)
                return Y.value(yv)
        return None
    pts = [(c["f"], c["B"], t, v) for c in out for t, v in c["samples"]]
    return pts, read, dict(X=X, Y=Y, curves=out)


def pvb(a, fig, name, rep):
    X, Y, (x0, y0, x1, y1), cal = axes(a, fig, name)
    rep["calibration"] = cal
    h, w, _ = a.shape
    thr = 28 if any(s[2] in (BLUE, LBLUE) for s in fig["series"]) and \
        {BLUE, LBLUE} <= {s[2] for s in fig["series"]} else 45
    inside = np.zeros((h, w), bool)
    # markers sitting on the top/bottom frame line are drawn whole (e.g. CF295 100 C, 100 kHz at 50 mT)
    inside[max(0, int(y0) - 9):int(y1) + 10, int(x0) + 3:int(x1) - 2] = True
    legend = np.zeros((h, w), bool)
    legend[:, int(x1) + 4:] = True
    # legend order check
    lys = []
    for lab, f, lc, fills, shape in fig["series"]:
        lm = (cdist(a, lc) < thr) & legend
        ys = np.nonzero(lm.sum(1) >= 8)[0]
        if not len(ys):
            raise ValueError(f"{name}: legend key {lab} not found")
        lys.append((float(np.median(ys)), lab))
    if [l for _, l in sorted(lys)] != [s[0] for s in fig["series"]]:
        raise ValueError(f"{name}: legend order {sorted(lys)}")
    series = {}
    for lab, f, lc, fills, shape in fig["series"]:
        cm = np.zeros((h, w), bool)
        for c in [lc] + fills:
            cm |= cdist(a, c) < thr
        cm &= inside
        op = ndimage.binary_opening(cm, structure=np.ones((5, 5), bool))
        L, n = ndimage.label(op)
        blobs = []
        for sl in ndimage.find_objects(L):
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            if hh >= 5 and ww >= 5 and hh <= 18 and ww <= 18:
                blobs.append(((sl[1].start + sl[1].stop - 1) / 2, (sl[0].start + sl[0].stop - 1) / 2,
                              sl[1].start, sl[1].stop - 1, sl[0].start, sl[0].stop - 1))
        blobs.sort()
        pts = []
        for xc, yc, _, _, top, bot in blobs:
            # vertical extent of the marker in its centre column, unopened (the opening clips a
            # triangle's apex); the marker box is centred on the data point
            col = np.nonzero(cm[:, int(round(xc))])[0]
            run = [r for r in runs(list(col)) if r[0] <= yc <= r[1]]
            if not run:
                raise ValueError(f"{name}: {lab} marker at x={xc} has no centre column")
            r0, r1 = run[0]
            if not (8 <= r1 - r0 + 1 <= 16):
                raise ValueError(f"{name}: {lab} marker at x={xc} spans {r0}..{r1} in its centre column")
            ym = (r0 + r1) / 2
            if shape != "triangle" and abs(ym - yc) > MARKER_TOL:
                raise ValueError(f"{name}: {lab} marker column centre {ym} vs blob centre {yc}")
            Bv = X.value(xc) / 1e3
            Bn = min(B_NOMINAL, key=lambda b: abs(math.log(b / Bv)))
            if abs(Bv / Bn - 1) > B_SNAP:
                raise ValueError(f"{name}: {lab} marker at B={Bv*1e3:.1f} mT is not a round value")
            pts.append(dict(B=Bn, B_read=round(Bv * 1e3, 1), pv=Y.value(ym), y_px=round(ym, 2),
                            col_span_px=[int(r0), int(r1)]))
        series[lab] = (f, pts)
    # physics order at common B
    for Bn in B_NOMINAL:
        vals = sorted((f, p["pv"]) for f, ps in series.values() for p in ps if p["B"] == Bn)
        if any(v2 <= v1 for (_, v1), (_, v2) in zip(vals, vals[1:])):
            raise ValueError(f"{name}: loss not rising with f at {Bn*1e3:g} mT: {vals}")
    rep["series"] = {lab: [dict(B_mT=p["B"] * 1e3, B_read_mT=p["B_read"], pv_kWm3=round(p["pv"], 1),
                                marker_rows=p["col_span_px"]) for p in ps] for lab, (f, ps) in series.items()}

    def read(f, B, T):
        if T != fig["T"]:
            return None
        for ff, ps in series.values():
            if ff == f:
                for p in ps:
                    if p["B"] == B:
                        return p["pv"]
        return None
    out = [(f, p["B"], fig["T"], p["pv"]) for f, ps in series.values() for p in ps]
    return out, read, dict(X=X, Y=Y, series=series)


def overlay(a, fig, geo, path):
    from PIL import Image, ImageDraw
    im = Image.fromarray(a.astype(np.uint8)).convert("RGB")
    d = ImageDraw.Draw(im)
    X, Y = geo["X"], geo["Y"]
    if fig["kind"] == "pvt":
        for c in geo["curves"]:
            for T, v in c["samples"]:
                x, y = X.pos(T), Y.pos(v)
                d.ellipse((x - 3, y - 3, x + 3, y + 3), outline=(255, 0, 255), width=1)
    else:
        for f, ps in geo["series"].values():
            for p in ps:
                x, y = X.pos(p["B"] * 1e3), Y.pos(p["pv"])
                d.line((x - 6, y, x + 6, y), fill=(255, 0, 0)); d.line((x, y - 6, x, y + 6), fill=(255, 0, 0))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srcdir")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    ap.add_argument("--overlay-dir")
    a_ = ap.parse_args()
    report, records, hashes = {}, [], {}
    order = ["CF124", "CF130", "CF138", "CF139", "CF297", "CF297A", "CF292", "CF295", "CF296", "CF296A", "CF249"]
    for mat in order:
        path = os.path.join(a_.srcdir, mat + ".pdf")
        raw = open(path, "rb").read()
        size, sha = SOURCES[mat]
        rep = report.setdefault(mat, dict(url=URL.format(mat), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        if len(raw) != size or rep["sha256"] != sha:
            raise SystemExit(f"{mat}: {len(raw)} bytes sha256 {rep['sha256']}, expected {size} {sha}")
        doc = fitz.open(path)
        pg = doc[0]
        if mat not in pg.get_text().split():
            raise SystemExit(f"{mat}: grade name not on the page")
        imgs = {}
        for im in pg.get_images():
            r = pg.get_image_rects(im[0])[0]
            ib = doc.extract_image(im[0])["image"]
            pix = fitz.Pixmap(doc, im[0])
            if pix.n - pix.alpha != 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].astype(int)
            imgs[(int(r.x0), int(r.y0))] = (arr, hashlib.sha256(ib).hexdigest())
        pts_all, figrep, accepted, pending = [], [], [], []
        dup = DUPLICATE_OF.get(mat)
        for k, fig in enumerate(FIGS[mat]):
            key = min(imgs, key=lambda q: abs(q[0] - fig["at"][0]) + abs(q[1] - fig["at"][1]))
            if abs(key[0] - fig["at"][0]) + abs(key[1] - fig["at"][1]) > 4:
                raise SystemExit(f"{mat}: no image at {fig['at']}")
            arr, h = imgs[key]
            hashes.setdefault(mat, []).append(h)
            name = f"{mat} {fig['kind']}" + (f" {fig['T']}C" if fig["kind"] == "pvb" else "")
            fr = dict(figure=name, image_at_pt=list(key), image_px=[arr.shape[1], arr.shape[0]], image_sha256=h)
            figrep.append(fr)
            try:
                pts, read, geo = (pvt if fig["kind"] == "pvt" else pvb)(arr, fig, name, fr)
            except ValueError as e:
                fr["REJECTED"] = str(e)
                print(f"{name}: REJECTED {e}")
                continue
            if a_.overlay_dir:
                os.makedirs(a_.overlay_dir, exist_ok=True)
                overlay(arr, fig, geo, os.path.join(a_.overlay_dir, name.replace(" ", "_") + ".png"))
            cid = (lambda f, B: (f, B)) if fig["kind"] == "pvt" else (lambda f, B: f)
            # table check, per curve
            chk = []
            for (T, f, B), (val, lim) in TABLES[mat].items():
                v = read(f, B, T)
                if v is not None:
                    chk.append(dict(T=T, f=f, B=B, table=val, limit=lim, read=round(v, 1), ratio=round(v / val, 3)))
            fr["table_check"] = chk
            if dup:
                fr["REJECTED"] = f"image is byte-identical to {dup}'s figure (not {mat} data)"
                if chk:
                    fr["REJECTED"] += "; table ratios " + ", ".join(
                        f"{c['T']} C {c['f']/1e3:g} kHz {c['B']*1e3:g} mT {c['ratio']}" for c in chk)
                print(f"{name}: REJECTED {fr['REJECTED']}")
                continue
            bad = {cid(c["f"], c["B"]) for c in chk if abs(c["ratio"] - 1) > TABLE_TOL}
            good = {cid(c["f"], c["B"]) for c in chk} - bad
            if bad:
                fr["REJECTED_CURVES"] = "; ".join(
                    f"{c['T']} C {c['f']/1e3:g} kHz {c['B']*1e3:g} mT reads {c['read']} vs table {c['table']} "
                    f"(ratio {c['ratio']})" for c in chk if cid(c["f"], c["B"]) in bad)
                print(f"{name}: curve(s) REJECTED {fr['REJECTED_CURVES']}")
            kept = [q for q in pts if cid(q[0], q[1]) not in bad]
            fr["dropped_points_of_rejected_curves"] = len(pts) - len(kept)
            if not chk:
                pending.append((fig, name, fr, kept, read))
                continue
            if not good:
                fr["REJECTED"] = "no curve of the figure reproduces the printed table"
                print(f"{name}: REJECTED {fr['REJECTED']}")
                continue
            fr["accepted_points"] = len(kept)
            accepted.append((fig, read, {cid(q[0], q[1]) for q in kept}))
            pts_all += [(f, B, T, v, name) for f, B, T, v in kept]
            print(f"{name}: {len(kept)} points, table ratios {[c['ratio'] for c in chk]}, cal {fr['calibration']}")
        # figures that cover no printed table condition (25 C Pv-B): accepted only if they agree with an
        # accepted, table-checked curve of the same sheet at every condition both cover
        for fig, name, fr, kept, read in pending:
            xc = []
            for f, B, T, v in kept:
                for afig, aread, acurves in accepted:
                    if afig["kind"] == "pvt" and (f, B) in acurves:
                        w = aread(f, B, T)
                        if w is not None:
                            xc.append(dict(T=T, f=f, B=B, this=round(v, 1), other=afig["kind"] + " curve",
                                           other_read=round(w, 1), ratio=round(v / w, 3)))
            fr["cross_check"] = xc
            if not xc:
                fr["REJECTED"] = "covers no printed table condition and no accepted curve of the sheet"
            elif any(abs(c["ratio"] - 1) > TABLE_TOL for c in xc):
                fr["REJECTED"] = "disagrees with the sheet's accepted Pv-T curve: " + str(xc)
            if fr.get("REJECTED"):
                print(f"{name}: REJECTED {fr['REJECTED']}")
                continue
            fr["accepted_points"] = len(kept)
            pts_all += [(f, B, T, v, name) for f, B, T, v in kept]
            print(f"{name}: {len(kept)} points, cross-check vs Pv-T {[c['ratio'] for c in xc]}, cal {fr['calibration']}")
        rep["figures"] = figrep
        if mat == "CF124":   # plain (typical) table value at a frequency no curve covers
            pts_all.append((16e3, 0.2, 100, 90.0, "CF124 table"))
        # a condition read from two figures (Pv-T sample and Pv-B marker at 25/100 C): keep the
        # Pv-B marker (a plotted data point; the Pv-T line is a smoothed curve) and report both
        dups, keep = [], []
        for q in pts_all:
            same = [o for o in pts_all if o is not q and o[:3] == q[:3]]
            if same and " pvt" in q[4] and any(" pvb" in o[4] for o in same):
                o = [o for o in same if " pvb" in o[4]][0]
                dups.append(dict(T=q[2], f=q[0], B=q[1], pvt=round(q[3], 1), pvb=round(o[3], 1),
                                 pvb_over_pvt=round(o[3] / q[3], 3)))
                continue
            keep.append(q)
        pts_all = keep
        rep["same_condition_pvt_vs_pvb"] = dups
        rep["points"] = len(pts_all)
        if pts_all:
            records.append({"name": mat, "manufacturerInfo": {"name": "Cosmo Ferrites"},
                            "volumetricLosses": {"default": [[point(f, B, T, v) for f, B, T, v, _ in pts_all]]}})
    for m, d in DUPLICATE_OF.items():
        same = [x == y for x, y in zip(hashes[m], hashes[d])]
        report[m]["figures_identical_to_" + d] = same
    # accepted figures of DIFFERENT grades that read the same everywhere (within 0.5 %): the same
    # chart pasted on two sheets. Reported, not rejected (each passes its own sheet's table).
    figs = {}
    for m, v in report.items():
        for fr in v.get("figures", []):
            if fr.get("REJECTED") or "series" not in fr and "curves" not in fr:
                continue
            vals = sorted(p["pv_kWm3"] for s_ in fr["series"].values() for p in s_) if "series" in fr else \
                sorted(x[1] for c in fr["curves"].values() for x in c["samples"])
            figs[fr["figure"]] = vals
    same = [(a, b) for i, a in enumerate(figs) for b in list(figs)[i + 1:] if a.split()[0] != b.split()[0]
            and len(figs[a]) == len(figs[b]) and all(abs(x / y - 1) < 0.005 for x, y in zip(figs[a], figs[b]))]
    report["_same_chart_on_two_sheets"] = same
    for a, b in same:
        print(f"NOTE: {a} and {b} read identically (same chart on two sheets)")
    json.dump(records, open(a_.json, "w"), indent=1)
    if a_.report:
        json.dump(report, open(a_.report, "w"), indent=1)


if __name__ == "__main__":
    sys.exit(main())
