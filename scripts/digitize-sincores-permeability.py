#!/usr/bin/env python3
"""Digitize mu_i(T) for the Sincores NiZn grades from the maker's own property
sheets, and cross-check each curve against the maker's tabulated relative
temperature coefficient.  ABT #632.

WHO PUBLISHES WHAT
    Sincores (東莞昱欣電子有限公司, http://www.sincores.com) is the factory.
    Halo Cosmos (長大國際股份有限公司, http://www.halocosmos.com) is the trading
    house that resells it and names SINCORES as its supply factory (供應工廠).
    The maker's 材質一覽 page lists 40 NiZn grades, and every row links a
    per-grade "MAGNETIC PROPERTIES OF MATERIAL" sheet - a bitmap with four
    small-signal curves.  The bottom-right one, "Inductance Change as a
    Function of Temperature", is the only published temperature dependence for
    these grades, and this script is what turns it into a MAS permeability
    sweep.  (The other three curves are relative loss factor, mu_i and Q versus
    frequency; none of them is a power-level Pv curve, so they do not close the
    volumetricLosses gap of ABT #575.)

PIPELINE
    1. fetch material.html, parse the 40-row table (this is also the source of
       the tabulated mu_i each curve is normalised to),
    2. fetch the per-grade sheet bitmap,
    3. locate the bottom-right chart as the largest dark structure in the
       bottom-right quadrant of the sheet,
    4. calibrate:  y from the frame edges, whose top and bottom labels are
       checked to actually sit on those edges;  x from the VERTICAL GRID LINES
       - the tick labels on these sheets are hand-placed and demonstrably not
       evenly spaced (DS6 is the clearest case), so the labels are used only to
       pin the two ends of the grid and the grid itself carries the scale.  The
       resulting degrees-per-grid-interval must come out a round number or the
       grade is refused,
    5. follow the red curve column by column, keeping the longest run per
       column,
    6. resample on a 5 C grid, stop at the published Curie temperature and
       before any near-vertical stretch (a column trace cannot resolve one),
       and normalise so mu_i(25 C) equals the maker's tabulated value,
    7. CROSS-CHECK: recompute the relative temperature coefficient from the
       digitized curve as (mu2-mu1)/(mu1*mu2*dT) over 20..70 C (clipped to the
       curve) and compare it with the coefficient the maker tabulates.  A grade
       whose curve disagrees with its own table is reported and NOT shipped -
       the two maker publications contradict each other and nothing in either
       resolves which is right.

    The AXES table below is the only hand-entered input: the axis annotations
    read off each sheet by eye.  Every one of them is re-checked numerically
    here before a curve is emitted.

Usage:
    python3 scripts/digitize-sincores-permeability.py [--out curves.json]
                                                      [--cache DIR] [GRADE ...]
"""
import argparse
import gzip
import io
import json
import os
import re
import sys
import tempfile
import urllib.request

import numpy as np
from PIL import Image
from scipy import ndimage

BASE = 'http://www.sincores.com'
TABLE_URL = BASE + '/material.html'
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/151.0.0.0 Safari/537.36')

# grade -> (value of the first x tick label, x label step, number of x labels,
#           value on the bottom frame, value on the top frame)
AXES = {
    'A5B': (-40, 10, 12, -20, 20),
    'A9N': (-40, 10, 12, -20, 20),
    'D2H': (-30, 10, 10, -40, 60),
    'DS6': (-40, 10, 12, -20, 20),
    'L4A': (-30, 10, 12, -40, 80),
    'L5D': (-30, 10, 12, -20, 20),
    'N4S': (-30, 30, 10, -50, 100),
    'N5H': (-30, 30, 10, -100, 170),
    'N6F': (-30, 30, 9, -100, 200),
    'N6H': (-30, 30, 10, -100, 260),
    'N8S': (-30, 30, 10, -100, 230),
    'R5A': (-40, 10, 12, -20, 20),
    'R6B': (-40, 10, 12, -20, 20),
    'R7H': (-40, 10, 12, -20, 20),
    'R9H': (-40, 10, 12, -20, 20),
    'S1A': (-40, 10, 12, -20, 20),
    'S2K': (-40, 40, 5, -90, 60),
    'S4H': (-30, 10, 12, -40, 80),
    'S5C': (-40, 10, 12, -20, 20),
    'S8H': (-30, 10, 12, -40, 80),
    'SFK': (-30, 10, 12, -40, 80),
    'SL5': (-40, 10, 12, -20, 20),
    'SL6': (-40, 10, 12, -20, 20),
    'STF': (-30, 30, 10, -100, 170),
    'T3B': (-40, 10, 12, -20, 20),
    'TFH': (-30, 10, 12, -40, 80),
}


