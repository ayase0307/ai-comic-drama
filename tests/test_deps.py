"""Segment 級依賴帳本（I5）：改一鏡要能列出哪些段失效，且帳本不能自己抹平證據。"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from scripts.storyboard import deps


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class DepsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.layer2 = self.root / "layer2" / "layer2-EP01-S01.json"
        write_json(self.layer2, {"segment_id": "EP01-S01", "shots": [{"shot_id": "SH01"}]})
        self.segments = self.root / "segments-ep01.json"
        write_json(self.segments, [{
            "segment_id": "EP01-S01",
            "h3_prompt": "A quiet street at dusk.",
            "metadata": {"frames": 192},
        }])
        (self.root / "videos").mkdir()
        self.video = self.root / "videos" / "EP01-S01.mp4"
        self.video.write_bytes(b"mp4")
        # 讓影片比提示詞檔舊，模擬「改了 prompt 但沒重跑影片」的常見狀態
        old = time.time() - 7200
        os.utime(self.video, (old, old))

    def _reasons(self):
        report = deps.status(self.root)
        stale = {item["segment_id"]: item["reasons"] for item in report["stale"]}
        return report, stale

    def test_record_then_status_reports_video_older_than_prompt(self):
        deps.record(self.root)
        report, stale = self._reasons()
        # 影片早於提示詞 → 這正是 v1 會誤判 clean 的情境
        self.assertIn("video_older_than_prompt", stale["EP01-S01"])

    def test_clean_after_video_is_regenerated(self):
        deps.record(self.root)
        os.utime(self.video, None)  # 影片重跑後 mtime 更新
        deps.record(self.root)
        report, stale = self._reasons()
        self.assertEqual(stale, {})

    def test_layer2_change_marks_prompt_stale(self):
        deps.record(self.root)
        write_json(self.layer2, {"segment_id": "EP01-S01", "shots": [{"shot_id": "SH01", "duration": 9}]})
        _, stale = self._reasons()
        self.assertIn("layer2_changed", stale["EP01-S01"])
        self.assertIn("prompt_stale", stale["EP01-S01"])

    def test_recompile_clears_prompt_stale(self):
        deps.record(self.root)
        write_json(self.layer2, {"segment_id": "EP01-S01", "shots": [{"shot_id": "SH01", "x": 1}]})
        # 重編譯：提示詞檔更新（內容也變）
        time.sleep(0.01)
        write_json(self.segments, [{
            "segment_id": "EP01-S01",
            "h3_prompt": "A quiet street at night.",
            "metadata": {"frames": 192},
        }])
        deps.record(self.root)
        _, stale = self._reasons()
        self.assertNotIn("prompt_stale", stale.get("EP01-S01", []))

    def test_prompt_edited_without_recompile_is_reported(self):
        deps.record(self.root)
        write_json(self.segments, [{
            "segment_id": "EP01-S01",
            "h3_prompt": "A quiet street at midnight.",
            "metadata": {"frames": 192},
        }])
        _, stale = self._reasons()
        self.assertIn("prompt_changed_elsewhere", stale["EP01-S01"])

    def test_missing_video_is_reported(self):
        deps.record(self.root)
        self.video.unlink()
        _, stale = self._reasons()
        self.assertIn("video_missing", stale["EP01-S01"])

    def test_new_segment_without_video_goes_to_unproduced(self):
        deps.record(self.root)
        write_json(self.root / "layer2" / "layer2-EP01-S02.json",
                   {"segment_id": "EP01-S02", "shots": [{"shot_id": "SH01"}]})
        report = deps.status(self.root)
        self.assertIn("EP01-S02", report["unproduced"])

    def test_removed_segment_is_reported(self):
        deps.record(self.root)
        self.layer2.unlink()
        self.segments.unlink()
        self.video.unlink()
        report = deps.status(self.root)
        self.assertIn("EP01-S01", report["removed"])

    def test_backup_segments_file_is_ignored(self):
        deps.record(self.root)
        write_json(self.root / "segments-ep01.bak.json", [{
            "segment_id": "EP01-S01", "h3_prompt": "backup prompt", "metadata": {},
        }])
        _, stale = self._reasons()
        self.assertNotIn("prompt_changed_elsewhere", stale.get("EP01-S01", []))

    def test_conflicting_episode_files_are_ambiguous(self):
        deps.record(self.root)
        write_json(self.root / "segments-ep02.json", [{
            "segment_id": "EP01-S01", "h3_prompt": "different", "metadata": {},
        }])
        _, stale = self._reasons()
        self.assertIn("prompt_ambiguous", stale["EP01-S01"])

    def test_unknown_video_files_are_ignored(self):
        deps.record(self.root)
        (self.root / "videos" / "EP01-S01-v2.mp4").write_bytes(b"x")
        deps.record(self.root)
        report = deps.status(self.root)
        self.assertTrue(any("EP01-S01-v2" in item for item in report["ignored_videos"]))

    def test_record_refuses_empty_directory(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            deps.record(empty)
        self.assertEqual(deps.main(["--root", str(empty), "--record"]), 2)

    def test_schema_mismatch_is_reported(self):
        deps.record(self.root)
        ledger = self.root / deps.LEDGER_NAME
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        payload["schema_version"] = 1
        ledger.write_text(json.dumps(payload), encoding="utf-8")
        report = deps.status(self.root)
        self.assertTrue(report.get("schema_mismatch"))
        self.assertIn("schema", deps.render(report))

    def test_status_without_ledger_says_not_recorded(self):
        report = deps.status(self.root)
        self.assertFalse(report["recorded"])
        self.assertIn("尚未建立", deps.render(report))

    def test_unproduced_is_separate_from_stale(self):
        self.video.unlink()
        deps.record(self.root)
        write_json(self.layer2, {"segment_id": "EP01-S01", "shots": [{"shot_id": "SH01", "z": 1}]})
        report = deps.status(self.root)
        self.assertEqual(report["stale"], [])
        self.assertIn("EP01-S01", report["unproduced"])

    def test_cli_strict_returns_nonzero_when_stale(self):
        self.assertEqual(deps.main(["--root", str(self.root), "--record"]), 0)
        write_json(self.layer2, {"segment_id": "EP01-S01", "shots": [{"shot_id": "SH01", "q": 1}]})
        self.assertEqual(deps.main(["--root", str(self.root), "--status", "--strict"]), 1)
        self.assertEqual(deps.main(["--root", str(self.root), "--status"]), 0)


if __name__ == "__main__":
    unittest.main()
