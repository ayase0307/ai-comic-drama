import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import next_step as ns  # noqa: E402
import project_state as ps  # noqa: E402
from audit_refs_and_segments import audit_refs_and_subjects  # noqa: E402


def _tmp(case):
    root = Path(tempfile.mkdtemp())
    case.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
    return root


class NextStepCommands(unittest.TestCase):
    def test_init_command_has_no_episode_flag(self):
        root = _tmp(self)  # 沒有 project-state：走 uninitialized 分支
        res = ns.plan(root)
        self.assertEqual(res["status"], "uninitialized")
        self.assertNotIn("--episodes", res["next_command"])

    def test_collect_command_has_no_placeholder(self):
        root = _tmp(self)
        ps.save_state(root, ps.initial_state("t", "p"))
        (root / "segments-all.json").write_text(json.dumps([{"segment_id": "A"}]), encoding="utf-8")
        videos = root / "videos"
        videos.mkdir()
        (videos / "_fv-job-ledger.json").write_text(json.dumps({"jobs": [
            {"segment_id": "A", "job_id": "J1", "status": "running"}]}), encoding="utf-8")
        res = ns.plan(root)
        self.assertIn("collect --segments segments-all.json", res["next_command"])
        self.assertNotIn("<", res["next_command"])


class NarrationDefault(unittest.TestCase):
    def test_external_narration_conflict_flagged_without_metadata_policy(self):
        # 沒寫 narration_policy 時，預設（short-offscreen-h3）與 external 都會擋住 <d> 重複台詞。
        line = "我們先走吧"
        seg = {
            "prompt": f"<d>[Chinese] {line}</d>",
            "external_narration": [{"line": line, "language": "Chinese"}],
        }
        result = audit_refs_and_subjects(seg, project_root=None, strict=False)
        text = json.dumps(result, ensure_ascii=False)
        self.assertIn("E24", text)


class GateBypassRecord(unittest.TestCase):
    def test_bypass_is_recorded_and_stamped(self):
        root = _tmp(self)
        ps.save_state(root, ps.initial_state("t", "p"))
        self.assertTrue(ps.record_gate_bypass(root, "stage-4", "test"))
        raw = json.loads((root / "review" / "project-state.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["gate_bypasses"][0]["gate"], "stage-4")
        self.assertEqual(ps.state_integrity(root), "ok")

    def test_no_state_file_means_no_record(self):
        root = _tmp(self)
        self.assertFalse(ps.record_gate_bypass(root, "stage-4", "test"))
        self.assertFalse((root / "review" / "project-state.json").exists())


if __name__ == "__main__":
    unittest.main()
