#!/usr/bin/env python3
"""Extract Pv-B and Pv-T core-loss curves for 11 TDG MnZn power ferrites from TDG's raster data sheets
(ABT #2266 / #1518).

    python3 -I scripts/extract-tdg-ferrite-loss.py <dir with TP4B.pdf ... TD3.pdf> --json tdg_points.json \
            [--report tdg_report.json] [--debug <dir for overlay PNGs>]

Sources
-------
TDG "Material Characteristic Sheets and figures of MnZn", one PDF per grade:
    https://www.tdgcore.com/uploads/file/20220705/<id>.pdf
Read 2026-11-05 (file id, bytes, sha256; the script refuses a file whose size or hash differs):
    TP4B   1657011139502275  722,468 B  f50ad143eb79d3e97a48a39d68ae9134993fa3d3d4d6e157d377ce7c419a745c
    TP4C   1657011155418741  740,944 B  363e6f69caffc36cde23143ad7d2f863edcd5280d05dc8d9b6f5785e9160fc5c
    TP4D   1657011167345165  637,604 B  88b561781f814b3c5421a932d344c17314ec756c01d46150c38e74b771fc15d0
    TP4E   1657011180312893  650,446 B  482e30cc48680402a35213344e6e4efefb634649f41d1eb8ccb98c7fda1f0c19
    TP4F   1657011194855454  641,866 B  9541ad5743acd7fcc13ecba3d8343e649f29da400da16dce56471b820db91d9c
    TP4S   1657011210720223  716,484 B  446bce57242495e75924067f3984588f7ca0c273cdecc26cf905c478844efcaf
    TPW30  1657011393609491  809,820 B  720b8f7fad05c489f8c7534164f27ba15ec566a3fc54912f1f0a80d86970ee7a
    TPG30  1657011352390197  636,448 B  908268e4d36a7bfbacda9b36e911d7c4c372bcfc2304a1c31271a64eb49e35a6
    TPB12  1657011286225353  814,968 B  5c09cdfa7f2da22191a9db30db8fb21159b19530335468b4873acb2906207227
    TP5i   1657011270221741  717,101 B  360d611930f84cadfe4e8b026ee86f259c393b54be56f0cf7757d9c47d6ac2b1
    TD3    1657010807867110  495,279 B  e7c19460bf3d1334bf0cf510665c507e8e29b45b3cf95b33857f9e93b67773b3
Each sheet is two pages (TD3: one); every page is ONE full-page JPEG drawn through a soft mask (the
RGB plane is flat black, the ink is in the /SMask). There is no text layer and no vector path, so
the figures must be digitised from pixels. Native resolution: ~220 dpi (1359 px wide) on most
second pages, ~300 dpi (1853 px) on TP4C, TP5i, TPB12, TPW30.

What each sheet publishes (read by eye from the page images, hard-coded in GRADES below):
  page 1: material table incl. "Core loss Pcv(kW/m3)" at 100 kHz 200 mT and 2-4 temperatures
          (TP5i: 300 kHz 100 mT and 500 kHz 50 mT at 30/80/100 C); test core Toroid OD25 ID15 H7.5
          (TD3: OD31 ID19 H6).
  page 2: "Pcv-Temperature" (linear axes, 100 kHz 200 mT; TP5i two curves) and two "Pcv-Bm"
          figures (log-log, 1E+1..1E+3 mT, one temperature each, 5-6 frequencies). No Pv-f figure
          exists on any sheet. TD3 has no core-loss figure at all (only its table).

Method -- pixels, calibrated on the gridlines
---------------------------------------------
1. Ink = 1 - soft-mask alpha composited on white (exact page ink, no colour conversion).
2. Frame + gridlines: rows/columns inked (>0.16) over more than GRID_COVER of the figure are
   gridlines (clustered, ink-weighted centre). The axis is fitted to the EXPECTED grid (linear:
   every label step; log: 1..9 x 10^k) by least squares, starting from the outermost lines as the
   axis ends (or the second line in, where a frame edge is drawn off the scale: TP4E's Pv-B
   frames, reported as off_scale_frame_px); every gridline inside the scale must be explained
   (within SNAP px), at most MISS_MAX expected gridlines may be hidden, and the straight-line
   residual must stay below FIT_TOL px (worst found: 1.2 px, TP4E; typically 0.2-0.5 px).
3. Tick labels: the printed tick labels (values read by eye, hard-coded in GRADES) must sit on
   their gridlines: the ink clusters under the x axis / left of the y axis must be exactly as
   many as the labels, and each must lie within LABEL_TOL of a label spacing of its gridline
   (worst found: 8.9 px on a 236 px decade).
4. Curves: ink > 0.45 inside the frame; a gridline pixel is blanked unless the ink continues on
   the pixel just beyond the gridline (a curve stroke crossing or running along it); the 1-px gaps
   are closed along the gridline normal only; connected components spanning > CURVE_MIN px are
   curves (labels and notes never span that far). Where two thin curves touch (TP4E 100 C,
   32/25 kHz) one component holds both and split_tracks() separates them column by column.
   The centre line is the ink-weighted mean row in each column (exact for a constant-width
   stroke); gaps of at most GAP_MAX px are linearly bridged, larger gaps fail the figure. TP5i's
   dashed 500 kHz/50 mT Pv-T curve is assembled from its dashes (legend box excluded, gaps
   <= 14 px bridged). --debug writes every figure with the read centre line drawn over it in red.
5. Labels: the vertical order of the Pv-B curves comes from every pair's overlap (a pair that
   crosses fails the figure). That order is assigned the legend read from the sheet top->bottom,
   which must itself be the physics order (higher f above). The figure temperature is the
   "xx C" box printed in the frame.
6. Checks that can fail (#1006), TABLE_TOL = 10 %:
   a) Pv-T: every printed table temperature inside the curve's drawn span.
   b) Pv-B: the 100 kHz curve at 200 mT (TP5i: 300 kHz@100 mT and 500 kHz@50 mT) against the
      printed table at the figure's temperature when the table prints it; otherwise against the
      ACCEPTED Pv-T curve at that temperature ("via Pv-T"); with neither, the figure is not
      checkable and is dropped.
   A failing curve is rejected with its whole figure (all curves share the calibration); nothing
   is rescaled. A grade left with < 4 points is not emitted (MAS minItems 4 on a points list).
7. Points: Pv-B at the standard Bm grid B_GRID inside each curve's drawn span (an endpoint
   within END_TOL px of a grid value counts: it is the drawn end, read at the end column);
   Pv-T at every 10 C and at the table temperatures inside the drawn span. Never extrapolated.
   Values rounded to 4 significant figures.

Result 2026-11-05 (table ratios = curve / printed value):
   TP4B  65 pts  Pv-B 25 C (0.917). Pv-T REJECTED (100 C: 377 vs 460, 0.819); Pv-B 80 C dropped
                 (80 C not in the table, Pv-T rejected: uncheckable).
   TP4C 139 pts  Pv-T 0.921/0.938/1.058, Pv-B 25 C 0.925, 45 C 0.986.
   TP4D 138 pts  Pv-T 1.003/1.012/1.076, Pv-B 100 C 1.037, 120 C 0.977 (via Pv-T).
   TP4E   -      Pv-T REJECTED (100 C 0.756), Pv-B 100 C REJECTED (0.833), 80 C uncheckable;
                 table has 2 points only: not emitted.
   TP4F  15 pts  Pv-T 0.948/0.925/0.947. Pv-B 100 C REJECTED (0.756), 140 C REJECTED (0.868).
   TP4S  11 pts  Pv-T 1.001/1.005/1.018. Pv-B 80 C REJECTED (0.852 via Pv-T), 100 C REJECTED
                 (1.188) -- the two figures read as if their temperature boxes were swapped.
   TP5i 140 pts  Pv-T 500k/50m 1.021/0.942/0.970; Pv-T 300k/100m REJECTED (30 C 0.833);
                 Pv-B 30 C 0.948/1.010, 100 C 1.012/1.013.
   TPB12 11 pts  Pv-T 0.971/0.948. Pv-B 25 C REJECTED (0.867), 100 C REJECTED (0.841).
   TPG30 80 pts  Pv-T 0.992/0.999/0.949/0.992, Pv-B 25 C 0.961; Pv-B 100 C REJECTED (0.729).
   TPW30 143 pts Pv-T 0.970/0.993/0.987, Pv-B 100 C 0.982 (via Pv-T), 120 C 0.967.
   TD3    -      no core-loss figure; table 25 C 380 / 100 C 660 kW/m3 = 2 points: not emitted.

Output: JSON array of MAS advanced-material records {"name", "manufacturerInfo": {"name": "TDG"},
"volumetricLosses": {"default": [[point, ...]]}}, SI units, waveform "sinusoidal" (the sheets do not
say; Pcv tables of power ferrites are sine B-H analyser data), origin "manufacturer".
"""
import argparse
import functools
import hashlib
import io
import json
import math
import os
import site
import sys

