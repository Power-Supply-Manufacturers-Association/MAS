# MAS-RFC 0010 — Electrostatic shielding requirement

- **Status:** Draft
- **Type:** Additive (target: 1.1.0)
- **Author:** Grant Pitel ([@gpitel](https://github.com/gpitel))
- **Created:** 2026-07-17

## Summary

Add an optional `shielding` array to `inputs/designRequirements.json`. Each
entry declares an electrostatic (Faraday) shield between a pair of windings.
Shields are a *requirement* consumed at coil materialization time — the engine
inserts SHIELDING-typed layers at the insulation interfaces of the pair — not
extra entries in `functionalDescription`.

## Motivation

Electrostatic shields between windings are standard practice for breaking
inter-winding capacitive coupling: a grounded copper foil between primary and
secondary diverts common-mode displacement current to ground (McLyman,
*Transformer and Inductor Design Handbook* 3rd ed., ch. 17 §9; Lee,
*Electronic Transformers and Circuits*, §83 covers the wound-screen variant).
MAS today has no way to express them:

- `functionalDescription` models *windings*. A shield is a conductor but not a
  winding — modeling it as a one-turn winding corrupts `turnsRatios`, demands
  a fake excitation in every operating point, and miscounts isolation sides.
- The coil description already *can represent* the result — `layer.type`
  already includes `shielding` — but nothing upstream of the coil can request
  it, so the only route today is hand-authoring `layersDescription`.

A requirement-level declaration keeps the electrical model clean and lets the
engine own placement, sizing, and insulation-stack integration.

## Proposal

Add a `shielding` property to `inputs/designRequirements.json`:

```json
"shielding": {
    "description": "List of electrostatic shields that must be placed between windings",
    "type": "array",
    "items": {
        "title": "shieldingRequirement",
        "type": "object",
        "properties": {
            "name": {
                "description": "A label that identifies this shield",
                "type": "string"
            },
            "type": {
                "description": "Construction of the shield: a continuous foil (near-complete coverage, must stay much thinner than a skin depth to limit eddy loss), or a screen wound from wire like a winding layer (runs on standard winding equipment, lower eddy loss, partial coverage)",
                "title": "shieldingType",
                "type": "string",
                "enum": ["foil", "wound"],
                "default": "foil"
            },
            "wire": {
                "description": "Name of the wire the screen is wound from, when the shield type is wound. The shield layer thickness follows the wire outer diameter",
                "type": "string"
            },
            "betweenWindings": {
                "description": "Names of the two windings between which the shield must be placed, as windings are referenced by name throughout MAS. The shield is inserted at every interface where sections of these two windings are adjacent, unless restricted by interfaces",
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2
            },
            "interfaces": {
                "description": "Zero-based ordinals of the insulation interfaces of the wound coil (counted in winding order, wrap-around interface last) at which the shield must be placed. If absent, the shield is placed at every interface where the two windings are adjacent",
                "type": "array",
                "items": {"type": "integer", "minimum": 0},
                "minItems": 1,
                "uniqueItems": true
            },
            "material": {
                "description": "Material of the shield, by default copper",
                "type": "string",
                "default": "copper"
            },
            "thickness": {
                "description": "Thickness of the shield, in m",
                "type": "number",
                "exclusiveMinimum": 0
            },
            "coverage": {
                "description": "Proportion of the winding window breadth covered by the shield, from 0 to 1. Ignored when margin is present",
                "type": "number",
                "exclusiveMinimum": 0,
                "maximum": 1,
                "default": 1
            },
            "margin": {
                "description": "Distances at the extremes of the winding window kept clear by the shield, in m. Two-element array, from 'inner or top' to 'outer or bottom', like section margins. Takes precedence over coverage",
                "type": "array",
                "items": {"type": "number", "minimum": 0},
                "minItems": 2,
                "maxItems": 2
            },
            "connection": {
                "description": "How the shield termination is connected. A shield terminates at one point only — the other end is left unconnected to avoid a shorted turn — so unlike windings there is a single connection instead of a start-finish pair",
                "$ref": "../magnetic/coil.json#/$defs/connection"
            },
            "terminatedTo": {
                "description": "Name of the winding whose quiet node the shield single-ended termination is connected to",
                "type": "string"
            }
        },
        "required": ["betweenWindings"]
    }
}
```

### Semantics

- **Placement.** The engine inserts a SHIELDING layer inside each insulation
  interface between sections of the named pair (insulation | shield |
  insulation), at materialization time. `interfaces` selects specific
  occurrences by ordinal so interleaved constructions (P-S-P) can shield only
  the interfaces that need it; absent, every interface of the pair — including
  the wrap-around last-to-first interface — is shielded.
- **Windings are referenced by name**, consistent with `partialWindings`,
  turns, and bobbin connections. Renames must propagate (reference
  implementations do).
- **Sizing.** Foil: `thickness` (a library default applies when absent).
  Wound: layer thickness is the named wire's outer diameter. Breadth comes
  from `coverage`, or from `margin` when present (asymmetric margins shift the
  shield center).
- **Termination.** A shield terminates at exactly one point (`connection`);
  the other end floats to avoid a shorted turn around the core. `chassis`
  terminations model safety-ground shields; `terminatedTo` records the
  intended quiet node for future capacitance modeling.

## Migration policy

Purely additive: documents without `shielding` are unaffected, and no existing
field changes meaning. Documents that *use* `shielding` will not validate
against earlier schema releases (`designRequirements` is a closed object), so
this rides a MINOR release. Casing of the `shieldingType` enum follows
RFC 0007.

## Cost

Schema + regenerated bindings (C++, TypeScript, Python), engine
materialization, and UI. A complete working implementation of exactly this
shape exists across the stack (schema, MKF layer insertion including
interleaving and margins, wasm, builder UI, summary rendering) and will be
submitted as the linked implementation PRs on acceptance.

## Open questions

1. Should the insulation coordinator credit a grounded shield between the pair
   (the reference implementation keeps full insulation on both sides —
   conservative w.r.t. IEC 60664 / 61558)?
2. Is shielding the wrap-around interface by default the right call, or should
   it be opt-in via `interfaces`?
3. Overall/outer shields around the whole winding stack (McLyman ch. 17
   distinguishes them from inter-winding shields) — a future `placement`
   field, or out of scope?
4. Should shield grounding state feed insulation-system modeling once both
   exist?
