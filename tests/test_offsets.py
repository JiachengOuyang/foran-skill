import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import foran_offsets as O


class TestHydrostatics(unittest.TestCase):
    def test_rectangular_box(self):
        # 100 m long, 20 m wide box, 10 m draught -> Cb = 1.0
        frames = {}
        for i, x in enumerate((0.0, 50.0, 100.0)):
            frames[i] = {"x": x, "z": {0.001: 10.0, 5.0: 10.0, 10.0: 10.0, 15.0: 0.0}}
        rows = O.hydrostatics({"frames": frames, "lpp": 100.0, "breadth": 20.0},
                              [10.0])
        self.assertAlmostEqual(rows[0]["volume"], 20000.0, places=6)
        self.assertAlmostEqual(rows[0]["cb"], 1.0, places=6)
        self.assertAlmostEqual(rows[0]["lcb_ap"], 50.0, places=6)

    def test_seam_repair_uses_neighbour_station(self):
        frames = {}
        for i, x in enumerate((0.0, 50.0, 100.0)):
            zm = {0.001: 10.0, 1.0: 10.0, 2.0: 10.0}
            if i == 1:
                zm[1.0] = 0.0          # simulated loftbook seam zero
            frames[i] = {"x": x, "z": zm}
        order = O.repair_frames(frames)
        self.assertEqual(order, [0, 1, 2])
        self.assertAlmostEqual(frames[1]["z"][1.0], 10.0, places=6)


if __name__ == "__main__":
    unittest.main()
