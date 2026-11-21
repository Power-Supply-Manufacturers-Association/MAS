#!/usr/bin/env python3
"""Reversible permeability mu_rev(H_DC, T) of ferrites from their manufacturers' data sheets, written as
permeability.reversible points (TDK and Ferroxcube), and incremental permeability mu_Delta(H_DC, T), written as
permeability.incremental points (Fair-Rite, Magnetics, DMEGC, TDG).

WHY
    A ferrite's loss and small-signal inductance under DC bias follow its reversible permeability: the slope of a
    vanishing AC excursion around the DC operating point, MAS `permeability.reversible`. It is kept apart from
    `permeability.initial`, whose DC-bias dependence consumers integrate into the B(H) curve: a reversible
    permeability integrated that way undercounts B (it leaves out the irreversible wall motion).

WHAT IT READS
    The figures' vector paths (lines and cubic Beziers, evaluated exactly), nothing traced from pixels. Log axes
    are calibrated on each figure's own gridlines: decade lines are found from the spacing pattern, every gridline
    must sit on a + b log10(m 10^k), m = 1..9, within GRID_TOL, and the decade exponents are read from the tick
    labels (superscripts told apart by font size) and must agree with one another; otherwise the figure is refused.

    Figures drawn with a small rigid rotation (Ferroxcube 3E25) are turned back square first: the angle is the one
    shared by most long thin lines of the figure, and counts only when horizontal and vertical gridlines both show
    it; every check below then applies unchanged. One figure is one plot: the horizontal gridlines sharing the most
    common x-extent, kept only inside the most common y-extent of the verticals there, so a neighbouring plot
    stacked above or below with almost the same x-extent (the 2025 Ferroxcube sheets, 3F37) is not read into it.
    The last gridline closes the axis but need not be a decade (DMEGC R10KC ends at 500 A/m): it counts as a decade
    line only if it sits a whole number of decades (from the decade lines inside) from the first, within GRID_TOL.

    Two per-figure opt-ins relax ONE rule for the named figures only (approved by Alf, 2026-11-21); never defaults:
      - DECADE_ONLY_X (Magnetics R, P, F): the 100-1000 A/m decade of these H axes draws a second set of minor
        gridlines, up to 0.61 pt from the first, one set off the log grid. Their H axis is calibrated on its decade
        lines alone: the first line and every line opening a step >= 0.8 of the widest (a decade opens with its
        widest step, 1 -> 2), plus the closing line if a whole number of decades out; at least 3 decade lines, each
        within GRID_TOL of the fitted decade spacing, labels as above. Minor lines are not checked; the y axis keeps
        the full check. (Magnetics M is not included: its y axis's top decade is drawn short, a different fault.)
      - GRID_BY_COLOUR (DMEGC DMR50): its grid is stroked 1.3 pt wide and its curve 1.59 pt, so the width rule
        (gridlines <= 0.8 pt, curves >= 1.5x the widest gridline) cannot separate them. Gridlines are then the long
        axis-parallel lines of any width; those inside the plot (not on its frame) must all share one colour, and a
        curve is a stroke in none of the grid and frame colours, at least MIN_COLOUR_DISTANCE (RGB) from each of them.

FERROXCUBE ("Reversible permeability as a function of magnetic field strength")
    Measured on ungapped ring cores: the material curve itself. Points are read off the curve on a fixed H grid
    inside the drawn range (log-log interpolation between evaluated path points); nothing is fitted. Where the
    curve is flat within FLAT_TOL over its first drawn decade, the left-end value is also written at H = 0. The
    temperature is the one the figure or caption states; none is written when it states none.

FAIR-RITE ("Incremental Permeability vs Field Strength", raster images on the material pages)
    Measured on 18/10/6 mm toroids at 25 C and 10 kHz (the pages' stated conditions); Fair-Rite names the
    quantity incremental permeability (mu_Delta), so it is written to permeability.incremental, not reversible.
    The images have no text layer: the axis end values are the ones printed on each image (FAIRRITE_AXES),
    and the gridlines found in the image must form exactly that many log decades with the log minor pattern
    (within RASTER_GRID_TOL px), or the image is refused. The curve is the stroke at least 2 px thick, read
    column by column between the gridlines (rows of horizontal gridlines are masked; a column that is a
    vertical gridline is skipped). H is converted from oersted (1 Oe = 1000/(4 pi) A/m). Fair-Rite 75 prints its
    left H end as "0.0" (sic): FAIRRITE_AXES takes it as 0.01 Oe, inferred from the neighbouring 0.1 and 1.0 labels
    (decades step by x10), not printed; FAIRRITE_AXIS_NOTES carries that into the provenance.

MAGNETICS ("PERMEABILITY vs. DC BIAS", vector figure on each material's page of the 2025 Ferrite Catalog)
    The page of each grade is fixed (MAGNETICS_PAGES) and must carry "<grade> Material" and exactly one such title.
    The plot is the framed grid under the title; one curve, starting at the initial permeability, so ungapped. The
    figure states no temperature, frequency or core and names the quantity only "permeability": it is written to
    permeability.incremental (a DC-biased small-signal permeability that is not stated to be reversible) without a
    temperature, read off the vector path as for Ferroxcube (H = 0 written only where the first decade is flat).

DMEGC ("Incremental Permeability mu_Delta" vs "Magnetic Field Strength H (A/m)", material characteristics sheets)
    Measured on the sheets' standard toroid, ungapped; written to permeability.incremental. The plot is located by its
    vertical y-axis title and the H-axis title under it. Each curve gets the temperature the plot states: one curve
    and one "T = 25 C" label inside the plot, or a legend in which every "<T> C" entry has exactly one short
    horizontal stroke just left of it; a curve is matched to an entry by its stroke colour, which must be unique and
    must match exactly one drawn curve (one curve per legend entry). A plot stating no temperature must have one
    curve, written without a temperature. A curve that rises with H is refused on its own; the others are kept.

TDK ("DC magnetic bias", gapped cores, mu_e = 50 ... 1000 (1500), 25 C and often 100 C)
    TDK draws the reversible permeability of GAPPED cores only; the gap is taken out by Ampere, with no assumed
    B-H curve. Curve i has the gap term g_i = 1/mu_e0,i - 1/mu_i, mu_e0,i its drawn zero-bias level at 25 C and
    mu_i the table value (same core, same g_i, at other temperatures). A material level L shows on curve i as
    mu_rev,e = 1/(1/L + g_i), reached at H_DC,i; all curves at that level share the material state (H, B), so
    H_DC,i = H + (B/mu0) g_i is a line in g_i, fitted with sigma = 1 % of H_DC (log-axis reading). B (the slope) is
    well determined; H (the intercept) is a small difference of large numbers, so a figure is accepted only when
    it is solid:
      - a level is kept when >= MIN_CURVES curves show it and its H is >= MIN_SIGNIFICANCE sigma, sigma scaled by
        the curves' observed disagreement; the curves may disagree by at most MAX_DISAGREEMENT;
      - the first kept level is >= ONSET_LEVEL of mu_rev(0) (the onset of the drop is observed, not extrapolated);
      - the solved field rises as the permeability falls; the smooth fit has chi2/dof <= MAX_CHI2;
      - mu_rev(Hc/2) >= REVERSIBLE_FLOOR mu_rev(0) with the table's coercive field (a reversible permeability
        changes on the scale of the coercive field: a figure whose knees all sit at one flux density, as drawn by a
        model, fails here);
      - at other temperatures each curve's drawn level must lie within MAX_PLACEMENT of where its 25 C gap and
        mu_i(T) (the data sheet's mu_i(T) curve, as tabulated in the database) put it; the curve is read as a ratio
        to its own drawn level.
    Accepted levels are smoothed with mu_rev(0) / (1 + (H/H0)^c)^k (even in H, zero slope at H = 0) and sampled from
    H = 0 to the largest solved field; mu_rev(0) is mu_i at 25 C and mu_i(T) otherwise.

TDK single-curve figures (one curve on an RM core with a small residual gap: N30, T35, T37, T38, T65)
    No second curve to solve against, so the material B(H) is taken from the same data sheet's 25 C "Dynamic
    magnetization curves" loop: its midline (mean of the rising and falling branches) on axes whose end values are
    the printed ones (TDK_LOOP_AXES; the evenly spaced gridlines must match). H_DC = H + g B(H)/mu0, g = 1/mu_e0 -
    1/mu_i. Refused if the midline is off-centre at B -> 0 (> LOOP_CENTRE_TOL Hc), does not reach LOOP_MIN_B, the
    un-gapped curve rises, or mu_rev(Hc/2) < REVERSIBLE_FLOOR. Less certain than the multi-curve solve: tried on each
    curve of N87, N49, N48 and N51 alone, it reproduces their multi-curve result within 0.04-0.10 of mu/mu0 for the
    smallest gap; the provenance says so.

TDG ("HDC Limit-mu_e", 2006 MnZn catalogue, archived by the Wayback Machine; TDG_PAGES)
    For gapped cores of effective permeability mu_e, two lines give the DC field H_DC at which the permeability has
    dropped 20 % and 40 % (legend: a short stroke left of each label; the two lines are told apart by dash pattern).
    The catalogue's glossary names a permeability under DC bias "incremental permeability", so the result is written
    to permeability.incremental. Each line's vertices (the plotted points; the lines are straight segments) are read
    on log axes calibrated as above. The gap is taken out by Ampere as for TDK, with the level read as the MATERIAL
    level L = 0.8 and 0.6 mu_i (TDG_LEVELS): each mu_e has g = 1/mu_e - 1/mu_i, and H_DC = H + (B/mu0) g is fitted as
    a line in g (ampere_line, sigma = READ_SIGMA of H_DC); H is the intercept, B the slope times mu0. Refused unless
    each line has >= MIN_CURVES points, H >= MIN_SIGNIFICANCE sigma (sigma scaled by the observed disagreement), the
    disagreement <= MAX_DISAGREEMENT, and the solved H rises from the 0.8 to the 0.6 level. The figure starts at a
    20 % drop, so the onset rule holds by construction. mu_i is the sheet's table value; the mu(Hc/2) >=
    REVERSIBLE_FLOOR check needs the table's Hc, and a sheet with a coercive-field row is refused (not read yet);
    TD3's sheet has none, so the check is not applied. Only three points are written: H = 0 (mu_i) and the two
    solved points, nothing interpolated, with no temperature or frequency (the figure states none).

THE CURVE'S START AGAINST THE RECORD'S mu_i (every maker)
    Before a grade is accepted, its curve at its lowest H (H = 0 where written), at the curve temperature nearest
    25 C, must lie within MUI_START_TOL (+-25 %) of the record's zero-bias permeability.initial at the temperature
    nearest 25 C (initial may be one object or a list; a record whose mu_i states no temperature gives its one nominal
    value; more than one value at that temperature is refused). Otherwise the figure was misread or belongs to another
    material, and the grade is refused (Fair-Rite 97: the image starts at 2558 against the record's mu_i 2016 at 20 C).

PATCHING
    Only the one record with the grade's name, its maker (EPCOS for TDK) and material == "ferrite" is patched; the
    makers also sell non-ferrite materials (Magnetics: powder cores) that a ferrite curve must never touch, and more
    than one matching record is an error. The provenance entry for the written field is replaced. The record's
    manufacturerInfo.datasheetUrl is set to the digitised source (Fair-Rite: the material page) only when absent; an
    existing one is never overwritten, and every difference between it and the digitised source is printed.

Usage:
    python3 scripts/digitize-reversible-permeability.py --cache DIR [--patch data/core_materials.ndjson] [GRADE ...]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import urllib.request

import numpy as np
import fitz  # PyMuPDF
from scipy.optimize import least_squares

MU0 = 4e-7 * np.pi
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
TDK_BASE = 'https://www.tdk-electronics.tdk.com/download/'
FXC_BASE = 'https://www.ferroxcube.com/upload/media/product/file/MDS/'
FR_BASE = 'https://fair-rite.com/wp-content/uploads/2020/06/'
FR_PAGE = 'https://fair-rite.com/{grade}-material-data-sheet/'
MAG_URL = 'https://www.acalbfi.com/media/pdf/'
MAGNETICS_PAGES = {'R': 7, 'P': 8, 'F': 9, 'J': 15, 'W': 16, 'M': 17}   # PDF pages of the 2025 Ferrite Catalog
# Magnetics grades whose H axis is calibrated on its decade lines only (see the docstring): their 100-1000 A/m decade
# draws a second set of minor gridlines, up to 0.61 pt from the first and one set off the log grid. Opt-in per grade,
# approved for these three figures only (M is not: its y axis is drawn short, a different fault); the y axis keeps
# the full check
# grade -> grade whose figure the catalogue draws identically (checked on every run; the provenance says so)
MAGNETICS_SHARED_FIGURE = {'P': 'R'}
SHARED_FIGURE_RTOL = 1e-3   # same vector path; each page's own axis calibration differs by ~2e-4
DECADE_ONLY_X = {'R', 'P', 'F'}
# DMEGC grades whose gridlines are told from the curves by stroke colour, not width (see the docstring): DMR50 draws
# its grid 1.3 pt wide and its curve 1.59 pt, so the width rule cannot separate them. Opt-in per grade
GRID_BY_COLOUR = {'DMR50'}
MIN_COLOUR_DISTANCE = 0.3   # RGB distance (0-1 per channel) every curve colour must keep from every grid colour
TDG_URL = ('https://web.archive.org/web/20171025062152id_/http://www.mhw-intl.com:80/assets/TDG/'
           'TDG%202006%20MnZn%20Catalog.pdf')
TDG_PAGES = {'TD3': 53}     # PDF page of the grade's sheet in TDG's 2006 MnZn catalogue
TDG_LEVELS = {'20%': 0.8, '40%': 0.6}   # legend entry of the "HDC Limit-mu_e" figure -> material level L / mu_i
OERSTED = 1000 / (4 * np.pi)   # A/m
# grade -> (H at left, H at right in Oe, mu at bottom, mu at top), as printed on the image
FAIRRITE_AXES = {'77': (0.1, 10.0, 10.0, 10000.0), '78': (0.1, 10.0, 100.0, 10000.0),
                 '43': (0.01, 10.0, 10.0, 1000.0), '51': (0.01, 10.0, 10.0, 1000.0), '52': (0.1, 10.0, 10.0, 1000.0),
                 '61': (0.1, 100.0, 10.0, 1000.0), '67': (0.1, 100.0, 10.0, 100.0),
                 # 75: the left H end is printed "0.0" (sic), not a value on a log axis. 0.01 Oe is INFERRED from the
                 # neighbouring 0.1 and 1.0 labels (the decades step by x10), not printed; the provenance says so
                 '75': (0.01, 10.0, 10.0, 10000.0),
                 '79': (0.1, 10.0, 10.0, 10000.0), '80': (0.1, 10.0, 10.0, 10000.0), '96': (0.01, 10.0, 10.0, 10000.0),
                 '97': (0.1, 10.0, 100.0, 10000.0), '98': (0.1, 10.0, 100.0, 10000.0)}
# grade -> what of FAIRRITE_AXES is not printed on the image (written into the provenance)
FAIRRITE_AXIS_NOTES = {'75': 'the left H axis end is printed "0.0" (sic); it is taken as 0.01 Oe, inferred from the '
                              'neighbouring 0.1 and 1.0 labels (the decades step by x10), not printed'}
RASTER_GRID_TOL = 2.0    # px
# grade -> (manufacturer, data sheet path); TDK paths as listed on its ferrite-materials catalogue page
SOURCES = {
    'N27': ('TDK', '528850/3a7f957d754f899aec42cd946598c5c4/pdf-n27.pdf'),
    'N41': ('TDK', '528876/07f8fe5e7fb654a26dc779e207a5de15/pdf-n41.pdf'),
    'N48': ('TDK', '528870/80183d6ef4a48b49c5bee48a6e8b2ac5/pdf-n48.pdf'),
    'N49': ('TDK', '528856/c44cc4ec800e9f6f22a8068409c85b4f/pdf-n49.pdf'),
    'N51': ('TDK', '528840/956e4358867968c72a6f3dc4fb7da68e/pdf-n51.pdf'),
    'N72': ('TDK', '528858/fe38d2b52133890d5f7cc6885ff05e75/pdf-n72.pdf'),
    'N87': ('TDK', '528882/d6940b239127a8bab71b22168746021b/pdf-n87.pdf'),
    'N91': ('TDK', '3108406/407bd23272e3b6e4f672151b54b9ef4d/pdf-n91.pdf'),
    'N92': ('TDK', '528888/2eb193d57530c5ad7aef246387fea250/pdf-n92.pdf'),
    'N95': ('TDK', '528866/0fe9e667e8e8afa649f776a2a5a7eb0a/pdf-n95.pdf'),
    'N97': ('TDK', '528886/81166f0de556e5b6a94db7793daed936/pdf-n97.pdf'),
    'M33': ('TDK', '528878/4f65b2fcd11b8b6b3e99fa2bc44bfd7e/pdf-m33.pdf'),
    'N88': ('TDK', '528890/cee245ee621a6b10bd5897f906870869/pdf-n88.pdf'),
    'N96': ('TDK', '528892/62108148dfc602168d141f831c2914e8/pdf-n96.pdf'),
    'N30': ('TDK', '528848/fd7b13cb06de3e2edca6c617ac9de7da/pdf-n30.pdf'),
    'T35': ('TDK', '528880/8351bfa4e86ee7129468f0e83b5db861/pdf-t35.pdf'),
    'T37': ('TDK', '528874/8251c697a6f71dc2bbf4c1f5362137ed/pdf-t37.pdf'),
    'T38': ('TDK', '528868/c2cb0f1f5413cd8e83b8ecf7e85152f9/pdf-t38.pdf'),
    'T65': ('TDK', '528846/1598c89da613db594840e493e0ffb9fe/pdf-t65.pdf'),
    '3B46': ('Ferroxcube', '3b46.pdf'), '3C11': ('Ferroxcube', '3c11.pdf'), '3C90': ('Ferroxcube', '3c90.pdf'),
    '3C91': ('Ferroxcube', '3c91.pdf'), '3C93': ('Ferroxcube', '3c93.pdf'), '3C94': ('Ferroxcube', '3c94.pdf'),
    '3C96': ('Ferroxcube', '3c96.pdf'), '3C98': ('Ferroxcube', '3c98.pdf'), '3E10': ('Ferroxcube', '3e10.pdf'),
    '3E27': ('Ferroxcube', '3e27.pdf'), '3E6': ('Ferroxcube', '3e6.pdf'), '3E65': ('Ferroxcube', '3e65.pdf'),
    '3F3': ('Ferroxcube', '3f3.pdf'), '3F36': ('Ferroxcube', '3f36.pdf'), '3F37': ('Ferroxcube', '2025%20MDS%203F37.pdf'),
    '3F4': ('Ferroxcube', '3f4.pdf'), '4F1': ('Ferroxcube', '4f1.pdf'),
    '3E25': ('Ferroxcube', '3e25.pdf'), '3E26': ('Ferroxcube', '3e26.pdf'), '4C65': ('Ferroxcube', '4c65.pdf'),
    '77': ('Fair-Rite', '77uvsH.jpg'), '78': ('Fair-Rite', '78uvsH.jpg'),
    '43': ('Fair-Rite', '43uvsh.jpg'), '51': ('Fair-Rite', '51_uvsH.jpg'), '52': ('Fair-Rite', '52ipvsfs.jpg'),
    '61': ('Fair-Rite', '61uvsH.jpg'), '67': ('Fair-Rite', '67vsH.jpg'), '75': ('Fair-Rite', '75UvsH.jpg'),
    '79': ('Fair-Rite', '79UvsH.jpg'), '80': ('Fair-Rite', '80uvsh.jpg'), '97': ('Fair-Rite', '97uvsH.jpg'),
    '98': ('Fair-Rite', '98uvH.jpg'), '96': ('Fair-Rite', 'https://fair-rite.com/wp-content/uploads/2024/08/96-IncrementalPerm.png'),
    **{g: ('Magnetics', 'Magnetics-2025-Ferrite-Catalog.pdf') for g in MAGNETICS_PAGES},
    **{g: ('DMEGC', f'https://dmegc.de/uploads/20230401/{g}%20Material%20Characteristics.pdf')
       for g in ('DMR44', 'DMR50', 'DMR52W', 'DMR91', 'DMR95', 'R10KC')},
    **{g: ('DMEGC', 'https://irp.cdn-website.com/eb58f5fe/files/uploaded/' + f)
       for g, f in (('DMR47', 'DMR47_Extremely_low_loss_power_material.pdf'), ('R5K', '46-r5k_high_ui_material_sl.pdf'),
                    ('R7K', '47-r7k_high_ui_material_sl.pdf'), ('R10K', '48-r10k_high_ui_material_sl.pdf'),
                    ('R12K', '49-r12k_high_ui_material_sl.pdf'), ('R15K', '50-r15k_extremely_high_ui_material_sl.pdf'))},
    'TD3': ('TDG', TDG_URL),
}
# TDK single-curve grades: (H at left, H at right in A/m, B at bottom, B at top in mT) of the 25 C "Dynamic
# magnetization curves" panel, as printed on the page (several draw these labels as outlines, not text)
TDK_LOOP_AXES = {'N30': (-100, 400, 0, 450), 'T35': (-100, 400, 0, 450), 'T37': (-100, 400, 0, 450),
                 'T38': (-100, 500, 0, 450), 'T65': (-200, 1400, 0, 600)}
LOOP_GRID_TOL = 0.5      # pt, linear gridlines must be evenly spaced within this
LOOP_CENTRE_TOL = 0.25   # loop midline at B -> 0 within this fraction of Hc of H = 0
LOOP_MIN_B = 0.03        # T, the loop midline must reach down to here (B(H) is needed from H = 0)
MONOTONE_TOL = 0.01      # the un-gapped single curve may rise by at most this between samples
SINGLE_CURVE_ERROR = 0.10  # validated on the multi-curve grades N87, N49, N48, N51: within 0.04-0.10 of mu/mu0
GRID_TOL = 0.5           # pt (about 1 % of a decade), a gridline off the fitted log grid by more refuses the figure
FLAT_TOL = 0.01          # Ferroxcube: flat first decade -> the left value is written at H = 0 too
READ_SIGMA = 0.01        # TDK: relative reading accuracy of H_DC on a log axis
MIN_CURVES = 3
MIN_SIGNIFICANCE = 5
MAX_DISAGREEMENT = 0.06
ONSET_LEVEL = 0.8
MAX_CHI2 = 4.0
REVERSIBLE_FLOOR = 0.9
MAX_PLACEMENT = 0.10
MUI_START_TOL = 0.25    # the curve's start (lowest H) must lie within this of the record's zero-bias mu_i near 25 C
H_GRID = sorted(set([0.0] + list(np.arange(2, 10, 2)) + list(np.arange(10, 50, 5)) + list(np.arange(50, 100, 10)) +
                    list(np.arange(100, 200, 20)) + list(np.arange(200, 1000, 50)) + list(np.arange(1000, 10001, 500))))


class Refused(Exception):
    pass


def fetch(grade, cache):
    maker, rel = SOURCES[grade]
    url = rel if rel.startswith('https://') else {'TDK': TDK_BASE, 'Ferroxcube': FXC_BASE, 'Fair-Rite': FR_BASE, 'Magnetics': MAG_URL}[maker] + rel
    path = os.path.join(cache, os.path.basename(rel).replace('%20', '_'))
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, 'wb') as f:
            f.write(r.read())
    data = open(path, 'rb').read()
    if maker == 'Fair-Rite':
        if not (data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG\r\n\x1a\n')):
            raise Refused(f'{url} is not a JPEG or PNG image')
    elif not data.startswith(b'%PDF'):
        raise Refused(f'{url} is not a PDF')
    return url, path, hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- figure reading (both manufacturers)

def spans_of(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines', []):
            for s in line['spans']:
                if s['text'].strip():
                    out.append((fitz.Rect(s['bbox']), s['size'], s['text'].strip()))
    return out


def label_exponent(spans):
    """A decade tick label: 10 with a superscript exponent (sign possibly a separate glyph), or a plain power of ten."""
    if not spans:
        return None
    spans = sorted(spans, key=lambda s: s[0].x0)
    base = max(s[1] for s in spans)
    big = ''.join(s[2] for s in spans if s[1] >= 0.85 * base)
    small = ''.join(s[2] for s in spans if s[1] < 0.85 * base)
    norm = lambda t: t.replace('_', '-').replace('−', '-').replace('–', '-').replace(' ', '')
    big, small = norm(big), norm(small)
    if small:
        if big.endswith('-'):
            big, small = big[:-1], '-' + small
        m = re.fullmatch(r'10(-?)', big)
        if m and re.fullmatch(r'-?\d', small):
            return int(m.group(1) + small) if not small.startswith('-') else int(small)
        return None
    m = re.fullmatch(r'10(-?\d)', big)   # superscript merged into one span by the PDF producer: ambiguous with 100
    if m and big not in ('10', '100', '1000', '10000'):
        return int(m.group(1))
    try:
        v = float(big)
    except ValueError:
        return None
    if v > 0 and abs(np.log10(v) - round(np.log10(v))) < 1e-9:
        return int(round(np.log10(v)))
    return None


def calibrate_log(lines, spans, axis, box, decades_only=False):
    """Returns position -> value for a log axis drawn with gridlines at `lines`. With `decades_only` (an opt-in per
    figure, DECADE_ONLY_X) the axis is calibrated on its decade lines alone and the minor lines are not checked."""
    p = np.array(sorted(set(np.round(lines, 2))))
    if axis == 'y':
        p = p[::-1]
    if len(p) < 3:
        raise Refused(f'{axis} axis: only {len(p)} gridlines')
    d = np.abs(np.diff(p))
    if decades_only:
        # a decade line opens the widest step of its decade (1 -> 2, 30 % of a decade; 2 -> 3 is 18 %), so the
        # decade lines are the first line, every line opening a step >= 0.8 of the widest, and the last line if it
        # sits a whole number of decades out (as below)
        if d[0] < 0.8 * d.max():
            raise Refused(f'{axis} axis: the first gridline does not open a decade')
        decades = [0] + [i for i in range(1, len(p) - 1) if d[i] >= 0.8 * d.max()]
        if len(decades) >= 2:
            per = abs(p[decades[-1]] - p[0]) / (len(decades) - 1)
            n = abs(p[-1] - p[0]) / per
            if abs(n - round(n)) * per <= GRID_TOL:
                decades.append(len(p) - 1)
        if len(decades) < 3:
            raise Refused(f'{axis} axis: only {len(decades)} decade lines found, 3 needed to calibrate on decades alone')
        p = p[decades]
        decades = list(range(len(p)))
    elif d.max() / d.min() < 1.1:
        decades = list(range(len(p)))          # only decade lines are drawn
    else:
        decades = [0] + [i for i in range(1, len(p) - 1) if d[i] / d[i - 1] > 4]
        if len(decades) >= 2:
            # the decade length from the decade lines found inside; the last line closes the axis but need not be a
            # decade (DMEGC R10KC ends at 500 A/m): it is one only if it sits a whole number of decades out
            per = abs(p[decades[-1]] - p[0]) / (len(decades) - 1)
            n = abs(p[-1] - p[0]) / per
            if abs(n - round(n)) * per <= GRID_TOL:
                decades.append(len(p) - 1)
        else:
            decades.append(len(p) - 1)
    b0 = abs(p[decades[-1]] - p[decades[0]]) / (len(decades) - 1)
    # assign every gridline its log value (decade index + log10 of the nearest mantissa 1..10), then fit
    # position = a + b * logvalue over all of them; every residual must be within GRID_TOL
    logv = []
    for q in p:
        frac = abs(q - p[0]) / b0
        k = np.floor(frac + 1e-6)
        m = min(range(1, 11), key=lambda m: abs(np.log10(m) - (frac - k)))
        logv.append(k + np.log10(m))
    logv = np.array(logv)
    A = np.c_[np.ones_like(logv), logv]
    (a_fit, b_fit), *_ = np.linalg.lstsq(A, np.abs(p - p[0]), rcond=None)
    resid = np.abs(p - p[0]) - A @ [a_fit, b_fit]
    if np.abs(resid).max() > GRID_TOL:
        i = int(np.argmax(np.abs(resid)))
        raise Refused(f'{axis} axis: gridline at {p[i]:.2f} is {resid[i]:+.2f} pt off the log grid')
    b = b_fit
    p = p.copy(); p0_shift = a_fit
    e0s = set()
    for j, i in enumerate(decades):
        pos = p[i]
        if axis == 'x':
            near = [s for s in spans if abs((s[0].x0 + s[0].x1) / 2 - pos) < 12 and box.y1 - 1 < s[0].y0 < box.y1 + 22]
        else:
            near = [s for s in spans if abs((s[0].y0 + s[0].y1) / 2 - pos) < 8 and box.x0 - 40 < s[0].x1 < box.x0 + 2]
        e = label_exponent(near)
        if e is not None:
            e0s.add(e - j)
    if len(e0s) != 1:
        raise Refused(f'{axis} axis: decade tick labels read {sorted(e0s) or "none"} (need one consistent reading)')
    e0 = e0s.pop()
    a = p[0] + (p0_shift if axis == 'x' else -p0_shift)
    if axis == 'x':
        return lambda x: 10 ** (e0 + (x - a) / b)
    return lambda y: 10 ** (e0 + (a - y) / b)


def bezier_points(item, n=40):
    if item[0] == 'l':
        return [(item[1].x, item[1].y), (item[2].x, item[2].y)]
    if item[0] != 'c':
        return []
    P = item[1:5]
    out = []
    for k in range(n + 1):
        t = k / n
        w = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3)
        out.append((sum(w[i] * P[i].x for i in range(4)), sum(w[i] * P[i].y for i in range(4))))
    return out


def figure_rotation(drawings, region):
    """Angle (degrees) by which a whole figure is drawn rotated, or 0. Some sheets (Ferroxcube 3E25) place the figure
    with a small rigid rotation: every long gridline then deviates from its axis by the same angle. The angle is the
    one shared by most long thin lines in `region`; it counts only if horizontal and vertical lines both show it."""
    from collections import Counter
    dev = Counter()
    for d in drawings:
        if (d.get('width') or 0) > 0.8:
            continue
        for it in d['items']:
            if it[0] != 'l' or not (region.contains(it[1]) and region.contains(it[2])):
                continue
            dx, dy = it[2].x - it[1].x, it[2].y - it[1].y
            if np.hypot(dx, dy) <= 80:
                continue
            ang = np.degrees(np.arctan2(dy, dx)) % 90
            ang = ang - 90 if ang > 45 else ang
            if abs(ang) < 1:
                dev[(round(ang, 3), abs(dx) > abs(dy))] += 1
    if not dev:
        return 0.0
    (ang, _), _ = dev.most_common(1)[0]
    if ang == 0 or not (dev[(ang, True)] and dev[(ang, False)]):
        return 0.0
    return ang


def rotate_drawings(drawings, m):
    out = []
    for d in drawings:
        items = []
        for it in d['items']:
            if it[0] in ('l', 'c'):
                items.append((it[0],) + tuple(p * m for p in it[1:]))
            elif it[0] == 're':
                items.append((it[0], it[1] * m) + tuple(it[2:]))
            elif it[0] == 'qu':
                items.append((it[0], it[1] * m) + tuple(it[2:]))
            else:
                items.append(it)
        out.append(dict(d, items=items, rect=d['rect'] * m))
    return out


def read_figure(page, region, with_color=False, grid_by_colour=False):
    """Gridlines and data curves of a log-log figure inside `region` (with `with_color`: also the plot box, and each
    curve with its colour and page points, see figure_curves). With `grid_by_colour` (an opt-in per figure,
    GRID_BY_COLOUR) gridlines and curves are told apart by stroke colour instead of width."""
    drawings, box, tox, toy, minw, grid_colours = figure_axes(page, region, grid_by_colour)
    curves = figure_curves(drawings, box, tox, toy, minw, with_color, exclude_colours=grid_colours)
    if grid_colours is not None:
        for c in curves:
            col = c[1] if with_color else None
            if col is not None and min(np.linalg.norm(np.subtract(col, g)) for g in grid_colours) < MIN_COLOUR_DISTANCE:
                raise Refused(f'curve colour {col} is within {MIN_COLOUR_DISTANCE} of a grid colour {sorted(grid_colours)}')
    return (curves, box) if with_color else curves


def colour_key(c):
    return None if c is None else tuple(round(float(x), 3) for x in c)


def figure_axes(page, region, grid_by_colour=False):
    """(drawings, plot box, x calibration, y calibration, minimum curve stroke width, grid colours) of a log-log
    figure inside `region`. Gridlines are the long thin (<= 0.8 pt) axis-parallel lines; with `grid_by_colour`, the
    long axis-parallel lines of any width, of which those inside the plot (not on its frame) must all share one
    colour; the grid colours (those and the frame's) are returned so curves can be told from them by colour, and the
    minimum curve width is then 0 (grid colours is None otherwise)."""
    drawings = page.get_drawings()
    spans = spans_of(page)
    rot = figure_rotation(drawings, region)
    if rot:     # turn the figure back square about the region's centre; every check below then applies unchanged
        c = (region.tl + region.br) / 2
        m = fitz.Matrix(1, 0, 0, 1, -c.x, -c.y) * fitz.Matrix(-rot) * fitz.Matrix(1, 0, 0, 1, c.x, c.y)
        drawings = rotate_drawings(drawings, m)
        spans = [(r * m, size, text) for r, size, text in spans]
    hl, vl = [], []     # (y, x0, x1, width), (x, y0, y1, width)
    colour_of = {}      # ('h' or 'v', position) -> set of stroke colours (grid_by_colour)
    for d in drawings:
        w = d.get('width') or 0
        if w > 0.8 and not grid_by_colour:
            continue
        if grid_by_colour and d.get('color') is None:
            continue
        for it in d['items']:
            if it[0] != 'l':
                continue
            a, c = it[1], it[2]
            if not (region.contains(a) and region.contains(c)):
                continue
            if abs(a.y - c.y) < 0.01 and abs(a.x - c.x) > 80:
                hl.append((a.y, min(a.x, c.x), max(a.x, c.x), w))
                colour_of.setdefault(('h', round(a.y, 2)), set()).add(colour_key(d.get('color')))
            if abs(a.x - c.x) < 0.01 and abs(a.y - c.y) > 80:
                vl.append((a.x, min(a.y, c.y), max(a.y, c.y), w))
                colour_of.setdefault(('v', round(a.x, 2)), set()).add(colour_key(d.get('color')))
    if len(hl) < 3 or len(vl) < 3:
        raise Refused('gridlines not found')
    # one plot: the horizontal gridlines sharing the most common x-extent, and the verticals inside it
    from collections import Counter
    extent = Counter((round(x0), round(x1)) for _, x0, x1, _ in hl).most_common(1)[0][0]
    hl = [h for h in hl if h[1] >= extent[0] - 1 and h[2] <= extent[1] + 1]   # segments broken by label boxes too
    # and inside the most common y-extent of the verticals in that x-extent: a neighbouring plot stacked above or
    # below with (almost) the same x-extent (the 2025 Ferroxcube sheets) is not part of this one
    yext = Counter((round(y0), round(y1)) for x, y0, y1, _ in vl if extent[0] - 1 <= x <= extent[1] + 1).most_common(1)
    if not yext:
        raise Refused('no vertical gridlines inside the plot')
    yext = yext[0][0]
    hl = [h for h in hl if yext[0] - 1 <= h[0] <= yext[1] + 1]
    if not hl:
        raise Refused('no horizontal gridlines inside the plot')
    ylo, yhi = min(h[0] for h in hl), max(h[0] for h in hl)
    vl = [v for v in vl if extent[0] - 1 <= v[0] <= extent[1] + 1 and v[1] < yhi and v[2] > ylo]
    H = [h[0] for h in hl]; V = [v[0] for v in vl]; widths = [h[3] for h in hl] + [v[3] for v in vl]
    if len(H) < 3 or len(V) < 3:
        raise Refused('gridlines of one plot not found')
    box = fitz.Rect(min(V), min(H), max(V), max(H))
    tox = calibrate_log(V, spans, 'x', box)
    toy = calibrate_log(H, spans, 'y', box)
    if not grid_by_colour:
        return drawings, box, tox, toy, 1.5 * max(widths), None
    inner = set().union(*[colour_of[('h', round(y, 2))] for y in H if min(y - box.y0, box.y1 - y) > GRID_TOL],
                        *[colour_of[('v', round(x, 2))] for x in V if min(x - box.x0, box.x1 - x) > GRID_TOL])
    if len(inner) != 1:
        raise Refused(f'gridlines inside the plot drawn in {len(inner)} colours {sorted(inner, key=str)}, one expected')
    grid_colours = set().union(*[colour_of[('h', round(y, 2))] for y in H], *[colour_of[('v', round(x, 2))] for x in V])
    return drawings, box, tox, toy, 0.0, grid_colours


def figure_curves(drawings, box, tox, toy, minw, with_color=False, exclude_colours=None):
    """Data curves (strokes at least `minw` wide, not dashed, not on the frame) inside `box`, in axis values. With
    `with_color`, each curve comes as (values, stroke colour, page points), and only strokes of one colour are joined.
    With `exclude_colours` (gridlines told apart by colour), strokes without a colour or in one of those are skipped."""
    paths, colors = [], []
    for d in drawings:
        if (d.get('width') or 0) < minw or not box.intersects(d['rect']):
            continue
        if exclude_colours is not None and (d.get('color') is None or colour_key(d['color']) in exclude_colours):
            continue
        if d.get('dashes') not in (None, '[] 0'):
            continue
        pts = []
        for it in d['items']:
            pts += bezier_points(it)
        pts = [(x, y) for x, y in pts if box.x0 - 0.5 <= x <= box.x1 + 0.5 and box.y0 - 0.5 <= y <= box.y1 + 0.5]
        on_frame = all(min(abs(x - box.x0), abs(x - box.x1)) < 0.6 or min(abs(y - box.y0), abs(y - box.y1)) < 0.6 for x, y in pts)
        if len(pts) > 1 and not on_frame:
            paths.append(pts)
            colors.append(d.get('color'))
    curves, ccol = [], []
    for k in sorted(range(len(paths)), key=lambda k: paths[k][0][0]):
        pth = paths[k]
        for c, cc in zip(curves, ccol):
            if np.hypot(c[-1][0] - pth[0][0], c[-1][1] - pth[0][1]) < 1.0 and (not with_color or cc == colors[k]):
                c += pth
                break
        else:
            curves.append(list(pth))
            ccol.append(colors[k])
    data = []
    for c, cc in zip(curves, ccol):
        a = np.array([(tox(x), toy(y)) for x, y in c])
        order = np.argsort(a[:, 0], kind='stable')
        data.append((a[order], cc, np.array(c)[order]) if with_color else a[order])
    data.sort(key=(lambda q: -q[0][0, 1]) if with_color else (lambda a: -a[0, 1]))
    return data


def sample_curve(a, T, page_no):
    """Points of one ungapped material curve (H, mu) read off a vector figure: on the fixed H grid inside the drawn
    range (log-log interpolation between evaluated path points), plus H = 0 when the first drawn decade is flat
    within FLAT_TOL. Nothing is fitted. Refused if the curve rises with H by more than 1 % between path points."""
    h, mu = a[:, 0], a[:, 1]
    keep = np.r_[True, np.diff(h) > 0]
    h, mu = h[keep], mu[keep]
    if np.any(np.diff(mu) > 0.01 * mu[:-1]):
        raise Refused('the curve rises with H somewhere')
    lh, lm = np.log(h), np.log(mu)
    pts = []
    first_decade = mu[h <= 10 * h[0]]
    if first_decade.max() / first_decade.min() - 1 <= FLAT_TOL:
        pts.append((0.0, float(mu[0])))
    for x in H_GRID:
        if h[0] <= x <= h[-1]:
            pts.append((float(x), float(np.exp(np.interp(np.log(x), lh, lm)))))
    if pts[-1][0] < h[-1] * 0.999:
        pts.append((float(round(h[-1], 1)), float(mu[-1])))
    report = dict(T=T, page=page_no, flat0=pts[0][0] == 0.0, hmin=float(h[0]), hmax=float(h[-1]), mu0=float(mu[0]),
                  ratio={x: round(float(np.exp(np.interp(np.log(x), lh, lm)) / mu[0]), 3) for x in (15, 30, 45, 60) if h[0] <= x <= h[-1]})
    points = []
    for x, v in pts:
        q = {'value': round(v, 1), 'magneticFieldDcBias': round(x, 1)}
        if T is not None:
            q['temperature'] = T
        points.append(q)
    return points, report


# ---------------------------------------------------------------- Ferroxcube: ungapped material curve

def ferroxcube(grade, doc):
    for page in doc:
        hits = page.search_for('Reversible permeability')
        if not hits:
            continue
        cap = hits[0]
        caption = page.get_textbox(fitz.Rect(cap.x0 - 60, cap.y0, cap.x0 + 260, cap.y1 + 30))
        region = fitz.Rect(cap.x0 - 75, cap.y0 - 300, cap.x0 + 240, cap.y0 - 2)
        curves = read_figure(page, region)
        if len(curves) != 1:
            raise Refused(f'figure on page {page.number + 1} has {len(curves)} data curves, one expected')
        a = curves[0]
        T = None
        figtext = page.get_textbox(region) + ' ' + caption
        mt = re.search(r'(?:T\s*=\s*|at\s*)(-?\d+)\s*[º°]\s*C', figtext)
        if mt:
            T = float(mt.group(1))
        points, report = sample_curve(a, T, page.number + 1)
        return points, [report], []
    raise Refused('no "Reversible permeability" figure')


def ferroxcube_provenance(grade, report, url, sha):
    r = report[0]
    t = f'at {r["T"]:.0f} C' if r['T'] is not None else 'at a temperature the figure does not state'
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': f'Ferroxcube, {grade} material data sheet',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"Reversible permeability as a function of magnetic field strength", page {r["page"]}, {t}; read off the '
            f'vector path of the curve, {r["hmin"]:.3g}-{r["hmax"]:.3g} A/m, on log axes calibrated on the figure\'s '
            f'gridlines; document sha256 {sha[:8]}...{sha[-4:]}. The H = 0 point is the curve\'s flat left end.'),
        'fields': ['permeability.reversible'],
    }


# ---------------------------------------------------------------- Fair-Rite: raster image of the material curve

def raster_axis(pos, n_decades, axis):
    """Gridline pixel positions -> (start pixel, pixels per decade), checked against the log pattern."""
    pos = sorted(pos) if axis == 'x' else sorted(pos, reverse=True)
    span = abs(pos[-1] - pos[0])
    per = span / n_decades
    for q in pos:
        frac = abs(q - pos[0]) / per
        m = 10 ** (frac - np.floor(frac + 1e-6))
        if min(abs(per * (np.log10(k) - np.log10(m))) for k in range(1, 11)) > RASTER_GRID_TOL:
            raise Refused(f'{axis} gridline at pixel {q:.0f} is off a {n_decades}-decade log grid')
    full = [k for k in range(n_decades + 1) if any(abs(abs(q - pos[0]) - k * per) <= RASTER_GRID_TOL for q in pos)]
    if len(full) != n_decades + 1:
        raise Refused(f'{axis} axis: decade gridlines found at {full}, {n_decades + 1} expected')
    return pos[0], per


def fairrite(grade, path):
    pm = fitz.Pixmap(path)
    if pm.alpha:
        pm = fitz.Pixmap(pm, 0)     # drop the alpha channel (PNG)
    img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)[:, :, :3].mean(axis=2)
    dark = img < 128
    def runs(ix):
        out, start, prev = [], ix[0], ix[0]
        for i in list(ix[1:]) + [None]:
            if i is None or i != prev + 1:
                out.append((start, prev))
                if i is not None:
                    start = i
            if i is not None:
                prev = i
        return out
    hruns = runs(np.where(dark.mean(axis=1) > 0.6)[0])
    vruns = runs(np.where(dark.mean(axis=0) > 0.6)[0])
    h0, h1, m0, m1 = FAIRRITE_AXES[grade]
    if min(h0, h1, m0, m1) <= 0:
        raise Refused(f'an axis end is printed as {min(h0, h1, m0, m1)}: not a value on a log axis')
    nx, ny = round(np.log10(h1 / h0)), round(np.log10(m1 / m0))
    x0, px = raster_axis([(a + b) / 2 for a, b in vruns], nx, 'x')
    y0, py = raster_axis([(a + b) / 2 for a, b in hruns], ny, 'y')
    masked = dark.copy()
    for a, b in hruns:
        masked[a:b + 1, :] = False
    vcols = set(c for a, b in vruns for c in range(a - 1, b + 2))
    top, bottom = min(a for a, _ in hruns), max(b for _, b in hruns)
    left, right = min(a for a, _ in vruns), max(b for _, b in vruns)
    hs, ms = [], []
    for c in range(left + 2, right - 1):
        if c in vcols:
            continue
        rows = np.where(masked[top + 1:bottom, c])[0] + top + 1
        if not len(rows):
            continue
        rr = runs(rows)
        # the curve: runs >= 2 px (a gridline row is masked; text is outside the plot box)
        rr = [(a, b) for a, b in rr if b - a >= 1]
        if len(rr) != 1:
            continue
        y = (rr[0][0] + rr[0][1]) / 2
        hs.append(h0 * 10 ** ((c - x0) / px) * OERSTED)
        ms.append(m0 * 10 ** ((y0 - y) / py))
    if len(hs) < 50:
        raise Refused(f'only {len(hs)} curve columns read')
    h, mu = np.array(hs), np.array(ms)
    lh, lm = np.log(h), np.log(mu)
    pts = []
    first = mu[h <= 3 * h[0]]
    if first.max() / first.min() - 1 <= 0.03:
        pts.append((0.0, float(np.median(first))))
    for x in H_GRID:
        if h[0] <= x <= h[-1]:
            # median of the columns within +-2 % in H: the stroke is a few pixels wide
            sel = np.abs(lh - np.log(x)) < 0.02
            pts.append((float(x), float(np.exp(np.median(lm[sel]))) if sel.any() else float(np.exp(np.interp(np.log(x), lh, lm)))))
    points = [{'value': round(v, 1), 'magneticFieldDcBias': round(x, 1), 'temperature': 25.0, 'frequency': 10000.0} for x, v in pts]
    mu0 = pts[0][1]
    report = dict(T=25.0, page=1, hmin=float(h[0]), hmax=float(h[-1]), mu0=mu0, flat0=pts[0][0] == 0.0,
                  ratio={x: round(float(np.exp(np.interp(np.log(x), lh, lm)) / mu0), 3) for x in (15, 30, 45, 60) if h[0] <= x <= h[-1]})
    return points, [report], []


def fairrite_provenance(grade, report, url, sha):
    r = report[0]
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': f'Fair-Rite, {grade} material data sheet',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"{grade} Material Incremental Permeability vs Field Strength" image on {FR_PAGE.format(grade=grade)}; '
            f'measured on 18/10/6 mm toroids at 25 C and 10 kHz (the page\'s stated conditions); read off the raster '
            f'(sha256 {sha[:8]}...{sha[-4:]}) on log axes calibrated on its gridlines, {r["hmin"]:.3g}-{r["hmax"]:.3g} A/m'
            + ('; the H = 0 point is the curve\'s flat left end.' if r['flat0'] else
               '; no H = 0 point (the curve varies by more than 3 % over its first factor of 3 in H).')
            + (f' Axis: {FAIRRITE_AXIS_NOTES[grade]}.' if grade in FAIRRITE_AXIS_NOTES else '')),
        'fields': ['permeability.incremental'],
    }


# ---------------------------------------------------------------- Magnetics Inc: ungapped curve in a framed plot

def framed_grid(page, cap, drawings):
    """Frame and gridline positions of a framed log-log plot whose title `cap` sits just above it (Magnetics, DMEGC):
    the frame is the stroked rectangle starting within 20 pt below the title; the gridlines are the thin lines that
    cross the frame (>= 90 % of it) plus the tick marks outside its left and bottom edges (the decade labels sit at
    the ticks; the frame edges themselves need not be decades). A gridline drawn twice is one line: copies within
    GRID_TOL are averaged; copies further apart stay two lines, and the log-grid check then decides. The frame may be
    stroked twice as well (copies within GRID_TOL are one frame)."""
    centre = (cap.x0 + cap.x1) / 2
    frames = set()
    for d in drawings:
        if not d.get('width') or d.get('color') is None:
            continue
        for it in d['items']:
            if it[0] == 're' and cap.y1 - 1 <= it[1].y0 <= cap.y1 + 20 and it[1].x0 < centre < it[1].x1 and it[1].width > 80:
                frames.add(tuple(it[1]))
    frames = sorted(frames)
    if not frames or any(max(abs(a - b) for a, b in zip(q, frames[0])) > GRID_TOL for q in frames):
        raise Refused(f'{len(frames)} different plot frames under the title, one expected')
    f = fitz.Rect(*np.mean(frames, axis=0))
    V, Hs, widths = [], [], []
    for d in drawings:
        w = d.get('width') or 0
        if not w or w > 0.8:
            continue
        for it in d['items']:
            if it[0] != 'l':
                continue
            a, c = it[1], it[2]
            if abs(a.x - c.x) < 0.01 and f.x0 - 1 <= a.x <= f.x1 + 1:
                y0, y1 = min(a.y, c.y), max(a.y, c.y)
                if min(y1, f.y1) - max(y0, f.y0) >= 0.9 * f.height or (f.y1 - 1 <= y0 and y1 <= f.y1 + 8 and y1 - y0 < 8):
                    V.append(a.x); widths.append(w)
            elif abs(a.y - c.y) < 0.01 and f.y0 - 1 <= a.y <= f.y1 + 1:
                x0, x1 = min(a.x, c.x), max(a.x, c.x)
                if min(x1, f.x1) - max(x0, f.x0) >= 0.9 * f.width or (f.x0 - 8 <= x0 and x1 <= f.x0 + 1 and x1 - x0 < 8):
                    Hs.append(a.y); widths.append(w)
    def merged(pos):
        groups = []
        for q in sorted(pos):
            if groups and q - groups[-1][0] <= GRID_TOL:
                groups[-1].append(q)
            else:
                groups.append([q])
        return [float(np.mean(g)) for g in groups]
    V, Hs = merged(V), merged(Hs)
    if len(V) < 3 or len(Hs) < 3:
        raise Refused(f'{len(V)} x and {len(Hs)} y gridlines/ticks found, 3 each needed')
    return f, V, Hs, max(widths)


def magnetics(grade, doc):
    page = doc[MAGNETICS_PAGES[grade] - 1]
    if not page.search_for(f'{grade} Material'):
        raise Refused(f'page {page.number + 1} is not the {grade} Material page')
    caps = page.search_for('PERMEABILITY vs. DC BIAS')
    if len(caps) != 1:
        raise Refused(f'{len(caps)} "PERMEABILITY vs. DC BIAS" titles on page {page.number + 1}, one expected')
    drawings = page.get_drawings()
    frame, V, Hs, gw = framed_grid(page, caps[0], drawings)
    box = fitz.Rect(min(V), min(Hs), max(V), max(Hs))
    spans = [(r, size, text.replace(',', '')) for r, size, text in spans_of(page)]   # "10,000"
    tox = calibrate_log(V, spans, 'x', box, decades_only=grade in DECADE_ONLY_X)
    toy = calibrate_log(Hs, spans, 'y', box)
    curves = figure_curves(drawings, frame, tox, toy, 1.5 * gw)
    if len(curves) != 1:
        raise Refused(f'figure on page {page.number + 1} has {len(curves)} data curves, one expected')
    points, report = sample_curve(curves[0], None, page.number + 1)
    report.update(frame=(float(toy(frame.y0)), float(tox(frame.x1))), raw=curves[0])
    if grade in MAGNETICS_SHARED_FIGURE:
        other = MAGNETICS_SHARED_FIGURE[grade]
        _, (rep_other,) = magnetics(other, doc)[:2]
        if rep_other['raw'].shape != curves[0].shape or not np.allclose(rep_other['raw'], curves[0], rtol=SHARED_FIGURE_RTOL, atol=0):
            raise Refused(f'MAGNETICS_SHARED_FIGURE says the {grade} figure is drawn identical to {other}\'s, but it no longer is')
        report['same_as'] = other
    return points, [report], []


def magnetics_provenance(grade, report, url, sha):
    r = report[0]
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': 'Magnetics, 2025 Ferrite Catalog',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"PERMEABILITY vs. DC BIAS" figure of {grade} Material, catalogue page {r["page"]} (PDF page), one curve '
            f'starting at the initial permeability (ungapped); the figure states no temperature, frequency or core, '
            f'and names the quantity only "permeability", stored as incremental. Read off the vector path of the curve, '
            f'{r["hmin"]:.3g}-{r["hmax"]:.3g} A/m, on log axes calibrated on the figure\'s gridlines and tick marks'
            + (' (the H axis on its decade lines only: its 100-1000 A/m decade draws a second set of minor gridlines, '
               'up to 0.6 pt from the first, so the minor lines were not used)' if grade in DECADE_ONLY_X else '')
            + (f'. The catalogue draws this figure identical to the {r["same_as"]} Material figure (same vector path); '
               f'kept as published for {grade} (Alf, 2026-11-21), but it may be a reused drawing'
               if r.get('same_as') else '')
            + f'; document sha256 {sha[:8]}...{sha[-4:]}. Points on a fixed H grid, nothing fitted'
            + ('; the H = 0 point is the curve\'s flat left end.' if r['flat0'] else '.')),
        'fields': ['permeability.incremental'],
    }


# ---------------------------------------------------------------- DMEGC: ungapped toroid, one curve per temperature

def text_lines(page):
    """(bbox, direction, text) of every non-empty text line of the page that has a size (some sheets carry
    zero-size duplicate text)."""
    out = []
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines', []):
            r = fitz.Rect(line['bbox'])
            t = ''.join(sp['text'] for sp in line['spans']).strip()
            if t and r.width > 1 and r.height > 1:
                out.append((r, line['dir'], t))
    return out


def dmegc(grade, doc):
    for page in doc:
        lines = text_lines(page)
        labels = [r for r, d, t in lines if 'Incremental Permeability' in t and abs(d[1]) > 0.99]
        if not labels:
            continue
        if len(labels) != 1:
            raise Refused(f'{len(labels)} "Incremental Permeability" axis titles on page {page.number + 1}, one expected')
        lab = labels[0]
        cy = (lab.y0 + lab.y1) / 2
        # the H axis title under the same plot; the y-axis title is centred on the plot, so the plot spans about as far
        # above the title's centre as the H axis title sits below it
        xt = [r for r, d, t in lines if 'Magnetic Field Strength' in t and r.y0 > cy and lab.x1 < (r.x0 + r.x1) / 2 < lab.x1 + 270]
        if not xt:
            raise Refused(f'no "Magnetic Field Strength" axis title under the plot on page {page.number + 1}')
        xt = min(xt, key=lambda r: r.y0)
        region = fitz.Rect(lab.x1, 2 * cy - xt.y0 - 8, lab.x1 + 270, xt.y0)
        curves, box = read_figure(page, region, with_color=True, grid_by_colour=grade in GRID_BY_COLOUR)
        # temperatures stated inside the plot: a legend (a short stroke left of "25 C") or one "T=25 C" box
        temps = []
        for r, d, t in lines:
            m = re.fullmatch(r'(T\s*=\s*)?(-?\d+)\s*℃', t)
            if m and box.contains(r):
                temps.append((r, float(m.group(2)), bool(m.group(1))))
        data = []
        if not temps:       # no temperature stated: one curve, written without a temperature
            if len(curves) != 1:
                raise Refused(f'plot on page {page.number + 1} states no temperature and has {len(curves)} curves')
            data.append((None, curves[0][0]))
        elif len(temps) == 1 and temps[0][2]:
            T = temps[0][1]
            if len(curves) != 1:
                raise Refused(f'"T = {T:.0f} C" plot on page {page.number + 1} has {len(curves)} curves, one expected')
            data.append((T, curves[0][0]))
        else:
            # legend strokes: one straight horizontal segment ending just left of the entry's text
            segs = [(d.get('color'), it[1], it[2]) for d in page.get_drawings() if d.get('color') is not None
                    for it in d['items'] if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.01 and box.contains(it[1])]
            for r, T, boxed in temps:
                cy_t = (r.y0 + r.y1) / 2
                strokes = [col for col, a, b in segs if abs(a.y - cy_t) < 3 and 0 <= r.x0 - max(a.x, b.x) < 12 and abs(a.x - b.x) < 30]
                if len(strokes) != 1:
                    raise Refused(f'legend entry {T:.0f} C: {len(strokes)} legend strokes beside it, one expected')
                data.append((T, strokes[0]))
            colours = [c for _, c in data]
            if len(set(colours)) != len(colours):
                raise Refused('two legend entries share one stroke colour')
            if len(curves) != len(data):
                raise Refused(f'{len(curves)} curves for {len(data)} legend entries')
            out = []
            for T, col in data:
                match = [c for c in curves if c[1] == col]
                if len(match) != 1:
                    raise Refused(f'{len(match)} curves drawn in the colour of the {T:.0f} C legend entry')
                out.append((T, match[0][0]))
            data = out
        points, report, refused = [], [], []
        for T, a in data:
            try:
                pts, rep = sample_curve(a, T, page.number + 1)
            except Refused as e:
                refused.append((f'{T:.0f} C: ' if T is not None else '') + str(e))
                continue
            points += pts
            report.append(rep)
        if not report:
            raise Refused(' | '.join(refused))
        return points, report, refused
    raise Refused('no "Incremental Permeability" figure')


def dmegc_provenance(grade, report, url, sha):
    figs = '; '.join((f'{r["T"]:.0f} C' if r['T'] is not None else 'temperature not stated') + f', {r["hmin"]:.3g}-{r["hmax"]:.3g} A/m' + (' (H = 0 point: the curve\'s flat left end)' if r['flat0'] else '')
                     for r in report)
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': f'DMEGC, {grade} material characteristics',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"Incremental Permeability mu_Delta" vs "Magnetic Field Strength H (A/m)" figure on page {report[0]["page"]}, '
            f'measured on the sheet\'s standard toroid (25 x 15 x 8 mm), ungapped; read off the vector paths of the curves, '
            f'each assigned the temperature its legend or label states: {figs}; on log axes calibrated on the figure\'s gridlines; '
            f'document sha256 {sha[:8]}...{sha[-4:]}. Points on a fixed H grid, nothing fitted.'),
        'fields': ['permeability.incremental'],
    }


# ---------------------------------------------------------------- TDK: gapped cores, un-gapped by Ampere

def table_value(doc, pattern, what):
    for page in doc:
        m = re.search(pattern, page.get_text())
        if m:
            return m
    raise Refused(f'no {what} in the data sheet table')


def tdk_panels(doc):
    panels = []
    for page in doc:
        hits = page.search_for('DC magnetic bias')
        words = page.get_text('words') if hits else []
        for hit in hits:
            cap = fitz.Rect(hit.x0 - 2, hit.y0, hit.x0 + 230, hit.y1 + 45)
            text = ' '.join(w[4] for w in words if cap.contains(fitz.Rect(w[:4])))
            mt = re.search(r'T\s*=\s*(\d+)\s*°C', text)
            if not mt:
                continue
            # the caption ends at the line carrying the temperature (words below it belong to the plot)
            bottom = max(w[3] for w in words if cap.contains(fitz.Rect(w[:4])) and '°C' in w[4])
            region = fitz.Rect(hit.x0 - 30, bottom, hit.x0 + 260, bottom + 330)
            T = float(mt.group(1))
            try:
                panels.append(dict(T=T, page=page.number + 1, curves=read_figure(page, region)))
            except Refused as e:
                panels.append(dict(T=T, page=page.number + 1, error=str(e)))
    return panels


def solve_levels(curves, g, levels):
    rows = []
    for L in levels:
        pts = []
        for a, gi in zip(curves, g):
            target = 1 / (1 / L + gi)
            drop = target / a[0, 1]
            if not (0.25 < drop < 0.985):
                continue
            idx = np.where((a[:-1, 1] >= target) & (a[1:, 1] < target))[0]
            if not len(idx):
                continue
            i = idx[0]
            t = (a[i, 1] - target) / (a[i, 1] - a[i + 1, 1])
            pts.append((gi, a[i, 0] + t * (a[i + 1, 0] - a[i, 0])))
        if len(pts) < MIN_CURVES:
            continue
        rows.append(dict(L=L, **ampere_line([q[0] for q in pts], [q[1] for q in pts])))
    return rows


def ampere_line(G, Hd):
    """The material state (H, B) shared by gapped cores with gap terms G that reach one material level at the DC
    fields Hd: H_DC = H + (B/mu0) g, a line in g fitted with sigma = READ_SIGMA of H_DC. sH is H's standard error,
    scaled up by the points' observed disagreement (rms relative residual) when it exceeds READ_SIGMA."""
    G = np.array(G, dtype=float); Hd = np.array(Hd, dtype=float)
    A = np.c_[np.ones_like(G), G]; W = 1 / (READ_SIGMA * Hd)
    (Hm, slope), *_ = np.linalg.lstsq(A * W[:, None], Hd * W, rcond=None)
    cov = np.linalg.inv((A * W[:, None]).T @ (A * W[:, None]))
    rel = (Hd - A @ [Hm, slope]) / Hd
    rms = float(np.sqrt(np.mean(rel ** 2)))
    return dict(H=Hm, sH=np.sqrt(cov[0, 0]) * max(1.0, rms / READ_SIGMA), B=slope * MU0, n=len(G), rms=rms)


def fit_and_sample(rows, mu0):
    H = np.array([r['H'] for r in rows]); L = np.array([r['L'] for r in rows]); s = np.array([r['sH'] for r in rows])
    f = lambda p, L: p[0] * np.maximum((mu0 / L) ** (1 / p[2]) - 1, 1e-12) ** (1 / p[1])
    r = least_squares(lambda p: (f(p, L) - H) / s, [40, 3, 1], bounds=([1, 0.5, 0.1], [2000, 12, 10]))
    res = (f(r.x, L) - H) / s
    H0, c, k = r.x
    hmax = float(H.max())
    grid = [h for h in H_GRID if h <= hmax] + [round(hmax, 1)]
    pts = [(float(h), float(mu0 / (1 + (h / H0) ** c) ** k)) for h in grid]
    return pts, dict(chi2=float(np.sum(res ** 2) / max(1, len(H) - 3)), hmin=float(H.min()), hmax=hmax)


def tdk_loop_midline(grade, doc):
    """Midline H(B) of the 25 C 'Dynamic magnetization curves' loop (mean of its rising and falling branches)."""
    if grade not in TDK_LOOP_AXES:
        raise Refused('single-curve figure, and no loop axis values in TDK_LOOP_AXES for this grade')
    h0, h1, b0, b1 = TDK_LOOP_AXES[grade]
    for page in doc:
        for hit in page.search_for('Dynamic magnetization curves'):
            cap = page.get_text('text', clip=fitz.Rect(hit.x0, hit.y0, hit.x0 + 200, hit.y1 + 40)).replace('\xa0', ' ')
            if not re.search(r'T\s*=\s*25\s*°C', cap):
                continue
            region = fitz.Rect(hit.x0 - 30, hit.y1 + 20, hit.x0 + 260, hit.y1 + 340)
            drawings = page.get_drawings()
            hl, vl, gw = set(), set(), []
            for d in drawings:
                w = d.get('width') or 0
                if w > 0.8:
                    continue
                for it in d['items']:
                    if it[0] == 'l' and region.contains(it[1]) and region.contains(it[2]):
                        a, c = it[1], it[2]
                        if abs(a.y - c.y) < 0.01 and abs(a.x - c.x) > 80:
                            hl.add(round(a.y, 2)); gw.append(w)
                        if abs(a.x - c.x) < 0.01 and abs(a.y - c.y) > 80:
                            vl.add(round(a.x, 2)); gw.append(w)
            for lines, what in ((sorted(vl), 'H'), (sorted(hl), 'B')):
                step = np.diff(lines)
                if len(lines) < 4 or np.ptp(step) > LOOP_GRID_TOL:
                    raise Refused(f'loop panel: {what} gridlines not evenly spaced ({len(lines)} found)')
            x0, x1, y0, y1 = min(vl), max(vl), max(hl), min(hl)
            toH = lambda x: h0 + (x - x0) / (x1 - x0) * (h1 - h0)
            toB = lambda y: (b0 + (y - y0) / (y1 - y0) * (b1 - b0)) * 1e-3
            inner = fitz.Rect(x0 + 0.5, y1 + 0.5, x1 - 0.5, y0 - 0.5)
            br = []     # the loop: every stroke inside the plot box that is not a gridline (one path or many short segments;
            # some panels draw it thinner than the grid, so stroke width does not tell it apart)
            on_grid = lambda pts: (all(abs(x - pts[0][0]) < 0.05 for x, _ in pts) and min(abs(pts[0][0] - v) for v in vl) < 0.05) or \
                                  (all(abs(y - pts[0][1]) < 0.05 for _, y in pts) and min(abs(pts[0][1] - h) for h in hl) < 0.05)
            for d in drawings:
                if d.get('fill') is not None or not d.get('width') or not inner.intersects(d['rect']):
                    continue
                for it in d['items']:
                    pts = [q for q in bezier_points(it) if inner.contains(fitz.Point(q))]
                    if len(pts) >= 2 and on_grid(pts):
                        continue
                    if len(pts) >= 2:
                        br.append(np.array([(toH(x), toB(y)) for x, y in pts]))
            if not br:
                raise Refused('loop panel: no loop curve')
            Bs, Hm = [], []
            for b in np.linspace(0.01, 0.97 * max(a[:, 1].max() for a in br), 300):
                hs = []
                for a in br:
                    d0, d1 = a[:-1, 1] - b, a[1:, 1] - b
                    for k in np.where((d0 * d1 <= 0) & (d0 != d1))[0]:
                        hs.append(a[k, 0] + (b - a[k, 1]) * (a[k + 1, 0] - a[k, 0]) / (a[k + 1, 1] - a[k, 1]))
                # a branch may be drawn as a bundle of parallel strokes: the crossings must form exactly two clusters
                hs = np.sort(hs)
                if len(hs) < 2:
                    continue
                cut = int(np.argmax(np.diff(hs)))
                left, right = hs[:cut + 1], hs[cut + 1:]
                if hs[cut + 1] - hs[cut] < 2 * max(np.ptp(left), np.ptp(right)):
                    continue
                Bs.append(b); Hm.append((np.median(left) + np.median(right)) / 2)
            if len(Bs) < 50:
                raise Refused('loop panel: the two branches were not both found')
            if min(Bs) > LOOP_MIN_B:
                raise Refused(f'loop panel: both branches resolved only above {1e3 * min(Bs):.0f} mT')
            return np.array(Hm), np.array(Bs), page.number + 1
    raise Refused('no 25 C "Dynamic magnetization curves" panel')


def tdk_single(grade, doc, panel, mui, hc):
    """One curve on a core with a small residual gap: the gap is taken out by Ampere with the material's B(H) taken
    from the same data sheet's 25 C loop (its midline), H_DC = H + g B(H)/mu0, g = 1/mu_e0 - 1/mu_i."""
    a = panel['curves'][0]
    g = 1 / a[0, 1] - 1 / mui
    if g <= 0:
        raise Refused(f'the single curve starts at {a[0, 1]:.0f} >= mu_i = {mui:.0f}: no gap to take out')
    Hm, Bs, loop_page = tdk_loop_midline(grade, doc)
    centre = float(np.interp(0.02, Bs, Hm))
    if abs(centre) > LOOP_CENTRE_TOL * hc:
        raise Refused(f'loop midline sits at {centre:.1f} A/m at B -> 0 (Hc = {hc:.0f} A/m): axis or branches misread')
    o = np.argsort(Hm)
    hg = np.linspace(0, float(Hm.max()), 20001)
    Bof = np.interp(hg, Hm[o], Bs[o])
    Hdc = hg + g * Bof / MU0
    Hmat = np.interp(a[:, 0], Hdc, hg, right=np.nan)
    mu = 1 / (1 / a[:, 1] - g)
    keep = ~np.isnan(Hmat) & (mu > 0)
    Hmat, mu = Hmat[keep], mu[keep]
    if np.any(np.diff(mu) > MONOTONE_TOL * mu[:-1]):
        raise Refused('the un-gapped curve rises with the field')
    hmax = float(Hmat.max())
    grid = [h for h in H_GRID if h <= hmax]
    vals = np.exp(np.interp(grid, Hmat, np.log(mu)))
    vals[np.array(grid) == 0] = mui
    half = float(np.interp(hc / 2, grid, vals)) / mui
    if half < REVERSIBLE_FLOOR:
        raise Refused(f'mu_rev falls to {half:.2f} of mu_rev(0) at Hc/2 = {hc / 2:.0f} A/m')
    points = [{'value': round(float(v), 1), 'temperature': 25.0, 'frequency': 10000.0, 'magneticFluxDensityPeak': 0.00025,
               'magneticFieldDcBias': round(float(h), 1)} for h, v in zip(grid, vals)]
    report = [dict(T=25.0, page=panel['page'], loop_page=loop_page, single=True, mu_e0=float(a[0, 1]), mu0=mui, hmin=0.0, hmax=hmax,
                   ratio={h: round(float(np.interp(h, grid, vals) / mui), 3) for h in (15, 30, 45, 60) if h <= hmax})]
    return points, report, []


def tdk(grade, doc, mui_of_T):
    mui = float(table_value(doc, r'Initial permeability\s*\(T = 25 °C\)\s*\S+\s*(\d{3,5})\s', 'initial permeability (T = 25 C)').group(1))
    m = table_value(doc, r'Hc \(25 °C\)\s*Hc \(100 °C\)\s*(?:Hc \(\d+ °C\)\s*)?(?:A/m\s*)+(\d+)\s+(\d+)', 'coercive field strengths (25 / 100 C)')
    coercive = {25.0: float(m.group(1)), 100.0: float(m.group(2))}
    panels = tdk_panels(doc)
    if not panels:
        raise Refused('no "DC magnetic bias" figure')
    temps = [p['T'] for p in panels]
    if len(set(temps)) != len(temps):
        raise Refused(f'two DC-bias figures carry the same temperature label {temps}')
    p25 = [p for p in panels if p['T'] == 25]
    if not p25:
        raise Refused('no 25 C DC-bias figure to take the gaps from')
    if 'error' in p25[0]:
        raise Refused(f'25 C figure: {p25[0]["error"]}')
    if len(p25[0]['curves']) == 1 and len(panels) == 1:
        return tdk_single(grade, doc, p25[0], mui, coercive[25.0])
    if len(p25[0]['curves']) < MIN_CURVES:
        raise Refused(f'25 C figure has {len(p25[0]["curves"])} gapped curve(s), {MIN_CURVES} needed')
    g = [1 / a[0, 1] - 1 / mui for a in p25[0]['curves']]
    if min(g) <= 0:
        raise Refused(f'a curve starts at or above mu_i = {mui:.0f}: not a gapped core')
    points, report, refused = [], [], []
    for p in panels:
        try:
            if 'error' in p:
                raise Refused(p['error'])
            if len(p['curves']) != len(g):
                raise Refused(f'{len(p["curves"])} curves, the 25 C figure has {len(g)}')
            if p['T'] == 25:
                mu0, curves = mui, p['curves']
            else:
                mu0 = mui_of_T(p['T'])
                expected = [1 / (gi + 1 / mu0) for gi in g]
                drawn = [a[0, 1] for a in p['curves']]
                if max(abs(d / e - 1) for d, e in zip(drawn, expected)) > MAX_PLACEMENT:
                    raise Refused(f'curves drawn at {[round(x) for x in drawn]}; the 25 C gaps and mu_i = {mu0:.0f} '
                                  f'put them at {[round(x) for x in expected]}')
                curves = [np.c_[a[:, 0], a[:, 1] * e / a[0, 1]] for a, e in zip(p['curves'], expected)]
            rows = solve_levels(curves, g, np.geomspace(0.97 * mu0, 0.03 * mu0, 60))
            rows = [r for r in rows if r['H'] >= MIN_SIGNIFICANCE * r['sH']]
            if len(rows) < 5:
                raise Refused(f'only {len(rows)} levels have a material field resolved to {MIN_SIGNIFICANCE} sigma '
                              f'by >= {MIN_CURVES} curves')
            worst = max(r['rms'] for r in rows)
            if worst > MAX_DISAGREEMENT:
                raise Refused(f'the gapped curves disagree by up to {100 * worst:.1f} % in H_DC at one material level')
            if rows[0]['L'] < ONSET_LEVEL * mu0:
                raise Refused(f'the first solved level is {rows[0]["L"] / mu0:.2f} of mu_rev(0) (at '
                              f'{rows[0]["H"]:.0f} A/m): the onset of the drop is not observed')
            for r1, r2 in zip(rows[:-1], rows[1:]):
                if r2['H'] < r1['H'] - 2 * np.hypot(r1['sH'], r2['sH']):
                    raise Refused(f'solved field falls from {r1["H"]:.0f} to {r2["H"]:.0f} A/m as the permeability falls')
            pts, fit = fit_and_sample(rows, mu0)
            if fit['chi2'] > MAX_CHI2:
                raise Refused(f'smooth fit chi2/dof {fit["chi2"]:.1f}')
            if p['T'] not in coercive:
                raise Refused('no coercive field in the table at this temperature')
            hc = coercive[p['T']]
            half = np.interp(hc / 2, [q[0] for q in pts], [q[1] for q in pts]) / mu0
            if half < REVERSIBLE_FLOOR:
                raise Refused(f'mu_rev falls to {half:.2f} of mu_rev(0) at Hc/2 = {hc / 2:.0f} A/m')
            for h, v in pts:
                points.append({'value': round(v, 1), 'temperature': p['T'], 'frequency': 10000.0,
                               'magneticFluxDensityPeak': 0.00025, 'magneticFieldDcBias': round(h, 1)})
            report.append(dict(T=p['T'], page=p['page'], n=len(g), mu0=mu0, worst_rms=worst, **fit,
                               ratio={h: round(float(np.interp(h, [q[0] for q in pts], [q[1] for q in pts]) / mu0), 3)
                                      for h in (15, 30, 45, 60) if h <= fit['hmax']}))
        except Refused as e:
            refused.append(f'{p["T"]:.0f} C: {e}')
    if not report:
        raise Refused(' | '.join(refused))
    return points, report, refused


def tdk_provenance(grade, report, url, sha):
    if report[0].get('single'):
        r = report[0]
        return {
            'source': 'manufacturerDatasheet',
            'sourceName': f'TDK Electronics, SIFERRIT material {grade} data sheet',
            'sourceUrl': url,
            'retrievedDate': datetime.date.today().isoformat(),
            'verification': 'digitizedFromGraph',
            'verificationDate': datetime.date.today().isoformat(),
            'verificationMethod': (
                f'"DC magnetic bias" figure (one curve, RM core with a residual gap, mu_e0 = {r["mu_e0"]:.0f}; B <= 0.25 mT, '
                f'f = 10 kHz, 25 C) on page {r["page"]}, read off its vector path; document sha256 {sha[:8]}...{sha[-4:]}. '
                f'The gap is taken out by Ampere, H_DC = H + g B(H)/mu0 with g = 1/mu_e0 - 1/mu_i (table mu_i), B(H) being '
                f'the midline of the same data sheet\'s 25 C dynamic magnetization loop (page {r["loop_page"]}). LESS CERTAIN '
                f'than a multi-curve solve: on N87, N49, N48 and N51 this single-curve method reproduces the multi-curve '
                f'result within 0.04-0.10 of mu_rev/mu_rev(0). Points on a fixed H grid up to {r["hmax"]:.0f} A/m, nothing fitted.'),
            'fields': ['permeability.reversible'],
        }
    figs = '; '.join(f'{r["T"]:.0f} C on page {r["page"]} ({r["n"]} gapped curves, field solved '
                     f'{r["hmin"]:.0f}-{r["hmax"]:.0f} A/m, curves agree within {100 * r["worst_rms"]:.1f} %)' for r in report)
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': f'TDK Electronics, SIFERRIT material {grade} data sheet',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'"DC magnetic bias" figures of gapped cores (B <= 0.25 mT, f = 10 kHz), read off their vector paths: {figs}; '
            f'document sha256 {sha[:8]}...{sha[-4:]}. Material values recovered by Ampere: each curve\'s gap from its drawn '
            f'zero-bias level and the table mu_i at 25 C; at each material permeability the field and flux density '
            f'solved jointly over the at least 3 curves showing it. Points sampled from mu_rev(0)/(1 + (H/H0)^c)^k fitted '
            f'to the solved levels; below the first solved field the drawing resolves no drop over 20 % and the points '
            f'follow the fitted shape. mu_rev(0) is the table mu_i at 25 C and the data sheet mu_i(T) curve otherwise.'),
        'fields': ['permeability.reversible'],
    }


