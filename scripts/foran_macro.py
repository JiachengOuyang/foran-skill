# -*- coding: utf-8 -*-
"""Manage FORAN FCS macro files (Tcl-based) in a working directory.

FORAN does not expose a documented headless macro runner on this install.
The reliable route is the GUI:
  Tools > Macros > Macros recorder   (record a reference session)
  Tools > Macros > Macros editor     (edit / paste the script)
  Tools > Macros > Refresh menu      (reload the menu)
  Tools > Macros > <macro name>      (run)

This helper only creates/lists/shows ASCII macro files; it never runs them.

Examples:
  python foran_macro.py where
  python foran_macro.py list --workdir "D:\\Document"
  python foran_macro.py new load_surface --workdir "D:\\Document" --note "加载型线"
  python foran_macro.py show "D:\\Document\\load_surface.mac"
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402

DEFAULT_PATTERNS = ("*.mac", "*.tcl", "*.fcs")


def _workdir(a) -> Path:
    p = Path(a.workdir).expanduser().resolve() if a.workdir else E.WORKDIR
    if not p.exists():
        raise SystemExit(f"working directory not found: {p}")
    return p


def cmd_where(a) -> int:
    print(f"default FORAN working directory : {E.WORKDIR}")
    print(f"wrapper dir                      : {E.WRAPPER_DIR}")
    print()
    print("Macros are ASCII files looked up in the module's working directory")
    print("(the 'Start in' folder of the shortcut). Use --workdir to point elsewhere.")
    print("Menu path: Tools > Macros > Macros recorder / Macros editor / Refresh menu")
    return 0


def cmd_list(a) -> int:
    wd = _workdir(a)
    files = []
    for pat in (a.pattern.split(",") if a.pattern else DEFAULT_PATTERNS):
        files.extend(wd.glob(pat.strip()))
    files = sorted({p.resolve(): p for p in files if p.is_file()}.values(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"no macro files in {wd} (patterns: {', '.join(DEFAULT_PATTERNS)})")
        return 1
    for p in files:
        st = p.stat()
        print(f"{dt.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}  {st.st_size:7d}  {p.name}")
    print(f"\n{len(files)} file(s) in {wd}")
    return 0


def cmd_new(a) -> int:
    wd = _workdir(a)
    name = a.name
    if not name.lower().endswith((".mac", ".tcl", ".fcs")):
        name += ".mac"
    dest = wd / name
    if dest.exists() and not a.force:
        raise SystemExit(f"refusing to overwrite {dest} (use --force)")
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# FORAN FCS macro: {Path(name).stem}",
        f"# Created: {stamp}",
        f"# Purpose: {a.note or ''}",
        "#",
        "# FORAN macros are Tcl-based ASCII scripts stored in the module working directory.",
        "# Recommended workflow:",
        "#   1) Tools > Macros > Macros recorder  -- record a reference session",
        "#   2) Tools > Macros > Macros editor    -- edit / merge into this file",
        "#   3) Tools > Macros > Refresh menu     -- reload the menu",
        "#   4) Tools > Macros > <name>           -- run",
        "#",
        "# Keep the recorded command lines below; add Tcl comments with '#'.",
        "",
    ]
    dest.write_text("\n".join(lines), encoding="utf-8")
    print(f"created {dest}")
    return 0


def cmd_show(a) -> int:
    p = Path(a.file).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"file not found: {p}")
    print(p.read_text(encoding="utf-8", errors="replace"))
    return 0


def cmd_record_help(a) -> int:
    print("""FORAN macro recording (reliable route)
=====================================
1. Open the target module (fbasic/fga/fsurf/fdm) from the wrapper shortcut.
2. Menu: Tools > Macros > Macros recorder.
3. Give the macro a name; choose an existing or new file in the working directory.
   If the file is not empty, confirm YES to append.
4. Perform the actions you want to automate once, at normal speed.
5. Use the top-right icon in the graphic area to add comments/messages or to stop.
6. Menu: Tools > Macros > Refresh menu.
7. Run it from Tools > Macros > <name>.

To edit manually: Tools > Macros > Macros editor. The files are ASCII/Tcl.
No headless runner is documented for this V80R3.0 install, so do not try to
execute a macro by double-clicking it.""")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("where"); p.set_defaults(fn=cmd_where)
    p = sub.add_parser("list"); p.add_argument("--workdir"); p.add_argument("--pattern", help="comma-separated globs")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("new"); p.add_argument("name"); p.add_argument("--workdir")
    p.add_argument("--note", default=""); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("show"); p.add_argument("file"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("record-help"); p.set_defaults(fn=cmd_record_help)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
