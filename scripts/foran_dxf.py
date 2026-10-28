# -*- coding: utf-8 -*-
"""Post-process a FORAN lines DXF: standard sheet + border + title block.

FORAN's Lines Drawing writes bare geometry (no sheet frame).  This command
puts that geometry on a standard sheet (A0-A4), scales it to fit, centres it,
and draws a simple drawing frame and title block with the project fields.

Usage:
  python foran_dxf.py frame --in lines.dxf --out framed.dxf --sheet A1 \
      --project "SAMPLE SHIP" --title 型线图 \
      --drawing-no EXAMPLE-010-04 --scale-text 1:100 \
      --designer APPROVER --checker CHECKER --approver APPROVER
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

try:
    import ezdxf
    from ezdxf import bbox
    from ezdxf.addons import Importer
    from ezdxf.math import Matrix44
except Exception as exc:  # noqa: BLE001
    print(f"ezdxf missing ({exc}). Install it: pip install ezdxf", file=sys.stderr)
    raise SystemExit(3)

# Landscape sheet sizes in millimetres (width, height).
SHEETS = {
    "A0": (1189.0, 841.0),
    "A1": (841.0, 594.0),
    "A2": (594.0, 420.0),
    "A3": (420.0, 297.0),
    "A4": (297.0, 210.0),
}
TB_W, TB_H = 180.0, 56.0      # title block size (mm)
LEFT, OTHER = 25.0, 10.0      # binding margin / other margins


def _text_style(doc):
    name = "CN"
    try:
        doc.styles.get(name)
    except Exception:  # noqa: BLE001
        doc.styles.new(name, dxfattribs={"font": "simsun.ttc"})
    return name


def _line(msp, x1, y1, x2, y2, layer="FRAME"):
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})


def _text(msp, x, y, value, height=3.5, style="CN", layer="TEXT"):
    if value:
        msp.add_text(value, height=height,
                     dxfattribs={"style": style, "layer": layer}).set_placement(
                         (x, y), align=ezdxf.enums.TextEntityAlignment.LEFT)


def _title_block(doc, msp, x0: float, y0: float, a):
    style = _text_style(doc)
    # Outer rectangle and horizontal separators.
    _line(msp, x0, y0, x0 + TB_W, y0)
    _line(msp, x0 + TB_W, y0, x0 + TB_W, y0 + TB_H)
    _line(msp, x0 + TB_W, y0 + TB_H, x0, y0 + TB_H)
    _line(msp, x0, y0 + TB_H, x0, y0)
    rows = [0, 12, 24, 36, 48, TB_H]
    for y in rows[1:-1]:
        _line(msp, x0, y0 + y, x0 + TB_W, y0 + y)
    _line(msp, x0 + 90, y0, x0 + 90, y0 + TB_H)
    # Left column: project / title / drawing no / designer / checker / approver.
    _text(msp, x0 + 2, y0 + 49, "项目", 3.0, style)
    _text(msp, x0 + 14, y0 + 49, a.project, 3.5, style)
    _text(msp, x0 + 2, y0 + 37, "图名", 3.0, style)
    _text(msp, x0 + 14, y0 + 37, a.title, 5.0, style)
    _text(msp, x0 + 2, y0 + 25, "图号", 3.0, style)
    _text(msp, x0 + 14, y0 + 25, a.drawing_no, 3.5, style)
    _text(msp, x0 + 2, y0 + 13, "设计", 3.0, style)
    _text(msp, x0 + 14, y0 + 13, a.designer, 3.5, style)
    _text(msp, x0 + 2, y0 + 1, "日期", 3.0, style)
    _text(msp, x0 + 14, y0 + 1, a.date, 3.5, style)
    # Right column: scale / checker / approver / company.
    _text(msp, x0 + 92, y0 + 49, "比例", 3.0, style)
    _text(msp, x0 + 104, y0 + 49, a.scale_text, 3.5, style)
    _text(msp, x0 + 92, y0 + 37, "审核", 3.0, style)
    _text(msp, x0 + 104, y0 + 37, a.checker, 3.5, style)
    _text(msp, x0 + 92, y0 + 25, "批准", 3.0, style)
    _text(msp, x0 + 104, y0 + 25, a.approver, 3.5, style)
    _text(msp, x0 + 92, y0 + 13, "单位", 3.0, style)
    _text(msp, x0 + 104, y0 + 13, a.company, 3.5, style)
    _text(msp, x0 + 92, y0 + 1, "图幅", 3.0, style)
    _text(msp, x0 + 104, y0 + 1, f"{a.sheet}" + (" (竖)" if a.portrait else ""),
          3.5, style)


def detect_template_area(tpl, margin: float = 10.0):
    """Guess the free drawing area of a frame/title-block DXF.

    The title block is assumed to sit in the bottom-right corner: when most
    texts cluster there, the area above them is used.  Otherwise the whole
    template (minus margins) is returned.  An explicit --template-area always
    wins.
    """
    te = bbox.extents(tpl)
    if not te.has_data:
        return None
    bx0, by0 = te.extmin.x, te.extmin.y
    bx1, by1 = te.extmax.x, te.extmax.y
    w, h = bx1 - bx0, by1 - by0
    texts = [e for e in tpl if e.dxftype() in ("TEXT", "MTEXT")]
    if texts:
        tb = bbox.extents(texts)
        if tb.has_data:
            tx0, ty0 = tb.extmin.x, tb.extmin.y
            tx1, ty1 = tb.extmax.x, tb.extmax.y
            cx, cy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
            if cx > bx0 + 0.55 * w and cy < by0 + 0.4 * h:
                # Bottom-right title block: draw above it.
                return (bx0 + margin, min(ty1 + margin, by1 - margin),
                        bx1 - margin, by1 - margin)
            if cx > bx0 + 0.6 * w and (ty1 - ty0) > 0.25 * h:
                # Right-hand title block: draw to its left.
                return (bx0 + margin, by0 + margin,
                        min(tx0 - margin, bx1 - margin), by1 - margin)
    return (bx0 + margin, by0 + margin, bx1 - margin, by1 - margin)


_ACCORE_GLOBS = (
    "C:/Program Files/Autodesk/AutoCAD */accoreconsole.exe",
    "C:/Program Files (x86)/Autodesk/AutoCAD */accoreconsole.exe",
)


def _script_path(p: Path) -> str:
    """Return a path safe to embed in an AutoCAD .scr file."""
    s = p.as_posix()
    if "\n" in s or "\r" in s or '"' in s:
        raise SystemExit("path contains characters unsafe for an AutoCAD script")
    return s


def find_accoreconsole():
    for var in ("FORAN_ACCORECONSOLE", "ACCORECONSOLE"):
        p = os.environ.get(var)
        if p and Path(p).is_file():
            return Path(p)
    for pat in _ACCORE_GLOBS:
        hits = sorted(glob.glob(pat), reverse=True)
        if hits:
            return Path(hits[0])
    return None


def cmd_dwg2dxf(a) -> int:
    """Convert a DWG to DXF with AutoCAD Core Console (headless)."""
    src = Path(a.inp).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"DWG not found: {src}")
    out = Path(a.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    accore = find_accoreconsole()
    if accore is None:
        raise SystemExit(
            "accoreconsole.exe not found; set FORAN_ACCORECONSOLE to its path")
    work = Path.cwd() / "_foran_work" / "cad" / (
        "dwg2dxf_" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    work.mkdir(parents=True, exist_ok=True)
    local = work / src.name
    shutil.copy2(src, local)
    scr = work / "convert.scr"
    # FILEDIA 0 -> command-line prompts; QUIT/Y discards and exits cleanly.
    scr.write_text(
        "FILEDIA\n0\nDXFOUT\n" + _script_path(out) + "\n16\nQUIT\nY\n",
        encoding="utf-8")
    print(f"accore   : {accore}")
    print(f"input    : {src} ({src.stat().st_size} bytes)")
    started = time.time()
    try:
        proc = subprocess.run(
            [str(accore), "/i", str(local), "/s", str(scr)],
            capture_output=True, timeout=a.timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        print(f"dwg2dxf: timed out after {a.timeout:.0f}s", file=sys.stderr)
        return 1
    elapsed = time.time() - started
    if not out.exists() or out.stat().st_size == 0:
        print(f"dwg2dxf: no DXF written (exit {rc}, {elapsed:.1f}s)",
              file=sys.stderr)
        tail = (proc.stdout or b"")[-800:]
        if tail:
            print(tail.decode("utf-8", "replace"), file=sys.stderr)
        return 1
    tail = out.read_bytes()[-200:]
    ok = b"EOF" in tail
    print(f"wrote    : {out} ({out.stat().st_size} bytes, {elapsed:.1f}s)")
    print(f"check    : {'EOF ok' if ok else 'WARNING: no EOF marker'}")
    return 0 if ok else 1


def cmd_dxf2dwg(a) -> int:
    """Convert a DXF to DWG with AutoCAD Core Console (headless)."""
    src = Path(a.inp).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"DXF not found: {src}")
    out = Path(a.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    accore = find_accoreconsole()
    if accore is None:
        raise SystemExit(
            "accoreconsole.exe not found; set FORAN_ACCORECONSOLE to its path")
    work = Path.cwd() / "_foran_work" / "cad" / (
        "dxf2dwg_" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    work.mkdir(parents=True, exist_ok=True)
    local = work / src.name
    shutil.copy2(src, local)
    scr = work / "convert.scr"
    # FILEDIA 0 -> command-line prompts; SAVEAS asks version then file name;
    # QUIT/Y discards the unsaved state and exits cleanly.
    # AutoCAD's console reads the script with the system ANSI code page, so a
    # UTF-8 script mangles Chinese paths; write GBK on Chinese Windows.
    ver = str(a.version or "2018")
    if not re.fullmatch(r"\d{4}", ver):
        raise SystemExit(f"invalid DWG version: {ver!r} (expected four digits)")
    body = ("FILEDIA\n0\nSAVEAS\n" + ver + "\n"
            + _script_path(out) + "\nQUIT\nY\n")
    try:
        scr.write_text(body, encoding="gbk")
    except UnicodeEncodeError:
        scr.write_text(body, encoding="utf-8")
    print(f"accore   : {accore}")
    print(f"input    : {src} ({src.stat().st_size} bytes)")
    started = time.time()
    try:
        proc = subprocess.run(
            [str(accore), "/i", str(local), "/s", str(scr)],
            capture_output=True, timeout=a.timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        print(f"dxf2dwg: timed out after {a.timeout:.0f}s", file=sys.stderr)
        return 1
    elapsed = time.time() - started
    if not out.exists() or out.stat().st_size == 0:
        print(f"dxf2dwg: no DWG written (exit {rc}, {elapsed:.1f}s)",
              file=sys.stderr)
        for stream in (proc.stdout or b"", proc.stderr or b""):
            tail = stream[-800:]
            if tail:
                print(tail.decode("utf-8", "replace"), file=sys.stderr)
        return 1
    head = out.read_bytes()[:6]
    ok = head.startswith(b"AC")
    print(f"wrote    : {out} ({out.stat().st_size} bytes, {elapsed:.1f}s)")
    print(f"check    : {'DWG ' + head.decode('ascii', 'replace') if ok else 'WARNING: bad DWG header'}")
    return 0 if ok else 1


def cmd_frame(a) -> int:
    src = Path(a.inp).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"DXF not found: {src}")
    out = Path(a.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    units = float(a.units_per_mm)          # mm per DXF unit
    src_doc = ezdxf.readfile(src)
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4          # millimetres
    msp = doc.modelspace()
    imp = Importer(src_doc, doc)
    imp.import_modelspace()
    imp.finalize()
    imported = list(msp)                 # everything present before the frame
    if not imported:
        raise SystemExit("input DXF has no modelspace entities")

    ext = bbox.extents(imported)
    if not ext.has_data:
        raise SystemExit("cannot compute the modelspace extents")
    ex0, ey0 = ext.extmin.x, ext.extmin.y
    ew_u = max(1e-9, ext.extmax.x - ex0)
    eh_u = max(1e-9, ext.extmax.y - ey0)
    ew_mm, eh_mm = ew_u * units, eh_u * units

    if a.template:
        # Merge an existing frame/title-block DXF and fit the lines inside it.
        tpl_path = Path(a.template).expanduser().resolve()
        if not tpl_path.is_file():
            raise SystemExit(f"template DXF not found: {tpl_path}")
        before = {e.dxf.handle for e in msp}
        tpl_doc = ezdxf.readfile(tpl_path)
        imp2 = Importer(tpl_doc, doc)
        imp2.import_modelspace()
        imp2.finalize()
        tpl = [e for e in msp if e.dxf.handle not in before]
        if not tpl:
            raise SystemExit("template DXF has no modelspace entities")
        t_units = float(a.template_units_per_mm)
        if t_units != 1.0:
            for e in tpl:
                e.transform(Matrix44.scale(t_units, t_units, 1))
        te = bbox.extents(tpl)
        if not te.has_data:
            raise SystemExit("cannot compute the template extents")
        if a.template_area and a.template_area != "auto":
            ax0, ay0, ax1, ay1 = (float(v) for v in a.template_area.split(","))
        else:
            box = detect_template_area(tpl, float(a.template_margin))
            if box is None:
                raise SystemExit("cannot detect the template drawing area")
            ax0, ay0, ax1, ay1 = box
            print(f"area    : auto-detected ({ax0:.0f},{ay0:.0f})-"
                  f"({ax1:.0f},{ay1:.0f})")
        aw, ah = max(1e-9, ax1 - ax0), max(1e-9, ay1 - ay0)
        scale = min(aw / ew_mm, ah / eh_mm)
        s_units = units * scale
        tx = ax0 + (aw - ew_mm * scale) / 2 - ex0 * s_units
        ty = ay0 + (ah - eh_mm * scale) / 2 - ey0 * s_units
        mtx = Matrix44.chain(Matrix44.scale(s_units, s_units, 1),
                             Matrix44.translate(tx, ty, 0))
        for e in imported:
            e.transform(mtx)
        doc.saveas(out)
        print(f"framed  : {out} ({out.stat().st_size} bytes)  [template]")
        print(f"template: {tpl_path.name}  extents "
              f"{te.extmax.x - te.extmin.x:.0f}x{te.extmax.y - te.extmin.y:.0f} mm")
        print(f"lines   : fit scale x{scale:.4g} into "
              f"({ax0:.0f},{ay0:.0f})-({ax1:.0f},{ay1:.0f})")
        return 0

    if a.fit:
        w, h = SHEETS[a.sheet]
        if a.portrait:
            w, h = h, w
        area_x0, area_y0 = LEFT, OTHER
        area_x1, area_y1 = w - OTHER, h - OTHER - TB_H - 4
        aw, ah = area_x1 - area_x0, area_y1 - area_y0
        scale = min(aw / ew_mm, ah / eh_mm)
        if a.scale and a.scale_den:
            scale = a.scale / a.scale_den
        # Convert DXF units to mm and fit: x' = x*(units*scale) + tx (mm).
        s_units = units * scale
        tx = area_x0 + (aw - ew_mm * scale) / 2 - ex0 * s_units
        ty = area_y0 + (ah - eh_mm * scale) / 2 - ey0 * s_units
        m = Matrix44.chain(Matrix44.scale(s_units, s_units, 1),
                           Matrix44.translate(tx, ty, 0))
        for e in imported:
            e.transform(m)
        print(f"sheet   : {a.sheet}{' portrait' if a.portrait else ''} "
              f"{w:.0f}x{h:.0f} mm  fit scale x{scale:.4g}")
    else:
        # Convert DXF units to mm, keep the drawing's paper scale.
        tx = LEFT - ex0 * units
        ty = (OTHER + TB_H) - ey0 * units
        m = Matrix44.chain(Matrix44.scale(units, units, 1),
                           Matrix44.translate(tx, ty, 0))
        for e in imported:
            e.transform(m)
        w = max(LEFT + ew_mm + OTHER, LEFT + TB_W + OTHER)
        h = OTHER + TB_H + eh_mm + OTHER
        print(f"sheet   : auto {w:.0f}x{h:.0f} mm  (drawing kept at its own scale)")

    # Border + title block.
    _line(msp, 0, 0, w, 0)
    _line(msp, w, 0, w, h)
    _line(msp, w, h, 0, h)
    _line(msp, 0, h, 0, 0)
    _line(msp, LEFT, OTHER, w - OTHER, OTHER)
    _line(msp, w - OTHER, OTHER, w - OTHER, h - OTHER)
    _line(msp, w - OTHER, h - OTHER, LEFT, h - OTHER)
    _line(msp, LEFT, h - OTHER, LEFT, OTHER)
    _title_block(doc, msp, w - OTHER - TB_W, OTHER, a)

    doc.saveas(out)
    print(f"framed  : {out} ({out.stat().st_size} bytes)")
    print(f"title   : {a.title}  {a.drawing_no}  {a.scale_text}")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dwg2dxf",
                       help="convert a DWG to DXF with AutoCAD Core Console")
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=float, default=900.0)
    p.set_defaults(fn=cmd_dwg2dxf)

    p = sub.add_parser("to-dwg",
                       help="convert a DXF to DWG with AutoCAD Core Console")
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--version", default="2018",
                   help="DWG version for SAVEAS (default 2018)")
    p.add_argument("--timeout", type=float, default=300.0)
    p.set_defaults(fn=cmd_dxf2dwg)

    p = sub.add_parser("frame", help="put a DXF on a standard sheet with a title block")
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sheet", choices=tuple(SHEETS), default="A1")
    p.add_argument("--template", help="existing frame/title-block DXF to merge")
    p.add_argument("--template-units-per-mm", type=float, default=1.0,
                   help="mm per template DXF unit (default 1 = mm)")
    p.add_argument("--template-margin", type=float, default=10.0,
                   help="margin (mm) inside the template extents")
    p.add_argument("--template-area",
                   help="drawing area x0,y0,x1,y1 (mm) or 'auto' (default)")
    p.add_argument("--fit", action="store_true",
                   help="scale the drawing to fit the sheet (default: keep its scale)")
    p.add_argument("--units-per-mm", type=float, default=0.0001,
                   help="mm per DXF unit (FORAN Lines Drawing default 0.0001)")
    p.add_argument("--portrait", action="store_true")
    p.add_argument("--project", default="SAMPLE SHIP")
    p.add_argument("--title", default="型线图")
    p.add_argument("--drawing-no", default="EXAMPLE-010-04")
    p.add_argument("--scale-text", default="1:100",
                   help="scale printed in the title block")
    p.add_argument("--designer", default="")
    p.add_argument("--checker", default="")
    p.add_argument("--approver", default="")
    p.add_argument("--company", default="YOUR COMPANY")
    p.add_argument("--date", default=dt.date.today().strftime("%Y-%m-%d"))
    p.add_argument("--scale", type=float, default=None,
                   help="explicit drawing scale numerator (optional)")
    p.add_argument("--scale-den", type=float, default=None,
                   help="explicit drawing scale denominator (with --scale)")
    p.set_defaults(fn=cmd_frame)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
