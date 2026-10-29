"""鏡間銜接與佔位延續（D15–D21，transition_lint.py）＋ seam_in／entry_state／cut_in／逐鏡 positions 欄位。

每條 lint 都有正例（該報）與反例（不該報）；舊專案沒有新欄位時零新警告；
compile 只在 seam_in=cont 時把 entry_state 寫成第 1 鏡開頭交接塊（ref2va 與 remix 兩個 backend）。
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import compile_layer2_to_h3 as compiler  # noqa: E402
import handoff_to_skeleton as skeleton  # noqa: E402
import layer2_to_table  # noqa: E402
import staging_lint  # noqa: E402
import transition_lint as tl  # noqa: E402

from tests import test_h3_compiler as _h3  # noqa: E402


def shot(sid, size="MS", chars=("C1",), az=None, cut=None, motivation="", pos=None, dlg=None, start=0.0, end=3.0,
         blocking=""):
    s = {"shot_id": sid, "start_time": start, "end_time": end, "duration": end - start,
         "character_ids": list(chars), "camera_optics": {"shot_size": size},
         "spatial_blocking": {"blocking_desc": blocking},
         "dialogue_and_audio": dlg or {"has_dialogue": False}}
    if az is not None:
        s["camera_optics"]["azimuth_deg"] = az
    if cut:
        s["cut_in"] = {"type": cut, "motivation": motivation}
    if pos is not None:
        s["positions"] = pos
    return s


def seg(sid, shots, scene="S01", **extra):
    total = shots[-1]["end_time"] if shots else 0
    data = {"segment_id": sid, "scene_id": scene, "metadata": {"target_duration_sec": total}, "shots": shots}
    data.update(extra)
    return data


def codes(findings):
    return sorted(f["code"] for f in findings)


def chain(n, sizes, chars_list=None, **kw):
    """n 鏡、每鏡 3 秒；第 2 鏡起 cut_in=hard（讓段落啟用銜接規則）。"""
    out = []
    for i in range(n):
        chars = chars_list[i] if chars_list else ("C1",)
        out.append(shot(f"SH{i + 1}", sizes[i], chars, cut="hard" if i else None, start=3.0 * i, end=3.0 * (i + 1),
                        **kw))
    return out


class D15CutSeamTests(unittest.TestCase):
    def prev(self, size="MS", chars=("C1",), az=None):
        return seg("S01-a", [shot("a1", size, chars, az=az)])

    def test_same_subject_one_level_unknown_angle_warns(self):
        found = tl.lint_segment(seg("S01-b", [shot("b1", "MCU")], seam_in="cut"), self.prev())
        self.assertEqual(codes(found), ["D15"])
        self.assertIn("azimuth_deg 未填", found[0]["message"])

    def test_any_of_three_passes(self):
        self.assertEqual(tl.lint_segment(seg("S01-b", [shot("b1", "MCU", ("C2",))], seam_in="cut"), self.prev()), [])
        self.assertEqual(tl.lint_segment(seg("S01-b", [shot("b1", "CU")], seam_in="cut"), self.prev()), [])
        found = tl.lint_segment(seg("S01-b", [shot("b1", "MS", az=100)], seam_in="cut"), self.prev(az=0))
        self.assertEqual(found, [])
        found = tl.lint_segment(seg("S01-b", [shot("b1", "MS", az=60)], seam_in="cut"), self.prev(az=0))
        self.assertEqual(codes(found), ["D15"])

    def test_angle_wraps_around_360(self):
        found = tl.lint_segment(seg("S01-b", [shot("b1", "MS", az=10)], seam_in="cut"), self.prev(az=260))
        self.assertEqual(found, [])  # 差 110°

    def test_no_seam_in_skips(self):
        self.assertEqual(tl.lint_segment(seg("S01-b", [shot("b1", "MS")]), self.prev()), [])


class D16D17WithinTests(unittest.TestCase):
    def test_d16_same_subject_small_change(self):
        found = tl.lint_segment(seg("S", chain(2, ["MS", "MCU"])))
        self.assertEqual(codes(found), ["D16"])

    def test_d16_passes_on_two_levels_angle_or_ots(self):
        self.assertEqual(tl.lint_segment(seg("S", chain(2, ["MS", "CU"]))), [])
        a, b = chain(2, ["MS", "MS"])
        a["camera_optics"]["azimuth_deg"], b["camera_optics"]["azimuth_deg"] = 0, 35
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])
        self.assertEqual(codes(tl.lint_segment(seg("S", chain(2, ["MS", "OTS_MS"])))), [])
        self.assertEqual(tl.lint_segment(seg("S", chain(2, ["MS", "MS"], [("C1",), ("C2",)]))), [])

    def test_d17_three_same_size(self):
        found = tl.lint_segment(seg("S", chain(3, ["MS", "MS", "MS"], [("C1",), ("C2",), ("C2", "C1")])))
        self.assertIn("D17", codes(found))

    def test_d17_alternating_shot_reverse_is_exempt_and_varied_passes(self):
        alt = chain(3, ["OTS_CU"] * 3, [("C1",), ("C2",), ("C1",)])
        self.assertNotIn("D17", codes(tl.lint_segment(seg("S", alt))))
        varied = chain(3, ["MS", "CU", "MS"], [("C1",), ("C2",), ("C3",)])
        self.assertEqual(tl.lint_segment(seg("S", varied)), [])


class D18ContSeamTests(unittest.TestCase):
    def pair(self, entry, exit_state, prev_dlg=None, first_size="MS"):
        prev = seg("S01-a", [shot("a1", "MS", dlg=prev_dlg, start=0, end=8)], exit_state=exit_state)
        nxt = seg("S01-b", [shot("b1", first_size, start=0, end=8)], seam_in="cont", entry_state=entry)
        return tl.lint_segment(nxt, prev)

    STATE = {"C1": {"position": "east end of the table", "facing": "frame right", "holding": "letter in left hand"}}

    def test_matching_cont_passes(self):
        self.assertEqual(self.pair(copy.deepcopy(self.STATE), copy.deepcopy(self.STATE)), [])

    def test_mismatch_missing_and_vague(self):
        entry = {"C1": {"position": "west end of the table", "facing": "frame right"}}
        found = self.pair(entry, self.STATE)
        self.assertEqual(codes(found), ["D18"])
        self.assertIn("west end", found[0]["message"])
        self.assertIn("holding 入口沒寫", found[0]["message"])
        self.assertIn("D18", codes(self.pair({"position": "同上"}, self.STATE)))
        self.assertTrue(any("沒有 entry_state" in f["message"] for f in self.pair({}, self.STATE)))
        self.assertTrue(any("沒有 exit_state" in f["message"] for f in self.pair(self.STATE, {})))

    def test_last_second_dialogue_and_size_change(self):
        dlg = {"has_dialogue": True, "speaker": "C1", "line_verbatim": "走",
               "speech_window": {"start": 6.0, "end": 7.8, "unit": "segment_seconds"}}
        self.assertTrue(any("最後 1 秒有台詞" in f["message"] for f in self.pair(self.STATE, self.STATE, prev_dlg=dlg)))
        early = dict(dlg, speech_window={"start": 1.0, "end": 3.0})
        self.assertEqual(self.pair(self.STATE, self.STATE, prev_dlg=early), [])
        self.assertTrue(any("同景別起手" in f["message"] for f in self.pair(self.STATE, self.STATE, first_size="CU")))


class D19ScenetransTests(unittest.TestCase):
    def two(self, bridge="L_CUT", text=""):
        dlg = {"has_dialogue": True, "speaker": "C1", "line_verbatim": "我不會回去" + text, "audio_bridge": bridge}
        a = shot("SH1", "MS", ("C1",), dlg=dlg)
        b = shot("SH2", "CU", ("C2",), cut="reaction", start=3, end=6)
        return seg("S", [a, b])

    def test_l_cut_without_scenetrans_warns(self):
        self.assertEqual(codes(tl.lint_segment(self.two())), ["D19"])

    def test_scenetrans_written_or_no_bridge_passes(self):
        self.assertEqual(tl.lint_segment(self.two(text=" <scenetrans>")), [])
        self.assertEqual(tl.lint_segment(self.two(bridge="NONE")), [])

    def test_speech_window_crossing_cut_warns(self):
        data = self.two(bridge="NONE")
        data["shots"][0]["dialogue_and_audio"]["speech_window"] = {"start": 1.0, "end": 4.2}
        self.assertEqual(codes(tl.lint_segment(data)), ["D19"])


class D20D21PositionTests(unittest.TestCase):
    @staticmethod
    def pos(order, anchors=True, world=None, xs=None):
        out = []
        for i, cid in enumerate(order, 1):
            p = {"id": cid, "order_lr": i}
            if anchors:
                p["background_anchor"] = f"{cid} 身後的窗"
            if world:
                p["world"] = world[cid]
            if xs:
                p["screen_x"] = xs[cid]
            out.append(p)
        return out

    def test_d20_swap_without_blocking_warns_and_with_move_passes(self):
        a = shot("SH1", "MS", ("C1", "C2"), pos=self.pos(["C1", "C2"]))
        b = shot("SH2", "LS", ("C1", "C2"), cut="hard", pos=self.pos(["C2", "C1"]), start=3, end=6)
        self.assertEqual(codes(tl.lint_segment(seg("S", [a, b]))), ["D20"])
        b["cut_in"]["motivation"] = "C2 繞到桌子另一側，越軸換位"
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])

    def test_d20_world_change_and_screen_x_drift(self):
        a = shot("SH1", "MS", ("C1", "C2"), pos=self.pos(["C1", "C2"], world={"C1": "桌東", "C2": "門口"},
                                                         xs={"C1": 0.3, "C2": 0.7}))
        b = shot("SH2", "LS", ("C1", "C2"), cut="hard", start=3, end=6,
                 pos=self.pos(["C1", "C2"], world={"C1": "窗邊", "C2": "門口"}, xs={"C1": 0.3, "C2": 0.95}))
        found = tl.lint_segment(seg("S", [a, b]))
        msgs = " ".join(f["message"] for f in found)
        self.assertEqual(codes(found), ["D20"])  # 硬切的畫面位置漂移不再查（第二輪：只在動作匹配時查）
        self.assertIn("世界位置改變", msgs)
        b["cut_in"]["type"] = "match_action"
        b["camera_optics"]["shot_size"] = "MCU"  # 和 MS 差 1 級
        found = tl.lint_segment(seg("S", [a, b]))
        self.assertEqual(codes(found), ["D20", "D20"])
        self.assertIn("15% 畫寬", " ".join(f["message"] for f in found))
        b["positions"] = self.pos(["C1", "C2"], world={"C1": "桌東", "C2": "門口"}, xs={"C1": 0.35, "C2": 0.75})
        self.assertEqual(tl.lint_segment(seg("S", [a, b])), [])

    def test_d21_missing_background_anchor(self):
        a = shot("SH1", "MS", ("C1", "C2"), pos=self.pos(["C1", "C2"], anchors=False))
        self.assertEqual(codes(tl.lint_segment(seg("S", [a]))), ["D21"])
        a["positions"] = self.pos(["C1", "C2"])
        self.assertEqual(tl.lint_segment(seg("S", [a])), [])

    def test_d21_segment_positions_only_when_planned(self):
        legacy = seg("S", [shot("SH1", "MS", ("C1", "C2"))], positions=[{"id": "C1", "order_lr": 1},
                                                                         {"id": "C2", "order_lr": 2}])
        self.assertEqual(tl.lint_segment(legacy), [])  # REMIX 舊專案的段層 positions 不報
        legacy["seam_in"] = "cut"
        self.assertEqual(codes(tl.lint_segment(legacy)), ["D21"])


class BackwardCompatTests(unittest.TestCase):
    def test_legacy_segments_produce_no_new_findings(self):
        golden = json.loads((ROOT / "tests" / "golden" / "ep01" / "segments-ep01.json").read_text(encoding="utf-8"))
        rows = tl.lint_sequence(golden["segments"])
        self.assertEqual([f for r in rows for f in r["findings"]], [])
        legacy = seg("S", [shot("SH1", "MS"), shot("SH2", "MS", start=3, end=6), shot("SH3", "MS", start=6, end=9)])
        self.assertFalse(tl.transition_planned(legacy))
        self.assertEqual(tl.lint_segment(legacy), [])

    def test_skeleton_fields_are_empty_and_inert(self):
        handoff = {"project_id": "T", "aspect_ratio": "9:16"}
        scene = {"scene_id": "EP01-S01", "setting": {"location": "教室"}, "characters": ["沈"], "props": [],
                 "dialogue": [], "continuity_final": {}}
        chunk = [{"kind": "beat", "text": "沈推門", "duration": 2.5}, {"kind": "beat", "text": "沈回頭", "duration": 2.5}]
        layer2 = skeleton.build_layer2(handoff, scene, "EP01-S01-a", chunk, {"mode": "INDEPENDENT_REF2VA"}, {},
                                       {"沈": "C-shen"})
        self.assertIsNone(layer2["seam_in"])
        self.assertEqual((layer2["entry_state"], layer2["exit_state"]), ({}, {}))
        self.assertTrue(all(s["cut_in"] == {"type": None, "motivation": ""} and s["positions"] == []
                            for s in layer2["shots"]))
        self.assertEqual(skeleton.check_layer2(layer2), [])
        self.assertFalse(tl.transition_planned(layer2))

    def test_schema_accepts_filled_fields_and_rejects_bad_enum(self):
        data = _h3.H3CompilerRegressionTests.segment(_h3.H3CompilerRegressionTests())
        data["seam_in"] = "cont"
        data["entry_state"] = {"position": "east of the table"}
        data["shots"][1]["cut_in"] = {"type": "match_action", "motivation": "手伸向信"}
        data["shots"][1]["camera_optics"]["azimuth_deg"] = 45
        data["shots"][1]["positions"] = [{"id": "C-MIRA", "order_lr": 1, "background_anchor": "west window",
                                          "screen_x": 0.6}]
        self.assertEqual([e for e in skeleton.check_layer2(data) if "seam_in" in e or "cut_in" in e
                          or "positions" in e or "azimuth" in e], [])
        data["seam_in"] = "dissolve"
        data["shots"][1]["cut_in"]["type"] = "wipe"
        errors = " ".join(skeleton.check_layer2(data))
        self.assertIn("seam_in", errors)
        self.assertIn("cut_in.type", errors)


class StagingIntegrationTests(unittest.TestCase):
    def segs(self):
        a = seg("S01-a", [shot("a1", "MS")])
        b = seg("S01-b", [shot("b1", "MCU")], seam_in="cut")
        return [a, b]

    def test_staging_lint_segments_include_transitions_and_respect_waivers(self):
        rows = staging_lint.lint_segments(self.segs(), lambda s: "ref2va")
        self.assertIn("D15", [f["code"] for f in rows[1]["findings"]])
        self.assertTrue(all(r["ok"] for r in rows))  # 只警告
        rows = staging_lint.lint_segments(self.segs(), lambda s: "ref2va", strict=True)
        self.assertTrue(all(r["ok"] for r in rows))  # strict 也不升級
        segs = self.segs()
        segs[1]["metadata"]["staging_waivers"] = [{"code": "D15", "reason": "刻意跳切", "quote": "這裡就是要跳切"}]
        rows = staging_lint.lint_segments(segs, lambda s: "ref2va")
        self.assertNotIn("D15", [f["code"] for f in rows[1]["findings"]])
        segs[1]["metadata"]["staging_waivers"] = [{"code": "D15", "reason": "沒原話"}]
        rows = staging_lint.lint_segments(segs, lambda s: "ref2va")
        self.assertIn("D15", [f["code"] for f in rows[1]["findings"]])

    def test_cross_scene_seam_is_not_compared(self):
        a, b = self.segs()
        b["scene_id"] = "S02"
        rows = staging_lint.lint_segments([a, b], lambda s: "ref2va")
        self.assertNotIn("D15", [f["code"] for f in rows[1]["findings"]])


class TableDisplayTests(unittest.TestCase):
    def test_columns_only_when_fields_present(self):
        data = _h3.H3CompilerRegressionTests.segment(_h3.H3CompilerRegressionTests())
        plain = layer2_to_table.render_md(copy.deepcopy(data))
        self.assertNotIn("接點／站位", plain)
        self.assertNotIn("段縫", plain)
        data["seam_in"] = "cut"
        data["exit_state"] = {"position": "east of the table"}
        data["shots"][1]["cut_in"] = {"type": "eyeline", "motivation": "她看向門"}
        data["shots"][1]["positions"] = [{"id": "C-MIRA", "order_lr": 1, "background_anchor": "west window"}]
        md = layer2_to_table.render_md(data)
        self.assertIn("接點／站位", md)
        self.assertIn("視線接：她看向門", md)
        self.assertIn("背後：west window", md)
        self.assertIn("段縫：CUT", md)
        self.assertIn("出口狀態", md)


class _Base(_h3.H3CompilerRegressionTests):
    """借用既有編譯器 fixture；不重跑父類別的測試。"""


for _name in [n for n in dir(_h3.H3CompilerRegressionTests) if n.startswith("test_")]:
    setattr(_Base, _name, None)


class CompileHandoffBlockTests(_Base):
    def shot1(self, compiled):
        return compiled["h3_prompt"].split("[Shot 1]")[1].split("[Shot 2]")[0]

    def test_cont_writes_handoff_block_and_replaces_carry_sentence(self):
        data = self.segment()
        data["seam_in"] = "cont"
        data["entry_state"] = {"C-MIRA": {"position": "east end of the table", "facing": "frame left",
                                          "holding": "the folded map in her right hand"}}
        compiled = compiler.compile_segment_h3(
            data, registry=self.registry, auto_lora=False,
            previous_end_state={"planned_final_state_en": {"Mira": "sits slumped against the door"}})
        head = self.shot1(compiled)
        self.assertIn("Opening state at 0.0 s:", head)
        self.assertIn("position east end of the table, facing frame left, holding the folded map", head)
        self.assertNotIn("Starting state carried over", compiled["h3_prompt"])
        self.assertNotRegex(compiled["h3_prompt"], r"previous segment|承接上一段|同上")
        self.assertEqual(compiled["seam_in"], "cont")
        self.assertEqual(compiled["h3_prompt"].count("Opening state"), 1)

    def test_cut_or_missing_seam_keeps_prompt_identical(self):
        base = self.compile()
        data = self.segment()
        data["entry_state"] = {"position": "east end of the table"}
        data["seam_in"] = "cut"
        cut = self.compile(data)
        self.assertNotIn("Opening state", cut["h3_prompt"])
        self.assertEqual(cut["h3_prompt"], base["h3_prompt"])
        self.assertNotIn("seam_in", base)

    def test_chinese_or_vague_entry_state_is_noted_not_written(self):
        data = self.segment()
        data["seam_in"] = "cont"
        data["entry_state"] = {"position": "桌子東側"}
        compiled = self.compile(data)
        self.assertNotIn("Opening state", compiled["h3_prompt"])
        self.assertTrue(any("entry_state_en" in n for n in compiled["compile_notes"]))
        data["entry_state_en"] = {"position": "east end of the table"}
        self.assertIn("Opening state at 0.0 s: position east end of the table.", self.compile(data)["h3_prompt"])
        data["entry_state_en"] = {"position": "same as the previous segment"}
        self.assertNotIn("Opening state", self.compile(data)["h3_prompt"])

    def test_check_cli_reports_transition_warnings_without_failing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            first = self.five_part_segment()
            first["segment_id"] = "EP01-S01-a"
            first["exit_state"] = {"position": "east end of the table"}
            second = self.five_part_segment()
            second["segment_id"] = "EP01-S01-b"
            second["seam_in"] = "cont"
            second["entry_state_en"] = {"position": "west end of the table"}
            second["entry_state"] = {"position": "west end of the table"}
            for name, doc in (("a", first), ("b", second)):
                (root / f"layer2-EP01-S01-{name}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            out = root / "segments.json"
            argv = ["compile_layer2_to_h3.py", "--layer2", str(root / "layer2-EP01-S01-b.json"), "--skip-stage-gate",
                    "--project-root", str(root), "--output-segments", str(out), "--check", "--no-auto-lora"]
            buf = io.StringIO()
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                status = compiler.main()
            self.assertEqual(status, 0, buf.getvalue())
            self.assertIn("[D18: CONT 段縫不符]", buf.getvalue())
            self.assertIn("east end of the table", buf.getvalue())
            seg_out = json.loads(out.read_text(encoding="utf-8"))["segments"][0]
            self.assertIn("Opening state at 0.0 s: position west end of the table.", seg_out["h3_prompt"])


class RemixHandoffBlockTests(unittest.TestCase):
    def setUp(self):
        import test_remix_compile as rc
        self.rc = rc.RemixProject()
        self.rc.setUp()
        self.addCleanup(self.rc.doCleanups)
        self.rc.make()

    def test_remix_cont_block_keeps_style_anchor_first(self):
        data = json.loads(self.rc.layer2_path.read_text(encoding="utf-8"))
        base = self.rc.compile(copy.deepcopy(data))
        data["seam_in"] = "cont"
        data["entry_state"] = {"C-YE": {"position": "by the flower bed", "facing": "frame left"}}
        seg_out = self.rc.compile(data)
        prompt = seg_out["h3_prompt"]
        self.assertIn("Opening state at 0.0 s: Ye Weishan: position by the flower bed, facing frame left.", prompt)
        integrated = prompt.split("integrated_multimodal_description: ")[1]
        self.assertTrue(integrated.startswith(base["h3_prompt"].split("integrated_multimodal_description: ")[1][:80]))
        self.assertEqual(seg_out["seam_in"], "cont")


if __name__ == "__main__":
    unittest.main()
