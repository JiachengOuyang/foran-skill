import sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ezdxf
import foran_dxf as DX


class TestFrame(unittest.TestCase):
    def test_frame_a4(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.dxf"
            out = Path(td) / "out.dxf"
            doc = ezdxf.new("R2010")
            doc.modelspace().add_line((0, 0), (1000, 500))
            doc.saveas(src)
            a = SimpleNamespace(
                inp=str(src), out=str(out), sheet="A4", portrait=False,
                fit=True, units_per_mm=1.0, scale=None, scale_den=None,
                template=None, template_units_per_mm=1.0, template_margin=10.0,
                template_area="auto", project="P", title="T",
                drawing_no="D-1", scale_text="1:100", designer="",
                checker="", approver="", company="", date="2026-01-01")
            self.assertEqual(DX.cmd_frame(a), 0)
            self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
