"""強制照既定流程走：多集閘門、技術 QA 覆寫、project-state 防手改、`h3d next`。"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "storyboard"))

import decisions  # noqa: E402
import h3d  # noqa: E402
import next_step  # noqa: E402
import project_state as ps  # noqa: E402
import verdicts  # noqa: E402

EPISODES = {"ep01": ["EP01-S01"], "ep02": ["EP02-S01"]}
ALL_IDS = [sid for ids in EPISODES.values() for sid in ids]
FAKE_PROBE = {"duration": 2.0}


class TwoEpisodeProject(unittest.TestCase):
    """兩集專案：階段 0–5 已核准，影片已生成，等著做階段 6。"""

    def setUp(self):
        from PIL import Image

        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        probe = patch.object(ps, "_ffprobe", return_value=FAKE_PROBE)
        probe.start()
        self.addCleanup(probe.stop)
        r = self.root
        for name in ("review", "source", "adapt", "images", "layer2/panels", "videos/qa", "final"):
            (r / name).mkdir(parents=True, exist_ok=True)
        (r / "project.md").write_text("pitch", encoding="utf-8")
        for name in ("source.json", "bible.json"):
            (r / "adapt" / name).write_text("{}", encoding="utf-8")
        (r / "adapt" / "character-bible.md").write_text("characters", encoding="utf-8")
        (r / "assets.md").write_text("assets", encoding="utf-8")
        Image.new("RGB", (2, 2), "white").save(r / "images" / "character.png")
        for tag, ids in EPISODES.items():
            (r / f"script-{tag}.md").write_text("script", encoding="utf-8")
            (r / f"handoff-{tag}.json").write_text("{}", encoding="utf-8")
            for sid in ids:
                Image.new("RGB", (2, 2), "white").save(r / "layer2" / "panels" / f"panel-01-{sid}.png")
                (r / "layer2" / f"layer2-{sid}.json").write_text(json.dumps({
                    "segment_id": sid,
                    "shots": [{"shot_id": "SH01", "sketch_file": f"panels/panel-01-{sid}.png"}]}), encoding="utf-8")
            (r / f"segments-{tag}.json").write_text(json.dumps({"segments": [
                {"segment_id": sid, "reference_images": [{"path": "images/character.png"}]} for sid in ids]}),
                encoding="utf-8")
        for stage in range(6):
            state = ps.load_state(r)
            ps.mark_awaiting_review(r, state, stage)
            self.assertTrue(ps.approve_stage(r, stage, "使用者確認通過"), f"stage-{stage}")
        for sid in ALL_IDS:
            (r / "videos" / f"{sid}.mp4").write_bytes(f"video {sid}".encode())
        (r / "videos" / "qa" / "tile.jpg").write_bytes(b"jpg")
        for did, value in (("style", "半寫實"), ("aspect_ratio", "16:9"), ("design_engine", "codex"),
                           ("dialogue_policy", "重點台詞上畫"), ("acceptance_policy", "recommended")):
            decisions.decide(r, did, value, f"原話：{value}", date="2026-10-22")

    # ---- helpers -------------------------------------------------------
    def write_qa(self, *, failing=None, hard=None, multi=True, results_ids=None):
        failing = failing or {}
        hard = hard or {}
        ids = results_ids or ALL_IDS
        results = []
        for sid in ids:
            video = self.root / "videos" / f"{sid}.mp4"
            issues = []
            if sid in failing:
                issues.append(failing[sid])
            if sid in hard:
                issues.append(hard[sid])
            results.append({"segment_id": sid, "video_file": str(video), "video_sha256": ps.sha256_file(video),
                            "passed": not issues, "issues": issues})
        failed = sum(1 for item in results if not item["passed"])
        payload = {
            "expected_segments": list(ids),
            "unproduced_segments": [],
            "evidence": {"verdict": "PARTIAL" if failed else "VERIFIED", "produced": len(ids),
                         "expected": len(ids), "unmeasured": 0, "failed": failed, "unproduced": [],
                         "structural_issues": []},
            "results": results,
        }
        files = sorted(self.root.glob("segments-ep*.json"))
        if multi:
            payload["source_segments_files"] = [{"path": str(f), "sha256": ps.sha256_file(f)} for f in files]
        else:
            payload["expected_segments"] = list(EPISODES["ep01"])
            payload["source_segments_file"] = str(files[0])
            payload["source_segments_sha256"] = ps.sha256_file(files[0])
        (self.root / "videos" / "qa-report.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def await_stage6(self):
        state = ps.load_state(self.root)
        ps.mark_awaiting_review(self.root, state, 6)

    def plan(self):
        return next_step.plan(self.root)


class MultiEpisodeGateTests(TwoEpisodeProject):
    def test_full_series_report_passes_without_unexpected_segment_error(self):
        self.write_qa()
        hard, technical = ps.stage6_issues(self.root)
        self.assertEqual((hard, technical), ([], []))

    def test_single_episode_source_with_series_results_is_flagged_with_fix(self):
        self.write_qa(multi=False)
        hard, _ = ps.stage6_issues(self.root)
        joined = "\n".join(hard)
        self.assertIn("非預期分段", joined)
        self.assertIn("h3d qa --segments", joined)

    def test_series_source_must_be_in_stage5_snapshot(self):
        self.write_qa()
        (self.root / "segments-ep02.json").write_text(json.dumps({"segments": [
            {"segment_id": "EP02-S01", "reference_images": [{"path": "images/character.png"}], "x": 1}]}),
            encoding="utf-8")
        payload = json.loads((self.root / "videos" / "qa-report.json").read_text(encoding="utf-8"))
        for entry in payload["source_segments_files"]:
            entry["sha256"] = ps.sha256_file(Path(entry["path"]))
        (self.root / "videos" / "qa-report.json").write_text(json.dumps(payload), encoding="utf-8")
        hard, _ = ps.stage6_issues(self.root)
        self.assertTrue(any("stage-5 核准快照" in h for h in hard), hard)

    def test_verify_video_shot_accepts_several_segment_files(self):
        out = self.root / "videos" / "qa-multi.json"
        empty_videos = self.root / "no-videos"
        empty_videos.mkdir()
        subprocess.run([sys.executable, str(SCRIPTS / "storyboard" / "verify_video_shot.py"),
                        "--segments", str(self.root / "segments-ep01.json"), str(self.root / "segments-ep02.json"),
                        "--videos-dir", str(empty_videos), "--out-json", str(out)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["expected_segments"], ALL_IDS)
        self.assertEqual(len(payload["source_segments_files"]), 2)
        self.assertEqual(payload["episode"], "ALL")
        ids, error = ps.scoped_expected_segment_ids(self.root, payload)
        self.assertIsNone(error)
        self.assertEqual(ids, set(ALL_IDS))


class OverrideTests(TwoEpisodeProject):
    def test_partial_needs_override_with_reason_and_is_recorded(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE: 彩度過低"})
        hard, technical = ps.stage6_issues(self.root)
        self.assertEqual(hard, [])
        self.assertEqual(len(technical), 2)  # 證據等級 PARTIAL + 該段技術未過
        self.await_stage6()
        ok, why = ps.approve_stage_detailed(self.root, 6, "老大：核准")
        self.assertFalse(ok)
        self.assertIn("--override", why)
        self.assertFalse(ps.is_approved(self.root, 6))

        ok, why = ps.approve_stage_detailed(self.root, 6, "老大：核准", override_reason="教室低彩度誤判，老大看過通過")
        self.assertTrue(ok, why)
        entry = ps.load_state(self.root)["stages"]["stage-6"]
        self.assertEqual(entry["override"]["reason"], "教室低彩度誤判，老大看過通過")
        self.assertEqual(entry["override"]["overridden_issue_count"], 2)
        self.assertTrue(entry["override"]["at"])
        self.assertEqual(len(entry["override_history"]), 1)
        self.assertTrue(ps.is_approved(self.root, 6))

        # 覆寫綁定快照：影片一換，核准就失效
        (self.root / "videos" / "EP02-S01.mp4").write_bytes(b"regenerated")
        self.assertFalse(ps.is_approved(self.root, 6))

    def test_hard_errors_cannot_be_overridden(self):
        self.write_qa(hard={"EP01-S01": "DURATION_MISMATCH: 差 0.7s"})
        hard, _ = ps.stage6_issues(self.root)
        self.assertTrue(any("不可覆寫" in h for h in hard))
        self.await_stage6()
        ok, why = ps.approve_stage_detailed(self.root, 6, "核准", override_reason="想硬過")
        self.assertFalse(ok)
        self.assertIn("不可覆寫", why)

    def test_override_only_applies_to_stage6(self):
        ok, why = ps.approve_stage_detailed(self.root, 5, "核准", override_reason="理由")
        self.assertFalse(ok)
        self.assertIn("階段 6", why)

    def test_policy_fail_verdict_blocks_even_with_override(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE"})
        verdicts.set_verdict(self.root, "EP01-S01", "pass", "低彩度可接受", ["videos/qa/tile.jpg"])
        verdicts.set_verdict(self.root, "EP02-S01", "pass", "看起來可以", ["videos/qa/tile.jpg"], issues=["extra_person"])
        hard, _ = ps.stage6_issues(self.root)
        self.assertTrue(any("EP02-S01: 驗收結論需重跑" in h for h in hard), hard)
        self.assertFalse(any(h.startswith("EP01-S01") for h in hard))

    def test_cli_rejects_override_without_reason_and_records_with_reason(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE"})
        cli = [sys.executable, str(SCRIPTS / "build_stage_review.py"), "--project-dir", str(self.root)]
        no_reason = subprocess.run(cli + ["--approve-stage", "6", "--override"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
        self.assertEqual(no_reason.returncode, 2)
        self.assertIn("--reason", no_reason.stderr)
        # 直接走模組核准（CLI 子行程沒有 _ffprobe 的 mock），確認 require_approved 接受覆寫紀錄
        self.await_stage6()
        self.assertTrue(ps.approve_stage(self.root, 6, "核准", override_reason="老大看過"))
        ok, detail = ps.require_approved(self.root, 6)
        self.assertTrue(ok, detail)


class IntegrityTests(TwoEpisodeProject):
    def test_hand_edit_is_detected(self):
        self.assertEqual(ps.state_integrity(self.root), "ok")
        path = ps.state_path(self.root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["stages"]["stage-6"]["status"] = "approved"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertEqual(ps.state_integrity(self.root), "tampered")
        res = self.plan()
        self.assertTrue(any("手改" in item for item in res["blocked_on"]))
        self.assertIn("停下", res["action"])

    def test_legacy_file_without_stamp_is_only_a_note(self):
        path = ps.state_path(self.root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("_integrity")
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(ps.state_integrity(self.root), "missing")
        res = self.plan()
        self.assertFalse(any("手改" in item for item in res["blocked_on"]))
        self.assertTrue(any("戳記" in note for note in res["notes"]))


class NextStepTests(TwoEpisodeProject):
    def test_uninitialized_project_points_to_init(self):
        empty = self.root / "empty"
        empty.mkdir()
        res = next_step.plan(empty)
        self.assertEqual(res["status"], "uninitialized")
        self.assertIn("init_project.py", res["next_command"])

    def test_missing_decision_comes_first(self):
        (self.root / "decisions.json").unlink()
        res = self.plan()
        self.assertEqual(res["stage"], 6)
        self.assertIn("decide", res["next_command"])
        self.assertIn("--quote", res["next_command"])
        self.assertTrue(res["read"])

    def test_missing_videos_lead_to_resume(self):
        (self.root / "videos" / "EP02-S01.mp4").unlink()
        res = self.plan()
        self.assertIn(" resume ", res["next_command"])
        self.assertIn("segments-ep02.json", res["next_command"])

    def test_missing_qa_report_leads_to_series_qa(self):
        res = self.plan()
        self.assertIn(" qa --segments segments-ep01.json segments-ep02.json", res["next_command"])

    def test_duration_drift_means_stop(self):
        self.write_qa(hard={"EP01-S01": "DURATION_MISMATCH: 差 0.7s"})
        res = self.plan()
        self.assertIsNone(res["next_command"])
        self.assertIn("停下", res["action"])

    def test_unreviewed_segments_lead_to_verdict(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE"})
        res = self.plan()
        self.assertIn(" verdict EP01-S01 ", res["next_command"])

    def test_reviewed_then_build_page_then_approve_with_override(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE"})
        for sid in ALL_IDS:
            verdicts.set_verdict(self.root, sid, "pass", "ok", ["videos/qa/tile.jpg"])
        res = self.plan()
        self.assertIn("--stage 6", res["next_command"])
        self.await_stage6()
        res = self.plan()
        self.assertEqual(res["status"], "awaiting_user_approval")
        self.assertIn("--approve-stage 6", res["next_command"])
        self.assertIn("--override --reason", res["next_command"])
        self.assertIn("<使用者原話>", res["next_command"])

    def test_active_runner_job_blocks_new_submissions(self):
        ledger = self.root / "videos" / "_fv-job-ledger.json"
        ledger.write_text(json.dumps({"jobs": [{"segment_id": "EP02-S01", "job_id": "j1", "status": "running"}]}),
                          encoding="utf-8")
        res = self.plan()
        self.assertIn(" collect ", res["next_command"])
        self.assertTrue(any("還在跑" in item for item in res["blocked_on"]))

    def test_h3d_next_json_output(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = h3d.main(["next", "--root", str(self.root), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["stage"], 6)
        for key in ("stage_title", "status", "blocked_on", "action", "next_command", "read", "notes", "done"):
            self.assertIn(key, payload)
        text = io.StringIO()
        with redirect_stdout(text):
            h3d.main(["--root", str(self.root), "next"])
        self.assertIn("下一步", text.getvalue())


if __name__ == "__main__":
    unittest.main()