# ---------------------------------------------------------------- TDG: field limits of gapped cores against mu_e

def polyline(segments, what):
    """The one open polyline the straight segments `segments` ((x0, y0, x1, y1), pieces drawn in any order and
    direction) form, as its vertices from one end to the other; refused unless they chain into exactly one."""
    pts = []
    def vid(x, y):
        for i, (u, v) in enumerate(pts):
            if abs(u - x) < 0.05 and abs(v - y) < 0.05:
                return i
        pts.append((x, y))
        return len(pts) - 1
    adj = {}
    for x0, y0, x1, y1 in segments:
        a, b = vid(x0, y0), vid(x1, y1)
        if a == b:
            continue
        adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    ends = [v for v, n in adj.items() if len(n) == 1]
    if len(ends) != 2 or any(len(n) > 2 for n in adj.values()):
        raise Refused(f'{what}: its segments do not chain into one open line')
    order, prev, cur = [ends[0]], None, ends[0]
    while True:
        nxt = [v for v in adj[cur] if v != prev]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
    if len(order) != len(adj):
        raise Refused(f'{what}: its segments form more than one line')
    return [pts[v] for v in order]


def tdg(grade, doc):
    page = doc[TDG_PAGES[grade] - 1]
    if not page.search_for(f'Material:{grade}'):
        raise Refused(f'page {page.number + 1} is not the {grade} material sheet')
    text = page.get_text()
    mui = re.findall(r'(\d{3,5})±25%', text)
    if len(mui) != 1:
        raise Refused(f'{len(mui)} initial permeabilities "<mu_i>±25%" in the table, one expected')
    mui = float(mui[0])
    if re.search(r'Hc|Coercivity', text):
        raise Refused('the sheet has a coercive field row, which this reader does not read: the Hc/2 check cannot run')
    lines = text_lines(page)
    caps = [r for r, d, t in lines if t == 'HDC Limit-μe']
    if len(caps) != 1:
        raise Refused(f'{len(caps)} "HDC Limit-μe" titles on page {page.number + 1}, one expected')
    cap = caps[0]
    ytit = [r for r, d, t in lines if t.startswith('HDC Limit') and '(A/m)' in t and abs(d[1]) > 0.99 and r.y0 > cap.y1]
    xtit = [r for r, d, t in lines if t == 'Effective permeability' and r.y0 > cap.y1]
    if len(ytit) != 1 or len(xtit) != 1:
        raise Refused(f'{len(ytit)} "HDC Limit (A/m)" and {len(xtit)} "Effective permeability" axis titles, one each expected')
    ytit, xtit = ytit[0], min(xtit, key=lambda r: r.y0)
    # the plot spans from the y-axis title to as far right of the x-axis title's centre as that title is left of it
    region = fitz.Rect(ytit.x1, cap.y1, 2 * (xtit.x0 + xtit.x1) / 2 - ytit.x1, xtit.y0)
    drawings, box, tox, toy, minw, _ = figure_axes(page, region)
    inside = lambda x, y: box.x0 - 0.5 <= x <= box.x1 + 0.5 and box.y0 - 0.5 <= y <= box.y1 + 0.5
    strokes = []        # (dashes, colour, segment) of every data-width stroke inside the plot
    for d in drawings:
        if (d.get('width') or 0) < minw or d.get('color') is None:
            continue
        for it in d['items']:      # (a straight horizontal stroke has an empty rect: test its points, not the rect)
            if not (all(inside(q.x, q.y) for q in it[1:] if isinstance(q, fitz.Point))):
                continue
            if it[0] != 'l':
                raise Refused(f'a data stroke inside the plot has a "{it[0]}" item: the lines are expected as straight segments')
            strokes.append((d.get('dashes'), colour_key(d['color']), (it[1].x, it[1].y, it[2].x, it[2].y)))
    # the legend: each level label inside the plot has exactly one short horizontal stroke just left of it, whose dash
    # pattern names that level's line
    styles = {}
    for r, d, t in lines:
        if t in TDG_LEVELS and box.contains(r):
            cy = (r.y0 + r.y1) / 2
            leg = [q for q in strokes if abs(q[2][1] - q[2][3]) < 0.01 and abs(q[2][1] - cy) < 3
                   and 0 <= r.x0 - max(q[2][0], q[2][2]) < 12 and abs(q[2][0] - q[2][2]) < 30]
            if len(leg) != 1:
                raise Refused(f'legend entry {t}: {len(leg)} legend strokes beside it, one expected')
            if t in styles:
                raise Refused(f'two "{t}" legend entries')
            styles[t] = leg[0]
    if set(styles) != set(TDG_LEVELS):
        raise Refused(f'legend entries {sorted(styles)}, expected {sorted(TDG_LEVELS)}')
    if len({q[:2] for q in styles.values()}) != len(styles):
        raise Refused('two legend entries share one line style')
    legend = [q[2] for q in styles.values()]
    rows, curves = [], {}
    for label, f in TDG_LEVELS.items():
        segs = [q[2] for q in strokes if q[:2] == styles[label][:2] and q[2] not in legend]
        v = polyline(segs, f'the {label} line')
        a = np.array(sorted((tox(x), toy(y)) for x, y in v))
        if np.any(np.diff(a[:, 0]) <= 0) or np.any(np.diff(a[:, 1]) >= 0):
            raise Refused(f'the {label} line is not a single falling line in mu_e')
        if a[-1, 0] >= mui:
            raise Refused(f'the {label} line reaches mu_e = {a[-1, 0]:.0f} >= mu_i = {mui:.0f}: no gap there')
        if len(a) < MIN_CURVES:
            raise Refused(f'the {label} line has {len(a)} mu_e points, {MIN_CURVES} needed')
        row = dict(L=f * mui, f=f, label=label, mue=(float(a[0, 0]), float(a[-1, 0])),
                   **ampere_line(1 / a[:, 0] - 1 / mui, a[:, 1]))
        if row['H'] < MIN_SIGNIFICANCE * row['sH']:
            raise Refused(f'{label} line: material field {row["H"]:.1f} A/m is below {MIN_SIGNIFICANCE} sigma ({row["sH"]:.1f} A/m)')
        if row['rms'] > MAX_DISAGREEMENT:
            raise Refused(f'{label} line: the mu_e points disagree by {100 * row["rms"]:.1f} % in H_DC with one material state')
        rows.append(row)
        curves[label] = a
    rows.sort(key=lambda r: -r['f'])
    for r1, r2 in zip(rows[:-1], rows[1:]):
        if r2['H'] < r1['H'] - 2 * np.hypot(r1['sH'], r2['sH']):
            raise Refused(f'solved field falls from {r1["H"]:.0f} to {r2["H"]:.0f} A/m as the permeability falls')
    pts = [(0.0, mui)] + [(r['H'], r['L']) for r in rows]
    points = [{'value': round(v, 1), 'magneticFieldDcBias': round(float(h), 1)} for h, v in pts]
    hs, vs = [q[0] for q in pts], [q[1] for q in pts]
    report = dict(T=None, page=page.number + 1, mu0=mui, hmin=0.0, hmax=float(rows[-1]['H']), flat0=True, rows=rows,
                  worst_rms=max(r['rms'] for r in rows),
                  ratio={h: round(float(np.interp(h, hs, vs) / mui), 3) for h in (15, 30, 45, 60) if h <= hs[-1]},
                  solved=[(round(float(r['H']), 1), round(float(r['sH']), 1), round(float(r['B']), 4), r['n'],
                           f'{100 * r["rms"]:.1f} %') for r in rows])
    return points, [report], []


