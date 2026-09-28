#!/usr/bin/env python3
"""Refit MAS Steinmetz loss models from the measured points, with a ct(T) that cannot go negative.

MKF evaluates  P = k*f^alpha*B^beta * ct(T),  ct(T) = ct2*T^2 - ct1*T + ct0  (CoreLosses.h sign
convention). A missing ct0/ct1/ct2 takes its schema default (ct0=1, ct1=0, ct2=0; ABT #1456), and
MKF THROWS when ct(T) <= 0 (it used to skip the ct factor silently) — so a fit whose ct dips
negative anywhere in the operating band makes MKF refuse to evaluate the material there. The unconstrained
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
        python3 scripts/refit-steinmetz.py --material 3C90 --below-span manufacturer \
            --cap-at-published [--apply]   # MagNet governs its band; the maker's MDS curves add
                                            # a range below MagNet's 50 kHz, joined to it with no
                                            # step; the model ends at the last point
        python3 scripts/refit-steinmetz.py --material 3F4 --range-origin 2=manufacturer ...
                                            # refit range 2 only, joined to unchanged neighbours
        python3 scripts/refit-steinmetz.py --material ML27D --cap-at 1e6 [--apply]
                                            # no points in MAS: end at the maker's last frequency
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
MIN_POINTS_JOINED = 4   # a range joined to a fixed neighbour: the edge pins k/alpha/beta at the
                        # edge frequency over B, so one maker curve (>= 3 flux densities) at
                        # another frequency identifies alpha (3F4: one 25 kHz line at 100 C)
REF_T = 25.0


# ---------------------------------------------------------------- data loading
def load_records(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    return lines, [json.loads(l) if l.strip() else None for l in lines]


def loss_points(name, base_by_name, adv_by_name, origin=None):
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
    if origin is not None:
        # An explicit source (--range-origin) is taken as asked, without the MagNet preference.
        raw = [(p, s) for p, s in raw if p.get('origin') == origin]
    elif any(p.get('origin') == 'MagNet' for p, _ in raw):
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


def ct_scale(coeffs, T):
    """MKF's temperature factor (CoreLosses.h, ABT #1456): each missing ct coefficient takes its
    schema default (ct0=1, ct1=0, ct2=0), and a non-positive factor is an error, not something to
    drop — MKF throws there, so this does too."""
    ct0 = coeffs.get('ct0')
    ct1 = coeffs.get('ct1')
    ct2 = coeffs.get('ct2')
    ct0 = 1.0 if ct0 is None else ct0
    ct1 = 0.0 if ct1 is None else ct1
    ct2 = 0.0 if ct2 is None else ct2
    return ct2 * T * T - ct1 * T + ct0


def model_error(coeffs, points):
    """Mean |relative error| of an existing coefficient set over the same points, MKF semantics."""
    if not points:
        return None
    tot = 0.0
    for f, B, T, P in points:
        scale = ct_scale(coeffs, T)
        if scale <= 0:
            raise ValueError(f"ct(T={T} C) = {scale:.4g} <= 0 for range "
                             f"[{coeffs.get('minimumFrequency')}, {coeffs.get('maximumFrequency')}] Hz"
                             f" — MKF throws on this; the range must be refitted")
        p = coeffs['k'] * f ** coeffs['alpha'] * B ** coeffs['beta'] * scale
        tot += abs(p - P) / P
    return tot / len(points)


def ct_dead_in_band(c):
    for T in range(OPERATING_TSPAN[0], OPERATING_TSPAN[1] + 1, 5):
        if ct_scale(c, T) <= 0:
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
def _cap_to_published(ranges, fmax, report):
    out = [dict(r) for r in ranges]
    while len(out) > 1 and out[-1]['minimumFrequency'] >= fmax:
        r = out.pop()
        report.append(f"    range {len(out)} [{r['minimumFrequency']:.4g},{r['maximumFrequency']:.4g}] Hz"
                      f" dropped: it lies above the last published point ({fmax:.4g} Hz)")
    if out[-1]['maximumFrequency'] > fmax:
        report.append(f"    range {len(out) - 1}: maximumFrequency {out[-1]['maximumFrequency']:.4g} ->"
                      f" {fmax:.4g} Hz (last published point)")
        out[-1]['maximumFrequency'] = fmax
    if out[-1]['maximumFrequency'] <= out[-1]['minimumFrequency']:
        raise ValueError(f"capping collapses range {len(out) - 1} to zero width")
    return out


SEAM_T = (0.0, 25.0, 50.0, 70.0, 90.0, 100.0, 120.0)
SEAM_WEIGHT = 10.0


def _log10_model(c, f, B, T):
    scale = ct_scale(c, T)
    if scale <= 0:
        return 50.0
    return math.log10(c['k']) + c['alpha'] * math.log10(f) + c['beta'] * math.log10(B) + math.log10(scale)


def fit_range_seamed(points, seams, held_ct=None, weight=SEAM_WEIGHT):
    """Fit one range to its points AND to its fixed neighbours at the shared edges.

    seams: [(f_edge, neighbour coefficients, B grid)]. The neighbour is not refitted: it is the
    better-sourced model (MagNet's measurements) and governs its own band. The residual is the
    log10 error on the points plus, at every edge, the log10 difference between this range and
    the neighbour at f_edge over the B grid and the SEAM_T temperatures, weighted so that the
    edge counts `weight` times the points' RMS (scripts in the style of the triage joint fit).
    Independently fitted ranges disagree at their shared edge, which is a step in loss vs f.

    ct: a parabola when the points carry >= 3 temperatures; otherwise the neighbour's ct shape
    (held_ct) is kept and only k/alpha/beta move. Returns (coefficients, mean |rel err|,
    worst |step| at the edges over the grid)."""
    f = np.array([p[0] for p in points], float)
    B = np.array([p[1] for p in points], float)
    T = np.array([p[2] for p in points], float)
    P = np.array([p[3] for p in points], float)
    y = np.log10(P)
    free_ct = len(set(T.tolist())) >= 3
    if not free_ct and held_ct is None:
        raise ValueError("fewer than 3 temperatures and no neighbour ct shape to hold")
    grid = [(fe, nb, Bs, Ts) for fe, nb, Bgrid in seams for Bs in Bgrid for Ts in SEAM_T]
    ws = weight * math.sqrt(len(points) / max(1, len(grid)))

    def coeffs(q):
        if free_ct:
            log_k, alpha, beta, a, h, log_m = q
            m = math.exp(log_m)
            c25 = _ct(REF_T, a, h, m)
            a_, m_ = a / c25, m / c25
            return {'k': 10 ** log_k * c25, 'alpha': alpha, 'beta': beta,
                    'ct0': a_ * h * h + m_, 'ct1': 2 * a_ * h, 'ct2': a_}
        log_k, alpha, beta = q
        return dict({'k': 10 ** log_k, 'alpha': alpha, 'beta': beta},
                    **{kk: held_ct[kk] for kk in ('ct0', 'ct1', 'ct2')})

    def res(q):
        c = coeffs(q)
        r = [_log10_model(c, fi, Bi, Ti) - yi for fi, Bi, Ti, yi in zip(f, B, T, y)]
        r += [ws * (_log10_model(c, fe, Bs, Ts) - _log10_model(nb, fe, Bs, Ts)) for fe, nb, Bs, Ts in grid]
        return r

    A = np.column_stack([np.ones(len(f)), np.log10(f), np.log10(B)])
    (lk, al, be), *_ = np.linalg.lstsq(A, y, rcond=None)
    al = min(max(al, ALPHA_LO + .01), ALPHA_HI - .01)
    be = min(max(be, BETA_LO + .01), BETA_HI - .01)
    if free_ct:
        q0, lo, hi = [lk, al, be, 1e-4, 80.0, 0.0], [-40, ALPHA_LO, BETA_LO, 0, -50, -8], [40, ALPHA_HI, BETA_HI, 1, 250, 8]
    else:
        lk -= float(np.mean(np.log10([ct_scale(held_ct, t) for t in T])))
        q0, lo, hi = [lk, al, be], [-40, ALPHA_LO, BETA_LO], [40, ALPHA_HI, BETA_HI]
    c = coeffs(least_squares(res, q0, bounds=(lo, hi)).x)
    c = {kk: float(v) for kk, v in c.items()}
    err = float(np.mean([abs(10 ** _log10_model(c, *p[:3]) / p[3] - 1) for p in points]))
    step = max((abs(10 ** (_log10_model(c, fe, Bs, Ts) - _log10_model(nb, fe, Bs, Ts)) - 1)
                for fe, nb, Bs, Ts in grid), default=0.0)
    return c, err, step


def _seam_B_grid(points_a, points_b):
    """5 flux densities inside the B span both sides were measured at (the whole span if the
    two do not overlap)."""
    ba = [p[1] for p in points_a]
    bb = [p[1] for p in points_b]
    lo, hi = max(min(ba), min(bb)), min(max(ba), max(bb))
    if hi <= lo:
        lo, hi = min(ba + bb), max(ba + bb)
    return list(np.geomspace(lo, hi, 5))


def _refit_overrides(rec, points, overrides, cap_published, below=None):
    report = []
    method = next(m for m in rec['volumetricLosses']['default']
                  if isinstance(m, dict) and m.get('method') == 'steinmetz')
    old_ranges = method['ranges']
    new_ranges = [dict(r) for r in old_ranges]
    measured = points  # the governing (MagNet-preferred) points of the unchanged ranges

    def in_range(pts, r):
        return [p for p in pts if r['minimumFrequency'] <= p[0] <= r['maximumFrequency']]

    for i, sub_all in sorted(overrides.items()):
        if i >= len(old_ranges):
            raise ValueError(f"range {i} does not exist ({len(old_ranges)} ranges)")
        nr = new_ranges[i]
        fs = [p[0] for p in sub_all]
        if i == 0 and min(fs) < nr['minimumFrequency']:
            report.append(f"    range 0: minimumFrequency {nr['minimumFrequency']:.4g} -> {min(fs):.4g} Hz"
                          f" (first override point)")
            nr['minimumFrequency'] = min(fs)
        if i == len(old_ranges) - 1 and max(fs) < nr['maximumFrequency']:
            report.append(f"    range {i}: maximumFrequency {nr['maximumFrequency']:.4g} -> {max(fs):.4g} Hz"
                          f" (last override point)")
            nr['maximumFrequency'] = max(fs)
        sub = [p for p in sub_all if nr['minimumFrequency'] <= p[0] <= nr['maximumFrequency']]
        if len(sub) < MIN_POINTS:
            raise ValueError(f"range {i}: only {len(sub)} override points")
        # Neighbours that are not refitted here govern their band; this range joins them.
        seams = []
        for j, edge in ((i - 1, 'minimumFrequency'), (i + 1, 'maximumFrequency')):
            if 0 <= j < len(old_ranges) and j not in overrides:
                nb_pts = in_range(measured, old_ranges[j])
                if nb_pts:
                    seams.append((nr[edge], old_ranges[j], _seam_B_grid(sub, nb_pts)))
        temps = sorted({p[2] for p in sub})
        if seams:
            held = old_ranges[i] if all(k in old_ranges[i] for k in ('ct0', 'ct1', 'ct2')) else None
            new, err, step = fit_range_seamed(sub, seams, held_ct=held)
            bad = gates(new)
            if bad:
                raise ValueError(f"range {i}: seamed refit fails the gates: {'; '.join(bad)}")
            old_err = None if ct_dead_in_band(old_ranges[i]) else model_error(old_ranges[i], sub)
            report.append(f"    range {i} [{nr['minimumFrequency']:.4g},{nr['maximumFrequency']:.4g}] "
                          f"n={len(sub)} T={temps[0]:g}..{temps[-1]:g}: k={new['k']:.4g} a={new['alpha']:.3f} "
                          f"b={new['beta']:.3f} | err on these points "
                          f"{'n/a' if old_err is None else f'{old_err*100:.1f}%'} -> {err*100:.1f}%"
                          f" | joined to the neighbour(s) at {', '.join(f'{s[0]:.4g}' for s in seams)} Hz,"
                          f" worst step {step*100:.2f}%")
            for key in ('ct0', 'ct1', 'ct2'):
                nr.pop(key, None)
            nr.update(new)
            continue
        new, err = fit_range(sub)
        note = ''
        if 'ct0' not in new and all(k in old_ranges[i] for k in ('ct0', 'ct1', 'ct2')):
            # The override curves sit at one temperature (Ferroxcube draws Pv-B at 100 C and its
            # Pv-T curves may all lie in another range). Keep the range's existing ct(T) SHAPE,
            # fitted on the measured points it had, and set k so that the model reproduces the
            # override curves at their temperature.
            c_ref = ct_scale(old_ranges[i], temps[0])
            new = dict(new, k=new['k'] / c_ref,
                       ct0=old_ranges[i]['ct0'], ct1=old_ranges[i]['ct1'], ct2=old_ranges[i]['ct2'])
            note = f" ct shape kept from the previous fit, anchored at {temps[0]:g} C"
        bad = gates(new)
        if bad:
            raise ValueError(f"range {i}: refit fails the gates: {'; '.join(bad)}")
        old_err = None if ct_dead_in_band(old_ranges[i]) else model_error(old_ranges[i], sub)
        report.append(f"    range {i} [{nr['minimumFrequency']:.4g},{nr['maximumFrequency']:.4g}] "
                      f"n={len(sub)} T={temps[0]:g}..{temps[-1]:g}: k={new['k']:.4g} a={new['alpha']:.3f} "
                      f"b={new['beta']:.3f} | err on these points "
                      f"{'n/a' if old_err is None else f'{old_err*100:.1f}%'} -> {err*100:.1f}%{note}")
        for key in ('ct0', 'ct1', 'ct2'):
            nr.pop(key, None)
        nr.update(new)
    if below:
        # The better source (MagNet) governs every frequency it measured; the maker's curves
        # extend the model only below its first range, with a new range that joins range 0.
        r0 = new_ranges[0]
        f0 = r0['minimumFrequency']
        sub = [p for p in below if p[0] <= f0]
        if len(sub) < MIN_POINTS_JOINED or len({round(p[1], 6) for p in sub}) < 3:
            raise ValueError(f"only {len(sub)} points below {f0:.4g} Hz to extend the model with")
        nb_pts = in_range(measured, r0)
        if not nb_pts:
            raise ValueError(f"range 0 has no governing points to join the new range to")
        held = r0 if all(k in r0 for k in ('ct0', 'ct1', 'ct2')) else None
        new, err, step = fit_range_seamed(sub, [(f0, r0, _seam_B_grid(sub, nb_pts))], held_ct=held)
        bad = gates(new)
        if bad:
            raise ValueError(f"new range below {f0:.4g} Hz fails the gates: {'; '.join(bad)}")
        fmin = min(p[0] for p in sub)
        temps = sorted({p[2] for p in sub})
        report.append(f"    new range 0 [{fmin:.4g},{f0:.4g}] n={len(sub)} T={temps[0]:g}..{temps[-1]:g}:"
                      f" k={new['k']:.4g} a={new['alpha']:.3f} b={new['beta']:.3f} | err on these points"
                      f" {err*100:.1f}% | joined to range 0 at {f0:.4g} Hz, worst step {step*100:.2f}%")
        new_ranges.insert(0, dict(new, minimumFrequency=float(fmin), maximumFrequency=float(f0)))
    # Contiguity: an extended first range must not overlap into nothing; interior edges stay.
    if cap_published:
        fmax = max([p[0] for p in points] + [p[0] for v in overrides.values() for p in v]
                   + [p[0] for p in (below or [])])
        new_ranges = _cap_to_published(new_ranges, fmax, report)
    out = dict(method)
    out['ranges'] = new_ranges
    return out, report


def refit_material(rec, points, narrow_only=False, overrides=None, cap_published=False, below=None):
    """Return (new_method, report_lines) or (None, report_lines) if nothing should change.

    overrides:     {range index: points} — refit ONLY these ranges, each from its own points
                   (--range-origin; e.g. the maker's datasheet curves where MagNet measured a
                   narrower band). The first range's lower edge moves out to the first override
                   point and the last range's upper edge to the last one: the maker's own curves
                   are measured ground. Every other range is left exactly as it is.
    below:         points of another source (--below-span) that extend the model below range 0
                   with a new range joined continuously to it; range 0 and up are kept. This is
                   how the maker's curves reach below MagNet's first frequency without
                   overriding MagNet where it measured.
    cap_published: the upper end of the model is the highest frequency any point covers. A
                   trailing range that starts at or above it (the [1 MHz, 1 GHz] placeholders
                   whose only reachable frequency is their lower edge, already covered by the
                   range below) is dropped; the new last range ends at that frequency."""
    if overrides or below:
        return _refit_overrides(rec, points, overrides or {}, cap_published, below=below)
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
                # A range whose old ct is dead in the operating band makes MKF throw there, so it
                # has no error to compare against (model_error raises on it, as MKF does).
                was_broken = ct_dead_in_band(r)
                old_err = None if was_broken else model_error(r, sub)
                bad = gates(new)
                ct_tag = ('no ct (single-temperature data)' if 'ct0' not in new else
                          f"ct(25)=1 ct(100)={new['ct2']*1e4 - new['ct1']*100 + new['ct0']:.3f}")
                tag = (f"    range {i} [{nr['minimumFrequency']:.4g},{nr['maximumFrequency']:.4g}] "
                       f"n={len(sub)}: k={new['k']:.4g} a={new['alpha']:.3f} b={new['beta']:.3f} "
                       f"{ct_tag} | err "
                       f"{'n/a (old ct dead in band)' if old_err is None else f'{old_err*100:.1f}%'}"
                       f" -> {err*100:.1f}%")
                # A range whose old ct was dead in the operating band was structurally broken, so
                # it is not a bar the replacement has to clear. Anywhere else, refuse to trade
                # accuracy on the measured points for tidier coefficients.
                worse = old_err is not None and err > max(old_err * 1.25, old_err + 0.02)
                if bad:
                    report.append(tag + f"  REJECTED ({'; '.join(bad)})")
                elif worse and not was_broken:
                    report.append(tag + "  REJECTED (fits the measured points worse)")
                else:
                    report.append(tag + ("  (old ct was dead in band)" if was_broken else ""))
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
    ap.add_argument('--range-origin', action='append', default=[], metavar='IDX=ORIGIN',
                    help='refit only range IDX, from the points of this origin (with --material)')
    ap.add_argument('--below-span', default=None, metavar='ORIGIN',
                    help='extend the model below range 0 with a new range fitted to the points of '
                         'this origin under range 0\'s lower edge, joined to range 0 (which is kept)')
    ap.add_argument('--cap-at-published', action='store_true',
                    help='end the model at the last point; drop trailing ranges above it')
    ap.add_argument('--cap-at', type=float, default=None, metavar='HZ',
                    help='end the model at HZ, the highest frequency the maker publishes loss for '
                         '(read off its datasheet; for records with no points in MAS). Trailing '
                         'ranges starting at or above it are dropped. Coefficients are not touched')
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
        if args.cap_at is not None:
            method = next(m for m in rec['volumetricLosses']['default']
                          if isinstance(m, dict) and m.get('method') == 'steinmetz')
            report = []
            capped = _cap_to_published(method['ranges'], args.cap_at, report)
            print(name)
            for line in report:
                print(line)
            if capped != method['ranges']:
                new = dict(method, ranges=capped)
                rec['volumetricLosses']['default'] = [
                    new if (isinstance(m, dict) and m.get('method') == 'steinmetz') else m
                    for m in rec['volumetricLosses']['default']]
                idx = next(i for i, r in enumerate(recs) if r is rec)
                lines[idx] = json.dumps(rec, ensure_ascii=False)
                changed += 1
            continue
        points = loss_points(name, base_by_name, adv_by_name)
        if len(points) < MIN_POINTS:
            skipped_no_points.append(name)
            continue
        overrides = {}
        for spec in args.range_origin:
            idx, _, origin = spec.partition('=')
            overrides[int(idx)] = loss_points(name, base_by_name, adv_by_name, origin=origin)
        below = (loss_points(name, base_by_name, adv_by_name, origin=args.below_span)
                 if args.below_span else None)
        if args.cap_at_published and not overrides and not below:
            method = next(m for m in rec['volumetricLosses']['default']
                          if isinstance(m, dict) and m.get('method') == 'steinmetz')
            report = []
            capped = _cap_to_published(method['ranges'], max(p[0] for p in points), report)
            new = None if capped == method['ranges'] else dict(method, ranges=capped)
        else:
            new, report = refit_material(rec, points, narrow_only=args.narrow_ranges,
                                         overrides=overrides, cap_published=args.cap_at_published,
                                         below=below)
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
