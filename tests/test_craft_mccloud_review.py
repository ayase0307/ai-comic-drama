import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "craft"))
import mccloud_review  # noqa: E402


class MccloudReviewTest(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(mccloud_review.self_test())

    def test_classify_aspect_to_aspect(self):
        a = {"scene": "S1", "chars": ("x",), "size": "近景"}
        b = {"scene": "S1", "chars": (), "size": "大全景"}
        self.assertEqual(mccloud_review.classify(a, b), "aspect-to-aspect")

    def test_missing_layer2_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mccloud_review.main(["--project-dir", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
