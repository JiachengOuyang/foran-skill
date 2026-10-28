# -*- coding: utf-8 -*-
"""Import a closed hull shell into FSURF, assign it to the External Hull,
Build Ship, run the Surface Validator, and save an .fsf forms file.

Verified manually on 2026-10-26 with an 11-patch shell generated from
`foran hull gen` (nz=4, makeSolid=False, makeRuled=False).  The two hard GUI
steps are automated here:

  1. Manager: drag every patch from Work Space > Surface Entities to
     Form Surfaces > Hull Group > External Hull.  (Dragging the group is
     rejected; individual patch rows are required.)
  2. Surface Validator: Analyze -> Open -> Checked on the first two pages,
     Analyze all surfaces on Duplicated geometry / Lines on surface, Finish.

Requires the skill venv (pywinauto/pyautogui) and a maximized 1920x1080
FSURF window; the menu/Manager offsets were measured there.

Examples:
  foran fsf build --brep hull_shell.brep --fnam TEST \
    --lpp 172 --breadth 28.8 --draught 9.83 --depth 14.6 --out TESTfsurf.fsf
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402
import foran_draw as D  # noqa: E402
import foran_ui as UI  # noqa: E402

try:
    import pyautogui
    import pyperclip
    import foran_gui as G
    from pywinauto import Application
except Exception as exc:  # noqa: BLE001
    print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
    raise SystemExit(3)


# ---------------------------------------------------------------- launch
def _launch_fsurf(workdir: Path) -> subprocess.Popen:
    info = E.module_info("fsurf")
    wrapper = info["wrapper"] if Path(info["wrapper"]).exists() else info["official"]
    env = dict(os.environ)
    env["LM_LICENSE_FILE"] = str(E.LICENSE_FILE)
    env["FORAN_CONF"] = str(E.CONF_DIR)
    workdir.mkdir(parents=True, exist_ok=True)
    log = workdir / f"fsurf_launch_{dt.datetime.now():%Y%m%d-%H%M%S}.log"
    with open(log, "ab") as fh:
        return subprocess.Popen(["cmd.exe", "/c", str(wrapper)], cwd=str(workdir),
                                env=env, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=subprocess.STDOUT)


def _wait_main(timeout: float = 30.0):
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            if w.get("title", "").startswith("fsurf -"):
                return w
        time.sleep(0.4)
    return None


def _click(hwnd: int, x: int, y: int, pause: float = 0.8):
    G._focus(hwnd)
    pyautogui.click(x, y)
    time.sleep(pause)


def _menu(hwnd: int, x: int, y: int, pause: float = 1.0):
    _click(hwnd, x, y, pause)


def _menu_key(txt: str) -> str:
    return UI.menu_key(txt)


def _menu_click(hwnd: int, name: str, fallback: tuple[int, int],
                pause: float = 0.8) -> bool:
    """Click a menu item by UIA name; fall back to the measured point."""
    return UI.menu_click(G, hwnd, name, fallback, pause)


def _import_brep(hwnd: int, workdir: Path, src: Path) -> bool:
    local = workdir / src.name
    shutil.copy2(src, local)
    _menu_click(hwnd, "File", (57, 54))
    _menu_click(hwnd, "Export/Import...", (120, 156))
    _menu_click(hwnd, "Import / Merge", (350, 313))
    dlg = D.find_hwnd("Import file", timeout=20)
    if dlg is None:
        print("Import file dialog not found", file=sys.stderr)
        return False
    G._focus(dlg)
    # Files of type: Project, Decks, Patches, Patches r1.1, Patches ASCII,
    # IGES, STEP, BREP -> Home + 5/6/7 Down.
    down = {".brep": 7, ".stp": 6, ".step": 6, ".igs": 5, ".iges": 5}.get(
        src.suffix.lower(), 7)
    # Click the ComboBox next to the "Files of type:" label (UIA); the old
    # fixed point is only a fallback.
    combo = None
    try:
        d0 = D.dlg_for(dlg)
        label = next((c for c in d0.descendants(control_type="Text")
                      if (c.window_text() or "").strip().lower()
                      .startswith("files of type")), None)
        if label is not None:
            top = label.rectangle().top
            cands = [c for c in d0.descendants(control_type="ComboBox")
                     if abs(c.rectangle().top - top) <= 8]
            combo = cands[0] if cands else None
    except Exception:  # noqa: BLE001
        combo = None
    if combo is not None:
        r = combo.rectangle()
        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    else:
        pyautogui.click(960, 712)
    time.sleep(0.6)
    pyautogui.press("home")
    time.sleep(0.2)
    for _ in range(down):
        pyautogui.press("down")
        time.sleep(0.1)
    pyautogui.press("enter")
    time.sleep(1.2)
    d = D.dlg_for(dlg)
    picked = False
    for c in d.descendants(control_type="ListItem"):
        try:
            if (c.window_text() or "").strip() == local.name:
                c.click_input()
                picked = True
                break
        except Exception:  # noqa: BLE001
            pass
    if not picked:
        print(f"file {local.name} not visible in Import file dialog", file=sys.stderr)
        return False
    time.sleep(0.6)
    for c in d.descendants(control_type="Button"):
        try:
            if (c.window_text() or "").strip() == "Open" and c.rectangle().top > 600:
                c.click_input()
                time.sleep(8)
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


# ---------------------------------------------------------------- manager
def _open_manager(hwnd: int):
    _menu_click(hwnd, "Structure", (400, 54))
    _menu_click(hwnd, "Manager", (430, 91))
    win = None
    for _ in range(20):
        for w in G.windows():
            if w.get("title") == "Foran Objects Manager":
                win = w
                break
        if win:
            break
        time.sleep(0.4)
    if win is None:
        return None
    import win32con
    import win32gui
    G._focus(win["hwnd"])
    win32gui.ShowWindow(win["hwnd"], win32con.SW_MAXIMIZE)
    time.sleep(1.5)
    return win["hwnd"]


def _mgr_click_item(d, name: str, expand: bool = False):
    for c in d.descendants(control_type="TreeItem"):
        try:
            r = c.rectangle()
            if (c.window_text() or "").strip() == name and r.left < 1100:
                c.click_input()
                time.sleep(0.5)
                if expand:
                    pyautogui.press("right")
                    time.sleep(0.7)
                return r
        except Exception:  # noqa: BLE001
            pass
    return None


def _mgr_patch_rows(d):
    """Patch rows in the right-hand Work Space list (left > 1000)."""
    rows = []
    for c in d.descendants(control_type="TreeItem"):
        try:
            txt = (c.window_text() or "").strip()
            if txt.startswith("Patch") and c.rectangle().left > 1000:
                rows.append(c)
        except Exception:  # noqa: BLE001
            pass
    return rows


def _mgr_row_point(r, grab: bool = False):
    """Screen point on the meaningful part of a Manager row.

    Manager rows are full-width QTreeWidget items: the UIA rectangle spans
    the whole tree pane, so the geometric centre lands on blank space far to
    the right of the label.  FORAN ignores drags dropped there -- the cursor
    has to be on the row's text (left edge + a few pixels).
    """
    y = (r.top + r.bottom) // 2
    if r.width() > 300:
        x = r.left + (30 if grab else 18)
    else:
        x = (r.left + r.right) // 2
    return x, y


def _mgr_find(d, name: str):
    for c in d.descendants(control_type="TreeItem"):
        try:
            if (c.window_text() or "").strip() == name and c.rectangle().left < 1100:
                return c
        except Exception:  # noqa: BLE001
            pass
    return None


def _drag_patch_to_hull(mw: int) -> bool:
    """Drag the first patch row onto External Hull. Returns False if unavailable."""
    d = G._app_window(mw, "uia")
    rows = _mgr_patch_rows(d)
    ext = _mgr_find(d, "External Hull")
    if not rows or ext is None:
        return False
    sr = rows[0].rectangle()
    er = ext.rectangle()
    sx, sy = _mgr_row_point(sr, grab=True)
    ex, ey = _mgr_row_point(er)
    print(f"  manager: drag ({sx},{sy}) -> ({ex},{ey})  "
          f"src={sr.width()}x{sr.height()} ext={er.width()}x{er.height()}")
    G._focus(mw)
    pyautogui.moveTo(sx, sy, duration=0.2)
    time.sleep(0.2)
    pyautogui.mouseDown()
    time.sleep(0.4)
    pyautogui.moveTo(sx + 8, sy + 2, duration=0.2)   # start the drag
    time.sleep(0.3)
    pyautogui.moveTo(ex, ey, duration=1.0)           # land on the row text
    time.sleep(0.3)
    pyautogui.moveTo(ex + 1, ey, duration=0.2)       # nudge -> drag-enter
    time.sleep(0.8)
    pyautogui.mouseUp()
    time.sleep(1.0)
    return True


def _open_manager_root(mw: int) -> bool:
    d = G._app_window(mw, "uia")
    _mgr_click_item(d, "Forma", True)
    _mgr_click_item(d, "Work Space", True)
    _mgr_click_item(d, "Form Surfaces", True)
    _mgr_click_item(d, "Hull Group", True)
    if _mgr_find(d, "External Hull") is None:
        print("External Hull not found in Manager", file=sys.stderr)
        return False
    return True


def _close_manager(mw: int) -> None:
    try:
        G._focus(mw)
        G._app_window(mw, "uia").close()
    except Exception:  # noqa: BLE001
        try:
            G._focus(mw)
            pyautogui.hotkey("alt", "f4")
        except Exception:  # noqa: BLE001
            pass
    end = time.time() + 6
    while time.time() < end:
        if not any(w["hwnd"] == mw for w in G.windows()):
            return
        time.sleep(0.3)


def _assign_patches(mw: int) -> bool:
    """Assign every patch to External Hull; verify the Work Space is empty.

    Dragging the group row is rejected by the Manager, so each patch row is
    dragged individually.  The source point comes from the first live Patch
    row (not a hard-coded coordinate) and the result is verified by re-counting
    the rows instead of trusting that the drag worked.
    """
    G._focus(mw)
    if not _open_manager_root(mw):
        return False
    d = G._app_window(mw, "uia")
    _mgr_click_item(d, "Surface Entities")
    time.sleep(0.8)
    d = G._app_window(mw, "uia")
    initial = _mgr_patch_rows(d)
    print(f"  manager: {len(initial)} patch row(s) in Work Space > Surface Entities")
    if not initial:
        # Do not report success: an empty right pane usually means the rows
        # were never listed (wrong node selected), not that they were moved.
        dump = []
        for c in d.descendants(control_type="TreeItem"):
            try:
                r = c.rectangle()
                if r.left > 1000:
                    dump.append(f"{c.window_text()!r} ({r.left},{r.top},{r.right},{r.bottom})")
            except Exception:  # noqa: BLE001
                pass
        print("  manager: right pane rows:\n    " + "\n    ".join(dump[:40]),
              file=sys.stderr)
        return False
    tries_without_progress = 0
    last_count = None
    for _ in range(80):
        d = G._app_window(mw, "uia")
        rows = _mgr_patch_rows(d)
        if not rows:
            print("  manager: all patches assigned to External Hull")
            _close_manager(mw)
            return True
        if last_count is not None and len(rows) >= last_count:
            tries_without_progress += 1
        else:
            tries_without_progress = 0
        last_count = len(rows)
        if tries_without_progress >= 5:
            print("  manager: patch count stopped decreasing; drag is failing",
                  file=sys.stderr)
            _close_manager(mw)
            return False
        if not _drag_patch_to_hull(mw):
            break
        # Re-select Work Space so the remaining rows are visible.
        d = G._app_window(mw, "uia")
        _mgr_click_item(d, "Surface Entities")
        time.sleep(0.5)
    d = G._app_window(mw, "uia")
    ok = not _mgr_patch_rows(d)
    print(f"  manager: assignment complete={ok}")
    _close_manager(mw)
    return ok


# ---------------------------------------------------------------- build ship
def _complete_validator(hwnd: int) -> bool:
    """Robust Surface Validator walk (shared implementation in foran_draw)."""
    return D.complete_validator(hwnd)


def _fill_ctrl(ctrl, value: str) -> None:
    r = ctrl.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.25)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyperclip.copy(str(value))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.25)
    pyautogui.press("tab")
    time.sleep(0.3)


def _define_frame_system(hwnd: int, nmax: int, spacing: float) -> bool:
    """Define a simple frame system (needed by Lines Drawing).

    Build Ship writes an .fsf without a frame system, so `DsgLinesDrawCmd`
    fails with "The Frame system has not been defined".  The dialog is
    File > Ship > Edit frame system: set Nmax + spacing, Add, Ok.
    """
    D.dismiss_extra_dialogs()
    G._focus(hwnd)
    _menu_click(hwnd, "File", (57, 54))
    time.sleep(0.4)
    _menu_click(hwnd, "Ship", (120, 289))
    time.sleep(0.4)
    _menu_click(hwnd, "Edit frame system", (400, 450))
    fh = D.find_hwnd("fsurf", exact=True, timeout=15)
    if fh is None:
        print("frame system dialog not found", file=sys.stderr)
        return False
    G._focus(fh)
    d = G._app_window(fh, "uia")
    nmax_ctrl = spc_ctrl = None
    for c in d.descendants():
        try:
            t = (c.window_text() or "").strip()
            ct = c.element_info.control_type
            if t == "Nmax" and ct == "Edit":
                nmax_ctrl = c
            elif t == "Spc" and ct == "Custom":
                spc_ctrl = c
        except Exception:  # noqa: BLE001
            pass
    if nmax_ctrl is None or spc_ctrl is None:
        print("frame system fields not found", file=sys.stderr)
        D.click_button(fh, "Cancel")
        return False
    _fill_ctrl(nmax_ctrl, nmax)
    _fill_ctrl(spc_ctrl, f"{spacing:.6g}")
    if not D.click_button(fh, "Add", timeout=5):
        print("frame system Add failed", file=sys.stderr)
        D.click_button(fh, "Cancel")
        return False
    time.sleep(0.6)
    # Verify the new row appears in the list (Num Max + Space columns).
    row_texts = D.validator_texts(fh)
    if str(nmax) not in row_texts and f"{spacing:.6f}" not in row_texts:
        print(f"frame system row not added (texts={row_texts})", file=sys.stderr)
        D.click_button(fh, "Cancel")
        return False
    if not D.click_button(fh, "Ok", timeout=5):
        print("frame system Ok failed", file=sys.stderr)
        return False
    time.sleep(1.5)
    return True


def _save_model(hwnd: int, path: Path, suffix: str = "_frames"):
    """File > Save the session (frames) to a fresh .fsf; return its path.

    Ctrl+S does not reach the command; File > Save opens a Qt `Save File`
    dialog with an *empty* File name field (even though the title bar shows
    the current file), so the name has to be typed.  The field is filled via
    the clipboard because a Chinese IME mangles pyautogui.typewrite (a test
    produced "特殊天赋surf。f's'f.fsf").

    Saving over an existing name raises an overwrite prompt whose window
    title is not in the usual Warning/Error set, so the writer silently sat
    there until it was cancelled.  Saving to a unique `_frames` name avoids
    that prompt entirely.
    """
    target = path.with_name(f"{path.stem}{suffix}{path.suffix}")
    if target.exists():
        target = path.with_name(
            f"{path.stem}{suffix}_{dt.datetime.now():%H%M%S}{path.suffix}")
    G._focus(hwnd)
    _menu_click(hwnd, "File", (57, 54))
    time.sleep(0.5)
    # "Save as ..." opens the Save File dialog; plain "Save" writes in place.
    _menu_click(hwnd, "Save as ...", (110, 232))
    sh = D.find_hwnd("Save File", timeout=10)
    if sh is None:
        print("Save File dialog not found", file=sys.stderr)
        return None
    G._focus(sh)
    d = D.dlg_for(sh)
    edit = None
    for c in d.descendants(control_type="Edit"):
        try:
            r = c.rectangle()
            if r.top > 550:       # File name field at the bottom
                edit = c
        except Exception:  # noqa: BLE001
            pass
    if edit is None:
        print("Save File: name field not found", file=sys.stderr)
        D.click_button(sh, "Cancel")
        return None
    r = edit.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyperclip.copy(str(target))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    if not D.click_button(sh, "Save", timeout=5):
        print("Save File: Save button not found", file=sys.stderr)
        D.click_button(sh, "Cancel")
        return None
    end = time.time() + 40
    while time.time() < end:
        if target.exists() and target.stat().st_size > 0:
            time.sleep(1.0)       # let the writer finish
            return target
        time.sleep(0.5)
    print("Save File: no file written", file=sys.stderr)
    return None


def _lines_drawing(hwnd: int, out: Path, opts: dict | None = None,
                   scale: float = 100.0) -> bool:
    """File > Ship > Drawings > Lines drawing, then save a DXF.

    Menu clicks measured on the maximized 1920x1080 window: Drawings is the
    4th item of the Ship submenu.  The Drawings submenu is a QPopup (not the
    floating QTool window the old code waited for), so navigate with the
    keyboard and let `fill_lines_dialog` handle the dialog.
    """
    G._focus(hwnd)
    pyautogui.press("escape")
    time.sleep(0.4)
    _menu_click(hwnd, "File", (57, 54))
    time.sleep(0.7)
    for _ in range(6):            # New .. Ship
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")      # Ship submenu
    time.sleep(0.8)
    for _ in range(3):            # Build ship .. Drawings
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")      # Drawings submenu
    time.sleep(0.8)
    pyautogui.press("enter")      # Lines drawing
    time.sleep(2.5)
    if not D.fill_lines_dialog(out, f"{scale:g}", opts, timeout=30):
        print("Lines Drawing dialog not found", file=sys.stderr)
        return False
    ok = D.wait_file(out, timeout=180)
    if not ok:
        print("DXF not produced", file=sys.stderr)
    return ok


def _build_ship(hwnd: int, fnam: str, lpp: str, b: str, t: str, d: str) -> bool:
    D.dismiss_extra_dialogs()
    # Keyboard navigation is more reliable than menu coordinates here:
    # File -> Down x6 = Ship -> Right -> Enter = Build ship.
    G._focus(hwnd)
    _menu_click(hwnd, "File", (57, 54))
    time.sleep(0.8)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(1.0)
    pyautogui.press("enter")
    bhwnd = D.find_hwnd("fsurf", exact=True, timeout=30)
    if bhwnd is None:
        print("Build Ship dialog not found", file=sys.stderr)
        return False
    G._focus(bhwnd)
    try:
        D.fill_build_ship(bhwnd, {"fnam": fnam, "lpp": lpp, "breadth": b,
                                  "draught": t, "depth": d})
    except SystemExit as exc:
        print(f"Build Ship fields: {exc}", file=sys.stderr)
        return False
    ok = False
    for c in D.dlg_for(bhwnd).descendants(control_type="Button"):
        try:
            if (c.window_text() or "").strip() == "OK":
                c.click_input()
                ok = True
                break
        except Exception:  # noqa: BLE001
            pass
    if not ok:
        return False
    # Wait for the overwrite prompt and the Surface Validator (Build Ship
    # recomputes the ship, so poll instead of sleeping a fixed time).
    val = None
    end = time.time() + 30
    while time.time() < end:
        exist = D.find_hwnd("File Ship Exist", timeout=0.2)
        if exist is not None:
            D.click_button(exist, "Yes")
            time.sleep(0.4)
            continue
        val = D.find_hwnd("Surface Validator", timeout=0.2)
        if val is not None:
            break
        time.sleep(0.3)
    if val is None:
        print("Surface Validator not found", file=sys.stderr)
        return False
    return _complete_validator(val)


# ---------------------------------------------------------------- CLI
def _set_float_value(hwnd: int, value: float) -> bool:
    """Fill the single Edit of FSURF's `Enter float value` dialog and accept."""
    end = time.time() + 10
    while time.time() < end:
        try:
            d = G._app_window(hwnd, "uia")
            edits = [c for c in d.descendants(control_type="Edit")]
        except Exception:  # noqa: BLE001
            edits = []
        if edits:
            e = edits[0]
            r = e.rectangle()
            G._focus(hwnd)
            pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            time.sleep(0.25)
            pyautogui.hotkey("ctrl", "a")
            pyperclip.copy(f"{value:.6f}")
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            return D.click_button(hwnd, "OK", timeout=5)
        time.sleep(0.2)
    return False


