#!/usr/bin/env python3
"""Extract core-loss curves from TDK's Mn-Zn ferrite material catalogue (vector PDF) (ABT #1518).

    python3 scripts/extract-tdk-loss.py ferrite_mn-zn_material_characteristics_en.pdf \
            --json /tmp/tdk-points.json [--report /tmp/tdk-report.json]

Source
------
TDK Corporation, "Ferrite for switching power supplies / high-frequency power supplies / large
size ferrite for high power -- Material list", catalogue ferrite_mn-zn_material_characteristics_en,
edition 20220510, 24 pages:
    https://product.tdk.com/system/files/dam/doc/product/ferrite/ferrite/ferrite-core/catalog/ferrite_mn-zn_material_characteristics_en.pdf
Read 2026-09-29. product.tdk.com is behind Akamai: a bare curl gets "Access Denied"; a desktop
Chrome User-Agent with Accept/Accept-Language headers and a product.tdk.com Referer is served
the PDF (508,915 bytes, sha256 in the commit message that added this script).

TDK's Magnetic Design Tool (tools.tdk-electronics.tdk.com/mdt) serves numeric loss grids only for
N27 N41 N49 N51 N72 N87 N88 N92 N95 N96 N97 PC200, which MAS already holds. The grades below are
not in the tool; their only published loss data is this catalogue.

Figures read (page numbers of the PDF):
    PC47 p5, PC90 p6, PC95 p7  "Core loss (Typ.) (Sine wave data)": Pv vs Bm at 60 C (solid)
                               and 100 C (dashed), one line per frequency; and "Temperature
                               dependence of core loss (Typ.)" at 100 kHz / 200 mT.
    PC50 p11                   the same Pv-Bm figure (200 kHz .. 1 MHz, 60 / 100 C) and Pv vs T
                               (log axis) at 500 kHz and 1 MHz, 50 and 100 mT.
    PE22 p15-16, PC40 p17-18   "Core loss vs. temperature characteristics" (25 kHz and
                               100 kHz at 200 mT) and "Core loss vs. frequency characteristics",
                               seven figures at 23/40/60/80/90/100/120 C, one line per Bm
                               (50..300 mT).

Method -- nothing is digitised from pixels
------------------------------------------
The catalogue is a vector PDF (its only raster images are the TDK logo and header bars), so every
curve is read from the PDF drawing operators with PyMuPDF, in page coordinates:

1. The plot area is the thin black rectangle of the figure. The axis limits are DECLARED per figure
   below (read off the printed tick labels) and then VERIFIED two ways, each of which can fail:
   every numeric tick label next to an axis must sit within LABEL_TOL pt of the position the
   declared calibration gives its value (this catches a whole-decade error, which the grid alone
   cannot), and every grey gridline must land within GRID_TOL pt of a 1..9 x 10^k (log) or
   step-multiple (linear) value.
2. Curves are the stroked paths of width ~1 pt inside the plot area; a path is split into
   subpaths wherever it jumps. Legend keys (short horizontal strokes) are recognised and
   removed from the curve set.
3. Each curve is identified by the figure's own labelling, never by guesswork:
     legend   -- colour + dash of the legend key, and the words printed right of it;
     endtext  -- the words printed just right of the curve's last point (PC50 Pv-T);
     textcolour -- in-plot text in the curve's own colour (PE22/PC40 Pv-T);
     order    -- for the frequency lines of the Pv-Bm figures, whose labels are shared between
                 the 60 C and 100 C sets: frequencies ascending in loss at a common Bm. Loss
                 rises with f at fixed B, so this is physics, and the count must match exactly.
   Wherever the physics ordering is defined (Pv-Bm: rising with f; Pv-f: rising with B) it is
   checked on the labelled result too; a figure that violates it is rejected.
4. Emitted points are exact reads of the drawn line: the polyline vertices when a curve has at
   most MAX_VERTICES of them (Bezier curves: the knots), otherwise N_SAMPLES abscissae spaced
   evenly (log or linear, as the axis) over the drawn span, interpolated along the drawn line.
   Nothing is extrapolated beyond the drawn span.
5. Every curve is then checked against the numbers printed in the SAME catalogue's material table
   (Pcv at a stated f, B, T). The curve is read at that condition; a disagreement larger than
   TABLE_TOL rejects the whole FIGURE (#1006: a trace that misses its own data sheet's numbers is
   rejected, not adjusted). A grade ships only if at least one of its remaining figures reproduces
   a printed value. A figure that labels two curves identically is dropped too. All ratios and
   every dropped figure are written to the report.

Output: {material: [MAS volumetricLossesPoint, ...]} with SI units (Hz, T, W/m^3, degC),
waveform label "sinusoidal" (the catalogue's tables and Pv-Bm figures state "sine wave"),
origin "manufacturer".
"""
import argparse
import json
import math
import re
import sys

