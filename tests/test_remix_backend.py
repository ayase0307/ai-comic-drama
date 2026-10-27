"""PR-R1～R3：video_backend＝remix（REMIX 角色包）。

設計原則：不刪、不改 Ref2VA 行為。這裡驗證
  R1 能力表 providers/remix.json＋h3_spec 往下取量子＋包數分級＋decisions.video_backend；
  R2 h3d bind 的 remix 分支（packs／refmods／pack_waivers／positions，缺包不寫檔）；
  R3 audit 依 backend 分支（同一份段落兩個 backend 的錯誤集合不同）。
"""
import contextlib
import io
import json
import math
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

import audit_refs_and_segments as audit  # noqa: E402
import decisions  # noqa: E402
import generate_bindings as gb  # noqa: E402
import h3_spec  # noqa: E402
import provider_caps  # noqa: E402

ANCHOR = "semi-realistic cinematic painting with muted earth tones, realistic proportions."

REMIX_PROMPT = f"""integrated_multimodal_description: {ANCHOR} <Picture 1> is the back alley location, keep its render style. <Video 1> is Hero, a young man with short black hair and a navy jacket, standing on the left. <Video 2> is Friend, a tall young man with a shaved head and a gray hoodie, standing on the right.
[Shot 1] Medium two-shot, from left to right: Hero, Friend. First Hero turns toward Friend, then he says (S1): <d>[Chinese] 我們走吧。</d> as the camera holds a static shot. Friend's lips remain closed while a warm lamp light falls from the left.
[Shot 2] At 00:03.500, close-up of Friend. First he nods, then he looks back at Hero as the camera dollies in.

overall_soundscape: Distant traffic and footsteps on wet asphalt.

non_diegetic_music: None."""


def remix_segment(**overrides):
    seg = {
        "segment_id": "EP01-S01-a",
        "metadata": {"video_backend": "remix", "target_duration_sec": 7.0, "style_anchor_en": ANCHOR},
        "refmods": [
            {"id": "S-ROOM", "pack": "demo_scene_room", "tag": "Picture", "kind": "scene", "label": "<Picture 1>"},
            {"id": "C-HERO", "pack": "demo_hero", "tag": "Video", "kind": "actor", "label": "<Video 1>"},
            {"id": "C-FRIEND", "pack": "demo_friend", "tag": "Video", "kind": "actor", "label": "<Video 2>"},
        ],
        "shots": [{"global_shot_id": "SH01", "visual_subject_ids": ["C-HERO", "C-FRIEND"]},
                  {"global_shot_id": "SH02", "visual_subject_ids": ["C-FRIEND"]}],
        "h3_prompt": REMIX_PROMPT,
    }
    seg.update(overrides)
    return seg


def codes(result):
    found = set()
    for item in result["errors"]:
        m = re.match(r"\[(E\d+\w?|E)\b", item)
        found.add(m.group(1) if m else item[:12])
    return found


