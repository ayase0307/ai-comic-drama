"""長篇漫劇預設（series_format=longform）與事件交代完整性檢查。

背景：《我修的是遺忘課》被舊預設切成 10 集、每集 80–100 秒，事件交代不清。
新預設：整部一支連續長片、每個事件交代起因→經過→結果；短劇短集只在使用者明確選擇時啟用。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ADAPT = SCRIPTS / "adapt"
for p in (SCRIPTS, ADAPT, SCRIPTS / "craft"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import series_format  # noqa: E402
import event_coverage  # noqa: E402
import estimate_duration  # noqa: E402
import init_project  # noqa: E402
from validate_structure import parse_and_validate_script  # noqa: E402


def write_decision(root: Path, value: str) -> None:
    (root / "decisions.json").write_text(json.dumps({
        "version": 1,
        "decisions": [{"id": "series_format", "value": value, "by": "user", "quote": value}],
    }, ensure_ascii=False), encoding="utf-8")


def scene(sid, refs, expo=None, changes=None, sec=(10, 20)):
    sc = {"scene_id": sid, "source_refs": refs, "estimated_duration_seconds": {"min": sec[0], "max": sec[1]},
          "adaptation_changes": changes or []}
    if expo is not None:
        sc["event_exposition"] = expo
    return sc


class SeriesFormatTests(unittest.TestCase):
    def test_default_is_longform(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(series_format.project_format(Path(d)), "longform")
        self.assertEqual(series_format.project_format(None), "longform")

    def test_short_only_when_user_decides(self):
        with tempfile.TemporaryDirectory() as d:
            write_decision(Path(d), "做成竪屏短劇，每集 90 秒")
            self.assertEqual(series_format.project_format(Path(d)), "short")
            write_decision(Path(d), "長篇漫劇，不要短集")
            self.assertEqual(series_format.project_format(Path(d)), "longform")

    def test_project_md_field(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "project.md").write_text("- 成片形式：短劇短集（使用者明確選擇）：3 集\n", encoding="utf-8")
            self.assertTrue(series_format.is_short(Path(d)))
            (Path(d) / "project.md").write_text("- 成片形式：<longform | short>\n", encoding="utf-8")
            self.assertFalse(series_format.is_short(Path(d)))


class EventCoverageTests(unittest.TestCase):
    SOURCE = {
        "must_keep": ["U1"],
        "story_units": [
            {"unit_id": "U1", "summary": "主角被逐出師門", "expected_grade": "MUST_KEEP", "needs_motivation": True},
            {"unit_id": "U2", "summary": "書院入學", "expected_grade": "KEEP_IF_POSSIBLE", "time_place_shift": "三日後・書院"},
            {"unit_id": "U3", "summary": "遺忘課第一堂", "expected_grade": "KEEP_IF_POSSIBLE"},
            {"unit_id": "U4", "summary": "茶館閒聊", "expected_grade": "REMOVE"},
            {"unit_id": "U5", "summary": "舊友相認", "expected_grade": "MUST_KEEP"},
            {"unit_id": "U6", "summary": "夜探藏書閣", "expected_grade": "KEEP_IF_POSSIBLE"},
            {"unit_id": "U7", "summary": "師父的信", "expected_grade": "MUST_KEEP"},
        ],
    }

    def handoff(self):
        return {"episodes": [{"episode_id": "EP01", "scenes": [
            scene("EP01-S01", ["U1"], {"U1": ["起因", "經過", "結果", "動機"]}),
            scene("EP01-S02", ["U2"], {"U2": ["cause", "result"]}),  # 缺經過、時地
            scene("EP01-S03", ["U3"]),  # 沒標註
            scene("EP01-S04", ["U5"], {"U5": ["結果"]},
                  changes=[{"type": "compress", "source_ref": "U5"}]),
            scene("EP01-S05", ["U3"], {}, changes=[{"type": "remove", "source_ref": "U4"},
                                                   {"type": "remove", "source_ref": "U6"}]),
        ]}]}

    def test_statuses(self):
        res = event_coverage.analyze_event_coverage(self.SOURCE, [self.handoff()])
        by = {e["unit_id"]: e for e in res["events"]}
        self.assertEqual(by["U1"]["status"], "full")
        self.assertEqual(by["U1"]["required_beats"], ["起因", "經過", "結果", "動機"])
        self.assertEqual(by["U2"]["status"], "partial")
        self.assertEqual(by["U2"]["missing_beats"], ["經過", "時地"])
        self.assertEqual(by["U3"]["status"], "unverified")
        self.assertEqual(by["U4"]["status"], "skipped")
        self.assertTrue(by["U4"]["planned_by_grade"])
        self.assertFalse(by["U4"]["needs_decision"])  # 原著分級就是 REMOVE
        self.assertEqual(by["U5"]["status"], "compressed")
        self.assertTrue(by["U5"]["needs_decision"])  # MUST_KEEP 被壓縮要問使用者
        self.assertEqual(by["U6"]["status"], "skipped")
        self.assertTrue(by["U6"]["needs_decision"])
        self.assertEqual(by["U7"]["status"], "missing")
        self.assertEqual(res["must_keep_missing"], ["U7"])
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(set(res["needs_decision"]), {"U2", "U3", "U5", "U6", "U7"})

    def test_markdown_lists_decisions(self):
        res = event_coverage.analyze_event_coverage(self.SOURCE, [self.handoff()])
        md = event_coverage.render_markdown(res)
        self.assertIn("請使用者逐條決定", md)
        self.assertIn("缺少交代：經過、時地", md)
        self.assertIn("`U7` 師父的信", md)

    def test_cli_exit_code_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "adapt").mkdir()
            (root / "adapt" / "source.json").write_text(json.dumps(self.SOURCE, ensure_ascii=False), encoding="utf-8")
            (root / "handoff-ep01.json").write_text(json.dumps(self.handoff(), ensure_ascii=False), encoding="utf-8")
            out = root / "adapt" / "event-coverage.md"
            r = subprocess.run([sys.executable, str(ADAPT / "event_coverage.py"), "--project-dir", str(root),
                                "--out", str(out)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertTrue(out.is_file())
            src = dict(self.SOURCE, story_units=self.SOURCE["story_units"][:1], must_keep=["U1"])
            (root / "adapt" / "source.json").write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, str(ADAPT / "event_coverage.py"), "--project-dir", str(root), "--json"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["status"], "PASS")

    def test_script_exposition_comment_parsed(self):
        script = ("第01集｜測試\n\n1-1 書院 日/內\n<!-- source: U01 -->\n<!-- exposition: U01 起因 經過、結果 -->\n"
                  "人物：林澈\n△林澈推門而入。\n林澈：我回來了。\n")
        sc = parse_and_validate_script(script)["scenes"][0]
        self.assertEqual(sc["event_exposition"], {"U01": ["起因", "經過", "結果"]})


class DurationEstimateTests(unittest.TestCase):
    def units(self, n, **extra):
        return {"story_units": [dict({"unit_id": f"U{i}", "summary": f"事件{i}", "expected_grade": "MUST_KEEP"}, **extra)
                                for i in range(n)]}

    def test_event_based_total_scales_with_events_not_episodes(self):
        r5 = estimate_duration.estimate_event_based_duration(self.units(5))
        r10 = estimate_duration.estimate_event_based_duration(self.units(10))
        self.assertAlmostEqual(r10["estimated_total_seconds"]["mid"], 2 * r5["estimated_total_seconds"]["mid"])
        split = estimate_duration.estimate_event_based_duration(self.units(10), episodes=10)
        self.assertEqual(split["estimated_total_seconds"], r10["estimated_total_seconds"])  # 分集不改總長
        self.assertIn("avg_episode_seconds", split)
        self.assertNotIn("avg_episode_seconds", r10)
        # 每個事件三個交代要素（8–15 秒）→ 10 個事件至少 240 秒，遠超 1 集 80–100 秒
        self.assertGreaterEqual(r10["estimated_total_seconds"]["min"], 240)

    def test_exposition_needs_and_grades(self):
        base = estimate_duration.estimate_event_based_duration(self.units(1))["estimated_total_seconds"]["mid"]
        more = estimate_duration.estimate_event_based_duration(
            self.units(1, needs_motivation=True, time_place_shift=True))["estimated_total_seconds"]["mid"]
        self.assertGreater(more, base)
        src = {"story_units": [{"unit_id": "A", "expected_grade": "REMOVE"},
                               {"unit_id": "B", "expected_grade": "COMPRESS"}]}
        res = estimate_duration.estimate_event_based_duration(src)
        self.assertEqual(res["events"][0]["estimated_seconds"], {"min": 0.0, "max": 0.0})
        self.assertEqual(res["exposition_beats_total"], 1)

    def test_novel_longform_has_no_episode_gate(self):
        text = "第一章\n" + "「你好啊，我們今天去哪裡吃飯比較好呢。」他說。\n" * 200
        lf = estimate_duration.estimate_novel_duration(text)
        self.assertEqual(lf["series_format"], "longform")
        self.assertEqual(lf["status"], "PASS")
        self.assertEqual(lf["policies_projection"]["policy_1"]["episodes_needed"], 1)
        self.assertIsNone(lf["target_seconds_per_episode"])
        sh = estimate_duration.estimate_novel_duration(text, series_format="short")
        self.assertEqual(sh["status"], "BLOCKED")
        self.assertEqual(sh["target_seconds_per_episode"], 90.0)
        self.assertGreater(sh["policies_projection"]["policy_1"]["episodes_needed"], 1)

    def test_script_over_budget_advice_depends_on_format(self):
        script = ("第01集｜測試\n\n1-1 書院 日/內\n人物：林澈\n△林澈推門而入，四下張望後走向書架。\n"
                  + "林澈：這裡的書都被人翻過了，我得找到那封信。\n" * 8)
        lf = estimate_duration.estimate_script_duration(script, target_seconds=10)
        self.assertEqual(lf["budget_status"], "OVER_BUDGET")
        self.assertFalse(any("拆成上下集" in a for a in lf["compression_advice"]))
        self.assertTrue(any("不為了秒數壓縮事件" in a for a in lf["compression_advice"]))
        sh = estimate_duration.estimate_script_duration(script, target_seconds=10, series_format="short")
        self.assertTrue(any("拆成上下集" in a for a in sh["compression_advice"]))
        # 長篇模式沒給目標 → 不做預算比對
        self.assertEqual(estimate_duration.estimate_script_duration(script)["budget_status"], "PASS")

    def test_cli_events_and_short_default_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "source.json"
            src.write_text(json.dumps(self.units(4), ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, str(ADAPT / "estimate_duration.py"), "--events", str(src), "--json"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["event_count"], 4)
            novel = root / "n.txt"
            novel.write_text("第一章\n" + "「你好啊。」他說。\n" * 300, encoding="utf-8")
            r = subprocess.run([sys.executable, str(ADAPT / "estimate_duration.py"), "--novel-file", str(novel), "--json"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0)
            self.assertEqual(json.loads(r.stdout)["series_format"], "longform")
            write_decision(root, "short")
            r = subprocess.run([sys.executable, str(ADAPT / "estimate_duration.py"), "--novel-file", str(novel), "--json"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(json.loads(r.stdout)["target_seconds_per_episode"], 90.0)


class InitProjectTests(unittest.TestCase):
    def test_default_is_one_continuous_longform(self):
        files = init_project.build_files("遺忘課", 1, "demo")
        md = files["project.md"]
        self.assertIn("長篇漫劇（預設）", md)
        self.assertNotIn("90 秒", md)
        self.assertIn("事件清單與段落規劃", md)
        handoff = json.loads(files["handoff-ep01.json"])
        self.assertNotIn("target_duration_seconds", handoff["episodes"][0])
        self.assertNotIn("script-ep02.md", files)
        src = json.loads(files["adapt/source.json"])
        self.assertEqual(src["story_units"][0]["exposition_needs"], ["起因", "經過", "結果"])

    def test_user_requested_split_has_no_per_episode_seconds(self):
        files = init_project.build_files("遺忘課", 3, "demo")
        self.assertIn("使用者要求分 3 集", files["project.md"])
        self.assertNotIn("target_duration_seconds", json.loads(files["handoff-ep03.json"])["episodes"][0])

    def test_short_mode_is_opt_in(self):
        files = init_project.build_files("遺忘課", 12, "demo", "short", 90)
        self.assertIn("短劇短集（使用者明確選擇）", files["project.md"])
        self.assertEqual(json.loads(files["handoff-ep12.json"])["episodes"][0]["target_duration_seconds"], 90)


class ReviewAndLensTests(unittest.TestCase):
    def test_stage1_review_shows_event_coverage(self):
        import build_stage_review as review
        import project_state as ps
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            subprocess.run([sys.executable, str(SCRIPTS / "init_project.py"), str(root), "--title", "測試"],
                           capture_output=True, text=True, encoding="utf-8", check=True)
            _ok, _err, html_out = review.build_stage_1(root, ps.load_state(root))
            self.assertIn('id="event-coverage"', html_out)
            self.assertIn("事件交代待決定", html_out)
            _ok, _err, html0 = review.build_stage_0(root, ps.load_state(root))
            self.assertIn("長篇漫劇（預設）", html0)

    def test_hit_lens_marked_short_only(self):
        import hit_review
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "project.md").write_text("# 測試\n受眾：學生\n", encoding="utf-8")
            text = hit_review.run(p, 0, "EP01", None, None).read_text(encoding="utf-8")
            self.assertIn("本專案是長篇漫劇", text)
            write_decision(p, "short")
            text = hit_review.run(p, 0, "EP01", None, None).read_text(encoding="utf-8")
            self.assertNotIn("本專案是長篇漫劇", text)

    def test_compare_adaptation_no_implicit_90s_in_longform(self):
        from compare_adaptation import evaluate_adaptation
        script = "第01集｜測試\n\n1-1 書院 日/內\n<!-- source: U1 -->\n人物：林澈\n△林澈推門而入。\n林澈：我回來了。\n"
        source = {"story_units": [{"unit_id": "U1", "summary": "回書院", "expected_grade": "MUST_KEEP"}]}
        handoff = {"episodes": [{"episode_id": "EP01", "scenes": [scene("EP01-S01", ["U1"], {"U1": ["起因", "經過", "結果"]})]}]}
        res = evaluate_adaptation(source, handoff, script)
        self.assertEqual(res["series_format"], "longform")
        self.assertFalse(any("DURATION_UNDER_BUDGET" in w for w in res["warnings"]))
        self.assertEqual(res["event_coverage"]["counts"]["full"], 1)
        short = evaluate_adaptation(source, handoff, script, series_format="short")
        self.assertTrue(any("DURATION_UNDER_BUDGET" in w for w in short["warnings"]))


if __name__ == "__main__":
    unittest.main()
