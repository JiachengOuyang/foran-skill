# -*- coding: utf-8 -*-
"""Bring the terminal hosting this process back to the foreground.

Used before pausing for user input, so the console is not buried under
FORAN windows.  The target is found by process ancestry, never by window
title: Claude Code rewrites its title constantly.

The Bash tool may run commands through a transient shell whose parent chain
is already gone, so the lookup falls back to the parent window of any
``claude.exe`` process on the machine.

  python foran_focus.py
  python foran_focus.py --list
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

TH32CS_SNAPPROCESS = 0x00000002
SW_RESTORE = 9
ASFW_ANY = -1


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def process_table() -> dict[int, tuple[int, str]]:
    """Return {pid: (parent_pid, exe_name)} for all visible processes."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (0, -1):
        return {}
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    table: dict[int, tuple[int, str]] = {}
    try:
        ok = kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            table[int(entry.th32ProcessID)] = (
                int(entry.th32ParentProcessID),
                entry.szExeFile.decode("utf-8", "replace"),
            )
            ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return table


def ancestors(pid: int | None = None, table: dict[int, tuple[int, str]] | None = None) -> list[int]:
    """Walk up the parent chain (self first, root last)."""
    table = process_table() if table is None else table
    out: list[int] = []
    cur = os.getpid() if pid is None else pid
    seen: set[int] = set()
    while cur and cur not in seen:
        out.append(cur)
        seen.add(cur)
        cur = table.get(cur, (0, ""))[0]
    return out


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def visible_windows() -> list[dict]:
    rows: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            title = _window_title(hwnd)
            if title:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                rows.append({
                    "hwnd": int(hwnd),
                    "pid": _window_pid(hwnd),
                    "title": title,
                    "rect": (rect.left, rect.top, rect.right, rect.bottom),
                })
        return True

    user32.EnumWindows(cb, 0)
    return rows


def _pick(hits: list[dict], rank: dict[int, int]) -> dict | None:
    if not hits:
        return None
    hits.sort(key=lambda w: (
        rank.get(w["pid"], 999),
        -(w["rect"][2] - w["rect"][0]) * (w["rect"][3] - w["rect"][1]),
    ))
    return hits[0]


def find_terminal() -> dict | None:
    table = process_table()
    wins = visible_windows()

    # 1) Our own ancestor chain (normal case).
    chain = ancestors(None, table)
    target = _pick([w for w in wins if w["pid"] in chain], {p: i for i, p in enumerate(chain)})
    if target:
        return target

    # 2) The window of whichever process hosts claude.exe (transient shells).
    for pid, (_parent, name) in table.items():
        if name.lower() != "claude.exe":
            continue
        chain = ancestors(pid, table)
        target = _pick([w for w in wins if w["pid"] in chain], {p: i for i, p in enumerate(chain)})
        if target:
            return target
    return None


def focus(hwnd: int) -> bool:
    cur_tid = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    attached = False
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
        if fg_tid and fg_tid != cur_tid:
            attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
    return int(user32.GetForegroundWindow()) == int(hwnd)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    table = process_table()
    chain = ancestors(None, table)
    if "--list" in argv:
        print("ancestors:", " <- ".join(str(p) for p in chain))
        for pid, (parent, name) in sorted(table.items()):
            if name.lower() == "claude.exe":
                print(f"claude  : pid={pid} parent={parent} chain={' <- '.join(str(p) for p in ancestors(pid, table))}")
        for w in visible_windows():
            mark = " *" if w["pid"] in chain else ""
            print(f"  0x{w['hwnd']:x}  pid={w['pid']:<6} {w['title']}{mark}")
        return 0

    target = find_terminal()
    if not target:
        print("focus   : no terminal window found", file=sys.stderr)
        return 1
    ok = focus(target["hwnd"])
    print(f"focus   : hwnd=0x{target['hwnd']:x} pid={target['pid']} ok={ok}  {target['title']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
