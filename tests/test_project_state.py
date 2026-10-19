import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_state as ps


class ProjectStateTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        for name in ("review", "source", "adapt", "images", "layer2", "videos", "final"):
            (self.root / name).mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_numeric_approved_without_snapshot_migrates_as_draft(self):
        (self.root / "project-state.json").write_text(json.dumps({
            "current_stage": 5,
            "stages": {str(i): {"status": "approved"} for i in range(5)}
        }), encoding="utf-8")
        state = ps.load_state(self.root)
        self.assertEqual(set(state["stages"]), {f"stage-{i}" for i in range(8)})
        self.assertEqual(state["stages"]["stage-4"]["status"], "draft")
        self.assertFalse(ps.is_approved(self.root, 4))

    def test_approval_binds_snapshot_and_changes_make_it_stale(self):
        (self.root / "project.md").write_text("pitch v1", encoding="utf-8")
        state = ps.load_state(self.root)
        ps.mark_awaiting_review(self.root, state, 0)
        self.assertTrue(ps.approve_stage(self.root, 0, "confirmed"))
        self.assertTrue(ps.is_approved(self.root, 0))
        (self.root / "project.md").write_text("pitch v2", encoding="utf-8")
        self.assertFalse(ps.is_approved(self.root, 0))

    def test_state_is_saved_only_at_canonical_path(self):
        ps.save_state(self.root, ps.initial_state("demo", "demo"))
        self.assertTrue((self.root / "review" / "project-state.json").exists())
        self.assertFalse((self.root / "project-state.json").exists())

    def test_valid_project_can_advance_through_all_eight_stages(self):
        from PIL import Image

        (self.root / "project.md").write_text("pitch", encoding="utf-8")
        (self.root / "adapt" / "source.json").write_text("{}", encoding="utf-8")
        (self.root / "adapt" / "bible.json").write_text("{}", encoding="utf-8")
        (self.root / "adapt" / "character-bible.md").write_text("characters", encoding="utf-8")
        (self.root / "assets.md").write_text("assets", encoding="utf-8")
        Image.new("RGB", (2, 2), "white").save(self.root / "images" / "character.png")
        (self.root / "script-ep01.md").write_text("script", encoding="utf-8")
        (self.root / "handoff-ep01.json").write_text("{}", encoding="utf-8")

        layer_dir = self.root / "layer2"
        (layer_dir / "panels").mkdir()
        panel = layer_dir / "panels" / "panel-01-SH01.png"
        Image.new("RGB", (2, 2), "white").save(panel)
        (layer_dir / "layer2-EP01-S01.json").write_text(json.dumps({
            "segment_id": "EP01-S01", "shots": [{"shot_id": "SH01", "sketch_file": "panels/panel-01-SH01.png"}]
        }), encoding="utf-8")

        segments = self.root / "segments-ep01.json"
        segments.write_text(json.dumps({"segments": [{
            "segment_id": "EP01-S01", "reference_images": [{"path": "images/character.png"}]
        }]}), encoding="utf-8")

        video = self.root / "videos" / "EP01-S01.mp4"
        video.write_bytes(b"segment video")
        source_hash = ps.sha256_file(segments)
        (self.root / "videos" / "qa-report.json").write_text(json.dumps({
            "source_segments_file": str(segments.resolve()), "source_segments_sha256": source_hash,
            "expected_segments": ["EP01-S01"], "unproduced_segments": [],
            "results": [{"segment_id": "EP01-S01", "video_file": str(video.resolve()),
                         "video_sha256": ps.sha256_file(video), "passed": True}]
        }), encoding="utf-8")

        final = self.root / "final" / "episode.mp4"
        final.write_bytes(b"assembled video" * 256)
        processed = self.root / "videos" / "processed-EP01-S01.mp4"
        processed.write_bytes(b"processed video")
        (self.root / "final" / "delivery-episode.json").write_text(json.dumps({
            "delivery_status": "complete", "source_segments_file": str(segments.resolve()),
            "source_segments_sha256": source_hash, "expected_segments": ["EP01-S01"],
            "expected_segment_count": 1, "assembled_segment_count": 1,
            "assembled_segments": [{"segment_id": "EP01-S01", "source_video_file": str(video.resolve()),
                                     "source_video_sha256": ps.sha256_file(video),
                                     "processed_video_file": str(processed.resolve()),
                                     "processed_video_sha256": ps.sha256_file(processed)}],
            "final_video": str(final.resolve()), "final_sha256": ps.sha256_file(final), "final_decode_ok": True
        }), encoding="utf-8")

        with patch.object(ps, "_ffprobe", return_value={"duration": 2.0}):
            for stage in range(8):
                state = ps.load_state(self.root)
                ps.mark_awaiting_review(self.root, state, stage)
                self.assertTrue(ps.approve_stage(self.root, stage, "confirmed"), f"stage-{stage}")
            self.assertTrue(ps.is_approved(self.root, 7))

            # A reapproved upstream stage must not resurrect an older downstream approval.
            (self.root / "adapt" / "bible.json").write_text('{"revision": 2}', encoding="utf-8")
            state = ps.load_state(self.root)
            ps.mark_awaiting_review(self.root, state, 1)
            self.assertTrue(ps.approve_stage(self.root, 1, "revised"))
            self.assertFalse(ps.is_approved(self.root, 4))


if __name__ == "__main__":
    unittest.main()