sys.path.append(site.getusersitepackages())   # python3 -I drops the user site; PyMuPDF lives there
import fitz  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage as nd  # noqa: E402

BASE = "https://www.tdgcore.com/uploads/file/20220705/"
SOURCES = {   # name: (file id, bytes, sha256), read 2026-11-05
    "TP4B": ("1657011139502275", 722468, "f50ad143eb79d3e97a48a39d68ae9134993fa3d3d4d6e157d377ce7c419a745c"),
    "TP4C": ("1657011155418741", 740944, "363e6f69caffc36cde23143ad7d2f863edcd5280d05dc8d9b6f5785e9160fc5c"),
    "TP4D": ("1657011167345165", 637604, "88b561781f814b3c5421a932d344c17314ec756c01d46150c38e74b771fc15d0"),
    "TP4E": ("1657011180312893", 650446, "482e30cc48680402a35213344e6e4efefb634649f41d1eb8ccb98c7fda1f0c19"),
    "TP4F": ("1657011194855454", 641866, "9541ad5743acd7fcc13ecba3d8343e649f29da400da16dce56471b820db91d9c"),
    "TP4S": ("1657011210720223", 716484, "446bce57242495e75924067f3984588f7ca0c273cdecc26cf905c478844efcaf"),
    "TPW30": ("1657011393609491", 809820, "720b8f7fad05c489f8c7534164f27ba15ec566a3fc54912f1f0a80d86970ee7a"),
    "TPG30": ("1657011352390197", 636448, "908268e4d36a7bfbacda9b36e911d7c4c372bcfc2304a1c31271a64eb49e35a6"),
    "TPB12": ("1657011286225353", 814968, "5c09cdfa7f2da22191a9db30db8fb21159b19530335468b4873acb2906207227"),
    "TP5i": ("1657011270221741", 717101, "360d611930f84cadfe4e8b026ee86f259c393b54be56f0cf7757d9c47d6ac2b1"),
    "TD3": ("1657010807867110", 495279, "e7c19460bf3d1334bf0cf510665c507e8e29b45b3cf95b33857f9e93b67773b3"),
}

