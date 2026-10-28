#!/usr/bin/env python3
"""Read the loss curves of DMEGC DMR52, DMR55 and DMR90 from their data sheets' vector charts.

    python3 scripts/extract-dmegc-pvt-curves.py DMR55 "DMR55 Material Datasheet.pdf" > dmr55-pvt.json
    python3 scripts/extract-dmegc-pvt-curves.py DMR90 "DMR90 Material Datasheet.pdf" > dmr90-pvt.json
    python3 scripts/extract-dmegc-pvt-curves.py DMR52 fericor-108-dmr52_material_characteristics_sl.pdf > dmr52.json

Sources (the DMEGC "Mn-Zn ferrite series" catalogue pages, CorelDRAW PDFs dated 2012-04-27, no
revision mark printed), read 2026-10-28:
  DMR55  https://ferrite.ru/upload/docs/pdf/DMR55%20Material%20Datasheet.pdf
         245,537 B, sha256 b8acfe365eabbffc0f3936ca7b6f75e2ebf4130e188facd41d37e56fa8f9193e
         catalogue pages 27-28; Pv-T chart on PDF page 2 (top right), 5 curves
  DMR90  https://ferrite.ru/upload/docs/pdf/DMR90%20Material%20Datasheet.pdf
         241,057 B, sha256 7d0e8025a254f0d9a08a997366f895bbf08e728b77eb91ee54da410346d00292
         catalogue pages 29-30; Pv-T chart on PDF page 2 (top right), 4 curves

  DMR52  DMR52-REV.A, dated 2014-07 (test core: toroid 20 x 10 x 5 mm), as hosted by Fericor:
         https://web.archive.org/web/20230322201548/https://fericor.com/uploads/fericor/public/document/108-dmr52_material_characteristics_sl.pdf
         139,167 B, sha256 df8d5ef6be0e17d3cc42dfaff810e03035f150f2363a8d1de908fcdef7e1899a
         PDF page 3: Pv-B at 25 C and at 100 C (log-log, 1/2/3 MHz) and Pv-T (3 MHz/10, 20, 30 mT,
         2 MHz/30 mT); see CHARTS below.

Method (DMR55, DMR90): each curve is one or two cubic Bezier strokes (no markers). The axes are calibrated on the
chart's own gridlines (residual printed on stderr), the strokes are evaluated exactly, and each
curve is sampled at its first point, every 5 C, and its last point. Output in kW/m3 (= mW/cm3).

Which stroke is which condition: the charts carry text labels beside the curves, not legend
swatches, so the colour -> condition map below is stated explicitly. It is the only assignment
consistent with (a) the label order beside the curves, (b) the page-1 typical-value table
(the rank of the four 100 C values, DMR55; the 100 kHz/200 mT row, DMR90) and (c) the maker's
Pv-B curves at 25/100 C already in MAS. The checks are printed on stderr.

Method (DMR52, CHARTS): every curve is one path of straight segments and cubic Beziers, evaluated
exactly. Pv-T curves are sampled at their ends and every 5 C, Pv-B curves at their ends and every
5 mT. A Pv-B condition that the Pv-T chart also draws (same f, B and T) is taken from the Pv-T chart
only, and the two readings are compared on stderr.
Axes of the two log-log Pv-B charts: Pv is calibrated on all 28 horizontal gridlines (1..1000,
frame included). B is calibrated on the frame, whose ends carry the printed labels 10 and 100 mT;
the eight vertical minor gridlines of both charts are drawn 0.046 decade to the right of 20..90 mT
of that frame (they fit 10..80 mT of a 9..90 mT axis instead) and are NOT used. The frame calibration
is the one consistent with the curves: every 1 and 2 MHz curve ends at 50.0 mT and every 3 MHz
curve at 30.0 mT (the highest flux of the Pv-T chart), and the 3 MHz/30 mT/100 C value read from it
(900) is the one the Pv-T chart and the printed table give; the gridline reading would end the
curves at 45 and 27 mT. The offset is printed on stderr.
Which path is which condition (no legend, text labels beside the curve ends): Pv-B, the label box
each curve ends in (3 MHz green, 2 MHz red, 1 MHz black, both charts); Pv-T, the label beside each
curve's 100 C end (3 MHz/30 mT black, 3 MHz/20 mT red, 2 MHz/30 mT blue, 3 MHz/10 mT green). The
end-to-label distances and the table checks are printed on stderr.
"""
import sys, json
import numpy as np
import pymupdf as fitz

