#!/usr/bin/env python3
"""Digitize Huoh Yow's MnZn "Core loss - Flux density" charts and keep its printed Pcv table (ABT #1518).

    python3 scripts/digitize-huohyow-loss.py --pdf-dir <dir with KL*.pdf> --table <cat21.html> \
            --json points.json --report report.json [--debug <dir>]

Source
------
Huoh Yow (Huayou Enterprise, https://www.huohyow.com.tw) publishes one data sheet per grade, linked from the
MnZn material category page https://www.huohyow.com.tw/en/index.php?c=category&id=21 (fetched 2026-09-29):

    KL95W  /uploadfile/ueditor/file/202410/17303843613616c9.pdf  sha256 2f284fbb1a508c035b1b32e4aa0599706d3a1cc75b47b28eb8ff1732fd4bfee1
    KL45   /uploadfile/ueditor/file/202410/1730384389cceea4.pdf  sha256 a2bb1688387d668595c8c98db59eeb0211f90b03c2a8300da6601dd43db7524f
    KL33W  /uploadfile/ueditor/file/202410/1730384374b1dfb6.pdf  sha256 4e77a32c2f5a99fea73299be2b6518c0b99674914fba55083ace60a42e6bdfb6
    KL96W  /uploadfile/ueditor/file/202410/1730384350fd276b.pdf  sha256 b583135c03c50e9434d3105b39bca4f8bba1d254e97f0edf86348fe12c7e0bac
    KL40   /uploadfile/ueditor/file/202410/1730384410804327.pdf  sha256 bb844bfc97b8f05c8462ca979a743a900a72bafd3289b1feedca0aaaea4a08c9

The PDFs are WPS exports of a spreadsheet: every page is a JPEG (extracted here with `pdfimages -j`), so the
charts are raster.  The category page itself carries a NUMERIC table, "Core loss volume density Pcv (kW/m3)
100KHz 200mT" at 20/60/80/100/120 C per grade.  Those printed numbers are stored exactly, as points
(TABLE below, transcribed from the page and asserted against it at run time).

What is digitized, and what is not
----------------------------------
* KL95W: Pv-B at 100 C (100 and 200 kHz).  KL45: Pv-B at 20 C and 100 C (25/100/200 kHz).
  KL33W: Pv-B at 20 C and 80 C (100/200/500 kHz).
* KL96W: its data sheet has no Pv-B chart (Pv-T only) -> table points only.
* KL40: the file linked as KL40 is the KM40T data sheet (header "KM40T", mu_i 4000, no loss chart) -> table
  points only.
* The Pv-T charts are drawn through the same table values; they are not digitized.
* KL7F/KL9F/KL11F are out of scope: their Pv-B lines are the printed Cm f^a B^b formula, not measurements.

Waveform: Huoh Yow does not state it.  The label "sinusoidal" is what the IEC 62044-3 / IEC 61332 Pcv
convention every ferrite maker's catalogue table uses, and what MAS uses for all other maker Pcv data.

Method (the #1006 bar: a check that can FAIL)
---------------------------------------------
1. Axes.  The decade limits are declared per chart from the printed tick labels (x 10..1000 mT, y 1..10^4
   kW/m3 on every chart).  They are then VERIFIED: every dark vertical gridline found in the plot must sit
   within GRID_TOL_PX of a 1..9 x 10^k position of the fitted log axis; the dark horizontal gridlines must be
   the equally spaced decades, as many as the declared range has; and the pale-yellow minor horizontals must
   land on the 2..9 x 10^k positions those decades define (MINOR_TOL_PX; 7/8/9 blur together, so at least
   75 % of the 2..5 lines are required).  A chart failing any of these is rejected.
2. Curves.  Pixels are classed by the legend's colours (red / green / navy).  The legend is an opaque box
   with a dark frame: it is found by flood-filling its interior from just above the first key's swatch, and
   excluded (gridline coverage is also measured outside it, since it hides them).  The declared colour ->
   frequency map (read off the legend text) is checked two ways: each declared colour must have a swatch
   inside the legend box in the declared top-to-bottom order, and loss must rise with frequency at every B
   the curves share (physics).
3. Trace.  Per column, the centre of the colour's single ink run.  Round caps at the curve ends and at every
   dash end (the 25/100 kHz lines are dashed) are half a line width of ink that is not the line; columns
   within that distance of a gap are dropped.  Tracing noise = each column against a straight line through
   its +-LOCAL_PX neighbours (the lines are polylines with kinks at the maker's data points, so a global fit
   would measure shape, not noise); a curve noisier than MAX_TRACE_RMS_PCT is refused.  A curve touching
   the plot frame may be clipped there by the plotting program, so no sample is taken near such a column.
4. Samples.  At the preferred B values of the E-series used by the charts (SAMPLE_MT) inside the drawn span,
   each read as a local log-log line through the trace columns within +-LOCAL_PX.  Nothing is extrapolated.
5. Check against the same data sheet.  Wherever a chart has the 100 kHz curve at a table temperature, its
   value at 200 mT must match the printed table within TABLE_TOL, else the whole chart is rejected.  Where
   the 100 kHz curve stops short of 200 mT (KL33W ends at 135-144 mT) the check is made on the power-law
   continuation of the curve's last third (only a CHECK -- that value is never stored) with the wider
   EXTRAP_TOL.  At a condition the table also prints, the table value is stored and the digitized one is
   dropped.

Result (2026-09-29): KL95W 100 C accepted (table ratio 1.011); KL45 20 C accepted (1.035), KL45 100 C
REJECTED (1.100); KL33W 20 C and 80 C REJECTED (continuation 1.33x and 1.57x the table).  Stored: 25 table
points (5 grades x 5 temperatures) + 52 digitized (KL95W 22, KL45 30).
"""
import argparse
import html as htmlmod
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage

