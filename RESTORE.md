# Deploy / restore / update the FORAN skill

`foran setup` only writes the skill's `config.toml`; it does **not** install
FORAN or a license.

## New computer (FORAN already installed and licensed)

1. Copy this skill to `.claude/skills/foran/` (or run it from its own folder).
2. Install Python 3.11+ and the GUI/DXF dependencies:
   ```bash
   python -m pip install -r scripts/requirements.txt
   ```
3. Configure this machine:
   ```bash
   foran setup
   ```
   It asks for `install_dir`, `wrapper_dir`, `license_file`, `projects_dir`,
   `conf_dir`, `logs_dir`, `workdir`, writes `config.toml`, then runs
   `foran env check`.
4. Copy the project `.db` / `.fsf` files separately; they are not part of the
   repository.
5. Verify:
   ```bash
   foran env check
   foran selftest
   ```

## New computer without FORAN / license

Install FORAN and restore the license first, then follow the steps above.
The license (`.lic`), project databases and generated data are deliberately
not stored in this repository.

## Existing machine, already configured

Only check, do not write:

```bash
foran setup --check
```

To review or change an existing configuration:

```bash
foran setup
```

The default is to keep the current values; choose "n" to edit them.

## Updating the skill

1. Replace the code files, but keep `config.toml` (and any local files you
   added).
2. Check and test:
   ```bash
   foran setup --check
   foran selftest
   ```
3. If the update adds new configuration keys, `foran setup` keeps the old
   values and fills the new ones with detected defaults.

If the skill is a git checkout, `config.toml` is ignored, so
`git pull` does not touch it.

## `foran setup` modes

| Command | Behaviour |
|---|---|
| `foran setup` | Create a config, or review/keep an existing one |
| `foran setup --check` | Report only; never writes |
| `foran setup --reset` | Overwrite an existing `config.toml` (a timestamped backup is made) |
| `foran setup --yes --install-dir ...` | Non-interactive create/update |

## Not covered

- FORAN installation and licensing
- AutoCAD `accoreconsole.exe` (DWG conversion)
- `gmsh` (optional BREP generation)
- GUI coordinates: the defaults are calibrated for 1920x1080 at 150% scaling;
  other displays may need recalibration (`references/portability.md`)
