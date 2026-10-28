import csv, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import foran_offsets as O


class TestExport(unittest.TestCase):
    def test_export_rectangular(self):
        frames = {}
        for i, x in enumerate((0.0, 50.0, 100.0)):
            frames[i] = {"x": x, "z": {0.001: 10.0, 5.0: 10.0, 10.0: 10.0, 15.0: 0.0}}
        data = {"frames": frames, "lpp": 100.0, "breadth": 20.0}
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "out" / "sample"
            res = O.export_tables(data, prefix, 10.0, make_xlsx=False,
                                  stations=3)
            self.assertTrue(Path(res["table_csv"]).is_file())
            self.assertTrue(Path(res["area_csv"]).is_file())
            self.assertAlmostEqual(res["volume"], 20000.0, places=6)
            self.assertEqual(res["rows"], 3)
            with open(res["table_csv"], encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(rows[0][0], "站号")
            self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
