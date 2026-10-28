# -*- coding: utf-8 -*-
"""End-to-end pipeline: closed BREP -> FGA space -> FBASIC WH -> hydrostatics.

Chains the already-tested commands:
  1. (optional) `foran hull gen ... --brep` -> hull.brep
  2. `foran fga brep`        -> imports the solid as an FGA space (SPC-xxxx)
  3. `foran fbasic wh`       -> SOLID-01 Method=Spaces + Build WH + sections
  4. `foran fbasic hydro`    -> recalculates HYD-CALC-* and saves

The database is copied once (--copy, default) and all steps run on that copy.
Tested on sample (2026-10-27) with the parametric closed hull.

Examples
--------
  foran pipeline hull --db sample.db --copy --brep hull.brep
  foran pipeline hull --db sample.db --copy --lpp 172 --breadth 28.8 \
      --draught 9.83 --depth 14.6 --cb 0.83
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_fbasic as FB  # noqa: E402

CLI = Path(__file__).resolve().parent / "foran_cli.py"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    print("$ foran " + " ".join(str(a) for a in args))
    p = subprocess.run([sys.executable, "-I", str(CLI), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if p.stdout:
        sys.stdout.write(p.stdout)
        sys.stdout.flush()
    if p.stderr:
        sys.stderr.write(p.stderr)
        sys.stderr.flush()
    return p


def _prepare_copy(db: Path, copy: bool) -> Path:
    if not copy:
        return db
    dest_dir = Path.cwd() / "_foran_work" / "projects"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / db.name
    if not dest.exists() or dest.stat().st_mtime < db.stat().st_mtime:
        shutil.copy2(db, dest)
    print(f"database copy: {dest}")
    return dest


def cmd_hull(a) -> int:
    db = Path(a.db).expanduser().resolve()
    if not db.is_file():
        raise SystemExit(f"database not found: {db}")
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    work = Path.cwd() / "_foran_work" / "pipeline" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    work.mkdir(parents=True, exist_ok=True)

    # 1) closed BREP: existing file or generated parametric hull
    if a.brep:
        brep = Path(a.brep).expanduser().resolve()
    else:
        if not (a.lpp and a.breadth and a.draught and a.depth):
            print("give --brep, or --lpp/--breadth/--draught/--depth to generate one",
                  file=sys.stderr)
            return 2
        hull_out = work / "hull"
        args = ["hull", "gen", "--lpp", a.lpp, "--breadth", a.breadth,
                "--draught", a.draught, "--depth", a.depth,
                "--out", hull_out, "--brep"]
        if a.cb:
            args += ["--cb", a.cb]
        if a.stations:
            args += ["--stations", a.stations]
        if a.nz:
            args += ["--nz", a.nz]
        p = _run(args)
        if p.returncode != 0:
            return p.returncode
        brep = hull_out / "hull.brep"
    if not brep.is_file():
        print(f"closed BREP not found: {brep}", file=sys.stderr)
        return 1

    db_run = _prepare_copy(db, a.copy)

    # 2) FGA: import the solid as a space
    p = _run(["fga", "brep", "--db", db_run, "--brep", brep,
              "--node", a.node, "--in-place"])
    if p.returncode != 0:
        return p.returncode
    m = re.search(r"imported\s*:\s*(SPC-\d+)", p.stdout or "")
    if not m:
        print("could not find the imported SPC name in `fga brep` output", file=sys.stderr)
        return 1
    space = m.group(1)

    # 3) FBASIC: watertight hull from that space + default sections
    p = _run(["fbasic", "wh", "--db", db_run, "--space", space, "--build", "--in-place"])
    if p.returncode != 0:
        return p.returncode
    solids, sections = FB._solid_info(db_run)
    print(f"verify   : solids={solids}, hull_sections={sections}")
    if sections <= 0:
        print("pipeline: no watertight hull sections", file=sys.stderr)
        return 1

    # 4) FBASIC: hydrostatics on the rebuilt hull
    p = _run(["fbasic", "hydro", "--db", db_run, "--calc", a.calc, "--in-place"])
    if p.returncode != 0:
        return p.returncode
    rows, row = FB._hydro_info(db_run)
    print(f"pipeline : space={space}, hull_sections={sections}, hyd_rows={rows}")
    if row:
        print("pipeline : 9.83 m displacement={:.3f} t, volume={:.3f} m3".format(
            row[1], row[2]))
    print(f"pipeline : database={db_run}")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hull", help="BREP -> FGA space -> FBASIC WH -> hydrostatics")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--brep", help="existing closed BREP/SOLID (skip `hull gen`)")
    p.add_argument("--lpp", help="generate a hull: Lpp")
    p.add_argument("--breadth", help="generate a hull: breadth")
    p.add_argument("--draught", help="generate a hull: draught")
    p.add_argument("--depth", help="generate a hull: depth")
    p.add_argument("--cb", help="generate a hull: block coefficient (default 0.83)")
    p.add_argument("--stations", help="generate a hull: stations (default 11)")
    p.add_argument("--nz", help="generate a hull: vertical points (default 4)")
    p.add_argument("--node", default="CARGO", help="FGA work-area node (default CARGO)")
    p.add_argument("--calc", default="HYD-CALC-01", help="hydrostatics node")
    p.add_argument("--copy", action="store_true", help="work on a copy (recommended)")
    p.add_argument("--in-place", action="store_true", help="write the original DB")
    p.set_defaults(fn=cmd_hull)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
