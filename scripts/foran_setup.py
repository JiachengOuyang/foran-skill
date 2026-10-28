# -*- coding: utf-8 -*-
"""Configure the FORAN skill for this machine.

Examples:
  foran setup                 # create config.toml, or review an existing one
  foran setup --check         # report only; never writes
  foran setup --reset --yes --install-dir "C:/Program Files/FORAN/V80R3.0"

The machine-specific values live in config.toml (or FORAN_SKILL_* env vars).
This command only writes that file; it does not install FORAN or a license.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("install_dir", "wrapper_dir", "license_file", "projects_dir",
          "conf_dir", "logs_dir", "workdir")
FLAGS = {
    "install_dir": "install_dir",
    "wrapper_dir": "wrapper_dir",
    "license_file": "license_file",
    "projects_dir": "projects_dir",
    "conf_dir": "conf_dir",
    "logs_dir": "logs_dir",
    "workdir": "workdir",
}


def config_path() -> Path:
    env = os.environ.get("FORAN_SKILL_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd() / "config.toml"
    if cwd.is_file():
        return cwd
    return SKILL_ROOT / "config.toml"


def load_toml(path: Path) -> dict:
    try:
        import tomllib
    except Exception:  # noqa: BLE001
        return {}
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return {}


def _current(value) -> str:
    if value is None:
        return ""
    s = str(value)
    return "" if s in ("", ".") else s


def detect(path: Path) -> dict:
    cfg = load_toml(path)
    section = cfg.get("foran", {})

    def pick(key: str, env_name: str, current, candidates=()) -> str:
        v = os.environ.get(env_name)
        if v:
            return str(Path(v).expanduser())
        if section.get(key):
            return _current(section[key])
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(candidate)
        return _current(current)

    install = pick("install_dir", "FORAN_SKILL_INSTALL_DIR",
                   getattr(E, "INSTALL_DIR", ""),
                   (r"C:\Program Files\FORAN\V80R3.0",))
    wrapper = pick("wrapper_dir", "FORAN_SKILL_WRAPPER_DIR",
                   getattr(E, "WRAPPER_DIR", ""),
                   ())
    projects = pick("projects_dir", "FORAN_SKILL_PROJECTS_DIR",
                    getattr(E, "PROJECTS_DIR", ""),
                    (r"C:\FORAN\projects",))
    if not projects and wrapper:
        projects = str(Path(wrapper) / "projects")
    conf = pick("conf_dir", "FORAN_SKILL_CONF_DIR",
                getattr(E, "CONF_DIR", ""),
                ())
    if not conf and wrapper and (Path(wrapper) / "conf").is_dir():
        conf = str(Path(wrapper) / "conf")
    logs = pick("logs_dir", "FORAN_SKILL_LOGS_DIR",
                getattr(E, "LOGS_DIR", ""),
                ())
    if not logs and wrapper and (Path(wrapper) / "logs").is_dir():
        logs = str(Path(wrapper) / "logs")
    license_file = pick("license_file", "FORAN_SKILL_LICENSE_FILE",
                        getattr(E, "LICENSE_FILE", ""), ())
    if not license_file and install:
        lic_dir = Path(install) / "foran_licensing"
        if lic_dir.is_dir():
            hits = sorted(lic_dir.glob("*.lic"))
            if hits:
                license_file = str(hits[0])
    workdir = pick("workdir", "FORAN_SKILL_WORKDIR",
                   getattr(E, "WORKDIR", Path.cwd()),
                   (str(Path.cwd()),))
    return {
        "install_dir": install, "wrapper_dir": wrapper,
        "license_file": license_file, "projects_dir": projects,
        "conf_dir": conf, "logs_dir": logs, "workdir": workdir,
    }


def ask(label: str, current: str, required: bool = False) -> str:
    suffix = f" [{current}]" if current else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if current:
            return current
        if not required:
            return ""
        print("  required")


def toml_string(value: str) -> str:
    if not value:
        return '""'
    p = Path(value).expanduser()
    return '"' + p.as_posix().replace('"', '\\"') + '"'


def write_config(path: Path, values: dict, old: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = path.with_name(
            f"{path.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, backup)
        print(f"backup   : {backup}")
    lines = [
        "# FORAN skill configuration (written by `foran setup`).",
        f"# {dt.datetime.now():%Y-%m-%d %H:%M}",
        "",
        "[foran]",
    ]
    for key in FIELDS:
        lines.append(f"{key} = {toml_string(values.get(key, ''))}")
    gui = old.get("gui", {})
    lines += ["", "[gui]"]
    for key, default in (("width", 1920), ("height", 1080),
                         ("dpi_scale", 1.0), ("click_settle", 0.3)):
        lines.append(f"{key} = {gui.get(key, default)}")
    deliver = old.get("deliver", {})
    if deliver:
        lines += ["", "[deliver]"]
        for key, value in deliver.items():
            if isinstance(value, str):
                lines.append(f"{key} = {toml_string(value)}")
            elif isinstance(value, bool):
                lines.append(f"{key} = {str(value).lower()}")
            elif isinstance(value, (int, float)):
                lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_check() -> int:
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("foran_env.py")), "check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report the current configuration; never write")
    ap.add_argument("--reset", action="store_true",
                    help="overwrite an existing config.toml")
    ap.add_argument("--yes", action="store_true",
                    help="non-interactive: keep existing values / use flags")
    for key in FIELDS:
        ap.add_argument("--" + key.replace("_", "-"), dest=key)
    args = ap.parse_args(argv)

    path = config_path()
    if args.check:
        print(f"config   : {path} ({'exists' if path.is_file() else 'missing'})")
        return run_check()

    old = load_toml(path)
    current = detect(path)
    values = dict(current)
    flags_given = False
    for key in FIELDS:
        flag = getattr(args, key)
        if flag:
            values[key] = flag
            flags_given = True

    keep = False
    if path.is_file() and not args.reset:
        print(f"config   : {path}")
        for key in FIELDS:
            print(f"  {key:14s} {values.get(key) or '<not set>'}")
        if args.yes:
            keep = not flags_given
            print("keeping existing values" if keep else "updating with flags")
        else:
            answer = input("Keep existing config? [Y/n] ").strip().lower()
            keep = answer in ("", "y", "yes")
            if keep:
                print("keeping existing values")
            else:
                for key in FIELDS:
                    values[key] = ask(key, values.get(key, ""),
                                      required=key in ("install_dir",))
    else:
        if args.yes:
            if not values.get("install_dir"):
                raise SystemExit("--install-dir is required")
        else:
            print(f"config   : {path} (new)")
            for key in FIELDS:
                values[key] = ask(key, values.get(key, ""),
                                  required=key in ("install_dir",))

    if not keep:
        write_config(path, values, old)
        print(f"written  : {path}")
    else:
        print(f"unchanged: {path}")
    return run_check()


if __name__ == "__main__":
    raise SystemExit(main())
