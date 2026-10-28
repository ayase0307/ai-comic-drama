"""W46 構圖板自動建議（board_advisor.py＋h3d staging）：命中／不命中／武戲排除，只建議、永遠不擋。

fixture 照老易實驗第二批 EP90 S01-c（廚師送湯、沈坐角落桌、對白近景）精簡：室內自助餐店、已綁場景母片、
兩名角色、anchor_objects 有角落桌、MCU 對白鏡。證據等級：方向性（D′ 15/16 vs A′ 6/8，未達 +25 門檻）。
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import board_advisor as ba  # noqa: E402
import staging_lint as sl  # noqa: E402


def shot(sid, size, chars, dialogue=False, beat="Dramatic_Core", anchors=None, action_en=None, blocking=""):
    return {
        "shot_id": sid,
        "character_ids": list(chars),
        "dramatic_beat_type": beat,
        "camera_optics": {"shot_size": size, "focal_length": "50mm", "movement": "static"},
        "spatial_blocking": {"anchor_objects": list(anchors or []), "blocking_desc": blocking},
        "action_and_performance": {"action_stages_en": list(action_en or [])},
        "dialogue_and_audio": {"has_dialogue": dialogue, "line_verbatim": "湯來了。" if dialogue else ""},
    }


def compiled_segment(**over):
    seg = {
        "segment_id": "EP90-S01-c",
        "scene_id": "EP90-S01",
        "metadata": {"interior": True},
        "h3_prompt": "integrated_multimodal_description: ...",
        "reference_images": [
            {"id": "S-buffet", "type": "scene", "path": "images/S-buffet.png"},
            {"id": "C-shen", "type": "character", "path": "images/C-shen.png"},
            {"id": "C-chef", "type": "character", "path": "images/C-chef.png"},
        ],
        "h3_loras": [],
        "shots": [
            shot("SH01", "MS", ["C-shen", "C-chef"], anchors=["左後角小桌", "廚房門洞"]),
            shot("SH02", "MCU", ["C-shen"], dialogue=True),
        ],
    }
    seg.update(over)
    return seg


def layer2_segment():
    seg = compiled_segment()
    for key in ("h3_prompt", "reference_images", "h3_loras"):
        seg.pop(key)
    seg["asset_refs"] = {"scene_id": "S-buffet", "characters": [{"id": "C-shen"}, {"id": "C-chef"}]}
    return seg


CTX = {"root": None, "stage2_approved": None, "scenes_interior": {}, "master_paths": {}}


def codes(findings):
    return [f["code"] for f in findings]


class HitTests(unittest.TestCase):
    def test_s01c_like_compiled_segment_hits(self):
        out = ba.advise_segment(compiled_segment(), dict(CTX))
        self.assertEqual(codes(out), ["W46"])
        msg = out[0]["message"]
        self.assertTrue(msg.startswith("[W46: 建議改用母片底四格構圖板] EP90-S01-c"))
        for needle in ("spatial-consistency.md §3", "店感鎖", 'reference_view: "panel"', "panel_label_en",
                       "方向性", "15/16", "不擋送件", "SH02（MCU）"):
            self.assertIn(needle, msg)
        self.assertEqual(out[0]["level"], "suggestion")

    def test_remix_scene_pack_counts_as_master(self):
        seg = compiled_segment(reference_images=[], refmods=[{"id": "S-buffet", "kind": "scene", "pack": "buffet"}])
        self.assertEqual(codes(ba.advise_segment(seg, dict(CTX))), ["W46"])

    def test_interior_from_handoff_and_seat_words(self):
        seg = compiled_segment(metadata={})
        seg["shots"][0]["spatial_blocking"] = {"anchor_objects": [], "blocking_desc": "沈坐在左後角小桌，廚師從門洞走出"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "images").mkdir()
            (root / "images" / "S-buffet.png").write_bytes(b"png")
            (root / "handoff-ep90.json").write_text(json.dumps({"episodes": [{"scenes": [
                {"scene_id": "EP90-S01", "int_ext": "內", "setting": {"interior": True}}]}]}), encoding="utf-8")
            out = ba.advise_segment(seg, root=root)
        self.assertEqual(codes(out), ["W46"])
        self.assertIn("blocking_desc", out[0]["message"])

    def test_layer2_needs_stage2_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "images").mkdir()
            (root / "images" / "S-buffet.png").write_bytes(b"png")
            ctx = ba.load_context(root)
            self.assertIsNone(ctx["stage2_approved"])  # 沒有狀態檔＝判不了
            self.assertEqual(ba.advise_segment(layer2_segment(), ctx), [])
            ctx["stage2_approved"] = True
            self.assertEqual(codes(ba.advise_segment(layer2_segment(), ctx)), ["W46"])
            ctx["stage2_approved"] = False
            self.assertEqual(ba.advise_segment(layer2_segment(), ctx), [])

    def test_staging_lint_emits_suggestion_never_error(self):
        for strict in (False, True):
            findings = sl.lint_segment(compiled_segment(), "ref2va", strict=strict, board_ctx=dict(CTX))
            w46 = [f for f in findings if f["code"] == "W46"]
            self.assertEqual(len(w46), 1)
            self.assertEqual(w46[0]["level"], "suggestion")
            errors, warnings = sl.split_findings(findings)
            self.assertFalse(any("W46" in e for e in errors))
            self.assertEqual(sl.suggestions_of(findings), [w46[0]["message"]])
        rows = sl.lint_segments([compiled_segment()], lambda s: "ref2va")
        self.assertTrue(rows[0]["ok"])


class MissTests(unittest.TestCase):
    def assertMiss(self, seg, needle, ctx=None):
        self.assertEqual(ba.advise_segment(seg, dict(ctx or CTX)), [])
        explained = ba.advise_segment(seg, dict(ctx or CTX), explain=True)
        self.assertFalse(explained[0]["hit"])
        self.assertTrue(any(needle in m for m in explained[0]["misses"]), explained[0]["misses"])

    def test_combat_beat_excluded(self):
        seg = compiled_segment()
        seg["shots"][1]["dramatic_beat_type"] = "Combat_Impact"
        self.assertMiss(seg, "武戲")

    def test_combat_words_and_loras_excluded(self):
        seg = compiled_segment()
        seg["shots"][0]["action_and_performance"]["action_stages_en"] = ["Shen swings the stool at the rat's face"]
        self.assertMiss(seg, "武戲")
        self.assertMiss(compiled_segment(h3_loras=[{"name": "fist_impact"}]), "武戲")

    def test_single_character_excluded(self):
        seg = compiled_segment()
        for sh in seg["shots"]:
            sh["character_ids"] = ["C-shen"]
        self.assertMiss(seg, "具名角色 1 名")

    def test_scene_and_extras_ids_do_not_count_as_characters(self):
        seg = compiled_segment()
        for sh in seg["shots"]:
            sh["character_ids"] = ["C-shen", "S-buffet", "EXTRAS-diners"]
        self.assertMiss(seg, "具名角色 1 名")

    def test_outdoor_and_unknown_interior_excluded(self):
        self.assertMiss(compiled_segment(metadata={"interior": False}), "戶外")
        self.assertMiss(compiled_segment(metadata={}), "判不了內外景")

    def test_no_close_shot_excluded(self):
        seg = compiled_segment()
        seg["shots"][1]["camera_optics"]["shot_size"] = "LS"
        self.assertMiss(seg, "沒有近景")

    def test_no_dialogue_excluded(self):
        seg = compiled_segment()
        seg["shots"][1]["dialogue_and_audio"] = {"has_dialogue": False, "line_verbatim": ""}
        self.assertMiss(seg, "沒有台詞")

    def test_no_fixed_positions_excluded(self):
        seg = compiled_segment()
        seg["shots"][0]["spatial_blocking"] = {"anchor_objects": [], "blocking_desc": "兩人在走廊擦身而過"}
        self.assertMiss(seg, "固定座位")

    def test_no_scene_master_excluded(self):
        seg = compiled_segment(reference_images=[{"id": "C-shen", "type": "character", "path": "x.png"}])
        self.assertMiss(seg, "場景母片")

    def test_board_already_in_use_excluded(self):
        seg = compiled_segment()
        seg["reference_images"][0]["reference_view"] = "panel"
        self.assertMiss(seg, "已在用板")

    def test_waiver_with_quote_silences_without_quote_does_not(self):
        seg = compiled_segment(metadata={"interior": True, "staging_waivers": [
            {"code": "W46", "reason": "近景看得到門洞", "quote": "這段不用板"}]})
        self.assertEqual(ba.advise_segment(seg, dict(CTX)), [])
        self.assertNotIn("W46", codes(sl.lint_segment(seg, "ref2va", board_ctx=dict(CTX))))
        seg["metadata"]["staging_waivers"][0]["quote"] = ""
        self.assertIn("W46", codes(sl.lint_segment(seg, "ref2va", board_ctx=dict(CTX))))


class WiringTests(unittest.TestCase):
    def test_rules_registry_is_extensible_and_has_no_nine_grid_yet(self):
        self.assertEqual([r.code for r in ba.RULES], ["W46"])
        extra = ba.BoardRule("demo", "W99", "示範", "無", lambda f: (True, []), lambda f: "demo")
        with mock.patch.object(ba, "RULES", ba.RULES + [extra]):
            self.assertEqual(codes(ba.advise_segment(compiled_segment(), dict(CTX))), ["W46", "W99"])

    def test_w46_code_does_not_collide(self):
        import re
        hits = set()
        for path in (ROOT / "scripts").rglob("*.py"):
            if path.name == "board_advisor.py":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if re.search(r"\[W46:", line) and "board_advisor" not in line and "W46" in line:
                    hits.add(path.name)
        self.assertLessEqual(hits, {"staging_lint.py", "build_stage_review.py"})

    def test_cli_layer2_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "layer2").mkdir()
            (root / "images").mkdir()
            (root / "images" / "S-buffet.png").write_bytes(b"png")
            (root / "layer2" / "layer2-EP90-S01-c.json").write_text(json.dumps(layer2_segment()), encoding="utf-8")
            l2 = root / "layer2" / "layer2-EP90-S01-c.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):  # 沒有狀態檔：判不了母片驗收 → 不建議
                self.assertEqual(sl.main(["--root", str(root), "--layer2"]), 0)
            self.assertIn("構圖板建議 0 段", buf.getvalue())
            with mock.patch("project_state.state_path", return_value=l2), \
                    mock.patch("project_state.is_approved", return_value=True):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(sl.main(["--root", str(root), "--layer2"]), 0)
            self.assertIn("W46", buf.getvalue())
            self.assertIn("構圖板建議 1 段", buf.getvalue())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                sl.main(["--root", str(root), "--layer2", "--explain"])
            self.assertIn("判不了場景母片是否已驗收", buf.getvalue())

    def test_review_panel_html(self):
        import build_stage_review as bsr
        self.assertEqual(bsr.board_suggestion_panel([]), "")
        html_out = bsr.board_suggestion_panel(["EP90-S01-c: [W46: 建議改用母片底四格構圖板] …"])
        self.assertIn("W46", html_out)
        self.assertIn("spatial-consistency.md", html_out)

    def test_stage4_review_lists_layer2_suggestions(self):
        import build_stage_review as bsr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "layer2").mkdir()
            (root / "images").mkdir()
            (root / "images" / "S-buffet.png").write_bytes(b"png")
            l2 = root / "layer2" / "layer2-EP90-S01-c.json"
            l2.write_text(json.dumps(layer2_segment()), encoding="utf-8")
            self.assertEqual(bsr.stage4_board_suggestions(root, [l2]), [])
            with mock.patch("project_state.state_path", return_value=l2), \
                    mock.patch("project_state.is_approved", return_value=True):
                rows = bsr.stage4_board_suggestions(root, [l2])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].startswith("EP90-S01-c: [W46:"))


if __name__ == "__main__":
    unittest.main()
