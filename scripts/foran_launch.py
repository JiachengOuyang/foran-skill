# -*- coding: utf-8 -*-
"""Launch a FORAN V80R3.0 module with the correct per-process environment.

Never launches the .exe directly: the official .bat chain sets FORAN_HOME,
TCL_LIBRARY, MARRUNB, FORANDISK, etc. We call the user's wrapper .bat when
present (it pins the license and local conf), otherwise the official .bat
with the same two variables set.

Examples:
  python foran_launch.py fdm --dry-run
  python foran_launch.py fbasic --project "D:\\...\\sample.db" --copy-project "_foran_work\\projects"
  python foran_launch.py fsurf --workdir "_foran_work\\fsurf"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402


def _is_foran_db(path: Path) -> tuple[bool, str]:
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        if not head.startswith(b"SQLite format 3"):
            return False, "not a SQLite file (bad magic)"
        con = sqlite3.connect("file:%s?mode=ro" % str(path).replace("\\", "/"), uri=True)
        try:
            tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            ok = con.execute("pragma quick_check").fetchone()[0]
        finally:
            con.close()
        missing = [t for t in E.SENTINEL_TABLES if t not in tables]
        if missing:
            return False, "missing FORAN tables: " + ", ".join(missing)
        if ok != "ok":
            return False, f"quick_check: {ok}"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _unique_copy(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{src.stem}_{stamp}{src.suffix}"
    n = 1
    while dest.exists():
        n += 1
        dest = dest_dir / f"{src.stem}_{stamp}_{n}{src.suffix}"
    shutil.copy2(src, dest)
    return dest


def build(args) -> dict:
    info = E.module_info(args.module)
    wrapper = (info["wrapper"] if info["wrapper"] != E.EMPTY
               and info["wrapper"].exists() else info["official"])
    if wrapper == E.EMPTY or not wrapper.exists():
        raise SystemExit(
            f"no launcher for {args.module}: configure [foran].wrapper_dir "
            f"or [foran].install_dir (tried {E._show(info['wrapper'])} / "
            f"{E._show(info['official'])})")

    project = Path(args.project).expanduser().resolve() if args.project else None
    notes = []

    if project is not None:
        if not project.exists():
            raise SystemExit(f"project DB not found: {project}")
        ok, why = _is_foran_db(project)
        if not ok and not args.force:
            raise SystemExit(f"refusing to open {project}: {why}\n(use --force to override)")
        if not info["db"]:
            notes.append(f"{args.module} does not use a project DB; --project ignored")
            project = None
        elif args.copy_project:
            copy_dir = Path(args.copy_project).expanduser().resolve()
            if args.dry_run:
                notes.append(f"dry-run: would copy the DB into {copy_dir}")
            else:
                project = _unique_copy(project, copy_dir)
                notes.append(f"working on a copy: {project}")
    elif info["db"] and args.module in ("fbasic", "fga"):
        notes.append("no --project given: the Database settings dialog will ask for a .db")

    if args.workdir:
        workdir = Path(args.workdir).expanduser().resolve()
        workdir.mkdir(parents=True, exist_ok=True)
    elif project is not None:
        workdir = project.parent
    elif E.WORKDIR.exists():
        workdir = E.WORKDIR
    else:
        workdir = Path.cwd()

    env = dict(os.environ)
    if E.LICENSE_FILE != E.EMPTY:
        env["LM_LICENSE_FILE"] = str(E.LICENSE_FILE)
    if E.CONF_DIR != E.EMPTY:
        env["FORAN_CONF"] = str(E.CONF_DIR)
    # Belt and braces: make the paths available to the child even if a wrapper is bypassed.
    env.setdefault("FORAN_SKILL_HOME", str(E.INSTALL_DIR))

    cmd = ["cmd.exe", "/c", str(wrapper)]
    use_wrapper = (info["wrapper"] != E.EMPTY and info["wrapper"].exists()
                   and str(wrapper) == str(info["wrapper"]))
    # The stock .bat defaults FORANDISK to C:\FORAN, which does not exist on
    # installs under Program Files; pass the real install dir explicitly.
    # A user wrapper already supplies its own install/license/conf arguments.
    if not use_wrapper and E.INSTALL_DIR != E.EMPTY:
        cmd += ["-install_dir", str(E.INSTALL_DIR).rstrip("\\") + "\\",
                "-foran_platform", "x64",
                "-foran_release", "V80R3.0",
                "-foran_lang", "eng"]
        if args.module in ("fbasic", "fga"):
            cmd += ["-sqlite"]
    if project is not None:
        # FORAN's own scripts forward unknown args to the exe; fbasic/fga accept -fnam.
        # Keep this opt-in because the exact switch is version-specific.
        if args.pass_fnam:
            cmd += ["-fnam", str(project)]
    cmd += list(args.extra or [])

    return {
        "module": args.module,
        "launcher": str(wrapper),
        "official": str(info["official"]),
        "exe": str(info["exe"]),
        "project": str(project) if project else None,
        "workdir": str(workdir),
        "env": {k: v for k, v in {
            "LM_LICENSE_FILE": env.get("LM_LICENSE_FILE"),
            "FORAN_CONF": env.get("FORAN_CONF"),
        }.items() if v},
        "command": cmd,
        "notes": notes,
    }


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module", choices=sorted(E.MODULES))
    ap.add_argument("--project", help="FORAN project .db (fbasic/fga)")
    ap.add_argument("--copy-project", metavar="DIR", help="copy the DB into DIR and launch the copy")
    ap.add_argument("--backup-first", action="store_true", help="copy the DB to ./_foran_work/backups and launch that copy")
    ap.add_argument("--workdir", help="working directory for the module (macros/relative files)")
    ap.add_argument("--pass-fnam", action="store_true", help="append -fnam <db> to the launcher (version-dependent)")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, help="extra arguments forwarded to the launcher")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--wait", action="store_true", help="wait for the module to exit (default: detach)")
    ap.add_argument("--force", action="store_true", help="open even if DB validation fails")
    args = ap.parse_args(argv)
    for extra in (args.extra or []):
        if any(c in extra for c in "&|<>^" + chr(13) + chr(10)):
            raise SystemExit(
                f"refusing --extra argument with shell metacharacters: {extra!r}")

    if args.backup_first and args.project and not args.copy_project:
        src = Path(args.project).expanduser().resolve()
        dest = Path.cwd() / "_foran_work" / "backups"
        args.copy_project = str(dest)
        if not args.json:
            print(f"[backup] {src} -> {dest}")

    plan = build(args)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(f"module   : {plan['module']}")
        print(f"launcher : {plan['launcher']}")
        print(f"project  : {plan['project']}")
        print(f"workdir  : {plan['workdir']}")
        print(f"license  : {plan['env'].get('LM_LICENSE_FILE', '<not configured>')}")
        print(f"conf     : {plan['env'].get('FORAN_CONF', '<not configured>')}")
        for n in plan["notes"]:
            print(f"note     : {n}")

    if args.dry_run:
        return 0

    # Redirect stdio: the GUI inherits the parent's pipe and would keep it
    # open, so `foran launch ... | tail` hangs until FORAN exits.
    log_dir = Path.cwd() / "_foran_work" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{args.module}_{dt.datetime.now():%Y%m%d-%H%M%S}.log"
    # cmd.exe /c with a list mangles quoted paths containing spaces; build the
    # command line as a string instead.
    cmd_obj = plan["command"]
    shell = False
    if (isinstance(cmd_obj, list) and len(cmd_obj) >= 3
            and str(cmd_obj[0]).lower().endswith("cmd.exe")):
        cmd_obj = subprocess.list2cmdline(cmd_obj[2:])
        shell = True
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            cmd_obj,
            shell=shell,
            cwd=plan["workdir"],
            env={**os.environ, **plan["env"]},
            stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    if not args.json:
        print(f"log      : {log}")
    if args.wait:
        rc = proc.wait()
        if not args.json:
            print(f"exited with {rc}")
        return rc
    if not args.json:
        print(f"launched pid={proc.pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
