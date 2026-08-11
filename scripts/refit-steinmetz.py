#!/usr/bin/env python3
"""Refit MAS Steinmetz loss models from the measured points, with a ct(T) that cannot go negative.

MKF evaluates  P = k*f^alpha*B^beta * ct(T),  ct(T) = ct2*T^2 - ct1*T + ct0  (CoreLosses.h sign
convention), and SKIPS the ct factor entirely when ct(T) <= 0 — so a fit whose ct dips negative
anywhere in the operating band silently loses its temperature dependence there. The unconstrained
6-parameter fits in MKF2/src/tools/steinmetz.py produce exactly that: a k<->ct0 scale degeneracy
lets the optimiser settle on a DOWNWARD parabola (ct2 < 0), which always crosses zero.

The fix here is to parameterise ct as an upward parabola with a positive minimum,

    ct(T) = a*(T - h)^2 + m,    a >= 0,  m > 0     ->   ct2 = a, ct1 = 2*a*h, ct0 = a*h^2 + m

which is also the physically right shape: volumetric loss in a power ferrite has a minimum near
80-100 C and rises on both sides. Positivity is then structural, not something to be checked after.

Pipeline per frequency range (mirrors the house two-stage method, ABT #183):
  1. k/alpha/beta by linear least squares in log space on a near-25 C slice (|T-25| <= 3 C; the
     older `temperature == 25` exact match silently produced an EMPTY slice on DMEGC data whose
     temperatures read 26.7 C, which is where the garbage fits came from).
  2. a/h/m on all points with k/alpha/beta held.
  3. joint refinement of all six, bounded to the physical exponent band.
  4. normalise to ct(25 C) = 1 (rescale k, divide the cts) — identical predictions, sane k, and
     bounded damage if a future edit ever does trip the ct<=0 guard.

Ranges are also narrowed to the span the points actually cover: the outer edges move in to the
first/last measured frequency, interior boundaries are left alone so the ranges stay contiguous
(MKF throws on an interior gap). Ranges with no points at all are dropped only when they are not
interior.

Usage:  python3 scripts/refit-steinmetz.py --list
        python3 scripts/refit-steinmetz.py --material N88 [--material 3C99 ...] [--apply]
        python3 scripts/refit-steinmetz.py --failing [--apply]      # everything failing a gate
        python3 scripts/refit-steinmetz.py --narrow-ranges [--apply]  # bounds only, no refit
Without --apply nothing is written; the fit and its error are printed for review.
"""
import argparse, json, math, sys
import numpy as np
from scipy.optimize import least_squares

DATA = 'data/core_materials.ndjson'
ADVANCED = 'data/advanced_core_materials.ndjson'

ALPHA_LO, ALPHA_HI = 0.5, 3.5
BETA_LO, BETA_HI = 1.0, 4.5
OPERATING_TSPAN = (-40, 140)
MIN_POINTS = 8          # below this a 3-parameter power law is not identifiable
REF_T = 25.0