# ---------------------------------------------------------------------------
# R1：能力表、量子、包數分級、decisions
# ---------------------------------------------------------------------------
class RemixCapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caps = provider_caps.load_caps("remix")

    def test_remix_caps_load_and_match_h3_spec(self):
        self.assertEqual(provider_caps.consistency_warnings(self.caps), [])
        self.assertIn("往下取", provider_caps.describe(self.caps))
        self.assertEqual(self.caps["fps"]["source"], "measured")
        self.assertEqual(self.caps["frames"]["rounding"], "floor")
        self.assertEqual(self.caps["requires_project"], {"value": True, "source": "measured",
                                                         "note": self.caps["requires_project"]["note"]})

    def test_freevideo_caps_unchanged(self):
        fv = provider_caps.load_caps()
        self.assertEqual(provider_caps.consistency_warnings(fv), [])
        self.assertNotIn("往下取", provider_caps.describe(fv))

    def test_rounding_drift_is_detected(self):
        caps = json.loads(json.dumps(self.caps))
        caps["frames"]["rounding"] = "ceil"
        self.assertTrue(any("rounding" in p for p in provider_caps.consistency_warnings(caps)))

    def test_pack_tiers_on_8gb(self):
        for count in (1, 3, 4):
            verdict = provider_caps.validate_segment({}, self.caps, refmod_count=count)
            self.assertEqual(verdict, {"errors": [], "warnings": []}, count)
        five = provider_caps.validate_segment({}, self.caps, refmod_count=5)
        self.assertFalse(five["errors"])
        self.assertTrue(any("慢" in w for w in five["warnings"]))
        six = provider_caps.validate_segment({}, self.caps, refmod_count=6)
        # 6 包只有一抽 draft 逾時，OOM 為推定 → 強烈警告而非硬擋
        self.assertFalse(six["errors"])
        self.assertTrue(any("失敗級" in w and "inferred" in w and "推定" in w for w in six["warnings"]))

    def test_fail_tier_blocks_once_it_is_measured(self):
        caps = json.loads(json.dumps(self.caps))
        caps["practical_pack_cap_by_vram"]["8GB"]["fail_source"] = "measured"
        verdict = provider_caps.validate_segment({}, caps, refmod_count=6)
        self.assertTrue(verdict["errors"])

    def test_server_max_refmods_is_docs_so_only_warns(self):
        verdict = provider_caps.validate_segment({}, self.caps, refmod_count=9)
        self.assertFalse(verdict["errors"])
        self.assertTrue(any("上限 8" in w for w in verdict["warnings"]))

    def test_project_cap_only_tightens(self):
        verdict = provider_caps.validate_segment({}, self.caps, refmod_count=4, project_pack_cap=3)
        self.assertTrue(any("remix_pack_cap=3" in e for e in verdict["errors"]))
        ok = provider_caps.validate_segment({}, self.caps, refmod_count=6, project_pack_cap=8)
        self.assertFalse(ok["errors"], "專案上限只會多擋，不會讓 6 包從警告變成放行以外的東西")
        self.assertTrue(ok["warnings"])

    def test_unmeasured_vram_tier_warns(self):
        verdict = provider_caps.validate_segment({}, self.caps, refmod_count=5, vram="24GB")
        self.assertFalse(verdict["errors"])
        self.assertTrue(any("24GB" in w for w in verdict["warnings"]))

    def test_measured_requires_project_blocks(self):
        verdict = provider_caps.validate_segment({}, self.caps, has_project=False)
        self.assertTrue(any("project" in e for e in verdict["errors"]))

    def test_modes_steps_seconds_negative(self):
        self.assertTrue(provider_caps.validate_segment({}, self.caps, mode="turbo")["warnings"])
        refine = provider_caps.validate_segment({}, self.caps, mode="refine")
        self.assertFalse(refine["errors"])
        self.assertTrue(any("沒跑過" in w for w in refine["warnings"]))
        self.assertEqual(provider_caps.validate_segment({}, self.caps, mode="single480", steps=4),
                         {"errors": [], "warnings": []})
        self.assertTrue(provider_caps.validate_segment({}, self.caps, mode="draft", steps=4)["warnings"])
        self.assertTrue(provider_caps.validate_segment({}, self.caps, mode="single480", continue_from=True)["warnings"])
        self.assertTrue(provider_caps.validate_segment({}, self.caps, seconds=11.0)["warnings"])
        self.assertTrue(provider_caps.validate_segment({}, self.caps, has_negative=True)["warnings"])
        self.assertTrue(provider_caps.validate_segment({}, self.caps, has_first_frame=True)["warnings"])

    def test_decisions_cap_range_matches_remix_caps(self):
        self.assertEqual(decisions.REMIX_MAX_REFMODS, self.caps["max_refmods"]["value"])


