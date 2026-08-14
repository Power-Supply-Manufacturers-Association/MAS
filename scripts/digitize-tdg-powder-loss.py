#!/usr/bin/env python3
"""Digitize TDG's metal-powder-core loss charts and audit MAS's stored `tdg` coefficients.

    python3 scripts/digitize-tdg-powder-loss.py tdg_powder.pdf              # dump the charts
    python3 scripts/digitize-tdg-powder-loss.py tdg_powder.pdf --audit      # + compare to MAS

Source
------
  https://www.tdgcore.com/en/technical-support/data-download   ->  "Metal Magnetic Powder Cores"
  (currently /uploads/file/20251110/1762741756399916.pdf; that 2025-11 upload is byte-identical
  to the May-2024 edition, so there is only one catalogue to digitize.)

Why a script instead of eyeballing the charts
---------------------------------------------
The charts are Adobe Illustrator vector art: every constant-frequency loss curve is ONE
straight segment in log-log, and the decade gridlines and their tick labels pin both axes
with no human judgement.  So the published curves can be read back EXACTLY, and - because
MKF's `tdg` model is itself a power law in B - re-fitted with no loss of information:

    MKF (src/physical_models/CoreLosses.cpp, VolumetricCoreLossesMethodType::TDG):
        P[W/m3] = 1000 * (10*B)^a * (b*f/1000 + c*(f/1000)^d)     B in T (AC peak), f in Hz

    in the units TDG plots (P in mW/cm3 == kW/m3, B in Gauss, f in kHz):
        P = (B/1000)^a * (b*f + c*f^d)

so `a` IS the log-log slope of the drawn curves and (b, c, d) are fixed by the seven curve
values at B = 1000 G (= 100 mT, TDG's own reference flux density).

Guard rails (every one of them is an assert, not a fallback)
------------------------------------------------------------
  * the decade count of each axis is taken from the gridlines AND cross-checked against the
    printed tick labels - a stray duplicate gridline once inflated three charts by a whole
    decade and made TMS/TMSA/TMF 60 um look 4-5x lossier than TDG's own summary table;
  * curves are ranked top-to-bottom and paired with the in-chart "NNkHz" labels ranked by
    frequency, then each label is VERIFIED to sit within 14 pt of the curve it was given.

Written for ABT #195.  Needs PyMuPDF (pip install pymupdf); --audit also needs scipy.
"""
import argparse
import json
import math
import os
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit('needs PyMuPDF:  pip install pymupdf')

GREY_GRIDLINE = (0.40, 0.48)      # the decade gridlines are a neutral grey in this range
LABEL_TOLERANCE_PT = 14.0         # max gap between a "NNkHz" label and the curve it names


def _points(drawing):
    pts = []
    for it in drawing['items']:
        if it[0] == 'l':
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif it[0] == 'c':
            p0, p1, p2, p3 = it[1], it[2], it[3], it[4]
            for k in range(9):
                t, mt = k / 8.0, 1 - k / 8.0
                pts.append((mt**3*p0.x + 3*mt*mt*t*p1.x + 3*mt*t*t*p2.x + t**3*p3.x,
                            mt**3*p0.y + 3*mt*mt*t*p1.y + 3*mt*t*t*p2.y + t**3*p3.y))
    return pts


