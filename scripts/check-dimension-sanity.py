#!/usr/bin/env python3
"""Dimensional-plausibility checker for the MAS catalogues (ABT #407).

Every length in MAS is stored in METRES. The bug class this guards against is a
conversion that stops one unit short — an importer that turns mils into millimetres
and writes the millimetre figure into a metre field, so the value lands 1000x (or
25.4x, or 10x) off with its digits intact. Nothing downstream notices: the JSON is
schema-valid, the number is a number, and the first symptom is a solver dying far
away with a message that names neither the part nor the cause.

The seven Magnetics "- P -" cores of ABT #407 were exactly this — a 127 mm gap on a
core 19.3 mm across, carried happily by the catalogue for weeks. The cheapest gate
that would have stopped them is geometric and needs no physics: **a length belonging
to a part cannot exceed the bounding box of that part**. That is the spine of this
script; the rest are the same idea applied per catalogue.

Checks (HARD = non-zero exit, physically impossible; SOFT = warning, eyeball-worthy):

  cores / cores_stock
    HARD  a gap length <= 0, or NOT a finite number
    HARD  a gap longer than the bounding box of its own shape          <- the #407 gate
    HARD  a core naming a shape that does not exist in core_shapes
    SOFT  a gap longer than GAP_SOFT_FRAC of that bounding box
    HARD  the "... Gapped X.XXX mm" in a core's name disagreeing with its
          subtractive gap (catches a half-applied correction)

  core_shapes
    HARD  a dimension outside [SHAPE_MIN, SHAPE_MAX]
    HARD  intra-record spread > SPREAD_MAX (one dimension orders of magnitude off
          its own siblings — the exact signature of a skipped conversion)
    HARD  a toroid whose bore (B) is not smaller than its outer diameter (A)
    SOFT  a toroid with A/B > TOROID_ODID_SOFT (near-solid disc: suspect a decimal slip)

  bobbins
    HARD  a dimension outside [SHAPE_MIN, SHAPE_MAX]
    HARD  intra-record spread > SPREAD_MAX
    HARD  a bobbin dimension larger than BOBBIN_OVER x the bounding box of the core
          shape it is built for (a bobbin cannot dwarf its core)

  wires
    HARD  a dimension outside [WIRE_MIN, WIRE_MAX]
    HARD  an outer dimension smaller than the conducting dimension it encloses
    HARD  outer/conducting ratio > WIRE_RATIO_MAX
    HARD  a coating thicker than the conductor it coats
    HARD  an AWG-named round wire whose conducting diameter misses the AWG
          definition by more than AWG_TOL (imperial-sourced wire is the prime
          suspect for the same skipped /1000)
    SOFT  outer/conducting ratio > WIRE_RATIO_SOFT

Angles (alpha/beta/gamma) are degrees, not lengths, and are excluded throughout.

Thresholds are set from the measured spread of the shipped catalogue with margin —
see the comment on each — so a clean catalogue exits 0 and the #407 defects do not.

Usage:  python3 scripts/check-dimension-sanity.py [--verbose]
Exit code 0 if no HARD failures, 1 otherwise.
"""
import json, sys, os, math, re

DATA = 'data'

# --- thresholds -------------------------------------------------------------
# Absolute range for a core-shape / bobbin dimension. The shipped catalogue spans
# 170 um (EFD 20/10/7 K) to 305 mm (T 305/207/30 A); these bounds sit well outside
# that on both sides, so only a genuine order-of-magnitude slip trips them.
SHAPE_MIN, SHAPE_MAX = 50e-6, 1.0

# Wire dimensions span 5 um (Foil 0.005) to 16.14 mm (Rectangular 16x5.60).
WIRE_MIN, WIRE_MAX = 1e-6, 0.1

# Largest legitimate intra-record spread in the shipped catalogue is 161x
# (Bobbin RM 14A: a 0.3 mm corner radius beside a 48 mm flange). A skipped /1000
# lands at ~1000x or worse, so 500x separates them with room on both sides.
SPREAD_MAX = 500.0

# A gap can never exceed its shape's bounding box (HARD). The largest gap actually
# shipped is 48% of its column height, so anything past 60% of the *bounding box*
# is worth a look without being an error.
GAP_SOFT_FRAC = 0.60

# A bobbin is built around its core and cannot dwarf it. Bobbin dimensions include
# flanges and pins that overhang the core somewhat, hence the slack.
BOBBIN_OVER = 1.5

