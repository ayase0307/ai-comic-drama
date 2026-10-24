import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import compile_layer2_to_h3 as c  # noqa: E402


class CompactFivePartTest(unittest.TestCase):
    def test_drops_optics_lead_and_trims_sound_keeps_light(self):
        five = {
            "camera": "50mm from one and a half metres at eye level, locked off for 2.5 s; she sits centre.",
            "motion": "First she lifts the cup.",
            "performance": "A calm face.",
            "light": "South window light on her left cheek.",
            "sound": "A chair creaks softly at about 0.4 s near her; a bird calls outside.",
        }
        out = c.compact_five_part(five)
        self.assertTrue(out["camera"].startswith("Locked off for 2.5 s"))
        self.assertEqual(out["light"], five["light"])
        self.assertEqual(out["motion"], five["motion"])
        self.assertNotIn("bird", out["sound"])
        self.assertIn("0.4 s", out["sound"])

    def test_thin_sound_kept_whole(self):
        five = {"camera": "x", "motion": "m", "performance": "p", "light": "l",
                "sound": "Silence; a soft exhale at about 3.0 s."}
        self.assertEqual(c.compact_five_part(five)["sound"], five["sound"])


if __name__ == "__main__":
    unittest.main()
