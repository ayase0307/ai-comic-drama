"""Offline cross-tool workflow: compiler -> submit dry-run -> QA -> assembly -> gates.

This deliberately uses tiny local fixtures and never contacts FreeVideo or a TTS service.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STORYBOARD = SCRIPTS / "storyboard"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(STORYBOARD))

import project_state as state
import submit_h3_segments as submit


def run_cli(script: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
    )


class OfflineWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = __import__("shutil").which("ffmpeg")
        cls.ffprobe = __import__("shutil").which("ffprobe")

    def setUp(self):
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("offline workflow requires ffmpeg and ffprobe")
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.project = Path(self.temp.name)
        for name in ("review", "images", "layer2", "layer2/panels", "videos", "final", "adapt"):
            (self.project / name).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def _approve(self, stage: int):
        data = state.load_state(self.project)
        state.mark_awaiting_review(self.project, data, stage)
        ok = state.approve_stage(self.project, stage, "offline workflow test")
        self.assertTrue(ok, f"stage-{stage}; errors={state.stage_validation_errors(self.project, stage)}; "
                        f"prior={state.require_approved(self.project, stage - 1) if stage else 'n/a'}; "
                        f"snapshot_match={state.load_state(self.project)['stages'][state.stage_key(stage)].get('review_snapshot') == state.stage_snapshot(self.project, stage)}")

    def _make_layer2(self, segment_id: str, duration: int):
        from PIL import Image

        shots = []
        for index, (start, end) in enumerate(((0, duration / 2), (duration / 2, duration)), 1):
            shot_id = f"SH{index:02d}"
            panel = self.project / "layer2" / "panels" / f"panel-{index:02d}-{segment_id}-{shot_id}.png"
            Image.new("RGB", (12, 12), "white").save(panel)
            shots.append({
                "shot_id": shot_id, "start_time": start, "end_time": end, "duration": end - start,
                "sketch_file": f"panels/{panel.name}",
                "camera_optics": {"shot_size": "MS", "focal_length": "35mm",
                                  "movement": "static" if index == 1 else "dollies in"},
                "action_and_performance": {"action_stages": [
                    "the character turns toward the doorway", "then steps forward with a steady stance",
                    "the character settles and holds eye contact"]},
                "dialogue_and_audio": {"has_dialogue": False},
            })
        payload = {
            "segment_id": segment_id,
            "scene_id": "S-OFFLINE",
            "asset_refs": {"characters": ["C-OFFLINE"], "scene_id": "S-OFFLINE"},
            "metadata": {"target_duration_sec": duration, "aspect_ratio": "16:9"},
            "shots": shots,
        }
        path = self.project / "layer2" / f"layer2-{segment_id}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _make_clip(self, segment_id: str, seconds: float):
        target = self.project / "videos" / f"{segment_id}.mp4"
        result = subprocess.run([
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=320x180:r=10:d={seconds:.3f}",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target),
        ], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return target

    def test_two_segment_offline_production_path(self):
        """A real CLI path must preserve stage gates and produce verifiable delivery evidence."""
        from PIL import Image

        (self.project / "project.md").write_text("offline fixture", encoding="utf-8")
        ref = self.project / "images" / "reference.png"
        Image.new("RGB", (16, 16), "blue").save(ref)
        bible = self.project / "adapt" / "bible.json"
        bible.write_text(json.dumps({
            "characters": [{"id": "C-OFFLINE", "name": "Offline", "reference_image": str(ref)}],
            "locations": [{"id": "S-OFFLINE", "name": "Offline", "reference_image": str(ref)}],
        }), encoding="utf-8")

        # Stages 0-3 are explicit approvals. Stage 4 binds both Layer 2 files and mapped panels.
        for stage in range(4):
            self._approve(stage)
        layer_files = [self._make_layer2("EP01-S01", 7), self._make_layer2("EP01-S02", 9)]
        self._approve(4)

        segments = self.project / "segments-ep01.json"
        prompts = self.project / "prompts-ep01.md"
        result = run_cli(STORYBOARD / "compile_layer2_to_h3.py", "--layer2",
            *[str(path) for path in layer_files], "--bible", str(bible), "--episode", "EP01",
            "--project-root", str(self.project), "--output-md", str(prompts),
            "--output-segments", str(segments), cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        compiled = json.loads(segments.read_text(encoding="utf-8"))
        self.assertEqual(len(compiled["segments"]), 2)
        self.assertEqual([s["segment_id"] for s in compiled["segments"]], ["EP01-S01", "EP01-S02"])

        # Stage 5 approval is required; submit is invoked with no token and its HTTP boundary is forbidden.
        self._approve(5)
        submit_dir = self.project / "submit-output"
        args = ["submit_h3_segments.py", "--segments", str(segments), "--dry-run",
                "--root-dir", str(self.project), "--output-dir", str(submit_dir)]
        with patch.object(sys, "argv", args), patch.object(submit, "find_token", return_value=None), \
             patch.object(submit, "get_gpu_vram", return_value=None), \
             patch.object(submit, "call_api", side_effect=AssertionError("dry-run attempted API call")):
            self.assertEqual(submit.main(), 0)
        self.assertFalse(submit_dir.exists(), "dry-run must not create submission/output state")

        for segment in compiled["segments"]:
            seconds = float(segment["metadata"]["effective_duration_sec"])
            self._make_clip(segment["segment_id"], seconds)

        qa_json = self.project / "videos" / "qa-report.json"
        qa_md = self.project / "videos" / "qa-report.md"
        result = run_cli(STORYBOARD / "verify_video_shot.py", "--segments", str(segments),
            "--videos-dir", str(self.project / "videos"), "--out-json", str(qa_json),
            "--out-report", str(qa_md), cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr +
                         (qa_json.read_text(encoding="utf-8") if qa_json.exists() else ""))
        report = json.loads(qa_json.read_text(encoding="utf-8"))
        self.assertEqual(set(report["expected_segments"]), {s["segment_id"] for s in compiled["segments"]})
        self.assertFalse(report["unproduced_segments"])
        self.assertTrue(all(row.get("video_file") and row.get("video_sha256") and row.get("passed") is True
                            for row in report["results"]))
        self._approve(6)
        self.assertFalse(state.stage6_errors(self.project))

        final = self.project / "final" / "final-ep01.mp4"
        manifest = self.project / "final" / "delivery-final-ep01.json"
        result = run_cli(STORYBOARD / "assemble_episode.py", "--segments", str(segments),
            "--videos-dir", str(self.project / "videos"), "--output", str(final),
            "--manifest", str(manifest), "--audio-mode", "native_sub", "--no-burn-subtitles",
            cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        delivery = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(delivery["delivery_status"], "complete")
        self.assertEqual(delivery["expected_segment_count"], 2)
        self.assertEqual(delivery["assembled_segment_count"], 2)
        self.assertTrue(delivery["final_decode_ok"])
        self._approve(7)
        self.assertFalse(state.stage7_errors(self.project))


if __name__ == "__main__":
    unittest.main()
