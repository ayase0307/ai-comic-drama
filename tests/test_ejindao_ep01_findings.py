# -*- coding: utf-8 -*-
"""《噩盡島》EP01 重跑（main faca084＋#119）與 v118 整集分鏡（SB-1–SB-6）發現的規則修正。

以 #116–#120 新規則（快節奏、無廢片、台詞優先）為準；不新增生成或後處理步驟。
  #3  #120「單句 ≤18 字」合併 vs 密度閘門：句間 0.3 s 依句數，不依台詞行數
  #4  extra_lines 認 VO／voice_only：畫外句式、閉唇句只給看得到臉的人
  #5  refcheck／audit E50：voice_only 角色不需要包
  #6  pacing_profile 新增 Fast_Dialogue
  #7  W47：純內心 VO 段不建議雙人引子
  #8  SB-1：劇本估時報「分鏡後預估片長」，和分鏡閘門同一套數字
  #10 SB-3：≤4 字短句鏡多出的秒數不計入 D2／pacing_gate 密度
  #11 SB-4：validate 6e 以角色包／設定圖清單比對
  #12 SB-5：Codex 構圖左右一律觀眾視角
  #13 SB-6：Codex 構圖只寫當下存在的物件
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))

import adapt_gate  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import codex_storyboard_panels as cp  # noqa: E402
import dialogue_budget  # noqa: E402
import dual_lead_in  # noqa: E402
import h3_spec  # noqa: E402
import handoff_to_skeleton  # noqa: E402
import refcheck  # noqa: E402
import validate_storyboard as vs  # noqa: E402
from dialogue_density import check_dialogue_density, short_line_need  # noqa: E402
from tests import test_h3_compiler as base  # noqa: E402

GATE = ROOT / "scripts" / "storyboard" / "pacing_gate.py"


def _script(lines):
    body = "\n".join(lines)
    return ("第01集｜測試\n<!-- source: 卷1 L1-L9 -->\n1-1 測試場 日/內\n人物：阿青、阿木\n"
            f"{body}\n<!-- episode-end: 「知道了」 | 換場 -->\n")


class MergeInvariantDensity(unittest.TestCase):
    """#3：同一人連續兩句合成一行（≤18 字）或拆開，估時與密度一樣。"""

    def test_merge_and_split_same_density(self):
        split = _script(["阿青：今天天氣很好。", "阿青：我們出去走走吧。", "阿木：好啊。", "阿木：知道了。"])
        merged = _script(["阿青：今天天氣很好。我們出去走走吧。", "阿木：好啊。知道了。"])
        a = dialogue_budget.scene_stats(dialogue_budget.parse_script(split).scenes)
        b = dialogue_budget.scene_stats(dialogue_budget.parse_script(merged).scenes)
        self.assertEqual(a["seconds"], b["seconds"])
        self.assertEqual(a["density"], b["density"])

    def test_gate_status_unchanged_by_merge(self):
        lines = ["阿青：這句台詞剛好十一字。"] * 8
        merged = ["阿青：這句台詞剛好十一字。這句台詞剛好十一字。"] * 4
        q = ["這句台詞剛好十一字。"]
        r1 = adapt_gate.run_gate(_script(lines), quotes=q)
        r2 = adapt_gate.run_gate(_script(merged), quotes=q)
        self.assertEqual(r1["stats"]["density"], r2["stats"]["density"])
        self.assertEqual(bool([f for f in r1["fails"] if f.startswith("G3")]),
                         bool([f for f in r2["fails"] if f.startswith("G3")]))

    def test_sentence_units(self):
        self.assertEqual(dialogue_budget.sentence_units("知道"), 1)
        self.assertEqual(dialogue_budget.sentence_units("好啊。知道了！"), 2)
        self.assertEqual(dialogue_budget.sentence_units("更……更多？"), 2)