import fitz  # PyMuPDF

GRID_TOL = 1.0              # pt (TDK draws its log grid to ~0.8 pt, 1 % of a decade)
LABEL_TOL = 3.0             # pt, tick-label centre vs calibrated position
MAX_VERTICES = 8
N_SAMPLES = 10
TABLE_TOL = 0.10            # max |curve/table - 1|
JUMP = 0.6                  # pt; a gap this large starts a new subpath

# Printed material-table values: (f Hz, B T, T degC, Pv kW/m^3). Pages 4, 10, 14.
TABLE = {
    "PC47": [(100e3, 0.2, 25, 600), (100e3, 0.2, 60, 400), (100e3, 0.2, 100, 250), (100e3, 0.2, 120, 360)],
    "PC90": [(100e3, 0.2, 25, 680), (100e3, 0.2, 60, 470), (100e3, 0.2, 100, 320), (100e3, 0.2, 120, 460)],
    "PC95": [(100e3, 0.2, 25, 350), (100e3, 0.2, 60, 290), (100e3, 0.2, 100, 290), (100e3, 0.2, 120, 350)],
    "PC50": [(500e3, 0.05, 25, 130), (500e3, 0.05, 100, 80)],
    "PE22": [(25e3, 0.2, 90, 79), (25e3, 0.2, 100, 80), (100e3, 0.2, 100, 520)],
    "PC40": [(25e3, 0.2, 90, 64), (25e3, 0.2, 100, 70), (100e3, 0.2, 100, 420)],
}

PVB = dict(kind="pv_b", x=("log", 50, 500), y=("log", 1, 1e5))
PVT_LIN = dict(kind="pv_t", x=("lin", 0, 140), y=("lin", 0, 1000))
PVF_T = (23, 40, 60, 80, 90, 100, 120)


def pvf_figs(page):
    """Seven Pv-f figures per page, left-to-right then top-to-bottom; T from 'Temp.xx°C'."""
    return [dict(kind="pv_f", page=page, slot=i, x=("log", 10e3, 10e6), xscale=1e3,
                 y=("log", 1, 1e4), T=t, label="legend") for i, t in enumerate(PVF_T)]


FIGS = {
    "PC47": [dict(PVB, page=5, at=(70, 616), label="order", styles={False: 60, True: 100},
                  series=[100e3, 200e3, 300e3]),
             dict(PVT_LIN, page=5, at=(333, 611), cond=(100e3, 0.2))],
    "PC90": [dict(PVB, page=6, at=(67, 615), y=("log", 0.1, 1e4), label="order",
                  styles={False: 60, True: 100}, series=[50e3, 100e3, 200e3, 300e3]),
             dict(PVT_LIN, page=6, at=(333, 611), cond=(100e3, 0.2))],
    "PC95": [dict(PVB, page=7, at=(70, 617), label="order", styles={False: 60, True: 100},
                  series=[50e3, 100e3, 200e3, 300e3]),
             dict(PVT_LIN, page=7, at=(333, 612), cond=(100e3, 0.2))],
    "PC50": [dict(PVB, page=11, at=(68, 610), x=("log", 10, 500), label="order",
                  styles={False: 60, True: 100}, series=[200e3, 300e3, 500e3, 700e3, 1e6]),
             dict(kind="pv_t", page=11, at=(336, 605), x=("lin", 0, 140), y=("log", 10, 1e4),
                  label="endtext")],
    "PE22": [dict(kind="pv_t", page=15, at=(64, 296), x=("lin", 0, 120), y=("lin", 0, 900),
                  label="textcolour")] + pvf_figs(16),
    "PC40": [dict(kind="pv_t", page=17, at=(64, 300), x=("lin", 0, 120), y=("lin", 0, 900),
                  label="textcolour")] + pvf_figs(18),
}


