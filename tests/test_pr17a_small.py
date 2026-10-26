"""PR-17a：#147 驗收只比 sha、#151 kick 片語、#154 甩頭不算打擊、#155 複合 OTS 景別。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import continuity_lint  # noqa: E402
import decisions  # noqa: E402
import verdicts  # noqa: E402
from audit_refs_and_segments import lint_h3_prompt  # noqa: E402
from director_storyboard_assistant import auto_adapt_h3_loras  # noqa: E402
sys.path.insert(0, str(ROOT / "tests"))
from test_audit_refs_and_segments import make_prompt, authored_shots  # noqa: E402


class SizeRegexTests(unittest.TestCase):
    def test_composite_ots_is_one_token(self):
        m = continuity_lint.SIZE_RE.search("OTS_CU (85mm, 1.2m) of Shen")
        self.assertEqual(m.group(1), "OTS_CU")
        m = continuity_lint.SIZE_RE.search("CU (85mm, 1.2m) of Shen")
        self.assertEqual(m.group(1), "CU")

    def test_ots_dialogue_shot_not_flagged_too_far(self):
        seg = {"segment_id": "S1", "h3_prompt":
               "[Shot 1] OTS_MS (35mm, 2.5m) of Shen, a visible speaking character holds a static shot, "
               "the background behind him is empty."}
        out = continuity_lint.lint_shots([seg])
        self.assertFalse([w for w in out["warnings"] if "S3" in w])


class E16WhipTests(unittest.TestCase):
    def _errors(self, text):
        return lint_h3_prompt(make_prompt([text]), nominal_duration=9.0, authored_shots=authored_shots([9.0]))["errors"]

    def test_neck_whip_alone_is_not_a_strike(self):
        self.assertFalse(any("E16:" in e for e in self._errors("The serpent whips its neck toward the left and holds.")))

    def test_tail_whip_still_needs_feedback(self):
        self.assertTrue(any("E16:" in e for e in self._errors("The serpent whips its tail at Luonian, then watches.")))


class LoraKickTests(unittest.TestCase):
    def _names(self, action):
        spec = {"focal": "35mm", "pov": "objective", "action": action, "expression": "", "dialogue": "",
                "anchor_obj": "", "dramatic_beat_type": "Combat_Impact"}
        return [l["name"] for l in auto_adapt_h3_loras(spec)["loras"]]

    def test_heels_kick_out_does_not_attach_combat_lora(self):
        self.assertNotIn("H3_Combat_V2.safetensors", self._names("the beam hits his chest and his heels kick out behind him"))

    def test_real_kick_still_attaches(self):
        self.assertIn("H3_Combat_V2.safetensors", self._names("he lands a spinning kick on the guard"))
        self.assertIn("H3_Combat_V2.safetensors", self._names("she kicks him in the ribs"))


class VerdictShaTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "videos" / "qa").mkdir(parents=True)
        (self.root / "videos" / "qa" / "tile.jpg").write_bytes(b"jpg")
        decisions.decide(self.root, "acceptance_policy", "recommended", "照建議")

    def test_old_qa_report_hash_does_not_mark_same_video_stale(self):
        (self.root / "videos" / "A.mp4").write_bytes(b"video")
        verdicts.set_verdict(self.root, "A", "pass", "ok", ["videos/qa/tile.jpg"])
        qa = {"expected_segments": ["A"], "results": [
            {"segment_id": "A", "passed": True, "issues": [], "video_sha256": "sha256:" + "0" * 64}]}
        rows = verdicts.classify(self.root, qa_report=qa)
        self.assertFalse(rows["segments"]["A"].get("stale") if "segments" in rows else rows["A"].get("stale"))

    def test_really_changed_video_is_still_stale(self):
        p = self.root / "videos" / "A.mp4"
        p.write_bytes(b"video")
        verdicts.set_verdict(self.root, "A", "pass", "ok", ["videos/qa/tile.jpg"])
        p.write_bytes(b"video2")
        rows = verdicts.classify(self.root, qa_report={"expected_segments": ["A"], "results": []})
        row = rows["segments"]["A"] if "segments" in rows else rows["A"]
        self.assertTrue(row.get("stale"))


if __name__ == "__main__":
    unittest.main()
