# MAS-RFC 0010 — Adopt the shared PEAS `pinout` / `landPattern` types for finished magnetics

- **Status:** Draft
- **Type:** Additive (non-breaking)
- **Author:** _to be assigned_
- **Created:** 2026-08-01

## Summary

On 2026-08-01 the family-wide per-terminal function map and the recommended-PCB-land-pattern
types were hoisted to PEAS (`https://psma.com/peas/utils.json#/$defs/{pinFunction, pin, pinout,
landPatternPad, landPattern}`), consolidating five previously divergent module-local
representations (AAS `pinout`, CTAS `pins`/`controllerPinFunction`, CONAS `pcbFootprint`,
CONAS `signalRole`; the fifth is MAS `bobbin.pinout`). AAS, CTAS, CONAS, SAS, RAS, TDAS, CAS
and COAS now `$ref` the PEAS types, and a PEAS guard test
(`PEAS/tests/test_schemas.py::test_no_module_local_pinout_or_landpattern`) fails on any module
that re-declares them. **MAS was deliberately excluded** — it is committee-stewarded with its
own RFC process, so this RFC proposes the adoption instead of imposing it.

## What is proposed

Add to the **finished magnetic component's** datasheet-side mechanical description (exact
attachment point to be settled by the committee — the natural candidate is alongside the
existing mounting/dimension fields consumed from `manufacturerInfo`):

1. `pinout` — `$ref https://psma.com/peas/utils.json#/$defs/pinout`. Per-terminal
   `(pin, name, function)` triples. The PEAS `pinFunction` vocabulary already carries the
   magnetics values `windingStart`, `windingEnd`, `tap`, `shield`, plus the generic
   `ground`/`noConnect`/`mechanical`. Missing vocabulary (e.g. `auxiliaryWinding` is already
   present from the CTAS merge) is ADDED to PEAS `pinFunction` per the complete-union rule,
   never forked locally.
2. `landPattern` — `$ref https://psma.com/peas/utils.json#/$defs/landPattern`. The
   datasheet's recommended pad/hole pattern: pad centres, copper sizes, drills (slotted
   drills supported — relevant for large-terminal chokes), `originDatum`,
   `recommendedBoardThickness` (press-fit terminals).

## What is explicitly NOT proposed

- **`bobbin.pinout` stays as it is.** It is a bobbin *manufacturing* specification (per-row
  pitch arrays, pin geometry, winding-to-pin connections) — a different concept from the
  finished part's terminal function map. No rename, no migration, no deprecation.
- No breaking change to any existing MAS field; both proposed fields are optional.

## Why

- A transformer's `windingStart`/`windingEnd`/`shield` terminal map becomes machine-comparable
  with every other family's pinout (the SAS/CTAS/AAS/CONAS side already is), enabling
  cross-family netlist stitching in CIAS/Kirchhoff without a magnetics-only special case.
- The recommended land pattern is the missing datasheet-side geometry for board-level
  EMI work (loop area from the pad coordinates of a choke's terminals) — the same motivation
  that drove the connector-side hoist.

## Compatibility

Additive and optional; no existing MAS document changes validity. MAS already references
PEAS utils (`MAS references PEAS utils these days` — the shared-types direction is
established); this adds two more `$ref`s in the same direction. No reverse dependency is
created (PEAS refs nothing in MAS).

## Consumers

MKF/MVB/WebFrontend are unaffected until they opt in; the generated-binding impact is two new
optional types (`Pinout`, `LandPattern`) in `MAS.hpp` on the next regeneration.