CFG = {
    'DMR55': dict(
        page=1, box=(340, 228, 490, 340), x0=0, dx=20, y0=0, dy=100,
        curves={  # stroke colour (rounded to 2 decimals) -> (frequency Hz, peak B T)
            (0.14, 0.12, 0.13): (100e3, 0.200),
            (0.0, 0.65, 0.32): (300e3, 0.100),
            (0.93, 0.11, 0.14): (200e3, 0.100),
            (0.0, 0.58, 0.85): (500e3, 0.050),
            (0.18, 0.19, 0.57): (400e3, 0.050),
        },
        # page-1 table, mW/cm3: {(f, B): {T: Pv}}
        table={(200e3, 0.1): {100: 170}, (300e3, 0.1): {100: 360},
               (400e3, 0.05): {100: 115}, (500e3, 0.05): {100: 200}},
    ),
    'DMR90': dict(
        page=1, box=(330, 225, 510, 350), x0=0, dx=25, y0=0, dy=100,
        curves={
            (0.93, 0.11, 0.14): (100e3, 0.200),
            (0.0, 0.65, 0.32): (200e3, 0.100),
            (0.0, 0.68, 0.94): (500e3, 0.050),
            (0.14, 0.12, 0.13): (25e3, 0.200),
        },
        table={(100e3, 0.2): {25: 750, 60: 465, 100: 370, 120: 450}},
    ),
}

# DMR52: several charts, each a dict of path colour -> condition. 'sweep' is the swept variable.
CHARTS = {
    'DMR52': dict(
        page=2,
        table={(3e6, 0.010, 100): 100, (3e6, 0.030, 100): 900},  # page-1 typical-value table, mW/cm3
        charts=[
            dict(name='Pv-T', box=(195, 335, 420, 505), sweep='T', x=('lin', 0, 20), y=('lin', 0, 100),
                 curves={(0.0, 0.0, 0.0): (3e6, 0.030), (1.0, 0.0, 0.0): (3e6, 0.020),
                         (0.0, 0.0, 1.0): (2e6, 0.030), (0.0, 1.0, 0.0): (3e6, 0.010)},
                 labels={(0.0, 0.0, 0.0): '3MHz,30mT', (1.0, 0.0, 0.0): '3MHz,20mT',
                         (0.0, 0.0, 1.0): '2MHz,30mT', (0.0, 1.0, 0.0): '3MHz,10mT'}),
            dict(name='Pv-B 25 C', box=(80, 130, 290, 290), sweep='B', T=25, x=('log-frame', 10, 100),
                 y=('log-grid', 1, 1000),
                 curves={(0.0, 1.0, 0.0): 3e6, (1.0, 0.0, 0.0): 2e6, (0.0, 0.0, 0.0): 1e6},
                 labels={(0.0, 1.0, 0.0): '3MHz', (1.0, 0.0, 0.0): '2MHz', (0.0, 0.0, 0.0): '1MHz'}),
            # its top frame line stands 0.18 decade above the 1000 gridline (the 1000 label sits on that
            # gridline), so the frame top is not a gridline and is left out of the calibration
            dict(name='Pv-B 100 C', box=(320, 130, 535, 292), sweep='B', T=100, x=('log-frame', 10, 100),
                 y=('log-grid', 1, 1000), y_frame_top_off_grid=True,
                 curves={(0.0, 1.0, 0.0): 3e6, (1.0, 0.0, 0.0): 2e6, (0.0, 0.0, 0.0): 1e6},
                 labels={(0.0, 1.0, 0.0): '3MHz', (1.0, 0.0, 0.0): '2MHz', (0.0, 0.0, 0.0): '1MHz'}),
        ],
    ),
}


