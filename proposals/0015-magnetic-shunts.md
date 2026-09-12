# MAS-RFC 0015 — Magnetic shunts: `magnetic.shunts[]`

- **Status:** Accepted (owner decision 2026-09-12, approved by Alf; implementation in the same change set)
- **Type:** Additive (non-breaking) schema change. No core-material data lands with it: see the
  data section — three of the four sheet grades surveyed cannot be filed without inventing a
  value, and the fourth is already in the database.
- **Author:** Alfonso Martínez (drafted 2026-09-12 with Alf)
- **Created:** 2026-09-12
- **Depends on:** nothing schema-wise. Reuses `magnetic/core/material.json` for the shunt
  material and `utils.json` coordinates/dimensions.

## Summary

An *integrated leakage* transformer — an LLC resonant transformer with its series inductance
built in, a flyback with a designed leakage, a current-limiting welding transformer — is built
by putting a deliberate piece of permeable material where the leakage flux runs: a ferrite plate
or a ferrite-polymer sheet in the winding window, between two sections, on a column, or outside
the window against the core. That piece is a **magnetic shunt**. It is what sets the leakage
inductance, it saturates and dissipates like any other permeable part, and MAS cannot describe
it at all.

A shunt belongs to neither the core nor the coil: it is not a piece of the magnetic circuit the
core maker ships (it is added at assembly, often by the winder), and it is not a conductor. It
also must not be expressed through `core.geometricalDescription`, which the reference
implementation regenerates on autocomplete and which no model reads. This RFC therefore attaches
it to the assembled component: `magnetic.shunts[]` (owner decision, 2026-09-12).

## What is proposed

```jsonc
// magnetic.json — add
"shunts": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "name":        { "type": "string" },
      "placement":   { "enum": ["inWindow", "betweenSections", "onColumn", "outsideWindow"] },
      "coordinates": { "$ref": "utils.json#/$defs/coordinates" },  // centre, main-column frame
      "dimensions":  { "$ref": "utils.json#/$defs/dimensions" },   // width radial, height axial (sheet thickness), depth across the window
      "gapToColumns": {
        "type": "object",
        "properties": { "inner": { "type": "number" }, "outer": { "type": "number" } }
      },
      "segments": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": { "length": { "type": "number" }, "gap": { "type": "number" } }
        }
      },
      "material": {
        "oneOf": [ { "$ref": "magnetic/core/material.json" }, { "type": "string" } ]
      }
    },
    "required": ["placement", "coordinates", "dimensions", "material"]
  }
}
```

`placement` names the topology of the shunt's flux path, which is what decides whether it enters
only the leakage network (`inWindow`, `betweenSections`, `outsideWindow`) or the magnetising one
as well (`onColumn`). `gapToColumns` carries the two air gaps that dominate the shunt branch's
reluctance and are the designer's tuning knob. `segments` describes a shunt built from several
pieces in series with gaps between them, which is how a large leakage is trimmed in production.

**Material reuses `magnetic/core/material.json`.** A ferrite-polymer sheet is a permeable
material and needs exactly what that schema already holds: initial and complex permeability,
saturation, resistivity, loss data, temperature dependence. Introducing a parallel "shunt
material" vocabulary would duplicate all of it; insulation materials, the other candidate, have
no permeability at all. As with every other material reference in MAS, either the full record or
the name of one is accepted.

Every new object is sealed (`additionalProperties: false`) and every new property carries a
one-sentence `description`.

### Data: the sheet materials

The sheets used as shunts are described as core materials like anything else permeable. What the
2026-09-12 datasheet sweep found, and what it means for the bundled database:

| Grade | Published permeability | Published saturation | Status in `data/core_materials.ndjson` |
|---|---|---|---|
| TDK FPC film C350 (and C351) | initial µi 9 ±30 % at 1 MHz, 25 °C | 255 mT at H = 25 kA/m, 10 kHz, 25 °C | **already filed** (records `C350`, `C351`, with resistivity 500 Ω·m, density 2930 kg/m³ and a loss factor) — nothing to add |
| TDK Flexield IFL04 | µ′ 45 and µ″ 1.3 at 13.56 MHz; no initial permeability, no temperature | 100 mT at H = 1194 A/m; no temperature | **cannot be filed** |
| Fair-Rite flexible sheets M1…M6 | µ′ 20 / 45 / 60 / 120 / 140 / 220, printed with **no frequency**; µ″ as curves only | **none published** — Fair-Rite issues no material data sheet for the M grades at all | **cannot be filed** |
| 3M FFDM EM15TF | µ′ 150 at 3 MHz (not split into µ′/µ″) | **none published** | **cannot be filed** |