def chart_frames(page):
    """Calibration for every loss chart on the page (there are one or two)."""
    words = page.get_text('words')
    ys = set()
    for d in page.get_drawings():
        col = d['color'] or ()
        if len(col) == 3 and max(col) - min(col) < 0.02 and GREY_GRIDLINE[0] < col[0] < GREY_GRIDLINE[1]:
            for it in d['items']:
                if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.01:
                    ys.add(round(it[1].y, 2))
    ys = sorted(ys)
    if not ys:
        return []
    deduped = []
    for y in ys:                       # 474.60 and 474.61 are the same gridline
        if not deduped or y - deduped[-1] > 0.5:
            deduped.append(y)
    charts, cur = [], [deduped[0]]
    for y in deduped[1:]:
        if y - cur[-1] < 60:
            cur.append(y)
        else:
            charts.append(cur)
            cur = [y]
    charts.append(cur)

    out = []
    for c in charts:
        below = [w for w in words if max(c) < w[1] < max(c) + 25]
        xlab = {w[4]: 0.5 * (w[0] + w[2]) for w in below if w[4] in ('100', '1000', '10000')}
        if '100' not in xlab or '10000' not in xlab:
            continue                    # not a loss chart (e.g. a DC-bias chart)
        # the y tick labels sit left of the plot, one per decade gridline
        ylab = [w for w in words if w[4] in ('1', '10', '100', '1000', '10000')
                and w[2] < xlab['100'] - 2 and min(c) - 6 < 0.5 * (w[1] + w[3]) < max(c) + 6]
        assert len(ylab) == len(c), (c, [w[4] for w in ylab])
        assert sorted(int(w[4]) for w in ylab) == [10 ** k for k in range(len(c))], \
            [w[4] for w in ylab]
        title_word, best = None, 1e9
        for w in words:
            if 'μ' in w[4]:
                dy = min(c) - w[3]
                if 0 < dy < 40 and dy < best:
                    best, title_word = dy, w
        title = ''
        if title_word is not None:
            title = ' '.join(w[4] for w in words
                             if abs(w[1] - title_word[1]) < 3 and w[0] < 400)
        out.append(dict(x0=xlab['100'], x1=xlab['10000'], ytop=min(c), ybot=max(c),
                        ndec_y=len(c) - 1, title=title))
    return out


def digitize_page(doc, page_index):
    """[(chart title, [(frequency Hz, [(B Gauss, P kW/m3), ...]), ...]), ...]"""
    page = doc[page_index]
    words = page.get_text('words')
    result = []
    for fr in chart_frames(page):
        curves = []
        for d in page.get_drawings():
            col = d['color'] or ()
            if d['type'] != 's' or len(col) != 3 or max(col) - min(col) < 0.08:
                continue                # grey / black is chrome, coloured is data
            pts = _points(d)
            if not pts:
                continue
            ymid = sum(p[1] for p in pts) / len(pts)
            if not (fr['ytop'] - 20 <= ymid <= fr['ybot'] + 20):
                continue
            curves.append(sorted(pts))
        if len(curves) < 3:
            continue
        labels = []
        for w in words:
            m = re.match(r'^(\d+)kHz$', w[4])
            if m and fr['ytop'] - 5 <= 0.5 * (w[1] + w[3]) <= fr['ybot'] + 5 and 200 < w[0] < 300:
                labels.append((float(m.group(1)) * 1e3, 0.5 * (w[1] + w[3]), 0.5 * (w[0] + w[2])))
        assert len(labels) == len(curves), (page_index, fr['title'], len(labels), len(curves))
        curves.sort(key=lambda pts: -sum(p[1] for p in pts) / len(pts))   # lowest curve first
        labels.sort(key=lambda t: t[0])                                    # lowest frequency first
        out = []
        for (f, ly, lx), pts in zip(labels, curves):
            (ax, ay), (bx, by) = pts[0], pts[-1]
            yat = ay + (by - ay) * (lx - ax) / (bx - ax)
            assert abs(ly - yat) < LABEL_TOLERANCE_PT, (page_index, fr['title'], f, ly, yat)
            data = []
            for x, y in pts:
                data.append((100 * 10 ** ((x - fr['x0']) / (fr['x1'] - fr['x0']) * 2),
                             10 ** ((fr['ybot'] - y) / (fr['ybot'] - fr['ytop']) * fr['ndec_y'])))
            out.append((f, sorted(data)))
        result.append((fr['title'], out))
    return result


def at_1000_gauss(poly):
    """The drawn curve's loss at 100 mT.

    Each catalogue curve is a single straight segment in log-log, so evaluating its line is
    exact even a few percent outside the clipped plot box (the clipping is a plot-frame
    artefact, not a statement about the data).
    """
    (b0, p0), (b1, p1) = poly[0], poly[-1]
    t = (math.log(1000.0) - math.log(b0)) / (math.log(b1) - math.log(b0))
    return math.exp(math.log(p0) + t * (math.log(p1) - math.log(p0)))