class StoryboardEstimate(unittest.TestCase):
    """#8／SB-1：劇本估時另報分鏡後片長（MIN_SHOT_SEC、#116 窗口、17n+5）。"""

    def test_constants_come_from_storyboard_layer(self):
        self.assertEqual(dialogue_budget.MIN_SHOT_SEC, h3_spec.MIN_SHOT_SEC)
        self.assertAlmostEqual(dialogue_budget.QUANTUM_SEC, h3_spec.FRAME_QUANTUM_STEP / h3_spec.FPS)
        self.assertEqual(dialogue_budget.SEGMENT_MAX_SEC, handoff_to_skeleton.DEFAULT_MAX_SEGMENT_SEC)

    def test_short_lines_hit_min_shot_floor(self):
        st = dialogue_budget.scene_stats(dialogue_budget.parse_script(_script(["阿木：哎！", "阿木：知道了。"])).scenes)
        # 1 字 0.22+0.3→1.2；3 字 0.67+0.3→1.2；一段 +半量子
        self.assertAlmostEqual(st["storyboard_seconds"], round(2.4 + h3_spec.FRAME_QUANTUM_STEP / h3_spec.FPS / 2, 2))
        self.assertGreater(st["storyboard_seconds"], st["seconds"])
        self.assertEqual(st["storyboard_segments"], 1)

    def test_gate_reports_note_only(self):
        res = adapt_gate.run_gate(_script(["阿木：哎！", "阿木：知道了。"]), quotes=["哎！", "知道了。"])
        self.assertTrue(any(n.startswith("分鏡後預估片長") for n in res["notes"]), res["notes"])
        self.assertFalse(any("分鏡後" in f for f in res["fails"] + res["warns"]))


class _CompilerFixture(unittest.TestCase):
    setUp = base.H3CompilerRegressionTests.setUp
    segment = base.H3CompilerRegressionTests.segment
    shot = staticmethod(base.H3CompilerRegressionTests.shot)
    compile = base.H3CompilerRegressionTests.compile


class ExtraLineVoiceover(_CompilerFixture):
    """#4：同鏡接話是內心 VO／只聞其聲時，用畫外句式，不寫「answers」也不給聲音寫嘴。"""

    def setUp(self):
        super().setUp()
        self.registry.characters["C-VOICE"] = {
            "id": "C-VOICE", "name": "Voice", "desc_en": "", "desc_zh": "神秘聲音", "ref_img": "",
            "wardrobe_states": {}, "is_creature": False, "voice_only": True, "no_visual_reference": True}

    def _data(self, main_speaker="C-MIRA", main_form=None, extra=None):
        data = self.segment()
        data["shots"] = [self.shot("S1", 0.0, 3.0, "Mira steps forward."),
                         self.shot("S2", 3.0, 7.0, "Mira listens.", line="誰在那裡？")]
        data["metadata"]["target_duration_sec"] = 7.0
        dlg = data["shots"][1]["dialogue_and_audio"]
        dlg["speaker"] = main_speaker
        if main_form:
            dlg["offscreen_form"] = main_form
            dlg["offscreen_voice_en"] = "a low echoing voice"
        dlg["speech_window"] = {"start": 3.3, "end": 4.6}
        dlg["extra_lines"] = [dict({"speech_window": {"start": 4.9, "end": 5.9}}, **extra)]
        return data

    def test_inner_vo_extra_line_uses_voiceover_form(self):
        compiled = self.compile(self._data(extra={
            "speaker": "C-MIRA", "line_verbatim": "不對勁。", "offscreen_form": "voiceover",
            "offscreen_voice_en": "a quiet inner voice"}))
        prompt = compiled["h3_prompt"]
        self.assertIn("says in an off-screen voiceover, a quiet inner voice: <d>[Chinese] 不對勁。</d>", prompt)
        self.assertNotIn("answers: <d>[Chinese] 不對勁。", prompt)
        self.assertRegex(prompt, r"不對勁。</d> while .+'s lips remain completely closed")

    def test_voice_only_previous_speaker_gets_no_lips(self):
        data = self._data(main_speaker="C-VOICE", main_form="offscreen", extra={
            "speaker": "C-MIRA", "line_verbatim": "你是誰？"})
        prompt = self.compile(data)["h3_prompt"]
        self.assertIn("<d>[Chinese] 你是誰？</d>", prompt)
        self.assertNotIn("soundless", prompt)
        self.assertNotRegex(prompt, r"你是誰？</d> while [^.;]*lips")

    def test_voice_only_extra_speaker_is_offscreen(self):
        prompt = self.compile(self._data(extra={"speaker": "C-VOICE", "line_verbatim": "在你身後。",
                                                "offscreen_voice_en": "a raspy old voice"}))["h3_prompt"]
        self.assertIn("the line is heard from", prompt)
        self.assertIn("off-screen, a raspy old voice: <d>[Chinese] 在你身後。</d>", prompt)
        self.assertNotIn("answers: <d>[Chinese] 在你身後。", prompt)

    def test_onscreen_extra_line_unchanged(self):
        prompt = self.compile(self._data(extra={"speaker": "C-MIRA", "line_verbatim": "出來。"}))["h3_prompt"]
        self.assertRegex(prompt, r"answers: <d>\[Chinese\] 出來。</d> while .+'s lips remain completely closed")


