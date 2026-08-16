#!/usr/bin/env python3
"""Digitize Fair-Rite's published "Power Loss vs Flux Density" charts (ABT #222).

    python3 scripts/digitize-fair-rite-loss.py 67 77 79 80 95 96 97 98 \
            --cache /tmp/fr-img --json /tmp/fr-points.json

Source
------
Every Fair-Rite material data sheet page embeds its characteristic curves as plain images
under `https://www.fair-rite.com/wp-content/uploads/...`.  Both the page and the images are
served to a normal desktop User-Agent with no cookie/session (an earlier attempt failed only
because it used the apex host `fair-rite.com` and a guessed upload path — the images live on
the `www.` host).  Full-resolution URLs per material are hard-coded in CHARTS below; they
were harvested from the `<material>-material-data-sheet/` pages.

Material 61 needs no digitizing at all: Fair-Rite publishes its loss table outright as
    https://www.fair-rite.com/wp-content/uploads/2016/06/61-Material-B-vs-Pv-at-25C.csv

Method
------
The charts are Excel log-log renders: a black axis box, decade + 2..9 minor gridlines, and
one saturated colour per frequency (material 96 and 79's 500 kHz curve are black).

1. The axis box is found as the outermost rows/columns whose dark-pixel coverage spans the
   plot; the decade limits are declared per chart (read off the printed tick labels).  The
   calibration is then VERIFIED, not assumed: every detected gridline must land within
   `GRID_TOL_PX` of a 1..9 x 10^k position, else the chart is rejected.
2. The grid is removed by dropping every run longer than HRUN in either direction -- a
   horizontal gridline is one long row-run, a vertical one a long column-run, while these
   curves climb at ~1:1 to 3:1 and are never that flat or that upright.  The legend is read
   for its key colours (and its own box excluded), small blobs are dropped as text/ringing.
3. Curves are traced left to right by a predictive tracker that requires BOTH the geometric
   prediction AND the colour to match.  Neither alone suffices: colour because JPEG washes
   thin lines out (a black curve renders mid-grey) and some palettes carry two close hues,
   geometry because curves start and end near each other.
4. A traced curve is labelled by matching its median colour to the legend keys in an opponent
   colour space, merging same-coloured fragments that lie on the same drawn line.  The result
   is then cross-checked against physics: loss is strictly increasing in frequency at fixed B,
   so ordering the curves by loss must reproduce the legend order.  A chart where the two
   signals disagree is REJECTED rather than guessed at.
5. Accuracy is self-reported per curve.  The scatter of the trace about a quadratic log-log
   fit is the digitizing noise (the straight-line residual also carries the curve's own real
   curvature); a curve scattering more than MAX_TRACE_RMS_PCT is refused.  Points are emitted
   on the vendor's own drawn span only -- nothing is extrapolated.

Output is a JSON dict {material: {"points": [...], "accuracy": [...]}} where each point is a
MAS `volumetricLosses` datum (SI: T, Hz, W/m^3, degC, origin=manufacturer).
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/151.0.0.0 Safari/537.36")
BASE = "https://www.fair-rite.com/wp-content/uploads/"

CHROMA = 15          # min (max-min) channel spread for a pixel to count as a curve colour
GRID_TOL_PX = 3.0    # max gridline mismatch allowed by the calibration check
HRUN = 12            # horizontal run length (px) above which pixels are legend/gridline
SWATCH_LO, SWATCH_HI = 12, 80   # legend key line length, px
COLOUR_TOL = 130     # max RGB distance from a legend colour for a pixel to join that curve
COLOUR_MARGIN = 0.6  # and it must be this much closer to that colour than to any other
LEG_PAD_X, LEG_PAD_Y, LEG_TEXT_X = 45, 22, 150   # legend exclusion box around the keys
EDGE = 4             # px of the image border ignored when hunting for the axis frame
TRACK_GAP = 25       # px a curve may vanish for (gridline crossings) before its track dies
TRACK_TOL = 9        # px a run may sit off the track's prediction and still be the same curve
MIN_TRACK = 60       # samples a track needs before it counts as a drawn curve
TRACK_DRIFT = 0.5    # extra px of tolerance per px of gap while a curve is hidden
STITCH_GAP, STITCH_TOL, STITCH_SLOPE = 70, 12, 0.6   # re-joining fragments of one curve
BLOB_MIN_H, BLOB_MIN_W = 40, 60   # bbox a monochrome blob must fill to count as a curve
MAX_TRACE_RMS_PCT = 5.0   # a curve whose trace scatters more than this is not shipped
OPPONENT_TOL = 55    # max opponent-space distance from a legend key for a track to be its curve
FRAGMENT_TOL = 8     # px a fragment may sit off the curve it is being appended to
TRIM_SIGMA, TRIM_FLOOR = 3.0, 0.006   # outlier trim: 3 sigma, or 1.4% in loss, whichever is larger

# x/y are the printed decade limits (gauss, mW/cm^3); freqs ascend, one per plotted curve.
CHARTS = {
    "67": [
        dict(url="2020/06/67PLvB25.jpg", T=25.0, x=(10, 1000), y=(10, 1000),
             freqs=[2e6, 5e6, 10e6, 15e6, 20e6]),
        dict(url="2020/06/67PLB100.jpg", T=100.0, x=(10, 1000), y=(10, 1000),
             freqs=[2e6, 5e6, 10e6, 15e6, 20e6]),
    ],
    "77": [
        dict(url="2020/06/77PLvsFlux25.jpg", T=25.0, x=(100, 10000), y=(1, 1000),
             freqs=[10e3, 25e3, 50e3, 100e3, 200e3, 400e3]),
        dict(url="2020/06/77PLvsFlux100.jpg", T=100.0, x=(100, 10000), y=(1, 1000),
             freqs=[10e3, 25e3, 50e3, 100e3, 200e3, 400e3]),
    ],
    "79": [
        dict(url="2020/06/79PLvB25.jpg", T=25.0, x=(10, 10000), y=(1, 1000),
             freqs=[100e3, 300e3, 500e3, 750e3, 1e6], black=500e3),
        dict(url="2020/06/79PLvB100.jpg", T=100.0, x=(10, 10000), y=(1, 1000),
             freqs=[100e3, 300e3, 500e3, 750e3, 1e6], black=500e3),
    ],
    "80": [
        dict(url="2020/06/80PLvB25.jpg", T=25.0, x=(10, 1000), y=(1, 1000),
             freqs=[1e6, 2e6, 3e6, 4e6]),
        dict(url="2020/06/80PLvB100.jpg", T=100.0, x=(10, 1000), y=(1, 1000),
             freqs=[1e6, 2e6, 3e6, 4e6]),
    ],
    "95": [
        dict(url="2020/06/95_PL25.jpg", T=25.0, x=(100, 10000), y=(1, 1000),
             freqs=[25e3, 50e3, 100e3, 200e3, 300e3, 500e3]),
        dict(url="2020/06/95pl100.jpg", T=100.0, x=(100, 10000), y=(1, 1000),
             freqs=[25e3, 50e3, 100e3, 200e3, 300e3, 500e3]),
    ],
    # Material 96 is deliberately absent.  Its PL-vs-B charts
    # (2024/08/96-PowerLossVsFluxDensity{25C,100C,140C}.png) are 632x366 monochrome renders
    # with the frequency labels printed INSIDE the plot: no colour to tell the four curves
    # apart, curve blobs that merge where they pass close, and text blobs the size of a curve
    # segment.  Every separation attempt left curves cross-contaminated (residuals 20-60 %),
    # so 96 is left without measured points rather than backed by unreliable ones.
    "97": [
        dict(url="2020/06/97PLvB.jpg", T=100.0, x=(100, 10000), y=(1, 10000),
             freqs=[50e3, 100e3, 200e3, 400e3]),
    ],
    "98": [
        dict(url="2020/06/98PLvsF100.jpg", T=100.0, x=(100, 10000), y=(1, 1000),
             freqs=[25e3, 50e3, 100e3, 200e3]),
    ],
}
# material 96's PNGs sit on the apex host (they are newer uploads); everything else on www.
APEX = ("2024/08/",)


def fetch(url_tail, cache):
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, os.path.basename(url_tail))
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    host = "https://fair-rite.com/wp-content/uploads/" if url_tail.startswith(APEX) else BASE
    subprocess.run(["curl", "-sS", "--max-time", "90", "-A", UA, "-o", dest, host + url_tail],
                   check=True)
    if os.path.getsize(dest) < 1000:
        raise RuntimeError(f"download of {url_tail} produced {os.path.getsize(dest)} bytes")
    return dest


def find_box(dark):
    """Outermost rows/cols whose dark coverage spans the plot -> the axis rectangle.

    Rows/cols within EDGE px of the image boundary are ignored: some of these figures are
    exported with a border around the whole picture, which is not the axis frame (it is what
    threw the y calibration on 95's charts off by 27 px)."""
    h, w = dark.shape
    rows = [y for y in range(EDGE, h - EDGE) if dark[y].sum() > 0.6 * w]
    cols = [x for x in range(EDGE, w - EDGE) if dark[:, x].sum() > 0.6 * h]
    if not rows or not cols:
        raise RuntimeError("no axis box found")
    return rows[0], rows[-1], cols[0], cols[-1], rows, cols


def check_grid(pos, value_of, px_per_decade, tol, axis):
    """Every detected gridline must sit on a 1..9 x 10^k tick of the declared decade span."""
    worst = 0.0
    for p in pos:
        v = value_of(p)
        frac = v - math.floor(v)
        best = min(abs(frac - math.log10(d)) for d in range(1, 11))
        worst = max(worst, best * px_per_decade)
    if worst > tol:
        raise RuntimeError(f"{axis} calibration check failed: gridline off by {worst:.1f} px")
    return worst


def strip_grid(mask, run):
    """Drop pixels on any run longer than `run` in EITHER direction.

    That is exactly the grid: a horizontal gridline is one long row-run, a vertical gridline
    one long column-run, a legend key one short-ish row-run.  These curves climb at roughly
    1:1 to 2:1 in pixels, so no curve segment is ever more than a few px flat or upright, and
    removing whole rows/cols with padding (the obvious alternative) chops the curve into
    fragments too short to survive blob filtering."""
    return strip_runs(strip_runs(mask, run).T, run).T


def strip_runs(mask, run):
    """Drop pixels that belong to a horizontal run longer than `run` (legend swatches,
    gridline remnants).  Curve segments on these plots are never that flat."""
    out = mask.copy()
    h, w = mask.shape
    for y in range(h):
        xs = np.flatnonzero(mask[y])
        if xs.size == 0:
            continue
        brk = np.flatnonzero(np.diff(xs) != 1)
        starts = np.r_[0, brk + 1]
        ends = np.r_[brk, xs.size - 1]
        for s, e in zip(starts, ends):
            if xs[e] - xs[s] + 1 > run:
                out[y, xs[s]:xs[e] + 1] = False
    return out


def legend_swatches(im, box, nfreq):
    """The legend key: nfreq horizontal single-colour runs sharing one x span.

    Reading the key instead of guessing a palette gives (a) the exact reference colour of
    every curve and (b) the legend's own top-to-bottom order, which on every Fair-Rite loss
    chart is the printed frequency order.  Requiring all keys to share the same x span is
    what separates them from bold decade gridlines chopped into segments by the curves.
    """
    r0, r1, c0, c1 = box
    ink = (im.max(2) - im.min(2)) > CHROMA
    ink |= im.max(2) < 110                       # black keys (e.g. 79's 500 kHz)
    runs = []
    for y in range(r0 + 1, r1):
        xs = np.flatnonzero(ink[y, c0:c1 + 1]) + c0
        if xs.size == 0:
            continue
        brk = np.flatnonzero(np.diff(xs) != 1)
        for s, e in zip(np.r_[0, brk + 1], np.r_[brk, xs.size - 1]):
            n = xs[e] - xs[s] + 1
            if SWATCH_LO <= n <= SWATCH_HI:
                runs.append((y, int(xs[s]), int(xs[e]), im[y, xs[s]:xs[e] + 1]))
    # group runs that share an x span (same midpoint and length, +-a few px of antialiasing);
    # the legend is the span that holds exactly nfreq vertically separated keys
    groups = []
    for y, xa, xb, seg in sorted(runs, key=lambda r: (r[1] + r[2]) / 2):
        mid, ln = (xa + xb) / 2, xb - xa + 1
        for g in groups:
            if abs(mid - g["mid"]) <= 8 and abs(ln - g["len"]) <= 16:
                g["items"].append((y, xa, xb, seg))
                g["mid"] = (g["mid"] * (len(g["items"]) - 1) + mid) / len(g["items"])
                break
        else:
            groups.append(dict(mid=mid, len=ln, items=[(y, xa, xb, seg)]))
    cands = []
    for g in groups:
        clusters = []
        for it in sorted(g["items"], key=lambda t: t[0]):
            if clusters and it[0] - clusters[-1][-1][0] <= 4:
                clusters[-1].append(it)
            else:
                clusters.append([it])
        if len(clusters) == nfreq:
            cands.append((len(g["items"]), clusters))
    if not cands:
        raise RuntimeError(f"no legend x span with {nfreq} keys")
    cands.sort(key=lambda c: -c[0])
    keys = [key_colour(cl) for cl in cands[0][1]]
    ys = [it[0] for cl in cands[0][1] for it in cl]
    xa = min(it[1] for cl in cands[0][1] for it in cl)
    xb = max(it[2] for cl in cands[0][1] for it in cl)
    # the legend's own drawing (keys, box border, text) must never be mistaken for a curve
    bbox = (min(ys) - LEG_PAD_Y, max(ys) + LEG_PAD_Y, xa - LEG_PAD_X, xb + LEG_TEXT_X)
    return keys, bbox


def key_colour(cluster):
    """Reference colour of one legend key: the median over its most saturated pixels (the
    core of the drawn line), so anti-aliased edge rows cannot wash the reference out.  A key
    with no saturated pixel at all is a black key."""
    px = np.vstack([it[3] for it in cluster]).astype(float)
    chroma = px.max(1) - px.min(1)
    if chroma.max() < CHROMA:
        return np.median(px[px.max(1) <= np.percentile(px.max(1), 25)], 0)
    return np.median(px[chroma >= 0.8 * chroma.max()], 0)


def despeckle(mask, min_blob=90):
    """Drop small ink blobs: the in-plot text labels of the monochrome charts, tick text that
    pokes inside the frame, and JPEG ringing.  A drawn curve is hundreds of pixels long."""
    bridged = ndimage.binary_closing(mask, structure=np.ones((7, 7), bool))
    lab, n = ndimage.label(bridged, structure=np.ones((3, 3), bool))
    if n == 0:
        return mask
    sizes = ndimage.sum_labels(mask, lab, index=np.arange(1, n + 1))
    return mask & np.isin(lab, np.flatnonzero(sizes >= min_blob) + 1)


def denoise(ys, xs, shape, min_blob=60):
    """Keep only pixels belonging to a sizeable connected blob.

    JPEG ringing around the black gridlines and axis text throws off coloured specks all over
    these charts; unfiltered they poison a column's median by tens of pixels.  A real curve is
    one long 8-connected component, a ringing speck is a handful of pixels."""
    m = np.zeros(shape, bool)
    m[ys, xs] = True
    # close first: a curve is cut into pieces wherever it crosses a gridline or another curve
    bridged = ndimage.binary_closing(m, structure=np.ones((7, 7), bool))
    lab, n = ndimage.label(bridged, structure=np.ones((3, 3), bool))
    sizes = ndimage.sum_labels(m, lab, index=np.arange(1, n + 1))
    keep = np.flatnonzero(sizes >= min_blob) + 1
    m &= np.isin(lab, keep)
    return np.nonzero(m)


def column_trace(ys, xs, x0, x1):
    """One (col, row) sample per pixel column: the median row of the column's LONGEST run of
    pixels, so a stray blob elsewhere in the column cannot drag the sample off the curve."""
    out = []
    order = np.argsort(xs)
    ys, xs = ys[order], xs[order]
    edges = np.searchsorted(xs, np.arange(x0, x1 + 2))
    for i, x in enumerate(range(x0, x1 + 1)):
        sel = np.sort(ys[edges[i]:edges[i + 1]])
        if sel.size == 0:
            continue
        brk = np.flatnonzero(np.diff(sel) > 3)
        starts = np.r_[0, brk + 1]
        ends = np.r_[brk + 1, sel.size]
        s, e = max(zip(starts, ends), key=lambda se: se[1] - se[0])
        out.append((x, float(np.median(sel[s:e]))))
    return out


def to_values(trace, spec, box):
    r0, r1, c0, c1 = box
    xdec = math.log10(spec["x"][1]) - math.log10(spec["x"][0])
    ydec = math.log10(spec["y"][1]) - math.log10(spec["y"][0])
    pts = []
    for x, y in trace:
        b = 10 ** (math.log10(spec["x"][0]) + (x - c0) / (c1 - c0) * xdec)
        p = 10 ** (math.log10(spec["y"][1]) - (y - r0) / (r1 - r0) * ydec)
        pts.append((b, p))
    return pts


def powerlaw_residual(pts):
    """beta/k of the power law the curve follows, plus two residual measures.

    The straight-line residual mixes tracing noise with the curve's own (small) real
    curvature; the quadratic residual isolates the tracing noise, which is the digitizing
    accuracy we actually want to report and gate on."""
    lb = np.log10([p[0] for p in pts])
    lp = np.log10([p[1] for p in pts])
    beta, k = np.polyfit(lb, lp, 1)
    lin = lp - (beta * lb + k)
    quad = lp - np.polyval(np.polyfit(lb, lp, 2), lb)
    return (beta, 10 ** k, float(np.max(np.abs(lin))), float(np.sqrt((lin ** 2).mean())),
            float(np.max(np.abs(quad))), float(np.sqrt((quad ** 2).mean())))


def trim_outliers(pts):
    """Drop the handful of columns where the trace jumped.

    Where a curve crosses a bold gridline or another curve, its column run is briefly wrong
    and the sample sits several px off the drawn line.  Those columns are removed against a
    quadratic log-log fit before any point is emitted -- they are tracing artefacts, not
    features of the vendor's curve, and one of them would otherwise be picked as an emitted
    sample."""
    lb = np.log10([p[0] for p in pts])
    lp = np.log10([p[1] for p in pts])
    res = np.abs(lp - np.polyval(np.polyfit(lb, lp, 2), lb))
    keep = res <= max(TRIM_FLOOR, TRIM_SIGMA * np.sqrt((res ** 2).mean()))
    if keep.sum() < 0.7 * len(pts):
        raise RuntimeError(f"trace is {100 * (1 - keep.mean()):.0f}% outliers, not a clean curve")
    return [pt for pt, k in zip(pts, keep) if k]


def sample(pts, n=6):
    """n log-spaced samples strictly inside the drawn span of the curve."""
    lb = np.log10([p[0] for p in pts])
    lo, hi = lb.min(), lb.max()
    targets = np.linspace(lo, hi, n)
    out = []
    for t in targets:
        i = int(np.argmin(np.abs(lb - t)))
        out.append(pts[i])
    return out


def digitize(path, spec):
    im = np.array(Image.open(path).convert("RGB")).astype(np.int16)
    h, w, _ = im.shape
    dark = im.max(2) < 200
    r0, r1, c0, c1, rows, cols = find_box(dark)
    xdec = math.log10(spec["x"][1]) - math.log10(spec["x"][0])
    ydec = math.log10(spec["y"][1]) - math.log10(spec["y"][0])
    gx = check_grid([c for c in cols if c0 <= c <= c1],
                    lambda c: math.log10(spec["x"][0]) + (c - c0) / (c1 - c0) * xdec,
                    (c1 - c0) / xdec, GRID_TOL_PX, "x")
    gy = check_grid([r for r in rows if r0 <= r <= r1],
                    lambda r: math.log10(spec["y"][1]) - (r - r0) / (r1 - r0) * ydec,
                    (r1 - r0) / ydec, GRID_TOL_PX, "y")

    inner = np.zeros((h, w), bool)
    inner[r0 + 2:r1 - 1, c0 + 2:c1 - 1] = True
    chroma = (im.max(2) - im.min(2)) > CHROMA
    freqs = list(spec["freqs"])
    curves = {}

    if spec.get("mono"):
        # Every curve is the same black, so colour cannot separate them -- but on these charts
        # the curves never touch, so each is simply one connected blob of ink once the grid and
        # the in-plot text are gone.  Taking components (rather than tracking) is exact here.
        mask = despeckle(strip_grid(dark & inner & ~chroma, HRUN))
        blobs = ndimage.label(ndimage.binary_closing(mask, np.ones((7, 7), bool)),
                              structure=np.ones((3, 3), bool))[0] * mask
        sizes = np.bincount(blobs.ravel())[1:]
        cand = []
        for lb in np.argsort(sizes)[::-1] + 1:
            if sizes[lb - 1] < MIN_TRACK:
                break
            cy, cx = np.nonzero(blobs == lb)
            # a drawn curve climbs across the plot; the in-plot "500kHz" annotations are wide
            # but only a dozen px tall, so a height floor separates them cleanly
            if cy.max() - cy.min() < BLOB_MIN_H or cx.max() - cx.min() < BLOB_MIN_W:
                continue
            cand.append(column_trace(cy, cx, cx.min(), cx.max()))
        if len(cand) != len(freqs):
            raise RuntimeError(f"monochrome chart yielded {len(cand)} curve blobs, "
                               f"expected {len(freqs)}")
        traces = cand
        # a monochrome chart offers nothing but geometry: the lossiest curve is the fastest
        traces.sort(key=lambda t: np.mean([y for _, y in t]))
        for rank, tr in enumerate(traces):
            curves[sorted(freqs, reverse=True)[rank]] = tr
        return curves, (r0, r1, c0, c1), max(gx, gy), spec

    keys, (ly0, ly1, lx0, lx1) = legend_swatches(im, (r0, r1, c0, c1), len(freqs))
    ref = np.array(keys, dtype=float)                      # legend order = freqs order
    inner[max(r0, ly0):min(r1, ly1) + 1, max(c0, lx0):min(c1, lx1) + 1] = False
    has_black_key = bool((ref.max(1) < 110).any())
    cand = chroma if not has_black_key else (chroma | (dark & inner))
    mask = despeckle(strip_grid(cand & inner, HRUN))

    # Trace with geometry AND colour together (see track_curves), then attach the finished
    # curves to the legend keys as a one-to-one assignment on their median colour.  Matching
    # whole curves rather than single pixels is what makes the labelling robust: a curve's
    # median colour is stable even where JPEG has washed individual pixels out.
    tracks = track_curves(im, mask, len(freqs), keep_all=True)
    tcol = np.array([np.median(np.array([c for _, _, c in tr]), 0) for tr in tracks])
    cost = ((opponent(tcol)[:, None, :] - opponent(ref)[None]) ** 2).sum(2)
    owner = np.argmin(cost, axis=1)
    plain, by_colour = [], {}
    for i, f in enumerate(freqs):
        mine = sorted((t for t in range(len(tracks))
                       if owner[t] == i and cost[t, i] <= OPPONENT_TOL ** 2),
                      key=lambda t: -len(tracks[t]))
        if not mine:
            raise RuntimeError(f"no traced curve carries the legend colour of {f/1e3:.0f} kHz")
        merged = {}
        for x, y, _ in tracks[mine[0]]:
            merged.setdefault(x, []).append(y)
        # A curve can be traced as several fragments, all in its own colour.  Take the longest
        # as the curve and admit another fragment only if it lies on the same drawn line --
        # that is what keeps a same-coloured stray (an artefact, or a second curve of a near
        # hue) from being glued onto a genuine trace.
        for t in mine[1:]:
            xs = np.array(sorted(merged))
            ys = np.array([np.median(merged[x]) for x in xs])
            fit = np.polyfit(xs, ys, 1)
            fx = np.array([p[0] for p in tracks[t]])
            fy = np.array([p[1] for p in tracks[t]])
            if np.median(np.abs(np.polyval(fit, fx) - fy)) > FRAGMENT_TOL:
                continue
            for x, y, _ in tracks[t]:
                merged.setdefault(x, []).append(y)
        by_colour[f] = len(plain)
        plain.append([(x, float(np.median(merged[x]))) for x in sorted(merged)])

    # Cross-check the colour labelling against physics: within one chart (one material, one
    # temperature) loss is strictly increasing in frequency at every flux density, so ordering
    # the curves by their loss at a shared B must reproduce the frequency order.  If the two
    # disagree, either a curve was mis-traced or the legend was mis-read -- in neither case
    # are the points trustworthy, so refuse them rather than guess which signal to believe.
    by_loss = {sorted(freqs)[rank]: t
               for rank, t in enumerate(order_by_loss(plain, (r0, r1, c0, c1), spec))}
    for f in freqs:
        if by_colour[f] != by_loss[f]:
            raise RuntimeError(f"legend colour and loss ordering disagree at {f/1e3:.0f} kHz")
    for f, t in by_colour.items():
        curves[f] = plain[t]
    return curves, (r0, r1, c0, c1), max(gx, gy), spec


def opponent(rgb):
    """Colour in an opponent space (R-G, G-B, dimmed luminance).

    Curve identity lives in the chromatic channels: JPEG renders a 1 px black curve as mid
    grey, which in plain RGB sits closer to a dark purple key than to the black key it
    belongs to, but in this space grey and black are neighbours and purple is not."""
    rgb = np.atleast_2d(np.asarray(rgb, dtype=float))
    return np.stack([rgb[:, 0] - rgb[:, 1], rgb[:, 1] - rgb[:, 2], rgb.mean(1) * 0.25], 1)


def order_by_loss(traces, box, spec):
    """Indices of the traces sorted by the loss each one carries at a shared flux density."""
    vals = []
    for tr in traces:
        pts = to_values(tr, spec, box)
        lb = np.log10([p[0] for p in pts])
        lp = np.log10([p[1] for p in pts])
        vals.append((np.polyfit(lb, lp, 1), lb.min(), lb.max()))
    lo = max(v[1] for v in vals)
    hi = min(v[2] for v in vals)
    at = (lo + hi) / 2 if lo < hi else np.mean([(v[1] + v[2]) / 2 for v in vals])
    return sorted(range(len(traces)), key=lambda i: np.polyval(vals[i][0], at))


def track_curves(im, mask, k, mono=False, keep_all=False):
    """Follow each drawn curve left to right through the stripped mask.

    With the grid and the legend removed, every column holds one short vertical run per curve
    passing through it.  A run joins the track whose extrapolation it lands on AND whose
    colour it shares.  Geometry alone confuses neighbouring curves where one ends and another
    begins nearby; colour alone is unreliable because JPEG washes thin lines out and some of
    these palettes put two close hues on one chart.  Together they are decisive -- and on the
    monochrome material 96 charts the colour term simply drops out."""
    h, w = mask.shape
    tracks = []
    for x in range(w):
        ys = np.flatnonzero(mask[:, x])
        if ys.size == 0:
            continue
        brk = np.flatnonzero(np.diff(ys) > 3)
        for s, e in zip(np.r_[0, brk + 1], np.r_[brk + 1, ys.size]):
            run = ys[s:e]
            yv = float(np.median(run))
            seg = im[run, x].astype(float)
            col = seg[int(np.argmax(seg.max(1) - seg.min(1)))]   # core, not the halo
            best, bestd = None, 1e9
            for t in tracks:
                dx = x - t["lx"]
                if dx <= 0 or dx > TRACK_GAP:
                    continue
                if not mono and ((t["col"] - col) ** 2).sum() > COLOUR_TOL ** 2:
                    continue
                d = abs(t["ly"] + t["slope"] * dx - yv) / (TRACK_TOL + TRACK_DRIFT * dx)
                if d < bestd:
                    best, bestd = t, d
            if best is not None and bestd < 1.0:
                dx = x - best["lx"]
                w_ = 1.0 / min(len(best["pts"]) + 1, 40)
                best["slope"] = (1 - 0.2) * best["slope"] + 0.2 * (yv - best["ly"]) / dx \
                    if len(best["pts"]) >= 3 else (yv - best["ly"]) / dx
                best["col"] = (1 - w_) * best["col"] + w_ * col
                best["lx"], best["ly"] = x, yv
                best["pts"].append((x, yv, col))
            else:
                tracks.append(dict(lx=x, ly=yv, slope=-1.0, col=col, pts=[(x, yv, col)]))
    tracks = stitch(tracks, mono)
    tracks = [t for t in tracks if len(t["pts"]) >= MIN_TRACK]
    tracks.sort(key=lambda t: -len(t["pts"]))
    if len(tracks) < k:
        raise RuntimeError(f"curve tracker found {len(tracks)} curves, expected {k}")
    return [sorted(t["pts"]) for t in (tracks if keep_all else tracks[:k])]


def stitch(tracks, mono):
    """Re-join track fragments that are the same drawn curve.

    A curve can still be dropped for longer than TRACK_GAP where it runs along a bold decade
    gridline.  Two fragments belong together when the earlier one, extrapolated along the
    slope it was carrying, lands on the start of the later one -- in the same colour."""
    tracks = sorted(tracks, key=lambda t: t["pts"][0][0])
    out = []
    for t in tracks:
        x0, y0 = t["pts"][0][0], t["pts"][0][1]
        j = min(4, len(t["pts"]) - 1)
        s0 = (t["pts"][j][1] - y0) / max(1, t["pts"][j][0] - x0)
        for u in out:
            gap = x0 - u["lx"]
            if not (0 < gap <= STITCH_GAP):
                continue
            if abs(u["ly"] + u["slope"] * gap - y0) > STITCH_TOL:
                continue
            if abs(u["slope"] - s0) > STITCH_SLOPE:
                continue
            if not mono and ((u["col"] - t["col"]) ** 2).sum() > COLOUR_TOL ** 2:
                continue
            u["pts"].extend(t["pts"])
            u["lx"], u["ly"] = t["lx"], t["ly"]
            u["slope"], u["col"] = t["slope"], t["col"]
            break
        else:
            out.append(t)
    return out


def point(freq, b_tesla, temp, w_per_m3):
    return {
        "magneticFluxDensity": {
            "frequency": float(freq),
            "magneticFluxDensity": {"processed": {
                "label": "sinusoidal", "peak": float(b_tesla), "offset": 0.0}},
        },
        "temperature": float(temp),
        "value": float(w_per_m3),
        "origin": "manufacturer",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("materials", nargs="+")
    ap.add_argument("--cache", default="fr-img")
    ap.add_argument("--json", default=None)
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()

    result = {}
    for mat in args.materials:
        if mat not in CHARTS:
            sys.exit(f"no chart declared for material {mat}")
        pts, acc = [], []
        for spec in CHARTS[mat]:
            path = fetch(spec["url"], args.cache)
            curves, box, griderr, spec = digitize(path, spec)
            for f in sorted(curves):
                vals = trim_outliers(to_values(curves[f], spec, box))
                beta, k, mx, rms, qmx, qrms = powerlaw_residual(vals)
                if (10 ** qrms - 1) * 100 > MAX_TRACE_RMS_PCT:
                    raise RuntimeError(
                        f"{os.path.basename(spec['url'])} {f/1e3:.0f} kHz: trace scatter "
                        f"{(10 ** qrms - 1) * 100:.1f}% exceeds the {MAX_TRACE_RMS_PCT}% gate")
                acc.append(dict(chart=os.path.basename(spec["url"]), T=spec["T"], f=f,
                                beta=round(beta, 3), k=round(k, 6),
                                max_dev_pct=round((10 ** mx - 1) * 100, 2),
                                rms_dev_pct=round((10 ** rms - 1) * 100, 2),
                                trace_rms_pct=round((10 ** qrms - 1) * 100, 2),
                                trace_max_pct=round((10 ** qmx - 1) * 100, 2),
                                grid_px=round(griderr, 2),
                                span_gauss=[round(vals[0][0], 1), round(vals[-1][0], 1)]))
                for b, p in sample(vals, args.samples):
                    pts.append(point(f, b * 1e-4, spec["T"], p * 1e3))
        result[mat] = dict(points=pts, accuracy=acc)
        print(f"== {mat}: {len(pts)} points from {len(CHARTS[mat])} charts")
        for a in acc:
            print(f"   {a['chart']:32s} {a['T']:5.0f}C {a['f']/1e3:8.0f} kHz  "
                  f"beta={a['beta']:5.3f} scatter={a['trace_rms_pct']:5.2f}%rms/"
                  f"{a['trace_max_pct']:5.2f}%max  line-rms={a['rms_dev_pct']:5.2f}%  "
                  f"grid={a['grid_px']}px  B={a['span_gauss']}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=1)
        print("wrote", args.json)


if __name__ == "__main__":
    main()