def _selected_count(hwnd: int):
    """Read the `N part(s) selected` text of a Select Parts/Decks dialog."""
    try:
        d = G._app_window(hwnd, "uia")
        for c in d.descendants(control_type="Text"):
            m = re.match(r"(\d+)\s+part\(s\)\s+selected",
                         (c.window_text() or "").strip())
            if m:
                return int(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return None


def _delete_structure(hwnd: int, parent: str, item: str, title: str,
                      timeout: float = 20.0) -> bool:
    """Structure > <parent> > <item> -> All -> Delete -> Done."""
    G._focus(hwnd)
    UI.menu_click(G, hwnd, "Structure", (400, 54))
    UI.menu_click(G, hwnd, parent, (400, 240), popup_first=True)
    UI.menu_click(G, hwnd, item, (780, 240), popup_first=True)
    dlg = D.find_hwnd(title, timeout=15)
    if dlg is None:
        print(f"delete {parent.lower()}: {title!r} dialog not found", file=sys.stderr)
        return False
    G._focus(dlg)
    if not D.click_button(dlg, "All", timeout=5):
        print(f"delete {parent.lower()}: 'All' not found", file=sys.stderr)
        return False
    time.sleep(0.6)
    count = _selected_count(dlg)
    if count == 0:
        # Nothing to delete (e.g. the model has no bulkheads): Done may stay
        # disabled, so just close the dialog.
        D.click_button(dlg, "Cancel")
        time.sleep(0.6)
        return True
    if not D.click_button(dlg, "Delete", timeout=5):
        print(f"delete {parent.lower()}: 'Delete' not found", file=sys.stderr)
        return False
    time.sleep(0.8)
    if not D.click_button(dlg, "Done", timeout=5):
        print(f"delete {parent.lower()}: 'Done' not found", file=sys.stderr)
        return False
    end = time.time() + timeout
    while time.time() < end:
        if D.find_hwnd(title, timeout=0.2) is None:
            time.sleep(1.0)
            return True
        time.sleep(0.4)
    print(f"delete {parent.lower()}: dialog did not close", file=sys.stderr)
    return False


def _plane_scale(hwnd: int, plane: str, factor: float,
                 timeout: float = 120.0) -> bool:
    """Edition > Transform > Plane scale -> All/Done -> plane -> factor.

    `plane` is the button that defines the reference plane: `YZ` means X=0
    (stretch along X), `XZ` means Y=0.  The first dialog selects the parts;
    "All" + "Done" selects everything in the scene.
    """
    G._focus(hwnd)
    UI.menu_click(G, hwnd, "Edition", (100, 54))
    UI.menu_click(G, hwnd, "Transform", (150, 316), popup_first=True)
    UI.menu_click(G, hwnd, "Plane scale", (400, 480), popup_first=True)
    sel = D.find_hwnd("Select Parts", timeout=15)
    if sel is None:
        print("plane scale: Select Parts dialog not found", file=sys.stderr)
        return False
    G._focus(sel)
    if not D.click_button(sel, "All", timeout=5):
        print("plane scale: 'All' not found", file=sys.stderr)
        return False
    time.sleep(0.6)
    if not D.click_button(sel, "Done", timeout=5):
        print("plane scale: 'Done' not found", file=sys.stderr)
        return False
    pl = D.find_hwnd("3D Plane", timeout=15)
    if pl is None:
        print("plane scale: 3D Plane dialog not found", file=sys.stderr)
        return False
    G._focus(pl)
    if not D.click_button(pl, plane, timeout=5):
        print(f"plane scale: {plane!r} button not found", file=sys.stderr)
        return False
    fv = D.find_hwnd("Enter float value", timeout=10)
    if fv is None:
        print("plane scale: scale factor dialog not found", file=sys.stderr)
        return False
    if not _set_float_value(fv, factor):
        print("plane scale: scale factor not accepted", file=sys.stderr)
        return False
    # Wait until the command's dialogs are gone (it may compute for a while).
    end = time.time() + timeout
    while time.time() < end:
        if (D.find_hwnd("Select Parts", timeout=0.2) is None
                and D.find_hwnd("3D Plane", timeout=0.2) is None
                and D.find_hwnd("Enter float value", timeout=0.2) is None):
            time.sleep(1.5)
            return True
        time.sleep(0.5)
    print("plane scale: transform did not finish", file=sys.stderr)
    return False


def _open_fsurf_model(model: Path, workdir: Path) -> bool:
    """Launch FSURF through the configured launcher and open `model` via GUI.

    The stock launcher is started normally, then File > Open is filled with
    `model`.
    """
    import foran_launch as L
    rc = L.main(["fsurf", "--workdir", str(workdir)])
    if rc:
        return False
    win = _wait_main(60)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        return False
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(1.5)
    if not _menu_click(hwnd, "File", (57, 54)):
        return False
    if not _menu_click(hwnd, "Open", (105, 80), pause=1.0):
        return False
    if not D.fill_open_dialog(model, timeout=30):
        print("Open file dialog not found", file=sys.stderr)
        return False
    # Wait until the main window title shows the model, then let geometry load.
    deadline = time.time() + 60
    while time.time() < deadline:
        wins = [w for w in G.windows() if w.get("hwnd") == hwnd]
        if wins and model.name in wins[0].get("title", ""):
            break
        time.sleep(0.5)
    time.sleep(6.0)
    return True


def _fill_offset_path(dlg: int, path: Path) -> bool:
    """Offset dialog -> Select... -> Save Offset File -> file name -> Save."""
    d = G._app_window(dlg, "uia")
    sel = next((b for b in d.descendants(control_type="Button")
                if "Select" in (b.window_text() or "")), None)
    if sel is None:
        return False
    sel.click_input()
    save = D.find_hwnd("Save Offset File", timeout=10)
    if save is None:
        return False
    G._focus(save)
    time.sleep(0.5)
    d2 = G._app_window(save, "uia")
    lab = next((c for c in d2.descendants(control_type="Text")
                if "File name" in (c.window_text() or "")), None)
    if lab is None:
        return False
    lt = lab.rectangle().top
    edits = [c for c in d2.descendants(control_type="Edit")
             if abs(c.rectangle().top - lt) <= 12]
    if not edits:
        return False
    edit = edits[0]
    edit.click_input()
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyperclip.copy(str(path))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    if not D.click_button(save, "Save", timeout=5):
        return False
    time.sleep(1.0)
    return True


def cmd_offsets(a) -> int:
    """File > Ship > Offset table -> .lis loftbook (+ optional hydrostatics)."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    out_base = Path(a.out).expanduser().resolve()
    out_base.parent.mkdir(parents=True, exist_ok=True)
    exp = out_base.with_suffix(".lis")
    if exp.exists():
        exp.unlink()
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"offsets_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    # File > Ship > Offset table (6th File item -> Ship -> 3rd Ship item).
    pyautogui.press("escape")
    time.sleep(0.4)
    _menu_click(hwnd, "File", (57, 54))
    time.sleep(0.7)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(0.8)
    for _ in range(2):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.5)
    dlg = D.find_hwnd("Offset", timeout=15)
    if dlg is None:
        print("Offset dialog not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    G._focus(dlg)
    time.sleep(0.5)
    if not _fill_offset_path(dlg, out_base.with_suffix(".lis")):
        print("Offset: output path not accepted", file=sys.stderr)
        D.close_fsurf()
        return 1
    if not D.click_button(dlg, "Ok", timeout=5):
        print("Offset: Ok not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    started = time.time()
    end = time.time() + a.timeout
    lis = None
    prev = None
    while time.time() < end:
        cand = exp if exp.exists() else None
        if cand is None:
            hits = sorted(out_base.parent.glob("*.lis"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            if hits and hits[0].stat().st_mtime >= started:
                cand = hits[0]
        if cand is not None and cand.stat().st_size > 0:
            size = cand.stat().st_size
            # Wait until the writer has finished (two stable size checks).
            if size == prev:
                try:
                    tail = cand.read_text(encoding="utf-8",
                                          errors="replace")[-400:]
                except Exception:  # noqa: BLE001
                    tail = ""
                if "PROCESS COMPLETED" in tail or size == prev:
                    lis = cand
                    break
            prev = size
        time.sleep(0.8)
    if lis is None:
        print("offset table was not written", file=sys.stderr)
        D.close_fsurf()
        return 1
    print(f"offsets  : {lis} ({lis.stat().st_size} bytes)")

    rc = 0
    if a.hydro:
        import foran_offsets as O
        data = O.parse_loftbook(lis)
        ts = [float(x) for x in a.hydro.split(",") if x.strip()]
        rows = O.hydrostatics(data, ts)
        for row in rows:
            print(f"T={row['draught']:6.2f} m  vol={row['volume']:10.1f} m3  "
                  f"Cb={row['cb']:.4f}  LCB(AP)={row['lcb_ap']:7.2f} m  "
                  f"Cm={row['cm']:.4f}  Cw={row['cwp']:.4f}")
        if a.expect:
            lines, ok = O.compare(rows, a.expect, a.tol)
            for ln in lines:
                print(ln)
            print("check    : " + ("PASS" if ok else "FAIL"))
            rc = 0 if ok else 1
    elif a.expect:
        print("--expect needs --hydro", file=sys.stderr)
        rc = 2

    if not a.keep_open:
        D.close_fsurf()
    return rc


def _labeled_edit_in(hwnd: int, label: str):
    d = G._app_window(hwnd, "uia")
    lab = next((c for c in d.descendants(control_type="Text")
                if (c.window_text() or "").strip() == label), None)
    if lab is None:
        return None
    top, right = lab.rectangle().top, lab.rectangle().right
    edits = [c for c in d.descendants(control_type="Edit")
             if abs(c.rectangle().top - top) <= 8
             and c.rectangle().left >= right - 2]
    return edits[0] if edits else None


def _set_edit(edit, value) -> bool:
    if edit is None:
        return False
    # Use UIA click_input(): pyautogui screen coordinates are off under 150%
    # display scaling and silently write into the wrong field.
    try:
        edit.click_input()
    except Exception:  # noqa: BLE001
        r = edit.rectangle()
        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyperclip.copy(str(value))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    return True


def _click_tab(hwnd: int, name: str) -> bool:
    for c in G._app_window(hwnd, "uia").descendants(control_type="TabItem"):
        if (c.window_text() or "").strip() == name:
            c.click_input()
            time.sleep(0.8)
            return True
    return False


def _click_radio(hwnd: int, name: str) -> bool:
    for c in G._app_window(hwnd, "uia").descendants(control_type="RadioButton"):
        if (c.window_text() or "").strip() == name:
            c.click_input()
            time.sleep(0.4)
            return True
    return False


def _bulkhead_new(hwnd: int, ident: int, name: str, x: float,
                  axis: str = "X", symmetrical: bool = False) -> bool:
    """Create one bulkhead at X = x (or Y = y); contour accepted as-is."""
    UI.menu_click(G, hwnd, "Structure", (400, 54))
    UI.menu_click(G, hwnd, "Bulkheads", (400, 275), popup_first=True)
    UI.menu_click(G, hwnd, "New bulkhead", (780, 275), popup_first=True)
    dlg = D.find_hwnd("Bulkhead", exact=True, timeout=15)
    if dlg is None:
        print("new bulkhead: dialog not found", file=sys.stderr)
        return False
    G._focus(dlg)
    time.sleep(0.6)
    _click_tab(dlg, "Properties")
    _set_edit(_labeled_edit_in(dlg, "Ident:"), ident)
    _set_edit(_labeled_edit_in(dlg, "Name:"), name)
    _click_tab(dlg, "Geometry")
    if not _click_radio(dlg, f"{axis} = k"):
        print(f"new bulkhead: '{axis} = k' not found", file=sys.stderr)
        return False
    # With a frame system present, "Frame:" is checked by default and the
    # absolute "Value of k" field is disabled.  Uncheck it to enter metres
    # from AP.
    for c in G._app_window(dlg, "uia").descendants(control_type="CheckBox"):
        if (c.window_text() or "").strip() == "Frame:":
            try:
                if c.get_toggle_state():
                    c.click_input()
                    time.sleep(0.4)
            except Exception:  # noqa: BLE001
                pass
            break
    if not _set_edit(_labeled_edit_in(dlg, "Value of k ="), f"{x:g}"):
        print("new bulkhead: 'Value of k' not found", file=sys.stderr)
        return False
    if symmetrical:
        for c in G._app_window(dlg, "uia").descendants(control_type="CheckBox"):
            if "symmetrical" in (c.window_text() or "").lower():
                try:
                    if not bool(c.iface_toggle.CurrentToggleState):
                        c.click_input()
                except Exception:  # noqa: BLE001
                    c.click_input()
                time.sleep(0.3)
                break
    if not D.click_button(dlg, "Done", timeout=5):
        print("new bulkhead: Done not found", file=sys.stderr)
        return False
    cont = D.find_hwnd("Contour", exact=True, timeout=15)
    if cont is None:
        print(f"new bulkhead {name}: Contour dialog not found", file=sys.stderr)
        return False
    G._focus(cont)
    ok_done = False
    end = time.time() + 10
    while time.time() < end:
        if D.click_button(cont, "Done", timeout=1):
            ok_done = True
            break
        time.sleep(0.4)
    if not ok_done:
        print(f"new bulkhead {name}: Contour Done not found", file=sys.stderr)
        return False
    end = time.time() + 45
    while time.time() < end:
        if (D.find_hwnd("Bulkhead", exact=True, timeout=0.2) is None
                and D.find_hwnd("Contour", exact=True, timeout=0.2) is None):
            time.sleep(0.5)
            return True
        time.sleep(0.3)
    print(f"new bulkhead {name}: dialogs did not close", file=sys.stderr)
    try:
        print("windows: " + ", ".join(
            f"{w.get('title')!r}" for w in G.windows()
            if w.get("process", "").lower() == "fsurf.exe"), file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
    return False


def _bulkhead_count(hwnd: int):
    """Count bulkheads via Structure > Bulkheads > Delete bulkheads (Cancel)."""
    UI.menu_click(G, hwnd, "Structure", (400, 54))
    UI.menu_click(G, hwnd, "Bulkheads", (400, 275), popup_first=True)
    UI.menu_click(G, hwnd, "Delete bulkheads", (780, 275), popup_first=True)
    sel = D.find_hwnd("Select Bulkheads", exact=True, timeout=10)
    if sel is None:
        return None
    G._focus(sel)
    D.click_button(sel, "All", timeout=5)
    time.sleep(0.8)
    count = None
    for c in G._app_window(sel, "uia").descendants(control_type="Text"):
        m = re.match(r"(\d+)\s+part\(s\)\s+selected",
                     (c.window_text() or "").strip())
        if m:
            count = int(m.group(1))
            break
    D.click_button(sel, "Cancel")
    time.sleep(0.8)
    return count


def cmd_bulkheads(a) -> int:
    """Create transverse bulkheads at the given X positions."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    xs = [float(v) for v in (a.x or "").split(",") if v.strip()]
    ys = [float(v) for v in (a.y or "").split(",") if v.strip()]
    if not xs and not ys:
        raise SystemExit("give --x and/or --y positions")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"bulkheads_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_bulkheads{src.suffix}")
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    ident = a.start_id
    idx = 0
    for x in xs:
        idx += 1
        name = f"{a.prefix}{idx:02d}"
        print(f"bulkhead : {name} X={x:g} id={ident}")
        if not _bulkhead_new(hwnd, ident, name, x, "X"):
            D.close_fsurf()
            return 1
        ident += 1
    idx = 0
    for y in ys:
        idx += 1
        name = f"{a.prefix_y}{idx:02d}"
        print(f"bulkhead : {name} Y={y:g} id={ident}"
              + (" (symmetrical)" if a.symmetrical else ""))
        if not _bulkhead_new(hwnd, ident, name, y, "Y", a.symmetrical):
            D.close_fsurf()
            return 1
        ident += 1

    expected = len(xs) + (2 * len(ys) if a.symmetrical else len(ys))
    count = _bulkhead_count(hwnd)
    print(f"bulkheads: {count if count is not None else '?'} in model "
          f"(expected >= {expected})")
    ok = count is not None and count >= expected
    if not ok:
        print("bulkhead count check failed", file=sys.stderr)

    saved = _save_model(hwnd, model, suffix="_bulkheads")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"saved    : {out} ({out.stat().st_size} bytes)")
    if not a.keep_open:
        D.close_fsurf()
    return 0 if ok else 1


