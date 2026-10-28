# -*- coding: utf-8 -*-
"""Parametric hull generator + hydrostatics, with no GUI.

The hull is built from station sections:

    y(x,z) = A * (B/2) * f(u) * g(v),   u = x/Lpp, v = z/T

`f(u)` is 1 in the parallel body and tapers to the ends; `g(v)` is the
vertical section shape.  The exponent of `g` is calibrated so the block
coefficient matches `--cb`.  The sections are written as JSON, a lines-plan
SVG, and (optionally) a closed BREP/STEP solid via gmsh.

Examples:
  foran hull gen --lpp 172 --breadth 28.8 --draught 9.83 --depth 14.6 --cb 0.83 \
    --out _foran_work/hull/demo --brep
  foran hull gen --lpp 100 --breadth 18 --draught 6 --depth 9 --cb 0.70 --stations 31
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_hydro as H  # noqa: E402


def f_long(u: float, qa: float = 0.6, qf: float = 1.2,
           pa: float = 0.2, pf: float = 0.8) -> float:
    if u <= 0.0 or u >= 1.0:
        return 1e-3
    if u < pa:
        return math.sin(math.pi / 2 * u / pa) ** qa
    if u > pf:
        return math.sin(math.pi / 2 * (1 - u) / (1 - pf)) ** qf
    return 1.0


def g_vert(v: float, p: float) -> float:
    return math.sin(math.pi / 2 * max(0.0, min(1.0, v))) ** p


def gen_sections(lpp: float, breadth: float, draught: float, depth: float,
                 p: float, amp: float = 1.0, stations: int = 21,
                 nz: int = 20) -> list[tuple[float, list[tuple[float, float]]]]:
    secs = []
    for i in range(stations):
        u = i / (stations - 1)
        x = u * lpp
        f = max(f_long(u), 1e-3)
        yw = amp * (breadth / 2.0) * f
        # port side keel -> deck, across the deck, starboard deck -> keel
        pts = [(0.0, 0.0)]
        for j in range(1, nz + 1):
            v = j / nz
            pts.append((-yw * g_vert(v, p), v * draught))
        pts.append((-yw, depth))
        pts.append((yw, depth))
        for j in range(nz, 0, -1):
            v = j / nz
            pts.append((yw * g_vert(v, p), v * draught))
        pts.append((0.0, 0.0))
        secs.append((x, pts))
    return secs


def cb_of(p: float, lpp: float, breadth: float, draught: float, depth: float,
          amp: float, stations: int, nz: int) -> float:
    secs = gen_sections(lpp, breadth, draught, depth, p, amp, stations, nz)
    row = H.calc_at_draft(secs, draught, lpp, breadth, 1.025)
    return row["cb"]


def calibrate(target_cb: float, lpp: float, breadth: float, draught: float,
              depth: float, stations: int, nz: int) -> tuple[float, float, float]:
    """Return (p, amp, achieved_cb).  p is the vertical fullness exponent."""
    lo, hi = 0.002, 3.0
    cb_lo = cb_of(lo, lpp, breadth, draught, depth, 1.0, stations, nz)
    cb_hi = cb_of(hi, lpp, breadth, draught, depth, 1.0, stations, nz)
    # cb decreases as p grows; if the target is above cb(lo), widen the hull.
    if target_cb >= cb_lo:
        amp = target_cb / cb_lo
        return lo, amp, cb_of(lo, lpp, breadth, draught, depth, amp, stations, nz)
    if target_cb <= cb_hi:
        amp = target_cb / cb_hi
        return hi, amp, cb_of(hi, lpp, breadth, draught, depth, amp, stations, nz)
    for _ in range(50):
        mid = (lo + hi) / 2
        cb = cb_of(mid, lpp, breadth, draught, depth, 1.0, stations, nz)
        if cb > target_cb:
            lo = mid
        else:
            hi = mid
    p = (lo + hi) / 2
    return p, 1.0, cb_of(p, lpp, breadth, draught, depth, 1.0, stations, nz)


def _svg_lines(secs, lpp: float, breadth: float, draught: float, depth: float,
               path: Path) -> None:
    W, Hh = 1200, 800
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{Hh}" '
           f'viewBox="0 0 {W} {Hh}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g fill="none" stroke="#222" stroke-width="1">']

    # body plan: sections at 10 stations, scale to 260 px high
    bp_x, bp_y, bp_w, bp_h = 40, 40, 520, 330
    zs = [p[1] for _, pts in secs for p in pts]
    ys = [abs(p[0]) for _, pts in secs for p in pts]
    zmax = max(zs) or 1.0
    ymax = max(ys) or 1.0
    sc = min(bp_w / (2 * ymax), bp_h / zmax) * 0.9
    cx = bp_x + bp_w / 2
    base = bp_y + bp_h
    for k, (x, pts) in enumerate(secs):
        if k % 2:
            continue
        coords = " ".join(f"{cx + y * sc:.1f},{base - z * sc:.1f}" for y, z in pts)
        out.append(f'<polyline points="{coords}"/>')

    # profile (side): x vs z
    px, py, pw, ph = 620, 40, 540, 330
    psc = min(pw / lpp, ph / zmax) * 0.9
    px0, pbase = px + 20, py + ph
    for z, col in ((0, "#222"), (draught, "#06c"), (depth, "#222")):
        x1 = px0
        x2 = px0 + lpp * psc
        y = pbase - z * psc
        out.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
                   f'stroke="{col}"/>')

    # waterlines: half-breadth at 4 drafts
    wx, wy, ww, wh = 40, 430, 1120, 300
    wsc = min(ww / lpp, wh / max(ymax, 1e-6)) * 0.9
    wx0 = wx + 20
    wbase = wy + wh / 2

    def width_at(pts, z):
        vals = []
        n = len(pts)
        for i in range(n):
            (y0, z0), (y1, z1) = pts[i], pts[(i + 1) % n]
            if (z0 - z) * (z1 - z) <= 0 and z0 != z1:
                t = (z - z0) / (z1 - z0)
                vals.append(y0 + t * (y1 - y0))
        return (min(vals), max(vals)) if vals else (0.0, 0.0)

    for z, col in ((0.25 * draught, "#888"), (0.5 * draught, "#666"),
                   (0.75 * draught, "#444"), (draught, "#06c")):
        coords = []
        for x, pts in secs:
            lo, hi = width_at(pts, z)
            coords.append(f"{wx0 + x * wsc:.1f},{wbase - hi * wsc:.1f}")
        out.append(f'<polyline points="{" ".join(coords)}" stroke="{col}"/>')

    out.append('</g>')
    out.append(f'<text x="60" y="24" font-size="16">Body plan</text>')
    out.append(f'<text x="640" y="24" font-size="16">Profile (z)</text>')
    out.append(f'<text x="60" y="420" font-size="16">Waterlines (half-breadth)</text>')
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")


def build_brep(secs, path: Path) -> bool:
    try:
        import gmsh
    except Exception as exc:  # noqa: BLE001
        print(f"gmsh not available ({exc}); skipping BREP", file=sys.stderr)
        return False
    gmsh.initialize()
    try:
        gmsh.model.add("hull")
        wires = []
        for x, pts in secs:
            tags = [gmsh.model.occ.addPoint(x, y, z) for y, z in pts[:-1]]
            lines = [gmsh.model.occ.addLine(tags[i], tags[(i + 1) % len(tags)])
                     for i in range(len(tags))]
            wires.append(gmsh.model.occ.addCurveLoop(lines))
        gmsh.model.occ.synchronize()
        gmsh.model.occ.addThruSections(wires, makeSolid=True, makeRuled=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return True


def cmd_gen(a) -> int:
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    p, amp, cb = calibrate(a.cb, a.lpp, a.breadth, a.draught, a.depth,
                           a.stations, a.nz)
    secs = gen_sections(a.lpp, a.breadth, a.draught, a.depth, p, amp,
                        a.stations, a.nz)
    row = H.calc_at_draft(secs, a.draught, a.lpp, a.breadth, a.density)
    (out / "sections.json").write_text(json.dumps(
        {"lpp": a.lpp, "breadth": a.breadth, "draught": a.draught,
         "depth": a.depth, "cb_target": a.cb, "p": p, "amp": amp,
         "sections": [{"x": x, "points": pts} for x, pts in secs]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    _svg_lines(secs, a.lpp, a.breadth, a.draught, a.depth, out / "lines.svg")
    report = {
        "parameters": {"lpp": a.lpp, "breadth": a.breadth, "draught": a.draught,
                       "depth": a.depth, "cb_target": a.cb, "stations": a.stations},
        "calibration": {"p": p, "amp": amp, "cb_achieved": cb},
        "hydro": row,
    }
    (out / "hydro.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    md = [
        "# Parametric hull",
        "",
        f"- Lpp = {a.lpp:.3f} m, B = {a.breadth:.3f} m, T = {a.draught:.3f} m, "
        f"D = {a.depth:.3f} m",
        f"- target Cb = {a.cb:.4f}, achieved Cb = {row['cb']:.4f} "
        f"(p={p:.4f}, amp={amp:.4f})",
        "",
        "| item | value |",
        "|---|---|",
    ]
    for key, label in (("volume", "Volume (m3)"), ("displacement", "Displacement (t)"),
                       ("cb", "Cb"), ("cp", "Cp"), ("cm", "Cm"), ("cwp", "Cwp"),
                       ("lcb", "LCB (m)"), ("lcf", "LCF (m)"), ("kb", "KB (m)"),
                       ("bm_t", "BM_T (m)"), ("km_t", "KM_T (m)"),
                       ("tpc", "TPC (t/cm)"), ("mct", "MCT (t*m/cm)"),
                       ("awp", "Awp (m2)"), ("wetted_area", "Wetted area (m2)")):
        md.append(f"| {label} | {row.get(key):.4f} |")
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"hull     : Lpp={a.lpp:g} B={a.breadth:g} T={a.draught:g} D={a.depth:g}")
    print(f"calib    : p={p:.4f} amp={amp:.4f} Cb={row['cb']:.4f} "
          f"(target {a.cb:.4f})")
    print(f"volume   : {row['volume']:,.3f} m3")
    print(f"disp     : {row['displacement']:,.3f} t")
    print(f"LCB/KB   : {row['lcb']:.3f} / {row['kb']:.3f} m")
    print(f"outputs  : {out / 'sections.json'}")
    print(f"           {out / 'lines.svg'}")
    print(f"           {out / 'hydro.json'} / report.md")
    if a.brep or a.step:
        target = out / ("hull.brep" if a.brep else "hull.step")
        try:
            ok = build_brep(secs, target)
        except Exception as exc:  # noqa: BLE001
            print(f"BREP failed: {exc}", file=sys.stderr)
            return 1
        if ok:
            print(f"solid    : {target} ({target.stat().st_size} bytes)")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gen")
    p.add_argument("--lpp", type=float, required=True)
    p.add_argument("--breadth", type=float, required=True)
    p.add_argument("--draught", type=float, required=True)
    p.add_argument("--depth", type=float, required=True)
    p.add_argument("--cb", type=float, default=0.75)
    p.add_argument("--stations", type=int, default=21)
    p.add_argument("--nz", type=int, default=20)
    p.add_argument("--density", type=float, default=1.025)
    p.add_argument("--out", required=True)
    p.add_argument("--brep", action="store_true", help="write hull.brep (gmsh)")
    p.add_argument("--step", action="store_true", help="write hull.step (gmsh)")
    p.set_defaults(fn=cmd_gen)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
