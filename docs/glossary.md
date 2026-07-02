# MAS Glossary

> **Informative.** This glossary defines the terms used across the MAS
> JSON Schema and its accompanying documents. It is a reading aid; the
> normative definitions are the schema `description` fields and the
> standards mapping in [`normative-references.md`](normative-references.md).
> Where a term has a citation in the IEC International
> Electrotechnical Vocabulary (IEV) or another standard, the reference
> follows the definition in parentheses.

Field names are written in `camelCase` to match the schema; concept
names that are not literal property keys are written in plain prose.

---

## Components and Geometry

| Term | Definition |
|------|------------|
| `core` | Magnetic core providing the magnetic circuit path (IEV 221-04-24). |
| `coil` | Wound assembly of one or more windings on a former. MAS uses the term in the broad industry sense; the strict IEV sense is in IEV 151-13-15. |
| `winding` | Assembly of interconnected turns intended for common operation (IEV 151-13-17). |
| `turn` | One closed loop of conductor (IEV 151-13-14). |
| `bobbin` | Insulating former on which one or more windings are arranged. Industry term; not yet in IEV (PSMA queue). |
| `layer` | Group of physical turns wound side-by-side in one radial position. |
| `section` | Group of layers belonging to the same winding or grouped for interleaving. |
| `group` | Collection of sections, typically used for distinct winding windows or PCB sub-assemblies. |
| `partialWinding` | Subset of a winding by proportion of turns or proportion of parallels. |
| `parallel` | Conductor connected in parallel with others to carry a fraction of one electrical turn's current. |
| `windingWindow` | Space available for placing turns of windings within the core. |
| `column` | Vertical or axial section of the core with a defined cross-section. |
| `pin` | Connection point on the bobbin where a winding terminates. |
| `coordinates` | Positional values (cartesian, polar, or cylindrical) used to place geometry features. |

## Core Construction Families

| Term | Definition |
|------|------------|
| `twoPieceSet` | Core assembled from two mating pieces (E, ETD, PQ, RM, etc.). |
| `pieceAndPlate` | Core assembled from one shaped piece and a flat plate. |
| `toroidal` | Single closed-ring core (IEV 221-04-24, ring core). |
| `closedShape` | Single-piece closed-magnetic-path core that is not toroidal (e.g. pot core). |
| `shape` | Geometric form of the core (E, ETD, ER, EFD, PQ, RM, T, EP, …). |
| `numberStacks` | Number of identical cores stacked along the axis perpendicular to the lamination plane. |
| `coating` | Surface treatment of the core (e.g. epoxy, parylene). |

## Air Gap

| Term | Definition |
|------|------------|
| `gapping` | List of air gaps introduced into the magnetic circuit (IEV 221-04-13). |
| `gap` / `airGap` | Intentional or residual break in the magnetic core path. |
| `subtractive` gap | Material removed from the core (e.g. centre-leg ground gap). |
| `additive` gap | Spacer inserted between mating surfaces, increasing the assembled core height. |
| `residual` gap | Unavoidable gap at mating surfaces of an ungapped two-piece set. |
| `distributed` gap | Air distributed throughout the magnetic path (e.g. powder cores). |

## Magnetic Quantities

| Term | Definition |
|------|------------|
| `magneticFluxDensity` | Magnetic flux density B, in tesla (T). |
| `magneticFieldStrength` | Magnetic field strength H, in ampere per metre (A/m). |
| `magnetizingInductance` | Inductance associated with the magnetising current; the design-target inductance of the component. |
| `leakageInductance` | Inductance from flux that does not link all turns of the coupled winding. |
| `permeability` | Relative permeability of the material; reported as `initial`, `amplitude`, `incremental`, `reversible`, or `complex`. |
| `saturation` | BH-curve points characterising saturation flux density; by convention reported where the relative differential permeability has fallen to 10 % of the initial permeability. |
| `remanence` | Residual flux density when the applied field is zero (BH-cycle point). |
| `coerciveForce` | Field strength required to reduce flux density to zero (BH-cycle point). |
| `bhCycle` | Complete B–H hysteresis loop characterising the material. |
| `effectiveLength` | Equivalent magnetic path length per IEC 60205 / IEC 63182. |
| `effectiveArea` | Equivalent cross-sectional area perpendicular to the flux path per IEC 60205 / IEC 63182. |
| `effectiveVolume` | Product of effective length and effective area; the magnetised volume. |
| `minimumArea` | Minimum cross-sectional area along the flux path. |

## Electrical and Waveform

