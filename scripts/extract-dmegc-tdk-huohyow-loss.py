#!/usr/bin/env python3
"""Own core-loss points for DMEGC DMR25/DMR95B/DMR40B, TDK PC91/PC95 and Huoh Yow KL40/KL96W.

    python3 scripts/extract-dmegc-tdk-huohyow-loss.py \
        --tdk2026 ferrite_material_characteristics_en.pdf \
        --dmr95b "DMR95B Material Characteristics.pdf" \
        --dmegc-cat2017 1504577498-77035.pdf \
        --huohyow-page cat21.html --kl96w-pdf 1730384350fd276b.pdf --kl40-pdf 1730384410804327.pdf \
        --mas . --json points.json --report report.json --overlays overlay_dir

Each of these seven grades either had a loss model cloned from another grade or too few points of
its own to identify Steinmetz alpha/beta.  This script gathers every loss figure and table the makers
publish for them, reads the figures, gates them against the makers' own printed Pcv tables and writes
one MAS advanced-material patch per grade (the complete recommended point set).  It does not fit.

Sources (all the makers' own files except where stated)
--------------------------------------------------------
TDK   "Mn-Zn Ferrite -- Material characteristics", ferrite_material_characteristics_en, edition
      20260420 (18 pages, vector), https://product.tdk.com/system/files/dam/doc/product/ferrite/
      ferrite/ferrite-core/catalog/ferrite_material_characteristics_en.pdf
      sha256 51be11487f875ea1a266af6d35704e92ab0543bd4ef4ce0684562cda4b4b9586.
        PC95  p4 table (100 kHz/200 mT, 25/60/100/120 C) + p4 "Core loss Temperature
              characteristics" (curve per material, 100kHz/200mT printed) + p5 top-left
              "Core loss Bm characteristics" (titled PC95; 60 C solid / 100 C dashed; 50..300 kHz).
        PC91  p10 table + p10 Pv-T figure + p11 Pv-Bm figure (same layout).
      TDK publishes no separate PC95/PC91 material page: the product.tdk.com tech-library pages
      (pel95.html, pem95.html) only reprint the same 100 kHz/200 mT Pv-T comparison and core-shape
      data; pc95.html / pc91.html do not exist (404, 2026-11-05).
DMEGC "DMR95B Material Characteristics", DMR95B-REV.B 2019-04, 2 pages, vector,
      https://www.dmegc.de/uploads/20230401/DMR95B%20Material%20Characteristics.pdf
      sha256 f18cc047ebe32c02741b363f28f78eb6f0aec3167d24e1c8a47552def0f83427 (still linked from
      DMEGC's own chinadmegc.com MnZn power page, 2026-11-05).
      DMEGC MnZn catalogue 2017-04-06 (13 pages, vector) -- the only document with DMR25 and DMR40B.
      DMEGC no longer hosts it; the copy read is the dianyuan.com re-host
      https://www.dianyuan.com/upload/community/2017/09/05/1504577498-77035.pdf
      sha256 0ba812c9c6dde95e0289c4cec3c35532286f125c6ce046e4b48f1e88e66b7478.
      DMEGC's current MnZn catalogue (chinadmegc.com/uploads/20250515/锰锌目录.pdf.pdf, 84 pages)
      and the per-grade sheets on dmegc.de / chinadmegc.com no longer list DMR25 or DMR40B.
Huoh Yow MnZn category page https://www.huohyow.com.tw/en/index.php?c=category&id=21 (numeric
      Pcv table at 100 kHz/200 mT, 20/60/80/100/120 C) and the per-grade sheets it links
      (image-only one-page PDFs).  The link in the KL40 column (1730384410804327.pdf, link title
      "KM40T") serves the KM40T sheet (no loss data); the KM40T column links a byte-identical file.
      KL96W's sheet (1730384350fd276b.pdf) has a Pcv table at 25..140 C and one Pv-T curve at
      100 kHz/200 mT; it has no Pv-B or Pv-f figure.

Method (the house method of extract-tdk-loss.py / extract-dmegc-loss.py, whose readers are
imported unchanged)
-------------------------------------------------------------------------------------------
* Vector figures only, read from the PDF drawing operators (no pixels). Axes are calibrated on
  the gridlines; every tick label must sit on its calibrated position (LABEL_TOL) and every
  gridline on the declared lin/log scale (GRID_TOL). Residuals are in PDF points (1 pt = 1 px
  at 72 dpi) and reported per figure.
* Pv-B curves are labelled by legend/series order and the physics order is enforced (Pv rises
  with f at a common B); the TDK and DMEGC Pv-B lines are polylines whose vertices are the data
  markers, and the vertices are what is emitted.
* GATE (Alf, 2026-11): the printed Pcv tables are MAXIMUM values.  A figure is rejected when a
  curve reads more than 10 % ABOVE the table at a printed condition (ratio > 1.10); readings
  below the table are accepted.  All ratios are reported.
* An overlay PNG of every read curve on its figure is written to --overlays.
* Units: Pv W/m^3 (kW/m^3 x 1e3, mW/cm^3 x 1e3), B peak T, f Hz, T degC; sinusoidal, offset 0.
"""
import argparse
import hashlib
import html as htmlmod
import importlib.util
import json
import math
import os
import re
import sys

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = 1.10   # reject a figure whose curve reads > 10 % above the (maximum) table value
# Alf's decisions (2026-11-05) on figures that fail the gate at only part of their range:
# (grade, page, kind) -> highest temperature (degC) kept.  PC91 p10 Pv-T reads 542 vs 390 at
# 120 C (x1.39) but 0.967-1.005 at 25/60/100 C, so only its 25-100 C stretch is accepted.
PARTIAL_ACCEPT = {("PC91", 10, "pv_t"): 100.0}
# Alf's decision (2026-11-05): where two figures of one sheet print the same condition, keep
# BOTH readings (DMR95B Pv-T and Pv-B at 100 kHz/200 mT, 25/100 C) instead of dropping one.
KEEP_DUPLICATES = {"DMR95B"}


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T22 = load("tdk2022", "extract-tdk-loss.py")
T26 = load("tdk2026", "extract-tdk-loss-2026.py")
DM = load("dmegc", "extract-dmegc-loss.py")
DM.TABLE_TOL = float("inf")   # gate applied here (asymmetric), not inside the reader

