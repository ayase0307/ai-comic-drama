"""Eian 文章對照（2026-11-05）：color_qa --luma 明暗對比。

- luma_quantiles：L* p5/p50/p95 與 spread（純計算，不需要 ffmpeg）。
- CLI 整合：--luma 時輸出 L* 列（ffmpeg 合成黑白測試圖；無 ffmpeg 就跳過）。
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

import color_qa as cq  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


class LumaQuantilesTests(unittest.TestCase):
    def test_flat_colour_has_zero_spread(self):
        px = [(128, 128, 128)] * 500
        lut = {c: cq.to_lab(c) for c in set(px)}
        p5, p50, p95 = cq.luma_quantiles(px, lut)
        self.assertAlmostEqual(p5, p50)
        self.assertAlmostEqual(p50, p95)

    def test_black_white_mix_has_full_spread(self):
        px = [(0, 0, 0)] * 250 + [(255, 255, 255)] * 250
        lut = {c: cq.to_lab(c) for c in set(px)}
        p5, _, p95 = cq.luma_quantiles(px, lut)
        self.assertAlmostEqual(p5, 0.0, places=1)
        self.assertAlmostEqual(p95, 100.0, places=1)


@unittest.skipIf(FFMPEG is None, "ffmpeg 不在 PATH")
class LumaCliTests(unittest.TestCase):
    def _make_png(self, path, color, extra_vf=""):
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-f", "lavfi", "-i", f"color=c={color}:s=64x36:d=1"]
        if extra_vf:
            cmd += ["-vf", extra_vf]
        cmd += ["-frames:v", "1", str(path)]
        subprocess.run(cmd, check=True, capture_output=True)

    def test_luma_flag_prints_luma_lines(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            a = Path(td) / "black.png"
            b = Path(td) / "white.png"
            self._make_png(a, "black")
            self._make_png(b, "white")
            out = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "color_qa.py"), str(a), str(b), "--luma"],
                capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertIn("L* p5/p50/p95", out.stdout)
            self.assertIn("L* mean distance", out.stdout)

    def test_default_output_unchanged_without_flag(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            a = Path(td) / "black.png"
            self._make_png(a, "black")
            out = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "color_qa.py"), str(a)],
                capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertNotIn("L* p5/p50/p95", out.stdout)
            self.assertIn("meanLab", out.stdout)


if __name__ == "__main__":
    unittest.main()
