"""PR #115 第二輪（T1 回溯驗證後的修正）：景別自由文字、同場判斷、D15 人→空鏡、走位中文詞表、D16 插入鏡／動作匹配／
過肩收緊、D20 降級、D21 改建議、新規則 D22 重演／狀態倒退（含事件帳 beats）、D23 朝向對站位、D24 反打沒換邊、
拋棄式前導 lead_in_s（compile 寫前導句、assemble 自動剪）、`h3d seamcheck` 接點自檢包。

每條規則都有正例（該報）與反例（不該報）；舊專案沒有新欄位時零新警告。
"""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import compile_layer2_to_h3 as compiler  # noqa: E402
import staging_lint  # noqa: E402
import transition_lint as tl  # noqa: E402

from tests import test_h3_compiler as _h3  # noqa: E402
from tests.test_transition_lint import chain, codes, seg, shot  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False


def act(s, text):
    """給鏡頭加動作描述（英文 action_stages_en 或中文 action_stages）。"""
    key = "action_stages" if any("\u3400" <= ch <= "\u9fff" for ch in text) else "action_stages_en"
    s.setdefault("action_and_performance", {})[key] = [text]
    return s


def P(cid, order=None, x=None, facing=None, anchor="窗", **kw):
    p = {"id": cid, "background_anchor": anchor}
    if order is not None:
        p["order_lr"] = order
    if x is not None:
        p["screen_x"] = x
    if facing:
        p["facing"] = facing
    p.update(kw)
    return p


class SizeCodeTests(unittest.TestCase):
    CASES = {
        "extreme close-up": "ECU", "Extreme Close Up shot": "ECU", "extreme_close_up": "ECU", "ECU": "ECU",
        "close-up": "CU", "Close-up": "CU", "close up": "CU", "Close shot": "CU", "close shot": "CU", "CU": "CU",
        "medium close-up": "MCU", "medium close shot": "MCU", "Medium Close-Up Shot": "MCU", "medium_close_up": "MCU",
        "Medium shot": "MS", "medium shot": "MS", "low medium shot": "MS", "Medium two-shot": "MS", "mid shot": "MS",
        "medium-wide shot": "MLS", "Medium-wide shot": "MLS", "medium wide": "MLS", "medium full shot": "MLS",
        "medium-wide two-shot": "MLS", "medium long shot": "MLS",
        "wide shot": "LS", "Wide shot": "LS", "Wide": "LS", "long shot": "LS", "full shot": "LS",
        "extreme wide shot": "ELS", "extreme long shot": "ELS", "establishing shot": "ELS", "extreme-wide": "ELS",
        "over-the-shoulder close-up": "OTS_CU", "over the shoulder medium shot": "OTS_MS", "OTS medium": "OTS_MS",
        "OTS_CU": "OTS_CU", "MLS": "MLS", "MCU (chest up)": "MCU",
        "大特寫": "ECU", "特寫": "CU", "中近景": "MCU", "近景": "MCU", "中景": "MS", "中遠景": "MLS", "遠景": "LS",
        "全景": "LS", "大遠景": "ELS", "過肩近景": "OTS_CU",
    }

    def test_free_text_variants(self):
        for raw, code in self.CASES.items():
            with self.subTest(raw=raw):
                self.assertEqual(tl.size_code(raw), code)

    def test_unknown_and_empty(self):
        self.assertIsNone(tl.size_code(""))
        self.assertIsNone(tl.size_code("aerial drone"))
        self.assertEqual(tl.size_level({"camera_optics": {"shot_size": "Medium-wide shot"}}), 2)

    def test_free_text_sizes_feed_d15_and_d16(self):
        prev = seg("S01-a", [shot("a1", "medium shot")])
        self.assertEqual(codes(tl.lint_segment(seg("S01-b", [shot("b1", "medium close shot")], seam_in="cut"), prev)),
                         ["D15"])
        self.assertEqual(tl.lint_segment(seg("S01-b", [shot("b1", "close-up")], seam_in="cut"), prev), [])
        self.assertEqual(codes(tl.lint_segment(seg("S", chain(2, ["medium shot", "Medium close-up"])))), ["D16"])


