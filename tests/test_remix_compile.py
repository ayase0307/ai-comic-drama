"""PR-R5：REMIX 三欄提示詞輸出（compile_layer2_to_h3 的 remix emitter）。

驗證：
  - golden fixture（EP04-S02-d 類：場景＋三個演員＝4 包、三人對話）逐字比對；
  - 三欄結構：風格錨開頭、[Shot N]＋五小節、<Picture N>／<Video N> 依 refmods 各自編號、場景第一、
    介紹句只寫身份不寫位置姿態、不輸出 subject_definitions／retention_analysis／summary；
  - 產出的 segments 通過 audit remix 分支（E50–E55）、lint（三欄）、refcheck、staging、prompt_authoring（E30–E40）；
  - 編譯指紋（E38）照舊；tag 編號錯誤時編譯器與 audit（E52）都擋；
  - 台詞 <d>[Chinese] …</d> 與畫外音規則沿用 ref2va。
"""
import contextlib
import copy
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "tests"))

import _remix_fixture as fx  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import compile_layer2_to_h3 as compiler  # noqa: E402
import generate_bindings as gb  # noqa: E402
import project_state as ps  # noqa: E402
import prompt_authoring  # noqa: E402
import refcheck  # noqa: E402
import staging_lint  # noqa: E402
import submit_h3_segments as submit  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "remix" / "EP04-S02-d.txt"


def _run(args, cwd):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, *[str(a) for a in args]], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=240)


def _codes(messages):
    return {m.group(1) for m in (re.match(r".*?\[(E\d+|W\d+|D\d+)\b", x) for x in messages) if m}


class RemixProject(unittest.TestCase):
    """每個測試一個乾淨的 remix 專案（bind 過）。"""

    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def make(self, **kwargs):
        self.layer2_path = fx.write_project(self.root, **kwargs)
        self.bind()

    def bind(self):
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            code = gb.main(["--root", str(self.root)])
        self.assertEqual(code, 0, err.getvalue())
        self.bindings = json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))

    def registry(self):
        return compiler.AssetRegistry(bible_path=self.root / "video-bible.json", project_root=self.root)

    def compile(self, layer2=None, binding=None, **kwargs):
        data = layer2 if layer2 is not None else json.loads(self.layer2_path.read_text(encoding="utf-8"))
        binding = binding if binding is not None else copy.deepcopy(self.bindings["segments"][0])
        with contextlib.redirect_stderr(io.StringIO()):
            return compiler.compile_segment_h3(data, self.registry(), auto_lora=False, stage5_binding=binding,
                                               remix_packs=self.bindings.get("packs"), **kwargs)


class RemixGoldenTests(RemixProject):
    def test_golden_prompt_verbatim(self):
        self.make()
        seg = self.compile()
        expected = GOLDEN.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(seg["h3_prompt"], expected)

    def test_cli_output_matches_in_process_and_passes_check(self):
        self.make()
        result = _run([ROOT / "scripts" / "storyboard" / "compile_layer2_to_h3.py", "--layer2", "layer2/",
                       "--bible", "video-bible.json", "--bindings", "video-bindings.json", "--episode", "EP04",
                       "--project-root", ".", "--skip-stage-gate", "--output-segments", "segments-ep04.json",
                       "--output-md", "prompts-ep04.md", "--check"], self.root)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])
        self.assertIn("REMIX 三欄", result.stdout)
        self.assertIn("錯誤數: 0", result.stdout)
        seg = json.loads((self.root / "segments-ep04.json").read_text(encoding="utf-8"))["segments"][0]
        self.assertEqual(seg["h3_prompt"], GOLDEN.read_text(encoding="utf-8").replace("\r\n", "\n"))
        md = (self.root / "prompts-ep04.md").read_text(encoding="utf-8")
        self.assertIn("REMIX 三欄提示詞包", md)
        self.assertIn("`<Video 3>` (actor): `C-YE` → 包 `ejin3_yeweishan`", md)
        self.assertNotIn("官方六段式", md)


