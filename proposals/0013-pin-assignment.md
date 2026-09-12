# MAS-RFC 0013 — Lead-to-pin assignment: data model and default algorithm

- **Status:** Accepted (owner decision 2026-09-12, approved by Alf; implementation in the same change set)
- **Type:** Additive (non-breaking) schema change + MKF/MVB++ behaviour
- **Author:** Alfonso Martínez (drafted 2026-09-12 with Alf)
- **Created:** 2026-09-12
- **Depends on:** nothing schema-wise; complements RFC 0010 (finished-part pinout) and the
  bobbin `pinout`/`pins` structures that already exist.

## Summary

Today a MAS coil says *which pin* a winding end is soldered to only through the free-text
`coil.functionalDescription[].connections[].pinName`, and nothing in MAS, MKF or MVB++ ever
decides that name, checks it against the bobbin's pin geometry, or routes copper to it. MVB++
ends every lead in free air on a common plane (concentric) or, since 2026-09-12, on one XZ
plane below a toroid. This RFC (1) makes the assignment unambiguous in the data model with two
small additive fields, (2) defines the default assignment algorithm MKF applies when a design
gives none, distilled from how winding shops actually do it, and (3) names the consumers.

## What exists (no change proposed)

- `bobbin.json#/functionalDescription/pinout` — pitch, `rowDistance`, `centralPitch`,
  `numberRows`, `numberPinsPerRow`, `pinDescription`. Manufacturing spec of the former.
- `bobbin.json#/processedDescription/pins[]` — per-pin `name`, `shape`, `type` (smd/tht),
  `dimensions`, `coordinates` (relative to the main column centre), `rotation`. This is the
  geometry every consumer needs; MKF does not populate it yet (see Consumers).
- `bobbin.json#/functionalDescription/connections[] {pin, winding}` — a *bobbin datasheet*
  hint ("this former is meant for primary on pins 1-6"), not the design's assignment.
- `coil.json#/$defs/connection` — `type` (PEAS `connectionType`: PIN, SMT, THT, PCB_PAD,
  FLYING_LEAD, SCREW, CHASSIS), `pinName`, `direction` (input/output), `length`, `diameter`,
  `footprint`, `landPattern`, …; attached per winding as `connections[]` (`minItems: 2`).
- `coil.json` winding `isolationSide` (**required** today) — the isolation group of a winding.

## What is proposed

### 1. Two additive fields on `coil.json#/$defs/connection`

| field | type | meaning |
|---|---|---|
| `end` | enum `start`, `finish`, `tap` | Which end of the winding this connection terminates. `start` is the dot end (first turn wound). `tap` is an intermediate junction shared with a series section. |
| `parallel` | integer ≥ 0 | Which parallel strand of the winding this connection belongs to. Absent = all parallels of the winding terminate together on this pin. |

`direction` (`input`/`output`) stays as the *electrical* current direction; it is not a
reliable proxy for start/finish (Power Integrations sheets start on the higher-numbered pin of
a pair, TDK examples on the lower one). `pinName` must match a `name` in the governing bobbin's
`processedDescription.pins[]` when the connection `type` is `PIN`, `THT` or `SMT`; a validator
rule, not a schema constraint.

### 2. One additive field on `bobbin.json#/$defs/pin`

| field | type | meaning |
|---|---|---|
| `removable` | boolean, default false | The pin may be cut off to open creepage (TDK sells the RM6 former "pin 4 omitted in 5-pin version"; corner pins are the usual candidates). |

Optional, purely additive; absent = not removable.

**Default pin numbering (owner decision, 2026-09-12).** No standard fixes bobbin pin
numbering, so a bobbin's own datasheet names always win. Where a record carries no pin names,
the reference implementation generates them **counter-clockwise starting from row 0**, seen
from the mounting side, pin 1 being the first pin of row 0. This is a naming default for
generated `pins[]`, not a schema constraint, and it is what `pinName` is matched against when
the bobbin brings no names of its own.

### 3. Default assignment algorithm (normative for MKF, informative for others)

Applied by MKF when a design has windings without a complete set of `connections[]` with
`pinName`, after winding (turn positions final) and before connection-length and lead
reservation. It never overrides a user-given `pinName`; it validates it instead.

**Inputs**
- Bobbin `processedDescription.pins[]` with coordinates, `removable`, and the row each pin
  belongs to (derived: pins sharing a coordinate along the row axis, or from `pinout` rows).
- Windings in build order (inner to outer, as wound), each with `isolationSide`,
  `numberParallels`, number of layers, wire type (enamelled / TIW / litz), and their sections
  (series sections and taps come from `sectionsDescription` + `partialWindings`).
- Required creepage and clearance per pair of isolation sides, from MKF's insulation
  coordination (IEC 60664 / 61558 / 62368 as the design requirements select).
- Role tags where the design gives them (`designRequirements` / topology): the primary end
  tied to the switching node, return ends, shield windings, flux band.

