"""階段 6 審核頁：影片 × 九宮格 × 設定圖 × QA 的並排驗收。

這個測試守的是「頁面承諾的四欄真的存在」——先前版本只剩影片＋QA，
標題卻寫著並排驗收，等於把對照工作丟回給人。
"""
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "storyboard"))

import build_stage_review as review  # noqa: E402
import project_state as ps  # noqa: E402

# 1x1 透明 PNG
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def build_project(root: Path, with_visuals: bool) -> None:
    write_json(root / "layer2" / "layer2-EP01-S01-a.json", {
        "segment_id": "EP01-S01-a", "scene_id": "SC01",
        "metadata": {"target_duration_sec": 8.0},
        "shots": [
            {"shot_id": "SH01", "start_time": 0.0, "end_time": 4.0, "duration": 4.0,
             "character_ids": ["C-MIRA"]},
            {"shot_id": "SH02", "start_time": 4.0, "end_time": 8.0, "duration": 4.0,
             "character_ids": ["C-MIRA"]},
        ],
    })
    write_json(root / "adapt" / "bible.json", {
        "characters": [{"character_id": "C-MIRA", "canonical_name": "Mira",
                        "reference_image": "images/mira.png"}],
    })
    (root / "videos").mkdir(parents=True, exist_ok=True)
    (root / "videos" / "EP01-S01-a.mp4").write_bytes(b"fake-mp4")
    write_json(root / "videos" / "qa-report.json", {
        "results": [{"segment_id": "EP01-S01-a", "video_file": "videos/EP01-S01-a.mp4",
                     "passed": True}],
    })
    if with_visuals:
        (root / "images").mkdir(parents=True, exist_ok=True)
        (root / "images" / "grid-EP01-S01-a.png").write_bytes(PNG_1PX)
        (root / "images" / "mira.png").write_bytes(PNG_1PX)


class Stage6ReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.old = ROOT

    def _render(self):
        with mock.patch.object(review, "stage6_errors", return_value=[]):
            ok, errors, html = review.build_stage_6(self.root, {"stages": {}})
        return ok, errors, html

    def test_page_shows_video_grid_and_design_sheet(self):
        build_project(self.root, with_visuals=True)
        ok, errors, html = self._render()
        self.assertTrue(ok, errors)
        self.assertIn("EP01-S01-a.mp4", html)
        self.assertIn("分鏡總覽圖 EP01-S01-a", html)
        self.assertIn("../images/grid-EP01-S01-a.png", html)
        self.assertIn("../images/mira.png", html)
        self.assertIn("技術 QA PASS", html)
        self.assertNotIn("缺漏設定圖", html)
        self.assertNotIn("找不到分鏡總覽圖", html)

    def test_missing_visuals_are_flagged_but_not_blocking(self):
        build_project(self.root, with_visuals=False)
        ok, errors, html = self._render()
        self.assertTrue(ok, "缺圖只紅框，不阻擋核准")
        self.assertIn("找不到分鏡總覽圖", html)
        self.assertIn("缺漏設定圖", html)
        self.assertIn("分鏡總覽圖覆蓋", html)

    def test_qa_failure_badge_is_shown(self):
        build_project(self.root, with_visuals=True)
        write_json(self.root / "videos" / "qa-report.json", {
            "results": [{"segment_id": "EP01-S01-a", "video_file": "videos/EP01-S01-a.mp4",
                         "passed": False}],
        })
        _ok, _errors, html = self._render()
        self.assertIn("技術 QA FAIL", html)

    def test_manifest_supplies_design_image_when_bible_has_none(self):
        build_project(self.root, with_visuals=True)
        # bible 沒有 reference_image，圖登記在 reference-manifest（實務常態）
        write_json(self.root / "adapt" / "bible.json", {
            "characters": [{"character_id": "C-MIRA", "canonical_name": "Mira"}],
        })
        write_json(self.root / "assets" / "reference-manifest.json", {
            "assets": [{"stable_id": "char-Mira",
                        "source_id": "C-MIRA / W-mira-school",
                        "target_path": "images/mira.png",
                        "status": "received_pending_visual_approval"}],
        })
        _ok, _errors, html = self._render()
        self.assertIn("../images/mira.png", html)
        self.assertNotIn("缺漏設定圖", html)

    def test_grid_file_metadata_is_shown(self):
        build_project(self.root, with_visuals=True)
        (self.root / "images" / "grid-page.png").write_bytes(PNG_1PX)
        data = json.loads((self.root / "layer2" / "layer2-EP01-S01-a.json").read_text(encoding="utf-8"))
        data["shots"][0]["metadata"] = {"grid_file": "images/grid-page.png"}
        write_json(self.root / "layer2" / "layer2-EP01-S01-a.json", data)
        _ok, _errors, html = self._render()
        self.assertIn("分鏡總覽圖 grid-page", html)
        self.assertIn("../images/grid-page.png", html)


if __name__ == "__main__":
    unittest.main()
