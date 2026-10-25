"""PR-2：收件匣與階段 2／4／5 流程（#22 #23 #24 #36 #44 #45 #56 #62 #63）。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, SCRIPTS / "review", SCRIPTS / "storyboard"):
    sys.path.insert(0, str(extra))

import build_stage_review as review  # noqa: E402
import inbox  # noqa: E402
import next_step  # noqa: E402
import project_state as ps  # noqa: E402


class _Project(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        for folder in ("review", "images", "panels", "layer2", "assets"):
            (self.root / folder).mkdir(exist_ok=True)
        # 定案卡不是這組測試的重點：假設該定的都定了
        patcher = mock.patch.object(inbox.decisions_mod, "missing_for_stage", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def png(self, rel, color="white"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 20), color).save(path)
        return path

    def layer(self, sid, shots):
        (self.root / "layer2" / f"layer2-{sid}.json").write_text(
            json.dumps({"segment_id": sid, "shots": shots}), encoding="utf-8")

    def set_stage(self, cur, status="in_progress"):
        state = ps.load_state(self.root)
        for i in range(8):
            key = ps.stage_key(i)
            state["stages"][key]["status"] = "approved" if i < cur else ("locked" if i > cur else status)
            if i < cur:
                state["stages"][key]["approval_snapshot"] = {"files": {}}
                state["stages"][key]["approval_dependencies"] = {"stage-0": "x"}
        ps.save_state(self.root, state)


class Stage4ArtifactTests(_Project):
    def test_rejected_panel_is_not_claimed(self):
        self.png("panels/panel-01-SH01.png")
        self.layer("EP01-S01-a", [{"shot_id": "SH01", "sketch_status": "rejected"}])
        matched, errors = ps.stage4_artifacts(self.root)
        self.assertEqual(matched, [])
        self.assertIn("自檢退回", errors[0])

    def test_explicit_sketch_file_does_not_fall_back_to_panels(self):
        self.png("panels/panel-01-SH01.png")
        self.layer("EP01-S01-a", [{"shot_id": "SH01", "sketch_file": "panels/new/SH01.png"}])
        matched, errors = ps.stage4_artifacts(self.root)
        self.assertEqual(matched, [])
        self.assertIn("sketch_file", errors[0])

    def test_implicit_panel_still_works(self):
        self.png("panels/panel-01-SH01.png")
        self.layer("EP01-S01-a", [{"shot_id": "SH01", "sketch_status": "manual"}])
        matched, errors = ps.stage4_artifacts(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(matched), 1)


class InboxStageCardTests(_Project):
    def test_stage4_gaps_produce_card_and_block_auto_approve(self):
        self.png("panels/_rejected/panel-02-SH02.png")
        self.png("panels/panel-01-SH01.png")
        self.layer("EP02-S01-a", [{"shot_id": "SH01"}, {"shot_id": "SH02", "sketch_status": "rejected"},
                                   {"shot_id": "SH03"}])
        self.set_stage(4)
        cards = inbox.build_cards(self.root)["open"]
        card = next(c for c in cards if c["id"] == "D4-sketch-gaps")
        self.assertIn("1 鏡缺構圖", card["title"])
        self.assertIn("1 鏡自檢退回", card["title"])
        self.assertTrue(card["evidence_paths"])
        self.assertTrue(inbox.open_cards_for_stage(self.root, 4))

    def _manifest(self, disposition):
        self.png("images/C-hero_sheet_v1.png", "red")
        self.png("images/C-villain_sheet_v1.png", "blue")
        data = {"assets": [
            {"stable_id": "C-hero", "display_name_zh": "主角", "asset_type": "character",
             "target_path": "images/C-hero_sheet_v1.png", "review_disposition": disposition,
             "technical_review_notes": ["臉偏偶像化"]},
            {"stable_id": "C-villain", "display_name_zh": "反派", "asset_type": "character",
             "target_path": "images/C-villain_sheet_v1.png", "review_disposition": "Agent 自檢通過"},
        ]}
        (self.root / "assets" / "reference-manifest.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_stage2_manifest_failure_becomes_card(self):
        self._manifest("自檢不通過（臉，兩次）")
        self.set_stage(2, "awaiting_user_approval")
        cards = inbox.build_cards(self.root)["open"]
        ids = [c["id"] for c in cards]
        self.assertIn("D2-asset-selfcheck", ids)
        self.assertNotIn("D2-approve", ids)

    def test_stage2_approval_card_embeds_sheets_and_flags_flaws(self):
        self._manifest("Agent 自檢通過（有瑕疵）→ 待老大看臉")
        self.set_stage(2, "awaiting_user_approval")
        ps.mark_awaiting_review(self.root, ps.load_state(self.root), 2)  # 核准卡只在審核快照有效時出現
        card = next(c for c in inbox.build_cards(self.root)["open"] if c["id"] == "D2-approve")
        self.assertNotIn("沒有例外", card["recommendation"])
        self.assertIn("瑕疵", card["recommendation"])
        self.assertEqual(len(card["evidence_paths"]), 2)
        model = inbox.collect(self.root, strips="none")
        approve = next(c for c in model["cards"] if c["id"] == "D2-approve")
        self.assertEqual(len(approve["evidence_b64"]), 2)

    def test_stage1_event_coverage_becomes_card_not_plain_approval(self):
        (self.root / "adapt").mkdir(exist_ok=True)
        (self.root / "adapt" / "source.json").write_text(json.dumps({"story_units": [
            {"unit_id": "U1", "summary": "上島", "expected_grade": "KEEP_IF_POSSIBLE"},
            {"unit_id": "U2", "summary": "遇獸", "expected_grade": "KEEP_IF_POSSIBLE"}]}), encoding="utf-8")
        (self.root / "handoff-ep01.json").write_text(json.dumps({"episodes": [
            {"episode_id": "EP01", "scenes": [{"scene_id": "S01", "source_refs": ["U1"]}]}]}), encoding="utf-8")
        self.set_stage(1, "awaiting_user_approval")
        ps.mark_awaiting_review(self.root, ps.load_state(self.root), 1)
        cards = inbox.build_cards(self.root)["open"]
        ids = [c["id"] for c in cards]
        self.assertIn("D1-event-coverage", ids)
        self.assertNotIn("D1-approve", ids, "有待決事件時不能出「沒有例外，建議通過」")
        card = next(c for c in cards if c["id"] == "D1-event-coverage")
        self.assertIn("U1", card["finding"])
        self.assertTrue(card["if_ignored"])

    def _segments(self, refs):
        (self.root / "segments-ep01.json").write_text(json.dumps({"segments": [
            {"segment_id": "EP01-S01-a", "reference_images": refs}]}), encoding="utf-8")

    def test_stage5_mixed_face_and_missing_refs(self):
        self.png("images/a.png")
        self._segments([{"type": "character", "path": "images/a.png"},
                        {"type": "character", "path": "images/missing.png"}])
        self.set_stage(5, "awaiting_user_approval")
        ids = [c["id"] for c in inbox.build_cards(self.root)["open"]]
        self.assertIn("D5-missing-refs", ids)
        self.assertIn("D5-mixed-face", ids)
        self.assertNotIn("D5-approve", ids)

    def test_stage5_non_face_crop_is_not_mixed(self):
        self.png("images/a.png")
        self.png("images/b.png")
        self._segments([{"type": "character", "path": "images/a.png"},
                        {"type": "character", "path": "images/b.png", "reference_view": "non_face"}])
        self.assertEqual(inbox.mixed_face_segments(self.root), [])

    def test_mixed_face_accepted_by_policy_goes_to_auto(self):
        self.png("images/a.png")
        self.png("images/b.png")
        self._segments([{"type": "character", "path": "images/a.png"},
                        {"type": "character", "path": "images/b.png"}])
        cards, auto = inbox.stage5_cards(self.root, {inbox.MIXED_FACE_CODE})
        self.assertEqual(cards, [])
        self.assertEqual(len(auto), 1)


class NextStepCommandTests(_Project):
    def test_stage4_without_layer2_points_to_skeleton(self):
        (self.root / "handoff-ep01.json").write_text("{}", encoding="utf-8")
        command, action = next_step.stage4_producer(self.root, ["找不到 layer2/layer2-*.json 分鏡檔案"])
        self.assertIn("handoff_to_skeleton.py", command)
        self.assertIn("handoff-ep01.json --out-dir layer2", command)
        self.assertNotIn("<EP", command)

    def test_stage4_with_layer2_substitutes_episode(self):
        self.layer("EP02-S01-a", [{"shot_id": "SH01"}])
        command, _ = next_step.stage4_producer(self.root, ["EP02-S01-a/SH01: 缺少有效且對應的構圖 PNG"])
        self.assertIn("sketch --root . --episode EP02", command)

    def test_stage5_compile_command_is_complete(self):
        self.layer("EP01-S01-a", [{"shot_id": "SH01"}])
        (self.root / "video-bible.json").write_text("{}", encoding="utf-8")
        (self.root / "video-bindings.json").write_text("{}", encoding="utf-8")
        command, _ = next_step.stage5_producer(self.root, [])
        for part in ('--layer2 "layer2/layer2-EP01-*.json"', "--episode EP01", "--bible video-bible.json",
                     "--bindings video-bindings.json", "--output-md prompts-ep01.md",
                     "--output-segments segments-ep01.json", "--check"):
            self.assertIn(part, command)
        self.assertNotIn("<", command)


class SelfContainedReviewTests(_Project):
    def test_inline_local_images(self):
        self.png("images/x.png")
        html_text = '<img loading="lazy" src="../images/x.png" alt="x"><img src="../images/none.png">'
        out, count = review.inline_local_images(html_text, self.root / "review")
        self.assertEqual(count, 1)
        self.assertIn("data:image/", out)
        self.assertIn('src="../images/none.png"', out)


if __name__ == "__main__":
    unittest.main()
