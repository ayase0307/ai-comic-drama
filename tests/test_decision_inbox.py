"""決策收件匣（h3d inbox）、自動核准（h3d approve --auto）、舊結論轉換（h3d verdict import）。"""
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, SCRIPTS / "storyboard", SCRIPTS / "review", Path(__file__).resolve().parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import auto_approve  # noqa: E402
import decisions  # noqa: E402
import h3d  # noqa: E402
import inbox  # noqa: E402
import next_step  # noqa: E402
import project_state as ps  # noqa: E402
import verdict_import  # noqa: E402
import verdicts  # noqa: E402
from test_enforce_flow import ALL_IDS, TwoEpisodeProject  # noqa: E402


import sys as _sys, pathlib as _pl  # noqa: E401,E402
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import _content_gate  # noqa: E402


def setUpModule():
    _content_gate.disable()


def tearDownModule():
    _content_gate.enable()



def _ids(cards):
    return [c["id"] for c in cards]


class InboxCardTests(TwoEpisodeProject):
    def test_unreviewed_segments_are_my_work_not_a_card(self):
        self.write_qa()
        built = inbox.build_cards(self.root)
        self.assertFalse([c for c in built["open"] if c["kind"] == "verdict"])
        self.assertTrue(any("等我目視" in n for n in built["notes"]))

    def test_fail_verdict_becomes_blocking_card_with_three_options(self):
        self.write_qa()
        verdicts.set_verdict(self.root, "EP01-S01", "fail", "末鏡燒出簡體字幕", ["videos/qa/tile.jpg"],
                             issues=["burned_subtitle"])
        verdicts.set_verdict(self.root, "EP02-S01", "pass", "OK", ["videos/qa/tile.jpg"])
        cards = inbox.build_cards(self.root)["open"]
        card = next(c for c in cards if c["id"] == "D6-EP01-S01")
        self.assertEqual(card["blocking"], 2)
        self.assertEqual(len(card["options"]), 3)
        self.assertIn("畫面燒進字幕", card["impact"])
        self.assertTrue(all(o["reply"].startswith("EP01-S01：") for o in card["options"]))
        self.assertEqual(cards[0]["id"], "D6-EP01-S01", "會擋下一步的卡排最前面")

    def test_custom_card_fields_from_verdict_are_used(self):
        self.write_qa()
        verdicts.set_verdict(self.root, "EP01-S01", "warn", "簿頁畫成紅界格", ["videos/qa/tile.jpg"],
                             impact="伏筆讀不出來", recommendation="後製疊墨線",
                             options=[{"label": "後製疊墨線", "reply": "EP01-S01：後製疊九道墨線"},
                                      {"label": "維持現狀", "reply": "EP01-S01：不處理"}])
        card = next(c for c in inbox.build_cards(self.root)["open"] if c["id"] == "D6-EP01-S01")
        self.assertEqual(card["impact"], "伏筆讀不出來")
        self.assertEqual(card["options"][0]["label"], "後製疊墨線")

    def test_many_plain_warns_are_grouped_into_one_card(self):
        self.write_qa()
        for sid in ALL_IDS:
            verdicts.set_verdict(self.root, sid, "warn", f"{sid} 佩刀像日本刀", ["videos/qa/tile.jpg"])
        with patch.object(inbox, "MAX_GROUP_WARN", 1):
            cards = inbox.build_cards(self.root)["open"]
        self.assertIn("D6-warn-group", _ids(cards))
        self.assertNotIn("D6-EP01-S01", _ids(cards))

    def test_user_verdict_goes_to_decided_not_open(self):
        self.write_qa()
        verdicts.set_verdict(self.root, "EP01-S01", "pass", "老大：先當通過", ["videos/qa/tile.jpg"], decided_by="user")
        built = inbox.build_cards(self.root)
        self.assertNotIn("D6-EP01-S01", _ids(built["open"]))
        self.assertTrue(any("EP01-S01" in d["title"] for d in built["decided"]))

    def test_missing_decision_card(self):
        (self.root / "decisions.json").unlink()
        cards = inbox.build_cards(self.root)["open"]
        self.assertIn("D2-decide-style", _ids(cards))
        self.assertTrue(all(c["blocking"] == 1 for c in cards if c["kind"] == "decision"))

    def test_voice_cast_card_lists_narration_speakers_until_user_decides(self):
        self.write_qa()
        seg = self.root / "segments-ep01.json"
        data = json.loads(seg.read_text(encoding="utf-8"))
        data["segments"][0]["external_narration"] = [{"speaker": "C-disciple-a", "line": "我忘了"}]
        seg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        card = next(c for c in inbox.build_cards(self.root)["open"] if c["kind"] == "voice")
        self.assertEqual(card["characters"], ["C-disciple-a"])
        decisions.decide(self.root, "voice:C-disciple-a", "內建音色 冯老师", "弟子甲用內建音色")
        self.assertFalse([c for c in inbox.build_cards(self.root)["open"] if c["kind"] == "voice"])

    def test_technical_override_card_when_policy_does_not_cover(self):
        self.write_qa(failing={"EP01-S01": "WEIRD_METRIC: 0.1"})
        verdicts.set_verdict(self.root, "EP01-S01", "pass", "看過 OK", ["videos/qa/tile.jpg"])
        verdicts.set_verdict(self.root, "EP02-S01", "pass", "OK", ["videos/qa/tile.jpg"])
        self.assertIn("D6-technical-override", _ids(inbox.build_cards(self.root)["open"]))

    def test_policy_accepted_technical_issue_is_auto_line_not_card(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE: chroma 0.02"})
        verdicts.set_verdict(self.root, "EP01-S01", "pass", "低彩度是設定", ["videos/qa/tile.jpg"])
        verdicts.set_verdict(self.root, "EP02-S01", "pass", "OK", ["videos/qa/tile.jpg"])
        built = inbox.build_cards(self.root)
        self.assertNotIn("D6-technical-override", _ids(built["open"]))
        self.assertTrue(any("可接受" in a["text"] for a in built["auto"]))

    def test_build_writes_standalone_html_and_json(self):
        self.write_qa()
        verdicts.set_verdict(self.root, "EP01-S01", "fail", "❌【11:15 重跑收件】燒字幕。其餘 OK", ["videos/qa/tile.jpg"],
                             issues=["burned_subtitle"])
        result = inbox.build(self.root, strips="none")
        page = result["html"].read_text(encoding="utf-8")
        self.assertIn('id="D6-EP01-S01"', page)
        self.assertIn('data-reply="EP01-S01：', page)
        self.assertIn("EP01-S01：燒字幕</h3>", page, "卡片標題去掉 ❌ 與【時間】標籤，只留一句話")
        self.assertNotIn('src="http', page)
        self.assertIn("../videos/EP01-S01.mp4", page)
        self.assertLess(result["bytes"], 5 * 1024 * 1024)
        model = json.loads(result["json"].read_text(encoding="utf-8"))
        self.assertEqual(model["cards"][0]["id"], "D6-EP01-S01")
        self.assertNotIn("evidence_b64", model["cards"][0])

    def test_real_image_evidence_is_embedded_as_data_uri(self):
        from PIL import Image
        self.write_qa()
        Image.new("RGB", (64, 36), "red").save(self.root / "videos" / "qa" / "real.png")
        verdicts.set_verdict(self.root, "EP01-S01", "fail", "多出人", ["videos/qa/real.png"], issues=["extra_person"])
        page = inbox.build(self.root, strips="none")["html"].read_text(encoding="utf-8")
        self.assertIn('src="data:image/', page)

    def test_cli_entry_points(self):
        self.write_qa()
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(h3d.main(["--root", str(self.root), "inbox", "--strips", "none"]), 0)
        self.assertTrue((self.root / "review" / "inbox.html").is_file())
        (self.root / "review" / "inbox.html").unlink()
        proc = subprocess.run([sys.executable, str(SCRIPTS / "build_stage_review.py"), "--project-dir", str(self.root),
                               "--inbox", "--inbox-strips", "none"], capture_output=True, text=True,
                              encoding="utf-8", timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.root / "review" / "inbox.html").is_file())