def tdg_provenance(grade, report, url, sha):
    r = report[0]
    solved = '; '.join(f'{x["label"]} line ({x["n"]} mu_e points, mu_e {x["mue"][0]:.0f}-{x["mue"][1]:.0f}): '
                       f'L = {x["f"]:.1f} mu_i at H = {x["H"]:.1f} +- {x["sH"]:.1f} A/m, B = {1e3 * x["B"]:.0f} mT, '
                       f'points agree within {100 * x["rms"]:.1f} %' for x in r['rows'])
    return {
        'source': 'manufacturerDatasheet',
        'sourceName': 'TDG, 2006 MnZn ferrite catalogue',
        'sourceUrl': url,
        'retrievedDate': datetime.date.today().isoformat(),
        'verification': 'digitizedFromGraph',
        'verificationDate': datetime.date.today().isoformat(),
        'verificationMethod': (
            f'TDG\'s 2006 MnZn catalogue, as archived by the Wayback Machine (2017-10-25 capture of the MHW International '
            f'distributor copy); document sha256 {sha[:8]}...{sha[-4:]}. "HDC Limit-mu_e" figure of the {grade} sheet '
            f'(PDF page {r["page"]}): for gapped cores of effective permeability mu_e, the DC field at which the '
            f'permeability has dropped 20 % and 40 %; the catalogue names a permeability under DC bias incremental '
            f'permeability. Read off the vertices of the two vector lines on log axes calibrated on the figure\'s '
            f'gridlines. The gap is taken out by Ampere, read as the material reaching L = 0.8 and 0.6 mu_i: each mu_e '
            f'has g = 1/mu_e - 1/mu_i and H_DC = H + (B/mu0) g, a line in g fitted with sigma = 1 % of H_DC: {solved}. '
            f'mu_i = {r["mu0"]:.0f} is the sheet\'s table value (25 C, 10 kHz); the sheet gives no coercive field, so '
            f'the mu(Hc/2) check was not applied. The figure states no temperature or frequency, so none is written. '
            f'Only H = 0 (mu_i) and the two solved points are written; nothing is interpolated between them.'),
        'fields': ['permeability.incremental'],
    }


