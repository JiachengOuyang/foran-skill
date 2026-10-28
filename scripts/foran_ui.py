# -*- coding: utf-8 -*-
"""Small UIA helpers shared by the FBASIC / FGA / FSURF drivers.

These used to be copied into each module.  They are deliberately free of
module state: the caller passes the `foran_gui` module (usually as `G`).

All coordinates are physical pixels (pyautogui sets DPI awareness on import).
"""
from __future__ import annotations

import os
import sys
import time


def menu_key(txt: str) -> str:
    """Normalize a menu label (drop & mnemonics and \\t shortcut text)."""
    return txt.replace("&", "").split("\t")[0].strip().lower()


def _menu_item(G, hwnd: int, key: str):
    try:
        d = G._app_window(hwnd, "uia")
        return next((c for c in d.descendants(control_type="MenuItem")
                     if menu_key(c.window_text() or "") == key), None)
    except Exception:  # noqa: BLE001
        return None


def menu_click(G, hwnd: int, name: str, fallback: tuple[int, int],
               pause: float = 0.8, wait: float = 2.0,
               popup_first: bool = False) -> bool:
    """Click a menu entry by UIA name, searching the main window and popups.

    Submenu entries live in a QPopup window, which can appear slightly after
    the parent item was clicked.  Focusing the main window while a popup is
    open dismisses the menu, so popup items are clicked without refocusing.
    """
    key = menu_key(name)
    item = None
    in_popup = False
    end = time.time() + wait
    while time.time() < end and item is None:
        popups = [w["hwnd"] for w in G.windows() if w.get("class") == "QPopup"]
        windows = popups + [hwnd] if popup_first else [hwnd] + popups
        for wh in windows:
            item = _menu_item(G, wh, key)
            if item is not None:
                in_popup = wh != hwnd
                break
        if item is None:
            time.sleep(0.15)
    if item is not None:
        if os.environ.get("FORAN_DEBUG_MENU"):
            print(f"menu dbg : {name!r} via {'popup' if in_popup else 'main'}",
                  file=sys.stderr)
        if not in_popup:
            try:
                G._focus(hwnd)
            except Exception:  # noqa: BLE001
                pass
        item.click_input()
        time.sleep(pause)
        return True
    print(f"menu     : {name!r} not exposed by UIA; using coordinates",
          file=sys.stderr)
    import pyautogui
    pyautogui.click(fallback[0], fallback[1])
    time.sleep(pause)
    return False


def popup_items(G, popup) -> list[tuple[str, tuple[int, int, int, int]]]:
    """MenuItem/ListItem texts + rectangles exposed by a QPopup (deduped)."""
    try:
        d = G._app_window(popup["hwnd"], "uia")
        out = []
        seen = set()
        for c in d.descendants():
            ct = c.element_info.control_type
            if ct not in ("MenuItem", "ListItem"):
                continue
            txt = (c.window_text() or "").strip()
            if not txt:
                continue
            r = c.rectangle()
            rect = (r.left, r.top, r.right, r.bottom)
            if (txt, rect) in seen:
                continue
            seen.add((txt, rect))
            out.append((txt, rect))
        return out
    except Exception:  # noqa: BLE001
        return []


def click_popup(popup, rel_y: int, x_off: int = 170) -> None:
    """Click `rel_y` pixels below the popup's top edge."""
    import pyautogui
    l, t, _r, _b = popup["rect"]
    pyautogui.click(l + x_off, t + rel_y)


def pick_popup_item(G, popup, name: str, rel_y: int,
                    x_off: int = 170) -> bool:
    """Click an entry of an open popup by name; fall back to an offset."""
    import pyautogui
    items = popup_items(G, popup)
    key = menu_key(name)
    for txt, (l, t, r, b) in items:
        if menu_key(txt) == key:
            pyautogui.click((l + r) // 2, (t + b) // 2)
            return True
    if items:
        print(f"menu     : {name!r} not in {[n for n, _ in items]}; "
              f"falling back to offset {rel_y}", file=sys.stderr)
    click_popup(popup, rel_y, x_off)
    return False


def wait_tree_item(G, hwnd: int, pred, timeout: float = 3.0):
    """Poll the window's TreeItems until `pred(text)` matches."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            d = G._app_window(hwnd, "uia")
            for c in d.descendants(control_type="TreeItem"):
                try:
                    t = (c.window_text() or "").strip()
                    if t and pred(t):
                        return c
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.15)
    return None


def close_app(G, pid: int, clicker, *, exit_confirm: str = "Yes",
              save_prompt: str = "No", timeout: float = 20.0) -> bool:
    """Dismiss dialogs and wait until every window of `pid` is gone.

    `clicker(hwnd, text)` must click a button by title and return bool
    (each module has its own helper).  Exit confirmations are answered with
    `exit_confirm`; an "Information modified" prompt is answered with
    `save_prompt` (default No, so a caller can discard a failed run).
    """
    end = time.time() + timeout
    while time.time() < end:
        alive = [w for w in G.windows() if int(w.get("pid") or 0) == int(pid)]
        if not alive:
            return True
        for w in alive:
            title = w.get("title", "")
            if title.startswith("Please confirm"):
                clicker(w["hwnd"], exit_confirm)
            elif title == "Information modified":
                clicker(w["hwnd"], save_prompt)
            elif title in ("Error", "Warning", "Information", "Alert"):
                for name in ("Close", "Ok", "OK"):
                    if clicker(w["hwnd"], name):
                        break
        time.sleep(0.4)
    return not [w for w in G.windows() if int(w.get("pid") or 0) == int(pid)]


def labeled_edit(G, hwnd: int, label: str):
    """Return the Edit control to the right of a `Text` label on the same row."""
    d = G._app_window(hwnd, "uia")
    edits = [c for c in d.descendants(control_type="Edit")]
    labels = sorted((c for c in d.descendants(control_type="Text")
                     if (c.window_text() or "").strip() == label),
                    key=lambda c: c.rectangle().top)
    for lab in labels:
        top = lab.rectangle().top
        left = lab.rectangle().right
        cands = [e for e in edits
                 if abs(e.rectangle().top - top) <= 8
                 and e.rectangle().left >= left - 2]
        if cands:
            return min(cands, key=lambda e: e.rectangle().left)
    return None