TABLE_TOL = 0.10
GRID_COVER = 0.50   # fraction of the frame span a gridline row/column must be inked over
SNAP = 3.0          # px (at 220 dpi), detected gridline -> expected gridline
FIT_TOL = 1.5       # px (at 220 dpi), max straight-scale residual
MISS_MAX = 0.25     # fraction of expected gridlines allowed hidden
LABEL_TOL = 0.15    # tick-label centre vs its gridline, fraction of the label spacing
CURVE_MIN = 100     # px (at 220 dpi)
END_TOL = 1.5       # px (at 220 dpi)
GAP_MAX = 6         # px (at 220 dpi), largest gap bridged inside one curve
B_GRID = [10, 12, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 200, 250, 300, 350, 400]  # mT

F6 = [500e3, 200e3, 100e3, 64e3, 32e3, 25e3]
F6B = [500e3, 300e3, 200e3, 100e3, 50e3, 25e3]
LIN = "lin"
LOG = "log"


def pvt(xr, yr, curves=((100e3, 0.2),)):
    return {"x": (LIN,) + xr, "y": (LIN,) + yr, "curves": list(curves)}


def pvb(T, freqs, x=(1, 3), y=(0, 4)):
    return {"T": T, "x": (LOG,) + x, "y": (LOG,) + y, "freqs": freqs}


# tables: {(f, B): {T: kW/m3}}; pvt axes (min, max, step); pvb (temperature, legend order top->bottom,
# log decades of x (mT) and y (kW/m3))
GRADES = {
    "TP4B": dict(table={(100e3, 0.2): {25: 570, 75: 250, 100: 460}},
                 pvt=pvt((0, 140, 20), (0, 600, 100)), pvb=[pvb(25, F6), pvb(80, F6)]),
    "TP4C": dict(table={(100e3, 0.2): {25: 350, 45: 250, 100: 660}},
                 pvt=pvt((0, 140, 20), (0, 900, 100)), pvb=[pvb(25, F6), pvb(45, F6)]),
    "TP4D": dict(table={(100e3, 0.2): {25: 600, 60: 400, 100: 250}},
                 pvt=pvt((0, 140, 20), (0, 700, 100)), pvb=[pvb(100, F6), pvb(120, F6)]),
    "TP4E": dict(table={(100e3, 0.2): {25: 1000, 100: 480}},
                 pvt=pvt((0, 160, 20), (0, 1000, 200)), pvb=[pvb(80, F6), pvb(100, F6)]),
    "TP4F": dict(table={(100e3, 0.2): {25: 900, 100: 500, 140: 400}},
                 pvt=pvt((0, 180, 30), (0, 1000, 200)), pvb=[pvb(100, F6), pvb(140, F6)]),
    "TP4S": dict(table={(100e3, 0.2): {25: 650, 100: 300, 120: 350}},
                 pvt=pvt((0, 140, 20), (0, 700, 100)), pvb=[pvb(80, F6), pvb(100, F6)]),
    "TP5i": dict(table={(300e3, 0.1): {30: 300, 80: 330, 100: 400}, (500e3, 0.05): {30: 80, 80: 100, 100: 120}},
                 pvt=pvt((0, 140, 20), (0, 600, 100), curves=((300e3, 0.1), (500e3, 0.05))),
                 pvb=[pvb(30, [1e6, 700e3, 500e3, 300e3, 200e3], x=(0, 3)),
                      pvb(100, [1e6, 700e3, 500e3, 300e3, 200e3], x=(0, 3))]),
    "TPB12": dict(table={(100e3, 0.2): {25: 1100, 100: 500}},
                  pvt=pvt((0, 140, 20), (0, 1200, 200)), pvb=[pvb(25, F6B, y=(0, 5)), pvb(100, F6B, y=(0, 5))]),
    "TPG30": dict(table={(100e3, 0.2): {0: 380, 25: 330, 100: 350, 120: 380}},
                  pvt=pvt((-20, 140, 20), (0, 500, 100)), pvb=[pvb(25, F6B, y=(0, 5)), pvb(100, F6B, y=(0, 5))]),
    "TPW30": dict(table={(100e3, 0.2): {60: 320, 120: 320, 140: 380}},
                  pvt=pvt((0, 140, 20), (0, 500, 100)), pvb=[pvb(100, F6B, y=(0, 5)), pvb(120, F6B, y=(0, 5))]),
    "TD3": dict(table={(100e3, 0.2): {25: 380, 100: 660}}, pvt=None, pvb=[]),
}


# ---------------------------------------------------------------------------------------------- images
def page_ink(doc, pno):
    """Ink (0 white .. 1 black) of the page's full-page image: 1 - soft mask alpha x (1 - rgb)."""
    pg = doc[pno]
    ims = [im for im in pg.get_images(full=True) if im[2] > 500]
    if len(ims) != 1:
        raise SystemExit(f"page {pno}: {len(ims)} large images")
    xref, smask = ims[0][0], ims[0][1]
    rgb = np.asarray(Image.open(io.BytesIO(doc.extract_image(xref)["image"])).convert("L"), float) / 255
    if not smask:
        raise SystemExit(f"page {pno}: no soft mask")
    a = np.asarray(Image.open(io.BytesIO(doc.extract_image(smask)["image"])).convert("L"), float) / 255
    if a.shape != rgb.shape:
        raise SystemExit(f"page {pno}: mask {a.shape} != image {rgb.shape}")
    return a * (1 - rgb)