def fit_chart(curves):
    """Fit MKF's tdg form to one chart.  Returns dict(a, b, c, d, rms_pct, g)."""
    import numpy as np
    from scipy.optimize import least_squares

    slopes = [math.log(poly[-1][1] / poly[0][1]) / math.log(poly[-1][0] / poly[0][0])
              for _, poly in curves]
    a = float(np.mean(slopes))
    fs = np.array([f / 1e3 for f, _ in curves])
    g = np.array([at_1000_gauss(poly) for _, poly in curves])

    def resid(p):
        return np.log(p[0] * fs + p[1] * fs ** p[2]) - np.log(g)

    best = None
    for b0 in (0.2, 1, 3, 8, 15):
        for c0 in (1e-4, 5e-3, 3e-2, 0.2):
            for d0 in (1.4, 1.8, 2.2, 2.8):
                r = least_squares(resid, [b0, c0, d0], method='trf',
                                  bounds=([0., 0., 1.0], [1e3, 1e3, 4.0]), max_nfev=20000)
                if best is None or r.cost < best.cost - 1e-12:
                    best = r
    rms = float(np.sqrt(np.mean(resid(best.x) ** 2)))
    return dict(a=a, b=float(best.x[0]), c=float(best.x[1]), d=float(best.x[2]),
                slope_min=min(slopes), slope_max=max(slopes),
                rms_pct=100 * (math.exp(rms) - 1),
                g={int(f): float(v) for (f, _), v in zip(curves, g)})


def predict(coef, f_hz, b_tesla):
    """MKF's tdg volumetric losses, W/m3."""
    return 1000 * (10 * b_tesla) ** coef['a'] * (coef['b'] * f_hz / 1000 +
                                                 coef['c'] * (f_hz / 1000) ** coef['d'])


def load_mas_tdg(ndjson):
    out = {}
    for line in open(ndjson, encoding='utf-8'):
        rec = json.loads(line)
        if (rec.get('manufacturerInfo') or {}).get('name') != 'TDG':
            continue
        losses = rec.get('volumetricLosses')
        if not isinstance(losses, dict):
            continue
        for entry in losses.get('default', []):
            if isinstance(entry, dict) and entry.get('method') == 'tdg':
                out[rec['name']] = entry
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', help='the TDG metal-powder-core catalogue PDF')
    ap.add_argument('--audit', action='store_true',
                    help='compare data/core_materials.ndjson to the digitized charts')
    ap.add_argument('--db', default='data/core_materials.ndjson')
    ap.add_argument('--json', help='write the digitized curves + fits here')
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    charts, fits = {}, {}
    for i in range(doc.page_count):
        if 'Core Loss (mW/cm3)' not in doc[i].get_text():
            continue
        for title, curves in digitize_page(doc, i):
            charts[title] = curves
            fits[title] = fit_chart(curves) if args.audit or args.json else None
            if not args.audit:
                print('=== p%-3d %s' % (i, title))
                for f, poly in curves:
                    print('    %6.0f kHz  %.4g..%.4g G   P(100 mT) = %8.1f kW/m3'
                          % (f / 1e3, poly[0][0], poly[-1][0], at_1000_gauss(poly)))
    if not charts:
        sys.exit('no loss charts found in %s' % args.pdf)

    if args.json:
        json.dump({t: dict(curves=[[f, p] for f, p in c], fit=fits[t])
                   for t, c in charts.items()}, open(args.json, 'w'), indent=1)

    if not args.audit:
        return

    chart_of = {}
    for title in charts:
        family, grades = title.split(' ', 1)
        for grade in grades.split(','):
            chart_of['%s %d' % (family, int(grade.rstrip('μ')))] = title

    stored = load_mas_tdg(args.db)
    print('%-10s %-24s %7s %7s %7s %7s  per-frequency stored/catalogue'
          % ('material', 'chart', 'a_MAS', 'a_TDG', 'ref', 'geo-rms'))
    for name in sorted(stored, key=lambda n: (n.split()[0], int(n.split()[1]))):
        title = chart_of.get(name)
        if title is None:
            print('%-10s %-24s  (TDG publishes no loss chart for this grade)   '
                  'stored P(50 kHz, 100 mT) = %.0f kW/m3'
                  % (name, '-', predict(stored[name], 5e4, 0.1) / 1000))
            continue
        ratios = [predict(stored[name], f, 0.1) / 1000 / at_1000_gauss(poly)
                  for f, poly in charts[title]]
        ref = dict((f, r) for (f, _), r in zip(charts[title], ratios)).get(5e4, float('nan'))
        geo = math.exp(math.sqrt(sum(math.log(r) ** 2 for r in ratios) / len(ratios)))
        print('%-10s %-24s %7.4f %7.4f %7.2f %7.2f  %s'
              % (name, title, stored[name]['a'], fits[title]['a'], ref, geo,
                 ' '.join('%.2f' % r for r in ratios)))


if __name__ == '__main__':
    main()
