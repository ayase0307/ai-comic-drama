"""階段 4–5 體檢（fix/audit-stage4-5）的回歸測試。

每個 class 對應一個修正：骨架 ID 對聖經、裁切框可設定、bind 的 backend 切換與輸入指紋、
階段 5 strict 門禁（漏編／落後／失敗目錄／backend 不符）、自動核准跑審核頁門禁、模板佔位不進提示詞、
refcheck「other people」、validate_storyboard 多集 handoff 與段間接縫、6d 不再用寫死名單的子字串。
路徑一律用含中文與空白的暫存目錄，順便驗證不依賴家機路徑。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STORYBOARD = SCRIPTS / "storyboard"
for extra in (SCRIPTS, STORYBOARD):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import auto_approve  # noqa: E402
import generate_bindings as gb  # noqa: E402
import handoff_to_skeleton as skel  # noqa: E402
import next_step  # noqa: E402
import project_state as ps  # noqa: E402
import refcheck  # noqa: E402
import validate_storyboard as vs  # noqa: E402
from compile_layer2_to_h3 import AssetRegistry  # noqa: E402

PY = sys.executable


def run(args, cwd):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([PY, *[str(a) for a in args]], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=600)


class TmpProject(unittest.TestCase):
    """含中文與空白的專案路徑。"""

    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "測試 專案"
        for name in ("layer2", "images", "adapt", "assets"):
            (self.root / name).mkdir(parents=True)

    def write(self, rel, payload):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
        path.write_text(text, encoding="utf-8")
        return path

    def png(self, rel, size=(64, 64)):
        from PIL import Image
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (90, 90, 90)).save(path)
        return path


BIBLE = {
    "characters": [
        {"character_id": "C-linyu", "canonical_name": "林雨", "aliases": ["小雨"], "name_en": "Lin Yu",
         "visual_prompt_en": "young woman with black hair", "reference_image": "images/C-linyu.png"},
        {"character_id": "C-chenmo", "canonical_name": "陳默", "name_en": "Chen Mo",
         "visual_prompt_en": "thin man with round glasses", "reference_image": "images/C-chenmo.png"},
    ],
    "locations": [{"location_id": "S-bookstore", "name": "舊書店", "visual_prompt_en": "an old bookstore",
                   "reference_image": "images/S-bookstore.png"}],
    "props": [{"prop_id": "P-letter", "name": "信", "description": "letter"}],
}


# ---------------------------------------------------------------------------
# 1. handoff_to_skeleton：中文名對到聖經 ID
# ---------------------------------------------------------------------------
class SkeletonBibleIdTests(TmpProject):
    def _handoff(self, characters):
        handoff = json.loads((ROOT / "references/adapt/templates/handoff.schema.json").read_text(encoding="utf-8"))
        del handoff  # 只確認檔案在；下面用最小合法 handoff
        scene = {
            "project_id": "demo", "episode_id": "EP01", "scene_id": "EP01-S01", "source_refs": ["U01"],
            "adaptation_mode": "balanced", "setting": {"location": "舊書店", "time": "night", "interior": True},
            "characters": characters, "scene_goal": "找信", "dramatic_turn": "信不見了",
            "action_beats": ["小雨推門進入"],
            "dialogue": [{"speaker": "陳默", "text": "昨天被拿走了。", "audio_type": "onscreen"}],
            "props": ["信"], "continuity_initial": {}, "continuity_final": {},
            "estimated_duration_seconds": {"min": 5, "max": 10}, "adaptation_changes": [],
            "storyboard_handoff": {"required_visual_beats": [], "required_audio_beats": [], "must_preserve": []},
        }
        return self.write("handoff-ep01.json", {
            "project_id": "demo", "rights_status": "unconfirmed", "adaptation_mode": "balanced",
            "genre_mode": "healing_literary", "aspect_ratio": "9:16", "target_medium": "ai_animation",
            "episodes": [{"episode_id": "EP01", "title": "t", "episode_goal": "g",
                          "act_out_type": "jeopardy_cliffhanger", "scenes": [scene]}]})

    def test_names_and_aliases_map_to_bible_ids(self):
        self.write("adapt/bible.json", BIBLE)
        handoff = self._handoff(["小雨", "陳默"])
        result = run([STORYBOARD / "handoff_to_skeleton.py", handoff, "--out-dir", self.root / "layer2"], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.root / "layer2" / "layer2-EP01-S01.json").read_text(encoding="utf-8"))
        ids = [c["id"] for c in data["asset_refs"]["characters"]]
        self.assertEqual(ids, ["C-linyu", "C-chenmo"])
        self.assertEqual(data["asset_refs"]["scene_id"], "S-bookstore")
        self.assertEqual(data["asset_refs"]["props"], ["P-letter"])
        self.assertNotIn("聖經裡找不到", result.stderr)

    def test_unknown_name_warns_and_bible_none_keeps_old_hash(self):
        self.write("adapt/bible.json", BIBLE)
        handoff = self._handoff(["路人甲", "陳默"])
        result = run([STORYBOARD / "handoff_to_skeleton.py", handoff, "--out-dir", self.root / "layer2"], self.root)
        self.assertIn("聖經裡找不到「路人甲」", result.stderr)
        legacy = run([STORYBOARD / "handoff_to_skeleton.py", handoff, "--out-dir", self.root / "legacy",
                      "--bible", "none"], self.root)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        data = json.loads((self.root / "legacy" / "layer2-EP01-S01.json").read_text(encoding="utf-8"))
        self.assertTrue(all(c["id"].startswith("C-x") for c in data["asset_refs"]["characters"]),
                        "--bible none 維持舊的雜湊 ID")

    def test_load_bible_ids_skips_template_placeholders(self):
        path = self.write("adapt/bible.json", {"characters": [
            {"character_id": "C-protagonist", "canonical_name": "<角色名>", "aliases": ["<主角別名>"]}]})
        ids = skel.load_bible_ids(path)
        self.assertNotIn(("C", "<角色名>"), ids)
        self.assertEqual(ids[("C", "C-protagonist")], "C-protagonist")


# ---------------------------------------------------------------------------
# 3. 裁切框（950×910 定案）可設定、crop --px、提示指令可直接執行
# ---------------------------------------------------------------------------
class CropBoxTests(TmpProject):
    def test_default_box_is_the_measured_950x910_head_cell(self):
        x0, y0, x1, y1 = (float(v) for v in gb.FACE_PANEL_BOX.split(","))
        self.assertEqual((round(x1 * 2560), round(y1 * 1440)), (950, 910))

    def test_plan_override_and_absolute_hint(self):
        self.assertEqual(gb.face_crop_box({"face_crop_box": "0,0,0.5,0.5"}), "0,0,0.5,0.5")
        self.assertEqual(gb.face_crop_box({"face_crop_box": "0,0,0.5,0.5"}, {"face_crop_box": [0, 0, 0.3, 0.4]}),
                         "0,0,0.3,0.4", "角色計畫優先於頂層")
        hint = gb._crop_hint("images/a b.png", "C-x", "0,0,0.5,0.5")
        self.assertIn(str((SCRIPTS / "h3d.py").as_posix()), hint)
        self.assertIn('"images/a b.png"', hint)
        self.assertIn("--box 0,0,0.5,0.5", hint)

    def test_crop_px_relative_paths_and_images_guard(self):
        from PIL import Image
        self.png("images/sheet.png", (2560, 1440))
        ok = run([SCRIPTS / "h3d.py", "crop", "--root", self.root, "--image", "images/sheet.png",
                  "--px", "0,0,950,910", "--out-dir", "assets/crops", "--prefix", "hero"], ROOT)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        with Image.open(self.root / "assets" / "crops" / "hero-crop1.png") as im:
            self.assertEqual(im.size, (950, 910))
        blocked = run([SCRIPTS / "h3d.py", "crop", "--root", self.root, "--image", "images/sheet.png",
                       "--px", "0,0,950,910", "--out-dir", "images/crops"], ROOT)
        self.assertEqual(blocked.returncode, 2, "images/ 底下的子資料夾也不行（會讓階段 2 快照失效）")
        out_of_range = run([SCRIPTS / "h3d.py", "crop", "--root", self.root, "--image", "images/sheet.png",
                            "--px", "0,0,3000,910", "--out-dir", "assets/crops"], ROOT)
        self.assertEqual(out_of_range.returncode, 1)


# ---------------------------------------------------------------------------
# 4. h3d bind：remix 預設服裝、remix→ref2va 切換、逐鏡判讀鍵、輸入指紋
# ---------------------------------------------------------------------------
class BindTests(TmpProject):
    def setUp(self):
        super().setUp()
        self.png("images/C-linyu.png")
        self.png("images/C-chenmo.png")
        self.png("images/S-bookstore.png", (1344, 768))
        self.write("adapt/bible.json", BIBLE)
        self.layer2 = self.write("layer2/layer2-EP01-S01-a.json", {
            "segment_id": "EP01-S01-a", "scene_id": "EP01-S01",
            "asset_refs": {"scene_id": "S-bookstore", "characters": [
                {"id": "C-linyu", "costume_id": "W-linyu-01"}, {"id": "C-chenmo", "costume_id": "W-chenmo-01"}]},
            "metadata": {"target_duration_sec": 7, "aspect_ratio": "16:9"},
            "shots": [{"shot_id": "SH01", "global_shot_id": "EP01-S01-a-SH01", "character_ids": ["C-linyu", "C-chenmo"]},
                      {"shot_id": "SH02", "global_shot_id": "EP01-S01-a-SH02", "character_ids": ["C-linyu"]}]})
        self.packs = {"packs": {
            "S-bookstore": {"default": "demo_scene", "tag": "Picture", "kind": "scene"},
            "C-linyu": {"default": "demo_linyu", "tag": "Video", "kind": "actor", "default_costume": "W-linyu-01"},
            "C-chenmo": {"default": "demo_chenmo", "tag": "Video", "kind": "actor", "default_costume": ["W-chenmo-01"]}}}

    def bindings(self):
        return json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))

    def test_remix_default_costume_needs_no_variant_pack(self):
        self.write("assets/character-packs.json", self.packs)
        self.assertEqual(gb.main(["--root", str(self.root), "--backend", "remix"]), 0)
        refmods = self.bindings()["segments"][0]["refmods"]
        linyu = next(r for r in refmods if r["id"] == "C-linyu")
        self.assertEqual((linyu["pack"], linyu["costume_id"]), ("demo_linyu", "W-linyu-01"))

    def test_remix_unregistered_costume_still_blocks_with_hint(self):
        del self.packs["packs"]["C-linyu"]["default_costume"]
        self.write("assets/character-packs.json", self.packs)
        self.assertEqual(gb.main(["--root", str(self.root), "--backend", "remix"]), 1)
        self.assertFalse((self.root / "video-bindings.json").exists())

    def test_switching_back_to_ref2va_drops_remix_fields(self):
        self.write("assets/character-packs.json", self.packs)
        self.assertEqual(gb.main(["--root", str(self.root), "--backend", "remix"]), 0)
        data = self.bindings()
        data["segments"][0]["positions"] = [{"id": "C-linyu", "order_lr": 1}]
        data["segments"][0]["en_overlay"] = {"lighting_lock_line_en": "Cold rain light."}
        self.write("video-bindings.json", data)
        self.write("assets/character-reference-plans.json", {"characters": {
            "C-linyu": {"default": {"face_crop": "images/C-linyu.png"}},
            "C-chenmo": {"default": {"face_crop": "images/C-chenmo.png"}}}})
        self.assertEqual(gb.main(["--root", str(self.root), "--backend", "ref2va"]), 0)
        data = self.bindings()
        self.assertNotIn("video_backend", data)
        self.assertNotIn("packs", data)
        seg = data["segments"][0]
        for key in ("refmods", "video_backend", "pack_waivers"):
            self.assertNotIn(key, seg)
        self.assertNotIn("pack_ids", seg["shots"][0])
        self.assertEqual(seg["positions"], [{"id": "C-linyu", "order_lr": 1}], "positions 兩個 backend 都用，保留")
        self.assertEqual(seg["en_overlay"], {"lighting_lock_line_en": "Cold rain light."})

    def test_visibility_key_segment_slash_shot_id(self):
        visibility = {"EP01-S01-a/SH01": {"C-chenmo": "back"}, "EP01-S01-a/SH02": {"C-linyu": "face"}}
        shots = json.loads(self.layer2.read_text(encoding="utf-8"))["shots"]
        states = gb.segment_states("EP01-S01-a", shots, visibility)
        self.assertEqual(states.get("C-chenmo"), "back", "文件寫的 segment_id/shot_id 鍵要認得")

    def test_plan_change_marks_bindings_stale(self):
        self.write("assets/character-reference-plans.json", {"characters": {
            "C-linyu": {"default": {"face_crop": "images/C-linyu.png"}},
            "C-chenmo": {"default": {"face_crop": "images/C-chenmo.png"}}}})
        self.assertEqual(gb.main(["--root", str(self.root)]), 0)
        self.assertIsNone(gb.bindings_stale(self.root))
        self.write("assets/face-visibility.json", {"shots": {"EP01-S01-a/SH01": {"C-chenmo": "back"}}})
        reason = gb.bindings_stale(self.root)
        self.assertIn("face-visibility.json", reason or "")
        self.assertTrue(any("輸入" in e for e in ps._stage5_freshness_errors(self.root, [])))


# ---------------------------------------------------------------------------
# 5. 階段 5 strict：漏編、提示詞落後、失敗目錄未處置、backend 不符
# ---------------------------------------------------------------------------
class Stage5StrictTests(TmpProject):
    def setUp(self):
        super().setUp()
        self.l1 = self.write("layer2/layer2-EP01-S01.json", {"segment_id": "EP01-S01", "shots": [{"shot_id": "A"}]})
        self.l2 = self.write("layer2/layer2-EP02-S01.json", {"segment_id": "EP02-S01", "shots": [{"shot_id": "A"}]})

    def seg_file(self, name, segs):
        return self.write(name, {"segments": segs})

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_missing_episode_is_reported(self):
        f = self.seg_file("segments-ep01.json", [{"segment_id": "EP01-S01", "metadata": {}}])
        errors = ps._stage5_freshness_errors(self.root, [f])
        self.assertTrue(any("EP02-S01" in e and "缺少" in e for e in errors), errors)

    def test_stale_prompt_after_layer2_edit(self):
        f = self.seg_file("segments-ep01.json", [
            {"segment_id": "EP01-S01", "metadata": {"source_layer2_sha256": self.sha(self.l1)}},
            {"segment_id": "EP02-S01", "metadata": {"source_layer2_sha256": self.sha(self.l2)}}])
        self.assertEqual(ps._stage5_freshness_errors(self.root, [f]), [])
        self.l1.write_text(self.l1.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        errors = ps._stage5_freshness_errors(self.root, [f])
        self.assertTrue(any("落後於分鏡" in e and "EP01-S01" in e for e in errors), errors)

    def test_legacy_segments_without_fingerprint_are_not_flagged(self):
        f = self.seg_file("segments-ep01.json", [{"segment_id": "EP01-S01"}, {"segment_id": "EP02-S01"}])
        self.assertEqual(ps._stage5_freshness_errors(self.root, [f]), [])

    def test_stale_bindings(self):
        f = self.seg_file("segments-ep01.json", [{"segment_id": "EP01-S01"}, {"segment_id": "EP02-S01"}])
        self.write("video-bindings.json", {"segments": [
            {"source_layer2_path": "layer2/layer2-EP01-S01.json", "source_sha256": "0" * 64},
            {"source_layer2_path": "layer2/layer2-EP02-S01.json", "source_sha256": self.sha(self.l2)}]})
        errors = ps._stage5_freshness_errors(self.root, [f])
        self.assertTrue(any("綁定落後" in e and "EP01-S01" in e for e in errors), errors)
        command, _ = next_step.stage5_producer(self.root, errors)
        self.assertIn("bind", command)

    def test_remix_decision_with_ref2va_segments_stops(self):
        f = self.seg_file("segments-ep01.json", [{"segment_id": "EP01-S01"}, {"segment_id": "EP02-S01"}])
        self.write("decisions.json", {"schema_version": 1, "decisions": [
            {"id": "video_backend", "rule": "r", "value": "remix", "source": {"quote": "q", "date": "2026-10-27"},
             "stages": [5]}]})
        errors = ps._stage5_freshness_errors(self.root, [f])
        remix = [e for e in errors if "video_backend=remix" in e]
        self.assertTrue(remix, errors)
        command, action = next_step.stage5_producer(self.root, remix)
        # PR-R5 起 compile 會產 REMIX 三欄：還沒有 remix 綁定 → 先 bind
        self.assertIn("bind", command)
        self.assertIn("refmods", action)
        # 已有新鮮的 remix 綁定 → 照常給 compile 指令（帶 --bindings）
        self.write("video-bible.json", {})
        self.write("video-bindings.json", {"video_backend": "remix", "segments": [
            {"source_layer2_path": "layer2/layer2-EP01-S01.json", "source_sha256": self.sha(self.l1), "refmods": []},
            {"source_layer2_path": "layer2/layer2-EP02-S01.json", "source_sha256": self.sha(self.l2), "refmods": []}]})
        command, _ = next_step.stage5_producer(self.root, remix)
        self.assertIn("compile", command)
        self.assertIn("--bindings video-bindings.json", command)

    def test_unacked_catalog_warning_blocks_and_ack_clears_it(self):
        # 綁定新鮮（綁定落後時改稿重編前要先 bind，next 會先給 bind；這裡只驗目錄分支）
        self.write("video-bible.json", {})
        self.write("video-bindings.json", {"segments": [
            {"source_layer2_path": "layer2/layer2-EP01-S01.json", "source_sha256": self.sha(self.l1)},
            {"source_layer2_path": "layer2/layer2-EP02-S01.json", "source_sha256": self.sha(self.l2)}]})
        self.write("segments-ep01.json", {"segments": [{"segment_id": "EP01-S01",
                   "h3_prompt": "detailed_description: She walks to the window and comes to a stop."}]})
        errors = ps._stage5_catalog_errors(self.root)
        self.assertTrue(any("F-STILL-ENDING" in e for e in errors), errors)
        command, _ = next_step.stage5_producer(self.root, errors)
        self.assertIn("catalog", command)
        ack = run([SCRIPTS / "h3d.py", "ack", "F-STILL-ENDING", "--root", self.root, "--note", "使用者接受"], ROOT)
        self.assertEqual(ack.returncode, 0, ack.stdout + ack.stderr)
        self.assertEqual(ps._stage5_catalog_errors(self.root), [])
        # 改稿後 ack 失效
        self.write("segments-ep01.json", {"segments": [{"segment_id": "EP01-S01",
                   "h3_prompt": "detailed_description: She walks to the cold window and comes to a stop."}]})
        self.assertTrue(ps._stage5_catalog_errors(self.root))


# ---------------------------------------------------------------------------
# 6. 自動核准階段 4 也要過審核頁門禁（TODO 分鏡不能自動過）
# ---------------------------------------------------------------------------
class AutoApproveReviewGateTests(TmpProject):
    def test_stage4_builder_errors_block(self):
        self.write("layer2/layer2-EP01-S01.json", {
            "segment_id": "EP01-S01", "scene_id": "EP01-S01",
            "shots": [{"shot_id": "SH01", "start_time": 0, "end_time": 3, "duration": 3,
                       "action_and_performance": {"observable_expression": "TODO：之後再寫"}}]})
        errors = auto_approve._review_builder_errors(self.root, 4, ps.load_state(self.root))
        self.assertTrue(errors)


# ---------------------------------------------------------------------------
# 7. assets.md 模板佔位不進提示詞
# ---------------------------------------------------------------------------
class PlaceholderStyleTests(TmpProject):
    def test_template_placeholders_are_ignored(self):
        assets = self.write("assets.md", "## 風格錨點\n"
                            "- **style_anchor**：`<全片共用風格，例：3D donghua, cel-shaded, soft rim light>`\n"
                            "- **style_negative**：`<不要出現的特徵>`\n"
                            "- **lighting_lock_line**：`Cold blue rain light.`\n")
        bible = self.write("video-bible.json", {"style": {"anchor": "<全片共用風格>", "negative": "no text"}})
        registry = AssetRegistry(bible_path=bible, assets_path=assets, project_root=self.root)
        self.assertNotIn("style_anchor", registry.style)
        self.assertEqual(registry.style.get("lighting_lock_line"), "Cold blue rain light.")
        self.assertEqual(registry.style.get("style_negative"), "no text")


# ---------------------------------------------------------------------------
# 8. refcheck：肯定句 other people 要報、否定句不報
# ---------------------------------------------------------------------------
class RefcheckOtherPeopleTests(unittest.TestCase):
    ANCHOR = "Painterly semi-realistic donghua."

    def _seg(self, sentence):
        prompt = (f"integrated_multimodal_description: {self.ANCHOR} <Picture 1> is the bookstore. "
                  f"<Video 1> is Lin Yu. [Shot 1] Lin Yu reads at the counter. {sentence}\n\n"
                  f"overall_soundscape: Rain.\n\nnon_diegetic_music: None.")
        return {"segment_id": "EP01-S01", "metadata": {"video_backend": "remix", "style_anchor_en": self.ANCHOR},
                "refmods": [{"id": "S-bookstore", "pack": "s", "tag": "Picture", "kind": "scene", "label": "<Picture 1>"},
                            {"id": "C-linyu", "pack": "l", "tag": "Video", "kind": "actor", "label": "<Video 1>"}],
                "h3_prompt": prompt}

    def test_affirmative_other_people_is_e51(self):
        result = refcheck.check_segment(self._seg("Other people browse the shelves behind her."), {}, backend="remix")
        self.assertIn("people", result["unbound_people"])

    def test_negated_other_people_is_fine(self):
        for sentence in ("There are no other people in the shop.", "The shop is quiet without other people."):
            result = refcheck.check_segment(self._seg(sentence), {}, backend="remix")
            self.assertEqual(result["unbound_people"], [], sentence)


# ---------------------------------------------------------------------------
# 9. validate_storyboard：多集 handoff、段間接縫 D05、6d 名單
# ---------------------------------------------------------------------------
class ValidateStoryboardTests(TmpProject):
    def test_seam_warning_between_adjacent_segments(self):
        shot = {"camera_optics": {"shot_size": "MS", "movement": "static"}}
        datas = [{"segment_id": "EP01-S01-b", "scene_id": "S1", "shots": [shot]},
                 {"segment_id": "EP01-S01-a", "scene_id": "S1", "shots": [shot]}]
        seams = vs.check_segment_seams(datas)
        self.assertEqual(len(seams), 1)
        self.assertTrue(seams[0].startswith("EP01-S01-a→EP01-S01-b"))

    def test_segment_anchor_names(self):
        data = {"asset_refs": {"characters": [{"id": "C-a", "name": "林雨"}]},
                "metadata": {"anchored_names": ["陳默"]}}
        self.assertEqual(vs._segment_anchor_names(data), ["林雨", "陳默"])
        self.assertIsNone(vs._PLACEHOLDER_ROLE_RE.search("ARRI camera, BG plate"),
                          "大寫 A／B 出現在單字裡不算點名角色")
        self.assertIsNotNone(vs._PLACEHOLDER_ROLE_RE.search("角色A 推門"))

    def test_multi_handoff_cli(self):
        def handoff(ep, sid):
            return {"project_id": "demo", "rights_status": "unconfirmed", "adaptation_mode": "balanced",
                    "genre_mode": "healing_literary", "aspect_ratio": "16:9", "target_medium": "ai_animation",
                    "episodes": [{"episode_id": ep, "title": "t", "episode_goal": "g", "act_out_type": "comic_topper",
                                  "scenes": [{"scene_id": sid, "dialogue": [{"speaker": "A", "text": "走吧。",
                                                                             "audio_type": "onscreen"}]}]}]}
        self.write("handoff-ep01.json", handoff("EP01", "EP01-S01"))
        self.write("handoff-ep02.json", handoff("EP02", "EP02-S01"))
        for sid in ("EP01-S01", "EP02-S01"):
            self.write(f"layer2/layer2-{sid}.json", {"segment_id": sid, "scene_id": sid, "shots": [
                {"shot_id": "SH01", "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "走吧。"}}]})
        result = run([STORYBOARD / "validate_storyboard.py", "--file", "layer2/*.json",
                      "--handoff", "handoff-ep*.json"], self.root)
        payload = json.loads(result.stdout)
        self.assertEqual(set(payload["dialogue_checks"]), {"EP01-S01", "EP02-S01"})
        self.assertTrue(all(v["passed"] for v in payload["dialogue_checks"].values()), payload["dialogue_checks"])


if __name__ == "__main__":
    unittest.main()
