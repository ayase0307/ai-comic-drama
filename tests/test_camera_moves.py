import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import camera_moves  # noqa: E402


class CameraMovesTests(unittest.TestCase):
    def test_alias_lookup(self):
        self.assertEqual(camera_moves.find_preset("子彈時間"), "bullet_time")
        self.assertEqual(camera_moves.find_preset("Dutch Angle"), "dutch_canted")
        self.assertEqual(camera_moves.find_preset("nope"), "")

    def test_expand_fills_slots(self):
        clause, warn = camera_moves.expand_preset("high_angle_tilt_down", {"target": "the sword"})
        self.assertIn("the sword", clause)
        self.assertEqual(warn, [])

    def test_missing_slot_raises(self):
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("bullet_time", {})

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("zzz")

    def test_experimental_warns(self):
        camera_moves.PRESETS["_tmp_exp"] = {"aliases": [], "slots": [], "status": "experimental",
                                             "strong": False, "clause": "x", "note": "n"}
        try:
            _, warn = camera_moves.expand_preset("_tmp_exp")
            self.assertTrue(warn)
        finally:
            del camera_moves.PRESETS["_tmp_exp"]

    def test_every_preset_formats(self):
        for pid, spec in camera_moves.PRESETS.items():
            camera_moves.expand_preset(pid, {k: "X" for k in spec["slots"]})


if __name__ == "__main__":
    unittest.main()
