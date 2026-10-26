import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import camera_moves as cm

NEW = ["push_in","pull_back","pan","truck","follow","crane_up","crane_down","low_angle","static_hold","orbit",
       "rise_orbit","steadicam","macro_push","rack_focus","aerial_reveal","whip_pan","crash_zoom","fpv","pov","foreground_wipe"]

class T(unittest.TestCase):
    def test_all_expand(self):
        for pid in NEW:
            spec = cm.PRESETS[pid]
            self.assertIn(spec["status"], ("pass","partial","fail"))
            slots = {k: "X" for k in spec["slots"]}
            clause, warns = cm.expand_preset(pid, slots)
            self.assertNotIn("{", clause)
            self.assertEqual(any("第 4 輪" in w for w in warns), spec["status"]!="pass", pid)
            with self.assertRaises(ValueError):
                if spec["slots"]:
                    cm.expand_preset(pid, {})
                else:
                    raise ValueError
    def test_orbit_avoids_word(self):
        c, _ = cm.expand_preset("orbit", {"subject": "A"})
        self.assertNotIn("orbit", c.lower())
        self.assertIn("trucks", c)
    def test_alias(self):
        self.assertEqual(cm.find_preset("甩鏡"), "whip_pan")
