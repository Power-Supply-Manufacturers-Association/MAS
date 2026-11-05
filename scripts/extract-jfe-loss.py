#!/usr/bin/env python3
"""Own core-loss points for JFE Ferrite MB1, MB1H, MB3, MB4, MBT1 and MBT2.

    python3 scripts/extract-jfe-loss.py \
        --ed2017 20180613191512_products_pdf_003.pdf \
        --ed2003 20040630004611_eng_product_pdf_No.003.pdf \
        --current 003.pdf \
        --mas . --json points.json --report report.json --overlays overlay_dir [--gate 1.10]

MAS stores all six grades with one cloned Steinmetz alpha/beta.  This script reads every loss
figure JFE publishes for them, gates each figure against JFE's own printed Pcv table and writes one
MAS advanced-material patch per grade (the complete recommended point set).  It does not fit.

Sources (all JFE Ferrite's own sheet "Low Power Loss Material Characteristics", catalogue pages 3-5)
----------------------------------------------------------------------------------------------------
current  https://www.jfe-frt.com/products/pdf/003.pdf (linked from https://www.jfe-frt.com/products/
         index.html, 2026-11-05), built 2024-09-26 from a DocuWorks file; 3 pages, vector, but every
         character is an outline (no text layer) and the curves are filled outlines.  Table: MB1, MB1H,
         MB3, MB4, MBT1, MBT2.  Figures: MB1H, MB3, MB4, MBT1 (Pv-T and Pv-B at 100 C).  NO figure for
         MB1 or MBT2.  Used for the table (read by eye; identical to ed2017's text layer) and as a
         geometric cross-check of ed2017's curves (the same drawings; see --current below).
ed2017   the same URL as archived by the Wayback Machine on 2018-06-13
         (http://web.archive.org/web/20180613191512id_/https://www.jfe-frt.com/products/pdf/003.pdf),
         PDF created 2017-04-12, 3 pages, vector WITH a text layer.  Same tables and figures as current.
         This is the edition that is digitised for MB1H, MB3, MB4, MBT1.
ed2003   http://www.jfe-frt.com/eng/product/pdf/No.003.pdf as archived 2004-06-30
         (http://web.archive.org/web/20040630004611id_/http://www.jfe-frt.com:80/eng/product/pdf/No.003.pdf),
         PDF created 2003-02-02, 3 pages, vector with a text layer.  Table and figures for MB1, MB3, MB4,
         MBT1 (MB1H and MBT2 did not exist yet).  The only published MB1 loss figures.  The Japanese-path
         copy (/product/pdf/003.pdf, archived 2004-10-20) has the same page drawings and text.

Method (house method, vector only)
----------------------------------
* Axes are calibrated on the gridlines.  Each tick label (a text token, split at character level
  because the 2017 layer merges e.g. the y "1" and x "10" into one word "110") anchors the nearest
  gridline; linear axes are fitted on those anchors and every other gridline must sit on a multiple
  of the grid step; log axes fit the decade lines and every minor line is assigned m = 2..9.
  Gates: label within LABEL_TOL of its line, every assigned line within GRID_TOL of the straight
  scale, at most MAX_UNASSIGNED unassignable lines per axis, piecewise vs straight reading of every
  output point within PIECEWISE_TOL.  Values are read piecewise between the gridlines around them.
* Curves are the 1 pt strokes inside the plot frame, split into sub-paths at discontinuities.
  Each curve is labelled by the text token nearest its right-hand end (one-to-one, minimum total
  distance).  Physics order is checked: at a common B, Pv rises with f (Pv-B), and at a common B the
  Pv-T curves are ordered by f.
* Points: Pv-T at the drawn start, every multiple of 10 C strictly inside and the drawn end; Pv-B at
  the drawn start, any interior vertex, 100 mT and 200 mT when strictly inside, and the drawn end.
  No extrapolation, no interpolation between figures.  A point where a line meets the plot frame
  is flagged (it is the exact read of the visible line where it leaves the chart).
* GATE (Alf, 2026-11): the printed Pcv(100 kHz, 200 mT) table values are MAXIMA.  A figure is
  rejected when a curve reads more than GATE (10 %) ABOVE the max at a printed condition.  Pv-T: the
  100 kHz/200 mT curve at 23/60/100/120 C.  Pv-B (100 C): the 100 kHz curve at 200 mT vs the 100 C
  max.  The ratio to the typical value (printed in 2017/current as "typ(max)") is reported too.
* KEEP BOTH readings (Alf, 2026-11-05) where two figures of the same grade share a condition: the
  2003 and 2017 figures of MB3, MB4, MBT1 are different drawings (compared below) and both are kept.
* Units: Pv W/m^3 (kW/m^3 x 1e3), B peak T, f Hz, T degC; sinusoidal, offset 0.
"""
import argparse
import glob
import hashlib
import itertools
import json
import math
import os
import re
import sys

import fitz  # PyMuPDF

GATE = 1.10
LABEL_TOL = 1.5        # pt, tick label centre to its gridline
GRID_TOL = 1.5         # pt, gridline to the straight (lin or log) scale
MAX_UNASSIGNED = 3     # per axis
PIECEWISE_TOL = 0.06   # relative, piecewise vs straight reading of an output point
FRAME_TOL = 0.6        # pt, a point this close to the frame is a frame-edge point
# Alf's decision (2026-11-05): MB1's 2003 Pv-B (100 C) 25 and 50 kHz lines disagree with JFE's own
# Pv-T figure of the same sheet at the same condition (Pv-B / Pv-T = 2.03 at 25 kHz/200 mT and 1.24
# at 50 kHz/200 mT; MB3/MB4/MBT1 agree within 0.90-1.12).  Those two lines are dropped; the other
# Pv-B lines and the whole Pv-T figure are kept.
DROP_LINES = {("MB1", "ed2003", "pv_b"): {
    25e3: "Pv-B/Pv-T = 2.03 at 25 kHz/200 mT, 100 C (59.0 vs 29.1 kW/m3)",
    50e3: "Pv-B/Pv-T = 1.24 at 50 kHz/200 mT, 100 C (144 vs 116 kW/m3)"}}
