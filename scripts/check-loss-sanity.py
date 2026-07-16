#!/usr/bin/env python3
"""Loss-model sanity checker for MAS core_materials.

Evaluates every material's *volumetric* loss model at a grid of reference operating
points (sinusoidal excitation) and flags physically-implausible results — the class of
bugs that unit/scale errors in an import produce (e.g. a lossFactor stored 1e6x too
large, a Steinmetz `k` off by a decade, a coefficient copied from the wrong family).

It is a Python mirror of MKF's CoreLosses formulas (physical_models/CoreLosses.cpp):
  steinmetz   P = k·f^alpha·B^beta·(ct2·T^2 - ct1·T + ct0)   [range-selected by f; ct only if >0]
  magnetics   P = a·B^b·f^c
  poco        P = 1000·(a·(f/1000)·(B·10)^b + c·(B·10·f/1000)^2)
  tdg         P = 1000·(B·10)^a·(b·(f/1000) + c·(f/1000)^d)
  micrometals P = f/(a/B^3 + b/B^2.3 + c/B^1.65) + d·B^2·f^2
  (roshen: resistivity/permeability based — not evaluated here; lossFactor: factor range
   is checked instead of a full loss evaluation.)

Units: P in W/m^3, f in Hz, B in T (peak), T in Celsius.

Checks (HARD = non-zero exit, physics violations; SOFT = warning, eyeball-worthy):
  HARD  loss non-finite or <= 0 at any reference point
  HARD  loss not strictly increasing with B (at fixed f,T)
  HARD  loss not strictly increasing with f (at fixed B,T)
  SOFT  reference loss (100 kHz, 100 mT, 100 C) outside [PLAUS_LO, PLAUS_HI] kW/m^3
  SOFT  reference loss > OUTLIER_RATIO x its material-family median (per-family scale error)
  HARD  lossFactor factor value outside [LF_LO, LF_HI]  (tan-delta/mu_i is ~1e-6..1e-1)

Usage:  python3 scripts/check-loss-sanity.py [--verbose] [--baseline]
        --verbose   list the reference loss of every material
        --baseline  print a stable name,loss CSV (regression baseline)
Exit code 0 if no HARD failures, 1 otherwise.
"""
import json, sys, math

DATA = 'data/core_materials.ndjson'

# reference grid (sinusoidal)
REF_F = 100e3          # Hz
REF_B = 0.100          # T
REF_T = 100.0          # C
GRID_F = [25e3, 100e3, 500e3]
GRID_B = [0.025, 0.050, 0.100, 0.200]

# plausibility band for a ferrite/powder at the reference point, in kW/m^3
PLAUS_LO, PLAUS_HI = 0.5, 30000.0
OUTLIER_RATIO = 6.0    # x family median
LF_LO, LF_HI = 1e-8, 1.0   # relative loss factor tan-delta/mu_i physical range


def steinmetz_range(ranges, f):
    """Mirror MKF get_steinmetz_coefficients: first range containing f, else nearest end."""
    lo_i = hi_i = None
    lo_f, hi_f = math.inf, 0.0
    for i, r in enumerate(ranges):
        mn, mx = r['minimumFrequency'], r['maximumFrequency']
        if mn <= f <= mx:
            return r
        if mn < lo_f:
            lo_f, lo_i = mn, i
        if mx > hi_f:
            hi_f, hi_i = mx, i
    return ranges[lo_i] if f < lo_f else ranges[hi_i]


def eval_loss(method, f, B, T):
    """Return volumetric loss [W/m^3] for a proprietary/steinmetz method dict, or None."""
    m = method.get('method')
    if m == 'steinmetz':
        r = steinmetz_range(method['ranges'], f)
        p = r['k'] * f**r['alpha'] * B**r['beta']
        ct0, ct1, ct2 = r.get('ct0'), r.get('ct1'), r.get('ct2')
        if ct0 is not None and ct1 is not None and ct2 is not None:
            scale = ct2 * T*T - ct1 * T + ct0
            if scale > 0:
                p *= scale
        return p
    if m == 'magnetics':
        a, b, c = method['a'], method['b'], method['c']
        return a * B**b * f**c
    if m == 'poco':
        a, b, c = method['a'], method['b'], method['c']
        return 1000.0 * (a * (f/1000.0) * (B*10.0)**b + c * (B*10.0*f/1000.0)**2)
    if m == 'tdg':
        a, b, c, d = method['a'], method['b'], method['c'], method['d']
        return 1000.0 * (B*10.0)**a * (b*(f/1000.0) + c*(f/1000.0)**d)
    if m == 'micrometals':
        a, b, c, d = method['a'], method['b'], method['c'], method['d']
        return f / (a/B**3 + b/B**2.3 + c/B**1.65) + d * B*B * f*f
    return None  # roshen, lossFactor handled elsewhere


