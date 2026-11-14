# MAS-RFC 0021 — Inductance and impedance curves on the datasheet `coupledInductor` electrical variant

- **Status:** Accepted (owner decision 2026-11-14, approved by Alf; implementation in the same change set, MAS 2.9.0)
- **Type:** Additive (non-breaking) schema change.
- **Author:** drafted 2026-11-14
- **Created:** 2026-11-14
- **Depends on:** nothing. Reuses the existing `magneticDatasheetInductancePoint` /
  `magneticDatasheetImpedancePoint` definitions unchanged.

## Summary

`magneticDatasheetCoupledInductorElectrical` (in `schemas/magnetic.json`) cannot state L(I) or
|Z|(f). `magneticDatasheetInductorElectrical` can, through `inductancePoints` /
`impedancePoints`. Both variants are closed (`additionalProperties: false`), so a measured
inductance roll-off curve or impedance curve for a part whose `subtype` is `coupledInductor`
has nowhere to go.

This is the same shape of gap as MAS-RFC 0017 (saturation current missing from `transformer`)
and MAS-RFC 0018 (R(f)/X(f) missing from `inductor`), and the same remedy: add the existing
fields to the variant that lacks them.

## Evidence

Trans-inductor voltage regulator (TLVR) inductors are two-winding parts: a primary carrying
the phase current and a secondary compensation winding that is chained across phases. Their
vendors print both windings:

    SLV9080-700KED   70 nH ±10 %   DCR ±10 %: Pri 0.19 mΩ, Sec 0.33 mΩ   (Coilcraft SLV9080 page)
    SLV1211-700KED   70 nH ±10 %   DCR ±10 %: Pri 0.125 mΩ, Sec 0.41 mΩ  (Coilcraft SLV1211 page)

82 TLVR parts are in the catalogue today (39 Eaton TL/TLP, 20 Pulse PAL6374 HL and PGL7195 /
PGL6520, 13 Coilcraft SLV9080/SLV1211, 10 Würth WE-HCMD). Every one of their vendors prints both
windings' DC resistance; Eaton and Würth also print the coupling coefficient. All 82 were stored
as `subtype: inductor` with one winding, because only that variant could hold the data they
arrived with:

- 23 carry a measured `inductancePoints` L(I) curve (Coilcraft's L vs current vs temperature
  charts; Würth's REDEXPERT curves);
- the 10 Würth parts also carry a measured `impedancePoints` |Z|(f) curve.

A downstream part-substitution engine (Kelvin) compares parts within the same subtype, and
offered SLV9080-700KED as a substitute for a single-winding power inductor. With
`coupledInductor` the two-winding nature is stated, both DC resistances fit in the existing
`dcResistances[]`, and the substitution gate separates the two kinds. Re-subtyping without this change
would force deleting the 23 measured L(I) curves and 10 impedance curves — data loss adopted for a
plumbing reason.

## Why the quantities belong on the variant

L(I) and |Z|(f) are properties of any magnetic with a defined inductance, not only of a
single-winding inductor. The coupled variant already states `inductance`,
`saturationCurrentPeak` and `saturationCurrents[]`; the roll-off curve is the full form of the
saturation figures it already accepts. For a coupled part the curves are measured on the
winding whose `inductance` is stated (the primary for a TLVR), which is the same reference
the variant's scalar `inductance` already uses.

## Change

In `magneticDatasheetCoupledInductorElectrical.properties` add:

```json
"inductancePoints": {
    "description": "Inductance vs. DC-bias current points (inductance roll-off / saturation curve), optionally per temperature, measured on the winding whose inductance is stated.",
    "type": "array",
    "items": {"$ref": "#/$defs/magneticDatasheetInductancePoint"}
},
"impedancePoints": {
    "description": "Impedance vs. frequency points, measured on the winding whose inductance is stated.",
    "type": "array",
    "items": {"$ref": "#/$defs/magneticDatasheetImpedancePoint"}
}
```

Nothing else changes. The definitions are reused unchanged, so no new point shape is
introduced.

## Compatibility

Additive and optional: every document valid today stays valid. Generated bindings (C++ MAS
types) gain two optional members on the coupled-inductor electrical struct; consumers that do
not read them are unaffected.

## Follow-up (data)

Done with the implementation (TAS, 2026-11-14): the 82 TLVR records are `subtype:
coupledInductor` with their curves kept and `dcResistances[]` = [phase winding, compensation
winding] as each vendor prints them. The 39 Eaton records had stored the compensation winding's
DC resistance (DCR_pri, pins 3-4) as the part's only resistance; the conversion corrects that.
