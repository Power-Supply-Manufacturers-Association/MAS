#!/usr/bin/env python3
"""Extract specific-power-loss curves from a Ferroxcube material data sheet (MDS) PDF.

The MDS PDFs are vector, not scans, so the loss curves can be read out exactly instead of
digitised from pixels. Two figures carry everything a Steinmetz fit needs:

  Fig.6  Pv vs peak flux density at a fixed temperature, one straight log-log line per
         frequency   -> the (f, B) plane, i.e. alpha and beta
  Fig.7  Pv vs temperature for a few (f, B) combinations, drawn as Beziers
         -> the ct(T) shape

Mechanics worth knowing before touching this:
  * pdftocairo emits every <path> with transform="matrix(1, 0, 0, -1, 0, H)", i.e. a y-flip,
    while the <use> elements that place text are already in page coordinates. Mixing the two
    without flipping puts the curves in the wrong figure — they land in the box vertically
    mirrored about the page centre, which is another figure of the same sheet.
  * The curves are Beziers; keeping only each segment's endpoint turns a U-shaped Pv(T) curve
    into a straight line. They are sampled here.
  * Grid lines are 2-point subpaths that span a figure box edge to edge; curves are everything
    else inside the box.

Calibration comes from the grid: the box edges are the axis extremes, which the caller states
per figure (they are printed on the sheet and do not vary within a family).

Usage:
    python3 scripts/extract-ferroxcube-loss.py 3f3.pdf --material 3F3 \
        --loss-vs-b  T=100 x=1,1000 y=10,10000 f=700,400,200,100,25 \
        --loss-vs-t  x=0,120 y=0,400 pairs=200/100,400/50,25/200,100/100
Emits MAS volumetricLosses points (W/m3, T, Hz) as JSON on stdout.
"""
import argparse, json, math, re, subprocess, sys, tempfile, os

BEZIER_SAMPLES = 12


def page_svg(pdf, page):
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, 'p.svg')
        subprocess.run(['pdftocairo', '-svg', '-f', str(page), '-l', str(page), pdf, out],
                       check=True, capture_output=True)
        return open(out, encoding='utf-8').read()


def page_height(svg):
    m = re.search(r'height="([\d.]+)"', svg)
    return float(m.group(1))


def subpaths(d, H):
    """Parse a path's `d` into subpaths of page-coordinate points (undoing pdftocairo's y-flip)."""
    subs, cur, pt = [], [], (0.0, 0.0)
    def flip(x, y):
        return (x, H - y)
    for m in re.finditer(r'([MLCZ])\s*([-\d\.\s,]*)', d):
        cmd = m.group(1)
        a = [float(x) for x in re.findall(r'-?\d+\.?\d*', m.group(2))]
        if cmd == 'M':
            if cur:
                subs.append(cur)
            cur = []
            for i in range(0, len(a) - 1, 2):
                pt = (a[i], a[i + 1])
                cur.append(flip(*pt))
        elif cmd == 'L':
            for i in range(0, len(a) - 1, 2):
                pt = (a[i], a[i + 1])
                cur.append(flip(*pt))
        elif cmd == 'C':
            for i in range(0, len(a) - 5, 6):
                p0, p1, p2, p3 = pt, (a[i], a[i+1]), (a[i+2], a[i+3]), (a[i+4], a[i+5])
                for s in range(1, BEZIER_SAMPLES + 1):
                    t = s / BEZIER_SAMPLES
                    u = 1 - t
                    x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
                    y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
                    cur.append(flip(x, y))
                pt = p3
        if cmd in 'ML' and a:
            pt = (a[-2], a[-1])
    if cur:
        subs.append(cur)
    return subs


def all_subpaths(svg):
    H = page_height(svg)
    body = svg[svg.index('</defs>'):]
    out = []
    for attrs, d in re.findall(r'<path([^>]*)\sd="([^"]+)"', body):
        if 'stroke' not in attrs:
            continue
        for sp in subpaths(d, H):
            if len(sp) >= 2:
                out.append(sp)
    return out


