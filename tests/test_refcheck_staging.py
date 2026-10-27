"""PR-R4＋R6：h3d refcheck（參考包涵蓋）與 h3d staging（站位／視線／運鏡閘門）。

fixture 是照《噩盡島》ch02 EP04 抽次提示詞改寫的精簡版（人名換成通用名，只留決定規則的句子）：
  - S04-a t1（三人鏡只有各自「on the left／far right」，沒寫左到右 → 左右對調 warn）vs t2（補「left to right: …」→ pass）；
  - S04-b t1（兩人並肩對鏡、整段沒有視線句 → fail）vs t3（eyes on her face → pass）；
  - S01-a／c 寫了巨蟒、銀槍卻沒有包（refcheck 擋）。
設計原則：不改 Ref2VA 既有門禁；refcheck 在 ref2va 只提示、staging 預設全部警告。
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "tests"))

import audit_refs_and_segments as audit  # noqa: E402
import decisions  # noqa: E402
import h3d  # noqa: E402
import refcheck  # noqa: E402
import staging_lint as sl  # noqa: E402

ANCHOR = "semi-realistic cinematic painting with muted earth tones, realistic proportions."
STRIP = r"Style lock for every shot:.*?not a photograph\."


def prompt(body: str) -> str:
    return (f"integrated_multimodal_description: {ANCHOR} {body} Style lock for every shot: painted look with "
            f"crowds of brush strokes, not a photograph.\n\noverall_soundscape: Alley ambience; people chatter far "
            f"away.\n\nnon_diegetic_music: N/A")


INTROS3 = ("<Picture 1> is the alley location, keep its render style. "
           "<Video 1> is Mei Lin, a slender girl with long black hair in a white blouse, on the far right, facing left. "
           "<Video 2> is Teacher Wu, a man with thin glasses in a light blue shirt, on the left, facing right. "
           "<Video 3> is Kai Chen, a tall boy with short hair and a tube backpack, center-right beside Mei Lin, facing left.")
REFMODS3 = [
    {"id": "S-ALLEY", "pack": "demo_scene_alley", "tag": "Picture", "kind": "scene", "label": "<Picture 1>"},
    {"id": "C-MEI", "pack": "demo_mei", "tag": "Video", "kind": "actor", "label": "<Video 1>"},
    {"id": "C-WU", "pack": "demo_wu", "tag": "Video", "kind": "actor", "label": "<Video 2>"},
    {"id": "C-KAI", "pack": "demo_kai", "tag": "Video", "kind": "actor", "label": "<Video 3>"},
]
# S04-a t1：只有 intro 的各自畫面側，動作句沒有左到右
S04A_T1 = prompt(
    f"[Shot 1] A narrow concrete alley in warm sunlight. {INTROS3} Medium three-shot at eye level; the camera trucks "
    f"right from Teacher Wu toward Kai Chen. First Teacher Wu leans in with narrowed eyes on Mei Lin. Teacher Wu (S1) "
    f"says: <d>[Chinese] 是宗教團體嗎？</d> Then Kai Chen tilts his head and grins at Teacher Wu. "
    f"[Shot 2] At 00:03.800, medium two-shot of Mei Lin and Kai Chen from a lower angle; the camera pushes in on Mei "
    f"Lin: she turns sharply to glare at Kai Chen, while Teacher Wu watches. Mei Lin (S2) says: <d>[Chinese] 你別說話啦！</d>")
# S04-a t2：補上左到右名單與畫面側
S04A_T2 = prompt(
    f"[Shot 1] A narrow concrete alley in warm sunlight. {INTROS3} Medium three-shot at eye level, left to right: "
    f"Teacher Wu, Kai Chen, Mei Lin; the camera trucks right from Teacher Wu toward Kai Chen. First Teacher Wu leans in "
    f"with narrowed eyes on Mei Lin. Teacher Wu (S1) says: <d>[Chinese] 是宗教團體嗎？</d> Then Kai Chen tilts his head "
    f"and grins at Teacher Wu. [Shot 2] At 00:03.800, medium two-shot from a lower angle with Kai Chen on frame left "
    f"and Mei Lin on frame right; the camera pushes in on Mei Lin: she turns sharply to glare at Kai Chen; at the left "
    f"edge of frame Teacher Wu watches. Mei Lin (S2) says: <d>[Chinese] 你別說話啦！</d>")

INTROS2 = ("<Picture 1> is the alley location, keep its render style. "
           "<Video 1> is Teacher Wu, a man with thin glasses and a cool gaze, on the left. "
           "<Video 2> is Mei Lin, a slender girl with long black hair, on the right.")
REFMODS2 = [REFMODS3[0], dict(REFMODS3[2], label="<Video 1>"), dict(REFMODS3[1], label="<Video 2>")]
# S04-b t1：兩人並肩、沒有視線句（intro 的 cool gaze 不算）
S04B_T1 = prompt(
    f"[Shot 1] Medium shot at eye level; {INTROS2} From the first frame Teacher Wu is adjusting his glasses as the "
    f"camera holds a static shot. Teacher Wu (S1) says: <d>[Chinese] 加入要繳錢嗎？</d> At the same time Mei Lin's "
    f"eyes widen; her lips remain closed. [Shot 2] At 00:03.000, medium close-up of Mei Lin; she frowns hard as the "
    f"camera pushes in. Mei Lin (S2) says: <d>[Chinese] 我們不是騙人的團體！</d>")
S04B_T3 = S04B_T1.replace("is adjusting his glasses as", "leans toward her cautiously, eyes on her face, as")


def seg(h3_prompt, refmods=None, **extra):
    data = {"segment_id": extra.pop("segment_id", "EP04-S04-a"), "metadata": {"video_backend": "remix",
            "style_anchor_en": ANCHOR}, "refmods": REFMODS3 if refmods is None else refmods, "h3_prompt": h3_prompt}
    data.update(extra)
    return data


def codes(findings):
    return [f["code"] for f in findings]


# ---------------------------------------------------------------------------
# R4 refcheck
# ---------------------------------------------------------------------------
class RefcheckProject(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self._tmp.name)
        (self.root / "adapt").mkdir()
        (self.root / "assets").mkdir()
        bible = {
            "characters": [
                {"id": "C-MEI", "name": "梅琳", "name_en": "Mei Lin"},
                {"id": "C-WU", "name": "吳老師", "name_en": "Teacher Wu", "aliases_en": ["the teacher"]},
                {"id": "C-KAI", "name": "陳凱", "name_en": "Kai Chen"},
                {"id": "CREATURE-PYTHON", "name": "黃色巨蟒", "is_creature": True,
                 "aliases_en": ["python", "serpent", "snake", "carcass", "worm"]},
            ],
            "locations": [{"id": "S-ALLEY", "name": "後巷", "aliases_en": ["service alley"]}],
            "props": [{"id": "P-SPEAR", "name": "銀槍", "alias_patterns_en": [r"\bspear(?:head)?\b", r"three-section staff"]}],
        }
        (self.root / "adapt" / "bible.json").write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
        plan = {"packs": {"S-ALLEY": {"default": "demo_scene_alley", "tag": "Picture", "kind": "scene"},
                          "C-MEI": "demo_mei", "C-WU": "demo_wu",
                          "C-KAI": {"default": "demo_kai", "costumes": {"W02": "demo_kai_dirty"}},
                          "CREATURE-PYTHON": {"default": "demo_python", "kind": "creature"},
                          "P-SPEAR": {"default": "demo_spear", "kind": "prop"},
                          "EXTRAS-DINERS": {"default": "demo_diners", "kind": "extras", "aliases_en": ["diners"]}},
                "refcheck": {"strip_patterns": [STRIP], "generic_en": ["handkerchief", "tray"]}}
        (self.root / "assets" / "character-packs.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        self.plan = refcheck.load_pack_plan(self.root)
        self.lex = refcheck.load_lexicon(self.root, self.plan)

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, segment, backend="remix"):
        return refcheck.check_segment(segment, self.lex, backend, self.plan, [ANCHOR])


class RefcheckTests(RefcheckProject):
    def test_lexicon_from_bible_and_pack_plan(self):
        self.assertIn("Mei Lin", self.lex["C-MEI"]["terms"])
        self.assertNotIn("梅琳", self.lex["C-MEI"]["terms"], "中文名不參與英文提示詞比對")
        self.assertEqual(self.lex["C-KAI"]["packs"], {"demo_kai", "demo_kai_dirty"})
        self.assertEqual(self.lex["P-SPEAR"]["kind"], "prop")
        self.assertEqual(self.lex["EXTRAS-DINERS"]["kind"], "extras")

    def test_clean_segment_passes(self):
        res = self.check(seg(S04A_T2))
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual({h["id"] for h in res["hits"]}, {"C-MEI", "C-WU", "C-KAI"})

    def test_unbound_creature_and_prop_are_e50(self):
        body = S04A_T2.replace("Then Kai Chen tilts", "Behind them the python carcass lies coiled; Kai Chen grips "
                                                       "the spear. Then Kai Chen tilts")
        res = self.check(seg(body))
        self.assertFalse(res["ok"])
        self.assertTrue(res["errors"][0].startswith("[E50"))
        self.assertTrue(any(m.startswith("CREATURE-PYTHON") for m in res["missing"]))
        self.assertTrue(any(m.startswith("P-SPEAR") for m in res["missing"]))

    def test_worm_alias_hits_same_pack(self):
        res = self.check(seg(S04A_T2.replace("Then Kai Chen tilts", "A pale worm wriggles. Then Kai Chen tilts")))
        self.assertTrue(any(m.startswith("CREATURE-PYTHON") for m in res["missing"]))

    def test_costume_variant_pack_counts_as_covered(self):
        refmods = [dict(r) for r in REFMODS3]
        refmods[3] = {"pack": "demo_kai_dirty", "tag": "Video", "kind": "actor", "label": "<Video 3>"}
        self.assertTrue(self.check(seg(S04A_T2, refmods))["ok"])

    def test_presence_list_missing_is_e50(self):
        res = self.check(seg(S04A_T2, REFMODS3[:3]))
        self.assertTrue(any(m.startswith("C-KAI") for m in res["missing"]))

    def test_waiver_needs_quote(self):
        body = S04A_T2.replace("Then Kai Chen tilts", "Kai Chen grips the spear. Then Kai Chen tilts")
        ok = self.check(seg(body, pack_waivers=[{"id": "P-SPEAR", "reason": "6 包逾時", "quote": "先拿掉銀槍"}]))
        self.assertTrue(ok["ok"], ok["errors"])
        self.assertEqual(ok["waived"], ["P-SPEAR"])
        bad = self.check(seg(body, pack_waivers=[{"id": "P-SPEAR", "reason": "6 包逾時"}]))
        self.assertFalse(bad["ok"])
        self.assertTrue(any("豁免缺原話" in e for e in bad["errors"]))

    def test_plan_level_waiver(self):
        self.plan["waivers"] = {"EP04-S04-a": [{"pack": "demo_spear", "quote": "先拿掉銀槍"}]}
        body = S04A_T2.replace("Then Kai Chen tilts", "Kai Chen grips the spear. Then Kai Chen tilts")
        self.assertTrue(self.check(seg(body))["ok"])

    def test_unbound_people_e51_and_exemptions(self):
        res = self.check(seg(S04A_T2.replace("Then Kai Chen tilts", "Students watch from the windows. Then Kai Chen tilts")))
        self.assertFalse(res["ok"])
        self.assertTrue(any(e.startswith("[E51") for e in res["errors"]))
        for safe in ("Kai Chen is as tall as the others.", "Only these three people are in frame.",
                     "Blurred silhouettes of students pass far behind."):
            r = self.check(seg(S04A_T2.replace("Then Kai Chen tilts", f"{safe} Then Kai Chen tilts")))
            self.assertEqual(r["unbound_people"], [], safe)
        with_extras = self.check(seg(S04A_T2.replace("Then Kai Chen tilts", "Students watch. Then Kai Chen tilts"),
                                     REFMODS3 + [{"id": "EXTRAS-DINERS", "pack": "demo_diners", "tag": "Video",
                                                  "kind": "extras", "label": "<Video 4>"}]))
        self.assertEqual(with_extras["unbound_people"], [])
        waived = self.check(seg(S04A_T2.replace("Then Kai Chen tilts", "Students watch. Then Kai Chen tilts"),
                                pack_waivers=[{"id": "E51", "quote": "學生遠景可以"}]))
        self.assertEqual(waived["unbound_people"], [])

    def test_soundscape_and_style_lock_are_ignored(self):
        # overall_soundscape 有 people、Style lock 有 crowds，都不算畫面內容
        self.assertEqual(self.check(seg(S04A_T2))["unbound_people"], [])

    def test_generic_objects_listed_only(self):
        res = self.check(seg(S04A_T2.replace("Then Kai Chen tilts", "Mei Lin holds a handkerchief. Then Kai Chen tilts")))
        self.assertTrue(res["ok"])
        self.assertEqual(res["generic"], ["handkerchief"])

    def test_ref2va_only_hints(self):
        body = S04A_T2.replace("Then Kai Chen tilts", "Kai Chen grips the spear. Then Kai Chen tilts")
        res = self.check(seg(body), backend="ref2va")
        self.assertTrue(res["ok"])
        self.assertEqual(res["errors"], [])
        self.assertTrue(any(w.startswith("[E50") and "ref2va 只提示" in w for w in res["warnings"]))

    def test_ref2va_reference_images_count_as_coverage(self):
        s = {"segment_id": "EP01-S01-a", "h3_prompt": prompt("[Shot 1] Mei Lin waits as the camera holds a static shot."),
             "reference_images": [{"id": "C-MEI", "type": "character", "path": "refs/mei.png"}]}
        self.assertEqual(self.check(s, backend="ref2va")["warnings"], [])

    def test_missing_english_names_is_flagged(self):
        s = seg(S04A_T2, shots=[{"visual_subject_ids": ["C-NONAME"]}])
        res = self.check(s)
        self.assertTrue(any("refcheck 詞表" in w for w in res["warnings"]))

    def write_segments(self, segments):
        path = self.root / "segments-ep04.json"
        path.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
        return path

    def run_h3d(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = h3d.main(list(args))
        return code, out.getvalue()

    def test_cli_exit_codes(self):
        bad = S04A_T2.replace("Then Kai Chen tilts", "Kai Chen grips the spear. Then Kai Chen tilts")
        self.write_segments([seg(S04A_T2), seg(bad, segment_id="EP04-S04-b")])
        code, out = self.run_h3d("refcheck", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("REFCHECK：1/2", out)
        code, out = self.run_h3d("refcheck", "--root", str(self.root), "--backend", "ref2va")
        self.assertEqual(code, 0, "ref2va 只提示，不擋")
        self.write_segments([seg(S04A_T2)])
        code, out = self.run_h3d("refcheck", "--root", str(self.root), "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)[0]["ok"])

    def test_cli_fills_refmods_from_bindings(self):
        s = seg(S04A_T2)
        del s["refmods"]
        self.write_segments([s])
        (self.root / "video-bindings.json").write_text(json.dumps(
            {"video_backend": "remix", "segments": [{"segment_id": "EP04-S04-a", "refmods": REFMODS3}]}), encoding="utf-8")
        self.assertEqual(self.run_h3d("refcheck", "--root", str(self.root))[0], 0)

    def test_takes_snapshot_mode(self):
        (self.root / "takes").mkdir()
        (self.root / "takes" / "t1.txt").write_text(
            S04A_T2.replace("Then Kai Chen tilts", "Kai Chen grips the spear. Then Kai Chen tilts"), encoding="utf-8")
        lines = [{"key": "EP04-S04-a_t1", "prompt_file": "takes/t1.txt",
                  "packs": ["demo_scene_alley", "demo_mei", "demo_wu", "demo_kai"]},
                 {"key": "EP04-S04-a_t2", "prompt": S04A_T2,
                  "packs": ["demo_scene_alley", "demo_mei", "demo_wu", "demo_kai"]}]
        (self.root / "queue.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        code, out = self.run_h3d("refcheck", "--root", str(self.root), "--takes", "queue.jsonl")
        self.assertEqual(code, 1)
        self.assertIn("FAIL EP04-S04-a_t1", out)
        self.assertIn("OK   EP04-S04-a_t2", out)

    def test_audit_remix_uses_text_match_when_lexicon_exists(self):
        decisions.decide(self.root, "style_anchor", ANCHOR, "錨句用這句")
        body = S04A_T2.replace("Then Kai Chen tilts", "Kai Chen grips the spear. Then Kai Chen tilts")
        res = audit.audit_refs_and_subjects(seg(body), project_root=self.root)
        self.assertTrue(any(e.startswith("[E50") and "P-SPEAR" in e for e in res["errors"]), res["errors"])
        clean = audit.audit_refs_and_subjects(seg(S04A_T2), project_root=self.root)
        self.assertFalse([e for e in clean["errors"] if e.startswith("[E50")], clean["errors"])

    def test_audit_ref2va_is_untouched_by_refcheck(self):
        s = {"segment_id": "EP01-S01-a", "h3_prompt": prompt("[Shot 1] Kai Chen grips the spear as the camera holds a static shot."),
             "reference_images": [{"id": "C-KAI", "type": "character", "path": "refs/kai.png"}]}
        res = audit.audit_refs_and_subjects(s, project_root=self.root, backend="ref2va")
        self.assertFalse(any(x.startswith(("[E50", "[E51", "[D0", "[D1")) for x in res["errors"] + res["warnings"]))


# ---------------------------------------------------------------------------
# R6 staging
# ---------------------------------------------------------------------------
class StagingTests(unittest.TestCase):
    def lint(self, segment, backend="remix", **kw):
        return sl.lint_segment(segment, backend, **kw)

    def test_s04a_t1_flagged_t2_passes(self):
        self.assertIn("D08", codes(self.lint(seg(S04A_T1))))
        t2 = self.lint(seg(S04A_T2))
        self.assertNotIn("D08", codes(t2))
        self.assertEqual([f for f in t2 if f["code"] != "D14"], [], t2)

    def test_two_person_shot_with_sides_passes(self):
        body = prompt(f"[Shot 1] {INTROS2} Medium two-shot with Teacher Wu on frame left and Mei Lin on frame right; "
                      f"the camera holds a static shot as Teacher Wu looks at Mei Lin. Teacher Wu (S1) says: <d>[Chinese] 走。</d> "
                      f"[Shot 2] At 00:03.000, medium two-shot of Teacher Wu and Mei Lin; the camera pushes in as she nods.")
        found = codes(self.lint(seg(body, REFMODS2)))
        self.assertIn("D08", found, "第二鏡明寫雙人構圖、卻沒有畫面側")
        self.assertEqual(found.count("D08"), 1)

    def test_s04b_t1_missing_gaze_t3_passes(self):
        self.assertIn("D07", codes(self.lint(seg(S04B_T1, REFMODS2))))
        self.assertNotIn("D07", codes(self.lint(seg(S04B_T3, REFMODS2))))

    def test_single_person_dialogue_needs_no_gaze(self):
        body = prompt("[Shot 1] <Video 1> is Mei Lin, a slender girl. Close-up of Mei Lin as the camera holds a static "
                      "shot. Mei Lin (S1) says: <d>[Chinese] 好。</d> [Shot 2] At 00:03.000, she nods as the camera pushes in.")
        self.assertNotIn("D07", codes(self.lint(seg(body, [REFMODS3[1] | {"label": "<Video 1>"}]))))

    def test_facing_camera_and_negation(self):
        bad = S04A_T2.replace("she turns sharply to glare at Kai Chen", "she turns to face the camera")
        self.assertIn("D06", codes(self.lint(seg(bad))))
        self.assertIn("D06", codes(self.lint(seg(S04A_T2.replace("grins at Teacher Wu", "grins straight at the lens")))))
        neg = S04A_T2.replace("grins at Teacher Wu", "grins at Teacher Wu, never looking at the camera")
        self.assertNotIn("D06", codes(self.lint(seg(neg))))
        back = S04A_T2.replace("grins at Teacher Wu", "grins at Teacher Wu with his back to the camera")
        self.assertNotIn("D06", codes(self.lint(seg(back))))

    def test_facing_camera_waiver_needs_quote(self):
        bad = S04A_T2.replace("she turns sharply to glare at Kai Chen", "she turns to face the camera")
        ok = seg(bad)
        ok["metadata"]["staging_waivers"] = [{"code": "D06", "reason": "刻意對鏡頭", "quote": "這句讓她對鏡頭說"}]
        self.assertNotIn("D06", codes(self.lint(ok)))
        no_quote = seg(bad)
        no_quote["metadata"]["staging_waivers"] = [{"code": "D06", "reason": "刻意對鏡頭"}]
        found = self.lint(no_quote)
        self.assertEqual(codes(found).count("D06"), 2)
        self.assertTrue(any("豁免缺原話" in f["message"] for f in found))

    def test_positions_mismatch_d09_and_toward(self):
        positions = [{"id": "C-WU", "order_lr": 1}, {"id": "C-MEI", "order_lr": 2}, {"id": "C-KAI", "order_lr": 3}]
        self.assertIn("D09", codes(self.lint(seg(S04A_T2, positions=positions))))
        good = [{"id": "C-WU", "order_lr": 1}, {"id": "C-KAI", "order_lr": 2}, {"id": "C-MEI", "order_lr": 3, "facing": "toward"}]
        found = codes(self.lint(seg(S04A_T2, positions=good)))
        self.assertNotIn("D09", found)
        self.assertNotIn("D14", found)
        self.assertIn("D06", found)

    def test_cross_segment_flip_d10(self):
        a = seg(S04A_T2, segment_id="EP04-S04-a", scene_id="EP04-S04",
                positions=[{"id": "C-KAI", "order_lr": 1}, {"id": "C-MEI", "order_lr": 2}])
        b = seg(S04A_T2, segment_id="EP04-S04-b", scene_id="EP04-S04",
                positions=[{"id": "C-MEI", "order_lr": 1}, {"id": "C-KAI", "order_lr": 2}])
        self.assertIn("D10", codes(self.lint(b, prev=a)))
        b["metadata"]["staging_reset"] = "S04-b 換到反打軸，先給大全景重建空間"
        self.assertNotIn("D10", codes(self.lint(b, prev=a)))
        other_scene = dict(b, scene_id="EP04-S05")
        other_scene["metadata"] = {"video_backend": "remix"}
        rows = sl.lint_segments([a, other_scene], lambda s: "remix")
        self.assertNotIn("D10", codes(rows[1]["findings"]), "換場不比站位")

    def test_sync_slow_and_static(self):
        body = S04A_T2.replace("Then Kai Chen tilts his head", "All three of them look up slowly. Then Kai Chen tilts his head")
        found = codes(self.lint(seg(body)))
        self.assertIn("D11", found)
        self.assertIn("D12", found)
        static = (S04A_T2.replace("the camera trucks right from Teacher Wu toward Kai Chen", "the camera holds a static shot")
                  .replace("the camera pushes in on Mei Lin", "the camera holds a static shot"))
        self.assertIn("D13", codes(self.lint(seg(static))))
        self.assertNotIn("D13", codes(self.lint(seg(S04A_T2))))

    def test_backend_difference_d14_only_remix(self):
        self.assertIn("D14", codes(self.lint(seg(S04A_T2), "remix")))
        self.assertNotIn("D14", codes(self.lint(seg(S04A_T2), "ref2va")))
        # 其餘規則兩個 backend 一樣
        self.assertIn("D08", codes(self.lint(seg(S04A_T1), "ref2va")))

    def test_default_is_warning_and_strict_escalates_measured_only(self):
        body = S04A_T1.replace("Then Kai Chen tilts his head", "All three of them look up. Then Kai Chen tilts his head")
        default = self.lint(seg(body))
        self.assertTrue(all(f["level"] == "warning" for f in default))
        strict = self.lint(seg(body), strict=True)
        levels = {f["code"]: f["level"] for f in strict}
        self.assertEqual(levels["D08"], "error")
        self.assertEqual(levels["D11"], "warning", "inferred 規則 strict 也只警告")

    def test_existing_remix_fixture_has_no_staging_noise(self):
        from test_remix_backend import remix_segment
        found = [f for f in self.lint(remix_segment()) if f["code"] != "D14"]
        self.assertEqual(found, [])


class StagingProjectTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self._tmp.name)
        (self.root / "segments-ep04.json").write_text(json.dumps({"segments": [seg(S04A_T1)]}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_h3d(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = h3d.main(list(args))
        return code, out.getvalue()

    def test_decision_value_is_validated(self):
        with self.assertRaises(decisions.DecisionError):
            decisions.decide(self.root, "staging_gate", "hard", "擋")
        self.assertEqual(decisions.staging_gate(self.root), "warn")
        decisions.decide(self.root, "staging_gate", "strict", "站位沒寫就擋")
        self.assertEqual(decisions.staging_gate(self.root), "strict")

    def test_cli_default_warns_strict_blocks(self):
        code, out = self.run_h3d("staging", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("D08", out)
        self.assertEqual(self.run_h3d("staging", "--root", str(self.root), "--strict")[0], 1)
        decisions.decide(self.root, "staging_gate", "strict", "站位沒寫就擋")
        self.assertEqual(self.run_h3d("staging", "--root", str(self.root))[0], 1)

    def test_audit_remix_carries_staging_findings(self):
        decisions.decide(self.root, "style_anchor", ANCHOR, "錨句")
        res = audit.audit_refs_and_subjects(seg(S04A_T1), project_root=self.root)
        self.assertTrue(any(w.startswith("[D08") for w in res["warnings"]))
        self.assertFalse(any(e.startswith("[D08") for e in res["errors"]))
        decisions.decide(self.root, "staging_gate", "strict", "站位沒寫就擋")
        res = audit.audit_refs_and_subjects(seg(S04A_T1), project_root=self.root)
        self.assertTrue(any(e.startswith("[D08") for e in res["errors"]))

    def test_h3d_lists_new_commands(self):
        code, out = self.run_h3d("--list")
        self.assertIn("refcheck", out)
        self.assertIn("staging", out)


if __name__ == "__main__":
    unittest.main()
