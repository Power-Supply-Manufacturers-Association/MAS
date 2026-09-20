# MAS-RFC 0018 — Resistance and reactance vs. frequency on the datasheet `inductor` electrical variant

- **Status:** Accepted (owner decision 2026-09-20, approved by Alf; implementation in the same change set)
- **Type:** Additive (non-breaking) schema change.
- **Author:** drafted 2026-09-20
- **Created:** 2026-09-20
- **Depends on:** nothing. Reuses the existing `magneticDatasheetResistancePoint` /
  `magneticDatasheetReactancePoint` definitions unchanged.

## Summary

`magneticDatasheetInductorElectrical` (in `schemas/magnetic.json`) cannot state R(f) or X(f).
`magneticDatasheetChipBeadElectrical` can, through `resistancePoints` / `reactancePoints`. Both
variants are closed (`additionalProperties: false`), so a measured R(f)/X(f) pair for a part
whose `subtype` is `inductor` has nowhere to go.

This is the same shape of gap as MAS-RFC 0017 (saturation current missing from the
`transformer` variant while present on `inductor` and `coupledInductor`), and the same remedy:
add the existing field to the variant that lacks it.

## Evidence

Würth publishes measured R(f) and X(f) through REDEXPERT for its WE-RFI ferrite SMT inductor
family — the same charts, on the same instrument, that it publishes for its chip beads. 68 parts
of that family are in the catalogue today. Their own vendor descriptions read

    WE-RFI Ferrite SMT Inductor, size 0805, 470nH, 500mA, 375MHz   (744760247A)
    WE-RFI Ferrite SMT Inductor, size 0805, 560nH, 450mA, 340MHz   (744760256A)

and each record carries `inductance.nominal` and `selfResonantFrequency`. These parts are
inductors, by the vendor's own naming and by the quantity they are selected on, so `subtype:
inductor` is correct and re-subtyping them to `chipBead` to unlock the field would be a false
classification adopted for a plumbing reason.

Both curves are clean at source — no derivation, no interpolation, no negative-value artefacts.
The data is available and verified; only the schema prevents it being stored.

## Why the quantity belongs on the variant

R(f) and X(f) are properties of any two-terminal magnetic, not of a bead. A ferrite inductor
near and above self-resonance is characterised by exactly the same decomposition, and the
inductor variant already accepts `impedancePoints` — so MAS today admits |Z|(f) for an inductor
while refusing the two components |Z|(f) is composed of. That asymmetry has no physical
justification.

Storing R(f) also answers a question `dcResistance` cannot: AC winding and core loss at the
operating frequency. For a part rated at 375 MHz, the DC figure is not the resistance that
matters.

## Proposed change

In `schemas/magnetic.json`, add two properties to
`$defs.magneticDatasheetInductorElectrical.properties`, copied verbatim from
`magneticDatasheetChipBeadElectrical`:

```json
"resistancePoints": {
  "description": "Resistance vs. frequency points, optionally parameterised by DC bias current.",
  "type": "array",
  "items": { "$ref": "#/$defs/magneticDatasheetResistancePoint" }
},
"reactancePoints": {
  "description": "Reactance vs. frequency points, optionally parameterised by DC bias current.",
  "type": "array",
  "items": { "$ref": "#/$defs/magneticDatasheetReactancePoint" }
}
```

No new `$defs`. No change to the chip-bead variant. No field becomes required.

## Compatibility

Additive and non-breaking. Every document valid before the change stays valid: the two
properties are optional, and the variant's `additionalProperties: false` only becomes *less*
restrictive. No existing record is affected; no migration is needed. Consumers that do not know
the fields ignore them, exactly as they do on the chip-bead variant today.

## Alternatives considered

- **Re-subtype the 68 parts to `chipBead`.** Rejected. WE-RFI is a real inductor family;
  changing a part's classification to make a field reachable puts a false statement in the
  catalogue to avoid a schema change, and the falsehood outlives the convenience.
- **Store R(f)/X(f) only as `impedancePoints`.** Rejected. |Z| = sqrt(R² + X²) discards the
  split, which is the part of the measurement an engineer needs at RF, and the information
  cannot be recovered afterwards.
- **Leave the data unharvested.** This is the status quo. It is the only known unharvested
  vendor data in REDEXPERT module 1, and the cost of the gap grows with every family Würth
  measures this way.

## Implementation

One edit to `schemas/magnetic.json` adding the two properties, plus a `CHANGELOG.md` entry under
the next MINOR release.

The draft said this would also add an entry to `docs/schema.md` and a fixture. Neither applies as
written, and the claim is corrected rather than left standing: `docs/` describes MAS as class
diagrams and does not enumerate the datasheet electrical variants at all — `impedancePoints`,
`resistancePoints` and `reactancePoints` are undocumented there today — and
`scripts/validate-fixtures.py` maps `samples/` directories to sub-schemas, with no mapping for a
variant that lives inside `magnetic.json`. Adding either would mean inventing a documentation
pattern this repo does not use.

What was done instead is a stronger check than a fixture: a REAL WE-RFI record
(`744760247A`) taken from the live catalogue, given `resistancePoints` and `reactancePoints`,
validated against `magnetic.json` with the full sibling registry — valid after the change, and
**invalid against the pre-change schema**, which is what proves the change is what admits it. A
non-curve value in either field is still rejected. `validate-fixtures.py` (25/25) and
`validate-samples.py` (8/8) both stay green, confirming no existing document is affected.

The 68 WE-RFI curves are harvested only after this RFC is accepted — nothing is written to the
catalogue in advance of the decision.
