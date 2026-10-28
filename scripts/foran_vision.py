# -*- coding: utf-8 -*-
"""Template matching for FORAN's custom-painted Qt widgets.

The left module tabs and some bottom icons are painted by FORAN and are not
exposed through UI Automation.  Crop a small template once and locate it in a
window screenshot with OpenCV; the returned centre is in screen coordinates.

  python foran_vision.py find --template calc_tab.png --source shot.png
  python foran_vision.py find --template calc_tab.png --hwnd 0x1234 --json
  python foran_vision.py crop --source shot.png --rect 0,250,32,95 --out t.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def _imread(path: str | Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    im = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if im is None:
        raise SystemExit(f"cannot read image: {path}")
    return im


def capture_window(hwnd: int) -> np.ndarray:
    """Capture a top-level window with PrintWindow (works when occluded)."""
    import ctypes
    import win32gui
    import win32ui

    wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
    w, h = wr - wl, wb - wt
    if w <= 0 or h <= 0:
        raise SystemExit("window has no area")
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
        im = np.frombuffer(bits, dtype=np.uint8).reshape(info["bmHeight"], info["bmWidth"], 4)
        return cv2.cvtColor(im, cv2.COLOR_BGRA2BGR)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mem.DeleteDC()
        src.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)


def find(template: Path, source: np.ndarray, threshold: float = 0.8,
         scales: tuple[float, ...] = (1.0,), region: tuple[int, int, int, int] | None = None):
    """Return the best match (score, x, y, w, h, scale) or None."""
    ox, oy = 0, 0
    img = source
    if region:
        ox, oy, rw, rh = region
        img = source[oy:oy + rh, ox:ox + rw]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tpl0 = cv2.cvtColor(_imread(template), cv2.COLOR_BGR2GRAY)
    best = None
    for scale in scales:
        tpl = tpl0 if scale == 1.0 else cv2.resize(tpl0, None, fx=scale, fy=scale)
        if tpl.shape[0] > gray.shape[0] or tpl.shape[1] > gray.shape[1]:
            continue
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _minv, maxv, _minl, maxl = cv2.minMaxLoc(res)
        if best is None or maxv > best[0]:
            best = (float(maxv), int(maxl[0]) + ox, int(maxl[1]) + oy,
                    int(tpl.shape[1]), int(tpl.shape[0]), float(scale))
    if best is None or best[0] < threshold:
        return None
    return best


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("find", help="find a template in a screenshot/window")
    p.add_argument("--template", required=True)
    p.add_argument("--source", help="screenshot PNG")
    p.add_argument("--hwnd", help="capture this window instead of --source")
    p.add_argument("--threshold", type=float, default=0.8)
    p.add_argument("--scales", default="1.0", help="comma list, e.g. 1.0,1.25,1.5")
    p.add_argument("--region", help="x,y,w,h in the source image")
    p.add_argument("--out", help="annotated PNG")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_find)

    p = sub.add_parser("crop", help="crop a template from a screenshot")
    p.add_argument("--source", required=True)
    p.add_argument("--rect", required=True, help="x,y,w,h")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_crop)

    a = ap.parse_args(argv)
    return a.fn(a)


def _rect(text: str) -> tuple[int, int, int, int]:
    parts = [int(x) for x in text.split(",")]
    if len(parts) != 4:
        raise SystemExit("--rect needs x,y,w,h")
    return tuple(parts)  # type: ignore[return-value]


def cmd_find(a) -> int:
    if a.hwnd:
        src = capture_window(int(a.hwnd, 0))
    elif a.source:
        src = _imread(a.source)
    else:
        raise SystemExit("need --source or --hwnd")
    region = _rect(a.region) if a.region else None
    scales = tuple(float(x) for x in a.scales.split(",") if x.strip())
    hit = find(Path(a.template), src, a.threshold, scales, region)
    if hit is None:
        print("no match", file=sys.stderr)
        return 1
    score, x, y, w, h, scale = hit
    cx, cy = x + w // 2, y + h // 2
    result = {"score": round(score, 4), "x": x, "y": y, "w": w, "h": h,
              "cx": cx, "cy": cy, "scale": scale}
    if a.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"match    : score={score:.4f} centre=({cx},{cy}) "
              f"rect=({x},{y},{w},{h}) scale={scale}")
    if a.out:
        annotated = src.copy()
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(annotated, f"{score:.3f}", (x, max(12, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        cv2.imencode(".png", annotated)[1].tofile(str(a.out))
        print(f"annotated: {a.out}")
    return 0


def cmd_crop(a) -> int:
    im = _imread(a.source)
    x, y, w, h = _rect(a.rect)
    cv2.imencode(".png", im[y:y + h, x:x + w])[1].tofile(str(a.out))
    print(f"crop     : {a.out} ({w}x{h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
