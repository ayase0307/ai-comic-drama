# -*- coding: utf-8 -*-
"""噩盡島 EP01 重跑尾項：
  1. Codex 構圖單人中近景自動加英文臉朝向句（中文「朝圖片左邊緣」常被畫反）
  2. 階段 4／5 審核頁自動建議列出 W46＋W47＋W48（以前只列 W46）
  3. handoff_to_skeleton --force 重建時保留構圖綁定（shot_id 對應、sha256 相符才保留）
  4. 可選劇本標記【動作】只進分鏡後預估片長，不算台詞、不影響 G3
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "scripts" / "adapt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import codex_storyboard_panels as cp  # noqa: E402
import sketch_bindings  # noqa: E402
import handoff_to_skeleton as hts  # noqa: E402
import dialogue_budget as db  # noqa: E402
import adapt_gate  # noqa: E402


# ---------------------------------------------------------------- 1. 臉朝向英文句
class FaceDirectionSentence(unittest.TestCase):
    ASSETS = {"C-guide": {"name": "導遊"}, "C-hat": {"name": "草帽女子"}}

    def _shot(self, desc, size="MCU"):
        return {"shot_id": "E1-02-SH03", "camera_optics": {"shot_size": size},
                "spatial_blocking": {"blocking_desc": desc}}

    def _prompt(self, desc, subjects=("C-guide",), size="MCU"):
        return cp.build_panel_prompt(self._shot(desc, size), {}, list(subjects), self.ASSETS, [])

    def test_parse_direction(self):
        self.assertEqual(cp.face_direction("導遊胸口以上在畫面中偏右、面向圖片左側；背後是岩面"), "left")
        self.assertEqual(cp.face_direction("沈商山在畫面中偏左，從看海轉頭面向圖片右側（遮陽帽女子）"), "right")
        self.assertEqual(cp.face_direction("身體 3/4 轉向圖片右側往坡上看"), "right")
        self.assertEqual(cp.face_direction("抬頭看向圖片左側"), "left")
        self.assertEqual(cp.face_direction("臉朝畫右"), "right")
        self.assertEqual(cp.face_direction("導遊在畫面中偏右，身體前傾湊向圖片左側、一手半掩嘴邊"), "left")
        self.assertEqual(cp.face_direction("先對圖片右側的導遊略點頭致歉，再轉頭眺望圖片左側遠處"), "right")
        self.assertIsNone(cp.face_direction("被紅光從圖片左側照得通紅"))
        self.assertIsNone(cp.face_direction("導遊站在畫面中偏右，頭轉向巨石"))
        self.assertIsNone(cp.face_direction(""))

    def test_first_facing_wins(self):
        # 「面向右側…再望向左側遠處」：第一個朝向是臉的方向
        self.assertEqual(cp.face_direction("他面向圖片右側，抬起左手腕看錶，再望向圖片左側遠處的海灘"), "right")

    def test_single_person_close_gets_english_left(self):
        prompt = self._prompt("導遊胸口以上在畫面中偏右、面向圖片左側，雙手一攤")
        self.assertIn("face turned toward the LEFT edge of the image — nose pointing left ←", prompt)
        self.assertIn("do NOT draw the face turned toward the right side", prompt)

    def test_single_person_close_gets_english_right(self):
        prompt = self._prompt("沈商山胸口以上在畫面中偏左、面向圖片右側", subjects=("C-hat",), size="MS")
        self.assertIn("face turned toward the RIGHT edge of the image — nose pointing right →", prompt)

    def test_not_added_for_two_people_wide_or_no_direction(self):
        self.assertNotIn("Face direction (viewer's perspective)",
                         self._prompt("兩人面向圖片右側", subjects=("C-guide", "C-hat")))
        self.assertNotIn("Face direction (viewer's perspective)", self._prompt("導遊面向圖片左側", size="MLS"))
        self.assertNotIn("Face direction (viewer's perspective)", self._prompt("導遊頭轉向巨石"))

    def test_existing_viewer_lines_kept(self):
        prompt = self._prompt("導遊面向圖片左側")
        self.assertIn("viewer's left or right of the image", prompt)
        self.assertIn("nose points at the image's left edge", prompt)


# ---------------------------------------------------------------- 2. 審核頁列 W46／W47／W48
def _seg(sid, shots, scene="S-rock"):
    return {"segment_id": sid, "scene_id": scene, "asset_refs": {"scene_id": scene}, "shots": shots}


class ReviewPageListsAllStagingCodes(unittest.TestCase):
    def test_panel_names_each_code_present(self):
        import build_stage_review as bsr
        html_out = bsr.board_suggestion_panel([
            "E1-02: [W47: 建議加雙人引子] E1-02：…",
            "E1-05: [W48: 雙人引子格式不符] E1-05：…",
        ])
        self.assertIn("W47", html_out)
        self.assertIn("W48", html_out)
        self.assertIn("§7", html_out)
        self.assertNotIn("<b>W46", html_out)  # 沒有 W46 就不放 W46 說明

    def test_stage4_includes_lead_in_rows(self):
        import build_stage_review as bsr
        fake = [{"code": "W48", "level": "warning", "hit": True, "segment_id": "E1-05",
                 "message": "[W48: 雙人引子格式不符] E1-05：不在第 1 鏡"},
                {"code": "W47", "level": "suggestion", "hit": True, "segment_id": "E1-02",
                 "message": "[W47: 建議加雙人引子] E1-02：同場硬切"}]
        with tempfile.TemporaryDirectory() as td, \
                mock.patch("board_advisor.advise_layer2_files", return_value=[]), \
                mock.patch("staging_lint._lead_in_layer2", return_value=fake):
            rows = bsr.stage4_board_suggestions(Path(td), [])
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("[W48:" in r for r in rows))
        self.assertTrue(any("[W47:" in r for r in rows))

    def test_stage4_real_w48_from_layer2(self):
        import build_stage_review as bsr
        import dual_lead_in
        seg = _seg("E1-05", [
            {"shot_id": "SH01", "duration": 3.0, "character_ids": ["C-a"]},
            {"shot_id": "SH02", "duration": 2.0, "dual_lead_in": True, "character_ids": ["C-a", "C-b"]},
        ])
        if not dual_lead_in.check(seg):
            self.skipTest("dual_lead_in.check 對這個樣本不報問題")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "layer2").mkdir()
            f = root / "layer2" / "layer2-E1-05.json"
            f.write_text(json.dumps(seg, ensure_ascii=False), encoding="utf-8")
            rows = bsr.stage4_board_suggestions(root, [f])
        self.assertTrue(any("[W48:" in r for r in rows), rows)


# ---------------------------------------------------------------- 3. 重建保留構圖綁定
class KeepSketchBindingsOnRebuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "panels").mkdir()
        (self.root / "layer2").mkdir()
        self.png = self.root / "panels" / "E1-01-SH01.png"
        self.png.write_bytes(b"panel-1")
        self.sha = hashlib.sha256(b"panel-1").hexdigest()

    def _old(self, sha=None):
        return {"segment_id": "E1-01", "shots": [
            {"shot_id": "SH01", "sketch_file": "panels/E1-01-SH01.png", "sketch_sha256": sha or self.sha,
             "sketch_status": "generated", "sketch_prompt": "p", "sketch_generation": {"backend": "codex"},
             "sketch_qc": {"verdict": "pass"}},
            {"shot_id": "SH02", "sketch_file": "panels/missing.png", "sketch_sha256": "x"}]}

    def _new(self):
        return {"segment_id": "E1-01", "shots": [{"shot_id": "SH01", "duration": 2.0},
                                                 {"shot_id": "SH02"}, {"shot_id": "SH03"}]}

    def test_carry_over_keeps_matching_sha(self):
        new = self._new()
        res = sketch_bindings.carry_over(self._old(), new, [self.root])
        self.assertEqual(res["kept"], ["SH01"])
        self.assertEqual([d[0] for d in res["dropped"]], ["SH02"])
        for key in sketch_bindings.BINDING_FIELDS:
            self.assertIn(key, new["shots"][0])
        self.assertEqual(new["shots"][0]["duration"], 2.0)
        self.assertNotIn("sketch_file", new["shots"][1])
        self.assertNotIn("sketch_file", new["shots"][2])

    def test_changed_image_not_kept(self):
        new = self._new()
        res = sketch_bindings.carry_over(self._old(sha="0" * 64), new, [self.root])
        self.assertEqual(res["kept"], [])
        self.assertNotIn("sketch_file", new["shots"][0])

    def test_missing_sha_not_kept(self):
        old = self._old()
        del old["shots"][0]["sketch_sha256"]
        new = self._new()
        self.assertEqual(sketch_bindings.carry_over(old, new, [self.root])["kept"], [])

    def test_handoff_force_preserves(self):
        out = self.root / "layer2"
        target = out / "layer2-E1-01.json"
        target.write_text(json.dumps(self._old(), ensure_ascii=False), encoding="utf-8")
        new = {"segment_id": "E1-01", "scene_id": "S-x", "metadata": {"target_duration_sec": 2.0},
               "continuity_handshake": {"mode": "INDEPENDENT_REF2VA"}, "asset_refs": {"characters": []},
               "shots": [{"shot_id": "SH01", "duration": 2.0}]}
        with mock.patch.object(hts, "check_layer2", return_value=[]):
            rows = hts.write_skeletons([("E1-01", new)], out, force=True)
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["shots"][0]["sketch_sha256"], self.sha)
        self.assertEqual(data["shots"][0]["sketch_qc"], {"verdict": "pass"})
        self.assertEqual(rows[0]["sketch_bindings"]["kept"], ["SH01"])
        self.assertIn("保留構圖綁定 1 鏡", rows[0]["status"])

    def test_handoff_without_force_untouched(self):
        out = self.root / "layer2"
        target = out / "layer2-E1-01.json"
        before = json.dumps(self._old(), ensure_ascii=False)
        target.write_text(before, encoding="utf-8")
        new = {"segment_id": "E1-01", "scene_id": "S-x", "metadata": {"target_duration_sec": 2.0},
               "continuity_handshake": {"mode": "INDEPENDENT_REF2VA"}, "asset_refs": {"characters": []},
               "shots": [{"shot_id": "SH01", "duration": 2.0}]}
        with mock.patch.object(hts, "check_layer2", return_value=[]):
            rows = hts.write_skeletons([("E1-01", new)], out, force=False)
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertEqual(rows[0]["status"], "略過（已存在）")


# ---------------------------------------------------------------- 4. 【動作】標記
BASE = ("1-1 火山口 日/外\n"
        "導遊：這塊石頭像青蛙吧。\n"
        "遊客：一點也不像。\n")


class ActionMarker(unittest.TestCase):
    def stats(self, text):
        return db.scene_stats(db.parse_script(text).scenes)

    def test_default_seconds(self):
        a = self.stats(BASE)
        b = self.stats(BASE + "△【動作】巨鳥從火山口竄出。\n")
        self.assertAlmostEqual(b["storyboard_seconds"] - a["storyboard_seconds"], db.ACTION_DEFAULT_SEC, places=2)
        self.assertEqual(b["storyboard_action_shots"], 1)
        # 不算台詞、不進 L：密度、劇本公式片長、無台詞區間都不變
        for key in ("seconds", "density", "chars", "lines", "longest_silence"):
            self.assertEqual(a[key], b[key], key)

    def test_explicit_seconds_and_min(self):
        a = self.stats(BASE)
        b = self.stats(BASE + "△【動作3.5】爆炸。\n△【動作0.5s】碎石落地。\n")
        self.assertAlmostEqual(b["storyboard_seconds"] - a["storyboard_seconds"], 3.5 + db.MIN_SHOT_SEC, places=2)
        self.assertEqual(b["storyboard_action_shots"], 2)

    def test_no_marker_unchanged(self):
        plain = self.stats(BASE + "△巨鳥從火山口竄出。\n")
        self.assertEqual(plain["storyboard_seconds"], self.stats(BASE)["storyboard_seconds"])
        self.assertEqual(plain["storyboard_action_shots"], 0)

    def test_action_marker_not_counted_as_pause(self):
        sc = db.parse_script(BASE + "△【動作】墜坡。\n")
        act = [ln for s in sc.scenes for ln in s.lines if ln.kind == "action"][0]
        self.assertEqual(act.note, "動作")
        self.assertEqual(act.seconds, 0.0)

    def test_gate_density_unaffected_and_note(self):
        quotes = ["這塊石頭像青蛙吧", "一點也不像"]
        head = "第01集｜測試\n<!-- source: 卷1 L1-L9 -->\n"
        end = "<!-- episode-end: 「一點也不像」 | 換場 -->\n"
        a = adapt_gate.run_gate(head + BASE + end, quotes=quotes)
        b = adapt_gate.run_gate(head + BASE + "△【動作】巨鳥從火山口竄出。\n" + end, quotes=quotes)
        self.assertEqual([f for f in a["fails"] if f.startswith("G3")], [f for f in b["fails"] if f.startswith("G3")])
        self.assertEqual([w for w in a["warns"] if w.startswith("G3")], [w for w in b["warns"] if w.startswith("G3")])
        self.assertTrue(any("【動作】鏡 1 個" in n for n in b["notes"]), b["notes"])
        self.assertFalse(any("【動作】鏡" in n and "個" in n for n in a["notes"]))


if __name__ == "__main__":
    unittest.main()
