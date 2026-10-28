import io, json, sqlite3, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import foran_db as D


def make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript('''
        create table FORAN_VERSION (VERSION text);
        insert into FORAN_VERSION values ('V80R3.0');
        create table DSG_HYD_CALC_DATA
            (OID integer, DESIGN_DRAUGHT real, LENGTH_BETWEEN_PP real,
             DESIGN_BREADTH real, WATER_DENSITY real);
        insert into DSG_HYD_CALC_DATA values (1, 10.0, 100.0, 20.0, 1.025);
        create table DSG_HYD_RESULTS
            (OID integer, HYD_DATA_OID integer, HYD_RESULT_TYPE integer, AFT_DRAFT real,
             MOULDED_VOLUME real, BLOCK_COEFF real, PRISMATIC_COEFF real,
             MIDSHIP_COEFF real, LENGTH_AT_WPLANE real, WATERLINE_COEFF real,
             XCB real, KM_TRANSVERSAL real, WETTED_SRF_AREA real,
             DISPLACEMENT real);
        insert into DSG_HYD_RESULTS values
            (1, 1, 1, 10.0, 20000.0, 1.0, 1.0, 1.0, 100.0, 1.0, 50.0, 5.0, 1000.0, 20500.0);
        create table DSG_GA_TREE (OID integer);
    ''')
    con.commit(); con.close()


class TestDb(unittest.TestCase):
    def test_check_and_hydro(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            path = Path(td) / "sample.db"
            make_db(path)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = D.cmd_check(SimpleNamespace(db=str(path), json=True))
            self.assertEqual(rc, 0)
            rep = json.loads(buf.getvalue())
            self.assertTrue(rep["ok"])
            self.assertEqual(rep["foran_version"]["VERSION"], "V80R3.0")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = D.cmd_hydro(SimpleNamespace(db=str(path), json=True))
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertAlmostEqual(out["computed"]["Cb_Lpp"], 1.0, places=6)
            self.assertAlmostEqual(out["computed"]["displacement_from_volume"],
                                   20500.0, places=6)
            self.assertTrue(out["checks"]["stored_Cb_Lpp_agrees"])


if __name__ == "__main__":
    unittest.main()
