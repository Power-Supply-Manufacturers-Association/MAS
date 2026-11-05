#!/usr/bin/env python3
"""Pv-vs-B core-loss curves for Samwha PL-13 and Proterial MB19D / MB20D / MB28D (ABT #1518 follow-up).

    python3 -I scripts/extract-samwha-proterial-mb-loss.py \
            --samwha-ev "<60_Ferrite and Powder Cores in EVs and (P)HEVs_Samwha Electronics.pdf>" \
            --proterial hj-b3-e.pdf --json points.json \
            [--advanced data/advanced_core_materials.ndjson] [--report report.json] [--overlay-dir DIR]

Why this exists
---------------
The stored points of these grades (extract-samwha-loss.py, extract-proterial-loss.py) come from
Pv-T figures only: Samwha PL-x sheets print three Pv-T curves (100k/200m, 200k/100m, 25k/200m) and
no Pv-B or Pv-f figure; for MB19D/MB20D/MB28D only the 100 kHz/200 mT Pv-T curve survived, because
extract-proterial-loss.py rejected every MB Pv-B figure on its minor-gridline checks. With one B per
frequency the Steinmetz beta is not identifiable. This script reads the makers' own Pv-B figures.

Sources (read 2026-11-05)
-------------------------
Samwha Electronics, "Ferrite and Powder Cores in EVs and (P)HEVs" (PowerPoint, Microsoft Print to
PDF, 2021-10-14), linked from http://www.samwha.co.kr/electronics_eng/0404.asp ("Download"):
    http://www.samwha.co.kr/electronics_eng/down/60_Ferrite%20and%20Powder%20Cores%20in%20EVs%20and%20(P)HEVs_Samwha%20Electronics.pdf
    1,880,876 B  sha256 014ae558c62e1069755e38bcd6a440f2ce998451c58367f47976511a8df31cef
    p7  table "Core loss (100kHz, 200mT)" PL-13 25/80/100/120 C = 400/300/340/400 kW/m3 (same values
        as the PL-13 material sheet); p8 left column "PL-13", figure "Core loss vs. Flux density":
        log-log, 10..1000 mT x 10..10000 kW/m3, 100/200/300 kHz, solid = 23 C, dashed = 100 C
        (the 23/100 C legend is a raster image inside the plot; read by eye on the overlay).
    Samwha's PL-5, PL-7, PL-11 have no Pv-B / Pv-f figure in any Samwha document found (material
    sheets, "Samwha Ferrite Cores_catalogue.pdf" pp. 5-7 = the same sheets); they are not read here.
Proterial "hj-b3-e" ferrite catalogue (see extract-proterial-loss.py for URL and sha256
56bc2d2e...): Pv-B figures "Core loss - Flux density", 25/50/100/200 kHz:
    MB19D p21 left 23 C, right 120 C     MB20D p23 left 23 C, right 130 C
    MB28D p25 left 23 C, right 60 C
Several of these have no text layer for some labels (title, ticks, kHz and temperature labels drawn
as outlines); the temperature then comes from PROT_FIGS (read by eye, shown on the overlay) and the
tick labels are checked as outline-glyph clusters instead of words.

Method -- vector, nothing is digitised from pixels
--------------------------------------------------
1. Gridlines: every thin horizontal/vertical stroke, hairline rectangle or thin filled polygon that
   spans >= 80 % of the plot frame, plus the frame edges. Each tick label (word centre, or for an
   outline-only figure the centre of its outline-glyph cluster, valued by the decades printed on the
   sibling figure) anchors the nearest line within LABEL_TOL as that decade. Lines between two
   decade anchors are assigned to m = 2..9 on the local decade (within SNAP_TOL; two lines claiming
   one m are both left out and listed -- Proterial p21/p25 draw two lines around 6000 kW/m3). The
   reading scale is piecewise log through all assigned lines (read like a paper chart between the
   gridlines around the point). Gates: decade lines within DECADE_TOL of one straight log scale;
   piecewise vs straight decade-fit reading of every curve point within CAL_TOL; <= 3 lines left
   out per axis. Proterial's minor grids are drawn unevenly (~1 pt), which is what made
   extract-proterial-loss.py drop these figures; the residuals are in the report.
2. Curves. Proterial: each curve is ONE stroked straight segment (0.84 pt line, or a 0.6 pt cubic on
   p23 whose control points are collinear -- checked, STRAIGHT_TOL). Samwha: each curve is a filled
   outline polygon (Print-to-PDF strokes); its centre line is the midpoint of the polygon's vertical
   cross-section, taken every 0.25 pt where the section is full-height (end caps excluded); dashed
   curves are the union of their dash polygons. Parts drawn outside the plot frame (Proterial
   draws two 25 kHz lines past the bottom edge, clipped in the rendering) are cut at the frame.
3. Labels: curves are ordered top -> bottom at a common B; that order must equal the label order
   top -> bottom (highest f on top) and the physics order (Pv rises with f at every common B; Pv
   rises with B along every curve). Where the kHz labels are words, each label must sit at the right
   end of the curve it names. Samwha solid/dashed curves of one frequency must share the hue.
4. Table check (#1006, Alf: tables are MAXIMA): the 100 kHz curve read at 200 mT against the printed
   Pcv(100 kHz, 200 mT) at the figure's temperature (Samwha's 23 C figure against the 25 C table
   value -- the sheet prints no 23 C value). A figure whose ratio is > 1 + TABLE_TOL is dropped;
   ratios below 1 are accepted and reported.
5. Points: each curve at its drawn start, at 100 mT and 200 mT when they lie strictly inside the drawn
   span, and at its drawn end. Never extrapolated. SI: B peak in T, Pv in W/m3, sine, offset 0.
6. Merge: each stored (f, B) series of the grade (advanced_core_materials.ndjson, Pv-T curves) is
   compared with the Pv-B curve of the same f at each figure temperature, at the series' B; it is
   kept when every comparison is within STORED_TOL (the stored value at the figure temperature is
   interpolated between the two stored points around it for this CHECK only, never output; a
   figure up to NEAR_T below the first stored temperature uses that first point). A series no Pv-B
   curve can check is kept: it comes from the same table-checked Pv-T figure.
"""
import argparse
import colorsys
import json
import math
import os
import re
import sys

