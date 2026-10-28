# -*- coding: utf-8 -*-
"""Open or export a FORAN .fds report in the Document Manager (FDM).

This drives the GUI: launch the module, File > Open..., fill the Win32 file
dialog, and verify that the window title changes to
`FORAN Document Manager - <file>`.

  python foran_fdm.py open --fds report.fds
  python foran_fdm.py open --fds report.fds --screenshot out.png
  python foran_fdm.py export --fds report.fds --out report.pdf
  python foran_fdm.py export --fds report.fds --out page.png --pages current
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_gui as G  # noqa: E402
import foran_launch as L  # noqa: E402


def _front(hwnd: int) -> bool:
    """Minimize the Claude terminal, maximize `hwnd`, and make it foreground."""
    import win32con
    import win32gui
    try:
        import foran_focus as FF
        term = FF.find_terminal()
        if term:
            win32gui.ShowWindow(term["hwnd"], win32con.SW_MINIMIZE)
            time.sleep(0.2)
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        time.sleep(0.3)
        ok = FF.focus(hwnd)
        return bool(ok or int(win32gui.GetForegroundWindow()) == int(hwnd))
    except Exception:  # noqa: BLE001
        return False


def _restore_terminal() -> None:
    try:
        import foran_focus as FF
        term = FF.find_terminal()
        if term:
            FF.focus(term["hwnd"])
    except Exception:  # noqa: BLE001
        pass


def _launch_fdm(workdir: Path) -> int:
    a = SimpleNamespace(module="fdm", project=None, copy_project=None, backup_first=False,
                        workdir=str(workdir), pass_fnam=False, extra=None, dry_run=False,
                        json=False, wait=False, force=False)
    plan = L.build(a)
    workdir.mkdir(parents=True, exist_ok=True)
    log_dir = Path.cwd() / "_foran_work" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"fdm_{dt.datetime.now():%Y%m%d-%H%M%S}.log"
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            plan["command"], cwd=plan["workdir"],
            env={**os.environ, **plan["env"]},
            stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    print(f"launched : pid={proc.pid} log={log}")
    return proc.pid


def _wait_window(title_prefix: str, timeout: float = 60.0):
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            if w.get("title", "").startswith(title_prefix):
                return w
        time.sleep(0.4)
    return None


def _open_dialog_path(dlg_hwnd: int, path: Path) -> bool:
    """Fill the Win32 `Choose a document to open` dialog and confirm."""
    import pyperclip
    import pyautogui
    from pywinauto import Application

    try:
        _front(dlg_hwnd)
        app = Application(backend="win32").connect(handle=dlg_hwnd).window(handle=dlg_hwnd)
    except Exception as exc:  # noqa: BLE001
        print(f"file dialog: {exc}", file=sys.stderr)
        return False
    try:
        edit = app.child_window(class_name="Edit", found_index=0)
        edit.click_input()
        pyautogui.hotkey("ctrl", "a")
        pyperclip.copy(str(path))
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
    except Exception:  # noqa: BLE001
        # Some dialogs expose the file name as a ComboBox.
        try:
            combo = app.child_window(class_name="ComboBox", found_index=0)
            combo.click_input()
            pyautogui.hotkey("ctrl", "a")
            pyperclip.copy(str(path))
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001
            print(f"file name field: {exc}", file=sys.stderr)
            return False
    try:
        app.child_window(title_re="^(打开|Open)", class_name="Button").click_input()
    except Exception:  # noqa: BLE001
        pyautogui.press("enter")
    return True


def _launch_and_open(fds: Path, workdir: Path, close_existing: bool):
    """Launch FDM, open `fds`, and return the main window dict (or None)."""
    running = [w for w in G.windows() if w.get("process", "").lower() == "fdm.exe"]
    if running:
        if not close_existing:
            print(f"FDM is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return None
        for w in running:
            _close_fdm(w)
        time.sleep(1.5)

    _launch_fdm(workdir)
    win = _wait_window("FORAN Document Manager", 60)
    if win is None:
        print("FORAN Document Manager window not found", file=sys.stderr)
        return None
    if not _front(win["hwnd"]):
        print("could not bring FDM to the foreground", file=sys.stderr)
        return None

    # File > Open... (the menu is custom-painted; click by position after maximize).
    import pyautogui
    pyautogui.click(55, 40)
    time.sleep(0.6)
    pyautogui.click(105, 77)
    time.sleep(1.5)
    dlg = None
    for w in G.windows():
        if w.get("class") == "#32770" and "document" in w.get("title", "").lower():
            dlg = w
            break
    if dlg is None:
        print("Open file dialog not found", file=sys.stderr)
        return None
    print(f"dialog   : {dlg['title']!r}")
    if not _open_dialog_path(dlg["hwnd"], fds):
        return None

    end = time.time() + 30
    opened = None
    while time.time() < end:
        for w in G.windows():
            if w.get("title", "").startswith("FORAN Document Manager -"):
                opened = w
                break
        if opened:
            break
        time.sleep(0.4)
    if opened is None:
        print("document did not open (title unchanged)", file=sys.stderr)
    return opened


def _close_fdm(win, timeout: float = 20.0) -> bool:
    import win32con
    import win32gui
    pid = int(win.get("pid") or 0)
    try:
        win32gui.PostMessage(win["hwnd"], win32con.WM_CLOSE, 0, 0)
    except Exception:  # noqa: BLE001
        return False
    end = time.time() + timeout
    while time.time() < end:
        if not [w for w in G.windows() if w.get("pid") == pid]:
            return True
        time.sleep(0.3)
    return False


def cmd_open(a) -> int:
    fds = Path(a.fds).expanduser().resolve()
    if not fds.is_file():
        raise SystemExit(f"FDS not found: {fds}")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fdm")

    win = _launch_and_open(fds, workdir, a.close_existing)
    _restore_terminal()
    if win is None:
        return 1
    print(f"opened   : {win['title']}")
    if a.screenshot:
        shot = Path(a.screenshot).expanduser().resolve()
        shot.parent.mkdir(parents=True, exist_ok=True)
        try:
            from foran_vision import capture_window
            import cv2
            cv2.imencode(".png", capture_window(win["hwnd"]))[1].tofile(str(shot))
            print(f"screenshot: {shot}")
        except Exception as exc:  # noqa: BLE001
            print(f"screenshot failed: {exc}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- export
# The Export dialog is a Qt widget, not a Win32 dialog: its controls are not
# exposed through UIA, so the coordinates below are relative to its rectangle
# (verified 2026-10-27 at 1920x1080, maximized FDM).
_EXPORT_TYPES = ("docx", "pdf", "csv", "dxf", "odt", "png", "svg")
_EXPORT_INDEX = {name: i + 1 for i, name in enumerate(_EXPORT_TYPES)}
_IMAGE_TYPES = {"png", "svg"}


def _fdm_foreground(win) -> bool:
    import win32gui
    if not _front(win["hwnd"]):
        return False
    time.sleep(0.6)
    return int(win32gui.GetForegroundWindow()) == int(win["hwnd"])


def _file_menu(win, rel_y: int, x_off: int = 100) -> bool:
    """Click the FDM File menu and an entry `rel_y` pixels below the popup top."""
    import pyautogui
    if not _fdm_foreground(win):
        print("FDM is not foreground; refusing to click", file=sys.stderr)
        return False
    pyautogui.click(55, 40)          # File (menu bar, maximized layout)
    pop = []
    end = time.time() + 4
    while time.time() < end and not pop:
        pop = [w for w in G.windows()
               if w.get("class") == "QPopup" and w.get("pid") == win["pid"]]
        if not pop:
            time.sleep(0.15)
    if not pop:
        print("File menu did not open", file=sys.stderr)
        return False
    l, t, _r, _b = pop[0]["rect"]
    pyautogui.click(l + x_off, t + rel_y)
    return True


def _pick_export_type(rect, fmt: str) -> None:
    """Pick a Files-of-type entry: the combo resets to DOCX, k Downs = k-th."""
    import pyautogui
    dl, dt_, _dr, _db = rect
    pyautogui.click(dl + 372, dt_ + 474)     # Files of type combo
    time.sleep(0.8)
    # A click on a popup row is swallowed (the popup is click-through), so close
    # the list and step the focused combo with Down instead.
    pyautogui.press("esc")
    time.sleep(0.5)
    for _ in range(_EXPORT_INDEX[fmt]):
        pyautogui.press("down")
        time.sleep(0.2)


def _export_dialog_fill(rect, out: Path) -> None:
    import pyautogui
    import pyperclip
    dl, dt_, _dr, _db = rect
    pyautogui.click(dl + 372, dt_ + 432)     # File name
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyperclip.copy(str(out))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)


def _image_options(pages: str) -> bool:
    """Answer the `Save as image` dialog (PNG/SVG only)."""
    import pyautogui
    dlg = _wait_window("Save as image", 10)
    if dlg is None:
        return True                          # some builds export directly
    il, it, _ir, _ib = dlg["rect"]
    pyautogui.click(il + (195 if pages == "all" else 35), it + 106)
    time.sleep(0.3)
    pyautogui.click(il + 93, it + 147)       # Ok
    time.sleep(0.5)
    return True


def _wait_export(out: Path, fmt: str, timeout: float) -> list[Path]:
    end = time.time() + timeout
    pattern = f"{out.stem}*{out.suffix}" if fmt in _IMAGE_TYPES else out.name
    files: list[Path] = []
    prev: dict[Path, int] | None = None
    while time.time() < end:
        alert = next((w for w in G.windows() if w.get("title") == "Alert"), None)
        if alert is not None:
            try:
                import pyautogui
                pyautogui.press("enter")
            except Exception:  # noqa: BLE001
                pass
            print("FDM reported an export error (Alert dialog)", file=sys.stderr)
            return []
        files = sorted(p for p in out.parent.glob(pattern) if p.is_file())
        sizes = {p: p.stat().st_size for p in files}
        if files and all(sizes.values()):
            if prev == sizes:
                return files
            prev = sizes
        else:
            prev = None
        time.sleep(1.0)
    return [p for p in files if p.stat().st_size > 0]


def _verify(path: Path, fmt: str) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    head = path.read_bytes()[:4096]
    if fmt == "pdf":
        return head.startswith(b"%PDF")
    if fmt in ("docx", "odt"):
        return head.startswith(b"PK\x03\x04")
    if fmt == "dxf":
        return b"SECTION" in head
    if fmt == "svg":
        return b"<svg" in head
    return True


def cmd_export(a) -> int:
    fds = Path(a.fds).expanduser().resolve()
    if not fds.is_file():
        raise SystemExit(f"FDS not found: {fds}")
    out = Path(a.out).expanduser().resolve()
    fmt = (a.format or out.suffix.lstrip(".")).lower()
    if fmt not in _EXPORT_INDEX:
        raise SystemExit(f"--format must be one of {', '.join(_EXPORT_TYPES)}")
    if a.pages not in ("current", "all"):
        raise SystemExit("--pages must be current or all")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fdm")

    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt in _IMAGE_TYPES:
        old = list(out.parent.glob(f"{out.stem}*{out.suffix}"))
    else:
        old = [out] if out.exists() else []
    for p in old:
        try:
            p.unlink()
        except OSError:
            pass

    win = _launch_and_open(fds, workdir, a.close_existing)
    if win is None:
        _restore_terminal()
        return 1
    print(f"opened   : {win['title']}")
    ok = False
    files: list[Path] = []
    try:
        if not _file_menu(win, 166):          # File > Export active...
            return 1
        dlg = _wait_window("Export FORAN document", 15)
        if dlg is None:
            print("Export dialog did not open", file=sys.stderr)
            return 1
        dl, dt_, _dr, _db = dlg["rect"]
        _pick_export_type(dlg["rect"], fmt)
        _export_dialog_fill(dlg["rect"], out)
        import pyautogui
        pyautogui.click(dl + 643, dt_ + 432)  # Open (starts the export)
        print(f"export   : {fmt} -> {out}")
        if fmt in _IMAGE_TYPES:
            _image_options(a.pages)
        files = _wait_export(out, fmt, a.timeout)
        ok = bool(files) and all(_verify(p, fmt) for p in files)
        for p in files:
            print(f"written  : {p} ({p.stat().st_size} bytes)")
        if not files:
            print("no output file was written", file=sys.stderr)
            if fmt == "png":
                print("hint: PNG rasterisation fails when the FDM page view is "
                      "blank; use pdf/dxf/svg or render the page first",
                      file=sys.stderr)
        elif not ok:
            print("output file failed the format check", file=sys.stderr)
        if not ok:
            # FDM leaves empty files behind when image generation fails.
            pat = (f"{out.stem}*{out.suffix}" if fmt in _IMAGE_TYPES else out.name)
            for p in out.parent.glob(pat):
                if p.is_file() and p.stat().st_size == 0:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        if fmt in _IMAGE_TYPES and a.pages == "all" and files:
            print(f"pages    : {len(files)} file(s)")
    finally:
        # Leave the dialog open only if the user asked to keep FDM.
        if not a.keep_open:
            dlg = next((w for w in G.windows()
                        if w.get("title", "").startswith("Export FORAN document")), None)
            if dlg is not None:
                try:
                    import pyautogui
                    dl, dt_, _dr, _db = dlg["rect"]
                    pyautogui.click(dl + 643, dt_ + 471)   # Cancel
                    time.sleep(0.5)
                except Exception:  # noqa: BLE001
                    pass
            _close_fdm(win)
        _restore_terminal()
    return 0 if ok else 1


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open", help="open a .fds in FDM")
    p.add_argument("--fds", required=True, help="FORAN .fds report")
    p.add_argument("--workdir", help="FDM working directory (default _foran_work/fdm)")
    p.add_argument("--screenshot", help="save a PNG of the opened document window")
    p.add_argument("--close-existing", action="store_true")
    p.set_defaults(fn=cmd_open)

    p = sub.add_parser("export", help="export the .fds via File > Export active")
    p.add_argument("--fds", required=True, help="FORAN .fds report")
    p.add_argument("--out", required=True, help="output file (extension picks the format)")
    p.add_argument("--format", choices=_EXPORT_TYPES,
                   help="output format (default: from --out extension)")
    p.add_argument("--pages", choices=("current", "all"), default="current",
                   help="png/svg only: current page or all pages (default current)")
    p.add_argument("--workdir", help="FDM working directory (default _foran_work/fdm)")
    p.add_argument("--timeout", type=float, default=600.0,
                   help="export timeout in seconds (default 600)")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.set_defaults(fn=cmd_export)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
