# MAS-RFC 0002 — Conformance classes

- **Status:** Withdrawn (2026-07-02). The `masConformance` field and the conformance-class bundles (`schemas/conformance/`, `scripts/validate-conformance.py`, `tests/conformance/`) were removed when the PEAS root object was closed: rather than carve MAS-specific keys into the shared PEAS container, `masConformance` was retired. This RFC is kept as a historical record; a future conformance mechanism would need a fresh proposal that does not add a top-level discriminator to the PEAS-shared document root.
- **Type:** Additive (target: 0.2.0); enforcement breaking at 1.0.0
- **Author:** _to be assigned_
- **Created:** 2026-04-26

## Summary

Define three named conformance classes — **A: Inductor Basic**, **B:
Transformer**, **C: Full** — so that small implementations can claim
partial conformance without forking the schema. Provide one schema bundle
per class plus a normative test-vector set.

## Motivation

The current single monolithic schema is hostile to small implementations:
a motor-drive vendor that only needs choke descriptions must still know
about LLC topologies, multi-winding leakage, insulation coordination and
stray capacitance. IEC standards routinely solve this with conformance
classes (61131, 61850, 62541). MAS must too before the IS submission.

A secondary benefit: a conformance suite gives PSMA a deliverable
("MAS-Class-B Certified") that is meaningful to procurement, where the
schema itself is not.

## Proposal

### Class definitions

| Class | Required sections | Required topology coverage | Required outputs |
|-------|-------------------|----------------------------|------------------|
| **A** Inductor Basic | inputs, magnetic.core, magnetic.coil (1 winding) | buck, boost, single inductor | inductance |
| **B** Transformer | A + multi-winding coil + bobbin + insulation | A + flyback, forward (single/two-switch), push-pull, isolated buck/buck-boost | A + windingLosses, coreLosses |
| **C** Full | B + every schema field | all 16 topologies + custom | every output type |

A document **conforms to class X** iff:

1. It validates against `schemas/conformance/class-X.json` (a strict
   subset bundle with `additionalProperties: false` at every level it
   doesn't reference).
2. It declares `masConformance: "A" | "B" | "C"` at the root.
3. The implementation passes the test vectors under
   `tests/conformance/class-X/`.

### Schema layout

Add `schemas/conformance/`:

```
schemas/conformance/
  class-A.json   # restrictive bundle imports MAS.json + tightens
  class-B.json
  class-C.json   # equivalent to current MAS.json
```

Each class bundle is a thin wrapper using `allOf` + `unevaluatedProperties:
false` so unknown extensions are caught at the requested rigour, not at
the loosest baseline.

### Test vectors

Move existing samples into class buckets:

```
tests/conformance/class-A/  buck_inductor.json, boost_inductor.json
tests/conformance/class-B/  flyback_transformer.json, push_pull_transformer.json, ...
tests/conformance/class-C/  (everything; superset)
```

Each vector has a sibling `.expected.json` listing the validation result a
conforming implementation must produce.

### Versioning of conformance

Conformance classes are versioned independently of MAS. A document carries
`masVersion` (the schema version) and `masConformance` (the class). Class
*definitions* may evolve under the SemVer rules of `GOVERNANCE.md` §4
(MAJOR-change process).

## Migration policy

- 0.2.0: add `class-A.json`, `class-B.json`, `class-C.json`; `class-C` is
  the existing schema renamed.
- 0.3.0: tooling (validator, `mas-cli check`) supports `--class A|B|C`.
- 1.0.0: `masConformance` becomes required.

## Open questions

1. Should there be a **Class D — Manufacturer Catalogue** (just core /
   wire / bobbin records, no full magnetic)? Probably yes; defer.
2. Where do *outputs-only* documents fit (a tool reporting losses without
   redescribing the magnetic)? Need a separate "result document"
   conformance, possibly Class O.
3. Does PSMA want to run a certification programme, or is self-declaration
   enough? Affects whether the test vectors must be sealed.
