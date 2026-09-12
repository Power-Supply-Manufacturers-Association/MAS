#!/usr/bin/env python3
"""Enrich ``data/bobbins.ndjson`` with pin-row geometry from public vendor catalogues.

WHY THIS EXISTS
---------------
504 bobbin records: 342 declared ``pinout.numberPins`` and nothing else, 9 carried real
pitch/row geometry, none carried pin coordinates.  MKF cannot place a single pin from a
pin *count*, so every catalogue bobbin drew, exported and simulated with no pins at all
(ABT #1171 / WP2).

Two vendor catalogues publish the missing footprint numbers for the same standard core
sizes:

* Taiwan Shulin (``bobbin.com.tw``) - a server-rendered parametric table, 128 pages of 10
  rows: category, product type, segment, part no., material, H/V, sections, pin quantity,
  core size, row pitch, pin pitch, pin pitch II.  Row pitch is the FULL row-to-row
  distance; the site states a +/- 0.3 mm tolerance on the three pitch columns.
* CB-Magnetics (``cb-magnetics.com``) - a WooCommerce store REST endpoint whose product
  descriptions carry ``Pins: 8+8`` / ``Pin distance: 5.00mm`` / ``Row distance: 35.0mm``.

WHAT IS AND IS NOT WRITTEN
--------------------------
A bobbin footprint is an interchange dimension: parts from different moulders for the same
core size, pin count and mounting orientation have to drop into the same PCB pattern.  That
is the ONLY reason a Shulin row may speak for a Norwe record - and only when the sources
agree.  So a value is written when, and only when:

* the vendor rows matching (family, core size, orientation, pin count [, chambers]) collapse
  to ONE geometry - every matching row agrees within the vendors' own 0.3 mm tolerance.
  Any disagreement is ambiguity, and ambiguity is dropped, not averaged;
* the value is stated by the source.  ``numberPinsPerRow`` is written only where a source
  spells the split out (CB's ``8+8``); a pitch quoted as a slash list (``2.5/3.8/5.0``) is
  ambiguous about which gap sits where and is dropped whole; ``centralPitch`` and
  ``pinDescription`` (pin diameter/length) are published by neither source and are never
  invented.

``numberRows`` = 2 is the one inference: a single quoted row-to-row distance exists only for
a two-row footprint.  It is recorded as such below and nowhere else.

PROVENANCE
----------
``schemas/magnetic/bobbin.json`` is a closed schema with no ``provenance`` property (MAS
``utils.json`` defines one, ``magnetic.json`` uses it, bobbin.json does not), and schemas are
not this script's to change.  So the audit trail is this script plus its ``--report`` CSV:
re-running it reproduces every number from the live catalogues.  Records that had no
``manufacturerInfo`` at all AND matched exactly one vendor part get that vendor recorded
there; a record that already names a manufacturer keeps it - a corroborated interchange
dimension does not make the part somebody else's.

Usage:
    scripts/enrich-bobbin-pinouts.py --shulin shulin.csv --cbmag cbmag.csv \
        [--report matches.csv] [--dry-run]
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

MM = 1e-3
TOL_MM = 0.3          # the tolerance Shulin itself prints under its pitch columns
DATA = Path(__file__).resolve().parent.parent / "data" / "bobbins.ndjson"
SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "magnetic" / "bobbin.json"

# Vendor segment prefix -> MAS bobbin family.  EI and EE bobbins for one core size are the
# same former (the winding body sits on the E half either way), which is why both map to
# `e`.  EPC/EPX/ATQ/EQ/POT/UU have no MAS bobbin family and are deliberately absent.
FAMILY_OF = {
    "EE": "e", "EI": "e", "EF": "e", "EEL": "e", "EL": "e",
    "ETD": "etd", "ET": "etd",
    "ER": "er", "ERL": "er", "EER": "er",
    "EFD": "efd",
    "PQ": "pq",
    "RM": "rm",
    "EP": "ep",
    "EC": "ec",
    "PM": "pm",
}


def leading_size(text: str) -> float | None:
    """First dimension of a MAS shape name: 'E 42/21/15' -> 42, 'EE 12.6' -> 12.6."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def code_size(code: str) -> float | None:
    """Vendor size code -> core size. '5501' -> 55, '19X8' -> 19, '6.0' -> 6.0."""
    code = code.split("X")[0].split("x")[0]
    m = re.match(r"^(\d+(?:\.\d+)?)", code)
    if not m:
        return None
    value = m.group(1)
    if "." not in value and len(value) >= 4:
        return float(value[:2])
    return float(value)


