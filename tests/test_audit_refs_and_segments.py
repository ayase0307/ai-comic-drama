import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

from audit_refs_and_segments import lint_h3_prompt


def make_prompt(shot_texts, effective="8.708", target="9.000"):
    shots = []
    for idx, text in enumerate(shot_texts, start=1):
        prefix = "" if idx == 1 else f"At 00:{(idx - 1) * 3:02d}.000, "
        shots.append(
            f"[Shot {idx}] {prefix}The frame holds then {text} as the camera holds a static shot."
        )
    return "\n".join([
        "subject_definitions:\nA scene plate.",
        f"summary:\nA {target}s scene ({effective}s effective from {target}s target).",
        "retention_analysis:\nThe scene identity is retained.",
        "detailed_description:\nSoft daylight lights the scene.\n" + "\n".join(shots),
        "overall_soundscape:\nQuiet room tone.",
        "non_diegetic_music:\nNo music.",
    ])


def authored_shots(durations):
    result = []
    cursor = 0.0
    for duration in durations:
        end = cursor + duration
        result.append({"start_time": cursor, "end_time": end, "duration": duration})
        cursor = end
    return result


class AuthoredShotLintTests(unittest.TestCase):
    def test_valid_authored_single_shot_is_preserved_with_clear_warning(self):
        result = lint_h3_prompt(
            make_prompt(["A person waits by the window." ]),
            nominal_duration=9.0,
            authored_shots=authored_shots([9.0]),
        )
        self.assertFalse(any("E2:" in e for e in result["errors"]))
        self.assertTrue(result["details"]["authored_shot_count_exception"])
        self.assertTrue(any("authored" in w.lower() and "1" in w for w in result["warnings"]))

    def test_valid_multi_shot_quantized_timeline_and_cut_points_are_preserved(self):
        result = lint_h3_prompt(
            make_prompt(["A person waits.", "A person turns.", "A person stops."], effective="14.375", target="14.750"),
            nominal_duration=14.75,
            authored_shots=authored_shots([3.0, 3.0, 8.375]),
        )
        self.assertFalse(any("E2:" in e for e in result["errors"]))
        self.assertTrue(result["details"]["authored_shot_count_exception"])
        self.assertEqual(result["details"]["authored_timeline_end_sec"], 14.375)

    def test_legacy_count_rule_is_unchanged_without_authored_context(self):
        result = lint_h3_prompt(make_prompt(["A person waits by the window."]), nominal_duration=9.0)
        self.assertTrue(any("E2:" in e and "鏡頭數量不符" in e for e in result["errors"]))

    def test_discontinuous_authored_shots_do_not_unlock_exception(self):
        shots = authored_shots([5.0, 5.0, 4.75])
        shots[1]["start_time"] += 0.25
        result = lint_h3_prompt(
            make_prompt(["A person waits.", "A person turns.", "A person stops."], effective="14.375", target="14.750"),
            nominal_duration=14.75,
            authored_shots=shots,
        )
        self.assertFalse(result["details"]["authored_shot_count_exception"])
        self.assertTrue(any("E2:" in e and "鏡頭數量不符" in e for e in result["errors"]))
        self.assertTrue(any("ignored" in w.lower() or "未採用" in w for w in result["warnings"]))

    def test_prompt_shot_count_must_match_authored_count(self):
        result = lint_h3_prompt(
            make_prompt(["A person waits.", "A person turns.", "A person stops."], effective="14.375", target="14.750"),
            nominal_duration=14.75,
            authored_shots=authored_shots([7.0, 7.75]),
        )
        self.assertFalse(result["details"]["authored_shot_count_exception"])
        self.assertTrue(any("E2:" in e for e in result["errors"]))

    def test_prompt_cut_points_must_match_authored_end_times(self):
        result = lint_h3_prompt(
            make_prompt(["A person waits.", "A person turns.", "A person stops."], effective="14.375", target="14.750"),
            nominal_duration=14.75,
            authored_shots=authored_shots([4.0, 4.0, 6.75]),
        )
        self.assertFalse(result["details"]["authored_shot_count_exception"])
        self.assertTrue(any("E2:" in e for e in result["errors"]))

    def test_authored_timing_must_cover_nominal_duration_and_match_quantized_summary(self):
        bad_total = lint_h3_prompt(
            make_prompt(["A person waits."]), nominal_duration=9.0,
            authored_shots=authored_shots([8.5]),
        )
        bad_quantized = lint_h3_prompt(
            make_prompt(["A person waits."], effective="8.500"), nominal_duration=9.0,
            authored_shots=authored_shots([9.0]),
        )
        self.assertFalse(bad_total["details"]["authored_shot_count_exception"])
        self.assertFalse(bad_quantized["details"]["authored_shot_count_exception"])

    def test_more_than_eight_authored_shots_do_not_unlock_exception(self):
        result = lint_h3_prompt(
            make_prompt(["A person waits."] * 9, effective="29.708", target="30.000"),
            nominal_duration=30.0,
            authored_shots=authored_shots([30.0 / 9] * 9),
        )
        self.assertFalse(result["details"]["authored_shot_count_exception"])
        self.assertTrue(any("E2:" in e for e in result["errors"]))

    def test_checks_swing_and_no_safe_path_to_strike_are_not_impacts(self):
        result = lint_h3_prompt(
            make_prompt(["Zhang checks his swing and finds no safe path to strike."]),
            nominal_duration=9.0,
            authored_shots=authored_shots([9.0]),
        )
        self.assertFalse(any("E16:" in e for e in result["errors"]))

    def test_executed_strike_without_feedback_still_fails_e16(self):
        result = lint_h3_prompt(
            make_prompt(["Zhang swings the stick at the serpent, then watches it." ]),
            nominal_duration=9.0,
            authored_shots=authored_shots([9.0]),
        )
        self.assertTrue(any("E16:" in e for e in result["errors"]))

    def test_actual_contact_feedback_cues_satisfy_e16(self):
        descriptions = [
            "Zhang swings the stick; the wrist jerks back.",
            "The serpent strikes; its head thrusts back and drives Luonian into the north wall.",
            "The serpent swings its body, recoils west, and Luonian drops to the ground.",
            "Zhang strikes the snake; its neck snaps back and kinks.",
            "The pen strikes; the snake convulses.",
        ]
        for description in descriptions:
            with self.subTest(description=description):
                result = lint_h3_prompt(
                    make_prompt([description]),
                    nominal_duration=9.0,
                    authored_shots=authored_shots([9.0]),
                )
                self.assertFalse(any("E16:" in e for e in result["errors"]))


    def test_match_door_and_clock_are_not_combat(self):
        for description in (
            "She strikes a match and lights the oil lamp.",
            "Match strike crackles softly in the dark.",
            "The cellar door swings open on its hinges.",
            "The hanging lantern swings slowly.",
            "A distant bell strikes six.",
        ):
            with self.subTest(description=description):
                result = lint_h3_prompt(
                    make_prompt([description]),
                    nominal_duration=9.0,
                    authored_shots=authored_shots([9.0]),
                )
                self.assertFalse(any("E16:" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