def path_points(items, n=2000):
    """Points along a path of straight segments ('l') and cubic Beziers ('c'), in drawing order."""
    pts = []
    for it in items:
        if it[0] == 'l':
            pts.append(np.array([[it[1].x, it[1].y], [it[2].x, it[2].y]]))
        elif it[0] == 'c':
            P = np.array([[q.x, q.y] for q in it[1:]])
            t = np.linspace(0, 1, n)[:, None]
            pts.append((1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t * t * P[2] + t ** 3 * P[3])
        else:
            raise ValueError(f'unexpected path item {it[0]}')
    return np.vstack(pts)


def log_grid_values(lo, hi):
    """1, 2, ..., 9, 10, 20, ..., hi: the gridline values of a log axis from lo to hi."""
    v, d = [], lo
    while d < hi:
        v += [d * m for m in range(1, 10)]
        d *= 10
    return v + [hi]


def calibrate(axis, lines, frame, spec, label):
    """Map page coordinate -> value for one axis. Returns (f(u) -> value, report string)."""
    kind, a, b = spec
    if kind == 'lin':  # gridlines every b from a
        vals = a + b * np.arange(len(lines))
        m, c = np.polyfit(lines, vals, 1)
        res = max(abs(np.polyval([m, c], lines) - vals))
        return (lambda u: np.polyval([m, c], u)), f'{label}: {len(lines)} gridlines {vals[0]:g}..{vals[-1]:g}, residual {res:.3f}'
    if kind == 'log-grid':  # every decade and minor gridline, frame included
        vals = np.log10(log_grid_values(a, b))
        if len(lines) != len(vals):
            raise ValueError(f'{label}: {len(lines)} gridlines, expected {len(vals)} for {a}..{b}')
        m, c = np.polyfit(lines, vals, 1)
        res = max(abs(np.polyval([m, c], lines) - vals))
        return (lambda u: 10 ** np.polyval([m, c], u)), f'{label}: {len(lines)} gridlines {a:g}..{b:g}, residual {res:.4f} decade'
    if kind == 'log-frame':  # frame ends carry the labels a and b
        u0, u1 = frame
        m = (np.log10(b) - np.log10(a)) / (u1 - u0)
        f = lambda u: 10 ** (np.log10(a) + m * (np.asarray(u) - u0))
        minors = [u for u in lines if u0 + 0.5 < u < u1 - 0.5]
        ratio = [float(f(u)) / (a * (k + 1)) for k, u in enumerate(minors)]  # against a, 2a, 3a, ...
        return f, (f'{label}: frame {u0:.2f}..{u1:.2f} = {a:g}..{b:g}; {len(minors)} minor gridlines read '
                   f'{", ".join(f"{float(f(u)):.1f}" for u in minors)}, i.e. {min(ratio):.4f}..{max(ratio):.4f} x '
                   f'{a:g}, {2 * a:g}, ... {len(minors) * a:g} (not used)')
    raise ValueError(kind)


def sample_grid(X, steps, tol=0.05):
    """The round steps inside the drawn span (an end drawn within tol of a step counts as that step),
    plus each end that is not such a step."""
    grid = [float(g) for g in steps if X[0] - tol <= g <= X[-1] + tol]
    for e in (X[0], X[-1]):
        if all(abs(e - g) > tol for g in grid):
            grid.append(round(float(e), 2))
    return sorted(grid)


def read_charts(name, pdf):
    cfg = CHARTS[name]
    page = fitz.open(pdf)[cfg['page']]
    drawings = page.get_drawings()
    words = page.get_text('words')
    out, seen = [], {}
    for ch in cfg['charts']:
        bx0, by0, bx1, by1 = ch['box']
        vx, hy, paths = set(), set(), {}
        for d in drawings:
            r = d['rect']
            if not (r.x0 >= bx0 and r.x1 <= bx1 and r.y0 >= by0 and r.y1 <= by1):
                continue
            its = d['items']
            if len(its) == 1 and its[0][0] == 'l':
                a, b = its[0][1], its[0][2]
                if abs(a.x - b.x) < 0.01 and abs(a.y - b.y) > 50:
                    vx.add(round(a.x, 2))
                elif abs(a.y - b.y) < 0.01 and abs(a.x - b.x) > 50:
                    hy.add(round(a.y, 2))
            elif len(its) > 1 and d['color'] and d.get('fill') is None:
                col = tuple(round(v, 2) for v in d['color'])
                if col in paths:
                    raise ValueError(f'{ch["name"]}: two paths with colour {col}')
                paths[col] = its
        VX, HY = sorted(vx), sorted(hy, reverse=True)
        fx, rx = calibrate('x', VX, (VX[0], VX[-1]), ch['x'], f'{ch["name"]} x')
        top_off = ch.get('y_frame_top_off_grid', False)
        fy, ry = calibrate('y', HY[:-1] if top_off else HY, (HY[0], HY[-1]), ch['y'], f'{ch["name"]} y')
        if top_off:
            ry += f'; frame top (not a gridline) reads {float(fy(HY[-1])):.0f}'
        print(f'{name} {rx}', file=sys.stderr)
        print(f'{name} {ry}', file=sys.stderr)
        if set(paths) != set(ch['curves']):
            raise ValueError(f'{ch["name"]}: path colours {sorted(paths)} != configured {sorted(ch["curves"])}')
        for col, cond in ch['curves'].items():
            p = path_points(paths[col])
            X, Y = fx(p[:, 0]), fy(p[:, 1])
            keep = np.concatenate([[True], np.diff(X) != 0])
            X, Y = X[keep], Y[keep]
            if np.any(np.diff(X) < 0):
                raise ValueError(f'{ch["name"]} curve {col} is not monotonic')
            # nearest printed label to the curve's last point
            ex, ey = p[-1]
            lab = min(((abs((w[0] + w[2]) / 2 - ex) + abs((w[1] + w[3]) / 2 - ey), w[4]) for w in words
                       if 'MHz' in w[4] and bx0 <= w[0] <= bx1 + 20 and by0 <= w[1] <= by1), key=lambda t: t[0])
            if lab[1] != ch['labels'][col]:
                raise ValueError(f'{ch["name"]} curve {col}: nearest label {lab[1]!r}, configured {ch["labels"][col]!r}')
            if ch['sweep'] == 'T':
                f, B = cond
                grid = sample_grid(X, range(-50, 200, 5))
                rows = [(f, B, float(g), float(np.interp(g, X, Y))) for g in grid]
                span = f'{X[0]:.2f}..{X[-1]:.2f} C'
                cname = f'{f / 1e6:g} MHz {B * 1e3:g} mT'
            else:
                f, T = cond, ch['T']
                Xm = X  # mT
                grid = sample_grid(Xm, range(0, 1000, 5))
                lx, ly = np.log10(Xm), np.log10(Y)
                rows = [(f, g / 1e3, float(T), float(10 ** np.interp(np.log10(g), lx, ly))) for g in grid]
                span = f'{Xm[0]:.2f}..{Xm[-1]:.2f} mT'
                cname = f'{f / 1e6:g} MHz {T} C'
            print(f'  {cname}: label {lab[1]!r} {lab[0]:.1f} pt from the curve end, span {span}', file=sys.stderr)
            for f_, B_, T_, P_ in rows:
                key = (f_, round(B_, 6), round(T_, 2))
                if key in seen:
                    print(f'    {f_ / 1e6:g} MHz {B_ * 1e3:g} mT {T_:g} C: {P_:.1f} here, {seen[key]:.1f} from the '
                          f'{"Pv-T" if ch["sweep"] == "B" else "Pv-B"} chart ({P_ / seen[key]:.3f}); kept the Pv-T reading',
                          file=sys.stderr)
                    continue
                seen[key] = P_
                out.append({"f": f_, "B": round(B_, 6), "T": round(T_, 2), "Pv_kWm3": round(P_, 2)})
    for (f, B, T), v in cfg['table'].items():
        got = seen.get((f, B, float(T)))
        print(f'{name} table {f / 1e6:g} MHz {B * 1e3:g} mT {T} C: drawn {got:.1f} / printed {v} = {got / v:.3f}', file=sys.stderr)
    return out


def bezier(items, n=2000):
    pts = []
    for it in items:
        if it[0] != 'c':
            raise ValueError(f'unexpected path item {it[0]}')
        P = np.array([[q.x, q.y] for q in it[1:]])
        t = np.linspace(0, 1, n)[:, None]
        pts.append((1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t * t * P[2] + t ** 3 * P[3])
    return np.vstack(pts)


def main():
    name, pdf = sys.argv[1], sys.argv[2]
    if name in CHARTS:
        json.dump(read_charts(name, pdf), sys.stdout, indent=0)
        return
    c = CFG[name]
    page = fitz.open(pdf)[c['page']]
    bx0, by0, bx1, by1 = c['box']
    vx, hy, strokes = set(), set(), {}
    for d in page.get_drawings():
        r = d['rect']
        if not (r.x0 >= bx0 and r.x1 <= bx1 and r.y0 >= by0 and r.y1 <= by1):
            continue
        its = d['items']
        if len(its) == 1 and its[0][0] == 'l':
            a, b = its[0][1], its[0][2]
            if abs(a.x - b.x) < 0.01 and abs(a.y - b.y) > 50:
                vx.add(round(a.x, 2))
            elif abs(a.y - b.y) < 0.01 and abs(a.x - b.x) > 50:
                hy.add(round(a.y, 2))
        elif its and all(it[0] == 'c' for it in its) and d['color']:
            col = tuple(round(v, 2) for v in d['color'])
            if col in strokes:
                raise ValueError(f'two strokes with colour {col}')
            strokes[col] = its
    VX, HY = sorted(vx), sorted(hy, reverse=True)
    tx = c['x0'] + c['dx'] * np.arange(len(VX))
    ty = c['y0'] + c['dy'] * np.arange(len(HY))
    ax, bx = np.polyfit(VX, tx, 1)
    ay, by = np.polyfit(HY, ty, 1)
    gx = max(abs(np.polyval([ax, bx], VX) - tx))
    gy = max(abs(np.polyval([ay, by], HY) - ty))
    print(f'{name}: {len(VX)} vertical gridlines {tx[0]}..{tx[-1]} C, {len(HY)} horizontal {ty[0]}..{ty[-1]} mW/cm3; '
          f'residual {gx:.3f} C, {gy:.3f} mW/cm3', file=sys.stderr)
    if set(strokes) != set(c['curves']):
        raise ValueError(f'stroke colours {sorted(strokes)} != configured {sorted(c["curves"])}')
    res = []
    for col, (f, B) in c['curves'].items():
        p = bezier(strokes[col])
        T = np.polyval([ax, bx], p[:, 0])
        P = np.polyval([ay, by], p[:, 1])
        keep = np.concatenate([[True], np.diff(T) != 0])  # the joint of two strokes repeats a point
        T, P = T[keep], P[keep]
        if np.any(np.diff(T) < 0):
            raise ValueError(f'curve {col} is not monotonic in T')
        grid = sorted(set([round(T[0], 2)] + [g for g in range(-50, 200, 5) if T[0] <= g <= T[-1]] + [round(T[-1], 2)]))
        for g in grid:
            res.append({"f": f, "B": B, "T": round(float(g), 2), "Pv_kWm3": round(float(np.interp(g, T, P)), 2)})
        chk = ''.join(f' T{t}: {np.interp(t, T, P):.0f}/{v} = {np.interp(t, T, P) / v:.3f};'
                      for t, v in c['table'].get((f, B), {}).items())
        print(f'  {f / 1e3:g} kHz {B * 1e3:g} mT: span {T[0]:.2f}..{T[-1]:.2f} C, {np.interp(25, T, P):.0f} at 25 C, '
              f'min {P.min():.1f} at {T[P.argmin()]:.1f} C; drawn/table:{chk or " no table value"}', file=sys.stderr)
    json.dump(res, sys.stdout, indent=0)


if __name__ == '__main__':
    main()
