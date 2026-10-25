import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import move_lint


def shot(sid, preset=None, slots=None, dur=4, dlg=False, intent=None, movement="static"):
    cam = {"movement": movement}
    if preset:
        cam["move_preset"] = preset
        cam["move_slots"] = slots or {}
    return {"shot_id": sid, "duration": dur, "camera_optics": cam,
            "dialogue_and_audio": {"dialogue": "hi"} if dlg else {}, "shot_intent": intent or {}}


class MoveLint(unittest.TestCase):
    def test_too_many_strong(self):
        ss = [shot(f"S{i}", "top_down_rise") for i in range(3)]
        out = move_lint.lint_segment_moves(ss)
        self.assertTrue(any("同段多個強運鏡" in x for x in out))
        self.assertTrue(any("連續同運鏡" in x for x in out))

    def test_dialogue_and_short(self):
        out = move_lint.lint_segment_moves([shot("A", "top_down_rise", dur=2, dlg=True)])
        self.assertTrue(any("對白鏡用強運鏡" in x for x in out))
        self.assertTrue(any("子鏡過短" in x for x in out))

    def test_missing_slots_unknown(self):
        out = move_lint.lint_segment_moves([shot("A", "bullet_time"), shot("B", "nope")])
        self.assertTrue(any("缺漏" in x for x in out))
        self.assertTrue(any("未知" in x for x in out))

    def test_recommend(self):
        r = move_lint.recommend_move("主角意識到真相，震驚")
        self.assertEqual(r["primary"], "dolly_zoom")
        out = move_lint.lint_segment_moves([shot("A", intent={"audience": "觀眾感受孤立"})])
        self.assertTrue(any("aerial_pullback" in x for x in out))
        self.assertEqual(move_lint.recommend_move("閒聊"), {})

    def test_clean(self):
        self.assertEqual(move_lint.lint_segment_moves([shot("A", "dutch_canted")]), [])


if __name__ == "__main__":
    unittest.main()


class TestIntentRulesPr15a(unittest.TestCase):
    def test_new_keywords(self):
        for text, want in [("笑點，急推強調", "crash_zoom"), ("甩鏡轉場", "whip_pan"),
                           ("轉焦到後景的人", "rack_focus"), ("展現權力威脅", "low_angle"),
                           ("微距細節", "macro_push"), ("第一人稱驚嚇", "pov")]:
            self.assertEqual(move_lint.recommend_move(text).get("primary"), want, text)

    def test_old_rules_still_first(self):
        self.assertEqual(move_lint.recommend_move("震驚")["primary"], "dolly_zoom")