class D15SubjectTests(unittest.TestCase):
    def test_person_to_empty_shot_counts_as_new_subject(self):
        prev = seg("S01-a", [shot("a1", "MS", ("C1",))])
        self.assertEqual(tl.lint_segment(seg("S01-b", [shot("b1", "MS", ())], seam_in="cut"), prev), [])
        prev_empty = seg("S01-a", [shot("a1", "MS", ())])
        self.assertEqual(tl.lint_segment(seg("S01-b", [shot("b1", "MS", ("C1",))], seam_in="cut"), prev_empty), [])

    def test_both_empty_still_warns(self):
        prev = seg("S01-a", [shot("a1", "MS", ())])
        found = tl.lint_segment(seg("S01-b", [shot("b1", "MS", ())], seam_in="cut"), prev)
        self.assertEqual(codes(found), ["D15"])
        self.assertIn("兩邊都沒填 character_ids", found[0]["message"])


class SameSceneTests(unittest.TestCase):
    def pair(self, a_extra, b_extra):
        a = seg("EP05-S01-a", [shot("a1", "MS")], scene="S-buffet-fight-a", **a_extra)
        b = seg("EP05-S01-b", [shot("b1", "MCU")], scene="S-buffet-fight-b", seam_in="cut", **b_extra)
        return [a, b]

    def test_scene_package_ids_need_narrative_scene(self):
        rows = tl.lint_sequence(self.pair({}, {}))
        self.assertEqual(rows[1]["findings"], [])  # scene_id 不同、沒寫 narrative_scene_id → 視為換場
        rows = tl.lint_sequence(self.pair({"narrative_scene_id": "EP05-buffet"}, {"narrative_scene_id": "EP05-buffet"}))
        self.assertEqual(codes(rows[1]["findings"]), ["D15"])

    def test_source_scene_id_and_narrative_override(self):
        rows = tl.lint_sequence(self.pair({"source_scene_id": "EP05-S01"}, {"source_scene_id": "EP05-S01"}))
        self.assertEqual(codes(rows[1]["findings"]), ["D15"])
        a, b = self.pair({"narrative_scene_id": "N1"}, {"narrative_scene_id": "N2"})
        a["scene_id"] = b["scene_id"] = "S"
        self.assertFalse(tl.same_scene(a, b))  # 敘事場景不同就是換場，即使 scene_id 一樣
        self.assertEqual(tl.lint_sequence([a, b])[1]["findings"], [])

    def test_staging_uses_narrative_scene_but_keeps_d10_rule(self):
        segs = self.pair({"narrative_scene_id": "EP05-buffet"}, {"narrative_scene_id": "EP05-buffet"})
        rows = staging_lint.lint_segments(segs, lambda s: "ref2va")
        self.assertIn("D15", [f["code"] for f in rows[1]["findings"]])


class BlockingVocabTests(unittest.TestCase):
    WORDS = ["持續向東經過黃宗儒", "繞過桌子", "退到門邊", "跨過倒下的凳子", "走到窗前", "移到畫左", "往北走",
             "向西衝去", "穿過人群", "後退兩步", "walks past him", "backs away from the table", "passes behind her",
             "heads east along the alley"]

    def test_movement_words_suppress_d20_swap(self):
        a = shot("SH1", "MS", ("C1", "C2"), pos=[P("C1", 1), P("C2", 2)])
        for word in self.WORDS:
            with self.subTest(word=word):
                b = shot("SH2", "LS", ("C1", "C2"), cut="hard", start=3, end=6,
                         pos=[P("C2", 1, move=word), P("C1", 2)])
                self.assertEqual(tl.lint_segment(seg("S", [a, copy.deepcopy(b)])), [])
        b = shot("SH2", "LS", ("C1", "C2"), cut="hard", start=3, end=6, pos=[P("C2", 1), P("C1", 2)])
        self.assertEqual(codes(tl.lint_segment(seg("S", [a, b]))), ["D20"])


class D16SkipTests(unittest.TestCase):
    def test_insert_and_match_action_skip(self):
        a, b = chain(2, ["MS", "MCU"])
        b["cut_in"]["type"] = "insert"
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        b["cut_in"]["type"] = "match_action"
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        a, b, c = chain(3, ["MS", "CU", "MCU"])
        b["cut_in"]["type"] = "insert"  # 插入鏡 → 回到臉：後一刀也不查
        self.assertNotIn("D16", codes(tl.lint_segment(seg("S", [a, b, c]))))

    def test_ots_exemption_only_without_azimuth(self):
        a, b = chain(2, ["MS", "OTS_MS"])
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        a["camera_optics"]["azimuth_deg"], b["camera_optics"]["azimuth_deg"] = 0, 10
        self.assertEqual(codes(tl.lint_segment(seg("S", [a, b]))), ["D16"])
        b["camera_optics"]["azimuth_deg"] = 35
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])


