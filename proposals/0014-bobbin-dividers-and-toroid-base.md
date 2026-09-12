# MAS-RFC 0014 — Multi-chamber bobbins (`dividers`, `numberChambers`) and the toroid base

- **Status:** Accepted (owner decision 2026-09-12, approved by Alf; implementation in the same change set)
- **Type:** Additive (non-breaking) schema change
- **Author:** Alfonso Martínez (drafted 2026-09-12 with Alf)
- **Created:** 2026-09-12
- **Depends on:** nothing schema-wise; complements RFC 0013 (the pins a base carries) and the
  existing `windingWindows` / `column` machinery of the coil and core processed descriptions.

## Summary

Two kinds of former that manufacturers ship by the thousand cannot be described in MAS today.

**Multi-chamber (split) bobbins.** A chambered former is a tube with interior walls that divide
the winding area into chambers, each holding one winding; the wall is the creepage barrier that
lets a mains transformer skip margin tape, and the side-by-side arrangement is what sets its
leakage inductance. MAS already expresses the *windows* — several `windingWindows` sharing one
`column` are stacked chambers (core.md) — but nothing describes the **wall** that makes them:
its thickness, where it sits, how far it reaches, or the slot a wire crosses through. 118 of the
504 bundled bobbin records are chambered, and say so only inside a free-text `variant` string.

**Toroid bases.** A wound toroid is mounted on a moulded base that holds the ring, sets the
standoff from the board and owns the pins. MAS has no way to say a part has one, so a toroidal
design stops at the bare ring: no standoff, no pins, no footprint, and leads that end in air.

Both are additive, optional fields on `bobbin.json`.

## What is proposed

### Part A — `processedDescription.dividers` and `functionalDescription.numberChambers`

```jsonc
// bobbin.json#/processedDescription — add
"dividers": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "thickness":   { "type": "number", "exclusiveMinimum": 0 },   // along the column axis
      "coordinates": { "$ref": "../utils.json#/$defs/coordinates" },// centre, main-column frame
      "height":      { "type": "number" },                          // radial reach; absent = as far as the flanges
      "crossingSlot": {
        "type": "object",
        "properties": {
          "width": { "type": "number" },   // along the divider rim
          "depth": { "type": "number" },   // radially inwards from the rim
          "angle": { "type": "number" }    // degrees, from +x around the column
        }
      }
    },
    "required": ["thickness", "coordinates"]
  }
}

// bobbin.json#/functionalDescription — add
"numberChambers": { "type": "integer", "minimum": 1 }
```

`dividers` is the geometry (processed description, the level every drawing and field consumer
reads); `numberChambers` is the functional statement a catalogue row can carry on its own,
before anybody has transcribed the wall drawing. A plain two-flange former is `numberChambers:
1`, which is also what absent means. The dividers are listed in the order they appear along the
column, and there are `numberChambers - 1` of them once both are given.

The IEC-style dimension labels vendors print for the wall and the chambers (`w1` for the wall
thickness, `c1..cN` for the chamber widths) go into the already-open `dimensions` map of the
functional description; they are admitted by documentation, not by a schema change.

### Part B — `functionalDescription.base` (family `t`)

```jsonc
// bobbin.json#/functionalDescription — add
"base": {
  "type": "object",
  "properties": {
    "mounting":     { "enum": ["horizontal", "vertical"] },
    "length":       { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "width":        { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "height":       { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "standoff":     { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "pocketInnerDiameter": { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "pocketDepth":  { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "boatWidth":    { "$ref": "../utils.json#/$defs/dimensionWithTolerance" },
    "maximumCoreOuterDiameter": { "type": "number" },
    "maximumCoreHeight":        { "type": "number" }
  },
  "required": ["mounting", "length", "width", "height", "standoff"]
}
```

**Decision D1 of the 2026-09-12 survey: a toroid base is a bobbin of family `t`.** It plays the
former's role — it carries the wound part, sets the standoff and owns the pins — so it reuses
`pinout`, `processedDescription.pins[]` and `connections[]` rather than introducing a second pin
vocabulary. The five required fields are the ones every base datasheet prints; the pocket fields
describe a horizontal base (ring laid flat), `boatWidth` a vertical one (ring on edge), and the
two maxima are the selection limits that say which wound core fits.

