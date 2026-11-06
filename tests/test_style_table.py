"""P1-4：風格查表——style id → 影片風格錨逐字取表（assets/styles/styles.json），模型不得改寫。"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

import style_rules  # noqa: E402


class StyleTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = style_rules.load_style_table()

    def test_table_has_twelve_styles_with_anchor_and_negative(self):
        self.assertEqual(sorted(self.table, key=int), [str(i) for i in list(range(1, 12)) + [14]])
        for sid, entry in self.table.items():
            self.assertTrue(entry.get("anchor"), f"{sid} 缺 anchor")
            self.assertTrue(entry.get("negative"), f"{sid} 缺 negative")
            self.assertTrue(entry.get("name"), f"{sid} 缺 name")

    def test_anchors_match_styles_md_verbatim(self):
        md = (ROOT / "references" / "styles.md").read_text(encoding="utf-8")
        for sid, entry in self.table.items():
            if sid == "14":
                continue  # 14 號影片錨在 §14，格式不同（含 <Picture 1>）
            self.assertIn(entry["anchor"], md, f"{sid} 的錨與 styles.md 不一致")
            self.assertIn(entry["negative"], md, f"{sid} 的負面錨與 styles.md 不一致")

    def test_table_anchor_by_index_and_key(self):
        self.assertIn("painterly xianxia fantasy illustration", style_rules.table_anchor("7"))
        self.assertIn("painterly xianxia fantasy illustration", style_rules.table_anchor("xianxia-painterly"))
        self.assertEqual(style_rules.table_anchor("14"), style_rules.VIDEO_ANCHOR)
        self.assertEqual(style_rules.table_anchor("unknown-style"), "")

    def test_table_negative(self):
        self.assertIn("3D render, CGI, plastic skin", style_rules.table_negative("7"))
        self.assertEqual(style_rules.table_negative("nope"), "")


class RemixAnchorResolutionTests(unittest.TestCase):
    """remix_style_anchor 的解析順序：段落錨 > decisions > 14 號 > 查表。"""

    def test_style7_resolves_from_table(self):
        import contextlib
        import io
        import tempfile
        (ROOT / "tmp").mkdir(exist_ok=True)
        import generate_bindings as gb
        import compile_layer2_to_h3 as compiler
        from tests import _remix_fixture as fx
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            root = Path(td)
            layer2_path = fx.write_project(root)
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gb.main(["--root", str(root)]), 0)
            bindings = json.loads((root / "video-bindings.json").read_text(encoding="utf-8"))
            layer2 = json.loads(layer2_path.read_text(encoding="utf-8"))
            layer2["metadata"]["style_key"] = "7"
            layer2["metadata"].pop("style_anchor_en", None)  # 段落錨優先；拿掉才輪到查表
            binding = copy.deepcopy(bindings["segments"][0])
            # en_overlay 的風格錨也會被 apply_stage5_binding 寫回 metadata，一併拿掉
            binding.get("en_overlay", {}).pop("style_anchor_en", None)
            # fixture 寫了 style_anchor 定案（定案又優先於查表）；拿掉才輪到查表
            decisions_path = root / "decisions.json"
            data = json.loads(decisions_path.read_text(encoding="utf-8"))
            data["decisions"] = [d for d in data.get("decisions", []) if d.get("id") != "style_anchor"]
            decisions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            registry = compiler.AssetRegistry(bible_path=root / "video-bible.json", project_root=root)
            seg = compiler.compile_segment_h3(
                layer2, registry, auto_lora=False,
                stage5_binding=binding,
                remix_packs=bindings.get("packs"))
            anchor = style_rules.table_anchor("7")
            body = seg["h3_prompt"].split("integrated_multimodal_description: ", 1)[1]
            self.assertTrue(body.startswith(anchor), body[:120])
            self.assertEqual(seg["metadata"].get("style_anchor_en"), anchor)


if __name__ == "__main__":
    unittest.main()
