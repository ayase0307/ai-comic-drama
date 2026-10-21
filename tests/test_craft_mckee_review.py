import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "craft"))
import mckee_review  # noqa: E402


class MckeeReviewTest(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(mckee_review.self_test())

    def test_default_output_name_is_script_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "handoff-ep02.json").write_text('{"episodes":[{"episode_id":"EP02","scenes":[{"scene_id":"A"}]}]}', encoding="utf-8")
            out = mckee_review.run(p, "EP02")
            self.assertEqual(out.name, "stage-3-mckee-script-review-ep02.md")
            self.assertIn("請 Agent 先逐場標註", out.read_text(encoding="utf-8"))

    def test_missing_input_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mckee_review.main(["--project-dir", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