import fitz  # PyMuPDF

DECADE_TOL = 1.5     # pt, decade lines vs the straight log scale through them (~4 % of a decade)
SNAP_TOL = 1.6       # pt, a minor gridline vs its m x 10^k on the local decade
LABEL_TOL = 2.5      # pt, tick label centre vs its decade line
DOUBLE_TOL = 1.0     # pt, a second line this close to a decade line is reported, not used
CAL_TOL = 0.06       # piecewise (paper-chart) vs straight decade-fit reading of any curve point
STRAIGHT_TOL = 0.15  # pt, Bezier curve vs its chord
TABLE_TOL = 0.10
STORED_TOL = 0.15
NEAR_T = 3.0
HUE_TOL = 0.06
END_TOL = 0.02     # a curve drawn to within 2 % of 200 mT is table-checked at its end

SAMWHA_TABLE = {"PL-13": {25: 400, 80: 300, 100: 340, 120: 400}}   # kW/m3, 100 kHz / 200 mT
PROT_TABLE = {   # kW/m3, 100 kHz / 200 mT (catalogue material pages; 23 C of MB19D/MB28D from p12)
    "MB19D": {23: 800, 60: 540, 80: 430, 100: 370, 120: 350, 140: 420},
    "MB20D": {23: 700, 100: 420, 130: 370, 150: 420},
    "MB28D": {23: 480, 60: 310, 80: 400, 100: 520, 120: 620},
}
# (grade, page, side, temperature C) -- side "L"/"R" = left/right lower panel
PROT_FIGS = [("MB19D", 21, "L", 23.0), ("MB19D", 21, "R", 120.0),
             ("MB20D", 23, "L", 23.0), ("MB20D", 23, "R", 130.0),
             ("MB28D", 25, "L", 23.0), ("MB28D", 25, "R", 60.0)]
PROT_FREQS = [200e3, 100e3, 50e3, 25e3]          # top -> bottom
PROT_DECADES = ((10.0, 1000.0), (1.0, 10000.0))  # x mT, y kW/m3 (printed on every MB Pv-B figure)
SAMWHA_DECADES = ((10.0, 1000.0), (10.0, 10000.0))


def lg(v):
    return math.log10(v)


# ----------------------------------------------------------------------------- geometry
def bez(p0, p1, p2, p3, n=24):
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0.x + b * p1.x + c * p2.x + d * p3.x, a * p0.y + b * p1.y + c * p2.y + d * p3.y))
    return out


def subpaths(d):
    """Flattened subpaths of a drawing: list of point lists ('re'/'qu' give closed 4-gons)."""
    out, cur = [], []
    for it in d["items"]:
        k = it[0]
        if k == "re":
            r = it[1]
            if cur:
                out.append(cur); cur = []
            out.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)])
            continue
        if k == "qu":
            q = it[1]
            if cur:
                out.append(cur); cur = []
            out.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y), (q.ul.x, q.ul.y)])
            continue
        p = it[1]
        if cur and (abs(cur[-1][0] - p.x) > 1e-3 or abs(cur[-1][1] - p.y) > 1e-3):
            out.append(cur); cur = []
        if not cur:
            cur.append((p.x, p.y))
        if k == "l":
            cur.append((it[2].x, it[2].y))
        elif k == "c":
            cur += bez(it[1], it[2], it[3], it[4])[1:]
        else:
            raise RuntimeError(f"unexpected path item {k}")
    if cur:
        out.append(cur)
    return out


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def dark(c):
    return c is not None and max(c) < 0.45


def gridlines(pg, frame):
    """Horizontal y's and vertical x's of every thin line spanning >= 80 % of the frame."""
    inside = fitz.Rect(frame.x0 - 2, frame.y0 - 2, frame.x1 + 2, frame.y1 + 2)
    H, V = [], []
    for d in pg.get_drawings():
        if not inside.contains(d["rect"]):
            continue
        stroke = dark(d.get("color")) and (d.get("width") or 0) <= 0.7
        fill = dark(d.get("fill"))
        if not (stroke or fill):
            continue
        for sp in subpaths(d):
            x0, y0, x1, y1 = bbox(sp)
            if y1 - y0 < (0.25 if stroke else 1.0) and x1 - x0 > 0.8 * frame.width:
                H.append((y0 + y1) / 2)
            elif x1 - x0 < (0.25 if stroke else 1.0) and y1 - y0 > 0.8 * frame.height:
                V.append((x0 + x1) / 2)
            elif stroke and len(sp) > 2:   # a polyline of grid strokes (p23: one path, many lines)
                for a, b in zip(sp, sp[1:]):
                    if abs(a[1] - b[1]) < 0.05 and abs(a[0] - b[0]) > 0.8 * frame.width:
                        H.append(a[1])
                    elif abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) > 0.8 * frame.height:
                        V.append(a[0])
    H += [frame.y0, frame.y1]
    V += [frame.x0, frame.x1]
    return dedupe(H), dedupe(V)


def dedupe(v, tol=0.3):
    v = sorted(v)
    out = []
    for x in v:
        if out and x - out[-1][-1] <= tol:
            out[-1].append(x)
        else:
            out.append([x])
    return [sum(g) / len(g) for g in out]


# ----------------------------------------------------------------------------- calibration
class LogScale:
    def __init__(self, pts):           # pts: [(value, pos)]
        xs = [lg(v) for v, _ in pts]
        ys = [p for _, p in pts]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        self.b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        self.a = my - self.b * mx
        self.res = max(abs(self.pos(v) - p) for v, p in pts)

    def pos(self, v):
        return self.a + self.b * lg(v)

    def val(self, p):
        return 10 ** ((p - self.a) / self.b)


