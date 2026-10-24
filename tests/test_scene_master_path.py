import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_stage_review import scene_master_image


class SceneMasterPathTest(unittest.TestCase):
    def test_falls_back_to_exported_master_name(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "images").mkdir()
            (Path(d) / "images" / "scene-cellar-master.png").write_bytes(b"x")
            self.assertEqual(scene_master_image(Path(d), {}, "S-cellar"), "images/scene-cellar-master.png")

    def test_prefers_default_and_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "images").mkdir()
            for n in ("S-cellar.png", "scene-cellar-master.png"):
                (Path(d) / "images" / n).write_bytes(b"x")
            self.assertEqual(scene_master_image(Path(d), {}, "S-cellar"), "images/S-cellar.png")
            self.assertEqual(scene_master_image(Path(d), {"reference_image": "a.png"}, "S-cellar"), "a.png")


if __name__ == "__main__":
    unittest.main()
