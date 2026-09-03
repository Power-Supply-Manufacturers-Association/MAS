# MAS-RFC 0012 — Native PCB (planar) manufacturing description: `group.pcb` and terminal details on `connection`

- **Status:** Accepted (owner decision 2026-09-03; implementation in the same change set)
- **Type:** Additive, non-breaking (`pcb` is optional on printed groups; forbidden on non-printed ones)
- **Author:** Alfonso Martínez
- **Created:** 2026-09-03

## 1. Summary

MAS already describes a planar coil *electromagnetically*: `coil.groupsDescription[].type =
"printed"`, planar wires (`wire/planar.json`: conducting/outer width × height), and MKF's
`Coil::wind_planar` emits `sectionsDescription`/`layersDescription`/`turnsDescription` with
exact per-turn `(r, z)` centres, `dimensions = [trackWidth, copperThickness]`, one winding per
copper layer, and *insulation* layers carrying the inter-copper dielectric thickness.

What MAS **cannot** express today is everything a fabricator or a PCB CAD tool needs beyond the
copper geometry. Each item below is currently either invented by `auto_planar/source/mas_design.py`
(`DEFAULT_CLEARANCES`, `DEFAULT_VIAS`, `+0.01` outline margin, `connector.diameter = 0.0007`) or
hardcoded in `MVB++/src/FR4Builder.cpp` (`DEFAULT_BORDER_TO_WIRE_DISTANCE = 90 µm`,
`DEFAULT_CORE_TO_LAYER_DISTANCE = 250 µm`, `MIN_FR4_THICKNESS = 0.5 mm`):

| # | Missing today | Consumer |
|---|---|---|
| 1 | Via: outer diameter, drill, type (through / blind / buried) | MPB (vias), MVB++ (3D vias), MKF (real-winding reserved space) |
| 2 | Design rules: track↔track, copper↔core cut-out, via↔via, via↔track, copper↔board edge | MPB, MKF `wind_planar` (pitch = width + trackToTrack; first turn = column + coreToTrack) |
| 3 | Board outline: overall width/depth, margin from core to edge, corner radius | MPB, MVB++ FR4 solid |
| 4 | Outer dielectric (prepreg/soldermask above top and below bottom copper) — internal dielectrics are already MAS insulation layers | MVB++ FR4 thickness, MPB stackup |
| 5 | Terminals: type, diameter/metric, male/female, blind/through, castellated, pad size | MPB footprints (land patterns via PEAS, RFC 0010) |
| 6 | Copper layer ordering ↔ MAS `layer` mapping | derivable (sort conduction layers by z) — **no new field**, see §4 |
| 7 | Per-turn trace path (racetrack with fillets / concentric arcs), via band positions | **derived**, not stored — see §4 |

## 2. Proposed attachment point

