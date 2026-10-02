#!/usr/bin/env python3
"""Digitize the published complex-permeability data of three NiZn grades whose vendors
publish it only as raster charts, and emit/patch the MAS `permeability.complex` block.

    python3 scripts/digitize-raster-permeability.py [--cache DIR] [--patch data/core_materials.ndjson]

Grades and sources (all public, fetched from the vendors' own web sites)
------------------------------------------------------------------------
  DL5H  TAK Technology (takferrite.com), "TAK 2027 NiZn Ferrite Catalog", page 46
        "DL5H Characteristic curves - Complex Permeability (mu', mu'') vs. Frequency":
        https://www.takferrite.com/file_download.php?file=7eed87d97e608caa48178a013461037a.pdf
        mu' and mu'' are both drawn, linear y axis, 10 kHz .. ~500 MHz.
        (The two-page DL5H sheet https://www.takferrite.com/file_download.php?file=e80f3343a777e5eaf46aa99aab86730a.pdf
        carries the same curve at 303x246 px and only to 100 MHz; the catalogue image is
        656x466 px.)
  C5A,  Fengyin / Fongyi Electronics (fengyin.com), per-grade "MAGNETIC PROPERTIES OF
  C6    MATERIAL" sheets:
          http://www.fengyin.com/cn//Editor/PDF/C5A.pdf
          http://www.fengyin.com/cn//Editor/PDF/C6.pdf
        Each publishes "Initial permeability vs Frequency" (mu_i(f), log-log) and
        "Loss factor vs Frequency" (tan(delta)/mu_i, log-log), not mu' and mu'' directly.

From Fengyin's two curves to mu', mu''
--------------------------------------
"Initial permeability vs frequency" is the small-signal inductance of a ring core
normalised to its air value, i.e. the series permeability mu'(f).  The relative loss factor
is tan(delta)/mu_i with tan(delta) = mu''/mu' (IEC 60401-3), both read on the same ring at
the same frequency, so

    mu''(f) = [tan(delta)/mu_i](f) * mu'(f)^2 .

This is a definition, not a model.  mu'' is emitted only where BOTH curves are drawn (on the
loss-factor curve's own pixel columns), so neither curve is extrapolated.  The third curve
on the sheet, "Quality factor vs Frequency", is not used: it rises with frequency at the low
end (C5A 45 -> 100 between 7 kHz and 100 kHz), which is the winding's copper loss of a
component, not the material's tan(delta).

Method
------
The charts are bitmaps, so each axis is calibrated from its own GRIDLINES, never from tick
labels: the gridline pixel positions are detected (dark/gridline-coloured rows/columns
spanning the plot), each is assigned its nominal value (log axes: the 1..9 minors of every
decade; linear: the labelled steps), and a least-squares line pixel->log10(value) (or
->value) is fitted.  The script refuses a chart whose gridlines do not fit that line to
within 1.5 px.  Each curve is then traced column by column on its own colour; a column
whose colour mask breaks into more than one run (a crossing, the legend) is left out
rather than guessed.  The curve end caps (half a line width) are trimmed.  The traced
polyline is resampled on the same 80-points-per-decade grid the ACME digitizer uses
(f = 1 kHz * 10^(k/80)), interpolating linearly in the plotted coordinates.
Nothing is extrapolated and nothing is fitted.

Method validation
-----------------
Run on DL6 (`... DL6`, same catalogue, page 44, y step 50) it reproduces the DL6 table
already in MAS, digitized independently, to 0.4 (mu') / 0.5 (mu'') mean and 3.3 / 2.1 max
absolute units over 10 kHz .. 28 MHz / 518 MHz; the largest difference sits on the steep
mu' plunge.  The Fengyin results reproduce the sheets' own table: C6 tan(delta)/mu_i at
0.5 MHz 74e-6 against the tabulated "<75e-6 at 0.5 MHz".

Usage note: the script refuses to overwrite an existing permeability.complex block.
"""
import argparse
import io
import json
import math
import sys
import urllib.request
from pathlib import Path

try:
    import fitz  # PyMuPDF
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("needs PyMuPDF, numpy and Pillow")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
TAK_CATALOGUE = "https://www.takferrite.com/file_download.php?file=7eed87d97e608caa48178a013461037a.pdf"
FENGYIN = "http://www.fengyin.com/cn//Editor/PDF/{grade}.pdf"
GRID_F0, GRID_PER_DECADE = 1000.0, 80
MAX_GRID_RESIDUAL_PX = 1.5


