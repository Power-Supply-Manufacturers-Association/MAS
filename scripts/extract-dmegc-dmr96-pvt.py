#!/usr/bin/env python3
"""Read the three Pv-T curves of DMEGC DMR96 from the data sheet's vector chart.

    python3 scripts/extract-dmegc-dmr96-pvt.py DMR96_Material_Characteristics.pdf > dmr96-pvt.json

Source: DMEGC "DMR96 Material Characteristic", DMR96-REV.C dated 2019-04, 2 pages,
https://irp.cdn-website.com/eb58f5fe/files/uploaded/DMR96_Material_Characteristics.pdf
read 2026-10-28 (322,604 bytes, sha256 d872b55f7aea088ffafb8a75003c0f715184b13f9082355b4ae66fe12f0d42a1).
Page 2, chart "Power Loss PV (mW/cm3)" vs "Temperature (C)", legend 100kHz 200mT (black),
200kHz 125mT (red), 300kHz 100mT (green).

Method: the curves are vector polylines. The axes are calibrated on the chart's own gridlines
(-40..160 C every 20 C, 0..500 mW/cm3 every 50; residual printed on stderr), each curve is
identified by the colour of its legend swatch, and the drawn line is sampled at -20 C, every
5 C from -15 C, and its end (139.97 C). Output in kW/m3 (= mW/cm3).
Check against the page-1 typical-value table (100 kHz/200 mT 315/310/280/355, 200 kHz/125 mT
265/260/210/280, 300 kHz/100 mT 295/290/240/340 mW/cm3 at -20/25/100/140 C): every curve
reads within 0.977..1.022 of the table.
"""
import sys, json, numpy as np, pymupdf as fitz
pdf = sys.argv[1]
p = fitz.open(pdf)[1]
# gridlines (verified against tick labels -40..160 C step 20, 0..500 mW/cm3 step 50)
VX = [92.11, 111.17, 130.31, 149.44, 168.58, 187.71, 206.85, 225.98, 245.12, 264.18, 283.31]
HY = [93.28, 108.84, 124.4, 139.96, 155.51, 171.07, 186.63, 202.18, 217.74, 233.3, 248.86]
tx = np.arange(-40, 161, 20); ty = np.arange(500, -1, -50)
ax, bx = np.polyfit(VX, tx, 1); ay, by = np.polyfit(HY, ty, 1)
gx = max(abs(np.polyval([ax, bx], VX) - tx)); gy = max(abs(np.polyval([ay, by], HY) - ty))
print(f"grid residual: {gx:.3f} C, {gy:.3f} mW/cm3", file=sys.stderr)
# legend: swatch line colour on the same row as each label
labels = {}
for w in p.get_text('words'):
    if w[4] in ('100kHz,', '200kHz,', '300kHz,') and w[3] < 250: labels[w[4]] = (w[1] + w[3]) / 2
legend = {}
curves = {}
for d in p.get_drawings():
    r = d['rect']; col = tuple(round(v, 2) for v in (d['color'] or ()))
    if r.y1 < 250 and 200 < r.x0 < 227 and r.x1 < 228 and len(d['items']) <= 2:
        for k, yc in labels.items():
            if abs((r.y0 + r.y1) / 2 - yc) < 3: legend[col] = k
    if len(d['items']) > 100 and r.x1 < 290 and r.y1 < 250:
        pts = [d['items'][0][1]] + [it[-1] for it in d['items']]
        curves[col] = [(float(np.polyval([ax, bx], q.x)), float(np.polyval([ay, by], q.y))) for q in pts]
print("legend", legend, file=sys.stderr)
cond = {'100kHz,': (100e3, 0.200), '200kHz,': (200e3, 0.125), '300kHz,': (300e3, 0.100)}
out = {}
for col, c in curves.items():
    c = sorted(c); T = np.array([a for a, _ in c]); P = np.array([b for _, b in c])
    out[legend[col]] = (T, P)
res = []
for k, (T, P) in out.items():
    f, B = cond[k]
    grid = [-20] + list(range(-20 + 5, 141, 5))
    grid = sorted(set([max(T.min(), -20.0)] + [g for g in grid if T.min() <= g <= T.max()] + [min(T.max(), 140.0)]))
    for g in grid:
        res.append({"f": f, "B": B, "T": round(float(g), 2), "Pv_kWm3": round(float(np.interp(g, T, P)), 2)})
    print(k, f"span {T.min():.2f}..{T.max():.2f} C, min {P.min():.1f} at {T[P.argmin()]:.1f} C", file=sys.stderr)
json.dump(res, sys.stdout, indent=0)
