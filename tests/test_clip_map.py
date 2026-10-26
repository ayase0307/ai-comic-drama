import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "edit"))
import clip_map as C  # noqa: E402


class ClipMapTest(unittest.TestCase):
    def test_cuts_normalize_and_apply(self):
        nc = C.normalize_cuts([[3, 4], [1, 2], [1.5, 2.5], [9, 12]], 10)
        self.assertEqual(nc, [(1.0, 2.5), (3.0, 4.0), (9.0, 10.0)])
        self.assertEqual(C.apply_cuts(5, nc), 2.5)
        self.assertEqual(C.apply_cuts(2, nc), 1.0)

    def test_cumulative_start_and_validate(self):
        a = C.build_clip("S1", frames=240, cuts=[[1, 2]])
        b = C.build_clip("S2", frames=120)
        cm = C.build_clip_map([a, b])
        self.assertEqual(cm["segments"][1]["start"], 9.0)
        self.assertEqual(cm["total"], 14.0)
        self.assertEqual(C.validate(cm), [])
        cm["segments"][1]["start"] = 10
        self.assertTrue(C.validate(cm))

    def test_time_mapping_with_ramp_and_cut(self):
        tm = [{"src": [0, 4], "out": [0, 2], "speed": 2}, {"src": [4, 6], "out": [2, 4], "speed": 1}]
        a = C.build_clip("S1", frames=96, time_map=tm, cuts=[[1, 2]])
        b = C.build_clip("S2", frames=48)
        cm = C.build_clip_map([a, b])
        self.assertEqual(cm["segments"][0]["out_dur"], 3.0)
        self.assertEqual(C.to_episode_time(cm, "S1", 5), 2.0)
        self.assertEqual(C.to_episode_time(cm, "S2", 1), 4.0)

    def test_bad_frames(self):
        with self.assertRaises(ValueError):
            C.build_clip("S", frames=0)


if __name__ == "__main__":
    unittest.main()
