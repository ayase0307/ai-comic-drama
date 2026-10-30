# -*- coding: utf-8 -*-
"""雙人引子（E3）× #116／#117／#118／#120 節奏規則的配套。

引子（shots[0].dual_lead_in）組裝時剪掉、不是成片，所以：
  - pacing_gate 的密度、有人聲鏡比例（≥80%）、切鏡後開口、開口次數都不算它（段長扣掉 2.0 s）
  - validate_storyboard D1–D4、說話佔比、分段時長提醒、9:16 景別比例以成片計
  - audit W13 說話佔比分母扣掉引子（否則引子把過載的段稀釋成合格）
  - #120 的 tail-fit／17n+5、extra_lines、speech_window 偏移和「引子後整段往後挪 2 s」相容
  - W48／assemble 也檢查 extra_lines、line_timecodes 沒落在引子裡
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

import audit_refs_and_segments as audit  # noqa: E402
import dual_lead_in  # noqa: E402
import h3_spec  # noqa: E402
import validate_storyboard as vs  # noqa: E402
from dialogue_density import check_dialogue_density  # noqa: E402
from tests import test_h3_compiler as base  # noqa: E402

GATE = ROOT / "scripts" / "storyboard" / "pacing_gate.py"


def _gate(seg):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"segments": [seg]}, f, ensure_ascii=False)
    return subprocess.run([sys.executable, str(GATE), f.name], capture_output=True, text=True).stdout


def _lead_shot(end=2.0):
    return {"start": 0.0, "end": end, "has_dialogue": False, "dual_lead_in": True}


class PacingGateExcludesLeadIn(unittest.TestCase):
    def test_voiced_ratio_ignores_lead_in(self):
        seg = {"id": "s", "duration": 8.0, "kind": "dialogue", "prompt": "real-time speed",
               "lines": [{"text": "一二三四五六", "start": 2.2, "end": 3.8},
                         {"text": "一二三四五六", "start": 4.2, "end": 5.8},
                         {"text": "一二三四五六", "start": 6.1, "end": 7.7}],
               "shots": [_lead_shot(), {"start": 2.0, "end": 4.0, "has_dialogue": True},
                         {"start": 4.0, "end": 6.0, "has_dialogue": True},
                         {"start": 6.0, "end": 8.0, "has_dialogue": True}]}
        self.assertNotIn("有人聲鏡", _gate(seg))  # 3/3（引子不算）
        seg["shots"][0]["dual_lead_in"] = False
        self.assertIn("有人聲鏡 3/4", _gate(seg))  # 沒標就是一般無台詞鏡

    def test_density_and_duration_exclude_lead_in(self):
        # 引子 2 s＋無台詞插入鏡 4 s＋說話 5 s；15 字
        seg = {"id": "s", "duration": 11.0, "kind": "dialogue", "prompt": "real-time speed",
               "lines": [{"text": "一二三四五", "start": 6.2, "end": 7.4},
                         {"text": "一二三四五", "start": 7.8, "end": 9.0},
                         {"text": "一二三四五", "start": 9.4, "end": 10.6}],
               "shots": [_lead_shot(), {"start": 2.0, "end": 6.0, "has_dialogue": False},
                         {"start": 6.0, "end": 11.0, "has_dialogue": True}]}
        out = _gate(seg)  # 成片 9 s、扣段首 4 s → 15/5=3.0；若把引子算進來 15/(11-5)=2.5 會警告
        self.assertNotIn("對話密度", out)
        seg["shots"][0]["dual_lead_in"] = False
        self.assertIn("對話密度 2.50", _gate(seg))

    def test_onset_after_cut_measured_after_lead_in(self):
        seg = {"id": "s", "duration": 6.0, "kind": "dialogue", "prompt": "real-time speed",
               "lines": [{"text": "一二三四五六七八九十", "start": 2.3, "end": 4.6, "cut_start": True}],
               "shots": [_lead_shot(), {"start": 2.0, "end": 6.0, "has_dialogue": True}]}
        self.assertNotIn("切鏡後", _gate(seg))  # 引子剪掉後是切鏡後 0.3 s 開口
        seg["shots"][0]["dual_lead_in"] = False
        self.assertIn("切鏡後 2.3s 才開口", _gate(seg))

    def test_tail_freeze_warning_still_applies(self):
        seg = {"id": "s", "duration": 6.0, "kind": "dialogue", "prompt": "The final second holds still.",
               "lines": [{"text": "一二三四五六七八九十", "start": 2.3, "end": 4.6}],
               "shots": [_lead_shot(), {"start": 2.0, "end": 6.0, "has_dialogue": True}]}
        self.assertIn("末 1 秒靜止", _gate(seg))

    def test_strip_pacing_shifts_everything(self):
        seg = {"id": "s", "duration": 9.0, "lines": [{"text": "x", "start": 2.5, "end": 3.0}],
               "shots": [_lead_shot(), {"start": 2.0, "end": 9.0, "has_dialogue": True}]}
        out = dual_lead_in.strip_pacing(seg)
        self.assertEqual(out["duration"], 7.0)
        self.assertEqual(out["shots"], [{"start": 0.0, "end": 7.0, "has_dialogue": True}])
        self.assertEqual((out["lines"][0]["start"], out["lines"][0]["end"]), (0.5, 1.0))
        self.assertIs(dual_lead_in.strip_pacing({"id": "x", "shots": [{"start": 0, "end": 3}]})["shots"][0]["end"], 3)


def _l2(start, end, line=None, size="MCU", lead=False, timecodes=None, **dlg):
    d = {"has_dialogue": bool(line), "speaker": "C-A" if line else "", "line_verbatim": line or "",
         "lips_closed_lock": not line}
    if timecodes:
        d["line_timecodes"] = timecodes
    d.update(dlg)
    shot = {"shot_id": f"SH{int(start * 10):03d}", "start_time": start, "end_time": end, "duration": round(end - start, 4),
            "character_ids": ["C-A", "C-B"] if lead else ["C-A"],
            "camera_optics": {"shot_size": "MLS" if lead else size}, "dialogue_and_audio": d}
    if lead:
        shot["dual_lead_in"] = True
    return shot


def _l2_data(*shots, aspect="16:9"):
    return {"segment_id": "T", "metadata": {"lighting_lock_line": "x", "aspect_ratio": aspect,
                                            "target_duration_sec": shots[-1]["end_time"]},
            "shots": list(shots)}


class StoryboardGatesExcludeLeadIn(unittest.TestCase):
    def test_d2_allowance_not_eaten_by_lead_in(self):
        data = _l2_data(_l2(0.0, 2.0, lead=True), _l2(2.0, 6.0),
                        _l2(6.0, 11.0, "一二三四五六七八九十一二三四五"))
        errs, _ = check_dialogue_density(data)  # 成片 9 s 扣段首 4 s → 15/5=3.0
        self.assertEqual([e for e in errs if "D2" in e], [])
        data["shots"][0].pop("dual_lead_in")
        errs, _ = check_dialogue_density(data)  # 引子當一般無台詞鏡：15/(11-5)=2.5 FAIL
        self.assertTrue([e for e in errs if "D2" in e])

    def test_d4_onset_with_shifted_timecodes(self):
        tc = [{"text": "一二三四五六七八九十", "start": 2.3, "end": 4.6}]
        data = _l2_data(_l2(0.0, 2.0, lead=True), _l2(2.0, 5.0, "一二三四五六七八九十", timecodes=tc))
        errs, _ = check_dialogue_density(data)
        self.assertEqual([e for e in errs if "D4" in e], [])
        tc[0]["start"], tc[0]["end"] = 2.9, 4.9  # 切鏡後 0.9 s：去掉引子後一樣要被抓
        errs, _ = check_dialogue_density(data)
        self.assertTrue([e for e in errs if "D4" in e and "0.90s" in e], errs)

    def test_speech_share_and_duration_use_film_length(self):
        # 37 字 ÷ 4.5 ≈ 8.2 s；成片 9 s → 91% 要提醒；連引子 11 s 算是 75% 會漏掉
        data = _l2_data(_l2(0.0, 2.0, lead=True), _l2(2.0, 6.5, "一二三四五六七八九十一二三四五六七八"),
                        _l2(6.5, 11.0, "一二三四五六七八九十一二三四五六七八九"))
        res = vs.validate_storyboard_data(data)
        share = [w for w in res["warnings"] if "說話佔比" in w]
        self.assertTrue(share and "已扣雙人引子 2s" in share[0], res["warnings"])
        self.assertFalse([w for w in res["warnings"] if "分段時長提醒" in w])  # 成片 9 s 在 5–10 s 內
        data["shots"][0].pop("dual_lead_in")
        res = vs.validate_storyboard_data(data)
        self.assertFalse([w for w in res["warnings"] if "說話佔比" in w])
        self.assertTrue([w for w in res["warnings"] if "分段時長提醒" in w])  # 11 s > 10 s

    def test_vertical_close_up_ratio_ignores_lead_in(self):
        data = _l2_data(_l2(0.0, 2.0, lead=True), _l2(2.0, 5.0, "一二三四五六七八九十"),
                        _l2(5.0, 8.0, "一二三四五六七八九十"), aspect="9:16")
        res = vs.validate_storyboard_data(data)
        self.assertFalse([w for w in res["warnings"] if "豎屏構圖" in w])  # 2/2 近景（引子 MLS 不算）

    def test_time_conservation_still_counts_lead_in(self):
        data = _l2_data(_l2(0.0, 2.0, lead=True), _l2(2.0, 9.0, "一二三四五六七八九十一二三四五六七八九十一"))
        res = vs.validate_storyboard_data(data)
        self.assertFalse([e for e in res["errors"] if "時長不守恆" in e])  # 生成時長＝含引子


class AuditW13ExcludesLeadIn(unittest.TestCase):
    PROMPT = ("subject_definitions:\n<Picture 1> is the plate.\n<Subject 1> is the woman in <Picture 2>.\n\n"
              "summary:\n[reference generation] Two shots.\n\nretention_analysis:\n<Subject 1>: fully_preserved.\n\n"
              "detailed_description:\nLive-action cinematic, illuminated by soft dusk sunlight.\n"
              "[Shot 1] Medium-wide shot, first she looks up then as the camera holds a static shot.\n"
              "[Shot 2] At 00:02.000, close up shot, first she speaks then the camera holds a static shot. "
              "(S1) says: <d>[Chinese] 一二三四五六七八九十一二三四五六七八</d> "
              "<d>[Chinese] 一二三四五六七八九十一二三四五六七</d> <d>[Chinese] 一二三四五六七八九十</d>\n\n"
              "overall_soundscape:\nWind blows.\n\nnon_diegetic_music:\nN/A\n")

    def test_w13_ratio_uses_film_length(self):
        shots = [{"start_time": 0.0, "end_time": 2.0, "dual_lead_in": True},
                 {"start_time": 2.0, "end_time": 12.0}]
        with_lead = audit.lint_h3_prompt(self.PROMPT, nominal_duration=12.0, rounding_mode="floor", authored_shots=shots)
        shots[0].pop("dual_lead_in")
        plain = audit.lint_h3_prompt(self.PROMPT, nominal_duration=12.0, rounding_mode="floor", authored_shots=shots)
        self.assertEqual(with_lead["details"]["dual_lead_in_sec"], 2.0)
        self.assertGreater(with_lead["details"]["speech_ratio"], plain["details"]["speech_ratio"])
        self.assertTrue([w for w in with_lead["warnings"] if "W13: 台詞佔比過載" in w and "已扣雙人引子" in w])
        self.assertFalse([w for w in plain["warnings"] if "W13: 台詞佔比過載" in w])


class LeadInCheckCoversV120Windows(unittest.TestCase):
    def _seg(self, **dlg):
        return {"segment_id": "X", "shots": [_l2(0.0, 2.0, lead=True), _l2(2.0, 7.0, "受傷了嗎？",
                                                                          speech_window={"start": 2.4, "end": 3.6}, **dlg)]}

    def test_extra_lines_window_inside_lead_in_is_rejected(self):
        seg = self._seg(extra_lines=[{"speaker": "C-B", "line_verbatim": "沒有。", "speech_window": {"start": 1.5, "end": 2.2}}])
        self.assertTrue([p for p in dual_lead_in.check(seg) if "extra_lines[1].speech_window" in p])
        seg["shots"][1]["dialogue_and_audio"]["extra_lines"][0]["speech_window"] = {"start": 4.0, "end": 4.8}
        self.assertEqual(dual_lead_in.check(seg), [])

    def test_line_timecodes_inside_lead_in_is_rejected(self):
        seg = self._seg(line_timecodes=[{"text": "受傷了嗎？", "start": 1.0, "end": 2.2}])
        self.assertTrue([p for p in dual_lead_in.check(seg) if "line_timecodes[1]" in p])

    def test_lead_in_may_not_carry_extra_lines(self):
        seg = self._seg()
        seg["shots"][0]["dialogue_and_audio"]["extra_lines"] = [{"line_verbatim": "", "speech_window": {"start": 0.5, "end": 1.0}}]
        self.assertTrue([p for p in dual_lead_in.check(seg) if "引子不可有" in p])

    def test_strip_layer2_shifts_all_windows(self):
        seg = self._seg(extra_lines=[{"line_verbatim": "沒有。", "speech_window": {"start": 4.0, "end": 4.8}}],
                        line_timecodes=[{"text": "受傷了嗎？", "start": 2.4, "end": 3.6}])
        seg["metadata"] = {"target_duration_sec": 7.0}
        out = dual_lead_in.strip_layer2(seg)
        self.assertEqual(len(out["shots"]), 1)
        sh = out["shots"][0]
        dlg = sh["dialogue_and_audio"]
        self.assertEqual((sh["start_time"], sh["end_time"]), (0.0, 5.0))
        self.assertEqual(dlg["speech_window"], {"start": 0.4, "end": 1.6})
        self.assertEqual(dlg["line_timecodes"][0]["start"], 0.4)
        self.assertEqual(dlg["extra_lines"][0]["speech_window"], {"start": 2.0, "end": 2.8})
        self.assertEqual(out["metadata"]["target_duration_sec"], 5.0)
        self.assertEqual(seg["shots"][1]["start_time"], 2.0)  # 原段不被改


class CompilerCompatibility(unittest.TestCase):
    """#120 tail-fit／17n+5、extra_lines、speech_window 偏移在引子後整段後移 2 s 時照常運作。"""

    setUp_base = base.H3CompilerRegressionTests.setUp
    segment = base.H3CompilerRegressionTests.segment
    shot = staticmethod(base.H3CompilerRegressionTests.shot)
    compile = base.H3CompilerRegressionTests.compile

    def setUp(self):
        self.setUp_base()
        self.registry.characters["C-YE"] = {
            "id": "C-YE", "name": "Ye", "desc_en": "Ye, long silver hair, blue robe", "desc_zh": "葉",
            "ref_img": "assets/characters/ye.png", "wardrobe_states": {}, "is_creature": False,
        }

    def _data(self, target, last_end, extra=False):
        data = self.segment()
        lead = self.shot("S1", 0.0, 2.0, "Mira sits still; Ye looks down toward frame left.")
        lead["character_ids"] = ["C-MIRA", "C-YE"]
        lead["dual_lead_in"] = True
        body = self.shot("S2", 2.0, target, "Mira looks up.", line="Stay right here.")
        body["dialogue_and_audio"]["speech_window"] = {"start": 2.3, "end": last_end}
        if extra:
            body["character_ids"] = ["C-MIRA", "C-YE"]
            body["dialogue_and_audio"]["speech_window"] = {"start": 2.3, "end": 3.9}
            body["dialogue_and_audio"]["extra_lines"] = [{
                "speaker": "C-YE", "line_verbatim": "知道。", "speech_window": {"start": 4.2, "end": last_end},
                "voice_4d_spec_en": "a calm low voice"}]
        data["shots"] = [lead, body]
        data["asset_refs"]["characters"].append({"id": "C-YE"})
        data["metadata"]["target_duration_sec"] = target
        return data

    def _frames_ok(self, compiled):
        frames = compiled["metadata"]["frames"] if "frames" in compiled["metadata"] else \
            h3_spec.frames_for(compiled["metadata"]["target_duration_sec"], rounding=compiled["metadata"]["rounding_mode"])
        self.assertEqual((frames - h3_spec.FRAME_QUANTUM_OFFSET) % h3_spec.FRAME_QUANTUM_STEP, 0)

    def test_tail_fit_floor_with_lead_in(self):
        # 同 #120 的 8.75／8.45 情境、整段後移：10.9／10.6 → ceil 11.542（句後 0.942）／floor 10.833（0.233）
        compiled = self.compile(self._data(10.9, 10.6))
        meta = compiled["metadata"]
        self.assertEqual(meta["rounding_mode"], "floor")
        self.assertEqual(meta["rounding_reason"], "tail-fit")
        self._frames_ok(compiled)
        self.assertIn("At 00:02.000", compiled["h3_prompt"])  # 引子後硬切在 2.0 s
        self.assertEqual(dual_lead_in.check(compiled), [])
        self.assertEqual(dual_lead_in.lead_in_seconds(compiled), 2.0)

    def test_tail_fit_keeps_ceil_when_floor_cuts_last_line(self):
        compiled = self.compile(self._data(11.2, 10.9))  # floor 10.833 < 末句 10.9
        self.assertEqual(compiled["metadata"]["rounding_mode"], "ceil")
        self._frames_ok(compiled)

    def test_extra_lines_after_lead_in(self):
        compiled = self.compile(self._data(7.0, 4.8, extra=True))
        prompt = compiled["h3_prompt"]
        self.assertIn("<d>[Chinese] 知道。</d>", prompt)
        self.assertIn("Speech window: segment_seconds 4.200–4.800.", prompt)
        self.assertEqual(dual_lead_in.check(compiled), [])


if __name__ == "__main__":
    unittest.main()