class Piecewise:
    """Paper-chart scale: log-linear interpolation between the two calibrated gridlines around a
    position (end segments extended only to the frame edge, which is itself a gridline)."""
    def __init__(self, pts):           # pts: [(value, pos)], unique values
        self.k = sorted((p, lg(v)) for v, p in pts)
        g = [q[1] for q in self.k]
        if not (all(b > a for a, b in zip(g, g[1:])) or all(b < a for a, b in zip(g, g[1:]))):
            raise RuntimeError("calibrated gridlines are not monotonic")

    def _seg(self, p):
        i = next((j for j in range(len(self.k) - 1) if p <= self.k[j + 1][0]), len(self.k) - 2)
        return self.k[i], self.k[i + 1]

    def val(self, p):
        (p0, g0), (p1, g1) = self._seg(p)
        return 10 ** (g0 + (p - p0) * (g1 - g0) / (p1 - p0))

    def pos(self, v):
        x = lg(v)
        ks = sorted(self.k, key=lambda q: q[1])
        i = next((j for j in range(len(ks) - 1) if x <= ks[j + 1][1]), len(ks) - 2)
        (p0, g0), (p1, g1) = ks[i], ks[i + 1]
        return p0 + (x - g0) * (p1 - p0) / (g1 - g0)


def calibrate(axis, lines, labels, rep):
    """lines: gridline positions (frame edges included); labels: [(decade value, centre)] -- tick-label
    words, or outline-glyph cluster centres carrying the decade values printed on the figure.
    1. Each label anchors the nearest line within LABEL_TOL (the decade line). A second line within
       DOUBLE_TOL of it (Proterial: frame edge + a gridline drawn ~0.5-0.9 pt beside it) is reported.
    2. Between two decade anchors the interior lines are assigned to m = 2..9 on the local decade
       (log interpolation between the anchors); a line further than SNAP_TOL from its m, or two lines
       claiming one m, are left out of the calibration and listed.
    3. Reading scale: piecewise through the anchors and the assigned lines (a paper chart is read
       between the gridlines around the point). Reported: the straight decade-line fit residual and
       the residual of every assigned line against it."""
    if len(labels) < 3:
        raise RuntimeError(f"{axis}: {len(labels)} tick labels")
    anchors, doubles = [], []
    for v, c in labels:
        near = sorted((abs(p - c), p) for p in lines if abs(p - c) <= LABEL_TOL)
        if not near:
            raise RuntimeError(f"{axis}: no gridline within {LABEL_TOL} pt of the '{v:g}' label")
        anchors.append((v, near[0][1], near[0][0]))
        doubles += [(v, round(p, 2), round(abs(p - near[0][1]), 2)) for _, p in near[1:] if abs(p - near[0][1]) <= DOUBLE_TOL]
    anchors.sort(key=lambda a: a[0])
    straight = LogScale([(v, p) for v, p, _ in anchors])
    used = {round(p, 3) for _, p, _ in anchors} | {round(p, 3) for _, p, _ in doubles}
    assigned, dropped = [(v, p) for v, p, _ in anchors], []
    for (v0, p0, _), (v1, p1, _) in zip(anchors, anchors[1:]):
        loc = LogScale([(v0, p0), (v1, p1)])
        inner = [p for p in lines if min(p0, p1) + 0.3 < p < max(p0, p1) - 0.3 and round(p, 3) not in used]
        claim = {}
        for p in inner:
            m = min(range(2, 10), key=lambda k: abs(loc.pos(k * v0) - p))
            d = abs(loc.pos(m * v0) - p)
            if d > SNAP_TOL:
                dropped.append((round(p, 2), f"{d:.2f} pt from any m x {v0:g}"))
            else:
                claim.setdefault(m, []).append(p)
        for m, ps in sorted(claim.items()):
            if len(ps) > 1:
                dropped += [(round(p, 2), f"one of {len(ps)} lines claiming {m * v0:g}") for p in ps]
            else:
                assigned.append((m * v0, ps[0]))
    sc = Piecewise(assigned)
    sc.straight = straight
    sc.decades = [v for v, _, _ in anchors]
    minor = max(abs(straight.pos(v) - p) for v, p in assigned)
    rep[axis] = dict(decades=sc.decades, label_worst_pt=round(max(d for _, _, d in anchors), 2),
                     decade_fit_res_pt=round(straight.res, 2), pt_per_decade=round(abs(straight.b), 2),
                     lines_assigned=len(assigned), lines_dropped=dropped, double_lines=doubles,
                     worst_line_vs_decade_fit_pt=round(minor, 2))
    if straight.res > DECADE_TOL:
        raise RuntimeError(f"{axis}: decade lines {straight.res:.2f} pt off a straight log scale")
    if len(dropped) > 3:
        raise RuntimeError(f"{axis}: {len(dropped)} gridlines could not be assigned: {dropped}")
    return sc


def cal_spread(cx, cy, pts):
    """Worst relative difference in Pv between the piecewise reading and the straight decade-fit
    reading of a curve point (x error converted through the curve's local slope is not needed:
    both readings of B and of Pv are compared separately and the larger is returned)."""
    w = 0.0
    for x, y in pts:
        w = max(w, abs(cx.straight.val(x) / cx.val(x) - 1), abs(cy.straight.val(y) / cy.val(y) - 1))
    if w > CAL_TOL:
        raise RuntimeError(f"piecewise and straight calibrations differ by {w:.1%} on a curve point")
    return round(w, 4)


def glyph_clusters(pg, region, along):
    """Centres of outline-glyph clusters (filled dark paths) inside region; clusters split where the
    gap along `along` ('x' or 'y') exceeds 2.5 pt."""
    boxes = []
    for d in pg.get_drawings():
        if not dark(d.get("fill")) or not region.intersects(d["rect"]):
            continue
        for sp in subpaths(d):
            b = bbox(sp)
            if region.contains(fitz.Rect(b)) and (b[2] - b[0]) < 8 and (b[3] - b[1]) < 9:
                boxes.append(b)
    i0, i1 = (0, 2) if along == "x" else (1, 3)
    boxes.sort(key=lambda b: b[i0])
    groups = []
    for b in boxes:
        if groups and b[i0] - max(g[i1] for g in groups[-1]) <= 2.5:
            groups[-1].append(b)
        else:
            groups.append([b])
    return [((min(g[i0] for g in gr) + max(g[i1] for g in gr)) / 2) for gr in groups]


