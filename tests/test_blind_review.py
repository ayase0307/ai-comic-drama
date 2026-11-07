"""Eian 文章對照（2026-11-05）：盲審材料包（build_blind_review.py）。

- stage 3：只帶劇本本文；manifest 記來源；包內不得出現結論檔。
- --inputs：手動材料（階段 1 故事地圖等）。
- stage 7：只收 videos/ 頂層 mp4（核准版；子目錄如 final-768/ 不收），
  每段抽幀拼貼成一張 jpg（ffmpeg 合成測試片；無 ffmpeg 就跳過該組）。
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"),):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_blind_review as br  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


class BlindReviewStage3Tests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        (self.root / "script-ep01.md").write_text("# EP01 劇本\n△ 場一\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stage3_bundle_has_script_only(self):
        bundle = br.build(self.root, 3, "EP01", [], 6)
        self.assertTrue((bundle / "files" / "script-ep01.md").is_file())
        import json
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["stage"], 3)
        self.assertEqual(manifest["sources"], ["script-ep01.md"])
        # 包內只有 files/ 與 manifest.json——結論檔不准進包
        names = sorted(p.name for p in bundle.rglob("*") if p.is_file())
        self.assertEqual(names, ["manifest.json", "script-ep01.md"])

    def test_stage3_missing_script_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            br.build(self.root, 3, "EP09", [], 6)
        self.assertEqual(ctx.exception.code, 2)

    def test_inputs_mode_copies_files(self):
        (self.root / "adapt").mkdir()
        (self.root / "adapt" / "story-map.md").write_text("# 故事地圖", encoding="utf-8")
        bundle = br.build(self.root, None, None, ["adapt/story-map.md"], 6)
        self.assertTrue((bundle / "files" / "story-map.md").is_file())
        self.assertIn("adapt/story-map.md", (bundle / "manifest.json").read_text(encoding="utf-8"))


@unittest.skipIf(FFMPEG is None, "ffmpeg 不在 PATH")
class BlindReviewStage7Tests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        vids = self.root / "videos"
        vids.mkdir()
        for name in ("EP01-S01-a", "EP01-S01-b"):
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc=size=160x90:rate=8:duration=1",
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                 str(vids / f"{name}.mp4")],
                check=True, capture_output=True)
        # 定稿子目錄不應被收進包（核准版＝videos/ 頂層）
        sub = vids / "final-768"
        sub.mkdir()
        (sub / "EP01-S01-a.mp4").write_bytes(b"not a video")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stage7_sheets_from_top_level_videos_only(self):
        bundle = br.build(self.root, 7, "EP01", [], 6)
        sheets = sorted(p.name for p in (bundle / "sheets").glob("*.jpg"))
        self.assertEqual(sheets, ["EP01-S01-a.jpg", "EP01-S01-b.jpg"])
        import json
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["stage"], 7)
        self.assertNotIn("final-768", "\n".join(manifest["contact_sheets"]))

    def test_stage7_no_videos_exits_2(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(SystemExit) as ctx:
            br.build(empty, 7, "EP01", [], 6)
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
