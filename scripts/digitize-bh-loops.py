#!/usr/bin/env python3
"""Major B-H loops of ferrites from their manufacturers' data sheets, written as the material's `bhCycle`.

WHY
    A consumer that needs the material's DC magnetisation B(H) (the load line of a DC-biased core) takes it from the
    loop, e.g. its midline (mean of the rising and falling branch at each B). Integrating the small-signal
    permeability.initial instead leaves out the irreversible wall motion: on an ungapped 3C90 at 15 A/m it gives
    0.042 T where the data sheet loop's midline is at 0.17 T.

WHAT IS WRITTEN (schema unchanged: bhCycle is an array of {magneticFluxDensity, magneticField, temperature})
    Per temperature the figure draws, the loop as drawn, as ONE ordered traversal:
      the rising (ascending) branch from its lowest resolved B up to the loop tip (the point of largest H drawn),
      then the falling (descending) branch from the tip back down to its lowest resolved B.
    So within one temperature H rises to the tip and then falls, and B does the same; the tip is the split point.
    Only the part where BOTH branches are drawn is written: from the lowest B at which both are resolved (the figures
    draw the upper half, B >= 0; the falling branch's tail below that B, down to -Hc, is not written). Where the
    two branches are drawn as one line (the closed part near the tip), both branches carry the same points.
    Points are the figure's own: crossings of the drawn curve with a fine grid of B rows and H columns, each branch
    kept monotone (a crossing that would make its branch go back is dropped), then thinned by Ramer-Douglas-Peucker
    to THIN_TOL of the axis spans. Nothing is fitted or smoothed.

ACCEPTANCE (else that temperature is refused and nothing is written for it)
    - both branches resolved down to B <= LOOP_MIN_B;
    - the midline (mean of the branches' H at each B) at the lowest common B lies within LOOP_CENTRE_TOL of Hc from
      H = 0, Hc being the record's coercive field at that temperature (within 5 C); a record without one is
      checked against the loop's own half-width at that B instead (stated in the provenance);
    - the midline H(B) rises strictly with B (a consumer inverts it to B(H)).

READERS
    TDK ("Dynamic magnetization curves (typical values) (f = 10 kHz, T = 25 / 100 C)", one panel per temperature):
      vector paths; axes on the panel's evenly spaced gridlines, values from the tick labels matched to gridlines
      (at least 3 per axis, collinear within 1 % of the span); panels whose labels are drawn as outlines take the
      printed end values from TDK_LOOP_AXES (read off the rendered page), checked against the evenly spaced grid.
    Ferroxcube ("Typical B-H loops", 25 and 100 C in one figure): vector paths; the H axis is broken (linear to
      50 A/m, compressed above): calibrated piecewise-linearly on its tick labels; the 25 C curve is the thicker
      stroke (legend). ABOVE THE BREAK THE CALIBRATION IS ONLY AS GOOD AS LINEAR BETWEEN LABELS (the gridlines
      there are not evenly spaced), so H above 50 A/m carries a few A/m of uncertainty; stated in the provenance.
    Magnetics ("TYPICAL B-H LOOPS", 2025 Ferrite Catalog, 25 and 100 C): as Ferroxcube; lighter stroke = 25 C.
    Fair-Rite ("<grade> Material Hysteresis Loop" raster images on the material pages): black = 25 C, blue =
      100 C (the image labels), axes from the gridlines and the printed axis range (FAIRRITE_LOOP_AXES), H in
      oersted converted to A/m. Raster: crossings are centres of pixel runs.
    DMEGC loops are not read: their H axis starts at 0, so the falling branch below B_r is not drawn and both
    branches are resolved only above B_r (fails LOOP_MIN_B).

PATCHING
    As digitize-reversible-permeability.py: only the one ferrite record of that grade and maker; its provenance
    entry for bhCycle is replaced; manufacturerInfo.datasheetUrl is set only when absent.

Usage:
    python3 scripts/digitize-bh-loops.py --cache DIR [--patch data/core_materials.ndjson] [GRADE ...]
"""
import bisect
import argparse
import collections
import datetime
import importlib.util
import json
import os
import re

import numpy as np
import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('rev', os.path.join(HERE, 'digitize-reversible-permeability.py'))
rev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rev)
Refused = rev.Refused

OERSTED = 1000 / (4 * np.pi)
LOOP_MIN_B = 0.06         # T
LOOP_CENTRE_TOL = 0.25    # fraction of Hc
THIN_TOL = 0.002          # fraction of the axis spans
LABEL_TOL = 0.01          # tick labels collinear within this fraction of the axis span
GRID_TOL = 0.5            # pt

TDK_GRADES = ['N22', 'N27', 'N30', 'N41', 'N48', 'N49', 'N51', 'N72', 'N87', 'N88', 'N92', 'N95', 'N96', 'N97',
              'T35', 'T37', 'T38', 'T65', 'M33']
# (grade, T): (H left, H right in A/m, B bottom, B top in mT) as printed, for panels whose labels are outlines
# (grade, T): panels whose tick labels are drawn as outlines, read off the rendered page:
#   ('frame', H left, H right, B bottom, B top) - the plot frame's printed end values (frame lines on the grid), or
#   ('grid', H at the first gridline, H per gridline, B at the bottom gridline, B per gridline) - N27 frames its H
#   axis off the grid (about -350 A/m) with gridlines every 200 A/m from -200.  H in A/m, B in mT.
TDK_LOOP_AXES = {('N30', 25): ('frame', -100, 400, 0, 450), ('T35', 25): ('frame', -100, 400, 0, 450),
                 ('T37', 25): ('frame', -100, 400, 0, 450), ('T38', 25): ('frame', -100, 500, 0, 450),
                 ('T65', 25): ('frame', -200, 1400, 0, 600),
                 ('N27', 25): ('grid', -200, 200, 0, 50), ('N27', 100): ('grid', -200, 200, 0, 50)}
