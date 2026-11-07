"""R09 結尾錨（style_lock_tail）：REMIX 提示詞結尾的定案解析（噩盡島監督實測修正）。

- decisions.style_lock_tail：有定案回原句、沒定案回 None。
- remix_style_lock_tail：Layer 2 metadata.style_lock_tail_en > 定案 style_lock_tail > 預設句；
  中文值 → 預設句＋附註（REMIX 提示詞只放英文）。
- 編譯層：定案句逐字進 h3_prompt 的 integrated_multimodal_description 結尾（無字句之前）；
  沒定案時行為不變（預設句，golden 測試不動）。
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "tests"))

import _remix_fixture as fx  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import compile_layer2_to_h3 as compiler  # noqa: E402
import decisions  # noqa: E402
import generate_bindings as gb  # noqa: E402

TAIL = ("Semi-realistic 3D anime CG with a painted finish, matte poreless skin with a soft translucent glow, "
        "narrow elongated almond eyes, adult proportions, warm amber and honey high-key grade, tropical "
        "high-noon light, painterly concept-art look, light film grain.")
CJK_NOTE = "style_lock_tail 是中文，改用預設 Style lock 句"


class StyleLockTailTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.layer2_path = fx.write_project(self.root)
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            code = gb.main(["--root", str(self.root)])
        self.assertEqual(code, 0, err.getvalue())
        self.bindings = json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))

    def registry(self):
        return compiler.AssetRegistry(bible_path=self.root / "video-bible.json", project_root=self.root)

    def compile(self, layer2=None, binding=None):
        data = layer2 if layer2 is not None else json.loads(self.layer2_path.read_text(encoding="utf-8"))
        binding = binding if binding is not None else copy.deepcopy(self.bindings["segments"][0])
        with contextlib.redirect_stderr(io.StringIO()):
            return compiler.compile_segment_h3(data, self.registry(), auto_lora=False,
                                               stage5_binding=binding,
                                               remix_packs=self.bindings.get("packs"))

    def body(self, seg) -> str:
        return audit._section_body(seg["h3_prompt"], "integrated_multimodal_description").strip()

    def test_decisions_helper(self):
        self.assertIsNone(decisions.style_lock_tail(None))
        self.assertIsNone(decisions.style_lock_tail(self.root))
        decisions.decide(self.root, "style_lock_tail", TAIL, "每段提示詞結尾都要附這句風格錨（逐字）", stages=[5, 6])
        self.assertEqual(decisions.style_lock_tail(self.root), TAIL)

    def test_helper_resolution_order(self):
        reg = self.registry()
        # 沒 metadata、沒定案 → 預設句
        tail, note = compiler.remix_style_lock_tail({"metadata": {}}, reg)
        self.assertEqual((tail, note), (compiler.REMIX_STYLE_LOCK_DEFAULT, ""))
        # 定案 → 定案句
        decisions.decide(self.root, "style_lock_tail", TAIL, "每段提示詞結尾都要附這句風格錨（逐字）", stages=[5, 6])
        tail, note = compiler.remix_style_lock_tail({"metadata": {}}, reg)
        self.assertEqual((tail, note), (TAIL, ""))
        # Layer 2 metadata 蓋過定案
        tail, note = compiler.remix_style_lock_tail({"metadata": {"style_lock_tail_en": "Meta tail."}}, reg)
        self.assertEqual((tail, note), ("Meta tail.", ""))
        # 中文 → 預設句＋附註
        tail, note = compiler.remix_style_lock_tail({"metadata": {"style_lock_tail_en": "中文結尾句"}}, reg)
        self.assertEqual(tail, compiler.REMIX_STYLE_LOCK_DEFAULT)
        self.assertEqual(note, CJK_NOTE)

    def test_no_decision_keeps_default_tail(self):
        seg = self.compile()
        body = self.body(seg)
        self.assertIn(compiler.REMIX_STYLE_LOCK_DEFAULT, body)
        self.assertNotIn("painterly concept-art", body)

    def test_decision_tail_reaches_prompt_before_no_lettering(self):
        decisions.decide(self.root, "style_lock_tail", TAIL, "每段提示詞結尾都要附這句風格錨（逐字）", stages=[5, 6])
        seg = self.compile()
        body = self.body(seg)
        self.assertIn(TAIL, body)
        self.assertNotIn(compiler.REMIX_STYLE_LOCK_DEFAULT, body)
        # R09 句在無字句之前；無字句仍是全段最後一句
        self.assertLess(body.index(TAIL), body.index("no graffiti"))
        self.assertTrue(body.rstrip().endswith("no graffiti."))

    def test_metadata_tail_wins_over_decision(self):
        decisions.decide(self.root, "style_lock_tail", TAIL, "每段提示詞結尾都要附這句風格錨（逐字）", stages=[5, 6])
        layer2 = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        layer2.setdefault("metadata", {})["style_lock_tail_en"] = "Segment-level style lock sentence."
        seg = self.compile(layer2=layer2)
        body = self.body(seg)
        self.assertIn("Segment-level style lock sentence.", body)
        self.assertNotIn("painterly concept-art", body)

    def test_chinese_decision_falls_back_to_default_with_note(self):
        decisions.decide(self.root, "style_lock_tail", "每段結尾都要霧面厚塗", "中文定案", stages=[5, 6])
        seg = self.compile()
        body = self.body(seg)
        self.assertIn(compiler.REMIX_STYLE_LOCK_DEFAULT, body)
        self.assertIn(CJK_NOTE, seg.get("compile_notes", []))


if __name__ == "__main__":
    unittest.main()
