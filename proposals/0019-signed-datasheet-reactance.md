# MAS-RFC 0019 — Signed reactance in `magneticDatasheetReactancePoint`

- **Status:** Accepted (owner decision 2026-11-03, approved by Alf; implementation in the same change set)
- **Type:** Relaxing (non-breaking for readers that accept any number; every document valid today stays valid).
- **Author:** drafted 2026-11-03
- **Created:** 2026-11-03
- **Depends on:** nothing.

## Summary

`magneticDatasheetReactancePoint.reactance` (in `schemas/magnetic.json`) carries `"minimum": 0`.
Reactance is a signed quantity: X = Im(Z) is positive while a part is inductive and negative
once it is capacitive. Every ferrite bead and inductor turns capacitive above its
self-resonant frequency, and manufacturers that publish the measured complex impedance publish
that negative branch as measured data.

Proposal: drop `"minimum": 0` from `reactance`, and state the sign convention in its
description. `frequency` and `current` keep their `minimum: 0`. `magneticDatasheetResistancePoint`
is unchanged, because a passive part's resistance is never negative.

## Motivation

TDK's Product Center publishes the numeric R(f), X(f) and |Z|(f) series behind its chip-bead
characteristic charts. On 2026-11-03, 495 TDK bead reactance series contained negative values
above self-resonance. These are measured vendor values, but they cannot be stored today. The only
schema-valid choices are both lossy:

- truncate the curve at the zero crossing, which throws away the high-frequency half where a
  bead does its filtering work;
- store |X|, which silently flips the sign and makes R + jX disagree with the published |Z|.

Without the sign, a consumer cannot rebuild Z = R + jX (needed for SPICE bead models and EMI
filter design). That reconstruction is the reason the R and X curves are stored separately at all.

## Change

```jsonc
"reactance": {
    "description": "Reactance X = Im(Z) in Ohms: positive when the part is inductive, negative when capacitive (above self-resonance).",
    "type": "number"
}
```

## Compatibility

- **Readers:** every existing document has X >= 0 and stays valid. Code that assumed X >= 0
  (e.g. taking log(X) for a plot) must handle the negative branch. This is a behavioural note,
  not a schema break.
- **Writers:** none need to change.
- **Bindings:** the generated C++/Python types already map `reactance` to `double`, so no type
  change is needed.

## Alternatives considered

1. **Keep `minimum: 0`; store only the inductive branch.** This loses the published data above
   self-resonance, which is the operating region of a bead.
2. **A separate `capacitiveReactancePoints` array.** Rejected: it splits one measured curve
   into two arrays and duplicates the point type.
3. **Store |Z| and the phase angle instead.** That is a different, larger change.
   `impedancePoints` already carries magnitude (and optionally phase) for consumers who want it.

## Open questions

- Should `impedancePoints[].impedance.phase` be documented as the preferred carrier of the
  sign instead, with X kept non-negative? The drafter's view is no: R and X are what vendors
  publish, and the schema already models them as separate curves.