def clusters(idx, weights):
    out, cur = [], []
    for i in idx:
        if cur and i - cur[-1] > 1:
            out.append(cur); cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return [(float(np.average(c, weights=[weights[i] for i in c])), c) for c in out]


class Axis:
    """pos = a + b * u, u = value (linear) or log10(value)."""

    def __init__(self, kind, lo, hi, step, lines, s, rep, name, flip=False):
        self.kind = kind
        if kind == LIN:
            vals = [lo + i * step for i in range(int(round((hi - lo) / step)) + 1)]
            us = vals
            self.labels = vals
        else:
            vals = [m * 10 ** d for d in range(lo, hi) for m in range(1, 10)] + [10 ** hi]
            us = [math.log10(v) for v in vals]
            self.labels = [10 ** d for d in range(lo, hi + 1)]
        p = np.array(lines)
        n = len(us)
        best = None
        # the outermost gridlines are normally the axis ends; a frame drawn off the scale (TP4E) is
        # an extra outermost line, so the ends may also be the second line in from either side
        for i0, i1 in ((0, len(p) - 1), (1, len(p) - 1), (0, len(p) - 2), (1, len(p) - 2)):
            if flip:   # image rows grow downwards: the top gridline is the axis maximum
                b = (p[i0] - p[i1]) / (us[-1] - us[0]); a = p[i1] - b * us[0]
            else:
                b = (p[i1] - p[i0]) / (us[-1] - us[0]); a = p[i0] - b * us[0]
            ok = True
            for _ in range(3):
                pred = a + b * np.array(us)
                match, extra = {}, []
                for k, q in enumerate(p):
                    j = int(np.argmin(abs(pred - q)))
                    if abs(pred[j] - q) > SNAP * s or j in match:
                        extra.append(float(q)); continue
                    match[j] = q
                if len(match) < 3:
                    ok = False; break
                J = sorted(match)
                b, a = np.polyfit([us[j] for j in J], [match[j] for j in J], 1)
            if not ok:
                continue
            # an unexplained line is tolerated only outside the scale (a frame edge)
            lo_p, hi_p = sorted((a + b * us[0], a + b * us[-1]))
            inner = [q for q in extra if lo_p - 1 < q < hi_p + 1]
            res = max(abs(a + b * us[j] - match[j]) for j in J)
            score = (len(inner), len(extra), n - len(match), res)
            if best is None or score < best[0]:
                best = (score, a, b, match, extra, inner, res)
        if best is None:
            raise SystemExit(f"{rep['_id']} {name}: no grid fit")
        _, a, b, match, extra, inner, res = best
        J = sorted(match)
        miss = [vals[j] for j in range(n) if j not in match]
        rep[name] = dict(gridlines=len(J), expected=n, hidden=miss, residual_px=round(float(res), 2),
                         off_scale_frame_px=[round(q, 1) for q in extra])
        if inner:
            raise SystemExit(f"{rep['_id']} {name}: gridlines {inner} px match no expected line")
        if len(extra) > 2:
            raise SystemExit(f"{rep['_id']} {name}: {len(extra)} unexplained lines {extra}")
        if len(miss) > MISS_MAX * n or 0 not in match or n - 1 not in match:
            raise SystemExit(f"{rep['_id']} {name}: hidden gridlines {miss}")
        if res > FIT_TOL * s:
            raise SystemExit(f"{rep['_id']} {name}: grid residual {res:.2f} px")
        self.a, self.b = a, b

    def pos(self, v):
        return self.a + self.b * (v if self.kind == LIN else math.log10(v))

    def value(self, p):
        u = (p - self.a) / self.b
        return u if self.kind == LIN else 10 ** u


def find_frame(ink, box, s):
    x0, y0, x1, y1 = box
    sub = ink[y0:y1, x0:x1] > 0.16
    rows = [i for i in np.where(sub.mean(1) > 0.45)[0]]
    cols = [i for i in np.where(sub.mean(0) > 0.45)[0]]
    if not rows or not cols:
        raise SystemExit(f"no frame in {box}")
    return x0 + cols[0], y0 + rows[0], x0 + cols[-1], y0 + rows[-1]


def gridlines(ink, fr):
    """Gridline rows / columns inside (and on) the frame: (centres, pixel groups) for rows and columns."""
    fx0, fy0, fx1, fy1 = fr
    sub = ink[fy0 - 2:fy1 + 3, fx0 - 2:fx1 + 3] > 0.16
    rc = sub[:, 2:-2].mean(1); cc = sub[2:-2, :].mean(0)
    rows = clusters([i for i in np.where(rc > GRID_COVER)[0]], rc)
    cols = clusters([i for i in np.where(cc > GRID_COVER)[0]], cc)
    return ([fy0 - 2 + c for c, _ in rows], [[fy0 - 2 + i for i in m] for _, m in rows],
            [fx0 - 2 + c for c, _ in cols], [[fx0 - 2 + i for i in m] for _, m in cols])


