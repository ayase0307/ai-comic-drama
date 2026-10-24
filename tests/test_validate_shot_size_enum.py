import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import validate_storyboard as vs


class ShotSizeEnumTest(unittest.TestCase):
    def _errors(self, size):
        data = {"metadata": {"lighting_lock_line": "x", "target_duration": 3}, "shots": [
            {"shot_id": "SH01", "duration": 3, "camera_optics": {"shot_size": size}}]}
        return [e for e in vs.validate_storyboard_data(data).get("errors", []) if "shot_size" in e]

    def test_ws_and_ots_rejected_with_hint(self):
        self.assertIn("LS", self._errors("WS")[0])
        self.assertIn("OTS_MS", self._errors("OTS")[0])

    def test_valid_size_passes(self):
        self.assertEqual(self._errors("OTS_CU"), [])


if __name__ == "__main__":
    unittest.main()
