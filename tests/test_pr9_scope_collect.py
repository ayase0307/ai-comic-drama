import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from scripts.storyboard import submit_h3_segments as submit
import scripts.next_step as ns

API = "https://api.example/freevideo/agent/v1"


class CollectLatest(unittest.TestCase):
    def test_only_latest_job_per_segment(self):
        root = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        out = root / "videos"; out.mkdir()
        ledger = out / "_fv-job-ledger.json"
        ledger.write_text(json.dumps({"api_scope": API, "project": str(root.resolve()), "jobs": [
            {"id": "OLD", "segment_id": "S1", "status": "succeeded", "frames": 24},
            {"id": "NEW", "segment_id": "S1", "status": "running"}]}))
        seen = []
        def fake(api_url, token, method, path, body=None, timeout=600):
            seen.append(path)
            return {"job": {"id": "NEW", "status": "running"}}
        with mock.patch.object(submit, "call_api", side_effect=fake):
            s = submit.collect_jobs(API, "t", ledger, out)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith("/jobs/NEW"))
        self.assertEqual(s["still_running"], 1)


class ScopeTests(unittest.TestCase):
    def _root(self, scope):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        (root / "segments-ep01.json").write_text(json.dumps([{"segment_id": "A"}]))
        (root / "segments-all.json").write_text(json.dumps([{"segment_id": "A"}, {"segment_id": "B"}]))
        (root / "decisions.json").write_text(json.dumps({"schema_version": 1, "decisions": [
            {"id": "delivery_scope", "rule": "x", "value": scope, "stages": [6], "source": {"quote": "q", "date": "2026-10-25", "by": "user"}}]}))
        return root

    def test_files_prefer_all(self):
        root = self._root({})
        self.assertEqual([f.name for f in ns._segment_files(root)], ["segments-all.json"])

    def test_no_video_blocks(self):
        root = self._root({"no_video": True})
        res = {"blocked_on": [], "action": "", "next_command": "x", "read": []}
        out = ns._stage6_work(res, root)
        self.assertIsNone(out["next_command"])
        self.assertIn("no_video", out["blocked_on"][0])

    def test_trial_limits(self):
        root = self._root({"trial_segments": ["B"]})
        res = {"blocked_on": [], "action": "", "next_command": None, "read": []}
        out = ns._stage6_work(res, root)
        self.assertIn("--segment-id B", out["next_command"])