SHA = {
    "tdk2026": "51be11487f875ea1a266af6d35704e92ab0543bd4ef4ce0684562cda4b4b9586",
    "dmr95b": "f18cc047ebe32c02741b363f28f78eb6f0aec3167d24e1c8a47552def0f83427",
    "dmegc_cat2017": "0ba812c9c6dde95e0289c4cec3c35532286f125c6ce046e4b48f1e88e66b7478",
    "kl96w_pdf": "b583135c03c50e9434d3105b39bca4f8bba1d254e97f0edf86348fe12c7e0bac",
    "kl40_pdf": "bb844bfc97b8f05c8462ca979a743a900a72bafd3289b1feedca0aaaea4a08c9",
}

URL = {
    "tdk2026": "https://product.tdk.com/system/files/dam/doc/product/ferrite/ferrite/ferrite-core/catalog/"
               "ferrite_material_characteristics_en.pdf",
    "dmr95b": "https://www.dmegc.de/uploads/20230401/DMR95B%20Material%20Characteristics.pdf",
    "dmegc_cat2017": "https://www.dianyuan.com/upload/community/2017/09/05/1504577498-77035.pdf",
    "huohyow_page": "https://www.huohyow.com.tw/en/index.php?c=category&id=21",
    "kl96w_pdf": "https://www.huohyow.com.tw/uploadfile/ueditor/file/202410/1730384350fd276b.pdf",
    "kl40_pdf": "https://www.huohyow.com.tw/uploadfile/ueditor/file/202410/1730384410804327.pdf",
}

