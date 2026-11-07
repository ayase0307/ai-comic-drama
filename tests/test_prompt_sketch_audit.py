"""Eian 文章對照（2026-11-05）：送件前「提示詞 ↔ 構圖圖」逐句核對清單（prompt_sketch_audit.py）。

- 有 sketch_file／panels 命名對應的鏡：列出構圖圖路徑＋八項核對清單。
- 找不到構圖圖的鏡：標 ❌ 並進 problems。
- generation_mode=fl2v 的段：附 frame_pair_qa 疊圖檢查提醒。
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.storyboard import prompt_sketch_audit as psa  # noqa: E402


def _layer2(seg_id, mode="r2v", shots=None):
    return {
        "segment_id": seg_id,
        "metadata": {"generation_mode": mode},
        "shots": shots or [],
    }


class PromptSketchAuditTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        (self.root / "layer2").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_png(self, path):
        from PIL import Image
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4), "white").save(path)

    def test_lists_sketch_and_checklist(self):
        panel = self.root / "panels" / "panel-01-SH01.png"
        self._write_png(panel)
        data = _layer2("EP01-S01-a", shots=[{"shot_id": "SH01", "camera_optics": {"shot_size": "MS"}}])
        (self.root / "layer2" / "layer2-EP01-S01-a.json").write_text(
            __import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
        md, problems = psa.build_audit(self.root)
        self.assertIn("EP01-S01-a", md)
        self.assertIn("panel-01-SH01.png", md)
        self.assertIn("✅", md)
        for name, _ in psa.CHECK_ITEMS:
            self.assertIn(name, md)
        self.assertEqual(problems, [])

    def test_missing_sketch_flags_problem(self):
        data = _layer2("EP01-S01-b", shots=[{"shot_id": "SH01", "camera_optics": {"shot_size": "CU"}}])
        (self.root / "layer2" / "layer2-EP01-S01-b.json").write_text(
            __import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
        md, problems = psa.build_audit(self.root)
        self.assertIn("❌ 找不到構圖圖", md)
        self.assertEqual(len(problems), 1)
        self.assertIn("EP01-S01-b", problems[0])

    def test_fl2v_segment_gets_pair_qa_note(self):
        panel = self.root / "panels" / "panel-01-SH01.png"
        self._write_png(panel)
        data = _layer2("EP01-S02-a", mode="fl2v",
                       shots=[{"shot_id": "SH01", "camera_optics": {"shot_size": "MS"}}])
        (self.root / "layer2" / "layer2-EP01-S02-a.json").write_text(
            __import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
        md, _ = psa.build_audit(self.root)
        self.assertIn("frame_pair_qa", md)
        self.assertIn("generation_mode=fl2v", md)
        # fl2v 段追加幀面檢查（Eian 2026-11-05）
        for name, _ in psa.FL2V_ITEMS:
            self.assertIn(name, md)
        # r2v 段不應出現 fl2v 專屬項
        data_r2v = _layer2("EP01-S03-a",
                           shots=[{"shot_id": "SH01", "camera_optics": {"shot_size": "MS"}}])
        (self.root / "layer2" / "layer2-EP01-S03-a.json").write_text(
            __import__("json").dumps(data_r2v, ensure_ascii=False), encoding="utf-8")
        md2, _ = psa.build_audit(self.root, episode="EP01")
        self.assertIn("EP01-S03-a", md2)

    def test_position_item_has_golden_ratio_hint(self):
        data = _layer2("EP01-S04-a",
                       shots=[{"shot_id": "SH01", "camera_optics": {"shot_size": "MS"}}])
        (self.root / "layer2" / "layer2-EP01-S04-a.json").write_text(
            __import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
        md, _ = psa.build_audit(self.root)
        self.assertIn("38%", md)
        self.assertIn("62%", md)

    def test_sketch_file_field_takes_priority(self):
        custom = self.root / "images" / "custom-shot.png"
        self._write_png(custom)
        data = _layer2("EP01-S03-a",
                       shots=[{"shot_id": "SH01", "sketch_file": "images/custom-shot.png",
                               "camera_optics": {"shot_size": "MS"}}])
        (self.root / "layer2" / "layer2-EP01-S03-a.json").write_text(
            __import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
        md, problems = psa.build_audit(self.root)
        self.assertIn("custom-shot.png", md)
        self.assertEqual(problems, [])

    def test_no_layer2_files_returns_problem(self):
        md, problems = psa.build_audit(self.root)
        self.assertEqual(md, "")
        self.assertEqual(len(problems), 1)


if __name__ == "__main__":
    unittest.main()