def tick_check(ink, fr, X, Y, s, rep, gid):
    fx0, fy0, fx1, fy1 = fr
    out = {}
    # x labels: ink columns in a band under the frame
    band = ink[int(fy1 + 8 * s):int(fy1 + 30 * s), int(fx0 - 20 * s):int(fx1 + 20 * s)] > 0.4
    cols = np.where(band.any(0))[0]
    cl = []
    for c in cols:
        if cl and c - cl[-1][-1] <= 14 * s:
            cl[-1].append(c)
        else:
            cl.append([c])
    xc = [int(fx0 - 20 * s) + (c[0] + c[-1]) / 2 for c in cl]
    rows = np.where((ink[int(fy0 - 10 * s):int(fy1 + 10 * s), int(fx0 - 55 * s):int(fx0 - 3 * s)] > 0.4).any(1))[0]
    rl = []
    for r in rows:
        if rl and r - rl[-1][-1] <= 3 * s:
            rl[-1].append(r)
        else:
            rl.append([r])
    yc = [int(fy0 - 10 * s) + (r[0] + r[-1]) / 2 for r in rl]
    for name, A, cs in (("x", X, xc), ("y", Y, yc)):
        if len(cs) != len(A.labels):
            raise SystemExit(f"{gid}: {len(cs)} {name} tick-label clusters for {len(A.labels)} labels {A.labels}")
        off = [c - A.pos(v) for c, v in zip(sorted(cs, reverse=(name == "y")), A.labels)]
        out[name] = round(float(max(abs(o) for o in off)), 2)
        spacing = abs(A.pos(A.labels[1]) - A.pos(A.labels[0]))
        if max(abs(o) for o in off) > LABEL_TOL * spacing:
            raise SystemExit(f"{gid}: {name} tick labels off their gridlines by {off}")
    rep["tick_label_offset_px"] = out


def curve_components(ink, fr, grid_rows, grid_cols, s, thr=0.45, exclude=None):
    """Curve ink inside the frame. A gridline pixel is blanked unless the ink continues on the pixel just beyond
    the gridline on either side (a curve stroke crossing or running along it)."""
    fx0, fy0, fx1, fy1 = fr
    ib = ink > thr
    m = np.zeros_like(ib)
    m[fy0 + 2:fy1 - 1, fx0 + 2:fx1 - 1] = ib[fy0 + 2:fy1 - 1, fx0 + 2:fx1 - 1]
    blank = np.zeros_like(m)
    for g in grid_rows:
        r0, r1 = min(g), max(g)
        keep = ib[r0 - 1, :] | ib[r1 + 1, :]
        for r in g:
            blank[r, :] |= ~keep
    for g in grid_cols:
        c0, c1 = min(g), max(g)
        keep = ib[:, c0 - 1] | ib[:, c1 + 1]
        for c in g:
            blank[:, c] |= ~keep
    m &= ~blank
    if exclude:
        ex0, ey0, ex1, ey1 = exclude
        m[ey0:ey1, ex0:ex1] = False
    # bridge the 1-px gaps left by blanked gridlines along the gridline's normal only (a full 3x3
    # closing merges TP4E's 32/25 kHz lines, which run 2-3 px apart)
    closed = m | nd.binary_closing(m, np.ones((1, 3))) | nd.binary_closing(m, np.ones((3, 1)))
    lab, n = nd.label(closed, np.ones((3, 3)))
    return lab, n, m, blank


def centreline(ink, mask, s):
    """{x: y} ink-weighted centre row per column; columns without ink (blanked gridline columns)
    are linearly interpolated, but only across gaps of at most GAP_MAX px."""
    ys, xs = np.nonzero(mask)
    cl = {}
    for x in np.unique(xs):
        yy = ys[xs == x]
        cl[int(x)] = float(np.average(yy, weights=ink[yy, x]))
    known = sorted(cl)
    out = dict(cl)
    for lo, hi in zip(known, known[1:]):
        if hi - lo > 1:
            if hi - lo > GAP_MAX * s:
                raise SystemExit(f"curve has a {hi - lo} px gap at column {lo}")
            for x in range(lo + 1, hi):
                out[x] = cl[lo] + (cl[hi] - cl[lo]) * (x - lo) / (hi - lo)
    return out


def split_tracks(ink, mask, s):
    """A component normally holds one curve; where two thin curves touch (TP4E 100 C, 32/25 kHz) it
    holds k. Per column the ink rows are grouped (gaps <= 3 px, i.e. a blanked gridline, do not
    split a group); k = the most common group count. Columns showing k groups give each track its
    ink-weighted centre (top group -> track 0); other columns (where the curves touch) are left out
    and bridged by centreline-style interpolation only if the gap is <= GAP_MAX."""
    ys, xs = np.nonzero(mask)
    groups = {}
    for x in np.unique(xs):
        yy = np.sort(ys[xs == x])
        gs, cur = [], [yy[0]]
        for y in yy[1:]:
            if y - cur[-1] > 3:
                gs.append(cur); cur = []
            cur.append(y)
        gs.append(cur)
        groups[int(x)] = [float(np.average(g, weights=ink[g, x])) for g in gs]
    cnt = np.bincount([len(v) for v in groups.values()])
    k = int(np.argmax(cnt))
    if k == 1:
        return [centreline(ink, mask, s)]
    tracks = []
    for t in range(k):
        cl = {x: v[t] for x, v in groups.items() if len(v) == k}
        known = sorted(cl)
        out = dict(cl)
        for lo, hi in zip(known, known[1:]):
            if hi - lo > 1:
                if hi - lo > GAP_MAX * s:
                    raise SystemExit(f"split curve has a {hi - lo} px gap at column {lo}")
                for x in range(lo + 1, hi):
                    out[x] = cl[lo] + (cl[hi] - cl[lo]) * (x - lo) / (hi - lo)
        tracks.append(out)
    return tracks


