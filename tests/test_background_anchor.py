"""P1-7：特寫／過肩鏡的編譯器背景錨——固定帶場景環境句，禁用設定圖灰底（11-03 #5b）。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

import compile_layer2_to_h3 as compiler  # noqa: E402
from tests import _remix_fixture as fx  # noqa: E402

GUARD = "never the plain studio backdrop of the character reference sheet"


class BackgroundAnchorCompileTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self._tmp.name)
        self.layer2_path = fx.write_project(self.root)
        import generate_bindings as gb
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gb.main(["--root", str(self.root)]), 0)
        self.bindings = json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self._tmp.cleanup()

    def _compile(self, shot_size):
        layer2 = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        layer2["shots"][0]["camera_optics"]["shot_size"] = shot_size
        registry = compiler.AssetRegistry(bible_path=self.root / "video-bible.json", project_root=self.root)
        return compiler.compile_segment_h3(
            layer2, registry, auto_lora=False,
            stage5_binding=copy.deepcopy(self.bindings["segments"][0]),
            remix_packs=self.bindings.get("packs"))

    def test_close_shot_carries_background_anchor(self):
        for size in ("CU", "MCU", "OTS_MS"):
            with self.subTest(size=size):
                seg = self._compile(size)
                self.assertIn(GUARD, seg["h3_prompt"])

    def test_wide_shot_does_not(self):
        seg = self._compile("MS")
        self.assertNotIn(GUARD, seg["h3_prompt"])

    def test_anchor_uses_scene_description(self):
        seg = self._compile("CU")
        # 場景卡的英文描述要真的進句裡（不是空殼句）
        self.assertRegex(seg["h3_prompt"], r"bound scene itself \(.{20,}\)")


if __name__ == "__main__":
    unittest.main()
