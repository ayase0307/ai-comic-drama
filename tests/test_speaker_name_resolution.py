"""說話者中文名解析（fix/speaker-name-resolution）：layer2 的 speaker 寫角色本名時要解析到資產記錄。

- 背景：`h3d bind` 重生 video-bible.json 後，說話者若寫中文本名（非 C- id），
  直接 `registry.characters.get(speaker)` 會落空——英文名丟失（REMIX 提示詞出現中文，E15）、
  voice_only／no_visual_reference 記錄也丟（畫外音誤判成 visible）。
- `_speaker_record`：id 直查 → name 掃描 → 未登記回 {}（不警告、維持舊行為）。
- 編譯層：fixture 的對白 speaker 改成本文名「沈洛年」→ REMIX 提示詞的說話者句用 name_en（Shen Luonian）。
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
import compile_layer2_to_h3 as compiler  # noqa: E402
import generate_bindings as gb  # noqa: E402


class SpeakerNameResolutionTests(unittest.TestCase):
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

    def compile(self, layer2):
        binding = copy.deepcopy(self.bindings["segments"][0])
        with contextlib.redirect_stderr(io.StringIO()):
            return compiler.compile_segment_h3(layer2, self.registry(), auto_lora=False,
                                               stage5_binding=binding,
                                               remix_packs=self.bindings.get("packs"))

    def test_speaker_record_resolves_canonical_name(self):
        reg = self.registry()
        rec = compiler._speaker_record("沈洛年", reg)
        self.assertEqual(rec.get("name_en"), "Shen Luonian")
        # id 直查照舊
        self.assertEqual(compiler._speaker_record("C-SHEN", reg).get("name_en"), "Shen Luonian")
        # 未登記：回 {}、不警告、不炸
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(compiler._speaker_record("路人甲", reg), {})
        self.assertNotIn("路人甲", err.getvalue())

    def test_chinese_speaker_gets_english_name_in_remix_prompt(self):
        layer2 = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        layer2["shots"][1]["dialogue_and_audio"] = {"has_dialogue": True, "speaker": "沈洛年",
                                                    "line_verbatim": "好。", "offscreen_form": "voiceover"}
        seg = self.compile(layer2)
        prompt = seg["h3_prompt"]
        self.assertIn("Shen Luonian (S", prompt)
        self.assertNotIn("沈洛年 (S", prompt)
        self.assertIn("<d>[Chinese] 好。</d>", prompt)

    def test_voice_only_chinese_speaker_routes_offscreen(self):
        # 中文本名的 voice_only 說話者：記錄解析得到 voice_only → 走畫外音句式（閉唇）
        layer2 = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        layer2["shots"][1]["dialogue_and_audio"] = {"has_dialogue": True, "speaker": "沈洛年",
                                                    "line_verbatim": "好。", "offscreen_form": "voiceover"}
        seg = self.compile(layer2)
        prompt = seg["h3_prompt"]
        self.assertIn("lips", prompt.lower())


if __name__ == "__main__":
    unittest.main()