# --------------------------------------------------------------------------- fetch
def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': TABLE_URL})
    with urllib.request.urlopen(req, timeout=90) as fh:
        raw = fh.read()
        if fh.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
    return raw


def maker_table(cache):
    p = os.path.join(cache, 'material.html')
    if not os.path.exists(p):
        with open(p, 'wb') as fh:
            fh.write(fetch(TABLE_URL))
    h = open(p, encoding='utf-8-sig').read()
    t = h[h.find('<table'):h.find('</table>')]
    out = {}
    for r in re.findall(r'<tr.*?</tr>', t, re.S):
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.S)
        cells = [re.sub(r'</?(a|span|p|br|b|strong|div)[^>]*>', '', c).replace('&nbsp;', ' ').strip()
                 for c in cells]
        if len(cells) < 8 or cells[0].startswith('Characteristics') or cells[0].startswith('ft'):
            continue
        m = re.search(r'href="([^"]+)"', r)
        out[cells[0]] = dict(ft=cells[1], mui=cells[2], bm=cells[3], tc=cells[4], sg=cells[5],
                             rlf=cells[6], tcoef=cells[7], img=m.group(1) if m else None)
    if len(out) < 30:
        raise RuntimeError('maker table looks wrong: %d rows' % len(out))
    return out


def sheet(cache, grade, rel):
    p = os.path.join(cache, grade + os.path.splitext(rel)[1])
    if not os.path.exists(p):
        with open(p, 'wb') as fh:
            fh.write(fetch(BASE + rel))
    return p


# --------------------------------------------------------------------- image work
def load(path):
    a = np.asarray(Image.open(path).convert('RGB')).astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    gray = (r + g + b) / 3.0
    red = (r - g > 40) & (r - b > 40) & (r > 90)
    return gray, red


def chart_box(gray, red):
    """bounding box of the bottom-right chart's frame"""
    H, W = gray.shape
    m = (gray < 220) & (~red)
    lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
    cands = []
    for i, sl in enumerate(ndimage.find_objects(lab)):
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        cy, cx = (ys.start + ys.stop) / 2.0, (xs.start + xs.stop) / 2.0
        if cy < 0.52 * H or cx < 0.45 * W:
            continue
        cands.append([ys.start, ys.stop - 1, xs.start, xs.stop - 1, h * w])
    if not cands:
        raise RuntimeError('bottom-right chart not found')
    cands.sort(key=lambda c: -c[4])
    b = list(cands[0])
    changed = True
    while changed:                      # JPEG noise breaks the frame into pieces
        changed = False
        for c in cands:
            ov = min(b[3], c[3]) - max(b[2], c[2])
            bw, cw = b[3] - b[2], c[3] - c[2]
            if ov > 0.55 * min(bw, cw) and cw > 0.5 * bw:
                ny0, ny1 = min(b[0], c[0]), max(b[1], c[1])
                nx0, nx1 = min(b[2], c[2]), max(b[3], c[3])
                if (ny1, nx1, ny0, nx0) != (b[1], b[3], b[0], b[2]):
                    b[0], b[1], b[2], b[3] = ny0, ny1, nx0, nx1
                    changed = True
    return dict(top=b[0], bot=b[1], left=b[2], right=b[3])


def _blobs(mask, axis, merge_gap):
    prof = mask.sum(axis=axis) > 0
    idx = np.where(prof)[0]
    if len(idx) == 0:
        return []
    groups, cur = [], [idx[0]]
    for i in idx[1:]:
        if i - cur[-1] <= merge_gap:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    out = []
    for gp in groups:
        if len(gp) < 3:
            continue
        w = (mask[:, gp].sum(axis=0) if axis == 0 else mask[gp, :].sum(axis=1)).astype(float)
        out.append(float(np.dot(np.array(gp), w) / w.sum()))
    return out


def x_label_centroids(gray, red, box):
    H, W = gray.shape
    ink = (gray < 175) & (~red)
    off = max(0, box['left'] - 14)
    s = ink[box['bot'] + 4:min(H, box['bot'] + 30), off:min(W, box['right'] + 14)]
    return [c + off for c in _blobs(s, 0, 3)]


