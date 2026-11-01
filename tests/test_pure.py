# -*- coding: utf-8 -*-
"""Offline unit tests for the FORAN skill's pure functions.

Run:  python .claude/skills/foran/scripts/foran_tests.py
"""
from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import foran_cli  # noqa: E402
import foran_fga  # noqa: E402

try:
    import foran_deliver  # noqa: E402
except ModuleNotFoundError:  # course layer is not in this build
    foran_deliver = None
import foran_hydro  # noqa: E402
import foran_names  # noqa: E402
import foran_offsets  # noqa: E402


class TestForanNames(unittest.TestCase):
    def test_version_dot_is_sanitised(self):
        raw = "DEMO-001_型线模型_v1.0_20260101_USER.fsf"
        safe = foran_names.foran_safe_filename(raw)
        self.assertEqual(safe, "DEMO-001_型线模型_v1_0_20260101_USER.fsf")
        self.assertEqual(safe.count("."), 1)

    def test_stem_keeps_letters_digits_dash_underscore(self):
        self.assertEqual(
            foran_names.foran_safe_stem("A b/c.d-e_f"), "A_b_c_d-e_f")

    def test_extra_dots(self):
        self.assertTrue(foran_names.has_extra_dots("model_v1.0_work.fsf"))
        self.assertFalse(foran_names.has_extra_dots("model_v1_0_work.fsf"))
        self.assertFalse(foran_names.has_extra_dots("sample.db"))

    @unittest.skipIf(foran_deliver is None, "deliver is local-only")
    def test_deliver_package_name(self):
        p = {"no": "DEMO-001", "ver": "v1.0",
             "date": "20260101", "author": "USER"}
        raw = foran_deliver._fname(p, "型线模型", ".fsf")
        safe = foran_deliver._foran_safe(raw)
        self.assertIn("_v1_0_", safe)
        self.assertEqual(safe.count("."), 1)


class TestCliWarning(unittest.TestCase):
    def test_warns_once_for_dotted_fsf(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            foran_cli._warn_dotted_foran_names(
                ["model_v1.0.fsf", "model_v1.0.fsf", "good.fsf"])
        text = buf.getvalue()
        self.assertEqual(text.count("warning:"), 1)
        self.assertIn("model_v1_0.fsf", text)


class TestOffsets(unittest.TestCase):
    def test_parse_loftbook_and_hydrostatics(self):
        text = (
            "LENGTH BETWEEN PERPENDICULARS          100.000\n"
            "MOULDED BREADTH                         10.000\n"
            "MOULDED DRAUGHT                          5.000\n"
            "FRAME NO.   0   10\n"
            "DIST A.P.   0.000  100.000\n"
            "   0.000   5000   5000\n"
            "  10.000   5000   5000\n"
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "offsets.lis"
            p.write_text(text, encoding="utf-8")
            data = foran_offsets.parse_loftbook(p)
        self.assertAlmostEqual(data["lpp"], 100.0)
        self.assertAlmostEqual(data["breadth"], 10.0)
        rows = foran_offsets.hydrostatics(data, [5.0])
        self.assertAlmostEqual(rows[0]["volume"], 5000.0)
        self.assertAlmostEqual(rows[0]["cb"], 1.0)
        self.assertAlmostEqual(rows[0]["lcb_ap"], 50.0)
        self.assertAlmostEqual(rows[0]["cwp"], 1.0)

    def test_parse_expect(self):
        got = foran_offsets.parse_expect("9.83:42514:0.8293,10.27:44644")
        self.assertAlmostEqual(got[9.83][0], 42514.0)
        self.assertAlmostEqual(got[9.83][1], 0.8293)
        self.assertIsNone(got[10.27][1])


class TestHydroGeometry(unittest.TestCase):
    RECT = [(-5.0, 0.0), (5.0, 0.0), (5.0, 10.0), (-5.0, 10.0)]

    def test_clip_below(self):
        clipped = foran_hydro.clip_below(self.RECT, 5.0)
        area, mz = foran_hydro.area_moment_z(clipped)
        self.assertAlmostEqual(area, 50.0)
        self.assertAlmostEqual(mz, 125.0)

    def test_calc_at_draft_box(self):
        secs = [(0.0, self.RECT), (10.0, self.RECT)]
        out = foran_hydro.calc_at_draft(secs, 5.0, 10.0, 10.0, 1.025)
        self.assertAlmostEqual(out["volume"], 500.0)
        self.assertAlmostEqual(out["displacement"], 512.5)
        self.assertAlmostEqual(out["lcb"], 5.0)
        self.assertAlmostEqual(out["kb"], 2.5)
        self.assertAlmostEqual(out["cb"], 1.0)
        self.assertAlmostEqual(out["cm"], 1.0)
        self.assertAlmostEqual(out["cwp"], 1.0)


@unittest.skipIf(foran_deliver is None, "deliver is local-only")
class TestDeliverVerify(unittest.TestCase):
    def _make_pkg(self, td: str, dotted_fsf: bool = False):
        import hashlib
        import zipfile

        pkg = Path(td) / "PKG"
        pkg.mkdir()
        (pkg / "hello.txt").write_text("hello", encoding="utf-8")
        (pkg / "drawing.dwg").write_bytes(b"AC1032" + b"0" * 10)
        fsf = pkg / ("model_v1.0.fsf" if dotted_fsf else "model_v1_0.fsf")
        fsf.write_bytes(b"FSF")
        files = sorted(f for f in pkg.iterdir() if f.name != "SHA256SUMS.txt")
        (pkg / "SHA256SUMS.txt").write_text(
            "\n".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}"
                      for f in files) + "\n", encoding="utf-8")
        zp = pkg.parent / (pkg.name + ".zip")
        with zipfile.ZipFile(zp, "w") as zf:
            for f in sorted(pkg.iterdir()):
                zf.write(f, arcname=f"{pkg.name}/{f.name}")
        return pkg

    def test_good_package(self):
        with tempfile.TemporaryDirectory() as td:
            res = foran_deliver.verify_package(self._make_pkg(td))
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["errors"], [])

    def test_dotted_fsf_fails(self):
        with tempfile.TemporaryDirectory() as td:
            res = foran_deliver.verify_package(self._make_pkg(td, dotted_fsf=True))
        self.assertFalse(res["ok"])
        self.assertTrue(any("misparse" in e for e in res["errors"]))


