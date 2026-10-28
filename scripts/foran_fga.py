# -*- coding: utf-8 -*-
"""FGA compartment, tree and drawing workflows.

Space and tree exports read the saved project database directly.  Commands
that need the live model (`brep`, `import-hull`, `draw`) launch FGA through the
configured wrapper, fill the `Database settings` dialog automatically, and
drive the GUI.

Commands
--------
  foran fga spaces --db <sample.db> --out spaces.tsv [--copy]
  foran fga tree   --db <sample.db> --out tree.tsv   [--copy]
  foran fga export --db <sample.db> --spaces spaces.tsv --tree tree.tsv [--copy]
  foran fga brep   --db <sample.db> --brep box.brep --node CARGO [--copy]
  foran fga brep   --db <sample.db> --box 20,10,8 --node CARGO [--copy]
  foran fga import-hull --db <sample.db> --fsf TESTfsurf.fsf [--copy]
  foran fga draw   --db <sample.db> --out ga.dxf    [--copy] [--views plan,side,transv]

`--copy` first copies the DB into `_foran_work/projects/` and opens the copy
(recommended; FORAN may write to the database it opens).

The exported columns come from the persisted FGA tree tables
(`DSG_SPC_TREE`, `DSG_SPC_PROPS`, `DSG_GSF_TREE`, `DSG_COMPT_TREE`).
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_ui as UI  # noqa: E402



def _close_fga(G) -> None:
    saw_error = False
    for _ in range(3):
        dialogs = [w for w in G.windows()
                   if w.get("title") in ("Error", "Warning", "Please confirm...",
                                         "Information modified")]
        if dialogs:
            for w in dialogs:
                title = w.get("title")
                if title == "Error":
                    saw_error = True
                    names = ("Close", "Ok", "OK")
                elif title == "Information modified":
                    names = ("No",) if saw_error else ("Yes", "No")
                else:
                    names = ("Ok", "OK", "Yes", "Close")
                for name in names:
                    if _click_button(G, w["hwnd"], name):
                        break
            time.sleep(0.8)
            continue
        hits = [w for w in G.windows() if w.get("title", "").startswith("fga -")]
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


def _tsv_escape(v) -> str:
    if v is None:
        return ""
    return str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _ro_db(db: Path):
    return sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)


def _has_table(con, name: str) -> bool:
    return con.execute(
        "select 1 from sqlite_master where type='table' and name=?", (name,)
    ).fetchone() is not None


def _write_tsv(out: Path, header: list[str], rows: list[list]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write("\t".join(header) + "\n")
        for row in rows:
            fh.write("\t".join(_tsv_escape(v) for v in row) + "\n")


def _spaces_rows(db: Path) -> list[list]:
    """Read spaces from the saved project DB (DSG_SPC_TREE + DSG_SPC_PROPS)."""
    con = _ro_db(db)
    try:
        if not (_has_table(con, "DSG_SPC_TREE") and _has_table(con, "DSG_SPC_PROPS")):
            return []
        sql = """
            select t.NAME, t.DESCRIPTION, p.VOLUME, p.X_COG, p.Y_COG, p.Z_COG,
                   p.AREA, p.X_MIN, p.X_MAX, p.Y_MIN, p.Y_MAX, p.Z_MIN, p.Z_MAX,
                   t.TYPE, t.OID
              from DSG_SPC_TREE t
              join DSG_SPC_PROPS p on p.SPC_TREE_OID = t.OID
             order by t.OID
        """
        return [list(r) for r in con.execute(sql)]
    finally:
        con.close()


def _tree_rows(db: Path) -> list[list]:
    """Best-effort dump of GspView/GsfView/CmpView from the saved DB.

    This reads the persisted trees and maps the known GSF type codes
    (3 External hull, 4 Patch, 6 Surface, 9 Deck).  Unknown codes are printed
    as the raw integer.
    """
    con = _ro_db(db)
    try:
        props = {}
        if _has_table(con, "DSG_SPC_PROPS"):
            props = {r[0]: r[1] for r in con.execute(
                "select SPC_TREE_OID, VOLUME from DSG_SPC_PROPS")}
        rows: list[list] = []
        for view, table in (("GspView", "DSG_SPC_TREE"),
                            ("GsfView", "DSG_GSF_TREE"),
                            ("CmpView", "DSG_COMPT_TREE")):
            if not _has_table(con, table):
                continue
            for oid, name, desc, typ, _parent in con.execute(
                    f"select OID, NAME, DESCRIPTION, TYPE, PARENT_OID "
                    f"from {table} order by OID"):
                is_space = view == "GspView" and oid in props
                is_patch = view == "GsfView" and typ == 4
                is_deck = view == "GsfView" and typ == 9
                is_surface = view == "GsfView" and typ in (3, 6)
                rows.append([
                    view, typ, name, desc, oid,
                    str(is_space).lower(), "false",
                    str(is_surface).lower(), str(is_patch).lower(),
                    str(is_deck).lower(), "false",
                    props.get(oid, ""),
                ])
        return rows
    finally:
        con.close()


def cmd_spaces(a) -> int:
    db = _prepare_db(a)
    out = Path(a.out).expanduser().resolve()
    rows = _spaces_rows(db)
    _write_tsv(out, ["name", "description", "volume", "xcog", "ycog", "zcog",
                     "area", "xmin", "xmax", "ymin", "ymax", "zmin", "zmax",
                     "type", "oid"], rows)
    print(f"spaces   : {len(rows)} -> {out}")
    return 0


def cmd_tree(a) -> int:
    db = _prepare_db(a)
    out = Path(a.out).expanduser().resolve()
    rows = _tree_rows(db)
    _write_tsv(out, ["view", "type", "name", "description", "oid",
                     "is_space", "is_subspace", "is_surface", "is_patch",
                     "is_deck", "is_work_deck", "volume"], rows)
    print(f"tree     : {len(rows)} -> {out}")
    return 0


def cmd_export(a) -> int:
    db = _prepare_db(a)
    spaces = Path(a.spaces).expanduser().resolve()
    tree = Path(a.tree).expanduser().resolve()
    srows = _spaces_rows(db)
    _write_tsv(spaces, ["name", "description", "volume", "xcog", "ycog", "zcog",
                        "area", "xmin", "xmax", "ymin", "ymax", "zmin", "zmax",
                        "type", "oid"], srows)
    trows = _tree_rows(db)
    _write_tsv(tree, ["view", "type", "name", "description", "oid",
                      "is_space", "is_subspace", "is_surface", "is_patch",
                      "is_deck", "is_work_deck", "volume"], trows)
    print(f"spaces   : {len(srows)} -> {spaces}")
    print(f"tree     : {len(trows)} -> {tree}")
    return 0


def _wait_main(G, timeout: float = 60.0):
    end = time.time() + timeout
    while time.time() < end:
        for w in G.windows():
            if w.get("title", "").startswith("fga -"):
                return w
        time.sleep(0.4)
    return None


def _save_project(G, hwnd: int) -> bool:
    """File > Save by UIA menu name; the old coordinates are a last resort."""
    UI.menu_click(G, hwnd, "File", (57, 54))
    time.sleep(0.5)
    return UI.menu_click(G, hwnd, "Save", (110, 91))


_SPACE_TABS = ("Summary", "Six limits", "Surfaces set", "Imported", "Parametric")


def _button_has_green(rect) -> bool:
    """True when the button bitmap contains the green icon (+ etc.)."""
    import pyautogui
    left, top = int(rect.left), int(rect.top)
    width = max(1, int(rect.right) - left)
    height = max(1, int(rect.bottom) - top)
    im = pyautogui.screenshot(region=(left, top, width, height))
    px = im.load()
    for y in range(0, im.height, 2):
        for x in range(0, im.width, 2):
            r, g, b = px[x, y][:3]
            if g > 90 and r < 90 and b < 90:
                return True
    return False


def _space_panel_buttons(hwnd: int):
    """Locate the space-definition toolbar buttons (Save & Exit, green +).

    They are custom QToolButtons with no accessible name.  The row sits just
    above the Summary/Six limits/... tab strip; Save & Exit is the leftmost
    icon and the '+' is the first green icon in the panel group.
    """
    d = G._app_window(hwnd, "uia")
    tabs = [c for c in d.descendants(control_type="TabItem")
            if (c.window_text() or "").strip() in _SPACE_TABS]
    if not tabs:
        return None, None
    strip_top = min(c.rectangle().top for c in tabs)
    strip_left = min(c.rectangle().left for c in tabs)
    row = [c for c in d.descendants(control_type="Button")
           if not (c.window_text() or "").strip()
           and 0 <= strip_top - c.rectangle().bottom <= 30]
    if not row:
        return None, None
    row.sort(key=lambda c: c.rectangle().left)
    save = row[0]
    plus = None
    for c in row:
        r = c.rectangle()
        if r.left < strip_left - 10:
            continue
        if _button_has_green(r):
            plus = c
            break
    return save, plus


def _wait_tree(G, hwnd: int, pred, timeout: float = 3.0):
    return UI.wait_tree_item(G, hwnd, pred, timeout)


def _click_rel(G, win, dx: int, dy: int, pause: float = 0.8) -> None:
    """Click at (window left + dx, window top + dy). Coordinates were measured
    on the maximized default FGA layout (V80R3.0, 1920x1080)."""
    import pyautogui
    left, top = win["rect"][0], win["rect"][1]
    G._focus(win["hwnd"])
    pyautogui.click(left + dx, top + dy)
    time.sleep(pause)


def _menu(G, win, x: int, y: int, pause: float = 1.0) -> None:
    _click_rel(G, win, x, y, pause)


def _click_button(G, hwnd: int, title: str, panel: str | None = None) -> bool:
    try:
        d = G._app_window(hwnd, "uia")
        scope = d
        if panel:
            scope = d.child_window(title=panel, control_type="Window")
        scope.child_window(title=title, control_type="Button").click_input()
        return True
    except Exception:  # noqa: BLE001
        return False


def _drawing_panel(G, hwnd: int):
    try:
        d = G._app_window(hwnd, "uia")
        return d.child_window(title="2D draw", control_type="Window")
    except Exception:  # noqa: BLE001
        return None


def _wait_panel(G, hwnd: int, present: bool, timeout: float = 20.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        panel = _drawing_panel(G, hwnd)
        ok = panel is not None
        if ok == present:
            return True
        time.sleep(0.4)
    return False


def _handle_warning(G, yes: bool = True) -> str:
    for w in G.windows():
        if w.get("title") in ("Warning", "Error", "Please confirm..."):
            try:
                d = G._app_window(w["hwnd"], "uia")
                text = " | ".join(c.window_text() for c in d.descendants(control_type="Text")
                                  if c.window_text())
            except Exception:  # noqa: BLE001
                text = ""
            for name in (("Yes", "Ok", "OK") if yes else ("No", "Cancel")):
                if _click_button(G, w["hwnd"], name):
                    return text
            return text
    return ""


def _space_rows(db: Path) -> set[tuple[int, str]]:
    import sqlite3
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return {(int(r[0]), str(r[1])) for r in
                con.execute("select OID,NAME from DSG_SPC_TREE where TYPE=7")}
    finally:
        con.close()


def _file_dialog_choose(G, file: Path, title: str = "Import spaces file") -> bool:
    """Choose `file` in FGA's `Import spaces file` / `Import surfaces file` dialog.

    The dialog's filter must match the extension; the file must be *clicked in
    the list* (a full path in `File name` leaves Open disabled).
    """
    import pyperclip
    win = next((w for w in G.windows() if w.get("title") == title), None)
    if win is None:
        return False
    hwnd = win["hwnd"]
    G._focus(hwnd)
    pyautogui = __import__("pyautogui")
    # 1) file-type filter (the ComboBox next to the "Files of type:" label)
    combo = None
    try:
        d = G._app_window(hwnd, "uia")
        label = next((c for c in d.descendants(control_type="Text")
                      if (c.window_text() or "").strip().lower()
                      .startswith("files of type")), None)
        if label is not None:
            top = label.rectangle().top
            cands = [c for c in d.descendants(control_type="ComboBox")
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
    ext = file.suffix.lower()
    pyautogui.press("home")
    if ext == ".fsf":
        pass  # FSURF file (*.fsf) is the first filter
    elif ext in (".stp", ".step"):
        pass
    elif ext in (".igs", ".iges"):
        pyautogui.press("down")
    else:  # .brep
        pyautogui.press("end")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(1.0)

    # 2) click the file in the list (cmd_brep copies it into the FGA workdir,
    #    which is the dialog's default `Look in` directory).
    d = G._app_window(hwnd, "uia")
    clicked = False
    try:
        for c in d.descendants(control_type="ListItem"):
            if (c.window_text() or "").strip() == file.name:
                c.click_input()
                clicked = True
                break
    except Exception:  # noqa: BLE001
        pass
    if not clicked:
        try:
            e = d.child_window(title="File name:", control_type="Edit")
            e.click_input()
            pyautogui.hotkey("ctrl", "a")
            pyperclip.copy(file.name)
            pyautogui.hotkey("ctrl", "v")
            clicked = True
        except Exception:  # noqa: BLE001
            pass
    time.sleep(0.6)

    # 4) Open button at the bottom of the dialog
    for c in d.descendants(control_type="Button"):
        try:
            if (c.window_text() or "").strip() == "Open" and c.rectangle().top > 600:
                c.click_input()
                time.sleep(3)
                return not any(w.get("title") == "Import spaces file" for w in G.windows())
        except Exception:  # noqa: BLE001
            pass
    return False


def cmd_brep(a) -> int:
    global G
    """Import a closed BREP/STEP/IGES solid as a new FGA space.

    Flow (verified manually on sample.db, 2026-10-26):
      lock project/tree -> select work-area node -> Set active -> New space ->
      Imported tab -> green + -> choose the file -> Save & Exit -> save project.
    """
    try:
        import foran_gui as G
        import pyautogui
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    if not a.brep and not a.box:
        raise SystemExit("give --brep <file> or --box L,W,H[,X,Y,Z]")
    if a.box:
        try:
            vals = [float(v) for v in a.box.split(",")]
        except ValueError:
            raise SystemExit(f"--box must be L,W,H[,X,Y,Z], got {a.box!r}")
        if len(vals) not in (3, 6):
            raise SystemExit(f"--box needs 3 or 6 numbers, got {len(vals)}")
        l, w, h = vals[:3]
        ox, oy, oz = (vals[3:6] + [0.0, 0.0, 0.0])[:3]
        try:
            import gmsh
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"--box needs gmsh in the skill venv ({exc}); "
                             f"pip install gmsh")
        box_dir = Path.cwd() / "_foran_work" / "fga" / "box"
        box_dir.mkdir(parents=True, exist_ok=True)
        src = box_dir / f"box_{dt.datetime.now():%Y%m%d-%H%M%S}.brep"
        gmsh.initialize()
        gmsh.model.add("box")
        gmsh.model.occ.addBox(ox, oy, oz, l, w, h)
        gmsh.model.occ.synchronize()
        gmsh.write(str(src))
        gmsh.finalize()
        print(f"box      : {l}x{w}x{h} at ({ox},{oy},{oz}) -> {src}")
    else:
        src = Path(a.brep).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"BREP/STEP/IGES file not found: {src}")
    if src.suffix.lower() not in (".brep", ".stp", ".step", ".igs", ".iges"):
        raise SystemExit("supported formats: .brep .stp .step .igs .iges")

    running = [w for w in G.windows("fga") if w.get("process", "").lower() == "fga.exe"
               or w.get("title", "").startswith("fga -")]
    if running:
        if not a.close_existing:
            print(f"FGA is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return 2
        _close_fga(G)
        time.sleep(2)

    db = _prepare_db(a)
    before = _space_rows(db)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fga" / f"brep_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Keep a copy of the solid in FGA's workdir so the import dialog lists it.
    local_file = run_dir / src.name
    shutil.copy2(src, local_file)
    import foran_launch as L
    rc = L.main(["fga", "--workdir", str(run_dir)])
    if rc:
        return 1
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close_fga(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    win = _wait_main(G, 60)
    if win is None:
        print("FGA main window not found", file=sys.stderr)
        _close_fga(G)
        return 1
    time.sleep(1.5)

    # 1) select the target work-area node
    d = G._app_window(win["hwnd"], "uia")
    node = None
    for c in d.descendants(control_type="TreeItem"):
        try:
            r = c.rectangle()
            if (c.window_text() or "").strip() == a.node and (r.right - r.left) > 80:
                node = c.rectangle()
                break
        except Exception:  # noqa: BLE001
            pass
    if node is None:
        print(f"space node not found: {a.node!r}", file=sys.stderr)
        _close_fga(G)
        return 1
    cx, cy = (node.left + node.right) // 2, (node.top + node.bottom) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.7)
    # 2) Set active (context menu item 10)
    pyautogui.click(cx, cy, button="right")
    time.sleep(1.1)
    for _ in range(11):
        pyautogui.press("down")
        time.sleep(0.07)
    pyautogui.press("enter")
    time.sleep(1.2)
    # 3) New space (context menu item 12)
    pyautogui.click(cx, cy, button="right")
    time.sleep(1.1)
    for _ in range(13):
        pyautogui.press("down")
        time.sleep(0.07)
    pyautogui.press("enter")
    time.sleep(3.0)
    # 4) Imported tab + green +
    try:
        d.child_window(title="Imported", control_type="TabItem").click_input()
    except Exception:  # noqa: BLE001
        print("Imported tab not found", file=sys.stderr)
        _close_fga(G)
        return 1
    time.sleep(1.2)
    _save_btn, plus_btn = _space_panel_buttons(win["hwnd"])
    if plus_btn is not None:
        plus_btn.click_input()
    else:
        print("space panel '+' not exposed; using coordinates", file=sys.stderr)
        pyautogui.click(470, 710)
    time.sleep(2.5)
    if not _file_dialog_choose(G, local_file):
        print("could not choose the file in `Import spaces file`", file=sys.stderr)
        _close_fga(G)
        return 1
    # Large BREP/STEP solids can take a while to tessellate; give the import
    # enough time before Save & Exit.
    time.sleep(30)
    err = next((w for w in G.windows() if w.get("title") == "Error"), None)
    if err is not None:
        try:
            d2 = G._app_window(err["hwnd"], "uia")
            txt = " | ".join(c.window_text() for c in d2.descendants(control_type="Text")
                             if c.window_text())
            print(f"import error: {txt}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        _close_fga(G)
        return 1
    # 5) Save & Exit, then close FGA and save the project
    save_btn, _plus = _space_panel_buttons(win["hwnd"])
    if save_btn is not None:
        try:
            save_btn.click_input()
        except Exception:  # noqa: BLE001
            pyautogui.click(14, 710)
    else:
        print("space panel 'Save & Exit' not exposed; using coordinates",
              file=sys.stderr)
        pyautogui.click(14, 710)
    time.sleep(3)
    _close_fga(G)
    time.sleep(2)

    after = _space_rows(db)
    new = sorted(after - before)
    if new:
        print("imported : " + ", ".join(f"{name} (OID {oid})" for oid, name in new))
    else:
        print("no new space appeared in DSG_SPC_TREE", file=sys.stderr)
        return 1
    return 0


def _surface_patch_info(db: Path, surface: str = "External hull") -> tuple[int, list[str]]:
    """(patch count, patch names) of a surface in DSG_GSF_TREE (-1 = no surface)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select OID from DSG_GSF_TREE where NAME=? and TYPE=3", (surface,)).fetchone()
        if row is None:
            return -1, []
        names = [r[0] for r in con.execute(
            "select NAME from DSG_GSF_TREE where PARENT_OID=? and TYPE=4 order by NAME",
            (row[0],))]
        return len(names), names
    finally:
        con.close()


