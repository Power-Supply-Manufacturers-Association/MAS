# Changelog

All notable changes to the Magnetic Agnostic Structure (MAS) specification are
documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning rules for MAS:

- **MAJOR** — backwards-incompatible schema changes (removed/renamed fields,
  tightened constraints, semantic changes to existing fields).
- **MINOR** — backwards-compatible additions (new optional fields, new schemas,
  new enum values that consumers are required to ignore-on-unknown).
- **PATCH** — clarifications, documentation, examples, bug fixes that do not
  alter the validation surface.

A change to the bundled component database (`data/*.ndjson`) follows the same
rules: adding a material/shape/wire is MINOR, removing or renaming one is
MAJOR.

## [Unreleased]

### Breaking

- **Removed `masVersion` and `masConformance` top-level fields.** MAS documents
  are the polymorphic payload of the shared PEAS container, and the PEAS root
  object was closed (`additionalProperties: false`) to reject junk keys. Rather
  than carve MAS-specific metadata into the shared root, both fields were removed.
- **Retired the conformance-classes feature (RFC 0002).** With `masConformance`
  gone, the Class A/B/C bundles (`schemas/conformance/`), their validator
  (`scripts/validate-conformance.py`), the test vectors (`tests/conformance/`)
  and `docs/conformance.md` were removed. RFC 0002 is marked Withdrawn.
- **Removed `inputs.converterInformation`** (unused; the topology seed files
  under `inputs/topologies/` remain for future use).

Note: `scripts/migrate-to-1.0.py` still writes `masVersion` and is now obsolete.

## [1.0.0] - 2026-04-27

The breaking-changes release. Verified end-to-end against MKF
(`libMKF.so` and `MKF_tests` link clean against the regenerated
`MAS.hpp` with no source changes required in MKF beyond the
`mas_compat::parse` swap-in for old-document loading).

### Breaking

- **Enum casing sweep (RFC 0007).** Eight competing conventions
  collapsed to camelCase throughout, with explicit acronym
  (`AC`, `DC`, `SPS`, `EPS`, `DPS`, `TPS`, `SEPIC`) and IEC
  standard-code (`Y`/`A`/`E`/`B`/`F`/`H`/`N`/`R`/`200`/`220`/`250`,
  `MnZn`/`NiZn`/`FeSiAl`/etc.) exceptions.
- **IEC 60664 alignment (RFC 0008).** `pollutionDegree` `P1`/`P2`/`P3`
  → `PD1`/`PD2`/`PD3` plus a new `PD4`. `overvoltageCategory`
  `OVC-I`/`OVC-II`/`OVC-III`/`OVC-IV` → `I`/`II`/`III`/`IV`.
- **`magneticManufacturerInfo.cost`** unified with
  `distributorInfo.cost` to the structured `{value, currency}` form
  introduced in 0.2.0.

### Compatibility shim

- New `include/mas_compat.hpp` (header-only). Drop into any C++
  consumer alongside `MAS.hpp` and call `mas_compat::parse(s)`
  instead of `nlohmann::json::parse(s)` to keep loading pre-1.0
  documents transparently. Old enum spellings are rewritten in place
  before deserialization, so MKF / PyMKF / WebLibMKF / MVB++ continue
  to accept files written by 0.x tools.
- Migration tool `scripts/migrate-to-1.0.py` rewrites a MAS document
  (or directory tree) in place to the 1.0 spellings. Single source of
  truth for the mapping; mirrored in `mas_compat.hpp`.

### Schema work that landed and was kept

- **Loss-method `customCoreLossesMethodData` (open registry)** —
  drafted in step 2a, reverted at the end because it caused
  quicktype to rename `CoreLossesMethodData` and break the variant
  shape MKF depends on. Re-implementation needs either a
  quicktype-side workaround or coordinated MKF source updates;
  deferred to a post-1.0 RFC.
- **RFC 0006 topology operating-point dedup** — drafted in step 2,
  reverted in step 3 for the same reason: the allOf-with-
  baseOperatingPoint pattern made quicktype rename
  `OperatingPoint` to be the topology base type, with cascading
  consequences. Re-implementation needs a quicktype workaround;
  RFC stays Draft.

### Schema work landed (additive, kept)

- `impedanceAtFrequency` consolidated into `utils.json` (RFC 0006
  partial), used by `designRequirements.minimumImpedance`, common-
  mode choke and differential-mode choke. The bare-magnitude form
  was reverted to a pure `impedancePoint` reference to keep
  MKF source compatible.