GRID_TOL_PX = 1.6
MINOR_TOL_PX = 2.0     # pale 1-px minor lines, 7/8/9 merge into one blur
TABLE_TOL = 0.10
EXTRAP_TOL = 0.15
MAX_TRACE_RMS_PCT = 3.0
LOCAL_PX = 5
SNAP_DEC = 0.02            # an end point within this many decades of a preferred value is that value
SAMPLE_MT = [10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 100, 120, 150, 200, 250, 300, 400, 500]

# Printed table on the category page (kW/m3, 100 kHz, 200 mT) -- asserted against the HTML at run time.
TABLE_T = [20, 60, 80, 100, 120]
TABLE = {"KL40": [680, 450, 390, 400, 500], "KL45": [600, 390, 380, 520, 680],
         "KL33W": [379, 340, 320, 340, 370], "KL95W": [420, 400, 370, 420, 495],
         "KL96W": [400, 360, 345, 340, 380]}

PDF = {"KL95W": "17303843613616c9", "KL45": "1730384389cceea4", "KL33W": "1730384374b1dfb6",
       "KL96W": "1730384350fd276b", "KL40": "1730384410804327"}

LOGX, LOGY = (10.0, 1000.0), (1.0, 1e4)     # mT, kW/m3 -- printed tick labels, same on every chart
CHARTS = {
    # panel = (x0, y0, x1, y1) px of the chart's frame on the page image (a region, not a calibration)
    "KL95W": [dict(page=2, panel=(0, 280, 535, 545), T=100, legend=[("red", 200e3), ("green", 100e3)])],
    "KL45": [dict(page=2, panel=(0, 265, 522, 525), T=20, legend=[("red", 200e3), ("green", 100e3), ("navy", 25e3)]),
             dict(page=2, panel=(528, 265, 978, 525), T=100, legend=[("red", 200e3), ("green", 100e3), ("navy", 25e3)])],
    "KL33W": [dict(page=2, panel=(0, 250, 532, 510), T=20, legend=[("red", 500e3), ("green", 200e3), ("navy", 100e3)]),
              dict(page=2, panel=(538, 250, 978, 510), T=80, legend=[("red", 500e3), ("green", 200e3), ("navy", 100e3)])],
}


