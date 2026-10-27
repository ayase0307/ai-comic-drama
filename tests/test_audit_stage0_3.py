# -*- coding: utf-8 -*-
"""階段 0–3＋創作 lens 體檢（fix/audit-stage0-3）的回歸測試。

用 tests/fixtures/audit_fogport（自編小說《霧港奇譚》：3 章、2 個角色、1 頭生物）在
「中文＋含空白」的路徑下實跑 init → 定案 → 階段 0–3 的腳本，鎖住這次修掉的問題。
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "audit_fogport"
for extra in (SCRIPTS, SCRIPTS / "adapt", SCRIPTS / "storyboard", SCRIPTS / "craft"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import araki_review  # noqa: E402
import build_stage_review as bsr  # noqa: E402
import decisions  # noqa: E402
import export_asset_prompts as eap  # noqa: E402
import extract_chapter as ec  # noqa: E402
import init_project  # noqa: E402
import project_state as ps  # noqa: E402
import stage_content_checks as scc  # noqa: E402
import sync_script  # noqa: E402
from project_ids import slugify_project  # noqa: E402
from validate_character_bible import validate_character_bible  # noqa: E402
from validate_structure import parse_and_validate_script  # noqa: E402


def run(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True,
                          text=True, encoding="utf-8", cwd=cwd)


def make_project(base: Path, name: str = "霧港 專案") -> Path:
    """init 一個中文＋空白路徑的專案，套上 fixture 的階段 0–3 產物與比例 16:9 定案。"""
    root = base / "測試 資料夾" / name
    res = run(SCRIPTS / "init_project.py", root, "--title", "霧港奇譚", "--genre", "mystery_thriller")
    assert res.returncode == 0, res.stderr
    for src in FIXTURE.rglob("*"):
        if src.is_file():
            dst = root / src.relative_to(FIXTURE)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    from PIL import Image
    for stem in ("C-linwu_W01_sheet_v1", "C-laozhou_W01_sheet_v1", "CREATURE-fogwhale_sheet_v1",
                 "scene lighthouse-master"):
        Image.new("RGB", (64, 36), (120, 120, 130)).save(root / "images" / f"{stem}.png")
    decisions.decide(root, "style", "recommended", "照建議")
    decisions.decide(root, "aspect_ratio", "16:9", "橫的")
    decisions.decide(root, "dialogue_policy", "2", "只留重點句")
    decisions.decide(root, "design_engine", "codex", "用 codex")
    return root


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_project(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()


# ---------------------------------------------------------------- 階段 0

class InitProjectTests(unittest.TestCase):
    def test_chinese_folder_gets_distinct_valid_project_id(self):
        a, b = slugify_project("霧港"), slugify_project("我修的是遺忘課")
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^project-[0-9a-f]{8}$")
        self.assertEqual(slugify_project("My Drama"), "my-drama")  # ASCII 結果與舊版相同
        self.assertEqual(slugify_project(""), "project")

    def test_init_fills_explicit_genre_and_aspect_and_uses_hash_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "中文 專案"
            res = run(SCRIPTS / "init_project.py", root, "--genre", "wuxia_action", "--aspect-ratio", "16：9")
            self.assertEqual(res.returncode, 0, res.stderr)
            md = (root / "project.md").read_text(encoding="utf-8")
            self.assertIn("- genre_mode：wuxia_action", md)
            self.assertIn("- aspect_ratio：16:9", md)
            handoff = json.loads((root / "handoff-ep01.json").read_text(encoding="utf-8"))
            self.assertEqual(handoff["aspect_ratio"], "16:9")
            self.assertRegex(handoff["project_id"], r"^project-[0-9a-f]{8}$")
            # 重跑冪等：已存在的檔案略過
            again = run(SCRIPTS / "init_project.py", root)
            self.assertIn("已存在，略過", again.stdout)

    def test_init_without_flags_keeps_old_defaults(self):
        stub = init_project.handoff_stub("p", 1)
        self.assertEqual(stub["aspect_ratio"], "9:16")
        self.assertEqual(init_project.handoff_stub("p", 1, aspect_ratio="4:3")["aspect_ratio"], "other")

    def test_init_rejects_bad_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            for args in (["--episodes", "0"], ["--aspect-ratio", "橫"], ["--project-id", "大寫X"]):
                with self.subTest(args=args):
                    res = run(SCRIPTS / "init_project.py", Path(tmp) / "x", *args)
                    self.assertEqual(res.returncode, 2)
                    self.assertNotIn("Traceback", res.stderr)

    def test_cd_command_is_platform_aware(self):
        root = PurePosixPath("/tmp/a b/it's")
        self.assertEqual(init_project.cd_command(root, "linux"), "cd '/tmp/a b/it'\\''s'")
        self.assertTrue(init_project.cd_command(root, "win32").startswith("Set-Location -LiteralPath"))


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "decisions.json").write_text(json.dumps(decisions.empty_decisions()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_value_is_rejected_and_does_not_overwrite(self):
        decisions.decide(self.root, "aspect_ratio", "16:9", "橫")
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "aspect_ratio", "  ", "x")
        self.assertEqual(decisions.get(decisions.load(self.root), "aspect_ratio")["value"], "16:9")

    def test_aspect_ratio_and_dialogue_policy_are_normalized(self):
        self.assertEqual(decisions.decide(self.root, "aspect_ratio", "9：16", "豎")["value"], "9:16")
        self.assertEqual(decisions.decide(self.root, "aspect_ratio", "16x9", "橫")["value"], "16:9")
        entry = decisions.decide(self.root, "dialogue_policy", "2", "只留重點句")
        self.assertEqual(entry["value"], "②")
        self.assertIsNone(decisions.narration_policy_of(decisions.load(self.root)))  # 以前 "2" 會 raise
        self.assertEqual(decisions.decide(self.root, "dialogue_policy", "4 純旁白", "x")["value"], "④ 純旁白")

    def test_value_warnings_flag_values_that_break_later(self):
        self.assertTrue(decisions.value_warnings("dialogue_policy", "重點台詞上畫"))
        self.assertFalse(decisions.value_warnings("dialogue_policy", "② 只留重點句"))
        self.assertTrue(decisions.value_warnings("aspect_ratio", "橫屏"))

    def test_list_on_empty_project_shows_known_ids(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(decisions.main(["--list", "--root", str(self.root)]), 0)
        self.assertIn("aspect_ratio", buf.getvalue())
        self.assertIn("階段 2 前", buf.getvalue())


# ---------------------------------------------------------------- 階段 1

class ExtractChapterTests(unittest.TestCase):
    def test_chinese_numbers_with_zero_and_thousand(self):
        self.assertEqual(ec.parse_cn_number("第一百零五章"), 105)
        self.assertEqual(ec.parse_cn_number("一千零一"), 1001)
        self.assertEqual(ec.parse_cn_number("一千二百三十四"), 1234)
        self.assertEqual(ec.parse_cn_number("十一"), 11)

    def scan(self, text):
        return [(c.chapter_num, c.chapter_title) for c in ec.scan_novel_structure(text.splitlines(True))]

    def test_h1_chapter_headings_are_recognized(self):
        self.assertEqual(self.scan("# 第一章 a\n內文\n# 第二章 b\n內文\n"), [(1, "第一章 a"), (2, "第二章 b")])

    def test_short_plain_chapter_is_not_mistaken_for_toc(self):
        got = self.scan("第一章 a\n內文一\n\n第一百零五章 b\n內文二\n\n第一千零一章 c\n內文三\n")
        self.assertEqual([n for n, _ in got], [1, 105, 1001])

    def test_toc_with_volume_lines_is_still_skipped(self):
        toc = "目錄\n第一卷 起\n第一章 甲\n第二章 乙\n\n"
        body = "第一章 甲\n內文。\n第二章 乙\n內文。\n"
        self.assertEqual([n for n, _ in self.scan(toc + body)], [1, 2])

    def test_metrics_skip_plain_heading_line(self):
        m = ec.analyze_chapter_metrics(["第一章 甲", "內文"])
        self.assertEqual(m["total_chars"], 2)

    def test_chapter_without_volume_and_bad_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "含 空白.txt"
            p.write_text("第一章 甲\n內文一\n\n第二章 乙\n內文二\n", encoding="utf-8")
            ok = run(SCRIPTS / "adapt" / "extract_chapter.py", "--input", p, "--chapter", "二")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("內文二", ok.stdout)
            bad = run(SCRIPTS / "adapt" / "extract_chapter.py", "--input", p, "--chapter", "abc")
            self.assertEqual(bad.returncode, 1)
            self.assertIn("看不懂章號", bad.stderr)
            md = Path(tmp) / "multi.md"
            md.write_text("## 第一集\n### 第一章 a\nx\n## 第二集\n### 第一章 b\ny\n", encoding="utf-8")
            amb = run(SCRIPTS / "adapt" / "extract_chapter.py", "--input", md, "--chapter", "1")
            self.assertEqual(amb.returncode, 1)
            self.assertIn("--volume", amb.stderr)


class CharacterBibleTests(unittest.TestCase):
    def test_e11_accepts_chinese_and_jpg_image_paths(self):
        md = (FIXTURE / "adapt" / "character-bible.md").read_text(encoding="utf-8")
        md = md.replace("images/C-linwu_W01_sheet_v1.png", "images/角色/林霧 斗篷.jpg")
        md = md.replace("`images/角色/林霧 斗篷.jpg`", "images/角色/林霧.jpg")
        res = validate_character_bible(md, None)
        self.assertFalse([e for e in res["errors"] if "E11" in e], res["errors"])

    def test_cli_missing_or_broken_bible_json_is_an_error(self):
        md = FIXTURE / "adapt" / "character-bible.md"
        with tempfile.TemporaryDirectory() as tmp:
            res = run(SCRIPTS / "adapt" / "validate_character_bible.py", "--bible-md", md,
                      "--bible-json", Path(tmp) / "nope.json")
            self.assertEqual(res.returncode, 1)
            bad = Path(tmp) / "bad.json"
            bad.write_text("{bad", encoding="utf-8")
            res = run(SCRIPTS / "adapt" / "validate_character_bible.py", "--bible-md", md, "--bible-json", bad)
            self.assertEqual(res.returncode, 1)
            self.assertNotIn("Traceback", res.stderr)


class Stage1GateTests(ProjectFixture):
    def test_fixture_passes_stage1(self):
        self.assertEqual(scc.content_errors(self.root, 1), [])

    def test_series_outline_copied_from_template_is_blocked(self):
        tpl = ROOT / "references" / "adapt" / "templates" / "series-outline.md"
        shutil.copyfile(tpl, self.root / "adapt" / "series-outline.md")
        errors = scc.content_errors(self.root, 1)
        self.assertTrue(any("series-outline.md" in e and "佔位符" in e for e in errors), errors)

    def test_stage1_review_tolerates_bom_json(self):
        p = self.root / "adapt" / "bible.json"
        p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
        passed, errors, _html = bsr.build_stage_1(self.root, ps.load_state(self.root))
        self.assertTrue(passed, errors)


# ---------------------------------------------------------------- 階段 2

class Stage2Tests(ProjectFixture):
    def test_image_refs_handles_spaces_chinese_and_extensions(self):
        text = "設定圖 `images/scene 燈塔-master.png`；另見 images/a/b.webp 與 images/x.JPG"
        self.assertEqual(bsr.image_refs(text),
                         ["images/scene 燈塔-master.png", "images/a/b.webp", "images/x.JPG"])

    def test_content_gate_reads_backticked_path_with_space(self):
        self.assertEqual(scc.content_errors(self.root, 2), [])
        (self.root / "images" / "scene lighthouse-master.png").unlink()
        errors = scc.content_errors(self.root, 2)
        self.assertTrue(any("images/scene lighthouse-master.png" in e for e in errors), errors)

    def test_review_page_uses_assets_md_scene_master(self):
        self.assertEqual(bsr.scene_master_image(self.root, {}, "S-lighthouse"), "images/scene lighthouse-master.png")
        passed, errors, _html = bsr.build_stage_2(self.root, ps.load_state(self.root))
        self.assertTrue(passed, errors)

    def test_review_page_falls_back_to_assets_md_character_sheet(self):
        p = self.root / "adapt" / "bible.json"
        bible = json.loads(p.read_text(encoding="utf-8"))
        for ch in bible["characters"]:
            ch.pop("reference_image", None)
        p.write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
        (self.root / "adapt" / "character-bible.md").write_text(
            (self.root / "adapt" / "character-bible.md").read_text(encoding="utf-8").replace("images/", "img-x/"),
            encoding="utf-8")
        passed, errors, _html = bsr.build_stage_2(self.root, ps.load_state(self.root))
        self.assertTrue(passed, errors)

    def test_no_image_scope_does_not_deadlock_stage2_review(self):
        for f in (self.root / "images").glob("*.png"):
            f.unlink()
        decisions.decide(self.root, "delivery_scope", '{"end_stage": 3, "no_image": true}', "不要圖")
        self.assertEqual(scc.content_errors(self.root, 2), [])
        with redirect_stderr(io.StringIO()):
            passed, errors, html = bsr.build_stage_2(self.root, ps.load_state(self.root))
        self.assertTrue(passed, errors)
        self.assertIn("missing-box", html)  # 紅框照畫

    def test_export_style_prefers_decision_and_maps_12_13(self):
        decisions.decide(self.root, "style", "master", "母版")
        token, source, notes = eap.pick_style_index(None, self.root, self.root / "assets.md")
        self.assertEqual((token, source), ("master", "decisions.json"))
        self.assertTrue(any("不一致" in n for n in notes))  # assets.md 寫 14
        self.assertEqual(eap.pick_style_index("7", self.root, self.root / "assets.md")[1], "--style")
        self.assertEqual(eap.resolve_style("12")["key"], "master")
        self.assertEqual(eap.resolve_style("13")["key"], "semi-real")
        self.assertEqual(eap.style_token(decisions.RECOMMENDED_STYLE), "14")

    def test_export_scene_plate_follows_aspect_decision(self):
        decisions.decide(self.root, "aspect_ratio", "9:16", "豎")
        out = Path(self.tmp.name) / "ex.json"
        argv = ["export_asset_prompts.py", "--assets-md", str(self.root / "assets.md"), "--no-gate",
                "--out-json", str(out)]
        old = sys.argv
        try:
            sys.argv = argv
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                eap.main()
        finally:
            sys.argv = old
        items = {c["type"]: c for c in json.loads(out.read_text(encoding="utf-8"))}
        self.assertIn("9:16 aspect ratio", items["scene"]["full_prompt"])
        self.assertEqual(items["scene"]["aspect_ratio"], "9:16")
        self.assertIn("16:9", items["creature"]["full_prompt"])  # 三視圖版式不變

    def test_araki_reads_v4_character_headings(self):
        md = (self.root / "adapt" / "character-bible.md").read_text(encoding="utf-8")
        names = [t for t, _ in araki_review.split_sections(md)]
        self.assertEqual(names, ["林霧（核心角色）", "老周（重要配角）"])


# ---------------------------------------------------------------- 階段 3

class Stage3Tests(ProjectFixture):
    def sync(self, *extra):
        return run(SCRIPTS / "adapt" / "sync_script.py", "--handoff", self.root / "handoff-ep01.json",
                   "--script", self.root / "script-ep01.md", "--source", self.root / "adapt" / "source.json", *extra)

    def test_sync_aligns_aspect_fills_title_and_is_idempotent(self):
        first = self.sync()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("[對齊定案] aspect_ratio 9:16 → 16:9", first.stdout)
        handoff = json.loads((self.root / "handoff-ep01.json").read_text(encoding="utf-8"))
        self.assertEqual(handoff["aspect_ratio"], "16:9")
        self.assertEqual(handoff["episodes"][0]["title"], "霧起")
        second = self.sync()
        self.assertIn("未進行任何檔案變更", second.stdout)

    def test_stage3_gate_flags_aspect_mismatch(self):
        self.sync()
        p = self.root / "handoff-ep01.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["episodes"][0]["episode_goal"] = "林霧引霧鯨回家"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(scc.content_errors(self.root, 3), [])
        data["aspect_ratio"] = "9:16"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertTrue(any("aspect_ratio" in e for e in scc.content_errors(self.root, 3)))

    def test_sync_scene_on_new_handoff_is_a_clean_error(self):
        res = run(SCRIPTS / "adapt" / "sync_script.py", "--handoff", self.root / "new-handoff.json",
                  "--script", self.root / "script-ep01.md", "--scene", "EP01-S01")
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("Traceback", res.stderr)

    def test_new_handoff_uses_project_md_aspect_when_not_decided(self):
        root = Path(self.tmp.name) / "p2"
        root.mkdir()
        (root / "decisions.json").write_text(json.dumps(decisions.empty_decisions()), encoding="utf-8")
        (root / "project.md").write_text("- aspect_ratio：16:9\n- genre_mode：wuxia_action\n", encoding="utf-8")
        self.assertEqual(sync_script.read_project_defaults(root),
                         {"aspect_ratio": "16:9", "genre_mode": "wuxia_action"})

    def test_bom_and_crlf_script(self):
        text = (self.root / "script-ep01.md").read_text(encoding="utf-8")
        res = parse_and_validate_script("\ufeff" + text.replace("\n", "\r\n"))
        self.assertFalse([w for w in res["warnings"] if "ORPHAN_LINE" in w], res["warnings"])
        self.assertEqual(len(res["scenes"]), 3)
        p = self.root / "script-crlf.md"
        p.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
        est = run(SCRIPTS / "adapt" / "estimate_duration.py", "--script", p, "--h3", "--json")
        self.assertEqual(est.returncode, 0, est.stderr)
        self.assertEqual(json.loads(est.stdout)["total_spoken_chars"], 55)

    def test_estimate_duration_bad_inputs_do_not_traceback(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("{bad", encoding="utf-8")
        lst = Path(self.tmp.name) / "list.json"
        lst.write_text("[]", encoding="utf-8")
        for args in (["--events", bad], ["--events", lst], ["--script", self.tmp.name],
                     ["--script", self.root / "script-ep01.md", "--target-seconds", "0"]):
            with self.subTest(args=args):
                res = run(SCRIPTS / "adapt" / "estimate_duration.py", *args)
                self.assertEqual(res.returncode, 1)
                self.assertNotIn("Traceback", res.stderr)

    def test_events_mode_on_fixture(self):
        res = run(SCRIPTS / "adapt" / "estimate_duration.py", "--events", self.root / "adapt" / "source.json", "--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["kept_event_count"], 3)


# ---------------------------------------------------------------- 核准與 hash 門禁

class ApprovalFlowTests(ProjectFixture):
    def approve(self, stage):
        b = SCRIPTS / "build_stage_review.py"
        built = run(b, "--project-dir", self.root, "--stage", stage)
        self.assertEqual(built.returncode, 0, built.stderr)
        ok = run(b, "--project-dir", self.root, "--approve-stage", stage, "--user-note", "通過")
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_stage0_to_2_then_hash_change_invalidates_and_reapprove_message(self):
        for stage in (0, 1, 2):
            self.approve(stage)
        again = run(SCRIPTS / "build_stage_review.py", "--project-dir", self.root, "--approve-stage", "2",
                    "--user-note", "通過")
        self.assertEqual(again.returncode, 2)
        self.assertIn("已核准且內容沒變", again.stderr)
        # 改設定圖 → 階段 2 核准失效
        from PIL import Image
        Image.new("RGB", (64, 36), (1, 2, 3)).save(self.root / "images" / "C-linwu_W01_sheet_v1.png")
        ok, detail = ps.require_approved(self.root, 2)
        self.assertFalse(ok)
        self.assertIn("變更", detail)

    def test_approve_without_user_note_warns(self):
        b = SCRIPTS / "build_stage_review.py"
        run(b, "--project-dir", self.root, "--stage", "0")
        res = run(b, "--project-dir", self.root, "--approve-stage", "0")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("沒有 --user-note", res.stderr)

    def test_craft_reports_do_not_touch_approval(self):
        for stage in (0, 1):
            self.approve(stage)
        before = (self.root / "review" / "project-state.json").read_bytes()
        for script, args in ((SCRIPTS / "craft" / "hit_review.py", ["--stage", "0"]),
                             (SCRIPTS / "craft" / "araki_review.py", ["--stage", "2"])):
            res = run(script, "--project-dir", self.root, *args)
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.root / "review" / "project-state.json").read_bytes(), before)
        self.assertTrue(ps.require_approved(self.root, 1)[0])


if __name__ == "__main__":
    unittest.main()
