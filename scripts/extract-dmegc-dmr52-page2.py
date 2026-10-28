#!/usr/bin/env python3
"""Read the page-2 charts of DMEGC DMR52-REV.A: initial permeability vs temperature, the first-quadrant
B-H curves at 25 and 100 C, and amplitude permeability vs flux density at 25 and 100 C.

    python3 scripts/extract-dmegc-dmr52-page2.py fericor-108-dmr52_material_characteristics_sl.pdf > dmr52-p2.json

Source: DMEGC "DMR52 Material Characteristics", DMR52-REV.A, dated 2014-07, as hosted by Fericor:
  https://web.archive.org/web/20230322201548/https://fericor.com/uploads/fericor/public/document/108-dmr52_material_characteristics_sl.pdf
  139,167 B, sha256 df8d5ef6be0e17d3cc42dfaff810e03035f150f2363a8d1de908fcdef7e1899a

Method: each curve is one vector path of straight segments and cubic Beziers (path_points of
extract-dmegc-pvt-curves.py, evaluated exactly). Every axis is linear and is calibrated on the chart's
own gridlines (frame included); the residual is printed on stderr.
- mu_i(T): -50..325 C every 25 C, mu 0..1000 every 250. Sampled at its ends and every 5 C.
- B-H at 25 and at 100 C: H 0..450 A/m every 50, B 0..475 mT every 25. Two paths per chart, both ending
  at the loop tip (400 A/m). The black path starts on H = 0: it is the descending branch, and its start
  is the remanence. The red path starts on B = 0 at H > 0: it is the ascending branch, and its start is
  the coercive force. Each start is interpolated to exactly H = 0 / B = 0.
- mu_a(B): B 0..400 mT every 25, mu_a 0..2000 every 250. Two paths; each is assigned the temperature
  label ("T=25", "T=100") nearest to its last point, and the distances are printed. Sampled every 10 mT.
The incremental-permeability chart (no temperature printed) and mu_i(f) are not read.
"""
import sys, json, importlib.util
from pathlib import Path
import numpy as np
import pymupdf as fitz

_spec = importlib.util.spec_from_file_location('pvt', Path(__file__).with_name('extract-dmegc-pvt-curves.py'))
pvt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pvt)

CHARTS = {  # box, x (first gridline value, step), y (first value, step), {colour: role}
    'muT': dict(box=(60, 120, 290, 300), x=(-50, 25), y=(0, 250), paths={(1.0, 0.0, 0.0): 'mu_i'}),
    'BH25': dict(box=(60, 330, 290, 520), x=(0, 50), y=(0, 25), T=25.0,
                 paths={(0.0, 0.0, 0.0): 'descending', (1.0, 0.0, 0.0): 'ascending'}),
    'BH100': dict(box=(300, 330, 560, 520), x=(0, 50), y=(0, 25), T=100.0,
                  paths={(0.0, 0.0, 0.0): 'descending', (1.0, 0.0, 0.0): 'ascending'}),
    'mua': dict(box=(60, 550, 300, 730), x=(0, 25), y=(0, 250), paths={(0.0, 0.0, 0.0): None, (1.0, 0.0, 0.0): None}),
}


def chart(page, drawings, name, cfg):
    bx0, by0, bx1, by1 = cfg['box']
    vx, hy, paths = set(), set(), {}
    for d in drawings:
        r = d['rect']
        if not (r.x0 >= bx0 and r.x1 <= bx1 and r.y0 >= by0 and r.y1 <= by1):
            continue
        its = d['items']
        if len(its) == 1 and its[0][0] == 'l':
            a, b = its[0][1], its[0][2]
            if abs(a.x - b.x) < 0.01 and abs(a.y - b.y) > 30:
                vx.add(round(a.x, 2))
            elif abs(a.y - b.y) < 0.01 and abs(a.x - b.x) > 30:
                hy.add(round(a.y, 2))
        elif len(its) > 1 and d['color'] and d.get('fill') is None:
            col = tuple(round(v, 2) for v in d['color'])
            if col in paths:
                raise ValueError(f'{name}: two paths with colour {col}')
            paths[col] = its
    if set(paths) != set(cfg['paths']):
        raise ValueError(f'{name}: path colours {sorted(paths)} != configured {sorted(cfg["paths"])}')
    VX, HY = sorted(vx), sorted(hy, reverse=True)
    fx, rx = pvt.calibrate('x', VX, None, ('lin',) + cfg['x'], f'{name} x')
    fy, ry = pvt.calibrate('y', HY, None, ('lin',) + cfg['y'], f'{name} y')
    print(f'{rx}; {ry}', file=sys.stderr)
    out = {}
    for col, its in paths.items():
        p = pvt.path_points(its)
        out[col] = (p, fx(p[:, 0]), fy(p[:, 1]))
    return out