def colour_mask(im, name):
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    if name == "red":
        return (r > 150) & (g < 110) & (b < 110) & (r - g > 90)
    if name == "green":
        return (g > 100) & (g - r > 40) & (g - b > 15) & (r < 140)
    if name == "navy":
        return (b > 60) & (r < 80) & (g < 80) & (b - r > 40)
    raise ValueError(name)


def runs(bool1d):
    """[(start, end_inclusive)] of True runs."""
    out, start = [], None
    for i, v in enumerate(bool1d):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1)); start = None
    if start is not None:
        out.append((start, len(bool1d) - 1))
    return out


def centres(idx):
    """Merge adjacent indices into line centres."""
    out, grp = [], []
    for i in idx:
        if grp and i != grp[-1] + 1:
            out.append(sum(grp) / len(grp)); grp = []
        grp.append(i)
    if grp:
        out.append(sum(grp) / len(grp))
    return out


def calibrate_x(vlines, lo, hi):
    """Fit pos = a + b*log10(v) to the dark verticals; each must sit on a 1..9x10^k position."""
    vals = [m * 10 ** k for k in range(int(round(math.log10(lo))), int(round(math.log10(hi))) + 1) for m in range(1, 10)]
    vals = [v for v in vals if lo <= v <= hi + 1e-9]
    best = None
    for i, p0 in enumerate(vlines):           # p0 = position of lo
        for p1 in vlines[i + 1:]:            # p1 = position of lo*10
            b = p1 - p0
            if b < 40:
                continue
            a = p0 - b * math.log10(lo)
            pred = [a + b * math.log10(v) for v in vals]
            res = [min(abs(x - q) for q in pred) for x in vlines]
            score = (sum(r <= GRID_TOL_PX for r in res), -sum(res))
            if best is None or score > best[0]:
                best = (score, a, b, res)
    (_, a, b, res) = best
    bad = [(round(x, 1), round(r, 2)) for x, r in zip(vlines, res) if r > GRID_TOL_PX]
    if bad:
        raise RuntimeError(f"x gridlines off the log axis: {bad}")
    return a, b


def calibrate_y(hlines, minor, lo, hi):
    """Dark rows are the decades (equally spaced, as many as the declared range has); the pale-yellow
    rows are the 2..9 x 10^k minor lines and must each land on the log axis those decades define."""
    ndec = int(round(math.log10(hi / lo)))
    hl = sorted(hlines)
    if len(hl) != ndec + 1:
        raise RuntimeError(f"expected {ndec + 1} decade gridlines, found {len(hl)} at {[round(h, 1) for h in hl]}")
    step = np.diff(hl)
    if step.max() - step.min() > 2 * GRID_TOL_PX:
        raise RuntimeError(f"decade gridlines unequally spaced: {step}")
    # row = c - d*log10(v): bottom line is lo, top is hi
    d = (hl[-1] - hl[0]) / ndec
    c = hl[-1] + d * math.log10(lo)
    decs = range(int(round(math.log10(lo))), int(round(math.log10(hi))))
    pred = [c - d * math.log10(m * 10 ** k) for k in decs for m in range(2, 10)]
    must = [c - d * math.log10(m * 10 ** k) for k in decs for m in range(2, 6)]
    near = lambda y, P: min(abs(y - q) for q in P)
    bad = [(round(y, 1), round(near(y, pred), 2)) for y in minor if near(y, pred) > MINOR_TOL_PX]
    missing = [round(q, 1) for q in must if near(q, minor) > MINOR_TOL_PX]
    if bad or len(missing) > 0.25 * len(must):
        raise RuntimeError(f"minor y gridlines off the log axis {bad}, missing at {missing}")
    return c, d


