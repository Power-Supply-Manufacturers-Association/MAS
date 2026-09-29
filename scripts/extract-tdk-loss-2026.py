#!/usr/bin/env python3
"""Extract core-loss curves from TDK's 2026 Mn-Zn ferrite material catalogue (vector PDF) (ABT #1518).

    python3 scripts/extract-tdk-loss-2026.py ferrite_material_characteristics_en.pdf \
            --json /tmp/tdk2026-points.json [--report /tmp/tdk2026-report.json]

Source
------
TDK Corporation, "Mn-Zn Ferrite -- Material characteristics", catalogue
ferrite_material_characteristics_en, edition 20260420 (April 2026), 18 pages:
    https://product.tdk.com/system/files/dam/doc/product/ferrite/ferrite/ferrite-core/catalog/ferrite_material_characteristics_en.pdf
Read 2026-09-30 (452,067 bytes, sha256 51be11487f875ea1a266af6d35704e92ab0543bd4ef4ce0684562cda4b4b9586).
product.tdk.com is behind Akamai: fetch with a desktop Chrome User-Agent, Accept/Accept-Language
headers and a product.tdk.com Referer. Test core stated by TDK for every table: T20 x 5 x 10
(no effective volume printed).

Grades read here (all newer than the 2022 catalogue read by extract-tdk-loss.py):
    PEL95, PEM95, PEH95  p4 table + "Core loss Temperature characteristics" (100kHz/200mT printed
                         in the figure), p5 "Core loss Bm characteristics (Sine wave data)" at
                         60 C (solid) and 100 C (dashed), 50/100/200/300 kHz.
    PC44, PCL47          p6 table + Pv-T figure (condition not printed in the figure; the p6 table
                         states 100kHz, 200mT and the curves pass through those numbers), p7 Pv-Bm.
    PC91                 p10 table + Pv-T figure, p11 Pv-Bm.

Method
------
The same as extract-tdk-loss.py, whose helpers are imported unchanged (axis calibration verified
by tick labels AND gridlines, curves are the PDF's own stroked paths, frequencies labelled by
loss order at a common Bm with the 60/100 C styles confirmed from the legend keys, physics order
checked, samples are exact reads of the drawn line, never extrapolated). Additions:

* Pv-T figures here draw one curve per MATERIAL; a curve is labelled by the legend key whose
  printed word is the material name (colour + dash must match exactly one curve).
* The title printed above each Pv-Bm figure must be the material name.
* PEH95's Pv-Bm figure (p5) is not stroked: its lines, dashes, gridlines and frame were converted
  to filled outlines. Its lines are read as the centreline of each outline (midpoint of the
  outline's upper and lower edge at the same abscissa; the outline must be 0.5..2.5 pt thick,
  i.e. a line and not an area), dashes as one centre point per dash; the gridlines are the thin
  grey filled bars. Everything else (calibration, labelling, table check) is identical.

Every accepted figure is checked against the printed Pcv table of the SAME catalogue (100 kHz,
200 mT at 25/60/100/120 C); a figure reading more than TABLE_TOL off any printed value it covers
is dropped whole (#1006). A grade ships only if an accepted figure reproduces a table value.

Catalogue data problems seen (recorded, not corrected):
* p10 (PC33/PC90/PC91) prints the Pcv row header as "500kHz, 50mT", but the p3 summary lists
  the same numbers (PC91 700/400, PC90 680/320) under "Pcv at 100kHz, 200mT", the 2022 catalogue
  prints PC90's identical 680/470/320/460 at 100kHz/200mT, and the p11 Pv-Bm figure of PC91 read
  at 100 kHz/200 mT reproduces the table. Stored as 100 kHz / 200 mT.
* PC44: the p3 summary prints Pcv 600 (25 C) / 300 (100 C), the p6 material table 620 / 320. The
  p6 table (the grade's own table) is used for the checks; both are reported.

Output: {material: [MAS volumetricLossesPoint, ...]} in SI units, waveform "sinusoidal" (the
figures state "Sine wave data"), origin "manufacturer".
"""
import argparse
import importlib.util
import json
import math
import os
import re
import sys

import fitz  # PyMuPDF