# ----------------------------------------------------------------------------------- geometry
def col(c):
    return tuple(round(v, 2) for v in c) if c else None


def is_grey(c):
    """Gridline grey: neutral and mid-light (TDK draws its grid in ~0.66 grey)."""
    return max(c) - min(c) < 0.03 and 0.5 < c[0] < 0.85


def is_dashed(d):
    da = d.get("dashes")
    return bool(da) and da.strip() not in ("[] 0", "[]0", "")


def bezier(p0, p1, p2, p3, n=16):
    out = []
    for s in range(1, n + 1):
        t = s / n
        u = 1 - t
        out.append((u**3 * p0.x + 3*u*u*t * p1.x + 3*u*t*t * p2.x + t**3 * p3.x,
                    u**3 * p0.y + 3*u*u*t * p1.y + 3*u*t*t * p2.y + t**3 * p3.y))
    return out


def subpaths(d):
    """Split a drawing into subpaths. Each is (dense points, knots)."""
    subs, dense, knots, last = [], [], [], None
    for it in d["items"]:
        op = it[0]
        if op == "l":
            a, b = it[1], it[2]
            seg, end = [(b.x, b.y)], b
        elif op == "c":
            a, end = it[1], it[4]
            seg = bezier(it[1], it[2], it[3], it[4])
        else:
            continue
        if last is None or math.hypot(a.x - last.x, a.y - last.y) > JUMP:
            if dense:
                subs.append((dense, knots))
            dense, knots = [(a.x, a.y)], [(a.x, a.y)]
        dense.extend(seg)
        knots.append((end.x, end.y))
        last = end
    if dense:
        subs.append((dense, knots))
    return subs


class Axis:
    def __init__(self, spec, p0, p1, flip):
        self.kind, self.lo, self.hi = spec
        self.p0, self.p1, self.flip = p0, p1, flip

    def val(self, p):
        t = (p - self.p0) / (self.p1 - self.p0)
        if self.flip:
            t = 1 - t
        if self.kind == "log":
            return self.lo * (self.hi / self.lo) ** t
        return self.lo + t * (self.hi - self.lo)

    def pos(self, v):
        if self.kind == "log":
            t = math.log(v / self.lo) / math.log(self.hi / self.lo)
        else:
            t = (v - self.lo) / (self.hi - self.lo)
        if self.flip:
            t = 1 - t
        return self.p0 + t * (self.p1 - self.p0)

    def span(self):
        return abs(self.p1 - self.p0)


def parse_tick(s, kind, pow10):
    s = s.replace("–", "-").replace("−", "-")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    if kind == "log" and pow10 and s.startswith("10") and len(s) > 2:
        return 10.0 ** int(s[2:])
    if kind == "log" and pow10 and s == "1":
        return 1.0
    return float(s)


