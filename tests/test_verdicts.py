"""review/verdicts.json 與驗收政策分類。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import decisions  # noqa: E402
import verdicts  # noqa: E402


def qa_item(sid, passed=True, issues=None, sha=None):
    return {"segment_id": sid, "passed": passed, "issues": issues or [], "video_sha256": sha}


class VerdictTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "videos" / "qa").mkdir(parents=True)
        self.tile = self.root / "videos" / "qa" / "tile.jpg"
        self.tile.write_bytes(b"jpg")
        decisions.decide(self.root, "acceptance_policy", "recommended", "照建議")

    def _video(self, sid, content=b"video"):
        path = self.root / "videos" / f"{sid}.mp4"
        path.write_bytes(content)
        return path

    def test_set_verdict_requires_existing_evidence_and_binds_video_hash(self):
        with self.assertRaises(verdicts.VerdictError):
            verdicts.set_verdict(self.root, "EP01-S01", "pass", "ok", [])
        with self.assertRaises(verdicts.VerdictError):
            verdicts.set_verdict(self.root, "EP01-S01", "pass", "ok", ["videos/qa/missing.jpg"])
        self._video("EP01-S01")
        entry = verdicts.set_verdict(self.root, "EP01-S01", "pass", "人物一致", ["videos/qa/tile.jpg"])
        self.assertEqual(entry["evidence"], "videos/qa/tile.jpg")
        self.assertEqual(entry["decided_by"], "agent")
        self.assertEqual(len(entry["video_sha256"]), 64)
        saved = json.loads((self.root / "review" / "verdicts.json").read_text(encoding="utf-8"))
        self.assertEqual(verdicts.validate(saved), [])

    def test_validate_rejects_bad_entries(self):
        bad = {"schema_version": 1, "segments": {"A": {"verdict": "ok", "reason": "", "evidence": [],
                                                      "decided_by": "robot", "issues": ["nope"]}}}
        errors = verdicts.validate(bad)
        self.assertEqual(len(errors), 5)

    def test_policy_escalates_and_downgrades_agent_verdicts(self):
        for sid in ("A", "B", "C", "D"):
            self._video(sid)
        verdicts.set_verdict(self.root, "A", "pass", "看起來可以", ["videos/qa/tile.jpg"], issues=["face_mix"])
        verdicts.set_verdict(self.root, "B", "fail", "簿頁出字", ["videos/qa/tile.jpg"], issues=["paper_text"])
        verdicts.set_verdict(self.root, "C", "fail", "老大說重跑", ["videos/qa/tile.jpg"],
                             decided_by="user", issues=["paper_text"])
        verdicts.set_verdict(self.root, "D", "warn", "人物稍老", ["videos/qa/tile.jpg"], issues=["aged_face"])
        report = verdicts.classify(self.root, qa_report={"expected_segments": ["A", "B", "C", "D", "E"], "results": []})
        rows = report["segments"]
        self.assertEqual((rows["A"]["effective"], rows["A"]["source"]), ("fail", "policy"))
        self.assertEqual((rows["B"]["effective"], rows["B"]["source"]), ("warn", "policy"))
        self.assertEqual((rows["C"]["effective"], rows["C"]["source"]), ("fail", "user"))
        self.assertEqual(rows["D"]["effective"], "warn")
        self.assertEqual(rows["E"]["effective"], "unreviewed")
        self.assertEqual(report["counts"], {"pass": 0, "warn": 2, "fail": 2, "unreviewed": 1})

    def test_technical_qa_codes_map_to_policy(self):
        qa = {"expected_segments": ["LOW", "GRID", "DRIFT", "OK"], "results": [
            qa_item("LOW", False, ["STYLE_BLEED_GRAYSCALE: 彩度過低"]),
            qa_item("GRID", False, ["GRID_PANEL_BORDER_DETECTED: 框線"]),
            qa_item("DRIFT", False, ["DURATION_MISMATCH: 差 0.7s"]),
            qa_item("OK", True),
        ]}
        rows = verdicts.classify(self.root, qa_report=qa)["segments"]
        # 低彩度在政策 accept 內：沒看過就是 unreviewed，不是 fail
        self.assertEqual(rows["LOW"]["effective"], "unreviewed")
        self.assertEqual(rows["LOW"]["qa_codes"], ["low_chroma"])
        # 九宮格殘留在 rerun_on：不用看也知道要重跑
        self.assertEqual((rows["GRID"]["effective"], rows["GRID"]["source"]), ("fail", "policy"))
        # 時長漂移是硬錯誤
        self.assertEqual((rows["DRIFT"]["effective"], rows["DRIFT"]["source"]), ("fail", "qa"))
        # 技術綠燈不等於看過
        self.assertEqual(rows["OK"]["effective"], "unreviewed")

    def test_low_chroma_with_agent_pass_stays_pass(self):
        video = self._video("LOW")
        verdicts.set_verdict(self.root, "LOW", "pass", "教室本來就暗", ["videos/qa/tile.jpg"])
        sha = verdicts._sha256(video)
        qa = {"expected_segments": ["LOW"], "results": [qa_item("LOW", False, ["STYLE_BLEED_GRAYSCALE"], sha)]}
        row = verdicts.classify(self.root, qa_report=qa)["segments"]["LOW"]
        self.assertEqual(row["effective"], "pass")

    def test_verdict_goes_stale_when_video_is_regenerated(self):
        self._video("A", b"take1")
        verdicts.set_verdict(self.root, "A", "pass", "ok", ["videos/qa/tile.jpg"])
        self._video("A", b"take2")
        row = verdicts.classify(self.root, qa_report={"expected_segments": ["A"], "results": []})["segments"]["A"]
        self.assertEqual(row["effective"], "unreviewed")
        self.assertTrue(row["stale"])

    def test_schema_file_matches_module(self):
        schema = json.loads((ROOT / "references" / "schemas" / "verdicts.schema.json").read_text(encoding="utf-8"))
        props = schema["$defs"]["verdict"]["properties"]
        self.assertEqual(props["verdict"]["enum"], list(verdicts.VERDICTS))
        self.assertEqual(props["decided_by"]["enum"], list(verdicts.DECIDED_BY))
        self.assertEqual(props["issues"]["items"]["enum"], list(decisions.ISSUE_CODES))


if __name__ == "__main__":
    unittest.main()


class AcceptAllTests(unittest.TestCase):
    def test_accept_all_converts_warn_to_user(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            root = Path(td)
            (root / "tile.jpg").write_bytes(b"x")
            decisions.decide(root, "acceptance_policy", "recommended", "照建議")
            verdicts.set_verdict(root, "S1", "warn", "小問題", ["tile.jpg"])
            verdicts.set_verdict(root, "S2", "pass", "ok", ["tile.jpg"])
            done = verdicts.accept_all(root, "接受現有")
            self.assertEqual(done, ["S1"])
            self.assertEqual(verdicts.load(root)["segments"]["S1"]["decided_by"], "user")
            with self.assertRaises(verdicts.VerdictError):
                verdicts.accept_all(root, " ")
