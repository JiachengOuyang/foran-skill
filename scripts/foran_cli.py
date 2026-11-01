# -*- coding: utf-8 -*-
"""Single entry point for the FORAN skill scripts.

  python foran_cli.py env check
  python foran_cli.py setup
  python foran_cli.py launch fdm --dry-run
  python foran_cli.py db hydro "D:\\path\\sample.db"
  python foran_cli.py journal summary --latest
  python foran_cli.py gui windows --filter foran
  python foran_cli.py macro where
  python foran_cli.py fga spaces --db sample.db --out spaces.tsv --copy
  python foran_cli.py fga tree --db sample.db --out tree.tsv --copy
  python foran_cli.py fga brep --db sample.db --brep box.brep --node CARGO --copy
  python foran_cli.py fga draw --db sample.db --out ga.dxf --copy
  python foran_cli.py hydro calc sample.db --draft 9.83
  python foran_cli.py hydro compare sample.db
  python foran_cli.py hull gen --lpp 172 --breadth 28.8 --draught 9.83 \
      --depth 14.6 --cb 0.83 --out out/hull --brep
  python foran_cli.py fsf build --brep hull_shell.brep --fnam TEST \
      --lpp 172 --breadth 28.8 --draught 9.83 --depth 14.6 --out TESTfsurf.fsf
  python foran_cli.py draw --fsf model.fsf --out lines.dxf
  python foran_cli.py gui fill-db --project sample.db --fnam sample --yes
  python foran_cli.py selftest [--db sample.db] [--json]
  python foran_cli.py test                     # offline unit tests
  python foran_cli.py doctor --db sample.db    # preflight before a long run
"""
from __future__ import annotations

# Make the process DPI-aware before pyautogui/pywinauto compute coordinates.
# On a 1920x1080 screen at 150% scaling, a DPI-unaware process sees 1280x720
# and every menu click lands at 2/3 of the intended position.
import os
if os.name == "nt":
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import importlib
import sys
from pathlib import Path

# `python -I` implies a safe sys.path (no script directory), so add it explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _warn_dotted_foran_names(argv: list[str]) -> None:
    """FORAN reads the extension from the first dot.

    ``model_v1.0_work.fsf`` is seen as ``.0_work.fsf`` and rejected with
    ``DsgAuxFileReader ERROR : Unknown file extension``.  Warn before a long
    GUI run instead of letting the user discover it halfway through.
    """
    from foran_names import has_extra_dots, suggest_foran_name

    seen: set[str] = set()
    for tok in argv:
        val = tok.split("=", 1)[1] if tok.startswith("--") and "=" in tok else tok
        name = Path(val).name
        low = name.lower()
        if low.endswith((".fsf", ".db")) and has_extra_dots(name) and name not in seen:
            seen.add(name)
            print(f"warning: {name!r} contains an extra '.'; FORAN parses the "
                  f"extension from the first dot and may reject it. Rename to "
                  f"{suggest_foran_name(name)}.", file=sys.stderr)


COMMANDS = {
    "env": "foran_env",
    "setup": "foran_setup",
    "launch": "foran_launch",
    "db": "foran_db",
    "journal": "foran_journal",
    "gui": "foran_gui",
    "macro": "foran_macro",
    "fga": "foran_fga",
    "fbasic": "foran_fbasic",
    "pipeline": "foran_pipeline",
    "hydro": "foran_hydro",
    "hull": "foran_hull",
    "fsf": "foran_fsf",
    "draw": "foran_draw",
    "dxf": "foran_dxf",
    "focus": "foran_focus",
    "vision": "foran_vision",
    "fdm": "foran_fdm",
    "offsets": "foran_offsets",
    "selftest": "foran_selftest",
    "test": "foran_tests",
    "doctor": "foran_doctor",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("commands: " + ", ".join(COMMANDS))
        return 0 if len(sys.argv) >= 2 else 2
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"unknown command {cmd!r}; choose from {', '.join(COMMANDS)}", file=sys.stderr)
        return 2
    _warn_dotted_foran_names(sys.argv[2:])
    mod = importlib.import_module(COMMANDS[cmd])
    return mod.main(sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
