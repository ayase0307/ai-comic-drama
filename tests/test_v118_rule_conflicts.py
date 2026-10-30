# -*- coding: utf-8 -*-
"""v118 實測規則衝突修正（#116／#117／#118 新規則為準，舊規則改成一致）。

每個 TestCase 對應 rule-conflicts.md 的一條：
  #1／#12 鏡長下限 1.2 s（編譯器、audit E4 首／相鄰／末切點），1.2–2.0 s 只提醒
  #2 同鏡接話 extra_lines → 每句一個 <d>
  #3 17n+5 取整 tail-fit（末句後 0.3 s）
  #4 validate 語速：畫內 4.7、VO 5.8 字/秒
  #5 說話佔比 >60% 舊警告 → >90%（#118 75–90%）
  #6 pacing_gate 密度扣段首／段尾無台詞鏡（同 D2）
  #7 adapt_gate --source-text 略過專有名詞引號
  #8 原著對白全保留時密度 3.6–3.9 只備註；停頓／建立標記上限
  #9 source_action 動作鏡不計入有人聲鏡比例
  #10 VO 16–18 字留 H3
  #11 beat_pause 的切鏡後開口與 D4 一致（≤1.2 s）
"""
import copy
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
import compile_layer2_to_h3 as compiler  # noqa: E402
import estimate_duration  # noqa: E402
import h3_spec  # noqa: E402
import validate_storyboard as vs  # noqa: E402
from dialogue_density import check_dialogue_density  # noqa: E402
from tests import test_h3_compiler as base  # noqa: E402

GATE = ROOT / "scripts" / "storyboard" / "pacing_gate.py"


class _CompilerFixture(unittest.TestCase):
    # 借用 test_h3_compiler 的夾具（不在模組層級引用那個 TestCase，免得它的測試在這裡重跑）
    setUp = base.H3CompilerRegressionTests.setUp
    segment = base.H3CompilerRegressionTests.segment
    shot = staticmethod(base.H3CompilerRegressionTests.shot)
    compile = base.H3CompilerRegressionTests.compile

    def single(self, start_end_pairs, lines=None, target=None):
        data = self.segment()
        shots = []
        for i, (a, b) in enumerate(start_end_pairs):
            line = (lines or {}).get(i)
            shots.append(self.shot(f"S{i+1}", a, b, f"Mira moves step {i+1}.", line=line))
        data["shots"] = shots
        data["metadata"]["target_duration_sec"] = target or start_end_pairs[-1][1]
        return data


class ShortShotBounds(_CompilerFixture):
    """#1／#12：每鏡 ≥1.2 s 合規（#116 說話窗口下限），1.2–2.0 s 只提醒。"""

    def test_constants(self):
        self.assertEqual(h3_spec.MIN_SHOT_SEC, 1.2)
        self.assertEqual(h3_spec.SHOT_SOFT_MIN_SEC, 2.0)

    def test_compiler_accepts_1_5s_shot_with_note(self):
        data = self.single([(0.0, 3.0), (3.0, 4.5), (4.5, 7.5)])
        compiled = self.compile(data)
        notes = " ".join(compiled.get("compile_notes") or [])
        self.assertIn("[短鏡]", notes)
        self.assertIn("Shot 2 1.50s", notes)

    def test_compiler_rejects_shot_below_1_2s(self):
        data = self.single([(0.0, 3.0), (3.0, 4.0), (4.0, 7.5)])
        with self.assertRaises(ValueError) as ctx:
            self.compile(data)
        self.assertIn("cut bounds", str(ctx.exception))

    def _lint(self, last_cut):
        prompt = ("subject_definitions:\n<Picture 1> is the plate.\n<Subject 1> is the woman in <Picture 2>.\n\n"
                  "summary:\n[reference generation] Two shots.\n\nretention_analysis:\n<Subject 1>: fully_preserved.\n\n"
                  "detailed_description:\nLive-action cinematic, illuminated by soft dusk sunlight.\n"
                  "[Shot 1] Medium shot, first she moves then the camera trucks left.\n"
                  f"[Shot 2] At 00:{last_cut:06.3f}, close up shot, first she looks then as the camera holds a static shot.\n\n"
                  "overall_soundscape:\nWind blows.\n\nnon_diegetic_music:\nN/A\n")
        return audit.lint_h3_prompt(prompt, nominal_duration=7.0, rounding_mode="floor")

    def test_e4_tail_room_1_2_to_2_is_warning_only(self):
        res = self._lint(5.0)  # D=6.583 → 末鏡 1.583 s
        self.assertFalse([e for e in res["errors"] if "E4" in e], res["errors"])
        self.assertTrue(any("W:E4 短鏡" in w for w in res["warnings"]))

    def test_e4_tail_room_below_1_2_is_error(self):
        res = self._lint(5.5)  # 末鏡 1.083 s
        self.assertTrue(any("E4: 末切點空間不足" in e for e in res["errors"]), res["errors"])


