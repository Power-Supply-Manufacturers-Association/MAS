# MAS-RFC 0016 — Lead sleeving: `connection.sleeve`, insulation-material `form` / `cti`

- **Status:** Accepted (owner decision 2026-09-12, approved by Alf; implementation in the same change set)
- **Type:** Additive (non-breaking) schema change
- **Author:** Alfonso Martínez (drafted 2026-09-12 with Alf)
- **Created:** 2026-09-12
- **Depends on:** nothing schema-wise; complements RFC 0013 (the `end` a sleeved lead terminates)
  and RFC 0012 (the other terminal details on `connection`).

## Summary

The lead is the least insulated part of a wound component and the one that crosses the safety
boundary. It leaves the winding, crosses the margin band, runs along the flange past the other
isolation side's pins and ends on its own pin — with nothing but its enamel, which is not
insulation in the safety sense. Winding shops therefore slide a sleeve over it, and every
construction sheet says so: sleeve the primary leads from the inner edge of the margin to the
pin.

MAS cannot express any of that. `coil.connection` has a `length` and a `diameter` but no
insulation; insulation materials have no supply form, so nothing distinguishes sleeve stock from
tape; and the insulation-coordination output reports one set of clearance/creepage figures for
the coil's section interfaces, with no line for the leads. This RFC adds the three small pieces.

## What is proposed

### 1. `coil.json#/$defs/connection.sleeve`

```jsonc
"sleeve": {
  "type": "object",
  "properties": {
    "material":           { "oneOf": [ { "$ref": "./insulation/material.json" }, { "type": "string" } ] },
    "wallThickness":      { "type": "number", "exclusiveMinimum": 0 },
    "innerDiameter":      { "type": "number", "exclusiveMinimum": 0 },
    "overlapIntoWinding": { "type": "number", "minimum": 0 },
    "numberLayers":       { "type": "integer", "minimum": 1, "default": 1 }
  },
  "required": ["material", "wallThickness", "innerDiameter"]
}
```

The three required fields are what makes a sleeve a sleeve and what every consumer needs: the
material (for dielectric strength, temperature class and permittivity), the wall (the distance
through insulation it provides) and the inner diameter (the fit over the lead, and with the wall
the outer diameter the margin and the bend radius have to accommodate). `overlapIntoWinding` is
how far it reaches back over the wound part — the practice construction sheets state as a
couple of millimetres past the margin's inner edge, recorded rather than assumed.
`numberLayers` covers the doubled or tripled sleeve used for reinforced insulation.

### 2. `magnetic/insulation/material.json` — `form` and `cti`

```jsonc
"form": { "type": "string", "enum": ["tape", "film", "sleeve", "varnish"] },
"cti":  { "type": "number" }
```

`form` is what lets a coordinator *pick* sleeve stock: today a material database says PTFE and
polyester exist but not that one is supplied as a sleeve and the other as tape, so choosing a
sleeve material means hard-coding a name. `cti` is the comparative tracking index per IEC 60112
in volts, which with pollution degree is what IEC 60664-1 turns into a required creepage
distance.

> **Note on the name `cti`.** The glossary already uses `cti` for the material *group*
> (`groupI`, `groupII`, `groupIIIA`, `groupIIIB`) as it appears in insulation-coordination
> inputs. The field added here is the measured index in volts, from which that group follows.
> The two live in different schemas and the field's `description` states which is which; this
> RFC does not rename either.

### 3. `outputs.json` `insulationCoordinationOutput` — `leadCreepage` (WITHDRAWN 2026-09-13)

> Withdrawn by Alf on 2026-09-13 after landing: the definition it was added to is unreachable
> (the property references the PEAS mirror) and the value is a report, not an input. MKF's
> insulation-coordination result carries per-lead creepage and the sleeved flag instead; no
> schema field. The text below is kept for the record.

```jsonc
"leadCreepage": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "winding":          { "type": "string" },
      "end":              { "enum": ["start", "finish", "tap"] },
      "creepageDistance": { "type": "number" },
      "sleeved":          { "type": "boolean" }
    }
  }
}
```

One entry per terminated winding end: the creepage actually available along that lead and whether
it is sleeved. It is reported separately from the coil's figures because the lead runs *outside*
the winding, where the section-to-section coordination does not apply.

