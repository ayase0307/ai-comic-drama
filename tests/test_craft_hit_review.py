import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "craft"))
import hit_review  # noqa: E402


class HitReviewTest(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(hit_review.self_test())

    def test_clean_episode_is_advisory_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            h = {"episodes": [{"episode_id": "EP01", "title": "舉報系統", "act_out_type": "revelation_twist",
                               "scenes": [{"scene_id": "S01", "estimated_duration_seconds": 20, "dramatic_turn": "反轉",
                                           "dialogue": [{"text": "你是誰？", "start": 1.0}]}]}]}
            (p / "handoff-ep01.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
            out = hit_review.run(p, 3, "EP01", None, None)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(out, p / "review" / "craft" / "stage-3-hit-ep01.md")
            self.assertNotIn("❌", text.split("## Agent 審查")[0])
            self.assertIn("## Agent 審查", text)

    def test_missing_inputs_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(hit_review.main(["--project-dir", tmp, "--stage", "3"]), 0)
            self.assertEqual(hit_review.main(["--project-dir", tmp, "--stage", "0"]), 0)


class CraftPanelTest(unittest.TestCase):
    def test_stage_review_shows_craft_reports_without_gating(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import build_stage_review as bsr
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            hint = bsr.craft_lens_panel(p, 0)  # 沒報告時列出可跑的 lens 指令，不再整塊消失
            self.assertIn("hit_review.py", hint)
            self.assertIn("還沒有 lens 報告", hint)
            self.assertEqual(bsr.craft_lens_panel(p, 5), "")  # 階段 5 沒有 lens
            (p / "review" / "craft").mkdir(parents=True)
            (p / "review" / "craft" / "stage-0-hit-ep01.md").write_text("# 測試報告\n\n內容ZZZ", encoding="utf-8")
            html_out = bsr.craft_lens_panel(p, 0)
            self.assertIn("不擋關", html_out)
            self.assertIn("ZZZ", html_out)
            self.assertIn("mckee_review.py", bsr.craft_lens_panel(p, 3))


if __name__ == "__main__":
    unittest.main()


class FirstLineTimestampTest(unittest.TestCase):
    def test_no_timestamp_is_info_not_pass(self):
        from craft import hit_review as hr
        ep = {"scenes": [{"estimated_duration_seconds": 30, "dialogue": [{"text": "你來了"}]}]}
        res = hr.review_stage3(ep)
        hook = [r for r in res if r[1] == "開場鉤子"][0]
        self.assertEqual(hook[0], "ℹ️")

    def test_timestamp_still_judged(self):
        from craft import hit_review as hr
        ep = {"scenes": [{"estimated_duration_seconds": 30, "dialogue": [{"text": "x", "start": 2.0}]}]}
        hook = [r for r in hr.review_stage3(ep) if r[1] == "開場鉤子"][0]
        self.assertEqual(hook[0], "✅")
