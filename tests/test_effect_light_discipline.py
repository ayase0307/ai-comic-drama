"""P1-8：特效光源句紀律——source_en 寫身體部位會擴散（11-03 #18），compile note 提醒改寫。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import compile_layer2_to_h3 as compiler  # noqa: E402


def sentence(source_en, notes):
    return compiler.effect_reference_sentence(
        "<Picture 2>", {"id": "B-firebird", "name_en": "the firebird", "desc_en": "the firebird",
                        "is_light": True, "source_en": source_en}, notes=notes)


class EffectLightBodyTests(unittest.TestCase):
    def test_body_part_source_adds_note(self):
        notes: list = []
        sentence("from his chest", notes)
        self.assertTrue(any("身體部位" in n and "chest" in n for n in notes), notes)

    def test_chinese_body_part_adds_note(self):
        notes: list = []
        sentence("從胸口發出", notes)
        self.assertTrue(any("身體部位" in n for n in notes), notes)

    def test_effect_itself_source_is_silent(self):
        notes: list = []
        out = sentence("the light curtain itself, high above", notes)
        self.assertEqual(notes, [])
        self.assertIn("the light curtain itself", out)

    def test_missing_source_keeps_original_note(self):
        notes: list = []
        compiler.effect_reference_sentence(
            "<Picture 2>", {"id": "B-firebird", "is_light": True, "source_en": ""}, notes=notes)
        self.assertTrue(any("特效缺光源位置" in n for n in notes), notes)


if __name__ == "__main__":
    unittest.main()
