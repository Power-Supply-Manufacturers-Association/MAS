#!/usr/bin/env python3
"""Digitize the "Complex Permeability V.S. Frequency" chart of an ACME ferrite material
straight out of the vendor catalogue PDF, and emit the MAS `permeability.complex` block.

    python3 scripts/digitize-acme-permeability.py A10 [--pdf acme_product_now.pdf]
                                                      [--patch data/core_materials.ndjson]

Source
------
  https://www.acme-ferrite.com.tw/img/CorePDF/acme_product_now.pdf   (whole catalogue)
  https://www.acme-ferrite.com.tw/doc/Datasheet/<MATERIAL>.pdf       (same page, per material)

Why a script instead of eyeballing the plot
-------------------------------------------
The charts are pure vector art, so the published curves can be read back EXACTLY: mu' is a
chain of solid line segments, mu'' a single dashed polyline, and the plot frame rectangle
IS the axis box (x = 1..1e5 kHz, y = 1e2..1e5), which calibrates the log-log mapping with
no human judgement. Every emitted point therefore lies on the curve ACME drew.

Nothing is extrapolated. Each table stops where the vendor's polyline stops: mu' leaves
the chart when it plunges through ferromagnetic resonance (~1-2.6 MHz for the A family),
mu'' is drawn considerably further out (16.8 MHz for A10, 100 MHz for A06). Material grades
whose curves genuinely start at 10 kHz / 40 kHz produce tables that start there too.

Method validation
-----------------
Run on A06 (page 42) it reproduces MAS's pre-existing, independently digitized A06 table:
mu'' to 1.1 % mean / 4.6 % max over 10 kHz..97 MHz, mu' to 1.1 % mean / 2.6 % max below
900 kHz (the two points on the near-vertical resonance plunge differ by up to 36 %, where
mu' drops a decade across 3 % in frequency). On A102 (page 45) it lands within 1-3 % of the
span that entry already covers faithfully. That agreement is what licenses trusting it on
materials whose stored data is wrong or missing.
"""
import argparse
import io
import json
import math
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("needs PyMuPDF:  pip install pymupdf")

# printed page number of each material's "Material Characteristics" sheet is the PDF page
# index minus 1; the index is resolved from the page text so a re-paginated catalogue still
# works.
CHART_REGION = (80, 640, 300, 845)   # bottom-left panel of a material sheet, PDF points
X_LO, X_HI = 1e3, 1e8                # axis limits, Hz (chart is labelled in kHz: 1..1e5)
Y_LO, Y_HI = 1e2, 1e5                # axis limits, relative permeability
GRID_F0, GRID_PER_DECADE = 1000.0, 80


def find_page(doc, material):
    needle = f"Material Characteristics-{material}"
    for i in range(doc.page_count):
        text = doc[i].get_text()
        if needle in text and "\n".join(text.split("\n")).count(needle):
            for line in text.split("\n"):
                if line.strip() == needle:
                    return i
    raise SystemExit(f"no '{needle}' page in {doc.name}")


def _points(drawing):
    pts = []
    for it in drawing["items"]:
        if it[0] == "l":
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif it[0] == "c":
            p0, p1, p2, p3 = it[1], it[2], it[3], it[4]
            for k in range(9):
                t, mt = k / 8.0, 1 - k / 8.0
                pts.append((mt**3*p0.x + 3*mt*mt*t*p1.x + 3*mt*t*t*p2.x + t**3*p3.x,
                            mt**3*p0.y + 3*mt*mt*t*p1.y + 3*mt*t*t*p2.y + t**3*p3.y))
    return pts