class RemixStructureTests(RemixProject):
    def setUp(self):
        super().setUp()
        self.make()
        self.seg = self.compile()
        self.prompt = self.seg["h3_prompt"]
        self.body = audit._section_body(self.prompt, "integrated_multimodal_description").strip()

    def test_three_columns_only(self):
        self.assertEqual(re.findall(r"^([a-z_]+):", self.prompt, re.M),
                         ["integrated_multimodal_description", "overall_soundscape", "non_diegetic_music"])
        for section in ("subject_definitions", "retention_analysis", "summary", "detailed_description"):
            self.assertNotIn(f"{section}:", self.prompt)
        self.assertNotIn("<Subject", self.prompt)
        self.assertIn("non_diegetic_music: N/A", self.prompt)

    def test_style_anchor_first_and_style_lock_last(self):
        self.assertTrue(self.body.startswith(fx.ANCHOR))
        self.assertEqual(self.seg["metadata"]["style_anchor_en"], fx.ANCHOR)
        self.assertLess(self.body.index("[Shot 2]"), self.body.index("Style lock for every shot:"))
        self.assertTrue(self.body.rstrip().endswith("no graffiti."), "無字句預設開，放最後")

    def test_tags_follow_refmods_and_scene_first(self):
        self.assertEqual([r["label"] for r in self.seg["refmods"]],
                         ["<Picture 1>", "<Video 1>", "<Video 2>", "<Video 3>"])
        self.assertEqual(self.seg["refmods"][0]["kind"], "scene")
        intro = self.body.split("The shot opens on a", 1)[0]
        self.assertLess(intro.index("<Picture 1> is the location"), intro.index("<Video 1> is Shen Luonian,"))
        self.assertLess(intro.index("<Video 1> is Shen Luonian,"), intro.index("<Video 2> is Lai Yixin,"))
        self.assertLess(intro.index("<Video 2> is Lai Yixin,"), intro.index("<Video 3> is Ye Weishan,"))
        self.assertEqual(self.prompt.count("<Video 3>"), 1, "每個包一句介紹，鏡內用英文名")

    def test_intro_sentences_carry_identity_not_position(self):
        intros = [m.group(0) for m in prompt_authoring.REMIX_INTRO.finditer(self.body)]
        self.assertEqual(len(intros), 3)
        for sentence in intros:
            self.assertIsNone(prompt_authoring.MAPPING_POSITION.search(sentence), sentence)
            self.assertIsNone(prompt_authoring.MAPPING_POSE.search(sentence), sentence)
        self.assertEqual(prompt_authoring.audit_mapping_layer(self.prompt), [])

    def test_shot_heads_five_parts_and_dialogue(self):
        self.assertIn("[Shot 2] At 00:04.300, the shot cuts to a MS (50mm, 2.5m)", self.body)
        for label in ("Camera:", "Motion:", "Performance:", "Light:", "Sound:"):
            self.assertEqual(self.body.count(label), 2, label)
        self.assertIn("Ye Weishan (S1) is the visible speaking character, a composed teenage girl with a cool, crisp, "
                      "clear voice, and says: <d>[Chinese] 他們又用不到，當然是我們的。</d>", self.body)
        self.assertIn("while Shen Luonian's and Lai Yixin's lips remain completely closed", self.body)
        self.assertNotIn("{C-", self.body, "五小節的 {C-id} 要換成英文名")
        self.assertEqual(self.seg["speaker_ids"], {"C-YE": "S1"})

    def test_segment_fields_and_frames(self):
        meta = self.seg["metadata"]
        self.assertEqual(meta["video_backend"], "remix")
        self.assertEqual((meta["frames"], meta["rounding_mode"]), (175, "ceil"), "台詞段照 ref2va 往上取，送 frames/24 精確值")
        self.assertEqual(self.seg["reference_images"], [])
        self.assertEqual(self.seg["h3_loras"], [])
        self.assertEqual([p["id"] for p in self.seg["positions"]], ["C-SHEN", "C-LAI", "C-YE"])
        self.assertEqual(self.seg["shots"][0]["visual_subject_ids"], ["C-SHEN", "C-LAI", "C-YE"])
        self.assertEqual(self.seg["shots"][1]["pack_ids"], ["C-LAI", "C-YE"])

    def test_fingerprint_covers_integrated_description(self):
        fp = self.seg["metadata"]["compiled_prompt_sha256"]
        self.assertEqual(fp, prompt_authoring.prompt_fingerprint(self.prompt))
        self.assertEqual(prompt_authoring.detailed_description(self.prompt), self.body)
        res = prompt_authoring.audit_segments([self.seg])
        self.assertFalse(any("E38" in e for e in res["errors"]), res["errors"])
        tampered = copy.deepcopy(self.seg)
        tampered["h3_prompt"] = self.prompt.replace("broad grin", "huge grin")
        res = prompt_authoring.audit_segments([tampered])
        self.assertTrue(any("E38" in e for e in res["errors"]), res["errors"])
        # 只改環境音欄不算改寫逐鏡描述（指紋只看 integrated_multimodal_description）
        sound_only = copy.deepcopy(self.seg)
        sound_only["h3_prompt"] = self.prompt.replace("light footsteps.", "light footsteps and wind.")
        self.assertFalse(any("E38" in e for e in prompt_authoring.audit_segments([sound_only])["errors"]))