# ---------------------------------------------------------------- printed tables (kW/m^3 at 100 kHz / 200 mT)
_C = (25, 60, 100, 120)
TDK_TABLE = {
    "PC95": [(100e3, 0.2, t, v) for t, v in zip(_C, (350, 300, 280, 330))],   # p4
    # p10 prints the row header "500kHz, 50mT"; the p3 summary lists PC91 700/400 under
    # "Pcv at 100kHz, 200mT" and the p11 Pv-Bm curves reproduce the numbers there
    # (see extract-tdk-loss-2026.py).  Taken as 100 kHz/200 mT.
    "PC91": [(100e3, 0.2, t, v) for t, v in zip(_C, (700, 480, 400, 390))],
}
TDK_FIGS = {
    "PC95": [dict(T26.PVB, page=5, at=(66.9, 141.3)), T26.pvt(4, (65.2, 577.7), 800, True)],
    "PC91": [dict(T26.PVB, page=11, at=(66.9, 323.4)), T26.pvt(10, (66.9, 557.6), 1400, False)],
}
# Huoh Yow category-page table, columns KL15 KL20 KL40 KL45 KL33W KL95W KL96W (asserted at run time)
HY_COLS = ["KL15", "KL20", "KL40", "KL45", "KL33W", "KL95W", "KL96W"]
HY_TEMPS = (20, 60, 80, 100, 120)
# KL96W's own sheet (image only, no text layer -- transcribed from the image of the file whose
# sha256 is SHA['kl96w_pdf']): Pcv 100kHz;200mT at 25/60/80/100/120/140 C.
KL96W_PDF_TABLE = {25: 400, 60: 360, 80: 345, 100: 340, 120: 380, 140: 440}