# ---------------------------------------------------------------- data loading
def load_records(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    return lines, [json.loads(l) if l.strip() else None for l in lines]


def loss_points(name, base_by_name, adv_by_name):
    """Measured Pv points for a material: [(f, B, T, Pv)], preferring MagNet where mixed.

    Points arrive in either of the two forms the schema defines: `volumetricLosses` in W/m^3 and
    `massLosses` in W/kg. The latter is what the tape-wound, amorphous and nanocrystalline records
    carry (their vendors publish loss per unit mass), and it is just as fittable once multiplied by
    the material density — the Steinmetz model MKF evaluates is volumetric, so mass points that are
    never converted look to this script like a material with no data at all. That is how AF ended up
    with a beta of 0.946 while 289 clean measured points sat in the file unused (ABT #643).
    """
    raw = []
    sources = list(adv_by_name.get(name, []))
    if name in base_by_name:
        sources.append(base_by_name[name])
    density = base_by_name.get(name, {}).get('density')
    for src in sources:
        for key, scale in (('volumetricLosses', 1.0), ('massLosses', density)):
            block = src.get(key)
            if not isinstance(block, dict):
                continue
            for method in block.get('default', []):
                if not isinstance(method, list) or not method:
                    continue
                if scale is None:
                    # No density, no conversion. Guessing one would put a made-up factor straight
                    # into k, so this is an error, not something to quietly skip.
                    raise ValueError(f"{name}: massLosses points (W/kg) but no density in "
                                     f"{DATA} — cannot convert to the volumetric W/m^3 the "
                                     f"Steinmetz model is fitted in")
                raw.extend((p, scale) for p in method)
    if any(p.get('origin') == 'MagNet' for p, _ in raw):
        raw = [(p, s) for p, s in raw if p.get('origin') == 'MagNet']
    out = []
    for p, scale in raw:
        try:
            exc = p['magneticFluxDensity']
            f = exc['frequency']
            B = exc['magneticFluxDensity']['processed']['peak']
            out.append((f, B, p['temperature'], p['value'] * scale))
        except (KeyError, TypeError):
            continue
    return [r for r in out if r[0] > 0 and r[1] > 0 and r[3] > 0]


# ---------------------------------------------------------------- the fit
def _ct(T, a, h, m):
    return a * (T - h) ** 2 + m


def _predict_log10(p, f, B, T):
    log_k, alpha, beta, a, h, log_m = p
    return (log_k + alpha * np.log10(f) + beta * np.log10(B)
            + np.log10(_ct(T, a, h, math.exp(log_m))))


def fit_range(points):
    """Fit one frequency range. Returns (coefficients dict, mean |relative error|)."""
    f = np.array([p[0] for p in points], float)
    B = np.array([p[1] for p in points], float)
    T = np.array([p[2] for p in points], float)
    P = np.array([p[3] for p in points], float)
    y = np.log10(P)

    # --- stage 1: k/alpha/beta on one temperature slice. Pick the slice carrying the most
    # distinct (f, B) pairs rather than always reaching for 25 C: alpha and beta are only
    # identifiable where the data spreads over frequency AND flux density, and some sources
    # (Ferroxcube's Pv-vs-B figure, for one) draw that spread at 100 C and give temperature
    # only as a few separate curves. Ties break toward 25 C. The older `temperature == 25`
    # exact match silently emptied the slice on DMEGC data whose temperatures read 26.7 C.
    def slice_score(t0):
        sel = np.abs(T - t0) <= 3.0
        return (len({(round(a, 6), round(b, 6)) for a, b in zip(f[sel], B[sel])}),
                -abs(t0 - REF_T))
    best = max(sorted(set(T.tolist())), key=slice_score)
    near = np.abs(T - best) <= 3.0
    if near.sum() < 4:
        near = np.ones_like(T, dtype=bool)
    A = np.column_stack([np.ones(near.sum()), np.log10(f[near]), np.log10(B[near])])
    (log_k0, alpha0, beta0), *_ = np.linalg.lstsq(A, y[near], rcond=None)

    # --- no ct at all unless the data can identify one. ct is a parabola in T: three parameters,
    # so it needs at least three distinct temperatures. Below that the ct stages below are fitting
    # an unconstrained direction and will happily return their own initial guess dressed up as a
    # temperature dependence — AF's 289 points are all at 25 C and produced ct(100)=0.81, a 19%
    # loss DROP with heating that nothing in the file says (ABT #643). Omitting ct0/ct1/ct2 is a
    # meaningful state: MKF's apply_temperature_coefficients requires all three and otherwise
    # applies no scaling at all, which is exactly the right behaviour for single-temperature data.
    temperatures = sorted(set(T.tolist()))
    if len(temperatures) < 3:
        A_all = np.column_stack([np.ones(len(f)), np.log10(f), np.log10(B)])
        (log_k, alpha, beta), *_ = np.linalg.lstsq(A_all, y, rcond=None)
        k = 10 ** log_k
        pred = k * f ** alpha * B ** beta
        err = float(np.mean(np.abs(pred - P) / P))
        return ({'k': float(k), 'alpha': float(alpha), 'beta': float(beta)}, err)

    # --- stage 2: ct only, k/alpha/beta held
    def resid_ct(q):
        a, h, log_m = q
        return _predict_log10([log_k0, alpha0, beta0, a, h, log_m], f, B, T) - y
    s2 = least_squares(resid_ct, [1e-4, 80.0, 0.0],
                       bounds=([0.0, -50.0, -8.0], [1.0, 250.0, 8.0]))

    # --- stage 3: joint refinement, exponents bounded to the physical band
    def resid_all(q):
        return _predict_log10(q, f, B, T) - y
    p0 = [log_k0, alpha0, beta0, *s2.x]
    lo = [-40.0, ALPHA_LO, BETA_LO, 0.0, -50.0, -8.0]
    hi = [40.0, ALPHA_HI, BETA_HI, 1.0, 250.0, 8.0]
    p0 = [min(max(v, l), u) for v, l, u in zip(p0, lo, hi)]
    s3 = least_squares(resid_all, p0, bounds=(lo, hi))
    log_k, alpha, beta, a, h, log_m = s3.x
    m = math.exp(log_m)

    # --- stage 4: normalise so ct(25 C) = 1
    c25 = _ct(REF_T, a, h, m)
    k = (10 ** log_k) * c25
    a, m = a / c25, m / c25
    ct2, ct1, ct0 = a, 2 * a * h, a * h * h + m

    pred = k * f ** alpha * B ** beta * (ct2 * T * T - ct1 * T + ct0)
    err = float(np.mean(np.abs(pred - P) / P))
    return ({'k': float(k), 'alpha': float(alpha), 'beta': float(beta),
             'ct0': float(ct0), 'ct1': float(ct1), 'ct2': float(ct2)}, err)


def model_error(coeffs, points):
    """Mean |relative error| of an existing coefficient set over the same points, MKF semantics."""
    if not points:
        return None
    # MKF applies the temperature term only when all three coefficients are present
    # (CoreLosses.h apply_temperature_coefficients), and only when it comes out positive.
    has_ct = all(coeffs.get(key) is not None for key in ('ct0', 'ct1', 'ct2'))
    tot = 0.0
    for f, B, T, P in points:
        p = coeffs['k'] * f ** coeffs['alpha'] * B ** coeffs['beta']
        if has_ct:
            scale = coeffs['ct2'] * T * T - coeffs['ct1'] * T + coeffs['ct0']
            if scale > 0:
                p *= scale
        tot += abs(p - P) / P
    return tot / len(points)


def ct_dead_in_band(c):
    if any(c.get(key) is None for key in ('ct0', 'ct1', 'ct2')):
        return False           # a range with no ct simply has no temperature scaling to lose
    for T in range(OPERATING_TSPAN[0], OPERATING_TSPAN[1] + 1, 5):
        if c['ct2'] * T * T - c['ct1'] * T + c['ct0'] <= 0:
            return True
    return False


def gates(c):
    bad = []
    if c.get('alpha') is not None and not (ALPHA_LO <= c['alpha'] <= ALPHA_HI):
        bad.append(f"alpha={c['alpha']:.3g}")
    if c.get('beta') is not None and not (BETA_LO <= c['beta'] <= BETA_HI):
        bad.append(f"beta={c['beta']:.3g}")
    if ct_dead_in_band(c):
        bad.append('ct(T)<=0 in the operating band')
    return bad


# ---------------------------------------------------------------- per material
def refit_material(rec, points, narrow_only=False):
    """Return (new_method, report_lines) or (None, report_lines) if nothing should change."""
    vl = rec.get('volumetricLosses')
    report = []
    if not isinstance(vl, dict):
        return None, report
    method = next((m for m in vl.get('default', [])
                   if isinstance(m, dict) and m.get('method') == 'steinmetz'), None)
    if method is None:
        return None, report
    fmin_data = min(p[0] for p in points)
    fmax_data = max(p[0] for p in points)

    # No range is ever DROPPED. A range with no points in MAS is not thereby baseless — its
    # coefficients may well come from vendor curves that were never imported as points — and
    # deleting it would silently change what MKF evaluates above/below the measured span. Only
    # the outer EDGES move, and only inward onto measured ground; interior boundaries are left
    # exactly where they are, because MKF throws on a gap between ranges.
    old_ranges = method['ranges']
    new_ranges = []
    for i, r in enumerate(old_ranges):
        nr = dict(r)
        first_with_data = (i == 0 and nr['minimumFrequency'] <= fmin_data <= nr['maximumFrequency'])
        last_with_data = (i == len(old_ranges) - 1
                          and nr['minimumFrequency'] <= fmax_data <= nr['maximumFrequency'])
        if first_with_data and nr['minimumFrequency'] < fmin_data:
            report.append(f"    range {i}: minimumFrequency {nr['minimumFrequency']:.4g} ->"
                          f" {fmin_data:.4g} Hz (first measured point)")
            nr['minimumFrequency'] = fmin_data
        if last_with_data and nr['maximumFrequency'] > fmax_data:
            report.append(f"    range {i}: maximumFrequency {nr['maximumFrequency']:.4g} ->"
                          f" {fmax_data:.4g} Hz (last measured point)")
            nr['maximumFrequency'] = fmax_data
        if not narrow_only:
            sub = [p for p in points
                   if nr['minimumFrequency'] <= p[0] <= nr['maximumFrequency']]
            if len(sub) < MIN_POINTS:
                report.append(f"    range {i} [{nr['minimumFrequency']:.4g},"
                              f"{nr['maximumFrequency']:.4g}]: only {len(sub)} points, kept as-is")
            else:
                new, err = fit_range(sub)
                old_err = model_error(r, sub)
                bad = gates(new)
                ct_tag = ('no ct (single-temperature data)' if 'ct0' not in new else
                          f"ct(25)=1 ct(100)={new['ct2']*1e4 - new['ct1']*100 + new['ct0']:.3f}")
                tag = (f"    range {i} [{nr['minimumFrequency']:.4g},{nr['maximumFrequency']:.4g}] "
                       f"n={len(sub)}: k={new['k']:.4g} a={new['alpha']:.3f} b={new['beta']:.3f} "
                       f"{ct_tag} | err {old_err*100:.1f}% -> {err*100:.1f}%")
                # A range whose old ct was dead in the operating band was structurally broken —
                # its apparent error was measured with the temperature scaling dropped, so it is
                # not a bar the replacement has to clear. Anywhere else, refuse to trade accuracy
                # on the measured points for tidier coefficients.
                was_broken = ct_dead_in_band(r)
                worse = old_err is not None and err > max(old_err * 1.25, old_err + 0.02)
                if bad:
                    report.append(tag + f"  REJECTED ({'; '.join(bad)})")
                elif worse and not was_broken:
                    report.append(tag + "  REJECTED (fits the measured points worse)")
                else:
                    report.append(tag + ("  (old ct was dead in band)" if was_broken and worse else ""))
                    if 'ct0' not in new:
                        # An old ct must not outlive the fit it belonged to: left in place next to
                        # new k/alpha/beta it would scale a curve it was never fitted against.
                        for key in ('ct0', 'ct1', 'ct2'):
                            nr.pop(key, None)
                    nr.update(new)
        new_ranges.append(nr)

    # Narrowing must never collapse a range onto a point (data ending exactly on the 1 MHz edge
    # would leave [1e6,1e6]) nor open an interior gap — MKF throws on gaps, and a zero-width
    # range is unreachable. Either means the edge move was wrong: undo it.
    for i, (nr, r) in enumerate(zip(new_ranges, old_ranges)):
        if nr['maximumFrequency'] <= nr['minimumFrequency']:
            report.append(f"    range {i}: narrowing would collapse it to zero width — reverted "
                          f"to [{r['minimumFrequency']:.4g},{r['maximumFrequency']:.4g}] Hz")
            new_ranges[i] = dict(r, **{k: v for k, v in nr.items()
                                       if k not in ('minimumFrequency', 'maximumFrequency')})
    for a_, b_ in zip(new_ranges, new_ranges[1:]):
        # Only a true GAP matters. Several records deliberately overlap consecutive ranges by
        # 1 Hz ([1, 100001] then [100000, 300001]) so that MKF's "first range containing f"
        # always has a winner at the boundary; that is not a gap.
        if b_['minimumFrequency'] - a_['maximumFrequency'] > max(1.0, 1e-6 * a_['maximumFrequency']):
            report.append(f"    !! interior gap {a_['maximumFrequency']:.4g}->"
                          f"{b_['minimumFrequency']:.4g} Hz — MKF throws on those, leaving alone")
            return None, report

    if new_ranges == old_ranges:
        return None, report
    out = dict(method)
    out['ranges'] = new_ranges
    return out, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--material', action='append', default=[])
    ap.add_argument('--failing', action='store_true',
                    help='every steinmetz model failing an exponent or ct gate')
    ap.add_argument('--narrow-ranges', action='store_true',
                    help='only pull declared range bounds back to the measured span')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    lines, recs = load_records(DATA)
    base_by_name = {r['name']: r for r in recs if r}
    adv_by_name = {}
    for l in open(ADVANCED, encoding='utf-8'):
        if l.strip():
            p = json.loads(l)
            adv_by_name.setdefault(p['name'], []).append(p)

    targets = list(args.material)
    if args.failing or args.narrow_ranges:
        for r in recs:
            if not r:
                continue
            vl = r.get('volumetricLosses')
            if not isinstance(vl, dict):
                continue
            meth = next((m for m in vl.get('default', [])
                         if isinstance(m, dict) and m.get('method') == 'steinmetz'), None)
            if meth is None:
                continue
            if args.narrow_ranges or any(gates(rg) for rg in meth['ranges']):
                targets.append(r['name'])
    targets = sorted(set(targets))

    changed = 0
    skipped_no_points = []
    for name in targets:
        rec = base_by_name.get(name)
        if rec is None:
            print(f"{name}: not in {DATA}")
            continue
        points = loss_points(name, base_by_name, adv_by_name)
        if len(points) < MIN_POINTS:
            skipped_no_points.append(name)
            continue
        new, report = refit_material(rec, points, narrow_only=args.narrow_ranges)
        if not report:
            continue
        print(f"{name} ({len(points)} points)")
        for line in report:
            print(line)
        if new is not None:
            rec['volumetricLosses']['default'] = [
                new if (isinstance(m, dict) and m.get('method') == 'steinmetz') else m
                for m in rec['volumetricLosses']['default']]
            idx = next(i for i, r in enumerate(recs) if r is rec)
            lines[idx] = json.dumps(rec, ensure_ascii=False)
            changed += 1

    if skipped_no_points:
        print(f"\n{len(skipped_no_points)} materials have no usable measured points "
              f"and cannot be refitted: {', '.join(skipped_no_points)}")
    print(f"\n{changed} materials changed"
          + (' (written)' if args.apply and changed else ' (dry run, nothing written)'))
    if args.apply and changed:
        open(DATA, 'w', encoding='utf-8').write('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