def mui_table(record, T):
    """mu_i(T) of the database record (the data sheet's mu_i(T) curve), linear between tabulated temperatures."""
    if record is None:
        raise Refused(f'no database record for mu_i({T:.0f} C)')
    pts = record['permeability']['initial']
    pts = pts if isinstance(pts, list) else [pts]
    tab = sorted((q['temperature'], q['value']) for q in pts if q.get('temperature') is not None and not q.get('magneticFieldDcBias'))
    if len(tab) < 2 or not tab[0][0] <= T <= tab[-1][0]:
        raise Refused(f'mu_i(T) in the database does not cover {T:.0f} C')
    return float(np.interp(T, [t for t, _ in tab], [v for _, v in tab]))


def mui_start_check(points, record):
    """Refuse a curve whose start disagrees with the record's initial permeability: the curve's value at its lowest H
    (H = 0 where written), at the curve temperature nearest 25 C, against the record's zero-bias
    permeability.initial at the temperature nearest 25 C (a record whose mu_i points state no temperature gives its
    one nominal value); more than MUI_START_TOL apart means a misread axis or a different material."""
    if record is None:
        raise Refused('no ferrite record in the database to check the curve start against')
    pts = record['permeability']['initial']
    pts = pts if isinstance(pts, list) else [pts]
    zero = [q for q in pts if not q.get('magneticFieldDcBias')]
    with_t = [q for q in zero if q.get('temperature') is not None]
    if with_t:
        t_rec = min((q['temperature'] for q in with_t), key=lambda t: abs(t - 25))
        values = sorted(set(q['value'] for q in with_t if q['temperature'] == t_rec))
        where = f'{t_rec:g} C'
    else:
        values = sorted(set(q['value'] for q in zero))
        where = 'no temperature stated'
    if len(values) != 1:
        raise Refused(f'record has {len(values)} zero-bias mu_i values at {where}: {values}, one expected')
    temps = [q.get('temperature') for q in points]
    known = [t for t in temps if t is not None]
    t_cur = min(known, key=lambda t: abs(t - 25)) if known else None
    start = min((q for q in points if q.get('temperature') == t_cur), key=lambda q: q['magneticFieldDcBias'])
    mui = values[0]
    if abs(start['value'] / mui - 1) > MUI_START_TOL:
        raise Refused(f'curve starts at {start["value"]:g} (H = {start["magneticFieldDcBias"]:g} A/m'
                      + (f', {t_cur:g} C' if t_cur is not None else '') + f'), record mu_i is {mui:g} ({where}): '
                      f'{100 * (start["value"] / mui - 1):+.0f} %, beyond +-{100 * MUI_START_TOL:.0f} %')