# Enamel/served/triple-insulated wire: the shipped extreme is 3.89x (40 AWG TIW).
WIRE_RATIO_SOFT, WIRE_RATIO_MAX = 5.0, 10.0

# AWG is a definition, not a measurement: d = 0.127 mm * 92^((36-n)/39).
AWG_TOL = 0.05

# A toroid whose outer diameter is more than this multiple of its bore is nearly a
# solid disc — real powder/ferrite rings sit well under it.
TOROID_ODID_SOFT = 12.0

ANGLE_KEYS = {'alpha', 'beta', 'gamma', 'angle'}


def load(fname):
    """Yield every record of a MAS ndjson, skipping the git-lfs pointer header."""
    path = os.path.join(DATA, fname)
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('version https'):
                continue
            yield json.loads(line)


def resolve(d):
    """Collapse a dimensionWithTolerance to a scalar: nominal -> mid -> max -> min.

    Mirrors MKF's resolve_dimensional_values. Returns None when the value carries no
    bound at all; callers treat that as 'not specified', never as zero.
    """
    if isinstance(d, bool):
        return None
    if isinstance(d, (int, float)):
        return float(d)
    if not isinstance(d, dict):
        return None
    if d.get('nominal') is not None:
        return float(d['nominal'])
    mn, mx = d.get('minimum'), d.get('maximum')
    if mn is not None and mx is not None:
        return (float(mn) + float(mx)) / 2.0
    if mx is not None:
        return float(mx)
    if mn is not None:
        return float(mn)
    return None


def lengths_of(dims):
    """{key: metres} for the length-valued entries of a dimensions block."""
    out = {}
    for k, v in (dims or {}).items():
        if k.lower() in ANGLE_KEYS:
            continue
        val = resolve(v)
        if val is not None:
            out[k] = val
    return out


def bounding_box(dims):
    """Largest length in a dimensions block — the part cannot be bigger than this."""
    vals = [v for v in lengths_of(dims).values() if v > 0]
    return max(vals) if vals else None


def in_range(v, lo, hi):
    """Is a shape/bobbin dimension of a plausible MAGNITUDE?

    Two shipped conventions make a naive `lo <= v <= hi` wrong, and both are real
    geometry rather than bad data:
      * exactly 0 means the feature is absent — a sharp corner rather than a fillet
        (core_shapes r1 on the large P cores, R2 on U 80/150/30);
      * a few dimensions are signed OFFSETS, not extents — EFD K is -0.2 mm on
        EFD 10/5/3, 12/6/3.5 and 15/8/5, describing which side of centre the leg
        sits on.
    So test the magnitude, and let an exact zero through. A unit slip changes the
    magnitude by orders of magnitude and is caught either way.
    """
    if v == 0:
        return True
    return lo <= abs(v) <= hi


def check_shapes(shapes, hard, soft):
    for s in shapes:
        name = s['name']
        dims = lengths_of(s.get('dimensions'))
        for k, v in dims.items():
            if not math.isfinite(v):
                hard.append(f"core_shapes {name}: dimension {k} is not finite ({v!r})")
            elif not in_range(v, SHAPE_MIN, SHAPE_MAX):
                hard.append(f"core_shapes {name}: dimension {k} = {v:g} m is outside "
                            f"[{SHAPE_MIN:g}, {SHAPE_MAX:g}] m — a length in the wrong unit?")
        pos = {k: v for k, v in dims.items() if v > 0 and math.isfinite(v)}
        if len(pos) >= 2:
            lo, hi = min(pos.values()), max(pos.values())
            if hi / lo > SPREAD_MAX:
                kmax = max(pos, key=pos.get)
                kmin = min(pos, key=pos.get)
                hard.append(f"core_shapes {name}: {kmax}={hi:g} m is {hi/lo:.0f}x its own "
                            f"sibling {kmin}={lo:g} m (>{SPREAD_MAX:g}x) — one dimension is "
                            f"in a different unit from the rest of the record")
        if s.get('family') == 't':
            A, B = dims.get('A'), dims.get('B')
            if A is not None and B is not None and A > 0 and B > 0:
                if B >= A:
                    hard.append(f"core_shapes {name}: toroid bore B={B:g} m is not smaller "
                                f"than outer diameter A={A:g} m")
                elif A / B > TOROID_ODID_SOFT:
                    soft.append(f"core_shapes {name}: toroid A/B = {A/B:.1f} "
                                f"(A={A*1000:.3f} mm, B={B*1000:.3f} mm) — near-solid disc, "
                                f"suspect a decimal slip in A")