_DECK_TYPE_BY_ID = {1: "Main", 9: "Double-bottom", 11: "Forecastle",
                     12: "Bridge", 13: "Poop-deck"}


def _combo_for_label(hwnd: int, label: str):
    d = G._app_window(hwnd, "uia")
    lab = next((c for c in d.descendants(control_type="Text")
                if (c.window_text() or "").strip() == label), None)
    if lab is None:
        return None
    top, right = lab.rectangle().top, lab.rectangle().right
    combos = [c for c in d.descendants(control_type="ComboBox")
              if abs(c.rectangle().top - top) <= 8
              and c.rectangle().left >= right - 2]
    return combos[0] if combos else None


def _pick_combo_item(hwnd: int, label: str, item: str) -> bool:
    combo = _combo_for_label(hwnd, label)
    if combo is None:
        print(f"deck: combo {label!r} not found", file=sys.stderr)
        return False
    r = combo.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    end = time.time() + 2.0
    popups = []
    while time.time() < end and not popups:
        popups = [w for w in G.windows() if w.get("class") == "QPopup"]
        if not popups:
            time.sleep(0.05)
    for w in popups:
        try:
            dd = G._app_window(w["hwnd"], "uia")
            for c in dd.descendants(control_type="ListItem"):
                txt = (c.window_text() or "").strip()
                if txt.lower() == item.lower() or item.lower() in txt.lower():
                    cr = c.rectangle()
                    pyautogui.click((cr.left + cr.right) // 2,
                                    (cr.top + cr.bottom) // 2)
                    time.sleep(0.3)
                    return True
        except Exception:  # noqa: BLE001
            pass
    pyautogui.press("esc")
    print(f"deck: item {item!r} not in {label!r}", file=sys.stderr)
    return False


def _camber_field(hwnd: int, label: str):
    """Edit control on the same row as a Text label such as 'L' or 'H'."""
    d = G._app_window(hwnd, "uia")
    lab = next((c for c in d.descendants(control_type="Text")
                if (c.window_text() or "").strip() == label), None)
    if lab is None:
        return None
    lr = lab.rectangle()
    edits = [c for c in d.descendants(control_type="Edit")
             if abs(c.rectangle().top - lr.top) <= 8
             and c.rectangle().left >= lr.right - 2]
    return edits[0] if edits else None


def _trace_table(dlg: int):
    """Return (headers, data items) of the Traces table in the Deck dialog."""
    d = G._app_window(dlg, "uia")
    tbl = next((c for c in d.descendants(control_type="Table")), None)
    if tbl is None:
        return [], []
    headers = [(c.window_text() or "").strip()
               for c in tbl.descendants(control_type="Header")]
    items = [c for c in tbl.descendants(control_type="DataItem")]
    items.sort(key=lambda c: (round(c.rectangle().top / 10), c.rectangle().left))
    return headers, items


def _trace_rows(dlg: int):
    headers, items = _trace_table(dlg)
    n = len(headers) or 1
    return headers, [items[i * n:(i + 1) * n] for i in range(len(items) // n)]


def _ctrl_number(ctrl):
    """First number shown by a UIA control ('12.500  m' -> 12.5)."""
    text = ""
    for getter in ("get_value", "window_text"):
        try:
            text = getattr(ctrl, getter)() or ""
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            break
    text = text.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def _check_number(ctrl, want: float, tol: float = 1e-3) -> bool:
    got = _ctrl_number(ctrl)
    return got is not None and abs(got - want) <= tol


def _edit_cell(ctrl, value, retries: int = 1) -> bool:
    """Qt table cell: click, F2, replace text, Enter; verify and retry once."""
    if ctrl is None:
        return False
    for _attempt in range(retries + 1):
        r = ctrl.rectangle()
        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(0.3)
        pyautogui.press("f2")
        time.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        pyperclip.copy(str(value))
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.45)
        try:
            want = float(str(value).replace(",", "."))
        except ValueError:
            return True
        if _check_number(ctrl, want):
            return True
    print(f"deck: cell edit did not stick ({value!r}, got "
          f"{_ctrl_number(ctrl)})", file=sys.stderr)
    return False


def _set_deck_traces(dlg: int, trace_l, traces, trace_l2=None) -> bool:
    """Fill the Traces table: flat halfbreadth + optional extra discontinuities.

    traces: list of (x, z_relative, l[, l2]) extra rows in ascending X.
    Tables without a "Z relative" column (Upper-Tanks) take (x, l) rows.
    """
    headers, rows = _trace_rows(dlg)
    if not rows:
        print("deck: traces table not found", file=sys.stderr)
        return False
    col = {h.lower(): i for i, h in enumerate(headers)}
    has_z = "z relative" in col

    def cell(row, key):
        i = col.get(key)
        if i is None or i >= len(row):
            return None
        return row[i]

    def norm(spec):
        """(x, z_or_None, l, l2_or_None) for either table shape."""
        if has_z:
            return (spec[0], spec[1], spec[2],
                    spec[3] if len(spec) > 3 else None)
        return spec[0], None, spec[-1], None

    if trace_l is not None:
        for row in rows:
            if not _edit_cell(cell(row, "l"), f"{trace_l:g}"):
                return False
    if trace_l2 is not None:
        for row in rows:
            if not _edit_cell(cell(row, "l2"), f"{trace_l2:g}"):
                return False
    if traces:
        # extra discontinuity rows; the two end rows stay as trimmed by the hull
        for spec in traces:
            x, z, l, l2 = norm(spec)
            if not D.click_button(dlg, "Add", timeout=5):
                print("deck: Add trace not found", file=sys.stderr)
                return False
            time.sleep(0.9)
            headers, rows = _trace_rows(dlg)
            row = rows[-1]
            ok = _edit_cell(cell(row, "x"), f"{x:g}")
            if z is not None:
                ok = _edit_cell(cell(row, "z relative"), f"{z:g}") and ok
            ok = _edit_cell(cell(row, "l"), f"{l:g}") and ok
            if l2 is not None:
                ok = _edit_cell(cell(row, "l2"), f"{l2:g}") and ok
            if not ok:
                return False

    # read back what the dialog actually accepted
    headers, rows = _trace_rows(dlg)
    ok = True
    if trace_l is not None:
        for i, row in enumerate(rows[:2], 1):
            if not _check_number(cell(row, "l"), trace_l):
                print(f"deck: trace row {i} L read back as "
                      f"{_ctrl_number(cell(row, 'l'))} (wanted {trace_l:g})",
                      file=sys.stderr)
                ok = False
    if trace_l2 is not None:
        for i, row in enumerate(rows[:2], 1):
            if not _check_number(cell(row, "l2"), trace_l2):
                print(f"deck: trace row {i} L2 read back as "
                      f"{_ctrl_number(cell(row, 'l2'))} (wanted {trace_l2:g})",
                      file=sys.stderr)
                ok = False
    if traces:
        for i, (row, spec) in enumerate(zip(rows[2:], traces), 3):
            x, z, l, l2 = norm(spec)
            good = (_check_number(cell(row, "x"), x)
                    and _check_number(cell(row, "l"), l))
            if z is not None:
                good = good and _check_number(cell(row, "z relative"), z)
            if l2 is not None:
                good = good and _check_number(cell(row, "l2"), l2)
            if not good:
                print(f"deck: trace row {i} read back as X="
                      f"{_ctrl_number(cell(row, 'x'))}"
                      + (f" Z={_ctrl_number(cell(row, 'z relative'))}"
                         if z is not None else "")
                      + f" L={_ctrl_number(cell(row, 'l'))}"
                      + (f" L2={_ctrl_number(cell(row, 'l2'))}" if l2 is not None else "")
                      + f" (wanted {x:g}"
                      + (f"/{z:g}" if z is not None else "")
                      + f"/{l:g}"
                      + (f"/{l2:g}" if l2 is not None else "") + ")",
                      file=sys.stderr)
                ok = False
    return ok


def _deck_new(hwnd: int, ident: int, name: str, height: float,
              deck_type: str, camber: str | None,
              camber_l=None, camber_h=None, trace_l=None,
              traces=None, description=None,
              camber_l2=None, camber_h2=None, trace_l2=None,
              camber_alpha=None) -> bool:
    UI.menu_click(G, hwnd, "Structure", (400, 54))
    UI.menu_click(G, hwnd, "Decks", (400, 240), popup_first=True)
    UI.menu_click(G, hwnd, "New deck", (780, 240), popup_first=True)
    dlg = D.find_hwnd("Deck", exact=True, timeout=15)
    if dlg is None:
        print("new deck: dialog not found", file=sys.stderr)
        return False
    G._focus(dlg)
    time.sleep(0.8)
    if not _pick_combo_item(dlg, "Type of deck:", deck_type):
        return False
    if not _set_edit(_labeled_edit_in(dlg, "Identifier:"), ident):
        print("new deck: Identifier not found", file=sys.stderr)
        return False
    _set_edit(_labeled_edit_in(dlg, "Name:"), name)
    if description:
        _set_edit(_labeled_edit_in(dlg, "Description:"), description)
    if height is not None:
        if not _set_edit(_labeled_edit_in(dlg, "Base height ="), f"{height:g}"):
            print("new deck: Base height not found", file=sys.stderr)
            return False
    # Parametric deck ON
    for c in G._app_window(dlg, "uia").descendants(control_type="CheckBox"):
        if (c.window_text() or "").strip() == "Parametric deck":
            try:
                if not bool(c.iface_toggle.CurrentToggleState):
                    c.click_input()
            except Exception:  # noqa: BLE001
                c.click_input()
            time.sleep(0.3)
            break
    if camber:
        # Upper-Tanks pins Limit with = External Hull 0 and hides the camber combo
        _pick_combo_item(dlg, "Limit with:", "External Hull")
        _pick_combo_item(dlg, "Type of camber:", camber)
    fields = [("L", camber_l), ("H", camber_h),
              ("L2", camber_l2), ("H2", camber_h2),
              ("Alpha", camber_alpha)]
    fields = [(lab, val) for lab, val in fields if val is not None]
    if fields:
        # the L/H fields only exist for sloped cambers; wait for the relayout
        end = time.time() + 8
        ctrls = {}
        while time.time() < end:
            for lab, _val in fields:
                if lab not in ctrls:
                    c = _camber_field(dlg, lab)
                    if c is not None:
                        ctrls[lab] = c
            if len(ctrls) == len(fields):
                break
            time.sleep(0.3)
        for lab, val in fields:
            c = ctrls.get(lab)
            if c is None:
                print(f"deck: camber {lab} field not found ({camber})",
                      file=sys.stderr)
                return False
            _set_edit(c, f"{val:g}")
            if not _check_number(c, val):
                print(f"deck: camber {lab} read back as {_ctrl_number(c)} "
                      f"(wanted {val:g})", file=sys.stderr)
                return False
    if trace_l is not None or trace_l2 is not None or traces:
        if not _set_deck_traces(dlg, trace_l, traces, trace_l2):
            return False
    if not D.click_button(dlg, "Done", timeout=5):
        print("new deck: Done not found", file=sys.stderr)
        return False
    end = time.time() + 30
    while time.time() < end:
        if D.find_hwnd("Deck", exact=True, timeout=0.2) is None:
            time.sleep(0.8)
            return True
        # dismiss stray warnings/information dialogs
        for w in G.windows():
            if w.get("title") in ("Warning", "Information", "Error"):
                D.click_button(w["hwnd"], "Ok")
                time.sleep(0.3)
        time.sleep(0.4)
    print("new deck: dialog did not close", file=sys.stderr)
    return False


def _parse_hopper_traces(specs):
    """Parse repeated 'X:Z:L[:L2]' hopper discontinuities, sorted by X."""
    out = []
    for spec in (specs or []):
        parts = spec.split(":")
        if len(parts) not in (3, 4):
            raise SystemExit(f"--hopper-trace expects X:Z:L[:L2], got {spec!r}")
        out.append(tuple(float(v) for v in parts))
    out.sort(key=lambda t: t[0])
    return out


def _upper_tank_params(text):
    """Parse 'L,H,ALPHA' for the Upper-Tanks deck."""
    if not text:
        return None
    parts = [float(v) for v in text.split(",") if v.strip()]
    if len(parts) != 3:
        raise SystemExit("--upper-tank expects 'L,H,ALPHA', e.g. 8,3.3,45")
    return tuple(parts)


def _add_upper_tank(hwnd: int, params) -> bool:
    l, h, alpha = params
    print(f"deck     : UpperTank id=10 L={l:g} H={h:g} alpha={alpha:g}")
    return _deck_new(hwnd, 10, "UpperTank", None, "Upper-Tanks", None,
                     camber_l=l, camber_h=h, camber_alpha=alpha, trace_l=l)


def _select_deck_rows(dlg: int):
    """Rows of Select Decks as (name, id, name-cell rect)."""
    d = G._app_window(dlg, "uia")
    cells = []
    for c in d.descendants(control_type="TreeItem"):
        try:
            t = (c.window_text() or "").strip()
            r = c.rectangle()
            if t:
                cells.append((t, (r.left, r.top, r.right, r.bottom)))
        except Exception:  # noqa: BLE001
            pass
    groups = {}
    for t, r in cells:
        groups.setdefault(round((r[1] + r[3]) / 2 / 5), []).append((t, r))
    rows = []
    for _key, grp in sorted(groups.items()):
        grp.sort(key=lambda x: x[1][0])
        name = grp[0][0]
        ident = None
        for t, _r in grp[1:]:
            if t.isdigit():
                ident = int(t)
                break
        rows.append((name, ident, grp[0][1]))
    return rows


def _delete_parts(hwnd: int, menu: str, item: str, title: str,
                  names, ids, prefixes=()) -> bool:
    """Delete structural parts whose name/id matches; keep the rest.

    The Select dialog works as a working list: All puts every part in it and
    the dialog's Delete button removes the highlighted row from that list, so
    we remove every row we want to keep and press Done.
    """
    UI.menu_click(G, hwnd, "Structure", (400, 54))
    UI.menu_click(G, hwnd, menu, (400, 240), popup_first=True)
    UI.menu_click(G, hwnd, item, (780, 240), popup_first=True)
    dlg = D.find_hwnd(title, exact=True, timeout=10)
    if dlg is None:
        return True  # no parts at all
    G._focus(dlg)
    time.sleep(0.8)
    D.click_button(dlg, "All", timeout=5)
    time.sleep(1.0)

    def wanted(row):
        return (row[0] in names
                or any(row[0].startswith(p) for p in prefixes)
                or (row[1] is not None and row[1] in ids))

    target = 0
    for _ in range(60):
        rows = _select_deck_rows(dlg)
        keep = [r for r in rows if wanted(r)]
        target = len(keep)
        if len(rows) == target:
            break
        victim = next(r for r in rows if not wanted(r))
        l, t, rgt, b = victim[2]
        pyautogui.click((l + rgt) // 2, (t + b) // 2)
        time.sleep(0.4)
        if not D.click_button(dlg, "Delete", timeout=3):
            print("replace: Delete button not found", file=sys.stderr)
            D.click_button(dlg, "Cancel")
            return False
        time.sleep(0.6)
    else:
        print(f"replace: could not narrow the {title} list", file=sys.stderr)
        D.click_button(dlg, "Cancel")
        return False

    rows = _select_deck_rows(dlg)
    got = sum(1 for r in rows if wanted(r))
    if got != target or target == 0:
        if target == 0:
            print(f"replace: no existing part matched in {title}; nothing deleted")
        else:
            print(f"replace: selected {got} of {target} matching parts "
                  f"in {title}", file=sys.stderr)
        D.click_button(dlg, "Cancel")
        return target == 0
    D.click_button(dlg, "Done", timeout=5)
    end = time.time() + 10
    while time.time() < end and D.find_hwnd(title, exact=True, timeout=0.2) is not None:
        for w in G.windows():
            if w.get("title") in ("Please confirm", "Warning", "Information", "Error"):
                D.click_button(w["hwnd"], "Yes") or D.click_button(w["hwnd"], "Ok")
                time.sleep(0.4)
        time.sleep(0.3)
    print(f"replace  : deleted {target} part(s) from {title}")
    return True


def _delete_decks(hwnd: int, names, ids) -> bool:
    return _delete_parts(hwnd, "Decks", "Delete decks", "Select Decks",
                         names, ids)


def _deck_count(hwnd: int):
    UI.menu_click(G, hwnd, "Structure", (400, 54))
    UI.menu_click(G, hwnd, "Decks", (400, 240), popup_first=True)
    UI.menu_click(G, hwnd, "Delete decks", (780, 240), popup_first=True)
    sel = D.find_hwnd("Select Decks", exact=True, timeout=10)
    if sel is None:
        return None
    G._focus(sel)
    D.click_button(sel, "All", timeout=5)
    time.sleep(0.8)
    count = None
    for c in G._app_window(sel, "uia").descendants(control_type="Text"):
        m = re.match(r"(\d+)\s+part\(s\)\s+selected",
                     (c.window_text() or "").strip())
        if m:
            count = int(m.group(1))
            break
    D.click_button(sel, "Cancel")
    time.sleep(0.8)
    return count


def cmd_decks(a) -> int:
    """Create parametric decks (main deck, inner bottom, forecastle, ...)."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    specs = []
    for spec in a.deck:
        parts = spec.split(":")
        if len(parts) < 3:
            raise SystemExit(
                "--deck expects ID:NAME:HEIGHT[:TYPE[:CAMBER[:L[:H[:L2[:H2]]]]]], "
                f"got {spec!r}")
        ident = int(parts[0])
        name = parts[1]
        height = float(parts[2])
        deck_type = parts[3] if len(parts) > 3 else _DECK_TYPE_BY_ID.get(ident, "Normal")
        camber = parts[4] if len(parts) > 4 else (a.camber or "Plane")
        camber_l = float(parts[5]) if len(parts) > 5 and parts[5] else a.camber_l
        camber_h = float(parts[6]) if len(parts) > 6 and parts[6] else a.camber_h
        camber_l2 = float(parts[7]) if len(parts) > 7 and parts[7] else a.camber_l2
        camber_h2 = float(parts[8]) if len(parts) > 8 and parts[8] else a.camber_h2
        specs.append((ident, name, height, deck_type, camber,
                      camber_l, camber_h, camber_l2, camber_h2))
    traces = {}
    for spec in (a.deck_trace or []):
        parts = spec.split(":")
        if len(parts) not in (4, 5):
            raise SystemExit(
                f"--deck-trace expects ID:X:Z:L[:L2], got {spec!r}")
        traces.setdefault(int(parts[0]), []).append(
            tuple(float(v) for v in parts[1:]))
    for ident in traces:
        traces[ident].sort(key=lambda t: t[0])
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"decks_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_decks{src.suffix}")
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    for ident, name, height, deck_type, camber, cl, ch, cl2, ch2 in specs:
        print(f"deck     : {name} id={ident} type={deck_type} z={height:g} "
              f"camber={camber}"
              + (f" L={cl:g} H={ch:g}" if cl is not None and ch is not None else "")
              + (f" L2={cl2:g} H2={ch2:g}"
                 if cl2 is not None and ch2 is not None else ""))
        if not _deck_new(hwnd, ident, name, height, deck_type, camber,
                         camber_l=cl, camber_h=ch,
                         camber_l2=cl2, camber_h2=ch2,
                         trace_l=a.flat_halfbreadth,
                         trace_l2=a.flat_halfbreadth2,
                         traces=traces.get(ident)):
            D.close_fsurf()
            return 1

    count = _deck_count(hwnd)
    print(f"decks    : {count if count is not None else '?'} in model")
    ok = count is not None and count >= len(specs)
    if not ok:
        print("deck count check failed", file=sys.stderr)

    saved = _save_model(hwnd, model, suffix="_decks")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"saved    : {out} ({out.stat().st_size} bytes)")
    if not a.keep_open:
        D.close_fsurf()
    return 0 if ok else 1


def cmd_inner_shell(a) -> int:
    """One session: main deck (optional) + inner bottom + symmetrical inner sides."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    xs = [float(v) for v in (a.x or "").split(",") if v.strip()]
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"inner_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_inner{src.suffix}")
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    if a.replace:
        ids, names = {9}, {"InnerBottom"}
        if a.main_deck_z:
            ids.add(1)
            names.add("MainDeck")
        if a.upper_tank:
            ids.add(10)
            names.add("UpperTank")
        _delete_decks(hwnd, names, ids)
        _delete_parts(hwnd, "Bulkheads", "Delete bulkheads",
                      "Select Bulkheads", set(), set(),
                      prefixes=("BHD-", "INNER-01"))

    if a.main_deck_z:
        print(f"deck     : MainDeck id=1 z={a.main_deck_z:g}")
        if not _deck_new(hwnd, 1, "MainDeck", a.main_deck_z, "Main", "Plane"):
            D.close_fsurf()
            return 1
    slope = [float(v) for v in (a.hopper or "").split(",") if v.strip()]
    if slope and len(slope) != 2:
        raise SystemExit("--hopper expects 'L,H', e.g. 3.0,1.5")
    slope2 = [float(v) for v in (a.hopper2 or "").split(",") if v.strip()]
    if slope2 and len(slope2) != 2:
        raise SystemExit("--hopper2 expects 'L2,H2'")
    if slope2 and a.flat_halfbreadth2 is None:
        raise SystemExit("--hopper2 needs --flat-halfbreadth2")
    camber = ("Trapezoidal with two knucles" if slope2
              else "Trapezoidal" if slope else "Plane")
    hopper_traces = _parse_hopper_traces(a.hopper_trace)
    print(f"deck     : InnerBottom id=9 z={a.bottom_z:g}"
          + (f" hopper L={slope[0]:g} H={slope[1]:g} flat=±{a.flat_halfbreadth:g}"
             if slope else "")
          + (f" / L2={slope2[0]:g} H2={slope2[1]:g} flat2=±{a.flat_halfbreadth2:g}"
             if slope2 else ""))
    for spec in hopper_traces:
        print("trace    : " + " ".join(
            f"{k}={v:g}" for k, v in zip(("X", "Z", "L", "L2"), spec)))
    if not _deck_new(hwnd, 9, "InnerBottom", a.bottom_z, "Double-bottom",
                     camber,
                     camber_l=slope[0] if slope else None,
                     camber_h=slope[1] if slope else None,
                     camber_l2=slope2[0] if slope2 else None,
                     camber_h2=slope2[1] if slope2 else None,
                     trace_l=a.flat_halfbreadth if slope else None,
                     trace_l2=a.flat_halfbreadth2 if slope2 else None,
                     traces=hopper_traces or None):
        D.close_fsurf()
        return 1
    ut = _upper_tank_params(a.upper_tank)
    if ut and not _add_upper_tank(hwnd, ut):
        D.close_fsurf()
        return 1

    ident = 101
    for x in xs:
        name = f"BHD-{xs.index(x) + 1:02d}"
        print(f"bulkhead : {name} X={x:g} id={ident}")
        if not _bulkhead_new(hwnd, ident, name, x, "X"):
            D.close_fsurf()
            return 1
        ident += 1
    print(f"bulkhead : INNER-01 Y={a.side_y:g} id={ident} (symmetrical)")
    if not _bulkhead_new(hwnd, ident, "INNER-01", a.side_y, "Y", True):
        D.close_fsurf()
        return 1

    decks = _deck_count(hwnd)
    bulkheads = _bulkhead_count(hwnd)
    print(f"decks    : {decks if decks is not None else '?'} in model")
    print(f"bulkheads: {bulkheads if bulkheads is not None else '?'} in model")
    want_decks = 1 + (1 if a.main_deck_z else 0) + (1 if ut else 0)
    want_bh = len(xs) + 2
    ok = (decks is not None and decks >= want_decks
          and bulkheads is not None and bulkheads >= want_bh)
    if not ok:
        print("inner shell count check failed", file=sys.stderr)

    saved = _save_model(hwnd, model, suffix="_inner")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"saved    : {out} ({out.stat().st_size} bytes)")
    if not a.keep_open:
        D.close_fsurf()
    return 0 if ok else 1


def cmd_hopper(a) -> int:
    """Create a Double-bottom deck with a Trapezoidal (hopper) camber."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    slope = [float(v) for v in (a.slope or "").split(",") if v.strip()]
    if len(slope) != 2:
        raise SystemExit("--slope expects 'L,H' (metres), e.g. 3.0,1.5")
    slope2 = [float(v) for v in (a.slope2 or "").split(",") if v.strip()]
    if slope2 and len(slope2) != 2:
        raise SystemExit("--slope2 expects 'L2,H2' (metres)")
    if slope2 and a.flat2 is None:
        raise SystemExit("--slope2 needs --flat2 (second horizontal half breadth)")
    traces = _parse_hopper_traces(a.trace)
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"hopper_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_hopper{src.suffix}")
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    if a.replace:
        _delete_decks(hwnd, {a.name}, {a.id})
    before = _deck_count(hwnd)
    camber = "Trapezoidal with two knucles" if slope2 else "Trapezoidal"
    print(f"deck     : {a.name} id={a.id} Double-bottom z={a.z:g} "
          f"flat=±{a.flat:g} slope L={slope[0]:g} H={slope[1]:g}"
          + (f" / L2={slope2[0]:g} H2={slope2[1]:g} flat2=±{a.flat2:g}"
             if slope2 else ""))
    for spec in traces:
        print("trace    : " + " ".join(
            f"{k}={v:g}" for k, v in zip(("X", "Z", "L", "L2"), spec)))
    if not _deck_new(hwnd, a.id, a.name, a.z, "Double-bottom", camber,
                     camber_l=slope[0], camber_h=slope[1],
                     camber_l2=slope2[0] if slope2 else None,
                     camber_h2=slope2[1] if slope2 else None,
                     trace_l=a.flat, trace_l2=a.flat2,
                     traces=traces or None):
        D.close_fsurf()
        return 1

    count = _deck_count(hwnd)
    print(f"decks    : {count if count is not None else '?'} in model"
          + (f" (was {before})" if before is not None else ""))
    ok = count is not None and (before is None or count == before + 1)
    if not ok:
        print("hopper deck count check failed", file=sys.stderr)

    saved = _save_model(hwnd, model, suffix="_hopper")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"saved    : {out} ({out.stat().st_size} bytes)")
    if not a.keep_open:
        D.close_fsurf()
    return 0 if ok else 1


def cmd_upper_tank(a) -> int:
    """Create an Upper-Tanks deck (topside tank) with its camber parameters."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"uppertank_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_uppertank{src.suffix}")
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    if a.replace:
        _delete_decks(hwnd, {a.name}, {a.id})
    before = _deck_count(hwnd)
    print(f"deck     : {a.name} id={a.id} Upper-Tanks "
          f"(base = Main deck) L={a.l:g} H={a.h:g} alpha={a.alpha:g}")
    if not _deck_new(hwnd, a.id, a.name, None, "Upper-Tanks", None,
                     camber_l=a.l, camber_h=a.h, camber_alpha=a.alpha,
                     trace_l=a.l):
        print("upper-tank: the model must already have a Main deck "
              "(Upper-Tanks uses 'Base height = Main deck'); its L/H/Alpha "
              "fields reset when no main deck exists", file=sys.stderr)
        D.close_fsurf()
        return 1

    count = _deck_count(hwnd)
    print(f"decks    : {count if count is not None else '?'} in model"
          + (f" (was {before})" if before is not None else ""))
    ok = count is not None and (before is None or count == before + 1)
    if not ok:
        print("upper-tank deck count check failed", file=sys.stderr)

    saved = _save_model(hwnd, model, suffix="_uppertank")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"saved    : {out} ({out.stat().st_size} bytes)")
    if not a.keep_open:
        D.close_fsurf()
    return 0 if ok else 1


