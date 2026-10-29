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

from unittest import mock as _mock  # noqa: E402
import sys as _sys, pathlib as _pl  # noqa: E401,E402
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import _content_gate  # noqa: E402,F401  (確保 scripts 在 sys.path)

_content_gate_off = _mock.patch("stage_content_checks.content_errors", new=lambda root, stage: [])



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

    def _scoped_setup(self, tagged_stages):
        patcher = patch.object(ps, "stage_validation_errors", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "project.md").write_text("- genre：x\n- aspect_ratio：9:16\n", encoding="utf-8")
        (self.root / "decisions.json").write_text(json.dumps({"decisions": [
            {"id": "aspect_ratio", "value": "9:16", "stages": tagged_stages}]}), encoding="utf-8")
        (self.root / "adapt" / "source.json").write_text("{}", encoding="utf-8")
        (self.root / "adapt" / "bible.json").write_text("{}", encoding="utf-8")
        (self.root / "adapt" / "character-bible.md").write_text("characters", encoding="utf-8")
        for stage in (0, 1):
            ps.mark_awaiting_review(self.root, ps.load_state(self.root), stage)
            ok, why = ps.approve_stage_detailed(self.root, stage, "ok"); self.assertTrue(ok, why)
        (self.root / "project.md").write_text("- genre：x\n- aspect_ratio：16:9\n", encoding="utf-8")
        ps.mark_awaiting_review(self.root, ps.load_state(self.root), 0)
        self.assertTrue(ps.approve_stage(self.root, 0, "改16:9"))

    def test_stage0_decision_not_tagged_to_stage_keeps_its_approval(self):
        self._scoped_setup([2, 4])
        self.assertTrue(ps.is_approved(self.root, 1))

    def test_stage0_decision_tagged_to_stage_invalidates_it(self):
        self._scoped_setup([1, 2])
        self.assertFalse(ps.is_approved(self.root, 1))

    def test_stage0_other_change_still_invalidates(self):
        self._scoped_setup([2])
        (self.root / "project.md").write_text("- genre：y\n- aspect_ratio：16:9\n", encoding="utf-8")
        ps.mark_awaiting_review(self.root, ps.load_state(self.root), 0)
        self.assertTrue(ps.approve_stage(self.root, 0, "改題材"))
        self.assertFalse(ps.is_approved(self.root, 1))

    def test_state_is_saved_only_at_canonical_path(self):
        ps.save_state(self.root, ps.initial_state("demo", "demo"))
        self.assertTrue((self.root / "review" / "project-state.json").exists())
        self.assertFalse((self.root / "project-state.json").exists())

    @_content_gate_off  # 測的是下游階段，階段 0–3 內容門禁另有測試

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
            "segment_id": "EP01-S01", "segment_end_state": {"planned_final_state": {"pose": "standing"}}, "reference_images": [{"path": "images/character.png"}]
        }]}), encoding="utf-8")

        video = self.root / "videos" / "EP01-S01.mp4"
        video.write_bytes(b"segment video")
        source_hash = ps.sha256_file(segments)
        (self.root / "videos" / "qa-report.json").write_text(json.dumps({
            "source_segments_file": str(segments.resolve()), "source_segments_sha256": source_hash,
            "expected_segments": ["EP01-S01"], "unproduced_segments": [],
            "evidence": {"verdict": "VERIFIED", "produced": 1, "expected": 1,
                         "failed": 0, "unverified_segments": []},
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

    def test_stage5_snapshot_covers_catalog_acks(self):
        (self.root / "segments-ep01.json").write_text("[]", encoding="utf-8")
        ack_path = self.root / "review" / "catalog-acks.json"
        ack_path.parent.mkdir(parents=True, exist_ok=True)
        ack_path.write_text('{"acks": [{"id": "F-STILL-ENDING"}]}', encoding="utf-8")
        # approve_stage() 的判定就是 entry["approval_snapshot"] != stage_snapshot(...)，
        # 所以快照變了即等於核准失效（不需要在單元測試裡湊齊完整專案）。
        before = ps.stage_snapshot(self.root, 5)
        ack_path.write_text('{"acks": [{"id": "F-NEGATION"}]}', encoding="utf-8")
        after = ps.stage_snapshot(self.root, 5)
        self.assertNotEqual(ps.snapshot_fingerprint(before), ps.snapshot_fingerprint(after),
                            "改動 ack 必須讓 stage-5 快照失效")


if __name__ == "__main__":
    unittest.main()