**`coil.groupsDescription[].pcb`** (optional object; forbidden when `group.type != "printed"`, expressed with
`if/then` in `coil.json#/$defs/group`). It is deliberately NOT required on printed groups: only consumers that
draw the board (MPB, MKF's planar real-winding placement) need it and they fail loudly without it; MKF's ideal
winding, the advisers, the web viewer and existing planar documents are unaffected, and nobody has to invent
fabrication data to stay schema-valid (decision 2026-09-03, superseding the first cut that made it required).

Rationale: the `group` is already the container MAS documents as "used for PCB or different
winding windows", its `type` is the `wiringTechnology` enum whose `printed` value *is* the PCB
marker, MKF `create_default_groups(..., WiringTechnology::PRINTED, …)` builds it, and MVB++
`FR4Builder` keys off the first `PRINTED` group. A stacked multi-board planar = multiple printed
groups, each with its own `pcb`. Alternatives considered: `bobbin.functionalDescription.family =
"pcb"` (a PCB is not a bobbin; `processedDescription` is the *winding window*, not the board) and
a new top-level `magnetic.pcbs[]` (breaks the group ↔ board 1:1 that MKF/MVB++ already assume).

## 3. Proposed `$defs/pcb` (all lengths in metres, per MAS-RFC 0001). Implemented as `coil.json#/$defs/{pcb,pcbVias,pcbDesignRules,pcbOutline,pcbOuterDielectric}`; terminals are NOT a `pcb` sub-object: `$defs/connection` gained `footprint`, `diameter`, `gender`, `mounting`, `padWidth`, `padDepth`, `landPattern` (PEAS) instead, see the resolved questions below.

```jsonc
"pcb": {
  "type": "object",
  "additionalProperties": false,
  "required": ["vias", "designRules", "outline"],
  "properties": {
    "vias": {
      "type": "object", "additionalProperties": false,
      "required": ["diameter", "drillDiameter"],
      "properties": {
        "diameter":      { "$ref": "/schemas/utils.json#/$defs/dimensionWithTolerance" },
        "drillDiameter": { "$ref": "/schemas/utils.json#/$defs/dimensionWithTolerance" },
        "type":          { "enum": ["through", "blind", "buried"], "default": "through" }
      }
    },
    "designRules": {
      "type": "object", "additionalProperties": false,
      "required": ["trackToTrack", "coreToTrack", "viaToVia", "viaToTrack"],
      "properties": {
        "trackToTrack": { "type": "number", "exclusiveMinimum": 0 },   // legacy clearances.track_to_track
        "coreToTrack":  { "type": "number", "exclusiveMinimum": 0 },   // legacy clearances.core_to_track  (== MKF borderToWireDistance/coreToLayerDistance)
        "viaToVia":     { "type": "number", "exclusiveMinimum": 0 },   // legacy clearances.via_to_via
        "viaToTrack":   { "type": "number", "exclusiveMinimum": 0 },   // legacy clearances.via_to_track
        "copperToEdge": { "type": "number", "minimum": 0 },            // optional; NO default: when absent the copper-to-edge rule is coreToTrack (state it in the RFC)
        "holeToHole":   { "type": "number", "minimum": 0 },            // optional; drill-to-drill (fab rule). Legacy inputs never had it, so the legacy generator's pad grids only pass KiCad's own default (0.25 mm)
        "holeToCopper": { "type": "number", "minimum": 0 }             // optional; drill edge to other-net copper
      }
    },
    "outline": {
      "type": "object", "additionalProperties": false,
      "required": ["width", "depth"],
      "properties": {
        "width":        { "type": "number", "exclusiveMinimum": 0 },   // legacy inputs_pcb.dimensions.width
        "depth":        { "type": "number", "exclusiveMinimum": 0 },   // legacy inputs_pcb.dimensions.height (MAS uses width/depth/height = x/y/z, RFC 0009)
        "cornerRadius": { "type": "number", "minimum": 0 },
        "coreCutoutClearance": { "type": "number", "minimum": 0 }      // gap between core column faces and the board cut-out edge (legacy uses coreToTrack for both; splitting them is a deliberate improvement)
      }
    },
    "outerDielectric": {                                                 // §1 item 4
      "type": "object", "additionalProperties": false,
      "properties": {
        "topThickness":    { "type": "number", "minimum": 0 },
        "bottomThickness": { "type": "number", "minimum": 0 },
        "material":        { "type": "string" }                          // same vocabulary as coil.layer.insulationMaterial ("FR4")
      }
    },
    "terminals": {                                                       // §1 item 5, one entry per winding, keyed by winding name
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["winding", "type"],
        "properties": {
          "winding":     { "type": "string" },
          "type":        { "enum": ["pin", "banana", "redcube", "pad", "castellated"] },   // legacy connector.type (+castellated promoted from bool)
          "diameter":    { "type": "number" },                             // legacy connector.diameter
          "metric":      { "type": "integer", "enum": [3, 4, 5] },          // legacy connector.metric
          "gender":      { "enum": ["male", "female"] },                    // legacy male_or_/female
          "mounting":    { "enum": ["throughHole", "blind"] },              // legacy blind_or_/through_hole
          "padWidth":    { "type": "number" }, "padDepth": { "type": "number" },  // legacy width/height for type=pad
          "landPattern": { "$ref": "https://psma.com/peas/utils.json#/$defs/landPattern" }  // preferred over the enum above once RFC 0010 lands
        }
      }
    }
  }
}
```

Open questions, resolved 2026-09-03:

- Rules as plain `number` vs `dimensionWithTolerance`. Decided: **plain number** — a clearance rule has no
  tolerance; via/drill sizes **do** (fab tolerance) and use `dimensionWithTolerance`.
- Should `terminals` live here or in `coil.functionalDescription[].connections[]` (MAS
  `$defs/connection` already has `type`, `metric`, `pinName`)? **Extend `connection`** with the
  missing fields (`gender`, `mounting`, `padWidth/Depth`, `landPattern`) and keep `pcb.terminals`
  out — one place for "how does this winding end". Needs a PEAS `connectionType` check for
  `banana`/`redcube`/`castellated`. Decided: **extend `connection`**; PEAS `connectionType` is not touched: pin -> `pin`, RedCube -> `screw` (+`metric`, `gender`, `mounting`), pad grid -> `pcbPad` (+`padWidth`/`padDepth`), banana -> `tht` with an explicit `footprint`; `mounting: castellated` replaces the legacy boolean.
- `copperToEdge` default. Decided: optional, with the stated rule 'absent = coreToTrack' (a documented semantic, not a silent fallback).

### Notes from the MPB implementation (2026-09-03)

- KiCad polygonises circular cut-outs for DRC with `max_error` (5 µm) biased outward; copper placed exactly at
  `coreToTrack` measures 0.5 µm short. MPB keeps the geometry exact and emits the KiCad rule as
  `coreToTrack − max_error`, pinning `max_error` in the project. Not a schema concern, recorded so nobody
  "fixes" it by padding the geometry (which would break the MKF radius contract).
- MPB routes **one parallel per copper layer** (the legacy constraint). MKF's default `wind_planar` lays the
  parallels of a winding side by side on one layer; `mpb::wind_with_mkf` therefore passes a stack-up with one
  copper layer per (winding, parallel). Whether MAS should record the routing intent (one parallel per layer vs
  side by side) is a question for the RFC discussion.
- "connections" layers (via fan-out copper, no turns) are inserted by MPB per the legacy rule; they are copper
  layers that MAS does not know about. Either MAS gets `pcb.connectionLayers` or they stay derived.

## 4. What is *derived*, and therefore NOT added to the schema

- **Copper layer index**: conduction layers sorted by `layer.coordinates[1]` descending (top → bottom).
  MKF already lays sections top→bottom from the group height. `F.Cu` = highest z.
- **Internal dielectric thickness**: `layersDescription[type == insulation].dimensions[1]` (MKF
  emits these, default `Defaults::pcbInsulationThickness = 100 µm`).
- **Turn centreline path**: from `bobbin.processedDescription.columnShape` (`round` → concentric
  arcs, `rectangular`/`oblong` → racetrack with fillet radius = `turn.coordinates[0] − columnWidth/2`),
  radius = `turn.coordinates[0]`, width = `turn.dimensions[0]`. This is exactly what MVB++
  `TurnBuilder` does in 3-D; MPB does it in 2-D. Storing it would duplicate MKF geometry.
- **Via band position / count**: from `pcb.vias`, `pcb.designRules`, number of parallels and
  turns-per-layer. When `coilUseRealWindingGeometry` is on, MKF must *reserve* this band (see §6).
- **Core cut-outs**: from `core.processedDescription.columns[]` (shape, width, depth, coordinates).

## 5. Legacy → MAS mapping (proof that no adapter is needed after this RFC)

| legacy `inputs_pcb` / `inputs_windings` / `inputs_layers` | MAS |
|---|---|
| `central_hole_dimensions.{shape,width,height}` | `core.processedDescription.columns[type=central].{shape,width,depth}` (existing) |
| `lateral_hole_dimensions.{shape,width,height}` | `core.processedDescription.columns[type=lateral]` (existing) |
| `lateral_hole_dimensions.window_width` | `core.processedDescription.windingWindows[0].width` (existing) |
| `lateral_hole_dimensions.aperture_height` | derived from core shape (existing) |
| `dimensions.{width,height}` | `group.pcb.outline.{width,depth}` **(new)** |
| `clearances.*` | `group.pcb.designRules.*` **(new)** |
| `vias.{diameter,drill_diameter}` | `group.pcb.vias.{diameter,drillDiameter}` **(new)** |
| `windings[].conductor_width/height` | `functionalDescription[].wire.conductingWidth/Height` (existing) |
| `windings[].number_turns/parallels/isolation_side` | `functionalDescription[].numberTurns/numberParallels/isolationSide` (existing) |
| `windings[].number_layers` | count of `layersDescription[partialWindings.winding == w]` (existing, derived) |
| `windings[].connector.*` | `functionalDescription[].connections[]` extended, or `group.pcb.terminals[]` **(new, §3 open question)** |
| `layers[].layer_type` (wiring/connections/insulation) | `layer.type` conduction/insulation (existing). "connections" layers (via-fanout copper) are **derived** — they are conduction layers with zero turns |
| `layers[].layer_turns_indexes / layer_parallels_indexes / layer_windings` | `turnsDescription[].{layer, parallel, winding}` (existing) |
| `layers[].via_info`, `routing_type` | derived at generation time (never persisted) |

## 6. Consequences for MKF (separate ABT ticket, not part of the schema RFC)

1. `Coil::wind_planar` takes `borderToWireDistance`/`wireToWireDistance`/`coreToLayerDistance`
   as *arguments with `Defaults`*; after this RFC it must read `group.pcb.designRules`
   (`coreToTrack`, `trackToTrack`) and throw when the group is printed and `pcb` is absent.
2. Turn placement rule: MKF centres the turn block in the layer (`turnsBlockMargin = max((layerWidth
   − turnsBlockWidth)/2, borderToWireDistance)`), auto_planar left-justifies from the column
   (`column/2 + coreToTrack + n·(width + trackToTrack)`). Decision 2026-09-03: **MKF is
   authoritative**; MPB reads `turn.coordinates[0]`. Whether MKF should switch to left-justified
   (better coupling to the centre post, what every planar vendor does) is an MKF question to raise
   in the same ticket.
3. Real winding geometry for planar (`Coil.cpp:4744` throws today, ABT #492 ruling): implement as
   *reserved space* — the via band (`vias.diameter + viaToTrack`, times parallels where needed) and
   the terminal corridor consume radial room on the layers that own them, using the same blocking
   machinery as ABT #187/#229/#492, so turn radii already leave room for vias. MPB then places
   vias in the reserved band and asserts every turn radius equals MAS.
