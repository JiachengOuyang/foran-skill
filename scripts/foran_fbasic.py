# -*- coding: utf-8 -*-
"""FBASIC workflows driven through the live GUI.

Verified on FORAN V80R3.0, 1920x1080 maximized window (2026-10-27).

Commands
--------
  foran fbasic wh --db <sample.db> [--copy|--in-place] [--keep-open]
  foran fbasic wh --db <db> --space SPC-0003
  foran fbasic wh --db <db> --space SPC-0003 --build
  foran fbasic hydro --db <db> [--calc HYD-CALC-01] [--copy|--in-place]
  foran fbasic cross --db <db> [--displacements 20000,30000,40000,50000,60000]
  foran fbasic capacity --db <db> --spaces SPC-0002,SPC-0003 [--levels 15] [--spacing 1.0]
  foran fbasic freeboard --db <db> [--calc FB-0001] [--copy|--in-place]
  foran fbasic tonnage --db <db> --spaces SPC-0002,SPC-0003 [--calc TONN-0001]
  foran fbasic lsw --db <db> --tsv zones.tsv [--name LSW-04]
  foran fbasic lc --db <db> --lsw LSW-04 [--load 32792,95,8]

`wh` opens `SOLID-01 > Edit`.  With `--space` it switches `Method` to
`Spaces` and checks the given space in `Space selection`.  With `--build`
it then runs `Build WH` -> `Sections` (default sections) -> `Ok` ->
`File > Save` and verifies `DSG_SOLID_DIR` / `DSG_SOLID_HULL_SECTIONS`.
Tested on a copy of the golden DB (2026-10-27): solid ready, 69 sections,
saved.

`hydro` opens an existing `HYD-CALC-*`, clicks `Calculate`, waits for
`Please wait` to finish, `Ok`, `File > Save`, then prints the closest row
to 9.83 m draught from `DSG_HYD_RESULTS`.  Tested on the golden DB copy:
58 rows, 41,432.117 t / 40,421.578 m3 at 9.83 m.

`cross` edits an existing `KNS-CALC-*` (or creates one), ensures at least
5 displacements, clicks `Calculate`, waits for `Please Wait...`, `Ok`,
`File > Save`, and prints `DSG_KNS_CALC_RESULT` rows.  Tested 2026-10-27:
357 rows, KN(5 deg, 20000 t)=4.915 m.

`capacity` edits an existing `CT-*` (or creates one), sets the waterline
levels/spacing, selects the spaces (maximized `Spaces selection` dialog),
`Calculate`, clicks `Close` when the progress bar reaches 100%, `Ok`,
`File > Save`, and prints `DSG_CT_DATA` / `DSG_CT_SPACES`.  Tested
2026-10-27: 15 levels / 1.0 m, SPC-0002/0003.

`freeboard` edits an existing `FB-*` (or creates one), clicks `Calculate`,
`Ok`, `File > Save`, and verifies `DSG_FREEBOARD_DATA` /
`DSG_FREEBOARD_RESULTS`.  `tonnage` edits an existing `TONN-*` (or creates
one), adds the given spaces to `Included spaces`, `Calculate`, `Ok`,
`File > Save`, and prints the `TONN-*` node (GT/NT are shown in the UI).

`lsw` creates a lightship weight distribution from a TSV
(Group/Name/Description/Ref/Weight/X min/X max/XCoG/YCoG/ZCoG).  The X
ranges must be the real longitudinal extents of the zones (midpoints of
neighbouring XCoG); identical ranges produce an invalid grid.  It reopens
the distribution in edition mode so the total weight is computed, then
runs `Edit complex distribution -> OK -> accept the remainder warning` and
`File > Save`.  Verified 2026-10-27: 17 zones / 8,650 t -> 244 distribution
rows in `DSG_LSW_DIST_RESULTS`.

`lc` creates a loading condition, selects `--lsw`, optionally adds one
local load (`--load WEIGHT,XCG,ZCG`), runs `Loading Conditions ->
Calculate`, saves and exits (the LC rows are flushed on exit).  The DB must
already contain a calculated LSW distribution from `lsw`; use a fresh
launch (this command always launches its own FBASIC).  Verified 2026-10-27:
LC with 32,792 t -> `DSG_LOAD_COND.CALCULATED=1`, Displac 41,442 t,
GM 3.856 m after reopening.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_ui as UI  # noqa: E402


def _prepare_db(a) -> Path:
    db = Path(a.db).expanduser().resolve()
    if not db.is_file():
        raise SystemExit(f"database not found: {db}")
    if a.copy:
        dest_dir = Path.cwd() / "_foran_work" / "projects"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / db.name
        if not dest.exists() or dest.stat().st_mtime < db.stat().st_mtime:
            shutil.copy2(db, dest)
        print(f"database copy: {dest}")
        return dest
    print("note: opening the database in place; use --copy to work on a copy")
    return db


def _close(G) -> None:
    for _ in range(3):
        dialogs = [w for w in G.windows()
                   if w.get("title") in ("Error", "Warning", "Please confirm...",
                                         "Information modified", "Information")]
        if dialogs:
            for w in dialogs:
                for name in ("No", "Ok", "OK", "Yes", "Close"):
                    try:
                        d = G._app_window(w["hwnd"], "uia")
                        for c in d.descendants(control_type="Button"):
                            if (c.window_text() or "").strip() == name:
                                c.invoke()
                                raise StopIteration
                    except StopIteration:
                        break
                    except Exception:  # noqa: BLE001
                        pass
            time.sleep(0.8)
            continue
        hits = [w for w in G.windows() if w.get("title", "").startswith("fbasic -")]
        if not hits:
            return
        for w in hits:
            G._focus(w["hwnd"])
            try:
                G._app_window(w["hwnd"], "uia").close()
            except Exception:  # noqa: BLE001
                import pyautogui
                pyautogui.hotkey("alt", "f4")
        time.sleep(1.5)


def _wait_main(G, timeout: float = 60.0):
    end = time.time() + timeout
    while time.time() < end:
        w = next((x for x in G.windows() if x["title"].startswith("fbasic -")), None)
        if w:
            return w
        time.sleep(0.4)
    return None


def _dismiss_warnings(G) -> None:
    for w in G.windows():
        if w.get("title") not in ("Warning", "Information"):
            continue
        G._focus(w["hwnd"])
        time.sleep(0.3)
        try:
            d = G._app_window(w["hwnd"], "uia")
            texts = " | ".join(c.window_text() for c in d.descendants(control_type="Text")
                               if c.window_text())
            print(f"dialog   : {w['title']}: {texts}")
            for c in d.descendants(control_type="Button"):
                if (c.window_text() or "").strip() in ("Ok", "OK", "Yes"):
                    c.invoke()
                    break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.8)


def _dismiss_profile_warning(G) -> bool:
    """Click Ok on the non-fatal 'ship's profile is not defined' warning."""
    for w in G.windows():
        if w.get("title") != "Warning":
            continue
        try:
            d = G._app_window(w["hwnd"], "uia")
            txt = " | ".join(c.window_text() for c in d.descendants(control_type="Text")
                             if c.window_text())
        except Exception:  # noqa: BLE001
            continue
        if "profile is not defined" not in txt:
            continue
        G._focus(w["hwnd"])
        time.sleep(0.2)
        for c in d.descendants(control_type="Button"):
            if (c.window_text() or "").strip() in ("Ok", "OK"):
                c.invoke()
                print("dialog   : profile warning -> Ok")
                return True
    return False


def _please_wait(G) -> bool:
    """FBASIC uses both `Please wait` and `Please Wait...` titles."""
    return any("please wait" in (w.get("title") or "").lower() for w in G.windows())


def _settle_warnings(G, timeout: float = 12.0) -> None:
    """Keep dismissing dialogs until the UI has been quiet for ~2 seconds."""
    end = time.time() + timeout
    quiet = 0
    while time.time() < end:
        if any(w.get("title") in ("Warning", "Information") for w in G.windows()):
            _dismiss_warnings(G)
            _dismiss_profile_warning(G)
            quiet = 0
        else:
            quiet += 1
            if quiet >= 4:
                return
        time.sleep(0.5)


def _tree_item_in_window(G, hwnd: int, text: str):
    try:
        d = G._app_window(hwnd, "uia")
        for c in d.descendants(control_type="TreeItem"):
            try:
                r = c.rectangle()
                if (c.window_text() or "").strip() == text and r.left < 250:
                    return c
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return None


def _wait_tree_item(G, hwnd: int, text: str, timeout: float = 5.0):
    """Poll `_tree_item` until the node appears (no fixed tab-switch sleep)."""
    end = time.time() + timeout
    while time.time() < end:
        item = _tree_item_in_window(G, hwnd, text)
        if item is not None:
            return item
        time.sleep(0.2)
    return None