def interp(cl, xp):
    xs = sorted(cl)
    if xp < xs[0] or xp > xs[-1]:
        raise ValueError("outside the drawn curve")
    i = int(math.floor(xp))
    if i == xs[-1]:
        return cl[i]
    return cl[i] + (cl[i + 1] - cl[i]) * (xp - i)


def sample_points(cl, X, Y, grid, s):
    xs = sorted(cl)
    pts = []
    for g in grid:
        xp = X.pos(g)
        if xs[0] - END_TOL * s <= xp <= xs[-1] + END_TOL * s:
            xq = min(max(xp, xs[0]), xs[-1])
            pts.append((g, Y.value(interp(cl, xq))))
    return pts


def pt(f, B, T, v):
    return {"magneticFluxDensity": {"frequency": float(f), "magneticFluxDensity": {
        "processed": {"label": "sinusoidal", "peak": float(B), "offset": 0.0}}},
        "temperature": float(T), "value": float(f"{v:.4g}"), "origin": "manufacturer"}


def figure_setup(ink, box, ax, ay, s, rep, gid):
    fr = find_frame(ink, box, s)
    rows, rowpix, cols, colpix = gridlines(ink, fr)
    X = Axis(ax[0], ax[1], ax[2], ax[3] if ax[0] == LIN else None, cols, s, rep, "x")
    Y = Axis(ay[0], ay[1], ay[2], ay[3] if ay[0] == LIN else None, rows, s, rep, "y", flip=True)
    tick_check(ink, fr, X, Y, s, rep, gid)
    rep["frame_px"] = [int(v) for v in fr]
    return fr, X, Y, rowpix, colpix


def debug_png(path, ink, box, curves_px):
    x0, y0, x1, y1 = box
    g = (255 * (1 - ink[y0:y1, x0:x1])).astype(np.uint8)
    im = np.stack([g, g, g], -1)
    for cl in curves_px:
        for x, y in cl.items():
            yy, xx = int(round(y)) - y0, x - x0
            if 0 <= yy < im.shape[0] and 0 <= xx < im.shape[1]:
                im[yy, xx] = (255, 0, 0)
    Image.fromarray(im).save(path)