def _make_offsets(hwnd: int, out_base: Path, timeout: float = 120.0):
    """File > Ship > Offset table in the current session -> .lis path."""
    exp = out_base.with_suffix(".lis")
    exp.unlink(missing_ok=True)
    pyautogui.press("escape")
    time.sleep(0.4)
    _menu_click(hwnd, "File", (57, 54))
    time.sleep(0.7)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(0.8)
    for _ in range(2):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.5)
    dlg = D.find_hwnd("Offset", exact=True, timeout=15)
    if dlg is None:
        print("offset table: dialog not found", file=sys.stderr)
        return None
    G._focus(dlg)
    time.sleep(0.5)
    if not _set_edit(_labeled_edit_in(dlg, "File name"), str(out_base)):
        print("offset table: File name field not found", file=sys.stderr)
        return None
    if not D.click_button(dlg, "Ok", timeout=5):
        print("offset table: Ok not found", file=sys.stderr)
        return None
    end = time.time() + timeout
    prev = None
    while time.time() < end:
        cand = exp if exp.exists() else None
        if cand is None:
            hits = sorted(out_base.parent.glob("*.lis"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            if hits and hits[0].stat().st_mtime > time.time() - 120:
                cand = hits[0]
        if cand is not None and cand.stat().st_size > 0:
            size = cand.stat().st_size
            if size == prev:
                return cand
            prev = size
        time.sleep(0.8)
    print("offset table: file not written", file=sys.stderr)
    return None


def cmd_workflow(a) -> int:
    """One-command AUTHOR workflow: transform, inner shell, verify, draw."""
    t0 = time.time()

    def mark(label):
        print(f"timing   : {label:<10s} {time.time() - t0:6.1f} s")

    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"workflow_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_workflow{src.suffix}")
    fnam = (a.fnam or src.stem[:4]).upper()
    if len(fnam) != 4:
        raise SystemExit("--fnam must be exactly 4 characters")
    sx = float(a.scale_x) if a.scale_x else float(a.lpp) / float(a.from_lpp)
    sy = float(a.scale_y) if a.scale_y else float(a.breadth) / float(a.from_breadth)
    xs = [float(v) for v in (a.x or "").split(",") if v.strip()]
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)
    print(f"model    : {model}")
    print(f"scale    : X x{sx:.6f}, Y x{sy:.6f}")

    if not a.keep_decks:
        if not _delete_structure(hwnd, "Decks", "Delete decks", "Select Decks"):
            D.close_fsurf()
            return 1
        print("decks    : deleted")
    if not a.keep_bulkheads:
        if not _delete_structure(hwnd, "Bulkheads", "Delete bulkheads",
                                 "Select Bulkheads"):
            D.close_fsurf()
            return 1
        print("bulkheads: deleted")
    mark("delete")
    if abs(sx - 1.0) > 1e-9 and not _plane_scale(hwnd, "YZ", sx, a.timeout):
        D.close_fsurf()
        return 1
    if abs(sy - 1.0) > 1e-9 and not _plane_scale(hwnd, "XZ", sy, a.timeout):
        D.close_fsurf()
        return 1
    print("scale    : applied")
    mark("scale")
    if not _build_ship(hwnd, fnam, f"{a.lpp:g}", f"{a.breadth:g}",
                       f"{a.draught:g}", f"{a.depth:g}"):
        print("Build Ship / Surface Validator failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    print("build    : ok")
    mark("build")
    if a.rebuild_frames:
        spacing = a.frame_spacing if a.frame_spacing else float(a.lpp) / max(1, a.frame_nmax)
        if not _define_frame_system(hwnd, a.frame_nmax, spacing):
            D.close_fsurf()
            return 1
        print(f"frames   : Nmax={a.frame_nmax}, spacing={spacing:.6g} m")
    mark("frames")

    if not a.no_inner:
        if a.main_deck_z and not _deck_new(hwnd, 1, "MainDeck", a.main_deck_z,
                                           "Main", "Plane"):
            D.close_fsurf()
            return 1
        slope = [float(v) for v in (a.hopper or "").split(",") if v.strip()]
        if slope and len(slope) != 2:
            raise SystemExit("--hopper expects 'L,H', e.g. 3.0,1.5")
        slope2 = [float(v) for v in (a.hopper2 or "").split(",") if v.strip()]
        if slope2 and len(slope2) != 2:
            raise SystemExit("--hopper2 expects 'L2,H2'")
        if slope2 and a.flat_halfbreadth2 is None:
            raise SystemExit("--hopper2 needs --flat-halfbreadth2")
        camber = ("Trapezoidal with two knucles" if slope2
                  else "Trapezoidal" if slope else "Plane")
        hopper_traces = _parse_hopper_traces(a.hopper_trace)
        for spec in hopper_traces:
            print("trace    : " + " ".join(
                f"{k}={v:g}" for k, v in zip(("X", "Z", "L", "L2"), spec)))
        if not _deck_new(hwnd, 9, "InnerBottom", a.bottom_z,
                         "Double-bottom", camber,
                         camber_l=slope[0] if slope else None,
                         camber_h=slope[1] if slope else None,
                         camber_l2=slope2[0] if slope2 else None,
                         camber_h2=slope2[1] if slope2 else None,
                         trace_l=a.flat_halfbreadth if slope else None,
                         trace_l2=a.flat_halfbreadth2 if slope2 else None,
                         traces=hopper_traces or None):
            D.close_fsurf()
            return 1
        if slope:
            print(f"hopper   : L={slope[0]:g} m, H={slope[1]:g} m, "
                  f"flat bottom ±{a.flat_halfbreadth:g} m")
        if slope2:
            print(f"hopper2  : L2={slope2[0]:g} m, H2={slope2[1]:g} m, "
                  f"second flat ±{a.flat_halfbreadth2:g} m")
        ut = _upper_tank_params(a.upper_tank)
        if ut and not _add_upper_tank(hwnd, ut):
            D.close_fsurf()
            return 1
        ident = 101
        for i, x in enumerate(xs, 1):
            if not _bulkhead_new(hwnd, ident, f"BHD-{i:02d}", x, "X"):
                D.close_fsurf()
                return 1
            ident += 1
        if not _bulkhead_new(hwnd, ident, "INNER-01", a.side_y, "Y", True):
            D.close_fsurf()
            return 1
        print(f"inner    : deck z={a.bottom_z:g}, side y=±{a.side_y:g}, "
              f"{len(xs)} transverse bulkhead(s)")
        mark("inner")

    saved = _save_model(hwnd, model, suffix="_workflow")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"saved    : {out} ({out.stat().st_size} bytes)")
    mark("save")

    rc = 0
    if a.hydro or a.expect:
        lis = _make_offsets(hwnd, workdir / "workflow_offsets", a.timeout)
        if lis is None:
            D.close_fsurf()
            return 1
        import foran_offsets as O
        data = O.parse_loftbook(lis)
        ts = [float(v) for v in (a.hydro or "9.83,10.27").split(",") if v.strip()]
        rows = O.hydrostatics(data, ts)
        for row in rows:
            print(f"T={row['draught']:6.2f} m  vol={row['volume']:10.1f} m3  "
                  f"Cb={row['cb']:.4f}  LCB(AP)={row['lcb_ap']:7.2f} m")
        if a.expect:
            lines, ok = O.compare(rows, a.expect, a.tol)
            for ln in lines:
                print(ln)
            print("check    : " + ("PASS" if ok else "FAIL"))
            rc = 0 if ok else 1
        mark("offsets")

    if a.draw_out:
        draw = Path(a.draw_out).expanduser().resolve()
        draw.parent.mkdir(parents=True, exist_ok=True)
        if not _lines_drawing(hwnd, draw, scale=a.draw_scale):
            D.close_fsurf()
            return 1
        print(f"lines DXF: {draw} ({draw.stat().st_size} bytes)")
        if a.frame_out:
            from types import SimpleNamespace
            import foran_dxf as DX
            ns = SimpleNamespace(
                inp=str(draw), out=str(Path(a.frame_out).expanduser().resolve()),
                sheet="A1", portrait=False, fit=False, units_per_mm=0.0001,
                template=a.frame_template, template_units_per_mm=1.0,
                template_margin=10.0, template_area=a.frame_area or "auto",
                project=a.project, title=a.title, drawing_no=a.drawing_no,
                scale_text=a.scale_text, designer=a.designer,
                checker=a.checker, approver=a.approver, company=a.company,
                date=dt.date.today().strftime("%Y-%m-%d"),
                scale=None, scale_den=None)
            if DX.cmd_frame(ns) != 0:
                rc = 1
            print(f"framed   : {a.frame_out}")
    mark("draw")

    if not a.keep_open:
        D.close_fsurf()
    return rc


