# -*- coding: utf-8 -*-
"""Read-only inspection of FORAN project databases (SQLite).

The important safety rule: every subcommand except `copy` opens the DB with
mode=ro + query_only, so a typo cannot modify the teacher's/project model.

Examples:
  python foran_db.py check  "D:\\path\\sample.db"
  python foran_db.py tables "D:\\path\\sample.db" --filter HYD --counts
  python foran_db.py schema "D:\\path\\sample.db" DSG_HYD_RESULTS
  python foran_db.py query  "D:\\path\\sample.db" -s "select * from FORAN_VERSION"
  python foran_db.py hydro  "D:\\path\\sample.db"
  python foran_db.py search "D:\\path\\sample.db" tank
  python foran_db.py copy   "D:\\path\\sample.db" --out-dir "_foran_work\\projects"
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import shutil
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402

READ_PREFIXES = ("select", "with", "pragma", "explain")


def connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"DB not found: {path}")
    uri = "file:%s?mode=ro" % str(path.resolve()).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    con.execute("pragma query_only=on")
    con.row_factory = sqlite3.Row
    return con


def _rows(con: sqlite3.Connection, sql: str, params=()):
    cur = con.execute(sql, params)
    headers = [d[0] for d in cur.description] if cur.description else []
    return headers, [dict(r) for r in cur.fetchall()]


def _fmt_table(headers, rows, max_width=60) -> str:
    if not headers:
        return "(no rows)"
    cells = [[("" if r[h] is None else str(r[h]))[:max_width] for h in headers] for r in rows]
    widths = [min(max_width, max(len(h), *(len(c[i]) for c in cells)) if cells else len(h))
              for i, h in enumerate(headers)]
    out = ["  ".join(h[:widths[i]].ljust(widths[i]) for i, h in enumerate(headers)),
           "  ".join("-" * w for w in widths)]
    for c in cells:
        out.append("  ".join(v.ljust(widths[i]) for i, v in enumerate(c)))
    return "\n".join(out)


def _emit(headers, rows, fmt="table", out=None, max_width=60):
    if fmt == "json":
        text = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
    elif fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
        text = buf.getvalue().rstrip()
    else:
        text = _fmt_table(headers, rows, max_width)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


# ---------------------------------------------------------------- commands
def cmd_check(a) -> int:
    p = Path(a.db).expanduser().resolve()
    rep = {"db": str(p), "exists": p.exists(), "ok": False, "problems": []}
    if not p.exists():
        print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else f"missing: {p}")
        return 2
    rep.update(size=p.stat().st_size, mtime=dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"))
    try:
        with open(p, "rb") as f:
            magic = f.read(16)
        if not magic.startswith(b"SQLite format 3"):
            rep["problems"].append("not a SQLite file (bad magic)")
            raise sqlite3.DatabaseError("bad magic")
        con = connect_ro(p)
        try:
            qc = con.execute("pragma quick_check").fetchone()[0]
            rep["quick_check"] = qc
            names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            rep["tables"] = len(names)
            rep["missing_sentinel_tables"] = [t for t in E.SENTINEL_TABLES if t not in names]
            if "FORAN_VERSION" in names:
                row = con.execute("select * from FORAN_VERSION limit 1").fetchone()
                rep["foran_version"] = dict(row)
            if qc == "ok" and not rep["missing_sentinel_tables"]:
                rep["ok"] = True
            if qc != "ok":
                rep["problems"].append("quick_check: " + qc)
            if rep["missing_sentinel_tables"]:
                rep["problems"].append("missing FORAN tables")
        finally:
            con.close()
    except (sqlite3.DatabaseError, OSError) as exc:
        if not rep["problems"]:
            rep["problems"].append(str(exc))
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"DB       : {rep['db']}")
        print(f"size     : {rep['size']:,} bytes")
        print(f"version  : {rep.get('foran_version', {})}")
        print(f"tables   : {rep.get('tables', 0)}")
        print(f"quick    : {rep.get('quick_check', 'n/a')}")
        print(f"status   : {'OK' if rep['ok'] else 'PROBLEM: ' + '; '.join(rep['problems'])}")
    return 0 if rep["ok"] else 1


def cmd_tables(a) -> int:
    con = connect_ro(Path(a.db))
    names = [r[0] for r in con.execute(
        "select name from sqlite_master where type in ('table','view') order by name")]
    if a.filter:
        k = a.filter.lower()
        names = [n for n in names if k in n.lower()]
    rows = []
    for n in names:
        row = {"name": n}
        if a.counts:
            try:
                row["rows"] = con.execute(f'select count(*) from "{n}"').fetchone()[0]
            except Exception:  # noqa: BLE001
                row["rows"] = None
        rows.append(row)
    con.close()
    _emit(["name"] + (["rows"] if a.counts else []), rows, a.format, a.out)
    return 0


def cmd_schema(a) -> int:
    if '"' in a.table or chr(10) in a.table or chr(13) in a.table:
        raise SystemExit(f"invalid table name: {a.table!r}")
    con = connect_ro(Path(a.db))
    rows = []
    for r in con.execute(f'pragma table_info("{a.table}")'):
        rows.append({"cid": r[0], "name": r[1], "type": r[2], "notnull": r[3], "default": r[4], "pk": r[5]})
    if not rows:
        con.close()
        raise SystemExit(f"table not found: {a.table}")
    objs = con.execute("select sql from sqlite_master where name=?", (a.table,)).fetchone()
    con.close()
    if a.format == "json":
        print(json.dumps({"table": a.table, "ddl": objs[0] if objs else None, "columns": rows},
                         ensure_ascii=False, indent=2))
    else:
        if objs and objs[0]:
            print(objs[0].strip())
            print()
        _emit(["cid", "name", "type", "notnull", "default", "pk"], rows, a.format, a.out)
    return 0


def cmd_search(a) -> int:
    con = connect_ro(Path(a.db))
    k = a.keyword.lower()
    out = {"tables": [], "columns": []}
    for (name,) in con.execute("select name from sqlite_master where type in ('table','view') order by name"):
        if k in name.lower():
            out["tables"].append(name)
        try:
            for r in con.execute(f'pragma table_info("{name}")'):
                if k in r[1].lower():
                    out["columns"].append({"table": name, "column": r[1], "type": r[2]})
        except Exception:  # noqa: BLE001
            pass
    con.close()
    if a.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"tables matching {a.keyword!r}: {len(out['tables'])}")
        for n in out["tables"]:
            print("  " + n)
        print(f"columns matching {a.keyword!r}: {len(out['columns'])}")
        for c in out["columns"]:
            print(f"  {c['table']}.{c['column']}  ({c['type']})")
    return 0


def _single_statement(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        raise SystemExit("empty SQL")
    if not sql.lower().startswith(READ_PREFIXES):
        raise SystemExit("only read-only statements are allowed (SELECT/WITH/PRAGMA/EXPLAIN)")
    # crude multi-statement guard: a semicolon may only be the final non-space char
    body = sql.rstrip()
    if body.endswith(";"):
        body = body[:-1]
    if ";" in body:
        raise SystemExit("multiple statements are not allowed")
    return sql


def cmd_query(a) -> int:
    sql = _single_statement(a.sql)
    low = sql.lower()
    for bad in ("attach", "detach", "pragma", "load_extension",
                "readfile", "writefile"):
        if re.search(rf"{re.escape(bad)}", low):
            raise SystemExit(f"refusing SQL containing {bad!r} in query mode")
    con = connect_ro(Path(a.db))
    try:
        headers, rows = _rows(con, sql)
    except sqlite3.Error as exc:
        con.close()
        raise SystemExit(f"SQL error: {exc}")
    total = len(rows)
    limit = a.limit if a.limit and a.limit > 0 else None
    if limit and total > limit:
        rows = rows[:limit]
        print(f"[{total} rows, showing first {limit}]", file=sys.stderr)
    con.close()
    _emit(headers, rows, a.format, a.out, a.max_width)
    return 0


def cmd_hydro(a) -> int:
    con = connect_ro(Path(a.db))
    calcs = [dict(r) for r in con.execute("select * from DSG_HYD_CALC_DATA order by OID limit 1")]
    if not calcs:
        con.close()
        raise SystemExit("DSG_HYD_CALC_DATA is empty")
    c = calcs[0]
    oid = c["OID"]
    T = c.get("DESIGN_DRAUGHT")
    rows = []
    if T is not None:
        rows = [dict(r) for r in con.execute(
            "select * from DSG_HYD_RESULTS where HYD_DATA_OID=? and abs(AFT_DRAFT-?)<0.01 "
            "order by case HYD_RESULT_TYPE when 1 then 0 else 1 end, OID limit 1", (oid, T))]
    if not rows:
        rows = [dict(r) for r in con.execute(
            "select * from DSG_HYD_RESULTS where HYD_DATA_OID=? order by OID limit 1", (oid,))]
    con.close()
    if not rows:
        raise SystemExit("DSG_HYD_RESULTS has no row for the design draught")
    r = rows[0]

    def g(k):
        return r.get(k)

    Lpp, B = c.get("LENGTH_BETWEEN_PP"), c.get("DESIGN_BREADTH")
    T_used = g("AFT_DRAFT") or T
    vol = g("MOULDED_VOLUME")
    computed = {}
    if Lpp and B and T_used and vol:
        cb = vol / (Lpp * B * T_used)
        computed["Cb_Lpp"] = cb
        if g("MIDSHIP_COEFF"):
            computed["Cp_Lpp"] = cb / g("MIDSHIP_COEFF")
    lwl = g("LENGTH_AT_WPLANE")
    if lwl and B and T_used and vol:
        computed["Cb_Lwl"] = vol / (lwl * B * T_used)
    if vol and c.get("WATER_DENSITY"):
        computed["displacement_from_volume"] = vol * c["WATER_DENSITY"]

    out = {"calc": c, "result": r, "computed": computed,
           "checks": {
               "stored_Cb_Lpp_agrees": (abs(computed.get("Cb_Lpp", -1) - (g("BLOCK_COEFF") or -2)) < 1e-4),
               "stored_Cp_agrees": (abs(computed.get("Cp_Lpp", -1) - (g("PRISMATIC_COEFF") or -2)) < 1e-3),
           }}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print("FORAN hydrostatics @ design draught")
        print("=" * 52)
        print(f"Lpp={Lpp}  B={B}  T={T}  rho={c.get('WATER_DENSITY')}")
        print(f"Lwl={lwl}  displacement={g('DISPLACEMENT')}  volume={vol}")
        print(f"stored Cb={g('BLOCK_COEFF')}  Cp={g('PRISMATIC_COEFF')}  Cm={g('MIDSHIP_COEFF')}  Cwp={g('WATERLINE_COEFF')}")
        print(f"XCB={g('XCB')}  KMt={g('KM_TRANSVERSAL')}  wetted={g('WETTED_SRF_AREA')}")
        print("computed: " + ", ".join(f"{k}={v:.6f}" if isinstance(v, float) else f"{k}={v}"
                                      for k, v in computed.items()))
        print(f"checks  : {out['checks']}")
    return 0


def cmd_copy(a) -> int:
    src = Path(a.db).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"DB not found: {src}")
    out_dir = Path(a.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out_dir / f"{src.stem}_{stamp}{src.suffix}"
    n = 1
    while dest.exists():
        n += 1
        dest = out_dir / f"{src.stem}_{stamp}_{n}{src.suffix}"
    shutil.copy2(src, dest)
    con = connect_ro(dest)
    try:
        qc = con.execute("pragma quick_check").fetchone()[0]
    finally:
        con.close()
    print(f"copied: {src}\n     -> {dest}\nquick_check: {qc}")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, out=True):
        p.add_argument("--json", action="store_true", help="JSON output (where applicable)")
        if out:
            p.add_argument("--format", choices=("table", "json", "csv"), default="table")
            p.add_argument("--out", help="write output to this file")

    p = sub.add_parser("check"); p.add_argument("db"); common(p, out=False); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("tables"); p.add_argument("db"); p.add_argument("--filter")
    p.add_argument("--counts", action="store_true"); common(p); p.set_defaults(fn=cmd_tables)
    p = sub.add_parser("schema"); p.add_argument("db"); p.add_argument("table"); common(p); p.set_defaults(fn=cmd_schema)
    p = sub.add_parser("search"); p.add_argument("db"); p.add_argument("keyword"); common(p, out=False); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("query"); p.add_argument("db"); p.add_argument("-s", "--sql", required=True)
    p.add_argument("--limit", type=int, default=200); p.add_argument("--max-width", type=int, default=60)
    common(p); p.set_defaults(fn=cmd_query)
    p = sub.add_parser("hydro"); p.add_argument("db"); common(p, out=False); p.set_defaults(fn=cmd_hydro)
    p = sub.add_parser("copy"); p.add_argument("db"); p.add_argument("--out-dir", required=True); p.set_defaults(fn=cmd_copy)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