class ReviewPageSpecTests(TwoEpisodeProject):
    """references/review-page-spec.md：卡片欄位、≤5 張、blocking 值域、舊頁收合、next 指向收件匣。"""

    def _eight_fails(self):
        segs = {f"EP01-S{i:02d}": {"effective": "fail", "reason": f"第 {i} 段燒出字幕", "issues": ["burned_subtitle"],
                                   "source": "agent"} for i in range(1, 9)}
        return {"segments": segs, "counts": {"fail": 8}, "policy": {"accept": []}, "policy_is_decided": True}

    def test_eight_fail_segments_merge_into_at_most_five_cards(self):
        with patch.object(inbox.verdicts_mod, "classify", return_value=self._eight_fails()):
            model = inbox.collect(self.root, images=False, strips="none")
        cards = model["cards"]
        self.assertLessEqual(len(cards), inbox.MAX_OPEN_CARDS)
        merged = [c for c in cards if c["kind"] == "merged"]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["blocking"], 2, "合併卡 blocking 取組內最高（數字最小）")
        self.assertEqual(len(merged[0]["merged"]) + len(cards) - 1, 8, "沒有卡被丟掉")
        page = inbox.render_html(model)
        self.assertIn("階段6/7・", page)
        self.assertIn("件待決・卡在", page)

    def test_every_card_has_spec_fields(self):
        (self.root / "decisions.json").unlink()  # 缺定案卡
        with patch.object(inbox.verdicts_mod, "classify", return_value=self._eight_fails()):
            model = inbox.collect(self.root, images=False, strips="none")
        self.assertTrue(model["cards"])
        for card in model["cards"]:
            self.assertTrue(card["if_ignored"], card["id"])
            self.assertIn(len(card["options"]), (2, 3), card["id"])
            self.assertTrue(all(o.get("reply") for o in card["options"]), card["id"])
            self.assertIn(card["blocking"], inbox.VALID_BLOCKING, card["id"])
            self.assertLessEqual(len(card["question"]), inbox.MAX_QUESTION, card["id"])
            self.assertEqual(card["recommended_option"], card["options"][0]["label"])
        self.assertEqual(model["problems"], [], "內建產卡處都寫了 if_ignored／合法 blocking／2–3 選項")
        page = inbox.render_html(model)
        self.assertIn("<dt>不回覆</dt>", page)

    def test_validate_model_normalizes_user_options_without_crashing(self):
        card = {"id": "D6-X", "kind": "verdict", "stage": 6, "segment": "X", "title": "長" * 80, "impact": "i",
                "recommendation": "r", "options": [{"label": "a", "reply": "X：a"}], "blocking": 3, "source": "s"}
        model = inbox.validate_model({"cards": [card]})
        out = model["cards"][0]
        self.assertEqual(len(out["options"]), 2)
        self.assertEqual(out["blocking"], 2)
        self.assertEqual(len(out["title"]), inbox.MAX_QUESTION)
        self.assertTrue(out["if_ignored"])
        self.assertEqual(len(model["problems"]), 3)
        with self.assertRaises(ValueError):
            inbox.validate_model({"cards": [{"id": "D-bad", "kind": "x"}]})

    def test_approval_card_requires_current_review_snapshot(self):
        state = ps.load_state(self.root)
        ps.mark_awaiting_review(self.root, state, 6)
        with patch.object(inbox.verdicts_mod, "classify",
                          return_value={"segments": {}, "counts": {}, "policy": {}, "policy_is_decided": True}):
            card = next(c for c in inbox.build_cards(self.root)["open"] if c["id"] == "D6-approve")
            self.assertIn("審核快照", card["options"][0]["reply"])
            self.assertEqual(len(card["review_snapshot"]), 8)
            (self.root / "videos" / "EP01-S01.mp4").write_bytes(b"changed")  # 快照過期
            built = inbox.build_cards(self.root)
        self.assertNotIn("D6-approve", _ids(built["open"]))
        self.assertTrue(any("審核快照已過期" in n for n in built["notes"]))

    def test_stage5_page_folds_every_prompt(self):
        import build_stage_review as bsr
        seg = self.root / "segments-ep01.json"
        data = json.loads(seg.read_text(encoding="utf-8"))
        data["segments"][0]["h3_prompt"] = "subject_definitions:\n<Subject 1> is a man.\nsummary:\nA man walks."
        seg.write_text(json.dumps(data), encoding="utf-8")
        _, _, page = bsr.build_stage_5(self.root, ps.load_state(self.root))
        docs = page.count('class="prompt-doc"')
        self.assertGreaterEqual(docs, 2)
        self.assertEqual(page.count('<details class="prompt-fold">'), docs)
        self.assertIn("舊版除錯頁", page)
        self.assertIn("inbox.html", page)
        self.assertNotIn("17 條 H3 防偷懶自檢", page)

    def test_render_issues_shows_three_and_folds_the_rest(self):
        import build_stage_review as bsr
        errors = [f"EP01-S{i:02d}: 參考圖不存在 `x.png`" for i in range(1, 6)] + [f"第 {i} 種錯" for i in range(5)]
        out = bsr.render_issues(errors)
        visible = out.split("<details>")[0]
        self.assertEqual(visible.count("<li>"), 3)
        self.assertIn("5 處（EP01-S01、EP01-S02、EP01-S03…）", visible)
        self.assertIn("其餘 3 條", out)

    def test_next_step_points_awaiting_stage_to_inbox(self):
        self.write_qa()
        ps.mark_awaiting_review(self.root, ps.load_state(self.root), 6)
        res = next_step.plan(self.root)
        self.assertEqual(res["status"], "awaiting_user_approval")
        self.assertIn("inbox", res["action"])
        self.assertIn("停下", res["action"])


