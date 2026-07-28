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
- **`TMFD` (μi=14) replaced by `TMFD 60` / `TMFD 90` (data, ABT #185).** TDG's
  own material workbook shows TMFD is an Fe-Si powder series in 60μ/90μ only —
  the two "duplicate" DC-bias fits were the per-grade coefficients (60μ:
  b=7.8e-7/c=1.70; 90μ: b=2.95e-7/c=2.23), and the μi=14 single record was a
  botched merge of them. No cores referenced `TMFD`. The per-grade fits
  reproduce TDG's published 82% μe@100 Oe (60μ) and the series loss
  coefficients reproduce the published 450 kW/m³ @ 50 kHz/100 mT.
- **Generic `Metglas` / `Finemet` records renamed to their actual alloy grades
  (data, ABT #221).** Each was a single record flattening a whole alloy family.
  Migration map for consumers that referenced a material by these bare names:
  `Metglas` → `Metglas 2605SA1` (Fe-based amorphous, the workhorse; Tc 395 °C
  matches 2605SA1), `Finemet` → `FT-3M` (FeCuNbSiB nanocrystalline; Bs 1.23 T /
  Tc 570 °C match FT-3M). The fitted μ(T) and loss curves are unchanged, only
  re-attributed. No cores or examples in MAS referenced the old bare names.
  Additional grades (Metglas 2605S3A/2605HB1M/2714A, Finemet FT-3K50T, …) are
  added separately (MINOR).

Note: `scripts/migrate-to-1.0.py` still writes `masVersion` and is now obsolete.

### Added

- **`cableCore` datasheet electrical subtype (new `oneOf` branch on `magnetic.manufacturerInfo.datasheetInfo.electrical[]`)** —
  clamp-on / cable ferrite cores (clip-on ferrites, cable rings, split/snap-on
  suppressors): a 1-port common-mode suppression core the cable is threaded
  through. Electrically a 1-port impedance like `chipBead`, but a distinct part
  class — retrofit/threaded onto a cable rather than reflow-soldered — so a
  consumer can query and prefer real cable cores for cable-level CM mitigation
  instead of overloading `chipBead`. Carries `impedancePoints` (with the
  existing per-point `current` for the DC-bias-derating curve), `numberTurns`,
  `dcResistance`, `ratedCurrents`/`ratedCurrentPoints`, `impedanceTolerance`,
  `selfResonantFrequency`, `mountingForm` (solidRing / snapOn / split /
  screwable — retrofit clamp vs build-time ring) and `maximumCableOuterDiameter`
  (the inner-diameter cable-fit limit, a primary cable-core selection param).
  Multi-turn curves reuse the existing
  one-electrical-entry-per-configuration idiom (a datasheet's 1/2/3-turn |Z|
  tables become one entry each, discriminated by `numberTurns`), and the
  toroid/ring geometry (inner/outer diameter, height) and ferrite material stay
  in the shared core description — no geometry or material fields are duplicated
  into the electrical block. Purely additive: every existing part still matches
  exactly one `oneOf` branch (verified against a per-subtype sample of the
  bundled catalog), and unknown-subtype-ignoring consumers are unaffected.
  Motivation: Hertz's radiated cable-mitigation picker currently selects from
  `chipBead` SMD beads for want of a cable-core class; this gives clamp-on cores
  a first-class home once the parts are ingested.
- **`saturationCurrentPeak` on the `commonModeChoke` electrical variant (ABT #279)** —
  peak core-saturating bias current in Amperes for current-compensated CMCs, mirroring
  the inductor variant's field. Motivation: 427 catalogued CMCs (WE-CMB/WE-LF/WE-CMBNC
  among others) carry a datasheet I_sat that previously had no schema slot, blocking
  their retag from the mistagged `inductor` variant.
- **Magnetics (Mag Inc.) power ferrites (data, ABT #213): L, R, P, F, T** — first
  Magnetics ferrite materials in the DB (their powder cores were already covered).
  Constants from the 2021 ferrite catalog (μi, Bs@1194 A/m 25 °C, Br, Tc, ρ,
  density, cross-checked against the parts database); loss model = Magnetics'
  official per-range equations `P[W/m³] = a·f^x·B^y·(b−cT+dT²)` mapped verbatim
  onto Steinmetz ranges (R/F/T reproduce the catalog's typical-loss table to ±3%);
  the catalog typical points are stored in `advanced_core_materials`. Known
  caveats: P's official equation overpredicts ~3× at 100 kHz vs the (internally
  inconsistent) typical table — kept official, discrepancy tracked in ABT #213;
  saturation has only the 25 °C point (Magnetics publishes no tabular 100 °C Bs);
  J/W/M/C/E/V (high-perm/filter grades) still pending loss-factor data.
- **6 more TDG MnZn ferrites (data): TPF26, TPW23, TP5H, TP5-B, TP5R, TP6** —
  measured μi–T curves and Pcv points from TDG's material-performance workbook
  with house-pipeline Steinmetz fits (13–31% mean error; TP6 split into
  [1,3 MHz]+[3 MHz,1 GHz] ranges). These grades have **no public datasheet**;
  Bs/Tc/resistivity/density are anchored on the closest documented family grade
  (TPF26←TP4A, TPW23←TPW30, TP5H/TP6←TP5E, TP5-B/TP5R←TP5) and must be replaced
  when TDG characteristic sheets arrive (ABT #196).
- **5 TDG MnZn ferrites (data): TP4, TPW33, TPG33B, TPB16, TPB22** — built from
  TDG's measured material-performance workbook (μi–T curves as the initial
  permeability, manufacturer Pcv points) plus per-material datasheet constants
  (Bs/Br/Hc/Tc/ρ/density; TPG33B constants from the 2025-11 automotive brochure,
  ρ/density carried from the TPG33 base grade). TPW33/TPG33B get house-pipeline
  Steinmetz fits (6.2% / 3.4% mean error, points in `advanced_core_materials`);
  TP4/TPB16/TPB22 carry their measured Pcv points inline (single (f,B) sweeps —
  a Steinmetz fit is not identifiable from them).
- **TP4A initial permeability upgraded** from the single spec point (2400 @ 25 °C)
  to the measured 24-point μi–T curve; TP4A/TP5 gained their measured Pcv–T
  sweeps in `advanced_core_materials`.
- **`frequencyFactor` on `pocoPermeabilityMethodData`** (optional `{a, b, c, d}`):
  percent-of-initial logistic rolloff `(a / (1 + (f/b)^c) + d) * 0.01`, matching
  the implementation MKF ships since ABT #169. Legalizes the 48 POCO V2026
  records that already carried the fitted factors.

### Fixed

- **Non-physical Steinmetz ranges refitted (data, ABT #183):** 12 ranges that
  validated but were physically garbage (β≈0: DMR28/DMR50B/DMR52/DMR51W/DN15P/JNP95;
  α≈0: ACME P47/P5; overfits: SMP53/DMR51/PC200) refitted with the house pipeline
  on manufacturer points from `advanced_core_materials`, normalized to `ct(25°C)=1`
  and gated (α∈[0.5,3.5], β≥1). Two unsupportable extrapolation ranges (DMR51W
  `[1,500k]`, P47 `[1M,1G]`) were deleted — MKF falls back to the neighbouring
  healthy range. DMR51's refit (α=3.59) exceeds the α-gate by 0.09 as a documented
  exception: the steepness is catalog-consistent (136 kW/m³ @ 3 MHz/10 mT/100 °C vs
  DMEGC's ≤150 spec). P5 is now temperature-flat (its only temperature-varying
  points were bogus, see below).
- **JNP95 (data):** the B=150 mT and B=300 mT loss series in
  `advanced_core_materials` were 1000× too small (kW/m³ digitized as W/m³).
- **P5 (data):** removed the 18 f=700 Hz loss points — three conflicting values per
  (f,B,T) and ~10⁵ W/m³ at 700 Hz/200 mT is impossible (frequency labels were lost
  in digitization).
- **`validate-db.py`:** merge-validates `massLosses` like `volumetricLosses` and
  flags losses blocks without a non-empty `default` method list (mirrors the MKF
  loader contract, ABT #184).
- **Metglas, AF, AN (data):** manufacturer loss curves were W/kg values stored as
  `volumetricLosses` (W/m³) — moved to `massLosses` (Nanoperm precedent), and the
  Steinmetz fits made on those W/kg points rescaled `k × density` into true W/m³.
- **Duplicate records (data):** 58 duplicated advanced lines removed (Kool Mµ /
  XFlux / High Flux / Edge / FS / MS / HF families; kept the last of each name,
  which is what MKF's last-wins merge already used); duplicate `XFlux 125`
  (2023 fit superseded by the 2025-08 refit) and `TMFD` base lines removed.
- **Nanoperm ×7 (data):** empty `volumetricLosses: {}` shells removed (undefined
  behavior in MKF's C++ advanced-materials merge).
- **M34 (data):** `datasheetUrl` pointed at M33's download path with the filename
  swapped; now the real TDK M34 datasheet URL.

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
