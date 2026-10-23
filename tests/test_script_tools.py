# -*- coding: utf-8 -*-
"""PR-4 劇本工具：#26 #27 #28 #29 #31 #32 #34 #3。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))
sys.path.insert(0, str(ROOT / "scripts" / "craft"))

import audio_keywords  # noqa: E402
import sync_script  # noqa: E402
import check_continuity  # noqa: E402
import estimate_duration  # noqa: E402
import hit_review  # noqa: E402
import mckee_review  # noqa: E402
import _common  # noqa: E402


class AudioKeywords(unittest.TestCase):
    def test_classification(self):
        c = audio_keywords.classify_note
        self.assertEqual(c("畫外"), "offscreen")
        self.assertEqual(c("腦內 O.S."), "offscreen")
        self.assertEqual(c("O.S."), "offscreen")
        self.assertEqual(c("畫外音"), "offscreen")
        self.assertEqual(c("V.O."), "voiceover")
        self.assertEqual(c("內心獨白"), "voiceover")
        self.assertEqual(c("內心"), "voiceover")
        self.assertEqual(c("腦內"), "voiceover")
        self.assertEqual(c("電話"), "phone")
        self.assertIsNone(c("低聲"))
        self.assertIsNone(c("COSMOS"))

    def test_sync_uses_shared_table(self):
        self.assertEqual(sync_script.detect_audio_type("畫外"), "offscreen")
        self.assertEqual(sync_script.detect_audio_type("內心"), "voiceover")

    def test_note_change_detected(self):
        hs = {"scene_id": "S1", "review": {"review_status": "draft", "revision": 1, "locked": False},
              "action_beats": ["a"], "dialogue": [{"speaker": "X", "text": "hi", "audio_type": "offscreen", "delivery_note": "畫外"}],
              "setting": {}}
        sc = {"actions": [{"text": "a"}], "dialogues": [{"speaker": "X", "text": "hi", "note": "V.O."}]}
        changed, _ = sync_script.sync_scene_content(hs, sc, {})
        self.assertTrue(changed)
        self.assertEqual(hs["dialogue"][0]["audio_type"], "voiceover")


class ProjectDefaults(unittest.TestCase):
    def test_defaults_from_decisions_and_project_md(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" if (ROOT / "tmp").exists() else None) as d:
            d = Path(d)
            (d / "decisions.json").write_text(json.dumps({"decisions": [{"id": "aspect_ratio", "value": "16:9"}]}), encoding="utf-8")
            (d / "project.md").write_text("- genre_mode：mystery_thriller\n", encoding="utf-8")
            r = sync_script.read_project_defaults(d)
            self.assertEqual(r, {"genre_mode": "mystery_thriller", "aspect_ratio": "16:9"})
            self.assertEqual(sync_script.read_project_defaults(d / "none")["aspect_ratio"], "9:16")


class CraftTools(unittest.TestCase):
    def test_duration_dict(self):
        self.assertEqual(_common.duration_seconds({"min": 10, "max": 20}), 15.0)
        self.assertEqual(_common.duration_seconds(12), 12.0)
        self.assertEqual(_common.duration_seconds(None), 0.0)

    def test_reviews_accept_min_max(self):
        ep = {"episode_id": "EP01", "title": "t", "scenes": [{"scene_id": "S1", "estimated_duration_seconds": {"min": 10, "max": 20}, "dialogue": []}]}
        hit_review.scene_spans(ep)
        mckee_review.review({"episodes": [ep], "scenes": ep["scenes"], "debt_ledger": []}, "EP01")

    def test_agent_section_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "r.md"
            new = "# x\n\n## Agent 審查\n\n（請 Agent 補）\n"
            t.write_text("# old\n\n## Agent 審查\n\n我寫的審查\n", encoding="utf-8")
            out = _common.keep_agent_section(new, t)
            self.assertIn("我寫的審查", out)
            t.write_text("# old\n\n## Agent 審查\n\n（請 Agent 補）\n", encoding="utf-8")
            self.assertEqual(_common.keep_agent_section(new, t), new)


class Continuity(unittest.TestCase):
    def test_creatures_registered_and_debt_tbd(self):
        bible = {"characters": [{"character_id": "C-A", "canonical_name": "甲"}],
                 "creatures": [{"creature_id": "CR-1", "canonical_name": "巨鳥"}]}
        handoff = {"episodes": [{"episode_id": "EP01", "scenes": [
            {"scene_id": "S1", "setting": {}, "characters": ["C-A", "CR-1"], "dialogue": []}]}],
            "debt_ledger": [{"debt_id": "D1", "origin_ep": "EP01", "payoff_ep": "TBD", "status": "open"}]}
        res = check_continuity.audit_continuity(bible, handoff, None)
        self.assertFalse([e for e in res["errors"] if "UNREGISTERED_CHAR_ID" in e or "INVALID_DEBT" in e], res["errors"])

    def test_paid_debt_needs_payoff(self):
        handoff = {"episodes": [], "debt_ledger": [{"debt_id": "D1", "origin_ep": "EP01", "status": "paid"}]}
        res = check_continuity.audit_continuity({"characters": []}, handoff, None)
        self.assertTrue([e for e in res["errors"] if "INVALID_DEBT" in e])


class EstimateDuration(unittest.TestCase):
    def test_project_genre_and_policy(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "project.md").write_text("- genre_mode：healing_literary\n", encoding="utf-8")
            (d / "decisions.json").write_text(json.dumps({"decisions": [{"id": "dialogue_policy", "value": "②"}]}), encoding="utf-8")
            (d / "source").mkdir()
            f = d / "source" / "c.txt"
            f.write_text("x", encoding="utf-8")
            root = estimate_duration.find_project_root(f)
            self.assertEqual(estimate_duration.project_genre(root), "healing_literary")
            self.assertTrue(estimate_duration.dialogue_policy_decided(root))


if __name__ == "__main__":
    unittest.main()