def find_legend(pan, colour):
    """The legend is an opaque white box with a dark frame, i.e. a closed region of the plot that no
    gridline crosses.  Seed a flood fill of non-dark pixels just above the declared first key's swatch (a
    short, thick horizontal stroke of that colour); the fill stays inside the frame (text is dark, so it is
    walked around).  A fill that escapes into the plot is caught by its size."""
    dark = pan.max(2) < 150
    m = colour_mask(pan, colour)
    lab, n = ndimage.label(m)
    sw = []
    for sl in ndimage.find_objects(lab):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if 20 <= w <= 90 and h <= 10 and w >= 4 * h:
            sw.append(sl)
    if len(sw) != 1:
        raise RuntimeError(f"{len(sw)} candidate {colour} legend swatches")
    sl = sw[0]
    seed = (sl[0].start - 3, (sl[1].start + sl[1].stop) // 2)
    free = ~dark & ~m
    lab, _ = ndimage.label(free)
    region = lab == lab[seed]
    if not lab[seed] or region.sum() > 0.25 * free.size:
        raise RuntimeError("legend interior not closed")
    ys, xs = np.nonzero(region)
    if xs.max() - xs.min() < 60 or ys.max() - ys.min() < 25:
        raise RuntimeError(f"legend interior too small ({xs.min()}..{xs.max()}, {ys.min()}..{ys.max()})")
    return int(ys.min()) - 3, int(ys.max()) + 3, int(xs.min()) - 3, int(xs.max()) + 3


def find_plot(pan, legend_colour):
    """Plot frame, gridlines and legend box.

    The minor horizontals are pale-yellow rows; the decades, the verticals and the (grey) frame are dark
    lines.  Gridline coverage is measured outside the legend box, which hides the gridlines behind it."""
    dark = pan.max(2) < 150        # black gridlines and the grey (~130) frame
    r, g, b = pan[..., 0], pan[..., 1], pan[..., 2]
    yel = (r > 225) & (g > 225) & (b < 225) & (r - b > 15)
    H, W = dark.shape
    yrows = np.nonzero(yel.mean(1) > 0.2)[0]
    if len(yrows) < 5:
        raise RuntimeError("no minor gridlines")
    ycols = np.nonzero(yel[yrows].sum(0) >= 0.3 * len(yrows))[0]
    xa, xb = int(ycols.min()), int(ycols.max())
    ya, yb = int(yrows.min()), int(yrows.max())
    leg = find_legend(pan, legend_colour)
    ly0, ly1, lx0, lx1 = leg
    vis = np.ones_like(dark)
    vis[ly0:ly1 + 1, lx0:lx1 + 1] = False
    def cover_row(y, x0, x1):
        v = vis[y, x0:x1 + 1]
        return dark[y, x0:x1 + 1][v].mean() if v.sum() > 20 else 0.0
    def cover_col(x, y0, y1):
        v = vis[y0:y1 + 1, x]
        return dark[y0:y1 + 1, x][v].mean() if v.sum() > 20 else 0.0
    hrows = [y for y in range(max(ya - 25, 0), min(yb + 26, H)) if cover_row(y, xa, xb) >= 0.6]
    hl = centres(hrows)
    if len(hl) < 2:
        raise RuntimeError(f"decade gridlines not found ({hl})")
    y0, y1 = int(round(min(hl))), int(round(max(hl)))
    vcols = [x for x in range(max(xa - 4, 0), min(xb + 5, W)) if cover_col(x, y0, y1) >= 0.7]
    vl = centres(vcols)
    if len(vl) < 4:
        raise RuntimeError(f"vertical gridlines not found ({vl})")
    x0, x1 = int(round(min(vl))), int(round(max(vl)))
    minor = centres([y for y in range(y0 + 2, y1 - 1) if yel[y, x0:x1 + 1][vis[y, x0:x1 + 1]].mean() > 0.2])
    return vl, hl, minor, (y0, y1, x0, x1), leg


def trace(mask):
    """{x: y_centre} for a single-curve mask; columns holding two separated ink runs are dropped."""
    lab, n = ndimage.label(mask)
    if n:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 25])
        mask = mask & keep
    out, thick = {}, []
    for x in range(mask.shape[1]):
        rr = runs(mask[:, x])
        if len(rr) == 1:
            s, e = rr[0]
            out[x] = (s + e) / 2.0
            thick.append(e - s + 1)
    return out, thick


