"""Eian 文章對照（2026-11-05）：fl2v 首尾幀疊圖差異檢查（frame_pair_qa.py）。

ffmpeg 合成測試圖：紅色底 vs 紅底＋藍色方塊——
- 完全相同的兩張圖：全圖與每格 dE76 都接近 0；
- 局部改動的兩張圖：差異集中在方塊所在的格子。
無 ffmpeg 就跳過。
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.storyboard import frame_pair_qa as fpq  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


@unittest.skipIf(FFMPEG is None, "ffmpeg 不在 PATH")
class FramePairQaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        base = Path(cls.tmp.name)
        cls.same_a = base / "same_a.png"
        cls.same_b = base / "same_b.png"
        cls.box_a = base / "box_a.png"
        cls.box_b = base / "box_b.png"
        for path, vf in (
            (cls.same_a, None),
            (cls.same_b, None),
            (cls.box_a, None),
            (cls.box_b, "drawbox=x=0:y=0:w=40:h=30:color=blue:t=fill"),
        ):
            cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-f", "lavfi", "-i", "color=c=red:s=160x90:d=1"]
            if vf:
                cmd += ["-vf", vf]
            cmd += ["-frames:v", "1", str(path)]
            subprocess.run(cmd, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_identical_pair_is_flat(self):
        rep = fpq.pair_report(str(self.same_a), str(self.same_b), 8, 5)
        self.assertLess(rep["global_mean_dE76"], 2.0)
        self.assertTrue(all(v < 2.0 for row in rep["grid"] for v in row), rep["grid"])

    def test_local_change_concentrates_in_cells(self):
        rep = fpq.pair_report(str(self.box_a), str(self.box_b), 8, 5)
        top = rep["top_cells"][0]
        self.assertGreater(top["mean_dE76"], 20.0)
        # 方塊在左上角 → 最大差異格應在第 1～2 欄、第 1 列
        self.assertLessEqual(top["col"], 2)
        self.assertEqual(top["row"], 1)
        # 其他格子應該安靜：全圖平均遠小於最大格
        self.assertLess(rep["global_mean_dE76"], top["mean_dE76"] / 3)

    def test_json_output_parses(self):
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "storyboard" / "frame_pair_qa.py"),
             str(self.same_a), str(self.same_b), "--json"],
            capture_output=True, text=True, encoding="utf-8", check=True)
        import json
        rep = json.loads(out.stdout)
        self.assertIn("global_mean_dE76", rep)
        self.assertIn("top_cells", rep)


if __name__ == "__main__":
    unittest.main()