def check_cores(fname, shape_bbox, hard, soft):
    for c in load(fname):
        name = c['name']
        fd = c.get('functionalDescription') or {}
        gapping = fd.get('gapping') or []
        sname = fd.get('shape')
        if isinstance(sname, dict):                 # shape given inline
            bbox = bounding_box(sname.get('dimensions'))
            sdesc = sname.get('name', '<inline>')
        else:
            sdesc = sname
            if sname not in shape_bbox:
                hard.append(f"{fname} {name}: names shape '{sname}', which is not in "
                            f"core_shapes.ndjson")
                continue
            bbox = shape_bbox[sname]
        if bbox is None or bbox <= 0:
            hard.append(f"{fname} {name}: shape '{sdesc}' has no usable dimensions, so its "
                        f"gaps cannot be bounds-checked")
            continue

        for g in gapping:
            L = g.get('length')
            if L is None:
                continue
            if not isinstance(L, (int, float)) or not math.isfinite(L) or L <= 0:
                hard.append(f"{fname} {name}: gap length {L!r} is not a positive finite number")
                continue
            # THE #407 GATE: a gap ground into a part cannot be longer than the part.
            if L > bbox:
                hard.append(f"{fname} {name}: {g.get('type')} gap {L*1000:.4f} mm is longer "
                            f"than its whole shape '{sdesc}' ({bbox*1000:.3f} mm) — "
                            f"physically impossible; {L*1000/25.4:.4g} mil would be "
                            f"{L*1000/25.4*0.0254:.6g} mm")
            elif L > GAP_SOFT_FRAC * bbox:
                soft.append(f"{fname} {name}: {g.get('type')} gap {L*1000:.4f} mm is "
                            f"{100*L/bbox:.0f}% of its shape's bounding box "
                            f"({bbox*1000:.3f} mm)")

        # The name carries the same number; if a correction touched one and not the
        # other, the record is internally inconsistent and one of them is a lie.
        m = re.search(r'Gapped\s+([\d.]+)\s*mm\s*$', name)
        if m:
            subs = [g for g in gapping if g.get('type') == 'subtractive']
            if not subs:
                hard.append(f"{fname} {name}: name says 'Gapped' but the record has no "
                            f"subtractive gap")
            else:
                want = float(m.group(1)) / 1000.0
                got = subs[0].get('length')
                if isinstance(got, (int, float)) and math.isfinite(got):
                    if abs(got - want) > max(0.01 * want, 5e-6):
                        hard.append(f"{fname} {name}: name says {want*1000:.4f} mm but the "
                                    f"subtractive gap is {got*1000:.4f} mm ({got/want:.6g}x)")


def check_bobbins(shape_bbox, hard, soft):
    for b in load('bobbins.ndjson'):
        name = b['name']
        fd = b.get('functionalDescription') or {}
        dims = lengths_of(fd.get('dimensions'))
        for k, v in dims.items():
            if not math.isfinite(v):
                hard.append(f"bobbins {name}: dimension {k} is not finite ({v!r})")
            elif not in_range(v, SHAPE_MIN, SHAPE_MAX):
                hard.append(f"bobbins {name}: dimension {k} = {v:g} m is outside "
                            f"[{SHAPE_MIN:g}, {SHAPE_MAX:g}] m")
        pos = {k: v for k, v in dims.items() if v > 0 and math.isfinite(v)}
        if len(pos) >= 2:
            lo, hi = min(pos.values()), max(pos.values())
            if hi / lo > SPREAD_MAX:
                kmax, kmin = max(pos, key=pos.get), min(pos, key=pos.get)
                hard.append(f"bobbins {name}: {kmax}={hi:g} m is {hi/lo:.0f}x its own sibling "
                            f"{kmin}={lo:g} m (>{SPREAD_MAX:g}x)")
        sname = fd.get('shape')
        if isinstance(sname, str) and sname in shape_bbox:
            bbox = shape_bbox[sname]
            if bbox:
                for k, v in pos.items():
                    if v > BOBBIN_OVER * bbox:
                        hard.append(f"bobbins {name}: {k} = {v*1000:.3f} mm exceeds "
                                    f"{BOBBIN_OVER}x the bounding box of its core shape "
                                    f"'{sname}' ({bbox*1000:.3f} mm)")


