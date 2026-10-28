# -*- coding: utf-8 -*-
"""Non-GUI health check for the FORAN skill.

Verifies the environment, GUI dependencies, script compilation, templates and
(optionally) a project database.  Nothing is launched and nothing is written
outside the skill directory.

  python foran_selftest.py
  python foran_selftest.py --db "D:\\...\\sample.db"
  python foran_selftest.py --gui
  python foran_selftest.py --fbasic "D:\\...\\sample.db"
  python foran_selftest.py --db sample.db --json
"""
from __future__ import annotations

import argparse
import json
import py_compile
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
TEMPLATES_DIR = SKILL_DIR / "templates"
EVALS = SKILL_DIR / "evals" / "evals.json"
KEY_TABLES = ("DSG_SPC_TREE", "DSG_LSW_PROJECT", "DSG_LOAD_COND",
              "DSG_CALC_TREE", "DSG_SOLID_HULL_SECTIONS")


def _result(name: str, ok: bool, detail: str = "", warn: bool = False) -> dict:
    return {"name": name, "ok": ok, "warn": warn, "detail": detail}


def check_env() -> dict:
    rep = E.check()
    detail = "ok" if rep["ok"] else "; ".join(rep["problems"])
    return _result("environment", rep["ok"], detail)


def check_display() -> dict:
    """Report the screen geometry the GUI coordinates were measured against."""
    try:
        try:
            # pyautogui sets per-monitor DPI awareness on import, so the
            # metrics below are physical pixels (not the 150%-scaled logical
            # size a DPI-unaware process would report).
            import pyautogui
            pyautogui.size()
        except Exception:  # noqa: BLE001
            pass
        import ctypes
        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        try:
            dpi = int(user32.GetDpiForSystem())
        except Exception:  # noqa: BLE001
            hdc = user32.GetDC(0)
            dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))
            user32.ReleaseDC(0, hdc)
        scale = round(dpi / 96 * 100)
    except Exception as exc:  # noqa: BLE001
        return _result("display", False, f"cannot query: {exc}", warn=True)
    detail = f"{width}x{height} @{scale}%"
    if (width, height) == (1920, 1080):
        return _result("display", True, detail)
    return _result("display", True,
                   detail + " (coordinates were measured at 1920x1080; "
                            "GUI flows may need re-measuring)", warn=True)


def check_gui_smoke() -> dict:
    """Launch FDM, verify its main window, and close it (no project needed)."""
    try:
        import foran_fdm as FD
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        return _result("gui-smoke", False, f"import failed: {exc}")
    if [w for w in G.windows() if w.get("process", "").lower() == "fdm.exe"]:
        return _result("gui-smoke", False, "FDM is already running; close it first")
    workdir = Path.cwd() / "_foran_work" / "selftest"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        FD._launch_fdm(workdir)
        win = FD._wait_window("FORAN Document Manager", 60)
        if win is None:
            return _result("gui-smoke", False, "FDM main window did not appear")
        title = win.get("title", "")
        closed = FD._close_fdm(win, timeout=20)
        if not closed:
            return _result("gui-smoke", False, "FDM did not close cleanly")
        return _result("gui-smoke", True, f"launched and closed: {title}")
    except Exception as exc:  # noqa: BLE001
        try:
            import foran_fdm as FD2
            for w in G.windows():
                if w.get("process", "").lower() == "fdm.exe":
                    FD2._close_fdm(w)
        except Exception:  # noqa: BLE001
            pass
        return _result("gui-smoke", False, str(exc))
    finally:
        try:
            import foran_fdm as FD3
            FD3._restore_terminal()
        except Exception:  # noqa: BLE001
            pass


def check_python() -> dict:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return _result("python", ok, f"{v.major}.{v.minor}.{v.micro}")


