# -*- coding: utf-8 -*-
"""Preflight check before a long FORAN run (no GUI is started).

Checks environment, license/launchers, running FORAN processes, optional
project database, free disk space, display/DPI and the work folder.

  foran doctor
  foran doctor --db _foran_work/projects/e365v10.db
  foran doctor --db <db> --json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402
import foran_focus as FOCUS  # noqa: E402

FORAN_EXES = ("fga.exe", "fsurf.exe", "fbasic.exe", "fdm.exe")
MIN_FREE_GB = 2.0


def _processes() -> dict[str, list[int]]:
    """{exe: [pid, ...]} for FORAN modules currently running."""
    out: dict[str, list[int]] = {}
    try:
        table = FOCUS.process_table()
    except Exception:  # noqa: BLE001
        return out
    for pid, (_ppid, name) in table.items():
        low = name.lower()
        if low in FORAN_EXES:
            out.setdefault(low, []).append(pid)
    return out


def _db_report(db: Path) -> dict:
    rep: dict = {"path": str(db), "ok": False, "size": 0,
                 "tables": 0, "quick_check": None, "writable": False,
                 "wal": False}
    if not db.is_file():
        rep["error"] = "not found"
        return rep
    rep["size"] = db.stat().st_size
    rep["writable"] = os.access(db, os.W_OK)
    rep["wal"] = any(db.with_name(db.name + s).exists()
                     for s in ("-wal", "-shm"))
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            rep["quick_check"] = con.execute("pragma quick_check").fetchone()[0]
            rep["tables"] = con.execute(
                "select count(*) from sqlite_master where type='table'").fetchone()[0]
        finally:
            con.close()
        rep["ok"] = rep["quick_check"] == "ok" and rep["tables"] > 0
    except sqlite3.Error as exc:
        rep["error"] = str(exc)
    return rep


def _display() -> dict:
    out = {"width": None, "height": None, "dpi": None}
    if os.name != "nt":
        return out
    try:
        import ctypes
        user32 = ctypes.windll.user32
        out["width"] = int(user32.GetSystemMetrics(0))
        out["height"] = int(user32.GetSystemMetrics(1))
        try:
            out["dpi"] = int(user32.GetDpiForSystem())
        except Exception:  # noqa: BLE001
            hdc = user32.GetDC(0)
            out["dpi"] = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))
            user32.ReleaseDC(0, hdc)
    except Exception:  # noqa: BLE001
        pass
    return out


def run(db: Path | None = None) -> dict:
    checks: list[str] = []
    warns: list[str] = []
    errs: list[str] = []

    env = E.check()
    if env["ok"]:
        checks.append("environment: install/license/launchers present")
    else:
        errs.extend(env["problems"])
    warns.extend(env["warnings"])
    if env.get("config"):
        checks.append(f"config: {env['config']}")
    else:
        warns.append("no config.toml (using built-in defaults)")

    procs = _processes()
    if procs:
        for exe, pids in sorted(procs.items()):
            warns.append(f"{exe} running (pid {', '.join(map(str, pids))}); "
                         f"close it or pass --close-existing")
    else:
        checks.append("no FORAN module is running")

    if db is not None:
        d = _db_report(db)
        if d["ok"]:
            checks.append(f"database: {d['size']:,} B, {d['tables']} tables, "
                          f"quick_check ok")
            if d["wal"]:
                warns.append("database has -wal/-shm sidecars; close FORAN "
                             "before copying it")
            if not d["writable"]:
                warns.append("database is not writable; use --copy")
        else:
            errs.append(f"database: {d.get('error') or d.get('quick_check') or 'bad'}"
                        f" ({d['path']})")

    root = db.parent if db is not None else Path.cwd()
    try:
        free = shutil.disk_usage(root).free / (1024 ** 3)
        if free < MIN_FREE_GB:
            warns.append(f"only {free:.1f} GiB free on {root.anchor or root}")
        else:
            checks.append(f"disk: {free:.1f} GiB free on {root.anchor or root}")
    except Exception as exc:  # noqa: BLE001
        warns.append(f"disk check failed: {exc}")

    disp = _display()
    if disp["width"] and disp["height"]:
        checks.append(f"display: {disp['width']}x{disp['height']} "
                      f"@{disp['dpi']} dpi")
        if (disp["width"], disp["height"]) != (1920, 1080):
            warns.append("GUI coordinates in the skill were measured on "
                         "1920x1080; re-verify clicks on this display")
        if disp["dpi"] and abs(disp["dpi"] - 144) > 2:
            warns.append(f"DPI {disp['dpi']} is not 150% (144 dpi); "
                         f"coordinates may need recalibration")

    work = Path.cwd() / "_foran_work"
    try:
        probe = work if work.exists() else Path.cwd()
        if os.access(probe, os.W_OK):
            checks.append(f"work folder: {probe} writable")
        else:
            errs.append(f"work folder not writable: {probe}")
    except Exception as exc:  # noqa: BLE001
        warns.append(f"work folder check failed: {exc}")

    return {"ok": not errs, "checks": checks, "warnings": warns,
            "errors": errs, "processes": procs, "display": disp}


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="optional FORAN project database to check")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = run(Path(a.db).expanduser().resolve() if a.db else None)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for item in res["checks"]:
            print(f"OK   : {item}")
        for item in res["warnings"]:
            print(f"WARN : {item}")
        for item in res["errors"]:
            print(f"FAIL : {item}", file=sys.stderr)
        print(f"doctor: {'PASS' if res['ok'] else 'FAIL'}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