def cmd_transform(a) -> int:
    """Mother-ship workflow: Plane Scale X/Y -> Build Ship -> save (+ lines)."""
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" /
        f"transform_{dt.datetime.now():%Y%m%d-%H%M%S}")
    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / f"{src.stem}_work{src.suffix}"
    shutil.copy2(src, model)
    out = (Path(a.out).expanduser().resolve() if a.out
           else workdir / f"{src.stem}_transform{src.suffix}")
    fnam = (a.fnam or src.stem[:4]).upper()
    if len(fnam) != 4:
        raise SystemExit("--fnam must be exactly 4 characters (e.g. SAMPLE)")

    lpp0 = float(a.from_lpp)
    b0 = float(a.from_breadth)
    sx = float(a.scale_x) if a.scale_x else float(a.lpp) / lpp0
    sy = float(a.scale_y) if a.scale_y else float(a.breadth) / b0
    print(f"model    : {model}")
    print(f"scale    : X x{sx:.6f} (YZ / X=0), Y x{sy:.6f} (XZ / Y=0)")

    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2

    if not _open_fsurf_model(model, workdir):
        print("FSURF launch/open failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        D.close_fsurf()
        return 1
    hwnd = win["hwnd"]
    G._focus(hwnd)
    time.sleep(2)

    if not a.keep_decks:
        if not _delete_structure(hwnd, "Decks", "Delete decks",
                                 "Select Decks"):
            print("could not delete the old decks", file=sys.stderr)
            D.close_fsurf()
            return 1
        print("decks    : deleted")
    if not a.keep_bulkheads:
        if not _delete_structure(hwnd, "Bulkheads", "Delete bulkheads",
                                 "Select Bulkheads"):
            print("could not delete the old bulkheads", file=sys.stderr)
            D.close_fsurf()
            return 1
        print("bulkheads: deleted")

    if abs(sx - 1.0) > 1e-9:
        if not _plane_scale(hwnd, "YZ", sx, a.timeout):
            D.close_fsurf()
            return 1
        print("scale X  : applied")
    if abs(sy - 1.0) > 1e-9:
        if not _plane_scale(hwnd, "XZ", sy, a.timeout):
            D.close_fsurf()
            return 1
        print("scale Y  : applied")

    if not _build_ship(hwnd, fnam, f"{a.lpp:g}", f"{a.breadth:g}",
                       f"{a.draught:g}", f"{a.depth:g}"):
        print("Build Ship / Surface Validator failed", file=sys.stderr)
        D.close_fsurf()
        return 1
    print("build    : ok")

    if a.rebuild_frames:
        spacing = a.frame_spacing if a.frame_spacing else float(a.lpp) / max(1, a.frame_nmax)
        print(f"frames   : Nmax={a.frame_nmax}, spacing={spacing:.6g} m")
        if not _define_frame_system(hwnd, a.frame_nmax, spacing):
            print("frame system not defined", file=sys.stderr)
            D.close_fsurf()
            return 1
        print("frames   : defined")

    saved = _save_model(hwnd, model, suffix="_transform")
    if saved is None:
        D.close_fsurf()
        return 1
    if saved != out:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, out)
    print(f"transformed: {out} ({out.stat().st_size} bytes)")

    if a.draw_out:
        draw = Path(a.draw_out).expanduser().resolve()
        draw.parent.mkdir(parents=True, exist_ok=True)
        if not _lines_drawing(hwnd, draw):
            print("lines DXF not produced", file=sys.stderr)
            D.close_fsurf()
            return 1
        print(f"lines DXF: {draw} ({draw.stat().st_size} bytes)")

    if not a.keep_open:
        D.close_fsurf()
    return 0


