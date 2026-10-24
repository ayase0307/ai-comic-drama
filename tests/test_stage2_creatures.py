import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_stage_review as review  # noqa: E402
import project_state as ps  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")


class Stage2CreatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)
        for d in ("images", "adapt", "review"):
            (self.p / d).mkdir()
        (self.p / "adapt" / "character-bible.md").write_text("# 角色\n", encoding="utf-8")
        (self.p / "assets.md").write_text(
            "## 生物\n\n### CREATURE-kaibuli\u3000凱布利（異獸）\n"
            "- **設定圖**：`images/creature-kaibuli.png`\n\n## 場景\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_creature_from_assets_md_and_orphan_png_get_cards(self):
        (self.p / "images" / "creature-kaibuli.png").write_bytes(PNG)
        (self.p / "images" / "creature-wolf.png").write_bytes(PNG)
        passed, errors, page = review.build_stage_2(self.p, ps.load_state(self.p))
        self.assertIn("生物／異獸：凱布利", page)
        self.assertIn("images/creature-kaibuli.png", page)
        self.assertIn("CREATURE-wolf", page)
        self.assertEqual(page.count("creature-card"), 2)

    def test_missing_creature_image_blocks(self):
        passed, errors, page = review.build_stage_2(self.p, ps.load_state(self.p))
        self.assertFalse(passed)
        self.assertTrue(any("凱布利" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
