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

The next release is a MINOR one: everything below is additive (new optional
fields and new records), with one requirement relaxed. No existing document
becomes invalid.

### Added

- **Lead-to-pin assignment (MAS-RFC 0013, ABT #1178).** Two optional fields on
  `coil.json#/$defs/connection` — `end` (`start` | `finish` | `tap`, which end of the
  winding terminates on this terminal; `start` is the dot end, a series junction is a
  `tap` on both sections) and `parallel` (integer >= 0, which parallel strand
  terminates here; absent means all of them together) — and one on
  `bobbin.json#/$defs/pin`: `removable` (boolean, default false), for the corner pins
  bobbin makers offer cut off to open up creepage. The RFC also fixes the default pin
  numbering used when a bobbin brings no pin names of its own: counter-clockwise from
  row 0, seen from the mounting side (owner decision 2026-09-12). Documented in
  `docs/magnetic/coil.md`, including the industry assignment rule (rows are isolation
  groups, start and finish adjacent, taps shared).

- **Multi-chamber bobbins and toroid bases (MAS-RFC 0014, ABT #1179).** Four optional
  fields on `bobbin.json`. `processedDescription.dividers[]` describes the interior
  walls of a split former — `thickness` along the column axis and `coordinates` are
  required, `height` (radial reach; absent = as far as the flanges) and `crossingSlot`
  (`width`, `depth`, `angle`) are optional — and `functionalDescription.numberChambers`
  (integer >= 1) is the count a catalogue row can state before anybody has transcribed
  the wall drawing. `functionalDescription.base` describes the moulded base a wound
  toroid is mounted on, which is a bobbin of family `t` (decision D1 of the 2026-09-12
  survey, so it reuses `pinout` / `pins[]` / `connections[]` rather than inventing a
  second pin vocabulary): `mounting` (`horizontal` | `vertical`), `length`, `width`,
  `height` and `standoff` required, `pocketInnerDiameter`, `pocketDepth`, `boatWidth`
  and the selection limits `maximumCoreOuterDiameter` / `maximumCoreHeight` optional.
  The bobbin's existing `orientation` is unchanged and keeps its former meaning.
  Documented in `docs/magnetic/coil.md`.

- **Lead sleeving (MAS-RFC 0016, ABT #1181).** `coil.json#/$defs/connection` gains
  `sleeve` — `material` (an insulation-material record or the name of one),
  `wallThickness` and `innerDiameter` required, `overlapIntoWinding` and
  `numberLayers` (default 1) optional — so the sleeve a winding shop slides over a
  lead is data rather than shop practice. `magnetic/insulation/material.json` gains
  `form` (`tape` | `film` | `sleeve` | `varnish`), which is what lets a coordinator
  pick sleeve stock instead of tape, and `cti`, the measured comparative tracking
  index per IEC 60112 in volts (the material *group* of the same name in insulation
  coordination follows from it per IEC 60664-1; neither is renamed).
  The RFC's `leadCreepage[]` output field was landed and then **withdrawn the same day**
  (Alf, 2026-09-13): the local `outputs.json#/$defs/insulationCoordination` it was added to is
  referenced by nothing (the `insulationCoordination` property points at the PEAS mirror), so the
  field was unreachable; per-lead creepage is reported by MKF's insulation-coordination result
  instead, with no schema field.

- **Two sleeve-stock records in `data/insulation_materials.ndjson`** (ABT #1174), the
  first with `form: sleeve`, so an insulation coordinator can pick the tube a lead is
  sleeved with instead of hard-coding a name:

  | record | maker, family | walls recorded (m) | dielectric strength | temperature |
  | --- | --- | --- | --- | --- |
  | `PTFE extruded tubing` | Zeus, AWG tubing | the 9 nominal walls of the Standard/Thin/Lightweight classes, 1.3e-4 to 5.1e-4 | 457 V/mil (ASTM D149, lower bound of 457-483) | 260 C |
  | `Polyolefin heat-shrink tubing` | Alpha Wire, FIT-221 (2:1) | the 10 nominal recovered walls, 4.1e-4 to 1.40e-3 | 500 V/mil | 135 C |

  Both datasheets publish dielectric strength per mil with no specimen thickness, so the
  one published value is recorded at each published wall; that pairing is stated in each
  record's description. The walls are a list of what the maker sells, not of what fits a
  given lead: which wall exists depends on the tube size (Zeus's 0.41 mm standard wall is
  only offered from AWG 20 to 10), and nothing in the record ties a wall to a size.

  Silicone-rubber-coated glass-fibre sleeving (UL 1441) was **not** added. Varflex,
  Techflex and Omerin publish a grade breakdown voltage for the whole sleeve (e.g. Grade A
  8 kV) but no dielectric strength per thickness, and Varflex and Techflex no wall either;
  `dielectricStrength` is required, and dividing a grade voltage by a wall would be our
  number, not theirs.

- **Magnetic shunts (MAS-RFC 0015, ABT #1180).** `magnetic.json` gains `shunts[]`, the
  pieces of permeable material — a ferrite plate, a ferrite-polymer or flexible-ferrite
  sheet — put deliberately where the leakage flux runs, which is how an
  integrated-leakage transformer gets the leakage inductance it is designed for.
  `placement` (`inWindow` | `betweenSections` | `onColumn` | `outsideWindow`),
  `coordinates`, `dimensions` and `material` (a core-material record or the name of one)
  are required; `name`, `gapToColumns` (`inner` / `outer`) and `segments[]`
  (`length` / `gap`, for a shunt built from several pieces in series) are optional. A
  shunt belongs to neither the core nor the coil — it is added at assembly — and
  deliberately not to `core.geometricalDescription`, which is regenerated on autocomplete.
  Documented in `docs/magnetic.md`.

  **No new core-material records ship with it, and that is a finding, not an omission.**
  The four sheet grades surveyed on 2026-09-12: TDK FPC film `C350` / `C351` are already
  in `data/core_materials.ndjson` (µi 9 at 1 MHz, Bs 255 mT at H = 25 kA/m, both from the
  FPC datasheet). TDK Flexield IFL04, Fair-Rite's flexible sheets M1…M6 and 3M EM15TF
  cannot be filed: `core/material.json` requires `saturation` (Fair-Rite publishes no
  material data sheet for the M grades at all, and 3M publishes no saturation figure) and
  requires `permeability.initial`, while all three publish only µ′ at an RF measurement
  frequency, which is a different quantity. Filing them would mean inventing a saturation
  figure or a measurement condition. Relaxing either requirement is a separate,
  owner-approved change.

### Changed

- **`resistivity` is no longer required on a core material.** It stays a defined,
  documented property and every existing record keeps it; it is simply no longer
  in the `required` list of `schemas/magnetic/core/material.json`.

  Rationale (ABT #1039). Two facts made the requirement untenable. First, the
  field is inert for the loss model most EMI-suppression ferrites use: in MKF,
  core-material resistivity is read only by `CoreLossesRoshenModel`'s
  eddy-current term and by `CoreMaterialCrossReferencer`'s similarity scoring,
  never by the `lossFactor` path. Second, it cannot be estimated when a maker
  does not publish it. Across NiZn grades at one permeability (mu_i 800-850) the
  filed and published values span **five decades** — Ferroxcube 4A11 1e2 ohm-m,
  Ferronics J 1e3, Meiwa J / ACME F80 / ACME M80 1e6, Fair-Rite 43 / Shinn Der
  N4S / Encore N1 1e7 — because resistivity is set by Fe(II) content and
  sintering, not by permeability. Requiring it therefore forced a fabricated
  value, of the one property the material's own loss model would not read.

  This unblocks real, shipping grades whose makers publish permeability,
  saturation and a loss curve but no resistivity.

  **Consumers of the generated bindings must regenerate and adapt.** The
  quicktype type changes from `std::vector<ResistivityPoint>` to
  `std::optional<std::vector<ResistivityPoint>>`, so call sites break at compile
  time rather than silently. In MKF there are THREE, found by compiling rather
  than by grepping — an early grep of mine was truncated and reported two:

  - `ResistivityCoreMaterialModel::get_resistivity` — throw `MISSING_DATA` on a
    disengaged optional, as it already does on empty data. No fallback.
  - `CoreMaterialCrossReferencer::MagneticCoreFilterResistivity` — mirror the
    Curie-temperature filter: no reference value skips the dimension, a candidate
    without one is culled from that filter. Nothing substituted.
  - `StrayCapacitance::core_image_factor` — the conduction-only branch is an
    `else if`, so a material without resistivity falls through to the no-data case
    already documented below it. Guard the optional, nothing else to decide.

  Verified end to end on a clean `origin/main` worktree with this schema and those
  three patches: MKF builds with 0 errors, and the catalogue plus one
  resistivity-less material parses as 1079 records, 1078 with resistivity and 1
  without. The same catalogue on the unpatched engine is rejected outright.

  Until a consumer regenerates, it will REJECT a record that omits the field —
  `nlohmann::json` raises `[json.exception.out_of_range.403] key 'resistivity'
  not found` and, in MKF's case, the whole `load_core_materials` call fails, not
  just that record. Land the regeneration before writing any record that omits it.

### Added

- **Seven bobbin plastics in `data/insulation_materials.ndjson`** (ABT #1164), so a
  bobbin's `functionalDescription.material` resolves to a record carrying a
  `relativePermittivity`. Every `material` value used by `data/bobbins.ndjson` now
  names a record: `PA66`, `PBT`, `PPS`, `A3X2G10`, `x2g5`, `Zen.6130L` and
  `SKYT.5220FR` (`PET` was already present). All eight are NORWE coil-former
  materials; the vendor short codes are resolved to their grade and base polymer
  through NORWE's published material list, and each permittivity is taken from that
  grade's own datasheet:

  | record | grade | polymer | eps_r (1 MHz) |
  | --- | --- | --- | --- |
  | `PA66` | Envalior Durethan AKV30H2.0 | PA66-GF30 | 4.0 |
  | `PBT` | Envalior Pocan B4225 | PBT-GF20 FR(17) | 3.6 |
  | `PPS` | Toray Torelina A504X90 | PPS-GF40 | 4.2 |
  | `A3X2G10` | BASF Ultramid A3X2G10 | PA66-GF50 FR(52) | 3.6 (dry) |
  | `x2g5` | BASF Ultramid A3X2G5 | PA66-GF25 FR(52) | 3.7 (dry) |
  | `Zen.6130L` | Celanese Zenite 6130L | LCP-GF30 | 4.0 |
  | `SKYT.5220FR` | SK Chemicals Skytra 5220FR | PET-GF30 FR | 4.7 |

  These are the GLASS-FILLED values, which is what a bobbin is moulded from; the
  neat polymer is materially lower. The two BASF polyamides publish a dry and a
  conditioned figure (3.6/5 and 3.7/5) and the dry, as-moulded figure is recorded —
  PA66 is hygroscopic and its permittivity drifts with humidity, so the recorded
  value is the lower bound of its range.

  `SKYT.5220FR` is the one record whose permittivity is not from its own maker's
  datasheet: SK Chemicals publishes no dielectric data for the grade. Its value is
  that of Rynite FR530L NC010, the PET-GF30 FR grade NORWE replaced with it
  (NORWE material-change note 09/2022) and which SK Chemicals states the grade
  corresponds to in mechanical and electrical properties. The substitution is
  recorded in the record's `manufacturerInfo.description`.

  Consumers that counted the bobbin wall as air in a winding-to-core dielectric
  stack can now read `t / eps_r` for it instead.

- **Seven bobbin plastics get a relative permittivity**, so a bobbin wall can enter a
  dielectric stack as `t/eps_r` instead of being counted as air (requested by MKF, ABT #1164):
  `PA66`, `PBT`, `PPS`, `A3X2G10`, `x2g5`, `Zen.6130L` and `SKYT.5220FR`. Every
  `functionalDescription.material` in `data/bobbins.ndjson` now resolves under an exact-name
  lookup; previously only `PET` did. Values are the glass-filled grades' own, from the
  manufacturers' datasheets, with the NORWE material number, grade reference and datasheet URL
  recorded on each.

  Two sourcing decisions are called out because they are judgement, not datasheet:
  - The two BASF polyamides (`A3X2G10`, `x2g5`) carry their **conditioned** permittivity of 5.0
    at 23 C / 50% r.h., not their dry as-moulded 3.6 and 3.7. PA66 is hygroscopic and a bobbin in
    service equilibrates toward the conditioned figure; the dry value would under-state
    winding-to-core capacitance and so over-state the predicted self-resonant frequency. The dry
    figure is recorded in each record's description.
  - `SKYT.5220FR` (SK Chemicals Skytra 5220FR, 131 bobbins) carries **4.7, which is Rynite
    FR530L NC010's value, not its own** — SK Chemicals publishes no dielectric data for the
    grade. It is carried across on NORWE's material-change note 09/2022, which records 5220FR
    replacing Rynite FR530L in the same bobbins, and on SK Chemicals' statement that the grade
    corresponds to that DuPont PET-GF30 FR grade in mechanical and electrical properties. The
    substitution and both sources are written into the record's description.

  `PA66` was also removed from `Nylon 6.6`'s aliases: it now names a record of its own, and the
  wire-serving polyamide at 3.4 is a different material from the glass-filled bobbin resin.

- **Optional `coreElectricalReference` on `magnetic`.** Records how the core is
  referenced electrically in the assembled component: `floating` (not bonded),
  `grounded` (bonded to a circuit reference, with an optional `isolationSide`
  naming whose local ground; absent = protective earth / chassis), or
  `tiedToWinding` (bonded to the `start` or `end` `terminal` of a named
  `winding`). A ferrite or powder core has no terminal of its own and follows
  the conductors around it unless a mounting clip, copper strap / flux band or
  conductive tape bonds it. The choice sets how the winding-to-core
  capacitances appear at the terminals (C0/12 floating vs C0/3 tied to a
  winding end, for a linear potential ramp) and whether the
  primary→core→secondary common-mode path closes through the core or is
  diverted. **Absent means floating**, which is what every model assumed before
  the field existed, so no existing document or result moves. Non-breaking.
  Requested by MKF (ABT #1167) after the stray-capacitance review of
  2026-09-12; `examples/02_flyback_efd25_3c95.json` shows it in use.
- **Optional `permittivity` on core materials.** Adds a `permittivity` object to
  the core material schema with a `complex` part (ε′ + j·ε″, same sign
  convention as complex permeability — the imaginary part is a positive loss
  magnitude), mirroring the `complex` entry under `permeability`: a `real` and
  an `imaginary` sub-object, each a new `permittivityPoint` (value, plus
  optional temperature and frequency). Enables modelling of dimensional
  effects (dimensional resonance) and displacement current in high-permittivity
  ferrites, and the effective usable bandwidth of a given core size. Non-breaking:
  the field is optional and existing materials are unaffected.
- **Complex permittivity data for 7 MnZn power ferrites** — ML91S, ML95S, ML27D
  (JFE), DMR51W, DMR96A (DMEGC), P63 (ACME) and 3F36 (Ferroxcube). ε'(f) and
  ε''(f) over 0.1–10 MHz, digitized from Fig. 23 of A. Nabih, F. Jin,
  R. Gadelrab and F. C. Lee, "Characterization and Mitigation of Dimensional
  Effects on Core Loss in High-Power High-Frequency Converters," IEEE Trans.
  Power Electron., 2023, doi: 10.1109/TPEL.2023.3285633
  (https://ieeexplore.ieee.org/document/10149511). Values are read-offs from
  log–log figures — expect ~5–10 % uncertainty.

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

- **Nine core-shape aliases dropped by a25fec9 are restored.** Rewriting `PQ 27/15`,
  `PQ 27/17`, `EQ 25` and `EP 14.5` to add their missing dimensions replaced the
  whole record and lost `PQ 27.3/15A`, `PQ 27.3/14.5A`, `PQ27.3/18`, `PQ27A/17.4`,
  `PQ27B/17.4`, `EQ 25/16`, `EQ 25/8/18`, `EP 14.4` and `EP 14.4/14.5`. Nine
  Micrometals cores in `cores.ndjson` name `PQ 27.3/14.5A`, so every consumer
  loading the catalogue failed with CORE_SHAPE_NOT_FOUND (ten MKF tests). The
  schema could not see it: a core's `shape` is a free string. `scripts/validate-db.py`
  now also checks that every core in `cores.ndjson` / `cores_stock.ndjson` resolves
  its shape (name or alias) and material, and fails the run otherwise — verified to
  fail on the pre-fix data and pass after it. `data/MANIFEST.sha256` regenerated; it
  had also been recording the LFS pointer's hash for `advanced_core_materials.ndjson`
  and a `core_materials.ndjson` hash three commits old.
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