FERROXCUBE_GRADES = ['3C90', '3C91', '3C94', '3C95', '3C96', '3C97', '3C98', '3E10', '3E25', '3E26', '3E27', '3E6',
                     '3E65', '3F3', '3F36', '3F37', '3F4', '3F46', '3C92', '3C93', '3C11', '3B46', '4F1', '4C65']
MAGNETICS_GRADES = ['R', 'P', 'F', 'J']
# Magnetics W is refused (Alf, 2026-11-22): its figure reaches 425 mT at 250 A/m while the table on the same page gives
# 390 mT at 15 Oe, and the figure is almost point for point Ferroxcube 3E6's.
FAIRRITE_GRADES = ['77', '78', '79', '98', '75', '80']
# (H left, H right in Oe, B top in G) printed on each Fair-Rite loop image (B bottom 0)
FAIRRITE_LOOP_AXES = {'77': (-1, 5, 6000), '78': (-1, 5, 5000), '79': (-1, 5, 5000), '80': (-1, 5, 6000),
                      '98': (-1, 5, 6000), '75': (-0.5, 5, 5000)}
FAIRRITE_LOOP_URL = 'https://fair-rite.com/wp-content/uploads/2020/06/{grade}_BH.jpg'
EXTRA_SOURCES = {'3C95': 'Ferroxcube', '3C97': 'Ferroxcube', '3F46': 'Ferroxcube', '3C92': 'Ferroxcube', 'N22': 'TDK'}


# ---------------------------------------------------------------- geometry helpers

def bez(it, n=40):
    """Points along a path item; a straight segment is densified too, so that clipping it to the plot keeps its
    inside part (TDK draws the straight low part of a branch as one segment ending on the B = 0 frame line)."""
    if it[0] == 'l':
        a, c = it[1], it[2]
        return [(a.x + (c.x - a.x) * t, a.y + (c.y - a.y) * t) for t in np.linspace(0, 1, n + 1)]
    return rev.bezier_points(it, n)


def crossings_rows(paths, b):
    """H of every crossing of the drawn paths (arrays of (H, B)) with B = b."""
    hs = []
    for a in paths:
        H, B = a[:, 0], a[:, 1]
        d = B - b
        k = np.where((d[:-1] * d[1:] <= 0) & (d[:-1] != d[1:]))[0]
        hs.extend(H[k] + (b - B[k]) * (H[k + 1] - H[k]) / (B[k + 1] - B[k]))
    return np.sort(hs)


def crossings_cols(paths, h):
    bs = []
    for a in paths:
        H, B = a[:, 0], a[:, 1]
        d = H - h
        k = np.where((d[:-1] * d[1:] <= 0) & (d[:-1] != d[1:]))[0]
        bs.extend(B[k] + (h - H[k]) * (B[k + 1] - B[k]) / (H[k + 1] - H[k]))
    return np.sort(bs)


def clusters(values, gap):
    """Split sorted values into groups separated by more than `gap`; each group's median."""
    if len(values) == 0:
        return []
    groups = np.split(values, np.where(np.diff(values) > gap)[0] + 1)
    return [float(np.median(g)) for g in groups]