def parse_pitch(text: str) -> float | None:
    """A single unambiguous pitch in mm, or None for '' and slash lists."""
    text = (text or "").strip()
    if not text or "/" in text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class Candidate:
    """One vendor row reduced to the numbers a pinout needs."""

    def __init__(self, source, part, family, size, orientation, pins, sections,
                 row_distance, pitch, pins_per_row):
        self.source = source
        self.part = part
        self.family = family
        self.size = size
        self.orientation = orientation
        self.pins = pins
        self.sections = sections
        self.row_distance = row_distance      # mm, full row-to-row
        self.pitch = pitch                    # mm, scalar or [row0, row1]
        self.pins_per_row = pins_per_row      # [n0, n1] or None

    @property
    def key(self):
        return (self.family, self.size, self.orientation, self.pins)

    def pitch_list(self):
        return self.pitch if isinstance(self.pitch, list) else [self.pitch, self.pitch]


def read_shulin(path: Path) -> list[Candidate]:
    out = []
    for row in csv.DictReader(path.open()):
        # The `segment` column carries the real series ("EI-16", "EEL-16", "SMD-EF-12.6");
        # `product_type` lumps several series into one label ("EE.EI.EL"), which is why the
        # segment is read first.  SMD series are skipped: they quote no H/V and their
        # gull-wing footprint is not the through-hole one these records describe.
        seg = (row["segment"] or row["product_type"] or "").strip().upper()
        if seg.startswith("SMD"):
            continue
        seg = re.split(r"[-\s.]", seg)[0]
        family = FAMILY_OF.get(seg)
        if not family:
            continue
        try:
            size = float(row["core_size"])
            pins = int(row["pin_qty"])
        except (TypeError, ValueError):
            continue
        orientation = {"H": "horizontal", "V": "vertical"}.get(row["type"].strip())
        if orientation is None:
            continue
        row_distance = parse_pitch(row["row_pitch"])
        p1, p2 = parse_pitch(row["pin_pitch"]), parse_pitch(row["pin_pitch2"])
        if p1 is None:
            pitch = None
        elif p2 is None or abs(p2 - p1) <= 1e-9:
            pitch = p1
        else:
            pitch = [p1, p2]
        try:
            sections = int(row["section"])
        except (TypeError, ValueError):
            sections = None
        out.append(Candidate("shulin", row["part_no"], family, size, orientation,
                             pins, sections, row_distance, pitch, None))
    return out


def read_cbmag(path: Path) -> list[Candidate]:
    out = []
    for row in csv.DictReader(path.open()):
        seg = (row["segment"] or "").strip().upper()
        family = FAMILY_OF.get(seg)
        if not family:
            continue
        size = code_size(row["size_code"] or "")
        if size is None:
            continue
        orientation = row["orientation"] or None
        if orientation is None:
            continue
        try:
            pins = int(row["pins"])
        except (TypeError, ValueError):
            continue
        row_distance = parse_pitch(row["row_distance"])
        p1, p2 = parse_pitch(row["pin_pitch1"]), parse_pitch(row["pin_pitch2"])
        if p1 is None:
            pitch = None
        elif p2 is None or abs(p2 - p1) <= 1e-9:
            pitch = p1
        else:
            pitch = [p1, p2]
        pins_per_row = None
        if row["pins_row1"] and row["pins_row2"]:
            pins_per_row = [int(row["pins_row1"]), int(row["pins_row2"])]
        try:
            sections = int(row["sections"])
        except (TypeError, ValueError):
            sections = None
        out.append(Candidate("cb-magnetics", row["name"], family, size, orientation,
                             pins, sections, row_distance, pitch, pins_per_row))
    return out