def check_axes(fig, box, words, grid, report):
    """Verify the declared calibration against tick labels and gridlines. Raise on failure."""
    xa, ya = fig["_xa"], fig["_ya"]
    # tick labels. A log axis whose labels are 10^k is written '10','101','102' ... in the text
    # layer (the exponent is a superscript); detect that style by the presence of '10k' words.
    for ax, name in ((xa, "x"), (ya, "y")):
        if name == "x":
            # right edge past the frame's left edge: the y axis's bottom label sits just left
            # of the frame at the same height and must not be read as an x label
            cand = [w for w in words if box.y1 - 1 < (w[1] + w[3]) / 2 < box.y1 + 12
                    and w[2] > box.x0 - 1 and w[0] < box.x1 + 6]
            centre = lambda w: (w[0] + w[2]) / 2
        else:
            cand = [w for w in words if box.x0 - 30 < w[2] < box.x0 + 1
                    and box.y0 - 4 < (w[1] + w[3]) / 2 < box.y1 + 4]
            centre = lambda w: (w[1] + w[3]) / 2
        texts = [w[4] for w in cand]
        pow10 = ax.kind == "log" and sum(1 for t in texts if re.fullmatch(r"10[-–]?\d", t)) >= 2
        good, worst = 0, 0.0
        for w in cand:
            v = parse_tick(w[4], ax.kind, pow10)
            if v is None or (ax.kind == "log" and v <= 0):
                continue
            v *= fig.get(name + "scale", 1.0)   # tick labels printed in kHz on a Hz axis
            lo, hi = min(ax.lo, ax.hi), max(ax.lo, ax.hi)
            if not (lo * 0.999 <= v <= hi * 1.001):
                raise RuntimeError(f"{name} tick label {w[4]!r} lies outside the declared axis {lo}..{hi}")
            err = abs(centre(w) - ax.pos(v))
            worst = max(worst, err)
            if err > LABEL_TOL:
                raise RuntimeError(f"{name} tick label {w[4]!r} is {err:.1f} pt off its calibrated position")
            good += 1
        if good < 2:
            raise RuntimeError(f"{name} axis: only {good} tick labels could verify the calibration")
        report[f"{name}_labels"] = [good, round(worst, 2)]
    # gridlines
    for ax, name, lines in ((xa, "x", grid["v"]), (ya, "y", grid["h"])):
        worst = 0.0
        step = None
        if ax.kind == "lin":
            step = fig.get(name + "step") or nice_step(ax)
        for p in lines:
            v = ax.val(p)
            if ax.kind == "log":
                e = math.log10(v)
                m = 10 ** (e - math.floor(e))
                nearest = min(range(1, 11), key=lambda k: abs(m - k))
                target = ax.pos(nearest * 10 ** math.floor(e))
            else:
                target = ax.pos(round(v / step) * step)
            worst = max(worst, abs(p - target))
        if worst > GRID_TOL:
            raise RuntimeError(f"{name} gridline off calibration by {worst:.2f} pt")
        report[f"{name}_grid"] = [len(lines), round(worst, 2)]


def nice_step(ax):
    span = abs(ax.hi - ax.lo)
    for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if span / s <= 16:
            return s
    return span / 10


# ------------------------------------------------------------------------------ figure reader
def find_box(page_draw, at):
    for d in page_draw:
        if d["items"] and d["items"][0][0] == "re" and d["rect"].width > 100:
            r = d["rect"]
            if abs(r.x0 - at[0]) < 3 and abs(r.y0 - at[1]) < 3:
                return r
    raise RuntimeError(f"no plot box at {at}")


def pvf_boxes(page_draw, words):
    """The seven Pv-f plot boxes of a page, each paired with its 'Temp.xx°C' label."""
    out = []
    for d in page_draw:
        if d["items"] and d["items"][0][0] == "re" and 150 < d["rect"].width < 200 and 90 < d["rect"].height < 115:
            r = d["rect"]
            t = [w[4] for w in words if r.contains(fitz.Rect(w[:4])) and w[4].startswith("Temp.")]
            if t:
                out.append((r, float(re.search(r"(-?\d+)", t[0]).group(1))))
    return out


def read_figure(pg, fig):
    draws = pg.get_drawings()
    words = pg.get_text("words")
    if fig["kind"] == "pv_f":
        boxes = [b for b, t in pvf_boxes(draws, words) if t == fig["T"]]
        if len(boxes) != 1:
            raise RuntimeError(f"page {fig['page']}: {len(boxes)} Pv-f boxes labelled Temp.{fig['T']}")
        box = boxes[0]
    else:
        box = find_box(draws, fig["at"])
    fig["_xa"] = Axis(fig["x"], box.x0, box.x1, False)
    fig["_ya"] = Axis(fig["y"], box.y0, box.y1, True)
    inside = fitz.Rect(box.x0 - 1.5, box.y0 - 1.5, box.x1 + 1.5, box.y1 + 1.5)
    grid = {"h": [], "v": []}
    strokes, swatches = [], []
    for d in draws:
        c = col(d.get("color"))
        if c is None or not inside.contains(d["rect"]):
            continue
        r = d["rect"]
        if is_grey(c) and len(d["items"]) == 1 and d["items"][0][0] == "l":
            if r.height < 0.2 and r.width > 0.9 * box.width:
                grid["h"].append(r.y0)
            elif r.width < 0.2 and r.height > 0.9 * box.height:
                grid["v"].append(r.x0)
            continue
        if (d.get("width") or 0) < 0.8 or is_grey(c):
            continue
        for dense, knots in subpaths(d):
            xs = [p[0] for p in dense]
            ys = [p[1] for p in dense]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if h < 0.3 and 8 < w < 30 and len(knots) == 2:
                swatches.append(dict(color=c, dashed=is_dashed(d), y=ys[0], x1=max(xs)))
            elif w > 3:
                strokes.append(dict(color=c, dashed=is_dashed(d), dense=dense, knots=knots,
                                    kind="line" if all(it[0] == "l" for it in d["items"]) else "bezier"))
    report = {"page": fig["page"], "kind": fig["kind"], "box": [round(v, 1) for v in box]}
    check_axes(fig, box, words, grid, report)
    # keep only strokes whose colour is a data colour: drop black frame bits and tiny text marks
    strokes = [s for s in strokes if max(s["color"]) > 0.3]
    return box, words, strokes, swatches, report


