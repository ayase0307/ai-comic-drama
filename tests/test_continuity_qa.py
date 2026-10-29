"""PR-19b（R3-16 方案 B）：交界連續性 QA——實際切點、交界拼貼、一側靜止候選；只警告、不擋任何關卡。"""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "scripts", ROOT / "scripts" / "storyboard"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    import numpy as np
except ImportError:  # Windows CI 沒裝 numpy
    np = None

import continuity_qa as cq  # noqa: E402  (模組本身不強制 numpy)

FPS = 24
W, H = 96, 54
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _stripes(phase: float, vertical: bool, width=W, height=H):
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float64)
    coord = xx if vertical else yy
    return (127 + 100 * np.sin(coord / 5.0 + phase)).astype(np.uint8)


def _shot_a(n, start=0):
    """整格都在動的直條紋。"""
    return [_stripes(0.25 * (start + i), True) for i in range(n)]


def _shot_b_left_only(n, start=0):
    """橫條紋，只有左 1/3 在動（中、右靜止）→ 不，這裡讓左＋中動、右靜止。"""
    frames = []
    for i in range(n):
        base = _stripes(0.0, False)
        moving = _stripes(0.3 * (start + i), False)
        base[:, : 2 * W // 3] = moving[:, : 2 * W // 3]
        frames.append(base)
    return frames


@unittest.skipIf(np is None, "需要 numpy")
class PureComputationTests(unittest.TestCase):
    def test_find_cut_locates_early_cut_within_window(self):
        gray = np.stack(_shot_a(48) + [_stripes(0.2 * i, False) for i in range(48)])
        diffs = cq.adjacent_dissimilarities(gray)
        cut = cq.find_cut(diffs, FPS, planned=2.3)
        self.assertEqual(cut["frame"], 48)
        self.assertAlmostEqual(cut["actual"], 2.0, places=3)
        self.assertAlmostEqual(cut["offset"], -0.3, places=3)
        self.assertTrue(cut["confident"])

    def test_cut_outside_window_is_not_found(self):
        gray = np.stack(_shot_a(24) + [_stripes(0.2 * i, False) for i in range(72)])
        diffs = cq.adjacent_dissimilarities(gray)
        cut = cq.find_cut(diffs, FPS, planned=3.0, window=0.9)  # 真正切點在 1.0s，不在 2.1–3.9s
        self.assertFalse(cut["confident"])

    def test_no_cut_is_unclear(self):
        gray = np.stack(_shot_a(96))
        cut = cq.find_cut(cq.adjacent_dissimilarities(gray), FPS, planned=2.0)
        self.assertFalse(cut["confident"])

    def test_column_motion_flags_static_side(self):
        gray = np.stack(_shot_b_left_only(30))
        motion = cq.column_motion(gray, 0, len(gray))
        self.assertEqual(motion["one_side_static"], "right")
        self.assertGreater(motion["left"], motion["right"] * 4)

    def test_column_motion_ignores_fully_static_shot(self):
        gray = np.stack([_stripes(0.0, True)] * 20)
        self.assertIsNone(cq.column_motion(gray, 0, 20)["one_side_static"])

    def test_column_motion_skips_cut_pair(self):
        gray = np.stack(_shot_a(10) + [_stripes(0.0, False)] * 10)
        with_cut = cq.column_motion(gray, 0, 20)
        without = cq.column_motion(gray, 0, 20, skip_pairs=[9])
        self.assertGreater(with_cut["right"], without["right"])

    def test_planned_cuts_prefers_cut_markers_then_shots(self):
        seg = {"metadata": {"cut_markers": [{"at_seconds": 5.0}, {"at_seconds": 2.5}]},
               "shots": [{"start_time": 0}, {"start_time": 3.0}]}
        self.assertEqual(cq.planned_cuts(seg), [2.5, 5.0])
        self.assertEqual(cq.planned_cuts({"shots": [{"start_time": 0}, {"start_time": 3.0}]}), [3.0])


def _encode(frames, out: Path):
    raw = b"".join(np.stack([f, f, f], axis=-1).astype(np.uint8).tobytes() for f in frames)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, input=raw, check=True, timeout=120)