class TestDbCopy(unittest.TestCase):
    def test_copy_from_outside_and_inside(self):
        import foran_db
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "ship.db"
            src.write_bytes(b"data")
            work = root / "work"
            dest = foran_db.copy_for_work(src, work)
            self.assertEqual(dest.name, "ship.db")
            self.assertEqual(dest.read_bytes(), b"data")
            self.assertNotEqual(dest.resolve(), src.resolve())
            # Source already inside the work folder: never copy onto itself.
            again = foran_db.copy_for_work(dest, work)
            self.assertNotEqual(again.resolve(), dest.resolve())
            self.assertTrue(again.name.startswith("ship_"))
            self.assertEqual(dest.read_bytes(), b"data")


class TestDoctor(unittest.TestCase):
    def test_db_report_good_and_missing(self):
        import foran_doctor
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "good.db"
            con = sqlite3.connect(db)
            con.execute("create table t (x int)")
            con.commit()
            con.close()
            good = foran_doctor._db_report(db)
            self.assertTrue(good["ok"], good)
            self.assertEqual(good["tables"], 1)
            missing = foran_doctor._db_report(Path(td) / "none.db")
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["error"], "not found")


class TestFgaDbHelpers(unittest.TestCase):
    def _db(self, td: str, sections: bool = True) -> Path:
        p = Path(td) / "test.db"
        con = sqlite3.connect(p)
        con.execute("create table DSG_SPC_TREE (OID int, NAME text, TYPE int)")
        con.executemany("insert into DSG_SPC_TREE values (?,?,?)",
                        [(128, "Ship", 1), (800, "HULL", 2),
                         (5200, "CARGO", 2), (5601, "SPC-0001", 7)])
        if sections:
            con.execute("create table DSG_SOLID_HULL_SECTIONS (X real, DATA blob)")
            con.executemany("insert into DSG_SOLID_HULL_SECTIONS values (?,null)",
                            [(-3.0,), (176.0,)])
        con.commit()
        con.close()
        return p

    def test_work_area_nodes(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._db(td)
            self.assertEqual(foran_fga._work_area_nodes(db),
                             {"Ship", "HULL", "CARGO"})

    def test_solid_sections_info(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._db(td)
            count, xmin, xmax = foran_fga._solid_sections_info(db)
            self.assertEqual(count, 2)
            self.assertAlmostEqual(xmin, -3.0)
            self.assertAlmostEqual(xmax, 176.0)

    def test_missing_sections_table(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._db(td, sections=False)
            self.assertIsNone(foran_fga._solid_sections_info(db))


if __name__ == "__main__":
    unittest.main()
