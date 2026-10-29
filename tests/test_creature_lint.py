"""#97 #101 #121 生物外觀檢查。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import creature_lint as cl  # noqa: E402
import creature_color_qa  # noqa: E402


class CreatureLintTests(unittest.TestCase):
    def test_worm_with_snake_actions_warns(self):
        w = cl.lint_creature_text("CREATURE-py", "a giant earthworm, toothless round mouth",
                                  ["its pink tongue flicks and it hisses"])
        self.assertTrue(any("#97" in x for x in w))

    def test_snake_noun_with_toothless_warns(self):
        w = cl.lint_creature_text("CREATURE-py", "a giant serpent, toothless", [])
        self.assertEqual(len(w), 1)

    def test_clean_creature_no_warning(self):
        self.assertEqual(cl.lint_creature_text("C", "a giant earthworm with segmented pale yellow body",
                                               ["the body rears up"]), [])

    def test_retention_defers_head_to_text(self):
        t = cl.head_retention_clause("toothless round mouth with fleshy folds", 3)
        self.assertIn("follow the written description", t)
        self.assertNotIn("head features from", t)
        self.assertIn("head features from <Picture 3>", cl.head_retention_clause("a tall bird", 3))

    def test_hsv_compare_splits_hue_and_sat(self):
        ref = cl.hsv_median([(230, 215, 150)] * 5)
        warm = cl.hsv_median([(240, 170, 90)] * 5)
        r = cl.compare_hsv(ref, warm)
        self.assertFalse(r["ok"])
        self.assertFalse(r["hue_ok"])
        self.assertTrue(cl.compare_hsv(ref, ref)["ok"])

    def test_color_qa_cli(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.png", Path(d) / "b.png"
            Image.new("RGB", (32, 32), (230, 215, 150)).save(a)
            Image.new("RGB", (32, 32), (240, 140, 60)).save(b)
            self.assertEqual(creature_color_qa.main(["--ref", str(a), "--frame", str(a)]), 0)
            self.assertEqual(creature_color_qa.main(["--ref", str(a), "--frame", str(b)]), 1)


if __name__ == "__main__":
    unittest.main()
