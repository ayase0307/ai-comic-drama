"""CLI 級證據分級回歸：確認「假 PASS」在真實入口被擋住，而不是只有單元測試綠。

對應 P2 對抗式審查的 blocker：
  - 10 段只有 1 段產出時，報告標題仍寫 TECHNICAL CHECK PASSED
  - 模式 3 只掃有 video_file 的鏡頭 → 3 鏡 1 片也被判 VERIFIED
  - --segments 遇到同名雙檔（ambiguous）會崩潰且不產報告
"""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.storyboard import verify_video_shot as qa

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg")


def _make_video(path: Path, seconds: float = 8.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=gray:s=64x64:d={seconds}:r=24",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


@unittest.skipUnless(FFMPEG, "需要 ffmpeg 才能產生測試影片")
class CLIEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.videos = self.tmp / "videos"
        self.videos.mkdir()

    def _segments(self, count: int) -> Path:
        path = self.tmp / "segments-ep01.json"
        path.write_text(json.dumps([
            {"segment_id": f"EP01-S{index:02d}",
             "metadata": {"target_duration_sec": 8.0, "frames": 192},
             "shots": [{"shot_id": "SH01"}]}
            for index in range(1, count + 1)
        ], ensure_ascii=False), encoding="utf-8")
        return path

    def _run(self, args):
        env = dict(__import__("os").environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [__import__("sys").executable, str(ROOT / "scripts" / "storyboard" / "verify_video_shot.py")]
            + [str(item) for item in args],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")

    def test_one_of_ten_produced_is_partial_and_never_says_passed(self):
        segments = self._segments(10)
        _make_video(self.videos / "EP01-S01.mp4")
        code, _ = self._run([
            "--segments", str(segments), "--videos-dir", str(self.videos),
            "--out-json", str(self.tmp / "qa.json"), "--out-report", str(self.tmp / "qa.md"),
        ])
        report = (self.tmp / "qa.md").read_text(encoding="utf-8")
        payload = json.loads((self.tmp / "qa.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(payload["evidence"]["verdict"], "PARTIAL")
        self.assertEqual(payload["evidence"]["expected"], 10)
        self.assertNotIn("TECHNICAL CHECK PASSED", report)
        self.assertIn("PARTIAL", report)
        self.assertIn("UNVERIFIED", report)

    def test_ambiguous_segment_does_not_crash_and_is_not_counted(self):
        segments = self._segments(1)
        _make_video(self.videos / "EP01-S01.mp4")
        _make_video(self.videos / "seg-EP01-S01.mp4")
        code, _ = self._run([
            "--segments", str(segments), "--videos-dir", str(self.videos),
            "--out-json", str(self.tmp / "qa.json"), "--out-report", str(self.tmp / "qa.md"),
        ])
        self.assertTrue((self.tmp / "qa.json").is_file(), "ambiguous 不應讓程式崩潰而不產報告")
        payload = json.loads((self.tmp / "qa.json").read_text(encoding="utf-8"))
        # 一段都沒有被量測到 → UNVERIFIED；重點是「不得 VERIFIED」且不得崩潰
        self.assertNotEqual(payload["evidence"]["verdict"], "VERIFIED")
        self.assertIn("EP01-S01", payload["evidence"]["unverified_segments"])
        self.assertEqual(code, 1)

    def test_single_layer2_mode_counts_shots_without_video(self):
        video = self.videos / "shot.mp4"
        _make_video(video)
        layer2 = self.tmp / "layer2-EP01-S01.json"
        layer2.write_text(json.dumps({
            "segment_id": "EP01-S01",
            "metadata": {"target_duration_sec": 24.0},
            "shots": [
                {"shot_id": "SH01", "start_time": 0.0, "end_time": 8.0, "duration": 8.0,
                 "video_file": str(video)},
                {"shot_id": "SH02", "start_time": 8.0, "end_time": 16.0, "duration": 8.0},
                {"shot_id": "SH03", "start_time": 16.0, "end_time": 24.0, "duration": 8.0},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        code, _ = self._run([
            "--layer2", str(layer2), "--out-json", str(self.tmp / "qa.json"),
            "--out-report", str(self.tmp / "qa.md"),
        ])
        payload = json.loads((self.tmp / "qa.json").read_text(encoding="utf-8"))
        self.assertNotEqual(payload["evidence"]["verdict"], "VERIFIED")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