MANUFACTURER = {"DMR25": "DMEGC", "DMR95B": "DMEGC", "DMR40B": "DMEGC",
                "PC91": "TDK", "PC95": "TDK", "KL40": "Huoh Yow", "KL96W": "Huoh Yow"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def point(f, B, T, pv_w_m3):
    return T22.point(f, B, T, pv_w_m3)


def key(p):
    m = p["magneticFluxDensity"]
    return (m["frequency"], m["magneticFluxDensity"]["processed"]["peak"], p["temperature"])


# ----------------------------------------------------------------------------------- overlays
PALETTE = [(220, 30, 30), (20, 120, 220), (0, 150, 60), (200, 120, 0), (150, 0, 180), (0, 170, 170),
           (120, 70, 20), (230, 0, 140)]


def overlay(pg, rect, series, path, zoom=5):
    """series: [(label, [(xpage, ypage), ...] markers, [(xpage, ypage), ...] traced line or None)]."""
    from PIL import Image, ImageDraw
    clip = fitz.Rect(rect.x0 - 30, rect.y0 - 20, rect.x1 + 90, rect.y1 + 25)
    pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(img)
    tp = lambda x, y: ((x - clip.x0) * zoom, (y - clip.y0) * zoom)
    for i, (label, marks, line) in enumerate(series):
        c = PALETTE[i % len(PALETTE)]
        if line and len(line) > 1:
            d.line([tp(*p) for p in line], fill=c, width=1)
        for x, y in marks:
            X, Y = tp(x, y)
            d.ellipse([X - 6, Y - 6, X + 6, Y + 6], outline=c, width=2)
        if marks:
            X, Y = tp(*marks[-1])
            d.text((X + 8, Y - 6), label, fill=c)
    img.save(path)


# --------------------------------------------------------------------------------------- TDK
def tdk_grade(doc, mat, ovdir):
    """Read every TDK figure of `mat`; returns (accepted points, figure reports)."""
    saved = T26.TABLE
    T26.TABLE = dict(TDK_TABLE)
    pts, figrep = [], []
    try:
        for fig in TDK_FIGS[mat]:
            fig = dict(fig)
            pg = doc[fig["page"] - 1]
            try:
                box, words, strokes, swatches, rep = T26.read(pg, fig)
                fig["_page"], fig["_box"] = pg, box
                if fig.get("title"):
                    T26.check_title(fig, box, words, mat)
                labelled = T26.label(fig, mat, words, strokes, swatches)
                p, curves = T22.to_points(fig, labelled)
                T22.physics_check(fig, curves)
            except RuntimeError as e:
                figrep.append(dict(source="tdk2026", page=fig["page"], kind=fig["kind"], REJECTED=str(e)))
                continue
            keys = [tuple(sorted(c["cond"].items())) for c in curves]
            if len(set(keys)) != len(keys):
                figrep.append(dict(source="tdk2026", page=fig["page"], kind=fig["kind"],
                                   REJECTED="two curves carry the same label"))
                continue
            rep["source"] = "tdk2026"
            rep["table"] = T26.table_check(mat, [(fig, c) for c in curves])
            rep["curves"] = [dict(c["cond"], n=c["n"]) for c in curves]
            rep["points"] = len(p)
            if fig["kind"] == "pv_t":
                rep["_xy"] = curves[0]["xy"]
            # overlay: emitted points + traced line, page coordinates
            xa, ya = fig["_xa"], fig["_ya"]
            series = []
            for (cond, s), c in zip(labelled, curves):
                lab = " ".join(f"{k}={v:g}" for k, v in cond.items())
                samples = T22.emit_samples(fig, s)
                series.append((lab, [(xa.pos(x), ya.pos(y)) for x, y in samples if y is not None], s["dense"]))
            png = os.path.join(ovdir, f"{mat}_tdk2026_p{fig['page']}_{fig['kind']}.png")
            overlay(pg, box, series, png)
            rep["overlay"] = os.path.basename(png)
            bad = [c for c in rep["table"] if c["ratio"] > GATE]
            tmax = PARTIAL_ACCEPT.get((mat, fig["page"], fig["kind"]))
            if bad and tmax is not None and all(c["T"] > tmax for c in bad):
                kept = [q for q in p if q["temperature"] <= tmax]
                rep["PARTIAL"] = (f"accepted for T <= {tmax:g} C only ({len(kept)} of {len(p)} points); "
                                  + ", ".join(f"{c['T']} C reads {c['curve']} vs table {c['table']} (x{c['ratio']})"
                                              for c in bad) + " is excluded")
                rep["points"] = len(kept)
                pts += kept
            elif bad:
                rep["REJECTED"] = f"{len(bad)} table check(s) above {GATE}: " + ", ".join(
                    f"{c['T']} C reads {c['curve']} vs table {c['table']} (x{c['ratio']})" for c in bad)
            else:
                pts += p
            figrep.append(rep)
    finally:
        T26.TABLE = saved
    return pts, figrep


def check_text(text, needles, where):
    flat = re.sub(r"\s+", " ", text)
    for n in needles:
        if n not in flat:
            raise SystemExit(f"{where}: expected {n!r} in the page text")


# ------------------------------------------------------------------------------------- DMEGC
def dmegc(A, B, ovdir, report):
    DM.check_table_text(A[0].get_text(), ["DMR95B", "100kHz, 200mT", "350", "300", "360"], "DMR95B p1")
    DM.check_table_text(B[1].get_text(), ["DMR40B", "90**", "75**", "95**", "At 25 kHz/200mT"], "cat p2")
    DM.check_table_text(B[3].get_text(), ["DMR25", "700", "450", "400", "At 300kHz/100mT"], "cat p4")
    raw = {}
    out = {}

    # DMR95B p2 Pv-T (100 kHz/200 mT printed in the figure)
    s95, rep_t, _ = DM.dmr95b_pvt(A, raw)
    X, Y = DM.figure(A[1], fitz.Rect(80, 280, 290, 450), 20, 50, False, False, {})
    line = DM.polylines(A[1], fitz.Rect(80, 280, 290, 450), DM.RED)[0]
    png = os.path.join(ovdir, "DMR95B_sheet_p2_pv_t.png")
    overlay(A[1], fitz.Rect(80, 280, 290, 450), [("100kHz 200mT", [(X.pos(t), Y.pos(v)) for t, v in s95], line)], png)
    r = dict(source="dmr95b", page=2, kind="pv_t", calib=dict(x=rep_t["x"], y=rep_t["y"]),
             table=rep_t["table"], overlay=os.path.basename(png))
    bad = [c for c in r["table"] if c["ratio"] > GATE]
    pts95 = []
    if bad:
        r["REJECTED"] = str(bad)
    else:
        pts95 += [point(100e3, 0.2, t, v * 1e3) for t, v in s95]
        r["points"] = len(s95)
    figs95 = [r]

    # DMR95B p2 Pv-B (25 C solid / 100 C dashed, 25..500 kHz); vertices on the 50 mT gridlines
    pvb_pts, rep_b = DM.dmr95b_pvb(A, raw)
    box = fitz.Rect(330, 470, 530, 640)
    X, Y = DM.figure(A[1], box, 2, 1, True, True, {})
    series = []
    for lab, d in rep_b["curves"].items():
        series.append((lab, [(X.pos(b), Y.pos(v)) for b, v in sorted(d.items())], None))
    png = os.path.join(ovdir, "DMR95B_sheet_p2_pv_b.png")
    overlay(A[1], box, series, png)
    r = dict(source="dmr95b", page=2, kind="pv_b", calib=dict(x=rep_b["x"], y=rep_b["y"]),
             table=rep_b["table"], overlay=os.path.basename(png),
             curves={k: len(v) for k, v in rep_b["curves"].items()})
    bad = [c for c in r["table"] if c["ratio"] > GATE]
    if bad:
        r["REJECTED"] = str(bad)
    else:
        pts95 += pvb_pts
        r["points"] = len(pvb_pts)
        r["note"] = ("previously rejected under the symmetric +-10 % gate (25 C reads 0.883 x table); "
                     "accepted under the maximum-value gate")
    figs95.append(r)
    out["DMR95B"] = (pts95, figs95)

    # catalogue p5 Pv-T: DMR25 curve (figure checked on all its grades with tables)
    X5, Y5, c5, f5, rep5 = DM.catalogue_pvt(B, 4, ["DMR25", "DMR95", "DMR95B", "DMR96", "DMR96A"], raw, "B_p5")
    s25 = DM.pvt_samples(X5, Y5, c5["DMR25"])
    png = os.path.join(ovdir, "DMR25_cat2017_p5_pv_t.png")
    overlay(B[4], fitz.Rect(150, 130, 450, 365),
            [("DMR25", [(X5.pos(t), Y5.pos(v)) for t, v in s25], c5["DMR25"])], png)
    figchk = {nm: rep5["table"][nm] for nm in ("DMR25", "DMR95", "DMR95B", "DMR96")}
    r = dict(source="dmegc_cat2017", page=5, kind="pv_t", calib=dict(x=rep5["x"], y=rep5["y"]),
             table=figchk["DMR25"], other_grades_on_figure={k: v for k, v in figchk.items() if k != "DMR25"},
             overlay=os.path.basename(png),
             condition="figure prints none; the table row is 100kHz/200mT and the curve reproduces it")
    bad = [c for c in figchk["DMR25"] if c["ratio"] > GATE]
    if bad:
        r["REJECTED"] = str(bad)
        pts25 = []
    else:
        pts25 = [point(100e3, 0.2, t, v * 1e3) for t, v in s25]
        r["points"] = len(pts25)
    out["DMR25"] = (pts25, [r])

    # catalogue p3 Pv-T: DMR40B curve vs its only printed values (25 kHz/200 mT)
    X3, Y3, c3, f3, rep3 = DM.catalogue_pvt(B, 2, ["DMR40", "DMR44", "DMR47", "DMR40B"], raw, "B_p3")
    s40 = DM.pvt_samples(X3, Y3, c3["DMR40B"])
    png = os.path.join(ovdir, "DMR40B_cat2017_p3_pv_t.png")
    overlay(B[2], fitz.Rect(150, 130, 450, 365),
            [("DMR40B", [(X3.pos(t), Y3.pos(v)) for t, v in s40], c3["DMR40B"])], png)
    r = dict(source="dmegc_cat2017", page=3, kind="pv_t", calib=dict(x=rep3["x"], y=rep3["y"]),
             table=rep3["table"]["DMR40B"], overlay=os.path.basename(png),
             other_grades_on_figure={k: rep3["table"][k] for k in ("DMR40", "DMR44", "DMR47")})
    bad = [c for c in r["table"] if c["ratio"] > GATE]
    r["REJECTED"] = ("figure prints no condition; DMR40B's only printed values are at 25 kHz/200 mT and the "
                     "curve reads %s x them (it sits with the 100 kHz/200 mT curves of DMR40/44/47)"
                     % [c["ratio"] for c in r["table"]]) if bad else None
    pts40 = [point(25e3, 0.2, t, v * 1e3) for t, v in sorted(DM.TABLE_CAT["DMR40B"].items())]
    out["DMR40B"] = (pts40, [r, dict(source="dmegc_cat2017", page=2, kind="table",
                                     note="Core loss ** At 25 kHz/200mT, 25/60/100/120 C (printed values)",
                                     points=len(pts40))])
    return out


# ---------------------------------------------------------------------------------- Huoh Yow
def huohyow(page_html, kl96w_pdf, kl40_pdf):
    flat = " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", open(page_html, encoding="utf-8").read())).split())
    hdr = "Characteristics Symbol Settings Unit " + " ".join(HY_COLS)
    if hdr not in flat:
        raise SystemExit("Huoh Yow page: column header changed")
    rows = {}
    pat = {20: r"Pcv 20℃ kW/m3 ", 60: r" 60℃ ", 80: r" 80℃ ", 100: r" 100℃ ", 120: r" 120℃ "}
    i = flat.index("100KHz 200mT＊500KHz 50mT Pcv 20℃")
    seg = flat[i:i + 900]
    for t, p in pat.items():
        m = re.search(re.escape(p.strip()) + r"\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)" if t != 20
                      else r"Pcv 20℃ kW/m3 (\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", seg)
        if not m:
            raise SystemExit(f"Huoh Yow page: no Pcv row at {t} C")
        rows[t] = dict(zip(HY_COLS, m.groups()))
    page = {g: {t: float(rows[t][g]) for t in HY_TEMPS} for g in ("KL40", "KL96W")}
    if sha256(kl96w_pdf) != SHA["kl96w_pdf"]:
        raise SystemExit("KL96W sheet changed: re-transcribe KL96W_PDF_TABLE from its image")
    if sha256(kl40_pdf) != SHA["kl40_pdf"]:
        raise SystemExit("the KL40-column sheet changed: re-check whether it is now the KL40 sheet")
    out = {}
    out["KL40"] = ([point(100e3, 0.2, t, v * 1e3) for t, v in page["KL40"].items()],
                   [dict(source="huohyow_page", kind="table", values=page["KL40"],
                         note="KL40 has no sheet of its own online: its link serves the KM40T sheet "
                              "(sha256 %s, no loss data)" % SHA["kl40_pdf"])])
    # KL96W: the sheet's table (25..140 C) supersedes the page's (20..120 C); the five common values agree
    agree = {t: (page["KL96W"][tp], KL96W_PDF_TABLE[t]) for tp, t in zip(HY_TEMPS, (25, 60, 80, 100, 120))}
    if any(a != b for a, b in agree.values()):
        raise SystemExit(f"KL96W page vs sheet values differ: {agree}")
    out["KL96W"] = ([point(100e3, 0.2, t, v * 1e3) for t, v in sorted(KL96W_PDF_TABLE.items())],
                    [dict(source="kl96w_pdf", kind="table", values=KL96W_PDF_TABLE,
                          note="sheet prints the first row at 25 C, the category page at 20 C (same 400); "
                               "the sheet adds 140 C = 440. Its Pv-T figure is drawn at the same "
                               "100 kHz/200 mT through these values and is not digitised (no f/B "
                               "information beyond the table)."),
                     dict(source="huohyow_page", kind="table", values=page["KL96W"])])
    return out


