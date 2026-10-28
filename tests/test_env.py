import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CLI = HERE / "scripts" / "foran_cli.py"


class TestConfig(unittest.TestCase):
    def test_config_toml_is_read(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.toml"
            install = Path(td) / "foran"
            cfg.write_text(
                '[foran]\ninstall_dir = "%s"\nprojects_dir = "%s"\n'
                % (install.as_posix(), (Path(td) / "projects").as_posix()),
                encoding="utf-8")
            env = dict(os.environ, FORAN_SKILL_CONFIG=str(cfg))
            out = subprocess.check_output(
                [sys.executable, str(CLI), "env", "paths", "--json"],
                env=env, text=True, encoding="utf-8")
            data = json.loads(out)
            self.assertEqual(Path(data["install_dir"]), install.resolve())
            self.assertEqual(Path(data["projects_dir"]),
                             (Path(td) / "projects").resolve())

    def test_env_overrides_config(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.toml"
            cfg.write_text('[foran]\ninstall_dir = "%s"\n' % (Path(td) / "a").as_posix(),
                           encoding="utf-8")
            override = (Path(td) / "b").resolve()
            env = dict(os.environ, FORAN_SKILL_CONFIG=str(cfg),
                       FORAN_SKILL_INSTALL_DIR=str(override))
            out = subprocess.check_output(
                [sys.executable, str(CLI), "env", "paths", "--json"],
                env=env, text=True, encoding="utf-8")
            self.assertEqual(Path(json.loads(out)["install_dir"]), override)


if __name__ == "__main__":
    unittest.main()