def fetch(url, cache):
    path = cache / url.rsplit("/", 1)[-1].split("=")[-1]
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return fitz.open(path)


def image(doc, page_index, bbox_pred):
    """The embedded image on the page whose placement bbox satisfies bbox_pred, at native pixels."""
    hits = [i for i in doc[page_index].get_image_info(xrefs=True) if bbox_pred(fitz.Rect(i["bbox"]))]
    if len(hits) != 1:
        raise SystemExit(f"expected one matching image on page {page_index + 1}, found {len(hits)}")
    pix = fitz.Pixmap(doc, hits[0]["xref"])
    if pix.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")).astype(int)


def line_centres(frac, threshold, offset):
    idx = np.where(frac > threshold)[0]
    out = []
    for i in idx:
        if out and i - out[-1][-1] <= 1:
            out[-1].append(i)
        else:
            out.append([i])
    return [offset + float(np.mean(o)) for o in out]


def calibrate(pixels, nominal, what):
    """Least-squares pixel -> coordinate line through the gridlines.  `nominal` is the list of
    coordinates (log10 value, or value) the gridlines are drawn at; every detected line is
    matched to the nearest nominal one under a first guess from the two end lines."""
    pixels = sorted(pixels)
    lo, hi = min(nominal), max(nominal)
    # first guess from the outermost lines (the frame / the end decades)
    a0 = (hi - lo) / (pixels[-1] - pixels[0])
    if a0 == 0:
        raise SystemExit(f"{what}: degenerate gridlines")
    pairs = []
    for p in pixels:
        guess = lo + a0 * (p - pixels[0])
        n = min(nominal, key=lambda v: abs(v - guess))
        pairs.append((p, n))
    P = np.array([p for p, _ in pairs])
    N = np.array([n for _, n in pairs])
    slope, icpt = np.polyfit(P, N, 1)
    res_px = np.abs((N - icpt) / slope - P)
    if res_px.max() > MAX_GRID_RESIDUAL_PX:
        raise SystemExit(f"{what}: gridlines do not fit one axis line (max residual {res_px.max():.2f} px)")
    if len(set(N)) != len(N):
        raise SystemExit(f"{what}: two gridlines matched the same nominal value")
    return slope, icpt, float(res_px.max()), len(pairs)


def log_minors(dec_lo, dec_hi):
    return [d + math.log10(k) for d in range(dec_lo, dec_hi) for k in range(1, 10)] + [dec_hi]


def trace(img, mask, x_range, y_range, cap):
    """Centre row of the curve in every column where the colour mask is ONE run."""
    x0, x1 = x_range
    y0, y1 = y_range
    cols = []
    for x in range(x0, x1 + 1):
        rows = np.where(mask[y0:y1 + 1, x])[0]
        if rows.size == 0:
            continue
        if np.any(np.diff(rows) > 2):
            continue                      # two runs: crossing or legend - not guessed
        cols.append((x, y0 + float(rows.mean())))
    if not cols:
        raise SystemExit("curve not found")
    first, last = cols[0][0], cols[-1][0]
    return [c for c in cols if first + cap <= c[0] <= last - cap]


def resample(f_pts, v_pts, linear_y):
    """f_pts strictly increasing; interpolate in the PLOTTED coordinates (log f, and log or
    linear value) on the 80/decade grid inside the traced span."""
    lf = np.log10(f_pts)
    lv = np.asarray(v_pts) if linear_y else np.log10(v_pts)
    k0 = math.ceil((lf[0] - math.log10(GRID_F0)) * GRID_PER_DECADE - 1e-9)
    k1 = math.floor((lf[-1] - math.log10(GRID_F0)) * GRID_PER_DECADE + 1e-9)
    out = []
    for k in range(k0, k1 + 1):
        x = math.log10(GRID_F0) + k / GRID_PER_DECADE
        y = float(np.interp(x, lf, lv))
        out.append((10 ** x, y if linear_y else 10 ** y))
    return out


# step between the labelled y gridlines (linear axis, 0 at the bottom spine), read off the
# tick labels; the gridline spacing itself is checked to be uniform by calibrate()
TAK_Y_STEP = {"DL5H": 100, "DL6": 50}


