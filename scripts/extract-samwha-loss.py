#!/usr/bin/env python3
"""Extract Pv-T core-loss curves for Samwha PL-5, PL-7, PL-11, PL-13 from Samwha's vector data sheets (ABT #1518).

    python3 scripts/extract-samwha-loss.py PL-5.pdf PL-7.pdf PL-11.pdf PL-13.pdf --json /tmp/samwha-points.json \
            [--report /tmp/samwha-report.json]

Sources
-------
Samwha Electronics "Power Material" data sheets, one page each (Adobe InDesign CS3, Adobe PDF Library 8.0):
    http://www.samwha.co.kr/electronics_eng/material/Material%20characteristics_PL-<n>.pdf
Read 2026-09-30:
    PL-5   170,975 B  sha256 615f1b343e225ab50371437e75055115f509f3d7c9b691da459ed2f7c091bdc2
    PL-7   166,275 B  sha256 2617cc6ae426c68236923330bc370ab5c4c590ecec1afe98cde9d6a02a820d9d
    PL-11  172,674 B  sha256 9ee922a81bb08daf0984c7bddf2986c38a34a98ad2d61180e2ba846a5e77fcf1
    PL-13  172,483 B  sha256 48339acb97f7df3de44a97a26037558d230fa57cc5c45484d84538a8b9076def
Each sheet prints a table "Core loss (100kHz, 200mT) Pcv kW/m3" at 25/80/100/120 C and a figure
"Core loss vs. Temperature" (linear axes, 20..120 C) with three curves labelled "100kHz, 200mT",
"200kHz, 100mT" and "25kHz, 200mT". Test core printed: "toroidal cores(30X8-20H)" (no Ve).
The sheets carry no Pv-B or Pv-f figure; only the Pv-T figure is read.

Method -- nothing is digitised from pixels
------------------------------------------
The figure is vector: gridlines are strokes (minor every 10 C / half a label step), the three curves
are single black polylines (PL-11: one path with three subpaths).
1. Calibration from the gridlines, checked against every printed tick label (LABEL_TOL) and for a
   straight linear scale (GRID_TOL) -- extract-dmegc-loss.Axis.
2. Curve labels: the three condition labels are printed next to the curves' right ends; the label
   order top->bottom must equal the curve order top->bottom, and the curves must not cross anywhere
   (loss ordering 100k/200m > 200k/100m > 25k/200m at every temperature, as Steinmetz behaviour of a
   power MnZn ferrite requires).
3. Check that can fail (#1006): the 100 kHz/200 mT curve must reproduce every printed table value
   (25/80/100/120 C) within TABLE_TOL, else the whole figure is rejected (all three curves share its
   calibration; the other two conditions have no printed value and are stored on the strength of
   the figure check, as for the TDK/Proterial Pv-T figures).
4. Points: each curve at its first temperature (25 C) and every 10 C from 30 to its last (120 C).
Result (2026-09-30): 33 points per grade (3 curves x 25, 30..120 C) = 132; table ratios (25/80/100/120 C)
PL-5 1.032/0.990/1.000/1.001, PL-7 1.046/0.982/1.000/1.001, PL-11 1.000/1.000/1.000/1.001, PL-13 1.000 x4
(the 100 kHz/200 mT curves pass through the printed values). Axis residuals: grid <= 0.09 pt; tick labels
<= 1.88 pt (the "20" and "100" x labels sit ~1.9/1.2 pt left of their gridlines on all four sheets). No reject.

Output: {material: [MAS volumetricLossesPoint, ...]} in SI; waveform "sinusoidal" (Samwha measures
sine-wave Pcv), origin "manufacturer".
"""
import argparse
import importlib.util
import json
import math
import os
import re
import sys

import fitz

_spec = importlib.util.spec_from_file_location(
    "dmegc", os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract-dmegc-loss.py"))
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)
point, Axis, interp, pvt_samples = D.point, D.Axis, D.interp, D.pvt_samples