def rdp(points, eps):
    """Ramer-Douglas-Peucker on an (n, 2) array in already normalised coordinates; returns kept indices."""
    keep = np.zeros(len(points), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = points[i], points[j]
        ab = b - a
        n = np.hypot(*ab)
        seg = points[i + 1:j] - a
        d = np.abs(ab[0] * seg[:, 1] - ab[1] * seg[:, 0]) / n if n > 0 else np.hypot(seg[:, 0], seg[:, 1])
        k = int(np.argmax(d))
        if d[k] > eps:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return np.where(keep)[0]


def monotone(branch):
    """Branch points sorted by B; the largest subset that rises in both B and H. (Taking points greedily from the
    bottom let one stray reading, the "100 C" label on Fair-Rite 77's figure, at 335 A/m and 0.36 T, delete the
    whole real branch from 71 to 335 A/m.)"""
    branch = sorted(set(branch), key=lambda p: (p[1], -p[0]))    # at equal B, H falling: one point per B can be kept
    tails, last, parent = [], [], []
    for i, (h, b) in enumerate(branch):
        k = bisect.bisect_left(tails, h)
        parent.append(last[k - 1] if k else -1)
        if k == len(tails):
            tails.append(h); last.append(i)
        else:
            tails[k] = h; last[k] = i
    out, i = [], last[-1] if last else -1
    while i >= 0:
        out.append(branch[i]); i = parent[i]
    return out[::-1]


def branches_from_samples(rows, cols, hspan, bspan):
    """rows: [(b, [h clusters])], cols: [(h, [b clusters])]. Returns rising, falling as lists of (H, B), B rising."""
    rising, falling = [], []
    two_rows = [b for b, hs in rows if len(hs) == 2]
    two_cols = [h for h, bs in cols if len(bs) == 2]
    if not two_rows:
        raise Refused('the two branches were not both found')
    b_merge, h_merge = max(two_rows), (max(two_cols) if two_cols else np.inf)
    for b, hs in rows:
        if len(hs) == 2:
            falling.append((hs[0], b)); rising.append((hs[1], b))
        elif len(hs) == 1 and b > b_merge:
            falling.append((hs[0], b)); rising.append((hs[0], b))
    for h, bs in cols:
        if len(bs) == 2:
            rising.append((h, bs[0])); falling.append((h, bs[1]))
        elif len(bs) == 1 and h > h_merge:
            rising.append((h, bs[0])); falling.append((h, bs[0]))
    rising, falling = monotone(rising), monotone(falling)
    # the common B range: from the higher of the two lowest B up
    b_low = max(rising[0][1], falling[0][1])
    out = []
    for br in (rising, falling):
        br = [p for p in br if p[1] >= b_low - 1e-12]
        a = np.array(br)
        keep = rdp(np.c_[a[:, 0] / hspan, a[:, 1] / bspan], THIN_TOL)
        out.append([tuple(map(float, a[k])) for k in keep])
    return out[0], out[1]


def midline(rising, falling):
    r, f = np.array(rising), np.array(falling)
    lo, hi = max(r[0, 1], f[0, 1]), min(r[-1, 1], f[-1, 1])
    B = np.unique(np.r_[r[:, 1], f[:, 1]])
    B = B[(B >= lo) & (B <= hi)]
    return (np.interp(B, r[:, 1], r[:, 0]) + np.interp(B, f[:, 1], f[:, 0])) / 2, B


def trim_low(rising, falling):
    """The loop is centred on H = 0, so its midline passes through the origin and, at the lowest B the figure
    resolves, is within the reading noise of 0 (a fraction of an A/m either side). Both branches are written from
    the lowest midline B above which the midline H is positive and rises strictly; the rows below are dropped (both
    branches together, so the written part is still the loop as drawn, from a slightly higher B). Returns the
    trimmed branches and the B they start at."""
    Hm, Bm = midline(rising, falling)
    ok = (Hm > 0) & np.r_[np.diff(Hm) > 0, True]
    bad = np.where(~ok)[0]
    if not len(bad):
        start = Bm[0]
    elif bad[-1] + 1 >= len(Bm):
        raise Refused('the midline never rises from a positive H')
    else:
        k = bad[-1]
        start = Bm[k + 1]
        # A figure that draws its low part as one straight segment per branch (TDK) leaves the midline with no
        # sample between its reading-noise offset at the bottom (H <= 0) and the top of that segment. Restarting at
        # the next sample would throw the whole segment away; instead cut where the midline, interpolated along
        # the drawn segment, has risen as far above 0 as it sat below it at the bottom (the reading noise), so the
        # written loop keeps the segment and its midline starts at a positive H.
        noise = -Hm[k]
        if Hm[k] < 0 and Hm[k + 1] > noise and Hm[k + 1] > Hm[k]:
            start = float(np.interp(noise, [Hm[k], Hm[k + 1]], [Bm[k], Bm[k + 1]]))

    def cut(br):
        a = np.array(br)
        if a[0, 1] >= start:
            return br
        h0 = float(np.interp(start, a[:, 1], a[:, 0]))
        return [(h0, float(start))] + [p for p in br if p[1] > start]
    return cut(rising), cut(falling), float(start)


def accept(rising, falling, hc, T):
    """Acceptance checks; returns a dict of what was checked."""
    Hm, Bm = midline(rising, falling)
    if len(Bm) < 5:
        raise Refused(f'{T:.0f} C: the branches share only {len(Bm)} flux densities')
    if Bm[0] > LOOP_MIN_B:
        raise Refused(f'{T:.0f} C: both branches resolved only above {1e3 * Bm[0]:.0f} mT')
    halfwidth = (np.interp(Bm[0], np.array(rising)[:, 1], np.array(rising)[:, 0]) -
                 np.interp(Bm[0], np.array(falling)[:, 1], np.array(falling)[:, 0])) / 2
    ref, what = (hc, 'table Hc') if hc is not None else (halfwidth, 'loop half-width (no table Hc)')
    if abs(Hm[0]) > LOOP_CENTRE_TOL * ref:
        raise Refused(f'{T:.0f} C: midline at {Hm[0]:.1f} A/m at {1e3 * Bm[0]:.0f} mT, {what} {ref:.1f} A/m')
    centre, bcentre = float(Hm[0]), float(Bm[0])
    rising[:], falling[:], start = trim_low(rising, falling)
    Hm, Bm = midline(rising, falling)
    if Bm[0] > LOOP_MIN_B:
        raise Refused(f'{T:.0f} C: the midline rises strictly from a positive H only above {1e3 * Bm[0]:.0f} mT')
    if np.any(np.diff(Hm) <= 0):
        k = int(np.argmax(np.diff(Hm) <= 0))
        raise Refused(f'{T:.0f} C: the midline H(B) does not rise at {1e3 * Bm[k]:.0f} mT ({Hm[k]:.2f} -> {Hm[k + 1]:.2f} A/m)')
    if Hm[0] <= 0:
        raise Refused(f'{T:.0f} C: the midline starts at H = {Hm[0]:.2f} A/m <= 0 at {1e3 * Bm[0]:.0f} mT')
    return dict(bmin=float(Bm[0]), btip=float(max(np.array(rising)[-1, 1], np.array(falling)[-1, 1])),
                htip=float(max(rising[-1][0], falling[-1][0])), centre=centre, bcentre=bcentre, halfwidth=float(halfwidth),
                centre_ref=what, n=len(rising) + len(falling),
                mid15=float(np.interp(15.0, Hm, Bm)) if Hm[0] < 15 < Hm[-1] else None)


def sample_vector(paths, fills=(), hc=None):
    """Rows of crossings of vector paths ((H, B) arrays, B in T). `fills`: thin filled polygons that draw a stretch of
    a branch (TDK draws the straight low part of its loops so): each counts once per row, at the mean of its
    crossings. Crossings closer than max(0.4 % of the H span, Hc/2) belong to one branch (TDK draws a thick branch as
    several parallel strokes up to ~10 A/m apart; the two branches are >= 2 Hc apart)."""
    every = list(paths) + list(fills)
    hmin = min(a[:, 0].min() for a in every); hmax = max(a[:, 0].max() for a in every)
    bmax = max(a[:, 1].max() for a in every)
    hspan, bspan = hmax - hmin, bmax
    rows = []
    gap_h = max(0.004 * hspan, 0.5 * hc if hc else 0.0)
    # rows only: a column through a steep branch drawn as a bundle of strokes would split it into two "branches"
    for b in np.linspace(0.001 * bmax, 0.999 * bmax, 1000):
        hs = list(crossings_rows(paths, b))
        for poly in fills:
            c = crossings_rows([poly], b)
            if len(c) >= 2 and np.ptp(c) < 0.03 * hspan:
                hs.append(float(np.mean(c)))
        rows.append((b, clusters(np.sort(hs), gap_h)))
    rising, falling = branches_from_samples(rows, [], hspan, bspan)
    # the tip: the point of largest H drawn ends both branches
    tip = max(((float(a[i, 0]), float(a[i, 1])) for a in paths for i in [int(np.argmax(a[:, 0]))]), key=lambda p: p[0])
    for br in (rising, falling):
        if tip[0] > br[-1][0] and tip[1] > br[-1][1]:
            br.append(tip)
    return rising, falling, hspan, bspan


# ---------------------------------------------------------------- TDK

def tdk_panels(grade, doc, hc_of=lambda T: None):
    out = {}
    for page in doc:
        for hit in page.search_for('Dynamic magnetization curves'):
            cap = page.get_text('text', clip=fitz.Rect(hit.x0, hit.y0, hit.x0 + 200, hit.y1 + 40)).replace('\xa0', ' ')
            mt = re.search(r'T\s*=\s*(-?\d+)\s*°C', cap)
            if not mt:
                continue
            T = float(mt.group(1))
            region = fitz.Rect(hit.x0 - 30, hit.y1 + 20, hit.x0 + 260, hit.y1 + 340)
            try:
                out[T] = tdk_panel(grade, page, region, T, hc_of(T))
            except Refused as e:
                out[T] = e
    if not out:
        raise Refused('no "Dynamic magnetization curves" panel')
    return out


def tdk_panel(grade, page, region, T, hc=None):
    drawings = page.get_drawings()
    hl, vl = set(), set()
    for d in drawings:
        if (d.get('width') or 0) > 0.8:
            continue
        for it in d['items']:
            if it[0] == 'l' and region.contains(it[1]) and region.contains(it[2]):
                a, c = it[1], it[2]
                if abs(a.y - c.y) < 0.01 and abs(a.x - c.x) > 80:
                    hl.add(round(a.y, 2))
                if abs(a.x - c.x) < 0.01 and abs(a.y - c.y) > 80:
                    vl.add(round(a.x, 2))
    vl, hl = sorted(vl), sorted(hl)
    if len(vl) < 4 or len(hl) < 4:
        raise Refused(f'{T:.0f} C panel: gridlines not found')
    x0, x1, y0, y1 = vl[0], vl[-1], hl[-1], hl[0]      # the plot frame

    def grid(lines, what):
        """The evenly spaced gridlines (the frame lines at either end may sit off the grid: N27 frames its H axis
        at about -350 A/m with gridlines from -200)."""
        step = float(np.median(np.diff(lines)))
        inner = [l for l in lines if l != lines[0] and l != lines[-1]]
        ref = inner[0]
        k = np.round((np.array(inner) - ref) / step)
        if float(np.max(np.abs(np.array(inner) - ref - k * step))) > GRID_TOL:
            raise Refused(f'{T:.0f} C panel: {what} gridlines not evenly spaced')
        on = [l for l in (lines[0], lines[-1]) if abs((l - ref) / step - round((l - ref) / step)) * step <= GRID_TOL]
        return sorted(inner + on), step

    vg, vstep = grid(vl, 'H')
    hg, hstep = grid(hl, 'B')
    words = [w for w in page.get_text('words', clip=fitz.Rect(region.x0 - 20, region.y0, region.x1 + 20, region.y1 + 20))
             if re.match(r'^[−–-]?\d+$', w[4])]
    hlab = [((w[0] + w[2]) / 2, rev_num(w[4])) for w in words if w[1] > y0 - 1 and w[1] < y0 + 16]
    blab = [((w[1] + w[3]) / 2, rev_num(w[4])) for w in words if w[2] < x0 + 2 and y1 - 6 < (w[1] + w[3]) / 2 < y0 + 6]
    # each label sits on a gridline: calibrate on the gridline's position, not the label's (TDK sets them ragged)
    snap = lambda p, lines: min(lines, key=lambda g: abs(g - p))
    hlab = [(snap(x, vg), v) for x, v in hlab if min(abs(x - g) for g in vg) < 6]
    blab = [(snap(y, hg), v) for y, v in blab if min(abs(y - g) for g in hg) < 4]
    for lab, what in ((hlab, 'H'), (blab, 'B')):
        if len(set(p for p, _ in lab)) != len(lab):
            lab.clear()       # two labels on one gridline: unreadable, try the printed axis values
    how = 'tick labels on the evenly spaced gridlines'
    if len(hlab) >= 3 and len(blab) >= 3:
        ah = np.polyfit([q[0] for q in hlab], [q[1] for q in hlab], 1)
        ab = np.polyfit([q[0] for q in blab], [q[1] for q in blab], 1)
        for lab, a, span, what in ((hlab, ah, abs(np.polyval(ah, x1) - np.polyval(ah, x0)), 'H'),
                                   (blab, ab, abs(np.polyval(ab, y1) - np.polyval(ab, y0)), 'B')):
            res = max(abs(np.polyval(a, p) - v) for p, v in lab)
            if res > LABEL_TOL * span:
                raise Refused(f'{T:.0f} C panel: {what} tick labels off a line by {res:.3g}')
        toH = lambda x: np.polyval(ah, x)
        toB = lambda y: np.polyval(ab, y) * 1e-3
        axes = (float(toH(x0)), float(toH(x1)), float(np.polyval(ab, y0)), float(np.polyval(ab, y1)))
    elif (grade, int(T)) in TDK_LOOP_AXES:
        kind, *v = TDK_LOOP_AXES[(grade, int(T))]
        if kind == 'frame':
            h0, h1, b0, b1 = v
            if vg[0] != x0 or vg[-1] != x1 or hg[0] != y1 or hg[-1] != y0:
                raise Refused(f'{T:.0f} C panel: the frame is off the gridlines, the printed frame values do not apply')
            hg0, dh, bg0, db = h0, (h1 - h0) / round((x1 - x0) / vstep), b0, (b1 - b0) / round((y0 - y1) / hstep)
        else:
            hg0, dh, bg0, db = v
        toH = lambda x: hg0 + (x - vg[0]) / vstep * dh
        toB = lambda y: (bg0 + (hg[-1] - y) / hstep * db) * 1e-3
        axes = (float(toH(x0)), float(toH(x1)), float(toB(y0) * 1e3), float(toB(y1) * 1e3))
        how = 'axis values printed as outlines, read off the rendered page (TDK_LOOP_AXES), on the evenly spaced gridlines'
    else:
        raise Refused(f'{T:.0f} C panel: tick labels not readable as text and no TDK_LOOP_AXES entry')
    inner = fitz.Rect(x0 + 0.5, y1 + 0.5, x1 - 0.5, y0 - 0.5)
    on_grid = lambda pts: (all(abs(x - pts[0][0]) < 0.05 for x, _ in pts) and min(abs(pts[0][0] - v) for v in vl) < 0.05) or \
                          (all(abs(y - pts[0][1]) < 0.05 for _, y in pts) and min(abs(pts[0][1] - h) for h in hl) < 0.05)
    paths, fills = [], []
    for d in drawings:
        if not inner.intersects(d['rect']):
            continue
        if d.get('fill') is not None and not d.get('width'):
            # a thin filled polygon (no stroke) inside the plot: a stretch of a branch
            pts = [q for it in d['items'] for q in bez(it)]
            if len(pts) >= 3 and all(inner.contains(fitz.Point(q)) for q in pts):
                a = np.array([(toH(x), toB(y)) for x, y in pts + pts[:1]])
                fills.append(a)
            continue
        if d.get('fill') is not None or not d.get('width'):
            continue
        for it in d['items']:
            pts = [q for q in bez(it) if inner.contains(fitz.Point(q))]
            if len(pts) >= 2 and not on_grid(pts):
                paths.append(np.array([(toH(x), toB(y)) for x, y in pts]))
    if not paths:
        raise Refused(f'{T:.0f} C panel: no loop curve')
    rising, falling, hspan, bspan = sample_vector(paths, fills, hc)
    return dict(T=T, rising=rising, falling=falling, page=page.number + 1, axes=axes, how=how)


def rev_num(s):
    return float(s.replace('−', '-').replace('–', '-'))


# ---------------------------------------------------------------- Ferroxcube / Magnetics (vector, broken H axis)

NUM = re.compile(r'^[−–-]?\d+(\.\d+)?$')


def style(d):
    c = d.get('color') or (0, 0, 0)
    return (round(d.get('width') or 0, 2), tuple(round(x, 2) for x in c))


def vector_loop(page, search, temp_rule='width'):
    """Calibrated drawn paths per temperature: {T: [arrays (H A/m, B T)]}, plus the calibration info."""
    drawings = [d for d in page.get_drawings() if search.intersects(d['rect']) and d.get('width')]
    words = [w for w in page.get_text('words', clip=search) if NUM.match(w[4].strip())]
    rows, last = [], None
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        yc = (w[1] + w[3]) / 2
        if last is None or yc - last > 2.5:
            rows.append([])
        rows[-1].append(w); last = yc
    xrow = max((r for r in rows if len(r) >= 4), key=lambda r: r[0][1], default=None)
    cols = collections.defaultdict(list)
    for w in words:
        if xrow is None or w not in xrow:
            cols[round(w[2] / 3)].append(w)
    ycol = max(cols.values(), key=len, default=[])
    if xrow is None or len(ycol) < 3:
        raise Refused('tick labels not found')
    xl = sorted([((w[0] + w[2]) / 2, rev_num(w[4])) for w in xrow])
    xv = [q[1] for q in xl]
    if 0.0 in xv:      # a separate minus glyph: labels left of 0 printed as absolute values
        z = len(xv) - 1 - xv[::-1].index(0.0)
        xl, xv = (xl[z - 1:], xv[z - 1:]) if z else (xl, xv)
        if z:
            xv[0] = -abs(xv[0])
        xl = [(q[0], v) for q, v in zip(xl, xv)]
    while len(xl) > 3:
        s0 = (xl[1][1] - xl[0][1]) / (xl[1][0] - xl[0][0]); s1 = (xl[2][1] - xl[1][1]) / (xl[2][0] - xl[1][0])
        if s0 <= 0 or abs(s0 / s1 - 1) > 0.35:
            xl = xl[1:]
        else:
            break
    xv = [q[1] for q in xl]
    if np.any(np.diff(xv) <= 0):
        raise Refused(f'H labels not increasing: {xv}')
    yl = [((w[1] + w[3]) / 2, rev_num(w[4])) for w in ycol]
    ay = np.polyfit([q[0] for q in yl], [q[1] for q in yl], 1)
    yres = float(np.max(np.abs(np.polyval(ay, [q[0] for q in yl]) - [q[1] for q in yl])))
    if yres > 3:
        frames = [d['rect'] for d in drawings if any(it[0] == 're' for it in d['items']) and d.get('type') in ('s', 'fs')
                  and d['rect'].width > 100 and d['rect'].height > 60]
        ylo, yhi = min(yl, key=lambda q: q[1]), max(yl, key=lambda q: q[1])
        ok = [r for r in frames if abs(r.y1 - ylo[0]) < 8 and abs(r.y0 - yhi[0]) < 8]
        if not ok:
            raise Refused(f'B labels off a line by {yres:.1f} and no plot frame')
        r = ok[0]
        ay = np.polyfit([r.y1, r.y0], [ylo[1], yhi[1]], 1)
        yl = [(r.y1, ylo[1]), (r.y0, yhi[1])]
    xs = np.array([q[0] for q in xl])
    ytop, ybot = min(q[0] for q in yl), max(q[0] for q in yl)
    # the plot may reach above its highest B label (Ferroxcube labels 0..400 mT on a 0..500 mT frame): clip at the
    # highest long horizontal line spanning the H labels (frame or gridline) instead
    hlines = [min(it[1].y, it[2].y) for d in drawings for it in d['items'] if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.05
              and abs(it[1].x - it[2].x) > 0.8 * (xs[-1] - xs[0])]
    if hlines and min(hlines) < ytop:
        ytop = min(hlines)
    toH = lambda x: np.interp(x, xs, xv, left=np.nan, right=np.nan)
    curves = collections.defaultdict(list)
    for d in drawings:
        if d.get('type') == 'f':
            continue
        items = [it for it in d['items'] if not (it[0] == 'l' and (abs(it[1].x - it[2].x) < 0.05 or abs(it[1].y - it[2].y) < 0.05)
                                                 and abs(it[1].x - it[2].x) + abs(it[1].y - it[2].y) > 15)]
        pts = []
        for it in items:
            q = bez(it, 24)
            if pts and q and np.hypot(q[0][0] - pts[-1][0], q[0][1] - pts[-1][1]) > 2:
                pts.append((np.nan, np.nan))
            pts += q
        if len(pts) < 2:
            continue
        a = np.array(pts)
        inside = ~np.isnan(a[:, 0]) & (a[:, 0] >= xs[0] + 0.3) & (a[:, 0] <= xs[-1] - 0.3) & (a[:, 1] >= ytop - 0.5) & (a[:, 1] <= ybot - 0.3)
        for run in np.split(np.arange(len(a)), np.where(np.diff(inside.astype(int)) != 0)[0] + 1):
            if not inside[run[0]]:
                continue
            seg = a[run]
            if len(seg) < 4 or np.ptp(seg[:, 1]) < 10 or np.ptp(seg[:, 0]) < 0.2:
                continue
            curves[style(d)].append(seg)
    if not curves:
        raise Refused('no curves')
    st = list(curves)
    tw = [w for w in page.get_text('words') if re.match(r'^\d+', w[4])]
    legend = {}
    for d in page.get_drawings():
        r = d['rect']
        if d.get('width') and style(d) in curves and r.height < 1.5 and 4 < r.width < 40 and search.contains(r):
            near = [w for w in tw if abs((w[1] + w[3]) / 2 - r.y0) < 6 and 0 < w[0] - r.x1 < 25]
            if near:
                legend[style(d)] = float(re.match(r'^(\d+)', near[0][4]).group(1))
    if len(legend) >= 2:
        temps = {s: legend.get(s) for s in st}
        temps = {s: T for s, T in temps.items() if T in (25.0, 100.0)}
        rule = 'legend'
    elif temp_rule == 'width':
        widths = sorted(set(s[0] for s in st), reverse=True)
        temps = {s: 25.0 if s[0] == widths[0] else 100.0 if len(widths) > 1 and s[0] == widths[1] else None for s in st}
        rule = 'thicker stroke = 25 C'
    else:
        lum = sorted(set(sum(s[1]) for s in st), reverse=True)
        temps = {s: 25.0 if sum(s[1]) == lum[0] else 100.0 if len(lum) > 1 and sum(s[1]) == lum[1] else None for s in st}
        rule = 'lighter stroke = 25 C'
    out = {}
    for s, paths in curves.items():
        T = temps.get(s)
        if T is None:
            continue
        P = [np.c_[toH(a[:, 0]), np.polyval(ay, a[:, 1]) * 1e-3] for a in paths]
        P = [a[~np.isnan(a[:, 0])] for a in P]
        out[T] = [a for a in P if len(a) > 3]
    return out, dict(xlabels=xv, temp_rule=rule)


def vector_panels(page, search, temp_rule, what):
    paths, info = vector_loop(page, search, temp_rule)
    out = {}
    for T, P in paths.items():
        try:
            rising, falling, _, _ = sample_vector(P)
            out[T] = dict(T=T, rising=rising, falling=falling, page=page.number + 1, how=what + f' (H labels {info["xlabels"]}; '
                          f'temperature by {info["temp_rule"]})')
        except Refused as e:
            out[T] = e
    return out


def ferroxcube(grade, doc):
    errs = []
    for p in doc:
        for cap in p.search_for('B-H loop') + p.search_for('BH loop'):
            for search in (fitz.Rect(cap.x0 - 150, cap.y0 - 235, cap.x0 + 160, cap.y0 - 2),
                           fitz.Rect(cap.x0 - 150, cap.y1 + 2, cap.x0 + 300, cap.y1 + 260)):
                try:
                    out = vector_panels(p, search, 'width', '"Typical B-H loops", H axis broken, calibrated piecewise-linearly on its tick labels')
                    if out:
                        return out
                except Refused as e:
                    errs.append(str(e))
    raise Refused('no readable B-H loop figure: ' + '; '.join(errs))


def magnetics(grade, doc):
    p = doc[rev.MAGNETICS_PAGES[grade] - 1]
    cap = p.search_for('TYPICAL B-H LOOPS')
    if len(cap) != 1:
        raise Refused(f'{len(cap)} "TYPICAL B-H LOOPS" titles')
    c = cap[0]
    return vector_panels(p, fitz.Rect(c.x0 - 110, c.y1 + 1, c.x0 + 140, c.y1 + 175), 'light',
                         '"TYPICAL B-H LOOPS", H axis calibrated piecewise-linearly on its tick labels')


# ---------------------------------------------------------------- Fair-Rite (raster)

def fairrite(grade, path):
    from PIL import Image
    h0, h1, bm = FAIRRITE_LOOP_AXES[grade]
    im = np.asarray(Image.open(path).convert('RGB')).astype(int)
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    grey = (abs(R - G) < 12) & (abs(G - B) < 12) & (R > 120) & (R < 225)
    h, w = grey.shape
    cols = np.where(grey.sum(0) > 0.45 * h)[0]
    rows = np.where(grey.sum(1) > 0.45 * w)[0]
    group = lambda ix: [int(np.mean(g)) for g in np.split(ix, np.where(np.diff(ix) > 2)[0] + 1) if len(g)]
    V, Hl = group(cols), group(rows)
    if len(V) < 5 or len(Hl) < 5:
        raise Refused('gridlines not found')
    sv = np.diff(V); sh = np.diff(Hl)
    if np.ptp(sv) > 3 or np.ptp(sh) > 3:
        raise Refused(f'gridlines not evenly spaced: {sv.tolist()}, {sh.tolist()}')
    x0, x1, y0, y1 = V[0], V[-1], Hl[-1], Hl[0]
    toH = lambda x: (h0 + (x - x0) / (x1 - x0) * (h1 - h0)) * OERSTED
    toB = lambda y: (y0 - y) / (y0 - y1) * bm * 1e-4
    black = (R < 90) & (G < 90) & (B < 90)
    blue = (B > R + 50) & (B > 120)
    out = {}
    hspan, bspan = (h1 - h0) * OERSTED, bm * 1e-4
    for T, mask in ((25.0, black), (100.0, blue)):
        m = mask.copy(); m[:, :x0 + 2] = False; m[:, x1 - 1:] = False; m[:y1 + 1] = False; m[y0 - 1:] = False
        rws, cls = [], []
        for y in range(y0 - 2, y1 + 1, -1):
            xs = np.where(m[y])[0]
            runs = [g for g in np.split(xs, np.where(np.diff(xs) > 1)[0] + 1) if len(g)] if len(xs) else []
            if len(runs) > 2 or any(len(g) > 12 for g in runs):
                continue        # a label or a flat stretch: the columns resolve it
            rws.append((toB(y), [toH(np.mean(g)) for g in runs]))
        for x in range(x0 + 3, x1 - 1):
            ys = np.where(m[:, x])[0]
            runs = [g for g in np.split(ys, np.where(np.diff(ys) > 1)[0] + 1) if len(g)] if len(ys) else []
            if len(runs) > 2 or any(len(g) > 12 for g in runs):
                continue        # steep stretch: the rows resolve it
            cls.append((toH(x), sorted(toB(np.mean(g)) for g in runs)))
        try:
            rising, falling = branches_from_samples(rws, cls, hspan, bspan)
            out[T] = dict(T=T, rising=rising, falling=falling, page=None,
                          how=f'raster, axes {h0} to {h1} Oe and 0 to {bm} G as printed, on its evenly spaced gridlines')
        except Refused as e:
            out[T] = e
    return out


# ---------------------------------------------------------------- driver

def source(grade):
    if grade in FAIRRITE_GRADES:
        return 'Fair-Rite', FAIRRITE_LOOP_URL.format(grade=grade)
    if grade in rev.SOURCES:
        return rev.SOURCES[grade]
    maker = EXTRA_SOURCES[grade]
    return maker, {'Ferroxcube': f'{grade.lower()}.pdf', 'TDK': f'pdf-{grade.lower()}.pdf'}[maker]


def fetch(grade, cache):
    maker, rel = source(grade)
    if grade not in rev.SOURCES or maker == 'Fair-Rite':
        rev.SOURCES[grade] = (maker, rel)
    return rev.fetch(grade, cache)


def provenance(grade, maker, results, url, sha):
    if maker == 'Fair-Rite':
        name = f'Fair-Rite, "{grade} Material Hysteresis Loop" image on {rev.FR_PAGE.format(grade=grade)}'
    elif maker == 'TDK':
        name = f'TDK Electronics, SIFERRIT material {grade} data sheet'
    elif maker == 'Magnetics':
        name = 'Magnetics, 2025 Ferrite Catalog'
    else:
        name = f'Ferroxcube, {grade} material data sheet'
    parts = []
    for T, r in sorted(results.items()):
        a = r['accepted']
        parts.append(f'{T:.0f} C' + (f' (page {r["page"]})' if r['page'] else '') + f': {r["how"]}; both branches from '
                     f'{1e3 * a["bmin"]:.0f} mT to the tip at {a["htip"]:.0f} A/m, {1e3 * a["btip"]:.0f} mT; midline at '
                     f'{a["centre"]:.1f} A/m at the lowest drawn common B, {1e3 * a["bcentre"]:.0f} mT (checked against the {a["centre_ref"]})'
                     + (f', written from {1e3 * a["bmin"]:.0f} mT, where the midline H turns positive and rising (below it, reading noise about H = 0)'
                        if a["bmin"] > a["bcentre"] + 1e-9 else ''))
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': name,
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            'Major B-H loop as the manufacturer draws it, read off the figure (' + ('pixel runs of the raster' if maker == 'Fair-Rite' else 'vector paths')
            + f', sha256 {sha[:8]}...{sha[-4:]}). Per temperature one ordered traversal: rising branch up to the tip '
            '(largest H drawn), then falling branch back down; only where both branches are drawn (B >= the lowest B '
            'both reach). Points are crossings of the drawn curve with fine B rows and H columns, thinned to 0.2 % of '
            'the axis spans; nothing fitted; falling-branch samples at or above the tip B dropped. ' + '; '.join(parts)
            + ('. H above 50 A/m on a broken axis whose gridlines are not evenly spaced: a few A/m of uncertainty there'
               if maker in ('Ferroxcube', 'Magnetics') else '') + '.'),
        'fields': ['bhCycle'],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', required=True)
    ap.add_argument('--patch')
    ap.add_argument('grades', nargs='*')
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    db = args.patch or os.path.join(HERE, '..', 'data', 'core_materials.ndjson')
    records = [json.loads(line) for line in open(db)]

    def record_index(grade, maker):
        mk = maker.upper()
        hits = [i for i, m in enumerate(records) if m['name'] == grade and m.get('material') == 'ferrite'
                and rev.maker_of(m) and (rev.maker_of(m).split()[0].upper().startswith(mk) or
                                         (mk == 'TDK' and rev.maker_of(m).split()[0].upper().startswith('EPCOS')))]
        if len(hits) > 1:
            raise RuntimeError(f'{grade} ({maker}): {len(hits)} ferrite records match')
        return hits[0] if hits else None

    def table(rec, key, T):
        pts = [q for q in (rec.get(key) or []) if q.get('temperature') is not None and abs(q['temperature'] - T) <= 5]
        if len(pts) > 1:
            raise RuntimeError(f'{rec["name"]}: {len(pts)} {key} values within 5 C of {T}')
        return pts[0]['magneticField'] if pts else None

    grades = args.grades or (TDK_GRADES + FERROXCUBE_GRADES + MAGNETICS_GRADES + FAIRRITE_GRADES)
    results = {}
    for grade in grades:
        maker = source(grade)[0]
        idx = record_index(grade, maker)
        if idx is None:
            print(f'{grade} ({maker}): no MAS ferrite record, skipped')
            continue
        rec = records[idx]
        try:
            url, path, sha = fetch(grade, args.cache)
            if maker == 'TDK':
                panels = tdk_panels(grade, fitz.open(path), lambda T: table(rec, 'coerciveForce', T))
            elif maker == 'Ferroxcube':
                panels = ferroxcube(grade, fitz.open(path))
            elif maker == 'Magnetics':
                panels = magnetics(grade, fitz.open(path))
            else:
                panels = fairrite(grade, path)
        except Refused as e:
            print(f'{grade} ({maker}): REFUSED: {e}')
            continue
        accepted = {}
        for T, r in sorted(panels.items()):
            if isinstance(r, Refused):
                print(f'{grade} ({maker}) {T:.0f} C: refused: {r}')
                continue
            try:
                r['accepted'] = accept(r['rising'], r['falling'], table(rec, 'coerciveForce', T), T)
            except Refused as e:
                print(f'{grade} ({maker}) {T:.0f} C: refused: {e}')
                continue
            accepted[T] = r
            a = r['accepted']
            print(f'{grade} ({maker}) {T:.0f} C: {a["n"]} points, B {1e3 * a["bmin"]:.0f}-{1e3 * a["btip"]:.0f} mT, tip '
                  f'{a["htip"]:.0f} A/m, centre {a["centre"]:.1f} A/m ({a["centre_ref"]}), midline B(15 A/m) '
                  + (f'{1e3 * a["mid15"]:.0f} mT' if a['mid15'] is not None else '-'))
        if accepted:
            results[grade] = (accepted, url, sha, idx, maker)
    if not args.patch:
        return
    out, done = [], []
    for index, line in enumerate(open(args.patch).read().splitlines()):
        m = json.loads(line)
        hit = [g for g, v in results.items() if v[3] == index]
        if hit:
            grade = hit[0]
            accepted, url, sha, _, maker = results[grade]
            ascii_form = json.dumps(m) == line
            cycle = []
            for T, r in sorted(accepted.items()):
                down = list(reversed(r['falling']))
                # The branches meet at the tip: a falling sample at lower H with at least the tip's B is the stroke's
                # width (up to 1.5 mT), and the traversal would not be monotone. The shared tip is written once.
                tip = r['rising'][-1][1]
                while down and round(down[0][1], 5) >= round(tip, 5):
                    down = down[1:]
                for h, b in list(r['rising']) + down:
                    cycle.append({'magneticFluxDensity': round(b, 5), 'magneticField': round(h, 3), 'temperature': T})
            m['bhCycle'] = cycle
            prov = [p for p in m.get('provenance', []) if 'bhCycle' not in (p.get('fields') or [])]
            prov.append(provenance(grade, maker, accepted, url, sha))
            m['provenance'] = prov
            info = m.setdefault('manufacturerInfo', {})
            if not info.get('datasheetUrl'):
                info['datasheetUrl'] = rev.FR_PAGE.format(grade=grade) if maker == 'Fair-Rite' else url
            line = json.dumps(m, ensure_ascii=ascii_form)
            done.append(grade)
        out.append(line)
    open(args.patch, 'w').write('\n'.join(out) + '\n')
    print(f'patched {len(done)}: {done}')


if __name__ == '__main__':
    main()
