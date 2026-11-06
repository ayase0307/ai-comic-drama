"""P1-1：段級 generation_mode（t2v/i2v/fl2v/r2v，導演大師對照）。

第一片：資料契約與門禁——schema 欄位、validate 的枚舉／幀來源檢查。
第二片（2026-11-07）：Base 三字段編譯分流（compile_segment_h3_base）與送件端
（FreeVideo media.first/last、REMIX pikaff first_frame、fl2v 僅 FreeVideo）。
"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

import compile_layer2_to_h3 as compiler  # noqa: E402
from scripts.storyboard import validate_storyboard as vs  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import submit_remix as submit_remix_mod  # noqa: E402


class GenerationModeValidateTests(unittest.TestCase):
    def test_unknown_mode_is_error(self):
        errors, _ = vs.generation_mode_checks({"generation_mode": "turbo"}, [])
        self.assertTrue(any("enum 錯誤" in e for e in errors), errors)

    def test_default_is_r2v_and_silent(self):
        errors, warnings = vs.generation_mode_checks({}, [])
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_i2v_requires_first_shot_sketch(self):
        shots = [{"shot_id": "A"}, {"shot_id": "B", "sketch_file": "sketch/b.png"}]
        errors, warnings = vs.generation_mode_checks({"generation_mode": "i2v"}, shots)
        self.assertTrue(any("G2 幀來源缺失" in e and "第 1 鏡" in e for e in errors), errors)
        self.assertTrue(any("W:G2" in w for w in warnings), warnings)

    def test_i2v_with_first_sketch_only_warns(self):
        shots = [{"shot_id": "A", "sketch_file": "sketch/a.png"}]
        errors, warnings = vs.generation_mode_checks({"generation_mode": "i2v"}, shots)
        self.assertEqual(errors, [])
        self.assertTrue(any("W:G2" in w for w in warnings), warnings)

    def test_fl2v_requires_last_shot_sketch(self):
        shots = [{"shot_id": "A", "sketch_file": "sketch/a.png"}, {"shot_id": "B"}]
        errors, _ = vs.generation_mode_checks({"generation_mode": "fl2v"}, shots)
        self.assertTrue(any("G2 幀來源缺失" in e and "末鏡" in e for e in errors), errors)

    def test_fl2v_single_shot_with_sketch_passes_structure(self):
        shots = [{"shot_id": "A", "sketch_file": "sketch/a.png"}]
        errors, _ = vs.generation_mode_checks({"generation_mode": "fl2v"}, shots)
        self.assertEqual([e for e in errors if "幀來源" in e], [])

    def test_t2v_with_characters_warns(self):
        shots = [{"shot_id": "A", "character_ids": ["C-A"]}]
        _, warnings = vs.generation_mode_checks({"generation_mode": "t2v"}, shots)
        self.assertTrue(any("W:G1" in w for w in warnings), warnings)

    def test_t2v_empty_is_silent(self):
        errors, warnings = vs.generation_mode_checks({"generation_mode": "t2v"},
                                                     [{"shot_id": "A", "character_ids": []}])
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [w for w in warnings if "W:G2" in w])


class BaseCompileTestBase(unittest.TestCase):
    """Base 三字段編譯共用的 fixture：暫存目錄＋sketch 檔＋最小 registry。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sketch = self.root / "sketch-a.png"
        self.sketch.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        self.registry = compiler.AssetRegistry(project_root=self.root)
        self.registry.locations["S-ROCK"] = {
            "id": "S-ROCK", "name": "Rock", "desc_en": "a black volcanic boulder under noon sun",
            "ref_img": "assets/scenes/rock.png"}
        self.registry.characters["C-HERO"] = {
            "id": "C-HERO", "name": "Luonian", "name_en": "Luonian",
            "short_en": "a teenage boy in a white shirt", "desc_en": "a teenage boy in a white shirt",
            "ref_img": "assets/characters/hero.png", "wardrobe_states": {}, "is_creature": False}

    def _shot(self, **over):
        shot = {
            "shot_id": "S1", "start_time": 0.0, "end_time": 7.0, "duration": 7.0,
            "character_ids": ["C-HERO"],
            "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "movement": "static"},
            "spatial_blocking": {"blocking_desc_en": "Luonian stands frame-left, the boulder frame-right.",
                                 "anchor_objects_en": ["the black boulder"]},
            "action_and_performance": {
                "action_stages_en": ["He plants his feet", "he raises his right arm toward the sky"],
                "observable_expression_en": "jaw set, eyes forward",
            },
            "dialogue_and_audio": {"has_dialogue": True, "speaker": "C-HERO", "line_verbatim": "風停了。",
                                   "speech_window": {"start": 1.0, "end": 2.2, "unit": "segment_seconds"}},
        }
        shot.update(over)
        return shot

    def _segment(self, mode, shots=None, **meta_over):
        metadata = {"aspect_ratio": "16:9", "target_duration_sec": 7.0, "generation_mode": mode}
        metadata.update(meta_over)
        return {
            "project_id": "T", "scene_id": "S-ROCK", "segment_id": "EP01-S01-x",
            "metadata": metadata,
            "style_lock": {"anchor": "3D donghua with clean rim light", "negative": "", "tail_freeze_hold": False},
            "asset_refs": {"scene_id": "S-ROCK", "characters": [{"id": "C-HERO"}]},
            "overall_soundscape": "Wind over the ridge.",
            "non_diegetic_music": "N/A",
            "shots": shots if shots is not None else [self._shot(sketch_file=str(self.sketch))],
        }

    def _compile(self, data, **kw):
        return compiler.compile_segment_h3(json.loads(json.dumps(data)), registry=self.registry,
                                           auto_lora=False, **kw)