def cmd_build(a) -> int:
    src = Path(a.brep).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"shell not found: {src}")
    if not a.fnam or len(a.fnam) != 4:
        raise SystemExit("--fnam must be exactly 4 characters (e.g. TEST)")
    workdir = Path(a.workdir).expanduser().resolve() if a.workdir else (
        Path.cwd() / "_foran_work" / "fsf" / dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    workdir.mkdir(parents=True, exist_ok=True)
    if D.find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first.", file=sys.stderr)
        return 2
    start = time.time()
    proc = _launch_fsurf(workdir)
    win = _wait_main(40)
    if win is None:
        print("FSURF main window not found", file=sys.stderr)
        return 1
    hwnd = win["hwnd"]
    try:
        G._focus(hwnd)
        time.sleep(2)
        # New ship (clear)
        _menu_click(hwnd, "File", (57, 54))
        _menu_click(hwnd, "New", (100, 91))
        ns = D.find_hwnd("New Ship", timeout=5)
        if ns is not None:
            D.click_button(ns, "Yes")
            time.sleep(2)
        if not _import_brep(hwnd, workdir, src):
            return 1
        mw = _open_manager(hwnd)
        if mw is None:
            print("Manager window not found", file=sys.stderr)
            return 1
        if not _assign_patches(mw):
            return 1
        if not _build_ship(hwnd, a.fnam, str(a.lpp), str(a.breadth), str(a.draught), str(a.depth)):
            print("Build Ship / Surface Validator failed", file=sys.stderr)
            return 1
        # locate the written forms file
        end = time.time() + a.timeout
        fsf = None
        while time.time() < end:
            hits = [Path(p) for p in glob.glob(str(workdir / "*.fsf"))]
            hits = [p for p in hits if p.stat().st_mtime >= start - 2]
            if hits:
                fsf = max(hits, key=lambda p: p.stat().st_mtime)
                break
            time.sleep(1)
        if fsf is None:
            print("no .fsf written", file=sys.stderr)
            return 1
        if not a.no_frames:
            spacing = a.frame_spacing if a.frame_spacing else a.lpp / max(1, a.frame_nmax)
            print(f"frame sys : Nmax={a.frame_nmax}, spacing={spacing:.6g} m")
            if _define_frame_system(hwnd, a.frame_nmax, spacing):
                print("frame sys : defined")
                saved = _save_model(hwnd, fsf)
                if saved:
                    fsf = saved
                    print(f"frame sys : saved to {saved.name} ({saved.stat().st_size} bytes)")
                else:
                    print("frame sys : could not save FSF (frames kept in session only)",
                          file=sys.stderr)
            else:
                print("frame sys : not defined", file=sys.stderr)
        out = Path(a.out).expanduser().resolve() if a.out else fsf
        if out != fsf:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fsf, out)
        print(f"built FSF : {out} ({out.stat().st_size} bytes)")
        if a.draw_out:
            draw = Path(a.draw_out).expanduser().resolve()
            draw.parent.mkdir(parents=True, exist_ok=True)
            if _lines_drawing(hwnd, draw):
                print(f"lines DXF : {draw} ({draw.stat().st_size} bytes)")
            else:
                print("lines DXF : not produced", file=sys.stderr)
                if not a.keep_open:
                    D.close_fsurf()
                return 1
        print(f"workdir   : {workdir}")
        if not a.keep_open:
            D.close_fsurf()
        return 0
    finally:
        if not a.keep_open:
            D.close_fsurf()