# The nine records that already carried full pitch/row geometry AND a pinDescription were
# also the only nine with no `orientation` - and MKF cannot place a pin without knowing which
# way it leaves the former, so all nine drew nothing.  Each manufacturer states it on its own
# datasheet, the one already referenced from the record's manufacturerInfo:
#
#   Miles-Platts pq0010..pq0080 part description "Bobbin PQ2016 V 14P 1S UL94V0" - the V
#   Swarm SW-59A product page title            "SW-59A ETD-59-H-24P"             - the H
#
# so this is the record's own manufacturer speaking, not a guess.  The quoted string is the
# evidence; re-reading the datasheet reproduces it.
ORIENTATION_FROM_OWN_DATASHEET = {
    "Bobbin PQ 20/16": ("vertical", "Miles-Platts pq0010: 'Bobbin PQ2016 V 14P 1S UL94V0'"),
    "Bobbin PQ 20/20": ("vertical", "Miles-Platts pq0020: 'Bobbin PQ2020 V 14P 1S UL94V0'"),
    "Bobbin PQ 26/20": ("vertical", "Miles-Platts pq0030: 'Bobbin PQ2620 V 12P 1S UL94V0'"),
    "Bobbin PQ 26/25": ("vertical", "Miles-Platts pq0040: 'Bobbin PQ2625 V 12P 1S UL94V0'"),
    "Bobbin PQ 32/20": ("vertical", "Miles-Platts pq0050: 'Bobbin PQ3220 V 12P 1S UL94V0'"),
    "Bobbin PQ 32/30": ("vertical", "Miles-Platts pq0060: 'Bobbin PQ3230 V 12P 1S UL94V0'"),
    "Bobbin PQ 35/35": ("vertical", "Miles-Platts pq0070: 'Bobbin PQ3535 V 12P 1S UL94V0'"),
    "Bobbin PQ 40/40": ("vertical", "Miles-Platts pq0080: 'Bobbin PQ4040 V 12P 1S UL94V0'"),
    "Bobbin ETD 59/31/22": ("horizontal", "Swarm product 1304: 'SW-59A ETD-59-H-24P'"),
}

NAME_PITCH = re.compile(r"(\d+(?:\.\d+)?)mm")


def stated_pitch(name: str) -> float | None:
    """The pin pitch the record's own catalogue name states, in mm, when it states one.

    393 of the 504 records are Norwe parts and 168 of their names carry the moulder's own
    pitch ("... 8-pin 3.81mm 2-chamber").  That number outranks any vendor row: it is this
    part's, not an interchangeable neighbour's.  A vendor row that contradicts it is a
    different footprint and is dropped rather than believed.
    """
    m = NAME_PITCH.search(name or "")
    return float(m.group(1)) if m else None


def chambers_of(functional: dict) -> int | None:
    variant = functional.get("variant") or ""
    m = re.match(r"^(\d+)-chamber", variant)
    return int(m.group(1)) if m else None


def agree(values: list[float]) -> float | None:
    """One number when every source agrees inside the vendors' tolerance, else None."""
    values = [v for v in values if v is not None]
    if not values:
        return None
    if max(values) - min(values) > TOL_MM:
        return None
    return round(sum(values) / len(values), 4)


