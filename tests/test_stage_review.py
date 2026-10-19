import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "storyboard"))

import build_stage_review as review
import compile_layer2_to_h3 as compiler
import submit_h3_segments as submit
import project_state as ps


class StageReviewGateTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        for d in ("review", "images", "panels", "layer2", "videos", "final"):
            (self.root / d).mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fake_or_unmapped_png_does_not_pass_stage4(self):
        (self.root / "layer2" / "layer2-seg1.json").write_text(json.dumps({
            "segment_id": "seg1", "shots": [{"shot_id": "S1"}]
        }), encoding="utf-8")
        (self.root / "images" / "grid-unrelated.png").write_bytes(b"not a png")
        passed, errors, _ = review.build_stage_4(self.root, ps.load_state(self.root))
        self.assertFalse(passed)
        self.assertTrue(errors)

    def test_qwen_layer2_grid_and_panel_layout_maps_to_current_shots(self):
        from PIL import Image

        layer_dir = self.root / "layer2"
        (layer_dir / "panels").mkdir()
        panel = layer_dir / "panels" / "panel-01-SH01.png"
        Image.new("RGB", (3, 3), "white").save(panel)
        (layer_dir / "layer2-seg1.json").write_text(json.dumps({
            "segment_id": "seg1", "shots": [{"shot_id": "SH01", "sketch_file": "panels/panel-01-SH01.png"}]
        }), encoding="utf-8")
        matched, errors = ps.stage4_artifacts(self.root)
        self.assertFalse(errors)
        self.assertEqual(matched, [panel.resolve()])

    def test_stage6_and_stage7_scope_each_episode_to_its_segments_file(self):
        from PIL import Image

        (self.root / "project.md").write_text("pitch", encoding="utf-8")
        reference = self.root / "images" / "ref.png"
        Image.new("RGB", (3, 3), "white").save(reference)
        segments = {}
        videos = {}
        for episode in ("ep01", "ep02"):
            p = self.root / f"segments-{episode}.json"
            sid = episode.upper() + "-S01"
            p.write_text(json.dumps({"segments": [{"segment_id": sid,
                "reference_images": [{"path": "images/ref.png"}]}]}), encoding="utf-8")
            segments[episode] = (p, sid)
            panel = self.root / "layer2" / "panels" / f"panel-01-{sid}.png"
            panel.parent.mkdir(exist_ok=True)
            Image.new("RGB", (3, 3), "white").save(panel)
            (self.root / "layer2" / f"layer2-{sid}.json").write_text(json.dumps({
                "segment_id": sid, "shots": [{"shot_id": "SH01", "sketch_file": f"panels/{panel.name}"}]
            }), encoding="utf-8")
            video = self.root / "videos" / f"{sid}.mp4"
            video.write_bytes((sid + " video").encode("utf-8"))
            videos[episode] = video

        state = ps.load_state(self.root)
        for stage in range(6):
            ps.mark_awaiting_review(self.root, state, stage)
            self.assertTrue(ps.approve_stage(self.root, stage, "confirmed"), f"stage-{stage}")
            state = ps.load_state(self.root)

        def report_for(episode):
            p, sid = segments[episode]
            video = videos[episode]
            return {
                "source_segments_file": str(p.resolve()),
                "source_segments_sha256": ps.sha256_file(p),
                "expected_segments": [sid], "unproduced_segments": [],
                "results": [{"segment_id": sid, "video_file": str(video.resolve()),
                             "video_sha256": ps.sha256_file(video), "passed": True}],
            }

        with patch.object(ps, "_ffprobe", return_value={"duration": 1.0}):
            qa_path = self.root / "videos" / "qa-report.json"
            qa_path.write_text(json.dumps(report_for("ep01")), encoding="utf-8")
            self.assertFalse(ps.stage6_errors(self.root))
            qa_path.write_text(json.dumps(report_for("ep02")), encoding="utf-8")
            self.assertFalse(ps.stage6_errors(self.root))

            for episode in ("ep01", "ep02"):
                p, sid = segments[episode]
                source_video = videos[episode]
                processed = self.root / "videos" / f"processed-{sid}.mp4"
                processed.write_bytes(b"processed-" + sid.encode("utf-8"))
                final = self.root / "final" / f"{episode}.mp4"
                final.write_bytes((episode * 2048).encode("utf-8"))
                manifest = {
                    "delivery_status": "complete", "source_segments_file": str(p.resolve()),
                    "source_segments_sha256": ps.sha256_file(p), "expected_segments": [sid],
                    "expected_segment_count": 1, "assembled_segment_count": 1,
                    "assembled_segments": [{"segment_id": sid,
                        "source_video_file": str(source_video.resolve()), "source_video_sha256": ps.sha256_file(source_video),
                        "processed_video_file": str(processed.resolve()), "processed_video_sha256": ps.sha256_file(processed)}],
                    "final_video": str(final.resolve()), "final_sha256": ps.sha256_file(final), "final_decode_ok": True,
                }
                (self.root / "final" / f"delivery-{episode}.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(ps.stage7_errors(self.root))

            # If episode 2 grows a segment after its manifest was built, its delivery is stale.
            p, sid = segments["ep02"]
            p.write_text(json.dumps({"segments": [{"segment_id": sid}, {"segment_id": "EP02-S02"}]}), encoding="utf-8")
            self.assertTrue(ps.stage7_errors(self.root))

    def test_compile_requires_current_stage4_approval_even_with_grid(self):
        self.assertFalse(compiler.verify_stage4_gate(self.root))

    def test_compile_cli_after_stage4_approval_writes_outputs_and_rejects_stale_edit(self):
        from PIL import Image

        (self.root / "project.md").write_text("pitch", encoding="utf-8")
        state = ps.load_state(self.root)
        for stage in range(4):
            ps.mark_awaiting_review(self.root, state, stage)
            self.assertTrue(ps.approve_stage(self.root, stage, "confirmed"))
            state = ps.load_state(self.root)
        layer_dir = self.root / "layer2"
        (layer_dir / "panels").mkdir()
        Image.new("RGB", (3, 3), "white").save(layer_dir / "panels" / "panel-01-SH01.png")
        layer = layer_dir / "layer2-seg1.json"
        layer.write_text(json.dumps({
            "segment_id": "EP01-S01", "scene_id": "S01",
            "metadata": {"target_duration_sec": 7, "aspect_ratio": "16:9"},
            "shots": [{"shot_id": "SH01", "duration": 7,
                "start_time": 0, "end_time": 7,
                "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "movement": "static"},
                "action_and_performance": {"action_stages": ["A", "B", "C"]},
                "dialogue_and_audio": {"has_dialogue": False}}]
        }), encoding="utf-8")
        # Stage 4 review needs the final Layer 2 content and its mapped Qwen panel.
        state = ps.load_state(self.root)
        ps.mark_awaiting_review(self.root, state, 4)
        self.assertTrue(ps.approve_stage(self.root, 4, "confirmed"))
        with patch.object(sys, "argv", ["compile_layer2_to_h3.py", "--layer2", str(layer),
                "--project-root", str(self.root), "--output-md", str(self.root / "prompts.md"),
                "--output-segments", str(self.root / "segments-ep01.json"), "--episode", "EP01"]):
            self.assertEqual(compiler.main(), 0)
        self.assertTrue((self.root / "prompts.md").exists())
        self.assertTrue((self.root / "segments-ep01.json").exists())
        layer.write_text(layer.read_text(encoding="utf-8").replace('"duration": 7', '"duration": 6'), encoding="utf-8")
        self.assertFalse(compiler.verify_stage4_gate(self.root))

    def test_submit_requires_stage5_approval_and_matching_segment_inputs(self):
        self.assertFalse(submit.verify_stage5_gate(self.root, self.root / "segments-ep01.json"))

    def test_submit_accepts_approved_stage5_batch_and_blocks_changed_reference(self):
        from PIL import Image

        (self.root / "project.md").write_text("pitch", encoding="utf-8")
        (self.root / "images" / "ref.png").parent.mkdir(exist_ok=True)
        Image.new("RGB", (3, 3), "white").save(self.root / "images" / "ref.png")
        layer_dir = self.root / "layer2"
        (layer_dir / "panels").mkdir()
        Image.new("RGB", (3, 3), "white").save(layer_dir / "panels" / "panel-01-SH01.png")
        (layer_dir / "layer2-seg1.json").write_text(json.dumps({
            "segment_id": "seg1", "shots": [{"shot_id": "SH01", "sketch_file": "panels/panel-01-SH01.png"}]
        }), encoding="utf-8")
        segments = self.root / "segments-ep01.json"
        segments.write_text(json.dumps({"segments": [{
            "segment_id": "seg1", "reference_images": [{"path": "images/ref.png"}]
        }]}), encoding="utf-8")
        state = ps.load_state(self.root)
        for stage in range(6):
            ps.mark_awaiting_review(self.root, state, stage)
            self.assertTrue(ps.approve_stage(self.root, stage, "confirmed"), f"stage-{stage}")
            state = ps.load_state(self.root)
        self.assertTrue(submit.verify_stage5_gate(self.root, segments))
        Image.new("RGB", (4, 4), "black").save(self.root / "images" / "ref.png")
        self.assertFalse(submit.verify_stage5_gate(self.root, segments))

    def test_stage6_missing_qa_is_blocked(self):
        (self.root / "videos" / "seg1.mp4").write_bytes(b"placeholder")
        passed, errors, _ = review.build_stage_6(self.root, ps.load_state(self.root))
        self.assertFalse(passed)
        self.assertTrue(errors)

    def test_stage6_hash_mismatch_or_unproduced_is_blocked(self):
        video = self.root / "videos" / "seg1.mp4"
        video.write_bytes(b"video")
        (self.root / "videos" / "qa-report.json").write_text(json.dumps({
            "expected_segments": ["seg1", "seg2"],
            "unproduced_segments": ["seg2"],
            "results": [{"segment_id": "seg1", "video_file": str(video), "video_sha256": "bad", "passed": True}]
        }), encoding="utf-8")
        passed, errors, _ = review.build_stage_6(self.root, ps.load_state(self.root))
        self.assertFalse(passed)
        self.assertTrue(errors)

    def test_stage7_requires_manifest_and_decodable_final(self):
        final = self.root / "final" / "episode.mp4"
        final.write_bytes(b"x")
        passed, errors, _ = review.build_stage_7(self.root, ps.load_state(self.root))
        self.assertFalse(passed)
        self.assertTrue(errors)


class BudgetPanelTests(unittest.TestCase):
    def test_over_target_is_flagged_but_not_an_error(self):
        out = review.render_budget([{"label": "EP01", "target": 90, "parts": [("EP01-S01-a", 100), ("EP01-S01-b", 30)]}], "x")
        self.assertIn("bud-note over", out)
        self.assertIn("+44%", out)

    def test_within_band_is_ok_and_shots_render(self):
        out = review.render_budget([{"label": "EP01", "target": 90, "parts": [("a", 95)]}], "x")
        self.assertIn("bud-note ok", out)
        shots = [{"shot_id": "SH01", "duration": 3, "dramatic_beat_type": "Dramatic_Core",
                  "action_and_performance": {"action_stages": ["①施力點：握刀"]},
                  "dialogue_and_audio": {"has_dialogue": False}}]
        html_out = review.render_shots(shots)
        self.assertIn("SH01", html_out)
        self.assertIn("閉唇無台詞", html_out)


if __name__ == "__main__":
    unittest.main()