class GenerationModeCompileTests(BaseCompileTestBase):
    def test_unknown_mode_fails_with_enum_list(self):
        with self.assertRaises(ValueError) as ctx:
            self._compile(self._segment("turbo"))
        self.assertIn("generation_mode", str(ctx.exception))

    def test_schema_declares_generation_mode(self):
        schema = json.loads((ROOT / "references/storyboard/templates/layer2-storyboard.schema.json")
                            .read_text(encoding="utf-8"))
        prop = schema["properties"]["metadata"]["properties"]["generation_mode"]
        self.assertEqual(prop["enum"], ["t2v", "i2v", "fl2v", "r2v"])

    # ---------- i2v：Base 三字段＋首幀 ----------
    def test_i2v_compiles_base_structure(self):
        out = self._compile(self._segment("i2v"))
        prompt = out["h3_prompt"]
        self.assertTrue(prompt.startswith(compiler.I2V_INSTRUCTION_EN), prompt[:120])
        # Base 結構：三欄，沒有六段的前三段與 detailed_description
        self.assertIn("integrated_multimodal_description:", prompt)
        self.assertIn("overall_soundscape:", prompt)
        self.assertIn("non_diegetic_music:", prompt)
        for banned in ("subject_definitions:", "summary:", "retention_analysis:", "detailed_description:"):
            self.assertNotIn(banned, prompt)
        self.assertEqual(out["reference_images"], [])
        self.assertEqual(out["metadata"]["generation_mode"], "i2v")
        self.assertEqual(out["metadata"]["frame_sources"], {"first": str(self.sketch)})
        # 首幀錨進第 1 鏡開頭
        self.assertIn("The shot begins from <Picture 1>:", prompt)

    def test_i2v_dialogue_keeps_speaker_id(self):
        out = self._compile(self._segment("i2v"))
        # E22：發聲者要有穩定 (Sx) 代號；Base 沒有 <Subject N>，用資產名綁定
        self.assertIn("Luonian (S1) is the visible speaking character", out["h3_prompt"])
        self.assertIn("<d>[Chinese] 風停了。</d>", out["h3_prompt"])

    def test_i2v_missing_sketch_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            self._compile(self._segment("i2v", shots=[self._shot()]))
        self.assertIn("sketch_file", str(ctx.exception))

    def test_i2v_missing_sketch_file_on_disk_fails_closed(self):
        data = self._segment("i2v", shots=[self._shot(sketch_file="sketch/ghost.png")])
        with self.assertRaises(ValueError) as ctx:
            self._compile(data)
        self.assertIn("不存在", str(ctx.exception))

    # ---------- t2v：無對齊指令、無幀來源 ----------
    def test_t2v_has_no_instruction_and_no_frames(self):
        data = self._segment("t2v", shots=[self._shot(character_ids=[], sketch_file=str(self.sketch),
                                                      dialogue_and_audio={"has_dialogue": False})])
        out = self._compile(data)
        prompt = out["h3_prompt"]
        self.assertTrue(prompt.startswith("integrated_multimodal_description:"), prompt[:80])
        self.assertNotIn("For the target video", prompt)
        self.assertNotIn("How the reference pictures align", prompt)
        self.assertNotIn("frame_sources", json.dumps(out["metadata"]))
        self.assertIn("The shot opens on a MS (35mm) of the scene", prompt)

    # ---------- fl2v：首尾幀對齊指令＋末鏡落尾幀 ----------
    def test_fl2v_instruction_declares_both_marks(self):
        out = self._compile(self._segment("fl2v"))
        prompt = out["h3_prompt"]
        self.assertIn("Picture 1 (from Shot 1) aligns with the 0.00-second mark", prompt)
        self.assertRegex(prompt, r"Picture 2 \(from Shot 1\) aligns with the \d+\.\d{2}-second mark")
        self.assertEqual(out["metadata"]["frame_sources"],
                         {"first": str(self.sketch), "last": str(self.sketch)})
        self.assertIn("The final frame matches <Picture 2>.", prompt)

    def test_fl2v_multi_shot_uses_last_shot_number(self):
        s1 = self._shot(sketch_file=str(self.sketch), shot_id="S1",
                        start_time=0.0, end_time=3.5, duration=3.5)
        s2 = self._shot(sketch_file=str(self.sketch), shot_id="S2",
                        start_time=3.5, end_time=7.0, duration=3.5,
                        dialogue_and_audio={"has_dialogue": False})
        out = self._compile(self._segment("fl2v", shots=[s1, s2]))
        self.assertIn("Picture 2 (from Shot 2) aligns with", out["h3_prompt"])

    def test_fl2v_missing_last_sketch_fails_closed(self):
        s1 = self._shot(sketch_file=str(self.sketch), shot_id="S1",
                        start_time=0.0, end_time=3.5, duration=3.5)
        s2 = self._shot(shot_id="S2", start_time=3.5, end_time=7.0, duration=3.5,
                        dialogue_and_audio={"has_dialogue": False})
        with self.assertRaises(ValueError) as ctx:
            self._compile(self._segment("fl2v", shots=[s1, s2]))
        self.assertIn("末鏡", str(ctx.exception))

    # ---------- remix 後端 ----------
    def test_remix_i2v_base_three_columns_with_instruction(self):
        data = self._segment("i2v", style_anchor_en="3D donghua with clean rim light, painterly shading")
        out = self._compile(data, backend="remix")
        prompt = out["h3_prompt"]
        self.assertTrue(prompt.startswith(compiler.I2V_INSTRUCTION_EN), prompt[:120])
        self.assertIn("integrated_multimodal_description: 3D donghua with clean rim light", prompt)
        self.assertEqual(out["metadata"]["video_backend"], "remix")
        self.assertEqual(out["refmods"] if "refmods" in out else [], [])
        # remix 三欄審查與 lint 都要過
        res = audit.audit_remix(out)
        self.assertTrue(res["passed"], res["errors"])
        l_res = audit.lint_h3_prompt(prompt, nominal_duration=out["metadata"]["target_duration_sec"],
                                     rounding_mode=out["metadata"]["rounding_mode"],
                                     authored_shots=out["shots"], backend="remix",
                                     submit_endpoint="local", generation_mode="i2v")
        self.assertTrue(l_res["passed"], l_res["errors"])

    def test_remix_fl2v_is_rejected_at_compile(self):
        data = self._segment("fl2v", style_anchor_en="3D donghua with clean rim light, painterly shading")
        with self.assertRaises(ValueError) as ctx:
            self._compile(data, backend="remix")
        self.assertIn("pikaff", str(ctx.exception))

    def test_stage5_binding_is_ignored_with_note(self):
        out = self._compile(self._segment("i2v"), stage5_binding={"shots": []})
        self.assertTrue(any("不吃 stage5 綁定" in n for n in out["compile_notes"]), out["compile_notes"])

    # ---------- r2v 回歸：六段式路線不變 ----------
    def test_r2v_still_produces_six_sections(self):
        data = self._segment("r2v")
        data["continuity_handshake"] = {"mode": "INDEPENDENT_REF2VA"}
        out = self._compile(data)
        prompt = out["h3_prompt"]
        for section in ("subject_definitions:", "summary:", "retention_analysis:",
                        "detailed_description:", "overall_soundscape:", "non_diegetic_music:"):
            self.assertIn(section, prompt)
        self.assertEqual(len(out["reference_images"]), 2)  # 場景＋角色
        self.assertNotIn("generation_mode", json.dumps(out["metadata"]).replace('"generation_mode": "r2v"', ""))