def check_wires(hard, soft):
    PAIRS = (('conductingDiameter', 'outerDiameter'),
             ('conductingWidth', 'outerWidth'),
             ('conductingHeight', 'outerHeight'))
    ALL = ('conductingDiameter', 'outerDiameter', 'conductingWidth', 'conductingHeight',
           'outerWidth', 'outerHeight', 'strandDiameter')
    for w in load('wires.ndjson'):
        name = w['name']
        vals = {}
        for k in ALL:
            v = resolve(w.get(k))
            if v is None:
                continue
            if not math.isfinite(v) or v <= 0:
                hard.append(f"wires {name}: {k} = {v!r} is not a positive finite number")
                continue
            if not (WIRE_MIN <= v <= WIRE_MAX):
                hard.append(f"wires {name}: {k} = {v:g} m is outside "
                            f"[{WIRE_MIN:g}, {WIRE_MAX:g}] m")
            vals[k] = v

        for ck, ok in PAIRS:
            c, o = vals.get(ck), vals.get(ok)
            if c is None or o is None:
                continue
            if o < c:
                hard.append(f"wires {name}: {ok} {o:g} m is smaller than the {ck} "
                            f"{c:g} m it encloses")
            elif o / c > WIRE_RATIO_MAX:
                hard.append(f"wires {name}: {ok}/{ck} = {o/c:.2f} (> {WIRE_RATIO_MAX:g}) — "
                            f"insulation cannot be that much of the wire")
            elif o / c > WIRE_RATIO_SOFT:
                soft.append(f"wires {name}: {ok}/{ck} = {o/c:.2f}")

        ct = resolve((w.get('coating') or {}).get('thickness'))
        if ct is not None and math.isfinite(ct) and ct > 0:
            cond = [vals[k] for k in ('conductingDiameter', 'conductingWidth',
                                      'conductingHeight') if k in vals]
            if cond and ct > min(cond):
                hard.append(f"wires {name}: coating thickness {ct:g} m exceeds the conductor "
                            f"it coats ({min(cond):g} m)")

        # AWG is a definition; an imperial-sourced wire that misses it was converted wrong.
        m = re.search(r'\bAWG\s*(\d{1,2})\b', str(w.get('standardName') or name))
        if m and w.get('type') == 'round' and 'conductingDiameter' in vals:
            n = int(m.group(1))
            want = 0.000127 * 92.0 ** ((36 - n) / 39.0)
            got = vals['conductingDiameter']
            if abs(got - want) / want > AWG_TOL:
                hard.append(f"wires {name}: conducting diameter {got*1000:.5f} mm but AWG {n} "
                            f"is {want*1000:.5f} mm ({got/want:.6g}x)")


def main(argv):
    verbose = '--verbose' in argv
    if not os.path.isdir(DATA):
        print(f"error: run from the MAS repo root ('{DATA}/' not found)", file=sys.stderr)
        return 2

    hard, soft = [], []
    shapes = list(load('core_shapes.ndjson'))
    shape_bbox = {s['name']: bounding_box(s.get('dimensions')) for s in shapes}
    for s in shapes:                       # aliases resolve to the same box
        for a in s.get('aliases') or []:
            shape_bbox.setdefault(a, shape_bbox[s['name']])

    check_shapes(shapes, hard, soft)
    ncores = 0
    for fname in ('cores.ndjson', 'cores_stock.ndjson'):
        before = len(hard)
        n = sum(1 for _ in load(fname))
        ncores += n
        check_cores(fname, shape_bbox, hard, soft)
        if verbose:
            print(f"  {fname}: {n} cores, {len(hard)-before} hard")
    check_bobbins(shape_bbox, hard, soft)
    check_wires(hard, soft)

    nwires = sum(1 for _ in load('wires.ndjson'))
    nbob = sum(1 for _ in load('bobbins.ndjson'))
    print(f"checked {len(shapes)} shapes, {ncores} cores, {nbob} bobbins, {nwires} wires")

    if soft:
        print(f"\n-- {len(soft)} SOFT warnings --")
        for s in soft:
            print("  ?", s)
    if hard:
        print(f"\n== {len(hard)} HARD failures ==")
        for h in hard:
            print("  X", h)
        return 1
    print("OK: no dimensional impossibilities")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
