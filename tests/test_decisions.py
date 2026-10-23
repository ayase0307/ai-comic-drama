"""decisions.json 與 `h3d decide`：使用者定案必須帶原話、日期與適用階段。"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import decisions  # noqa: E402
import h3d  # noqa: E402
import init_project  # noqa: E402


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_decide_records_rule_quote_date_and_stages(self):
        entry = decisions.decide(self.root, "aspect_ratio", "16:9", "比例用 16:9", date="2026-10-21")
        data = json.loads((self.root / "decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        saved = data["decisions"][0]
        self.assertEqual(saved["id"], "aspect_ratio")
        self.assertEqual(saved["value"], "16:9")
        self.assertEqual(saved["source"], {"quote": "比例用 16:9", "date": "2026-10-21", "by": "user"})
        self.assertEqual(saved["stages"], decisions.KNOWN_DECISIONS["aspect_ratio"]["stages"])
        self.assertIn("16:9", saved["rule"])
        self.assertEqual(entry["id"], "aspect_ratio")

    def test_quote_is_mandatory(self):
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "style", "半寫實", "  ")
        self.assertFalse((self.root / "decisions.json").exists())

    def test_custom_decision_requires_stages(self):
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "voice_engine", "edge-tts", "配音用 edge")
        entry = decisions.decide(self.root, "voice_engine", "edge-tts", "配音用 edge", stages=[7])
        self.assertEqual(entry["stages"], [7])

    def test_redeciding_keeps_history(self):
        decisions.decide(self.root, "style", "平塗", "先用平塗")
        entry = decisions.decide(self.root, "style", "半寫實", "改半寫實")
        self.assertEqual(entry["value"], "半寫實")
        self.assertEqual(len(entry["history"]), 1)
        self.assertEqual(entry["history"][0]["value"], "平塗")
        self.assertEqual(len(decisions.load(self.root)["decisions"]), 1)

    def test_acceptance_policy_recommended_expands_and_is_validated(self):
        entry = decisions.decide(self.root, "acceptance_policy", "recommended", "照建議")
        self.assertIn("extra_person", entry["value"]["rerun_on"])
        self.assertIn("paper_text", entry["value"]["accept"])
        policy, decided = decisions.acceptance_policy(self.root)
        self.assertTrue(decided)
        self.assertEqual(policy["rerun_on"], entry["value"]["rerun_on"])
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "acceptance_policy",
                             '{"rerun_on": ["not_a_code"], "accept": []}', "亂寫")
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "acceptance_policy",
                             '{"rerun_on": ["paper_text"], "accept": ["paper_text"]}', "矛盾")

    def test_policy_falls_back_to_recommended_but_says_so(self):
        policy, decided = decisions.acceptance_policy(self.root)
        self.assertFalse(decided)
        self.assertEqual(policy["rerun_on"], decisions.RECOMMENDED_ACCEPTANCE_POLICY["rerun_on"])

    def test_missing_for_stage_follows_required_by(self):
        self.assertEqual(decisions.missing_for_stage(self.root, 1), [])
        self.assertEqual(set(decisions.missing_for_stage(self.root, 2)), {"style", "aspect_ratio", "design_engine"})
        decisions.decide(self.root, "style", "半寫實", "半寫實")
        self.assertNotIn("style", decisions.missing_for_stage(self.root, 6))
        self.assertIn("acceptance_policy", decisions.missing_for_stage(self.root, 6))

    def test_corrupt_file_is_reported_not_silently_ignored(self):
        (self.root / "decisions.json").write_text('{"schema_version": 1, "decisions": [{"id": "x"}]}', encoding="utf-8")
        with self.assertRaises(decisions.DecisionError):
            decisions.load(self.root)

    def test_h3d_decide_cli_accepts_root_before_or_after(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = h3d.main(["--root", str(self.root), "decide", "style", "半寫實", "--quote", "半寫實就好"])
        self.assertEqual(code, 0)
        with redirect_stdout(io.StringIO()):
            code = h3d.main(["decide", "aspect_ratio", "16:9", "--quote", "16:9", "--root", str(self.root)])
        self.assertEqual(code, 0)
        ids = [d["id"] for d in decisions.load(self.root)["decisions"]]
        self.assertEqual(ids, ["style", "aspect_ratio"])
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = h3d.main(["decide", "style", "卡通", "--root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("原話", err.getvalue())

    def test_init_project_creates_empty_decisions_file(self):
        files = init_project.build_files("demo", 2, "demo")
        self.assertIn("decisions.json", files)
        self.assertEqual(json.loads(files["decisions.json"]), {"schema_version": 1, "decisions": []})
        self.assertEqual(decisions.validate(json.loads(files["decisions.json"])), [])

    def test_schema_file_lists_the_same_issue_codes(self):
        schema = json.loads((ROOT / "references" / "schemas" / "decisions.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$defs"]["issueCode"]["enum"], list(decisions.ISSUE_CODES))
        self.assertEqual(set(schema["$defs"]["decision"]["required"]), {"id", "rule", "value", "source", "stages"})


if __name__ == "__main__":
    unittest.main()