def tak(grade, cache):
    doc = fetch(TAK_CATALOGUE, cache)
    page = next(i for i in range(doc.page_count)
                if f"\n{grade}\n" in doc[i].get_text() and "Complex Permeability" in doc[i].get_text())
    # top-right chart of the four on the page
    img = image(doc, page, lambda r: r.x0 > 290 and 80 < r.y0 < 200 and r.width > 150)
    H, W, _ = img.shape
    nonbg = np.abs(img - 245).max(axis=2) > 12
    grid = nonbg & (img[:, :, 1] >= img[:, :, 0]) & (img[:, :, 1] > 150) & (img[:, :, 2] > 120)
    # spines (darker grey-green, full length) bound the axes box
    vcols = line_centres(grid[int(0.1 * H):int(0.8 * H)].mean(axis=0), 0.9, 0)
    # 0.4, not 0.9: a flat curve can hide half of a gridline (DL6's mu' lies on its 300 line)
    hrows = line_centres(grid[:, int(0.2 * W):int(0.9 * W)].mean(axis=1), 0.4, 0)
    xl, xr, yt, yb = vcols[0], vcols[-1], hrows[0], hrows[-1]
    decade_x = vcols[1:-1]                  # major gridlines: 1e-2 .. 1e2 MHz
    if len(decade_x) != 5:
        raise SystemExit(f"{grade}: expected 5 decade gridlines, found {decade_x}")
    # minor x gridlines (lighter) between the majors confirm the log scale
    light = (255 - img.min(axis=2)) > 3          # minor gridlines are only a few levels below white
    minor_x = [c for c in line_centres(light[int(yt) + 5:int(yb) - 5].mean(axis=0), 0.9, 0)
               if decade_x[0] < c < decade_x[-1] and min(abs(c - d) for d in decade_x) > 3]
    xs, xi, xres, xn = calibrate(decade_x + minor_x, log_minors(4, 8), f"{grade} x")   # log10(Hz)
    y_grid = hrows[1:-1] + [yb]             # the labelled gridlines and the 0 spine
    step = TAK_Y_STEP[grade]
    ys, yi, yres, yn = calibrate_desc(y_grid, [step * k for k in range(len(y_grid))], f"{grade} y")
    print(f"{grade}: x {xn} gridlines, max residual {xres:.2f} px; y {yn} gridlines, "
          f"max residual {yres:.2f} px", file=sys.stderr)
    green = (img[:, :, 1] > 100) & (img[:, :, 0] < 80) & (img[:, :, 1] - img[:, :, 2] > 40)
    orange = (img[:, :, 0] > 180) & (img[:, :, 1] > 80) & (img[:, :, 1] < 170) & (img[:, :, 2] < 90)
    # legend box (top right, above the 500 gridline) is outside the traced window
    legend_x = int(decade_x[-1]) + 5
    y_range = (int(hrows[1]) - 25, int(yb) - 1)
    out = {}
    for key, mask in (("real", green), ("imaginary", orange)):
        m = mask.copy()
        m[:int(hrows[1]) + 1, legend_x:] = False
        cols = trace(img, m, (int(xl) + 2, int(xr) - 2), (int(yt) + 2, int(yb) - 1), cap=1)
        f = [10 ** (xi + xs * c[0]) for c in cols]
        v = [yi + ys * c[1] for c in cols]
        out[key] = resample(f, v, linear_y=True)
        print(f"{grade} {key:9}: traced {len(cols)} columns {f[0]:.4g}..{f[-1]:.4g} Hz", file=sys.stderr)
    return out


def calibrate_desc(pixels, nominal, what):
    """calibrate() for an axis whose value grows as the pixel index falls (image y)."""
    s, i, r, n = calibrate([-p for p in pixels], nominal, what)
    return -s, i, r, n


FENGYIN_AXES = {
    # decades of the x axis (log10 Hz) of both upper charts, read off the tick labels and
    # confirmed by the count of detected decade gridlines
    "C5A": (4, 8),   # 0.01 .. 100 MHz
    "C6": (3, 7),    # 0.001 .. 10 MHz
}