def words_right_of(words, x, y, dx=14, dy=4.5):
    near = [w for w in words if x - 1 <= w[0] <= x + dx and abs((w[1] + w[3]) / 2 - y) <= dy]
    return " ".join(w[4] for w in sorted(near, key=lambda w: w[0]))


def parse_cond(text):
    f = re.search(r"([\d.]+)\s*(k|M)Hz", text)
    b = re.search(r"([\d.]+)\s*mT", text)
    t = re.search(r"(-?[\d.]+)\s*°C", text)
    out = {}
    if f:
        out["f"] = float(f.group(1)) * (1e3 if f.group(2) == "k" else 1e6)
    if b:
        out["B"] = float(b.group(1)) * 1e-3
    if t:
        out["T"] = float(t.group(1))
    return out


def to_xy(fig, pts):
    return [(fig["_xa"].val(x), fig["_ya"].val(y)) for x, y in pts]


def curve_value(xy, xq, logx, logy):
    """Read the drawn curve at abscissa xq (None outside the drawn span)."""
    pts = sorted(xy)
    if not (pts[0][0] <= xq <= pts[-1][0]):
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= xq <= x1:
            if x1 == x0:
                return y0
            t = (math.log(xq / x0) / math.log(x1 / x0)) if logx else (xq - x0) / (x1 - x0)
            if logy:
                return y0 * (y1 / y0) ** t
            return y0 + t * (y1 - y0)
    return None


def emit_samples(fig, s):
    """Exact reads of the drawn line: vertices/knots if few, else N_SAMPLES along the span."""
    xy_dense = to_xy(fig, s["dense"])
    xy_knots = to_xy(fig, s["knots"])
    if len(xy_knots) <= MAX_VERTICES:
        return xy_knots
    logx = fig["x"][0] == "log"
    xs = [p[0] for p in xy_dense]
    lo, hi = min(xs), max(xs)
    out = []
    for i in range(N_SAMPLES):
        t = i / (N_SAMPLES - 1)
        xq = lo * (hi / lo) ** t if logx else lo + t * (hi - lo)
        xq = min(max(xq, lo), hi)
        out.append((xq, curve_value(xy_dense, xq, logx, fig["y"][0] == "log")))
    return out