def maker_of(record):
    return record.get('manufacturerInfo', {}).get('name', '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', required=True)
    ap.add_argument('--patch')
    ap.add_argument('grades', nargs='*')
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    db = args.patch or os.path.join(os.path.dirname(__file__), '..', 'data', 'core_materials.ndjson')
    records = [json.loads(line) for line in open(db)]
    def record_index(grade):
        """Line index of the one ferrite record of this grade and maker, or None. Every maker read here also sells
        non-ferrite materials (Magnetics: powder cores) that a ferrite curve must never patch, so only records with
        material == "ferrite" match; more than one match is an error, never a choice."""
        maker = SOURCES[grade][0].upper()
        hits = [i for i, m in enumerate(records) if m['name'] == grade and m.get('material') == 'ferrite' and maker_of(m)
                and (maker_of(m).split()[0].upper().startswith(maker) or (maker == 'TDK' and maker_of(m).split()[0].upper().startswith('EPCOS')))]
        if len(hits) > 1:
            raise RuntimeError(f'{grade} ({SOURCES[grade][0]}): {len(hits)} ferrite records match (lines {[i + 1 for i in hits]}), one expected')
        return hits[0] if hits else None
    def record(grade):
        i = record_index(grade)
        return None if i is None else records[i]
    results = {}
    for grade in args.grades or sorted(SOURCES):
        maker = SOURCES[grade][0]
        try:
            url, path, sha = fetch(grade, args.cache)
            if maker == 'Fair-Rite':
                points, report, refused = fairrite(grade, path)
            elif maker == 'DMEGC':
                points, report, refused = dmegc(grade, fitz.open(path))
            elif maker == 'Magnetics':
                points, report, refused = magnetics(grade, fitz.open(path))
            elif maker == 'TDG':
                points, report, refused = tdg(grade, fitz.open(path))
            elif maker == 'TDK':
                points, report, refused = tdk(grade, fitz.open(path), lambda T, g=grade: mui_table(record(g), T))
            else:
                points, report, refused = ferroxcube(grade, fitz.open(path))
            mui_start_check(points, record(grade))
        except Refused as e:
            print(f'{grade} ({maker}): REFUSED: {e}')
            continue
        results[grade] = (points, report, url, sha, record_index(grade))
        for r in refused:
            print(f'{grade} ({maker}): figure refused: {r}')
        for r in report:
            t = f'{r["T"]:.0f} C' if r['T'] is not None else 'T unstated'
            print(f'{grade} ({maker}) {t}: mu_rev(0) {r["mu0"]:.0f}, {r["hmin"]:.3g}-{r["hmax"]:.3g} A/m, '
                  f'mu_rev(H)/mu_rev(0) {r["ratio"]}' + (f', curves agree {100 * r["worst_rms"]:.1f} %, fit chi2/dof {r["chi2"]:.1f}' if 'chi2' in r else '')
                  + (f', solved (H, sH, B, n, disagreement) {r["solved"]}' if 'solved' in r else ''))
    if not args.patch:
        return
    out, done, url_differs = [], set(), []
    for index, line in enumerate(open(args.patch).read().splitlines()):
        m = json.loads(line)
        ascii_form = json.dumps(m) == line          # keep each line in the encoding it was written in
        grade = m.get('name')
        if grade in results and results[grade][4] == index:
            points, report, url, sha, _ = results[grade]
            maker = SOURCES[grade][0]
            field = 'reversible' if maker in ('TDK', 'Ferroxcube') else 'incremental'
            m['permeability'][field] = points
            prov = [p for p in m.get('provenance', []) if f'permeability.{field}' not in (p.get('fields') or [])]
            prov.append({'TDK': tdk_provenance, 'Ferroxcube': ferroxcube_provenance, 'Fair-Rite': fairrite_provenance,
                         'Magnetics': magnetics_provenance, 'DMEGC': dmegc_provenance,
                         'TDG': tdg_provenance}[maker](grade, report, url, sha))
            m['provenance'] = prov
            # the record names its source: set manufacturerInfo.datasheetUrl when absent, never overwrite it
            info = m.setdefault('manufacturerInfo', {})
            source = FR_PAGE.format(grade=grade) if maker == 'Fair-Rite' else url
            if not info.get('datasheetUrl'):
                info['datasheetUrl'] = source
            elif info['datasheetUrl'] != source:
                url_differs.append((grade, info['datasheetUrl'], source))
            done.add(grade)
            line = json.dumps(m, ensure_ascii=ascii_form)
        out.append(line)
    open(args.patch, 'w').write('\n'.join(out) + '\n')
    print(f'patched {sorted(done)}; accepted but not in the database: {sorted(set(results) - done)}')
    for grade, have, source in url_differs:
        print(f'{grade}: datasheetUrl kept as {have}; digitised from {source}')


if __name__ == '__main__':
    main()