def find_boxes(subs, min_lines=4):
    """A figure box is where a bundle of horizontal grid lines sharing an x-span meets a bundle
    of vertical ones sharing a y-span. Clustering by bbox containment does not work: a vertical
    grid line's bbox never contains a horizontal one's."""
    from collections import defaultdict
    hor, ver = defaultdict(list), defaultdict(list)
    for sp in subs:
        if len(sp) != 2:
            continue
        (x1, y1), (x2, y2) = sp
        # Group horizontals by their LEFT edge only: on the Pv(T) sheet some of them run on
        # into the legend table, so grouping by the full span splits one figure in two.
        if abs(y1 - y2) < 0.3 and abs(x1 - x2) > 20:
            hor[round(min(x1, x2))].append((y1, max(x1, x2)))
        elif abs(x1 - x2) < 0.3 and abs(y1 - y2) > 20:
            ver[(round(min(y1, y2)), round(max(y1, y2)))].append(x1)
    boxes = []
    for hx0, hs in hor.items():
        if len(hs) < min_lines:
            continue
        # Two figures stacked in the same column share a left edge, so split the y values
        # wherever there is a gap much larger than the typical grid spacing.
        hs = sorted(hs)
        gaps = [b[0] - a[0] for a, b in zip(hs, hs[1:])]
        typical = sorted(gaps)[len(gaps) // 2] if gaps else 0
        clusters, cur = [], [hs[0]]
        for prev, item in zip(hs, hs[1:]):
            if typical and item[0] - prev[0] > max(6 * typical, 30):
                clusters.append(cur); cur = []
            cur.append(item)
        clusters.append(cur)
        for cl in clusters:
            if len(cl) < min_lines:
                continue
            ys = [y for y, _ in cl]
            rights = sorted(x for _, x in cl)
            hx1 = rights[len(rights) // 2]             # median right edge
            for (vy0, vy1), xs in ver.items():
                if len(xs) < min_lines:
                    continue
                if abs(min(ys) - vy0) < 2 and abs(max(ys) - vy1) < 2 and abs(min(xs) - hx0) < 2:
                    boxes.append((min(xs), hx1, min(ys), max(ys), len(ys) + len(xs)))
    return boxes


def curves_in(subs, box, pad=2.0):
    x0, x1, y0, y1 = box[:4]
    out = []
    for sp in subs:
        xs = [p[0] for p in sp]; ys = [p[1] for p in sp]
        if min(xs) < x0 - pad or max(xs) > x1 + pad or min(ys) < y0 - pad or max(ys) > y1 + pad:
            continue
        dx, dy = max(xs) - min(xs), max(ys) - min(ys)
        # A curve crosses a real fraction of the plot. Absolute thresholds also admit the
        # little boxed part-number label Ferroxcube puts inside the top-right corner.
        if dx < 0.10 * (x1 - x0) or dy < 0.10 * (y1 - y0):
            continue
        out.append(sp)
    return out


def log_map(v0, v1, p0, p1):
    ld = math.log10(v1 / v0)
    return lambda p: v0 * 10 ** ((p - p0) / (p1 - p0) * ld)


def lin_map(v0, v1, p0, p1):
    return lambda p: v0 + (p - p0) / (p1 - p0) * (v1 - v0)


def parse_kv(items):
    out = {}
    for it in items:
        k, _, v = it.partition('=')
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('--material', required=True)
    ap.add_argument('--page', type=int, default=3)
    ap.add_argument('--loss-vs-b', nargs='+', default=None,
                    help='T=100 x=1,1000 y=10,10000 f=700,400,200,100,25  (kHz, left curve first)')
    ap.add_argument('--loss-vs-t', nargs='+',
                    help='x=0,120 y=0,400 pairs=200/100,400/50,25/200,100/100  (kHz/mT)')
    ap.add_argument('--box-index', type=int, default=None,
                    help='override automatic figure selection (see --list-boxes)')
    ap.add_argument('--list-boxes', action='store_true')
    args = ap.parse_args()

    svg = page_svg(args.pdf, args.page)
    subs = all_subpaths(svg)
    boxes = find_boxes(subs)
    boxes.sort(key=lambda b: (b[2], b[0]))
    if args.list_boxes:
        for i, b in enumerate(boxes):
            print(f"box {i}: x[{b[0]:.1f},{b[1]:.1f}] y[{b[2]:.1f},{b[3]:.1f}] "
                  f"gridlines={b[4]} curves={len(curves_in(subs, b))}")
        return 0

    points = []

    cfg = parse_kv(args.loss_vs_b)
    Tb = float(cfg['T'])
    bx0, bx1 = [float(v) for v in cfg['x'].split(',')]
    by0, by1 = [float(v) for v in cfg['y'].split(',')]
    freqs = [float(v) * 1e3 for v in cfg['f'].split(',')]
    # the Pv-vs-B figure is the log-log one: its grid lines are unevenly spaced
    cands = [(i, b) for i, b in enumerate(boxes) if len(curves_in(subs, b)) == len(freqs)]
    if args.box_index is not None:
        cands = [(args.box_index, boxes[args.box_index])]
    if not cands:
        print(f"no figure box holds {len(freqs)} curves; try --list-boxes", file=sys.stderr)
        return 1
    bi, box = cands[0]
    cs = curves_in(subs, box)
    fx = log_map(bx0, bx1, box[0], box[1])
    fy = log_map(by0, by1, box[3], box[2])
    cs.sort(key=lambda sp: min(p[0] for p in sp))       # leftmost = highest frequency
    for f, sp in zip(freqs, cs):
        for x, y in sp:
            points.append({'f': f, 'B': fx(x) / 1000.0, 'T': Tb, 'Pv': fy(y) * 1000.0})

    if args.loss_vs_t:
        cfg = parse_kv(args.loss_vs_t)
        tx0, tx1 = [float(v) for v in cfg['x'].split(',')]
        ty0, ty1 = [float(v) for v in cfg['y'].split(',')]
        pairs = [(float(a) * 1e3, float(b) / 1000.0)
                 for a, b in (p.split('/') for p in cfg['pairs'].split(','))]
        cands = [(i, b) for i, b in enumerate(boxes)
                 if i != bi and len(curves_in(subs, b)) == len(pairs)]
        if not cands:
            print(f"no figure box holds {len(pairs)} Pv(T) curves; skipping", file=sys.stderr)
        else:
            box = cands[0][1]
            cs = curves_in(subs, box)
            # the legend sits to the right of the plot; the x axis ends at the last gridline
            # that a curve actually reaches
            xmax = max(max(p[0] for p in sp) for sp in cs)
            fx = lin_map(tx0, tx1, box[0], xmax)
            fy = lin_map(ty0, ty1, box[3], box[2])
            # Order by the value at the RIGHT edge, which is where Ferroxcube's legend table
            # sits and how its rows line up. Sorting by each curve's highest point instead gets
            # it wrong: these curves cross, so the vertical order at 0 C is not the order at 120 C.
            cs.sort(key=lambda sp: min(p[1] for p in sp if p[0] >= max(q[0] for q in sp) - 1))
            for (f, B), sp in zip(pairs, cs):
                for x, y in sp:
                    points.append({'f': f, 'B': B, 'T': fx(x), 'Pv': fy(y) * 1000.0})

    print(json.dumps({'material': args.material, 'points': points}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
