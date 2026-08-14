# MAS-RFC 0011 — Machine-readable data provenance for catalogue records

- **Status:** Draft
- **Type:** Additive (target: 0.3.0)
- **Author:** _to be assigned_
- **Created:** 2026-08-14
- **Numbering note:** `0010` is taken by an existing draft
  (pinout / landPattern for finished magnetics, referenced by ABT #476 as
  "MAS-RFC 0010 (draft, committed bf8964f)"). That file is not present in
  this checkout, so this RFC takes **0011** rather than risk a collision.
  If 0010 turns out to have been withdrawn, this RFC does *not* reclaim
  the number — withdrawn numbers are kept for the historical record per
  `proposals/README.md` §6.

## Summary

MAS catalogue records carry values that are real and useful but are **not
vendor measurements**: numbers computed from a published relation, curves
digitised off vendor artwork, class-typical constants borrowed from a
sibling grade, coefficients fitted by a house script, values transcribed
from a reseller rather than the maker. Today MAS has no machine-readable
way to say so. The only place that information is recorded is prose in
`commercialName` — a field whose schema description is *"The name of a
magnetic material together its manufacturer"* and whose longest instance
in `data/core_materials.ndjson` is **5 515 characters**.

This RFC proposes that MAS **adopt the existing PEAS `provenance` type**
— which MAS already aliases in `schemas/utils.json` and already uses on
`magnetic.json` — on `core/material.json` and the other catalogue record
roots, plus a MAS-local convention for the existing `fields` member so
that a trail entry can point at a specific field or points-array. No new
type is invented, and nothing is duplicated.

## Motivation

### The concrete cases

Six tickets from a single week, all the same defect class: a value that
is not what its record says it is.

**ABT #706 — computed values tagged `origin: "manufacturer"`.** Nanoperm
1000 / 2000 / 4000 / 8000 / 30000 / 80000 / 90000 each carry 98
`massLosses` points, **byte-identical across all seven grades** (md5
`f1a1339654d17afae310aa5031eb333d`), every point tagged
`origin: "manufacturer"`. They are not measurements. They are the
classical thin-ribbon eddy-current law

```
Pv = pi^2 * d^2 * f^2 * B^2 / (6 * rho)
```

evaluated from Magnetec's own published constants: with the published
`rho = 115 uOhm.cm` the implied ribbon thickness is `d = 21.3 um`, dead
centre of Magnetec's published 17–23 um band, and the resulting curve
hits Magnetec's published 80 W/kg at 100 kHz / 0.3 T to 0.35 % (80.28 vs
80.00). A free 3-parameter fit lands on `alpha = 2.0045`,
`beta = 2.0003` at 0.316 % mean error over 98 points — a formula has no
grade dependence, which is exactly why the block is byte-identical seven
times over. And because the classical eddy term omits hysteresis, these
"manufacturer" points sit **13 % below Magnetec's own published relation
at 50 kHz, 28 % below at 20 kHz and 60 % below at 1 kHz**. A future
refit that reads them as measurements would mint a model that
under-predicts the manufacturer's own published figure. Nothing in the
file says any of this; the record's `commercialName` is empty.

**ABT #703 — borrowed class-typical scalars presented as vendor data.**
`AT&M 1K107` carries `curieTemperature: 570`, `density: 7300` and
`resistivity: 1.15e-6`. AT&M publishes **none of the three**; they were
taken from generic "FeCuNbSiB class" values when the record was created
(2026-07-15). Its `commercialName` is likewise empty, so today the record
is indistinguishable from one whose three scalars came off a datasheet.
The same gap blocks the import of the whole AT&M range (1K107H / B / BW /
E / O / W, FN-200/100/080/035), so whatever precedent is set here
propagates.

**ABT #314 — hand-generated curve presented as vendor artwork.** ACME's
complex-permeability charts draw mu' only up to ferromagnetic resonance
(A06: 1.26 MHz), but MAS stored mu' for the A family all the way to
100 MHz, going smoothly negative past resonance. Those points are not in
the artwork; somebody generated them. The mu'' in the same records *is* a
faithful digitisation (reproduced to 1.1 % mean), which is precisely what
made the synthetic mu' tail hard to spot. Resolved by truncation — 152 to
166 points removed per record — but only after an audit. A provenance
entry saying "digitised from vendor chart, extent 1 kHz–1.26 MHz" would
have made the fabricated tail self-evident.

