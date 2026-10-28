# -*- coding: utf-8 -*-
"""See and drive FORAN windows (pywinauto + pyautogui).

Run this with the skill venv, not the system Python:
  .venv\\Scripts\\python.exe foran_gui.py ...

Safety: click/type/keys refuse to act unless --yes is passed. Always take a
screenshot before and after a GUI action, and confirm destructive dialogs with
the user first.

Examples:
  foran_gui.py windows
  foran_gui.py screenshot --window "FORAN Document Manager"
  foran_gui.py controls --window "Database settings" --backend uia
  foran_gui.py click --window "Database settings" --name "Open DB file" --yes
  foran_gui.py type --window "Database settings" --text "D:\\...\\sample.db" --yes --enter
  foran_gui.py keys --window "FORAN Document Manager" --keys "ctrl+o" --yes
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import re
import sys
import time
from pathlib import Path

try:
    import pyautogui
    import win32api
    import win32con
    import win32gui
    import win32process
    from pywinauto import Application, Desktop
except Exception as exc:  # noqa: BLE001
    print(f"GUI dependencies missing ({exc}).", file=sys.stderr)
    print("Run with the skill venv, e.g. .venv\\Scripts\\python.exe", file=sys.stderr)
    raise SystemExit(3)

try:
    from PIL import ImageGrab
except Exception:  # noqa: BLE001
    ImageGrab = None


def _process_name(pid: int) -> str:
    try:
        h = win32process.GetModuleFileNameEx(win32api.OpenProcess(0x1000, False, pid), 0)
        return Path(h).name
    except Exception:  # noqa: BLE001
        return ""


def windows(filter_text: str | None = None) -> list[dict]:
    out = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        item = {
            "hwnd": hwnd,
            "title": title,
            "class": win32gui.GetClassName(hwnd),
            "pid": pid,
            "process": _process_name(pid),
            "minimized": bool(win32gui.IsIconic(hwnd)),
            "rect": list(win32gui.GetWindowRect(hwnd)),
        }
        if filter_text:
            hay = " ".join(str(item[k]) for k in ("title", "class", "process")).lower()
            if filter_text.lower() not in hay:
                return
        out.append(item)

    win32gui.EnumWindows(cb, None)
    return out


def _match_one(title: str | None, hwnd: int | None, all_windows: bool = False):
    wins = windows(None)
    if hwnd:
        hits = [w for w in wins if w["hwnd"] == hwnd]
    elif title:
        try:
            rx = re.compile(title, re.I)
        except re.error:
            rx = re.compile(re.escape(title), re.I)
        hits = [w for w in wins if rx.search(w["title"]) or rx.search(w["process"])]
    else:
        raise SystemExit("need --window or --hwnd")
    if not hits:
        raise SystemExit("no matching window. Current windows:\n" + "\n".join(
            f"  0x{w['hwnd']:x}  {w['title']}  [{w['process']}]" for w in wins))
    if len(hits) > 1 and not all_windows:
        raise SystemExit("multiple windows matched; use --hwnd or a narrower --window:\n" + "\n".join(
            f"  0x{w['hwnd']:x}  {w['title']}  [{w['process']}]" for w in hits))
    return hits if all_windows else hits[0]


def _focus(hwnd: int):
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)


def wait_until(pred, timeout: float = 10.0, interval: float = 0.15) -> bool:
    """Poll `pred` until it returns true (or times out); returns the result.

    Used instead of fixed `sleep(2)` before clicks: the control is clicked as
    soon as it exists/enables, which is usually well under a second.
    """
    end = time.time() + timeout
    while time.time() < end:
        try:
            if pred():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(interval)
    try:
        return bool(pred())
    except Exception:  # noqa: BLE001
        return False


def _app_window(hwnd: int, backend: str):
    app = Application(backend=backend).connect(handle=hwnd)
    return app.window(handle=hwnd)


def _walk(ctrl, depth=0, max_depth=8, out=None):
    out = out if out is not None else []
    if depth > max_depth:
        return out
    try:
        info = ctrl.element_info
        rect = getattr(info, "rectangle", None)
        out.append({
            "depth": depth,
            "control_type": getattr(info, "control_type", None),
            "class_name": getattr(info, "class_name", None),
            "name": getattr(info, "name", None),
            "automation_id": getattr(info, "automation_id", None),
            "rect": [rect.left, rect.top, rect.right, rect.bottom] if rect else None,
            "enabled": getattr(info, "enabled", None),
        })
    except Exception:  # noqa: BLE001
        pass
    try:
        kids = ctrl.children()
    except Exception:  # noqa: BLE001
        kids = []
    for k in kids:
        _walk(k, depth + 1, max_depth, out)
    return out


def _find(ctrl, args, depth=0, out=None):
    out = out if out is not None else []
    if depth > args.depth:
        return out
    ok = True
    try:
        info = ctrl.element_info
        name = (getattr(info, "name", "") or "")
        auto = (getattr(info, "automation_id", "") or "")
        cls = (getattr(info, "class_name", "") or "")
        ctype = (getattr(info, "control_type", "") or "")
        if args.name:
            ok = ok and bool(re.search(args.name, name, re.I))
        if args.auto_id:
            ok = ok and auto == args.auto_id
        if args.class_name:
            ok = ok and bool(re.search(args.class_name, cls, re.I))
        if args.control_type:
            ok = ok and args.control_type.lower() in ctype.lower()
        if ok:
            out.append(ctrl)
    except Exception:  # noqa: BLE001
        pass
    try:
        for k in ctrl.children():
            _find(k, args, depth + 1, out)
    except Exception:  # noqa: BLE001
        pass
    return out


def _require_yes(a, what: str) -> bool:
    if a.dry_run or a.yes:
        return True
    print(f"REFUSED: {what} needs --yes (or --dry-run to only show the plan).", file=sys.stderr)
    return False


def _wait_window(title: str, timeout: float = 30.0, class_name: str | None = None):
    end = time.time() + timeout
    while time.time() < end:
        for w in windows():
            if w["title"] != title:
                continue
            if class_name and w["class"] != class_name:
                continue
            return w
        time.sleep(0.4)
    return None


def _paste(text: str) -> None:
    """Paste via clipboard: pyautogui.write mangles backslashes and non-ASCII."""
    import pyperclip
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.hotkey("ctrl", "v")


def fill_database_dialog(project: str, fnam: str | None = None, timeout: float = 45.0,
                         dry_run: bool = False, shot_dir: str | None = None) -> dict:
    """Fill FGA/FBASIC's `Database settings` dialog and press Ok.

    Tested on FGA V80R3.0.  The SQLite path field must be set through the
    dialog's `...` browse button: typing the path directly and tabbing out
    makes the widget clear itself.  The browse dialog is the standard Win32
    file dialog, so we type the path in its `File name` edit.

    Returns a dict with the chosen fnam/path and whether Ok was pressed.
    """
    from pathlib import Path as _Path
    proj = _Path(project).expanduser().resolve()
    if not proj.is_file():
        raise SystemExit(f"database not found: {proj}")
    # FNAM is the 4-character project code.  Default to the DB stem when it is
    # already 4 chars, otherwise the first 4 alphanumeric characters.
    if not fnam:
        alnum = "".join(c for c in proj.stem if c.isalnum())
        fnam = proj.stem if len(proj.stem) == 4 and proj.stem.isalnum() else alnum[:4]

    win = _wait_window("Database settings", timeout)
    if win is None:
        raise SystemExit("`Database settings` window not found (is the module running?)")
    hwnd = win["hwnd"]
    _focus(hwnd)
    dlg = _app_window(hwnd, "uia")
    edits = dlg.descendants(control_type="Edit")
    if len(edits) < 2:
        raise SystemExit(f"expected 2 edits in Database settings, found {len(edits)}")
    plan = {"fnam": fnam, "db": str(proj), "hwnd": hwnd}
    if dry_run:
        return {**plan, "ok": False, "dry_run": True}

    # FNAM first.
    edits[0].click_input()
    _paste(fnam)
    time.sleep(0.3)

    # `...` opens the Win32 `Open DB file` dialog; choose the .db there.
    browse = [b for b in dlg.descendants(control_type="Button")
              if (b.window_text() or "").strip() in ("...", "…")]
    if not browse:
        raise SystemExit("browse button (`...`) not found in Database settings")
    browse[-1].click_input()
    open_dlg = _wait_window("Open DB file", 20.0)
    if open_dlg is None:
        raise SystemExit("`Open DB file` dialog did not appear")
    _focus(open_dlg["hwnd"])
    app = Application(backend="win32").connect(handle=open_dlg["hwnd"])
    fd = app.window(handle=open_dlg["hwnd"])
    edit = fd.child_window(class_name="Edit", found_index=0)
    edit.click_input()
    edit.set_edit_text(str(proj))
    time.sleep(0.3)
    fd.child_window(title_re="^(打开|Open)", class_name="Button").click_input()

    # Back in Database settings: poll until Ok enables (the old code always
    # waited 2 s here, even when the dialog was ready immediately).
    win = _wait_window("Database settings", 10.0) or win
    _focus(win["hwnd"])
    dlg = _app_window(win["hwnd"], "uia")
    ok = dlg.child_window(title="Ok", control_type="Button")
    t0 = time.time()
    wait_until(lambda: ok.is_enabled(), 10.0, 0.2)
    plan["ok_enabled"] = ok.is_enabled()
    plan["ok_ready_s"] = round(time.time() - t0, 2)
    print(f"database : Ok enabled after {plan['ok_ready_s']}s")
    if shot_dir:
        out = _Path(shot_dir) / "db_dialog_before_ok.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import ImageGrab
            left, top, right, bottom = win32gui.GetWindowRect(win["hwnd"])
            ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(out)
            plan["screenshot"] = str(out)
        except Exception:  # noqa: BLE001
            pass
    if not ok.is_enabled():
        raise SystemExit("Ok is disabled: the database path was not accepted")
    ok.click_input()
    plan["ok"] = True
    return plan


# ---------------------------------------------------------------- commands
def cmd_windows(a) -> int:
    wins = windows(a.filter)
    if a.json:
        print(json.dumps(wins, ensure_ascii=False, indent=2))
        return 0
    for w in wins:
        flag = " [min]" if w["minimized"] else ""
        print(f"0x{w['hwnd']:08x}  {w['title']}{flag}\n    class={w['class']}  pid={w['pid']}  {w['process']}")
    if not wins:
        print("no visible windows matched")
    return 0


def cmd_screenshot(a) -> int:
    if a.window or a.hwnd:
        w = _match_one(a.window, a.hwnd)
        _focus(w["hwnd"])
        left, top, right, bottom = win32gui.GetWindowRect(w["hwnd"])
        bbox = (left, top, right, bottom)
        tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", w["title"])[:40]
    else:
        bbox = None
        tag = "screen"
    if ImageGrab is None:
        raise SystemExit("Pillow ImageGrab unavailable")
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
    out = Path(a.out) if a.out else (Path.cwd() / "_foran_work" / "screenshots" /
                                     f"foran_{tag}_{dt.datetime.now():%Y%m%d-%H%M%S}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"saved {out}  size={img.size}")
    return 0


def cmd_controls(a) -> int:
    w = _match_one(a.window, a.hwnd)
    dlg = _app_window(w["hwnd"], a.backend)
    if a.dump:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dlg.print_control_identifiers(depth=a.depth)
        text = buf.getvalue()
        Path(a.dump).write_text(text, encoding="utf-8")
        print(f"wrote {a.dump}")
    tree = _walk(dlg, 0, a.depth)
    if a.json:
        print(json.dumps(tree, ensure_ascii=False, indent=2))
    else:
        for n in tree:
            if n["name"] or n["automation_id"]:
                print(f"{'  '*n['depth']}{n['control_type']}  name={n['name']!r}  "
                      f"auto_id={n['automation_id']!r}  class={n['class_name']}")
    return 0


def cmd_click(a) -> int:
    w = _match_one(a.window, a.hwnd)
    _focus(w["hwnd"])
    if a.pos:
        x, y = (int(v) for v in a.pos.split(","))
        plan = f"click screen ({x},{y})"
        if not _require_yes(a, plan):
            return 2
        print(plan)
        if not a.dry_run:
            pyautogui.click(x, y)
        return 0

    dlg = _app_window(w["hwnd"], a.backend)
    hits = _find(dlg, a)
    if not hits:
        raise SystemExit("no control matched. Try `controls` and use --name/--auto-id/--control-type.")
    if len(hits) > 1 and a.index is None:
        print("multiple controls matched; pass --index:", file=sys.stderr)
        for i, c in enumerate(hits):
            print(f"  [{i}] {c.element_info.control_type} name={c.element_info.name!r}", file=sys.stderr)
        return 2
    ctrl = hits[a.index or 0]
    info = ctrl.element_info
    plan = f"click [{info.control_type}] name={info.name!r} auto_id={info.automation_id!r}"
    if not _require_yes(a, plan):
        return 2
    print(plan)
    if not a.dry_run:
        ctrl.click_input()
    return 0


def cmd_type(a) -> int:
    w = _match_one(a.window, a.hwnd)
    _focus(w["hwnd"])
    plan = f"type {a.text!r}" + (" + Enter" if a.enter else "")
    if not _require_yes(a, plan):
        return 2
    print(plan)
    if a.dry_run:
        return 0
    if a.text:
        # Always paste: pyautogui.write() mangles backslashes and cannot type
        # non-ASCII (Chinese paths/names). The clipboard path handles both.
        import pyperclip
        pyperclip.copy(a.text)
        pyautogui.hotkey("ctrl", "v")
    if a.enter:
        pyautogui.press("enter")
    return 0


def cmd_keys(a) -> int:
    w = _match_one(a.window, a.hwnd)
    _focus(w["hwnd"])
    plan = f"keys {a.keys!r}"
    if not _require_yes(a, plan):
        return 2
    print(plan)
    if a.dry_run:
        return 0
    parts = [p.strip() for p in a.keys.split("+") if p.strip()]
    pyautogui.hotkey(*parts)
    return 0


def cmd_fill_db(a) -> int:
    plan = f"fill `Database settings` with {a.project!r}"
    if not _require_yes(a, plan):
        return 2
    print(plan)
    info = fill_database_dialog(a.project, a.fnam, a.timeout, a.dry_run, a.shot_dir)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info.get("ok") or info.get("dry_run") else 1


def cmd_focus(a) -> int:
    w = _match_one(a.window, a.hwnd)
    _focus(w["hwnd"])
    print(f"focused 0x{w['hwnd']:x} {w['title']}")
    return 0


def cmd_wait(a) -> int:
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        try:
            w = _match_one(a.window, a.hwnd)
            print(f"found 0x{w['hwnd']:x} {w['title']}")
            return 0
        except SystemExit:
            time.sleep(0.5)
    print(f"timeout after {a.timeout}s", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def target(p):
        p.add_argument("--window", help="title/process regex")
        p.add_argument("--hwnd", type=lambda s: int(s, 0), help="window handle (0x...)")

    p = sub.add_parser("windows"); p.add_argument("--filter"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_windows)
    p = sub.add_parser("screenshot"); target(p); p.add_argument("--out"); p.set_defaults(fn=cmd_screenshot)
    p = sub.add_parser("controls"); target(p); p.add_argument("--backend", choices=("uia", "win32"), default="uia")
    p.add_argument("--depth", type=int, default=5); p.add_argument("--json", action="store_true")
    p.add_argument("--dump", help="also write print_control_identifiers output here"); p.set_defaults(fn=cmd_controls)
    p = sub.add_parser("click"); target(p); p.add_argument("--backend", choices=("uia", "win32"), default="uia")
    p.add_argument("--name", help="regex on control name/text"); p.add_argument("--auto-id")
    p.add_argument("--class-name"); p.add_argument("--control-type"); p.add_argument("--depth", type=int, default=8)
    p.add_argument("--index", type=int); p.add_argument("--pos", help="screen x,y (bypass control search)")
    p.add_argument("--yes", action="store_true"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_click)
    p = sub.add_parser("type"); target(p); p.add_argument("--text", default=""); p.add_argument("--enter", action="store_true")
    p.add_argument("--interval", type=float, default=0.02); p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_type)
    p = sub.add_parser("keys"); target(p); p.add_argument("--keys", required=True); p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_keys)
    p = sub.add_parser("fill-db"); p.add_argument("--project", required=True)
    p.add_argument("--fnam"); p.add_argument("--timeout", type=float, default=45.0)
    p.add_argument("--shot-dir"); p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_fill_db)
    p = sub.add_parser("focus"); target(p); p.set_defaults(fn=cmd_focus)
    p = sub.add_parser("wait"); target(p); p.add_argument("--timeout", type=float, default=30); p.set_defaults(fn=cmd_wait)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
