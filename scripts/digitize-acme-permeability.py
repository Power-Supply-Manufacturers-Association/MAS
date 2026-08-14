#!/usr/bin/env python3
"""Digitize the "Complex Permeability V.S. Frequency" chart of an ACME ferrite material
straight out of the vendor catalogue PDF, and emit the MAS `permeability.complex` block.

    python3 scripts/digitize-acme-permeability.py A10 [--pdf acme_product_now.pdf]
                                                      [--patch data/core_materials.ndjson]

Source
------
  https://www.acme-ferrite.com.tw/img/CorePDF/acme_product_now.pdf   (whole catalogue)
  https://www.acme-ferrite.com.tw/doc/Datasheet/<MATERIAL>.pdf       (same page, per material;
                                                                      verified identical art)

Why a script instead of eyeballing the plot
-------------------------------------------
The charts are pure vector art, so the published curves can be read back EXACTLY: mu' is a
chain of solid line segments, mu'' a single dashed polyline, and the plot frame rectangle
IS the axis box, which calibrates the log-log mapping with no human judgement. Every
emitted point therefore lies on the curve ACME drew.

Nothing is extrapolated. Each table stops where the vendor's polyline stops: mu' leaves the
chart when it plunges through ferromagnetic resonance (~0.8-2.8 MHz for the A family), mu''
is drawn considerably further out (14 MHz for A10, 100 MHz for A06). Material grades whose
curves genuinely start at 10 kHz / 40 kHz produce tables that start there too.

Axis calibration
----------------
x is 1..1e5 kHz and the y top is 1e5 on every A-family sheet (checked by fingerprinting the
vector glyphs of the corner tick labels - the labels are paths, not text). The y BOTTOM is
NOT constant: A043's chart is 10..1e5, everyone else's is 1e2..1e5. The number of y decades
is therefore measured from the log-minor gridline spacing (the widest gap inside the frame
is the 1->2 minor, i.e. log10(2) of a decade) and the script refuses to guess if that does
not come out integral. Assuming 1e2 there read A043's mu' 13 % high and its mu'' up to 90 %
off.

What counts as "drawn"
----------------------
mu' is cut where its polyline leaves the plot box. Past resonance mu' goes negative, so the
plotting program's line dives off the bottom of a log axis and the plot's clip path hides
it; that invisible continuation is a near-vertical artefact (a decade of value per ~1 % in
frequency), not readable data. mu'' is kept as drawn, including the slowly-varying part
below the axis floor, which is the same curve merely outside the plotted window.

Method validation
-----------------
Reproduces MAS's A10 and A102 records (themselves produced by this script in ABT #313) BYTE
FOR BYTE, and reproduces nine independently digitized stored tables it never wrote - A06,
A064, A07, A071, A072, A103, A104, A121, A13, A151 - to 0.1-2.5 % mean over their common
span (A06 mu'' 1.1 % mean / 4.4 % max over 10 kHz..97 MHz). That agreement is what licenses
trusting it on materials whose stored data is wrong or missing: in ABT #314 the same
comparison exposed A043, A044, A05 and A062 as matching no ACME chart at all (rms-log 0.2
to 0.6 against their own charts, where a faithful entry scores 0.002-0.03).
"""
import argparse
import json
import math
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("needs PyMuPDF:  pip install pymupdf")


CHART_REGION = (80, 640, 300, 845)
X_LO, X_HI = 1e3, 1e8            # x axis is 1..1e5 kHz on every A-family sheet (verified by glyph fingerprint)
Y_HI = 1e5                       # top y label is 1e5 on every sheet (verified by glyph fingerprint)
GRID_F0, GRID_PER_DECADE = 1000.0, 80
DARK = 0.3


def find_page(doc, material):
    needle = f"Material Characteristics-{material}"
    for i in range(doc.page_count):
        for line in doc[i].get_text().split("\n"):
            if line.strip() == needle:
                return i
    raise SystemExit(f"no '{needle}' page in {doc.name}")


def _region_drawings(page):
    """Drawings that OVERLAP the chart panel.

    Overlap, not containment: a curve may start left of the axis or plunge below it (the
    viewer never sees those parts - the plot's clip path hides them), and such a path has a
    bounding box sticking out of the panel. Rect.intersects() is not usable here either: a
    horizontal gridline / curve segment has a zero-height (empty) rect, for which PyMuPDF's
    intersects() is always False.
    """
    x0, y0, x1, y1 = CHART_REGION
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.x1 >= x0 and r.x0 <= x1 and r.y1 >= y0 and r.y0 <= y1:
            out.append(d)
    return out


def _frame(ds):
    frames = [d for d in ds if d["type"] == "s" and d["color"] and max(d["color"]) < DARK
              and d["rect"].width > 100 and d["rect"].height > 60]
    if not frames:
        raise SystemExit("no plot frame found - is this a material characteristics page?")
    return max(frames, key=lambda d: d["rect"].width * d["rect"].height)["rect"]


