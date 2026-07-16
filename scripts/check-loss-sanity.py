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
  HARD  steinmetz alpha/beta outside the physical band (import/fit blunder)
  HARD  saturation flux density RISES with temperature (Bs falls toward the Curie point)
  SOFT  reference loss (100 kHz, 100 mT, 100 C) outside [PLAUS_LO, PLAUS_HI] kW/m^3
  SOFT  reference loss > OUTLIER_RATIO x its material-family median (per-family scale error)
  SOFT  steinmetz ct(T) <= 0 in [-40,220] C  (MKF skips scaling -> temp dependence dead)
  SOFT  steinmetz alpha/beta outside the typical band
  SOFT  Bs above the material-class ceiling / Curie temp below a characterization temp
  SOFT  lossFactor drops with rising frequency (loss factor normally increases)
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

# temperature span over which a Steinmetz ct(T) scale must stay positive. MKF's
# apply_temperature_coefficients SKIPS the ct scaling when ct(T) <= 0, which silently
# inflates the loss by whatever factor ct would have applied (documented ~1000x trap) —
# so a ct polynomial that dips <= 0 anywhere a user might operate is a real hazard.
CT_TSPAN = list(range(-40, 221, 5))

# Steinmetz exponent gates (per the ct/#183 sanity memory: reject alpha<0.5 / alpha>3.5 /
# beta<1, eyeball beta>4.5). Outside the HARD band is almost always a fit/import bug.
ALPHA_LO, ALPHA_HI = 0.5, 3.5
BETA_LO,  BETA_HI  = 1.0, 4.5
ALPHA_HARD_LO, ALPHA_HARD_HI = 0.3, 4.0   # beyond this a power law is unphysical
BETA_HARD_LO,  BETA_HARD_HI  = 0.8, 6.0

# physical saturation-flux ceiling by material class (T, peak); above this Bs is wrong.
BS_MAX = {'ferrite': 0.62, 'nanocrystalline': 1.35, 'amorphous': 1.75,
          'electricalSteel': 2.2, 'powder': 1.9}


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


def check_steinmetz_coeffs(name, primary, hard, soft):
    """Steinmetz exponent gates + the ct(T)<=0 loss-inflation trap (per range)."""
    if primary.get('method') != 'steinmetz':
        return
    for r in primary.get('ranges', []):
        a, b = r.get('alpha'), r.get('beta')
        if a is not None:
            if not (ALPHA_HARD_LO <= a <= ALPHA_HARD_HI):
                hard.append(f"{name}: steinmetz alpha={a:.3g} outside physical "
                            f"[{ALPHA_HARD_LO},{ALPHA_HARD_HI}]")
            elif not (ALPHA_LO <= a <= ALPHA_HI):
                soft.append(f"{name}: steinmetz alpha={a:.3g} outside typical [{ALPHA_LO},{ALPHA_HI}]")
        if b is not None:
            if not (BETA_HARD_LO <= b <= BETA_HARD_HI):
                hard.append(f"{name}: steinmetz beta={b:.3g} outside physical "
                            f"[{BETA_HARD_LO},{BETA_HARD_HI}]")
            elif not (BETA_LO <= b <= BETA_HI):
                soft.append(f"{name}: steinmetz beta={b:.3g} outside typical [{BETA_LO},{BETA_HI}]")
        ct0, ct1, ct2 = r.get('ct0'), r.get('ct1'), r.get('ct2')
        if ct0 is not None and ct1 is not None and ct2 is not None:
            # ct(T) = ct2*T^2 - ct1*T + ct0  (MKF sign convention, CoreLosses.h). When
            # scale <= 0 MKF returns the UNSCALED k*f^a*B^b, so a ct that dips <= 0 in the
            # operating band means the temperature scaling is silently inoperative there
            # (degenerate joint fit). SOFT: the loss magnitude is separately bounded by the
            # monotonicity (HARD) and plausibility (SOFT) checks, so this is a fit-quality
            # flag, not a magnitude blow-up.
            neg = [T for T in CT_TSPAN if ct2*T*T - ct1*T + ct0 <= 0]
            if neg:
                lo, hi = min(neg), max(neg)
                soft.append(f"{name}: steinmetz ct(T)<=0 on T in [{lo},{hi}]C "
                            f"(MKF skips scaling there -> temperature dependence inoperative) "
                            f"[range {r.get('minimumFrequency')}-{r.get('maximumFrequency')} Hz]")


def _series_vs_temperature(entries, key):
    """Return [(temperature, value)] sorted by temperature for a list of {temperature,key}."""
    out = []
    for e in entries or []:
        if isinstance(e, dict) and 'temperature' in e and key in e:
            out.append((e['temperature'], e[key]))
    return sorted(out)


def check_saturation(name, o, hard, soft):
    """Bs must not exceed its material-class ceiling and must not RISE with temperature
    (saturation falls toward the Curie point)."""
    pts = _series_vs_temperature(o.get('saturation'), 'magneticFluxDensity')
    if not pts:
        return
    cap = BS_MAX.get(o.get('material'))
    for T, B in pts:
        if cap and B > cap * 1.02:
            soft.append(f"{name}: Bs={B:.3g} T @ {T}C exceeds {o.get('material')} ceiling {cap} T")
    for i in range(len(pts) - 1):
        (t0, b0), (t1, b1) = pts[i], pts[i+1]
        if b1 > b0 * 1.02:           # >2% rise with temperature is unphysical
            hard.append(f"{name}: Bs rises with temperature ({b0:.3g}@{t0}C -> {b1:.3g}@{t1}C)")
            break


def check_curie(name, o, soft):
    """Curie temperature should sit above the hottest characterization temperature."""
    tc = o.get('curieTemperature')
    if tc is None:
        return
    tmax = 0
    for fld, key in (('saturation','magneticFluxDensity'), ('remanence','magneticFluxDensity'),
                     ('coerciveForce','magneticField')):
        for T, _ in _series_vs_temperature(o.get(fld), key):
            tmax = max(tmax, T)
    if tmax and tc < tmax:
        soft.append(f"{name}: Curie temperature {tc}C below a characterization temp {tmax}C")


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
        # material-level physics (independent of the loss model)
        check_saturation(name, o, hard, soft)
        check_curie(name, o, soft)
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
        # steinmetz exponent + ct(T) guards
        if primary is not None:
            check_steinmetz_coeffs(name, primary, hard, soft)
        # lossFactor factor-range + frequency-monotonicity check
        for meth in methods:
            if isinstance(meth, dict) and meth.get('method') == 'lossFactor':
                facs = [f for f in meth.get('factors', []) if isinstance(f, dict)]
                for fac in facs:
                    v = fac.get('value')
                    if v is None or not (LF_LO <= v <= LF_HI):
                        hard.append(f"{name}: lossFactor value {v} @ {fac.get('frequency')} Hz "
                                    f"outside physical [{LF_LO},{LF_HI}]")
                fv = sorted((f.get('frequency'), f.get('value')) for f in facs
                            if f.get('frequency') is not None and f.get('value') is not None)
                for i in range(len(fv) - 1):
                    if fv[i+1][1] < fv[i][1] * 0.5:   # loss factor should not halve as f rises
                        soft.append(f"{name}: lossFactor drops with frequency "
                                    f"({fv[i][1]:.2g}@{fv[i][0]:.0f}Hz -> {fv[i+1][1]:.2g}@{fv[i+1][0]:.0f}Hz)")
                        break
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
