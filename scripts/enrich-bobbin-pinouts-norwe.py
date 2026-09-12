#!/usr/bin/env python3
"""Enrich ``data/bobbins.ndjson`` pin geometry from Norwe's OWN dimensioned drawings.

WHY THIS EXISTS
---------------
The interchange pass (``scripts/enrich-bobbin-pinouts.py``, ABT #1171) could speak for a
Norwe record only where two other moulders' parametric tables agreed on the same standard
footprint; 255 of the 393 Norwe records were left with a pin COUNT and nothing else.  Those
records already carry the first-party evidence in ``manufacturerInfo.datasheetUrl``: a Norwe
catalogue sheet at ``norwe.eu/katalogbilder/*.pdf``, which draws the part's own pin field.

WHAT THE SHEET ACTUALLY STATES
------------------------------
Every sheet carries a "Grid / View pin-side" panel: the pin field seen from the solder side,
drawn as filled dots on a ruled grid whose pitch the panel dimensions (2.54 mm, 2.5 mm, ...).
That panel is a measurement, not a table lookup - so the numbers below are read off the one
drawing that belongs to the record being written, and nothing is carried across parts.

Both readings are geometric and are taken from the PDF's vector content, never from a
rendered image or from OCR:

* the dot centres give the pin field: how many parallel rows, how many pins in each, and the
  spacings along and across the rows, exactly, in points;
* the scale comes from the panel's own dimension.  Where the panel is ruled, one grid step is
  the unit and every dot must sit on a whole number of steps - a dot that does not is a
  reading this script refuses to make.  Where it is not ruled, the panel's single dimension
  fixes the scale only if, at that scale, EVERY measured distance lands within 1 % of a
  dimension printed elsewhere on the same sheet; anything less is ambiguity, and ambiguity is
  refused rather than rounded into place.

WHAT IS NOT WRITTEN
-------------------
* ``pinDescription`` - Norwe identifies a pin by a type code ("Solder-pin: z112/ua"), not by
  a diameter or a length, so the sheet does not state one and this script never invents one.
* anything at all when the dot count disagrees with the record's ``numberPins``, when the
  sheet draws more than two rows (several footprint variants share one sheet), when the pin
  gaps in a row are irregular in a way ``pitch``/``centralPitch`` cannot express, or when the
  drawing is unreachable.  Every refusal is one row of the report CSV with its reason.
* any change to a record that already carries geometry.  Where such a record's own Norwe
  drawing disagrees with what is stored, the record is left exactly as it is and the
  disagreement is reported as a conflict for a human to settle - this script does not get to
  overrule an earlier source on its own.

``rowDistance`` is written as the FULL row-to-row distance, which is what the 78 records of
ABT #1171 already hold and what MKF consumes (it places the rows at +/- rowDistance/2).

Usage:
    scripts/enrich-bobbin-pinouts-norwe.py --cache ~/.cache/norwe-sheets \\
        [--pdf-dir DIR] [--report norwe_pinouts.csv] [--dry-run] [--offline]
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pdfplumber

MM = 1e-3
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "bobbins.ndjson"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/151.0.0.0 Safari/537.36")
DELAY = 0.5                      # <= 2 requests a second, as a guest on somebody's server
INCH = 25.4
REL = 0.01                       # 1 % - the agreement a corroborating dimension must reach


# --------------------------------------------------------------------------- extraction

def _tokens(page):
    """Numeric/word tokens with their size, reading rotated dimension text correctly.

    pdfplumber's word grouping scrambles the sheet's rotated dimensions ("20.32" comes back
    as '02', '.', '23'), so the characters are regrouped by hand: upright text reads left to
    right along a line, rotated text reads bottom to top up a column.
    """
    out = []
    for upright in (True, False):
        chars = [c for c in page.chars if bool(c["upright"]) is upright]
        if upright:
            chars.sort(key=lambda c: (round(c["top"], 1), c["x0"]))
        else:
            chars.sort(key=lambda c: (round(c["x0"], 1), -c["top"]))
        run = []
        for c in chars:
            if run:
                prev = run[-1]
                gap = (abs(c["top"] - prev["top"]) > 0.6 or c["x0"] - prev["x1"] > 0.8
                       or c["x0"] < prev["x0"] - 0.1
                       if upright else
                       abs(c["x0"] - prev["x0"]) > 0.6 or prev["top"] - c["bottom"] > 0.8
                       or c["top"] > prev["top"] + 0.1)
                if gap:
                    out.append(run)
                    run = []
            run.append(c)
        if run:
            out.append(run)
    tokens = []
    for run in out:
        text = "".join(c["text"] for c in run)
        tokens.append({
            "t": text,
            "size": round(max(c["size"] for c in run), 2),
            "x0": round(min(c["x0"] for c in run), 2),
            "x1": round(max(c["x1"] for c in run), 2),
            "top": round(min(c["top"] for c in run), 2),
            "bottom": round(max(c["bottom"] for c in run), 2),
            "up": run[0]["upright"],
        })
    return tokens


def _modal_step(values, minimum=0.6):
    """The spacing that most of a set of parallel rulings share."""
    values = sorted(values)
    gaps = [round(b - a, 3) for a, b in zip(values, values[1:]) if b - a > minimum]
    if not gaps:
        return None, 0
    best = []
    for x in gaps:
        group = [y for y in gaps if abs(y - x) <= max(0.08, 0.02 * x)]
        if len(group) > len(best):
            best = group
    return round(statistics.median(best), 4), len(best)


def extract(data: bytes) -> dict:
    """One catalogue sheet -> the few hundred bytes of it that state a pin field."""
    feat = {"pages": 0, "typeLines": [], "printed": [], "grid": None, "note": ""}
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        feat["pages"] = len(pdf.pages)
        page = pdf.pages[0]
        text = page.extract_text(layout=True) or ""
        feat["typeLines"] = [re.sub(r"\s+", " ", line.strip()) for line in text.splitlines()
                             if re.search(r"Coilformer:|Solder-pin:|Solder-tag:", line)]
        tokens = _tokens(page)
        # Every dimension is printed in mm at ~7 pt with its inch value beneath at ~5 pt;
        # keeping only the larger size drops the inch column, which would otherwise
        # corroborate a millimetre reading with an inch number.
        printed = set()
        for tk in tokens:
            for m in re.findall(r"\d+\.\d+", tk["t"]):
                if tk["size"] >= 6.0 and 0.3 <= float(m) <= 300:
                    printed.add(float(m))
        feat["printed"] = sorted(printed)

        heading = [tk for tk in tokens if tk["t"] == "Grid" and tk["up"]
                   and tk["size"] >= 9 and tk["x0"] > 250]
        if not heading:
            feat["note"] = "the sheet has no 'Grid / View pin-side' panel"
            return feat
        head = min(heading, key=lambda tk: tk["top"])
        x0, x1 = head["x0"] - 45, page.width - 20
        y0, y1 = head["top"], head["top"] + 195

        def inside(o):
            return x0 <= o["x0"] and o["x1"] <= x1 and y0 <= o["top"] and o["bottom"] <= y1

        dots = {}
        for c in page.curves:
            if not inside(c):
                continue
            w, h = c["x1"] - c["x0"], c["bottom"] - c["top"]
            if 1.0 < w < 5.0 and abs(w - h) < 0.6:
                # the same dot is often stroked twice; one position is one pin
                key = (round((c["x0"] + c["x1"]) / 2, 1), round((c["top"] + c["bottom"]) / 2, 1))
                dots[key] = [key[0], key[1]]
        rulings = [o for o in page.lines if inside(o)]
        vx = sorted({round(o["x0"], 2) for o in rulings if abs(o["x0"] - o["x1"]) < 0.15})
        hy = sorted({round(o["top"], 2) for o in rulings if abs(o["top"] - o["bottom"]) < 0.15})
        step_x, n_x = _modal_step(vx)
        step_y, n_y = _modal_step(hy)

        # A panel dimension is a millimetre number that has its own inch value printed under
        # it; a bare integer at the same size is a pin NUMBER ("1", "10") and is not a length.
        labels = []
        for tk in tokens:
            if not (tk["up"] and x0 <= tk["x0"] and tk["x1"] <= x1
                    and y0 <= tk["top"] and tk["bottom"] <= y1):
                continue
            if not re.fullmatch(r"\d+\.\d+", tk["t"]) or tk["size"] < 6.0:
                continue
            value = float(tk["t"])
            for other in tokens:
                if other is tk or other["size"] >= 6.0 or not other["up"]:
                    continue
                if (abs(other["x0"] - tk["x0"]) < 6
                        and 0 <= other["top"] - tk["bottom"] < 12
                        and re.fullmatch(r"\d+\.\d+", other["t"])
                        and abs(float(other["t"]) - value / INCH) <= 0.002 + 0.01 * value / INCH):
                    labels.append({"mm": value, "x": tk["x0"], "y": tk["top"]})
                    break
        feat["grid"] = {"dots": sorted(dots.values()), "stepX": step_x, "nX": n_x,
                        "stepY": step_y, "nY": n_y, "labels": labels}
    return feat


# ------------------------------------------------------------------------ interpretation

def _cluster(values, tol):
    values = sorted(values)
    groups = [[values[0]]]
    for v in values[1:]:
        if v - groups[-1][-1] > tol:
            groups.append([])
        groups[-1].append(v)
    return [statistics.mean(g) for g in groups]


def _near(value, printed, rel=REL):
    return any(abs(value - p) <= rel * max(value, 1.0) for p in printed)


def _snap(value, printed, rel=REL):
    hits = [p for p in printed if abs(value - p) <= rel * max(value, 1.0)]
    return min(hits, key=lambda p: abs(p - value)) if hits else None


def read_pin_field(feat: dict):
    """(geometry, None) when the panel states one unambiguously, else (None, reason)."""
    grid = feat.get("grid")
    if not grid:
        return None, feat.get("note") or feat.get("error") or "no pin-side panel"
    dots = grid["dots"]
    if len(dots) < 2:
        return None, f"the pin-side panel draws {len(dots)} pin dots"
    labels = sorted({round(l["mm"], 4) for l in grid["labels"]})
    if not labels:
        return None, "the pin-side panel dimensions nothing"

    # The grid rulings give the scale where the panel is ruled.  Norwe rules the pin field
    # in one or both directions; the better-supported direction is the step, and every dot
    # then has to sit on a whole number of those steps in BOTH directions, which is the check
    # that catches a step read off the wrong set of lines.
    axes = [(grid["stepX"], grid["nX"]), (grid["stepY"], grid["nY"])]
    axes = [(s, n) for s, n in axes if s and n >= 4]
    unit = min(labels)
    step = max(axes, key=lambda a: a[1])[0] if axes and unit <= 6.0 else None
    quantum = unit if step else None
    how = f"ruled grid, {unit} mm per step" if step else None
    scale = unit / step if step else None

    tol_pt = 0.30 * (step if step else 3.0)
    xs = _cluster([d[0] for d in dots], tol_pt)
    ys = _cluster([d[1] for d in dots], tol_pt)
    if len(xs) == len(ys) and len(xs) != 1:
        return None, f"the pin field is {len(xs)}x{len(ys)}; which axis is a row is ambiguous"
    axis, other = (0, 1) if len(xs) < len(ys) else (1, 0)
    rowpos = xs if axis == 0 else ys
    if len(rowpos) > 2:
        return None, (f"the panel draws {len(rowpos)} rows of pins - several footprint "
                      "variants share this sheet")
    rows = []
    for rp in rowpos:
        along = sorted(d[other] for d in dots if abs(d[axis] - rp) <= tol_pt)
        rows.append(_cluster(along, tol_pt))
    if sum(len(r) for r in rows) != len(dots):
        return None, "two pin dots share one position in the panel"

    measured = []                                             # every distance the panel shows
    if len(rowpos) == 2:
        measured.append(("rowDistance", abs(rowpos[1] - rowpos[0])))
    for i, r in enumerate(rows):
        for a, b in zip(r, r[1:]):
            measured.append((f"gap{i}", b - a))
    if not any(k.startswith("gap") for k, _ in measured):
        return None, "no row holds two pins, so the panel states no pitch"

    if scale is None:
        # Unruled panel: its one dimension fixes the scale only if every other distance the
        # panel shows then lands on a dimension printed elsewhere on the same sheet.
        printed = feat.get("printed") or []
        # Distances that differ by a rounding wobble are one distance; the drawing is not
        # drawn to the tenth of a point.
        distinct = _cluster(sorted(d for _, d in measured), 0.25)
        best = []
        for label in labels:
            for d in distinct:
                k = label / d
                if not (0.05 < k < 5):
                    continue
                if all(_near(x * k, printed, 0.015) for x in distinct):
                    best.append(k)
        best = [k for i, k in enumerate(best) if all(abs(k - j) > REL * k for j in best[:i])]
        if len(best) != 1:
            return None, ("the pin-side panel is not ruled and its dimensions do not fix a "
                          "scale the rest of the sheet confirms")
        scale = best[0]
        how = "unruled panel, scale from its own dimension, every distance printed on the sheet"

    def to_mm(dpt, name):
        raw = dpt * scale
        if quantum is not None:
            k = raw / quantum
            if abs(k - round(k)) > 0.12 or round(k) < 1:
                return None, f"{name} is not a whole number of grid steps"
            return round(round(k) * quantum, 6), None
        snapped = _snap(raw, feat.get("printed") or [], 0.015)
        if snapped is None:
            return None, f"{name} matches no dimension printed on the sheet"
        return round(snapped, 6), None

    values = {}
    for name, dpt in measured:
        mm, why = to_mm(dpt, name)
        if mm is None:
            return None, why
        values.setdefault(name, []).append(mm)

    out = {"numberPins": len(dots), "numberRows": len(rowpos),
           "numberPinsPerRow": [len(r) for r in rows]}
    if "rowDistance" in values:
        out["rowDistance"] = values["rowDistance"][0]
    pitches, centrals = [], []
    for i, r in enumerate(rows):
        gaps = values.get(f"gap{i}", [])
        if not gaps:
            pitches.append(None)
            continue
        distinct = sorted(set(gaps))
        if len(distinct) == 1:
            pitches.append(distinct[0])
        elif len(distinct) == 2 and len(gaps) % 2 == 1:
            mid = len(gaps) // 2
            rest = gaps[:mid] + gaps[mid + 1:]
            if len(set(rest)) == 1 and gaps[mid] != rest[0]:
                pitches.append(rest[0])
                centrals.append(gaps[mid])
            else:
                return None, f"the pin gaps along a row are irregular ({gaps})"
        else:
            return None, f"the pin gaps along a row are irregular ({gaps})"
    if None in pitches and len(pitches) > 1:
        return None, "one row holds a single pin, so its pitch is unstated"
    if len({p for p in pitches if p is not None}) == 1:
        out["pitch"] = next(p for p in pitches if p is not None)
    else:
        out["pitch"] = pitches
    if centrals:
        if len(set(centrals)) > 1:
            return None, "the two rows are drawn with different central pitches"
        if len(centrals) != len([r for r in rows if len(r) > 2]):
            return None, "only one of the two rows is drawn with a central gap"
        out["centralPitch"] = centrals[0]
    out["_how"] = how
    return out, None


TYPE_LINE = re.compile(r"Coilformer:\s*(.+)")


def type_code(feat):
    for line in feat.get("typeLines", []):
        m = TYPE_LINE.match(line)
        if m:
            return m.group(1)
    return None


def stated_orientation(code):
    """Norwe's own type code: 'ETD 19/v10/-1/SKYT.5220FR' is vertical with 10 pins."""
    m = re.search(r"/([vh])(\d+)(?:/|\b)", code or "")
    return ({"v": "vertical", "h": "horizontal"}[m.group(1)], int(m.group(2))) if m else (None, None)


