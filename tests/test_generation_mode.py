"""P1-1：段級 generation_mode（t2v/i2v/fl2v/r2v，導演大師對照）。

本輪範圍：資料契約與門禁——schema 欄位、validate 的枚舉／幀來源檢查、
compile 對非 r2v fail closed（Base 三字段編譯尚未實作，不靜默產出錯誤結構）。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

import compile_layer2_to_h3 as compiler  # noqa: E402
from scripts.storyboard import validate_storyboard as vs  # noqa: E402


class GenerationModeValidateTests(unittest.TestCase):
    def test_unknown_mode_is_error(self):
        errors, _ = vs.generation_mode_checks({"generation_mode": "turbo"}, [])
        self.assertTrue(any("enum 錯誤" in e for e in errors), errors)

    def test_default_is_r2v_and_silent(self):
        errors, warnings = vs.generation_mode_checks({}, [])
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_i2v_requires_first_shot_sketch(self):
        shots = [{"shot_id": "A"}, {"shot_id": "B", "sketch_file": "sketch/b.png"}]
        errors, warnings = vs.generation_mode_checks({"generation_mode": "i2v"}, shots)
        self.assertTrue(any("G2 幀來源缺失" in e and "第 1 鏡" in e for e in errors), errors)
        self.assertTrue(any("W:G2" in w for w in warnings), warnings)

    def test_i2v_with_first_sketch_only_warns(self):
        shots = [{"shot_id": "A", "sketch_file": "sketch/a.png"}]
        errors, warnings = vs.generation_mode_checks({"generation_mode": "i2v"}, shots)
        self.assertEqual(errors, [])
        self.assertTrue(any("W:G2" in w for w in warnings), warnings)

    def test_fl2v_requires_last_shot_sketch(self):
        shots = [{"shot_id": "A", "sketch_file": "sketch/a.png"}, {"shot_id": "B"}]
        errors, _ = vs.generation_mode_checks({"generation_mode": "fl2v"}, shots)
        self.assertTrue(any("G2 幀來源缺失" in e and "末鏡" in e for e in errors), errors)

    def test_fl2v_single_shot_with_sketch_passes_structure(self):
        shots = [{"shot_id": "A", "sketch_file": "sketch/a.png"}]
        errors, _ = vs.generation_mode_checks({"generation_mode": "fl2v"}, shots)
        self.assertEqual([e for e in errors if "幀來源" in e], [])

    def test_t2v_with_characters_warns(self):
        shots = [{"shot_id": "A", "character_ids": ["C-A"]}]
        _, warnings = vs.generation_mode_checks({"generation_mode": "t2v"}, shots)
        self.assertTrue(any("W:G1" in w for w in warnings), warnings)

    def test_t2v_empty_is_silent(self):
        errors, warnings = vs.generation_mode_checks({"generation_mode": "t2v"},
                                                     [{"shot_id": "A", "character_ids": []}])
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [w for w in warnings if "W:G2" in w])


class GenerationModeCompileTests(unittest.TestCase):
    def test_non_r2v_fails_closed_before_heavy_work(self):
        with self.assertRaises(ValueError) as ctx:
            compiler.compile_segment_h3(
                {"segment_id": "EP01-S01-a", "metadata": {"generation_mode": "i2v"}},
                registry=None)
        self.assertIn("尚未實作", str(ctx.exception))
        self.assertIn("i2v", str(ctx.exception))

    def test_unknown_mode_fails_with_enum_list(self):
        with self.assertRaises(ValueError) as ctx:
            compiler.compile_segment_h3(
                {"segment_id": "EP01-S01-a", "metadata": {"generation_mode": "turbo"}},
                registry=None)
        self.assertIn("generation_mode", str(ctx.exception))

    def test_schema_declares_generation_mode(self):
        schema = json.loads((ROOT / "references/storyboard/templates/layer2-storyboard.schema.json")
                            .read_text(encoding="utf-8"))
        prop = schema["properties"]["metadata"]["properties"]["generation_mode"]
        self.assertEqual(prop["enum"], ["t2v", "i2v", "fl2v", "r2v"])


if __name__ == "__main__":
    unittest.main()