class SameShotReply(_CompilerFixture):
    """#2：同鏡接話寫在 extra_lines，編譯器逐句給 <d>（不再編譯後手動注入）。"""

    def setUp(self):
        super().setUp()
        self.registry.characters["C-YE"] = {
            "id": "C-YE", "name": "Ye", "desc_en": "Ye, long silver hair, blue robe", "desc_zh": "葉",
            "ref_img": "assets/characters/ye.png", "wardrobe_states": {}, "is_creature": False,
        }

    def _data(self):
        data = self.single([(0.0, 3.0), (3.0, 7.0)], lines={1: "回去早點休息。"})
        sh = data["shots"][1]
        sh["character_ids"] = ["C-MIRA", "C-YE"]
        data["asset_refs"]["characters"].append({"id": "C-YE"})
        sh["dialogue_and_audio"]["speech_window"] = {"start": 3.3, "end": 4.9}
        sh["dialogue_and_audio"]["extra_lines"] = [{
            "speaker": "C-YE", "line_verbatim": "知道。", "speech_window": {"start": 5.2, "end": 5.8},
            "voice_4d_spec_en": "a calm low voice"}]
        return data

    def test_two_d_blocks_and_second_speaker_id(self):
        compiled = self.compile(self._data())
        prompt = compiled["h3_prompt"]
        self.assertIn("<d>[Chinese] 回去早點休息。</d>", prompt)
        self.assertIn("<d>[Chinese] 知道。</d>", prompt)
        self.assertIn("Speech window: segment_seconds 5.200–5.800. Right after that line,", prompt)
        self.assertRegex(prompt, r"\(S2\), a calm low voice, answers: <d>\[Chinese\] 知道。</d> while .+'s lips remain completely closed")

    def test_dialogue_density_counts_extra_line(self):
        d = {"segment_id": "T", "shots": [
            {"shot_id": "A", "start_time": 0, "end_time": 2.0,
             "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "回去早點休息",
                                    "extra_lines": [{"line_verbatim": "知道知道"}]}}]}
        errs, _ = check_dialogue_density(d)  # 10 字 / 2.0 s = 5.0（只算第一句 3.0 也過）
        self.assertEqual([e for e in errs if "D2" in e], [])
        d["shots"][0]["end_time"] = 3.2  # 只算第一句 6/3.2=1.9 FAIL；含接話 10/3.2=3.1 過
        errs, _ = check_dialogue_density(d)
        self.assertEqual([e for e in errs if "D2" in e], [])


class TailFitRounding(_CompilerFixture):
    """#3：17n+5 往上取整撐長末句後留白時，往下取一格（仍念得完、更接近 0.3 s）。"""

    def _data(self, target, end):
        data = self.single([(0.0, target)], lines={0: "Stay right here."}, target=target)
        data["shots"][0]["dialogue_and_audio"]["speech_window"] = {"start": 0.3, "end": end}
        return data

    def test_floor_when_ceil_overshoots_0_3_tail(self):
        compiled = self.compile(self._data(8.75, 8.45))  # ceil 9.417（句後 0.967）／floor 8.708（0.258）
        meta = compiled["metadata"]
        self.assertEqual(meta["rounding_mode"], "floor")
        self.assertEqual(meta["rounding_reason"], "tail-fit")
        self.assertAlmostEqual(meta["effective_duration_sec"], 209 / 24, places=3)
        self.assertTrue(any("[tail-fit]" in n for n in compiled["compile_notes"]))

    def test_ceil_kept_when_floor_would_cut_last_line(self):
        compiled = self.compile(self._data(9.0, 8.7))  # floor 8.708 → 句後 0.008 < 0.1
        self.assertEqual(compiled["metadata"]["rounding_mode"], "ceil")

    def test_opt_out(self):
        data = self._data(8.75, 8.45)
        data["metadata"]["disable_tail_fit"] = True
        self.assertEqual(self.compile(data)["metadata"]["rounding_mode"], "ceil")