`orientation`, which already exists, keeps its former meaning (how the *bobbin* is mounted);
`mounting` is the toroid's. The finished part's own pinout stays at magnetic level (RFC 0010).

Every new object is sealed (`additionalProperties: false`) and every new property carries a
one-sentence `description`, as the rest of the schema does.

## What is explicitly NOT proposed

- No change to what a `windingWindow` means, and no new placement field: chambers are still
  windows sharing a `column`, and the coil still declares placement with the `windingWindow`
  indices of RFC 0009 / the winding-placement rules.
- No requirement anywhere. `numberChambers` without divider geometry stays valid data; it is the
  reference implementation that throws when it is asked to *wind* such a former, rather than
  invent a wall thickness.
- No new dimension labels in the schema: the wall and chamber labels live in the open
  `dimensions` map, documented.
- No toroid-base *selection* rule in MAS: filtering bases by `maximumCoreOuterDiameter` and
  `maximumCoreHeight` is model behaviour, not data.
- No second pin structure for bases, and no change to `pinout`.

## Why

A divider is not cosmetic. It is simultaneously the creepage barrier that replaces margin tape
on the interface it separates, the reason a split-bobbin transformer has the leakage inductance
it does (McLyman's side-by-side geometry, not the concentric one), and an obstacle the crossing
conductor has to pass through a slot. Each of those is a calculation that is wrong today, and
each needs exactly the same four numbers: thickness, position, reach, slot.

A base is the difference between a toroid that can be placed on a board and a ring. Its
standoff and pocket decide the part's height and footprint, its pins are where the leads
terminate (RFC 0013), and its two maxima are what makes automatic base selection possible.

## Compatibility

Additive and optional; ships in the next MINOR release. Every existing document stays valid —
all four fields absent means exactly today's meaning (a two-flange former, no base). The
generated bindings gain `std::optional` members: `BobbinFunctionalDescription::number_chambers`
and `::base`, `CoreBobbinProcessedDescription::dividers`, plus the new `BobbinBase`,
`BobbinDivider` and `DividerCrossingSlot` types. `base.mounting` reuses the generated
horizontal/vertical enum that `orientation` already uses.

## Consumers

- **MKF**: bobbin family processors emit one `WindingWindowElement` per chamber when the wall
  geometry is there, and throw when `numberChambers > 1` without it; insulation coordination
  treats a full-height divider of at least the required distance-through-insulation as the
  barrier between chambers and drops the tape section and margin on that interface; the
  connection reservation reserves the crossover through `crossingSlot`; `BobbinTDataProcessor`
  exposes the base and places the pins on its underside; base selection filters on the two
  maxima.
- **MVB++**: `BobbinBuilder` draws interior dividers as flange-like plates with the slot cut;
  a `BaseBuilder` draws the base (box with pocket, or boat) and its pins; the conductor builder
  picks the window by containment and follows the reserved crossover route.
- **OMFEM**: `divider_<i>` and the base become their own regions instead of being classified as
  core.
- **WebFrontend**: display only — chamber count and base dimensions on the part sheet.

## Sources

Multi-chamber formers: NORWE coil-former catalogue and TDK former datasheets (published wall
thicknesses, e.g. the 0.56 / 0.65 mm chamber walls of the RM6 / RM8 formers), Miles Platts
former catalogue (0.6 to 1.0 mm walls; 5- and 8-chamber ETD formers), Shulin's parametric
bobbin table (5,100 rows) for the range of chamber counts in production, McLyman *Transformer
and Inductor Design Handbook* eq. 17-5 for the side-by-side leakage geometry a chamber creates,
and IEC 60664-1 / IEC 61558 for the barrier role of the wall. Toroid bases: CB-Magnetics' open
base catalogue (134 bases with L×W×H and pin grids), TDK B64291 / B64292 / B64293 base tables,
and WE-CMB 744821240 for the toroid-on-base pin layout.