**ABT #632 / #575 — reseller-sourced values, and a borrowed constant.**
46 NiZn grades were built from the **reseller's** table (Halo Cosmos, a
trading house) rather than the maker's (Sincores). Where both publish,
they disagree on fields MKF consumes: D2H `mu_i` 200 vs 180 and Curie
250 vs >290 °C; S1A `mu_i` 550 vs 500; S2K `mu_i` 2000 vs 2100, Curie 80
vs >110 °C, density 4700 vs 4900. Twenty of the 46 grades are **still**
reseller-only and cannot be cross-checked at all. Separately, all 46
carry the same **borrowed `1e6 ohm*m` resistivity** (ABT #575) taken from
comparable NiZn records (B45, NB50S) because neither vendor publishes one.

**ABT #640 — a model that is only valid on a curve, not on a plane.**
Six house Steinmetz fits sit on a degenerate (f, B) locus — one flux
density per frequency — which makes `alpha` and `beta` mathematically
unseparable. DMR52's fitted `beta = 1.13` (loss almost linear in B, which
no ferrite does) is an artefact of the data geometry, not a bad fit.
`DMR28` range 1's `beta = 1.000542` is **pinned at the fitter's own lower
bound** (`BETA_LO = 1.0` in `scripts/refit-steinmetz.py`). MKF will
happily evaluate these materials at any B a design asks for, and away
from the measured locus the answer is arbitrary. The limitation is
currently recorded in prose only.

**ABT #645 — a `ct` that was never identifiable.** The fitter now refuses
to emit a temperature polynomial from fewer than 3 distinct temperatures
(a 3-parameter parabola in T is not identifiable below that), but older
single-temperature refits may still be carrying `ct` values that nothing
supported. Eleven CF grades (CF124…CF297A, 22 Steinmetz ranges) share one
identical `ct` polynomial to the last digit — `ct(-40)=2.492`,
`ct(25)=1.000`, `ct(100)=0.567`, `ct(140)=0.901` — and not one of the
eleven has a single measured loss point in MAS to corroborate it.

### What these have in common

In every case the *value* is defensible and worth keeping. What is wrong
is that the record **claims a status the value does not have**. A
consumer — MKF, a fitter, a reviewer, a downstream advisor — cannot tell
a measured point from a computed one, a maker's number from a reseller's,
a fit constrained by data from a fit pinned at a solver bound.

## What exists today, and why it fails

### 1. Prose in `commercialName`

The status quo is honest prose. It is genuinely good prose — e.g. D2H:

> "…THREE FIELDS ARE NOT VENDOR-PUBLISHED and are marked here rather than
> passed off as measured: (1) volumetricLosses is deliberately EMPTY …
> (2) resistivity is BORROWED: 1e6 ohm*m, the value carried by the
> comparable NiZn records already in MAS (B45, NB50S)…"

Measured over `data/core_materials.ndjson` (954 records):

| metric | value |
|---|---|
| `commercialName` mean length | 271 characters |
| longest `commercialName` (S4H) | **5 515 characters** |
| records with `commercialName` > 200 chars | 153 |
| records whose `commercialName` contains a caveat keyword (`borrowed`, `reseller`, `class-typical`, `synthesised`, `not published`, `derived`, `assumed`, `generic`) | **97** |

Ninety-seven records — a tenth of the material catalogue — are using a
name field as a provenance essay. Why that fails:

- **Not machine-readable.** No consumer can act on it. There is no query
  that answers "give me every material whose loss model was fitted rather
  than published", or "exclude reseller-sourced grades from this study".
- **Not validatable.** A schema validator, or Blade Runner, cannot check
  that a computed value is labelled as computed, because there is no
  field to check.
- **It is not even reliably applied.** The two worst cases in this RFC —
  the seven Nanoperm grades and `AT&M 1K107` — have an **empty**
  `commercialName`. The prose convention protects exactly those records
  whose author happened to remember it.
- **It abuses a typed field.** `commercialName`'s schema description is
  "The name of a magnetic material together its manufacturer". Anything
  that renders a material name in a UI renders 5 KB of caveats.