| Term | Definition |
|------|------------|
| `current` | Electrical current through a winding, in amperes (A). |
| `voltage` | Electrical voltage across a winding, in volts (V). |
| `frequency` | Operating frequency of the waveform, in hertz (Hz). |
| `dutyCycle` | Fraction of the period during which the signal is in its active state (0–1). |
| `deadTime` | Interval after T<sub>on</sub> and T<sub>off</sub> in switching waveforms, in seconds. |
| `peakToPeak` | Difference between the maximum and minimum values of the waveform. |
| `peak` | Maximum absolute value of the waveform. |
| `positivePeak` | Maximum positive value of the waveform. |
| `negativePeak` | Most-negative value of the waveform (≤ 0 for bipolar signals). |
| `rms` | Root-mean-square value of the periodic waveform. |
| `average` | Mean value of the waveform over one period. |
| `offset` | DC component of the waveform. |
| `phase` | Phase angle of the waveform, in degrees. |
| `harmonics` | Frequency components of a complex waveform (amplitudes and frequencies). |
| `thd` | Total harmonic distortion of the waveform. |
| `effectiveFrequency` | Equivalent sinusoidal frequency producing the same RMS rate of change (per IEEE 750181 Appendix C). |
| `waveform` | Sample-based representation of an arbitrary waveform. |
| `processed` | Higher-level descriptor of a waveform from which the waveform itself can be reconstructed. |
| `waveformLabel` | Common waveform shape (`triangular`, `rectangular`, `sinusoidal`, `flybackPrimary`, `flybackSecondary`, `custom`, …). |
| `bias` | DC component superimposed on an AC excitation. |

## Operating Conditions

| Term | Definition |
|------|------------|
| `operatingPoint` | A complete operating state: conditions plus excitations on every winding. |
| `operatingConditions` | Ambient and cooling parameters that apply to one operating point. |
| `excitation` | Per-winding signal description (frequency, current, voltage, flux density, field strength, magnetising current). |
| `ambientTemperature` | Ambient temperature at the operating point, in degrees Celsius. |
| `ambientRelativeHumidity` | Ambient relative humidity, as a fraction 0–1. |
| `cooling` | Heat-dissipation arrangement: `naturalConvection`, `forcedConvection`, `heatsink`, or `coldPlate`. |
| `outputVoltagesType` | How values in `outputVoltages` are interpreted (`dc`, `rms`, `peak`, `peakToPeak`, `average`); defaults to `dc`. |
| `outputCurrentsType` | How values in `outputCurrents` are interpreted; same enum and default as above. |

## Wire

| Term | Definition |
|------|------------|
| `wire` | Conductor used to form turns and windings. |
| `round` | Single solid circular conductor. |
| `litz` | Stranded wire of individually insulated round strands twisted together to mitigate skin and proximity effects. |
| `rectangular` | Solid conductor of rectangular cross-section. |
| `foil` | Solid flat conductor with specified width and height. |
| `planar` | Spiral conductor patterned on a PCB layer. |
| `numberConductors` | Count of separate conductors in a multi-strand wire. |
| `strand` | One round conductor in a litz bundle. |
| `twistPitch` | Length of one full twist of a litz bundle along the wire axis. |
| `outerDiameter` | Overall diameter including insulation. |
| `conductingArea` | Cross-sectional area of conducting material (rounded corners accounted for). |
| `conductingWidth` | Width of the conducting region (foil, rectangular). |
| `conductingHeight` | Height of the conducting region (foil, rectangular). |
| `standard` | Wire specification standard (IEC 60317, NEMA MW 1000 C, IPC-6012). |

## Materials

| Term | Definition |
|------|------------|
| `material` | Magnetic material composition family (`ferrite`, `powder`, `nanocrystalline`, `amorphous`, `electricalSteel`). |
| `materialComposition` | Detailed make-up (`MnZn`, `NiZn`, `FeSiAl`, `FeSi`, `FeNi`, `FeNiMo`, `FeMo`, `carbonylIron`, `iron`). |
| `resistivity` | Volume resistivity per IEC 60093, in Ω·m. |
| `density` | Mass per unit volume, in kg/m³. |
| `curieTemperature` | Temperature above which a ferromagnetic material loses its ferromagnetism. |
| `heatConductivity` | Thermal conductivity, in W/(m·K). |
| `heatCapacity` | Specific heat capacity, in J/(kg·K). |

## Insulation and Safety

| Term | Definition |
|------|------------|
| `insulationType` | Insulation classification per IEC 60664-1 §4.1: `functional`, `basic`, `supplementary`, `double`, `reinforced`. |
| `temperatureClass` | Insulation thermal class per IEC 60085 (Y/A/E/B/F/H/N/R/200/220/250). |
| `dielectricStrength` | Field strength at which insulation breaks down, in V/m. |
| `relativePermittivity` | Dielectric constant of the insulation material. |
| `creepageDistance` | Shortest path along an insulation surface between two conductive parts (IEC 60664-1). |
| `clearance` | Shortest straight-line distance through air between two conductive parts (IEC 60664-1). |
| `cti` | Comparative tracking index group per IEC 60112: `groupI`, `groupII`, `groupIIIA`, `groupIIIB`. |
| `pollutionDegree` | Pollution level per IEC 60664-1 §4.2: `PD1`, `PD2`, `PD3`, `PD4`. |
| `overvoltageCategory` | Overvoltage category per IEC 60664-1 §4.3: `I`, `II`, `III`, `IV`. |
| `surfaceResistivity` | Surface resistivity per IEC 60093, in Ω/sq. |
| `meltingPoint` | Temperature at which the insulation material melts, in degrees Celsius. |
| `interlayerInsulation` | Insulation barrier placed between adjacent layers of a winding. |
| `marginInfo` | Margin tape at the extremes of a section, used to enforce creepage. |