- New optional `numberStrands` and `twistPitch` on `wire/litz.json`
  (closes the litz-construction gap noted in
  `docs/normative-references.md`).
- `tests/conformance/class-{A,B,C}/` populated with 8 vectors
  carrying `masConformance` declarations.
- Three CI scripts: `scripts/validate-samples.py`,
  `scripts/check-mas-hpp.sh`, `scripts/validate-conformance.py`.
- Bundled `data/*.ndjson` migrated to the new enum spellings.
- Tracked `MAS.hpp` regenerated and is now in sync with the schema.

### Out of scope

- RFC 0001 v2 prose sweep (per-field `description` rewriting to
  point at `docs/units.md`) deferred — cosmetic only, ship later.
- Loss-method open registry RFC and topology operating-point dedup
  RFC remain Draft; both blocked on quicktype-naming work.

## [0.2.0] - 2026-04-26

Standards-alignment release. Five RFCs implemented; license, governance
and normative references in place; project documentation reframed
around an open specification with a reference implementation.

All changes in 0.2.0 are **non-breaking**: every document that validated
against 0.1.0 continues to validate against 0.2.0. MKF rebuilds clean
against the new schema (verified end-to-end on this branch — 164/164
build steps, zero source changes required in MKF).

### Project / governance

- Apache-2.0 license (replaces BSD-4-Clause).
- New top-level docs: `CHANGELOG.md`, `GOVERNANCE.md`, `CONTRIBUTING.md`,
  `MAINTAINERS.md`, `SECURITY.md`.
- `README.md` rewritten with a status table, scope, normative
  references, governance trail and history.
- Stewardship roadmap documented: OpenMagnetics → proposed PSMA
  Magnetics Committee Working Group.

### Specification framing

- New `docs/units.md` — normative SI units table (RFC 0001 v2). Bare
  numbers in JSON; one canonical unit per field, fixed by the spec.
- New `docs/normative-references.md` — comprehensive mapping of MAS
  fields to existing standards (IEC 62317, 63093, 60401, 60205, 60317,
  60228, 60085, 60112, 60664, 62368-1, 61558, 60050-151/-221, 60404,
  61007, 62044; ASTM A772/A773/A977/A1086/A753/A901; MPIF Standard 35;
  JIS C 2560/2565/2552/2550-1; NEMA MW 1000; SAE AMS 7717/7718/7701;
  MIL-PRF-27G; UL 1446; IEEE Std 393). Verbatim IEV definitions for
  turn (151-13-14), coil (151-13-15), winding (151-13-17), bifilar
  winding (151-13-18), air gap (221-04-13), magnetic core (221-04-24),
  laminated/powder/strip-wound core (221-04-25/26/27), yoke (221-04-32).
- New `docs/conformance.md` — defines Class A / B / C with their
  respective required fields and intended use cases.
- All schema descriptions reworded for IEV vocabulary alignment;
  citations to IEC 60401-3 (initial permeability convention),
  IEC 60085 (insulation thermal classes), IEV 103-02 (values of a
  periodic quantity).

### Added (schema)

- `masVersion` (optional, root) — SemVer string; will become required
  at 1.0.
- `masConformance` (optional, root) — `"A"` / `"B"` / `"C"`; declares
  which conformance class this document targets.
- New `schemas/conformance/{class-A,class-B,class-C}.json` bundles
  that `allOf`-extend `MAS.json` with class-specific tightening.
- New shared `cost` type `{value: number, currency: ISO 4217 code}`.
  `manufacturerInfo.cost` and `distributorInfo.cost` reference it.
- New shared `irdi` type (RFC 0003) with ISO/IEC 11179-6 pattern.
  Optional `irdi` field on `manufacturerInfo`, available on every
  catalogue record (cores, materials, wires, bobbins, insulation).
- `outputVoltagesType` and `outputCurrentsType` on `baseOperatingPoint`
  — optional discriminator over `dc / rms / peak / peakToPeak / average`,
  default `dc`.
- New permeability slots (RFC 0005): `incremental` (μΔ) and
  `reversible` (μᵣₑᵥ) on `core/material.json` `permeability`. Required
  for inductors operating under DC bias.
- `surfaceResistivity` on `insulation/material.json` (Ω/sq per IEC 60093),
  alongside the existing volume resistivity.
