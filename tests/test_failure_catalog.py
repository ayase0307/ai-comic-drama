"""失敗目錄（I8）：已知失敗要能被確定性偵測，且不誤傷正常提示詞。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.storyboard import failure_catalog as fc


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = fc.load_catalog()

    def test_default_catalog_loads_with_expected_ids(self):
        ids = {entry["id"] for entry in self.catalog["entries"]}
        for expected in ("F-RED-GLOBAL", "F-NEGATION", "F-STILL-ENDING",
                         "F-CROWD-BY-NUMBER", "F-SINGLE-FACE"):
            self.assertIn(expected, ids)

    def test_red_light_heuristic_flags_undefined_light(self):
        text = "texture: Porous charcoal volcanic stone, matte red light with no defined edge."
        result = fc.lint_text(text, self.catalog)
        self.assertIn("F-RED-GLOBAL", [item["id"] for item in result["errors"]])

    def test_red_light_with_explicit_source_is_not_flagged(self):
        text = ("A red radiance from above the crater rim lighting only the near edge of the stone; "
                "the rest of the frame keeps neutral daylight.")
        result = fc.lint_text(text, self.catalog)
        self.assertEqual([item["id"] for item in result["errors"]], [])
        self.assertEqual([item["id"] for item in result["warnings"]], [])

    def test_red_and_undefined_must_be_in_the_same_sentence(self):
        text = ("The palette includes a restrained red glow. "
                "Elsewhere the cave has no visible source of daylight.")
        result = fc.lint_text(text, self.catalog)
        self.assertNotIn("F-RED-GLOBAL", [item["id"] for item in result["errors"]])

    def test_negation_is_flagged(self):
        result = fc.lint_text("The camera does not move. no push in.", self.catalog)
        self.assertIn("F-NEGATION", [item["id"] for item in result["warnings"]])

    def test_character_motion_is_not_a_negation(self):
        # 真實語料誤報：角色的動作描述不是鏡頭指令
        result = fc.lint_text("He answers without moving, then turns away.", self.catalog)
        self.assertNotIn("F-NEGATION", [item["id"] for item in result["warnings"]])

    def test_colored_light_is_not_red_light(self):
        # 真實語料誤報："colored light" 含 "red light" 子字串
        result = fc.lint_text("add no unusual colored light, except the cold flash.", self.catalog)
        self.assertNotIn("F-RED-GLOBAL", [item["id"] for item in result["errors"]])

    def test_real_corpus_has_no_red_errors_after_repair(self):
        corpus = Path(__file__).resolve().parents[1] / "噩盡島-第一章"
        files = sorted(corpus.glob("segments-ep0*.json"))
        if not files:
            self.skipTest("找不到真實語料")
        red_hits, still_hits, segments = set(), set(), 0
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for item in data.get("segments", []):
                segments += 1
                result = fc.lint_text(item.get("h3_prompt", ""), self.catalog)
                if any(hit["id"] == "F-RED-GLOBAL" for hit in result["errors"]):
                    red_hits.add(item["segment_id"])
                if any(hit["id"] == "F-STILL-ENDING" for hit in result["warnings"]):
                    still_hits.add(item["segment_id"])
        self.assertEqual(segments, 46)
        # 2026-10-21：6 段 texture 已改成有來源的局部光，紅光條目應歸零。
        # 「偵測能力」由 test_archived_original_prompt_hits_the_red_rule 守住。
        self.assertEqual(red_hits, set())
        # 只剩「角色動作停在原地」與「鏡頭 settle 在某人身上」這 2 段仍待處理
        self.assertEqual(still_hits, {"EP01-S01-b", "EP02-S05-d"})

    def test_archived_original_prompt_hits_the_red_rule(self):
        archived = (Path(__file__).resolve().parents[1] / "噩盡島-第一章" / "review"
                    / "video-visual-diagnosis" / "held-v1-20261019-192411" / "prompts-ep01.md")
        if not archived.is_file():
            self.skipTest("找不到原始提示詞封存檔")
        text = archived.read_text(encoding="utf-8-sig")
        result = fc.lint_text(text, self.catalog)
        self.assertIn("F-RED-GLOBAL", [item["id"] for item in result["errors"]])

    def test_still_ending_is_flagged(self):
        result = fc.lint_text("She holds the lock as the frame ends.", self.catalog)
        self.assertIn("F-STILL-ENDING", [item["id"] for item in result["warnings"]])

    def test_crowd_by_number_is_flagged(self):
        result = fc.lint_text("Three students stand by the gate.", self.catalog)
        self.assertIn("F-CROWD-BY-NUMBER", [item["id"] for item in result["warnings"]])

    def test_clean_prompt_has_no_hits(self):
        text = ("The camera stays locked. Mira raises one hand; her brows slam down into a hard knot. "
                "Warm daylight from the west window keeps the palette neutral.")
        result = fc.lint_text(text, self.catalog)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["errors"], [])

    def test_empty_text_is_ignored(self):
        self.assertEqual(fc.lint_text("", self.catalog), {"errors": [], "warnings": []})

    def test_enforce_error_elevates_to_error(self):
        catalog = {"entries": [{
            "id": "T-1", "title": "test", "confidence": "measured", "enforce": "error",
            "detector": {"type": "any", "patterns": ["boom"]},
        }]}
        result = fc.lint_text("boom", catalog)
        self.assertEqual([item["id"] for item in result["errors"]], ["T-1"])

    def test_detector_types(self):
        any_cat = {"entries": [{"id": "A", "title": "a", "detector": {"type": "any", "patterns": ["x", "y"]}}]}
        all_cat = {"entries": [{"id": "B", "title": "b", "detector": {"type": "all", "patterns": ["x", "y"]}}]}
        self.assertEqual(len(fc.lint_text("x", any_cat)["warnings"]), 1)
        self.assertEqual(len(fc.lint_text("x", all_cat)["warnings"]), 0)
        self.assertEqual(len(fc.lint_text("x y", all_cat)["warnings"]), 1)

    def test_project_override_merges_by_id_and_adds_new(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "failure-catalog.json").write_text(json.dumps({"entries": [
                {"id": "F-NEGATION", "title": "覆寫版", "confidence": "measured",
                 "detector": {"type": "any", "patterns": ["never say this"]}},
                {"id": "F-NEW", "title": "專案專屬", "confidence": "inferred",
                 "detector": {"type": "any", "patterns": ["project-specific"]}},
            ]}, ensure_ascii=False), encoding="utf-8")
            catalog = fc.load_catalog(root)
        by_id = {entry["id"]: entry for entry in catalog["entries"]}
        self.assertEqual(by_id["F-NEGATION"]["title"], "覆寫版")
        self.assertIn("F-NEW", by_id)
        self.assertIn("F-RED-GLOBAL", by_id)

    def test_override_cannot_disable_builtin_entry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "failure-catalog.json").write_text(json.dumps({"entries": [
                {"id": "F-NEGATION", "disabled": True, "title": "停用",
                 "detector": {"type": "any", "patterns": ["no push in"]}},
            ]}), encoding="utf-8")
            with self.assertRaises(fc.CatalogError):
                fc.load_catalog(root)

    def test_override_cannot_downgrade_enforced_entry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "failure-catalog.json").write_text(json.dumps({"entries": [
                {"id": "F-RED-GLOBAL", "title": "降級", "enforce": "warning",
                 "detector": {"type": "all", "patterns": ["red", "no defined edge"]}},
            ]}), encoding="utf-8")
            with self.assertRaises(fc.CatalogError):
                fc.load_catalog(root)

    def test_override_can_add_project_specific_entry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "failure-catalog.json").write_text(json.dumps({"entries": [
                {"id": "F-PROJECT", "title": "本專案", "confidence": "inferred",
                 "detector": {"type": "any", "patterns": ["project-only"]}},
            ]}), encoding="utf-8")
            catalog = fc.load_catalog(root)
        self.assertIn("F-PROJECT", {entry["id"] for entry in catalog["entries"]})

    def test_exclude_is_not_over_broad(self):
        # "only the two of them" 不該讓紅光條目失效（紅光條目已無 exclude，仍要守住）
        text = "Porous stone, matte red light with no defined edge, only the two of them remain."
        result = fc.lint_text(text, self.catalog)
        self.assertIn("F-RED-GLOBAL", [item["id"] for item in result["errors"]])

    def _audit(self, prompt, **kwargs):
        from unittest import mock
        from scripts.storyboard import submit_h3_segments as submit

        seg = {"segment_id": "EP99-S01", "h3_prompt": prompt, "reference_images": []}
        passing = {"passed": True, "errors": [], "warnings": []}
        with mock.patch.object(submit, "audit_refs_and_subjects", return_value=passing), \
             mock.patch.object(submit, "lint_h3_prompt", return_value=passing):
            return submit.audit_segment_prompts([seg], **kwargs)

    def test_unacknowledged_warning_blocks_submission(self):
        ok, errors = self._audit("Shangshan completes his turn and settles.")
        self.assertFalse(ok)
        self.assertTrue(any("F-STILL-ENDING" in item and "--ack-warnings" in item for item in errors))

    def test_acknowledged_warning_allows_submission(self):
        ok, errors = self._audit("Shangshan completes his turn and settles.",
                                 ack_warnings=["F-STILL-ENDING"])
        self.assertTrue(ok, errors)

    def test_strict_catalog_blocks_even_acknowledged_warning(self):
        ok, errors = self._audit("Shangshan completes his turn and settles.",
                                 ack_warnings=["F-STILL-ENDING"], strict_catalog=True)
        self.assertFalse(ok)
        self.assertTrue(any("strict" in item for item in errors))

    def test_enforced_error_blocks_even_with_ack(self):
        ok, errors = self._audit("texture: matte red light with no defined edge.",
                                 ack_warnings=["F-RED-GLOBAL"])
        self.assertFalse(ok)
        self.assertTrue(any("F-RED-GLOBAL" in item for item in errors))

    def test_ack_requires_covers_to_be_valid(self):
        entry = {"id": "F-STILL-ENDING", "covers": {}}
        self.assertFalse(fc.ack_is_valid(entry, "EP01-S01", "deadbeef"))
        self.assertFalse(fc.ack_is_valid({"id": "X"}, "EP01-S01", "deadbeef"))

    def test_empty_pattern_is_rejected_at_load(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps({"entries": [
                {"id": "X", "title": "x", "detector": {"type": "any", "patterns": ["  "]}}
            ]}), encoding="utf-8")
            with self.assertRaises(fc.CatalogError):
                fc.load_catalog(path=bad)

    def test_string_exclude_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps({"entries": [
                {"id": "X", "title": "x",
                 "detector": {"type": "any_without", "patterns": ["red"], "exclude": "neutral"}}
            ]}), encoding="utf-8")
            with self.assertRaises(fc.CatalogError):
                fc.load_catalog(path=bad)

    def test_record_acks_is_merged_and_auditable(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            path = fc.record_acks(root, ["F-STILL-ENDING"], note="first")
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            first_seen = payload["acks"][0]["acknowledged_at"]
            fc.record_acks(root, ["F-NEGATION", "f-still-ending"], note="second")
            acks = fc.load_acks(root)
            self.assertEqual(set(acks), {"F-STILL-ENDING", "F-NEGATION"})
            self.assertEqual(acks["F-STILL-ENDING"]["acknowledged_at"], first_seen)
            self.assertEqual(acks["F-STILL-ENDING"]["note"], "second")

    def test_recorded_ack_allows_submission_without_cli_flag(self):
        import hashlib
        from scripts.storyboard import submit_h3_segments as submit

        prompt = "Shangshan completes his turn and settles."
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            fc.record_acks(root, ["F-STILL-ENDING"], note="test", covers={"EP99-S01": sha})
            seg = {"segment_id": "EP99-S01", "h3_prompt": prompt, "reference_images": []}
            passing = {"passed": True, "errors": [], "warnings": []}
            with mock.patch.object(submit, "audit_refs_and_subjects", return_value=passing), \
                 mock.patch.object(submit, "lint_h3_prompt", return_value=passing):
                ok, errors = submit.audit_segment_prompts([seg], root_dir=root)
        self.assertTrue(ok, errors)

    def test_ack_is_bound_to_the_prompt_it_covered(self):
        import hashlib
        from scripts.storyboard import submit_h3_segments as submit

        old_prompt = "Shangshan completes his turn and settles."
        new_prompt = "Shangshan completes his turn and settles. (revised)"
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            sha = hashlib.sha256(old_prompt.encode("utf-8")).hexdigest()
            fc.record_acks(root, ["F-STILL-ENDING"], covers={"EP99-S01": sha})
            seg = {"segment_id": "EP99-S01", "h3_prompt": new_prompt, "reference_images": []}
            passing = {"passed": True, "errors": [], "warnings": []}
            with mock.patch.object(submit, "audit_refs_and_subjects", return_value=passing), \
                 mock.patch.object(submit, "lint_h3_prompt", return_value=passing):
                ok, errors = submit.audit_segment_prompts([seg], root_dir=root)
        self.assertFalse(ok, "改稿後舊 ack 必須失效")
        self.assertTrue(any("F-STILL-ENDING" in item for item in errors))

    def test_ack_without_cover_hash_is_not_valid(self):
        import hashlib
        from scripts.storyboard import submit_h3_segments as submit

        prompt = "Shangshan completes his turn and settles."
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            fc.record_acks(root, ["F-STILL-ENDING"])  # 沒有 covers
            seg = {"segment_id": "EP99-S01", "h3_prompt": prompt, "reference_images": []}
            passing = {"passed": True, "errors": [], "warnings": []}
            with mock.patch.object(submit, "audit_refs_and_subjects", return_value=passing), \
                 mock.patch.object(submit, "lint_h3_prompt", return_value=passing):
                ok, errors = submit.audit_segment_prompts([seg], root_dir=root)
        self.assertFalse(ok, "沒有綁定稿件的 ack 不得放行")
        self.assertTrue(any("ack-warnings" in item for item in errors))

    def test_ack_covers_only_matching_segments(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": "Shangshan completes his turn and settles."},
                {"segment_id": "EP99-S02", "h3_prompt": "The camera stays locked. Warm daylight."},
            ]), encoding="utf-8")
            covers = fc.covers_from_segments(root, ["F-STILL-ENDING"])
        self.assertIn("EP99-S01", covers)
        self.assertNotIn("EP99-S02", covers)

    def test_covers_prefer_episode_file_over_combined(self):
        import hashlib

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            old_prompt = "Shangshan completes his turn and settles. (old combined)"
            new_prompt = "Shangshan completes his turn and settles."
            (root / "segments-all.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": old_prompt},
            ]), encoding="utf-8")
            (root / "segments-ep99.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": new_prompt},
            ]), encoding="utf-8")
            covers = fc.covers_from_segments(root, ["F-STILL-ENDING"])
        self.assertEqual(covers["EP99-S01"], hashlib.sha256(new_prompt.encode("utf-8")).hexdigest())

    def test_covers_episode_file_overrides_combined_hit(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "segments-all.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": "Shangshan completes his turn and settles."},
            ]), encoding="utf-8")
            (root / "segments-ep99.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": "The camera stays locked. Warm daylight."},
            ]), encoding="utf-8")
            covers = fc.covers_from_segments(root, ["F-STILL-ENDING"])
        self.assertEqual(covers, {}, "逐集稿已經沒有該症狀時，不該沿用合併檔的舊命中")

    def test_prune_acks_drops_stale_covers_and_empty_entries(self):
        import hashlib

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            keep = "Shangshan completes his turn and settles."
            drop = "He also settles."
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": keep},
                {"segment_id": "EP99-S02", "h3_prompt": drop},
            ]), encoding="utf-8")
            fc.record_acks(root, ["F-STILL-ENDING"], covers={
                "EP99-S01": hashlib.sha256(keep.encode("utf-8")).hexdigest(),
                "EP99-S02": hashlib.sha256(drop.encode("utf-8")).hexdigest(),
            })
            # EP99-S02 的稿改了 → 它的 cover 應被清掉；EP99-S01 保留
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": keep},
                {"segment_id": "EP99-S02", "h3_prompt": "The camera stays locked."},
            ]), encoding="utf-8")
            report = fc.prune_acks(root)
            acks = fc.load_acks(root)
        self.assertEqual(report["pruned_segments"], 1)
        self.assertEqual(set(acks["F-STILL-ENDING"]["covers"]), {"EP99-S01"})

    def test_prune_acks_removes_entry_when_all_covers_stale(self):
        import hashlib

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            text = "Shangshan completes his turn and settles."
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": text},
            ]), encoding="utf-8")
            fc.record_acks(root, ["F-STILL-ENDING"],
                           covers={"EP99-S01": hashlib.sha256(text.encode("utf-8")).hexdigest()})
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": "The camera stays locked."},
            ]), encoding="utf-8")
            report = fc.prune_acks(root)
            self.assertEqual(report["removed"], ["F-STILL-ENDING"])
            self.assertEqual(fc.load_acks(root), {})

    def test_cli_prune_acks(self):
        import hashlib

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            text = "Shangshan completes his turn and settles."
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": text},
            ]), encoding="utf-8")
            fc.record_acks(root, ["F-STILL-ENDING"],
                           covers={"EP99-S01": hashlib.sha256(text.encode("utf-8")).hexdigest()})
            with mock.patch("sys.stdout") as out:
                code = fc.main(["--root", str(root), "--prune-acks"])
            printed = "".join(c.args[0] for c in out.write.call_args_list)
        self.assertEqual(code, 0)
        self.assertIn("保留 1 條", printed)

    def test_cli_ack_writes_covers_and_revision(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            (root / "segments-ep01.json").write_text(json.dumps([
                {"segment_id": "EP99-S01", "h3_prompt": "Shangshan completes his turn and settles."},
            ]), encoding="utf-8")
            with mock.patch("sys.stdout") as out:
                code = fc.main(["--root", str(root), "--ack", "F-STILL-ENDING", "--note", "cli"])
            printed = "".join(call.args[0] for call in out.write.call_args_list)
            acks = fc.load_acks(root)
        self.assertEqual(code, 0, printed)
        self.assertIn("EP99-S01", acks["F-STILL-ENDING"]["covers"])
        self.assertEqual(acks["F-STILL-ENDING"]["catalog_rev"], fc.catalog_rev(fc.load_catalog(root)))

    def test_cli_ack_rejects_unknown_id(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td, \
             mock.patch("sys.stderr"):
            code = fc.main(["--root", td, "--ack", "F-NOT-EXIST"])
        self.assertEqual(code, 2)

    def test_cli_ack_refuses_when_nothing_matches(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td, \
             mock.patch("sys.stderr"), mock.patch("sys.stdout"):
            code = fc.main(["--root", td, "--ack", "F-STILL-ENDING"])
        self.assertEqual(code, 1)

    def test_invalid_detector_type_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps({"entries": [
                {"id": "X", "title": "x", "detector": {"type": "regex", "patterns": ["a"]}}
            ]}), encoding="utf-8")
            with self.assertRaises(fc.CatalogError):
                fc.load_catalog(path=bad)

    def test_missing_catalog_is_rejected(self):
        with self.assertRaises(fc.CatalogError):
            fc.load_catalog(path=Path("does-not-exist.json"))

    def test_cli_acks_flag_lists_recorded_acks(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            fc.record_acks(root, ["F-STILL-ENDING"], note="cli test")
            with mock.patch("sys.stdout") as out:
                code = fc.main(["--root", str(root), "--acks"])
            printed = "".join(call.args[0] for call in out.write.call_args_list)
        self.assertEqual(code, 0)
        self.assertIn("F-STILL-ENDING", printed)

    def test_cli_acks_on_empty_project(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            with mock.patch("sys.stdout") as out:
                code = fc.main(["--root", td, "--acks"])
        self.assertEqual(code, 0)
        self.assertIn("沒有任何 ack", "".join(c.args[0] for c in out.write.call_args_list))

    def test_cli_check_exit_code_follows_enforced_errors(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            clean = root / "clean.txt"
            clean.write_text("The camera stays locked. Warm daylight from the west window.",
                             encoding="utf-8")
            self.assertEqual(fc.main(["--root", str(root), "--check", str(clean)]), 0)

            bad = root / "bad.txt"
            bad.write_text("texture: matte red light with no defined edge.", encoding="utf-8")
            # 內建目錄中 F-RED-GLOBAL 是 enforce=error
            self.assertEqual(fc.main(["--root", str(root), "--check", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
