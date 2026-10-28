# -*- coding: utf-8 -*-
"""One-command FSURF workflow: open .fsf -> (optional Build Ship + Surface Validator) -> Lines Drawing (DXF).

With --build-ship, the tool runs two phases: it opens the model, completes
Build Ship (including the four-page Surface Validator), captures the newly
written .fsf, closes FSURF, then reopens that built .fsf and generates the DXF.

Window discovery uses win32gui (via foran_gui) because pywinauto's UIA desktop
enumeration mangles some Qt window titles on this machine.

Run with the skill venv:
  .venv\\Scripts\\python.exe foran_draw.py --fsf <file> --out <dxf>
or via the wrapper:
  foran draw --fsf "D:\\...\\samplefsurf.fsf" --out "...\\lines.dxf"
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402
import foran_ui as UI  # noqa: E402

try:
    import pyautogui
    import pyperclip
    import foran_gui as G
except Exception as exc:  # noqa: BLE001
    print(f"GUI dependencies missing: {exc}", file=sys.stderr)
    print("Use the venv: .venv\\Scripts\\python.exe", file=sys.stderr)
    raise SystemExit(3)


def find_hwnd(title: str, exact: bool = False, timeout: float = 20.0):
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            text = w.get("title", "")
            if (text == title) if exact else (title.lower() in text.lower()):
                return w["hwnd"]
        time.sleep(0.4)
    return None


def dlg_for(hwnd: int):
    return G._app_window(hwnd, "uia")


def _button_controls(hwnd: int, title: str):
    """All Button controls whose text equals `title` (case-insensitive)."""
    out = []
    try:
        d = dlg_for(hwnd)
        want = title.strip().lower()
        for c in d.descendants(control_type="Button"):
            try:
                if (c.window_text() or "").strip().lower() == want:
                    out.append(c)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return out


def click_control(ctrl, hwnd: int) -> bool:
    """Invoke a UIA control without relying on screen focus; click as fallback."""
    try:
        if not ctrl.is_enabled():
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        ctrl.invoke()
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        G._focus(hwnd)
        ctrl.click_input()
        return True
    except Exception:  # noqa: BLE001
        return False


def click_button(hwnd: int, title: str, timeout: float = 6.0) -> bool:
    """Click a button by exact text, polling until it appears.

    The old implementation used `child_window(...).click_input()` once.  On
    this machine that silently failed when the validator page was still
    rebuilding (the click landed on the previous page) or when the window was
    not the foreground window.  UIA `invoke()` is focus-independent, and the
    polling loop tolerates page transitions; click_input remains as fallback.
    """
    end = time.time() + max(0.0, timeout)
    while True:
        for c in _button_controls(hwnd, title):
            if click_control(c, hwnd):
                return True
        if time.time() >= end:
            return False
        time.sleep(0.3)


def paste_into_window(text: str) -> None:
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.hotkey("ctrl", "v")


VALIDATOR_PAGES = ("Free edges", "Patches orientation",
                   "Duplicated geometry", "Lines on surface")


def page_title(hwnd: int) -> str:
    """Return the current validator page name.

    Qt puts the page caption among several `Text` controls.  Returning the
    first non-empty one (the old behaviour) could pick a table cell; prefer a
    known page caption instead.
    """
    texts = []
    try:
        d = dlg_for(hwnd)
        for c in d.descendants(control_type="Text"):
            t = (c.window_text() or "").strip()
            if t:
                texts.append(t)
    except Exception:  # noqa: BLE001
        pass
    for t in texts:
        if t in VALIDATOR_PAGES:
            return t
    return texts[0] if texts else ""


_POPUP_CLASSES = ("QPopup", "QComboBoxPrivateContainer", "QComboBoxPopup", "QMenu")


def find_popup(timeout: float = 2.0):
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            cls = w.get("class", "")
            if cls in _POPUP_CLASSES or cls.startswith("QCombo"):
                return w["hwnd"]
        time.sleep(0.2)
    return None


def popup_checked(timeout: float = 3.0) -> bool:
    """Choose `Checked` in the status-dropdown popup.

    The popup has no title on this Qt build and may be exposed as a QPopup or
    an internal combo container, so scan every popup-like window for any control
    whose text is "Checked" instead of assuming ListItem/QPopup.
    """
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            cls = w.get("class", "")
            if not (cls in _POPUP_CLASSES or cls.startswith("QCombo")):
                continue
            try:
                d = dlg_for(w["hwnd"])
                for c in d.descendants():
                    try:
                        if (c.window_text() or "").strip().lower() == "checked":
                            if click_control(c, w["hwnd"]):
                                return True
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.2)
    return False


def wait_button_enabled(hwnd: int, title: str, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            d = dlg_for(hwnd)
            c = d.child_window(title=title, control_type="Button")
            if c.is_enabled():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return False


def validator_texts(hwnd: int):
    out = []
    try:
        for c in dlg_for(hwnd).descendants():
            try:
                t = (c.window_text() or "").strip()
                if t:
                    out.append(t)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return out


def validator_combos(hwnd: int):
    """(ComboBox, selected_text) pairs on the current validator page.

    The Status cell is a Qt ComboBox whose text is *not* exposed through
    `window_text()`; `selected_text()` is the only reliable value (verified on
    2026-10-26: it returns "Not checked" / "Checked").
    """
    out = []
    try:
        for c in dlg_for(hwnd).descendants(control_type="ComboBox"):
            try:
                out.append((c, c.selected_text()))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return out


def validator_unchecked(hwnd: int) -> bool:
    return any(t.strip().lower() == "not checked" for _, t in validator_combos(hwnd))


def validator_open_buttons(hwnd: int):
    return _button_controls(hwnd, "Open")


def validator_analyze_buttons(hwnd: int):
    return _button_controls(hwnd, "Analyze")


def _open_for_combo(combo, opens):
    """The row's tiny `Open` dropdown button (same vertical band)."""
    r = combo.rectangle()
    for b in opens:
        br = b.rectangle()
        if br.top < r.bottom and br.bottom > r.top:
            return b
    return None