def _vs_shot(sid, a, b, line=None, **dlg):
    d = {"has_dialogue": bool(line), "speaker": "C-A" if line else "", "line_verbatim": line or "",
         "lips_closed_lock": not line}
    d.update(dlg)
    return {"shot_id": sid, "start_time": a, "end_time": b, "duration": b - a,
            "camera_optics": {"shot_size": "MS"}, "dialogue_and_audio": d}


def _vs_data(*shots, target=None):
    return {"segment_id": "T", "metadata": {"lighting_lock_line": "x",
                                            "target_duration_sec": target or shots[-1]["end_time"]},
            "shots": list(shots)}


class ValidateRates(unittest.TestCase):
    """#4／#5：語速閘門依畫內／VO 分線；說話佔比 >90% 才提醒。"""

    def run_vs(self, *shots, **kw):
        return vs.validate_storyboard_data(_vs_data(*shots, **kw))

    def test_vo_at_5_5_passes(self):
        res = self.run_vs(_vs_shot("SH01", 0, 2.0, "一二三四五六七八九十一", audio_type="voiceover"))
        self.assertFalse([e for e in res["errors"] if "語速超載" in e], res["errors"])

    def test_onscreen_above_4_7_fails(self):
        res = self.run_vs(_vs_shot("SH01", 0, 2.0, "一二三四五六七八九十一"))
        self.assertTrue([e for e in res["errors"] if "語速超載" in e])

    def test_onscreen_4_5_passes_old_4_2_gate(self):
        res = self.run_vs(_vs_shot("SH01", 0, 2.0, "一二三四五六七八九"))
        self.assertFalse([e for e in res["errors"] if "語速超載" in e])

    def test_speech_share_75_percent_no_warning(self):
        # 27 字 ÷ 4.5 = 6 s / 8 s = 75%（舊規 4 字/秒、>60% 會警告）
        res = self.run_vs(_vs_shot("SH01", 0, 4.0, "一二三四五六七八九十一二三四"),
                          _vs_shot("SH02", 4.0, 8.0, "一二三四五六七八九十一二三"))
        self.assertFalse([w for w in res["warnings"] if "說話佔比" in w or "台詞密度過高" in w])

    def test_estimate_and_audit_share_threshold(self):
        self.assertEqual(estimate_duration.SPEECH_SHARE_WARN, 0.90)
        self.assertEqual(audit.W13_SPEECH_SHARE_WARN, 0.90)
        self.assertEqual(audit.W13_LINE_SUGGEST_MAX, 18)


def _gate(seg):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"segments": [seg]}, f, ensure_ascii=False)
    return subprocess.run([sys.executable, str(GATE), f.name], capture_output=True, text=True).stdout


class PacingGateAlignment(unittest.TestCase):
    def test_density_uses_d2_allowance(self):  # #6
        seg = {"id": "s", "duration": 7.0, "kind": "dialogue", "prompt": "real-time speed",
               "lines": [{"text": "一二三四五六七八", "start": 2.2, "end": 4.0},
                         {"text": "一二三四五六七", "start": 4.3, "end": 6.0}],
               "shots": [{"start": 0, "end": 2.0, "has_dialogue": False},
                         {"start": 2.0, "end": 7.0, "has_dialogue": True}]}
        out = _gate(seg)  # 整段 15/7=2.14；扣段首 2 s → 15/5=3.0
        self.assertNotIn("對話密度", out)
        seg["shots"] = []
        self.assertIn("對話密度 2.14", _gate(seg))

    def test_source_action_shot_exempt_from_voiced_ratio(self):  # #9
        seg = {"id": "s", "duration": 7.0, "kind": "action", "prompt": "real-time speed",
               "lines": [{"text": "一二三四五六七八九十", "start": 2.6, "end": 5.0}],
               "shots": [{"start": 0, "end": 2.4, "has_dialogue": False, "source_action": True},
                         {"start": 2.4, "end": 7.0, "has_dialogue": True}]}
        self.assertNotIn("有人聲鏡", _gate(seg))
        seg["shots"][0]["source_action"] = False
        self.assertIn("有人聲鏡 1/2", _gate(seg))

    def test_beat_pause_onset_matches_d4(self):  # #11
        seg = {"id": "s", "duration": 6.0, "kind": "action", "prompt": "real-time speed",
               "lines": [{"text": "一二三四五", "start": 1.0, "end": 2.2, "cut_start": True, "beat_pause": True}]}
        self.assertNotIn("切鏡後", _gate(seg))
        seg["lines"][0]["beat_pause"] = False
        self.assertIn("切鏡後 1.0s 才開口", _gate(seg))