def _dialog_text(G, hwnd: int) -> str:
    try:
        d = G._app_window(hwnd, "uia")
        return " | ".join(c.window_text() for c in d.descendants(control_type="Text")
                          if c.window_text())
    except Exception:  # noqa: BLE001
        return ""


def _handle_overwrite_prompts(G, choice: str, timeout: float = 120.0) -> int:
    """Click through `Surface ... is already defined` prompts.

    FGA raises the prompt several seconds after the wizard's OK (the surface
    is prepared first), so an immediate scan finds nothing and the old code
    returned 0 while the prompt was still about to appear.  Wait for the first
    prompt, then keep handling until the import command ends.
    """
    end = time.time() + timeout
    first_deadline = time.time() + 60
    handled = 0
    while time.time() < end:
        found = None
        for w in G.windows():
            if w.get("class") != "QWidget":
                continue
            txt = _dialog_text(G, w["hwnd"])
            if "already defined" in txt or "overwrite" in txt.lower():
                found = w
                break
        if found is not None:
            G._focus(found["hwnd"])
            time.sleep(0.4)
            names = ("Yes to All",) if choice == "all" else (
                ("Yes",) if choice == "yes" else ("No to All", "No"))
            for name in names:
                if _click_button(G, found["hwnd"], name):
                    handled += 1
                    break
            time.sleep(1.0)
            first_deadline = time.time() + 60
            continue
        if _journal_end_seen():
            return handled
        if handled == 0 and time.time() > first_deadline:
            return 0
        time.sleep(1.0)
    return handled