def fengyin(grade, cache):
    doc = fetch(FENGYIN.format(grade=grade), cache)
    img = image(doc, 0, lambda r: 230 < r.y0 < 240)     # middle band: loss factor + mu_i charts
    H, W, _ = img.shape
    dark = img.max(axis=2) < 100
    blue = (img[:, :, 2] > 110) & (img[:, :, 0] < 90) & (img[:, :, 2] - img[:, :, 0] > 50)
    dlo, dhi = FENGYIN_AXES[grade]
    charts = {}
    for name, half, (vlo, vhi) in (("lossFactor", (0, W // 2), (-6, -3)), ("mu_i", (W // 2, W), (1, 4))):
        band = dark[:, half[0]:half[1]]
        # the plot area: rows/cols that are dark over most of the frame
        rows_all = line_centres(band.mean(axis=1), 0.6, 0)
        rows = [r for r in rows_all if 100 < r < 700]
        sub = dark[int(rows[0]):int(rows[-1]) + 1, half[0]:half[1]]
        cols = line_centres(sub.mean(axis=0), 0.6, half[0])
        xs, xi, xres, xn = calibrate(cols, log_minors(dlo, dhi), f"{grade} {name} x")
        ys, yi, yres, yn = calibrate_desc(rows, log_minors(vlo, vhi), f"{grade} {name} y")
        print(f"{grade} {name}: x {xn} gridlines (max residual {xres:.2f} px), "
              f"y {yn} gridlines (max residual {yres:.2f} px)", file=sys.stderr)
        tr = trace(img, blue, (int(cols[0]) + 2, int(cols[-1]) - 2), (int(rows[0]) + 2, int(rows[-1]) - 2), cap=2)
        f = np.array([10 ** (xi + xs * c[0]) for c in tr])
        v = np.array([10 ** (yi + ys * c[1]) for c in tr])
        charts[name] = (f, v)
        print(f"{grade} {name}: traced {len(tr)} columns {f[0]:.4g}..{f[-1]:.4g} Hz "
              f"({v[0]:.4g} .. {v[-1]:.4g})", file=sys.stderr)
    fm, mu = charts["mu_i"]
    fl, lf = charts["lossFactor"]
    real = resample(fm, mu, linear_y=False)
    # mu'' on the loss-factor curve's own span, only where mu' is drawn too
    lo, hi = max(fl[0], fm[0]), min(fl[-1], fm[-1])
    lf_grid = [(f, v) for f, v in resample(fl, lf, linear_y=False) if lo <= f <= hi]
    imag = []
    for f, v in lf_grid:
        mu1 = 10 ** float(np.interp(math.log10(f), np.log10(fm), np.log10(mu)))
        imag.append((f, v * mu1 * mu1))
    return {"real": real, "imaginary": imag}


def block(curves):
    return {k: [{"frequency": round(f, 4), "value": round(v, 4)} for f, v in curves[k]]
            for k in ("real", "imaginary")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=Path("."))
    ap.add_argument("--patch", type=Path)
    ap.add_argument("grades", nargs="*", default=["DL5H", "C5A", "C6"])
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    blocks = {}
    for g in args.grades:
        c = fengyin(g, args.cache) if g in FENGYIN_AXES else tak(g, args.cache)
        blocks[g] = block(c)
        for k, t in blocks[g].items():
            print(f"{g} {k:9}: {len(t):4d} pts {t[0]['frequency']:.6g}..{t[-1]['frequency']:.6g} Hz "
                  f"({t[0]['value']:.4g} .. {t[-1]['value']:.4g})", file=sys.stderr)
    if not args.patch:
        print(json.dumps(blocks))
        return
    lines = args.patch.read_text().split("\n")
    hit = {g: 0 for g in blocks}
    for i, line in enumerate(lines):
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("name") in blocks:
            if json.dumps(rec, ensure_ascii=False) != line:
                raise SystemExit(f"{rec['name']}: line does not round-trip; refusing to rewrite")
            if "complex" in rec["permeability"]:
                raise SystemExit(f"{rec['name']}: already has permeability.complex; refusing to overwrite")
            rec["permeability"]["complex"] = blocks[rec["name"]]
            hit[rec["name"]] += 1
            lines[i] = json.dumps(rec, ensure_ascii=False)
    if any(n != 1 for n in hit.values()):
        raise SystemExit(f"expected exactly one record per grade, found {hit}")
    args.patch.write_text("\n".join(lines))
    print(f"patched {', '.join(blocks)} in {args.patch}", file=sys.stderr)


if __name__ == "__main__":
    main()