**Reachability caveat, to be resolved before a consumer relies on it.**
`outputs.json#/$defs/insulationCoordination` (title `insulationCoordinationOutput`) is the
definition this field is added to, exactly as approved. That definition is currently **not
referenced by any path**: `outputs.json#/properties/insulationCoordination` points at the PEAS
mirror `https://psma.com/peas/outputs/insulationCoordination.json`, so a document's
`outputs[].insulationCoordination` is validated by PEAS's copy and the generated binding takes
its members from there. `leadCreepage` is therefore present and valid in MAS but unreachable
from a MAS document until one of two decisions is taken, neither of which is in scope here:
re-point `outputs.json#/properties/insulationCoordination` at the local definition (a MAS
change), or add the field to the PEAS mirror (a PEAS change, and PEAS is the shared root).
This is flagged, not worked around.

Every new object is sealed (`additionalProperties: false`) and every new property carries a
one-sentence `description`.

## What is explicitly NOT proposed

- **No sleeve requirement.** A document with no `sleeve` describes a part with bare leads, which
  is what every document describes today.
- **No creepage or sleeve-selection rule in MAS.** Whether a lead needs a sleeve, what wall it
  needs and which material is picked is insulation-coordination logic in the reference
  implementation; MAS records the result.
- **No sleeve geometry.** Where the sleeve runs is the routed lead's path (RFC 0013's
  reservation and the drawing), not data. Only its cross-section and overlap are recorded.
- **No renaming of the existing `cti`** vocabulary, and no new material-group enum.
- **No change to PEAS.** The `leadCreepage` field is added to the MAS definition only; the PEAS
  mirror is untouched (see the reachability caveat).
- **No wire-coating change.** A sleeve is an added part, not a coating; triple-insulated wire
  stays a `wire` property.

## Why

A sleeve changes numbers that are wrong without it. It is the distance through insulation on the
lead path, so it decides whether the design meets reinforced insulation at all; it is an outer
diameter three to four times the wire's, so it decides whether the lead fits the margin band and
what bend radius the terminal can take; and it is the reason a lead is *allowed* to cross the
margin, which the keep-out rule currently forbids unconditionally. `form` is the smallest field
that turns a material database into something a coordinator can select from, and `cti` closes
the last input IEC 60664-1 needs that MAS did not hold.

## Compatibility

Additive and optional; ships in the next MINOR release. Existing documents stay valid. The
generated bindings gain `ConnectionElement::sleeve` (a new `ConnectionSleeve` type),
`InsulationMaterial::form` and `::cti`. `leadCreepage` generates no member while the definition
it lives on stays unreferenced (see the caveat), which is also why it breaks nothing.

## Consumers

- **MKF**: insulation coordination gains a lead-sleeve requirement calculation (same withstand
  voltage as the section interfaces; a sleeve is needed when the wire's own coating does not
  already cover the required layers *and* the lead crosses a margin or flange slot on a
  safety-isolated interface), chooses the material from the insulation database filtered by
  `form == sleeve` and temperature class, fills `connections[].sleeve` and the `leadCreepage`
  output, and reserves the sleeved outer diameter in the connection's blocked space; the
  margin keep-out becomes conditional on the lead being sleeved.
- **MVB++**: a second sweep of each lead run at the sleeved radius, named as a sleeve solid,
  spanning terminal to `overlapIntoWinding` past the margin; the sleeved outer diameter drives
  the terminal bend radius and the margin fit check.
- **OMFEM**: `sleeve_<w>_<k>` is a dielectric region (permittivity for capacitance, insulation
  conductivity for thermal); air to the field solvers.
- **WebFrontend**: display only.

## Sources

Power Integrations AN-18 and its ETD44 construction sheet (sleeve the primary leads from the
margin's inner edge to the pin; TIW construction needs neither margins nor sleeving); Lodestone
Pacific bobbin application notes (sleeve practice and the creepage barrier); IEC 60664-1
(creepage from working voltage, pollution degree and material group), IEC 60112 (the tracking
index itself), IEC 61558-1 / IEC 62368-1 (the withstand requirements a sleeve serves); IPC-A-610
and Mini-Circuits AN40-010 for the terminal-wrap practice a sleeved lead ends in.
