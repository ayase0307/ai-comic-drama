import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import decisions as dec  # noqa: E402
import next_step as ns  # noqa: E402
import stage_content_checks as scc  # noqa: E402
import project_state as ps  # noqa: E402


def _tmp(case):
    root = Path(tempfile.mkdtemp())
    case.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
    return root


class DeliveryScopeDecision(unittest.TestCase):
    def test_known_and_decidable_without_stages(self):
        root = _tmp(self)
        entry = dec.decide(root, "delivery_scope", "script-only", "只要劇本")
        self.assertEqual(entry["value"], {"end_stage": 3})
        self.assertIn("delivery_scope", dec.KNOWN_DECISIONS)

    def test_json_value_and_unknown_key_rejected(self):
        self.assertEqual(dec.validate_delivery_scope({"end_stage": 4, "no_image": True}), [])
        self.assertTrue(dec.validate_delivery_scope({"end_stage": 9}))
        self.assertTrue(dec.validate_delivery_scope({"nope": 1}))
        self.assertTrue(dec.validate_delivery_scope("full"))

    def test_no_decision_means_full_scope(self):
        root = _tmp(self)
        self.assertEqual(dec.delivery_scope(root), {})
        self.assertIsNone(ns._scope_end({}))

    def test_no_video_caps_end_stage(self):
        self.assertEqual(ns._scope_end({"no_video": True}), 5)
        self.assertEqual(ns._scope_end({"end_stage": 3, "no_video": True}), 3)


class StageTwoNoImage(unittest.TestCase):
    def _assets(self, body):
        root = _tmp(self)
        (root / "assets.md").write_text(body, encoding="utf-8")
        return root

    CARD = ("### C-lin　林晚\n- **固定描述片段**：`女, 二十歲, 黑長髮, 瘦高, 冷靜`\n"
            "- **設定圖**：`images/C-lin_W01_sheet_v1.png`\n")

    def test_no_image_accepts_text_card_without_image_file(self):
        root = self._assets(self.CARD)
        dec.decide(root, "delivery_scope", "script-only", "只要文字")
        dec.decide(root, "delivery_scope", '{"end_stage": 3, "no_image": true}', "不生圖")
        self.assertEqual(scc._text_card_errors(self.CARD), [])
        self.assertEqual([e for e in scc.stage2_errors(root) if "不存在" in e], [])

    def test_no_image_rejects_without_text_card(self):
        root = self._assets("# 資產聖經\n")
        dec.decide(root, "delivery_scope", '{"no_image": true}', "不生圖")
        self.assertTrue(any("文字設定卡" in e for e in scc.stage2_errors(root)))

    def test_image_mode_still_requires_files(self):
        root = self._assets(self.CARD)
        self.assertTrue(any("不存在" in e for e in scc.stage2_errors(root)))


class DoneAtScopeEnd(unittest.TestCase):
    def test_plan_reports_done_past_end_stage(self):
        root = _tmp(self)
        ps.save_state(root, ps.initial_state("t", "p"))
        dec.decide(root, "delivery_scope", "storyboard-only", "到分鏡")
        with mock.patch.object(ps, "first_unapproved", return_value=(5, "x")):
            res = ns.plan(root)
        self.assertTrue(res["done"])
        self.assertEqual(res["stage"], 4)
        self.assertIsNone(res["next_command"])

    def test_plan_keeps_going_inside_scope(self):
        root = _tmp(self)
        ps.save_state(root, ps.initial_state("t", "p"))
        dec.decide(root, "delivery_scope", "storyboard-only", "到分鏡")
        with mock.patch.object(ps, "first_unapproved", return_value=(4, "x")):
            res = ns.plan(root)
        self.assertFalse(res["done"])


if __name__ == "__main__":
    unittest.main()