- `measurementCondition` block on `outputs.magnetizingInductance` —
  optional `{frequency, voltageRms, currentRms, dcBiasCurrent, temperature}`
  pinning the operating point at which the inductance applies.
- `cylindrical` value on `coordinateSystem` (RFC 0009) — natural for
  toroidal cores; `(r, theta, z)`.
- IEC 60085 letter-class form on `insulation/material.json`
  `temperatureClass` — `oneOf [letter enum, °C number]`.
- New RFC stream under `proposals/` documenting design proposals 0001
  through 0009. Five Implemented, two Draft (1.0 batch), one
  Withdrawn, one Superseded.

### Changed (schema)

- `$id` swept from `http://openmagnetics.com/schemas/...` to
  `https://psma.com/mas/...` across all 44 schema files.
  Cross-`$ref` links unaffected (all relative).
- SPDX header `"$comment": "SPDX-License-Identifier: Apache-2.0"` added
  to every schema file.
- 10 inlined topology operating-point definitions (RFC 0006) refactored
  to `allOf [baseOperatingPoint, extras]`. Net diff: 85 insertions,
  580 deletions. Field shape unchanged for valid documents.
- `magnetic.json` `manufacturerInfo` re-defined as `allOf`-extension
  of the shared `utils.json` `manufacturerInfo` (eliminates the second,
  contradictory `cost: string` definition).
- `gap.coordinates` now `$ref`s the shared `coordinates` def instead
  of redefining it inline.
- Loss-method descriptions on `core/material.json` pinned to W/m³, Hz,
  T (peak); Steinmetz `k` units made explicit.
- Thermal resistance corrected from `W/K` to `K/W` in
  `operatingConditions.json` (heatsink, coldPlate). Same correction
  in `magnetic.json` `magneticDatasheetThermal` and
  `outputs.json` `bulkThermalResistance`.
- Saturation flux density description tightened to the IEC convention
  (10 % drop in differential permeability).
- Bobbin and coil prose rewritten to align with IEV 60050-151
  vocabulary (winding, turn, coil).
- `additionalProperties: false` added to leaf schemas (`resistivityPoint`,
  `bhCyclePoint`, `complexFieldPoint`, `fieldPoint`, `manufacturerInfo`,
  `distributorInfo`, `marginInfo`, `connection`, `partialWinding`, `cost`).
  Wave 2 (root containers) deferred pending a fixture audit.
- Various unit format fixes: `J/(kg*K)` instead of `J/Kg/K`,
  `W/(m*K)` instead of `W/m/K` (per ISO 80000); units added to
  previously bare-number outputs (`creepageDistance`, `clearance`,
  `withstandVoltage`, `withstandVoltageDuration`, core-loss outputs).
- Bobbin enum: removed duplicate `"er"` entry. Pure cleanup.

### Fixed

- Numerous prose typos: `losses → loses`, `thicknes → thickness` (×4),
  `whre → where`, `descriptionof → description of`,
  `impendance → impedance`, `dieletric → dielectric` (×5, including
  the `dieletricStrengthPoint` field rename), `tetha → theta`,
  `gamma → phi/z` (in coordinate-system prose), `Magnetic method →
  Magnetec method`. Removed unverifiable "IEEE 750181" citation.
- `EN 62317` references updated to the canonical `IEC 62317` (and
  forward-reference to `IEC 63093` for planar).
- `eddyCurrentCoreLosses` and `hysteresisCoreLosses` constraint
  relaxed from `>0` to `≥0` (low-conductivity ferrites can have eddy
  losses approaching zero).

### Deprecated

- BSD-4-Clause license. Removed in this release; downstream
  redistributors relying on the advertising clause should switch to
  Apache-2.0 attribution.

### Out of scope (deferred to 1.0)

- Per-field `description`-text sweep referencing `docs/units.md`
  (RFC 0001 v2 prose pass).
- Enum casing convention sweep (RFC 0007).
- `pollutionDegree` / `overvoltageCategory` rename to IEC 60664
  spelling (RFC 0008).
- Loss-method open registry (extension to current closed `anyOf`).
- Per-class test-vector partition under `tests/conformance/`.

## [0.1.0] - prior to this changelog

Initial public schema, C++ binding generation via quicktype, component
databases for cores, materials, wires and bobbins. See git history for
per-commit detail.