class BaseGateTests(unittest.TestCase):
    """lint／audit／送件端對 Base 段的行為。"""

    def test_lint_base_prompt_passes_single_shot(self):
        prompt = (
            "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
            "\n"
            "integrated_multimodal_description:\n"
            "The target video follows the authored visual style (16:9), illuminated by soft dusk sunlight.\n"
            "[Shot 1] The shot begins from <Picture 1>: eye-level medium shot of a teenage boy on a rooftop, "
            "as the camera holds a static shot. First he turns slowly to his right toward the skyline, "
            "then the wind lifts the hem of his coat.\n"
            "\n"
            "overall_soundscape:\n"
            "Low hum of wind blowing across the concrete roof.\n"
            "\n"
            "non_diegetic_music:\n"
            "N/A\n"
        )
        res = audit.lint_h3_prompt(prompt, nominal_duration=7.0, rounding_mode="ceil",
                                   submit_endpoint="local", generation_mode="i2v")
        self.assertTrue(res["passed"], res["errors"])

    def test_lint_base_missing_soundscape_is_error(self):
        prompt = (
            "integrated_multimodal_description:\n"
            "The target video follows the authored visual style (16:9), illuminated by soft dusk sunlight.\n"
            "[Shot 1] The shot opens on a wide empty rooftop, as the camera holds a static shot. "
            "First the lamp flickers once, then the clock ticks twice as the camera stays still.\n"
            "\n"
            "non_diegetic_music:\n"
            "N/A\n"
        )
        res = audit.lint_h3_prompt(prompt, nominal_duration=7.0, rounding_mode="ceil",
                                   submit_endpoint="local", generation_mode="t2v")
        self.assertFalse(res["passed"])
        self.assertTrue(any("E1" in e and "overall_soundscape" in e for e in res["errors"]), res["errors"])

    def test_audit_ref2va_base_skips_subject_pairing_warning(self):
        seg = {
            "segment_id": "EP01-S01-x",
            "metadata": {"generation_mode": "i2v"},
            "reference_images": [],
            "h3_prompt": "integrated_multimodal_description:\n[Shot 1] The shot begins from <Picture 1>: "
                         "a wide rooftop at dusk, as the camera holds a static shot. First the lamp flickers, "
                         "then the clock ticks as the camera stays still.\n\noverall_soundscape:\nWind.\n\n"
                         "non_diegetic_music:\nN/A\n",
        }
        res = audit.audit_refs_and_subjects(seg)
        self.assertTrue(res["passed"], res["errors"])
        self.assertFalse(any("subject_definitions" in w for w in res["warnings"]), res["warnings"])

    def test_audit_remix_base_skips_pack_checks(self):
        seg = {
            "segment_id": "EP01-S01-x",
            "metadata": {"generation_mode": "i2v", "video_backend": "remix",
                         "style_anchor_en": "3D donghua with clean rim light"},
            "refmods": [],
            "h3_prompt": "For the target video, at 0.00 seconds into the target video, "
                         "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
                         "integrated_multimodal_description: 3D donghua with clean rim light The whole clip is 16:9, "
                         "lit by soft dusk sunlight. [Shot 1] The shot begins from <Picture 1>: a teenage boy on a "
                         "rooftop, as the camera holds a static shot. First he turns to his right, then the wind lifts "
                         "his coat as the camera trucks left while panning right.\n\n"
                         "overall_soundscape: Wind.\n\nnon_diegetic_music: N/A\n",
        }
        res = audit.audit_remix(seg)
        self.assertTrue(res["passed"], res["errors"])

    def test_resolve_segment_mode_maps_pika_to_pikaff(self):
        seg = {"metadata": {"generation_mode": "i2v"}}
        mode, warnings = submit_remix_mod.resolve_segment_mode(seg, "pika768")
        self.assertEqual(mode, "pikaff768")
        self.assertTrue(warnings)
        mode, warnings = submit_remix_mod.resolve_segment_mode(seg, "pikaff480")
        self.assertEqual(mode, "pikaff480")
        self.assertEqual(warnings, [])
        with self.assertRaises(ValueError):
            submit_remix_mod.resolve_segment_mode(seg, "pika1440")
        seg_t2v = {"metadata": {"generation_mode": "t2v"}}
        mode, warnings = submit_remix_mod.resolve_segment_mode(seg_t2v, "pika768")
        self.assertEqual((mode, warnings), ("pika768", []))


