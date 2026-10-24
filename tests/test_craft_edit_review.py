import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "craft"))
import edit_review  # noqa: E402


class EditReviewTest(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(edit_review.self_test())

    def test_missing_inputs_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(edit_review.main(["--project-dir", tmp]), 0)
            report = (Path(tmp) / "review" / "craft" / "stage-7-edit-ep01.md").read_text(encoding="utf-8")
            self.assertIn("找不到 timeline-plan-ep01.csv", report)

    def test_fatigue(self):
        shots = [{"shot": f"S{i}", "dur": 1.0} for i in range(25)]
        self.assertEqual(edit_review.check_fatigue(shots)[0], "⚠️")

    def test_chars_ignores_punctuation(self):
        self.assertEqual(edit_review.chars("你好，世界！"), 4)

    def test_lens_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(edit_review.main(["--project-dir", tmp, "--lens", "murch-cut"]), 0)
            report = (Path(tmp) / "review" / "craft" / "stage-7-edit-ep01.md").read_text(encoding="utf-8")
            self.assertIn("murch-cut", report)
            self.assertNotIn("hamilton-action", report)


if __name__ == "__main__":
    unittest.main()