def family_of(name, fam):
    return fam or name.rsplit(' ', 1)[0]


def main():
    verbose = '--verbose' in sys.argv
    baseline = '--baseline' in sys.argv
    hard, soft = [], []
    ref = {}   # name -> reference loss (kW/m^3)
    fam_ref = {}

    records = []
    for line in open(DATA):
        line = line.strip()
        if not line or line.startswith('version'):
            continue
        records.append(json.loads(line))

    for o in records:
        name = o['name']
        vl = o.get('volumetricLosses')
        if not isinstance(vl, dict):
            continue
        methods = vl.get('default', [])
        # pick the primary evaluable method (steinmetz/proprietary); skip roshen
        primary = None
        for meth in methods:
            if isinstance(meth, dict) and meth.get('method') in (
                    'steinmetz', 'magnetics', 'poco', 'tdg', 'micrometals'):
                primary = meth
                break
        # lossFactor factor-range check
        for meth in methods:
            if isinstance(meth, dict) and meth.get('method') == 'lossFactor':
                for fac in meth.get('factors', []):
                    v = fac.get('value')
                    if v is None or not (LF_LO <= v <= LF_HI):
                        hard.append(f"{name}: lossFactor value {v} @ {fac.get('frequency')} Hz "
                                    f"outside physical [{LF_LO},{LF_HI}]")
        if primary is None:
            continue

        try:
            # monotonicity in B (fixed f=REF_F, T=REF_T)
            pb = [eval_loss(primary, REF_F, B, REF_T) for B in GRID_B]
            pf = [eval_loss(primary, f, REF_B, REF_T) for f in GRID_F]
            pref = eval_loss(primary, REF_F, REF_B, REF_T)
        except Exception as e:
            hard.append(f"{name}: loss eval raised {type(e).__name__}: {e}")
            continue

        allpts = pb + pf + [pref]
        if any(p is None or not math.isfinite(p) or p <= 0 for p in allpts):
            hard.append(f"{name}: non-finite/non-positive loss at a reference point "
                        f"(method={primary['method']})")
            continue
        if any(pb[i] >= pb[i+1] for i in range(len(pb)-1)):
            hard.append(f"{name}: loss not increasing with B "
                        f"({[round(x/1e3) for x in pb]} kW/m3 @ B={GRID_B})")
        if any(pf[i] >= pf[i+1] for i in range(len(pf)-1)):
            hard.append(f"{name}: loss not increasing with f "
                        f"({[round(x/1e3) for x in pf]} kW/m3 @ f={GRID_F})")

        rk = pref / 1000.0  # kW/m^3
        ref[name] = rk
        fam_ref.setdefault(family_of(name, o.get('family')), []).append(rk)
        if not (PLAUS_LO <= rk <= PLAUS_HI):
            soft.append(f"{name}: ref loss {rk:.1f} kW/m3 (100kHz/100mT/100C) outside "
                        f"plausible [{PLAUS_LO},{PLAUS_HI}] (method={primary['method']})")

    # per-family outlier scan
    for name, rk in ref.items():
        fam = None
        for r in records:
            if r['name'] == name:
                fam = family_of(name, r.get('family')); break
        peers = [v for v in fam_ref.get(fam, []) if v is not None]
        if len(peers) >= 3:
            med = sorted(peers)[len(peers)//2]
            if med > 0 and (rk > OUTLIER_RATIO*med or rk < med/OUTLIER_RATIO):
                soft.append(f"{name}: ref loss {rk:.1f} kW/m3 is {rk/med:.1f}x family '{fam}' "
                            f"median {med:.1f} (possible per-family scale error)")

    if baseline:
        for n in sorted(ref):
            print(f"{n},{ref[n]:.2f}")
        return 0
    if verbose:
        for n in sorted(ref):
            print(f"  {n:22s} {ref[n]:9.1f} kW/m3 @100kHz/100mT/100C")

    print(f"\nchecked {len(ref)} evaluable materials "
          f"({len(records)} records total)")
    if soft:
        print(f"\n-- {len(soft)} SOFT warnings --")
        for s in soft:
            print("  ?", s)
    if hard:
        print(f"\n== {len(hard)} HARD failures ==")
        for h in hard:
            print("  X", h)
        return 1
    print("OK: no hard loss-physics violations")
    return 0


if __name__ == '__main__':
    sys.exit(main())
