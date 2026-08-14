#!/usr/bin/env python3
"""Audit every Steinmetz loss model against the evidence MAS actually holds for it.

scripts/check-loss-sanity.py asks whether a model is PHYSICALLY plausible. This asks the
different question of whether it is IDENTIFIABLE: given the measured points backing each
frequency range, could the coefficients that range carries have been determined at all?
A model can reproduce every point it was fitted to and still be arbitrary everywhere else.

Four checks, each of which found real defects (ABT #640, #645):

  LOCUS      A range whose points carry fewer than 2 distinct flux densities at EVERY
             single frequency determines k, alpha and beta only along a line in
             (alpha, beta). DMR52's beta = 1.13 and DMR28's beta = 1.0005 are both this.

  BOUND      An exponent sitting on refit-steinmetz.py's own optimiser bound is the
             constraint talking, not the data. Always read together with LOCUS.

  CT         ct(T) = ct2*T^2 - ct1*T + ct0 is a parabola. With the house ct(25 C) = 1
             normalisation it needs 3 distinct temperatures; 2 determine only a line
             (propose ct2 = 0, ABT #708) and 1 determines nothing at all. Ranges with NO
             in-range points are reported separately and are NOT a defect on their own —
             their coefficients simply never came from MAS points.

  RANGE      A declared outer edge far beyond the first/last measured frequency claims a
             warranty the file has no data for. Only the OUTER edges of the first and last
             range are checked; interior boundaries must stay contiguous or MKF throws.

Deliberately does NOT apply refit-steinmetz's MagNet-preference filter: the question here
is what evidence EXISTS, not which subset a refit would choose. That filter is why
3C90/3C94/3F4 range 2 look empty when they carry 16 Ferroxcube points over 4 temperatures.

Usage:  python3 scripts/audit-loss-identifiability.py [--root DIR] [--check locus|bound|ct|range]
Exit status is always 0: this is a report, not a gate.
"""
import argparse
import json
import os
import sys

# refit-steinmetz.py's optimiser bounds; an exponent landing here is unconstrained.
ALPHA_LO, ALPHA_HI = 0.5, 3.5
BETA_LO, BETA_HI = 1.0, 4.5
BOUND_TOL = 1e-3
RANGE_RATIO = 1.5       # only report an edge overstated by this factor or more


def load_points(root):
    """name -> [(f, B, T)] from advanced_core_materials.ndjson, streamed.

    The advanced file is ~137 MB of git-LFS: read it line by line and keep only the three
    numbers each point contributes, never the parsed record.
    """
    out = {}
    path = os.path.join(root, 'data', 'advanced_core_materials.ndjson')
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            if not line.strip() or line.startswith('version https'):
                continue
            rec = json.loads(line)
            bucket = out.setdefault(rec['name'], [])
            for key in ('volumetricLosses', 'massLosses'):
                block = rec.get(key)
                if not isinstance(block, dict):
                    continue
                for method in block.get('default', []):
                    if not isinstance(method, list):
                        continue
                    for p in method:
                        try:
                            exc = p['magneticFluxDensity']
                            bucket.append((exc['frequency'],
                                           exc['magneticFluxDensity']['processed']['peak'],
                                           p['temperature']))
                        except (KeyError, TypeError):
                            continue
    return out


def base_points(rec):
    out = []
    for key in ('volumetricLosses', 'massLosses'):
        block = rec.get(key)
        if not isinstance(block, dict):
            continue
        for method in block.get('default', []):
            if not isinstance(method, list):
                continue
            for p in method:
                try:
                    exc = p['magneticFluxDensity']
                    out.append((exc['frequency'],
                                exc['magneticFluxDensity']['processed']['peak'],
                                p['temperature']))
                except (KeyError, TypeError):
                    continue
    return out


def steinmetz(rec):
    vl = rec.get('volumetricLosses')
    if not isinstance(vl, dict):
        return None
    return next((m for m in vl.get('default', [])
                 if isinstance(m, dict) and m.get('method') == 'steinmetz'), None)