def label_curves(fig, words, strokes, swatches):
    """Return [(cond dict, stroke)]. Raises if the labelling is incomplete or ambiguous."""
    kind, how = fig["kind"], fig.get("label", "single")
    out = []
    if how == "single":
        # one curve, its condition printed in the figure (e.g. '100kHz/200mT'): check that too
        printed = parse_cond(" ".join(w[4] for w in words if fig["_box"].contains(fitz.Rect(w[:4]))))
        f, B = fig["cond"]
        if abs(printed.get("f", -1) - f) > 1 or abs(printed.get("B", -1) - B) > 1e-6:
            raise RuntimeError(f"figure prints {printed}, config says f={f} B={B}")
        if len(strokes) != 1:
            raise RuntimeError(f"{len(strokes)} curves in a one-condition figure")
        out.append((dict(f=f, B=B), strokes[0]))
    elif how == "legend":
        keys = {}
        for sw in swatches:
            keys[(sw["color"], sw["dashed"])] = parse_cond(words_right_of(words, sw["x1"], sw["y"]))
        for s in strokes:
            k = keys.get((s["color"], s["dashed"]))
            if not k:
                raise RuntimeError(f"curve colour {s['color']} dashed={s['dashed']} has no legend key")
            out.append((dict(k), s))
    elif how == "endtext":
        for s in strokes:
            x, y = max(s["dense"], key=lambda p: p[0])
            txt = " ".join(w[4] for w in sorted(
                [w for w in words if x - 1 <= w[0] <= x + 6 and -9 <= (w[1] + w[3]) / 2 - y <= 9],
                key=lambda w: (w[1], w[0])))
            c = parse_cond(txt)
            if "f" not in c or "B" not in c:
                raise RuntimeError(f"curve ending at {x:.1f},{y:.1f}: end label {txt!r} is not an f/B pair")
            out.append((c, s))
    elif how == "textcolour":
        spans = [(sp["text"], sp["color"]) for b in fig["_page"].get_text("dict")["blocks"]
                 for l in b.get("lines", []) for sp in l["spans"]
                 if fig["_box"].contains(fitz.Rect(sp["bbox"]))]
        for s in strokes:
            hits = [t for t, cc in spans
                    if all(abs(((cc >> sh) & 255) / 255 - v) < 0.02 for sh, v in zip((16, 8, 0), s["color"]))]
            if len(hits) != 1:
                raise RuntimeError(f"curve colour {s['color']}: {len(hits)} same-coloured labels {hits}")
            c = parse_cond(hits[0])
            if "f" not in c or "B" not in c:
                raise RuntimeError(f"coloured label {hits[0]!r} is not an f/B pair")
            out.append((c, s))
    elif how == "order":
        # pv_b: style -> T (confirmed from the legend keys), frequencies ascending in loss.
        leg = {}
        for sw in swatches:
            leg[sw["dashed"]] = parse_cond(words_right_of(words, sw["x1"], sw["y"])).get("T")
        for dashed, T in fig["styles"].items():
            if leg.get(dashed) != T:
                raise RuntimeError(f"legend says dashed={dashed} is {leg.get(dashed)} C, config says {T}")
            group = [s for s in strokes if s["dashed"] == dashed]
            if len(group) != len(fig["series"]):
                raise RuntimeError(f"{len(group)} curves at {T} C, expected {len(fig['series'])}")
            xy = [to_xy(fig, s["dense"]) for s in group]
            lo = max(min(p[0] for p in c) for c in xy)
            hi = min(max(p[0] for p in c) for c in xy)
            if lo > hi:
                # disjoint spans: compare by the power-law line through each curve at a common B
                xq = math.sqrt(lo * hi)
                vals = [line_at(c, xq) for c in xy]
            else:
                xq = math.sqrt(lo * hi)
                vals = [curve_value(c, xq, True, True) for c in xy]
            order = sorted(range(len(group)), key=lambda i: vals[i])
            for f, i in zip(fig["series"], order):
                out.append((dict(f=f, T=T), group[i]))
    else:
        raise RuntimeError(f"unknown labelling {how}")
    return out


def line_at(xy, xq):
    """Straight log-log line through a curve's end points, evaluated at xq (ordering only)."""
    (x0, y0), (x1, y1) = min(xy), max(xy)
    b = math.log(y1 / y0) / math.log(x1 / x0)
    return y0 * (xq / x0) ** b


def to_points(fig, labelled):
    pts, curves = [], []
    for cond, s in labelled:
        samples = emit_samples(fig, s)
        for x, y in samples:
            if fig["kind"] == "pv_b":
                f, B, T = cond["f"], x * 1e-3, cond["T"]
            elif fig["kind"] == "pv_f":
                f, B, T = x, cond["B"], fig["T"]
            else:  # pv_t
                f, B, T = cond["f"], cond["B"], x
            pts.append(point(f, B, T, y * 1e3))
        curves.append(dict(cond=cond, xy=to_xy(fig, s["dense"]), n=len(samples)))
    return pts, curves


def point(f, B, T, pv):
    sig = lambda v, n=4: float(f"{v:.{n}g}")
    return {"magneticFluxDensity": {"frequency": sig(f, 6), "magneticFluxDensity": {"processed": {
        "label": "sinusoidal", "peak": sig(B), "offset": 0.0}}},
        "temperature": sig(T, 4), "value": sig(pv), "origin": "manufacturer"}