def monotonic(X, Y, name):
    keep = np.concatenate([[True], np.diff(X) != 0])
    X, Y = X[keep], Y[keep]
    if np.any(np.diff(X) < 0):
        raise ValueError(f'{name} is not monotonic')
    return X, Y


def main():
    page = fitz.open(sys.argv[1])[1]
    drawings, words = page.get_drawings(), page.get_text('words')
    res = {}

    (_, X, Y), = chart(page, drawings, 'muT', CHARTS['muT']).values()
    X, Y = monotonic(X, Y, 'mu_i(T)')
    grid = pvt.sample_grid(X, range(-50, 330, 5))
    res['initialPermeabilityVsTemperature'] = [{'T': g, 'mu': round(float(np.interp(g, X, Y)), 1)} for g in grid]
    print(f'mu_i(T): span {X[0]:.2f}..{X[-1]:.2f} C, {np.interp(25, X, Y):.1f} at 25 C, maximum {Y.max():.1f} '
          f'at {X[Y.argmax()]:.1f} C, {Y[-1]:.1f} at the end', file=sys.stderr)

    res['remanence'], res['coerciveForce'] = {}, {}
    for name in ('BH25', 'BH100'):
        cfg = CHARTS[name]
        for col, (_, H, B) in chart(page, drawings, name, cfg).items():
            role = cfg['paths'][col]
            if role == 'descending':  # starts at H ~ 0: B there is Br
                if abs(H[0]) > 0.5:
                    raise ValueError(f'{name} descending branch starts at H = {H[0]:.2f}, not on H = 0')
                Hs, Bs = monotonic(H, B, f'{name} descending')
                res['remanence'][cfg['T']] = round(float(np.interp(0.0, Hs, Bs)), 1)
                print(f'  {name} descending: starts at H {H[0]:.2f}, B {B[0]:.2f}; Br {res["remanence"][cfg["T"]]} mT; '
                      f'tip H {H[-1]:.1f}, B {B[-1]:.1f}', file=sys.stderr)
            else:  # starts at B ~ 0, H > 0: H there is Hc
                if abs(B[0]) > 0.5 or H[0] <= 0:
                    raise ValueError(f'{name} ascending branch starts at H {H[0]:.2f}, B {B[0]:.2f}, not on B = 0')
                Bs, Hs = monotonic(B, H, f'{name} ascending')
                res['coerciveForce'][cfg['T']] = round(float(np.interp(0.0, Bs, Hs)), 1)
                print(f'  {name} ascending: starts at H {H[0]:.2f}, B {B[0]:.2f}; Hc {res["coerciveForce"][cfg["T"]]} A/m; '
                      f'tip H {H[-1]:.1f}, B {B[-1]:.1f}', file=sys.stderr)

    res['amplitudePermeability'] = {}
    labels = [((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, w[4]) for w in words if w[4].startswith('T=')]
    bx0, by0, bx1, by1 = CHARTS['mua']['box']
    labels = [l for l in labels if bx0 <= l[0] <= bx1 and by0 <= l[1] <= by1]
    for col, (p, X, Y) in chart(page, drawings, 'mua', CHARTS['mua']).items():
        ex, ey = p[-1]
        dist, lab = min((abs(lx - ex) + abs(ly - ey), t) for lx, ly, t in labels)
        T = float(lab.replace('T=', '').replace('℃', ''))
        X, Y = monotonic(X, Y, f'mu_a {lab}')
        grid = pvt.sample_grid(X, range(0, 410, 10))
        res['amplitudePermeability'][T] = [{'B_mT': g, 'mu': round(float(np.interp(g, X, Y)), 1)} for g in grid]
        print(f'  mu_a colour {col}: label {lab!r} {dist:.1f} pt from the curve end; span {X[0]:.2f}..{X[-1]:.2f} mT, '
              f'{Y[0]:.0f} at 0, max {Y.max():.0f} at {X[Y.argmax()]:.0f} mT, {np.interp(200, X, Y):.0f} at 200 mT, '
              f'{Y[-1]:.0f} at the end', file=sys.stderr)
    json.dump(res, sys.stdout, indent=0)


if __name__ == '__main__':
    main()
