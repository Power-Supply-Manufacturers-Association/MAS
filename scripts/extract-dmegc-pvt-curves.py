#!/usr/bin/env python3
"""Read the Pv-T curves of DMEGC DMR55 and DMR90 from their data sheets' vector charts.

    python3 scripts/extract-dmegc-pvt-curves.py DMR55 "DMR55 Material Datasheet.pdf" > dmr55-pvt.json
    python3 scripts/extract-dmegc-pvt-curves.py DMR90 "DMR90 Material Datasheet.pdf" > dmr90-pvt.json

Sources (the DMEGC "Mn-Zn ferrite series" catalogue pages, CorelDRAW PDFs dated 2012-04-27, no
revision mark printed), read 2026-10-28:
  DMR55  https://ferrite.ru/upload/docs/pdf/DMR55%20Material%20Datasheet.pdf
         245,537 B, sha256 b8acfe365eabbffc0f3936ca7b6f75e2ebf4130e188facd41d37e56fa8f9193e
         catalogue pages 27-28; Pv-T chart on PDF page 2 (top right), 5 curves
  DMR90  https://ferrite.ru/upload/docs/pdf/DMR90%20Material%20Datasheet.pdf
         241,057 B, sha256 7d0e8025a254f0d9a08a997366f895bbf08e728b77eb91ee54da410346d00292
         catalogue pages 29-30; Pv-T chart on PDF page 2 (top right), 4 curves

Method: each curve is one or two cubic Bezier strokes (no markers). The axes are calibrated on the
chart's own gridlines (residual printed on stderr), the strokes are evaluated exactly, and each
curve is sampled at its first point, every 5 C, and its last point. Output in kW/m3 (= mW/cm3).

Which stroke is which condition: the charts carry text labels beside the curves, not legend
swatches, so the colour -> condition map below is stated explicitly. It is the only assignment
consistent with (a) the label order beside the curves, (b) the page-1 typical-value table
(the rank of the four 100 C values, DMR55; the 100 kHz/200 mT row, DMR90) and (c) the maker's
Pv-B curves at 25/100 C already in MAS. The checks are printed on stderr.
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