class VoiceOnlyNoPack(unittest.TestCase):
    """#5：bible 標 voice_only 的角色有 name_en，提示詞寫到也不報 E50。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "adapt").mkdir()
        (self.root / "adapt" / "bible.json").write_text(json.dumps({"characters": [
            {"id": "C-HERO", "name_en": "Hero"},
            {"id": "C-GOD", "name_en": "Frog Sage", "voice_only": True}]}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _seg(self):
        return {"segment_id": "E1-19", "refmods": [{"id": "C-HERO", "pack": "hero", "kind": "actor"}],
                "h3_prompt": "integrated_multimodal_description: Hero looks up. The Frog Sage speaks off-screen: "
                             "<d>[Chinese] 如你所願。</d>",
                "shots": [{"character_ids": ["C-HERO", "C-GOD"]}]}

    def test_refcheck_skips_voice_only(self):
        lex = refcheck.load_lexicon(self.root)
        self.assertTrue(lex["C-GOD"]["voice_only"])
        res = refcheck.check_segment(self._seg(), lex, "remix")
        self.assertEqual(res["missing"], [], res)
        self.assertTrue(res["ok"])

    def test_refcheck_still_catches_visual_character(self):
        bible = json.loads((self.root / "adapt" / "bible.json").read_text(encoding="utf-8"))
        bible["characters"][1].pop("voice_only")
        (self.root / "adapt" / "bible.json").write_text(json.dumps(bible), encoding="utf-8")
        res = refcheck.check_segment(self._seg(), refcheck.load_lexicon(self.root), "remix")
        self.assertTrue(any(m.startswith("C-GOD") for m in res["missing"]))

    def test_audit_presence_e50_skips_voice_only(self):
        out = audit.audit_remix(self._seg(), project_root=self.root)
        self.assertFalse([e for e in out["errors"] if "E50" in e and "C-GOD" in e], out["errors"])


class PacingProfile(unittest.TestCase):
    """#6：Fast_Dialogue 是合法 enum（validate 與 schema 一致）。"""

    def test_enum(self):
        self.assertIn("Fast_Dialogue", vs.PACING_PROFILES)
        schema = json.loads((ROOT / "references/storyboard/templates/layer2-storyboard.schema.json").read_text(encoding="utf-8"))
        enum = schema["properties"]["metadata"]["properties"]["pacing_profile"]["enum"]
        self.assertEqual(tuple(enum), vs.PACING_PROFILES)
        data = {"segment_id": "T", "metadata": {"lighting_lock_line": "x", "target_duration_sec": 2.0,
                                                "pacing_profile": "Fast_Dialogue"},
                "shots": [{"shot_id": "SH01", "start_time": 0, "end_time": 2.0, "duration": 2.0,
                           "camera_optics": {"shot_size": "MS"}, "dialogue_and_audio": {"has_dialogue": False}}]}
        self.assertFalse([e for e in vs.validate_storyboard_data(data)["errors"] if "pacing_profile" in e])


def _shot(sid, a, b, ids, size="medium close-up", line=None, **dlg):
    d = {"has_dialogue": bool(line), "line_verbatim": line or "", **dlg}
    return {"shot_id": sid, "start_time": a, "end_time": b, "duration": round(b - a, 4),
            "character_ids": list(ids), "camera_optics": {"shot_size": size}, "dialogue_and_audio": d}


