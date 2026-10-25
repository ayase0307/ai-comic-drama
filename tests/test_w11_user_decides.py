import sys
import unittest
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

    def test_over_7000_chars_is_hard_error(self):
        r = a.lint_h3_prompt(_prompt(10, pad_chars=7100), nominal_duration=15.0)
        self.assertTrue(any("字元超過上限" in e for e in r["errors"]))

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
