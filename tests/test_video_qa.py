import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.storyboard import verify_video_shot as qa


class VideoQaRegressionTests(unittest.TestCase):
    def _patch_media(self, *, audio=True, width=640, height=360):
        specs = {
            "duration": 2.0,
            "width": width,
            "height": height,
            "fps": 24.0,
            "aspect_ratio_val": width / height,
            "video_codec": "h264",
            "has_audio": audio,
            "audio_codec": "aac" if audio else None,
            "file_size": 100,
        }
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(qa, "probe_video_specs", return_value=specs))
        stack.enter_context(mock.patch.object(qa, "extract_frame_rgb", return_value=bytes([255, 0, 0]) * 360 * 202))
        stack.enter_context(mock.patch.object(qa, "generate_contact_sheet", return_value=False))
        return stack

    def test_aspect_mismatch_fails_technical_qa(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            video = Path(td) / "shot.mp4"
            video.write_bytes(b"media")
            with self._patch_media(width=360, height=640):
                result = qa.verify_single_shot(
                    {"shot_id": "S1", "duration": 2}, video,
                    {"aspect_ratio": "16:9"},
                )
        self.assertFalse(result["passed"])
        self.assertTrue(any("ASPECT_RATIO_MISMATCH" in item for item in result["issues"]))

    def test_required_audio_missing_fails_and_stays_pending_review(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            video = Path(td) / "segment.mp4"
            video.write_bytes(b"media")
            segment = {
                "segment_id": "SEG-1", "seconds": 2,
                "shots": [{"dialogue_and_audio": {"has_dialogue": True}}],
            }
            with self._patch_media(audio=False):
                result = qa.verify_single_segment(segment, video)
        self.assertFalse(result["passed"])
        self.assertEqual(result["review_status"], "pending_review")
        self.assertTrue(any("NO_AUDIO_STREAM_FOR_DIALOGUE" in item for item in result["issues"]))

    def test_narration_requires_audio_but_subtitle_only_does_not(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            video = Path(td) / "segment.mp4"
            video.write_bytes(b"media")
            with self._patch_media(audio=False):
                narration = qa.verify_single_segment({
                    "segment_id": "NARRATED", "seconds": 2,
                    "shots": [{"narration": "Voice over"}],
                }, video)
                subtitle = qa.verify_single_segment({
                    "segment_id": "SILENT-TEXT", "seconds": 2,
                    "shots": [{"subtitle": "畫面文字"}],
                }, video)
        self.assertFalse(narration["passed"])
        self.assertTrue(narration["audio_check"]["required"])
        self.assertTrue(subtitle["passed"])
        self.assertFalse(subtitle["audio_check"]["required"])

    def test_explicit_audio_required_false_overrides_authored_lines(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            video = Path(td) / "segment.mp4"
            video.write_bytes(b"media")
            segment = {
                "segment_id": "SILENT-OVERRIDE", "seconds": 2,
                "audio_required": False,
                "shots": [{"narration": "Optional VO", "dialogue_and_audio": {"has_dialogue": True}}],
            }
            with self._patch_media(audio=False):
                result = qa.verify_single_segment(segment, video)
        self.assertTrue(result["passed"])
        self.assertFalse(result["audio_check"]["required"])

    def test_no_dialogue_marker_does_not_require_audio(self):
        segment = {
            "segment_id": "SILENT", "seconds": 2,
            "shots": [{"dialogue_and_audio": {"has_dialogue": False, "line_verbatim": "（無台詞）"}}],
        }
        self.assertFalse(qa.segment_requires_audio(segment))

    def test_batch_missing_segment_returns_failure_and_reports_inventory(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments.json"
            segments.write_text(json.dumps({"segments": [
                {"segment_id": "SEG-A", "seconds": 2},
                {"segment_id": "SEG-B", "seconds": 2},
            ]}), encoding="utf-8")
            videos = root / "videos"
            videos.mkdir()
            (videos / "SEG-A.mp4").write_bytes(b"a")
            (videos / "wrong-name-SEG-B.mp4").write_bytes(b"misassigned")
            report = root / "qa.json"
            with mock.patch.object(qa, "verify_single_segment", return_value={
                "shot_id": "SEG-A", "segment_id": "SEG-A", "video_file": str(videos / "SEG-A.mp4"),
                "video_sha256": "a" * 64, "passed": True,
                "review_status": "pending_review", "issues": [],
                "specs": {"expected_duration": 2, "duration": 2, "width": 640, "height": 360, "fps": 24},
                "color_analysis": {"mean_chroma": 20}, "grid_check": {"detected": False},
            }), mock.patch.object(sys, "argv", [
                "verify_video_shot.py", "--segments", str(segments),
                "--videos-dir", str(videos), "--out-json", str(report),
            ]), contextlib.redirect_stdout(io.StringIO()):
                exit_code = qa.main()
            payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(payload["expected_segments"], ["SEG-A", "SEG-B"])
        self.assertEqual(payload["unproduced_segments"], ["SEG-B"])

    def test_duplicate_segment_ids_fail_batch(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments.json"
            segments.write_text(json.dumps({"segments": [
                {"segment_id": "SEG-A", "seconds": 2},
                {"segment_id": "SEG-A", "seconds": 2},
            ]}), encoding="utf-8")
            videos = root / "videos"
            videos.mkdir()
            (videos / "SEG-A.mp4").write_bytes(b"a")
            report = root / "qa.json"
            with mock.patch.object(qa, "verify_single_segment", return_value={
                "shot_id": "SEG-A", "segment_id": "SEG-A", "video_file": str(videos / "SEG-A.mp4"),
                "video_sha256": "a" * 64, "passed": True,
                "review_status": "pending_review", "issues": [],
                "specs": {"expected_duration": 2, "duration": 2, "width": 640, "height": 360, "fps": 24},
                "color_analysis": {"mean_chroma": 20}, "grid_check": {"detected": False},
            }), mock.patch.object(sys, "argv", [
                "verify_video_shot.py", "--segments", str(segments),
                "--videos-dir", str(videos), "--out-json", str(report),
            ]), contextlib.redirect_stdout(io.StringIO()):
                exit_code = qa.main()
            payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertNotEqual(exit_code, 0)
        self.assertTrue(payload.get("duplicate_segments"))

    def test_technical_writeback_preserves_manual_approval_lock(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            path = Path(td) / "layer2.json"
            original_review = {"review_status": "approved", "locked": True, "revision": 7}
            path.write_text(json.dumps({"shots": [{"shot_id": "S1", "review": original_review}]}), encoding="utf-8")
            result = {
                "shot_id": "S1", "video_file": "clip.mp4", "video_sha256": "a" * 64,
                "passed": True, "specs": {"duration": 2},
                "color_analysis": {"mean_chroma": 20, "c_tail": 20, "tail_mean_lab": [1, 2, 3]},
                "grid_check": {"detected": False}, "issues": [],
            }
            updated = qa.write_back_review_to_layer2(path, [result])
        shot = updated["shots"][0]
        self.assertEqual(shot["review"], original_review)
        self.assertEqual(shot["technical_review"]["technical_status"], "passed")
        self.assertEqual(shot["technical_review"]["review_status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