def at_bound(value, lo, hi):
    if value is None:
        return None
    if abs(value - lo) <= BOUND_TOL:
        return f'lower bound {lo}'
    if abs(value - hi) <= BOUND_TOL:
        return f'upper bound {hi}'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--check', action='append', default=[],
                    choices=['locus', 'bound', 'ct', 'range'],
                    help='restrict to one or more checks (default: all)')
    args = ap.parse_args()
    wanted = set(args.check) or {'locus', 'bound', 'ct', 'range'}

    adv = load_points(args.root)
    materials = [json.loads(l) for l in
                 open(os.path.join(args.root, 'data', 'core_materials.ndjson'),
                      encoding='utf-8') if l.strip()]

    locus, bound, ct_few, ct_none, over = [], [], [], [], []
    for rec in materials:
        name = rec['name']
        meth = steinmetz(rec)
        if meth is None:
            continue
        pts = adv.get(name, []) + base_points(rec)
        pts = [p for p in pts if p[0] > 0 and p[1] > 0]
        ranges = meth['ranges']
        for i, r in enumerate(ranges):
            lo, hi = r['minimumFrequency'], r['maximumFrequency']
            sub = [p for p in pts if lo <= p[0] <= hi]
            tag = f'{name} range {i}/{len(ranges)} [{lo:.4g},{hi:.4g}]'

            if sub:
                by_f = {}
                for f, B, T in sub:
                    by_f.setdefault(round(f, 6), set()).add(round(B, 6))
                if max(len(v) for v in by_f.values()) < 2:
                    all_b = sorted({b for v in by_f.values() for b in v})
                    locus.append((tag, len(sub), sorted(by_f), all_b,
                                  r.get('alpha'), r.get('beta')))

            for label, value, bounds in (('alpha', r.get('alpha'), (ALPHA_LO, ALPHA_HI)),
                                         ('beta', r.get('beta'), (BETA_LO, BETA_HI))):
                hit = at_bound(value, *bounds)
                if hit:
                    bound.append((tag, label, value, hit, len(sub)))

            if all(r.get(k) is not None for k in ('ct0', 'ct1', 'ct2')):
                temps = sorted({round(p[2], 1) for p in sub})
                if not sub:
                    ct_none.append(tag)
                elif len(temps) < 3:
                    ct100 = r['ct2'] * 1e4 - r['ct1'] * 100 + r['ct0']
                    ct_few.append((tag, len(sub), temps, ct100))

        if pts:
            f_lo, f_hi = min(p[0] for p in pts), max(p[0] for p in pts)
            first, last = ranges[0], ranges[-1]
            if (first['minimumFrequency'] <= f_lo <= first['maximumFrequency']
                    and first['minimumFrequency'] > 0
                    and f_lo / first['minimumFrequency'] >= RANGE_RATIO):
                over.append((f'{name} range 0/{len(ranges)}', 'minimumFrequency',
                             first['minimumFrequency'], f_lo,
                             f_lo / first['minimumFrequency']))
            if (last['minimumFrequency'] <= f_hi <= last['maximumFrequency']
                    and f_hi > 0 and last['maximumFrequency'] / f_hi >= RANGE_RATIO):
                over.append((f'{name} range {len(ranges)-1}/{len(ranges)}',
                             'maximumFrequency', last['maximumFrequency'], f_hi,
                             last['maximumFrequency'] / f_hi))

    def header(title):
        print()
        print('=' * 100)
        print(title)
        print('=' * 100)

    if 'locus' in wanted:
        header('LOCUS — no single frequency carries 2+ distinct flux densities (ABT #640)')
        for tag, n, freqs, bs, a, b in sorted(locus):
            print(f'  {tag}')
            print(f'      n={n}  frequencies={[f"{f/1e6:g}MHz" for f in freqs]}  '
                  f'B values={bs}  alpha={a:.4f} beta={b:.4f}')
        print(f'  {len(locus)} range(s). Read each as "fitted AT these flux densities", '
              f'not as a model over a plane.')

    if 'bound' in wanted:
        header("BOUND — exponent sitting on refit-steinmetz.py's optimiser bound")
        for tag, label, value, hit, n in sorted(bound):
            print(f'  {tag}\n      {label}={value:.6f} is at the {hit} '
                  f'({n} in-range measured points)')
        print(f'  {len(bound)} exponent(s). A fit that lands on its own bound was not '
              f'constrained by the data.')

    if 'ct' in wanted:
        header('CT — temperature polynomial present but not identifiable (ABT #645, #708)')
        print('  Fewer than 3 distinct in-range temperatures:')
        for tag, n, temps, ct100 in sorted(ct_few):
            verdict = ('UNIDENTIFIABLE (1 temperature)' if len(temps) < 2
                       else 'curvature unidentifiable (2 temperatures) — see ABT #708')
            print(f'    {tag}\n        n={n} T={temps} ct(100)={ct100:.3f}  -> {verdict}')
        print(f'    {len(ct_few)} range(s).')
        print('\n  No in-range measured points at all — NOT a defect on its own, the')
        print('  coefficients simply did not come from MAS points; do not delete their ct:')
        for tag in sorted(ct_none):
            print(f'    {tag}')
        print(f'    {len(ct_none)} range(s).')

    if 'range' in wanted:
        header(f'RANGE — declared outer edge >= {RANGE_RATIO}x beyond the measured span')
        for tag, edge, declared, data, ratio in sorted(over, key=lambda x: -x[4]):
            print(f'  {tag:<34} {edge}: declared {declared:>12.4g} Hz, '
                  f'data {data:>11.4g} Hz  ({ratio:.4g}x)')
        print(f'  {len(over)} edge(s). scripts/refit-steinmetz.py --narrow-ranges pulls '
              f'them back;\n  MKF falls back to the nearest-end range '
              f'(CoreLosses.cpp), so narrowing never makes a request fail.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