def y_label_centroids(gray, red, box):
    H, W = gray.shape
    ink = (gray < 175) & (~red)
    y0 = max(0, box['top'] - 12)
    s = ink[y0:min(H, box['bot'] + 12), max(0, box['left'] - 46):box['left'] - 4]
    return [c + y0 for c in _blobs(s, 1, 5)]


def grid_lines(gray, red, box):
    d = np.where(red, 0.0, np.clip(255.0 - gray, 0, None))
    prof = d[box['top']:box['bot'] + 1, box['left']:box['right'] + 1].mean(axis=0)
    idx = np.where(prof >= 0.30 * prof.max())[0]
    if len(idx) < 3:
        raise RuntimeError('fewer than 3 grid lines')
    groups, cur = [], [idx[0]]
    for i in idx[1:]:
        if i - cur[-1] <= 2:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    return [float(np.dot(np.array(g), prof[g]) / prof[g].sum()) + box['left'] for g in groups]


def calibrate(gray, red, box, grade):
    x0v, xstep, nx, ybot, ytop = AXES[grade]
    gl = sorted(grid_lines(gray, red, box))
    gaps = np.diff(gl)
    if len(gaps) < 2:
        raise RuntimeError('%s: only %d grid lines' % (grade, len(gl)))
    p0 = float(np.median(gaps))
    fine = gaps[(gaps > 0.75 * p0) & (gaps < 1.25 * p0)]
    if len(fine) < 0.4 * len(gaps):
        raise RuntimeError('%s: grid spacing is not uniform' % grade)
    pitch = float(fine.mean())
    a = gl[0]
    if abs(a - box['left']) > 12:
        raise RuntimeError('%s: first grid line %.1f px off the left frame' % (grade, a - box['left']))

    xc = x_label_centroids(gray, red, box)
    if len(xc) < 3:
        raise RuntimeError('%s: only %d x tick-label blobs' % (grade, len(xc)))
    devf, devl = (min(xc) - a) / pitch, (max(xc) - a) / pitch
    kf, kl = int(round(devf)), int(round(devl))
    if abs(devf - kf) > 0.42 or abs(devl - kl) > 0.42:
        raise RuntimeError('%s: outer x labels do not sit on grid lines (%.2f, %.2f)'
                           % (grade, devf, devl))
    if kl - kf <= 0:
        raise RuntimeError('%s: degenerate x label span' % grade)
    per_grid = xstep * (nx - 1) / float(kl - kf)
    nice = min([1, 2, 2.5, 5, 10, 15, 20, 25, 30, 40, 50], key=lambda v: abs(v - per_grid))
    if abs(nice - per_grid) > 0.04 * nice:
        raise RuntimeError('%s: grid step %.3f C is not a round number' % (grade, per_grid))

    yc = y_label_centroids(gray, red, box)
    if len(yc) < 2:
        raise RuntimeError('%s: only %d y tick-label blobs' % (grade, len(yc)))
    if abs(min(yc) - box['top']) > 6 or abs(max(yc) - box['bot']) > 6:
        raise RuntimeError('%s: the outer y labels are not on the frame edges' % grade)

    return dict(x_px0=a, x_val0=x0v - kf * nice, x_deg_per_px=nice / pitch,
                y_px0=box['bot'], y_val0=ybot,
                y_per_px=(ytop - ybot) / float(box['bot'] - box['top']),
                grid_step=nice, grid_lines=len(gl))


def trace(red, box):
    sub = red[box['top']:box['bot'] + 1, box['left']:box['right'] + 1]
    cols, rows = [], []
    for j in range(sub.shape[1]):
        idx = np.where(sub[:, j])[0]
        if len(idx) == 0:
            continue
        runs, cur = [], [idx[0]]
        for i in idx[1:]:
            if i - cur[-1] <= 2:
                cur.append(i)
            else:
                runs.append(cur)
                cur = [i]
        runs.append(cur)
        runs.sort(key=len)
        cols.append(j + box['left'])
        rows.append(float(np.mean(runs[-1])) + box['top'])
    if len(cols) < 20:
        raise RuntimeError('curve too short (%d columns)' % len(cols))
    return np.array(cols, float), np.array(rows, float)


