#!/usr/bin/env python3
"""Reversible permeability mu_rev(H_DC, T) of ferrites from their manufacturers' data sheets, written as
permeability.reversible points (TDK and Ferroxcube).

WHY
    A ferrite's loss and small-signal inductance under DC bias follow its reversible permeability: the slope of a
    vanishing AC excursion around the DC operating point, MAS `permeability.reversible`. It is kept apart from
    `permeability.initial`, whose DC-bias dependence consumers integrate into the B(H) curve: a reversible
    permeability integrated that way undercounts B (it leaves out the irreversible wall motion).

WHAT IT READS
    The figures' vector paths (lines and cubic Beziers, evaluated exactly), nothing traced from pixels. Log axes
    are calibrated on each figure's own gridlines: decade lines are found from the spacing pattern, every gridline
    must sit on a + b log10(m 10^k), m = 1..9, within GRID_TOL, and the decade exponents are read from the tick
    labels (superscripts told apart by font size) and must agree with one another; otherwise the figure is refused.

FERROXCUBE ("Reversible permeability as a function of magnetic field strength")
    Measured on ungapped ring cores: the material curve itself. Points are read off the curve on a fixed H grid
    inside the drawn range (log-log interpolation between evaluated path points); nothing is fitted. Where the
    curve is flat within FLAT_TOL over its first drawn decade, the left-end value is also written at H = 0. The
    temperature is the one the figure or caption states; none is written when it states none.

TDK ("DC magnetic bias", gapped cores, mu_e = 50 ... 1000 (1500), 25 C and often 100 C)
    TDK draws the reversible permeability of GAPPED cores only; the gap is taken out by Ampere, with no assumed
    B-H curve. Curve i has the gap term g_i = 1/mu_e0,i - 1/mu_i, mu_e0,i its drawn zero-bias level at 25 C and
    mu_i the table value (same core, same g_i, at other temperatures). A material level L shows on curve i as
    mu_rev,e = 1/(1/L + g_i), reached at H_DC,i; all curves at that level share the material state (H, B), so
    H_DC,i = H + (B/mu0) g_i is a line in g_i, fitted with sigma = 1 % of H_DC (log-axis reading). B (the slope) is
    well determined; H (the intercept) is a small difference of large numbers, so a figure is accepted only when
    it is solid:
      - a level is kept when >= MIN_CURVES curves show it and its H is >= MIN_SIGNIFICANCE sigma, sigma scaled by
        the curves' observed disagreement; the curves may disagree by at most MAX_DISAGREEMENT;
      - the first kept level is >= ONSET_LEVEL of mu_rev(0) (the onset of the drop is observed, not extrapolated);
      - the solved field rises as the permeability falls; the smooth fit has chi2/dof <= MAX_CHI2;
      - mu_rev(Hc/2) >= REVERSIBLE_FLOOR mu_rev(0) with the table's coercive field (a reversible permeability
        changes on the scale of the coercive field: a figure whose knees all sit at one flux density, as drawn by a
        model, fails here);
      - at other temperatures each curve's drawn level must lie within MAX_PLACEMENT of where its 25 C gap and
        mu_i(T) (the data sheet's mu_i(T) curve, as tabulated in the database) put it; the curve is read as a ratio
        to its own drawn level.
    Accepted levels are smoothed with mu_rev(0) / (1 + (H/H0)^c)^k (even in H, zero slope at H = 0) and sampled from
    H = 0 to the largest solved field; mu_rev(0) is mu_i at 25 C and mu_i(T) otherwise.

Usage:
    python3 scripts/digitize-reversible-permeability.py --cache DIR [--patch data/core_materials.ndjson] [GRADE ...]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import urllib.request

import numpy as np
import fitz  # PyMuPDF
from scipy.optimize import least_squares

MU0 = 4e-7 * np.pi
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
TDK_BASE = 'https://www.tdk-electronics.tdk.com/download/'
FXC_BASE = 'https://www.ferroxcube.com/upload/media/product/file/MDS/'
# grade -> (manufacturer, data sheet path); TDK paths as listed on its ferrite-materials catalogue page
SOURCES = {
    'N27': ('TDK', '528850/3a7f957d754f899aec42cd946598c5c4/pdf-n27.pdf'),
    'N41': ('TDK', '528876/07f8fe5e7fb654a26dc779e207a5de15/pdf-n41.pdf'),
    'N48': ('TDK', '528870/80183d6ef4a48b49c5bee48a6e8b2ac5/pdf-n48.pdf'),
    'N49': ('TDK', '528856/c44cc4ec800e9f6f22a8068409c85b4f/pdf-n49.pdf'),
    'N51': ('TDK', '528840/956e4358867968c72a6f3dc4fb7da68e/pdf-n51.pdf'),
    'N72': ('TDK', '528858/fe38d2b52133890d5f7cc6885ff05e75/pdf-n72.pdf'),
    'N87': ('TDK', '528882/d6940b239127a8bab71b22168746021b/pdf-n87.pdf'),
    'N91': ('TDK', '3108406/407bd23272e3b6e4f672151b54b9ef4d/pdf-n91.pdf'),
    'N92': ('TDK', '528888/2eb193d57530c5ad7aef246387fea250/pdf-n92.pdf'),
    'N95': ('TDK', '528866/0fe9e667e8e8afa649f776a2a5a7eb0a/pdf-n95.pdf'),
    'N97': ('TDK', '528886/81166f0de556e5b6a94db7793daed936/pdf-n97.pdf'),
    'M33': ('TDK', '528878/4f65b2fcd11b8b6b3e99fa2bc44bfd7e/pdf-m33.pdf'),
    '3B46': ('Ferroxcube', '3b46.pdf'), '3C11': ('Ferroxcube', '3c11.pdf'), '3C90': ('Ferroxcube', '3c90.pdf'),
    '3C91': ('Ferroxcube', '3c91.pdf'), '3C93': ('Ferroxcube', '3c93.pdf'), '3C94': ('Ferroxcube', '3c94.pdf'),
    '3C96': ('Ferroxcube', '3c96.pdf'), '3C98': ('Ferroxcube', '3c98.pdf'), '3E10': ('Ferroxcube', '3e10.pdf'),
    '3E27': ('Ferroxcube', '3e27.pdf'), '3E6': ('Ferroxcube', '3e6.pdf'), '3E65': ('Ferroxcube', '3e65.pdf'),
    '3F3': ('Ferroxcube', '3f3.pdf'), '3F36': ('Ferroxcube', '3f36.pdf'), '3F37': ('Ferroxcube', '2025%20MDS%203F37.pdf'),
    '3F4': ('Ferroxcube', '3f4.pdf'), '4F1': ('Ferroxcube', '4f1.pdf'),
}
GRID_TOL = 0.5           # pt (about 1 % of a decade), a gridline off the fitted log grid by more refuses the figure
FLAT_TOL = 0.01          # Ferroxcube: flat first decade -> the left value is written at H = 0 too
READ_SIGMA = 0.01        # TDK: relative reading accuracy of H_DC on a log axis
MIN_CURVES = 3
MIN_SIGNIFICANCE = 5
MAX_DISAGREEMENT = 0.06
ONSET_LEVEL = 0.8
MAX_CHI2 = 4.0
REVERSIBLE_FLOOR = 0.9
MAX_PLACEMENT = 0.10
H_GRID = sorted(set([0.0] + list(np.arange(2, 10, 2)) + list(np.arange(10, 50, 5)) + list(np.arange(50, 100, 10)) +
                    list(np.arange(100, 200, 20)) + list(np.arange(200, 1000, 50)) + list(np.arange(1000, 10001, 500))))


class Refused(Exception):
    pass


def fetch(grade, cache):
    maker, rel = SOURCES[grade]
    url = (TDK_BASE if maker == 'TDK' else FXC_BASE) + rel
    path = os.path.join(cache, os.path.basename(rel).replace('%20', '_'))
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, 'wb') as f:
            f.write(r.read())
    data = open(path, 'rb').read()
    if not data.startswith(b'%PDF'):
        raise Refused(f'{url} is not a PDF')
    return url, path, hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- figure reading (both manufacturers)

def spans_of(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines', []):
            for s in line['spans']:
                if s['text'].strip():
                    out.append((fitz.Rect(s['bbox']), s['size'], s['text'].strip()))
    return out


def label_exponent(spans):
    """A decade tick label: 10 with a superscript exponent (sign possibly a separate glyph), or a plain power of ten."""
    if not spans:
        return None
    spans = sorted(spans, key=lambda s: s[0].x0)
    base = max(s[1] for s in spans)
    big = ''.join(s[2] for s in spans if s[1] >= 0.85 * base)
    small = ''.join(s[2] for s in spans if s[1] < 0.85 * base)
    norm = lambda t: t.replace('_', '-').replace('−', '-').replace('–', '-').replace(' ', '')
    big, small = norm(big), norm(small)
    if small:
        if big.endswith('-'):
            big, small = big[:-1], '-' + small
        m = re.fullmatch(r'10(-?)', big)
        if m and re.fullmatch(r'-?\d', small):
            return int(m.group(1) + small) if not small.startswith('-') else int(small)
        return None
    m = re.fullmatch(r'10(-?\d)', big)   # superscript merged into one span by the PDF producer: ambiguous with 100
    if m and big not in ('10', '100', '1000', '10000'):
        return int(m.group(1))
    try:
        v = float(big)
    except ValueError:
        return None
    if v > 0 and abs(np.log10(v) - round(np.log10(v))) < 1e-9:
        return int(round(np.log10(v)))
    return None


def calibrate_log(lines, spans, axis, box):
    """Returns position -> value for a log axis drawn with gridlines at `lines`."""
    p = np.array(sorted(set(np.round(lines, 2))))
    if axis == 'y':
        p = p[::-1]
    if len(p) < 3:
        raise Refused(f'{axis} axis: only {len(p)} gridlines')
    d = np.abs(np.diff(p))
    if d.max() / d.min() < 1.1:
        decades = list(range(len(p)))          # only decade lines are drawn
    else:
        decades = [0] + [i for i in range(1, len(p) - 1) if d[i] / d[i - 1] > 4] + [len(p) - 1]
    b0 = abs(p[decades[-1]] - p[decades[0]]) / (len(decades) - 1)
    # assign every gridline its log value (decade index + log10 of the nearest mantissa 1..10), then fit
    # position = a + b * logvalue over all of them; every residual must be within GRID_TOL
    logv = []
    for q in p:
        frac = abs(q - p[0]) / b0
        k = np.floor(frac + 1e-6)
        m = min(range(1, 11), key=lambda m: abs(np.log10(m) - (frac - k)))
        logv.append(k + np.log10(m))
    logv = np.array(logv)
    A = np.c_[np.ones_like(logv), logv]
    (a_fit, b_fit), *_ = np.linalg.lstsq(A, np.abs(p - p[0]), rcond=None)
    resid = np.abs(p - p[0]) - A @ [a_fit, b_fit]
    if np.abs(resid).max() > GRID_TOL:
        i = int(np.argmax(np.abs(resid)))
        raise Refused(f'{axis} axis: gridline at {p[i]:.2f} is {resid[i]:+.2f} pt off the log grid')
    b = b_fit
    p = p.copy(); p0_shift = a_fit
    e0s = set()
    for j, i in enumerate(decades):
        pos = p[i]
        if axis == 'x':
            near = [s for s in spans if abs((s[0].x0 + s[0].x1) / 2 - pos) < 12 and box.y1 - 1 < s[0].y0 < box.y1 + 22]
        else:
            near = [s for s in spans if abs((s[0].y0 + s[0].y1) / 2 - pos) < 8 and box.x0 - 40 < s[0].x1 < box.x0 + 2]
        e = label_exponent(near)
        if e is not None:
            e0s.add(e - j)
    if len(e0s) != 1:
        raise Refused(f'{axis} axis: decade tick labels read {sorted(e0s) or "none"} (need one consistent reading)')
    e0 = e0s.pop()
    a = p[0] + (p0_shift if axis == 'x' else -p0_shift)
    if axis == 'x':
        return lambda x: 10 ** (e0 + (x - a) / b)
    return lambda y: 10 ** (e0 + (a - y) / b)


def bezier_points(item, n=40):
    if item[0] == 'l':
        return [(item[1].x, item[1].y), (item[2].x, item[2].y)]
    if item[0] != 'c':
        return []
    P = item[1:5]
    out = []
    for k in range(n + 1):
        t = k / n
        w = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3)
        out.append((sum(w[i] * P[i].x for i in range(4)), sum(w[i] * P[i].y for i in range(4))))
    return out


def read_figure(page, region):
    """Gridlines and data curves of a log-log figure inside `region`."""
    drawings = page.get_drawings()
    hl, vl = [], []     # (y, x0, x1, width), (x, y0, y1, width)
    for d in drawings:
        w = d.get('width') or 0
        if w > 0.8:
            continue
        for it in d['items']:
            if it[0] != 'l':
                continue
            a, c = it[1], it[2]
            if not (region.contains(a) and region.contains(c)):
                continue
            if abs(a.y - c.y) < 0.01 and abs(a.x - c.x) > 80:
                hl.append((a.y, min(a.x, c.x), max(a.x, c.x), w))
            if abs(a.x - c.x) < 0.01 and abs(a.y - c.y) > 80:
                vl.append((a.x, min(a.y, c.y), max(a.y, c.y), w))
    if len(hl) < 3 or len(vl) < 3:
        raise Refused('gridlines not found')
    # one plot: the horizontal gridlines sharing the most common x-extent, and the verticals inside it
    from collections import Counter
    extent = Counter((round(x0), round(x1)) for _, x0, x1, _ in hl).most_common(1)[0][0]
    hl = [h for h in hl if h[1] >= extent[0] - 1 and h[2] <= extent[1] + 1]   # segments broken by label boxes too
    ylo, yhi = min(h[0] for h in hl), max(h[0] for h in hl)
    vl = [v for v in vl if extent[0] - 1 <= v[0] <= extent[1] + 1 and v[1] < yhi and v[2] > ylo]
    H = [h[0] for h in hl]; V = [v[0] for v in vl]; widths = [h[3] for h in hl] + [v[3] for v in vl]
    if len(H) < 3 or len(V) < 3:
        raise Refused('gridlines of one plot not found')
    box = fitz.Rect(min(V), min(H), max(V), max(H))
    spans = spans_of(page)
    tox = calibrate_log(V, spans, 'x', box)
    toy = calibrate_log(H, spans, 'y', box)
    minw = 1.5 * max(widths)
    paths = []
    for d in drawings:
        if (d.get('width') or 0) < minw or not box.intersects(d['rect']):
            continue
        if d.get('dashes') not in (None, '[] 0'):
            continue
        pts = []
        for it in d['items']:
            pts += bezier_points(it)
        pts = [(x, y) for x, y in pts if box.x0 - 0.5 <= x <= box.x1 + 0.5 and box.y0 - 0.5 <= y <= box.y1 + 0.5]
        on_frame = all(min(abs(x - box.x0), abs(x - box.x1)) < 0.6 or min(abs(y - box.y0), abs(y - box.y1)) < 0.6 for x, y in pts)
        if len(pts) > 1 and not on_frame:
            paths.append(pts)
    curves = []
    for pth in sorted(paths, key=lambda q: q[0][0]):
        for c in curves:
            if np.hypot(c[-1][0] - pth[0][0], c[-1][1] - pth[0][1]) < 1.0:
                c += pth
                break
        else:
            curves.append(list(pth))
    data = []
    for c in curves:
        a = np.array([(tox(x), toy(y)) for x, y in c])
        a = a[np.argsort(a[:, 0], kind='stable')]
        data.append(a)
    data.sort(key=lambda a: -a[0, 1])
    return data


# ---------------------------------------------------------------- Ferroxcube: ungapped material curve

def ferroxcube(grade, doc):
    for page in doc:
        hits = page.search_for('Reversible permeability')
        if not hits:
            continue
        cap = hits[0]
        caption = page.get_textbox(fitz.Rect(cap.x0 - 60, cap.y0, cap.x0 + 260, cap.y1 + 30))
        region = fitz.Rect(cap.x0 - 75, cap.y0 - 300, cap.x0 + 240, cap.y0 - 2)
        curves = read_figure(page, region)
        if len(curves) != 1:
            raise Refused(f'figure on page {page.number + 1} has {len(curves)} data curves, one expected')
        a = curves[0]
        T = None
        figtext = page.get_textbox(region) + ' ' + caption
        mt = re.search(r'(?:T\s*=\s*|at\s*)(-?\d+)\s*[º°]\s*C', figtext)
        if mt:
            T = float(mt.group(1))
        h, mu = a[:, 0], a[:, 1]
        keep = np.r_[True, np.diff(h) > 0]
        h, mu = h[keep], mu[keep]
        if np.any(np.diff(mu) > 0.01 * mu[:-1]):
            raise Refused('the curve rises with H somewhere')
        lh, lm = np.log(h), np.log(mu)
        pts = []
        first_decade = mu[h <= 10 * h[0]]
        if first_decade.max() / first_decade.min() - 1 <= FLAT_TOL:
            pts.append((0.0, float(mu[0])))
        for x in H_GRID:
            if h[0] <= x <= h[-1]:
                pts.append((float(x), float(np.exp(np.interp(np.log(x), lh, lm)))))
        if pts[-1][0] < h[-1] * 0.999:
            pts.append((float(round(h[-1], 1)), float(mu[-1])))
        report = dict(T=T, page=page.number + 1, hmin=float(h[0]), hmax=float(h[-1]), mu0=float(mu[0]),
                      ratio={x: round(float(np.exp(np.interp(np.log(x), lh, lm)) / mu[0]), 3) for x in (15, 30, 45, 60) if h[0] <= x <= h[-1]})
        points = []
        for x, v in pts:
            q = {'value': round(v, 1), 'magneticFieldDcBias': round(x, 1)}
            if T is not None:
                q['temperature'] = T
            points.append(q)
        return points, [report], []
    raise Refused('no "Reversible permeability" figure')


def ferroxcube_provenance(grade, report, url, sha):
    r = report[0]
    t = f'at {r["T"]:.0f} C' if r['T'] is not None else 'at a temperature the figure does not state'
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': f'Ferroxcube, {grade} material data sheet',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"Reversible permeability as a function of magnetic field strength", page {r["page"]}, {t}; read off the '
            f'vector path of the curve, {r["hmin"]:.3g}-{r["hmax"]:.3g} A/m, on log axes calibrated on the figure\'s '
            f'gridlines; document sha256 {sha[:8]}...{sha[-4:]}. The H = 0 point is the curve\'s flat left end.'),
        'fields': ['permeability.reversible'],
    }


# ---------------------------------------------------------------- TDK: gapped cores, un-gapped by Ampere

def table_value(doc, pattern, what):
    for page in doc:
        m = re.search(pattern, page.get_text())
        if m:
            return m
    raise Refused(f'no {what} in the data sheet table')


def tdk_panels(doc):
    panels = []
    for page in doc:
        hits = page.search_for('DC magnetic bias')
        words = page.get_text('words') if hits else []
        for hit in hits:
            cap = fitz.Rect(hit.x0 - 2, hit.y0, hit.x0 + 230, hit.y1 + 45)
            text = ' '.join(w[4] for w in words if cap.contains(fitz.Rect(w[:4])))
            mt = re.search(r'T\s*=\s*(\d+)\s*°C', text)
            if not mt:
                continue
            # the caption ends at the line carrying the temperature (words below it belong to the plot)
            bottom = max(w[3] for w in words if cap.contains(fitz.Rect(w[:4])) and '°C' in w[4])
            region = fitz.Rect(hit.x0 - 30, bottom, hit.x0 + 260, bottom + 330)
            T = float(mt.group(1))
            try:
                panels.append(dict(T=T, page=page.number + 1, curves=read_figure(page, region)))
            except Refused as e:
                panels.append(dict(T=T, page=page.number + 1, error=str(e)))
    return panels


def solve_levels(curves, g, levels):
    rows = []
    for L in levels:
        pts = []
        for a, gi in zip(curves, g):
            target = 1 / (1 / L + gi)
            drop = target / a[0, 1]
            if not (0.25 < drop < 0.985):
                continue
            idx = np.where((a[:-1, 1] >= target) & (a[1:, 1] < target))[0]
            if not len(idx):
                continue
            i = idx[0]
            t = (a[i, 1] - target) / (a[i, 1] - a[i + 1, 1])
            pts.append((gi, a[i, 0] + t * (a[i + 1, 0] - a[i, 0])))
        if len(pts) < MIN_CURVES:
            continue
        G = np.array([q[0] for q in pts]); Hd = np.array([q[1] for q in pts])
        A = np.c_[np.ones_like(G), G]; W = 1 / (READ_SIGMA * Hd)
        (Hm, slope), *_ = np.linalg.lstsq(A * W[:, None], Hd * W, rcond=None)
        cov = np.linalg.inv((A * W[:, None]).T @ (A * W[:, None]))
        rel = (Hd - A @ [Hm, slope]) / Hd
        rms = float(np.sqrt(np.mean(rel ** 2)))
        rows.append(dict(L=L, H=Hm, sH=np.sqrt(cov[0, 0]) * max(1.0, rms / READ_SIGMA), B=slope * MU0, n=len(pts), rms=rms))
    return rows


def fit_and_sample(rows, mu0):
    H = np.array([r['H'] for r in rows]); L = np.array([r['L'] for r in rows]); s = np.array([r['sH'] for r in rows])
    f = lambda p, L: p[0] * np.maximum((mu0 / L) ** (1 / p[2]) - 1, 1e-12) ** (1 / p[1])
    r = least_squares(lambda p: (f(p, L) - H) / s, [40, 3, 1], bounds=([1, 0.5, 0.1], [2000, 12, 10]))
    res = (f(r.x, L) - H) / s
    H0, c, k = r.x
    hmax = float(H.max())
    grid = [h for h in H_GRID if h <= hmax] + [round(hmax, 1)]
    pts = [(float(h), float(mu0 / (1 + (h / H0) ** c) ** k)) for h in grid]
    return pts, dict(chi2=float(np.sum(res ** 2) / max(1, len(H) - 3)), hmin=float(H.min()), hmax=hmax)


def tdk(grade, doc, mui_of_T):
    mui = float(table_value(doc, r'Initial permeability\s*\(T = 25 °C\)\s*\S+\s*(\d{3,5})\s', 'initial permeability (T = 25 C)').group(1))
    m = table_value(doc, r'Hc \(25 °C\)\s*Hc \(100 °C\)\s*(?:A/m\s*)+(\d+)\s+(\d+)', 'coercive field strengths (25 / 100 C)')
    coercive = {25.0: float(m.group(1)), 100.0: float(m.group(2))}
    panels = tdk_panels(doc)
    if not panels:
        raise Refused('no "DC magnetic bias" figure')
    temps = [p['T'] for p in panels]
    if len(set(temps)) != len(temps):
        raise Refused(f'two DC-bias figures carry the same temperature label {temps}')
    p25 = [p for p in panels if p['T'] == 25]
    if not p25:
        raise Refused('no 25 C DC-bias figure to take the gaps from')
    if 'error' in p25[0]:
        raise Refused(f'25 C figure: {p25[0]["error"]}')
    if len(p25[0]['curves']) < MIN_CURVES:
        raise Refused(f'25 C figure has {len(p25[0]["curves"])} gapped curve(s), {MIN_CURVES} needed')
    g = [1 / a[0, 1] - 1 / mui for a in p25[0]['curves']]
    if min(g) <= 0:
        raise Refused(f'a curve starts at or above mu_i = {mui:.0f}: not a gapped core')
    points, report, refused = [], [], []
    for p in panels:
        try:
            if 'error' in p:
                raise Refused(p['error'])
            if len(p['curves']) != len(g):
                raise Refused(f'{len(p["curves"])} curves, the 25 C figure has {len(g)}')
            if p['T'] == 25:
                mu0, curves = mui, p['curves']
            else:
                mu0 = mui_of_T(p['T'])
                expected = [1 / (gi + 1 / mu0) for gi in g]
                drawn = [a[0, 1] for a in p['curves']]
                if max(abs(d / e - 1) for d, e in zip(drawn, expected)) > MAX_PLACEMENT:
                    raise Refused(f'curves drawn at {[round(x) for x in drawn]}; the 25 C gaps and mu_i = {mu0:.0f} '
                                  f'put them at {[round(x) for x in expected]}')
                curves = [np.c_[a[:, 0], a[:, 1] * e / a[0, 1]] for a, e in zip(p['curves'], expected)]
            rows = solve_levels(curves, g, np.geomspace(0.97 * mu0, 0.03 * mu0, 60))
            rows = [r for r in rows if r['H'] >= MIN_SIGNIFICANCE * r['sH']]
            if len(rows) < 5:
                raise Refused(f'only {len(rows)} levels have a material field resolved to {MIN_SIGNIFICANCE} sigma '
                              f'by >= {MIN_CURVES} curves')
            worst = max(r['rms'] for r in rows)
            if worst > MAX_DISAGREEMENT:
                raise Refused(f'the gapped curves disagree by up to {100 * worst:.1f} % in H_DC at one material level')
            if rows[0]['L'] < ONSET_LEVEL * mu0:
                raise Refused(f'the first solved level is {rows[0]["L"] / mu0:.2f} of mu_rev(0) (at '
                              f'{rows[0]["H"]:.0f} A/m): the onset of the drop is not observed')
            for r1, r2 in zip(rows[:-1], rows[1:]):
                if r2['H'] < r1['H'] - 2 * np.hypot(r1['sH'], r2['sH']):
                    raise Refused(f'solved field falls from {r1["H"]:.0f} to {r2["H"]:.0f} A/m as the permeability falls')
            pts, fit = fit_and_sample(rows, mu0)
            if fit['chi2'] > MAX_CHI2:
                raise Refused(f'smooth fit chi2/dof {fit["chi2"]:.1f}')
            if p['T'] not in coercive:
                raise Refused('no coercive field in the table at this temperature')
            hc = coercive[p['T']]
            half = np.interp(hc / 2, [q[0] for q in pts], [q[1] for q in pts]) / mu0
            if half < REVERSIBLE_FLOOR:
                raise Refused(f'mu_rev falls to {half:.2f} of mu_rev(0) at Hc/2 = {hc / 2:.0f} A/m')
            for h, v in pts:
                points.append({'value': round(v, 1), 'temperature': p['T'], 'frequency': 10000.0,
                               'magneticFluxDensityPeak': 0.00025, 'magneticFieldDcBias': round(h, 1)})
            report.append(dict(T=p['T'], page=p['page'], n=len(g), mu0=mu0, worst_rms=worst, **fit,
                               ratio={h: round(float(np.interp(h, [q[0] for q in pts], [q[1] for q in pts]) / mu0), 3)
                                      for h in (15, 30, 45, 60) if h <= fit['hmax']}))
        except Refused as e:
            refused.append(f'{p["T"]:.0f} C: {e}')
    if not report:
        raise Refused(' | '.join(refused))
    return points, report, refused


def tdk_provenance(grade, report, url, sha):
    figs = '; '.join(f'{r["T"]:.0f} C on page {r["page"]} ({r["n"]} gapped curves, field solved '
                     f'{r["hmin"]:.0f}-{r["hmax"]:.0f} A/m, curves agree within {100 * r["worst_rms"]:.1f} %)' for r in report)
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': f'TDK Electronics, SIFERRIT material {grade} data sheet',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"DC magnetic bias" figures of gapped cores (B <= 0.25 mT, f = 10 kHz), read off their vector paths: {figs}; '
            f'document sha256 {sha[:8]}...{sha[-4:]}. Material values recovered by Ampere: each curve\'s gap from its drawn '
            f'zero-bias level and the table mu_i at 25 C; at each material permeability the field and flux density '
            f'solved jointly over the at least 3 curves showing it. Points sampled from mu_rev(0)/(1 + (H/H0)^c)^k fitted '
            f'to the solved levels; below the first solved field the drawing resolves no drop over 20 % and the points '
            f'follow the fitted shape. mu_rev(0) is the table mu_i at 25 C and the data sheet mu_i(T) curve otherwise.'),
        'fields': ['permeability.reversible'],
    }


def mui_table(record, T):
    """mu_i(T) of the database record (the data sheet's mu_i(T) curve), linear between tabulated temperatures."""
    if record is None:
        raise Refused(f'no database record for mu_i({T:.0f} C)')
    pts = record['permeability']['initial']
    pts = pts if isinstance(pts, list) else [pts]
    tab = sorted((q['temperature'], q['value']) for q in pts if q.get('temperature') is not None and not q.get('magneticFieldDcBias'))
    if len(tab) < 2 or not tab[0][0] <= T <= tab[-1][0]:
        raise Refused(f'mu_i(T) in the database does not cover {T:.0f} C')
    return float(np.interp(T, [t for t, _ in tab], [v for _, v in tab]))


def maker_of(record):
    return record.get('manufacturerInfo', {}).get('name', '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', required=True)
    ap.add_argument('--patch')
    ap.add_argument('grades', nargs='*')
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    db = args.patch or os.path.join(os.path.dirname(__file__), '..', 'data', 'core_materials.ndjson')
    records = {}
    for line in open(db):
        m = json.loads(line)
        records[(m['name'], maker_of(m).split()[0].upper() if maker_of(m) else '')] = m
    def record(grade):
        maker = SOURCES[grade][0].upper()
        keys = [k for k in records if k[0] == grade and (k[1].startswith(maker) or (maker == 'TDK' and k[1].startswith('EPCOS')))]
        return records[keys[0]] if keys else None
    results = {}
    for grade in args.grades or sorted(SOURCES):
        maker = SOURCES[grade][0]
        try:
            url, path, sha = fetch(grade, args.cache)
            doc = fitz.open(path)
            if maker == 'TDK':
                points, report, refused = tdk(grade, doc, lambda T, g=grade: mui_table(record(g), T))
            else:
                points, report, refused = ferroxcube(grade, doc)
        except Refused as e:
            print(f'{grade} ({maker}): REFUSED: {e}')
            continue
        results[grade] = (points, report, url, sha)
        for r in refused:
            print(f'{grade} ({maker}): figure refused: {r}')
        for r in report:
            t = f'{r["T"]:.0f} C' if r['T'] is not None else 'T unstated'
            print(f'{grade} ({maker}) {t}: mu_rev(0) {r["mu0"]:.0f}, {r["hmin"]:.3g}-{r["hmax"]:.3g} A/m, '
                  f'mu_rev(H)/mu_rev(0) {r["ratio"]}' + (f', curves agree {100 * r["worst_rms"]:.1f} %, fit chi2/dof {r["chi2"]:.1f}' if 'chi2' in r else ''))
    if not args.patch:
        return
    out, done = [], set()
    for line in open(args.patch).read().splitlines():
        m = json.loads(line)
        ascii_form = json.dumps(m) == line          # keep each line in the encoding it was written in
        grade = m.get('name')
        if grade in results and record(grade) is not None and record(grade)['name'] == grade and maker_of(record(grade)) == maker_of(m):
            points, report, url, sha = results[grade]
            m['permeability']['reversible'] = points
            prov = [p for p in m.get('provenance', []) if 'permeability.reversible' not in (p.get('fields') or [])]
            prov.append((tdk_provenance if SOURCES[grade][0] == 'TDK' else ferroxcube_provenance)(grade, report, url, sha))
            m['provenance'] = prov
            done.add(grade)
            line = json.dumps(m, ensure_ascii=ascii_form)
        out.append(line)
    open(args.patch, 'w').write('\n'.join(out) + '\n')
    print(f'patched {sorted(done)}; accepted but not in the database: {sorted(set(results) - done)}')


if __name__ == '__main__':
    main()
