"""Layer 2 正規化層回歸測試（對應《噩盡島》第一章的 11 類實際缺陷）。"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.storyboard import normalize


def base_layer2(**overrides):
    data = {
        "segment_id": "EP01-S01-a",
        "scene_id": "SC01",
        "metadata": {"target_duration_sec": 8.0},
        "shots": [
            {
                "shot_id": "SH01",
                "start_time": 0.0,
                "end_time": 4.0,
                "duration": 4.0,
                "camera_optics": {"focal_length_mm": 50},
                "dialogue_and_audio": {
                    "has_dialogue": True,
                    "speaker": "C-A",
                    "line_verbatim": "走吧",
                    "speech_window": {"start": 1.0, "end": 3.0, "unit": "segment_seconds"},
                },
            },
            {"shot_id": "SH02", "start_time": 4.0, "end_time": 8.0, "duration": 4.0},
        ],
    }
    data.update(overrides)
    return data


class NormalizeTests(unittest.TestCase):
    def test_alias_conflict_is_an_error(self):
        data = base_layer2()
        data["shots"][0]["character_ids"] = ["C-luonien"]
        data["shots"][0]["characters"] = ["C-WRONG"]
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_props_object_is_rejected(self):
        data = base_layer2()
        data["shots"][0]["props"] = {"main": "P-pen"}
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_normalize_does_not_mutate_input(self):
        data = base_layer2()
        data["shots"][0]["dialogue_and_audio"]["speech_window"]["unit"] = "shot_seconds"
        normalizer_input = data["shots"][0]["dialogue_and_audio"]["speech_window"]
        normalize.normalize_layer2(data)
        self.assertEqual(normalizer_input["unit"], "shot_seconds")
        self.assertEqual(data["shots"][0]["dialogue_and_audio"]["speech_window"]["start"], 1.0)

    def test_real_project_corpus_has_no_errors(self):
        corpus = Path(__file__).resolve().parents[1] / "噩盡島-第一章" / "layer2"
        files = sorted(corpus.glob("*.json")) if corpus.is_dir() else []
        if not files:
            self.skipTest("找不到真實專案語料（噩盡島-第一章/layer2）")
        failures = []
        for path in files:
            try:
                # 與 compile 相同的設定（strict_aliases=False）：已知的
                # characters/character_ids 分歧記為 note，其餘問題仍要報錯。
                normalize.load_layer2(path, strict=False, strict_aliases=False)
            except normalize.NormalizationError as exc:
                failures.append(f"{path.name}: {exc}")
        self.assertEqual(failures, [], f"{len(failures)}/{len(files)} 個真實分鏡被誤殺")

    def test_real_corpus_alias_conflicts_are_still_visible(self):
        corpus = Path(__file__).resolve().parents[1] / "噩盡島-第一章" / "layer2"
        files = sorted(corpus.glob("*.json")) if corpus.is_dir() else []
        if not files:
            self.skipTest("找不到真實專案語料")
        noted = []
        for path in files:
            data = normalize.load_layer2(path, strict=False, strict_aliases=False)
            noted.extend(data["_normalization"]["notes"])
        # 2 個已知檔（EP02-S05-e、EP03-S04-a）的欄位分歧必須留下痕跡，不可靜默
        self.assertTrue(any("character_ids" in item for item in noted),
                        "真實語料的別名分歧必須留下 note")

    def test_composition_alias_is_moved_to_canonical_path(self):
        data = base_layer2()
        data["shots"][0]["composition"] = "medium shot, subject left of frame"
        result = normalize.normalize_layer2(data)
        self.assertEqual(
            result["shots"][0]["camera_optics"]["composition_start"],
            "medium shot, subject left of frame",
        )
        self.assertFalse("composition" in result["shots"][0])
        self.assertTrue(any("composition" in item for item in result["_normalization"]["aliases_applied"]))

    def test_shot_seconds_window_is_converted_to_segment_seconds(self):
        data = base_layer2()
        data["shots"][1]["dialogue_and_audio"] = {
            "has_dialogue": True,
            "speaker": "C-B",
            "line_verbatim": "好",
            "speech_window": {"start": 0.5, "end": 2.0, "unit": "shot_seconds"},
        }
        result = normalize.normalize_layer2(data)
        window = result["shots"][1]["dialogue_and_audio"]["speech_window"]
        self.assertEqual(window["unit"], "segment_seconds")
        self.assertAlmostEqual(window["start"], 4.5)
        self.assertAlmostEqual(window["end"], 6.0)

    def test_window_outside_shot_is_a_hard_error(self):
        data = base_layer2()
        data["shots"][0]["dialogue_and_audio"]["speech_window"] = {"start": 1.0, "end": 6.0}
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_window_outside_shot_can_be_downgraded_to_warning(self):
        data = base_layer2()
        data["shots"][0]["dialogue_and_audio"]["speech_window"] = {"start": 1.0, "end": 6.0}
        result = normalize.normalize_layer2(data, strict=False)
        self.assertTrue(any("speech_window" in item for item in result["_normalization"]["warnings"]))

    def test_duration_mismatch_is_an_error(self):
        data = base_layer2()
        data["shots"][0]["duration"] = 3.0
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_missing_timeline_is_an_error(self):
        data = base_layer2()
        del data["shots"][1]["start_time"]
        del data["shots"][1]["end_time"]
        del data["shots"][1]["duration"]
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_duplicate_shot_id_is_an_error(self):
        data = base_layer2()
        data["shots"][1]["shot_id"] = "sh01"
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_wardrobe_dict_is_rejected_but_list_of_dicts_is_normalized(self):
        data = base_layer2()
        data["shots"][0]["wardrobe"] = {"main": ["W-school"]}
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

        data["shots"][0]["wardrobe"] = [{"id": "W-school"}, "W-coat"]
        result = normalize.normalize_layer2(data)
        self.assertEqual(result["shots"][0]["wardrobe"], ["W-school", "W-coat"])

    def test_characters_alias_and_string_form(self):
        data = base_layer2()
        data["shots"][0]["characters"] = "C-A"
        result = normalize.normalize_layer2(data)
        self.assertEqual(result["shots"][0]["character_ids"], ["C-A"])

    def test_props_strings_become_objects(self):
        data = base_layer2()
        data["shots"][0]["props"] = ["P-pen"]
        result = normalize.normalize_layer2(data)
        self.assertEqual(result["shots"][0]["props"], [{"id": "P-pen"}])

    def test_panel_reference_requires_label(self):
        data = base_layer2(reference_images=[{"path": "board.png", "reference_view": "panel"}])
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

        data["reference_images"][0]["panel_label_en"] = "front view, top-left cell"
        result = normalize.normalize_layer2(data)
        self.assertEqual(result["reference_images"][0]["panel_label_en"], "front view, top-left cell")

    def test_missing_target_duration_is_an_error(self):
        data = base_layer2(metadata={})
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_real_world_unit_alias_is_accepted(self):
        # 真實專案用的是 seconds_segment_relative（2026-10-19 的 layer2 檔）；
        # 舊檔不可因命名不同被判非法。
        data = base_layer2()
        data["shots"][0]["dialogue_and_audio"]["speech_window"]["unit"] = "seconds_segment_relative"
        result = normalize.normalize_layer2(data)
        self.assertEqual(result["shots"][0]["dialogue_and_audio"]["speech_window"]["unit"],
                         "segment_seconds")

    def test_unknown_speech_unit_still_errors(self):
        data = base_layer2()
        data["shots"][0]["dialogue_and_audio"]["speech_window"]["unit"] = "frames"
        with self.assertRaises(normalize.NormalizationError):
            normalize.normalize_layer2(data)

    def test_timeline_gap_between_shots_is_reported(self):
        data = base_layer2()
        data["shots"][1]["start_time"] = 4.5
        data["shots"][1]["end_time"] = 8.5
        data["shots"][1]["duration"] = 4.0
        result = normalize.normalize_layer2(data)
        self.assertTrue(any("空隙" in item for item in result["_normalization"]["warnings"]))

    def test_segment_total_length_mismatch_is_reported(self):
        data = base_layer2()
        data["shots"][1]["end_time"] = 9.0
        data["shots"][1]["duration"] = 5.0
        result = normalize.normalize_layer2(data)
        self.assertTrue(any("總長" in item for item in result["_normalization"]["warnings"]))

    def test_load_layer2_rejects_missing_file_and_bad_json(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            with self.assertRaises(normalize.NormalizationError):
                normalize.load_layer2(root / "nope.json")
            bad = root / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(normalize.NormalizationError):
                normalize.load_layer2(bad)

    def test_load_layer2_accepts_bom(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            path = Path(td) / "layer2-EP01.json"
            path.write_text("\ufeff" + json.dumps(base_layer2(), ensure_ascii=False), encoding="utf-8")
            result = normalize.load_layer2(path)
            self.assertEqual(result["segment_id"], "EP01-S01-a")


if __name__ == "__main__":
    unittest.main()