TABLE_TOL = 0.10
# printed Pcv tables (100 kHz, 200 mT, kW/m3); re-read from the page words in read_table()
TABLES = {
    "PL-5": {25: 800, 80: 550, 100: 500, 120: 600},
    "PL-7": {25: 650, 80: 450, 100: 410, 120: 500},
    "PL-11": {25: 650, 80: 350, 100: 320, 120: 400},
    "PL-13": {25: 400, 80: 300, 100: 340, 120: 400},
}
CONDS = [(100e3, 0.2), (200e3, 0.1), (25e3, 0.2)]   # expected top->bottom order


def read_table(pg, mat):
    words = pg.get_text("words")
    flat = re.sub(r"\s+", " ", pg.get_text())
    if not re.search(rf"Material\s+{mat}(?!\d)", pg.get_text()):
        raise SystemExit(f"{mat}: material name not on the page")
    if "Core loss (100kHz, 200mT)" not in flat:
        raise SystemExit(f"{mat}: table condition missing")
    y_cl = [w[1] for w in words if w[4] == "(100kHz," and w[1] < 300][0]
    y_sat = [w[1] for w in words if w[4] == "Saturation" and w[1] < 300][0]
    y_ip = [w[1] for w in words if w[4] == "Initial" and w[1] < 300][0]
    # the four Pcv rows straddle the "Core loss" label (+-23 pt); the Bs rows start ~36 pt below it
    temps = [w for w in words if re.fullmatch(r"\d+℃", w[4]) and abs(w[1] - y_cl) < 28 and y_ip + 5 < w[1] < y_sat
             and 330 < w[0] < 380]
    if len(temps) != 4:
        raise SystemExit(f"{mat}: {len(temps)} Pcv table rows")
    tab = {}
    for t in temps:
        v = [w for w in words if re.fullmatch(r"\d+", w[4]) and 460 < w[0] < 510 and abs(w[1] - t[1]) < 2]
        if len(v) != 1:
            raise SystemExit(f"{mat}: table row {t[4]} has {len(v)} values")
        tab[int(t[4][:-1])] = int(v[0][4])
    if tab != TABLES[mat]:
        raise SystemExit(f"{mat}: page table {tab} != {TABLES[mat]}")
    return tab, y_cl


def subpaths(d):
    out, cur = [], []
    for it in d["items"]:
        if it[0] != "l":
            raise RuntimeError(f"unexpected path item {it[0]}")
        p, q = it[1], it[2]
        if cur and (abs(cur[-1][0] - p.x) > 1e-6 or abs(cur[-1][1] - p.y) > 1e-6):
            out.append(cur); cur = []
        if not cur:
            cur.append((p.x, p.y))
        cur.append((q.x, q.y))
    if cur:
        out.append(cur)
    return out