# ------------------------------------------------------------------- mu_i and check
def band(s):
    s = s.strip()
    m = re.match(r'^(-?\d+(?:\.\d+)?)\s*-\s*\+?(-?\d+(?:\.\d+)?)$', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.match(r'^-(\d+(?:\.\d+)?)-\+(\d+(?:\.\d+)?)$', s)
    if m:
        return -float(m.group(1)), float(m.group(2))
    return float(s), float(s)


def one(cache, grade, row):
    p = sheet(cache, grade, row['img'])
    gray, red = load(p)
    box = chart_box(gray, red)
    cal = calibrate(gray, red, box, grade)
    cols, rows = trace(red, box)
    T = cal['x_val0'] + (cols - cal['x_px0']) * cal['x_deg_per_px']
    dl = cal['y_val0'] + (cal['y_px0'] - rows) * cal['y_per_px']

    order = np.argsort(T)
    T, dl = T[order], dl[order]
    grid = np.arange(np.ceil(T.min() / 5.0) * 5.0, np.floor(T.max() / 5.0) * 5.0 + 1e-9, 5.0)
    dlg = np.interp(grid, T, dl)

    mui = float(row['mui'])
    curie = float(row['tc'].lstrip('>'))
    d25 = float(np.interp(25.0, grid, dlg))
    mu = mui * (1 + dlg / 100.0) / (1 + d25 / 100.0)

    cut = len(grid)
    for i in range(int(np.argmax(dlg)) + 1, len(grid)):
        if abs(dlg[i] - dlg[i - 1]) / (grid[i] - grid[i - 1]) > 4.0:
            cut = i
            break
    keep = (grid <= curie) & (np.arange(len(grid)) < cut)

    # the coefficient is recomputed from the sampled sweep itself, over as much
    # of the maker's own 20..70 C window as the curve actually covers
    t1, t2 = max(20.0, float(grid.min())), min(70.0, float(grid.max()))
    m1, m2 = float(np.interp(t1, grid, mu)), float(np.interp(t2, grid, mu))
    alpha = (m2 - m1) / (m1 * m2 * (t2 - t1)) * 1e6
    lo, hi = band(row['tcoef'])
    ok = hi > 0 and (0.8 * lo - 1e-9) <= alpha <= (1.25 * hi + 1e-9)

    return dict(grade=grade, mui=mui, curie=curie, grid_step=cal['grid_step'],
                grid_lines=cal['grid_lines'], dl25=round(d25, 2),
                window=[t1, t2], alpha=round(alpha, 1), published=[lo, hi], consistent=bool(ok),
                points=[[float(a) + 0.0, round(float(b), 1)]
                        for a, b in zip(grid[keep], mu[keep])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('grades', nargs='*')
    ap.add_argument('--out', default='sincores-permeability.json')
    ap.add_argument('--cache', default=None)
    args = ap.parse_args()

    cache = args.cache or tempfile.mkdtemp(prefix='sincores-')
    os.makedirs(cache, exist_ok=True)
    tbl = maker_table(cache)
    grades = args.grades or sorted(AXES)

    out, rc = {}, 0
    print('%-4s %5s %6s %5s %-9s %8s  %s' %
          ('grd', 'mu_i', 'grid', 'pts', 'published', 'digitis', 'verdict'))
    for g in grades:
        if g not in AXES:
            print('%-4s  no axis annotation on file - add it to AXES first' % g)
            rc = 1
            continue
        try:
            r = one(cache, g, tbl[g])
        except Exception as exc:                       # noqa: BLE001 - reported, not hidden
            print('%-4s  REFUSED: %s' % (g, exc))
            rc = 1
            continue
        lo, hi = r['published']
        pub = ('%g' % lo) if lo == hi else ('%g-%g' % (lo, hi))
        print('%-4s %5g %5g C %5d %-9s %8.1f  %s  (%g..%g C)'
              % (g, r['mui'], r['grid_step'], len(r['points']), pub, r['alpha'],
                 'CONSISTENT' if r['consistent'] else 'INCONSISTENT - do not ship',
                 r['points'][0][0], r['points'][-1][0]))
        out[g] = r

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1)
    print('wrote %s (%d grades; %d consistent)'
          % (args.out, len(out), sum(1 for v in out.values() if v['consistent'])))
    return rc


if __name__ == '__main__':
    sys.exit(main())
