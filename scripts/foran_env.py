# -*- coding: utf-8 -*-
"""FORAN V80R3.0 environment discovery and validation.

All machine-specific paths live here. Override with FORAN_SKILL_* env vars
when the installation moves.

Usage:
  python foran_env.py check [--json]
  python foran_env.py paths  [--json]
  python foran_env.py modules [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------- config
# No personal paths are baked in. Everything comes from config.toml or the
# FORAN_SKILL_* environment variables; the conventional install location is
# only a last-resort suggestion.
_CFG_ERROR = ""


def _load_config() -> dict:
    """Read config.toml (FORAN_SKILL_CONFIG, cwd, or next to the skill)."""
    global _CFG_ERROR
    try:
        import tomllib
    except Exception:  # noqa: BLE001
        _CFG_ERROR = "tomllib unavailable (Python < 3.11)"
        return {}
    candidates = []
    env = os.environ.get("FORAN_SKILL_CONFIG")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd() / "config.toml")
    candidates.append(Path(__file__).resolve().parent.parent / "config.toml")
    for p in candidates:
        if p.is_file():
            try:
                with open(p, "rb") as fh:
                    data = tomllib.load(fh)
                data["_path"] = str(p)
                return data
            except Exception as exc:  # noqa: BLE001
                _CFG_ERROR = f"{p}: {exc}"
                return {}
    return {}


_CFG = _load_config()


def _cfg_path(section: str, key: str, env_name: str, default: Path) -> Path:
    v = os.environ.get(env_name)
    if v:
        return Path(v).expanduser().resolve()
    value = _CFG.get(section, {}).get(key)
    if value:
        return Path(str(value)).expanduser().resolve()
    return default


DEFAULT_INSTALL_DIR = Path(r"C:\Program Files\FORAN\V80R3.0")
EMPTY = Path()

INSTALL_DIR = _cfg_path("foran", "install_dir", "FORAN_SKILL_INSTALL_DIR",
                        DEFAULT_INSTALL_DIR)
WRAPPER_DIR = _cfg_path("foran", "wrapper_dir", "FORAN_SKILL_WRAPPER_DIR", EMPTY)
PROJECTS_DIR = _cfg_path("foran", "projects_dir", "FORAN_SKILL_PROJECTS_DIR", EMPTY)
CONF_DIR = _cfg_path("foran", "conf_dir", "FORAN_SKILL_CONF_DIR", EMPTY)
LOGS_DIR = _cfg_path("foran", "logs_dir", "FORAN_SKILL_LOGS_DIR", EMPTY)
WORKDIR = _cfg_path("foran", "workdir", "FORAN_SKILL_WORKDIR", Path.cwd())
LICENSE_FILE = _cfg_path("foran", "license_file", "FORAN_SKILL_LICENSE_FILE", EMPTY)
BIN_DIR = (INSTALL_DIR / "run" / "foranapp" / "windows_amd64" / "bin"
           if INSTALL_DIR != EMPTY else EMPTY)
USER_JOURNAL_DIR = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".foran" / "journal"

# module -> metadata
def _launcher(name: str) -> Path:
    return WRAPPER_DIR / f"{name}.bat" if WRAPPER_DIR != EMPTY else EMPTY


def _official(name: str, ext: str) -> Path:
    return BIN_DIR / f"{name}.{ext}" if BIN_DIR != EMPTY else EMPTY


MODULES = {
    "fbasic": {
        "wrapper": _launcher("fbasic"),
        "official": _official("fbasic", "bat"),
        "exe": _official("fbasic", "exe"),
        "db": True,
        "sqlite": True,
        "title": "FBASIC (performance / hydrostatics / stability)",
    },
    "fga": {
        "wrapper": _launcher("fga"),
        "official": _official("fga", "bat"),
        "exe": _official("fga", "exe"),
        "db": True,
        "sqlite": True,
        "title": "FGA (compartments / general arrangement)",
    },
    "fsurf": {
        "wrapper": _launcher("fsurf"),
        "official": _official("fsurf", "bat"),
        "exe": _official("fsurf", "exe"),
        "db": False,
        "sqlite": False,
        "title": "FSURF (hull form / surfaces)",
    },
    "fdm": {
        "wrapper": _launcher("fdm"),
        "official": _official("fdm", "bat"),
        "exe": _official("fdm", "exe"),
        "db": False,
        "sqlite": False,
        "title": "FDM (document manager)",
    },
}

SENTINEL_TABLES = ("FORAN_VERSION", "DSG_HYD_CALC_DATA", "DSG_GA_TREE")


def module_info(name: str) -> dict:
    key = name.lower()
    if key not in MODULES:
        raise KeyError(f"unknown module {name!r}; choose from {', '.join(MODULES)}")
    info = dict(MODULES[key])
    info["name"] = key
    return info


def _exists(p: Path) -> bool:
    return p.exists()


def _show(p: Path) -> str:
    return "<not configured>" if p == EMPTY else str(p)


def check() -> dict:
    """Return a machine-readable health report."""
    result = {
        "config": _CFG.get("_path"),
        "config_error": _CFG_ERROR,
        "install_dir": _show(INSTALL_DIR),
        "wrapper_dir": _show(WRAPPER_DIR),
        "bin_dir": _show(BIN_DIR),
        "license_file": _show(LICENSE_FILE),
        "conf_dir": _show(CONF_DIR),
        "logs_dir": _show(LOGS_DIR),
        "projects_dir": _show(PROJECTS_DIR),
        "workdir": _show(WORKDIR),
        "ok": True,
        "problems": [],
        "warnings": [],
        "modules": {},
    }

    if _CFG_ERROR:
        result["warnings"].append(f"config.toml could not be read ({_CFG_ERROR})")
    if INSTALL_DIR == EMPTY:
        result["ok"] = False
        result["problems"].append(
            "install_dir not configured: set [foran].install_dir in config.toml "
            "or FORAN_SKILL_INSTALL_DIR")
    elif not _exists(INSTALL_DIR):
        result["ok"] = False
        result["problems"].append(f"missing install_dir: {INSTALL_DIR}")

    for label, p in [("conf_dir", CONF_DIR), ("wrapper_dir", WRAPPER_DIR)]:
        if p != EMPTY and not _exists(p):
            result["warnings"].append(f"missing {label}: {p}")

    if LICENSE_FILE == EMPTY:
        result["warnings"].append(
            "license_file not configured; relying on the ambient LM_LICENSE_FILE")
    elif not _exists(LICENSE_FILE):
        result["warnings"].append(f"license file not found: {LICENSE_FILE}")

    for name, info in MODULES.items():
        entry = {
            "title": info["title"],
            "needs_db": info["db"],
            "wrapper": _show(info["wrapper"]),
            "wrapper_exists": info["wrapper"] != EMPTY and _exists(info["wrapper"]),
            "official": _show(info["official"]),
            "official_exists": info["official"] != EMPTY and _exists(info["official"]),
            "exe_exists": info["exe"] != EMPTY and _exists(info["exe"]),
        }
        if INSTALL_DIR != EMPTY and not (entry["wrapper_exists"] or entry["official_exists"]):
            result["ok"] = False
            result["problems"].append(f"{name}: no launcher found")
        if not entry["exe_exists"] and INSTALL_DIR != EMPTY:
            result["warnings"].append(f"{name}: exe not found at {info['exe']}")
        result["modules"][name] = entry

    result["sqlite3"] = (shutil.which("sqlite3")
                         or (str(BIN_DIR / "sqlite3.exe") if BIN_DIR != EMPTY else ""))
    return result


def human_check(rep: dict) -> str:
    lines = ["FORAN environment", "=" * 60]
    lines.append(f"{'config':14} {rep.get('config') or '<none>'}")
    for k in ("install_dir", "wrapper_dir", "bin_dir", "license_file", "conf_dir", "logs_dir", "projects_dir", "workdir"):
        lines.append(f"{k:14} {rep[k]}")
    lines.append("")
    lines.append(f"status: {'OK' if rep['ok'] else 'PROBLEMS'}")
    for p in rep["problems"]:
        lines.append(f"  [X] {p}")
    for w in rep["warnings"]:
        lines.append(f"  [!] {w}")
    if any("install_dir" in p for p in rep["problems"]):
        lines.append("  fix: set [foran].install_dir in config.toml "
                     "(see config.example.toml)")
    if any("license_file" in w for w in rep["warnings"]):
        lines.append("  hint: set [foran].license_file, or rely on your "
                     "LM_LICENSE_FILE environment variable")
    lines.append("")
    lines.append(f"{'module':8} {'db':4} {'wrapper':8} {'official':9} title")
    for name, m in rep["modules"].items():
        lines.append(
            f"{name:8} {str(m['needs_db']):4} "
            f"{('yes' if m['wrapper_exists'] else 'NO'):8} "
            f"{('yes' if m['official_exists'] else 'NO'):9} {m['title']}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("check", "paths", "modules"):
        sp = sub.add_parser(c)
        sp.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        rep = check()
        print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else human_check(rep))
        return 0 if rep["ok"] else 1

    if a.cmd == "paths":
        rep = {k: _show(v) for k, v in {
            "install_dir": INSTALL_DIR, "wrapper_dir": WRAPPER_DIR, "bin_dir": BIN_DIR,
            "license_file": LICENSE_FILE, "conf_dir": CONF_DIR, "logs_dir": LOGS_DIR,
            "projects_dir": PROJECTS_DIR, "workdir": WORKDIR,
        }.items()}
        print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else "\n".join(f"{k}={v}" for k, v in rep.items()))
        return 0

    if a.cmd == "modules":
        rep = {n: {k: (str(v) if isinstance(v, Path) else v) for k, v in m.items()} for n, m in MODULES.items()}
        print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else "\n".join(
            f"{n}: wrapper={m['wrapper']} db={m['db']}" for n, m in MODULES.items()))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