class AutoApproveTests(TwoEpisodeProject):
    def pass_all(self):
        for sid in ALL_IDS:
            verdicts.set_verdict(self.root, sid, "pass", "OK", ["videos/qa/tile.jpg"])

    def test_auto_approve_cannot_cover_stage_0_or_2(self):
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "auto_approve", "1,2,3", "全自動")
        res = auto_approve.evaluate(self.root, 2)
        self.assertFalse(res["eligible"])
        self.assertIn("永遠要人決定", res["blockers"][0])

    def test_without_user_authorization_stage6_is_not_auto(self):
        self.write_qa()
        self.pass_all()
        res = auto_approve.evaluate(self.root, 6)
        self.assertFalse(res["eligible"])
        self.assertTrue(any("沒有授權" in b for b in res["blockers"]))

    def test_stage6_auto_approves_and_records_basis(self):
        self.write_qa()
        self.pass_all()
        decisions.decide(self.root, "auto_approve", "3,4,5,6", "睡前授權全自動執行後面的東西")
        res = auto_approve.run(self.root, 6)
        self.assertTrue(res["eligible"], res["blockers"])
        self.assertTrue(ps.is_approved(self.root, 6))
        entry = ps.load_state(self.root)["stages"]["stage-6"]
        record = entry["auto_approval"]
        self.assertEqual({p["id"] for p in record["policy"]}, {"auto_approve", "acceptance_policy"})
        self.assertEqual(record["verdicts"]["segments"]["EP01-S01"]["effective"], "pass")
        self.assertIn("睡前授權", entry["user_note"])
        self.assertEqual(ps.state_integrity(self.root), "ok")

    def test_policy_accepted_technical_issue_is_overridden_with_reason(self):
        self.write_qa(failing={"EP01-S01": "STYLE_BLEED_GRAYSCALE: chroma 0.02"})
        self.pass_all()
        decisions.decide(self.root, "auto_approve", "6", "照政策自動過")
        res = auto_approve.run(self.root, 6)
        self.assertTrue(res["eligible"], res["blockers"])
        entry = ps.load_state(self.root)["stages"]["stage-6"]
        self.assertIn("low_chroma", entry["override"]["reason"])
        self.assertTrue(ps.is_approved(self.root, 6))

    def test_technical_issue_outside_policy_blocks(self):
        self.write_qa(failing={"EP01-S01": "WEIRD_METRIC: 0.1"})
        self.pass_all()
        decisions.decide(self.root, "auto_approve", "6", "照政策自動過")
        res = auto_approve.run(self.root, 6)
        self.assertFalse(res["eligible"])
        self.assertFalse(ps.is_approved(self.root, 6))

    def test_open_card_blocks(self):
        self.write_qa()
        self.pass_all()
        verdicts.set_verdict(self.root, "EP02-S01", "warn", "佩刀像日本刀", ["videos/qa/tile.jpg"])
        decisions.decide(self.root, "auto_approve", "6", "照政策自動過")
        res = auto_approve.evaluate(self.root, 6)
        self.assertFalse(res["eligible"])
        self.assertTrue(any("未決卡" in b for b in res["blockers"]))

    def test_stage7_requires_user_voice_for_every_narration_speaker(self):
        seg = self.root / "segments-ep02.json"
        data = json.loads(seg.read_text(encoding="utf-8"))
        data["segments"][0]["external_narration"] = [{"speaker": "C-passerby", "line": "走吧"}]
        seg.write_text(json.dumps(data), encoding="utf-8")
        decisions.decide(self.root, "auto_approve", "7", "照政策自動過")
        res = auto_approve.evaluate(self.root, 7)
        self.assertTrue(any("C-passerby" in b for b in res["blockers"]))
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "voice:C-passerby", "內建", "你決定就好", by="user_delegated")

    def test_next_suggests_auto_approve_when_eligible(self):
        self.write_qa()
        self.pass_all()
        decisions.decide(self.root, "auto_approve", "6", "照政策自動過")
        res = next_step.plan(self.root)
        self.assertIn("approve --auto --stage 6", res["next_command"] or "")

    def test_h3d_approve_requires_auto_flag(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(h3d.main(["--root", str(self.root), "approve"]), 2)
            self.assertEqual(h3d.main(["--root", str(self.root), "approve", "--auto", "--stage", "2"]), 1)


class VerdictImportTests(TwoEpisodeProject):
    def write_legacy(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_line_parsing(self):
        self.assertEqual(verdict_import.parse_line("✅【08:47】OK"), "pass")
        self.assertEqual(verdict_import.parse_line("✅（附註）【11:15】紅界格"), "warn")
        self.assertEqual(verdict_import.parse_line("⚠️ 偏老"), "warn")
        self.assertEqual(verdict_import.parse_line("❌ 多一張臉"), "fail")
        self.assertIsNone(verdict_import.parse_line(""))
        self.assertEqual(verdict_import.current_part("✅ 新判 OK；原判：❌ 多一張臉"), "✅ 新判 OK；")

    def test_pass_only_gets_accept_like_issue_codes(self):
        self.assertEqual(verdict_import.infer_issues("由平塗卡通改回半寫實；紙上寫字屬紙面出字", "pass"), ["paper_text"])
        self.assertIn("style_shift", verdict_import.infer_issues("畫風突變成平塗卡通", "fail"))

    def test_convert_maps_verdicts_rulings_and_skips(self):
        legacy = self.write_legacy("conclusions-ep01.json", {
            "EP01-S01": "❌【08:47】末鏡燒字幕「我不记得」；原判：✅ 本來以為 OK",
            "EP02-S01": "✅【08:47 新標準：暫時通過】原判：❌ 記名簿頁上寫出成行字",
            "EP01-S01-take3": "✅ 重抽 OK",
            "EP09-X": "",
            "_驗收標準_20261022": "老大新驗收標準：紙面出字不算問題",
            "_老大裁示_20261022": {"EP02-S01": "09:26 老大：先當通過（頭巾）"},
        })
        report = verdict_import.convert(self.root, [legacy])
        segs = report["data"]["segments"]
        self.assertEqual(segs["EP01-S01"]["verdict"], "fail")
        self.assertEqual(segs["EP01-S01"]["issues"], ["burned_subtitle"])
        self.assertNotIn("原判", segs["EP01-S01"]["reason"])
        self.assertEqual(segs["EP02-S01"]["decided_by"], "user", "使用者裁示蓋過同檔 agent 結論")
        self.assertEqual(segs["EP02-S01"]["evidence"], "videos/EP02-S01.mp4")
        self.assertIn("video_sha256", segs["EP02-S01"])
        self.assertNotIn("EP01-S01-take3", segs)
        skipped = {s["segment_id"] for s in report["skipped"]}
        self.assertEqual(skipped, {"EP01-S01-take3", "EP09-X"})
        self.assertTrue(report["policy_hints"])

    def test_existing_user_verdict_is_not_overwritten(self):
        verdicts.set_verdict(self.root, "EP01-S01", "pass", "老大說過", ["videos/qa/tile.jpg"], decided_by="user")
        legacy = self.write_legacy("c.json", {"EP01-S01": "❌ 多一張臉"})
        report = verdict_import.convert(self.root, [legacy])
        self.assertEqual(report["data"]["segments"]["EP01-S01"]["decided_by"], "user")
        report = verdict_import.convert(self.root, [legacy], overwrite=True)
        self.assertEqual(report["data"]["segments"]["EP01-S01"]["verdict"], "fail")

    def test_cli_dry_run_and_write(self):
        legacy = self.write_legacy("c.json", {"EP01-S01": "✅ OK", "EP02-S01": "⚠️ 偏老"})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(h3d.main(["--root", str(self.root), "verdict", "import", str(legacy), "--dry-run"]), 0)
        self.assertFalse((self.root / "review" / "verdicts.json").is_file())
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(h3d.main(["--root", str(self.root), "verdict", "import", str(legacy)]), 0)
        data = verdicts.load(self.root)
        self.assertEqual(data["segments"]["EP02-S01"]["issues"], ["aged_face"])
        self.assertEqual(data["segments"]["EP02-S01"]["imported_from"]["key"], "EP02-S01")
        self.write_qa()
        summary = verdicts.classify(self.root)
        self.assertEqual(summary["counts"]["unreviewed"], 0)


if __name__ == "__main__":
    unittest.main()