def to_val(x, y, cal):
    (ax, bx), (cy, dy) = cal
    return 10 ** ((x - ax) / bx), 10 ** ((cy - y) / dy)


def digitize_chart(im, spec, debug=None, tag=""):
    x0p, y0p, x1p, y1p = spec["panel"]
    pan = im[y0p:y1p, x0p:x1p].astype(int)
    vl, hl, minor, box, (ly0, ly1, lx0, lx1) = find_plot(pan, spec['legend'][0][0])
    cal = (calibrate_x(vl, *LOGX), calibrate_y(hl, minor, *LOGY))
    y0, y1, x0, x1 = box
    # legend order check: each declared colour has a swatch inside the legend box, top to bottom as declared
    sw = []
    for name, _ in spec["legend"]:
        m = colour_mask(pan, name)[ly0:ly1, lx0:lx1]
        ys, xs = np.nonzero(m)
        if len(ys) < 15:
            raise RuntimeError(f"no {name} swatch in the legend")
        sw.append(float(np.median(ys)))
    if sw != sorted(sw):
        raise RuntimeError(f"legend swatch order {sw} differs from the declared order")
    curves = {}
    for name, f in spec["legend"]:
        m = colour_mask(pan, name)
        m[:y0 + 2, :] = False; m[y1 - 1:, :] = False; m[:, :x0 + 2] = False; m[:, x1 - 1:] = False
        m[ly0:ly1, lx0:lx1] = False
        tr, thick = trace(m)
        if len(tr) < 40:
            raise RuntimeError(f"{name}: only {len(tr)} columns traced")
        xs = np.array(sorted(tr)); ys = np.array([tr[x] for x in xs])
        # vertical ink run -> perpendicular width -> half width = cap overshoot in x
        slope = np.polyfit(xs, ys, 1)[0]
        width = float(np.median(thick)) * math.cos(math.atan(abs(slope)))
        cap = width / 2
        # round caps: at the curve's ends and at every dash end the ink column is a cap, not the line
        present = set(xs.tolist())
        keep = np.array([all((x + dx) in present for dx in range(-int(math.ceil(cap)), int(math.ceil(cap)) + 1))
                         for x in xs])
        xs, ys = xs[keep], ys[keep]
        lb = np.array([math.log10(to_val(x, y, cal)[0]) for x, y in zip(xs, ys)])
        lp = np.array([math.log10(to_val(x, y, cal)[1]) for x, y in zip(xs, ys)])
        # tracing noise: each column against a straight line through its +-LOCAL_PX neighbours (the Excel
        # lines are polylines with kinks at the maker's data points, so a global fit would measure shape)
        q = []
        for i in range(len(xs)):
            nb = (np.abs(xs - xs[i]) <= LOCAL_PX) & (xs != xs[i])
            if nb.sum() >= 4:
                k, m0 = np.polyfit(xs[nb], ys[nb], 1)
                q.append((ys[i] - (k * xs[i] + m0)) / cal[1][1])   # px -> decades
        q = np.array(q)
        rms_pct = float((10 ** np.sqrt((q ** 2).mean()) - 1) * 100)
        if rms_pct > MAX_TRACE_RMS_PCT:
            raise RuntimeError(f"{name}: trace rms {rms_pct:.1f}% > {MAX_TRACE_RMS_PCT}%")
        # a curve touching the plot frame may be clipped there by the plotting program: its end is not data
        clip = [(x, y) for x, y in zip(xs, ys) if min(y - y0, y1 - y) < width]
        clip_mT = sorted({round(to_val(x, y, cal)[0], 1) for x, y in clip})
        curves[f] = dict(colour=name, xs=xs, ys=ys, lb=lb, lp=lp, rms_pct=rms_pct, width_px=width, clip_mT=clip_mT,
                         span_mT=(10 ** lb.min(), 10 ** lb.max()))
    if debug:
        dbg = Image.fromarray(pan.astype(np.uint8)).convert("RGB")
        px = dbg.load()
        for c in curves.values():
            for x, y in zip(c["xs"], c["ys"]):
                px[int(x), int(round(y))] = (255, 0, 255)
        for v in vl:
            px[int(round(v)), y0 - 4] = (0, 0, 255)
        dbg.resize((dbg.width * 2, dbg.height * 2)).save(os.path.join(debug, f"{tag}.png"))
    return curves, cal, box


