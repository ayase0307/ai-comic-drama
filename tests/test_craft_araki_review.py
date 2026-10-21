import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "craft"))
import araki_review  # noqa: E402


class ArakiReviewTest(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(araki_review.self_test())

    def test_unannotated_handoff_asks_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "handoff-ep01.json").write_text('{"episodes":[{"episode_id":"EP01","scenes":[{},{}]}]}', encoding="utf-8")
            text = araki_review.run(p, 3, "EP01").read_text(encoding="utf-8")
            self.assertIn("protagonist_charge", text)

    def test_missing_inputs_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(araki_review.main(["--project-dir", tmp, "--stage", "2"]), 0)
            self.assertEqual(araki_review.main(["--project-dir", tmp, "--stage", "3"]), 0)


if __name__ == "__main__":
    unittest.main()