**Rules, in order**
1. **Rows are isolation groups.** Each `isolationSide` gets one row (or one contiguous pin
   block when there are more sides than rows). Sides with the largest required creepage
   between them go to opposite rows. Reject a row plan whose worst pin-to-pin surface path
   or through-core path between two sides is below the requirement; first mark `removable`
   corner pins as unused, then split blocks, then fail loudly.
2. **Start and finish are adjacent pins in the winding's row.** Walk windings in build order.
   The start pin is the row pin nearest the flange where turn 1 begins; the finish pin is the
   nearest free pin to the flange where the last layer ends (odd layer count: far flange).
3. **Series sections share the junction pin as a tap.** The finish of section k is the start of
   section k+1 (`end: tap` on both connections, same `pinName`).
4. **Parallels.** All strands of a winding share a pin while the wraps fit the pin
   (`wraps ≤ maxWiresPerPin`, default 2 for round enamelled wire ≥ 0.5 mm, 3 below). Otherwise
   adjacent pins, one per strand, with `parallel` set and a design note "shorted on PCB".
5. **Switched-node end is the start.** When the topology names it, the primary end connected
   to the switch is `start` (buried innermost). Shields: one end on the primary-return pin
   (shared with the flux band if any), the other end `type: FLYING_LEAD` with no pin (buried).
6. **No lead crossings.** Lead exits map monotonically along the flange to pins along the
   row; an outer winding never takes a pin that an inner winding's lead must pass over.
7. **High-voltage stripped ends avoid corner pins.** TIW or margin-wound leads that need
   sleeving to the pin are not assigned to corner pins; corner pins left over become anchors
   or are removed (rule 1).

**Tie-breaks:** minimum total lead length, then fewest pins used, then lower pin name as the
start, then symmetry with the bobbin datasheet's own `connections[]` hint.

**Toroids on a base** (bobbin family `t`, see the toroid-base discussion of 2026-09-12): pins
in a rectangle; winding k takes the two pins of side k; starts of all windings at the same
angular position; sectional windings on opposite halves. Vertical vs horizontal is a
mechanical choice made before assignment.

**Failure is loud.** No pin plan meeting rule 1 ⇒ MKF throws naming the offending side pair
and the shortfall in mm. A user `pinName` that violates rule 1 ⇒ throw. A `pinName` not in
the bobbin ⇒ throw. No silent fall-back to "free air".

### 4. Outputs

- `coil.functionalDescription[].connections[]` filled with `pinName`, `end`, `parallel`,
  `type` (from the bobbin pin type), `diameter`, and `length` (from the routed lead).
- The same information exposed at the finished-part level through RFC 0010's `pinout`
  (`pinFunction`: `windingStart`, `windingEnd`, `tap`, `shield`, `noConnect`) — derived, never
  authored twice.

## What is explicitly NOT proposed

- No change to `bobbin.pinout` semantics; no new pin-numbering convention (none exists in any
  standard; the bobbin's own pin names rule).
- No creepage *calculation* method: that stays in MKF's insulation coordination.
- No routing geometry in MAS: how the lead runs from the window to the pin is MKF's
  connection reservation (MKF ABT #187) and MVB++'s drawing, not data.

## Consumers

- **MKF**: (a) populate `processedDescription.pins[]` from `pinout` in each family processor
  (today all nine processors ignore it); (b) `Coil::assign_pins(const Bobbin&)` implementing
  §3; (c) connection reservation reserves the lead corridor from the window exit to the
  assigned pin instead of a straight-out stub; (d) `connections[].length` measured along that
  route.
- **MVB++**: draw pins from `pins[]`; route each terminal lead along the flange to its pin and
  end it with a wrap (2–3 turns) or a straight stub into the pin's axis; the FEM terminal cap
  moves onto the pin tip. Toroids: the -Y drops re-aimed at the base pins.
- **OMFEM**: ports on the pin tips; nothing else changes.
- **WebFrontend**: show the assignment as a winding table ("Primary: start pin 3, finish pin
  2, 2 parallels on pins 9 & 10") and let the user override per connection.

## Compatibility

Additive and optional. Existing documents stay valid (`end` and `parallel` absent). The
generated bindings gain two optional members on `Connection` and one on `Pin`.

## Sources

Power Integrations AN-18 (transformer construction guide) and the ETD44 construction sheet
(pin-by-pin winding tables, row = isolation group, sleeving rule), TDK RM6 datasheet (pin
omitted for creepage), Würth 750311424 datasheet (solder-bridged parallel pins), Lodestone
Pacific bobbin application notes (wrap turns, 6 mm creepage barrier), Mini-Circuits AN40-010 /
IPC-A-610 (wrap counts), WE-CMB 744821240 (toroid-on-base pin layout), IEC 61558 / 62368-1 via
IEC 60664 (creepage by working voltage, pollution degree, CTI).
