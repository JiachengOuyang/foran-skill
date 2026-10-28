# FORAN skill

A Claude Code skill for automating **SENER FORAN V80R3.0** on Windows:
environment checks, read-only project-database queries, FBASIC/FGA/FSURF/FDM
launching, GUI automation, DXF post-processing and hydrostatic/offset
calculations.

> **Not affiliated with SENER.** FORAN is a commercial product. You must have
> your own valid FORAN installation and license. This repository contains only
> original automation code and documentation; it does **not** distribute FORAN,
> its installers, license files, help files or API dumps.

## What it can do

| Area | Commands |
|---|---|
| Environment | `foran setup`, `foran env check`, `foran selftest` |
| Project DB (read-only) | `foran db check/tables/schema/query/hydro/search/copy` |
| Launch | `foran launch fbasic/fga/fsurf/fdm` |
| FBASIC | `foran fbasic wh/hydro/cross/capacity/freeboard/tonnage/lsw/lc` |
| FGA | `foran fga spaces/tree/brep/draw/export` |
| FSURF | `foran fsf build/transform/decks/bulkheads/inner-shell/hopper/upper-tank/workflow/offsets` |
| FDM | `foran fdm open/export` |
| Lines / DXF | `foran draw`, `foran dxf frame/dwg2dxf/to-dwg` |
| Offsets / hydro | `foran offsets parse/export`, `foran hydro calc/compare` |
| Parametric hull | `foran hull gen` (no GUI) |
| Screen automation | `foran gui ...` (screenshot, controls, click, type) |

> **Scope:** workflows that open a FORAN window (FSURF modelling, live
> FBASIC, `fga draw/brep/import-hull`, `draw` including `--build-ship`, and
> `pipeline`) use GUI automation through your configured `wrapper_dir`;
> read-only queries read the saved project DB directly. `pipeline` requires
> a `CARGO` work-area node in the project DB.

## Requirements

- Windows 10/11, licensed **FORAN V80R3.0** (other V80 builds may work).
- Python 3.11+ (3.12 recommended; config.toml uses tomllib).
- GUI automation needs `pywinauto`, `pyautogui`, `Pillow`, `pyperclip`.
- `opencv-python-headless` for template matching; `ezdxf`/`openpyxl` for DXF/XLSX;
  `gmsh` only for `--brep` box examples.

## Install

```bash
git clone <this repo> foran-skill
cd foran-skill
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# configure your own paths/license
cp config.example.toml config.toml
# edit install_dir, license_file (optional), projects_dir
```

Use it as a Claude Code project skill by copying/symlinking this folder to
`.claude/skills/foran/`, or run the CLI directly:

```bash
python scripts/foran_cli.py env check
```

## Quick start

```bash
foran setup          # 首次使用：写 config.toml 并检查环境
foran env check
foran selftest --db C:/FORAN/projects/sample.db
foran db check C:/FORAN/projects/sample.db
foran launch fsurf --workdir ./work/fsurf
foran hull gen --lpp 150 --breadth 22 --draught 8 --depth 12 --cb 0.78 --out ./out/hull
foran dxf frame --in ./out/lines.dxf --out ./out/framed.dxf --sheet A1 --fit
foran offsets export --lis ./out/offsets.lis --out-prefix ./out/sample --stations 21
```


## Examples by module

> All examples run as documented; `pipeline` needs a project DB that
> already has a `CARGO` work-area node.

```bash
# --- environment / database (no FORAN window) ---
foran env check
foran env paths --json
foran db check  C:/FORAN/projects/sample.db
foran db tables C:/FORAN/projects/sample.db --filter HYD --counts
foran db hydro  C:/FORAN/projects/sample.db --json
foran db copy   C:/FORAN/projects/sample.db --out-dir ./work/projects

# --- launch ---
foran launch fbasic --project C:/FORAN/projects/sample.db --copy-project ./work/projects
foran launch fsurf  --workdir ./work/fsurf
foran launch fdm

# --- FBASIC ---
foran fbasic wh      --db ./work/projects/sample_copy.db --copy
foran fbasic hydro   --db ./work/projects/sample_copy.db --copy
foran fbasic capacity --db ./work/projects/sample_copy.db --copy

# --- FGA ---
foran fga spaces --db C:/FORAN/projects/sample.db --out ./out/spaces.tsv --copy
foran fga tree   --db C:/FORAN/projects/sample.db --out ./out/tree.tsv --copy
foran fga brep   --db C:/FORAN/projects/sample.db --box 20,10,8 --node CARGO --copy
foran fga draw   --db C:/FORAN/projects/sample.db --out ./out/ga.dxf --copy

# --- FSURF ---
foran fsf build  --brep ./out/hull.brep --fnam SAMP --lpp 150 --breadth 22                  --draught 8 --depth 12 --out ./out/SAMP.fsf
foran fsf decks  --fsf ./out/SAMP.fsf --deck "1:MainDeck:12:Main" --out ./out/SAMP_deck.fsf
foran fsf inner-shell --fsf ./out/SAMP.fsf --main-deck-z 12 --bottom-z 1.5                       --side-y 9.5 --x 40,70 --out ./out/SAMP_inner.fsf
foran draw --fsf ./out/SAMP.fsf --out ./out/lines.dxf --scale 200

# --- offsets / hydro / hull (pure Python) ---
foran offsets parse  --lis ./out/offsets.lis --draughts 8,8.5
foran offsets export --lis ./out/offsets.lis --out-prefix ./out/SAMP --stations 21
foran hydro calc     C:/FORAN/projects/sample.db --draft 8
foran hydro compare  C:/FORAN/projects/sample.db
foran hull gen --lpp 150 --breadth 22 --draught 8 --depth 12 --cb 0.78 --out ./out/hull --brep

# --- DXF / DWG ---
foran dxf frame  --in ./out/lines.dxf --out ./out/framed.dxf --sheet A1 --fit
foran dxf to-dwg --in ./out/framed.dxf --out ./out/framed.dwg
foran dxf dwg2dxf --in ./out/source.dwg --out ./out/source.dxf
```

## Configuration

All machine-specific values come from `config.toml` (or `FORAN_SKILL_*`
environment variables). See `config.example.toml`. **Do not commit** your real
`config.toml`, `.lic`, project `.db`/`.fsf`, or screenshots.

## Limitations

- GUI coordinates were calibrated on a **1920×1080 maximized** window. Other
  resolutions/scaling need recalibration; `foran gui` prints warnings when the
  screen size differs.
- UI strings are matched in Chinese; an English FORAN install may need changes.
- GUI calibration procedure: `references/gui-automation.md` and `references/portability.md`.
- Workflows that open a FORAN window need a working `wrapper_dir`; read-only
  queries work on a saved copy of the project DB. `pipeline` requires a
  `CARGO` work-area node.
- Only even-keel hydrostatics are implemented in `foran hydro calc`.

## License

Code: MIT (see `LICENSE`). Documentation: CC BY 4.0 unless noted.
FORAN and SENER are trademarks of SENER Ingeniería y Sistemas, S.A.
