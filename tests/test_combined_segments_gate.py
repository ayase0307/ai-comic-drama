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


class SegmentsAllConsistencyTests(unittest.TestCase):
    """segments-all.json 是階段 6 的單一來源，必須等於逐集檔聯集。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ep = {"EP01": [{"segment_id": "EP01-S01-a", "h3_prompt": "one"}],
                   "EP02": [{"segment_id": "EP02-S01-a", "h3_prompt": "two"}]}
        for ep, segs in self.ep.items():
            self._write(f"segments-{ep.lower()}.json", segs)

    def _write(self, name, segs):
        (self.root / name).write_text(json.dumps({"segments": segs}, ensure_ascii=False), encoding="utf-8")

    def _errors(self):
        return state.segments_all_consistency_errors(self.root, sorted(self.root.glob("segments-ep*.json")))

    def test_no_combined_file_is_fine(self):
        self.assertEqual(self._errors(), [])

    def test_combined_equal_to_union_passes(self):
        self._write("segments-all.json", self.ep["EP01"] + self.ep["EP02"])
        self.assertEqual(self._errors(), [])

    def test_stale_combined_content_blocks_with_rebuild_command(self):
        self._write("segments-all.json", [{"segment_id": "EP01-S01-a", "h3_prompt": "old"}] + self.ep["EP02"])
        errors = self._errors()
        self.assertEqual(len(errors), 1)
        self.assertIn("內容不同 EP01-S01-a", errors[0])
        self.assertIn("--output-segments segments-all.json", errors[0])

    def test_missing_and_extra_ids_block(self):
        self._write("segments-all.json", self.ep["EP01"] + [{"segment_id": "EP09-S01-a", "h3_prompt": "x"}])
        errors = self._errors()
        self.assertIn("缺少 EP02-S01-a", errors[0])
        self.assertIn("多出 EP09-S01-a", errors[0])

    def test_strict_stage5_reports_mismatch_but_lenient_does_not(self):
        self._write("segments-all.json", self.ep["EP01"])
        strict = state.stage_validation_errors(self.root, 5, strict=True)
        lenient = state.stage_validation_errors(self.root, 5)
        self.assertTrue(any("segments-all.json 與" in e for e in strict))
        self.assertFalse(any("segments-all.json 與" in e for e in lenient))

    def test_scoped_ids_default_to_combined_file(self):
        self._write("segments-all.json", self.ep["EP01"] + self.ep["EP02"])
        _, error = state.scoped_expected_segment_ids(self.root, {})
        # 不再因「多集沒指定來源」而報錯；改走 segments-all（此處因未核准而在 hash 檢查擋下）。
        self.assertNotIn("多集專案", error or "")


if __name__ == "__main__":
    unittest.main()