`magnetic/core/material.json` requires `saturation` and requires `permeability.initial`, and
`saturation` items require a temperature. Three of the four grades publish no saturation flux
density of any kind, and none of the three flexible sheets publishes an *initial* permeability —
what they publish is µ′ at an RF measurement frequency, which is a different quantity from the
near-zero-excitation, ≤ 10 kHz figure the field is defined as. Filing them would mean inventing
either a saturation figure or a measurement condition, so **no record is added for them** and the
gap is reported rather than papered over. Resolving it needs an owner decision that is outside
this RFC: either those two `required` entries are relaxed for materials whose makers publish
neither (a separate, additive schema change), or these sheets stay out of the catalogue and a
shunt using one carries its material inline.

Naming, when records do get filed: **material class plus the distinguishing property** per the
material-naming rule — `Ferrite Polymer 9`, `Flexible Ferrite 45` — never the product family or
part number the material was measured on, with the vendor identification in `manufacturerInfo`
and `commercialName`. (The two FPC records already in the database are named by their grade code,
`C350` / `C351`, which predates that rule; renaming them is a breaking change and is not proposed
here.)

## What is explicitly NOT proposed

- **No shunt geometry in `core.geometricalDescription`.** That list is regenerated on
  autocomplete; a shunt placed there would be silently deleted.
- **No shunt model, sizing rule or reluctance ladder in MAS.** The energy/reluctance model
  (Zhang 2014 and successors), the `B_shunt` and `P_shunt` figures and the sizing pass belong to
  the reference implementation; MAS only describes the part.
- **No new material schema, and no new required field on `core/material.json`.** In particular
  no fabricated resistivity or loss data for the sheets (see RFC on resistivity's
  de-requirement, CHANGELOG 1.0.0+).
- **No shunt on the `core`,** and no change to `spacer.json`: a spacer separates core pieces in
  the main flux path, a shunt bridges a leakage path. They are different parts.
- **No output field** for shunt flux density or loss in this RFC; when the model exists, its
  outputs get their own additive change.

## Why

Attaching shunts at magnetic level follows the part's own life: it is added when the core and
coil are assembled, it interacts with both (its position is given in the coil's window, its gaps
are to the core's columns), and it is what makes the *assembled* component behave differently
from the sum of core and coil. Any other attachment point forces one of two errors — a coil that
claims to own a piece of ferrite, or a core description that claims a piece the core maker never
shipped.

The four `placement` values are not a taxonomy for its own sake: they are the four distinct flux
topologies in the literature (shunt inside the window; shunt filling the insulation gap between
primary and secondary; shunt on the column, which changes the magnetising reluctance too; shunt
outside the window bridging the legs), and a model has to branch on them.

## Compatibility

Additive and optional; ships in the next MINOR release. Existing documents stay valid (`shunts`
absent = a part with no shunt, which is every part described so far). The generated bindings gain
`Magnetic::shunts` as an optional vector plus the new `MagneticShunt`,
`MagneticShuntGapToColumns` and `MagneticShuntSegment` types; the shunt material resolves to the
same core-material-or-name union the core already uses.

## Consumers

- **MKF**: a leakage-inductance method selected when `shunts` is non-empty (winding energy by
  the existing Dowell/MMF integration, shunt and core branches by a reluctance ladder using
  `dimensions`, `gapToColumns` and `segments`); `B_shunt` and, where the material publishes a
  complex permeability, `P_shunt`; magnetising inductance unchanged unless `placement ==
  onColumn`; a leakage-target filter and an optional shunt-sizing pass; the 2D painter draws it.
  A shunt material without permeability is a loud failure.
- **MVB++**: a `ShuntBuilder` box or annulus at `coordinates`/`dimensions`, cut back by
  `gapToColumns`, split when `segments` is given; named `Shunt_<i>`; an obstacle in the collision
  gate and a cutter for the bobbin when it sits inside it.
- **OMFEM**: `shunt_<i>` is its own region with its own material properties, its own loss bucket
  and, for sheets, the complex-permeability path.
- **WebFrontend**: display only.

## Sources

Zhang, *Leakage inductance calculation for transformers with magnetic shunts* (2014) —
reluctance ladder and the segmented-shunt series-gap treatment; Li (2018) integrated-leakage
E-core transformer with a µ′ 45 sheet; Ansari et al. (2020–2023) on ferrite-polymer and flexible
ferrite sheets used as shunts (µ′ 9 to 220); FEMMT's `StrayPath`, the one open-source shunt
model, for the placement vocabulary in use; the sheet datasheets themselves (TDK Flexield IFL
series and FPC series, Fair-Rite flexible-material sheets, 3M electromagnetic-absorber sheets)
for the material records; McLyman for the window-geometry leakage baseline the shunt modifies.