def pvt_figure(pg, mat, rep):
    words = pg.get_text("words")
    t = [w for w in words if w[4] == "Temperature" and w[0] > 300 and 560 < w[1] < 600]
    if len(t) != 1 or not any(w[4] == "Core" and abs(w[1] - t[0][1]) < 1 for w in words):
        raise SystemExit(f"{mat}: 'Core loss vs. Temperature' title not found")
    box = fitz.Rect(300, t[0][3], pg.rect.width, t[0][3] + 160)
    H, V, curves = set(), set(), []
    for d in pg.get_drawings():
        c = d.get("color")
        if c is None or not box.contains(d["rect"]) or max(c) > 0.2:
            continue
        w = d.get("width") or 0
        if w > 0.7:
            if len(d["items"]) >= 20:
                curves += [s for s in subpaths(d) if len(s) >= 20]
            continue
        for it in d["items"]:
            if it[0] != "l":
                continue
            p, q = it[1], it[2]
            if abs(p.y - q.y) < 0.01 and abs(p.x - q.x) > 100:
                H.add(round(p.y, 2))
            elif abs(p.x - q.x) < 0.01 and abs(p.y - q.y) > 80:
                V.add(round(p.x, 2))
    V = sorted(V); H = sorted(H)
    V = [v for i, v in enumerate(V) if i == 0 or v - V[i - 1] > 1.0]
    H = [h for i, h in enumerate(H) if i == 0 or h - H[i - 1] > 1.0]
    xl, yl = [], []
    for w in words:
        if not re.fullmatch(r"-?\d+(\.\d+)?", w[4]):
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if V[0] - 8 <= cx <= V[-1] + 8 and H[-1] + 3 < cy < H[-1] + 16 and w[2] > V[0]:
            xl.append((cx, float(w[4])))
        elif H[0] - 8 <= cy <= H[-1] + 8 and V[0] - 30 < w[2] < V[0]:
            yl.append((cy, float(w[4])))
    xs = sorted(v for _, v in xl); ys = sorted(v for _, v in yl)
    X = Axis(V, xl, False, (xs[1] - xs[0]) / 2, rep, "x")
    Y = Axis(H, yl, False, (ys[1] - ys[0]) / 2, rep, "y")
    rep["x_labels"] = xs; rep["y_labels"] = ys
    if len(curves) != 3:
        raise SystemExit(f"{mat}: {len(curves)} curves in the Pv-T figure")
    # labels: "<f>kHz," + "<B>mT" on one line, right of the curves
    labs = []
    for w in words:
        m = re.fullmatch(r"(\d+)kHz,", w[4])
        if m and box.contains(fitz.Rect(w[:4])):
            b = [u for u in words if abs(u[1] - w[1]) < 1 and 0 < u[0] - w[2] < 5 and re.fullmatch(r"\d+mT", u[4])]
            labs.append((w[1], float(m.group(1)) * 1e3, float(b[0][4][:-2]) / 1e3))
    labs = [(f, B) for _, f, B in sorted(labs)]
    if labs != CONDS:
        raise SystemExit(f"{mat}: labels top->bottom {labs}")
    curves.sort(key=lambda s: sum(p[1] for p in s) / len(s))   # top (smaller y) first
    samples = [pvt_samples(X, Y, c) for c in curves]
    # no crossing: at every sampled temperature the order is strict
    for i, (t0, _) in enumerate(samples[0]):
        vals = [dict(s)[t0] for s in samples]
        if not (vals[0] > vals[1] > vals[2]):
            raise SystemExit(f"{mat}: curves not in label order at {t0} C: {vals}")
    return X, Y, curves, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()
    report, result, rc = {}, {}, 0
    for path in a.pdfs:
        mat = os.path.splitext(os.path.basename(path))[0]
        pg = fitz.open(path)[0]
        rep = report.setdefault(mat, {})
        tab, _ = read_table(pg, mat)
        X, Y, curves, samples = pvt_figure(pg, mat, rep)
        top = curves[0]
        chk = []
        for T, pv in sorted(tab.items()):
            y = interp(top, X.pos(T))
            v = Y.value(y)
            chk.append(dict(T=T, table=pv, curve=round(v, 1), ratio=round(v / pv, 3)))
        rep["table"] = chk
        rep["samples"] = {f"{f/1e3:g}kHz/{B*1e3:g}mT": [(t, round(v, 1)) for t, v in s]
                          for (f, B), s in zip(CONDS, samples)}
        bad = [c for c in chk if abs(c["ratio"] - 1) > TABLE_TOL]
        if bad:
            rep["REJECTED"] = "; ".join(f"{c['T']} C reads {c['curve']} vs table {c['table']} ({c['ratio']})" for c in bad)
            print(f"{mat}: REJECTED {rep['REJECTED']}")
            rc = 1
            continue
        pts = [point(f, B, t, v) for (f, B), s in zip(CONDS, samples) for t, v in s]
        result[mat] = pts
        print(f"{mat}: {len(pts)} points, table ratios {[c['ratio'] for c in chk]}, "
              f"axes {rep['x']} {rep['y']}")
    json.dump(result, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