class D20D21DowngradeTests(unittest.TestCase):
    def test_hard_cut_screen_x_drift_no_longer_warns(self):
        a = shot("SH1", "MS", ("C1", "C2"), az=0, pos=[P("C1", 1, 0.3), P("C2", 2, 0.7)])
        b = shot("SH2", "MCU", ("C1", "C2"), az=40, cut="hard", start=3, end=6,
                 pos=[P("C1", 1, 0.1), P("C2", 2, 0.95)])
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        b["cut_in"]["type"] = "match_action"
        self.assertEqual(codes(tl.lint_segment(seg("S", [a, b]))), ["D20"])
        b["camera_optics"]["shot_size"] = "ECU"  # 景別差 3 級：位置本來就會變
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])

    def test_d21_is_suggestion_not_warning(self):
        a = shot("SH1", "MS", ("C1", "C2"), pos=[{"id": "C1", "order_lr": 1}, {"id": "C2", "order_lr": 2}])
        found = tl.lint_segment(seg("S", [a]))
        self.assertEqual(codes(found), ["D21"])
        self.assertEqual(found[0]["level"], "suggestion")
        self.assertEqual(tl.warnings_only(found), [])
        rows = staging_lint.lint_segments([seg("S", [a])], lambda s: "ref2va")
        self.assertEqual([f["level"] for f in rows[0]["findings"] if f["code"] == "D21"], ["suggestion"])
        self.assertIn("D21", staging_lint.SUGGESTION_CODES)