_spec = importlib.util.spec_from_file_location(
    "tdk2022", os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract-tdk-loss.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

TABLE_TOL = T.TABLE_TOL

# Printed material-table values (f Hz, B T, T degC, Pv kW/m^3): p4 (PEx95), p6 (PC44, PCL47), p10 (PC91).
_C = (25, 60, 100, 120)
TABLE = {
    "PEL95": [(100e3, 0.2, t, v) for t, v in zip(_C, (250, 270, 340, 390))],
    "PEM95": [(100e3, 0.2, t, v) for t, v in zip(_C, (440, 360, 320, 340))],
    "PEH95": [(100e3, 0.2, t, v) for t, v in zip(_C, (550, 460, 380, 360))],
    "PC44": [(100e3, 0.2, t, v) for t, v in zip(_C, (620, 420, 320, 450))],
    "PCL47": [(100e3, 0.2, t, v) for t, v in zip(_C, (530, 400, 280, 350))],
    "PC91": [(100e3, 0.2, t, v) for t, v in zip(_C, (700, 480, 400, 390))],
}
# The p3 summary table, reported beside the checks (not used to accept/reject).
SUMMARY_P3 = {"PC44": {25: 600, 100: 300}}

PVB = dict(kind="pv_b", x=("log", 10, 1000), y=("log", 1, 1e5), label="order",
           styles={False: 60, True: 100}, series=[50e3, 100e3, 200e3, 300e3], title=True)


def pvt(page, at, ymax, printed):
    return dict(kind="pv_t", page=page, at=at, x=("lin", 0, 160), y=("lin", 0, ymax),
                label="legendmat", cond=(100e3, 0.2), printed=printed)


FIGS = {
    "PEL95": [dict(PVB, page=5, at=(331.1, 141.4)), pvt(4, (65.2, 577.7), 800, True)],
    "PEM95": [dict(PVB, page=5, at=(66.9, 307.4)), pvt(4, (65.2, 577.7), 800, True)],
    "PEH95": [dict(PVB, page=5, at=(330.3, 307.3), outlined=True), pvt(4, (65.2, 577.7), 800, True)],
    "PC44": [dict(PVB, page=7, at=(66.9, 157.4)), pvt(6, (66.9, 585.6), 1000, False)],
    "PCL47": [dict(PVB, page=7, at=(66.9, 323.4)), pvt(6, (66.9, 585.6), 1000, False)],
    "PC91": [dict(PVB, page=11, at=(66.9, 323.4)), pvt(10, (66.9, 557.6), 1400, False)],
}


def norm_words(words):
    return [tuple(w[:4]) + (w[4].replace("℃", "°C"),) + tuple(w[5:]) for w in words]


# --------------------------------------------------------------------- outlined (filled) figures
def is_greyfill(c):
    return max(c) - min(c) < 0.03 and 0.6 < c[0] < 0.97


def poly_crossings(pts, xq):
    ys = []
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        if (x0 - xq) * (x1 - xq) <= 0 and x1 != x0:
            ys.append(y0 + (xq - x0) / (x1 - x0) * (y1 - y0))
    return ys


def centre_at(pts, xq):
    ys = poly_crossings(pts, xq)
    if len(ys) < 2:
        return None
    thick = max(ys) - min(ys)
    if not 0.5 <= thick <= 2.5:
        raise RuntimeError(f"outline at x={xq:.1f} is {thick:.2f} pt thick, not a line")
    return (xq, (max(ys) + min(ys)) / 2)


def read_outlined(pg, fig):
    """Box, gridlines, curves and legend keys of a figure whose strokes were converted to fills."""
    draws = pg.get_drawings()
    ax, ay = fig["at"]
    frame = [d for d in draws if d.get("fill") and d.get("color") is None and max(d["fill"]) < 0.05
             and abs(d["rect"].x0 - ax) < 3 and abs(d["rect"].y0 - ay) < 3 and d["rect"].width > 100]
    if len(frame) != 1:
        raise RuntimeError(f"{len(frame)} filled frames at {fig['at']}")
    # frame = outline of a 0.32 pt rectangle: the axis lines are its centre
    fr = frame[0]["rect"]
    subs = T.subpaths(frame[0])
    ys = sorted({round(p[1], 2) for s in subs for p in s[0]})
    half = (ys[1] - ys[0]) / 2 if len(ys) > 1 and ys[1] - ys[0] < 1 else 0.16
    box = fitz.Rect(fr.x0 + half, fr.y0 + half, fr.x1 - half, fr.y1 - half)
    inside = fitz.Rect(box.x0 - 1.5, box.y0 - 1.5, box.x1 + 1.5, box.y1 + 1.5)
    grid = {"h": set(), "v": set()}
    curves, swatches = [], []
    for d in draws:
        f = d.get("fill")
        if not f or d.get("color") is not None or not inside.contains(d["rect"]) or d is frame[0]:
            continue
        c = T.col(f)
        subs = T.subpaths(d)
        if is_greyfill(c):
            for dense, _ in subs:
                xs = [p[0] for p in dense]
                yy = [p[1] for p in dense]
                w, h = max(xs) - min(xs), max(yy) - min(yy)
                if h < 0.6 and w > 0.9 * box.width:
                    grid["h"].add(round((max(yy) + min(yy)) / 2, 2))
                elif w < 0.6 and h >= 1:
                    grid["v"].add(round((max(xs) + min(xs)) / 2, 2))
            continue
        if max(c) < 0.3 or min(c) > 0.9:   # black text marks / white label backgrounds
            continue
        if all(it[0] == "re" for it in d["items"]):
            # legend keys are drawn as filled bars; a dashed key is several bars
            r = d["rect"]
            if r.height < 2 and 8 < r.width < 30:
                swatches.append(dict(color=c, dashed=len(d["items"]) > 1, y=(r.y0 + r.y1) / 2, x1=r.x1))
            continue
        xs = [p[0] for s in subs for p in s[0]]
        yy = [p[1] for s in subs for p in s[0]]
        if not xs:
            continue
        w, h = max(xs) - min(xs), max(yy) - min(yy)
        dashed = len(subs) > 1
        if h < 2 and 8 < w < 30:
            swatches.append(dict(color=c, dashed=dashed, y=(max(yy) + min(yy)) / 2, x1=max(xs)))
            continue
        if w < 20:
            continue
        pts = []
        if dashed:
            for dense, _ in subs:
                x0, x1 = min(p[0] for p in dense), max(p[0] for p in dense)
                if x1 - x0 < 1.2:
                    continue
                p = centre_at(dense, (x0 + x1) / 2)
                if p:
                    pts.append(p)
        else:
            if len(subs) != 1:
                raise RuntimeError("solid outline with several subpaths")
            dense = subs[0][0]
            x0, x1 = min(xs) + 0.8, max(xs) - 0.8
            for i in range(60):
                p = centre_at(dense, x0 + (x1 - x0) * i / 59)
                if p:
                    pts.append(p)
        pts.sort()
        curves.append(dict(color=c, dashed=dashed, dense=pts, knots=pts, kind="outline"))
    grid = {k: sorted(v) for k, v in grid.items()}
    return box, grid, curves, swatches


# ------------------------------------------------------------------------------- figure reader
def read(pg, fig):
    words = norm_words(pg.get_text("words"))
    if fig.get("outlined"):
        box, grid, strokes, swatches = read_outlined(pg, fig)
        fig["_xa"] = T.Axis(fig["x"], box.x0, box.x1, False)
        fig["_ya"] = T.Axis(fig["y"], box.y0, box.y1, True)
        report = {"page": fig["page"], "kind": fig["kind"], "box": [round(v, 1) for v in box],
                  "outlined": True}
        T.check_axes(fig, box, words, grid, report)
    else:
        box, _w, strokes, swatches, report = T.read_figure(pg, fig)
    return box, words, strokes, swatches, report


def check_title(fig, box, words, mat):
    near = [w[4] for w in words if box.y0 - 40 < w[3] < box.y0 - 3 and box.x0 - 40 < w[0] < box.x0 + 40]
    if mat not in near:
        raise RuntimeError(f"title above the figure is {near}, not {mat}")


def label(fig, mat, words, strokes, swatches):
    if fig["label"] != "legendmat":
        return T.label_curves(fig, words, strokes, swatches)
    box = fig["_box"]
    inbox = " ".join(w[4] for w in words if box.contains(fitz.Rect(w[:4])))
    printed = T.parse_cond(inbox)
    f, B = fig["cond"]
    if fig["printed"]:
        if abs(printed.get("f", -1) - f) > 1 or abs(printed.get("B", -1) - B) > 1e-6:
            raise RuntimeError(f"figure prints {printed}, config says f={f} B={B}")
    elif printed.get("f") or printed.get("B"):
        raise RuntimeError(f"figure prints a condition {printed}, config assumes none is printed")
    # p4 draws its legend keys 7.4 pt long, below the 8 pt the 2022 reader takes as a key, so
    # the short straight horizontal strokes are separated here.
    def short(s):
        xs = [p[0] for p in s["dense"]]
        ys = [p[1] for p in s["dense"]]
        return len(s["knots"]) == 2 and max(ys) - min(ys) < 0.3 and max(xs) - min(xs) < 30
    swatches = swatches + [dict(color=s["color"], dashed=s["dashed"], y=s["dense"][0][1],
                                x1=max(p[0] for p in s["dense"])) for s in strokes if short(s)]
    strokes = [s for s in strokes if not short(s)]
    keys = [(sw["color"], sw["dashed"]) for sw in swatches
            if T.words_right_of(words, sw["x1"], sw["y"], dx=16).strip() == mat]
    if len(keys) != 1:
        raise RuntimeError(f"{len(keys)} legend keys print {mat}")
    hits = [s for s in strokes if (s["color"], s["dashed"]) == keys[0]]
    if len(hits) != 1:
        raise RuntimeError(f"{len(hits)} curves in the {mat} legend style {keys[0]}")
    others = [s for s in strokes if s["color"] == keys[0][0] and s is not hits[0]]
    if others:
        raise RuntimeError(f"{len(others)} other strokes share the {mat} colour")
    return [(dict(f=f, B=B), hits[0])]


def table_check(mat, all_curves):
    saved = T.TABLE
    T.TABLE = TABLE
    try:
        return T.table_check(mat, all_curves)
    finally:
        T.TABLE = saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    doc = fitz.open(a.pdf)
    result, report, failed = {}, {}, {}
    for mat, figs in FIGS.items():
        if a.only and mat not in a.only:
            continue
        try:
            pts, all_curves, figrep = [], [], []
            for fig in figs:
                fig = dict(fig)
                pg = doc[fig["page"] - 1]
                try:
                    box, words, strokes, swatches, rep = read(pg, fig)
                    fig["_page"], fig["_box"] = pg, box
                    if fig.get("title"):
                        check_title(fig, box, words, mat)
                    labelled = label(fig, mat, words, strokes, swatches)
                    p, curves = T.to_points(fig, labelled)
                    T.physics_check(fig, curves)
                except RuntimeError as e:
                    figrep.append(dict(page=fig["page"], kind=fig["kind"], REJECTED=str(e)))
                    continue
                keys = [tuple(sorted(c["cond"].items())) for c in curves]
                if len(set(keys)) != len(keys):
                    figrep.append(dict(page=fig["page"], kind=fig["kind"],
                                       REJECTED="two curves carry the same label"))
                    continue
                checks = table_check(mat, [(fig, c) for c in curves])
                rep["table"] = checks
                rep["curves"] = [dict(c["cond"], n=c["n"]) for c in curves]
                bad = [c for c in checks if abs(c["ratio"] - 1) > TABLE_TOL]
                if bad:
                    rep["REJECTED"] = f"{len(bad)} table check(s) beyond {TABLE_TOL:.0%}: " + ", ".join(
                        f"{c['T']}C {c['curve']} vs {c['table']}" for c in bad)
                    figrep.append(rep)
                    continue
                pts += p
                all_curves += [(fig, c) for c in curves]
                figrep.append(rep)
            checks = table_check(mat, all_curves)
            report[mat] = dict(points=len(pts), figures=figrep, table=checks,
                               summary_p3=SUMMARY_P3.get(mat))
            if not checks:
                raise RuntimeError("no accepted figure reproduces a printed table value")
            result[mat] = pts
        except RuntimeError as e:
            failed[mat] = str(e)
            report.setdefault(mat, {})["REJECTED"] = str(e)
    json.dump(result, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    for mat in FIGS:
        if a.only and mat not in a.only:
            continue
        r = report.get(mat, {})
        if mat in failed:
            print(f"{mat}: REJECTED -- {failed[mat]}")
            for f in r.get("figures", []):
                if "REJECTED" in f:
                    print(f"    figure dropped: p{f['page']} {f['kind']}: {f['REJECTED']}")
        else:
            ratios = [c["ratio"] for c in r["table"]]
            dropped = [f"p{f['page']} {f['kind']}: {f['REJECTED']}" for f in r["figures"] if "REJECTED" in f]
            print(f"{mat}: {r['points']} points, {len(r['table'])} table checks, "
                  f"ratio {min(ratios):.3f}..{max(ratios):.3f}"
                  + "".join(f"\n    figure dropped: {d}" for d in dropped))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