## Topology and Application

| Term | Definition |
|------|------------|
| `topology` | Converter topology for which the magnetic is designed (e.g. `buckConverter`, `flybackConverter`, `llcResonantConverter`, `dualActiveBridgeConverter`, `commonModeChoke`). |
| `application` | Primary application: `power`, `signalProcessing`, or `interferenceSuppression`. |
| `subApplication` | Sub-application: `powerFiltering`, `transforming`, `isolation`, `commonModeNoiseFiltering`, `differentialModeNoiseFiltering`. |
| `wiringTechnology` | Construction method: `wound`, `printed`, `stamped`, `deposition`. |
| `market` | Target market: `commercial`, `industrial`, `medical`, `military`, `space`. |

## Losses and Efficiency

| Term | Definition |
|------|------------|
| `coreLosses` | Total power dissipated in the core, in watts. |
| `hysteresisCoreLosses` | Component of core loss attributed to hysteresis. |
| `eddyCurrentCoreLosses` | Component of core loss attributed to induced eddy currents. |
| `volumetricLosses` | Core loss per unit volume, in W/m³. |
| `massLosses` | Core loss per unit mass, in W/kg. |
| `windingLosses` | Power dissipated in the winding conductors, in watts. |
| `steinmetz` | Empirical core-loss model, P = k · f<sup>α</sup> · B<sup>β</sup>. |
| `roshen` | Roshen core-loss model accounting for excess losses. |
| `skinEffect` | Tendency of AC current to concentrate near the conductor surface, raising effective resistance. |
| `proximityEffect` | Eddy currents induced in a conductor by the field of nearby conductors, raising effective resistance. |
| `fillingFactor` | Fraction of available winding-window area occupied by conductor. |
| `thermalResistance` | Steady-state temperature rise per dissipated power, in K/W. |
| `temperatureRise` | Steady-state temperature increase above ambient, in kelvins. |

## Coil Construction

| Term | Definition |
|------|------------|
| `numberTurns` | Total number of turns in a winding. |
| `numberParallels` | Number of conductors connected in parallel to form one electrical turn. |
| `isolationSide` | Label grouping windings that share a common ground reference (`primary`, `secondary`, `tertiary`, …). |
| `woundWith` | Names of other windings physically wound together (e.g. bifilar, IEV 151-13-18). |
| `connectionType` | Terminal style: `pin`, `screw`, `smt`, `flyingLead`, `tht`, `pcbPad`. |
| `bobbinFamily` | Core-shape family the bobbin is designed for (`u`, `e`, `etd`, `er`, `p`, `rm`, `ep`, `pm`, `el`, `pq`, `efd`, `ec`, `t`). |
| `wallThickness` | Thickness of the bobbin walls confining the wire on the column sides. |
| `columnThickness`, `columnDepth`, `columnWidth` | Dimensions of the bobbin's central column. |

## Standards Metadata

| Term | Definition |
|------|------------|
| `manufacturerInfo` | Manufacturer-supplied identification for a part. |
| `distributorInfo` | Distributor-supplied identification, stocking, and price information for a part. |
| `cost` | Monetary value with explicit currency: `{ value, currency }` where `currency` is an ISO 4217 three-letter code. |
| `irdi` | International Registration Data Identifier per ISO/IEC 11179-6 / ISO 29002-5, in the form `RAI#DI#VI`. |
| `datasheetInfo` | Catalogue-level data extracted directly from the manufacturer's datasheet. |
| `status` | Production status: `production`, `prototype`, `obsolete`. |

---

## See also

- [`normative-references.md`](normative-references.md) — full mapping
  to IEC, IEV, ISO, IEEE, NEMA, JIS, MPIF, ASTM standards.
- [`units.md`](units.md) — normative unit table.
- [`schema.md`](schema.md) — schema structure and required-field
  reference.
- [`quickref.md`](quickref.md) — quick reference for common patterns.
## Provenance (data-source trail)

Every `datasheetInfo` carries an optional `provenance` array recording where its data
came from. Optional and closed, so records without it remain valid. Each entry:

| field | meaning |
|---|---|
| `source` | `manufacturerDatasheet` · `manufacturerParametric` · `manufacturerDatabase` · `distributor` · `librarianEnrichment` · `scrape` · `manual` |
| `sourceName` | human-readable source, e.g. `"TI parametric API"`, `"WE - Passive Components.mdb"`, `"DigiKey"` |
| `sourceUrl` | URL the value came from (optional) |
| `retrievedDate` | `YYYY-MM-DD` (optional) |
| `fields` | which `datasheetInfo` fields this source supplied — for mixed-source records (optional) |

It is a **list**: a record may combine sources (e.g. specs from the datasheet, a rated
voltage from a distributor, a missing field back-filled by librarian enrichment). The
canonical definition lives in `PEAS/schemas/utils.json#/$defs/provenance` (aliased by
`MAS/schemas/utils.json` via `$ref`, as are the other shared definitions such as
`dimensionWithTolerance`).