class D22RepeatTests(unittest.TestCase):
    def seam(self, prev_kwargs, first_action, nxt_kwargs=None, prev_action=None):
        a1 = shot("a1", "MS", ("C-MOM",))
        if prev_action:
            act(a1, prev_action)
        prev = seg("S01-a", [a1], **prev_kwargs)
        b1 = act(shot("b1", "CU", ("C-MOM",)), first_action) if first_action else shot("b1", "CU", ("C-MOM",))
        nxt = seg("S01-b", [b1], seam_in="cut", **(nxt_kwargs or {}))
        return tl.lint_segment(nxt, prev)

    def test_seam_redo_from_ledger_and_still_seated_regression(self):
        found = self.seam({"ledger_out": "婦人半起身、手伸向畫右的孩子"},
                          "First the mother, still seated with chopsticks in hand, twists round, then she half-rises")
        self.assertEqual(codes(found), ["D22"])
        self.assertIn("站起", found[0]["message"])

    def test_stative_wording_does_not_warn(self):
        self.assertEqual(self.seam({"ledger_out": "婦人半起身"},
                                   "The mother, already standing, steps back from the table"), [])
        self.assertEqual(self.seam({"ledger_out": "沈站起"}, "沈已站起，手扶桌緣喘氣"), [])

    def test_chinese_redo_and_fall(self):
        self.assertEqual(codes(self.seam({}, "沈又站了起來", prev_action="沈撐著桌子站起")), ["D22"])
        self.assertEqual(codes(self.seam({"exit_state": {"C-BOY": {"position": "摔倒在地上"}}},
                                         "The boy falls hard onto the tiles")), ["D22"])
        self.assertEqual(self.seam({"exit_state": {"C-BOY": {"position": "坐在圓凳上"}}},
                                   "The boy falls hard onto the tiles"), [])

    def test_ledger_regression_needs_same_subject(self):
        found = self.seam({"ledger_out": "婦人半起身、手伸向孩子"}, "", {"ledger_in": "接 S01-a：婦人坐在桌邊吃麵"})
        self.assertEqual(codes(found), ["D22"])
        self.assertIn("入口", found[0]["message"])
        self.assertEqual(self.seam({"ledger_out": "婦人半起身、手伸向孩子"}, "",
                                   {"ledger_in": "接 S01-a：孩子坐在圓凳上；婦人半起身"}), [])

    def test_structured_posture_and_back_to_start(self):
        found = self.seam({"exit_state": {"C-MOM": {"position": "standing by the door"}}}, "",
                          {"entry_state": {"C-MOM": {"position": "seated at the table"}}})
        self.assertIn("D22", codes(found))
        found = self.seam({"entry_state": {"C-MOM": {"position": "table east end"}},
                           "exit_state": {"C-MOM": {"position": "by the door"}}}, "",
                          {"entry_state": {"C-MOM": {"position": "table east end"}}})
        self.assertTrue(any("回原點" in f["message"] for f in found))
        self.assertEqual(self.seam({"exit_state": {"C-MOM": {"position": "by the door"}}}, "",
                                   {"entry_state": {"C-MOM": {"position": "by the door"}}}), [])

    def test_beat_ledger(self):
        prev = seg("S01-a", [shot("a1", "MS")], beats_new=["B03-wall-breaks"])
        dup = seg("S01-b", [shot("b1", "CU", ("C2",))], seam_in="cut", beats_new=["B03-wall-breaks"])
        self.assertEqual(codes(tl.lint_segment(dup, prev)), ["D22"])
        ok = seg("S01-b", [shot("b1", "CU", ("C2",))], seam_in="cut", beats_done=["B03-wall-breaks"],
                 beats_new=["B04-rat-pounces"])
        self.assertEqual(tl.lint_segment(ok, prev), [])
        broken = seg("S01-b", [shot("b1", "CU", ("C2",))], seam_in="cut", beats_done=["B01"], beats_new=["B04"])
        self.assertTrue(any("事件帳斷了" in f["message"] for f in tl.lint_segment(broken, prev)))
        clash = seg("S01-b", [shot("b1", "CU", ("C2",))], seam_in="cut", beats_done=["B03-wall-breaks", "B04"],
                    beats_new=["B04"])
        self.assertTrue(any("同時在 beats_done" in f["message"] for f in tl.lint_segment(clash, prev)))

    def test_beat_repeated_two_segments_later_and_within_shots(self):
        a = seg("S01-a", [shot("a1", "MS")], beats_new=["B1"])
        b = seg("S01-b", [shot("b1", "CU", ("C2",))], seam_in="cut", beats_done=["B1"], beats_new=["B2"])
        c = seg("S01-c", [shot("c1", "LS", ("C3",))], seam_in="cut", beats_done=["B2"], beats_new=["B1"])
        rows = tl.lint_sequence([a, b, c])
        self.assertEqual(codes(rows[2]["findings"]), ["D22"])
        self.assertIn("S01-a", rows[2]["findings"][0]["message"])
        s1, s2 = chain(2, ["MS", "CU"], [("C1",), ("C2",)])
        s1["beats_new"], s2["beats_new"] = ["B9"], ["B9"]
        self.assertEqual(codes(tl.lint_segment(seg("S", [s1, s2]))), ["D22"])

    def test_within_repeat_hard_cut_but_not_match_action(self):
        s1, s2 = chain(2, ["MS", "CU"], [("C1",), ("C2",)])
        act(s1, "The vase shatters on the tiles")
        act(s2, "The vase shatters again as she looks down")
        self.assertEqual(codes(tl.lint_segment(seg("S", [s1, s2]))), ["D22"])
        s2["cut_in"]["type"] = "match_action"
        self.assertEqual(tl.lint_segment(seg("S", [s1, s2])), [])

    def test_unplanned_segments_never_warn(self):
        a1 = act(shot("a1", "MS"), "沈撐著桌子站起")
        b1 = act(shot("b1", "MS"), "沈又站了起來")
        self.assertEqual(tl.lint_sequence([seg("S01-a", [a1]), seg("S01-b", [b1])])[1]["findings"], [])


class D23FacingTests(unittest.TestCase):
    def test_facing_toward_target_on_wrong_side(self):
        s1 = shot("SH1", "MS", ("C1", "C2"), cut="hard",
                  pos=[P("C1", 1, 0.3, "frame_left toward C2"), P("C2", 2, 0.9, "frame_left")])
        found = tl.lint_segment(seg("S", [s1]))
        self.assertEqual(codes(found), ["D23"])
        self.assertIn("畫右", found[0]["message"])
        s1["positions"][0]["facing"] = "frame_right toward C2"
        self.assertEqual(tl.lint_segment(seg("S", [s1])), [])
        s1["positions"][0] = P("C1", 1, 0.3, "畫左", toward="C2")
        self.assertEqual(codes(tl.lint_segment(seg("S", [s1]))), ["D23"])

    def test_facing_flip_between_close_angles(self):
        a = shot("SH1", "MS", ("C1", "C2"), az=0, pos=[P("C1", 1, facing="frame_right"), P("C2", 2, facing="frame_left")])
        b = shot("SH2", "CU", ("C1", "C2"), az=20, cut="hard", start=3, end=6,
                 pos=[P("C1", 1, facing="frame_left"), P("C2", 2, facing="frame_left")])
        self.assertEqual(codes(tl.lint_segment(seg("S", [a, b]))), ["D23"])
        b["cut_in"]["motivation"] = "C1 回頭看門口"
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        b["cut_in"]["motivation"] = ""
        b["camera_optics"]["azimuth_deg"] = 180
        b["positions"] = [P("C2", 1, facing="frame_right"), P("C1", 2, facing="frame_left")]
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])  # 反打：朝向跟著翻是對的