class BaseFrameMediaTests(unittest.TestCase):
    """FreeVideo 送件端：Base 模式的 media.first／media.last。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sketch = self.root / "sketch-a.png"
        self.sketch.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    def _args(self):
        return types.SimpleNamespace(root_dir=str(self.root), api_url="http://127.0.0.1:8189")

    def test_i2v_sends_first_only(self):
        import submit_h3_segments as sub
        calls = []
        orig = sub.upload_reference_media
        sub.upload_reference_media = lambda api, token, path, cache, cf: calls.append(Path(path)) or "file-1"
        try:
            seg = {"metadata": {"generation_mode": "i2v", "frame_sources": {"first": "sketch-a.png"}}}
            media = sub._base_frame_media(seg, "i2v", self._args(), "tok", {}, Path("cache.json"))
        finally:
            sub.upload_reference_media = orig
        self.assertEqual(media, {"first": {"file": "file-1"}})
        self.assertEqual([p.name for p in calls], ["sketch-a.png"])

    def test_fl2v_sends_first_and_last(self):
        import submit_h3_segments as sub
        ids = iter(["file-1", "file-2"])
        orig = sub.upload_reference_media
        sub.upload_reference_media = lambda api, token, path, cache, cf: next(ids)
        try:
            seg = {"metadata": {"generation_mode": "fl2v",
                                "frame_sources": {"first": "sketch-a.png", "last": "sketch-a.png"}}}
            media = sub._base_frame_media(seg, "fl2v", self._args(), "tok", {}, Path("cache.json"))
        finally:
            sub.upload_reference_media = orig
        self.assertEqual(media, {"first": {"file": "file-1"}, "last": {"file": "file-2"}})

    def test_t2v_sends_no_media(self):
        import submit_h3_segments as sub
        seg = {"metadata": {"generation_mode": "t2v"}}
        media = sub._base_frame_media(seg, "t2v", self._args(), "tok", {}, Path("cache.json"))
        self.assertEqual(media, {})

    def test_missing_frame_source_raises(self):
        import submit_h3_segments as sub
        seg = {"metadata": {"generation_mode": "i2v", "frame_sources": {}}}
        with self.assertRaises(ValueError) as ctx:
            sub._base_frame_media(seg, "i2v", self._args(), "tok", {}, Path("cache.json"))
        self.assertIn("frame_sources.first", str(ctx.exception))


class RemixFirstFrameBodyTests(unittest.TestCase):
    """REMIX 送件端：build_job_body 的 first_frame 與 fl2v 拒送。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sketch = self.root / "sketch-a.png"
        self.sketch.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    def _seg(self, mode, frame_sources):
        return {"segment_id": "EP01-S01-x",
                "metadata": {"generation_mode": mode, "frames": 124,
                             "effective_duration_sec_exact": 124 / 24,
                             "aspect_ratio": "16:9", "rounding_mode": "floor",
                             "frame_sources": frame_sources},
                "h3_prompt": "integrated_multimodal_description: x\n\noverall_soundscape: y\n\nnon_diegetic_music: N/A\n",
                "refmods": []}

    def test_i2v_body_carries_first_frame(self):
        body, warnings = submit_remix_mod.build_job_body(
            self._seg("i2v", {"first": "sketch-a.png"}), "proj", "pikaff768", None, root_dir=self.root)
        self.assertEqual(body["first_frame"], str(self.sketch))
        self.assertEqual(body["refmods"], [])

    def test_i2v_missing_frame_source_raises(self):
        with self.assertRaises(ValueError) as ctx:
            submit_remix_mod.build_job_body(self._seg("i2v", {}), "proj", "pikaff768", None, root_dir=self.root)
        self.assertIn("frame_sources.first", str(ctx.exception))

    def test_fl2v_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            submit_remix_mod.build_job_body(self._seg("fl2v", {"first": "sketch-a.png"}),
                                            "proj", "pika768", None, root_dir=self.root)
        self.assertIn("pikaff", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
