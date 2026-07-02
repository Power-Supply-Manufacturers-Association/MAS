# MAS — Magnetic Agnostic Structure

A vendor-neutral data model for describing magnetic components used in
power electronics: their design requirements, physical construction, and
computed performance. MAS is incubated at OpenMagnetics and is being
prepared for transfer to the [PSMA](https://www.psma.com/) Magnetics
Committee for further stewardship.

## Status

| Aspect | Value |
|----|----|
| Specification version | pre-1.0, see [`CHANGELOG.md`](CHANGELOG.md) |
| Schema dialect | JSON Schema [draft 2020-12](https://json-schema.org/draft/2020-12/release-notes) |
| Stewardship | OpenMagnetics maintainers (incubation phase) |
| Roadmap | OpenMagnetics → proposed PSMA Magnetics Committee Working Group. See [`GOVERNANCE.md`](GOVERNANCE.md). |
| License | Apache-2.0 (see [`LICENSE.md`](LICENSE.md)) |
| Open work items | numbered RFCs under [`proposals/`](proposals/) |

## Scope

MAS describes magnetic components used in power-electronic converters:
transformers, inductors, chokes, current transformers and the operating
points and outputs associated with them. A MAS document has three
top-level parts:

| Part | What it describes |
|----|----|
| `inputs`  | Design requirements and operating conditions — what the magnetic must do. |
| `magnetic` | Physical construction — core, coil, materials, gaps, insulation, bobbin. |
| `outputs`  | Computed results — core and winding losses, inductance, temperature rise, stray capacitance, insulation coordination. |

In scope:

- Cores: ferrite, powder, amorphous, nanocrystalline; ungapped and gapped.
- Coils: single and multi-winding, round / rectangular / foil / planar / litz wires.
- Insulation: temperature classes, dielectric strength, creepage, reinforced and double insulation per IEC 62368-1 / IEC 61558.
- Twenty-five converter topologies, from buck and boost through LLC, CLLC, dual-active-bridge, push-pull and PFC.

Out of scope:

- PCB layout and routing (covered by IPC formats).
- Thermal-management hardware beyond the magnetic itself.
- Rotating machines (motor / generator construction).

## Normative references

MAS defers to existing international standards wherever possible.
[`docs/normative-references.md`](docs/normative-references.md) is the
master mapping. Highlights:

- **Core shapes:** IEC 62317 series, IEC 63093 series.
- **Effective parameters Aₑ, lₑ, Vₑ, C₁:** IEC 60205.
- **Core terminology and nomenclature:** IEC 60401-1 / -3.
- **Wire enamel grades:** IEC 60317 series; NEMA MW 1000 (US-market).
- **Conductor sizes:** IEC 60228 (metric), ASTM B258 (AWG).
- **Insulation thermal classes:** IEC 60085.
- **Comparative Tracking Index:** IEC 60112.
- **Insulation coordination (clearance, creepage):** IEC 60664-1.
- **Vocabulary:** IEC 60050-151 (electrical and magnetic devices), IEC 60050-221 (magnetic materials and components). Verbatim definitions reproduced in [`docs/normative-references.md`](docs/normative-references.md) §6b.
- **Test methods:** IEC 60205, IEC 61007, IEC 62044, IEEE Std 393.
- **Identifier registries:** ISO/IEC 11179-6 (IRDI), IEC 61360-4 / IEC CDD.

Where no standard exists — power-electronics ferrite grade nomenclature
(N87, 3C95, …), powder-core alloy families (MPP, High Flux, Kool Mµ),
litz wire construction — MAS encodes the data pragmatically. See
`docs/normative-references.md` "Standardisation gaps".

## Units and vocabulary

[`docs/units.md`](docs/units.md) is the normative units table. All
numeric fields carry SI units fixed by that document; values are bare
numbers, not `{value, unit}` objects. Highlights: frequency in Hz,
length in metres, temperature in degrees Celsius (per ISO 80000-5,
which permits °C alongside K and recommends °C for everyday
temperatures), magnetic flux density in tesla.

Vocabulary follows IEV 60050-151 and 60050-221. Each MAS field
description that introduces a domain term cites the relevant IEV
reference number.

## Reference implementation

The `MAS.hpp` header is a C++ reference binding generated from the
schemas via [quicktype](https://quicktype.io/) and consumed by the
[OpenMagnetics MKF](https://github.com/OpenMagnetics/MKF) library and
its Python bindings (PyMKF). Conforming implementations need not use
this binding — they need only consume MAS documents that validate
against `schemas/MAS.json`. Build instructions for the reference
implementation are in [`BUILD.md`](BUILD.md).

## Reading the schema

- [`docs/quickref.md`](docs/quickref.md) — at-a-glance index of every field.
- [`docs/schema.md`](docs/schema.md) — guided tour of the schema hierarchy.
- [`docs/inputs.md`](docs/inputs.md) — detailed walk-through of the inputs section.
- [`docs/magnetic.md`](docs/magnetic.md) — detailed walk-through of the magnetic section.
- [`docs/units.md`](docs/units.md) — normative units table.
- [`docs/glossary.md`](docs/glossary.md) — definitions of every term used in MAS, with IEC/IEV citations.
- [`docs/normative-references.md`](docs/normative-references.md) — mapping of every MAS area to the standards it defers to.

## Examples

Eight complete MAS documents under [`samples/complete/`](samples/complete/)
cover buck, boost, flyback, forward (single-switch / two-switch /
active-clamp), push-pull, isolated buck, isolated buck-boost and current
transformer designs. Each one validates against `schemas/MAS.json`.

A bundled component database under [`data/`](data/) contains 410+
ferrite and powder materials, 300+ standard core shapes, 4 350+ wires
and 300+ bobbins, all referenced by name from MAS documents.

## Governance and contributing

- [`GOVERNANCE.md`](GOVERNANCE.md) — stewardship roadmap, decision
  rules, IPR.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — DCO sign-off, PR checklist,
  schema conventions.
- [`MAINTAINERS.md`](MAINTAINERS.md) — current maintainers.
- [`SECURITY.md`](SECURITY.md) — how to report security or IPR concerns.
- [`proposals/`](proposals/) — RFCs for non-trivial changes.

The project follows Semantic Versioning. Pre-1.0 minor breaks are
permitted but flagged in [`CHANGELOG.md`](CHANGELOG.md); from 1.0
onward, breaking changes require a MAJOR bump and a documented
migration path.

## License

Apache-2.0. See [`LICENSE.md`](LICENSE.md). Each schema file carries an
SPDX header. The patent grant in §3 of the licence is intended to keep
the specification clear of IPR encumbrance for downstream users.

## History

MAS began at OpenMagnetics as a working data model for an
inductor-design tool. As coverage grew it became useful as a
standalone specification, independent of any one tool. Transfer to the
PSMA Magnetics Committee is the next step. The schema lives openly on
GitHub under Apache-2.0.