class D24ReverseTests(unittest.TestCase):
    def test_reverse_without_swap_warns_and_swap_passes(self):
        a = shot("SH1", "MS", ("C1", "C2"), az=0, pos=[P("C1", 1), P("C2", 2)])
        b = shot("SH2", "MS", ("C1", "C2"), az=180, cut="hard", start=3, end=6, pos=[P("C1", 1), P("C2", 2)])
        found = tl.lint_segment(seg("S", [a, b]))
        self.assertEqual(codes(found), ["D24"])
        b["positions"] = [P("C2", 1), P("C1", 2)]
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])  # 反打換邊：不報 D24，也不報 D20 對調
        b["positions"] = [P("C1", 1, move="C2 繞到桌子另一側"), P("C2", 2)]
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        b["positions"] = [P("C1", 1), P("C2", 2)]
        b["camera_optics"]["azimuth_deg"] = 60
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])

    def test_seam_reverse(self):
        prev = seg("S01-a", [shot("a1", "MS", ("C1", "C2"), az=0, pos=[P("C1", 1), P("C2", 2)])])
        nxt = seg("S01-b", [shot("b1", "CU", ("C1", "C2"), az=170, pos=[P("C1", 1), P("C2", 2)])], seam_in="cut")
        self.assertEqual(codes(tl.lint_segment(nxt, prev)), ["D24"])
        nxt["seam_in"] = None
        self.assertNotIn("D24", codes(tl.lint_segment(nxt, prev)))


class BackwardCompatR2Tests(unittest.TestCase):
    def test_golden_and_legacy_free_text_project_stay_silent(self):
        golden = json.loads((ROOT / "tests" / "golden" / "ep01" / "segments-ep01.json").read_text(encoding="utf-8"))
        self.assertEqual([f for r in tl.lint_sequence(golden["segments"]) for f in r["findings"]], [])
        legacy = [seg("EP05-S01-a", [act(shot("a1", "Medium-wide shot", ("C1", "C2")), "the cook bursts out"),
                                     act(shot("a2", "medium shot", ("C1", "C2"), start=3, end=6), "the cook bursts out")],
                      scene="S-buffet-v3", ledger_out="婦人半起身"),
                  seg("EP05-S01-b", [act(shot("b1", "Medium-wide shot", ("C1", "C2")), "she half-rises")],
                      scene="S-buffet-v3", ledger_in="婦人坐在桌邊")]
        self.assertEqual([f for r in tl.lint_sequence(legacy) for f in r["findings"]], [])


class _Base(_h3.H3CompilerRegressionTests):
    """借用既有編譯器 fixture；不重跑父類別的測試。"""


for _name in [n for n in dir(_h3.H3CompilerRegressionTests) if n.startswith("test_")]:
    setattr(_Base, _name, None)


class LeadInCompileTests(_Base):
    def test_lead_in_off_by_default_and_on_when_set(self):
        base = self.compile()
        self.assertNotIn("holds still in the opening pose", base["h3_prompt"])
        self.assertNotIn("lead_in_s", base)
        data = self.segment()
        data["lead_in_s"] = 1.0
        data["narrative_scene_id"] = "EP01-cafe"
        data["beats_new"] = ["B1"]
        compiled = self.compile(data)
        head = compiled["h3_prompt"].split("[Shot 1]")[1].split("[Shot 2]")[0]
        self.assertIn("From 0.0 s to 1.0 s everyone holds still in the opening pose", head)
        self.assertEqual(compiled["h3_prompt"].count("holds still in the opening pose"), 1)
        self.assertEqual((compiled["lead_in_s"], compiled["narrative_scene_id"], compiled["beats_new"]),
                         (1.0, "EP01-cafe", ["B1"]))
        data["lead_in_s"] = 3.0
        self.assertTrue(any("lead_in_s=3 太長" in n for n in self.compile(data)["compile_notes"]))