def read_at(c, b_mt):
    t = math.log10(b_mt)
    px_per_dec = (c["xs"][-1] - c["xs"][0]) / max(c["lb"][-1] - c["lb"][0], 1e-9)
    win = LOCAL_PX / px_per_dec
    sel = np.abs(c["lb"] - t) <= win
    if sel.sum() < 3:
        sel = np.argsort(np.abs(c["lb"] - t))[:5]
    k, m = np.polyfit(c["lb"][sel], c["lp"][sel], 1)
    return 10 ** (k * t + m)


def extrapolate(c, b_mt):
    n = len(c["lb"]); sel = slice(2 * n // 3, n)
    k, m = np.polyfit(c["lb"][sel], c["lp"][sel], 1)
    return 10 ** (k * math.log10(b_mt) + m)


def samples(c):
    lo, hi = c["lb"].min(), c["lb"].max()
    out = []
    for b in SAMPLE_MT:
        t = math.log10(b)
        if lo - SNAP_DEC <= t <= hi + SNAP_DEC and not any(abs(math.log10(cb) - t) <= 2 * SNAP_DEC for cb in c["clip_mT"]):
            out.append(b)
    return out


def point(freq, b_tesla, temp, w_per_m3):
    return {"magneticFluxDensity": {"frequency": float(freq), "magneticFluxDensity": {"processed": {
                "label": "sinusoidal", "peak": float(b_tesla), "offset": 0.0}}},
            "temperature": float(temp), "value": float(w_per_m3), "origin": "manufacturer"}


def check_table(html_path):
    t = open(html_path, encoding="utf-8", errors="replace").read()
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    cells = [c.strip() for c in htmlmod.unescape(re.sub(r"<[^>]+>", "|", t)).split("|") if c.strip()]
    i = cells.index("KL15")
    names = cells[i:i + 7]
    if names != ["KL15", "KL20", "KL40", "KL45", "KL33W", "KL95W", "KL96W"]:
        raise SystemExit(f"table header changed: {names}")
    j = cells.index("Pcv", i)
    rows, k = {}, j
    for T in TABLE_T:
        k = cells.index(f"{T}℃", k)
        rows[T] = [c for c in cells[k + 1:k + 9] if re.fullmatch(r"[\d.]+\*?", c)][:7]
        k += 8
    for m in TABLE:
        col = names.index(m)
        got = [float(rows[T][col].rstrip("*")) for T in TABLE_T]
        if got != [float(v) for v in TABLE[m]]:
            raise SystemExit(f"{m}: page prints {got}, script has {TABLE[m]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--table", required=True, help="saved category page id=21 (cat21.html)")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--debug")
    a = ap.parse_args()
    check_table(a.table)
    pts, report, failed = {}, {}, False
    with tempfile.TemporaryDirectory() as tmp:
        for mat in TABLE:
            rep = report.setdefault(mat, {"pdf": PDF[mat], "charts": [], "table_checks": []})
            table_pts = {(100e3, 0.2, float(T)): v * 1e3 for T, v in zip(TABLE_T, TABLE[mat])}
            got = {}
            for ci, spec in enumerate(CHARTS.get(mat, [])):
                subprocess.run(["pdfimages", "-j", os.path.join(a.pdf_dir, mat + ".pdf"), os.path.join(tmp, mat)], check=True)
                im = np.asarray(Image.open(os.path.join(tmp, f"{mat}-{spec['page']:03d}.jpg")).convert("RGB"))
                tag = f"{mat}_{spec['T']}C"
                try:
                    curves, cal, box = digitize_chart(im, spec, a.debug, tag)
                except RuntimeError as e:
                    rep["charts"].append({"T": spec["T"], "rejected": str(e)}); failed = True
                    print(f"{tag}: REJECTED {e}"); continue
                # physics: loss rises with frequency at every shared B
                fs = sorted(curves)
                for fa, fb in zip(fs, fs[1:]):
                    lo = max(curves[fa]["span_mT"][0], curves[fb]["span_mT"][0])
                    hi = min(curves[fa]["span_mT"][1], curves[fb]["span_mT"][1])
                    for b in np.geomspace(lo, hi, 5) if hi > lo else []:
                        if not read_at(curves[fa], b) < read_at(curves[fb], b):
                            raise SystemExit(f"{tag}: loss at {fa:g} Hz not below {fb:g} Hz at {b:.0f} mT")
                crep = {"T": spec["T"], "x_px_per_decade": round(cal[0][1], 2), "y_px_per_decade": round(cal[1][1], 2),
                        "curves": {}}
                bad_chart = False
                if 100e3 in curves and spec["T"] in TABLE_T:
                    c = curves[100e3]
                    tv = TABLE[mat][TABLE_T.index(spec["T"])]
                    if c["span_mT"][1] >= 200 * 10 ** -SNAP_DEC:
                        v, how = read_at(c, 200), "read"
                        tol = TABLE_TOL
                    else:
                        v, how = extrapolate(c, 200), f"extrapolated from {c['span_mT'][1]:.0f} mT"
                        tol = EXTRAP_TOL
                    ratio = v / tv
                    chk = {"T": spec["T"], "table_kW": tv, "chart_kW": round(v, 1), "ratio": round(ratio, 4), "how": how}
                    rep["table_checks"].append(chk)
                    print(f"{tag}: 100 kHz 200 mT chart {v:.0f} vs table {tv} kW/m3 ratio {ratio:.3f} ({how})")
                    if abs(ratio - 1) > tol:
                        crep["rejected"] = f"table check ratio {ratio:.3f} beyond {tol:.0%}"
                        bad_chart = True; failed = True
                for f, c in curves.items():
                    bs = samples(c)
                    crep["curves"][f"{f / 1e3:g} kHz"] = {"colour": c["colour"], "span_mT": [round(x, 1) for x in c["span_mT"]],
                                                         "trace_rms_pct": round(c["rms_pct"], 2), "line_px": round(c["width_px"], 1),
                                                         "touches_frame_mT": c["clip_mT"][:1] + c["clip_mT"][-1:],
                                                         "samples_mT": bs}
                    if bad_chart:
                        continue
                    for b in bs:
                        got[(f, b / 1e3, float(spec["T"]))] = read_at(c, b) * 1e3   # kW/m3 -> W/m3
                rep["charts"].append(crep)
            dropped = [k for k in got if k in table_pts]
            for k in dropped:
                del got[k]
            allp = [point(f, b, T, v) for (f, b, T), v in sorted(table_pts.items())]
            allp += [point(f, b, T, round(v, -1) if v >= 1e3 else round(v, 1)) for (f, b, T), v in sorted(got.items())]
            rep["points"] = {"table": len(table_pts), "digitized": len(got), "digitized_dropped_at_table_condition": len(dropped)}
            pts[mat] = allp
            print(f"{mat}: {len(table_pts)} table + {len(got)} digitized points")
    json.dump(pts, open(a.json, "w"), indent=1)
    json.dump(report, open(a.report, "w"), indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
