# MAS-RFC 0017 — Saturation current on the datasheet `transformer` electrical variant

- **Status:** Accepted (owner decision 2026-09-13, approved by Alf; implementation in the same change set)
- **Type:** Additive (non-breaking) schema change.
- **Author:** Alfonso Martínez (drafted 2026-09-13 with Alf)
- **Created:** 2026-09-13
- **Depends on:** nothing. Reuses the existing `magneticDatasheetSaturationCurrent` definition.

## Summary

`magneticDatasheetTransformerElectrical` (in `schemas/magnetic.json`) cannot state a saturation
current. `magneticDatasheetInductorElectrical` and `magneticDatasheetCoupledInductorElectrical`
both can, through `saturationCurrentPeak` / `saturationCurrents`. The variant is closed
(`additionalProperties: false`), so a transformer datasheet's I_sat has nowhere to go.

Energy-storing transformers do publish it. Every Würth Midcom flyback transformer datasheet has
a row such as

    Saturation Current   ISAT   N1+N2 / |ΔL/L| < 20 %   3.5 A typ.   (750811248)
    Saturation Current   ISAT   N1    / |ΔL/L| < 20 %   300 mA typ.  (750811023)

and I_sat is the quantity a flyback transformer is selected by. Leaving it out forces bad
choices. Either the catalogue drops the value, and Kelvin can no longer rank flyback parts by
saturation headroom. Or the part gets filed under `coupledInductor`, whose `inductance` means
per-winding inductance, not the magnetizing inductance the datasheet states. Or it gets filed
as a single-winding `inductor`, which is what happened to 530 Würth parts in TAS: their turns
ratios, leakage and per-winding DCR were lost, and the Kirchhoff engine rejects them when
bound into a flyback.

## What is proposed

Add two optional properties to `magneticDatasheetTransformerElectrical`. Both are identical to
the ones already on the inductor and coupled-inductor variants:

```jsonc
"saturationCurrentPeak": {
  "description": "Peak saturation current in Amperes (I_sat from datasheet), referred to the winding(s) the datasheet states it on (normally the primary). A single unqualified I_sat; when the datasheet states I_sat at explicit inductance-drop criteria, use saturationCurrents instead (or in addition).",
  "type": "number",
  "minimum": 0
},
"saturationCurrents": {
  "description": "Saturation-current table: I_sat at one or more inductance-drop criteria (|dL/L| %), referred to the winding(s) the datasheet states it on (normally the primary).",
  "type": "array",
  "items": { "$ref": "#/$defs/magneticDatasheetSaturationCurrent" }
}
```

Nothing else changes: no new required fields, and no change to `inductance`, `turnsRatios`,
`dcResistances` or `leakageInductance`.

## Compatibility

Additive and optional, so every currently valid document stays valid. Consumers that ignore
unknown optional fields are unaffected. Kelvin's `magnetic_saturation_current()` already reads
`saturationCurrentPeak` / `saturationCurrents` from `electrical[0]` whatever the subtype.

## Data that lands with it (separate change set)

694 Würth Midcom flyback / PoE transformers re-ingested into TAS `data/magnetics.ndjson` from the
Midcom *Smart Transformer Selector Database Rev42* workbook, as `subtype: "transformer"` with
`inductance`, `turnsRatios`, `dcResistances`, `leakageInductance {maximum}`, and I_sat where a
datasheet source states it.

## Alternatives considered

- **File as `coupledInductor`.** Rejected: its `inductance` is per-winding, not magnetizing.
- **Drop I_sat.** Rejected: it discards the selection figure the datasheet publishes.