@unittest.skipUnless(HAVE_FFMPEG, "需要 ffmpeg")
class LeadInAssembleTests(unittest.TestCase):
    def test_process_segment_trims_lead_in_and_shifts_subtitles(self):
        from scripts.storyboard import assemble_episode as assembly
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "S01-b.mp4"
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                            "-i", "color=c=blue:s=160x90:r=24:d=3", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
                           check=True, capture_output=True)
            out = root / "out.mp4"
            ok, msg = assembly.process_single_segment(
                src, out, [{"start": 1.5, "end": 2.5, "subtitle": "走"}], 3.0, audio_mode="native_sub",
                burn_subtitles=False, temp_dir=root / "tmp", lead_in_s=1.0)
            self.assertTrue(ok, msg)
            self.assertAlmostEqual(assembly.probe_video_specs(out)["duration"], 2.0, delta=0.1)
            srt = (root / "tmp" / "S01-b.srt").read_text(encoding="utf-8")
            self.assertIn("00:00:00,500 --> 00:00:01,500", srt)
            ok, msg = assembly.process_single_segment(src, out, [], 3.0, audio_mode="native_sub",
                                                      burn_subtitles=False, temp_dir=root / "tmp", lead_in_s=3.0)
            self.assertFalse(ok)
            self.assertIn("lead_in_s", msg)

    def test_lead_in_seconds_reads_segment_or_metadata(self):
        self.assertEqual(tl.lead_in_seconds({}), 0.0)
        self.assertEqual(tl.lead_in_seconds({"lead_in_s": 1.2}), 1.2)
        self.assertEqual(tl.lead_in_seconds({"metadata": {"lead_in_s": 0.8}}), 0.8)
        self.assertEqual(tl.lead_in_seconds({"lead_in_s": True}), 0.0)


class SeamCheckRoutingTests(unittest.TestCase):
    def test_h3d_routes_seamcheck(self):
        import h3d
        self.assertEqual(h3d.MODULE_FOR["seamcheck"], "seam_check")
        self.assertIn("seamcheck", h3d.COMMANDS)


@unittest.skipUnless(HAVE_FFMPEG and HAVE_NUMPY, "需要 ffmpeg 與 numpy")
class SeamCheckTests(unittest.TestCase):
    @staticmethod
    def video(path, colors, each=1.0):
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for c in colors:
            cmd += ["-f", "lavfi", "-i", f"color=c={c}:s=160x90:r=24:d={each}"]
        cmd += ["-filter_complex", "".join(f"[{i}:v]" for i in range(len(colors))) + f"concat=n={len(colors)}:v=1[v]",
                "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
        subprocess.run(cmd, check=True, capture_output=True)

    def test_builds_pair_images_and_null_checklist(self):
        import seam_check
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "videos").mkdir()
            self.video(root / "videos" / "EP01-S01-a.mp4", ["black", "white"])
            self.video(root / "videos" / "EP01-S01-b.mp4", ["gray"])
            a = seg("EP01-S01-a", [shot("SH1", "MS", ("C1", "C2"), pos=[P("C1", 1), P("C2", 2)], end=1.0),
                                   shot("SH2", "close-up", ("C1",), cut="hard", start=1.0, end=2.0)],
                    beats_new=["B1"])
            b = seg("EP01-S01-b", [shot("SH1", "MS", ("C2",), end=1.0)], seam_in="cut", beats_done=["B1"])
            (root / "segments-ep01.json").write_text(json.dumps({"segments": [a, b]}, ensure_ascii=False),
                                                     encoding="utf-8")
            report = seam_check.build_checklist(root)
            ids = [j["id"] for j in report["junctions"]]
            self.assertEqual(ids, ["EP01-S01-a#1>2", "EP01-S01-a|EP01-S01-b"])
            within, seam = report["junctions"]
            self.assertTrue(within["cut_found"])
            self.assertEqual(within["expected"]["size_code_b"], "CU")
            self.assertEqual(within["expected"]["order_lr_a"], ["C1", "C2"])
            self.assertEqual(seam["expected"]["beats_done_b"], ["B1"])
            self.assertTrue(all(v is None for j in report["junctions"] for v in j["checks"].values()))
            for j in report["junctions"]:
                self.assertTrue((root / j["image"]).is_file())
            saved = json.loads((root / "videos" / "qa" / "seamcheck" / "seamcheck.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"]["junctions"], 2)


if __name__ == "__main__":
    unittest.main()
