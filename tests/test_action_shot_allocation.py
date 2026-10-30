# -*- coding: utf-8 -*-
"""原著無台詞動作鏡（劇本【動作】標記）一路強制到分鏡與編譯。

失敗案例（噩盡島 EP01 吞鳥鏡）：片長照台詞時間反推，無台詞動作只分到 2.2 秒，要塞「咬手、甩上半空、落進喉嚨」
三個動作；成片角色被拋起又掉回地上、沒被吞。正確是咬／甩／落喉三鏡約 7 秒。PR #123 的【動作】標記只進
「分鏡後預估片長」報告，分鏡與編譯不給時間——本 PR 補上：
  1. adapt_gate G14：一個【動作】行塞 ≥3 個動作要拆行；原著兩句台詞之間有動作敘述卻沒標【動作】
  2. handoff_to_skeleton：每個標記獨立一鏡、鏡長＝標記秒數、依劇本先後排、fit 不壓縮、切段不截短
  3. validate D5（標記遺失／合併／截短）、D6（無台詞鏡 ≥3 個動作且鏡長不夠）
  4. D1–D4、pacing_gate 台詞類檢查不計動作鏡
  5. 編譯器末鏡是動作鏡時不 tail-fit（不截短動作），17n+5 照舊
  6. 沒標記的舊專案行為不變
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "scripts" / "adapt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import action_marks as am  # noqa: E402
import adapt_gate  # noqa: E402
import h3_spec  # noqa: E402
import handoff_to_skeleton as hts  # noqa: E402
import sync_script  # noqa: E402
import validate_storyboard as vs  # noqa: E402
from dialogue_density import check_dialogue_density  # noqa: E402
from validate_structure import parse_and_validate_script  # noqa: E402
from tests import test_h3_compiler as base  # noqa: E402

GATE = ROOT / "scripts" / "storyboard" / "pacing_gate.py"

SOURCE = ("洛年抬頭看著天空。「那是什麼？」他問。\n"
          "懷真臉色一變：「快跑！」\n"
          "話音未落，巨鳥俯衝而下，一口咬住洛年的手，把他甩上半空，張開大嘴，洛年就這麼落進了牠的喉嚨。\n"
          "「洛年！」懷真大喊。\n")
HEAD = "第01集｜吞鳥\n<!-- source: 卷1 L1-L9 -->\n1-1 火山口 日/外\n人物：洛年、懷真\n△洛年抬頭望天。\n洛年：那是什麼？\n懷真：快跑！\n"
TAIL = "懷真：洛年！\n<!-- episode-end: 「懷真大喊」 | 換場 -->\n"
SPLIT3 = ("△【動作2.3】巨鳥俯衝，一口咬住洛年的手。\n"
          "△【動作2.3】巨鳥把洛年甩上半空。\n"
          "△【動作2.4】洛年落進巨鳥的喉嚨。\n")
CRAMMED = "△【動作】巨鳥一口咬住洛年的手，把他甩上半空，他落進喉嚨。\n"
UNMARKED = "△巨鳥一口咬住洛年的手，把他甩上半空，他落進喉嚨。\n"


def _g14(warns):
    return [w for w in warns if w.startswith("G14")]


# ---------------------------------------------------------------- 主要動作數
class CountActions(unittest.TestCase):
    def test_swallow_beat_is_three_actions(self):
        self.assertEqual(am.count_actions("巨鳥一口咬住洛年的手，把他甩上半空，張嘴讓他落進喉嚨。"), 3)
        self.assertEqual(am.count_actions("咬手、甩上半空、落進喉嚨"), 3)

    def test_single_action_and_non_actions(self):
        self.assertEqual(am.count_actions("【動作】巨鳥一口咬住洛年的手。"), 1)  # 同子句多字只算一個
        self.assertEqual(am.count_actions("他打算去「飛鳥旅社」看看，心裡判斷不斷。"), 0)  # 引號、打算、判斷不算
        self.assertEqual(am.count_actions("話音未落，他點了點頭"), 0)

    def test_names_ignored(self):
        self.assertEqual(am.count_actions("張飛看著窗外", ignore_names=["張飛"]), 0)
        self.assertEqual(am.count_actions("張飛看著窗外"), 1)

    def test_mark_seconds(self):
        self.assertEqual(am.mark_seconds("【動作】咬"), [2.0])
        self.assertEqual(am.mark_seconds("【動作3.5】爆"), [3.5])
        self.assertEqual(am.mark_seconds("【動作0.5s】落"), [h3_spec.MIN_SHOT_SEC])
        parts = am.split_marked_line("【動作2.5】咬【動作】甩")
        self.assertEqual([p["seconds"] for p in parts], [2.5, 2.0])


# ---------------------------------------------------------------- 1. adapt_gate G14
class AdaptGateG14(unittest.TestCase):
    def run_gate(self, body, source=SOURCE):
        return adapt_gate.run_gate(HEAD + body + TAIL, novel_text=source, male_leads=["洛年"])

    def test_crammed_mark_warns_split(self):
        res = self.run_gate(CRAMMED)
        g = _g14(res["warns"])
        self.assertTrue(any(w.startswith("G14a") and "3 個主要動作" in w for w in g), g)

    def test_missing_mark_warns_with_source(self):
        res = self.run_gate("△巨鳥俯衝。\n")
        g = _g14(res["warns"])
        self.assertTrue(any(w.startswith("G14b") and "0 行【動作】" in w for w in g), g)

    def test_split_three_marks_passes(self):
        self.assertEqual(_g14(self.run_gate(SPLIT3)["warns"]), [])

    def test_no_source_no_g14b(self):
        res = adapt_gate.run_gate(HEAD + "△巨鳥俯衝。\n" + TAIL, quotes=["那是什麼？", "快跑！", "洛年！"])
        self.assertEqual([w for w in res["warns"] if w.startswith("G14b")], [])

    def test_quiet_source_no_warning(self):
        quiet = SOURCE.replace("話音未落，巨鳥俯衝而下，一口咬住洛年的手，把他甩上半空，張開大嘴，洛年就這麼落進了牠的喉嚨。",
                               "兩人沉默地看著天空。")
        self.assertEqual(_g14(self.run_gate("△兩人看著天空。\n", source=quiet)["warns"]), [])

    def test_storyboard_estimate_counts_split_marks(self):
        res = self.run_gate(SPLIT3)
        self.assertEqual(res["stats"]["storyboard_action_shots"], 3)


# ---------------------------------------------------------------- 2. 骨架
def _handoff(script_text):
    parsed = parse_and_validate_script(script_text)
    sc = parsed["scenes"][0]
    scene = sync_script.create_handoff_scene_from_script(sc, "t", "EP01", "EP01-S01", {})
    return {"project_id": "t", "rights_status": "owned_original", "adaptation_mode": "balanced",
            "genre_mode": "wuxia_action", "aspect_ratio": "9:16", "target_medium": "motion_comic",
            "episodes": [{"episode_id": "EP01", "title": "t", "episode_goal": "t", "act_out_type": "visual_spectacle",
                          "scenes": [scene]}]}


def _all_shots(results):
    return [sh for _, seg in results for sh in seg["shots"]]


class Skeleton(unittest.TestCase):
    def test_sequence_written_only_when_marked(self):
        h = _handoff(HEAD + SPLIT3 + TAIL)
        seq = h["episodes"][0]["scenes"][0]["script_sequence"]
        self.assertEqual([x["kind"] for x in seq], ["action", "dialogue", "dialogue", "action", "action", "action", "dialogue"])
        self.assertNotIn("script_sequence", _handoff(HEAD + UNMARKED + TAIL)["episodes"][0]["scenes"][0])

    def test_three_marks_three_shots_in_script_order(self):
        res = hts.convert_handoff(_handoff(HEAD + SPLIT3 + TAIL), None)
        shots = _all_shots(res)
        acts = [s for s in shots if am.is_action_shot(s)]
        self.assertEqual([s["duration"] for s in acts], [2.3, 2.3, 2.4])  # 三鏡 7.0 s，鏡長＝標記秒數
        self.assertTrue(all(len(am.ACTION_MARK_RE.findall(s["action_mark"]["text"])) == 1 for s in acts))
        kinds = ["A" if am.is_action_shot(s) else ("D" if s["dialogue_and_audio"]["has_dialogue"] else "B") for s in shots]
        self.assertEqual(kinds, ["B", "D", "D", "A", "A", "A", "D"])  # 依劇本先後，不是全部擠到台詞前
        for _, seg in res:  # 每段 ≤10 s
            self.assertLessEqual(seg["metadata"]["target_duration_sec"], hts.DEFAULT_MAX_SEGMENT_SEC + 1e-6)

    def test_action_shot_not_truncated_to_fit_segment(self):
        # 動作鏡合計超過一段上限：另開段，不截短
        script = HEAD + "△【動作4】咬。\n△【動作4】甩。\n△【動作4】落喉。\n" + TAIL
        res = hts.convert_handoff(_handoff(script), None)
        acts = [s for s in _all_shots(res) if am.is_action_shot(s)]
        self.assertEqual([s["duration"] for s in acts], [4.0, 4.0, 4.0])
        self.assertGreaterEqual(len(res), 3)

    def test_fit_does_not_compress_action_shots(self):
        res = hts.convert_handoff(_handoff(HEAD + SPLIT3 + TAIL), None)
        hts.fit_total_duration(res, 9.0)
        acts = [s for s in _all_shots(res) if am.is_action_shot(s)]
        self.assertEqual([s["duration"] for s in acts], [2.3, 2.3, 2.4])

    def test_unmarked_scene_unchanged(self):
        h = _handoff(HEAD + UNMARKED + TAIL)
        scene = h["episodes"][0]["scenes"][0]
        items = hts.build_items(scene)
        self.assertEqual(items[:1], hts.merge_beats(scene["action_beats"]))  # 舊行為：動作拍合併、排在台詞前
        self.assertFalse(any(am.is_action_shot(s) for s in _all_shots(hts.convert_handoff(h, None))))

    def test_missing_sequence_falls_back_to_actions_first(self):
        h = _handoff(HEAD + SPLIT3 + TAIL)
        h["episodes"][0]["scenes"][0].pop("script_sequence")
        items = hts.build_items(h["episodes"][0]["scenes"][0])
        self.assertEqual([i["kind"] for i in items][:4], ["beat", "action_mark", "action_mark", "action_mark"])


# ---------------------------------------------------------------- 3. validate D5／D6
def _shot(sid, start, end, line=None, action=None, beat=None):
    d = {"has_dialogue": bool(line), "line_verbatim": line, "speaker": "C-A" if line else None}
    s = {"shot_id": sid, "start_time": start, "end_time": end, "duration": round(end - start, 4),
         "character_ids": ["C-A"], "camera_optics": {"shot_size": "MS"}, "dialogue_and_audio": d}
    if action is not None:
        s["source_action"] = True
        s["action_mark"] = {"text": action, "seconds": am.required_seconds({"action_mark": {"text": action}})}
    if beat:
        s["shot_intent"] = {"story_beat": beat}
    return s


def _seg(seg_id, *shots):
    return {"segment_id": seg_id, "scene_id": "EP01-S01",
            "metadata": {"lighting_lock_line": "x", "aspect_ratio": "16:9", "target_duration_sec": shots[-1]["end_time"]},
            "shots": list(shots)}


def _d(res, code):
    return [e for e in res if e.startswith(f"[{code}")]


SPLIT_SEG = _seg("EP01-S01-b",
                 _shot("b1", 0.0, 2.3, action="【動作2.3】巨鳥俯衝，一口咬住洛年的手。"),
                 _shot("b2", 2.3, 4.6, action="【動作2.3】巨鳥把洛年甩上半空。"),
                 _shot("b3", 4.6, 7.0, action="【動作2.4】洛年落進巨鳥的喉嚨。"))
CRAMMED_SEG = _seg("EP01-S01-b",
                   _shot("b1", 0.0, 2.2, action="【動作2.2】巨鳥一口咬住洛年的手，把他甩上半空，他落進喉嚨。"))


class ValidateD5D6(unittest.TestCase):
    def handoff(self, body):
        return _handoff(HEAD + body + TAIL)

    def test_split_three_shots_pass(self):
        res = vs.validate_storyboard_data(copy.deepcopy(SPLIT_SEG))
        self.assertEqual(_d(res["errors"], "D"), [])
        self.assertEqual(_d(res["warnings"], "D6"), [])
        group = vs.check_dialogue_groups([copy.deepcopy(SPLIT_SEG)], self.handoff(SPLIT3), "EP01-S01")
        self.assertEqual(_d(group["EP01-S01"]["errors"], "D5"), [])

    def test_crammed_single_shot_fails(self):
        res = vs.validate_storyboard_data(copy.deepcopy(CRAMMED_SEG))
        self.assertTrue(_d(res["errors"], "D6"), res["errors"])  # 2.2 s < 1.5×3
        group = vs.check_dialogue_groups([copy.deepcopy(CRAMMED_SEG)], self.handoff(SPLIT3), "EP01-S01")
        self.assertTrue(_d(group["EP01-S01"]["errors"], "D5"), group)  # 劇本 3 個標記、分鏡 1 個

    def test_d6_warn_band(self):
        seg = _seg("x", _shot("x1", 0.0, 5.0, action="【動作5】巨鳥一口咬住洛年的手，把他甩上半空，他落進喉嚨。"))
        res = vs.validate_storyboard_data(seg)  # 4.5 ≤ 5.0 < 6.0
        self.assertEqual(_d(res["errors"], "D6"), [])
        self.assertTrue(_d(res["warnings"], "D6"))
        seg = _seg("x", _shot("x1", 0.0, 6.0, action="【動作6】巨鳥一口咬住洛年的手，把他甩上半空，他落進喉嚨。"))
        self.assertEqual(_d(vs.validate_storyboard_data(seg)["warnings"], "D6"), [])

    def test_merged_marks_and_truncation(self):
        seg = _seg("x", _shot("x1", 0.0, 4.0, action="【動作】咬。【動作】甩。"))
        self.assertTrue([e for e in vs.validate_storyboard_data(seg)["errors"] if "被合併" in e])
        seg = _seg("x", _shot("x1", 0.0, 1.5, action="【動作2.5】巨鳥咬住洛年的手。"))
        self.assertTrue([e for e in vs.validate_storyboard_data(seg)["errors"] if "被截短" in e])

    def test_mark_lost_into_dialogue_shot(self):
        seg = copy.deepcopy(SPLIT_SEG)
        seg["shots"][2]["dialogue_and_audio"].update(has_dialogue=True, line_verbatim="洛年！", speaker="C-B")
        group = vs.check_dialogue_groups([seg], self.handoff(SPLIT3), "EP01-S01")
        errs = _d(group["EP01-S01"]["errors"], "D5")
        self.assertTrue(errs and "b3" in errs[0], errs)

    def test_extra_source_action_without_mark_fails_count(self):
        seg = copy.deepcopy(SPLIT_SEG)
        seg["shots"].append(dict(_shot("b4", 7.0, 9.0), source_action=True))
        seg["metadata"]["target_duration_sec"] = 9.0
        group = vs.check_dialogue_groups([seg], self.handoff(SPLIT3), "EP01-S01")
        self.assertTrue(_d(group["EP01-S01"]["errors"], "D5"))

    def test_unmarked_legacy_shot_only_warns(self):
        seg = _seg("x", _shot("x1", 0.0, 2.2, beat="巨鳥一口咬住洛年的手，把他甩上半空，他落進喉嚨"))
        res = vs.validate_storyboard_data(seg)
        self.assertEqual(_d(res["errors"], "D6"), [])
        self.assertTrue(_d(res["warnings"], "D6"))
        group = vs.check_dialogue_groups([seg], self.handoff(UNMARKED), "x")
        self.assertEqual(_d(group["x"]["errors"], "D5"), [])


# ---------------------------------------------------------------- 4. D1–D4／pacing_gate 不計動作鏡
TC1 = [{"text": "那是什麼東西在天上？", "start": 0.2, "end": 2.2}]
TC2 = [{"text": "洛年你給我撐住啊！", "start": 9.6, "end": 11.4}]


def _mixed(action=True):
    a1 = _shot("m1", 0.0, 2.4, line="那是什麼東西在天上？")
    a1["dialogue_and_audio"]["line_timecodes"] = TC1
    acts = [_shot("m2", 2.4, 4.7, action="【動作2.3】巨鳥咬住洛年的手。"),
            _shot("m3", 4.7, 7.0, action="【動作2.3】巨鳥把洛年甩上半空。"),
            _shot("m4", 7.0, 9.4, action="【動作2.4】洛年落進巨鳥的喉嚨。")]
    if not action:
        for s in acts:
            s.pop("source_action")
            s.pop("action_mark")
    a5 = _shot("m5", 9.4, 11.6, line="洛年你給我撐住啊！")
    a5["dialogue_and_audio"]["line_timecodes"] = TC2
    return _seg("m", a1, *acts, a5)


class DialogueGatesExcludeActionShots(unittest.TestCase):
    def test_d1_to_d4_skip_action_shots(self):
        errs, _ = check_dialogue_density(_mixed())
        self.assertEqual([e for e in errs if e.startswith(("[D1", "[D2", "[D3", "[D4"))], [])
        errs, _ = check_dialogue_density(_mixed(action=False))  # 沒標：句間 7.5 s、密度都 FAIL（舊行為）
        self.assertTrue([e for e in errs if e.startswith("[D3")])

    def test_action_only_segment_skips_d1(self):
        errs, _ = check_dialogue_density(copy.deepcopy(SPLIT_SEG))
        self.assertEqual([e for e in errs if e.startswith("[D1")], [])
        plain = copy.deepcopy(SPLIT_SEG)
        for s in plain["shots"]:
            s.pop("source_action")
        errs, _ = check_dialogue_density(plain)
        self.assertTrue([e for e in errs if e.startswith("[D1")])  # 舊行為：全段無台詞 7 s > 5 s

    def test_strip_layer2_shifts_windows(self):
        out = am.strip_layer2(_mixed())
        self.assertEqual([s["shot_id"] for s in out["shots"]], ["m1", "m5"])
        self.assertAlmostEqual(out["shots"][1]["start_time"], 2.4)
        self.assertAlmostEqual(out["shots"][1]["dialogue_and_audio"]["line_timecodes"][0]["start"], 2.6)
        self.assertAlmostEqual(out["metadata"]["target_duration_sec"], 4.6)


def _gate(seg):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"segments": [seg]}, f, ensure_ascii=False)
    return subprocess.run([sys.executable, str(GATE), f.name], capture_output=True, text=True).stdout


class PacingGateExcludesActionShots(unittest.TestCase):
    def seg(self, flag=True):
        acts = [{"start": a, "end": b, "has_dialogue": False, "source_action": flag}
                for a, b in ((2.0, 4.3), (4.3, 6.6), (6.6, 9.0))]
        return {"id": "s", "duration": 11.0, "kind": "dialogue", "prompt": "real-time speed",
                "lines": [{"text": "一二三四五六", "start": 0.2, "end": 1.7},
                          {"text": "一二三四五六", "start": 9.2, "end": 10.7}],
                "shots": [{"start": 0.0, "end": 2.0, "has_dialogue": True}, *acts,
                          {"start": 9.0, "end": 11.0, "has_dialogue": True}]}

    def test_gap_density_voiced_ratio_exclude_actions(self):
        out = _gate(self.seg())
        self.assertNotIn("句間空隙", out)
        self.assertNotIn("有人聲鏡", out)
        self.assertNotIn("對話密度", out)
        self.assertIn("0 FAIL", out)

    def test_unflagged_keeps_old_behaviour(self):
        out = _gate(self.seg(flag=False))
        self.assertIn("句間空隙", out)  # 7.5 s 空隙 FAIL（舊行為）
        self.assertIn("有人聲鏡 2/5", out)


# ---------------------------------------------------------------- 5. 編譯器不截短末尾動作鏡
class CompilerKeepsActionTail(unittest.TestCase):
    setUp = base.H3CompilerRegressionTests.setUp
    segment = base.H3CompilerRegressionTests.segment
    shot = staticmethod(base.H3CompilerRegressionTests.shot)
    compile = base.H3CompilerRegressionTests.compile

    def _data(self, flag):
        data = self.segment()
        talk = self.shot("S1", 0.0, 3.0, "Mira looks up.", line="Stay right here.")
        talk["dialogue_and_audio"]["speech_window"] = {"start": 0.3, "end": 2.7}
        act = self.shot("S2", 3.0, 8.1, "A huge bird snatches Mira's hand.")
        if flag:
            act["source_action"] = True
            act["action_mark"] = {"text": "【動作5.1】巨鳥咬住手。", "seconds": 5.1}
        data["shots"] = [talk, act]
        data["metadata"]["target_duration_sec"] = 8.1
        return data

    def test_action_tail_not_floored(self):
        plain = self.compile(self._data(False))["metadata"]
        self.assertEqual(plain["rounding_mode"], "floor")  # 舊行為：tail-fit 往下取 8.0 s（末鏡被截 0.1 s）
        meta = self.compile(self._data(True))["metadata"]
        self.assertEqual(meta["rounding_mode"], "ceil")
        frames = h3_spec.frames_for(8.1, rounding="ceil")
        self.assertEqual((frames - h3_spec.FRAME_QUANTUM_OFFSET) % h3_spec.FRAME_QUANTUM_STEP, 0)
        self.assertGreaterEqual(meta["effective_duration_sec"], 8.1)


if __name__ == "__main__":
    unittest.main()
