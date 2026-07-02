# MAS Schema Documentation

> **Informative.** This document is a structural guide to the MAS JSON
> Schema; it does not add normative requirements. For the normative
> units table see [`units.md`](units.md); for the mapping of MAS to
> existing standards (IEC, ASTM, MPIF, JIS, NEMA, IEV vocabulary) see
> [`normative-references.md`](normative-references.md).

This document describes the JSON Schema structure for MAS (Magnetic
Agnostic Structure).

## Schema Hierarchy

```
MAS.json (root)
├── inputs.json
│   ├── designRequirements.json
│   │   └── (insulation, tolerances, etc.)
│   ├── operatingPoint.json
│   │   ├── operatingConditions.json
│   │   └── operatingPointExcitation.json
│   └── topologies/
│       ├── buck.json
│       ├── flyback.json
│       └── ...
├── magnetic.json
│   ├── core.json
│   │   ├── functionalDescription (shape, material, gapping)
│   │   ├── geometricalDescription (detailed geometry)
│   │   └── processedDescription (computed values)
│   ├── coil.json
│   │   ├── functionalDescription (windings, turns)
│   │   ├── layersDescription
│   │   └── turnsDescription
│   ├── wire.json
│   │   ├── round/
│   │   ├── litz/
│   │   ├── rectangular/
│   │   └── foil/
│   └── bobbin.json
└── outputs.json
    ├── coreLosses
    ├── windingLosses
    ├── magnetizingInductance
    └── leakageInductance
```

## Required vs Optional Fields

### MAS Root (required: all three)
```json
{
  "inputs": { ... },      // Required
  "magnetic": { ... },    // Required
  "outputs": [ ... ]      // Required (can be empty array)
}
```

### Inputs (required: designRequirements, operatingPoints)
```json
{
  "designRequirements": {
    "magnetizingInductance": { ... },  // Required
    "turnsRatios": [ ... ],            // Required (empty for inductor)
    "topology": "string",              // Required
    "name": "string",                  // Optional
    "operatingTemperature": { ... },   // Optional
    "insulation": { ... },             // Optional
    "maximumDimensions": {             // Optional: {width, height, depth} object, in m
      "width": number, "height": number, "depth": number
    },
    "maximumWeight": number,           // Optional
    "market": "string",                // Optional
    "terminalType": [ ... ]            // Optional
  },
  "operatingPoints": [                 // Required, min 1 item
    {
      "name": "string",                // Optional
      "conditions": {                  // Required
        "ambientTemperature": number   // Required
      },
      "excitationsPerWinding": [ ... ] // Required, one per winding
    }
  ]
}
```

### Magnetic (no required fields — a bare magnetic is valid, seed-friendly)
```json
{
  "name": "string",                    // Optional
  "core": {                            // Optional
    "name": "string",                  // Optional
    "functionalDescription": {         // Required within core
      "type": "string",                // Required: "twoPieceSet", "toroidal", etc.
      "material": "string",            // Required: material name
      "shape": "string",               // Required: shape name
      "gapping": [ ... ],              // Required: array (empty for ungapped)
      "numberStacks": number           // Optional, default 1
    }
  },
  "coil": {                            // Optional
    "bobbin": "string",                // Optional
    "functionalDescription": [         // One object per winding
      {
        "name": "string",              // Optional
        "numberTurns": number,         // Required
        "numberParallels": number,     // Required
        "wire": "string",              // Required: wire name
        "isolationSide": "string"      // Optional: "primary", "secondary", etc.
      }
    ]
  }
}
```

## Enumeration Values

### Core Types
- `"twoPieceSet"` - E, ETD, PQ, RM cores
- `"toroidal"` - Ring/toroid cores
- `"closedShape"` - Pot cores
- `"pieceAndPlate"` - Core with flat plate

### Gapping Types
- `"subtractive"` - Ground gap (reduces core height)
- `"additive"` - Spacer gap (increases core height)
- `"residual"` - Unavoidable gap at mating surfaces

### Waveform Labels
- `"triangular"`, `"triangularWithDeadtime"` - Triangular wave (inductor current)
- `"rectangular"`, `"rectangularWithDeadtime"`, `"rectangularDCM"` - Rectangular/square wave variants
- `"unipolarRectangular"`, `"unipolarTriangular"` - Unipolar (single-polarity) variants
- `"bipolarRectangular"`, `"bipolarTriangular"` - Bipolar (symmetric) variants
- `"sinusoidal"` - Sine wave
- `"flybackPrimary"`, `"flybackSecondary"`, `"flybackSecondaryWithDeadtime"` - Flyback current shapes
- `"secondaryRectangular"`, `"secondaryRectangularWithDeadtime"` - Secondary-side rectangular shapes
- `"custom"` - User-defined with data points

