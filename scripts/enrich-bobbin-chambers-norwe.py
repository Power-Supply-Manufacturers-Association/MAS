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
* ``Norwe 94803-181`` (EFD 20, variant "3-chamber"): its type code reads "1-3ks" and the side view
  draws three hidden walls with "4x2.9" chambers, which does not state an unambiguous 3-chamber
  geometry; and the other 11 three-chamber records (this script transcribes two-chamber sheets).
* the chambered records whose sheet does not state W, w and the equality unambiguously
  (ABT #1246 re-read, every Norwe link reachable): the ten RM "45-degree ... 2-chamber" formers
  (the centred label is 0.3 mm on RM 4..12 but 0.8 mm on RM 14 beside a 0.3 mm step, so which
  line is the wall is not stated); EE 25 solder-tags 10112-024 (its sheet overlays the 2k and 3k
  walls in one view); EE 20 N0105-106 (the sheet draws the one-chamber part, no equality mark);
  EP 7 90083-087 (no equality mark, no identifiable winding length); EE 20 09931-024 and M 20
  N0115-106 (no wall thickness printed); the "2-chamber-s" 09742-106 and 10751-024 (type code
  "/2ks/", a different former than "/2k/"); ETD 59 N0013-186 (its sheet's text layer is
  scrambled, so the "/2k/" line cannot be confirmed). Those records keep ``numberChambers``
  only, and MKF refuses to split their window.

On the vertical EE/M and the PQ sheets the equality marks and W are drawn rotated beside the
winding space; on ETD and vertical sheets W is the inner of the two flange-spanning dimensions,
not the overall one the marks happen to sit under.

Usage:
    scripts/enrich-bobbin-chambers-norwe.py --pdf-dir DIR [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
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
    # ABT #1246
    "00221-024": (10.8, 0.7),
    "00223-024": (10.8, 0.7),
    "N0100-106": (5.7, 0.5),
    "09741-106": (7.1, 0.6),
    "09751-047": (7.3, 0.55),
    "09771-106": (7.5, 0.6),
    "09824-106": (10.0, 0.6),
    "09851-024": (9.9, 0.6),
    "09868-106": (10.0, 0.6),
    "09921-024": (12.3, 0.6),
    "09951-024": (12.4, 0.6),
    "09971-024": (11.8, 0.6),
    "09977-106": (11.8, 0.6),
    "09979-024": (11.8, 0.6),
    "09986-106": (12.5, 0.6),
    "10046-017": (12.4, 0.6),
    "10051-106": (12.4, 0.6),
    "10056-106": (12.4, 0.6),
    "10173-024": (15.5, 0.8),
    "10176-106": (15.6, 0.7),
    "10186-024": (15.6, 0.6),
    "10221-024": (15.5, 0.8),
    "10227-024": (15.5, 0.7),
    "10568-106": (20.1, 0.9),
    "10752-024": (20.3, 1.0),
    "92038-024": (12.4, 0.6),
    "92183-106": (7.3, 0.6),
    "N0098-106": (7.5, 0.6),
    "N0102-106": (10.0, 0.6),
    "N0104-106": (12.5, 0.6),
    "N0137-106": (7.5, 0.6),
    "N0139-106": (7.5, 0.6),
    "N0241-024": (10.8, 1.0),
    "90597-186": (19.0, 1.0),
    "90598-186": (19.0, 1.0),
    "90599-186": (21.0, 1.0),
    "90600-186": (25.8, 1.0),
    "90601-186": (29.6, 1.0),
    "N0002-186": (16.4, 1.0),
    "N0006-186": (19.0, 1.0),
    "N0011-186": (37.0, 1.0),
    "90063-087": (7.6, 1.0),
    "N0200-087": (9.4, 1.0),
    "90068-087": (9.4, 1.0),
    "90085-087": (5.8, 1.0),
    "N0201-087": (12.3, 1.1),
    "90087-087": (12.3, 1.1),
    "00161-024": (10.9, 0.7),
    "00631-106": (17.5, 0.8),
    "N0116-106": (17.4, 0.8),
    "01421-024": (25.9, 1.0),
    "09786-106": (7.5, 0.6),
    "09841-024": (9.9, 0.5),
    "09848-106": (10.0, 0.6),
    "09947-106": (12.5, 0.6),
    "09988-106": (12.5, 0.6),
    "N0199-106": (12.5, 0.6),
    "10162-024": (15.5, 0.8),
    "10341-106": (15.5, 1.5),
    "92246-106": (10.0, 0.5),
    "N0176-106": (7.5, 0.6),
    "N0197-106": (12.5, 0.6),
    "N0203-106": (15.5, 0.8),
    "N0501-186": (8.0, 0.8),
    "N0502-186": (8.0, 0.8),
    "N0503-186": (12.0, 1.0),
    "N0504-186": (12.0, 1.0),
    "N0505-186": (9.0, 1.0),
    "N0506-186": (13.9, 1.0),
    "N0508-186": (12.5, 1.0),
    "N0509-186": (22.3, 1.0),
    "N0510-186": (26.8, 1.0),
    "N0511-186": (23.6, 1.1),
    "N0512-186": (32.8, 1.1),
    "N0513-186": (32.8, 1.1),
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
    parser.add_argument("--report", type=Path, help="CSV: every chambered record, what was done and why")
    args = parser.parse_args()

    records = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]
    counts: dict[int, int] = {}
    written, refused, unchanged, report = [], [], [], []
    for record in records:
        functional = record["functionalDescription"]
        number = chamber_count(functional.get("variant"))
        if number is None:
            continue
        counts[number] = counts.get(number, 0) + 1
        functional["numberChambers"] = number

        reference = (record.get("manufacturerInfo") or {}).get("reference")
        row = {"bobbin": record["name"], "numberChambers": number,
               "datasheetUrl": (record.get("manufacturerInfo") or {}).get("datasheetUrl", "")}
        report.append(row)
        if reference not in TRANSCRIPTIONS:
            row["status"] = "numberChambers only: no transcription (see WHAT IS NOT WRITTEN)"
            continue
        row["W_mm"], row["w_mm"] = TRANSCRIPTIONS[reference]
        row["c_mm"] = round((row["W_mm"] - row["w_mm"]) / 2, 6)
        if number != 2:
            refused.append((record["name"], f"transcription is two-chamber, record says {number}"))
            row["status"] = "refused: " + refused[-1][1]
            continue
        reason = verify(record, args.pdf_dir)
        if reason:
            refused.append((record["name"], reason))
            row["status"] = "refused: " + reason
            continue
        winding_length, wall = TRANSCRIPTIONS[reference]
        chamber = (winding_length - wall) / 2
        dimensions = functional["dimensions"]
        wanted = {"w1": round(wall * MM, 9), "c1": round(chamber * MM, 9), "c2": round(chamber * MM, 9)}
        present = {key: dimensions[key] for key in wanted if key in dimensions}
        if present == {key: {"nominal": value} for key, value in wanted.items()}:
            unchanged.append(record["name"])       # an earlier run wrote exactly this
            row["status"] = "already carries exactly this geometry"
            continue
        for key in ("w1", "c1", "c2"):
            if key in dimensions:
                refused.append((record["name"], f"already carries a different '{key}'"))
                row["status"] = "refused: " + refused[-1][1]
                break
        else:
            dimensions["w1"] = {"nominal": round(wall * MM, 9)}
            dimensions["c1"] = {"nominal": round(chamber * MM, 9)}
            dimensions["c2"] = {"nominal": round(chamber * MM, 9)}
            written.append(record["name"])
            row["status"] = "written"

    print("numberChambers:", ", ".join(f"{n} chambers x {c}" for n, c in sorted(counts.items())),
          f"({sum(counts.values())} records)")
    print(f"chamber geometry written for {len(written)} records:")
    for name in written:
        print("  +", name)
    print(f"already carrying exactly this geometry: {len(unchanged)} records")
    for name, reason in refused:
        print("  -", name, "->", reason)
    if args.report:
        with args.report.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, ["bobbin", "numberChambers", "status", "W_mm", "w_mm",
                                             "c_mm", "datasheetUrl"])
            writer.writeheader()
            writer.writerows(sorted(report, key=lambda r: (r["status"], r["bobbin"])))
    if refused:
        return 1
    if not args.dry_run:
        DATA.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