def consolidate(cands: list[Candidate]):
    """Collapse the vendor rows for one key, or return None when they disagree."""
    row_distance = agree([c.row_distance for c in cands])
    per_row = [[], []]
    for c in cands:
        pitches = c.pitch_list()
        for i in (0, 1):
            per_row[i].append(pitches[i])
    pitch0, pitch1 = agree(per_row[0]), agree(per_row[1])
    if pitch0 is None or pitch1 is None:
        pitch = None
    elif abs(pitch0 - pitch1) <= 1e-9:
        pitch = pitch0
    else:
        pitch = [pitch0, pitch1]
    splits = {tuple(c.pins_per_row) for c in cands if c.pins_per_row}
    pins_per_row = list(splits.pop()) if len(splits) == 1 else None
    return row_distance, pitch, pins_per_row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shulin", type=Path, required=True)
    ap.add_argument("--cbmag", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cands = read_shulin(args.shulin) + read_cbmag(args.cbmag)
    by_key = collections.defaultdict(list)
    for c in cands:
        by_key[c.key].append(c)

    records = [json.loads(line) for line in args.data.open()]
    report = []
    stats = collections.Counter()
    per_family = collections.Counter()

    for record in records:
        functional = record["functionalDescription"]
        pinout = functional.get("pinout")
        if not pinout:
            stats["skipped: no pinout"] += 1
            continue
        stated = ORIENTATION_FROM_OWN_DATASHEET.get(record.get("name", ""))
        if stated and not functional.get("orientation"):
            functional["orientation"] = stated[0]
            stats["orientation read off the record's own datasheet"] += 1
        if "pitch" in pinout or "rowDistance" in pinout:
            stats["skipped: already has geometry"] += 1
            continue
        size = leading_size(functional["shape"])
        orientation = functional.get("orientation")
        if size is None or orientation is None:
            stats["skipped: no core size or orientation"] += 1
            continue
        key = (functional["family"], size, orientation, pinout["numberPins"])
        matches = by_key.get(key)
        if not matches:
            stats["unmatched: no vendor row for family/size/orientation/pins"] += 1
            continue
        chambers = chambers_of(functional)
        if chambers is not None:
            narrowed = [c for c in matches if c.sections == chambers]
            if narrowed:
                matches = narrowed
        named = stated_pitch(record.get("name", ""))
        if named is not None:
            matches = [c for c in matches
                       if any(p is not None and abs(p - named) <= TOL_MM
                              for p in c.pitch_list())]
            if not matches:
                stats["unmatched: every vendor row contradicts the pitch in the record's own name"] += 1
                continue
        row_distance, pitch, pins_per_row = consolidate(matches)
        if named is not None:
            pitch = named
        if row_distance is None or pitch is None:
            stats["unmatched: vendor rows disagree or quote no usable pitch"] += 1
            continue

        pinout["numberRows"] = 2
        if pins_per_row:
            pinout["numberPinsPerRow"] = pins_per_row
        pinout["rowDistance"] = round(row_distance * MM, 9)
        pinout["pitch"] = ([round(p * MM, 9) for p in pitch]
                           if isinstance(pitch, list) else round(pitch * MM, 9))
        # Stable key order inside pinout, so a diff of this file stays readable.
        order = ["numberPins", "numberRows", "numberPinsPerRow", "rowDistance",
                 "pitch", "centralPitch", "pinDescription"]
        functional["pinout"] = {k: pinout[k] for k in order if k in pinout}

        sources = sorted({c.source for c in matches})
        if not record.get("manufacturerInfo") and len(matches) == 1:
            only = matches[0]
            record["manufacturerInfo"] = {
                "name": ("Taiwan Shulin" if only.source == "shulin" else "CB-Magnetics"),
                "reference": only.part,
            }
            stats["manufacturer recorded"] += 1
        stats["enriched"] += 1
        per_family[functional["family"]] += 1
        report.append({
            "bobbin": record.get("name", ""),
            "family": functional["family"],
            "shape": functional["shape"],
            "orientation": orientation,
            "numberPins": pinout["numberPins"],
            "chambers": chambers if chambers is not None else "",
            "rowDistance_mm": row_distance,
            "pitch_mm": pitch,
            "numberPinsPerRow": pins_per_row or "",
            "sources": "|".join(sources),
            "vendor_parts": "|".join(sorted(c.part for c in matches)),
        })

    if not args.dry_run:
        with args.data.open("w") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    if args.report:
        with args.report.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, list(report[0]) if report else ["bobbin"])
            writer.writeheader()
            writer.writerows(report)

    print(f"records: {len(records)}")
    for key, value in stats.most_common():
        print(f"  {key}: {value}")
    print("enriched per family: " + ", ".join(f"{k}={v}" for k, v in sorted(per_family.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