### Insulation Types (IEC 60664-1 §4.1)
- `"functional"` - Basic operation only, no protection against shock
- `"basic"` - Single level of protection against electric shock
- `"supplementary"` - Independent insulation additional to basic
- `"double"` - Basic insulation plus supplementary insulation
- `"reinforced"` - Single insulation system equivalent to double

### Overvoltage Categories (IEC 60664-1 §4.3)
- `"I"` - Low transient overvoltage (protected equipment)
- `"II"` - Household appliances connected to fixed installation
- `"III"` - Fixed installation equipment
- `"IV"` - Equipment at the origin of the installation

### Pollution Degrees (IEC 60664-1 §4.2)
- `"PD1"` - No pollution or only dry, non-conductive pollution
- `"PD2"` - Non-conductive pollution; temporary conductivity possible
- `"PD3"` - Conductive pollution, or dry non-conductive that becomes conductive due to condensation
- `"PD4"` - Persistent conductive pollution (e.g. conductive dust or rain)

### CTI Groups (IEC 60112)
- `"groupI"` - CTI ≥ 600
- `"groupII"` - 400 ≤ CTI < 600
- `"groupIIIA"` - 175 ≤ CTI < 400
- `"groupIIIB"` - 100 ≤ CTI < 175

### Markets
- `"commercial"`, `"industrial"`, `"medical"`, `"automotive"`, `"military"`, `"space"`

### Topologies
- `"buckConverter"`, `"boostConverter"`, `"sepicConverter"`, `"cukConverter"`, `"zetaConverter"`, `"fourSwitchBuckBoostConverter"`
- `"flybackConverter"`, `"activeClampForwardConverter"`, `"singleSwitchForwardConverter"`, `"twoSwitchForwardConverter"`
- `"pushPullConverter"`, `"weinbergConverter"`, `"asymmetricHalfBridgeConverter"`
- `"phaseShiftedFullBridgeConverter"`, `"phaseShiftedHalfBridgeConverter"`
- `"llcResonantConverter"`, `"cllcResonantConverter"`, `"clllcResonantConverter"`, `"seriesResonantConverter"`, `"dualActiveBridgeConverter"`
- `"isolatedBuckConverter"`, `"isolatedBuckBoostConverter"`
- `"powerFactorCorrection"`, `"viennaRectifierConverter"`
- `"currentTransformer"`, `"commonModeChoke"`, `"differentialModeChoke"`

## DimensionWithTolerance Pattern

Used throughout MAS for numeric values with tolerances:

```json
// At least one of these is required:
{
  "nominal": number,        // Typical/target value
  "minimum": number,        // Lower bound
  "maximum": number,        // Upper bound
  "excludeMinimum": bool,   // true = > not >=
  "excludeMaximum": bool    // true = < not <=
}
```

Examples:
```json
// Just nominal
{"nominal": 100e-6}

// With ±10% tolerance
{"nominal": 100e-6, "minimum": 90e-6, "maximum": 110e-6}

// Maximum only
{"maximum": 0.001}
```

## Validation

The schemas use JSON Schema Draft 2020-12. Validate with:

```python
import glob
import json

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# Register every schema file under its $id (https://psma.com/mas/...).
# Include the sibling PEAS schemas too, since MAS $refs them.
resources = []
for path in glob.glob("schemas/**/*.json", recursive=True) + \
            glob.glob("../PEAS/schemas/**/*.json", recursive=True):
    with open(path) as f:
        contents = json.load(f)
    resources.append((contents["$id"], Resource.from_contents(contents)))
registry = Registry().with_resources(resources)

# Load schema
with open("schemas/MAS.json") as f:
    schema = json.load(f)

validator = Draft202012Validator(schema, registry=registry)

# Validate document
with open("my_design.json") as f:
    data = json.load(f)

validator.validate(data)
```

`scripts/validate-samples.py` does exactly this for every document under
`samples/complete/`; `scripts/validate-fixtures.py` validates the
per-record sub-schema fixtures under `samples/`; `scripts/validate-db.py`
validates every record in `data/*.ndjson` (records in
`advanced_core_materials.ndjson` are heavy-field patches and are
validated merged onto their base `core_materials.ndjson` material, never
standalone).

## File Locations

| File | Purpose |
|------|---------|
| `schemas/MAS.json` | Root schema |
| `schemas/inputs.json` | Inputs section |
| `schemas/magnetic.json` | Magnetic section |
| `schemas/outputs.json` | Outputs section |
| `schemas/inputs/*.json` | Input sub-schemas |
| `schemas/magnetic/*.json` | Magnetic sub-schemas |
| `schemas/outputs/*.json` | Output sub-schemas |
| `data/*.ndjson` | Component databases |