class W47InnerVoice(unittest.TestCase):
    """#7：純內心 VO 段（沒有畫內對話）不建議雙人引子；有畫內台詞照舊建議。"""
    PREV = {"segment_id": "E1-18", "scene_id": "S-hill", "shots": [
        _shot("SH01", 0.0, 4.0, ["C-hero", "C-actress"], "medium-wide shot", "走吧。")]}

    def test_inner_vo_only_not_suggested(self):
        seg = {"segment_id": "E1-19", "scene_id": "S-hill", "shots": [
            _shot("SH01", 0.0, 4.0, ["C-hero"], line="這裡到底是哪裡。", offscreen_form="voiceover")]}
        self.assertIsNone(dual_lead_in.suggest(seg, self.PREV))

    def test_onscreen_line_still_suggested(self):
        seg = {"segment_id": "E1-19", "scene_id": "S-hill", "shots": [
            _shot("SH01", 0.0, 4.0, ["C-hero"], line="這裡到底是哪裡。")]}
        self.assertIsNotNone(dual_lead_in.suggest(seg, self.PREV))

    def test_onscreen_extra_line_counts(self):
        seg = {"segment_id": "E1-19", "scene_id": "S-hill", "shots": [
            _shot("SH01", 0.0, 4.0, ["C-hero"], line="這裡。", offscreen_form="voiceover",
                  extra_lines=[{"line_verbatim": "喂！"}])]}
        self.assertIsNotNone(dual_lead_in.suggest(seg, self.PREV))


