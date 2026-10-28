# -*- coding: utf-8 -*-
"""Hydrostatics from a FORAN project DB, without FBASIC's GUI.

FORAN stores the hull solid as station sections in
`DSG_SOLID_HULL_SECTIONS`: one row per X (abscissa), `DATA` is a 12-byte
header followed by 5 big-endian float32 per point; the first two are the
section's (Y, Z) coordinates, the remaining three are sentinels.  Clipping
each section at the waterline and integrating over X reproduces FBASIC's
`DSG_HYD_RESULTS` very closely (sample, T=9.83 m: volume within 0.03 %).

Examples:
  foran hydro calc <sample.db> --draft 9.83
  foran hydro calc <sample.db> --drafts 1,2,4,6,8,9.83 --json
  foran hydro compare <sample.db>            # vs FBASIC rows in DSG_HYD_RESULTS
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402


# ---------------------------------------------------------------- DB access
def _connect_ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect("file:%s?mode=ro" % db.as_posix(), uri=True)


def load_sections(db: Path) -> list[tuple[float, list[tuple[float, float]]]]:
    con = _connect_ro(db)
    try:
        rows = con.execute(
            "select X, DATA from DSG_SOLID_HULL_SECTIONS where DATA is not null "
            "order by X").fetchall()
    finally:
        con.close()
    secs = []
    for x, data in rows:
        if not data or len(data) < 32:
            continue
        n = (len(data) - 12) // 4
        vals = struct.unpack(">%df" % n, data[12:12 + 4 * n])
        pts = [(vals[i], vals[i + 1]) for i in range(0, len(vals), 5)]
        if len(pts) > 2 and math.dist(pts[0], pts[-1]) > 1e-6:
            pts.append(pts[0])
        if len(pts) >= 3:
            secs.append((float(x), pts))
    return secs


def main_particulars(db: Path) -> dict:
    con = _connect_ro(db)
    try:
        row = con.execute(
            "select LENGTH_BETWEEN_PP, DESIGN_BREADTH, DESIGN_DRAUGHT, WATER_DENSITY "
            "from DSG_HYD_CALC_DATA limit 1").fetchone()
    finally:
        con.close()
    if not row:
        return {"lpp": None, "breadth": None, "draught": None, "density": 1.025}
    return {"lpp": row[0], "breadth": row[1], "draught": row[2],
            "density": row[3] or 1.025}


def fbasic_results(db: Path) -> list[dict]:
    con = _connect_ro(db)
    try:
        cols = [r[1] for r in con.execute("pragma table_info(DSG_HYD_RESULTS)")]
        rows = con.execute("select * from DSG_HYD_RESULTS").fetchall()
    finally:
        con.close()
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------- geometry
def clip_below(pts: list[tuple[float, float]], z: float) -> list[tuple[float, float]]:
    """Clip a closed (Y,Z) polygon to Z <= z (Sutherland-Hodgman)."""
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        pin, qin = p[1] <= z, q[1] <= z
        if pin:
            out.append(p)
        if pin != qin:
            t = (z - p[1]) / (q[1] - p[1])
            out.append((p[0] + t * (q[0] - p[0]), z))
    return out


def area_moment_z(pts: list[tuple[float, float]]) -> tuple[float, float]:
    """Polygon area and first moment about the Z=0 axis."""
    a = 0.0
    mz = 0.0
    n = len(pts)
    for i in range(n):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % n]
        c = y0 * z1 - y1 * z0
        a += c
        mz += (z0 + z1) * c
    a *= 0.5
    if abs(a) < 1e-12:
        return 0.0, 0.0
    return abs(a), abs(mz / 6.0)


def waterline_ends(pts: list[tuple[float, float]], z: float) -> tuple[float, float]:
    ys = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        if (p[1] - z) * (q[1] - z) <= 0 and p[1] != q[1]:
            t = (z - p[1]) / (q[1] - p[1])
            ys.append(p[0] + t * (q[0] - p[0]))
    if not ys:
        return 0.0, 0.0
    return min(ys), max(ys)


def girth(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 2:
        return 0.0
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def calc_at_draft(sections, draft: float, lpp: float, breadth: float,
                  density: float) -> dict:
    rows = []
    for x, pts in sections:
        cp = clip_below(pts, draft)
        a, mz = area_moment_z(cp) if len(cp) >= 3 else (0.0, 0.0)
        lo, hi = waterline_ends(pts, draft)
        rows.append((x, a, mz, max(0.0, hi - lo), lo, hi, girth(cp)))

    vol = mx = mz = awp = xwp = 0.0
    it = wetted = 0.0
    for (x0, a0, m0, w0, l0, h0, g0), (x1, a1, m1, w1, l1, h1, g1) in zip(rows, rows[1:]):
        dx = x1 - x0
        vol += 0.5 * (a0 + a1) * dx
        mx += 0.5 * (a0 * x0 + a1 * x1) * dx
        mz += 0.5 * (m0 + m1) * dx
        awp += 0.5 * (w0 + w1) * dx
        xwp += 0.5 * (w0 * x0 + w1 * x1) * dx
        it += 0.5 * ((w0 ** 3) / 12.0 + (w1 ** 3) / 12.0) * dx
        wetted += 0.5 * (g0 + g1) * dx

    if vol <= 0 or awp <= 0:
        raise SystemExit(f"no submerged geometry at draft {draft}")
    lcb = mx / vol
    kb = mz / vol
    lcf = xwp / awp
    il = 0.0
    for (x0, a0, m0, w0, *_rest), (x1, a1, m1, w1, *_rest2) in zip(rows, rows[1:]):
        dx = x1 - x0
        il += 0.5 * (w0 * (x0 - lcf) ** 2 + w1 * (x1 - lcf) ** 2) * dx
    am = max(r[1] for r in rows)
    wl = [r for r in rows if r[3] > 1e-6]
    lwl = (wl[-1][0] - wl[0][0]) if wl else 0.0
    bwl = max((r[3] for r in rows), default=0.0)
    bm_t = it / vol
    bm_l = il / vol
    out = {
        "draft": draft,
        "lpp": lpp,
        "breadth": breadth,
        "density": density,
        "volume": vol,
        "displacement": vol * density,
        "lcb": lcb,
        "lcf": lcf,
        "kb": kb,
        "bm_t": bm_t,
        "km_t": kb + bm_t,
        "bm_l": bm_l,
        "awp": awp,
        "lwl": lwl,
        "bwl": bwl,
        "am": am,
        "cb": vol / (lpp * breadth * draft) if lpp and breadth else None,
        "cp": vol / (am * lpp) if am and lpp else None,
        "cm": am / (breadth * draft) if breadth else None,
        "cwp": awp / (lwl * bwl) if lwl and bwl else None,
        "tpc": density * awp / 100.0,
        "mct": density * il / (100.0 * lpp) if lpp else None,
        "wetted_area": wetted,
    }
    return out


def calc(db: Path, drafts: list[float], density: float | None = None) -> dict:
    mp = main_particulars(db)
    lpp = mp["lpp"] or 0.0
    breadth = mp["breadth"] or 0.0
    rho = density or mp["density"] or 1.025
    sections = load_sections(db)
    if not sections:
        raise SystemExit("no hull sections in DSG_SOLID_HULL_SECTIONS")
    result = {
        "db": str(db),
        "lpp": lpp,
        "breadth": breadth,
        "design_draught": mp["draught"],
        "density": rho,
        "sections": len(sections),
        "xmin": sections[0][0],
        "xmax": sections[-1][0],
        "drafts": {},
    }
    for t in drafts:
        result["drafts"][f"{t:g}"] = calc_at_draft(sections, t, lpp, breadth, rho)
    return result


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.4f}"
    return str(v)


def print_table(res: dict) -> None:
    keys = [
        ("draft", "T (m)"), ("volume", "Volume (m3)"), ("displacement", "Disp (t)"),
        ("cb", "Cb"), ("cp", "Cp"), ("cm", "Cm"), ("cwp", "Cwp"),
        ("lcb", "LCB (m)"), ("lcf", "LCF (m)"), ("kb", "KB (m)"),
        ("bm_t", "BM_T (m)"), ("km_t", "KM_T (m)"), ("tpc", "TPC (t/cm)"),
        ("mct", "MCT (t*m/cm)"), ("awp", "Awp (m2)"), ("wetted_area", "Wetted (m2)"),
    ]
    head = "  ".join(f"{h:>12}" for _, h in keys)
    print(head)
    print("-" * len(head))
    for _k, row in res["drafts"].items():
        print("  ".join(f"{_fmt(row.get(key)):>12}" for key, _ in keys))


# ---------------------------------------------------------------- compare
def compare(db: Path, tol: float = 0.01) -> int:
    ours = calc(db, [])
    ref = [r for r in fbasic_results(db)
           if r.get("AFT_DRAFT") is not None
           and abs((r["AFT_DRAFT"] or 0) - (r["FORE_DRAFT"] or 0)) < 1e-6]
    if not ref:
        print("no even-keel rows in DSG_HYD_RESULTS")
        return 1
    sections = load_sections(db)
    mp = main_particulars(db)
    lpp, b = mp["lpp"] or 0.0, mp["breadth"] or 0.0
    rho = mp["density"] or 1.025
    fields = [
        ("MOULDED_VOLUME", "volume", "Volume"),
        ("DISPLACEMENT", "displacement", "Disp"),
        ("XCB", "lcb", "LCB"),
        ("WATERLINE_AREA", "awp", "Awp"),
        ("XCF", "lcf", "LCF"),
        ("HCB", "kb", "KB"),
        ("BLOCK_COEFF", "cb", "Cb"),
        ("PRISMATIC_COEFF", "cp", "Cp"),
        ("MIDSHIP_COEFF", "cm", "Cm"),
        ("TRANS_METACENT_RAD", "bm_t", "BM_T"),
        ("KM_TRANSVERSAL", "km_t", "KM_T"),
        ("TONS_INMERSION_CM", "tpc", "TPC"),
        ("MOMENT_TRIM_CM", "mct", "MCT"),
        ("WETTED_SRF_AREA", "wetted_area", "Wetted"),
    ]
    print(f"{'T':>6}  {'field':<8} {'ours':>12} {'FBASIC':>12} {'diff%':>8}")
    bad = 0
    for r in sorted(ref, key=lambda r: r["AFT_DRAFT"]):
        t = float(r["AFT_DRAFT"])
        row = calc_at_draft(sections, t, lpp, b, rho)
        for ref_key, our_key, label in fields:
            rv = r.get(ref_key)
            ov = row.get(our_key)
            if rv in (None, 0) or ov is None:
                continue
            diff = (ov - rv) / rv * 100.0
            flag = ""
            if abs(diff) > tol * 100:
                flag = "  <--"
                bad += 1
            print(f"{t:6.2f}  {label:<8} {ov:12.4f} {rv:12.4f} {diff:8.3f}{flag}")
    return 0 if bad == 0 else 2


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("calc", "calc"), ("compare", "compare")):
        p = sub.add_parser(name)
        p.add_argument("db")
        if name == "calc":
            p.add_argument("--draft", type=float)
            p.add_argument("--drafts", help="comma list, e.g. 1,2,4,6,8,9.83")
            p.add_argument("--density", type=float)
            p.add_argument("--json", action="store_true")
        else:
            p.add_argument("--tol", type=float, default=0.01,
                           help="warn above this relative difference (default 0.01 = 1%%)")
    a = ap.parse_args(argv)
    db = Path(a.db).expanduser().resolve()
    if not db.is_file():
        raise SystemExit(f"database not found: {db}")
    if a.cmd == "calc":
        mp = main_particulars(db)
        if a.drafts:
            drafts = [float(v) for v in a.drafts.split(",") if v.strip()]
        elif a.draft is not None:
            drafts = [a.draft]
        else:
            drafts = [mp["draught"]] if mp["draught"] else [9.83]
        res = calc(db, drafts, a.density)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"DB       : {res['db']}")
            print(f"sections : {res['sections']}  x={res['xmin']:.2f}..{res['xmax']:.2f}")
            print(f"Lpp={res['lpp']:.3f}  B={res['breadth']:.3f}  "
                  f"Tdesign={res['design_draught']}  rho={res['density']}")
            print_table(res)
        return 0
    return compare(db, a.tol)


if __name__ == "__main__":
    raise SystemExit(main())