def wait_validator_clean(hwnd: int, timeout: float = 12.0) -> bool:
    """Wait until every status combo reads Checked / Not applicable."""
    end = time.time() + timeout
    while time.time() < end:
        cs = validator_combos(hwnd)
        if cs and all(t.strip().lower() in ("checked", "not applicable")
                      for _, t in cs):
            return True
        time.sleep(0.4)
    return False


def dump_controls(hwnd: int, path) -> None:
    """Write the UIA tree to a text file (diagnostics only)."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            for c in dlg_for(hwnd).descendants():
                try:
                    fh.write(f"{c.element_info.control_type}\t"
                             f"{(c.window_text() or '').strip()!r}\t"
                             f"{c.rectangle()}\tenabled={c.is_enabled()}\n")
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass


def status_point(hwnd: int):
    """Return the click point for the Status dropdown in the first row."""
    d = dlg_for(hwnd)
    status = None
    table = None
    for c in d.descendants(control_type="Header"):
        if c.window_text().strip() == "Status":
            status = c.rectangle()
            break
    for c in d.descendants(control_type="Table"):
        table = c.rectangle()
        break
    if status is None or table is None:
        return None
    return (status.right - 6, status.bottom + 10)


def wait_page(hwnd: int, title: str, timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if page_title(hwnd) == title:
            return True
        time.sleep(0.4)
    return False


def close_error() -> None:
    hwnd = find_hwnd("Error", timeout=1)
    if hwnd is not None:
        click_button(hwnd, "Ok") or click_button(hwnd, "OK")


def _check_validator_rows(hwnd: int, timeout: float = 60.0) -> bool:
    """Analyze every row and set its status to Checked, with retries.

    After `Analyze` the Status cell becomes a ComboBox (value "Not checked");
    its value is not exposed as text.  Click the row's tiny `Open` button, pick
    `Checked`, then read the combo back.  This is idempotent: rows already
    Checked are skipped.
    """
    for attempt in range(3):
        close_error()
        cs = validator_combos(hwnd)
        if cs and not any(t.strip().lower() == "not checked" for _, t in cs):
            return True
        if not cs:
            analyze = validator_analyze_buttons(hwnd)
            if not analyze:
                # No rows on this page, or already analysed and collapsed.
                return not validator_unchecked(hwnd)
            for c in analyze:
                click_control(c, hwnd)
            end = time.time() + timeout
            while time.time() < end and not validator_combos(hwnd):
                if any(t.strip().lower() == "checked"
                       for t in validator_texts(hwnd)):
                    return True          # plain-text pages (Duplicated/Lines)
                time.sleep(0.5)
            cs = validator_combos(hwnd)
            if not cs:
                print("    validator: no status combo after Analyze",
                      file=sys.stderr)
                continue
        opens = validator_open_buttons(hwnd)
        for combo, status in cs:
            if status.strip().lower() in ("checked", "not applicable"):
                continue
            btn = _open_for_combo(combo, opens)
            if btn is None:
                continue
            click_control(btn, hwnd)
            time.sleep(0.3)
            popup_checked(3)
            time.sleep(0.3)
        if wait_validator_clean(hwnd, 12):
            return True
        print(f"    validator: retry {attempt + 2}/3", file=sys.stderr)
    return False


def complete_validator(hwnd: int) -> bool:
    """Walk Surface Validator: Analyze -> Open -> Checked -> Next/Finish."""
    pages = VALIDATOR_PAGES
    for idx, step in enumerate(pages):
        page_t0 = time.time()
        if not wait_page(hwnd, step, 20):
            print(f"  validator: expected page {step!r}, got {page_title(hwnd)!r}",
                  file=sys.stderr)
        nxt = pages[idx + 1] if idx + 1 < len(pages) else None
        ok = False
        for attempt in range(2):
            time.sleep(0.4)
            close_error()
            print(f"  validator: {page_title(hwnd) or step}"
                  + (f" (attempt {attempt + 1})" if attempt else ""))
            G._focus(hwnd)
            if step in ("Free edges", "Patches orientation"):
                ok = _check_validator_rows(hwnd, timeout=60)
            else:
                # Duplicated geometry / Lines on surface: bulk analyze marks
                # every row Checked as plain text (no combo to read back).
                ok = click_button(hwnd, "Analyze all surfaces", timeout=5)
                if ok:
                    print("    pressed Analyze all surfaces")
                    # FORAN marks these rows Checked only at the very end;
                    # polling the text was slower than this fixed settle.
                    time.sleep(5)
            print(f"    status -> Checked: {ok}")
            if not ok:
                break
            if nxt is None:
                break
            if not click_button(hwnd, "Next >", timeout=10):
                print("    Next > not found", file=sys.stderr)
                ok = False
                break
            if wait_page(hwnd, nxt, 25):
                break
            print(f"    did not reach {nxt!r} (got {page_title(hwnd)!r}); retrying",
                  file=sys.stderr)
            ok = False
        if not ok:
            close_error()
            try:
                dump_controls(hwnd, Path.cwd() / "_foran_work" / "logs" /
                              f"validator_{step.replace(' ', '_')}.txt")
            except Exception:  # noqa: BLE001
                pass
            return False
        close_error()
        print(f"    page {step!r} done in {time.time() - page_t0:.1f} s")
    if not click_button(hwnd, "Finish", timeout=10):
        return False
    time.sleep(2)
    warning = find_hwnd("Warning", timeout=10)
    if warning is not None:
        click_button(warning, "Ok")
    err = find_hwnd("Error", timeout=2)
    if err is not None:
        try:
            for c in dlg_for(err).descendants(control_type="Text"):
                print("    validator error:", c.window_text(), file=sys.stderr)
                break
        except Exception:  # noqa: BLE001
            pass
        return False
    return True


def wait_file(path: Path, timeout: float = 90.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return False


def fill_open_dialog(path: Path, timeout: float = 30.0) -> bool:
    hwnd = find_hwnd("Open file", timeout=timeout)
    if hwnd is None:
        return False
    try:
        G._focus(hwnd)
        d = dlg_for(hwnd)
        edit = d.child_window(control_type="Edit", title="File name:")
        edit.click_input()
    except Exception:  # noqa: BLE001
        r = next(w for w in G.windows() if w["hwnd"] == hwnd)["rect"]
        pyautogui.click(r[0] + 300, r[1] + 440)
    paste_into_window(str(path))
    pyautogui.press("enter")
    return True


def launch_fsurf_open(model: Path, workdir: Path):
    """Launch FSURF with the configured wrapper and open `model` via File > Open."""
    import foran_launch as L
    rc = L.main(["fsurf", "--workdir", str(workdir)])
    if rc:
        return None
    hwnd = find_hwnd("fsurf -", timeout=60)
    if hwnd is None:
        return None
    G._focus(hwnd)
    time.sleep(1.0)
    UI.menu_click(G, hwnd, "File", (57, 54))
    time.sleep(0.6)
    UI.menu_click(G, hwnd, "Open", (105, 80))
    time.sleep(1.0)
    if not fill_open_dialog(model, timeout=30):
        return None
    deadline = time.time() + 60
    while time.time() < deadline:
        w = next((w for w in G.windows() if w.get("hwnd") == hwnd), None)
        if w and model.name in w.get("title", ""):
            break
        time.sleep(0.5)
    time.sleep(5.0)
    return hwnd


def open_lines_drawing(hwnd: int) -> bool:
    """File > Ship > Drawings > Lines drawing (keyboard menu path)."""
    import pyautogui
    G._focus(hwnd)
    pyautogui.press("escape")
    time.sleep(0.4)
    UI.menu_click(G, hwnd, "File", (57, 54))
    time.sleep(0.7)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(0.8)
    for _ in range(3):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(0.8)
    pyautogui.press("enter")
    time.sleep(2.0)
    return True


def open_build_ship(hwnd: int) -> bool:
    """File > Ship > Build ship (first item in the Ship submenu)."""
    import pyautogui
    G._focus(hwnd)
    pyautogui.press("escape")
    time.sleep(0.4)
    UI.menu_click(G, hwnd, "File", (57, 54))
    time.sleep(0.7)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(0.8)
    pyautogui.press("enter")
    time.sleep(2.0)
    return True


def click_build_ship_ok(timeout: float = 20.0) -> bool:
    hwnd = find_hwnd("fsurf", exact=True, timeout=timeout)
    if hwnd is None:
        return False
    G._focus(hwnd)
    return click_button(hwnd, "OK")


# Build Ship dialog labels (V80R3.0, English UI) -> data entry fields.
BUILD_SHIP_LABELS = {
    "fnam": "FNAM",
    "description": "Description",
    "type": "Type of Ship",
    "class": "Classification Society",
    "owner": "Owner",
    "deadweight": "Deadweight",
    "lpp": "Length between pp.",
    "breadth": "Design Breadth",
    "draught": "Design Draught",
    "depth": "Design Depth",
    "origin": "Origin",
    "cyl_length": "Length",
    "xmin": "Xmin",
    "ymin": "Ymin",
    "zmin": "Zmin",
    "xmax": "Xmax",
    "ymax": "Ymax",
    "zmax": "Zmax",
}


def _center_y(ctrl) -> float:
    r = ctrl.rectangle()
    return (r.top + r.bottom) / 2.0


def fill_build_ship(hwnd: int, fields: dict[str, str]) -> dict[str, str]:
    """Set Build Ship fields by label, using UIA geometry + clipboard paste.

    The Qt edits expose their *values* through UIA but reject
    `set_edit_text`/`iface_value.SetValue` on this machine, so each field is
    focused and filled with ctrl+A + clipboard paste + Tab.

    `fields` keys can be the short names in BUILD_SHIP_LABELS or the exact
    dialog label (e.g. "Length between pp.").
    """
    if not fields:
        return {}
    d = dlg_for(hwnd)
    labels = {}
    for c in d.descendants(control_type="Text"):
        t = (c.window_text() or "").strip()
        if t and t not in labels:
            labels[t] = c
    edits = d.descendants(control_type="Edit")
    done = {}
    for key, value in fields.items():
        label = BUILD_SHIP_LABELS.get(key.lower(), key)
        lc = labels.get(label)
        if lc is None:
            raise SystemExit(f"Build Ship label not found: {label!r}")
        ly = _center_y(lc)
        ll = lc.rectangle().left
        cand = [e for e in edits
                if abs(_center_y(e) - ly) <= 10 and e.rectangle().left > ll + 20]
        if not cand:
            raise SystemExit(f"Build Ship edit not found for label {label!r}")
        # The nearest field to the right of the label.
        cand.sort(key=lambda e: e.rectangle().left)
        e = cand[0]
        G._focus(hwnd)
        r = e.rectangle()
        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        pyautogui.hotkey("ctrl", "a")
        paste_into_window(str(value))
        pyautogui.press("tab")
        time.sleep(0.4)
        try:
            done[label] = e.get_value()
        except Exception:  # noqa: BLE001
            done[label] = str(value)
    return done


_LINE_RADIOS = {
    "type": {"after-fore": "After-Fore", "after": "After", "fore": "Fore",
             "two": "Two-drawings"},
    "body": {"centre": "Centre", "right": "Right"},
    "marks": {"frames": "Frames", "metres": "Metres"},
}
_LINE_CHECKS = {
    "diagonals": "Scale for the diagonals",
    "special": "Drawing of special lines",
    "parallel": "Marks for the parallel body",
    "particulars": "Printing of main particulars",
    "stamp": "Drawing of the stamp",
    "deck_sections": "Transversal sections of the decks",
    "deck_centre": "Intersection of the decks with the central plane",
}


def _control_by_text(hwnd: int, text: str):
    try:
        d = G._app_window(hwnd, "uia")
        for c in d.descendants():
            if (c.window_text() or "").strip() == text:
                return c
    except Exception:  # noqa: BLE001
        pass
    return None


def _labeled_edit(hwnd: int, label: str):
    try:
        d = G._app_window(hwnd, "uia")
        lab = next((c for c in d.descendants(control_type="Text")
                    if (c.window_text() or "").strip() == label), None)
        if lab is None:
            return None
        top = lab.rectangle().top
        right = lab.rectangle().right
        edits = [c for c in d.descendants(control_type="Edit")
                 if abs(c.rectangle().top - top) <= 8
                 and c.rectangle().left >= right - 2]
        return edits[0] if edits else None
    except Exception:  # noqa: BLE001
        return None


def _set_toggle(ctrl, value: bool) -> None:
    state = None
    try:
        state = bool(ctrl.iface_toggle.CurrentToggleState)
    except Exception:  # noqa: BLE001
        pass
    if state is None or state != value:
        ctrl.click_input()
        time.sleep(0.15)
        try:
            if bool(ctrl.iface_toggle.CurrentToggleState) != value:
                ctrl.click_input()
                time.sleep(0.15)
        except Exception:  # noqa: BLE001
            pass


def line_opts_from_args(a) -> dict:
    """Collect --line-* flags (None means "leave the dialog as it is")."""
    opts = {}
    for key, attr in (("type", "line_type"), ("body", "line_body"),
                      ("marks", "line_marks")):
        v = getattr(a, attr, None)
        if v:
            opts[key] = v
    for key, attr in (("diagonals", "line_diagonals"),
                      ("special", "line_special"),
                      ("parallel", "line_parallel"),
                      ("particulars", "line_particulars"),
                      ("stamp", "line_stamp"),
                      ("deck_sections", "line_deck_sections"),
                      ("deck_centre", "line_deck_centre")):
        v = getattr(a, attr, None)
        if v is not None:
            opts[key] = bool(v)
    return opts


def _choose_output_file(dlg: int, save_title: str, path: Path) -> bool:
    """Click Select... in a drawing dialog and fill the Save <x> File dialog."""
    d = G._app_window(dlg, "uia")
    sel = next((b for b in d.descendants(control_type="Button")
                if "Select" in (b.window_text() or "")), None)
    if sel is None:
        return False
    sel.click_input()
    save = find_hwnd(save_title, timeout=10)
    if save is None:
        return False
    G._focus(save)
    time.sleep(1.0)
    lab = None
    edit = None
    for _ in range(10):
        d2 = G._app_window(save, "uia")
        lab = next((c for c in d2.descendants(control_type="Text")
                    if "File name" in (c.window_text() or "")), None)
        if lab is not None:
            lt = lab.rectangle().top
            edits = [c for c in d2.descendants(control_type="Edit")
                     if abs(c.rectangle().top - lt) <= 12]
            if edits:
                edit = edits[0]
                break
        time.sleep(0.5)
    if edit is None:
        return False
    edit.click_input()
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyperclip.copy(str(path))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.6)
    if not click_button(save, "Save", timeout=5):
        return False
    # The Save dialog is modal; wait until it closes so the drawing dialog is
    # usable again.
    end = time.time() + 10
    while time.time() < end:
        if find_hwnd(save_title, timeout=0.3) is None:
            return True
        time.sleep(0.3)
    return False


def fill_lines_dialog(out: Path, scale: str = "100", opts: dict | None = None,
                      timeout: float = 45.0) -> bool:
    """Fill the Lines Drawing dialog, preferring UIA labels over coordinates."""
    opts = opts or {}
    hwnd = find_hwnd("Lines Drawing", timeout=timeout)
    if hwnd is None:
        return False
    G._focus(hwnd)
    r = next(w for w in G.windows() if w["hwnd"] == hwnd)["rect"]

    def set_edit(edit, value, fallback_x):
        if edit is not None:
            try:
                edit.click_input()
            except Exception:  # noqa: BLE001
                er = edit.rectangle()
                pyautogui.click((er.left + er.right) // 2, (er.top + er.bottom) // 2)
        else:
            pyautogui.click(r[0] + fallback_x, r[1] + 122)
        pyautogui.hotkey("ctrl", "a")
        # Qt spin box: clipboard paste is ignored, typing works.
        pyautogui.typewrite(str(value), interval=0.05)
        pyautogui.press("tab")

    set_edit(_labeled_edit(hwnd, "Scale"), scale, 80)

    for key, choices in _LINE_RADIOS.items():
        value = opts.get(key)
        if value and value in choices:
            ctrl = _control_by_text(hwnd, choices[value])
            if ctrl is not None:
                ctrl.click_input()
                time.sleep(0.15)
    for key, label in _LINE_CHECKS.items():
        if key not in opts:
            continue
        ctrl = _control_by_text(hwnd, label)
        if ctrl is not None:
            _set_toggle(ctrl, bool(opts[key]))

    if not _choose_output_file(hwnd, "Save Drawing File", out):
        return False
    if not click_button(hwnd, "OK", timeout=5):
        return False
    return True


def dismiss_extra_dialogs(max_rounds: int = 5) -> None:
    for _ in range(max_rounds):
        hit = False
        for w in G.windows():
            text = w.get("title", "")
            if text in ("Warning", "Error", "Please confirm...") or "warning" in text.lower():
                for name in ("OK", "Yes", "Ok"):
                    if click_button(w["hwnd"], name):
                        hit = True
                        time.sleep(0.5)
                        break
        if not hit:
            return


def close_fsurf() -> None:
    """Close FSURF, answering the exit confirmation; retry if it lingers."""
    hwnd = find_hwnd("fsurf -", timeout=5)
    if hwnd is None:
        return
    import win32process
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    close = click_button(hwnd, "关闭")
    if not close:
        try:
            G._app_window(hwnd, "uia").close()
        except Exception:  # noqa: BLE001
            pass
    if UI.close_app(G, pid, click_button, timeout=12):
        return
    # Last resort: post WM_CLOSE, then keep answering the confirmation.
    import win32con
    import win32gui
    for w in [x for x in G.windows()
              if x.get("process", "").lower() == "fsurf.exe"]:
        try:
            win32gui.PostMessage(w["hwnd"], win32con.WM_CLOSE, 0, 0)
        except Exception:  # noqa: BLE001
            pass
    UI.close_app(G, pid, click_button, timeout=8)


def build_then_draw(a, src: Path, out: Path, shadow: Path) -> int:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    models = Path.cwd() / "_foran_work" / "models"
    models.mkdir(parents=True, exist_ok=True)
    model_copy = models / f"{src.stem}_{stamp}.fsf"
    shutil.copy2(src, model_copy)

    build_run = Path.cwd() / "_foran_work" / "draw_runs" / f"{stamp}_build"
    if not launch_fsurf_open(model_copy, build_run):
        print("FSURF launch/open failed (build phase)", file=sys.stderr)
        return 1
    print(f"build run  : {build_run}")
    hwnd = find_hwnd("fsurf -", timeout=10)
    if hwnd is None or not open_build_ship(hwnd):
        print("Build Ship menu failed", file=sys.stderr)
        return 1
    build_hwnd = find_hwnd("fsurf", exact=True, timeout=60)
    if build_hwnd is None:
        print("Build Ship dialog not found", file=sys.stderr)
        return 1
    fields = getattr(a, "build_fields", None) or {}
    if fields:
        try:
            filled = fill_build_ship(build_hwnd, fields)
        except SystemExit as exc:
            print(f"Build Ship fields: {exc}", file=sys.stderr)
            return 1
        print("Build Ship fields: " + ", ".join(f"{k}={v}" for k, v in filled.items()))
    G._focus(build_hwnd)
    build_started = time.time()
    if not click_button(build_hwnd, "OK"):
        print("Build Ship OK not found", file=sys.stderr)
        return 1
    print("Build Ship OK")
    validator = find_hwnd("Surface Validator", timeout=60)
    if validator is not None:
        print("Surface Validator: completing")
        if not complete_validator(validator):
            print("Surface Validator: could not finish", file=sys.stderr)
            return 1
        print("Surface Validator: finished")
    deadline = time.time() + 30
    built = []
    while time.time() < deadline:
        cands = []
        for d in (build_run, model_copy.parent, Path.cwd()):
            cands += list(d.glob("*.fsf"))
        cands = [p for p in cands
                 if p.resolve() != model_copy.resolve()
                 and p.stat().st_mtime >= build_started - 2]
        built = sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True)
        if built:
            break
        time.sleep(1)
    draw_src = built[0] if built else model_copy
    if built:
        print(f"built FSF  : {built[0]} ({built[0].stat().st_size} bytes)")
    else:
        print("built FSF not found; drawing from the copy")
    close_fsurf()
    time.sleep(1)

    draw_run = Path.cwd() / "_foran_work" / "draw_runs" / f"{stamp}_draw"
    if not launch_fsurf_open(draw_src, draw_run):
        print("FSURF launch/open failed (draw phase)", file=sys.stderr)
        return 1
    print(f"draw run   : {draw_run}")
    hwnd = find_hwnd("fsurf -", timeout=10)
    if hwnd is None or not open_lines_drawing(hwnd):
        print("Lines Drawing menu failed", file=sys.stderr)
        return 1
    if not fill_lines_dialog(out, a.scale, line_opts_from_args(a), timeout=45):
        print("Lines Drawing dialog not found", file=sys.stderr)
        return 1
    print("Lines Drawing submitted")
    if wait_file(out, timeout=a.timeout):
        print(f"DXF written: {out} ({out.stat().st_size} bytes)")
        if _frame_lines(a, out) != 0:
            print("framing failed", file=sys.stderr)
            if not a.keep_open:
                close_fsurf()
            return 1
    else:
        print("DXF not produced (timeout)", file=sys.stderr)
        return 1
    if not a.keep_open:
        close_fsurf()
    return 0


def _frame_lines(a, lines_path: Path) -> int:
    """Optionally put the written DXF on a framed sheet (see foran_dxf)."""
    if not getattr(a, "frame_out", None):
        return 0
    import foran_dxf as DX
    from types import SimpleNamespace
    ns = SimpleNamespace(
        inp=str(lines_path), out=a.frame_out,
        sheet="A1", portrait=False, fit=False, units_per_mm=0.0001,
        template=getattr(a, "frame_template", None),
        template_units_per_mm=1.0, template_margin=10.0,
        template_area=getattr(a, "frame_area", None) or "auto",
        project=getattr(a, "frame_project", "SAMPLE SHIP"),
        title=getattr(a, "frame_title", "型线图"),
        drawing_no=getattr(a, "frame_drawing_no", "EXAMPLE-010-04"),
        scale_text=getattr(a, "frame_scale_text", "1:100"),
        designer=getattr(a, "frame_designer", ""),
        checker=getattr(a, "frame_checker", ""),
        approver=getattr(a, "frame_approver", ""),
        company=getattr(a, "frame_company", "YOUR COMPANY"),
        date=dt.date.today().strftime("%Y-%m-%d"),
        scale=None, scale_den=None,
    )
    return DX.cmd_frame(ns)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fsf", required=True, help="input FSURF .fsf model (will be copied)")
    ap.add_argument("--out", required=True, help="output DXF path")
    ap.add_argument("--module", default="fsurf", choices=("fsurf",))
    ap.add_argument("--scale", default="100", help="Lines Drawing scale (default 100)")
    ap.add_argument("--frame-out", help="also write a framed DXF here")
    ap.add_argument("--frame-template", help="frame/title-block DXF to merge")
    ap.add_argument("--frame-area",
                    help="drawing area x0,y0,x1,y1 (mm) or auto (default)")
    ap.add_argument("--frame-project", default="SAMPLE SHIP")
    ap.add_argument("--frame-title", default="型线图")
    ap.add_argument("--frame-drawing-no", default="EXAMPLE-010-04")
    ap.add_argument("--frame-scale-text", default="1:100")
    ap.add_argument("--frame-designer", default="")
    ap.add_argument("--frame-checker", default="")
    ap.add_argument("--frame-approver", default="")
    ap.add_argument("--frame-company", default="YOUR COMPANY")
    ap.add_argument("--line-type", choices=("after-fore", "after", "fore", "two"),
                    help="Lines Drawing type (default: dialog value, After-Fore)")
    ap.add_argument("--line-body", choices=("centre", "right"),
                    help="Location of the body")
    ap.add_argument("--line-marks", choices=("frames", "metres"),
                    help="Marks in the axis")
    for _flag, _attr, _help in (
            ("diagonals", "line_diagonals", "Scale for the diagonals"),
            ("special", "line_special", "Drawing of special lines"),
            ("parallel", "line_parallel", "Marks for the parallel body"),
            ("particulars", "line_particulars", "Printing of main particulars"),
            ("stamp", "line_stamp", "Drawing of the stamp"),
            ("deck-sections", "line_deck_sections", "Transversal sections of the decks"),
            ("deck-centre", "line_deck_centre",
             "Intersection of the decks with the central plane")):
        ap.add_argument(f"--line-{_flag}", dest=_attr, action="store_true",
                        default=None, help=_help)
        ap.add_argument(f"--no-line-{_flag}", dest=_attr, action="store_false",
                        help=f"disable: {_help}")
    ap.add_argument("--build-ship", action="store_true",
                    help="complete Build Ship + Surface Validator, then draw from the built .fsf")
    # Build Ship fields (only used with --build-ship).
    for opt, helptext in (
        ("fnam", "FNAM / project code"),
        ("description", "Description"),
        ("type", "Type of Ship"),
        ("class", "Classification Society"),
        ("owner", "Owner"),
        ("deadweight", "Deadweight"),
        ("lpp", "Length between perpendiculars"),
        ("breadth", "Design breadth"),
        ("draught", "Design draught"),
        ("depth", "Design depth"),
    ):
        ap.add_argument(f"--build-{opt}", dest=f"build_{opt.replace('-', '_')}", help=helptext)
    ap.add_argument("--build-field", action="append", metavar="LABEL=VALUE",
                    help="set any Build Ship field by its dialog label (repeatable), "
                         "e.g. --build-field 'Xmin=0'")
    ap.add_argument("--shadow", help="shadow FORAN_HOME")
    ap.add_argument("--keep-open", action="store_true", help="do not close FSURF at the end")
    ap.add_argument("--timeout", type=float, default=120.0)
    a = ap.parse_args(argv)
    fields = {}
    for key in ("fnam", "description", "type", "class", "owner", "deadweight",
                "lpp", "breadth", "draught", "depth"):
        val = getattr(a, f"build_{key}")
        if val is not None:
            fields[key] = val
    for spec in a.build_field or []:
        if "=" not in spec:
            raise SystemExit(f"--build-field must be LABEL=VALUE, got {spec!r}")
        label, value = spec.split("=", 1)
        fields[label.strip()] = value.strip()
    a.build_fields = fields

    if find_hwnd("fsurf -", timeout=0.2) is not None:
        print("FSURF is already running; close it first or use --keep-open after closing.", file=sys.stderr)
        return 2

    src = Path(a.fsf).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"FSF not found: {src}")
    out = Path(a.out).expanduser().resolve()
    shadow = None
    if a.build_ship:
        return build_then_draw(a, src, out, shadow)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "draw_runs" / stamp
    models = Path.cwd() / "_foran_work" / "models"
    models.mkdir(parents=True, exist_ok=True)
    model_copy = models / f"{src.stem}_{stamp}.fsf"
    shutil.copy2(src, model_copy)
    if not launch_fsurf_open(model_copy, run_dir):
        print("FSURF launch/open failed", file=sys.stderr)
        return 1
    print(f"model copy : {model_copy}")
    print(f"run dir    : {run_dir}")
    print(f"output     : {out}")
    hwnd = find_hwnd("fsurf -", timeout=10)
    if hwnd is None or not open_lines_drawing(hwnd):
        print("Lines Drawing menu failed", file=sys.stderr)
        return 1


    if a.build_ship:
        dismiss_extra_dialogs()
        if click_build_ship_ok(timeout=20):
            print("Build Ship OK")
            time.sleep(2)
            validator = find_hwnd("Surface Validator", timeout=10)
            if validator is not None:
                print("Surface Validator: completing")
                if complete_validator(validator):
                    print("Surface Validator: finished")
                else:
                    print("Surface Validator: could not finish (continuing)")
        else:
            print("Build Ship dialog not found (continuing)")
        time.sleep(1)
    dismiss_extra_dialogs()
    if not fill_lines_dialog(out, a.scale, line_opts_from_args(a), timeout=45):
        print("Lines Drawing dialog not found", file=sys.stderr)
        for w in G.windows():
            print("  window:", w.get("title"), file=sys.stderr)
        return 1
    print("Lines Drawing submitted")
    if wait_file(out, timeout=a.timeout):
        print(f"DXF written: {out} ({out.stat().st_size} bytes)")
        if _frame_lines(a, out) != 0:
            print("framing failed", file=sys.stderr)
            if not a.keep_open:
                close_fsurf()
            return 1
    else:
        print("DXF not produced (timeout)", file=sys.stderr)
        return 1
    built = sorted(run_dir.glob("*.fsf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if built:
        print(f"built FSF: {built[0]} ({built[0].stat().st_size} bytes)")
    if not a.keep_open:
        close_fsurf()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