class RemixGateTests(RemixProject):
    def setUp(self):
        super().setUp()
        self.make()
        self.seg = self.compile()

    def test_audit_remix_branch_passes(self):
        res = audit.audit_refs_and_subjects(self.seg, project_root=self.root)
        self.assertEqual(res["backend"], "remix")
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["total_references"], 4)

    def test_lint_three_columns_passes(self):
        meta = self.seg["metadata"]
        res = audit.lint_h3_prompt(self.seg["h3_prompt"], nominal_duration=meta["target_duration_sec"],
                                   rounding_mode=meta["rounding_mode"], authored_shots=self.seg["shots"],
                                   backend="remix")
        self.assertEqual(res["errors"], [])
        self.assertTrue(res["details"]["authored_shot_count_exception"], res["warnings"])

    def test_refcheck_and_staging_pass(self):
        plan = refcheck.load_pack_plan(self.root)
        lexicon = refcheck.load_lexicon(self.root, plan)
        rc = refcheck.check_segment(self.seg, lexicon, "remix", plan, [fx.ANCHOR])
        self.assertEqual(rc["missing"], [], rc)
        findings = staging_lint.lint_segment(self.seg, "remix", lexicon=lexicon, strict=True)
        self.assertEqual([f for f in findings if f["level"] == "error"], [])
        self.assertFalse({"D07", "D08", "D09", "D14"} & {f["code"] for f in findings}, findings)

    def test_prompt_authoring_passes(self):
        res = prompt_authoring.audit_segments([self.seg])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["warnings"], [])

    def test_stage5_validation_accepts_remix_segments(self):
        (self.root / "segments-ep04.json").write_text(json.dumps({"segments": [self.seg]}, ensure_ascii=False),
                                                      encoding="utf-8")
        errors = ps.stage_validation_errors(self.root, 5)
        self.assertFalse(any("reference_images" in e for e in errors), errors)
        empty = dict(self.seg, refmods=[])
        (self.root / "segments-ep04.json").write_text(json.dumps({"segments": [empty]}, ensure_ascii=False),
                                                      encoding="utf-8")
        self.assertTrue(any("refmods" in e for e in ps.stage_validation_errors(self.root, 5)))

    def test_freevideo_submit_refuses_remix_segments(self):
        with contextlib.redirect_stdout(io.StringIO()):
            ok, errors = submit.audit_segment_prompts([self.seg], root_dir=self.root)
        self.assertFalse(ok)
        self.assertTrue(any("PR-R7" in e for e in errors), errors)

    def test_tag_number_errors_are_blocked(self):
        binding = copy.deepcopy(self.bindings["segments"][0])
        binding["refmods"][2]["label"] = "<Video 3>"
        with self.assertRaisesRegex(ValueError, "E52"):
            self.compile(binding=binding)
        binding = copy.deepcopy(self.bindings["segments"][0])
        binding["refmods"] = binding["refmods"][1:] + binding["refmods"][:1]
        for ref in binding["refmods"]:
            ref.pop("label", None)
        with self.assertRaisesRegex(ValueError, "E53"):
            self.compile(binding=binding)
        # 編譯後提示詞被改成引用不存在的 <Video 4>：audit E52 擋
        bad = copy.deepcopy(self.seg)
        bad["h3_prompt"] = bad["h3_prompt"].replace("<Video 3> is", "<Video 4> is")
        codes = _codes(audit.audit_refs_and_subjects(bad, project_root=self.root)["errors"])
        self.assertIn("E52", codes)

    def test_three_columns_fail_ref2va_lint_but_pass_remix_lint(self):
        meta = self.seg["metadata"]
        kwargs = dict(nominal_duration=meta["target_duration_sec"], rounding_mode=meta["rounding_mode"],
                      authored_shots=self.seg["shots"])
        ref2va = audit.lint_h3_prompt(self.seg["h3_prompt"], **kwargs)
        self.assertIn("E1", _codes(ref2va["errors"]), "三欄缺六段式必填區塊，ref2va lint 本來就不合格")
        self.assertTrue(audit.lint_h3_prompt(self.seg["h3_prompt"], backend="remix", **kwargs)["passed"])


