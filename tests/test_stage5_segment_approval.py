"""PR-19a：階段 5 段級核准。

核准後只改部分段 → 只有改過的段待重審，沒改的段保持核准、可送件；
舊快照（沒有 approval_segments）行為照舊；共用部分變了要整份重審；
改過的段只能人工 `h3d approve --stage 5 --segments` 重審，不自動核准；
已有影片的段被改 → h3d deps 的 stale 清單出現 prompt_stale。
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for p in (SCRIPTS, SCRIPTS / "storyboard", SCRIPTS / "review", Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import _content_gate  # noqa: E402
import project_state as ps  # noqa: E402


def setUpModule():
    _content_gate.disable()


def tearDownModule():
    _content_gate.enable()


SEG_IDS = ("EP01-S01", "EP01-S02", "EP01-S03")


class Stage5SegmentApprovalTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = root = Path(self.tmp.name)
        for name in ("review", "adapt", "images", "layer2", "videos"):
            (root / name).mkdir()
        (root / "project.md").write_text("pitch", encoding="utf-8")
        (root / "adapt" / "source.json").write_text("{}", encoding="utf-8")
        (root / "adapt" / "bible.json").write_text("{}", encoding="utf-8")
        (root / "adapt" / "character-bible.md").write_text("characters", encoding="utf-8")
        (root / "assets.md").write_text("assets", encoding="utf-8")
        Image.new("RGB", (2, 2), "white").save(root / "images" / "character.png")
        Image.new("RGB", (2, 2), "black").save(root / "images" / "scene.png")
        (root / "script-ep01.md").write_text("script", encoding="utf-8")
        (root / "handoff-ep01.json").write_text("{}", encoding="utf-8")
        (root / "layer2" / "panels").mkdir()
        for sid in SEG_IDS:
            Image.new("RGB", (2, 2), "white").save(root / "layer2" / "panels" / f"{sid}.png")
            (root / "layer2" / f"layer2-{sid}.json").write_text(json.dumps({
                "segment_id": sid, "shots": [{"shot_id": "SH01", "sketch_file": f"panels/{sid}.png"}]}),
                encoding="utf-8")
        self.segments = root / "segments-ep01.json"
        self.write_segments({sid: f"prompt {sid}" for sid in SEG_IDS})
        with mock.patch.object(ps, "_ffprobe", return_value={"duration": 2.0}):
            for stage in range(6):
                ps.mark_awaiting_review(root, ps.load_state(root), stage)
                ok, why = ps.approve_stage_detailed(root, stage, "confirmed")
                self.assertTrue(ok, f"stage-{stage}: {why}")

    def write_segments(self, prompts, extra=None, refs=None):
        payload = {"episode": "EP01", "segments": [
            {"segment_id": sid, "h3_prompt": text,
             "segment_end_state": {"planned_final_state": "standing"},
             "reference_images": [{"path": (refs or {}).get(sid, "images/character.png")}]}
            for sid, text in prompts.items()]}
        payload.update(extra or {})
        self.segments.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def edit(self, sid, text):
        data = json.loads(self.segments.read_text(encoding="utf-8"))
        for seg in data["segments"]:
            if seg["segment_id"] == sid:
                seg["h3_prompt"] = text
        self.segments.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # ---- 快照 ----------------------------------------------------------
    def test_approval_records_per_segment_fingerprints(self):
        entry = ps.load_state(self.root)["stages"]["stage-5"]
        self.assertEqual(set(entry["approval_segments"]["segments"]), set(SEG_IDS))
        self.assertEqual(ps.stage5_segment_review(self.root)["mode"], "full")
        self.assertTrue(ps.is_approved(self.root, 5))

    def test_editing_one_segment_marks_only_it_pending(self):
        self.edit("EP01-S02", "prompt changed")
        self.assertFalse(ps.is_approved(self.root, 5))
        review = ps.stage5_segment_review(self.root)
        self.assertEqual(review["mode"], "partial")
        self.assertEqual(review["pending"], ["EP01-S02"])
        self.assertEqual(review["approved"], ["EP01-S01", "EP01-S03"])
        stage, detail = ps.first_unapproved(self.root)
        self.assertEqual(stage, 5)
        self.assertIn("EP01-S02", detail)
        self.assertIn("待人工重審", detail)

    def test_reference_image_change_marks_segments_using_it(self):
        from PIL import Image
        self.write_segments({sid: f"prompt {sid}" for sid in SEG_IDS}, refs={"EP01-S03": "images/scene.png"})
        # 換綁參考圖本身就是段內容變動
        self.assertEqual(ps.stage5_segment_review(self.root)["pending"], ["EP01-S03"])
        # 階段 5 自己的裁切圖（不在 images/，不屬於階段 2）被改 → 用到它的段待重審
        (self.root / "crops").mkdir()
        crop = self.root / "crops" / "hero-face.png"
        Image.new("RGB", (2, 2), "white").save(crop)
        refs = {"EP01-S01": "crops/hero-face.png", "EP01-S02": "crops/hero-face.png"}
        self.write_segments({sid: f"prompt {sid}" for sid in SEG_IDS}, refs=refs)
        ps.record_segment_review(self.root, ["EP01-S01", "EP01-S02", "EP01-S03"])
        ok, why = ps.approve_stage5_segments(self.root, "all", "通過")
        self.assertTrue(ok, why)
        Image.new("RGB", (3, 3), "red").save(crop)
        review = ps.stage5_segment_review(self.root)
        self.assertEqual(review["mode"], "partial")
        self.assertEqual(review["pending"], ["EP01-S01", "EP01-S02"])

    def test_new_and_removed_segments_are_pending(self):
        prompts = {sid: f"prompt {sid}" for sid in SEG_IDS if sid != "EP01-S03"}
        prompts["EP01-S04"] = "brand new"
        self.write_segments(prompts)
        review = ps.stage5_segment_review(self.root)
        self.assertEqual(review["new"], ["EP01-S04"])
        self.assertEqual(review["removed"], ["EP01-S03"])
        self.assertEqual(review["pending"], ["EP01-S03", "EP01-S04"])

    def test_shared_shell_change_requires_full_rereview(self):
        self.write_segments({sid: f"prompt {sid}" for sid in SEG_IDS}, extra={"episode": "EP01-v2"})
        review = ps.stage5_segment_review(self.root)
        self.assertEqual(review["mode"], "invalid")
        self.assertIn("共用部分", review["reason"])
        allowed, _pending, _why = ps.stage5_submittable_ids(self.root, self.segments)
        self.assertEqual(allowed, set())

    def test_legacy_snapshot_without_segment_data_keeps_old_behavior(self):
        state = ps.load_state(self.root)
        state["stages"]["stage-5"].pop("approval_segments")
        ps.save_state(self.root, state)
        self.assertTrue(ps.is_approved(self.root, 5))
        self.edit("EP01-S02", "prompt changed")
        review = ps.stage5_segment_review(self.root)
        self.assertEqual(review["mode"], "legacy")
        self.assertIn("核准後輸入或產物已變更", ps.first_unapproved(self.root)[1])
        import submit_h3_segments as submit
        scope = {}
        with redirect_stderr(io.StringIO()):
            self.assertFalse(submit.verify_stage5_gate(self.root, self.segments, scope=scope))
        self.assertEqual(scope, {})

    # ---- 送件閘門 ------------------------------------------------------
    def test_submit_gate_only_passes_unchanged_segments(self):
        import submit_h3_segments as submit
        self.edit("EP01-S02", "prompt changed")
        scope = {}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertTrue(submit.verify_stage5_gate(self.root, self.segments, scope=scope))
        self.assertEqual(scope["allowed"], {"EP01-S01", "EP01-S03"})
        self.assertEqual(scope["pending"], ["EP01-S02"])
        self.assertIn("EP01-S02", err.getvalue())

    def test_submit_main_refuses_explicit_pending_segment(self):
        import submit_h3_segments as submit
        self.edit("EP01-S02", "prompt changed")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(submit, "audit_segment_prompts", side_effect=AssertionError("不該走到審查")), \
                redirect_stdout(out), redirect_stderr(err):
            rc = submit.main(["--segments", str(self.segments), "--root-dir", str(self.root),
                              "--segment-id", "EP01-S02", "--dry-run"])
        self.assertEqual(rc, 1)
        self.assertIn("待重審", err.getvalue())

    def test_submit_main_skips_pending_segments_in_batch(self):
        import submit_h3_segments as submit
        self.edit("EP01-S02", "prompt changed")
        seen = {}

        def fake_audit(todo, **_kw):
            seen["ids"] = [s["segment_id"] for s in todo]
            return False, ["stop here"]

        with mock.patch.object(submit, "audit_segment_prompts", side_effect=fake_audit), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            submit.main(["--segments", str(self.segments), "--root-dir", str(self.root), "--dry-run"])
        self.assertEqual(seen["ids"], ["EP01-S01", "EP01-S03"])

    def test_runner_blocks_pending_segments_in_plan(self):
        import fv_runner
        self.edit("EP01-S02", "prompt changed")
        plan = [{"key": sid, "segment_id": sid, "out": f"videos/{sid}.mp4"} for sid in SEG_IDS]
        runner = fv_runner.Runner(self.root, plan, api=mock.Mock(api="local"),
                                  progress=self.root / "videos" / "_progress.json", log=lambda m: None)
        self.assertEqual(runner.stage5_pending(runner.load_segments()), ["EP01-S02"])
        ok_plan = [p for p in plan if p["key"] != "EP01-S02"]
        runner2 = fv_runner.Runner(self.root, ok_plan, api=mock.Mock(api="local"),
                                   progress=self.root / "videos" / "_progress2.json", log=lambda m: None)
        self.assertEqual(runner2.stage5_pending(runner2.load_segments()), [])

    # ---- 重審流程 ------------------------------------------------------
    def test_segment_reapproval_requires_review_page_and_note(self):
        self.edit("EP01-S02", "prompt changed")
        ok, why = ps.approve_stage5_segments(self.root, ["EP01-S02"], "")
        self.assertFalse(ok)
        self.assertIn("使用者原話", why)
        ok, why = ps.approve_stage5_segments(self.root, ["EP01-S02"], "通過")
        self.assertFalse(ok)
        self.assertIn("重審頁", why)
        ok, why = ps.approve_stage5_segments(self.root, ["EP01-S01"], "通過")
        self.assertFalse(ok)
        self.assertIn("不在待重審清單", why)

    def test_segment_reapproval_restores_full_approval(self):
        self.edit("EP01-S02", "prompt changed")
        self.edit("EP01-S03", "prompt changed too")
        ps.record_segment_review(self.root, ["EP01-S02"])
        ok, why = ps.approve_stage5_segments(self.root, ["EP01-S02"], "S02 通過")
        self.assertTrue(ok, why)
        review = ps.stage5_segment_review(self.root)
        self.assertEqual(review["pending"], ["EP01-S03"])
        self.assertFalse(ps.is_approved(self.root, 5))
        ps.record_segment_review(self.root, ["EP01-S03"])
        self.edit("EP01-S03", "edited after review page")
        ok, why = ps.approve_stage5_segments(self.root, ["EP01-S03"], "通過")
        self.assertFalse(ok)
        self.assertIn("重審頁產出後又改了", why)
        ps.record_segment_review(self.root, ["EP01-S03"])
        ok, why = ps.approve_stage5_segments(self.root, ["EP01-S03"], "S03 通過")
        self.assertTrue(ok, why)
        self.assertTrue(ps.is_approved(self.root, 5))
        entry = ps.load_state(self.root)["stages"]["stage-5"]
        self.assertEqual(len(entry["segment_approval_history"]), 2)
        self.assertEqual(ps.state_integrity(self.root), "ok")

    def test_change_reverted_needs_no_rereview(self):
        self.edit("EP01-S02", "prompt changed")
        self.edit("EP01-S02", "prompt EP01-S02")
        self.assertTrue(ps.is_approved(self.root, 5))

    def test_h3d_approve_segments_cli(self):
        import h3d
        self.edit("EP01-S02", "prompt changed")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(h3d.main(["approve", "--auto", "--stage", "5", "--segments", "EP01-S02",
                                       "--root", str(self.root)]), 2)
        ps.record_segment_review(self.root, ["EP01-S02"])
        out = io.StringIO()
        with redirect_stdout(out):
            rc = h3d.main(["approve", "5", "--segments", "EP01-S02", "--user-note", "這段可以",
                           "--root", str(self.root)])
        self.assertEqual(rc, 0, out.getvalue())
        self.assertTrue(ps.is_approved(self.root, 5))

    def test_auto_approve_never_reapproves_changed_segments(self):
        import auto_approve
        self.edit("EP01-S02", "prompt changed")
        result = auto_approve.evaluate(self.root, 5)
        self.assertFalse(result["eligible"])
        self.assertTrue(any("人工重審" in b for b in result["blockers"]), result["blockers"])

    def test_rereview_page_binds_only_pending_segments(self):
        import build_stage_review as bsr
        self.edit("EP01-S02", "prompt changed")
        captured = {}

        def fake_build(project_dir, state, only=None, removed=None):
            captured["only"] = only
            captured["status"] = state["stages"]["stage-5"]["status"]
            return True, [], "<html><!--ISSUES--></html>"

        with mock.patch.object(bsr, "build_stage_5", side_effect=fake_build), redirect_stdout(io.StringIO()):
            rc = bsr._build_stage5_rereview(self.root, ps.load_state(self.root), "all", False)
        self.assertEqual(rc, 0)
        self.assertEqual(captured["only"], {"EP01-S02"})
        self.assertEqual(captured["status"], "awaiting_user_approval")
        self.assertTrue((self.root / "review" / bsr.REREVIEW_FILE).is_file())
        entry = ps.load_state(self.root)["stages"]["stage-5"]
        self.assertEqual(entry["status"], "approved", "重審頁不得改動其他段的核准狀態")
        self.assertEqual(set(entry["segment_review"]["segments"]), {"EP01-S02"})
        with redirect_stderr(io.StringIO()):
            self.assertEqual(bsr._build_stage5_rereview(self.root, ps.load_state(self.root), "EP01-S01", False), 2)

    # ---- deps／next ----------------------------------------------------
    def test_changed_segment_with_video_shows_in_deps_stale(self):
        import deps
        (self.root / "videos" / "EP01-S02.mp4").write_bytes(b"old video")
        (self.root / "videos" / "EP01-S01.mp4").write_bytes(b"old video")
        self.assertEqual(deps.status(self.root)["stale"], [])
        self.edit("EP01-S02", "prompt changed")
        report = deps.status(self.root)
        self.assertEqual([i["segment_id"] for i in report["stale"]], ["EP01-S02"])
        self.assertIn("prompt_stale", report["stale"][0]["reasons"])
        self.assertIn("EP01-S02", deps.render(report))
        deps.record(self.root)
        report = deps.status(self.root)
        self.assertIn("EP01-S02", [i["segment_id"] for i in report["stale"]])

    def test_next_points_to_segment_rereview(self):
        import next_step
        self.edit("EP01-S02", "prompt changed")
        with mock.patch.object(next_step.decisions_mod, "missing_for_stage", return_value=[]):
            res = next_step.plan(self.root)
        self.assertEqual(res["stage"], 5)
        self.assertEqual(res["status"], "segments_pending_review")
        self.assertEqual(res["segments_pending_review"], ["EP01-S02"])
        self.assertIn("--stage 5 --segments EP01-S02", res["next_command"])
        self.assertIn("approve --stage 5 --segments EP01-S02", res["action"])
        self.assertTrue(any("EP01-S01" in n and "submit" in n for n in res["notes"]), res["notes"])


if __name__ == "__main__":
    unittest.main()