# ------------------------------------------------------------------------- existing MAS points
def existing_points(mas):
    out = {}
    for line in open(os.path.join(mas, "data", "advanced_core_materials.ndjson")):
        r = json.loads(line)
        if r["name"] in MANUFACTURER:
            pts = [p for m in r.get("volumetricLosses", {}).get("default", []) if isinstance(m, list) for p in m]
            out[r["name"]] = pts
    return out


def compare_existing(old, new):
    """Each stored point vs the new point at the same (f, B, T) (B,T within rounding)."""
    res = []
    for p in old:
        f, B, T = key(p)
        hit = [q for q in new if abs(key(q)[0] - f) < 1 and abs(key(q)[1] - B) <= 2e-4 * max(1, B / 0.2)
               and abs(key(q)[2] - T) < 0.05]
        res.append(dict(f=f, B=B, T=T, old=p["value"], new=hit[0]["value"] if hit else None,
                        ratio=round(hit[0]["value"] / p["value"], 4) if hit else None))
    return res


def validate(records, mas):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    import glob
    res = []
    for base in [os.path.join(mas, "schemas"), os.path.join(mas, "..", "PEAS", "schemas")]:
        for p in glob.glob(f"{base}/**/*.json", recursive=True):
            try:
                s = json.load(open(p))
            except Exception:
                continue
            if isinstance(s, dict) and "$id" in s:
                res.append((s["$id"], Resource.from_contents(s)))
    reg = Registry().with_resources(res)
    v = Draft202012Validator(json.load(open(os.path.join(mas, "schemas/magnetic/core/material.json"))), registry=reg)
    base = {}
    for line in open(os.path.join(mas, "data/core_materials.ndjson")):
        r = json.loads(line)
        base[r["name"]] = r
    out = {}
    for rec in records:
        b = base.get(rec["name"])
        if b is None:
            out[rec["name"]] = ["no base record"]
            continue
        if b["manufacturerInfo"]["name"] != rec["manufacturerInfo"]["name"]:
            out[rec["name"]] = [f"manufacturer {rec['manufacturerInfo']['name']} != base {b['manufacturerInfo']['name']}"]
            continue
        merged = json.loads(json.dumps(b))
        merged.setdefault("volumetricLosses", {}).setdefault("default", []).extend(rec["volumetricLosses"]["default"])
        out[rec["name"]] = [f"{list(e.absolute_path)}: {e.message[:120]}" for e in v.iter_errors(merged)]
    return out


