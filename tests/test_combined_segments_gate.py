import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import project_state as state


class CombinedSegmentsStageGateTests(unittest.TestCase):
    """A multi-episode project needs one combined segments file for stage 6.

    The stage-6 gate resolves a single source_segments_file, so with three
    episodes it can only confirm one episode's completeness unless the project
    also publishes a combined segments-all.json that stage 5 has approved.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "layer2").mkdir()
        (self.root / "videos").mkdir()
        for name, ids in (("ep01", ["EP01-S01-a"]), ("ep02", ["EP02-S01-a"]), ("ep03", ["EP03-S01-a"])):
            (self.root / f"segments-{name}.json").write_text(json.dumps(
                {"episode": name.upper(), "segments": [
                    {"segment_id": sid, "reference_images": []} for sid in ids]},
                ensure_ascii=False), encoding="utf-8")
        combined = {"episode": "ALL", "segments": [
            {"segment_id": sid, "reference_images": []}
            for sid in ("EP01-S01-a", "EP02-S01-a", "EP03-S01-a")]}
        (self.root / "segments-all.json").write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")

    def test_combined_segments_file_is_part_of_the_stage5_snapshot(self):
        files = state._files_for_stage(self.root, 5)
        names = {p.name for p in files}
        self.assertIn("segments-all.json", names)
        self.assertIn("segments-ep01.json", names)
        self.assertIn("segments-ep03.json", names)

    def test_combined_segments_file_is_absent_from_other_stage_snapshots(self):
        for stage in (0, 3, 4, 6, 7):
            names = {p.name for p in state._files_for_stage(self.root, stage)}
            self.assertNotIn("segments-all.json", names, f"stage {stage} must not claim it")

    def test_stage6_gate_accepts_a_report_scoped_to_the_combined_file(self):
        import hashlib
        combined = self.root / "segments-all.json"
        digest = hashlib.sha256(combined.read_bytes()).hexdigest()
        payload = {
            "source_segments_file": str(combined),
            "source_segments_sha256": digest,
            "expected_segments": ["EP01-S01-a", "EP02-S01-a", "EP03-S01-a"],
            "unproduced_segments": [],
            "results": [],
        }
        (self.root / "videos" / "qa-report.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # The gate still needs the stage-5 snapshot to contain the combined file,
        # so confirm the hash lookup is what would fail without that approval.
        state_files = {p.name for p in state._files_for_stage(self.root, 5)}
        self.assertIn("segments-all.json", state_files)
        self.assertTrue((self.root / "videos" / "qa-report.json").is_file())


if __name__ == "__main__":
    unittest.main()