def _y_decades(ds, fr):
    """Number of decades on the y axis, from the log-minor gridline spacing."""
    hs = set()
    for d in ds:
        if d["type"] == "s" and d["rect"].width > 0.95 * fr.width and d["rect"].height > 0.95 * fr.height:
            continue
        for it in d["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                if abs(p.y - q.y) < 0.05 and abs(p.x - q.x) > 0.5 * fr.width:
                    hs.add(round((p.y + q.y) / 2, 2))
            elif it[0] == "re":
                r = it[1]
                if r.height < 0.05 and r.width > 0.5 * fr.width:
                    hs.add(round((r.y0 + r.y1) / 2, 2))
    ys, ded = sorted(hs), []
    for v in ys:
        if not ded or v - ded[-1] > 0.3:
            ded.append(v)
    if len(ded) < 10:
        raise SystemExit("too few horizontal gridlines to calibrate the y axis")
    gap = max(ded[i + 1] - ded[i] for i in range(len(ded) - 1))   # the 1->2 minor gap
    n = fr.height / (gap / math.log10(2.0))
    if abs(n - round(n)) > 0.15:
        raise SystemExit(f"y axis decade count is not integral ({n:.3f}) - refusing to guess")
    return int(round(n))


def _path_points(drawing):
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


def _clip_box(poly, y_lo):
    """Longest run of the curve INSIDE the plot box, with the boundary crossings interpolated.

    Anything outside the frame is not published artwork: the PDF's clip path hides it, so the
    reader never sees it. Both the mu' plunge (which continues below the axis) and curve heads
    that start left of the axis get cut exactly where the vendor's plot cuts them.
    """
    def inside(p):
        return X_LO - 1e-9 <= p[0] <= X_HI * (1 + 1e-12) and y_lo * (1 - 1e-12) <= p[1] <= Y_HI * (1 + 1e-12)

    def cross(a, b):
        """point where segment a->b (straight in log-log) meets the box, walking from a."""
        lo, hi = 0.0, 1.0
        la, lb = (math.log(a[0]), math.log(a[1])), (math.log(b[0]), math.log(b[1]))
        for _ in range(60):
            t = 0.5 * (lo + hi)
            p = (math.exp(la[0] + t * (lb[0] - la[0])), math.exp(la[1] + t * (lb[1] - la[1])))
            if inside(p):
                lo = t
            else:
                hi = t
        t = lo
        return (math.exp(la[0] + t * (lb[0] - la[0])), math.exp(la[1] + t * (lb[1] - la[1])))

    runs, cur = [], []
    for i, p in enumerate(poly):
        if inside(p):
            if not cur and i > 0:
                cur.append(cross(p, poly[i - 1]))
            cur.append(p)
        else:
            if cur:
                cur.append(cross(cur[-1], p))
                runs.append(cur)
                cur = []
    if cur:
        runs.append(cur)
    if not runs:
        return []
    runs.sort(key=lambda r: math.log(r[-1][0] / r[0][0]) if r[0][0] > 0 else 0)
    return sorted(runs[-1])


def curves(page, clip_real=True, clip_imaginary=False):
    """(mu' polyline, mu'' polyline, y axis floor) in data coordinates.

    mu' is cut where the drawn polyline leaves the plot box, mu'' is kept as drawn.
    Rationale: below the axis floor the two curves are not comparable. mu' is in its
    near-vertical plunge through ferromagnetic resonance (mu' crosses zero, so on a log
    axis the polyline dives: a decade of value per ~1 % in frequency), which is both
    invisible to the reader and numerically meaningless to digitise. mu'' below the floor
    is the same slowly-varying curve as above it, merely outside the plotted window.
    """
    ds = _region_drawings(page)
    fr = _frame(ds)
    y_lo = Y_HI / 10.0 ** _y_decades(ds, fr)

    solid, dashed = [], []
    for d in ds:
        if d["type"] != "s" or not d["color"] or max(d["color"]) > DARK:
            continue
        if d["rect"].width > 0.95 * fr.width and d["rect"].height > 0.95 * fr.height:
            continue                                   # the frame itself
        pts = _path_points(d)
        if not pts:
            continue
        (dashed if d.get("dashes") not in (None, "", "[] 0") else solid).extend(pts)

    def to_data(pts):
        out = []
        for x, y in pts:
            f = X_LO * (X_HI / X_LO) ** ((x - fr.x0) / fr.width)
            v = y_lo * (Y_HI / y_lo) ** ((fr.y1 - y) / fr.height)
            out.append((f, v))
        out.sort()
        merged = []
        for f, v in out:
            if merged and abs(math.log(f / merged[-1][0])) < 1e-6:
                merged[-1] = (merged[-1][0], 0.5 * (merged[-1][1] + v))
            else:
                merged.append((f, v))
        return merged

    def maybe_clip(poly, do):
        return _clip_box(poly, y_lo) if do else poly

    return (maybe_clip(to_data(solid), clip_real),
            maybe_clip(to_data(dashed), clip_imaginary), y_lo)


def resample(poly):
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
    mu1, mu2, y_lo = curves(page)
    if not mu1 or not mu2:
        raise SystemExit("no curves extracted")
    print(f"{args.material}: y axis floor {y_lo:g}, mu' drawn to {mu1[-1][0]:.6g} Hz, "
          f"mu'' drawn to {mu2[-1][0]:.6g} Hz", file=sys.stderr)
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