def _wait_tree(G, hwnd: int, pred, timeout: float = 5.0):
    """Poll the left-hand entity tree until a matching TreeItem appears."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            d = G._app_window(hwnd, "uia")
            for c in d.descendants(control_type="TreeItem"):
                try:
                    if c.rectangle().left < 250 and pred((c.window_text() or "").strip()):
                        return c
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.15)
    return None


def _win_stub(hwnd: int) -> dict:
    """Minimal window dict for the helpers that only need hwnd/pid."""
    import win32process
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return {"hwnd": hwnd, "pid": pid}


def _tree_item_contains(hwnd: int, needle: str):
    """First TreeItem whose text contains `needle` (case-insensitive)."""
    d = G._app_window(hwnd, "uia")
    for c in d.descendants(control_type="TreeItem"):
        try:
            if needle.lower() in (c.window_text() or "").lower():
                return c
        except Exception:  # noqa: BLE001
            pass
    return None


def _expand_node(G_mod, hwnd: int, needle: str, child_pred,
                 timeout: float = 5.0) -> bool:
    """Expand a tree node (triangle click + Right) only if its child is hidden."""
    import pyautogui
    if _wait_tree(G_mod, hwnd, child_pred, 0.2) is not None:
        return True
    node = _tree_item_contains(hwnd, needle)
    if node is None:
        print(f"tree node not found: {needle}", file=sys.stderr)
        return False
    r = node.rectangle()
    pyautogui.click(r.left + 8, (r.top + r.bottom) // 2)
    time.sleep(0.3)
    pyautogui.press("right")
    return _wait_tree(G_mod, hwnd, child_pred, timeout) is not None


def _save_and_wait(db: Path, hwnd: int, timeout: float = 30.0) -> bool:
    """File > Save (by menu name) and wait until the database mtime changes."""
    before = db.stat().st_mtime
    if not _file_save(_win_stub(hwnd)):
        print("File > Save failed", file=sys.stderr)
        return False
    end = time.time() + timeout
    while time.time() < end and db.stat().st_mtime <= before:
        time.sleep(0.5)
    saved = db.stat().st_mtime > before
    print(f"saved    : {saved}")
    return saved


def _open_edit_panel(G, hwnd: int) -> bool:
    """Entities tab -> expand Watertight hull definitions -> SOLID-01 > Edit."""
    import pyautogui

    G._focus(hwnd)
    if not _click_tab(hwnd, "Entities"):
        print("Entities tab not found", file=sys.stderr)
        return False
    t0 = time.time()
    item = _wait_tree_item(G, hwnd, "SOLID-01", 3.0)
    if item is None:
        _expand_node(G, hwnd, "Watertight hull",
                     lambda t: t == "SOLID-01", 5.0)
        item = _wait_tree_item(G, hwnd, "SOLID-01", 2.0)
    if item is None:
        print("SOLID-01 not found in the Entities tree", file=sys.stderr)
        return False
    print(f"tree     : SOLID-01 ready in {time.time() - t0:.2f}s")
    r = item.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.3)
    pyautogui.click(cx, cy, button="right")
    G.wait_until(lambda: any(w.get("class") == "QPopup" for w in G.windows()), 3.0, 0.1)
    try:
        pop = next((w for w in G.windows() if w.get("class") == "QPopup"), None)
        if pop is None:
            print("SOLID-01 context menu not found", file=sys.stderr)
            return False
        d = G._app_window(pop["hwnd"], "uia")
        for c in d.descendants(control_type="MenuItem"):
            if (c.window_text() or "").strip() == "Edit":
                c.click_input()
                break
    except Exception:  # noqa: BLE001
        print("could not click SOLID-01 > Edit", file=sys.stderr)
        return False
    # The editor is a docked panel; poll for it instead of always waiting 3 s.
    t0 = time.time()

    def _panel_ready() -> bool:
        d = G._app_window(hwnd, "uia")
        return any((c.window_text() or "").strip() == "Solid hull edition"
                   for c in d.descendants())

    if G.wait_until(_panel_ready, 15.0, 0.25):
        print(f"panel    : Solid hull edition (ready in {time.time() - t0:.2f}s)")
        return True
    print("Solid hull edition panel not found", file=sys.stderr)
    return False


def _panel_items(G, hwnd: int):
    """Visible rows of the Solid hull edition panel (text, rect)."""
    try:
        d = G._app_window(hwnd, "uia")
        out = []
        seen = {}
        for c in d.descendants(control_type="TreeItem"):
            try:
                r = c.rectangle()
                t = (c.window_text() or "").strip()
                if not t or r.left < 0 or r.top <= 100 or r.right >= 1200:
                    continue
                key = (t, int(r.top))
                if key not in seen or r.right > seen[key].right:
                    seen[key] = r
            except Exception:  # noqa: BLE001
                pass
        return [(t, r) for (t, _), r in seen.items()] if seen else []
    except Exception:  # noqa: BLE001
        return []


def _row(items, text: str, left_min: int, left_max: int):
    return next(((t, r) for t, r in items
                 if t == text and left_min <= r.left < left_max), None)


def _wait_panel_row(G_mod, hwnd: int, label: str, left_max: int = 150,
                    timeout: float = 8.0):
    """Poll the panel until a labelled row appears (panels render lazily)."""
    end = time.time() + timeout
    items = _panel_items(G_mod, hwnd)
    while time.time() < end:
        if _row(items, label, 0, left_max) is not None:
            return items
        time.sleep(0.25)
        items = _panel_items(G_mod, hwnd)
    return items


def _set_method_spaces(G, hwnd: int) -> bool:
    import pyautogui
    items = _panel_items(G, hwnd)
    mrow = _row(items, "Method", 0, 150)
    if mrow is None:
        print("Method row not found", file=sys.stderr)
        return False
    val = next(((t, r) for t, r in items
                if r.left > 100 and abs(r.top - mrow[1].top) < 12), None)
    if val and val[0] == "Spaces":
        print("method   : Spaces (already)")
        return True
    if val is None:
        print("Method value cell not found", file=sys.stderr)
        return False
    x = (val[1].left + val[1].right) // 2
    y = (val[1].top + val[1].bottom) // 2
    # Two separate clicks: a double-click can open and immediately close the
    # combo, especially when the panel has just been opened.
    pyautogui.click(x, y)
    time.sleep(0.5)
    pyautogui.click(x, y)
    end = time.time() + 3
    pop = None
    while time.time() < end:
        pop = next((w for w in G.windows() if w.get("class") == "QPopup"), None)
        if pop:
            break
        time.sleep(0.2)
    if pop is None:
        print("Method dropdown not found", file=sys.stderr)
        return False
    d = G._app_window(pop["hwnd"], "uia")
    for c in d.descendants(control_type="ListItem"):
        try:
            if (c.window_text() or "").strip() == "Spaces":
                c.click_input()
                break
        except Exception:  # noqa: BLE001
            pass
    time.sleep(2.5)
    items = _panel_items(G, hwnd)
    mrow = _row(items, "Method", 0, 150)
    val = next(((t, r) for t, r in items
                if r.left > 100 and abs(r.top - mrow[1].top) < 12), None) if mrow else None
    ok = bool(val and val[0] == "Spaces")
    print(f"method   : Spaces ({'set' if ok else 'failed'})")
    return ok


def _click_row_plus(G, rect) -> bool:
    """Click the green '+' anywhere in a panel row (column width varies)."""
    import pyautogui
    left, top = int(rect.left), int(rect.top)
    width, height = max(1, int(rect.right) - left), max(1, int(rect.bottom) - top)
    im = pyautogui.screenshot(region=(left, top, width, height))
    px = im.load()
    xs = []
    ys = []
    for y in range(0, im.height, 2):
        for x in range(0, im.width, 2):
            r, g, b = px[x, y][:3]
            if g > 90 and r < 90 and b < 90:   # the '+' icon is green
                xs.append(x)
                ys.append(y)
    if not xs:
        return False
    pyautogui.click(left + sum(xs) // len(xs), top + sum(ys) // len(ys))
    return True


def _tree_rect(d, text: str):
    for c in d.descendants(control_type="TreeItem"):
        try:
            if (c.window_text() or "").strip() == text:
                return c.rectangle()
        except Exception:  # noqa: BLE001
            pass
    return None


def _add_space(G, hwnd: int, name: str) -> bool:
    import pyautogui
    items = _panel_items(G, hwnd)
    srow = _row(items, "Spaces", 0, 100)
    if srow is None:
        print("Spaces row not found", file=sys.stderr)
        return False
    G._focus(hwnd)
    time.sleep(0.15)
    if not _click_row_plus(G, srow[1]):
        print("Spaces '+' not found in the row", file=sys.stderr)
        return False
    t0 = time.time()
    end = time.time() + 20
    win = None
    while time.time() < end:
        win = next((w for w in G.windows()
                    if w.get("title", "").startswith("Space selection")), None)
        if win:
            break
        time.sleep(0.2)
    if win is None:
        print("Space selection dialog not found", file=sys.stderr)
        return False
    print(f"dialog   : Space selection ready in {time.time() - t0:.2f}s")
    G._focus(win["hwnd"])
    time.sleep(0.15)
    # The dialog is small and the last SPC row can sit under the OK button.
    # Maximizing makes every row visible (checked on 2026-10-27).
    try:
        import win32con
        import win32gui
        win32gui.ShowWindow(win["hwnd"], win32con.SW_MAXIMIZE)
        time.sleep(0.8)
    except Exception:  # noqa: BLE001
        pass
    d = G._app_window(win["hwnd"], "uia")
    target = _tree_rect(d, name)
    if target is None:
        cargo = _tree_rect(d, "CARGO")
        if cargo is not None:
            pyautogui.click(int(cargo.left) + 10,
                            (int(cargo.top) + int(cargo.bottom)) // 2)
            time.sleep(0.6)
            pyautogui.press("right")
            time.sleep(1.0)
            # Re-open the UIA tree: the Qt accessibility cache may still show
            # CARGO as collapsed right after expanding it.
            d = G._app_window(win["hwnd"], "uia")
            target = _tree_rect(d, name)
    if target is None:
        print(f"{name} not listed in Space selection", file=sys.stderr)
        for c in d.descendants(control_type="Button"):
            if (c.window_text() or "").strip() == "Cancel":
                c.invoke()
                break
        return False
    pyautogui.click(int(target.left) + 6,
                    (int(target.top) + int(target.bottom)) // 2)
    time.sleep(0.8)
    for c in d.descendants(control_type="Button"):
        try:
            if (c.window_text() or "").strip() == "OK":
                c.invoke()
                break
        except Exception:  # noqa: BLE001
            pass
    # Poll until the dialog closes (or a validation box appears); the old
    # code always waited 2.5 s here.
    G.wait_until(lambda: (not any(w.get("title", "").startswith("Space selection")
                                 for w in G.windows()))
                 or any(w.get("title") in ("Warning", "Information") for w in G.windows()),
                 10.0, 0.2)
    # A validation box may appear when nothing got checked.
    for w in G.windows():
        if w.get("title") == "Space selection":
            txt = " | ".join(c.window_text()
                             for c in G._app_window(w["hwnd"], "uia").descendants(
                                 control_type="Text") if c.window_text())
            if "Please select space" in txt:
                print("Space selection rejected: nothing checked", file=sys.stderr)
                for c in G._app_window(w["hwnd"], "uia").descendants(control_type="Button"):
                    if (c.window_text() or "").strip() in ("Ok", "OK"):
                        c.invoke()
                        break
                return False
    items = _panel_items(G, hwnd)
    return any(t == name and r.left > 50 for t, r in items)


def _ensure_space(G, hwnd: int, name: str) -> bool:
    items = _panel_items(G, hwnd)
    if any(t == name and r.left > 50 for t, r in items):
        print(f"space    : {name} (already listed)")
        return True
    if not _add_space(G, hwnd, name):
        print(f"could not add space {name}", file=sys.stderr)
        return False
    print(f"space    : {name} (added)")
    return True


def _solid_info(db: Path) -> tuple[int, int]:
    """(DSG_SOLID_DIR rows, DSG_SOLID_HULL_SECTIONS rows)."""
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        n = con.execute("select count(*) from DSG_SOLID_DIR").fetchone()[0]
        h = con.execute("select count(*) from DSG_SOLID_HULL_SECTIONS").fetchone()[0]
        return n, h
    finally:
        con.close()


def _panel_button(G, hwnd: int, name: str):
    try:
        d = G._app_window(hwnd, "uia")
        for c in d.descendants(control_type="Button"):
            try:
                r = c.rectangle()
                if (c.window_text() or "").strip() == name and r.top > 880:
                    return c
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return None


def _click_btn(ctrl) -> bool:
    try:
        ctrl.invoke()
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        ctrl.click_input()
        return True
    except Exception:  # noqa: BLE001
        return False


def _answer_information(G, contains: str, answer: str = "Yes") -> bool:
    for w in G.windows():
        if w.get("title") not in ("Information", "Warning", "Please confirm..."):
            continue
        try:
            d = G._app_window(w["hwnd"], "uia")
        except Exception:  # noqa: BLE001
            continue
        txt = " | ".join(c.window_text() for c in d.descendants(control_type="Text")
                         if c.window_text())
        if contains.lower() not in txt.lower():
            continue
        G._focus(w["hwnd"])
        time.sleep(0.3)
        for c in d.descendants(control_type="Button"):
            if (c.window_text() or "").strip() == answer:
                c.invoke()
                print(f"prompt   : {txt[:60]} -> {answer}")
                time.sleep(1.0)
                return True
    return False


def _build_wh(G, hwnd: int, db: Path, timeout: float) -> bool:
    import pyautogui
    G._focus(hwnd)
    time.sleep(0.4)
    btn = _panel_button(G, hwnd, "Build WH")
    if btn is None:
        print("Build WH button not found", file=sys.stderr)
        return False
    if not _click_btn(btn):
        print("Build WH click failed", file=sys.stderr)
        return False
    print("build WH : started")
    # The Sections button becomes enabled once the solid exists.
    end = time.time() + timeout
    sections = None
    while time.time() < end:
        _dismiss_profile_warning(G)
        if any(w.get("title") == "Error" for w in G.windows()):
            break
        sections = _panel_button(G, hwnd, "Sections")
        try:
            if sections is not None and sections.is_enabled():
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    if sections is None or not sections.is_enabled():
        print("Build WH did not enable Sections (solid not built)", file=sys.stderr)
        return False
    print("build WH : solid ready")
    if not _click_btn(sections):
        print("Sections click failed", file=sys.stderr)
        return False
    time.sleep(1.5)
    _answer_information(G, "calculate the default sections", "Yes")
    end = time.time() + timeout
    while time.time() < end:
        if not _please_wait(G):
            break
        time.sleep(2)
    if any(w.get("title") == "Error" for w in G.windows()):
        return False
    print("sections : calculated")
    ok = _panel_button(G, hwnd, "Ok")
    if ok is None or not _click_btn(ok):
        print("panel Ok not found", file=sys.stderr)
        return False
    time.sleep(4)
    G._focus(hwnd)
    time.sleep(0.4)
    return _save_and_wait(db, hwnd)


def _open_hydro_calc(G, hwnd: int, name: str | None = None) -> str | None:
    """Calculations tab -> expand -> open an existing HYD-CALC node. Returns its name."""
    import pyautogui
    G._focus(hwnd)
    if not _click_tab(hwnd, "Calculations"):
        print("Calculations tab not found", file=sys.stderr)
        return None
    _expand_node(G, hwnd, "Naval Architecture",
                 lambda t: "Parallel hydrostatics" in t, 3.0)
    _expand_node(G, hwnd, "Parallel hydrostatics",
                 lambda t: t.startswith("HYD-CALC"), 3.0)
    node = _wait_tree(G, hwnd,
                      (lambda t: t == name) if name else (lambda t: t.startswith("HYD-CALC")),
                      5.0)
    if node is None:
        print("no HYD-CALC node found", file=sys.stderr)
        return None
    found = (node.window_text() or "").strip()
    r = node.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.click(cx, cy, button="right")
    G.wait_until(lambda: any(w.get("class") == "QPopup" for w in G.windows()), 3.0, 0.1)
    pop = next((w for w in G.windows() if w.get("class") == "QPopup"), None)
    if pop is None:
        print("HYD-CALC context menu not found", file=sys.stderr)
        return None
    d = G._app_window(pop["hwnd"], "uia")
    for c in d.descendants(control_type="MenuItem"):
        if (c.window_text() or "").strip() == "Edit":
            c.click_input()
            break
    end = time.time() + 15
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is not None:
            print(f"calc     : {found}")
            return found
        time.sleep(0.5)
    print("Hydrostatics edition panel not found", file=sys.stderr)
    return None


def _hydro_info(db: Path):
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        n = con.execute("select count(*) from DSG_HYD_RESULTS").fetchone()[0]
        row = con.execute(
            "select AFT_DRAFT, DISPLACEMENT, MOULDED_VOLUME, BLOCK_COEFF, KM_TRANSVERSAL "
            "from DSG_HYD_RESULTS order by abs(AFT_DRAFT-9.83) limit 1").fetchone()
        return n, row
    finally:
        con.close()


def _run_hydro(G, hwnd: int, db: Path, timeout: float) -> bool:
    import pyautogui
    btn = _panel_button(G, hwnd, "Calculate")
    if btn is None or not _click_btn(btn):
        print("Calculate button not found", file=sys.stderr)
        return False
    print("calc     : started")
    # The calculation dialog can take a few seconds to appear and ~1-2 minutes
    # for ~60 waterlines.  Wait for it to appear, then until it has been gone
    # for 3 consecutive checks (a single gap is not "done").
    end = time.time() + 15
    while time.time() < end:
        _dismiss_profile_warning(G)
        if _please_wait(G):
            break
        time.sleep(0.5)
    end = time.time() + timeout
    gone_since = None
    while time.time() < end:
        _dismiss_profile_warning(G)
        if _please_wait(G):
            gone_since = None
        else:
            if gone_since is None:
                gone_since = time.time()
            elif time.time() - gone_since >= 3:
                break
        time.sleep(1)
    for w in G.windows():
        if w.get("title") == "Error":
            try:
                txt = " | ".join(c.window_text()
                                 for c in G._app_window(w["hwnd"], "uia").descendants(
                                     control_type="Text") if c.window_text())
            except Exception:  # noqa: BLE001
                txt = ""
            print(f"calc error: {txt}", file=sys.stderr)
            for c in G._app_window(w["hwnd"], "uia").descendants(control_type="Button"):
                if (c.window_text() or "").strip().lower() == "ok":
                    c.invoke()
                    break
            return False
    print("calc     : results ready")
    ok = _panel_button(G, hwnd, "Ok")
    if ok is None or not _click_btn(ok):
        print("panel Ok not found", file=sys.stderr)
        return False
    # The panel must close before File > Save is meaningful.
    end = time.time() + 15
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is None:
            break
        time.sleep(0.5)
    if _panel_button(G, hwnd, "Calculate") is not None:
        ok = _panel_button(G, hwnd, "Ok")
        if ok is not None:
            _click_btn(ok)
            time.sleep(3)
    if _panel_button(G, hwnd, "Calculate") is not None:
        print("Hydrostatics panel did not close after Ok", file=sys.stderr)
        return False
    print("panel    : closed")
    time.sleep(2)
    G._focus(hwnd)
    time.sleep(0.4)
    return _save_and_wait(db, hwnd)


def cmd_hydro(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    running = [w for w in G.windows() if w.get("process", "").lower() == "fbasic.exe"
               or w.get("title", "").startswith("fbasic -")]
    if running:
        if not a.close_existing:
            print(f"FBASIC is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return 2
        _close(G)
        time.sleep(2)

    db = _prepare_db(a)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fbasic" / f"hydro_{stamp}"
    import foran_launch as L
    rc = L.main(["fbasic", "--workdir", str(run_dir)])
    if rc:
        _close(G)
        return 1
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    win = _wait_main(G, 60)
    if win is None:
        print("FBASIC main window not found", file=sys.stderr)
        _close(G)
        return 1
    time.sleep(2)
    _settle_warnings(G)
    if _open_hydro_calc(G, win["hwnd"], a.calc) is None:
        _close(G)
        return 1
    if not _run_hydro(G, win["hwnd"], db, a.timeout):
        _close(G)
        return 1
    n, row = _hydro_info(db)
    print(f"hyd rows : {n}")
    if row:
        print("9.83 m   : displacement={:.3f} t, volume={:.3f} m3, Cb={:.4f}, KM_T={:.4f}".format(
            row[1], row[2], row[3] or 0, row[4] or 0))
    if not a.keep_open:
        _close(G)
    else:
        print("keeping FBASIC open (--keep-open)")
    return 0


def _open_cross_calc(G, hwnd: int, name: str | None = None) -> str | None:
    """Calculations tab -> Cross curves: edit an existing KNS-CALC or create one."""
    import pyautogui
    G._focus(hwnd)
    if not _click_tab(hwnd, "Calculations"):
        print("Calculations tab not found", file=sys.stderr)
        return None
    cross = _wait_tree(G, hwnd, lambda t: t == "Cross curves", 3.0)
    if cross is None:
        _expand_node(G, hwnd, "Naval Architecture",
                     lambda t: t == "Cross curves", 3.0)
        cross = _wait_tree(G, hwnd, lambda t: t == "Cross curves", 3.0)
    node = None
    if cross is not None:
        # Expand Cross curves so existing KNS-CALC children are visible.
        r = cross.rectangle()
        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(0.2)
        pyautogui.press("right")
        if name:
            _wait_tree(G, hwnd, lambda t: t == name, 5.0)
        else:
            _wait_tree(G, hwnd, lambda t: t.startswith("KNS-CALC"), 5.0)
    d = G._app_window(hwnd, "uia")
    for c in d.descendants(control_type="TreeItem"):
        try:
            t = (c.window_text() or "").strip()
            r = c.rectangle()
            if r.left >= 250:
                continue
            if t == "Cross curves":
                cross = c
            elif name and t == name:
                node = c
            elif not name and t.startswith("KNS-CALC"):
                node = c
        except Exception:  # noqa: BLE001
            pass
    target = node or cross
    if target is None:
        print("Cross curves node not found", file=sys.stderr)
        return None
    found = (target.window_text() or "").strip()
    r = target.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.click(cx, cy, button="right")
    G.wait_until(lambda: any(w.get("class") == "QPopup" for w in G.windows()), 3.0, 0.1)
    pop = next((w for w in G.windows() if w.get("class") == "QPopup"), None)
    if pop is None:
        print("Cross curves context menu not found", file=sys.stderr)
        return None
    want = "Edit" if node is not None else "New calculation"
    d = G._app_window(pop["hwnd"], "uia")
    clicked = False
    for c in d.descendants(control_type="MenuItem"):
        if (c.window_text() or "").strip() == want:
            c.click_input()
            clicked = True
            break
    if not clicked:
        print(f"menu item {want!r} not found", file=sys.stderr)
        return None
    end = time.time() + 15
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is not None:
            print(f"calc     : {found} ({want})")
            return found
        time.sleep(0.5)
    print("Stability cross curves panel not found", file=sys.stderr)
    return None


def _displacement_values(G, hwnd: int) -> list[float]:
    items = _panel_items(G, hwnd)
    rows = sorted([r for t, r in items if t == "Displacement" and r.left < 150],
                  key=lambda r: r.top)
    out = []
    for r in rows:
        val = None
        for t, rr in items:
            if rr.left > 260 and abs(rr.top - r.top) < 2:
                m = re.match(r"([\d.]+)", t.strip())
                if m:
                    val = float(m.group(1))
                break
        out.append(val if val is not None else 0.0)
    return out


def _set_displacements(G, hwnd: int, values: list[float]) -> bool:
    """Add displacements through the input row (type value, then click '+').

    The Displacements table has a fixed input row (0.000) at the top; typing
    a value and clicking the row's green '+' commits it.  Clicking '+' without
    a value only adds blank rows, and editing committed rows makes the table
    re-sort/duplicate, so a new calculation is always built this way.
    """
    import pyautogui
    existing = [v for v in _displacement_values(G, hwnd) if v > 0]
    if existing:
        print("displ    : existing " + ", ".join(f"{v:g}" for v in existing) + " (kept)")
        return True
    # Create exactly len(values) blank rows, then fill each 0-valued row.
    # This mirrors the manually verified flow and leaves no extra 0 row
    # (a 0 row is rejected by FBASIC's displacement range check).
    for _ in range(20):
        items = _panel_items(G, hwnd)
        rows = [r for t, r in items if t == "Displacement" and r.left < 150]
        if len(rows) >= len(values):
            break
        srow = _row(items, "Displacements", 0, 100)
        if srow is None or not _click_row_plus(G, srow[1]):
            print("Displacements '+' not found", file=sys.stderr)
            return False
        time.sleep(1.2)
    if len(rows) != len(values):
        print(f"displ    : panel has {len(rows)} rows, expected {len(values)}",
              file=sys.stderr)
        return False
    for v in values:
        items = _panel_items(G, hwnd)
        rows = sorted([r for t, r in items if t == "Displacement" and r.left < 150],
                      key=lambda r: r.top)
        vals = _displacement_values(G, hwnd)
        zero = next((i for i, x in enumerate(vals) if x == 0), None)
        if zero is None or zero >= len(rows):
            print("no zero Displacement row to fill", file=sys.stderr)
            return False
        y = (rows[zero].top + rows[zero].bottom) // 2
        cells = [r for t, r in items
                 if r.left > 150 and abs(r.top - rows[zero].top) < 12]
        x = (cells[0].left + cells[0].right) // 2 if cells else 450
        pyautogui.click(x, y)
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.typewrite(str(v), interval=0.08)
        time.sleep(0.2)
        pyautogui.press("tab")
        time.sleep(0.8)
    got = [v for v in _displacement_values(G, hwnd) if v > 0]
    print("displ    : " + ", ".join(f"{v:g}" for v in got))
    return sorted(got) == sorted(values)


def _kns_info(db: Path):
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        n = con.execute("select count(*) from DSG_KNS_CALC_RESULT").fetchone()[0]
        row = con.execute(
            "select HEEL, DISP, KN from DSG_KNS_CALC_RESULT where abs(HEEL-5)<0.01 "
            "order by abs(DISP-20000) limit 1").fetchone()
        return n, row
    finally:
        con.close()


def _run_cross(G, hwnd: int, db: Path, timeout: float) -> bool:
    import pyautogui
    btn = _panel_button(G, hwnd, "Calculate")
    if btn is None or not _click_btn(btn):
        print("Calculate button not found", file=sys.stderr)
        return False
    print("calc     : started")
    end = time.time() + 15
    while time.time() < end:
        _dismiss_profile_warning(G)
        if _please_wait(G):
            break
        time.sleep(0.5)
    end = time.time() + timeout
    gone_since = None
    while time.time() < end:
        _dismiss_profile_warning(G)
        if _please_wait(G):
            gone_since = None
        else:
            if gone_since is None:
                gone_since = time.time()
            elif time.time() - gone_since >= 3:
                break
        time.sleep(1)
    for w in G.windows():
        if w.get("title") == "Error":
            try:
                txt = " | ".join(c.window_text()
                                 for c in G._app_window(w["hwnd"], "uia").descendants(
                                     control_type="Text") if c.window_text())
            except Exception:  # noqa: BLE001
                txt = ""
            print(f"calc error: {txt}", file=sys.stderr)
            return False
        if w.get("title") == "Warning":
            try:
                txt = " | ".join(c.window_text()
                                 for c in G._app_window(w["hwnd"], "uia").descendants(
                                     control_type="Text") if c.window_text())
            except Exception:  # noqa: BLE001
                txt = ""
            if "profile is not defined" in txt:
                continue
            print(f"calc warning: {txt}", file=sys.stderr)
            for c in G._app_window(w["hwnd"], "uia").descendants(control_type="Button"):
                if (c.window_text() or "").strip().lower() == "ok":
                    c.invoke()
                    break
            return False
    print("calc     : results ready")
    ok = _panel_button(G, hwnd, "Ok")
    if ok is None or not _click_btn(ok):
        print("panel Ok not found", file=sys.stderr)
        return False
    end = time.time() + 15
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is None:
            break
        time.sleep(0.5)
    if _panel_button(G, hwnd, "Calculate") is not None:
        ok = _panel_button(G, hwnd, "Ok")
        if ok is not None:
            _click_btn(ok)
            time.sleep(3)
    if _panel_button(G, hwnd, "Calculate") is not None:
        print("Cross curves panel did not close after Ok", file=sys.stderr)
        return False
    print("panel    : closed")
    time.sleep(2)
    G._focus(hwnd)
    time.sleep(0.4)
    return _save_and_wait(db, hwnd)


def cmd_cross(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    try:
        values = [float(x) for x in a.displacements.split(",") if x.strip()]
    except ValueError:
        raise SystemExit(f"--displacements must be comma numbers, got {a.displacements!r}")
    if len(values) < 5:
        raise SystemExit("FBASIC needs at least 5 displacements")
    running = [w for w in G.windows() if w.get("process", "").lower() == "fbasic.exe"
               or w.get("title", "").startswith("fbasic -")]
    if running:
        if not a.close_existing:
            print(f"FBASIC is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return 2
        _close(G)
        time.sleep(2)

    db = _prepare_db(a)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fbasic" / f"cross_{stamp}"
    import foran_launch as L
    rc = L.main(["fbasic", "--workdir", str(run_dir)])
    if rc:
        _close(G)
        return 1
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    win = _wait_main(G, 60)
    if win is None:
        print("FBASIC main window not found", file=sys.stderr)
        _close(G)
        return 1
    time.sleep(2)
    _settle_warnings(G)
    if _open_cross_calc(G, win["hwnd"], a.calc) is None:
        _close(G)
        return 1
    if not _set_displacements(G, win["hwnd"], values):
        _close(G)
        return 1
    if not _run_cross(G, win["hwnd"], db, a.timeout):
        _close(G)
        return 1
    n, row = _kns_info(db)
    print(f"kns rows : {n}")
    if row:
        print("sample   : heel={:.1f} deg, volume={:.1f} m3, KN={:.3f} m".format(*row))
    if not a.keep_open:
        _close(G)
    else:
        print("keeping FBASIC open (--keep-open)")
    return 0


def _open_capacity(G, hwnd: int, name: str | None = None) -> str | None:
    import pyautogui
    G._focus(hwnd)
    _dismiss_profile_warning(G)
    if not _click_tab(hwnd, "Calculations"):
        print("Calculations tab not found", file=sys.stderr)
        return None
    _expand_node(G, hwnd, "Naval Architecture",
                 lambda t: "Compartmentation" in t, 3.0)
    _dismiss_profile_warning(G)
    _expand_node(G, hwnd, "Compartmentation",
                 lambda t: t == "Capacities", 5.0)
    cap = _wait_tree(G, hwnd, lambda t: t == "Capacities", 5.0)
    _dismiss_profile_warning(G)
    node = None
    if cap is not None:
        r = cap.rectangle()
        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(0.2)
        pyautogui.press("right")
        if name:
            _wait_tree(G, hwnd, lambda t: t == name, 5.0)
        else:
            _wait_tree(G, hwnd, lambda t: t.startswith("CT-"), 5.0)
    d = G._app_window(hwnd, "uia")
    for c in d.descendants(control_type="TreeItem"):
        try:
            t = (c.window_text() or "").strip()
            r = c.rectangle()
            if r.left >= 250:
                continue
            if t == "Capacities":
                cap = c
            elif name and t == name:
                node = c
            elif not name and t.startswith("CT-"):
                node = c
        except Exception:  # noqa: BLE001
            pass
    target = node or cap
    if target is None:
        print("Capacities node not found", file=sys.stderr)
        return None
    found = (target.window_text() or "").strip()
    r = target.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.click(cx, cy, button="right")
    G.wait_until(lambda: any(w.get("class") == "QPopup" for w in G.windows()), 3.0, 0.1)
    pop = next((w for w in G.windows() if w.get("class") == "QPopup"), None)
    if pop is None:
        print("Capacities context menu not found", file=sys.stderr)
        return None
    want = "Edit" if node is not None else "New Capacity Table"
    d = G._app_window(pop["hwnd"], "uia")
    clicked = False
    for c in d.descendants(control_type="MenuItem"):
        if (c.window_text() or "").strip() == want:
            c.click_input()
            clicked = True
            break
    if not clicked:
        print(f"menu item {want!r} not found", file=sys.stderr)
        return None
    end = time.time() + 15
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is not None:
            print(f"capacity : {found} ({want})")
            return found
        time.sleep(0.5)
    print("Capacity table panel not found", file=sys.stderr)
    return None


def _maximize_front(hwnd: int) -> bool:
    """Bring the module to the front and keep the Claude terminal out of the way.

    Returns True only when `hwnd` is the foreground window, so callers never
    click into a window that is still covered by the terminal.
    """
    import win32con
    import win32gui
    try:
        import foran_focus as FF
        term = FF.find_terminal()
        if term:
            win32gui.ShowWindow(term["hwnd"], win32con.SW_MINIMIZE)
            time.sleep(0.2)
    except Exception:  # noqa: BLE001
        pass
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    except Exception:  # noqa: BLE001
        pass
    ok = False
    try:
        import foran_focus as FF
        ok = FF.focus(hwnd)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    return ok and int(win32gui.GetForegroundWindow()) == int(hwnd)


def _ensure_tree(G, hwnd: int) -> bool:
    """Open the Tree view dock only if no tree is visible.

    `dsgnewndtree` creates a *new* dock each time it is clicked, so clicking it
    unconditionally piles up Tree views and squeezes the calculation panels.
    """
    d = G._app_window(hwnd, "uia")
    try:
        for c in d.descendants(control_type="TreeItem"):
            r = c.rectangle()
            t = (c.window_text() or "").strip()
            if t in ("Ship", "Elements") and r.left < 250 and r.top > 100:
                return True
    except Exception:  # noqa: BLE001
        pass
    try:
        for c in d.descendants(control_type="Button"):
            if (c.window_text() or "").strip() == "dsgnewndtree":
                c.click_input()
                time.sleep(1.0)
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _click_calc_tab(G, hwnd: int) -> bool:
    """Click the Calculations dock tab (UIA first, then vision/coords)."""
    import pyautogui
    if _click_tab(hwnd, "Calculations"):
        print("tab      : Calculations (uia)")
        return True
    try:
        import win32gui
        import foran_vision as V
        tpl = Path(__file__).resolve().parent.parent / "templates" / "fbasic_calc_tab.png"
        shot = V.capture_window(hwnd)
        hit = V.find(tpl, shot, 0.75, (0.95, 1.0, 1.05))
        if hit:
            score, x, y, w, h, _scale = hit
            left, top, _r, _b = win32gui.GetWindowRect(hwnd)
            # Click inside the tab body (the probe verified x=25 works);
            # the far-right pixel of the template is the tab border.
            pyautogui.click(left + x + min(w - 2, 25), top + y + h // 2)
            print(f"tab      : Calculations (vision {score:.2f})")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"vision   : {exc}", file=sys.stderr)
    pyautogui.click(25, 320)
    return False


def _open_comp_calc(G, hwnd: int, node_text: str, new_item: str,
                    prefix: str, name: str | None = None) -> str | None:
    """Open a Compartmentation calculation panel (New or Edit).

    Used for Freeboard and Tonnage; the navigation is the same as Capacity:
    Calculations -> Naval Architecture -> Compartmentation -> <node>.
    """
    import pyautogui
    if not _maximize_front(hwnd):
        print("could not bring FBASIC to the foreground; not clicking", file=sys.stderr)
        return None
    _ensure_tree(G, hwnd)
    _dismiss_profile_warning(G)
    _click_calc_tab(G, hwnd)
    nav = _wait_tree(G, hwnd, lambda t: "Naval Architecture" in t, 3.0)
    if nav is None:
        print("Naval Architecture node not found", file=sys.stderr)
        return None
    r = nav.rectangle()
    pyautogui.click(r.left + 8, (r.top + r.bottom) // 2)
    time.sleep(0.3)
    pyautogui.press("right")
    _dismiss_profile_warning(G)
    comp = _wait_tree(G, hwnd, lambda t: "Compartmentation" in t, 3.0)
    if comp is None:
        print("Compartmentation node not found", file=sys.stderr)
        return None
    r = comp.rectangle()
    pyautogui.click(r.left + 8, (r.top + r.bottom) // 2)
    time.sleep(0.3)
    pyautogui.press("right")
    node = _wait_tree(G, hwnd, lambda t: t == node_text, 5.0)
    _dismiss_profile_warning(G)
    if node is None:
        print(f"{node_text} node not found", file=sys.stderr)
        return None
    r = node.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.2)
    pyautogui.press("right")
    existing = _wait_tree(
        G, hwnd,
        (lambda t: t == name) if name else (lambda t: t.startswith(prefix)),
        5.0)
    target = existing or node
    found = (target.window_text() or "").strip()
    r = target.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.click(cx, cy, button="right")
    G.wait_until(lambda: any(w.get("class") == "QPopup" for w in G.windows()), 3.0, 0.1)
    pop = next((w for w in G.windows() if w.get("class") == "QPopup"), None)
    if pop is None:
        print(f"{node_text} context menu not found", file=sys.stderr)
        return None
    want = "Edit" if existing is not None else new_item
    clicked = False
    for c in G._app_window(pop["hwnd"], "uia").descendants(control_type="MenuItem"):
        text = (c.window_text() or "").strip()
        match = text == want
        if not match and existing is None:
            # Menu labels vary in case ("New freeboard calculation").
            match = text.lower().startswith("new") and node_text.lower() in text.lower()
        if match:
            c.click_input()
            clicked = True
            break
    if not clicked:
        print(f"menu item {want!r} not found", file=sys.stderr)
        return None
    end = time.time() + 20
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is not None:
            print(f"{node_text.lower():<9}: {found} ({want})")
            return found
        time.sleep(0.5)
    print(f"{node_text} panel not found", file=sys.stderr)
    return None


def _set_row_value(G, hwnd: int, label: str, value: str) -> bool:
    import pyautogui
    _dismiss_profile_warning(G)
    items = _wait_panel_row(G, hwnd, label, 150)
    row = _row(items, label, 0, 150)
    if row is None:
        print(f"{label} row not found (enlarge the calculation panel if it is docked short)", file=sys.stderr)
        return False
    val = next(((t, r) for t, r in items
                if r.left > 150 and abs(r.top - row[1].top) < 12), None)
    if val is None:
        print(f"{label} value cell not found", file=sys.stderr)
        return False
    vr = val[1]
    pyautogui.click((vr.left + vr.right) // 2, (vr.top + vr.bottom) // 2)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(value, interval=0.08)
    time.sleep(0.2)
    pyautogui.press("tab")
    time.sleep(0.6)
    return True


def _select_capacity_spaces(G, hwnd: int, names: list[str],
                            row_label: str = "Spaces", verify: bool = True) -> bool:
    import pyautogui
    _dismiss_profile_warning(G)
    items = _wait_panel_row(G, hwnd, row_label, 100)
    have = {t for t, r in items if t in names and r.left > 30}
    if all(n in have for n in names):
        print("spaces   : existing " + ", ".join(names))
        return True
    srow = _row(items, row_label, 0, 100)
    if srow is None:
        print(f"{row_label} row not found (enlarge the calculation panel if it is docked short)", file=sys.stderr)
        return False
    if not _click_row_plus(G, srow[1]):
        print("Spaces '+' not found", file=sys.stderr)
        return False
    time.sleep(2.0)
    win = None
    end = time.time() + 20
    while time.time() < end:
        win = next((w for w in G.windows() if w.get("title") == "Spaces selection"), None)
        if win:
            break
        time.sleep(0.4)
    if win is None:
        print("Spaces selection dialog not found", file=sys.stderr)
        return False
    G._focus(win["hwnd"])
    time.sleep(0.4)
    try:
        import win32con
        import win32gui
        win32gui.ShowWindow(win["hwnd"], win32con.SW_MAXIMIZE)
        time.sleep(0.8)
    except Exception:  # noqa: BLE001
        pass
    d = G._app_window(win["hwnd"], "uia")
    for c in d.descendants(control_type="Button"):
        if (c.window_text() or "").strip() == "Expand":
            c.invoke()
            break
    time.sleep(1.0)
    d = G._app_window(win["hwnd"], "uia")
    for name in names:
        target = None
        for c in d.descendants(control_type="TreeItem"):
            try:
                if (c.window_text() or "").strip() == name:
                    target = c.rectangle()
                    break
            except Exception:  # noqa: BLE001
                pass
        if target is None:
            print(f"{name} not listed in Spaces selection", file=sys.stderr)
            return False
        pyautogui.click(int(target.left) + 10,
                        (int(target.top) + int(target.bottom)) // 2)
        time.sleep(0.5)
    for c in d.descendants(control_type="Button"):
        if (c.window_text() or "").strip() == "OK":
            c.invoke()
            break
    time.sleep(2.0)
    print("spaces   : " + ", ".join(names))
    if not verify:
        return True
    items = _panel_items(G, hwnd)
    have = {t for t, r in items if r.left > 30}
    missing = [n for n in names if n not in have]
    if missing:
        print("spaces   : missing " + ", ".join(missing), file=sys.stderr)
        return False
    return True


def _capture_window(hwnd: int):
    """Capture a window with PrintWindow (works even if it is occluded)."""
    import ctypes
    import win32gui
    import win32ui
    from PIL import Image
    wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
    w, h = wr - wl, wb - wt
    if w <= 0 or h <= 0:
        return None
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    try:
        ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                              bits, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mem.DeleteDC()
        src.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)
    return im


def _progress_fraction(G) -> float:
    """Green fraction of the capacity progress bar (0..1).

    Uses PrintWindow so an occluding terminal does not hide the dialog.
    The bar is the only green element; take its most common row and measure
    the filled width against the bar's full width.
    """
    import pyautogui
    from collections import Counter
    w = next((x for x in G.windows() if "please wait" in x["title"].lower()), None)
    if w is None:
        return -1.0
    im = None
    try:
        im = _capture_window(w["hwnd"])
    except Exception:  # noqa: BLE001
        im = None
    left, top, right, bottom = w["rect"]
    if im is None or im.width < 50 or im.height < 50:
        G._focus(w["hwnd"])
        time.sleep(0.15)
        try:
            im = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
        except Exception:  # noqa: BLE001
            return 0.0
    px = im.load()
    coords = []
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y][:3]
            if g > 100 and r < 100 and b < 100:
                coords.append((x, y))
    if not coords:
        return 0.0
    y = Counter(yy for _, yy in coords).most_common(1)[0][0]
    xs = [x for x, yy in coords if yy == y]
    x0 = min(xs)
    total = max(1, (right - left) - 99)   # 509-wide dialog -> 410 px bar
    filled = sum(1 for x in xs if x0 <= x < x0 + total)
    return filled / total


def _run_capacity(G, hwnd: int, db: Path, timeout: float) -> bool:
    import pyautogui
    btn = _panel_button(G, hwnd, "Calculate")
    if btn is None or not _click_btn(btn):
        print("Calculate button not found", file=sys.stderr)
        return False
    print("calc     : started")
    end = time.time() + timeout
    closed = False
    while time.time() < end:
        _dismiss_profile_warning(G)
        w = next((x for x in G.windows() if "please wait" in x["title"].lower()), None)
        if w is None:
            time.sleep(1)
            if not any("please wait" in x["title"].lower() for x in G.windows()):
                break
            continue
        frac = _progress_fraction(G)
        if frac >= 0.90:
            G._focus(w["hwnd"])
            time.sleep(0.3)
            d = G._app_window(w["hwnd"], "uia")
            for c in d.descendants(control_type="Button"):
                if (c.window_text() or "").strip() == "Close":
                    c.invoke()
                    closed = True
                    break
            if closed:
                print(f"progress : {frac * 100:.0f}% -> Close")
                time.sleep(2)
                break
        time.sleep(2)
    for w in G.windows():
        if w.get("title") == "Error":
            try:
                txt = " | ".join(c.window_text()
                                 for c in G._app_window(w["hwnd"], "uia").descendants(
                                     control_type="Text") if c.window_text())
            except Exception:  # noqa: BLE001
                txt = ""
            print(f"calc error: {txt}", file=sys.stderr)
            return False
    print("calc     : finished")
    ok = _panel_button(G, hwnd, "Ok")
    if ok is None or not _click_btn(ok):
        print("panel Ok not found", file=sys.stderr)
        return False
    end = time.time() + 15
    while time.time() < end:
        if _panel_button(G, hwnd, "Calculate") is None:
            break
        time.sleep(0.5)
    print("panel    : closed")
    time.sleep(2)
    G._focus(hwnd)
    time.sleep(0.4)
    return _save_and_wait(db, hwnd)


def _ct_info(db: Path):
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        n = con.execute("select count(*) from DSG_CT_DATA").fetchone()[0]
        s = con.execute("select count(*) from DSG_CT_SPACES").fetchone()[0]
        row = con.execute("select WATERLINE_LEVELS, WATERLINE_SPACING, DENSITY "
                          "from DSG_CT_DATA limit 1").fetchone()
        return n, s, row
    finally:
        con.close()


def cmd_capacity(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    spaces = [x.strip() for x in a.spaces.split(",") if x.strip()]
    if not spaces:
        raise SystemExit("--spaces needs at least one SPC name")
    running = [w for w in G.windows() if w.get("process", "").lower() == "fbasic.exe"
               or w.get("title", "").startswith("fbasic -")]
    if running:
        if not a.close_existing:
            print(f"FBASIC is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return 2
        _close(G)
        time.sleep(2)

    db = _prepare_db(a)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fbasic" / f"capacity_{stamp}"
    import foran_launch as L
    rc = L.main(["fbasic", "--workdir", str(run_dir)])
    if rc:
        _close(G)
        return 1
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    win = _wait_main(G, 60)
    if win is None:
        print("FBASIC main window not found", file=sys.stderr)
        _close(G)
        return 1
    time.sleep(2)
    _settle_warnings(G)
    if _open_capacity(G, win["hwnd"], a.calc) is None:
        _close(G)
        return 1
    if not _set_row_value(G, win["hwnd"], "Number of levels", str(a.levels)):
        _close(G)
        return 1
    if not _set_row_value(G, win["hwnd"], "Spacing", f"{a.spacing:g}"):
        _close(G)
        return 1
    if not _select_capacity_spaces(G, win["hwnd"], spaces):
        _close(G)
        return 1
    if not _run_capacity(G, win["hwnd"], db, a.timeout):
        _close(G)
        return 1
    n, s, row = _ct_info(db)
    print(f"ct rows  : data={n}, spaces={s}")
    if row:
        print("ct input : levels={}, spacing={} m, density={}".format(*row))
    if not a.keep_open:
        _close(G)
    else:
        print("keeping FBASIC open (--keep-open)")
    return 0


def _launch_calc(a, G, tag: str):
    """Launch FBASIC with `a.db`, fill the DB dialog, return (db, main_window, run_dir)."""
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return None, None, None
    running = [w for w in G.windows() if w.get("process", "").lower() == "fbasic.exe"
               or w.get("title", "").startswith("fbasic -")]
    if running:
        if not a.close_existing:
            print(f"FBASIC is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return None, None, None
        _close(G)
        time.sleep(2)
    db = _prepare_db(a)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fbasic" / f"{tag}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    import foran_launch as L
    rc = L.main(["fbasic", "--workdir", str(run_dir)])
    if rc:
        _close(G)
        return None, None, None
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close(G)
        return None, None, None
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    win = _wait_main(G, 60)
    if win is None:
        print("FBASIC main window not found", file=sys.stderr)
        _close(G)
        return None, None, None
    time.sleep(2)
    _settle_warnings(G)
    return db, win, run_dir


def _freeboard_info(db: Path) -> tuple[int, int]:
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        d = con.execute("select count(*) from DSG_FREEBOARD_DATA").fetchone()[0]
        r = con.execute("select count(*) from DSG_FREEBOARD_RESULTS").fetchone()[0]
        return d, r
    finally:
        con.close()


def _tonnage_info(db: Path):
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("select OID,NAME from DSG_CALC_TREE "
                           "where NAME like 'TONN-%' order by OID").fetchall()
    finally:
        con.close()


def cmd_freeboard(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    db, win, _run_dir = _launch_calc(a, G, "freeboard")
    if db is None:
        return 1
    hwnd = win["hwnd"]
    if _open_comp_calc(G, hwnd, "Freeboard", "New Freeboard calculation",
                       "FB-", a.calc) is None:
        _close(G)
        return 1
    if not _run_capacity(G, hwnd, db, a.timeout):
        _close(G)
        return 1
    data, results = _freeboard_info(db)
    print(f"freeboard: data={data}, results={results}")
    if not a.keep_open:
        _close(G)
    else:
        print("keeping FBASIC open (--keep-open)")
    return 0 if data > 0 and results > 0 else 1


def cmd_tonnage(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    spaces = [x.strip() for x in a.spaces.split(",") if x.strip()]
    if not spaces:
        raise SystemExit("--spaces needs at least one SPC name")
    db, win, _run_dir = _launch_calc(a, G, "tonnage")
    if db is None:
        return 1
    hwnd = win["hwnd"]
    if _open_comp_calc(G, hwnd, "Tonnage", "New Tonnage calculation",
                       "TONN-", a.calc) is None:
        _close(G)
        return 1
    if not _select_capacity_spaces(G, hwnd, spaces, row_label="Included spaces",
                                   verify=False):
        _close(G)
        return 1
    if not _run_capacity(G, hwnd, db, a.timeout):
        _close(G)
        return 1
    nodes = _tonnage_info(db)
    print("tonnage  : " + (", ".join(f"{n} (OID {o})" for o, n in nodes) or "no TONN node"))
    if not a.keep_open:
        _close(G)
    else:
        print("keeping FBASIC open (--keep-open)")
    return 0 if nodes else 1


# ---------------------------------------------------------------- stability
# LSW / loading-condition flows verified 2026-10-27 on V80R3.0 (1920x1080).
# Menu offsets are measured from the top of each QPopup, in physical pixels.

_LSW_NODE_MENU = {"new_node": 54, "new_complex": 91, "new_distribution": 124,
                  "paste": 160, "import": 199, "properties": 238}
_LSW_MENU = {"copy": 46, "report": 76, "drawing": 105, "export": 133,
             "rename": 168, "edit_complex": 232, "edit_distribution": 267,
             "set_active": 301, "delete": 336, "properties": 371}
_LC_NODE_MENU = {"new_node": 44, "new_lc": 88, "import": 122,
                 "calculate": 160, "paste": 201, "properties": 238}
_FILE_MENU = {"save": 27, "reload": 59, "lock_all": 91, "deactivate": 130,
              "import_export": 168, "fdm": 207, "exit": 248}


def _window_pid(win) -> int:
    return int(win["pid"])


def _snap(hwnd: int, path: Path) -> None:
    """Best-effort screenshot of a window (diagnostics only)."""
    try:
        import cv2
        from foran_vision import capture_window
        cv2.imwrite(str(path), capture_window(hwnd))
    except Exception:  # noqa: BLE001
        pass


def _find_window(title: str, pid: int | None = None, timeout: float = 30.0,
                 prefix: bool = False):
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            t = w.get("title", "")
            if pid is not None and w.get("pid") != pid:
                continue
            if (t.startswith(title) if prefix else t == title):
                return w
        time.sleep(0.2)
    return None


def _focus_window(hwnd: int, tries: int = 6) -> bool:
    """Focus a dialog without maximizing it (maximizing breaks Qt dialogs)."""
    import win32gui
    import foran_focus as FF
    for _ in range(tries):
        FF.focus(hwnd)
        time.sleep(0.25)
        if int(win32gui.GetForegroundWindow()) == int(hwnd):
            return True
    return False


def _front_main(win, tries: int = 6) -> bool:
    import win32gui
    for _ in range(tries):
        if _maximize_front(win["hwnd"]):
            return True
        time.sleep(0.3)
    return int(win32gui.GetForegroundWindow()) == int(win["hwnd"])


def _invoke(hwnd: int, names=("Ok", "OK", "Yes", "Close", "Cancel")) -> str | None:
    try:
        d = G._app_window(hwnd, "uia")
        for c in d.descendants(control_type="Button"):
            txt = (c.window_text() or "").strip()
            if txt in names:
                c.invoke()
                return txt
    except Exception:  # noqa: BLE001
        pass
    return None


def _click_tab(hwnd: int, name: str) -> bool:
    """Click the visible dock tab `name` (the top dock when two are shown)."""
    d = G._app_window(hwnd, "uia")
    tabs = [c for c in d.descendants(control_type="TabItem")
            if (c.window_text() or "").strip() == name
            and c.rectangle().top < 700]
    if not tabs:
        return False
    tabs.sort(key=lambda c: c.rectangle().top)
    tabs[0].click_input()
    time.sleep(1.2)
    return True


def _tree_item(hwnd: int, text: str, top_min: int | None = None):
    d = G._app_window(hwnd, "uia")
    items = []
    for c in d.descendants(control_type="TreeItem"):
        if (c.window_text() or "").strip() != text:
            continue
        if top_min is not None and c.rectangle().top < top_min:
            continue
        items.append(c)
    if not items:
        return None
    items.sort(key=lambda c: (c.rectangle().top, c.rectangle().left))
    return items[0]


def _tree_item_matching(hwnd: int, pattern: str, top_min: int | None = None):
    d = G._app_window(hwnd, "uia")
    for c in d.descendants(control_type="TreeItem"):
        txt = (c.window_text() or "").strip()
        if re.fullmatch(pattern, txt) and (
                top_min is None or c.rectangle().top >= top_min):
            return c
    return None


def _expand_item(hwnd: int, text: str) -> bool:
    t = _tree_item(hwnd, text)
    if t is None:
        return False
    t.click_input()
    time.sleep(0.2)
    t.click_input(double=True)
    time.sleep(1.0)
    return True


def _ensure_expanded(hwnd: int, text: str, pattern: str) -> bool:
    """Expand a node idempotently (double-click on an open node collapses it)."""
    if _tree_item_matching(hwnd, pattern) is not None:
        return True
    t = _tree_item(hwnd, text)
    if t is None:
        return False
    for _ in range(2):
        t.click_input()
        time.sleep(0.2)
        t.click_input(double=True)
        time.sleep(0.9)
        if _tree_item_matching(hwnd, pattern) is not None:
            return True
    return False


def _context_menu(win, text: str, top_min: int | None = None):
    t = _tree_item(win["hwnd"], text, top_min)
    if t is None:
        print(f"tree item not found: {text}", file=sys.stderr)
        try:
            print(f"tree items: {_tree_lsw_names(win['hwnd'])}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        return None
    t.click_input()
    time.sleep(0.2)
    t.click_input(button="right")
    end = time.time() + 3.0
    while time.time() < end:
        ps = [w for w in G.windows() if w.get("class") == "QPopup"
              and w.get("pid") == _window_pid(win)]
        if ps:
            return ps[0]
        time.sleep(0.1)
    print(f"context menu did not open for {text}", file=sys.stderr)
    return None


def _popup_items(popup) -> list[tuple[str, tuple[int, int, int, int]]]:
    """MenuItem/ListItem texts + rectangles exposed by a QPopup."""
    return UI.popup_items(G, popup)


def _popup_click(popup, rel_y: int, x_off: int = 170) -> None:
    UI.click_popup(popup, rel_y, x_off)


def _menu_key(txt: str) -> str:
    return UI.menu_key(txt)


def _popup_pick(popup, name: str, rel_y: int, x_off: int = 170) -> None:
    """Click a context-menu entry by UIA name when possible, else by offset."""
    UI.pick_popup_item(G, popup, name, rel_y, x_off)


def _file_action(win, rel_y: int, name: str | None = None) -> bool:
    hwnd = win["hwnd"]
    if not _front_main(win):
        print("FBASIC is not foreground; refusing to use the File menu", file=sys.stderr)
        return False
    d = G._app_window(hwnd, "uia")
    file_item = next((c for c in d.descendants(control_type="MenuItem")
                      if _menu_key(c.window_text() or "") == "file"), None)
    if file_item is None:
        return False
    file_item.click_input()
    end = time.time() + 3.0
    while time.time() < end:
        ps = [w for w in G.windows() if w.get("class") == "QPopup"
              and w.get("pid") == _window_pid(win)]
        if ps:
            if name:
                _popup_pick(ps[0], name, rel_y, x_off=80)
            else:
                _popup_click(ps[0], rel_y, x_off=80)
            time.sleep(0.4)
            return True
        time.sleep(0.1)
    return False


def _file_save(win) -> bool:
    return _file_action(win, _FILE_MENU["save"], "Save")


def _exit_app(win) -> bool:
    """File > Exit, answering Yes to the modified-tree prompt."""
    pid = _window_pid(win)
    _file_action(win, _FILE_MENU["exit"], "Exit")
    end = time.time() + 20.0
    while time.time() < end:
        alive = [w for w in G.windows() if w.get("pid") == pid]
        if not alive:
            return True
        for w in list(alive):
            title = w.get("title", "")
            if title in ("Information modified", "Information", "Warning", "Error"):
                if title == "Information modified":
                    _invoke(w["hwnd"], names=("Yes",))
                else:
                    _invoke(w["hwnd"], names=("Ok", "OK", "Close"))
                time.sleep(0.4)
        # a nested confirmation can appear after the first one
        es = [w for w in G.windows() if w.get("pid") == pid
              and w.get("title") == "Information modified"]
        for w in es:
            _invoke(w["hwnd"], names=("Yes",))
            time.sleep(0.4)
        time.sleep(0.3)
    return not [w for w in G.windows() if w.get("pid") == pid]


def _paste_text(hwnd: int, x: int, y: int, text: str,
                select_all: bool = False) -> None:
    import pyautogui
    import pyperclip
    pyautogui.click(x, y)
    time.sleep(0.25)
    if select_all:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.0)


def _table_rect(hwnd: int):
    d = G._app_window(hwnd, "uia")
    tables = [c for c in d.descendants(control_type="Table")]
    if not tables:
        return None
    tables.sort(key=lambda c: (c.rectangle().right - c.rectangle().left)
                * (c.rectangle().bottom - c.rectangle().top), reverse=True)
    return tables[0].rectangle()


def _labeled_edit(hwnd: int, label: str):
    """Find the Edit control to the right of a `Text` label on the same row."""
    return UI.labeled_edit(G, hwnd, label)


def _row_tops(hwnd: int) -> list[int]:
    d = G._app_window(hwnd, "uia")
    tops = sorted({round(c.rectangle().top / 5) * 5
                   for c in d.descendants(control_type="DataItem")})
    return tops


def _tree_lsw_names(hwnd: int) -> list[str]:
    d = G._app_window(hwnd, "uia")
    return sorted({(c.window_text() or "").strip()
                   for c in d.descendants(control_type="TreeItem")
                   if re.fullmatch(r"LSW-\d+", (c.window_text() or "").strip())})


def _lsw_names(db: Path) -> list[str]:
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        return [r[0] for r in con.execute(
            "select NAME from DSG_LSW_PROJECT order by OID")]
    finally:
        con.close()


def _lsw_info(db: Path, name: str | None = None):
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        if name is None:
            row = con.execute("select NAME from DSG_LSW_TREE where PARENT_OID is null "
                              "order by OID desc limit 1").fetchone()
            name = row[0] if row else None
        if not name:
            return None
        row = con.execute("select OID, WEIGHT from DSG_LSW_TREE where NAME=? "
                          "and PARENT_OID is null order by OID desc limit 1",
                          (name,)).fetchone()
        if not row:
            return None
        root, weight = row
        link = con.execute("select ENT_TREE_OID from DSG_ENT_LSW_LINK "
                           "where LSW_TREE_OID=?", (root,)).fetchone()
        ent = link[0] if link else None
        dist = tot = 0
        total = None
        if ent is not None:
            dist = con.execute("select count(*) from DSG_LSW_DIST_RESULTS "
                               "where ENT_OID=?", (ent,)).fetchone()[0]
            row = con.execute("select count(*) from DSG_LSW_DIST_TOTAL_RESULTS "
                              "where ENT_OID=?", (ent,)).fetchone()
            tot = row[0] if row else 0
            total = con.execute("select LOCAL_WEIGHT, XCG_LOCAL_WEIGHT "
                                "from DSG_LSW_DIST_TOTAL_RESULTS where ENT_OID=?",
                                (ent,)).fetchone()
        return {"name": name, "root": root, "weight": weight,
                "dist": dist, "total_rows": tot, "total": total}
    finally:
        con.close()


def _lc_info(db: Path, oid: int | None = None):
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        if oid is None:
            row = con.execute("select max(OID) from DSG_LOAD_COND").fetchone()
            oid = row[0] if row else None
        if oid is None:
            return None
        row = con.execute("select INT_TREE_OID, CALCULATED from DSG_LOAD_COND "
                          "where OID=?", (oid,)).fetchone()
        if not row:
            return None
        int_oid, calculated = row
        name = con.execute("select NAME from DSG_INT_TREE where OID=?",
                           (int_oid,)).fetchone()
        loads = con.execute("select NAME, WEIGHT, X_COG, Z_COG from DSG_LOCAL_LOAD "
                            "where INT_TREE_OID=?", (int_oid,)).fetchall()
        return {"oid": oid, "name": name[0] if name else None,
                "calculated": calculated, "loads": loads}
    finally:
        con.close()


def _lsw_dialogs(pid: int):
    return [w for w in G.windows() if w.get("pid") == pid and w.get("title") in (
        "Lightship weight distribution definition",
        "Lightship weight distribution edition",
        "Lightship weight distribution",
        "Warning", "Information", "Error")]


def _abort_app(G_mod, win) -> None:
    """Cancel any LSW/LC dialog (modal dialogs block the main-window close)."""
    pid = win.get("pid")
    for w in [x for x in G_mod.windows() if x.get("pid") == pid]:
        if w.get("title") in ("Lightship weight distribution definition",
                              "Lightship weight distribution edition",
                              "Lightship weight distribution",
                              "Loading condition calculation"):
            _invoke(w["hwnd"], names=("Cancel", "Close"))
    time.sleep(0.8)
    _close(G_mod)


def _dismiss_modal(win, seconds: float = 20.0) -> None:
    """Dismiss Warning/Information/Error dialogs until they stop appearing."""
    pid = _window_pid(win)
    end = time.time() + seconds
    while time.time() < end:
        mods = [w for w in G.windows() if w.get("pid") == pid and w.get("title") in (
            "Warning", "Information", "Error", "Information modified")]
        if not mods:
            return
        for w in mods:
            if w.get("title") == "Information modified":
                _invoke(w["hwnd"], names=("Yes",))
            else:
                _invoke(w["hwnd"], names=("Ok", "OK", "Close"))
        time.sleep(0.5)


def _cmd_lsw_impl(a, G_mod) -> int:
    global G
    G = G_mod
    tsv = Path(a.tsv).expanduser().resolve()
    if not tsv.is_file():
        print(f"tsv not found: {tsv}", file=sys.stderr)
        return 2
    text = tsv.read_text(encoding="utf-8").rstrip("\n")
    lines = [ln for ln in text.splitlines() if ln.strip("\t ")]
    if not lines:
        print("tsv is empty", file=sys.stderr)
        return 2
    total_weight = 0.0
    for ln in lines:
        cols = ln.split("\t")
        if len(cols) < 5:
            print(f"tsv row has fewer than 5 columns: {ln!r}", file=sys.stderr)
            return 2
        total_weight += float(cols[4])

    db, win, run_dir = _launch_calc(a, G, "lsw")
    if db is None:
        return 1
    hwnd = win["hwnd"]
    _settle_warnings(G)
    _ensure_tree(G, hwnd)
    if not _front_main(win):
        print("FBASIC is not foreground; aborting before any click", file=sys.stderr)
        _abort_app(G, win)
        return 1
    if not _click_tab(hwnd, "Entities"):
        print("Entities tab not found", file=sys.stderr)
        _abort_app(G, win)
        return 1
    if not _ensure_expanded(hwnd, "Lightship weight distribution", r"LSW-\d+"):
        print("Lightship weight distribution node not found", file=sys.stderr)
        _abort_app(G, win)
        return 1

    before = set(_tree_lsw_names(hwnd))
    popup = _context_menu(win, "Lightship weight distribution")
    if popup is None:
        _abort_app(G, win)
        return 1
    _popup_pick(popup, "New distribution", _LSW_NODE_MENU["new_distribution"])
    dlg = _find_window("Lightship weight distribution definition",
                       _window_pid(win), timeout=15)
    if dlg is None:
        print("definition dialog did not open", file=sys.stderr)
        _abort_app(G, win)
        return 1
    dlg_hwnd = dlg["hwnd"]
    if not _focus_window(dlg_hwnd):
        print("definition dialog did not come to the foreground", file=sys.stderr)
        _abort_app(G, win)
        return 1

    if a.name:
        # Qt QLineEdit defaults to the next auto name, so select all first.
        edit = _labeled_edit(dlg_hwnd, "Name")
        if edit is None:
            edits = [c for c in G._app_window(dlg_hwnd, "uia")
                     .descendants(control_type="Edit")]
            edit = edits[0] if edits else None
        if edit is not None:
            r = edit.rectangle()
            _paste_text(dlg_hwnd, r.left + 20, r.top + 10, a.name,
                        select_all=True)
            time.sleep(0.3)
            _snap(dlg_hwnd, run_dir / "def_name.png")

    rect = _table_rect(dlg_hwnd)
    if rect is None:
        print("definition table not found", file=sys.stderr)
        _abort_app(G, win)
        return 1
    _paste_text(dlg_hwnd, rect.left + 84, rect.top + 53, text)
    rows = len(_row_tops(dlg_hwnd))
    print(f"pasted   : {rows} visible rows ({len(lines)} in tsv)")
    if rows == 0:
        print("paste did not produce any rows", file=sys.stderr)
        _abort_app(G, win)
        return 1
    # Move focus out of the table so a pending cell edit is committed.
    d = G._app_window(dlg_hwnd, "uia")
    edits = [c for c in d.descendants(control_type="Edit")]
    if edits:
        r = edits[0].rectangle()
        import pyautogui
        pyautogui.click(r.left + 10, r.top + 10)
        time.sleep(0.6)
    accepted = False
    for attempt in range(2):
        if _invoke(dlg_hwnd, names=("Ok",)) is None:
            print("Ok button not found in the definition dialog", file=sys.stderr)
            _abort_app(G, win)
            return 1
        end = time.time() + 8
        while time.time() < end:
            mods = [w for w in G.windows() if w.get("pid") == _window_pid(win)
                    and w.get("title") in ("Warning", "Information", "Error")]
            for w in mods:
                try:
                    import cv2
                    from foran_vision import capture_window
                    cv2.imwrite(str(run_dir / f"def_warning_{attempt}.png"),
                                capture_window(w["hwnd"]))
                except Exception:  # noqa: BLE001
                    pass
                print(f"dialog   : {w.get('title')} during definition OK")
                _invoke(w["hwnd"], names=("Ok", "OK", "Yes", "Close"))
            if _find_window("Lightship weight distribution definition",
                            _window_pid(win), timeout=0.2) is None:
                accepted = True
                break
            time.sleep(0.3)
        if accepted:
            break
        time.sleep(0.5)
    if not accepted:
        try:
            import cv2
            from foran_vision import capture_window
            cv2.imwrite(str(run_dir / "def_stuck.png"), capture_window(dlg_hwnd))
        except Exception:  # noqa: BLE001
            pass
        print("definition dialog did not accept the data (still open)", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(1.0)

    # The new node exists only in the tree until File > Save, so diff the tree.
    end = time.time() + 10
    new_names: list[str] = []
    while time.time() < end:
        new_names = [n for n in _tree_lsw_names(hwnd) if n not in before]
        if new_names:
            break
        time.sleep(0.5)
    names = _tree_lsw_names(hwnd) or _lsw_names(db) or []
    if new_names:
        detected = sorted(new_names,
                          key=lambda n: int(re.sub(r"\D", "", n) or 0))[-1]
    else:
        detected = sorted(names, key=lambda n: int(re.sub(r"\D", "", n) or 0))[-1]
    if a.name and a.name in names:
        new_name = a.name
    elif new_names:
        new_name = detected
        if a.name:
            print(f"warning  : requested name {a.name} was not created; "
                  f"using {new_name}", file=sys.stderr)
    elif a.name:
        new_name = a.name
    else:
        new_name = detected
    print(f"created  : {new_name}")

    # Re-open in edition mode so Total weight is computed from the rows.
    popup = _context_menu(win, new_name)
    if popup is None:
        _abort_app(G, win)
        return 1
    items = _popup_items(popup)
    print(f"menu     : {'|'.join(n for n, _ in items) if items else popup['rect']}")
    _popup_pick(popup, "Edit distribution", _LSW_MENU["edit_distribution"])
    dlg = _find_window("Lightship weight distribution edition",
                       _window_pid(win), timeout=15)
    if dlg is None:
        _snap(win["hwnd"], run_dir / "edition_missing.png")
        titles = [w.get("title", "") for w in G.windows()
                  if w.get("pid") == _window_pid(win)]
        print(f"edition dialog did not open; windows={titles}", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(0.8)
    _focus_window(dlg["hwnd"])
    clicked = _invoke(dlg["hwnd"], names=("Ok",))
    print(f"edition  : clicked {clicked!r}")
    end = time.time() + 10
    while time.time() < end:
        _dismiss_modal(win, seconds=0.2)
        if _find_window("Lightship weight distribution edition",
                        _window_pid(win), timeout=0.2) is None:
            break
        time.sleep(0.3)
    if _find_window("Lightship weight distribution edition",
                    _window_pid(win), timeout=0.5) is not None:
        _snap(dlg["hwnd"], run_dir / "edition_stuck.png")
        _snap(win["hwnd"], run_dir / "edition_stuck_main.png")
        print("edition dialog did not close", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(0.8)

    # Compute the distribution: complex dialog -> OK -> accept warning.
    popup = _context_menu(win, new_name)
    if popup is None:
        _abort_app(G, win)
        return 1
    _popup_pick(popup, "Edit complex distribution", _LSW_MENU["edit_complex"])
    dlg = _find_window("Lightship weight distribution", _window_pid(win), timeout=15)
    if dlg is None:
        print("complex distribution dialog did not open", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(0.8)
    _invoke(dlg["hwnd"], names=("OK", "Ok"))
    end = time.time() + 40
    while time.time() < end:
        _dismiss_modal(win, seconds=0.2)
        if _find_window("Lightship weight distribution", _window_pid(win),
                        timeout=0.2) is None:
            break
        time.sleep(0.4)
    if _find_window("Lightship weight distribution", _window_pid(win),
                    timeout=1.0) is not None:
        print("complex distribution dialog did not close", file=sys.stderr)
        _abort_app(G, win)
        return 1

    if not _file_save(win):
        print("File > Save failed", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(2.5)

    info = _lsw_info(db, new_name)
    print(f"lsW      : {new_name} root_weight={info['weight'] if info else '?'} "
          f"dist_rows={info['dist'] if info else '?'} "
          f"total_rows={info['total_rows'] if info else '?'}")
    ok = bool(info and info["weight"] > 0 and info["dist"] > 0
              and info["total_rows"] > 0
              and abs(info["weight"] - total_weight) < 0.01)
    if info and abs(info["weight"] - total_weight) >= 0.01:
        print(f"root weight {info['weight']} != tsv total {total_weight}",
              file=sys.stderr)
    if not ok:
        print("LSW distribution was not written", file=sys.stderr)
    if a.keep_open:
        print("keeping FBASIC open (--keep-open)")
        return 0 if ok else 1
    if not _exit_app(win):
        print("FBASIC did not exit", file=sys.stderr)
        return 1
    return 0 if ok else 1


def cmd_lsw(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    return _cmd_lsw_impl(a, G)


_LC_EDITOR_TABS = ("Loads in compartments", "Local loads", "Modular loads")


def _lc_editor_tabs(hwnd: int):
    d = G._app_window(hwnd, "uia")
    return [c for c in d.descendants(control_type="TabItem")
            if (c.window_text() or "").strip() in _LC_EDITOR_TABS]


def _lc_editor_open(hwnd: int) -> bool:
    return (bool(_lc_editor_tabs(hwnd))
            or _tree_item(hwnd, "LightShipWeight", top_min=400) is not None)


def _lc_tab(hwnd: int, name: str):
    for c in _lc_editor_tabs(hwnd):
        if (c.window_text() or "").strip() == name:
            return c
    return None


def _lc_row_cell(hwnd: int, label: str):
    """Return the value cell (right-hand TreeItem) of an editor row."""
    d = G._app_window(hwnd, "uia")
    items = [c for c in d.descendants(control_type="TreeItem")]
    labels = sorted((c for c in items
                     if (c.window_text() or "").strip() == label),
                    key=lambda c: c.rectangle().top)
    for lab in labels:
        top = lab.rectangle().top
        left = lab.rectangle().right
        cells = [c for c in items
                 if abs(c.rectangle().top - top) <= 3
                 and c.rectangle().left >= left - 4]
        if cells:
            return min(cells, key=lambda c: c.rectangle().left)
    return None


def _lc_row_value(hwnd: int, label: str) -> str | None:
    cell = _lc_row_cell(hwnd, label)
    return (cell.window_text() or "").strip() if cell is not None else None


def _lc_icon_buttons(hwnd: int):
    """Locate the custom-painted icon buttons of the LC editor.

    Returns (add_remove, dock): `add_remove` is [+, -] (the two buttons just
    left of the tab strip) and `dock` is the tree-dock group ordered left to
    right (accept, apply, cancel, info, ...). All of these are QToolButtons
    with no accessible name, so they are identified structurally.
    """
    tabs = _lc_editor_tabs(hwnd)
    if not tabs:
        return [], []
    strip_top = min(c.rectangle().top for c in tabs)
    tab_left = min(c.rectangle().left for c in tabs)
    d = G._app_window(hwnd, "uia")
    row = [c for c in d.descendants(control_type="Button")
           if not (c.window_text() or "").strip()
           and 0 <= strip_top - c.rectangle().bottom <= 25]
    # The add/remove pair is nearest to the tab strip's left edge.
    row.sort(key=lambda c: tab_left - c.rectangle().right)
    pair = sorted(row[:2], key=lambda c: c.rectangle().left)
    # The accept/apply/cancel/info group sits far left of the add/remove pair.
    limit = pair[0].rectangle().left - 100 if pair else 250
    dock = sorted((c for c in row if c.rectangle().right < limit),
                  key=lambda c: c.rectangle().left)
    return pair, dock


def _wait_editor_closed(hwnd: int, timeout: float = 5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if not _lc_editor_open(hwnd):
            return True
        time.sleep(0.2)
    return not _lc_editor_open(hwnd)


def _has_load_row(hwnd: int) -> bool:
    d = G._app_window(hwnd, "uia")
    return any((c.window_text() or "").strip().startswith("LOA-")
               for c in d.descendants(control_type="DataItem"))


def _set_lsw(win, lsw: str) -> bool:
    hwnd = win["hwnd"]
    target = _lc_row_cell(hwnd, "LightShipWeight")
    if target is None:
        print("LightShipWeight row not found", file=sys.stderr)
        return False
    target.click_input()
    time.sleep(0.2)
    target.click_input(double=True)
    end = time.time() + 3
    popup = None
    while time.time() < end:
        ps = [w for w in G.windows() if w.get("class") == "QPopup"
              and w.get("pid") == _window_pid(win)]
        if ps:
            popup = ps[0]
            break
        time.sleep(0.1)
    if popup is None:
        print("LightShipWeight dropdown did not open", file=sys.stderr)
        return False
    picked = False
    for txt, (l, t, r, b) in _popup_items(popup):
        if txt.strip() == lsw:
            import pyautogui
            pyautogui.click((l + r) // 2, (t + b) // 2)
            picked = True
            break
    if not picked:
        names = _lsw_names(Path(win["_db"]))
        if lsw not in names:
            print(f"{lsw} not in {names}", file=sys.stderr)
            _invoke(popup["hwnd"], names=("Close",))
            return False
        print(f"dropdown : {lsw!r} not exposed by UIA; using offsets",
              file=sys.stderr)
        _popup_click(popup, 12 + 24 * names.index(lsw))
    end = time.time() + 3
    now = None
    while time.time() < end:
        now = _lc_row_value(hwnd, "LightShipWeight")
        if now == lsw:
            return True
        time.sleep(0.2)
    print(f"LightShipWeight is {now!r}, expected {lsw!r}", file=sys.stderr)
    return False


def _fill_load_row(win, weight: float, xcg: float, zcg: float) -> bool:
    import pyautogui
    hwnd = win["hwnd"]
    d = G._app_window(hwnd, "uia")
    items = [c for c in d.descendants(control_type="DataItem")]
    name_cell = next((c for c in items
                      if (c.window_text() or "").strip().startswith("LOA-")), None)
    if name_cell is None:
        print("local load row not found", file=sys.stderr)
        return False
    row_top = name_cell.rectangle().top

    def cell(pred):
        for c in items:
            r = c.rectangle()
            if abs(r.top - row_top) < 6 and pred((c.window_text() or "").strip()):
                return c
        return None

    targets = [
        (cell(lambda t: bool(re.fullmatch(r"[\d.]+ +t", t))), f"{weight:g}"),
        (cell(lambda t: t.startswith("AP ") or t.startswith("x ")), f"{xcg:g}"),
        (cell(lambda t: t.startswith("z ")), f"{zcg:g}"),
    ]
    for c, val in targets:
        if c is None:
            print("a local-load cell was not found", file=sys.stderr)
            return False
        r = c.rectangle()
        pyautogui.doubleClick((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        import pyperclip
        pyperclip.copy(val)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.5)
    d = G._app_window(hwnd, "uia")
    items = [c for c in d.descendants(control_type="DataItem")]
    name_cell = next((c for c in items
                      if (c.window_text() or "").strip().startswith("LOA-")), None)
    if name_cell is None:
        return False
    row_top = name_cell.rectangle().top

    def number(pred):
        for c in items:
            if abs(c.rectangle().top - row_top) >= 6:
                continue
            t = (c.window_text() or "").strip()
            if pred(t):
                m = re.search(r"-?\d+(?:\.\d+)?", t)
                return float(m.group()) if m else None
        return None

    w = number(lambda t: bool(re.fullmatch(r"[\d.]+ +t", t)))
    x = number(lambda t: t.startswith("AP ") or t.startswith("x "))
    z = number(lambda t: t.startswith("z "))
    ok = (w is not None and abs(w - weight) <= max(0.5, abs(weight) * 1e-4)
          and x is not None and abs(x - xcg) <= 0.05
          and z is not None and abs(z - zcg) <= 0.05)
    if not ok:
        print(f"local load row reads weight={w!r} xcg={x!r} zcg={z!r}",
              file=sys.stderr)
    return ok


def _run_lc_calculate(win, run_dir: Path, timeout: float) -> bool:
    hwnd = win["hwnd"]
    if not _front_main(win):
        print("FBASIC is not foreground; aborting Calculate", file=sys.stderr)
        return False
    popup = _context_menu(win, "Loading Conditions")
    if popup is None:
        return False
    _popup_pick(popup, "Calculate", _LC_NODE_MENU["calculate"])
    calc = _find_window("Loading condition calculation", _window_pid(win), timeout=15)
    if calc is None:
        print("calculation dialog did not open", file=sys.stderr)
        return False
    end = time.time() + timeout
    shots = 0
    while time.time() < end:
        for w in [x for x in G.windows() if x.get("pid") == _window_pid(win)
                  and x.get("title") in ("Error", "Warning", "Information")]:
            if shots < 5:
                try:
                    import cv2
                    from foran_vision import capture_window
                    cv2.imwrite(str(run_dir / f"lc_error_{shots}.png"),
                                capture_window(w["hwnd"]))
                    shots += 1
                except Exception:  # noqa: BLE001
                    pass
            _invoke(w["hwnd"], names=("Ok", "OK", "Close"))
            print(f"dismissed : {w.get('title')}")
            time.sleep(0.3)
        calc = _find_window("Loading condition calculation", _window_pid(win),
                            timeout=0.2)
        if calc is None:
            return True
        if _invoke(calc["hwnd"], names=("Close",)) == "Close":
            print("calculate : finished")
            return True
        time.sleep(2.0)
    print("calculation timed out", file=sys.stderr)
    return False


def _cmd_lc_impl(a, G_mod) -> int:
    global G
    G = G_mod
    db, win, run_dir = _launch_calc(a, G, "lc")
    if db is None:
        return 1
    win["_db"] = db
    hwnd = win["hwnd"]
    _settle_warnings(G)
    _ensure_tree(G, hwnd)
    if not _front_main(win):
        print("FBASIC is not foreground; aborting before any click", file=sys.stderr)
        _abort_app(G, win)
        return 1
    if not _click_tab(hwnd, "Stability"):
        print("Stability tab not found", file=sys.stderr)
        _abort_app(G, win)
        return 1
    if _tree_item(hwnd, "Loading Conditions") is None:
        print("Loading Conditions node not found", file=sys.stderr)
        _abort_app(G, win)
        return 1

    popup = _context_menu(win, "Loading Conditions")
    if popup is None:
        _abort_app(G, win)
        return 1
    _popup_pick(popup, "New loading condition", _LC_NODE_MENU["new_lc"])
    end = time.time() + 15
    while time.time() < end and not _lc_editor_open(hwnd):
        time.sleep(0.3)
    if not _lc_editor_open(hwnd):
        print("loading condition editor did not open", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(0.8)

    if not _set_lsw(win, a.lsw):
        print(f"could not select LightShipWeight={a.lsw}", file=sys.stderr)
        _abort_app(G, win)
        return 1
    print(f"lightship: {a.lsw}")

    if a.load:
        parts = [p.strip() for p in a.load.split(",")]
        if len(parts) != 3:
            print("--load must be WEIGHT,XCG,ZCG", file=sys.stderr)
            _abort_app(G, win)
            return 2
        weight, xcg, zcg = (float(p) for p in parts)
        if not _front_main(win):
            _abort_app(G, win)
            return 1
        tab = _lc_tab(hwnd, "Local loads")
        if tab is None:
            print("Local loads tab not found", file=sys.stderr)
            _abort_app(G, win)
            return 1
        tab.click_input()
        time.sleep(0.8)
        pair, _dock = _lc_icon_buttons(hwnd)
        if not pair:
            print("local-load add button not found", file=sys.stderr)
            _abort_app(G, win)
            return 1
        pair[0].click_input()              # green +
        end = time.time() + 6
        while time.time() < end and not _has_load_row(hwnd):
            time.sleep(0.2)
        if not _fill_load_row(win, weight, xcg, zcg):
            print("could not fill the local load row", file=sys.stderr)
            _abort_app(G, win)
            return 1
        print(f"local load: {weight:g} t @ XCG {xcg:g} / ZCG {zcg:g}")

    # Accept/close the editor (first icon in the tree-dock group).
    if not _front_main(win):
        _abort_app(G, win)
        return 1
    _pair, dock = _lc_icon_buttons(hwnd)
    if not dock:
        print("loading condition editor buttons not found", file=sys.stderr)
        _abort_app(G, win)
        return 1
    dock[0].click_input()                  # single check
    if not _wait_editor_closed(hwnd, 4):
        _pair, dock = _lc_icon_buttons(hwnd)
        if len(dock) > 1:
            dock[1].click_input()          # double check (apply)
    if not _wait_editor_closed(hwnd, 6):
        print("loading condition editor did not close", file=sys.stderr)
        _abort_app(G, win)
        return 1

    if not _run_lc_calculate(win, run_dir, a.timeout):
        _abort_app(G, win)
        return 1

    if not _file_save(win):
        print("File > Save failed", file=sys.stderr)
        _abort_app(G, win)
        return 1
    time.sleep(2.0)
    if a.keep_open:
        print("keeping FBASIC open (--keep-open); LC results persist only on exit")
        info = _lc_info(db)
        print(f"lc       : {info}")
        return 0

    if not _exit_app(win):
        print("FBASIC did not exit", file=sys.stderr)
        return 1
    info = _lc_info(db)
    if not info:
        print("no loading condition was written", file=sys.stderr)
        return 1
    print(f"lc       : {info['name']} calculated={info['calculated']} "
          f"loads={info['loads']}")
    ok = info["calculated"] == 1
    if a.load and not info["loads"]:
        ok = False
    if not ok:
        print("loading condition was not persisted/calculated", file=sys.stderr)
    return 0 if ok else 1


def cmd_lc(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    return _cmd_lc_impl(a, G)


def cmd_wh(a) -> int:
    global G
    try:
        import foran_gui as G
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    running = [w for w in G.windows() if w.get("process", "").lower() == "fbasic.exe"
               or w.get("title", "").startswith("fbasic -")]
    if running:
        if not a.close_existing:
            print(f"FBASIC is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return 2
        _close(G)
        time.sleep(2)

    db = _prepare_db(a)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fbasic" / f"wh_{stamp}"
    import foran_launch as L
    rc = L.main(["fbasic", "--workdir", str(run_dir)])
    if rc:
        _close(G)
        return 1
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    win = _wait_main(G, 60)
    if win is None:
        print("FBASIC main window not found", file=sys.stderr)
        _close(G)
        return 1
    time.sleep(2)
    _settle_warnings(G)
    if not _open_edit_panel(G, win["hwnd"]):
        print("could not open Solid hull edition", file=sys.stderr)
        _close(G)
        return 1
    if a.space:
        if not _set_method_spaces(G, win["hwnd"]):
            _close(G)
            return 1
        if not _ensure_space(G, win["hwnd"], a.space):
            _close(G)
            return 1
    if a.build:
        if not a.space:
            print("--build needs --space", file=sys.stderr)
            _close(G)
            return 2
        before = _solid_info(db)
        print(f"before   : solids={before[0]}, hull_sections={before[1]}")
        if not _build_wh(G, win["hwnd"], db, a.timeout):
            _close(G)
            return 1
        after = _solid_info(db)
        print(f"after    : solids={after[0]}, hull_sections={after[1]}")
        if after[1] <= 0:
            print("no watertight hull sections were produced", file=sys.stderr)
            _close(G)
            return 1
    if not a.keep_open:
        _close(G)
        return 0
    print("keeping FBASIC open (--keep-open)")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("wh", help="open SOLID-01 > Edit in FBASIC")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--space", help="select this space under Method=Spaces (e.g. SPC-0003)")
    p.add_argument("--build", action="store_true",
                   help="Build WH, calculate default sections, Ok and File Save")
    p.add_argument("--timeout", type=float, default=300.0,
                   help="Build WH / sections timeout in seconds")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_wh)

    p = sub.add_parser("cross", help="stability cross curves: 5 displacements -> Calculate -> save")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--calc", help="KNS-CALC node name (default: first, or create one)")
    p.add_argument("--displacements", default="20000,30000,40000,50000,60000",
                   help="comma list, at least 5 (default 20000..60000)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=900.0, help="calculation timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_cross)

    p = sub.add_parser("capacity", help="capacity table: spaces + levels/spacing -> Calculate -> save")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--spaces", required=True, help="comma list of SPC names, e.g. SPC-0002,SPC-0003")
    p.add_argument("--levels", type=int, default=15, help="waterline levels (default 15)")
    p.add_argument("--spacing", type=float, default=1.0, help="spacing in m, 0<v<10 (default 1.0)")
    p.add_argument("--calc", help="CT-* node name (default: first, or create one)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=1800.0, help="calculation timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_capacity)

    p = sub.add_parser("freeboard", help="freeboard: Calculate -> Ok -> save")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--calc", help="FB-* node name (default: first, or create one)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=600.0, help="calculation timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_freeboard)

    p = sub.add_parser("tonnage", help="tonnage: included spaces -> Calculate -> save")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--spaces", required=True, help="comma list of SPC names, e.g. SPC-0002,SPC-0003")
    p.add_argument("--calc", help="TONN-* node name (default: first, or create one)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=900.0, help="calculation timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_tonnage)

    p = sub.add_parser("lsw", help="create + calculate a lightship weight distribution (TSV)")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--tsv", required=True,
                   help="TSV: Group/Name/Description/Ref/Weight/Xmin/Xmax/XCoG/YCoG/ZCoG")
    p.add_argument("--name", help="distribution name (default: auto LSW-xx)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=300.0, help="dialog timeout in seconds")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_lsw)

    p = sub.add_parser("lc", help="create + calculate a loading condition")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--lsw", required=True, help="light ship weight distribution (e.g. LSW-04)")
    p.add_argument("--load", help="one local load as WEIGHT,XCG,ZCG (e.g. 32792,95,8)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=1800.0, help="calculation timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_lc)

    p = sub.add_parser("hydro", help="recalculate an existing HYD-CALC and save the results")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--calc", help="calculation node name (default: first HYD-CALC-*)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=300.0, help="calculation timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_hydro)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