CODE_PITCH = re.compile(r"/(\d{1,2}[.,]\d{1,2})(?=[/\s-])")


def stated_pitch(code):
    """The pin pitch Norwe's own type code on this sheet states, when it states one.

    The code names the footprint after the core size: 'EE 16/1k/5-8/3.75-c(12.5)/p6g' and
    'EFD 20/1k/8-8/2.5/A3X2G10' both quote the pitch as their own segment.  It is the same
    sheet talking, so a drawing read that contradicts it is a read to throw away.
    """
    m = CODE_PITCH.search(code or "")
    return float(m.group(1).replace(",", ".")) if m else None


def stated_chambers(code):
    m = re.search(r"/(\d+)k(?:/|\b)", code or "")
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------------------- fetching

def sheet(url: str, cache: Path, pdf_dir: Path | None, offline: bool):
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    cached = cache / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    data = None
    if pdf_dir is not None and (pdf_dir / f"{key}.pdf").exists():
        data = (pdf_dir / f"{key}.pdf").read_bytes()
    elif offline:
        return {"error": "not fetched (offline)"}
    else:
        request = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/pdf,*/*"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            feat = {"error": f"the datasheet URL answers HTTP {exc.code}"}
            cached.write_text(json.dumps(feat))
            time.sleep(DELAY)
            return feat
        except Exception as exc:                                        # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
        time.sleep(DELAY)
    if not data[:4] == b"%PDF":
        feat = {"error": "the datasheet URL does not answer with a PDF"}
    else:
        try:
            feat = extract(data)
        except Exception as exc:                                        # noqa: BLE001
            feat = {"error": f"the PDF cannot be read ({type(exc).__name__})"}
    cached.write_text(json.dumps(feat))
    return feat


# ----------------------------------------------------------------------------------- main

PIN_ORDER = ["numberPins", "numberRows", "numberPinsPerRow", "rowDistance", "pitch",
             "centralPitch", "pinDescription"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--pdf-dir", type=Path)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    records = [json.loads(line) for line in args.data.open()]
    stats = collections.Counter()
    per_family = collections.Counter()
    report = []

    for record in records:
        info = record.get("manufacturerInfo") or {}
        url = info.get("datasheetUrl") or ""
        if "norwe.eu/katalogbilder" not in url:
            continue
        functional = record["functionalDescription"]
        pinout = functional.get("pinout")
        name = record.get("name", "")
        row = {"bobbin": name, "url": url, "status": "", "reason": "",
               "numberRows": "", "numberPinsPerRow": "", "rowDistance_mm": "",
               "pitch_mm": "", "centralPitch_mm": "", "typeCode": ""}

        feat = sheet(url, args.cache, args.pdf_dir, args.offline)
        row["typeCode"] = type_code(feat) or ""
        geometry, why = read_pin_field(feat)

        # Orientation and chamber count, where Norwe's own type code on this sheet states
        # them and the record does not.  A contradiction is reported, never resolved here.
        code = type_code(feat)
        orientation, coded_pins = stated_orientation(code)
        if orientation:
            have = functional.get("orientation")
            if have and have != orientation:
                stats["conflict: orientation"] += 1
                report.append(dict(row, status="conflict",
                                   reason=f"record says {have}, the sheet's type code "
                                          f"'{code}' says {orientation}"))
                continue
            if not have and not args.dry_run:
                functional["orientation"] = orientation
                stats["orientation from the sheet's own type code"] += 1

        if not pinout:
            stats["skipped: the record declares no pinout"] += 1
            continue
        if geometry is None:
            stats[f"refused: {why.split('(')[0].strip()}"] += 1
            report.append(dict(row, status="refused", reason=why))
            continue
        coded_pitch = stated_pitch(code)
        drawn_pitch = geometry.get("pitch")
        if (coded_pitch is not None and isinstance(drawn_pitch, (int, float))
                and abs(coded_pitch - drawn_pitch) > 0.06):
            stats["refused: the sheet's own type code and its drawing disagree on the pitch"] += 1
            report.append(dict(row, status="refused",
                               reason=f"type code '{code}' states a {coded_pitch} mm pitch, "
                                      f"the drawing measures {drawn_pitch} mm"))
            continue
        if coded_pins is not None and coded_pins != geometry["numberPins"]:
            stats["refused: the sheet's own type code and its drawing disagree on pin count"] += 1
            report.append(dict(row, status="refused",
                               reason=f"type code '{code}' says {coded_pins} pins, the "
                                      f"drawing has {geometry['numberPins']} dots"))
            continue
        if geometry["numberPins"] != pinout["numberPins"]:
            stats["refused: the drawing's pin count differs from the record's"] += 1
            report.append(dict(row, status="refused",
                               reason=f"record says {pinout['numberPins']} pins, the drawing "
                                      f"has {geometry['numberPins']}"))
            continue

        written = {k: v for k, v in geometry.items()
                   if k in PIN_ORDER and k != "numberPins"}
        row.update({"numberRows": written.get("numberRows", ""),
                    "numberPinsPerRow": written.get("numberPinsPerRow", ""),
                    "rowDistance_mm": written.get("rowDistance", ""),
                    "pitch_mm": written.get("pitch", ""),
                    "centralPitch_mm": written.get("centralPitch", "")})

        clash = []
        for key in ("rowDistance", "pitch", "centralPitch", "numberRows", "numberPinsPerRow"):
            if key not in pinout or key not in written:
                continue
            have, drawn = pinout[key], written[key]
            if isinstance(have, (int, float)) and isinstance(drawn, (int, float)):
                if abs(have - drawn * (MM if key != "numberRows" else 1)) > 1e-9:
                    clash.append(f"{key}: record {have}, drawing {drawn}")
            elif have != drawn and not (key == "numberPinsPerRow" and have == drawn):
                clash.append(f"{key}: record {have}, drawing {drawn}")
        if clash:
            stats["conflict: the drawing contradicts geometry already on the record"] += 1
            report.append(dict(row, status="conflict", reason="; ".join(clash)))
            continue
        if any(k in pinout for k in ("pitch", "rowDistance")):
            stats["left alone: the record already carries geometry the drawing agrees with"] += 1
            report.append(dict(row, status="already-present",
                               reason="the drawing agrees with what the record holds"))
            continue

        for key, value in written.items():
            if key in ("numberRows", "numberPinsPerRow"):
                pinout[key] = value
            elif isinstance(value, list):
                pinout[key] = [round(v * MM, 9) for v in value]
            else:
                pinout[key] = round(value * MM, 9)
        functional["pinout"] = {k: pinout[k] for k in PIN_ORDER if k in pinout}
        chambers = stated_chambers(code)
        stats["enriched"] += 1
        per_family[functional["family"]] += 1
        report.append(dict(row, status="enriched",
                           reason=f"{geometry['_how']}"
                                  + (f"; {chambers}-chamber per the type code" if chambers else "")))

    if not args.dry_run:
        with args.data.open("w") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    if args.report:
        fields = ["bobbin", "url", "status", "numberRows", "numberPinsPerRow",
                  "rowDistance_mm", "pitch_mm", "centralPitch_mm", "typeCode", "reason"]
        with args.report.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(sorted(report, key=lambda r: (r["status"], r["bobbin"])))

    for key, value in stats.most_common():
        print(f"  {key}: {value}")
    print("enriched per family: " + ", ".join(f"{k}={v}" for k, v in sorted(per_family.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