class QuantumRoundingTests(unittest.TestCase):
    def test_remix_floors_and_freevideo_ceils(self):
        self.assertEqual(h3_spec.server_rounding("remix"), "floor")
        self.assertEqual(h3_spec.server_rounding("freevideo"), "ceil")
        self.assertEqual(h3_spec.server_rounding(), "ceil")
        # measured：REMIX 5.5s → 124 幀；FreeVideo 11.542s → 294 幀（2026-10-19 事故）
        self.assertEqual(h3_spec.server_frames(5.5, "remix"), 124)
        self.assertEqual(h3_spec.server_frames(5.5, "freevideo"), 141)
        self.assertEqual(h3_spec.server_frames(11.542, "freevideo"), 294)
        self.assertEqual(h3_spec.server_frames(11.542, "remix"), 277)

    def test_exact_wire_seconds_round_trip_for_both_providers(self):
        for provider in ("remix", "freevideo"):
            for frames in range(22, 363, 17):
                self.assertEqual(h3_spec.server_frames(h3_spec.wire_seconds(frames), provider), frames,
                                 (provider, frames))

    def test_remix_frame_bounds(self):
        self.assertTrue(h3_spec.in_supported_range(243, "remix"))
        self.assertFalse(h3_spec.in_supported_range(260, "remix"))
        self.assertTrue(h3_spec.in_supported_range(56, "remix"))
        self.assertFalse(h3_spec.in_supported_range(39, "remix"))
        self.assertTrue(h3_spec.in_supported_range(362))  # 預設 freevideo 不變
        self.assertEqual(h3_spec.provider_spec("remix")["max_frames"], math.floor(10.125 * 24))

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            h3_spec.server_rounding("sora")
        caps = {"provider": "sora", "frames": {}, "fps": {"value": 24}}
        self.assertTrue(provider_caps.consistency_warnings(caps))


class VideoBackendDecisionTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_default_is_ref2va_and_not_required(self):
        self.assertEqual(decisions.video_backend(self.root), "ref2va")
        self.assertEqual(decisions.video_backend(None), "ref2va")
        for stage in range(8):
            self.assertNotIn("video_backend", decisions.missing_for_stage(self.root, stage))

    def test_decide_remix_and_alias(self):
        decisions.decide(self.root, "video_backend", "角色卡", "第二章改用角色卡")
        self.assertEqual(decisions.video_backend(self.root), "remix")
        decisions.decide(self.root, "video_backend", "REF2VA", "改回去")
        self.assertEqual(decisions.video_backend(self.root), "ref2va")

    def test_invalid_backend_rejected(self):
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "video_backend", "sora", "用 sora")

    def test_pack_cap_only_tightens(self):
        for bad in ("9", "0", "\"4\""):
            with self.assertRaises(decisions.DecisionError, msg=bad):
                decisions.decide(self.root, "remix_pack_cap", bad, "上限")
        decisions.decide(self.root, "remix_pack_cap", "4", "一段最多四包")
        self.assertEqual(decisions.remix_pack_cap(self.root), 4)

    def test_style_anchor(self):
        self.assertIsNone(decisions.style_anchor(self.root))
        decisions.decide(self.root, "style_anchor", ANCHOR, "錨句用這句")
        self.assertEqual(decisions.style_anchor(self.root), ANCHOR)

    def test_schema_declares_backend_enum(self):
        schema = json.loads((ROOT / "references" / "schemas" / "decisions.schema.json").read_text(encoding="utf-8"))
        rules = {r["if"]["properties"]["id"].get("const"): r for r in schema["$defs"]["decision"]["allOf"]
                 if "const" in r["if"]["properties"]["id"]}
        self.assertEqual(rules["video_backend"]["then"]["properties"]["value"]["enum"], list(decisions.VIDEO_BACKENDS))
        self.assertEqual(rules["remix_pack_cap"]["then"]["properties"]["value"]["maximum"], decisions.REMIX_MAX_REFMODS)
        self.assertIn("style_anchor", rules)


# ---------------------------------------------------------------------------
# R2：h3d bind 的 remix 分支
# ---------------------------------------------------------------------------
def run(args, cwd):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, *[str(a) for a in args]], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=240)


class RemixBindingsTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("layer2", "images", "adapt", "assets"):
            (self.root / name).mkdir()
        shots = [
            {"shot_id": "SH01", "start_time": 0.0, "end_time": 3.5, "duration": 3.5,
             "character_ids": ["C-HERO", "C-FRIEND"]},
            {"shot_id": "SH02", "start_time": 3.5, "end_time": 7.0, "duration": 3.5,
             "character_ids": ["C-HERO", "CREATURE-SNAKE"]},
        ]
        self.layer2 = self.root / "layer2" / "layer2-EP01-S01-a.json"
        self.layer2.write_text(json.dumps({
            "segment_id": "EP01-S01-a", "scene_id": "S-ROOM",
            "asset_refs": {"scene_id": "S-ROOM", "characters": [{"id": "C-HERO", "costume_id": "W-HERO-dirty"},
                                                                {"id": "C-FRIEND"}],
                           "props": [{"id": "P-SPEAR"}]},
            "metadata": {"target_duration_sec": 7, "aspect_ratio": "16:9"}, "shots": shots,
        }, ensure_ascii=False), encoding="utf-8")
        (self.root / "adapt" / "bible.json").write_text(json.dumps({"characters": [
            {"character_id": "C-HERO", "canonical_name": "Hero", "visual_prompt_en": "young man in a navy jacket"},
            {"character_id": "C-FRIEND", "canonical_name": "Friend", "visual_prompt_en": "tall man in a gray hoodie"},
            {"character_id": "CREATURE-SNAKE", "canonical_name": "Snake", "is_creature": True,
             "visual_prompt_en": "giant yellow python"}],
            "locations": [{"location_id": "S-ROOM", "name": "Room", "visual_prompt_en": "a back alley"}]},
            ensure_ascii=False), encoding="utf-8")
        self.plan = {"packs": {
            "S-ROOM": {"default": "demo_scene_room", "tag": "Picture", "kind": "scene"},
            "C-HERO": {"default": "demo_hero", "tag": "Video", "kind": "actor",
                       "costumes": {"W-HERO-dirty": {"pack": "demo_hero_dirty", "display_name": "英雄（髒）"}}},
            "C-FRIEND": {"default": "demo_friend", "tag": "Video", "kind": "actor"},
            "CREATURE-SNAKE": {"default": "demo_snake", "tag": "Video", "kind": "creature"},
            "P-SPEAR": {"default": "demo_spear", "tag": "Video", "kind": "prop"},
        }}
        decisions.decide(self.root, "video_backend", "remix", "這章用角色卡")

    def write_plan(self, plan=None):
        (self.root / "assets" / "character-packs.json").write_text(
            json.dumps(plan or self.plan, ensure_ascii=False), encoding="utf-8")

    def bind(self, *extra):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = gb.main(["--root", str(self.root), *extra])
        return code, err.getvalue()

    def load_segment(self):
        return json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))

    def test_refmods_order_labels_and_costume_variant(self):
        self.write_plan()
        code, err = self.bind()
        self.assertEqual(code, 0, err)
        data = self.load_segment()
        self.assertEqual(data["video_backend"], "remix")
        self.assertEqual(data["packs"]["S-ROOM"]["default"], "demo_scene_room")
        seg = data["segments"][0]
        self.assertEqual([r["pack"] for r in seg["refmods"]],
                         ["demo_scene_room", "demo_hero_dirty", "demo_friend", "demo_snake", "demo_spear"])
        self.assertEqual([r["label"] for r in seg["refmods"]],
                         ["<Picture 1>", "<Video 1>", "<Video 2>", "<Video 3>", "<Video 4>"])
        hero = seg["refmods"][1]
        self.assertEqual((hero["costume_id"], hero["variant_of"], hero["display_name"]),
                         ("W-HERO-dirty", "demo_hero", "英雄（髒）"))
        self.assertTrue(any("慢" in line for line in err.splitlines()), "5 包要提醒慢")
        for shot in seg["shots"]:
            for key in ("face_subject_ids", "identity_anchor_ids", "reference_paths"):
                self.assertNotIn(key, shot)
        self.assertEqual(seg["shots"][1]["pack_ids"], ["C-HERO", "CREATURE-SNAKE"])

    def test_missing_pack_lists_gap_and_writes_nothing(self):
        plan = json.loads(json.dumps(self.plan))
        del plan["packs"]["CREATURE-SNAKE"]
        del plan["packs"]["C-HERO"]["costumes"]
        self.write_plan(plan)
        code, err = self.bind()
        self.assertEqual(code, 1)
        self.assertIn("CREATURE-SNAKE", err)
        self.assertIn("W-HERO-dirty", err, "服裝變體沒登記不能退回預設包")
        self.assertIn("character-packs.json", err)
        self.assertFalse((self.root / "video-bindings.json").exists())
        self.assertFalse((self.root / "video-bible.json").exists())

    def test_missing_plan_file_is_reported(self):
        code, err = self.bind()
        self.assertEqual(code, 1)
        self.assertIn("character-packs.json", err)
        self.assertFalse((self.root / "video-bindings.json").exists())

    def test_waiver_needs_quote_and_then_skips_the_pack(self):
        plan = json.loads(json.dumps(self.plan))
        del plan["packs"]["P-SPEAR"]
        plan["waivers"] = {"EP01-S01-a": [{"id": "P-SPEAR", "reason": "6 包逾時，改文字"}]}
        self.write_plan(plan)
        code, err = self.bind()
        self.assertEqual(code, 1)
        self.assertIn("quote", err)
        plan["waivers"]["EP01-S01-a"][0]["quote"] = "銀槍不用包，文字寫就好"
        self.write_plan(plan)
        code, err = self.bind()
        self.assertEqual(code, 0, err)
        seg = self.load_segment()["segments"][0]
        self.assertNotIn("demo_spear", [r["pack"] for r in seg["refmods"]])
        self.assertEqual(seg["pack_waivers"][0]["id"], "P-SPEAR")
        self.assertFalse(any("慢" in line for line in err.splitlines()), "豁免後剩 4 包不該再警告")

    def test_pack_cap_decision_blocks(self):
        self.write_plan()
        decisions.decide(self.root, "remix_pack_cap", "4", "一段最多四包")
        code, err = self.bind()
        self.assertEqual(code, 1)
        self.assertIn("remix_pack_cap=4", err)

    def test_ref2va_only_keys_warn_and_are_dropped_on_regen(self):
        self.write_plan()
        self.assertEqual(self.bind()[0], 0)
        path = self.root / "video-bindings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        seg = data["segments"][0]
        seg["shots"][0]["face_subject_ids"] = ["C-HERO"]
        seg["positions"] = [{"id": "C-HERO", "order_lr": 1, "axis_side": "left", "facing": "right"}]
        seg["en_overlay"] = {"lighting_lock_line_en": "Grey daylight."}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, err = self.bind()
        self.assertEqual(code, 0, err)
        self.assertIn("remix 不使用", err)
        again = self.load_segment()["segments"][0]
        self.assertNotIn("face_subject_ids", again["shots"][0])
        self.assertEqual(again["positions"][0]["order_lr"], 1, "手寫 positions 要保留")
        self.assertEqual(again["en_overlay"], {"lighting_lock_line_en": "Grey daylight."})

    def test_missing_tag_is_inferred_with_warning(self):
        plan = json.loads(json.dumps(self.plan))
        plan["packs"]["C-FRIEND"] = "demo_friend"
        self.write_plan(plan)
        code, err = self.bind()
        self.assertEqual(code, 0, err)
        self.assertIn("推定", err)
        friend = next(r for r in self.load_segment()["segments"][0]["refmods"] if r["id"] == "C-FRIEND")
        self.assertEqual((friend["tag"], friend.get("tag_inferred")), ("Video", True))

    def test_ref2va_flag_overrides_decision(self):
        self.write_plan()
        code, _ = self.bind("--backend", "ref2va")
        self.assertEqual(code, 1, "ref2va 分支沒有設定圖，照舊列缺口")
        self.assertFalse((self.root / "video-bindings.json").exists())

    def test_compiler_refuses_remix_bindings_until_r5(self):
        self.write_plan()
        self.assertEqual(self.bind()[0], 0)
        result = run([ROOT / "scripts" / "storyboard" / "compile_layer2_to_h3.py", "--layer2", "layer2/",
                      "--bible", "video-bible.json", "--bindings", "video-bindings.json",
                      "--project-root", ".", "--skip-stage-gate"], self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PR-R5", result.stderr)


# ---------------------------------------------------------------------------
# R3：audit 依 backend 分支
# ---------------------------------------------------------------------------
class RemixAuditTests(unittest.TestCase):
    def test_valid_remix_segment_passes(self):
        res = audit.audit_refs_and_subjects(remix_segment())
        self.assertEqual(res["backend"], "remix")
        self.assertEqual(res["errors"], [])
        lint = audit.lint_h3_prompt(REMIX_PROMPT, nominal_duration=7.0, backend="remix")
        self.assertFalse([e for e in lint["errors"] if e.startswith("[E1")], lint["errors"])

    def test_same_fixture_gives_different_error_sets_per_backend(self):
        seg = remix_segment()
        # 給 ref2va 一份它看得懂的參考圖欄位：兩張可辨識臉＋一位未錨定的在場人物
        seg["reference_images"] = [
            {"id": "S-ROOM", "type": "scene", "path": "images/S-ROOM.png"},
            {"id": "C-HERO", "type": "character", "path": "images/hero.png"},
            {"id": "C-FRIEND", "type": "character", "path": "images/friend.png"},
        ]
        seg["unanchored_in_frame_characters"] = ["CREATURE-SNAKE"]
        ref2va = audit.audit_refs_and_subjects(seg, backend="ref2va")
        remix = audit.audit_refs_and_subjects(seg, backend="remix")
        self.assertIn("E19", codes(ref2va))
        self.assertTrue(any("混臉" in w for w in ref2va["warnings"]))
        self.assertNotIn("E19", codes(remix))
        self.assertIn("E50", codes(remix))
        self.assertFalse(any("混臉" in w for w in remix["warnings"]))
        self.assertNotEqual(codes(ref2va), codes(remix))

    def test_ref2va_result_is_unchanged_without_backend(self):
        seg = remix_segment()
        del seg["metadata"]["video_backend"]
        del seg["refmods"]
        seg["reference_images"] = [{"id": "C-HERO", "type": "character", "path": "images/hero.png"}]
        self.assertEqual(audit.audit_refs_and_subjects(seg), audit.audit_refs_and_subjects(seg, backend="ref2va"))

    def test_tag_numbering_must_match_refmods(self):
        extra = remix_segment(h3_prompt=REMIX_PROMPT.replace(
            "standing on the right.", "standing on the right. <Video 3> is a stranger."))
        self.assertTrue(any("<Video 3>" in e for e in audit.audit_refs_and_subjects(extra)["errors"]))
        unused = remix_segment(h3_prompt=REMIX_PROMPT.replace("<Video 2> is Friend", "Friend is"))
        self.assertTrue(any("沒有被引用" in e for e in audit.audit_refs_and_subjects(unused)["errors"]))
        seg = remix_segment()
        seg["refmods"][2]["label"] = "<Video 3>"
        self.assertTrue(any("標籤順序錯" in e for e in audit.audit_refs_and_subjects(seg)["errors"]))
        seg = remix_segment()
        seg["refmods"][1]["tag"] = None
        self.assertIn("E52", codes(audit.audit_refs_and_subjects(seg)))

    def test_scene_pack_must_be_first(self):
        seg = remix_segment()
        seg["refmods"] = [seg["refmods"][1], seg["refmods"][0], seg["refmods"][2]]
        for ref in seg["refmods"]:
            ref.pop("label")
        self.assertIn("E53", codes(audit.audit_refs_and_subjects(seg)))

    def test_e50_named_character_without_pack_and_waiver(self):
        seg = remix_segment()
        seg["shots"][1]["visual_subject_ids"] = ["C-FRIEND", "CREATURE-SNAKE"]
        self.assertIn("E50", codes(audit.audit_refs_and_subjects(seg)))
        seg["pack_waivers"] = [{"id": "CREATURE-SNAKE", "reason": "改文字"}]
        self.assertTrue(any("原話" in e for e in audit.audit_refs_and_subjects(seg)["errors"]))
        seg["pack_waivers"][0]["quote"] = "蛇不用包"
        self.assertEqual(audit.audit_refs_and_subjects(seg)["errors"], [])

    def test_e55_style_anchor(self):
        seg = remix_segment()
        seg["metadata"].pop("style_anchor_en")
        self.assertIn("E55", codes(audit.audit_refs_and_subjects(seg)))
        seg["metadata"]["style_anchor_en"] = "Cinematic live-action film shot, photorealistic."
        res = audit.audit_refs_and_subjects(seg)
        self.assertTrue(any("開頭不是風格錨" in e for e in res["errors"]))

    def test_e55_reads_anchor_from_decisions(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            seg = remix_segment()
            seg["metadata"].pop("style_anchor_en")
            decisions.decide(Path(td), "style_anchor", "  " + ANCHOR.upper() + " ", "錨句")
            self.assertEqual(audit.audit_refs_and_subjects(seg, project_root=Path(td))["errors"], [])

    def test_e21_wider_crowd_cues_only_in_remix(self):
        prompt = REMIX_PROMPT.replace("close-up of Friend.", "close-up of Friend while students pass behind him.")
        seg = remix_segment(h3_prompt=prompt)
        self.assertIn("E21", codes(audit.audit_refs_and_subjects(seg)))
        ratio = REMIX_PROMPT.replace("close-up of Friend.", "close-up of Friend, as tall as the others.")
        self.assertNotIn("E21", codes(audit.audit_refs_and_subjects(remix_segment(h3_prompt=ratio))))
        seg["refmods"].append({"id": "EXTRAS-STUDENTS", "pack": "demo_students", "tag": "Video", "kind": "extras"})
        seg["h3_prompt"] = prompt.replace("standing on the right.", "standing on the right. <Video 3> is the students.")
        self.assertNotIn("E21", codes(audit.audit_refs_and_subjects(seg)))
        ref2va_seg = {"segment_id": "x", "reference_images": [], "h3_prompt": prompt.replace(
            "integrated_multimodal_description", "detailed_description")}
        self.assertNotIn("E21", codes(audit.audit_refs_and_subjects(ref2va_seg, backend="ref2va")))

    def test_e54_pack_count(self):
        seg = remix_segment()
        extra = [{"id": f"P-{i}", "pack": f"demo_p{i}", "tag": "Video", "kind": "prop"} for i in range(3)]
        seg["refmods"] = seg["refmods"] + extra
        lines = "".join(f" <Video {n}> is prop {n}." for n in (3, 4, 5))
        seg["h3_prompt"] = REMIX_PROMPT.replace("standing on the right.", "standing on the right." + lines)
        res = audit.audit_refs_and_subjects(seg)
        self.assertEqual(res["errors"], [])
        self.assertTrue(any(w.startswith("[E54") and "推定" in w for w in res["warnings"]))
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            decisions.decide(Path(td), "remix_pack_cap", "5", "最多五包")
            self.assertIn("E54", codes(audit.audit_refs_and_subjects(seg, project_root=Path(td))))

    def test_shared_gates_still_apply_in_remix(self):
        no_speaker = remix_segment(h3_prompt=REMIX_PROMPT.replace("(S1)", ""))
        self.assertIn("E22", codes(audit.audit_refs_and_subjects(no_speaker)))
        echo = remix_segment(h3_prompt=REMIX_PROMPT.replace(
            "Distant traffic", "我們走吧。 Distant traffic"))
        self.assertIn("E25", codes(audit.audit_refs_and_subjects(echo)))

    def test_backend_resolution_order(self):
        self.assertEqual(audit.resolve_backend({}), "ref2va")
        self.assertEqual(audit.resolve_backend({"refmods": []}), "remix")
        self.assertEqual(audit.resolve_backend({"metadata": {"video_backend": "ref2va"}, "refmods": []}), "ref2va")
        self.assertEqual(audit.resolve_backend({"refmods": []}, backend="ref2va"), "ref2va")

    def test_audit_cli_with_backend_flag(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
            path = Path(td) / "segments-remix.json"
            path.write_text(json.dumps({"segments": [remix_segment()]}, ensure_ascii=False), encoding="utf-8")
            ok = run([ROOT / "scripts" / "storyboard" / "audit_refs_and_segments.py", "--audit-refs", path,
                      "--backend", "remix"], ROOT)
            self.assertEqual(ok.returncode, 0, ok.stdout[-2000:])
            seg = remix_segment()
            seg["refmods"].pop()
            path.write_text(json.dumps(seg, ensure_ascii=False), encoding="utf-8")
            bad = run([ROOT / "scripts" / "storyboard" / "audit_refs_and_segments.py", "--audit-refs", path], ROOT)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("E52", bad.stdout)


if __name__ == "__main__":
    unittest.main()
