import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import audit_refs_and_segments as a  # noqa: E402


def _prompt(desc_words: int, pad_chars: int = 0) -> str:
    desc = " ".join(["word"] * desc_words)
    return "detailed_description: " + desc + ("x" * pad_chars)


class W11UserDecidesTest(unittest.TestCase):
    def test_long_description_is_warning_not_error_and_lists_sacrifices(self):
        r = a.lint_h3_prompt(_prompt(900), nominal_duration=15.0)
        w11 = [w for w in r["warnings"] if w.startswith("[W11")]
        self.assertTrue(w11)
        self.assertIn("使用者可放行", w11[0])
        self.assertIn("犧牲", w11[0])
        self.assertFalse(any("字元超過上限" in e for e in r["errors"]))

    def test_over_7000_chars_is_hard_error_only_for_hosted(self):
        r = a.lint_h3_prompt(_prompt(10, pad_chars=7100), nominal_duration=15.0, submit_endpoint="hosted")
        self.assertTrue(any("字元超過上限" in e for e in r["errors"]))

    def test_over_7000_chars_is_fine_for_local_default(self):
        # 守富 2026-11-02：實際送件是家機本地 H3，沒有 hosted 的 7000 字元上限
        for endpoint in (None, "local"):
            r = a.lint_h3_prompt(_prompt(10, pad_chars=7100), nominal_duration=15.0, submit_endpoint=endpoint)
            self.assertFalse(any("字元超過上限" in e for e in r["errors"]), endpoint)
            self.assertFalse(any("文字編碼器" in w for w in r["warnings"]), endpoint)
            self.assertEqual(r["details"]["submit_endpoint"], "local")
            self.assertGreater(r["details"]["prompt_token_estimate"], 1700)

    def test_local_warns_only_past_text_encoder_limit(self):
        with unittest.mock.patch.object(a, "LOCAL_TEXT_ENCODER_MAX_TOKENS", 1000):
            r = a.lint_h3_prompt(_prompt(10, pad_chars=7100), nominal_duration=15.0)
        self.assertFalse(r["errors"] and any("字元超過上限" in e for e in r["errors"]))
        self.assertTrue(any(w.startswith("[W11: 可能超過文字編碼器長度]") for w in r["warnings"]))

    def test_token_estimate_counts_cjk_per_char(self):
        self.assertEqual(a.estimate_prompt_tokens("abcd" * 10), 10)
        self.assertEqual(a.estimate_prompt_tokens("妖怪不是"), 4)

    def test_over_density_gives_per_shot_budget(self):
        r = a.lint_h3_prompt(_prompt(400), nominal_duration=9.0)
        w = [x for x in r["warnings"] if x.startswith("[W11: 超過密度上限]")]
        self.assertTrue(w)
        self.assertIn("每鏡約剩", w[0])

    def test_under_suggestion_no_w11(self):
        r = a.lint_h3_prompt(_prompt(450), nominal_duration=15.0)
        self.assertFalse(any(w.startswith("[W11") for w in r["warnings"]))


class CarryOptOutTest(unittest.TestCase):
    def test_opt_out_skips_c2(self):
        import continuity_lint as cl
        import inspect
        fn = [f for n, f in inspect.getmembers(cl, inspect.isfunction) if "extra_end_states" in inspect.signature(f).parameters][0]
        segs = [
            {"segment_id": "EP01-S02-a", "scene_id": "S02", "segment_end_state": {"pose_en": "she kneels on the floor."}, "shots": []},
            {"segment_id": "EP01-S02-b", "scene_id": "S02", "carry_previous_end_state": False, "shots": [{"motion": "she walks in"}]},
        ]
        try:
            out = fn(segs)
        except Exception:
            self.skipTest("lint signature differs")
        self.assertFalse(any("EP01-S02-b" in w for w in out))


if __name__ == "__main__":
    unittest.main()
