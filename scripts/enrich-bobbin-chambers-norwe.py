#!/usr/bin/env python3
"""Multi-chamber bobbins: ``numberChambers`` from the catalogue variant, chamber geometry
from Norwe's own drawings (MAS-RFC 0014 part A, ABT #1175).

WHAT IS WRITTEN
---------------
1. ``functionalDescription.numberChambers`` on every record whose ``variant`` names a chamber
   count ("2-chamber", "longer-creepage-2-chamber", "3-chamber", "2-chamber-s", ...). The count
   is the integer in front of "-chamber" and nothing else; a variant with no such token gets
   no field (absent means a plain two-flange former, which is what those records are).

2. The wall and chamber labels documented in ``docs/magnetic/coil.md`` - ``w1..w(N-1)`` wall
   thicknesses and ``c1..cN`` chamber widths, in column order - for the records in
   ``TRANSCRIPTIONS`` below, and only for those.

WHERE THE GEOMETRY COMES FROM
-----------------------------
Every record in ``TRANSCRIPTIONS`` links a Norwe catalogue sheet (manufacturerInfo.datasheetUrl)
whose side view dimensions, for the ``2k`` (two-chamber) type code printed on the same sheet:

* ``W``  the winding length between the two flange faces (e.g. "10" on EE 16, "32.8" on ETD 49),
* ``w``  the thickness of the centre wall (e.g. "0.6", "1"),
* and marks the two chambers with the drafting equality sign ("=" on each side of the wall),
  which states that the wall is centred and the two chambers are equal.

So the chamber width is ``c = (W - w) / 2``: two printed numbers and a printed equality, no
reading off the drawing's scale. The values were transcribed by a person from the rendered sheet;
this script does not trust the transcription blindly - with the sheet at hand it refuses to write
a record unless (a) the sheet's type lines carry a "/2k/" coilformer with the record's order code,
(b) both ``W`` and ``w`` are printed on the sheet as millimetre dimensions and (c) the sheet
carries the "=" sign. A record whose sheet is unreachable is not written.

WHAT IS NOT WRITTEN
-------------------
* ``height`` of the wall. Norwe does not dimension it; every transcribed sheet draws the wall
  (hidden line) out to the flange outline, which is what the absent value means in RFC 0014
  ("absent means it reaches as far as the flanges"). A sheet that drew a shorter wall would need
  a height label, and none is transcribed here.
* a crossing slot. No transcribed sheet dimensions one.
* the 104 chambered records whose drawing is no longer online (404 on 2026-09-13), and
  ``Norwe 94803-181`` (EFD 20, variant "3-chamber"): its type code reads "1-3ks" and the side view
  draws three hidden walls with "4x2.9" chambers, which does not state an unambiguous 3-chamber
  geometry. Those records keep ``numberChambers`` only, and MKF refuses to split their window.

Usage:
    scripts/enrich-bobbin-chambers-norwe.py --pdf-dir DIR [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "bobbins.ndjson"
MM = 1e-3

# order code -> (winding length between flanges W, wall thickness w), both in mm, as printed.
TRANSCRIPTIONS = {
    "90596-186": (18.0, 1.0),    # ETD 24/lr/2k/h12
    "90565-186": (32.8, 1.0),    # ETD 49/lr/2k/h20
    "92062-024": (10.0, 1.0),    # EE 16/2k/5-6/3.75-c(12.5)/p6g
    "92062-243": (10.0, 1.0),    # EE 16/2k/5-6/3.75-c(12.5)/Zen.6130L,sw
    "09864-106": (10.0, 0.6),    # EE 16/2k/K9/7-6/2.5-eh
    "09874-106": (10.0, 0.6),    # EE 16/2k/11/7-6/3.81-d(20.32)
    "09876-106": (10.0, 0.6),    # EE 16/2k/9-6/3.81-d(8.89)
    "09886-106": (10.0, 0.6),    # EE 16/2k/K9/9-6/3.75-cd
    "09896-106": (10.0, 0.6),    # EE 16/2k/K10/9-6/3.81-d(12.7)
    "09991-106": (12.5, 0.6),    # EE 20/2k/K11/7-8/3.81-e(20.32)
    "10166-106": (15.6, 0.7),    # EE 25/2k/K12/7-8/5.08-ik
    "90832-186": (8.8, 1.0),     # PQ 32-20/2k/-8/lm
    "90833-186": (18.6, 1.0),    # PQ 32-30/2k/-8/lm
}

CHAMBERS = re.compile(r"(?:^|-)(\d+)-chamber(?:-|$)")


def chamber_count(variant: str | None) -> int | None:
    if not variant:
        return None
    match = CHAMBERS.search(variant)
    return int(match.group(1)) if match else None


def sheet_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                          capture_output=True, text=True).stdout


def verify(record: dict, pdf_dir: Path) -> str | None:
    """None when the record's own sheet supports its transcription, else the reason."""
    reference = record["manufacturerInfo"]["reference"]
    url = record["manufacturerInfo"].get("datasheetUrl")
    if not url:
        return "no datasheetUrl"
    pdf = pdf_dir / url.rsplit("/", 1)[1]
    if not pdf.exists():
        return f"sheet {pdf.name} not in --pdf-dir"
    text = sheet_text(pdf)
    lines = [re.sub(r"\s+", " ", line) for line in text.splitlines() if "Coilformer:" in line]
    code = reference.replace("-", r"-\s*")
    if not any(re.search(r"/2k/", line) and re.search(code, line) for line in lines):
        return f"the sheet has no '/2k/' coilformer line for {reference}"
    printed = {float(m) for m in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])", text)}
    winding_length, wall = TRANSCRIPTIONS[reference]
    for label, value in (("winding length", winding_length), ("wall thickness", wall)):
        if value not in printed:
            return f"{label} {value} mm is not printed on the sheet"
    if "=" not in text:
        return "the sheet carries no '=' equal-chamber mark"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf-dir", type=Path, required=True,
                        help="directory holding the Norwe sheets under their URL basename")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]
    counts: dict[int, int] = {}
    written, refused = [], []
    for record in records:
        functional = record["functionalDescription"]
        number = chamber_count(functional.get("variant"))
        if number is None:
            continue
        counts[number] = counts.get(number, 0) + 1
        functional["numberChambers"] = number

        reference = (record.get("manufacturerInfo") or {}).get("reference")
        if reference not in TRANSCRIPTIONS:
            continue
        if number != 2:
            refused.append((record["name"], f"transcription is two-chamber, record says {number}"))
            continue
        reason = verify(record, args.pdf_dir)
        if reason:
            refused.append((record["name"], reason))
            continue
        winding_length, wall = TRANSCRIPTIONS[reference]
        chamber = (winding_length - wall) / 2
        dimensions = functional["dimensions"]
        for key in ("w1", "c1", "c2"):
            if key in dimensions:
                refused.append((record["name"], f"already carries '{key}'"))
                break
        else:
            dimensions["w1"] = {"nominal": round(wall * MM, 9)}
            dimensions["c1"] = {"nominal": round(chamber * MM, 9)}
            dimensions["c2"] = {"nominal": round(chamber * MM, 9)}
            written.append(record["name"])

    print("numberChambers:", ", ".join(f"{n} chambers x {c}" for n, c in sorted(counts.items())),
          f"({sum(counts.values())} records)")
    print(f"chamber geometry written for {len(written)} records:")
    for name in written:
        print("  +", name)
    for name, reason in refused:
        print("  -", name, "->", reason)
    if refused:
        return 1
    if not args.dry_run:
        DATA.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