SAME_DRAWING_TOL = 0.005  # relative: two editions' readings this close are one re-published drawing

SHA = {
    "current": "1386d030b6530e6d5074607cb3d8c197fce4904bd48e4e90bb5215a4d94a0e25",
    "ed2017": "0a0bfe415ac3cbcd7a111c36bb874258c62f713b4ae170d5923ed1e8515e60d4",
    "ed2003": "ef8b762bf9e278b86710661a79ffcf27341cba610c03d74ee4a764aaae10ea71",
}
URL = {
    "current": "https://www.jfe-frt.com/products/pdf/003.pdf",
    "ed2017": "http://web.archive.org/web/20180613191512id_/https://www.jfe-frt.com/products/pdf/003.pdf",
    "ed2003": "http://web.archive.org/web/20040630004611id_/http://www.jfe-frt.com:80/eng/product/pdf/No.003.pdf",
}

TEMPS = (23, 60, 100, 120)
# Pcv(100 kHz, 200 mT) kW/m^3: (typical, max).  ed2017 is checked against its text layer at run time;
# the current edition prints the same numbers (read by eye from its outline glyphs).
TABLE_2017 = {
    "MB1": [(870, 900), (600, 620), (420, 440), (475, 490)],
    "MB1H": [(980, 1070), (600, 670), (380, 450), (550, 630)],
    "MB3": [(650, 700), (440, 500), (350, 410), (390, 500)],
    "MB4": [(575, 630), (375, 430), (270, 300), (350, 400)],
    "MBT1": [(395, 450), (325, 430), (340, 380), (390, 430)],
    "MBT2": [(370, 425), (310, 365), (300, 340), (370, 410)],
}
# ed2003 prints maxima only (same maxima as 2017)
TABLE_2003 = {"MB1": (900, 620, 440, 490), "MB3": (700, 500, 410, 500),
              "MB4": (630, 430, 300, 400), "MBT1": (450, 430, 380, 430)}

# figure definitions: page index (0-based) and a point inside the plot frame
FIGS = {
    "ed2017": [
        ("MB1H", 1, "pv_t", (150, 180)), ("MB3", 1, "pv_t", (420, 180)),
        ("MB1H", 1, "pv_b", (150, 600)), ("MB3", 1, "pv_b", (420, 600)),
        ("MB4", 2, "pv_t", (150, 180)), ("MBT1", 2, "pv_t", (420, 180)),
        ("MB4", 2, "pv_b", (150, 600)), ("MBT1", 2, "pv_b", (420, 600)),
    ],
    "ed2003": [
        ("MB1", 1, "pv_t", (150, 180)), ("MB3", 1, "pv_t", (420, 180)),
        ("MB1", 1, "pv_b", (150, 600)), ("MB3", 1, "pv_b", (420, 600)),
        ("MB4", 2, "pv_t", (150, 180)), ("MBT1", 2, "pv_t", (420, 180)),
        ("MB4", 2, "pv_b", (150, 600)), ("MBT1", 2, "pv_b", (420, 600)),
    ],
}
AXES = {  # kind -> (x lin/log, y lin/log, x tick values, y tick values)
    "pv_t": ("lin", "lin", None, None),
    "pv_b": ("log", "log", (1, 10, 100, 1000), (1, 10, 100, 1000, 10000, 100000)),
}
GRADES = ("MB1", "MB1H", "MB3", "MB4", "MBT1", "MBT2")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def point(f, B, T, pv):
    sig = lambda v, n=4: float(f"{v:.{n}g}")
    return {"magneticFluxDensity": {"frequency": sig(f, 6), "magneticFluxDensity": {"processed": {
        "label": "sinusoidal", "peak": sig(B), "offset": 0.0}}},
        "temperature": round(T, 1), "value": sig(pv), "origin": "manufacturer"}


def key(p):
    m = p["magneticFluxDensity"]
    return (m["frequency"], m["magneticFluxDensity"]["processed"]["peak"], p["temperature"])