def curves(page):
    """(mu' polyline, mu'' polyline) in data coordinates, from the chart's vector art."""
    x0, y0, x1, y1 = CHART_REGION
    ds = [d for d in page.get_drawings()
          if d["rect"].x0 >= x0 - 1 and d["rect"].x1 <= x1 + 1
          and d["rect"].y0 >= y0 - 1 and d["rect"].y1 <= y1 + 1]
    frames = [d for d in ds if d["type"] == "s" and d["color"] and max(d["color"]) < 0.3
              and d["rect"].width > 100 and d["rect"].height > 60]
    if not frames:
        raise SystemExit("no plot frame found - is this a material characteristics page?")
    fr = max(frames, key=lambda d: d["rect"].width * d["rect"].height)["rect"]

    solid, dashed = [], []
    for d in ds:
        if d["type"] != "s" or not d["color"] or max(d["color"]) > 0.3:
            continue
        if d["rect"].width > 0.95 * fr.width and d["rect"].height > 0.95 * fr.height:
            continue                                   # the frame itself
        pts = [p for p in _points(d) if fr.x0 - 0.5 <= p[0] <= fr.x1 + 0.5]
        if not pts:
            continue
        (dashed if d.get("dashes") not in (None, "", "[] 0") else solid).extend(pts)

    def to_data(pts):
        out = []
        for x, y in pts:
            f = X_LO * (X_HI / X_LO) ** ((x - fr.x0) / fr.width)
            v = Y_LO * (Y_HI / Y_LO) ** ((fr.y1 - y) / fr.height)
            out.append((f, v))
        out.sort()
        merged = []
        for f, v in out:
            if merged and abs(math.log(f / merged[-1][0])) < 1e-6:
                merged[-1] = (merged[-1][0], 0.5 * (merged[-1][1] + v))
            else:
                merged.append((f, v))
        return merged

    return to_data(solid), to_data(dashed)


def resample(poly):
    """Sample the drawn polyline onto a log grid, strictly inside its own span.

    The polyline is straight-line art in the PDF, i.e. straight in (log f, log mu), so
    log-log interpolation reproduces the drawn curve rather than approximating it.
    """
    ratio = 10 ** (1.0 / GRID_PER_DECADE)
    k0 = math.ceil(math.log(poly[0][0] / GRID_F0) / math.log(ratio) - 1e-9)
    k1 = math.floor(math.log(poly[-1][0] / GRID_F0) / math.log(ratio) + 1e-9)
    out, j = [], 1
    for k in range(max(k0, 0), k1 + 1):
        f = GRID_F0 * ratio ** k
        while j < len(poly) - 1 and poly[j][0] < f:
            j += 1
        (f0, v0), (f1, v1) = poly[j - 1], poly[j]
        t = (math.log(f) - math.log(f0)) / (math.log(f1) - math.log(f0))
        out.append({"frequency": round(f, 4),
                    "value": round(math.exp(math.log(v0) + t * (math.log(v1) - math.log(v0))), 4)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("material")
    ap.add_argument("--pdf", default="acme_product_now.pdf",
                    help="the ACME catalogue PDF (or the per-material datasheet PDF)")
    ap.add_argument("--patch", help="rewrite this ndjson in place, replacing the material's "
                                    "permeability.complex block")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    page = doc[find_page(doc, args.material)]
    mu1, mu2 = curves(page)
    if not mu1 or not mu2:
        raise SystemExit("no curves extracted")
    block = {"real": resample(mu1), "imaginary": resample(mu2)}
    for key in ("real", "imaginary"):
        t = block[key]
        print(f"{args.material} {key:9}: {len(t):4d} pts  "
              f"{t[0]['frequency']:.6g}..{t[-1]['frequency']:.6g} Hz  "
              f"({t[0]['value']:.1f} .. {t[-1]['value']:.1f})", file=sys.stderr)

    if not args.patch:
        print(json.dumps(block))
        return
    lines, hit = [], 0
    for line in open(args.patch):
        rec = json.loads(line)
        if rec.get("name") == args.material:
            rec["permeability"]["complex"] = block
            hit += 1
            lines.append(json.dumps(rec, ensure_ascii=False))
        else:
            lines.append(line.rstrip("\n"))
    if hit != 1:
        raise SystemExit(f"expected exactly one '{args.material}' record, found {hit}")
    with open(args.patch, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"patched {args.material} in {args.patch}", file=sys.stderr)


if __name__ == "__main__":
    main()