def check_gui_deps() -> dict:
    missing = []
    versions = []
    for mod in ("pywinauto", "pyautogui", "PIL"):
        try:
            m = __import__(mod)
            versions.append(f"{mod}={getattr(m, '__version__', '?')}")
        except Exception:  # noqa: BLE001
            missing.append(mod)
    if missing:
        return _result("gui-deps", False, "missing " + ", ".join(missing))
    return _result("gui-deps", True, ", ".join(versions))


def check_cv2() -> dict:
    try:
        import cv2
        return _result("opencv", True, cv2.__version__)
    except Exception:  # noqa: BLE001
        return _result("opencv", False,
                       "not installed (vision template fallback disabled)", warn=True)


def check_compile() -> dict:
    bad = []
    for p in sorted(SCRIPTS_DIR.glob("*.py")):
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as exc:
            bad.append(f"{p.name}: {exc.msg}")
    if bad:
        return _result("compile", False, "; ".join(bad))
    n = len(list(SCRIPTS_DIR.glob("*.py")))
    return _result("compile", True, f"{n} scripts")


def check_templates() -> dict:
    # Only evals.json is required.
    need = [EVALS]
    missing = [p.name for p in need if not p.is_file()]
    if missing:
        return _result("templates", False, "missing " + ", ".join(missing))
    try:
        json.loads(EVALS.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _result("templates", False, f"evals.json: {exc}")
    return _result("templates", True, "evals.json valid")


def check_launchers() -> dict:
    need = [SCRIPTS_DIR / "foran", SCRIPTS_DIR / "foran.cmd"]
    missing = [p.name for p in need if not p.is_file()]
    if missing:
        return _result("launchers", False, "missing " + ", ".join(missing))
    return _result("launchers", True, "foran, foran.cmd")


def check_db(path: Path) -> dict:
    if not path.is_file():
        return _result("database", False, f"not found: {path}")
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return _result("database", False, str(exc))
    try:
        quick = con.execute("pragma quick_check").fetchone()
        if not quick or quick[0] != "ok":
            return _result("database", False, f"quick_check: {quick}")
        have = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}
        missing = [t for t in KEY_TABLES if t not in have]
        if missing:
            return _result("database", False, "missing tables: " + ", ".join(missing))
        counts = {}
        for t in ("DSG_SPC_TREE", "DSG_LSW_PROJECT", "DSG_LOAD_COND",
                  "DSG_CALC_TREE"):
            counts[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
        detail = ", ".join(f"{k.replace('DSG_', '')}={v}" for k, v in counts.items())
        return _result("database", True, f"{path.name} ({detail})")
    except sqlite3.Error as exc:
        return _result("database", False, str(exc))
    finally:
        con.close()


def check_fsurf_smoke() -> dict:
    """Launch FSURF (no database), verify its main window, and close it."""
    try:
        import foran_fsf as FS
        import foran_draw as D
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        return _result("fsurf-smoke", False, f"import failed: {exc}")
    if [w for w in G.windows() if w.get("process", "").lower() == "fsurf.exe"]:
        return _result("fsurf-smoke", False,
                       "FSURF is already running; close it first", warn=True)
    workdir = Path.cwd() / "_foran_work" / "selftest" / "fsurf"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        FS._launch_fsurf(workdir)
        win = FS._wait_main(40)
        if win is None:
            return _result("fsurf-smoke", False, "FSURF main window did not appear")
        title = win.get("title", "")
        if not title.startswith("fsurf -"):
            return _result("fsurf-smoke", False,
                           f"unexpected main window: {title!r}")
        return _result("fsurf-smoke", True, f"launched: {title}")
    except Exception as exc:  # noqa: BLE001
        return _result("fsurf-smoke", False, str(exc))
    finally:
        try:
            D.close_fsurf()
        except Exception:  # noqa: BLE001
            pass
        _restore_terminal()


def _restore_terminal() -> None:
    try:
        import foran_focus as FF
        term = FF.find_terminal()
        if term:
            FF.focus(term["hwnd"])
    except Exception:  # noqa: BLE001
        pass


def check_fbasic_smoke(db_path: Path) -> dict:
    """Copy the DB, launch FBASIC, select the database, then close it."""
    try:
        import shutil
        from types import SimpleNamespace
        import foran_fbasic as FB
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        return _result("fbasic-smoke", False, f"import failed: {exc}")
    if [w for w in G.windows() if w.get("process", "").lower() == "fbasic.exe"]:
        return _result("fbasic-smoke", False,
                       "FBASIC is already running; close it first", warn=True)
    work = Path.cwd() / "_foran_work" / "selftest"
    work.mkdir(parents=True, exist_ok=True)
    local = work / db_path.name
    try:
        shutil.copy2(db_path, local)
    except Exception as exc:  # noqa: BLE001
        return _result("fbasic-smoke", False, f"copy failed: {exc}")
    FB.G = G
    a = SimpleNamespace(db=str(local), copy=False, in_place=True,
                        close_existing=False, shadow=None)
    win = None
    try:
        db, win, _run_dir = FB._launch_calc(a, G, "selftest")
        if db is None or win is None:
            return _result("fbasic-smoke", False,
                           "launch or database dialog failed")
        title = win.get("title", "")
        if not title.startswith("fbasic -"):
            return _result("fbasic-smoke", False,
                           f"unexpected main window: {title!r}")
        # Go one step past the DB dialog: the calculation tree must render.
        hwnd = win["hwnd"]
        FB._ensure_tree(G, hwnd)
        nav = FB._wait_tree(G, hwnd, lambda t: "Naval Architecture" in t, 3.0)
        if nav is None and FB._click_tab(hwnd, "Calculations"):
            nav = FB._wait_tree(G, hwnd, lambda t: "Naval Architecture" in t, 5.0)
        if nav is None:
            return _result("fbasic-smoke", False,
                           "main window opened but the Calculations tree is not visible")
        return _result("fbasic-smoke", True,
                       f"{title}; Calculations tree visible (db {Path(db).name})")
    except Exception as exc:  # noqa: BLE001
        return _result("fbasic-smoke", False, str(exc))
    finally:
        try:
            if win is not None:
                FB._exit_app(win)
        except Exception:  # noqa: BLE001
            pass
        _restore_terminal()


def run(db: Path | None, gui: bool = False,
        fbasic_db: Path | None = None) -> tuple[list[dict], bool]:
    checks = [check_python(), check_env(), check_display(), check_gui_deps(),
              check_cv2(), check_compile(), check_templates(), check_launchers()]
    if gui:
        checks.append(check_gui_smoke())
        checks.append(check_fsurf_smoke())
    if fbasic_db is not None:
        if db is None:
            checks.append(check_db(fbasic_db))
        checks.append(check_fbasic_smoke(fbasic_db))
    if db is not None:
        checks.append(check_db(db))
    hard_fail = any(not c["ok"] and not c["warn"] for c in checks)
    return checks, not hard_fail


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="also check this project database (read-only)")
    ap.add_argument("--gui", action="store_true",
                    help="also launch and close FDM and FSURF (no project needed)")
    ap.add_argument("--fbasic", metavar="DB",
                    help="also open a copy of DB in FBASIC and close it")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

    db = Path(a.db).expanduser().resolve() if a.db else None
    fdb = Path(a.fbasic).expanduser().resolve() if a.fbasic else None
    checks, ok = run(db, gui=a.gui, fbasic_db=fdb)
    if a.json:
        print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    for c in checks:
        tag = "OK  " if c["ok"] else ("WARN" if c["warn"] else "FAIL")
        print(f"[{tag}] {c['name']:<11s} {c['detail']}")
    passed = sum(1 for c in checks if c["ok"])
    print(f"\nselftest: {passed}/{len(checks)} passed"
          + ("" if ok else " — fix the FAIL items above"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
