"""P2-7：短劇（series_format=short）全季分集節奏預設（導演大師對照）。

rhythm_plan：四相位 15/30/35/20（最大餘額法、每相位 ≥1）、<4 集合併相位、
單集不適用；付費卡點數量＝10–15% 中值、攀升末集／風暴末集必卡、末集不卡。
estimate_duration --novel 短劇模式附 short_rhythm（依政策②建議集數）、長篇不附。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ADAPT = SCRIPTS / "adapt"
for p in (SCRIPTS, ADAPT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import short_rhythm  # noqa: E402
import estimate_duration  # noqa: E402


def _phase(plan, key):
    for row in plan["phases"]:
        if key in row["phases"]:
            return row
    return None


class RhythmPlanAllocationTests(unittest.TestCase):
    def test_total_ge_4_covers_all_phases_with_min_one(self):
        for total in (4, 5, 6, 7, 12, 24, 60):
            plan = short_rhythm.rhythm_plan(total)
            self.assertEqual(plan["mode"], "four_phases")
            self.assertEqual(sum(row["episodes"] for row in plan["phases"]), total)
            self.assertTrue(all(row["episodes"] >= 1 for row in plan["phases"]), (total, plan["phases"]))
            # 連續編號
            cursor = 1
            for row in plan["phases"]:
                self.assertEqual(row["start"], cursor)
                cursor = row["end"] + 1
            self.assertEqual(cursor - 1, total)

    def test_ratio_shape_close_to_template(self):
        # 60 集：起勢 9／攀升 18／風暴 21／決戰 12（15/30/35/20 的最大餘額分配）
        plan = short_rhythm.rhythm_plan(60)
        sizes = {row["phases"][0]: row["episodes"] for row in plan["phases"]}
        self.assertEqual(sizes, {"rising": 9, "climbing": 18, "storm": 21, "finale": 12})

    def test_merged_plans_for_two_and_three(self):
        plan2 = short_rhythm.rhythm_plan(2)
        self.assertEqual(plan2["mode"], "merged_phases")
        self.assertEqual([row["label"] for row in plan2["phases"]], ["起勢＋攀升", "風暴＋決戰"])
        plan3 = short_rhythm.rhythm_plan(3)
        self.assertEqual([row["label"] for row in plan3["phases"]], ["起勢", "攀升＋風暴", "決戰"])

    def test_single_episode_has_no_phases(self):
        plan = short_rhythm.rhythm_plan(1)
        self.assertEqual(plan["mode"], "single_episode")
        self.assertEqual(plan["phases"], [])
        self.assertEqual(plan["paywall_positions"], [])

    def test_invalid_total_raises(self):
        with self.assertRaises(ValueError):
            short_rhythm.rhythm_plan(0)
        with self.assertRaises(ValueError):
            short_rhythm.rhythm_plan(-3)


class PaywallPositionTests(unittest.TestCase):
    def test_count_follows_mid_ratio(self):
        # 60 集 × 12.5% = 7.5 → 8 個卡點（10–15% 區間內）
        plan = short_rhythm.rhythm_plan(60)
        self.assertEqual(plan["paywall_count"], 8)
        self.assertGreaterEqual(plan["paywall_count"] / 60, short_rhythm.PAYWALL_RATIO[0])
        self.assertLessEqual(plan["paywall_count"] / 60, short_rhythm.PAYWALL_RATIO[1])

    def test_phase_boundaries_are_paywalls_and_final_episode_is_not(self):
        for total in (4, 6, 12, 24, 60):
            plan = short_rhythm.rhythm_plan(total)
            climbing_end = _phase(plan, "climbing")["end"]
            storm_end = _phase(plan, "storm")["end"]
            positions = plan["paywall_positions"]
            self.assertNotIn(total, positions)
            self.assertTrue(positions == sorted(set(positions)))
            # 風暴末集（決戰前鉤子）優先必卡；卡點數 ≥2 時攀升末集也要卡
            if storm_end < total:
                self.assertIn(storm_end, positions, (total, positions))
            elif climbing_end < total:
                self.assertIn(climbing_end, positions, (total, positions))
            if plan["paywall_count"] >= 2 and climbing_end < total:
                self.assertIn(climbing_end, positions, (total, positions))

    def test_two_episode_plan_paywalls_at_first_episode_end(self):
        plan = short_rhythm.rhythm_plan(2)
        self.assertEqual(plan["paywall_positions"], [1])

    def test_three_episode_plan_paywalls_at_climbing_end(self):
        plan = short_rhythm.rhythm_plan(3)
        self.assertEqual(plan["paywall_positions"], [2])


class EstimateWiringTests(unittest.TestCase):
    NOVEL_TEXT = (
        "「你到底想不想活？」\n" * 40
    )

    def test_short_mode_attaches_short_rhythm(self):
        res = estimate_duration.estimate_novel_duration(self.NOVEL_TEXT, target_seconds=90,
                                                        series_format="short")
        sr = res.get("short_rhythm")
        self.assertIsNotNone(sr)
        self.assertEqual(sr["total_episodes"], res["policies_projection"]["policy_2"]["episodes_needed"])
        self.assertTrue(sr["source"])

    def test_longform_mode_has_no_short_rhythm(self):
        res = estimate_duration.estimate_novel_duration(self.NOVEL_TEXT)
        self.assertIsNone(res.get("short_rhythm"))


if __name__ == "__main__":
    unittest.main()
