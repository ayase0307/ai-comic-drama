import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import director_lint as d


def sh(sid, size="MS", loc="", side=None, spk="", intent=None, mv="static"):
    cam = {"shot_size": size, "movement": mv}
    if side:
        cam["screen_side"] = side
    return {"shot_id": sid, "location": loc, "camera_optics": cam,
            "dialogue_and_audio": {"dialogue": {"speaker": spk}} if spk else {}, "shot_intent": intent or {}}


class DirectorLint(unittest.TestCase):
    def test_new_location(self):
        out = d.lint_director([sh("A", loc="屋頂"), sh("B", "CU", loc="地下室")])
        self.assertTrue(any("新地點缺建立鏡" in x for x in out))
        self.assertFalse(d.lint_director([sh("A", loc="屋頂"), sh("B", "LS", loc="地下室")]))

    def test_axis(self):
        out = d.lint_director([sh("A", side="left", spk="沈"), sh("B", side="right", spk="沈")])
        self.assertTrue(any("越軸" in x for x in out))

    def test_reaction(self):
        tw = {"story_beat": "揭穿真相"}
        self.assertTrue(any("反應鏡" in x for x in d.lint_director([sh("A", intent=tw), sh("B", "LS")])))
        self.assertFalse(d.lint_director([sh("A", intent=tw), sh("B", "CU")]))

    def test_eyeline(self):
        out = d.lint_director([sh("A", intent={"audience": "他看向遠方"})])
        self.assertTrue(any("視線匹配" in x for x in out))

    def test_seam(self):
        self.assertTrue(d.lint_segment_seam(sh("A"), sh("B")))
        self.assertFalse(d.lint_segment_seam(sh("A"), sh("B", "LS")))


if __name__ == "__main__":
    unittest.main()