# ------------------------------------------------------------------------------- page geometry
def tokens(pg):
    """Text tokens split at character level: (text, x0, y0, x1, y1)."""
    out = []
    raw = pg.get_text("rawdict")
    for b in raw["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                cur = None
                for ch in sp["chars"]:
                    x0, y0, x1, y1 = ch["bbox"]
                    c = ch["c"]
                    if c.isspace():
                        if cur:
                            out.append(cur)
                        cur = None
                        continue
                    if cur and (x0 - cur[3] > 1.2 or abs((y0 + y1) / 2 - (cur[2] + cur[4]) / 2) > 2.0):
                        out.append(cur)
                        cur = None
                    if cur is None:
                        cur = [c, x0, y0, x1, y1]
                    else:
                        cur[0] += c
                        cur[3] = max(cur[3], x1)
                        cur[2] = min(cur[2], y0)
                        cur[4] = max(cur[4], y1)
                if cur:
                    out.append(cur)
    return [tuple(t) for t in out]


def bez(p0, p1, p2, p3, n=48):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        pts.append((a * p0.x + b * p1.x + c * p2.x + d * p3.x, a * p0.y + b * p1.y + c * p2.y + d * p3.y))
    return pts


def subpaths(d):
    """Split a drawing into continuous sub-paths; each: dict(dense=[(x,y)], verts=[(x,y)], kinds)."""
    out, cur = [], None
    for it in d["items"]:
        if it[0] not in ("l", "c"):
            continue
        p0 = it[1]
        if cur is None or math.hypot(p0.x - cur["dense"][-1][0], p0.y - cur["dense"][-1][1]) > 0.05:
            cur = dict(dense=[(p0.x, p0.y)], verts=[(p0.x, p0.y)], kinds="")
            out.append(cur)
        if it[0] == "l":
            q = it[2]
            cur["dense"].append((q.x, q.y))
            cur["verts"].append((q.x, q.y))
        else:
            cur["dense"] += bez(*it[1:5])[1:]
            cur["verts"].append((it[4].x, it[4].y))
        cur["kinds"] += it[0]
    return out


def find_frame(pg, at):
    best = None
    for d in pg.get_drawings():
        if d.get("type") not in ("s", "fs") or (d.get("width") or 0) > 0.7:
            continue
        for it in d["items"]:
            if it[0] == "re" and it[1].contains(fitz.Point(*at)):
                r = it[1]
                if best is None or r.get_area() < best.get_area():
                    best = fitz.Rect(r)
    if best is None:
        raise RuntimeError(f"no plot frame around {at}")
    return best


def gridlines(pg, box):
    xs, ys = [box.x0, box.x1], [box.y0, box.y1]
    for d in pg.get_drawings():
        if d.get("type") != "s" or (d.get("width") or 0) > 0.7:
            continue
        for it in d["items"]:
            if it[0] != "l":
                continue
            a, b = it[1], it[2]
            if abs(a.x - b.x) < 0.05 and box.x0 - 0.3 <= a.x <= box.x1 + 0.3 \
                    and min(a.y, b.y) <= box.y0 + 1 and max(a.y, b.y) >= box.y1 - 1:
                xs.append(a.x)
            elif abs(a.y - b.y) < 0.05 and box.y0 - 0.3 <= a.y <= box.y1 + 0.3 \
                    and min(a.x, b.x) <= box.x0 + 1 and max(a.x, b.x) >= box.x1 - 1:
                ys.append(a.y)
    dedup = lambda v: [x for i, x in enumerate(sorted(v)) if i == 0 or x - sorted(v)[i - 1] > 0.3]
    return dedup(xs), dedup(ys)


def curves(pg, box):
    out = []
    for d in pg.get_drawings():
        if d.get("type") != "s" or (d.get("width") or 0) < 0.9 or d.get("dashes") not in (None, "[] 0"):
            continue
        r = d["rect"]
        if not fitz.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1).contains(r):
            continue
        out += [s for s in subpaths(d) if len(s["dense"]) > 1]
    return out


# ------------------------------------------------------------------------------------- axes
class Axis:
    def __init__(self, kind, grid, a, b):
        self.kind, self.grid, self.a, self.b = kind, sorted(grid), a, b   # grid [(pos, value)]

    def _t(self, v):
        return math.log10(v) if self.kind == "log" else v

    def _ti(self, t):
        return 10 ** t if self.kind == "log" else t

    def val(self, pos):
        g = self.grid
        asc = g[-1][1] > g[0][1]
        for (p0, v0), (p1, v1) in zip(g, g[1:]):
            if min(p0, p1) - 1e-6 <= pos <= max(p0, p1) + 1e-6:
                return self._ti(self._t(v0) + (pos - p0) / (p1 - p0) * (self._t(v1) - self._t(v0)))
        raise RuntimeError(f"position {pos:.2f} outside the calibrated grid")

    def pos(self, v):
        g = self.grid
        t = self._t(v)
        for (p0, v0), (p1, v1) in zip(g, g[1:]):
            t0, t1 = self._t(v0), self._t(v1)
            if min(t0, t1) - 1e-12 <= t <= max(t0, t1) + 1e-12:
                return p0 + (t - t0) / (t1 - t0) * (p1 - p0)
        raise RuntimeError(f"value {v} outside the calibrated grid")

    def straight(self, pos):
        return self._ti((pos - self.a) / self.b)