def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("offsets",
                       help="File > Ship > Offset table -> .lis (+ hydrostatics)")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--out", required=True,
                   help="output base path; FSURF writes <stem>.lis")
    p.add_argument("--hydro", help="comma list of draughts to integrate, e.g. 9.83,10.27")
    p.add_argument("--expect",
                   help="targets T:volume[:Cb], e.g. 9.83:42514,10.27:44644")
    p.add_argument("--tol", type=float, default=0.005,
                   help="relative vol / absolute Cb tolerance (default 0.005)")
    p.add_argument("--workdir")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_offsets)

    p = sub.add_parser("workflow",
                       help="one command: transform + inner shell + verify + draw")
    p.add_argument("--fsf", required=True, help="mother .fsf (copied)")
    p.add_argument("--lpp", type=float, required=True)
    p.add_argument("--breadth", type=float, required=True)
    p.add_argument("--depth", type=float, default=14.8)
    p.add_argument("--draught", type=float, default=9.83)
    p.add_argument("--from-lpp", type=float, default=172.0)
    p.add_argument("--from-breadth", type=float, default=28.8)
    p.add_argument("--scale-x", type=float)
    p.add_argument("--scale-y", type=float)
    p.add_argument("--fnam", help="4-character ship name (default from file)")
    p.add_argument("--keep-decks", action="store_true")
    p.add_argument("--keep-bulkheads", action="store_true")
    p.add_argument("--rebuild-frames", action="store_true")
    p.add_argument("--frame-nmax", type=int, default=100)
    p.add_argument("--frame-spacing", type=float)
    p.add_argument("--no-inner", action="store_true",
                   help="skip inner bottom / sides / decks")
    p.add_argument("--main-deck-z", type=float)
    p.add_argument("--bottom-z", type=float, default=2.0)
    p.add_argument("--side-y", type=float, default=12.5)
    p.add_argument("--hopper", metavar="L,H",
                   help="hopper slope on the inner bottom (L,H in metres)")
    p.add_argument("--hopper2", metavar="L2,H2",
                   help="second knuckle slope (Trapezoidal with two knuckles)")
    p.add_argument("--flat-halfbreadth", type=float, default=12.5,
                   help="flat inner-bottom half breadth for --hopper (default 12.5)")
    p.add_argument("--flat-halfbreadth2", type=float,
                   help="second flat half breadth for --hopper2")
    p.add_argument("--hopper-trace", action="append", metavar="X:Z:L[:L2]",
                   help="extra inner-bottom discontinuity (repeatable)")
    p.add_argument("--upper-tank", metavar="L,H,ALPHA",
                   help="also build the Upper-Tanks deck (needs a main deck)")
    p.add_argument("--x", help="transverse bulkhead X positions")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--hydro", default="9.83,10.27")
    p.add_argument("--expect", help="T:vol[:Cb] targets for the hydro check")
    p.add_argument("--tol", type=float, default=0.005)
    p.add_argument("--draw-out", help="also write a lines DXF")
    p.add_argument("--draw-scale", type=float, default=100.0,
                   help="Lines Drawing scale field (default 100)")
    p.add_argument("--frame-template")
    p.add_argument("--frame-out")
    p.add_argument("--frame-area")
    p.add_argument("--project", default="SAMPLE SHIP")
    p.add_argument("--title", default="型线图")
    p.add_argument("--drawing-no", default="EXAMPLE-010-04")
    p.add_argument("--scale-text", default="1:100")
    p.add_argument("--designer", default="")
    p.add_argument("--checker", default="")
    p.add_argument("--approver", default="")
    p.add_argument("--company", default="YOUR COMPANY")
    p.add_argument("--workdir")
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_workflow)

    p = sub.add_parser("inner-shell",
                       help="main deck + inner bottom + symmetrical inner sides")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--main-deck-z", type=float,
                   help="main deck height (omit to keep the existing deck)")
    p.add_argument("--bottom-z", type=float, default=2.0,
                   help="inner bottom height (default 2.0)")
    p.add_argument("--side-y", type=float, default=12.5,
                   help="inner side half-breadth (default 12.5)")
    p.add_argument("--hopper", metavar="L,H",
                   help="hopper slope on the inner bottom (L,H in metres)")
    p.add_argument("--hopper2", metavar="L2,H2",
                   help="second knuckle slope (Trapezoidal with two knuckles)")
    p.add_argument("--flat-halfbreadth", type=float, default=12.5,
                   help="flat inner-bottom half breadth for --hopper (default 12.5)")
    p.add_argument("--flat-halfbreadth2", type=float,
                   help="second flat half breadth for --hopper2")
    p.add_argument("--hopper-trace", action="append", metavar="X:Z:L[:L2]",
                   help="extra inner-bottom discontinuity (repeatable)")
    p.add_argument("--upper-tank", metavar="L,H,ALPHA",
                   help="also build the Upper-Tanks deck (needs a main deck)")
    p.add_argument("--replace", action="store_true",
                   help="delete the decks this command rebuilds before creating")
    p.add_argument("--x", help="optional transverse bulkhead X positions")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--workdir")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_inner_shell)

    p = sub.add_parser("decks",
                       help="create parametric decks (main, inner bottom, ...)")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--deck", action="append", required=True,
                   help="ID:NAME:HEIGHT[:TYPE[:CAMBER[:L[:H[:L2[:H2]]]]]] (repeatable)")
    p.add_argument("--camber", default="Plane", help="default camber (Plane)")
    p.add_argument("--camber-l", type=float,
                   help="default camber slope length L (m)")
    p.add_argument("--camber-h", type=float,
                   help="default camber slope height H (m)")
    p.add_argument("--camber-l2", type=float,
                   help="default second camber length L2 (two-knuckle)")
    p.add_argument("--camber-h2", type=float,
                   help="default second camber height H2 (two-knuckle)")
    p.add_argument("--flat-halfbreadth", type=float,
                   help="set the flat half breadth (table L) on every trace")
    p.add_argument("--flat-halfbreadth2", type=float,
                   help="set the second flat half breadth (table L2)")
    p.add_argument("--deck-trace", action="append", metavar="ID:X:Z:L[:L2]",
                   help="extra trace/discontinuity row for a deck (repeatable)")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--workdir")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_decks)

    p = sub.add_parser("hopper",
                       help="inner bottom deck with a trapezoidal hopper camber")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--z", type=float, default=2.0,
                   help="inner bottom base height (default 2.0)")
    p.add_argument("--flat", type=float, default=12.5,
                   help="flat inner-bottom half breadth (default 12.5)")
    p.add_argument("--slope", required=True, metavar="L,H",
                   help="hopper slope: run L and rise H in metres")
    p.add_argument("--slope2", metavar="L2,H2",
                   help="second knuckle slope (Trapezoidal with two knuckles)")
    p.add_argument("--flat2", type=float,
                   help="second horizontal half breadth (needed with --slope2)")
    p.add_argument("--trace", action="append", metavar="X:Z:L[:L2]",
                   help="extra discontinuity row (repeatable)")
    p.add_argument("--id", type=int, default=9, help="deck identifier (default 9)")
    p.add_argument("--name", default="InnerBottom", help="deck name")
    p.add_argument("--replace", action="store_true",
                   help="delete an existing deck with the same id/name first")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--workdir")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_hopper)

    p = sub.add_parser("upper-tank",
                       help="Upper-Tanks deck (topside tank, id 10)")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--l", type=float, required=True,
                   help="half breadth of the vertical internal side (m)")
    p.add_argument("--h", type=float, required=True,
                   help="height of the internal side above the main deck (m)")
    p.add_argument("--alpha", type=float, required=True,
                   help="hopper angle in degrees")
    p.add_argument("--id", type=int, default=10, help="deck identifier (default 10)")
    p.add_argument("--name", default="UpperTank", help="deck name")
    p.add_argument("--replace", action="store_true",
                   help="delete an existing deck with the same id/name first")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--workdir")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_upper_tank)

    p = sub.add_parser("bulkheads",
                       help="create transverse bulkheads at X = k positions")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--x", help="comma list of X positions (m from AP)")
    p.add_argument("--y", help="comma list of Y positions (longitudinal, m)")
    p.add_argument("--symmetrical", action="store_true",
                   help="generate symmetrical Y bulkheads (port + starboard)")
    p.add_argument("--prefix", default="BHD", help="name prefix for X bulkheads")
    p.add_argument("--prefix-y", default="INNER",
                   help="name prefix for Y bulkheads (default INNER)")
    p.add_argument("--start-id", type=int, default=101, help="first identifier")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--workdir")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_bulkheads)

    p = sub.add_parser("transform",
                       help="mother-ship Plane Scale X/Y -> Build Ship -> .fsf")
    p.add_argument("--fsf", required=True, help="source .fsf (copied)")
    p.add_argument("--lpp", type=float, required=True, help="target Lpp")
    p.add_argument("--breadth", type=float, required=True, help="target breadth")
    p.add_argument("--depth", type=float, default=14.6)
    p.add_argument("--draught", type=float, default=9.83)
    p.add_argument("--from-lpp", type=float, default=172.0,
                   help="source Lpp (default 172)")
    p.add_argument("--from-breadth", type=float, default=28.8,
                   help="source breadth (default 28.8)")
    p.add_argument("--scale-x", type=float, help="override X factor")
    p.add_argument("--scale-y", type=float, help="override Y factor")
    p.add_argument("--rebuild-frames", action="store_true",
                   help="rebuild the frame system after Build Ship (handoff step 12)")
    p.add_argument("--frame-nmax", type=int, default=100,
                   help="highest frame number for --rebuild-frames (default 100)")
    p.add_argument("--frame-spacing", type=float,
                   help="frame spacing in m (default Lpp / frame-nmax)")
    p.add_argument("--keep-decks", action="store_true",
                   help="do not delete the old decks before scaling")
    p.add_argument("--keep-bulkheads", action="store_true",
                   help="do not delete the old bulkheads before scaling")
    p.add_argument("--fnam", help="4-character ship name (default from file)")
    p.add_argument("--out", help="output .fsf")
    p.add_argument("--draw-out", help="also write a lines DXF")
    p.add_argument("--workdir")
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_transform)

    p = sub.add_parser("build")
    p.add_argument("--brep", required=True, help="closed shell (11-patch BREP recommended)")
    p.add_argument("--fnam", required=True, help="4-character project code, e.g. TEST")
    p.add_argument("--lpp", type=float, required=True)
    p.add_argument("--breadth", type=float, required=True)
    p.add_argument("--draught", type=float, required=True)
    p.add_argument("--depth", type=float, required=True)
    p.add_argument("--out", help="copy the written .fsf here")
    p.add_argument("--draw-out", help="also write a Lines Drawing DXF (needs frames)")
    p.add_argument("--frame-nmax", type=int, default=100,
                   help="highest frame number for the frame system (default 100)")
    p.add_argument("--frame-spacing", type=float,
                   help="frame spacing in metres (default Lpp/frame-nmax)")
    p.add_argument("--no-frames", action="store_true",
                   help="skip the frame system (Lines Drawing will refuse to run)")
    p.add_argument("--workdir", help="FSURF working directory")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--keep-open", action="store_true")
    p.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
