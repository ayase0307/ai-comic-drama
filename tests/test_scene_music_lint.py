"""C4 同場配樂跟著生成段走（抖音蒸餾 2026-10 A 批 #1）：同場相鄰段配樂不同或非 N/A 就警告，不擋。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import continuity_lint  # noqa: E402


def _six(sid, scene, music):
    """六段式提示詞（non_diegetic_music 換行後接內容，後面不再有區塊）。"""
    return {
        "segment_id": sid, "scene_id": scene,
        "h3_prompt": (
            "detailed_description:\n[Shot 1] CU of Shen.\n\n"
            "overall_soundscape:\nrain on the roof\n\n"
            f"non_diegetic_music:\n{music}\n"
        ),
    }


def _remix(sid, scene, music):
    """REMIX 三欄（non_diegetic_music: 同一行）。"""
    return {
        "segment_id": sid, "scene_id": scene,
        "h3_prompt": (
            "integrated_multimodal_description: Shen stands.\n\n"
            "overall_soundscape: wind\n\n"
            f"non_diegetic_music: {music}\n"
        ),
    }


def _c4(compiled):
    return [w for w in continuity_lint.lint_adjacent(compiled)["warnings"] if "[C4" in w]


class SceneMusicLintTests(unittest.TestCase):
    def test_music_text_reads_both_formats(self):
        self.assertEqual(continuity_lint.music_text(_six("a", "S", "Low cello drone.")["h3_prompt"]), "Low cello drone.")
        self.assertEqual(continuity_lint.music_text(_remix("a", "S", "N/A")["h3_prompt"]), "N/A")
        self.assertEqual(continuity_lint.music_text("detailed_description:\n[Shot 1] x"), "")

    def test_music_block_in_middle_stops_at_next_section(self):
        prompt = "non_diegetic_music:\nSoft piano.\n\nsubject_definitions:\n<Subject 1> is Shen."
        self.assertEqual(continuity_lint.music_text(prompt), "Soft piano.")

    def test_no_music_variants(self):
        for text in ("", "N/A", "n/a", "NA", "None.", "no music", "  "):
            self.assertTrue(continuity_lint.is_no_music(text), text)
        self.assertFalse(continuity_lint.is_no_music("Soft piano, no vocals."))

    def test_all_na_in_scene_is_quiet(self):
        self.assertEqual(_c4([_six("EP01-S01-a", "ROOM", "N/A"), _six("EP01-S01-b", "ROOM", ""),
                              _remix("EP01-S01-c", "ROOM", "N/A")]), [])

    def test_different_music_in_adjacent_segments_warns(self):
        w = _c4([_six("EP01-S01-a", "ROOM", "Low cello drone."), _six("EP01-S01-b", "ROOM", "Upbeat trap beat.")])
        self.assertEqual(len(w), 1, w)
        self.assertIn("EP01-S01-b", w[0])
        self.assertIn("描述不同", w[0])

    def test_one_side_music_warns(self):
        w = _c4([_six("EP01-S01-a", "ROOM", "N/A"), _remix("EP01-S01-b", "ROOM", "Soft piano.")])
        self.assertEqual(len(w), 1, w)

    def test_identical_music_still_warns(self):
        w = _c4([_six("EP01-S01-a", "ROOM", "Soft piano."), _six("EP01-S01-b", "ROOM", "Soft piano.")])
        self.assertEqual(len(w), 1, w)
        self.assertIn("兩段都寫了配樂", w[0])

    def test_scene_boundary_and_single_segment_scene_do_not_warn(self):
        compiled = [_six("EP01-S01-a", "ROOM", "N/A"), _six("EP01-S02-a", "ROOF", "Epic choir.")]
        self.assertEqual(_c4(compiled), [])

    def test_order_follows_segment_ids_not_input_order(self):
        compiled = [_six("EP01-S01-c", "ROOM", "N/A"), _six("EP01-S01-a", "ROOM", "N/A"),
                    _six("EP01-S01-b", "ROOM", "Soft piano.")]
        w = _c4(compiled)
        self.assertEqual(len(w), 2, w)  # a→b、b→c 兩個接縫
        self.assertTrue(w[0].startswith("EP01-S01-b"))
        self.assertTrue(w[1].startswith("EP01-S01-c"))

    def test_warning_does_not_block(self):
        res = continuity_lint.lint_adjacent([_six("EP01-S01-a", "ROOM", "A."), _six("EP01-S01-b", "ROOM", "B.")])
        self.assertEqual(set(res), {"warnings"})


if __name__ == "__main__":
    unittest.main()