@unittest.skipIf(np is None or not HAS_FFMPEG, "需要 numpy 與 ffmpeg")
class SyntheticVideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "videos").mkdir()
        # A：0–2.0s 直條紋全畫面動，2.0s 切到橫條紋（右側靜止）；規劃切點 2.3s（模型晚切的反面：早切 0.3s）
        _encode(_shot_a(48) + _shot_b_left_only(48), self.root / "videos" / "EP01-S01-a.mp4")
        # B：單鏡；C 沒有影片
        _encode(_shot_a(48, start=10), self.root / "videos" / "EP01-S01-b.mp4")
        segs = {"segments": [
            {"segment_id": "EP01-S01-a", "metadata": {"cut_markers": [{"at_seconds": 2.3}]}},
            {"segment_id": "EP01-S01-b", "metadata": {}},
            {"segment_id": "EP01-S01-c", "metadata": {}},
        ]}
        (self.root / "segments-ep01.json").write_text(json.dumps(segs), encoding="utf-8")

    def test_report_and_montages(self):
        import project_state as ps
        before = ps.stage_snapshot(self.root, 6)
        report = cq.run(self.root)
        by_id = {s["segment_id"]: s for s in report["segments"]}
        a, b, c = by_id["EP01-S01-a"], by_id["EP01-S01-b"], by_id["EP01-S01-c"]
        self.assertEqual(a["status"], "analyzed")
        self.assertEqual(len(a["cuts"]), 1)
        self.assertAlmostEqual(a["cuts"][0]["actual"], 2.0, places=2)
        self.assertTrue(a["cuts"][0]["confident"])
        self.assertEqual(a["columns"][1]["one_side_static"], "right")
        self.assertTrue(any("一側靜止候選" in w for w in a["warnings"]))
        self.assertEqual(a["neighbours"], {"prev": None, "next": "EP01-S01-b"})
        self.assertEqual(b["neighbours"], {"prev": "EP01-S01-a", "next": None})
        self.assertEqual(c["status"], "no_video")
        for entry in (a, b):
            png = self.root / entry["montage"]
            self.assertTrue(png.is_file())
            from PIL import Image
            with Image.open(png) as img:
                self.assertEqual(img.format, "PNG")
        report_file = self.root / "videos" / "qa" / "continuity" / "continuity-report.json"
        saved = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["gate"], "warning_only")
        self.assertEqual(saved["summary"]["analyzed"], 2)
        # 只警告：不寫 qa-report.json、不動階段 6 快照
        self.assertFalse((self.root / "videos" / "qa-report.json").exists())
        self.assertEqual(before, ps.stage_snapshot(self.root, 6))
        self.assertEqual(set(cq.load_report(self.root)), {"EP01-S01-a", "EP01-S01-b", "EP01-S01-c"})

    def test_h3d_qa_continuity_route(self):
        import h3d
        out = io.StringIO()
        with redirect_stdout(out):
            rc = h3d.main(["qa", "--continuity", "--root", str(self.root), "--segment-id", "EP01-S01-a"])
        self.assertEqual(rc, 0)
        self.assertIn("只警告", out.getvalue())
        self.assertTrue((self.root / "videos" / "qa" / "continuity" / "EP01-S01-a.png").is_file())

    def test_review_panel_shows_montage_and_warnings(self):
        import build_stage_review as bsr
        cq.run(self.root)
        entries = bsr._continuity_entries(self.root)
        panel = bsr._continuity_panel(self.root, entries["EP01-S01-a"])
        self.assertIn("../videos/qa/continuity/EP01-S01-a.png", panel)
        self.assertIn("一側靜止候選", panel)
        self.assertIn("實際 2.0", panel)


class ReviewPanelWithoutReportTests(unittest.TestCase):
    def test_panel_hint_when_no_report(self):
        import build_stage_review as bsr
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            self.assertEqual(bsr._continuity_entries(Path(tmp)), {})
            self.assertIn("h3d.py qa --continuity", bsr._continuity_panel(Path(tmp), None))


if __name__ == "__main__":
    unittest.main()