def _journal_end_seen(cmd: str = "SrfCmdImportFormsFile") -> bool:
    import glob
    import os
    files = sorted(glob.glob(os.path.join(os.path.expanduser("~"), ".foran", "journal",
                                          "*fga*.jrnl.csv")),
                   key=os.path.getmtime)
    if not files:
        return False
    try:
        txt = Path(files[-1]).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return False
    i = txt.rfind(cmd)
    return i >= 0 and "COMMAND_END" in txt[i:]


def _hull_line_snapshot(db: Path, surface: str = "External hull") -> dict:
    """Capture the significant lines under `surface` before a Hull forms import.

    `SrfCmdImportFormsFile` replaces the External hull surface and deletes its
    children -- including the PROFILE line (`CL`) and its wire.  FBASIC then
    prints "The ship's profile is not defined" at every start.  Snapshot the
    rows here and re-insert them after the import (see `_restore_hull_lines`).
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select OID from DSG_GSF_TREE where NAME=? and TYPE=3", (surface,)).fetchone()
        if row is None:
            return {}
        nodes = [r[0] for r in con.execute(
            "select OID from DSG_GSF_TREE where PARENT_OID=? and TYPE=6 order by OID",
            (row[0],))]
        if not nodes:
            return {}
        q = ",".join("?" * len(nodes))

        def grab(sql: str) -> dict:
            cur = con.execute(sql, nodes)
            return {"cols": [d[0] for d in cur.description], "rows": cur.fetchall()}

        return {
            "nodes": nodes,
            "tree": grab("select OID,NAME,DESCRIPTION,TYPE,PARENT_OID "
                         f"from DSG_GSF_TREE where OID in ({q})"),
            "line": grab("select OID,GSF_TREE_OID,LINE_TYPE,LINE_NUMBER,GSF_SRF_OID "
                         f"from DSG_LINE_DATA where GSF_TREE_OID in ({q})"),
            "wire": grab("select OID,DSG_LINE_OID,ORIENT,X_MIN,Y_MIN,Z_MIN,X_MAX,Y_MAX,Z_MAX,OCC_WIRE "
                         f"from DSG_WIRE_DIR where DSG_LINE_OID in ({q})"),
            "user": grab("select * from DSG_TREE_USER_DATE "
                         f"where GSF_TREE_OID in ({q})"),
        }
    finally:
        con.close()


def _next_free(used: set[int], preferred: int, counter: list[int]) -> int:
    if preferred not in used:
        used.add(preferred)
        return preferred
    while counter[0] in used:
        counter[0] += 1
    oid = counter[0]
    used.add(oid)
    counter[0] += 1
    return oid


def _restore_hull_lines(db: Path, snap: dict, surface: str = "External hull") -> int:
    """Re-insert a `_hull_line_snapshot` under the current External hull."""
    if not snap or not snap.get("nodes"):
        return 0
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "select OID from DSG_GSF_TREE where NAME=? and TYPE=3", (surface,)).fetchone()
        if row is None:
            print("lines    : no External hull after import; not restored", file=sys.stderr)
            return 0
        ext = row[0]
        have = con.execute(
            "select count(*) from DSG_GSF_TREE where PARENT_OID=? and TYPE=6", (ext,)).fetchone()[0]
        if have:
            print(f"lines    : {have} line(s) already present; not restored")
            return 0

        tree_used = {r[0] for r in con.execute("select OID from DSG_GSF_TREE")}
        line_used = {r[0] for r in con.execute("select OID from DSG_LINE_DATA")}
        wire_used = {r[0] for r in con.execute("select OID from DSG_WIRE_DIR")}
        user_used = {r[0] for r in con.execute("select OID from DSG_TREE_USER_DATE")}
        tree_ctr = [max(tree_used or {0}) + 1]
        line_ctr = [max(line_used or {0}) + 1]
        wire_ctr = [max(wire_used or {0}) + 1]
        user_ctr = [max(user_used or {0}) + 1]

        tree_map: dict[int, int] = {}
        for oid, name, desc, typ, _parent in snap["tree"]["rows"]:
            new = _next_free(tree_used, oid, tree_ctr)
            tree_map[oid] = new
            con.execute("insert into DSG_GSF_TREE (OID,NAME,DESCRIPTION,TYPE,PARENT_OID) "
                        "values (?,?,?,?,?)", (new, name, desc, typ, ext))

        for oid, tree_oid, line_type, number, _srf in snap["line"]["rows"]:
            new = _next_free(line_used, oid, line_ctr)
            con.execute("insert into DSG_LINE_DATA "
                        "(OID,GSF_TREE_OID,LINE_TYPE,LINE_NUMBER,GSF_SRF_OID) values (?,?,?,?,?)",
                        (new, tree_map.get(tree_oid, tree_oid), line_type, number, ext))

        for oid, tree_oid, orient, xmin, ymin, zmin, xmax, ymax, zmax, wire in snap["wire"]["rows"]:
            new = _next_free(wire_used, oid, wire_ctr)
            con.execute("insert into DSG_WIRE_DIR "
                        "(OID,DSG_LINE_OID,ORIENT,X_MIN,Y_MIN,Z_MIN,X_MAX,Y_MAX,Z_MAX,OCC_WIRE) "
                        "values (?,?,?,?,?,?,?,?,?,?)",
                        (new, tree_map.get(tree_oid, tree_oid), orient,
                         xmin, ymin, zmin, xmax, ymax, zmax, wire))

        for row in snap["user"]["rows"]:
            vals = list(row)
            vals[0] = _next_free(user_used, vals[0], user_ctr)
            vals[1] = tree_map.get(vals[1], vals[1])
            con.execute("insert into DSG_TREE_USER_DATE values ({})".format(
                ",".join("?" * len(vals))), vals)

        con.commit()
        return len(tree_map)
    finally:
        con.close()


def _open_hull_forms_import(hwnd: int) -> None:
    """File > Export/Import... > Hull forms (last submenu item)."""
    import pyautogui
    G._focus(hwnd)
    pyautogui.press("escape")
    time.sleep(0.4)
    UI.menu_click(G, hwnd, "File", (57, 54))
    time.sleep(0.7)
    for _ in range(4):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("right")
    time.sleep(0.8)
    for _ in range(7):
        pyautogui.press("down")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)


def cmd_import_hull(a) -> int:
    global G
    """Import an FSURF .fsf as project surfaces (`Export/Import... > Hull forms`).

    Verified on sample.db (2026-10-27): FGA reads the FSF's main data and
    surfaces, then asks to overwrite the existing `External hull` surface.
    After saving, `DSG_GSF_TREE` holds one TYPE=4 (patch) row per patch of the
    imported hull, so FBASIC/FGA can use the generated hull instead of the
    mother ship's.

    Flow: launch FGA with `SrfCmdImportFormsFile` -> choose the .fsf ->
    Import surfaces OK -> Yes to All on the overwrite prompt -> File Save.
    The Import surfaces wizard is a custom-painted list; `Edit` cannot be
    driven through UIA, but it is not needed when the FSF already carries the
    `External hull` surface and its Location.

    The import replaces the External hull and deletes *all* its children,
    including the significant lines.  The PROFILE line (`CL`) is what FBASIC
    uses to decide whether "the ship's profile is defined"; without it every
    FBASIC start warns.  The lines are snapshotted before the import and
    re-inserted afterwards; pass --no-restore-lines to skip that.
    """
    try:
        import foran_gui as G
        import pyautogui
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3
    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy or --in-place.",
              file=sys.stderr)
        return 2
    src = Path(a.fsf).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"FSF not found: {src}")
    if src.suffix.lower() != ".fsf":
        raise SystemExit("--fsf must be a FSURF .fsf file")

    running = [w for w in G.windows("fga") if w.get("process", "").lower() == "fga.exe"
               or w.get("title", "").startswith("fga -")]
    if running:
        if not a.close_existing:
            print(f"FGA is already running ({running[0]['title']!r}); close it or "
                  f"pass --close-existing.", file=sys.stderr)
            return 2
        _close_fga(G)
        time.sleep(2)

    db = _prepare_db(a)
    line_snap = _hull_line_snapshot(db)
    if line_snap:
        print(f"lines    : captured {len(line_snap['nodes'])} (PROFILE included)")
    before_n, before_names = _surface_patch_info(db)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fga" / f"importhull_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    local_file = run_dir / src.name
    shutil.copy2(src, local_file)
    import foran_launch as L
    rc = L.main(["fga", "--workdir", str(run_dir)])
    if rc:
        return 1
    print(f"run dir  : {run_dir}")
    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close_fga(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")
    main = _wait_main(G, 60)
    if main is None:
        print("FGA main window not found", file=sys.stderr)
        _close_fga(G)
        return 1
    _open_hull_forms_import(main["hwnd"])

    # 1) choose the .fsf in `Import surfaces file`
    end = time.time() + 90
    while time.time() < end and not any(
            w.get("title") == "Import surfaces file" for w in G.windows()):
        time.sleep(0.4)
    if not _file_dialog_choose(G, local_file, title="Import surfaces file"):
        print("could not choose the file in `Import surfaces file`", file=sys.stderr)
        _close_fga(G)
        return 1
    # 2) Import surfaces wizard -> OK (surface is already configured in the FSF)
    win = None
    end = time.time() + 60
    while time.time() < end:
        win = next((w for w in G.windows() if w.get("title") == "Import surfaces"), None)
        if win:
            break
        time.sleep(0.4)
    if win is None:
        print("`Import surfaces` wizard not found", file=sys.stderr)
        _close_fga(G)
        return 1
    G._focus(win["hwnd"])
    time.sleep(0.2)
    ok = False
    for c in G._app_window(win["hwnd"], "uia").descendants(control_type="Button"):
        try:
            if (c.window_text() or "").strip() == "OK":
                c.invoke()
                ok = True
                break
        except Exception:  # noqa: BLE001
            pass
    if not ok:
        print("`Import surfaces`: OK not found", file=sys.stderr)
        _close_fga(G)
        return 1
    # 3) overwrite prompts (the stock project already has `External hull`)
    handled = _handle_overwrite_prompts(G, a.overwrite, timeout=60)
    print(f"overwrite: {handled} prompt(s), choice={a.overwrite}")
    # 4) wait for the import command itself
    end = time.time() + a.timeout
    while time.time() < end and not _journal_end_seen():
        err = next((w for w in G.windows() if w.get("title") == "Error"), None)
        if err is not None:
            print(f"import error: {_dialog_text(G, err['hwnd'])}", file=sys.stderr)
            _close_fga(G)
            return 1
        time.sleep(1)
    # 5) save the project
    main = _wait_main(G, 30)
    if main is None:
        print("FGA main window not found", file=sys.stderr)
        _close_fga(G)
        return 1
    before_mtime = db.stat().st_mtime
    G._focus(main["hwnd"])
    time.sleep(0.15)
    _save_project(G, main["hwnd"])
    end = time.time() + 30
    while time.time() < end and db.stat().st_mtime <= before_mtime:
        time.sleep(1)
    saved = db.stat().st_mtime > before_mtime
    print(f"saved    : {saved}")
    if not a.keep_open:
        _close_fga(G)
        time.sleep(2)

    after_n, after_names = _surface_patch_info(db)
    print(f"surface  : External hull patches {before_n} -> {after_n}")
    if after_n > 0:
        print("patches  : " + ", ".join(after_names))
    if not saved or after_n <= 0:
        return 1
    if line_snap and not a.no_restore_lines:
        if a.keep_open:
            print("lines    : FGA kept open; restore skipped (rerun without "
                  "--keep-open to restore)", file=sys.stderr)
        else:
            restored = _restore_hull_lines(db, line_snap)
            print(f"lines    : restored {restored} (PROFILE included)")
    return 0


def cmd_draw(a) -> int:
    global G
    """Create + arrange + export a General Arrangement drawing to DXF.

    Flow (verified manually on sample.db):
      General arrangements tab -> select Ship -> New drawing -> add views ->
      Ok -> select the drawing row -> Arrange drawing -> File/Save as (DXF) ->
      File/Save drawing -> File/Exit 2D context.
    """
    try:
        import foran_gui as G
        import pyautogui
    except Exception as exc:  # noqa: BLE001
        print(f"GUI dependencies missing ({exc}). Run with the skill venv.", file=sys.stderr)
        return 3

    running = [w for w in G.windows("fga") if w.get("process", "").lower() == "fga.exe"
               or w.get("title", "").startswith("fga -")]
    if running:
        if not a.close_existing:
            print(f"FGA is already running ({running[0]['title']!r}). "
                  f"Close it first, or pass --close-existing.", file=sys.stderr)
            return 2
        _close_fga(G)
        time.sleep(2)

    if not a.copy and not a.in_place:
        print("refusing to write the original database: pass --copy (recommended) "
              "or --in-place if you really mean it.", file=sys.stderr)
        return 2
    if a.in_place:
        print("WARNING: --in-place writes the GA drawing into the original database.")
    db = _prepare_db(a)
    out = Path(a.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path.cwd() / "_foran_work" / "fga" / f"draw_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    import foran_launch as L
    rc = L.main(["fga", "--workdir", str(run_dir)])
    if rc:
        _close_fga(G)
        return 1
    print(f"run dir  : {run_dir}")

    try:
        db_info = G.fill_database_dialog(str(db), timeout=60, shot_dir=str(run_dir))
    except SystemExit as exc:
        print(f"database dialog: {exc}", file=sys.stderr)
        _close_fga(G)
        return 1
    print(f"database : {db_info['fnam']} -> {db_info['db']}")

    win = _wait_main(G, 60)
    if win is None:
        print("FGA main window not found", file=sys.stderr)
        _close_fga(G)
        return 1
    time.sleep(2)
    # Make the layout deterministic (the measured coordinate offsets assume a
    # maximized window on 1920x1080).
    try:
        import win32con
        import win32gui
        win32gui.ShowWindow(win["hwnd"], win32con.SW_MAXIMIZE)
    except Exception:  # noqa: BLE001
        pass
    G._focus(win["hwnd"])
    time.sleep(1)
    r = win["rect"]
    width, height = r[2] - r[0], r[3] - r[1]
    if not (1750 <= width <= 2100 and 900 <= height <= 1200):
        print(f"warning: FGA window is {width}x{height}; `fga draw` coordinates were "
              f"measured on a maximized 1920x1080 window and may miss.", file=sys.stderr)

    # 1. General arrangements tab.
    try:
        d = G._app_window(win["hwnd"], "uia")
        d.child_window(title="General arrangements", control_type="TabItem").click_input()
    except Exception:  # noqa: BLE001
        _click_rel(G, win, 28, 501)
    time.sleep(1.5)

    # 2. Select the Ship root (the only node before any drawing exists).
    ship = _wait_tree(G, win["hwnd"], lambda t: t == "Ship", 3.0)
    if ship is not None:
        ship.click_input()
        time.sleep(0.8)
    else:
        _click_rel(G, win, 88, 204, pause=0.8)

    # 3. Tools -> New drawing.  Opening the menu bar by coordinate is the
    # reliable part; the item itself is picked by UIA name.
    _menu(G, win, 482, 65)
    UI.menu_click(G, win["hwnd"], "New drawing", (482, 210), pause=1.5,
                  popup_first=True)
    if not _wait_panel(G, win["hwnd"], True, 20):
        print("2D draw panel did not open", file=sys.stderr)
        _shot(G, win, run_dir, "no_draw_panel")
        _close_fga(G)
        return 1

    panel = _drawing_panel(G, win["hwnd"])
    name = a.name
    try:
        edits = panel.descendants(control_type="Edit")
    except Exception:  # noqa: BLE001
        edits = []
    if name and edits:
        edits[0].click_input()
        pyautogui.hotkey("ctrl", "a")
        pyautogui.typewrite(name, interval=0.02)
    elif edits:
        try:
            name = edits[0].get_value()
        except Exception:  # noqa: BLE001
            name = "DRAW"
    else:
        name = name or "DRAW"
    print(f"drawing  : {name}")

    # 4. Add views, then Ok.
    views = [v.strip().lower() for v in a.views.split(",") if v.strip()]
    bad = [v for v in views if v not in ("plan", "side", "transv")]
    if bad:
        print(f"unknown views: {bad} (choose plan,side,transv)", file=sys.stderr)
        _close_fga(G)
        return 2
    for label in views:
        btn = {"plan": "Plan", "side": "Side", "transv": "Transv."}[label]
        if not _click_button(G, win["hwnd"], btn, panel="2D draw"):
            print(f"view button not found: {btn}", file=sys.stderr)
            _close_fga(G)
            return 1
        time.sleep(1.5)
    if not _click_button(G, win["hwnd"], "Ok", panel="2D draw"):
        print("Ok button not found in 2D draw", file=sys.stderr)
        _close_fga(G)
        return 1
    _wait_panel(G, win["hwnd"], False, 20)
    time.sleep(2)

    # 5. Select the new drawing row (first child of Ship) and arrange it.
    row = _wait_tree(G, win["hwnd"], lambda t: t == name, 3.0)
    if row is not None:
        row.click_input()
        time.sleep(1.0)
    else:
        _click_rel(G, win, 141, 225, pause=1.0)
    _menu(G, win, 482, 65)
    UI.menu_click(G, win["hwnd"], "Arrange drawing", (482, 341), pause=4.0,
                  popup_first=True)
    text = _handle_warning(G, yes=True)
    if text:
        print(f"arrange warning: {text}", file=sys.stderr)
        if "item selected" in text.lower():
            _shot(G, win, run_dir, "arrange_bad_item")
            _close_fga(G)
            return 1

    # 6. File -> Save as -> DXF.  The 2D context menu appears once arranged.
    deadline = time.time() + a.arrange_timeout
    while time.time() < deadline:
        titles = [w.get("title", "") for w in G.windows() if w.get("title", "").startswith("fga -")]
        if titles and "[" in titles[0]:
            break
        time.sleep(1)
    time.sleep(3)
    _menu(G, win, 43, 65)
    UI.menu_click(G, win["hwnd"], "Save as", (43, 178), pause=2.0,
                  popup_first=True)
    save = next((w for w in G.windows() if w.get("title") == "Save Drawing As"), None)
    if save is None:
        print("Save Drawing As did not open", file=sys.stderr)
        _shot(G, win, run_dir, "no_save_dialog")
        _close_fga(G)
        return 1
    try:
        d = G._app_window(save["hwnd"], "uia")
        e = d.child_window(title="File name:", control_type="Edit")
        e.click_input()
        import pyperclip
        pyperclip.copy(str(out))
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.4)
        d.child_window(title="Save", control_type="Button").click_input()
    except Exception as exc:  # noqa: BLE001
        print(f"cannot fill Save Drawing As: {exc}", file=sys.stderr)
        _close_fga(G)
        return 1

    deadline = time.time() + a.timeout
    while time.time() < deadline and not (out.exists() and out.stat().st_size > 0):
        time.sleep(0.5)
    if not out.exists():
        print("DXF was not written", file=sys.stderr)
        _shot(G, win, run_dir, "no_dxf")
        _close_fga(G)
        return 1
    print(f"DXF      : {out} ({out.stat().st_size} bytes)")

    # 7. Persist the drawing in the project DB, then leave the 2D context.
    _menu(G, win, 43, 65)
    UI.menu_click(G, win["hwnd"], "Save drawing", (43, 106), pause=2.0,
                  popup_first=True)
    _menu(G, win, 43, 65)
    UI.menu_click(G, win["hwnd"], "Exit 2D context", (43, 387), pause=3.0,
                  popup_first=True)
    _handle_warning(G, yes=False)  # cancel a "exit without saving" prompt
    if not a.keep_open:
        _close_fga(G)
    return 0


def _shot(G, win, run_dir: Path, tag: str) -> None:
    try:
        import pyautogui
        G._focus(win["hwnd"])
        left, top, right, bottom = win["rect"]
        pyautogui.screenshot(region=(left, top, right - left, bottom - top)).save(
            run_dir / f"{tag}.png")
    except Exception:  # noqa: BLE001
        pass


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


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--db", required=True, help="FORAN project .db")
        p.add_argument("--out", required=True, help="output TSV/JSON file")
        p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
        p.add_argument("--timeout", type=float, default=120.0)
        p.add_argument("--keep-open", action="store_true")
        p.add_argument("--close-existing", action="store_true",
                       help="close a running FGA before starting (may lose unsaved work)")
        p.add_argument("--shadow")

    p = sub.add_parser("spaces", help="export spaces (name/volume/CG/bbox) from the project DB")
    common(p); p.set_defaults(fn=cmd_spaces)
    p = sub.add_parser("tree", help="export the FGA geometric-spaces tree from the project DB")
    common(p); p.set_defaults(fn=cmd_tree)
    p = sub.add_parser("export", help="export spaces + tree in one FGA session")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--spaces", required=True, help="spaces TSV output")
    p.add_argument("--tree", required=True, help="design-tree TSV output")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--timeout", type=float, default=150.0)
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("brep", help="import a closed BREP/STEP/IGES solid as a new space")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--brep", help="solid file: .brep/.stp/.step/.igs/.iges")
    p.add_argument("--box", help="generate a box BREP first: L,W,H[,X,Y,Z] (needs gmsh)")
    p.add_argument("--node", default="CARGO", help="work-area node name (default CARGO)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_brep)

    p = sub.add_parser("import-hull", help="import an FSURF .fsf as project surfaces (Hull forms)")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--fsf", required=True, help="FSURF .fsf (after Build Ship)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the surfaces into the original DB (not recommended)")
    p.add_argument("--overwrite", choices=("yes", "all", "no"), default="all",
                   help="answer for an existing surface with the same name (default all)")
    p.add_argument("--timeout", type=float, default=180.0, help="import command timeout")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--no-restore-lines", action="store_true",
                   help="do not re-insert the External hull lines deleted by the import")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_import_hull)

    p = sub.add_parser("draw", help="create/arrange a GA drawing and export it to DXF")
    p.add_argument("--db", required=True, help="FORAN project .db")
    p.add_argument("--out", required=True, help="output DXF path")
    p.add_argument("--name", help="drawing name (default: the panel's DRAW-000N)")
    p.add_argument("--views", default="plan,side,transv",
                   help="comma list of plan,side,transv (default all)")
    p.add_argument("--copy", action="store_true", help="open a copy in _foran_work/projects")
    p.add_argument("--in-place", action="store_true",
                   help="write the GA drawing into the original DB (not recommended)")
    p.add_argument("--timeout", type=float, default=180.0, help="DXF write timeout")
    p.add_argument("--arrange-timeout", type=float, default=120.0)
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--close-existing", action="store_true")
    p.add_argument("--shadow")
    p.set_defaults(fn=cmd_draw)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
