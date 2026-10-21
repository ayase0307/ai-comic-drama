"""證據分級（I2）的回歸測試：沒有媒體就不得出現 PASS。"""
import unittest
from pathlib import Path

from scripts.storyboard import evidence


def _result(passed=True):
    return {"shot_id": "EP01-S01-a", "passed": passed, "issues": [] if passed else ["DURATION_MISMATCH"]}


class MediaEvidenceTests(unittest.TestCase):
    def test_no_media_is_unverified(self):
        summary = evidence.media_evidence([], ["EP01-S01-a", "EP01-S01-b"])
        self.assertEqual(summary["verdict"], evidence.UNVERIFIED)
        self.assertEqual(summary["produced"], 0)
        self.assertEqual(summary["expected"], 2)
        self.assertIn("不得作為通過依據", summary["note"])

    def test_all_produced_and_passed_is_verified(self):
        summary = evidence.media_evidence([_result(True), _result(True)])
        self.assertEqual(summary["verdict"], evidence.VERIFIED)
        self.assertEqual(summary["failed"], 0)

    def test_partial_when_some_segments_unproduced(self):
        summary = evidence.media_evidence([_result(True)], ["EP01-S02-a"])
        self.assertEqual(summary["verdict"], evidence.PARTIAL)
        self.assertIn("EP01-S02-a", summary["unverified_segments"])
        self.assertIn("1 段未產出", summary["note"])

    def test_partial_when_technical_failure(self):
        summary = evidence.media_evidence([_result(False)])
        self.assertEqual(summary["verdict"], evidence.PARTIAL)
        self.assertEqual(summary["failed"], 1)

    def test_partial_when_structural_issue(self):
        summary = evidence.media_evidence([_result(True)], structural_issues=["ambiguous:EP01-S03-a"])
        self.assertEqual(summary["verdict"], evidence.PARTIAL)

    def test_expected_total_can_exceed_produced(self):
        summary = evidence.media_evidence([_result(True)], [], expected_total=46)
        # 期望 46 段、只有 1 段進量測 → 不得判 VERIFIED
        self.assertEqual(summary["verdict"], evidence.PARTIAL)
        self.assertEqual(summary["expected"], 46)
        self.assertEqual(summary["unmeasured"], 45)

    def test_grade_results_defaults_to_measured_and_keeps_existing(self):
        items = evidence.grade_results([{"passed": True}, {"passed": True, "evidence_level": evidence.SOURCED}])
        self.assertEqual(items[0]["evidence_level"], evidence.MEASURED)
        self.assertEqual(items[1]["evidence_level"], evidence.SOURCED)

    def test_render_line_contains_verdict_and_counts(self):
        line = evidence.render_line(evidence.media_evidence([_result(True)], ["S2"]))
        self.assertIn("PARTIAL", line)
        self.assertIn("1/2", line)

    def test_levels_are_declared(self):
        self.assertEqual(set(evidence.LEVELS), {"measured", "sourced", "inferred"})
        for level in evidence.LEVELS:
            self.assertTrue(evidence.label(level))

    def test_continuity_warning_blocks_verified(self):
        summary = evidence.media_evidence([_result(True)], continuity_warnings=["dE76=96.6 日夜跳變"])
        self.assertEqual(summary["verdict"], evidence.PARTIAL)
        self.assertTrue(any("continuity" in item for item in summary["structural_issues"]))

    def test_inferred_check_cannot_be_verified(self):
        result = dict(_result(True), evidence_level=evidence.INFERRED)
        summary = evidence.media_evidence([result])
        self.assertEqual(summary["verdict"], evidence.PARTIAL)
        self.assertEqual(summary["lowest_level"], evidence.INFERRED)

    def test_stage6_gate_requires_verified_evidence(self):
        import json
        import tempfile
        from scripts import project_state as ps

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "videos").mkdir()
            (root / "videos" / "qa-report.json").write_text(json.dumps({
                "expected_segments": ["EP01-S01"],
                "unproduced_segments": ["EP01-S01"],
                "results": [],
                "evidence": {"verdict": "PARTIAL", "produced": 0, "expected": 1},
            }), encoding="utf-8")
            errors = ps.stage6_errors(root)
            self.assertTrue(any("證據等級" in error for error in errors), errors)

    def test_empty_report_does_not_claim_technical_pass(self):
        from scripts.storyboard import verify_video_shot as qa

        summary = evidence.media_evidence([], ["EP01-S01-a"])
        markdown = qa.render_markdown_report([], {"project_id": "P", "segment_id": "BATCH"}, [], evidence=summary)
        self.assertIn("NOTHING VERIFIED", markdown)
        self.assertNotIn("TECHNICAL CHECK PASSED", markdown)
        self.assertIn("UNVERIFIED", markdown)


if __name__ == "__main__":
    unittest.main()