# ---------------------------------------------------------------------------------------------- figures
def read_pvt(ink, g, cfg, s, rep, dbg):
    H, W = ink.shape
    box = (0, int(0.02 * H), W // 2, int(0.40 * H))
    fr, X, Y, rows, cols = figure_setup(ink, box, cfg["x"], cfg["y"], s, rep, f"{g} Pv-T")
    exclude = None
    if len(cfg["curves"]) == 2:    # TP5i: legend box (two keys) in the upper left of the frame
        lab, n, m, blank = curve_components(ink, fr, rows, cols, s)
        sl = nd.find_objects(lab)
        keys = [o for o in sl if o and o[0].stop - o[0].start <= 4 * s and o[1].stop - o[1].start > 20 * s]
        if not keys:
            raise SystemExit(f"{g}: legend key not found")
        k = keys[0]
        exclude = (k[1].start - int(8 * s), k[0].start - int(15 * s), k[1].start + int(150 * s), k[0].stop + int(30 * s))
        rep["legend_excluded_px"] = [int(v) for v in exclude]
    lab, n, m, blank = curve_components(ink, fr, rows, cols, s, exclude=exclude)
    sl = nd.find_objects(lab)
    big = [i + 1 for i, o in enumerate(sl) if o and max(o[0].stop - o[0].start, o[1].stop - o[1].start) > CURVE_MIN * s]
    curves = []
    if len(cfg["curves"]) == 1:
        if len(big) != 1:
            raise SystemExit(f"{g} Pv-T: {len(big)} curves")
        curves.append(centreline(ink, m & (lab == big[0]), s))
    else:
        if len(big) != 1:
            raise SystemExit(f"{g} Pv-T: {len(big)} solid curves")
        solid = centreline(ink, m & (lab == big[0]), s)
        # dashes: components 5..60 px long below the solid curve, each a short stroke
        dash = np.zeros_like(m)
        nd_ = 0
        for i, o in enumerate(sl):
            if not o or i + 1 == big[0]:
                continue
            h, w = o[0].stop - o[0].start, o[1].stop - o[1].start
            cx = (o[1].start + o[1].stop) // 2
            if 6 * s <= max(h, w) <= 40 * s and h <= 12 * s and cx in solid and o[0].start > solid[cx] + 10 * s:
                dash |= m & (lab == i + 1); nd_ += 1
        rep["dashes"] = nd_
        dl = {}
        ys, xs = np.nonzero(dash)
        for x in np.unique(xs):
            yy = ys[xs == x]; dl[int(x)] = float(np.average(yy, weights=ink[yy, x]))
        # dashed line: interpolate across the dash gaps only (gaps <= 12 px at 220 dpi)
        ks = sorted(dl)
        gaps = [ks[i + 1] - ks[i] for i in range(len(ks) - 1)]
        if max(gaps) > 14 * s:
            raise SystemExit(f"{g}: dashed curve gap {max(gaps)} px")
        full = {}
        for i in range(len(ks) - 1):
            for x in range(ks[i], ks[i + 1]):
                full[x] = dl[ks[i]] + (dl[ks[i + 1]] - dl[ks[i]]) * (x - ks[i]) / (ks[i + 1] - ks[i])
        full[ks[-1]] = dl[ks[-1]]
        rep["dashed_gap_max_px"] = int(max(gaps))
        curves = [solid, full]
    if dbg:
        debug_png(os.path.join(dbg, f"{g}_pvt.png"), ink, box, curves)
    return X, Y, curves


def read_pvb(ink, g, cfg, side, s, rep, dbg):
    H, W = ink.shape
    box = (0 if side == 0 else W // 2, int(0.42 * H), W // 2 if side == 0 else W, H)
    fr, X, Y, rows, cols = figure_setup(ink, box, cfg["x"], cfg["y"], s, rep, f"{g} Pv-B {cfg['T']}C")
    lab, n, m, blank = curve_components(ink, fr, rows, cols, s)
    sl = nd.find_objects(lab)
    big = [i + 1 for i, o in enumerate(sl) if o and max(o[0].stop - o[0].start, o[1].stop - o[1].start) > CURVE_MIN * s]
    cls = []
    for i in big:
        tr = split_tracks(ink, m & (lab == i), s)
        if len(tr) > 1:
            rep.setdefault("split_components", []).append(len(tr))
        cls += tr
    if len(cls) != len(cfg["freqs"]):
        raise SystemExit(f"{g} Pv-B {cfg['T']}C: {len(cls)} curves for legend {cfg['freqs']}")

    # vertical order from every pair's overlap; a pair that crosses, or does not overlap, fails
    def above(i, j):
        ov = set(cls[i]) & set(cls[j])
        if not ov:
            raise SystemExit(f"{g} Pv-B {cfg['T']}C: two curves do not overlap")
        d = [cls[i][x] < cls[j][x] for x in ov]
        if not (all(d) or not any(d)):
            raise SystemExit(f"{g} Pv-B {cfg['T']}C: two curves cross")
        return d[0]
    order = sorted(range(len(cls)), key=functools.cmp_to_key(lambda i, j: -1 if above(i, j) else 1))
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            if not above(order[i], order[j]):
                raise SystemExit(f"{g} Pv-B {cfg['T']}C: no consistent vertical order")
    freqs = cfg["freqs"]
    if sorted(freqs, reverse=True) != freqs:
        raise SystemExit(f"{g}: legend order {freqs} is not the physics order")
    out = {f: cls[k] for f, k in zip(freqs, order)}
    spans = {f"{f/1e3:g}kHz": [round(X.value(min(c)), 1), round(X.value(max(c)), 1)] for f, c in out.items()}
    rep["curve_spans_mT"] = spans
    if dbg:
        debug_png(os.path.join(dbg, f"{g}_pvb{cfg['T']}.png"), ink, box, list(out.values()))
    return X, Y, out


# ---------------------------------------------------------------------------------------------- main
def emit(records, g, pts, rep):
    """MAS volumetricLossesPoint lists need >= 4 unique points (material.json minItems 4): a grade
    with fewer is NOT emitted (no schema-invalid record is ever written) and the report says so."""
    keys = [json.dumps(p, sort_keys=True) for p in pts]
    if len(set(keys)) != len(keys):
        raise SystemExit(f"{g}: duplicate points")
    if len(pts) < 4:
        rep["NOT_EMITTED"] = f"only {len(pts)} points; MAS needs >= 4 in a points list"
        print(f"{g}: NOT EMITTED, {len(pts)} points < 4")
        return
    records.append({"name": g, "manufacturerInfo": {"name": "TDG"}, "volumetricLosses": {"default": [pts]}})


def check_source(path, g):
    fid, size, sha = SOURCES[g]
    b = open(path, "rb").read()
    h = hashlib.sha256(b).hexdigest()
    if len(b) != size:
        raise SystemExit(f"{g}: {len(b)} B, expected {size}")
    if sha and h != sha:
        raise SystemExit(f"{g}: sha256 {h} != {sha}")
    return dict(url=BASE + fid + ".pdf", bytes=len(b), sha256=h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srcdir")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    ap.add_argument("--debug")
    a = ap.parse_args()
    records, report = [], {}
    for g, cfg in GRADES.items():
        rep = report.setdefault(g, {})
        rep["source"] = check_source(os.path.join(a.srcdir, g + ".pdf"), g)
        rep["table_kW_m3"] = {f"{f/1e3:g}kHz/{B*1e3:g}mT": t for (f, B), t in cfg["table"].items()}
        pts = []
        if cfg["pvt"] is None:
            rep["figures"] = "none: the sheet prints no core-loss figure; table points only"
            for (f, B), t in cfg["table"].items():
                for T, v in sorted(t.items()):
                    pts.append(pt(f, B, T, v * 1e3))
            rep["points"] = len(pts)
            emit(records, g, pts, rep)
            print(f"{g}: table only, {len(pts)} points")
            continue
        doc = fitz.open(os.path.join(a.srcdir, g + ".pdf"))
        ink = page_ink(doc, 1)
        s = ink.shape[1] / 1359.0
        rep["page2_px"] = list(ink.shape[::-1])
        # ---- Pv-T
        r = rep.setdefault("pvt", {"_id": g + " Pv-T"})
        pvt_ok = {}
        try:
            X, Y, cls = read_pvt(ink, g, cfg["pvt"], s, r, a.debug)
            for (f, B), cl in zip(cfg["pvt"]["curves"], cls):
                key = f"{f/1e3:g}kHz/{B*1e3:g}mT"
                t0, t1 = X.value(min(cl)), X.value(max(cl))
                chk = []
                for T, v in sorted(cfg["table"][(f, B)].items()):
                    if t0 - 0.5 <= T <= t1 + 0.5:
                        c = Y.value(interp(cl, min(max(X.pos(T), min(cl)), max(cl))))
                        chk.append(dict(T=T, table=v, curve=round(c, 1), ratio=round(c / v, 3)))
                    else:
                        chk.append(dict(T=T, table=v, curve=None, note="outside the drawn span"))
                cr = r.setdefault("curves", {})[key] = dict(span_C=[round(t0, 1), round(t1, 1)], table=chk)
                bad = [c for c in chk if c.get("ratio") and abs(c["ratio"] - 1) > TABLE_TOL]
                if not [c for c in chk if c.get("ratio")]:
                    cr["REJECTED"] = "no printed table temperature inside the curve"
                elif bad:
                    cr["REJECTED"] = "; ".join(f"{c['T']} C reads {c['curve']} vs table {c['table']} ({c['ratio']})"
                                               for c in bad)
                if "REJECTED" in cr:
                    print(f"{g} Pv-T {key}: REJECTED {cr['REJECTED']}")
                    continue
                Ts = sorted(set([T for T in range(-60, 200, 10) if t0 - 0.5 <= T <= t1 + 0.5]
                                + [T for T in cfg["table"][(f, B)] if t0 - 0.5 <= T <= t1 + 0.5]
                                + ([25] if t0 - 0.5 <= 25 <= t1 + 0.5 else [])))
                vals = []
                for T in Ts:
                    xq = min(max(X.pos(T), min(cl)), max(cl))
                    vals.append((T, Y.value(interp(cl, xq))))
                pvt_ok[(f, B)] = (X, Y, cl)
                cr["points"] = [(T, round(v, 1)) for T, v in vals]
                pts += [pt(f, B, T, v * 1e3) for T, v in vals]
        except SystemExit as e:
            r["REJECTED"] = str(e); print(f"{g} Pv-T: REJECTED {e}")
        r.pop("_id", None)
        # ---- Pv-B
        for side, pc in enumerate(cfg["pvb"]):
            T = pc["T"]
            r = rep.setdefault(f"pvb_{T}C", {"_id": f"{g} Pv-B {T}C"})
            try:
                X, Y, cur = read_pvb(ink, g, pc, side, s, r, a.debug)
                checks = []
                for (f, B), tab in cfg["table"].items():
                    if f not in cur:
                        continue
                    cl = cur[f]
                    xp = X.pos(B * 1e3)
                    if not (min(cl) - END_TOL * s <= xp <= max(cl) + END_TOL * s):
                        continue
                    c = Y.value(interp(cl, min(max(xp, min(cl)), max(cl))))
                    if T in tab:
                        ref, via = tab[T], "table"
                    elif (f, B) in pvt_ok:
                        PX, PY, pcl = pvt_ok[(f, B)]
                        if not (min(pcl) <= PX.pos(T) <= max(pcl)):
                            continue
                        ref, via = PY.value(interp(pcl, PX.pos(T))), "via Pv-T"
                    else:
                        continue
                    checks.append(dict(cond=f"{f/1e3:g}kHz/{B*1e3:g}mT", ref=round(ref, 1), via=via,
                                       curve=round(c, 1), ratio=round(c / ref, 3)))
                r["check"] = checks
                if not checks:
                    raise SystemExit(f"{g} Pv-B {T}C: no checkable curve (table or accepted Pv-T)")
                bad = [c for c in checks if abs(c["ratio"] - 1) > TABLE_TOL]
                if bad:
                    raise SystemExit(f"{g} Pv-B {T}C: " + "; ".join(
                        f"{c['cond']} reads {c['curve']} vs {c['ref']} {c['via']} ({c['ratio']})" for c in bad))
                n0 = len(pts)
                r["points"] = {}
                for f, cl in cur.items():
                    sp = sample_points(cl, X, Y, B_GRID, s)
                    r["points"][f"{f/1e3:g}kHz"] = [(b, round(v, 2)) for b, v in sp]
                    pts += [pt(f, b / 1e3, T, v * 1e3) for b, v in sp]
                r["n_points"] = len(pts) - n0
            except SystemExit as e:
                r["REJECTED"] = str(e); print(f"{g} Pv-B {T}C: REJECTED {e}")
            r.pop("_id", None)
        if not pts:
            rep["fallback"] = "every figure rejected: printed table points only"
            pts = [pt(f, B, T, v * 1e3) for (f, B), tb in cfg["table"].items() for T, v in sorted(tb.items())]
        rep["points"] = len(pts)
        emit(records, g, pts, rep)
        print(f"{g}: {len(pts)} points; " + "; ".join(
            f"{k}: " + ",".join(str(c.get("ratio")) for c in (v.get("table") or v.get("check") or []))
            for k, v in rep.items() if k.startswith("pv") and isinstance(v, dict)
            for v in ([v] if "check" in v else v.get("curves", {}).values())))
    json.dump(records, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1, default=float)
    return 0


if __name__ == "__main__":
    sys.exit(main())