class ShortLineDensity(unittest.TestCase):
    """#10／SB-3：≤4 字短句鏡只算需要的長度，多的出 WARN，不再拖成 D2 FAIL；pacing_gate 同算法。"""

    def _seg(self):
        # 12 字 3.0 s ＋「哎！」1 字撐 2.0 s：舊算 13/5.0=2.6 FAIL；新算 13/(5.0−0.8)=3.10
        return {"segment_id": "V1-23", "shots": [
            {"shot_id": "SH01", "start_time": 0.0, "end_time": 3.0,
             "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "媽的這到底是什麼鬼東西啊"}},
            {"shot_id": "SH02", "start_time": 3.0, "end_time": 5.0,
             "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "哎！"}}]}

    def test_need(self):
        self.assertEqual(short_line_need(1), h3_spec.MIN_SHOT_SEC)
        self.assertAlmostEqual(short_line_need(4), 1.5)

    def test_d2_passes_with_warning(self):
        errs, warns = check_dialogue_density(self._seg())
        self.assertFalse([e for e in errs if "D2" in e], errs)
        self.assertTrue(any("D2 短句鏡偏長" in w for w in warns), warns)

    def test_long_lines_unaffected(self):
        seg = self._seg()
        seg["shots"][1]["dialogue_and_audio"]["line_verbatim"] = "你到底是誰"
        errs, warns = check_dialogue_density(seg)  # 5 字不是短句，不扣
        self.assertFalse(any("短句鏡" in w for w in warns))

    def test_pacing_gate_same_rule(self):
        seg = {"id": "V1-23", "kind": "dialogue", "duration": 5.0,
               "lines": [{"text": "媽的這到底是什麼鬼東西啊", "start": 0.2, "end": 2.8},
                         {"text": "哎！", "start": 3.1, "end": 3.5}],
               "shots": [{"start": 0.0, "end": 3.0, "has_dialogue": True},
                         {"start": 3.0, "end": 5.0, "has_dialogue": True}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"segments": [seg]}, f, ensure_ascii=False)
        out = subprocess.run([sys.executable, str(GATE), f.name], capture_output=True, text=True,
                             encoding="utf-8").stdout
        self.assertNotIn("空跑", out)  # 舊算 13/5.0=2.6 <2.8 會警告空跑


class UnreferencedCharacter(unittest.TestCase):
    """#11／SB-4：沒有包／設定圖的配角佔 MS 以上主鏡 → 6e 警告；有包、voice_only、遠景不報。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "adapt").mkdir()
        (self.root / "assets").mkdir()
        (self.root / "layer2").mkdir()
        (self.root / "adapt" / "bible.json").write_text(json.dumps({"characters": [
            {"id": "C-hero", "reference_image": "images/hero.png"},
            {"id": "C-guide"}, {"id": "C-god", "voice_only": True}]}), encoding="utf-8")
        (self.root / "assets" / "character-packs.json").write_text(json.dumps({"packs": {"C-girl": "girl_pack"}}),
                                                                   encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _data(self, ids, size="MCU"):
        return {"segment_id": "V1-01", "metadata": {"lighting_lock_line": "x", "target_duration_sec": 3.0},
                "shots": [{"shot_id": "SH01", "start_time": 0, "end_time": 3.0, "duration": 3.0,
                           "character_ids": ids, "camera_optics": {"shot_size": size},
                           "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}}]}

    def test_load_reference_ids(self):
        refs, voice = vs.load_reference_ids(self.root)
        self.assertEqual(refs, {"C-hero", "C-girl"})
        self.assertEqual(voice, {"C-god"})
        self.assertIsNone(vs.load_reference_ids(None)[0])
        f = self.root / "layer2" / "layer2-V1-01.json"
        f.write_text("{}", encoding="utf-8")
        self.assertEqual(vs.find_project_root(f), self.root.resolve())

    def test_guide_close_up_warns(self):
        refs, voice = vs.load_reference_ids(self.root)
        res = vs.validate_storyboard_data(self._data(["C-hero", "C-guide", "C-god"]), ref_ids=refs, voice_only_ids=voice)
        hits = [w for w in res["warnings"] if "6e" in w]
        self.assertEqual(len(hits), 1, res["warnings"])
        self.assertIn("C-guide", hits[0])
        self.assertNotIn("C-god", hits[0])

    def test_wide_and_no_root_do_not_warn(self):
        refs, voice = vs.load_reference_ids(self.root)
        res = vs.validate_storyboard_data(self._data(["C-guide"], "LS"), ref_ids=refs, voice_only_ids=voice)
        self.assertFalse([w for w in res["warnings"] if "6e" in w])
        res = vs.validate_storyboard_data(self._data(["C-guide"]))
        self.assertFalse([w for w in res["warnings"] if "6e" in w])


class CodexPanelPrompt(unittest.TestCase):
    """#12／#13（SB-5／SB-6）：左右寫觀眾視角；已消失的物件不寫進構圖、明寫畫面中沒有，可停用母版。"""

    def _shot(self, **extra):
        shot = {"shot_id": "V1-10-SH01", "character_ids": [], "camera_optics": {"shot_size": "MCU"},
                "spatial_blocking": {"blocking_desc": "導遊站畫左，臉朝畫右，巨鳥在蛙仙石上方盤旋"}}
        shot.update(extra)
        return shot

    def test_viewer_side(self):
        prompt = cp.build_panel_prompt(self._shot(), {}, [], {}, [])
        self.assertIn("畫面左側（觀眾視角）", prompt)
        self.assertIn("臉朝畫面右側（觀眾視角）", prompt)
        self.assertNotIn("站畫左", prompt)
        self.assertIn("viewer's left or right of the image", prompt)
        self.assertIn("nose points at the image's left edge", prompt)
        self.assertEqual(cp.viewer_side_text("畫面左側（觀眾視角）"), "畫面左側（觀眾視角）")

    def test_absent_objects_dropped_and_negated(self):
        shot = self._shot()
        shot["spatial_blocking"]["absent_objects"] = ["巨鳥"]
        prompt = cp.build_panel_prompt(shot, {}, [], {}, [])
        comp = next(l for l in prompt.splitlines() if l.startswith("Composition"))
        self.assertNotIn("巨鳥", comp)
        self.assertIn("畫面中沒有：巨鳥", prompt)
        self.assertIn("no 巨鳥", prompt)

    def test_segment_level_absent_and_master_disabled(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        r = Path(tmp.name)
        (r / "layer2").mkdir()
        (r / "images").mkdir()
        (r / "images" / "S-rock.png").write_bytes(b"x")
        seg = r / "layer2" / "layer2-V1-26.json"
        seg.write_text(json.dumps({"segment_id": "V1-26", "metadata": {"absent_objects": ["蛙仙石"]},
                                   "asset_refs": {"scene_id": "S-rock"},
                                   "shots": [self._shot(shot_id="SH01"),
                                             self._shot(shot_id="SH02", scene_master_disabled=True)]},
                                  ensure_ascii=False), encoding="utf-8")
        jobs = cp.plan(r, [seg])
        self.assertEqual([Path(p).name for _, p in jobs[0]["refs"]], ["S-rock.png"])
        self.assertEqual(jobs[1]["refs"], [])
        self.assertIn("畫面中沒有：蛙仙石", jobs[1]["prompt"])
        comp = next(l for l in jobs[1]["prompt"].splitlines() if l.startswith("Composition"))
        self.assertNotIn("蛙仙石", comp)


if __name__ == "__main__":
    unittest.main()
