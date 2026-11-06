# MAS-RFC 0020 — Fill factor of the core in `effectiveParameters`

- **Status:** Draft
- **Type:** Additive (one new optional property; every document valid today stays valid).
- **Author:** drafted 2026-11-07
- **Created:** 2026-11-07
- **Depends on:** nothing.

## Summary

Add an optional `fillFactor` to `effectiveParameters` (`schemas/magnetic/core.json`). It is the
fraction of the gross cross-section that is magnetic material: the stacking or lamination factor of
a tape-wound or laminated core. `effectiveArea`, `minimumArea` and `effectiveVolume` already include
it. The new field records the factor that was applied, so a reader can see it and trace it.

## Motivation

A tape-wound core (nanocrystalline, amorphous, or electrical-steel tape wound as a toroid or C core)
is a spiral of ribbon with insulation, oxide and air between the layers. Its iron section is only a
fraction of the section the shape dimensions give. Since MKF dae6ae93 (2026-11-03), the engine
looks up that fraction from the material's `laminationThickness` and the makers' published values.
It then writes the reduced `effectiveArea` / `minimumArea` / `effectiveVolume` into
`processedDescription.effectiveParameters`. For example, a T 40/24/16 core in VITROPERM 500F gets
k_f = 0.71 and Ae = 88.9 mm², against a gross 125 mm².

The processed description stores the result but not the factor. Two consequences:

- **A saved part cannot be audited.** A user who uploads measured core-loss data states the flux
  density B they applied, and B = Φ / Ae. To check that B against the stored part, they need to know
  whether its Ae is gross or net, and by which factor. A CoreDataX user raised exactly this.
  Today the only way is to rebuild the part in an engine of the same version.
- **Engine changes are invisible.** When the factor's source changes, as it did when the flat 0.80
  was replaced, every stored tape-wound Ae changes silently. A stored factor makes the difference
  visible: the gross area is Ae / k_f.

## Change

In `schemas/magnetic/core.json`, `$defs/effectiveParameters/properties`:

```jsonc
"fillFactor": {
    "description": "Fraction of the gross cross-section that is magnetic material (stacking or lamination factor of a tape-wound or laminated core). effectiveArea, minimumArea and effectiveVolume already include it. Absent for solid cores (ferrite, powder), where it is 1 by construction.",
    "type": "number",
    "exclusiveMinimum": 0,
    "maximum": 1
}
```

It is not added to `required`. `additionalProperties: false` stays.

Docs: add the field to the `effectiveParameters` table in `docs/`, and add one tape-wound sample to
`samples/` that carries it.

## Compatibility

- **Readers:** the field is optional, so no reader has to change. A reader that recomputes the
  gross area must not apply the factor a second time. The description says the areas already
  include it.
- **Writers:** MKF would write it from `Core::get_tape_wound_fill_factor` in `process_data`, and
  only for tape-wound cores. Other writers may omit it.
- **Bindings:** the generated C++/Python types gain an `std::optional<double>` / `Optional[float]`
  member.

## Alternatives considered

1. **Leave it out; show k_f only in the UI.** This is what CoreDataX does now: the builder asks the
   engine for the factor live. A saved part still loses it, and it cannot be audited offline.
2. **Store the gross area next to the net one (`grossEffectiveArea`).** This carries the same
   information, but it adds a second area that readers could mistake for the one to use. A factor
   in [0, 1] cannot be confused that way.
3. **Put it on the material (`laminationFactor` in `core/material.json`).** The factor depends on
   the material *and* the construction: the same ribbon gets a different VAC value as a toroid
   than as a cut core, and a laminated steel stack gets none. It belongs to the built core.

## Open questions

- Should the source of the factor also be stored, for example the citation string MKF returns with
  it ("VAC Tabelle 10.4 VITROVAC column, 25 um ribbon"), or a PEAS `provenance` object? The drafter
  leans towards a `provenance` reference rather than a free-text string, in line with MAS-RFC 0011.