def lsq(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def calibrate(kind, lines, ticks, rep, name):
    """ticks: [(value, centre pos)].  Returns Axis; fills rep[name]."""
    if len(ticks) < 2:
        raise RuntimeError(f"{name}: fewer than 2 tick labels")
    anchors, label_off = {}, 0.0
    for v, c in ticks:
        g = min(lines, key=lambda p: abs(p - c))
        label_off = max(label_off, abs(g - c))
        if abs(g - c) > LABEL_TOL:
            raise RuntimeError(f"{name}: tick {v} sits {abs(g - c):.2f} pt from the nearest line")
        anchors[v] = g
    t = (lambda v: math.log10(v)) if kind == "log" else (lambda v: v)
    vs = sorted(anchors)
    a, b = lsq([t(v) for v in vs], [anchors[v] for v in vs])  # pos = a + b t
    # a label can sit half-way between its line and a minor line (MB1H 2017 Pv-B "100" is 0.64 pt
    # from the decade line and 0.62 pt from the m=9 line): re-anchor every label on the line nearest
    # the straight scale through all labels, then refit
    centre = dict(ticks)
    for _ in range(2):
        for v in vs:
            anchors[v] = min(lines, key=lambda p: abs(p - (a + b * t(v))))
        a, b = lsq([t(v) for v in vs], [anchors[v] for v in vs])
    label_off = max(abs(anchors[v] - centre[v]) for v in vs)
    if label_off > LABEL_TOL:
        raise RuntimeError(f"{name}: a tick label sits {label_off:.2f} pt from its line")
    dec_res = max(abs(anchors[v] - (a + b * t(v))) for v in vs)
    if dec_res > GRID_TOL:
        raise RuntimeError(f"{name}: tick-anchored lines {dec_res:.2f} pt off one straight scale")
    if kind == "lin":
        # grid step: lines strictly between two adjacent anchors
        v0, v1 = vs[0], vs[1]
        n = sum(1 for p in lines if min(anchors[v0], anchors[v1]) + 0.3 < p < max(anchors[v0], anchors[v1]) - 0.3)
        step = (v1 - v0) / (n + 1)
    grid, unassigned, worst = {}, [], 0.0
    for p in lines:
        te = (p - a) / b
        if kind == "log":
            ve = 10 ** te
            dec = math.floor(math.log10(ve) + 1e-9)
            m = round(ve / 10 ** dec)
            if m == 10:
                dec, m = dec + 1, 1
            v = m * 10 ** dec if m >= 1 else None
        else:
            v = round(te / step) * step
        if v is None or v <= 0 and kind == "log":
            unassigned.append(round(p, 2))
            continue
        r = abs(p - (a + b * t(v)))
        if r > GRID_TOL:
            unassigned.append(round(p, 2))
            continue
        v = float(f"{v:.6g}")
        if v in grid:   # two lines snap to one value: keep the one nearer the straight scale
            q = grid[v]
            keep = p if r < abs(q - (a + b * t(v))) else q
            unassigned.append(round(q if keep == p else p, 2))
            grid[v] = keep
            continue
        grid[v] = p
        worst = max(worst, r)
    if len(unassigned) > MAX_UNASSIGNED:
        raise RuntimeError(f"{name}: {len(unassigned)} unassignable lines {unassigned}")
    rep[name] = dict(scale=kind, decade_or_tick_fit_pt=round(dec_res, 3), worst_line_pt=round(worst, 3),
                     worst_label_pt=round(label_off, 3), lines=len(grid), unassigned=unassigned,
                     ticks=[v for v in vs])
    return Axis(kind, [(p, v) for v, p in grid.items()], a, b)


def axis_ticks(toks, box, axis, values):
    out = []
    for t, x0, y0, x1, y1 in toks:
        if not re.fullmatch(r"\d+", t):
            continue
        v = int(t)
        if values is not None and v not in values:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # x ticks: below the frame and not left of it (the y-axis "0"/"1" sit at the corner);
        # y ticks: right-aligned against the frame's left edge
        if axis == "x" and box.y1 < cy < box.y1 + 14 and x1 > box.x0 - 0.5 and x0 < box.x1 + 0.5:
            out.append((v, cx))
        if axis == "y" and box.x0 - 12 < x1 <= box.x0 + 0.5 and box.y0 - 6 < cy < box.y1 + 6:
            out.append((v, cy))
    return out


# --------------------------------------------------------------------------------- reading
def y_at(dense, x):
    hits = []
    for (x0, y0), (x1, y1) in zip(dense, dense[1:]):
        if min(x0, x1) - 1e-6 <= x <= max(x0, x1) + 1e-6:
            y = y0 if x1 == x0 else y0 + (x - x0) / (x1 - x0) * (y1 - y0)
            if not any(abs(y - h) < 0.05 for h in hits):
                hits.append(y)
    if len(hits) != 1:
        raise RuntimeError(f"curve crosses x={x:.2f} {len(hits)} times")
    return hits[0]


def label_curves(subs, toks, kind):
    pat = r"(\d+)kHz\((\d+)mT\)" if kind == "pv_t" else r"(\d+)kHz"
    labs = [(t, x0, y0, x1, y1) for t, x0, y0, x1, y1 in toks if re.fullmatch(pat, t)]
    ends = [max(s["dense"], key=lambda p: p[0]) for s in subs]
    if len(labs) < len(subs):
        raise RuntimeError(f"{len(subs)} curves but {len(labs)} labels")

    def dist(e, l):
        _, x0, y0, x1, y1 = l
        dx = max(x0 - e[0], 0, e[0] - x1)
        dy = max(y0 - e[1], 0, e[1] - y1)
        return math.hypot(dx, dy)
    best = None
    for perm in itertools.permutations(range(len(labs)), len(subs)):
        tot = sum(dist(e, labs[j]) for e, j in zip(ends, perm))
        if best is None or tot < best[0]:
            best = (tot, perm)
    out = []
    for s, e, j in zip(subs, ends, best[1]):
        d = dist(e, labs[j])
        if d > 30:
            raise RuntimeError(f"curve ending at {e} has no label within 30 pt")
        m = re.fullmatch(pat, labs[j][0])
        cond = dict(f=float(m.group(1)) * 1e3)
        if kind == "pv_t":
            cond["B"] = float(m.group(2)) / 1e3
        out.append((cond, s, round(d, 2)))
    conds = [tuple(sorted(c.items())) for c, _, _ in out]
    if len(set(conds)) != len(conds):
        raise RuntimeError("two curves carry the same label")
    return out


def figure_temperature(words, box):
    for t, x0, y0, x1, y1 in words:
        m = re.fullmatch(r"(\d+)°C", t)
        if m and box.contains(fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)):
            return float(m.group(1))
    raise RuntimeError("no 'at NN°C' label inside the Pv-B frame")