class AdaptGateAlignment(unittest.TestCase):
    def test_source_text_skips_proper_noun_quotes(self):  # #7
        novel = ("一行人正對一群住在「蛙仙大旅社」的旅客。\n"
                 "少女笑咪咪地接口說：「這是蛙仙嗎？不大像。」\n"
                 "「要有想像力啊。」\n"
                 "青年點頭：「知道」\n")
        skipped = []
        quotes = adapt_gate.source_quotes(novel, skipped)
        self.assertEqual(quotes, ["這是蛙仙嗎？不大像。", "要有想像力啊。", "知道"])
        self.assertEqual(skipped, ["蛙仙大旅社"])

    def _script(self, lines, pause=""):
        body = "\n".join(f"{'阿青' if i % 2 == 0 else '阿木'}：{t}" for i, t in enumerate(lines)) + pause
        return ("第01集｜測試\n<!-- source: 卷1 L1-L9 -->\n1-1 測試場 日/內\n人物：阿青、阿木\n"
                f"{body}\n<!-- episode-end: 「{lines[-1]}」 | 換場 -->\n")

    def test_full_source_dense_is_note_not_warn(self):  # #8
        lines = ["這句台詞剛好十一個字啊"] * 10
        script = self._script(lines, pause="\n△【停頓1.2】兩人對望。")
        res = adapt_gate.run_gate(script, quotes=["這句台詞剛好十一個字啊"])
        d = res["stats"]["density"]
        self.assertTrue(3.6 < d <= 3.9, d)
        self.assertFalse([w for w in res["warns"] if w.startswith("G3 密度")])
        self.assertTrue(any("原著對白全保留" in n for n in res["notes"]))
        res2 = adapt_gate.run_gate(script, quotes=["這句台詞剛好十一個字啊", "沒有出現的原著台詞"])
        self.assertTrue(any(w.startswith("G3 密度") for w in res2["warns"]))

    def test_marker_caps_warn(self):  # #8
        text = self._script(["這句台詞剛好十一個字啊"] * 6)
        extra = "△【停頓0.8】靜。\n" * 4 + "△【建立2.0】遠景。\n△【建立2.0】遠景。\n"
        text = text.replace("人物：阿青、阿木\n", "人物：阿青、阿木\n" + extra)
        res = adapt_gate.run_gate(text, quotes=["這句台詞剛好十一個字啊"])
        self.assertTrue(any("刻意停頓 4 處 > 3" in w for w in res["warns"]), res["warns"])
        self.assertTrue(any("建立鏡 2 處 > 1" in w for w in res["warns"]), res["warns"])


class VoiceoverRouting(_CompilerFixture):
    """#10：16–18 字 VO 預設留 H3（不多一道外部 TTS），只提醒超過實測範圍。"""

    def _vo(self, line):
        data = self.single([(0.0, 6.0)], lines={0: line}, target=6.0)
        dlg = data["shots"][0]["dialogue_and_audio"]
        dlg.update(offscreen_form="voiceover", offscreen_voice_en="a calm, flat teenage male voice")
        return self.compile(data)

    def test_17_chars_stays_h3_with_note(self):
        line = "媽的，人生用這種方式結束，也算得上別緻呢。"  # 18 字
        compiled = self._vo(line)
        self.assertIn(f"<d>[Chinese] {line}</d>", compiled["h3_prompt"])
        self.assertEqual(compiled["external_narration"], [])
        self.assertTrue(any("超過實測範圍" in n for n in compiled["compile_notes"]))

    def test_over_18_goes_external(self):
        line = "媽的，人生用這種方式結束，也算得上相當別緻吧。"  # 20 字
        compiled = self._vo(line)
        self.assertEqual([e["line"] for e in compiled["external_narration"]], [line])


if __name__ == "__main__":
    unittest.main()
