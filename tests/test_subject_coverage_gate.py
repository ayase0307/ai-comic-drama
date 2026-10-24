import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
import prompt_authoring as pa  # noqa: E402


def seg(refs, shots, subjects, blocks):
    prompt = "subject_definitions:\n" + "\n".join(subjects) + "\n\ndetailed_description:\n" + "\n\n".join(blocks)
    return {"segment_id": "EP01-S01-a", "h3_prompt": prompt,
            "reference_images": [{"id": r} for r in refs], "shots": shots}


SKETCH = ("Reference images, in attachment order: <Picture 1> = 沈洛年 (C-shen-luonian); "
          "<Picture 2> = 凱布利 (CREATURE-kaibuli); <Picture 3> = scene 地窖 (S-cellar).")


class SubjectCoverageGate(unittest.TestCase):
    def test_creature_in_sketch_but_unbound_is_error(self):
        s = seg(["S-cellar", "C-shen-luonian"],
                [{"shot_id": "SH01", "character_ids": [], "sketch_prompt": SKETCH}],
                ["<Subject 1> is the character in <Picture 2> (C-shen-luonian; crop)"],
                ["[Shot 1] <Subject 1> lies on the bed; a black shell mass in front."])
        errs = pa.audit_subject_coverage(s)
        self.assertTrue(any("E40" in e and "CREATURE-kaibuli" in e for e in errs), errs)

    def test_bound_but_not_named_in_shot_is_error(self):
        s = seg(["S-cellar", "CREATURE-kaibuli", "C-shen-luonian"],
                [{"shot_id": "SH01", "character_ids": ["CREATURE-kaibuli", "C-shen-luonian"], "sketch_prompt": SKETCH}],
                ["<Subject 1> is the large side view of <Picture 2>, beetle",
                 "<Subject 2> is the character in <Picture 3> (C-shen-luonian; crop)"],
                ["[Shot 1] <Subject 1> crouches; the bed with a red-robed figure."])
        errs = pa.audit_subject_coverage(s)
        self.assertTrue(any("E41" in e and "C-shen-luonian" in e for e in errs), errs)
        self.assertFalse(any("CREATURE-kaibuli" in e for e in errs), errs)

    def test_fully_covered_and_waived_passes(self):
        s = seg(["S-cellar", "CREATURE-kaibuli", "C-shen-luonian"],
                [{"shot_id": "SH01", "character_ids": ["CREATURE-kaibuli", "C-shen-luonian"], "sketch_prompt": SKETCH},
                 {"shot_id": "SH02", "character_ids": ["C-ailu"], "accepted_unbound_subject_ids": ["C-ailu"]},
                 {"shot_id": "SH03", "character_ids": [], "sketch_prompt": SKETCH,
                  "offscreen_subject_ids": ["CREATURE-kaibuli", "C-shen-luonian"]}],
                ["<Subject 1> is the large side view of <Picture 2>, beetle",
                 "<Subject 2> is the character in <Picture 3> (C-shen-luonian; crop)"],
                ["[Shot 1] <Subject 1> crouches before <Subject 2>.", "[Shot 2] a silhouette.", "[Shot 3] stairs."])
        self.assertEqual(pa.audit_subject_coverage(s), [])

    def test_extras_and_ref_filenames_map_to_ids(self):
        shot = {"sketch_generation": {"refs": ["images/ref/C-ailu_front.png", "images/creature-kaibuli.png",
                                               "images/extras-yuanzu-disciples.png", "images/scene-hall.png"]}}
        self.assertEqual(pa.shot_entities(shot), ["C-ailu", "CREATURE-kaibuli", "EXTRAS-yuanzu-disciples"])

    def test_audit_segments_reports_gate_as_error(self):
        s = seg(["S-cellar"], [{"shot_id": "SH01", "character_ids": ["CREATURE-kaibuli"]}], [], ["[Shot 1] dark."])
        res = pa.audit_segments([s])
        self.assertTrue(any("E40" in e for e in res["errors"]), res["errors"])

    def test_placeholder_regex_accepts_creature_and_extras(self):
        src = (Path(__file__).resolve().parents[1] / "scripts" / "storyboard" / "compile_layer2_to_h3.py").read_text(encoding="utf-8")
        self.assertIn("(?:C|CREATURE|EXTRAS)-", src)


if __name__ == "__main__":
    unittest.main()