- **It cannot be scoped.** Prose cannot say *which* of a record's forty
  fields the caveat applies to in a way a machine can resolve.

### 2. The free-form `origin` string on loss points

`volumetricLossesPoint` and `massLossesPoint` each have a **required**
`origin` of `type: "string"`, described as "Origin of the data
(datasheet, measurement, simulation, fitted)" — but with no `enum`, so
the description is advisory. What the corpus actually contains:

| `origin` value | count | file |
|---|---|---|
| `MagNet` | 27 588 | `advanced_core_materials.ndjson` |
| `manufacturer` | 19 233 | `advanced_core_materials.ndjson` |
| `manufacturer` | 18 | `core_materials.ndjson` |
| `datasheet` | 10 | `core_materials.ndjson` |

Three distinct values across 46 849 points, none of which can express
"computed from the vendor's published constants", "digitised from a
chart", or "borrowed from a sibling grade" — which is why the Nanoperm
points are tagged `manufacturer`. It is also worth stating plainly:
**MKF never reads this field.** A grep of `MKF/src` finds no consumer of
`VolumetricLossesPoint::get_origin()`; the only `origin` MKF sets is the
unrelated `ResultOrigin` on *output* blocks. So the one machine-readable
provenance hook MAS already has is both under-specified and unused.

### 3. Nothing at all for scalars, curves, or models

`resistivity`, `density`, `curieTemperature`, `saturation`,
`permeability` points, `bhCycle` points and every
`*CoreLossesMethodData` block have no origin field of any kind.
`core/material.json` is `additionalProperties: false`, so a record
**cannot** carry provenance today even out-of-band. That closure is
correct and should stay — it is also why this RFC is required rather than
optional.

## PEAS already has the type

This is the decisive finding, and it makes the proposal small.

`PEAS/schemas/utils.json` (`$id: https://psma.com/peas/utils.json`)
defines, at `#/$defs/provenance`:

```json
"provenance": {
  "title": "provenance",
  "description": "Data-provenance trail for this record's data. A list, because different fields may come from different sources … the definition is deliberately record-neutral: CIAS $refs it for a whole circuit brick, which has no datasheetInfo at all, and a DERIVED brick's trail describes how the brick itself was generated.",
  "type": "array",
  "items": {
    "type": "object",
    "additionalProperties": false,
    "required": ["source"],
    "properties": {
      "source":        { "type": "string",
                         "enum": ["manufacturerDatasheet", "manufacturerParametric",
                                  "manufacturerDatabase", "distributor",
                                  "librarianEnrichment", "scrape", "manual", "derived"] },
      "derivation":    { "type": "string" },
      "sourceName":    { "type": "string" },
      "sourceUrl":     { "type": ["string", "null"], "format": "uri" },
      "retrievedDate": { "type": ["string", "null"] },
      "fields":        { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

Two properties of that definition matter here:

- `source: "derived"` is documented as marking values **COMPUTED from
  other fields of the same record (never measured, never read from a
  document)**, and *"a derived entry must say how in `derivation`, so a
  consumer can distinguish vendor fact from arithmetic."* That is the
  Nanoperm case, written down in PEAS before we found it.
- `fields` is *"which fields of this record this source provided (for
  mixed-source records)"* — the granularity hook this RFC needs.

**MAS already aliases it.** `MAS/schemas/utils.json:407`:

```json
"provenance": {
  "$ref": "https://psma.com/peas/utils.json#/$defs/provenance",
  "$comment": "Alias to the canonical PEAS provenance (the former inline copy was byte-identical)."
}
```

**And MAS already uses it**, on exactly one site —
`magnetic.json:106`, inside `magneticDatasheetInfo`:

```json
"provenance": {
  "description": "Data-provenance trail (see provenance).",
  "$ref": "./utils.json#/$defs/provenance"
}
```

So the type exists, MAS points at it, and the generated
`MKF/MAS/MAS.hpp` already contains `class Provenance` with
`get_provenance() / set_provenance()`. What is missing is not a type —
it is the *attachment points*.

### How the other modules use it

Consistent across the family, and this RFC follows them exactly:

| module | attachment | form |
|---|---|---|
| CAS `capacitor.json` | `datasheetInfo.provenance` | `$ref` PEAS, **optional** |
| RAS `resistor.json`, `thermistor.json`, `varistor.json` | `datasheetInfo.provenance` | `$ref` PEAS, optional |
| SAS `mosfet/igbt/bjt/diode/module.json` | `datasheetInfo.provenance` | `$ref` PEAS, optional |
| AAS, CTAS, TDAS, CONAS, COAS | `datasheetInfo.provenance` | `$ref` PEAS, optional |
| CIAS `CIAS.json` | **record root** (a brick has no `datasheetInfo`) | `$ref` PEAS, optional — approved 2026-08, ABT #479 |
| MAS `magnetic.json` | `datasheetInfo.provenance` | `$ref` via MAS alias, optional |

Two observations worth recording for the committee:

1. **It is optional everywhere.** A scan of every `*/schemas/*.json`
   under PSMA finds `provenance` in **zero** `required` arrays. The
   organisational rule that "provenance is required on every part" is a
   *data policy* enforced outside the schema, not a schema constraint.
2. **CIAS is the precedent for this RFC.** A core material is like a
   CIAS brick and unlike a capacitor: it is not a purchasable part with a
   `datasheetInfo` block, it is a *characterisation*. CIAS's decision to
   hang `provenance` on the record root — explicitly so that a
   **derived** brick can record "how it was generated" — is the same
   shape as a Nanoperm loss block.

## Proposal

### 1. Attach the existing PEAS provenance to the catalogue record roots

Add one optional property to each catalogue record root, via the MAS
alias (so MAS keeps a single `$ref` surface onto PEAS):

```json
"provenance": {
  "description": "Data-provenance trail for this record (see provenance). Entries whose `fields` is absent describe the record as a whole; entries with `fields` describe only the listed locations. Any value that was not read from the named source as printed — computed, digitised, fitted, borrowed from another grade, or transcribed from a reseller — MUST carry an entry saying so.",
  "$ref": "../../utils.json#/$defs/provenance"
}
```

Sites (all currently `additionalProperties: false`, so each needs the
explicit property):

- `schemas/magnetic/core/material.json` — **the priority**; every case in
  this RFC lives here.
- `schemas/magnetic/core/shape.json`, `schemas/magnetic/core.json`
- `schemas/magnetic/wire.json`, `schemas/magnetic/wire/material.json`,
  `schemas/magnetic/wire/coating.json`
- `schemas/magnetic/bobbin.json`, `schemas/insulation/material.json`

A record with a single honest source is one entry:

```json
"provenance": [
  { "source": "manufacturerDatasheet",
    "sourceName": "TDK N87 datasheet",
    "sourceUrl": "https://www.tdk-electronics.tdk.com/...",
    "retrievedDate": "2026-03-11" }
]
```

### 2. Define a MAS convention for `fields`: RFC 6901 JSON Pointers

PEAS types `fields` as `array of string` with no format constraint. MAS
adopts the convention that each entry is a **JSON Pointer relative to the
record root**. This costs **no schema change** — it is a documented
convention plus a description tightening — and it is what makes the type
usable at the granularity the real cases demand.

`AT&M 1K107` (ABT #703), three borrowed scalars:

```json
"provenance": [
  { "source": "manufacturerDatasheet",
    "sourceName": "AT&M nanocrystalline ribbon brochure (EN/CN)",
    "sourceUrl": "https://www.antai-emarketing.com/nanocrystalline-ribbon/",
    "retrievedDate": "2026-07-15",
    "fields": ["/saturation", "/coerciveForce", "/permeability"] },

  { "source": "derived",
    "derivation": "Class-typical FeCuNbSiB values; AT&M publishes no Curie temperature, density or resistivity for any grade in this range. Not measured, not vendor-stated. See ABT #703.",
    "retrievedDate": "2026-07-15",
    "fields": ["/curieTemperature", "/density", "/resistivity/0/value"] }
]
```

Nanoperm (ABT #706), a whole points-array:

```json
"provenance": [
  { "source": "derived",
    "derivation": "The 98 massLosses points are NOT measurements. They are Pv = pi^2*d^2*f^2*B^2/(6*rho), the classical thin-ribbon eddy-current law, evaluated from Magnetec's published rho = 115 uOhm.cm (implied d = 21.3 um, within the published 17-23 um). Identical across all seven Nanoperm grades (md5 f1a1339654d17afae310aa5031eb333d). The classical term omits hysteresis, so they lie 13% / 28% / 60% BELOW Magnetec's own published f^1.8 relation at 50 / 20 / 1 kHz. Do NOT fit a loss model to them; MKF serves this family through massLosses {\"method\":\"magnetec\"}. See ABT #706, #645.",
    "sourceUrl": "https://www.magnetec.de/storage/2023/12/AppNoteNanoperm.pdf",
    "fields": ["/massLosses"] }
]
```

DMR52 (ABT #640), an identifiability limit on a fitted model:

```json
{ "source": "derived",
  "derivation": "House Steinmetz refit (scripts/refit-steinmetz.py). Backing points lie on a DEGENERATE (f,B) locus - one flux density per frequency (1 MHz/50 mT, 3 MHz/30 mT, 4 MHz/20 mT, 5 MHz/20 mT) - so alpha and beta are identifiable only along a line. Read as 'valid over 1-5 MHz AT 20-50 mT', not over the (f,B) plane. See ABT #640.",
  "retrievedDate": "2026-08-11",
  "fields": ["/volumetricLosses/steinmetz/0/ranges/0"] }
```

Sincores/Halo Cosmos (ABT #632), mixed maker/reseller:

```json
"provenance": [
  { "source": "manufacturerDatasheet", "sourceName": "Sincores (maker) material table",
    "sourceUrl": "http://www.sincores.com/material.html", "retrievedDate": "2026-08-14",
    "fields": ["/permeability/initial", "/saturation", "/curieTemperature", "/density"] },
  { "source": "distributor", "sourceName": "Halo Cosmos (reseller) material table",
    "sourceUrl": "http://www.halocosmos.com/products/products-ferrite-core",
    "retrievedDate": "2026-08-06",
    "derivation": "Reseller-sourced; the maker does not list this grade, so no cross-check was possible.",
    "fields": ["/recommendations"] },
  { "source": "derived",
    "derivation": "Resistivity 1e6 ohm*m BORROWED from comparable NiZn records (B45, NB50S). Neither maker nor reseller publishes one. Inert while volumetricLosses is empty (MKF consumes resistivity only via Roshen). See ABT #575.",
    "fields": ["/resistivity/0/value"] }
]
```

### 3. The granularity question — and why this answer

This is the crux of the design, so state the options plainly.

| option | Nanoperm (98-point array) | 1K107 (3 scalars) | cost |
|---|---|---|---|
| **(a) Record-level trail + `fields` JSON Pointers** *(recommended)* | one entry, `fields: ["/massLosses"]` | one entry, three pointers | one optional property per record root; **additive** |
| (b) Per-field provenance objects | every scalar becomes `{value, provenance}` | same | **breaking everywhere**; changes the type of every field; MKF rewrite |
| (c) Per-points-array provenance | requires wrapping the bare array in `{provenance, data:[…]}` | does not help at all | **breaking**: the points-array branch of `volumetricLosses`/`massLosses` `anyOf` is a *bare array* with no object to hang a property on |
| (d) Tighten the existing free-form `origin` string to an enum | works for loss points only | does not help | breaking for the 27 588 `MagNet` points; leaves scalars, curves and models uncovered |

Option (c) deserves a second look because it is the intuitive answer for
the Nanoperm case, and it is worth being explicit about why it is
rejected: `massLosses` is `{ <shapeFamily>: [ magnetecMethodData | [massLossesPoint, …] ] }`.
The points variant is a bare JSON array. Giving it a provenance slot
means changing it to an object, which invalidates **every existing
record with a points array** (349 records in
`advanced_core_materials.ndjson`, 46 821 points) and every MKF call site
that iterates it. Option (a) reaches the same array with
`fields: ["/massLosses"]` at zero breakage.

Option (b) is the theoretically cleanest — provenance travelling with the
value it describes, immune to a field being copied out of context — and
the committee should hear the argument. It is also a 1.0.0-scale
rewrite of the entire schema and of MKF, for a benefit that (a) delivers
at ~5 % of the cost. Recommend (a) now; (b) remains available later for a
narrow set of fields if the pointer convention proves too fragile.

### 4. Do NOT add a MAS-local origin enum

The natural instinct is to invent a MAS enum
(`vendorPublished / computedFromVendorRelation / digitisedFromVendorChart /
houseFit / borrowedClassTypical / resellerSourced`). **This RFC recommends
against it**, per the org placement rule: a type shared across modules
belongs in PEAS, defined once and `$ref`-ed. Every one of those six
concepts maps onto PEAS `source` today:

| MAS situation | PEAS `source` | what carries the detail |
|---|---|---|
| read off a vendor datasheet | `manufacturerDatasheet` | `sourceUrl`, `retrievedDate` |
| vendor parametric table / online selector | `manufacturerParametric` | `sourceName` |
| computed from a vendor-published relation (Nanoperm) | `derived` | `derivation` — the formula and its inputs |
| digitised from vendor artwork (ACME) | `manufacturerDatasheet` | `derivation` documents the digitisation and its drawn extent |
| house Steinmetz fit (DMR52) | `derived` | `derivation` — fitter, backing points, identifiability limit |
| borrowed class-typical (1K107, Sincores rho) | `derived` | `derivation` names the donor records |
| reseller table (Halo Cosmos) | `distributor` | `sourceName` = the reseller |

The one gap worth arguing about: `derived` is doing a lot of work — it
covers "computed from a published law", "fitted from our own points" and
"copied from a sibling grade", which are epistemically different. That is
a real weakness, but the fix belongs in **PEAS** (a proposal to split
`derived`, or to add an optional `derivationKind`), raised through PEAS
governance, **not** a parallel MAS enum. Filed as open question 1.

Similarly, the existing per-point `origin` string is left **exactly as
is** by this RFC. Tightening it is a breaking change against 46 849
points for no benefit that record-level provenance does not already
provide, and MKF does not read it. Open question 4 asks whether it should
be deprecated at 1.0.0.

## Migration policy

- **0.3.0:** `provenance` is added as **optional** at every listed record
  root. Every document that validates today still validates. No field
  changes type; no field becomes required.
- **Never required by the schema.** This matches every other PSMA module
  (provenance appears in zero `required` arrays across all of them). A
  "provenance present" rule is a *data policy* — enforceable by the MAS
  data linter or by Blade Runner as a WARNING — not a schema constraint.
  Making it schema-required would instantly invalidate all 954 materials,
  18 942 cores, 1 581 shapes and 4 352 wires, which is not an acceptable
  cost for a field whose value is per-record editorial judgement.

### Backfill, costed honestly

MAS ships **954 core materials**, **349 advanced core materials** (all
954-set members, i.e. a richer overlay of the same names), **18 942
cores**, **1 581 shapes**, **4 352 wires**. Nobody is going to research
the provenance of 26 178 records, and this RFC does not ask anyone to.

Proposed tiers:

1. **The 97 records that already say it in prose** (`core_materials.ndjson`,
   caveat-keyword scan). These are the ones whose author already did the
   research. Converting the prose to a structured trail is mechanical for
   the *classification*; the `derivation` text can be lifted verbatim from
   `commercialName`. Estimate: a scripted first pass plus per-record
   review. **This is the only tier that must land with the RFC.**
2. **The records named in open tickets** — the 7 Nanoperm grades (#706),
   1K107 (#703), the 17 ACME A-family records (#314), the 46
   Sincores/Halo grades (#632/#575), the 6 degenerate-locus Steinmetz
   ranges and 11 CF `ct` clones (#640/#706). Roughly **90 records**,
   overlapping tier 1. Each already has a ticket with the finding written
   up; the trail is a transcription.
3. **Bulk one-line trails.** Records emitted by a known importer can get a
   single entry from the importer's own metadata (`source`,
   `sourceName`, `sourceUrl`, `retrievedDate`) at negligible cost — the
   27 588 `MagNet`-origin points are one such family. This is worth doing
   at the record level even though it says nothing per-field.
4. **Everything else: no provenance, which is the honest answer.** A
   record with no trail means "not yet documented" — the same status quo
   as today, but now visibly so, and now distinguishable from a record
   that has been checked. Absence is not a claim of measurement; but see
   open question 3, which asks whether the committee wants the opposite
   default at some future major version.

`commercialName` prose is **not** deleted by the backfill. Prose stays as
the human-readable narrative; the trail is the machine-readable index
into it. A follow-up cleanup can trim `commercialName` back toward its
documented purpose once the trails exist, but that is a separate change
and should not be bundled here.

## Consumer impact

**MKF.** Additive and inert on day one.
`MKF/MAS/MAS.hpp` already generates `class Provenance` (from
`magneticDatasheetInfo`), so adding the property to `CoreMaterial` yields
a `std::optional<std::vector<Provenance>> provenance` member and its
accessors — no existing signature changes, no call site breaks, nothing
in `CoreLosses.cpp` or the `MagneticFilter*` classes needs to read it.
Note the regeneration caveat: quicktype `MAS.hpp` regeneration is
currently broken (ABT #283), so the practical cost is whatever that
ticket costs, not the schema edit.

Once the field exists, the interesting MKF work is **optional and
deliberately out of scope here**: a filter or a warning that declines to
use a `derived` loss model outside its stated validity, or that surfaces
"this material's resistivity is borrowed" when the Roshen model is
selected. Worth its own ticket; not part of this RFC.

**Fitters and house scripts.** `scripts/refit-steinmetz.py` and the
digitisers become *producers* of provenance: a script that mints
coefficients should write the trail entry that describes its own fit,
including the identifiability caveat when the backing points are
degenerate. This is the change that stops the defect class recurring —
the six tickets above all describe values whose generator knew exactly
what it was doing and had nowhere to write it down.

**Validators.** `jsonschema` (Draft 2020-12) needs the PEAS `utils.json`
`$ref` to resolve, which it already does for `manufacturerInfo` and
`distributorInfo` on the same records. No new resolution surface. Any
host serving a stale `psma.com/peas/utils.json` must be synced to
canonical — a deploy, not a schema edit.

**WebFrontend / UI.** No change required. A material card *may* choose to
render a "derived" badge; nothing breaks if it does not.

## Alternatives considered

**A. Do nothing — keep prose in `commercialName`.**
Zero cost, and the prose that exists is high quality. Rejected because
the two most serious cases in this RFC (Nanoperm, 1K107) have an *empty*
`commercialName`: the convention protects only the records whose author
remembered it, which is the opposite of a data contract. It is also
unqueryable, unvalidatable, and it puts 5 KB of caveats in a field
documented as a name. Prose remains — it just stops being the only
mechanism.

**B. Remove every value that is not vendor-backed.**
The strictest reading of the no-fallbacks rule, and it has real force: a
loud missing-data error beats a plausible fake number, and MAS has
applied exactly this reasoning before (S4H's `volumetricLosses` is
deliberately empty so that a loss request *fails* rather than returning a
fabricated Pv). Applied here it would delete the 98 Nanoperm points,
1K107's three scalars, the 46 borrowed resistivities and the six
degenerate Steinmetz ranges.

Rejected as a blanket policy, for three reasons, but **not** rejected
case by case:
1. Several of these values are *good* — a digitised vendor chart is real
   vendor data; a house fit over honest points is the best available
   model. Deleting them loses information the corpus paid for.
2. Some are load-bearing but inert: 1K107's density and the borrowed
   `1e6 ohm*m` resistivity are schema-**required** fields
   (`core/material.json` requires `resistivity`), so deleting them means
   deleting the whole record, taking real published data (Bs, Hc, mu)
   with it.
3. Deletion and labelling are not exclusive. Labelling is the mechanism
   that lets the *consumer* apply the strict rule — an MKF filter can
   refuse to use a `derived` resistivity in Roshen and throw, which is
   precisely the loud error the rule asks for, while the value stays
   visible to a human who knows what it is.

The honest framing for the committee: **this RFC does not decide the
Nanoperm/1K107 disposition.** Those tickets stay open. It gives whoever
decides a way to record the decision. Where a value has *no* defensible
basis at all, delete it — that remains the right answer and this RFC does
not license keeping junk because it is now labelled junk.

**C. A MAS-local `origin`/`dataQuality` enum.**
Rejected on the placement rule: PEAS already defines this type, MAS
already `$ref`s it, and every sibling module uses it. Inventing a
parallel MAS enum duplicates a shared type and puts MAS out of step with
CAS/RAS/SAS/CIAS for no gain. Where PEAS's vocabulary is genuinely
short (the overloaded `derived`), the fix is a PEAS proposal.

**D. Tighten the existing per-point `origin` string to an enum.**
Cheap-looking, but breaking against 46 849 existing points, and it covers
only loss points — not scalars, not permeability curves, not fitted
coefficients, which is where four of the six cases live. Folded into open
question 4 as a possible 1.0.0 cleanup.

**E. A sidecar provenance file** (`data/provenance.ndjson`, keyed by
material name). Keeps the schema untouched entirely. Rejected: it splits
a record from its own metadata, it will drift, `name` is already
overloaded as the cross-file foreign key, and no consumer that loads a
single record would ever see it.

## Open questions

1. **Is PEAS's `source` vocabulary sufficient, or does `derived` need
   splitting?** `derived` currently covers "computed from a vendor's
   published law" (Nanoperm), "fitted from our own measured points"
   (DMR52) and "copied from a sibling grade" (1K107, Sincores rho).
   These are epistemically different and a consumer might reasonably want
   to accept one and reject another. If the committee agrees, the fix is
   a **PEAS** proposal — an optional `derivationKind`, or additional
   `source` values — raised with PEAS governance, since CAS/RAS/SAS/CIAS
   share the type. MAS should not fork it. *Unresolved: needs PEAS WG.*

2. **Should the `fields` JSON-Pointer convention be normative or
   advisory?** PEAS types `fields` as free strings and CAS uses plain
   field names (`"rippleCurrent"`). If MAS makes pointers normative, MAS
   trails become machine-resolvable but diverge stylistically from CAS.
   If advisory, they may rot. A third option — propose
   `"format": "json-pointer"` to PEAS — is the DRY answer but needs the
   same PEAS WG round as (1). *Recommendation: document as a MAS
   convention now, propose the PEAS format later.*

3. **What does absence of provenance mean?** This RFC says "not yet
   documented", which is honest but weak: it makes an unchecked record
   indistinguishable from a checked one that simply has one source. The
   alternative — absence means "vendor-published, unqualified" — is
   stronger but retroactively asserts something about 26 178 records
   nobody has audited, which is exactly the defect this RFC exists to
   fix. *Recommendation: "not yet documented" at 0.3.0; revisit for
   1.0.0 once tier-1/2 backfill lands.*

4. **What happens to the existing per-point `origin` string?** It is
   required, free-form, has three values in practice, is unread by MKF,
   and now overlaps record-level provenance. Deprecate at 1.0.0? Tighten
   to an enum? Leave it? *Unresolved.* Note that whatever is decided
   must handle `"MagNet"` (27 588 points), which is a *dataset* name, not
   a source kind — arguably `source: "librarianEnrichment"` +
   `sourceName: "MagNet"` in a record-level trail is where it belongs.

5. **Should `provenance` also go on `MAS.json` / `Mas.inputs` design
   records, or only on catalogue records?** This RFC scopes to catalogue
   records (materials, cores, shapes, wires, bobbins, insulation). A
   design's provenance is a different question and probably belongs with
   the `outputs` `resultOrigin` machinery. *Out of scope; flagged so the
   committee can say if it disagrees.*

6. **Who owns backfill tier 1, and against what deadline?** 97 records
   with existing prose is a bounded, one-person job, but it needs an
   owner and it should land close to the schema change or it will not
   land at all. *Unresolved: needs a volunteer and an ABT ticket.*

7. **Does `advanced_core_materials.ndjson` get the same treatment?** It
   holds 46 821 of the 46 849 origin-bearing points and all seven
   Nanoperm records, so on content grounds it clearly should.

   *Note on a non-blocker:* earlier drafts of this section, and several
   ABT tickets (#225, #242, #632, #640, #645, #222), describe this file
   as **unpushable behind a GitHub LFS budget cap**. That is **stale**.
   MAS's LFS has since been migrated to a self-hosted endpoint
   (`.lfsconfig` → `https://openmagnetics.com/lfs/openmagnetics/mas`,
   commit `626c871`, ABT #296; the write endpoint is the credentialed
   `/lfs-rw/` variant in local git config). Verified 2026-08-14 by
   pushing 578 MB across four new 137 MB objects of this very file with
   no budget error. Backfill here is a question of scale and review
   effort — 138 MB rewritten per pass — not of push capacity.
   *Resolved as a practical matter; the design question of whether the
   advanced file carries its own provenance or inherits the base
   record's remains open.*