# ----------------------------------------------------------------------------- curves
def clip_to_frame(pts, frame):
    """Keep the part of a polyline that lies inside the frame's y range, cutting the crossing
    segments exactly at the edge (one entry and one exit at most: the curves are monotonic)."""
    def inside(p):
        return frame.y0 - 1e-6 <= p[1] <= frame.y1 + 1e-6

    def cut(a, b):
        yb = frame.y1 if max(a[1], b[1]) > frame.y1 + 1e-6 else frame.y0
        t = (yb - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), yb)

    out = [pts[0]] if inside(pts[0]) else []
    for a, b in zip(pts, pts[1:]):
        ia, ib = inside(a), inside(b)
        if ia and ib:
            out.append(b)
        elif not ia and ib:
            out += [cut(a, b), b]
        elif ia and not ib:
            out.append(cut(a, b))
            break
    return out


def y_at(pts, x):
    for a, b in zip(pts, pts[1:]):
        if min(a[0], b[0]) - 1e-6 <= x <= max(a[0], b[0]) + 1e-6 and b[0] != a[0]:
            return a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])
    return None


def centreline(polys, step=0.25):
    """Centre line of filled outline polygons: per x, the midpoint of the vertical cross-section.
    Sections shorter than 85 % of the median section (end caps, dash ends) are not used."""
    edges = [(a, b) for poly in polys for a, b in zip(poly, poly[1:] + poly[:1]) if a != b]
    x0 = min(p[0] for poly in polys for p in poly)
    x1 = max(p[0] for poly in polys for p in poly)
    secs = []
    x = x0 + step / 2
    while x < x1:
        ys = []
        for a, b in edges:
            if (a[0] - x) * (b[0] - x) < 0:
                ys.append(a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0]))
        if len(ys) >= 2:
            secs.append((x, min(ys), max(ys)))
        x += step
    hs = sorted(s[2] - s[1] for s in secs)
    med = hs[len(hs) // 2]
    return [(x, (lo + hi) / 2) for x, lo, hi in secs if hi - lo >= 0.85 * med and hi - lo <= 1.15 * med], med


def dash_centreline(polys, med):
    """Centre line of a dashed curve: a dash too short to have a full-height vertical section (a
    steep line) contributes its bounding-box centre (dashes are symmetric about the centre line);
    a longer piece contributes its full-height sections (centreline() with the solid curve's
    section height `med`). The line runs from the first to the last dash centre -- the outer half
    of the end dashes is not used, so nothing is extrapolated."""
    pts = []
    for poly in polys:
        x0, y0, x1, y1 = bbox(poly)
        if x1 - x0 > 6:
            sec, _ = centreline([poly])
            pts += [p for p in sec]
        else:
            pts.append(((x0 + x1) / 2, (y0 + y1) / 2))
    return sorted(pts), med


def line_fit_res(pts):
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sum((p[0] - mx) ** 2 for p in pts)
    a = my - b * mx
    return max(abs(a + b * p[0] - p[1]) for p in pts)


def reads(cx, cy, pts):
    """Points of one drawn curve: start, 100 mT and 200 mT if strictly inside, end. [(B mT, Pv kW/m3)]"""
    xs = [p[0] for p in pts]
    xa, xb = min(xs), max(xs)
    Ba, Bb = cx.val(xa), cx.val(xb)
    out = [(Ba, cy.val(y_at(pts, xa)))]
    for B in (100.0, 200.0):
        if Ba * 1.03 < B < Bb / 1.03:
            out.append((B, cy.val(y_at(pts, cx.pos(B)))))
    out.append((Bb, cy.val(y_at(pts, xb))))
    return out


def value_at(cx, cy, pts, B):
    y = y_at(pts, cx.pos(B))
    return None if y is None else cy.val(y)


def table_read(cx, cy, pts):
    """The 100 kHz curve at 200 mT for the table check, and the B it was read at. Proterial draws its
    lines to ~199 mT on the calibrated scale; a curve ending within END_TOL below 200 mT is read at
    its drawn end (loss rises with B, so that reading can only sit LOW against the table)."""
    v = value_at(cx, cy, pts, 200.0)
    if v is not None:
        return v, 200.0
    end = max(pts)
    Bend = cx.val(end[0])
    if 200.0 / (1 + END_TOL) <= Bend < 200.0:
        return cy.val(end[1]), Bend
    raise RuntimeError(f"the 100 kHz curve ends at {Bend:.1f} mT, short of 200 mT")


def check_order(cx, cy, curves, rep):
    """curves: [(label, pts)] top -> bottom; Pv must fall down the list at every common B, and rise
    with B along every curve."""
    for lab, pts in curves:
        ys = [p[1] for p in sorted(pts)]
        if any(b > a + 1e-6 for a, b in zip(ys, ys[1:])):
            raise RuntimeError(f"curve {lab}: loss does not rise with B")
    for (la, a), (lb, b) in zip(curves, curves[1:]):
        lo = max(min(p[0] for p in a), min(p[0] for p in b))
        hi = min(max(p[0] for p in a), max(p[0] for p in b))
        if lo >= hi:
            raise RuntimeError(f"curves {la} and {lb} share no B range")
        for k in range(11):
            x = lo + (hi - lo) * k / 10
            if not y_at(a, x) < y_at(b, x):
                raise RuntimeError(f"physics order violated: {la} not above {lb} at B = {cx.val(x):.1f} mT")


def point(f, B_mT, T, pv_kw):
    sig = lambda v, n=4: float(f"{v:.{n}g}")
    return {"magneticFluxDensity": {"frequency": sig(f, 6), "magneticFluxDensity": {"processed": {
        "label": "sinusoidal", "peak": sig(B_mT * 1e-3), "offset": 0.0}}},
        "temperature": sig(T), "value": sig(pv_kw * 1e3), "origin": "manufacturer"}


# ----------------------------------------------------------------------------- overlays
def overlay(doc_path, pno, frame, cx, cy, curves, pts, path):
    """Draw the calibration (decade lines, cyan), the read centre lines (magenta) and the output
    points (green rings) on a copy of the page and save the plot region at 300 dpi."""
    doc = fitz.open(doc_path)
    pg = doc[pno - 1]
    sh = pg.new_shape()
    for v in cx.decades:
        x = cx.pos(v); sh.draw_line((x, frame.y0 - 4), (x, frame.y1 + 4))
    for v in cy.decades:
        y = cy.pos(v); sh.draw_line((frame.x0 - 4, y), (frame.x1 + 4, y))
    sh.finish(color=(0, 0.75, 0.85), width=0.25)
    for _, c in curves:
        sh.draw_polyline(c)
    sh.finish(color=(1, 0, 1), width=0.3)
    for B, pv in pts:
        sh.draw_circle((cx.pos(B), cy.pos(pv)), 1.6)
    sh.finish(color=(0, 0.7, 0), width=0.5)
    sh.commit()
    clip = fitz.Rect(frame.x0 - 45, frame.y0 - 25, frame.x1 + 45, frame.y1 + 30)
    pg.get_pixmap(dpi=300, clip=clip).save(path)


# ----------------------------------------------------------------------------- Samwha PL-13
def samwha_pl13(path, rep, ovdir):
    doc = fitz.open(path)
    pg7, pg = doc[6], doc[7]
    flat7 = re.sub(r"\s+", " ", pg7.get_text())
    m = re.search(r"Core loss \(100kHz, 200mT\) Pcv kW/m3 25℃ (\d+) (\d+) (\d+) 80℃ (\d+) (\d+) (\d+) "
                  r"100℃ (\d+) (\d+) (\d+) 120℃ (\d+) (\d+) (\d+)", flat7)
    if not m or "PL-13 PL-15 PL-17YH" not in flat7:
        raise SystemExit("EV catalogue p7: PL-13 Pcv table not found")
    tab = {T: int(m.group(1 + 3 * i)) for i, T in enumerate((25, 80, 100, 120))}
    if tab != SAMWHA_TABLE["PL-13"]:
        raise SystemExit(f"EV catalogue p7: PL-13 table {tab} != {SAMWHA_TABLE['PL-13']}")
    words = pg.get_text("words")
    heads = [w for w in words if w[4] == "PL-13"]
    title = [w for w in words if w[4] == "Core" and any(u[4] == "vs." and abs(u[1] - w[1]) < 1 and 0 < u[0] - w[2] < 30
                                                        for u in words) and w[1] > 560 and w[0] < 200]
    if len(heads) != 1 or len(title) != 1 or not any(u[4] == "Flux" and abs(u[1] - title[0][1]) < 1 for u in words):
        raise SystemExit("EV catalogue p8: PL-13 'Core loss vs. Flux density' panel not found")
    col = fitz.Rect(0, title[0][3], 210, pg.rect.height - 20)   # PL-13 is the left column
    # frame: the black filled outline path of the plot box, x/y from the tick labels' extent
    H, V = [], []
    draws = [d for d in pg.get_drawings() if col.contains(d["rect"])]
    big = [d for d in draws if dark(d.get("fill")) and d["rect"].width > 120 and d["rect"].height > 150]
    fr = None
    for d in big:
        r = d["rect"]
        fr = r if fr is None or r.width * r.height > fr.width * fr.height else fr
    # the frame is drawn as filled 0.48 pt strips; its centre lines are the frame edges
    frame0 = fitz.Rect(fr.x0 + 0.24, fr.y0 + 0.24, fr.x1 - 0.24, fr.y1 - 0.24)
    H, V = gridlines(pg, frame0)
    frame = fitz.Rect(V[0], H[0], V[-1], H[-1])
    xl = [(float(w[4]), (w[0] + w[2]) / 2) for w in words if re.fullmatch(r"\d+", w[4])
          and frame.y1 + 2 < (w[1] + w[3]) / 2 < frame.y1 + 14 and frame.x0 - 8 < (w[0] + w[2]) / 2 < frame.x1 + 8]
    yl = [(float(w[4]), (w[1] + w[3]) / 2) for w in words if re.fullmatch(r"\d+", w[4])
          and frame.x0 - 25 < w[2] < frame.x0 and frame.y0 - 6 < (w[1] + w[3]) / 2 < frame.y1 + 6]
    frep = dict(source="Samwha EV catalogue p8, PL-13 'Core loss vs. Flux density'",
                frame=[round(v, 2) for v in frame])
    for axis, lab, dec in (("x", xl, SAMWHA_DECADES[0]), ("y", yl, SAMWHA_DECADES[1])):
        if (min(v for v, _ in lab), max(v for v, _ in lab)) != dec:
            raise SystemExit(f"PL-13 Pv-B: {axis} tick labels {sorted(v for v, _ in lab)} do not span {dec}")
    cx = calibrate("x", V, xl, frep)
    cy = calibrate("y", H, yl, frep)
    # coloured filled polygons inside the frame
    polys = []
    for d in draws:
        c = d.get("fill")
        if c is None or max(c) - min(c) < 0.15 or not frame.intersects(d["rect"]):
            continue
        for sp in subpaths(d):
            b = bbox(sp)
            if b[0] >= frame.x0 - 1 and b[2] <= frame.x1 + 1 and b[3] - b[1] > 2:
                polys.append((tuple(round(v, 3) for v in c), b, sp))
    solid = [p for p in polys if p[1][2] - p[1][0] > 30]
    dash = [p for p in polys if p[1][2] - p[1][0] <= 30]
    groups = {}
    for c, b, sp in dash:
        groups.setdefault(c, []).append(sp)
    solids = [(c, [sp]) for c, b, sp in solid]
    dashes = list(groups.items())
    if len(solids) != 3 or len(dashes) != 3:
        raise SystemExit(f"PL-13 Pv-B: {len(solids)} solid and {len(dashes)} dashed curves (expected 3 + 3)")
    freqs_words = sorted([w for w in words if re.fullmatch(r"\d+kHz", w[4]) and col.contains(fitz.Rect(w[:4]))],
                         key=lambda w: w[1])
    flabels = [float(w[4][:-3]) * 1e3 for w in freqs_words]
    if flabels != [300e3, 200e3, 100e3]:
        raise SystemExit(f"PL-13 Pv-B: kHz labels top->bottom {flabels}")
    out = {}
    for style, T, sets in (("solid", 23.0, solids), ("dashed", 100.0, dashes)):
        cl = []
        for c, ps in sets:
            pts, h = centreline(ps) if style == "solid" else dash_centreline(ps, None)
            pts = clip_to_frame(pts, frame)
            cl.append((c, pts, h))
        xm = (max(min(p[0] for p in pts) for _, pts, _ in cl) + min(max(p[0] for p in pts) for _, pts, _ in cl)) / 2
        cl.sort(key=lambda t: y_at(t[1], xm) if y_at(t[1], xm) is not None else 1e9)
        named = [(f"{f / 1e3:g}kHz {T:g}C", pts) for f, (_, pts, _) in zip(flabels, cl)]
        check_order(cx, cy, named, frep)
        out[style] = (T, [(f, c, pts, h) for f, (c, pts, h) in zip(flabels, cl)])
    # each solid label word sits at the right end of its solid curve
    for f, c, pts, h in out["solid"][1]:
        end = max(pts)
        w = [w for w in freqs_words if float(w[4][:-3]) * 1e3 == f][0]
        if not (0 < w[0] - end[0] < 12 and abs((w[1] + w[3]) / 2 - end[1]) < 8):
            raise SystemExit(f"PL-13 Pv-B: label {w[4]} is not at the end of the {f / 1e3:g} kHz solid curve")
    # dashed and solid curves of one frequency share a hue
    for (f, cs, _, _), (_, cd, _, _) in zip(out["solid"][1], out["dashed"][1]):
        hs, hd = colorsys.rgb_to_hsv(*cs)[0], colorsys.rgb_to_hsv(*cd)[0]
        if min(abs(hs - hd), 1 - abs(hs - hd)) > HUE_TOL:
            raise SystemExit(f"PL-13 Pv-B: {f / 1e3:g} kHz solid/dashed hues differ ({hs:.3f} vs {hd:.3f})")
    figs = []
    for style in ("solid", "dashed"):
        T, cl = out[style]
        frep_s = json.loads(json.dumps(frep))
        frep_s.update(T=T, style=style, curves=[])
        pts_all, ov_pts = [], []
        for f, c, pts, h in cl:
            r = reads(cx, cy, pts)
            frep_s["curves"].append(dict(f=f, n=len(r), straight_res_pt=round(line_fit_res(pts), 3),
                                         section_pt=round(h, 2) if h else None, B_span_mT=[round(r[0][0], 1), round(r[-1][0], 1)],
                                         cal_spread=cal_spread(cx, cy, pts)))
            pts_all += [point(f, B, T, pv) for B, pv in r]
            ov_pts += r
        v, Bt = table_read(cx, cy, [p for f, _, p, _ in cl if f == 100e3][0])
        Ttab = 25 if T == 23.0 else int(T)
        frep_s["table"] = dict(T_table=Ttab, table=tab[Ttab], curve=round(v, 1), read_at_mT=round(Bt, 1), ratio=round(v / tab[Ttab], 3))
        if ovdir:
            p = os.path.join(ovdir, f"PL-13_EVcat_p8_{int(T)}C.png")
            overlay(path, 8, frame, cx, cy, [(f, p_) for f, _, p_, _ in cl], ov_pts, p)
            frep_s["overlay"] = p
        figs.append((frep_s, pts_all, [(f, p_) for f, _, p_, _ in cl], cx, cy))
    return figs


# ----------------------------------------------------------------------------- Proterial MB
def prot_panel(pg, side):
    """The lower-left / lower-right panel frame (0.6 pt panel rectangle) and its plot frame."""
    panels = [d["rect"] for d in pg.get_drawings() if d.get("color") and d["items"][0][0] == "re"
              and abs((d.get("width") or 0) - 0.6) < 0.05 and d["rect"].width > 150 and d["rect"].height > 150
              and d["rect"].y0 > pg.rect.height / 2]
    panels.sort(key=lambda r: r.x0)
    if len(panels) != 2:
        raise RuntimeError(f"{len(panels)} lower panels")
    panel = panels[0 if side == "L" else 1]
    frames = [d["rect"] for d in pg.get_drawings() if d.get("color") and d["items"][0][0] == "re"
              and len(d["items"]) == 1 and 0.8 <= (d.get("width") or 0) <= 1.3 and panel.contains(d["rect"])
              and d["rect"].width > 100]
    if len(frames) != 1:
        raise RuntimeError(f"{len(frames)} plot frames in the panel")
    return panel, frames[0]


def prot_curves(pg, frame):
    out = []
    for d in pg.get_drawings():
        c = d.get("color")
        w = d.get("width") or 0
        if not dark(c) or not (0.55 < w < 1.0) or d.get("fill") is not None:
            continue
        r = d["rect"]
        if not (frame.x0 < r.x0 and r.x1 < frame.x1 and r.y0 < frame.y1 and r.y1 > frame.y0):
            continue
        if len(d["items"]) != 1 or d["items"][0][0] not in "lc":
            continue
        it = d["items"][0]
        if it[0] == "l":
            pts = [(it[1].x, it[1].y), (it[2].x, it[2].y)]
            dev = 0.0
        else:
            pts = bez(*it[1:5], n=64)
            a, b = pts[0], pts[-1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            dev = max(abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L for p in pts)
            if dev > STRAIGHT_TOL:
                raise RuntimeError(f"a Bezier curve deviates {dev:.2f} pt from straight")
        if pts[0][0] > pts[-1][0]:
            pts = pts[::-1]
        if not (pts[-1][0] - pts[0][0] > 10 and pts[0][1] - pts[-1][1] > 5):
            continue     # not a rising curve (legend keys, boxes)
        out.append((clip_to_frame(pts, frame), dev, (r.y1 > frame.y1 + 0.5)))
    return out


def proterial(path, rep, ovdir):
    doc = fitz.open(path)
    figs = []
    for mat, pno, side, T in PROT_FIGS:
        pg = doc[pno - 1]
        head = re.sub(r"\s+", "", doc[pno - 2].get_text())
        if "Material：" + mat not in head and "Material:" + mat not in head:
            raise SystemExit(f"p{pno - 1} is not the {mat} page")
        frep = dict(source=f"Proterial hj-b3-e p{pno} {'left' if side == 'L' else 'right'} 'Core loss - Flux density'",
                    grade=mat, T=T)
        try:
            panel, frame = prot_panel(pg, side)
            frep["frame"] = [round(v, 2) for v in frame]
            words = [w for w in pg.get_text("words") if panel.contains(fitz.Rect(w[:4]))]
            H, V = gridlines(pg, frame)
            xl = [(float(w[4]), (w[0] + w[2]) / 2) for w in words if re.fullmatch(r"\d+", w[4])
                  and frame.y1 + 2 < (w[1] + w[3]) / 2 < frame.y1 + 14]
            yl = [(float(w[4]), (w[1] + w[3]) / 2) for w in words if re.fullmatch(r"\d+", w[4])
                  and frame.x0 - 25 < w[2] < frame.x0 + 1 and frame.y0 - 6 < (w[1] + w[3]) / 2 < frame.y1 + 6]
            for axis, lab, dec in (("x", xl, PROT_DECADES[0]), ("y", yl, PROT_DECADES[1])):
                if lab and (min(v for v, _ in lab), max(v for v, _ in lab)) != dec:
                    raise RuntimeError(f"{axis} tick labels {sorted(v for v, _ in lab)} do not span {dec}")
            sc = {}
            for axis, lab, region, along, lines, dec in (
                    ("x", xl, fitz.Rect(frame.x0 - 12, frame.y1 + 2, frame.x1 + 12, frame.y1 + 14), "x", V, PROT_DECADES[0]),
                    ("y", yl, fitz.Rect(frame.x0 - 26, frame.y0 - 6, frame.x0 - 1, frame.y1 + 6), "y", H, PROT_DECADES[1])):
                decs = [10.0 ** k for k in range(round(lg(dec[0])), round(lg(dec[1])) + 1)]
                kind = "words"
                if not lab:
                    cen = sorted(glyph_clusters(pg, region, along))
                    if len(cen) != len(decs):
                        raise RuntimeError(f"{axis}: {len(cen)} outline tick-label clusters for {len(decs)} decades")
                    lab = list(zip(decs if along == "x" else decs[::-1], cen))
                    kind = "outline glyph clusters (values read by eye: same decades as the sibling figure)"
                elif sorted(v for v, _ in lab) != decs:
                    raise RuntimeError(f"{axis}: tick-label words {sorted(v for v, _ in lab)} != {decs}")
                sc[axis] = calibrate(axis, lines, lab, frep)
                frep[axis]["label_kind"] = kind
            cx, cy = sc["x"], sc["y"]
            # temperature label: a word when present, else the PROT_FIGS value (read by eye)
            tw = [w[4] for w in words if re.fullmatch(r"-?\d+℃", w[4]) and frame.contains(fitz.Rect(w[:4]))]
            if tw:
                if float(tw[0][:-1]) != T or len(tw) != 1:
                    raise RuntimeError(f"temperature label {tw} != {T:g} C")
                frep["T_label"] = "word"
            else:
                frep["T_label"] = "outline (read by eye from the overlay)"
            cs = prot_curves(pg, frame)
            if len(cs) != 4:
                raise RuntimeError(f"{len(cs)} curves (expected 4)")
            xm = (max(c[0][0][0] for c in cs) + min(c[0][-1][0] for c in cs)) / 2   # inside every curve
            cs.sort(key=lambda c: y_at(c[0], xm))
            named = [(f"{f / 1e3:g}kHz", c[0]) for f, c in zip(PROT_FREQS, cs)]
            check_order(cx, cy, named, frep)
            # kHz label words (where present) at the right end of the curve they name
            kw = [w for w in words if re.fullmatch(r"\d+kHz", w[4]) and frame.contains(fitz.Rect(w[:4]))]
            for w in kw:
                f = float(w[4][:-3]) * 1e3
                end = [c[0][-1] for ff, c in zip(PROT_FREQS, cs) if ff == f][0]
                if not (-3 < w[0] - end[0] < 25 and abs((w[1] + w[3]) / 2 - end[1]) < 10):
                    raise RuntimeError(f"label {w[4]} is not at the end of the {f / 1e3:g} kHz curve")
            frep["kHz_label_words"] = sorted(w[4] for w in kw)
            frep["curves"], pts_all, ov = [], [], []
            for f, (pts, dev, clipped) in zip(PROT_FREQS, cs):
                r = reads(cx, cy, pts)
                frep["curves"].append(dict(f=f, n=len(r), bezier_dev_pt=round(dev, 3), clipped_at_frame=clipped,
                                           B_span_mT=[round(r[0][0], 1), round(r[-1][0], 1)],
                                           cal_spread=cal_spread(cx, cy, pts)))
                pts_all += [point(f, B, T, pv) for B, pv in r]
                ov += r
            v, Bt = table_read(cx, cy, cs[1][0])
            Tt = int(T)
            if Tt not in PROT_TABLE[mat]:
                raise RuntimeError(f"no printed Pcv at {T:g} C")
            frep["table"] = dict(T_table=Tt, table=PROT_TABLE[mat][Tt], curve=round(v, 1), read_at_mT=round(Bt, 1),
                                 ratio=round(v / PROT_TABLE[mat][Tt], 3))
            if ovdir:
                p = os.path.join(ovdir, f"{mat}_hj-b3-e_p{pno}{side}_{int(T)}C.png")
                overlay(path, pno, frame, cx, cy, named, ov, p)
                frep["overlay"] = p
            figs.append((frep, pts_all, named, cx, cy))
        except RuntimeError as e:
            frep["REJECTED"] = str(e)
            figs.append((frep, [], [], None, None))
    return figs


# ----------------------------------------------------------------------------- merge
def stored_points(adv_path, names):
    out = {}
    for line in open(adv_path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("name") in names:
            pts = [p for grp in r.get("volumetricLosses", {}).get("default", []) if isinstance(grp, list) for p in grp]
            out[r["name"]] = (r["manufacturerInfo"]["name"], pts)
    return out


def key(p):
    m = p["magneticFluxDensity"]
    return (m["frequency"], m["magneticFluxDensity"]["processed"]["peak"])


def stored_at(pts, f, B, T):
    """Stored value at (f, B) interpolated in T between the two stored points around T (check only).
    A figure temperature up to NEAR_T below the first stored temperature (Samwha: 23 C figure, Pv-T
    curves from 25 C) is compared with that first stored point. Returns (value, how)."""
    s = sorted((p["temperature"], p["value"]) for p in pts if key(p) == (f, B))
    for (t0, v0), (t1, v1) in zip(s, s[1:]):
        if t0 <= T <= t1:
            return (v0 + (v1 - v0) * (T - t0) / (t1 - t0) if t1 > t0 else v0), f"interp {t0:g}..{t1:g} C"
    if s and 0 < s[0][0] - T <= NEAR_T:
        return s[0][1], f"stored {s[0][0]:g} C point"
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samwha-ev", required=True)
    ap.add_argument("--proterial", required=True)
    ap.add_argument("--advanced", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                                                       "advanced_core_materials.ndjson"))
    ap.add_argument("--json", required=True)
    ap.add_argument("--report")
    ap.add_argument("--overlay-dir")
    a = ap.parse_args()
    if a.overlay_dir:
        os.makedirs(a.overlay_dir, exist_ok=True)
    report = {}
    figs = {"PL-13": samwha_pl13(a.samwha_ev, report, a.overlay_dir)}
    for fr in proterial(a.proterial, report, a.overlay_dir):
        figs.setdefault(fr[0]["grade"], []).append(fr)
    stored = stored_points(a.advanced, set(figs))
    result, rc = [], 0
    for mat, fl in figs.items():
        manu, old = stored[mat]
        new, mrep = [], dict(figures=[], stored_checks=[])
        for frep, pts, named, cx, cy in fl:
            if "REJECTED" not in frep and frep["table"]["ratio"] > 1 + TABLE_TOL:
                frep["REJECTED"] = (f"100 kHz/200 mT reads {frep['table']['curve']} vs table "
                                    f"{frep['table']['table']} (ratio {frep['table']['ratio']})")
            mrep["figures"].append(frep)
            if "REJECTED" in frep:
                print(f"{mat}: figure dropped: {frep['source']}: {frep['REJECTED']}")
                continue
            new += pts
            # stored 100 kHz / 200 mT Pv-T points vs this figure's 100 kHz curve at 200 mT
            sv, how = stored_at(old, 100000.0, 0.2, frep["T"])
            if sv is not None:
                mrep["stored_checks"].append(dict(T=frep["T"], f=100000.0, B=0.2, stored=round(sv / 1e3, 1), how=how,
                                                  figure=frep["table"]["curve"],
                                                  ratio=round(frep["table"]["curve"] * 1e3 / sv, 3)))
            # other stored conditions that coincide with a Pv-B curve (Samwha 200 kHz / 100 mT)
            for f, c in named:
                fz = f if isinstance(f, float) else float(re.match(r"([\d.]+)kHz", f).group(1)) * 1e3
                for (sf, sB) in sorted({key(p) for p in old}):
                    if sf == fz and (sf, sB) != (100000.0, 0.2):
                        y = value_at(cx, cy, c, sB * 1e3)
                        sv2, how2 = stored_at(old, sf, sB, frep["T"])
                        if y is not None and sv2 is not None:
                            mrep["stored_checks"].append(dict(T=frep["T"], f=sf, B=sB, stored=round(sv2 / 1e3, 1), how=how2,
                                                              figure=round(y, 1), ratio=round(y * 1e3 / sv2, 3)))
        if not new:
            mrep["REJECTED"] = "no accepted Pv-B figure"
            report[mat] = mrep
            print(f"{mat}: no accepted Pv-B figure; nothing written")
            rc = 1
            continue
        # per stored series (f, B): dropped when any check of it is off by more than STORED_TOL;
        # a series no Pv-B curve can check (Samwha 25 kHz / 200 mT) is kept -- it comes from the same
        # table-checked Pv-T figure as the checked series
        bad = {(c["f"], c["B"]) for c in mrep["stored_checks"] if abs(c["ratio"] - 1) > STORED_TOL}
        keep = [p for p in old if key(p) not in bad]
        mrep["stored_series"] = {f"{f / 1e3:g}kHz/{B * 1e3:g}mT": dict(
            n=sum(key(p) == (f, B) for p in old),
            checks=[c["ratio"] for c in mrep["stored_checks"] if (c["f"], c["B"]) == (f, B)],
            kept=(f, B) not in bad) for f, B in sorted({key(p) for p in old})}
        for f, B in sorted(bad):
            print(f"{mat}: stored {f / 1e3:g} kHz/{B * 1e3:g} mT series disagrees with the Pv-B figure "
                  f"beyond {STORED_TOL:.0%}; NOT kept")
        pts = keep + new
        fs = sorted({key(p)[0] for p in pts}); Bs = sorted({key(p)[1] for p in pts}); Ts = sorted({p["temperature"] for p in pts})
        mrep.update(points=len(pts), stored=len(keep), new=len(new), frequencies=fs, flux_densities=Bs, temperatures=Ts)
        report[mat] = mrep
        result.append({"name": mat, "manufacturerInfo": {"name": manu}, "volumetricLosses": {"default": [pts]}})
        print(f"{mat}: {len(pts)} points ({len(keep)} stored + {len(new)} new), {len(fs)} f, {len(Bs)} B, {len(Ts)} T; "
              f"table {[f['table']['ratio'] for f in mrep['figures'] if 'table' in f and 'REJECTED' not in f]}; "
              f"stored checks {[c['ratio'] for c in mrep['stored_checks']]}")
    json.dump(result, open(a.json, "w"), indent=1)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