class RemixRuleTests(RemixProject):
    def test_missing_english_name_is_an_error(self):
        bible = copy.deepcopy(fx.BIBLE)
        del bible["characters"][0]["name_en"]
        fx.write_project(self.root)
        (self.root / "adapt" / "bible.json").write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
        self.layer2_path = self.root / "layer2" / "layer2-EP04-S02-d.json"
        self.bind()
        with self.assertRaisesRegex(ValueError, "name_en"):
            self.compile()
        # 計畫表寫 name_en 也可以
        packs = copy.deepcopy(fx.PACKS)
        packs["packs"]["C-YE"]["name_en"] = "Ye Weishan"
        (self.root / "assets" / "character-packs.json").write_text(json.dumps(packs, ensure_ascii=False),
                                                                   encoding="utf-8")
        self.bind()
        self.assertIn("<Video 3> is Ye Weishan,", self.compile()["h3_prompt"])

    def test_missing_style_anchor_is_an_error(self):
        self.make(anchor=False)
        with self.assertRaisesRegex(ValueError, "E55"):
            self.compile()
        data = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        data["metadata"]["style_anchor_en"] = "Painterly 3D CG with soft rim light."
        seg = self.compile(layer2=data)
        self.assertTrue(audit._section_body(seg["h3_prompt"], "integrated_multimodal_description").strip()
                        .startswith("Painterly 3D CG with soft rim light."))

    def test_backend_and_binding_must_agree(self):
        self.make()
        with self.assertRaisesRegex(ValueError, "ref2va"):
            self.compile(backend="ref2va")
        data = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(ValueError, "remix 綁定"):
            compiler.compile_segment_h3(data, self.registry(), auto_lora=False, backend="remix")

    def test_offscreen_voiceover_follows_ref2va_rules(self):
        self.make()
        data = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        data["shots"][1]["dialogue_and_audio"] = {
            "has_dialogue": True, "speaker": "C-SHEN", "line_verbatim": "真麻煩。", "offscreen_form": "voiceover",
            "voice_4d_spec_en": "a calm, low teenage boy's voice"}
        seg = self.compile(layer2=data)
        body = seg["h3_prompt"]
        self.assertIn("Shen Luonian (S2) says in an off-screen voiceover, a calm, low teenage boy's voice: "
                      "<d>[Chinese] 真麻煩。</d>", body)
        self.assertIn("lips remain completely closed", body.split("[Shot 2]", 1)[1])
        res = audit.audit_refs_and_subjects(seg, project_root=self.root)
        self.assertEqual(res["errors"], [])

    def test_lettering_guard_can_be_turned_off(self):
        self.make()
        seg = self.compile(no_lettering=False)
        self.assertNotIn("no lettering", seg["h3_prompt"])
        self.assertNotIn("no_lettering_added", seg["metadata"])
        self.assertTrue(audit._section_body(seg["h3_prompt"], "integrated_multimodal_description").rstrip()
                        .endswith("environment."))

    def test_costume_variant_uses_pack_description(self):
        packs = copy.deepcopy(fx.PACKS)
        packs["packs"]["C-SHEN"]["costumes"] = {"W-SHEN-dusty": {
            "pack": "ejin3_shen_dusty",
            "description_en": "a slim pale 17 year old boy in a grey-dusted school shirt with a torn left shoulder seam"}}
        layer2 = fx.layer2_doc()
        layer2["asset_refs"]["characters"][2] = {"id": "C-SHEN", "costume_id": "W-SHEN-dusty"}
        self.make(packs=packs, layer2=layer2)
        seg = self.compile()
        shen = next(r for r in seg["refmods"] if r["id"] == "C-SHEN")
        self.assertEqual((shen["pack"], shen["costume_id"]), ("ejin3_shen_dusty", "W-SHEN-dusty"))
        self.assertIn("<Video 1> is Shen Luonian, a slim pale 17 year old boy in a grey-dusted school shirt",
                      seg["h3_prompt"])

    def test_w42_flags_position_words_in_remix_intro(self):
        bible = copy.deepcopy(fx.BIBLE)
        bible["characters"][1]["visual_prompt_en"] += ", standing on the left"
        fx.write_project(self.root)
        (self.root / "adapt" / "bible.json").write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
        self.layer2_path = self.root / "layer2" / "layer2-EP04-S02-d.json"
        self.bind()
        warnings = prompt_authoring.audit_mapping_layer(self.compile()["h3_prompt"])
        self.assertTrue(any("W42" in w and "<Video 2>" in w for w in warnings), warnings)

    def test_unbound_character_is_caught_by_coverage(self):
        self.make()
        seg = self.compile()
        seg["shots"][1]["character_ids"] = ["C-LAI", "C-YE", "C-MA"]
        errors = prompt_authoring.audit_subject_coverage(seg)
        self.assertTrue(any("E40" in e and "C-MA" in e for e in errors), errors)
        seg["pack_waivers"] = [{"id": "C-MA", "reason": "背景遠景", "quote": "馬聯不用包"}]
        self.assertEqual(prompt_authoring.audit_subject_coverage(seg), [])

    def test_ref2va_compile_is_unchanged_by_remix_parameters(self):
        """沒有 remix 綁定時不受影響：同一份 Layer 2 不帶綁定照舊產六段式。"""
        self.make()
        data = json.loads(self.layer2_path.read_text(encoding="utf-8"))
        with contextlib.redirect_stderr(io.StringIO()):
            seg = compiler.compile_segment_h3(data, self.registry(), auto_lora=False)
        self.assertIn("subject_definitions:", seg["h3_prompt"])
        self.assertNotIn("refmods", seg)
        self.assertNotIn("video_backend", seg["metadata"])


if __name__ == "__main__":
    unittest.main()
