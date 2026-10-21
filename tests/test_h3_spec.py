"""H3 幀量子規格回歸測試（17n+5）。

這些測試直接鎖住 2026-10-19 的事故：把 effective_duration_sec 四捨五入成
3 位小數再送，會被服務端向上取整到多 17 幀。
"""
import math
import unittest

from scripts.storyboard import h3_spec


class FrameQuantumTests(unittest.TestCase):
    def test_every_result_is_a_quantum(self):
        for mode in h3_spec.ROUNDING_MODES:
            for tenth in range(10, 300):
                seconds = tenth / 10.0
                frames = h3_spec.frames_for(seconds, rounding=mode)
                self.assertTrue(
                    h3_spec.is_quantum(frames),
                    f"{seconds}s/{mode} → {frames} 不是 17n+5",
                )

    def test_known_values(self):
        cases = [
            (7.0, "floor", 158),
            (7.0, "round", 175),
            (7.0, "ceil", 175),
            (8.0, "floor", 192),
            (11.542, "floor", 277),
            (15.0, "floor", 345),
            (15.0, "ceil", 362),
        ]
        for seconds, mode, expected in cases:
            self.assertEqual(h3_spec.frames_for(seconds, rounding=mode), expected,
                             f"{seconds}s/{mode}")

    def test_eleven_point_five_four_two_is_277(self):
        # 277/24 = 11.541666…；送 11.542 會漂成 294。
        self.assertEqual(h3_spec.frames_for(11.541666666666666, rounding="floor"), 277)
        self.assertEqual(h3_spec.frames_for(11.542, rounding="floor"), 277)

    def test_legacy_rounding_bug_is_reproducible(self):
        """證明舊寫法為什麼會漂：round(277/24, 3) * 24 = 277.008 → 294 幀。"""
        legacy_seconds = round(277 / 24.0, 3)
        self.assertGreater(legacy_seconds * 24.0, 277.0)
        self.assertEqual(h3_spec.quantize_up(math.ceil(legacy_seconds * 24.0)), 294)

    def test_wire_seconds_is_exact(self):
        for frames in (124, 158, 175, 277, 294, 345, 362):
            wire = h3_spec.wire_seconds(frames)
            self.assertEqual(wire, frames / 24.0)
            self.assertEqual(math.ceil(wire * 24.0), frames,
                             f"{frames} 幀送 {wire!r} 後回推失敗")

    def test_quantize_up_and_down(self):
        self.assertEqual(h3_spec.quantize_up(277), 277)
        self.assertEqual(h3_spec.quantize_up(278), 294)
        self.assertEqual(h3_spec.quantize_up(124), 124)
        self.assertEqual(h3_spec.quantize_down(294), 294)
        self.assertEqual(h3_spec.quantize_down(293), 277)
        # n >= 1：最小量子是 22，不是 5
        self.assertEqual(h3_spec.quantize_down(20), 22)
        self.assertEqual(h3_spec.quantize_down(0), 22)
        self.assertFalse(h3_spec.is_quantum(5))
        self.assertTrue(h3_spec.is_quantum(22))

    def test_quantize_rejects_negative(self):
        with self.assertRaises(ValueError):
            h3_spec.quantize_up(-1)
        with self.assertRaises(ValueError):
            h3_spec.quantize_down(-5)
        with self.assertRaises(ValueError):
            h3_spec.nearest_quantum(-1)

    def test_nearest_quantum_absorbs_three_decimal_rounding(self):
        # 這是 review 抓到的反向漂移：6.583*24 = 157.992，floor 會變 141。
        for frames in (124, 141, 158, 175, 192, 209, 226, 243, 260,
                       277, 294, 311, 328, 345, 362):
            rounded_seconds = round(frames / 24.0, 3)
            recovered = h3_spec.nearest_quantum(round(rounded_seconds * 24))
            self.assertEqual(recovered, frames, f"{frames} 幀被 3 位小數四捨五入後回推錯誤")

    def test_nearest_quantum_ties_go_up(self):
        # 277 與 294 的中點 285.5：距離相同時取上，避免回退到較短的段
        self.assertEqual(h3_spec.nearest_quantum(285), 277)
        self.assertEqual(h3_spec.nearest_quantum(285.5), 294)
        self.assertEqual(h3_spec.nearest_quantum(286), 294)

    def test_supported_range(self):
        self.assertTrue(h3_spec.in_supported_range(124))
        self.assertTrue(h3_spec.in_supported_range(362))
        self.assertFalse(h3_spec.in_supported_range(107))
        self.assertFalse(h3_spec.in_supported_range(379))

    def test_plan_reports_drift_and_range(self):
        info = h3_spec.plan(11.542, rounding="floor")
        self.assertEqual(info["frames"], 277)
        self.assertTrue(info["is_quantum"])
        self.assertTrue(info["in_supported_range"])
        self.assertAlmostEqual(info["effective_seconds"], 277 / 24.0, places=9)
        self.assertAlmostEqual(info["drift_seconds"], 277 / 24.0 - 11.542, places=6)

        too_long = h3_spec.plan(20.0, rounding="ceil")
        self.assertFalse(too_long["in_supported_range"])

    def test_validate_plan_surfaces_truncation(self):
        problems = h3_spec.validate_plan(7.0, rounding="floor")
        self.assertTrue(any("ceil" in item for item in problems))
        self.assertEqual(h3_spec.validate_plan(7.0, rounding="ceil"), [])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            h3_spec.frames_for(0)
        with self.assertRaises(ValueError):
            h3_spec.frames_for(7.0, rounding="nearest")
        with self.assertRaises(ValueError):
            h3_spec.seconds_for_frames(0)


if __name__ == "__main__":
    unittest.main()