def read_figure(doc, ed, grade, pn, kind, at):
    pg = doc[pn]
    toks = tokens(pg)                                   # character-level, for numeric ticks
    words = [tuple(w[:4]) and (w[4],) + tuple(w[:4]) for w in pg.get_text("words")]   # word-level
    box = find_frame(pg, at)
    xl, yl = gridlines(pg, box)
    xk, yk, xv, yv = AXES[kind]
    rep = dict(source=ed, page=pn + 1, kind=kind, frame=[round(v, 1) for v in box])
    # title check: "<grade> Power loss vs. ..." just above the frame
    title = [t for t in words if t[0] == grade and box.y0 - 30 < t[2] < box.y0 and box.x0 - 40 < t[1] < box.x0 + 10]
    if not title:
        raise RuntimeError(f"no '{grade}' title above the frame")
    X = calibrate(xk, xl, axis_ticks(toks, box, "x", xv), rep, "x")
    Y = calibrate(yk, yl, axis_ticks(toks, box, "y", yv), rep, "y")
    subs = curves(pg, box)
    lab = label_curves(subs, [t for t in words if box.x0 < (t[1] + t[3]) / 2 < box.x1 + 60
                              and box.y0 - 8 < (t[2] + t[4]) / 2 < box.y1], kind)
    T_fig = figure_temperature(words, box) if kind == "pv_b" else None
    rep["temperature"] = T_fig
    out, worst_pw = [], 0.0
    for cond, s, ld in lab:
        xs = [p[0] for p in s["dense"]]
        xa, xb = min(xs), max(xs)
        va, vb = X.val(xa), X.val(xb)
        if kind == "pv_t":
            grid_v = [10.0 * k for k in range(int(math.ceil(va / 10)), int(vb // 10) + 1)
                      if va + 1.0 < 10.0 * k < vb - 1.0]
            want = [("start", va)] + [("grid", v) for v in grid_v] + [("end", vb)]
        else:
            interior = [X.val(v[0]) for v in s["verts"][1:-1]] if "c" not in s["kinds"] else []
            want = [("start", va)] + [("vertex", v) for v in interior]
            want += [("grid", v) for v in (100.0, 200.0) if va * 1.01 < v < vb / 1.01
                     and not any(abs(math.log(v / w)) < 0.01 for w in interior)]
            want += [("end", vb)]
            want.sort(key=lambda w: w[1])
        pts = []
        for tag, xv_ in want:
            xp = xa if tag == "start" else xb if tag == "end" else X.pos(xv_)
            yp = y_at(s["dense"], xp)
            yv_ = Y.val(yp)
            ys = Y.straight(yp)
            xs_ = X.straight(xp)
            dev = max(abs(ys / yv_ - 1), abs(xs_ / xv_ - 1) if X.kind == "log" else 0)
            worst_pw = max(worst_pw, dev)
            edge = (abs(xp - box.x0) < FRAME_TOL or abs(xp - box.x1) < FRAME_TOL
                    or abs(yp - box.y0) < FRAME_TOL or abs(yp - box.y1) < FRAME_TOL)
            pts.append(dict(tag=tag, x=xv_, y=yv_, xp=xp, yp=yp, edge=edge))
        out.append(dict(cond=cond, label_dist=ld, pts=pts, dense=s["dense"], kinds=s["kinds"],
                        n_vertices=len(s["verts"])))
    if worst_pw > PIECEWISE_TOL:
        raise RuntimeError(f"piecewise vs straight reading differ by {worst_pw:.3f}")
    rep["piecewise_vs_straight_max"] = round(worst_pw, 4)
    physics(kind, out, X)
    return pg, box, X, Y, out, rep


def physics(kind, cs, X):
    if kind == "pv_b":
        for c1, c2 in itertools.combinations(cs, 2):
            lo, hi = sorted((c1, c2), key=lambda c: c["cond"]["f"])
            # common B range
            a = max(min(p[0] for p in lo["dense"]), min(p[0] for p in hi["dense"]))
            b = min(max(p[0] for p in lo["dense"]), max(p[0] for p in hi["dense"]))
            for k in range(5):
                if b <= a:
                    break
                x = a + (b - a) * (k + 0.5) / 5
                if y_at(lo["dense"], x) <= y_at(hi["dense"], x):   # page y grows downward
                    raise RuntimeError(f"Pv({lo['cond']['f']:g}) >= Pv({hi['cond']['f']:g}) at a common B")
    else:
        byB = {}
        for c in cs:
            byB.setdefault(c["cond"]["B"], []).append(c)
        for B, group in byB.items():
            group.sort(key=lambda c: c["cond"]["f"])
            for lo, hi in zip(group, group[1:]):
                x = (max(min(p[0] for p in lo["dense"]), min(p[0] for p in hi["dense"]))
                     + min(max(p[0] for p in lo["dense"]), max(p[0] for p in hi["dense"]))) / 2
                if y_at(lo["dense"], x) <= y_at(hi["dense"], x):
                    raise RuntimeError(f"Pv-T at {B} T: {lo['cond']['f']:g} Hz curve not below {hi['cond']['f']:g} Hz")


def table_check(grade, ed, kind, X, Y, cs, T_fig):
    typ = {t: v[0] for t, v in zip(TEMPS, TABLE_2017[grade])} if ed != "ed2003" else {}
    mx = {t: v[1] for t, v in zip(TEMPS, TABLE_2017[grade])} if ed != "ed2003" else dict(zip(TEMPS, TABLE_2003[grade]))
    res = []
    for c in cs:
        if c["cond"]["f"] != 100e3:
            continue
        if kind == "pv_t" and c["cond"]["B"] == 0.2:
            xs = [p[0] for p in c["dense"]]
            ta, tb = X.val(min(xs)), X.val(max(xs))
            for t in TEMPS:
                tt = t
                if t < ta and ta - t <= 1.0:
                    tt = ta   # drawn start is within 1 C of the 23 C table temperature
                if t > tb and t - tb <= 1.0:
                    tt = tb   # drawn end is within 1 C of the 120 C table temperature
                if not ta - 1e-9 <= tt <= tb + 1e-9:
                    continue
                v = Y.val(y_at(c["dense"], X.pos(tt)))
                res.append(dict(T=t, read_at_T=round(tt, 2), curve=round(v, 1), table_max=mx[t],
                                ratio=round(v / mx[t], 3),
                                ratio_typ=round(v / typ[t], 3) if typ else None))
        if kind == "pv_b" and T_fig in mx:
            xs = [p[0] for p in c["dense"]]
            if X.val(min(xs)) <= 200 <= X.val(max(xs)) * 1.0001:
                xp = min(X.pos(200.0), max(xs))
                v = Y.val(y_at(c["dense"], xp))
                res.append(dict(T=T_fig, B_mT=round(X.val(xp), 1), curve=round(v, 1), table_max=mx[T_fig],
                                ratio=round(v / mx[T_fig], 3),
                                ratio_typ=round(v / typ[T_fig], 3) if typ else None))
    if not res:
        raise RuntimeError("no 100 kHz/200 mT reading to check against the table")
    return res


# ----------------------------------------------------------------------------- overlays
PALETTE = [(220, 30, 30), (20, 120, 220), (0, 150, 60), (200, 120, 0), (150, 0, 180), (0, 170, 170)]


def overlay(pg, box, X, Y, cs, path, zoom=5):
    from PIL import Image, ImageDraw
    clip = fitz.Rect(box.x0 - 30, box.y0 - 20, box.x1 + 90, box.y1 + 25)
    pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(img)
    tp = lambda x, y: ((x - clip.x0) * zoom, (y - clip.y0) * zoom)
    for p, v in X.grid:   # calibrated lines, cyan
        d.line([tp(p, box.y0), tp(p, box.y1)], fill=(0, 200, 230), width=1)
    for p, v in Y.grid:
        d.line([tp(box.x0, p), tp(box.x1, p)], fill=(0, 200, 230), width=1)
    for i, c in enumerate(cs):
        col = PALETTE[i % len(PALETTE)]
        d.line([tp(*q) for q in c["dense"]], fill=(255, 0, 255), width=1)
        for q in c["pts"]:
            X_, Y_ = tp(q["xp"], q["yp"])
            d.ellipse([X_ - 7, Y_ - 7, X_ + 7, Y_ + 7], outline=col, width=2)
        last = c["pts"][-1]
        lab = " ".join(f"{k}={v:g}" for k, v in c["cond"].items())
        d.text(tp(last["xp"] + 2, last["yp"] + 2), lab, fill=col)
    img.save(path)


# ------------------------------------------------------- current edition vs 2017: same drawing?
def colourful(c):
    return c is not None and (max(c) - min(c)) > 0.25


def grey_lines(pg):
    hs, vs = [], []
    for d in pg.get_drawings():
        col = d.get("color") if d.get("color") is not None else d.get("fill")
        if col is None or colourful(col) or min(col) > 0.9:
            continue
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.05:
                    hs.append((a.y, min(a.x, b.x), max(a.x, b.x)))
                elif abs(a.x - b.x) < 0.05:
                    vs.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            elif it[0] == "re":
                r = it[1]
                if d.get("type") == "s":
                    hs += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
                    vs += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
                elif r.height < 1.0 and r.width > 20:
                    hs.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif r.width < 1.0 and r.height > 20:
                    vs.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
    return hs, vs


def frame_from_lines(pg, at):
    hs, vs = grey_lines(pg)
    H = [h for h in hs if h[1] <= at[0] <= h[2] and h[2] - h[1] > 150]
    if not H:
        raise RuntimeError(f"no horizontal gridline through x={at[0]}")
    xa, xb = min(h[1] for h in H), max(h[2] for h in H)
    V = [v for v in vs if v[1] <= at[1] <= v[2] and v[2] - v[1] > 100 and xa - 1.5 <= v[0] <= xb + 1.5]
    if len(V) < 2:
        raise RuntimeError(f"no vertical gridlines through y={at[1]}")
    ya, yb = min(v[1] for v in V), max(v[2] for v in V)
    H2 = [h[0] for h in H if ya - 1.5 <= h[0] <= yb + 1.5]
    return fitz.Rect(min(v[0] for v in V), min(H2), max(v[0] for v in V), max(H2))


def compare_current(cur, ed17, fig, cur_fig=None):
    """Map the 2017 figure's frame onto the current edition's frame and measure how far every 2017
    curve sample lies from the nearest point of the current edition's coloured curve geometry."""
    grade, pn, kind, at = fig
    p17, pcur = ed17[pn], cur[pn]
    b17 = find_frame(p17, at)
    # the current edition draws frames and gridlines as thin filled rectangles inside composite
    # paths, slightly shifted and scaled on the page: rebuild its frame from those lines
    bc = frame_from_lines(pcur, at if cur_fig is None else cur_fig[3])
    if cur_fig is not None:
        pcur = cur[cur_fig[1]]
    geo = []
    for d in pcur.get_drawings():
        col = d.get("color") if d.get("color") is not None else d.get("fill")
        if not colourful(col):
            continue
        if not fitz.Rect(bc.x0 - 1, bc.y0 - 1, bc.x1 + 1, bc.y1 + 1).contains(d["rect"]):
            continue
        for s in subpaths(d):
            for (x0, y0), (x1, y1) in zip(s["dense"], s["dense"][1:]):
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.2))
                geo += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n + 1)]
    if not geo:
        raise RuntimeError("no coloured curve geometry in the current edition's frame")
    sx, sy = bc.width / b17.width, bc.height / b17.height
    worst, allds = 0.0, []
    for s in curves(p17, b17):
        dense = []
        for (x0, y0), (x1, y1) in zip(s["dense"], s["dense"][1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.5))
            dense += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n)]
        for x, y in dense:
            X_, Y_ = bc.x0 + (x - b17.x0) * sx, bc.y0 + (y - b17.y0) * sy
            dmin = min([math.hypot(X_ - gx, Y_ - gy) for gx, gy in geo if abs(gx - X_) < 3] or [99.0])
            allds.append(dmin)
    allds.sort()
    return dict(frame2017=[round(v, 1) for v in b17], frame_current=[round(v, 1) for v in bc],
                scale=(round(sx, 4), round(sy, 4)), samples=len(allds),
                median_pt=round(allds[len(allds) // 2], 3), max_pt=round(allds[-1], 3))


# ------------------------------------------------------------------------------- validation
def validate(records, mas):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
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
    base = {json.loads(l)["name"]: json.loads(l) for l in open(os.path.join(mas, "data/core_materials.ndjson"))}
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
    Bm = sorted({round(key(p)[1] * 1000) for p in pts})
    Ts = sorted({key(p)[2] for p in pts})
    return dict(n=len(pts), f_kHz=[f / 1e3 for f in fs], B_mT=Bm, T=Ts, nf=len(fs), nB=len(Bm), nT=len(Ts))


def identifiability(pts):
    """At any one temperature: how many f share a B, and how many B share an f (Pv-B figures)."""
    byT = {}
    for p in pts:
        f, B, T = key(p)
        byT.setdefault(T, set()).add((f, round(B * 1000)))
    best = None
    for T, s in byT.items():
        fs = {f for f, _ in s}
        nB_per_f = max(len({b for f2, b in s if f2 == f}) for f in fs)
        if best is None or (len(fs), nB_per_f) > (best["nf"], best["nB_per_f"]):
            best = dict(T=T, nf=len(fs), nB_per_f=nB_per_f)
    return best


def check_text(text, needles, where):
    flat = re.sub(r"\s+", " ", text)
    for n in needles:
        if n not in flat:
            raise SystemExit(f"{where}: expected {n!r} in the page text")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ed2017", required=True, help="2017 edition of products/pdf/003.pdf (Wayback 2018-06-13)")
    ap.add_argument("--ed2003", required=True, help="2003 edition eng/product/pdf/No.003.pdf (Wayback 2004-06-30)")
    ap.add_argument("--current", required=True, help="current products/pdf/003.pdf")
    ap.add_argument("--mas", required=True, help="MAS checkout (data/, schemas/; ../PEAS/schemas for $refs)")
    ap.add_argument("--json", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--overlays", required=True)
    ap.add_argument("--gate", type=float, default=GATE, help="reject ratio to the table maximum (default 1.10)")
    a = ap.parse_args()
    os.makedirs(a.overlays, exist_ok=True)
    shas = {}
    for k in ("ed2017", "ed2003", "current"):
        shas[k] = sha256(getattr(a, k))
        if shas[k] != SHA[k]:
            print(f"WARNING {k}: sha256 {shas[k]} differs from the file read when this script was written",
                  file=sys.stderr)
    docs = {"ed2017": fitz.open(a.ed2017), "ed2003": fitz.open(a.ed2003)}
    cur = fitz.open(a.current)

    t17 = docs["ed2017"][0].get_text()
    check_text(t17, ["MB1", "MB1H", "MB3", "MB4", "MBT1", "MBT2", "Power loss at 100kHz, 200mT"], "2017 p3")
    for g, rows in TABLE_2017.items():
        for typ, mx in rows:
            check_text(t17, [f"{typ}({mx}max.)"], f"2017 p3 {g}")
    t03 = docs["ed2003"][0].get_text()
    check_text(t03, ["MB1", "MB3", "MB4", "MBT1", "Power loss at 100kHz, 200mT"], "2003 p3")
    for g, rows in TABLE_2003.items():
        for mx in rows:
            check_text(t03, [f"{mx}max."], f"2003 p3 {g}")
    if cur[0].get_text().strip():
        print("NOTE: the current edition now has a text layer; re-check its table against TABLE_2017",
              file=sys.stderr)

    figs, pts = {g: [] for g in GRADES}, {g: [] for g in GRADES}
    readings, figpts = {}, {}
    for ed in ("ed2017", "ed2003"):
        for fig in FIGS[ed]:
            grade, pn, kind, at = fig
            try:
                pg, box, X, Y, cs, rep = read_figure(docs[ed], ed, grade, pn, kind, at)
                rep["table"] = table_check(grade, ed, kind, X, Y, cs, rep["temperature"])
            except RuntimeError as e:
                figs[grade].append(dict(source=ed, page=pn + 1, kind=kind, REJECTED=str(e)))
                continue
            png = os.path.join(a.overlays, f"{grade}_{ed}_p{pn + 1}_{kind}.png")
            overlay(pg, box, X, Y, cs, png)
            rep["overlay"] = os.path.basename(png)
            rep["curves"] = [dict(c["cond"], n=len(c["pts"]), label_dist_pt=c["label_dist"],
                                  segments=c["kinds"]) for c in cs]
            bad = [c for c in rep["table"] if c["ratio"] > a.gate]
            new = []
            drop = DROP_LINES.get((grade, ed, kind), {})
            if drop:
                rep["DROPPED_LINES"] = {f"{f / 1e3:g} kHz": why for f, why in drop.items()}
            for c in cs:
                if c["cond"]["f"] in drop:
                    continue
                for q in c["pts"]:
                    if kind == "pv_t":
                        f, B, T = c["cond"]["f"], c["cond"]["B"], q["x"]
                    else:
                        f, B, T = c["cond"]["f"], q["x"] / 1e3, rep["temperature"]
                    new.append(point(f, B, T, q["y"] * 1e3))
                    readings[(grade, ed, kind, f, round(B, 4), round(T, 1))] = q["y"]
            rep["frame_edge_points"] = [dict(c["cond"], x=round(q["x"], 2), y=round(q["y"], 3))
                                        for c in cs if c["cond"]["f"] not in drop for q in c["pts"] if q["edge"]]
            if bad:
                rep["REJECTED"] = f"{len(bad)} table check(s) above {a.gate}: " + ", ".join(
                    f"{c['T']} C reads {c['curve']} vs max {c['table_max']} (x{c['ratio']})" for c in bad)
            else:
                rep["points"] = len(new)
                figpts[(grade, ed, kind)] = new
            figs[grade].append(rep)

    # 2003 vs 2017 at common conditions (MB3, MB4, MBT1): different drawings or one?
    cross = {}
    for (g, ed, kind, f, B, T), v in readings.items():
        if ed != "ed2003":
            continue
        for (g2, ed2, kind2, f2, B2, T2), v2 in readings.items():
            if g2 == g and ed2 == "ed2017" and kind2 == kind and f2 == f and abs(B2 - B) < 1e-3 and abs(T2 - T) < 0.6:
                cross.setdefault(g, []).append(dict(kind=kind, f_kHz=f / 1e3, B_mT=round(B * 1e3, 1), T=T,
                                                    ed2003=round(v, 2), ed2017=round(v2, 2),
                                                    ratio_2003_over_2017=round(v / v2, 3)))
    # The 2003 figures of MB3, MB4 and MBT1 turned out to be the SAME drawing as the 2017 ones (every
    # common reading agrees to < SAME_DRAWING_TOL).  A re-published drawing is one figure, not two, so
    # its second reading adds nothing and would duplicate every point: the 2017 reading is kept.
    for (g, ed, kind), new in sorted(figpts.items()):
        if ed == "ed2003" and (g, "ed2017", kind) in figpts:
            rs = [c["ratio_2003_over_2017"] for c in cross.get(g, []) if c["kind"] == kind]
            if rs and max(abs(r - 1) for r in rs) < SAME_DRAWING_TOL:
                for f in figs[g]:
                    if f["source"] == ed and f["kind"] == kind:
                        f["SAME_DRAWING_AS_ed2017"] = (f"{len(rs)} common readings agree within "
                                                       f"{max(abs(r - 1) for r in rs):.4f}; points not added again")
                        f["points"] = 0
                continue
        pts[g] += new
    # current edition vs 2017: geometric identity
    current_check = {}
    for fig in FIGS["ed2017"]:
        try:
            current_check[f"{fig[0]} p{fig[1] + 1} {fig[2]}"] = compare_current(cur, docs["ed2017"], fig)
        except RuntimeError as e:
            current_check[f"{fig[0]} p{fig[1] + 1} {fig[2]}"] = dict(ERROR=str(e))

    # negative control: the same measure between DIFFERENT drawings must be large, or it proves nothing
    neg = {}
    for a_, b_ in ((FIGS["ed2017"][4], FIGS["ed2017"][5]), (FIGS["ed2017"][6], FIGS["ed2017"][7]),
                   (FIGS["ed2017"][1], FIGS["ed2017"][5])):
        neg[f"2017 {a_[0]} {a_[2]} onto current {b_[0]} {b_[2]}"] = compare_current(cur, docs["ed2017"], a_, b_)
    records, report = [], {}
    for g in GRADES:
        p = sorted(pts[g], key=key)
        note = None
        if g == "MBT2":
            # no figure in any edition: the printed typical values are the only data
            p = [point(100e3, 0.2, t, typ * 1e3) for t, (typ, _) in zip(TEMPS, TABLE_2017[g])]
            note = ("no loss figure in any JFE edition (2003: grade absent; 2017 and current: table only); "
                    "the 4 points are the printed TYPICAL Pcv(100 kHz, 200 mT) at 23/60/100/120 C")
            figs[g].append(dict(source="ed2017+current", kind="table", points=len(p), note=note))
        dup = {}
        for q in p:
            dup.setdefault(key(q), []).append(q["value"])
        report[g] = dict(manufacturer="JFE", figures=figs[g], coverage=coverage(p),
                         identifiability=identifiability(p),
                         same_condition_both_kept={str(k): v for k, v in dup.items() if len(v) > 1},
                         cross_edition=cross.get(g, []))
        if len(p) < 4:
            report[g]["NOT_EMITTED"] = f"only {len(p)} points"
            continue
        records.append({"name": g, "manufacturerInfo": {"name": "JFE"}, "volumetricLosses": {"default": [p]}})
    report["_current_vs_2017"] = current_check
    report["_current_vs_2017_negative_control"] = neg
    report["_validation"] = validate(records, a.mas)
    report["_sources"] = {k: dict(url=URL[k], sha256=shas[k]) for k in URL}
    report["_gate"] = a.gate
    json.dump(records, open(a.json, "w"), indent=1)
    json.dump(report, open(a.report, "w"), indent=1)
    for g in GRADES:
        r = report[g]
        c = r["coverage"]
        print(f"{g:5s} {c['n']:3d} pts  f={c['f_kHz']} kHz  nB={c['nB']}  T={c['T'][:3]}..{c['T'][-3:]}"
              f"  ident={r['identifiability']}")
        for f in r["figures"]:
            tab = ", ".join(f"{t['T']}C x{t['ratio']}" for t in f.get("table", []) or [])
            st = ("REJECTED: " + f["REJECTED"]) if f.get("REJECTED") else "accepted"
            print(f"    {f['source']} p{f.get('page', '-')} {f['kind']}: {st}  [{tab}]")
    for k, v in current_check.items():
        print("current vs 2017", k, v)
    for k, v in neg.items():
        print("negative control", k, v)
    bad = {k: v for k, v in report["_validation"].items() if v}
    print("schema:", "all valid" if not bad else bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