def physics_check(fig, curves):
    """Loss must rise with f (pv_b, per T) and with B (pv_f) at a common abscissa."""
    if fig["kind"] not in ("pv_b", "pv_f"):
        return
    key = "f" if fig["kind"] == "pv_b" else "B"
    groups = {}
    for c in curves:
        groups.setdefault(c["cond"].get("T"), []).append(c)
    for T, g in groups.items():
        g = sorted(g, key=lambda c: c["cond"][key])
        for a, b in zip(g, g[1:]):
            lo = max(min(p[0] for p in a["xy"]), min(p[0] for p in b["xy"]))
            hi = min(max(p[0] for p in a["xy"]), max(p[0] for p in b["xy"]))
            if lo > hi:
                continue
            xq = math.sqrt(lo * hi)
            va, vb = curve_value(a["xy"], xq, True, True), curve_value(b["xy"], xq, True, True)
            if not va < vb:
                raise RuntimeError(f"physics order violated: {key}={a['cond'][key]} gives {va:.4g} >= "
                                   f"{key}={b['cond'][key]} {vb:.4g} at x={xq:.4g}")


def table_check(mat, all_curves):
    """Read every curve at each printed table condition it covers."""
    out = []
    for f, B, T, pv in TABLE.get(mat, []):
        for fig, c in all_curves:
            k, cond = fig["kind"], c["cond"]
            if k == "pv_b" and abs(cond["f"] - f) < 1 and cond["T"] == T:
                v = curve_value(c["xy"], B * 1e3, True, True)
            elif k == "pv_t" and abs(cond["f"] - f) < 1 and abs(cond["B"] - B) < 1e-6:
                v = curve_value(c["xy"], T, False, fig["y"][0] == "log")
            elif k == "pv_f" and abs(cond["B"] - B) < 1e-6 and fig["T"] == T:
                v = curve_value(c["xy"], f, True, True)
            else:
                continue
            if v is None:
                continue
            out.append(dict(figure=f"p{fig['page']} {k}", f=f, B=B, T=T, table=pv,
                            curve=round(v, 1), ratio=round(v / pv, 3)))
    return out


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
                # A figure whose own axes or labels fail verification is dropped whole (and
                # reported); it never contributes a point. The grade still has to pass the
                # table checks with the figures that remain.
                try:
                    box, words, strokes, swatches, rep = read_figure(pg, fig)
                    fig["_page"], fig["_box"] = pg, box
                    labelled = label_curves(fig, words, strokes, swatches)
                    p, curves = to_points(fig, labelled)
                    physics_check(fig, curves)
                except RuntimeError as e:
                    figrep.append(dict(page=fig["page"], kind=fig["kind"], T=fig.get("T"),
                                       REJECTED=str(e)))
                    continue
                # A figure may not label two curves with the same condition (TDK's PE22 90 C
                # figure draws its 200 mT line in the 100 mT colour): that figure is dropped.
                keys = [tuple(sorted(c["cond"].items())) for c in curves]
                if len(set(keys)) != len(keys):
                    figrep.append(dict(page=fig["page"], kind=fig["kind"], T=fig.get("T"),
                                       REJECTED="two curves carry the same label"))
                    continue
                checks = table_check(mat, [(fig, c) for c in curves])
                rep["table"] = checks
                rep["curves"] = [dict(c["cond"], n=c["n"]) for c in curves]
                bad = [c for c in checks if abs(c["ratio"] - 1) > TABLE_TOL]
                if bad:
                    # #1006: a trace that misses its own data sheet's printed number is rejected,
                    # not adjusted -- the whole figure goes, with every curve in it.
                    rep["REJECTED"] = f"{len(bad)} table check(s) beyond {TABLE_TOL:.0%}"
                    figrep.append(rep)
                    continue
                pts += p
                all_curves += [(fig, c) for c in curves]
                figrep.append(rep)
            checks = table_check(mat, all_curves)
            report[mat] = dict(points=len(pts), figures=figrep, table=checks)
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
        else:
            ratios = [c["ratio"] for c in r["table"]]
            dropped = [f"p{f['page']} {f['kind']}{' T=%g' % f['T'] if f.get('T') is not None else ''}: {f['REJECTED']}"
                       for f in r["figures"] if "REJECTED" in f]
            print(f"{mat}: {r['points']} points, {len(r['table'])} table checks, "
                  f"ratio {min(ratios):.3f}..{max(ratios):.3f}"
                  + "".join(f"\n    figure dropped: {d}" for d in dropped))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
