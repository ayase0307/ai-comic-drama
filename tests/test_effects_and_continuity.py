# -*- coding: utf-8 -*-
"""PART 1 特效參考圖（E56）與 PART 2 連戲檢查的回歸測試。"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import compile_layer2_to_h3 as compiler  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import continuity_lint  # noqa: E402
import verify_video_shot as verify  # noqa: E402
import voice_lint  # noqa: E402

FFMPEG = shutil.which("ffmpeg")

EFFECT_CARD = """# assets

## B-huoniao 火鳥光效
- **類型**：特效
- **固定描述片段**：`a translucent crimson-gold light-bird made of feather-like light streaks`
- **光源**：從鳥身核心向外
- **source_en**：`its own glowing core`
- **設定圖**：`images/B-huoniao_fx_v1.png`
"""


def _assets(root: Path, text: str = EFFECT_CARD) -> Path:
    path = root / "assets.md"
    path.write_text(text, encoding="utf-8")
    return path


def _registry(root: Path, assets: Path):
    return compiler.AssetRegistry(assets_path=assets, project_root=root)


def _effect_segment(reference_image: str = "images/B-huoniao_fx_v1.png"):
    return {
        "segment_id": "EP01-S01", "scene_id": "S-HALL",
        "metadata": {"aspect_ratio": "16:9", "target_duration_sec": 4.0},
        "style_lock": {"anchor": "3D donghua", "negative": "", "tail_freeze_hold": False},
        "asset_refs": {"scene_id": "S-HALL", "characters": [],
                       "effects": [{"id": "B-huoniao"}]},
        "continuity_handshake": {"mode": "INDEPENDENT_REF2VA"},
        "shots": [{
            "shot_id": "SH01", "global_shot_id": "EP01-S01-SH01",
            "start_time": 0.0, "end_time": 4.0, "duration": 4.0,
            "character_ids": [],
            "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "movement": "static"},
            "spatial_blocking": {"blocking_desc": "The light-bird hovers over the hall.",
                                 "anchor_objects": ["B-huoniao"]},
            "action_and_performance": {
                "action_stages": ["The light-bird beats its wings"],
                "observable_expression": "",
            },
            "dialogue_and_audio": {"has_dialogue": False, "line_verbatim": ""},
        }],
    }


def _ref2va_binding(global_shot_id: str, reference_image: str = "images/B-huoniao_fx_v1.png"):
    return {
        "segment_id": "EP01-S01", "video_backend": "ref2va",
        "shots": [{
            "global_shot_id": global_shot_id,
            "reference_paths": {"effects": [{"id": "B-huoniao", "reference_image": reference_image}]},
            "visual_subject_ids": [], "no_visual_reference_ids": [],
        }],
    }


class EffectAssetTests(unittest.TestCase):
    def test_b_card_with_type_and_source_is_registered_as_light_effect(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            assets = _assets(root)
            reg = _registry(root, assets)
        self.assertIn("B-huoniao", reg.effects)
        rec = reg.effects["B-huoniao"]
        self.assertTrue(rec["is_effect"])
        self.assertTrue(rec["is_light"])
        self.assertEqual(rec["source_en"], "its own glowing core")
        self.assertEqual(rec["ref_img"], "images/B-huoniao_fx_v1.png")

    def test_b_card_without_effect_keywords_stays_a_creature(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            card = chr(10).join(["# assets", "", "## B-python 暗影巨蟒",
                                  "- **固定描述片段**：`a black shadow python`"])
            assets = _assets(root, card)
            reg = _registry(root, assets)
        self.assertNotIn("B-python", reg.effects)
        self.assertIn("B-python", reg.characters)
        self.assertTrue(reg.characters["B-python"]["is_creature"])

    def test_b_creature_card_with_board_description_is_never_an_effect(self):
        card = chr(10).join([
            "# assets", "",
            "### B-baishou　白色巨獸",
            "- **固定描述片段**：`colossal white-furred wolf-like beast, blood-red eyes`",
            "- **生物設定板描述**：`白色巨獸，三視圖：頭部特寫、正面全身、側面全身`",
            "- **材質與動作**：`雪白長毛會發光`",
            "- **三視圖**：`images/B-baishou_sheet_v1.png`",
        ])
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            assets = _assets(root, card)
            reg = _registry(root, assets)
        self.assertNotIn("B-baishou", reg.effects)
        self.assertIn("B-baishou", reg.characters)
        self.assertTrue(reg.characters["B-baishou"]["is_creature"])

    def test_explicit_non_effect_type_wins_over_effect_keywords(self):
        card = chr(10).join([
            "# assets", "",
            "### B-glowbeast　微光獸",
            "- **類型**：生物",
            "- **固定描述片段**：`a beast with a glowing aura`",
            "- **三視圖**：`images/B-glowbeast_sheet_v1.png`",
        ])
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            reg = _registry(Path(td), _assets(Path(td), card))
        self.assertNotIn("B-glowbeast", reg.effects)
        self.assertIn("B-glowbeast", reg.characters)

    def test_e56_does_not_treat_a_creature_b_id_as_an_effect(self):
        card = chr(10).join([
            "# assets", "",
            "### B-baishou　白色巨獸",
            "- **固定描述片段**：`colossal white-furred wolf-like beast`",
            "- **生物設定板描述**：`白色巨獸，三視圖`",
            "- **三視圖**：`images/B-baishou_sheet_v1.png`",
        ])
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            _assets(root, card)
            seg = {
                "segment_id": "EP01-S03", "scene_id": "S-HALL",
                "shots": [{"shot_id": "SH01", "character_ids": ["B-baishou"],
                           "action_and_performance": {"action_stages": ["B-baishou lunges"]}}],
            }
            res = audit.audit_refs_and_subjects(seg, project_root=root)
        self.assertFalse(any("E56" in e for e in res["errors"]), res["errors"])

    def test_e56_errors_when_effect_has_no_bound_reference_image(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            _assets(root)
            seg = _effect_segment()
            seg["reference_images"] = []
            res = audit.audit_refs_and_subjects(seg, project_root=root)
        self.assertTrue(any("E56" in e for e in res["errors"]), res["errors"])

    def test_e56_clears_when_effect_reference_image_is_bound(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            _assets(root)
            (root / "images").mkdir()
            (root / "images" / "B-huoniao_fx_v1.png").write_bytes(b"x")
            seg = _effect_segment()
            seg["reference_images"] = [{
                "id": "B-huoniao", "type": "effect",
                "description": "a light bird", "path": "images/B-huoniao_fx_v1.png",
            }]
            res = audit.audit_refs_and_subjects(seg, project_root=root)
        self.assertFalse(any("E56" in e for e in res["errors"]), res["errors"])

    def test_e56_waiver_does_not_clear_effect(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            _assets(root)
            seg = _effect_segment()
            seg["reference_images"] = []
            seg["pack_waivers"] = [{"id": "B-huoniao", "reason": "時間不夠", "quote": "先跳過"}]
            res = audit.audit_refs_and_subjects(seg, project_root=root)
        self.assertTrue(any("E56" in e for e in res["errors"]), res["errors"])

    def test_remix_effect_needs_a_pack_and_waiver_does_not_help(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            _assets(root)
            seg = _effect_segment()
            seg.pop("reference_images", None)
            seg["video_backend"] = "remix"
            seg["refmods"] = []
            seg["pack_waivers"] = [{"id": "B-huoniao", "reason": "時間不夠", "quote": "先跳過"}]
            res = audit.audit_refs_and_subjects(seg, project_root=root)
        self.assertTrue(any("E56" in e for e in res["errors"]), res["errors"])

    def test_compiler_emits_effect_reference_and_local_light_sentence(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            assets = _assets(root)
            (root / "images").mkdir()
            (root / "images" / "B-huoniao_fx_v1.png").write_bytes(b"x")
            (root / "images" / "hall.png").write_bytes(b"x")
            reg = _registry(root, assets)
            reg.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "a school hall",
                                       "ref_img": "images/hall.png"}
            data = _effect_segment()
            data["shots"][0]["reference_paths"] = {}
            binding = _ref2va_binding("EP01-S01-SH01")
            compiled = compiler.compile_segment_h3(data, reg, auto_lora=False, stage5_binding=binding)
            prompt = compiled["h3_prompt"]
        self.assertIn("is the visual reference for the effect", prompt)
        self.assertIn("copy only its shape", prompt)
        self.assertIn("The light is emitted locally from its own glowing core", prompt)
        self.assertIn("the overall colour grade of the scene does not change", prompt)

    def test_compiler_warns_when_light_effect_has_no_source(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            card = EFFECT_CARD.replace("- **source_en**：`its own glowing core`\n", "")
            assets = _assets(root, card)
            (root / "images").mkdir()
            (root / "images" / "B-huoniao_fx_v1.png").write_bytes(b"x")
            (root / "images" / "hall.png").write_bytes(b"x")
            reg = _registry(root, assets)
            reg.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "a school hall",
                                       "ref_img": "images/hall.png"}
            data = _effect_segment()
            data["shots"][0]["reference_paths"] = {}
            compiled = compiler.compile_segment_h3(
                data, reg, auto_lora=False, stage5_binding=_ref2va_binding("EP01-S01-SH01"))
        self.assertTrue(any("特效缺光源位置" in n for n in compiled["compile_notes"]), compiled["compile_notes"])

    def test_whole_frame_tint_is_a_warning_not_an_error(self):
        prompt = ("subject_definitions:\n<Picture 1> is a scene.\n\n"
                  "detailed_description:\n[Shot 1] A MS. The light bathes the scene in red. "
                  "<d>[Chinese] 走。</d>\n\noverall_soundscape:\nWind.\n")
        codes = [i["code"] for i in voice_lint.voice_issues(prompt)]
        self.assertIn("W56", codes)
        self.assertEqual(voice_lint.voice_lint(prompt, strict=True)["errors"], [])


class EffectVocabularyTests(unittest.TestCase):
    def _seg(self, **shot_extra):
        shot = {
            "shot_id": "SH01",
            "action_and_performance": {"action_stages": ["A crimson-gold glow flares over the hall"],
                                       "observable_expression": ""},
            "spatial_blocking": {"blocking_desc": ""},
        }
        shot.update(shot_extra)
        return {"segment_id": "EP01-S01", "scene_id": "S-HALL", "shots": [shot]}

    def test_e57_errors_when_prose_describes_an_effect_without_an_effect_id(self):
        res = audit.audit_refs_and_subjects(self._seg())
        self.assertTrue(any("E57" in e for e in res["errors"]), res["errors"])

    def test_e57_chinese_light_vocabulary_also_errors(self):
        res = audit.audit_refs_and_subjects(self._seg(action_and_performance={
            "action_stages": ["紅芒一閃，光幕掃過大廳"], "observable_expression": ""}))
        self.assertTrue(any("E57" in e for e in res["errors"]), res["errors"])

    def test_e57_sunlight_and_plain_lighting_are_negative(self):
        for text in ("Afternoon sunlight falls across the hall.",
                     "The noon light and the sunlight fill the room.",
                     "陽光從窗戶照進來。"):
            with self.subTest(text=text):
                res = audit.audit_refs_and_subjects(self._seg(action_and_performance={
                    "action_stages": [text], "observable_expression": ""}))
                self.assertFalse(any("E57" in e for e in res["errors"]), res["errors"])

    def test_e57_ignores_glints_reflections_and_faint_light(self):
        for text in ("A last wet highlight on his lower lip.",
                     "畫面中央只剩一線微光，是唾液的反光。"):
            with self.subTest(text=text):
                res = audit.audit_refs_and_subjects(self._seg(action_and_performance={
                    "action_stages": [text], "observable_expression": ""}))
                self.assertFalse(any("E57" in e for e in res["errors"]), res["errors"])

    def test_e57_ignores_lighting_keys(self):
        res = audit.audit_refs_and_subjects(self._seg(
            light="a warm glow",
            action_and_performance={"action_stages": ["Mira folds the map"], "observable_expression": ""}))
        self.assertFalse(any("E57" in e for e in res["errors"]), res["errors"])

    def test_e57_per_shot_override_clears_the_error(self):
        res = audit.audit_refs_and_subjects(self._seg(
            effect_ids=[], no_effect_reason="只是窗外陽光打進來"))
        self.assertFalse(any("E57" in e for e in res["errors"]), res["errors"])

    def test_e57_listing_an_effect_id_clears_the_error(self):
        res = audit.audit_refs_and_subjects(self._seg(effect_ids=["B-huoniao"]))
        self.assertFalse(any("E57" in e for e in res["errors"]), res["errors"])


class ContinuityStaticTests(unittest.TestCase):
    def _seg(self, sid, end_state=None, anchors=None, changes=None):
        seg = {"segment_id": sid, "scene_id": "S-HALL", "h3_prompt": "[Shot 1] A MS of the hall.",
               "shots": [{}], "metadata": {"style_lock": {"continuity_anchors": anchors or {}}}}
        if end_state is not None:
            seg["segment_end_state"] = {"planned_final_state_en": end_state}
        if changes is not None:
            seg["metadata"]["continuity_changes"] = changes
        return seg

    def test_c5_warns_when_tracked_state_changes_without_marker(self):
        a = self._seg("EP01-S01-a", end_state={"effect_glow": "on", "door": "closed"})
        b = self._seg("EP01-S01-b", anchors={"effect_glow": "off", "door": "closed"})
        warnings = continuity_lint.lint_adjacent([a, b])["warnings"]
        self.assertTrue(any("C5" in w and "effect_glow" in w for w in warnings), warnings)

    def test_c5_marker_suppresses_the_warning(self):
        a = self._seg("EP01-S01-a", end_state={"effect_glow": "on"})
        b = self._seg("EP01-S01-b", anchors={"effect_glow": "off"}, changes={"effect_glow": "off"})
        warnings = continuity_lint.lint_adjacent([a, b])["warnings"]
        self.assertFalse(any("C5" in w for w in warnings), warnings)

    def test_c5_does_not_warn_when_values_match(self):
        a = self._seg("EP01-S01-a", end_state={"effect_glow": "on"})
        b = self._seg("EP01-S01-b", anchors={"effect_glow": "on"})
        warnings = continuity_lint.lint_adjacent([a, b])["warnings"]
        self.assertFalse(any("C5" in w for w in warnings), warnings)


class EndStateProseTests(unittest.TestCase):
    def test_state_sentence_uses_english_prose(self):
        body = continuity_lint.state_sentence({
            "Luonian": "back against the stone, chin lifted",
            "red sky": "spreading overhead",
        })
        self.assertEqual(body, "Luonian is back against the stone, chin lifted; the red sky is spreading overhead")
        self.assertNotIn("{", body)
        self.assertNotIn("}", body)
        self.assertNotIn('": "', body)

    def test_carry_sentence_does_not_leak_json(self):
        text = continuity_lint.carry_sentence({
            "Luonian": "back against the stone, chin lifted",
            "red sky": "spreading overhead",
        })
        self.assertIn("Starting state carried over from the previous segment: Luonian is back", text)
        self.assertNotIn("{", text)
        self.assertNotIn("}", text)

    def test_compiler_end_state_is_prose_not_json(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            assets = _assets(root)
            (root / "images").mkdir()
            (root / "images" / "hall.png").write_bytes(b"x")
            (root / "images" / "B-huoniao_fx_v1.png").write_bytes(b"x")
            reg = _registry(root, assets)
            reg.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "a school hall",
                                       "ref_img": "images/hall.png"}
            data = _effect_segment()
            data["segment_end_state"] = {"planned_final_state_en": {
                "Luonian": "back against the stone, chin lifted",
                "red sky": "spreading overhead",
            }}
            binding = _ref2va_binding("EP01-S01-SH01")
            compiled = compiler.compile_segment_h3(data, reg, auto_lora=False, stage5_binding=binding)
            prompt = compiled["h3_prompt"]
        self.assertIn("End state: Luonian is back against the stone, chin lifted; the red sky is spreading overhead.", prompt)
        self.assertNotIn('{"', prompt)
        self.assertNotIn('": "', prompt)

    def test_e58_blocks_raw_json_in_prompt(self):
        prompt = chr(10).join(["subject_definitions:", "<Picture 1> is a scene.", "",
                              "detailed_description:", "[Shot 1] A MS. End state: {\"Luonian\": \"sits\"}.", "",
                              "overall_soundscape:", "Wind.", "", "non_diegetic_music:", "N/A"])
        res = audit.lint_h3_prompt(prompt)
        self.assertTrue(any("E58" in e for e in res["errors"]), res["errors"])

    def test_e58_allows_prose(self):
        prompt = chr(10).join(["subject_definitions:", "<Picture 1> is a scene.", "",
                              "detailed_description:", "[Shot 1] A MS. End state: Luonian is back against the stone.", "",
                              "overall_soundscape:", "Wind.", "", "non_diegetic_music:", "N/A"])
        res = audit.lint_h3_prompt(prompt)
        self.assertFalse(any("E58" in e for e in res["errors"]), res["errors"])


@unittest.skipUnless(FFMPEG, "需要 ffmpeg")
class ContinuityPairsTests(unittest.TestCase):
    def test_builds_sheets_and_checklist_from_two_tiny_videos(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            videos = []
            for name, color in (("SEG-A", "red"), ("SEG-B", "blue")):
                path = root / f"{name}.mp4"
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=24:d=0.6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
                ], check=True)
                videos.append({"segment_id": name, "video_path": path})
            report = verify.build_continuity_pairs(videos, root / "pairs", width=160, height=90)
            self.assertTrue((root / "pairs" / "pairs-1.jpg").is_file())
            text = Path(report["checklist"]).read_text(encoding="utf-8")
        self.assertIn("location layout", text)
        self.assertIn("effect state", text)
        self.assertIn("dE76", text)


if __name__ == "__main__":
    unittest.main()
