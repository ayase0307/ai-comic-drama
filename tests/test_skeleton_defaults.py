import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import handoff_to_skeleton as h


class SkeletonDefaults(unittest.TestCase):
    def test_beats_merge(self):
        items = h.merge_beats(["a", "b", "c"])
        self.assertEqual([i["duration"] for i in items], [5.0, 2.5])
        self.assertEqual(items[0]["text"], "a；b")

    def test_cjk_ids_unique_not_item(self):
        a, b = h.make_id("C", "沈商山", 0), h.make_id("C", "蛙仙", 1)
        self.assertNotEqual(a, b)
        self.assertNotIn("item", a)
        self.assertEqual(a, h.make_id("C", "沈商山", 5))

    def test_beat_shot_defaults(self):
        scene = {"characters": ["沈商山", "蛙仙"], "props": []}
        cm = {"沈商山": "C-a", "蛙仙": "C-b"}
        sh = h.make_shot({"kind": "beat", "text": "沈商山退後", "duration": 2.5}, "X-SH01", 0, 2.5, scene, cm)
        self.assertEqual(sh["character_ids"], ["C-a"])
        self.assertFalse(sh["dialogue_and_audio"]["lips_closed_lock"])


if __name__ == "__main__":
    unittest.main()