def coverage(pts):
    fs = sorted({key(p)[0] for p in pts})
    Bs = sorted({key(p)[1] for p in pts})
    Ts = sorted({key(p)[2] for p in pts})
    # B values that share a curve differ only by rounding; count distinct to 1 mT
    Bm = sorted({round(b * 1000) for b in Bs})
    return dict(n=len(pts), f=fs, B_mT=Bm, T=Ts, nf=len(fs), nB=len(Bm), nT=len(Ts))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tdk2026", required=True)
    ap.add_argument("--dmr95b", required=True)
    ap.add_argument("--dmegc-cat2017", required=True)
    ap.add_argument("--huohyow-page", required=True)
    ap.add_argument("--kl96w-pdf", required=True)
    ap.add_argument("--kl40-pdf", required=True)
    ap.add_argument("--mas", required=True, help="MAS checkout (data/, schemas/; ../PEAS/schemas for $refs)")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--overlays", required=True)
    a = ap.parse_args()
    os.makedirs(a.overlays, exist_ok=True)
    for k in ("tdk2026", "dmr95b", "dmegc_cat2017"):
        h = sha256(getattr(a, k))
        if h != SHA[k]:
            print(f"WARNING {k}: sha256 {h} differs from the file read when this script was written", file=sys.stderr)

    tdk = fitz.open(a.tdk2026)
    check_text(tdk[3].get_text(), ["PC95", "100kHz, 200mT", "350", "300", "280", "330"], "TDK p4")
    check_text(tdk[9].get_text(), ["PC91", "700", "480", "400", "390"], "TDK p10")

    grades = {}
    for mat in ("PC95", "PC91"):
        grades[mat] = tdk_grade(tdk, mat, a.overlays)
    grades.update(dmegc(fitz.open(a.dmr95b), fitz.open(a.dmegc_cat2017), a.overlays, {}))
    grades.update(huohyow(a.huohyow_page, a.kl96w_pdf, a.kl40_pdf))

    old = existing_points(a.mas)
    records, report = [], {}
    for mat in ("DMR25", "DMR95B", "DMR40B", "PC91", "PC95", "KL40", "KL96W"):
        pts, figs = grades[mat]
        cmp_ = compare_existing(old.get(mat, []), pts)
        # stored points with no new point at the same condition: read them off any Pv-T curve of the
        # same f/B that was read here (accepted or not), to say whether they are consistent with it
        for c in cmp_:
            if c["new"] is not None:
                continue
            for f in figs:
                if f.get("kind") == "pv_t" and f.get("_xy") and abs(c["f"] - 100e3) < 1 and abs(c["B"] - 0.2) < 1e-6:
                    v = T22.curve_value(f["_xy"], c["T"], False, False)
                    if v is not None:
                        c["on_curve"] = f"{f['source']} p{f['page']} pv_t{' (rejected)' if f.get('REJECTED') else ''}"
                        c["curve"] = round(v * 1e3)
                        c["ratio_curve"] = round(v * 1e3 / c["old"], 4)
        # Two figures of one sheet can print the same condition (DMR95B: Pv-T and the 100 kHz Pv-B
        # vertex at 200 mT, 25/100 C). The FIRST figure read keeps it (the Pv-T, which is the figure
        # drawn through the printed table); the other reading is dropped and reported, unless the
        # grade is in KEEP_DUPLICATES, where both readings are kept and listed.
        seen, kept, dup = {}, [], []
        for p in pts:
            k = key(p)
            if k in seen and mat in KEEP_DUPLICATES:
                dup.append(dict(f=k[0], B=k[1], T=k[2], values=[seen[k]["value"], p["value"]],
                                both_kept=True))
                kept.append(p)
                continue
            if k in seen:
                dup.append(dict(f=k[0], B=k[1], T=k[2], kept=seen[k]["value"], dropped=p["value"]))
                continue
            seen[k] = p
            kept.append(p)
        pts = sorted(kept, key=key)
        report[mat] = dict(manufacturer=MANUFACTURER[mat], figures=figs, coverage=coverage(pts),
                           existing=dict(n=len(old.get(mat, [])), vs_new=cmp_), duplicates=dup)
        if len(pts) < 4:
            report[mat]["NOT_EMITTED"] = f"only {len(pts)} points"
            continue
        records.append({"name": mat, "manufacturerInfo": {"name": MANUFACTURER[mat]},
                        "volumetricLosses": {"default": [pts]}})
    for mat in report:
        for f in report[mat]["figures"]:
            f.pop("_xy", None)
    report["_validation"] = validate(records, a.mas)
    report["_sources"] = {k: dict(url=URL[k], sha256=SHA.get(k)) for k in URL}
    json.dump(records, open(a.json, "w"), indent=1)
    json.dump(report, open(a.report, "w"), indent=1)
    for mat, r in report.items():
        if mat.startswith("_"):
            continue
        c = r["coverage"]
        print(f"{mat:7s} {c['n']:3d} pts  f={[x / 1e3 for x in c['f']]} kHz  nB={c['nB']}  T={c['T']}")
        for f in r["figures"]:
            tab = ", ".join(f"{t['T']}C x{t['ratio']}" for t in f.get("table", []) or [])
            st = ("REJECTED: " + f["REJECTED"]) if f.get("REJECTED") else (("PARTIAL: " + f["PARTIAL"]) if f.get("PARTIAL") else "accepted")
            print(f"    {f['source']} p{f.get('page', '-')} {f['kind']}: {st}  [{tab}]")
    bad = {k: v for k, v in report["_validation"].items() if v}
    print("schema:", "all valid" if not bad else bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
